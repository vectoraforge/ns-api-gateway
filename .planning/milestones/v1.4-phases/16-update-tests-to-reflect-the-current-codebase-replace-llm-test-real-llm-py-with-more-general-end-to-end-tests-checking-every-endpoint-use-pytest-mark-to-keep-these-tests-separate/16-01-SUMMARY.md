---
phase: 16-update-tests
plan: 01
subsystem: testing
tags: [pytest, conftest, fixtures, firebase, e2e, unit-tests]

# Dependency graph
requires:
  - phase: 15-refactor-chats
    provides: ChatService API surface and AIContent model
provides:
  - Isolated unit test fixtures in tests/unit/conftest.py
  - Real-infrastructure e2e fixtures in tests/e2e/conftest.py
  - Fixed ChatResponseLLM import bug (now uses AIContent)
affects: [16-02, 16-03, 16-04]

# Tech tracking
tech-stack:
  added: [httpx (e2e Firebase auth), PyJWT with crypto extras]
  patterns: [conftest-per-directory fixture isolation, session-scoped Firebase token, module-scoped TestClient]

key-files:
  created:
    - tests/unit/conftest.py
    - tests/e2e/conftest.py
    - tests/e2e/__init__.py
  modified:
    - tests/conftest.py
    - tests/unit/test_services.py

key-decisions:
  - "Conftest split: root conftest minimal (comments only), unit fixtures in tests/unit/conftest.py, e2e fixtures in tests/e2e/conftest.py"
  - "Firebase token at session scope (tokens last 1h, avoids redundant REST calls)"
  - "real_client at module scope with lifespan for safety"
  - "db_session at function scope with rollback for isolation"
  - "create_chat/cleanup_chat as module-level async helpers not fixtures for explicit control"

patterns-established:
  - "Conftest-per-directory: each test directory owns its fixtures"
  - "Session-scoped Firebase auth: single token per test run via REST API"

requirements-completed: [E2E-INFRA]

# Metrics
duration: 5min
completed: 2026-03-17
---

# Phase 16 Plan 01: Test Conftest Restructuring Summary

**Isolated unit/e2e test fixtures with conftest-per-directory pattern and fixed ChatResponseLLM import bug**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-17T07:34:02Z
- **Completed:** 2026-03-17T07:39:04Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Moved all mocked fixtures from root conftest to tests/unit/conftest.py for proper isolation
- Created tests/e2e/conftest.py with real Firebase token, real app TestClient, DB session, and seeding helpers
- Fixed broken ChatResponseLLM import in test_services.py (replaced with AIContent from app.models)
- Removed duplicate fixture definitions from test_services.py (now resolved via conftest)
- Root conftest.py reduced to comments-only (no fixtures, no imports)

## Task Commits

Each task was committed atomically:

1. **Task 1: Move mocked fixtures to tests/unit/conftest.py and fix ChatResponseLLM import** - `3452c04` (fix)
2. **Task 2: Create tests/e2e/conftest.py with real-infrastructure fixtures** - `5a83390` (feat)

## Files Created/Modified
- `tests/unit/conftest.py` - All mocked fixtures for unit tests (mock_config, mock_chats_db, service, client, service_instance)
- `tests/e2e/conftest.py` - Real-infrastructure fixtures (firebase_token, real_client, test_user_id, db_engine, db_session, create_chat, cleanup_chat)
- `tests/e2e/__init__.py` - Package marker
- `tests/conftest.py` - Minimal root conftest (comments only)
- `tests/unit/test_services.py` - Fixed ChatResponseLLM -> AIContent, removed duplicate fixtures

## Decisions Made
- Followed plan as specified for conftest split and fixture scoping
- Added __init__.py to tests/e2e/ for proper Python package import resolution

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing PyJWT[crypto] dependency**
- **Found during:** Task 1 (running unit tests)
- **Issue:** PyJWT and cryptography not installed in venv, causing ModuleNotFoundError on import
- **Fix:** Installed PyJWT[crypto] via uv pip
- **Files modified:** None (runtime dependency only, not added to pyproject.toml as it's a pre-existing gap)
- **Verification:** All 70 unit tests pass after install
- **Committed in:** N/A (runtime install only)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Dependency install necessary to run tests. No scope creep.

## Issues Encountered
- Pre-existing test failures in test_config.py (ValidationError for examples.path) and test_error_contract.py (test_openapi_schema_has_no_422) are unrelated to this plan's changes. Logged as out-of-scope.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- e2e conftest provides all fixtures needed for plans 16-02 through 16-04
- Unit test suite stable with proper fixture isolation
- Pre-existing test failures in test_config.py and test_error_contract.py should be addressed separately

## Self-Check: PASSED

All 5 files verified present. Both task commits (3452c04, 5a83390) verified in git log.

---
*Phase: 16-update-tests*
*Completed: 2026-03-17*
