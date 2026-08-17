# Phase 21: User Management - Research

**Researched:** 2026-03-20
**Domain:** JIT user provisioning, SQLModel/SQLAlchemy INSERT ON CONFLICT, FastAPI dependency refactoring
**Confidence:** HIGH

## Summary

Phase 21 adds a local user table with just-in-time provisioning from Firebase JWT identity. The core technical challenge is the INSERT ON CONFLICT DO NOTHING pattern for race-safe user creation, refactoring the auth dependency chain from returning a string `user_id` to returning a full `User` model object, and migrating the chat table's `user_id` column from TEXT to a UUID foreign key.

The project already has well-established patterns for everything needed: `BaseTable` for models, `ChatsDB` session-in-init pattern for database classes, `ChatService` for service layer, and `dependency_overrides` for test DI. The new code follows these patterns directly. The only genuinely new pattern is using SQLAlchemy Core's `pg_insert().on_conflict_do_nothing()` within an async SQLModel session for race-safe provisioning.

**Primary recommendation:** Follow existing codebase patterns exactly. The only new technical element is `sqlalchemy.dialects.postgresql.insert` for the upsert -- everything else is repetition of established patterns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- User table with uuid7 PK, `jwt_sub` column (UNIQUE, indexed) for Firebase identity
- Fields: id (uuid7), jwt_sub (str, unique), email (str, required), name (str, nullable), plan (PlanTier StrEnum, default "free"), active (bool, default True), created_at (datetime)
- PlanTier as StrEnum: free/silver/gold/platinum
- `active` field for soft-delete: inactive users get opaque 401 AUTH_FAILED
- Email required from JWT, name optional (nullable)
- JWTVerifier.verify() return type changes from `str` to `UserIdentity` dataclass (sub, email, name)
- TokenVerifier Protocol updated to match: `verify(token) -> UserIdentity`
- Provisioning happens inside `get_user_id` dependency, renamed to `get_current_user`, returns User model object
- `get_current_user` adds a DB session via `Depends(get_db)` for provisioning
- INSERT ON CONFLICT DO NOTHING on jwt_sub, then SELECT to get existing record
- Snapshot at creation -- email/name NOT synced from JWT on subsequent requests
- Inactive users rejected with AuthenticationError (opaque 401)
- New UsersDB class in `app/database/users_db.py` following session-in-init pattern
- New UserService class in `app/services/user_service.py` wrapping UsersDB
- chats.user_id changes from TEXT to UUID FK referencing users.id (ON DELETE RESTRICT)
- Rewrite pogo-migrate SQL in migrations/ (no existing data to migrate)
- Chat model gets SQLAlchemy Relationship to User
- ChatsDB methods switch from `user_id: str` to `user_id: UUID` throughout
- All chat routes change from `user_id: str = Depends(get_user_id)` to `user: User = Depends(get_current_user)`, passing `user.id`
- `GET /users/me` in new `app/routers/users.py` router
- Returns: email, name, plan, created_at (no internal id exposed)
- Transaction rollback (Phase 18) handles JIT-created user records

### Claude's Discretion
- Pydantic response schema for GET /users/me
- UserIdentity dataclass location (auth.py or separate module)
- Exact UsersDB method signatures and query patterns
- UserService method signatures
- Test structure for new user endpoints

### Deferred Ideas (OUT OF SCOPE)
- Profile sync from JWT on subsequent requests
- User profile editing (PUT /users/me)
- User deactivation mechanism
- Usage/quota data in GET /users/me response (Phase 23)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| USER-01 | User record is auto-created in local PostgreSQL on first authenticated API request (JIT provisioning) | INSERT ON CONFLICT DO NOTHING pattern verified with SQLAlchemy pg_insert + SQLModel. UserIdentity dataclass extracts claims. get_current_user dependency does provisioning. |
| USER-02 | User can retrieve their profile via `GET /users/me` | New users router, Pydantic response schema, UserService.get_user_by_id() |
| USER-03 | Concurrent first requests from same user do not create duplicate records | ON CONFLICT DO NOTHING on jwt_sub unique index handles race condition at DB level |
| USER-04 | Users cannot access other users' data (existing isolation extended to user records) | get_current_user returns User object scoped to JWT identity; /users/me only returns own profile; chat isolation unchanged (user_id FK filtering) |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLModel | 0.0.37 | User model, Chat FK change | Already used for Chat/Message models |
| SQLAlchemy | 2.0.46 | pg_insert ON CONFLICT, async session | Already the ORM backend |
| FastAPI | 0.135.1 | New users router, dependency chain | Already the web framework |
| Pydantic | 2.12.5 | UserProfileResponse schema | Already used for all API schemas |
| asyncpg | 0.30+ | PostgreSQL driver | Already the async driver |
| structlog | 25.5+ | Request-scoped logging with user_id binding | Already configured |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlalchemy.dialects.postgresql.insert | (part of SQLAlchemy) | INSERT ON CONFLICT DO NOTHING | JIT user provisioning in UsersDB |

### No New Dependencies
This phase requires zero new packages. Everything is available in the current dependency set.

## Architecture Patterns

### Recommended File Changes
```
app/
  auth.py                    # Add UserIdentity dataclass, change verify() return type
  models.py                  # Add PlanTier StrEnum, User model, Chat FK change
  api/
    dependencies.py          # Rename get_user_id -> get_current_user, add DB provisioning
  database/
    __init__.py              # Add UsersDB re-export
    users_db.py              # NEW: UsersDB with get_or_create, get_by_id
  services/
    __init__.py              # Add UserService re-export
    user_service.py          # NEW: UserService wrapping UsersDB
  routers/
    __init__.py              # Add users_router re-export
    users.py                 # NEW: GET /users/me
    chats.py                 # Change Depends(get_user_id) -> Depends(get_current_user)
migrations/
  20260317_01_bvi4l-initial-release.sql  # Rewrite with users table + FK
tests/
  unit/
    conftest.py              # Update _FixedKeyVerifier, get_user_id override
    test_users.py            # NEW: unit tests for user provisioning + profile
  e2e/
    conftest.py              # Update create_chat helper for UUID user_id
    test_isolation.py        # May need update for User FK
```

### Pattern 1: UserIdentity Dataclass (in auth.py)
**What:** Frozen dataclass returned by verify() instead of bare string
**When to use:** TokenVerifier.verify() return type
**Example:**
```python
# Source: verified with Python 3.14 dataclass
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class UserIdentity:
    sub: str
    email: str
    name: str | None = None
```
**Recommendation:** Place in `app/auth.py` alongside TokenVerifier Protocol. It is a small data carrier tightly coupled to the auth verification flow. Keeping it co-located avoids a separate module for a single dataclass.

### Pattern 2: INSERT ON CONFLICT DO NOTHING (in UsersDB)
**What:** Race-safe user provisioning using PostgreSQL's ON CONFLICT clause
**When to use:** First-time user creation in get_current_user dependency
**Example:**
```python
# Source: verified with SQLAlchemy 2.0.46 + SQLModel 0.0.37
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def get_or_create(self, identity: UserIdentity) -> User:
    stmt = (
        pg_insert(User)
        .values(jwt_sub=identity.sub, email=identity.email, name=identity.name)
        .on_conflict_do_nothing(index_elements=["jwt_sub"])
    )
    await self.session.exec(stmt)
    # Always SELECT after -- INSERT may have been a no-op
    result = await self.session.exec(
        select(User).where(User.jwt_sub == identity.sub)
    )
    return result.one()
```

### Pattern 3: get_current_user Dependency (in dependencies.py)
**What:** Replaces get_user_id, adds DB provisioning, returns User model
**When to use:** Every authenticated route
**Example:**
```python
# Source: follows existing get_user_id pattern in app/api/dependencies.py
async def get_current_user(request: Request,
                           authorization: str | None = Header(None),
                           db: AsyncSession = Depends(get_db)) -> User:
    # 1. Extract and verify token (same as current get_user_id)
    # 2. JIT provision user via UserService
    # 3. Check active flag
    # 4. Bind user_id to structlog contextvars
    # 5. Return User model
```

### Pattern 4: Pydantic Response Schema
**What:** Response model for GET /users/me
**Recommendation:** Define in `app/api/schema.py` alongside other response models.
```python
class UserProfileResponse(BaseModel):
    email: str
    name: str | None = None
    plan: str
    created_at: datetime
```

### Anti-Patterns to Avoid
- **Using session.add() for upsert:** SQLModel's session.add() has no ON CONFLICT support. Must use Core `pg_insert()` for race-safe provisioning.
- **Querying user on every request after creation:** The INSERT ON CONFLICT + SELECT pattern is two queries on first request, but for subsequent requests only the SELECT is needed. Do not add a third query to "check if insert happened."
- **Exposing internal user ID in /users/me response:** The CONTEXT.md explicitly excludes `id` from the response. Only email, name, plan, created_at.
- **Making get_current_user async unnecessarily complex:** It needs DB access, so it must be async. Keep the flow linear: verify token -> provision user -> check active -> return.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Race-safe upsert | Manual try/except IntegrityError loop | `pg_insert().on_conflict_do_nothing()` | Single atomic statement, no retry needed, handles concurrent requests at DB level |
| JWT claim extraction | Manual payload dict parsing | `UserIdentity` dataclass from verified payload dict | Type safety, immutability, clear contract |
| User model validation | Manual field checking | SQLModel + Pydantic defaults | Automatic validation, serialization, schema generation |

**Key insight:** PostgreSQL's ON CONFLICT clause handles the entire concurrency problem at the database level. No application-level locking, no retry loops, no distributed coordination needed.

## Common Pitfalls

### Pitfall 1: Forgetting to SELECT after INSERT ON CONFLICT DO NOTHING
**What goes wrong:** INSERT ON CONFLICT DO NOTHING returns no rows when the conflict occurs (existing user). If you rely on RETURNING, you get None for existing users.
**Why it happens:** RETURNING only returns rows that were actually inserted, not conflicting rows.
**How to avoid:** Always follow with a SELECT to get the user regardless of whether INSERT or conflict occurred.
**Warning signs:** `None` returned for existing users, `AttributeError` on user object.

### Pitfall 2: Session flush ordering with pg_insert
**What goes wrong:** SQLAlchemy Core insert (pg_insert) and ORM operations (session.add) in the same session can have unexpected flush ordering.
**Why it happens:** Core statements execute immediately; ORM add() is deferred until flush.
**How to avoid:** Execute pg_insert via `session.exec()` and flush/commit before any ORM operations that depend on the inserted row. In this project, the `get_db` dependency already handles commit.
**Warning signs:** FK violations when creating a Chat referencing a User that was just inserted.

### Pitfall 3: Changing get_user_id to get_current_user breaks all dependency overrides
**What goes wrong:** Unit tests override `get_user_id` in `dependency_overrides`. Renaming it breaks all test fixtures.
**Why it happens:** dependency_overrides key is the function reference, not the name.
**How to avoid:** Update ALL test conftest fixtures and dependency_overrides in the same change. The unit conftest overrides `get_user_id` with `lambda: "test-user"` -- this must change to return a User model object.
**Warning signs:** Test failures with `AttributeError: 'str' object has no attribute 'id'`.

### Pitfall 4: Chat.user_id type change cascades widely
**What goes wrong:** Changing `Chat.user_id` from `str` to `UUID` breaks ChatsDB method signatures, ChatService calls, and e2e test helpers.
**Why it happens:** The type flows through the entire call chain: route -> dependency -> service -> DB.
**How to avoid:** Change systematically: model first, then DB class, then service, then routes. Run tests after each layer.
**Warning signs:** Type errors from Pyright/ty, runtime UUID vs str comparison failures.

### Pitfall 5: E2E create_chat helper uses string user_id
**What goes wrong:** `tests/e2e/conftest.py::create_chat()` creates `Chat(user_id=user_id)` where `user_id` is the Firebase UID string. After the FK change, it must be a UUID referencing users.id.
**Why it happens:** The helper was written when user_id was a raw Firebase string.
**How to avoid:** The e2e helper must first ensure a User record exists (via JIT provisioning or direct insert), then use `user.id` as the chat's `user_id`.
**Warning signs:** FK violation errors in e2e tests.

### Pitfall 6: Inactive user check must use opaque 401
**What goes wrong:** Returning a specific "account deactivated" message leaks information about account existence.
**Why it happens:** Developer instinct to give helpful error messages.
**How to avoid:** Use the same `AuthenticationError` as invalid tokens -- the CONTEXT.md specifies opaque 401 AUTH_FAILED with no "account deactivated" reveal.
**Warning signs:** Response body mentioning "deactivated" or "inactive".

## Code Examples

### User Model (verified pattern)
```python
# Source: verified with SQLModel 0.0.37, matches existing Chat/Message pattern
from enum import StrEnum

class PlanTier(StrEnum):
    free = "free"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"

class User(BaseTable, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    jwt_sub: str = Field(unique=True, index=True, sa_type=Text())
    email: str = Field(sa_type=Text())
    name: str | None = Field(default=None, sa_type=Text())
    plan: PlanTier = Field(default=PlanTier.free, sa_type=Text())
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC),
                                  sa_type=DateTime(timezone=True))
```

### Migration SQL (rewrite)
```sql
-- users table MUST be created before chats (FK dependency)
CREATE TABLE users (
    id UUID PRIMARY KEY,
    jwt_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_users_jwt_sub ON users (jwt_sub);

CREATE TABLE chats (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    lang TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_chats_user_id ON chats (user_id);
```

### JWTVerifier.verify() change
```python
# Source: existing app/auth.py pattern + UserIdentity addition
def verify(self, token: str) -> UserIdentity:
    # ... existing JWT decode logic ...
    sub = payload.get("sub")
    if not sub:
        raise AuthenticationError("Missing sub claim")
    return UserIdentity(
        sub=str(sub),
        email=payload.get("email", ""),
        name=payload.get("name"),
    )
```

### Unit test dependency override pattern

```python
# Source: existing tests/unit/conftest.py pattern
from models import User, PlanTier

TEST_USER = User(
    jwt_sub="test-user",
    email="test@example.com",
    name="Test User",
    plan=PlanTier.free,
    active=True,
)

# In client fixture:
app.dependency_overrides[get_current_user] = lambda: TEST_USER
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `verify() -> str` | `verify() -> UserIdentity` | This phase | All verifier implementations + test stubs must update |
| `get_user_id` returning str | `get_current_user` returning User | This phase | All routes and test overrides must update |
| `Chat.user_id: str` (TEXT) | `Chat.user_id: UUID` (FK) | This phase | Full call chain update: DB, service, routes, tests |

**No deprecated APIs involved:** All patterns used (pg_insert, SQLModel Field, Relationship, dataclass) are current and stable.

## Open Questions

1. **Email claim requirement from Firebase**
   - What we know: Firebase ID tokens include `email` claim for email/password auth. CONTEXT.md says email is required.
   - What's unclear: Some Firebase auth providers (anonymous, phone) may not include email. The project uses email/password auth for tests.
   - Recommendation: Extract email from JWT payload, use empty string fallback if absent (defensive). The verify() method can raise if email is missing for stricter enforcement.

2. **Session commit timing for JIT provisioning + chat creation**
   - What we know: `get_db` dependency yields a session, commits on success. `get_current_user` uses `Depends(get_db)` for provisioning. Chat routes also use `Depends(get_db)` via `get_chat_service`.
   - What's unclear: Are these the same session or different? If different, the user INSERT must be committed before the chat INSERT (FK constraint).
   - Recommendation: `get_current_user` should use its own `Depends(get_db)` call. FastAPI resolves the same dependency to the same value within a single request, so both `get_current_user` and `get_chat_service` receive the same `AsyncSession` instance. This means the user INSERT and chat INSERT happen in the same transaction -- no commit ordering issue. The `get_db` dependency commits once at the end.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -m 'not e2e' -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| USER-01 | JIT provisioning creates user on first request | unit | `python -m pytest tests/unit/test_users.py::test_jit_provisioning -x` | Wave 0 |
| USER-01 | UserIdentity extracted from JWT claims | unit | `python -m pytest tests/unit/test_users.py::test_user_identity_from_jwt -x` | Wave 0 |
| USER-02 | GET /users/me returns profile | unit | `python -m pytest tests/unit/test_users.py::test_get_users_me -x` | Wave 0 |
| USER-02 | Response excludes internal id | unit | `python -m pytest tests/unit/test_users.py::test_profile_no_internal_id -x` | Wave 0 |
| USER-03 | Concurrent inserts produce no duplicates | unit | `python -m pytest tests/unit/test_users.py::test_concurrent_provisioning -x` | Wave 0 |
| USER-04 | Cannot access other user's profile | unit | `python -m pytest tests/unit/test_users.py::test_user_isolation -x` | Wave 0 |
| USER-04 | Inactive user gets opaque 401 | unit | `python -m pytest tests/unit/test_users.py::test_inactive_user_rejected -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -m 'not e2e' -x -q`
- **Phase gate:** Full unit suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_users.py` -- covers USER-01 through USER-04
- [ ] Update `tests/unit/conftest.py` -- _FixedKeyVerifier returns UserIdentity, dependency override returns User model
- [ ] Update `tests/e2e/conftest.py` -- create_chat helper uses UUID user_id with User FK

## Sources

### Primary (HIGH confidence)
- SQLAlchemy 2.0.46 `postgresql.insert` -- verified locally with `pg_insert().on_conflict_do_nothing(index_elements=['jwt_sub'])` compiles correctly
- SQLModel 0.0.37 -- verified table=True models work with pg_insert Core statements
- Python 3.14 `dataclasses` -- verified `@dataclass(frozen=True, slots=True)` with optional fields
- Existing codebase files (auth.py, dependencies.py, models.py, chats_db.py, chat_service.py, conftest.py) -- read and analyzed directly

### Secondary (MEDIUM confidence)
- [SQLAlchemy 2.1 PostgreSQL docs](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html) -- INSERT ON CONFLICT API reference, RETURNING behavior
- [SQLAlchemy ON CONFLICT discussion](https://github.com/sqlalchemy/sqlalchemy/discussions/7831) -- confirms Core pg_insert is the correct approach, not ORM session.add()

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, versions verified locally
- Architecture: HIGH -- follows exact existing patterns (ChatsDB, ChatService, dependency chain)
- Pitfalls: HIGH -- verified through code reading and local testing of SQL compilation
- Upsert pattern: HIGH -- pg_insert ON CONFLICT verified to compile correctly with SQLModel tables

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (stable patterns, no fast-moving dependencies)
