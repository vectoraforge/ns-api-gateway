---
phase: 48-narrow-identity-to-the-verified-pair
plan: 06
subsystem: testing
tags: [pytest, fastapi, dependencies, refactor, jwt]

# Dependency graph
requires:
  - phase: 48-01
    provides: RestoreService.restore taking linked, get_identity as the account dependency, and LinkedIdentity with two required fields
provides:
  - the restore service suite driving `linked=` at all 11 call sites
  - the users route suite overriding `get_identity` and reading `linked.user` and `linked.identity`
  - both probe routes declaring `linked: LinkedIdentity = Depends(get_identity)`
  - a collectable e2e suite: `tests/e2e/conftest.py:18`'s import chain is green again
affects: [48-07, 48-08, 49-delete-the-single-implementation-auth-protocols]

actuals:
  tokens: 21779
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A test fixture is named for the value the handler declares: `linked`, never `identity`"

key-files:
  created: []
  modified:
    - tests/unit/test_restore_proof.py
    - tests/unit/test_users_me.py
    - tests/unit/test_auth_security.py
    - tests/unit/test_jwks_offload.py

key-decisions:
  - "Task 2 was executed and committed before Task 1: the restore suite transitively imports `test_jwks_offload.py`, so Task 1's own `<verify>` cannot collect until Task 2's edit lands"
  - "The users suite's `identity` fixture becomes `linked`, taking the plan's stated discretion, because the handler's own parameter is `linked`"
  - "`_caller()`'s docstring is deleted rather than rewritten: its whole subject was the `identity=None` state D-02 makes unconstructible"

patterns-established:
  - "When a plan's task order contradicts the import graph, the import graph wins and the order is swapped rather than the verify being skipped"

requirements-completed: []

coverage:
  - id: D1
    description: "RestoreService.restore is driven by the renamed parameter at all 11 call sites, with every refusal unchanged"
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'linked=' tests/unit/test_restore_proof.py)\" = \"11\""
        status: pass
    human_judgment: false
  - id: D2
    description: "Every LinkedIdentity in these four files is built with two keywords and carries no token value (D-02)"
    verification:
      - kind: other
        ref: "grep -n 'issuer=' tests/unit/test_restore_proof.py returns only the ExternalIdentity row field"
        status: pass
      - kind: other
        ref: "grep -n 'get_linked_identity|\\bAuthIdentity\\b' over the three Task 2 files"
        status: pass
    human_judgment: false
  - id: D3
    description: "The users route suite overrides get_identity, and the handler's reads of linked.user and linked.identity stay pinned (D-08)"
    verification:
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestTheProfileTakesOneQuery::test_the_read_is_keyed_on_the_barrier_resolved_caller"
        status: pass
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestTheProfileBodyIsClosed"
        status: pass
    human_judgment: false
  - id: D4
    description: "Both probe routes declare the account dependency by its new name, and neither suite's subject moved (D-05)"
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_security.py#test_the_probe_route_declares_the_dependency"
        status: pass
      - kind: unit
        ref: "tests/unit/test_jwks_offload.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "The whole e2e suite collects again, which 48-03 named as this plan's gating effect"
    verification:
      - kind: e2e
        ref: ".venv/bin/pytest -q -m e2e --collect-only tests/e2e"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_challenge_store.py (48-03's unscaffolded re-run)"
        status: pass
    human_judgment: false

# Metrics
duration: 3 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 06: The restore, users route and probe suites follow the rename Summary

**`RestoreService.restore` is driven by `linked` at all 11 call sites and both probe routes declare `get_identity`: 130 unit cases pass across the four suites, and the whole e2e suite collects again — 361 tests, where every `-m e2e` command in this phase failed at `tests/e2e/conftest.py` before this plan.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-16T22:19:51Z
- **Completed:** 2026-09-16T22:22:54Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `_caller()` builds a `LinkedIdentity` from two keywords, and every one of the 11
  `service.restore(...)` call sites passes `linked=`. No proof, store, term or refusal assertion
  moved: the suite's subject is the two store proofs, and all 71 of its cases are the pre-phase cases.
- The users route suite overrides `get_identity` and builds its caller with the two rows alone. Every
  body assertion, the one-statement pin and the user-scoped-read pin (WR-84) are unchanged, and the
  scoped-read case still compares against the caller the barrier resolved.
- Both probe routes declare `linked: LinkedIdentity = Depends(get_identity)`. Neither suite changed
  what it measures: `test_auth_security.py` still measures the wire refusals and the structural
  double declaration, `test_jwks_offload.py` still measures the JWKS fetch off the event loop.
- **The e2e blocker this plan owned is gone.** `tests/e2e/conftest.py:18` imports
  `unit.test_jwks_offload`, whose `:13` imported the deleted `get_linked_identity`; three earlier
  plans in this phase could not collect a single e2e file because of it. The suite now collects 361
  tests at exit 0.

## Task Commits

1. **Task 2: The users route suite and the two probe suites take the new name** — `0469864` (test)
2. **Task 1: The restore suite passes linked at every call site** — `bf7b01b` (test)

The numbers are out of order on purpose; see deviation 1.

**Plan metadata:** the `docs(48-06)` commit below.

## Files Created/Modified

- `tests/unit/test_restore_proof.py` — `_caller()` drops the two token keywords and its docstring; the
  11 `restore(identity=...)` call sites become `restore(linked=...)`
- `tests/unit/test_users_me.py` — imports and overrides `get_identity`; `_linked_identity()` drops the
  two token keywords; the `identity` fixture and `_client_for`'s parameter become `linked`
- `tests/unit/test_auth_security.py` — imports `get_identity` and `LinkedIdentity`; the router-level
  declaration, the probe's parameter and the structural assertion at `:57` all follow the rename
- `tests/unit/test_jwks_offload.py` — the same three edits; nothing about the fetch measurement moved

## Verification — measured, not copied

Every command below was run in this session, at `bf7b01b` unless a "before" is named.

| Command | Result |
|---|---|
| `.venv/bin/pytest -q tests/unit/test_restore_proof.py` **before Task 2** | `ImportError: cannot import name 'get_linked_identity'`, 1 collection error, exit 2 |
| `.venv/bin/pytest -q tests/unit/test_restore_proof.py` **after** | `87 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_users_me.py tests/unit/test_auth_security.py tests/unit/test_jwks_offload.py` | `43 passed`, exit 0 |
| all four files together (the plan-level `<verification>`) | `130 passed`, **EXIT=0** |
| `test "$(grep -c 'linked=' tests/unit/test_restore_proof.py)" = "11"` | exit 0 |
| `grep -n 'issuer=' tests/unit/test_restore_proof.py` | one line, `:624`, the `ExternalIdentity` row field |
| `grep -n 'get_linked_identity\|\bAuthIdentity\b'` over the three Task 2 files | no output, exit 1 |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |
| `.venv/bin/pytest -q -m e2e --collect-only tests/e2e` | `361 tests collected`, exit 0 |
| `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` **unscaffolded** | `32 passed`, exit 0 |

**Acceptance criteria, each re-run:**

| Task | Criterion | Measured | Verdict |
|---|---|---|---|
| 1 | `grep -c 'issuer='` counts no occurrence inside a `LinkedIdentity(` construction | the one match is `identity=ExternalIdentity(... issuer=ISSUER`, a required row field | PASS |
| 1 | All 11 restore call sites pass `linked=` | `grep -c 'linked='` prints `11` | PASS |
| 1 | `.venv/bin/pytest -q tests/unit/test_restore_proof.py` exits 0 | `87 passed`, exit 0 | PASS |
| 2 | `grep -n 'get_linked_identity\|\bAuthIdentity\b'` over the three files prints nothing | exit 1, no output | PASS |
| 2 | the three suites exit 0 | `43 passed`, exit 0 | PASS |

**The case counts, derived rather than asserted.** `git show 937864c:` gives 71, 11, 13 and 6
`def test_` across the four files. Now: 71, 11, 13 and 6. Not one case was added, removed or
relaxed. Collection is 87 in the restore suite and 19, 16 and 8 in the other three, which is the 130
above.

The full `-m ''` suite was deliberately not run: the schema suites stay red until 48-07 lands.

## Decisions Made

- **Task 2 runs and commits first.** Measured, not preferred; see deviation 1.
- **The users suite's fixture is `linked`.** The plan left this to discretion ("the fixture and the
  helper keep their names or take `linked`, whichever reads better against the handler's own
  parameter"). `routers/users.py:19` declares `linked`, so the fixture, `_client_for`'s parameter and
  the three cases that name it now read the same word the handler does. The builder keeps the name
  `_linked_identity`, which states the type it returns. The same reasoning 48-03 applied to
  `claims_for` and 48-05 to `_claims()`.
- **`_caller()`'s docstring is deleted, not rewritten.** Its whole subject was "a user standing
  beside `identity=None` stands in for a state production cannot produce" — a state D-02 removes from
  the type, so the sentence has nothing left to warn about. One line naming the shape replaces it,
  under AGENTS.md § Comments.
- **The two probe suites keep their unused probe parameter.** `_probe(linked: LinkedIdentity = ...)`
  never reads its argument, exactly as `_probe(identity: AuthIdentity = ...)` did not. The parameter
  is the declaration under measurement, not a value; ruff passes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1's `<verify>` cannot collect in the plan's task order**

- **Found during:** Task 1 (running the task's own `<verify>`, first command)
- **Issue:** `.venv/bin/pytest -q tests/unit/test_restore_proof.py` exited 2 on a collection error,
  not on anything Task 1 wrote. The chain is three imports deep and entirely inside this plan's own
  file list: `tests/unit/test_restore_proof.py:52` imports `unit.test_google_play_notifications`,
  whose `:52` imports `unit.test_jwks_offload`, whose `:13` imported the deleted
  `get_linked_identity`. `tests/unit/test_jwks_offload.py` is Task **2**'s file. So Task 1 as
  ordered can be written but can never be verified, and committing it on an unrun verify would have
  been a claim rather than a measurement.
- **Fix:** The task order was swapped, not the verification skipped. Task 2 was executed, its own
  `<verify>` and `<acceptance_criteria>` run green, and committed at `0469864`; Task 1's edit was then
  verified against that tree — `87 passed`, exit 0 — and committed at `bf7b01b`. Each commit is still
  atomic and each carries only its own task's files; only their order on the branch moved.
- **Files modified:** none beyond the two tasks' own files
- **Verification:** the "before Task 2" and "after" rows of the table above, both measured
- **Committed in:** n/a — an ordering correction, recorded rather than taken silently

**2. [Rule 2 - Missing Critical] A docstring stated a state D-02 deletes (D-10)**

- **Found during:** Task 1
- **Issue:** `_caller()`'s docstring read "`resolve` sets the two rows together or neither, so a user
  standing beside `identity=None` stands in for a state production cannot produce". After D-02 both
  fields are required on a slotted, frozen class, so `identity=None` is not a state the type admits
  at all — the sentence describes the deleted four-field class. D-10 forbids leaving a comment whose
  subject is the removed fields.
- **Fix:** Replaced by one line naming what the helper builds: "The shape the barrier hands the
  handler: both rows, resolved together."
- **Files modified:** `tests/unit/test_restore_proof.py`
- **Verification:** `87 passed`, exit 0; `grep -n 'identity=None' tests/unit/test_restore_proof.py`
  prints nothing
- **Committed in:** `bf7b01b`

**3. [Rule 3 - Blocking] Task 2's action names two lines per probe suite where each has four**

- **Found during:** Task 2
- **Issue:** The action names `test_auth_security.py:8, 38` and `test_jwks_offload.py:16, 105` — the
  class import and the probe's parameter. Each file also imports the dependency itself (`:6`, `:13`)
  and declares it at router level (`:35`, `:102`), and `test_auth_security.py:57` asserts
  `declared.count(get_linked_identity) == 2` by the callable. Renaming only the two named lines in
  either file leaves it unimportable, and in the security suite would leave a passing-looking
  assertion counting a name that no longer exists.
- **Fix:** All four sites per file follow the rename, plus the structural assertion at `:57`. Nothing
  else in either module moved. RESEARCH § "Every remaining test site" carries the same two-line
  inventory, so the omission is upstream of the plan, not in it.
- **Files modified:** `tests/unit/test_auth_security.py`, `tests/unit/test_jwks_offload.py`
- **Verification:** `43 passed`, exit 0;
  `test_the_probe_route_declares_the_dependency` still asserts the count is exactly 2, now against
  `get_identity`
- **Committed in:** `0469864`

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing critical).
**Impact on plan:** No scope creep — every edit is inside the four files `files_modified` names, and
no file outside that list was touched in either commit. Deviation 1 is the one that mattered: the
plan's task order and the suite's import graph disagreed, and the import graph is the fact.

## Broken-windows ledger

`gsd-tools windows append` still refuses (`Ledger counts disagree with entries`), as 48-01, 48-02,
48-03 and 48-05 recorded and as this phase's `deferred-items.md` logs. Per this phase's conventions
the entry is carried here instead, and the ledger is not repaired:

- **kind:** deviation — **phase:** 48 — **file:**
  `.planning/phases/48-narrow-identity-to-the-verified-pair/48-06-PLAN.md` — Task 1's `<verify>`
  cannot collect before Task 2's file is edited; the tasks were executed in the reverse of the
  written order and each was verified at its own commit.

## Issues Encountered

None beyond the three deviations above, each found by running a check rather than reading it.

## Carry into the phase gate

- **48-03's carried item is discharged here, by a run.** Its coverage entry D5 carried
  `human_judgment: true` because `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py`
  could only be measured behind a temporary scaffold. Re-run unscaffolded at `bf7b01b`: `32 passed`,
  exit 0. The whole e2e directory now collects — 361 tests — so every `-m e2e` command in this phase
  is runnable again. 48-01's coverage entry D8 (`tests/e2e/test_create_user.py`) is now reachable too
  and should be run at the gate.
- Two sibling notes still stand and neither is this plan's to close: 48-01 deviation 1 (the
  plan-level `grep -rln 'LinkedIdentity | None' src` line is unsatisfiable as written, because D-03
  mandates the third occurrence as `resolve`'s return type) and 48-02's note that
  `grep -rn 'allow_preauth\|preauth_callable' tests` prints a method name rather than a call site.
- `tests/schema/test_claim_race.py:251` and `tests/schema/test_restore_race.py:220-222` are the last
  red sites in the tree and belong to plan 48-07.

## Known Stubs

None. No placeholder, no hardcoded empty value and no TODO was introduced.

## TDD Gate Compliance

Neither task carries `tdd="true"`, so no RED/GREEN sequence applies. Both commits are `test(48-06)`,
which is the right type: both tasks change test files only. The implementation half — `restore`'s
`linked` parameter and the `get_identity` rename — landed in plan 48-01 and is already green.

The red these commits close is real and was measured, not assumed:
`.venv/bin/pytest -q tests/unit/test_restore_proof.py` before Task 2 answered
`ImportError: cannot import name 'get_linked_identity' from 'nativespeaker.api.app.dependencies'`,
exit 2. It is a red the previous wave created.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to.

- **T-48-06-01** (elevation of privilege at `services/restore.py::restore`) is carried by all 11 call
  sites re-run green, with `linked.user.id` still the destination — the entitlement-destination
  assertions in `TestTheAttributionTokenNamesTheBinding` and the adoption cases are unchanged.
- **T-48-06-02** (information disclosure at `GET /users/me`) is carried by
  `test_the_read_is_keyed_on_the_barrier_resolved_caller`, which still binds the statement to the
  caller the barrier resolved, plus the two secrecy cases on the 500 arm.
- **T-48-06-03** (denial of service at the JWKS fetch) holds: only the probe route's declaration was
  renamed, and all 8 offload cases pass, including the heartbeat measurement.
- **T-48-06-SC** holds: no package was installed and `pyproject.toml` is untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The four suites are green and the e2e directory is collectable again, which unblocks every `-m e2e`
  verification in the rest of this phase. Nothing in this plan blocks 48-07 or 48-08.
- 48-07 owns the two remaining red files, both under `tests/schema/`. After it lands the full
  `-m ''`, `-m e2e` and `-m schema` runs become meaningful for the first time since 48-01.

## Self-Check: PASSED

- `tests/unit/test_restore_proof.py` — FOUND, 87 cases pass
- `tests/unit/test_users_me.py`, `tests/unit/test_auth_security.py`,
  `tests/unit/test_jwks_offload.py` — FOUND, 43 cases pass together
- Commits `0469864` and `bf7b01b` — both present in `git log --all`; the metadata commit is `e799d37`
- Every `<acceptance_criteria>` of both tasks re-run above; all five pass
- Plan-level `<verification>` re-run above; it passes at exit 0
- Neither commit deletes a tracked file (`git diff --diff-filter=D --name-only HEAD~2 HEAD` is empty)
- No file outside this plan's `files_modified` list was edited (`git diff --name-only HEAD~2 HEAD`
  lists exactly the four; `git status --short` shows only the three pre-existing untracked
  `.planning` directories)

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
