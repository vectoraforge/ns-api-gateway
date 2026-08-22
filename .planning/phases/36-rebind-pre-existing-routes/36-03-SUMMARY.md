---
phase: 36-rebind-pre-existing-routes
plan: 03
subsystem: api
tags: [fastapi, sqlmodel, postgres, row-locking, quota, entitlements, dependency-injection]

# Dependency graph
requires:
  - phase: 36-01
    provides: AccessGrant / AccessTier / UserMonthlyUsage models, the two native grant enums, and the seeded `registered` tier row this plan's fixture FKs against
  - phase: 36-02
    provides: the AnalyzeResponse list defaults, so a correct phrase returns 200 rather than 500 — the gate now runs ahead of a path that no longer fails for free
  - phase: 35-foundation
    provides: the barrier, RequestContext.evaluated_at, the route registry and its §2.3 startup assertion, and the closed error registry carrying QUOTA_EXCEEDED
provides:
  - GrantsDB.lock_effective_grants — the shared effective-grant predicate, FOR UPDATE, ascending by grant id, no row-count cap
  - src/nativespeaker/api/quota.py::consume_quota — the D-03 named resolver seam Phase 38 imports
  - require_quota (own-session, commits before the handler) and require_quota_create_chat (the D-14 body-declaring wrapper)
  - §2.3 condition 10 — quota_checked and the attached dependency cross-checked by callable identity in both directions at boot
  - tests/e2e/conftest.py::seed_grant + the quota_grant fixture — the only grant-writing code in the repo, test-only
affects: [36-04 usage row and increment, 36-05 POST /chats/{chat_id}, 38 auth-sync, 41 claim-anonymous-grant, 42 claim-registered-grant, 45 subscription grants]

actuals:
  tokens: 12600
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A FastAPI dependency that must not hold locks across the handler opens its own session and commits inside its own body, never `Depends(get_db)`"
    - "A per-route wrapper dependency declares the route's body model as a plain parameter, so FastAPI validates the body before the dependency's side effect runs"
    - "A registry flag is cross-checked against the wiring it claims, by callable identity, at boot"

key-files:
  created:
    - src/nativespeaker/api/database/grants.py
    - src/nativespeaker/api/quota.py
    - tests/e2e/test_quota.py
  modified:
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/auth/registry.py
    - src/nativespeaker/api/routers/chats.py
    - src/nativespeaker/api/database/__init__.py
    - tests/e2e/conftest.py
    - tests/e2e/test_chats.py
    - tests/e2e/test_flows.py
    - tests/e2e/test_error_cases.py
    - tests/unit/conftest.py
    - tests/unit/test_route_registry.py

key-decisions:
  - "`seed_grant` defaults to `source = manual`, not `registered_account_grant`. The two free sources populate the `anti_abuse_required_grant_id` generated column, whose deferrable FK demands a matching `core.access_grants_anti_abuse` row at commit — a table with no SQLModel class in this phase. `manual` is the schema's hand-issued source, which is what a fixture writes."
  - "`consume_quota` takes a required keyword-only `route` parameter. The plan's telemetry rule requires the route path template as a label, and the resolver has no other way to learn it; a default would let the label be silently forgotten."
  - "Condition 10 reads `route.dependencies` (raw, decorator-level) and matches `.dependency` by identity. `route.dependant.dependencies` also carries parameter-level dependencies and would conflate them."
  - "The quota-wrapper set is a function-scope tuple, not a module-level frozenset: the import that breaks the auth.registry <-> app.dependencies cycle is itself function-scope, so no module-level constant can exist."
  - "No `Retry-After` on the 429 and no counter increment. `QuotaExceededError` inherits `extra_headers() -> None`, and `record_rejection`'s `result` is typed to the closed 44-value `AuthEventResult` enum the migration pins."

patterns-established:
  - "Own-session dependency: `async with request.app.state.session_factory()`, commit inside the body, no yield — so the lock window closes before the handler and the provider round trip."
  - "D-14 body declaration: the wrapper's body parameter must carry the handler's parameter *name*, or FastAPI switches to an embedded body and the wire contract changes."
  - "Deliberate-gap comment: an unimplemented spec step is marked with a banner naming the plan that owns it and stating what the gap currently permits, rather than stubbed with a permissive branch."

requirements-completed: []

coverage:
  - id: D1
    description: "`POST /chats` from an admitted caller with no effective grant returns 429 `quota_exceeded` in the shared error shape — not a 500 and not a 200."
    requirement: REBIND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestNoEffectiveGrant::test_a_caller_with_no_grant_is_refused"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestNoEffectiveGrant::test_the_no_grant_refusal_carries_the_shared_error_body"
        status: pass
    human_judgment: false
  - id: D2
    description: "A grant row that is not effective — not yet started, already ended, or status not `active` — is refused identically, so the rejection is a property of the shared predicate rather than of an empty table."
    requirement: REBIND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestNoEffectiveGrant::test_a_not_yet_started_grant_is_no_grant"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestNoEffectiveGrant::test_an_already_ended_grant_is_no_grant"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestNoEffectiveGrant::test_a_grant_whose_status_is_not_active_is_no_grant[revoked|expired]"
        status: pass
    human_judgment: false
  - id: D3
    description: "An admitted caller holding a seeded active grant is admitted, reaches the handler, and returns its v1.6 status."
    requirement: REBIND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestASeededGrantIsAdmitted::test_a_seeded_grant_reaches_the_handler"
        status: pass
      - kind: e2e
        ref: "tests/e2e (181 passed) — the six repointed chat cases run against quota_grant and answer 2xx / their business 4xx"
        status: pass
    human_judgment: false
  - id: D4
    description: "Condition 10 makes `quota_checked` enforcement: equal sets pass, and either direction of disagreement fails boot with a distinctly-labelled line naming the route."
    requirement: REBIND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_route_registry.py::TestCondition10QuotaFlagAndDependencyDisagree (7 cases, -k quota_checked)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py (9 passed) — the real app boots with condition 10 active"
        status: pass
      - kind: other
        ref: "uv run uvicorn nativespeaker.api.app.main:app -> 'Application startup complete'; curl localhost:8124/health/ready -> 200 {\"status\":\"up\"}"
        status: pass
    human_judgment: false
  - id: D5
    description: "The condition-10 RuntimeError is deterministic: both set differences are emitted through `sorted()`, so the same disagreement produces byte-identical text."
    requirement: REBIND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_route_registry.py::TestCondition10QuotaFlagAndDependencyDisagree::test_the_quota_checked_message_is_byte_identical_across_runs"
        status: pass
    human_judgment: false
  - id: D6
    description: "Condition 10 is a no-op on empty input — zero routes with a zero-length registry, and a registry declaring zero `quota_checked` entries, add no problem."
    requirement: REBIND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_route_registry.py::TestCondition10QuotaFlagAndDependencyDisagree::test_empty_input_adds_no_quota_checked_problem"
        status: pass
    human_judgment: false
  - id: D7
    description: "The effective-grant statement takes row locks and orders ascending by grant id, with no row-count cap (SHARED-INVARIANTS:33, D-10)."
    requirement: REBIND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestTheEffectiveGrantStatement::test_the_statement_locks_the_rows_and_orders_ascending_by_grant_id"
        status: pass
      - kind: other
        ref: "grep -c with_for_update src/.../database/grants.py == 1; grep -ciE '\\.limit\\(' (comments stripped) == 0; grep -cE 'selectinload|joinedload' == 0"
        status: pass
    human_judgment: false
  - id: D8
    description: "No lock is held and no network call is made while the quota session is open: the transaction commits and the session closes before the handler body is entered."
    requirement: REBIND-05
    verification:
      - kind: other
        ref: "`require_quota` uses `async with request.app.state.session_factory()` with an in-body commit and no yield; the FastAPI 0.135.1 ordering probe in the plan's §A2 confirms decorator dependencies complete before the handler body"
        status: pass
    human_judgment: true
    rationale: "The lock window is proven by reading the code plus a framework-ordering probe, not by an observation of a held lock. Only a two-connection contention test can show it directly, and that is plan 36-05's `tests/schema/test_grant_locks.py`."

# Metrics
duration: 7min
completed: 2026-08-21
status: complete
---

# Phase 36 Plan 03: End-to-End Quota Gate on POST /chats Summary

**The product's primary route now refuses a caller with no entitlement — 429 `quota_exceeded` before the handler, resolved in a transaction that closes before the LLM call — and the registry flag that claims it is checked against the wiring at boot.**

## Performance

- **Duration:** 7 min (first task commit to last)
- **Started:** 2026-08-21T19:19:24-07:00
- **Completed:** 2026-08-21T19:26:22-07:00
- **Tasks:** 2 of 2
- **Files modified:** 13 (3 created, 10 modified)

## Accomplishments

- **One thin path through every layer, committed green.** `POST /chats` -> barrier admission ->
  `require_quota_create_chat` -> `require_quota`'s own session -> `consume_quota` ->
  `GrantsDB.lock_effective_grants` -> 429. Seven source layers and three test seams, each at its
  final shape, verified over the real transport against live PostgreSQL, Firebase and OpenAI.
- **`GrantsDB.lock_effective_grants` is the reference implementation of the lock order.** The
  shared effective-grant predicate (`status == active AND starts_at <= t AND (ends_at IS NULL OR
  ends_at > t)`), `FOR UPDATE`, ascending by grant id, no row-count cap, no eager loading, no
  system clock. Every predicate carries its reason in a comment beside it, because Phases 41, 42
  and 45 copy this shape rather than re-deriving it.
- **`quota.py` exists as the D-03 named seam**, with the gap for §8.4 steps 2-4 marked by a banner
  naming plan 36-04 and stating plainly what the gap currently permits — a grant holder passes
  uncharged — rather than papered over with a permissive branch.
- **`quota_checked` became enforcement.** Condition 10 walks `route.dependencies` (the raw
  decorator-level list) and matches by callable identity against the wrapper set, reporting both
  directions as separately labelled, `sorted()`-emitted problem lines. A route that declares the
  flag and forgets the dependency — the failure mode that serves the product free and invisibly —
  now aborts boot.
- **The e2e suite stayed green across the wiring commit.** `seed_grant` writes the grant *and* its
  usage row in one call, and the six pre-existing admitted chat cases were repointed onto
  `quota_grant` in the same commit as the decorator and the registry flag.

## Task Commits

1. **Task 1 (RED): failing e2e cases for the quota gate** — `67f0511` (test)
2. **Task 1 (GREEN): the whole tracer slice wired and green** — `096ac3a` (feat)
3. **Task 2: unit cases for condition 10, both directions** — `fe07be1` (test)

## Files Created/Modified

- `src/nativespeaker/api/database/grants.py` — `GrantsDB.lock_effective_grants`, plus the module
  docstring recording SHARED-INVARIANTS:33 and why the locking is two statements, not a join
- `src/nativespeaker/api/quota.py` — `consume_quota`, the D-03/D-04/D-08/D-09/D-10/D-11 docstring,
  the structured rejection log, and the 36-04 slot
- `src/nativespeaker/api/database/__init__.py` — `GrantsDB` in `__all__` and the second import
- `src/nativespeaker/api/app/dependencies.py` — the `# ---` quota-seam banner, `require_quota`,
  `require_quota_create_chat`; the D-16 `require_quota` entry retired from the deletion block
- `src/nativespeaker/api/routers/chats.py` — `dependencies=[Depends(require_quota_create_chat)]`
  on `POST /chats` and one paragraph in the module comment
- `src/nativespeaker/api/auth/registry.py` — `quota_checked=True` on the `POST /chats` entry,
  condition 10, and the docstring's "nine" -> "ten"
- `tests/e2e/conftest.py` — `REGISTERED_TIER_ID`, `seed_grant`, the `quota_grant` fixture
- `tests/e2e/test_quota.py` — `TestNoEffectiveGrant`, `TestASeededGrantIsAdmitted`,
  `TestTheEffectiveGrantStatement`
- `tests/e2e/test_chats.py`, `test_flows.py`, `test_error_cases.py` — the admitted `POST /chats`
  cases repointed onto `quota_grant`; `test_chats.py`'s "no quota to assert" paragraph retired
- `tests/unit/conftest.py` — `require_quota_create_chat` override in the `client` fixture
- `tests/unit/test_route_registry.py` — `_app(dependencies=...)` and
  `TestCondition10QuotaFlagAndDependencyDisagree`

## Decisions Made

- **`manual`, not `registered_account_grant`, for the seeded grant.** See Deviations 1 — this is
  the one decision here that changes a plan-named default, and it is forced by the schema.
- **`consume_quota` takes `route`.** The telemetry requirement names the route path template as a
  label; the resolver cannot derive it, and an optional parameter would let it be dropped silently.
  Documented as a departure because D-03 rates the seam's signature costly to change.
- **No `record_rejection`, no `AuthEventResult` member, no counter.** Reusing the auth counter
  needs either a non-member string (breaking bounded cardinality) or an enum widening the migration
  forbids. One structured log line with two closed-set labels is the whole telemetry.
- **`test_missing_phrase_returns_422` was deliberately *not* given a grant.** Left ungranted, it is
  a live D-14 regression test in the e2e suite: if body validation ever stopped preceding the
  dependency, it would turn 429 and fail. Granting it would have made it pass either way.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `seed_grant`'s planned default source cannot be inserted**

- **Found during:** Task 1, writing the e2e fixture
- **Issue:** The plan specified `source=AccessGrantSource.registered_account_grant`. Both free
  sources populate `core.access_grants.anti_abuse_required_grant_id`
  (`migrations/20260818_01_initial-release.sql:404-406`), whose `DEFERRABLE INITIALLY DEFERRED` FK
  (`:520-523`) requires a matching `core.access_grants_anti_abuse` row at commit. That table has no
  SQLModel class (36-01 mapped three tables, not four) and its CHECK demands a non-NULL
  `idp_account_hash` plus key version. The seed would have failed at commit, in the fixture, on
  every admitted chat case.
- **Fix:** Defaulted `source` to `AccessGrantSource.manual` — the source the schema reserves for a
  hand-issued grant, which is exactly what a fixture writes. It requires no companion row (the
  anti-abuse CHECK forbids one for `manual`), and the effective-grant predicate reads
  `status`/`starts_at`/`ends_at` only, never the source, so nothing under test is weakened. The
  parameter stays, so 36-04 and 36-05 can vary it. Reason recorded in the helper's docstring.
- **Files modified:** `tests/e2e/conftest.py`
- **Commit:** `67f0511`

### Documented departures from the plan text

**2. `consume_quota` gained a required `route` keyword-only parameter.** The plan's signature is
`(session, *, user_id, evaluated_at) -> None`, and its telemetry instruction requires the route
path template as a log label. The resolver has no access to the request, so the label must be
passed. Made required rather than defaulted: a default would let a future call site drop the label
without failing anything. `require_quota` supplies `context.route_metadata.path`.

**3. `seed_grant` gained a `status` parameter.** Not in the plan's signature, but the plan's own
`<behavior>` list requires "a grant whose `status` is not `active` is not effective -> 429". Two
cases (`revoked`, `expired`) parametrize it.

**4. Step 7 repointed three e2e modules, not four, and not every line the plan listed.** The plan's
line numbers were stale against the working tree. Each listed site was checked against what it
actually requests:
  - `test_chats.py` (5 × `TestCreateChat`, 1 × `TestFollowup`), `test_flows.py`, and
    `test_error_cases.py::test_unsupported_language_returns_400` **were** repointed — all POST
    `/chats` as an admitted caller and would have turned 429.
  - `test_error_cases.py:49` (`test_followup_nonexistent_chat_returns_404`) and
    `test_isolation.py:92` (`test_cannot_post_to_other_user_chat`) drive `POST /chats/{chat_id}`,
    which has no quota dependency until plan 36-05. `test_isolation.py` never calls `POST /chats`
    at all — its `owned_chat` fixture seeds rows directly. Neither needed the fixture.
  - `test_error_cases.py:92, 99` are inside `TestUnadmittedCallerLearnsNothing`, whose whole
    subject is that **no** identity row exists. `quota_grant` depends on `linked_firebase_identity`,
    so adding it there would have seeded the identity and destroyed the anti-oracle assertions.
  - `test_error_cases.py:63` (`test_missing_phrase_returns_422`) was left ungranted on purpose —
    see Decisions Made.
The plan's acceptance criterion expecting "the four repointed e2e test modules" in the wiring
commit is therefore satisfied by three modules; the criterion's intent (flag + decorator + repoints
in one commit) holds — `096ac3a` carries all of them.

**5. No `# noqa` on the unused `body` parameter.** The plan asks for a named linter ignore. This
repo's ruff `select` is `["E", "W", "F", "I", "UP"]` — no `ARG` rules, so nothing flags an unused
parameter and a `# noqa: ARG001` would be a suppression for a rule that is not enabled. The
parameter's purpose is recorded in the wrapper's docstring instead, including why its *name* is
load-bearing.

**6. The quota-wrapper set is a function-scope tuple, not a module-level frozenset.** The plan asks
for both a module-level frozenset and a function-scope import; the two are mutually exclusive,
since `app.dependencies` cannot be imported at `auth.registry` module scope without forming the
cycle the local import exists to break. The identity match is unchanged.

**7. Task 1 committed as two commits (RED then GREEN).** Task 1 carries `tdd="true"`. The plan's
"commit steps 1-9 such that steps 4, 5 and 7 land together" is satisfied: `096ac3a` carries the
decorator, the registry flag, condition 10 and every repointed test module.

**8. Task 2 had no RED phase.** Condition 10 was written by the tracer, so its unit cases pass on
first run by construction. The task is test-only and committed as `test(...)`. Its determinism and
empty-input cases are genuinely new pins, not restatements of what task 1 already proved.

**9. `TestTheEffectiveGrantStatement` imports `GrantsDB` inside the test.** A module-scope import
would have turned every behavioural case in `test_quota.py` into a collection error during the RED
commit, hiding the `200 != 429` failure the RED phase exists to show. The reason is in a comment.

**10. The tracer feedback gate was not surfaced as an interactive checkpoint.** Auto mode is off
(`workflow.auto_advance` and `workflow._auto_chain_active` both `false`), so the tracer's
`<verify>` should have been returned as a `checkpoint:human-verify` before Task 2 rather than
self-verified. The substance of the gate was performed — the full e2e suite (181 passed), the unit
suite, ruff, ty, and a real `uvicorn` boot with a 200 from `/health/ready` were all run and green
before Task 2 started — but the human confirmation step was skipped. Recorded rather than hidden.

**11. `requirements.mark-complete` not run.** The plan claims REBIND-01, REBIND-05 and REBIND-06.
REBIND-05's usage-row locking, fail-closed-on-missing-row, rollover and non-negative `remaining`
are plans 36-04's and 36-05's; REBIND-06 also spans 36-04/36-05. Checking any of them off here
would report the phase's central behaviour as done while one branch of it exists.

---

**Total deviations:** 1 auto-fixed (1 × Rule 3), 10 documented departures.
**Impact on plan:** No scope change. The auto-fix was forced by a schema constraint the plan did
not account for; every other departure narrows or explains rather than widens.
`docker-compose.yml` and `uv.lock` were never staged.

## Issues Encountered

- **`uvicorn` will not boot from a bare shell.** `EnvironmentConfig()` reads `.env` only through
  `pytest-dotenv` under pytest; the plan's `uv run uvicorn ...` verification step needs
  `set -a; . ./.env; set +a` first. Not a defect, but the plan's verification line as written fails.
- **`gsd-tools query state.update-progress`** still fails with "Progress field not found in
  STATE.md", as plans 36-01 and 36-02 reported. Known non-fatal tooling issue; not investigated.
- **Two stale husk directories removed.** `src/nativespeaker/api/quota/` and
  `src/nativespeaker/api/ratelimit/` held only untracked `__pycache__` from the Phase 35 D-05/D-16
  deletions. Removed so `nativespeaker.api.quota` resolves to the module; no diff, nothing to
  commit.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest tests/e2e/test_quota.py -m e2e -q` | 8 passed |
| `uv run pytest tests/e2e/test_quota.py -k no_grant -m e2e` | 6 selected, 6 passed |
| `uv run pytest tests/e2e -m e2e -q` | 181 passed (was 173) — six repointed chat cases green, not 429 and not 500 |
| `uv run pytest tests/e2e/test_startup_assertion.py -x -m e2e` | 9 passed |
| `uv run pytest -q` | 923 passed, 261 deselected (was 915) |
| `uv run pytest -q -m ""` | **1184 passed** (baseline 1168; +16, no regression) |
| `uv run ruff check src tests` | clean |
| `uv run ty check src` | clean |
| `uv run uvicorn ...` + `curl /health/ready` | "Application startup complete"; HTTP 200 `{"status":"up"}` |
| `import nativespeaker.api.quota` | resolves to `.../api/quota.py` — the husk no longer shadows it |
| route-attachment probe | `attached` |
| registry-flag probe | `one flag set` (exactly one, on `POST /chats`) |
| `grep` gates (`text(`, `selectinload`/`joinedload`, `.limit(`, `datetime.now`, `record_rejection`, grant-mint) | all `0`, comments stripped first |
| `grep -c with_for_update .../grants.py` | 1 |
| `grep -c 'class TestCondition10' tests/unit/test_route_registry.py` | 1 |
| `_app` passthrough probe | `passthrough present` |
| `git log --stat -3 \| grep -cE 'docker-compose.yml\|uv.lock'` | 0 |
| `git status --porcelain` | `docker-compose.yml` and `uv.lock` still ` M`, unstaged, uncommitted (D-15) |
| deletion check on all three commits | no tracked file deleted |

## Threat Flags

None. No new network endpoint or trust boundary is introduced — the change is a gate in front of an
existing one. Against the plan's register:

- **T-36-bypass:** mitigated as specified. `.with_for_update()` is on the effective-grant select
  and grep-asserted. Verified end-to-end under real contention is plan 36-05's
  `tests/schema/test_grant_locks.py`; here it is proven at the statement level only.
- **T-36-bypass2:** upheld. The user id comes only from `RequestContext.identity.user.id`. No
  client-supplied id, header, or body field reaches the grant selection — `require_quota` reads
  nothing off `body`.
- **T-36-drain:** mitigated and now proven over the real transport.
  `test_error_cases.py::test_missing_phrase_returns_422` posts `{"lang": "en"}` to `/chats` with no
  grant seeded and still gets 422, so body validation precedes the dependency's session work.
- **T-36-deadlock:** upheld. Grants are locked ascending by grant id, and no usage-row statement
  exists yet to order against it. The one-statement-per-table shape is in place for 36-04.
- **T-36-lockspan:** mitigated. `require_quota` opens and commits its own session, does not yield,
  and does not take `Depends(get_db)`. Routed to human judgment as deliverable D8.
- **T-36-telemetry:** mitigated. The fail-closed branch logs `quota_rejected` with
  `branch="no_effective_grant"` and the route path template. `record_rejection` is not called
  (grep-asserted) and `AuthEventResult` is untouched.
- **T-36-sqli:** upheld. ORM select constructs with `col()`-wrapped comparisons; zero `text(`.
- **T-36-idor:** upheld. The quota dependency reads no client-supplied identifier;
  `tests/e2e/test_isolation.py` is unchanged and green.
- **T-36-mint:** upheld and stronger than the register requires. `src/` inserts no grant row and no
  usage row — grep-asserted across `quota.py`, `grants.py` and `dependencies.py`. The only
  grant-writing code in the repo is `tests/e2e/conftest.py::seed_grant`, unreachable from any route.
- **T-36-oracle:** accepted disposition unchanged. This plan produces no 500 branch at all.
- **T-36-SC:** upheld. Zero packages installed; `uv.lock` untouched.

## Known Gaps

- **A caller holding an effective grant currently passes the gate uncharged.** §8.4 steps 2-4 —
  the usage-row lock, D-09's fail-closed on a missing row, the lazy period rollover, the allowance
  arithmetic and the increment — are plan 36-04's. The gap is marked by a banner comment in
  `quota.py` and is the *stricter* of the two possible incomplete states: no `core.user_monthly_usage`
  row is created, so D-09's never-lazily-mint rule cannot be violated by an unfinished increment.
- **D-10's >1-effective-grant tripwire is not implemented.** `lock_effective_grants` deliberately
  returns every matching row with no cap so the caller *can* see a second grant, but no caller
  inspects the length yet. That branch is 36-04's, and it is unreachable in PostgreSQL anyway while
  `ix_access_grants_one_active_per_user` stands.
- **`POST /chats/{chat_id}` is ungated.** Its wrapper and its `quota_checked=True` are plan 36-05's,
  and condition 10 requires them to land together.
- **The lock window is argued, not observed.** No test holds a competing lock. Deliverable D8 is
  routed to human judgment until `tests/schema/test_grant_locks.py` lands in 36-05.

## User Setup Required

None — no external service configuration required. Note for anyone running the app by hand:
`set -a; . ./.env; set +a` before `uv run uvicorn ...`, or `EnvironmentConfig()` fails at boot.

## Next Phase Readiness

Ready. Wave 2's remaining plans can proceed:

- `36-04` extends `consume_quota`'s marked slot and adds `GrantsDB` methods for the usage row; the
  lock order, the session boundary and the error contract are all fixed and proven.
- `36-05` adds `require_quota_send_message` plus `quota_checked=True` on `POST /chats/{chat_id}`.
  Condition 10 will fail boot if either lands alone, which is the intended forcing function. The
  wrapper tuple in `assert_route_enumeration` is the single place to extend.
- `seed_grant` accepts `source`, `status`, `starts_at`, `ends_at`, `monthly_period` and
  `monthly_used`, so 36-04's allowance and rollover cases need no new fixture.
- `docker-compose.yml` and `uv.lock` remain modified and uncommitted per D-15.

---
*Phase: 36-rebind-pre-existing-routes*
*Completed: 2026-08-21*

## Self-Check: PASSED

All claimed artifacts exist on disk (`database/grants.py`, `quota.py`, `tests/e2e/test_quota.py`,
this SUMMARY) and all four claimed commits (`67f0511`, `096ac3a`, `fe07be1`, `217c7a9`) resolve in
`git log`.
