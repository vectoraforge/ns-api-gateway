---
phase: 23-envoy-gateway-rate-limiting
plan: 01
subsystem: database, api
tags: [sqlmodel, postgresql, rate-limiting, quota, migration]

# Dependency graph
requires:
  - phase: 22-apple-subscription-integration
    provides: Subscription/SubscriptionEvent models, PlanTier enum, users table
provides:
  - Plan and UsageMonthly SQLModel table models
  - UsageDB with atomic check-and-increment quota enforcement
  - QuotaExceededError (429/rate_limited) error contract
  - Extended UserProfileResponse with usage fields
  - Migration for plans seed data and usage_monthly table
  - Project renamed to ns-api-gateway v1.5.0
affects: [23-02, 23-03, chat-service-quota-integration, subscription-service-usage-reset]

# Tech tracking
tech-stack:
  added: []
  patterns: [atomic-upsert-with-conditional-update, lazy-row-creation-on-conflict]

key-files:
  created:
    - app/database/usage_db.py
    - migrations/20260321_01_add-plans-and-usage.sql
  modified:
    - app/models.py
    - app/exceptions.py
    - app/api/errors.py
    - app/api/schema.py
    - app/database/__init__.py
    - pyproject.toml
    - app/api/main.py

key-decisions:
  - "Atomic quota check uses INSERT ON CONFLICT DO NOTHING + conditional UPDATE FROM plans for race-safe increment"
  - "Project renamed from sn-api-gateway to ns-api-gateway to match NativeSpeaker branding"
  - "429 removed from _STATUS_REMAP so QuotaExceededError flows through as native 429 instead of being remapped to 503"

patterns-established:
  - "Lazy row creation: INSERT ON CONFLICT DO NOTHING before conditional UPDATE for usage tracking"
  - "Raw SQL in UsageDB for multi-table atomic operations that SQLModel ORM cannot express"

requirements-completed: [ENVOY-05]

# Metrics
duration: 3min
completed: 2026-03-22
---

# Phase 23 Plan 01: Quota Data Layer Summary

**Plan/UsageMonthly models, UsageDB with atomic quota enforcement, 429/rate_limited error contract, project rename to ns-api-gateway v1.5.0**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-22T01:25:38Z
- **Completed:** 2026-03-22T01:28:51Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Plan and UsageMonthly SQLModel tables with migration and seed data for 4 tier quotas (free:150, silver:1500, gold:3000, platinum:30000)
- UsageDB class with atomic try_increment (INSERT ON CONFLICT + conditional UPDATE FROM plans), get_usage, get_monthly_limit, reset_usage
- Error contract expanded: QuotaExceededError returns 429/rate_limited; 429 no longer remapped to 503
- UserProfileResponse extended with requests_used, monthly_limit, resets_at fields
- Project renamed from sn-api-gateway to ns-api-gateway v1.5.0 with NativeSpeaker branding

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Plan and UsageMonthly models, migration, error contract expansion, schema extension** - `c8e0e01` (feat)
2. **Task 2: Create UsageDB class, update database package, rename project** - `d1662c9` (feat)

## Files Created/Modified
- `app/models.py` - Added Plan and UsageMonthly SQLModel table classes with UniqueConstraint
- `app/exceptions.py` - Added rate_limited to ErrorCode Literal, added QuotaExceededError class
- `app/api/errors.py` - Removed 429->503 remap, added 429 to _CODE_MAP
- `app/api/schema.py` - Extended UserProfileResponse with requests_used, monthly_limit, resets_at
- `migrations/20260321_01_add-plans-and-usage.sql` - Migration creating plans (with seed) and usage_monthly tables
- `app/database/usage_db.py` - New UsageDB class with atomic quota operations
- `app/database/__init__.py` - Added UsageDB to package re-exports
- `pyproject.toml` - Renamed to ns-api-gateway v1.5.0
- `app/api/main.py` - Updated title to NativeSpeaker API Gateway, added 429 response

## Decisions Made
- Atomic quota check uses INSERT ON CONFLICT DO NOTHING + conditional UPDATE FROM plans for race-safe increment
- Project renamed from sn-api-gateway to ns-api-gateway to match NativeSpeaker branding
- 429 removed from _STATUS_REMAP so QuotaExceededError flows through as native 429 instead of being remapped to 503

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan/UsageMonthly models and UsageDB ready for ChatService and SubscriptionService integration in Plan 02
- Error contract expanded for quota enforcement middleware in Plan 03
- Migration ready for deployment

## Self-Check: PASSED

All 9 files verified present. Both task commits (c8e0e01, d1662c9) verified in git log.

---
*Phase: 23-envoy-gateway-rate-limiting*
*Completed: 2026-03-22*
