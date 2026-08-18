# Phase 27: Migration - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Rewrite the single pogo-migrate migration file to reflect the final schema state: native PG enum types, renamed columns, no `core.plans` table, no FK constraints to plans. No incremental ALTER migration -- the existing file is overwritten since there is no production data.

</domain>

<decisions>
## Implementation Decisions

### Migration Strategy
- **D-01:** Overwrite `migrations/20260322_01_initial-release.sql` in place -- no new migration file. Database will be recreated from scratch (no existing data to preserve).
- **D-02:** Migration is a clean CREATE from the final schema state, not an ALTER-based incremental migration.

### Enum Types
- **D-03:** Four `CREATE TYPE` statements in `core` schema before any table creation:
  - `core.chat_role`: human, ai
  - `core.subscription_plan`: free, silver, gold, platinum
  - `core.subscription_provider`: apple
  - `core.subscription_status`: active, grace_period, billing_retry, expired, revoked
- **D-04:** Enum values match Python StrEnum string values exactly (including underscores)

### Column Definitions
- **D-05:** No SQL-level DEFAULT values on any column -- Python models own all defaults
- **D-06:** Columns use enum types directly (e.g., `role core.chat_role NOT NULL` instead of `TEXT`)
- **D-07:** Column renames applied directly in CREATE TABLE:
  - `users.plan` -> `users.subscription_plan` (type: `core.subscription_plan`)
  - `subscription_events.old_tier` -> `old_plan` (type: `core.subscription_plan`)
  - `subscription_events.new_tier` -> `new_plan` (type: `core.subscription_plan`)

### Removed Elements
- **D-08:** `core.plans` table not created at all (no CREATE, no INSERT, no FK references to it)
- **D-09:** No FK constraints from `users.subscription_plan` or `subscriptions.plan` to any plans table

### Indexes
- **D-10:** All existing indexes preserved with same names; column references updated where renamed

### Rollback
- **D-11:** Rollback section drops tables and types (standard pattern) -- no data restoration needed

### Claude's Discretion
- Exact ordering of CREATE TYPE and CREATE TABLE statements within the migration
- Whether to add comments within the SQL for clarity
- Rollback DROP ordering (reverse dependency order)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Migration
- `migrations/20260322_01_initial-release.sql` -- The file to overwrite with the new schema

### Models (source of truth for column types and names)
- `src/nativespeaker/api/models.py` -- All SQLModel classes with StrEnum types, column names, relationships, and table args

### Requirements
- `.planning/REQUIREMENTS.md` -- SCHEMA-01 (single atomic migration)

### Prior Phase Context
- `.planning/phases/25-config-and-model-foundation/25-CONTEXT.md` -- D-06 (PG enum type names), D-09 (column renames), D-11 (Plan model deleted)
- `.planning/phases/26-service-and-database-rewiring/26-CONTEXT.md` -- Confirms no query JOINs to plans table

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing migration file provides the complete current schema structure and pogo-migrate format (`-- depends:`, `-- migrate: apply`, `-- migrate: rollback`)
- `models.py` is the authoritative source for all table definitions, column types, indexes, and constraints

### Established Patterns
- pogo-migrate with `-- depends:` header for dependency tracking
- `-- migrate: apply` / `-- migrate: rollback` section markers
- Schema-qualified table names (`core.` prefix)
- Named indexes with `ix_` prefix convention

### Integration Points
- pogo-migrate reads from `./migrations` directory (configured in `pyproject.toml [tool.pogo]`)
- E2E test conftest will need updating in Phase 28 to match new schema (CREATE TYPE before create_all)

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose overwrite over incremental migration -- no production data exists, clean slate approach
- User explicitly chose no SQL-level defaults -- Python models are the single source of truth for default values
- Enum values confirmed as exact matches to Python StrEnum string values (including underscores in `grace_period`, `billing_retry`)

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 27-migration*
*Context gathered: 2026-03-23*
