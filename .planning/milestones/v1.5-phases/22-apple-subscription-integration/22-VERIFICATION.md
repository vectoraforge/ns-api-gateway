---
phase: 22-apple-subscription-integration
verified: 2026-03-20T22:45:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 22: Apple Subscription Integration Verification Report

**Phase Goal:** Apple subscription integration — webhook endpoint, JWS verification, lifecycle mapping, idempotent processing, Firebase claim sync
**Verified:** 2026-03-20
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All truths derived from plan must_haves and ROADMAP success criteria.

| #  | Truth                                                                                    | Status     | Evidence                                                                 |
|----|------------------------------------------------------------------------------------------|------------|--------------------------------------------------------------------------|
| 1  | Subscription and SubscriptionEvent models exist with correct fields and constraints      | VERIFIED   | `app/models.py` lines 116-149; partial unique index on (user_id, provider) WHERE status NOT IN ('expired', 'revoked') present |
| 2  | SubscriptionDB provides idempotent event insertion via ON CONFLICT DO NOTHING            | VERIFIED   | `app/database/subscriptions_db.py` lines 61-80; `.on_conflict_do_nothing(index_elements=["notification_uuid"])` confirmed |
| 3  | AppConfig includes Apple environment, bundle_id, and product-to-tier mapping             | VERIFIED   | `app/config.py` lines 61-84; `AppConfig.apple: AppleConfig` field present; `config/config.yaml` has `apple:` section with `product_id_to_tier` |
| 4  | Migration SQL creates subscriptions and subscription_events tables with correct indexes  | VERIFIED   | `migrations/20260317_01_bvi4l-initial-release.sql` lines 36-71; both tables, 3 indexes, rollback DROP statements confirmed |
| 5  | POST /webhooks/apple receives and acknowledges Apple notifications with HTTP 200         | VERIFIED   | `app/routers/webhooks.py` line 10; `@router.post("/webhooks/apple", status_code=200)`; returns `Response(status_code=200)` |
| 6  | Invalid JWS signatures are rejected with HTTP 400 before any state mutation              | VERIFIED   | `app/services/subscription_service.py` lines 72-75; `VerificationException` caught and re-raised as `WebhookVerificationError`; tests confirm 400 |
| 7  | Subscription lifecycle events map to correct status and plan tier                        | VERIFIED   | `subscription_service.py` lines 170-197; match-case covers SUBSCRIBED, DID_RENEW, DID_FAIL_TO_RENEW (grace/billing_retry), EXPIRED, REVOKE, DID_CHANGE_RENEWAL_PREF |
| 8  | Plan changes sync to Firebase custom claims via asyncio.to_thread                       | VERIFIED   | `app/services/firebase_service.py` lines 14-15; `await asyncio.to_thread(auth.set_custom_user_claims, ...)` confirmed |
| 9  | Firebase sync failure does not prevent webhook from returning 200                        | VERIFIED   | `firebase_service.py` lines 17-19; `except Exception: logger.warning(...)` swallows all errors |
| 10 | Duplicate notifications are silently ignored (idempotency on notificationUUID)          | VERIFIED   | `subscription_service.py` lines 140-150; `if not inserted: return` after `insert_event_idempotent` returns False |
| 11 | User plan tier stored in local DB after each subscription event                          | VERIFIED   | `subscription_service.py` lines 136-138, 155-157; `update_user_plan` called for both new and existing subscriptions |
| 12 | Unit tests cover all SUBS requirements and pass                                          | VERIFIED   | 21 tests in test_webhooks.py + test_subscriptions.py; 125 total unit tests pass |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact                                    | Expected                                               | Status     | Details                                                  |
|---------------------------------------------|--------------------------------------------------------|------------|----------------------------------------------------------|
| `app/models.py`                             | SubscriptionProvider, SubscriptionStatus enums; Subscription, SubscriptionEvent models | VERIFIED | Both enums and both table models present; partial unique index confirmed |
| `app/config.py`                             | AppleConfig with environment, bundle_id, product_id_to_tier; AppConfig.apple field | VERIFIED | Lines 61-84; all fields present |
| `app/database/subscriptions_db.py`          | SubscriptionDB with idempotent event insertion         | VERIFIED   | All 5 methods present: get_by_external_id, create, update, insert_event_idempotent, update_user_plan |
| `config/config.yaml`                        | Apple config section                                   | VERIFIED   | Lines 20-27; apple section with product_id_to_tier mapping |
| `migrations/20260317_01_bvi4l-initial-release.sql` | Subscription tables DDL                          | VERIFIED   | Both tables, all indexes, rollback statements |
| `app/services/firebase_service.py`          | FirebaseService wrapping firebase-admin                | VERIFIED   | asyncio.to_thread confirmed; best-effort exception handling |
| `app/services/subscription_service.py`      | SubscriptionService with full lifecycle mapping        | VERIFIED   | process_apple_notification, _map_lifecycle_event, create_apple_verifier all present |
| `app/routers/webhooks.py`                   | POST /webhooks/apple without JWT auth                  | VERIFIED   | No get_current_user dependency; uses get_subscription_service |
| `app/api/main.py`                           | Firebase init in lifespan, webhooks_router registered  | VERIFIED   | Lines 43-47, 74 |
| `app/api/dependencies.py`                   | get_subscription_service dependency                    | VERIFIED   | Lines 39-47; uses apple_verifier and firebase_service from app.state |
| `tests/unit/test_webhooks.py`               | TestAppleWebhook class with endpoint tests             | VERIFIED   | 5 tests covering SUBS-01 and SUBS-02 |
| `tests/unit/test_subscriptions.py`          | TestSubscriptionLifecycle, TestIdempotency, TestPlanTierUpdate, TestFirebaseSync | VERIFIED | 16 tests covering SUBS-03 through SUBS-07 |

---

### Key Link Verification

| From                                      | To                                       | Via                                             | Status  | Details                                                          |
|-------------------------------------------|------------------------------------------|-------------------------------------------------|---------|------------------------------------------------------------------|
| `app/database/subscriptions_db.py`        | `app/models.py`                          | imports Subscription, SubscriptionEvent, SubscriptionStatus | WIRED  | Line 8-15; all 6 models/enums imported |
| `app/config.py`                           | `app/models.py`                          | imports PlanTier for product mapping type       | NOT WIRED (not needed) | AppleConfig uses `dict[str, str]` — no PlanTier import required; product_id_to_tier values are strings validated at service layer. Not a gap. |
| `app/routers/webhooks.py`                 | `app/services/subscription_service.py`  | Depends(get_subscription_service)               | WIRED  | Line 12; `Depends(get_subscription_service)` confirmed |
| `app/services/subscription_service.py`   | `app/services/firebase_service.py`       | calls firebase_service.set_plan_claim           | WIRED  | Line 166; `await self.firebase_service.set_plan_claim(user.jwt_sub, plan_tier)` |
| `app/services/subscription_service.py`   | `app/database/subscriptions_db.py`       | self.subscriptions_db methods                   | WIRED  | Line 65; `self.subscriptions_db = SubscriptionDB(db)`; all methods called |
| `app/api/main.py`                         | `app/routers/webhooks.py`                | app.include_router(webhooks_router)             | WIRED  | Line 74 confirmed |
| `tests/unit/test_webhooks.py`             | `app/routers/webhooks.py`                | TestClient POST /webhooks/apple                 | WIRED  | `webhook_client.post("/webhooks/apple", ...)` confirmed |
| `tests/unit/test_subscriptions.py`        | `app/services/subscription_service.py`  | SubscriptionService.process_apple_notification  | WIRED  | `await subscription_service.process_apple_notification(...)` confirmed |

Note on config.py → models.py link: The plan specified `from app.models import PlanTier` but the actual implementation uses `dict[str, str]` for `product_id_to_tier` with string-to-string mapping. PlanTier validation occurs at the service layer. This is a valid design choice and does not represent a gap.

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                              | Status    | Evidence                                                                   |
|-------------|-------------|------------------------------------------------------------------------------------------|-----------|----------------------------------------------------------------------------|
| SUBS-01     | 22-02, 22-03 | App receives Apple Store Server Notifications V2 via POST /webhooks/apple               | SATISFIED | `app/routers/webhooks.py`; 5 tests in test_webhooks.py; all passing        |
| SUBS-02     | 22-02, 22-03 | Apple notifications verified using JWS signature chain (app-store-server-library)       | SATISFIED | `subscription_service.py` lines 72-75; VerificationException -> 400; test_invalid_jws_rejected passes |
| SUBS-03     | 22-02, 22-03 | Webhook processes full subscription lifecycle (active, grace, billing retry, expired, revoked) | SATISFIED | _map_lifecycle_event covers all 5 statuses; 8 lifecycle tests pass |
| SUBS-04     | 22-01, 22-03 | Duplicate Apple notifications safely ignored (idempotency on notificationUUID)          | SATISFIED | ON CONFLICT DO NOTHING in subscriptions_db; test_duplicate_notification_ignored passes |
| SUBS-05     | 22-01, 22-03 | User plan tier stored in local DB as authoritative source                                | SATISFIED | update_user_plan called in both new/existing subscription paths; test_plan_updated_on_subscription_change passes |
| SUBS-06     | 22-02, 22-03 | Plan changes sync to Firebase custom claims for JWT propagation                          | SATISFIED | firebase_service.set_plan_claim called when old_tier != plan_tier; test_firebase_sync_on_tier_change passes |
| SUBS-07     | 22-02, 22-03 | Firebase claim sync does not block event loop (asyncio.to_thread())                     | SATISFIED | asyncio.to_thread confirmed in firebase_service.py; test_uses_to_thread and test_firebase_failure_does_not_raise pass |

All 7 SUBS requirements satisfied. REQUIREMENTS.md confirms Phase 22 status as Complete for all.

---

### Anti-Patterns Found

None. Scanned all phase-modified files (`app/models.py`, `app/config.py`, `app/database/subscriptions_db.py`, `app/services/firebase_service.py`, `app/services/subscription_service.py`, `app/routers/webhooks.py`, `app/api/main.py`, `app/api/dependencies.py`) — zero TODO/FIXME/HACK/placeholder comments, no empty return stubs, no hardcoded empty arrays/objects flowing to user-visible output.

---

### Human Verification Required

| Test | What to Do | Expected | Why Human |
|------|-----------|----------|-----------|
| Apple JWS end-to-end | Send a real Apple Store Server Notification V2 (sandbox environment) to POST /webhooks/apple | HTTP 200, subscription record created in DB, Firebase custom claim updated | Requires Apple developer account, sandbox IAP product, real JWS token |
| Firebase claim propagation | After a subscription event, verify Firebase ID token contains updated `plan` custom claim | Token's `plan` claim reflects new tier within Firebase cache TTL | Requires real Firebase project and credentials |
| Certificate loading | Start the app with Apple root CA certificates in `certs/` directory | App starts without error; create_apple_verifier succeeds | Certificate files are deployment-time concern, not in repo |

---

### Test Suite Results

```
tests/unit/test_webhooks.py   5 tests    PASSED
tests/unit/test_subscriptions.py  16 tests  PASSED
Full unit suite (125 tests)   PASSED (including pre-existing test_config.py)
```

All 6 task commits verified in git history:
- `c10d4c2` feat(22-01): subscription models, enums, dependencies
- `1953e32` feat(22-01): AppleConfig, WebhookVerificationError, SubscriptionDB, migration
- `53e0604` feat(22-02): FirebaseService and SubscriptionService
- `c63ff1c` feat(22-02): webhooks router, subscription dependency, wire into app
- `ffb2208` test(22-03): webhook endpoint tests (SUBS-01/02)
- `83104c6` test(22-03): subscription service tests (SUBS-03 through SUBS-07)

---

## Summary

Phase 22 goal is fully achieved. All seven SUBS requirements have implementation evidence and passing unit tests. The Apple subscription integration pipeline is complete end-to-end: incoming JWS payloads are verified by `app-store-server-library`, lifecycle events map to the correct `SubscriptionStatus` and `PlanTier`, events are inserted idempotently using a unique constraint on `notification_uuid`, user plan tiers are written to the local DB, and Firebase custom claims are synced asynchronously via `asyncio.to_thread` with best-effort failure handling. The webhook endpoint is correctly unauthenticated (no JWT requirement) and registered in the app lifespan.

Three human verification items remain for production validation (real Apple sandbox notification, Firebase claim propagation, certificate loading) — these are deployment-time concerns and do not block phase completion.

---

_Verified: 2026-03-20_
_Verifier: Claude (gsd-verifier)_
