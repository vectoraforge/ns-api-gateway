---
phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
plan: 02
subsystem: auth
tags: [lifespan, boot, google-auth, app-store, firebase, pytest]

requires:
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: the rebuild machinery plan 50-01 deleted, which made a `None` verifier ambiguous
  - phase: 44-post-webhooks-google-play-rtdn
    provides: the degraded-mode rule D-08 reverses for a failed warm-up
provides:
  - four builders that raise `RuntimeError` on a transient failure
  - "build_admin_apps(jwt: JWTConfig) — the narrowed signature D-07 asks for"
  - a `None` from a builder that now means one thing only, an absent setting
affects: [50-03, 50-04, 50-05, 50-06]

actuals:
  tokens: 5800
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Boot-fatal versus absent: the narrow `except` arm returns `None` and is written first, the wide arm raises `RuntimeError` naming the setting and the failure class"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/auth/firebase.py
    - tests/unit/test_config.py
    - tests/unit/test_google_play_notifications.py
    - tests/unit/test_firebase_adapter.py

key-decisions:
  - "Each `RuntimeError` message names the setting, the URL or the path and the failure class, never the file bytes or a credential"
  - "`_play_credential` is annotated `google.auth.credentials.Credentials | None`, with the module imported explicitly rather than relied on transitively"
  - "Two test names that said `yields_no_verifier` were renamed, not only the one the plan listed: the old names now describe the opposite of the rule"

patterns-established:
  - "A test name is part of the rule: when a builder's answer inverts, every case name that stated the old answer is renamed in the same commit"

requirements-completed: []

coverage:
  - id: D1
    description: "build_google_push_verifier raises on a JWKS warm-up failure and answers None only when the pins are absent"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestAJwksWarmUpFailureStopsTheBoot::test_the_builder_raises_and_stops_the_pod"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestAJwksWarmUpFailureStopsTheBoot::test_a_2xx_that_is_not_json_stops_the_pod_too"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestAJwksWarmUpFailureStopsTheBoot::test_an_unconfigured_value_answers_none_without_a_fetch"
        status: pass
    human_judgment: false
  - id: D2
    description: "_play_credential answers None only for DefaultCredentialsError and raises for every other GoogleAuthError"
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py#TestOnlyAnAbsentAdcCostsARouteAndAnyOtherFailureStopsTheBoot::test_a_badly_answered_read_stops_the_boot"
        status: pass
      - kind: unit
        ref: "tests/unit/test_config.py#TestOnlyAnAbsentAdcCostsARouteAndAnyOtherFailureStopsTheBoot::test_an_absent_credential_answers_none"
        status: pass
      - kind: unit
        ref: "tests/unit/test_config.py#TestOnlyAnAbsentAdcCostsARouteAndAnyOtherFailureStopsTheBoot::test_a_supplied_credential_is_returned_control"
        status: pass
    human_judgment: false
  - id: D3
    description: "build_app_store_verifier raises when a present root file cannot be read or parsed, and answers None for an absent setting"
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py#TestAnIncompleteConfigurationBootsAndAnUnusableRootDoesNot::test_a_root_that_is_not_a_der_certificate_stops_the_boot"
        status: pass
      - kind: unit
        ref: "tests/unit/test_config.py#TestAnIncompleteConfigurationBootsAndAnUnusableRootDoesNot::test_an_unopenable_root_stops_the_boot"
        status: pass
      - kind: unit
        ref: "tests/unit/test_config.py#TestAnIncompleteConfigurationBootsAndAnUnusableRootDoesNot::test_an_absent_root_certificate_yields_no_verifier"
        status: pass
    human_judgment: false
  - id: D4
    description: "_application_default_credential raises for every GoogleAuthError but absence, and build_admin_apps takes a JWTConfig"
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestBuildAdminApps::test_a_badly_answered_adc_read_stops_the_boot"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestBuildAdminApps::test_an_absent_credential_is_that_absent_state"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestBuildAdminApps::test_adc_yields_one_app_keyed_on_the_issuer"
        status: pass
    human_judgment: false
  - id: D5
    description: "Neither warm-up event name is logged anywhere, and no case asserts one"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn 'google_push_verifier_warm_up_failed\\|play_credential_warm_up_failed' src tests --include='*.py')\""
        status: pass
    human_judgment: false
  - id: D6
    description: "Every *_absent warning keeps its event name and its consequence text"
    verification:
      - kind: other
        ref: "git diff -U0 src/nativespeaker/api/{app/lifespan.py,auth/firebase.py} — no consequence line of a surviving warning is added or removed"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e"
        status: pass
    human_judgment: false

duration: 17 min
completed: 2026-09-18
status: complete
---

# Phase 50 Plan 02: A failed warm-up stops the pod Summary

**Four boot builders stopped swallowing a transient failure: each now raises `RuntimeError`, returns `None` only for an absent setting, and the two warm-up warnings are gone with the retry that justified them.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-09-18T07:56:00Z
- **Completed:** 2026-09-18T08:13:40Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `build_google_push_verifier` raises on a `PyJWTError` from the warm-up fetch. An absent pin still answers `None` without a fetch.
- `_play_credential` answers `None` for `DefaultCredentialsError` alone. `RefreshError`, `TransportError` and `MutualTLSChannelError` raise.
- `build_app_store_verifier` raises when the root file is present but cannot be read or parsed. An absent bundle id, environment, app id or path still answers `None`.
- `_application_default_credential` catches the absent arm only and raises the rest. Its docstring no longer promises that it never raises.
- `build_admin_apps` takes `jwt: JWTConfig`, so it reads the one block it uses. The lifespan passes `config.jwt`.
- Both warm-up warnings are deleted, with the `elif` arm that logged the push-verifier one and the cases that asserted them.
- In both new two-arm readers the narrow arm is written first, so the raise is reachable.

## Task Commits

1. **Task 1: the two Google builders in lifespan.py** - `512991c` (test, RED), `985aaa8` (feat, GREEN)
2. **Task 2: the App Store root file and the Firebase credential** - `8f658a3` (test, RED), `c3f3c15` (feat, GREEN)

## Files Created/Modified

- `src/nativespeaker/api/app/lifespan.py` - Three raising arms; the push-verifier `elif` warning arm deleted; `_play_credential` annotated `google.auth.credentials.Credentials | None`; `build_admin_apps(config.jwt)`.
- `src/nativespeaker/api/auth/firebase.py` - `_application_default_credential` gained the narrow-first `except` pair and a rewritten docstring; `build_admin_apps` takes `jwt: JWTConfig`; `JWTConfig` imported.
- `tests/unit/test_config.py` - Two classes renamed; two parametrize lists split; five cases now expect `RuntimeError`; the `play_credential_warm_up_failed` case deleted.
- `tests/unit/test_google_play_notifications.py` - `TestAJwksWarmUpFailureStopsTheBoot` with the two inverted cases; the absent-pin control unchanged.
- `tests/unit/test_firebase_adapter.py` - The four `build_admin_apps` call sites pass `StubConfig().jwt`; the four-way ADC parametrize split into an absent case and a raising one.

## Decisions Made

- Each `RuntimeError` names the setting, the URL or the configured path and the failure class, and nothing else. It never carries the file bytes, the credential or `DatabaseConfig.url`. This follows `_prove_database_reachable`.
- `_play_credential` is annotated `google.auth.credentials.Credentials | None`. `import google.auth.credentials` is added, because `import google.auth` alone does not promise the submodule.
- `_application_default_credential` keeps its return type. `google.auth.default()` is called for its raise only, and the value returned is a fresh `credentials.ApplicationDefault()`, as before.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Renamed one test the plan did not list**

- **Found during:** Task 2
- **Issue:** `test_an_unreadable_root_certificate_yields_no_verifier` uses a nonexistent path. Under the new rule "unreadable" is the case that raises, so the name stated the opposite of what the case measures.
- **Fix:** Renamed to `test_an_absent_root_certificate_yields_no_verifier`, with a one-line docstring saying `is_file()` is false. The assertion is unchanged, as the plan requires.
- **Files modified:** `tests/unit/test_config.py`
- **Verification:** `.venv/bin/pytest -q` exits 0.
- **Commit:** `8f658a3`

**2. [Rule 1 - Bug] Renamed the parametrized not-a-DER case too**

- **Found during:** Task 2
- **Issue:** The plan named the class and one case for renaming. `test_a_root_that_is_not_a_der_certificate_yields_no_verifier` also states the old answer, and it now expects a raise.
- **Fix:** Renamed to `test_a_root_that_is_not_a_der_certificate_stops_the_boot`.
- **Files modified:** `tests/unit/test_config.py`
- **Verification:** `.venv/bin/pytest -q` exits 0.
- **Commit:** `8f658a3`

---

**Total deviations:** 2 auto-fixed (2 naming bugs). **Impact on plan:** None on behavior. Both keep a test name and its assertion in agreement, which the plan asks for in the cases it did list.

## Issues Encountered

A first draft of the renamed class docstring in `tests/unit/test_config.py` ran to four lines, and `tests/unit/test_docstring_bar.py` failed on the `tests/unit` baseline of 0. The docstring was shortened to three lines before the commit. The baseline was not moved. Recorded because the gate fired and the cause was my own text, not the plan.

`tests/unit/test_auth_package_shape.py` needed no re-measure: this plan adds and removes no module, class or function in `auth/`, and `CURRENT` at `(7, 18, 58)` still measures.

## Operational note (threat T-50-02-03, accepted)

D-08 trades a degraded route for `CrashLoopBackOff`. If Google's metadata server or the JWKS endpoint is briefly unreachable at pod start, or a mounted root certificate is corrupt, the pod does not become Ready and Kubernetes restarts it. This is the intent of the rule. An operator who sees a boot loop should read the `RuntimeError` text: it names the setting, the URL or the file path that failed.

## Verification Results

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` | 1889 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m e2e` | 361 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m schema` | 297 passed, exit 0 |
| `.venv/bin/ruff check src tests` | All checks passed! |
| warm-up event name absence gate | empty, exit 0 |
| `_play_credential` arm order | `DefaultCredentialsError` at `lifespan.py:140`, `GoogleAuthError` at `:142` |
| `_application_default_credential` arm order | `DefaultCredentialsError` at `firebase.py:59`, `GoogleAuthError` at `:61` |
| `grep -c 'raise RuntimeError' src/.../lifespan.py` | 6 (4 or more required) |
| `grep -c 'def build_admin_apps(jwt: JWTConfig)'` | 1 |
| `grep -c 'google_play_configuration_absent'` | 1, text byte-identical |
| `grep -c 'firebase_admin_credential_absent'` | 1, text byte-identical |

The schema suite is not a plan verify command. It was run as a regression check.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ROADMAP criterion 8 is met in full. Plan 50-01 delivered the merge and the deleted rebuild machinery; this plan delivers the boot rule.
- A `None` from any of the four builders now has one meaning. Plan 50-03 can annotate the `Runtime` fields as `X | None` and know that `None` is an absent provider, never a failed read.
- `build_admin_apps` no longer takes the whole config, so the two remaining `config.*` reads in `auth/` are gone. D-07's other half, `build_firebase_adapter(jwt: JWTConfig)`, belongs to the plan that writes the builders.
- The three suites are 1889 / 361 / 297, all green. The unit count fell by 3 because four parametrized cases became two plus three, and one case was deleted.

## Self-Check: PASSED

- `src/nativespeaker/api/app/lifespan.py` — FOUND
- `src/nativespeaker/api/auth/firebase.py` — FOUND
- `tests/unit/test_config.py` — FOUND
- `tests/unit/test_google_play_notifications.py` — FOUND
- `tests/unit/test_firebase_adapter.py` — FOUND
- commit `512991c` — FOUND
- commit `985aaa8` — FOUND
- commit `8f658a3` — FOUND
- commit `c3f3c15` — FOUND
- Every `<acceptance_criteria>` of both tasks re-run after the last commit — PASS

---
*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Completed: 2026-09-18*
</content>
</invoke>
