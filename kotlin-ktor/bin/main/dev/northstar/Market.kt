package dev.northstar

import com.fasterxml.jackson.core.type.TypeReference
import com.fasterxml.jackson.databind.ObjectMapper

/** Market records mirror the mobile TypeScript type but store exact cents internally. */
data class Asset(val symbol: String, val companyName: String, val exchange: String, val price: Double,
                 val change: Double, val changePercent: Double, val history: List<Int>, val category: String,
                 val priceCents: Long) {
    /** Internal integer-cents value is removed from JSON by using a separate DTO. */
    fun toDto(): Map<String, Any> = mapOf("symbol" to symbol,"companyName" to companyName,"exchange" to exchange,
        "price" to price,"change" to change,"changePercent" to changePercent,"history" to history,"category" to category)
}

/** Loads the *same fixtures* as Java, Go, Python, and Node backends. */
class Market(private val json: ObjectMapper = ObjectMapper()) {
    val assets: List<Asset> = json.readValue(resource("market-assets.json"),object: TypeReference<List<Asset>>() {})
    val bySymbol = assets.associateBy { it.symbol }
    val indexes: List<Map<String, Any>> = json.readValue(resource("market-indexes.json"),object: TypeReference<List<Map<String,Any>>>() {})
    private fun resource(filename: String) = requireNotNull(javaClass.classLoader.getResourceAsStream(filename)) { "Missing fixture $filename" }
    /** Search ticker and company with case-insensitive substring matching. */
    fun find(q: String): List<Map<String, Any>> = assets.filter { it.symbol.contains(q.trim(),true) || it.companyName.contains(q.trim(),true) }.map { it.toDto() }
}
