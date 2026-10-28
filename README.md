# Northstar: five-language backend engineering lab

**Source React Native app:** https://github.com/pk-debug/reactNativeStock (`main`, inspected 2026-10-25). The seven assets, three index values, local initial cash and portfolio were transcribed from the repo's `marketData.ts` and `TradingProvider.tsx`.

## Native app paper-trading API

The authenticated INR service for [kmpNativeUiTrading](https://github.com/pk-debug/kmpNativeUiTrading) lives in **[paper-trading-api/](paper-trading-api/README.md)**. It adds isolated users, expiring sessions, watchlists, account deletion and transactional/idempotent orders under `/api/v2`. It is separate from the five original v1 language-comparison implementations. Its Docker Compose file is local to that folder.

## Folders

```text
shared/              API contract, exact fixture data, 5W2H, database choices
java-spring/         Spring Boot REST API, JDBC, H2 or PostgreSQL
kotlin-ktor/         Ktor REST API, JDBC, H2 or PostgreSQL
go-http/             Go net/http, database/sql, SQLite or PostgreSQL
node-express/        Express+TypeScript, SQLite or PostgreSQL
python-fastapi/      Original v1 FastAPI+SQLAlchemy lab, SQLite or PostgreSQL
paper-trading-api/   Authenticated v2 INR paper accounts for the native KMP app
mobile-integration/  Expo API client and integration guide
contracts/           black-box API compatibility tests
```

Read [ELI15 code walkthrough](ELI15-CODE-WALKTHROUGH.md) for transaction statements explained line-by-line.

Each of the five original v1 services: `GET /health`, `GET /api/v1/assets`, `GET /api/v1/assets/{symbol}`, `GET /api/v1/indexes`, `GET /api/v1/portfolio`, `GET /api/v1/orders`, `POST /api/v1/orders`. See [full contract](shared/api-contract.md).

## Start your first backend: Python
```bash
cd python-fastapi
python -m venv .venv
source .venv/bin/activate    # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
`http://localhost:8000/docs` displays interactive OpenAPI. The default SQLite DB is created automatically.

## Run the other four

| Folder | Run (after installing prerequisites / dependencies) | Default port |
|---|---|---|
| `node-express` | `npm install && npm run dev` | 3000 |
| `go-http` | `go mod tidy && go run ./cmd/server` | 8080 |
| `java-spring` | `mvn spring-boot:run` (Maven + Java 21) | 8081 |
| `kotlin-ktor` | `gradle run` (Gradle + Java 21) | 8082 |

By default each backend uses **its own** local SQLite (Go/Node/Python) or H2 (Java/Kotlin) file; change to PostgreSQL using each `.env.example` and [database guide](shared/database-options.md). In five terminals, all five APIs work independently with the same JSON shape.

## Docker: launch all five implementations
```bash
docker compose --profile backends up --build
# Check endpoints on 8000, 3000, 8080, 8081, 8082.
# First build needs internet to download language dependencies and Docker images.
```
This optional mode uses **five separate PostgreSQL databases**, all hosted in one PostgreSQL container. Dockerfiles are learning examples, not hardened production images.

## PostgreSQL locally
```bash
docker compose up -d postgres
# For each backend configure the PostgreSQL environment in its .env.example.
# Note: compose creates the 5 databases only on FIRST initialization of the PG volume.
```

## Test a backend independently
```bash
python contracts/smoke.py http://localhost:8000
python contracts/smoke.py http://localhost:3000
python contracts/smoke.py http://localhost:8080
```
Tests mutate demo state, so use fresh databases for repeatable initial-cash assertions. `contracts/smoke.py` only asserts invariants, and can run against already-mutated demo state.

## Learning rule
Follow folder-local `5W2H.md`; read each source file's module, class and function docstrings. Comment lines explain non-obvious decisions, not obvious syntax. The five original v1 services are **educational starter implementations** with genuine transactional persistence, not production trading systems. No brokers, live quotes, user accounts or authorization are included. **Never expose them publicly**: order endpoints operate on one shared demo portfolio.

## Interview narrative
"I translated an existing React Native stock demo into five comparable backend implementations. I kept a stable REST contract and validated amounts server-side in cents, implemented transactions and idempotency, and compared JVM, Go, Node and Python error-handling, database access and concurrency trade-offs. I intentionally made pricing static and did not present this as a real trading backend."
