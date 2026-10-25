package dev.northstar

import com.fasterxml.jackson.databind.ObjectMapper
import io.ktor.http.*
import io.ktor.serialization.jackson.*
import io.ktor.server.application.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.plugins.statuspages.*
import io.ktor.server.plugins.cors.routing.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import java.util.Locale

/** Starts a Ktor embedded server on a separately configurable port. */
fun main() {
    val port = System.getenv("PORT")?.toIntOrNull() ?: 8082
    embeddedServer(Netty,port=port) { northstarModule() }.start(wait=true)
}
/** HTTP boundary. The DTO contract is intentionally identical across all languages. */
fun Application.northstarModule() {
    val market=Market()
    val store=Store(market)
    val json=ObjectMapper()
    environment.monitor.subscribe(ApplicationStopped) { store.close() }
    install(ContentNegotiation) { jackson() }
    // Expo web during local development. Never deploy publicly with broad CORS.
    install(CORS) { allowHost("localhost:8081",schemes=listOf("http"));allowHost("localhost:19006",schemes=listOf("http"));allowHost("localhost:3000",schemes=listOf("http"));allowMethod(HttpMethod.Post);allowMethod(HttpMethod.Get);allowHeader(HttpHeaders.ContentType);allowHeader("Idempotency-Key") }
    install(StatusPages) {
        exception<ApiException> { call,e -> call.respond(HttpStatusCode.fromValue(e.code),mapOf("ok" to false,"message" to e.message)) }
        exception<Throwable> { call, _ -> call.respond(HttpStatusCode.InternalServerError,mapOf("ok" to false,"message" to "Internal server error")) }
    }
    routing {
        get("/health") { call.respond(mapOf("status" to "ok","service" to "kotlin-ktor")) }
        get("/api/v1/assets") { call.respond(market.find(call.request.queryParameters["q"] ?: "")) }
        get("/api/v1/assets/{symbol}") {
            val symbol=call.parameters["symbol"].orEmpty().uppercase(Locale.ROOT)
            val asset=market.bySymbol[symbol] ?: throw ApiException(404,"That asset is not available in the sample market.")
            call.respond(asset.toDto())
        }
        get("/api/v1/indexes") { call.respond(market.indexes) }
        get("/api/v1/portfolio") { call.respond(store.portfolio()) }
        get("/api/v1/orders") { call.respond(store.orders()) }
        post("/api/v1/orders") {
            val key=call.request.header("Idempotency-Key")?.trim()
            if(key==null||!Regex("[A-Za-z0-9._:-]{1,128}").matches(key)) throw ApiException(400,"Supply an Idempotency-Key of 1–128 safe characters.")
            // Read a strict JSON object; do not silently convert 1.5 into one share.
            val request=try {json.readTree(call.receiveText())} catch (_:Exception) {throw ApiException(400,"Invalid order JSON")}
            if(!request.isObject||request.size()!=3) throw ApiException(400,"Enter a known symbol, BUY/SELL, and a positive whole-share quantity.")
            val symbolNode=request.get("symbol")
            val sideNode=request.get("side")
            val countNode=request.get("quantity")
            if(symbolNode==null||!symbolNode.isTextual||sideNode==null||!sideNode.isTextual||countNode==null||!countNode.isIntegralNumber)
                throw ApiException(400,"Enter a known symbol, BUY/SELL, and a positive whole-share quantity.")
            val symbol=symbolNode.asText().trim().uppercase(Locale.ROOT)
            val side=sideNode.asText()
            val quantity=countNode.asLong()
            if(symbol.isEmpty()||symbol.length>16||quantity<1||quantity>1000000||(side!="BUY"&&side!="SELL")) throw ApiException(400,"Enter a positive whole-share quantity and BUY or SELL.")
            if(!market.bySymbol.containsKey(symbol)) throw ApiException(404,"That asset is not available in the sample market.")
            val (status,order)=store.place(symbol,side,quantity,key)
            call.respond(HttpStatusCode.fromValue(status),mapOf("ok" to true,"order" to order))
        }
    }
}
