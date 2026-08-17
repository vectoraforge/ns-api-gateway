# Retrospective: sn-api-gateway

---

## Milestone: v1.1 — Security & Quality

**Shipped:** 2026-02-27
**Phases:** 4 | **Plans:** 8

### What Was Built

- Typed exception hierarchy covering all API error cases — auth (401), ownership (404), validation (400), LLM failures (502/503), database startup (500)
- Uniform `{status, error}` error response shape registered for all exception types
- `TokenVerifier` protocol with structural subtyping; `get_user_id` resolves verifier from `app.state` at request-time
- `TransientLLMError`/`PermanentLLMError` typed exceptions with `__cause__` chain through `_invoke` retry loop
- Cursor pre-validation at route entry before base64 decode
- Circuit breaker in-memory limitation documented with concrete Redis migration path
- Cross-user chat isolation integration tests against real PostgreSQL (6 tests, selective `db` marker)

### What Worked

- **Phase sequencing**: Exception foundation first (Phase 1) gave Phase 2/3/4 a clean typed exception base to build on — no rework needed
- **Parametrized test pattern**: `_make_raise_route` factory closure in `test_exception_handlers.py` scales cleanly to new exception types — Phase 4 added `PageSizeLimitError` and `InvalidCursorError` to the same CASES list with zero structural changes
- **app.state provider pattern**: Resolved auth verifier at request-time, not import-time — made test fixture swapping trivial and documented the production-readiness path
- **Audit-then-complete workflow**: Running `/gsd:audit-milestone` before `/gsd:complete-milestone` surfaced the Phase 1 VERIFICATION.md historical gap status issue before archival — prevented confusion in the final record
- **Phase 4 insertion**: Adding a thin Phase 4 purely for gap closure after the audit was faster than retrofitting Phase 1 — kept Phase 1's record clean

### What Was Inefficient

- **SUMMARY.md frontmatter omissions**: EXCP-03, CURS-01, CB-01 were missing from their respective `requirements_completed` frontmatter entries — code was correct but the audit had to cross-reference VERIFICATION.md to confirm. Adding requirements to frontmatter as a post-execution checklist step would eliminate this noise.
- **Quick task for Phase 1 gaps**: A quick task was inserted between Phase 1 and Phase 2 to wire `ExpiredTokenError` and `ChatOwnershipError` raise sites. This could have been caught in Phase 1 planning if the success criteria explicitly listed "verify exception is actually raised, not just registered."
- **test_config.py pre-existing failures**: Two YAML config test failures were present before this milestone and remain unresolved. They add noise to every test run. Should be triaged early in next milestone.

### Patterns Established

- `str | None = Header(None)` + explicit None-guard in dependency body — safe pattern for FastAPI optional auth headers
- `dep_client` fixture (separate from `handler_client`) for end-to-end `Depends()` path testing
- `db` pytest marker + `addopts = -m "not db"` in `pytest.ini` — keeps default runs fast, integration tests opt-in
- `engine.sync_engine.dispose()` for module-scoped engine teardown in Python 3.12+

### Key Lessons

- **Define "exception is raised" vs "handler is registered" as separate success criteria** — registration without raise sites passing tests is the most common gap pattern
- **Cross-reference VERIFICATION.md + REQUIREMENTS.md + SUMMARY.md frontmatter** — three sources, three failure modes; the audit script catches mismatches that individual plan summaries miss
- **Real-DB tests are high-value but require docker-compose coordination** — set up integration test infrastructure in the first phase that touches DB, not the last

### Cost Observations

- Model mix: ~90% sonnet, ~10% opus (complex planning), minimal haiku
- Sessions: ~6 sessions across 2 days
- Notable: Phase 4 gap closure was fast (~5 min) because the exception hierarchy was already clean — marginal cost of doing things right in Phase 1

---

## Milestone: v1.2 — Cleanup & Tech Debt

**Shipped:** 2026-02-28
**Phases:** 5 | **Plans:** 5

### What Was Built

- Fixed 4 config bugs and removed dead `get_chat()`/`delete_chat()` methods
- Schema-guaranteed LLM responses via `with_structured_output(strict=True)` — eliminated fragile `JsonOutputParser`
- ruff-enforced PEP8 compliance (E/W/F/I/UP, line-length=120) with dev dependency separation
- `ResiliencePolicy` facade composing circuit breaker, execution gate, retry, and timeout behind `invoke()`
- Simplified `/health/ready` to unconditional 200/up — removed `ReadinessCache` and all backend probes

### What Worked

- **Dependency ordering**: Phase 5 (green test suite) → Phase 6 (parsing) → Phase 7 (formatting) → Phase 8 (refactor) → Phase 9 (cleanup) — each phase had a clean baseline to diff against
- **Net code reduction**: -144 lines net despite adding `ResiliencePolicy` and `ResilienceConfig` — cleanup phases pay for themselves
- **Milestone audit**: Caught two cross-phase regressions (startup crash from `config.pool_size` stale reference, ruff violations from Phase 8) that individual phase verifications missed
- **Atomic task commits**: Every plan had 2 atomic commits — easy to revert or bisect if needed

### What Was Inefficient

- **Cross-phase regressions not caught during execution**: Phase 8 broke Phase 7's ruff compliance and introduced a startup crash. Phase-level verification passed because tests bypass `lifespan()`. The audit caught it, but an automated cross-phase check (e.g., running `ruff check .` after every phase) would have caught it earlier.
- **SUMMARY.md frontmatter `one_liner` field missing**: The `summary-extract` CLI returned null for all 5 summaries because the one_liner field wasn't populated. The accomplishments section existed but wasn't extractable via the CLI.

### Patterns Established

- `_env_prefix='__NONE__'` to isolate nested BaseSettings from environment variable leakage
- `with_structured_output(strict=True, method='json_schema')` for constrained decoding
- Facade pattern for cross-cutting concerns (`ResiliencePolicy.invoke()`)
- Nested Pydantic config: `ModelConfig.resilience` groups related settings
- `__all__` for intentional re-exports in `__init__.py` modules
- Unconditional health endpoint — if lifespan fails, FastAPI never serves

### Key Lessons

1. **Run ruff after every phase that touches code** — formatting regressions from new files are the most common cross-phase issue
2. **Test lifespan startup in at least one integration test** — unit/integration test fixtures that bypass `lifespan()` miss production-critical config wiring bugs
3. **Populate SUMMARY.md `one_liner` field** — CLI-extractable accomplishments make milestone completion faster

### Cost Observations

- Model mix: ~85% sonnet, ~15% opus (planning + audit)
- Sessions: ~4 sessions in 1 day
- Notable: Entire v1.2 milestone (5 phases, 25 files, -144 net LOC) completed in a single day

---

## Milestone: v1.3 — Feature Integration

**Shipped:** 2026-03-03
**Phases:** 4 | **Plans:** 8

### What Was Built

- Real RS256 JWT verification via PyJWKClient JWKS with startup warm-up
- Opaque 5-code error contract with `ErrorResponse` Pydantic model and 422 suppression
- Centralized DI in `app/dependencies.py` — routes use `Depends()` only
- `BaseChatModel` type annotation making services provider-agnostic
- Unified `POST /chats` endpoint; old `/prompts/analyze` and `/chats/{id}/messages` removed
- Router-per-resource pattern (chats.py, examples.py, health.py, root.py)

### What Worked

- **DI centralization**: Moving all dependencies to one file made the router code trivially simple
- **Error contract locking**: Defining exactly 5 status codes + 5 error codes upfront prevented scope creep
- **Test infrastructure on `dependency_overrides`**: Clean fixture pattern carried through v1.4

### What Was Inefficient

- No notable inefficiencies recorded for this milestone

### Key Lessons

- **Lock error contract early** — it becomes the stability anchor for all subsequent work
- **Router-per-resource** scales better than monolithic route files

---

## Milestone: v1.4 — Incremental Improvements

**Shipped:** 2026-03-20
**Phases:** 4 | **Plans:** 15

### What Was Built

- Single-query data access per request handler — ownership checks folded into JOINs
- Full chat model refactoring: new schemas (ChatRequest/FollowupRequest), session-in-init ChatsDB, chain-based DI, separate per-operation endpoints
- Complete E2E test suite with real PostgreSQL + OpenAI + Firebase auth, all 8 endpoints covered
- Data-driven error handling — HTTP metadata on exception classes, single `service_error_handler`
- Dead code removal: `get_chat_owned`, `get_message_counts`, `_ensure_history_capacity`, `ChatOwnershipError`

### What Worked

- **Phase 14 → 15 sequencing**: DB optimization first gave the refactoring a clean query layer to build on
- **E2E test infrastructure** (Phase 16): Real-infra tests caught several integration bugs that unit tests missed (asyncpg connect_args, env var collisions, event-loop mismatches)
- **Quick tasks between phases**: 6 quick tasks during Phase 16/17 fixed real integration issues found during E2E testing — fast, targeted, well-tracked
- **Net code reduction**: -488 lines despite adding E2E tests and new schemas — refactoring pays for itself
- **Data-driven error handler**: Phase 17 was the fastest phase (~2min) because the exception hierarchy was already well-structured from v1.1

### What Was Inefficient

- **Phase 15 plan count explosion**: Started with 5 plans, added 3 more (15-06 through 15-08) for ty type-check fixes — the type errors should have been anticipated in the original planning since the refactoring was comprehensive
- **SUMMARY.md `one_liner` field still not populated**: Same issue as v1.2 — CLI extraction returns null for all summaries, requiring manual reading for milestone completion
- **No milestone audit**: Skipped `/gsd:audit-milestone` for v1.4 — requirements were all checked off but the formal audit step was not run

### Patterns Established

- Session-in-init DB pattern (`ChatsDB.__init__` takes session)
- Separate request schemas per endpoint instead of conditional validation
- `create_chain()` factory with `MessagesPlaceholder("history")` — no `("{input}")` slot
- E2E tests: happy path + structure assertions only; error paths stay in unit tests
- `pytestmark = pytest.mark.e2e` in each test module (not conftest — pytest 9 doesn't propagate)
- `AsyncMock(spec=ChatsDB)` prevents phantom mock attributes
- HTTP metadata as class attributes on exception hierarchy

### Key Lessons

1. **Anticipate type-checker impact for large refactors** — plan a type-fix phase upfront instead of discovering 52 errors post-refactoring
2. **E2E test infrastructure pays compound returns** — found 6+ integration bugs that unit tests structurally cannot catch
3. **Quick tasks are the right tool for mid-milestone fixes** — small, atomic, tracked, and don't derail the phase sequence
4. **Data-driven patterns enable fast future changes** — Phase 17 took 2 minutes because the exception hierarchy was clean

### Cost Observations

- Model mix: ~70% opus, ~30% sonnet (higher opus usage for refactoring complexity)
- Sessions: ~8 sessions across 28 days (intermittent work)
- Notable: Phase 17 (error simplification) was 2 minutes — fastest plan execution in the project's history

---

## Milestone: v1.5 — User Management & Subscriptions

**Shipped:** 2026-03-22
**Phases:** 7 | **Plans:** 15

### What Was Built

- Transaction-based test isolation with SQLAlchemy 2.0 create_savepoint and async httpx client
- Service/database packages with re-export `__init__.py` pattern following routers convention
- structlog with ProcessorFormatter dual-output pipeline, contextvars request correlation, single-line request logging middleware
- Local user management: UserIdentity dataclass, User SQLModel with uuid7 PK, race-safe ON CONFLICT upsert, JIT provisioning via get_current_user dependency
- Apple subscription integration: JWS verification, full lifecycle mapping, idempotent event processing, Firebase custom claim sync
- Quota enforcement: Plan/UsageMonthly models, atomic try_increment, ChatService gating, SubscriptionService usage zero-out on tier change
- Envoy Gateway Helm chart: SecurityPolicy for JWT claim extraction, BackendTrafficPolicy for per-tier local rate limiting, separate HTTPRoutes per auth level
- Merged migrations with FK constraints (users.plan, subscriptions.plan → plans.tier)

### What Worked

- **Foundational phases first**: Phase 18 (test isolation) and Phase 19 (package split) enabled all subsequent phases to add modules cleanly — zero structural rework needed
- **3-day execution**: 7 phases, 15 plans, 29 commits completed in 3 days — the infrastructure built in v1.1-v1.4 (error handling, DI, test patterns) compounded
- **Race-safe patterns throughout**: ON CONFLICT upsert for users, idempotent webhook processing, atomic quota increment — all three were designed upfront, none needed rework
- **Separation of Envoy and backend concerns**: Backend enforces authoritative quota; Envoy provides non-authoritative rate limiting at the edge — clean responsibility split
- **Best-effort Firebase sync**: Catching exceptions and logging warnings instead of blocking webhooks was the right call — Firebase propagation delay is inherent

### What Was Inefficient

- **Phase 24 was unplanned**: Migration FK constraint issue was discovered post-Phase 23 — should have been caught during Phase 22 planning when the second migration was added
- **Blockers listed but not formally resolved**: Apple root CA delivery and Envoy Gateway version concerns were listed as blockers but never formally resolved in planning — they just worked out during execution
- **Error contract expanded without formal review**: 429/rate_limited was added in Phase 23 — the constraint says "no new codes without contract review" but the review was informal

### Patterns Established

- `get_or_create` via INSERT ON CONFLICT DO NOTHING + SELECT (not RETURNING) — guaranteed row return for upsert
- `UserIdentity` frozen dataclass for immutable auth payload extraction
- `try_increment` via INSERT ON CONFLICT + conditional UPDATE FROM joined table — race-safe quota enforcement
- Helm chart HTTPRoute separation by auth level (app/llm/webhooks/health)
- `appAccountToken` from Apple transaction as user UUID lookup key
- structlog `ProcessorFormatter` with shared processor chain for dual console/JSON output
- Package re-export pattern: `__init__.py` with `__all__` for services/ and database/

### Key Lessons

1. **Plan migrations holistically** — adding a second migration file for new tables should trigger review of FK relationships with existing tables
2. **Resolve blockers during planning, not execution** — listing concerns without resolution creates false confidence
3. **Error contract changes need explicit decision records** — even "obvious" additions like 429 should be noted as contract evolution
4. **Foundation investment compounds** — v1.5 was the fastest feature-heavy milestone (3 days) because v1.1-v1.4 built clean infrastructure

### Cost Observations

- Model mix: ~60% opus, ~40% sonnet (high opus for new domain patterns — subscriptions, webhooks, quota)
- Sessions: ~4 sessions across 3 days
- Notable: Average plan execution was 4 minutes; the infrastructure patterns from prior milestones eliminated boilerplate decisions

---

## Milestone: v1.6 — Schema Hardening

**Shipped:** 2026-03-26
**Phases:** 9 | **Plans:** 16

### What Was Built

- Native PG enum types (ChatRole, SubscriptionPlan, SubscriptionProvider, SubscriptionStatus) replacing TEXT columns
- Config-driven quotas via bare `dict[SubscriptionPlan, int]` in YAML — `core.plans` table eliminated
- UsageDB rewritten from raw `text()` SQL to type-safe ORM constructs (pg_insert, SQLAlchemy update, SQLModel select)
- Clean-slate pogo-migrate migration with 4 native PG enum types, 6 tables, no plans table
- `require_quota` FastAPI dependency extracting quota enforcement from ChatService (single-responsibility)
- Pydantic content models aligned with LLM prompt schema: `models/llm.py` for validation, `models/api.py` for API schemas
- `OutOfScopeError` exception for LLM reject responses with `resolved_mode` dispatch
- `Message.content` stored as plain dict with `sa_type=JSONB` — no Pydantic wrapping at persistence layer
- Comprehensive security tests: auth edge cases, Retry-After headers, subscription service gaps
- 15 E2E tests for GET /users/me and error paths (404/400/422/401)
- Full error contract consistency: `quota_exceeded` propagated across handler, tests, k8s config

### What Worked

- **Incremental schema hardening**: Phases 25-28 followed a clean dependency chain (models → services → migration → tests) — zero rework needed between phases
- **Scope expansion via user-driven phases**: Phases 29-33 were all added mid-milestone by user request, each addressing real gaps discovered during development. The roadmap evolution mechanism handled this smoothly.
- **Milestone audit before completion**: The audit caught `rate_limited` → `quota_exceeded` rename residue across 4 files — would have been a production 500 on the HTTP exception handler path. Phase 33 was added specifically to close these gaps.
- **Quick tasks for mid-milestone fixes**: 3 quick tasks (content field fix, message rename revert, OpenAPI descriptions) handled small issues without derailing phase sequencing
- **ORM rewrite (Phase 29)**: Replacing raw SQL with ORM constructs was a single-phase effort because the `try_increment` logic was already well-understood from Phase 26

### What Was Inefficient

- **Post-rename propagation missed**: The `rate_limited` → `quota_exceeded` rename in Phase 31 didn't propagate to `errors.py`, tests, or k8s config — required Phase 33 as a gap closure phase. A cross-file rename checklist would have caught this during Phase 31 execution.
- **Phase 32 had no formal requirement IDs**: The model rewrite phase used "Requirements: TBD" and never assigned REQ-IDs — made traceability weaker for that phase
- **Nyquist validation never achieved**: All 8 original phases show `nyquist_compliant: false` — the validation wave-0 was never completed for any phase. This is a workflow compliance gap, not a code quality gap.
- **ENUM-02 dropped mid-execution**: The decision to let SQLAlchemy auto-infer from StrEnum instead of explicit `sa_type=PG_ENUM(...)` was made during Phase 25 execution (D-05) rather than during planning — caused some confusion in the audit

### Patterns Established

- `dict[SubscriptionPlan, int]` for tier→quota config (no wrapper class needed)
- `monthly_quota: int` parameter on DB methods to decouple from config/plans
- `require_quota` as a `Depends()` dependency — cross-cutting concern extraction pattern
- `models/llm.py` + `models/api.py` separation for LLM vs API schema concerns
- `OutOfScopeError` for reject classification — resolved_mode dispatch in service layer
- Plain dict + JSONB for flexible JSON columns — no Pydantic at persistence layer

### Key Lessons

1. **Cross-file rename propagation needs a checklist** — renaming an error code in one file without updating all consumers is the most common gap pattern; grep for the old name after every rename
2. **Assign requirement IDs upfront, not TBD** — phases without REQ-IDs weaken traceability and make audit/completion harder
3. **Milestone audit is essential** — v1.6 audit caught a potential production 500 from stale `_CODE_MAP` entry that would have survived deployment
4. **ORM purity simplifies reasoning** — replacing raw SQL with ORM constructs in Phase 29 made the subsequent model rewrite (Phase 32) cleaner because there were no raw query strings to update
5. **User-driven scope expansion works well** — 5 of 9 phases were added mid-milestone, all addressing real needs; the roadmap evolution mechanism handles this gracefully

### Cost Observations

- Model mix: ~75% opus, ~25% sonnet (high opus for schema design and model rewriting)
- Sessions: ~6 sessions across 4 days
- Notable: Phase 33 gap closure was 3 minutes — fastest phase in project history, because the audit precisely identified the 4 files to fix

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Days | Net LOC | Key Pattern |
|-----------|--------|-------|------|---------|-------------|
| v1.1 | 4 | 8 | 2 | +? | Exception-first foundation + audit before archival |
| v1.2 | 5 | 5 | 1 | -144 | Cleanup phases with milestone audit catching cross-phase regressions |
| v1.3 | 4 | 8 | 2 | +1,503 | DI centralization + error contract locking |
| v1.4 | 4 | 15 | 28 | -488 | Refactoring + E2E infra + data-driven patterns |
| v1.5 | 7 | 15 | 3 | +2,274 | Foundation investment compounds — fastest feature milestone |
| v1.6 | 9 | 16 | 4 | +? | Schema hardening + user-driven scope expansion + milestone audit saves production |

### Top Lessons (Verified Across Milestones)

1. **Milestone audit before completion is non-negotiable** — v1.1 audit caught SUMMARY frontmatter gaps; v1.2 audit caught a startup crash and ruff regressions. Individual phase verification is insufficient.
2. **Atomic commits per task enable safe bisection** — consistent pattern across all milestones, never caused issues
3. **Cross-phase integration is the primary risk** — both v1.1 and v1.2 had gaps that only surfaced when checking connections between phases
4. **Anticipate type-checker impact for large refactors** — v1.4 Phase 15 needed 3 extra plans for type errors; plan a fix phase upfront
5. **E2E test infrastructure pays compound returns** — v1.4 found 6+ integration bugs that unit tests structurally cannot catch
6. **Data-driven patterns enable fast future changes** — v1.4 Phase 17 took 2 minutes because v1.1's exception hierarchy was clean
7. **Foundation investment compounds** — v1.5 delivered 7 feature phases in 3 days because v1.1-v1.4 built clean infrastructure (DI, error handling, test patterns)
8. **Plan migrations holistically** — v1.5 Phase 24 was unplanned because FK constraints between migration files weren't reviewed upfront
9. **Cross-file rename propagation needs a checklist** — v1.6 rename of `rate_limited` → `quota_exceeded` missed 4 files across errors.py, tests, and k8s config; grep for the old name after every rename
10. **Milestone audit saves production** — v1.6 audit caught a potential production 500 from stale `_CODE_MAP` entry; Phase 33 gap closure took 3 minutes to fix what would have been a deployment incident

