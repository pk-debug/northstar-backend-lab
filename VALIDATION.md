# Build / test status as of 2026-10-25

- **Python / FastAPI:** `python -m pytest -q` passed 1 integration test. Launched uvicorn locally and executed `contracts/smoke.py`, which passed HTTP market, index, portfolio, buy, idempotent retry, mismatch rejection, and unsupported sell tests.
- **Go:** formatted with `gofmt`, including Go 1.23+ router. **Could not compile or run** in this environment because external Go dependencies were not downloadable (no go.sum yet); run `go mod tidy && go test ./...` with network access.
- **Node:** TypeScript and package scripts created. **Not compiled or executed** here because npm dependency installation was unavailable. Run `npm install && npm run check && npm run dev` locally.
- **Java:** Spring Boot Maven project created. **Not compiled or executed** here because Maven is not available. Run `mvn test` locally.
- **Kotlin:** Ktor Gradle project created. **Not compiled or executed** here because Gradle/dependencies are unavailable. Run `gradle test` locally.
- **Docker Compose:** parsed successfully with Python YAML loader. **Images were not built** because Docker is not installed in the environment.
- **Mobile:** drop-in API client and providers created; the existing GitHub repo has **not been modified** and its frontend has **not yet been built with the replacements**. Follow `mobile-integration/INTEGRATION.md`; the upgrade changes an existing synchronous order API to an asynchronous API.

This is an educational, public-demo-only code package, not a production-grade/regulated trading backend.
