---
phase: 17-simplify-error-handling-in-errors-py-and-related-files
plan: 01
subsystem: api
tags: [fastapi, error-handling, exceptions, refactoring]

# Dependency graph
requires:
  - phase: 16-update-tests-to-reflect-the-current-codebase
    provides: unit tests for exception handlers and error contract
provides:
  - ServiceError subclasses with class-level HTTP metadata (status_code, error_code, log_level, extra_headers)
  - Single data-driven service_error_handler replacing 12 per-exception handlers
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Class-level HTTP metadata on exception hierarchy for data-driven error handling"
    - "Single handler reads exc.status_code/error_code/log_level/extra_headers() instead of per-exception functions"

key-files:
  created: []
  modified:
    - app/exceptions.py
    - app/api/errors.py

key-decisions:
  - "TransientLLMError and PermanentLLMError explicitly set log_level=None to override AnalysisError's logging.ERROR inheritance"
  - "service_error_handler uses assert isinstance for type narrowing, consistent with existing handler pattern"

patterns-established:
  - "Exception metadata pattern: new ServiceError subclasses only need class attributes, no handler registration"

requirements-completed: [ERR-SIMPLIFY-01, ERR-SIMPLIFY-02]

# Metrics
duration: 2min
completed: 2026-03-19
---

# Phase 17 Plan 01: Simplify Error Handling Summary

**Data-driven service_error_handler replaces 12 per-exception handlers using class-level HTTP metadata on ServiceError hierarchy**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-19T04:21:48Z
- **Completed:** 2026-03-19T04:23:52Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added status_code, error_code, log_level class attributes and extra_headers() method to all 12 ServiceError subclasses
- Replaced 12 individual handler functions with single data-driven service_error_handler (net -27 lines)
- All 84 unit tests pass unchanged, proving identical API behavior for all exception types

## Task Commits

Each task was committed atomically:

1. **Task 1: Add HTTP metadata to ServiceError hierarchy** - `039a6d8` (refactor)
2. **Task 2: Replace 12 handlers with single service_error_handler** - `1e3512e` (refactor)

## Files Created/Modified
- `app/exceptions.py` - Added import logging, class-level HTTP metadata (status_code, error_code, log_level) and extra_headers() to ServiceError base and all subclasses
- `app/api/errors.py` - Replaced 12 per-exception handler functions with single service_error_handler; 4 handler functions + 4 registrations instead of 15

## Decisions Made
- TransientLLMError and PermanentLLMError explicitly set log_level=None to prevent inheriting AnalysisError's logging.ERROR (matches current behavior where those handlers do not log)
- service_error_handler uses assert isinstance(exc, ServiceError) for type narrowing, consistent with existing queue_full_handler and circuit_open_handler pattern

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Error handling simplified; adding new exception types now only requires class attributes on the exception, no handler registration
- All tests green, ready for next phase

## Self-Check: PASSED

- FOUND: app/exceptions.py
- FOUND: app/api/errors.py
- FOUND: 039a6d8 (Task 1)
- FOUND: 1e3512e (Task 2)

---
*Phase: 17-simplify-error-handling-in-errors-py-and-related-files*
*Completed: 2026-03-19*
