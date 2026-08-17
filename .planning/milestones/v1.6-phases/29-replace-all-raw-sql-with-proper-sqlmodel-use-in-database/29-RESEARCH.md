# Phase 29: Replace all raw SQL with proper SQLModel use in database/* - Research

**Researched:** 2026-03-24
**Domain:** SQLModel/SQLAlchemy ORM patterns for PostgreSQL async operations
**Confidence:** HIGH

## Summary

Phase 29 is a focused rewrite of a single file: `src/nativespeaker/api/database/usage.py`. This file contains 3 methods (`try_increment`, `get_usage`, `reset_usage`) that all use raw `text()` SQL strings. Every other database file in the project already uses proper ORM patterns. The rewrite replaces raw SQL with the same ORM constructs already proven in the codebase: `pg_insert().on_conflict_do_nothing()` for upserts, `select()` for reads, and SQLAlchemy core `update().where().values()` for mutations.

All required APIs have been verified against the installed versions (SQLModel 0.0.37, SQLAlchemy 2.0.46). The `AsyncSession.exec()` method accepts `UpdateBase` statements and returns `CursorResult[Any]`, which supports `.first()` for RETURNING clauses. The `select(UsageMonthly.used)` pattern returns a `SelectOfScalar` type, which means `session.exec()` auto-applies `.scalars()` yielding direct scalar values from `.first()`.

**Primary recommendation:** Follow the exact ORM patterns already established in `users.py`, `subscriptions.py`, and `chats.py`. No new libraries, no new patterns -- just apply existing codebase conventions to the one remaining file.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Mixed approach -- SQLModel `select()` for reads, `pg_insert()` for upserts, SQLAlchemy core `update().where().returning()` for atomic operations
- **D-02:** This matches established patterns in `users.py` (pg_insert) and `chats.py` (SQLModel select)
- **D-03:** `get_usage` keeps its scalar `int` return type -- don't leak model instances into the service layer
- **D-04:** `try_increment` keeps its `bool` return type
- **D-05:** `reset_usage` keeps its `None` return type
- **D-06:** Keep the two-statement approach rewritten with ORM constructs: (1) `pg_insert(UsageMonthly).on_conflict_do_nothing()` to ensure the row exists, (2) `update(UsageMonthly).where(..., UsageMonthly.used < monthly_quota).values(used=UsageMonthly.used + 1).returning(UsageMonthly.used)` for atomic conditional increment
- **D-07:** Same atomicity guarantee as the current raw SQL implementation

### Claude's Discretion
- Whether `get_usage` uses `select(UsageMonthly.used)` + `scalar_one_or_none()` or `select(UsageMonthly)` + `.first()` + extract `.used` -- either is fine
- Import organization after removing `from sqlalchemy import text` and adding model/construct imports
- Whether to add inline comments explaining the atomic pattern

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

## Project Constraints (from CLAUDE.md)

- **Don't commit .planning dir** -- `commit_docs` is already `false` in config
- **Opening delimiter alignment style** for multiline constructs (func defs one per line, func calls collapse into 1+ lines)
- **Use Context7 MCP** for library/API documentation
- **Don't use string-based module references** in Python tests
- **Python 3.12+** (project actually targets 3.14 per pyproject.toml)

## Standard Stack

### Core (already installed, no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlmodel | 0.0.37 (latest) | ORM models and `select()` for reads | Already used in chats.py, users.py, subscriptions.py |
| sqlalchemy | 2.0.46 | Core `update()`, `pg_insert()`, `text()` (being removed) | Underlying engine for SQLModel |
| sqlalchemy.dialects.postgresql | 2.0.46 | `insert as pg_insert` for ON CONFLICT | Already used in users.py, subscriptions.py |

### No New Dependencies
This phase adds zero new packages. Every import needed already exists in other files in the same `database/` package.

## Architecture Patterns

### Target File Structure (no project structure changes)
```
src/nativespeaker/api/database/
    __init__.py          # exports unchanged
    chats.py             # already ORM -- reference for select()
    subscriptions.py     # already ORM -- reference for pg_insert()
    usage.py             # THE TARGET: rewrite from text() to ORM
    users.py             # already ORM -- reference for pg_insert()
```

### Pattern 1: Upsert with pg_insert + on_conflict_do_nothing
**What:** Insert a row if it doesn't exist, silently skip if it does (based on unique constraint).
**When to use:** `try_increment` step 1 -- ensure usage row exists before attempting UPDATE.
**Established in:** `users.py:get_or_create`, `subscriptions.py:insert_event_idempotent`
**Example:**
```python
# Source: verified against users.py lines 15-19 in this codebase
from sqlalchemy.dialects.postgresql import insert as pg_insert
from uuid import uuid7

stmt = (
    pg_insert(UsageMonthly)
    .values(id=uuid7(), user_id=user_id, month=month, used=0)
    .on_conflict_do_nothing(index_elements=["user_id", "month"])
)
await self.session.exec(stmt)
```

**Key detail:** `index_elements=["user_id", "month"]` maps to the `UniqueConstraint("user_id", "month")` on the `UsageMonthly` model. This is the same pattern as `on_conflict_do_nothing(index_elements=["jwt_sub"])` in `users.py`.

### Pattern 2: SQLAlchemy core update().where().values().returning()
**What:** Atomic conditional UPDATE that returns data -- used when ORM load-modify-flush is insufficient (need atomicity guarantee).
**When to use:** `try_increment` step 2 -- atomically increment `used` only if under quota.
**Example:**
```python
# Source: verified via SQLAlchemy 2.0 docs + runtime check on installed version
from sqlalchemy import update

result = await self.session.exec(
    update(UsageMonthly)
    .where(UsageMonthly.user_id == user_id,
           UsageMonthly.month == month,
           UsageMonthly.used < monthly_quota)
    .values(used=UsageMonthly.used + 1)
    .returning(UsageMonthly.used)
)
return result.first() is not None
```

**Key detail:** `session.exec()` returns `CursorResult[Any]` for `UpdateBase` statements. `.first()` returns the first row (a tuple) or `None`. The `result.first() is not None` check preserves the existing boolean return contract.

### Pattern 3: SQLModel select() for scalar reads
**What:** Type-safe column-level SELECT using SQLModel's `select()`.
**When to use:** `get_usage` -- read a single scalar value from one row.
**Recommendation:** Use `select(UsageMonthly.used)` which returns `SelectOfScalar`. SQLModel's `session.exec()` auto-applies `.scalars()` for `SelectOfScalar` types, so `.first()` returns the scalar value directly (not a row tuple).
**Example:**
```python
# Source: verified via runtime -- select(UsageMonthly.used) is SelectOfScalar type
from sqlmodel import select

result = await self.session.exec(
    select(UsageMonthly.used)
    .where(UsageMonthly.user_id == user_id, UsageMonthly.month == month)
)
used = result.first()
return used if used is not None else 0
```

**Alternative (also acceptable per Claude's Discretion):**
```python
result = await self.session.exec(
    select(UsageMonthly).where(UsageMonthly.user_id == user_id, UsageMonthly.month == month)
)
row = result.first()
return row.used if row is not None else 0
```

### Pattern 4: SQLAlchemy core update().where().values() (no RETURNING)
**What:** Simple UPDATE without needing a return value.
**When to use:** `reset_usage` -- zero out the counter.
**Example:**
```python
from sqlalchemy import update

await self.session.exec(
    update(UsageMonthly)
    .where(UsageMonthly.user_id == user_id, UsageMonthly.month == month)
    .values(used=0)
)
```

### Anti-Patterns to Avoid
- **Loading model instance to modify a single field:** Don't do `row = select(UsageMonthly)... ; row.used = 0 ; session.add(row)` for `reset_usage` -- this is a SELECT + UPDATE when a single UPDATE suffices. The core `update()` pattern is both simpler and more efficient.
- **Using `session.execute()` instead of `session.exec()`:** The codebase exclusively uses `session.exec()`. SQLModel's `exec()` provides better type inference and auto-scalar behavior. Do not introduce `session.execute()`.
- **Using `text()` for any reason:** The entire point of this phase is eliminating raw SQL. No `text()` should remain.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Conditional upsert | Manual IF-EXISTS logic | `pg_insert().on_conflict_do_nothing()` | Race-condition-free, single statement |
| Atomic increment with ceiling | Two separate SELECT + UPDATE | `update().where(col < limit).values(col=col+1).returning()` | Atomic in a single statement, no TOCTOU bug |
| Row existence check before insert | `SELECT ... ; if not found: INSERT` | `pg_insert().on_conflict_do_nothing()` | Single statement, no race condition |

**Key insight:** The current raw SQL already implements these patterns correctly. The task is translating the SQL to ORM constructs, not redesigning the logic.

## Common Pitfalls

### Pitfall 1: Wrong index_elements for ON CONFLICT
**What goes wrong:** Using column names that don't match any unique constraint causes PostgreSQL to raise an error.
**Why it happens:** Forgetting that the constraint is on `(user_id, month)` and using just one column.
**How to avoid:** Use `index_elements=["user_id", "month"]` matching the `UniqueConstraint("user_id", "month")` in the `UsageMonthly` model.
**Warning signs:** `ProgrammingError: there is no unique or exclusion constraint matching the ON CONFLICT specification`.

### Pitfall 2: Forgetting uuid7() for the id field
**What goes wrong:** `pg_insert(UsageMonthly).values(user_id=..., month=..., used=0)` without `id=uuid7()` relies on the model's `default_factory`. However, `pg_insert` bypasses SQLModel defaults -- it generates raw SQL, not model instances.
**Why it happens:** Assuming `default_factory=uuid7` on the model field will fire during `pg_insert`.
**How to avoid:** Always explicitly pass `id=uuid7()` in `pg_insert().values(...)`.
**Warning signs:** `NOT NULL constraint violation on 'id'` column.

### Pitfall 3: Using session.execute() instead of session.exec()
**What goes wrong:** Breaks codebase consistency. `session.execute()` returns raw `Result` objects requiring `.scalars()` calls.
**Why it happens:** Copying from SQLAlchemy docs instead of following codebase patterns.
**How to avoid:** Always use `self.session.exec()` -- the codebase standard. Verified that `exec()` accepts `UpdateBase` and returns `CursorResult[Any]`.
**Warning signs:** Code review shows `execute()` where `exec()` is used everywhere else.

### Pitfall 4: CursorResult.first() returns a Row, not a scalar
**What goes wrong:** For `update().returning(UsageMonthly.used)`, `result.first()` returns a `Row` (tuple-like), not a bare int. The check `result.first() is not None` still works correctly for the boolean return, but if you tried to use the value as an int, you'd get a Row.
**Why it happens:** `CursorResult` from `update()` is not a `ScalarResult` -- it doesn't auto-unwrap scalars.
**How to avoid:** For `try_increment`, only check `is not None` (which is what we want). For `get_usage`, use `select()` which does auto-scalar via `SelectOfScalar`.
**Warning signs:** Getting `(5,)` instead of `5` when trying to use a returned value.

### Pitfall 5: Opening delimiter alignment style
**What goes wrong:** CLAUDE.md mandates a specific multiline alignment style. Failing to follow it creates inconsistency.
**Why it happens:** Default formatter or habit.
**How to avoid:** For method definitions: one parameter per line, aligned to opening paren. For method calls: collapse into 1+ lines.
**Example:**
```python
# Correct per CLAUDE.md
async def try_increment(self,
                        user_id: UUID,
                        month: str,
                        monthly_quota: int) -> bool:
```

## Code Examples

### Complete rewritten usage.py (recommended implementation)

```python
# Source: derived from established patterns in users.py, chats.py, subscriptions.py
# and verified against SQLModel 0.0.37 / SQLAlchemy 2.0.46 APIs

from uuid import UUID, uuid7

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.models.users import UsageMonthly


class UsageDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def try_increment(self,
                            user_id: UUID,
                            month: str,
                            monthly_quota: int) -> bool:
        """Atomically increment usage if under quota. Returns True if allowed."""
        await self.session.exec(
            pg_insert(UsageMonthly)
            .values(id=uuid7(), user_id=user_id, month=month, used=0)
            .on_conflict_do_nothing(index_elements=["user_id", "month"])
        )

        result = await self.session.exec(
            update(UsageMonthly)
            .where(UsageMonthly.user_id == user_id,
                   UsageMonthly.month == month,
                   UsageMonthly.used < monthly_quota)
            .values(used=UsageMonthly.used + 1)
            .returning(UsageMonthly.used)
        )
        return result.first() is not None

    async def get_usage(self, user_id: UUID, month: str) -> int:
        """Get current usage count for a user in a given month."""
        result = await self.session.exec(
            select(UsageMonthly.used)
            .where(UsageMonthly.user_id == user_id, UsageMonthly.month == month)
        )
        used = result.first()
        return used if used is not None else 0

    async def reset_usage(self, user_id: UUID, month: str) -> None:
        """Zero out usage counter (called on plan change)."""
        await self.session.exec(
            update(UsageMonthly)
            .where(UsageMonthly.user_id == user_id, UsageMonthly.month == month)
            .values(used=0)
        )
```

### Import changes summary
```python
# REMOVED:
from sqlalchemy import text

# ADDED:
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from nativespeaker.api.models.users import UsageMonthly

# UNCHANGED:
from uuid import UUID, uuid7
from sqlmodel.ext.asyncio.session import AsyncSession
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `text()` raw SQL strings | SQLModel `select()` + SQLAlchemy `update()` + `pg_insert()` | This phase | Type safety, IDE support, consistency with rest of codebase |
| `session.execute()` | `session.exec()` | SQLModel 0.0.22+ | Auto-scalar behavior, better type inference |

**Deprecated/outdated:**
- `sqlalchemy.text()` for queries that can be expressed as ORM constructs -- still valid SQL but defeats the purpose of having an ORM layer.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio 1.3+ |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python3 -m pytest tests/unit/test_usage.py -x` |
| Full suite command | `python3 -m pytest tests/unit/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| (no formal IDs) | try_increment returns bool | unit (mock) | `python3 -m pytest tests/unit/test_usage.py -x` | Yes |
| (no formal IDs) | get_usage returns int | unit (mock) | `python3 -m pytest tests/unit/test_usage.py -x` | Yes |
| (no formal IDs) | reset_usage returns None | unit (mock) | `python3 -m pytest tests/unit/test_usage.py -x` | Yes |
| (no formal IDs) | Imports resolve correctly | smoke | `python3 -c "from nativespeaker.api.database.usage import UsageDB"` | N/A |

### Important Test Context
The existing unit tests (`tests/unit/test_usage.py`) mock `UsageDB` entirely via `AsyncMock`. They test the **service layer's behavior when UsageDB returns True/False**, not the actual SQL queries. This means:

1. **All 7 existing tests will continue to pass unchanged** -- they never instantiate a real `UsageDB` or execute real SQL.
2. **There are no tests that verify the actual ORM queries** -- this is by design (the unit tests verify service behavior, not DB layer internals).
3. **Verifying the rewrite** requires: (a) import smoke test, (b) code review confirming ORM constructs match the original SQL semantics, (c) optionally running against a real DB (E2E).

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/unit/test_usage.py -x`
- **Per wave merge:** `python3 -m pytest tests/unit/ -x`
- **Phase gate:** Full unit suite green + import smoke test

### Wave 0 Gaps
None -- existing test infrastructure covers the phase requirements. The rewrite is behavior-preserving and all service-level tests remain valid. No new test files are needed for the mocked unit tests to pass.

## Open Questions

1. **select(UsageMonthly.used) vs select(UsageMonthly) for get_usage**
   - What we know: Both work. `select(UsageMonthly.used)` returns `SelectOfScalar` which auto-scalars. `select(UsageMonthly)` returns the full model.
   - What's unclear: Nothing technically unclear -- this is a style preference.
   - Recommendation: Use `select(UsageMonthly.used)` -- it's more explicit about intent, returns less data over the wire, and matches D-03's directive to keep the `int` return type clean. The auto-scalar behavior makes the code cleaner (no `.used` attribute access needed).

## Sources

### Primary (HIGH confidence)
- SQLModel 0.0.37 `AsyncSession.exec()` source code -- verified signature accepts `UpdateBase`, returns `CursorResult[Any]`
- SQLAlchemy 2.0.46 installed locally -- verified `update().where().values().returning()` compiles correctly with `UsageMonthly` model
- Codebase files: `users.py`, `subscriptions.py`, `chats.py` -- established ORM patterns verified by reading source
- Runtime verification: `select(UsageMonthly.used)` returns `SelectOfScalar` type (confirmed via Python REPL)
- Runtime verification: `pg_insert(UsageMonthly).on_conflict_do_nothing(index_elements=["user_id", "month"])` compiles (confirmed via Python REPL)

### Secondary (MEDIUM confidence)
- [SQLAlchemy 2.0 DML documentation](https://docs.sqlalchemy.org/en/20/core/dml.html) -- `update().returning()` patterns
- [SQLAlchemy 2.0 AsyncIO documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) -- async session usage
- [SQLAlchemy PostgreSQL dialect](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html) -- `insert().on_conflict_do_nothing()`
- [SQLModel Read Data tutorial](https://sqlmodel.tiangolo.com/tutorial/select/) -- `select()` patterns

### Tertiary (LOW confidence)
None -- all findings verified against installed versions or official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used elsewhere in codebase
- Architecture: HIGH -- patterns copied from sibling files in same package, verified via runtime
- Pitfalls: HIGH -- verified each pitfall against actual API behavior via Python REPL

**Research date:** 2026-03-24
**Valid until:** 2026-06-24 (stable -- SQLModel/SQLAlchemy APIs are mature)
