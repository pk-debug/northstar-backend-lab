# Database connection options and honest implementation status

A database is chosen for its **data access requirements**, not because a resume needs many brand names. The five codebases provide **working local embedded database + PostgreSQL connection paths**. They do not claim feature-complete connectors to every item below. Start with a relational ledger and deliberate business constraints.

| Database | This project | Where it fits | Connection/learning example |
|---|---|---|---|
| SQLite | **Implemented in Go, Node and Python** | No-server local tutorial | `DATABASE_URL=sqlite:///./northstar.db` (Python); project-specific env docs |
| H2 | **Implemented in Java and Kotlin** | No-server local JVM tutorial | JDBC `jdbc:h2:file:./northstar` |
| PostgreSQL | **Implemented in all five** | Primary durable shared server state | `postgres://northstar:northstar@localhost:5432/northstar` (JDBC for JVM) |
| MySQL | Design option (not wired) | Traditional relational apps | JDBC/MySQL driver, SQLAlchemy `mysql+pymysql://...`, mysql2 for Node |
| SQL Server | Design option (not wired) | .NET/enterprise | JDBC SQL Server, pyodbc, tedious |
| MongoDB | Design option (not wired) | Document read models | mongodb://localhost:27017 (avoid splitting atomic trading ledger without design) |
| Redis | Example config; not a primary SQL replacement | Cached quotes / rate limiting | redis://localhost:6379; use TTL and invalidation |
| Elasticsearch | Optional planned search | Full-text / analytics | http://localhost:9200; index source-of-truth DB records asynchronously |
| DynamoDB | Optional AWS architecture | Key-value with access-pattern-first modeling | AWS SDK, table, region, IAM (cost can apply) |
| Cosmos DB | Optional Azure architecture | Globally distributed multi-model workloads | Azure SDK, account URI + identity (cost can apply) |
| Firestore | Optional Firebase architecture | Mobile-focused document sync | Firebase Admin SDK, service account and security rules |
| InfluxDB | Optional observability architecture | Time-series measurements | InfluxDB client, bucket/token |
| TimescaleDB | Optional PostgreSQL extension | Time-series on PostgreSQL | PostgreSQL driver + enabled extension |

For production-like testing, run `docker compose up -d postgres`; each backend chooses PostgreSQL via its `.env.example`. All five services using the same credentials **would share one portfolio**; use the five provided separate DB names and ports to keep examples independent. `db/init/01-create-databases.sql` creates those names on first volume initialization.

## What to practice after each backend is working
1. Unique indexes and `EXPLAIN ANALYZE` for frequently queried stock symbols and descending order history.
2. `SERIALIZABLE` / row-locking and contention; read committed transaction boundaries and idempotent retry behavior.
3. Proper migration tools rather than the educational create-on-start schema.
4. Redis cache-aside for *read-only* fixtures; do not cache authoritative mutable cash during order placement.
5. Connection pool sizing, slow-query logs, optimistic concurrency and load tests.

## Concurrency note
PostgreSQL order transactions lock the single account row with `SELECT ... FOR UPDATE`; SQLite serializes writes through its embedded writer lock and short write transactions. For a real application use one account row **per authenticated user**, audit the monetary ledger and decide a formal isolation strategy. See each codebase for its exact implementation.
