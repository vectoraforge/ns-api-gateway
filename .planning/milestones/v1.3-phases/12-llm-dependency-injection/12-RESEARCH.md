# Phase 12: LLM Dependency Injection - Research

**Researched:** 2026-03-02
**Domain:** FastAPI Dependency Injection — centralizing `app.state` access behind `Depends()`
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- New `app/dependencies.py` module hosts ALL FastAPI dependencies: `get_service`, `get_config`, `get_db`, `get_user_id`
- `get_db` moves from `database.py`, `get_user_id` moves from `auth.py` — originals deleted, not re-exported
- `get_service` reads `app.state.service` (built in lifespan with llm passed to `__init__`)
- `get_config` reads `app.state.config`
- No standalone `get_llm` dependency — LLM stays internal to AnalysisService
- Verifier stays accessed via `app.state` inside `get_user_id` (not a route-level dependency)
- Routes completely stop importing `Request` — clean signatures with only `Depends()` params and body models
- No changes to chain build strategy — `self.chain` stays built once at startup in `AnalysisService.__init__`
- Replace `from langchain_openai import ChatOpenAI` with `BaseChatModel` from `langchain_core` in `services.py`
- Replace `request.app.state.service` with `service: AnalysisService = Depends(get_service)`
- Replace `request.app.state.config` with `config: AppConfig = Depends(get_config)`
- Remove `request: Request` from all route handler signatures
- `dependency_overrides[get_service]` returns real `AnalysisService` constructed with mock LLM
- `dependency_overrides[get_config]` returns mock config
- `dependency_overrides[get_user_id]` returns `'test-user'` directly (skips JWT verification in unit tests)
- `dependency_overrides[get_db]` stays as-is (already uses this pattern)
- No more `app.state.service = ...` or `app.state.verifier = ...` in test setup

### Claude's Discretion

- Route signature cleanup details (param ordering, annotation improvements)
- Internal structure of `app/dependencies.py` (function ordering, grouping)
- Whether `get_service` and `get_config` use `Request` internally or access `app.state` differently

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

Note: REQUIREMENTS.md DI-01/DI-02/DI-03 describe the original deep-decoupling design (get_llm standalone dep, chain per-call). CONTEXT.md explicitly overrides these with the lighter centralization approach. The phase still ships under requirement IDs DI-01/DI-02/DI-03 per roadmap continuity, but the implementation matches the decisions above.

| ID | Original Description (REQUIREMENTS.md) | Actual Implementation (CONTEXT.md decisions) |
|----|----------------------------------------|----------------------------------------------|
| DI-01 | `get_llm()` provides ChatOpenAI via `Depends()` | `get_service()` provides AnalysisService via `Depends()` — no `get_llm` |
| DI-02 | `AnalysisService.analyze()` accepts `llm` as parameter | AnalysisService type annotation: `llm: BaseChatModel` instead of `llm: ChatOpenAI` |
| DI-03 | LangChain chain built per-call inside `analyze()` | Chain stays in `__init__`; all `app.state.*` access from routes goes through `Depends()` |
</phase_requirements>

## Summary

Phase 12 is a dependency centralization refactor. All FastAPI dependency functions (`get_db`, `get_user_id`, and two new ones: `get_service`, `get_config`) move into a single `app/dependencies.py` module. Route handlers stop reading `request.app.state.*` directly and stop importing `Request`; instead they receive dependencies via `Depends()` parameters. The LLM and chain construction remain untouched — `AnalysisService.__init__` still builds `self.chain` at startup. The only change to `services.py` is replacing the `ChatOpenAI` type annotation with `BaseChatModel` from `langchain_core`.

The test impact is the bulk of this phase. Existing tests set `app.state.service`, `app.state.config`, and `app.state.verifier` directly; after this phase they use `dependency_overrides` for `get_service`, `get_config`, and `get_user_id` instead. The `get_db` override pattern already exists and is the template. Two conftest files need migration: `tests/conftest.py` (unit/integration fixture) and `tests/integration/conftest.py`.

**Primary recommendation:** Create `app/dependencies.py` first, wire routes to it, then migrate tests — each step is independently verifiable.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.129 (0.129.0 installed) | `Depends()`, `Request`, `APIRouter` | Project stack; DI system built-in |
| langchain-core | >=1.2 (1.2.14 installed) | `BaseChatModel` type annotation | Vendor-agnostic base class; avoids hard-coding ChatOpenAI in service signature |
| pydantic | >=2.12 | `AppConfig` type in `get_config` return annotation | Already in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langchain-openai | >=1.1 | `ChatOpenAI` — stays in `main.py` lifespan only | Construction of LLM at startup |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `BaseChatModel` in services.py | Keep `ChatOpenAI` annotation | ChatOpenAI annotation couples service to OpenAI; BaseChatModel allows mock injection without subclassing |
| `dependencies.py` single module | Multiple files (deps/service.py, deps/db.py) | Single file is fine at this project scale; splitting only helps when file exceeds ~150 lines |

**Installation:** No new packages required — all libraries already installed.

## Architecture Patterns

### Recommended Project Structure

```
app/
├── dependencies.py      # ALL FastAPI dependencies: get_db, get_user_id, get_service, get_config
├── auth.py              # JWTVerifier, TokenVerifier Protocol — get_user_id removed
├── database.py          # engine, init_engine, session_factory — get_db removed
├── services.py          # AnalysisService — llm: BaseChatModel annotation
├── main.py              # lifespan builds app.state — no changes
└── routers/
    ├── prompts.py       # imports get_service, get_config, get_user_id, get_db from dependencies
    └── root.py          # imports get_service from dependencies
```

### Pattern 1: Reading app.state inside a dependency

The FastAPI standard for accessing application state inside a dependency is to accept `Request` as a parameter. This does **not** expose `Request` to route handlers — `Request` is consumed inside the dependency function, routes only see the return value.

```python
# app/dependencies.py
from fastapi import Request
from services import AnalysisService
from config import AppConfig


def get_service(request: Request) -> AnalysisService:
    return request.app.state.service


def get_config(request: Request) -> AppConfig:
    return request.app.state.config
```

Route handlers then declare:
```python
# app/routers/prompts.py
from app.dependencies import get_service, get_config

async def analyze_prompt(
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
    service: AnalysisService = Depends(get_service),
) -> AnalyzeResponse:
    return await service.analyze(db, body.text, body.lang, user_id, body.chat_id)
```

Routes import `Request` never — they delegate to `Depends()`.

### Pattern 2: Moving get_db and get_user_id — delete originals

The user decision is to delete the original functions from `database.py` and `auth.py` (not re-export). This means any imports like `from app.database import get_db` in route files must change to `from app.dependencies import get_db`. Tests that import `get_db` from `app.database` (both `tests/conftest.py` and `tests/integration/conftest.py`) must update their import.

### Pattern 3: dependency_overrides for all injected dependencies

```python
# tests/conftest.py — after migration
from app.dependencies import get_db, get_service, get_config, get_user_id
from services import AnalysisService


@pytest.fixture
def client(mock_config, mock_examples, mock_chats, mock_db):
    app = FastAPI()
    app.include_router(...)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_config] = lambda: mock_config
    app.dependency_overrides[get_user_id] = lambda: "test-user"

    mock_llm = MagicMock()
    service = AnalysisService(
        prompt="Test prompt for {lang}: {phrase}",
        examples=mock_examples,
        llm=mock_llm,
        policy=policy,
        ...
    )
    app.dependency_overrides[get_service] = lambda: service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
```

No `app.state.service`, `app.state.config`, or `app.state.verifier` assignments needed in tests. The `auth_header` fixture and `make_test_verifier()` are no longer needed in the unit conftest (JWT is bypassed via `dependency_overrides[get_user_id]`).

### Pattern 4: BaseChatModel annotation in services.py

```python
# app/services.py — only change here
from langchain_core.language_models import BaseChatModel  # replaces ChatOpenAI import

class AnalysisService:
    def __init__(
        self,
        ...
        llm: BaseChatModel,  # was: llm: ChatOpenAI
        ...
    ):
        # rest unchanged
        structured_llm = self.llm.with_structured_output(...)
        ...
        self.chain = prompt_template | structured_llm
```

`BaseChatModel` provides `.with_structured_output()` as part of its interface — verified installed.

### Pattern 5: root.py router — get_service

`root.py` currently reads `request.app.state.service.supported_languages` directly. After migration:

```python
# app/routers/root.py
from fastapi import APIRouter, Depends
from app.dependencies import get_service
from services import AnalysisService

router = APIRouter()


@router.get("/")
async def root(service: AnalysisService = Depends(get_service)):
    return {
        "name": "SpeakNative API Gateway",
        "version": version("sn-api-gateway"),
        "supported_languages": service.supported_languages,
    }
```

### Anti-Patterns to Avoid

- **Re-exporting from original modules:** `database.py` keeping a `get_db` that just calls `dependencies.get_db`. The user decision is to delete the originals outright — single source of truth.
- **Passing Request to route handlers:** `get_service(request: Request)` is INSIDE the dependency, not the route. Routes never see `Request`.
- **app.state.service in tests:** After migration, tests must not fall back to setting `app.state.*` — the override must go through `dependency_overrides`.
- **Importing get_db from database.py in tests after migration:** Both conftest files currently do `from app.database import get_db` — these imports must update to `from app.dependencies import get_db`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Accessing app state per-request | Custom middleware or thread-local state | `Depends(get_service)` with `Request` internally | FastAPI DI is the established pattern; middleware can't be overridden in tests |
| Bypassing JWT in tests | Setting verifier to a test stub on app.state | `dependency_overrides[get_user_id] = lambda: "test-user"` | Overrides work at the DI level; app.state approach requires test setup to know about verifier internals |

**Key insight:** FastAPI's `dependency_overrides` is the canonical test isolation mechanism. `app.state.*` in tests is an escape hatch that bypasses the DI graph — after this phase, the DI graph is the only path.

## Common Pitfalls

### Pitfall 1: Import chain break — tests importing get_db from database.py

**What goes wrong:** After `get_db` is deleted from `database.py`, any code that imports it from there raises `ImportError`. Both `tests/conftest.py` line 8 and `tests/integration/conftest.py` line 14 import `from app.database import get_db`.
**Why it happens:** The move is a delete + add, not a rename — Python doesn't auto-redirect imports.
**How to avoid:** Update both conftest files' imports to `from app.dependencies import get_db` as part of the same change that deletes it from `database.py`.
**Warning signs:** `ImportError: cannot import name 'get_db' from 'app.database'` at test collection time.

### Pitfall 2: Import chain break — routers importing from old locations

**What goes wrong:** `app/routers/prompts.py` imports `from app.auth import get_user_id` and `from app.database import get_db`. After deletion, this breaks at startup.
**Why it happens:** Same as above — delete without updating all importers.
**How to avoid:** Global search for all import sites before deleting originals. Check: `app/routers/prompts.py` (both imports), `tests/conftest.py`, `tests/integration/conftest.py`.
**Warning signs:** `ImportError` at app startup or pytest collection.

### Pitfall 3: test_exception_handlers.py uses app.state.verifier directly

**What goes wrong:** `tests/unit/test_exception_handlers.py` sets `app.state.verifier` on a minimal app (not the main client fixture). This test creates its own minimal FastAPI app with auth routes — it does NOT use the `client` fixture and is specifically testing the verifier-from-state pattern.
**Why it happens:** This is an intentional test of the `get_user_id` function's internal behavior, not a test of the route DI graph.
**How to avoid:** Do NOT migrate test_exception_handlers.py. `get_user_id` still reads `app.state.verifier` internally (CONTEXT.md decision) — this test validates exactly that internal behavior and must stay.
**Warning signs:** If test_exception_handlers.py starts failing, the `get_user_id` function broke its internal state access.

### Pitfall 4: Integration conftest still sets app.state.service and app.state.verifier

**What goes wrong:** `tests/integration/conftest.py` has `app.state.config`, `app.state.verifier`, and `app.state.service` — after migration, routes no longer read these. Tests will pass but be testing the wrong thing (overrides shadow state).
**Why it happens:** Integration conftest needs the same migration as unit conftest.
**How to avoid:** Migrate both conftest files in the same commit; run the full test suite after.

### Pitfall 5: test_prompts_endpoints.py sets client.app.state.service.analyze = AsyncMock

**What goes wrong:** After the migration, `client.app.state.service` is not what the route reads — the route reads the service via `get_service` dependency. Mocking `app.state.service.analyze` won't intercept anything.
**Why it happens:** Tests mock the service method on the state object, but DI now returns the override-provided service object (different object reference).
**How to avoid:** After migration, `client.app.dependency_overrides[get_service]` returns a service instance — tests must mock methods on that instance, not `client.app.state.service`. One pattern: expose the service instance from the fixture and mock it directly.

### Pitfall 6: chats router defined in prompts.py, exported as chats_router

**What goes wrong:** `app/routers/__init__.py` exports `chats_router` which is defined in `prompts.py` (not a separate file). Imports must remain consistent — `from app.routers import chats_router` still works.
**Why it happens:** The naming is non-obvious. The chats-related routes are in `prompts.py`.
**How to avoid:** When updating `prompts.py` imports, remember both `router` (prompts_router) and `chats_router` live in that file.

## Code Examples

### get_service and get_config in dependencies.py

```python
# app/dependencies.py
# Source: FastAPI docs — accessing app state via Request in dependencies
from collections.abc import AsyncGenerator

from fastapi import Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenVerifier
from config import AppConfig
from database import session_factory
from exceptions import AuthenticationError, DatabaseNotInitializedError
from services import AnalysisService


def get_service(request: Request) -> AnalysisService:
    return request.app.state.service


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if session_factory is None:
        raise DatabaseNotInitializedError()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_user_id(request: Request, authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Missing Bearer token")
    verifier: TokenVerifier = request.app.state.verifier
    return verifier.verify(token)
```

### prompts.py route — after migration

```python
# app/routers/prompts.py — analyze_prompt after Request removal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from config import AppConfig
from app.dependencies import get_config, get_db, get_service, get_user_id
from services import AnalysisService


# ... other imports

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(
        body: AnalyzeRequest,
        db: AsyncSession = Depends(get_db),
        user_id: str = Depends(get_user_id),
        service: AnalysisService = Depends(get_service),
) -> AnalyzeResponse:
    return await service.analyze(db, body.text, body.lang, user_id, body.chat_id)
```

### Unit conftest.py — after migration

```python
# tests/conftest.py — client fixture after DI migration
from app.dependencies import get_config, get_db, get_service, get_user_id

@pytest.fixture
def client(mock_config, mock_examples, mock_chats, mock_db):
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(prompts_router)
    app.include_router(chats_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    mock_llm = MagicMock()
    policy = ResiliencePolicy(ResilienceConfig(...))
    service = AnalysisService(
        prompt="Test prompt for {lang}: {phrase}",
        examples=mock_examples,
        llm=mock_llm,
        policy=policy,
        history_max_human_messages=50,
        history_max_assistant_messages=50,
        message_max_chars=4096,
        chats=mock_chats,
    )

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_config] = lambda: mock_config
    app.dependency_overrides[get_user_id] = lambda: "test-user"
    app.dependency_overrides[get_service] = lambda: service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
```

No `app.state.*` assignments. No `auth_header` fixture needed (JWT bypassed via override).

### services.py — type annotation change only

```python
# app/services.py — only the import and annotation change
from langchain_core.language_models import BaseChatModel  # replaces: from langchain_openai import ChatOpenAI

class AnalysisService:
    def __init__(
        self,
        ...
        llm: BaseChatModel,        # was: llm: ChatOpenAI
        ...
    ):
        # Everything else UNCHANGED
        structured_llm = self.llm.with_structured_output(AnalyzeResponseLLM, method="json_schema", strict=True)
        ...
        self.chain = prompt_template | structured_llm
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `request.app.state.X` in routes | `Depends(get_X)` in routes | This phase | Routes become testable without real app state |
| `from app.database import get_db` | `from app.dependencies import get_db` | This phase | Single import location for all DI functions |
| `app.state.service = X` in tests | `dependency_overrides[get_service] = lambda: X` | This phase | Tests exercise same DI graph as production |
| `ChatOpenAI` annotation in service | `BaseChatModel` annotation in service | This phase | Service no longer references concrete LLM provider |

**Deprecated/outdated after this phase:**
- `get_db` in `database.py`: deleted, not re-exported
- `get_user_id` in `auth.py`: deleted, not re-exported
- `app.state.service`, `app.state.config`, `app.state.verifier` reads in route handlers: removed

## Open Questions

1. **test_prompts_endpoints.py mock pattern after migration**
   - What we know: Tests currently mock `client.app.state.service.analyze` — a method on the state-stored instance
   - What's unclear: After migration, `get_service` returns the `dependency_overrides`-provided instance. Tests need to mock methods on the instance returned by that override, not on `app.state.service`. The conftest will expose the service instance; tests need to reference it.
   - Recommendation: In the migrated conftest, expose `service` from the fixture (yield a tuple, or use a separate fixture). Tests calling `client.app.state.service.analyze = AsyncMock(...)` must update to mock on the service instance. Planner should create a task to update `test_prompts_endpoints.py` assertions.

2. **auth_header fixture — still needed?**
   - What we know: `auth_header` is currently used as a fixture parameter in `client` and applied via `test_client.headers.update(auth_header)`. After `get_user_id` is overridden to return `"test-user"` directly, no Authorization header is checked.
   - What's unclear: Whether any test explicitly checks that a 401 is returned (those tests may still need auth-less headers to trigger the override path, or they may test the real `get_user_id` separately).
   - Recommendation: Remove `auth_header` from the `client` fixture. Tests that explicitly test 401 behavior (in `test_exception_handlers.py`) have their own auth setup and don't use `client`.

## Sources

### Primary (HIGH confidence)

- Codebase inspection — `app/main.py`, `app/auth.py`, `app/database.py`, `app/services.py`, `app/routers/prompts.py`, `app/routers/root.py` — full read of all files affected by this phase
- `tests/conftest.py`, `tests/integration/conftest.py`, `tests/integration/test_prompts_endpoints.py` — full read of test files requiring migration
- `langchain_core` Python import verification — `BaseChatModel` confirmed importable from `langchain_core.language_models` (1.2.14 installed)
- FastAPI 0.129.0 installed — `Depends()`, `Request`, `dependency_overrides` patterns confirmed in use throughout codebase

### Secondary (MEDIUM confidence)

- FastAPI dependency injection pattern (Request in dependency, not route) — standard documented pattern, verified consistent with existing `get_user_id` implementation in auth.py which uses this exact pattern

### Tertiary (LOW confidence)

- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified installed, import paths confirmed
- Architecture: HIGH — patterns derived from reading actual code; no speculation
- Pitfalls: HIGH — derived from reading all affected files and tracing import chains

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable FastAPI DI patterns; no fast-moving dependencies involved)
