"""A small paper exchange: the server, never the phone, owns account balances.

The v1 asset/order JSON shapes come from pk-debug/northstar-backend-lab.
This v2 service adds isolated users, expiring sessions and account deletion.
Prices are fixtures, not a live exchange. Run behind HTTPS in public deployments.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

DB_PATH = os.environ.get('NORTHSTAR_DB', 'northstar.sqlite3')
ASSETS = json.loads(Path(__file__).with_name('assets.json').read_text())
INDEXES = json.loads(Path(__file__).with_name('indexes.json').read_text())
BY_SYMBOL = {a['symbol']: a for a in ASSETS}
SESSION_SECONDS = 8 * 60 * 60
app = FastAPI(title='Northstar paper trading', version='2.0.0')


@contextmanager
def transaction():
    """One write lock makes check-balance-and-spend a single indivisible action."""
    db = sqlite3.connect(DB_PATH, timeout=15)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    """Versioned migrations should replace this schema bootstrap before schema v2."""
    with transaction() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
          salt TEXT NOT NULL, cash INTEGER NOT NULL CHECK(cash>=0));
        CREATE TABLE IF NOT EXISTS sessions (
          digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS positions (
          user_id TEXT REFERENCES users(id) ON DELETE CASCADE, symbol TEXT,
          quantity INTEGER NOT NULL CHECK(quantity>0), cost INTEGER NOT NULL,
          PRIMARY KEY(user_id,symbol));
        CREATE TABLE IF NOT EXISTS orders (
          id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
          key TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, quantity INTEGER NOT NULL,
          price INTEGER NOT NULL, created TEXT NOT NULL, UNIQUE(user_id,key));
        CREATE TABLE IF NOT EXISTS watchlist (
          user_id TEXT REFERENCES users(id) ON DELETE CASCADE, symbol TEXT,
          PRIMARY KEY(user_id,symbol));
        CREATE TABLE IF NOT EXISTS auth_attempts (
          bucket TEXT PRIMARY KEY, started INTEGER NOT NULL, attempts INTEGER NOT NULL);
        ''')


@app.middleware('http')
async def security_headers(request: Request, call_next):
    """Prevent caches from retaining private balances or login responses."""
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Request-ID'] = str(uuid4())
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError):
    """Pydantic error details can echo passwords; return only a safe summary."""
    return JSONResponse(status_code=422, content={'ok': False, 'message': 'Check the request fields and try again.'})


@app.exception_handler(HTTPException)
async def business_error(_: Request, exc: HTTPException):
    """The phone receives a safe message, never a database query or stack trace."""
    return JSONResponse(status_code=exc.status_code, content={'ok': False, 'message': exc.detail})


def password_hash(password: str, salt: str) -> str:
    """A slow salted hash makes stolen password tables harder to crack."""
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def rate_limit(request: Request, username: str):
    """Bound password guessing by both account and direct client address.

    Do not trust an arbitrary X-Forwarded-For header. Configure trusted proxies
    in the HTTP server and add gateway rate limits for distributed deployments.
    """
    now = int(time.time())
    buckets = ['account:' + username, 'ip:' + (request.client.host if request.client else 'unknown')]
    with transaction() as db:
        db.execute('DELETE FROM auth_attempts WHERE started<?', (now - 900,))
        for bucket in buckets:
            row = db.execute('SELECT attempts FROM auth_attempts WHERE bucket=?', (bucket,)).fetchone()
            if row and row['attempts'] >= 15:
                raise HTTPException(429, 'Too many sign-in attempts. Try again in 15 minutes.')
        for bucket in buckets:
            db.execute('INSERT INTO auth_attempts VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1', (bucket, now))


class Credentials(BaseModel):
    """Use a showcase username, so the app does not need a real phone number."""
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=40, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=12, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize(cls, value):
        return value.lower()


def issue_session(db, user_id):
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + SESSION_SECONDS
    db.execute('DELETE FROM sessions WHERE expires<?', (int(time.time()),))
    db.execute('INSERT INTO sessions VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id, expires))
    return {'token': token, 'expiresAt': expires}


@app.post('/api/v2/auth/register', status_code=201)
def register(body: Credentials, request: Request):
    """Give each new user an empty, isolated practice account with ₹10 lakh."""
    rate_limit(request, body.username)
    salt = secrets.token_hex(16)
    hashed = password_hash(body.password, salt)
    with transaction() as db:
        try:
            user_id = str(uuid4())
            db.execute('INSERT INTO users VALUES (?,?,?,?,?)', (user_id, body.username, hashed, salt, 100_000_000))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'That username is unavailable.')
        return issue_session(db, user_id)


@app.post('/api/v2/auth/login')
def login(body: Credentials, request: Request):
    rate_limit(request, body.username)
    with transaction() as db:
        user = db.execute('SELECT * FROM users WHERE username=?', (body.username,)).fetchone()
        salt = user['salt'] if user else '00' * 16
        candidate = password_hash(body.password, salt)
        if not user or not hmac.compare_digest(candidate, user['password']):
            raise HTTPException(401, 'Username or password is incorrect.')
        return issue_session(db, user['id'])


def current_user(authorization: str = Header(default='')):
    """Only a valid, unexpired bearer session can select an account."""
    scheme, _, token = authorization.partition(' ')
    if scheme != 'Bearer' or not token or len(token) > 200:
        raise HTTPException(401, 'Please sign in again.')
    digest = hashlib.sha256(token.encode()).hexdigest()
    with transaction() as db:
        row = db.execute('SELECT user_id FROM sessions WHERE digest=? AND expires>?', (digest, int(time.time()))).fetchone()
        if not row:
            raise HTTPException(401, 'Please sign in again.')
        return row['user_id'], digest


@app.post('/api/v2/auth/logout', status_code=204)
def logout(user=Depends(current_user)):
    with transaction() as db:
        db.execute('DELETE FROM sessions WHERE digest=?', (user[1],))


@app.delete('/api/v2/account', status_code=204)
def delete_account(user=Depends(current_user)):
    """Cascades remove this user's sessions, holdings, watchlist and orders."""
    with transaction() as db:
        db.execute('DELETE FROM users WHERE id=?', (user[0],))


@app.get('/health')
def health():
    with transaction() as db:
        db.execute('SELECT 1 FROM users LIMIT 1')
    return {'status': 'ok', 'service': 'northstar-paper-v2'}


@app.get('/api/v2/assets')
def assets(q: str = ''):
    if len(q) > 100:
        raise HTTPException(400, 'Search is too long.')
    return [a for a in ASSETS if q.lower() in (a['symbol'] + a['companyName']).lower()]


@app.get('/api/v2/indexes')
def indexes():
    return INDEXES


def order_dto(row):
    return dict(id=row['id'], symbol=row['symbol'], side=row['side'], quantity=row['quantity'],
                price=row['price']/100, createdAt=row['created'], status='SIMULATED')


@app.get('/api/v2/snapshot')
def snapshot(user=Depends(current_user)):
    """Read orders and balance together, so the UI cannot show mixed revisions."""
    with transaction() as db:
        account = db.execute('SELECT cash FROM users WHERE id=?', (user[0],)).fetchone()
        if account is None:
            raise HTTPException(401, 'Please sign in again.')
        cash = account['cash']
        positions = [dict(symbol=r['symbol'], quantity=r['quantity'], averageCost=r['cost']/100)
                     for r in db.execute('SELECT * FROM positions WHERE user_id=? ORDER BY symbol', (user[0],))]
        orders = [order_dto(r) for r in db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY rowid DESC LIMIT 500', (user[0],))]
        watchlist = [r['symbol'] for r in db.execute('SELECT symbol FROM watchlist WHERE user_id=? ORDER BY symbol', (user[0],))]
    return dict(cash=cash/100, positions=positions, orders=orders, watchlist=watchlist, currency='INR')


class OrderInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str = Field(min_length=1, max_length=16)
    side: str = Field(pattern='^(BUY|SELL)$')
    quantity: int = Field(strict=True, ge=1, le=1_000_000)

    @field_validator('symbol')
    @classmethod
    def normalize(cls, value):
        return value.strip().upper()


@app.post('/api/v2/orders')
def place_order(body: OrderInput, idempotency_key: str = Header(alias='Idempotency-Key'), user=Depends(current_user)):
    """Same user + same key + same payload returns one order, even after a timeout."""
    if not re.fullmatch(r'[a-zA-Z0-9._:-]{1,128}', idempotency_key):
        raise HTTPException(400, 'Invalid order key.')
    asset = BY_SYMBOL.get(body.symbol)
    if asset is None:
        raise HTTPException(404, 'Unknown sample stock.')
    with transaction() as db:
        prior = db.execute('SELECT * FROM orders WHERE user_id=? AND key=?', (user[0], idempotency_key)).fetchone()
        if prior:
            if (prior['symbol'], prior['side'], prior['quantity']) != (body.symbol, body.side, body.quantity):
                raise HTTPException(409, 'This order key belongs to a different order.')
            return {'ok': True, 'order': order_dto(prior)}
        account = db.execute('SELECT cash FROM users WHERE id=?', (user[0],)).fetchone()
        if account is None:
            raise HTTPException(401, 'Please sign in again.')
        cash = account['cash']
        position = db.execute('SELECT * FROM positions WHERE user_id=? AND symbol=?', (user[0], body.symbol)).fetchone()
        price = round(asset['price'] * 100)
        total = price * body.quantity
        quantity = position['quantity'] if position else 0
        if body.side == 'BUY':
            if total > cash:
                raise HTTPException(409, 'Not enough practice cash.')
            new_quantity = quantity + body.quantity
            cost = ((position['cost'] * quantity if position else 0) + total + new_quantity // 2) // new_quantity
            db.execute('INSERT INTO positions VALUES (?,?,?,?) ON CONFLICT(user_id,symbol) DO UPDATE SET quantity=excluded.quantity,cost=excluded.cost', (user[0], body.symbol, new_quantity, cost))
            cash -= total
        else:
            if body.quantity > quantity:
                raise HTTPException(409, 'Not enough shares.')
            remain = quantity - body.quantity
            if remain:
                db.execute('UPDATE positions SET quantity=? WHERE user_id=? AND symbol=?', (remain, user[0], body.symbol))
            else:
                db.execute('DELETE FROM positions WHERE user_id=? AND symbol=?', (user[0], body.symbol))
            cash += total
        db.execute('UPDATE users SET cash=? WHERE id=?', (cash, user[0]))
        order_id = str(uuid4())
        created = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        db.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)', (order_id, user[0], idempotency_key, body.symbol, body.side, body.quantity, price, created))
        row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        return JSONResponse(status_code=201, content={'ok': True, 'order': order_dto(row)})


@app.put('/api/v2/watchlist/{symbol}', status_code=204)
def watch(symbol: str, user=Depends(current_user)):
    if symbol not in BY_SYMBOL:
        raise HTTPException(404, 'Unknown sample stock.')
    with transaction() as db:
        db.execute('INSERT OR IGNORE INTO watchlist VALUES (?,?)', (user[0], symbol))


@app.delete('/api/v2/watchlist/{symbol}', status_code=204)
def unwatch(symbol: str, user=Depends(current_user)):
    with transaction() as db:
        db.execute('DELETE FROM watchlist WHERE user_id=? AND symbol=?', (user[0], symbol))


initialize()
