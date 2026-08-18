---
phase: 22-apple-subscription-integration
plan: 02
subsystem: api
tags: [apple-subscriptions, firebase, fastapi, webhooks, jws-verification]

# Dependency graph
requires:
  - phase: 22-apple-subscription-integration/01
    provides: Subscription/SubscriptionEvent models, SubscriptionDB, AppleConfig, WebhookVerificationError
provides:
  - FirebaseService with non-blocking set_plan_claim via asyncio.to_thread
  - SubscriptionService with full Apple notification lifecycle processing
  - create_apple_verifier factory for SignedDataVerifier initialization
  - POST /webhooks/apple endpoint (no JWT auth)
  - get_subscription_service FastAPI dependency
  - Firebase Admin SDK and Apple verifier initialization in lifespan
affects: [22-03 tests]

# Tech tracking
tech-stack:
  added: []
  patterns: [best-effort Firebase sync with warning log, match-case lifecycle mapping, appAccountToken as user UUID]

key-files:
  created: [app/services/firebase_service.py, app/services/subscription_service.py, app/routers/webhooks.py]
  modified: [app/services/__init__.py, app/routers/__init__.py, app/api/dependencies.py, app/api/main.py]

key-decisions:
  - "appAccountToken from Apple transaction used as user UUID for new subscription creation"
  - "Firebase sync is best-effort: failure logs warning but does not block webhook response"
  - "DID_CHANGE_RENEWAL_PREF with DOWNGRADE subtype returns None status (deferred to next renewal)"

patterns-established:
  - "Best-effort external service sync: catch all exceptions, log warning, continue"
  - "match-case for Apple notification lifecycle mapping"

requirements-completed: [SUBS-01, SUBS-02, SUBS-03, SUBS-06, SUBS-07]

# Metrics
duration: 5min
completed: 2026-03-20
---

# Phase 22 Plan 02: Service Layer and Webhook Router Summary

**SubscriptionService with Apple JWS verification and lifecycle mapping, FirebaseService with async claim sync, POST /webhooks/apple endpoint wired via DI**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-20T22:06:27Z
- **Completed:** 2026-03-20T22:11:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- FirebaseService with non-blocking set_plan_claim using asyncio.to_thread (SUBS-07)
- SubscriptionService with full Apple notification pipeline: JWS verification, lifecycle mapping, idempotent event insertion, user plan update, Firebase claim sync
- Lifecycle mapping covers SUBSCRIBED, DID_RENEW, DID_FAIL_TO_RENEW (grace_period/billing_retry), EXPIRED, REVOKE, DID_CHANGE_RENEWAL_PREF (upgrade/downgrade-deferred)
- POST /webhooks/apple endpoint without JWT auth, returning 200 on success and 400 on invalid JWS
- Firebase Admin SDK and Apple verifier initialized in lifespan, stored on app.state
- get_subscription_service dependency in app/api/dependencies.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Create FirebaseService and SubscriptionService** - `53e0604` (feat)
2. **Task 2: Create webhooks router, add dependency, wire into app** - `c63ff1c` (feat)

## Files Created/Modified
- `app/services/firebase_service.py` - FirebaseService wrapping firebase-admin auth.set_custom_user_claims with asyncio.to_thread
- `app/services/subscription_service.py` - SubscriptionService with process_apple_notification pipeline and create_apple_verifier factory
- `app/services/__init__.py` - Exported FirebaseService, SubscriptionService, create_apple_verifier
- `app/routers/webhooks.py` - POST /webhooks/apple endpoint with no JWT auth
- `app/routers/__init__.py` - Exported webhooks_router
- `app/api/dependencies.py` - Added get_subscription_service dependency
- `app/api/main.py` - Firebase Admin SDK init, Apple verifier init, webhooks_router registration

## Decisions Made
- appAccountToken from Apple transaction is used directly as user UUID for new subscription creation (set at purchase time by iOS client)
- Firebase sync is best-effort: exceptions caught and logged as warning, webhook still returns 200
- DID_CHANGE_RENEWAL_PREF with DOWNGRADE subtype returns None status (no immediate action, deferred to next renewal)
- Ignored notification types: TEST, CONSUMPTION_REQUEST, REFUND_DECLINED, PRICE_INCREASE, RENEWAL_EXTENDED, EXTERNAL_PURCHASE_TOKEN, ONE_TIME_CHARGE

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed import ordering in app/api/main.py**
- **Found during:** Task 2 (wire into app)
- **Issue:** firebase_admin import placed after local imports, breaking PEP8 import ordering
- **Fix:** Moved firebase_admin and credentials imports to the third-party section before local imports
- **Files modified:** app/api/main.py
- **Committed in:** c63ff1c (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor import ordering fix. No scope creep.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required. Firebase credentials and Apple root CA certificates are deployment-time concerns (documented in blockers).

## Next Phase Readiness
- Service layer and webhook endpoint complete for Plan 03 (tests)
- All imports verified working
- SubscriptionService ready to be tested with mocked SignedDataVerifier

## Self-Check: PASSED

All 7 files verified present. Both task commits (53e0604, c63ff1c) verified in git log.

---
*Phase: 22-apple-subscription-integration*
*Completed: 2026-03-20*
