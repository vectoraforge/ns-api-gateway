# Phase 14: DB Query Optimization - Research

**Researched:** 2026-03-04
**Domain:** SQLAlchemy async query optimization, dead code removal
**Confidence:** HIGH

## Summary

Phase 14 refactors all DB access in `app/chats.py` and `app/services.py` so that every request handler makes at most one DB read call. The current pattern performs separate ownership checks (SELECT) before data queries, resulting in 2-3 round trips per request. The new pattern folds `user_id` filtering directly into data queries using JOINs and WHERE clauses, then removes all orphaned code (`get_chat_owned`, `get_message_counts`, `_ensure_history_capacity`, `ChatOwnershipError`).

The codebase uses SQLAlchemy 2.0.46 async with SQLModel 0.0.37 on top. All data access is through the `Chats` class using static-style methods on `AsyncSession`. The `get_db` dependency in `app/dependencies.py` already handles commit/rollback, so Chats methods that currently call `db.commit()` explicitly can drop those calls (the dependency's context manager commits on success). The messages table is partitioned by `created_at` with `ON DELETE CASCADE` from `chat_id`, so chat deletion automatically cascades.

**Primary recommendation:** Implement changes in two logical waves: (1) modify Chats methods + ChatService + router callers to use single-query patterns, (2) remove all dead code and update tests to match.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Zero-row handling: 0 rows from JOIN with user_id filter -> 404 (InvalidChatError); no fallback existence check
- Invariant: every chat has >= 1 message, enforced by `create_chat_with_messages` atomic operation
- Defer chat creation until after LLM call succeeds
- `get_db` dependency handles commits -- no explicit `db.commit()` in Chats methods
- Single session per request (no split read/write sessions)
- `load_history` gains `user_id` parameter; JOIN with user_id filter; raises InvalidChatError on 0 rows
- For new chats: skip `load_history` entirely -- empty history `[]` assigned directly
- `list_messages` gains `user_id` parameter; JOIN with user_id filter; raises InvalidChatError on 0 rows AND no cursor
- `delete_chat_owned` -> `delete_chat`; single DELETE WHERE id AND user_id with rowcount 0 -> InvalidChatError
- Capacity derived from `len(history)` in Python; config simplified to single `history_max_messages` (default 50)
- Capacity check: `len(history) >= history_max_messages * 2`; inline in `chat()` method
- `ChatHistoryLimitError` constructor: `ChatHistoryLimitError(max_messages=N)`
- Method naming: `list_messages`/`load_history` keep names, `delete_chat_owned` -> `delete_chat`, `create_chat` -> `create_chat_with_messages`
- Router keeps direct access to `service.chats` methods (no service wrappers)
- `ChatOwnershipError` handler removal: `InvalidChatError` handler covers all cases
- Tests rewritten to match new query patterns (not minimal adaptation)
- YAML config: `history_max_messages: 50` replaces both old keys

### Claude's Discretion
- Exact SQL query construction for JOINs (SQLAlchemy expression style)
- `create_chat_with_messages` internal implementation (reuses `save_messages`)
- Test structure and assertion patterns
- Removal order across files

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| QOPT-01 | `list_messages` uses LEFT JOIN from Chat to Message with user_id filter -- 1 query, 404 for non-existent/wrong-user chats | JOIN pattern in Architecture Patterns; zero-row detection logic documented |
| QOPT-02 | `delete_chat` uses single DELETE WHERE id AND user_id with rowcount check -- 1 query | SQLAlchemy `delete()` + `result.rowcount` pattern documented |
| QOPT-03 | `load_history` (continuation) uses JOIN with user_id filter -- 1 query replaces separate ownership check + history load | JOIN pattern same as QOPT-01; user_id parameter addition |
| QOPT-04 | Capacity check derived from loaded history in Python -- eliminates `get_message_counts` DB call | `len(history) >= history_max_messages * 2` inline check; config simplification |
| QOPT-05 | New chat path skips `load_history` -- empty history assigned directly | Service layer flow change; `create_chat_with_messages` defers creation to after LLM success |
| DEAD-01 | Remove `get_chat_owned` method from Chats class | Grep inventory shows 5 call sites across app + tests |
| DEAD-02 | Remove `get_message_counts` method from Chats class | Grep inventory shows 3 references across app + tests |
| DEAD-03 | Remove `_ensure_history_capacity` method from ChatService | Grep inventory shows 2 references in services.py |
| DEAD-04 | Remove `ChatOwnershipError` exception class + handler + imports (4-file atomic cleanup) | Full dependency chain mapped: exceptions.py, errors.py, chats.py, test_exception_handlers.py |
| DEAD-05 | Clean up phantom test mocks for removed methods | Inventory of mock setups documented in Pitfalls section |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.46 | Async ORM + Core SQL | Already in use; 2.0 style `select()`/`delete()` |
| SQLModel | 0.0.37 | Model definitions, `select()` helper | Already in use for models |
| FastAPI | 0.129.0 | Web framework | Already in use |
| asyncpg | 0.30+ | PostgreSQL async driver | Already in use |

### Supporting (no new libraries needed)
This phase requires zero new dependencies. All changes use existing SQLAlchemy Core constructs (`delete`, `select`, `and_`, `func`, `insert`) that are already imported in `app/chats.py`.

## Architecture Patterns

### Current Data Flow (BEFORE -- what we're changing)

```
POST /chats (continuation):
  router -> service.chat()
    -> chats.get_chat_owned(db, chat_id, user_id)     # SELECT 1
    -> service._ensure_history_capacity(db, chat_id)
      -> chats.get_message_counts(db, chat_id)         # SELECT 2
    -> chats.load_history(db, chat_id, limit)           # SELECT 3
    -> LLM invoke
    -> chats.save_messages(db, chat_id, ...)            # INSERT

GET /chats/{id}/messages:
  router
    -> service.chats.get_chat_owned(db, chat_id, user_id)  # SELECT 1
    -> service.chats.list_messages(db, chat_id, ...)        # SELECT 2

DELETE /chats/{id}:
  router
    -> service.chats.delete_chat_owned(db, chat_id, user_id)  # SELECT + DELETE (2 ops)
```

### Target Data Flow (AFTER)

```
POST /chats (continuation):
  router -> service.chat()
    -> chats.load_history(db, chat_id, user_id, limit)  # SELECT 1 (JOIN w/ user_id)
    -> capacity check: len(history) >= max * 2           # Python, no DB
    -> LLM invoke
    -> chats.save_messages(db, chat_id, ...)             # INSERT

POST /chats (new chat):
  router -> service.chat()
    -> history = []                                       # No DB call
    -> LLM invoke
    -> chats.create_chat_with_messages(db, chat_id, user_id, human, assistant)  # INSERT

GET /chats/{id}/messages:
  router
    -> service.chats.list_messages(db, chat_id, user_id, ...)  # SELECT 1 (JOIN w/ user_id)

DELETE /chats/{id}:
  router
    -> service.chats.delete_chat(db, chat_id, user_id)  # DELETE 1 (WHERE w/ user_id)
```

### Pattern 1: DELETE with rowcount check (SQLAlchemy 2.0)

**What:** Single DELETE statement with WHERE clause, using `result.rowcount` to detect missing/unowned rows.
**When to use:** `delete_chat` -- replacing SELECT-then-DELETE pattern.

```python
from sqlalchemy import delete

async def delete_chat(self, db: AsyncSession, chat_id: UUID, user_id: str) -> None:
    result = await db.execute(
        delete(Chat).where(and_(Chat.id == chat_id, Chat.user_id == user_id))
    )
    if result.rowcount == 0:
        raise InvalidChatError(chat_id)
```

**Confidence:** HIGH -- `result.rowcount` is a standard SQLAlchemy 2.0 attribute on `CursorResult` returned by `execute()` for DML statements. PostgreSQL always returns accurate rowcount for DELETE.

### Pattern 2: JOIN query for ownership-filtered data reads

**What:** SELECT from messages with JOIN to chats table to enforce user_id filter in the same query.
**When to use:** `load_history` and `list_messages` -- replacing separate ownership check.

```python
# For load_history: JOIN Chat to Message, filter by user_id
statement = (
    select(Message.role, Message.content)
    .join(Chat, Message.chat_id == Chat.id)
    .where(and_(Message.chat_id == chat_id, Chat.user_id == user_id))
    .order_by(Message.created_at.desc())
)
if limit is not None:
    statement = statement.limit(limit)
results = (await db.exec(statement)).all()
```

**Note:** Using `sqlmodel.select` (which wraps `sqlalchemy.select`) with `.join()` is the established pattern. The `Message.chat_id == chat_id` filter is redundant with the JOIN condition but helps the query planner use the `idx_messages_chat_created` index directly.

### Pattern 3: Zero-row detection with cursor awareness

**What:** For `list_messages`, 0 rows on first page (no cursor) = 404; 0 rows with cursor = end of pagination.
**When to use:** `list_messages` only.

```python
# After query execution:
if not results and cursor is None:
    raise InvalidChatError(chat_id)
```

### Pattern 4: Atomic chat + messages creation

**What:** `create_chat_with_messages` inserts chat row + message pair in one method call, reusing `save_messages` internally.
**When to use:** New chat path only (after LLM success).

```python
async def create_chat_with_messages(
    self, db: AsyncSession, chat_id: UUID, user_id: str, human: str, assistant: str
) -> None:
    db.add(Chat(id=chat_id, user_id=user_id))
    await db.execute(
        insert(Message),
        [
            {"chat_id": chat_id, "role": "human", "content": human},
            {"chat_id": chat_id, "role": "assistant", "content": assistant},
        ],
    )
```

**Note:** No explicit commit -- `get_db` dependency handles it. Reuses the `insert(Message)` pattern from `save_messages`. The method does not call `save_messages` directly because that method also has no commit (after this refactor), so either approach works. Keeping the insert inline avoids a method call.

### Pattern 5: Deferred chat creation in service

**What:** For new chats, the LLM call happens BEFORE any DB write. Chat + messages are created atomically after LLM succeeds.
**When to use:** `service.chat()` new chat path.

```python
# New chat path (simplified):
chat_id = uuid4()
history = []  # QOPT-05: skip load_history
response = await self._invoke(chain, params)
await self.chats.create_chat_with_messages(db, chat_id, user_id, human_text, assistant_payload)
```

### Anti-Patterns to Avoid
- **SELECT-then-act:** Never do a SELECT to check existence/ownership, then a separate DML. Fold the check into the query.
- **Explicit `db.commit()` in Chats methods:** The `get_db` dependency already commits on success. Adding explicit commits creates double-commit or inconsistent behavior.
- **Separate ownership exception type:** `ChatOwnershipError` and `InvalidChatError` both map to 404. With query-level filtering, there is no way to distinguish "doesn't exist" from "wrong owner" -- and that's the correct security behavior (OWASP).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rowcount-based deletion | Manual SELECT + conditional DELETE | `delete().where(...)` + `result.rowcount` | Atomic, race-condition-free |
| Ownership verification | Separate ownership query method | JOIN/WHERE in data query itself | Eliminates round trip, same security |
| Message counting | `get_message_counts` DB query | `len(history)` from already-loaded data | Data is already in memory |

## Common Pitfalls

### Pitfall 1: Forgetting to remove explicit `db.commit()` calls
**What goes wrong:** After removing the commit from Chats methods, `save_messages` and `create_chat` still have `await db.commit()`. These cause the session to commit mid-request.
**Why it happens:** The original Chats methods were written before `get_db` handled commits.
**How to avoid:** Remove ALL `await db.commit()` calls from Chats methods. The `get_db` dependency's context manager (`yield session; await session.commit()`) handles this.
**Warning signs:** Tests pass but integration tests show unexpected commit behavior.
**Files affected:** `app/chats.py` lines 28-29 (`create_chat`), 48-49 (`delete_chat_owned`), 107-108 (`save_messages`).

### Pitfall 2: Phantom mock setups in tests
**What goes wrong:** Tests mock `get_chat_owned`, `get_message_counts`, or `_ensure_history_capacity` which no longer exist, leading to either: (a) tests pass vacuously because mocks absorb calls that never happen, or (b) tests break because they reference removed methods.
**Why it happens:** Mock objects accept any attribute by default (`AsyncMock()` auto-creates attributes).
**How to avoid:** Rewrite test fixtures from scratch for the new API surface. The `mock_chats` fixture in both `tests/conftest.py` and `tests/integration/conftest.py` must be updated.
**Specific phantom mocks to remove:**
- `tests/conftest.py:30` -- `chats.get_chat_owned = AsyncMock(return_value=None)`
- `tests/conftest.py:32` -- `chats.get_message_counts = AsyncMock(...)`
- `tests/integration/conftest.py:46` -- `chats.get_message_counts = AsyncMock(...)` (unit conftest)
- `tests/unit/test_services.py` lines 89, 104, 147, 164, 172 -- `mock_chats.get_chat_owned` usage

### Pitfall 3: ChatHistoryLimitError constructor mismatch
**What goes wrong:** `ChatHistoryLimitError` currently takes `max_human` and `max_assistant` parameters. After config simplification to single `history_max_messages`, the constructor must change to `max_messages`.
**Why it happens:** Constructor signature is coupled to config shape.
**How to avoid:** Update constructor, all raise sites, and the test case in `test_exception_handlers.py` line 38.
**Files affected:** `app/exceptions.py:65-69`, `app/services.py` (raise site), `tests/unit/test_exception_handlers.py:38`.

### Pitfall 4: `list_messages` zero-row false positive on paginated requests
**What goes wrong:** Raising 404 when cursor-based pagination returns 0 rows (legitimate end of data).
**Why it happens:** Zero-row detection must be conditional on whether it's a first-page request.
**How to avoid:** Only raise `InvalidChatError` when `cursor is None` AND results are empty. With a cursor, 0 rows means end of pagination.

### Pitfall 5: Config/constructor cascading updates
**What goes wrong:** Changing `AppConfig` to use `history_max_messages` but forgetting to update `ChatService.__init__`, `main.py` lifespan, `config.yaml`, and all test fixtures.
**Why it happens:** The config value flows through 5+ files.
**How to avoid:** Trace the full chain: `config.yaml` -> `AppConfig` -> `main.py` lifespan -> `ChatService.__init__` -> `service.chat()` usage -> test fixtures (`tests/conftest.py`, `tests/integration/conftest.py`).
**Full chain:**
1. `config/config.yaml`: Replace `history_max_human_messages` + `history_max_assistant_messages` with `history_max_messages: 50`
2. `app/config.py:77-78`: Replace two fields with `history_max_messages: int = Field(default=50, ge=1)`
3. `app/main.py:61-62`: Replace two kwargs with `history_max_messages=config.history_max_messages`
4. `app/services.py:20-21`: Replace two init params with `history_max_messages: int`
5. `tests/conftest.py` fixture: Replace two kwargs with one
6. `tests/integration/conftest.py` fixture: Replace two kwargs with one

### Pitfall 6: Router `list_chat_messages` still calls `get_chat_owned`
**What goes wrong:** The router at `app/routers/chats.py:55` explicitly calls `service.chats.get_chat_owned()` before `list_messages()`. This must be removed and `list_messages` must gain the `user_id` parameter.
**How to avoid:** Update the router to pass `user_id` directly to `list_messages()` and remove the `get_chat_owned` call.

### Pitfall 7: `save_messages` still has explicit commit
**What goes wrong:** `save_messages` at `app/chats.py:108` calls `await db.commit()`. After this phase, the `get_db` dependency handles commits, so this explicit commit is premature and can cause issues with the atomic `create_chat_with_messages` pattern.
**How to avoid:** Remove `await db.commit()` from `save_messages`. This is safe because `get_db` commits after the request handler returns.

## Code Examples

### Example 1: Refactored `delete_chat` method

```python
# app/chats.py
from sqlalchemy import and_, delete

async def delete_chat(self, db: AsyncSession, chat_id: UUID, user_id: str) -> None:
    """Delete chat owned by user_id. Raises InvalidChatError if not found or wrong owner."""
    result = await db.execute(
        delete(Chat).where(and_(Chat.id == chat_id, Chat.user_id == user_id))
    )
    if result.rowcount == 0:
        raise InvalidChatError(chat_id)
```

### Example 2: Refactored `load_history` with user_id

```python
# app/chats.py
async def load_history(
    self, db: AsyncSession, chat_id: UUID, user_id: str, limit: int | None = None
) -> list[HumanMessage | AIMessage]:
    statement = (
        select(Message.role, Message.content)
        .join(Chat, Message.chat_id == Chat.id)
        .where(and_(Message.chat_id == chat_id, Chat.user_id == user_id))
        .order_by(Message.created_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    results = (await db.exec(statement)).all()
    if not results:
        raise InvalidChatError(chat_id)
    messages = []
    for role, content in reversed(results):
        if role == "human":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages
```

### Example 3: Refactored `list_messages` with user_id

```python
# app/chats.py
async def list_messages(
    self,
    db: AsyncSession,
    chat_id: UUID,
    user_id: str,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Message], str | None]:
    statement = (
        select(Message)
        .join(Chat, Message.chat_id == Chat.id)
        .where(and_(Message.chat_id == chat_id, Chat.user_id == user_id))
    )
    if cursor:
        cursor_created_at, cursor_id = self._decode_cursor(cursor)
        statement = statement.where(
            or_(
                Message.created_at < cursor_created_at,
                and_(Message.created_at == cursor_created_at, Message.id < cursor_id),
            )
        )
    statement = statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)
    results = (await db.exec(statement)).all()

    if not results and cursor is None:
        raise InvalidChatError(chat_id)

    next_cursor = None
    if len(results) > limit:
        last = results.pop()
        if last.created_at is not None and last.id is not None:
            next_cursor = self._encode_cursor(last.created_at, last.id)
    return results, next_cursor
```

### Example 4: `create_chat_with_messages`

```python
# app/chats.py
async def create_chat_with_messages(
    self, db: AsyncSession, chat_id: UUID, user_id: str, human: str, assistant: str
) -> None:
    db.add(Chat(id=chat_id, user_id=user_id))
    await db.execute(
        insert(Message),
        [
            {"chat_id": chat_id, "role": "human", "content": human},
            {"chat_id": chat_id, "role": "assistant", "content": assistant},
        ],
    )
```

### Example 5: Refactored `service.chat()` flow

```python
# app/services.py - chat method (continuation path)
if chat_id:
    history = await self.chats.load_history(db, chat_id, user_id, limit=self.history_max_messages * 2)
    if len(history) >= self.history_max_messages * 2:
        raise ChatHistoryLimitError(max_messages=self.history_max_messages)
else:
    if lang not in self.examples:
        raise UnsupportedLanguageError(lang=lang, supported=self.supported_languages)
    chat_id = uuid4()
    history = []

# ... LLM invoke ...

if not history:
    # New chat: atomic create
    await self.chats.create_chat_with_messages(db, chat_id, user_id, human_text, assistant_payload)
else:
    # Continuation: just save messages
    await self.chats.save_messages(db, chat_id, human_text, assistant_payload)
```

## Dependency Chain: What Gets Removed

Complete inventory of code to remove, by file:

### `app/exceptions.py`
- Lines 85-90: `ChatOwnershipError` class definition

### `app/errors.py`
- Line 12: `ChatOwnershipError` import
- Lines 117-118: `chat_ownership_error_handler` function
- Line 156: `app.add_exception_handler(ChatOwnershipError, ...)`

### `app/chats.py`
- Line 10: `ChatOwnershipError` import (keep `InvalidChatError`)
- Lines 26-28: `create_chat` method (replaced by `create_chat_with_messages`)
- Lines 30-38: `get_chat_owned` method (entire method removed)
- Lines 40-49: `delete_chat_owned` method (replaced by `delete_chat`)
- Lines 68-73: `get_message_counts` method (entire method removed)

### `app/services.py`
- Lines 20-21: `history_max_human_messages` and `history_max_assistant_messages` init params
- Lines 47-55: `_ensure_history_capacity` method (entire method removed)

### `app/routers/chats.py`
- Line 55: `await service.chats.get_chat_owned(db, chat_id, user_id)` call

### `app/config.py`
- Lines 77-78: `history_max_human_messages` and `history_max_assistant_messages` fields

### `tests/unit/test_exception_handlers.py`
- Line 12: `ChatOwnershipError` import
- Line 30: `ChatOwnershipError("abc")` test case

### `tests/conftest.py`
- Line 30: `chats.get_chat_owned = AsyncMock(...)` phantom mock
- Line 32: `chats.get_message_counts = AsyncMock(...)` phantom mock

### `tests/integration/conftest.py`
- Line 46: `chats.get_message_counts = AsyncMock(...)` phantom mock
- Lines 89-94: `create_chat` helper (may need update for `create_chat_with_messages`)

### `tests/unit/test_services.py`
- Multiple lines referencing `mock_chats.get_chat_owned` (lines 89, 104, 147, 164, 172)

### `config/config.yaml`
- Lines 3-4: `history_max_human_messages` and `history_max_assistant_messages` keys

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate SELECT for ownership | WHERE/JOIN with user_id in data query | SQLAlchemy 2.0+ best practice | Eliminates N+1 pattern |
| `db.execute(delete(M)).where(...)` | Same, using `result.rowcount` | SQLAlchemy 2.0 | Atomic check-and-delete |
| Explicit `session.commit()` in methods | Dependency-managed commit via `get_db` | FastAPI pattern | Consistent transaction boundaries |

## Open Questions

1. **Integration test `create_chat` helper**
   - What we know: `tests/integration/conftest.py:89-94` has a `create_chat` helper that inserts a bare chat row (no messages). After this phase, chats always have messages (invariant). Integration tests for cross-user isolation create chats without messages.
   - What's unclear: Should integration test helpers create chat + messages to honor the invariant, or is it acceptable to keep bare-chat helpers for negative test cases?
   - Recommendation: Update integration helpers to use `create_chat_with_messages` pattern (insert chat + at least one message pair) to match production invariants. This ensures `list_messages` JOIN returns rows for positive cases and tests the actual zero-row path for cross-user access.

2. **`save_messages` commit removal impact on existing tests**
   - What we know: Removing explicit `db.commit()` from `save_messages` is correct for production (handled by `get_db`). Unit tests use `MagicMock` for db which won't complain. Integration tests use real sessions with rollback.
   - What's unclear: Integration test `db_session` fixture does `await session.rollback()` in cleanup -- does removing explicit commit from `save_messages` change when data becomes visible?
   - Recommendation: Should be fine -- integration tests override `get_db` and the session fixture handles cleanup. No commit is needed mid-method because the entire request is one transaction.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ with pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -x -q -m 'not llm and not db'` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QOPT-01 | `list_messages` JOIN with user_id, 404 on no rows | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite |
| QOPT-02 | `delete_chat` single DELETE with rowcount | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite |
| QOPT-03 | `load_history` JOIN with user_id | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite |
| QOPT-04 | Capacity from len(history) | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite |
| QOPT-05 | New chat skips load_history | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite |
| DEAD-01 | `get_chat_owned` removed | grep | `grep -r 'get_chat_owned' app/ tests/` | Verification step |
| DEAD-02 | `get_message_counts` removed | grep | `grep -r 'get_message_counts' app/ tests/` | Verification step |
| DEAD-03 | `_ensure_history_capacity` removed | grep | `grep -r '_ensure_history_capacity' app/ tests/` | Verification step |
| DEAD-04 | `ChatOwnershipError` removed | grep | `grep -r 'ChatOwnershipError' app/ tests/` | Verification step |
| DEAD-05 | No phantom mocks | unit | `python -m pytest tests/ -x -q -m 'not llm and not db'` | Needs rewrite |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q -m 'not llm and not db'` + `ruff check`
- **Phase gate:** Full suite green + grep verification for all DEAD-* requirements

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. Tests need rewriting (not new infrastructure).

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection of all files in `app/` and `tests/`
- `migrations/001_create_tables.sql` -- confirmed ON DELETE CASCADE, partitioned messages table, index structure
- SQLAlchemy 2.0 `CursorResult.rowcount` -- standard attribute, confirmed available in 2.0.46
- `pyproject.toml` -- confirmed library versions and test configuration

### Secondary (MEDIUM confidence)
- SQLAlchemy 2.0 async patterns for `delete().where()` + `result.rowcount` -- consistent with established 2.0 API

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all changes use existing imports
- Architecture: HIGH -- patterns verified against codebase structure and SQLAlchemy 2.0 API
- Pitfalls: HIGH -- every pitfall identified from direct code inspection with line numbers
- Dead code inventory: HIGH -- exhaustive grep of all references

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable -- internal refactoring, no external dependencies changing)
