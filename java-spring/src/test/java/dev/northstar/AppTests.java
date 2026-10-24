package dev.northstar;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.*;

/** A Spring context test checks wiring, SQL schema creation, and fixture loading. */
@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:testjava;DB_CLOSE_DELAY=-1"})
class AppTests {
    @Autowired Market market;
    @Autowired LedgerService ledger;
    @Test void seededPortfolioAndMarket() {
        assertEquals(7,market.assets("").size());
        assertEquals(12450.0, (Double)ledger.portfolio().get("cash"));
        assertEquals(0,ledger.orders().size());
    }
}
