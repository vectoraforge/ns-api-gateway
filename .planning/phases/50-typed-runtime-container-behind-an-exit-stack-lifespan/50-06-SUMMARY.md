---
phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
plan: 06
subsystem: app
tags: [runtime, dependencies, lifespan, webhooks, app-store, google-play, pytest, ast]

requires:
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "`Runtime`, `get_runtime` and `app.state.runtime` (50-03)"
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "the `dataclasses.replace` field-swap pattern for the e2e suite (50-04, 50-05)"
provides:
  - "`get_restore_service` and both webhook verifiers served off the container, with no `Request`"
  - "one `request.app.state` read in `dependencies.py` and one `app.state` write in the lifespan"
  - "criterion 5's counting clause and criterion 6, each measured in `tests/unit/test_app_wiring.py`"
affects: [50-07]

actuals:
  tokens: 51400
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A wiring case walks the `dependencies.py` AST and compares the count against a literal in the test file"
    - "A criterion that says `no test does X` carries a control case proving the walk still finds what it should"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/app/lifespan.py
    - tests/e2e/conftest.py
    - tests/e2e/test_quota.py
    - tests/e2e/test_challenge_store.py
    - tests/unit/test_app_wiring.py
    - tests/unit/test_app_store_notifications.py
    - tests/unit/test_google_play_notifications.py

key-decisions:
  - "`real_google_play_seam` saves the notifications field and the three config values as two names, because a container field cannot be restored by tuple unpacking"
  - "`_stub_runtime` keeps one `SimpleNamespace` for the config stand-in: `AppConfig` needs five unrelated required fields, and `make_runtime`'s `MagicMock` default is truthy where a case passes `None`"
  - "The `ty` count rose to 297 and no suppression was added; the new diagnostic is a real pre-existing annotation mismatch the typed container made visible"

requirements-completed: []

coverage:
  - id: D1
    description: "`dependencies.py` holds exactly one `request.app.state` read and it sits inside `get_runtime`; only `get_runtime` and `get_claims` declare a `Request` (criterion 5, D-01)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheContainerIsTheOneUntypedRead::test_the_module_holds_exactly_one_app_state_chain"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheContainerIsTheOneUntypedRead::test_the_one_chain_sits_inside_get_runtime"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheContainerIsTheOneUntypedRead::test_only_those_two_functions_declare_a_request"
        status: pass
      - kind: other
        ref: "throwaway `request.app.state.runtime` read added to `get_sync_service` — all three cases failed, then reverted"
        status: pass
    human_judgment: false
  - id: D2
    description: "The lifespan writes exactly one `app.state` attribute, the container, built from the eight locals in field order (criterion 4, D-02)"
    verification:
      - kind: other
        ref: "test \"$(grep -cE '^\\s+app\\.state\\.' src/nativespeaker/api/app/lifespan.py)\" = 1 — exit 0, the one line is `app.state.runtime`"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e — 361 passed against the real lifespan"
        status: pass
    human_judgment: false
  - id: D3
    description: "No test sets a lifespan-built attribute on `app.state`, and `opened_sessions` stays as it is (criterion 6)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestNoTestSetsALifespanAttributeOnAppState::test_no_container_field_is_assigned_through_state"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestNoTestSetsALifespanAttributeOnAppState::test_opened_sessions_is_still_assigned_that_way_control"
        status: pass
      - kind: other
        ref: "throwaway `app.state.jwt_verifier = verifier` added to `test_jwks_offload.py` — the case failed naming the file and line, then reverted"
        status: pass
    human_judgment: false
  - id: D4
    description: "`get_restore_service`, `verify_app_store_notification` and `verify_google_play_notification` reach both store classes through `Depends(get_runtime)`, keeping their refusal ordering (T-50-06-01, T-50-06-02)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheProviderCallbackPartition::test_the_verifier_resolves_before_any_session_is_taken"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py — the token, decode and package-comparison cases over `_stub_runtime`"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e — 361 passed"
        status: pass
    human_judgment: false
  - id: D5
    description: "`_stub_request` is gone: the Play dependency is called with a `Runtime` built through `make_runtime`, not a nested request stub (D-09)"
    verification:
      - kind: other
        ref: "grep -n '_stub_request' tests/unit/test_google_play_notifications.py — no match"
        status: pass
      - kind: unit
        ref: ".venv/bin/pytest -q -p no:cacheprovider tests/unit/test_google_play_notifications.py — passed inside the 1901-case unit run"
        status: pass
    human_judgment: false

duration: 13 min
completed: 2026-09-18
status: complete
---

# Phase 50 Plan 06: The store classes move into the container Summary

**The lifespan now writes one attribute and `dependencies.py` reads one, and both counts are measurements rather than claims.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-09-18T08:52:43Z
- **Completed:** 2026-09-18T09:06:04Z
- **Tasks:** 3
- **Files created or modified:** 8

## Accomplishments

- `get_restore_service` drops `Request` and takes the container, passing `runtime.app_store_notifications`, `runtime.google_play_notifications` and `runtime.config.google_play.package_name`.
- `verify_app_store_notification` and `verify_google_play_notification` drop `Request` and take the container. Both keep their ordering: the token or envelope check first, the body decode after, the package comparison before the Play call.
- `dependencies.py` holds one `request.app.state` expression, in `get_runtime`. `get_claims` keeps its `Request` for the authorization header alone.
- The lifespan drops `app.state.config`, `app.state.app_store_notifications`, `app.state.google_play_notifications` and `app.state.llm_service`. It assigns `app.state` once, immediately before `yield`.
- The two App Store and three Play fixtures in `tests/e2e/conftest.py` save the field, replace the field and restore the field. `scripted_google_play` and `real_google_play_seam` read `runtime.config.google_play` and mutate it in place, because the config object is shared with the container.
- `_stub_request` becomes `_stub_runtime` and returns a real `Runtime` through `make_runtime`. The dependency takes the container as a parameter, so `_verify` passes it directly.
- Two new classes in `tests/unit/test_app_wiring.py` measure criteria 5 and 6. The unit suite rose from 1896 to 1901.

## Task Commits

1. **Task 1: the store seams move, and the lifespan writes one attribute** — `254720c` (refactor)
2. **Task 2: the criterion 5 counting case** — `910444e` (test)
3. **Task 3: the criterion 6 case** — `7776763` (test)

## Files Created/Modified

- `src/nativespeaker/api/app/dependencies.py` — three signatures rewritten; the `Request` comment on `get_restore_service` deleted; seven `request.app.state` reads became container fields.
- `src/nativespeaker/api/app/lifespan.py` — four `app.state` assignments deleted. All four locals stay and feed the one `Runtime(...)` call.
- `tests/e2e/conftest.py` — five fixtures swap the container field with `dataclasses.replace`.
- `tests/e2e/test_quota.py`, `tests/e2e/test_challenge_store.py` — five reads now go through `state.runtime`.
- `tests/unit/test_app_wiring.py` — `_dotted`, `_dependency_functions`, `_app_state_chains`, `_assignment_targets` and `_state_assignments`, plus the two new classes, five cases.
- `tests/unit/test_google_play_notifications.py` — `_stub_request` replaced by `_stub_runtime`; `_verify` passes the container.
- `tests/unit/test_app_store_notifications.py` — one docstring no longer says the class lives on `app.state`.

## Decisions Made

- `real_google_play_seam` saved one tuple of four values and restored it by unpacking. A container field cannot be an unpacking target, so the save is now two names: the notifications field, and the three config values the fixture mutates in place. The config values are restored first, then the field.
- `_stub_runtime` passes `config=SimpleNamespace(google_play=GooglePlayConfig(package_name=package_name))`. `make_runtime` defaults `config` to a `MagicMock`, whose `package_name` would be truthy, and three cases in that file pass `None` or `""` on purpose. A real `AppConfig` needs `openai`, `db`, `jwt`, `prompt` and `examples`, none of which the dependency reads.
- The criterion 6 walk reads its field names from `dataclasses.fields(Runtime)` and flattens tuple targets, because the fixture this plan rewrote assigned through a tuple until Task 1.
- No `ty` suppression was added for the one new diagnostic. See below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two e2e test files read attributes the lifespan stops setting**

- **Found during:** Task 1
- **Issue:** The plan lists `tests/e2e/conftest.py` alone, but `tests/e2e/test_quota.py:370, 371, 381, 394, 395, 403, 413` and `tests/e2e/test_challenge_store.py:83` also read `_app_lifespan.state.config` and `_app_lifespan.state.llm_service`. Task 1 deletes both assignments from the lifespan, so all eight reads would raise `AttributeError`. Plan 50-05's own readiness note predicted this.
- **Fix:** The five config reads and the one LLM read became `state.runtime.config` and `state.runtime.llm_service`. The two quota cases still mutate `chats_limit` and `messages_limit` in place and restore them, because the config object is the one the container holds.
- **Files modified:** `tests/e2e/test_quota.py`, `tests/e2e/test_challenge_store.py`
- **Verification:** `.venv/bin/pytest -q -p no:cacheprovider -m e2e` — 361 passed, exit 0.
- **Commit:** `254720c`

### One acceptance criterion is reported as written, not as passed

Task 1 asks that `grep -c 'SimpleNamespace' tests/unit/test_google_play_notifications.py` be 0. It counts 3: the import at line 11, the config stand-in inside `_stub_runtime` at line 329, and `_RecordingSession.request` at line 732.

Line 732 is not this plan's subject. It returns a `requests`-shaped response double for `TestTheCredentialRefreshIsCapped`, which measures the refresh timeout and never touches `app.state`. Rewriting it would be a change to an unrelated case.

The criterion's subject, named in the plan's own artifacts list as "the `SimpleNamespace` request stub", is gone: `_stub_request` no longer exists, the `app=SimpleNamespace(state=...)` nesting is gone, and `grep -n '_stub_request'` returns nothing. The task action states the operative rule — "Drop the `SimpleNamespace` import if nothing else in the file uses it" — and something else does use it, so the import stays.

---

**Total deviations:** 1 auto-fixed (1 blocking), plus one acceptance criterion reported with its measurement above. **Impact on plan:** none on the plan's goal. The e2e fix is what lets the `-m e2e` gate pass at all.

## The `ty` measurement

| Reading | Count |
|---|---|
| Measured after plan 50-05 (`50-05-SUMMARY.md`) | 296 |
| Measured after `7776763`, read from `.venv/bin/ty check` output | **297** |
| Delta | **+1** |

The one new diagnostic is at `dependencies.py:124`: `RestoreService.__init__` declares `package_name: str`, and `GooglePlayConfig.package_name` is `str | None`. The mismatch is not new; the read was `request.app.state.config.google_play.package_name`, which `ty` cannot type, so it was invisible. A typed container made it visible.

It is a latent weakness, not a live failure. `RestoreService` passes the value to `play.read_for_restore`, and an unconfigured deployment refuses there with `Unavailable` before the package name is used. Widening the annotation to `str | None` would move the same mismatch into `read_for_restore`, which is a service and adapter change this plan's scope does not cover. No suppression was written: the repository does not suppress this rule, and hiding a newly visible real mismatch to hold a number is the opposite of what the count is for. Recorded here for a later phase.

## Issues Encountered

None beyond the deviation above. The unit suite rose from 1896 to 1901, which is the five new cases and nothing else. The e2e count is 361 and the schema count is 297, both unchanged since plan 50-04.

## Threat Notes

- **T-50-06-01** (spoofing at both webhook verifiers): both stay the route's first declared dependency and both still resolve before `get_db`. `test_the_verifier_is_the_routes_first_declared_dependency` and `test_the_verifier_resolves_before_any_session_is_taken` pass for both paths. `get_runtime` performs one attribute read and no I/O, so the refusal path costs nothing more than before.
- **T-50-06-02** (tampering through reordering in `verify_google_play_notification`): the `credential is None` raise is still the first statement, `developer_notification_from` still runs after the token check, and the package comparison still precedes the Play call. The body is carried over line for line with `request.app.state.*` replaced by `runtime.*`. `tests/unit/test_google_play_notifications.py` covers each arm.
- **T-50-06-03** (the whole config reachable from any dependency): accepted as planned. `TestOnlyTheSignOutRouteReachesTheContainer` from plan 50-05 still passes, so no route declares the container except the revocation route, and the new counting case pins that only two functions can reach `app.state` at all.
- **T-50-06-SC**: no package was installed or upgraded. `uv.lock` is untouched.

## Verification Results

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` | 1901 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m e2e` | 361 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m schema` | 297 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m ''` | 2559 passed, exit 0 |
| `.venv/bin/ruff check src tests` | All checks passed! |
| `.venv/bin/ty check` | Found 297 diagnostics, read from this run's own output |
| `test "$(grep -c 'request.app.state' src/nativespeaker/api/app/dependencies.py)" = 1` | exit 0 |
| `test "$(grep -cE '^\s+app\.state\.' src/nativespeaker/api/app/lifespan.py)" = 1` | exit 0, the line is `app.state.runtime` |
| `grep -n 'request' src/nativespeaker/api/app/dependencies.py` | `get_runtime` and `get_claims` only |
| `grep -c 'SimpleNamespace' tests/unit/test_google_play_notifications.py` | 3 — see the deviation above |
| `.venv/bin/pytest tests/unit/test_app_wiring.py -k TestTheContainerIsTheOneUntypedRead --collect-only` | 3 cases |
| `.venv/bin/pytest tests/unit/test_app_wiring.py -k TestNoTestSetsALifespanAttributeOnAppState --collect-only` | 2 cases |
| `git diff --diff-filter=D --name-only HEAD~3 HEAD` | empty, no file deleted |

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Criterion 5 is complete and measured in three ways: the count, the enclosing function, and the `Request`-declaring set.
- Criterion 6 is complete and measured, with a control case so a walk that found nothing cannot pass silently.
- Criterion 4's "exactly one attribute" clause is now true of the lifespan as well as of `Runtime`; plan 50-07 can assert it against the running app rather than against the source.
- Open for a later phase: `RestoreService.__init__` annotates `package_name: str` where the config supplies `str | None`. The path is safe at runtime; the annotation is not honest.

## Self-Check: PASSED

- `src/nativespeaker/api/app/dependencies.py` — FOUND
- `src/nativespeaker/api/app/lifespan.py` — FOUND
- `tests/e2e/conftest.py` — FOUND
- `tests/e2e/test_quota.py` — FOUND
- `tests/e2e/test_challenge_store.py` — FOUND
- `tests/unit/test_app_wiring.py` — FOUND
- `tests/unit/test_app_store_notifications.py` — FOUND
- `tests/unit/test_google_play_notifications.py` — FOUND
- commit `254720c` — FOUND
- commit `910444e` — FOUND
- commit `7776763` — FOUND
- All three tasks' `<acceptance_criteria>` re-run after the commits — PASS, with the one SimpleNamespace criterion reported above
- The plan `<verification>` block re-run after the commits — PASS

---
*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Completed: 2026-09-18*
