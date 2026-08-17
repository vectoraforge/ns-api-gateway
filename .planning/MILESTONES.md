# Milestones

## v1.6 Schema Hardening (Shipped: 2026-03-26)

**Phases completed:** 9 phases, 16 plans, 33 tasks

**Key accomplishments:**

- Renamed enums (Role->ChatRole, Tier->SubscriptionPlan), narrowed model fields to StrEnum types, deleted Plan model, added config-driven QuotaConfig with exhaustiveness validator
- Propagated Role->ChatRole and Tier->SubscriptionPlan renames through all 6 consumer files (services, database, dependencies, router)
- Removed QuotaConfig wrapper in favor of bare dict[SubscriptionPlan, int], flattened YAML quotas, and rewrote UsageDB.try_increment to accept monthly_quota parameter eliminating plans table dependency
- Threaded config-driven quotas through ChatService via DI, changed create_chat/send_message to accept User objects, and replaced get_monthly_limit DB call with config.quotas lookup in /users/me
- Clean-slate pogo-migrate migration with 4 native PG enum types, 6 tables, no plans table, and no SQL-level defaults
- Removed ensure_tables E2E fixture and fixed FirebaseService patch paths for 134/134 green unit suite
- Rewrote UsageDB from raw text() SQL to type-safe ORM constructs using pg_insert, SQLAlchemy update(), and SQLModel select()
- Fixed Issue import path in test_models.py and test_services.py, added 7 missing @pytest.mark.asyncio decorators to subscription test class methods
- 15 E2E tests covering GET /users/me profile response and all error paths (404/400/422/401) with opaque error code verification
- Added auth edge case tests, Retry-After header verification, and subscription service gap tests
- Extracted quota enforcement from ChatService into require_quota FastAPI dependency wired on POST chat routes
- Rewrote quota tests to target require_quota dependency directly with 9 tests passing, ChatService fixtures stripped of quota logic
- OutOfScopeError exception, 6 LLM validation models in models/llm.py, API schemas moved to models/api.py with field renames, Message.content as plain dict with JSONB
- ChatService rewritten with orjson serialization, LLM resolved_mode dispatch, OutOfScopeError reject handling; all 5 consumer files rewired from schema to models.api with field renames
- Full unit test suite (163 tests) rewritten to validate dict-based content, LLM model contracts, and reject/out-of-scope flow
- Propagated rate_limited -> quota_exceeded rename across error handler, k8s config, and test files; fixed stale content -> message field in test payload

---

## v1.5 User Management & Subscriptions (Shipped: 2026-03-23)

**Phases completed:** 7 phases, 15 plans, 31 tasks

**Key accomplishments:**

- Per-test transaction rollback via SQLAlchemy 2.0 create_savepoint, async httpx client replacing sync TestClient, all cleanup_chat/try-finally blocks eliminated
- Split app/service.py and app/database.py into proper Python packages with re-export __init__.py files following the routers pattern
- structlog with ProcessorFormatter pipeline providing dual-output (console + optional JSON file), request correlation via contextvars, and single-line request logging middleware
- UserIdentity dataclass, PlanTier enum, User SQLModel with uuid7 PK, race-safe UsersDB upsert via pg_insert ON CONFLICT, and UserService wrapper
- get_current_user dependency with JIT provisioning replacing get_user_id, UUID user_id throughout, and GET /users/me profile endpoint
- Unit tests covering UserIdentity, User model, profile endpoint, inactive user rejection, and user isolation with updated conftest and e2e helpers
- Subscription/SubscriptionEvent SQLModel tables with partial unique index, SubscriptionDB with idempotent event insertion, AppleConfig with product-to-tier mapping
- SubscriptionService with Apple JWS verification and lifecycle mapping, FirebaseService with async claim sync, POST /webhooks/apple endpoint wired via DI
- 21 unit tests covering webhook endpoint validation (SUBS-01/02), lifecycle mapping (SUBS-03), idempotency (SUBS-04), plan tier update (SUBS-05), and Firebase sync (SUBS-06/07)
- Plan/UsageMonthly models, UsageDB with atomic quota enforcement, 429/rate_limited error contract, project rename to ns-api-gateway v1.5.0
- ChatService quota-gated before LLM calls, SubscriptionService usage zero-out on tier change, GET /users/me returns usage data with 22 new/updated unit tests
- Helm chart with Envoy Gateway SecurityPolicy for JWT plan claim extraction and BackendTrafficPolicy for per-tier local rate limiting on POST /chats only
- Root endpoint updated from SpeakNative/sn-api-gateway to NativeSpeaker/ns-api-gateway with package metadata re-registration
- Merged two SQL migrations into single file with FK constraints on users.plan and subscriptions.plan referencing plans(tier), plus matching SQLModel foreign_key declarations
- Database schema dropped and recreated from merged migration with FK constraints and plans seed data

---

## v1.4 Incremental Improvements (Shipped: 2026-03-20)

**Delivered:** DB query optimization, full chat model refactoring, E2E test suite, and error handling simplification — net 488-line reduction.

**Phases completed:** 14-17 (4 phases, 15 plans)
**Net change:** +1,865 / -2,353 lines (net -488) across 51 files
**Timeline:** 28 days (2026-02-19 → 2026-03-19), 47 commits
**Git range:** `feat(14-01)` → `v1.4.0`
**Requirements:** 33/33 satisfied

**Key accomplishments:**

- Single-query data access per request handler — ownership checks folded into JOINs, eliminating separate ownership queries
- Full chat model refactoring — new schemas (ChatRequest/FollowupRequest), session-in-init DB pattern, chain-based DI, separate endpoints per operation
- Complete E2E test suite with real PostgreSQL + OpenAI + Firebase auth covering all 8 endpoints, cross-user isolation, and full lifecycle flows
- Data-driven error handling — HTTP metadata on exception classes, 12 per-exception handlers replaced with single `service_error_handler`
- Dead code removal: `get_chat_owned`, `get_message_counts`, `_ensure_history_capacity`, `ChatOwnershipError` all eliminated

**What's next:** TBD — next milestone planning

---

## v1.3 Feature Integration (Shipped: 2026-03-03)

**Phases completed:** 4 phases, 8 plans, 16 tasks
**Net change:** +2,016 / -513 lines across 40 files
**Timeline:** 2 days (2026-03-02 → 2026-03-03), 36 min execution time
**Git range:** `feat(10-01)` → `feat(13-02)` (16 commits)
**Requirements:** 21/21 satisfied

**Key accomplishments:**

- Real RS256 JWT verification via PyJWKClient JWKS with startup warm-up, replacing the stub UnsafeBase64Verifier; 19 security tests covering algorithm rejection, signature verification, and claim validation
- Opaque error contract locked to 5 status codes (400/401/404/503/500) with `ErrorResponse` Pydantic model, `_STATUS_REMAP` for non-contract codes, and 422 stripped from OpenAPI schema
- All FastAPI dependencies centralized in `app/dependencies.py` with `Depends()`-only route signatures; `BaseChatModel` type annotation makes services provider-agnostic
- Test infrastructure migrated to `dependency_overrides` with `service_instance` fixture for clean DI-based mocking
- Unified `POST /chats` endpoint handling both new analysis and chat continuation; old routes removed; `alternatives` renamed to `suggestions`
- Router-per-resource pattern established (chats.py, examples.py, health.py, root.py)

**Known tech debt:** 4 items (documentation/test hygiene only — see v1.3-MILESTONE-AUDIT.md)

---

## v1.1 Security & Quality (Shipped: 2026-02-27)

**Phases completed:** 4 phases, 8 plans, 2 tasks

**Key accomplishments:**

- Typed exception hierarchy (`AuthError`, `ChatOwnershipError`, `DatabaseNotInitializedError`, `InvalidCursorError`, `PageSizeLimitError`, `TransientLLMError`, `PermanentLLMError`) replacing all bare `HTTPException` and `Exception` raises
- Uniform `{status, error}` error response shape for all API error cases, enforced by registered exception handlers
- `TokenVerifier` protocol (structural subtyping) + `UnsafeBase64Verifier` dev stub; `get_user_id` resolves verifier from `app.state` for zero-code auth provider swaps
- Typed LLM exception chain: `TransientLLMError`/`PermanentLLMError` with `__cause__` preserved through `_invoke` retry loop
- Cross-user chat isolation verified end-to-end against real PostgreSQL — GET, POST, DELETE ownership tests with `db` pytest marker
- Circuit breaker in-memory limitation documented with concrete Redis migration path (INCR/SET EX, Lua script)

---

## v1.2 Cleanup & Tech Debt (Shipped: 2026-02-28)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Key accomplishments:**

- Fixed 4 config bugs in MainConfig construction (`_env_prefix` isolation, `return self` validator, StrEnum dict, nested model) and removed dead `get_chat()`/`delete_chat()` methods
- Replaced fragile `JsonOutputParser` with `with_structured_output(AnalyzeResponseLLM)` for schema-guaranteed LLM responses at token-generation level
- Added ruff config (E/W/F/I/UP, line-length=120) achieving zero-violation PEP8 compliance; moved ruff/ty to dev dependencies
- Extracted retries, circuit breaker, and concurrency gating into `ResiliencePolicy` facade — `AnalysisService._invoke()` reduced to one-liner delegation
- Simplified health endpoint to unconditional 200/up by removing `ReadinessCache` and all backend probes

**Net change:** +332 / -476 lines (net reduction of 144 lines across 25 files)

---
