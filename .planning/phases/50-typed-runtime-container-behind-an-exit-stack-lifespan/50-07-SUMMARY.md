---
phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
plan: 07
subsystem: app
tags: [lifespan, boot, teardown, exit-stack, builders, pytest, ast]

requires:
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "`Runtime` and the one `app.state` write (50-03, 50-06)"
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "the boot rule: a builder returns `None` only for an absent setting (50-02)"
provides:
  - "one `AsyncExitStack` that owns every teardown in `lifespan.py`"
  - "five builders, each named after the `Runtime` field it fills"
  - "criteria 1, 2 and 3 as measurements in `tests/unit/test_app_wiring.py`"
  - "the phase gate: three marker runs, `ruff` and a re-read `ty` count"
affects: []

actuals:
  tokens: 5600
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A builder takes its config slice plus the stack when it owns a closeable, and registers the teardown at the moment of creation"
    - "A source-shape case pairs with a behavioural case: the AST proves the code is gone, the run proves the behaviour it described"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/app/lifespan.py
    - tests/unit/test_app_wiring.py

key-decisions:
  - "The stand-ins in the criterion-3 case register all three ways the real builders do: `callback`, `push_async_callback` and `enter_async_context`"
  - "The criterion-3 case records the `started` log too, so the order pins that the started line runs before the app serves"
  - "The three `ty` diagnostics the new AST helpers added were narrowed away, not recorded: they were my own unnarrowed `ast.expr` reads, not a pre-existing mismatch"

requirements-completed: []

coverage:
  - id: D1
    description: "One `AsyncExitStack` owns every teardown: no `try/finally` in `lifespan`, `dispose` registered before the reachability probe, the shutdown log registered first (criterion 1)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheStackOwnsEveryTeardown::test_the_module_builds_exactly_one_exit_stack"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheStackOwnsEveryTeardown::test_the_lifespan_holds_no_try_finally"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheStackOwnsEveryTeardown::test_dispose_is_registered_before_the_reachability_probe"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheStackOwnsEveryTeardown::test_the_shutdown_log_is_the_first_statement_of_the_stack"
        status: pass
      - kind: other
        ref: "throwaway: `push_async_callback` moved after the probe — the case failed with `assert 157 < 155`, then reverted"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each of the five `Runtime` fields has a builder of its own name, the two boot-fatal builders run first, and the three `*_absent` warnings are the only warnings (criterion 2, D-06)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheStackOwnsEveryTeardown::test_each_runtime_field_has_a_builder_of_its_own_name"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheStackOwnsEveryTeardown::test_the_two_boot_fatal_builders_run_before_the_degraded_tolerant_ones"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheStackOwnsEveryTeardown::test_the_only_warnings_are_the_three_absent_ones"
        status: pass
      - kind: unit
        ref: ".venv/bin/pytest -q -p no:cacheprovider tests/unit/test_config.py tests/unit/test_google_play_notifications.py — 218 passed, every kept builder still importable by name"
        status: pass
      - kind: other
        ref: "throwaway: `build_google_play_notifications` moved before `build_jwt_verifier` — the ordering case failed, then reverted"
        status: pass
    human_judgment: false
  - id: D3
    description: "`shutdown_step_failed` is logged nowhere, and a teardown that raises does not stop the callbacks still queued (criterion 3, T-50-07-01)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestATeardownThatRaisesStopsNoOtherTeardown::test_every_remaining_callback_runs_and_the_failure_propagates"
        status: pass
      - kind: other
        ref: "test -z \"$(grep -rn 'shutdown_step_failed' src tests --include='*.py')\" — exit 0"
        status: pass
      - kind: other
        ref: "throwaway: the recorder short-circuited after the raising teardown — the case failed at index 4, then reverted"
        status: pass
    human_judgment: false
  - id: D4
    description: "The phase gate: all three marker runs exit 0, `ruff` passes, and the `ty` count is re-read (criterion 7)"
    verification:
      - kind: unit
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m '' — 2567 passed, exit 0"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e — 361 passed, exit 0"
        status: pass
      - kind: schema
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m schema — 297 passed, exit 0"
        status: pass
      - kind: other
        ref: ".venv/bin/ruff check src tests — All checks passed!; .venv/bin/ty check — Found 297 diagnostics"
        status: pass
    human_judgment: false

duration: 17 min
completed: 2026-09-18
status: complete
---

# Phase 50 Plan 07: One exit stack, one builder per field Summary

**The lifespan body is now eight builder calls and one `Runtime(...)` inside a single `AsyncExitStack`, and the teardown order it relies on is measured by a run rather than asserted by an absence grep.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-09-18T09:09:24Z
- **Completed:** 2026-09-18T09:26:41Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Five builders join the four kept ones, each named after the `Runtime` field it fills: `build_session_factory`, `build_firebase_adapter`, `build_devicecheck_adapter`, `build_app_store_notifications` and `build_google_play_notifications`.
- `build_session_factory` registers `stack.push_async_callback(engine.dispose)` before it awaits `_prove_database_reachable`. A probe that raises still disposes the pool the engine opened.
- The `lifespan` body is one `async with AsyncExitStack() as stack:`. The shutdown log is registered first, so it runs last. `build_session_factory` and `build_jwt_verifier` run before the four degraded-tolerant builders.
- The `try`/`finally` block, the four resource locals and all four `shutdown_step_failed` log calls are deleted. `shutdown_step_failed` now appears nowhere in `src` or `tests`.
- Every `*_absent` warning moved into its builder with its event name and its consequence text byte-identical.
- `TestTheStackOwnsEveryTeardown` walks the `lifespan.py` AST for the four criterion-1 facts and the three criterion-2 facts, each against a literal written in the test file.
- `TestATeardownThatRaisesStopsNoOtherTeardown` drives the real `lifespan(app)` over recording stand-ins. One of them raises from its registered teardown.
- The unit suite rose from 1901 to 1909, which is the eight new cases and nothing else.

## Task Commits

1. **Task 1: one exit stack, one builder per field** — `08f06e2` (refactor)
2. **Task 2: the criteria 1, 2 and 3 cases** — `3cff783` (test)
3. **Task 3: the phase gate** — `e6279ca` (test, the type narrowing the gate found)

## Files Created/Modified

- `src/nativespeaker/api/app/lifespan.py` — five builders added; `AsyncExitStack` and `DeviceCheckConfig` imported; the lifespan body rewritten; the whole teardown block deleted.
- `tests/unit/test_app_wiring.py` — four AST helpers, one recording helper, two classes and eight cases.

## Decisions Made

- The criterion-3 stand-ins register their teardowns all three ways the real builders do: `stack.callback` for the Firebase delete, `stack.push_async_callback` for the engine dispose and the raising one, and `stack.enter_async_context` for the Play client. A case that used one kind would not measure the kind the other builders use.
- The recorder records the `started` log as well as the `shutdown` log, so the asserted order also pins that the started line runs before the app serves and that the shutdown line runs after every teardown.
- `build_app_store_notifications` takes no stack. It owns nothing closeable, and a stack parameter it never used would suggest it did.

## The teardown order, measured

The criterion-3 case asserts this exact list:

```
['started', 'serving', 'play_close', 'devicecheck_boom', 'firebase_delete', 'dispose', 'shutdown']
```

`devicecheck_boom` is the teardown that raises. Three callbacks registered before it still run, the shutdown log runs last, and the `RuntimeError` leaves the `async with` afterwards. That is what the deleted `shutdown_step_failed` handlers were written to provide, and the stack provides it without them.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Three `ty` diagnostics from the new AST helpers**

- **Found during:** Task 3, by the gate's own `ty check` run
- **Issue:** The count read 300 against the 297 plan 50-06 measured. All three were mine: `_warning_events` read `.value` off an `ast.expr` without narrowing, and the shutdown-log case passed an `expr` to `_dotted`, which declares `ast.Attribute`, then read `.value` off two more.
- **Fix:** `_warning_events` became a loop that narrows the first argument with `isinstance(event, ast.Constant)` before reading it. The shutdown-log case unpacks `call.args` into two names and narrows each one.
- **Files modified:** `tests/unit/test_app_wiring.py`
- **Verification:** `.venv/bin/ty check` re-read: 297 diagnostics. `.venv/bin/pytest -q tests/unit/test_app_wiring.py` — 55 passed.
- **Commit:** `e6279ca`

**2. [Rule 3 - Blocking] One docstring one character over the line limit**

- **Found during:** Task 1
- **Issue:** `build_google_play_notifications`'s docstring read 121 characters. `ruff` `E501` failed at a line length of 120.
- **Fix:** Shortened to "Google's push-token and subscription reader, degraded when this deployment supplies no credential."
- **Files modified:** `src/nativespeaker/api/app/lifespan.py`
- **Verification:** `.venv/bin/ruff check src tests` — All checks passed!
- **Commit:** `08f06e2`

---

**Total deviations:** 2 auto-fixed (1 annotation bug, 1 blocking lint failure). **Impact on plan:** none on the plan's goal. The `ty` fix keeps the count where plan 50-06 left it, so this plan adds no diagnostic.

## The `ty` measurement

| Reading | Count |
|---|---|
| RESEARCH.md HEAD baseline, before the phase | 295 |
| Measured after plan 50-06 (`50-06-SUMMARY.md`) | 297 |
| Measured after `e6279ca`, read from `.venv/bin/ty check` output in this run | **297** |
| Delta against the 295 baseline | **+2** |
| Delta against plan 50-06 | **0** |

The +2 against the baseline is plan 50-04's diagnostic and plan 50-06's `RestoreService.__init__` one, both recorded in their own summaries. This plan adds none.

## The one behaviour change that reaches production

D-08 turns four degraded-mode returns into a boot failure. `build_google_push_verifier`, `_play_credential`, `_application_default_credential` and `build_app_store_verifier` now raise `RuntimeError` when a read fails for a transient reason, and return `None` only when the setting is absent.

**What an operator sees.** A cluster whose Google metadata server or whose JWKS endpoint is briefly unreachable at pod start now gets `CrashLoopBackOff`. Before, the pod started and served 503 on two routes. Kubernetes restarting the pod is the retry, which is why the rebuild machinery is gone.

**What does not change.** A deployment that is genuinely not configured for a store still starts. The `*_absent` warning is logged, with the same text as before, and the two store routes refuse as they always did.

## ROADMAP check (D-11)

`.planning/ROADMAP.md` was read and not edited by this plan. `git status` reports it unmodified, and none of the three commits touches it. The Phase 50 entry already carries:

- the eight-field list, in build order, ending in `llm_service`
- criterion 5 naming `sign_out_all` and the clause that no other route declares `get_runtime`
- the goal's "keep every `*_absent` warning text unchanged" line, with the two warm-up warnings excepted
- criterion 8, stating the boot rule and the one Google Play class

## Issues Encountered

None beyond the two deviations above.

## Threat Notes

- **T-50-07-01** (a failing teardown swallowing a leaked client): measured, not assumed. The criterion-3 case proves the queued callbacks still run and the exception still propagates, so a leak cannot hide behind a swallowed error. The four `shutdown_step_failed` handlers that swallowed are deleted.
- **T-50-07-02** (a failed probe leaking a pool): `push_async_callback(engine.dispose)` sits at line 156 and the probe call at line 157. The line-order case fails if they swap, confirmed with a throwaway edit.
- **T-50-07-03** (`logger.info("started", ...)`): still names `config.model.name`, `config.resilience.pool_size` and the example language keys. Three scalars, never the container and never `config`. One inline comment beside the line records why.
- **T-50-07-04** (builder ordering): `build_session_factory` and `build_jwt_verifier` are the first two calls in the stack body. The ordering case fails if a degraded-tolerant builder moves ahead of them, confirmed with a throwaway edit.
- **T-50-07-SC**: no package was installed or upgraded. `uv.lock` is untouched.

## Verification Results

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider -m ''` | 2567 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m e2e` | 361 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m schema` | 297 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider` | 1909 passed, exit 0 |
| `.venv/bin/ruff check src tests` | All checks passed! |
| `.venv/bin/ty check` | Found 297 diagnostics, read from this run's own output |
| `test -z "$(grep -rn 'shutdown_step_failed' src tests --include='*.py')"` | exit 0, absent |
| `grep -c 'AsyncExitStack()' src/.../lifespan.py` | 1 |
| `grep -c 'try:' src/.../lifespan.py` | 5, all builder guard blocks (lines 65, 92, 105, 128, 140) |
| `grep -c 'finally:' src/.../lifespan.py` | 0 |
| `grep -c 'def build_' src/.../lifespan.py` | 9 — four kept plus five new |
| `grep -cE '\| None = None' src/.../lifespan.py` | 0 |
| `push_async_callback` vs `_prove_database_reachable` | line 156 before line 157 |
| `pytest tests/unit/test_app_wiring.py -k "<the two new classes>" --collect-only` | 8 cases |
| `git status --short .planning/ROADMAP.md` | empty, unmodified |
| `git diff --diff-filter=D --name-only HEAD~3 HEAD` | empty, no file deleted |

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ROADMAP criteria 1, 2, 3 and 7 are met and measured. With plans 50-01 to 50-06 the phase covers all eight.
- Criterion 7 reads green on all three suites. The Phase-47 restore case plan 50-01 fixed stays fixed.
- Open for a later phase, carried from plan 50-06: `RestoreService.__init__` annotates `package_name: str` where `GooglePlayConfig` supplies `str | None`. The path is safe at runtime; the annotation is not honest.
- The phase is executed but not verified. `/gsd:verify-phase 50` is what moves the completed-phase count.

## Self-Check: PASSED

- `src/nativespeaker/api/app/lifespan.py` — FOUND
- `tests/unit/test_app_wiring.py` — FOUND
- commit `08f06e2` — FOUND
- commit `3cff783` — FOUND
- commit `e6279ca` — FOUND
- Every `<acceptance_criteria>` of all three tasks re-run after the last commit — PASS
- The plan `<verification>` block re-run after the last commit — PASS

---
*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Completed: 2026-09-18*
