# Phase 35: Foundation — Research

**Researched:** 2026-08-20
**Domain:** ASGI middleware, FastAPI/Starlette route introspection, pydantic-settings config layering, SQLModel atomic conditional updates, HMAC key management
**Confidence:** HIGH — every load-bearing claim was executed against this repository's own `.venv` (FastAPI 0.135.1 / Starlette 0.52.1 / SQLModel 0.0.37) and, for the challenge protocol, against the live database with the v2.0 migration applied.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Barrier wiring**

- **D-01:** The barrier is **one ASGI middleware**, not a `Depends()` and not a custom `APIRoute` class. Only middleware is genuinely default-on — a router added later cannot forget it — which is what `§1.5` and "no authenticated route may be registered outside the barrier" actually require, rather than a property the enumeration assertion has to police after the fact. Consequences the planner must carry: it matches the request against the router itself to read route metadata before dispatch (`§2.2` metadata must be readable *before* the barrier); it takes its DB session from `app.state.session_factory` rather than `Depends(get_db)`; and it **returns** error-registry responses directly instead of raising, because middleware added via `add_middleware` sits outside Starlette's `ExceptionMiddleware` and `app.add_exception_handler` never sees what it raises. — **Reversibility:** costly.
- **D-02:** Handlers consume the identity context through **typed `Depends()` accessors in `app/dependencies.py`** — `get_linked_identity()`, `get_preauth_identity()`, `get_request_context()` — reading one request-scoped object the middleware stashed on `request.state`. Routes stay `Depends()`-only, matching the v1.3 convention. The accessors **raise** when the barrier did not run, which is exactly `§1.4`'s "fails loudly → `auth_required`, never a `None` a handler could treat as anonymous". The request-scoped object carries the identity variant, route metadata record, canonical client IP key, the single captured evaluation time, and the attempt id. — **Reversibility:** costly.
- **D-03:** Middleware stack, outermost in: `RequestLoggingMiddleware` → barrier. There is no admission middleware, because D-04 removed backend rate limiting.
- **D-04:** FastAPI's auto-registered doc routes are **turned off** — `docs_url=None`, `redoc_url=None`, `openapi_url=None`. Turning them off keeps the allowlist honest without inventing a fourth disposition, and stops an unauthenticated schema dump being reachable.

**Rate limiting — removed**

- **D-05:** **No backend traffic limiting ships, in this phase or any v2.0 phase.** `§5` in full is deleted from the product. Envoy Gateway is the sole request-rate enforcement point. This **overrides** `SHARED-INVARIANTS.md` § Rate limits and `01-foundation.md §5`. — **Reversibility:** costly.
- **D-06:** **The `§7.1` provider-call budget seam survives**, implemented as plain in-process counters: the 3-attempt Firebase `getUser` retry budget, and the check-all-budgets-non-destructively-then-charge-them-together gating helper with its broadest-to-narrowest evaluation order. Exhaustion maps to internal `firebase_lookup_unavailable` → client `verification_temporarily_unavailable`.
- **D-07:** `rate_limited` (429) **stays in the error registry** regardless.
- **D-08:** FOUND-09 / `§9` (the Envoy contract) is **deferred to the next milestone**. Nothing in `k8s/` is touched by this phase.

**Error registry**

- **D-09:** **One module absorbs both.** The registry becomes the single home for every client-visible class in the service — the seven foundation classes plus the existing business classes, each keeping its current code and status verbatim. `ErrorResponse` and the single data-driven `service_error_handler` survive, generalized. — **Reversibility:** costly.
- **D-10:** The registry lives at **package root** (`nativespeaker.api`, replacing `exceptions.py`), not inside `auth/`. `app/errors.py` keeps registering the handlers on the app.
- **D-11:** The existing 401 code `"unauthorized"` is **retired** — deleted from the `Literal` set and from `_CODE_MAP`. `auth_required` becomes the only 401 the service emits. Tests and `k8s/` references to the old string are updated in this phase. — **Reversibility:** one-way.
- **D-12:** **`_STATUS_REMAP` is deleted outright.** In its place the registry declares a class for every status the service can emit — `validation_error` (422), `not_found` (404), `internal_error` (500), `service_unavailable` (503), and whatever covers 405/415 — and each framework exception maps to exactly one declared class with its own honest status.
- **D-13:** Anti-oracle enforcement is **structural only**. Guaranteed: identical status, body, and copy per class, and both `account_unavailable` branches reached through the same code path and the same single identity query. **Not** implemented: timing normalization, padding, or constant-time delays — document the omission and its rationale.

**Boot state and verification**

- **D-14:** **The application boots at the end of this phase.** The model layer is repaired against the v2.0 schema so `nativespeaker.api` imports, the lifespan runs, and the `§2.3` enumeration assertion executes at real startup against the real router. — **Reversibility:** reversible.
- **D-15:** "Boots" means **starts clean; chat paths still broken**. The chat quota path still reads a grant model Phase 36 wires, so those routes fail at runtime until REBIND-04/05 lands. SQLModel classes import fine even when their columns are gone — the failure only appears when a query runs.
- **D-16:** **Delete what later phases replace:** `POST /webhooks/apple` and `routers/webhooks.py`, `services/subscriptions.py`, `database/subscriptions.py`, `database/usage.py`, and `GET /users/me` unless it can serve against the new schema unchanged. — **Reversibility:** reversible.
- **D-17:** Tests **reuse `tests/unit` and `tests/e2e`**. Pure logic goes in `tests/unit`; anything needing real PostgreSQL or the running app goes in `tests/e2e` behind the existing marker and its transaction-rollback fixtures. `tests/schema/` is left alone.
- **D-18:** Phase-end bar: **delete dead tests, everything else green.** No xfail markers.
- **D-19:** The barrier and the audit writer reach the database through the **SQLModel session factory** on `app.state.session_factory`. The barrier opens one short session for identity resolution; the audit writer opens its own for standalone-durable rows and takes the caller's session as a parameter for in-consuming-transaction mode. Rejected: a second raw-asyncpg pool.

**HMAC key material**

- **D-20:** Key material lives in **`config/config.yaml`**, loaded through the existing `pydantic-settings` split; the existing secrets stay in the gitignored `.env`. Shape is Claude's discretion, expected to be `hmac: {active_version: N, keys: {N: "..."}}`. **Accepted consequence:** HMAC key material is committed to git. — **Reversibility:** costly.
- **D-21:** **One shared key** derives both audit `actor_subject_hash` and challenge `preauth_subject_hash`, distinguished only by the pinned domain-separation prefix `"actor-subject:v1:"`, exposed as one shared derivation helper. Phase 07's `idp_account_hash` gets its own key under the parallel `"idp-account:v1:"` derivation.
- **D-22:** Startup **fails closed only on the active key**. A missing *older* version is a warning. Rejected: requiring every version 1..active to be present.

**Module layout**

- **D-23:** The seven subsystems go in a **new `src/nativespeaker/api/auth/` subpackage** — barrier, route registry, audit writer, challenge store, adapter interfaces, key derivation — with the existing `auth.py` absorbed into it as the verification module. The error registry is the deliberate exception — it sits at package root per D-10. — **Reversibility:** costly.

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

### Deferred Ideas (OUT OF SCOPE)

- **The Envoy gateway contract (FOUND-09 / `§9`)** — moved to the next milestone per D-08.
- **Backend rate limiting (`§5`)** — removed rather than deferred per D-05.
- **`quota_checked_request` admission (`§8.4`, Phase 36 REBIND-04)** — void with D-05.
- **Timing normalization for anti-oracle guarantees** — explicitly not built per D-13.
- **Google Secret Manager for all secrets** — captured at `.planning/todos/pending/secret-manager-integration.md`.
- **Fully working chat routes in Phase 35** — considered and rejected per D-15.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOUND-01 | Mandatory default-on pre-handler barrier; only place JWT acceptance and identity resolution happen; admits only `identity_state='active'` AND `users.active` TRUE | § Pattern 1 (pure-ASGI barrier), § Pattern 2 (route resolution), § Code Example 1–2. Enum values verified from the applied migration. |
| FOUND-02 | Exactly-one-`Authorization` wire contract; zero / duplicate / comma-joined / multiple credentials / empty / trailing all reject as `invalid_external_jwt` | § Pitfall 1 (`Headers.get()` silently takes the first value). `scope["headers"]` preserves duplicates; verified through both httpx `ASGITransport` and Starlette `TestClient`. |
| FOUND-03 | Route registry, three-way partition, startup enumeration assertion failing in both directions | § Pattern 3 + § Code Example 3. `app.routes` contents verified empirically for `APIRoute` / `APIWebSocketRoute` / `Mount` / docs-disabled. |
| FOUND-04 | One shared error-registry module owning shape, statuses, copy, handlers | § Pattern 4. Framework exception inventory verified from Starlette/FastAPI source. |
| FOUND-05 | Audit writer: one durable row per on-path attempt, redacted `details`, HMAC-SHA-256 `actor_subject_hash` with key version | § Pattern 5, § Code Example 4. Column list and CHECKs quoted verbatim from the migration. |
| FOUND-06 | Provider-call budget seam with plain in-process counters; 3-attempt Firebase retry budget; check-all-then-charge helper | § Pattern 6. No dependency needed. |
| FOUND-07 | Challenge store implementing claim/consume | § Pattern 7, § Code Example 5 — the two conditional `UPDATE`s were executed against the live `core.auth_challenges` table. |
| FOUND-08 | Adapter interfaces only, no implementations | § Pattern 8. `typing.Protocol` + frozen dataclasses; the codebase already uses `Protocol` in `auth.py`. |
</phase_requirements>

## Project Constraints (from CLAUDE.md → AGENTS.md)

| Directive | Consequence for this plan |
|-----------|---------------------------|
| First version, no users, startup | Do not build operational scale machinery. Reinforces D-05 and D-13. |
| Sub-$5/month subscription; the product is not worth stealing — do not over-engineer the threat model, but do not skip normal security measures | Normal measures that stay: fail-closed barrier, positive-test identity resolution, HMAC-hashed subjects, redaction, anti-oracle response identity. Skipped by decision and now documented: timing normalization (D-13), distributed limiters (D-05). |
| Keep specs short; programming this app should not consume many tokens | Prefer one module per subsystem over deep package trees inside `auth/`. Prefer a single declarative registry table over a builder DSL. Do not generate per-error-class subclasses where a table entry suffices. |
| Runs in Kubernetes behind Envoy Gateway, which authenticates by JWT and rate-limits by IP, user, URL | The backend remains the sole authoritative verifier (`§9` is explicit). D-08 defers the gateway contract; nothing in `k8s/` changes. |

## Summary

Nearly everything Phase 35 needs already exists in the repository, and the framework surface it depends on behaves as the locked decisions assumed — with three exceptions that will silently produce a wrong plan if missed.

First, **the application already boots.** `import nativespeaker.api.app.main` succeeds today and `app.router.lifespan_context(app)` runs to completion against the applied v2.0 schema `[VERIFIED: executed in .venv, 2026-08-20]`. D-14's "repair the model layer so the application boots" is therefore not import repair — it is *query* repair. `select(User)` fails with `UndefinedColumnError: column users.jwt_sub`, `select(UsageMonthly)` fails with `UndefinedTableError: relation "core.usage_monthly"`, and `select(Chat)` succeeds `[VERIFIED: executed against the live database, 2026-08-20]`. Scoping the phase around "make it import" would under-plan; scoping it around "delete or repair every model/database/service module that touches a dropped structure" is the real shape, and § Runtime State Inventory enumerates that set exhaustively.

Second, **D-14 structurally pulls REBIND-01 into Phase 35.** `§2.3` failure condition 1 fails the assertion on any registered route the registry does not declare. Once the assertion runs at real startup against the real router (D-14), the ten surviving pre-existing routes must each carry a registry entry, which is precisely REBIND-01's "partition membership is declared for every pre-existing route ... and the enumeration assertion passes in both directions." This is a requirement-boundary move that must be recorded before planning, exactly as the three D-05/D-08/D-14 overrides were. It pulls in only the *declaration*; REBIND-02 (audit exclusion), REBIND-03 (business-error preservation), and REBIND-05 (grant/quota flow) stay in Phase 36.

Third, **the barrier must be pure ASGI, not `BaseHTTPMiddleware`,** and it must resolve the matched route by calling `route.matches(scope)` itself. Starlette never sets `scope["route"]` on the way in — that key is written by `APIRoute.matches` during router dispatch, which happens inside `call_next`, after the barrier has already had to decide `[VERIFIED: fastapi/routing.py:800-804, 994-998; empirically confirmed]`. And a `BaseHTTPMiddleware` cannot see contextvars set anywhere downstream, and disrupts contextvars propagation for pure-ASGI middleware below it `[CITED: starlette docs/middleware.md § BaseHTTPMiddleware > Limitations]` — which matters because the existing `RequestLoggingMiddleware` is a `BaseHTTPMiddleware` sitting outermost per D-03 and will therefore never see anything the barrier binds.

**Primary recommendation:** implement the barrier as a pure ASGI middleware that (1) iterates `scope["app"].router.routes` calling `route.matches(scope)` and takes the first `Match.FULL`, (2) passes straight through when nothing matches FULL so the router's own 404/405 stays admission-phase, (3) reads `scope["headers"]` directly for the wire contract, (4) obtains its session from `scope["app"].state.session_factory` **per request, never cached in `__init__`**, and (5) returns error-registry responses by awaiting them against `(scope, receive, send)` without ever calling the downstream app.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Request-rate enforcement | CDN / Gateway (Envoy) | — | D-05: sole enforcement point; the backend builds none. |
| JWT signature/claims verification | API / Backend | Gateway (defence-in-depth only) | `§9` and SHARED-INVARIANTS: the backend is the sole authoritative verifier; no backend correctness depends on Envoy. |
| `Authorization` wire contract (exactly one field value) | API / Backend — ASGI middleware layer | — | Must run before either layer picks a value; only the backend sees the raw `scope["headers"]` list. |
| Identity resolution `(issuer, subject)` → user | API / Backend — barrier middleware | Database (single query) | `§1.3` is a positive test over two columns; one query, one code path (D-13). |
| Route→category/operation metadata | API / Backend — declarative registry module | — | Must be readable before dispatch, so it cannot live on the route object FastAPI builds. |
| Client-visible error shape and copy | API / Backend — one registry module at package root | — | D-09/D-10: one module, one response model, one handler set. |
| Audit durability (`audit.auth_events`) | Database | API / Backend (writer) | Two write modes; standalone-durable commits before the response returns. |
| Challenge serialization | Database (one atomic conditional `UPDATE`) | API / Backend | `§6.1`: the claim is the single serialization point; no application-side lock. |
| Provider-call budgets | API / Backend — in-process counters | — | Per-request call metering, not traffic limiting; no gateway can express it (D-06). |
| HMAC key material | Config file (v2.0) → Secret Manager (deferred) | — | D-20 with its accepted git-history consequence. |

## Standard Stack

**No new runtime dependency is required by this phase.** Every capability is covered by a stdlib module or a dependency already pinned in `pyproject.toml`.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.135.1 (pinned `==`) | App, routers, `Depends()` accessors, route introspection | `[VERIFIED: importlib.metadata in .venv]` Already the app framework. |
| `starlette` | 0.52.1 (transitive) | ASGI middleware protocol, `Route.matches`, `Match`, `JSONResponse`, `HTTPException` | `[VERIFIED: importlib.metadata in .venv]` The barrier lives at this layer. |
| `sqlmodel` | 0.0.37 | Session factory, ORM models, `update().where().returning()` | `[VERIFIED: importlib.metadata]` v1.6 zero-raw-SQL convention (D-19). |
| `sqlalchemy` | 2.0.46 | `update()`, `async_sessionmaker`, `join_transaction_mode` | `[VERIFIED: importlib.metadata]` |
| `pydantic` / `pydantic-settings` | 2.12.5 / 2.13.1 | `HmacConfig` model, `SecretStr`, YAML-init + env-secret layering | `[VERIFIED: importlib.metadata]` D-20 keeps the existing split. |
| `PyJWT[crypto]` | 2.12.1 | RS256 verification against cached JWKS | `[VERIFIED: importlib.metadata]` `JWTVerifier` already uses `PyJWKClient`. |
| `structlog` | 25.5.0 | Structured security log, contextvars binding | `[VERIFIED: importlib.metadata]` |
| `hmac` + `hashlib` (stdlib) | Python 3.14.7 | HMAC-SHA-256 derivation | Never hand-roll; `hmac.new(k, msg, hashlib.sha256).digest()` returns 32 bytes `[VERIFIED: executed]`. |
| `secrets` + `base64` (stdlib) | Python 3.14.7 | 16-byte CSPRNG `challenge_id`, base64url unpadded | `base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=")` yields 22 chars `[VERIFIED: executed]`. |
| `uuid.uuid7` (stdlib) | Python 3.14.7 | Row ids, attempt ids | `uuid.uuid7()` exists in 3.14 `[VERIFIED: executed]`; already used across `models/`. |
| `typing.Protocol` + `dataclasses` (stdlib) | Python 3.14.7 | Adapter interfaces (FOUND-08), typed identity context | Already the codebase idiom (`auth.py` `TokenVerifier`). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` / `pytest-asyncio` | 9.0.2 / 1.3.0 | Test runner; `asyncio_mode=auto` | All tests. |
| `httpx` | 0.28.1 | `ASGITransport` e2e client | Wire-contract and identity-matrix e2e tests. |
| `firebase-admin` | 7.3.0 | Nothing in this phase | FOUND-08 declares the interface; foundation calls it zero times (`§7.1`). |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pure ASGI barrier | `BaseHTTPMiddleware` | Rejected — see § Pitfall 2. Loses contextvars propagation and forces `Headers` access that violates `§1.1`. |
| `route.matches(scope)` | Registry lookup keyed on `(method, path_template)` | Rejected as *primary* matcher — you would have to reimplement `compile_path` to turn `/chats/abc` into `/chats/{chat_id}`. Keep the registry lookup as the *second* step, keyed on the matched route's `.path`. |
| A new `method_not_allowed` class | Fold 405 into `invalid_request` (400) | Rejected — that is exactly the `_STATUS_REMAP` lie D-12 deletes, and D-12 pins "its own honest status". |
| `dict[int, SecretStr]` key map | A list of `{version, key}` objects | Rejected — the dict validates the uniqueness of versions for free and reads directly as `keys[active_version]`. |

**Installation:**

```bash
# none — this phase adds no dependency
```

**Version verification** `[VERIFIED: .venv/bin/python -c "import importlib.metadata …", executed 2026-08-20]`:
`fastapi==0.135.1 · starlette==0.52.1 · pydantic==2.12.5 · pydantic-settings==2.13.1 · sqlmodel==0.0.37 · sqlalchemy==2.0.46 · pyjwt==2.12.1 · structlog==25.5.0 · httpx==0.28.1 · pytest==9.0.2 · pytest-asyncio==1.3.0 · firebase-admin==7.3.0 · asyncpg==0.31.0 · uvicorn==0.42.0 · CPython 3.14.7`.

## Package Legitimacy Audit

**This phase installs no external packages.** No `pip install`, no `pyproject.toml` dependency addition, no new `uv.lock` entry. The Package Legitimacy Gate is therefore vacuous for Phase 35.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none added)* | — | — | — | — | — | — |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** none.

Note: D-05 *removes* the `limits` package that `01-foundation.md §5` would have introduced. If a plan task proposes adding `limits`, `redis`, `valkey`, or `python-multipart`, that task has drifted from D-05 (or, for `python-multipart`, from the "no `Form`/`File` params" reality — it is **not** installed `[VERIFIED: RuntimeError from fastapi/dependencies/utils.py:118 when declaring a Form param]`).

## Architecture Patterns

### System Architecture Diagram

```
                     ┌──────────────────────────────────────────────┐
   HTTP request ───► │ ServerErrorMiddleware  (Starlette, implicit)  │  ← 500 handler only
                     └───────────────────┬──────────────────────────┘
                                         ▼
                     ┌──────────────────────────────────────────────┐
                     │ RequestLoggingMiddleware (BaseHTTPMiddleware) │  ← D-03 outermost user mw
                     └───────────────────┬──────────────────────────┘
                                         ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │ AUTH BARRIER  (pure ASGI middleware — D-01)                                  │
   │                                                                              │
   │  scope["type"] != "http" ──────────────────────────────────► pass through    │
   │            │                                                                 │
   │  (1) resolve route:  for r in scope["app"].router.routes: r.matches(scope)    │
   │            ├── no Match.FULL ──────────────────────────────► pass through    │
   │            │        (router owns 404 / 405 / 307 — admission phase, no audit) │
   │            ▼ Match.FULL                                                       │
   │  (2) registry lookup  (method, route.path) → RouteMetadata ──┐               │
   │            │            miss ⇒ startup assertion already failed              │
   │            ▼                                                  │              │
   │       category?                                               │              │
   │        ├─ public ────────────────────────────────────────────►│ pass through │
   │        ├─ provider_callback ─────────────────────────────────►│ pass through │
   │        └─ authenticated                                       │  (no identity)│
   │            ▼                                                  │              │
   │  (3) wire contract  ── scope["headers"] raw list ── reject ──►(E)            │
   │  (4) verify JWT     ── JWTVerifier (cached JWKS) ── reject ──►(E)            │
   │  (5) resolve identity ── ONE query: external_identities ⋈ users               │
   │            │            (both account_unavailable branches, same path — D-13) │
   │            ├─ outcome 1'/2/3 ─────────────────────── reject ──►(E)           │
   │            ▼ outcome 1 (pre-auth) | 4 (linked)                               │
   │  (6) build RequestContext → scope["state"]["ns_request_context"]              │
   │            │      { variant, route_metadata, client_ip_bucket_kind,           │
   │            │        evaluated_at, attempt_id }                                │
   │            ▼                                                                  │
   └────────────┼──────────────────────────────────────────────────────────────────┘
                │                              (E) REJECT PATH
                │                               ├─ metadata.operation is not None
                │                               │    └─► AuditWriter.write_standalone()
                │                               │          commits before response
                │                               ├─ always: security log + counter metric
                │                               └─► return ErrorRegistry.response(cls)
                │                                     (RETURNED, never raised — D-01)
                ▼
   ┌──────────────────────────────────┐
   │ ExceptionMiddleware  (Starlette)  │  ← where app.add_exception_handler lives
   └────────────────┬─────────────────┘
                    ▼
   ┌──────────────────────────────────┐
   │ Router → APIRoute → Depends(...)  │
   │   get_linked_identity()  ─────────┼──► reads scope["state"], raises if absent
   │   get_request_context()           │
   └────────────────┬─────────────────┘
                    ▼
              handler ──► ChallengeStore.issue/locate/claim/consume  ─► core.auth_challenges
                     ──► AuditWriter.write_in_transaction(session)   ─► audit.auth_events
                     ──► BudgetGate.check_all() / charge_all()       ─► in-process counters

   STARTUP (lifespan, before serving):
     load config ─► HmacKeyring.validate()  ── missing active version ⇒ abort
                 ─► assert_route_enumeration(app, REGISTRY) ── 9 conditions ⇒ abort
                 ─► construct ChallengeStore / AuditWriter / BudgetGate on app.state
```

### Recommended Project Structure

```
src/nativespeaker/api/
├── errors.py                  # D-10: the one error registry at package root; replaces exceptions.py
├── config.py                  # + HmacConfig; − AppleConfig, − quotas
├── logs.py                    # unchanged (RequestLoggingMiddleware stays BaseHTTPMiddleware)
├── auth/                      # D-23: new subpackage, one stable import root for phases 36–46
│   ├── __init__.py            # re-exports the public seam
│   ├── verification.py        # absorbed auth.py: TokenVerifier, JWTVerifier + §1.2 rules
│   ├── wire.py                # §1.1 single-Authorization contract → (token | BoundedReason)
│   ├── context.py             # LinkedIdentity, PreAuthIdentity, RequestContext (typed, frozen)
│   ├── barrier.py             # the pure ASGI middleware (§1.5 ordering)
│   ├── registry.py            # §2.2 RouteMetadata table + §2.3 assert_route_enumeration()
│   ├── identity.py            # §1.3 the ONE resolution query + admission matrix
│   ├── audit.py               # §4 writer, two modes, details builder, redaction
│   ├── challenges.py          # §6 store: issue / locate / claim / consume
│   ├── keys.py                # D-21/D-22 HmacKeyring + pinned domain prefixes
│   ├── budgets.py             # D-06 §7.1 in-process counters + check-all/charge-all gate
│   └── adapters.py            # FOUND-08 Protocols + result types ONLY
├── app/
│   ├── main.py                # docs off (D-04), redirect_slashes off, middleware order (D-03)
│   ├── lifespan.py            # keyring validation + enumeration assertion, fail closed
│   ├── dependencies.py        # D-02 accessors; − get_current_user, − require_quota
│   └── errors.py              # registers the handlers (unchanged role)
├── models/                    # repaired; users.py to the v2.0 seven-column shape
├── database/                  # − usage.py, − subscriptions.py
├── routers/                   # − webhooks.py, − users.py
└── services/                  # − subscriptions.py, − users.py, − firebase.py
```

### Pattern 1: Pure ASGI barrier that returns instead of raising

**What:** A three-arg callable class installed with `add_middleware`. It never calls `self.app` on a rejection; it awaits a `Response` against `(scope, receive, send)` directly.

**When to use:** Any middleware that must produce a *specific* client-visible status. `add_middleware` places user middleware between `ServerErrorMiddleware` and `ExceptionMiddleware` `[VERIFIED: starlette/applications.py:85-89 — "middleware = [Middleware(ServerErrorMiddleware, handler=error_handler, debug=debug)] + self.user_middleware + [Middleware(ExceptionMiddleware, handlers=exception_handlers, debug=debug)]"]`, so an exception raised in it bypasses every class-specific handler. Empirically: a custom exception with a registered handler returning 418, raised from middleware, produced **500 `internal_error`** instead `[VERIFIED: executed 2026-08-20]`. D-01's rationale is confirmed exactly.

**Example:**

```python
# src/nativespeaker/api/auth/barrier.py
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

class AuthBarrierMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # NOTE: capture NOTHING from app.state here. See Pitfall 5.

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":                 # lifespan + websocket pass through
            await self.app(scope, receive, send)
            return

        route = _match_full(scope)
        if route is None:                            # 404 / 405 / 307 belong to the router
            await self.app(scope, receive, send)     # admission phase: no audit row (§4.1)
            return

        meta = REGISTRY.lookup(scope["method"], route.path)
        if meta.category is not Category.AUTHENTICATED:
            await self.app(scope, receive, send)
            return

        decision = await self._admit(scope, meta)    # steps 2–5 of §1.5
        if decision.rejected:
            response = ERRORS.response(decision.error_class)
            await response(scope, receive, send)     # RETURN, never raise (D-01)
            return

        scope.setdefault("state", {})["ns_request_context"] = decision.context
        await self.app(scope, receive, send)

def _match_full(scope: Scope):
    for route in scope["app"].router.routes:
        match, _child = route.matches(scope)
        if match == Match.FULL:
            return route
    return None
```

`scope["state"]` mutations made by middleware **are** visible to the handler via `request.state`, and remain visible to an outer `BaseHTTPMiddleware` after `call_next` returns `[VERIFIED: executed 2026-08-20 — an outer BaseHTTPMiddleware read the barrier's `scope["state"]` keys after `call_next`]`. That is the supported channel; contextvars are not (§ Pitfall 2).

### Pattern 2: Resolve the matched route by asking Starlette, not by string-matching

**What:** iterate `scope["app"].router.routes` and call `route.matches(scope)`, taking the first `Match.FULL`.

**Why this and not `scope["route"]`:** `Router.app` sets `scope["router"]` but never `scope["route"]`; FastAPI adds `child_scope["route"] = self` inside `APIRoute.matches` / `APIWebSocketRoute.matches` `[VERIFIED: .venv/lib/python3.14/site-packages/fastapi/routing.py:800-804 and 994-998 — "match, child_scope = super().matches(scope); if match != Match.NONE: child_scope[\"route\"] = self; return match, child_scope"]`, and that `child_scope` is merged only when `Router.app` dispatches — i.e. *inside* `call_next`. Empirically, `"route" in request.scope` was `False` on the way in for both a `BaseHTTPMiddleware` and a raw ASGI middleware, and `True` only after dispatch `[VERIFIED: executed 2026-08-20]`.

**Why not a registry lookup as the primary matcher:** the request path is `/chats/9f3…`, the registry key is `/chats/{chat_id}`. Turning one into the other means reimplementing `compile_path`. `route.matches()` is literally the same code the router will run one layer down, so the barrier and the router can never disagree — which is the structural form of `§2.3` failure condition 9.

**Match semantics** `[VERIFIED: starlette/routing.py:40-43 — "class Match(Enum): NONE = 0 / PARTIAL = 1 / FULL = 2"]`:

- `Match.FULL` — path regex matched **and** method is in `route.methods`.
- `Match.PARTIAL` — path matched, method did not. `Router.app` collects the first PARTIAL and dispatches to it, and `Route.handle` then raises `HTTPException(status_code=405, headers={"Allow": …})` `[VERIFIED: starlette/routing.py:283-285]`.
- `Match.NONE` — no path match.
- `Mount.matches` returns only FULL or NONE, never PARTIAL, and rewrites `root_path`. **This phase registers no `Mount`** — treat any `Mount` in `app.routes` as an enumeration-assertion failure.

**Recommendation on PARTIAL:** the barrier should treat "no FULL match" as pass-through, PARTIAL included. `§4.1` names "route/method mismatch" as an admission-phase rejection that writes no audit row, and the resulting 405 is only reachable by a caller who already got past... nothing — which is fine, because a 405 leaks only that a path template exists, and the alternative (401 on every wrong-method request) would make the barrier own a status it has no metadata for.

### Pattern 3: Startup route enumeration

**What:** a pure function `enumerate_registered(app) -> set[tuple[str, str]]` plus `assert_route_enumeration(app, registry)` implementing all nine `§2.3` conditions, called from the lifespan before `yield`.

Verified `app.routes` contents `[VERIFIED: executed 2026-08-20]`:

| Route object | `path` | `methods` | Enumerate as |
|---|---|---|---|
| `fastapi.routing.APIRoute` | template, e.g. `/chats/{chat_id}` | `{"GET"}` — **HEAD is not added** | one `(method, path)` per method |
| `fastapi.routing.APIWebSocketRoute` | template | attribute absent | `("WEBSOCKET", path)` — none registered; treat as undeclared |
| `starlette.routing.Mount` | prefix, e.g. `/static` | `None` | fail the assertion — foundation registers no mount |
| `starlette.routing.Route` (docs) | `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc` | `{"GET", "HEAD"}` | absent entirely once D-04 lands |

With `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`, `app.routes == []` before any `include_router` `[VERIFIED: executed 2026-08-20]`. D-04 fully removes all four default routes — there is no residual `/docs/oauth2-redirect`.

`route.path` and `route.path_format` are identical for this project's templates (`/chats/{chat_id}`) `[VERIFIED: executed]`; they diverge only when a path converter suffix is used (`{id:int}`), which this project never does. Use `route.path` and declare registry paths byte-identically.

The registered set for Phase 35 after D-04 and D-16, ordered as `app.routes` yields it `[VERIFIED: executed against the current app, minus the D-16 deletions]`:

```
GET    /                     GET    /chats            GET    /chats/{chat_id}
POST   /chats                POST   /chats/{chat_id}  DELETE /chats/{chat_id}
GET    /examples             GET    /health/ready
```

Eight entries — `GET /users/me` and `POST /webhooks/apple` are deleted by D-16. All eight must be declared (see § Pitfall 4).

### Pattern 4: One error registry, total by construction

**What:** one module at package root owning `ErrorClass` (name → status, code, copy, extra fields), the `ErrorResponse` model, a `response(cls)` factory, and the framework-exception mapping.

**Complete inventory of framework exceptions that can reach a handler in this deployment** `[VERIFIED: source inspection of starlette 0.52.1 and fastapi 0.135.1 in .venv]`:

| Raised by | Exception | Status | Maps to declared class |
|---|---|---|---|
| `Router.not_found` | `starlette.exceptions.HTTPException` | 404 | `not_found` (404) |
| `Route.handle` (method mismatch) | `starlette.exceptions.HTTPException` | 405 | **`method_not_allowed` (405)** — recommended new class; preserve the `Allow` header |
| FastAPI request parsing/validation | `fastapi.exceptions.RequestValidationError` | 422 | `validation_error` (422) |
| Anything unhandled | `Exception` | 500 | `internal_error` (500) |
| Application code | `ServiceError` subclasses | per class | the class each declares |

**415 is unreachable and must not be declared.** `grep -rn "415" .venv/…/fastapi/` returns nothing, and Starlette's only occurrence is the `HTTP_415_UNSUPPORTED_MEDIA_TYPE = 415` constant in `status.py` `[VERIFIED: executed 2026-08-20]`. FastAPI emits 415 only on `Form`/`File` paths, and `python-multipart` is not installed, so a `Form` parameter cannot even be declared `[VERIFIED: RuntimeError raised at route-registration time]`. Declaring a class no branch reaches is precisely the argument D-11 used to retire `unauthorized` — apply it consistently and declare none.

**405 gets its own class at its own status.** Two supporting facts: `_STATUS_REMAP`'s existing `405 → 400` is the same category of lie as its `409 → 400` collision, and — importantly — a 405 is only reachable by a caller the barrier already admitted, because the barrier runs first and rejects unauthenticated requests with `auth_required` before the router ever produces the 405. There is no anti-oracle cost.

**Totality:** replace `_STATUS_REMAP` + `_CODE_MAP.get(status, 500)` with an explicit closed `dict[int, ErrorClass]` and a module-level self-check run from the lifespan that asserts every status the registry can produce has exactly one class and that no two classes share a code. A runtime miss logs `error_registry_unmapped_status` at ERROR and returns `internal_error` — a loud programming-error path, not a silent table fallback.

**Retiring `unauthorized` (D-11):** `[VERIFIED: grep over k8s/ 2026-08-20]` there are **zero** `unauthorized` references in `k8s/`. The only error-code string in the chart is `k8s/templates/backend-traffic-policy.yaml:53 — inline: '{"code":"quota_exceeded"}'` on a 429, which `§3.2` says should name `rate_limited`. D-08 forbids touching `k8s/` this phase, so this stays a known, accepted inconsistency to record in the phase notes rather than a task.

### Pattern 5: Audit writer, two modes, one shared session source

**What:** a class whose standalone mode opens its own session from `app.state.session_factory` and commits before the response returns, and whose in-transaction mode takes the caller's `AsyncSession` as a parameter.

Row shape, quoted verbatim from the applied migration `[VERIFIED: migrations/20260818_01_initial-release.sql:641-670]`:

```sql
CREATE TABLE audit.auth_events (
    id UUID PRIMARY KEY,
    challenge_row_id UUID,
    operation core.auth_operation,
    result core.auth_event_result NOT NULL,
    actor_issuer TEXT,
    actor_subject_hash BYTEA,
    actor_subject_hash_key_version SMALLINT,
    actor_provider core.identity_provider,
    details JSONB NOT NULL DEFAULT '{"schema_version":1,"context":{},"verification":{},"resolved":{},"mutation":{},"failure":{}}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
```

with the CHECK that makes success criterion 4 structural:

```sql
    CHECK (
        (result = 'invalid_external_jwt'
            AND actor_issuer IS NULL
            AND actor_subject_hash IS NULL
            AND actor_subject_hash_key_version IS NULL
            AND actor_provider IS NULL)
        OR
        (result <> 'invalid_external_jwt'
            AND actor_issuer IS NOT NULL
            AND actor_subject_hash IS NOT NULL
            AND actor_subject_hash_key_version IS NOT NULL)
    ),
```

`actor_subject_hash_key_version` is `SMALLINT` — bound `HmacConfig.active_version` to `1 ≤ N ≤ 32767` so a bad config fails at load rather than at the first insert.

The internal result values foundation itself emits, each an exact member of `core.auth_event_result` `[VERIFIED: migration lines 89-133]`: `'invalid_external_jwt'`, `'preauth_identity_not_allowed'`, `'historical_identity'`, `'blocked_user'`, `'internal_error'`, `'challenge_not_found'`, `'challenge_expired'`, `'challenge_consumed'`, `'challenge_identity_mismatch'`, `'challenge_operation_mismatch'`. The seven `core.auth_operation` values are `'create_user'`, `'upgrade_anonymous_to_registered'`, `'claim_anonymous_grant'`, `'claim_registered_grant'`, `'restore_subscription'`, `'sign_out_all'`, `'sync'` `[VERIFIED: migration lines 59-69]` — foundation declares `operation = None` on every route it registers, so no row it writes carries one.

### Pattern 6: In-process budget gate (D-06)

**What:** a per-request object created by the barrier and carried on the request context; a `dict[str, int]` of remaining counts plus two methods.

```python
class BudgetGate:
    """Per-request provider-call metering. Not traffic limiting (D-05)."""
    def check_all(self, names: Sequence[str]) -> str | None: ...   # broadest→narrowest; returns first exhausted
    def charge_all(self, names: Sequence[str]) -> None: ...        # only after check_all returned None
```

`§7.1` order is load-bearing: check **every** applicable budget non-destructively, increment **nothing** unless all have capacity, then charge them **together** immediately before the outbound call and before each permitted retry. When more than one is exhausted the global `adapter_firebase_lookup` is the primary reported result. Foundation ships only the mechanism and the `adapter_firebase_lookup` name with its 3-attempt budget; every endpoint-layer name belongs to a later phase.

### Pattern 7: Challenge claim/consume as two conditional `UPDATE`s

Executed against the live `core.auth_challenges` table `[VERIFIED: executed 2026-08-20 — CLAIM#1 returned 1 row, CLAIM#2 returned 0, CONSUME returned 1]`. See § Code Example 5. Three facts the plan depends on:

1. `session.exec(update(...).returning(col(Model.id)))` gives an affected-row count via `len(result.all())` — no `rowcount` guesswork, and it works under `join_transaction_mode="create_savepoint"`.
2. The claim's `WHERE` must carry **both** `claimed_at IS NULL` **and** `expires_at > :now`. `§6.1` makes this the only place expiry is evaluated; no earlier step checks `expires_at`.
3. Consume must set `consumed_at` and clear `preauth_subject_hash` in **one** `UPDATE`, because the table CHECK admits a cleared hash only once `consumed_at` is set `[VERIFIED: migration lines 625-634 — "(bound_external_identity_id IS NULL AND preauth_issuer IS NOT NULL AND (preauth_subject_hash IS NOT NULL OR consumed_at IS NOT NULL))"]`. Two statements would trip the constraint.

Lifecycle discrimination is by column nullability, not a state enum `[VERIFIED: migration lines 601-607 — "Lifecycle: issued while claimed_at IS NULL; claimed once claimed_at and the attempt's server-generated claim_attempt_id are set; consumed once consumed_at is set."]`.

### Pattern 8: Adapter interfaces with zero implementations

`typing.Protocol` classes plus frozen dataclass / `StrEnum` result types, and **not one** `firebase_admin` call. `§7.1` is explicit that foundation calls `get_user_provider_data` zero times. A plan task that imports `firebase_admin.auth` inside `auth/adapters.py` has drifted.

### Anti-Patterns to Avoid

- **Using `request.headers.get("authorization")` for the wire contract.** It returns only the *first* value, which `§1.1` forbids. See § Pitfall 1.
- **Caching `session_factory` (or `config`, or `jwt_verifier`) in the barrier's `__init__`.** Breaks the e2e rollback fixture. See § Pitfall 5.
- **Raising from the barrier.** `app.add_exception_handler` never sees it. See § Pattern 1.
- **Declaring an error class no branch reaches** (415, or `unauthorized`) — D-11's own reasoning.
- **Adding routes after `add_middleware` and assuming order.** `add_middleware` inserts at index 0, so the *last* call is outermost. See § Pitfall 3.
- **Treating `identity_state` as an open enum.** `§1.3` outcome 2: anything not exactly `active` — including NULL and unrecognized — rejects, never falls through to pre-auth.
- **Writing the public `challenge_id` anywhere but the prepare response body.** Not in `audit.auth_events`, `details`, logs, traces, or error text; correlate with `core.auth_challenges.id`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Turning `/chats/9f3…` into `/chats/{chat_id}` | A path-template matcher | `route.matches(scope)` | `compile_path` handles converters, trailing-slash, and mount root_path rewriting; a hand-rolled matcher will disagree with the router it is supposed to guard. |
| Counting `Authorization` field instances | Header parsing | `scope["headers"]` (raw list of `(bytes, bytes)`) or `Headers.getlist()` | Both preserve duplicates; `.get()` silently collapses them. |
| Keyed subject hashing | Any bespoke digest | `hmac.new(key, msg, hashlib.sha256).digest()` | Constant-time comparison via `hmac.compare_digest` for binding verification. |
| Opaque capability handle | UUID string, counter, or token format | `base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=")` | `§6.1` pins 16 CSPRNG bytes, base64url, unpadded. |
| Challenge mutual exclusion | Advisory locks, `SELECT … FOR UPDATE`, an app-level mutex | One conditional `UPDATE` with `RETURNING` | `§6.1`: the update *is* the serialization point. SHARED-INVARIANTS forbids distributed locks outright. |
| Secret values in config | `str` fields | `pydantic.SecretStr` | Already the codebase idiom (`DatabaseConfig.password`); keeps keys out of `repr`/tracebacks/log lines. |
| Per-request DB session plumbing in middleware | A second pool or a raw asyncpg connection | `scope["app"].state.session_factory` | D-19; and the e2e rollback fixture swaps exactly this attribute. |
| Request-scoped correlation | A custom contextvar chain across middleware | `scope["state"]` for data, `structlog.contextvars` for log fields | `scope["state"]` survives `BaseHTTPMiddleware`; contextvars do not. |

**Key insight:** every hand-rolled alternative in this domain fails the same way — it disagrees with the framework layer beneath it under a condition nobody tests (a converter in a path, a duplicated header field, a savepoint-nested commit), and the disagreement surfaces as a security hole rather than a crash.

## Runtime State Inventory

This is a refactor/migration phase (D-14/D-16). Every category was checked explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | The applied dev database at `localhost:5432` already has the full v2.0 schema — 17 tables across `core` and `audit`, **no** `core.usage_monthly`, **no** `core.subscription_events`, `core.users` without `jwt_sub`/`subscription_plan` `[VERIFIED: information_schema query, 2026-08-20]`. There is no legacy row data to migrate (Phase 34's migration was destructive against an empty DB). `core.access_tiers` is **empty** — the migration seeds no tier rows by design `[VERIFIED: migration comment at line 258 — "This migration seeds NO tier rows (00-schema.md:249)"]`. | Code edits only. **No data migration.** But note the empty `access_tiers`: Phase 36's grant path has nothing to resolve against until tiers are configured. Out of scope here; flag for Phase 36. |
| **Live service config** | None. This service has no externally-hosted workflow, dashboard, or ACL state carrying a renamed string. `config/config.yaml` and `config/examples.yaml` are both tracked in git `[VERIFIED: git ls-files]`. | None. |
| **OS-registered state** | None — no scheduled task, pm2 process, systemd unit, or launchd plist in this repo. Deployment is a Kubernetes `Deployment` in `k8s/templates/deployment.yaml`, untouched per D-08. | None. |
| **Secrets / env vars** | `.env` (gitignored) defines exactly: `APPLE_CERTS_DIR CONFIG_DIR DB_HOST DB_NAME DB_PASSWORD DB_PORT DB_USER FIREBASE_TEST_EMAIL FIREBASE_TEST_PASSWORD JWT_API_KEY JWT_PROJECT_ID OPENAI_API_KEY POSTGRES_*` `[VERIFIED: key-name extraction from .env, 2026-08-20]`. Deleting `AppleConfig` (D-16 cascade) orphans `APPLE_CERTS_DIR`. The new `hmac:` block adds **no** env var — it is YAML-only per D-20. | Remove `APPLE_CERTS_DIR` from `.env.example`; leave the developer's `.env` alone. Add the `hmac:` block to `config/config.yaml` and to any deployment copy. |
| **Build artifacts** | `src/ns_api_gateway.egg-info/` exists and its `SOURCES.txt` still lists `nativespeaker/api/exceptions.py` `[VERIFIED: grep hit on src/ns_api_gateway.egg-info/SOURCES.txt]`. The package is installed editable via setuptools with `packages.find` over `src/`. Converting `auth.py` → `auth/` adds a subpackage. | Re-run the editable install (`uv sync` / `pip install -e .`) after the `auth/` split so the new subpackage is discovered; the stale `SOURCES.txt` is otherwise harmless. Note `auth/` needs an explicit `__init__.py` — the project currently uses implicit namespace packages at `nativespeaker/` and `nativespeaker/api/` (no `__init__.py` at either level) but every subpackage (`models/`, `database/`, `routers/`, `services/`) has one `[VERIFIED: find src -name "__init__.py"]`. |

### The boot-repair surface (D-14/D-15/D-16), module by module

`import nativespeaker.api.app.main` **already succeeds** and the lifespan **already runs to completion** `[VERIFIED: executed 2026-08-20 — "LIFESPAN OK; state keys: ['apple_verifier', 'config', 'firebase_service', 'jwt_verifier', 'llm_service', 'session_factory']"]`. The failure is at query time `[VERIFIED: executed against the live DB — `select(User)` → `UndefinedColumnError: column users.jwt_sub`; `select(UsageMonthly)` → `UndefinedTableError: relation "core.usage_monthly"`; `select(Chat)` → OK]`.

| Module | Touches a dropped structure | Disposition |
|---|---|---|
| `models/users.py` `User` | `jwt_sub`, `name`, `subscription_plan` | **Repair** to the v2.0 shape: `id, email, display_name, registered_at, active, created_at, updated_at` `[VERIFIED: migration lines 150-158]`. `email` is nullable on purpose. |
| `models/users.py` `UsageMonthly` | `core.usage_monthly` | **Delete.** Phase 36 introduces `core.user_monthly_usage` (PK `grant_id`). |
| `models/subscriptions.py` `SubscriptionPlan`, `SubscriptionPlanType` | `core.subscription_plan` enum | **Delete.** Cascades into `config.py`, `models/api.py`, `services/firebase.py`. |
| `models/subscriptions.py` `SubscriptionEvent` | `core.subscription_events` | **Delete.** The v2.0 schema has `audit.subscription_events`, a different table owned by Phase 43. |
| `models/subscriptions.py` `Subscription` | shape changed | **Delete** with `database/subscriptions.py` (D-16). |
| `models/api.py` `UserProfileResponse` | `SubscriptionPlan` | **Delete** with `GET /users/me`. |
| `models/api.py` `ErrorResponse` | `ErrorCode` Literal from `exceptions.py` | **Move** to the registry at package root (D-09/D-10). |
| `database/usage.py`, `database/subscriptions.py` | both | **Delete** (D-16). |
| `database/users.py` `UsersDB.get_or_create` | `jwt_sub` | **Delete** — JIT provisioning is gone in v2.0; only `POST /auth/create-user` creates accounts. Replace with the barrier's single `(issuer, subject)` resolution query in `auth/identity.py`. |
| `services/subscriptions.py`, `services/users.py` | both | **Delete** (D-16). |
| `services/firebase.py` `set_plan_claim` | `SubscriptionPlan`; also the v1.5 claim-sync path | **Delete** — no plan claim exists in v2.0, and SHARED-INVARIANTS forbids rederiving provider from claims. |
| `routers/webhooks.py` | `SubscriptionService` | **Delete** (D-16); Phase 43 writes `/webhooks/app-store` from scratch. |
| `routers/users.py` `GET /users/me` | `user.name`, `user.subscription_plan`, `UsageDB` | **Delete** — it uses three dropped structures, so it *cannot* serve unchanged. This resolves the open discretion item. Phase 39 rewrites it. |
| `config.py` `AppleConfig`, `AppConfig.quotas`, `AppConfig.apple` | `SubscriptionPlan` | **Delete**, plus the `apple:` and `quotas:` blocks from `config/config.yaml`. Allowance in v2.0 comes from `core.access_tiers.monthly_credits`, not config. |
| `app/lifespan.py` `create_apple_verifier`, `FirebaseService` construction | deleted services | **Repair** — remove both; add keyring validation and the enumeration assertion. |
| `app/dependencies.py` `get_current_user`, `require_quota`, `get_subscription_service` | all | **Delete** → replaced by D-02 accessors. |
| `routers/chats.py` | `Depends(get_current_user)`, `Depends(require_quota)` | **Repair-lite** — swap to `Depends(get_linked_identity)`; leave quota wiring to Phase 36 (D-15). |
| `services/chats.py` `create_chat(user=...)`, `send_message(user=...)` | takes a `User` | **Repair** signature to take `user_id: UUID`. |
| `tests/e2e/conftest.py::create_chat` | `User(jwt_sub=…)` | **Repair** — must seed `core.users` **and** a matching `core.external_identities` row. |
| `app/main.py` | — | **Repair** — D-04 docs off, D-03 middleware order, `router.redirect_slashes = False` (§ Pitfall 6). |
| `resilience.py`, `services/llm.py`, `models/chats.py`, `models/llm.py`, `database/chats.py`, `routers/root.py`, `routers/examples.py`, `routers/health.py`, `logs.py` | none | **Untouched.** |

## Common Pitfalls

### Pitfall 1: `Headers.get("authorization")` silently satisfies a duplicate-header attack

**What goes wrong:** `§1.1` says duplicate `Authorization` field instances must reject as `duplicate_authorization`, "never resolved by taking the first or last value." A reviewer assumes `Headers.get()` comma-joins duplicates (per RFC 9110) and that a comma check therefore covers both cases.

**Why it happens:** Starlette's `Headers.get()` returns the **first** matching value and discards the rest — not a comma-joined string `[VERIFIED: executed 2026-08-20 — Headers(raw=[(b"authorization", b"Bearer a"), (b"authorization", b"Bearer b")]).get("authorization") == 'Bearer a'; .getlist("authorization") == ['Bearer a', 'Bearer b']]`.

**How to avoid:** count field instances from `scope["headers"]` (or `Headers.getlist`) and reject on `len != 1` before looking at the value at all. Only then apply the comma/fold/scheme/trailing-content checks to the single value.

**Warning signs:** any use of `request.headers["authorization"]`, `.get("authorization")`, or FastAPI's `Header(None)` alias in the barrier path. The existing `get_current_user` uses `Header(None)` `[VERIFIED: app/dependencies.py:52]` and is deleted this phase precisely for this reason.

**Bonus trap for tests:** `Headers(raw=[(b"Authorization", ...)])` — capitalized — returns `None` from `.get("authorization")`, because the raw constructor does not lowercase `[VERIFIED: executed]`. Real ASGI servers always lowercase; both httpx `ASGITransport` and Starlette `TestClient` do `[VERIFIED: executed — `AUTHORIZATION` arrived as `b'authorization'`]`. A hand-built scope in a unit test will not, so build scopes with lowercase keys or go through a real client.

### Pitfall 2: `BaseHTTPMiddleware` cannot observe anything the barrier binds

**What goes wrong:** D-03 puts `RequestLoggingMiddleware` — a `BaseHTTPMiddleware` `[VERIFIED: logs.py:57]` — outermost, and its `dispatch` logs *after* `call_next`. A plan that has the barrier bind `user_id`, `result`, or `attempt_id` to `structlog.contextvars` and expects the request log line to carry them will produce log lines that silently lack every one of those fields.

**Why it happens:** `BaseHTTPMiddleware` runs the downstream app in an anyio task-group child task, so contextvars set below it never propagate back up. `[CITED: starlette docs/middleware.md § BaseHTTPMiddleware > Limitations — "changes made in endpoints do not propagate upwards to the middleware. Furthermore, using this middleware can disrupt contextvars propagation for subsequent pure ASGI middleware in the stack."]` Empirically, after `call_next` an outer `BaseHTTPMiddleware` saw only its own binding `{'request_id': 'rid-1'}`, while an outer *pure ASGI* middleware in the same stack saw the downstream bindings too `[VERIFIED: executed 2026-08-20]`.

**How to avoid:** carry request-scoped data on `scope["state"]`, which **is** visible to an outer `BaseHTTPMiddleware` after `call_next` `[VERIFIED: executed]`. Use `structlog.contextvars` only for fields consumed *at or below* the binding point (the security log the barrier itself emits, and handler logs). If the request log line must carry identity, have `RequestLoggingMiddleware` read `request.state` after `call_next` — do **not** convert it to pure ASGI in this phase unless a plan explicitly scopes that.

**Warning signs:** an assertion in a test that the request log line contains `user_id`.

### Pitfall 3: `add_middleware` order is the reverse of reading order

**What goes wrong:** D-03 says "outermost in: `RequestLoggingMiddleware` → barrier." Written in that reading order the calls become `add_middleware(RequestLoggingMiddleware); add_middleware(AuthBarrier)` — which produces the **opposite** stack.

**Why it happens:** `add_middleware` does `self.user_middleware.insert(0, Middleware(...))` `[VERIFIED: starlette/applications.py, Starlette.add_middleware]`, so the last call is outermost. Empirically confirmed with a two-middleware stack `[VERIFIED: executed 2026-08-20]`.

**How to avoid:** call `app.add_middleware(AuthBarrierMiddleware)` **first**, then `app.add_middleware(RequestLoggingMiddleware)`. Add a test asserting `[type(m.cls).__name__ for m in app.user_middleware]` order, since the mistake is invisible at runtime except through log-field absence.

**Second trap:** `add_middleware` raises `RuntimeError("Cannot add middleware after an application has started")` once `middleware_stack` is built `[VERIFIED: same source]`. All `add_middleware` calls must stay at module scope in `main.py`, never in the lifespan.

### Pitfall 4: D-14 makes the enumeration assertion fail unless the pre-existing routes are declared

**What goes wrong:** the phase boundary says `§8` (rebinding) is Phase 36, so a planner declares only the empty foundation registry. Startup then aborts: eight registered routes, zero declared entries — `§2.3` failure condition 1, eight times over.

**Why it happens:** `§2.3` is a *set-equality* check on the **actual router**, and D-14 makes it run at real startup. The moment the assertion is real, the registry must cover whatever is registered.

**How to avoid:** Phase 35 declares all eight surviving routes with the `§8.1` metadata — `GET /health/ready` → `public`; `GET /`, `GET /examples`, and the six `/chats` entries → `authenticated`; all with `operation=None, preauth_callable=False, challenge_bearing=False, named_verifier=None, quota_checked` per `§8.4`. **This is REBIND-01 landing in Phase 35.** Record it as a fourth scope move alongside D-05/D-08/D-14 and update `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` before planning. It pulls in *only* the declaration — REBIND-02, REBIND-03, and REBIND-05 stay in Phase 36.

**Warning signs:** a plan whose registry module contains only comments, or an assertion implemented as "every declared route is registered" without the reverse.

### Pitfall 5: caching `app.state` in the barrier's `__init__` breaks every e2e test

**What goes wrong:** the barrier is constructed once, at `add_middleware` time — before the lifespan has run. Capturing `app.state.session_factory` there yields either an `AttributeError` at construction or, worse, the *production* factory, which the e2e rollback fixture then cannot swap.

**Why it happens:** `tests/e2e/conftest.py::_db_transaction` works by reassigning `_app_lifespan.state.session_factory` to a connection-bound `async_sessionmaker(..., join_transaction_mode="create_savepoint")` and restoring it afterwards `[VERIFIED: tests/e2e/conftest.py:66-89]`. Anything that read the attribute earlier keeps the old object, writes to the real database, and never rolls back.

**How to avoid:** read `scope["app"].state.session_factory` (and `.config`, `.jwt_verifier`, `.challenge_store`, `.audit_writer`, `.hmac_keyring`) **per request**. The same rule applies to the audit writer's standalone mode. This is a one-line habit that makes the entire e2e strategy work; getting it wrong makes rollback isolation silently ineffective, which is far worse than a failing test.

### Pitfall 6: `redirect_slashes` gives an unauthenticated 307 the barrier never sees

**What goes wrong:** `GET /chats/` returns **307** with `Location: /chats` and no authentication `[VERIFIED: executed 2026-08-20]`, because `Router.redirect_slashes` defaults to `True` and the redirect is produced *after* the barrier passed through on "no FULL match."

**Why it happens:** the redirect branch lives in `Router.app` after the FULL/PARTIAL loop.

**How to avoid:** set `app.router.redirect_slashes = False` in `main.py`. `GET /chats/` then returns 404 `[VERIFIED: executed]`. This also makes the registered set exactly what the enumeration assertion asserts, with no shadow paths.

### Pitfall 7: FastAPI does not add `HEAD` to `APIRoute.methods`, but Starlette does add it to `Route`

**What goes wrong:** an enumerator written against Starlette's behaviour expects `{"GET", "HEAD"}` and produces a declared set with phantom `HEAD` entries; or a test asserts `HEAD /health/ready` returns 200 and gets 405.

**Why it happens:** `Route.__init__` contains `if "GET" in self.methods: self.methods.add("HEAD")`; `APIRoute.__init__` has no such line `[VERIFIED: source comparison in .venv]`. A `HEAD` request to a GET-only `APIRoute` produces `Match.PARTIAL` and a 405 `[VERIFIED: executed — "HEAD /g -> 405"]`.

**How to avoid:** enumerate exactly `route.methods` and declare exactly the same. Do not synthesize `HEAD`. Do not add a `HEAD /health/ready` declaration.

### Pitfall 8: a `SecretStr` HMAC key that is base64 in YAML and bytes in `hmac.new`

**What goes wrong:** `hmac.new(key.get_secret_value(), ...)` raises `TypeError: key: expected bytes or bytearray, but got 'str'` — or, worse, someone calls `.encode()` and derives the HMAC over the *base64 text* rather than the 32 key bytes. Both derivations "work"; only one matches whatever wrote the existing rows.

**How to avoid:** decode once, at config load, into a `bytes` keyring, and assert length ≥ 32. Never call `hmac.new` on a `str`. Pin the domain-separation prefixes as module-level `bytes` literals so they cannot drift: `b"actor-subject:v1:"` and `b"idp-account:v1:"`.

### Pitfall 9: YAML wins over env for any field it declares

**What goes wrong:** an operator tries to override a committed HMAC key with an env var and it is silently ignored.

**Why it happens:** `AppConfig` is built as `AppConfig(**yaml_data, ...)` `[VERIFIED: config.py:106-108]`, and pydantic-settings ranks `init_settings` above `env_settings`. Empirically, `HMAC_ACTIVE_VERSION=9` with `active_version: 2` in the YAML yielded `2` `[VERIFIED: executed 2026-08-20]`.

**How to avoid:** document that the YAML is authoritative for anything it declares, and that the Secret Manager follow-up must *remove* the YAML entries, not shadow them. (The good news, also verified: env values **do** fill nested fields the YAML omits — `jwt.project_id`/`jwt.api_key` from env coexist with `jwt.jwks_cache_ttl_seconds` from YAML in the same model.)

### Pitfall 10: an `internal_error` audit row is impossible for an unresolvable user

**What goes wrong:** `§1.3` says a `core.users` row with no `core.external_identities` row must "fail closed as an internal error." A writer that emits `result='internal_error'` with NULL actor fields hits the CHECK: only `'invalid_external_jwt'` may carry all-NULL actors, and every other result **requires** `actor_issuer`, `actor_subject_hash`, and `actor_subject_hash_key_version` non-NULL `[VERIFIED: migration lines 655-668]`.

**How to avoid:** at that point the token *has* been verified, so the issuer and subject are known — populate the three actor fields from the verified `(issuer, subject)`. Leave `actor_provider` NULL (no resolved identity row). The same rule applies to `preauth_identity_not_allowed`, which is emitted for an unlinked but verified subject.

## Code Examples

### 1. The wire contract, reading the raw header list

```python
# src/nativespeaker/api/auth/wire.py
from enum import StrEnum

class BoundedReason(StrEnum):            # §1.1 / §4.5 — audit + metric labels only, never client-visible
    missing_token = "missing_token"
    malformed = "malformed"
    duplicate_authorization = "duplicate_authorization"
    bad_signature = "bad_signature"
    issuer_mismatch = "issuer_mismatch"
    audience_mismatch = "audience_mismatch"
    expired = "expired"
    empty_subject = "empty_subject"

def extract_bearer(raw_headers: list[tuple[bytes, bytes]]) -> tuple[str | None, BoundedReason | None]:
    values = [v for (k, v) in raw_headers if k == b"authorization"]   # ASGI guarantees lowercase keys
    if not values:
        return None, BoundedReason.missing_token
    if len(values) > 1:
        return None, BoundedReason.duplicate_authorization
    value = values[0]
    if b"," in value or b"\n" in value or b"\r" in value:              # comma-joined or line-folded
        return None, BoundedReason.duplicate_authorization
    parts = value.split(b" ")                                          # exactly two, no trailing content
    if len(parts) != 2 or parts[0].lower() != b"bearer" or not parts[1]:
        return None, BoundedReason.malformed
    return parts[1].decode("ascii", "strict"), None                    # token bytes never normalized
```

### 2. The single identity-resolution query and the admission matrix

```python
# src/nativespeaker/api/auth/identity.py  — ONE query, ONE code path for both reject branches (D-13)
stmt = (
    select(ExternalIdentity, User)
    .join(User, col(ExternalIdentity.user_id) == col(User.id))
    .where(col(ExternalIdentity.issuer) == issuer,
           col(ExternalIdentity.subject) == subject)
)
row = (await session.exec(stmt)).first()

if row is None:                                              # outcome 1 / 1'
    return Admit(PreAuthIdentity(issuer, subject)) if meta.preauth_callable \
        else Reject("preauth_identity_not_allowed", "preauth_identity_not_allowed")

identity, user = row
if identity.identity_state != IdentityState.active:          # outcome 2 — NULL/unknown lands here too
    return Reject("account_unavailable", "historical_identity")
if user.active is not True:                                  # outcome 3 — `is not True`, not `not user.active`
    return Reject("account_unavailable", "blocked_user")
return Admit(LinkedIdentity(user=user, identity=identity, issuer=issuer, subject=subject))  # outcome 4
```

`core.identity_state` has exactly two values `[VERIFIED: migration line 57 — "CREATE TYPE core.identity_state AS ENUM ('active', 'historical');"]`; the column is `NOT NULL DEFAULT 'active'` `[VERIFIED: migration line 219]`. The `!= active` form still fails closed if a future value appears.

### 3. Route enumeration and the assertion

```python
# src/nativespeaker/api/auth/registry.py
from fastapi.routing import APIRoute, APIWebSocketRoute

def enumerate_registered(app) -> tuple[set[tuple[str, str]], list[str]]:
    registered: set[tuple[str, str]] = set()
    problems: list[str] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:            # NOTE: no synthetic HEAD (Pitfall 7)
                registered.add((method, route.path))
        elif isinstance(route, APIWebSocketRoute):
            registered.add(("WEBSOCKET", route.path))
        else:
            problems.append(f"unsupported route object registered: {type(route).__name__} {getattr(route, 'path', '?')!r}")
    return registered, problems

def assert_route_enumeration(app, registry) -> None:
    registered, problems = enumerate_registered(app)
    declared = {(e.method, e.path) for e in registry}
    if extra := registered - declared:
        problems.append(f"registered but undeclared: {sorted(extra)}")       # condition 1
    if missing := declared - registered:
        problems.append(f"declared but unregistered: {sorted(missing)}")     # condition 2 — mandatory
    # conditions 3–8 over the registry table itself: duplicate (method, path);
    # preauth_callable outside POST /auth/create-user; challenge_bearing without a
    # challenge-bearing operation; operation not a core.auth_operation value;
    # one operation on two routes; operation on a non-authenticated route;
    # provider_callback with named_verifier None / unregistered / unconfigured.
    if problems:
        raise RuntimeError("route enumeration assertion failed:\n  " + "\n  ".join(problems))
```

Condition 9 ("authenticated route outside the barrier") is satisfied *structurally* by D-01 — one middleware wraps the whole router, so no registered route can be outside it. Assert the structural fact instead: `any(m.cls is AuthBarrierMiddleware for m in app.user_middleware)`.

### 4. HMAC keyring and derivation

```yaml
# config/config.yaml  (D-20 — tracked in git; see the Secret Manager todo)
hmac:
  active_version: 1
  keys:
    1: "REPLACE-ME-base64-encoded-32-bytes"
```

```python
# src/nativespeaker/api/auth/keys.py
import base64, hashlib, hmac
from pydantic import BaseModel, Field, SecretStr, model_validator

_ACTOR_SUBJECT_PREFIX = b"actor-subject:v1:"     # §4.3 / §6.4 — pinned, never parameterized
_IDP_ACCOUNT_PREFIX   = b"idp-account:v1:"       # phase 07, its own key

class HmacConfig(BaseModel):
    # audit.auth_events.actor_subject_hash_key_version is SMALLINT
    active_version: int = Field(ge=1, le=32767)
    keys: dict[int, SecretStr]

    @model_validator(mode="after")
    def _active_key_usable(self):
        key = self.keys.get(self.active_version)          # D-22: fail closed on the ACTIVE key only
        if key is None or not key.get_secret_value().strip():
            raise ValueError(f"hmac.keys has no non-empty entry for active_version {self.active_version}")
        if len(base64.b64decode(key.get_secret_value(), validate=True)) < 32:
            raise ValueError("hmac key material must be at least 32 bytes")
        return self

class HmacKeyring:
    def __init__(self, cfg: HmacConfig) -> None:
        self._keys = {v: base64.b64decode(s.get_secret_value(), validate=True) for v, s in cfg.keys.items()}
        self.active_version = cfg.active_version

    def warn_missing_older(self, log) -> None:            # D-22: a gap is a WARNING, never fatal
        for v in range(1, self.active_version):
            if v not in self._keys:
                log.warning("hmac_key_version_missing", key_version=v)

    def actor_subject_hash(self, issuer: str, subject: str, *, version: int | None = None) -> bytes:
        key = self._keys[version if version is not None else self.active_version]
        msg = _ACTOR_SUBJECT_PREFIX + issuer.encode() + b":" + subject.encode()
        return hmac.new(key, msg, hashlib.sha256).digest()      # 32 bytes → BYTEA
```

The challenge store calls the **same** method for `preauth_subject_hash` (D-21) and stores no key version — the row has no such column, and verification uses the active key alone `[VERIFIED: migration lines 588-595 — "This row records NO HMAC key version — verification uses the current active key alone … Do NOT add a key-version column here (unlike audit.auth_events, which has one)."]`. Compare with `hmac.compare_digest`.

### 5. Claim and consume

```python
# src/nativespeaker/api/auth/challenges.py — both statements executed against the live table
async def claim(self, session, challenge_id: str, claim_attempt_id: UUID, now: datetime) -> bool:
    result = await session.exec(
        update(AuthChallenge)
        .where(col(AuthChallenge.challenge_id) == challenge_id,
               col(AuthChallenge.claimed_at).is_(None),          # still `issued`
               col(AuthChallenge.expires_at) > now)              # the ONLY expiry evaluation (§6.1)
        .values(claimed_at=now, claim_attempt_id=claim_attempt_id)
        .returning(col(AuthChallenge.id))
    )
    return len(result.all()) == 1                                # 1 on the winner, 0 on every other attempt

async def consume(self, session, challenge_id: str, claim_attempt_id: UUID, now: datetime) -> bool:
    result = await session.exec(
        update(AuthChallenge)
        .where(col(AuthChallenge.challenge_id) == challenge_id,
               col(AuthChallenge.claimed_at).is_not(None),
               col(AuthChallenge.consumed_at).is_(None),
               col(AuthChallenge.claim_attempt_id) == claim_attempt_id)   # THIS attempt only
        .values(consumed_at=now, preauth_subject_hash=None)      # both in ONE update — CHECK requires it
        .returning(col(AuthChallenge.id))
    )
    return len(result.all()) == 1
```

`[VERIFIED: executed against the live v2.0 database 2026-08-20 — "CLAIM#1 returned rows: 1 / CLAIM#2 (expect 0): 0 / CONSUME (expect 1): 1"]`

### 6. Middleware wiring in `main.py`

```python
app = FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)   # D-04
app.router.redirect_slashes = False                                   # Pitfall 6

app.include_router(root_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
register_exception_handlers(app)

app.add_middleware(AuthBarrierMiddleware)          # added FIRST  → inner
app.add_middleware(RequestLoggingMiddleware)       # added SECOND → outermost (D-03, Pitfall 3)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `BaseHTTPMiddleware` as the default middleware base | Pure ASGI middleware recommended for anything needing contextvars, early rejection, or body control | Starlette documents the limitation directly in `docs/middleware.md` | The barrier and any future security middleware should be pure ASGI. `RequestLoggingMiddleware` may stay as-is. |
| `_STATUS_REMAP` status folding (a v1.3 five-status-code artifact) | A declared class per emitted status, total by construction | Reversed by v2.0 / D-12 | Deleting the table is mandatory; the `409 → 400` entry actively collides with `challenge_required`. |
| JIT user provisioning on first authenticated request | Explicit `POST /auth/create-user` only; the barrier never creates | v2.0 schema (Phase 34) | `UsersDB.get_or_create` and `UserService` are deleted, not repaired. |
| `core.users.subscription_plan` + `config.quotas` | `core.access_grants` → `core.access_tiers.monthly_credits` | v2.0 schema | Allowance leaves the config file entirely. |
| Firebase custom-claim plan sync (v1.5) | No plan claim; the stored `provider` column is the sole classifier | v2.0 SHARED-INVARIANTS | `services/firebase.py` is deleted. |

**Deprecated/outdated:**

- `.planning/codebase/*.md` — captured 2026-02-24, describes an `app/` layout with `prompts.py` and `schema.py` that do not exist. Do not read; read the source.
- `01-foundation.md §5` in full and `§9` — superseded by D-05 and D-08 respectively.
- `SHARED-INVARIANTS.md § Rate limits` — overridden by D-05, recorded as the required conflict flag.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 405 should get its own `method_not_allowed` class rather than folding into `not_found` or `invalid_request` | § Pattern 4 | Low. Cosmetic client-contract choice; D-12 pins "honest status" but does not name the class. One line to change. |
| A2 | 415 should get **no** class because it is unreachable in this deployment | § Pattern 4 | Low, and self-correcting: adding `python-multipart` or a `Form` param would make it reachable, and the registry self-check would then fail loudly rather than silently mis-map. |
| A3 | The canonical client IP should be recorded as **bucket kind only** (`ipv4`/`ipv6`/`unresolved`) in `details.context`, read from `scope["client"]`, with the address itself omitted | § Architectural Responsibility Map | Medium. `§4.4` names "client-IP bucket kind" as a `context` field, so the kind is required; storing the address is optional. With `§9` deferred, `xff_num_trusted_hops` is unpinned so a stored address would be trusted-not-proven. If forensic value is wanted, store the address too — a one-field change. |
| A4 | `services/firebase.py` should be deleted rather than repaired | § Runtime State Inventory | Low. Its only method syncs a plan claim that no longer exists; Phase 37+ builds the `§7.1` adapter fresh. Recoverable from git. |
| A5 | HMAC key material is base64-encoded in YAML and decoded to bytes at load | § Code Example 4 | Low, but **one-way once rows exist**: changing the encoding changes every derived hash. Pin it in this phase and never revisit. |
| A6 | `router.redirect_slashes = False` is desirable | § Pitfall 6 | Low. Removes a pre-barrier 307. If any client relies on trailing-slash redirects it would break — no client exists yet. |
| A7 | The barrier passes through on `Match.PARTIAL` (405 stays the router's) rather than rejecting with `auth_required` | § Pattern 2 | Medium. `§4.1` names route/method mismatch as admission-phase, which supports pass-through, but a reviewer could read `§1.3`'s "no authenticated route may be registered outside the barrier" as covering wrong-method requests to an authenticated path. Confirm with the user if the 405-before-401 ordering matters. |

## Open Questions (RESOLVED)

All four were closed before planning finished. No question below is live for an executor.

1. **Does REBIND-01 formally move to Phase 35?**
   - What we know: D-14 makes the assertion run at real startup; `§2.3` fails on any undeclared registered route; the eight surviving routes are all registered.
   - What's unclear: whether `.planning/REQUIREMENTS.md` should re-label REBIND-01 as a Phase 35 requirement or add a FOUND-0x for it.
   - Recommendation: record it as a fourth scope move in the phase notes, mark REBIND-01 satisfied-by-35 in the traceability table, and leave REBIND-02/03/05 in Phase 36. Do this **before** planning — the planner needs the registry task in scope.
   - **RESOLVED:** by developer decision — "leave it, the planner just does the work". REBIND-01 does **not** move into Phase 35's requirement set, `.planning/REQUIREMENTS.md` is not re-labelled, no FOUND-0x is minted, and **no requirement ID tracks the declaration work**. REBIND-01 stays a Phase 36 requirement. The work itself is planned regardless: plan 01 writes the ten route declarations and the enumeration assertion, and plan 04 narrows the declared set to the surviving eight in the same commit as the router deletions.

2. **`GET /health/ready` returns a `JSONResponse` directly, not a model.**
   - What we know: `routers/health.py` returns `JSONResponse(status_code=200, content={"status": "up"})`; it is the sole public-allowlist member.
   - What's unclear: nothing blocking — noted so the planner does not "fix" it while touching the file.
   - Recommendation: leave it exactly as-is; only its registry declaration is added.
   - **RESOLVED:** recommendation adopted verbatim. Recorded in plan 04's `<recorded_assumptions>` as a standing instruction not to "fix" it while touching neighbouring files; only its registry declaration (plan 01) matters.

3. **Where do `core.access_tiers` rows come from?**
   - What we know: the migration seeds none, by design.
   - What's unclear: whether tier configuration is Phase 36's or a deployment task.
   - Recommendation: out of scope for Phase 35 (foundation reads no tier). Flag for Phase 36's discussion — REBIND-05 cannot resolve an allowance against an empty table.
   - **RESOLVED:** out of scope for Phase 35. Carried as a Phase 36 flag in plan 04's `<recorded_assumptions>` and required in plan 04's SUMMARY output, so REBIND-05's empty-table problem reaches Phase 36's discussion rather than being rediscovered at runtime.

4. **Should `RequestLoggingMiddleware` become pure ASGI?**
   - What we know: as a `BaseHTTPMiddleware` it cannot see the barrier's contextvars, and it disrupts propagation for anything pure-ASGI below it.
   - What's unclear: whether the request log line is required to carry identity fields.
   - Recommendation: do **not** convert it in this phase (D-03 pins the stack, and conversion is unscoped work). Have the barrier stash on `scope["state"]`; if the log line needs `user_id`, read `request.state` after `call_next`.
   - **RESOLVED:** recommendation adopted — no conversion this phase. Plan 06 follows it: the barrier stashes on `scope["state"]` and `RequestLoggingMiddleware` stays a `BaseHTTPMiddleware`, per D-03.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 17 | e2e tests, challenge store, audit writer | ✓ | 17 (docker-compose `postgres:17`), reachable on `localhost:5432` with the full v2.0 schema applied | — |
| Python | everything | ✓ | 3.14.7 | — |
| `.venv` with all deps | everything | ✓ | see § Standard Stack | — |
| `ruff` | lint gate | ✓ | 0.15.7 pinned — `ruff check src tests` currently reports **All checks passed!** | — |
| `ty` | type gate | ✓ | 0.0.24 pinned — `ty check src` currently reports **All checks passed!** | — |
| Firebase Identity Toolkit REST | existing `firebase_token` e2e fixture | ⚠ requires `JWT_API_KEY`, `FIREBASE_TEST_EMAIL`, `FIREBASE_TEST_PASSWORD` and network | present in `.env` | Stub `app.state.jwt_verifier` for identity-matrix tests (see § Validation Architecture) |
| Google Application Default Credentials | `firebase_admin.initialize_app(credentials.ApplicationDefault())` in the current lifespan | ✓ (lifespan ran clean) | — | This call is **removed** this phase along with `FirebaseService`, eliminating the dependency from startup |
| `python-multipart` | nothing | ✗ | — | Not needed; its absence is why 415 is unreachable |
| Redis / Valkey | nothing (D-05) | ✗ | — | Not needed |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Firebase REST for the identity matrix — use a fixture verifier over an ephemeral RSA keypair, the pattern already in `tests/unit/conftest.py`.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.2 + `pytest-asyncio` 1.3.0 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `addopts = "-v --tb=short -m 'not e2e and not schema'"`, markers `e2e` and `schema` |
| Quick run command | `.venv/bin/python -m pytest -q` (unit only — 163 tests, **2.49 s**, all green today) |
| Full suite command | `.venv/bin/python -m pytest -q -m ""` (273 collected: 163 unit + 33 e2e + 77 schema) |
| Lint / type gate | `.venv/bin/ruff check src tests && .venv/bin/ty check src` — both green today |

Conventions new files must follow `[VERIFIED: tests/e2e/test_health.py:1-5]`: e2e modules set `pytestmark = pytest.mark.e2e` at module level and decorate classes with `@pytest.mark.asyncio(loop_scope="module")`, matching the module-scoped `_app_lifespan` fixture. A new e2e module that omits `loop_scope="module"` will bind to the wrong event loop.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | Four-outcome admission matrix: linked-active admits; pre-auth on a non-preauth route → `preauth_identity_not_allowed`; `identity_state != 'active'` → `account_unavailable`; `users.active IS NOT TRUE` → `account_unavailable` | e2e | `pytest -m e2e tests/e2e/test_barrier_admission.py -x` | ❌ Wave 0 |
| FOUND-01 | A route reached with no identity context fails loudly as `auth_required` (D-02 accessors raise) | unit | `pytest tests/unit/test_identity_accessors.py -x` | ❌ Wave 0 |
| FOUND-02 | Zero / duplicate-instance / differently-cased-duplicate / comma-joined / empty-token / trailing-content each reject with **identical** status, body, and copy | unit | `pytest tests/unit/test_barrier_wire_contract.py -x` | ❌ Wave 0 |
| FOUND-02 | The same six cases over a real ASGI transport (proves duplicates survive the wire) | e2e | `pytest -m e2e tests/e2e/test_barrier_wire_contract.py -x` | ❌ Wave 0 |
| FOUND-03 | Set-equality assertion passes for the real app; a route in zero categories fails; a route in two fails; declared-but-unregistered fails; all nine `§2.3` conditions | unit | `pytest tests/unit/test_route_registry.py -x` | ❌ Wave 0 |
| FOUND-03 | The assertion executes at **real startup** against the **real router** (success criterion 5) | e2e | `pytest -m e2e tests/e2e/test_startup_assertion.py -x` | ❌ Wave 0 |
| FOUND-04 | Registry totality: every declared class has exactly one status; no two classes share a code; `unauthorized` is absent; `_STATUS_REMAP` is gone; 404/405/422/500 each map to exactly one declared class | unit | `pytest tests/unit/test_error_registry.py -x` | ❌ Wave 0 (extend `test_error_contract.py`) |
| FOUND-05 | A barrier rejection produces exactly **one** `audit.auth_events` row with all three actor fields NULL and a bounded reason in `details.failure` (success criterion 4) | e2e | `pytest -m e2e tests/e2e/test_audit_writer.py -x` | ❌ Wave 0 |
| FOUND-05 | `details` top-level shape is exactly `{schema_version, context, verification, resolved, mutation, failure}`; redaction drops raw tokens and the public `challenge_id` | unit | `pytest tests/unit/test_audit_details.py -x` | ❌ Wave 0 |
| FOUND-05 | `actor_subject_hash` is 32 bytes, stable for a fixed `(key, issuer, subject)`, and differs across key versions | unit | `pytest tests/unit/test_hmac_keys.py -x` | ❌ Wave 0 |
| FOUND-06 | `check_all` is non-destructive; nothing is charged when any budget is exhausted; all charge together on success; broadest-to-narrowest order; exhaustion → `firebase_lookup_unavailable` | unit | `pytest tests/unit/test_budgets.py -x` | ❌ Wave 0 |
| FOUND-07 | Claim is atomic: exactly one of N concurrent claims wins; an expired row rejects `challenge_expired`; a claimed row rejects `challenge_consumed`; consume requires **this** `claim_attempt_id`; consume clears `preauth_subject_hash` | e2e | `pytest -m e2e tests/e2e/test_challenge_store.py -x` | ❌ Wave 0 |
| FOUND-07 | `challenge_id` is 16 CSPRNG bytes base64url-unpadded; TTL is exactly 300 s from the server clock; `locate` compares byte-for-byte | unit | `pytest tests/unit/test_challenge_ids.py -x` | ❌ Wave 0 |
| FOUND-08 | Adapter module declares interfaces only — no `firebase_admin` import, no concrete class | unit | `pytest tests/unit/test_adapter_interfaces.py -x` | ❌ Wave 0 |
| D-22 | Missing/empty **active** key aborts config load; a missing **older** version only warns | unit | `pytest tests/unit/test_hmac_keys.py -x` | ❌ Wave 0 |
| D-03 | Middleware order is `[RequestLoggingMiddleware, AuthBarrierMiddleware]` outermost-first | unit | `pytest tests/unit/test_app_wiring.py -x` | ❌ Wave 0 |
| D-14 | `import nativespeaker.api.app.main` succeeds and the lifespan runs clean | e2e | `pytest -m e2e tests/e2e/test_startup_assertion.py -x` | ❌ Wave 0 |
| D-18 | Whole suite green with no xfail | all | `pytest -q -m "" && ruff check src tests && ty check src` | ✓ (gate exists) |

### Sampling Rate

- **Per task commit:** `.venv/bin/python -m pytest -q` (unit only, ~2.5 s) plus `ruff check src tests`.
- **Per wave merge:** `.venv/bin/python -m pytest -q -m ""` (unit + e2e + schema) plus `ty check src`.
- **Phase gate:** full suite green, zero xfail, `ruff` and `ty` clean, and the real app starts — before `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] `tests/unit/test_barrier_wire_contract.py` — FOUND-02
- [ ] `tests/unit/test_route_registry.py` — FOUND-03 (all nine conditions)
- [ ] `tests/unit/test_error_registry.py` — FOUND-04 (or extend `test_error_contract.py`)
- [ ] `tests/unit/test_audit_details.py` — FOUND-05 (shape + redaction)
- [ ] `tests/unit/test_hmac_keys.py` — FOUND-05, D-21, D-22
- [ ] `tests/unit/test_budgets.py` — FOUND-06
- [ ] `tests/unit/test_challenge_ids.py` — FOUND-07 (pure logic)
- [ ] `tests/unit/test_adapter_interfaces.py` — FOUND-08
- [ ] `tests/unit/test_identity_accessors.py` — FOUND-01 fail-loudly
- [ ] `tests/unit/test_app_wiring.py` — D-03, D-04
- [ ] `tests/e2e/test_barrier_admission.py` — FOUND-01 four-outcome matrix
- [ ] `tests/e2e/test_barrier_wire_contract.py` — FOUND-02 over the wire
- [ ] `tests/e2e/test_startup_assertion.py` — FOUND-03 + D-14
- [ ] `tests/e2e/test_audit_writer.py` — FOUND-05
- [ ] `tests/e2e/test_challenge_store.py` — FOUND-07 atomicity
- [ ] `tests/e2e/conftest.py` — **extend**, do not replace: add a `seed_identity(state, user_active)` helper writing `core.users` + `core.external_identities`, and a `stub_verifier` fixture that swaps `app.state.jwt_verifier` for the ephemeral-RSA verifier so four distinct subjects can be exercised without four Firebase accounts. Repair the existing `create_chat` helper (it builds `User(jwt_sub=…)`).
- [ ] **Delete** (D-18): `tests/unit/test_usage.py`, `tests/unit/test_subscriptions.py`, `tests/unit/test_webhooks.py`, `tests/e2e/test_users.py`, and the `/users/me` cases in `tests/unit/test_users.py`. **Narrow**: `tests/unit/test_auth_security.py`, `tests/unit/test_exception_handlers.py`, `tests/unit/conftest.py` (drop `TEST_USER`, `mock_usage_db`, `webhook_client`, the `get_current_user`/`require_quota` overrides), `tests/e2e/test_error_cases.py`, `tests/e2e/test_chats.py`, `tests/e2e/test_chat_queries.py`, `tests/e2e/test_isolation.py`.
- [ ] Framework install: **none** — pytest, pytest-asyncio, and httpx are installed.

**Two properties that make the existing e2e harness work unchanged**, both verified:
1. `_db_transaction` swaps `app.state.session_factory` for a connection-bound factory with `join_transaction_mode="create_savepoint"` `[VERIFIED: tests/e2e/conftest.py:66-89]`. Because D-19 routes the barrier and audit writer through that same attribute, both land inside the per-test rollback — **provided** neither caches it (§ Pitfall 5). A standalone-durable audit `commit()` under `create_savepoint` releases a savepoint, not the outer transaction, so the row is visible to a session on the same connection and still rolls back. Assertions must therefore read through the swapped `test_factory`, not a fresh engine.
2. httpx `ASGITransport` and Starlette `TestClient` both deliver duplicate, differently-cased, and comma-joined `Authorization` fields to `scope["headers"]` byte-for-byte `[VERIFIED: executed 2026-08-20]`, so the wire-contract matrix is exercisable through the ordinary client.

## Security Domain

`security_enforcement` is not disabled in `.planning/config.json`, so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | External IdP (Firebase) RS256 over cached JWKS; `PyJWT[crypto]` + `PyJWKClient`; `iss`/`aud` pinned to the one configured integration; no backend-minted credential |
| V3 Session Management | **no by design** | SHARED-INVARIANTS: no backend session, no cookie, no token minting. Per-request ID token only. Nothing to build; the absence is the control. |
| V4 Access Control | yes | The barrier as the single enforcement point; fail-closed default with pre-auth as an explicit per-route allowlist; the enumeration assertion proves no route escapes the partition |
| V5 Input Validation | yes | Pydantic v2 request models (already in place); the `§6.5` syntactic mode-signal check; the wire contract as byte-level input validation |
| V6 Cryptography | yes | stdlib `hmac`/`hashlib` for HMAC-SHA-256; `secrets.token_bytes` for the challenge CSPRNG; `hmac.compare_digest` for binding verification. **Never hand-roll.** |
| V7 Error Handling & Logging | yes | One registry, identical body/status/copy per class; internal `core.auth_event_result` never client-visible; `audit.auth_events` append-only; redaction before write |
| V8 Data Protection | yes | Raw subjects never stored outside `core.external_identities` (the deliberate, documented exception); `SecretStr` for key material; `challenge_id` body-only |
| V9 Communications | no | TLS terminates at Envoy; nothing in this phase |
| V13 API & Web Service | yes | The three-way route partition; provider-callback membership by exact path only, never wildcard |

### Known Threat Patterns for FastAPI + PostgreSQL + external IdP

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Duplicate/ambiguous `Authorization` header desync between gateway and backend | Spoofing | The wire contract rejects before either layer picks a value; count instances from `scope["headers"]`, never `.get()` |
| Token confusion across Firebase projects | Spoofing | `iss` and `aud` pinned to exactly one configured integration; issuer mismatch rejects before any Admin client selection |
| Algorithm confusion (`alg: none`, HS256-with-public-key) | Spoofing | `algorithms=["RS256"]` explicitly; `tests/unit/test_jwt_security.py` already covers this — **keep those tests** |
| Enumeration oracle: distinguishing "retired" from "blocked" from "never existed" | Information disclosure | `account_unavailable` covers both retired and blocked with identical status/body/copy through the same single query (D-13); timing is explicitly not normalized and the omission is documented |
| Challenge replay / double-spend | Tampering | One atomic conditional `UPDATE` as the sole serialization point; one-way `issued → claimed → consumed`; a claimed challenge is dead |
| Capability-handle leakage | Information disclosure | The public `challenge_id` never enters URLs, audit rows, logs, traces, analytics, or error text; correlate on `core.auth_challenges.id` |
| Audit log as a secret archive | Information disclosure | Redaction before write; HMAC-hashed subjects; schema CHECKs enforce the `details` shape and the all-or-nothing actor rule |
| Committed key material | Information disclosure | **Accepted risk** per D-20, with the Secret Manager follow-up as the mitigation path. Use a placeholder in the committed YAML and generate the real key at deploy time where possible |
| SQL injection | Tampering | ORM constructs only; zero raw `text()` (v1.6 convention, held by D-19) |
| Unauthenticated schema disclosure via `/docs`, `/openapi.json` | Information disclosure | D-04 turns all four off; `app.routes == []` before `include_router` `[VERIFIED]` |
| Unauthenticated 307 leaking route existence | Information disclosure | `router.redirect_slashes = False` (§ Pitfall 6) |

## Sources

### Primary (HIGH confidence)

- **This repository's `.venv`, executed 2026-08-20** — `fastapi/routing.py` (`APIRoute.matches` / `APIWebSocketRoute.matches` at lines 800-804 and 994-998; `APIRoute.__init__` method handling), `starlette/routing.py` (`Match` enum lines 40-43; `Route.__init__` HEAD addition; `Route.handle` 405 raise at lines 283-285), `starlette/applications.py` (`build_middleware_stack` lines 74-94; `add_middleware`), `starlette/middleware/exceptions.py`. Plus twelve executed probe scripts covering: `app.routes` contents with and without docs; middleware ordering; `scope["route"]` availability; `scope["state"]` propagation; contextvars propagation for both middleware kinds; exception routing from middleware; `Headers.get`/`getlist`; `QueryParams.getlist`; duplicate-header survival through `ASGITransport` and `TestClient`; `redirect_slashes`; `path` vs `path_format`; pydantic-settings YAML/env layering.
- **`migrations/20260818_01_initial-release.sql`** (the applied v2.0 schema) — enum values (lines 48-138), `core.users` (150-158), `core.external_identities` (206-246), `core.access_grants` (376-424), `core.user_monthly_usage` (562-570), `core.auth_challenges` (575-635), `audit.auth_events` (641-670).
- **The live development database** (`localhost:5432`, PostgreSQL 17) — table inventory via `information_schema`; the claim/consume conditional `UPDATE` pair executed end-to-end against the real `core.auth_challenges`.
- **Context7 `/kludex/starlette`** — `Router.app` route-iteration loop, `Route.matches`, `Mount.matches`, `BaseHTTPMiddleware` limitations and `_CachedRequest` body lifecycle, pure-ASGI middleware guidance.
- **Context7 `/pydantic/pydantic-settings`** — nested-model loading, `YamlConfigSettingsSource`, `SecretStr` in nested models.
- **`/home/init/native-speaker/specs/auth-refactor-phases/01-foundation.md`** and **`SHARED-INVARIANTS.md`** — the binding specification.

### Secondary (MEDIUM confidence)

- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/phases/34-schema/34-CONTEXT.md`, `.planning/todos/pending/secret-manager-integration.md` — already updated for D-05/D-06/D-08/D-14/D-15; REBIND-01 is the remaining edit.

### Tertiary (LOW confidence)

- None. No claim in this document rests on web search or unverified training knowledge; the seven `[ASSUMED]`-class items are recorded in the Assumptions Log as recommendations rather than facts.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — every version read from the installed distribution; no new package.
- Architecture (barrier mechanics, route enumeration, error registry, challenge protocol): **HIGH** — each behavioural claim executed in this environment, and the two most consequential (`scope["route"]` absence, exception-handler bypass) confirmed both by source reading and by running them.
- Boot-repair surface: **HIGH** — import and lifespan executed; the failing queries executed against the live schema; the module dispositions derive from an exhaustive grep of the five dropped structures.
- Pitfalls: **HIGH** — nine of the ten were reproduced; Pitfall 10 is read directly off the migration's CHECK constraint.
- Test-seam compatibility: **HIGH** for the fixture mechanics (read from `tests/e2e/conftest.py`) and header transport (executed); **MEDIUM** for the recommended stub-verifier split, which is a design proposal not yet built.
- Assumptions A1–A7: **LOW by construction** — these are the discretion items, offered as recommendations for the planner or the user to confirm.

**Research date:** 2026-08-20
**Valid until:** 2026-09-19 (30 days — `fastapi` is `==`-pinned and `starlette` is transitively frozen by `uv.lock`, so the verified framework behaviour cannot drift without a deliberate lock update)
