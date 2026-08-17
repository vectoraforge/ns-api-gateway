---
phase: quick
plan: 260317-ivv
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - tests/e2e/conftest.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_examples.py
  - tests/e2e/test_root.py
  - tests/e2e/test_health.py
  - tests/e2e/test_chat_queries.py
  - tests/e2e/test_isolation.py
autonomous: true
must_haves:
  truths:
    - "Unit tests run by default via plain `pytest` without needing mark flags"
    - "E2E tests are excluded from default `pytest` via a single `e2e` mark"
    - "E2E tests can be explicitly run with `pytest -m e2e`"
    - "No `db` or `llm` marks remain anywhere in the codebase"
  artifacts:
    - path: "pyproject.toml"
      provides: "e2e marker definition and addopts excluding e2e"
      contains: "not e2e"
    - path: "tests/e2e/conftest.py"
      provides: "Auto-applied e2e mark for all tests in e2e directory"
      contains: "pytestmark"
  key_links:
    - from: "tests/e2e/conftest.py"
      to: "pyproject.toml"
      via: "pytestmark = pytest.mark.e2e matches markers definition"
      pattern: "pytest\\.mark\\.e2e"
---

<objective>
Replace the granular `@pytest.mark.db` and `@pytest.mark.llm` decorators on e2e tests with a single `e2e` mark applied automatically via conftest. Update pyproject.toml to exclude `e2e` by default instead of `db` and `llm`.

Purpose: Simplify test selection -- unit tests run by default, e2e tests run with `-m e2e`.
Output: Clean test marks, updated pytest config.
</objective>

<execution_context>
@/Users/vay/.claude/get-shit-done/workflows/execute-plan.md
@/Users/vay/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@pyproject.toml
@tests/e2e/conftest.py
@tests/e2e/test_chats.py
@tests/e2e/test_flows.py
@tests/e2e/test_examples.py
@tests/e2e/test_root.py
@tests/e2e/test_health.py
@tests/e2e/test_chat_queries.py
@tests/e2e/test_isolation.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Replace db/llm marks with auto-applied e2e mark and update pytest config</name>
  <files>
    pyproject.toml,
    tests/e2e/conftest.py,
    tests/e2e/test_chats.py,
    tests/e2e/test_flows.py,
    tests/e2e/test_examples.py,
    tests/e2e/test_root.py,
    tests/e2e/test_health.py,
    tests/e2e/test_chat_queries.py,
    tests/e2e/test_isolation.py
  </files>
  <action>
    1. In `tests/e2e/conftest.py`, add at module level (after imports, before fixtures):
       ```python
       pytestmark = pytest.mark.e2e
       ```
       This auto-applies `@pytest.mark.e2e` to every test collected from the `tests/e2e/` directory.

    2. In `pyproject.toml` [tool.pytest.ini_options]:
       - Change `addopts` from `-v --tb=short -m 'not llm and not db'` to `-v --tb=short -m 'not e2e'`
       - Replace the `markers` list with:
         ```
         markers = [
             "e2e: marks end-to-end tests requiring real infrastructure (deselect with -m 'not e2e')",
         ]
         ```

    3. Remove ALL `@pytest.mark.db` and `@pytest.mark.llm` decorators from every e2e test file:
       - `test_chats.py`: Remove `@pytest.mark.db` and `@pytest.mark.llm` from both `TestCreateChat` and `TestFollowup` classes (lines 4-5 and 45-46)
       - `test_flows.py`: Remove `@pytest.mark.db` and `@pytest.mark.llm` from `TestChatLifecycle` class (lines 4-5)
       - `test_examples.py`: Remove `@pytest.mark.db` from `TestExamplesEndpoint` class (line 4)
       - `test_root.py`: Remove `@pytest.mark.db` from `TestRootEndpoint` class (line 4)
       - `test_health.py`: Remove `@pytest.mark.db` from `TestHealthEndpoint` class (line 4)
       - `test_chat_queries.py`: Remove `@pytest.mark.db` from `TestListChats`, `TestGetChatMessages`, and `TestDeleteChat` classes (lines 6, 25, 45)
       - `test_isolation.py`: Remove `@pytest.mark.db` from `TestCrossUserIsolation` class (line 8)
       - Also remove `import pytest` from files that no longer use any pytest features directly (test_chats.py, test_flows.py, test_examples.py, test_root.py, test_health.py). Keep `import pytest` in test_chat_queries.py and test_isolation.py since they use `@pytest.mark.asyncio`.
  </action>
  <verify>
    <automated>python -m pytest tests/unit/ --co -q 2>&1 | tail -3 && python -m pytest tests/e2e/ --co -q -m e2e 2>&1 | tail -3 && python -m pytest --co -q 2>&1 | tail -3</automated>
  </verify>
  <done>
    - `pytest --co -q` collects only unit tests (82 tests, no e2e)
    - `pytest -m e2e --co -q` collects all 18 e2e tests
    - No `@pytest.mark.db` or `@pytest.mark.llm` decorators remain in any test file
    - No `db` or `llm` marker definitions in pyproject.toml
  </done>
</task>

<task type="auto">
  <name>Task 2: Verify unit tests still pass</name>
  <files></files>
  <action>
    Run the full unit test suite to confirm nothing is broken by the marker changes.
    Run `python -m pytest` (which now defaults to `-m 'not e2e'`).
    All 82 unit tests must pass.
  </action>
  <verify>
    <automated>python -m pytest 2>&1 | tail -5</automated>
  </verify>
  <done>All unit tests pass with exit code 0. No tests unexpectedly skipped or deselected.</done>
</task>

</tasks>

<verification>
- `grep -r "pytest.mark.db\|pytest.mark.llm" tests/` returns no results
- `grep "not e2e" pyproject.toml` shows the updated addopts
- `pytest --co -q` shows only unit tests collected
- `pytest -m e2e --co -q` shows all 18 e2e tests collected
- `pytest` passes all unit tests
</verification>

<success_criteria>
- Zero occurrences of `pytest.mark.db` or `pytest.mark.llm` in codebase
- `pyproject.toml` uses `e2e` marker exclusively
- `tests/e2e/conftest.py` has `pytestmark = pytest.mark.e2e`
- Default `pytest` runs unit tests only and passes
- `pytest -m e2e` selects all 18 e2e tests
</success_criteria>

<output>
After completion, create `.planning/quick/260317-ivv-remove-db-and-llm-marks-from-tests-and-f/260317-ivv-SUMMARY.md`
</output>
