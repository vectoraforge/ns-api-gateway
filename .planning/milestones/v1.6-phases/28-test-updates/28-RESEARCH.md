# Phase 28: Test Updates - Research

**Researched:** 2026-03-23
**Domain:** Python test infrastructure (pytest, pytest-asyncio, SQLModel, FastAPI)
**Confidence:** HIGH

## Summary

Phase 28 is a focused test-fix phase. The codebase has already been updated through Phases 25-27 (config-driven quotas, native PG enum types, new migration). The test suite needs two categories of changes: (1) removing the `ensure_tables` fixture from E2E conftest so tests assume a pre-migrated database, and (2) fixing broken module paths in unit tests.

A live test run against the current codebase reveals the unit test suite has **exactly 1 failure**: `tests/unit/test_subscriptions.py::TestFirebaseSync::test_uses_to_thread` fails with `ModuleNotFoundError: No module named 'app'` because the `patch()` target uses the wrong module path `"app.services.firebase_service.asyncio.to_thread"` instead of the correct `"nativespeaker.api.services.firebase.asyncio.to_thread"`. The same wrong path appears on line 309 for `test_firebase_failure_does_not_raise`. All other 133 unit tests pass.

**Primary recommendation:** Remove the `ensure_tables` fixture and fix `_app_lifespan` dependency chain in E2E conftest, then fix the two broken `patch()` paths in `test_subscriptions.py`. A full audit grep confirms no stale `Plan` model or `plans` table references exist in the test suite -- Phase 25 already cleaned those up.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Tests do NOT create database objects -- no `create_all()`, no `CREATE TYPE`, no running migrations from test code. The database must be fully set up (migrations applied) before tests run.
- **D-02:** Remove the `ensure_tables` fixture from `tests/e2e/conftest.py` that currently calls `SQLModel.metadata.create_all`
- **D-03:** E2E tests assume a pre-migrated database -- the migration is applied externally before `pytest` runs
- **D-04:** Audit all test files for stale references before running pytest -- grep for old names, old signatures, plans table references, etc.
- **D-05:** Fix all stale references found in audit, then verify with full `pytest` run
- **D-06:** Include plans table references in the audit -- grep for `plans`, `Plan`, `seed` across all test files even though Phase 25 removed the model
- **D-07:** Remove any residual plans references found (imports, seeding, assertions)

### Claude's Discretion
- How to handle `ensure_tables` removal -- whether to delete entirely or replace with a lightweight DB connectivity check
- Specific grep patterns for the audit step
- Order of fixes after audit

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | E2E conftest creates PG enum types before `create_all()` and removes plans seed data | **REVISED per D-01/D-02/D-03:** E2E conftest must NOT create any DB objects at all. Remove `ensure_tables` entirely. Tests assume a pre-migrated database. |
| TEST-02 | Unit tests updated for new UsageDB.try_increment signature | Verified: unit tests already use the correct `try_increment` signature via `ChatService` integration. The mock in conftest accepts any args. The only unit test failure is a broken `patch()` path in `test_subscriptions.py`. |
</phase_requirements>

## Current Test State (Live Run Results)

### Unit Tests (134 collected)
| Status | Count | Detail |
|--------|-------|--------|
| PASSED | 133 | All unit tests except one |
| FAILED | 1 | `test_subscriptions.py::TestFirebaseSync::test_uses_to_thread` -- `ModuleNotFoundError: No module named 'app'` |

**Root cause of failure:** Two tests in `test_subscriptions.py` use `patch("app.services.firebase_service.asyncio.to_thread", ...)` -- the correct path is `nativespeaker.api.services.firebase.asyncio.to_thread` (module file is `src/nativespeaker/api/services/firebase.py`).

### E2E Tests (not runnable without live DB)
The `ensure_tables` fixture currently calls `SQLModel.metadata.create_all` which will fail against a database with native PG enum types (SQLModel's `create_all` cannot create PG enums with `create_type=False`). Per user decisions D-01 through D-03, this fixture must be removed entirely.

### Audit Results: Stale References
A comprehensive grep for `Plan`, `plans`, `seed`, `get_monthly_limit`, `ensure_tables`, `create_all` across all test files found:

| Pattern | Matches | Status |
|---------|---------|--------|
| `Plan` (not `SubscriptionPlan`) | 1 match: `TestPlanTierUpdate` class name in `test_subscriptions.py` | **Not stale** -- class name describes plan tier update behavior, not the deleted Plan model |
| `plans` (not `SubscriptionPlan`) | 0 matches | Clean |
| `seed` | 1 match: comment "seeding assertions" in `e2e/conftest.py:53` | **Not stale** -- comment refers to seeding test assertions, not DB seeding |
| `get_monthly_limit` | 0 matches in test suite proper | Clean (exists only in `.claude/worktrees/` -- stale worktrees) |
| `ensure_tables` | 3 matches in `e2e/conftest.py` | **Must remove** -- fixture definition and dependency |
| `create_all` | 1 match in `e2e/conftest.py:30` | **Must remove** -- inside `ensure_tables` |

**Conclusion:** The test suite is cleaner than expected. Phase 25 already removed Plan model references. The work is narrowly scoped.

## Architecture Patterns

### E2E Fixture Chain (Current)
```
_app_config (session)
    |
    +-- ensure_tables (session) <-- REMOVE THIS
    |       |
    +-------+-- _app_lifespan (module) <-- UPDATE: remove ensure_tables dependency
    |               |
    +-- firebase_token (session)
    |       |
    +-------+-------+-- async_client (module)
    |
    +-- _db_transaction (module, autouse)
    +-- test_user_id (module)
```

### E2E Fixture Chain (After Fix)
```
_app_config (session)
    |
    +-- _app_lifespan (module) <-- depends only on _app_config (implicit via app)
    |       |
    +-- firebase_token (session)
    |       |
    +-------+-- async_client (module)
    |
    +-- _db_transaction (module, autouse)
    +-- test_user_id (module)
```

### Recommended: `ensure_tables` Removal Strategy
**Delete entirely** rather than replacing with a connectivity check. Rationale:
1. The `_app_lifespan` fixture already starts the app lifespan which initializes the DB engine -- if the DB is unreachable, this will fail with a clear error
2. A connectivity check adds complexity for zero value
3. The `_db_transaction` fixture creates a connection per test -- another implicit connectivity check

### Code Change: `_app_lifespan` Signature
```python
# Before:
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan(ensure_tables):
    """Start app lifespan (config, DB engine, verifier, LLM service)."""
    async with app.router.lifespan_context(app):
        yield app

# After:
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan():
    """Start app lifespan (config, DB engine, verifier, LLM service)."""
    async with app.router.lifespan_context(app):
        yield app
```

### Code Change: Fix Broken Patch Paths
```python
# Before (line 300):
with patch("app.services.firebase_service.asyncio.to_thread",
            new_callable=AsyncMock) as mock_to_thread:

# After:
with patch("nativespeaker.api.services.firebase.asyncio.to_thread",
            new_callable=AsyncMock) as mock_to_thread:

# Before (line 309):
with patch("app.services.firebase_service.asyncio.to_thread",
            side_effect=Exception("Firebase down")):

# After:
with patch("nativespeaker.api.services.firebase.asyncio.to_thread",
            side_effect=Exception("Firebase down")):
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DB connectivity check | Custom fixture that runs `SELECT 1` | App lifespan init (already does engine setup) | Already covered by `_app_lifespan` and `_db_transaction` fixtures |
| Enum type creation in tests | `CREATE TYPE IF NOT EXISTS` statements | Pre-migrated database (pogo-migrate applied before test run) | D-01 is explicit: tests NEVER create database objects |

## Common Pitfalls

### Pitfall 1: Removing `ensure_tables` but Not Updating `_app_lifespan`
**What goes wrong:** `_app_lifespan(ensure_tables)` has `ensure_tables` as a parameter dependency. Deleting the fixture without removing the parameter causes `fixture 'ensure_tables' not found`.
**How to avoid:** Remove `ensure_tables` from `_app_lifespan` parameter list in the same edit.

### Pitfall 2: Unused Imports After `ensure_tables` Removal
**What goes wrong:** `create_async_engine` and `SQLModel` are imported in `e2e/conftest.py` only for the `ensure_tables` fixture. Leaving them causes ruff lint warnings.
**How to avoid:** Remove the now-unused imports: `create_async_engine` from sqlalchemy, `SQLModel` from sqlmodel. Verify with `ruff check`.

### Pitfall 3: Patch Path Must Match Where Object Is Looked Up
**What goes wrong:** `patch("nativespeaker.api.services.firebase.asyncio.to_thread")` patches `asyncio.to_thread` in the `firebase` module's namespace. This is correct because `firebase.py` imports `asyncio` at the top level and calls `asyncio.to_thread`.
**How to avoid:** Always patch where the object is used, not where it's defined.

### Pitfall 4: E2E Tests Fail If Migration Not Applied
**What goes wrong:** After removing `ensure_tables`, E2E tests will fail with table-not-found errors if the migration hasn't been applied to the test database.
**How to avoid:** This is expected and acceptable per D-01/D-03 -- the migration must be applied externally. Document this in the test runner instructions or CI pipeline.

## Code Examples

### Complete E2E conftest.py After Fix
```python
import asyncio
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.app.main import app
from nativespeaker.api.config import MainConfig
from nativespeaker.api.models import AIContent, Chat, ChatRole, HumanContent, Message, User


@pytest.fixture(scope="session")
def _app_config():
    """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
    return MainConfig().app_config


@pytest.fixture(scope="session")
def firebase_token(_app_config):
    # ... unchanged ...


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan():
    """Start app lifespan (config, DB engine, verifier, LLM service)."""
    async with app.router.lifespan_context(app):
        yield app

# ... rest unchanged ...
```

### Unused Imports to Remove
```python
# Remove these from e2e/conftest.py:
from sqlalchemy.ext.asyncio import create_async_engine  # only used in ensure_tables
from sqlmodel import SQLModel                            # only used in ensure_tables
```

### Imports That Stay
```python
# Keep -- still used by _db_transaction:
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
```

## File-by-File Change Summary

| File | Change | Reason |
|------|--------|--------|
| `tests/e2e/conftest.py` | Delete `ensure_tables` fixture (lines 24-33); remove `ensure_tables` param from `_app_lifespan` (line 59); remove unused imports `create_async_engine`, `SQLModel` | D-01, D-02, TEST-01 |
| `tests/unit/test_subscriptions.py` | Fix `patch()` path on lines 300 and 309: `"app.services.firebase_service"` -> `"nativespeaker.api.services.firebase"` | Broken test -- `ModuleNotFoundError` |
| All other test files | No changes needed | Audit confirms no stale references |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (auto mode) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/unit/ -x --tb=short` |
| Full suite command | `python -m pytest tests/unit/ -v --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | E2E conftest does not create DB objects | code inspection + E2E run | `python -m pytest tests/e2e/ -v -m e2e --tb=short` (requires live DB) | N/A -- this is a conftest change, not a test |
| TEST-02 | Unit tests pass with new try_increment signature | unit | `python -m pytest tests/unit/ -x --tb=short` | Already exists and passes (133/134) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x --tb=short`
- **Per wave merge:** `python -m pytest tests/unit/ -v --tb=short`
- **Phase gate:** Full unit suite green (`python -m pytest tests/unit/`)

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. No new test files needed.

## Project Constraints (from CLAUDE.md)

- **Opening delimiter alignment style** for multiline constructs (func defs one per line, func calls collapse)
- **Don't use string-based module references in Python tests** -- note: `unittest.mock.patch()` inherently requires string targets; the constraint means avoid string-based test discovery/imports. The two broken paths use `patch()` which is standard practice, but they have the WRONG string.
- **Don't commit .planning dir**
- **Use Context7 MCP** for library/API documentation
- **Use shorter names for branch names**

## Sources

### Primary (HIGH confidence)
- Live `pytest` run against current codebase (134 tests collected, 1 failure identified)
- Direct code inspection of all 8 E2E test files and 12 unit test files
- Direct code inspection of `UsageDB.try_increment` signature (`user_id`, `month`, `monthly_quota`)
- Direct code inspection of `ChatService.create_chat` and `send_message` (both call `try_increment` correctly)
- Direct code inspection of `FirebaseService` at `src/nativespeaker/api/services/firebase.py`

### Secondary (MEDIUM confidence)
- Grep audit for `Plan`, `plans`, `seed`, `get_monthly_limit`, `ensure_tables`, `create_all` across test directory

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - existing framework, no new libraries
- Architecture: HIGH - fixture chain directly inspected and live-tested
- Pitfalls: HIGH - based on actual code inspection and live test run

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (stable -- no moving targets, pure test fixes)
