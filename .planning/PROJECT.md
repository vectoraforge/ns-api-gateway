# ns-api-gateway

## What This Is

A FastAPI-based linguistic analysis API service that accepts text phrases and returns structured analysis results via an LLM backend (OpenAI). Features user management with JIT provisioning, Apple Store subscription integration (free/silver/gold/platinum tiers), config-driven quota enforcement via FastAPI dependency, native PostgreSQL enum types for all domain enums, Envoy Gateway rate limiting by plan tier, structured logging, real RS256 JWT authentication with JWKS key rotation, an opaque 5-code error contract, LLM content models aligned with the prompt schema, and a complete E2E + security test suite against real infrastructure.

## Core Value

The analysis pipeline must work reliably — correct LLM invocation, proper resilience under load, and safe per-user data isolation.

## Current Milestone: v2.0 Authentication & Entitlements

**Goal:** Replace JIT JWT provisioning with a full backend-verified identity system — a mandatory pre-handler auth barrier, explicit account creation, an access-grant entitlement model, and dual-store subscription ingestion.

**Target features:**
- Rewritten initial migration: identity, tiers, access grants, per-grant monthly usage, store purchase tokens, challenges, `audit.auth_events`
- Shared foundation: pre-handler auth barrier, route registry with startup enumeration assertion, one error registry, audit writer, `limits`-based rate-limit engine, challenge store, adapter interfaces
- `POST /auth/create-user` — the only pre-auth-callable route
- `POST /auth/sync` — read-only auth-state reconciliation
- `GET /users/me` — rewritten profile with registration state and purchase-attribution tokens
- `POST /auth/upgrade-anonymous` — anonymous → registered identity transition
- `POST /auth/claim-anonymous-grant` and `POST /auth/claim-registered-grant` — the only free-grant creators
- `POST /webhooks/app-store` and `POST /webhooks/google-play/rtdn` — the two provider-callback routes
- `POST /auth/restore-subscription` — native store artifact verification
- `POST /auth/sign-out-all` — Firebase refresh-token revocation

**Specification:** `/home/init/native-speaker/specs/auth-refactor-phases/` — one file per phase. `SHARED-INVARIANTS.md` binds every phase and wins over any phase brief on conflict.

## Requirements

### Validated

- ✓ Phrase analysis via `POST /chats` — existing (unified in v1.3)
- ✓ Multi-turn chat sessions with persistent message history — existing
- ✓ Cursor-based pagination for message listing — existing
- ✓ JWT user ownership enforcement on chat endpoints — existing
- ✓ LLM resilience: circuit breaker, concurrency gate, retry with backoff — existing
- ✓ Chat delete endpoint — existing
- ✓ Language-specific examples via `GET /examples` — existing (moved in v1.3)
- ✓ Health readiness probe — existing
- ✓ YAML-based configuration with Pydantic validation — existing
- ✓ Mandatory pre-handler auth barrier: single point of JWT acceptance and identity resolution, admitting only active identities — Validated in Phase 35: Foundation
- ✓ Shared machinery every later phase calls: route registry with startup enumeration assertion, error registry, audit writer, provider-call budget seam, challenge store, adapter interfaces — Validated in Phase 35: Foundation
- ✓ Typed exception hierarchy replacing bare `Exception` in database and service layers — v1.1
- ✓ JWT auth structured for real signature verification (TokenVerifier protocol, pluggable via app.state) — v1.1
- ✓ Retry logic preserves original exception chain with granular error types (TransientLLMError/PermanentLLMError) — v1.1
- ✓ Cross-user access boundary tests (user A cannot access user B's chats, real PostgreSQL) — v1.1
- ✓ Cursor pagination validation before decode (InvalidCursorError at route entry) — v1.1
- ✓ Circuit breaker designed for multi-instance awareness (in-memory limitation documented, Redis path noted) — v1.1
- ✓ Dead code removed (unreachable `get_chat()`/`delete_chat()`) and config bugs fixed — v1.2
- ✗ **Withdrawn — never shipped (corrected in Phase 36, D-13):** LLM responses are parsed as unconstrained JSON by `JsonOutputParser` and validated after the fact by the `models/llm.py` response models. Schema-constrained decoding via `with_structured_output(strict=True)` is not in the source and never was; restoring it is filed as `.planning/todos/pending/restore-strict-structured-output.md` — claimed v1.2
- ✓ PEP8 compliance enforced by ruff (E/W/F/I/UP, line-length=120) — v1.2
- ✓ Resilience concerns extracted into `ResiliencePolicy` facade — v1.2
- ✓ Health endpoint simplified to unconditional 200/up (ReadinessCache removed) — v1.2
- ✓ Real RS256 JWT verification via PyJWKClient JWKS with startup warm-up — v1.3
- ✓ Opaque error contract: 5 status codes, 5 fixed error codes, ErrorResponse in OpenAPI — v1.3
- ✓ Centralized FastAPI DI in `app/dependencies.py` with `Depends()`-only routes — v1.3
- ✓ `BaseChatModel` type annotation on ChatService (provider-agnostic) — v1.3
- ✓ Test infrastructure on `dependency_overrides` with `service_instance` fixture — v1.3
- ✓ Unified `POST /chats` endpoint; old `/prompts/analyze` and `/chats/{id}/messages` removed — v1.3
- ✓ `alternatives` → `suggestions` field rename in response schema — v1.3
- ✓ Error handling simplified: HTTP metadata on exception classes, single data-driven handler — v1.4
- ✓ Single-query data access per request handler (ownership folded into JOINs) — v1.4
- ✓ Dead code removed (`get_chat_owned`, `get_message_counts`, `_ensure_history_capacity`, `ChatOwnershipError`) — v1.4
- ✓ Chat model refactored: separate schemas, session-in-init DB, chain-based DI, per-operation endpoints — v1.4
- ✓ E2E test suite: real PostgreSQL + OpenAI + Firebase auth, all endpoints covered, cross-user isolation — v1.4
- ✓ Transaction-based test isolation with auto-rollback (no manual cleanup) — v1.5
- ✓ Service/database packages with re-export pattern (services/, database/) — v1.5
- ✓ Structured logging via structlog with dual-output pipeline and request correlation — v1.5
- ✓ JIT user provisioning from JWT with race-safe ON CONFLICT upsert — v1.5
- ✓ `GET /users/me` returns profile with email, name, plan tier, and usage data — v1.5
- ✓ Apple Store subscription lifecycle processing via POST /webhooks/apple — v1.5
- ✓ JWS signature verification for Apple notifications — v1.5
- ✓ Idempotent webhook processing (notificationUUID dedup) — v1.5
- ✓ Plan tier storage (free/silver/gold/platinum) as authoritative source — v1.5
- ✓ Firebase custom claim sync for JWT propagation (async, best-effort) — v1.5
- ✓ Atomic quota enforcement via INSERT ON CONFLICT + conditional UPDATE — v1.5
- ✓ Envoy Gateway rate limiting by plan tier (SecurityPolicy + BackendTrafficPolicy) — v1.5
- ✓ Helm chart with separate HTTPRoutes per auth level — v1.5
- ✓ Project renamed from sn-api-gateway to ns-api-gateway — v1.5
- ✓ Single merged migration with FK constraints (users.plan, subscriptions.plan → plans.tier) — v1.5
- ✓ Config-driven quotas replacing `core.plans` table; native PG enum types for all StrEnums — v1.6
- ✓ All database layer uses ORM constructs (zero raw `text()` SQL) — v1.6
- ✓ Comprehensive E2E and security test coverage (auth edge cases, Retry-After headers, subscription paths) — v1.6
- ✓ Quota enforcement centralized in `require_quota` FastAPI dependency (ChatService single-responsibility) — v1.6
- ✓ Pydantic content models aligned with LLM prompt schema; `models/llm.py` for validation, `models/api.py` for API schemas — v1.6
- ✓ `Message.content` stored as plain `dict` with `sa_type=JSONB` (no Pydantic model wrapping at persistence layer) — v1.6
- ✓ `OutOfScopeError` exception for LLM reject responses with `resolved_mode` dispatch — v1.6
- ✓ Error contract fully consistent: `quota_exceeded` propagated across handler, tests, and k8s config — v1.6

### Active

Scoped in `.planning/REQUIREMENTS.md` for v2.0. Summary:

- [ ] Single rewritten initial migration delivering the full auth schema (no incremental migrations)
- [ ] Mandatory default-on pre-handler auth barrier — the only place identity resolution happens
- [ ] Route registry with three closed categories and a startup/CI enumeration assertion
- [ ] One shared error registry owning every client-visible response shape
- [ ] `audit.auth_events` writer — exactly one durable row per on-path attempt
- [ ] Challenge store with claim/consume protocol for challenge-bearing operations
- [ ] Explicit account creation replacing JIT provisioning (`POST /auth/create-user`)
- [ ] Access-grant entitlement model — exactly one active grant per user, four enumerated sources
- [ ] Anonymous and registered free-grant claim flows with supersession
- [ ] Dual-store subscription ingestion (App Store notifications + Google Play RTDN)
- [ ] Store-artifact subscription restore and Firebase refresh-token revocation

### Out of Scope

- LangChain/OpenAI provider abstraction — no multi-provider requirement yet
- Message content encryption-at-rest — defer to infrastructure layer
- Load/stress tests — not a current priority
- Application-level rate limiting — ~~Envoy Gateway owns rate limiting~~ ~~**reversed in v2.0**: backend limiting uses the `limits` library~~ — **re-settled by Phase 35 D-05**: the backend rate-limit engine (`§5`) is **deleted from the product**, not deferred. No `limits` dependency, no Redis/Valkey, no `rate_limits` config block (REQUIREMENTS.md:42, FOUND-06). Envoy is the sole request-rate enforcement point *in principle* — but `§9`'s gateway contract is deferred to v2.1 (D-08), and Phase 37.2 confirmed no HTTPRoute matches `/auth` at all, so **no rate limit of any kind applies to the auth surface this milestone**. Knowingly accepted — see `37.2-SECURITY.md` AR-01
- CORS middleware / security headers — Envoy Gateway handles at infrastructure level
- Trusted host validation — Envoy Gateway perimeter control
- Redis-backed circuit breaker — single-instance deployment; migration path documented in code
- CI linting gate — ruff enforced locally; CI gate can be added later
- Token creation endpoint — this service is not an identity provider
- Per-request Firebase claim reads — adds 100-300ms latency; JWT already carries the plan claim
- ~~New HTTP status codes or error codes — contract locked at 5 codes (400/401/404/429/500)~~ — **reversed in v2.0**: the auth error registry is materially larger. The locked-contract principle survives in stricter form — one shared registry module owns every client-visible shape, and within an error class the body, status, and copy are identical across every triggering branch (anti-oracle)
- Multi-provider identity support — exactly one configured Firebase integration; still holds in v2.0. The `core.identity_provider` values and the second store webhook are Firebase sign-in providers and payment stores, not additional IdPs
- Payment refund processing — Apple handles refunds; app reacts to revocation notifications
- ~~User registration endpoint — JIT provisioning from JWT; Firebase handles account creation~~ — **reversed in v2.0**: JIT provisioning cannot establish the `(issuer, subject)` → `core.users` linkage the barrier requires. `POST /auth/create-user` is now the only pre-auth-callable route and the sole creator of identity rows
- Admin user management — own profile only (`GET /users/me`); no admin listing or management

Added in v2.0 (from `SHARED-INVARIANTS.md` "Global deletions" — build none of these, in any phase):

- Backend-minted tokens or sessions — authentication is per-request via the Firebase ID token only; no cookie, no secondary auth state, no generation counter
- `checkRevoked` / per-request revocation checks — already-minted ID tokens are never force-expired
- `promo` grant source — deleted from the enum and from every rule that referenced it
- Scheduled cleanup, purge, reconciliation, recovery-scan, or background-healer jobs of any kind — indefinite retention
- Device-fingerprint or device-check components in any rate-limit key
- Claim-header authentication or header-derived identity — the gateway forwards `Authorization` unchanged and injects no identity headers
- Distributed locks, leases, or multi-phase-commit machinery
- Wildcard or path-prefix membership for the provider-callback route category — callback routes are named individually by exact path
- Identity row deletion — rows are tombstones; retirement is permanent and irreversible
- Data migration, backfill, compatibility shims, dual-write windows, or deprecated aliases — pre-launch DB with disposable data

## Current State

Shipped v1.6. All milestones through v1.6 complete. v2.0 (Authentication & Entitlements) in progress — Phase 34 (schema) and Phase 35 (foundation) complete. Phase 35 delivered the shared auth machinery and the app now boots with the route enumeration assertion running for real; chat and quota routes still fail at runtime until Phase 36 rewires them (D-14/D-15).

## Context

Tech stack: Python 3.12, FastAPI, LangChain, SQLAlchemy async, Pydantic v2, PyJWT, structlog, orjson, ruff. Infrastructure: Envoy Gateway (rate limiting, JWT extraction), Kubernetes via Helm chart, PostgreSQL with native enum types.

Endpoints:
- `POST /chats` — new analysis (context + question + lang)
- `POST /chats/{id}` — followup (message)
- `GET /chats` — list user's chats
- `GET /chats/{id}` — chat detail with messages
- `DELETE /chats/{id}` — delete chat
- `GET /users/me` — user profile + plan tier + usage
- `POST /webhooks/apple` — Apple subscription notifications
- `GET /examples` — language-specific examples
- `GET /health/ready` — health probe
- `GET /` — API root

v2.0 adds: Firebase Admin SDK (issuer-selected client, no ambient default), the `limits` library with Redis/Valkey for backend rate limiting, Google Play RTDN ingestion via Cloud Pub/Sub push, and `audit.auth_events` as a first-class audit surface.

v2.0 endpoint changes: `POST /webhooks/apple` → `POST /webhooks/app-store`; `GET /users/me` rewritten; nine new `/auth/*` routes. The analysis routes (`POST /chats`, `GET /chats`, etc.) are rebound onto the barrier in phase 35 but keep their behavior.

Known areas for future work:
- Proactive quota warnings via `X-RateLimit-Remaining` header
- Grace period transparency in `GET /users/me` — `core.subscriptions.status` models `grace_period`, but `04-users-me.md` does not surface it in the response
- Webhook retry reconciliation via App Store Server API polling
- Startup exhaustiveness check for quota config (QUOTA-06)
- `REVOKE DELETE ON core.external_identities` for the application and cleanup roles — the migration only records the requirement in a comment because this repo defines no database role, so it becomes actionable when role provisioning lands in the Kubernetes deployment

## Constraints

- **Tech stack**: Python 3.12, FastAPI, LangChain, SQLAlchemy async — no stack changes
- **Auth**: PyJWT with Firebase JWKS — TokenVerifier protocol remains pluggable
- **Error contract**: Exactly 5 status codes (400/401/404/429/500), 5 opaque error codes — no new codes without contract review
- **Rate limiting**: backend `limits` engine owns identity/user-keyed limits (v2.0); Envoy Gateway limiting is defense-in-depth. Every limit value lives in config; security-sensitive entries default fail-closed
- **Spec authority**: `/home/init/native-speaker/specs/auth-refactor-phases/` is the binding specification for v2.0. `SHARED-INVARIANTS.md` overrides any conflicting phase brief — flag conflicts, never resolve them silently
- **Migrations**: pre-launch DB with no data. One initial migration file, replaced by a renamed file with the superseded one deleted — never add incremental migrations during v2.0

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|--------:|
| JWT structure without a real provider | Need the skeleton in place even if verification is stubbed | ✓ Good — TokenVerifier protocol implemented, easy to swap |
| Cross-user access tests against real DB | Only way to catch ownership bugs before production | ✓ Good — 6 integration tests passing |
| Defer LangChain abstraction | No multi-provider requirement; premature | — Pending |
| `app.state.verifier` resolved at request-time | Enables zero-code swapping of auth providers in tests and startup | ✓ Good |
| Typed LLM errors with `__cause__` | Callers can distinguish transient vs permanent without inspecting internals | ✓ Good |
| CORS, rate limiting, security headers → Envoy Gateway | Avoids redundant app-level middleware | ◐ Mixed — CORS and headers hold. **Rate limiting does not**: Phase 37.2 found no HTTPRoute matches `/auth`, so no `BackendTrafficPolicy` reaches it, and Phase 35 D-05 removed the in-process engine. The auth surface is unlimited this milestone (`37.2-SECURITY.md` AR-01) |
| `with_structured_output(strict=True, method='json_schema')` | Constrained decoding would eliminate fragile parsing — but the decision was never implemented. `services/llm.py` has always been `prompt_template \| self.llm \| JsonOutputParser()`, and `git log -S'with_structured_output' -- src/` returns nothing. That gap is what made D-35-11-A reachable: an already-correct phrase returned 500 because the model omitted two keys nothing forced it to emit. Corrected in Phase 36 per D-13 | ✓ **Implemented in Phase 37.2** (plan 03) — `services/llm.py:31` binds `with_structured_output(ChatModelResponse, method="json_schema", strict=True)`, with a provider-free schema assertion and a real-provider e2e gate. Flat root model by construction: a union root would ship looking strict while leaving every branch unconstrained |
| ResiliencePolicy composes existing CB/gate without modifying them | Facade pattern; composition over modification | ✓ Good |
| Health endpoint unconditional 200/up | If lifespan fails, FastAPI never serves — probing backends is redundant | ✓ Good |
| PyJWT 2.11.0 over python-jose | python-jose is abandoned; PyJWT is actively maintained | ✓ Good |
| JWTVerifier uses PyJWKClient with JWKS warm-up | Production-grade key rotation with fail-fast startup | ✓ Good |
| ErrorResponse with Pydantic Literal codes | Typos cause ValidationError at construction, not runtime 500 | ✓ Good |
| HTTP metadata on exception classes | Single handler reads class attrs; eliminates 12 boilerplate handlers | ✓ Good |
| All dependencies in app/dependencies.py | Single import source; routes never touch Request | ✓ Good |
| BaseChatModel annotation on ChatService | Provider-agnostic; no vendor lock-in in service layer | ✓ Good |
| Unified POST /chats with optional chat_id | Single entry point for all chat operations; cleaner API surface | ✓ Good |
| Session-in-init DB pattern (ChatsDB) | Clean lifecycle; session scoped to instance | ✓ Good |
| JIT user provisioning via `get_or_create` with ON CONFLICT | Race-safe; no separate registration step | ✓ Good |
| `UserIdentity` frozen dataclass from `TokenVerifier` | Immutable auth data; clean separation from DB model | ✓ Good |
| `UserProfileResponse` omits `id`, `jwt_sub`, `active` | Security: internal fields not exposed to client | ✓ Good |
| Atomic `try_increment` via INSERT ON CONFLICT + conditional UPDATE | Race-safe quota enforcement without app-level locks | ✓ Good |
| Envoy Gateway local rate limiting (no Redis) | Matches single-cluster deployment; PostgreSQL is authoritative quota | ✓ Good |
| Separate HTTPRoutes for app/llm/webhooks/health | Per-route policy attachment; webhooks exempt from rate limiting | ✓ Good |
| Firebase claim sync is best-effort | Exceptions caught and logged as warning; webhook still returns 200 | ✓ Good |
| structlog with ProcessorFormatter dual-output pipeline | Console for dev, JSON for prod; contextvars for request correlation | ✓ Good |
| 429 not remapped by _STATUS_REMAP | QuotaExceededError flows through as native 429 | ✓ Good |
| Bare `dict[SubscriptionPlan, int]` for quotas over QuotaConfig wrapper | Simpler config model; no extra abstraction needed | ✓ Good — v1.6 |
| `UsageDB.try_increment` accepts `monthly_quota: int` parameter | Decouples DB layer from plans table entirely | ✓ Good — v1.6 |
| Plain dict for `Message.content` with `sa_type=JSONB` | No Pydantic model wrapping at persistence layer; flexible schema | ✓ Good — v1.6 |
| LLM validation models in `models/llm.py`, API schemas in `models/api.py` | Separate concerns; LLM contract vs API contract | ✓ Good — v1.6 |
| `require_quota` FastAPI dependency for quota enforcement | ChatService single-responsibility; quota is cross-cutting concern | ✓ Good — v1.6 |
| `OutOfScopeError` for LLM reject responses | Clean error contract for out-of-scope input; dispatches on `resolved_mode` | ✓ Good — v1.6 |
| Deliver the v2.0 schema as `20260818_01_initial-release.sql`, deleting the superseded `20260322` file, instead of the six-migration sequence in `00-schema.md §1`/`§2` | Pre-launch DB with no data; teardown-then-rebuild SQL is pure waste. Overrides the phase brief — recorded per SHARED-INVARIANTS conflict rule. The rename also matters for correctness: the filename stem is pogo's tracked migration id, so rewriting the old file under its own id is silently skipped on any database that already applied it, whereas a new id fails loudly | — Pending — v2.0 |
| Schema (34) and foundation (35) stay separate phases | Foundation is already the heaviest phase (8 subsystems); the two have genuinely different acceptance gates — "migration applies, constraints exist" vs "app starts, route assertion passes". Accepts one knowingly-broken intermediate commit | — Pending — v2.0 |
| Phase numbering continues at 34–45 rather than resetting to 1 | Avoids colliding with the 33 phases already in MILESTONES.md; spec-file number maps to GSD phase by a fixed +34 offset | — Pending — v2.0 |
| Roadmap built from spec metadata; each phase reads its own spec file at plan time | The spec dir is ~90k tokens — too large for one context, and unnecessary: the roadmapper needs dependency edges, not SQL DDL | — Pending — v2.0 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-25 after completing Phase 37.2*
