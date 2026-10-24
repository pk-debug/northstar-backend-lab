package dev.northstar;

import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;

/** Map JSON to typed application data. Controller never writes SQL directly. */
@RestController
@CrossOrigin(origins={"http://localhost:8081","http://localhost:19006","http://localhost:3000"}) // Local Expo web only.
public class ApiController {
    private final Market market; private final LedgerService ledger;
    public ApiController(Market market,LedgerService ledger){this.market=market;this.ledger=ledger;}
    /** Lightweight test for HTTP server availability. */
    @GetMapping("/health") public Map<String,String> health(){return Map.of("status","ok","service","java-spring");}
    /** Filter sample quotes for the Discover page. */
    @GetMapping("/api/v1/assets") public List<Map<String,Object>> assets(@RequestParam(defaultValue="")String q){return market.assets(q);}
    /** Quote view needs symbol normalization and explicit 404s. */
    @GetMapping("/api/v1/assets/{symbol}") public Map<String,Object> asset(@PathVariable String symbol){
        var name=symbol.toUpperCase(Locale.ROOT);
        if(!market.contains(name)) throw LedgerService.problem(HttpStatus.NOT_FOUND,"That asset is not available in the sample market.");
        return market.asset(name);
    }
    @GetMapping("/api/v1/indexes") public List<Map<String,Object>> indexes(){return market.indexes();}
    @GetMapping("/api/v1/portfolio") public Map<String,Object> portfolio(){return ledger.portfolio();}
    @GetMapping("/api/v1/orders") public List<LedgerService.Order> orders(){return ledger.orders();}

    /** Reject unknown or malformed order body before entering the transaction. */
    @PostMapping("/api/v1/orders") public ResponseEntity<Map<String,Object>> place(@RequestHeader(value="Idempotency-Key",required=false) String key,@RequestBody Map<String,Object> body){
        if (key==null||!key.trim().matches("[A-Za-z0-9._:-]{1,128}")) throw LedgerService.problem(HttpStatus.BAD_REQUEST,"Supply an Idempotency-Key of 1–128 safe characters.");
        if(body.size()!=3 || !(body.get("symbol") instanceof String sym) || !(body.get("side") instanceof String side) || !(body.get("quantity") instanceof Integer count))
            throw LedgerService.problem(HttpStatus.BAD_REQUEST,"Enter a known symbol, BUY/SELL, and a positive whole-share quantity.");
        var symbol=sym.trim().toUpperCase(Locale.ROOT);
        if(!side.equals("BUY")&&!side.equals("SELL")||count<1||count>1000000) throw LedgerService.problem(HttpStatus.BAD_REQUEST,"Enter a positive whole-share quantity and BUY or SELL.");
        if(!market.contains(symbol)) throw LedgerService.problem(HttpStatus.NOT_FOUND,"That asset is not available in the sample market.");
        var result=ledger.place(symbol,side,count,key.trim());
        return ResponseEntity.status(result.status()).body(result.body());
    }
    /** Match the React Native OrderResult error format rather than Spring's default envelope. */
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String,Object>> businessError(ResponseStatusException ex){
        return ResponseEntity.status(ex.getStatusCode()).body(Map.of("ok",false,"message",Objects.requireNonNullElse(ex.getReason(),"Request rejected")));
    }
}
