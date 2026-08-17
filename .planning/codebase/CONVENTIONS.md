# Coding Conventions

**Analysis Date:** 2026-02-24

## Naming Patterns

**Files:**
- Lowercase with underscores for modules: `services.py`, `exceptions.py`, `chats.py`
- Router files: `prompts.py`, `health.py`, `root.py`
- Test files: `test_services.py`, `test_config.py` (matches module being tested)
- Schema file: `schema.py` (singular)
- Model file: `models.py` (plural for SQLAlchemy ORM models)

**Functions:**
- snake_case throughout: `get_examples()`, `analyze()`, `load_history()`, `_decode_jwt_payload()`
- Private helper functions prefixed with underscore: `_extract_status_code()`, `_is_transient_error()`, `_encode_cursor()`
- Async functions use plain snake_case (no special prefix): `async def analyze()`, `async def create_chat()`

**Variables:**
- snake_case for all local variables and parameters: `llm_response`, `chat_id`, `user_id`, `max_concurrency`
- Type unions use pipe operator (Python 3.10+ syntax): `str | None`, `dict[str, list[str]]`
- Private class attributes prefixed with underscore: `self._failure_count`, `self._opened_at`, `self._lock`

**Types:**
- PascalCase for classes: `AnalysisService`, `CircuitBreaker`, `LLMExecutionGate`, `Chat`, `Message`
- Exception classes inherit from appropriate base: `ServiceError`, `UnsupportedLanguageError`
- Request/Response classes in `schema.py`: `AnalyzeRequest`, `AnalyzeResponse`, `ChatMessageRequest`, `Issue`

**Constants:**
- Used sparingly; embedded in configs or as class attributes
- Configuration values use typed Pydantic models: `ModelConfig`, `DatabaseConfig`, `AppConfig`

## Code Style

**Formatting:**
- Ruff configured as linter (presence in dependencies)
- No explicit prettier/black config found, code follows PEP 8
- Line length appears to be standard ~100-120 characters
- Imports sorted in standard Python order

**Linting:**
- Ruff configured (visible in `pyproject.toml` dependencies)
- Pragma comment used for conditional imports: `# pragma: no cover`

## Import Organization

**Order:**
1. Standard library imports: `import asyncio`, `import logging`, `from datetime import datetime`
2. Third-party framework imports: `from fastapi import`, `from sqlalchemy import`, `from langchain import`
3. Local application imports: `from app.services import`, `from app.models import`

**Path Aliases:**
- No path aliases used; all imports use absolute paths from `app.*`
- Examples: `from app.database import get_db`, `from app.routers import prompts_router`

**Actual pattern from codebase** (`app/services.py`):

```python
import asyncio
import time
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats import Chats
from app.schema import AnalyzeResponse, ExamplesResponse
from exceptions import (

...)
```

## Error Handling

**Patterns:**
- Custom exceptions inherit from `ServiceError` base class (`app/exceptions.py`)
- Exceptions carry relevant data as attributes: `UnsupportedLanguageError` stores `lang` and `supported`
- HTTP layer uses FastAPI exception handlers to convert service exceptions to JSON responses
- Generic exception handler logs with `exc_info=True` for full tracebacks
- Bare `except Exception` used cautiously with `from exc` or `from None` to control traceback

**Example from services.py:**
```python
except QueueFullError:
    raise
except CircuitOpenError:
    raise
except Exception as e:
    await self.circuit_breaker.record_failure()
    if attempt >= self.retry_max_attempts or not _is_transient_error(e):
        raise AnalysisError(str(e)) from e
```

## Logging

**Framework:** Python standard `logging` module (not third-party)

**Patterns:**
- Module-level logger initialized: `logger = logging.getLogger(__name__)`
- Used for lifecycle events: `logger.info("Starting API Gateway")`
- Used for errors with context: `logger.error("Analysis failed: %s", exc)`
- Httpx and httpcore loggers suppressed to WARNING level in setup

**Actual pattern from main.py:**
```python
logger = logging.getLogger(__name__)

def setup_logging(log_level: str):
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
```

## Comments

**When to Comment:**
- Minimal commentary; code is self-documenting through clear naming
- Comments appear only for non-obvious logic
- Example: `# pragma: no cover` for conditional imports in error handling

**JSDoc/Docstrings:**
- Pydantic models use `Field(description="...")` for schema documentation
- Function docstrings are minimal or absent; types are explicit in signatures
- Class docstrings present for custom exceptions, explaining purpose

**Example from exceptions.py:**
```python
class UnsupportedLanguageError(ServiceError):
    """Raised when an unsupported language is requested"""
    def __init__(self, lang: str, supported: list[str]):
        self.lang = lang
        self.supported = supported
```

## Function Design

**Size:** Functions are compact, typically 5-30 lines; complex logic split into private helpers

**Parameters:**
- Explicit typed parameters (no *args, **kwargs)
- Dependency injection via parameters: `db: AsyncSession = Depends(get_db)`
- FastAPI Depends pattern used consistently in routers
- Dataclass-like initialization in services: `AnalysisService.__init__` takes many parameters

**Return Values:**
- Explicit return types: `async def analyze(...) -> AnalyzeResponse:`
- Pydantic models for complex returns
- Raise exceptions for errors (no None returns for errors)
- Union types for optional returns: `dict | None`

**Async/Await:**
- Async used for I/O operations (database, LLM calls)
- `asynccontextmanager` for resource management: lifespan in FastAPI
- `asyncio.Lock` for thread-safe state management in CircuitBreaker

## Module Design

**Exports:**
- Each module is self-contained; imports are explicit
- Routers defined in `app/routers/` and imported in `main.py`
- Services instantiated in lifespan context and stored in `app.state`

**Barrel Files:**
- `app/routers/__init__.py` re-exports routers: `from app.routers.prompts import prompts_router`
- Simplifies imports in main: `from app.routers import prompts_router`

**Example from routers/__init__.py**:

```python
from routers import router as prompts_router, chats_router
from routers.health import router as health_router
from routers.root import router as root_router
```

## Type Annotations

**Usage:** Full type annotations throughout:
- Function parameters: `async def analyze(self, db: AsyncSession, text: str, lang: str, user_id: str, chat_id: UUID | None = None) -> AnalyzeResponse:`
- Class attributes explicitly typed via SQLModel/Pydantic
- Modern union syntax: `str | None` instead of `Optional[str]`
- Generic collections typed: `dict[str, list[str]]`, `list[HumanMessage | AIMessage]`

## Configuration

**Pydantic for validation:**
- `BaseSettings` for environment-based config: `class MainConfig(BaseConfig)`
- `BaseModel` for nested structures: `class ModelConfig(BaseModel)`
- Field validators with constraints: `ge=0.0, le=2.0` for temperature, `ge=1` for min values
- Custom validator via `@model_validator(mode='after')` for loading files

---

*Convention analysis: 2026-02-24*
