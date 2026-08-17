# Phase 18: Test Infrastructure Cleanup - Research

**Researched:** 2026-03-19
**Domain:** SQLAlchemy async transaction-based test isolation with FastAPI
**Confidence:** HIGH

## Summary

This phase replaces manual `cleanup_chat()` try/finally blocks with per-test transaction rollback using SQLAlchemy 2.0's `join_transaction_mode="create_savepoint"` pattern. The core mechanism is: open a database connection, begin a transaction, bind all sessions to that connection with savepoint mode, run the test, then rollback the outer transaction -- undoing all database changes regardless of any intermediate commits.

The critical architectural decision is switching e2e tests from sync `TestClient` to async `httpx.AsyncClient`. This is required because `TestClient` runs its own internal event loop, making it impossible to share a database connection/transaction between test fixtures and the app's request handling. With `httpx.AsyncClient`, everything runs in a single event loop, enabling true transaction sharing.

**Primary recommendation:** Use `httpx.AsyncClient` with `ASGITransport` for e2e tests. Trigger app lifespan via `app.router.lifespan_context(app)`. Per-test: open connection, begin transaction, create `async_sessionmaker` bound to that connection with `join_transaction_mode="create_savepoint"`, swap `app.state.session_factory`, rollback after test.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
No explicitly locked decisions -- all areas deferred to Claude's discretion with recommended defaults.

### Claude's Discretion

All implementation areas deferred to Claude's judgment. Recommended defaults based on codebase analysis:

**Transaction scope:**
- Per-test rollback -- each test gets a clean database slate
- Use SAVEPOINT-based nested transactions so the app's own commit/rollback inside `get_db` works within the test's outer transaction
- Override `app.state.session_factory` in e2e fixtures to bind all sessions to the test transaction

**Seed data pattern:**
- Keep `create_chat()` as an async helper (it's clear and direct) -- just remove `cleanup_chat()` and all try/finally blocks
- Transaction rollback handles cleanup automatically

**Test boundary:**
- Transaction isolation applies to e2e tests only
- Unit tests stay on `AsyncMock(spec=ChatsDB)` -- no changes needed

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TEST-01 | Each test runs within a transaction that rolls back on completion | SQLAlchemy 2.0 `join_transaction_mode="create_savepoint"` pattern; per-test async fixture creates connection + transaction, rolls back in teardown |
| TEST-02 | Manual cleanup helpers (e.g. `cleanup_chat`) removed | Transaction rollback handles all cleanup; `cleanup_chat()` function and all try/finally blocks deleted |
| TEST-03 | No database artifacts remain after test suite execution | Outer transaction rollback undoes all INSERT/UPDATE/DELETE within each test; verified by running suite twice with identical results |
</phase_requirements>

## Standard Stack

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.46 | `join_transaction_mode="create_savepoint"` on AsyncSession | Official recipe for test isolation since SA 2.0 |
| SQLModel | 0.0.37 | `SQLModelAsyncSession` extends `AsyncSession`, passes `join_transaction_mode` via `**kw` | Already used for all DB sessions |
| httpx | 0.28.1 | `AsyncClient` + `ASGITransport` for async e2e test client | Already a dev dependency; replaces sync `TestClient` for e2e |
| pytest-asyncio | 1.3.0 | `loop_scope="module"` for module-scoped async fixtures | Already installed; supports async fixture scoping |
| pytest | 9.0.2 | Test framework | Already installed |
| asyncpg | 0.31.0 | PostgreSQL async driver with full SAVEPOINT support | Already installed; PostgreSQL SAVEPOINT works without workarounds (unlike SQLite) |

### Supporting (already installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| FastAPI | 0.135.1 | `app.router.lifespan_context(app)` to trigger lifespan manually | Module-scoped fixture to set up app state |
| Starlette | (transitive) | `ASGITransport` via httpx, lifespan protocol | Underlying ASGI handling |

### No New Dependencies Required

The entire implementation uses existing installed packages. No new dependencies needed.

- `asgi-lifespan` is NOT needed -- `app.router.lifespan_context(app)` provides the same capability
- No new test plugins required

**Verification performed:**
```
SQLAlchemy 2.0.46 -- confirmed join_transaction_mode="create_savepoint" works with SQLModelAsyncSession
httpx 0.28.1 -- confirmed ASGITransport available
pytest-asyncio 1.3.0 -- confirmed loop_scope parameter supported
asyncpg 0.31.0 -- PostgreSQL SAVEPOINT support is native, no workarounds needed
```

## Architecture Patterns

### How `get_db` Works Today

```python
# app/api/dependencies.py
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

The dependency reads `session_factory` from `app.state`. In production, this is an `async_sessionmaker` bound to an engine. For tests, we replace it with a factory bound to a connection inside a transaction.

### Pattern 1: Connection-Bound Session Factory with Savepoint Mode

**What:** Replace the engine-bound `async_sessionmaker` with one bound to a specific connection that has an open (uncommitted) transaction. Sessions use `join_transaction_mode="create_savepoint"` so their commits become savepoint releases (not real commits).

**When to use:** Every e2e test, via autouse fixture.

**Mechanism:**
```python
# Conceptual pattern (verified against SQLAlchemy 2.0 docs)
# Source: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites

# 1. Open a connection and begin a transaction (not committed)
connection = await engine.connect()
transaction = await connection.begin()

# 2. Create session factory bound to this connection
test_factory = async_sessionmaker(
    bind=connection,
    class_=SQLModelAsyncSession,
    expire_on_commit=False,
    join_transaction_mode="create_savepoint",
)

# 3. Swap app.state.session_factory
app.state.session_factory = test_factory

# 4. Run test (all session.commit() calls become SAVEPOINT releases)
# ...

# 5. Rollback outer transaction (undoes everything)
await transaction.rollback()
await connection.close()
```

**Why `join_transaction_mode="create_savepoint"` works:**
- The app's `get_db` calls `session.commit()` on success
- With `create_savepoint` mode, each session transaction is actually a SAVEPOINT
- `session.commit()` releases the savepoint (not a real commit)
- `session.rollback()` rolls back to the savepoint
- The outer transaction remains open and uncommitted
- Rolling back the outer transaction undoes ALL changes

**Verified:** `SQLModelAsyncSession` accepts `join_transaction_mode` via `**kw` parameter, which forwards to SQLAlchemy's sync `Session.__init__`. Tested locally:
```
>>> s = SQLModelAsyncSession(bind=engine, join_transaction_mode='create_savepoint')
>>> s.sync_session.join_transaction_mode
'create_savepoint'
```

### Pattern 2: Async Client with Manual Lifespan

**What:** Replace sync `TestClient(app)` with `httpx.AsyncClient(transport=ASGITransport(app=app))`. Trigger lifespan manually via `app.router.lifespan_context(app)`.

**Why required:** Sync `TestClient` creates its own event loop internally. This makes it impossible to share an `AsyncConnection` (which is event-loop-bound) between test fixtures and the app's request handlers. `httpx.AsyncClient` runs in the same event loop as the test, enabling shared connections.

**Verified:** `app.router.lifespan_context` is an `@asynccontextmanager` that can be called directly:
```python
async with app.router.lifespan_context(app):
    # app.state.session_factory, app.state.verifier, app.state.llm_service are set
    ...
```

### Pattern 3: Module-Scoped App + Function-Scoped Transaction

**What:** The app lifespan (expensive: config loading, engine creation, JWT verifier, LLM service) is module-scoped. The transaction (cheap: connect, begin) is function-scoped.

**Scope layout:**
```
Module scope:
  - app lifespan (config, verifier, llm_service)
  - engine (from lifespan)
  - httpx.AsyncClient
  - firebase_token

Function scope:
  - connection (from engine.connect())
  - transaction (from connection.begin())
  - test_session_factory (async_sessionmaker bound to connection)
  - app.state.session_factory swap (inject test_session_factory, restore original after test)
```

**Event loop scope:** Module-scoped async fixtures require `loop_scope="module"` on both fixtures and test marks. The current `asyncio_default_fixture_loop_scope = "function"` in pyproject.toml means we must explicitly set `loop_scope="module"` on module-scoped fixtures and all e2e test functions/classes.

### Pattern 4: `create_chat()` Uses the Same Transaction

**What:** `create_chat()` switches from using its own `test_db_factory` (separate engine/connection) to using the same connection-bound session factory that the app uses during the test.

**Before:**
```python
# Separate connection -- data persists even if app transaction rolls back
async def create_chat(factory, user_id):
    async with factory() as session:
        session.add(chat)
        await session.commit()
```

**After:**
```python
# Uses the test transaction -- data is rolled back automatically
async def create_chat(session_factory, user_id):
    async with session_factory() as session:
        session.add(chat)
        await session.commit()  # Actually a SAVEPOINT release
```

The `test_db_factory` fixture is removed entirely. Seed data helpers use `app.state.session_factory` (which is the test-scoped factory during tests).

### Recommended Fixture Structure

```
tests/e2e/conftest.py:
  _app_config         (session scope)  -- loads MainConfig once
  ensure_tables       (session scope)  -- CREATE TABLE IF NOT EXISTS once
  firebase_token      (session scope)  -- Firebase auth token once

  _app_lifespan       (module scope, loop_scope=module)  -- app lifespan context
  async_client        (module scope, loop_scope=module)  -- httpx.AsyncClient
  test_user_id        (module scope)   -- Firebase test user UID

  _db_transaction     (function scope, loop_scope=module, autouse for e2e)  -- connection + transaction + factory swap
```

### Anti-Patterns to Avoid

- **Sharing `AsyncConnection` across event loops:** Never create a connection in one event loop and use it in another. This is why sync `TestClient` cannot participate in the shared transaction.
- **Using `begin_nested()` without `join_transaction_mode`:** The older pattern of manually calling `begin_nested()` and listening for `after_transaction_end` events is obsolete in SQLAlchemy 2.0. Use `join_transaction_mode="create_savepoint"` instead.
- **Module-scoped transactions:** Do not share a single transaction across multiple tests. Each test must get its own connection + transaction for proper isolation.
- **Forgetting to restore `session_factory`:** The function-scoped fixture must restore the original `app.state.session_factory` after each test, or subsequent tests in the same module will fail.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Savepoint management | Manual `BEGIN`/`SAVEPOINT`/`ROLLBACK TO` SQL | `join_transaction_mode="create_savepoint"` | SA 2.0 handles all savepoint lifecycle automatically |
| Event listener for nested txn reset | `@event.listens_for(session, "after_transaction_end")` | `join_transaction_mode="create_savepoint"` | SA 2.0 removed the need for event listeners (1.x pattern) |
| Lifespan triggering | `asgi-lifespan` third-party package | `app.router.lifespan_context(app)` | Built into FastAPI/Starlette, no new dependency |
| Test data cleanup | `cleanup_chat()` try/finally | Transaction rollback | Catches ALL data changes, not just known objects |

**Key insight:** SQLAlchemy 2.0's `join_transaction_mode="create_savepoint"` eliminates all the complexity that existed in 1.x for test transaction isolation. The old pattern required event listeners and manual savepoint management; the new pattern is a single constructor parameter.

## Common Pitfalls

### Pitfall 1: Event Loop Mismatch
**What goes wrong:** `TestClient` (sync) creates its own event loop. Async fixtures create connections in pytest-asyncio's event loop. Sharing an `AsyncConnection` across loops causes `RuntimeError: Task attached to a different loop`.
**Why it happens:** `TestClient` uses `anyio.start_blocking_portal()` internally to run the async ASGI app.
**How to avoid:** Use `httpx.AsyncClient` with `ASGITransport` -- everything runs in one event loop.
**Warning signs:** `RuntimeError` about event loops, `ConnectionError` on session operations.

### Pitfall 2: Forgetting `loop_scope="module"` on Fixtures and Tests
**What goes wrong:** Module-scoped async fixtures fail with `ScopeMismatch` or `Event loop is closed` errors.
**Why it happens:** pytest-asyncio defaults to function-scoped event loops (`asyncio_default_fixture_loop_scope = "function"` in pyproject.toml). A module-scoped fixture needs a module-scoped loop.
**How to avoid:** Add `loop_scope="module"` to both `@pytest_asyncio.fixture(scope="module", loop_scope="module")` and `@pytest.mark.asyncio(loop_scope="module")` on all e2e test functions/classes.
**Warning signs:** Errors about event loop scope or fixtures being in wrong loop.

### Pitfall 3: `create_chat()` Using a Separate Connection
**What goes wrong:** Data inserted by `create_chat()` persists after test rollback because it used a different database connection.
**Why it happens:** The old `test_db_factory` creates its own engine with its own connection pool, separate from the test transaction.
**How to avoid:** `create_chat()` must use the same `session_factory` that `app.state.session_factory` points to during the test. Pass the test's session factory to `create_chat()` or have it read from the app.
**Warning signs:** Data from previous tests visible in current test; test suite fails on second run.

### Pitfall 4: Session Factory Not Restored After Test
**What goes wrong:** The first test in a module swaps `app.state.session_factory`, the fixture's teardown fails or doesn't run, and subsequent tests use a closed connection.
**How to avoid:** Use try/finally in the fixture teardown. Store the original factory and always restore it.
**Warning signs:** `ConnectionError`, `StatementError: (sqlalchemy.exc.ResourceClosedError)`.

### Pitfall 5: `expire_on_commit=False` Must Be Set
**What goes wrong:** After a commit (which is actually a savepoint release), SQLAlchemy expires all loaded attributes. Accessing them triggers a lazy load, which fails because the session state is inconsistent with savepoints.
**Why it happens:** Default `expire_on_commit=True` invalidates object state after commit.
**How to avoid:** Set `expire_on_commit=False` on the test session factory (already set in existing code).
**Warning signs:** `DetachedInstanceError`, `MissingGreenlet` errors after commits in tests.

### Pitfall 6: Sync Tests Must Become Async
**What goes wrong:** Tests like `test_chats.py` and `test_flows.py` currently use sync `def test_*` methods with sync `real_client`. After switching to `httpx.AsyncClient`, all tests must use `async def` and `await client.get(...)`.
**Why it happens:** `httpx.AsyncClient` requires async API calls.
**How to avoid:** Convert all e2e test methods to `async def`, use `await` for all client calls. Add `@pytest.mark.asyncio(loop_scope="module")` to all e2e test classes/functions.
**Warning signs:** `TypeError: 'coroutine' object is not subscriptable`.

## Code Examples

### Example 1: Module-Scoped App Lifespan Fixture

```python
# Source: verified locally against FastAPI 0.135.1
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from api.main import app


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan():
    """Start app lifespan (config, DB engine, verifier, LLM service)."""
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def async_client(_app_lifespan, firebase_token):
    """Async HTTP client wired to the real app with Firebase auth."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {firebase_token}"
        yield client
```

### Example 2: Function-Scoped Transaction Fixture (Autouse)

```python
# Source: SQLAlchemy 2.0 "Joining a Session into an External Transaction"
# https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _db_transaction(_app_lifespan):
    """Wrap each test in a transaction that rolls back on completion."""
    app = _app_lifespan
    original_factory = app.state.session_factory

    # Get the engine from the lifespan-created factory
    engine = original_factory.kw.get("bind", None) or original_factory.class_.kw.get("bind")
    # Note: async_sessionmaker stores bind in its kw dict

    async with engine.connect() as connection:
        transaction = await connection.begin()

        # Session factory bound to this connection with savepoint mode
        test_factory = async_sessionmaker(
            bind=connection,
            class_=SQLModelAsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        app.state.session_factory = test_factory
        try:
            yield test_factory
        finally:
            app.state.session_factory = original_factory
            await transaction.rollback()
```

**Note on engine access:** The engine reference may need to be extracted differently. The cleanest approach is to store the engine on `app.state` during lifespan, or extract it from the original factory's bind. The `async_sessionmaker` stores its bind as `factory.kw["bind"]` internally. Implementation should verify the exact attribute path.

### Example 3: Simplified `create_chat()` (No Cleanup Needed)

```python
# Before: create_chat + cleanup_chat + try/finally
# After: just create_chat, transaction rollback handles cleanup

async def create_chat(factory, user_id: str):
    """Insert a chat with human+AI message pair, return chat_id."""
    chat_id = uuid4()
    chat = Chat(id=chat_id, user_id=user_id, title="test phrase")
    human = Message(chat_id=chat_id, role=Role.human,
                    content=HumanContent(phrase="test phrase"))
    ai = Message(chat_id=chat_id, role=Role.ai,
                 content=AIContent(response="test answer", issues=[], suggestions=[]))
    chat.messages.append(human)
    chat.messages.append(ai)
    async with factory() as session:
        session.add(chat)
        await session.commit()  # SAVEPOINT release in test context
    return chat_id
```

### Example 4: Converted Test (Before/After)

**Before:**
```python
class TestCrossUserIsolation:
    @pytest.mark.asyncio
    async def test_cannot_read_other_user_chat(self, real_client, test_db_factory):
        chat_id = await create_chat(test_db_factory, OTHER_USER)
        try:
            response = real_client.get(f"/chats/{chat_id}")
            assert response.status_code == 404
        finally:
            await cleanup_chat(test_db_factory, chat_id)
```

**After:**
```python
@pytest.mark.asyncio(loop_scope="module")
class TestCrossUserIsolation:
    async def test_cannot_read_other_user_chat(self, async_client, _db_transaction):
        chat_id = await create_chat(_db_transaction, OTHER_USER)
        response = await async_client.get(f"/chats/{chat_id}")
        assert response.status_code == 404
        # No cleanup needed -- transaction rolls back automatically
```

### Example 5: Converted Sync Test (Before/After)

**Before:**
```python
class TestCreateChat:
    def test_create_chat_english(self, real_client):
        response = real_client.post("/chats", json={"phrase": "I am going to home.", "lang": "en"})
        assert response.status_code == 200
```

**After:**
```python
@pytest.mark.asyncio(loop_scope="module")
class TestCreateChat:
    async def test_create_chat_english(self, async_client):
        response = await async_client.post("/chats", json={"phrase": "I am going to home.", "lang": "en"})
        assert response.status_code == 200
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Event listeners for savepoint reset (SA 1.x) | `join_transaction_mode="create_savepoint"` (SA 2.0) | SQLAlchemy 2.0 (Jan 2023) | No event handlers needed |
| Manual `cleanup_*()` helpers | Transaction rollback | Standard practice | Catches ALL changes, not just known objects |
| Sync `TestClient` for all tests | `httpx.AsyncClient` for async-heavy tests | FastAPI docs recommend since ~2023 | Required for shared async resources |
| `@pytest.fixture(scope="session") event_loop` | `loop_scope` parameter on fixtures and marks | pytest-asyncio 0.23+ | Per-scope event loop configuration |

## Open Questions

1. **Engine access from `async_sessionmaker`**
   - What we know: `async_sessionmaker` stores `bind` in its internal state
   - What's unclear: Exact attribute path (`factory.kw["bind"]` vs other)
   - Recommendation: During implementation, inspect `app.state.session_factory` to find the engine reference, or store engine separately on `app.state` during lifespan

2. **`ensure_tables` fixture interaction**
   - What we know: Currently session-scoped, creates tables via separate engine
   - What's unclear: Whether it should run before or within the module-scoped lifespan
   - Recommendation: Keep `ensure_tables` as session-scoped sync fixture (runs once), then module-scoped lifespan starts app; the app's engine connects to already-created tables

3. **LLM-calling tests and transaction rollback**
   - What we know: `test_chats.py` and `test_flows.py` call the real LLM via the API, which creates real DB records
   - What's unclear: Whether LLM responses will be consistent enough for rollback to matter (tests check response structure, not content)
   - Recommendation: Transaction rollback still cleans up the DB records created by these tests, which is the goal

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `pytest tests/unit/ -x` |
| Full suite command | `pytest -m e2e --override-ini="addopts=" -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | Each test runs within a rollback transaction | smoke | Run full e2e suite, check no DB artifacts remain | Existing e2e tests serve as validation |
| TEST-02 | No `cleanup_chat` or manual cleanup helpers | static | `grep -r "cleanup_chat\|cleanup_" tests/` should return nothing | N/A (grep check) |
| TEST-03 | No DB artifacts after suite execution | integration | Run suite twice: `pytest -m e2e && pytest -m e2e` -- second run identical | Existing e2e tests |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/ -x` (ensure no unit test regressions)
- **Per wave merge:** `pytest -m e2e --override-ini="addopts=" -x` (full e2e suite)
- **Phase gate:** Full suite green, run twice to verify no artifacts

### Wave 0 Gaps
None -- existing test infrastructure (pytest, pytest-asyncio, httpx) covers all requirements. No new test files or framework setup needed. The work is refactoring existing fixtures and tests, not creating new test infrastructure.

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 - Joining a Session into an External Transaction](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites) - Official recipe for `join_transaction_mode="create_savepoint"`
- [SQLAlchemy 2.0 - Session API](https://docs.sqlalchemy.org/en/20/orm/session_api.html) - `join_transaction_mode` parameter documentation
- [FastAPI - Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/) - Official guidance on `httpx.AsyncClient` + `ASGITransport`
- [pytest-asyncio 1.3.0 - Concepts](https://pytest-asyncio.readthedocs.io/en/stable/concepts.html) - Event loop scoping, `loop_scope` parameter
- [pytest-asyncio - Change Fixture Loop Scope](https://pytest-asyncio.readthedocs.io/en/stable/how-to-guides/change_fixture_loop.html) - Module-scoped async fixtures
- Local verification: `SQLModelAsyncSession` accepts `join_transaction_mode`, `async_sessionmaker` passes it through, `app.router.lifespan_context` is an async context manager

### Secondary (MEDIUM confidence)
- [SQLAlchemy Discussion #11658](https://github.com/sqlalchemy/sqlalchemy/discussions/11658) - Community pattern for async FastAPI + SA 2.0 test isolation
- [CORE27 - Transactional Unit Tests with Async SQLAlchemy](https://www.core27.co/post/transactional-unit-tests-with-pytest-and-async-sqlalchemy) - Async transaction isolation walkthrough

### Tertiary (LOW confidence)
- None -- all findings verified against official docs or local code inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages already installed, versions verified locally, `join_transaction_mode` tested
- Architecture: HIGH -- pattern is official SQLAlchemy 2.0 recipe, adapted for async; event loop constraint verified by understanding TestClient internals
- Pitfalls: HIGH -- each pitfall identified from either official docs, community discussions, or analysis of the specific codebase constraints

**Research date:** 2026-03-19
**Valid until:** 2026-06-19 (stable libraries, established patterns)
