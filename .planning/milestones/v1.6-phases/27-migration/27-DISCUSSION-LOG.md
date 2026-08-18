# Phase 27: Migration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-03-23
**Phase:** 27-migration
**Areas discussed:** Rollback strategy, Data safety guards, FK constraint naming, Migration file naming, Enum value mapping, Column defaults, Index changes

---

## Migration Strategy (user-initiated clarification)

User clarified before area-by-area discussion began:

**User's direction:** "Don't create a new migration file, just overwrite the existing one. There is no data in the database, everything will be recreated from scratch."

**Impact:** This resolved Rollback strategy, Data safety guards, FK constraint naming, and Migration file naming simultaneously:
- Rollback: Simple DROP tables/types (no data to restore)
- Data safety: Moot (no existing data)
- FK constraints: Moot (no ALTER needed, just don't create FKs to plans)
- File naming: Same file overwritten

---

## Enum Value Mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Looks correct | All values match Python StrEnums exactly | ✓ |
| Needs changes | Adjust some enum values or type names | |

**User's choice:** Looks correct
**Notes:** Confirmed: core.chat_role (human, ai), core.subscription_plan (free, silver, gold, platinum), core.subscription_provider (apple), core.subscription_status (active, grace_period, billing_retry, expired, revoked)

---

## Column Defaults

| Option | Description | Selected |
|--------|-------------|----------|
| Match Python models | Only columns with Field(default=...) get SQL DEFAULT | |
| Needs changes | Adjust which columns get defaults | ✓ |

**User's choice:** Needs changes
**Notes:** "Don't set defaults in the database, Python models will handle that." -- No SQL-level DEFAULT on any column.

---

## Index Changes

| Option | Description | Selected |
|--------|-------------|----------|
| Keep as-is | Preserve all existing indexes, update column names | ✓ |
| Needs changes | Add, remove, or rename indexes | |

**User's choice:** Keep as-is
**Notes:** All existing indexes preserved with column name updates where applicable.

---

## Claude's Discretion

- SQL statement ordering within the migration
- Comments within the SQL
- Rollback DROP ordering

## Deferred Ideas

None -- discussion stayed within phase scope.
