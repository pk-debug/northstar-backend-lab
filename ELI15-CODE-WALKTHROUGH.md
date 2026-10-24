# ELI15: annotated execution of a single simulated BUY across all five languages

You asked for docstrings and explanations "for each line." The source code includes module/class/function comments and inline annotations around important logic; this guide goes deeper **statement by statement** for the hardest paths. A comment after *every punctuation mark* can make source harder to read; instead, comments explain intent, invariants and consequences. Each project has its own 5W2H document too.

## Before any code: the story
The user's phone sends `POST /api/v1/orders` with `{symbol:"AAPL",side:"BUY",quantity:2}` and a unique idempotency key. The server does not trust a price from the phone. It finds $228.87 in its own *sample* catalogue, checks there is $457.74 cash, increases shares, reduces cash, writes history, and commits once.

## 1. Java: `LedgerService.place` (transactional JDBC)
```java
@Transactional  // Spring opens a DB transaction; exceptions roll back all SQL changes.
public Result place(String symbol, String side, long quantity, String key) {
    long cash=db.queryForObject("SELECT cash_cents FROM accounts WHERE id=1 FOR UPDATE",Long.class);
    // SELECT FOR UPDATE locks the account row until COMMIT/ROLLBACK; competing BUYs wait.
    var prior=db.query("SELECT * FROM orders WHERE idempotency_key=?",ORDER_MAPPER,key);
    // ? means the JDBC driver safely binds this untrusted value. Do NOT concatenate SQL.
    // Existing matching key -> return original receipt. Conflicting key -> HTTP 409.
    // Fetch existing holdings; calculate total in integer cents (22887 * 2 = 45774).
    // If buying, compute weighted average; if selling, keep average and decrement quantity.
    // UPDATE cash; INSERT order; then exit method: @Transactional commits.
}
```
**Interview:** What happens if `INSERT order` fails after `UPDATE cash`? The transaction is rolled back. Why not call the controller from another thread? `@Transactional` uses Spring proxy boundaries, and you should understand self-invocation caveats.

## 2. Go: `Server.handlePlaceOrder` (explicit transaction)
```go
tx, err := s.db.BeginTx(ctx, nil) // Reserve one connection and start the transaction.
if err != nil { /* return 500, not "success" */ }
defer tx.Rollback()                 // Safe cleanup if any later step returns early.
// SELECT cash FOR UPDATE on Postgres; SQLite single-connection configuration serializes writes.
// Every tx.ExecContext uses bound ? or $1 placeholders, never raw user text.
if err = tx.Commit(); err != nil { /* return server failure */ }
```
**Interview:** Why `context.Context`? The request can cancel slow database operations. Why `SetMaxOpenConns(1)` for local SQLite? A single in-process writer simplifies transaction isolation in this educational example.

## 3. Kotlin: `Store.place` (JDBC transaction + concise Kotlin)
```kotlin
db.autoCommit = false // JDBC does not commit after each UPDATE.
try {
    val cash = db.select("SELECT cash_cents FROM accounts WHERE id=1 FOR UPDATE") { it.getLong(1) }.single()
    // .single() means this learning system assumes exactly ONE seeded demo account.
    // If order is valid, update holdings, cash and history inside this SAME connection.
    db.commit() // All statements become visible as one unit.
} catch (error: Exception) {
    db.rollback() // If *any* step fails, revert every statement in this transaction.
    throw error  // Let the HTTP error handler decide the final response.
} finally { db.autoCommit = true } // Return a clean connection to Hikari's pool.
```
**Interview:** Are Ktor coroutines enough to make blocking JDBC asynchronous? No. JDBC blocks a thread; consider R2DBC or a dispatcher designed for blocking I/O if throughput requirements justify it.

## 4. Node.js: `db.transaction(async tx => ...)` (async + serialization)
```ts
const result = await db.transaction(async tx => { // Run every state mutation as a unit.
  const [account] = await tx.rows('SELECT cash_cents FROM accounts WHERE id=1 FOR UPDATE');
  // NOTE: the real code adds FOR UPDATE ONLY when PostgreSQL is selected.
  const amount = asset.priceCents * quantity; // Integer cents avoid FP ledger error.
  if (amount > Number(account.cash_cents)) throw new ApiError(409,'Insufficient cash');
  // Update positions, cash, and history inside tx; a throw aborts the transaction.
  return {code:201,body:{ok:true,order}};
});
```
**Interview:** What does `await` do? It yields to the event loop while I/O completes. Why queue SQLite transactions in `db.ts`? JavaScript interleaving between `await`s could otherwise overlap BEGIN/COMMIT on the one SQLite connection. PostgreSQL uses a dedicated pool client per transaction instead.

## 5. Python: `place_order` (Pydantic + SQLAlchemy Core)
```python
with store.engine.connect() as db:       # Acquire pooled DB connection.
    if not store.POSTGRES:
        db.exec_driver_sql("BEGIN IMMEDIATE") # Acquire SQLite write lock before reading.
    else:
        db.begin()                       # Start PostgreSQL transaction.
    try:
        cash = store.account_lock(db)    # SELECT FOR UPDATE on PostgreSQL.
        # Reject invalid quantities BEFORE all of this with Pydantic OrderInput.
        # UPDATE cash, UPDATE/INSERT/DELETE position and INSERT order.
        db.commit()                     # Persist all changes together.
    except Exception:
        db.rollback()                   # Never keep half an order.
        raise                           # Preserve error, including HTTP 409.
```
**Interview:** Why SQLAlchemy Core here instead of ORM? It makes the actual SQL and isolation boundary visible to a backend beginner. ORM is useful in larger models but doesn't remove the need to understand transactions.

## Key mathematical example: average cost
Starting AAPL: 4 shares at $182.45. BUY 2 at $228.87.
- Old invested cost = 4 × 18245 = 72980 cents.
- Added cost = 2 × 22887 = 45774 cents.
- Total = 118754 cents across 6 shares.
- Weighted average ≈ 19792.33 cents/share = $197.92 rounded to two decimals.
- Cash changes from $12,450.00 to $11,992.26.
- When selling 1 share later, remaining 5 shares retain the same average purchase cost; only quantity changes.

## Useful interview follow-ups
1. Difference between `400`, `404`, `409`, and `500`?
2. Why must the server choose the price rather than trust a mobile POST body?
3. What happens if a phone times out after the server commits?
4. What guarantees uniqueness of an idempotency key at database level?
5. Why is PostgreSQL row locking different from a Node.js mutex?
6. What is an N+1 SQL query and how does eager loading help?
7. How do connection pools limit parallel database load?
8. How do you safely migrate a DB schema with no downtime?
9. How would user authentication and authorization change this one-account example?
10. What changes when quote fixtures become real market feed data?
