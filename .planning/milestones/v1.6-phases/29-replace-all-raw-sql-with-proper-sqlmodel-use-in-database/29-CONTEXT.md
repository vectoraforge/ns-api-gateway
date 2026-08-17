# Phase 29: Replace all raw SQL with proper SQLModel use in database/* - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Convert all raw `text()` SQL in `database/usage.py` to proper SQLModel/SQLAlchemy ORM patterns. Only `usage.py` has raw SQL — the other 3 DB files (`chats.py`, `users.py`, `subscriptions.py`) already use proper ORM patterns. No new features, no schema changes, no migration work.

</domain>

<decisions>
## Implementation Decisions

### ORM Purity Level
- **D-01:** Mixed approach — SQLModel `select()` for reads, `pg_insert()` for upserts, SQLAlchemy core `update().where().returning()` for atomic operations
- **D-02:** This matches established patterns in `users.py` (pg_insert) and `chats.py` (SQLModel select)

### Method Return Types
- **D-03:** `get_usage` keeps its scalar `int` return type — don't leak model instances into the service layer
- **D-04:** `try_increment` keeps its `bool` return type
- **D-05:** `reset_usage` keeps its `None` return type

### try_increment Pattern
- **D-06:** Keep the two-statement approach rewritten with ORM constructs:
  1. `pg_insert(UsageMonthly).on_conflict_do_nothing()` to ensure the row exists
  2. `update(UsageMonthly).where(..., UsageMonthly.used < monthly_quota).values(used=UsageMonthly.used + 1).returning(UsageMonthly.used)` for atomic conditional increment
- **D-07:** Same atomicity guarantee as the current raw SQL implementation

### Claude's Discretion
- Whether `get_usage` uses `select(UsageMonthly.used)` + `scalar_one_or_none()` or `select(UsageMonthly)` + `.first()` + extract `.used` — either is fine
- Import organization after removing `from sqlalchemy import text` and adding model/construct imports
- Whether to add inline comments explaining the atomic pattern

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Database Layer (target file)
- `src/nativespeaker/api/database/usage.py` — The file to rewrite; currently 100% raw SQL via `text()`

### Models (source of truth for ORM constructs)
- `src/nativespeaker/api/models/users.py` — `UsageMonthly` model with all fields, constraints, and table args

### Established ORM Patterns (reference implementations)
- `src/nativespeaker/api/database/users.py` — `pg_insert().on_conflict_do_nothing()` pattern for upserts
- `src/nativespeaker/api/database/subscriptions.py` — `pg_insert().on_conflict_do_nothing()` pattern + model-based updates
- `src/nativespeaker/api/database/chats.py` — SQLModel `select()` pattern for reads

### Tests
- `tests/` — Any tests exercising `UsageDB` methods need to remain green after the rewrite

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pg_insert` from `sqlalchemy.dialects.postgresql` — already imported in `users.py` and `subscriptions.py`
- `UsageMonthly` model in `models/users.py` — has all fields (id, user_id, month, used) with UniqueConstraint on (user_id, month)
- `uuid7()` from `uuid` — already used for ID generation throughout the codebase

### Established Patterns
- Session-in-init: all DB classes take `AsyncSession` in `__init__`, store as `self.session`
- `pg_insert(Model).values(...).on_conflict_do_nothing(index_elements=[...])` for upserts
- `select(Model).where(...)` with `(await self.session.exec(statement)).first()` for reads
- SQLAlchemy core `update()` available for atomic operations that can't use ORM load-modify-flush

### Integration Points
- `UsageDB` is instantiated via dependency injection in `app/dependencies.py`
- Callers (`ChatService`, routers) depend on the return types (`bool`, `int`, `None`) — these don't change

</code_context>

<specifics>
## Specific Ideas

- User confirmed two-statement pattern for `try_increment` after seeing preview of both approaches
- User asked about `scalar_one_or_none()` for `get_usage` — left as Claude's discretion since both approaches work
- The `on_conflict_do_nothing(index_elements=["user_id", "month"])` maps to the UniqueConstraint on UsageMonthly

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 29-replace-all-raw-sql-with-proper-sqlmodel-use-in-database*
*Context gathered: 2026-03-24*
