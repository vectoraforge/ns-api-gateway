---
phase: 48-narrow-identity-to-the-verified-pair
plan: 05
subsystem: testing
tags: [pytest, fastapi, refactor, jwt]

# Dependency graph
requires:
  - phase: 48-01
    provides: option B — AuthService.complete resolves the caller itself before the sequence, and create_user takes claims
provides:
  - the four create-user suites driving claims through the route, the service and the crud insert
  - a case pinning the completion path's statement count at exactly one, on the success path and on the earliest rejection
  - the create-user rejection precedence, its order and its codes, re-run rather than inspected
affects: [48-08, 49-delete-the-single-implementation-auth-protocols]

actuals:
  tokens: 14032
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A guard that forbade a query becomes a guard that counts it: the stub records statements instead of raising on them"

key-files:
  created: []
  modified:
    - tests/unit/test_create_user_precedence.py
    - tests/unit/test_create_user_body.py
    - tests/unit/test_create_user_rollback.py
    - tests/unit/test_conflict_classification.py

key-decisions:
  - "The deleted `_StubSession.exec` guard is replaced by two cases counting statements, not by one: the success path is the longest path and the earliest rejection is the shortest, so a second query added anywhere between them fails"
  - "`test_a_body_handle_is_located_byte_for_byte` asserted zero reads on a non-422 path; option B makes that false, so it counts one read instead — recorded as deviation 1 rather than relaxed"
  - "`_identity()` becomes `_claims()` in both service-level suites: after D-01 the helper answers a `VerifiedClaims`, and the old name states a type the codebase no longer has"

patterns-established:
  - "A refusal that now costs a read is pinned by its exact statement count, never by the absence of one"

requirements-completed: []

coverage:
  - id: D1
    description: "The completion path issues exactly one statement, the identity query option B added"
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheCompletionPathIssuesOneStatement::test_the_whole_success_path_issues_exactly_one_statement"
        status: pass
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheCompletionPathIssuesOneStatement::test_a_rejected_presentation_issues_the_same_one_statement"
        status: pass
      - kind: unit
        ref: "tests/unit/test_create_user_body.py#TestTheHandleReachesTheStore::test_a_body_handle_is_located_byte_for_byte"
        status: pass
    human_judgment: false
  - id: D2
    description: "The five challenge rejections keep their status, code, event name and place in the precedence"
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections"
        status: pass
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestThePrecedenceItself"
        status: pass
    human_judgment: false
  - id: D3
    description: "The four provider-stage rejections keep their status, code and stage, and every one of them consumes"
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheProviderStageRejections"
        status: pass
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestEveryProviderStageRejectionConsumes"
        status: pass
    human_judgment: false
  - id: D4
    description: "The 422 validation partition is unchanged: an unusable handle issues nothing, locates nothing and reads nothing"
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_body.py#TestTheValidationPartition"
        status: pass
      - kind: unit
        ref: "tests/unit/test_create_user_body.py#TestTheRejectionHasNoSideEffects"
        status: pass
    human_judgment: false
  - id: D5
    description: "The rollback arms and the SQLSTATE conflict classification are unchanged under `claims=`, including the 409 arm"
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_rollback.py"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheInsertsUniqueViolationIsTheSubjectRace"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms"
        status: pass
    human_judgment: false
  - id: D6
    description: "T-48-05-01: `_reject_existing_identity` keeps all three arms, each asserted by the suite"
    verification:
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms::test_an_active_linked_row_raises_already_linked_and_inserts_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms::test_a_historical_row_raises_account_unavailable"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms::test_an_active_row_whose_user_is_blocked_raises_account_unavailable"
        status: pass
    human_judgment: false
  - id: D7
    description: "T-48-05-03: the handle reaches neither logger"
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections::test_every_rejection_is_recorded_exactly_once_and_never_names_the_handle"
        status: pass
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheTransactionRejectionIsObservedAtTheHandler::test_the_handle_never_reaches_either_log"
        status: pass
    human_judgment: false

# Metrics
duration: 5 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 05: The four create-user suites follow claims Summary

**Option B's one identity statement is now measured rather than forbidden: 80 cases pass across the four create-user suites, which all four failed at import before this plan, and not one rejection, status, code or place in the precedence moved.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-16T22:11:50Z
- **Completed:** 2026-09-16T22:16:42Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- `_StubSession.exec` in the precedence suite was a guard that raised on any query, because before this phase the completion path issued none. Option B gives it exactly one. The guard is not relaxed — it is replaced by a stronger, two-sided one: `TestTheCompletionPathIssuesOneStatement` counts the statements on the **longest** path (the full success, through the provider read and the consuming transaction) and on the **shortest** (an unknown handle, rejected before the sequence begins). Both are exactly one, so a second query added anywhere between them still fails.
- All four suites build a `VerifiedClaims`. The two route-driven suites override `get_claims`, which is what create-user declares after D-07; the two service-driven suites call `service.create_user(claims=...)`.
- Every rejection the precedence suite drove before the phase it still drives: the five challenge results, the four provider-stage arms with their stages, the precedence pairs and the transaction-rejection arm. The case counts are unchanged in three files and up by exactly the new class's two cases in the fourth.
- The conflict classification is untouched in substance: the count of every conflict class named in the file is byte-identical to the pre-phase tree, including the 409 `identity_already_linked` arm on both its paths.

## Task Commits

1. **Task 1: The precedence suite answers the completion path's one statement** — `e6e3f9e` (test)
2. **Task 2: The body suite and the rollback suite take claims** — `915e5f1` (test)
3. **Task 3: The conflict classification suite takes claims** — `b031373` (test)

**Plan metadata:** the `docs(48-05)` commit below.

## Files Created/Modified

- `tests/unit/test_create_user_precedence.py` — `get_claims` replaces the `get_identity` override and the fixture is a `VerifiedClaims`; `_StubSession` gains a `statements` list and an `_EmptyResult`, answering the caller with no row every case here uses; `TestTheCompletionPathIssuesOneStatement` is new
- `tests/unit/test_create_user_body.py` — the same two edits; `_RecordingChallengeStore.issue` follows `ChallengesDB.issue`'s `claims` and `linked`; the located-handle case counts one read where it asserted none (deviation 1)
- `tests/unit/test_create_user_rollback.py` — `_identity()` becomes `_claims()`; `create_user` is called with `claims=`
- `tests/unit/test_conflict_classification.py` — the same two edits; no assertion, parametrization or case changed

## Verification — measured, not copied

Every command below was run in this session, at `b031373` unless a "before" is named.

| Command | Result |
|---|---|
| the four suites together **before** | `ImportError: cannot import name 'AuthIdentity'`, 4 collection errors, exit 2 |
| the four suites together **after** (the plan-level `<verification>`) | `80 passed`, **EXIT=0** |
| `.venv/bin/pytest -q tests/unit/test_create_user_precedence.py` | `29 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_create_user_body.py tests/unit/test_create_user_rollback.py` | `22 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_conflict_classification.py` | `29 passed`, exit 0 |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |
| `test -z "$(grep -n 'get_linked_identity\|\bAuthIdentity\b' tests/unit/test_create_user_precedence.py)"` | exit 0 |
| `grep -n '\bAuthIdentity\b'` over the other three files | no output, exit 1 |
| `grep -c 'dependency_overrides\[get_claims\]' tests/unit/test_create_user_precedence.py` | `1` |
| `grep -c 'claims=' tests/unit/test_create_user_rollback.py` | `1` |

**Acceptance criteria, each re-run:**

| Task | Criterion | Measured | Verdict |
|---|---|---|---|
| 1 | A case asserts the completion path issues exactly one statement | `TestTheCompletionPathIssuesOneStatement`, two cases, both passing | PASS |
| 1 | All five challenge rejections and all four provider-stage rejections still driven | the five results and the three stages all present; `TestEveryProviderStageRejectionConsumes` parametrizes the four | PASS |
| 1 | `grep -c 'dependency_overrides\[get_claims\]'` prints 1 | `1` | PASS |
| 1 | the suite exits 0 | `29 passed`, exit 0 | PASS |
| 2 | `grep -n '\bAuthIdentity\b'` over both files prints nothing | exit 1, no output | PASS |
| 2 | `grep -c 'claims='` on the rollback suite prints 1 or more | `1` | PASS |
| 2 | both suites exit 0 | `22 passed`, exit 0 | PASS |
| 3 | `grep -n '\bAuthIdentity\b'` prints nothing | exit 1, no output | PASS |
| 3 | Every conflict class the suite asserted before the phase is still asserted | the per-class occurrence counts are identical to `937864c` (see below) | PASS |
| 3 | the suite exits 0 | `29 passed`, exit 0 | PASS |

**The case counts, derived rather than asserted.** `git show 937864c:` gives 24, 9, 4 and 22 `def test_` across the four files. Now: 26, 9, 4 and 22. The one difference is Task 1's new class, which the plan required. Collection is 29 in the precedence suite (26 defs, one parametrized over four arms) and 29 in the conflict suite (22 defs, two parametrized).

**The conflict classes, counted rather than eyeballed.** `grep -o` over the seven class names the module asserts prints the same seven counts at `937864c` and at `b031373`: `AccountUnavailable` 5, `BlockedUser` 3, `HistoricalIdentity` 2, `IdentityAlreadyLinked` 5, `IntegrityError` 6, `ProviderAccountAlreadyLinked` 3, `RuntimeError` 2.

The full `-m ''` suite was deliberately not run: it stays red until the last wave-2 plan lands.

## Decisions Made

- **Two counting cases, not one.** The plan asks for "a case asserting the completion path issues exactly one statement". One case can only pin one path. The success path is the longest and the unknown-handle rejection the shortest, so counting both brackets every statement the module can reach, which is what the deleted `raise AssertionError` guard used to do for zero.
- **The counting case drives the success path with `create_user` monkeypatched**, as every case in the module does — the `creator` fixture is a dependency of `client`. The one statement is therefore `complete`'s own `resolve` and nothing else, which is precisely the claim being pinned.
- **`_identity()` becomes `_claims()`** in the rollback and conflict suites. The plan names the line numbers and the new return type but not the name. After D-01 the helper answers a `VerifiedClaims`, and CONTEXT § Specific ideas says to name a value by what the code calls it — the codebase calls it `claims`. The same reasoning 48-03 applied to `preauth_identity` → `claims_for`.
- **`_RecordingChallengeStore.issue` follows the real signature** even though completion never calls it. Its docstring says it is kept so "nothing was issued" stays an assertion with teeth; a fake whose signature has drifted from `ChallengesDB.issue` would give that assertion a second way to pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 2's action keeps an assertion that option B makes false**

- **Found during:** Task 2 (running the task's own `<verify>`)
- **Issue:** The action says the body suite's `_UnlinkedSession` "already answers an empty result, so the completion path's identity query reads as a caller with no row and the 422 partition is unchanged", and that both suites "keep every assertion". Both halves are true as far as they go — the 422 partition **is** unchanged, because the framework refuses those bodies before the handler runs. But the module has one non-422 case: `TestTheHandleReachesTheStore::test_a_body_handle_is_located_byte_for_byte`, which reaches the handler and asserted `session.statements == []`. Under option B the completion path resolves the caller, so that path now issues exactly one statement and the assertion cannot hold. Measured: `1 failed, 17 passed`, the failure being `assert [<Select object>] == []`. The comment above it carried the same error — "The handler resolves no identity of its own: the racy pre-check is gone, not relocated" — which D-10 forbids leaving in place, because it now states the opposite of what the code does.
- **Fix:** The assertion counts the statement instead of forbidding it: `assert len(session.statements) == 1`. That is the same claim Task 1's new class makes, asserted here on the one path this module reaches, so the body suite still fails if a second query is added. The comment is rewritten to one line naming what the count means. No other assertion in the case moved — `store.located`, `store.issued` and `session.rollbacks` are untouched and green.
- **Files modified:** `tests/unit/test_create_user_body.py`
- **Verification:** `22 passed`, exit 0 across the body and rollback suites; the four `TestTheRejectionHasNoSideEffects` arms still assert `session.statements == []` and still pass, because the handler genuinely never runs on a 422
- **Committed in:** `915e5f1`

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** No scope creep — every edit is inside the four files `files_modified` names. The deviation is the third of its kind in this phase (48-01 deviation 1, 48-03 deviation 1, this one): a plan instruction to keep an assertion unchanged, measured against the behaviour a locked decision of the same phase produces, with the behaviour winning and the check corrected.

## Broken-windows ledger

`gsd-tools windows append` still refuses (`Ledger counts disagree with entries`), as 48-01, 48-02 and 48-03 recorded and as this phase's `deferred-items.md` logs. Per this phase's conventions the entry is carried here instead, and the ledger is not repaired:

- **kind:** deviation — **phase:** 48 — **file:** `.planning/phases/48-narrow-identity-to-the-verified-pair/48-05-PLAN.md` — Task 2's action preserves an assertion that option B makes false on the one non-422 path in the module; the assertion was converted from "no statement" to "exactly one statement" and every neighbouring assertion kept.

## Issues Encountered

None beyond the deviation above, which was found by running the task's `<verify>` rather than by reading it.

## Carry into the phase gate

- **D-07's accepted weakening is now covered by a run, not only by argument.** CONTEXT D-07 accepts that a historical row or a blocked user is refused *after* the claim on create-user. `TestTheReResolutionsThreeNoMutationArms` proves all three arms still raise from `_reject_existing_identity` with their pre-phase status and code, and `TestEveryProviderStageRejectionConsumes` proves what that costs the caller. The window itself — one spent challenge — is a wire-level fact that `tests/e2e/test_create_user.py` owns and this plan does not run.
- Two sibling notes still stand and neither is this plan's to close: `tests/e2e/conftest.py:18` blocks every `-m e2e` command until the plan owning `tests/unit/test_jwks_offload.py` lands (48-03 deviation 2), and the plan-level `grep -rln 'LinkedIdentity | None' src` line is unsatisfiable as written (48-01 deviation 1).

## Known Stubs

None. No placeholder, no hardcoded empty value and no TODO was introduced.

## TDD Gate Compliance

Task 1 carries `tdd="true"`. **The RED/GREEN sequence is not present, and could not be**, for the same reason 48-02 and 48-03 recorded: the implementation half — option B's `resolve` call inside `AuthService.complete`, and `create_user`'s `claims` keyword — landed in plan 48-01 at `89ede98` and is already green. A `feat(48-05)` commit would have nothing to contain, and the new statement-counting case would have passed on arrival, which `references/tdd.md` names as the fail-fast case to investigate rather than commit through.

What was measured instead, and is the honest substitute: the four suites **before** the edit — `ImportError: cannot import name 'AuthIdentity' from 'nativespeaker.api.schemas.auth'`, 4 collection errors, exit 2 — and **after** — `80 passed`, exit 0. Deviation 1 is a genuine intra-plan red: `1 failed, 17 passed` on the body suite, failing on the assertion option B invalidated, green after the fix. The red is real and recorded; it is a red the previous wave created.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to.

- **T-48-05-01** (elevation of privilege at `AuthService.create_user`) is carried by the three no-mutation arms above, all passing, plus the two `ProviderAccountAlreadyLinked` cases.
- **T-48-05-02** (spoofing — an unplanned second query on the completion path) is carried by the three statement-count cases across two files. The guard is strictly stronger than the one it replaces: the old `raise AssertionError` fired only if a query was issued at all, and could not have distinguished one from two.
- **T-48-05-03** (a handle in a log) holds: both cases asserting `HANDLE not in repr(rejections.entries)` are kept and pass.
- **T-48-05-SC** holds: no package was installed and `pyproject.toml` is untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Create-user's rejections, their order and their codes are proved by a run, and the one statement option B added is measured on both ends of the path. Nothing in this plan blocks the remaining wave-2 plans.
- Wave 1's coverage entry **D8** (`human_judgment: true`, "every create-user wire outcome is unchanged under option B ... re-run in plan 48-05 and at the phase gate") is discharged here for the unit layer. Its e2e half, `tests/e2e/test_create_user.py:203-256`, is still owned by a sibling plan and is still blocked by the `tests/e2e/conftest.py` import, so it must be re-run at the phase gate.

## Self-Check: PASSED

- `tests/unit/test_create_user_precedence.py` — FOUND, 29 cases pass
- `tests/unit/test_create_user_body.py` and `tests/unit/test_create_user_rollback.py` — FOUND, 22 cases pass together
- `tests/unit/test_conflict_classification.py` — FOUND, 29 cases pass
- Commits `e6e3f9e`, `915e5f1`, `b031373` — all present in `git log --all`
- Every `<acceptance_criteria>` of all three tasks re-run above; all ten pass
- Plan-level `<verification>` re-run above; both lines pass
- No commit of this plan deletes a tracked file (`git diff --diff-filter=D --name-only HEAD~3 HEAD` is empty)
- No file outside this plan's `files_modified` list was edited (`git status --short` shows only the three pre-existing untracked `.planning` directories)

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
