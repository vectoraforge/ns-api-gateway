---
phase: 43-post-webhooks-app-store
plan: 01
subsystem: payments
tags: [app-store-server-library, jws, x509, fastapi, sqlmodel, postgres, webhooks, subscriptions]

# Dependency graph
requires:
  - phase: 41-post-auth-claim-anonymous-grant
    provides: the class-plus-Protocol-plus-frozen-value seam (`auth/devicecheck.py`) and its scripted e2e fake
  - phase: 42-post-auth-claim-registered-grant
    provides: the SQLSTATE 23505 idiom read off `violation.orig.sqlstate`, and the flush-boundary shape
  - phase: 37.1-route-registry-deletion
    provides: the router-level dependency as the structural replacement for the deleted route registry
provides:
  - "`POST /webhooks/app-store`: an exact-path, credential-free route outside the auth dependency"
  - "The provider-callback partition: `routers/webhooks.py` plus `PROVIDER_CALLBACK_PATHS` as a literal"
  - "`AppStoreNotifications`, `StoreNotificationVerifier` (Protocol) and `VerifiedNotification`"
  - "`SubscriptionsDB` and `SubscriptionsService`: one transaction, one commit, one replay key"
  - "`AppStoreConfig` with a typed `StoreEnvironment`, and `app.state.app_store_notifications`"
  - "`Subscription`, `SubscriptionEvent` and `SubscriptionStatus` over the existing v2.0 tables"
affects: [44-webhook-google-play-rtdn, 45-restore-subscription, 43-02, 43-03, 43-04, 43-05, 43-06]

actuals:
  tokens: 21200
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "The provider-callback partition is the set of routes on one APIRouter, counted by one test literal"
    - "The admission gate is a body-taking router dependency, so verification precedes `get_db`"
    - "A store seam returns this project's frozen value type; no vendor type crosses into `services/`"

key-files:
  created:
    - src/nativespeaker/api/auth/app_store.py
    - src/nativespeaker/api/routers/webhooks.py
    - src/nativespeaker/api/schemas/webhooks.py
    - src/nativespeaker/api/crud/subscriptions.py
    - src/nativespeaker/api/services/subscriptions.py
    - tests/unit/test_app_store_notifications.py
    - tests/e2e/test_app_store_webhook.py
  modified:
    - src/nativespeaker/api/config.py
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/tables/purchases.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/app/main.py
    - tests/unit/test_app_wiring.py
    - tests/unit/test_users.py

key-decisions:
  - "A mid-term tier change updates `core.subscriptions.tier_id` in place rather than flipping and inserting; the unique index on (provider, external_id) allows exactly one row per lifecycle key, and the change is recorded in `audit.subscription_events.old_tier_id`/`new_tier_id`. Recorded per 43-CONTEXT.md Claude's Discretion; moot with one paid tier."
  - "The lost race raises the generic `InternalError` rather than a fourth error leaf, because the phase's artifact list fixes the new exception classes at `NotificationRejected`, `UnmappedStoreProduct` and 43-03's `AttributionConflict`."
  - "`WriteOutcome.replayed` is returned by `upsert_subscription` when the stored row already carries the same tier and status, so all three enum members have a producer without a second query."
  - "The crud outcome enum is named `WriteOutcome` (not `ActivationOutcome`, which is `crud/grants.py`'s and means something else) and lives beside `SubscriptionsDB`."
  - "`services/subscriptions.py` holds the D-22 INFO line and the lost-race WARNING; `auth/app_store.py` declares no logger at all."
  - "APPLEHOOK-01 and APPLEHOOK-02 are NOT marked complete by this plan — see Deviations."

patterns-established:
  - "Partition membership: an `APIRouter(dependencies=[Depends(gate)])` whose route set IS the closed category, with a literal set in `tests/unit/test_app_wiring.py` compared by `==`"
  - "Store seam: one class, one method, its Protocol beside it, a frozen dataclass out, and no logger"
  - "Throwaway X.509 chain fixture: three EC P-256 certificates carrying the two Apple OIDs, leaf-intermediate-root, with the vendored real root as the non-vacuity control"

requirements-completed: []

coverage:
  - id: D1
    description: "A verified Apple notification reaches a committed `core.subscriptions` row and its `audit.subscription_events` row, and the route answers 200 only after the commit"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestTheVerifiedNotificationReachesCommittedRows"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every verification failure answers one byte-identical 401 `{\"code\":\"auth_required\"}` and writes nothing, including when a valid Firebase token is present"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestEveryVerificationFailureAnswersTheOneBody"
        status: pass
    human_judgment: false
  - id: D3
    description: "A replayed `notification_uuid` answers 200 writing no second event row; a notification with no transaction part answers 200 writing nothing"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestTheReplayAndTheEmptyNotificationWriteNothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "The seam verifies a payload minted by a throwaway chain against that chain's own root, and the vendored Apple Root CA G3 refuses the same payload"
    requirement: APPLEHOOK-01
    verification:
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py::TestTheRealChainVerifies"
        status: pass
    human_judgment: false
  - id: D5
    description: "Each reachable verification failure raises one `NotificationRejected` carrying its own `stage`, and both nested payloads are verified on their own"
    requirement: APPLEHOOK-01
    verification:
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py::TestEveryReachableRefusalIsOneClassWithItsOwnStage"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py::TestTheNestedPayloadsAreVerifiedOnTheirOwn"
        status: pass
    human_judgment: false
  - id: D6
    description: "`services/subscriptions.py` names no symbol from the Apple store library, proved by an ast walk with two controls"
    requirement: APPLEHOOK-01
    verification:
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py::TestTheServiceNamesNothingFromTheAppleLibrary"
        status: pass
    human_judgment: false
  - id: D7
    description: "`/webhooks/app-store` is the only route on the webhooks router, declares the verifier and neither identity accessor, no route outside the partition declares it, and `PUBLIC_PATHS` is still exactly `{\"/health/ready\"}` as a literal"
    requirement: APPLEHOOK-02
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py::TestTheProviderCallbackPartition"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py::TestEveryRouteIsAuthenticated::test_the_public_allowlist_is_exactly_the_readiness_probe"
        status: pass
    human_judgment: false
  - id: D8
    description: "An unconfigured deployment boots, logs one warning and answers 503 `verification_temporarily_unavailable`, including production without an app id"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestEveryVerificationFailureAnswersTheOneBody::test_an_unconfigured_deployment_answers_503"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py::TestAnAbsentVerifierFailsClosedOnUse"
        status: pass
    human_judgment: false
  - id: D9
    description: "Two simultaneous deliveries of one `notification_uuid` leave one committed set of rows; the loser reads SQLSTATE 23505, rolls back and answers 5xx"
    requirement: APPLEHOOK-01
    verification: []
    human_judgment: true
    rationale: "The concurrency path is written and its SQLSTATE arm is in place, but no two-connection harness runs against real PostgreSQL in this plan. Plan 43-05 owns `tests/schema/test_subscription_race.py`; until it lands, the loser's 5xx is asserted by code reading only."

duration: 17min
completed: 2026-09-04
status: complete
---

# Phase 43 Plan 01: One Verified Apple Notification Reaches a Committed Subscription Row — Summary

**`POST /webhooks/app-store` now verifies Apple's signed envelope and both nested payloads against the vendored Apple Root CA G3, crosses into this project's own frozen value type, and writes one `core.subscriptions` row with its `audit.subscription_events` row in one committed transaction — on a dedicated router that is itself the closed provider-callback partition.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-09-04T21:49:35Z
- **Completed:** 2026-09-04T22:06:20Z
- **Tasks:** 2 of 2
- **Files modified:** 23 (7 created, 16 modified)

## Accomplishments

- **The whole path works end to end on one slice.** A verified notification travels envelope → nested transaction → nested renewal → `VerifiedNotification` → `SubscriptionsService` → `SubscriptionsDB` → commit → 200, and the two rows are asserted present on a real database.
- **The partition is countable, not described.** `routers/webhooks.py` carries the router-level `verify_app_store_notification`, and four new cases in `tests/unit/test_app_wiring.py` assert that the literal `PROVIDER_CALLBACK_PATHS` equals the routes on that router, that each declares the verifier and neither identity accessor, that no route outside declares it, and that the three literals are disjoint. `PUBLIC_PATHS == {"/health/ready"}` is now its own case, separated from the structural set the callback route also joins.
- **The chain check runs for real.** `tests/unit/test_app_store_notifications.py` builds a throwaway root, intermediate and leaf carrying Apple's two required OIDs, mints ES256 payloads with a three-certificate `x5c`, and proves the library's chain walk, OID checks, algorithm rule and signature check all execute — with the vendored real Apple root refusing the same payload as the control that makes it non-vacuous.
- **The seam is airtight by measurement, not by claim.** `auth/app_store.py` declares no logger, never calls `run_in_threadpool`, never reads `.notificationType`; `crud/subscriptions.py` never reaches through `__cause__`; `services/subscriptions.py` names nothing from `appstoreserverlibrary`, proved by an `ast` walk with two controls that both fail when the walk is made vacuous.
- **Four ratchet literals were re-measured in the commit that trips them,** so `main` never carries a red suite: `test_auth_package_shape.py` (5,12,35 → 6,15,40), `test_rejection_vocabulary.py` (+2 event names, +2 constructor entries), `test_app_wiring.py` (the third literal and both unions), and — unplanned — `test_users.py`'s `REMOVED_SYMBOLS`.

## Task Commits

1. **Task 1: One verified Apple notification reaches a committed subscription row** — `0541027` (feat)
2. **Task 2: The seam proved against a real certificate chain** — `3bdf141` (test)

## Files Created/Modified

**Created**

- `src/nativespeaker/api/auth/app_store.py` — the store seam: `AppStoreNotifications`, its `StoreNotificationVerifier` Protocol and the `VerifiedNotification` frozen dataclass. Three library calls, each in its own one-statement `try`; no logger.
- `src/nativespeaker/api/schemas/webhooks.py` — `AppStoreNotificationRequest`, the one-field body keeping Apple's `signedPayload` camelCase spelling.
- `src/nativespeaker/api/routers/webhooks.py` — the `APIRouter` whose membership is the partition, and the thin handler that calls the service and returns an empty 200.
- `src/nativespeaker/api/crud/subscriptions.py` — `SubscriptionsDB` and `WriteOutcome`; module statement builders, thin methods, no `commit()`, no lock, SQLSTATE read off `violation.orig.sqlstate`.
- `src/nativespeaker/api/services/subscriptions.py` — `SubscriptionsService`, `status_at` with its five grounded arms, and the one `commit()`.
- `tests/unit/test_app_store_notifications.py` — 25 cases over a real throwaway certificate chain.
- `tests/e2e/test_app_store_webhook.py` — 15 cases over the real router and a real database.

**Modified**

- `src/nativespeaker/api/config.py` — `StoreEnvironment` (a typed two-member StrEnum, which is a security control), `AppStoreConfig`, and `AppConfig.app_store`.
- `src/nativespeaker/api/errors.py` — `NotificationRejected` (401 `auth_required`) and `UnmappedStoreProduct` (500 `internal_error`, ERROR, with `log_fields()`). No new `ErrorCode` member.
- `src/nativespeaker/api/tables/purchases.py` — `SubscriptionStatus`, its pinned `SubscriptionStatusType`, `Subscription` and `SubscriptionEvent`. The generated column stays unmapped.
- `src/nativespeaker/api/app/lifespan.py` — `build_app_store_verifier`, the explicit two-arm environment mapping, `enable_online_checks=False`, and the `app_store_configuration_absent` warning.
- `src/nativespeaker/api/app/dependencies.py` — `get_subscriptions_service` and `verify_app_store_notification`.
- `src/nativespeaker/api/app/main.py`, `routers/__init__.py`, `crud/__init__.py`, `services/__init__.py`, `tables/__init__.py` — registration and the four barrel exports.
- `config/config.yaml` — the partial `app_store.products` block only; the four env-settable keys stay out of the tracked YAML.
- `tests/e2e/conftest.py` — `FakeAppStoreNotifications` and the `scripted_app_store_notifications` swap fixture.
- `tests/unit/test_app_wiring.py`, `test_auth_package_shape.py`, `test_rejection_vocabulary.py`, `test_users.py` — the four ratchets.

## Decisions Made

1. **A mid-term tier change updates the row in place** (43-CONTEXT.md left this at discretion and asked for it to be recorded). `ix_subscriptions_provider_external_id` allows exactly one row per `(provider, external_id)`, so a flip-then-insert has nowhere to put the second row; the change is recorded as `old_tier_id`/`new_tier_id` on the event. Moot with one paid tier.

2. **The lost race raises the generic `InternalError`, not a fourth leaf.** The plan's `<artifacts_this_phase_produces>` fixes this phase's new exception classes at three, one of which (`AttributionConflict`) belongs to 43-03. `app/error_handlers.py` already constructs `InternalError()` directly for the same purpose, so this is the existing idiom rather than a new one. A one-line WARNING with a closed-set `provider` label is written by the service before the raise, so the race is not silent.

3. **`WriteOutcome.replayed` is produced by `upsert_subscription`** when the stored row already carries the same tier and status. The alternative — a second `read_event` inside `append_event` — would have cost an extra indexed lookup on every write to give the member a producer.

4. **The crud outcome enum is `WriteOutcome`, not `ActivationOutcome`.** `crud/grants.py` already owns that name for the grant activation outcome, and two enums of the same name meaning different things is the drift this project's naming rules exist to prevent.

5. **`status_at`'s arm order is revoked → live `expires_at` → grace → billing retry → expired,** each carrying its one-line ground in the code. Grace is tested before billing retry because Apple sets the retry flag during the grace period too, so the reverse order would drop entitlement from a subscriber Apple is still serving. This closes RESEARCH assumption A1, which was flagged LOW confidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] A fourth ratchet the plan and RESEARCH did not name**

- **Found during:** Task 1
- **Issue:** `tests/unit/test_users.py::TestSubscriptionModelLayerIsGone` holds `REMOVED_SYMBOLS`, a frozenset asserted against `tables.__all__` and against an `ast` import walk over all of `src/` and `tests/`. It lists `Subscription`, `SubscriptionEvent`, `SubscriptionStatus` and `SubscriptionStatusType` as symbols that left with the deleted v1 `tables/subscriptions.py`. Adding the v2.0 models broke two cases. RESEARCH § "Test Ratchets This Phase Trips" names four ratchets and this is not among them.
- **Fix:** Narrowed `REMOVED_SYMBOLS` to the names that are genuinely still gone (`SubscriptionPlan`, `SubscriptionPlanType`, `SubscriptionProvider`, `SubscriptionProviderType`, `UsageMonthly` — the v1 layer, none of which has a table in the v2.0 migration), and moved the four returning names into the exemption set, renamed `ALLOWED_USAGE_SYMBOLS` → `ALLOWED_MODEL_SYMBOLS` because it no longer holds only usage names. A comment states the ground: these came back in 43-01 against the v2.0 migration, in `tables/purchases.py`. `test_subscriptions_module_does_not_exist` is untouched and still binds, so the ratchet's real invariant — the v1 module stays deleted — is intact.
- **Files modified:** `tests/unit/test_users.py`
- **Verification:** `uv run pytest -q` — 1023 passed at the time of the fix, and the module-absence case still passes.
- **Committed in:** `0541027` (part of the task commit, per the standing rule that a ratchet is re-measured in the commit that trips it)

**2. [Rule 3 — Blocking] The throwaway chain's expired-leaf window was invalid**

- **Found during:** Task 2
- **Issue:** `_build_chain` opened every certificate's validity one day back, so the P-09 case asking for a leaf that expired 30 days ago produced `not_valid_after` before `not_valid_before`, which `cryptography` refuses outright. Two cases errored in the fixture rather than in the assertion.
- **Fix:** Opened the shared window 200 days back, so an expired-leaf window still has a `not_before` that precedes it. The backdated `signedDate` (90 days) then falls inside the expired leaf's window and the current one does not, which is exactly the pair the two cases contrast.
- **Files modified:** `tests/unit/test_app_store_notifications.py`
- **Verification:** `uv run pytest tests/unit/test_app_store_notifications.py -q` — 25 passed.
- **Committed in:** `3bdf141`

### Departures from the plan's letter, taken deliberately

**3. Task 1 is one commit, not a RED/GREEN/REFACTOR sequence.** The task carries `tdd="true"`, but its own `<objective>` states — at length, under "Why Task 1 spans 22 files, deliberately" — that the three ratchet literals must land in the same commit as the source change that trips them, because "deferring any of them to Task 2 or to a later plan would land a red suite on `main`, which is what a ratchet is built to prevent." A RED commit is precisely such a red suite. The tests were written and run before the implementation in the working tree, so the discipline held; only the commit boundary differs. `TDD_MODE=false` for this phase, so no gate was bypassed.

**4. `requirements.mark-complete` was NOT run for APPLEHOOK-01 or APPLEHOOK-02.** All six plans in phase 43 declare APPLEHOOK-01, and 43-06 — the documentation plan — declares both and owns the dated REQUIREMENTS.md amendments that 43-CONTEXT.md D-26 specifies. Checking either box after plan 1 of 6 would assert something false: the store purchase row (43-03), the entitlement grant (43-04) and the two-connection race proof (43-05) are all still owed under APPLEHOOK-01. The boxes are left unchecked for 43-06 to close, and `requirements-completed` in this summary's frontmatter is empty for the same reason.

**5. `.env.example` and `k8s/templates/httproute-webhooks.yaml` were not touched.** Both appear in the phase's artifact list, and neither is in this plan's `files_modified` frontmatter. Plan 43-02's objective is exactly that deployment surface, so they are its work, not a gap here.

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking), plus 3 recorded departures from the plan's letter.
**Impact on plan:** No scope creep. Both auto-fixes were mechanically forced — one by an unnamed ratchet, one by a fixture arithmetic error — and neither changed any production behaviour. The three departures are boundary decisions, each with its ground written down above.

## Verification

All four gates green at completion, quoted from the tail of each run:

| Command | Result | Baseline |
|---|---|---|
| `uv run pytest -q` | **1048 passed**, 412 deselected | 1016 |
| `uv run pytest -m e2e -q` | **258 passed**, 1202 deselected | 241 |
| `uv run pytest -m schema -q` | **154 passed**, 1306 deselected | 154 |
| `uv run ruff check src tests` | **All checks passed!** | clean |

Every acceptance grep in the plan matched:

- `structlog` in `auth/app_store.py`: `0` — the seam declares no logger
- `run_in_threadpool` in `auth/app_store.py`: `0`
- `.notificationType` in `auth/app_store.py`: `0` — `rawNotificationType` only
- `enable_online_checks=False` in `app/lifespan.py`: `1`
- `__cause__` in `crud/subscriptions.py`: `0`
- `appstoreserverlibrary` in `services/subscriptions.py`: `0`
- `PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}`: `1`
- `PUBLIC_PATHS == {"/health/ready"}`: `1`
- `git status --porcelain -- migrations/ config/certs/`: empty — neither was modified

The import-fence control was mutation-checked rather than asserted: making `_imported_roots` return an empty set fails both control cases and leaves the fence case passing, which is the acceptance criterion's exact demand.

## Known Stubs

| Stub | File | Reason |
|---|---|---|
| `com.nativespeaker.subscription.monthly` | `config/config.yaml` | A placeholder App Store product id, written on the plan's explicit instruction: the real product id does not exist yet because there is no iOS app. The line above it says an operator edits the map, and an unmapped product id is a logged 500 with nothing written, so a wrong entry fails loudly rather than silently granting a tier. It is resolved by an operator edit, not by a later plan. |

`core.store_purchases` is deliberately unmodelled and no `core.access_grants` row is written; both are plan boundaries stated in this plan's `<action>`, not stubs.

## Issues Encountered

**The e2e savepoint fixture and the service's `commit()`.** `tests/e2e/conftest.py::_db_transaction` swaps the session factory for one bound to an open connection with `join_transaction_mode="create_savepoint"`, so the service's real `commit()` releases a savepoint and the rows stay visible to a second session from the same factory, then roll back at test end. This worked unmodified — the two-row assertions and the replay case all read the committed rows — so no fixture change was needed.

**Nothing else.** No package was installed, no migration was touched, no certificate was added, and no authentication gate was reached.

## User Setup Required

None by this plan. Plan 43-02 documents the three App Store environment variables a deployer must supply (`APP_STORE_BUNDLE_ID`, `APP_STORE_APP_APPLE_ID`, `APP_STORE_ENVIRONMENT`). Until they are set, the application boots, logs `app_store_configuration_absent` once, and the route answers 503 — which is the designed and tested behaviour, not a defect.

## Next Phase Readiness

**Ready for the rest of phase 43.** The seam, the value type, the service, the crud and the partition are all in place and are what the remaining five plans extend:

- **43-02** renames the k8s route and documents the three variables. Independent of this code.
- **43-03** adds `StorePurchase` and `AttributionConflict`, and resolves the user from `attribution_token`. `VerifiedNotification.attribution_token` is already populated from `appAccountToken` and already flows into the service.
- **43-04** writes the entitlement grant under the fixed lock order in the same transaction. The service's `commit()` is the one boundary it must join; `status_at`'s entitled set is exactly `active` and `grace_period`, which the generated column keys on.
- **43-05** owns the two-connection race, the wire-level oracle proof and the config gate. The SQLSTATE arm and the rollback it must exercise are written; only the harness is missing.
- **43-06** writes the REQUIREMENTS.md amendments and checks the two boxes this plan deliberately left open.

**For Phase 44 (Google Play):** `StoreNotificationVerifier` and `VerifiedNotification` are the contract to satisfy, and `services/subscriptions.py` is proved by test to name nothing Apple-specific, so a Google class producing the same value type feeds the same service with no change to it.

**One concern to carry forward.** RESEARCH § Security residual 3 — this route is publicly reachable with no credential and no limiter at either layer, and each request costs a full certificate-path build plus up to three ES256 verifications. It is CPU burn and not amplification (no network call, no session, nothing written, a constant-size body), and it is accepted on the Phase 35 D-05/D-08 precedent. It is wider than the three residuals STATE.md already records, because those all need a valid token first. It closes with the v2.1 gateway contract, and 43-06 should record it in that wording rather than as one more of the same.

## Self-Check: PASSED

All seven created source and test files exist on disk, and both task commits (`0541027`, `3bdf141`) are present in `git log`.

---
*Phase: 43-post-webhooks-app-store*
*Completed: 2026-09-04*
