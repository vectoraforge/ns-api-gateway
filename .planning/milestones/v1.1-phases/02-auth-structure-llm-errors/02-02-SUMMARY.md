---
phase: 02-auth-structure-llm-errors
plan: "02"
subsystem: exceptions
tags: [exceptions, llm-errors, retry, transient-error, error-handling]

dependency_graph:
  requires:
    - phase: 02-auth-structure-llm-errors plan 01
      provides: TransientLLMError/PermanentLLMError classes and HTTP handlers (stubbed)
  provides:
    - typed-llm-exceptions-with-cause-chain
    - _invoke-raises-typed-subtypes
  affects: [app/services.py, tests/unit/test_services.py]

tech_stack:
  added: []
  patterns:
    - "raise TypedError(str(e)) from e — typed exception subclasses carry __cause__ for introspection"
    - "patch _is_transient_error in tests to force transient/permanent path without mocking openai exceptions"

key_files:
  created: []
  modified:
    - app/services.py
    - tests/unit/test_services.py

key-decisions:
  - "_invoke raises PermanentLLMError for non-transient failures (no retry path) and TransientLLMError for retry exhaustion on transient errors — callers and handlers can now distinguish without inspecting __cause__"
  - "Fallback raise after loop (retry_max_attempts=0 edge case) typed as TransientLLMError for consistency"
  - "test_transient_llm_error_exhausted patches _is_transient_error to return True — avoids needing real openai exception types in unit tests"

patterns-established:
  - "Always carry __cause__ when re-raising at exception boundaries — enables debuggability without leaking internals to clients"

requirements-completed: [RETRY-01]

duration: ~5min
completed: 2026-02-26
---

# Phase 2 Plan 2: Typed LLM Errors with __cause__ Chain Summary

**_invoke raises TransientLLMError or PermanentLLMError (with __cause__) on retry exhaustion, replacing the generic AnalysisError raise.**

## Performance

- **Duration:** ~5 min
- **Completed:** 2026-02-26
- **Tasks:** 2 (Task 1 was pre-completed by 02-01 stub; Task 2 executed this plan)
- **Files modified:** 2

## Accomplishments

- `_invoke` now raises `PermanentLLMError(str(e)) from e` for non-transient LLM failures
- `_invoke` now raises `TransientLLMError(str(e)) from e` when retries exhausted on transient errors
- `test_llm_error` in both `TestAnalyze` and `TestChat` asserts typed exception + `__cause__` chain
- New `test_transient_llm_error_exhausted` verifies `TransientLLMError` path with `__cause__`
- 68 tests pass, 2 pre-existing config failures only (unchanged)

## Task Commits

1. **Task 1: Add TransientLLMError and PermanentLLMError (exceptions.py, errors.py)** — Pre-completed by 02-01 stub (commits: `1ef106e`, `14490bf`)
2. **Task 2: Update _invoke and test_services.py** — `f21e71a` (feat)

## Files Created/Modified

- `app/services.py` — Added `TransientLLMError`/`PermanentLLMError` imports; updated `_invoke` exception raises
- `tests/unit/test_services.py` — Added typed exception imports; updated `test_llm_error` assertions in TestAnalyze and TestChat; added `test_transient_llm_error_exhausted`

## Decisions Made

1. **Typed error selection in _invoke**: The condition `attempt >= retry_max_attempts or not _is_transient_error(e)` triggers early exit. Within that block, `_is_transient_error(e)` is re-evaluated to choose `TransientLLMError` vs `PermanentLLMError`. This keeps the logic explicit at the cost of one extra call (acceptable).

2. **Fallback after loop**: Changed `raise AnalysisError("LLM request failed")` to `raise TransientLLMError("LLM request failed after all retries")`. This line is only reachable if `retry_max_attempts == 0` (invalid config), but typing it consistently avoids a naked `AnalysisError` escape hatch.

3. **Test strategy for transient path**: Patches `app.services._is_transient_error` to return `True` rather than constructing actual openai exceptions. Cleaner and tests exactly the branching logic in `_invoke`.

## Deviations from Plan

None — plan executed exactly as written. Task 1 artifacts were already present from 02-01 stub; verified 21 handler tests pass before starting Task 2.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 2 complete: TokenVerifier protocol (02-01) and typed LLM errors (02-02) both done
- Phase 3 can proceed: resilience testing, circuit breaker, queue behavior
- Both `TransientLLMError` (503) and `PermanentLLMError` (502) are live in the exception handler chain

## Self-Check: PASSED

Files verified:
- `app/services.py` — FOUND, raises TransientLLMError/PermanentLLMError from _invoke
- `tests/unit/test_services.py` — FOUND, asserts typed exceptions and __cause__ chain

Commits verified:
- `f21e71a` — feat(02-02): raise TransientLLMError/PermanentLLMError from _invoke with __cause__

---
*Phase: 02-auth-structure-llm-errors*
*Completed: 2026-02-26*
