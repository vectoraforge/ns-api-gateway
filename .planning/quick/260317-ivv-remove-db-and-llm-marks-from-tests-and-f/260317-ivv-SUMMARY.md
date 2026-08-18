---
phase: quick
plan: 260317-ivv
subsystem: testing
tags: [pytest, marks, e2e, test-selection]

requires:
  - phase: 16-update-tests
    provides: e2e test suite structure under tests/e2e/
provides:
  - Single e2e mark replacing granular db/llm marks
  - Default pytest runs unit tests only via addopts 'not e2e'
  - Explicit e2e selection via pytest -m e2e
affects: [testing, ci]

tech-stack:
  added: []
  patterns: [pytestmark module-level e2e marking]

key-files:
  created: []
  modified:
    - pyproject.toml
    - tests/e2e/conftest.py
    - tests/e2e/test_chats.py
    - tests/e2e/test_flows.py
    - tests/e2e/test_examples.py
    - tests/e2e/test_root.py
    - tests/e2e/test_health.py
    - tests/e2e/test_chat_queries.py
    - tests/e2e/test_isolation.py

key-decisions:
  - "pytestmark in each test module (not just conftest.py) because conftest.py pytestmark does not propagate to test files in pytest 9"

patterns-established:
  - "e2e mark pattern: every test module in tests/e2e/ declares pytestmark = pytest.mark.e2e"

requirements-completed: []

duration: 4min
completed: 2026-03-17
---

# Quick Task 260317-ivv: Remove db/llm marks Summary

**Replaced granular db/llm pytest marks with single e2e mark auto-applied per module; default pytest now runs only unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-17T20:41:54Z
- **Completed:** 2026-03-17T20:46:07Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Replaced `addopts = "-v --tb=short -m 'not llm and not db'"` with `"-v --tb=short -m 'not e2e'"` in pyproject.toml
- Replaced `llm` and `db` marker definitions with single `e2e` marker
- Added `pytestmark = pytest.mark.e2e` to all 7 e2e test modules for reliable mark propagation
- Default `pytest` collects 82 unit tests (18 e2e deselected); `pytest -m e2e` collects all 18 e2e tests
- All 82 unit tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace db/llm marks with auto-applied e2e mark and update pytest config** - `e2bc60b` (feat)
2. **Task 2: Verify unit tests still pass** - verification only, no commit

## Files Created/Modified
- `pyproject.toml` - Changed addopts to exclude e2e, replaced marker definitions
- `tests/e2e/conftest.py` - Added pytestmark = pytest.mark.e2e (belt-and-suspenders)
- `tests/e2e/test_chats.py` - Added pytestmark, removed old db/llm marks
- `tests/e2e/test_flows.py` - Added pytestmark, removed old db/llm marks
- `tests/e2e/test_examples.py` - Added pytestmark, removed old db mark
- `tests/e2e/test_root.py` - Added pytestmark, removed old db mark
- `tests/e2e/test_health.py` - Added pytestmark, removed old db mark
- `tests/e2e/test_chat_queries.py` - Added pytestmark, removed old db mark
- `tests/e2e/test_isolation.py` - Added pytestmark, removed old db mark

## Decisions Made
- Used `pytestmark` in each test module rather than relying solely on conftest.py, because conftest.py `pytestmark` does not propagate to test files in pytest 9.x. The conftest.py `pytestmark` is kept as a secondary signal.
- Removed `import pytest` from test files that no longer need it (test_chats.py, test_flows.py, test_examples.py, test_root.py, test_health.py) -- then re-added it since `pytestmark = pytest.mark.e2e` requires the import.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pytestmark in conftest.py does not propagate to test modules**
- **Found during:** Task 1 (verification step)
- **Issue:** Plan specified adding `pytestmark = pytest.mark.e2e` only in conftest.py, but pytest 9.x does not propagate conftest.py pytestmark to test files -- `pytest -m e2e` collected 0 tests
- **Fix:** Added `pytestmark = pytest.mark.e2e` to each individual test module
- **Files modified:** All 7 test files in tests/e2e/
- **Verification:** `pytest -m e2e --co -q` now collects 18 tests; `pytest --co -q` collects 82 (18 deselected)
- **Committed in:** e2bc60b

**2. [Rule 1 - Bug] import pytest needed in test files for pytestmark**
- **Found during:** Task 1
- **Issue:** Plan said to remove `import pytest` from files not using pytest features directly, but pytestmark requires the import
- **Fix:** Added `import pytest` to files that need it for `pytestmark = pytest.mark.e2e`
- **Files modified:** test_chats.py, test_flows.py, test_examples.py, test_root.py, test_health.py
- **Committed in:** e2bc60b

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes essential for correct test selection behavior. No scope creep.

## Issues Encountered
- Previous quick task (260317-1g1) left pyproject.toml and conftest.py changes uncommitted in the working tree. These changes aligned with this plan's objectives and were included in the Task 1 commit.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Test selection is clean: `pytest` for unit tests, `pytest -m e2e` for e2e tests
- No db/llm marks remain in the codebase

## Self-Check: PASSED

All 9 modified files verified present. Commit e2bc60b verified in git log. SUMMARY.md created.

---
*Quick task: 260317-ivv*
*Completed: 2026-03-17*
