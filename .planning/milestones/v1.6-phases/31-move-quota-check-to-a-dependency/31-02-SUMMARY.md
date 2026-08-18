---
phase: 31-move-quota-check-to-a-dependency
plan: 02
subsystem: testing
tags: [pytest, fastapi, dependency-injection, quota, unit-tests]

# Dependency graph
requires:
  - phase: 31-move-quota-check-to-a-dependency
    plan: 01
    provides: "require_quota dependency and quota-free ChatService"
provides:
  - "Unit tests verifying require_quota dependency directly"
  - "HTTP integration tests verifying 429 via dependency override"
  - "ChatService test fixtures free of quota/usage mocking"
affects: [testing, chat-routes]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Direct async dependency invocation in unit tests (bypass FastAPI DI)", "dependency_overrides[require_quota] for HTTP-level quota testing"]

key-files:
  created: []
  modified:
    - tests/unit/conftest.py
    - tests/unit/test_usage.py

key-decisions:
  - "Retained patch.object for users_module.UsageDB in client fixture (GET /users/me creates UsageDB directly, not via DI)"
  - "Used patch.object(dep_module, 'UsageDB') per CLAUDE.md -- no string-based module references in tests"
  - "Error response field is 'code' not 'error_code' (matches ErrorResponse schema)"

patterns-established:
  - "Test require_quota by calling it directly with mock user/db/config (no FastAPI test client needed)"
  - "Override require_quota in HTTP tests via dependency_overrides to test quota enforcement at route level"

requirements-completed: [DEP-01, DEP-02, DEP-03, DEP-04, DEP-05, DEP-06]

# Metrics
duration: 5min
completed: 2026-03-25
---

# Phase 31 Plan 02: Update Unit Tests for Quota Dependency Summary

**Rewrote quota tests to target require_quota dependency directly with 9 tests passing, ChatService fixtures stripped of quota logic**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-25T08:38:10Z
- **Completed:** 2026-03-25T08:43:24Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Rewrote `test_usage.py` with `TestRequireQuota` (4 direct unit tests) and `TestQuotaViaHTTP` (2 HTTP integration tests) replacing old `TestChatServiceQuota`
- Updated `service` fixture to create ChatService with 5 kwargs only (no quotas, no usage_db)
- Added `require_quota` no-op override in `client` fixture via `dependency_overrides`
- Full unit suite passes: 148 tests, 0 failures across all test files

## Task Commits

Each task was committed atomically:

1. **Task 1: Update conftest.py fixtures for new ChatService signature and require_quota override** - `c64d38a` (refactor)
2. **Task 2: Rewrite test_usage.py to test require_quota dependency directly** - `9debc65` (test)
3. **Task 3: Clean test_services.py and verify full suite green** - `66536f9` (fix)

## Files Created/Modified
- `tests/unit/conftest.py` - Removed quotas/usage_db from service fixture; added require_quota override and scoped UsageDB patch to users router in client fixture
- `tests/unit/test_usage.py` - Replaced TestChatServiceQuota with TestRequireQuota (direct invocation) and TestQuotaViaHTTP (HTTP integration); all patch calls use patch.object

## Decisions Made
- Retained `patch.object(users_module, "UsageDB")` in client fixture because `GET /users/me` creates UsageDB directly in the route handler (not via FastAPI DI). This is a users router concern, not quota enforcement.
- Used `patch.object(dep_module, "UsageDB")` in test_usage.py per CLAUDE.md prohibition on string-based module references in tests.
- Fixed error response assertion from `error_code` to `code` to match the actual `ErrorResponse` schema.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed error response field name in HTTP quota tests**
- **Found during:** Task 2 (test_usage.py rewrite)
- **Issue:** Plan specified `response.json()["error_code"]` but ErrorResponse schema uses `code` field
- **Fix:** Changed assertions to use `response.json()["code"]`
- **Files modified:** tests/unit/test_usage.py
- **Verification:** Both HTTP tests pass with correct assertion
- **Committed in:** 9debc65

**2. [Rule 3 - Blocking] Restored UsageDB mock for users router in client fixture**
- **Found during:** Task 3 (full suite verification)
- **Issue:** Removing patch.object entirely broke `GET /users/me` tests -- the users router creates UsageDB(db) directly in the handler, and MagicMock session is not awaitable
- **Fix:** Re-added scoped `patch.object(users_module, "UsageDB")` in client fixture with comment explaining it serves the users router, not quota enforcement
- **Files modified:** tests/unit/conftest.py
- **Verification:** All 148 unit tests pass including test_users.py
- **Committed in:** 66536f9

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 31 is fully complete: production code refactored (Plan 01) and all tests updated (Plan 02)
- Quota enforcement verified at both dependency level and HTTP level
- ChatService is single-responsibility (no quota logic)
- 148 unit tests passing with zero failures

## Known Stubs
None -- all data paths are fully wired.

## Self-Check: PASSED
