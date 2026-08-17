---
phase: 29-replace-all-raw-sql-with-proper-sqlmodel-use-in-database
plan: 01
subsystem: database
tags: [sqlmodel, sqlalchemy, orm, postgresql, pg_insert, upsert]

# Dependency graph
requires:
  - phase: 26-rewrite-usagedb-to-read-quotas-from-config-instead-of-joining-plans
    provides: UsageDB with caller-provided monthly_quota decoupled from plans table
provides:
  - ORM-based UsageDB with zero raw SQL -- pg_insert upsert, SQLAlchemy update(), SQLModel select()
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pg_insert for INSERT ON CONFLICT upserts (matching users.py pattern)"
    - "SQLAlchemy core update() with RETURNING for atomic conditional mutations"
    - "SQLModel select() for type-safe scalar reads"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/database/usage.py

key-decisions:
  - "Used SQLAlchemy core update() instead of ORM attribute mutation for atomic conditional increment with RETURNING"
  - "Explicit id=uuid7() in pg_insert values since pg_insert bypasses SQLModel default_factory"

patterns-established:
  - "All database layer files now use ORM constructs -- no raw SQL remains in the codebase"

requirements-completed: [ORM-01, ORM-02, ORM-03, ORM-04]

# Metrics
duration: 2min
completed: 2026-03-24
---

# Phase 29 Plan 01: Replace Raw SQL in usage.py Summary

**Rewrote UsageDB from raw text() SQL to type-safe ORM constructs using pg_insert, SQLAlchemy update(), and SQLModel select()**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-24T23:45:29Z
- **Completed:** 2026-03-24T23:47:06Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Eliminated all raw SQL text() calls from usage.py -- the last file in the database layer using raw SQL
- try_increment uses pg_insert for race-safe upsert + SQLAlchemy update() with RETURNING for atomic conditional increment
- get_usage uses SQLModel select() for type-safe scalar read
- reset_usage uses SQLAlchemy update() for simple mutation
- All 103 unit tests pass unchanged (7 usage-specific tests, 96 others)

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite usage.py from raw SQL to ORM constructs** - `997a12a` (feat)

## Files Created/Modified
- `src/nativespeaker/api/database/usage.py` - Rewrote all 3 methods from raw text() SQL to ORM: pg_insert for upsert, update() for mutations, select() for reads

## Decisions Made
- Used SQLAlchemy core `update()` instead of ORM attribute mutation for try_increment because the atomic conditional UPDATE with RETURNING clause requires a single-statement approach -- ORM load-modify-save would introduce a race window
- Passed explicit `id=uuid7()` in pg_insert `.values()` because `pg_insert` bypasses SQLModel `default_factory`, which would otherwise leave `id` as NULL

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test collection errors in test_models.py and test_services.py (ImportError for `Issue` from `nativespeaker.api.schema`) -- unrelated to this plan's changes, confirmed by reverting and re-running. These are out of scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All database layer files now use proper ORM constructs -- raw SQL has been fully eliminated
- No blockers or concerns

## Self-Check: PASSED

- FOUND: src/nativespeaker/api/database/usage.py
- FOUND: commit 997a12a
- FOUND: 29-01-SUMMARY.md

---
*Phase: 29-replace-all-raw-sql-with-proper-sqlmodel-use-in-database*
*Completed: 2026-03-24*
