# Northstar V1 HTTP contract

All services deliberately implement the same contract, created from the actual `reactNativeStock` TypeScript model. **All prices and indexes are synthetic sample data**. Each backend uses its OWN state/database; switching ports will not merge balances. No authentication or real brokerage is implemented.

## Routes

| HTTP | URI | Success payload | Notes |
|---|---|---|---|
| GET | `/health` | `{ "status": "ok", "service": "..." }` | Readiness demonstration |
| GET | `/api/v1/assets?q=app` | `MarketAsset[]` | Filter ticker OR company, case-insensitive |
| GET | `/api/v1/assets/AAPL` | `MarketAsset` | Unknown: 404 |
| GET | `/api/v1/indexes` | `MarketIndex[]` | Static, illustrative |
| GET | `/api/v1/portfolio` | `Portfolio` | Persisted demo account |
| GET | `/api/v1/orders` | `SimulatedOrder[]` | Newest first |
| POST | `/api/v1/orders` | `{ "ok": true, "order": SimulatedOrder }` (201) | `Idempotency-Key` required; body below |

POST body: `{ "symbol": "AAPL", "side": "BUY", "quantity": 1 }`.
`Idempotency-Key`: caller-generated UUID (same key for network retries of the SAME order only).

`MarketAsset`: `{symbol, companyName, exchange, price, change, changePercent, history, category}`. Numeric prices in dollars match the mobile code. `Portfolio`: `{cash, positions: [{symbol,quantity,averageCost}], totalValue, positionsValue}`. `SimulatedOrder`: `{id,symbol,side,quantity,price,createdAt,status:"SIMULATED"}`.

For order errors: `{ "ok": false, "message": "..." }`. Invalid data 400, insufficient cash/holdings 409, unknown asset 404, duplicate key with different payload 409. For the same key and same order request return the original saved order with HTTP 200 and no ledger mutation. Whitespace around the symbol is trimmed and normalized uppercase.

## State and invariants
- Each project has one shared DEMO account, not per-user isolation. It starts with $12,450.00 cash and AAPL 4 @ $182.45, MSFT 2 @ $402.20, VOO 3 @ $494.10.
- Only integer positive quantities. Price is read from SERVER fixtures, never accepted from the request.
- Every successful buy/sell writes the ledger and order atomically, with an idempotency key unique constraint.
- `averageCost` uses weighted average on buys and remains unchanged on partial sales. Empty positions are deleted.
- Money is stored in integral **cents**, avoiding binary floating-point ledger errors. Presentation converts to dollars; a rounded cent is used for a weighted average.
- This is intentionally a *single-account learning lab*. Add user identities, authn/authz, CSRF considerations for browser use, migrations, ledger auditing, rate limits, external pricing sources and production-grade isolation before deployment.

## Suggested curl smoke test
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/assets?q=aapl
curl http://localhost:8000/api/v1/portfolio
curl -i -X POST http://localhost:8000/api/v1/orders \\
  -H 'Content-Type: application/json' -H 'Idempotency-Key: lesson-buy-1' \\
  -d '{"symbol":"AAPL","side":"BUY","quantity":1}'
curl http://localhost:8000/api/v1/orders
```
