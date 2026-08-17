---
phase: 24-migration-merge
plan: 01
subsystem: database
tags: [postgresql, sqlmodel, migrations, foreign-keys]

requires:
  - phase: 23-envoy-gateway-rate-limiting
    provides: "plans table and usage_monthly table in separate migration"
provides:
  - "Single merged migration with FK constraints on users.plan and subscriptions.plan"
  - "SQLModel models with foreign_key declarations matching SQL REFERENCES"
  - "E2E test fixture seeding plans data for FK satisfaction"
affects: [e2e-tests, subscription-management, user-management]

tech-stack:
  added: []
  patterns: ["FK constraints at both SQL and ORM level for referential integrity"]

key-files:
  created:
    - migrations/20260322_01_initial-release.sql
  modified:
    - app/models.py
    - tests/e2e/conftest.py

key-decisions:
  - "Plans table created first in migration for FK dependency order"
  - "Seed data inserted in migration (not just e2e conftest) for production correctness"
  - "ON CONFLICT DO NOTHING in e2e seeding for idempotency"

patterns-established:
  - "FK dependency order: plans -> users -> chats -> messages -> subscriptions -> subscription_events -> usage_monthly"

requirements-completed: [MIG-01, MIG-02, MIG-03]

duration: 2min
completed: 2026-03-22
---

# Phase 24 Plan 01: Migration Merge Summary

**Merged two SQL migrations into single file with FK constraints on users.plan and subscriptions.plan referencing plans(tier), plus matching SQLModel foreign_key declarations**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-22T23:34:14Z
- **Completed:** 2026-03-22T23:36:13Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Merged two migration files into single `20260322_01_initial-release.sql` with tables in FK dependency order
- Added `REFERENCES plans (tier)` on both `users.plan` and `subscriptions.plan` columns in SQL
- Added `foreign_key="plans.tier"` to `User.plan` and `Subscription.plan` SQLModel fields
- E2E test fixture now seeds plans table after `create_all` with `ON CONFLICT DO NOTHING`

## Task Commits

Each task was committed atomically:

1. **Task 1: Merge migrations and add FK to SQLModel models** - `3bc5b92` (feat)
2. **Task 2: Seed plans table in e2e test setup** - `2d63738` (feat)

## Files Created/Modified
- `migrations/20260322_01_initial-release.sql` - Single merged migration with 7 tables in FK order, REFERENCES constraints, and seed data
- `app/models.py` - User.plan and Subscription.plan now declare foreign_key="plans.tier"
- `tests/e2e/conftest.py` - ensure_tables fixture seeds plans after create_all for FK satisfaction

## Decisions Made
- Plans table created first in migration to satisfy FK dependency order
- Seed data (free/silver/gold/platinum) inserted directly in migration for production use
- E2E conftest uses ON CONFLICT DO NOTHING for idempotent re-seeding across test reruns

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Migration is clean and ready for deployment
- All 134 unit tests pass with no regressions
- E2E test infrastructure prepared for FK-constrained database

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 24-migration-merge*
*Completed: 2026-03-22*
