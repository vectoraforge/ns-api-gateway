---
phase: 48-narrow-identity-to-the-verified-pair
plan: 07
subsystem: testing
tags: [pytest, postgres, race, refactor, jwt]

# Dependency graph
requires:
  - phase: 48-01
    provides: IdentitiesDB.resolve's two-keyword signature, AuthService.complete taking claims, both claim completions taking claims and linked, and LinkedIdentity with two required fields
provides:
  - the four schema race suites driving the two types against a live database
  - identity_of in tests/schema/test_restore_race.py answering a LinkedIdentity that carries both rows
  - a schema suite that collects and passes at its pre-phase count of 297
  - a tree that collects end to end again: 2573 tests, no file red at import
affects: [48-08, 49-delete-the-single-implementation-auth-protocols]

actuals:
  tokens: 27064
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A race suite follows a type change in its plumbing alone: no assertion line moves, because the suite measures the database"

key-files:
  created: []
  modified:
    - tests/schema/test_claim_race.py
    - tests/schema/test_create_atomicity.py
    - tests/schema/test_create_race.py
    - tests/schema/test_restore_race.py

key-decisions:
  - "Both claim completions needed `claims=` and `linked=`, which Task 1's action does not name; the action's inventory was incomplete and the service signature is the fact"
  - "`identity_for` becomes `claims_for` and the create-race attempt field becomes `claims`, as 48-03, 48-05 and 48-06 each renamed a helper whose name stated a deleted type"
  - "`identity_of` keeps its name: tests/schema/test_grant_locks.py imports it, and that file is outside this plan's scope"
  - "The restore race builder invents its identity row rather than mirroring a seeded one, because this module seeds no external_identities row at all"

patterns-established:
  - "A test helper imported by a file outside the plan's scope keeps its name; only its return type follows the rename"

requirements-completed: []

coverage:
  - id: D1
    description: "The claim race resolves with two keywords and drives both claim completions with claims and linked, and each race still commits exactly one grant row"
    verification:
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_exactly_one_grant_row_exists_on_the_anonymous_tier"
        status: pass
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousRegisteredClaimsAllocateOnce::test_exactly_one_grant_row_exists_on_the_registered_tier"
        status: pass
    human_judgment: false
  - id: D2
    description: "Both create suites drive AuthService.complete with claims, and the create race still yields exactly one account"
    verification:
      - kind: integration
        ref: "tests/schema/test_create_race.py"
        status: pass
      - kind: integration
        ref: "tests/schema/test_create_atomicity.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "The restore race builder carries both rows, and the raced restore still commits exactly one grant"
    verification:
      - kind: integration
        ref: "tests/schema/test_restore_race.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-03: no schema test passes the deleted flag"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn 'allow_preauth' tests/schema)\""
        status: pass
    human_judgment: false
  - id: D5
    description: "D-11: every schema test builds a VerifiedClaims or a LinkedIdentity"
    verification:
      - kind: other
        ref: "grep -rn '\\bAuthIdentity\\b' src tests"
        status: pass
    human_judgment: false
  - id: D6
    description: "The two schema files this plan does not own, which fail at import only through these four, are green again"
    verification:
      - kind: integration
        ref: ".venv/bin/pytest -q -m schema tests/schema (297 passed)"
        status: pass
    human_judgment: false

# Metrics
duration: 5 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 07: The four schema race suites take the two types Summary

**The last red files in the tree are green: 89 cases pass across the four race suites against live
PostgreSQL, the whole schema suite is back at its pre-phase 297, and the tree collects end to end
again — 2573 tests, where five schema files failed at import before this plan.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-16T22:26:36Z
- **Completed:** 2026-09-16T22:31:37Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `resolve_identity` in the claim race calls `resolve` with two keywords, and the attempt reads
  `linked.user` and `linked.identity`. Both claim completions now take `claims=` **and** `linked=`,
  which the plan's action does not name and 48-01's signatures require (deviation 1).
- Both create suites build a `VerifiedClaims` and drive `AuthService.complete(claims=...)`. The
  create-race attempt record carries `claims`, and `identity_for` becomes `claims_for`.
- `identity_of` answers a `LinkedIdentity` carrying both rows. The plan expected a seeded row to
  mirror; this module seeds none, so the row is built from the field set of
  `tests/unit/conftest.py:115-126` (deviation 2).
- **Not one assertion line moved in any of the four files.** Measured: the diff over `tests/schema/`
  contains no added or removed line matching `assert`. The `def test_` counts are 30, 12, 13 and 34,
  identical to `937864c`. These suites measure the database, and the database is what they still
  measure.
- **Two schema files this plan does not own were red through these four and are green again.**
  `tests/schema/test_registration_pairing.py` imports `run_creation` from the create-atomicity
  suite, and `tests/schema/test_grant_locks.py` imports `identity_of` from the restore race. Neither
  needed an edit: `test_grant_locks.py:1039` passes the caller positionally, which the renamed
  parameter still accepts.

## Task Commits

1. **Task 1: The claim race and the two create suites take the two types** — `a426b87` (test)
2. **Task 2: The restore race builder carries both rows** — `9b69769` (test)

**Plan metadata:** the `docs(48-07)` commit below.

## Files Created/Modified

- `tests/schema/test_claim_race.py` — imports `VerifiedClaims`; `resolve` loses the flag; the caller
  is `linked`; both completions take `claims=` and `linked=`; one docstring naming the deleted
  `get_linked_identity` follows the rename (D-10)
- `tests/schema/test_create_atomicity.py` — `identity_for` becomes `claims_for` answering a
  `VerifiedClaims`; `run_creation`'s keyword parameter is `claims`; `complete(claims=...)`
- `tests/schema/test_create_race.py` — the attempt record's field is `claims: VerifiedClaims`;
  `prepare_attempt` builds it; `complete(claims=attempt.claims, ...)`
- `tests/schema/test_restore_race.py` — `identity_of` answers a `LinkedIdentity` holding a `User`
  and an `ExternalIdentity`; three table names are imported for that row

## Verification — measured, not copied

Every command below was run in this session, at `9b69769` unless a "before" is named.

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -m schema --collect-only tests/schema` **before** | `189 tests collected, 5 errors`, exit 2 — `ImportError: cannot import name 'AuthIdentity'` |
| the three Task 1 suites, `-m schema` | `55 passed`, exit 0 |
| `tests/schema/test_restore_race.py`, `-m schema` | `34 passed`, exit 0 |
| all four together (the plan-level `<verification>`) | `89 passed`, **EXIT=0** |
| `.venv/bin/pytest -q -m schema tests/schema` | `297 passed`, exit 0 — the RESEARCH baseline figure at `937864c` |
| `test -z "$(grep -rn 'allow_preauth' tests/schema)"` | exit 0 |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |
| `grep -rn '\bAuthIdentity\b' src tests` | no output, exit 1 |
| `grep -rn 'allow_preauth' src tests` | no output, exit 1 |
| `grep -rn 'get_linked_identity' src tests` | no output, exit 1 |
| `.venv/bin/pytest -q -m '' --collect-only` | `2573 tests collected`, exit 0 |

**Acceptance criteria, each re-run:**

| Task | Criterion | Measured | Verdict |
|---|---|---|---|
| 1 | `grep -rn '\bAuthIdentity\b'` over the three files prints nothing | exit 1, no output | PASS |
| 1 | The run collects more than 0 cases and exits 0 | 55 collected, `55 passed`, exit 0 | PASS |
| 1 | Every race case still asserts exactly one committed row | the four one-row cases pass, and the diff changes no `assert` line | PASS |
| 2 | `grep -n '\bAuthIdentity\b' tests/schema/test_restore_race.py` prints nothing | exit 1, no output | PASS |
| 2 | The builder passes both `user=` and `identity=` | lines 230 and 231 | PASS |
| 2 | The run collects more than 0 cases and exits 0 | 34 collected, `34 passed`, exit 0 | PASS |

**The case counts, derived rather than asserted.** `git show 937864c:` gives 30, 12, 13 and 34
`def test_` across the four files. Now: 30, 12, 13 and 34. Not one case was added, removed or
relaxed.

**The tree-wide collection, for the plan that closes wave 2.** 2573 tests collect at exit 0 against
2580 at `937864c`. The seven-case difference is the net of the deletions and additions plans 48-01
to 48-05 each recorded in their own SUMMARY; none of it is this plan's, whose four files hold their
pre-phase counts exactly. The full `-m ''` run is the phase gate's, not this plan's, and was not run
here.

## Decisions Made

- **`identity_for` becomes `claims_for`, and the create-race attempt field becomes `claims`.** The
  plan keeps both names. After D-01 the value is a `VerifiedClaims`, and the codebase calls it
  `claims`: `AuthService.complete` takes `claims=`, so `complete(identity=identity_for(...))` would
  name one value two ways in one line. The same reasoning 48-03 applied to `preauth_identity`,
  48-05 to `_identity()` and 48-06 to the users suite's fixture. `run_creation`'s keyword parameter
  follows; measured first that no caller passes it — the three in-module callers and
  `tests/schema/test_registration_pairing.py:116` all omit it.
- **`identity_of` keeps its name.** `tests/schema/test_grant_locks.py:43` imports it, and that file
  is outside this plan's `files_modified`. Renaming it would have required an edit the scope
  boundary forbids. Only its return type moved.
- **The restore race builder's identity row is invented, not mirrored.** See deviation 2.
- **The `ExternalIdentity` is `google` with a `provider_uid`.** `tests/unit/conftest.py:115-126` is
  the field set the plan names, and the table's CHECK allows a NULL `provider_uid` for `anonymous`
  alone. The row is never persisted and never read — `services/restore.py:59` reads `linked.user.id`
  and nothing else — so the values state a consistent row rather than a load-bearing one.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1's action does not name the two completion call sites it breaks**

- **Found during:** Task 1
- **Issue:** The action names `test_claim_race.py:246-251` (the `resolve` call) and `:261-262` (the
  two reads). It does not name `:269-272`, where `run_attempt` calls
  `completion(identity=identity, ...)`. 48-01 gave `complete_claim_anonymous_grant` and
  `complete_claim_registered_grant` keyword-only `claims` and `linked` parameters, so that call
  raises `TypeError` on an unexpected keyword and the whole suite is red however correctly the two
  named sites are edited. RESEARCH § "Every remaining test site" carries the same two-line
  inventory for this file, so the omission is upstream of the plan.
- **Fix:** `run_attempt` builds a `VerifiedClaims` from `harness.issuer` and the attempt's subject —
  the same two values the seeded identity row carries, so the grant writer records what this
  request proved (D-08) — and passes `claims=` and `linked=`. Nothing else in the function moved.
- **Files modified:** `tests/schema/test_claim_race.py`
- **Verification:** `30 passed` on the claim race alone, `55 passed` with the two create suites; the
  four one-row assertions are untouched and green
- **Committed in:** `a426b87`

**2. [Rule 1 - Bug] The restore race has no seeded identity row for the builder to mirror**

- **Found during:** Task 2
- **Issue:** The action says "The seeded row for that user is what the builder must mirror, so read
  the seeding helper in this module before choosing `provider` and `provider_uid`." Measured:
  `grep -n 'external_identities\|ExternalIdentity' tests/schema/test_restore_race.py` printed
  nothing before this plan. `commit_account` inserts a `core.users` row and stops; this file's
  restore path never resolves an identity, and `clean_up` deletes no identity row. There is no
  seeded row, so there is nothing to mirror and no fact to read.
- **Fix:** The row is built from the field set the plan's other instruction names —
  `tests/unit/conftest.py:115-126` — with `user_id` set to the account's id, the issuer the deleted
  builder already used, and the subject it already used. One inline comment states that the row is
  built here because the file seeds none. No row is inserted, so teardown is unchanged.
- **Files modified:** `tests/schema/test_restore_race.py`
- **Verification:** `34 passed`, exit 0; `tests/schema/test_grant_locks.py`, which imports this
  builder, passes inside the 297 of the whole schema suite
- **Committed in:** `9b69769`

**3. [Rule 2 - Missing Critical] A docstring named a deleted dependency (D-10)**

- **Found during:** Task 1
- **Issue:** `commit_issued_challenge`'s docstring read "both claim routes depend on
  `get_linked_identity`" — a name 48-01 deleted. D-10 forbids leaving a comment whose subject is a
  removed identifier.
- **Fix:** The name follows the rename to `get_identity`, which is what both claim routes declare
  today (48-01, D-08's table). The sentence is still true and the docstring is still three lines.
- **Files modified:** `tests/schema/test_claim_race.py`
- **Verification:** `grep -rn 'get_linked_identity' src tests` prints nothing, exit 1
- **Committed in:** `a426b87`

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 bug, 1 missing critical).
**Impact on plan:** No scope creep — every edit is inside the four files `files_modified` names, and
`git diff --name-only a426b87~1..HEAD` lists exactly those four. Deviation 1 is the one that
mattered: the plan's action was an incomplete inventory of one function, and the service's own
signature is what caught it. Deviation 2 is the second of its kind this phase: a plan instruction
resting on a fact the working tree does not hold, measured against the tree rather than assumed.

## Broken-windows ledger

`gsd-tools windows append` still refuses (`Ledger counts disagree with entries`), as 48-01, 48-02,
48-03, 48-05 and 48-06 recorded and as this phase's `deferred-items.md` logs. Per this phase's
conventions the entries are carried here instead, and the ledger is not repaired:

- **kind:** deviation — **phase:** 48 — **file:**
  `.planning/phases/48-narrow-identity-to-the-verified-pair/48-07-PLAN.md` — Task 1's action omits
  the two completion call sites at `tests/schema/test_claim_race.py:269-272`, which 48-01's
  keyword-only signatures break; both were given `claims=` and `linked=`.
- **kind:** deviation — **phase:** 48 — **file:**
  `.planning/phases/48-narrow-identity-to-the-verified-pair/48-07-PLAN.md` — Task 2's action tells
  the builder to mirror a seeded row; `tests/schema/test_restore_race.py` seeds no identity row, so
  the row was built from the field set the same action names.

## Issues Encountered

None beyond the three deviations above, each found by running a check rather than by reading it.

## Carry into the phase gate

- **Wave 2 is complete and the tree collects.** `-m schema` is back at 297, the figure RESEARCH
  measured at `937864c`, and `-m '' --collect-only` exits 0 at 2573 tests. The three full-suite
  commands are meaningful for the first time since 48-01, and 48-08 should run them.
- **48-02's carried note is now closed by a measurement.** `grep -rn 'allow_preauth\|preauth_callable'
  tests` prints exactly one line, `tests/unit/test_app_wiring.py:65`, which is the **method name**
  `test_the_preauth_callable_route_still_verifies_the_token` and not a call site. The last real call
  site, `tests/schema/test_claim_race.py:251`, is gone. Criterion 4's gate command must therefore
  grep for `allow_preauth=` or exclude `def test_`, or it will read a passing tree as failing.
- **48-01's deviation 1 still stands** and is not this plan's to close: the plan-level
  `grep -rln 'LinkedIdentity | None' src` line is unsatisfiable as written, because D-03 mandates
  `resolve`'s return type as a third occurrence. Measure the parameter form.
- **48-01's coverage entry D8** (`tests/e2e/test_create_user.py`, every create-user wire outcome
  under option B) is still open at the e2e layer and is now reachable: 48-06 restored e2e
  collection. It belongs to the gate.

## Known Stubs

None. No placeholder, no hardcoded empty value and no TODO was introduced.

## TDD Gate Compliance

Neither task carries `tdd="true"`, so no RED/GREEN sequence applies. Both commits are `test(48-07)`,
which is the right type: both tasks change test files only. The implementation half — `resolve`'s
two-keyword signature, `complete`'s `claims` parameter, both claim completions' two parameters and
`LinkedIdentity`'s two required fields — landed in plan 48-01 and is already green.

The red these commits close is real and was measured, not assumed:
`.venv/bin/pytest -q -m schema --collect-only tests/schema` before Task 1 answered
`ImportError: cannot import name 'AuthIdentity' from 'nativespeaker.api.schemas.auth'` over five
files, exit 2. It is a red the previous wave created.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to.

- **T-48-07-01** (tampering — a type change that loosened a lock) is carried by the four one-row
  assertions, each passing: one grant row on the anonymous tier, one on the registered tier, one
  account from two concurrent creates, and one winner in the raced restore. None of those assertion
  lines was edited.
- **T-48-07-02** (elevation of privilege at `resolve` inside a transaction) is carried by
  `test_neither_attempt_handed_the_service_a_row_of_its_own_session`, which reads both rows off the
  value `resolve` returned — a value that can no longer be absent on the admitted path.
- **T-48-07-SC** holds: no package was installed and `pyproject.toml` is untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The four schema race suites run against a live database and commit exactly what they committed
  before the phase. Wave 2 is finished; nothing in this plan blocks 48-08.
- The whole tree imports again. `-m ''`, `-m e2e` and `-m schema` are all runnable, which is the
  precondition 48-08's criterion 5 needs. RESEARCH's pitfall 6 still applies: the pre-existing
  failure in `tests/e2e/test_restore_subscription.py` is not this phase's, and criterion 5 is met
  when the failure set is exactly that one case.

## Self-Check: PASSED

- `tests/schema/test_claim_race.py` — FOUND, 30 cases pass
- `tests/schema/test_create_atomicity.py` and `tests/schema/test_create_race.py` — FOUND, 25 cases
  pass together with the claim race
- `tests/schema/test_restore_race.py` — FOUND, 34 cases pass
- Commits `a426b87` and `9b69769` — both present in `git log --all`
- Every `<acceptance_criteria>` of both tasks re-run above; all six pass
- Plan-level `<verification>` re-run above; both lines pass
- Neither commit deletes a tracked file (`git diff --diff-filter=D --name-only HEAD~2 HEAD` is empty)
- No file outside this plan's `files_modified` list was edited (`git diff --name-only a426b87~1..HEAD`
  lists exactly the four; `git status --short` shows only the three pre-existing untracked
  `.planning` directories)

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
