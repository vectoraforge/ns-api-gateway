---
phase: 01-exception-foundation
plan: 03
subsystem: auth
tags: [fastapi, header, dependency, 401, pytest]

requires:
  - phase: 01-exception-foundation
    provides: MissingTokenError/InvalidTokenError handlers mapped to 401 (from 01-01, 01-02)
provides:
  - get_user_id dependency with optional Header(None) so FastAPI never intercepts missing auth header before dependency body
  - dep_client integration tests confirming end-to-end 401 for missing and malformed Authorization headers
affects: [any phase that adds routes protected by Depends(get_user_id)]

tech-stack:
  added: []
  patterns:
    - "Optional header pattern: str | None = Header(None) plus explicit None-guard raises domain error before FastAPI validation intercepts"
    - "dep_client fixture: module-scoped TestClient with real Depends(get_user_id) wired to minimal route for end-to-end auth path testing"

key-files:
  created: []
  modified:
    - app/auth.py
    - tests/unit/test_exception_handlers.py

key-decisions:
  - "Use str | None = Header(None) so FastAPI skips required-field enforcement; dependency body explicitly raises MissingTokenError when authorization is None"
  - "dep_client fixture is separate from handler_client — it exercises the full Depends() path, not just the exception handler in isolation"

patterns-established:
  - "Optional header + explicit None-guard: canonical way to make a required header return a domain 4xx rather than a framework 422"

requirements-completed: [EXCP-01]

duration: 5min
completed: 2026-02-26
---

# Phase 1 Plan 03: Exception Foundation Gap Closure Summary

**`str | None = Header(None)` fix in get_user_id converts missing Authorization header from 422 to 401, with three new dep_client tests confirming the full FastAPI dependency path**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-02-26T00:00:00Z
- **Completed:** 2026-02-26T00:05:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Fixed `get_user_id` to use `str | None = Header(None)` so FastAPI never raises `RequestValidationError` for a missing Authorization header before the dependency body runs
- Added explicit `if not authorization: raise MissingTokenError()` guard as the first line of the dependency body
- Added `dep_client` fixture and three tests exercising the real `Depends(get_user_id)` path: missing header → 401, invalid JWT → 401, valid JWT → 200 with correct user_id

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix get_user_id to use optional header** - `6648fcd` (fix)
2. **Task 2: Add missing-header integration test via real dependency** - `dc44489` (test)

## Files Created/Modified

- `app/auth.py` - Changed `Header(...)` to `Header(None)`, added None-guard raising MissingTokenError
- `tests/unit/test_exception_handlers.py` - Added `Depends` import, `dep_client` fixture, and three new tests

## Decisions Made

- `str | None = Header(None)` with an explicit None-guard is the canonical FastAPI pattern for turning a missing required header into a domain error rather than a 422. The existing `startswith("Bearer ")` check is retained as a secondary guard for non-None empty/malformed values.
- `dep_client` is kept separate from the existing `handler_client` fixture because it tests the full dependency injection chain, not just the exception handler wiring in isolation.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- UAT test 1 (missing Authorization header → 401) now passes
- All 35 tests pass (17 unit + 18 integration), no regressions
- Phase 1 gap closure complete; ready for Phase 2

---
*Phase: 01-exception-foundation*
*Completed: 2026-02-26*