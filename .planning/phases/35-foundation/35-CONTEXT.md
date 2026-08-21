# Phase 35: Foundation - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the shared machinery every later auth phase calls and none rebuilds: the pre-handler auth barrier, the route registry and its startup enumeration assertion, the one error registry, the `audit.auth_events` writer, the challenge store and its claim/consume protocol, and the adapter interfaces — `01-foundation.md §1`–`§4`, `§6`, `§7`.

**Changed by this discussion — three scope moves, all flagged per the SHARED-INVARIANTS conflict rule:**

1. **`§5` (backend rate-limit engine) is removed from the product.** Envoy Gateway owns all request-rate enforcement. No `limits` library, no Redis/Valkey, no `rate_limits` config block, no IP/user request limiting, no `quota_checked_request` entry. The `§7.1` provider-call budget seam survives (see D-05).
2. **`§9` (the Envoy gateway contract, FOUND-09) is deferred to the next milestone.** Nothing gateway-side ships in v2.0.
3. **The phase now ends with a booting application.** ROADMAP.md's "Still not bootable — verification here is unit-level against the machinery in isolation" no longer holds: the model layer is repaired here so the enumeration assertion runs at real startup against the real router.

`§8` (rebinding the pre-existing routes) remains Phase 36 per ROADMAP.md, and is **not** in this phase.

Explicitly NOT in this phase: any `/auth/*` route or handler, `GET /users/me`, the two provider-callback routes, any concrete adapter implementation, prepare/completion endpoint logic, any grant/subscription/identity mutation, and every error class beyond the seven foundation-emitted ones. `01-foundation.md` "Explicitly out of scope" is binding and enumerates these with their owning phase.

**Requirements affected — `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` need an explicit edit before planning:**

- **FOUND-06** — rewrite to the narrow provider-call-budget scope (D-05); the `limits`/moving-window/Redis/canonical-IP language no longer describes anything being built.
- **FOUND-09** — move to the v2.1 backlog.
- **Phase 35 success criterion 5** ("Rate limits load entirely from config with no hard-coded values, and an unresolvable client address shares the single-address ceiling bucket") — void; delete or replace.
- **Phase 36 REBIND-04** ("Every quota-checked chat request passes the named `quota_checked_request` admission entry before any database quota mutation") — void; the named entry no longer exists. REBIND-05's grant resolution, lock order, and lazy rollover are unaffected.
- **ROADMAP.md Phase 35 note** — "Still not bootable" is now false.

</domain>

<decisions>
## Implementation Decisions

### Barrier wiring

- **D-01:** The barrier is **one ASGI middleware**, not a `Depends()` and not a custom `APIRoute` class. Only middleware is genuinely default-on — a router added later cannot forget it — which is what `§1.5` and "no authenticated route may be registered outside the barrier" actually require, rather than a property the enumeration assertion has to police after the fact. Consequences the planner must carry: it matches the request against the router itself to read route metadata before dispatch (`§2.2` metadata must be readable *before* the barrier); it takes its DB session from `app.state.session_factory` rather than `Depends(get_db)`; and it **returns** error-registry responses directly instead of raising, because middleware added via `add_middleware` sits outside Starlette's `ExceptionMiddleware` and `app.add_exception_handler` never sees what it raises. — **Reversibility:** costly — every later phase's routes and tests assume identity context is already attached at handler entry; moving to a dependency or route class changes where rejection happens for all of them.

- **D-02:** Handlers consume the identity context through **typed `Depends()` accessors in `app/dependencies.py`** — `get_linked_identity()`, `get_preauth_identity()`, `get_request_context()` — reading one request-scoped object the middleware stashed on `request.state`. Routes stay `Depends()`-only, matching the v1.3 convention. The accessors **raise** when the barrier did not run, which is exactly `§1.4`'s "fails loudly → `auth_required`, never a `None` a handler could treat as anonymous"; putting that check in one place stops each of the seven later phases from re-implementing it. The request-scoped object carries the identity variant, route metadata record, canonical client IP key, the single captured evaluation time, and the attempt id — `§1.4` requires all four, and later phases must not recompute any of them. — **Reversibility:** costly — this is the seam phases 36–46 import verbatim.

- **D-03:** Middleware stack, outermost in: `RequestLoggingMiddleware` → barrier. There is no admission middleware, because D-04 removed backend rate limiting.

- **D-04:** FastAPI's auto-registered doc routes are **turned off** — `docs_url=None`, `redoc_url=None`, `openapi_url=None`. `§2.3`'s assertion is set-equality on `(method, path)` between registered and declared, and `§2.1` pins the public allowlist to exactly the health and readiness probes, so `/docs`, `/redoc`, `/openapi.json`, and `/docs/oauth2-redirect` would otherwise each be an undeclared registered route. Turning them off keeps the allowlist honest without inventing a fourth disposition, and stops an unauthenticated schema dump being reachable. Re-enabling `/docs` locally would require its own declaration.

### Rate limiting — removed

- **D-05:** **No backend traffic limiting ships, in this phase or any v2.0 phase.** `§5` in full is deleted from the product: no `limits` dependency, no Redis/Valkey, no `parse_many`, no moving-window strategy, no `rate_limits` config block, loader, or validator, no named entries, no canonical-IP key derivation, no unresolved-address ceiling bucket. Envoy Gateway is the sole request-rate enforcement point. This **overrides** `SHARED-INVARIANTS.md` § Rate limits and `01-foundation.md §5`, and is recorded here as the required flag rather than silently resolved. Rationale: a sub-$5/month grammar subscription with no users does not justify a distributed-counter subsystem. — **Reversibility:** costly — reinstating it means the config schema, the storage backend, and named entries across phases 36–46, all of which those phase briefs currently assume exist.

- **D-06:** **The `§7.1` provider-call budget seam survives**, implemented as plain in-process counters rather than `limits` entries: the 3-attempt Firebase `getUser` retry budget, and the check-all-budgets-non-destructively-then-charge-them-together gating helper with its broadest-to-narrowest evaluation order. This is per-request call metering, not traffic limiting — no gateway can express it, and phases 37/40/41/42 import the seam. Exhaustion still maps to internal `firebase_lookup_unavailable` → client `verification_temporarily_unavailable`.

- **D-07:** `rate_limited` (429) **stays in the error registry** regardless. It is the class Envoy's 429 body must name once the gateway contract lands, and `§3.2` pins it as the generic 429 every unspecialized rate-limit rejection carries.

- **D-08:** FOUND-09 / `§9` (the Envoy contract — `Authorization` forwarded unchanged, no injected identity headers, `xff_num_trusted_hops` pinned, the 429 shared-body override, global rate-limit service) is **deferred to the next milestone**. Nothing in `k8s/` is touched by this phase. Known and accepted consequences, to be recorded rather than rediscovered: v2.0 ships with no *new* rate limiting anywhere — only whatever the v1.6 chart already enforces, untouched and unverified against `§9`; Envoy's 429s keep their empty body, which does not satisfy the client error contract; and `xff_num_trusted_hops` stays unpinned, so the client address the backend records in audit `details` is trusted rather than proven. None of this affects foundation's correctness — `§9` is explicit that the backend is the sole authoritative verifier and that no backend correctness depends on the gateway.

### Error registry

- **D-09:** **One module absorbs both.** The registry becomes the single home for every client-visible class in the service — the seven foundation classes (`auth_required`, `preauth_identity_not_allowed`, `account_unavailable`, `challenge_required`, `invalid_request`, `verification_temporarily_unavailable`, `rate_limited`) plus the existing business classes (`quota_exceeded`, `not_found`, `service_unavailable`, the LLM/out-of-scope errors), each keeping its current code and status verbatim so `§8.3`'s "existing non-auth error contracts unchanged" holds. `ErrorResponse` and the single data-driven `service_error_handler` survive, generalized. This reads `§3.1` literally: one module, one response model, one handler set, later phases append. — **Reversibility:** costly — it replaces `exceptions.py` and every `raise` site in the v1.6 codebase.

- **D-10:** The registry lives at **package root** (`nativespeaker.api`, replacing `exceptions.py`), not inside `auth/`. It owns every client-visible class in the service, not just the auth ones; quota and LLM errors importing from an auth package would be misleading, and a future non-auth class needs an obvious home. `app/errors.py` keeps registering the handlers on the app.

- **D-11:** The existing 401 code `"unauthorized"` is **retired** — deleted from the `Literal` set and from `_CODE_MAP`. `auth_required` becomes the only 401 the service emits. Once the barrier owns acceptance nothing else can produce a 401, so keeping both would leave a code no branch reaches, and `§3.1` forbids minting near-duplicates. Tests and `k8s/` references to the old string are updated in this phase. — **Reversibility:** one-way — it changes a published client error code; pre-launch with no clients, which is why it is cheap now and would not be later.

- **D-12:** **`_STATUS_REMAP` is deleted outright.** It was a v1.3 artifact of the five-status-code lock, which v2.0 reverses — and one of its entries is now actively wrong: it maps `409 → 400` while the registry uses 409 for `challenge_required`, so a framework 409 would surface as `invalid_request`. In its place the registry declares a class for every status the service can emit — `validation_error` (422), `not_found` (404), `internal_error` (500), `service_unavailable` (503), and whatever covers 405/415 — and each framework exception maps to exactly one declared class with its own honest status. `§3.1`'s "always a declared class, never a fallback" then holds structurally rather than by table lookup.

- **D-13:** Anti-oracle enforcement is **structural only**. Guaranteed: identical status, body, and copy per class, and both `account_unavailable` branches (`historical_identity`, `blocked_user`) reached through the same code path and the same single identity query, so neither branch does DB or network work the other skips. **Not** implemented: timing normalization, padding, or constant-time delays — document the omission and its rationale rather than leaving it to look like an oversight. A timing oracle distinguishing "retired" from "blocked" on a sub-$5/month subscription buys an attacker nothing worth per-rejection latency.

### Boot state and verification

- **D-14:** **The application boots at the end of this phase.** The model layer is repaired against the v2.0 schema so `nativespeaker.api` imports, the lifespan runs, and the `§2.3` enumeration assertion executes at real startup against the real router — not a fixture-built stand-in. Phase 34 accepted one knowingly-broken commit; this ends it one phase earlier than the roadmap assumed. — **Reversibility:** reversible — it moves work between adjacent phases, nothing published.

- **D-15:** "Boots" means **starts clean; chat paths still broken**. Imports, lifespan, and startup succeed and the assertion runs for real. The chat quota path still reads a grant model Phase 36 wires, so those routes fail at runtime until REBIND-04/05 lands. This holds the roadmap's 35-machinery / 36-rebinding boundary while making the success criteria genuinely testable. Note SQLModel classes import fine even when their columns are gone — the failure only appears when a query runs, which is exactly the gap this decision draws the line through.

- **D-16:** **Delete what later phases replace**, rather than repairing code with a known deletion date: `POST /webhooks/apple` and `routers/webhooks.py`, `services/subscriptions.py`, `database/subscriptions.py`, `database/usage.py` (built on the dropped `core.usage_monthly`), and `GET /users/me` unless it can serve against the new schema unchanged. Phase 43 writes `/webhooks/app-store` from scratch and Phase 39 rewrites `/users/me`. Same pre-launch, disposable-data reasoning that justified Phase 34's destructive migration; it also leaves nothing stale in the route registry for the assertion to reconcile. — **Reversibility:** reversible — the deleted code stays in git history and both replacements are already scoped to their own phases.

- **D-17:** Tests **reuse `tests/unit` and `tests/e2e`**. Phase 34's `tests/schema/` sibling existed because nothing under `tests/e2e/` could run while the app was broken — a constraint D-14 removes. Pure logic (wire-contract parsing, registry validation rules, `details` redaction, error-registry mapping) goes in `tests/unit`; anything needing real PostgreSQL or the running app (the four-outcome identity matrix, challenge claim/consume atomicity, audit row shape, the startup assertion) goes in `tests/e2e` behind the existing marker and its transaction-rollback fixtures. `tests/schema/` is left alone.

- **D-18:** Phase-end bar: **delete dead tests, everything else green.** Tests for deleted surfaces go with them; chat/quota tests whose path Phase 36 owns are removed or narrowed to what still holds. No xfail markers — Phase 36 should start from a known-good baseline, not an unknown number of pre-existing failures.

- **D-19:** The barrier and the audit writer reach the database through the **SQLModel session factory** on `app.state.session_factory` — the same source `get_db` uses. The barrier opens one short session for identity resolution; the audit writer opens its own for standalone-durable rows and takes the caller's session as a parameter for in-consuming-transaction mode. One pool, one ORM, consistent with the v1.6 zero-raw-SQL convention. Rejected: a second raw-asyncpg pool for the hot path — a second DB idiom and a second pool to monitor, for latency that does not matter at this scale.

### HMAC key material

- **D-20:** Key material lives in **`config/config.yaml`**, loaded through the existing `pydantic-settings` split; the existing secrets (`DB_*`, `JWT_*`, `OPENAI_API_KEY`) stay in the gitignored `.env`. Shape is Claude's discretion, expected to be `hmac: {active_version: N, keys: {N: "..."}}`. **Stated consequence, accepted by the user after it was raised:** `config/config.yaml` is tracked in git, so HMAC key material is committed, and rotating a key leaves its predecessor readable in history. Mitigated by the Secret Manager todo below, which is the reason that todo exists. — **Reversibility:** costly — rotating a committed key requires history rewriting or accepting permanent exposure.

- **D-21:** **One shared key** derives both audit `actor_subject_hash` (`§4.3`) and challenge `preauth_subject_hash` (`§6.4`), distinguished only by the pinned domain-separation prefix `"actor-subject:v1:"`, exposed as one shared derivation helper. This holds the spec's explicit "same family and the same key" coupling, and with it the accepted consequence that rotation invalidates outstanding challenges — clients simply prepare a fresh one inside the 300-second TTL. Phase 07's `idp_account_hash` gets its own key under the parallel `"idp-account:v1:"` derivation.

- **D-22:** Startup **fails closed only on the active key** — missing or empty active version aborts boot, since nothing can be written without it. A missing *older* version is a warning: it only means historical audit hashes cannot be recomputed, which no request path needs. Rejected: requiring every version 1..active to be present — keys could then never be retired, the config would grow without bound, and losing an old key would brick the app.

### Module layout

- **D-23:** The seven subsystems go in a **new `src/nativespeaker/api/auth/` subpackage** — barrier, route registry, audit writer, challenge store, adapter interfaces, key derivation — with the existing `auth.py` (`TokenVerifier`, `JWTVerifier`) absorbed into it as the verification module. One stable import root for phases 36–46, and the seam is visibly one thing. `auth.py` becoming `auth/` moves every existing import of `nativespeaker.api.auth`; this phase is already touching those call sites. The error registry is the deliberate exception — it sits at package root per D-10. — **Reversibility:** costly — later phases import these module paths by name.

### Claude's Discretion

- Exact `hmac:` config block shape and its Pydantic model.
- How the barrier middleware resolves the matched route to read metadata before dispatch (Starlette route matching against the scope vs a registry lookup keyed on method + path template).
- Raw ASGI middleware vs `BaseHTTPMiddleware` for the barrier.
- Module and file split inside `auth/`, and the naming of the typed identity-context classes.
- Which class covers 405/415 in the registry.
- Whether the canonical client IP — now needed only as audit `details` context, not as a limiter key — is read from the gateway-resolved address or omitted from the request context entirely. It must never be recomputed from raw forwarded headers either way.
- Whether `GET /users/me` can serve unchanged against the v2.0 schema or is deleted under D-16.
- Test file organization within `tests/unit` and `tests/e2e`.
- Inline commenting depth on the redaction rules and the admission matrix.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Binding specification

- `/home/init/native-speaker/specs/auth-refactor-phases/01-foundation.md` — the phase specification. `§1` barrier (wire contract, JWT rules, admission matrix, typed context, ordering); `§2` route registry and the nine startup-assertion failure conditions; `§3` error mechanism and the exact seven classes; `§4` audit writer (two write modes, row shape, hashing, `details` shape, redaction, the internal result values foundation emits); `§6` challenge store and protocol; `§7` adapter interfaces. **`§5` is deleted per D-05 and `§9` deferred per D-08 — do not implement either.** `§8` is Phase 36. The "Explicitly out of scope" section is binding and names the owning phase for each exclusion.
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — binds every phase and **wins over any conflicting phase brief**. Flag conflicts, never resolve them silently. Its § Rate limits section is overridden by D-05 — that override is the flag. "Global deletions" lists what no phase ever builds.

### Project planning

- `.planning/REQUIREMENTS.md` — FOUND-01 … FOUND-09. **FOUND-06 and FOUND-09 need editing before planning** (see the Phase Boundary section above).
- `.planning/ROADMAP.md` — Phase 35 goal, dependency position, and five success criteria. **Criterion 5 is void and the "Still not bootable" note is now false** per D-05 and D-14.
- `.planning/PROJECT.md` — Key Decisions table and the v2.0 constraints; its "Rate limiting" constraint and the "reversed in v2.0" note on application-level rate limiting are both superseded by D-05.
- `.planning/phases/34-schema/34-CONTEXT.md` — Phase 34's decisions. D-13 (test package isolation) and D-17/D-18 (introspection, exact-set assertions) inform D-17 here; D-08 (the `§9` rulings that override contrary prose) is the precedent for how the three overrides above are recorded.
- `.planning/todos/pending/secret-manager-integration.md` — the Secret Manager follow-up D-20 depends on.

### Current implementation

- `src/nativespeaker/api/auth.py` — `TokenVerifier` protocol, `JWTVerifier` on `PyJWKClient` with startup JWKS warm-up. Close to `§1.2` but has no wire contract, no issuer-selection, and no identity resolution. Absorbed into `auth/` per D-23.
- `src/nativespeaker/api/exceptions.py`, `src/nativespeaker/api/app/errors.py`, `src/nativespeaker/api/models/api.py` — the three-part v1.6 error stack the registry replaces per D-09/D-12: `ServiceError` carrying HTTP metadata on the class, the single data-driven `service_error_handler`, and `ErrorResponse` with its `Literal` code set.
- `src/nativespeaker/api/app/dependencies.py` — the `Depends()`-only convention D-02 extends. `get_db` shows the session-factory pattern D-19 reuses; `get_current_user` and `require_quota` are the JIT-provisioning and quota paths the barrier and Phase 36 replace.
- `src/nativespeaker/api/app/main.py` — app construction, router registration, handler registration, and `RequestLoggingMiddleware`. D-03 and D-04 both land here.
- `src/nativespeaker/api/config.py` — `BaseConfig`/`AppConfig` on `pydantic-settings` with `SecretStr`, the YAML-structure + env-secrets split D-20 keeps.
- `src/nativespeaker/api/logs.py` — `RequestLoggingMiddleware` and the structlog contextvars pipeline; the structured security log and the bounded counter metric build on this.
- `migrations/20260818_01_initial-release.sql` — the applied v2.0 schema. Foundation writes no migration.
- `tests/e2e/conftest.py` — app-lifespan fixtures and `join_transaction_mode=create_savepoint` rollback isolation, usable again once D-14 lands.
- `k8s/` — **not touched this phase** per D-08.

### Stale — do not trust

- `.planning/codebase/*.md` — captured 2026-02-24, before the project rename and the v1.4/v1.5/v1.6 restructuring. `STRUCTURE.md` describes an `app/` layout with `prompts.py` and `schema.py` that no longer exist. Read the source instead.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `JWTVerifier` already does RS256-over-JWKS with a cached client and a fail-fast startup warm-up — `§1.2` needs the wire contract, issuer pinning to the one configured Firebase integration, and `iss`/`aud`/`exp`/`iat`/non-empty-`sub` checks layered on, not a rewrite.
- `service_error_handler` is already the single data-driven handler `§3.1` asks for; it reads HTTP metadata off the exception class. The registry generalizes it rather than replacing the mechanism.
- `app.state` already carries `config`, `session_factory`, `jwt_verifier`, and `llm_service` — the barrier's dependency-free access path, and where the challenge store, audit writer, and budget counters belong.
- `structlog` contextvars binding per request is in place, so the structured security log `§4`/`§8.2` require has a home.
- `firebase-admin>=7.3.0` is already a dependency (used by the v1.5 claim-sync path) — `§7.1`'s interface has a concrete library behind it when phases 37+ implement it.

### Established Patterns

- **`Depends()`-only routes, all DI in `app/dependencies.py`** (v1.3) — D-02 keeps handlers inside it; D-01's middleware is the deliberate exception, and the accessors are the bridge back.
- **HTTP metadata on exception classes, one handler** (v1.4) — the shape the registry inherits.
- **Session-in-init DB classes** — the challenge store and audit writer follow it, with the audit writer additionally accepting a caller session for in-transaction mode.
- **Zero raw `text()` SQL, ORM constructs only** (v1.6) — D-19 holds the line; note `§6.1`'s claim and consume are single atomic conditional `UPDATE`s, expressible as ORM `update().where()` with a rowcount check.
- **Per-test transaction rollback** — D-17 reuses it directly.
- **Native PostgreSQL enum types for domain enums** (v1.6) — the eleven v2.0 enums continue it; `core.auth_operation` and `core.auth_event_result` are referenced by route metadata and the audit writer.

### Integration Points

- `app/main.py` — middleware stack order (D-03), `docs_url=None` (D-04), and the startup assertion hook.
- `app/lifespan.py` — where the enumeration assertion, HMAC key validation (D-22), and challenge-store/audit-writer construction fail closed before serving.
- `app/dependencies.py` — `get_current_user` and `require_quota` are superseded; the identity accessors replace them.
- `models/`, `database/` — repaired against the v2.0 schema (D-14) with the dead subscription and usage layers deleted (D-16).
- Every existing `from nativespeaker.api.auth import ...` and every `raise` of a `ServiceError` subclass moves under D-23 and D-09.

</code_context>

<specifics>
## Specific Ideas

- The `409 → 400` entry in `_STATUS_REMAP` is a live collision with `challenge_required`, not a hypothetical — it is the concrete reason D-12 deletes the table rather than trimming it.
- `§2.3`'s failure direction 2 (declared-but-unregistered) exists because a previous implementation checked only direction 1 and left seven phantom registry entries undetected. The assertion must be set equality with both differences reported separately.
- `§6.1`'s claim is the single serialization point for the whole challenge protocol — one atomic conditional `UPDATE` conditioned on `issued` **and** unexpired, and the only place expiry is ever evaluated. No earlier step checks `expires_at`.
- A claimed challenge is dead: any post-claim failure consumes it, and an abandoned attempt leaves the row `claimed` forever with no cleanup job. Indefinite retention is the design, not an omission.
- Barrier rejections are first-class `audit.auth_events` rows with all three actor fields NULL (CHECK-enforced) and the bounded reason confined to `details`/metric labels — never collapsed into a generic 401 log line.
- The public `challenge_id` is a secret capability handle: never in URLs, audit rows, logs, traces, analytics, or error text. Correlation uses the non-secret `core.auth_challenges.id`.

</specifics>

<deferred>
## Deferred Ideas

- **The Envoy gateway contract (FOUND-09 / `§9`)** — moved to the next milestone per D-08. Carries the `Authorization`-unchanged guarantee, the no-identity-headers rule, `xff_num_trusted_hops` pinning, the 429 shared-body override, and the global rate-limit service. Also the natural home for reworking the v1.6 per-tier chart policies.
- **Backend rate limiting (`§5`)** — removed rather than deferred per D-05, but if real abuse traffic appears, this is the record of what was cut and why.
- **`quota_checked_request` admission (`§8.4`, Phase 36 REBIND-04)** — void with D-05. Phase 36's quota flow keeps its grant resolution, lock order, and lazy rollover; only the admission entry ahead of it disappears.
- **Timing normalization for anti-oracle guarantees** — explicitly not built per D-13; revisit only if the threat model changes.
- **Google Secret Manager for all secrets** — captured at `.planning/todos/pending/secret-manager-integration.md`. Directly relevant to D-20: it is what would take the HMAC key material out of a tracked file.
- **Fully working chat routes in Phase 35** — considered and rejected per D-15; that is Phase 36's REBIND-04/05 verbatim.

</deferred>

---

*Phase: 35-Foundation*
*Context gathered: 2026-08-20*
