---
phase: 22-apple-subscription-integration
plan: 03
subsystem: testing
tags: [pytest, asyncmock, apple-subscriptions, webhooks, firebase, unit-tests]

# Dependency graph
requires:
  - phase: 22-apple-subscription-integration/02
    provides: SubscriptionService, FirebaseService, POST /webhooks/apple endpoint, get_subscription_service dependency
provides:
  - Unit tests for webhook endpoint (SUBS-01, SUBS-02)
  - Unit tests for subscription lifecycle mapping (SUBS-03)
  - Unit tests for idempotent event processing (SUBS-04)
  - Unit tests for user plan tier update (SUBS-05)
  - Unit tests for Firebase claim sync (SUBS-06, SUBS-07)
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [mock_subscriptions_db fixture replacing internal SubscriptionDB for isolated service testing, webhook_client fixture with dedicated FastAPI app for endpoint testing]

key-files:
  created: [tests/unit/test_webhooks.py, tests/unit/test_subscriptions.py]
  modified: [tests/unit/conftest.py]

key-decisions:
  - "Replace SubscriptionDB after construction via mock_subscriptions_db fixture rather than mocking session methods, for cleaner assertion access"
  - "Webhook tests use dedicated webhook_client fixture with isolated FastAPI app (no JWT auth dependency)"

patterns-established:
  - "mock_subscriptions_db fixture: AsyncMock replacing service.subscriptions_db post-construction for direct method assertion"
  - "webhook_client fixture: dedicated FastAPI app with only webhooks_router for isolated endpoint testing"

requirements-completed: [SUBS-01, SUBS-02, SUBS-03, SUBS-04, SUBS-05, SUBS-06, SUBS-07]

# Metrics
duration: 6min
completed: 2026-03-20
---

# Phase 22 Plan 03: Subscription Unit Tests Summary

**21 unit tests covering webhook endpoint validation (SUBS-01/02), lifecycle mapping (SUBS-03), idempotency (SUBS-04), plan tier update (SUBS-05), and Firebase sync (SUBS-06/07)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-20T22:14:44Z
- **Completed:** 2026-03-20T22:20:58Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- 5 webhook endpoint tests: receives notification (200), missing payload (400), empty payload (400), invalid JWS (400), no JWT auth required (200)
- 10 subscription lifecycle mapping tests: SUBSCRIBED, DID_RENEW, GRACE_PERIOD, billing_retry, EXPIRED, REVOKE, UPGRADE, DOWNGRADE deferred, unknown product defaults to free, ignored notification types
- 1 idempotency test: duplicate notification (insert_event returns False) does not call update_subscription
- 1 plan tier update test: subscription change calls update_user_plan with correct user_id and plan
- 4 Firebase sync tests: sync called on tier change, uses asyncio.to_thread, failure does not raise, no sync when tier unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: Create webhook endpoint tests** - `ffb2208` (test)
2. **Task 2: Create subscription service tests** - `83104c6` (test)

## Files Created/Modified
- `tests/unit/test_webhooks.py` - TestAppleWebhook class with 5 endpoint tests covering SUBS-01 and SUBS-02
- `tests/unit/test_subscriptions.py` - TestSubscriptionLifecycle, TestIdempotency, TestPlanTierUpdate, TestFirebaseSync classes with 16 tests covering SUBS-03 through SUBS-07
- `tests/unit/conftest.py` - Added mock_subscription_service, webhook_client, and updated imports for webhooks_router, SubscriptionService, get_subscription_service

## Decisions Made
- Used mock_subscriptions_db fixture (AsyncMock) replacing the internal SubscriptionDB after construction, rather than mocking session-level DB calls, for cleaner assertion access on service methods
- Webhook tests use a dedicated webhook_client fixture with an isolated FastAPI app containing only webhooks_router -- no JWT auth dependency leaking into webhook tests
- FirebaseService tests use `patch("app.services.firebase_service.asyncio.to_thread")` to verify SUBS-07 without real Firebase SDK

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mock pattern for SubscriptionDB internal attribute**
- **Found during:** Task 2 (subscription service tests)
- **Issue:** Plan assumed subscriptions_db methods would be directly mockable on the service, but SubscriptionService creates SubscriptionDB(db) internally, making its methods real functions not mocks
- **Fix:** Added mock_subscriptions_db fixture (AsyncMock) and replaced service.subscriptions_db post-construction for clean method assertion
- **Files modified:** tests/unit/test_subscriptions.py
- **Committed in:** 83104c6 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor mock wiring adjustment. No scope creep. All planned assertions preserved.

## Issues Encountered

Pre-existing failure in `tests/unit/test_config.py::test_main_config_loads_yaml_and_content` -- test YAML fixture missing required `apple` config fields added in Plan 01. Not caused by this plan's changes. Logged to `deferred-items.md`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All SUBS requirements (SUBS-01 through SUBS-07) now have unit test coverage
- Phase 22 (apple-subscription-integration) complete -- all 3 plans delivered
- Ready for Phase 23 (Envoy Gateway rate limiting)

## Self-Check: PASSED

All 3 files verified present. Both task commits (ffb2208, 83104c6) verified in git log. All acceptance criteria patterns found in target files.
