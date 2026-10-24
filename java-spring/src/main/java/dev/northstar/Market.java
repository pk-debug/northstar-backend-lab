package dev.northstar;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.util.*;

/** Immutable quote catalogue, intentionally illustrative and never live stock data. */
@Component
public class Market {
    private final List<Map<String,Object>> assets;
    private final List<Map<String,Object>> indexes;
    private final Map<String,Map<String,Object>> bySymbol = new HashMap<>();

    /** Load fixture JSON from classpath, which works inside packaged JARs. */
    public Market(ObjectMapper json) throws IOException {
        assets = json.readValue(new ClassPathResource("market-assets.json").getInputStream(), new TypeReference<>() {});
        indexes = json.readValue(new ClassPathResource("market-indexes.json").getInputStream(), new TypeReference<>() {});
        for (var asset : assets) bySymbol.put((String) asset.get("symbol"),asset);
    }
    /** Domain reads use cents; HTTP responses omit the internal cents field. */
    public long priceCents(String symbol) { return ((Number)bySymbol.get(symbol).get("priceCents")).longValue(); }
    /** Whether a ticker exists in the fixture catalogue. */
    public boolean contains(String symbol) { return bySymbol.containsKey(symbol); }
    /** Return a fresh map so client code cannot mutate the master fixtures. */
    public Map<String,Object> asset(String symbol) { var a=new LinkedHashMap<>(bySymbol.get(symbol));a.remove("priceCents");return a; }
    /** Read-only asset search over symbols and names. */
    public List<Map<String,Object>> assets(String q) {
        var query=q.trim().toLowerCase(Locale.ROOT);
        return assets.stream().filter(a -> ((String)a.get("symbol")).toLowerCase(Locale.ROOT).contains(query) || ((String)a.get("companyName")).toLowerCase(Locale.ROOT).contains(query))
            .map(a->asset((String)a.get("symbol"))).toList();
    }
    public List<Map<String,Object>> indexes() { return indexes; }
}
