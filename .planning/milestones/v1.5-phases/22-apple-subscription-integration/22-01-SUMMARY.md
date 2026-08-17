---
phase: 22-apple-subscription-integration
plan: 01
subsystem: database
tags: [sqlmodel, postgresql, apple-subscriptions, pydantic, config]

# Dependency graph
requires:
  - phase: 21-user-management
    provides: User model with PlanTier, session-in-init DB pattern, BaseTable
provides:
  - SubscriptionProvider and SubscriptionStatus StrEnums
  - Subscription and SubscriptionEvent SQLModel tables
  - SubscriptionDB with idempotent event insertion
  - AppleConfig with product_id_to_tier mapping
  - WebhookVerificationError exception
  - Migration DDL for subscriptions and subscription_events tables
affects: [22-02 service-and-router, 22-03 tests]

# Tech tracking
tech-stack:
  added: [app-store-server-library, firebase-admin]
  patterns: [partial unique index for active subscription constraint, idempotent event insertion via ON CONFLICT DO NOTHING]

key-files:
  created: [app/database/subscriptions_db.py]
  modified: [app/models.py, app/config.py, config/config.yaml, app/exceptions.py, app/database/__init__.py, migrations/20260317_01_bvi4l-initial-release.sql, pyproject.toml]

key-decisions:
  - "Partial unique index on (user_id, provider) WHERE status NOT IN ('expired', 'revoked') prevents duplicate active subscriptions"
  - "ON CONFLICT DO NOTHING on notification_uuid for idempotent webhook event processing"

patterns-established:
  - "SubscriptionDB follows session-in-init pattern established by ChatsDB/UsersDB"
  - "Partial unique index pattern for business-rule constraints at database level"

requirements-completed: [SUBS-04, SUBS-05]

# Metrics
duration: 4min
completed: 2026-03-20
---

# Phase 22 Plan 01: Subscription Data Foundation Summary

**Subscription/SubscriptionEvent SQLModel tables with partial unique index, SubscriptionDB with idempotent event insertion, AppleConfig with product-to-tier mapping**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-20T22:00:04Z
- **Completed:** 2026-03-20T22:03:38Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- SubscriptionProvider and SubscriptionStatus StrEnums with correct values
- Subscription model with partial unique index preventing duplicate active subscriptions per user/provider
- SubscriptionEvent model with unique notification_uuid for idempotent processing
- SubscriptionDB with full CRUD: get by external ID, create, update, idempotent event insert, user plan update
- AppleConfig with environment, bundle_id, cert_dir, and product_id_to_tier mapping
- WebhookVerificationError (400, validation_error) for JWS verification failures
- Migration SQL with subscriptions/subscription_events tables, indexes, and rollback

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies, add enums and models** - `c10d4c2` (feat)
2. **Task 2: Add AppleConfig, WebhookVerificationError, SubscriptionDB, migration** - `1953e32` (feat)

## Files Created/Modified
- `app/models.py` - Added SubscriptionProvider, SubscriptionStatus enums; Subscription, SubscriptionEvent models with partial unique index
- `app/config.py` - Added AppleConfig with environment, bundle_id, product_id_to_tier; added apple field to AppConfig
- `config/config.yaml` - Added apple section with sandbox defaults and product-to-tier mapping
- `app/exceptions.py` - Added WebhookVerificationError (400, validation_error)
- `app/database/subscriptions_db.py` - New SubscriptionDB with session-in-init pattern, idempotent event insertion
- `app/database/__init__.py` - Exported SubscriptionDB
- `migrations/20260317_01_bvi4l-initial-release.sql` - Added subscriptions and subscription_events DDL with indexes and rollback
- `pyproject.toml` - Added app-store-server-library and firebase-admin dependencies

## Decisions Made
- Partial unique index on (user_id, provider) WHERE status NOT IN ('expired', 'revoked') enforces one active subscription per provider per user at the database level
- ON CONFLICT DO NOTHING on notification_uuid provides idempotent webhook event processing without application-level dedup

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Data foundation complete for Plan 02 (service layer, Apple JWS verification, webhook router)
- Subscription models and DB operations ready to be consumed by AppleSubscriptionService
- AppleConfig available for signed payload verification

---
*Phase: 22-apple-subscription-integration*
*Completed: 2026-03-20*
