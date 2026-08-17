# Codebase Structure

**Analysis Date:** 2026-02-24

## Directory Layout

```
sn-api-gateway/
├── app/                    # Main application package
│   ├── routers/           # HTTP route handlers
│   │   ├── __init__.py    # Router exports
│   │   ├── prompts.py     # Analysis and chat endpoints
│   │   ├── root.py        # GET / metadata endpoint
│   │   └── health.py      # GET /health/ready probe
│   ├── main.py            # FastAPI app initialization and lifespan
│   ├── services.py        # AnalysisService, LLMExecutionGate, CircuitBreaker
│   ├── chats.py           # Chat and message database operations
│   ├── models.py          # SQLModel ORM: Chat, Message
│   ├── schema.py          # Pydantic request/response schemas
│   ├── config.py          # Configuration models (app/db/model settings)
│   ├── database.py        # SQLAlchemy async engine and session factory
│   ├── auth.py            # JWT user_id extraction
│   ├── errors.py          # Custom exception handlers
│   └── exceptions.py      # Custom exception classes
├── config/                # Configuration files
│   ├── config.yaml        # App configuration (db, model, limits)
│   ├── examples.yaml      # Language-specific phrase examples
│   └── prompt.txt         # System prompt for LLM
├── tests/                 # Test suite
│   ├── conftest.py        # Pytest fixtures and setup
│   ├── unit/              # Unit tests
│   │   ├── test_config.py
│   │   ├── test_models.py
│   │   └── test_services.py
│   ├── integration/       # Integration tests
│   │   ├── test_prompts_endpoints.py
│   │   └── test_root_endpoint.py
│   └── llm/               # Tests that call real LLM (optional)
│       └── test_real_llm.py
├── migrations/            # Database migrations (Alembic)
├── pyproject.toml         # Project metadata and dependencies
└── .env                   # Environment variables (not committed)
```

## Directory Purposes

**app/:**
- Purpose: Main application source code
- Contains: FastAPI initialization, business logic, data access, HTTP handlers
- Key files: `main.py` (entry point), `services.py` (core logic), `models.py` (ORM)

**app/routers/:**
- Purpose: HTTP request handlers organized by domain
- Contains: FastAPI routes with request validation, dependency injection, response serialization
- Key files: `prompts.py` (analysis and chat endpoints), `health.py` (readiness probe)

**config/:**
- Purpose: Application configuration and prompt content
- Contains: YAML configurations, system prompt text, language examples
- Key files: `config.yaml` (loaded at startup), `prompt.txt` (LLM system prompt), `examples.yaml` (language data)

**tests/:**
- Purpose: Test suite with unit, integration, and optional LLM tests
- Contains: Pytest fixtures, unit test cases, endpoint integration tests
- Key files: `conftest.py` (shared fixtures), `unit/` (isolated tests), `integration/` (endpoint tests)

## Key File Locations

**Entry Points:**
- `app/main.py`: FastAPI app factory with lifespan context manager; registers routers and exception handlers
- `pyproject.toml`: Project metadata; pytest configuration

**Configuration:**
- `app/config.py`: Pydantic models for `MainConfig`, `AppConfig`, `DatabaseConfig`, `ModelConfig` loaded at startup
- `config/config.yaml`: Database URL, model name, concurrency limits, history size limits
- `config/prompt.txt`: LLM system prompt (dynamic prompt engineering)
- `config/examples.yaml`: Language code → list of example phrases

**Core Logic:**
- `app/services.py`: `AnalysisService` (orchestrates analysis), `LLMExecutionGate` (concurrency control), `CircuitBreaker` (resilience)
- `app/chats.py`: `Chats` class for chat/message CRUD and history management
- `app/routers/prompts.py`: Endpoints for `/prompts/analyze`, `/prompts/examples`, `/chats/**`

**Data Access:**
- `app/database.py`: Async SQLAlchemy engine initialization and session factory
- `app/models.py`: SQLModel ORM definitions for `Chat` and `Message` tables

**Testing:**
- `tests/conftest.py`: Pytest fixtures (app instance, async test client)
- `tests/unit/test_services.py`: Tests for `AnalysisService`, circuit breaker, execution gate
- `tests/integration/test_prompts_endpoints.py`: Endpoint tests for analysis and chat flows

## Naming Conventions

**Files:**
- Routers: `{feature}.py` in `app/routers/` (e.g., `prompts.py`, `root.py`, `health.py`)
- Business logic: Single-responsibility classes in `app/` (e.g., `services.py`, `chats.py`, `auth.py`)
- Tests: `test_{module}.py` in `tests/{category}/` (e.g., `test_services.py`, `test_prompts_endpoints.py`)
- Configuration: `config.yaml`, `examples.yaml`, `prompt.txt`

**Directories:**
- Application code: lowercase `app`, `config`, `tests`
- Python packages: lowercase with `__init__.py` (e.g., `app/routers/`)
- Test categories: `unit/`, `integration/`, `llm/`

**Classes:**
- Service classes: PascalCase, single responsibility (e.g., `AnalysisService`, `Chats`, `CircuitBreaker`)
- Exception classes: PascalCase ending in `Error` (e.g., `UnsupportedLanguageError`, `InvalidChatError`)
- Configuration classes: PascalCase ending in `Config` (e.g., `AppConfig`, `DatabaseConfig`)

**Functions:**
- Private functions: prefix with `_` (e.g., `_invoke()`, `_extract_status_code()`)
- Async functions: prefix with `async` keyword (e.g., `async def analyze()`)
- Endpoint handlers: verb-first, descriptive (e.g., `analyze_prompt()`, `list_chat_messages()`)

**Variables:**
- Constants: UPPERCASE (e.g., in exceptions for status codes if used)
- Private instance variables: prefix with `_` (e.g., `self._semaphore`, `self._failure_count`)
- Config nested fields: snake_case (e.g., `db.pool_size`, `model.max_tokens`)

## Where to Add New Code

**New Feature (e.g., user feedback on analyses):**
- Primary code: `app/services.py` - Add methods to `AnalysisService` for feedback handling
- Database: `app/models.py` - Add `Feedback` SQLModel; `app/chats.py` - Add feedback CRUD methods
- Endpoints: `app/routers/prompts.py` - Add new routes under appropriate router prefix
- Tests: `tests/integration/test_prompts_endpoints.py` - Add endpoint tests; `tests/unit/test_services.py` - Add service logic tests
- Configuration: `app/config.py` - Add new config fields if needed to `AppConfig`

**New Component/Module (e.g., separate "corrections" service):**
- Implementation: `app/corrections.py` - Create standalone module with service class
- Injection: `app/main.py` - Initialize in lifespan, store in `app.state`
- Integration: Use as dependency in routers via `request.app.state.corrections`
- Tests: `tests/unit/test_corrections.py` - Mirror service structure

**Utilities (e.g., text normalization helper):**
- Shared helpers: `app/utils.py` (create if doesn't exist) or add to existing utility module
- Import: Use absolute imports `from app.utils import normalize_text`
- Tests: `tests/unit/test_utils.py` - Isolated function tests

**New Endpoint:**
- Endpoint code: Add to appropriate router in `app/routers/` (or create new router if needed)
- Registration: Import and `app.include_router()` in `app/main.py`
- Dependencies: Use `Depends(get_user_id)`, `Depends(get_db)` for common injections
- Response model: Define Pydantic schema in `app/schema.py`, use as `response_model=` parameter
- Tests: Add to appropriate integration test file

**New Exception:**
- Definition: Add class to `app/exceptions.py` extending `ServiceError`
- Handler: Add handler function and registration to `app/errors.py`
- HTTP mapping: Define status code and response detail in handler

## Special Directories

**config/:**
- Purpose: Runtime configuration and prompts
- Generated: No
- Committed: Yes (config.yaml, examples.yaml, prompt.txt all committed)
- Notes: Do not add secrets here; use environment variables instead

**tests/:**
- Purpose: Test suite
- Generated: No (but pytest creates `.pytest_cache/`, `__pycache__/`)
- Committed: Yes (all test files and fixtures)
- Notes: Mark expensive tests (LLM calls) with `@pytest.mark.llm`; tests run with `pytest -m 'not llm'` by default

**migrations/:**
- Purpose: Database schema migrations (Alembic)
- Generated: No (manually created and committed)
- Committed: Yes
- Notes: Run migrations via `alembic upgrade head`

**.planning/codebase/:**
- Purpose: GSD planning documents (this file and related analysis)
- Generated: Yes (by mapping tool)
- Committed: Yes
- Notes: Read-only reference; updated when codebase structure significantly changes

**pgdata/:**
- Purpose: PostgreSQL data files (local development only)
- Generated: Yes
- Committed: No (in .gitignore)
- Notes: Created by Docker; deleted on container shutdown

## Module Import Patterns

**Standard pattern:**

```python
# External imports (alphabetical)
import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

# FastAPI
from fastapi import APIRouter, Depends

# SQLAlchemy
from sqlalchemy.ext.asyncio import AsyncSession

# Internal imports (alphabetical by module)
from database import get_db
from app.schema import AnalyzeRequest, AnalyzeResponse
from services import AnalysisService
```

**Path aliases:**
- No import aliases (e.g., `@` or similar) configured
- All imports use absolute paths from project root: `from app.X import Y`
- Tests use same absolute import pattern: `from app.services import AnalysisService`

---

*Structure analysis: 2026-02-24*
