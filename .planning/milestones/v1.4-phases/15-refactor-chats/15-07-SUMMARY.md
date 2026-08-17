---
phase: 15-refactor-chats
plan: 07
subsystem: api
tags: [ty, type-checking, fastapi, starlette, sqlalchemy]

# Dependency graph
requires:
  - phase: 15-refactor-chats/05
    provides: "Flattened module structure with app/api/errors.py, app/api/dependencies.py"
provides:
  - "Type-correct exception handler signatures in app/api/errors.py"
  - "Type-ignore annotations for FastAPI Depends pattern in app/api/dependencies.py"
  - "Type-ignore annotation for SQLAlchemy selectinload in app/database.py"
affects: [15-refactor-chats/08]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Exception base type in handler signatures with assert isinstance for narrowing"]

key-files:
  created: []
  modified:
    - app/api/errors.py
    - app/api/dependencies.py
    - app/database.py

key-decisions:
  - "Widen handler exc param to Exception with assert isinstance for attribute access rather than type: ignore on registrations"
  - "Use type: ignore for FastAPI Depends and SQLAlchemy selectinload framework patterns that ty cannot resolve"

patterns-established:
  - "Exception handler pattern: accept Exception, assert isinstance for attribute access"
  - "Framework DI pattern: type: ignore[invalid-parameter-default] for FastAPI Depends"

requirements-completed: [REFACT-03, REFACT-05, REFACT-06]

# Metrics
duration: 3min
completed: 2026-03-16
---

# Phase 15 Plan 07: Fix ty Errors Summary

**Eliminated 18 ty type-check errors across errors.py, dependencies.py, and database.py using widened handler signatures and targeted type: ignore**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-16T21:51:35Z
- **Completed:** 2026-03-16T21:55:23Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Fixed 15 ty errors in app/api/errors.py by widening handler signatures to accept Exception base type
- Fixed 2 ty errors in app/api/dependencies.py for FastAPI Depends() default parameter pattern
- Fixed 1 ty error in app/database.py for SQLAlchemy selectinload relationship argument
- Total ty errors reduced from ~52 to 5 (remaining errors in test files, addressed by plan 08)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix type errors in app/api/errors.py** - `5b0d528` (fix)
2. **Task 2: Fix type errors in app/api/dependencies.py and app/database.py** - `66bf318` (fix)

## Files Created/Modified
- `app/api/errors.py` - Widened 14 handler signatures to exc: Exception, added assert isinstance for 3 handlers needing attribute access, added type: ignore on _CODE_MAP lookup
- `app/api/dependencies.py` - Added type: ignore for Depends() default parameter pattern (2 lines)
- `app/database.py` - Added type: ignore for selectinload relationship argument

## Decisions Made
- Used assert isinstance narrowing rather than type: ignore on add_exception_handler registrations -- preserves runtime safety while satisfying type checker
- Used type: ignore for framework patterns (FastAPI Depends, SQLAlchemy selectinload) where the type mismatch is inherent to the framework API

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 5 remaining ty errors are in test files, addressed by plan 08
- All 82 unit tests passing
- Ruff check clean across entire project

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 15-refactor-chats*
*Completed: 2026-03-16*
