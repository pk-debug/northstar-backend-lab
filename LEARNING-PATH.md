# Backend engineering roadmap (5W2H applied across all projects)

## Week 1: architecture and HTTP
**WHAT** Learn request, URL, verb, JSON DTO, status codes, CORS, port, environment variable, API version and OpenAPI. **WHY** The phone should depend on a stable contract rather than the backend language. **WHO** A mobile frontend and simulated-account server. **WHEN** On a request. **WHERE** App → network → API handler. **HOW** Trace `/api/v1/assets` and add a new optional category filter. **HOW MUCH** Free locally.

## Week 2: SQL and portfolio
Trace a whole request from `GET /api/v1/portfolio` to SQL. Learn primary key, indexes, decimal vs float, cents, normalization, `EXPLAIN`, and connection pools. Draw account ↔ positions ↔ orders. Add an index for descending order history and compare execution plans.

## Week 3: transactions and concurrency
Follow `POST /api/v1/orders`: validation → row lock → replay check → balance check → holding change → cash change → order audit → commit. Test exact-cash buy, insufficient-cash buy, sell to zero, two concurrent buys, repeated idempotency key, and restart durability. **Interview question:** Why is "check then update" without a lock unsafe?

## Week 4: five implementations
Compare Spring's dependency injection and `@Transactional`, Ktor's routes and JDBC, Go's explicit `err` returns, Node's async promise queue, Python's SQLAlchemy and Pydantic. Keep the API unchanged and test each service with `contracts/smoke.py`.

## Week 5: backend quality
Add true integration tests with temporary PostgreSQL (Testcontainers or Docker), database migrations (Flyway/Alembic/Goose/Drizzle), structured logs with request IDs, HTTP response errors, input fuzzing, and CI matrix. Validate invalid JSON, concurrency, and database restart.

## Week 6+: production concepts (not implemented by the lab)
Authentication & authorization (OIDC/JWT), distinct user accounts, encrypted secrets, per-account ledger audit, immutable financial journals, market-data vendors, quote timestamp/staleness, distributed locks or transactional queues, schema migrations, SLOs, tracing, rate-limiting, Redis read cache, Redis invalidation, backups/restore, CI/CD, and threat modeling. A stock broker integration adds extensive regulatory duties.

## Answers you should be able to explain
- **Why cents?** Float cannot represent many decimal fractions exactly; cents give exact integer storage for fixed two-decimal sample USD prices.
- **Why transactions?** Without atomicity cash may update while shares or history fail.
- **Why lock?** Two requests can read the same initial balance and overspend (lost update / write skew).
- **Why idempotency?** HTTP retries after timeouts must not create duplicate simulated orders.
- **Why relational DB?** An order joins an account, a position and a journal with constraints.
- **When MongoDB?** Independent flexible documents or denormalized views, not a substitute for carefully managed ledgers.
- **When Redis?** Repeatable read-only responses like quote fixtures with TTL; not authoritative cash balance.
- **What is missing?** User auth and tenant isolation, real feeds, financial compliance, production migrations and ops.
