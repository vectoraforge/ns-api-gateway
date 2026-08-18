---
phase: 01-exception-foundation
plan: "02"
subsystem: testing
tags: [exceptions, pytest, parametrize, fastapi, testclient]

requires:
  - phase: 01-exception-foundation
    plan: "01"
    provides: [typed-exception-hierarchy, uniform-error-shape, register_exception_handlers]

provides:
  - parametrized-exception-handler-tests

affects: []

tech-stack:
  added: []
  patterns: [factory-closure-for-fastapi-test-routes, module-scoped-test-fixture]

key-files:
  created:
    - tests/unit/test_exception_handlers.py
  modified: []

key-decisions:
  - "Used add_api_route + factory closure (_make_raise_route) instead of default-arg trick — FastAPI treats exception instances with __init__ args as query parameters when used as defaults"

patterns-established:
  - "Factory closure pattern: def _make_raise_route(exc) -> async def _route(): raise exc — safe way to register per-exception test routes without FastAPI introspecting exception defaults"

requirements-completed:
  - EXCP-04

duration: ~2min
completed: 2026-02-25
---

# Phase 1 Plan 2: Exception Handler Parametrized Tests Summary

**14 parametrized tests covering all registered exception handlers via real FastAPI TestClient requests, asserting HTTP status and {"status", "error"} body shape**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-25T00:11:19Z
- **Completed:** 2026-02-25T00:13:21Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- 13 parametrized test cases covering every registered exception handler (MissingTokenError, InvalidTokenError, ExpiredTokenError, ChatOwnershipError, DatabaseNotInitializedError, UnsupportedLanguageError, InvalidChatError, QueueFullError, CircuitOpenError, ChatHistoryLimitError, MessageTooLargeError, generic Exception, StarletteHTTPException)
- 1 separate RequestValidationError test via POST with invalid Pydantic body
- Standalone `handler_client` module-scoped fixture (not reusing conftest `client`) with minimal FastAPI app
- All 14 tests pass; full suite 60 passed (2 pre-existing config test failures unrelated to this plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: Exception handler parametrized tests** - `8a8e50a` (test)

**Plan metadata:** (docs commit — see below)

_Note: TDD tasks may have multiple commits (test → feat → refactor). GREEN passed on first run since Plan 01 handlers were already complete._

## Files Created/Modified

- `tests/unit/test_exception_handlers.py` - Parametrized test suite for all registered exception handlers

## Decisions Made

- Used `add_api_route()` with a `_make_raise_route(exc)` factory closure instead of the `async def _route(e=exc_to_raise): raise e` default-arg pattern. FastAPI/Pydantic introspects default parameter values and tries to `deepcopy` them as query parameters — exceptions with required `__init__` args (e.g., `ChatHistoryLimitError(max_human, max_assistant)`) fail with `TypeError: __init__() missing argument`. The factory closure captures the exception instance in a proper closure scope that FastAPI does not introspect.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed FastAPI default-parameter introspection for exception instances**
- **Found during:** Task 1 (RED phase run)
- **Issue:** Plan's suggested `async def _route(e=exc_to_raise): raise e` pattern causes FastAPI to treat exception instances as query parameters. Pydantic tries to `deepcopy` and reconstruct them as field defaults, failing for exceptions with required `__init__` arguments (e.g., `MissingTokenError`, `ChatHistoryLimitError`, `MessageTooLargeError`, `UnsupportedLanguageError`, `StarletteHTTPException`)
- **Fix:** Replaced with `_make_raise_route(exc)` factory function + `app.add_api_route()` — closes over the exception without exposing it as a FastAPI parameter
- **Files modified:** `tests/unit/test_exception_handlers.py`
- **Verification:** All 14 tests pass
- **Committed in:** `8a8e50a` (task commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix necessary for correctness; no scope change.

## Issues Encountered

- FastAPI/Pydantic interaction: default parameter trick from plan's code snippet does not work when exception instances have required constructor arguments. Fixed via factory closure pattern.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All exception handlers are now covered by tests
- Phase 1 is complete — exception hierarchy, uniform error shape, and handler test coverage all in place
- Phase 2 can proceed with confidence that exception handling is correct and tested

## Self-Check: PASSED

Files verified:
- `tests/unit/test_exception_handlers.py` — FOUND, 83 lines, contains `pytest.mark.parametrize`, 14 test cases

Commits verified:
- `8a8e50a` — test(01-02): parametrized exception handler tests

---
*Phase: 01-exception-foundation*
*Completed: 2026-02-25*
