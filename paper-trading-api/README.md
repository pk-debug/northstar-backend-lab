# API and deployment

## Relationship to northstar-backend-lab

The lab's v1 HTTP contract inspired the asset DTO, order request, idempotency header and order response in this project. Its README explicitly describes a single unauthenticated shared demo portfolio. It uses USD/US fixtures. A mobile release must not present that as a private Indian brokerage account.

`paper-trading-api/` is the v2 implementation using the app's seven INR/NSE fixtures. Each user has separate cash, holdings, orders, sessions and watchlist. It is separate from the five original v1 lab implementations. There is no compatibility flag that silently trusts the old shared account.

## Routes

| Method | Path | Authentication | Result |
|---|---|---|---|
| GET | `/health` | public | Liveness plus a database query |
| POST | `/api/v2/auth/register` | public, rate limited | New practice account + session |
| POST | `/api/v2/auth/login` | public, rate limited | Session token, expiry epoch seconds |
| POST | `/api/v2/auth/logout` | bearer | Revoke this session, 204 |
| DELETE | `/api/v2/account` | bearer | Delete profile and dependent data, 204 |
| GET | `/api/v2/assets?q=TCS` | public | Synthetic INR asset list |
| GET | `/api/v2/indexes` | public | Synthetic index list |
| GET | `/api/v2/snapshot` | bearer | Consistent cash, positions, latest 500 orders, watchlist, currency |
| POST | `/api/v2/orders` | bearer + Idempotency-Key | 201 new order / 200 same-key replay |
| PUT | `/api/v2/watchlist/{symbol}` | bearer | Idempotent add, 204 |
| DELETE | `/api/v2/watchlist/{symbol}` | bearer | Idempotent remove, 204 |

Credentials: `{"username":"trader.pawan","password":"a-unique-12-plus-character-password"}`. Usernames are lowercased and allow letters, digits, dot, underscore and hyphen. They are not a verified identity or KYC. No recovery email or password-reset flow is implemented; do not use this as a real-money identity provider.

Order: `{"symbol":"RELIANCE","side":"BUY","quantity":1}`. The server reads price from fixtures; extra fields such as `price` or `userId` are rejected. Quantities must be integer 1–1,000,000. Same UUID with a different payload returns 409. The uniqueness scope is user + UUID. Server writes are transactional and use integer paise. Same-key replay is checked before balance validation, so it still succeeds after the original trade has consumed cash.

Snapshot: `{cash,positions:[{symbol,quantity,averageCost}],orders:[{id,symbol,side,quantity,price,createdAt,status:"SIMULATED"}],watchlist:[symbol],currency:"INR"}`. Timestamps are UTC ISO-8601. Error bodies contain a safe message; raw validation values, SQL and exception traces are excluded. 401 means reauthenticate, 409 is a business conflict, 422 invalid input, 429 wait before retrying. A network failure or 5xx after POST is ambiguous: retain the original UUID.

## Local and container operation

From this repository's root (Python 3.12):

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r paper-trading-api/requirements.lock
NORTHSTAR_DB=/tmp/northstar.sqlite3 uvicorn app.main:app --app-dir paper-trading-api --host 127.0.0.1 --port 8000 --no-access-log
# In another terminal with the same virtual environment:
PYTHONPATH=paper-trading-api NORTHSTAR_DB=/tmp/northstar-bootstrap.sqlite3 pytest -q paper-trading-api/tests
```

The native client is [kmpNativeUiTrading](https://github.com/pk-debug/kmpNativeUiTrading). Connect using its `apiOrigin`/`NORTHSTAR_API_ORIGIN` configuration. This service uses INR and `/api/v2`, not the v1 USD lab contract. No broker API keys are required for paper trading.

For containers:

```bash
cd paper-trading-api
docker compose up --build -d
curl --fail http://127.0.0.1:8000/health
```

Compose binds to loopback. Put an HTTPS reverse proxy in front for a reachable deployment; DNS and a hosting account are operator inputs. No public deployment was performed during implementation. The container runs without root privileges and uses a persistent volume. Run **one instance** against that volume. SQLite write locking is not a substitute for multi-region architecture.

At the ingress, set a conservative request-body limit (e.g. 16 KiB), per-IP/request rate limits, TLS certificates and timeouts. Trust forwarded headers only from your proxy. The app service's auth counters limit repeated password hashing per username and direct client IP. Uvicorn disables access logs in the supplied container command; never log credentials, bearer headers, request bodies or full portfolios. Add structured operational metrics with redaction before a public launch.

Back up the SQLite database using SQLite's online backup API, encrypt backups and test restoration. Protect the volume and host disk. Account deletion removes active rows, not prior backups: publish your actual backup-retention policy. For multiple instances, migrate to PostgreSQL with migrations, row-level account locks and concurrency tests before scaling.
