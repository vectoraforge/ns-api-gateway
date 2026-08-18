# Feature Research: v1.6 Schema Hardening

**Domain:** Config-driven quota systems, native PostgreSQL enum types, schema migration patterns for an existing FastAPI + SQLAlchemy async + SQLModel + Pydantic v2 app
**Researched:** 2026-03-23
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Must Have for This Milestone)

Features required for the milestone to be considered complete. Missing any of these leaves the schema in an inconsistent or half-migrated state.

| Feature | Why Expected | Complexity | Dependencies | Notes |
|---------|--------------|------------|--------------|-------|
| Pydantic config model for tier-to-quota mapping | The `core.plans` table is being removed. Quota values must live somewhere typed and validated. A `dict[Tier, int]` in `AppConfig` is the natural replacement. | LOW | Existing `AppConfig` + `Tier` StrEnum | Add `quotas: dict[Tier, int]` to config.yaml and a corresponding Pydantic model. Pydantic validates exhaustiveness at startup. |
| YAML quota definitions with Pydantic validation | Config must be human-readable, environment-overridable, and validated at startup -- not silently wrong at runtime. | LOW | Config model above | `quotas:` block in config.yaml with `free: 150`, `silver: 1500`, etc. Pydantic v2 validates types and constraints. |
| Rewrite `UsageDB.try_increment` to accept quota as parameter | The atomic `UPDATE ... FROM plans` JOIN is the core of quota enforcement. It must work identically after the `plans` table is removed. | MEDIUM | Config model, `ChatService` passes quota value | Replace the `JOIN plans` subquery with a parameter: `AND u.used < :quota`. Caller looks up `config.quotas[user.plan]`. |
| Rewrite `UsageDB.get_monthly_limit` to read from config | `GET /users/me` calls this to display `monthly_limit`. Currently JOINs `plans` table. | LOW | Config model | Replace DB query with `config.quotas[tier]` lookup. This method becomes a pure config read, may move out of UsageDB entirely. |
| Drop FK constraints on `users.plan` and `subscriptions.plan` | These columns reference `core.plans(tier)`. The table is being dropped, so the FKs must go first. | LOW | Must happen in migration before `DROP TABLE plans` | `ALTER TABLE core.users DROP CONSTRAINT ...`, same for subscriptions. |
| Drop `core.plans` table | The table is replaced by config. Keeping it creates confusion about the source of truth. | LOW | FK constraints dropped first | `DROP TABLE core.plans` in migration. |
| `CREATE TYPE` for all 4 enums in `core` schema | Role, Tier, SubscriptionProvider, SubscriptionStatus are currently stored as TEXT. Native PG enums enforce valid values at the database level. | MEDIUM | Must happen before `ALTER COLUMN` | `CREATE TYPE core.role AS ENUM ('human', 'ai')` etc. Types live in the `core` schema to match table namespace. |
| `ALTER COLUMN ... TYPE ... USING` for all enum columns | Convert existing TEXT columns to the new enum types. Requires USING clause for the cast. | MEDIUM | CREATE TYPE must exist first | `ALTER TABLE core.messages ALTER COLUMN role TYPE core.role USING role::text::core.role`. Also need to drop and re-add DEFAULT on columns that have one. |
| SQLModel column definitions use `sa_type=ENUM(...)` | Python model definitions must match the new database types so SQLAlchemy generates correct SQL. | MEDIUM | PostgreSQL dialect ENUM with `schema=`, `create_type=False` | Use `sa_type=ENUM(Role, name="role", schema="core", create_type=False, values_callable=...)`. The `create_type=False` is critical -- migration handles type creation, not SQLAlchemy metadata. |
| Single pogo-migrate migration file | All schema changes in one migration: drop FKs, create enum types, alter columns, drop plans table. Atomic and reversible. | MEDIUM | All of the above | pogo-migrate uses `-- migrate: apply` / `-- migrate: rollback` format. Rollback must recreate the plans table and convert columns back to TEXT. |
| Update E2E test fixture (remove plans table seeding) | `tests/e2e/conftest.py` currently seeds the `plans` table with `INSERT INTO plans`. This will fail after migration. | LOW | Plans table dropped | Remove the `INSERT INTO plans` from `ensure_tables`. Config now provides quotas. |
| Update unit tests for new `try_increment` signature | Unit tests mock `UsageDB.try_increment`. If the signature changes (quota parameter), mocks must match. | LOW | `try_increment` signature change | Update `AsyncMock` calls in `test_usage.py`. |

### Differentiators (Valuable But Not Required for This Milestone)

Features that go beyond the stated milestone goals but add real value.

| Feature | Value Proposition | Complexity | Dependencies | Notes |
|---------|-------------------|------------|--------------|-------|
| Startup validation: config quotas cover all Tier values | Catch missing tier definitions at startup, not at the first request that hits a missing tier. Prevents silent 500s in production. | LOW | Config model with `Tier` enum | Pydantic `model_validator(mode="after")` that checks `set(quotas.keys()) == set(Tier)`. Fails fast at config load. |
| Type-safe `plan` field on User/Subscription models | Change `plan: str` to `plan: Tier` on User and Subscription models. Python-side type safety catches misassignment at development time. | LOW | `sa_type` changes | Currently `plan: str = Field(...)`. Change to `plan: Tier = Field(sa_type=...)`. SQLModel handles serialization. |
| Typed `role` field on Message model | Change from `role: Role = Field()` (currently works by accident because StrEnum inherits str) to explicit `sa_type` declaration. | LOW | `sa_type` changes | Makes the contract explicit rather than relying on implicit StrEnum-to-TEXT coercion. |
| Type-safe `old_tier`/`new_tier` on SubscriptionEvent | These are currently `str | None`. Changing to `Tier | None` adds type safety for subscription event audit trail. | LOW | Tier enum type exists in PG | Optional because these are audit fields, not frequently queried. |
| Migration idempotency guards | `CREATE TYPE IF NOT EXISTS` is not valid PostgreSQL. Use `DO $$ ... $$ LANGUAGE plpgsql` blocks to check existence before creating types. | LOW | None | Prevents migration failures on partial reruns. Important for operational safety. |

### Anti-Features (Explicitly Do Not Build)

Features that seem related but create problems or are out of scope.

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| Alembic autogeneration for enum changes | Seems like the "proper" migration approach | This project uses pogo-migrate (raw SQL), not Alembic. Adding Alembic alongside pogo would create two competing migration systems. The `alembic-postgresql-enum` package is Alembic-specific. | Hand-write the SQL migration in pogo-migrate format. Raw SQL gives full control over `CREATE TYPE`, `ALTER COLUMN ... USING`, and rollback. |
| `SQLModel.metadata.create_all()` for enum types | Feels like it should "just work" | SQLAlchemy's `create_all()` with `create_type=True` creates enum types in the `public` schema by default, not `core`. With `inherit_schema=True`, behavior depends on table creation order. Migrations are the reliable path. | Set `create_type=False` on all ENUM sa_types. Migration owns type creation. `create_all()` in tests creates tables only. |
| `native_enum=False` (VARCHAR + CHECK constraint) | Avoids the complexity of `CREATE TYPE` and `ALTER COLUMN` migration | Loses database-level enforcement. CHECK constraints on VARCHAR don't participate in PG's type system, cannot be shared across columns, and require separate constraint management. The whole point of this milestone is to use real PG types. | Use native PG enum types via `CREATE TYPE`. Accept the migration complexity -- it's a one-time cost. |
| Dynamic tier definitions (add tiers without migration) | Future-proofs against adding a "diamond" tier | Overengineering. Adding a new tier requires code changes (StrEnum member, config entry, rate limit rules, Apple product mapping). A PG enum `ALTER TYPE ... ADD VALUE` migration is trivial compared to all the other changes needed. | Static enum types in PG. New tiers require a migration to add the value -- this is correct and intentional. |
| Config-driven enum values (load enum members from YAML) | "Single source of truth" for enum values | Python StrEnum members must be compile-time constants for type checkers, IDE support, and `match` statements. Loading from YAML breaks all of these. The YAML-to-enum sync would be fragile and unverifiable. | Python StrEnum is the source of truth for valid values. YAML config references those values (e.g., in `product_id_to_tier`). |
| Separate migration per change (one for enums, one for plans removal) | Seems safer to do incremental migrations | Creates an intermediate state where some columns are enum-typed and some are TEXT, or the plans table exists but FKs are gone. This invites confusion and partial-rollback scenarios. | Single migration that does everything atomically. If it fails, rollback restores the original schema completely. |
| `ChoiceType` from sqlalchemy-utils | A "simpler" approach to enum columns | Adds a new dependency (`sqlalchemy-utils`) for a feature that native PG enums handle better. ChoiceType stores VARCHAR internally, defeating the purpose. Also has known issues with SQLModel. | Native PostgreSQL ENUM types. No extra dependencies. |

## Feature Dependencies

```
Config Model (Pydantic)
    |
    +-> quotas: dict[Tier, int] in AppConfig
    |     |
    |     +-> Startup validation (all Tier values covered)
    |     |
    |     +-> UsageDB.try_increment(user_id, month, quota)
    |     |     |
    |     |     +-> ChatService passes config.quotas[user.plan]
    |     |
    |     +-> UsageDB.get_monthly_limit() replaced by config lookup
    |           |
    |           +-> GET /users/me reads quota from config
    |
Migration (single pogo-migrate file)
    |
    +-> Phase 1: Drop FK constraints (users.plan, subscriptions.plan -> plans.tier)
    |
    +-> Phase 2: CREATE TYPE in core schema (role, tier, subscription_provider, subscription_status)
    |
    +-> Phase 3: ALTER COLUMN ... TYPE ... USING for all enum columns
    |     |
    |     +-> messages.role: TEXT -> core.role
    |     +-> users.plan: TEXT -> core.tier (also drop/re-add DEFAULT)
    |     +-> subscriptions.plan: TEXT -> core.tier
    |     +-> subscriptions.provider: TEXT -> core.subscription_provider
    |     +-> subscriptions.status: TEXT -> core.subscription_status
    |
    +-> Phase 4: DROP TABLE core.plans
    |
SQLModel Column Definitions
    |
    +-> sa_type=ENUM(EnumClass, name=..., schema="core", create_type=False, values_callable=...)
    |     |
    |     +-> User.plan: Tier with sa_type
    |     +-> Message.role: Role with sa_type
    |     +-> Subscription.plan: Tier with sa_type
    |     +-> Subscription.provider: SubscriptionProvider with sa_type
    |     +-> Subscription.status: SubscriptionStatus with sa_type
    |
Test Updates
    |
    +-> Remove plans table seeding from E2E conftest
    +-> Update unit test mocks for new try_increment signature
    +-> Verify StrEnum values round-trip correctly with native PG enums
```

### Dependency Notes

- **Config model must be done before UsageDB rewrite:** The rewrite needs a quota value to pass to the SQL query. Without config, there's nowhere to get it.
- **FK drop must precede plans table drop:** PostgreSQL will refuse to drop a table that is referenced by foreign keys.
- **CREATE TYPE must precede ALTER COLUMN:** Cannot cast to a type that does not exist.
- **SQLModel changes are independent of migration:** They can be done before or after the migration runs, but must match the final schema state. In practice, do them alongside the migration so the app code and schema stay in sync.
- **Test updates depend on all the above:** Tests validate the final state, so they come last.

## MVP Definition

### Must Ship (v1.6)

- [x] `quotas` config model with Pydantic validation
- [x] YAML quota definitions (`free: 150`, `silver: 1500`, `gold: 3000`, `platinum: 30000`)
- [x] Startup validation that all Tier values have quota entries
- [x] `UsageDB.try_increment` accepts quota parameter instead of JOINing plans
- [x] `UsageDB.get_monthly_limit` replaced by config lookup
- [x] `ChatService` and `GET /users/me` pass quota from config
- [x] Single pogo-migrate migration: drop FKs, create types, alter columns, drop plans
- [x] SQLModel `sa_type=ENUM(...)` with `create_type=False` and `schema="core"`
- [x] `values_callable=lambda x: [e.value for e in x]` on all ENUM sa_types
- [x] Remove Plan model class
- [x] E2E test fixture updated (no plans table seeding)
- [x] Unit test mocks updated

### Defer to Later

- [ ] `old_tier`/`new_tier` on SubscriptionEvent typed as `Tier | None` -- low value, audit-only fields
- [ ] Migration idempotency guards (`DO $$ ... $$` blocks) -- nice-to-have for operations, not strictly needed for a one-shot migration

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Config-driven quotas (model + YAML + validation) | HIGH (system correctness) | LOW | P1 |
| UsageDB rewrite (try_increment + get_monthly_limit) | HIGH (quota enforcement) | MEDIUM | P1 |
| Migration: CREATE TYPE for all enums | HIGH (data integrity) | MEDIUM | P1 |
| Migration: ALTER COLUMN TEXT -> enum | HIGH (data integrity) | MEDIUM | P1 |
| Migration: drop FKs + drop plans table | HIGH (schema cleanup) | LOW | P1 |
| SQLModel sa_type declarations | HIGH (ORM correctness) | MEDIUM | P1 |
| Remove Plan model class | MEDIUM (dead code) | LOW | P1 |
| Type-safe plan field (str -> Tier) | MEDIUM (dev safety) | LOW | P2 |
| Test updates | HIGH (CI must pass) | LOW | P1 |
| Startup quota exhaustiveness check | MEDIUM (fail-fast) | LOW | P2 |

## Key Technical Decisions

### 1. `sa_type` vs `sa_column` for Enum Fields

**Decision: Use `sa_type`.**

SQLModel offers two approaches:
- `Field(sa_column=Column(ENUM(...)))` -- full SQLAlchemy Column control
- `Field(sa_type=ENUM(...))` -- type-only override, keeps SQLModel Field features (default, foreign_key, index)

Use `sa_type` because these fields also carry other SQLModel metadata (defaults, indexes). The `sa_column` approach replaces the entire column definition, losing SQLModel-managed attributes.

```python
# Correct pattern for this codebase
role: Role = Field(sa_type=ENUM(Role, name="role", schema="core",
                                create_type=False,
                                values_callable=lambda x: [e.value for e in x]))
```

### 2. `values_callable` Is Required for StrEnum

**Decision: Always pass `values_callable=lambda x: [e.value for e in x]`.**

SQLAlchemy's default Enum behavior persists enum **names** (e.g., `"human"` from `Role.human`). For StrEnum where name == value, this works by coincidence. But for enums where name and value could diverge (e.g., `grace_period = "grace_period"`), and for clarity, always use `values_callable` to explicitly persist **values**. This matches the existing TEXT data in the database.

### 3. `create_type=False` Is Mandatory

**Decision: Never let SQLAlchemy create enum types. Migration owns type creation.**

With `create_type=True` (default), SQLAlchemy attempts to CREATE TYPE during `metadata.create_all()`. This causes:
- Types created in `public` schema instead of `core` (unless `inherit_schema=True`, which has edge cases)
- "DuplicateObject" errors if types already exist from migration
- Non-deterministic behavior in tests vs production

Setting `create_type=False` means: migration creates types explicitly in the `core` schema, SQLAlchemy just references them.

### 4. Schema Namespace for Enum Types

**Decision: Create enum types in `core` schema to match table namespace.**

All tables are in `core` schema (`__table_args__ = {"schema": "core"}`). Enum types should live in the same schema for consistency and to avoid cross-schema references.

```sql
CREATE TYPE core.role AS ENUM ('human', 'ai');
CREATE TYPE core.tier AS ENUM ('free', 'silver', 'gold', 'platinum');
```

On the SQLModel side, use `schema="core"` on the ENUM type, not `inherit_schema=True`, because `inherit_schema` depends on table processing order which is fragile.

### 5. Quota Parameter Injection Pattern

**Decision: Caller passes quota value, not config object.**

The `UsageDB.try_increment` method should accept `quota: int`, not `config: AppConfig`. Database classes should not know about application config. The caller (`ChatService`) reads `config.quotas[user.plan]` and passes the integer.

```python
# ChatService
quota = self.config.quotas[user.plan]
if not await self.usage_db.try_increment(user_id, month, quota):
    raise QuotaExceededError("Monthly quota exceeded")
```

This preserves the clean boundary: ChatService owns business logic, UsageDB owns SQL.

## Sources

### SQLAlchemy Enum Type Documentation
- [SQLAlchemy Type Hierarchy - Enum](https://docs.sqlalchemy.org/en/20/core/type_basics.html) -- HIGH confidence, authoritative
- [PostgreSQL Enum in custom schemas (Discussion #10583)](https://github.com/sqlalchemy/sqlalchemy/discussions/10583) -- HIGH confidence, maintainer response recommends `inherit_schema` or explicit `schema=`
- [StrEnum vs Enum processing (Discussion #12123)](https://github.com/sqlalchemy/sqlalchemy/discussions/12123) -- HIGH confidence, confirms `values_callable` is the fix for StrEnum

### SQLModel Enum Handling
- [PostgreSQL Enum Types with SQLModel and Alembic](https://shekhargulati.com/2025/01/12/postgresql-enum-types-with-sqlmodel-and-alembic/) -- MEDIUM confidence, demonstrates `sa_column=Column(Enum(...))` pattern
- [SQLModel Discussion #717: (str, Enum) fields breaking change](https://github.com/fastapi/sqlmodel/discussions/717) -- HIGH confidence, documents the behavior change in SQLModel 0.0.9+
- [SQLModel Issue #31: Postgres Enum columns](https://github.com/fastapi/sqlmodel/issues/31) -- HIGH confidence, shows `sa_column` with `postgresql.ENUM`

### PostgreSQL Migration Patterns
- [PostgreSQL ALTER TYPE Documentation](https://www.postgresql.org/docs/current/sql-altertype.html) -- HIGH confidence, authoritative
- [PostgreSQL Enumerated Types](https://www.postgresql.org/docs/current/datatype-enum.html) -- HIGH confidence, authoritative
- [Altering columns from TEXT to enum type](https://www.munderwood.ca/index.php/2015/05/28/altering-postgresql-columns-from-one-enum-to-another/) -- MEDIUM confidence, demonstrates USING clause pattern
- [Managing Enums in Postgres (Supabase)](https://supabase.com/docs/guides/database/postgres/enums) -- MEDIUM confidence

### Migration Tooling
- [pogo-migrate on PyPI](https://pypi.org/project/pogo-migrate/) -- HIGH confidence, uses `-- migrate: apply` / `-- migrate: rollback` format matching existing migration

---
*Feature research for: v1.6 Schema Hardening*
*Researched: 2026-03-23*
