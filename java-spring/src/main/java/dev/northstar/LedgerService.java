package dev.northstar;

import jakarta.annotation.PostConstruct;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.time.Instant;
import java.util.*;

/** Service layer: the server, not the app, owns simulated cash and shares.
 * WHAT: persistent ledger; WHY: atomic validated writes; WHO: one demo account;
 * WHEN: every order; WHERE: H2/PostgreSQL; HOW: JDBC + @Transactional;
 * HOW MUCH: entirely local by default.
 */
@Service
public class LedgerService {
    public record Position(String symbol, long quantity, double averageCost) {}
    public record Order(String id,String symbol,String side,long quantity,double price,String createdAt,String status) {}
    public record Result(int status,Map<String,Object> body) {}
    private final JdbcTemplate db;
    private final Market market;
    /** Constructor injection keeps dependencies explicit and testable. */
    public LedgerService(JdbcTemplate db, Market market) { this.db=db;this.market=market; }

    /** Creates tables and inserts the exact starting demo holdings only once. */
    @PostConstruct
    public void initialize() {
        db.execute("CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,cash_cents BIGINT NOT NULL CHECK(cash_cents>=0))");
        db.execute("CREATE TABLE IF NOT EXISTS positions(symbol VARCHAR(16) PRIMARY KEY,quantity INTEGER NOT NULL CHECK(quantity>0),average_cost_cents BIGINT NOT NULL)");
        db.execute("CREATE TABLE IF NOT EXISTS orders(id VARCHAR(64) PRIMARY KEY,idempotency_key VARCHAR(128) UNIQUE NOT NULL,symbol VARCHAR(16) NOT NULL,side VARCHAR(4) NOT NULL,quantity INTEGER NOT NULL,price_cents BIGINT NOT NULL,created_at VARCHAR(40) NOT NULL,status VARCHAR(16) NOT NULL)");
        db.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)");
        if (db.queryForObject("SELECT COUNT(*) FROM accounts",Integer.class)==0) {
            db.update("INSERT INTO accounts(id,cash_cents) VALUES(1,1245000)");
            db.update("INSERT INTO positions VALUES('AAPL',4,18245)");
            db.update("INSERT INTO positions VALUES('MSFT',2,40220)");
            db.update("INSERT INTO positions VALUES('VOO',3,49410)");
        }
    }
    /** Convert a single SQL row into the same JSON property names as React Native. */
    private static final RowMapper<Order> ORDER_MAPPER=(rs,n)-> new Order(rs.getString("id"),rs.getString("symbol"),rs.getString("side"),rs.getLong("quantity"),rs.getLong("price_cents")/100.0,rs.getString("created_at"),rs.getString("status"));

    /** Read-only portfolio snapshot, including derived sample mark-to-market value. */
    public Map<String,Object> portfolio() {
        long cash=db.queryForObject("SELECT cash_cents FROM accounts WHERE id=1",Long.class);
        var positions=db.query("SELECT * FROM positions ORDER BY symbol",(rs,n)->new Position(rs.getString("symbol"),rs.getLong("quantity"),rs.getLong("average_cost_cents")/100.0));
        long value=positions.stream().mapToLong(p->market.priceCents(p.symbol())*p.quantity()).sum();
        return Map.of("cash",cash/100.0,"positions",positions,"positionsValue",value/100.0,"totalValue",(cash+value)/100.0);
    }
    /** List committed orders newest first. */
    public List<Order> orders() { return db.query("SELECT * FROM orders ORDER BY created_at DESC,id DESC",ORDER_MAPPER); }

    /** A transaction locks the account row, rejects invalid trades, and commits ALL updates together. */
    @Transactional
    public Result place(String symbol,String side,long quantity,String key) {
        // Both H2 and PostgreSQL support SELECT FOR UPDATE on this account row.
        long cash=db.queryForObject("SELECT cash_cents FROM accounts WHERE id=1 FOR UPDATE",Long.class);
        var prior=db.query("SELECT * FROM orders WHERE idempotency_key=?",ORDER_MAPPER,key);
        if(!prior.isEmpty()) {
            var previous=prior.get(0);
            if(!previous.symbol().equals(symbol) || !previous.side().equals(side) || previous.quantity()!=quantity)
                throw problem(HttpStatus.CONFLICT,"Idempotency-Key was already used for a different order.");
            return new Result(200,Map.of("ok",true,"order",previous));
        }
        var position=db.query("SELECT * FROM positions WHERE symbol=?",(rs,n)->new long[]{rs.getLong("quantity"),rs.getLong("average_cost_cents")},symbol);
        var previous=position.isEmpty()?null:position.get(0);
        long price=market.priceCents(symbol);
        long amount=price*quantity;
        if(side.equals("BUY")&&amount>cash) throw problem(HttpStatus.CONFLICT,"There is not enough demo cash for this order.");
        if(side.equals("SELL")&&(previous==null||previous[0]<quantity)) throw problem(HttpStatus.CONFLICT,"You do not own enough shares for this demo sale.");
        if(side.equals("BUY")) {
            if(previous!=null) {
                long next=previous[0]+quantity,average=(previous[1]*previous[0]+amount+next/2)/next;
                db.update("UPDATE positions SET quantity=?,average_cost_cents=? WHERE symbol=?",next,average,symbol);
            } else db.update("INSERT INTO positions VALUES(?,?,?)",symbol,quantity,price);
        } else {
            long remaining=previous[0]-quantity;
            if(remaining==0) db.update("DELETE FROM positions WHERE symbol=?",symbol);
            else db.update("UPDATE positions SET quantity=? WHERE symbol=?",remaining,symbol);
        }
        db.update("UPDATE accounts SET cash_cents=? WHERE id=1",side.equals("BUY")?cash-amount:cash+amount);
        var order=new Order(UUID.randomUUID().toString(),symbol,side,quantity,price/100.0,Instant.now().toString(),"SIMULATED");
        db.update("INSERT INTO orders(id,idempotency_key,symbol,side,quantity,price_cents,created_at,status) VALUES(?,?,?,?,?,?,?,?)",order.id(),key,symbol,side,quantity,price,order.createdAt(),order.status());
        return new Result(201,Map.of("ok",true,"order",order));
    }
    /** Uniform business HTTP exception used at both layers. */
    public static ResponseStatusException problem(HttpStatus status,String msg) {return new ResponseStatusException(status,msg);}
}
