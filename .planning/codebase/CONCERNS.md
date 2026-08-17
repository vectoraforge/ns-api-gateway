# Codebase Concerns

**Analysis Date:** 2026-02-24

## Tech Debt

**JWT Authentication Without Signature Verification:**
- Issue: `app/auth.py` decodes JWT tokens without cryptographic signature verification. The `_decode_jwt_payload()` function only parses the JWT payload using base64 decoding.
- Files: `app/auth.py`
- Impact: Any attacker can forge JWT tokens with arbitrary `user_id` claims. This allows unauthorized access to chat endpoints and data exfiltration/manipulation for other users.
- Fix approach: Implement JWT signature verification using the public key from the auth provider (Auth0, Cognito, etc.). Use `PyJWT` library with proper key management. Consider using FastAPI security schemes with `HTTPBearer` and verified token dependencies.

**Database Session Initialization Check Too Late:**
- Issue: `app/database.py` raises a generic `Exception("session_factory is not initialized")` at runtime if `get_db()` is called before `init_engine()` completes during app startup.
- Files: `app/database.py:16-17`
- Impact: If startup fails or initialization order is wrong, the error message is vague and difficult to debug in production. The exception type is too generic.
- Fix approach: Create a specific `DatabaseNotInitializedError` exception. Consider validating database initialization during application lifespan before yielding.

**Generic Exception in Retry Logic:**
- Issue: `app/services.py:_invoke()` catches all exceptions broadly (`except Exception as e`) but only handles transient errors specially. Non-transient errors are re-raised as `AnalysisError`.
- Files: `app/services.py:193-196`
- Impact: Obscures the original error type from callers. Makes it harder to distinguish between client errors (bad input), server errors (LLM down), and infrastructure errors (DB connection).
- Fix approach: Preserve exception chain more carefully. Consider creating more granular exception types (e.g., `LLMInvocationError`, `LLMRateLimitError`) and handle each appropriately.

**No Input Validation for Cursor Pagination:**
- Issue: `app/chats.py:_decode_cursor()` and `app/routers/prompts.py:list_chat_messages()` only validate cursor format inside a try-except that catches `ValueError`. Malformed cursors raise HTTP 400 with a generic "Invalid cursor" message.
- Files: `app/chats.py:20-23`, `app/routers/prompts.py:76-81`
- Impact: Clients cannot distinguish between a genuinely invalid cursor and a database consistency issue. Error recovery is difficult.
- Fix approach: Explicitly validate cursor format before decoding. Create a `CursorValidationError` with details about what failed.

## Known Bugs

**Assumption: Message Primary Key Constraint**
- Symptoms: The `messages` table uses composite primary key `(id, created_at)` with partition by `created_at`. If two messages are created at the exact same microsecond, they could theoretically collide.
- Files: `migrations/001_create_tables.sql`, `app/models.py:16-27`
- Trigger: Rapid message creation in same millisecond; extremely unlikely in practice but possible with batch operations.
- Workaround: Current schema accepts this risk. In practice, PostgreSQL `BIGSERIAL` increments always and `created_at` server default has sufficient granularity.

**Chat History Load May Return Reverse Order in Edge Cases:**
- Symptoms: `app/chats.py:load_history()` reverses results after fetching in DESC order, but if results are empty or if message order is not guaranteed by database, history could appear out of order.
- Files: `app/chats.py:37-54`
- Trigger: Race condition during message insertion; extremely rare.
- Workaround: Results are reversed correctly for normal cases. Consider adding an order-by-id secondary sort.

## Security Considerations

**Credential Exposure in Database URL:**
- Risk: `app/config.py:DatabaseConfig.url` includes plaintext password in the connection string: `postgresql+asyncpg://{user}:{password.get_secret_value()}@{host}:{port}/{name}`.
- Files: `app/config.py:24-26`
- Current mitigation: Password is a `SecretStr` field and is only materialized when `.get_secret_value()` is called. Pydantic doesn't log or serialize secrets automatically.
- Recommendations:
  - Never log the full URL. If needed, log only `postgresql+asyncpg://{user}@{host}:{port}/{name}`.
  - Consider using environment variables directly or connection pooling services that manage credentials externally (e.g., PgBouncer with `PGPASSFILE`).
  - Review application logs to ensure the URL is never printed.

**No Rate Limiting on Endpoint `/prompts/examples`:**
- Risk: The `GET /prompts/examples` endpoint requires no authentication. An attacker could enumerate all supported languages by polling repeatedly.
- Files: `app/routers/prompts.py:34-40`
- Current mitigation: Examples are static and publicly known; information leak is low-risk. However, abuse could waste bandwidth.
- Recommendations: Add HTTP rate limiting middleware (e.g., `slowapi` or FastAPI built-in rate limit). Consider adding a global rate limit per IP or API key.

**Message Content Stored as Plain Text:**
- Risk: All message content (both human and assistant) is stored unencrypted in PostgreSQL. If database is compromised, all user conversations are exposed.
- Files: `app/models.py:20-22`, `app/chats.py:97-105`
- Current mitigation: Database should be in a private network. Access should be restricted via security groups/firewall.
- Recommendations: Consider encryption-at-rest for sensitive data. If messages contain PII, implement column-level encryption (e.g., using `pgcrypto`). Add a data retention policy to automatically purge old messages.

**No Request Signing or Integrity Checks:**
- Risk: API endpoints accept requests over HTTPS but do not verify request integrity or implement HMAC signing. An attacker with network access (e.g., compromised CDN) could modify request bodies.
- Files: All endpoints in `app/routers/`
- Current mitigation: Requests are validated via Pydantic schemas, which reject unexpected fields. Signature verification is the client's responsibility.
- Recommendations: For high-security scenarios, implement request signing with shared keys or mTLS.

## Performance Bottlenecks

**LLM Concurrency Gate Single-Threaded Token Allocation:**
- Problem: `app/services.py:LLMExecutionGate` uses `asyncio.Queue` with slots managed as Python objects. Under extremely high concurrency (thousands of requests), the asyncio event loop serializes all slot operations.
- Files: `app/services.py:95-122`
- Cause: Queue operations are not truly lock-free. Contention on the internal queue lock can cause slowdown.
- Improvement path: For ultra-high throughput, consider using a semaphore-only design without a separate queue, or delegate concurrency control to an external service (e.g., Redis-based rate limiting).

**Message History Loaded Fully Into Memory:**
- Problem: `app/services.py:analyze()` and `app/services.py:chat()` load entire chat history via `chats.load_history()` and pass it to the LLM. For long chats (max 100 messages), this consumes memory and adds latency.
- Files: `app/services.py:231-232, 245-246`, `app/chats.py:37-54`
- Cause: No pagination or streaming of history. All messages are fetched before invoking the LLM.
- Improvement path:
  - Implement sliding-window history: only load the last N messages instead of all capped messages.
  - Use database cursors or streaming to avoid materializing entire result sets.

**Cursor Encoding/Decoding Uses Base64 Every Request:**
- Problem: Pagination cursors are encoded as base64 strings on every `list_messages()` call and decoded on the next call. This is not a bottleneck for small datasets but is wasteful.
- Files: `app/chats.py:15-23`, `app/routers/prompts.py:76-81`
- Cause: Cursor is treated as an opaque string passed by the client. No server-side cache or optimization.
- Improvement path: Use a more compact cursor format (e.g., JSON with `{"created_at": "...", "id": 123}`) or store cursor state server-side with a short TTL.

**No Database Connection Pooling Tuning:**
- Problem: `app/database.py:11` sets `pool_size` from config but hard-codes `max_overflow=0`. Under peak load, connection requests will be queued instead of creating temporary overflow connections.
- Files: `app/database.py:9-12`, `app/config.py:22`
- Cause: Conservative default to prevent connection leaks. But may cause unnecessary latency during traffic spikes.
- Improvement path: Increase `max_overflow` to allow temporary connections. Monitor connection pool metrics in production. Consider using a connection pooler service (e.g., PgBouncer) external to the app.

## Fragile Areas

**LLM Output Parsing Dependency on JSON Format:**
- Files: `app/services.py:229, 253`, `app/schema.py:18-24`
- Why fragile: The LLM is prompted to return JSON, but the prompt is loaded from a static file (`config/prompt.txt`). If the prompt is changed incorrectly or the LLM model changes behavior, JSON parsing will fail and raise `AnalysisError` with a cryptic message.
- Safe modification:
  - Always test prompt changes with actual LLM calls before deploying.
  - Add logging that captures the raw LLM response before parsing.
  - Implement a fallback or retry with a corrected prompt if parsing fails.
  - Add unit tests that mock the LLM to ensure the output schema is stable.
- Test coverage: `tests/unit/test_services.py` has mocked LLM tests but no real LLM integration tests in CI.

**Chat Ownership Validation Only at Query Time:**
- Files: `app/routers/prompts.py:46-56, 58-92, 95-106`, `app/chats.py:29-35`
- Why fragile: Chat ownership is enforced in `get_chat(db, chat_id, user_id)`, but the ownership check happens after querying. If there's a race condition or bug in the ownership check, users could access other users' chats.
- Safe modification:
  - Add database-level constraints: add a unique index on `(chat_id, user_id)` or a check constraint that ownership is always validated.
  - Add integration tests that verify a user cannot access another user's chat.
  - Consider adding audit logging for all chat access.
- Test coverage: `tests/integration/test_prompts_endpoints.py` has tests for authorized endpoints but limited tests for unauthorized access.

**Circuit Breaker State Not Persisted:**
- Files: `app/services.py:61-93`
- Why fragile: Circuit breaker state is in-memory and not shared across instances. If the app is running in multiple processes or replicas, each instance maintains separate breaker state. A failure in one replica won't trigger the breaker in others.
- Safe modification:
  - For single-instance deployments, this is acceptable.
  - For multi-instance deployments, move circuit breaker state to Redis or another shared cache.
  - Add metrics/observability to detect when the breaker is open in any instance.
- Test coverage: `tests/unit/test_services.py` has unit tests for the `CircuitBreaker` class but no integration tests with real LLM failures.

## Scaling Limits

**Message Table Partition Daily But Retention 30 Days:**
- Current capacity: Partitions created daily, 30-day retention = 30 partitions maximum.
- Limit: Once the table reaches 30 days of data, the oldest daily partition is deleted. This is appropriate for most use cases. However, if retention needs to be extended (e.g., for compliance or analytics), the partition scheme may need tuning.
- Scaling path:
  - Monitor partition size and query performance. If partitions become very large, consider hourly partitioning instead of daily.
  - Consider archiving old partitions to cold storage (e.g., S3) instead of deleting.

**LLM Queue Size Fixed at Startup:**
- Current capacity: `queue_size` from config + `pool_size` determines total inflight slots. Default is 5 (active) + 25 (queue) = 30 total.
- Limit: Queue is sized at startup and cannot be dynamically adjusted. If traffic spikes beyond queue capacity, requests return `503 Service Unavailable`.
- Scaling path:
  - Monitor queue full errors. If frequent, increase `model.queue_size` and redeploy.
  - Implement adaptive queue sizing based on real-time load (requires code change).
  - Use an external queue service (e.g., Celery with Redis) to decouple request handling from LLM execution.

**Database Connection Pool Fixed at Startup:**
- Current capacity: `pool_size` from config, default 5. Total connections = 5 + overflow (currently 0).
- Limit: With 5 concurrent database connections and many requests, database operations will be queued and slow.
- Scaling path:
  - Increase `db.pool_size` in config and redeploy.
  - Use an external connection pooler (PgBouncer).
  - Optimize queries to use fewer database operations.

**Message History Limit Hard-Coded in Config:**
- Current capacity: `history_max_human_messages` and `history_max_assistant_messages`, each default to 50.
- Limit: Chat history is limited to 100 total messages. For long conversations, older context is lost.
- Scaling path:
  - Increase limits in config (trade-off: higher LLM token usage and latency).
  - Implement smart history summarization: summarize old messages before feeding to LLM.
  - Implement vector-based retrieval: store embeddings of messages and retrieve only relevant context.

## Dependencies at Risk

**LangChain Dependency on OpenAI:**
- Risk: Code imports directly from `langchain_openai` and `openai` packages. If OpenAI's API changes or service goes down, the app fails immediately.
- Files: `app/services.py:1-33`, `app/main.py:7`
- Impact: No fallback to alternative LLM providers (e.g., Anthropic, Azure OpenAI). Multi-provider support would require code refactoring.
- Migration plan:
  - Abstract the LLM interface: create a `LLMProvider` interface and implement multiple providers.
  - Add configuration to select the provider at runtime.
  - Implement fallback logic: try primary provider, then fallback provider if primary fails.

**PostgreSQL + asyncpg Direct Dependency:**
- Risk: Application is tightly coupled to PostgreSQL and the `asyncpg` driver. Switching databases would require significant refactoring.
- Files: `app/database.py`, `app/models.py`, `app/chats.py`
- Impact: No flexibility to use other databases (MySQL, CockroachDB, etc.).
- Migration plan:
  - Database choice is typically not changed frequently, so this is a lower priority.
  - If needed, abstract the data layer using SQLAlchemy's database-agnostic ORM features.

**Pydantic v2 Breaking Changes:**
- Risk: `pyproject.toml` specifies `pydantic >=2.12` without an upper bound. Major Pydantic v3 (if released) could break validation logic.
- Files: `app/config.py`, `app/schema.py`, `app/models.py`
- Impact: Dependency upgrades could silently change behavior or break validation.
- Migration plan: Pin major version: `pydantic >=2.12,<3.0`. Add pre-deployment testing with newer versions in CI.

## Test Coverage Gaps

**No Real LLM Integration Tests in CI:**
- What's not tested: End-to-end analysis flow with real LLM is only tested with `@pytest.mark.llm` which is skipped in CI by default (`-m 'not llm'`).
- Files: `tests/llm/test_real_llm.py` (marked as llm-only)
- Risk: Changes to the prompt, LLM schema, or error handling may break real LLM calls undetected. The app may work in local tests but fail in production.
- Priority: High. Real LLM integration tests should run in CI before deployment (or at least in a staging environment).

**No Ownership Validation Tests for Cross-User Access:**
- What's not tested: Tests do not verify that a user cannot access another user's chat or messages.
- Files: `tests/integration/test_prompts_endpoints.py` mocks auth but does not test authorization boundary conditions.
- Risk: A bug in ownership checks could expose user data.
- Priority: High. Add explicit tests for unauthorized access attempts.

**No Load/Stress Tests:**
- What's not tested: Queue full, circuit breaker open, high concurrency scenarios are not tested.
- Files: No load test files found in `tests/`.
- Risk: The app may behave unexpectedly under peak load. Queue and circuit breaker logic may have race conditions.
- Priority: Medium. Add load tests for queue saturation and circuit breaker triggering.

**No Database Partition Edge-Case Tests:**
- What's not tested: Partition rollover (daily boundary), retention policy (30-day deletion).
- Files: `migrations/001_create_tables.sql` is not tested.
- Risk: Partition deletion may fail silently or delete more data than intended.
- Priority: Medium. Add integration tests that verify partition lifecycle.

**No Cursor Pagination Edge-Case Tests:**
- What's not tested: Cursor behavior with empty result sets, out-of-order cursors, malformed cursors.
- Files: `tests/integration/test_prompts_endpoints.py` does not comprehensively test pagination.
- Risk: Pagination may break or leak data under edge conditions.
- Priority: Medium. Add parameterized tests for cursor edge cases.

**Error Handler Coverage Not Measured:**
- What's not tested: All custom exception handlers in `app/errors.py` are not explicitly tested.
- Files: `app/errors.py:20-82` (no dedicated unit tests).
- Risk: Exception handler logic may be broken or missing.
- Priority: Low. Add unit tests for each exception handler.

---

*Concerns audit: 2026-02-24*
