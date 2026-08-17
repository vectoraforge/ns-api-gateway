# Stack Research

**Domain:** Schema hardening -- native PG enums + config-driven quotas for existing FastAPI/SQLModel app
**Researched:** 2026-03-23
**Confidence:** HIGH

## Scope

This research covers ONLY what changes/additions are needed for v1.6 schema hardening.
The existing stack (Python 3.12, FastAPI, SQLAlchemy async, SQLModel, Pydantic v2, pogo-migrate, etc.) is validated and not re-researched.

## Recommended Stack Changes

### No New Dependencies Required

The v1.6 milestone requires zero new pip packages. Everything needed is already available in the existing dependency tree:

| Capability | Provided By | Already Installed | Version |
|------------|-------------|-------------------|---------|
| Native PG ENUM types | `sqlalchemy.dialects.postgresql.ENUM` | Yes (via sqlalchemy) | 2.0.46 |
| ENUM in SQLModel columns | `sqlmodel.Field(sa_type=...)` | Yes (via sqlmodel) | 0.0.37 |
| Config-driven quotas | `pydantic.BaseModel` | Yes (via pydantic) | 2.12.5 |
| YAML quota config | `pyyaml` | Yes | >=6.0 |
| Raw SQL migrations | `pogo-migrate` | Yes (dev dep) | >=0.4.2 |

## Core Technologies

### 1. `sqlalchemy.dialects.postgresql.ENUM` -- Native PG Enum Column Type

**What:** Use `postgresql.ENUM` as the column type via SQLModel's `sa_type` parameter to map Python StrEnums to native PostgreSQL `CREATE TYPE ... AS ENUM` types.

**Why `postgresql.ENUM` not `sqlalchemy.Enum` (generic):** The generic `sqlalchemy.Enum` auto-creates the PG type when the table is created via `metadata.create_all()`. Since this project uses pogo-migrate (raw SQL migrations), not Alembic autogenerate, we need `create_type=False` to prevent SQLAlchemy from issuing `CREATE TYPE` at runtime. The `postgresql.ENUM` dialect type supports `create_type=False` and an explicit `schema` parameter. The generic `Enum` also supports `create_type=False` (via `native_enum` + `create_constraint` controls), but `postgresql.ENUM` is the idiomatic choice when targeting PostgreSQL exclusively.

**Why `sa_type` not `sa_column`:** The project already uses `sa_type` (see `PydanticJSONB` on `Message.content`). Using `sa_type` preserves other `Field()` parameters like `default` and `index`. Using `sa_column=Column(...)` would override all Field parameters, requiring them to be re-specified in the Column call.

**Verified pattern** (tested against installed SQLModel 0.0.37 + SQLAlchemy 2.0.46):

```python
from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlmodel import Field, SQLModel

class Tier(StrEnum):
    free = "free"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"

# Define PG type object once, reference in all columns that use it
TierType = PG_ENUM(Tier, name="tier", schema="core", create_type=False)

class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    plan: Tier = Field(default=Tier.free, sa_type=TierType)
```

**Verified behaviors (local test, HIGH confidence):**
- `create_type=False` prevents runtime `CREATE TYPE` -- the migration handles DDL
- `schema="core"` tells SQLAlchemy the PG type lives in the `core` schema (required because tables are in `core`, not `public`)
- `sa_type` preserves `Field(default=...)` -- column gets `ScalarElementColumnDefault`
- StrEnum where name == value (e.g., `free = "free"`) means `values_callable` is unnecessary
- `PG_ENUM.enums` correctly resolves to `['free', 'silver', 'gold', 'platinum']`

**All four project enums and their PG type definitions:**

```python
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from nativespeaker.api.models import Role, Tier, SubscriptionProvider, SubscriptionStatus

RoleType = PG_ENUM(Role, name="role", schema="core", create_type=False)
TierType = PG_ENUM(Tier, name="tier", schema="core", create_type=False)
SubscriptionProviderType = PG_ENUM(
    SubscriptionProvider, name="subscription_provider", schema="core", create_type=False
)
SubscriptionStatusType = PG_ENUM(
    SubscriptionStatus, name="subscription_status", schema="core", create_type=False
)
```

### 2. Pydantic `dict[Tier, int]` -- Config-Driven Quotas

**What:** Replace the `core.plans` database table with a `quotas` section in `config.yaml`, validated by a Pydantic `BaseModel`.

**Why Pydantic, not a raw dict:** The existing `AppConfig` already uses nested `BaseModel` for every config section (`DatabaseConfig`, `ResilienceConfig`, `JWTConfig`, `AppleConfig`, `ModelConfig`). A `QuotasConfig` follows the established pattern and gets free validation -- unknown tiers fail at startup, not at runtime.

**Pattern:**

```python
# In config.py
from nativespeaker.api.models import Tier

class QuotasConfig(BaseModel):
    tier_quotas: dict[Tier, int] = Field(
        description="Monthly request quota per tier"
    )

    def monthly_quota(self, tier: Tier) -> int:
        return self.tier_quotas[tier]
```

```yaml
# In config.yaml
quotas:
  tier_quotas:
    free: 150
    silver: 1500
    gold: 3000
    platinum: 30000
```

**Why `dict[Tier, int]`:** Pydantic v2 validates enum keys natively. A tier typo in YAML (`fre: 150`) raises `ValidationError` at startup. No custom validators needed. Verified against Pydantic 2.12.5.

**Why a method, not just dict access:** `config.quotas.monthly_quota(tier)` is self-documenting and provides a single point to add fallback logic later (e.g., returning a default for unknown tiers during enum expansion).

### 3. pogo-migrate Raw SQL -- Migration DDL

**What:** A single new pogo-migrate SQL migration that: creates the PG enum types, alters columns from TEXT to enum, drops FK constraints, drops the plans table.

**Why one migration:** All changes are logically coupled. The `core.plans` table cannot be dropped until FKs are removed, and columns should be enum-typed in the same transaction that removes FKs. pogo-migrate executes each migration file as a single transaction by default.

**Migration pattern:**

```sql
-- migrate: apply

-- 1. Create native enum types in the core schema
CREATE TYPE core.role AS ENUM ('human', 'ai');
CREATE TYPE core.tier AS ENUM ('free', 'silver', 'gold', 'platinum');
CREATE TYPE core.subscription_provider AS ENUM ('apple');
CREATE TYPE core.subscription_status AS ENUM (
    'active', 'grace_period', 'billing_retry', 'expired', 'revoked'
);

-- 2. Drop FK constraints referencing plans table
ALTER TABLE core.users DROP CONSTRAINT IF EXISTS users_plan_fkey;
ALTER TABLE core.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_plan_fkey;

-- 3. Alter columns from TEXT to native enum types (USING cast required)
ALTER TABLE core.messages ALTER COLUMN role TYPE core.role USING role::core.role;
ALTER TABLE core.users ALTER COLUMN plan TYPE core.tier USING plan::core.tier;
ALTER TABLE core.subscriptions ALTER COLUMN plan TYPE core.tier USING plan::core.tier;
ALTER TABLE core.subscriptions ALTER COLUMN provider TYPE core.subscription_provider
    USING provider::core.subscription_provider;
ALTER TABLE core.subscriptions ALTER COLUMN status TYPE core.subscription_status
    USING status::core.subscription_status;

-- 4. Drop the plans lookup table
DROP TABLE core.plans;

-- migrate: rollback
-- (reverse operations to restore previous state)
```

**Key detail -- `USING` clause:** PostgreSQL requires explicit `USING column::new_type` when converting TEXT to ENUM. Without it, `ALTER COLUMN ... TYPE` fails with "column cannot be cast automatically to type."

**Key detail -- partial index compatibility:** The existing partial index `WHERE status NOT IN ('expired', 'revoked')` works with native ENUM types. PostgreSQL supports `IN` / `NOT IN` comparison with enum values using string literals.

**Key detail -- FK constraint names:** The actual constraint names in the database may differ from the defaults shown above. The migration should verify exact names via `\d+ core.users` before writing, or use `DROP CONSTRAINT IF EXISTS` with the correct names.

## Integration Points -- What Changes

| File | Change | Reason |
|------|--------|--------|
| `models.py` | Add `PG_ENUM` type objects; add `sa_type=` on enum columns; remove `Plan` model; remove `foreign_key="core.plans.tier"` from User.plan and Subscription.plan | Native enum columns replace TEXT+FK |
| `config.py` | Add `QuotasConfig` with `tier_quotas: dict[Tier, int]`; add `quotas: QuotasConfig` to `AppConfig` | Config replaces plans table |
| `config.yaml` | Add `quotas.tier_quotas` section with free/silver/gold/platinum values | Quota values that were in `core.plans` |
| `database/usage.py` | Rewrite `try_increment` to accept `monthly_quota: int` parameter instead of JOINing plans; rewrite `get_monthly_limit` to accept `user_tier` and `config` instead of querying plans | No more plans table to JOIN |
| `routers/users.py` | Read monthly limit from config using user's tier | `get_monthly_limit` no longer queries DB |
| `dependencies.py` | Pass quota config into services that need it | DI for config-driven quota |
| `services/chats.py` | Pass quota value to `try_increment` | Quota comes from config, not DB |
| `database/__init__.py` | No change needed (Plan is not exported there) | - |
| `schema.py` | Optionally type `plan` field as `Tier` instead of `str` in `UserProfileResponse` | Stronger API typing |
| Migration | New `migrations/YYYYMMDD_01_schema-hardening.sql` | DDL changes |

## What Does NOT Change

| Component | Why Unchanged |
|-----------|---------------|
| `StrEnum` definitions (Role, Tier, SubscriptionProvider, SubscriptionStatus) | Already correct; name == value pattern is PG-ENUM compatible |
| Subscription partial index logic | `NOT IN ('expired', 'revoked')` works identically with native enums |
| Apple webhook flow | Already uses `Tier` enum in Python; DB serialization changes are transparent |
| Firebase claim sync | Operates on string values; `str(Tier.free)` returns `"free"` with StrEnum |
| JWT auth flow | Unaffected by schema changes |
| E2E test structure | Same endpoints, same behavior |
| `PydanticJSONB` TypeDecorator | Unrelated to enum changes |

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| `postgresql.ENUM` with `create_type=False` | `sqlalchemy.Enum` (generic) with `native_enum=True` | Generic Enum can auto-create PG types at MetaData.create_all() time; conflicts with pogo-migrate owning all DDL |
| `sa_type=PG_ENUM(...)` on Field | `sa_column=Column(PG_ENUM(...))` | `sa_column` overrides all Field params (default, index, nullable, etc.); `sa_type` composes with them. Project already uses `sa_type` pattern. |
| Explicit `schema="core"` on PG_ENUM | `inherit_schema=True` on generic Enum | `inherit_schema` inherits from MetaData schema, but SQLModel tables use `__table_args__` not shared MetaData; explicit schema is clearer and verified working |
| `dict[Tier, int]` in Pydantic config | `dict[str, int]` with manual validation | Pydantic v2 validates enum keys natively; typos caught at startup for free |
| Single migration file | Separate migrations per change type | All changes are logically atomic; splitting adds ordering complexity with no benefit |
| Quota as Pydantic config | Quota as environment variables | Quotas are structured data (4 tier-value pairs); YAML is cleaner than 4 env vars and follows existing config pattern |
| Quota as Pydantic config | Keep plans table, just remove FK | Defeats the purpose of schema hardening; table with 4 static rows is pure overhead vs config |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `alembic` | Project uses pogo-migrate for raw SQL migrations; adding a second migration tool creates confusion | Write `CREATE TYPE` / `ALTER COLUMN` in pogo-migrate SQL file |
| `alembic-postgresql-enum` | Only useful with Alembic autogenerate; irrelevant with raw SQL migrations | Handle enum DDL in migration SQL directly |
| `sqlalchemy-utils` ChoiceType | Unnecessary abstraction over native PG ENUM; adds a dependency for something built into SQLAlchemy | Use `sqlalchemy.dialects.postgresql.ENUM` directly |
| `values_callable` parameter | All project StrEnums use `name = "value"` where both are identical; no name/value mismatch to resolve | Omit; add only if enum naming convention changes |
| `Mapped[Tier]` / `mapped_column()` | Project uses SQLModel `Field()`, not raw SQLAlchemy ORM declarative | Keep using `Field(sa_type=...)` |
| `enum.auto()` | Current explicit `name = "value"` pattern ensures name == value; `auto()` generates names from member names which is identical for StrEnum, but explicit is clearer | Keep explicit string values |
| New pip packages | Zero additional dependencies needed | Everything is already in sqlalchemy + pydantic + pyyaml |

## Critical Implementation Details

### StrEnum Name-Value Alignment

All four project enums follow the `name = "value"` pattern where both are identical:

```python
class Tier(StrEnum):
    free = "free"       # name="free", value="free"
    silver = "silver"   # name="silver", value="silver"
```

SQLAlchemy stores enum **names** by default (not values). Since names match values in all project enums, the DB stores `"free"` regardless of which is used. This means:
1. No `values_callable` parameter needed on PG_ENUM definitions
2. Existing TEXT data (`"free"`, `"active"`, etc.) casts cleanly to the new ENUM types via `USING column::core.tier`
3. Raw SQL queries using string literals (e.g., `WHERE status NOT IN ('expired', 'revoked')`) continue to work unchanged
4. The `text()` queries in `UsageDB` that reference plan/status values by string continue to work

**If this convention is ever broken** (e.g., `FREE = "free"` where name != value), add `values_callable=lambda x: [e.value for e in x]` to all `PG_ENUM` definitions to persist values instead of names.

### PG_ENUM Object Reuse

Define each `PG_ENUM` object once at module level and reference it in all columns that use that type. Do NOT create separate `PG_ENUM` instances per column -- PostgreSQL has one `CREATE TYPE` per name, and SQLAlchemy expects one Python type object to correspond to it.

```python
# CORRECT: one object, multiple columns reference it
TierType = PG_ENUM(Tier, name="tier", schema="core", create_type=False)

class User(SQLModel, table=True):
    plan: Tier = Field(default=Tier.free, sa_type=TierType)

class Subscription(SQLModel, table=True):
    plan: Tier = Field(sa_type=TierType)

# WRONG: separate instances for same PG type
class User(SQLModel, table=True):
    plan: Tier = Field(sa_type=PG_ENUM(Tier, name="tier", schema="core", create_type=False))
class Subscription(SQLModel, table=True):
    plan: Tier = Field(sa_type=PG_ENUM(Tier, name="tier", schema="core", create_type=False))
```

### UsageDB Query Rewrite

The `try_increment` query currently JOINs the plans table:

```sql
UPDATE usage_monthly u SET used = u.used + 1
FROM plans p
WHERE u.user_id = :user_id AND u.month = :month
  AND p.tier = (SELECT plan FROM users WHERE id = :user_id)
  AND u.used < p.monthly_quota
RETURNING u.used
```

After removing the plans table, the quota comes from config as a parameter:

```sql
UPDATE core.usage_monthly u SET used = u.used + 1
WHERE u.user_id = :user_id AND u.month = :month
  AND u.used < :monthly_quota
RETURNING u.used
```

This is simpler, faster (no JOIN, no subquery), and the quota lookup moves to Python where the config is already loaded.

## Version Compatibility

| Package | Version | Compatible With | Notes |
|---------|---------|-----------------|-------|
| SQLAlchemy | 2.0.46 | `postgresql.ENUM` with `create_type`, `schema` | Full support; tested locally |
| SQLModel | 0.0.37 | `Field(sa_type=PG_ENUM(...))` | Tested: `sa_type` works with `default`, preserves column metadata |
| Pydantic | 2.12.5 | `dict[StrEnum, int]` as model field | Enum key validation works natively |
| asyncpg | >=0.30 | Native PG ENUM types | asyncpg handles enum encoding/decoding transparently |
| pogo-migrate | >=0.4.2 | Raw SQL `CREATE TYPE` / `ALTER COLUMN` | SQL-passthrough migration tool; no enum-specific concerns |
| PostgreSQL | 14+ | `CREATE TYPE ... AS ENUM`, `ALTER COLUMN ... USING` | All required DDL supported; partial indexes with enum `IN` work |

## Sources

- [SQLAlchemy 2.0 PostgreSQL Dialect Docs](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html) -- `postgresql.ENUM` API, `create_type`, `schema` params (HIGH confidence)
- [SQLAlchemy 2.0 Type Hierarchy Docs](https://docs.sqlalchemy.org/en/20/core/type_basics.html) -- generic `Enum` type, `values_callable`, `native_enum`, `inherit_schema` (HIGH confidence)
- [SQLAlchemy Discussion #12123](https://github.com/sqlalchemy/sqlalchemy/discussions/12123) -- StrEnum processing confirmed working by maintainers (HIGH confidence)
- [SQLAlchemy Discussion #10583](https://github.com/sqlalchemy/sqlalchemy/discussions/10583) -- `inherit_schema=True` for schema-qualified enums; explicit `schema=` alternative (HIGH confidence)
- [SQLAlchemy Discussion #11527](https://github.com/sqlalchemy/sqlalchemy/discussions/11527) -- `values_callable` for name vs value persistence; default stores names (HIGH confidence)
- [SQLModel Issue #96](https://github.com/fastapi/sqlmodel/issues/96) -- `sa_column=Column(Enum(...))` pattern for PostgreSQL enums (MEDIUM confidence)
- [PostgreSQL Enum Types with SQLModel](https://shekhargulati.com/2025/01/12/postgresql-enum-types-with-sqlmodel-and-alembic/) -- end-to-end SQLModel + PG enum walkthrough (MEDIUM confidence)
- [PostgreSQL 18 ENUM Documentation](https://www.postgresql.org/docs/current/datatype-enum.html) -- native enum type DDL and behavior (HIGH confidence)
- Local verification: `sa_type=PG_ENUM(...)` tested against installed SQLModel 0.0.37 + SQLAlchemy 2.0.46 -- `create_type=False`, `schema="core"`, `default=Tier.free` all work correctly (HIGH confidence)

---
*Stack research for: v1.6 Schema Hardening -- native PG enums + config-driven quotas*
*Researched: 2026-03-23*
