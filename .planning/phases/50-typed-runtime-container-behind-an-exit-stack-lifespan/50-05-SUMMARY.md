---
phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
plan: 05
subsystem: auth
tags: [runtime, dependencies, firebase, devicecheck, routing, pytest]

requires:
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "`Runtime`, `get_runtime` and `app.state.runtime` (50-03)"
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "the `dataclasses.replace` field-swap pattern for the e2e suite (50-04)"
provides:
  - "`get_auth_service` served off the container; `get_firebase_adapter` and `get_devicecheck_adapter` deleted"
  - "`sign_out_all` declares `get_runtime` and reads `runtime.firebase_adapter`"
  - "criterion 5's route clause measured in both directions, in `tests/unit/test_app_wiring.py`"
affects: [50-06, 50-07]

actuals:
  tokens: 72500
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A unit app replaces several getter overrides with one `app.dependency_overrides[get_runtime]`, naming every field that file reads"
    - "A route-table case uses `_declared`, not `_flattened`, when the dependency is reachable under a sub-dependency"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/routers/auth.py
    - tests/e2e/conftest.py
    - tests/e2e/test_sign_out_all.py
    - tests/e2e/test_upgrade_anonymous.py
    - tests/e2e/test_create_user.py
    - tests/unit/test_app_wiring.py
    - tests/unit/test_challenge_endpoint.py
    - tests/unit/test_create_user_body.py
    - tests/unit/test_create_user_precedence.py
    - tests/unit/test_claim_precedence.py
    - tests/unit/test_claim_precedence_registered.py
    - tests/unit/test_upgrade_precedence.py

key-decisions:
  - "The plan's `# ty: ignore[invalid-argument-type]` on a `None` adapter field was not written: `make_runtime` takes `**overrides`, so `ty` reports nothing there and the comment measures as unused"
  - "Three e2e test files the plan did not list also read the deleted attribute; they were rewritten in the same commit, because the lifespan stops setting it"
  - "An override of `get_runtime` replaced the `app.state.runtime` assignment in the three precedence files, rather than sitting beside it"

requirements-completed: []

coverage:
  - id: D1
    description: "`get_firebase_adapter` and `get_devicecheck_adapter` are deleted, and `get_auth_service` reads both adapters off the container (criterion 5)"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn 'get_firebase_adapter\\|get_devicecheck_adapter\\|state.firebase_adapter\\|state.devicecheck_adapter' src tests --include='*.py')\""
        status: pass
      - kind: unit
        ref: ".venv/bin/pytest -q -p no:cacheprovider — 1896 passed"
        status: pass
    human_judgment: false
  - id: D2
    description: "`sign_out_all` declares `runtime: Runtime = Depends(get_runtime)`, passes `runtime.firebase_adapter` to `revoke_with_retry`, and still declares no database session (D-05)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestOnlyTheSignOutRouteReachesTheContainer::test_sign_out_all_declares_the_container"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheSignOutRouteOpensNoSession::test_sign_out_all_declares_no_database_session"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py — passed inside the 361-case `-m e2e` run"
        status: pass
    human_judgment: false
  - id: D3
    description: "No route other than `sign_out_all` declares `get_runtime`, so a future route cannot quietly reach the whole container (threat T-50-05-03)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestOnlyTheSignOutRouteReachesTheContainer::test_no_other_route_declares_the_container"
        status: pass
      - kind: other
        ref: "throwaway `Depends(get_runtime)` added to `/auth/sync` — the case failed with `['/auth/sync']`, then reverted"
        status: pass
    human_judgment: false
  - id: D4
    description: "The lifespan sets two fewer `app.state` attributes, and the e2e adapter fixtures swap the container field rather than the container"
    verification:
      - kind: other
        ref: "grep -c 'app.state' src/nativespeaker/api/app/lifespan.py — the two adapter assignments are gone"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e — 361 passed"
        status: pass
    human_judgment: false
  - id: D5
    description: "49 D-06 stands: `services/auth.py` is untouched and `AuthService.__init__` keeps its two adapter annotations"
    verification:
      - kind: other
        ref: "git diff --stat -- src/nativespeaker/api/services/auth.py — empty"
        status: pass
    human_judgment: false

duration: 10 min
completed: 2026-09-18
status: complete
---

# Phase 50 Plan 05: The two adapters move into the container Summary

**The Firebase and DeviceCheck adapters are served off `Runtime`, the last two getters criterion 5 names are gone, and the revocation route is the one route that declares the container.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-09-18T08:40:11Z
- **Completed:** 2026-09-18T08:50:16Z
- **Tasks:** 2
- **Files created or modified:** 14

## Accomplishments

- `get_firebase_adapter` and `get_devicecheck_adapter` are deleted, with the `FirebaseAdminLookup` and `AppleDeviceCheck` imports they were the last users of in `dependencies.py`.
- `get_auth_service` takes `db` and `runtime`, and passes `adapter=runtime.firebase_adapter` and `devicecheck=runtime.devicecheck_adapter`. `services/auth.py` is untouched, so 49 D-06's annotations stand where they live.
- `sign_out_all` declares `runtime: Runtime = Depends(get_runtime)` and calls `revoke_with_retry(runtime.firebase_adapter, claims.issuer, claims.subject)`. Its `get_claims` and `get_identity` parameters did not move, and it still opens no session.
- The lifespan drops `app.state.firebase_adapter` and `app.state.devicecheck_adapter`. Both locals stay and still feed the one `Runtime(...)` call.
- `scripted_firebase_adapter` and `scripted_devicecheck_adapter` in `tests/e2e/conftest.py` save the field, replace the field, and restore the field, as plan 50-04 proved under nesting.
- Six unit files replace two `dependency_overrides` entries each with one `app.dependency_overrides[get_runtime]`. In the three precedence files that one entry absorbs the `app.state.runtime` assignment as well.
- A new class in `tests/unit/test_app_wiring.py` measures criterion 5's route clause in both directions, and the unit suite rose from 1894 to 1896.

## Task Commits

1. **Task 1: the two adapters move into the container, and `sign_out_all` with them** — `e4890b1` (refactor)
2. **Task 2: the criterion 5 route clause** — `f658615` (test)

## Files Created/Modified

- `src/nativespeaker/api/app/dependencies.py` — two getters and two imports deleted; `get_auth_service` rewritten.
- `src/nativespeaker/api/app/lifespan.py` — two `app.state` assignments deleted.
- `src/nativespeaker/api/routers/auth.py` — `sign_out_all` takes the container; the import list swaps `get_firebase_adapter` and `FirebaseAdminLookup` for `get_runtime` and `Runtime`.
- `tests/e2e/conftest.py` — both adapter fixtures swap the container field.
- `tests/e2e/test_sign_out_all.py` — `real_seam` swaps the field; `replace` imported.
- `tests/e2e/test_upgrade_anonymous.py`, `tests/e2e/test_create_user.py` — five reads now go through `state.runtime`.
- `tests/unit/test_app_wiring.py` — the new criterion 5 class, two cases.
- `tests/unit/test_challenge_endpoint.py`, `test_create_user_body.py`, `test_create_user_precedence.py`, `test_claim_precedence.py`, `test_claim_precedence_registered.py`, `test_upgrade_precedence.py` — one `get_runtime` override each.

## Decisions Made

- The new wiring class uses `_declared`, as the plan required, and its docstring says why. Every route already reaches `get_runtime` under `get_db` or `get_claims`, so a `_flattened` walk would hold for all of them and measure nothing.
- In the three precedence files the `get_runtime` override replaced the `app.state.runtime` line rather than joining it. An override bypasses `app.state`, so two containers would have left the unused one as a false record of the fixture's intent. The session factory each file relies on is named in the same `make_runtime(...)` call.
- No `# ty: ignore[invalid-argument-type]` was written for the `None` adapter fields. See the deviation below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Three e2e test files read the deleted attribute**

- **Found during:** Task 1
- **Issue:** The plan lists `tests/e2e/conftest.py` alone, but `tests/e2e/test_sign_out_all.py:64-72`, `test_upgrade_anonymous.py:69, 76, 282` and `test_create_user.py:567, 605` also read or write `_app_lifespan.state.firebase_adapter`. The lifespan stops setting that attribute in this same task, so all three would raise `AttributeError`, and the task's own `test -z` gate would have failed on them.
- **Fix:** `real_seam` in `test_sign_out_all.py` now swaps the container field with `dataclasses.replace`, saving and restoring the field, as the conftest fixtures do. The five reads in the other two files became `state.runtime.firebase_adapter`.
- **Files modified:** `tests/e2e/test_sign_out_all.py`, `tests/e2e/test_upgrade_anonymous.py`, `tests/e2e/test_create_user.py`
- **Verification:** `.venv/bin/pytest -q -p no:cacheprovider -m e2e` — 361 passed, exit 0; the `test -z` gate is empty.
- **Commit:** `e4890b1`

### The `# ty: ignore` the plan asked for was not written

The plan's action says: "Where a case overrode a getter with `lambda: None` to script an absent adapter, pass `None` as that field with an inline `# ty: ignore[invalid-argument-type]`." The `None` was passed, in `test_claim_precedence.py`, `test_claim_precedence_registered.py`, `test_create_user_body.py` and `test_upgrade_precedence.py`. The suppression was not, because `make_runtime(**overrides)` takes untyped keyword arguments, so `ty` reports no diagnostic at those call sites.

This was measured, not assumed. Adding the comment to one such line and running `.venv/bin/ty check tests/unit/test_claim_precedence.py` returned `warning[unused-ignore-comment]: Unused 'ty: ignore' directive` and raised that file from 1 diagnostic to 2. The comment would have added noise and hidden nothing. The whole-tree count stays at 296, the plan 50-04 baseline.

---

**Total deviations:** 1 auto-fixed (1 blocking), plus one instruction not followed with the measurement above. **Impact on plan:** no acceptance criterion is weakened. The e2e fix is what lets the task's own grep gate pass.

## Issues Encountered

None. The unit suite rose from 1894 to 1896, which is task 2's two cases and nothing else. The e2e count is 361 and the schema count is 297, both unchanged since plan 50-04.

## Threat Notes

- **T-50-05-01** (elevation at `sign_out_all`): `Depends(get_claims)` and `Depends(get_identity)` are unchanged and still first in the signature. Only the adapter parameter moved. `TestOnlyTheSignOutRouteReachesTheContainer` and the existing `TestEveryRouteIsAuthenticated` cases both pass, and `test_a_narrowed_route_declares_the_linked_identity_narrowing` names this route.
- **T-50-05-02** (spoofing at `revoke_with_retry`): the call still reads `claims.issuer` and `claims.subject`, the request-verified pair, never `linked`. The line is carried over word for word with `adapter` replaced by `runtime.firebase_adapter`. `tests/e2e/test_sign_out_all.py` covers the route end to end.
- **T-50-05-03** (the container on an unintended route): measured, not asserted by reading. A throwaway `Depends(get_runtime)` on `/auth/sync` made `test_no_other_route_declares_the_container` fail with `routes declaring the whole container: ['/auth/sync']`. The edit was reverted and `git diff` on the router is empty.
- **T-50-05-SC**: no package was installed or upgraded. `uv.lock` is untouched.

## Verification Results

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` | 1896 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m e2e` | 361 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m schema` | 297 passed, exit 0 |
| `.venv/bin/ruff check src tests` | All checks passed! |
| `.venv/bin/ty check` | Found 296 diagnostics, the 50-04 baseline |
| `test -z "$(grep -rn 'get_firebase_adapter\|get_devicecheck_adapter\|state.firebase_adapter\|state.devicecheck_adapter' src tests --include='*.py')"` | empty, exit 0 |
| `grep -c 'Depends(get_runtime)' src/nativespeaker/api/routers/auth.py` | 1 |
| `sign_out_all` parameter count | 3: claims, linked, runtime |
| `git diff --stat -- src/nativespeaker/api/services/auth.py` | empty, byte-identical |
| `.venv/bin/pytest tests/unit/test_app_wiring.py -k OnlyTheSignOutRouteReachesTheContainer --collect-only` | 2 cases |
| `git diff --diff-filter=D --name-only` over both commits | empty, no file deleted |

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Criterion 5 is now complete for the getters: `get_config`, `get_session_factory`, `get_firebase_adapter` and `get_devicecheck_adapter` are all gone. Its route clause is measured in both directions.
- `dependencies.py` holds 8 `request.app.state` reads, down from 10 after plan 50-04. All eight are in `get_restore_service` and the two webhook verifiers, which are plan 50-06.
- Criterion 6: `tests/e2e/conftest.py` still sets no lifespan attribute on `app.state`; the two store fixtures and one `config` read remain for plan 50-06, and they now have two more worked examples of the field swap.
- Plan 50-06 should expect e2e test files outside `conftest.py` to read the store attributes too, as three did here.

## Self-Check: PASSED

- `src/nativespeaker/api/app/dependencies.py` — FOUND
- `src/nativespeaker/api/app/lifespan.py` — FOUND
- `src/nativespeaker/api/routers/auth.py` — FOUND
- `tests/e2e/conftest.py` — FOUND
- `tests/e2e/test_sign_out_all.py` — FOUND
- `tests/e2e/test_upgrade_anonymous.py` — FOUND
- `tests/e2e/test_create_user.py` — FOUND
- `tests/unit/test_app_wiring.py` — FOUND
- `tests/unit/test_challenge_endpoint.py` — FOUND
- `tests/unit/test_create_user_body.py` — FOUND
- `tests/unit/test_create_user_precedence.py` — FOUND
- `tests/unit/test_claim_precedence.py` — FOUND
- `tests/unit/test_claim_precedence_registered.py` — FOUND
- `tests/unit/test_upgrade_precedence.py` — FOUND
- commit `e4890b1` — FOUND
- commit `f658615` — FOUND
- Both tasks' `<acceptance_criteria>` re-run after the commits — PASS
- The plan `<verification>` block re-run after the commits — PASS

---
*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Completed: 2026-09-18*
</content>
</invoke>
