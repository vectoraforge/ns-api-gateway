---
phase: quick
plan: 260317-waa
subsystem: testing
tags: [asyncpg, pydantic-settings, sqlalchemy, e2e, config]

requires:
  - phase: 260317-nbq
    provides: api_key field on JWTConfig and config.yaml
provides:
  - Working e2e test suite (18 tests passing against real Postgres and Firebase)
  - DatabaseConfig.connect_args property for asyncpg server_settings
  - AppConfig env_nested_max_split=1 for correct JWT_API_KEY env var resolution
affects: [e2e-tests, config, database]

tech-stack:
  added: []
  patterns:
    - "connect_args with server_settings for asyncpg search_path instead of URL options param"
    - "env_nested_max_split=1 on leaf BaseSettings subclass, not base class"
    - "Separate engine per async fixture to avoid TestClient event-loop mismatch"

key-files:
  created: []
  modified:
    - app/config.py
    - app/api/main.py
    - config/config.yaml
    - tests/e2e/conftest.py

key-decisions:
  - "connect_args with server_settings for asyncpg schema selection instead of URL ?options= (asyncpg rejects options kwarg via SQLAlchemy)"
  - "env_nested_max_split=1 on AppConfig directly, not BaseConfig (pydantic-settings metaclass resets inherited SettingsConfigDict)"
  - "Remove api_key from config.yaml so JWT_API_KEY env var is picked up by pydantic-settings"
  - "db_session fixture creates its own engine to avoid event-loop conflict with TestClient"
  - "ensure_tables drops and recreates to ensure FK cascades match current models"

patterns-established:
  - "connect_args property on DatabaseConfig: callers pass config.db.connect_args to create_async_engine"
  - "Async test fixtures that need DB access must create their own engine, not reuse the app's session factory"

requirements-completed: []

duration: 6min
completed: 2026-03-17
---

# Quick Task 260317-waa: Fix E2E Tests Summary

**Fix asyncpg connect_args, JWT env var resolution, and e2e conftest event-loop/FK issues for all 18 e2e tests**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-18T06:24:30Z
- **Completed:** 2026-03-18T06:30:53Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Fixed asyncpg connect() TypeError by moving search_path from URL ?options= to connect_args server_settings
- Fixed JWT_API_KEY env var being ignored due to YAML empty string override and missing env_nested_max_split
- Fixed e2e conftest db_session event-loop mismatch and stale FK cascade
- All 82 unit tests and 18 e2e tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Revert uncommitted changes and fix all config/engine bugs** - `96eff5e` (fix)
2. **Task 2: Run e2e tests to confirm full fix** - `ac09f8e` (fix)

## Files Created/Modified
- `app/config.py` - DatabaseConfig.connect_args property, AppConfig env_nested_max_split=1
- `app/api/main.py` - Pass connect_args to create_async_engine in lifespan
- `config/config.yaml` - Removed api_key from jwt section
- `tests/e2e/conftest.py` - Own engine in db_session, drop+create in ensure_tables, explicit message delete in cleanup

## Decisions Made
- Used connect_args with server_settings for asyncpg search_path instead of URL ?options= parameter (asyncpg rejects options kwarg when passed via SQLAlchemy)
- Set env_nested_max_split=1 on AppConfig directly, not on BaseConfig, because pydantic-settings metaclass resets inherited SettingsConfigDict values during subclass creation
- Removed api_key from config.yaml entirely so JWT_API_KEY env var is picked up by pydantic-settings nested delimiter
- db_session fixture creates its own engine to avoid event-loop conflict between pytest-asyncio and TestClient

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed db_session event-loop mismatch with TestClient**
- **Found during:** Task 2 (e2e test run)
- **Issue:** db_session fixture reused app's session factory which is bound to TestClient's event loop, but async test runs in a different loop, causing "attached to a different loop" RuntimeError
- **Fix:** Changed db_session to create its own engine and session factory using _app_config connection details
- **Files modified:** tests/e2e/conftest.py
- **Verification:** All 18 e2e tests pass without event-loop errors
- **Committed in:** ac09f8e (Task 2 commit)

**2. [Rule 1 - Bug] Fixed stale FK cascade in test database**
- **Found during:** Task 2 (e2e test run)
- **Issue:** The `api` schema's messages_chat_id_fkey had NO ACTION instead of CASCADE (table created before ondelete="CASCADE" was added to model). Both cleanup_chat and the app's delete endpoint failed with FK violation.
- **Fix:** Changed ensure_tables to drop_all + create_all (safe for test DB), and made cleanup_chat explicitly delete messages before chats
- **Files modified:** tests/e2e/conftest.py
- **Verification:** delete_chat e2e test passes, all 18 tests green
- **Committed in:** ac09f8e (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes were pre-existing bugs exposed by fixing the planned issues. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All unit and e2e tests passing (82 + 18)
- Test infrastructure stable with correct event-loop handling and FK cascades

## Self-Check: PASSED

- All 4 modified files exist on disk
- Both commit hashes (96eff5e, ac09f8e) found in git log
- SUMMARY.md created successfully
- 82 unit tests + 18 e2e tests passing

---
*Quick task: 260317-waa*
*Completed: 2026-03-17*
