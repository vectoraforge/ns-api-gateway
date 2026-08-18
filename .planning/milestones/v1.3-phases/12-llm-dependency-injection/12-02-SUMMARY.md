---
phase: 12-llm-dependency-injection
plan: 02
subsystem: testing
tags: [fastapi, dependency-injection, dependency-overrides, pytest]

# Dependency graph
requires:
  - phase: 12-llm-dependency-injection
    provides: app/dependencies.py with get_db, get_user_id, get_service, get_config
  - phase: 11-error-contract-hardening
    provides: Error contract with {"code": "..."} response shape
provides:
  - All test files using dependency_overrides instead of app.state assignments
  - service_instance fixture for DI-injected service access in tests
  - Test assertions aligned with Phase 11 error contract
affects: [13-endpoint-merge]

# Tech tracking
tech-stack:
  added: []
  patterns: [dependency-overrides-in-tests, service-instance-fixture]

key-files:
  created: []
  modified: [tests/conftest.py, tests/integration/conftest.py, tests/integration/test_prompts_endpoints.py, tests/unit/test_exception_handlers.py]

key-decisions:
  - "auth_token kept in integration conftest — cross-user isolation tests (db-marked) still need per-user JWT tokens"
  - "service_instance fixture retrieves service from dependency_overrides lambda — clean DI-based access"
  - "Test assertions updated to match Phase 11 error contract: code key instead of error key, 400 instead of 422 for validation"

patterns-established:
  - "DI test overrides: all test fixtures use dependency_overrides, never app.state assignments"
  - "service_instance fixture: tests mock service methods on the DI-provided instance, not app.state.service"

requirements-completed: [DI-01, DI-02, DI-03]

# Metrics
duration: 5min
completed: 2026-03-02
---

# Phase 12 Plan 02: Test DI Migration Summary

**Migrated all test fixtures to dependency_overrides, added service_instance fixture for mock injection, and fixed error contract assertion mismatches**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-02T23:01:45Z
- **Completed:** 2026-03-02T23:06:56Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Migrated `tests/conftest.py` to use `dependency_overrides` for get_db, get_config, get_user_id, get_service (zero `app.state.*` assignments)
- Migrated `tests/integration/conftest.py` to use `dependency_overrides` for all 4 dependencies
- Added `service_instance` fixture for clean DI-based service method mocking in test_prompts_endpoints.py
- Replaced all `client.app.state.service.*` mock patterns with `service_instance.*` across 11 test methods
- Updated `test_exception_handlers.py` import from `app.auth` to `app.dependencies`
- Fixed 6 pre-existing test assertion bugs from Phase 11 error contract change

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate conftest files to DI overrides** - `bdd46c6` (feat)
2. **Task 2: Migrate test mocks to service_instance and fix import** - `cdf9762` (feat)

## Files Created/Modified
- `tests/conftest.py` - Removed auth_header fixture, replaced app.state.* with dependency_overrides, added service_instance fixture
- `tests/integration/conftest.py` - Replaced app.state.* with dependency_overrides, kept auth_token for cross-user tests
- `tests/integration/test_prompts_endpoints.py` - All service mocks use service_instance, error assertions match Phase 11 contract
- `tests/unit/test_exception_handlers.py` - Import changed from app.auth to app.dependencies; verifier state tests unchanged

## Decisions Made
- Kept `auth_token` helper and `make_token` import in integration conftest because `test_cross_user_isolation.py` imports and uses `auth_token` for per-user JWT tokens. Removing it would break test collection even for non-db test runs.
- `service_instance` fixture retrieves the service by calling the `dependency_overrides[get_service]` lambda, ensuring tests mock on the exact same instance that routes receive.
- Fixed pre-existing error contract mismatches (Rule 1 bug): Phase 11 changed responses to `{"code": "..."}` and validation errors to 400, but test_prompts_endpoints.py still asserted `{"error": "..."}` and 422.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed 6 error contract assertion mismatches in test_prompts_endpoints.py**
- **Found during:** Task 2
- **Issue:** Phase 11 changed error responses from `{"status": N, "error": "..."}` to `{"code": "..."}` and validation errors from 422 to 400. Tests still asserted old shape.
- **Fix:** Updated 3 assertions from `response.json()["error"]` to `response.json()["code"]`; updated 3 assertions from `status_code == 422` to `status_code == 400`
- **Files modified:** tests/integration/test_prompts_endpoints.py
- **Verification:** All 100 non-db tests pass
- **Committed in:** cdf9762 (Task 2 commit)

**2. [Rule 3 - Blocking] Kept auth_token in integration conftest despite plan saying remove**
- **Found during:** Task 1
- **Issue:** Plan instructed to remove `auth_token` helper, but `test_cross_user_isolation.py` imports it. Removing would cause ImportError at test collection time, failing all tests.
- **Fix:** Kept `auth_token` function and `make_token` import. Removed `make_test_verifier` import (no longer used).
- **Files modified:** tests/integration/conftest.py
- **Verification:** pytest collection succeeds; all 100 non-db tests pass
- **Committed in:** bdd46c6 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for test suite to pass. Error contract mismatches were pre-existing from Phase 11. auth_token retention prevents breaking cross-user isolation tests. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All production code and tests fully migrated to Depends() pattern
- Zero `app.state.*` in test setup (except intentional verifier tests in test_exception_handlers.py)
- Phase 13 (endpoint merge) can proceed: DI infrastructure complete, tests exercise same DI graph as production
- Cross-user isolation tests (db-marked) will need separate fixture without get_user_id override when exercised with real DB

## Self-Check: PASSED

- FOUND: tests/conftest.py
- FOUND: tests/integration/conftest.py
- FOUND: tests/integration/test_prompts_endpoints.py
- FOUND: tests/unit/test_exception_handlers.py
- FOUND: 12-02-SUMMARY.md
- FOUND: commit bdd46c6 (Task 1)
- FOUND: commit cdf9762 (Task 2)

---
*Phase: 12-llm-dependency-injection*
*Completed: 2026-03-02*
