# Using any of the five backends from your actual React Native app

The real repo contains sync fixture imports; **copying stockApi.ts alone will not migrate your screens**. This folder supplies two providers designed for your exact types at `src/features/market/types.ts`.

1. Copy `stockApi.ts`, `MarketProvider.tsx`, and `BackendTradingProvider.tsx` into the frontend repo's **new** folder `src/features/network/`. Their relative imports (`../market/types`) will now resolve.
2. In `src/app/_layout.tsx`, replace the imported `TradingProvider` with `BackendTradingProvider`, add `MarketProvider`, and nest both providers around your `<Stack />` root: `<MarketProvider><BackendTradingProvider><Stack /></BackendTradingProvider></MarketProvider>`. Preserve the file's other wrappers/options.
3. In `src/app/(tabs)/index.tsx` replace the `MARKET_ASSETS, MARKET_INDEXES` import with `useMarket` from `../../features/network/MarketProvider`; inside the component use `const {assets: MARKET_ASSETS,indexes: MARKET_INDEXES,loading,error}=useMarket();`. Keep its existing search and filter logic, **but add `MARKET_ASSETS` to the `useMemo` dependency list**: change `[search]` to `[search, MARKET_ASSETS]` so a completed fetch recomputes results. Handle `loading`/`error` with a progress view/retry button.
4. In `src/app/(tabs)/portfolio.tsx` replace the `MARKET_ASSETS` import with `useMarket`, and use `const {assets:MARKET_ASSETS}=useMarket();`. Replace the existing `useTrading` import with `../../features/network/BackendTradingProvider`.
5. In `src/app/(tabs)/activity.tsx` replace `findAsset` import with `useMarket`; at the start of the component use `const {findAsset}=useMarket();`. Also replace its `useTrading` import with the network provider.
6. In `src/app/asset/[symbol].tsx`, replace `findAsset` import with `useMarket` and use `const {findAsset}=useMarket();` near the top, BEFORE `const asset=findAsset(routeSymbol??'')`. Replace its `useTrading` import too. **Change `function confirmOrder()` to `async function confirmOrder()` and `const result=placeOrder(...)` to `const result=await placeOrder(...)`**. Add a `submitting` state to disable Confirm during network requests, and use a stable idempotency key for retries. Show a loading state while quotes load (otherwise first navigation can look like a 404).
7. In all screens importing `useTrading`, change their import to `../../features/network/BackendTradingProvider` (adjust path for the screen's depth). The React Native model types stay unchanged.
8. In the frontend project's `.env`, set:
   - Android emulator: `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`
   - iOS simulator / web: `EXPO_PUBLIC_API_URL=http://localhost:8000`
   - Physical phone: `EXPO_PUBLIC_API_URL=http://YOUR_LAPTOP_LAN_IP:8000` (server must bind to 0.0.0.0, same Wi-Fi; firewall permitted)
9. Restart Expo (`npx expo start -c`) after changing `EXPO_PUBLIC_*` values.

Change the port to `3000`, `8080`, `8081`, or `8082` to switch Node, Go, Java, or Kotlin. **This switches to a different account database**; the five backends are alternatives, NOT a five-stage distributed trading system. An insecure `http://` URL is only for local learning; production must use HTTPS.

**Important:** `placeOrder` is now asynchronous. A transient timeout can mean the server committed an order but the response was lost. Do not blindly submit the next request with a new key. Generate and keep a key for the user's order intent, inspect `/api/v1/orders`, and reuse the same key for an explicit retry. For real product code, use persistent request keys, login, authorization, rate limits, and a ledger audit.
