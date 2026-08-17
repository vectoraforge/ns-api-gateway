# Phase 19: Service Layer Refactoring - Research

**Researched:** 2026-03-19
**Domain:** Python package refactoring (FastAPI / SQLModel codebase)
**Confidence:** HIGH

## Summary

This phase is a pure structural refactoring with zero behavior changes. The existing `app/service.py` (two classes: `LLMService`, `ChatService`) splits into an `app/services/` package, and `app/database.py` (one class: `ChatsDB`) moves into an `app/database/` package. Both new packages re-export their public classes from `__init__.py` so that importers use short paths (`from app.services import ChatService`).

There are exactly 7 import sites that reference the old modules, plus 1 internal cross-reference (`ChatService` imports `ChatsDB`). The `pyproject.toml` `[tool.setuptools]` packages list must also be updated. The risk profile is low because all changes are mechanical and the codebase already has an established pattern for package re-exports (`app/routers/__init__.py`).

**Primary recommendation:** Follow the existing `app/routers/__init__.py` pattern exactly -- use `__all__` with re-exports -- and update `pyproject.toml` packages in the same commit.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Re-export classes from package `__init__.py` files
- Importers use short paths: `from app.services import ChatService`, `from app.database import ChatsDB`
- `__init__.py` handles internal wiring -- importers don't need to know module names
- Minimal database package structure: `database/__init__.py` + `chats_db.py` only
- No base class or shared utilities -- add when Phase 21 introduces UsersDB
- Keep the existing session-in-init pattern on ChatsDB unchanged
- Delete `app/service.py` and `app/database.py` immediately after split
- No compatibility shims or re-export stubs -- clean break
- All 7 import sites updated in one pass

### Claude's Discretion
- Exact ordering of imports within new `__init__.py` files
- Whether to add `__all__` to new packages
- Test file import updates (same convention, just new paths)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SVC-01 | `service.py` split into `services/` package with separate modules (LLMService, ChatService) | Complete inventory of LLMService (21 lines, self-contained) and ChatService (97 lines, depends on ChatsDB/LLMService). Existing `app/routers/__init__.py` pattern provides exact template for `__init__.py` structure |
| SVC-02 | `database.py` split into `database/` package with separate modules (ChatsDB, UsersDB) | Phase 19 scope is ChatsDB only (55 lines, self-contained). UsersDB deferred to Phase 21 per CONTEXT.md |
| SVC-03 | Refactoring introduces zero behavior changes -- all existing tests pass unchanged | Complete import site inventory (7 external + 1 internal). E2e tests have NO direct imports to change. `pyproject.toml` packages list identified as additional update site |
</phase_requirements>

## Standard Stack

No new libraries are introduced. This is pure structural refactoring of existing code.

### Tooling Used
| Tool | Purpose | Notes |
|------|---------|-------|
| Python packages (`__init__.py`) | Module organization | Standard Python packaging -- no third-party tools |
| setuptools | Package discovery | `pyproject.toml` `[tool.setuptools]` packages list must be updated |

## Architecture Patterns

### Target Project Structure
```
app/
├── api/
│   ├── dependencies.py
│   ├── errors.py
│   ├── main.py
│   └── schema.py
├── database/              # NEW package (was database.py)
│   ├── __init__.py        # re-exports ChatsDB
│   └── chats_db.py        # ChatsDB class (moved from database.py)
├── routers/
│   ├── __init__.py
│   ├── chats.py
│   ├── examples.py
│   ├── health.py
│   └── root.py
├── services/              # NEW package (was service.py)
│   ├── __init__.py        # re-exports LLMService, ChatService
│   ├── chat_service.py    # ChatService class
│   └── llm_service.py     # LLMService class
├── auth.py
├── config.py
├── exceptions.py
├── models.py
└── resilience.py
```

### Pattern 1: Package Re-export with `__all__` (follow existing `app/routers/` pattern)

**What:** The project already uses this pattern in `app/routers/__init__.py`. New packages must follow it exactly.

**Existing pattern to replicate:**

```python
# app/routers/__init__.py (existing -- this IS the pattern)
__all__ = ["chats_router", "examples_router", "health_router", "root_router"]

from routers import router as chats_router
from routers.examples import router as examples_router
from routers.health import router as health_router
from routers.root import router as root_router
```

**Recommendation for `__all__`:** YES, add `__all__` to both new packages. The existing `app/routers/__init__.py` uses `__all__`, so consistency demands it.

**New `app/services/__init__.py`:**

```python
__all__ = ["ChatService", "LLMService"]

from services import ChatService
from services import LLMService
```

**New `app/database/__init__.py`:**

```python
__all__ = ["ChatsDB"]

from database import ChatsDB
```

### Pattern 2: Internal Cross-Package Import

**What:** `ChatService` currently imports `from app.database import ChatsDB`. After refactoring, the import path stays identical because `database/__init__.py` re-exports `ChatsDB`.

**Key insight:** The re-export pattern means `chat_service.py` uses `from app.database import ChatsDB` -- the exact same import that worked with the old flat module. No change needed in the internal cross-reference.

### Anti-Patterns to Avoid
- **Deep imports from external callers:** Never `from app.services.chat_service import ChatService` in routers/tests. Always use the package-level import `from app.services import ChatService`. The `__init__.py` is the public API.
- **Circular imports via __init__.py:** Don't import from sibling packages inside `__init__.py` -- only import from the package's own submodules.

## Complete Import Site Inventory

This is the exhaustive list of every file that must change. Verified via `grep`.

### External Import Sites (7 files)

| File | Old Import | New Import |
|------|-----------|------------|
| `app/api/dependencies.py:10` | `from app.service import ChatService` | `from app.services import ChatService` |
| `app/api/main.py:15` | `from app.service import LLMService` | `from app.services import LLMService` |
| `app/routers/chats.py:8` | `from app.service import ChatService` | `from app.services import ChatService` |
| `app/routers/root.py:6` | `from app.service import ChatService` | `from app.services import ChatService` |
| `app/routers/examples.py:5` | `from app.service import ChatService` | `from app.services import ChatService` |
| `tests/unit/conftest.py:13` | `from app.database import ChatsDB` | `from app.database import ChatsDB` (UNCHANGED -- same path) |
| `tests/unit/conftest.py:16` | `from app.service import ChatService` | `from app.services import ChatService` |

**Critical observation:** The `from app.database import ChatsDB` import path does NOT change because the new package `app/database/__init__.py` re-exports `ChatsDB` at the same path as the old `app/database.py` module. Only `app.service` -> `app.services` changes (singular to plural).

### Internal Cross-Reference (1 file)

| File | Old Import | New Import |
|------|-----------|------------|
| `app/services/chat_service.py:14` (was `app/service.py:14`) | `from app.database import ChatsDB` | `from app.database import ChatsDB` (UNCHANGED) |

### E2e Tests (0 changes)

E2e tests (`tests/e2e/`) do NOT import from `app.service` or `app.database` directly. They import `from app.api.main import app` and interact via HTTP client. No changes needed.

### pyproject.toml Update (1 change)

```toml
# OLD
[tool.setuptools]
packages = ["app", "app.routers", "app.api"]

# NEW
[tool.setuptools]
packages = ["app", "app.routers", "app.api", "app.services", "app.database"]
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Backward compatibility shims | Re-export stubs in old locations | Clean break (user decision) | Shims accumulate tech debt; all 7 sites can be updated atomically |
| Import rewriting tools | Automated sed/codemod scripts | Manual find-and-replace | Only 6 actual changes across 6 files; automation overhead not justified |

## Common Pitfalls

### Pitfall 1: Forgetting pyproject.toml packages list
**What goes wrong:** New `app.services` and `app.database` packages are created but not listed in `[tool.setuptools]` packages. Package installs (`pip install -e .`) will silently exclude the new packages, causing `ModuleNotFoundError` in production but working fine in development (where `pythonpath = ["."]` in pytest config masks the issue).
**Why it happens:** Setuptools explicit package listing is easy to overlook when the dev test runner uses `pythonpath` directly.
**How to avoid:** Update `pyproject.toml` `[tool.setuptools]` packages in the same commit as the package creation.
**Warning signs:** Tests pass locally but `pip install -e .` followed by running the app fails.

### Pitfall 2: Leaving old modules behind
**What goes wrong:** `app/service.py` or `app/database.py` left on disk after creating packages. Python resolves `app.database` to the `database/` package (directory wins over file), but `app.service` vs `app/service.py` can cause confusion and bytecode cache issues.
**Why it happens:** Forgetting to `git rm` the old files, or doing it in a separate commit.
**How to avoid:** Delete old files in the same operation as creating new packages. Verify with `git status` that old files show as deleted.
**Warning signs:** `__pycache__` contains stale `.pyc` files for old modules.

### Pitfall 3: __pycache__ stale bytecode
**What goes wrong:** Python loads cached `.pyc` from `app/__pycache__/service.cpython-*.pyc` or `app/__pycache__/database.cpython-*.pyc` instead of the new package.
**Why it happens:** Bytecache from before the refactoring persists.
**How to avoid:** The `.pyc` files are in `.gitignore` and will be regenerated. But for local development, clearing `__pycache__` directories is prudent after the refactoring.
**Warning signs:** Import errors that "shouldn't happen" or classes appearing to have old behavior.

### Pitfall 4: Naming collision between file and package
**What goes wrong:** If `app/database.py` exists alongside `app/database/` directory, Python's import resolution becomes undefined.
**Why it happens:** Creating the package directory before deleting the old file.
**How to avoid:** Atomic operation: delete old file, create new package directory, add `__init__.py` -- all before running any imports. In practice, doing this in one git commit prevents any intermediate state.

## Code Examples

### New `app/database/__init__.py`

```python
__all__ = ["ChatsDB"]

from database import ChatsDB
```

### New `app/services/__init__.py`

```python
__all__ = ["ChatService", "LLMService"]

from services import ChatService
from services import LLMService
```

### `app/services/llm_service.py` (moved from service.py lines 1-41)

```python
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel

from config import ModelConfig, ResilienceConfig
from resilience import ResiliencePolicy


class LLMService:
# ... (exact same class body, no changes)
```

### `app/services/chat_service.py` (moved from service.py lines 43-140)

```python
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from api.schema import ExamplesResponse
from database import ChatsDB  # <-- same import path, resolves to new package
from exceptions import ChatHistoryLimitError, InvalidChatError, UnsupportedLanguageError
from models import AIContent, Chat, HumanContent, Message, Role
from services import LLMService  # <-- sibling module import


class ChatService:
# ... (exact same class body, no changes)
```

**Note on `chat_service.py` imports:** `LLMService` is imported from the sibling module `app.services.llm_service` (not from `app.services`) to avoid circular imports through `__init__.py`. `ChatsDB` is imported from `app.database` (the package public API) since there is no circular dependency risk.

### `app/database/chats_db.py` (moved from database.py)
```python
# Exact contents of current app/database.py -- no changes needed
```

## State of the Art

Not applicable -- this is a structural refactoring, not a technology choice. Python package conventions have been stable for years.

## Open Questions

1. **Ruff import sorting**
   - What we know: The project uses ruff with `select = ["E", "W", "F", "I", "UP"]` which includes `I` (isort). Ruff will auto-sort imports when run.
   - What's unclear: Whether the new import paths will trigger ruff formatting changes beyond the direct substitutions.
   - Recommendation: Run `ruff check --fix` after all changes and include any formatting adjustments in the commit.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0 with pytest-asyncio >= 1.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit -x -q` |
| Full suite command | `uv run pytest tests/unit -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SVC-01 | Services package imports resolve correctly | smoke | `uv run python -c "from app.services import ChatService, LLMService"` | N/A -- import check |
| SVC-02 | Database package imports resolve correctly | smoke | `uv run python -c "from app.database import ChatsDB"` | N/A -- import check |
| SVC-03 | All existing tests pass unchanged | unit+e2e | `uv run pytest tests/unit -x -q` | Yes -- existing tests |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit -x -q`
- **Per wave merge:** `uv run pytest tests/unit -v`
- **Phase gate:** Full unit suite green + import smoke tests pass

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. The refactoring success criterion is that ALL existing tests pass with zero modifications to test logic. The only test file change is updating import paths in `tests/unit/conftest.py`.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `app/service.py`, `app/database.py`, all 7 import sites verified via grep
- `app/routers/__init__.py` -- existing re-export pattern with `__all__`
- `pyproject.toml` -- setuptools packages list, pytest config, ruff config

### Secondary (MEDIUM confidence)
- Python packaging documentation on `__init__.py` re-exports and module vs package resolution priority

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, pure Python packaging
- Architecture: HIGH -- existing pattern in `app/routers/__init__.py` provides exact template
- Pitfalls: HIGH -- all pitfalls are well-documented Python packaging behaviors
- Import inventory: HIGH -- verified exhaustively via grep on current codebase

**Research date:** 2026-03-19
**Valid until:** Indefinite -- Python packaging conventions are stable; import inventory valid until codebase changes
