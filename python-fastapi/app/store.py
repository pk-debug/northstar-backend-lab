"""Persistence layer: SQLite for fast learning, PostgreSQL for server-side locking.

5W2H: WHAT SQL transactions; WHY prevent half-completed orders; WHO one demo
account; WHEN on every POST; WHERE local DB/server; HOW SQLAlchemy Core;
HOW MUCH no managed database is required for the tutorial.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

# Use an environment variable so the same API can target another SQL engine.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./northstar.db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
POSTGRES = engine.dialect.name == "postgresql"
ASSETS = json.loads((Path(__file__).resolve().parents[2] / "shared" / "market-assets.json").read_text())
INDEXES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "market-indexes.json").read_text())
BY_SYMBOL = {a["symbol"]: a for a in ASSETS}


def initialize() -> None:
    """Create tutorial schema and seed once; do not reset persistent user actions."""
    # These portable SQL statements work with SQLite and PostgreSQL.
    with engine.begin() as db:
        db.execute(text("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, cash_cents BIGINT NOT NULL CHECK(cash_cents >= 0))"))
        db.execute(text("CREATE TABLE IF NOT EXISTS positions (symbol VARCHAR(16) PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity > 0), average_cost_cents BIGINT NOT NULL CHECK(average_cost_cents >= 0))"))
        db.execute(text("CREATE TABLE IF NOT EXISTS orders (id VARCHAR(64) PRIMARY KEY, idempotency_key VARCHAR(128) UNIQUE NOT NULL, symbol VARCHAR(16) NOT NULL, side VARCHAR(4) NOT NULL, quantity INTEGER NOT NULL, price_cents BIGINT NOT NULL, created_at VARCHAR(40) NOT NULL, status VARCHAR(16) NOT NULL)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)"))
        if db.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one() == 0:
            db.execute(text("INSERT INTO accounts (id,cash_cents) VALUES (1,1245000)"))
            for symbol, qty, avg in (("AAPL", 4, 18245), ("MSFT", 2, 40220), ("VOO", 3, 49410)):
                db.execute(text("INSERT INTO positions(symbol,quantity,average_cost_cents) VALUES (:s,:q,:a)"), {"s":symbol,"q":qty,"a":avg})


def account_lock(db: Connection) -> int:
    """Lock one account row before read/modify/write; serialize competing orders.

    PostgreSQL uses row-level FOR UPDATE. SQLite's BEGIN IMMEDIATE is invoked
    *before* any reads inside the write transaction by the order service.
    """
    sql = "SELECT cash_cents FROM accounts WHERE id=1" + (" FOR UPDATE" if POSTGRES else "")
    return int(db.execute(text(sql)).scalar_one())


def portfolio() -> dict:
    """Calculate market value from fixture quotes; persisted state is the ledger."""
    with engine.connect() as db:
        cash = int(db.execute(text("SELECT cash_cents FROM accounts WHERE id=1")).scalar_one())
        rows = db.execute(text("SELECT symbol,quantity,average_cost_cents FROM positions ORDER BY symbol")).mappings().all()
    positions = [{"symbol":r["symbol"],"quantity":r["quantity"],"averageCost":r["average_cost_cents"]/100} for r in rows]
    value = sum(BY_SYMBOL[p["symbol"]]["priceCents"] * p["quantity"] for p in positions)
    return {"cash":cash/100,"positions":positions,"positionsValue":value/100,"totalValue":(value+cash)/100}


def serialize_order(row) -> dict:
    """Translate database snake_case and integral cents into mobile TS shape."""
    return {"id":row["id"],"symbol":row["symbol"],"side":row["side"],"quantity":row["quantity"],"price":row["price_cents"]/100,"createdAt":row["created_at"],"status":row["status"]}


def orders() -> list[dict]:
    """List committed simulated orders newest first; never show pending writes."""
    with engine.connect() as db:
        rows = db.execute(text("SELECT * FROM orders ORDER BY created_at DESC,id DESC")).mappings().all()
    return [serialize_order(r) for r in rows]
