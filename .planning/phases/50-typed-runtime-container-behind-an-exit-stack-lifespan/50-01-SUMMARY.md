---
phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
plan: 01
subsystem: auth
tags: [google-play, pubsub, subscriptions, httpx, fastapi, pytest]

requires:
  - phase: 47-thread-no-instant
    provides: the log-event rename this plan's first commit finishes
  - phase: 49-delete-the-single-implementation-auth-protocols
    provides: the auth package shape tuple this plan re-measures
provides:
  - GooglePlayNotifications — one class with verify, read and read_for_restore
  - app.state.google_play_notifications — one attribute in place of two
  - FakePlaySubscriptions.verify and .push_calls in tests/e2e/conftest.py
  - a green e2e suite, with the Phase 47 failure cleared
affects: [50-02, 50-03, 50-06]

actuals:
  tokens: 9600
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "One store class per store, shaped like AppStoreNotifications: keyword-only constructor, one self._x per parameter, each entry point opening with its own None guard"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/auth/google_play.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/services/restore.py
    - tests/e2e/conftest.py
    - tests/e2e/test_restore_subscription.py
    - tests/unit/test_google_play_notifications.py
    - tests/unit/test_auth_package_shape.py
    - tests/unit/test_restore_proof.py

key-decisions:
  - "The Phase 47 e2e failure is a wrong test expectation, not a source defect: errors.py is byte-identical at both commits"
  - "GooglePlayNotifications keeps the stage string play_subscriptions_read, because D-09 pins every stage string unchanged"
  - "The credential rebuild classes are deleted with the machinery they test, not only the one class the plan named"

patterns-established:
  - "A stage string is not an attribute name: a merged class renames its app.state attribute and keeps its wire and log vocabulary"

requirements-completed: []

coverage:
  - id: D1
    description: "The Phase 47 log-event expectation is corrected, so the e2e suite exits 0"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e"
        status: pass
    human_judgment: false
  - id: D2
    description: "GooglePlayNotifications is the one Google Play class, carrying verify, read and read_for_restore with their current stage strings"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheCanceledTermIsJudgedByTheHelperThatTakesTheInstant::test_the_class_holds_no_clock_of_its_own_to_fall_back_to"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePushTokenCheck"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestAnUnconfiguredCredentialIsNeverAcknowledged"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "No build callable, rebuild lock, rebuild interval or _credential_in_hand survives in src or tests"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn 'PubSubPushTokens\\|PlayDeveloperSubscriptions\\|_credential_in_hand\\|_rebuild_lock\\|_next_rebuild\\|REBUILD_INTERVAL_SECONDS' src tests --include='*.py')\""
        status: pass
    human_judgment: false
  - id: D4
    description: "CURRENT in tests/unit/test_auth_package_shape.py carries a re-measured tuple, read off the failing run's own text"
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_package_shape.py#TestThePackageShrank::test_it_still_measures_the_recorded_current_shape"
        status: pass
    human_judgment: false

duration: 13 min
completed: 2026-09-18
status: complete
---

# Phase 50 Plan 01: One Google Play class, no rebuild machinery Summary

**`PubSubPushTokens` and `PlayDeveloperSubscriptions` merged into `GooglePlayNotifications`, the rebuild code deleted, and the Phase 47 e2e failure cleared in its own commit.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-09-18T07:49:50Z
- **Completed:** 2026-09-18T08:02:44Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- The e2e suite is green again. The Phase 47 defect was one wrong test expectation, not a source defect.
- One Google Play class holds the three entry points `verify`, `read` and `read_for_restore`. Each keeps its own `None` guard and its current stage string.
- The rebuild machinery is gone: no `build` parameter, no lock, no interval, no `_credential_in_hand`.
- The lifespan sets one attribute, `app.state.google_play_notifications`, in place of two.
- `CURRENT` in the auth shape test is re-measured at `(7, 18, 58)`, read off the failing run's own output.

## Task Commits

1. **Task 1: the Phase-47 log-event expectation** - `85261f7` (test)
2. **Task 2: one Google Play class, no rebuild machinery** - `c1ead1c` (refactor)

## Files Created/Modified

- `src/nativespeaker/api/auth/google_play.py` - Two classes become `GooglePlayNotifications`; the rebuild code and two module constants are deleted. `CappedRefreshRequest` is unchanged.
- `src/nativespeaker/api/app/lifespan.py` - One construction in place of two.
- `src/nativespeaker/api/app/dependencies.py` - Three reads now name the one attribute.
- `src/nativespeaker/api/services/restore.py` - The import and the `play` annotation name the merged class.
- `tests/e2e/test_restore_subscription.py` - The two log-event literals read `purchase_proof_rejected`.
- `tests/e2e/conftest.py` - `FakePlaySubscriptions` gained `verify` and `push_calls`; the three Play fixtures swap one attribute; `AcceptingPushTokens` is deleted.
- `tests/unit/test_google_play_notifications.py` - The fixtures build the merged class; the three rebuild test classes are deleted.
- `tests/unit/test_auth_package_shape.py` - `CURRENT` is `(7, 18, 58)`.
- `tests/unit/test_restore_proof.py` - Its four Play call sites name the merged class.

## Decisions Made

- The Phase 47 failure is a test defect. `errors.py` is byte-identical at `9bc4e97` before and after Task 1, and the emitted event was measured as `purchase_proof_rejected` before the edit.
- `GooglePlayNotifications` keeps the stage string `play_subscriptions_read`. The plan's acceptance line "`play_subscriptions` appears nowhere in `src`" is read as the `app.state` attribute, because must-have D-09 pins every stage string unchanged. The two cannot both hold literally, and D-09 is the must-have.
- `verify` takes no default. Every call site passes `verifier=`, as `AppStoreNotifications` requires its own.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated `tests/unit/test_restore_proof.py`**
- **Found during:** Task 2
- **Issue:** The file was not in the plan's `<files>` list, but it holds four `PlayDeveloperSubscriptions` call sites. The plan's own gate requires that name absent from `src` and `tests`.
- **Fix:** Its import, two annotations and two constructions name `GooglePlayNotifications` and pass `verifier=None`.
- **Verification:** `.venv/bin/pytest -q` exits 0; the six-name gate is empty.
- **Committed in:** `c1ead1c`

**2. [Rule 3 - Blocking] Deleted two more rebuild test classes**
- **Found during:** Task 2
- **Issue:** The plan named only `TestAWarmUpFailureIsRetriedRatherThanCachedForThePodsLife`. Two more classes test the same deleted machinery: `TestTheRebuildIsSerializedAndFloored` and `TestACredentialBootCouldNotReadIsRebuiltRatherThanCachedForThePodsLife`, with its helper `_RecordingCredentialBuild`.
- **Fix:** All three classes and the helper are deleted.
- **Verification:** `.venv/bin/pytest -q` exits 0; `ruff check src tests` prints `All checks passed!`.
- **Committed in:** `c1ead1c`

**3. [Rule 3 - Blocking] One stub object for the merged dependency**
- **Found during:** Task 2
- **Issue:** `_stub_request` set two `app.state` members that cases script apart. The dependency now reads one.
- **Fix:** A new `_StubGooglePlay` composes this case's token check and this case's read behind one object. Every existing case keeps its `tokens=` and `play=` arguments.
- **Verification:** All 25 dependency cases in the file pass.
- **Committed in:** `c1ead1c`

---

**Total deviations:** 3 auto-fixed (3 blocking)
**Impact on plan:** All three were required by the plan's own acceptance gate or by the merge itself. No scope creep.

## Issues Encountered

A `git stash` was run mid-task while inspecting type-checker output. It reverted every uncommitted Task 2 edit. The work was recovered in full with `git stash pop`, and all three suites plus `ruff` and every acceptance gate were re-run green before the commit. Nothing was lost. Recorded because the command should not have been run at all.

## Verification Results

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` | 1892 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m e2e` | 361 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m schema` | 297 passed, exit 0 |
| `.venv/bin/ruff check src tests` | All checks passed! |
| six-name absence gate | empty, exit 0 |
| `.venv/bin/ty check` | 295 diagnostics, down from the 306 at Phase 49 close |

The schema suite and `ty` are not plan verify commands. They were run as regression checks.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ROADMAP criterion 8's first half is met: `GooglePlayNotifications` is the one Google Play class, with no `build` callable, lock or rebuild interval.
- Criterion 7 is no longer blocked by a foreign failure. The three suites are 1892 / 361 / 297, all green.
- Plan 50-03 can annotate `Runtime.google_play_notifications` with the merged type: it exists now.
- `app.state.google_play_notifications` is temporary. Plan 50-06 moves it into `Runtime`.
- Plan 50-02 owns the boot rule (D-08) and the two warm-up warnings this plan left untouched.

## Self-Check: PASSED

- `src/nativespeaker/api/auth/google_play.py` — FOUND
- `tests/unit/test_auth_package_shape.py` — FOUND
- `tests/e2e/test_restore_subscription.py` — FOUND
- commit `85261f7` — FOUND
- commit `c1ead1c` — FOUND
- Every `<acceptance_criteria>` of both tasks re-run after the stash recovery — PASS

---
*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Completed: 2026-09-18*
