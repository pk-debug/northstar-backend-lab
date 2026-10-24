package dev.northstar
import kotlin.test.Test
import kotlin.test.assertEquals

/** Verify fixture parity before integrating real HTTP networking. */
class MarketTest {
    @Test fun marketFixture() {
        val market=Market()
        assertEquals(7,market.assets.size)
        assertEquals("AAPL",market.find("apple").single()["symbol"])
        assertEquals(22887L,market.bySymbol["AAPL"]!!.priceCents)
    }
}
