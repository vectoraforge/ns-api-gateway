# Domain Pitfalls: Schema Hardening -- Native PG Enums + Lookup Table Removal (v1.6)

**Domain:** Converting TEXT columns to native PostgreSQL enum types, removing a lookup table with FK constraints, and rewriting raw SQL queries in an existing FastAPI + SQLAlchemy async + SQLModel + Pydantic v2 application
**Researched:** 2026-03-23
**Confidence:** HIGH (codebase analysis + official PostgreSQL/SQLAlchemy docs + community reports)

---

## Critical Pitfalls

Mistakes that cause migration failures, data loss, or production downtime.

---

### Pitfall 1: Column DEFAULT must be dropped before ALTER COLUMN TYPE TEXT to ENUM

**What goes wrong:** The migration runs `ALTER TABLE core.users ALTER COLUMN plan TYPE core.tier USING plan::core.tier` and PostgreSQL rejects it with `default for column "plan" cannot be cast automatically to type core.tier`. The `users.plan` column has `DEFAULT 'free'` -- a text literal. PostgreSQL cannot automatically cast a text default to an enum type, even if the string value is a valid enum member.

**Why it happens:** PostgreSQL treats the column default as a separate expression from the column data. `ALTER COLUMN TYPE` recasts the existing *data* via the `USING` clause but does NOT recast the *default value*. The default `'free'` is type `text`, not type `core.tier`, so the ALTER fails.

**Consequences:** Migration aborts. If run in production without testing, the migration fails mid-transaction (safe if transactional) but blocks the deployment.

**This codebase's specific exposure:**
- `core.users.plan` has `DEFAULT 'free'` (models.py line 111: `plan: str = Field(default="free", ...)`)
- `core.subscriptions.plan` has `DEFAULT 'free'` (migration SQL line 54: `DEFAULT 'free'`)

**Prevention:** The migration must follow this exact sequence for each affected column:
```sql
-- 1. Drop the default
ALTER TABLE core.users ALTER COLUMN plan DROP DEFAULT;

-- 2. Change the type with USING cast
ALTER TABLE core.users ALTER COLUMN plan TYPE core.tier USING plan::core.tier;

-- 3. Re-add the default as the enum value
ALTER TABLE core.users ALTER COLUMN plan SET DEFAULT 'free'::core.tier;
```

**Detection:** Test the migration against a database with existing data before deploying.

**Confidence:** HIGH -- PostgreSQL 18 documentation on [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) explicitly states that the default is not re-cast.

---

### Pitfall 2: CREATE TYPE must precede all ALTER TABLE TYPE changes -- ordering within a single migration

**What goes wrong:** The migration file creates enum types and alters columns, but the `CREATE TYPE` for a given enum appears *after* the `ALTER TABLE ... TYPE` that references it. PostgreSQL executes SQL statements sequentially within a migration, and the type must exist before it can be used.

**Why it happens:** When writing a migration that does many things (create 4 enum types, drop FKs, alter 5+ columns, drop a table), it is easy to get the ordering wrong, especially with copy-paste.

**Consequences:** Migration fails with `type "core.tier" does not exist`.

**This codebase's specific exposure:** Four enum types to create (`role`, `tier`, `subscription_provider`, `subscription_status`), used across 4 tables (`messages`, `users`, `subscriptions`, `subscription_events`). The dependency graph:
```
CREATE TYPE core.role           -> ALTER core.messages.role
CREATE TYPE core.tier           -> ALTER core.users.plan
                                -> ALTER core.subscriptions.plan
                                -> ALTER core.subscription_events.old_tier
                                -> ALTER core.subscription_events.new_tier
CREATE TYPE core.sub_provider   -> ALTER core.subscriptions.provider
CREATE TYPE core.sub_status     -> ALTER core.subscriptions.status
```

**Prevention:** Structure the migration in strict phases:
1. All `CREATE TYPE` statements first
2. All `ALTER TABLE ... DROP DEFAULT` statements
3. All `ALTER TABLE ... DROP CONSTRAINT` (FK removal)
4. All `ALTER TABLE ... ALTER COLUMN TYPE ... USING` statements
5. All `ALTER TABLE ... SET DEFAULT` statements
6. `DROP TABLE` for `core.plans`

**Detection:** Run the migration on a fresh clone of the production database (or the test database) before deploying.

**Confidence:** HIGH -- fundamental PostgreSQL DDL ordering.

---

### Pitfall 3: FK constraints must be dropped BEFORE the referenced table is dropped, AND before column types change

**What goes wrong:** The migration tries to `DROP TABLE core.plans` while `core.users.plan` and `core.subscriptions.plan` still have `REFERENCES core.plans(tier)`. PostgreSQL rejects the drop with `ERROR: cannot drop table core.plans because other objects depend on it`.

Separately: if you try to `ALTER COLUMN plan TYPE core.tier` while the FK constraint to `core.plans(tier)` still exists, PostgreSQL rejects it because the FK references a `text` column on the `plans` table, and you are changing the column to a different type.

**Why it happens:** FK constraints create a dependency between the referencing column and the referenced column. The column types must be compatible, and the referenced table cannot be dropped while references exist.

**Consequences:** Migration fails. Using `DROP TABLE ... CASCADE` as a "fix" silently drops the FK constraints but does not convert the column types -- leaving TEXT columns without constraints.

**This codebase's specific exposure:**
- `core.users.plan` REFERENCES `core.plans(tier)` (migration line 24)
- `core.subscriptions.plan` REFERENCES `core.plans(tier)` (migration line 54)
- FK constraint names are auto-generated; must be looked up or use `ALTER TABLE ... DROP CONSTRAINT` with the constraint name from `information_schema.table_constraints`

**Prevention:** The migration must explicitly name and drop each FK constraint:
```sql
-- Find constraint names or use a deterministic naming convention.
-- For this codebase, the constraints were unnamed in the CREATE TABLE so
-- PostgreSQL generated names like 'users_plan_fkey' and 'subscriptions_plan_fkey'.

ALTER TABLE core.users DROP CONSTRAINT users_plan_fkey;
ALTER TABLE core.subscriptions DROP CONSTRAINT subscriptions_plan_fkey;

-- THEN alter column types
-- THEN drop the plans table
```

**Important:** If constraint names are uncertain, query them first:
```sql
SELECT constraint_name FROM information_schema.table_constraints
WHERE table_schema = 'core' AND table_name = 'users' AND constraint_type = 'FOREIGN KEY';
```

Or use the migration rollback to confirm names in a test environment.

**Detection:** The migration will fail immediately if this ordering is wrong. Always test on a copy.

**Confidence:** HIGH -- PostgreSQL [DROP TABLE docs](https://www.postgresql.org/docs/current/sql-droptable.html) and [ALTER TABLE docs](https://www.postgresql.org/docs/current/sql-altertable.html).

---

### Pitfall 4: SQLModel 0.0.37 StrEnum auto-creates native PG enums in `create_all()` but production uses TEXT -- test/production schema drift

**What goes wrong:** The E2E test fixture calls `SQLModel.metadata.create_all` (tests/e2e/conftest.py line 31). With SQLModel >= 0.0.9, `StrEnum` fields like `role: Role = Field()` automatically create native PostgreSQL enum types. But the production migration (initial-release.sql) creates these as `TEXT` columns. After the v1.6 migration converts production columns to native enums, the *names* of the enum types may differ between `create_all()` (which uses Python class names like `role`, `tier`) and the migration (which uses explicit `CREATE TYPE core.tier AS ENUM (...)` with chosen names).

**Why it happens:** `create_all()` derives enum type names from the Python enum class name by default (e.g., `Role` -> type name `role`). The migration uses explicit names that may differ (e.g., `core.tier` vs `tier`). Additionally, `create_all()` may create enum types in the `public` schema (default) while the migration creates them in the `core` schema.

**Consequences:**
- Tests pass but production fails (or vice versa)
- `create_all()` creates enum type `role` in `public` schema; migration creates `core.role` -- two different types
- SQLAlchemy queries reference the wrong enum type, causing `ProgrammingError: type "role" does not exist` in production or `type "core.role" does not exist` in tests

**This codebase's specific exposure:**
- All models use `{"schema": "core"}` in `__table_args__`
- SQLAlchemy's `Enum` type has `inherit_schema` defaulting to `False` (confirmed in [SQLAlchemy issue #10594](https://github.com/sqlalchemy/sqlalchemy/issues/10594))
- Without explicit `sa_column=Column(Enum(..., schema="core"))`, the enum type will be created in the default schema, not `core`

**Prevention:**
1. Use explicit `sa_column` with `Enum` type that specifies `schema="core"` for each enum field:
   ```python
   from sqlalchemy import Column, Enum as SAEnum

   class User(BaseTable, table=True):
       plan: Tier = Field(
           default=Tier.free,
           sa_column=Column(
               SAEnum(Tier, name="tier", schema="core",
                      values_callable=lambda e: [m.value for m in e]),
               default=Tier.free.value,
           )
       )
   ```
2. OR set `inherit_schema=True` on the Enum type (but this was reverted in SQLAlchemy 2.1 plans, so explicit `schema` is safer)
3. Ensure the migration `CREATE TYPE` names match exactly what SQLAlchemy's `Enum` type constructor produces
4. After writing the migration, verify: `create_all()` on a blank DB and the migration on a blank DB should produce identical schema (`pg_dump --schema-only` diff)

**Detection:** Run `\dT+ core.*` in psql after both `create_all()` and migration, compare outputs.

**Confidence:** HIGH -- confirmed via SQLModel 0.0.37 behavior, [SQLModel Discussion #717](https://github.com/fastapi/sqlmodel/discussions/717), and [SQLAlchemy Discussion #10583](https://github.com/sqlalchemy/sqlalchemy/discussions/10583).

---

### Pitfall 5: StrEnum stores VALUES by default but SQLAlchemy Enum may store NAMES -- silent data mismatch

**What goes wrong:** Python `StrEnum` members have both a name and a value. For this codebase they are identical (`free = "free"`), so this pitfall is *latent* -- it will not bite today but will if a member with a different name/value is added later. SQLAlchemy's `Enum` type, when given a Python Enum class, stores member *names* (e.g., `"free"`) by default. But when `values_callable` is used, it stores *values*. If names and values diverge (e.g., `FREE = "free"`), data written with one convention is unreadable with the other.

**Why it happens:** SQLAlchemy `Enum` uses `enum.__members__` keys (names) for persistence unless overridden with `values_callable`. The existing TEXT columns store values like `"free"`, `"human"`, `"active"`. If the new native enum type is configured to persist names instead, existing data after the `USING` cast may not match.

**Consequences:**
- `LookupError: 'free' is not among the defined enum values` when reading existing data
- All existing rows become unreadable until the enum mapping is fixed

**This codebase's specific exposure:**
- All four StrEnums use lowercase matching names/values: `free = "free"`, `human = "human"`, etc.
- Current risk is LOW because names == values
- Risk becomes HIGH if anyone adds `PLATINUM = "platinum"` (uppercase name, lowercase value) -- SQLAlchemy would store `"PLATINUM"` but existing data says `"platinum"`

**Prevention:**
1. Always use `values_callable=lambda e: [m.value for m in e]` when constructing the SQLAlchemy `Enum` type
2. Add a project convention: StrEnum member names MUST equal their values (enforced by a test)
3. Verify with a query after migration: `SELECT DISTINCT plan FROM core.users` should show values that match enum labels

**Detection:** A unit test that asserts `all(m.name == m.value for m in MyEnum)` for each StrEnum catches future drift.

**Confidence:** HIGH -- confirmed via [SQLAlchemy Discussion #12123](https://github.com/sqlalchemy/sqlalchemy/discussions/12123) and [SQLAlchemy docs on Enum types](https://docs.sqlalchemy.org/en/20/core/type_basics.html).

---

### Pitfall 6: Raw SQL queries in UsageDB use UNQUALIFIED table names -- break when search_path changes

**What goes wrong:** The `UsageDB.try_increment` method uses raw SQL with unqualified table names: `FROM plans p`, `FROM users WHERE`, `INSERT INTO usage_monthly`. These rely on PostgreSQL's `search_path` being set to include the `core` schema. If `search_path` is not configured (or changes), these queries fail with `relation "plans" does not exist`.

**Why it happens:** The initial migration creates tables in the `core` schema (`CREATE TABLE core.plans`), but the raw SQL queries in `usage.py` reference tables without the `core.` prefix. This works in tests because `create_all()` (SQLModel.metadata) might create tables in the default schema, and in production it works if `search_path` happens to include `core`. But it is fragile.

**Consequences:**
- After removing `core.plans`, the `try_increment` query fails because `plans` no longer exists
- Even after rewriting to remove the `plans` JOIN, the remaining references to `users` and `usage_monthly` without schema qualification are fragile
- Different PostgreSQL configurations (local dev vs. production) may have different `search_path` settings

**This codebase's specific exposure:**
- `usage.py` line 23: `"FROM plans p "` -- must be removed entirely (plans table going away)
- `usage.py` line 26: `"SELECT plan FROM users WHERE"` -- unqualified
- `usage.py` line 15: `"INSERT INTO usage_monthly"` -- unqualified
- `usage.py` line 35: `"SELECT used FROM usage_monthly"` -- unqualified
- `usage.py` line 44-45: `"SELECT p.monthly_quota FROM plans p JOIN users u"` -- both unqualified

**Prevention:** When rewriting the UsageDB queries:
1. Remove all references to `plans` (replaced by config lookup)
2. Qualify ALL remaining table references with `core.` prefix: `core.usage_monthly`, `core.users`
3. Or (better for this milestone) rewrite `try_increment` to accept `monthly_quota` as a parameter, removing the need to query `users` at all -- the caller already knows the user's tier from the User object
4. Rewrite `get_monthly_limit` to read from config instead of querying the database

**Detection:** Run the E2E tests with `search_path` explicitly set to only `public` -- unqualified references to `core` tables will fail.

**Confidence:** HIGH -- directly verified in the codebase. The raw SQL strings are on lines 14-28 and 34-48 of `usage.py`.

---

## Moderate Pitfalls

Mistakes that cause bugs, test failures, or significant rework but are recoverable.

---

### Pitfall 7: Test fixture seeds `plans` table that no longer exists after migration

**What goes wrong:** The E2E conftest.py (line 32-35) seeds the `plans` table:
```python
await conn.execute(text(
    "INSERT INTO plans (tier, monthly_quota) VALUES "
    "('free', 150), ('silver', 1500), ('gold', 3000), ('platinum', 30000) "
    "ON CONFLICT (tier) DO NOTHING"
))
```
After the v1.6 migration removes `core.plans`, this fixture INSERT fails with `relation "plans" does not exist`, breaking all E2E tests.

**Why it happens:** The test fixture was written for v1.5 when the `plans` table existed and had FK constraints requiring it to be pre-populated.

**Consequences:** All E2E tests fail immediately on the `ensure_tables` fixture.

**Prevention:**
1. Remove the `plans` seed INSERT from the `ensure_tables` fixture
2. Remove the `Plan` model from `models.py` (or keep it only for migration rollback reference)
3. Add the quota config to test configuration (YAML or environment)
4. If using `create_all()` in tests, the `Plan` table will be created if the model still exists -- remove the model or exclude it from metadata

**Detection:** Run E2E tests after the migration. They fail immediately and obviously.

**Confidence:** HIGH -- directly verified in `tests/e2e/conftest.py` line 32-35.

---

### Pitfall 8: `subscription_events.old_tier` and `new_tier` are nullable TEXT -- converting nullable TEXT to nullable ENUM requires special USING clause

**What goes wrong:** The `subscription_events` table has `old_tier TEXT` and `new_tier TEXT` columns that are nullable. A naive `ALTER COLUMN old_tier TYPE core.tier USING old_tier::core.tier` fails on NULL values because PostgreSQL tries to cast NULL to the enum type. While NULL-to-NULL should be safe, the real danger is if *any* unexpected string value exists in these columns (e.g., an empty string `''`, a typo, or a value that is not in the enum).

**Why it happens:** These columns store historical tier values. If a notification was processed before all tier values were defined, or if a bug wrote an unexpected value, the cast will fail on that row.

**Consequences:** Migration fails partway through if any row has a value not in the enum.

**This codebase's specific exposure:**
- `subscription_events.old_tier` and `new_tier` are `TEXT` and nullable (models.py line 147-148)
- Values come from `SubscriptionService._map_lifecycle_event` which returns `Tier` enum values, but `old_tier` is set from `subscription.plan` which is currently a `str` column

**Prevention:**
1. Before the ALTER, validate data: `SELECT DISTINCT old_tier FROM core.subscription_events WHERE old_tier IS NOT NULL`
2. Clean up any unexpected values: `UPDATE core.subscription_events SET old_tier = NULL WHERE old_tier NOT IN ('free', 'silver', 'gold', 'platinum')`
3. Use a defensive USING clause:
   ```sql
   ALTER TABLE core.subscription_events
       ALTER COLUMN old_tier TYPE core.tier
       USING CASE WHEN old_tier IS NULL THEN NULL ELSE old_tier::core.tier END;
   ```
   (Though in practice, NULL::core.tier works fine -- the real guard is against invalid strings.)

**Detection:** Query for unexpected values before writing the migration.

**Confidence:** HIGH -- standard PostgreSQL ALTER COLUMN behavior.

---

### Pitfall 9: asyncpg OID cache goes stale after CREATE TYPE in migrations -- existing connections break

**What goes wrong:** The pogo-migrate migration runs `CREATE TYPE core.tier AS ENUM (...)`. asyncpg caches PostgreSQL type OIDs (including enum types) per connection. Existing application connections (from the pool) do not know about the new type. The first query that uses the new enum type on a pooled connection raises `asyncpg.exceptions.InvalidCachedStatementError`.

**Why it happens:** asyncpg's prepared statement cache maps type OIDs to Python decoders. New custom types (created by DDL) are not in this cache. The [SQLAlchemy asyncpg dialect](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html) handles this by invalidating caches on DDL, but only when the DDL is executed through the same engine. Migrations run through pogo-migrate (a separate process), so the application's asyncpg connections are not notified.

**Consequences:**
- First few requests after migration deployment fail with `InvalidCachedStatementError`
- SQLAlchemy's asyncpg dialect auto-recovers by clearing the cache and retrying, but the first affected request still fails

**Prevention:**
1. **Restart the application after migration** -- this is the simplest and most reliable approach. The new connections will see the new types.
2. If zero-downtime is required: run the migration, then execute `SELECT pg_advisory_lock(0); SELECT pg_advisory_unlock(0);` through the app's engine to trigger a cache clear (hacky, not recommended)
3. In Kubernetes: the migration runs as an init container or Job before the new pods start, so new pods always see the updated schema -- this is the natural pattern for this codebase

**Detection:** Monitor for `InvalidCachedStatementError` in logs after migration.

**Confidence:** HIGH -- [SQLAlchemy asyncpg dialect docs](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html) explicitly document this behavior; see also [SQLAlchemy Discussion #6648](https://github.com/sqlalchemy/sqlalchemy/discussions/6648).

---

### Pitfall 10: Rollback migration for enum types requires DROP TYPE in correct order

**What goes wrong:** The rollback section of the migration drops the enum types but does not first revert the columns back to TEXT. PostgreSQL refuses to `DROP TYPE core.tier` while columns still use it.

**Why it happens:** The forward migration creates types and changes columns. The rollback must reverse both, in the opposite order: first change columns back to TEXT, then drop the types. Additionally, the rollback needs to recreate the `plans` table and re-add the FK constraints.

**Consequences:** Rollback fails, leaving the database in a partially-migrated state that requires manual intervention.

**This codebase's specific exposure:** pogo-migrate uses `-- migrate: rollback` section. The rollback must be fully functional because the existing migration already has a working rollback pattern.

**Prevention:** The rollback must:
```sql
-- 1. Re-create the plans table
CREATE TABLE core.plans (tier TEXT PRIMARY KEY, monthly_quota INTEGER NOT NULL);
INSERT INTO core.plans (tier, monthly_quota) VALUES
    ('free', 150), ('silver', 1500), ('gold', 3000), ('platinum', 30000);

-- 2. Drop defaults on enum columns
ALTER TABLE core.users ALTER COLUMN plan DROP DEFAULT;
ALTER TABLE core.subscriptions ALTER COLUMN plan DROP DEFAULT;

-- 3. Revert column types to TEXT
ALTER TABLE core.users ALTER COLUMN plan TYPE TEXT USING plan::TEXT;
ALTER TABLE core.subscriptions ALTER COLUMN plan TYPE TEXT USING plan::TEXT;
ALTER TABLE core.messages ALTER COLUMN role TYPE TEXT USING role::TEXT;
ALTER TABLE core.subscriptions ALTER COLUMN provider TYPE TEXT USING provider::TEXT;
ALTER TABLE core.subscriptions ALTER COLUMN status TYPE TEXT USING status::TEXT;
ALTER TABLE core.subscription_events ALTER COLUMN old_tier TYPE TEXT USING old_tier::TEXT;
ALTER TABLE core.subscription_events ALTER COLUMN new_tier TYPE TEXT USING new_tier::TEXT;

-- 4. Re-add defaults
ALTER TABLE core.users ALTER COLUMN plan SET DEFAULT 'free';
ALTER TABLE core.subscriptions ALTER COLUMN plan SET DEFAULT 'free';

-- 5. Re-add FK constraints
ALTER TABLE core.users ADD CONSTRAINT users_plan_fkey FOREIGN KEY (plan) REFERENCES core.plans(tier);
ALTER TABLE core.subscriptions ADD CONSTRAINT subscriptions_plan_fkey FOREIGN KEY (plan) REFERENCES core.plans(tier);

-- 6. NOW drop the enum types
DROP TYPE core.tier;
DROP TYPE core.role;
DROP TYPE core.sub_provider;
DROP TYPE core.sub_status;
```

**Detection:** Test the rollback on a copy of the migrated database.

**Confidence:** HIGH -- fundamental PostgreSQL DDL dependency ordering.

---

### Pitfall 11: Enum type naming collision -- `role` is a PostgreSQL reserved word

**What goes wrong:** `CREATE TYPE core.role AS ENUM ('human', 'ai')` may fail or cause confusion because `role` is a non-reserved keyword in PostgreSQL (used in `SET ROLE`, `CREATE ROLE`). While it is technically allowed as a type name when schema-qualified, some tools and ORMs may not handle it correctly.

**Why it happens:** `role` appears in PostgreSQL's keyword list. While it is only a "non-reserved" keyword (meaning it can be used as an identifier), some client libraries and SQL tools may quote it unexpectedly or refuse it.

**Consequences:**
- Potential issues with SQL tools, pg_dump formatting, or ORM introspection
- Confusion in queries: `WHERE role = 'human'` is ambiguous -- is `role` a column or a type?

**Prevention:**
1. Use a more specific name: `CREATE TYPE core.message_role AS ENUM ('human', 'ai')` instead of `core.role`
2. Always schema-qualify the type in migrations and SQLAlchemy: `core.message_role`
3. Match the type name in the SQLAlchemy Enum constructor: `Enum(Role, name="message_role", schema="core")`

**Detection:** Check PostgreSQL keyword list; test with `pg_dump --schema-only` and verify the dump is parseable.

**Confidence:** MEDIUM -- `role` is non-reserved so it works, but naming it `message_role` avoids all ambiguity. This is a defensive measure, not a strict requirement.

---

## Minor Pitfalls

Mistakes that cause friction, confusion, or minor bugs.

---

### Pitfall 12: `User.plan` field type annotation changes from `str` to `Tier` -- downstream serialization impact

**What goes wrong:** Currently `User.plan` is `str`, and `UserProfileResponse.plan` is also `str`. After changing `User.plan` to `Tier`, Pydantic serialization in `UserProfileResponse` may serialize it as `Tier.free` (the repr) instead of `"free"` (the string value), depending on how the response model is constructed.

**Why it happens:** `StrEnum` values serialize as strings in most contexts, but if the response model is built by copying attributes (`plan=user.plan`), the Pydantic model receives a `Tier` instance. If `UserProfileResponse.plan` is typed as `str`, Pydantic v2 coerces it correctly. But if someone changes it to `Tier`, the JSON response might include `"Tier.free"` or just `"free"` depending on the serialization mode.

**Prevention:**
1. Keep `UserProfileResponse.plan` typed as `str` -- the API contract should not expose enum types
2. OR change it to `Tier` and verify that Pydantic v2 serializes `StrEnum` members as their `.value` (it does by default in `model_dump(mode='json')`)
3. Add a test that verifies the JSON response for `/users/me` returns `"plan": "free"` not `"plan": "Tier.free"`

**Detection:** Existing E2E test `test_users.py` should catch this if it checks the plan value format.

**Confidence:** HIGH -- Pydantic v2 handles StrEnum correctly, but worth a quick test.

---

### Pitfall 13: `SubscriptionEvent.old_tier` and `new_tier` type annotation -- str vs Tier for nullable enum columns

**What goes wrong:** `SubscriptionEvent.old_tier` and `new_tier` are currently `str | None`. Changing them to `Tier | None` requires ensuring that the SQLAlchemy Column definition handles nullable enums correctly. Additionally, the `insert_event_idempotent` method in `subscriptions.py` (line 66) passes `old_tier: str | None` -- all callers must be updated to pass `Tier | None`.

**Why it happens:** Nullable enum columns need `Enum(..., nullable=True)` in the Column definition. SQLModel's `Field(default=None)` handles the Python side, but the `sa_column` must also specify `nullable=True`.

**Prevention:**
1. Update the type annotation and `sa_column` together
2. Update all callers of `insert_event_idempotent` to pass `Tier | None`
3. The `SubscriptionService._map_lifecycle_event` already returns `Tier` values, but `old_tier = subscription.plan` returns whatever type `plan` is -- once `plan` is `Tier`, this flows correctly

**Detection:** Type checker (ty/mypy) will flag mismatches if run after the type changes.

**Confidence:** HIGH -- straightforward type propagation, but easy to miss a caller.

---

### Pitfall 14: `Message.__tablename__` is `"core.messages"` with `schema="core"` -- double-prefixed table

**What goes wrong:** This is an existing issue that becomes relevant during this migration. `Message.__tablename__ = "core.messages"` combined with `__table_args__ = {"schema": "core"}` means SQLAlchemy sees the full table name as `core.core.messages`. In practice, SQLAlchemy may treat the tablename as a dotted path or as a literal name, depending on the context. If `create_all()` tries to create `core.core.messages`, it will fail or create a table with a literal dot in the name.

**Why it happens:** The Message model appears to have been written with the intent of `__tablename__` including the schema prefix, but `__table_args__` also specifies the schema separately.

**This codebase's specific exposure:** Only the `Message` model has this pattern (line 65: `__tablename__ = "core.messages"`). Other models use just the table name (e.g., `__tablename__ = "users"`, `__tablename__ = "chats"`).

**Prevention:**
1. Change `Message.__tablename__` to `"messages"` (just the table name, no schema prefix)
2. This should be done in the same migration/release as the enum changes to avoid a separate migration for a model fix

**Detection:** If `create_all()` works in tests and the production migration creates the table correctly, this may be silently handled by SQLAlchemy. But it is technically incorrect and should be fixed.

**Confidence:** HIGH -- directly verified in `models.py` line 65 vs line 66.

---

### Pitfall 15: Enum type created in `core` schema but SQLAlchemy Enum without explicit schema casts fail

**What goes wrong:** After creating `core.tier` in the migration, SQLAlchemy constructs queries with casts like `CAST('free' AS tier)` (without schema qualification) instead of `CAST('free' AS core.tier)`. PostgreSQL cannot find the type because `core` is not on the `search_path`.

**Why it happens:** SQLAlchemy's Enum type generates SQL casts using the type name it was given. If the Enum is constructed without `schema="core"`, the cast will be unqualified. asyncpg and SQLAlchemy work together to register custom types, but schema-qualified types need explicit configuration.

**Prevention:**
1. Every SQLAlchemy `Enum` must be constructed with `schema="core"`: `Enum(Tier, name="tier", schema="core")`
2. Alternatively, set `search_path` on the connection to include `core` -- but this is fragile and not recommended
3. Verify by checking the SQL output: enable SQLAlchemy echo (`echo=True` on engine) and look for unqualified type casts

**Detection:** First query involving an enum column will fail with `type "tier" does not exist` if the schema is missing.

**Confidence:** HIGH -- confirmed via [SQLAlchemy Enum schema parameter behavior](https://docs.sqlalchemy.org/en/20/core/type_basics.html) and [issue #10594](https://github.com/sqlalchemy/sqlalchemy/issues/10594).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|---|---|---|
| Migration: CREATE TYPE | Types must exist before ALTER COLUMN references them (#2) | Strict phase ordering in migration file |
| Migration: ALTER COLUMN TYPE | DEFAULT must be dropped first, then re-added (#1) | Three-step: drop default, alter type, set default |
| Migration: FK removal | Drop FK constraints before altering column types or dropping plans table (#3) | Explicit ALTER TABLE DROP CONSTRAINT before any type changes |
| Migration: DROP TABLE plans | FK constraints block the drop (#3) | Drop FKs first, alter columns, then drop table |
| Migration: Rollback | Rollback must reverse in exact opposite order (#10) | Write and test the rollback section thoroughly |
| SQLModel models: Enum columns | Need `sa_column` with `schema="core"` and `values_callable` (#4, #5, #15) | Explicit Enum constructor on every enum field |
| SQLModel models: Message tablename | Double-prefixed `core.messages` (#14) | Fix `__tablename__` to just `"messages"` |
| Raw SQL: UsageDB | Unqualified table names + plans table removal (#6) | Qualify all tables with `core.` prefix; remove plans JOIN |
| Test fixtures: plans seed | Fixture seeds a table that no longer exists (#7) | Remove INSERT from conftest; add quota config to test config |
| Nullable enum columns | `old_tier`/`new_tier` need nullable Enum handling (#8, #13) | Validate data before migration; update type annotations and callers |
| asyncpg cache | New types invisible to existing connections (#9) | Restart application after migration (natural in K8s) |
| Enum naming | `role` is a PostgreSQL keyword (#11) | Use `message_role` instead of `role` |
| Response serialization | `User.plan` type change may affect API response (#12) | Keep response model as `str`; add serialization test |

## Integration Pitfall Map

These pitfalls must be addressed in a specific order. The dependency chain:

```
Fix Message.__tablename__ (#14)
  (independent, do first as cleanup)

Migration file ordering:
  CREATE TYPE (all 4 types) (#2, #11)
    -> DROP DEFAULT on affected columns (#1)
      -> DROP FK constraints (#3)
        -> ALTER COLUMN TYPE with USING (#1, #8)
          -> SET DEFAULT with enum cast (#1)
            -> DROP TABLE core.plans (#3)

SQLModel model updates:
  Add sa_column with Enum(schema="core", values_callable=...) (#4, #5, #15)
    -> Update type annotations (str -> Tier, str -> Role, etc.) (#12, #13)
      -> Update callers (SubscriptionDB, UsageDB) (#13)

Raw SQL rewrite:
  Remove plans JOIN from try_increment (#6)
    -> Accept monthly_quota as parameter or read from config
      -> Qualify all remaining table names with core. (#6)

Test fixture updates:
  Remove plans seed (#7)
    -> Update test config with quota values
      -> Verify E2E tests pass

Post-deployment:
  Restart application pods (#9)
```

**Recommended migration execution order:**
1. Fix `Message.__tablename__` in models.py (code change, no migration needed if tests use `create_all`)
2. Update SQLModel fields with `sa_column` Enum definitions (code change)
3. Rewrite `UsageDB` to remove plans dependency (code change)
4. Update test fixtures (code change)
5. Write the migration (single SQL file with strict phase ordering)
6. Test migration forward AND rollback on a copy of the database
7. Deploy: migration runs first (K8s Job/init container), then new pods start with fresh connections

## Sources

- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) -- DEFAULT handling with ALTER COLUMN TYPE
- [PostgreSQL DROP TABLE](https://www.postgresql.org/docs/current/sql-droptable.html) -- CASCADE vs RESTRICT behavior
- [PostgreSQL Enumerated Types](https://www.postgresql.org/docs/current/datatype-enum.html) -- native enum capabilities and limitations
- [PostgreSQL ALTER TYPE](https://www.postgresql.org/docs/current/sql-altertype.html) -- cannot remove values, ADD VALUE in transaction limitations
- [SQLAlchemy Enum Type Basics](https://docs.sqlalchemy.org/en/20/core/type_basics.html) -- `native_enum`, `create_type`, `values_callable`, `schema` parameters
- [SQLAlchemy inherit_schema issue #10594](https://github.com/sqlalchemy/sqlalchemy/issues/10594) -- `inherit_schema` defaults to False, explicit schema required
- [SQLAlchemy asyncpg dialect](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html) -- OID cache invalidation behavior
- [SQLAlchemy asyncpg stale cache discussion #6648](https://github.com/sqlalchemy/sqlalchemy/discussions/6648) -- strategies for cache invalidation
- [SQLAlchemy StrEnum processing discussion #12123](https://github.com/sqlalchemy/sqlalchemy/discussions/12123) -- name vs value storage
- [SQLModel (str, Enum) behavior change discussion #717](https://github.com/fastapi/sqlmodel/discussions/717) -- breaking change in 0.0.9+
- [SQLModel enum column issue #96](https://github.com/fastapi/sqlmodel/issues/96) -- sa_column pattern for PostgreSQL enums
- [PostgreSQL Enum Types with SQLModel and Alembic](https://shekhargulati.com/2025/01/12/postgresql-enum-types-with-sqlmodel-and-alembic/) -- practical patterns
- [Safely Alter Postgres Columns with USING](https://echobind.com/post/safely-alter-postgres-columns-with-using) -- USING clause for type conversion
- [Native enums or CHECK constraints in PostgreSQL](https://making.close.com/posts/native-enums-or-check-constraints-in-postgresql/) -- tradeoffs analysis
- [pogo-migrate](https://pypi.org/project/pogo-migrate/) -- migration tool documentation
