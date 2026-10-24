"""Black-box regression for the exact current Northstar buy/sell contract."""
import os
import tempfile
from pathlib import Path
# DB URL is read at import time. Set it BEFORE importing the app.
path = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = "sqlite:///" + str(path)
from fastapi.testclient import TestClient
from app.main import app


def test_end_to_end():
    """Check persistence, replay safety, rejection without mutation, and contracts."""
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert len(c.get("/api/v1/assets").json()) == 7
        assert c.get("/api/v1/assets/aapl").json()["symbol"] == "AAPL"
        assert c.get("/api/v1/assets/NOPE").status_code == 404
        assert len(c.get("/api/v1/indexes").json()) == 3
        before = c.get("/api/v1/portfolio").json()
        assert before["cash"] == 12450
        header = {"Idempotency-Key":"test-1"}
        body = {"symbol":"aapl","side":"BUY","quantity":2}
        order = c.post("/api/v1/orders", headers=header, json=body)
        assert order.status_code == 201
        assert order.json()["order"]["status"] == "SIMULATED"
        assert c.post("/api/v1/orders", headers=header, json=body).status_code == 200
        assert c.post("/api/v1/orders", headers=header, json={**body,"quantity":3}).status_code == 409
        assert len(c.get("/api/v1/orders").json()) == 1
        after = c.get("/api/v1/portfolio").json()
        assert after["cash"] == 12450 - 228.87*2
        assert next(p for p in after["positions"] if p["symbol"]=="AAPL")["quantity"]==6
        assert c.post("/api/v1/orders",headers={"Idempotency-Key":"bad-sale"},json={"symbol":"TSLA","side":"SELL","quantity":1}).status_code == 409
        assert c.get("/api/v1/portfolio").json() == after
