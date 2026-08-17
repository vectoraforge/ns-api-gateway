---
phase: 16-update-tests
plan: 04
subsystem: testing
tags: [pytest, cleanup, test-infrastructure]

# Dependency graph
requires:
  - phase: 16-update-tests
    plan: 02
    provides: e2e tests for health, root, prompts, examples endpoints
  - phase: 16-update-tests
    plan: 03
    provides: e2e tests for chat endpoints and lifecycle flow
provides:
  - Clean test tree with only tests/unit/ and tests/e2e/ directories
  - JWT test helpers consolidated in tests/unit/conftest.py
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JWT test helpers in unit conftest rather than separate module"

key-files:
  created: []
  modified:
    - tests/unit/conftest.py
    - tests/unit/test_jwt_security.py
    - tests/unit/test_exception_handlers.py
  deleted:
    - tests/integration/conftest.py
    - tests/integration/test_cross_user_isolation.py
    - tests/integration/test_health_endpoints.py
    - tests/integration/test_prompts_endpoints.py
    - tests/integration/test_root_endpoint.py
    - tests/llm/test_real_llm.py
    - tests/jwt_helpers.py

key-decisions:
  - "Migrated jwt_helpers into tests/unit/conftest.py since both test_jwt_security.py and test_exception_handlers.py need them"

patterns-established:
  - "All shared unit test utilities live in tests/unit/conftest.py"

requirements-completed: [E2E-CLEANUP]

# Metrics
duration: 2min
completed: 2026-03-17
---

# Phase 16 Plan 04: Old Test Cleanup Summary

**Removed tests/integration/, tests/llm/, and tests/jwt_helpers.py after migrating JWT helpers to unit conftest**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-17T07:47:18Z
- **Completed:** 2026-03-17T07:49:40Z
- **Tasks:** 2
- **Files modified:** 10 (3 modified, 7 deleted)

## Accomplishments
- Migrated JWT test infrastructure (ephemeral RSA keypair, make_token, make_test_verifier, _FixedKeyVerifier) from tests/jwt_helpers.py into tests/unit/conftest.py
- Updated imports in test_jwt_security.py and test_exception_handlers.py to reference new location
- Deleted tests/integration/ (5 files), tests/llm/ (1 file), and tests/jwt_helpers.py
- Test directory now contains only tests/conftest.py (minimal), tests/unit/, and tests/e2e/

## Task Commits

Each task was committed atomically:

1. **Task 2: Verify jwt_helpers.py is not imported by remaining tests** - `e3f65fe` (refactor)
2. **Task 1: Remove old test directories and verify** - `2847a5b` (chore)

_Note: Tasks executed in dependency order (Task 2 first to ensure safe deletion in Task 1)_

## Files Created/Modified
- `tests/unit/conftest.py` - Added JWT test infrastructure (keypair, make_token, make_test_verifier, _FixedKeyVerifier)
- `tests/unit/test_jwt_security.py` - Updated import from tests.unit.conftest
- `tests/unit/test_exception_handlers.py` - Updated import from tests.unit.conftest

## Files Deleted
- `tests/integration/conftest.py` - Old integration test fixtures
- `tests/integration/test_cross_user_isolation.py` - Replaced by e2e tests
- `tests/integration/test_health_endpoints.py` - Replaced by e2e tests
- `tests/integration/test_prompts_endpoints.py` - Replaced by e2e tests
- `tests/integration/test_root_endpoint.py` - Replaced by e2e tests
- `tests/llm/test_real_llm.py` - Replaced by e2e tests
- `tests/jwt_helpers.py` - Migrated to tests/unit/conftest.py

## Decisions Made
- Migrated jwt_helpers into tests/unit/conftest.py rather than creating a separate tests/unit/jwt_helpers.py module, since conftest.py already serves as the shared fixture/utility module for unit tests
- Executed Task 2 before Task 1 to ensure imports were updated before the source file was deleted

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_exception_handlers.py also imports jwt_helpers**
- **Found during:** Task 2 (jwt_helpers import check)
- **Issue:** Plan mentioned only test_jwt_security.py but test_exception_handlers.py also imports make_test_verifier and make_token from tests.jwt_helpers
- **Fix:** Updated import in test_exception_handlers.py alongside test_jwt_security.py
- **Files modified:** tests/unit/test_exception_handlers.py
- **Verification:** All 40 JWT/exception tests pass
- **Committed in:** e3f65fe (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix -- without updating the second file, deletion would have broken test_exception_handlers.py. No scope creep.

## Issues Encountered
- Pre-existing test failures in test_config.py and test_error_contract.py unrelated to this plan's changes (pydantic config and OpenAPI schema issues). Not addressed per scope boundary rules.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 16 test update is now complete (all 4 plans executed)
- Test tree is clean: tests/unit/ for mocked unit tests, tests/e2e/ for real-infrastructure end-to-end tests
- pyproject.toml correctly excludes llm and db markers from default pytest runs

## Self-Check: PASSED

All files confirmed present/deleted. All commits verified.

---
*Phase: 16-update-tests*
*Completed: 2026-03-17*
