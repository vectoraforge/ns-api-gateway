# Phase 39: GET /users/me - Research

**Researched:** 2026-09-01
**Domain:** One read-only authenticated FastAPI route over two already-loaded ORM rows and one new `crud/` query
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: The shape.** `profile` is a nested block; `identity_provider` and `purchase_tokens` sit
  beside it at top level. `purchase_tokens` is an object keyed by store provider whose values are
  the bare token strings.

  ```json
  {"profile": {"email": "a@b.com", "display_name": "Ada"},
   "identity_provider": "google",
   "purchase_tokens": {"apple": "…", "google_play": "…"}}
  ```

  **The body carries nothing else** — no `user_id`, no `registered_at`.
  — **Reversibility:** one-way — a published client contract. The iOS client reads the `apple`
  value and passes that exact string into StoreKit at purchase time; `GET /users/me` and
  `/auth/sync` must also keep reporting the same `identity_provider` value (Phase 38 D-06).

- **D-02: Every store's token ships on every request, with no platform condition. Not open —
  recorded here so a planner does not reopen it.** This is PROF-01 and roadmap success criterion 1.
  Branching would let a client-supplied signal (User-Agent, an `X-Platform`-style header, a query
  parameter, a body flag) decide what the server reads and returns, and this codebase forbids that
  class of thing everywhere else.

- **D-03: Profile fields come from the barrier's already-resolved row. No second query.**
  `get_linked_identity` returns an `Identity` carrying the loaded `User` row, and
  `app/lifespan.py:36` sets `expire_on_commit=False`, so `identity.user.email` and
  `identity.user.display_name` stay readable after the barrier's short session closes. The purchase-
  token read is therefore the request's **only** query. This is a **deliberate divergence from the
  brief's literal handler step 1** and belongs in `.planning/REQUIREMENTS.md` as a dated amendment.

- **D-04: The purchase-token query lives in a new `crud/purchases.py`.** It pairs with
  `tables/purchases.py`. Reading tokens is not identity work, so it does not widen `IdentitiesDB`.

- **D-05: No service layer for this endpoint — the router calls `crud/` directly — and `AGENTS.md`
  is amended to state the general rule.** The developer's rule, to be written into `AGENTS.md`
  § "Package layout": a router may call `crud/` directly; a `services/` class is introduced when the
  router body would otherwise become too big or complicated. Existing services are not refactored.
  — **Reversibility:** costly — a repo-wide convention binding every later phase's layering.

- **D-06: A missing token row raises a new `MissingPurchaseTokenError`.** An `InternalError`
  subclass at `log_level = logging.ERROR`, sitting beside `MissingUsageRowError`,
  `MultipleEffectiveGrantsError` and `UnknownTierError` and following their exact pattern.
  **It carries `user_id` and the missing provider(s)** — **neither value is the token, so invariant
  10's redaction rule is untouched: `identity_value` must never enter the exception message or any
  log field.** Per `AGENTS.md` § Package layout exception 4, the raise stays with the query in
  `crud/purchases.py`.

- **D-07: Completeness is checked against the `PurchaseProvider` enum — one row required per
  member.** Not "zero rows returned". **Known consequence, accepted:** adding a third store later
  makes every pre-existing account fail closed until its rows are backfilled. Never lazily minted.

- **D-08: A new `routers/users.py`, with `Depends(get_linked_identity)` at router level.** Requires
  an export in `routers/__init__.py` and an `include_router` call in `app/main.py`.

- **D-09: The response carries `Cache-Control: no-store`.** Set through an injected `Response` so
  the handler keeps returning the typed model rather than hand-building a `JSONResponse`.

- **D-10: No test asserting the token is absent from logs.** The redaction obligation is met by
  D-06's constraint on the exception message instead.

**Carried forward — decided in earlier phases, binding here, do NOT rebuild:** no `audit.auth_events`
row and nothing to write one with; no bounded-cardinality counter metric; no `users_me` rate-limit
entry and no rate-limit engine; no route registry and no startup enumeration assertion; no new
client-visible error class; no success log line; the phase briefs under `specs/auth-refactor-phases/`
are marked verbatim and are NOT edited.

### Claude's Discretion

- The `crud/purchases.py` class and method names, and whether the completeness check reads as a dict
  comprehension over the enum or an explicit set difference.
- How `tests/unit/test_app_wiring.py` gains its `/users/me` assertions (two parallel tests, a
  parametrised pair, or a widened generic assertion).
- Test placement and depth, within the existing `tests/unit` + `tests/e2e` split.
- The exact wording of the `AGENTS.md` § "Package layout" amendment required by D-05.

### Deferred Ideas (OUT OF SCOPE)

- `user_id` and `registered_at` in the profile payload.
- Restoring rate limiting to the auth and `/users` surface.
- A test asserting the purchase token never reaches a log line.
- Refactoring existing services under D-05's new rule.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROF-01 | The endpoint returns profile fields, the stored `identity_provider`, and per-store purchase-attribution tokens unconditionally for every store provider, with no platform or client-signal branching | Standard Stack (no new deps); Architecture Patterns 1–3; Code Examples 1–4; Pitfalls 1, 4, 5; the enum-keyed-dict shape verified to serialize to exactly the two enum values |
| PROF-02 | The endpoint is off the audited attempt path and writes no `audit.auth_events` row ever; rejections keep their stable internal result in the structured security log instead | Trivially true and inherited — verified that no `audit.auth_events` table, writer or call site exists and that `tests/unit/test_sync_audit_removal.py` already guards a rebuild; the compensating log lines are `RequestLoggingMiddleware`'s `request` line plus one WARNING/ERROR per raised `AppError` |
</phase_requirements>

## Summary

This is a small phase with a large surrounding contract. Every mechanism the endpoint needs already
exists and has an in-repo precedent: the barrier (`app/dependencies.py::get_linked_identity`) raises
all four rejections the route owes; `routers/auth.py::sync` is a line-for-line template for the
handler; `crud/grants.py` is the template for the new `crud/purchases.py`; `errors.py`'s
`MissingUsageRowError` is the exact template for `MissingPurchaseTokenError`; and
`routers/auth.py::issue_challenge` is the `Cache-Control: no-store` precedent. **No new dependency,
no schema change, no migration, and no service class.** The work is one new router module, one new
crud module, two new schema models, one new error class, three wiring edits, one `AGENTS.md`
amendment, and tests.

The two load-bearing premises were verified by execution rather than inferred. **D-03 holds:**
against the real database, `identity.user.email` and `identity.user.display_name` read correctly
*after* the barrier's short session closes, because `app/lifespan.py:34-36` builds the factory with
`expire_on_commit=False` and the barrier never commits. **D-01's wire shape holds:** a Pydantic
`dict[PurchaseProvider, str]` serializes to exactly `{"apple": …, "google_play": …}` in both
`model_dump(mode="json")` and the HTTP body, and FastAPI generates a valid OpenAPI schema for it
(`propertyNames: $ref PurchaseProvider`). An injected `Response` sets `Cache-Control: no-store`
while the handler still returns the typed model under `response_model`.

The largest planning risk is not the endpoint — it is three **ratchet literals** that a new error
class and a new route will break in files the phase does not otherwise touch, and one **test-fixture
gap**: `tests/e2e/conftest.py::seed_identity` inserts a user and an identity row and **no purchase
tokens at all**, so an e2e happy path needs new seeding while the fail-closed case is the existing
helper's default behaviour.

**Primary recommendation:** Model the handler on `routers/auth.py::sync` and the query on
`crud/grants.py::read_usage`; check completeness against `set(PurchaseProvider)` inside
`crud/purchases.py` and raise `MissingPurchaseTokenError(user_id, missing)` there; and treat the
three ratchet literals (`EVENT_NAMES`, `CONSTRUCTOR_ARGUMENTS`, `test_app_wiring.py`'s path sets) as
first-class plan tasks in the same commit as the code that trips them.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| JWT acceptance and identity resolution | API — `app/dependencies.py::get_identity` | — | `SHARED-INVARIANTS.md` § The barrier: the only place identity happens; the handler never re-verifies |
| Narrowing to a linked caller (403 for unlinked) | API — `app/dependencies.py::get_linked_identity` | Router-level `dependencies=[...]` (D-08) | Declared once on the router so every future `/users/*` route inherits it |
| Profile field supply (`email`, `display_name`) | API — the barrier's already-loaded `User` row (D-03) | — | Row was loaded from `core.users` in this request; a second read buys no freshness (no path in this milestone edits either field) |
| Registration state (`identity_provider`) | Database — stored `core.external_identities.provider`, read via the barrier's `ExternalIdentity` row | — | § Identity and ownership: the stored column is the sole per-request classifier; never rederived from claims or headers |
| Purchase-token read | Database — new `crud/purchases.py` | — | `AGENTS.md` § Package layout: `crud/` owns database access |
| Completeness check + fail-closed raise | `crud/` (with the query) | — | `AGENTS.md` § Package layout exception 4: a fail-closed read may raise its own rejection, so the rejection stays with the query |
| Response assembly + `Cache-Control` | API — `routers/users.py` | — | D-05: the router calls `crud/` directly; D-09 sets the header via an injected `Response` |
| Client-visible status/code/body | `errors.py` + `app/error_handlers.py` | — | § Errors: one shared module owns the shape, statuses and copy |
| Rate limiting | **Gateway (Envoy) only** | — | Phase 35 D-05 deleted the backend engine from the product; `AGENTS.md` § Resilience |
| Attempt telemetry | `logs.py::RequestLoggingMiddleware` | `app/error_handlers.py::app_error_handler` | PROF-02: no durable row, no counter; one `request` line per attempt plus one log line per raised `AppError` |

## Standard Stack

### Core

**No new dependency is added by this phase.** Everything below is already installed and in use.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.135.1 | Route declaration, `Depends()`, `response_model`, injected `Response` | Already the app's framework [VERIFIED: `pyproject.toml:6`, `uv run python -c "import fastapi"` → `fastapi 0.135.1`] |
| pydantic | 2.12.5 | The two new response models | Already every `schemas/` body [VERIFIED: executed `import pydantic; pydantic.VERSION` → `2.12.5`] |
| sqlmodel | 0.0.37 | The `select()` in `crud/purchases.py` | Every `crud/` module uses it [VERIFIED: executed `sqlmodel.__version__` → `0.0.37`] |
| structlog | ≥25.5 | The one ERROR line `MissingPurchaseTokenError` earns via `app_error_handler` | The app's logging pipeline [VERIFIED: `pyproject.toml:22`] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest / pytest-asyncio | 9.0.2 / 1.3.0 | Unit, e2e and schema suites | All test work [VERIFIED: `uv run pytest -q` header — `plugins: cov-7.0.0, langsmith-0.7.5, anyio-4.12.1, asyncio-1.3.0, dotenv-0.5.2`] |
| httpx | ≥0.28 | `AsyncClient` + `ASGITransport` in `tests/e2e` | E2E route tests [VERIFIED: `pyproject.toml:34`, used at `tests/e2e/conftest.py:99-104`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Router calls `crud/` directly (D-05) | A `ProfileService` in `services/` | Rejected by the developer: the service would hold one awaited read and nothing else — the shape `AGENTS.md` § Function shape says to inline. **Locked; do not reopen.** |
| Injected `Response` for the header (D-09) | Hand-built `JSONResponse` (the `issue_challenge` precedent at `routers/auth.py:57-59`) | The `JSONResponse` form loses the typed return and the `response_model` OpenAPI entry. D-09 explicitly prefers the injected `Response`; **verified working** under `response_model` (Code Example 4). |
| `dict[PurchaseProvider, str]` (D-01) | A list of `{provider, token}` entries, or per-store fields | Rejected in discussion: the keyed object makes "an entry for every store" structurally evident and lets the client index rather than scan. **Locked.** |

**Installation:** none. `uv sync` already satisfies this phase.

## Package Legitimacy Audit

**Not applicable — this phase installs no external package.** No addition to `pyproject.toml`
dependencies or dependency-groups is in scope, so there is nothing to check against a registry.

- Packages removed due to `[SLOP]` verdict: none
- Packages flagged as suspicious `[SUS]`: none

If a plan proposes any new dependency, that alone is a scope breach against the phase boundary
(CONTEXT.md § Phase Boundary lists no dependency work) and should be rejected rather than audited.

## Architecture Patterns

### System Architecture Diagram

```
GET /users/me   (Authorization: Bearer <Firebase ID token>)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ RequestLoggingMiddleware  (logs.py)                             │
│   emits exactly one `request` line per attempt on the way out   │
└───────────────┬─────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ Router-level Depends(get_linked_identity)   [D-08]              │
│   ├── HTTPBearer(auto_error=False) → no credential ─► 401 auth_required
│   ├── jwt_verifier.verify (threadpool)  → bad token ─► 401 auth_required
│   ├── IdentitiesDB.resolve  (its OWN short session, then CLOSED)│
│   │      ├── no row          ─► (allow_preauth) unlinked Identity
│   │      ├── user is None    ─► 500 internal_error  (IdentityUnresolvable)
│   │      ├── state≠active    ─► 403 account_unavailable
│   │      └── user.active≠True─► 403 account_unavailable
│   └── unlinked               ─► 403 preauth_identity_not_allowed
└───────────────┬─────────────────────────────────────────────────┘
                │  Identity(user=<User row>, identity=<ExternalIdentity row>)
                │  ── rows stay readable while DETACHED: expire_on_commit=False
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ routers/users.py::me   (handler — no service layer, D-05)       │
│   profile ◄── identity.user.email / .display_name      [D-03]   │
│   identity_provider ◄── identity.identity.provider     [D-03]   │
│   response.headers["Cache-Control"] = "no-store"       [D-09]   │
└───────────────┬─────────────────────────────────────────────────┘
                ▼  Depends(get_db)  ── the request's ONE query
┌─────────────────────────────────────────────────────────────────┐
│ crud/purchases.py                                               │
│   SELECT provider, identity_value                               │
│     FROM core.store_purchase_tokens WHERE user_id = :id         │
│   completeness := set(rows.keys()) == set(PurchaseProvider)     │
│        ├── complete ─► {apple: "…", google_play: "…"}           │
│        └── missing  ─► raise MissingPurchaseTokenError   [D-06] │
└───────────────┬─────────────────────────────────────────────────┘
                ▼
        200  {"profile": {...}, "identity_provider": "...",
              "purchase_tokens": {"apple": "...", "google_play": "..."}}
        500  {"code": "internal_error"}   + one ERROR log line

  NOT ON ANY PATH: audit row · counter metric · rate limiter · lock ·
                   provider call · clock read · write of any kind
```

### Component Responsibilities

| File | Status | Responsibility |
|------|--------|----------------|
| `src/nativespeaker/api/routers/users.py` | **new** (D-08) | The handler, the router-level narrowing, the `Cache-Control` header |
| `src/nativespeaker/api/routers/__init__.py` | edit | Export `users_router` — `__all__` at `:1` is a literal list [VERIFIED: `routers/__init__.py:1-7`] |
| `src/nativespeaker/api/app/main.py` | edit | `app.include_router(users_router)` beside the five existing calls [VERIFIED: `app/main.py:43-47`] |
| `src/nativespeaker/api/schemas/auth.py` | edit | The profile block and the response model, beside `SyncResponse` at `:60-63` |
| `src/nativespeaker/api/crud/purchases.py` | **new** (D-04) | The one query, the completeness check, the fail-closed raise |
| `src/nativespeaker/api/crud/__init__.py` | edit | Export the new class — `__all__` at `:1` is a literal [VERIFIED: `crud/__init__.py:1`] |
| `src/nativespeaker/api/app/dependencies.py` | edit | The accessor the router `Depends()` on (see Pitfall 6) |
| `src/nativespeaker/api/errors.py` | edit | `MissingPurchaseTokenError`, beside `MissingUsageRowError` at `:213-220` |
| `AGENTS.md` | edit (D-05) | The § "Package layout" amendment |
| `.planning/REQUIREMENTS.md` | edit | Two dated amendments (D-02's rate-limit omission, D-03's divergence from handler step 1) |

### Pattern 1: The handler is `sync` with a different body

`routers/auth.py::sync` is the closest analog and is 5 lines long. Copy its structure: route-level
`Depends(get_linked_identity)`, a typed `response_model`, a docstring of one line, and no clock read.
**Do not add an `evaluated_at`** — CONTEXT.md § Established Patterns says this endpoint reads no clock
at all and the one-instant-per-request pattern does not apply.

### Pattern 2: `crud/` owns the query *and* its fail-closed raise

`AGENTS.md` § Package layout exception 4 states verbatim: *"A fail-closed read may raise its own
rejection, so the rejection stays with the query in `crud/`."* `crud/identities.py` already raises
four rejections from inside `resolve()` [VERIFIED: `crud/identities.py:36-51`]. `crud/purchases.py`
follows: build the mapping, compare against `set(PurchaseProvider)`, raise on any shortfall.

### Pattern 3: Session-in-`__init__` for the crud class

Both `GrantsDB` and `IdentitiesDB` take the session in `__init__` and expose `async def` methods that
use `self.session` [VERIFIED: `crud/grants.py:32-35`, `crud/identities.py:22-25`]. `ChallengesDB` is
the *exception*, not the model — it holds no session and takes one per method because the lifespan
builds a single long-lived instance at `app/lifespan.py:28`. **Follow `GrantsDB`, not `ChallengesDB`.**

### Pattern 4: The statement is a module-level private function

`crud/grants.py` factors each statement into a module-level `_..._statement()` so the locking and
non-locking reads provably share one predicate [VERIFIED: `crud/grants.py:11-29`]. This endpoint has
one read and no locking sibling, so a single method body is defensible; matching the file's
neighbours is the safer default and costs nothing.

### Anti-Patterns to Avoid

- **A `ProfileService`.** Explicitly rejected by D-05. A plan that introduces one contradicts a
  locked decision *and* the `AGENTS.md` amendment the same phase writes.
- **`if not rows: raise`.** D-07 requires completeness against the enum, not emptiness. One row
  present and one missing must fail, and an emptiness test passes that case.
- **Lazy minting on a missing row.** Forbidden by the brief at `04-users-me.md:44` (*"never a lazy
  re-mint"*) and by D-07. `crud/identities.py:88-93` is the *only* mint site and stays that way.
- **Reading a second `core.users` row.** D-03: the barrier already loaded it. A second query is a
  divergence in the opposite direction from the recorded one.
- **Any `X-Platform` / User-Agent / query-parameter branch.** PROF-01, D-02, roadmap criterion 1 and
  `SHARED-INVARIANTS.md` § Wire contract all forbid it. **Verified: no such branch exists anywhere in
  `src/` today** — `grep -rn "User-Agent\|X-Platform" src/` returns nothing, so this criterion is met
  by *not writing* code, and the executable guard is a test that the body is identical across headers.
- **A new client-visible error class or a new `ErrorCode` member.** D-06 adds an *internal* subclass
  of `InternalError` that declares neither `status` nor `code`, exactly like `MissingUsageRowError`.
  Declaring either would trip `error_tree.py`'s together-or-neither assertion.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rejecting an unlinked/historical/blocked/unverified caller | Any check in the handler | `Depends(get_linked_identity)` | It already raises all four; a second check is a second admission rule and violates § The barrier [VERIFIED: `app/dependencies.py:36-61`] |
| Turning an exception into a 500 body | A `try/except` in the handler or router | Raise; `app_error_handler` builds the body from `code` alone | One shared builder owns the shape [VERIFIED: `app/error_handlers.py:33-44`] |
| Emitting the ERROR log line for a broken invariant | A `logger.error(...)` call in `crud/` or the router | `log_level = logging.ERROR` on the class | The handler logs exactly once, `camel_to_snake(type(exc).__name__)`, with `exc_info` [VERIFIED: `app/error_handlers.py:36-41`] |
| A per-attempt success/telemetry line | `users_me_succeeded` or any counter | `RequestLoggingMiddleware` | Already writes one `request` line per attempt; `/users/me` is not excluded — `_EXCLUDED_PATHS = frozenset({"/health/ready"})` [VERIFIED: `logs.py:12`] |
| Rate limiting this route | A `users_me` limits entry | Envoy Gateway | The `limits` engine is deleted from the product, not deferred [VERIFIED: `AGENTS.md` § Resilience; `limits` absent from `pyproject.toml:5-26`] |
| An audit row | Anything | Nothing | Table, writer and call sites are gone; `tests/unit/test_sync_audit_removal.py` fails a rebuild |
| Minting or repairing a token | A backfill or re-mint branch | Fail closed | `crud/identities.py:88-93` mints both eagerly in the create transaction; a read path repairs nothing (§ Fail-closed defaults) |
| Serializing enum keys to strings | A `{k.value: v for …}` comprehension at the boundary | `dict[PurchaseProvider, str]` on the model | Pydantic already emits `{"apple": …, "google_play": …}` — **verified by execution** (Code Example 3) |

**Key insight:** this phase's entire failure surface is *addition* — a handler that re-does the
barrier's work, a service that holds one line, a log line the middleware already writes, a limiter
that no longer exists. Everything the endpoint owes is already built; the phase is wiring plus one
query plus one exception class.

## Common Pitfalls

### Pitfall 1: The rejection-vocabulary ratchet fails on the new error class

**What goes wrong:** adding `MissingPurchaseTokenError` breaks two cases in
`tests/unit/test_rejection_vocabulary.py`, a file the phase otherwise has no reason to open.
**Why it happens:** `EVENT_NAMES` is a hand-written literal — "One entry per class in the tree" —
and `test_the_tree_spells_exactly_the_recorded_event_names` asserts set *equality* against
`{camel_to_snake(cls.__name__) for cls in _production_family()}`
[VERIFIED: `tests/unit/test_rejection_vocabulary.py:32-80, 89-94`]. Separately,
`CONSTRUCTOR_ARGUMENTS` maps each class to the arguments its own `__init__` insists on, and
`_sample()` falls back to a **no-argument** build for anything absent — so a class whose `__init__`
requires `user_id` raises `TypeError` inside a parametrised case
[VERIFIED: `tests/unit/test_rejection_vocabulary.py:102-127`].
**How to avoid:** in the same commit as the class, add `"missing_purchase_token_error"` to
`EVENT_NAMES` and an entry such as
`errors_module.MissingPurchaseTokenError: ((uuid7(), [PurchaseProvider.apple]), {})` to
`CONSTRUCTOR_ARGUMENTS`. Phase 37.3's recorded decision says exactly this: *"Ratchet literals … are
extended in the commit that adds each class, not batched."*
**Warning signs:** `uv run pytest -q` reporting a set-difference assertion naming your new event, or
a `TypeError` in `test_every_class_in_the_tree_contributes_only_scalars`.

### Pitfall 2: The new route trips `test_app_wiring.py` if the dependency is misdeclared

**What goes wrong:** `test_the_public_allowlist_is_exactly_the_readiness_probe` fails, or
`test_every_route_but_the_two_exemptions_requires_a_linked_identity` names `/users/me`.
**Why it happens:** both assertions are computed over the **real** app's routes against two literal
sets — `PUBLIC_PATHS = {"/health/ready"}` and
`PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}`
[VERIFIED: `tests/unit/test_app_wiring.py:11-12, 27-31, 50-55`]. A router registered without
`dependencies=[Depends(get_linked_identity)]` shows up as unauthenticated immediately.
**How to avoid:** declare the narrowing at router level (D-08) and leave both literals untouched —
`/users/me` belongs in neither set, which is itself worth asserting (CONTEXT.md § Discretion).
**Warning signs:** the failing assertion prints your path inside the `unauthenticated` set.

### Pitfall 3: The e2e fixture seeds no purchase tokens

**What goes wrong:** an e2e happy-path test written against `linked_firebase_identity` gets a 500
instead of a 200, and looks like a code bug.
**Why it happens:** `seed_identity` inserts a `User` and an `ExternalIdentity` and **nothing else** —
there is no `StorePurchaseToken` insert anywhere in `tests/e2e/conftest.py`
[VERIFIED: `tests/e2e/conftest.py:171-192`; `grep -rn "StorePurchaseToken" tests/` hits only
`test_models.py`, `test_create_user_rollback.py`, `tests/e2e/test_create_user.py` and
`tests/schema/test_store_purchase_tokens.py`]. Tokens exist only for accounts created through
`POST /auth/create-user`, whose transaction mints both [VERIFIED: `crud/identities.py:88-93`].
**How to avoid:** Wave 0 adds a `seed_purchase_tokens(factory, *, user_id, providers=PurchaseProvider)`
helper to `tests/e2e/conftest.py`. The silver lining: the fail-closed case (D-06/criterion 4) needs
**no** new fixture — it is the current default, and a partial-seed argument covers the one-row-missing
case D-07 insists on.
**Warning signs:** a 500 with `missing_purchase_token_error` in the captured log on a test you
expected to be green.

### Pitfall 4: `"apple"` means two different things

**What goes wrong:** `identity_provider` gets derived from a purchase token's provider, or a store
key gets typed as `IdentityProvider`. Both type-check, both are wrong, and the anonymous case is the
one that exposes it (an anonymous account still has an `apple` purchase token).
**Why it happens:** the value `"apple"` is a member of both enums.
`IdentityProvider` is `anonymous = "anonymous"` / `google = "google"` / `apple = "apple"`
[VERIFIED: `tables/identities.py:11-15`, quoted verbatim] and `PurchaseProvider` is
`apple = "apple"` / `google_play = "google_play"` [VERIFIED: `tables/purchases.py:10-14`, quoted
verbatim]. They mirror two different PostgreSQL types: `core.identity_provider` and
`core.subscription_provider`.
**How to avoid:** annotate the response model's `identity_provider` as `IdentityProvider` and the
token mapping as `dict[PurchaseProvider, str]`; never construct one enum from the other's value.
**Warning signs:** any expression converting between the two, or a test asserting
`identity_provider == purchase_tokens` keys.

### Pitfall 5: Checking emptiness instead of completeness

**What goes wrong:** an account with one row (a partially-backfilled or partially-deleted account)
returns a body missing a key the contract guarantees, and the client's `purchase_tokens["apple"]`
raises on the device rather than the server.
**Why it happens:** `if not rows: raise` is the reflexive shape and it passes the zero-row case.
**How to avoid:** D-07 — compare the mapping's key set against `set(PurchaseProvider)` and raise with
the *missing* members named. The database permits the partial state: the table's only guarantee is
`UNIQUE (user_id, provider)` [VERIFIED: `migrations/20260818_01_initial-release.sql:163-170`, quoted:
`UNIQUE (user_id, provider),` / `UNIQUE (provider, identity_value)`], with no constraint requiring
both rows to exist.
**Warning signs:** a test that seeds one row and expects a 200.

### Pitfall 6: `AGENTS.md` says routers take `Depends()` only

**What goes wrong:** the handler does `PurchasesDB(session)` inline, and the phase's own layering
amendment is the first thing violated.
**Why it happens:** D-05 removes the *service* requirement, not the `Depends()`-only rule.
`AGENTS.md` § Package layout still reads `routers/` — *"HTTP handlers, `Depends()` only"*, and STATE.md
carries *"All FastAPI dependencies in app/dependencies.py; routes use Depends() only"*. **No router in
`src/` constructs a DB class inline today** [VERIFIED: `grep -rn "DB(" src/nativespeaker/api/routers/`
returns nothing].
**How to avoid:** add a small accessor to `app/dependencies.py` — the `get_challenge_store` /
`get_sync_service` shape [VERIFIED: `app/dependencies.py:90-92, 111-114`] — e.g.
`def get_purchases_db(db: AsyncSession = Depends(get_db)) -> PurchasesDB: return PurchasesDB(db)`.
This is the D-05-compliant reading: the router reaches `crud/` **without a service in between**, which
is what the developer asked for.
**Warning signs:** an `import` of a `crud` class in `routers/users.py` used as a constructor rather
than a type annotation.

### Pitfall 7: A unit-test stub that keys on `column_descriptions[0]["entity"]`

**What goes wrong:** a fake session copied from `tests/unit/test_sync_resolver.py` mis-routes the new
statement.
**Why it happens:** `_StubSession.exec` dispatches on `statement.column_descriptions[0]["entity"]`
[VERIFIED: `tests/unit/test_sync_resolver.py:77-80`]. That still works for a two-column select —
executed check: `select(StorePurchaseToken.provider, StorePurchaseToken.identity_value)` yields
`[('provider', <StorePurchaseToken>), ('identity_value', <StorePurchaseToken>)]` — but the **result
rows are `Row` tuples, not ORM instances**, so a stub returning model objects will not match the
production unpacking.
**How to avoid:** have the stub return `(provider, identity_value)` tuples, or select the whole entity
and read attributes. Decide once and keep the stub and the production code in agreement.
**Warning signs:** an `AttributeError` on `.provider` inside a test double.

### Pitfall 8: `get_db` commits even on a read

**What goes wrong:** a reviewer reads the read-only claim as false.
**Why it happens:** `get_db` yields, then `await session.commit()` unconditionally
[VERIFIED: `app/dependencies.py:22-29`]. For a read the COMMIT is a no-op that writes nothing.
**How to avoid:** nothing to change — `/auth/sync` behaves identically and Phase 38 proved
no-lock/no-write behaviour against a real database in `tests/schema/test_sync_lock_freedom.py`. If a
UAT criterion asserts "writes nothing", assert **table state** (Phase 38's approach), not the absence
of a COMMIT.

## Code Examples

### 1. The handler — modelled on `routers/auth.py::sync`

```python
# Source (pattern): src/nativespeaker/api/routers/auth.py:77-86, verbatim structure
# `Response` injection verified working under response_model — see example 4.
router = APIRouter(tags=["users"], dependencies=[Depends(get_linked_identity)])


@router.get("/users/me",
            response_model=MeResponse,
            summary="Report the caller's profile, registration state and purchase tokens")
async def me(response: Response,
             identity: Identity = Depends(get_linked_identity),
             purchases: PurchasesDB = Depends(get_purchases_db)) -> MeResponse:
    """Report the caller's stored profile and both store attribution tokens. Nothing is written."""
    tokens = await purchases.read_tokens(identity.user.id)
    # `no-store`: private account metadata, which a private client cache would otherwise keep.
    response.headers["Cache-Control"] = "no-store"
    return MeResponse(profile=Profile(email=identity.user.email,
                                      display_name=identity.user.display_name),
                      identity_provider=identity.identity.provider,
                      purchase_tokens=tokens)
```

### 2. The query and the fail-closed raise — modelled on `crud/grants.py`

```python
# Source (pattern): src/nativespeaker/api/crud/grants.py:32-57 (session-in-init, no lock, `.all()`)
class PurchasesDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def read_tokens(self, user_id: UUID) -> dict[PurchaseProvider, str]:
        """Return one attribution token per store for `user_id`, or raise if any store has no row."""
        statement = select(StorePurchaseToken.provider, StorePurchaseToken.identity_value) \
            .where(col(StorePurchaseToken.user_id) == user_id)
        tokens = {provider: value for provider, value in (await self.session.exec(statement)).all()}

        # Completeness against the enum, never emptiness: one row present and one absent must fail.
        missing = sorted(set(PurchaseProvider) - set(tokens))
        if missing:
            raise MissingPurchaseTokenError(user_id, missing)
        return tokens
```

### 3. The error class — the `MissingUsageRowError` template, verbatim in shape

```python
# Source: src/nativespeaker/api/errors.py:213-220 — the class this one copies
# class MissingUsageRowError(InternalError):
#     """An effective grant with no `core.user_monthly_usage` row."""
#     log_level = logging.ERROR
#     def __init__(self, grant_id: UUID):
#         self.grant_id = grant_id
#         super().__init__(f"Grant {grant_id} has no core.user_monthly_usage row")

class MissingPurchaseTokenError(InternalError):
    """A user with no `core.store_purchase_tokens` row for one or more stores."""
    # Never minted here: the create transaction is the only mint site, and a read path repairs nothing.
    log_level = logging.ERROR

    def __init__(self, user_id: UUID, missing: Sequence[PurchaseProvider]):
        self.user_id = user_id
        self.missing = list(missing)
        # `identity_value` is never formatted in: invariant 10 keeps the token out of every log line.
        super().__init__(f"User {user_id} has no core.store_purchase_tokens row for "
                         f"{[p.value for p in missing]}")
```

Declares neither `status` nor `code`, so it inherits `InternalError`'s
`status = 500` / `code = "internal_error"` [VERIFIED: `errors.py:131-136`, quoted:
`status = 500` / `code = "internal_error"`] and satisfies `error_tree.py`'s
together-or-neither rule [VERIFIED: `tests/unit/error_tree.py:31-34`].

### 4. Verified: the wire shape, the header and the OpenAPI schema

```python
# Executed this session against the installed fastapi 0.135.1 / pydantic 2.12.5.
class MeResponse(BaseModel):
    profile: Profile
    identity_provider: str
    purchase_tokens: dict[PurchaseProvider, str]

@app.get("/users/me", response_model=MeResponse)
async def me(response: Response) -> MeResponse:
    response.headers["Cache-Control"] = "no-store"
    return MeResponse(...)

# Observed output:
#   200 no-store {'profile': {'email': 'a@b.com', 'display_name': None},
#                 'identity_provider': 'google',
#                 'purchase_tokens': {'apple': 't1', 'google_play': 't2'}}
#   openapi purchase_tokens: {"additionalProperties": {"type": "string"},
#                             "propertyNames": {"$ref": "#/components/schemas/PurchaseProvider"},
#                             "type": "object", "title": "Purchase Tokens"}
```

### 5. Verified: D-03's detached read holds against the real database

```python
# Executed this session against PostgreSQL 17 with the app's own config and IdentitiesDB.
async with factory() as s2:                        # the barrier's short session
    ident = await IdentitiesDB(s2).resolve(issuer=..., subject=..., allow_preauth=True)
# session is now closed
print(ident.user.email, ident.user.display_name, ident.identity.provider)
# AFTER CLOSE -> 'detached@example.com' 'Ada' google
```

The premise is `async_sessionmaker(db_engine, class_=SQLModelAsyncSession, expire_on_commit=False)`
[VERIFIED: `app/lifespan.py:34-36`] — and the e2e harness sets the same flag on its substituted
factory [VERIFIED: `tests/e2e/conftest.py:125-130`], so e2e tests exercise the same behaviour.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1.5 `/users/me` returning email, name, plan tier and usage | Deleted with its router | Phase 35 D-16 | Nothing to "rewrite" against — this is a fresh declaration, not an edit [VERIFIED: `grep -rn "users/me" src/` returns nothing] |
| `audit.auth_events` row per attempt | No audit subsystem at all | Phase 37.1 D-01; § "Audit" struck from `SHARED-INVARIANTS.md` by Phase 38 D-03 | PROF-02 is trivially true; a rebuild fails `tests/unit/test_sync_audit_removal.py` |
| Hand-rolled `RejectionCounter` metric | Rejection rate derived from the structured log | Phase 36 D-15 | No counter to register |
| Backend `limits` rate-limit engine | Envoy Gateway only | Phase 35 D-05 | No `users_me` entry; brief `04-users-me.md:26` and `:52` are superseded |
| Pre-handler ASGI barrier middleware + route registry | `Depends(get_linked_identity)`; membership is the router a route is registered on | Phase 37.1 D-06 | No registry entry, no startup enumeration; `tests/unit/test_app_wiring.py` carries route categorisation |
| Business logic always routed through `services/` | A router may call `crud/` directly; a service is earned by complexity | **This phase, D-05** | The `AGENTS.md` amendment is itself a deliverable |

**Deprecated/outdated in the phase brief (`04-users-me.md`) — do not implement:**
- `:17` route registry and startup enumeration assertion — deleted.
- `:19`, `:26`, `:52` the `limits` engine and the `users_me` entry — deleted from the product.
- `:25`, `:50` the bounded-cardinality counter metric — never rebuilt; PROF-02 says so explicitly.
- `:24`, `:45`, `:50` `audit.auth_events` — table, writer and call sites are gone.
- `:35`, `:49` "exactly-one-`Authorization`" — the invariant was removed by the developer on
  2026-08-30 and FOUND-02 deleted; the framework's `HTTPBearer` behaviour is the recorded contract.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Apple's StoreKit 2 field is `appAccountToken` and Google Play Billing's is `obfuscatedExternalAccountId`, and the stored `identity_value` is what the client passes to each | User Constraints D-01, Security Domain | None inside this phase — the server returns an opaque string either way. Wrong only affects client-side documentation. Sourced from the discussion log, not from vendor docs read this session. |
| A2 | `get_purchases_db` (or an equivalent accessor in `app/dependencies.py`) is the D-05-compliant way for the router to reach `crud/` | Pitfall 6, Code Example 1 | Low. The alternative — constructing the class inline in the handler — is defensible under the new rule but breaks the `Depends()`-only line the same file keeps. The planner should settle this explicitly when wording the `AGENTS.md` amendment. |
| A3 | A partial token set (one row present, one missing) is reachable in production | Pitfall 5 | Low. The schema permits it and D-07 mandates the check regardless; if it is truly unreachable the check is a tripwire, which is exactly what `MultipleEffectiveGrantsError` already is. |
| A4 | No plan will need to touch `migrations/` | Component Responsibilities | Low — CONTEXT.md's out-of-scope list forbids schema changes of any kind, and the table already exists with both required constraints. |

## Open Questions

1. **Does `/users/me` earn its own two named tests in `test_app_wiring.py`, or a parametrisation?**
   - What we know: `/auth/sync` has two dedicated cases,
     `test_the_sync_route_declares_the_linked_identity_narrowing` and
     `test_the_sync_route_is_in_neither_exemption_set` [VERIFIED: `tests/unit/test_app_wiring.py:39-48`].
   - What's unclear: CONTEXT.md explicitly leaves the shape to the planner.
   - Recommendation: parametrise the existing pair over `("/auth/sync", "/users/me")`. It keeps the
     named-route protection (a generic assertion would pass if the route were exempted) while adding
     no duplicated bodies, and it scales to Phase 40's route.

2. **Does the e2e happy path use a seeded account or a real `POST /auth/create-user` run?**
   - What we know: create-user mints both tokens in one transaction, so driving it end to end
     produces a genuinely complete account; but `tests/e2e/test_create_user.py` needs the Firebase
     Admin credential and skips without it [VERIFIED: `tests/e2e/conftest.py:62-78`].
   - What's unclear: whether the phase wants that coupling.
   - Recommendation: seed directly (new `seed_purchase_tokens` helper). It keeps `/users/me` tests
     green on a machine with no Admin credential, matching how `tests/e2e/test_sync.py` seeds.

3. **Does `MissingPurchaseTokenError` also join `test_error_contract.py::_id_carrying_cases`?**
   - What we know: that helper covers the three existing id-carrying `InternalError` subclasses and
     asserts no identifier reaches the body [VERIFIED: `tests/unit/test_error_contract.py:60-95`].
   - What's unclear: whether D-10's "no log-redaction test" also discourages this body-redaction one.
   - Recommendation: add it. D-10 declined a *log* test because no code path carries a body into a
     log; this case asserts the opposite direction (that `user_id` never reaches the client), it is
     three lines of parametrisation, and it is the executable trace of D-06's redaction constraint.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.7 | — |
| uv | test/run commands | ✓ | 0.12.5 | `.venv/bin/pytest` directly |
| PostgreSQL (dev/test) | `-m schema` suite, e2e suite | ✓ | reachable on the configured DSN | — |
| Firebase Identity Toolkit (network) | e2e `firebase_token` fixture | ✓ | — | — |
| Firebase Admin credential (ADC) | `tests/e2e/test_create_user.py` only | not checked | — | Those tests `pytest.skip` themselves; `/users/me` tests should not depend on it (Open Question 2) |
| Node/npm ecosystems | — | n/a | — | — |

**Verified by execution this session:** `uv run pytest -q -m schema tests/schema/test_store_purchase_tokens.py`
→ `7 passed in 0.85s`; `uv run pytest -q -m e2e tests/e2e/test_sync.py` → `14 passed in 0.75s`
(the e2e run fetches a real Firebase ID token, so both the database and the network path are live).

**Missing dependencies with no fallback:** none.

## Validation Architecture

`workflow.nyquist_validation` is `true` [VERIFIED: `.planning/config.json` → `"nyquist_validation": true`].

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`), pytest-dotenv 0.5.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`:52-62`) |
| Quick run command | `uv run pytest -q` — addopts already deselect `e2e` and `schema` |
| Full suite command | `uv run pytest -q -m ""` |
| Marked suites | `uv run pytest -q -m e2e` · `uv run pytest -q -m schema` |
| Lint / types | `uv run ruff check` · `ty` (both pinned in `pyproject.toml:20-21`) |

`addopts = "-v --tb=short -m 'not e2e and not schema'"` [VERIFIED: `pyproject.toml:58`, quoted
verbatim], so **every e2e or schema command must pass `-m` explicitly** — the rule Phase 34 recorded
and that still holds.

**Measured this session:** `uv run pytest -q` → `767 passed, 311 deselected, 9 warnings in 29.21s`
(30.4s wall). The e2e and schema probes above ran in under a second each once the session fixtures
were warm; the full `-m ""` run is dominated by the e2e Firebase sign-in and the schema
apply/rollback cases.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROF-01 | The 200 body is exactly `{profile:{email,display_name}, identity_provider, purchase_tokens}` — whole-body equality, so a fourth key fails | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ Wave 0 |
| PROF-01 | Both store keys are present for every caller; the key set equals `set(PurchaseProvider)` | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ Wave 0 |
| PROF-01 / criterion 1 | The body is byte-identical across differing `User-Agent`, an `X-Platform` header and a `?platform=` query parameter | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ Wave 0 |
| PROF-01 / criterion 2 | `identity_provider` equals the stored `core.external_identities.provider`, read back from the row rather than the fixture argument | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ Wave 0 — reuse `_stored_provider` from `tests/e2e/test_sync.py:71-76` |
| PROF-01 / criterion 2 | `/users/me` and `/auth/sync` report the same `identity_provider` in one test run | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ Wave 0 |
| PROF-01 / D-03 | The request issues exactly **one** query (no second `core.users` read) | unit (statement-recording stub) | `uv run pytest -q tests/unit/test_users_me.py` | ❌ Wave 0 |
| criterion 4 / D-06 | Zero token rows → 500 `{"code":"internal_error"}`, one ERROR log line, no null entry | unit + e2e | `uv run pytest -q tests/unit/test_purchases_crud.py` and `-m e2e tests/e2e/test_users_me.py` | ❌ Wave 0 |
| criterion 4 / D-07 | **One** row present and one missing → the same 500 (the case an emptiness check would pass) | unit | `uv run pytest -q tests/unit/test_purchases_crud.py` | ❌ Wave 0 |
| D-06 | `user_id` and the missing providers never reach the response body or headers | unit | `uv run pytest -q tests/unit/test_error_contract.py` | ✅ extend `_id_carrying_cases` |
| D-06 | The new class joins the recorded log vocabulary and the constructor table | unit | `uv run pytest -q tests/unit/test_rejection_vocabulary.py` | ✅ **must be extended in the same commit** |
| D-06 | The error tree stays total (new class declares neither status nor code) | unit | `uv run pytest -q tests/unit/test_error_registry.py` | ✅ must stay green unchanged |
| D-08 | `/users/me` declares `get_linked_identity` and sits in neither exemption set | unit | `uv run pytest -q tests/unit/test_app_wiring.py` | ✅ extend |
| D-08 | Unauthenticated `GET /users/me` → 401 `auth_required`; unlinked → 403 `preauth_identity_not_allowed` | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ Wave 0 (precedents: `tests/e2e/test_unauthenticated_access.py`, `tests/e2e/test_admission.py`) |
| D-09 | The 200 carries `Cache-Control: no-store` | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ Wave 0 (precedent: `tests/unit/test_challenge_endpoint.py:116-119`) |
| PROF-02 | No audit table, writer or call site is reintroduced | unit | `uv run pytest -q tests/unit/test_sync_audit_removal.py` | ✅ must stay green unchanged |
| PROF-02 | The route writes nothing: table state before and after is identical | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ Wave 0 (precedent: `_entitlement_snapshot` at `tests/e2e/test_sync.py:61-68`) |
| D-05 | `AGENTS.md` § Package layout states the router-to-crud rule; no `ProfileService` exists | manual + grep | `grep -rn "ProfileService" src/` returns nothing | n/a |
| repo rule | Every new docstring is ≤ 3 lines on every root | unit | `uv run pytest -q tests/unit/test_docstring_bar.py` | ✅ baselines are **0 on every root** and must stay 0 [VERIFIED: `tests/unit/test_docstring_bar.py:41-47`] |

### Sampling Rate

- **Per task commit:** `uv run pytest -q` (unit only; measured 29.2s) plus `uv run ruff check`.
- **Per wave merge:** `uv run pytest -q -m ""` (unit + e2e + schema).
- **Phase gate:** full suite green, `ruff check` clean, before `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] `tests/unit/test_users_me.py` — the route over a substituted identity and a fake crud: body
      shape, both keys, `Cache-Control`, one-query, client-signal invariance. Build the client the way
      `tests/unit/test_challenge_endpoint.py:73-80` does — a bare `FastAPI()`, `include_router`,
      `register_exception_handlers`, then `dependency_overrides`.
- [ ] `tests/unit/test_purchases_crud.py` — the completeness rule: both rows → mapping; zero rows →
      raise; **one row → raise**; the statement takes no lock (`" FOR UPDATE" not in str(compiled)`,
      the check `tests/unit/test_sync_resolver.py:31-32` already uses).
- [ ] `tests/e2e/test_users_me.py` — real transport, real database: happy path, stored-provider
      agreement with `/auth/sync`, the fail-closed 500, the barrier's 401/403, and an
      unchanged-table-state assertion.
- [ ] `tests/e2e/conftest.py` — a `seed_purchase_tokens` helper (Pitfall 3). Needed for every e2e
      case except the fail-closed one, which the current fixtures already produce.
- [ ] `tests/unit/test_rejection_vocabulary.py` — extend `EVENT_NAMES` and `CONSTRUCTOR_ARGUMENTS`
      (Pitfall 1). Not optional: the suite goes red the moment the class lands.
- [ ] `tests/unit/test_app_wiring.py` — `/users/me` assertions (Open Question 1).
- [ ] `tests/unit/test_error_contract.py` — extend `_id_carrying_cases` (Open Question 3).
- [ ] Framework install: **none needed.**

## Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json`, so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `Depends(get_linked_identity)` → `HTTPBearer` + `JWTVerifier` (RS256, pinned `iss`/`aud`, cached JWKS). The route adds nothing; adding anything would violate § The barrier. |
| V3 Session Management | no | No backend session or token is minted — `SHARED-INVARIANTS.md` § Tokens and sessions forbids it globally. |
| V4 Access Control | yes | The only object returned is the caller's own, keyed by `identity.user.id` from the verified `(issuer, subject)`. **No `user_id` is ever accepted from the request** — there is no path parameter, query parameter or body. |
| V5 Input Validation | **n/a by construction** | The route takes no input at all: no body, no path parameter, no query parameter. This is the strongest form of criterion 1 — there is no client-supplied value to branch on. |
| V6 Cryptography | no (indirect) | The tokens are `str(uuid4())` minted elsewhere [VERIFIED: `crud/identities.py:88-93`]; this route mints and derives nothing. |
| V7 Error Handling & Logging | yes | One shared handler builds the body from `code` alone; the exception message never reaches the client [VERIFIED: `app/error_handlers.py:42-44`]. D-06 keeps `identity_value` out of the message and out of every log field. |
| V8 Data Protection | yes | `Cache-Control: no-store` (D-09) keeps private account metadata out of a private client cache. |
| V13 API | yes | `Depends()`-only handler, typed `response_model`, closed payload (D-01), no documentation route registered [VERIFIED: `app/main.py:25-27`]. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR — reading another account's tokens | Information disclosure | Ownership comes only from the barrier's resolved `user_id`; no identifier is accepted from the request |
| Client-signal steering (User-Agent / `X-Platform` / query flag changing what is read) | Tampering | D-02's fixed shape: no branch exists to steer. Asserted by an invariance test rather than assumed. |
| Secret leakage through an error message or log field | Information disclosure | D-06: the exception carries `user_id` and provider names, never `identity_value`; `test_error_contract.py` asserts no identifier reaches the body |
| Silent repair of a broken invariant (lazy mint) | Elevation of privilege / integrity | D-07 fails closed and never mints; `crud/identities.py` stays the only mint site |
| Enumeration oracle across error branches | Information disclosure | All four barrier rejections and the internal 500 use existing classes whose status/code/body are declared once; `error_tree.py` asserts no code is bound to two statuses |
| Cache retention of private metadata on a shared or private cache | Information disclosure | `Cache-Control: no-store` (D-09) |
| Unauthenticated reachability of the new route | Spoofing | Router-level dependency (D-08) plus `test_app_wiring.py`'s public-allowlist equality assertion |

**Accepted risk, recorded rather than mitigated** (`04-users-me.md:51`, restated in D-02): the tokens
are non-secret opaque identifiers that confer nothing, and a leaked ID token already reads profile,
entitlement and chats until its `exp`. Returning both tokens to an authenticated bearer is therefore
no privilege escalation. This is proportionate for a pre-launch sub-$5/month app — consistent with
`AGENTS.md`'s instruction not to over-engineer against a high-value-target threat model.

## Project Constraints (from AGENTS.md / CLAUDE.md)

`./CLAUDE.md` is `@AGENTS.md`; the repository-level `ns-api-gateway/AGENTS.md` adds the code rules.
Directives that bind this phase, each treated with the authority of a locked decision:

1. **Keep specs short — programming this app should not consume many tokens.** Prefer the smallest
   plan that satisfies the criteria; this phase is one route, one query, one class.
2. **Docstrings: three lines maximum**, stating what the entity does and nothing else. **Comments:
   only where they resolve a genuine ambiguity; default to none, one line each.** Enforced at 0 on
   every root by `tests/unit/test_docstring_bar.py`.
3. **Package layout** — `crud/` database access, `schemas/` bodies and value types, `tables/` SQLModel
   tables, `routers/` handlers with `Depends()` only, `errors.py` owns the error shape. Exception 4
   (a fail-closed read raises its own rejection in `crud/`) is what places D-06's raise.
   **This phase amends this section per D-05.**
4. **Function shape** — delete a function that is only a step; keep one that states a rule or marks a
   boundary. A one-line private helper in `routers/users.py` is a step.
5. **Resilience** — the `limits` engine is deleted from the product, not deferred. No rate limiting.
6. **No over-engineering for a high-value-target threat model, but no skipping of normal security
   measures.** Fail closed, redact the token from messages, `no-store` — and nothing more.
7. **Envoy Gateway handles JWT authentication and rate limiting by IP/user/URL** — but per
   `SHARED-INVARIANTS.md` § Wire contract, *"Envoy's JWT filter is defense-in-depth only; no backend
   correctness depends on it."* The backend still verifies every token itself.

## Sources

### Primary (HIGH confidence)

- Executed against the installed environment this session: `uv run pytest -q` (767 passed / 29.21s);
  `-m schema tests/schema/test_store_purchase_tokens.py` (7 passed); `-m e2e tests/e2e/test_sync.py`
  (14 passed); a FastAPI `TestClient` probe of the response model, the injected `Response` header and
  the generated OpenAPI schema; a real-database probe of the detached `identity.user.email` read.
- Repository source read this session: `src/nativespeaker/api/{app/dependencies.py, app/main.py,
  app/lifespan.py, app/error_handlers.py, errors.py, logs.py, routers/auth.py, routers/root.py,
  routers/__init__.py, crud/__init__.py, crud/grants.py, crud/identities.py, schemas/auth.py,
  services/sync.py, tables/purchases.py, tables/users.py, tables/identities.py, tables/__init__.py}`;
  `migrations/20260818_01_initial-release.sql:163-199`; `tests/unit/{test_app_wiring.py,
  test_rejection_vocabulary.py, test_error_contract.py, test_error_registry.py, error_tree.py,
  test_docstring_bar.py, test_sync_audit_removal.py, test_sync_error_reuse.py, test_sync_resolver.py,
  test_challenge_endpoint.py, test_users.py, conftest.py}`; `tests/e2e/{conftest.py, test_sync.py,
  test_unauthenticated_access.py}`; `pyproject.toml`; `AGENTS.md`.
- Binding specification: `specs/auth-refactor-phases/SHARED-INVARIANTS.md` (whole file);
  `specs/auth-refactor-phases/04-users-me.md` (whole file).
- Project planning: `.planning/phases/39-get-users-me/39-CONTEXT.md`; `.planning/REQUIREMENTS.md`
  § PROF and the amendment blocks; `.planning/ROADMAP.md:508-518`; `.planning/STATE.md`;
  `.planning/phases/38-post-auth-sync/38-06-SUMMARY.md` (the Phase 39 handoff).

### Secondary (MEDIUM confidence)

- `.planning/phases/39-get-users-me/39-DISCUSSION-LOG.md` — audit trail only; used solely to source
  A1's vendor field names and to confirm no alternative to a locked decision was left open.

### Tertiary (LOW confidence)

- None. No external documentation lookup was required: the phase adds no dependency and every
  behavioural claim was checked against installed code or executed directly.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — no new dependency; every version confirmed by executing against the
  installed environment.
- Architecture: **HIGH** — every component has a named in-repo precedent read this session, and the
  two load-bearing premises (D-03's detached read, D-01's wire shape) were verified by execution
  rather than inference.
- Pitfalls: **HIGH** — each is grounded in a file, line range and verbatim quote from the ratchet or
  fixture that will actually fail; the fixture gap in Pitfall 3 was confirmed by a repository-wide grep.
- Validation architecture: **HIGH** — commands and runtimes measured this session, not estimated.
- Vendor client-side field names (A1): **LOW** — training/discussion-sourced, no impact inside this
  phase's boundary.

**Research date:** 2026-09-01
**Valid until:** 2026-10-01 (30 days — the codebase is the only moving part, and no external
dependency is in scope)
