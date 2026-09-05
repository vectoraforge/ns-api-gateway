---
phase: 44-post-webhooks-google-play-rtdn
plan: 01
subsystem: payments
tags: [google-play, pubsub, rtdn, oidc, jwt, fastapi, httpx, google-auth, subscriptions]

requires:
  - phase: 43-post-webhooks-app-store
    provides: SubscriptionsService.ingest, SubscriptionsDB, the value type and the App Store seam
provides:
  - "POST /webhooks/google-play/rtdn, verified by a Google-signed Pub/Sub OIDC token"
  - "auth/store_notifications.py — VerifiedNotification, now carrying status and tier_id"
  - "auth/google_play.py — PubSubPushTokens, PlayDeveloperSubscriptions, PlaySubscriptionSource, the Play and RTDN models"
  - "GooglePlayConfig and AppConfig.google_play"
  - "The provider-callback partition at two exact paths, each declaring its own verifier first"
affects: [44-02, 44-03, 44-04, 44-05, 44-06, 44-07, 45-restore-subscription]

actuals:
  tokens: 21878
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "The two-class dependency: one Pub/Sub token class and one Play read class behind one verifier"
    - "Each provider class owns its store status word and its product map; the service writes both"
    - "The replay key for a store with no delivery id is derived from the payload itself"

key-files:
  created:
    - src/nativespeaker/api/auth/store_notifications.py
    - src/nativespeaker/api/auth/google_play.py
    - tests/e2e/test_google_play_webhook.py
  modified:
    - src/nativespeaker/api/auth/app_store.py
    - src/nativespeaker/api/auth/jwt_verifier.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/routers/webhooks.py
    - src/nativespeaker/api/services/subscriptions.py
    - src/nativespeaker/api/schemas/webhooks.py
    - src/nativespeaker/api/config.py
    - tests/e2e/conftest.py
    - tests/unit/test_app_wiring.py

key-decisions:
  - "OQ-4: the Google replay key is the payload-derived composite google_play:{purchaseToken}:{eventTimeMillis}:{notificationType}, chosen by the user at the plan's checkpoint"
  - "VerifiedNotification carries tier_id as str | None, absent exactly when product_id is absent, because a notification with no transaction part names no product"
  - "instant_from_millis and notification_key_for are public names, because the dependency in another module calls them"
  - "verify_google_play_notification declares no evaluated_at parameter; the Play class takes a clock source, because the Protocol read() carries no instant"

patterns-established:
  - "Provider seam: the class on app.state resolves the store status and the tier, and the service writes what the value type carries"
  - "Each callback route declares its own verifier as parameter 0, asserted by a flattened resolution walk against get_db"

requirements-completed: []

coverage:
  - id: D1
    description: "One Cloud Pub/Sub push with a Google-signed OIDC token becomes one committed core.subscriptions row for google_play, through the unforked Phase 43 service"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#test_a_verified_push_writes_the_subscription_row"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#test_the_play_read_asked_for_the_configured_package_and_this_token"
        status: pass
    human_judgment: false
  - id: D2
    description: "The delivery records exactly one audit.subscription_events row under the payload-derived composite key"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#test_the_delivery_records_exactly_one_event_under_the_composite_key"
        status: pass
    human_judgment: false
  - id: D3
    description: "The Google path reaches SubscriptionsService.ingest unchanged rather than a forked copy"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py#test_the_service_imports_no_apple_store_library_name"
        status: pass
      - kind: schema
        ref: "uv run pytest -m schema -q (189 passed)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The provider-callback partition counts two exact paths, each declaring its own verifier as dependency element 0, resolving before get_db"
    requirement: "PLAYHOOK-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#test_the_verifier_is_the_routes_first_declared_dependency"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#test_the_verifier_resolves_before_any_session_is_taken"
        status: pass
    human_judgment: false
  - id: D5
    description: "A deployment with no Play configuration still boots, still registers both callback routes, and answers 503 on use"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#test_an_unconfigured_deployment_answers_503"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#test_both_callback_routes_are_registered_while_the_seam_is_unconfigured"
        status: pass
    human_judgment: false
  - id: D6
    description: "An unreachable JWKS endpoint at boot yields a None verifier and one warning, never a raised lifespan"
    verification: []
    human_judgment: true
    rationale: "build_google_push_verifier is written with the guard and read, but no case drives an unreachable JWKS through it yet; plan 44-03 executes that arm."
  - id: D7
    description: "The status written comes from the store's own word, and each provider resolves its own tier: status_at and the service's products argument are deleted"
    verification:
      - kind: unit
        ref: "tests/unit/test_subscription_attribution.py#test_the_status_written_is_the_one_the_notification_carries"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py#test_the_status_and_the_tier_are_resolved_in_this_seam"
        status: pass
    human_judgment: false

duration: 64min
completed: 2026-09-05
status: complete
---

# Phase 44 Plan 01: The Google Play RTDN tracer Summary

**One Cloud Pub/Sub push with a Google-signed OIDC token now becomes one committed `core.subscriptions` row for `google_play`, through the Phase 43 service, with the value type promoted out of the Apple module and each provider owning its own status word and product map.**

## Performance

- **Duration:** 64 min
- **Started:** 2026-09-05T10:00:57Z
- **Completed:** 2026-09-05T11:05:00Z
- **Tasks:** 2 (plus the resolved decision checkpoint)
- **Files modified:** 21 (3 created)

## Accomplishments

- `POST /webhooks/google-play/rtdn` ships end to end: the push token is verified against Google's keys through the existing `JWTVerifier`, the RTDN is decoded only after that check, `purchases.subscriptionsv2.get` supplies every written value, and the row is committed before the 200.
- `VerifiedNotification` moved to `auth/store_notifications.py` carrying `status` and `tier_id`, and lost `revoked_at` and `in_billing_retry`, which had no readers once the date-derived status was deleted.
- `status_at` and the service's `products` argument are gone: `services/subscriptions.py` now writes the word the provider class resolved, so no date comparison decides entitlement any more.
- The provider-callback partition is two exact paths with one verifier each, and the wiring test now asserts the resolution order D-02 asks for rather than assuming it.
- `JWTVerifier` gained an optional `required_claims` pin and an optional `payload` field, with the tuple arity unchanged: `tests/unit/test_jwks_offload.py` is byte-unchanged in this plan's diff.

## Task Commits

1. **Task 1 (tracer, RED): the failing end-to-end case** - `270e94c` (test)
2. **Task 1 (tracer, GREEN): the Google Play callback end to end** - `e28cb96` (feat)
3. **Task 2: the inherited suite re-greened** - `8baf44a` (test)

**Plan metadata:** see the `docs(44-01)` commit that follows this file.

## Files Created/Modified

- `src/nativespeaker/api/auth/store_notifications.py` - the shared value type both providers fill
- `src/nativespeaker/api/auth/google_play.py` - the push-token class, the Play read class, the Protocol, the Play and RTDN models, the state map
- `src/nativespeaker/api/auth/app_store.py` - imports the value type, maps Apple's five statuses, resolves its own tier
- `src/nativespeaker/api/auth/jwt_verifier.py` - optional `required_claims` and the pinned payload
- `src/nativespeaker/api/app/lifespan.py` - `build_google_push_verifier` with the JWKS warm-up guard, `_play_credential`, the Play client, both `app.state` classes
- `src/nativespeaker/api/app/dependencies.py` - `verify_google_play_notification`; `get_subscriptions_service` drops `products`
- `src/nativespeaker/api/routers/webhooks.py` - no router-level gate; the second route
- `src/nativespeaker/api/services/subscriptions.py` - `status_at` deleted, `products` dropped, the superseded line raised to WARNING
- `src/nativespeaker/api/schemas/webhooks.py` - `PubSubPushMessage` and `PubSubPushRequest`
- `src/nativespeaker/api/config.py` - `GooglePlayConfig`, `AppConfig.google_play`
- `tests/e2e/test_google_play_webhook.py` - the end-to-end proof against the real seam classes
- `tests/e2e/conftest.py` - `real_google_play_seam` and `unconfigured_google_play_seam`
- `tests/unit/test_app_wiring.py` - `PROVIDER_CALLBACK_VERIFIERS` and the two ordering cases
- `tests/unit/test_auth_package_shape.py`, `tests/unit/test_app_store_notifications.py`, `tests/unit/test_subscription_attribution.py`, `tests/unit/test_jwt_security.py`, `tests/e2e/test_app_store_webhook.py`, `tests/schema/test_subscription_ingestion.py`, `tests/schema/test_subscription_race.py`, `tests/schema/test_grant_locks.py` - re-greened against the promoted value type

## Decisions Made

- **OQ-4, the Google replay key: `composite`.** `notification_uuid` on the Google path is the literal string `google_play:{purchaseToken}:{eventTimeMillis}:{notificationType}`. The user selected it at the plan's blocking checkpoint. It is derived from the RTDN body alone, so it dedupes both a Pub/Sub redelivery and a Play republish of the same event without relying on any Google delivery-id guarantee; the `google_play:` prefix keeps Google keys from colliding with Apple `notificationUUID` values in the shared `audit.subscription_events.notification_uuid` UNIQUE index; and it stays readable in a database row during an incident. `message.messageId` is not used, and the components are not hashed.
- **`tier_id` is `str | None` on the value type.** It is absent exactly when `product_id` is absent, which is the Apple test-or-summary notification the service already returns on. A fabricated empty string would be a value that could reach a foreign key.
- **A no-transaction notification carries `status = expired`.** The word must exist, and the non-granting one is the only safe stand-in for "this delivery states nothing about entitlement".
- **The Apple seam raises `InternalError` when `data.status` names no member of Apple's own enum** (OQ-2 stands unverified), so Apple retries and the case is visible rather than falling back to a date.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tests/schema/test_subscription_race.py` and `tests/schema/test_grant_locks.py` construct the value type**
- **Found during:** Task 2
- **Issue:** Both files import the schema suite's `_notification` factory and build `SubscriptionsService(products=...)`. Neither is named in the plan's `files_modified`, and both errored at collection after the value type moved.
- **Fix:** Passed `tier_id` through the factory call and dropped the `products` argument, exactly as in the two files the plan does name.
- **Files modified:** tests/schema/test_subscription_race.py, tests/schema/test_grant_locks.py
- **Verification:** `uv run pytest -m schema -q` — 189 passed
- **Committed in:** `8baf44a`

**2. [Rule 3 - Blocking] `tests/unit/test_jwt_security.py` pins the `VerifiedClaims` field set**
- **Found during:** Task 2
- **Issue:** `test_carries_exactly_issuer_and_subject` asserts the dataclass fields are exactly `["issuer", "subject"]`, which D-09's optional `payload` field breaks. The file is not in the plan's `files_modified`.
- **Fix:** Widened the case to the three fields and asserted `payload is None` for a caller that pinned no claim, which is what keeps the Firebase path unchanged.
- **Files modified:** tests/unit/test_jwt_security.py
- **Verification:** `uv run pytest tests/unit/test_jwt_security.py -q` — 46 passed
- **Committed in:** `8baf44a`

**3. [Rule 2 - Missing critical] The two no-write arms of D-04 and D-05 were built now, not deferred**
- **Found during:** Task 1
- **Issue:** The plan puts `developer_notification_from` inside a `try` but leaves its failure arm, and D-05's non-subscription body, to plan 44-03. Without either, an undecodable body or a `testNotification` — the first message a real Pub/Sub subscription sends — raises an unhandled exception, which Pub/Sub redelivers until retention expires.
- **Fix:** Both arms return `None`, the dependency returns `None`, and the handler answers 200 having written nothing. D-05 is implemented as a presence test on `subscriptionNotification`, never as a list of body names. Neither arm grants anything. Plan 44-03's tests still execute both.
- **Files modified:** src/nativespeaker/api/auth/google_play.py, src/nativespeaker/api/app/dependencies.py
- **Verification:** `uv run pytest -m e2e tests/e2e/test_google_play_webhook.py -q` — 5 passed; the arms themselves are covered by plan 44-03
- **Committed in:** `e28cb96`

### Deliberate departures from the written plan

**4. `_instant_from_millis` and `_notification_key` ship as `instant_from_millis` and `notification_key_for`.** The plan lists both with a leading underscore, but `app/dependencies.py` calls both — the underscore names a module-private symbol, and importing one from another module contradicts it.

**5. `verify_google_play_notification` declares no `evaluated_at` parameter.** The plan's signature includes `evaluated_at: datetime = Depends(get_evaluated_at)`, but `PlaySubscriptionSource.read` — whose signature the plan pins — carries no instant, so the parameter would have been read by nothing. The Play class takes an `evaluated_at_source` instead, which `lifespan` fills with `get_evaluated_at`.

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing critical) and 2 documented departures.
**Impact on plan:** No scope creep. The two blocking fixes are the same mechanical edit the plan already prescribes for four other files; the missing-critical fix closes a redelivery loop that the first real `testNotification` would have opened.

## Issues Encountered

None.

## User Setup Required

None in this plan. The deployment values `GOOGLE_PLAY_PACKAGE_NAME`, `GOOGLE_PLAY_PUSH_AUDIENCE`, `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL` and the `google_play.products` map are documented by plan 44-04; until they are supplied the route answers 503 and the boot log carries one `google_play_configuration_absent` warning.

## Known Stubs

- `src/nativespeaker/api/auth/google_play.py` `_STATES` holds one state, `SUBSCRIPTION_STATE_ACTIVE`, and `grace_period_expires_at` is always `None`. This is the tracer's declared boundary: plan 44-03 fills the remaining eight states and the grace window. The fall-through is `SubscriptionStatus.expired`, so no unlisted state grants anything.
- `PlayDeveloperSubscriptions.read` treats every non-2xx Play status the same, as an `InternalError` that Pub/Sub redelivers. The `404`/`410` arm is plan 44-03's (OQ-5).

## Threat Flags

None. Every surface this plan adds is in the plan's own threat register: the push-token check (T-44-01), the post-verification decode and the `packageName` comparison (T-44-02), the composite replay key (T-44-03), and the JWKS warm-up guard (T-44-06).

## Next Phase Readiness

- Plan 44-02 (`google-auth` as a direct dependency) and plan 44-04 (configuration and environment) are unblocked and touch no code this plan wrote.
- Plan 44-03 expands `auth/google_play.py` from the proven slice: the nine states, the grace window, and the arms listed under Known Stubs.
- Plan 45 consumes `PlaySubscriptionSource` and `PlayDeveloperSubscriptions` with no Pub/Sub token, which is why D-08's two classes are separate here.

---
*Phase: 44-post-webhooks-google-play-rtdn*
*Completed: 2026-09-05*

## Self-Check: PASSED

- Every created file exists on disk: `auth/store_notifications.py`, `auth/google_play.py`, `tests/e2e/test_google_play_webhook.py`, this summary.
- Every task commit exists in `git log`: `270e94c`, `e28cb96`, `8baf44a`.
- Every `coverage[].ref` names a case that exists in the file it names.
- Plan verification re-run at close: `uv run pytest -q` 1105 passed, `uv run pytest -m e2e -q` 277 passed, `uv run pytest -m schema -q` 189 passed, `uv run ruff check src tests` clean, and `tests/unit/test_jwks_offload.py` is unchanged in `git diff dd8863b..HEAD`.
