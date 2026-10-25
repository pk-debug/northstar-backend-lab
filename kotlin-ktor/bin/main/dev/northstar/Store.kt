package dev.northstar

import com.zaxxer.hikari.HikariConfig
import com.zaxxer.hikari.HikariDataSource
import java.sql.Connection
import java.sql.ResultSet
import java.time.Instant
import java.util.UUID

/** A position is measured in whole shares with average cost from integer cents. */
data class Position(val symbol: String,val quantity: Long,val averageCost: Double)
/** The mobile app expects status = SIMULATED and camelCase createdAt. */
data class Order(val id: String,val symbol: String,val side: String,val quantity: Long,val price: Double,val createdAt: String,val status: String)
/** Returns the correct HTTP status with an error message when business rules fail. */
class ApiException(val code: Int, override val message: String): RuntimeException(message)

/** JDBC helper: never paste untrusted input directly into SQL strings. */
private fun Connection.exec(sql: String,vararg args: Any) = prepareStatement(sql).use { statement ->
    args.forEachIndexed { index, value -> statement.setObject(index + 1,value) }
    statement.executeUpdate()
}
/** JDBC mapper: close statements and result sets on every successful or failed call. */
private fun <T> Connection.select(sql: String,vararg args: Any,mapper:(ResultSet)->T):List<T> = prepareStatement(sql).use { statement ->
    args.forEachIndexed { index,value -> statement.setObject(index + 1,value) }
    statement.executeQuery().use { rs -> buildList { while (rs.next()) add(mapper(rs)) } }
}
private fun ResultSet.order(): Order = Order(getString("id"),getString("symbol"),getString("side"),getLong("quantity"),getLong("price_cents")/100.0,getString("created_at"),getString("status"))

/** 5W2H: WHAT JDBC ledger; WHY atomic trades; WHO single demo account;
 * WHEN orders; WHERE H2/PostgreSQL; HOW pooled JDBC transactions;
 * HOW MUCH no cloud cost for local H2 or local Docker.
 */
class Store(private val market:Market): AutoCloseable {
    private val config = HikariConfig().apply {
        jdbcUrl = System.getenv("DATABASE_URL") ?: "jdbc:h2:file:./northstar;DB_CLOSE_ON_EXIT=FALSE"
        username = System.getenv("DB_USER") ?: "sa"
        password = System.getenv("DB_PASSWORD") ?: ""
        maximumPoolSize = 8
        poolName = "northstar-kotlin"
    }
    private val pool = HikariDataSource(config)
    init { initialize() }
    override fun close() = pool.close()

    /** Start new projects with a seed; reboots never overwrite previous orders. */
    private fun initialize() = pool.connection.use { db ->
        db.createStatement().use { s ->
            s.execute("CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,cash_cents BIGINT NOT NULL CHECK(cash_cents>=0))")
            s.execute("CREATE TABLE IF NOT EXISTS positions(symbol VARCHAR(16) PRIMARY KEY,quantity INTEGER NOT NULL CHECK(quantity>0),average_cost_cents BIGINT NOT NULL)")
            s.execute("CREATE TABLE IF NOT EXISTS orders(id VARCHAR(64) PRIMARY KEY,idempotency_key VARCHAR(128) UNIQUE NOT NULL,symbol VARCHAR(16) NOT NULL,side VARCHAR(4) NOT NULL,quantity INTEGER NOT NULL,price_cents BIGINT NOT NULL,created_at VARCHAR(40) NOT NULL,status VARCHAR(16) NOT NULL)")
            s.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)")
        }
        if(db.select("SELECT COUNT(*) FROM accounts") { it.getInt(1) }.single()==0) {
            db.exec("INSERT INTO accounts(id,cash_cents) VALUES(1,1245000)")
            db.exec("INSERT INTO positions VALUES('AAPL',4,18245)")
            db.exec("INSERT INTO positions VALUES('MSFT',2,40220)")
            db.exec("INSERT INTO positions VALUES('VOO',3,49410)")
        }
    }
    /** Return server-owned cash, holdings, and market value based on sample quotes. */
    fun portfolio(): Map<String,Any> = pool.connection.use { db ->
        val cash=db.select("SELECT cash_cents FROM accounts WHERE id=1") { it.getLong(1) }.single()
        val positions=db.select("SELECT * FROM positions ORDER BY symbol") { Position(it.getString("symbol"),it.getLong("quantity"),it.getLong("average_cost_cents")/100.0) }
        val value=positions.sumOf { (market.bySymbol[it.symbol]?.priceCents ?: 0L) * it.quantity }
        mapOf("cash" to cash/100.0,"positions" to positions,"positionsValue" to value/100.0,"totalValue" to (cash+value)/100.0)
    }
    /** Return committed simulated orders, newest first. */
    fun orders():List<Order> = pool.connection.use { it.select("SELECT * FROM orders ORDER BY created_at DESC,id DESC") { row -> row.order() } }

    /** Execute a BUY/SELL all-or-nothing, using row locks for concurrent orders. */
    fun place(symbol:String,side:String,quantity:Long,key:String):Pair<Int,Order> = pool.connection.use { db ->
        db.autoCommit=false
        try {
            // H2 and PostgreSQL support SELECT FOR UPDATE. It serializes writes to the account.
            val cash=db.select("SELECT cash_cents FROM accounts WHERE id=1 FOR UPDATE") { it.getLong(1) }.single()
            val prior=db.select("SELECT * FROM orders WHERE idempotency_key=?",key) { it.order() }.firstOrNull()
            if(prior!=null) {
                if(prior.symbol!=symbol||prior.side!=side||prior.quantity!=quantity) throw ApiException(409,"Idempotency-Key was already used for a different order.")
                db.commit()
                return@use 200 to prior
            }
            val position=db.select("SELECT quantity,average_cost_cents FROM positions WHERE symbol=?",symbol) { it.getLong(1) to it.getLong(2) }.firstOrNull()
            val price=requireNotNull(market.bySymbol[symbol]).priceCents
            val amount=price*quantity
            if(side=="BUY" && amount>cash) throw ApiException(409,"There is not enough demo cash for this order.")
            if(side=="SELL"&&(position==null||position.first<quantity)) throw ApiException(409,"You do not own enough shares for this demo sale.")
            if(side=="BUY") {
                if(position!=null) {
                    val next=position.first+quantity
                    val avg=(position.second*position.first+amount+next/2)/next
                    db.exec("UPDATE positions SET quantity=?,average_cost_cents=? WHERE symbol=?",next,avg,symbol)
                } else db.exec("INSERT INTO positions(symbol,quantity,average_cost_cents) VALUES(?,?,?)",symbol,quantity,price)
            } else {
                val remaining=requireNotNull(position).first-quantity
                if(remaining==0L) db.exec("DELETE FROM positions WHERE symbol=?",symbol)
                else db.exec("UPDATE positions SET quantity=? WHERE symbol=?",remaining,symbol)
            }
            db.exec("UPDATE accounts SET cash_cents=? WHERE id=1",if(side=="BUY") cash-amount else cash+amount)
            val order=Order(UUID.randomUUID().toString(),symbol,side,quantity,price/100.0,Instant.now().toString(),"SIMULATED")
            db.exec("INSERT INTO orders(id,idempotency_key,symbol,side,quantity,price_cents,created_at,status) VALUES(?,?,?,?,?,?,?,?)",order.id,key,symbol,side,quantity,price,order.createdAt,order.status)
            db.commit()
            201 to order
        } catch(error:Exception) { db.rollback();throw error }
        finally {db.autoCommit=true}
    }
}
