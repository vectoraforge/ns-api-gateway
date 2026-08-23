---
phase: 37-post-auth-create-user
plan: 07
subsystem: auth
tags: [tracer, fastapi-router, challenge-protocol, savepoint, audit, firebase-adapter, mode-signal]
status: complete

# Dependency graph
requires:
  - plan: "37-01"
    provides: "the operation_variant removal — ChallengeStore.issue is (session, *, operation, identity, now)"
  - plan: "37-03"
    provides: "IDENTITY_ALREADY_LINKED and OPERATION_NOT_ALLOWED; FirebaseConfig.credential_dict() -> dict | None"
  - plan: "37-04"
    provides: "PurchaseProvider / StorePurchaseToken, and A2 CONFIRMED so the create transaction writes through the mapped class"
  - plan: "37-05"
    provides: "FirebaseAdminLookup, build_admin_apps, classify_provider_data, email_to_persist, and ProviderDataResult.email/.email_verified"
  - plan: "37-02"
    provides: "auth/retry.py's lookup_with_retry — result-based policy that never raises"
provides:
  - "POST /auth/create-user registered, declared, and serving both modes end to end"
  - "src/nativespeaker/api/routers/auth.py — the router, the permissive body model, both mode bodies"
  - "src/nativespeaker/api/auth/creation.py — create_account and resolve_existing_identity, drivable without FastAPI"
  - "app.state.firebase_adapter, plus five Depends() accessors phases 40/41/42 reuse"
  - "tests/unit/conftest.py::FakeFirebaseAdapter — the one shared provider fake"
affects: [37-08, 37-09, 37-10, 38, 39, 40, 41, 42]

actuals:
  tokens: 36386
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "One registered path function dispatching to two mode bodies behind a single registry entry"
    - "A mid-handler commit as an architectural boundary: the claim is durable before the provider call"
    - "The consuming transaction as a plain function over (session + resolved facts), reachable without the framework"
    - "begin_nested() around business inserts so consumption and the audit row survive a rollback"
    - "Permissive Any-typed body field so a wrong-typed value earns 400 invalid_request, never 422"

key-files:
  created:
    - src/nativespeaker/api/routers/auth.py
    - src/nativespeaker/api/auth/creation.py
    - tests/e2e/test_create_user.py
    - tests/unit/test_create_user_modes.py
  modified:
    - src/nativespeaker/api/auth/registry.py
    - src/nativespeaker/api/routers/__init__.py
    - src/nativespeaker/api/app/main.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/app/lifespan.py
    - tests/e2e/conftest.py
    - tests/unit/conftest.py
    - tests/unit/test_route_registry.py

key-decisions:
  - "Symbol names (Claude's discretion per 37-CONTEXT.md): create_account, resolve_existing_identity, CreateUserRequest, PrepareResponse, CompletionResponse, _prepare, _complete, _already_linked, get_raw_query_string, get_challenge_store, get_audit_writer, get_session_factory, get_firebase_adapter, FakeFirebaseAdapter."
  - "One registered path function dispatching to two module-level mode bodies — the registry can express only one (method, path) per operation, and two bodies keep each mode readable alone."
  - "The claim commits in its own transaction before the provider read. A crash mid-lookup leaves a permanently-claimed dead row, which is §6.2's design; the alternative lets a second attempt win the challenge."
  - "A-37-07-1: the route reads the identity variant off RequestContext instead of Depends(get_preauth_identity). §02 prepare step 1's already-linked rejection is unreachable otherwise — the barrier resolves such a caller as LINKED and the accessor raises 401."
  - "The prepare pre-check has two arms: a linked context needs no query (the barrier just resolved it), a pre-auth context gets one direct read through the same query the consuming transaction uses."
  - "Five Depends() accessors rather than the plan's three — approved deviation, see Deviations 1."
  - "The shared provider fake lives once in tests/unit/conftest.py; tests/e2e/conftest.py imports it, following the make_test_verifier precedent."

patterns-established:
  - "A mid-handler `await session.commit()` documented at the call site as a transaction boundary, not a stray commit"
  - "Rejection branches owned by a later plan return the correct client class today and name their owning plan in a docstring"
  - "A stub session in unit tests that records statements, so 'exactly one read' is asserted rather than assumed"

requirements-completed: [CREATE-01, CREATE-02, CREATE-03]

coverage:
  - id: D1
    description: "POST /auth/create-user is the only REGISTRY entry declaring preauth_callable=True, and the startup enumeration assertion passes in both directions"
    requirement: CREATE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_route_registry.py#TestCreate01TheProductionPreAuthDeclaration::test_exactly_one_production_route_is_preauth_callable"
        status: pass
      - kind: unit
        ref: "tests/unit/test_route_registry.py#TestCreate01TheProductionPreAuthDeclaration::test_that_route_carries_the_create_user_operation_and_is_challenge_bearing"
        status: pass
      - kind: integration
        ref: "the e2e module-scoped lifespan boots the real app, so assert_route_enumeration passes for all 220 e2e tests"
        status: pass
    human_judgment: false
  - id: D2
    description: "Prepare returns exactly {challenge_id, expires_at} with Cache-Control: no-store and creates no core.users row"
    requirement: CREATE-02
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheAnonymousHappyPath::test_an_unlinked_caller_creates_an_anonymous_account"
        status: pass
    human_judgment: false
  - id: D3
    description: "A completion for an unlinked subject with empty providerData returns 200 anonymous and creates exactly one users row, one ACTIVE anonymous identity with NULL provider_uid, and two store_purchase_tokens rows with distinct identity_values"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheAnonymousHappyPath::test_an_unlinked_caller_creates_an_anonymous_account"
        status: pass
    human_judgment: false
  - id: D4
    description: "The successful completion writes exactly one audit row with operation=create_user / result=succeeded, and the challenge is consumed with preauth_subject_hash cleared"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheAnonymousHappyPath (audit + challenge assertions)"
        status: pass
    human_judgment: false
  - id: D5
    description: "No access grant, no free credits, no user_monthly_usage row, and display_name / registered_at both NULL for an anonymous creation"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheAnonymousHappyPath (entitlement + field assertions)"
        status: pass
    human_judgment: false
  - id: D6
    description: "The mode signal partitions exhaustively; every invalid_request is 400 with body code invalid_request, never 422, and writes no audit row and has no side effect"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_modes.py (29 cases: TestTheTwoModesDispatch, TestTheInvalidRequestPartition, TestTheWhitespaceAsymmetry, TestTheRejectionHasNoSideEffects)"
        status: pass
    human_judgment: false
  - id: D7
    description: "A prepare request from an already-linked caller returns 409 identity_already_linked, issues no challenge, and writes exactly one standalone-durable audit row"
    requirement: CREATE-01
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestPrepareRejectsAnAlreadyLinkedCaller (3 cases)"
        status: pass
    human_judgment: false
  - id: D8
    description: "Prepare is not idempotent — two prepares from one unlinked caller issue two distinct challenge_ids"
    requirement: CREATE-02
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestPrepareStillIssuesForAnUnlinkedCaller::test_two_prepares_issue_two_distinct_challenges"
        status: pass
    human_judgment: false
  - id: D9
    description: "No database transaction is open across the Firebase call — the claim commits before the lookup and the consuming transaction opens after it"
    verification:
      - kind: other
        ref: "routers/auth.py::_complete — an explicit `await session.commit()` sits between the claim and lookup_with_retry, with the rationale at the call site"
        status: pass
      - kind: integration
        ref: "the e2e completion exercises the full ordering against real PostgreSQL"
        status: pass
    human_judgment: true

# Metrics
duration: ~35 min active (wall clock spans a checkpoint pause)
completed: 2026-08-23
---

# Phase 37 Plan 07: The Phase Tracer — POST /auth/create-user End to End Summary

**One unlinked caller goes from no account to an account over real HTTP, through the real barrier, the real challenge store, a real transaction and a real database — with the claim committed before the provider read, the provider read outside any transaction, and the consuming transaction reachable as a plain function.**

## Performance

- **Started:** 2026-08-22T23:55Z
- **Completed:** 2026-08-23T23:10Z
- **Duration:** ~35 min of active execution, split across the tracer feedback gate (the wall-clock span includes the checkpoint pause)
- **Tasks:** 3
- **Files:** 12 (4 created, 8 modified, 0 deleted)
- **Tests:** unit 1065 → 1097, e2e 214 → 220. Zero failures throughout.

## Task Commits

1. **Task 1 (tracer): the end-to-end anonymous slice** — `7cb49e2`
2. **Task 2: prepare mode's already-linked fail-fast** (TDD) — `3898fdb` (test, RED) → `29a4370` (feat, GREEN)
3. **Task 3: the exhaustive mode-signal partition at unit level** — `dc81378` (test)

No REFACTOR commit: the GREEN implementation needed no cleanup.

## The Names Chosen

37-CONTEXT.md left these to implementation. 37-08, 37-09 and 37-10 import them.

| Symbol | Module | What it is |
|---|---|---|
| `create_account(session, *, context, identity, challenge, provider, provider_uid, email, challenge_store, audit_writer) -> AuthEventResult` | `auth/creation.py` | §02 step 10's consuming transaction |
| `resolve_existing_identity(session, *, issuer, subject) -> ExternalIdentity \| None` | `auth/creation.py` | The one `(issuer, subject)` read, used by both the racy pre-check and the authoritative in-transaction resolution |
| `create_user` | `routers/auth.py` | The registered path function |
| `_prepare` / `_complete` | `routers/auth.py` | The two mode bodies |
| `_already_linked` | `routers/auth.py` | §02 prepare step 1's fail-fast |
| `CreateUserRequest` / `PrepareResponse` / `CompletionResponse` | `routers/auth.py` | The body models |
| `get_raw_query_string`, `get_challenge_store`, `get_audit_writer`, `get_session_factory`, `get_firebase_adapter` | `app/dependencies.py` | The five accessors |
| `FakeFirebaseAdapter` / `fake_firebase_adapter` | `tests/unit/conftest.py` | The one shared provider fake |

## Prepare and Completion Are Two Functions Behind One Registered Path Function

The registry can express only one `(method, path)` per operation — condition 8 fails boot on a second — so one route is not a choice. What was a choice is what sits behind it, and it is two module-level functions rather than one branching body: prepare mutates **no** business state and completion mutates all of it, so a single body would be an `if` around two procedures that share nothing but their entry point. The dispatcher's own job is exactly one thing — classify the mode signal, reject `None`, and hand off.

## Why the Claim Commits in Its Own Transaction

`_complete` carries an explicit `await session.commit()` between the claim and `lookup_with_retry`. It looks like a stray commit; it is the plan's most load-bearing line, and the reason is written beside it.

- **If the claim were held uncommitted across the provider call**, a second attempt could still win the same challenge — destroying the single-serialization-point property the claim exists to provide.
- **Committing it means a crash mid-lookup leaves a permanently-claimed dead row.** That is §6.2's stated design ("a claimed challenge is dead"): there is no reclaim, no cleanup job, no recovery scan. The client's remedy is one fresh prepare inside the 300-second TTL.

The consequence is that the claim (step 5) and the consume (step 13) live in **different transactions** with the provider call between them, and that between them **no transaction is open at all** — which is what SHARED-INVARIANTS § Locks requires, and what keeps provider latency from becoming a database-wide stall.

## The Structured Security Log on Each Fail-Closed Branch

Nothing below ever carries the raw subject, the client address, or the public `challenge_id`.

| Branch | Log event | Fields |
|---|---|---|
| Mode-signal rejection (`invalid_request`) | `auth_mode_signal_invalid` | `route`, `operation`, `body_present` — the *shape*, never the offending value: an unusable handle is still a handle somebody typed |
| Challenge rejection (`challenge_required`) | `create_user_challenge_rejected` | `stage` only (`challenge_not_found`, `challenge_binding_rejected`, `challenge_operation_mismatch`, `challenge_claim_lost`) — the client sees one collapsed class, so completion is not an enumeration oracle |
| Provider read produced no classifiable account | `create_user_lookup_rejected` | `outcome` — the closed `ProviderDataOutcome` member, never provider text |
| Consuming transaction rejected | `create_user_transaction_rejected` | `result` — the internal `AuthEventResult` |
| Consume matched no row while this attempt held the claim | `challenge_consume_did_not_match` (ERROR) | `challenge_row_id` — the **non-secret** row id |

The `invalid_request` branch is the one that writes **no** `audit.auth_events` row at all: it belongs to the admission phase, has no internal `core.auth_event_result`, and the structured log plus the counter metric are its entire record. A unit case asserts that against a recording writer.

## A-37-07-1 — The Route Reads the Identity Variant Off the Context

**The plan's Task 2 premise was factually wrong, and following it literally would have made the required behaviour unreachable.** The plan states "the barrier hands a `PreAuthIdentity` here, so the pre-check is a direct query, not a read of the context" — while simultaneously requiring that a caller whose `(issuer, subject)` already resolves to an ACTIVE identity gets 409 `identity_already_linked`. Those cannot both hold: such a caller is resolved by the barrier as **linked**, so `Depends(get_preauth_identity)` raises and the client receives 401 `auth_required`. The RED test proved exactly this, with the observed log line `Identity context is linked on a route expecting a pre-auth identity` and a 401.

**Resolution — both halves implemented, neither dropped:**

- The handler takes `Depends(get_request_context)` and reads `context.identity`. This is the **only** route in the system that admits both variants, and that is precisely §02's design: `preauth_callable` says the barrier *may* admit an unlinked caller here, not that a linked one is a wiring bug. 409 and 401 tell a client incompatible things.
- **The direct query survives, for the race.** A pre-auth context still gets one read through `resolve_existing_identity` — the row may have appeared between the barrier's resolution and now. A linked context gets **no** query, because the barrier resolved that exact pair one layer ago through `auth/identity.py`'s single statement; asking again would be a second identity resolution (which §1.4 forbids a handler) and would be *later*, hence racier, not less.

`get_preauth_identity` is untouched and still raises for every other route. The docstring records why this route is the exception.

## Deviations from Plan

### 1. [Rule 3 — Blocking] Five `Depends()` accessors, not three — **approved by the coordinator at the tracer gate**

- **Found during:** Task 1
- **Issue:** The plan specifies three accessors (raw query string, challenge store, Firebase adapter). But `AuditWriter.write_in_transaction` needs the writer and Task 2's `write_standalone` needs the raw session factory, and neither is reachable without a `Request` parameter — which the v1.3 `Depends()`-only convention forbids on handlers.
- **Fix:** Added `get_audit_writer` and `get_session_factory`. Both landed in Task 1 because Task 2's declared file list does not include `app/dependencies.py`.
- **Committed in:** `7cb49e2`

### 2. [Rule 1 — Bug] The plan's Task 2 premise contradicted its own behaviour spec

- **Found during:** Task 2 (caught by the RED test, which failed with 401 instead of 409)
- **Fix:** See A-37-07-1 above. Both the context read and the racy direct query are implemented.
- **Committed in:** `29a4370`

### 3. [Rule 3 — Blocking] Task 2 touched `auth/creation.py`, outside its declared file list

- **Found during:** Task 2
- **Issue:** Once a linked caller can reach the handler, `LinkedIdentity` can reach `_complete` and `create_account`, whose annotations said `PreAuthIdentity`. Separately, the racy pre-check needed the same `(issuer, subject)` query the consuming transaction uses — and the plan's own `read_first` asks for "the same query the barrier uses, not a second one".
- **Fix:** Widened the `identity` annotations to `LinkedIdentity | PreAuthIdentity` (both functions read `.issuer`/`.subject` only, so the wider type is the honest one), and published `_resolve_existing` as `resolve_existing_identity` so there is **one** query definition with two call sites rather than a third query shape in the router.
- **Committed in:** `29a4370`

### 4. Task 3's TDD gate could not be honoured as RED→GREEN

- **Issue:** Task 3 is marked `tdd="true"` but is **test-only** — its subject was implemented by Tasks 1 and 2, so a genuinely failing-first test was not available. Writing production code solely to make it fail would have been theatre.
- **What happened instead:** 2 of the 29 cases *did* fail on first run, but for a harness reason rather than a production defect — the stub session had no `exec`, because I had assumed prepare touched no database. It does: §02 prepare step 1's racy pre-check is one read. The test was corrected, not the code, and the finding was turned into a permanent assertion (`len(session.statements) == 1`) that would catch a future second identity resolution in the handler.
- **Committed in:** `dc81378`, as a single `test(...)` commit. No `feat(...)` pair exists for Task 3 and none should.

### 5. Scope addition — the shared provider fake was de-duplicated

- Task 1 put a scripted adapter in `tests/e2e/conftest.py`; Task 3's plan requires the shared fake in `tests/unit/conftest.py`. Rather than ship two fakes that can drift, the class lives once in `tests/unit/conftest.py` and `tests/e2e/conftest.py` imports it — exactly the rule `stub_verifier` already follows for `make_test_verifier`, and for the reason its docstring states. Only the app-state swap remains in the e2e package.

### Not encountered

- **No self-invalidating acceptance criterion.** Every grep criterion in this plan (`compare_digest` 0, `rowcount` 0, `begin_nested` present, `email_to_persist` once) held literally, with the call-count one verified by AST rather than grep since the import line is also a textual match.
- **The src-wide adapter-method scan never fired.** No new `src/` file names an adapter method in code or prose; `ADAPTER_IMPLEMENTORS` is byte-identical (`git diff --stat` empty) and `test_adapter_interfaces.py` passes at 56.

## Known Stubs

Four rejection branches are deliberately incomplete, each assigned by the phase plan and each marked in a docstring naming its owner. **None of them is silent**: every one returns a correct fail-closed client class today, and no path returns a 200 it did not earn.

| # | Gap | Owner | Site | Behaviour today |
|---|---|---|---|---|
| 1 | Per-rejection internal results, audit rows and consumption dispositions for the five challenge rejections | 37-08 Task 1 | `routers/auth.py::_challenge_rejected` | Correct `challenge_required` (409); no audit row; a claimed challenge is left claimed rather than consumed |
| 2 | The `user_not_found` arm (`auth_required`, not either class currently returned), plus internal results and audit rows for the lookup/classifier rejections | 37-08 Task 2 | `routers/auth.py::_lookup_rejected` | `verification_temporarily_unavailable` for a non-`ok` outcome, `operation_not_allowed` for a rejected classification. **`user_not_found` currently earns 503 where §02 earns 401** |
| 3 | `except IntegrityError` → rollback-to-savepoint + constraint-name discrimination | 37-09 Task 1 | `auth/creation.py::_insert_account` | The savepoint is built but has no rollback arm: a genuine race would surface as a 500 |
| 4 | Blocked-user discrimination in the in-transaction re-resolution | 37-09 | `auth/creation.py::_result_for_existing` | A non-active row audits as `historical_identity`; both arms surface identically to the client as `account_unavailable`, so only the internal result differs |

Gaps 2 and 3 are the two with client-visible consequences and should be treated as 37-08/37-09's first work.

## Threat Flags

None. No security-relevant surface appeared beyond what the plan's `<threat_model>` registered. Every `mitigate` disposition has a passing assertion:

| Threat | Status |
|---|---|
| T-37-24 (`preauth_callable` spreading) | Pinned by `_PREAUTH_CALLABLE_ROUTE` + condition 6, and asserted against the **production** table |
| T-37-25 (burning another user's challenge) | `verify_binding` and the operation check run before the claim; the handler adds no comparison of its own |
| T-37-26 (`challenge_id` disclosure) | Body-only transport; audit correlates on `challenge_row_id`; the e2e case asserts no `challenge_id` key at any depth **and** that the literal handle does not appear in `details` |
| T-37-28 (transaction across the Firebase call) | The claim commits first; the lookup runs with nothing open |
| T-37-29 (partial account) | All three inserts inside one `begin_nested()` (rollback arm is 37-09's) |
| T-37-30 (silent entitlement) | Zero grants and zero usage rows asserted after a successful completion |
| T-37-31 (prepare over-disclosure) | `PrepareResponse` declares two fields; the key set is asserted exactly |
| T-37-32 (minting a token) | Nothing is minted; the response carries one field |
| T-37-33 (`display_name` / unverified email) | `display_name` never constructed; `email` written straight through from `email_to_persist`'s single evaluation |
| T-37-27 (unmetered creation) | **Accepted**, unchanged — D-01, gateway limits, closes with FOUND-09 in v2.1 |

## Verification Commands Run

| Command | Result |
|---|---|
| `.venv/bin/pytest -q` | **1097 passed**, 316 deselected, 0 failed (baseline 1065) |
| `.venv/bin/pytest -q -m e2e` | **220 passed**, 1193 deselected, 0 failed (baseline 214) |
| `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py` | 6 passed |
| `.venv/bin/pytest -q tests/unit/test_create_user_modes.py tests/unit/test_route_registry.py tests/unit/test_mode_signal.py` | 120 passed |
| `.venv/bin/pytest -q tests/unit/test_adapter_interfaces.py` | 56 passed |
| `.venv/bin/python -c "import nativespeaker.api.app.main"` | exit 0 |
| `.venv/bin/ruff check src/ tests/` | All checks passed |
| `grep -c "compare_digest" routers/auth.py auth/creation.py` | 0 and 0 |
| `grep -c "rowcount" routers/auth.py auth/creation.py` | 0 and 0 |
| AST: `email_to_persist` call sites in `routers/auth.py` | 1 |
| `inspect.signature(create_account)` email-related parameters | `['email']`, annotated `str \| None` |
| `git diff --diff-filter=D --name-only 7c4e57e..HEAD` | empty — no file deleted |

## Next Phase Readiness

- **37-08** extends `routers/auth.py`'s `_challenge_rejected` and `_lookup_rejected`. Both are single functions with the full branch context available; the `stage` / `outcome` arguments already discriminate the cases they need to map. Known Stubs 1 and 2 are its exact scope.
- **37-09** drives `auth/creation.py::create_account` directly — it takes a session plus resolved facts, imports nothing from FastAPI, and needs no request. The savepoint is already in place; Known Stubs 3 and 4 are its exact scope.
- **37-10** scripts `tests/unit/conftest.py::FakeFirebaseAdapter` on all four `ProviderDataResult` fields, and swaps it into the app through `tests/e2e/conftest.py::scripted_firebase_adapter`.
- **Phases 40/41/42** reuse all five `Depends()` accessors and the one-route/two-bodies shape unchanged.
- **Still unmeasured, carried from 37-05:** RESEARCH A5 — whether `httpTimeout` bounds a genuinely slow `getUser`. Nothing in this plan touched real Firebase; 37-10's real-anonymous fixture is the earliest detector.

## Self-Check: PASSED

- Created files exist: `src/nativespeaker/api/routers/auth.py`, `src/nativespeaker/api/auth/creation.py`, `tests/e2e/test_create_user.py`, `tests/unit/test_create_user_modes.py`.
- All four task commits present in `git log 7c4e57e..HEAD`: `7cb49e2`, `3898fdb`, `29a4370`, `dc81378`.
- TDD gate sequence intact for Task 2: `test(37-07)` (`3898fdb`) precedes `feat(37-07)` (`29a4370`).
- `git diff --diff-filter=D --name-only 7c4e57e..HEAD` → empty. No file deleted by this plan.
- Branch verified `gsd/phase-37-post-auth-create-user` before every commit.

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-23*
