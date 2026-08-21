---
phase: 35-foundation
plan: 06
subsystem: auth-barrier
tags: [starlette, asgi-middleware, sqlmodel, postgresql, httpx, structlog, anti-oracle]

requires:
  - phase: 35-foundation
    plan: 01
    provides: "the pure-ASGI barrier seam, the route registry, and the §1.1 wire contract"
  - phase: 35-foundation
    plan: 02
    provides: "errors.py with the seven foundation classes; verification.py returning (claims, reason)"
  - phase: 35-foundation
    plan: 03
    provides: "auth/context.py -- the §1.4 variants and REQUEST_CONTEXT_SCOPE_KEY the barrier writes"
  - phase: 35-foundation
    plan: 05
    provides: "a model layer that queries the applied v2.0 schema, and e2e create_chat"
provides:
  - "auth/identity.py -- the single outer-joined resolution query and the four-outcome admission matrix"
  - "auth/telemetry.py -- RejectionCounter (result x bounded reason x route) and record_rejection"
  - "a barrier running all six §1.5 steps: verify, resolve, admit, attach"
  - "app.state.rejection_counter, constructed in the lifespan"
  - "tests/e2e/conftest.py::seed_identity and ::stub_verifier -- four subjects without four Firebase accounts"
  - "the four-outcome matrix and the six wire cases proven against real rows and a real transport"
affects: [35-08, 35-09, 35-10, 35-11, 36-rebinding, 37-create-user, 39-profile, 43-webhooks]

actuals:
  tokens: 23838
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "A LEFT OUTER JOIN used to keep a defensive branch reachable, with the join *kind* asserted on the compiled statement because no data can exercise it"
    - "Counting real cursor executions per outcome, so 'one query, one code path' is observed at runtime rather than read off the source"
    - "A stub session that keeps the statements it was handed, turning an untestable query-count claim into a direct assertion"
    - "Swapping app.state.jwt_verifier in a fixture rather than mocking the barrier, so the seam under test is the production one"
    - "Retargeting a positive control onto the *class* of its answer, so it still distinguishes 'the wire contract passed' from 'nothing is ever refused'"

key-files:
  created:
    - src/nativespeaker/api/auth/identity.py
    - src/nativespeaker/api/auth/telemetry.py
    - tests/e2e/test_barrier_admission.py
    - tests/e2e/test_barrier_wire_contract.py
    - tests/unit/test_barrier_wire_contract.py
    - tests/unit/test_identity_resolution.py
  modified:
    - src/nativespeaker/api/auth/barrier.py
    - src/nativespeaker/api/auth/__init__.py
    - src/nativespeaker/api/app/lifespan.py
    - tests/e2e/conftest.py
    - tests/unit/test_auth_security.py
    - tests/e2e/test_chats.py
    - tests/e2e/test_chat_queries.py
    - tests/e2e/test_error_cases.py
    - tests/e2e/test_root.py
    - tests/e2e/test_examples.py
  deleted: []

key-decisions:
  - "The join is an OUTER join, not the inner one RESEARCH.md Code Example 2 sketches. An identity row whose user row is missing and no identity row at all are different §1.3 conditions -- internal_error versus outcome 1 -- and an inner join collapses them, reading a broken link as a fresh identity. Verified by mutation: the inner-join form passed the entire suite until the compiled statement itself was asserted."
  - "The wrong-variant choice plan 03 left open was NOT specialised. `get_preauth_identity` still raises AuthenticationError rather than preauth_identity_not_allowed, because `/auth/create-user` still has no caller: no route declares preauth_callable, so the barrier admits no pre-auth principal and no handler can receive the wrong variant. Specialising now would ship an untested branch. Phase 37 owns it."
  - "35-01's `test_invalid_bearer_token_returns_401` needed no retargeting. It sends `Bearer invalid.token.here`, which now reaches step 3 and fails verification, so `auth_required` is still the right answer -- the case got stronger without changing."
  - "Nine existing e2e cases moved from `auth_required` to `preauth_identity_not_allowed`, and three moved back to a served 200 through a seeded identity. The class change is the barrier resolving identity for the first time; the seeding is what an authenticated route now requires."
  - "record_rejection tolerates a missing counter rather than raising. A telemetry gap must never turn a 401 into a 500 -- that would be both an availability regression and an anti-oracle break -- so the absence is logged at ERROR and the client still gets the rejection its request earned."
  - "The route label is `meta.path`, the registry's path template, never `scope['path']`. Verified by mutation: labelling with the request path fails the bounded-cardinality case."

requirements-completed: [FOUND-01, FOUND-02]

coverage:
  - id: A1
    description: "The barrier admits only identity_state = 'active' AND users.active exactly TRUE; historical, blocked, NULL, and unrecognized values all reject and none falls through to pre-auth"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_barrier_admission.py::TestOutcomeFourLinkedAndActive (4 cases) and ::TestOutcomesTwoAndThreeAreIndistinguishable (4 cases)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_resolution.py::TestOutcomeTwoIdentityStateIsNotExactlyActive (9 cases over historical/None/'retired'/'') -- NULL and unrecognized are unreachable through PostgreSQL"
        status: pass
      - kind: unit
        ref: "::TestOutcomeThreeUserIsNotExactlyTrue (5 cases; None/1/'true'/'yes' all reject)"
        status: pass
      - kind: other
        ref: "mutation M2 (`is not True` -> `not user.active`) -> 3 failed; M3 (`!= active` -> `== historical`) -> 6 failed"
        status: pass
    human_judgment: false
  - id: A2
    description: "An unlinked verified subject on a non-preauth route rejects preauth_identity_not_allowed; on a preauth_callable route the barrier admits a pre-auth context carrying only (issuer, subject)"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_barrier_admission.py::TestOutcomeOnePrimeUnlinked (4 cases across /, /examples, /chats)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_resolution.py::TestOutcomeOneNoMatchingRow (4 cases, incl. the variant carrying no user or identity attribute)"
        status: pass
    human_judgment: false
  - id: A3
    description: "A historical identity and a blocked user both reject as account_unavailable with identical status, body, and copy, through the same code path and the same single identity query"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_barrier_admission.py::test_the_two_responses_are_identical_in_status_body_and_headers"
        status: pass
      - kind: unit
        ref: "::TestOneQueryOneCodePath::test_both_account_unavailable_branches_carry_the_same_class_object; ::TestTheResolutionStatement::test_the_state_columns_are_read_in_python_not_filtered_in_sql"
        status: pass
      - kind: other
        ref: "live probe: both 403, both b'{\"code\":\"account_unavailable\"}', headers minus Date identical, both 1 identity statement"
        status: pass
    human_judgment: false
  - id: A4
    description: "Identity resolution issues exactly one database query per request, joining core.external_identities to core.users"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_barrier_admission.py::TestOneQueryPerRequest -- real cursor executions counted across all four outcomes, plus a wire rejection that touches the database not at all"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_resolution.py::test_every_outcome_issues_exactly_one_statement (5 outcomes)"
        status: pass
      - kind: other
        ref: "live probe: identity_queries=1 for linked/historical/blocked/unlinked, 0 for a credential-less request"
        status: pass
    human_judgment: false
  - id: A5
    description: "A core.users row reachable from no core.external_identities row fails closed as an internal error; no path invents, reassigns, merges, or repairs an identity row inline"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_resolution.py::TestUnresolvableUser (3 cases) and ::TestTheResolutionStatement (4 cases pinning the outer join that keeps the branch reachable)"
        status: pass
      - kind: other
        ref: "mutation M1 (isouter=True -> inner join) -> 1 failed. Undetected before the statement-shape assertions were added; see Issues Encountered."
        status: pass
    human_judgment: false
  - id: A6
    description: "Zero, duplicate-instance, differently-cased-duplicate, comma-joined, empty-token, and trailing-content Authorization values each reject over a real ASGI transport with byte-identical response bodies and the same 401 status"
    requirement: FOUND-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_barrier_wire_contract.py::TestTheSixCasesOverTheWire (8 cases, incl. byte-identical bodies and identical statuses)"
        status: pass
      - kind: e2e
        ref: "::TestTheTransportPreservesTheAwkwardShapes (3 cases) -- duplicates arrive as two fields, differently-cased fields fold onto one lowercase key, comma-joined values arrive unsplit"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barrier_wire_contract.py (26 cases), incl. shapes no client can send: line folds and a non-ASCII token byte"
        status: pass
    human_judgment: false
  - id: A7
    description: "A wrong-method request to a registered authenticated path receives the router's 405, not auth_required"
    requirement: FOUND-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_barrier_admission.py::TestAdmissionPhasePrecedesAuth (3 cases: 405 with and without a credential, and 404 for an unknown path)"
        status: pass
    human_judgment: false
  - id: A8
    description: "Every barrier rejection increments a bounded-cardinality counter labeled by result x bounded reason x route and emits one structured security-log event; the bounded reason never appears in the client response"
    requirement: FOUND-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_barrier_admission.py::TestEveryRejectionIsCounted (3 cases: all four internal results counted, the route label is the template, no label carries a subject)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_resolution.py::TestRejectionCounter (5 cases) and ::TestRecordRejection (5 cases, incl. a monkeypatched log spy)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_auth_security.py::test_every_barrier_rejection_is_counted; ::test_the_counter_labels_the_route_template_and_never_the_token"
        status: pass
      - kind: other
        ref: "mutation M4 (label with scope['path']) -> 1 failed; M5 (counter never increments) -> 6 failed"
        status: pass
    human_judgment: false
  - id: A9
    description: "The barrier reads app.state.session_factory per request rather than caching it, so the e2e rollback fixture's factory swap takes effect"
    requirement: FOUND-01
    verification:
      - kind: other
        ref: "`'state' not in inspect.getsource(AuthBarrierMiddleware.__init__)` -> True; `getsource(cls).count('scope[\"app\"].state')` -> 3"
        status: pass
      - kind: other
        ref: "post-run live count: core.users 0 rows, core.external_identities 0 rows -- 41 new e2e cases seeded and every row rolled back"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-08-20
status: complete
---

# Phase 35 Plan 06: The Admitting Barrier Summary

**The barrier resolves identity for the first time: one outer-joined query per request, the four
§1.3 outcomes enforced on two columns tested positively, both `account_unavailable` branches
leaving the same statement through the same path, and a bounded counter recording every rejection
— proven against real rows over a real transport by 41 new e2e cases and 74 new unit cases.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-08-21 06:36Z
- **Completed:** 2026-08-21 06:50Z
- **Tasks:** 3 of 3
- **Files:** 16 (6 created, 10 modified, 0 deleted) — 1,433 insertions, 78 deletions

## The observed query count per request

Measured live against the started application, with a `before_cursor_execute` listener counting
real cursor executions:

| Request | Status | Identity statements |
|---|---|---|
| linked + active | 200 | **1** |
| `identity_state='historical'` | 403 | **1** |
| `users.active = FALSE` | 403 | **1** |
| unlinked verified subject | 403 | **1** |
| no `Authorization` field | 401 | **0** |

One statement, whatever the outcome. The full statement list for a rejecting request is:

```
1. SAVEPOINT sa_savepoint_2
2. SELECT core.external_identities.id, core.external_identities.user_id, ...
3. ROLLBACK TO SAVEPOINT sa_savepoint_2
```

The two savepoint statements are the e2e harness's `join_transaction_mode="create_savepoint"`
rollback isolation, not production. Production issues the one `SELECT` and nothing else.

The zero on the last row is §1.5's ordering as a measurable fact: the wire contract runs at step 2
and a request that fails it never opens a session, so an unauthenticated flood costs no database
work. `TestOneQueryPerRequest` and `test_a_wire_contract_rejection_touches_the_database_not_at_all`
assert both, so a later refactor that adds a second query — or moves resolution ahead of the wire
contract — fails rather than merely slowing things down.

## The two `account_unavailable` responses are byte-identical

Also measured live, `historical_identity` versus `blocked_user`:

```
historical body: b'{"code":"account_unavailable"}'
blocked    body: b'{"code":"account_unavailable"}'
bodies identical:  True
statuses identical: True (403)
headers minus Date: {'content-length': '30', 'content-type': 'application/json'}
headers identical:  True
```

`Date` is excluded because it is the clock, not the response. Nothing else differs — same status,
same 30 bytes, same content type, same length.

The structural half of D-13 holds too, and is asserted rather than asserted-about:

- both branches are reached from the same `row` of the same statement, so neither issues a query,
  a lookup, or a network call the other skips (observed above: 1 statement each);
- both carry the *same `ErrorClass` object* — `historical.error_class is blocked.error_class` —
  so the two can never drift to different copy through an edit to one of them;
- the state columns are read in Python, never filtered in SQL. `test_the_state_columns_are_read_
  in_python_not_filtered_in_sql` compares the compiled statement across the two branches and
  requires them equal. A `WHERE identity_state = 'active'` would collapse outcome 2 into outcome 1
  *and* put the two rejections on different paths; this catches both at once.

**Timing normalization is deliberately absent**, per D-13. No `sleep`, no padding constant, no
`perf_counter` appears in `identity.py`, and no test asserts timing parity — a latency assertion
would be testing a property this product knowingly does not have. `test_no_timing_normalisation_
is_present` pins the absence so a future contributor does not "fix" it without revisiting D-13.

## The missing metrics exporter — an accepted v2.0 gap

**§1.2 and §8.2 require a bounded-cardinality counter as the alerting source for cross-route attack
volume and for a systemic verification break. This plan ships the counter. Nothing exports it.**

`RejectionCounter` implements exactly the required labels — result × bounded reason × route — and
`snapshot()` makes it readable. But this deployment has no Prometheus client, no scrape endpoint
and no exporter, and adding one is outside FOUND-01…FOUND-08. So:

- the counter increments correctly and is proven to (see coverage A8);
- **the operational alert §1.2 calls for cannot fire**, because nothing reads the counter;
- a systemic verification break is, by §1.2's own design, client-indistinguishable from ordinary
  session expiry — so this alert is the *only* detection path, and it is currently dark;
- the counter is per-process and in-memory. With more than one replica each holds its own view, and
  a restart discards it.

**This belongs on the v2.0 accepted-consequences list beside D-08's deferred gateway contract**, or
it needs an exporter scheduled. It is recorded here rather than left to be rediscovered, and is the
one item in this plan that a reader should not skim past. Logged in `deferred-items.md` as
**D-35-06-A**.

## The §1.4 wrong-variant choice plan 03 left open

Plan 03 left one decision to this plan: whether `get_preauth_identity` and `get_linked_identity`
should answer a wrong-variant context with `preauth_identity_not_allowed` rather than
`auth_required`, once `/auth/create-user` had a real caller.

**It does not yet, so the accessors were left alone — stated explicitly, as asked.** No route in
`REGISTRY` declares `preauth_callable = True`; §2.3 condition 6 permits only
`POST /auth/create-user` to, and that route belongs to Phase 37. The barrier therefore admits no
pre-auth principal on any registered route today, which means no handler can receive the wrong
variant, which means specialising the accessor would ship a branch nothing can reach and no test
can exercise honestly. Plan 03's own reasoning also still holds: a wrong variant arriving at an
accessor is a wiring bug between a route's declaration and its handler, not a caller condition, and
answering a bug with the caller-facing "complete account setup" contract sends a client round a
loop it cannot exit.

What this plan *did* implement is the half plan 03 correctly assigned to the barrier: the
caller-facing `preauth_identity_not_allowed` rejection now exists, at §1.5 step 5, in
`identity.py`'s outcome 1'. Phase 37 inherits a working rejection and one accessor to revisit.

## 35-01's deliberately-wrong test needed no retarget

35-01 left `test_invalid_bearer_token_returns_401` asserting `auth_required` "until plan 06 moves
verification onto the barrier". It sends `Bearer invalid.token.here` — which passes the §1.1 wire
contract, reaches step 3, and fails RS256 verification. `auth_required` is still exactly right, and
the case is now stronger than when it was written: it used to pass because nothing verified
anything, and now it passes because verification ran and refused. No edit was needed.

## Task Commits

| # | Task | Commit | Type |
|---|---|---|---|
| 1 | Task 1 RED: failing tests for the four-outcome matrix | `a46f9c5` | test |
| 2 | Task 1 GREEN: the single identity query and the counter | `d836110` | feat |
| 3 | Task 2: the barrier's full §1.5 ordering | `f6d69ef` | feat |
| 4 | Task 3 RED: the admission and wire-contract matrices | `6f19833` | test |
| 5 | Task 3 GREEN: the e2e seeding and stub-verifier harness | `1e813bf` | feat |

Both TDD tasks ran RED before GREEN: `a46f9c5` failed at collection against the absent
`auth.identity` module, and `6f19833` failed at collection against the absent `seed_identity`.

## Test Status

| Suite | Before | After | Δ |
|---|---|---|---|
| Unit (`pytest -q`) | 374 | **448** | +74 |
| E2E (`pytest -q -m e2e`) | 35 | **76** | +41 |
| Schema (`pytest -q -m schema`) | 77 | **77** | untouched |
| Combined (`pytest -q -m ""`) | 486 | **601 passed, 0 failed** | +115 |
| `ruff check src tests` | clean | **All checks passed!** | |
| `ty check src` | clean | **All checks passed!** | |

`448 + 76 + 77 = 601`. Zero `xfail`, zero `pytest.mark.skip` — `grep -rn "xfail\|pytest.mark.skip" tests/`
returns 0 lines.

New modules: `test_identity_resolution.py` (45), `test_barrier_wire_contract.py` unit (26),
`test_barrier_admission.py` (26), `test_barrier_wire_contract.py` e2e (15). `test_auth_security.py`
grew 9 → 12.

## Decisions Made

- **The join is an outer join, against RESEARCH.md's sketch.** Code Example 2 writes
  `.join(User, ...)`, which is inner. That silently merges two distinct §1.3 conditions: an
  identity row whose `user_id` resolves to nothing returns no row under an inner join, so the
  unresolvable-state case becomes outcome 1 and a broken link is read as a fresh identity — the
  precise thing SHARED-INVARIANTS' "never invent, reassign, merge, or repair an identity row
  inline" forbids. The outer join keeps the two apart at the cost of one keyword. It is defensive:
  `user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT` means no such row can exist,
  which is exactly why the join kind needed asserting directly — see Issues Encountered.
- **The route label is the registry path template.** `meta.path` is `/chats/{chat_id}`, not
  `scope["path"]`, so a thousand distinct chat ids collapse to one counter key. All three labels
  come from closed sets — `AuthEventResult`, `BoundedReason`, and the declared templates — so
  cardinality is bounded by construction rather than by hoping callers behave.
- **`record_rejection` tolerates a missing counter.** It logs `rejection_counter_missing` at ERROR
  and still returns the client its rejection. Raising would convert every 401 into a 500 on any
  application that forgot to construct the counter, which is both an availability regression and an
  anti-oracle break — a 500 where a 401 belongs tells a caller something a 401 does not. The
  lifespan always constructs it, so the branch is a guardrail, not a design.
- **An undeclared route gets a synthesised strictest `RouteMetadata`.** `lookup` returns `None` for
  an undeclared route; rather than special-casing `None` through resolution and the context, the
  barrier builds `RouteMetadata(method, path, category=authenticated)` with every flag at its
  default. `preauth_callable` is then `False` by construction, so an undeclared route cannot become
  pre-auth-callable by omission. (In a started process §2.3 aborts boot first; this is the belt.)
- **The `stub_verifier` fixture swaps `app.state.jwt_verifier` rather than mocking the barrier.**
  What is under test is the production barrier reading a verifier per request — the same mechanism
  Pitfall 5 warns about for the session factory. Swapping the attribute exercises it; patching
  `resolve_identity` or overriding a dependency would prove only that the patch took.
- **The e2e wire-contract module asserts the transport separately from the barrier.** The six cases
  go through the real app, but the "duplicates are not folded" claim is asserted against a bare
  recording ASGI app. If httpx folded a duplicate into one comma-joined value, the six cases would
  still return 401 — for the wrong reason — and the module would be quietly claiming something
  false about the deployed service.
- **`test_user_id` now depends on `firebase_token`.** It read `os.environ["FIREBASE_TEST_USER_ID"]`,
  which only `firebase_token` sets, and worked solely because `async_client` happened to be
  requested first. `linked_firebase_identity` needs it directly, so the missing edge was added
  rather than relied upon.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The inner join in RESEARCH.md Code Example 2 collapses two §1.3 outcomes**

- **Found during:** Task 1, writing `identity.py`.
- **Issue:** the researched statement uses an inner join. The plan's own `<behavior>` requires that
  "a resolution that finds an identity row whose user row is missing returns
  `Reject(INTERNAL_ERROR, …)`" — unreachable under an inner join, which returns no row at all and
  sends the case to outcome 1 instead. A dangling link would be read as an unlinked pair and, on a
  pre-auth-callable route, admitted.
- **Fix:** `isouter=True`, plus a `user is None` branch ahead of the state checks. Still exactly one
  `select(` and one statement, so every acceptance criterion is unaffected.
- **Committed in:** `d836110` (the branch), `1e813bf` (the assertions that pin the join kind).

**2. [Rule 3 - Blocking] `tests/unit/test_auth_security.py`'s positive control could no longer pass**

- **Found during:** Task 2, first full unit run.
- **Issue:** the module drives the real barrier over a bare `FastAPI()` app carrying no
  `app.state`. Once the barrier verified tokens, a well-formed credential hit
  `AttributeError: 'State' object has no attribute 'jwt_verifier'` → 500. The module's own docstring
  had flagged this ("the barrier does not verify the token here — plan 06 adds that").
- **Fix:** supplied the three attributes the real lifespan supplies — a fixed-key verifier, a
  no-identity session stand-in, and a counter — and retargeted the two positive-control cases from
  200 to 403 `preauth_identity_not_allowed`. The control still does its job and does it better: the
  answer *changes class* when the wire contract passes, which a 200 no longer proves, since a 200
  would also be produced by a barrier that skipped steps 3–5 entirely. Three cases added while
  there (step-3 refusal, counter increments, label shape).
- **Committed in:** `f6d69ef`.

**3. [Rule 3 - Blocking] Nine e2e refusal cases asserted a class the barrier no longer returns**

- **Found during:** Task 2, first full e2e run.
- **Issue:** `test_chats.py`, `test_chat_queries.py`, and `test_error_cases.py::
  TestUnadmittedCallerLearnsNothing` all assert `401 auth_required` for the real Firebase
  credential. That subject is *verified*; it simply has no `core.external_identities` row, so §1.3
  outcome 1' now applies and the answer is `403 preauth_identity_not_allowed`.
- **Fix:** retargeted all nine, with the module docstrings rewritten to say why the new class is a
  strengthening: the old 401 was consistent with a barrier that never touched the database, and the
  new 403 is not. Their anti-oracle intent — three branches, one indistinguishable answer — is
  unchanged. Two classes renamed `TestUnadmittedCallerIsRefused` → `TestUnlinkedCallerIsRefused`,
  because "unadmitted" no longer says which step refused.
- **Committed in:** `f6d69ef`.

**4. [Rule 3 - Blocking] `GET /` and `GET /examples` are authenticated routes and stopped serving**

- **Found during:** Task 2, first full e2e run.
- **Issue:** `test_root.py` and `test_examples.py` assert served 200s. §8.1 puts both routes in the
  authenticated partition, so once the barrier resolved identity they needed an admitted caller,
  and the e2e Firebase subject had no identity row.
- **Fix:** added `linked_firebase_identity`, a fixture seeding the real credential's
  `(issuer, subject)` inside the per-test transaction, and had both modules request it. Retargeting
  them to 403 was the alternative and was rejected: it would have left `GET /` and `GET /examples`
  with no served coverage anywhere in the suite, and `seed_identity` exists precisely so that is not
  necessary. They now prove more than before — that a real Firebase credential resolves through a
  real identity row to a served response.
- **Committed in:** `f6d69ef` (the barrier change that exposed it), `1e813bf` (the fixture).

**5. [Rule 2 - Missing coverage] Task 1 had no unit module, but three of its truths need one**

- **Found during:** Task 1, choosing where the TDD RED commit goes.
- **Issue:** the plan marks task 1 `tdd="true"` but names no unit test file, and its acceptance
  criterion is `pytest -q` (unit only). Three of the plan's `must_haves.truths` are unreachable
  through the database: `core.identity_state` is a two-value `NOT NULL` enum, so NULL and
  unrecognized states cannot be stored; `users.active` is `BOOLEAN NOT NULL`, so a truthy
  non-boolean cannot be stored; and `user_id` carries a `NOT NULL` foreign key, so a dangling user
  reference cannot exist. An e2e-only plan would have shipped all three branches untested.
- **Fix:** added `tests/unit/test_identity_resolution.py` (45 cases) driving `resolve_identity`
  against a stub session that records the statements it is handed. It covers the three unreachable
  branches, the per-outcome statement count, and the counter.
- **Committed in:** `a46f9c5` (RED), `d836110` (GREEN), `1e813bf` (the statement-shape additions).

---

**Total deviations:** 5 — one Rule 1 bug (the inner join), one Rule 2 coverage gap, three Rule 3
blockers. No Rule 4 architectural question arose. Deviations 2–4 are all one consequence: this is
the plan where the barrier starts resolving identity, so every test that assumed it did not had to
move. The plan anticipated the direction and named D-11 as the retarget rule; the specific twelve
cases are what it did not enumerate.

## Issues Encountered

- **Seven mutations, all caught — but only after the sixth exposed a real hole.** Coverage was
  verified by mutating the shipped modules rather than assumed from a green run:

  | Mutation | Result |
  |---|---|
  | M1 — `isouter=True` → inner join | **passed 597, caught nothing** → fixed, then **1 failed** |
  | M2 — `user.active is not True` → `not user.active` | 3 failed |
  | M3 — `!= IdentityState.active` → `== IdentityState.historical` | 6 failed |
  | M4 — label with `scope["path"]` instead of the template | 1 failed |
  | M5 — counter never increments | 6 failed |
  | M6 — filter `identity_state = 'active'` in SQL | 5 failed |
  | M7 — pass through instead of returning the rejection | 26 failed |

  **M1 is the one worth reading.** The inner-join form passed the entire 597-case suite. The unit
  test for the unresolvable-user branch hands `(identity, None)` straight to a stub session, so it
  proves the *branch* exists while proving nothing about the query that would produce it — and no
  e2e test can, because the foreign key makes the row unconstructible. A defensive branch whose
  only guarantee is a join keyword needs that keyword asserted directly, so
  `TestTheResolutionStatement` now compiles the statement the stub was handed and requires
  `LEFT OUTER JOIN` in it. Without that, the code would have been correct and the correctness
  entirely unprotected.

  Each mutation asserted its anchor matched before its result was read, and
  `git diff --exit-code -- src/` confirmed the tree byte-identical after every restore.

- **Rollback isolation verified, not assumed.** After the full run, the live database reports
  `core.users` 0 rows and `core.external_identities` 0 rows. Forty-one new e2e cases seed identity
  pairs and every row rolled back — which is the direct evidence that the barrier reads
  `scope["app"].state.session_factory` per request rather than caching it (Pitfall 5). A cached
  factory would have written to the real database and left rows behind.

- **No out-of-scope discoveries.** The two pre-existing warnings in a combined run
  (`langchain_core` pydantic-v1 on 3.14, and PyJWT's `InsecureKeyLengthWarning` from
  `test_jwt_security.py`'s deliberate HS256 case) reproduce exactly as measured at baseline.

- **One item deferred:** D-35-06-A, the missing metrics exporter. Nothing else.

## Known Stubs

None. Every symbol this plan declares is implemented, wired, and exercised over the real transport.

One thing is deliberately unbuilt and is **not** a stub, because a stub is an unfinished
implementation and this is a complete one with no consumer: `RejectionCounter` is a working counter
that nothing exports. It is covered in full above and logged as D-35-06-A.

Two things are correctly incomplete and belong to named owners:

| Item | State | Owner |
|---|---|---|
| `preauth_callable = True` on a real route | the barrier's outcome-1 admit path exists and is unit-covered; no route declares the flag, so it has no e2e case | Phase 37 (`POST /auth/create-user`) |
| The `audit.auth_events` write on a barrier rejection | §8.2 puts every route this phase registers off the audited path, so no row is due; the writer itself is plan 35-08's | plan 35-08 |

The nineteen served chat cases plan 11 restores are still absent, as 35-04-SUMMARY.md records —
but the blocker named there is gone: `seed_identity` plus `stub_verifier` make a served chat
response reachable, and `test_the_handler_sees_the_resolved_user` demonstrates one.

## Threat Flags

None. Every file this plan created or modified is covered by the plan's own `<threat_model>`. No
new route was registered, no new network path opened, and the one new query is a parameterised ORM
select. All seven `mitigate` dispositions are implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-06-01 | Admission is a positive test on two columns: `identity_state != IdentityState.active` and `user.active is not True` both reject. NULL, `''`, and an unrecognized state all take the `historical_identity` branch, including on a `preauth_callable` route; a truthy non-boolean `active` takes `blocked_user`. Mutations M2 and M3 confirm the coverage. |
| T-35-06-02 | Outcome 2 is reached from a *found* row, so a retired identity can never take the no-row path. `test_a_retired_identity_never_surfaces_preauth_identity_not_allowed` and its e2e counterpart assert the negative directly. |
| T-35-06-03 | One `ErrorClass` object shared by both branches, one status, one 30-byte body, one set of headers — measured, not inferred. Reached from the same single statement, which `test_the_state_columns_are_read_in_python_not_filtered_in_sql` pins by comparing the compiled SQL across the two branches. |
| T-35-06-04 | **Accepted, as planned.** No timing normalization, and no test asserts timing parity. `identity.py` contains no `sleep` and no `perf_counter`, asserted by `test_no_timing_normalisation_is_present` so the absence stays deliberate. |
| T-35-06-05 | All three counter labels come from closed sets; the route label is the registry path template. `test_the_route_label_is_the_template_not_the_request_path` and `test_no_label_carries_a_token_or_a_subject` assert both, and mutation M4 confirms. The bounded reason never leaves the server: `ErrorResponse` has exactly one field. |
| T-35-06-06 | `'state' not in getsource(__init__)` and three per-request `scope["app"].state` reads. The operational proof is the zero-row database after 41 seeding e2e cases. |
| T-35-06-07 | The outer join keeps the unresolvable case distinct, and it returns `INTERNAL_ERROR` with both actor fields populated from the verified token — the shape `audit.auth_events`' CHECK requires for every result but `invalid_external_jwt`. `resolve_identity` takes a session but issues one `SELECT` and no write of any kind. |
| T-35-06-SC | No package installed. The legitimacy gate stays vacuous for Phase 35. |

`tests/unit/test_adapter_interfaces.py::test_foundation_calls_no_adapter_method_anywhere_in_src`
still passes: neither new `src/` module names any of the ten adapter methods, and the barrier calls
`verifier.verify(token)` through the §1.2 seam, never a concrete provider.

## Next Phase Readiness

Ready. The barrier is complete as §1.5 specifies it, and every later phase's routes can assume the
typed context is attached at handler entry.

- **Plan 08** (audit writer) has the two things it needs from here: `Reject` carries
  `actor_issuer`/`actor_subject` on every branch a token was verified on, which is the shape
  Pitfall 10 requires, and `record_rejection` is the one place a rejection is already funnelled
  through — the audited-path write belongs beside it, gated on `meta.operation is not None`. Note
  that §8.2 means *no* route registered today is on that path, so plan 08's e2e coverage needs a
  route with an `operation`, or a synthetic registry entry.
- **Plan 11** can restore the served chat cases: `seed_identity` + `stub_verifier` +
  `create_chat` compose, and `test_the_handler_sees_the_resolved_user` is the working template.
  `seed_identity` must run before `create_chat` for the same pair, or `create_chat` seeds an
  `anonymous` identity itself.
- **Phase 36** inherits `RequestContext.evaluated_at` as the single captured evaluation time and
  `attempt_id` as the server-generated identifier. REBIND-05's grant resolution must derive every
  time-dependent value from `evaluated_at`, never a fresh `now()`.
- **Phase 37** owns `POST /auth/create-user`, the first and only route that may declare
  `preauth_callable = True`. When it lands, outcome 1's admit path gets its first e2e case, and
  `get_preauth_identity`'s wrong-variant class becomes a real decision rather than a hypothetical.
- **The metrics exporter (D-35-06-A) is unowned.** It needs a phase or an explicit acceptance.

## Self-Check: PASSED

- All 16 claimed created/modified files exist on disk with the claimed content.
- All 5 claimed commits are in `git log`: `a46f9c5`, `d836110`, `f6d69ef`, `6f19833`, `1e813bf`.
- `pytest -q -m ""` exits 0 at **601 passed, 0 failed**; `ruff check src tests` and `ty check src`
  both print `All checks passed!`.
- Every acceptance criterion in the plan verified by direct execution, including the three
  `inspect.getsource` probes (`select(` count 1, `is not True` present, `!= IdentityState.active`
  present), the `RejectionCounter` `[2]` probe, `'state' not in __init__`, and
  `scope["app"].state` count 3.
- `git diff --diff-filter=D --name-only` over this plan's commits is empty — nothing was deleted.
- Working tree carries no change outside this plan's scope: `docker-compose.yml`, `.gsd/` and
  `.planning/research/.cache/` were pre-existing, are untouched, and remain uncommitted. `uv.lock`
  is unmodified. `.planning/STATE.md` and `.planning/ROADMAP.md` are untouched, as instructed.

---
*Phase: 35-foundation*
*Completed: 2026-08-20*
