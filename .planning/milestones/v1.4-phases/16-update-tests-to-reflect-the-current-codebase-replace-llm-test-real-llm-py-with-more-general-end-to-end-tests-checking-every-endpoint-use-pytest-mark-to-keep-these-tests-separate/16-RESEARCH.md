# Phase 16: Update Tests - Research

**Researched:** 2026-03-17
**Domain:** Python test infrastructure (pytest, FastAPI TestClient, Firebase Auth, async DB testing)
**Confidence:** HIGH

## Summary

Phase 16 replaces `tests/llm/` and `tests/integration/` with a unified `tests/e2e/` directory, reorganizes conftest files, and covers every endpoint with real-infrastructure end-to-end tests. The codebase already has the two pytest markers (`@pytest.mark.db` and `@pytest.mark.llm`) registered in `pyproject.toml` with `addopts = "-m 'not llm and not db'"` excluding them from default runs.

The e2e tests need real Firebase ID tokens because the production `app.api.main:app` lifespan configures a `JWTVerifier` backed by Firebase JWKS. The approach is to call Firebase's REST API (`signInWithPassword`) at fixture time to obtain a real ID token for a dedicated test user. The synchronous `TestClient` context manager (`with TestClient(app) as client:`) triggers lifespan events, so the real app boots with real config, real DB engine, and real LLM chain -- no test assembly needed.

A secondary finding is that the current unit tests in `tests/unit/test_services.py` import `ChatResponseLLM` from `app.api.schema`, but this class does not exist in the codebase. The chain actually returns `AIContent` objects (see `app/service.py` line 15). The fixtures in `tests/conftest.py` (mocked) need to move to `tests/unit/conftest.py`. The root `tests/conftest.py` should become minimal (shared constants only). No `__init__.py` files exist in any test directory currently.

**Primary recommendation:** Use synchronous `TestClient(app)` with the real `app.api.main:app` for all e2e tests. Obtain Firebase tokens via REST API at session scope. Seed DB data via ORM fixtures with rollback-per-test for non-LLM tests.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- E2E = real PostgreSQL + real OpenAI LLM + real Firebase auth
- Real FastAPI app from `app.api.main` with lifespan running
- Real Firebase tokens from production Firebase project with dedicated test user
- Rollback-per-test via db_session fixture for data isolation
- Assertions check response structure only (status code, required fields, correct types) -- not LLM content
- Two markers: `@pytest.mark.db` and `@pytest.mark.llm` (both already in pyproject.toml)
- LLM endpoints: both `@db` and `@llm`; non-LLM endpoints: `@db` only
- Default addopts unchanged: `-m 'not llm and not db'`
- Happy path only; one multi-step lifecycle flow test
- Cross-user isolation tests move from integration/ to e2e/
- Remove entirely: `tests/llm/`, `tests/integration/`, `tests/jwt_helpers.py`
- New `tests/e2e/` directory with specific file organization per CONTEXT.md
- Mocked fixtures move from `tests/conftest.py` to `tests/unit/conftest.py`
- `tests/conftest.py` becomes minimal (shared config only)

### Claude's Discretion
- Firebase Admin SDK setup for generating test tokens
- Exact fixture design for real app client with auth headers
- Test data seeding helpers for non-LLM endpoint tests
- conftest.py minimal shared content

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | Test framework | Already installed, pyproject.toml configured |
| pytest-asyncio | 1.3.0 | Async test support | Already installed, `asyncio_mode = "auto"` configured |
| pytest-dotenv | 0.5+ | Load .env for test config | Already installed, `env_files = [".env"]` in pyproject.toml |
| httpx | 0.28.1 | Required by FastAPI TestClient | Already installed as dev dependency |
| FastAPI TestClient | (bundled) | Synchronous HTTP test client | Triggers lifespan events via `with TestClient(app) as client:` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| requests | (stdlib-adjacent) | Firebase REST API token acquisition | Session-scoped fixture to get real Firebase ID tokens |
| sqlalchemy (asyncpg) | (already installed) | Direct DB seeding in fixtures | Non-LLM tests that need pre-seeded data |

### No New Dependencies Needed

All required libraries are already in `pyproject.toml` dev dependencies. The Firebase token acquisition uses the REST API via `httpx` (already installed) -- no `firebase-admin` SDK needed.

## Architecture Patterns

### Recommended Test Structure
```
tests/
  conftest.py              # Minimal: shared constants only (TEST_OWNER, etc.)
  unit/
    conftest.py            # Mocked fixtures moved from tests/conftest.py
    test_config.py         # (unchanged)
    test_error_contract.py # (unchanged)
    test_exception_handlers.py # (unchanged)
    test_jwt_security.py   # (unchanged)
    test_models.py         # (unchanged)
    test_services.py       # (unchanged, but fix ChatResponseLLM import)
  e2e/
    conftest.py            # Real-infra fixtures: app client, db_session, firebase auth
    test_chats.py          # POST /chats, POST /chats/{id} (@db @llm)
    test_chat_queries.py   # GET /chats, GET /chats/{id}, DELETE /chats/{id} (@db)
    test_examples.py       # GET /examples (@db)
    test_health.py         # GET /health/ready (@db)
    test_root.py           # GET / (@db)
    test_isolation.py      # Cross-user isolation (@db)
    test_flows.py          # Full lifecycle flow (@db @llm)
```

### Pattern 1: Synchronous TestClient with Real App and Lifespan
**What:** Import `app` from `app.api.main` and wrap in `TestClient(app)` context manager. The lifespan runs: real config loaded, real DB engine created, real LLM chain initialized, real JWTVerifier created.
**When to use:** All e2e tests.
**Example:**

```python
# Source: Existing pattern in tests/llm/test_real_llm.py + FastAPI docs
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture(scope="module")
def real_client(firebase_token):
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {firebase_token}"
        yield client
```

### Pattern 2: Firebase Token via REST API
**What:** Call Firebase's `signInWithPassword` REST endpoint to get a real ID token for a dedicated test user. Cache at session scope since tokens last 1 hour.
**When to use:** e2e/conftest.py session-scoped fixture.
**Example:**
```python
# Source: Firebase Auth REST API docs
import httpx

FIREBASE_API_KEY = os.environ["FIREBASE_API_KEY"]
FIREBASE_TEST_EMAIL = os.environ["FIREBASE_TEST_EMAIL"]
FIREBASE_TEST_PASSWORD = os.environ["FIREBASE_TEST_PASSWORD"]

@pytest.fixture(scope="session")
def firebase_token():
    """Get a real Firebase ID token for the dedicated test user."""
    response = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={FIREBASE_API_KEY}",
        json={"email": FIREBASE_TEST_EMAIL,
              "password": FIREBASE_TEST_PASSWORD,
              "returnSecureToken": True}
    )
    response.raise_for_status()
    return response.json()["idToken"]
```

### Pattern 3: Rollback-Per-Test DB Session for Seeded Data
**What:** Create an async session, yield it to the test, then rollback on teardown. Tests that seed data directly via ORM get automatic cleanup.
**When to use:** Non-LLM e2e tests that need pre-seeded chats/messages.
**Example:**
```python
# Source: Existing pattern in tests/integration/conftest.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

@pytest.fixture(scope="module")
def db_engine():
    engine = create_async_engine(TEST_DB_URL, pool_size=2, max_overflow=0)
    yield engine
    engine.sync_engine.dispose()

@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
```

### Pattern 4: Structure-Only Assertions for LLM Responses
**What:** Assert on status codes, field presence, and types -- never on specific LLM-generated content.
**When to use:** All tests involving LLM endpoints (POST /chats, POST /chats/{id}).
**Example:**
```python
def test_create_chat(self, real_client):
    response = real_client.post("/chats", json={"phrase": "I going home.", "lang": "en"})
    assert response.status_code == 200
    data = response.json()
    assert "chat_id" in data
    assert data["role"] == "ai"
    assert "content" in data
    assert "created_at" in data
```

### Anti-Patterns to Avoid
- **Fake JWT tokens for e2e tests:** The current `test_real_llm.py` creates base64-encoded fake JWTs. This CANNOT work with the real app's `JWTVerifier` which validates RS256 signatures against Firebase JWKS. Must use real Firebase tokens.
- **Building a test FastAPI app for e2e:** Don't assemble `FastAPI()` + `include_router()` manually for e2e. Import the real `app` from `app.api.main` to test the actual boot path.
- **Asserting on LLM content values:** LLM output is non-deterministic. Assert structure (keys exist, types correct), not content (specific words/sentences).
- **Mixing mocked and real fixtures:** Unit tests use mocked fixtures; e2e tests use real infrastructure. Never share fixtures between the two categories.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Firebase test tokens | Mock JWT creation, fake base64 tokens | Firebase REST API `signInWithPassword` | Real JWTVerifier validates RS256 against JWKS; fakes won't pass |
| Test app assembly | `FastAPI()` + routers + handlers | `from app.api.main import app` | Tests the real boot path including lifespan |
| DB test isolation | Manual DELETE/cleanup after each test | Rollback-per-test via async session fixture | Automatic, no cleanup code needed, handles test failures |
| Token caching | Per-test token acquisition | Session-scoped fixture | Firebase tokens last 1 hour; session scope avoids redundant API calls |

**Key insight:** The existing `test_real_llm.py` creates fake JWTs that would fail with the real `JWTVerifier`. The e2e tests must use real Firebase tokens obtained via the REST API.

## Common Pitfalls

### Pitfall 1: Fake JWTs Failing Real Verification
**What goes wrong:** The current `test_real_llm.py` creates base64-encoded fake tokens. With the real app, `JWTVerifier` validates RS256 signatures against Firebase's JWKS endpoint. Fake tokens return 401.
**Why it happens:** The old test skipped real auth by assembling a test app without proper verification.
**How to avoid:** Use Firebase REST API to get real ID tokens for a dedicated test user.
**Warning signs:** All e2e tests returning 401 Unauthorized.

### Pitfall 2: TestClient Without Context Manager Skips Lifespan
**What goes wrong:** Using `client = TestClient(app)` without `with` statement doesn't trigger lifespan startup. `app.state` attributes (config, session_factory, verifier, chain) are never set.
**Why it happens:** TestClient only triggers lifespan when used as context manager.
**How to avoid:** Always use `with TestClient(app) as client:` pattern.
**Warning signs:** `AttributeError: 'State' object has no attribute 'config'`.

### Pitfall 3: Conftest Fixture Name Collisions After Move
**What goes wrong:** If `tests/conftest.py` still defines `mock_config` or `client` fixtures, they shadow the ones in `tests/unit/conftest.py` (pytest resolves nearest conftest first, but root conftest is always loaded).
**Why it happens:** Forgetting to remove moved fixtures from the root conftest.
**How to avoid:** Root conftest must ONLY contain shared constants. All mocked fixtures must be in `tests/unit/conftest.py`.
**Warning signs:** Unit tests using wrong fixtures, unexpected test failures.

### Pitfall 4: DB Session Conflict Between Real App and Test Seeding
**What goes wrong:** The real app creates its own DB sessions via `session_factory` in lifespan. Test-seeded data via a separate `db_session` fixture lives in a different transaction. If the test commits seeded data, the app can see it. If the test rolls back, the app never saw it.
**Why it happens:** Two independent DB connections/sessions.
**How to avoid:** For DB-only tests that seed data, the real app session reads committed data. Seed data must be committed (not just added), then cleaned up. Use `create_chat` helper that commits, then `cleanup_chat` in finally blocks. For LLM tests, no seeding needed -- the real app creates data through normal flow.
**Warning signs:** Tests pass individually but fail when run together; 404s on seeded data.

### Pitfall 5: ChatResponseLLM Import Error in Unit Tests
**What goes wrong:** `tests/unit/test_services.py` imports `ChatResponseLLM` from `app.api.schema` but this class does not exist. The chain returns `AIContent` objects.
**Why it happens:** Name mismatch from Phase 15 planning vs implementation.
**How to avoid:** Fix the import to use `AIContent` from `app.models` and update mock return values accordingly.
**Warning signs:** `ImportError: cannot import name 'ChatResponseLLM' from 'app.api.schema'`.

### Pitfall 6: Async Fixtures with Synchronous TestClient
**What goes wrong:** TestClient runs a background event loop. Mixing async fixtures (like `db_session`) with synchronous `TestClient` calls can cause event loop conflicts.
**Why it happens:** `TestClient` manages its own event loop internally.
**How to avoid:** Keep e2e test methods synchronous (`def test_...`). Only use async for fixtures that interact directly with the DB for seeding. For DB-seeded tests, seed data in an async fixture before yielding, then use the synchronous client.
**Warning signs:** `RuntimeError: This event loop is already running`.

## Code Examples

### e2e/conftest.py -- Real Infrastructure Fixtures

```python
# Core fixture pattern for e2e tests
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="session")
def firebase_token():
    """Obtain a real Firebase ID token via REST API."""
    api_key = os.environ["FIREBASE_API_KEY"]
    email = os.environ["FIREBASE_TEST_EMAIL"]
    password = os.environ["FIREBASE_TEST_PASSWORD"]
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={api_key}",
        json={"email": email, "password": password, "returnSecureToken": True},
    )
    resp.raise_for_status()
    return resp.json()["idToken"]


@pytest.fixture(scope="module")
def real_client(firebase_token):
    """TestClient wired to the real app with Firebase auth."""
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {firebase_token}"
        yield client
```

### e2e/conftest.py -- DB Seeding Fixtures (for non-LLM tests)

```python
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import AIContent, Chat, HumanContent, Message, Role

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/nativespeaker"


@pytest.fixture(scope="module")
def db_engine():
    engine = create_async_engine(TEST_DB_URL, pool_size=2, max_overflow=0)
    yield engine
    engine.sync_engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


async def create_chat(session: AsyncSession, user_id: str):
    """Insert a chat with human+AI message pair, return chat_id."""
    chat_id = uuid4()
    chat = Chat(id=chat_id, user_id=user_id, title="test phrase")
    human = Message(chat_id=chat_id, role=Role.human,
                    content=HumanContent(phrase="test phrase"))
    ai = Message(chat_id=chat_id, role=Role.ai,
                 content=AIContent(response="test", issues=[], suggestions=[]))
    chat.messages.append(human)
    chat.messages.append(ai)
    session.add(chat)
    await session.commit()
    return chat_id


async def cleanup_chat(session: AsyncSession, chat_id):
    chat = await session.get(Chat, chat_id)
    if chat:
        await session.delete(chat)
        await session.commit()
```

### e2e/test_chats.py -- LLM Endpoint Test Pattern
```python
import pytest


@pytest.mark.db
@pytest.mark.llm
class TestCreateChat:
    def test_create_chat_english(self, real_client):
        response = real_client.post("/chats",
                                    json={"phrase": "I am going to home.", "lang": "en"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"
        assert "content" in data
        assert "created_at" in data
```

### e2e/test_chat_queries.py -- DB-Only Seeded Test Pattern
```python
import pytest

from tests.e2e.conftest import cleanup_chat, create_chat

TEST_OWNER = "test-user-uid"  # Must match Firebase test user's UID


@pytest.mark.db
class TestGetChatMessages:
    @pytest.mark.asyncio
    async def test_get_messages(self, real_client, db_session):
        chat_id = await create_chat(db_session, TEST_OWNER)
        try:
            response = real_client.get(f"/chats/{chat_id}")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
        finally:
            await cleanup_chat(db_session, chat_id)
```

### Root conftest.py -- Minimal Shared Content
```python
# tests/conftest.py -- shared constants only
# All mocked fixtures live in tests/unit/conftest.py
# All real-infra fixtures live in tests/e2e/conftest.py
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fake base64 JWTs in `test_real_llm.py` | Real Firebase tokens via REST API | Phase 16 | Fake tokens fail real JWTVerifier |
| Separate integration/ and llm/ dirs | Unified e2e/ directory | Phase 16 | Simpler structure, consistent patterns |
| `tests/conftest.py` has all mocked fixtures | Split: unit/conftest.py (mocked) + e2e/conftest.py (real) | Phase 16 | No fixture leakage between test categories |
| Manual test app assembly | Import real `app` from `app.api.main` | Phase 16 | Tests actual boot path + lifespan |

**Deprecated/outdated:**
- `tests/jwt_helpers.py`: Ephemeral RSA keypair helper -- only used by unit JWT tests which have their own fixtures. Remove.
- `ChatResponseLLM` in `test_services.py`: Class does not exist. Chain returns `AIContent`. Must fix.

## Open Questions

1. **Firebase test user UID must match seeded data owner**
   - What we know: The real app extracts `user_id` from the Firebase token's `sub` claim. DB-only tests seed data for a specific `user_id`.
   - What's unclear: The exact UID of the Firebase test user (it's in the Firebase project).
   - Recommendation: Discover the test user's UID by decoding a token or checking Firebase console. Store as env var `FIREBASE_TEST_USER_ID` or derive from the token response's `localId` field.

2. **DB URL for e2e test environment**
   - What we know: Integration tests hardcode `postgresql+asyncpg://postgres:postgres@localhost:5432/nativespeaker`. The real app reads DB config from `config/config.yaml` + env vars.
   - What's unclear: Whether the e2e DB URL should be hardcoded in conftest or read from the same config as the app.
   - Recommendation: Read from env var with fallback to the hardcoded default. The real app and the seeding fixture must point to the same database.

3. **Session scope vs module scope for TestClient**
   - What we know: `scope="module"` creates one client per test file. `scope="session"` creates one for all e2e tests.
   - What's unclear: Whether the app's lifespan (which creates DB engine, LLM chain, etc.) handles being started/stopped multiple times gracefully.
   - Recommendation: Use `scope="module"` for safety (matches existing pattern). The lifespan cleanup disposes the engine, so each module gets a fresh app state.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `pytest -m 'db and not llm' -x -q` |
| Full suite command | `pytest -m 'db' -x -q` (includes LLM tests) |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| E2E-01 | POST /chats returns structured response | e2e | `pytest tests/e2e/test_chats.py -m 'llm' -x` | Wave 0 |
| E2E-02 | POST /chats/{id} followup works | e2e | `pytest tests/e2e/test_chats.py -m 'llm' -x` | Wave 0 |
| E2E-03 | GET /chats returns chat list | e2e | `pytest tests/e2e/test_chat_queries.py -m 'db' -x` | Wave 0 |
| E2E-04 | GET /chats/{id} returns messages | e2e | `pytest tests/e2e/test_chat_queries.py -m 'db' -x` | Wave 0 |
| E2E-05 | DELETE /chats/{id} removes chat | e2e | `pytest tests/e2e/test_chat_queries.py -m 'db' -x` | Wave 0 |
| E2E-06 | GET /examples returns examples | e2e | `pytest tests/e2e/test_examples.py -m 'db' -x` | Wave 0 |
| E2E-07 | GET /health/ready returns up | e2e | `pytest tests/e2e/test_health.py -m 'db' -x` | Wave 0 |
| E2E-08 | GET / returns app info | e2e | `pytest tests/e2e/test_root.py -m 'db' -x` | Wave 0 |
| E2E-09 | Cross-user isolation enforced | e2e | `pytest tests/e2e/test_isolation.py -m 'db' -x` | Wave 0 |
| E2E-10 | Full lifecycle flow works | e2e | `pytest tests/e2e/test_flows.py -m 'llm' -x` | Wave 0 |
| UNIT-FIX | Unit tests still pass after conftest move | unit | `pytest tests/unit/ -x` | Existing (needs fix) |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/ -x -q` (verify unit tests not broken)
- **Per wave merge:** `pytest -m 'db and not llm' -x -q` (all DB e2e + unit)
- **Phase gate:** `pytest -m 'db' -x -q` (full suite including LLM tests)

### Wave 0 Gaps
- [ ] `tests/e2e/conftest.py` -- real-infra fixtures (firebase token, real_client, db_engine, db_session, seeding helpers)
- [ ] `tests/unit/conftest.py` -- moved mocked fixtures from root conftest
- [ ] `tests/conftest.py` -- reduced to minimal shared content
- [ ] Environment variables for Firebase test credentials (FIREBASE_API_KEY, FIREBASE_TEST_EMAIL, FIREBASE_TEST_PASSWORD)
- [ ] Fix `ChatResponseLLM` import in `tests/unit/test_services.py` -> use `AIContent`

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `app/api/main.py`, `app/api/dependencies.py`, `app/auth.py`, `app/service.py`, `app/database.py` -- full endpoint and auth flow
- Codebase analysis: `tests/conftest.py`, `tests/integration/conftest.py`, `tests/llm/test_real_llm.py` -- existing test patterns
- `pyproject.toml` -- pytest configuration, markers, addopts
- [FastAPI Testing Events docs](https://fastapi.tiangolo.com/advanced/testing-events/) -- TestClient triggers lifespan with context manager
- [Firebase signInWithPassword REST API](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v1/accounts/signInWithPassword) -- returns idToken for real auth

### Secondary (MEDIUM confidence)
- [FastAPI Async Tests docs](https://fastapi.tiangolo.com/advanced/async-tests/) -- AsyncClient vs TestClient tradeoffs
- [Firebase Auth REST API overview](https://firebase.google.com/docs/reference/rest/auth) -- token format and lifecycle

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed, versions verified via `python -c`
- Architecture: HIGH - patterns derived directly from existing codebase + official FastAPI docs
- Pitfalls: HIGH - discovered real bugs (ChatResponseLLM missing, fake JWT incompatibility) via codebase analysis
- Firebase auth: MEDIUM - REST API approach verified via official docs, but exact test user setup depends on Firebase project config

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (stable domain, no fast-moving dependencies)
