"""HTTP boundary for the Northstar stock simulation (not real brokerage)."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from . import store


class OrderInput(BaseModel):
    """Validate untrusted HTTP input before touching money or positions."""
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=16)
    side: str
    quantity: int = Field(strict=True, ge=1, le=1_000_000)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, symbol: str) -> str:
        """Normalize mobile input, keeping lookup deterministic."""
        return symbol.strip().upper()

    @field_validator("side")
    @classmethod
    def validate_side(cls, side: str) -> str:
        """Reject unknown order types instead of assuming BUY."""
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        return side


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Set up durable tables once on application start."""
    store.initialize()
    yield

app = FastAPI(title="Northstar Python learning backend", version="1.0.0", lifespan=lifespan)
# Local learning: permit Expo web. Restrict origins before deploying publicly.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8081", "http://localhost:19006", "http://localhost:3000"], allow_methods=["GET","POST"], allow_headers=["Content-Type","Idempotency-Key"])


@app.exception_handler(HTTPException)
async def api_error(_, exc: HTTPException):
    """Keep business errors compatible with the existing mobile OrderResult."""
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "message": str(exc.detail)})


@app.get("/health")
def health():
    """Basic liveness endpoint; production readiness should also test dependencies."""
    return {"status": "ok", "service": "python-fastapi"}


@app.get("/api/v1/assets")
def list_assets(q: str = Query("", max_length=100)):
    """Filter immutable sample quotes by symbol or company name."""
    needle = q.strip().lower()
    return [{k:v for k,v in a.items() if k!="priceCents"} for a in store.ASSETS if needle in a["symbol"].lower() or needle in a["companyName"].lower()]


@app.get("/api/v1/assets/{symbol}")
def get_asset(symbol: str):
    """Return one known asset, otherwise a truthful 404."""
    a = store.BY_SYMBOL.get(symbol.upper())
    if a is None:
        raise HTTPException(404, "That asset is not available in the sample market.")
    return {k:v for k,v in a.items() if k!="priceCents"}


@app.get("/api/v1/indexes")
def list_indexes():
    """Provide the exact three illustrative indexes displayed on Discover."""
    return store.INDEXES


@app.get("/api/v1/portfolio")
def get_portfolio():
    """Derive a consistent view of cash, positions and sample market value."""
    return store.portfolio()


@app.get("/api/v1/orders")
def get_orders():
    """Return persisted order activity instead of app-local array state."""
    return store.orders()


@app.post("/api/v1/orders")
def place_order(order: OrderInput, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    """Validate and atomically record one simulation; retry key prevents repeats.

    The account lock protects read-then-write from overspending in parallel.
    A database unique constraint is the final line of defense for retries.
    """
    key = idempotency_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise HTTPException(400, "Supply an Idempotency-Key of 1–128 safe characters.")
    asset = store.BY_SYMBOL.get(order.symbol)
    if asset is None:
        raise HTTPException(404, "That asset is not available in the sample market.")
    with store.engine.connect() as db:
        if not store.POSTGRES:
            # Claim SQLite's write lock before reading current cash/holdings.
            db.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            db.begin()
        try:
            cash = store.account_lock(db)
            prior = db.execute(text("SELECT * FROM orders WHERE idempotency_key=:k"), {"k":key}).mappings().first()
            if prior:
                if (prior["symbol"], prior["side"], prior["quantity"]) != (order.symbol,order.side,order.quantity):
                    raise HTTPException(409, "Idempotency-Key was already used for a different order.")
                db.commit()
                return JSONResponse(status_code=200, content={"ok":True,"order":store.serialize_order(prior)})
            position = db.execute(text("SELECT quantity,average_cost_cents FROM positions WHERE symbol=:s"), {"s":order.symbol}).mappings().first()
            price = int(asset["priceCents"])
            amount = price * order.quantity
            if order.side == "BUY" and amount > cash:
                raise HTTPException(409, "There is not enough demo cash for this order.")
            if order.side == "SELL" and (not position or position["quantity"] < order.quantity):
                raise HTTPException(409, "You do not own enough shares for this demo sale.")
            if order.side == "BUY":
                if position:
                    new_qty = position["quantity"] + order.quantity
                    avg = (position["average_cost_cents"] * position["quantity"] + amount + new_qty//2) // new_qty
                    db.execute(text("UPDATE positions SET quantity=:q,average_cost_cents=:a WHERE symbol=:s"), {"q":new_qty,"a":avg,"s":order.symbol})
                else:
                    db.execute(text("INSERT INTO positions(symbol,quantity,average_cost_cents) VALUES (:s,:q,:a)"),{"s":order.symbol,"q":order.quantity,"a":price})
            else:
                remain = position["quantity"] - order.quantity
                if remain == 0:
                    db.execute(text("DELETE FROM positions WHERE symbol=:s"), {"s":order.symbol})
                else:
                    db.execute(text("UPDATE positions SET quantity=:q WHERE symbol=:s"), {"q":remain,"s":order.symbol})
            db.execute(text("UPDATE accounts SET cash_cents=:c WHERE id=1"), {"c":cash - amount if order.side == "BUY" else cash + amount})
            dto={"id":str(uuid4()),"symbol":order.symbol,"side":order.side,"quantity":order.quantity,"price":price/100,"createdAt":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"status":"SIMULATED"}
            db.execute(text("INSERT INTO orders(id,idempotency_key,symbol,side,quantity,price_cents,created_at,status) VALUES (:id,:key,:s,:side,:q,:p,:date,'SIMULATED')"), {"id":dto["id"],"key":key,"s":order.symbol,"side":order.side,"q":order.quantity,"p":price,"date":dto["createdAt"]})
            db.commit()
            return JSONResponse(status_code=201,content={"ok":True,"order":dto})
        except Exception:
            db.rollback()
            raise
