---
phase: 49-delete-the-single-implementation-auth-protocols
plan: 02
subsystem: auth
tags: [protocol, refactor, firebase, devicecheck, dataclass, annotations]

requires:
  - phase: 49-delete-the-single-implementation-auth-protocols
    provides: "Plan 49-01's proven seam recipe, and CURRENT at (8, 22, 64)"
  - phase: 48-narrow-identity-to-the-verified-pair
    provides: "D-10, the comment rule every edit here follows"
provides:
  - "DeviceCheckAdapter deleted; both retry helpers and both dependency sites annotate AppleDeviceCheck"
  - "FirebaseAdminAdapter deleted; both retry helpers and get_firebase_adapter annotate FirebaseAdminLookup"
  - "auth/adapters.py removed; VerifiedProviderIdentity declared in and imported from auth/firebase.py"
  - "The SDK-isolation guard and the value-type guard now run from tests/unit/test_firebase_adapter.py"
  - "All four Protocol names of this phase are absent from tracked src/ and tests/"
affects: [49-03, 49-04, 50-typed-runtime-container]

actuals:
  tokens: 75129
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "One Protocol per commit, with the re-measured package-shape tuple in that same commit (D-08)"
    - "A relocated package-wide guard derives its package path from a module that survives the deletion"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/auth/devicecheck.py
    - src/nativespeaker/api/auth/firebase.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/services/auth.py
    - tests/unit/test_firebase_adapter.py
    - tests/unit/test_devicecheck_adapter.py
    - tests/unit/test_claim_ordering.py
    - tests/unit/test_auth_package_shape.py
    - tests/unit/conftest.py

key-decisions:
  - "tests/unit/test_adapter_interfaces.py is deleted; TestNoProviderDependency and TestTheValueTypeIsImmutable move to tests/unit/test_firebase_adapter.py (Research Open Question 2)."
  - "Both measured CURRENT triples matched their projections exactly: (8, 21, 62) then (7, 20, 60)."
  - "Two verify greps in the plan match names that are not the Protocol; both were re-scoped rather than satisfied by editing unrelated code."

patterns-established:
  - "A relocated SDK-isolation guard names a surviving module in its membership control, so the case cannot go vacuous"

requirements-completed: []

coverage:
  - id: D1
    description: "DeviceCheckAdapter is deleted and both retry helpers plus both dependency sites annotate AppleDeviceCheck"
    verification:
      - kind: other
        ref: "git grep -nw 'DeviceCheckAdapter' -- src tests (prints nothing)"
        status: pass
      - kind: other
        ref: "inspect.get_annotations(read_bits_with_retry, eval_str=True)['adapter'] is AppleDeviceCheck; same for write_bits_with_retry and get_devicecheck_adapter's return"
        status: pass
      - kind: unit
        ref: "tests/unit/test_devicecheck_adapter.py, tests/unit/test_claim_ordering.py, tests/unit/test_app_wiring.py (114 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "FirebaseAdminAdapter is deleted, auth/adapters.py is removed, and VerifiedProviderIdentity is declared in auth/firebase.py"
    verification:
      - kind: other
        ref: "git grep -nw 'FirebaseAdminAdapter' -- src tests (prints nothing); test ! -e src/nativespeaker/api/auth/adapters.py (exit 0)"
        status: pass
      - kind: other
        ref: "grep -c 'class VerifiedProviderIdentity' src/nativespeaker/api/auth/firebase.py prints 1; 12 files name the type and every import resolves to auth.firebase"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py, tests/unit/test_firebase_retry.py (105 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The package-wide SDK-isolation guard still walks every surviving auth module, from its new home"
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestNoProviderDependency::test_importing_the_module_does_not_import_firebase_admin (5 cases: app_store, devicecheck, google_play, jwt_verifier, store_notifications)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestNoProviderDependency::test_the_set_is_every_auth_module_but_the_one_excluded_by_design (control names jwt_verifier)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The frozen and slotted properties of VerifiedProviderIdentity are still asserted, from their new home"
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheValueTypeIsImmutable (4 cases: frozen-and-slotted, reassignment, no-instance-dict, email default)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Each of the two seam commits carries its own re-measured auth package-shape tuple (D-08)"
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_package_shape.py#test_it_still_measures_the_recorded_current_shape"
        status: pass
      - kind: other
        ref: "git log --stat: 7fe6762 touches 5 files, 65b1c91 touches 16, each including the shape test"
        status: pass
    human_judgment: false
  - id: D6
    description: "All three suites carry only the pre-existing restore four-arms failure"
    verification:
      - kind: e2e
        ref: ".venv/bin/pytest -q -m '' (1 failed, 2563 passed)"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -m e2e (1 failed, 360 passed)"
        status: pass
      - kind: integration
        ref: ".venv/bin/pytest -q -m schema (297 passed, exit 0)"
        status: pass
    human_judgment: false

duration: 10 min
completed: 2026-09-17
status: complete
---

# Phase 49 Plan 02: Delete the single-implementation auth Protocols Summary

**`DeviceCheckAdapter` and `FirebaseAdminAdapter` deleted in one commit each, `auth/adapters.py` removed with `VerifiedProviderIdentity` re-landed in `auth/firebase.py`, and the package-wide SDK-isolation guard relocated into `tests/unit/test_firebase_adapter.py` without weakening it.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-09-17T23:03:03Z
- **Completed:** 2026-09-17T23:13:33Z
- **Tasks:** 2
- **Files modified:** 19 (17 modified, 2 deleted)

## Accomplishments

- The device-gate Protocol is gone. `read_bits_with_retry`, `write_bits_with_retry`, `get_devicecheck_adapter` and `get_auth_service`'s `devicecheck` parameter all name `AppleDeviceCheck`, the one class that ever implemented it.
- The provider Protocol is gone with its whole module. `lookup_with_retry`, `revoke_with_retry` and `get_firebase_adapter` name `FirebaseAdminLookup`.
- `VerifiedProviderIdentity` is declared in `auth/firebase.py`, verbatim with its docstring and both field comments. 11 importers were repointed; 12 files name the type and every import resolves to `nativespeaker.api.auth.firebase`.
- The two properties that had nothing to do with the deleted Protocol survived the file that held them. Both now run from `tests/unit/test_firebase_adapter.py`, and the membership control names `jwt_verifier` — a module that still exists — so the parametrized case cannot go vacuous.
- All four Protocol names of this phase are now absent from tracked `src/` and `tests/`.
- Both `CURRENT` triples were read out of the failing run, never typed in from the projection, and both matched: `(8, 22, 64)` to `(8, 21, 62)` to `(7, 20, 60)`.

## Task Commits

1. **Task 1: Delete the DeviceCheck Protocol** — `7fe6762` (refactor)
2. **Task 2: Delete the Firebase admin Protocol, move the value type, remove the adapter module** — `65b1c91` (refactor)

## Files Created/Modified

- `src/nativespeaker/api/auth/devicecheck.py` — the `DeviceCheckAdapter` Protocol deleted with its docstrings, the `typing.Protocol` import dropped, both retry helpers annotating `AppleDeviceCheck`.
- `src/nativespeaker/api/auth/firebase.py` — `VerifiedProviderIdentity` declared above `FirebaseAdminLookup`, `from dataclasses import dataclass` added, the `auth.adapters` import deleted, both retry helpers annotating `FirebaseAdminLookup`.
- `src/nativespeaker/api/auth/adapters.py` — **deleted**.
- `src/nativespeaker/api/app/dependencies.py` — both adapter imports repointed, three annotations repointed, and the one-line comment whose subject was the removed Protocol deleted (48 D-10). `get_challenge_store` and the two-accessor comment untouched; 49-03 owns them.
- `src/nativespeaker/api/services/auth.py` — the value type imported from `auth.firebase`, merged into the existing `auth.firebase` import line.
- `tests/unit/test_devicecheck_adapter.py` — `TestTheSeamIsTheAnnotation` deleted, the Protocol name dropped from the import, and the orphaned `typing` and `inspect` imports dropped.
- `tests/unit/test_claim_ordering.py` — the deleted name dropped from the `SEAM_NAMES` frozenset; `"AppleDeviceCheck"` and every other member kept.
- `tests/unit/test_adapter_interfaces.py` — **deleted**.
- `tests/unit/test_firebase_adapter.py` — `TestTheDeliberateNonImplementations` deleted; `TestNoProviderDependency` and `TestTheValueTypeIsImmutable` relocated here with `AUTH_PACKAGE`, `SDK_FREE_MODULES`, `FROZEN` and the `_run` subprocess helper.
- `tests/unit/{conftest,test_firebase_retry,test_upgrade_precedence,test_create_user_precedence}.py`, `tests/e2e/{test_upgrade_anonymous,test_create_user,test_flows}.py`, `tests/schema/{test_create_atomicity,test_create_race}.py` — one-line value-type import repoints.
- `tests/unit/test_auth_package_shape.py` — `CURRENT` re-measured twice, once per seam commit.

## Decisions Made

- **`tests/unit/test_adapter_interfaces.py` is deleted, and two of its four classes move to `tests/unit/test_firebase_adapter.py`.** This settles Research Open Question 2. The file read the removed module's source at import time, so it could not collect once the module went. `test_firebase_adapter.py` is the new home because `firebase` is the one auth module that may hold the provider SDK, and it is now also the module that declares the value type.
- **`AUTH_PACKAGE` is derived from the `firebase` module's own file.** The original derived it from the removed module. The relocated control reads `assert "jwt_verifier" in SDK_FREE_MODULES` in place of `assert "adapters" in SDK_FREE_MODULES`, and `assert len(SDK_FREE_MODULES) > 1` is kept. The parametrized case now collects five arms — `app_store`, `devicecheck`, `google_play`, `jwt_verifier`, `store_notifications` — one per surviving SDK-free auth module.
- **The retired WR-23 guard.** `TestTheSeamIsTheAnnotation` is deleted, as ROADMAP criterion 3 asks, rather than rewritten against the concrete class the way 37a5ac6 rewrote its own WR-18 guard. Three cases go: the two parametrized annotation assertions, and the member-set control that checked the production class carried every member the Protocol declared. The loss is deliberate — a class cannot fail to carry its own members, so the control had nothing left to catch once the Protocol went.
- **Both measured tuples matched their projections.** `(8, 21, 62)` after Task 1 and `(7, 20, 60)` after Task 2. Each was read out of the failing assertion's own text, as D-08 requires.
- **`ty` is unmoved at 306 diagnostics**, the Phase 48 baseline. The repointed annotations type-check against the existing lifespan and call sites.

## Cases dropped with `tests/unit/test_adapter_interfaces.py`

25 cases were deleted across Task 1 and Task 2 and 11 were relocated, a net loss of 14. Every drop below was deliberate, and each is recorded because a later reader would otherwise read it as an accident.

| Dropped | Cases | Why it has no subject after the deletion |
|---|---|---|
| `TestTheSeamIsTheAnnotation` (WR-23, `test_devicecheck_adapter.py`) | 3 | ROADMAP criterion 3. The annotation now names the only class it could name |
| `TestTheDeliberateNonImplementations` (`test_firebase_adapter.py`) | 1 | Asserted the concrete class does not inherit the Protocol. There is no Protocol |
| `TestTheOutcomeVocabularyLeftTheSeam` | 2 | Both count declarations inside the removed module |
| `TestFirebaseAdminAdapter` | 7 | Asserts the removed Protocol's method set, its two `async` declarations and its two return annotations. ROADMAP criterion 3 deletes the adapter-shape class rather than rewriting it against the concrete class |
| `test_every_public_class_is_a_protocol_or_a_frozen_dataclass` | 1 | Counts the removed module's own class list |
| `test_the_source_names_firebase_admin_nowhere_as_an_import` | 1 | An AST walk of the removed module's source. The parametrized subprocess case covers the same property for every surviving module, and covers it at import time rather than by reading text |
| `test_the_source_imports_only_the_stdlib_and_this_project` | 1 | Same: an AST walk of source that no longer exists |
| The `adapters` arm of the parametrized SDK-free case | 1 | The module it imported is gone |
| **Relocated, not dropped** | **11** | `TestNoProviderDependency` (5 parametrized arms + 2 controls) and `TestTheValueTypeIsImmutable` (1 parametrized + 3) |

Case-count arithmetic, measured: `-m ''` read 2580 passed before this plan, 2577 after Task 1 (−3), and 2563 after Task 2 (−14).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1's verify grep cannot pass as written**

- **Found during:** Task 1
- **Issue:** `test -z "$(grep -rn 'DeviceCheckAdapter' src tests)"` still prints three lines after the Protocol is gone. `tests/e2e/conftest.py:301` declares `class FakeDeviceCheckAdapter`, an e2e test double, and `:335` and `:504` name it. The Protocol name is a substring of that identifier, so a substring grep can never go quiet unless unrelated test code is renamed.
- **Fix:** Diagnosed to the identifier, then used a word-boundary grep: `grep -rnw 'DeviceCheckAdapter' src tests` exits 1 with no output, which is the property the must-have truth actually states ("no name of the DeviceCheck Protocol is left"). `FakeDeviceCheckAdapter` was NOT renamed — `tests/e2e/conftest.py` is not in this plan's file list, the double is not the Protocol, and "adapter" is a sanctioned codebase term.
- **Files modified:** none — this is a plan-text error, not a code defect.
- **Verification:** `grep -rnw 'DeviceCheckAdapter' src tests` → exit 1, no output.
- **Committed in:** no code change; recorded here.

**2. [Rule 3 - Blocking] Task 2's module-import grep matches a gitignored build artifact**

- **Found during:** Task 2
- **Issue:** `test -z "$(grep -rn 'nativespeaker.api.auth.adapters' src tests)"` matches `src/ns_api_gateway.egg-info/SOURCES.txt:14`, the editable install's stale file manifest. `git check-ignore` reports it covered by `.gitignore:7` (`*.egg-info/`) and `git ls-files` does not know it, so it is neither source nor tracked. 49-RESEARCH.md § Runtime State Inventory predicted a stale build artifact here.
- **Fix:** Scoped the check to tracked source: `git grep -n 'nativespeaker\.api\.auth\.adapters' -- src tests` prints nothing. The manifest is regenerated by the next build and was left alone rather than deleted.
- **Files modified:** none — this is a plan-text error, not a code defect.
- **Verification:** `git grep -n 'nativespeaker\.api\.auth\.adapters' -- src tests` → exit 1, no output.
- **Committed in:** no code change; recorded here.

**3. [Rule 3 - Blocking] Two unused imports after the guard class went**

- **Found during:** Task 1
- **Issue:** `TestTheSeamIsTheAnnotation` held the only `typing.` use and the only `inspect.` use in `tests/unit/test_devicecheck_adapter.py`, so deleting it left both imports unused and ruff's `F401` red.
- **Fix:** Dropped `import typing` and `import inspect`.
- **Files modified:** `tests/unit/test_devicecheck_adapter.py`
- **Verification:** `.venv/bin/ruff check src tests` → `All checks passed!`
- **Committed in:** `7fe6762` (part of the task commit)

---

**Total deviations:** 3 auto-fixed (all Rule 3, blocking).
**Impact on plan:** No scope creep. Two corrected the scope of the plan's own verify greps without touching code; the third cleared imports the deletion orphaned. Nothing the plan set out to do changed.

## Issues Encountered

- **The stated test baseline was stale, as 49-01 already reported.** The plan records `1 failed, 2572 passed` for `-m ''`. The measured count before any edit of this plan was `1 failed, 2580 passed`, which is where 49-01 left it. Plans 49-03 and 49-04 should measure against 2563, not 2572.

## Verification Results

Run from the repository root after both commits:

| Check | Result |
|---|---|
| `.venv/bin/pytest -q -m ''` | `1 failed, 2563 passed` — the failure is the pre-existing restore four-arms case and no other |
| `.venv/bin/pytest -q -m e2e` | `1 failed, 360 passed, 2203 deselected` — the same pre-existing case; the passed count matches the Phase 48 baseline |
| `.venv/bin/pytest -q -m schema` | `297 passed, 2267 deselected` — exit 0 |
| `.venv/bin/ruff check src tests` | `All checks passed!` |
| `git grep -nw -e 'DeviceCheckAdapter' -e 'FirebaseAdminAdapter' -- src tests` | exit 1 — neither name is left (see Deviation 1) |
| `git grep -nw -e 'PlaySubscriptionSource' -e 'TokenVerifier' -e 'DeviceCheckAdapter' -e 'FirebaseAdminAdapter' -- src tests` | exit 1 — all four Protocol names of this phase are absent |
| `test ! -e src/nativespeaker/api/auth/adapters.py` | exit 0 |
| `.venv/bin/ty check` | `Found 306 diagnostics` — the Phase 48 baseline, unmoved |

The e2e and schema suites were run with their own markers, because this task edits five files in those two suites.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or schema change.

- **T-49-04 (Tampering, the moved value type):** mitigated. `TestTheValueTypeIsImmutable` runs from `tests/unit/test_firebase_adapter.py` with all four cases and asserts frozen, slotted, no instance dict and the absent-email default.
- **T-49-05 (Elevation of Privilege, SDK isolation):** mitigated. `TestNoProviderDependency` walks all five surviving SDK-free auth modules in a subprocess, and its membership control names `jwt_verifier`, a module that exists.
- **T-49-06 (Spoofing, the retry helpers):** mitigated. `tests/unit/test_firebase_retry.py` and `tests/unit/test_devicecheck_adapter.py` are both green; only annotations changed.
- **T-49-07 (Repudiation, the retired WR-23 guard):** accepted, and the loss is recorded under Decisions Made and in the dropped-cases table.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The Protocol half of the phase is finished. 49-03 and 49-04 own `get_challenge_store`, the `ChallengesDB` constructor (D-01) and the remaining `dependencies.py` comments.
- `CURRENT` now reads `(7, 20, 60)`. Only a commit that changes the module, class or function count under `auth/` needs to move it again; 49-03 and 49-04 touch `crud/` and `app/`, so they may not need to.
- Two corrections for the remaining plans: scope a "name is gone" grep to tracked source and to word boundaries (`git grep -nw`), and the `-m ''` passed baseline is 2563.

## Self-Check: PASSED

- All nine surviving key files exist on disk; both deleted files are absent.
- Both commits exist: `7fe6762`, `65b1c91`, and `git log --stat` shows the two deletions in `65b1c91`.
- Every task acceptance criterion re-run and passing, with the two grep-scope corrections recorded as deviations.

---
*Phase: 49-delete-the-single-implementation-auth-protocols*
*Completed: 2026-09-17*
