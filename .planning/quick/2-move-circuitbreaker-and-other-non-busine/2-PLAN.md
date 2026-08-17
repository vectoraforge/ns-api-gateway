---
phase: quick
plan: 2
type: execute
wave: 1
depends_on: []
files_modified:
  - app/resilience.py
  - app/services.py
  - app/main.py
  - tests/conftest.py
  - tests/unit/test_services.py
  - tests/integration/conftest.py
autonomous: true
requirements: [CLEANUP-SERVICES-SPLIT]

must_haves:
  truths:
    - "CircuitBreaker, LLMExecutionGate, and helper functions live in app/resilience.py"
    - "AnalysisService stays in app/services.py and still uses _is_transient_error"
    - "All existing tests pass without modification to test logic"
  artifacts:
    - path: "app/resilience.py"
      provides: "CircuitBreaker, LLMExecutionGate, _extract_status_code, _is_transient_error"
      exports: ["CircuitBreaker", "LLMExecutionGate", "_extract_status_code", "_is_transient_error"]
    - path: "app/services.py"
      provides: "AnalysisService only, imports resilience components"
  key_links:
    - from: "app/services.py"
      to: "app/resilience.py"
      via: "import statement"
      pattern: "from app\\.resilience import"
    - from: "app/main.py"
      to: "app/resilience.py"
      via: "import statement"
      pattern: "from app\\.resilience import"
---

<objective>
Extract non-business resilience code (CircuitBreaker, LLMExecutionGate, helper functions) from app/services.py into a new app/resilience.py module.

Purpose: Separate infrastructure/resilience concerns from business logic for cleaner architecture.
Output: New app/resilience.py file; updated imports across app and test files.
</objective>

<execution_context>
@/Users/otto/.claude/get-shit-done/workflows/execute-plan.md
@/Users/otto/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@app/services.py
@app/main.py
@tests/conftest.py
@tests/unit/test_services.py
@tests/integration/conftest.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create app/resilience.py and trim app/services.py</name>
  <files>app/resilience.py, app/services.py</files>
  <action>
Create `app/resilience.py` containing (in this order):
1. All necessary imports: `asyncio`, `time`, `contextlib.asynccontextmanager`, `collections.abc.Awaitable`, `collections.abc.Callable`, and the openai exception imports (the try/except block from services.py lines 25-34), plus `from app.exceptions import QueueFullError, CircuitOpenError`
2. `_extract_status_code()` function (lines 37-44)
3. `_is_transient_error()` function (lines 47-59)
4. `CircuitBreaker` class (lines 62-93)
5. `LLMExecutionGate` class (lines 96-122)

Then edit `app/services.py`:
1. Remove the moved code (lines 25-122: the openai try/except block, both helper functions, both classes)
2. Add import at top: `from app.resilience import CircuitBreaker, LLMExecutionGate, _is_transient_error`
3. Keep all existing imports that AnalysisService needs (asyncio, time, uuid, langchain, sqlalchemy, app.chats, app.schema, app.exceptions)
4. Remove imports from app.exceptions that are ONLY used by the moved code (QueueFullError, CircuitOpenError) -- BUT check first: QueueFullError and CircuitOpenError are referenced in AnalysisService._invoke (lines 188-191), so they MUST stay in services.py's exception imports
5. Remove the openai try/except import block (moved to resilience.py)
6. Remove `from contextlib import asynccontextmanager` and `from collections.abc import Awaitable, Callable` if no longer used in services.py (AnalysisService does not use them)

IMPORTANT: `_is_transient_error` is called directly in `AnalysisService._invoke` (lines 194-195), so it must be imported into services.py from resilience.py.
  </action>
  <verify>python -c "from app.resilience import CircuitBreaker, LLMExecutionGate, _extract_status_code, _is_transient_error; print('resilience OK')" && python -c "from app.services import AnalysisService; print('services OK')"</verify>
  <done>app/resilience.py exists with all 4 exports. app/services.py contains only AnalysisService and imports resilience components. No circular imports.</done>
</task>

<task type="auto">
  <name>Task 2: Update all import sites across app and tests</name>
  <files>app/main.py, tests/conftest.py, tests/unit/test_services.py, tests/integration/conftest.py</files>
  <action>
Update import statements in all files that previously imported CircuitBreaker or LLMExecutionGate from app.services:

1. `app/main.py` (line 16): Change `from app.services import AnalysisService, LLMExecutionGate, CircuitBreaker` to two imports:
   - `from app.services import AnalysisService`
   - `from app.resilience import LLMExecutionGate, CircuitBreaker`

2. `tests/conftest.py` (line 14): Change `from app.services import AnalysisService, LLMExecutionGate, CircuitBreaker` to two imports:
   - `from app.services import AnalysisService`
   - `from app.resilience import LLMExecutionGate, CircuitBreaker`

3. `tests/unit/test_services.py` (line 9): Change `from app.services import AnalysisService, LLMExecutionGate, CircuitBreaker` to two imports:
   - `from app.services import AnalysisService`
   - `from app.resilience import LLMExecutionGate, CircuitBreaker`
   ALSO: Line 155 patches `app.services._is_transient_error`. After the move, `_is_transient_error` is defined in `app.resilience` but imported into `app.services`. The patch path should become `app.services._is_transient_error` -- actually this STILL WORKS because the function is imported into the services namespace and the patch targets the reference in the module where it's used. Verify this is correct by checking: the patch mocks the name in services' namespace, which is where AnalysisService._invoke calls it. So the patch path `app.services._is_transient_error` remains correct. Do NOT change it.

4. `tests/integration/conftest.py` (line 18): Change `from app.services import AnalysisService, LLMExecutionGate, CircuitBreaker` to two imports:
   - `from app.services import AnalysisService`
   - `from app.resilience import LLMExecutionGate, CircuitBreaker`
  </action>
  <verify>cd /Users/otto/Work/nativespeaker/sn-api-gateway && python -m pytest tests/ -x -q 2>&1 | tail -20</verify>
  <done>All 4 import sites updated. All tests pass. The patch path for _is_transient_error in test_services.py remains valid because the import brings it into app.services namespace.</done>
</task>

</tasks>

<verification>
- `python -c "from app.resilience import CircuitBreaker, LLMExecutionGate, _extract_status_code, _is_transient_error"` -- all exports available
- `python -c "from app.services import AnalysisService"` -- services module still works
- `grep -r "from app.services import.*CircuitBreaker" app/ tests/` -- returns NO results (all moved to resilience imports)
- `python -m pytest tests/ -x -q` -- all tests pass
</verification>

<success_criteria>
- app/resilience.py exists with CircuitBreaker, LLMExecutionGate, _extract_status_code, _is_transient_error
- app/services.py contains only AnalysisService (plus its imports)
- No file imports CircuitBreaker or LLMExecutionGate from app.services
- All existing tests pass unchanged
</success_criteria>

<output>
After completion, create `.planning/quick/2-move-circuitbreaker-and-other-non-busine/2-SUMMARY.md`
</output>
