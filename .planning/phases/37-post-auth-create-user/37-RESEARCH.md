# Phase 37: POST /auth/create-user - Research

**Researched:** 2026-08-22
**Domain:** FastAPI auth endpoint · Firebase Admin SDK (Python) · PostgreSQL race arbitration · tenacity retry
**Confidence:** HIGH (stack, race arbitration, SDK shapes — empirically verified against the live DB and the installed SDK) / MEDIUM (test-harness strategy for criteria 3–4)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** **No backend traffic limiter ships on this route, in any form.** `02-create-user.md:28`
  and `:84` name two backend IP-keyed entries — `create_user_prepare` 10/min/ip and `create_user`
  10/min/ip — and call the gateway limits "required and load-bearing". Neither exists and neither
  will. Phase 35 D-05 deleted `§5` from the product outright and the developer reaffirmed it here
  without exception, explicitly rejecting a narrow per-route reinstatement. **This is a flagged
  SHARED-INVARIANTS conflict, recorded and not silently resolved.**

  **The consequence the planner must carry, stated plainly:** `POST /auth/create-user` is reachable
  by anyone holding any valid Firebase ID token — which anyone can mint by signing up — and it is
  rate-limited by nothing. Each completion costs one Firebase Admin call and creates one account.
  The mitigating facts, for the record: a valid token is still required, accounts carry no
  entitlement at creation (§02 step 10), and the v1.6 Helm chart's existing Envoy limits remain in
  place untouched. — **Reversibility:** costly.

- **D-02:** **Both cross-request Firebase lookup budgets are dropped.**
  `create_user_firebase_identity_lookup` (60/min, key `deployment`) and
  `create_user_firebase_identity_lookup_ip` (10/min, key client IP) are per-minute IP- and
  deployment-keyed — traffic limits written in budget vocabulary. Of §02 step 7's three-budget
  `check_all` list, only the retry budget survives.

- **D-03:** **`registration_temporarily_unavailable` is not registered.** Phase 37 registers
  **three** new classes, not four.

- **D-04:** **`auth/budgets.py` is retired and the Firebase retry is expressed with `tenacity`.**
  Delete `auth/budgets.py` and `tests/unit/test_budgets.py`; `BudgetExhausted`'s mapping (internal
  `firebase_lookup_unavailable` → client `verification_temporarily_unavailable`) moves onto the
  tenacity exhaustion path and must be preserved exactly. **Phase 35 D-06 is superseded.**
  — **Reversibility:** costly.

- **D-05:** **`resilience.py:165-191`'s retry loop is converted to the same tenacity policy.**
  **Planner: this is the highest-risk item in the phase and it is not on the phase's own critical
  path.** Three non-obvious behaviors a naive conversion drops: `on_admitted` fires **at most once
  across every attempt**; transient-vs-permanent classification via `_is_transient_error` gates
  whether a retry happens at all; and `record_failure` must fire on provider failures but **not** on
  the non-provider path at `:176`. Treat existing behavior as the specification, convert under the
  existing tests, and give it its own plan and its own commit. — **Reversibility:** reversible.

- **D-06:** **`uv lock` is run deliberately and its full output committed** in one dependency-scoped
  commit — the new `tenacity` direct dependency, the `1.5.0 → 1.6.0` project-version correction, and
  the `revision = 2 → 3` lockfile-format bump. This **closes D-35-05-A**. `docker-compose.yml` stays
  unowned and untouched.

- **D-07:** **`firebase-admin`, awaited through `starlette.concurrency.run_in_threadpool`.** No async
  Firebase *Auth* admin client exists.
  [firebase-admin-python#104](https://github.com/firebase/firebase-admin-python/issues/104) is still
  open. Rejected: Identity Toolkit REST over httpx.

- **D-08:** **Service-account credentials are inline JSON in the gitignored `.env`**, loaded with
  `credentials.Certificate(json.loads(...))`. Rejected: `GOOGLE_APPLICATION_CREDENTIALS` / ADC
  (SHARED-INVARIANTS forbids any ambient/default/fallback client); GKE Workload Identity.

- **D-09:** **Test coverage is split: real anonymous e2e, substituted adapter for everything else.**
  The existing e2e fixture (`tests/e2e/conftest.py:44-60`) signs in with email/password, yielding
  `providerData == [{providerId: "password"}]` — a guaranteed `create_flow_mismatch`.
  - **Anonymous flow, for real.** Add a fixture minting a genuine anonymous Firebase user via
    Identity Toolkit `accounts:signUp`.
  - **Registered flow and every rejection shape, substituted.** A fake `FirebaseAdminAdapter`
    returning synthetic `ProviderDataResult`s.

- **D-10:** **A successful completion returns registration state only** — the classified
  `identity_provider`. — **Reversibility:** cheap in practice, pre-launch.

- **D-11:** **The purchase-attribution tokens are not in the response.** Minted eagerly in the create
  transaction on every branch; `GET /users/me` in Phase 39 surfaces them.

### Claude's Discretion

- **Race-loser durability mechanism.** §02 step 12 names three acceptable mechanisms. Default:
  **consume-first conditional update**. Planner may revisit with reasons.
  → *Research revisits this with hard evidence. See Pitfall 1 and Pattern 3.*
- **Testing success criteria 3 and 4.** Both need genuinely committed, concurrent transactions. The
  e2e harness wraps every test in one outer transaction with savepoint-joined sessions
  (`tests/e2e/conftest.py:93-115`). Options: a second escape-hatch fixture doing real commits with
  explicit cleanup, or pushing these two to `tests/schema/`.
- Issuer → named-app selection for the Admin client, and where the fixed 5–10s per-attempt timeout
  `adapters.py:14-20` mandates is configured on the SDK transport.
- Module layout for the concrete adapter and the classifier, and the names of the three new error
  classes' constants.
- Whether prepare-mode and completion-mode handlers are one route function dispatching on
  `classify_mode_signal()` or two functions behind one registered route.
- What the structured security log records on each fail-closed branch.

### Deferred Ideas (OUT OF SCOPE)

- **`registration_temporarily_unavailable` and the Envoy gateway contract (§9 / FOUND-09)** — v2.1.
- **Real Google- and Apple-linked Firebase test accounts** — rejected as unreproducible shared CI state.
- **`docker-compose.yml`** — still modified in the working tree, still unowned, not picked up by D-06.
- **Secret Manager integration** — the todo's rationale now covers the Firebase service-account key.
- **Restore `with_structured_output(strict=True)`** — must not be conflated with D-05's conversion.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CREATE-01 | The endpoint is the only pre-auth-callable route; every other route rejects an unlinked caller with `preauth_identity_not_allowed` | Already structurally enforced. `_PREAUTH_CALLABLE_ROUTE` is pinned and `resolve_identity` implements both arms — see *Reusable Assets*. This phase only adds the `RouteMetadata` entry. |
| CREATE-02 | The endpoint implements both prepare mode and completion mode, partitioned by the mode signal | `classify_mode_signal()` is complete and unit-tested. See Pattern 1 (body parsing must precede it) and Pitfall 6. |
| CREATE-03 | The creation transaction atomically produces one `core.users` row, exactly one ACTIVE `core.external_identities` row, and the per-store purchase-attribution tokens — never a partial account | Blocked on a missing model — `core.store_purchase_tokens` has no SQLModel class and no PK (Pitfall 2). Transaction shape in Pattern 3, Code Example 4. |
| CREATE-04 | Concurrent create-user attempts for the same `(issuer, subject)` never produce duplicate accounts; the losing caller reconciles through `POST /auth/sync` | Fully resolved by empirical probe: constraint-name discrimination (Code Example 5) and savepoint durability (Pitfall 1). |
</phase_requirements>

## Project Constraints (from CLAUDE.md / AGENTS.md)

`./CLAUDE.md` is a single `@AGENTS.md` include [VERIFIED: /home/init/native-speaker/CLAUDE.md:1 — file contains exactly `@AGENTS.md`]. The directives:

| Directive | Consequence for this phase |
|---|---|
| "There are no users yet, and it will not attract many users at first." | Justifies D-01's no-limiter position and rules out any distributed-counter subsystem. |
| "The product's value is not great enough to make stealing it attractive — don't over-engineer for that threat model. **But don't skip normal security measures just because there are no users yet.**" | Fail-closed rules, the closed classifier, and the anti-oracle error contract are *normal* measures and stay. Timing normalization is over-engineering (already declined in 35 D-13). |
| "Keep specs short: programming this app should not consume many tokens." | Prefer the smallest module count that satisfies the seams. Do not create a `services/` layer for the create flow. |
| "The app runs in a Kubernetes cluster behind Envoy Gateway, which authenticates by JWT and rate-limits by IP, user, URL, etc." | This is the standing basis for D-01. Envoy's JWT filter is defense-in-depth only — SHARED-INVARIANTS is explicit that no backend correctness depends on it. |

## Summary

This phase is unusually well-constrained: `02-create-user.md` is 88 lines of near-verbatim normative
text with a numbered rejection precedence that **is** the ordering contract, and Phase 35 shipped
every shared seam the route consumes. The genuine unbuilt surface is narrow — one concrete Firebase
Admin adapter, one closed providerData classifier, three error classes, one route + registry entry,
two mode handlers, and one consuming transaction — plus two refactors (D-04, D-05) that are not on
the endpoint's critical path.

Research turned up **three blocking facts the planner must design around, none of which is visible
from the spec.** First, `core.store_purchase_tokens` has *no primary key by design* and has no
SQLModel class at all — CREATE-03 cannot be satisfied until one is written with an ORM-level
composite key. Second, the Firebase SDK **raises `ValueError` from the `provider_data` property
itself** when a providerData entry carries an empty `rawId`, so §02 step 9's "missing/empty uid"
branch never reaches the classifier as data; the adapter must catch it inside the offloaded call.
Third — and this settles the CONTEXT's open discretion item — the "consume-first" race-loser
mechanism **does not work**: an `IntegrityError` poisons the entire SQLAlchemy session, so the
post-conflict consume and audit writes both fail. A `begin_nested()` savepoint around the business
inserts is required, and it was verified working under the e2e harness's exact
`join_transaction_mode="create_savepoint"` configuration.

The retry story also needs a correction to the CONTEXT's framing: `FirebaseAdminAdapter.get_user_provider_data`
**returns** a `ProviderDataResult` outcome rather than raising, so D-04's `retry_if_exception_type`
is the wrong tenacity predicate — `retry_if_result` is the right one, and result-based exhaustion
raises `RetryError` regardless of `reraise=True`, so a `retry_error_callback` is mandatory.

**Primary recommendation:** Sequence the phase as (1) `uv lock` + `tenacity` dependency commit,
(2) the `StorePurchaseToken` model + `SubscriptionProvider` enum, (3) the adapter + classifier +
tenacity policy, (4) errors + registry + route + prepare handler, (5) the completion handler and its
savepoint-wrapped consuming transaction, (6) the independent `resilience.py` conversion in its own
revertible commit. Put criteria 3 and 4 in `tests/schema/`, which already owns a disposable scratch
database and is the only harness in the repo that can commit for real.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Firebase ID token acceptance, `(issuer, subject)` resolution, pre-auth admission | Barrier middleware (`auth/barrier.py`) | — | SHARED-INVARIANTS § The barrier: "JWT acceptance and identity resolution happen ONLY in the shared, mandatory, default-on pre-handler barrier." Already built; the handler consumes `PreAuthIdentity` and re-verifies nothing. |
| Mode-signal partition (prepare vs completion vs `invalid_request`) | Route handler, via `auth/modesignal.py` | — | §6.5's shared syntactic check. Foundation ships it; the handler owns dispatch only. |
| Challenge issue / locate / claim / consume / binding verification | `auth/challenges.py` (`ChallengeStore`) | — | The claim is the single serialization point. No handler-side locking, mutex, or second expiry check. |
| Firebase `getUser` providerData read | Concrete adapter (new, off-loop via threadpool) | tenacity retry policy | §7's adapter rules bind: no provider call under a lock, fixed 5–10s per-attempt timeout, never leak provider text. |
| providerData → `IdentityProvider` classification | New classifier module (this phase) | — | `adapters.py:84-86` states the rule explicitly: "The **classification rule itself is phase 02's**, not foundation's". |
| Account creation (users + identity + attribution tokens) | Consuming transaction in the handler | PostgreSQL constraints as the sole race arbiter | §02 step 12: `UNIQUE (issuer, subject)` + `UNIQUE (user_id)` are the ONLY arbiters. No advisory lock, no serializable isolation. |
| Race arbitration and conflict classification | PostgreSQL (DB) | Handler, reading `constraint_name` | The DB decides; the handler only *names* which constraint fired to pick the client class. |
| Audit row for the terminal outcome | `auth/audit.py` (`AuditWriter`) | — | In-consuming-transaction mode for post-claim outcomes; standalone-durable for earlier rejections. |
| Client error surface | `errors.py` registry | — | SHARED-INVARIANTS § Errors: "No phase defines its own response shape or exception handler". |
| Request-rate limiting | Envoy Gateway (out of repo) | — | D-01. Nothing backend-side, by decision. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `firebase-admin` | `7.3.0` installed; `>=7.3.0` declared at `pyproject.toml:24`; `7.5.0` latest on PyPI | The `getUser(subject)` providerData read (§02 step 8) | Google's own Admin SDK; the only supported server-side Firebase Auth client. [VERIFIED: pypi.org/pypi/firebase-admin/json — latest 7.5.0, uploaded 2026-07-02] |
| `tenacity` | `9.1.4` — latest on PyPI, already installed transitively via langchain | The 3-attempt Firebase retry (D-04) and the `resilience.py` conversion (D-05) | Already resident in the dependency tree (`uv.lock:1540-1545`); promotion to a direct dependency adds no new wheel. [VERIFIED: pypi.org/pypi/tenacity/json — latest 9.1.4, uploaded 2026-02-07] |
| `starlette` | `0.52.1` installed (via FastAPI 0.135.1) | `run_in_threadpool` for the blocking Admin call (D-07) | Already the house rule — plan 35-12 pinned it, and `barrier.py:123` already uses it for `jwt_verifier.verify`. |
| `sqlmodel` / SQLAlchemy async | `sqlmodel >=0.0.22` | The consuming transaction, savepoints, ORM inserts | v1.6 convention: zero raw `text()` SQL. |
| `asyncpg` | `>=0.30` | Driver; supplies `UniqueViolationError.constraint_name` | The discriminator between `identity_already_linked` and `provider_account_already_linked` (Code Example 5). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | `>=0.28` (dev group) | The `accounts:signUp` anonymous-user fixture (D-09) | Test-only. `tests/e2e/conftest.py:50` already calls Identity Toolkit this way. |
| `structlog` | `>=25.5` | The fail-closed structured security log | Already wired; `record_rejection` in `auth/telemetry.py` is the existing seam. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `firebase-admin` + threadpool | Identity Toolkit REST over `httpx` | Natively async with per-call `timeout=`, but costs a service-account token-minting dependency and makes you own the error taxonomy. **Rejected by D-07 — do not revisit.** |
| `tenacity` | Keeping `BudgetGate` | Its multi-name all-or-nothing protocol has one name left after D-02 and degenerates to `stop_after_attempt(3)`. **Retired by D-04.** |
| `begin_nested()` savepoint | Consume-first without a savepoint | Empirically **does not work** — see Pitfall 1. Not a tradeoff; a correctness failure. |
| `begin_nested()` savepoint | `INSERT … ON CONFLICT DO NOTHING RETURNING` | Avoids the exception entirely, but cannot undo the already-inserted `core.users` row without an explicit `DELETE`, and cannot distinguish which of the three unique constraints would have fired. Savepoint is strictly simpler. |

**Installation:**

```bash
# D-06: one dependency-scoped commit. Add tenacity to [project].dependencies in pyproject.toml, then:
uv lock
uv sync
# Commit pyproject.toml + the FULL uv.lock diff (tenacity as a direct dep, 1.5.0 -> 1.6.0, revision 2 -> 3)
```

**Version verification:**

```bash
.venv/bin/python -c "import tenacity, firebase_admin; print(tenacity.__version__, firebase_admin.__version__)"
# tenacity 9.1.4 / firebase-admin 7.3.0 -- both confirmed installed 2026-08-22
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `tenacity` | PyPI | latest release 2026-02-07; project predates 2013 | unavailable via PyPI API | github.com/jd/tenacity | `SUS` (reason: `unknown-downloads` only) | **Approved** — already in `uv.lock:1540` transitively via langchain; repo matches the canonical upstream; confirmed via Context7 `/jd/tenacity` (High reputation). |
| `firebase-admin` | PyPI | latest release 2026-07-02 | unavailable via PyPI API | github.com/firebase/firebase-admin-python | `SUS` (reason: `unknown-downloads` only) | **Approved** — already a declared direct dependency at `pyproject.toml:24` and installed in `.venv`; official Firebase org repo; confirmed via Context7 `/firebase/firebase-admin-python` (High reputation). |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** both, for the single reason `unknown-downloads` — the PyPI JSON API does not expose weekly download counts, so *every* PyPI package scores this way. Neither is a novel introduction: both are already resolved in `uv.lock` and importable in the project venv, and both were cross-confirmed against Context7-indexed official documentation. **No `checkpoint:human-verify` task is warranted.** The planner should record this reasoning rather than re-deriving it.

**No new third-party package is introduced by this phase.** `tenacity` is a promotion from transitive to direct.

## Architecture Patterns

### System Architecture Diagram

```
   POST /auth/create-user            POST /auth/create-user?challenge=true
   { challenge_id, provider }        { provider? }
              │                                  │
              └──────────────┬───────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │ RequestLoggingMiddleware     │   (outermost)
              └──────────────┬───────────────┘
                             ▼
              ┌──────────────────────────────┐   route metadata read BEFORE dispatch
              │ AuthBarrierMiddleware        │   → operation=create_user, preauth_callable=True
              │  wire contract → verify(JWT) │───reject──▶ auth_required / account_unavailable
              │  → resolve_identity()        │            (audit row written standalone)
              └──────────────┬───────────────┘
                             │ Admit(PreAuthIdentity | LinkedIdentity)
                             ▼
              ┌──────────────────────────────┐
              │ create_user route handler    │
              │  parse body                  │
              │  classify_mode_signal()      │──None──▶ invalid_request 400
              └───────┬──────────────┬───────┘          (NO audit row, NO internal result)
                      │              │
              PREPARE │              │ COMPLETION
                      ▼              ▼
      ┌───────────────────┐   ┌──────────────────────────────────────────────┐
      │ already-linked?   │   │ 3. locate(challenge_id)      ─┐               │
      │  → identity_      │   │ 4. verify_binding()           │ pre-claim:    │
      │    already_linked │   │    + operation == create_user │ NO consume    │
      │ normalize provider│   │ 5. claim()  ◀── the ONLY      ─┘               │
      │ issue()  ──────┐  │   │    expiry evaluation                          │
      │ commit         │  │   │ 6. variant match? ── no ──▶ consume + reject  │
      └────────────────┼──┘   └──────────────┬───────────────────────────────┘
                       │                     │  (transaction CLOSED here)
                       ▼                     ▼
        { challenge_id,          ┌────────────────────────────────┐
          expires_at }           │ tenacity policy, 3 attempts    │
        Cache-Control: no-store  │  run_in_threadpool(            │
                                 │    adapter.get_user_provider_  │──▶ Firebase Admin
                                 │    data(issuer, subject))      │◀── ProviderDataResult
                                 └──────────────┬─────────────────┘
                                                │ NO DB session open across this call
                                   ┌────────────┴─────────────┐
                          user_not_found              ok / retryable exhausted
                                   │                          │
                          auth_required            ┌──────────▼───────────┐
                                                   │ closed classifier    │
                                                   │ [] → anonymous       │
                                                   │ 1×google.com → google│
                                                   │ 1×apple.com  → apple │
                                                   │ else → REJECT        │
                                                   └──────────┬───────────┘
                                                   declaration match?
                                              no ──▶ create_flow_mismatch 409
                                                     + required_flow
                                                              │ yes
                                 ┌────────────────────────────▼─────────────────────────┐
                                 │ CONSUMING TRANSACTION (database-only, no network)     │
                                 │  10. re-resolve (issuer, subject) INSIDE              │
                                 │  ┌── SAVEPOINT (begin_nested) ──────────────────┐     │
                                 │  │ INSERT core.users                            │     │
                                 │  │ INSERT core.external_identities (ACTIVE)     │     │
                                 │  │ INSERT core.store_purchase_tokens × 2        │     │
                                 │  └── IntegrityError ─▶ ROLLBACK TO SAVEPOINT ───┘     │
                                 │       read constraint_name → which client class        │
                                 │  13. consume(challenge_id, claim_attempt_id)          │
                                 │      audit.write_in_transaction(...)                  │
                                 │  COMMIT  ← consume + audit survive the business rollback│
                                 └────────────────────────────┬─────────────────────────┘
                                                              ▼
                                      200 { identity_provider }  |  409 identity_already_linked
                                                                 |  403 operation_not_allowed
```

### Component Responsibilities

| File | New / Existing | Responsibility |
|------|---------------|----------------|
| `auth/firebase.py` (name is discretion) | **new** | Concrete `FirebaseAdminAdapter`: issuer→named-app selection, `run_in_threadpool` offload, exception→`ProviderDataOutcome` mapping. **Must not live in `auth/adapters.py`** — `tests/unit/test_adapter_interfaces.py` asserts that module declares no function at all. |
| `auth/classifier.py` (name is discretion) | **new** | §02 step 9's closed providerData classifier + declaration match + `required_flow` derivation. |
| `auth/retry.py` or inline | **new** | The one tenacity policy (`stop_after_attempt(3)`, `retry_if_result`, `retry_error_callback`). Shared idiom with `resilience.py` per D-05. |
| `routers/auth.py` (name is discretion) | **new** | The route, the two mode handlers, the consuming transaction. |
| `models/subscriptions.py` (name is discretion) | **new** | `SubscriptionProvider` enum + `StorePurchaseToken` model. |
| `auth/registry.py` | edit | One `RouteMetadata` entry. Must land in the **same commit** as the router registration (`assert_route_enumeration` is set-equality at startup). |
| `errors.py` | edit | Three appended classes + three `ErrorCode` Literal members. |
| `app/dependencies.py` | edit | Expose adapter + challenge store to the handler. |
| `app/lifespan.py` | edit | Build the issuer-keyed Firebase app; fail closed at boot on a missing/invalid credential. |
| `config.py` | edit | `FirebaseConfig` model. **Do not add a `firebase:` block to `config/config.yaml`** (see Pitfall 7). |
| `auth/budgets.py`, `tests/unit/test_budgets.py` | **delete** | D-04. |
| `resilience.py` | edit, **own plan + own commit** | D-05. |

### Pattern 1: Body-first, then mode signal

`classify_mode_signal(raw_query, body_challenge_id)` takes the *raw ASGI query bytes* and the
already-parsed body value. The handler must therefore read the body **before** classifying, and must
not let FastAPI's Pydantic validation reject a malformed `challenge_id` first — §02 pins those cases
to `invalid_request` (400) with no audit row, while a Pydantic failure would surface as
`validation_error` (422).

**What:** Declare the request body as a permissive model (all fields optional, `challenge_id: object`
or `Any`), then hand the value to `classify_mode_signal`.
**When to use:** Every challenge-bearing endpoint (37, 40, 41, 42).
**Why:** `classify_mode_signal`'s own docstring pins the reason.

```python
# Source: src/nativespeaker/api/auth/modesignal.py:45-48 (verbatim docstring)
#   "`body_challenge_id` is whatever the parsed request body carried under `challenge_id`, typed
#    `object` on purpose: a client can put anything there, and a signature promising `str | None`
#    would push the wrong-type case onto every caller."
```

Reading the raw query string requires the ASGI scope. Routes are `Depends()`-only by convention
(v1.3), and `RequestContext` does **not** carry the query string — so either take `Request` for this
one route (a documented deviation) or add a small `Depends()` accessor that returns
`request.scope["query_string"]`. **Recommend the accessor**: it keeps the handler signature
`Depends()`-only and gives phases 40/41/42 the same seam.

### Pattern 2: Result-based tenacity retry over a threadpool-offloaded sync adapter

The adapter's `get_user_provider_data` **returns** `ProviderDataResult` and does not raise — so the
retry predicate is `retry_if_result`, not `retry_if_exception_type`. This corrects D-04's phrasing.

**When to use:** Any adapter seam in this codebase that returns a closed outcome enum rather than
raising (all three §7 adapters do).
**Why:** `retry_if_exception_type` would never fire, and the 3-attempt budget would silently become
a 1-attempt one.

### Pattern 3: Savepoint-wrapped business mutation inside the consuming transaction

**What:** Wrap the users + identity + attribution-token inserts in `await session.begin_nested()`.
On `IntegrityError`, `await savepoint.rollback()`, classify by `constraint_name`, then run the
consume and the audit write on the still-live outer transaction and commit.
**When to use:** Every path where a rejection must be durable while a business mutation rolls back —
§02 step 12 here, and phases 40/41/42 inherit it.
**Why:** Verified empirically (Pitfall 1). This is the same instinct as Phase 34's recorded decision:
"Savepoint-scoped rejection helper, because a rejected statement aborts the whole transaction and
blocks any post-rejection query" [VERIFIED: `.planning/STATE.md:131`].

### Pattern 4: Issuer-keyed named Firebase app, initialized once at boot

`firebase_admin.initialize_app(credential, options, name=...)` returns an `App`; every call site then
passes `app=`. Selection is an explicit dict lookup keyed on the request-verified issuer, with a
`KeyError` → `selection_failure` (never a fallback).

### Anti-Patterns to Avoid

- **Calling `firebase_admin.initialize_app()` with no credential.** Falls back to Application Default
  Credentials, which in local dev silently picks up the developer's gcloud user credentials. SHARED-
  INVARIANTS § Wire contract: "No ambient, default, global, or fallback client exists". D-08 rejects
  this explicitly.
- **Calling `auth.get_user(uid)` without `app=`.** Uses the `[DEFAULT]` app — the same ambient-client
  violation. **Do not initialize a `[DEFAULT]` app at all**, so this mistake fails loudly.
- **Retrying on `user_not_found`.** `ProviderDataOutcome.user_not_found` is documented as
  "Definitive and **non-retryable**: it spends no retry budget and rejects immediately" [VERIFIED:
  `src/nativespeaker/api/auth/adapters.py:52-54`]. It maps to `firebase_user_unresolved` → `auth_required`,
  **not** `verification_temporarily_unavailable`.
- **Taking the first recognized providerData entry.** §02 step 9: "Never take the first recognized
  entry; never classify non-empty providerData as anonymous; never read `firebase.sign_in_provider`."
- **Writing a `compare_digest` in the handler.** `HmacKeyring.actor_subject_matches` is the only
  permitted comparison — `challenges.py:232-236` states this is deliberate.
- **Re-checking `expires_at` anywhere but `ChallengeStore.claim`.** "`expires_at > now` in this WHERE
  is the **only** expiry evaluation in the entire protocol" [VERIFIED: `challenges.py:174`].
- **Recomputing `evaluated_at` or `attempt_id`.** 35 D-02; both are on `RequestContext`.
- **Using `rowcount` for any conditional update.** Not dependable under `join_transaction_mode="create_savepoint"`
  [VERIFIED: `challenges.py:176-178`]. Use `.returning(...)` and count rows.
- **Creating any grant, free credit, or `core.user_monthly_usage` row.** §02 step 10 forbids it
  outright; the new account correctly answers `quota_exceeded` on its first chat until Phase 41/42.
- **Putting the concrete adapter in `auth/adapters.py`.** `tests/unit/test_adapter_interfaces.py`
  asserts `test_the_module_declares_no_function_at_all` and `test_no_class_defines_a_method_body`.
- **Logging or auditing the public `challenge_id`.** Correlate on `AuthChallenge.id`; the redactor
  already drops any key containing the fragment `"challenge_id"` [VERIFIED: `auth/audit.py:94`].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 3-attempt retry with a non-retryable escape | A counter loop, or keeping `BudgetGate` | `tenacity` — `stop_after_attempt(3)` + `retry_if_result` | D-04. Same reasoning that retired `RejectionCounter` in Phase 36 (commit 5f275c8). |
| Challenge issue/claim/consume/expiry | Anything | `ChallengeStore` | Built, e2e-tested, and encodes §6 rules the handler must not re-derive. |
| Mode-signal partition | A `request.query_params.get("challenge")` check | `classify_mode_signal()` | A first-value-wins accessor cannot see the duplicate-parameter case §02 pins to `invalid_request`. |
| Subject hashing / comparison | `hmac.compare_digest` | `HmacKeyring.actor_subject_hash` / `.actor_subject_matches` | One shared key, one derivation (35 D-21). Two derivations both produce plausible 32-byte digests; only one matches stored rows. |
| Audit row construction & redaction | A dict literal | `build_details()` + `AuditWriter.write_in_transaction` | The builder is keyword-only so a seventh key is a `TypeError` at the call site rather than a CHECK violation at insert. |
| Duplicate-account detection | A pre-SELECT then INSERT | The DB's `UNIQUE (issuer, subject)` | §02 step 12: those constraints "are the ONLY arbiters". A check-then-insert has a window; the constraint does not. |
| Error responses | A new response model | `errors.register_class` + `error_response` | SHARED-INVARIANTS § Errors; `assert_registry_total()` fails boot on a mismatch. |
| Firebase token verification in the handler | Anything | Nothing — the barrier did it | The handler receives `PreAuthIdentity`; re-verifying is forbidden. |

**Key insight:** In this phase, "don't hand-roll" mostly means "don't re-derive what Phase 35 already
proved." The scout's table in CONTEXT.md is accurate: every seam listed there is complete. The one
place the codebase genuinely lacks machinery — the store-purchase-token model — is invisible from the
spec, which is exactly why it is the likeliest thing to be discovered mid-execution.

## Runtime State Inventory

> Included because D-04 deletes a module and D-05 refactors a live request path.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None.** No existing `core.users`, `core.external_identities`, or `core.store_purchase_tokens` rows originate from `src/` — `tests/e2e/conftest.py:174` states verbatim: "`core.users` rows originate from `POST /auth/create-user` in Phase 37." Pre-launch, disposable data. | none |
| Live service config | **None.** `k8s/` is untouched (35 D-08 defers §9); the v1.6 Envoy chart is unmodified by this phase. No dashboards or external workflows reference `budgets.py` or `resilience.py` symbols. | none |
| OS-registered state | **None.** No scheduler entries, no pm2/systemd units in this repo. | none |
| Secrets / env vars | **One addition.** A Firebase service-account JSON must be added to the gitignored `.env` (D-08). **Verified absent today**: no `service_account` / `private_key_id` string exists anywhere under `config/` or in `.env`. Existing `.env` keys are `CONFIG_DIR`, `APPLE_CERTS_DIR`, `POSTGRES_*`, `DB_*`, `OPENAI_API_KEY`, `JWT_PROJECT_ID`, `JWT_API_KEY`, `FIREBASE_TEST_EMAIL`, `FIREBASE_TEST_PASSWORD`. | **Human action, blocking.** See *Environment Availability*. Also update the Helm chart's Secret env list (v2.1 scope note: chart edits are out of scope per 35 D-08 — record as a deferred item rather than doing it here). |
| Build artifacts / installed packages | `src/ns_api_gateway.egg-info/` and the editable install must be refreshed after the `uv lock` commit. `uv.lock` currently carries **uncommitted** working-tree edits (`version = 1.5.0 → 1.6.0`, `revision = 2 → 3`) [VERIFIED: `git diff uv.lock`]. `docker-compose.yml` is also dirty and is **explicitly not owned** by D-06. | `uv sync` after the D-06 commit. Leave `docker-compose.yml` alone. |
| Deleted-symbol references | `auth/budgets.py` exports `ADAPTER_FIREBASE_LOOKUP`, `FIREBASE_LOOKUP_ATTEMPTS`, `BudgetExhausted`, `BudgetGate`. `auth/adapters.py:22-26` documents the budget wiring in prose and names `auth.budgets`. | Grep for `budgets` across `src/` and `tests/` before deleting; update the `adapters.py` module docstring in the same commit so it does not name a module that no longer exists. |

## Common Pitfalls

### Pitfall 1: "Consume-first" cannot survive an IntegrityError — the session is poisoned

**What goes wrong:** The CONTEXT's default race-loser mechanism (consume-first atomic conditional
update, no savepoint) fails. After the duplicate `core.external_identities` insert raises
`IntegrityError`, SQLAlchemy marks the session's transaction as rolled back. Every subsequent
statement — including `ChallengeStore.consume` and `AuditWriter.write_in_transaction` — raises
`PendingRollbackError`, and so does `commit()`. §02 step 12's "challenge consumption + rejected audit
row MUST survive the business rollback" is then violated, and the client gets a generic 500 — which
step 12 explicitly forbids ("The uniqueness violation must never escape as a generic 500").

**Why it happens:** PostgreSQL aborts the entire transaction on any statement error; SQLAlchemy
mirrors that by requiring an explicit rollback before further work. Consuming *earlier* in the same
transaction does not help — the abort rolls the consume back too.

**How to avoid:** `savepoint = await session.begin_nested()` around the business inserts;
`await savepoint.rollback()` in the `except IntegrityError` arm. The outer transaction stays live.

**Verified empirically, 2026-08-22, against the live PostgreSQL 17.11 and the *exact* e2e harness
configuration (`join_transaction_mode="create_savepoint"`):**

```
# WITHOUT savepoint:
caught IntegrityError (no savepoint)
post-error query FAILED -> PendingRollbackError
commit FAILED -> PendingRollbackError

# WITH begin_nested():
caught IntegrityError; orig.__cause__ = UniqueViolationError | constraint_name = external_identities_issuer_subject_key
post-rollback query WORKS, rows = 1
session.commit() after savepoint rollback: OK
```

**Warning signs:** `PendingRollbackError` in a test; a 500 where the test expected 409.

**Note for the planner:** this *reverses* the CONTEXT's stated default and its stated rationale
("it avoids savepoint nesting under the e2e harness's `join_transaction_mode='create_savepoint'`").
Savepoint nesting under that harness was directly tested and works. Record the reversal explicitly.

### Pitfall 2: `core.store_purchase_tokens` has no primary key and no SQLModel class

**What goes wrong:** CREATE-03 requires "both purchase-attribution tokens" in the create transaction.
There is no model to insert. Naively adding `class StorePurchaseToken(SQLModel, table=True)` fails at
import with SQLAlchemy's *"could not assemble any primary key columns"*.

**Why it happens:** The table is deliberately PK-less. Verbatim from
`migrations/20260818_01_initial-release.sql:327-338`:

```sql
-- Intentionally has NO primary key; its two UNIQUE constraints carry the rules - one
-- attribution token per user per store for the account's life, and one owner per
-- (provider, identity_value). The value is a random, opaque, server-generated,
-- non-secret UUID that is never rotated and survives the anonymous-to-registered upgrade.
CREATE TABLE core.store_purchase_tokens (
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    provider core.subscription_provider NOT NULL,
    identity_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider),
    UNIQUE (provider, identity_value)
);
```

**How to avoid:** Declare an **ORM-level composite primary key** on `(user_id, provider)` — the pair
the table's own UNIQUE already makes unique. SQLAlchemy only needs a key it can identify a row by;
it does not require the database to declare one. **Do not add a `PRIMARY KEY` to the migration** —
v2.0 forbids incremental migrations [VERIFIED: `.planning/REQUIREMENTS.md:16` SCHEMA-01: "no
incremental migration files are added"] and the PK-less shape is a documented ruling.

Also missing: a Python mirror of `core.subscription_provider`. Verbatim from
`migrations/20260818_01_initial-release.sql:54`:

```sql
CREATE TYPE core.subscription_provider AS ENUM ('apple', 'google_play');
```

Nothing in `src/nativespeaker/api/models/` declares it — `models/__init__.py`'s `__all__` lists 27
names and neither `SubscriptionProvider` nor `StorePurchaseToken` is among them [VERIFIED:
`src/nativespeaker/api/models/__init__.py:1-8`]. The two token rows use provider `apple` (carrying
Apple's `app_account_token`) and `google_play` (carrying Google's `obfuscated_external_account_id`),
each a fresh server-generated UUID in `identity_value`.

**Warning signs:** An import-time `ArgumentError` mentioning primary key columns; a plan task that
says "insert the attribution tokens" with no preceding model task.

### Pitfall 3: `UserRecord.provider_data` raises `ValueError` — the empty-uid branch never reaches the classifier

**What goes wrong:** §02 step 9 says "missing/empty uid = malformed/indeterminate lookup → reject, no
persistence." A classifier written to check `if not entry.uid` will never see that case, because the
SDK raises first — and it raises from a *lazy property*, so the exception surfaces wherever
`.provider_data` is first touched. If that is on the event loop after the threadpool call returns, it
escapes the tenacity policy entirely and becomes an unhandled 500.

**Why it happens:** Verbatim from
`.venv/lib/python3.14/site-packages/firebase_admin/_user_mgt.py:246-256` and `:455-466`:

```python
    @property
    def provider_data(self):
        """Returns a list of UserInfo instances.
        ...
        """
        providers = self._data.get('providerUserInfo', [])
        return [ProviderUserInfo(entry) for entry in providers]
```

```python
    def __init__(self, data):
        super().__init__()
        if not isinstance(data, dict):
            raise ValueError(f'Invalid data argument: {data}. Must be a dictionary.')
        if not data.get('rawId'):
            raise ValueError('User ID must not be None or empty.')
        self._data = data

    @property
    def uid(self):
        return self._data.get('rawId')
```

**How to avoid:** Materialize `provider_data` into `tuple[ProviderDataEntry, ...]` **inside** the
function passed to `run_in_threadpool`, wrapped in `except ValueError` → `ProviderDataOutcome.retryable_failure`
(§02 step 8 classifies "malformed/indeterminate response" as retryable). The adapter must return the
foundation's own frozen dataclasses, never the SDK objects — `adapters.py:78-91` defines
`ProviderDataEntry(provider_id: str, uid: str)` for exactly this reason.

**Warning signs:** A 500 on a Firebase edge case that a fake-adapter test cannot reproduce, because
the fake returns pre-built `ProviderDataEntry` objects and never exercises the SDK's constructor.

### Pitfall 4: tenacity result-based exhaustion always raises `RetryError`, even with `reraise=True`

**What goes wrong:** `reraise=True` re-raises the *original exception*. With `retry_if_result` there
is no exception — the attempts merely returned an unacceptable value — so exhaustion raises
`RetryError` regardless. A handler written to expect a `ProviderDataResult` back gets an exception it
does not catch, and the `firebase_lookup_unavailable` → `verification_temporarily_unavailable`
mapping D-04 requires to be "preserved exactly" is lost.

**How to avoid:** Supply `retry_error_callback=lambda retry_state: retry_state.outcome.result()`, so
the last `ProviderDataResult` is returned rather than raised. Then map
`outcome is retryable_failure` → `AuthEventResult.firebase_lookup_unavailable` →
`VERIFICATION_TEMPORARILY_UNAVAILABLE`, exactly as `budgets.py:65-66` declares it today:

```python
    audit_result: AuthEventResult = AuthEventResult.firebase_lookup_unavailable
    error_class: ErrorClass = VERIFICATION_TEMPORARILY_UNAVAILABLE
```

**Warning signs:** An uncaught `tenacity.RetryError` producing a 500 instead of a 503.

### Pitfall 5: `identity_already_linked` and `provider_account_already_linked` are different client classes and must be told apart by constraint name

**What goes wrong:** Both are `IntegrityError`s from the same `INSERT` into `core.external_identities`,
but §02 routes them to different client classes — `identity_already_linked` (step 12, remediation
`/auth/sync`) versus `operation_not_allowed` (step 11, routed to support). Collapsing them is a
client-contract bug; discriminating on the exception's *message string* is brittle and locale-fragile.

**How to avoid:** Read `exc.orig.__cause__.constraint_name` (asyncpg populates it for both table-level
UNIQUE constraints and standalone unique *indexes* — verified empirically, see Code Example 5). The
live names, queried from the running database on 2026-08-22:

| `constraint_name` | Definition | Internal result | Client class |
|---|---|---|---|
| `external_identities_issuer_subject_key` | `UNIQUE (issuer, subject)` | `identity_already_linked` | `identity_already_linked` (409) |
| `external_identities_user_id_key` | `UNIQUE (user_id)` | `identity_already_linked` | `identity_already_linked` (409) |
| `ix_external_identities_provider_account` | `UNIQUE (issuer, provider, provider_uid) WHERE provider_uid IS NOT NULL` | `provider_account_already_linked` | `operation_not_allowed` |
| `external_identities_check` | the provider/provider_uid agreement CHECK | — | a programming error; must be unreachable |

**Warning signs:** A test asserting 409 that gets 403, or vice versa; any `str(exc)` parsing.

### Pitfall 6: `invalid_request` must not be reachable through Pydantic validation

**What goes wrong:** §02 pins mode-signal violations to `invalid_request` (400) with **no audit row
and no internal result**. If the request body model declares `challenge_id: str | None`, a client
sending `challenge_id: 123` gets FastAPI's 422 `validation_error` instead — a different status, a
different code, and a class §02 never names for this route.

**How to avoid:** Type the body field permissively and let `classify_mode_signal` own the rejection.
Its docstring makes this explicit (quoted in Pattern 1). Note the deliberate asymmetry it encodes:
whitespace-padded handles are **not** `invalid_request` — `modesignal.py:61-64` states "A handle with
stray whitespace is `challenge_not_found`, not `invalid_request`."

### Pitfall 7: `config/config.yaml` silently outranks `.env` — the Firebase block must not appear there

**What goes wrong:** Adding a `firebase:` block to `config/config.yaml` to "document the shape" makes
the YAML authoritative and the `.env` value unreachable — and, worse, puts real key material in a
tracked file, defeating D-08's whole purpose.

**Why it happens:** Verbatim from `config/config.yaml:26-31`:

```
# The YAML is authoritative for anything it declares: AppConfig is built as AppConfig(**yaml_data,
# ...) and pydantic-settings ranks init_settings above env_settings, so no environment variable
# can override a key declared here. The Secret Manager follow-up must REMOVE these entries, not
# shadow them.
```

**How to avoid:** Declare `firebase: FirebaseConfig` on `AppConfig` and populate it from `.env` only.
The env-var naming follows the existing nesting rule — `BaseConfig` sets
`env_nested_delimiter="_"` with `env_nested_max_split=1` [VERIFIED: `src/nativespeaker/api/config.py:21-23`],
which is how `JWT_PROJECT_ID` reaches `jwt.project_id` and `DB_HOST` reaches `db.host`. So
`FIREBASE_SERVICE_ACCOUNT_JSON` reaches `firebase.service_account_json`.

**Warning signs:** A Firebase key appearing in `git diff config/config.yaml`.

### Pitfall 8: The existing e2e credential can only ever exercise the rejection arm

**What goes wrong:** A completion test written against `firebase_token` "passes" while testing the
`create_flow_mismatch` path. `tests/e2e/conftest.py:50-56` signs in with
`accounts:signInWithPassword`, so `providerData == [{providerId: "password"}]` — an unrecognized
single entry, which §02 step 9's closed classifier rejects.

**How to avoid:** Exactly D-09's split. The new anonymous fixture mirrors the existing REST idiom;
the endpoint is `POST https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={api_key}` with
`{"returnSecureToken": true}` and **no** `email`/`password`. Google's Identity Platform reference for
`accounts.signUp` states of the `email` field: *"An anonymous user will be created if not provided."*
[CITED: docs.cloud.google.com/identity-platform/docs/reference/rest/v1/accounts/signUp]

**Warning signs:** A green completion test that never asserts a 200; a test whose fixture is
`firebase_token` and whose name says "success".

### Pitfall 9: The registry entry and the router registration must land in one commit

**What goes wrong:** Adding the route without the `RouteMetadata` entry (or vice versa) aborts boot —
every test in the suite fails, not just the new ones.

**Why it happens:** `assert_route_enumeration` reports both directions [VERIFIED:
`src/nativespeaker/api/auth/registry.py:162-165`]:

```python
    if extra := registered - declared:
        problems.append(f"registered but undeclared: {sorted(extra)}")
    if missing := declared - registered:
        problems.append(f"declared but unregistered: {sorted(missing)}")
```

**How to avoid:** One task, one commit, both files. Also note `assert_route_enumeration` performs
**local imports of concrete handler modules** at lines 141-142 to break an import cycle — if the new
router imports the registry, follow the same local-import discipline.

### Pitfall 10: No provider call may run while the consuming transaction is open

**What goes wrong:** Moving the `getUser` call inside the transaction "to keep it simple" converts
Firebase latency into a database-wide stall and violates SHARED-INVARIANTS § Locks.

**How to avoid:** §02 already sequences it correctly — the Admin lookup is step 8, the transaction
opens at step 10. Preserve that ordering literally. Note this also means the challenge **claim**
(step 5) and the **consume** (step 13) are in *different* transactions, with the provider call
between them. The claim must be committed before the provider call, or a crash mid-lookup leaves an
unclaimed challenge a second attempt could win — which contradicts §6.2's "a claimed challenge is
dead."

## Code Examples

### Example 1: The concrete Firebase Admin adapter (issuer-selected, offloaded, timeout-bounded)

```python
# Sources: /firebase/firebase-admin-python Context7 (initialize_app, get_user, httpTimeout);
#          firebase_admin/__init__.py:33 (_CONFIG_VALID_KEYS includes 'httpTimeout');
#          firebase_admin/credentials.py Certificate.__init__ (accepts a dict);
#          firebase_admin/_user_mgt.py:246-256, :455-466 (provider_data / ProviderUserInfo)
import json

import firebase_admin
from firebase_admin import auth, credentials, exceptions
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.adapters import (
    ProviderDataEntry, ProviderDataOutcome, ProviderDataResult,
)

# §7 preamble: "every outbound call carries a fixed configured per-attempt timeout on the order of
# 5-10 seconds" (adapters.py:16-17). httpTimeout is an APP-level option, so it is set once here --
# there is no per-call timeout knob in this SDK.
FIREBASE_HTTP_TIMEOUT_SECONDS = 8


def build_admin_apps(config) -> dict[str, firebase_admin.App]:
    """One named app per configured issuer. NO [DEFAULT] app is ever created, so a call site that
    forgets `app=` fails loudly instead of falling back to Application Default Credentials."""
    cert = credentials.Certificate(json.loads(config.service_account_json.get_secret_value()))
    app = firebase_admin.initialize_app(
        cert,
        {"projectId": config.project_id, "httpTimeout": FIREBASE_HTTP_TIMEOUT_SECONDS},
        name=f"issuer:{config.issuer}",
    )
    return {config.issuer: app}


class FirebaseAdmin:
    """Satisfies the FirebaseAdminAdapter Protocol structurally. Lives OUTSIDE auth/adapters.py."""

    def __init__(self, apps: dict[str, firebase_admin.App]) -> None:
        self._apps = apps

    async def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        app = self._apps.get(issuer)
        if app is None:
            # SHARED-INVARIANTS: "selection fails closed"; never fall back to another project.
            return ProviderDataResult(ProviderDataOutcome.selection_failure)
        return await run_in_threadpool(self._read, app, subject)

    @staticmethod
    def _read(app: firebase_admin.App, subject: str) -> ProviderDataResult:
        try:
            record = auth.get_user(subject, app=app)
            # Materialized HERE, inside the threadpool: `provider_data` is a lazy property that
            # constructs ProviderUserInfo, which raises ValueError on an empty rawId (Pitfall 3).
            entries = tuple(ProviderDataEntry(provider_id=e.provider_id, uid=e.uid)
                            for e in record.provider_data)
        except auth.UserNotFoundError:
            # Definitive, non-retryable, spends no budget (adapters.py:52-54).
            return ProviderDataResult(ProviderDataOutcome.user_not_found)
        except ValueError:
            # Malformed/indeterminate response -- §02 step 8 makes this retryable.
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        except exceptions.FirebaseError:
            # Outage or integration-auth failure. Provider text NEVER leaks to the client
            # (adapters.py:19-20) -- log it, do not attach it.
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        return ProviderDataResult(ProviderDataOutcome.ok, entries)
```

### Example 2: The tenacity retry policy (result-based, D-04)

```python
# Source: /jd/tenacity Context7 -- "Custom Callback to Return Last Value" and retry_if_result
from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt

from nativespeaker.api.auth.adapters import ProviderDataOutcome, ProviderDataResult

# §7.1: 3 attempts total -- the initial call plus up to two additional -- for retryable causes only.
# This constant replaces budgets.FIREBASE_LOOKUP_ATTEMPTS verbatim (budgets.py:50).
FIREBASE_LOOKUP_ATTEMPTS = 3


def _is_retryable(result: ProviderDataResult) -> bool:
    # ONLY retryable_failure. user_not_found and selection_failure are definitive and spend
    # no budget; ok is a success.
    return result.outcome is ProviderDataOutcome.retryable_failure


async def lookup_with_retry(adapter, issuer: str, subject: str) -> ProviderDataResult:
    """Never raises RetryError: `retry_error_callback` hands the last result back instead.

    `reraise=True` would NOT help here -- it re-raises an original *exception*, and a result-based
    retry has none, so exhaustion would still surface as RetryError (Pitfall 4).
    """
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        retry=retry_if_result(_is_retryable),
        retry_error_callback=lambda retry_state: retry_state.outcome.result(),
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
```

### Example 3: The closed providerData classifier (§02 step 9)

```python
from nativespeaker.api.auth.adapters import ProviderDataEntry
from nativespeaker.api.models.identities import IdentityProvider

# Exactly two recognized provider ids. Verbatim from §02 step 9: "no entries -> anonymous; exactly
# one google.com entry -> google; exactly one apple.com entry -> apple; every other shape ... reject".
_RECOGNIZED = {"google.com": IdentityProvider.google, "apple.com": IdentityProvider.apple}


def classify(entries: tuple[ProviderDataEntry, ...]) -> tuple[IdentityProvider, str | None] | None:
    """`None` means reject (internal `provider_not_linked`, invalid-shape cause -> operation_not_allowed).

    Returns (provider, provider_uid). provider_uid is None exactly for anonymous -- the table's CHECK
    requires NULL there and forbids a sentinel (migration ruling 9.2).
    """
    if not entries:
        return IdentityProvider.anonymous, None
    if len(entries) != 1:
        return None                      # both providers, or multiple entries -- never take the first
    provider = _RECOGNIZED.get(entries[0].provider_id)
    if provider is None:
        return None                      # unrecognized entry, e.g. the e2e fixture's "password"
    if not entries[0].uid:
        return None                      # belt-and-braces; the SDK raises first (Pitfall 3)
    return provider, entries[0].uid
```

### Example 4: The consuming transaction with a savepoint-wrapped business mutation

```python
# Verified working under join_transaction_mode="create_savepoint" (Pitfall 1 probe, 2026-08-22).
from sqlalchemy.exc import IntegrityError

_RACE_CONSTRAINTS = frozenset({
    "external_identities_issuer_subject_key",   # UNIQUE (issuer, subject)
    "external_identities_user_id_key",          # UNIQUE (user_id)
})
_PROVIDER_ACCOUNT_INDEX = "ix_external_identities_provider_account"


async def complete(session, ctx, identity, challenge_row, provider, provider_uid, email):
    # §02 step 10: re-resolve INSIDE the transaction. Prepare-time pre-auth status never suffices.
    existing = await find_identity(session, identity.issuer, identity.subject)
    result = evaluate_existing(existing)          # already_linked / historical / blocked / None

    if result is None:
        savepoint = await session.begin_nested()
        try:
            user = User(email=email,
                        registered_at=None if provider is IdentityProvider.anonymous
                        else ctx.evaluated_at)
            session.add(user)
            await session.flush()
            session.add(ExternalIdentity(user_id=user.id,
                                         issuer=identity.issuer,
                                         subject=identity.subject,
                                         provider=provider,
                                         provider_uid=provider_uid,
                                         identity_state=IdentityState.active,
                                         created_at=ctx.evaluated_at,
                                         updated_at=ctx.evaluated_at))
            # §02 step 10: minted EAGERLY on every branch, one row per store.
            for store in (SubscriptionProvider.apple, SubscriptionProvider.google_play):
                session.add(StorePurchaseToken(user_id=user.id, provider=store,
                                               identity_value=str(uuid4()),
                                               created_at=ctx.evaluated_at))
            await session.flush()
            await savepoint.commit()              # RELEASE SAVEPOINT
            result = AuthEventResult.succeeded
        except IntegrityError as exc:
            await savepoint.rollback()            # ROLLBACK TO SAVEPOINT -- outer txn stays LIVE
            result = _classify_conflict(exc)

    # Both of these run on the still-live outer transaction, on success AND rejection alike (step 13).
    await store.consume(session, challenge_id=challenge_row.challenge_id,
                        claim_attempt_id=ctx.attempt_id, now=ctx.evaluated_at)
    await writer.write_in_transaction(session, operation=AuthOperation.create_user, result=result, ...)
    await session.commit()
    return result
```

### Example 5: Discriminating the two conflict causes by constraint name

```python
# Empirically verified 2026-08-22 against PostgreSQL 17.11: asyncpg populates `constraint_name`
# for BOTH a table-level UNIQUE constraint and a standalone partial UNIQUE INDEX.
#   partial unique INDEX:      constraint_name='ix_t_partial'
#   table UNIQUE constraint:   constraint_name='t_b_key'
def _classify_conflict(exc: IntegrityError) -> AuthEventResult:
    cause = exc.orig.__cause__ if exc.orig is not None else None
    name = getattr(cause, "constraint_name", None)
    if name in _RACE_CONSTRAINTS:
        return AuthEventResult.identity_already_linked          # -> identity_already_linked (409)
    if name == _PROVIDER_ACCOUNT_INDEX:
        return AuthEventResult.provider_account_already_linked  # -> operation_not_allowed
    raise exc   # anything else is a programming error and must not be swallowed as a business branch
```

### Example 6: The anonymous Firebase test-user fixture (D-09)

```python
# Mirrors the existing REST idiom at tests/e2e/conftest.py:50-57.
# Google Identity Platform accounts.signUp: "An anonymous user will be created if not provided"
# (of the `email` field).
@pytest.fixture(scope="session")
def anonymous_firebase_token(_app_config):
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={_app_config.jwt.api_key}",
        json={"returnSecureToken": True},   # no email, no password -> anonymous
    )
    resp.raise_for_status()
    data = resp.json()
    return data["idToken"], data["localId"]
```

> **Note:** every completion this fixture drives creates a *real, permanent* Firebase anonymous user
> in the shared project. There is no cleanup path (SHARED-INVARIANTS deletes purge jobs). Accept the
> accumulation, or delete via `auth.delete_user` in the fixture teardown — the latter is a genuine
> Admin call and needs the credential to be present.

### Example 7: The `StorePurchaseToken` model over a PK-less table

```python
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import DateTime, Enum
from sqlmodel import Field, SQLModel


class SubscriptionProvider(StrEnum):
    """Mirrors `core.subscription_provider` -- exactly two values (migration:54)."""
    apple = "apple"
    google_play = "google_play"


SubscriptionProviderType = cast(Any, Enum(SubscriptionProvider, name="subscription_provider",
                                          schema="core"))
DateTimeType = cast(Any, DateTime(timezone=True))


class StorePurchaseToken(SQLModel, table=True):
    """The table has NO database primary key by design (migration:327-338). The composite key below
    is ORM-level only: SQLAlchemy needs a row identity, and `UNIQUE (user_id, provider)` already
    provides one. Do NOT add a PRIMARY KEY to the migration -- SCHEMA-01 forbids incremental
    migrations and the PK-less shape is a documented ruling.
    """

    __tablename__ = "store_purchase_tokens"
    __table_args__ = {"schema": "core"}

    user_id: UUID = Field(foreign_key="core.users.id", primary_key=True)
    provider: SubscriptionProvider = Field(sa_type=SubscriptionProviderType, primary_key=True)
    # A random opaque server-generated UUID: no PII, not derivable from identity, never rotated.
    identity_value: str = Field(unique=True)
    created_at: datetime = Field(sa_type=DateTimeType)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-rolled retry/counter machinery (`BudgetGate`, `RejectionCounter`) | Library primitives (`tenacity`) or derived-from-logs telemetry | Phase 36 (commit 5f275c8) established the precedent; D-04/D-05 extend it | Two hand-rolled subsystems removed across two phases; one retry idiom in the codebase instead of two |
| JIT user provisioning on any authenticated request (`get_current_user`) | `POST /auth/create-user` is the only account-creating path | Phase 35 D-16 deleted `get_current_user` | An unlinked caller now rejects everywhere except this route — CREATE-01 is structural, not enforced by convention |
| `firebase-admin` used for claim-sync with ADC at boot | No Firebase client at boot; issuer-selected named app behind the §7.1 seam | Phase 35 (`app/lifespan.py:66-69`) | This phase reintroduces Firebase, and must not reintroduce the ambient client |
| Five status codes / five opaque error codes (v1.3) | One shared registry, anti-oracle within class | Phase 35 D-09/D-11/D-12 | Three new classes are appended, not invented |

**Deprecated/outdated:**

- **`firebase-admin` async Auth support:** does not exist and is not coming.
  [firebase-admin-python#104](https://github.com/firebase/firebase-admin-python/issues/104) remains
  open; async landed for Firestore and messaging only. Executor offload is Google's own documented
  workaround. [CITED: github.com/firebase/firebase-admin-python/issues/104, via 37-CONTEXT.md D-07]
- **`https://www.googleapis.com/identitytoolkit/v3/relyingparty/signupNewUser`:** the legacy v3
  anonymous sign-up endpoint. Superseded by `identitytoolkit.googleapis.com/v1/accounts:signUp`;
  use the v1 form, matching what `tests/e2e/conftest.py:50` already does for password sign-in.
- **`auth/budgets.py`:** deleted this phase (D-04). Do not import it in new code.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `returnSecureToken: true` is accepted by `accounts:signUp` and is what returns an `idToken`. The Identity Platform reference lists `email`, `password`, `displayName`, `photoUrl`, `phoneNumber`, `disabled`, `emailVerified`, `idToken`, `localId`, `mfaInfo[]`, `clientType`, `recaptchaVersion` — **but not `returnSecureToken`**. The field is documented in the Firebase Auth REST reference and is already used successfully at `tests/e2e/conftest.py:55`. | Pitfall 8, Code Example 6 | Low. If the field is ignored, the response may lack `idToken`; the fixture would fail loudly on `data["idToken"]` at first run, not silently. |
| A2 | SQLAlchemy accepts an ORM-level composite primary key on a table whose database definition has none, and will `INSERT` correctly. This follows from SQLAlchemy's mapper contract (it needs an identity key, not a DDL constraint) but was **not** executed against this specific model. | Pitfall 2, Code Example 7 | Medium. If wrong, CREATE-03 needs a different approach (e.g. a Core `insert()` against a `Table` object rather than a mapped class). **The plan should prove this in its first task, before the handler depends on it.** |
| A3 | The three new error-class names are `identity_already_linked` (409), `create_flow_mismatch` (409, with the mandatory `required_flow` field), `operation_not_allowed` (403). Statuses: §02 pins 409 for `create_flow_mismatch` explicitly and pins "400/409/429/403" as the numerically-specified set; `identity_already_linked`'s and `operation_not_allowed`'s exact statuses are inferred from that set and from the existing registry's conventions. | Standard Stack, diagram | Medium. A wrong status is a published contract error — cheap to fix pre-launch, but it should be confirmed against §02 during planning rather than assumed. |
| A4 | `create_flow_mismatch` carrying a mandatory `required_flow` field extends `ErrorResponse`, whose docstring says "Exactly one field -- do not add more" [VERIFIED: `errors.py:50-52`]. The mechanism for that extension is **undecided** — a subclassed response model, or an `extra` payload on the class. | Architecture Patterns | Medium. This is the one place §02 requires a body shape the foundation registry deliberately forbids. **Flag as a decision the planner must make explicitly**, not discover. |
| A5 | The `httpTimeout` app option applies to `auth.get_user` calls (it is documented as "a global timeout for all remote API calls"). Not separately measured. | Code Example 1 | Low. Worst case the per-attempt bound is the 120s default; detectable by a slow test. |
| A6 | `firebase-admin 7.3.0` (installed) behaves as `7.5.0` (latest) for `get_user`/`provider_data`/`initialize_app`. All source quotes above are from the **installed 7.3.0**, so they are accurate for what will run. | Standard Stack | Low. Pin behavior to the installed version; do not upgrade in this phase. |

## Open Questions

1. **How does `create_flow_mismatch` carry `required_flow` through a one-field response model?**
   - What we know: §02 makes the field mandatory; `ErrorResponse` declares exactly one field and says
     not to add more; SHARED-INVARIANTS forbids a phase defining its own response shape.
   - What's unclear: whether the registry grows an optional per-class payload mechanism, or this one
     class gets a subclassed model registered alongside it.
   - Recommendation: treat as an explicit planning decision with a one-line rationale recorded. The
     narrower option (a `CreateFlowMismatchResponse(ErrorResponse)` subclass returned only by that
     class's raise site) touches less and does not weaken the anti-oracle guarantee, since
     `required_flow` is derived solely from the Admin classification and never from client input.

2. **Where do criteria 3 and 4 actually run?**
   - What we know: the e2e harness cannot express them (one outer transaction, savepoint-joined
     sessions share a connection). `tests/schema/` uses a **disposable scratch database created per
     session** with per-test asyncpg connections — so a test there can open two independent
     connections and commit for real, and the database is dropped at session end.
   - What's unclear: whether the create transaction's logic can be exercised from `tests/schema/`
     without importing the handler (that package deliberately does not import the app's config module).
   - Recommendation: put criterion 4 (concurrency) in `tests/schema/` driving the *transaction
     function* directly with two real sessions; put criterion 3 (forced mid-transaction failure) in
     `tests/unit` with a substituted session that raises on the second `flush()`, plus a
     `tests/schema/` check that no orphan `core.users` row survives. Do **not** add a second
     commit-for-real fixture to `tests/e2e/` — it would defeat the isolation every other module relies on.

3. **Is `verify_id_token` on the adapter Protocol needed at all this phase?**
   - What we know: `adapters.py:114-123` declares it, and notes the barrier does not call it.
   - What's unclear: whether Phase 37 has any call site for it.
   - Recommendation: implement it as a genuine method (the Protocol is structural, so an incomplete
     class simply does not satisfy it), but do not call it. The barrier's `TokenVerifier` remains the
     only verification path.

4. **Does the challenge claim get its own committed transaction?**
   - What we know: the claim (step 5) and the consume (step 13) sit on either side of the provider
     call, and no transaction may be open across it (Pitfall 10).
   - Recommendation: commit the claim in its own short transaction before the lookup. Record this
     explicitly — it is the reason a crashed attempt leaves a permanently-claimed dead row, which
     §6.2 says is the design.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | The whole phase; both test harnesses | ✓ | 17.11, `localhost:5432`, database `nativespeaker` | — |
| Python | build/test | ✓ | 3.14.7 in `.venv` (system `python3` is 3.13.5 — always use `.venv/bin/python`) | — |
| `uv` | D-06's lock + sync | ✓ | 0.12.5 | — |
| `firebase-admin` | The adapter | ✓ | 7.3.0 installed | — |
| `tenacity` | D-04, D-05 | ✓ | 9.1.4 installed (transitive today) | — |
| `httpx` | test fixtures | ✓ | dev group | — |
| **Firebase service-account JSON** | **The completion path — every completion, no branch skips it** | **✗** | — | **None.** |
| Firebase test project + API key | e2e fixtures | ✓ | `JWT_PROJECT_ID`, `JWT_API_KEY` present in `.env` | — |

**Missing dependencies with no fallback:**

- **The Firebase service-account credential.** Verified absent: no `service_account` or
  `private_key_id` string exists under `config/` or in `.env`, and `app/lifespan.py:66-69` records
  that Phase 35 removed the last Firebase client at boot. **This is a human action and it blocks
  every completion-mode test, including the real-anonymous e2e D-09 requires.** The planner must add
  an explicit `checkpoint:human-verify` task: *"Download a service-account JSON from the Firebase
  console for the test project and set `FIREBASE_SERVICE_ACCOUNT_JSON` in the gitignored `.env`."*
  Everything else in the phase — prepare mode, the mode-signal partition, the classifier, the
  transaction, and every substituted-adapter rejection test — can proceed without it.

**Missing dependencies with fallback:** none.

## Validation Architecture

`workflow.nyquist_validation` is `true` [VERIFIED: `.planning/config.json`].

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest -q` (addopts already exclude `e2e` and `schema`) |
| Full suite command | `.venv/bin/pytest -q -m ""` |
| Marked suites | `.venv/bin/pytest -q -m e2e` · `.venv/bin/pytest -q -m schema` |

Markers are registered and `addopts = "-v --tb=short -m 'not e2e and not schema'"` [VERIFIED:
`pyproject.toml` `[tool.pytest.ini_options]`], so every e2e/schema command must pass `-m` explicitly —
a rule Phase 34 recorded and that still holds.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CREATE-01 | The route declares `preauth_callable=True`; it is the only one that may | unit | `pytest tests/unit/test_route_registry.py -q` | ✅ extend |
| CREATE-01 | An unlinked caller is admitted here and `preauth_identity_not_allowed` elsewhere | e2e | `pytest -m e2e tests/e2e/test_create_user.py -q` | ❌ Wave 0 |
| CREATE-02 | Mode-signal partition, incl. duplicate/wrong-valued `challenge` and bad `challenge_id` types → 400, no audit row | unit | `pytest tests/unit/test_create_user_modes.py -q` | ❌ Wave 0 |
| CREATE-02 | Prepare returns exactly `{challenge_id, expires_at}` with `Cache-Control: no-store` and mutates no business state | e2e | `pytest -m e2e tests/e2e/test_create_user.py -q` | ❌ Wave 0 |
| CREATE-02 | Completion rejection precedence follows §02's numbering (steps 3→4→5→6→8→9) | unit | `pytest tests/unit/test_create_user_precedence.py -q` | ❌ Wave 0 |
| CREATE-03 | Closed classifier: 7 shapes (empty, 1×google, 1×apple, both, 2×google, unrecognized, empty-uid) | unit | `pytest tests/unit/test_provider_classifier.py -q` | ❌ Wave 0 |
| CREATE-03 | One transaction produces user + 1 ACTIVE identity + 2 attribution tokens | e2e | `pytest -m e2e tests/e2e/test_create_user.py -q` | ❌ Wave 0 |
| CREATE-03 | Forced mid-transaction failure leaves **no** partial account | unit + schema | `pytest tests/unit/test_create_user_rollback.py -q` and `pytest -m schema tests/schema/test_create_atomicity.py -q` | ❌ Wave 0 |
| CREATE-04 | Two concurrent completions for one `(issuer, subject)` → one account; loser gets `identity_already_linked` | schema (real commits, two connections) | `pytest -m schema tests/schema/test_create_race.py -q` | ❌ Wave 0 |
| CREATE-04 | Conflict classification by `constraint_name` maps the three names to the two internal results | unit | `pytest tests/unit/test_conflict_classification.py -q` | ❌ Wave 0 |
| D-04 | tenacity policy: exactly 3 attempts on retryable; 1 on `user_not_found`; exhaustion returns the last result, never `RetryError` | unit | `pytest tests/unit/test_firebase_retry.py -q` | ❌ Wave 0 |
| D-05 | `on_admitted` fires at most once across retries; `record_failure` not called on the `_AdmissionRejected` path; transient/permanent classification preserved | unit | `pytest tests/unit/test_services.py -q` (existing) | ✅ **must stay green unchanged** |
| D-06 | `tenacity` is a direct dependency and `uv.lock` is consistent | manual | `uv lock --check` | n/a |

### Sampling Rate

- **Per task commit:** `.venv/bin/pytest -q` (unit only; sub-30s)
- **Per wave merge:** `.venv/bin/pytest -q -m ""` (unit + e2e + schema)
- **Phase gate:** full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/test_create_user_modes.py` — covers CREATE-02
- [ ] `tests/unit/test_create_user_precedence.py` — covers CREATE-02
- [ ] `tests/unit/test_provider_classifier.py` — covers CREATE-03
- [ ] `tests/unit/test_create_user_rollback.py` — covers CREATE-03
- [ ] `tests/unit/test_conflict_classification.py` — covers CREATE-04
- [ ] `tests/unit/test_firebase_retry.py` — covers D-04
- [ ] `tests/e2e/test_create_user.py` — covers CREATE-01/02/03 over the real transport
- [ ] `tests/schema/test_create_race.py` — covers CREATE-04 (needs two real connections)
- [ ] `tests/schema/test_create_atomicity.py` — covers CREATE-03 criterion 3
- [ ] **Fake `FirebaseAdminAdapter` fixture** (D-09) — shared by every substituted test; put it in
      `tests/unit/conftest.py` so `tests/e2e` can import it the way `stub_verifier` already imports
      `make_test_verifier` from `unit.conftest` (`pythonpath = ["."]` makes both packages importable)
- [ ] **Anonymous Firebase token fixture** in `tests/e2e/conftest.py` (Code Example 6)
- [ ] **Delete** `tests/unit/test_budgets.py` (313 lines) with `auth/budgets.py` (D-04)
- [ ] Framework install: none needed

## Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json`, so it is enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | **yes** | Firebase ID token, RS256 over cached JWKS, verified in the barrier only. Already built; this phase adds no verification code. §02's DELETIONS forbid device check, CAPTCHA, proof-of-work, and attestation on this route in either phase or form. |
| V3 Session Management | **yes — as a prohibition** | **No backend token, session, cookie, or generation counter is minted.** §02 step 14 and SHARED-INVARIANTS § Tokens are explicit. A successful completion issues nothing; the same Firebase ID token simply resolves as linked next request. |
| V4 Access Control | **yes** | The route is the *single* exception to the pre-auth ban, enforced structurally by `_PREAUTH_CALLABLE_ROUTE` in `registry.py` and condition 6 of the startup assertion. |
| V5 Input Validation | **yes** | `classify_mode_signal` (syntactic), the closed providerData classifier (semantic, fail-closed), byte-for-byte `challenge_id` comparison. Provider normalization is exact case-sensitive enum match — no trimming, no case-folding, no defaulting at completion. |
| V6 Cryptography | **yes** | `secrets.token_bytes(16)` for the challenge handle; HMAC-SHA-256 via `HmacKeyring`; `uuid4` for the attribution tokens (opaque, non-secret, not derivable from identity). **Nothing hand-rolled** — no `compare_digest` outside the keyring. |
| V7 Error Handling & Logging | **yes** | Exactly one audit row per on-path attempt; anti-oracle within class; `challenge_id` never logged or audited; provider text never leaked to clients. |
| V8 Data Protection | **yes** | Raw subject never stored outside `core.external_identities` (the documented uniqueness-reservation exception); `email` copied only when `emailVerified = true`; `display_name` **never** populated. |
| V13 API & Web Service | partial | `Cache-Control: no-store` on the prepare response. Rate limiting is Envoy's (D-01). |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Duplicate-account creation via concurrent completions | Tampering | `UNIQUE (issuer, subject)` as the sole arbiter + savepoint-scoped loser handling (Pattern 3) |
| Challenge theft / replay | Spoofing, Elevation | 128-bit CSPRNG handle, 300s TTL, one-way lifecycle, HMAC identity binding, single claim, no stored-outcome replay |
| Burning another user's in-flight challenge | Denial of Service | Identity/operation mismatches are rejected **before** the claim and consume nothing (`challenges.py:33-37`) |
| Provider-account hijack (linking someone else's Google/Apple uid) | Spoofing | `provider_uid` comes solely from the Admin `getUser` response, never from client input; `ix_external_identities_provider_account` spans historical rows so retirement never frees an account |
| Flow confusion (anonymous challenge completing a registered create) | Tampering | `operation_variant` is immutable on the challenge row; the completion variant check is byte-for-byte and runs before the Admin lookup |
| Issuer oracle / integration enumeration | Information Disclosure | Identical body/status per class; issuer mismatch rejects at the barrier before any client selection |
| Unbounded account creation | Denial of Service | **Accepted risk under D-01.** No backend limiter. Mitigants on record: a valid Firebase token is required, accounts carry zero entitlement, and the v1.6 Envoy chart's existing limits are untouched. Closes when FOUND-09 lands in v2.1. |
| Ambient-credential privilege escalation in dev | Elevation | No `[DEFAULT]` Firebase app is created; every call passes `app=`; ADC is never reachable |
| Service-account key in git | Information Disclosure | D-08 puts it in the gitignored `.env`; Pitfall 7 explains why it must not go in `config/config.yaml` |
| Audit log becoming a tracking archive | Information Disclosure | `redact()` drops the full forbidden list at any nesting depth; only the client-IP *bucket kind* is stored, never the address |

## Sources

### Primary (HIGH confidence)

- **The running PostgreSQL 17.11 database** — `pg_constraint` / `pg_indexes` for
  `core.external_identities` and `core.store_purchase_tokens`; empirical probes for asyncpg
  `constraint_name` population and SQLAlchemy savepoint recovery under
  `join_transaction_mode="create_savepoint"`. Queried 2026-08-22.
- **The installed `firebase_admin` 7.3.0 package source** —
  `_user_mgt.py:88-130, :246-256, :455-490`, `credentials.py` `Certificate.__init__`,
  `__init__.py:33` (`_CONFIG_VALID_KEYS`), `auth.py:73,150`, `_auth_utils.py:363`.
- **Context7 `/firebase/firebase-admin-python`** (High reputation) — `initialize_app` signature and
  options, `get_user(uid, app=)`, `httpTimeout`, error taxonomy.
- **Context7 `/jd/tenacity`** (High reputation) — `AsyncRetrying`, `retry_if_result`,
  `retry_error_callback`, `reraise` semantics.
- **`/home/init/native-speaker/specs/auth-refactor-phases/02-create-user.md`** — the full 88 lines.
- **`/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md`** — the full file.
- **Repository source, read in full this session:** `auth/adapters.py`, `auth/challenges.py`,
  `auth/registry.py`, `auth/budgets.py`, `auth/context.py`, `auth/modesignal.py`, `auth/audit.py`,
  `auth/barrier.py` (lines 60-190), `auth/identity.py` (excerpt), `errors.py`, `config.py`,
  `resilience.py`, `app/dependencies.py`, `app/lifespan.py`, `models/auth.py`, `models/identities.py`,
  `models/users.py`, `models/__init__.py`, `tests/e2e/conftest.py`, `pyproject.toml`,
  `config/config.yaml`, `migrations/20260818_01_initial-release.sql` (excerpts).
- **Planning artifacts:** `37-CONTEXT.md`, `35-CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md`,
  `ROADMAP.md:247-258`, `35-foundation/deferred-items.md`, `.planning/config.json`.
- **PyPI JSON API** — `tenacity` 9.1.4 (2026-02-07), `firebase-admin` 7.5.0 (2026-07-02).

### Secondary (MEDIUM confidence)

- **docs.cloud.google.com Identity Platform `accounts.signUp` reference** — confirms an anonymous
  user is created when `email` is omitted; does **not** document `returnSecureToken` (see A1).

### Tertiary (LOW confidence)

- WebSearch on the Firebase Auth REST anonymous sign-up endpoint — corroborated the v3→v1 endpoint
  migration but produced no primary source. Superseded by the Identity Platform reference above.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — no new package is introduced; both libraries are already resolved,
  installed, and version-verified against PyPI.
- Architecture / race arbitration: **HIGH** — the savepoint pattern, the transaction-poisoning
  failure mode, and the constraint-name discriminator were each executed against the real database
  under the real harness configuration, not reasoned about.
- Firebase SDK shapes: **HIGH** — quoted from the installed package source, cross-checked against
  Context7's official docs.
- Pitfalls: **HIGH** for 1–5 and 7–9 (each traced to a verbatim source quote or an executed probe);
  **MEDIUM** for 6 and 10 (derived from spec reading and existing docstrings).
- Test-harness strategy for criteria 3–4: **MEDIUM** — the `tests/schema/` scratch-database mechanism
  was read but a two-connection concurrency test was not prototyped.
- Error-class statuses and the `required_flow` body mechanism: **MEDIUM** — see A3, A4.

**Research date:** 2026-08-22
**Valid until:** 2026-09-21 (30 days — the stack is stable; the only fast-moving input is the
`firebase-admin` release line, and this phase pins the installed 7.3.0)
