---
phase: 49-delete-the-single-implementation-auth-protocols
plan: 01
subsystem: auth
tags: [protocol, refactor, google-play, jwt, annotations]

requires:
  - phase: 44-store-notifications
    provides: "Commit 37a5ac6, the model for one Protocol deletion per commit"
  - phase: 48-narrow-identity-to-the-verified-pair
    provides: "D-10, the comment rule every edit here follows"
provides:
  - "PlaySubscriptionSource deleted; RestoreService annotates play as PlayDeveloperSubscriptions"
  - "TokenVerifier deleted; PubSubPushTokens annotates verifier and build as JWTVerifier"
  - "The proven seam recipe: delete the Protocol, repoint the annotation, re-measure CURRENT, one commit"
affects: [49-02, 49-03, 49-04, 50-typed-runtime-container]

actuals:
  tokens: 25251
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "One Protocol per commit, with the re-measured package-shape tuple in that same commit (D-08)"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/auth/google_play.py
    - src/nativespeaker/api/auth/jwt_verifier.py
    - src/nativespeaker/api/services/restore.py
    - tests/unit/test_auth_package_shape.py
    - tests/unit/test_google_play_notifications.py

key-decisions:
  - "The plan named tests/unit/test_jwt_verifier.py in Task 2's verify block; no such file exists. The real JWTVerifier suites are tests/unit/test_jwt_security.py and tests/unit/test_jwks_offload.py, and both were run instead."
  - "Both measured CURRENT triples matched their projections exactly: (8, 23, 65) then (8, 22, 64)."

patterns-established:
  - "Seam recipe: delete the Protocol block with its docstrings, move no docstring onto the concrete class, drop the typing.Protocol import when nothing else needs it, repoint the consumer's import and annotation, then re-measure CURRENT from the failing run's own output."

requirements-completed: []

coverage:
  - id: D1
    description: "PlaySubscriptionSource is deleted and RestoreService annotates play as PlayDeveloperSubscriptions"
    verification:
      - kind: other
        ref: "grep -rn 'PlaySubscriptionSource' src tests (prints nothing)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_restore_proof.py, tests/unit/test_google_play_notifications.py (231 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "TokenVerifier is deleted and PubSubPushTokens annotates verifier and build as JWTVerifier"
    verification:
      - kind: other
        ref: "grep -rn 'TokenVerifier' src tests (prints nothing)"
        status: pass
      - kind: other
        ref: "inspect.get_annotations(PubSubPushTokens.__init__, eval_str=True)['verifier'] is JWTVerifier | None"
        status: pass
      - kind: unit
        ref: "tests/unit/test_jwt_security.py, tests/unit/test_jwks_offload.py, tests/unit/test_google_play_notifications.py (216 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Each seam commit carries its own re-measured auth package-shape tuple (D-08)"
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_package_shape.py#test_it_still_measures_the_recorded_current_shape"
        status: pass
      - kind: other
        ref: "git log --stat: bfb923a touches 3 files, 6d9ed93 touches 4, each including the shape test"
        status: pass
    human_judgment: false
  - id: D4
    description: "The whole suite carries only the pre-existing restore four-arms failure"
    verification:
      - kind: e2e
        ref: ".venv/bin/pytest -q -m '' (1 failed, 2580 passed)"
        status: pass
    human_judgment: false

duration: 7 min
completed: 2026-09-17
status: complete
---

# Phase 49 Plan 01: Delete the single-implementation auth Protocols Summary

**`PlaySubscriptionSource` and `TokenVerifier` deleted in one commit each, their three annotation sites repointed at `PlayDeveloperSubscriptions` and `JWTVerifier`, and the auth package-shape tuple re-measured inside each commit.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-17T22:51:07Z
- **Completed:** 2026-09-17T22:58:26Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- The Play read Protocol is gone. `RestoreService.__init__` annotates `play` as `PlayDeveloperSubscriptions`, the one class that ever implemented it.
- The JWT verification Protocol is gone. `PubSubPushTokens.__init__` annotates `verifier` as `JWTVerifier | None` and `build` as `Callable[[], JWTVerifier | None] | None`, which is what `build_google_push_verifier` already returns.
- The tracer proved the full seam recipe end to end on the smallest seam before the second seam copied it.
- Both `CURRENT` triples were read out of the failing run, never typed in from the projection, and both matched: `(8, 24, 67)` to `(8, 23, 65)` to `(8, 22, 64)`.

## Task Commits

1. **Task 1: Delete the Play subscription Protocol** — `bfb923a` (refactor)
2. **Task 2: Delete the JWT Protocol and repoint the push-token consumer** — `6d9ed93` (refactor)

## Files Created/Modified

- `src/nativespeaker/api/auth/google_play.py` — the `PlaySubscriptionSource` Protocol deleted, the `typing.Protocol` import dropped, and both `PubSubPushTokens.__init__` annotations repointed at `JWTVerifier`.
- `src/nativespeaker/api/auth/jwt_verifier.py` — the `TokenVerifier` Protocol deleted and the `typing.Protocol` import dropped.
- `src/nativespeaker/api/services/restore.py` — the import and the `play` annotation name `PlayDeveloperSubscriptions`.
- `tests/unit/test_google_play_notifications.py` — `TestThePushTokenSeamIsTheAnnotation` deleted, with the deleted name dropped from the `jwt_verifier` import and the now-unused `typing` import.
- `tests/unit/test_auth_package_shape.py` — `CURRENT` re-measured twice, once per seam commit.

## Decisions Made

- **The retired WR-24 guard.** `TestThePushTokenSeamIsTheAnnotation` is deleted, as ROADMAP criterion 3 asks, rather than rewritten against the concrete class the way 37a5ac6 rewrote its own WR-18 guard. Two cases go: the annotation assertion, and the member-set control that checked the production verifier carried every member the Protocol declared. A later reader should know the loss is deliberate — a class cannot fail to carry its own members, so the control had nothing left to catch once the Protocol went.
- **Both measured tuples matched their projections.** `(8, 23, 65)` after Task 1 and `(8, 22, 64)` after Task 2. Each was still read out of the failing assertion's own text, as D-08 requires, and never written from the projection.
- **`ty` is unmoved at 306 diagnostics**, the Phase 48 baseline. The new annotations type-check against the existing builder and call sites.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 2's verify block named a test file that does not exist**

- **Found during:** Task 2
- **Issue:** `<verify>` and threat T-49-01 both name `tests/unit/test_jwt_verifier.py`. `git ls-files tests` shows no such path, and pytest answered `ERROR: file or directory not found`, collecting 0 items. A run that collects nothing is not a pass, so the command could not verify the mitigation it was written for.
- **Fix:** Diagnosed to the real suites. `grep -rln 'jwt_verifier' tests` and `git ls-files` name `tests/unit/test_jwt_security.py` as the `JWTVerifier` behavior suite, with `tests/unit/test_jwks_offload.py` covering the JWKS fetch path. Both were run in its place, beside `tests/unit/test_google_play_notifications.py`: **216 passed**. These are the suites that exercise signature checking, the audience claim and the required-claim list, which is what T-49-01 asks to stay green.
- **Files modified:** none — this is a plan-text error, not a code defect.
- **Verification:** `.venv/bin/pytest -q tests/unit/test_google_play_notifications.py tests/unit/test_jwt_security.py tests/unit/test_jwks_offload.py` → 216 passed.
- **Committed in:** no code change; recorded here. Plans 49-02 to 49-04 should not copy the wrong file name.

**2. [Rule 3 - Blocking] The unused `typing` import after the guard class went**

- **Found during:** Task 2
- **Issue:** `TestThePushTokenSeamIsTheAnnotation` held the only `typing.` use in `tests/unit/test_google_play_notifications.py`, so deleting it left `import typing` unused and ruff's `F401` red.
- **Fix:** Dropped `import typing`. `import inspect` stays — line 510 still uses it.
- **Files modified:** `tests/unit/test_google_play_notifications.py`
- **Verification:** `.venv/bin/ruff check src tests` → `All checks passed!`
- **Committed in:** `6d9ed93` (part of the task commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3, blocking).
**Impact on plan:** No scope creep. Neither deviation changed what the plan set out to do; one corrected a wrong file name in the plan's own verify block, the other cleared an import the deletion orphaned.

## Issues Encountered

- **The stated test baseline did not match the tree.** The plan records `1 failed, 2572 passed` for `-m ''`. The measured count before any edit of this plan was `1 failed, 2582 passed`, ten higher. The failed name is the same pre-existing restore four-arms case, so the gate is met; the passed baseline in the plan was simply stale. After both commits the count is `1 failed, 2580 passed` — two lower, which is exactly the two cases Task 2 deleted. Later plans in this phase should measure against 2580, not 2572.

## Verification Results

Run from the repository root after both commits:

| Check | Result |
|---|---|
| `.venv/bin/pytest -q -m ''` | `1 failed, 2580 passed` — the failure is the pre-existing restore four-arms case and no other |
| `.venv/bin/ruff check src tests` | `All checks passed!` |
| `test -z "$(grep -rn 'PlaySubscriptionSource\|TokenVerifier' src tests)"` | exit 0 — neither name is left |
| `.venv/bin/ty check` | `Found 306 diagnostics` — the Phase 48 baseline, unmoved |

The `e2e` and `schema` suites were not run with their own markers: this plan touches no file in either, and `-m ''` selects both anyway, which is the run recorded above.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or schema change. T-49-01 and T-49-02 are annotation-only edits with their suites green; T-49-03's accepted loss is recorded under Decisions Made.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The seam recipe is proven end to end and 49-02 can copy it for `FirebaseAdminAdapter` and `DeviceCheckAdapter`.
- `CURRENT` now reads `(8, 22, 64)`. 49-02's two seam commits each re-measure from there.
- Two corrections for the remaining plans: the JWT suites are `test_jwt_security.py` and `test_jwks_offload.py`, and the `-m ''` passed baseline is 2580.

## Self-Check: PASSED

- All five modified files exist on disk.
- Both commits exist: `bfb923a`, `6d9ed93`.
- Every task acceptance criterion re-run and passing.

---
*Phase: 49-delete-the-single-implementation-auth-protocols*
*Completed: 2026-09-17*
