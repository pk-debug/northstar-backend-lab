/** Repository layer. Every route speaks to an abstraction, not a DB-specific driver.
 * WHAT: DB sessions; WHY: portable queries/transactions; WHO: service layer;
 * WHEN: any write; WHERE: local SQLite or PostgreSQL; HOW: prepared queries;
 * HOW MUCH: local DB requires no cloud subscription.
 */
import Database from 'better-sqlite3';
import pg from 'pg';

export type Row = Record<string, unknown>;
export interface Session {
  rows<T = Row>(sql: string, params?: unknown[]): Promise<T[]>;
  exec(sql: string, params?: unknown[]): Promise<void>;
}
export interface Store extends Session {
  transaction<T>(fn: (session: Session) => Promise<T>): Promise<T>;
}

/** Convert portable question-mark parameters to PG $1, $2, ... parameters. */
function pgSql(sql: string): string {
  let index = 0;
  return sql.replace(/\?/g, () => `$${++index}`);
}

/** Build either SQL driver based on DATABASE_URL without touching routes. */
export function createStore(): Store {
  const url = process.env.DATABASE_URL;
  if (url?.startsWith('postgres://') || url?.startsWith('postgresql://')) {
    const pool = new pg.Pool({ connectionString: url });
    return {
      rows: async <T = Row>(sql: string, p: unknown[] = []) => (await pool.query(pgSql(sql), p)).rows as T[],
      exec: async (sql, p=[]) => { await pool.query(pgSql(sql), p); },
      transaction: async fn => {
        const client = await pool.connect();
        try {
          await client.query('BEGIN');
          const session: Session = {
            rows: async <T = Row>(sql: string, p: unknown[] = []) => (await client.query(pgSql(sql),p)).rows as T[],
            exec: async (sql,p=[]) => { await client.query(pgSql(sql),p); }
          };
          const result = await fn(session);
          await client.query('COMMIT');
          return result;
        } catch (err) {
          await client.query('ROLLBACK');
          throw err;
        } finally { client.release(); }
      }
    };
  }

  const sqlite = new Database(process.env.SQLITE_PATH || './northstar.db');
  sqlite.pragma('journal_mode = WAL');
  sqlite.pragma('busy_timeout = 5000');
  // JS promises can yield. Queue writes so no two async transactions overlap.
  let tail: Promise<void> = Promise.resolve();
  const session: Session = {
    rows: async <T = Row>(sql: string, p: unknown[] = []) => sqlite.prepare(sql).all(...p) as T[],
    exec: async (sql, p=[]) => { sqlite.prepare(sql).run(...p); }
  };
  return {
    ...session,
    transaction: async fn => {
      let release!: () => void;
      const next = new Promise<void>(resolve => { release = resolve; });
      const previous = tail;
      tail = next;
      await previous;
      try {
        sqlite.exec('BEGIN IMMEDIATE');
        const result = await fn(session);
        sqlite.exec('COMMIT');
        return result;
      } catch (err) {
        sqlite.exec('ROLLBACK');
        throw err;
      } finally { release(); }
    }
  };
}

/** Create relational invariants and seed the original mock ledger once only. */
export async function initialize(store: Store): Promise<void> {
  await store.exec('CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, cash_cents BIGINT NOT NULL CHECK(cash_cents>=0))');
  await store.exec('CREATE TABLE IF NOT EXISTS positions(symbol VARCHAR(16) PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity>0), average_cost_cents BIGINT NOT NULL)');
  await store.exec('CREATE TABLE IF NOT EXISTS orders(id VARCHAR(64) PRIMARY KEY, idempotency_key VARCHAR(128) UNIQUE NOT NULL, symbol VARCHAR(16) NOT NULL, side VARCHAR(4) NOT NULL, quantity INTEGER NOT NULL, price_cents BIGINT NOT NULL, created_at VARCHAR(40) NOT NULL, status VARCHAR(16) NOT NULL)');
  await store.exec('CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)');
  await store.transaction(async tx => {
    const [{ count }] = await tx.rows<{count:number|string}>('SELECT COUNT(*) AS count FROM accounts');
    if (Number(count) > 0) return;
    await tx.exec('INSERT INTO accounts(id,cash_cents) VALUES(1,1245000)');
    for (const [s,q,a] of [['AAPL',4,18245],['MSFT',2,40220],['VOO',3,49410]] as const)
      await tx.exec('INSERT INTO positions(symbol,quantity,average_cost_cents) VALUES(?,?,?)',[s,q,a]);
  });
}
