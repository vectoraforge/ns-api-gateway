# Phase 27: Migration - Research

**Researched:** 2026-03-23
**Domain:** PostgreSQL DDL migration (CREATE TYPE, CREATE TABLE) via pogo-migrate
**Confidence:** HIGH

## Summary

Phase 27 rewrites the single pogo-migrate migration file (`migrations/20260322_01_initial-release.sql`) from scratch. The existing file creates the old schema with TEXT columns, FK to `core.plans`, and DEFAULT values. The new file creates four native PG enum types in the `core` schema, then creates all tables using those enum types for the relevant columns, with no `core.plans` table, no FK constraints to plans, no SQL-level DEFAULT values, and renamed columns (`subscription_plan`, `old_plan`, `new_plan`).

This is a clean-slate rewrite, not an incremental ALTER migration. The user explicitly confirmed there is no production data to preserve (D-01, D-02). The migration file keeps the same filename and pogo-migrate `-- depends:` header.

**Primary recommendation:** Rewrite the migration SQL to create enum types before tables, match column names and types exactly to `models.py`, and ensure the rollback section drops tables before types (reverse dependency order).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Overwrite `migrations/20260322_01_initial-release.sql` in place -- no new migration file. Database will be recreated from scratch (no existing data to preserve).
- **D-02:** Migration is a clean CREATE from the final schema state, not an ALTER-based incremental migration.
- **D-03:** Four `CREATE TYPE` statements in `core` schema before any table creation:
  - `core.chat_role`: human, ai
  - `core.subscription_plan`: free, silver, gold, platinum
  - `core.subscription_provider`: apple
  - `core.subscription_status`: active, grace_period, billing_retry, expired, revoked
- **D-04:** Enum values match Python StrEnum string values exactly (including underscores)
- **D-05:** No SQL-level DEFAULT values on any column -- Python models own all defaults
- **D-06:** Columns use enum types directly (e.g., `role core.chat_role NOT NULL` instead of `TEXT`)
- **D-07:** Column renames applied directly in CREATE TABLE:
  - `users.plan` -> `users.subscription_plan` (type: `core.subscription_plan`)
  - `subscription_events.old_tier` -> `old_plan` (type: `core.subscription_plan`)
  - `subscription_events.new_tier` -> `new_plan` (type: `core.subscription_plan`)
- **D-08:** `core.plans` table not created at all (no CREATE, no INSERT, no FK references to it)
- **D-09:** No FK constraints from `users.subscription_plan` or `subscriptions.plan` to any plans table
- **D-10:** All existing indexes preserved with same names; column references updated where renamed
- **D-11:** Rollback section drops tables and types (standard pattern) -- no data restoration needed

### Claude's Discretion
- Exact ordering of CREATE TYPE and CREATE TABLE statements within the migration
- Whether to add comments within the SQL for clarity
- Rollback DROP ordering (reverse dependency order)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHEMA-01 | Single atomic pogo-migrate migration covering CREATE TYPE, DROP DEFAULT, DROP FK, ALTER COLUMN TYPE, SET DEFAULT, DROP TABLE | Since this is a clean CREATE (D-02), SCHEMA-01 is satisfied by a single file with CREATE TYPE + CREATE TABLE. No ALTER/DROP needed because we start from nothing. The pogo-migrate format supports multiple SQL statements in one file. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Don't commit .planning dir** -- research file stays local
- **Opening delimiter alignment style** for multiline constructs (not relevant to SQL migration, but noted)
- **Use Context7 MCP** for library docs when needed
- **Shorter branch names** for git branches

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pogo-migrate | 0.4.2 | SQL migration runner | Already in use; reads from `./migrations` directory per `pyproject.toml [tool.pogo]` |
| PostgreSQL | 15+ (target) | Database engine | Project database; supports CREATE TYPE AS ENUM with schema qualification |

### Supporting
No additional libraries needed -- this phase is pure SQL DDL.

## Architecture Patterns

### pogo-migrate SQL File Format

The migration file follows this exact structure:

```sql
-- description text
-- depends:

-- migrate: apply

[SQL statements here]

-- migrate: rollback

[SQL statements here]
```

**Key constraints:**
- `-- depends:` with no value means this is the first migration (no predecessors)
- `-- migrate: apply` and `-- migrate: rollback` are section markers (mandatory)
- Multiple SQL statements are allowed in each section
- Statements must be valid PostgreSQL DDL

### Recommended Statement Ordering (Apply)

```
1. CREATE SCHEMA IF NOT EXISTS core;
2. CREATE TYPE core.chat_role AS ENUM (...)
3. CREATE TYPE core.subscription_plan AS ENUM (...)
4. CREATE TYPE core.subscription_provider AS ENUM (...)
5. CREATE TYPE core.subscription_status AS ENUM (...)
6. CREATE TABLE core.users (...)
7. CREATE TABLE core.chats (...)
8. CREATE TABLE core.messages (...)
9. CREATE TABLE core.subscriptions (...)
10. CREATE TABLE core.subscription_events (...)
11. CREATE TABLE core.usage_monthly (...)
12. CREATE INDEX statements
```

**Rationale:** Types must exist before any table references them. Tables with FK dependencies come after their referenced tables (users before chats, subscriptions before subscription_events).

### Recommended Statement Ordering (Rollback)

```
1. DROP TABLE IF EXISTS core.subscription_events;
2. DROP TABLE IF EXISTS core.subscriptions;
3. DROP TABLE IF EXISTS core.messages;
4. DROP TABLE IF EXISTS core.chats;
5. DROP TABLE IF EXISTS core.usage_monthly;
6. DROP TABLE IF EXISTS core.users;
7. DROP TYPE IF EXISTS core.subscription_status;
8. DROP TYPE IF EXISTS core.subscription_provider;
9. DROP TYPE IF EXISTS core.subscription_plan;
10. DROP TYPE IF EXISTS core.chat_role;
11. DROP SCHEMA IF EXISTS core;
```

**Rationale:** Reverse dependency order -- tables that have FKs to other tables drop first, then independent tables, then types (which tables depend on), then schema.

### Anti-Patterns to Avoid
- **Using CASCADE on DROP TYPE:** Silently drops columns. Use explicit table drops first, then type drops.
- **Adding DEFAULT values in SQL:** D-05 explicitly forbids this. Python models own all defaults.
- **Using IF NOT EXISTS on CREATE TYPE:** PostgreSQL does not support `IF NOT EXISTS` for `CREATE TYPE`. The migration runs exactly once against a fresh database.

## Column-to-Type Mapping

Derived from `models.py` (source of truth) cross-referenced with CONTEXT.md decisions:

| Table | Column | Old Type | New Type | Notes |
|-------|--------|----------|----------|-------|
| `core.users` | `subscription_plan` | `plan TEXT ... DEFAULT 'free' REFERENCES core.plans` | `subscription_plan core.subscription_plan NOT NULL` | Renamed from `plan`, no FK, no DEFAULT |
| `core.messages` | `role` | `role TEXT NOT NULL` | `role core.chat_role NOT NULL` | Type change only |
| `core.subscriptions` | `provider` | `provider TEXT NOT NULL` | `provider core.subscription_provider NOT NULL` | Type change only |
| `core.subscriptions` | `plan` | `plan TEXT ... DEFAULT 'free' REFERENCES core.plans` | `plan core.subscription_plan NOT NULL` | No FK, no DEFAULT |
| `core.subscriptions` | `status` | `status TEXT NOT NULL` | `status core.subscription_status NOT NULL` | Type change only |
| `core.subscription_events` | `old_plan` | `old_tier TEXT` | `old_plan core.subscription_plan` | Renamed, nullable |
| `core.subscription_events` | `new_plan` | `new_tier TEXT` | `new_plan core.subscription_plan` | Renamed, nullable |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Migration execution | Custom SQL runner | pogo-migrate CLI (`pogo apply`) | Already configured in pyproject.toml, handles transaction wrapping |
| Schema diffing | Manual comparison | Compare models.py to SQL directly | Single source of truth is models.py; no automated schema diff tool in stack |

## Common Pitfalls

### Pitfall 1: Partial Index with Enum Type WHERE Clause
**What goes wrong:** The existing partial index on `core.subscriptions` uses `WHERE status NOT IN ('expired', 'revoked')`. When `status` becomes an enum type, string literals in the WHERE clause must be implicitly castable to the enum type.
**Why it happens:** PostgreSQL casts string literals to enum types at DDL time via `enum_in()`. For CREATE INDEX DDL this works correctly because the cast is resolved at index creation time, not at query time.
**How to avoid:** Use the exact enum value strings in the WHERE clause. Since the column is declared as `core.subscription_status` and the enum values include `expired` and `revoked`, the statement `WHERE status NOT IN ('expired', 'revoked')` will work correctly at CREATE INDEX time.
**Warning signs:** If `pogo apply` errors with "invalid input value for enum", the string literals don't match enum values.

### Pitfall 2: Forgetting to Remove DEFAULT Values
**What goes wrong:** Copying DEFAULT clauses from the old migration into the new one.
**Why it happens:** The old migration has `DEFAULT 'free'` on `users.plan` and `subscriptions.plan`, plus `DEFAULT TRUE`, `DEFAULT 0`, `DEFAULT now()` on other columns.
**How to avoid:** D-05 mandates no SQL-level DEFAULT values. Every column definition should be `column_name type [NOT NULL]` only. Python models own all defaults via `Field(default=...)` and `Field(default_factory=...)`.
**Warning signs:** Any `DEFAULT` keyword in the new migration file.

### Pitfall 3: Mismatching Column Names Between SQL and models.py
**What goes wrong:** The SQL column name doesn't match the Python field name, causing SQLModel/SQLAlchemy to not find the column.
**Why it happens:** Multiple renames happened in Phase 25 (`plan` -> `subscription_plan`, `old_tier` -> `old_plan`, `new_tier` -> `new_plan`).
**How to avoid:** For each table, verify every column name in the SQL matches the corresponding field name in models.py. The `__tablename__` attribute gives the SQL table name; field names give column names.
**Warning signs:** Runtime errors like "column users.plan does not exist".

### Pitfall 4: Missing ON DELETE Clauses
**What goes wrong:** FK behavior changes silently if ON DELETE is omitted.
**Why it happens:** The old migration has `ON DELETE RESTRICT` and `ON DELETE CASCADE` on various FKs. The models.py defines these via `ondelete="CASCADE"` on `Field(foreign_key=...)`.
**How to avoid:** Check each FK in models.py for `ondelete` parameter and mirror it in SQL. Models without explicit `ondelete` get PostgreSQL's default (RESTRICT/NO ACTION).
**Warning signs:** SQLModel fields with `ondelete=` that don't match the SQL FK clause.

### Pitfall 5: Enum Value Ordering
**What goes wrong:** Enum sort order in PostgreSQL is determined by creation order, not alphabetical.
**Why it happens:** PG enums are ordered by the position they appear in the `CREATE TYPE ... AS ENUM (...)` values list.
**How to avoid:** Match the order to the Python StrEnum class member order. This isn't functionally critical for this application (no ORDER BY on enum columns), but is good practice.
**Warning signs:** None for this project, but noted for completeness.

### Pitfall 6: Schema Name in __tablename__ vs SQL
**What goes wrong:** SCHEMA-02 fixed `Message.__tablename__` from `"core.messages"` to `"messages"` with `__table_args__ = {"schema": "core"}`. The SQL must use `core.messages` (schema-qualified) in CREATE TABLE but models.py uses just `"messages"`.
**How to avoid:** In SQL, always use schema-qualified names (`core.tablename`). In models.py, the schema is in `__table_args__`. These are different representations of the same thing.
**Warning signs:** None -- this is already established pattern.

## Code Examples

### Complete models.py-to-SQL Mapping for CREATE TYPE

Source: `src/nativespeaker/api/models.py` lines 25-46

```sql
-- Matches ChatRole(StrEnum): human = "human", ai = "ai"
CREATE TYPE core.chat_role AS ENUM ('human', 'ai');

-- Matches SubscriptionPlan(StrEnum): free, silver, gold, platinum
CREATE TYPE core.subscription_plan AS ENUM ('free', 'silver', 'gold', 'platinum');

-- Matches SubscriptionProvider(StrEnum): apple = "apple"
CREATE TYPE core.subscription_provider AS ENUM ('apple');

-- Matches SubscriptionStatus(StrEnum): active, grace_period, billing_retry, expired, revoked
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');
```

### Users Table (showing removed DEFAULT, renamed column, no FK to plans)

Source: `models.py` User class (lines 103-113) + D-05, D-07, D-09

```sql
CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    jwt_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    subscription_plan core.subscription_plan NOT NULL,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

### Partial Index on Subscriptions (enum-aware)

Source: `models.py` Subscription class (lines 118-126)

```sql
CREATE UNIQUE INDEX ix_subscriptions_user_provider_active
    ON core.subscriptions (user_id, provider)
    WHERE status NOT IN ('expired', 'revoked');
```

PostgreSQL resolves string literal to enum cast at CREATE INDEX time. This works because the `status` column is typed as `core.subscription_status` and the literal values match enum members exactly.

### Rollback Pattern

```sql
-- migrate: rollback

DROP TABLE IF EXISTS core.subscription_events;
DROP TABLE IF EXISTS core.subscriptions;
DROP TABLE IF EXISTS core.messages;
DROP TABLE IF EXISTS core.chats;
DROP TABLE IF EXISTS core.usage_monthly;
DROP TABLE IF EXISTS core.users;
DROP TYPE IF EXISTS core.subscription_status;
DROP TYPE IF EXISTS core.subscription_provider;
DROP TYPE IF EXISTS core.subscription_plan;
DROP TYPE IF EXISTS core.chat_role;
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| TEXT columns with FK to plans table | Native PG enum types, no plans table | Phase 25-27 (v1.6) | Database enforces valid values; no lookup table overhead |
| SQL DEFAULT values on columns | Python-owned defaults via SQLModel Field() | Phase 25-27 (v1.6) | Single source of truth for defaults in application code |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `pytest tests/unit -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHEMA-01 | Migration SQL is syntactically valid and creates correct schema | manual-only | Apply migration against a test PG instance (`pogo apply`) | N/A -- migration validation requires live PG |

### Justification for Manual-Only Testing

SCHEMA-01 is a SQL file rewrite. It cannot be validated by Python unit tests -- it requires running the SQL against a real PostgreSQL instance. The validation path is:

1. `pogo apply` against a fresh PG database succeeds without error
2. Inspect the resulting schema: enum types exist, columns have correct types, no plans table
3. Attempt inserting invalid enum values -- PG rejects them

This aligns with the phase success criteria:
- "Running the migration against the current production schema succeeds without error"
- "After migration, inserting a row with an invalid enum value into any converted column is rejected by PostgreSQL"

E2E test infrastructure updates (TEST-01) are deferred to Phase 28.

### Sampling Rate
- **Per task commit:** Visual diff review of SQL against models.py
- **Phase gate:** `pogo apply` against fresh PG instance (Docker available)

### Wave 0 Gaps
None -- no new test files needed for this phase. Migration validation is via `pogo apply`.

## Open Questions

1. **pogo-migrate schema tracking table**
   - What we know: pogo-migrate stores applied migrations in a tracking table. The `[tool.pogo]` config sets `schema = 'api'` which may be the schema for the tracking table (separate from `core` where application tables live).
   - What's unclear: Whether overwriting the migration file in place requires any special handling if pogo has already tracked the old version.
   - Recommendation: Since the database is recreated from scratch (D-01), this is a non-issue. The tracking table will also be fresh.

2. **`core.role` naming concern from STATE.md**
   - What we know: STATE.md mentions "core.role type name uses PG non-reserved keyword; decide whether to use core.message_role before migration". However, D-03 in CONTEXT.md explicitly locks the name as `core.chat_role`.
   - What's unclear: Nothing -- CONTEXT.md decision supersedes the STATE.md concern. The name was decided during the discussion phase.
   - Recommendation: Use `core.chat_role` as decided in D-03.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pogo-migrate | Migration execution | Yes (CLI) | 0.4.2 | -- |
| PostgreSQL | Migration target | Via Docker | -- | Docker compose or manual container |
| Docker | PG container for testing | Yes | 28.2.2 | -- |
| psql | Direct SQL verification | No | -- | Use pogo CLI or Docker exec |

**Missing dependencies with no fallback:**
- None -- all critical dependencies available

**Missing dependencies with fallback:**
- psql not installed locally -- use `docker exec` to run SQL verification against a PG container

## Sources

### Primary (HIGH confidence)
- `migrations/20260322_01_initial-release.sql` -- current migration file (source of truth for existing schema)
- `src/nativespeaker/api/models.py` -- Python models (source of truth for target schema)
- `27-CONTEXT.md` -- all locked decisions D-01 through D-11
- `25-CONTEXT.md` -- D-05 (no sa_type), D-06 (PG enum type names), D-07-D-09 (renames)
- [PostgreSQL CREATE TYPE docs](https://www.postgresql.org/docs/current/sql-createtype.html) -- schema-qualified enum creation syntax
- [PostgreSQL Enumerated Types docs](https://www.postgresql.org/docs/current/datatype-enum.html) -- enum value constraints, case sensitivity, NAMEDATALEN limit

### Secondary (MEDIUM confidence)
- [PostgreSQL partial index with enum thread](https://www.postgresql.org/message-id/2770839.1632775590@sss.pgh.pa.us) -- string literals in partial index WHERE clauses work at DDL time
- [pogo-migrate GitHub](https://github.com/NRWLDev/pogo-migrate) -- SQL migration file format (-- depends:, -- migrate: apply/rollback)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pogo-migrate already in use, format verified from existing migration file
- Architecture: HIGH -- all column types, names, and constraints derivable from models.py and CONTEXT.md decisions
- Pitfalls: HIGH -- enum/partial-index interaction verified via PostgreSQL mailing list; DEFAULT removal verified from decisions

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (stable -- PostgreSQL DDL syntax does not change between minor versions)
