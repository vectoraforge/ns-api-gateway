# Phase 24: Migration Table Reference Fix - Research

**Researched:** 2026-03-22
**Domain:** PostgreSQL migrations, SQLModel/SQLAlchemy FK constraints, pogo-migrate
**Confidence:** HIGH

## Summary

The project has two SQL migration files managed by pogo-migrate. The first migration (`20260317_01_bvi4l-initial-release.sql`) creates `users` and `subscriptions` tables with a `plan TEXT` column -- a plain string with no referential integrity. The second migration (`20260321_01_add-plans-and-usage.sql`) creates a `plans` table with `tier TEXT PRIMARY KEY` and a `monthly_quota` column. The `usage_db.py` code already joins `users.plan = plans.tier`, but there is no database-level foreign key enforcing this relationship.

Since this is a pre-production project with no live data, the correct approach is to merge both migrations into a single initial migration that creates the `plans` table first, then references it via FK from `users.plan` and `subscriptions.plan`. The SQLAlchemy/SQLModel models in `app/models.py` must also be updated to declare the FK relationship.

**Primary recommendation:** Merge both SQL migrations into one file, add `REFERENCES plans(tier)` to `users.plan` and `subscriptions.plan` columns, and add matching `foreign_key="plans.tier"` to the SQLModel field definitions.

## Project Constraints (from CLAUDE.md)

- Do not commit `.planning` directory
- Use opening delimiter alignment style for multiline constructs
- Use Context7 MCP for library/API documentation
- Python 3.12+ with latest features
- FastAPI + SQLModel + asyncpg stack

## Detailed Problem Analysis

### Current State: Two Migration Files

**Migration 1:** `migrations/20260317_01_bvi4l-initial-release.sql`
- Creates: `users`, `chats`, `messages`, `subscriptions`, `subscription_events`
- `users.plan` is `TEXT NOT NULL DEFAULT 'free'` -- no FK constraint
- `subscriptions.plan` is `TEXT NOT NULL DEFAULT 'free'` -- no FK constraint

**Migration 2:** `migrations/20260321_01_add-plans-and-usage.sql`
- Depends on migration 1
- Creates: `plans` (tier TEXT PK, monthly_quota INTEGER), `usage_monthly`
- Seeds plan tiers: free(150), silver(1500), gold(3000), platinum(30000)

### Current State: SQLModel Models

In `app/models.py`:
- `User.plan` is `PlanTier = Field(default=PlanTier.free, sa_type=Text())` -- no `foreign_key` declared
- `Subscription.plan` is `PlanTier = Field(sa_type=Text())` -- no `foreign_key` declared
- `Plan.tier` is `str = Field(primary_key=True, sa_type=Text())` -- the PK target

### Current State: Runtime SQL Queries

`app/database/usage_db.py` uses raw SQL that already assumes the relationship:
- `try_increment()`: `p.tier = (SELECT plan FROM users WHERE id = :user_id)` -- joins plans via subquery
- `get_monthly_limit()`: `JOIN users u ON u.plan = p.tier` -- explicit join

These queries work today because the text values happen to match, but nothing prevents inserting a user with `plan = 'invalid_tier'`.

### What Needs to Change

| Component | Current | Target |
|-----------|---------|--------|
| `users.plan` column (SQL) | `TEXT NOT NULL DEFAULT 'free'` | `TEXT NOT NULL DEFAULT 'free' REFERENCES plans(tier)` |
| `subscriptions.plan` column (SQL) | `TEXT NOT NULL DEFAULT 'free'` | `TEXT NOT NULL DEFAULT 'free' REFERENCES plans(tier)` |
| Migration files | 2 separate files | 1 merged file (plans table first, then users/subscriptions) |
| `User.plan` model field | `Field(default=PlanTier.free, sa_type=Text())` | `Field(default=PlanTier.free, sa_type=Text(), foreign_key="plans.tier")` |
| `Subscription.plan` model field | `Field(sa_type=Text())` | `Field(sa_type=Text(), foreign_key="plans.tier")` |

## Architecture Patterns

### Migration Merge Strategy

Since this is a pre-production greenfield project (confirmed by STATE.md: "v1.5 milestone, no production data"), the cleanest approach is:

1. **Delete both existing migration files**
2. **Create a single new migration** that creates tables in dependency order:
   - `plans` (no deps)
   - `users` (depends on `plans` via FK)
   - `chats` (depends on `users`)
   - `messages` (depends on `chats`)
   - `subscriptions` (depends on `users` and `plans`)
   - `subscription_events` (depends on `subscriptions`)
   - `usage_monthly` (depends on `users`)
3. **Seed the plans data** in the same migration

### pogo-migrate File Format

Based on the existing migration files, pogo-migrate uses this format:
```sql
-- description line
-- depends: [previous_migration_id or empty for first]

-- migrate: apply

[SQL statements]

-- migrate: rollback

[SQL statements]
```

File naming: `YYYYMMDD_NN_HASH-description.sql`

For a single merged migration with no predecessor:
```sql
-- initial release with plans, users, and usage
-- depends:

-- migrate: apply
...
-- migrate: rollback
...
```

### Table Creation Order

The FK dependency graph requires this creation order:

```
plans           (no FK deps)
  |
users           (plan -> plans.tier)
  |
  +-- chats     (user_id -> users.id)
  |     |
  |     +-- messages (chat_id -> chats.id)
  |
  +-- subscriptions (user_id -> users.id, plan -> plans.tier)
  |     |
  |     +-- subscription_events (subscription_id -> subscriptions.id)
  |
  +-- usage_monthly (user_id -> users.id)
```

Rollback must be in reverse: `subscription_events`, `subscriptions`, `messages`, `chats`, `usage_monthly`, `users`, `plans`.

### SQLModel FK Declaration

SQLModel `Field(foreign_key="table.column")` syntax for the plan field:

```python
class User(BaseTable, table=True):
    plan: PlanTier = Field(default=PlanTier.free,
                           sa_type=Text(),
                           foreign_key="plans.tier")
```

```python
class Subscription(BaseTable, table=True):
    plan: PlanTier = Field(sa_type=Text(),
                           foreign_key="plans.tier")
```

### Anti-Patterns to Avoid

- **Keeping two migrations when there's no production data:** Unnecessary complexity. A single clean migration is simpler and self-documenting.
- **Adding a third migration to alter columns:** Over-engineering for a greenfield project. ALTER TABLE ADD CONSTRAINT is for production databases with existing data.
- **Forgetting to update the rollback section:** Drop order must respect FK dependencies (reverse of creation).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Referential integrity for plan tier | Application-level validation only | Database FK constraint | FK guarantees consistency even under raw SQL, concurrent writes, or bugs |
| Migration ordering | Manual trial and error | pogo-migrate `depends:` directive | Tool handles topological ordering |

## Common Pitfalls

### Pitfall 1: FK Ordering in CREATE TABLE
**What goes wrong:** Creating `users` table before `plans` table causes FK reference error
**Why it happens:** `REFERENCES plans(tier)` requires `plans` to already exist
**How to avoid:** Create `plans` table (with seed data) before any table that references it
**Warning signs:** `ERROR: relation "plans" does not exist`

### Pitfall 2: Seed Data Must Precede FK-Constrained Inserts
**What goes wrong:** Application tries to create a user with `plan='free'` but the plans table has no seed data yet
**Why it happens:** FK constraint validates that the referenced row exists
**How to avoid:** INSERT seed data into `plans` immediately after CREATE TABLE plans, before any other table is used
**Warning signs:** `ERROR: insert or update on table "users" violates foreign key constraint`

### Pitfall 3: Rollback Order Must Reverse FK Dependencies
**What goes wrong:** DROP TABLE plans fails because users table still references it
**Why it happens:** PostgreSQL won't drop a table that is referenced by FK unless CASCADE is used
**How to avoid:** Drop in reverse dependency order, or use CASCADE (but CASCADE is dangerous)
**Warning signs:** `ERROR: cannot drop table plans because other objects depend on it`

### Pitfall 4: E2E Tests Use `SQLModel.metadata.create_all`
**What goes wrong:** E2E test conftest at `tests/e2e/conftest.py:31` uses `SQLModel.metadata.create_all` to create tables. If models declare FK to `plans.tier` but the `Plan` model is not imported, SQLAlchemy won't know about the `plans` table and creation will fail.
**Why it happens:** SQLModel only registers tables for models that have been imported into the Python process.
**How to avoid:** Ensure `Plan` and `UsageMonthly` models are imported in the e2e conftest (they should already be via `app/models.py` import, but verify).
**Warning signs:** `sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 'users.plan' could not find table 'plans'`

### Pitfall 5: E2E Tests Won't Have Plans Seed Data
**What goes wrong:** E2E tests use `create_all` which creates table structure but does NOT run migrations, so the `plans` table will be empty. Any user insert triggers FK violation.
**Why it happens:** `SQLModel.metadata.create_all` only creates DDL, not DML (INSERT statements from migration).
**How to avoid:** Add a fixture or startup step that seeds the plans table after `create_all`, OR add the seed data in application lifespan startup.
**Warning signs:** `IntegrityError: insert or update on table "users" violates foreign key constraint "users_plan_fkey"`

### Pitfall 6: pogo-migrate Internal State Table
**What goes wrong:** pogo-migrate tracks which migrations have been applied. Renaming/merging migration files means the old migration IDs no longer match.
**Why it happens:** pogo-migrate stores applied migration IDs in a `_pogo_migration` table.
**How to avoid:** Since this is pre-production, either drop the pogo state table before re-applying, or document that a fresh `pogo migrate apply` is needed after the merge.
**Warning signs:** pogo-migrate thinks migrations are already applied or shows conflicts

## Code Examples

### Merged Migration SQL (Target State)
```sql
-- initial release with plans, users, subscriptions, and usage
-- depends:

-- migrate: apply

CREATE TABLE plans (
    tier TEXT PRIMARY KEY,
    monthly_quota INTEGER NOT NULL
);

INSERT INTO plans (tier, monthly_quota) VALUES
    ('free', 150),
    ('silver', 1500),
    ('gold', 3000),
    ('platinum', 30000);

CREATE TABLE users (
    id UUID PRIMARY KEY,
    jwt_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    plan TEXT NOT NULL DEFAULT 'free' REFERENCES plans (tier),
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

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES chats (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free' REFERENCES plans (tier),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscriptions_user_id ON subscriptions (user_id);
CREATE INDEX ix_subscriptions_external_id ON subscriptions (external_id);
CREATE UNIQUE INDEX ix_subscriptions_user_provider_active
    ON subscriptions (user_id, provider)
    WHERE status NOT IN ('expired', 'revoked');

CREATE TABLE subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES subscriptions (id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_tier TEXT,
    new_tier TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscription_events_subscription_id ON subscription_events (subscription_id);

CREATE TABLE usage_monthly (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, month)
);

CREATE INDEX ix_usage_monthly_user_month ON usage_monthly (user_id, month);

-- migrate: rollback

DROP TABLE IF EXISTS subscription_events;
DROP TABLE IF EXISTS subscriptions;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS usage_monthly;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS plans;
```

### SQLModel FK Field Updates
```python
# In User model
plan: PlanTier = Field(default=PlanTier.free,
                       sa_type=Text(),
                       foreign_key="plans.tier")

# In Subscription model
plan: PlanTier = Field(sa_type=Text(),
                       foreign_key="plans.tier")
```

### E2E Test Plans Seeding (if needed)
```python
# In tests/e2e/conftest.py ensure_tables fixture, after create_all:
from sqlalchemy import text
async with engine.begin() as conn:
    await conn.execute(text(
        "INSERT INTO plans (tier, monthly_quota) VALUES "
        "('free', 150), ('silver', 1500), ('gold', 3000), ('platinum', 30000) "
        "ON CONFLICT (tier) DO NOTHING"
    ))
```

## Files Requiring Changes

| File | Change | Reason |
|------|--------|--------|
| `migrations/20260317_01_bvi4l-initial-release.sql` | Delete | Being merged |
| `migrations/20260321_01_add-plans-and-usage.sql` | Delete | Being merged |
| `migrations/YYYYMMDD_01_HASH-initial-release.sql` | Create | Merged migration with FK constraints |
| `app/models.py` line 110 (`User.plan`) | Add `foreign_key="plans.tier"` | Model must match DB schema |
| `app/models.py` line 131 (`Subscription.plan`) | Add `foreign_key="plans.tier"` | Model must match DB schema |
| `tests/e2e/conftest.py` | Add plans seed data after `create_all` | E2E tests don't run migrations, need seed data for FK |

## Impact Analysis

### No Changes Needed
- `app/database/usage_db.py` -- Raw SQL already joins correctly (`u.plan = p.tier`)
- `app/database/subscriptions_db.py` -- Uses ORM, FK is transparent
- `app/database/users_db.py` -- Uses ORM, FK is transparent
- `app/routers/users.py` -- Reads `user.plan`, no write impact
- `app/services/subscription_service.py` -- Writes valid PlanTier values, FK will pass
- `tests/unit/*` -- Unit tests mock the DB layer, no schema dependency
- `k8s/templates/*` -- Kubernetes manifests reference `plan` as a JWT claim header, not DB column

### Needs Verification
- `tests/e2e/conftest.py` -- Must seed `plans` table for FK to work with `create_all`

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x` |
| Full suite command | `uv run pytest tests/unit/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MIG-01 | Merged migration creates all tables with FK constraints | manual/e2e | `pogo migrate apply` against test DB | N/A (migration correctness) |
| MIG-02 | SQLModel models declare FK to plans.tier | unit | `uv run pytest tests/unit/test_usage.py -x` | Existing tests cover quota logic |
| MIG-03 | E2E tests work with new FK constraints | e2e | `uv run pytest tests/e2e/ -x -m e2e` | Existing e2e conftest needs update |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x`
- **Per wave merge:** `uv run pytest tests/unit/ -v`
- **Phase gate:** Full unit suite green

### Wave 0 Gaps
- [ ] `tests/e2e/conftest.py` -- needs plans seed data fixture after `create_all`

## Open Questions

1. **Migration file naming convention for pogo-migrate**
   - What we know: Existing files use `YYYYMMDD_NN_HASH-description.sql` format
   - What's unclear: Whether pogo-migrate generates the hash or if it's manual
   - Recommendation: Use `pogo new` command if available, otherwise manually create with today's date and a new hash. Since both old files are deleted, there's no dependency chain to maintain.

2. **Should `subscription_events.old_tier` / `new_tier` also FK to plans?**
   - What we know: These columns store tier strings but are nullable (recording history)
   - What's unclear: Whether historical tier values should be constrained
   - Recommendation: Leave as plain TEXT. These are audit log fields and should preserve whatever value was recorded, even if the plans table changes in the future.

## Sources

### Primary (HIGH confidence)
- `migrations/20260317_01_bvi4l-initial-release.sql` -- direct file inspection
- `migrations/20260321_01_add-plans-and-usage.sql` -- direct file inspection
- `app/models.py` -- direct file inspection
- `app/database/usage_db.py` -- direct file inspection of raw SQL queries
- `app/database/subscriptions_db.py` -- direct file inspection
- `tests/e2e/conftest.py` -- direct file inspection of test setup

### Secondary (MEDIUM confidence)
- [pogo-migrate PyPI](https://pypi.org/project/pogo-migrate/) -- migration tool format

## Metadata

**Confidence breakdown:**
- Problem analysis: HIGH - direct source code inspection, all files read
- Migration strategy: HIGH - standard PostgreSQL FK pattern, greenfield project
- Model changes: HIGH - SQLModel FK syntax is well-documented
- Test impact: HIGH - e2e conftest inspected, pitfall identified and solution provided
- Pitfalls: HIGH - all based on direct analysis of actual project code

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable domain, no library version sensitivity)
