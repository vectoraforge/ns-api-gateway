# Architecture Patterns

**Domain:** Schema hardening -- native PG enums and config-driven quotas in existing FastAPI + SQLAlchemy async + SQLModel + Pydantic v2 app
**Researched:** 2026-03-23
**Overall confidence:** HIGH (codebase fully inspected, SQLAlchemy Enum docs verified, all integration points traced)

## Current Architecture Snapshot (v1.5)

```
FastAPI (app/main.py)
  |-- lifespan: engine, session_factory, JWTVerifier, LLMService, FirebaseService, AppleVerifier -> app.state
  |-- config: AppConfig (Pydantic-validated YAML)
  |-- routers: chats, examples, health, root, users, webhooks
  |-- dependencies.py: get_db, get_config, get_current_user, get_chat_service, get_subscription_service
  |
  v
Service Layer
  |-- ChatService (per-request, receives db session + LLMService)
  |     |-- ChatsDB (session-in-init, SQLModel queries)
  |     |-- UsageDB (session-in-init, RAW SQL with JOINs to plans table)
  |-- SubscriptionService (per-request)
  |     |-- SubscriptionDB (session-in-init, SQLModel queries)
  |     |-- UsageDB (for reset_usage on tier change)
  |-- UserService (per-request)
  |     |-- UsersDB (session-in-init, SQLModel queries)
  |
  v
SQLAlchemy Async (PostgreSQL, "core" schema)
  |-- Plan (tier:TEXT PK, monthly_quota:INT) <-- REMOVAL TARGET
  |-- User (id:UUID, jwt_sub:TEXT, plan:TEXT FK->plans.tier)
  |-- Subscription (id:UUID, plan:TEXT FK->plans.tier, status:TEXT, provider:TEXT)
  |-- SubscriptionEvent (event_type:TEXT, old_tier:TEXT, new_tier:TEXT)
  |-- UsageMonthly (user_id FK->users.id, month:TEXT, used:INT)
  |-- Chat (id:UUID, user_id FK->users.id)
  |-- Message (id:UUID, role:TEXT, content:JSONB)
```

### Current Pain Points This Milestone Resolves

1. **`core.plans` is a static lookup table** -- its 4 rows (free/silver/gold/platinum) never change at runtime, yet `UsageDB.try_increment` JOINs against it on every chat creation request. This is unnecessary database I/O for configuration data.

2. **All enum columns are `TEXT`** -- `Role`, `Tier`, `SubscriptionProvider`, `SubscriptionStatus` exist as Python `StrEnum` types but are stored as unbounded `TEXT` in PostgreSQL. No database-level constraint prevents invalid values.

3. **FK constraints on `plans` table** -- `users.plan` and `subscriptions.plan` both reference `plans(tier)`, meaning the plans table cannot be dropped without first dropping these constraints.

---

## Target Architecture (v1.6)

```
FastAPI (app/main.py)
  |-- lifespan: unchanged
  |-- config: AppConfig + NEW QuotaConfig (tier->monthly_quota mapping)
  |-- routers: unchanged
  |-- dependencies.py: get_chat_service NOW passes quota_config; users router uses config for monthly_limit
  |
  v
Service Layer
  |-- ChatService: receives QuotaConfig, passes to UsageDB
  |-- SubscriptionService: unchanged (no quota reads)
  |-- UserService: unchanged
  |
  v
Database Layer
  |-- UsageDB: try_increment accepts monthly_quota:int param (no more JOIN)
  |           get_monthly_limit REMOVED (moved to config lookup)
  |-- UsersDB: unchanged
  |-- SubscriptionDB: unchanged
  |
  v
SQLAlchemy Async (PostgreSQL, "core" schema)
  |-- [DELETED] Plan table
  |-- User (plan: core.tier ENUM, no FK)
  |-- Subscription (plan: core.tier ENUM, status: core.subscription_status ENUM,
  |                  provider: core.subscription_provider ENUM, no FK)
  |-- SubscriptionEvent (old_tier: core.tier ENUM, new_tier: core.tier ENUM)
  |-- Message (role: core.role ENUM)
  |-- UsageMonthly: unchanged
  |-- Chat: unchanged
  |
  v
PostgreSQL Native Types (in "core" schema)
  |-- CREATE TYPE core.role AS ENUM ('human', 'ai')
  |-- CREATE TYPE core.tier AS ENUM ('free', 'silver', 'gold', 'platinum')
  |-- CREATE TYPE core.subscription_provider AS ENUM ('apple')
  |-- CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked')
```

---

## Component-by-Component Changes

### 1. Config: Add QuotaConfig (NEW)

**Where:** `src/nativespeaker/api/config.py`

**What changes:** Add a Pydantic model that maps `Tier -> monthly_quota`. This replaces the `plans` table as the source of truth.

```python
from nativespeaker.api.models import Tier

class QuotaConfig(BaseModel):
    tier_quotas: dict[Tier, int] = Field(
        description="Monthly request quota per plan tier"
    )

    def monthly_quota(self, tier: Tier) -> int:
        return self.tier_quotas[tier]
```

**Where configured:** `config.yaml` gains a new section:

```yaml
quotas:
  tier_quotas:
    free: 150
    silver: 1500
    gold: 3000
    platinum: 30000
```

**AppConfig adds:**
```python
class AppConfig(BaseConfig):
    # ... existing fields ...
    quotas: QuotaConfig = Field(default_factory=QuotaConfig)
```

**Rationale:** The plans table currently stores exactly this mapping. Moving it to config means:
- No database I/O for configuration reads
- Quota changes deploy via config update, not SQL migration
- Pydantic validates all tiers are present at startup (fail-fast)

**Confidence:** HIGH -- follows the existing pattern for `product_id_to_tier` in `AppleConfig`.

### 2. Models: Native PG Enum Column Types (MODIFIED)

**Where:** `src/nativespeaker/api/models.py`

**What changes:** Each `StrEnum` field on a table model gets `sa_type=SAEnum(EnumClass, ...)` to use native PostgreSQL `CREATE TYPE` enum instead of `TEXT`.

**Approach -- use `sa_type` with `sqlalchemy.Enum`:**

The project already uses `sa_type=PydanticJSONB` on `Message.content`. The same parameter works for enum types. The key configuration for SQLAlchemy's `Enum` type:

- `schema="core"` -- place the PG type in the `core` schema alongside the tables
- `create_type=False` -- the migration handles `CREATE TYPE`, not SQLAlchemy's `create_all()`
- `values_callable=lambda e: [m.value for m in e]` -- persist enum *values* (e.g., `"human"`) not *names* (e.g., `"HUMAN"`). Required because `StrEnum` members have lowercase values that match the member names, but this is explicit safety.

```python
from sqlalchemy import Enum as SAEnum

# Define reusable type objects (module-level, shared across models)
RoleType = SAEnum(Role, schema="core", create_type=False,
                  values_callable=lambda e: [m.value for m in e])
TierType = SAEnum(Tier, schema="core", create_type=False,
                  values_callable=lambda e: [m.value for m in e])
ProviderType = SAEnum(SubscriptionProvider, schema="core", create_type=False,
                      values_callable=lambda e: [m.value for m in e])
SubStatusType = SAEnum(SubscriptionStatus, schema="core", create_type=False,
                       values_callable=lambda e: [m.value for m in e])
```

**Model changes:**

```python
class Message(BaseTable, table=True):
    # ...
    role: Role = Field(sa_type=RoleType)  # was: Field()

class User(BaseTable, table=True):
    # ...
    plan: Tier = Field(default=Tier.free, sa_type=TierType)  # was: str with FK

class Subscription(BaseTable, table=True):
    # ...
    provider: SubscriptionProvider = Field(sa_type=ProviderType)  # was: Field()
    plan: Tier = Field(sa_type=TierType)  # was: str with FK
    status: SubscriptionStatus = Field(sa_type=SubStatusType)  # was: Field()

class SubscriptionEvent(BaseTable, table=True):
    # ...
    old_tier: Tier | None = Field(default=None, sa_type=TierType)  # was: str | None
    new_tier: Tier | None = Field(default=None, sa_type=TierType)  # was: str | None
```

**Why `create_type=False`:** The `CREATE TYPE` statements must exist in the migration (executed before the column `ALTER TYPE` statements). If `create_type=True` (default), SQLAlchemy's `create_all()` would attempt to create them, conflicting with the migration. Since this project uses pogo-migrate for DDL, SQLAlchemy should never create types.

**Why `schema="core"`:** All tables are in the `core` schema. The enum types must also live in `core` so column definitions reference `core.role`, `core.tier`, etc. Without this parameter, SQLAlchemy would place types in `public`.

**Why `values_callable`:** SQLAlchemy's default for `StrEnum` persists the member `.value`. The `values_callable` makes this explicit and prevents surprises if a future refactor changes enum member casing.

**What about `User.plan` type change?** Currently `plan: str = Field(default="free", foreign_key="core.plans.tier")`. This changes to `plan: Tier = Field(default=Tier.free, sa_type=TierType)`. The FK is removed (plans table goes away), and the Python type narrows from `str` to `Tier`.

**Confidence:** HIGH -- `sa_type` with `SAEnum` is the documented SQLAlchemy approach, and this project already uses `sa_type` for `PydanticJSONB`.

**Source:** [SQLAlchemy Enum type docs](https://docs.sqlalchemy.org/en/20/core/type_basics.html), [GitHub discussion #10583 on schema-scoped enums](https://github.com/sqlalchemy/sqlalchemy/discussions/10583), [GitHub discussion #12123 on StrEnum handling](https://github.com/sqlalchemy/sqlalchemy/discussions/12123)

### 3. Plan Model: DELETED

**Where:** `src/nativespeaker/api/models.py`

**What happens:** Remove the `Plan` class entirely. No other model references it via `Relationship()` -- the FK constraints are simple column-level foreign keys on `User.plan` and `Subscription.plan`.

```python
# REMOVE entirely:
class Plan(BaseTable, table=True):
    __tablename__ = "plans"
    __table_args__ = {"schema": "core"}
    tier: str = Field(primary_key=True)
    monthly_quota: int = Field()
```

### 4. UsageDB: Config-Driven Quotas (MODIFIED)

**Where:** `src/nativespeaker/api/database/usage.py`

**What changes:**

The `try_increment` method currently JOINs against the `plans` table to get `monthly_quota`. After this change, it receives the quota as a parameter.

**Current `try_increment` (raw SQL with JOIN):**
```sql
UPDATE usage_monthly u
SET used = u.used + 1
FROM plans p
WHERE u.user_id = :user_id
  AND u.month = :month
  AND p.tier = (SELECT plan FROM users WHERE id = :user_id)
  AND u.used < p.monthly_quota
RETURNING u.used
```

**New `try_increment` (quota as param, no JOIN):**
```sql
UPDATE core.usage_monthly u
SET used = u.used + 1
WHERE u.user_id = :user_id
  AND u.month = :month
  AND u.used < :monthly_quota
RETURNING u.used
```

The subquery `SELECT plan FROM users WHERE id = :user_id` and the JOIN to `plans` are both eliminated. The caller (ChatService) looks up the quota from config before calling.

**`get_monthly_limit` method: REMOVED.** This method existed solely to read `plans.monthly_quota` via a JOIN. The users router now reads the quota directly from config.

**Updated interface:**
```python
class UsageDB:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def try_increment(self, user_id: UUID, month: str, monthly_quota: int) -> bool:
        # INSERT ON CONFLICT DO NOTHING (ensure row exists) -- unchanged
        # UPDATE with used < :monthly_quota -- no JOIN
        ...

    async def get_usage(self, user_id: UUID, month: str) -> int:
        # unchanged
        ...

    async def reset_usage(self, user_id: UUID, month: str) -> None:
        # unchanged
        ...
```

**Confidence:** HIGH -- the raw SQL is straightforward; removing the JOIN simplifies it.

### 5. ChatService: Pass Quota from Config (MODIFIED)

**Where:** `src/nativespeaker/api/services/chats.py`

**What changes:** ChatService needs access to `QuotaConfig` to look up the user's quota before calling `try_increment`.

**Current flow:**
```
ChatService.create_chat(user_id, phrase, ...) ->
  UsageDB.try_increment(user_id, month) ->  # UsageDB reads quota from plans table
```

**New flow:**
```
ChatService.create_chat(user_id, phrase, ...) ->
  user = get User from DB (already available via caller context)
  quota = QuotaConfig.monthly_quota(user.plan)
  UsageDB.try_increment(user_id, month, quota) ->  # quota passed as param
```

**Design decision: How does ChatService know the user's tier?**

Currently `ChatService.create_chat` receives `user_id: UUID` but not the `User` object. The `User` object is resolved in the `get_current_user` dependency. Two options:

**Option A: Pass `User` object into ChatService methods.** The routes already have `user: User = Depends(get_current_user)`. Pass `user` instead of `user.id` to `create_chat` and `send_message`.

**Option B: Pass `Tier` into ChatService at construction via DI.** The `get_chat_service` dependency already receives `config: AppConfig`. Add the user's tier.

**Recommendation: Option A** -- Pass the `User` object. This avoids adding a new constructor parameter that varies per request. The route already resolves the user. The method signature changes from `create_chat(user_id: UUID, ...)` to `create_chat(user: User, ...)`.

```python
class ChatService:
    def __init__(self, db, llm_service, examples, messages_limit, chats_limit, quota_config):
        # ...
        self.quota_config = quota_config

    async def create_chat(self, user: User, phrase: str, ...) -> Message:
        quota = self.quota_config.monthly_quota(Tier(user.plan))
        month = datetime.now(UTC).strftime("%Y-%m")
        if not await self.usage_db.try_increment(user.id, month, quota):
            raise QuotaExceededError("Monthly quota exceeded")
        # ... rest unchanged
```

**DI change in `dependencies.py`:**
```python
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit,
                       quota_config=config.quotas)  # NEW param
```

**Confidence:** HIGH -- follows existing DI patterns.

### 6. Users Router: Config-Driven Monthly Limit (MODIFIED)

**Where:** `src/nativespeaker/api/routers/users.py`

**What changes:** The `get_me` endpoint currently calls `usage_db.get_monthly_limit(user.id)` which JOINs against `plans`. Replace with config lookup.

**Current:**
```python
monthly_limit = await usage_db.get_monthly_limit(user.id)
```

**New:**
```python
config: AppConfig = ...  # from DI
monthly_limit = config.quotas.monthly_quota(Tier(user.plan))
```

The route needs `AppConfig` via DI. Add `config: AppConfig = Depends(get_config)` to the route signature.

### 7. SubscriptionEvent: Type Narrowing (MODIFIED)

**Where:** `src/nativespeaker/api/models.py` and `src/nativespeaker/api/database/subscriptions.py`

The `SubscriptionEvent.old_tier` and `new_tier` fields change from `str | None` to `Tier | None`. The `insert_event_idempotent` method signature changes accordingly:

```python
async def insert_event_idempotent(self,
                                  subscription_id: UUID,
                                  event_type: str,
                                  notification_uuid: str,
                                  old_tier: Tier | None,
                                  new_tier: Tier | None) -> bool:
```

The callers in `SubscriptionService` already pass `Tier` enum values (e.g., `plan_tier` which is `Tier`), so this is a type annotation narrowing, not a behavioral change.

### 8. Schema Response: Type Narrowing (MODIFIED)

**Where:** `src/nativespeaker/api/schema.py`

`UserProfileResponse.plan` changes from `str` to `Tier`:

```python
class UserProfileResponse(BaseModel):
    # ...
    plan: Tier  # was: str
```

This narrows the OpenAPI schema from `string` to an enum, which is a non-breaking change for clients (existing valid values remain valid).

### 9. Migration: Single SQL Migration (NEW)

**Where:** `migrations/` (new pogo-migrate SQL file)

The migration must be ordered carefully:

```sql
-- Step 1: Create native enum types in core schema
CREATE TYPE core.role AS ENUM ('human', 'ai');
CREATE TYPE core.tier AS ENUM ('free', 'silver', 'gold', 'platinum');
CREATE TYPE core.subscription_provider AS ENUM ('apple');
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');

-- Step 2: Drop FK constraints referencing plans table
ALTER TABLE core.users DROP CONSTRAINT IF EXISTS users_plan_fkey;
ALTER TABLE core.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_plan_fkey;

-- Step 3: Convert TEXT columns to native enum types
ALTER TABLE core.messages ALTER COLUMN role TYPE core.role USING role::core.role;
ALTER TABLE core.users ALTER COLUMN plan TYPE core.tier USING plan::core.tier;
ALTER TABLE core.subscriptions ALTER COLUMN provider TYPE core.subscription_provider USING provider::core.subscription_provider;
ALTER TABLE core.subscriptions ALTER COLUMN plan TYPE core.tier USING plan::core.tier;
ALTER TABLE core.subscriptions ALTER COLUMN status TYPE core.subscription_status USING status::core.subscription_status;
ALTER TABLE core.subscription_events ALTER COLUMN old_tier TYPE core.tier USING old_tier::core.tier;
ALTER TABLE core.subscription_events ALTER COLUMN new_tier TYPE core.tier USING new_tier::core.tier;

-- Step 4: Drop plans table (no longer referenced)
DROP TABLE core.plans;
```

**`USING` clause:** Required because PostgreSQL cannot implicitly cast `TEXT` to a custom enum type. The `USING column::core.type` syntax tells PG to cast each existing text value to the enum. If any row contains a value not in the enum, the migration fails -- this is intentional (catches bad data).

**Rollback:**
```sql
-- Reverse: recreate plans, restore TEXT columns, restore FKs
ALTER TABLE core.subscription_events ALTER COLUMN new_tier TYPE TEXT;
ALTER TABLE core.subscription_events ALTER COLUMN old_tier TYPE TEXT;
ALTER TABLE core.subscriptions ALTER COLUMN status TYPE TEXT;
ALTER TABLE core.subscriptions ALTER COLUMN plan TYPE TEXT;
ALTER TABLE core.subscriptions ALTER COLUMN provider TYPE TEXT;
ALTER TABLE core.users ALTER COLUMN plan TYPE TEXT;
ALTER TABLE core.messages ALTER COLUMN role TYPE TEXT;

DROP TYPE core.subscription_status;
DROP TYPE core.subscription_provider;
DROP TYPE core.tier;
DROP TYPE core.role;

CREATE TABLE core.plans (
    tier TEXT PRIMARY KEY,
    monthly_quota INTEGER NOT NULL
);
INSERT INTO core.plans (tier, monthly_quota) VALUES
    ('free', 150), ('silver', 1500), ('gold', 3000), ('platinum', 30000);

ALTER TABLE core.users ADD CONSTRAINT users_plan_fkey FOREIGN KEY (plan) REFERENCES core.plans (tier);
ALTER TABLE core.subscriptions ADD CONSTRAINT subscriptions_plan_fkey FOREIGN KEY (plan) REFERENCES core.plans (tier);
```

**Confidence:** HIGH -- standard PostgreSQL DDL. The `USING` cast syntax is documented and widely used.

### 10. E2E Test Fixture: Remove Plans Seeding (MODIFIED)

**Where:** `tests/e2e/conftest.py`

The `ensure_tables` fixture currently seeds the `plans` table:

```python
await conn.execute(text(
    "INSERT INTO plans (tier, monthly_quota) VALUES "
    "('free', 150), ('silver', 1500), ('gold', 3000), ('platinum', 30000) "
    "ON CONFLICT (tier) DO NOTHING"
))
```

This entire block is removed. The plans table no longer exists. The native enum types are created by the migration, and SQLModel's `create_all()` does NOT create them (because `create_type=False`).

**New requirement:** The `ensure_tables` fixture must execute the `CREATE TYPE` statements before `create_all()`, because `create_all()` will try to create tables that reference these types.

```python
async def _create():
    engine = create_async_engine(_app_config.db.url, pool_size=1, max_overflow=0)
    async with engine.begin() as conn:
        # Create enum types before tables (create_type=False means create_all won't do it)
        for stmt in [
            "CREATE TYPE IF NOT EXISTS core.role AS ENUM ('human', 'ai')",
            "CREATE TYPE IF NOT EXISTS core.tier AS ENUM ('free', 'silver', 'gold', 'platinum')",
            "CREATE TYPE IF NOT EXISTS core.subscription_provider AS ENUM ('apple')",
            "CREATE TYPE IF NOT EXISTS core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked')",
        ]:
            await conn.execute(text(stmt))
        await conn.run_sync(SQLModel.metadata.create_all)
    await engine.dispose()
```

**Note:** `CREATE TYPE IF NOT EXISTS` requires PostgreSQL 9.1+. Since this project uses a modern PG version (asyncpg requires PG 9.6+), this is safe.

**Confidence:** HIGH -- direct consequence of `create_type=False`.

### 11. Unit Test Fixtures: Minimal Changes (MODIFIED)

**Where:** `tests/unit/conftest.py`

The `mock_usage_db` fixture currently mocks `get_monthly_limit`. Since that method is removed from `UsageDB`, remove it from the mock:

```python
@pytest.fixture
def mock_usage_db():
    db = AsyncMock()
    db.try_increment = AsyncMock(return_value=True)
    db.get_usage = AsyncMock(return_value=0)
    db.reset_usage = AsyncMock(return_value=None)
    # REMOVED: db.get_monthly_limit
    return db
```

The `service` fixture needs to pass `quota_config`:

```python
@pytest.fixture
def service(mock_chats_db, mock_usage_db):
    from nativespeaker.api.config import QuotaConfig
    from nativespeaker.api.models import Tier
    quota_config = QuotaConfig(tier_quotas={
        Tier.free: 150, Tier.silver: 1500,
        Tier.gold: 3000, Tier.platinum: 30000
    })
    svc = ChatService(db=MagicMock(),
                      llm_service=AsyncMock(),
                      examples={"en": ["Example"], "es": ["Ejemplo"]},
                      messages_limit=50,
                      chats_limit=50,
                      quota_config=quota_config)
    svc.chats_db = mock_chats_db
    svc.usage_db = mock_usage_db
    return svc
```

The quota-related tests in `test_usage.py` need updating because `try_increment` now takes a `monthly_quota` parameter. The mock assertion changes from `try_increment(user_id, month)` to `try_increment(user_id, month, quota)`.

---

## Component Boundaries

| Component | Responsibility | Changed? | Communicates With |
|-----------|---------------|----------|-------------------|
| `config.py` | YAML config + validation | **MODIFIED** (add QuotaConfig) | Pydantic YAML loader |
| `models.py` | SQLModel table defs + StrEnums | **MODIFIED** (sa_type, remove Plan, type narrowing) | SQLAlchemy engine |
| `database/usage.py` | Usage queries | **MODIFIED** (quota param, remove get_monthly_limit) | AsyncSession |
| `database/subscriptions.py` | Subscription queries | **MODIFIED** (type narrowing in signatures) | AsyncSession |
| `database/users.py` | User queries | Unchanged | AsyncSession |
| `database/chats.py` | Chat queries | Unchanged | AsyncSession |
| `services/chats.py` | Chat business logic | **MODIFIED** (pass User + quota to try_increment) | UsageDB, ChatsDB, LLMService |
| `services/subscriptions.py` | Apple webhook logic | Unchanged (already uses Tier enum) | SubscriptionDB, UsageDB |
| `services/users.py` | User business logic | Unchanged | UsersDB |
| `routers/users.py` | GET /users/me | **MODIFIED** (config lookup for monthly_limit) | UsageDB, AppConfig |
| `app/dependencies.py` | FastAPI DI | **MODIFIED** (pass quota_config to ChatService) | AppConfig, services |
| `schema.py` | API response schemas | **MODIFIED** (plan: str -> Tier) | Pydantic |
| `migrations/` | DB schema DDL | **NEW** migration file | PostgreSQL |
| `tests/` | Test fixtures | **MODIFIED** (remove plans seeding, update mocks) | Test infrastructure |

---

## Data Flow: Quota Enforcement (Before and After)

### Before (v1.5):

```
Route: POST /chats
  |
  v
get_current_user -> User (user.id)
  |
  v
ChatService.create_chat(user_id=user.id, phrase=...)
  |
  v
UsageDB.try_increment(user_id, month)
  |-- INSERT usage_monthly ON CONFLICT DO NOTHING
  |-- UPDATE usage_monthly u
  |     FROM plans p                                   <-- JOIN to plans table
  |     WHERE p.tier = (SELECT plan FROM users ...)    <-- subquery to users
  |       AND u.used < p.monthly_quota                 <-- quota from DB
  |
  v
  True/False -> QuotaExceededError or proceed
```

### After (v1.6):

```
Route: POST /chats
  |
  v
get_current_user -> User (user object, including user.plan = Tier enum)
  |
  v
ChatService.create_chat(user=user, phrase=...)
  |-- quota = self.quota_config.monthly_quota(user.plan)   <-- config lookup, no DB
  |
  v
UsageDB.try_increment(user_id, month, monthly_quota=quota)
  |-- INSERT usage_monthly ON CONFLICT DO NOTHING
  |-- UPDATE usage_monthly u
  |     WHERE u.user_id = :user_id                         <-- direct filter, no JOIN
  |       AND u.month = :month
  |       AND u.used < :monthly_quota                      <-- quota from param
  |
  v
  True/False -> QuotaExceededError or proceed
```

### After (v1.6) -- GET /users/me:

```
Route: GET /users/me
  |
  v
get_current_user -> User (user.plan = Tier.gold)
get_config -> AppConfig (config.quotas)
  |
  v
monthly_limit = config.quotas.monthly_quota(user.plan)     <-- config lookup
requests_used = await usage_db.get_usage(user.id, month)   <-- unchanged query
  |
  v
UserProfileResponse(plan=user.plan, monthly_limit=..., requests_used=...)
```

---

## Patterns to Follow

### Pattern 1: Module-Level SA Type Objects
**What:** Define `SAEnum` type instances at module level in `models.py`, reuse across multiple model fields.
**Why:** Prevents creating duplicate PG type definitions. A single `TierType` object is used by `User.plan`, `Subscription.plan`, `SubscriptionEvent.old_tier`, and `SubscriptionEvent.new_tier`.

### Pattern 2: Config as DI Parameter
**What:** Pass `QuotaConfig` through the existing DI chain (AppConfig -> dependency -> service constructor).
**Why:** Consistent with how `product_id_to_tier`, `chats_limit`, and `messages_limit` are already passed. No new DI patterns.

### Pattern 3: Migration Owns DDL, SQLAlchemy Does Not
**What:** Use `create_type=False` on all `SAEnum` objects. The migration creates types, not `create_all()`.
**Why:** The project uses pogo-migrate for DDL management. SQLAlchemy's `create_all()` is only used in test fixtures. Having two DDL sources creates conflicts.

### Pattern 4: Narrow Types at Boundaries
**What:** Change `plan: str` to `plan: Tier` on models and schemas. Change `str | None` to `Tier | None` on event fields.
**Why:** SQLAlchemy auto-converts between PG enum values and Python enum members. Having the Python type match the PG type means invalid values are caught at both layers.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Using `create_type=True` (SQLAlchemy Default)
**What:** Letting SQLAlchemy auto-create PG enum types via `create_all()`.
**Why bad:** Conflicts with pogo-migrate ownership of DDL. In production, `create_all()` is never called -- only migrations run. In tests, `create_all()` would try to create types that may already exist, causing `DuplicateObject` errors.
**Instead:** `create_type=False` on all SAEnum objects. Test fixtures create types explicitly before `create_all()`.

### Anti-Pattern 2: Using `inherit_schema=True` Instead of Explicit `schema="core"`
**What:** Relying on `inherit_schema=True` to copy the table's schema to the enum type.
**Why bad:** This couples the type's schema to whichever table happens to define it first. If models are reordered or tables are moved, the enum schema silently changes. Also fragile with `create_type=False` -- the schema is informational only for SQLAlchemy's type system, but an explicit value is clearer.
**Instead:** Explicit `schema="core"` on every SAEnum instance.

### Anti-Pattern 3: Storing Quota in a New Config Column on User
**What:** Adding `monthly_quota: int` to the User table so the JOIN is replaced by a denormalized column.
**Why bad:** Creates a sync problem -- when quotas change, all user rows must be updated. The plans table had this exact problem.
**Instead:** Config lookup. Quotas are application configuration, not user data.

### Anti-Pattern 4: Keeping `get_monthly_limit` on UsageDB
**What:** Replacing the plans JOIN with a users-table query to read `user.plan`, then looking up quota from config inside UsageDB.
**Why bad:** Gives UsageDB knowledge of the config system. Database classes should be pure query wrappers -- they should not hold business logic or config references.
**Instead:** The service layer (ChatService) performs the config lookup and passes the resolved quota as a primitive `int` to UsageDB.

---

## Build Order (Dependency-Aware)

The changes have a clear dependency chain. The build order must respect it:

### Phase 1: Config + Model Foundation (No Behavioral Change)

**Step 1.1: Add QuotaConfig to config.py + config.yaml**
- New `QuotaConfig` Pydantic model
- Add `quotas` section to `config.yaml`
- Add `quotas: QuotaConfig` to `AppConfig`
- Zero risk: additive change, nothing reads it yet

**Step 1.2: Add SAEnum type objects to models.py**
- Define `RoleType`, `TierType`, `ProviderType`, `SubStatusType` at module level
- Apply `sa_type=...` to all enum fields
- Change `User.plan: str` to `User.plan: Tier` and remove `foreign_key="core.plans.tier"`
- Change `Subscription.plan: str` to `Subscription.plan: Tier` and remove FK
- Change `SubscriptionEvent.old_tier/new_tier` from `str | None` to `Tier | None`
- Delete `Plan` model class
- Update `UserProfileResponse.plan` from `str` to `Tier` in schema.py
- **Note:** The app still works against the existing TEXT columns because `StrEnum` values are strings. SQLAlchemy will cast transparently. But this step should be deployed alongside the migration (Step 3).

### Phase 2: Service + Database Layer Rewiring

**Step 2.1: Modify UsageDB**
- Add `monthly_quota: int` parameter to `try_increment`
- Rewrite SQL to remove JOIN and subquery
- Remove `get_monthly_limit` method

**Step 2.2: Modify ChatService**
- Add `quota_config: QuotaConfig` to constructor
- Change `create_chat` and `send_message` to accept `User` instead of `user_id: UUID`
- Look up quota from config, pass to `try_increment`

**Step 2.3: Modify users router**
- Add `config: AppConfig = Depends(get_config)` to `get_me` signature
- Replace `usage_db.get_monthly_limit(user.id)` with `config.quotas.monthly_quota(Tier(user.plan))`

**Step 2.4: Modify dependencies.py**
- Pass `quota_config=config.quotas` to ChatService constructor

**Step 2.5: Update chats router (if needed)**
- If `create_chat`/`send_message` signatures changed to accept `User` instead of `user_id`, update route call sites

### Phase 3: Migration

**Step 3.1: Write the SQL migration**
- CREATE TYPE statements
- DROP FK constraints
- ALTER COLUMN ... TYPE ... USING
- DROP TABLE core.plans

### Phase 4: Test Updates

**Step 4.1: Update E2E conftest**
- Remove plans table seeding
- Add CREATE TYPE IF NOT EXISTS before create_all()

**Step 4.2: Update unit conftest**
- Remove `get_monthly_limit` from mock_usage_db
- Add `quota_config` to service fixture
- Update `try_increment` mock assertions to expect 3 args

**Step 4.3: Update unit test assertions**
- `test_usage.py`: update mock calls for new `try_increment` signature
- `test_users.py`: if any tests check `monthly_limit`, update to verify config-based lookup
- `test_subscriptions.py`: type annotation changes may affect mock assertions

### Why This Order

1. **Config first** -- everything downstream depends on QuotaConfig existing
2. **Models second** -- SAEnum types must be defined before service code references the new method signatures
3. **Service/DB together** -- UsageDB signature change and ChatService change are tightly coupled
4. **Migration third** -- the app code works against both TEXT and ENUM columns (StrEnum values are strings), so the migration can run after the code is deployed
5. **Tests last** -- tests verify the final state; updating them alongside or after the code changes ensures they test the right thing

---

## Scalability Considerations

| Concern | Before (v1.5) | After (v1.6) |
|---------|---------------|--------------|
| Quota check per request | 1 UPDATE with JOIN + subquery (2 table reads) | 1 UPDATE, no JOIN (single table) |
| Monthly limit lookup (GET /users/me) | 1 SELECT with JOIN to plans | Python dict lookup (zero DB I/O) |
| Schema validation of enum values | Application-only (Python StrEnum) | Application + database (PG enum type) |
| Quota config changes | Requires SQL INSERT/UPDATE to plans table | YAML config change + restart |
| Adding a new tier | Migration + config + Python enum | Migration (ALTER TYPE ADD VALUE) + config + Python enum |

---

## Sources

- [SQLAlchemy Enum type documentation (type_basics)](https://docs.sqlalchemy.org/en/20/core/type_basics.html) -- schema, create_type, native_enum, values_callable parameters
- [SQLAlchemy discussion #10583: Enum in non-default schema](https://github.com/sqlalchemy/sqlalchemy/discussions/10583) -- inherit_schema vs explicit schema parameter
- [SQLAlchemy discussion #12123: StrEnum vs Enum processing](https://github.com/sqlalchemy/sqlalchemy/discussions/12123) -- values_callable for StrEnum, default behavior
- [PostgreSQL enum types with SQLModel and Alembic](https://shekhargulati.com/2025/01/12/postgresql-enum-types-with-sqlmodel-and-alembic/) -- sa_column pattern for SQLModel
- [PostgreSQL ALTER TYPE documentation](https://www.postgresql.org/docs/current/datatype-enum.html) -- ALTER COLUMN TYPE USING cast syntax
- Codebase inspection: all files in `src/nativespeaker/api/` and `tests/`
