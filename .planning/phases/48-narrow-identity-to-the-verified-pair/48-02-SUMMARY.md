---
phase: 48-narrow-identity-to-the-verified-pair
plan: 02
subsystem: testing
tags: [pytest, fastapi, crud, refactor]

# Dependency graph
requires:
  - phase: 48-01
    provides: IdentitiesDB.resolve(*, issuer, subject) -> LinkedIdentity | None, with the three rejections copied character for character
provides:
  - the crud suite driving resolve's two-keyword signature, with the three rejections re-run rather than inspected
  - test_resolve_answers_none_when_no_row_exists, the executable form of "no row is None, never a usable value"
  - the admission fixture in the handler suite calling resolve with two keywords
affects: [48-08, 49-delete-the-single-implementation-auth-protocols]

actuals:
  tokens: 9709
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A crud read that can legitimately find nothing is pinned by a case asserting `None`, not by a case asserting a rejection"

key-files:
  created: []
  modified:
    - tests/unit/test_identities_crud.py
    - tests/unit/test_exception_handlers.py

key-decisions:
  - "Task 1 acceptance criterion 3 (no `PreAuthIdentityNotAllowed` anywhere in the crud suite) contradicts the same task's action (the rejection cases keep every assertion); the action won and the criterion is recorded failed with its measurement"
  - "`test_the_admitted_identity_carries_the_verified_pair` is deleted: it read `identity.issuer` and `identity.subject` off a `LinkedIdentity`, and D-02 removed both fields. The plan named neither the case nor the deletion"

patterns-established:
  - "A test that names a deleted parameter in its docstring loses the docstring, not only the argument (D-10)"

requirements-completed: []

coverage:
  - id: D1
    description: "resolve answers None when the joined query returns no row"
    verification:
      - kind: unit
        ref: "tests/unit/test_identities_crud.py#TestOutcomeOneNoMatchingRow::test_resolve_answers_none_when_no_row_exists"
        status: pass
    human_judgment: false
  - id: D2
    description: "resolve answers a LinkedIdentity holding both rows when the row is active and its user is active"
    verification:
      - kind: unit
        ref: "tests/unit/test_identities_crud.py#TestOutcomeFourLinkedAndActive::test_it_admits_with_the_resolved_rows"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identities_crud.py#TestOutcomeFourLinkedAndActive::test_the_classifier_is_the_stored_provider_column"
        status: pass
    human_judgment: false
  - id: D3
    description: "An identity row with no user raises IdentityUnresolvable; a non-active row raises HistoricalIdentity; a non-active user raises BlockedUser — all three re-run against the new signature"
    verification:
      - kind: unit
        ref: "tests/unit/test_identities_crud.py#TestUnresolvableUser"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identities_crud.py#TestOutcomeTwoIdentityStateIsNotExactlyActive"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identities_crud.py#TestOutcomeThreeUserIsNotExactlyTrue"
        status: pass
    human_judgment: false
  - id: D4
    description: "No test in either file passes the deleted flag or asserts a None row field"
    verification:
      - kind: other
        ref: "grep -n 'allow_preauth\\|preauth_callable' tests/unit/test_identities_crud.py tests/unit/test_exception_handlers.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "The handler suite still answers 403 account_unavailable on both admission arms and logs one record each, driven through the real resolution"
    verification:
      - kind: unit
        ref: "tests/unit/test_exception_handlers.py#TestAnAccountUnavailableArmTravelsTheWholeErrorPath"
        status: pass
    human_judgment: false

duration: 3 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 02: The crud and handler suites follow resolve's two-keyword signature Summary

**`IdentitiesDB.resolve`'s three rejections are re-run rather than inspected, and its new `None` answer is pinned by a case: 91 cases pass across the two suites, which reported 42 failures before this plan.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-16T21:53:29Z
- **Completed:** 2026-09-16T21:56:20Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `_resolve`, `_rejected` and `_drive` take the row alone. The `preauth_callable` parametrization is gone from the three cases that carried it, and every assertion in those cases is unchanged.
- `TestOutcomeOneNoMatchingRow` is one case instead of four: `test_resolve_answers_none_when_no_row_exists`. The two cases asserting the unlinked shape and the two expecting `PreAuthIdentityNotAllowed` from `resolve` are deleted — that rejection now belongs to `get_identity`, where `tests/unit/test_identity_accessors.py` pins it.
- The three rejections are **proved**, not copied: 48-01 moved them character for character but re-ran none of them. Wave 1's coverage entry D5 carried `human_judgment: true` for exactly this reason. It is now discharged.
- The admission fixture in the handler suite drives the real `resolve` through the real dependency stack with the two keywords. Both 403 arms, their one-record log assertions and the field-free log line are unchanged and green.

## Task Commits

1. **Task 1: The crud suite calls resolve with two keywords** — `dd9f0b7` (test)
2. **Task 2: The admission fixture drops the deleted argument** — `8eb8a54` (test)

**Plan metadata:** the `docs(48-02)` commit below.

## Files Created/Modified

- `tests/unit/test_identities_crud.py` — the three helpers lose the flag; `TestOutcomeOneNoMatchingRow` becomes the single `None` case; one case reading deleted fields is removed; two docstrings naming a deleted identifier are corrected or dropped
- `tests/unit/test_exception_handlers.py` — the admission fixture's `resolve` call loses its argument; nothing else in the module is touched

## Verification — measured, not copied

Every command below was run in this session, at `8eb8a54` unless a "before" is named.

| Command | Result |
|---|---|
| `.venv/bin/pytest -q tests/unit/test_identities_crud.py` **before** | `37 failed, 2 passed` |
| `.venv/bin/pytest -q tests/unit/test_identities_crud.py` **after** | `35 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_exception_handlers.py` **before** | `5 failed, 51 passed` |
| `.venv/bin/pytest -q tests/unit/test_exception_handlers.py` **after** | `56 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_identities_crud.py tests/unit/test_exception_handlers.py` | `91 passed`, exit 0 |
| `grep -n 'allow_preauth\|preauth_callable'` over both files | no output, exit 1 |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |

**Task 1 acceptance criteria, each re-run:**

| Criterion | Measured | Verdict |
|---|---|---|
| `grep -c 'is None'` prints 1 or more, and the new case is one of them | `1`, and it is line 88 of the new case | PASS |
| `grep -c 'IdentityUnresolvable\|HistoricalIdentity\|BlockedUser'` prints 3 or more | `17` | PASS |
| `grep -n 'PreAuthIdentityNotAllowed'` prints nothing | prints 3 lines: the import at `:16` and two `assert not isinstance` guards at `:108` and `:150` | **FAIL — see deviation 1** |
| `.venv/bin/pytest -q tests/unit/test_identities_crud.py` exits 0 | exit 0 | PASS |

**Task 2 acceptance criteria:** `grep -n 'allow_preauth' tests/unit/test_exception_handlers.py` prints nothing (exit 1) — PASS. The suite exits 0 — PASS.

The full `-m ''` suite was deliberately not run: it stays red until the last wave-2 plan lands.

## Decisions Made

- **The action beats the acceptance criterion where they disagree**, as 48-01 decided for its own criterion-3 grep. Recorded as deviation 1 with the measurement, never resolved silently.
- **A case reading deleted fields is deleted, not rewritten.** `test_the_admitted_identity_carries_the_verified_pair` asserted `(identity.issuer, identity.subject) == (ISSUER, SUBJECT)` on the value `resolve` returns. D-02 removed both fields from `LinkedIdentity`, which is slotted, so the case raised `AttributeError`. Its subject is now `VerifiedClaims`, which `tests/unit/test_jwt_security.py:207-227` already pins — the same reasoning RESEARCH used to resolve its open question 2.
- **`_resolve` keeps returning `(identity, session)`.** The plan writes the new case as `await _resolve(row=None) is None`; five other cases read the session half of that tuple, so the case unpacks instead: `identity, _ = await _resolve(None)` then `assert identity is None`. Same assertion, no helper churn.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 1's acceptance criterion 3 contradicts Task 1's own action**

- **Found during:** Task 1 (running the four acceptance criteria)
- **Issue:** The criterion requires `grep -n 'PreAuthIdentityNotAllowed' tests/unit/test_identities_crud.py` to print nothing. The action requires that "the three rejection cases at `:112-186` keep every assertion", and two of those cases assert exactly that the rejection a row earned is **not** the never-linked one: `test_a_retired_identity_never_surfaces_preauth_identity_not_allowed` (old `:131-132`) and `test_it_is_not_read_as_an_unlinked_pair` (old `:178`). Both sit inside the range the action protects. As written the two instructions cannot both be satisfied.
- **Fix:** No further source change — the criterion is a proxy for "no case expects `resolve` to raise `PreAuthIdentityNotAllowed`", and that claim **is** satisfied: the two cases that expected it are deleted, and the two survivors assert the negative. Keeping them is what the action orders and what T-48-02-02 wants: they are the live guard against the flag's branch being restored ahead of the two state checks. D-11 mandates deleting the unlinked-shape cases and nothing more.
- **Files modified:** none
- **Verification:** the three surviving lines are `:16` (the import both guards need), `:108` and `:150`, each an `assert not isinstance(...)` inside a case the action names; `grep -c 'pytest.raises(PreAuthIdentityNotAllowed'` prints 0
- **Committed in:** n/a — a check correction, carried here rather than silently into the suite

**2. [Rule 3 - Blocking] A case the plan does not name read two fields D-02 deleted**

- **Found during:** Task 1 (first run after the mechanical edit was planned)
- **Issue:** `TestOutcomeFourLinkedAndActive::test_the_admitted_identity_carries_the_verified_pair` (old `:158-160`) reads `identity.issuer` and `identity.subject` off the value `resolve` returns. That value is now a slotted `LinkedIdentity` with `user` and `identity` only, so the case raises `AttributeError`. It lies outside every range the plan's action names, so following the action literally would have left the suite red and the task's own `<verify>` failing.
- **Fix:** Deleted the case. Its subject moved to `VerifiedClaims` and is already pinned by `tests/unit/test_jwt_security.py:207-227`.
- **Files modified:** `tests/unit/test_identities_crud.py`
- **Verification:** `35 passed`, exit 0; the sibling cases asserting the two rows are untouched and green
- **Committed in:** `dd9f0b7`

**3. [Rule 2 - Missing Critical] Two docstrings named the deleted flag or a deleted class (D-10)**

- **Found during:** Task 1
- **Issue:** D-10 forbids a comment whose subject is the `allow_preauth` flag or a deleted identifier. `_resolve`'s docstring said resolution "returns the `AuthIdentity` it resolved" — a class 48-01 deleted from `src/`. `test_it_never_falls_through_to_pre_auth`'s docstring said "Even on the one route that may admit a pre-auth principal", which described the argument the same case was losing.
- **Fix:** `_resolve`'s docstring names `LinkedIdentity` and its `None` answer. The second docstring is deleted; the method name still states the rule.
- **Files modified:** `tests/unit/test_identities_crud.py`
- **Verification:** `grep -n 'AuthIdentity' tests/unit/test_identities_crud.py` prints only the `PreAuthIdentityNotAllowed` lines, never the bare class
- **Committed in:** `dd9f0b7`

---

**Total deviations:** 3 auto-fixed (1 bug, 1 blocking, 1 missing critical).
**Impact on plan:** No scope creep — every edit is inside the two files `files_modified` names. Deviation 2 is the one that mattered: the plan's action was an incomplete inventory of the suite, and the task's own `<verify>` is what caught it.

## Broken-windows ledger

`gsd-tools windows append` still refuses (`Ledger counts disagree with entries`), as 48-01 recorded and as this phase's `deferred-items.md` logs. Per this phase's conventions the entry is carried here instead, and the ledger is not repaired:

- **kind:** deviation — **phase:** 48 — **file:** `.planning/phases/48-narrow-identity-to-the-verified-pair/48-02-PLAN.md` — Task 1 acceptance criterion 3 is unsatisfiable beside Task 1's own action; the action was followed and the criterion measured failed.

## Issues Encountered

None beyond the three deviations above, each found by running a check rather than reading it.

## Carry into the phase gate

- **Criterion 4's grep will print a line that is not a call site.** `grep -rn 'allow_preauth\|preauth_callable' tests` still prints `tests/unit/test_app_wiring.py:65`, which is the **method name** `test_the_preauth_callable_route_still_verifies_the_token` — not an argument. The only real call site left in `tests/` is `tests/schema/test_claim_race.py:251`, owned by a sibling wave-2 plan. Measured at `8eb8a54`. Plan 48-08 should grep for `allow_preauth=` or exclude `def test_`, or it will read a passing tree as failing. This is the same class of error as 48-01's deviation 1.
- Wave 1's coverage entry **D5** (`human_judgment: true`, "the three rejections are re-run against the crud suite only in plan 48-02") is discharged by this plan's D3 above.

## Known Stubs

None. No placeholder, no hardcoded empty value and no TODO was introduced.

## TDD Gate Compliance

Task 1 carries `tdd="true"`. **The RED/GREEN sequence is not present, and could not be.** Both tasks change test files only; the implementation half — `resolve`'s two-keyword signature and its `None` answer — landed in plan 48-01 at `89ede98` and is already green. A `feat(48-02)` commit would have nothing to contain, and a RED commit asserting the new behavior would have passed on arrival, which `references/tdd.md` names as the fail-fast case to investigate rather than commit through.

What was measured instead, and is the honest substitute: the suite's state **before** the edit, `37 failed, 2 passed` (every failure a `TypeError` on the removed keyword or an `AttributeError` on a removed field), and **after**, `35 passed`. The red is real and recorded; it is a red the previous wave created, not one this plan wrote.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to. T-48-02-01 is carried by the three rejection classes above, all passing. T-48-02-02 is carried by `test_resolve_answers_none_when_no_row_exists` plus the two surviving `not isinstance` guards deviation 1 keeps. T-48-02-SC holds: no package was installed and `pyproject.toml` is untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Criterion 2's crud half is proved by a run. Plans 48-03 to 48-07 own the remaining red test files; nothing in this plan blocks them.
- `tests/schema/test_claim_race.py:251` is the last `allow_preauth=` call site in the tree and belongs to a sibling plan.

## Self-Check: PASSED

- `tests/unit/test_identities_crud.py` — FOUND, 35 cases pass
- `tests/unit/test_exception_handlers.py` — FOUND, 56 cases pass
- Commits `dd9f0b7` and `8eb8a54` — both present in `git log --all`
- Every `<acceptance_criteria>` of both tasks re-run above; seven of eight pass, the eighth recorded as deviation 1 with its measurement
- Plan-level `<verification>` re-run above; both lines pass
- Neither commit deletes a tracked file (`git diff --diff-filter=D HEAD~2 HEAD` is empty)

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
