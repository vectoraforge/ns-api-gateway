---
phase: 45-post-auth-restore-subscription
plan: 07
subsystem: auth
tags: [restore, entitlements, app-store, google-play, access-grants, postgres]

requires:
  - phase: 45-04
    provides: "RestoreService.restore, its four branches and the write_subscription_grant call"
  - phase: 45-06
    provides: "the bounded restore_proof and the escaped Play URL this plan's cases ride on"
provides:
  - "A term check before any write: an absent or already-past term refuses the restore"
  - "One binding for the grant's end, so the checked term and the written term cannot drift"
  - "Eight e2e cases covering the stored-status/proof-term mismatch the phase never had"
affects: [45-09, restore, entitlements, verification]

actuals:
  tokens: 4139
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A value crossing a trust boundary is bound once, checked, then passed by that name"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/services/restore.py
    - tests/e2e/test_restore_subscription.py

key-decisions:
  - "The new refusal reuses RestoreSubscriptionNotEntitled rather than a leaf of its own, so the restore_not_found family answers one body for three causes"
  - "`<=` and not `<`: a term ending exactly at the captured instant is over"
  - "`is None` and not a falsy test: a datetime is never falsy, and the absent term is the whole first combination"
  - "The stale-term case seeds a live grant first, so `frees no slot` is measured against a slot that was really occupied"
  - "The class holding the family keeps its name while its docstring is corrected to three arms"

patterns-established:
  - "A falsification experiment proves a byte-equality case: raise a distinct leaf, observe red, revert"

requirements-completed: [RESTORE-01]

coverage:
  - id: D1
    description: "A stored grace_period row plus an Apple proof answers 404 and writes no grant; no grant of the account carries ends_at NULL"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_a_stored_grace_row_and_an_apple_proof_attaches_nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "An active proof carrying no expiry at all refuses rather than writing an unbounded grant"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_an_active_proof_carrying_no_expiry_attaches_nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "A stale proof against an active stored row refuses and leaves the account's live grant in its slot"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_a_stale_proof_against_an_active_row_attaches_nothing_and_frees_no_slot"
        status: pass
    human_judgment: false
  - id: D4
    description: "The boundary is closed: a term ending at the captured instant refuses, a term still open attaches with that exact end"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_a_term_ending_at_the_captured_instant_is_not_open"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_an_open_term_still_attaches_the_grant_control"
        status: pass
    human_judgment: false
  - id: D5
    description: "A stored grace row plus a Play proof in GRACE_STATE still attaches, with the grace window as the grant's end"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_a_stored_grace_row_and_a_play_proof_carrying_its_window_still_attaches"
        status: pass
    human_judgment: false
  - id: D6
    description: "The three arms of the restore_not_found family answer identical response bytes, so the new refusal is no oracle"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTwoRefusalsOfTheRestoreNotFoundFamily::test_the_three_arms_of_the_family_answer_the_same_bytes"
        status: pass
    human_judgment: false
  - id: D7
    description: "A repeat of a proof whose term has passed is refused and leaves the account's grant id list and usage counter unchanged"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTwoRefusalsOfTheRestoreNotFoundFamily::test_a_repeat_of_a_proof_whose_term_has_passed_is_refused_and_changes_nothing"
        status: pass
    human_judgment: false
  - id: D8
    description: "Truth 2's ordering guarantee and the surface gate are undisturbed: the store call still runs before the session's first statement"
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_restore_proof.py -q (39 passed)"
        status: pass
      - kind: e2e
        ref: "uv run pytest -m e2e -q (333 passed)"
        status: pass
    human_judgment: false

duration: 11 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 07: The proof's term must support the stored row's status Summary

**One check before any write reconciles the status the stored row decides with the term the client's proof carries, so a restore can no longer mint a grant with no end or an end already past.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-09-08T21:06:00Z
- **Completed:** 2026-09-08T21:17:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `services/restore.py` binds the term once, immediately after the entitled check and before the
  attribution read, and refuses when that term is absent or already past. The refusal is
  `RestoreSubscriptionNotEntitled`, so it joins the existing family instead of adding a leaf.
- The `write_subscription_grant` call now passes that same binding as `ends_at`. The expression
  existed in one place before and exists in one place after, so the checked term and the written
  term cannot drift apart.
- Eight e2e cases, six of them refusals and two of them controls, plus a second control on the
  other store. The phase's 1250+325+229 passing suite had none of them.

## Task Commits

1. **Task 1 (tracer, TDD): the proof's own term must support the status the stored row claims**
   - `b1e5559` (test — RED)
   - `25e56cf` (feat — GREEN)
2. **Task 2 (TDD): the refused arms stay one answer, and a dead term cannot be replayed** -
   `18913be` (test)

**Plan metadata:** see the `docs(45-07)` commit that follows this file.

## Files Created/Modified

- `src/nativespeaker/api/services/restore.py` - one local `term_ends_at` binding, one two-clause
  raise, and the `ends_at` argument that now names that binding. No new function, no new class, no
  new error leaf, no signature change. Twelve lines changed.
- `tests/e2e/test_restore_subscription.py` - `_proof` gains an `expires_at` keyword;
  `TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach` with six cases; two cases added
  to `TestTheTwoRefusalsOfTheRestoreNotFoundFamily` and its docstring corrected to three arms.

## Measured, not reasoned about

**The pre-fix defect was observed, not inferred.** The cases were written first and run against the
unchanged source. All four refusal cases came back **200** where they now answer 404. A throwaway
probe drove the stored-`grace_period`-plus-Apple-proof combination against that same unchanged
source and printed what it had committed:

```
OBSERVED status=200 ends_at=[None] status_of=[<AccessGrantStatus.active: 'active'>]
```

That is the VERIFICATION report's truth 1 exactly: an **active** paid grant with **`ends_at` NULL**,
which `crud/grants.py::_effective_grants_statement` reads as effective forever. The probe was
deleted before the RED commit.

Both controls **already passed against the unchanged source**, so the four refusals do not pass
because the write path stopped working.

**The one-body property was falsified before it was trusted.** The new refusal was temporarily
given a leaf of its own and both Task 2 cases were run:

- With a code outside the error registry, `ErrorResponse`'s `Literal` refused to serialise it at
  all — the contract will not carry a new restore code without a registry change.
- With `code = "not_found"` (a code the registry does carry), both cases went red on the **response
  bytes** with the status still 404:
  `assert (404, b'{"cod..._not_found"}') == (404, b'{"code":"not_found"}')`.

So the cases pin the body and not merely the status. The experiment was reverted with
`git checkout --` on the two source files, and the module was re-run green before the commit.

## Decisions Made

- **The refusal reuses `RestoreSubscriptionNotEntitled`.** `grep -c 'class Restore'` in
  `errors.py` reads 5 before and after. A distinguishable body would tell a caller which of three
  checks refused, which is an oracle for another account's subscription state (T-45-07-03).
- **`<=`, not `<`.** A term ending exactly at the captured instant is over. Pinned by
  `test_a_term_ending_at_the_captured_instant_is_not_open`.
- **`is None`, not a falsy test.** A datetime is never falsy, and the absent term is the whole
  first reachable combination.
- **The comparison reads `self.evaluated_at` and no clock.** `grep -c 'datetime.now'` in
  `restore.py` reads 0.
- **The stale-term case seeds a live grant first.** Without it the case would assert that nothing
  changed in an account that held nothing. With it, the case fails pre-fix precisely because the
  live grant was superseded to make room for a dead one — CR-02's "bricked slot" as a measurement.
- **The Play control rides the real class.** It scripts a `SUBSCRIPTION_STATE_IN_GRACE_PERIOD` body
  through `real_google_play_seam`, so `read_for_restore`'s own grace mapping is what supplies the
  window, rather than a hand-built value type asserting itself.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's stale-term value would have violated a CHECK instead of reaching the defect**

- **Found during:** Task 1
- **Issue:** The plan scripts the stale case as `_proof(external_id, expires_at=now - PURCHASED_AGO)`.
  `_proof` already sets `purchased_at = now - PURCHASED_AGO`, so `starts_at` and `ends_at` would
  have been the same instant, and `CHECK (ends_at IS NULL OR ends_at > starts_at)` would have
  refused the pre-fix write. The case would have gone red on a 500 from a constraint, not on the
  dead grant CR-02 describes, and would have proved nothing about the defect.
- **Fix:** Added `TERM_ENDED_AGO = timedelta(minutes=30)` — past, and still later than
  `PURCHASED_AGO`, which the CHECK compares it to.
- **Files modified:** `tests/e2e/test_restore_subscription.py`
- **Verification:** The case goes red pre-fix on the account snapshot (the live grant superseded),
  which is the defect, and green post-fix.
- **Committed in:** `b1e5559`

**2. [Rule 2 - Missing Critical] The plan's five cases left one of its own must-have truths uncovered**

- **Found during:** Task 1
- **Issue:** The plan's must-haves name "a proof carrying no term at all — `expires_at` None on the
  active path, `grace_period_expires_at` None on the grace path". The five named cases cover the
  grace path only. The plan's own `_proof` keyword cannot express the active path, because its
  default is `None` and `None` means "not given".
- **Fix:** Added `test_an_active_proof_carrying_no_expiry_attaches_nothing`, building that proof
  with `dataclasses.replace(_proof(...), expires_at=None)` rather than changing the keyword's
  specified signature.
- **Files modified:** `tests/e2e/test_restore_subscription.py`
- **Verification:** Observed red (200) pre-fix, green post-fix.
- **Committed in:** `b1e5559`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both are inside the plan's own scope — one makes a named case actually reach
the defect it names, the other covers a truth the plan itself declares. No scope creep; no source
change beyond the plan's twelve lines.

## Issues Encountered

None.

## Known residuals

- **The class name still says "Two" while the class holds three arms.**
  `TestTheTwoRefusalsOfTheRestoreNotFoundFamily` now covers three refusals. The plan directed the
  count be corrected in the docstring and named the class by that name in its acceptance criteria,
  so the name was left as it is. It is a one-line rename with no other reference in the repository.
- **A refused restore still writes no audit row** (45-REVIEW WR-04). A refusal that was wrong would
  leave no trail. 45-CONTEXT's "Carried forward" deletes `audit.auth_events`, and a gap-closure
  plan may not reverse that.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

VERIFICATION truth 1 is ready to be re-run and answered VERIFIED: both reachable combinations CR-02
names — the never-expiring grant and the bricked slot — now refuse before any write, and both
stores still attach a genuine term.

RESTORE-01 stays unmarked in `REQUIREMENTS.md`: 45-09 also declares it and has no SUMMARY yet, so
the shared-ID gate holds it. 45-09 is the remaining plan of this phase.

Full suite after this plan: **1250 unit / 333 e2e / 229 schema**, `uv run ruff check src tests`
clean. Every command was run in this plan, not copied.

## Self-Check

- `src/nativespeaker/api/services/restore.py` — FOUND
- `tests/e2e/test_restore_subscription.py` — FOUND
- `b1e5559`, `25e56cf`, `18913be` — FOUND in `git log`

## Self-Check: PASSED

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*
