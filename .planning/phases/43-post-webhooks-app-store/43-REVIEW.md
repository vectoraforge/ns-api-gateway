---
phase: 43-post-webhooks-app-store
reviewed: 2026-09-10T05:15:33Z
depth: standard
files_reviewed: 142
files_reviewed_list:
  - AGENTS.md
  - config/config.yaml
  - docker-compose.yml
  - Dockerfile
  - .dockerignore
  - .env.example
  - .gitignore
  - k8s/templates/deployment.yaml
  - k8s/templates/httproute-app.yaml
  - k8s/templates/httproute-auth.yaml
  - k8s/templates/httproute-health.yaml
  - k8s/templates/httproute-webhooks.yaml
  - k8s/templates/NOTES.txt
  - k8s/templates/security-policy.yaml
  - k8s/values.yaml
  - migrations/20260818_01_initial-release.sql
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/error_handlers.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/devicecheck.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/chats.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/crud/violations.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/logs.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/routers/webhooks.py
  - src/nativespeaker/api/schemas/api.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/schemas/llm.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/llm.py
  - src/nativespeaker/api/services/quota.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/services/sync.py
  - src/nativespeaker/api/tables/auth.py
  - src/nativespeaker/api/tables/chats.py
  - src/nativespeaker/api/tables/grants.py
  - src/nativespeaker/api/tables/identities.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/purchases.py
  - tests/e2e/conftest.py
  - tests/e2e/refusal_sites.py
  - tests/e2e/test_app_store_webhook.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/e2e/test_create_user.py
  - tests/e2e/test_google_play_webhook.py
  - tests/e2e/test_llm_schema.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/e2e/test_sign_out_all.py
  - tests/e2e/test_sync.py
  - tests/e2e/test_users_me.py
  - tests/schema/conftest.py
  - tests/schema/test_apply_rollback.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_constraints.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_harness_guards.py
  - tests/schema/test_inventory.py
  - tests/schema/test_registration_pairing.py
  - tests/schema/test_restore_race.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/schema/test_sync_lock_freedom.py
  - tests/unit/conftest.py
  - tests/unit/error_tree.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_chats_crud.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_config.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_conversion_carries_usage.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_identities_crud.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_identity_flip.py
  - tests/unit/test_jwks_offload.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_logging.py
  - tests/unit/test_models.py
  - tests/unit/test_monthly_period.py
  - tests/unit/test_purchases_crud.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_services.py
  - tests/unit/test_spent_free_grant_refusal.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_subscription_grant_write.py
  - tests/unit/test_subscription_store_clock.py
  - tests/unit/test_sync_clock_capture.py
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_tables_metadata.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users_me.py
  - tests/unit/test_users.py
  - uv.lock
findings:
  critical: 1
  warning: 23
  info: 27
  total: 51
status: issues_found
---

# Phase 43: Code Review Report

**Reviewed:** 2026-09-10T05:15:33Z
**Depth:** standard
**Files Reviewed:** 142
**Status:** issues_found

## Summary

Re-review of phase 43 over everything that changed since the previous 43-REVIEW.md commit
(`b1bb418`) — 142 files, reviewed by seven parallel reviewers over disjoint module groups with
disjoint finding-ID blocks, then merged. The phase-35..42 fix passes that landed on this branch in
the interim were treated as current intended code, not as regressions.

Every reviewer first checked `.planning/REQUIREMENTS.md`, the phase decision records (D-nn / A-nn /
OQ-n) and the binding specs under `specs/` for a ratified decision that already settled the point.
75 candidate findings were dropped on that basis and are listed below with their citations.

One Critical survives: the subscription grant writer decides to insert from `entitled` alone
(CR-60), so a lapsed subscription re-entitles itself with no restore, and a notification about a
newest-wins-superseded subscription expires the live grant and reactivates the loser.

The remaining 23 Warnings cluster in four places: silent event loss on the two
unauthenticated store-webhook routes (WR-20, WR-21, WR-40), boot-time configuration that validates
one store but not its twin (WR-03, WR-04, WR-41), guards and controls that cannot fail as written
(WR-120, WR-121, WR-122, WR-80, WR-81, WR-82, WR-100..WR-104), and packaging or comment-convention
drift (WR-02, WR-23).

**Cross-reference (from the unit-test group):** the free-tier usage copied into the paid counter sits in
`src/nativespeaker/api/crud/subscriptions.py`, filed as CR-60. WR-100 is the test-side gap that let it
through, and is not a duplicate of it.

## Dropped (ratified)

**Part A — infra and config**

- **No per-IP / per-URL gateway rate limit on `/webhooks/app-store`** (`k8s/templates/httproute-webhooks.yaml`), contrary to `08-webhook-app-store.md`:24 "Gateway rate-limit entries: per-IP and per-URL limits on this exact path" — settled by **D-06**: "`k8s/templates/httproute-webhooks.yaml` is renamed only. … No rate-limit entries are added. The brief's per-IP and per-URL gateway limits are a **flagged deferral** to the v2.1 gateway contract (Phase 35 D-05), not an omission." (43-CONTEXT.md:72-75)
- **The route is registered even when `app_store` is unconfigured**, contrary to the brief's "not registered at all while Apple's store integration is unconfigured" and "startup fails closed if the registered route lacks configuration its verifier requires" — settled by **D-02**: "Always registered; fails closed when unconfigured. … **FLAGGED CONFLICT** against `08-webhook-app-store.md`". (43-CONTEXT.md:43-50)
- **`chats_limit` / `messages_limit` in `config/config.yaml` duplicate the `config.py` defaults and foreclose `CHATS_LIMIT` / `MESSAGES_LIMIT`** — settled by 42-REVIEW.md:207: "Keep in this file only what must not vary: `app_store.products`, `google_play.products`, `chats_limit`, `messages_limit`, `jwt.jwks_cache_ttl_seconds`."
- **`db.pool_size: 12` in `config/config.yaml` forecloses `DB_POOL_SIZE`** — settled by Phase 41 **D-16**, cited in the file itself: "`resilience.pool_size * 2 + 2` at that field's default (Phase 41 D-16, which accepts that declaring it here forecloses DB_POOL_SIZE)."
- **The route answers the shared `{code}` error body instead of the brief's "plain HTTP status codes … never the shared client-visible error classes"** — settled by **D-04**: "**FLAGGED CONFLICT** against the brief's 'never the shared client-visible error classes' … The brief's 'plain status' cannot be answered any other way here". (43-CONTEXT.md:59-67)
- **No route-registry / `Category` / `RouteMetadata` / named-`VERIFIERS` metadata anywhere in config or the chart**, contrary to SHARED-INVARIANTS § "The barrier" and the brief's "Named verifier declared in the route registry" — settled by 43-CONTEXT.md:213-214: "**No route registry, no `Category`, no `RouteMetadata`, no `VERIFIERS`** (Phase 37.1 D-06/D-10). D-01 is the replacement."
- **`config/config.yaml` ships a placeholder App Store product id (`com.nativespeaker.subscription.monthly`)** — settled by 43-06-SUMMARY.md:250: "A fourth operator action is owed once a real product exists: replacing the placeholder id in `config/config.yaml`'s `app_store.products` map with the real App Store product id."
- **Apple's root CA is committed to the repository rather than fetched or pinned by digest** (`config/certs/AppleRootCA-G3.cer`, defaulted from `config.py:167`) — settled by **D-10**: "Apple's root CA is vendored. … It is public, not a secret; pinning Apple's own root is what the brief allows. A rotation is a commit." (43-CONTEXT.md:102-105)
- **`enable_online_checks=False`, so a revoked Apple intermediate is still accepted** — settled by **D-09**: "No online revocation check. … Divergence from Apple's production guidance, recorded with its reason". (43-CONTEXT.md:96-101)

Also dropped as out of Group A: the missing `max_length` on `signedPayload` (already 43-REVIEW.md WR-01, and `schemas/webhooks.py` belongs to another reviewer).

**Part B — auth adapters, schemas, resilience**

- **The App Store route is registered even when Apple's integration is unconfigured, and answers 503 instead of not existing** — settled by 43-CONTEXT D-02: "Always registered; fails closed when unconfigured. … **FLAGGED CONFLICT** against `08-webhook-app-store.md` 'not registered at all while Apple's store integration is unconfigured'."
- **Verification failures answer the shared `{code}` error body, which spec 08 forbids ("never the shared client-visible error classes")** — settled by 43-CONTEXT D-04: "**FLAGGED CONFLICT** against the brief's 'never the shared client-visible error classes': the body shape is shared, the classes are the route's own, and no `ErrorCode` member is added."
- **No per-IP/per-URL gateway limit guards `/webhooks/app-store`, so unauthenticated 64 KB envelopes pay inline x5c chain verification on the event loop** — settled by 43-CONTEXT D-06: "No rate-limit entries are added. The brief's per-IP and per-URL gateway limits are a **flagged deferral** to the v2.1 gateway contract (Phase 35 D-05), not an omission." Inherited by 44-CONTEXT D-19.
- **`AppStoreNotifications.verify` runs on the event loop rather than `run_in_threadpool`** — settled by 43-CONTEXT D-07: "It is called inline, not through `run_in_threadpool`: with D-09 there is no I/O in it."
- **No online certificate-revocation check on Apple's chain** — settled by 43-CONTEXT D-09: "`enable_online_checks=False`. … Divergence from Apple's production guidance, recorded with its reason."
- **`UnmappedStoreProduct` answers 500, so Apple/Pub-Sub retry a notification that can never succeed until an operator edits config** — settled by 43-CONTEXT D-14 and D-21: "for the missing mapping that is the right loop — an operator adds the line and the next retry succeeds."
- **The Play replay key is `google_play:{purchaseToken}:{eventTimeMillis}:{notificationType}`, not the Pub/Sub message ID spec 09 §41 names** — settled by 44-01-SUMMARY OQ-4: "the Google replay key is the payload-derived composite … chosen by the user at the plan's checkpoint", confirmed by 44-VERIFICATION row 5.
- **`PubSubPushMessage.data` is unbounded at the pydantic layer** — settled by 37.2-REVIEW-FIX WR-25: "an empty or oversized Pub/Sub `data` field is a permanent 422 redelivery loop … so the route answers 200. The value of `PUBSUB_DATA_LIMIT` is unchanged."
- **`PubSubPushMessage` declares no `messageId`** — settled by 37.3-REVIEW-FIX WR-25: "`PubSubPushMessage.messageId` is required, unread, and makes a permanent 422 reachable"; and 44-REVIEW IN-04.
- **`before_call`'s elapsed arm primes `_failure_count` to `threshold - 1` instead of clearing it** — settled by 41-REVIEW-FIX WR-01: "the elapsed arm now primes the tally at `self._failure_threshold - 1` … so one failure after the window reopens the breaker."
- **`record_success` takes a generation stamp instead of reading `_opened_at`** — settled by 39-REVIEW-FIX WR-02: "`attempt()` stamps it immediately before the provider call, so an answer from an attempt admitted before the trip is discarded however long it took to land."
- **`FirebaseAdminLookup.revoke_refresh_tokens` exists at all, against SHARED-INVARIANTS § Tokens and sessions** — settled by `11-sign-out-all.md`:20, which mandates "the `revoke_refresh_tokens(issuer, subject) -> confirmed | unconfirmed` seam this phase implements the call site for". The invariant bans `checkRevoked` and *per-request* revocation checks, not whole-subject sign-out.
- **`ainvoke` skips the breaker on the first attempt** — settled by `ns-api-gateway/AGENTS.md` § Resilience: "The first attempt rides the admission verdict instead, because that is the verdict the caller's quota charge was committed against: a charged request always reaches the provider at least once."

**Part C — app wiring, routers, errors, logs**

- **The App Store route answers with the shared `{code}` error body, against `08-webhook-app-store.md` "never the shared client-visible error classes."** — settled by 43-CONTEXT.md **D-04**: "`NotificationRejected` (401, `auth_required`) … `Unavailable` (503 …) is reused for absent config. Both reach `app_error_handler`, so the body is the shared `{code}` shape. **FLAGGED CONFLICT** against the brief's 'never the shared client-visible error classes'."
- **A missing or empty `signedPayload` answers 422, not the brief's 401.** — settled by 43-RESEARCH.md :420: "this is a wording correction, not a defect"; and 43-PATTERNS.md :685 "422 is preferred over a business rejection".
- **The route stays registered while Apple's integration is unconfigured, against the brief's "not registered at all".** — settled by **D-02**: "Always registered; fails closed when unconfigured … **FLAGGED CONFLICT** against `08-webhook-app-store.md` 'not registered at all while Apple's store integration is unconfigured'."
- **`main.py` runs no startup route-enumeration assertion (SHARED-INVARIANTS § The barrier).** — settled by 43-CONTEXT.md "Carried forward": "**No route registry, no `Category`, no `RouteMetadata`, no `VERIFIERS`** (Phase 37.1 D-06/D-10). D-01 is the replacement." The replacement is `tests/unit/test_app_wiring.py`, which I ran (35 cases, all pass).
- **No backend rate limiting anywhere, and the generic 429 carries no `Retry-After`.** — settled by **D-06** and "Carried forward": "**No rate limiting and no vendor budgets, backend or gateway** (Phase 35 D-05)."
- **The webhooks router lost D-01's router-level `verify_app_store_notification` dependency, so a future route added there is unauthenticated.** — the control D-01 names ("Membership … is the set of routes on that router", counted by literal) is intact: `test_no_route_serves_without_an_identity_or_a_callback_declaration` asserts the unauthenticated set equals `PUBLIC_PATHS | PROVIDER_CALLBACK_PATHS`, so a verifier-less webhooks route fails there. Phase 44 legitimately added the second route and literal member (PLAYHOOK-03).
- **`NotificationRejected`'s 401 carries no `WWW-Authenticate`.** — already raised and dismissed as IN-02 in 43-REVIEW.md: "Apple ignores the header, so this costs nothing."
- **`UnmappedStoreProduct` and `AttributionConflict` answer 500 for a well-formed notification.** — settled by **D-21**: "Two `InternalError` leaves answer 500 … Apple retries on its schedule … for the missing mapping that is the right loop."
- **`/webhooks/google-play/rtdn` answers 200 for a delivery it decodes to nothing.** — settled by **D-22** ("A notification with no transaction answers 200") and the Pub/Sub rule recorded in `schemas/webhooks.py`: "Pub/Sub acknowledges 2xx alone and redelivers every other status."
- **`get_db` never commits, so a handler that forgets its `commit()` answers 200 for a rolled-back write.** — deliberate, and correct: FastAPI 0.135.1 `routing.py:112-117` closes `fastapi_inner_astack` only after `await response(scope, receive, send)`, exactly as the comment claims. I traced every writer: `routers/auth.py:74`, `services/chats.py:99/134/153/176`, `services/subscriptions.py:98/169`. None is missing.
- **Two pooled connections per chat request with `max_overflow=0` could deadlock the pool.** — `services/chats.py:99` and `:134` commit the request session before `QuotaService.charge` opens its own, so no request holds two.
- **`get_identity` returns ORM rows from a session it then closes, so handlers read detached instances.** — `AsyncSession.close()` detaches without expiring, and every consumer reads loaded column attributes only (`identity.user.id`, `.email`, `.display_name`, `identity.identity.provider`, `.free_grant_consumed_at`, `.id`). No caller re-attaches or lazy-loads.

**Part D — crud, tables, services, migration**

- `core.subscriptions.store_signed_at` is a column the `00-schema.md` DDL fence does not carry —
  settled by `.planning/quick/260904-u7t-.../260904-u7t-PLAN.md:151`, "Add a nullable
  `store_signed_at TIMESTAMPTZ` column to `CREATE TABLE core.subscriptions` in ...".
- The attribution-conflict guard reads `resolved_token_value`, while `08-webhook-app-store.md:43`
  names `identity_value` — settled by `260904-u7t-PLAN.md:108`, "**Decision: promote, with no new
  column.** `resolved_token_value` is already the only-ever-store-supplied value on that row ...
  Task 4 promotes it to be the key the attribution conflict guard reads."
- `AttributionConflict` carries `purchase_id`, not the `external_id` 43-03-PLAN.md:119 names —
  settled by the citation the class itself carries, `errors.py:316`: "The row's own key, never the
  lifecycle key: on the Google path the lifecycle key is the purchase token itself (44 D-10), which
  is not admissible in a log line."
- A token-bearing but unbound purchase records the token as `identity_value`, not a generated UUID —
  settled by `43-03-SUMMARY.md:208`, "`identity_value` is the presented token whenever the
  notification carries one, and a server-generated UUID only when the store gives none. This is the
  literal wording of the locked decision in `43-CONTEXT.md` D-17."
- The migration omits `audit.auth_events`, `core.auth_event_result`,
  `core.access_grants_anti_abuse`, `core.provider_accounts`,
  `core.provider_account_gate_consumptions` and `UNIQUE (id, source)` — settled by
  `.planning/REQUIREMENTS.md:67`, "**SCHEMA-06** — **WITHDRAWN.** ... The `audit.auth_events` table,
  its nine CHECK constraints and its four `ix_auth_events_*` indexes were deleted from the initial
  migration", and by the Phase 38 amendment at `REQUIREMENTS.md:32`.
- `RestoreService` prefers a recorded grant term over the proof's, so a live subscription whose
  grant row is time-ended is refused `term_closed` — settled by 37.5 CR-25 (`559deaa`) and
  re-affirmed by `40-REVIEW-FIX.md:466`, "already settled by phase 37.5 **CR-25**, and the suggested
  fix is disproven — applied and reverted."
- Carrying a month's count across a supersession at all, against 43-04-PLAN.md:27's "a fresh
  `core.user_monthly_usage` row at `monthly_used = 0`" — settled by 37.5 WR-48 (`c1bc549`),
  `37.5-REVIEW-FIX.md:566`: "The counter now travels the way `activate_registered_account_grant`
  already travels it". Only the free-source half is filed below, as WR-60.
- `write_subscription_grant` and `upsert_subscription` never lock `core.subscriptions` — settled by
  `43-CONTEXT.md:143`, "No subscription-row lock: it would be a lock tier ahead of the grant locks,
  and it does not exist on the first insert."

Two further candidates were disproven by reading rather than by a ruling, and are not filed:
`store_original_transaction_id=notification.external_id` is correct, because `auth/app_store.py:77`
sets `external_id` from `transaction.originalTransactionId`; and `is_unique_violation`'s
`getattr(orig, "sqlstate", ...)` does match, because SQLAlchemy 2.0.46's asyncpg adapter sets
`translated_error.pgcode = translated_error.sqlstate` before raising.

**Part E1 — unit tests (first half)**

- **`_instant` reads an out-of-range Apple stamp as absent rather than refusing it** (`app_store.py:42-54`,
  pinned by `test_app_store_notifications.py:327-339`) — looked like a fail-open reading of
  SHARED-INVARIANTS § Fail-closed defaults ("never read a failed lookup as an empty result").
  Settled by `37.5-REVIEW-FIX.md:222` — *"WR-16 — `_instant` has no range guard, so one out-of-range
  Apple stamp 500s the webhook forever"* — and the compensating refusal really exists:
  `services/subscriptions.py:116-120` raises `InternalError` under
  `store_notification_without_term` for an entitled status with no term.
- **`PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}`** (`test_app_wiring.py:19`)
  against SHARED-INVARIANTS:14 *"Only `POST /auth/create-user` (both phases) is pre-auth-callable."*
  Settled verbatim by `REQUIREMENTS.md:187` — *"the count changed from one route to two; the
  substance did not … that route **must** be pre-auth-callable"* — and `:189` names this exact
  literal as *"The enforcement point"*.
- **`crud/grants.py:157-235` (`activate_anonymous_device_grant`) has zero unit coverage**, while its
  registered twin is driven directly by `test_conversion_carries_usage.py`. Not a unit gap: the
  writer is driven against real PostgreSQL by `tests/schema/test_grant_locks.py:347,383,662-675`, and
  the platform pin specifically at `:830-855` (`activate_anonymous(NativeClaimProvider.android_play_integrity)`
  → `refused`). The tier split is the design.
- **Spec 08:49's *"does not accept a valid Firebase user token in place of provider verification"*
  is absent from `test_app_wiring.py`** — covered by
  `tests/e2e/test_app_store_webhook.py:292` (`test_a_valid_firebase_token_does_not_change_the_refusal`).
- **`UnmappedStoreProduct` is never raised through `AppStoreNotifications.verify` in any unit case**
  (`app_store.py:199` uncovered by `test_app_store_notifications.py`) — the same `_tier_for` is
  covered through `verify_transaction` by `test_restore_proof.py:185,455`, and the notification path
  by `tests/e2e/test_app_store_webhook.py:361,506`.
- **The real `ChallengesDB.claim` / `consume` statements (`challenges.py:68-88`) are executed by no
  unit test** — `conftest.FakeChallengeStore` stands in for them. I diffed the fake against the SQL
  clause by clause (`claimed_at IS NULL AND expires_at > now`; `claimed_at IS NOT NULL AND
  consumed_at IS NULL`, clearing `preauth_subject`) and found no drift; the real statements are
  covered per `REQUIREMENTS.md:206` by `tests/e2e/test_challenge_store.py`.
- **No case signs a nested *renewal* payload with a foreign key**, though spec 08:48 requires each
  nested payload be *"verified on its own"*. Dropped: `test_a_renewal_from_the_wrong_environment_is_refused`
  (`test_app_store_notifications.py:591-597`) only reaches its `INVALID_ENVIRONMENT` stage after the
  library has walked the chain and checked the signature, so the renewal's own verification is
  already proven load-bearing.
- **`RESCIND_CONSENT` is missing from `test_no_statusless_apple_type_answers_the_500`'s parametrize**
  while `app_store.py:138-139` names four such types. Dropped: the arm keys on `data.rawStatus`, never
  on the type, so the fourth type adds no branch.
- **restore.py's five never-asserted cause strings** (`status_not_entitled`,
  `status_moved_under_the_locks`, `tier_moved_under_the_locks`, `term_closed`,
  `another_account_won_the_race` — none appears anywhere under `tests/`). Not ratified, but out of
  this group's scope: `test_restore_proof.py` is group E2's file. Flagged here only so it is not
  lost.

**Part E2 — unit tests (second half)**

Twelve candidates were dropped after finding a ratified decision that settles them.

- A renewal minting a **fresh** `monthly_used = 0` rather than carrying the month's count —
  settled by `43-04-PLAN.md:27` ("inserts the next term's grant with a fresh
  `core.user_monthly_usage` row at `monthly_used = 0` … (D-15)") and by 37.5 WR-48's fix
  (`c1bc549`): "A renewal at a month boundary still starts at zero, so 43-04's ratified 'its fresh
  usage row' still describes what a renewal does."
- The entitled-but-closed-term and tierless notifications earning a permanent 500 with the
  `notification_uuid` never recorded — settled by D-21 ("Two `InternalError` leaves answer 500")
  and D-23 ("5xx, never 200, on internal failure"); 37.5 WR-50 raised the retry-budget cost and was
  listed under "## Skipped".
- The route answering the shared `{code}` body instead of a bare status — settled by D-04
  (**FLAGGED CONFLICT**): "the body shape is shared, the classes are the route's own, and no
  `ErrorCode` member is added."
- `test_rejection_vocabulary.py:188` handing `NotificationRejected` a
  `stage="VERIFICATION_FAILURE"` taken from Apple's library — settled by D-04: "the library's
  `VerificationStatus` name goes to the log as `stage`."
- No case covering online certificate revocation on the chain walk — settled by D-09
  ("`enable_online_checks=False`") and `COVERAGE.md`: "`enable_online_checks` (OCSP revocation) |
  OPT-OUT".
- `test_restore_proof.py` verifying against a throwaway root instead of Apple's — settled by D-24:
  "Unit tests generate a throwaway root CA, intermediate and leaf … a control proves the vendored
  Apple root refuses them."
- No unit case for the per-IP / per-URL gateway limits on the webhook path — settled by D-06 (a
  "**flagged deferral** to the v2.1 gateway contract") and 43-CONTEXT "Carried forward": "**No rate
  limiting and no vendor budgets, backend or gateway**".
- No `audit.auth_events` assertion in any ingestion suite — settled by `08-webhook-app-store.md:22`
  ("the route writes no `audit.auth_events` row, so it adds no audit result value") and D-27.
- `test_subscription_grant_write.py::test_a_free_grant_is_superseded_too` expiring the buyer's free
  grant and never giving it back — settled by D-18: "A product consequence, not a divergence."
- `test_identity_flip.py` / `test_restore_proof.py` classifying `IntegrityError` off
  `orig.sqlstate` and never off a constraint name — settled by 43-CONTEXT "Carried forward":
  "`IntegrityError` is caught by SQLSTATE 23505 only, read off `orig.__cause__.sqlstate`, never by
  constraint name (Phase 42-07)."
- The webhook route being registered in every environment and answering 503 when unconfigured —
  settled by D-02 (**FLAGGED CONFLICT**): "Always registered; fails closed when unconfigured."
- `test_tables_metadata.py` demanding the SQLModel metadata declare no index, no uniqueness rule
  and no delete action — settled by `oft-conventions.md` § Umbrella items
  (`req~schema-ddl-as-written~1`, "The migration file that applies it carries the one tag") plus
  WR-33 / WR-41.

**Part F — e2e and schema tests**

- **An empty or absent `signedPayload` answers 422, not the brief's "401 for a missing, malformed,
  or invalid payload"** (`tests/e2e/test_app_store_webhook.py:479-486`) — settled by
  `43-RESEARCH.md:415-424` ("a body that fails Pydantic validation does not short-circuit … The
  project maps 422 to `ValidationError` and answers the one-field `{"code": "validation_error"}`,
  so nothing client-visible changes") and `43-05-PLAN.md:241-242` ("A malformed body answers the
  project's 422 `validation_error`; assert that instead if the module wants a shape case").
- **No case in this group drives the usage carry-over across a supersession inside one UTC month**
  (`crud/subscriptions.py:372`) — a probe replacing `carried = usage.monthly_used` with
  `carried = 0` left all 170 store/restore schema+e2e cases green, but the behaviour is driven by
  `tests/unit/test_subscription_grant_write.py::TestTheMonthsCountSurvivesATermChangeInsideIt`
  ("WR-48: the allowance is a UTC calendar month's, so a supersession inside one month carries its
  count"), which is another group's file.
- **No case in this group drives the mid-term tier-change flip** (`crud/subscriptions.py:322`,
  `and grant.tier_id == tier_id`) — a probe deleting that clause left all 633 schema+e2e cases
  green, but it is driven by `tests/unit/test_subscription_grant_write.py::
  test_this_subscriptions_own_earlier_term_is_superseded` ("A mid-term tier change takes the same
  expire-then-insert path as every other write"), and `43-CONTEXT.md` § Claude's Discretion already
  records "Whether a mid-term tier change updates `tier_id` in place or flips and inserts; moot
  with one paid tier."
- **The route is registered and answers 503 while unconfigured, against the brief's "not registered
  at all while Apple's store integration is unconfigured"**
  (`tests/e2e/test_app_store_webhook.py:305-319`) — settled by D-02, "Always registered; fails
  closed when unconfigured … **FLAGGED CONFLICT** against `08-webhook-app-store.md`".
- **The refusals answer the shared `{code}` bodies, against the brief's "never the shared
  client-visible error classes"** (`REJECTED`, `UNAVAILABLE`, `INTERNAL` at
  `tests/e2e/test_app_store_webhook.py:44-51`) — settled by D-04, "**FLAGGED CONFLICT** … the body
  shape is shared, the classes are the route's own, and no `ErrorCode` member is added."
- **No per-IP or per-URL gateway limit is exercised for `/webhooks/app-store`** — settled by D-06,
  "No rate-limit entries are added. The brief's per-IP and per-URL gateway limits are a **flagged
  deferral** to the v2.1 gateway contract (Phase 35 D-05)."
- **`audit.subscription_events.old_tier_id` transitions are asserted nowhere in this group** —
  covered by `tests/unit/test_subscription_attribution.py:565-602`.
- **No case proves "the provider credential opens no route behind the barrier"** (spec 08
  § Security hardenings) — covered structurally by `tests/unit/test_app_wiring.py:132-161`, which
  asserts every provider-callback route declares its verifier and neither `get_identity` nor
  `get_linked_identity`, and that no route outside the literal declares the verifier (D-01).
- **The e2e Apple route never runs the real `AppStoreNotifications`, only the scripted fake** —
  settled by D-24, "Real chain in unit tests, scripted fake in e2e."
- **No online-certificate-revocation case** — settled by D-09 and `COVERAGE.md`
  (`enable_online_checks` OPT-OUT, "explicitly out of scope").
- **No case for the version 1 notification format, consumption requests, refund decisions or
  external purchase tokens** — settled by `COVERAGE.md` § "Notification handling", all OPT-OUT.
- **The Apple e2e has no grace-status-with-a-closed-window case** — covered by the shared,
  provider-agnostic writer through `tests/schema/test_subscription_ingestion.py:707-721`
  (`test_a_grace_window_already_closed_is_refused_before_any_write`, CR-20), which D-13/D-19 make
  the one path for both stores.

## Critical

### CR-60: Ingestion reactivates a lapsed entitlement, and a notification about a superseded subscription takes the live grant

**File:** `src/nativespeaker/api/crud/subscriptions.py:313-388` (reached from
`src/nativespeaker/api/services/subscriptions.py:155-165`)

**Why:** `write_subscription_grant` decides to insert a new active grant from `entitled` alone. It
never asks whether this subscription's grant already lapsed. The rule it must hold is stated twice
and is binding: `08-webhook-app-store.md:42` — "When state becomes entitled again, ingestion
**never reactivates** the grant: reactivation belongs to user-invoked restore alone; the
entitled-subscription/expired-grant state persists until restore. After newest-wins supersession, a
later notification about the superseded subscription may update its canonical row but must not
silently reactivate its grant." `43-CONTEXT.md` D-18 repeats it: "Ingestion never reactivates a
grant; restore (Phase 45) is the only path back."

Two inputs produce a wrong result.

1. Lapse and recovery on one subscription. `EXPIRED` marks the grant `expired` and the buyer holds
   nothing. A later `DID_RENEW` carries `active`, so `held` is empty (the expired row is not in
   `marked_active`), `superseded` is empty, and the writer inserts a fresh `status='active'` grant.
   The buyer is re-entitled with no restore. Probed against the real writer over the file's own stub
   session: `_write(session, [])` returns `applied` and adds one grant with `status=active`.

2. Newest-wins supersession, then a notification about the loser. Subscription B superseded
   subscription A, so A's grant is `expired` and B's is active. A genuine later notification for A
   arrives. `held` (A's active grants) is empty, so there is no replay. `superseded` at line 327 is
   `[grant for grant in marked_active if grant.user_id == user_id or ...]`, which is **B's live
   grant**: B is expired with `ends_at = evaluated_at`, and A's grant is re-inserted active on A's
   older term. The account is moved back onto the superseded subscription; when A's term ends the
   buyer holds nothing at all, while B is still a paid, live subscription. `store_signed_at` does
   not guard this — that clock is per canonical row, and a genuine later A notification carries a
   newer one. This is the exact sentence the spec writes as "must not silently reactivate its
   grant". `tests/unit/test_subscription_grant_write.py:114-122` pins the symmetric direction and
   nothing pins this one.

**Fix:** Decide before superseding. Read this subscription's grant history at any status
(`AccessGrant` where `subscription_id == subscription_id`, no status predicate — a sibling of
`GrantsDB._grants_of_source_statement`). If a grant row exists for it and none of them is in
`marked_active`, the term lapsed: leave every held grant alone, write no grant, and return
`WriteOutcome.applied` so the canonical row and the event row still commit. Insert only when the
subscription has never had a grant (first verified purchase) or when it still holds one to flip
(per-term flip-then-insert). Add a unit case for the lapse-then-renew input and one for the
superseded-subscription input, both asserting that no `AccessGrant` is added and that no other
account grant changes status.

## Warnings

### WR-01: `.dockerignore`'s credential patterns are root-anchored, so a key under `config/` is gitignored but baked into the image

**File:** `.dockerignore:6-12` (see also `Dockerfile:29`)
**Why:** The file's own header states its contract: "The credential shapes are the ones `.gitignore` names." That is false. `.gitignore` patterns without a slash match at **any** depth, so `.gitignore:20-23` (`*.p8`, `*.pem`, `*.key`, `application_default_credentials.json`) covers `config/AuthKey_XXXX.p8`. `.dockerignore` uses Go `filepath.Match` semantics, where a pattern with no `**` matches **only path components at the context root** — so `*.p8` in `.dockerignore` does *not* exclude `config/AuthKey_XXXX.p8`. `Dockerfile:29` is `COPY config ./config/`, and `config/` is precisely the tree this phase made key-adjacent (it now carries `certs/AppleRootCA-G3.cer`, and `config.py:203-208` derives the certificate location from `config_dir`). A developer who drops the DeviceCheck `.p8` or an ADC JSON beside it gets no git warning — the file is correctly ignored — and then ships a live private key inside every published image layer. The same root-anchoring silently disables `__pycache__/` and `*.egg-info/` for everything under `src/`, so stale bytecode from the developer's machine enters the builder stage.
**Fix:** Anchor the credential shapes at every depth, matching `.gitignore`'s semantics the header claims:
```
**/.env
**/.env.*
!**/.env.example
**/*.p8
**/*.pem
**/*.key
**/application_default_credentials.json
**/__pycache__/
**/*.egg-info/
```

### WR-02: `cryptography` is imported by `src/` but is not a declared dependency

**File:** `pyproject.toml:5-32`
**Why:** `src/nativespeaker/api/app/lifespan.py:11` is `from cryptography import x509`, used at `lifespan.py:67` to reject a non-DER Apple root. `cryptography` appears in `uv.lock` only as a transitive of `PyJWT[crypto]` (uv.lock:43). This is the exact hazard `pyproject.toml:7-10` writes its own rule against: "Declared, not inherited: `src/` imports both directly … so a transitive range widening (sqlmodel's, fastapi's) would relock this project onto a version nothing here constrains." Phase 41 recorded "Not declared separately and should not be" (41-RESEARCH.md:102), but that rested on the premise that `cryptography` was only PyJWT's ES256 backend and was never imported by this codebase — Phase 43 broke that premise, so the earlier statement no longer settles the point. If PyJWT ever drops the `crypto` extra's pin, or `firebase-admin` widens it, the next `uv lock` resolves an X.509 API this project imports directly against a range nothing here constrains — and `Dockerfile:17` (`uv sync --frozen`) means the failure surfaces as a boot `ImportError`/`AttributeError` in the image, not at lock time.
**Fix:** Add `"cryptography >=46,<47"` (or the ceiling matching the `x509` API in use) to `[project].dependencies`, then `uv lock`. Same argument as the `starlette` and `sqlalchemy` entries two lines above it.

### WR-03: `_numeric_or_absent`'s `str.isdigit()` guard lets a malformed value through to a boot crash — the exact outcome the guard exists to prevent

**File:** `src/nativespeaker/api/config.py:102-107`
**Why:** The validator's stated contract is "Degrading beats raising: absence is already the fail-closed path this route answers 503 from" (`config.py:100-101`). `str.isdigit()` is `True` for characters `int()` refuses — superscripts and subscripts among them. Proven in this tree:

```
$ APP_STORE_APP_APPLE_ID='²' .venv/bin/python -c "from nativespeaker.api.config import EnvironmentConfig; EnvironmentConfig()"
pydantic_core._pydantic_core.ValidationError: 1 validation error for EnvironmentConfig
app_store.app_apple_id
  Input should be a valid integer, unable to parse string as an integer [type=int_parsing]
```

`EnvironmentConfig()` is called at `lifespan.py:136`, so this is a CrashLoopBackOff of the **whole** API — chat included — from one malformed optional store setting. This is the same failure class that 43-REVIEW.md CR-04 filed against this block; the fix landed on the value's *source* (`.env.example` now ships the three commented out) but left the guard itself holed. A digit string longer than `sys.int_info.default_max_str_digits` (4300) reaches the same crash.
**Fix:** Classify by the parse that actually runs, not by a predicate that only approximates it:
```python
@field_validator("app_apple_id", mode="before")
@classmethod
def _numeric_or_absent(cls, value):
    """Keep an int or a string that parses as one, and read anything else as absent."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
```

### WR-04: an App Store product map that cannot serve the deployment produces no boot signal, unlike its Google sibling

**File:** `config/config.yaml:17-20` (guard to change: `src/nativespeaker/api/app/lifespan.py:170-178`)
**Why:** `config.yaml:17` states the consequence of an unmapped id — "a verified product id absent from it is a 500 and Apple's next retry succeeds" — and D-21/D-14 make an unmapped product a 500 (`UnmappedStoreProduct`). But `build_app_store_verifier` (`lifespan.py:56-76`) checks `bundle_id`, `environment`, the root certificate and `app_apple_id`, and never looks at `products`; the `app_store_configuration_absent` warning is gated on that builder returning `None`. So a deployment with the store credentials set but an empty or stale product map boots **clean**, logs nothing, reports Ready — and then 500s every genuine Apple notification forever, with Apple retrying until its schedule expires. The Google branch guards exactly this case one screen below: `lifespan.py:181-184` includes `or not config.google_play.products` in its warning condition. The map that ships today is a placeholder (43-06-SUMMARY.md:250), so the very first real deployment is in this state by default, and this is the failure mode with no signal at all rather than the 503-plus-warning one the file promises.
**Fix:** Make the two store branches symmetric — add the product map to the App Store absence condition, so the unusable-map case degrades to the same 503 + one named warning as every other absent App Store setting:
```python
        app_store_verifier = build_app_store_verifier(config.app_store)
        if app_store_verifier is None or not config.app_store.products:
            logger.warning("app_store_configuration_absent", consequence=...)
```
and extend the `consequence` string to name the product map alongside the bundle id, environment, app id and root certificate.

### WR-20: A verified Apple transaction with no `originalTransactionId` is acknowledged 200 and permanently dropped

**File:** `src/nativespeaker/api/auth/app_store.py:77` (reached from `verify`, lines 100-162)

**Why:** `originalTransactionId` is `Optional` on `JWSTransactionDecodedPayload` and the App Store
Server Library never checks it. `_crossed` copies it straight through as `external_id`, so a
notification whose signature, chain, bundle id and environment all verified — carrying a real
`signedTransactionInfo` — produces a `VerifiedNotification` with `external_id=None`.
`SubscriptionsService.ingest:33-36` then takes its `external_id is None` early return, logs
`store_notification_without_transaction` at INFO, and `routers/webhooks.py:26-29` answers **200**.
Apple treats 200 as delivered and never resends: the subscription event is lost, and the log line
is indistinguishable from a routine TEST notification.

The same module already refuses exactly this input on the restore path —
`verify_transaction:178-180` raises `ProofRejected(stage="transaction_without_original_id")`
because "the lifecycle key this proof is looked up by is absent" — and the sibling field
`productId` is refused too, because `_tier_for(None)` raises `UnmappedStoreProduct` (a 500 Apple
retries). Only `originalTransactionId` on the notification path degrades to a silent success.
Spec 08 requires 401 for "a missing, malformed, or invalid payload (envelope or **any nested
payload**)"; a nested transaction with no lifecycle key is that.

**Fix:** guard it in `verify` where the transaction is decoded, mirroring the restore path, so the
answer is a refusal rather than a false acknowledgement:

```python
transaction = self._verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)
...
if transaction.originalTransactionId is None:
    raise NotificationRejected(stage="transaction_without_original_id")
```

### WR-21: The product→tier lookup runs before the renewal payload is verified, turning a 401 into a retried 500

**File:** `src/nativespeaker/api/auth/app_store.py:150` (renewal verification at 152-160)

**Why:** `tier_id = self._tier_for(transaction.productId)` executes at line 150, and
`verify_and_decode_renewal_info` only at line 156. `_tier_for` raises `UnmappedStoreProduct`,
which is an `InternalError` → **500**. So a notification whose `data.signedRenewalInfo` cannot be
verified *and* whose product id is not in the configured map answers 500 instead of the 401 spec 08
mandates ("Any failure → 401, fail closed"; "401 … before any business logic"). 500 is precisely
the answer that makes Apple resend a payload that can never verify, on its whole multi-day retry
schedule — the loop the `_instant` and `verify` comments elsewhere in this file say they exist to
avoid. The reachable trigger is not forgery but library drift: the code already anticipates
`payload_unstructurable` when "a field of the wrong JSON type leaves a cattrs error", and Apple
extends `JWSRenewalInfoDecodedPayload` independently of this deployment's product map.

Resolving the tier is also business logic performed while a nested signed payload of the same
envelope is still unverified, which inverts the spec's stated order.

**Fix:** move the tier resolution below the last nested-payload verification, so every
verification arm is exhausted before any business rule runs:

```python
if data.signedRenewalInfo is None:
    return _crossed(payload, transaction, None, status=status,
                    tier_id=self._tier_for(transaction.productId))
try:
    renewal = self._verifier.verify_and_decode_renewal_info(data.signedRenewalInfo)
except VerificationException as failure:
    raise NotificationRejected(stage=failure.status.name) from failure
except Exception as failure:
    raise NotificationRejected(stage="payload_unstructurable") from failure
return _crossed(payload, transaction, renewal, status=status,
                tier_id=self._tier_for(transaction.productId))
```

### WR-22: `record_failure` carries no generation guard, so a straggler failure reopens a recovered breaker

**File:** `src/nativespeaker/api/resilience.py:82-89` (stamp at 192, success guard at 71-80)

**Why:** the generation mechanism was added so that "an attempt in flight when the breaker tripped
predates it, so its answer says nothing about the provider now" (lines 72-79). That reasoning is
applied to successes only. `attempt()` stamps `generation` at line 192, but the failure arm at
line 203 calls `record_failure()` with no argument, and `record_failure` compares nothing.

Consequence: an attempt stamped under generation *g* whose failure lands after the breaker tripped
(*g+1*) **and** after `before_call`'s elapsed arm reset it now increments a tally that
41-REVIEW-FIX WR-01 deliberately primed to `threshold - 1`. One stale failure therefore reopens the
breaker immediately, and the whole fleet pays another `circuit_breaker_reset_seconds` of 503 even
though the provider recovered. The mirror-image case — a straggler success zeroing the primed
tally — is exactly what the generation guard was introduced to stop.

At the shipped defaults the window is closed by arithmetic alone (`timeout_seconds` 30 <
`circuit_breaker_reset_seconds` 60, and `record_failure` runs at most one attempt-timeout after the
stamp). It opens on any deployment where an operator tightens the reset window or lengthens the
provider timeout; `config.py:51,56` bound each field independently and cross-check neither, so
`circuit_breaker_reset_seconds: 15` — a plausible tightening — makes it live.

**Fix:** make the two arms symmetric rather than relying on a config coincidence — pass the stamp
into `record_failure` and discard a pre-trip generation, as `record_success` already does:

```python
async def record_failure(self, generation: int) -> None:
    async with self._lock:
        if generation != self._generation or self._opened_at is not None:
            return
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._opened_at = time.monotonic()
            self._generation += 1
```

with the call site becoming `await self._circuit_breaker.record_failure(generation)`. (If the
asymmetry is intentional as a fail-closed bias, the cheaper root-cause fix is a validator on
`ResilienceConfig` asserting `timeout_seconds < circuit_breaker_reset_seconds`, so the precondition
is enforced rather than assumed.)

### WR-23: 50 multi-line comment runs across these 12 files break the repo-binding comment rule

**File:** `src/nativespeaker/api/schemas/webhooks.py:22-33` (12 lines), `auth/jwt_verifier.py:148-155` and `212-219` (8 each), `auth/firebase.py:139-145` (7), `auth/devicecheck.py:26-31,40-45`, `auth/app_store.py:137-142`, `auth/store_notifications.py:30-35`, `resilience.py:74-78,123-127`, and 39 more

**Why:** `ns-api-gateway/AGENTS.md` § "Comments and docstrings" opens with "These rules bind all
code in this repository" and states "**One line each.** A comment explains the specific line or
lines below it. It never explains the design, the request lifecycle, a rule enforced in another
module, or a decision that was made elsewhere." A scan of the twelve reviewed files finds 50
comment runs of three lines or more. They are not stylistic near-misses: they are the banned
content. `schemas/webhooks.py:22-33` explains Pub/Sub's retry semantics and a bound enforced in
`auth/google_play.py`; `store_notifications.py:30-35` explains `crud/subscriptions.py::
SubscriptionsDB.write_subscription_grant`; `app_store.py:49-53` explains
`SubscriptionsService.ingest`; `resilience.py:123-127` narrates a decision made in a review pass.

This is the same defect 41-REVIEW-FIX WR-79 fixed for `services/` and `routers/` ("All 21 remaining
runs of three to seven lines are gone. A detector over `services/` and `routers/` now reports
none"). The rule binds the whole repository; `auth/`, `schemas/` and `resilience.py` were simply
never swept, so the register the rule superseded survives in the packages this phase owns. It
matters for the product's stated constraint too — AGENTS.md at the repo root asks that programming
this app "not consume many tokens", and these files carry roughly 200 lines of prose no reader
needs at the line.

**Fix:** run the same sweep over `src/nativespeaker/api/auth/`, `src/nativespeaker/api/schemas/`
and `src/nativespeaker/api/resilience.py`: keep the one clause that resolves the ambiguity at the
line below, and move the rationale into the phase context files that already hold it. Extend the
existing `services/`/`routers/` detector to these paths so the register cannot return.

### WR-40: the App Store boot warning does not test the product map its sibling does
**File:** `src/nativespeaker/api/app/lifespan.py:171-180` (compare `:182-190`)
**Why:** `build_app_store_verifier` tests `bundle_id`, `environment`, `app_apple_id` and the root certificate, and the `app_store_configuration_absent` warning fires only when that builder answers `None`. `config.app_store.products` is never tested. The Play arm one block below *does* test it — `or not config.google_play.products` — and names "product map" in its consequence text. So a deployment that overrides `app_store.products` to `{}` (or drops the one shipped key while renaming a product in App Store Connect) boots completely clean: no warning, verifier built, route live. Every real purchase notification then verifies, reaches `AppStoreNotifications.verify`, and dies at `auth/app_store.py:196-199` — `self._products.get(product_id)` is `None`, so `UnmappedStoreProduct` raises a 500 with nothing written. Apple retries that notification on its schedule for about three days and then stops; the buyer is charged and never gets a grant, and the only evidence is `unmapped_store_product` ERROR lines nobody was told to look for at boot. D-21 accepts the 500-and-retry loop *because* "an operator adds the line and the next retry succeeds" — that loop only closes if the operator is told, and the boot warning is what tells them.
**Fix:** widen the condition to the same shape as the Play arm, and name the map in the text:
```python
if app_store_verifier is None or not config.app_store.products:
    logger.warning("app_store_configuration_absent",
                   consequence="POST /webhooks/app-store fails closed until this pod is restarted "
                               "with the App Store bundle id, environment, product map, app id "
                               "(production only) and root certificate available in this environment")
```
(The same edit fixes the text's second inaccuracy: `app_apple_id` is required only when `environment is StoreEnvironment.production`, per the guard at `:60-61`, so a sandbox operator is currently sent looking for a setting that is not their problem.)

### WR-41: a transient JWKS failure at boot disables Play ingestion for the pod's whole life, under a warning that names the wrong cause
**File:** `src/nativespeaker/api/app/lifespan.py:79-92`, consumed at `:193`
**Why:** `JWTVerifier.__init__` performs a live JWKS fetch (`auth/jwt_verifier.py:156-161`). `build_google_push_verifier` catches `PyJWTError` and answers `None`. `PubSubPushTokens` stores that `None` once (`auth/google_play.py:225-226`) and never rebuilds, so `verify` raises `Unavailable` → 503 for every subsequent delivery. Nothing recovers: readiness (`/health/ready`) still answers 200 unconditionally, so Kubernetes never restarts the pod, and no code path retries the build. A two-second blip reaching `www.googleapis.com` during pod start therefore costs every Play RTDN until someone manually restarts — and after the subscription's message retention (7 days by default) those deliveries are gone, which for RTDN means renewals, cancellations and revocations that never reach `core.access_grants`. The warning emitted is `google_play_configuration_absent`, whose text tells the operator to supply "the Play package name, product map, push audience, push service account and Application Default Credentials" — all of which are already present in this scenario, so the message actively directs them away from the one fix (restart). I accept the builder's stated goal ("one route's 503 beats a dead pod", pinned by `TestTheJwksWarmUpGuard`); what I dispute is making the degradation permanent, since the failure it guards against is transient by nature while the App Store builder's `None` genuinely means "unconfigured".
**Fix:** keep the boot behaviour the tests pin (builder answers `None`, pod boots) and make the seam recover, so the next delivery rebuilds instead of 503-ing forever. Hand `PubSubPushTokens` the builder rather than the built object:
```python
# lifespan.py
app.state.google_push_tokens = PubSubPushTokens(
    build=lambda: build_google_push_verifier(config.google_play))

# auth/google_play.py
async def verify(self, bearer: str) -> None:
    if self._verifier is None:
        # Rebuilt off the loop: the constructor fetches. A still-unconfigured deployment
        # answers None again and this stays the 503 it was.
        self._verifier = await run_in_threadpool(self._build)
    if self._verifier is None:
        raise Unavailable(stage="google_push_verify")
    ...
```
Failing that, the minimum root-cause fix is to distinguish the two cases in the log: emit a separate `google_push_verifier_warm_up_failed` event whose consequence text says "restart this pod", so the operator is not sent to check configuration that is already correct.

### WR-60: Free-tier usage is copied into the paid counter

**File:** `src/nativespeaker/api/crud/subscriptions.py:356-372`

**Why:** `08-webhook-app-store.md:38` requires the paid entitlement's usage row be "seeded
`monthly_used=0` (**free-tier usage never copied into the paid counter**)". The carry at line 360
selects on `grant.user_id == user_id` alone, so it takes the count off whichever grant the buyer
held — including the `anonymous_device_grant` or `registered_account_grant` row that line 327
supersedes. Probed against the real writer: a free grant with `monthly_used=9` in the current
period yields a paid usage row seeded at `9`. The 37.5 WR-48 fix that introduced the carry was
reasoned about a grace bounce and a mid-term tier change; both are subscription-to-subscription, and
the free source was not in front of it. A new paid subscriber silently starts the month down by
whatever they spent on the free tier.

**Fix:** Restrict the carry to the same source the term is being written for:
`mine = [grant for grant in superseded if grant.user_id == user_id and grant.source is
AccessGrantSource.subscription]`. The tripwire and the `MissingUsageRowError` arm stay as they are;
a free-grant supersession then seeds `monthly_used=0`, which is what the spec names. WR-48's own
cases (grace bounce, tier change) are untouched, because both supersede a `subscription` row.

### WR-61: A store notification silently expires an operator-issued manual grant

**File:** `src/nativespeaker/api/crud/subscriptions.py:327-339`

**Why:** When the status is entitled, `superseded` is every grant the destination holds. Probed:
an `AccessGrantSource.manual` grant is set to `expired` with `ends_at` by an ordinary ingestion.
`08-webhook-app-store.md:40` enumerates what ingestion may expire — "any index-blocking grant
(buyer's active free grant, or previously active subscription grant)" — and `manual` is not in that
list. `core.manual_grant_issuances` is an immutable record with a `case_id`, an `operator` and a
`reason`; after this write it points at an expired grant, nothing records why, and — by D-18 —
ingestion never gives it back. An operator compensation grant is destroyed by a webhook the operator
never saw.

**Fix:** Handle `manual` explicitly rather than by falling into the general sweep. The cheapest
correct answer here is to keep expiring it (the non-deferrable
`ix_access_grants_one_active_per_user` leaves no alternative) but to make it visible: log one
WARNING naming the superseded `source` and the `manual_grant_issuances.case_id` when the superseded
grant's source is `manual`, from a closed label set. Add the unit case that pins the log line, so
the loss is a recorded event and not a silent one.

### WR-80: the only thing that distinguishes `lost_race_to_another_source` is asserted nowhere, so the branch can be deleted with the whole unit suite green

**File:** `tests/unit/test_claim_precedence.py:540-554`, `tests/unit/test_claim_precedence_registered.py:464-479`

**Why:** `AuthService._settle` (`services/auth.py:308-316`) has two lost-race refusal arms that are
byte-identical on the wire — both are `ClaimRefusedUnderLock`, 403 `operation_not_allowed`. Phase 42's
own fix record says so: `42-REVIEW-FIX.md:263-265` — *"The client-visible answer of
`ClaimRefusedUnderLock` and `OtherActiveGrantHeld` is identical … so the raced answer now matches the
deterministic one on the wire and **differs only in the internal log event's `cause`**."* Both cases
that WR-60 added assert only `status_code == 403` and `response.json() == REFUSED`, which the
`lost_race_without_a_readable_grant` fall-through produces just as well. `cause="lost_race_to_another_source"`
appears in no file under `tests/` at all — I grepped every `cause=` literal in `src/` against the whole
test tree.

Mutation-probed: deleting the whole `if held: raise ClaimRefusedUnderLock(cause="lost_race_to_another_source")`
block from `services/auth.py:311-314` leaves **1831 passed** in `tests/unit`. The sibling case
`test_a_race_the_re_read_cannot_answer_is_named_apart_from_those_refusals` (`:589-602`) shows the
right shape and is what the two WR-60 cases should have copied. (WR-60's own probe — swapping the
source test for the old `if held:` — flips 200→403 and so does fail; it does not cover deletion.)

**Fix:** add the `_handler_warnings` assertion the sibling case already uses, to both files:

```python
def test_a_race_lost_to_another_source_is_the_refusal_the_preflight_gives(
        self, client, store, account, grants, devicecheck, monkeypatch):
    records = _handler_warnings(monkeypatch)
    ...
    assert response.status_code == 403
    assert [(line["event"], line.get("cause")) for line in records] == [
        ("claim_refused_under_lock", "lost_race_to_another_source")]
```

### WR-81: the DeviceCheck adapter's transport-failure conversion is claimed in the phase summary and tested by nothing

**File:** `tests/unit/test_devicecheck_adapter.py` (whole file; `TestTheParseArms:194-294` is where it belongs)

**Why:** `auth/devicecheck.py:189-192` converts `httpx.HTTPError` into `RetryableDeviceCheckError`
carrying only the exception's class name. `41-01-SUMMARY.md:204` states the behaviour as shipped —
*"A transport failure is retryable. `httpx.HTTPError` is converted to the internal marker carrying
only the exception's class name, so a timeout exhausts to 503 rather than escaping as a 500."* No
test drives it. `Recorder` always returns an `httpx.Response`; the file never raises a transport
error from the mock transport, and `RetryableDeviceCheckError` is only ever *scripted onto a fake
seam* (`test_claim_precedence.py:513,776`, `test_claim_precedence_registered.py`,
`tests/e2e/test_claim_anonymous_grant.py:425`, `tests/e2e/test_claim_registered_grant.py:584,611`) —
never produced by the real adapter. `devicecheck.py:191-192` is the file's only uncovered pair of
lines under its own suite (98%).

The consequence if it regresses is worse than a wrong status: an escaping `httpx.ConnectError` is
not an `AppError`, so it also misses `AuthService._complete`'s `except AppError` arm
(`services/auth.py:155-160`) — no rollback, no `_consume_quietly`, and a generic 500 on a routine
network blip.

Mutation-probed: replacing the `except httpx.HTTPError as failure: raise RetryableDeviceCheckError(...)`
with a bare `raise` leaves **1831 passed** in `tests/unit`.

The same arm on the Play adapter *is* tested twice
(`test_google_play_notifications.py:618-634`), which is the shape to copy.

**Fix:** add a transport case beside `TestTheParseArms`, on both entry points, asserting the exhausted
budget and that nothing of the request survives in the marker:

```python
async def test_a_transport_failure_exhausts_the_budget_and_names_only_its_class(self, private_key):
    def _unreachable(_request):
        raise httpx.ConnectError("the DeviceCheck endpoint is unreachable")
    recorder = Recorder()  # never reached; the transport raises
    adapter = AppleDeviceCheck(key_id=KEY_ID, team_id=TEAM_ID, private_key=private_key,
                               client=httpx.AsyncClient(transport=httpx.MockTransport(_unreachable)))
    with pytest.raises(RetryableDeviceCheckError) as raised:
        await adapter.read_bits(QUERY_TOKEN)
    assert str(raised.value) == "ConnectError"
    assert QUERY_TOKEN not in str(raised.value) and DEVICECHECK_HOST not in str(raised.value)

    with pytest.raises(Unavailable):
        await read_bits_with_retry(adapter, QUERY_TOKEN)
```

### WR-82: the unconfigured-Play-credential arm has no test, and the e2e fixture that looks like it covers it masks it

**File:** `tests/unit/test_google_play_notifications.py:122-128` (`_play_reader`), `:840-843`

**Why:** `auth/google_play.py:257-258` — `if self._credential is None: raise Unavailable(stage="play_subscriptions_read")`
— is the fail-closed arm for a deployment whose ADC read returned `None`. It is the only uncovered
statement of `google_play.py` on the webhook path (`--cov-report=term-missing` over this file:
`Missing 258, 323, 326, 329, 333-336, 341, 345, 356-358, 386`; every other miss is
`read_for_restore`/`_product_of`, which is group E2's `test_restore_proof.py`).

`_play_reader`'s `credential=None` default is never actually used as `None` — line 126 substitutes
`_FakeCredential()`. `stage="play_subscriptions_read"` appears nowhere under `tests/`.
`TestThePushTokenCheck::test_an_unconfigured_deployment_answers_503_rather_than_admitting_the_push`
(`:840-843`) covers only the push-token half and asserts no stage.

The e2e fixture that appears to close this does not: `tests/e2e/conftest.py:583-589`
(`unconfigured_google_play`) nulls **both** the push verifier and the credential, and the push-token
check runs first in `verify_google_play_notification`, so `read()` is never entered and line 258 never
executes there either. The state is reachable in production independently —
`build_google_push_verifier` needs only `push_audience` + `push_service_account_email` + a reachable
JWKS, while `_play_credential()` returns `None` on any of the four ADC failures that
`test_config.py:644-651` already enumerates.

Mutation-probed: replacing the raise with `return None` — which makes an unconfigured pod **acknowledge**
every RTDN, and Pub/Sub never redelivers an acknowledged message — leaves **1831 passed** in
`tests/unit`.

**Fix:** drive the arm directly, and pin the stage:

```python
async def test_an_unconfigured_play_credential_is_never_acknowledged(self):
    reader = _play_reader(_never_reached, credential=None)   # pass the real None through
    with pytest.raises(Unavailable) as refusal:
        await _read_through(reader)
    assert refusal.value.stage == "play_subscriptions_read"
```

`_play_reader` also needs a sentinel default so `credential=None` can be expressed at all:
`credential=_UNSET` / `_FakeCredential() if credential is _UNSET else credential`. Splitting the e2e
`unconfigured_google_play` fixture into its two halves would close the same hole from the other side.

### WR-100: The free-grant supersession case is seeded so that it cannot detect the usage carry

**File:** `tests/unit/test_subscription_grant_write.py:124-132` and `:204-257`

**Why:** `TestTheMonthsCountSurvivesATermChangeInsideIt` is the class that pins the carry rule, and
every case in it supersedes a **subscription** grant (`_grant()`'s default
`source=AccessGrantSource.subscription`, line 80). The one case that supersedes a free grant,
`test_a_free_grant_is_superseded_too`, seeds `_usage(free, monthly_period=THIS_MONTH,
monthly_used=0)` — a zero, so its assertion `free.status is AccessGrantStatus.expired` holds whether
or not the count travels into the new paid row. Probed against the real writer with no source
change: a `anonymous_device_grant` holding `monthly_used=45` in the current period produces a paid
usage row seeded at `45`, which `08-webhook-app-store.md:38` forbids in as many words — "seeded
`monthly_used=0` (**free-tier usage never copied into the paid counter**)". Probed the other way as
well: restricting `mine` to `AccessGrantSource.subscription` — the spec-correct writer — leaves
every case in this file, in `test_subscription_attribution.py` and in `test_restore_proof.py` green,
so nothing under `tests/` pins either behaviour. A new paid subscriber starts the month short by
whatever the free tier already spent, and no test says so.

**Fix:** Seed the free case at a non-zero count and assert the zero:

```python
async def test_a_free_grants_count_is_never_carried_into_the_paid_counter(self):
    """`08-webhook-app-store.md:38`: free-tier usage never reaches the paid counter."""
    free = _grant(source=AccessGrantSource.anonymous_device_grant, subscription_id=None,
                  ends_at=None, tier_id=FREE_TIER_ID)
    session = _StubSession(_usage(free, monthly_period=THIS_MONTH, monthly_used=45))

    await _write(session, [free])

    assert _minted(session) == [0]
```

Keep `test_a_term_change_inside_the_month_carries_the_count` beside it as the control, so the two
sources are told apart rather than the carry being switched off wholesale.

### WR-101: `PurchasesDB.resolve_user` — the attribution lookup — has no unit case at all

**File:** `tests/unit/test_purchases_crud.py:120-158`

**Why:** This file pins `read_tokens` down to the statement: one query, no `FOR UPDATE`, the token
table by name, no `core.users` read, the owner predicate, and — in `TestTheReadIsScopedToOneOwner`
(WR-84) — the bound value the predicate carries. Its sibling on the same class, `resolve_user`, is
the server-authoritative attribution read that both `SubscriptionsService.ingest` and
`RestoreService.restore` key an owner off, and it is driven by nothing: every consumer test replaces
it with a stub that ignores its arguments (`test_subscription_attribution.py:230`,
`test_restore_proof.py:686`). Probed: deleting `col(StorePurchaseToken.provider) == provider` from
`crud/purchases.py::resolve_user` — so one store's `identity_value` resolves the other store's
binding, against `08-webhook-app-store.md:37` "keyed by store provider + lifetime attribution token,
with **no identity-kind dimension**" — leaves every test in the four files that touch `PurchasesDB`
green.

**Fix:** Add the sibling class here, reusing `_compiled` and `_bound`, because the compiled text
renders both key values as placeholders and only `_bound` can state them:

```python
class TestTheAttributionReadIsKeyedOnTheStoreAndTheToken:
    async def test_it_carries_both_halves_of_the_key(self):
        session = _StubSession(SEEDED)
        await PurchasesDB(session).resolve_user(PurchaseProvider.apple, APPLE_TOKEN)

        assert session.executed == 1
        assert LOCK_CLAUSE not in _compiled(session.statements[0])
        assert _bound(session.statements[0]) == [PurchaseProvider.apple, APPLE_TOKEN]
```

`_StubResult` needs a `first()` beside its `all()` for this.

### WR-102: The replay key's own statement is unpinned, so the idempotency guarantee rests on a stub

**File:** `tests/unit/test_subscription_attribution.py:172-173`

**Why:** `08-webhook-app-store.md:44` makes the whole replay contract "keyed on Apple's notification
UUID, recorded as `audit.subscription_events.notification_uuid` (UNIQUE)". The only unit case that
touches replay, `test_a_replay_takes_no_lock_and_gives_its_read_transaction_back`, measures what the
service does **after** `_RecordingSubscriptions.read_event` — a dict lookup keyed by
`notification_uuid` in the test — has answered. The production statement is never compiled or
inspected. Probed: re-keying `_event_statement` in `crud/subscriptions.py` onto
`SubscriptionEvent.event_type` — which would swallow every redelivery of one Apple type as a replay
and re-apply every distinct notification carrying a new type — leaves the entire unit tree green.

**Fix:** One compiled-statement case in the shape this repo already uses for crud reads: drive
`SubscriptionsDB(session).read_event("uuid-under-test")` over a recording stub session, and assert
one statement, `audit.subscription_events` in `_compiled(...)`, no `FOR UPDATE`, and
`_bound(...) == ["uuid-under-test"]`.

### WR-103: The attribution-conflict secrecy case checks a narrower scope than its docstring, and three of its four assertions cannot fail

**File:** `tests/unit/test_subscription_attribution.py:413-429`

**Why:** Line 424 already asserts `refusal.value.log_fields()` by exact dict equality against
`{"provider": "apple", "purchase_id": str(recorded.id)}`. Lines 427-429 then assert that
`external_id`, `TOKEN` and `OTHER_TOKEN` are absent from `repr(refusal.value.log_fields())` — each
strictly implied by the equality above, so none can ever fail independently. This is the same
tautology 38-REVIEW WR-48 removed elsewhere. Meanwhile the docstring's claim, "no store value is in
the record", is never checked where a store value could actually reach an operator: the exception's
own message. `AttributionConflict.__init__` (`errors.py:312`) builds `f"Store purchase {purchase_id}
of {provider.value} presents another attribution value"` — safe today, but nothing here holds it
that way, and the sibling case for the same property on the restore path
(`test_restore_proof.py:467-476`) checks `stage`, `str(...)` and `log_fields()` all three.

**Fix:** Delete lines 427-429 and move the three absence checks onto the message, matching
`TestThePlayRefusalNamesNoPartOfTheToken`:

```python
for secret in (external_id, TOKEN, OTHER_TOKEN):
    assert secret not in str(refusal.value)
```

### WR-104: The ingestion recorder copies both store transaction ids and no case reads either

**File:** `tests/unit/test_subscription_attribution.py:200-212` and `:291-303`

**Why:** The module docstring states the standard this file holds itself to — "Each case asserts the
values the writer was asked to persist". `_RecordingSubscriptions.insert_purchase` faithfully copies
`store_transaction_id` and `store_original_transaction_id` into the recorded `StorePurchase`, and
then no assertion anywhere reads either field; `test_the_attributed_shape_carries_the_owner_and_the_resolved_token`
stops at `identity_value`, `resolved_token_value` and `purchase_user_id`. Probed: swapping the two
arguments in `services/subscriptions.py::ingest`, so the per-term transaction id lands in the
original-transaction column and the lifecycle key in the per-term one — against D-08, which fixes
`external_id` as `originalTransactionId` — leaves the entire unit tree green. The two ids are what
an operator matches an App Store Connect record against.

**Fix:** `_notification()` already mints them distinguishably (`original-<uuid>` against
`txn-<uuid>`), so two lines in the attributed-shape case suffice:

```python
assert purchase["store_original_transaction_id"] == notification.external_id
assert purchase["store_transaction_id"] == notification.transaction_id
```

(the case needs the notification bound to a name rather than built inline).

### WR-120: both "no refusal arm is missed" controls are blind to a new raise site in `app/dependencies.py`

**File:** `tests/e2e/test_app_store_webhook.py:66-67,261-275`; `tests/e2e/test_google_play_webhook.py:228-229,354-367`; `tests/e2e/refusal_sites.py:33-38`

**Why:** The completeness control reads *function* source
(`_REFUSAL_SOURCES = (inspect.getsource(verify_app_store_notification), inspect.getsource(app_store))`),
while the control that is supposed to close that control's gap —
`test_no_raise_site_lives_where_neither_route_control_reads_it`, whose docstring says "a refusal
raised in a file `_REFUSAL_SOURCES` misses would shrink both sides of the equality above instead of
failing it" — compares only *file* names (`files_raising_the_refusal() == REFUSAL_FILES`). Because
`app/dependencies.py` is already a member of `REFUSAL_FILES` (it carries
`verify_google_play_notification`'s two raises at :208 and :224), a refusal added anywhere else in
that file is invisible to both. Worse, `verify_app_store_notification`
(`app/dependencies.py:193-197`) contains no `NotificationRejected` call at all, so half of the
Apple `_REFUSAL_SOURCES` tuple contributes nothing and only `auth/app_store.py` is really scanned.

Proved: adding `def _probe_never_called(): raise NotificationRejected(stage="a_stage_no_case_covers")`
to `app/dependencies.py` (probe reverted in the same command) left all four control cases green —
`4 passed`. The stage has no parameter in `REFUSAL_STAGES`/`REFUSALS`, and nothing said so.

**Fix:** Make the scan file-wide on both routes and derive the expected set from it. Replace the
function-source tuple with `refusal_sites`' own package scan — e.g. add
`stages_by_file() -> dict[str, set[str]]` beside `files_raising_the_refusal()`, have each webhook
module assert its parametrised arms equal the union over `REFUSAL_FILES`, and drop
`inspect.getsource` entirely. Then a raise site anywhere in the package reaches a parameter list or
fails the equality.

### WR-121: the stage scanner reads only the `stage=` keyword, so a positionally-raised refusal adds nothing

**File:** `tests/e2e/refusal_sites.py:41-49`

**Why:** `raised_refusal_stages` walks `node.keywords` and records a stage only when
`keyword.arg == "stage"`. `NotificationRejected` is a `ProviderLookupError` leaf whose `stage` can
be passed positionally, and a positional call contributes **no** member to `raised`. The
completeness equality in `test_every_reachable_arm_is_covered_by_one_parameter`
(`tests/e2e/test_app_store_webhook.py:270`) then still holds while the new arm has no parameter and
no case. This is the same failure mode WR-120 describes, reached by a second route, and it is the
one the comment at `test_app_store_webhook.py:69-71` says cost the suite
`notification_without_identity` once already.

**Fix:** Fail closed on any call shape the scanner cannot read: in `refusal_calls`/
`raised_refusal_stages`, record `COMPUTED` for a call carrying `node.args` or no `stage=` keyword
at all, rather than silently contributing nothing. A positional or star-args raise then either
becomes `COMPUTED` (and is covered by the computed-stage arm) or breaks the equality.

### WR-122: the Apple "a valid Firebase token buys nothing" case never establishes that the token is valid

**File:** `tests/e2e/test_app_store_webhook.py:292-303`

**Why:** `test_a_valid_firebase_token_does_not_change_the_refusal` requests the `stub_verifier`
fixture and then never uses it: the body only posts `Bearer {make_token(sub='store-callback-subject')}`
and asserts 401. The route reads no Authorization header at all (D-05), so the case passes for any
bearer string whatsoever — including one the application would itself reject. It therefore cannot
fail on the half the spec's route-enumeration assertion names ("does **not** accept a valid Firebase
user token in place of provider verification"): a drift in `make_token`'s defaults, in
`make_test_verifier`, or in the audience/issuer pinning would leave this case green while the
premise "valid" quietly stopped holding. The Google twin at
`tests/e2e/test_google_play_webhook.py:381-393` already carries the missing control
(`claims, _reason = stub_verifier.verify(firebase_bearer); assert claims is not None`, "The control:
a token the application itself would not admit proves nothing about leakage").

**Fix:** Mint the bearer once, verify it through `stub_verifier` and assert the claims are not
`None` before posting it, exactly as the Google case does.

## Info

### IN-01: `values.yaml` cites a `config.py` line that moved

**File:** `k8s/values.yaml:68`
**Why:** "`DEVICECHECK_PRIVATE_KEY_PATH` is a path (`config.py:81`)" — `private_key_path` is declared at `config.py:79`; line 81 is blank and line 82 opens `class AppStoreConfig`. A reader following the citation lands in the wrong class.
**Fix:** Cite the field, not the line: "`DeviceCheckConfig.private_key_path` is a path". Line numbers in this file will drift again on the next edit.

### IN-02: the DeviceCheck block in `.env.example` ships uncommented while every sibling credential block ships commented out

**File:** `.env.example:98-100`
**Why:** The Firebase ADC (`:80-84`), App Store (`:127-131`) and Play (`:169-173`) blocks each ship commented out and each states the rule in its own words: "They ship commented out, with values that parse if you uncomment them, because a copied line is read at boot by the whole service." The DeviceCheck block states the same degradation contract at `:96-97` but ships its three values live, so `cp .env.example .env` yields `key_id="..."`, `team_id="..."` and a path that does not exist. It degrades rather than crashing (`read_private_key` returns `None` for a missing file, `devicecheck.py:78-79`), so this is a consistency defect, not a boot hazard.
**Fix:** Comment the three lines out and append the same closing sentence the other three blocks carry.

### IN-03: stray double space in an expression

**File:** `src/nativespeaker/api/config.py:72`
**Why:** `return  f"https://securetoken.google.com/{self.project_id}"` — two spaces after `return`. Ruff's default `E` selection does not enable the E2xx whitespace rules, so `ruff check` passes and nothing else will ever catch it.
**Fix:** Single space.

### IN-20: `RestoreRequest.provider` contradicts the parity its own comment claims

**File:** `src/nativespeaker/api/schemas/auth.py:48-50`

**Why:** the comment reads "A plain `str`, as `ChallengeRequest.operation` is: an unserved store is
the handler's 403", but the field declares `min_length=1` while `ChallengeRequest.operation`
(lines 15-18) deliberately omits it — "the empty string must stay one of the many 400s,
indistinguishable from every other unissuable value, and a 422 for it alone would make it
distinguishable." As written, `provider: ""` is a 422 `validation_error` while `provider: "amazon"`
is a 403 `operation_not_allowed`, which is the exact distinction the sibling comment says must not
exist. Nothing is disclosed by it (the empty string names no real store), so this is a
consistency defect, not an oracle.

**Fix:** drop `min_length=1` from `provider` so both unserved values reach the handler's 403, or
correct the comment to state why this field diverges.

### IN-21: `PubSubPushRequest.subscription` is declared and never read

**File:** `src/nativespeaker/api/schemas/webhooks.py:40`

**Why:** no code in `src/` reads `body.subscription`. Its sibling `messageId` was deleted for
precisely this reason (37.3-REVIEW-FIX WR-25, 44-REVIEW IN-04: "required but never read"). Being
`str | None = None` it cannot produce the permanent 422 that motivated that deletion, so it is
inert — but it is the same unread envelope field, kept on a different rule.

**Fix:** delete the field, or state in one line why the Pub/Sub envelope is documented here while
`messageId` is not.

### IN-40: raising `log_level` above WARNING makes the "quieted" libraries louder than the application
**File:** `src/nativespeaker/api/logs.py:63-64`
**Why:** `logging.getLogger(name).setLevel(logging.WARNING)` is an absolute pin, not the relative one the comment at `:14` describes ("Pinned **below** the configured level"). `logging.Logger.callHandlers` walks to the root logger's *handlers* without consulting the root logger's *level*, so a library record that passes its own WARNING check is emitted regardless of `root.setLevel(...)`. Meanwhile the application's own lines go through `make_filtering_bound_logger(log_level)`, which does drop them. Measured with `setup_logging("ERROR")`: an application `warning()` produced nothing, while `sqlalchemy.engine` and `httpx` warnings both reached the stream. So `LOG_LEVEL=ERROR` — the setting an operator reaches for to cut noise — yields a stream containing only third-party warnings and no application warnings. `test_logging.py` covers only the `DEBUG` direction (`:260-264`).
**Fix:** pin relative to the configured level, so quieting can only ever subtract:
```python
floor = max(logging.WARNING, logging.getLevelNamesMapping()[log_level.upper()])
for name in _QUIETED_LIBRARIES:
    logging.getLogger(name).setLevel(floor)
```

### IN-41: the comment on `verify_app_store_notification` states the opposite of what happens, and invites the bug it warns about
**File:** `src/nativespeaker/api/app/dependencies.py:196-197`
**Why:** the comment reads "Never `run_in_threadpool`: with online checks off, no code path in the seam performs I/O." But the function is a plain `def`, and FastAPI's solver dispatches every non-coroutine dependency callable through exactly that helper — `fastapi/dependencies/utils.py:674-677`: `elif use_sub_dependant.is_coroutine_callable: solved = await call(...) else: solved = await run_in_threadpool(call, ...)`. The behaviour is right (the JWS chain check is CPU-bound and belongs off the loop); the comment is inverted, and its stated rule — "never run it in a threadpool" — is precisely the change a reader would make by turning the dependency into `async def`, which would move Apple's `x5c` chain verification and three signature checks onto the event loop for every delivery. Its sibling `PubSubPushTokens.verify` (`auth/google_play.py:233-234`) is `async` and calls `run_in_threadpool` explicitly for the same reason, so the two comments contradict each other.
**Fix:** state what the `def` achieves instead of denying it:
```python
# A plain `def`, so FastAPI's solver runs this on the worker threadpool: the chain and
# signature checks are CPU-bound and must not sit on the event loop. With online checks
# off (D-09) the seam performs no I/O, so the threadpool is the whole cost.
```

### IN-60: A dead disjunct in the term guard

**File:** `src/nativespeaker/api/services/subscriptions.py:116-118`

**Why:** `starts_at` is `min(notification.purchased_at or self.evaluated_at, self.evaluated_at)`
(line 114), so `starts_at <= self.evaluated_at` always holds. The disjunct
`term_ends_at <= starts_at` is therefore subsumed by `term_ends_at <= self.evaluated_at` on the next
line and can never be the clause that fires. The comment above it names three conditions where only
two exist.

**Fix:** Drop `term_ends_at <= starts_at` and keep `term_ends_at is None or term_ends_at <=
self.evaluated_at`, and reword the comment to the two cases that remain.

### IN-61: `count_chats` declares `int` and returns what `scalar` gives it

**File:** `src/nativespeaker/api/crud/chats.py:26-28`

**Why:** `AsyncSession.scalar` is typed `Any | None`, so the `-> int` annotation is asserted rather
than met. `services/chats.py:91` and `:107` compare the result with `>=`, which would raise a
`TypeError` rather than a domain error if it were ever `None`. `SELECT count()` always returns a
row, so this is a typing defect and not a live bug.

**Fix:** `return await self.session.scalar(statement) or 0`, or use
`(await self.session.exec(statement)).one()` so the return type is met by the call.

### IN-62: `resilence_config` is misspelled in the public signature

**File:** `src/nativespeaker/api/services/llm.py:18,26`

**Why:** The parameter is spelled `resilence_config` while the type is `ResilienceConfig`. Because
it is passed by keyword, the misspelling has propagated to `app/lifespan.py:207` and
`tests/e2e/test_llm_schema.py:38`, so the wrong spelling is now the contract.

**Fix:** Rename to `resilience_config` and update the two call sites in the same commit.

### IN-63: An existing chat with no messages is reported as an invalid chat

**File:** `src/nativespeaker/api/services/chats.py:159-166`

**Why:** `get_messages` raises `InvalidChatError(chat_id)` when the list is empty. That conflates
"this chat is not yours or does not exist" with "this chat has no messages". `create_chat` always
writes two messages, so the state is unreachable today; it becomes wrong the moment any path writes
a chat row before its first message.

**Fix:** Ask `ChatsDB.get_chat(chat_id, user_id)` for existence and raise `InvalidChatError` only on
`None`; return the empty list otherwise.

### IN-80: the conversion writer's fixture scripts a state PostgreSQL cannot produce, so one guard is exercised vacuously

**File:** `tests/unit/test_conversion_carries_usage.py:463-488`

**Why:** the `writer` fixture scripts `lock_active_grants → []` and `lock_effective_grants → [superseded]`.
Effective is a strict subset of active — `_effective_grants_statement` (`crud/grants.py:26-36`) is
`_active_grants_statement`'s predicate plus the term window — so an effective grant is always in
`marked_active`. With the realistic `[superseded]` the outcome is the same, because
`crud/grants.py:275` filters on `grant.id != superseded.id`; but that filter is therefore never
exercised, and a regression narrowing it to `if marked_active:` would refuse every conversion in
production while this file, which exists precisely because *"every other unit suite replaces the
whole writer with a recorder"*, stayed green. (`tests/schema/test_grant_locks.py` catches it against
a real database, so this is realism, not a hole.)

**Fix:** `async def lock_active(self, user_id): return [superseded]`.

### IN-81: four assertions that cannot fail

**File:** `tests/unit/test_create_user_rollback.py:126,132`, `tests/unit/test_conflict_classification.py:169,191`

**Why:** each sits under a `pytest.raises(IntegrityError)` / `pytest.raises(RuntimeError)` that has
already fixed the exception's type, and asserts `not isinstance(rejection, IdentityAlreadyLinked)` /
`not isinstance(raised, AppError)`. Neither class is in `IntegrityError`'s or `RuntimeError`'s MRO, so
the predicate is constant-true. The `pytest.raises` is the whole test; the line reads as a second
guard and is not one.

**Fix:** delete the four lines, or replace the pair with one honest statement —
`assert type(raised) is IntegrityError`.

### IN-82: the Firebase log spy discards the level, so no case in the file can assert one

**File:** `tests/unit/test_firebase_adapter.py:108-115`

**Why:** the fixture binds the same `lambda event, **fields: records.append((event, fields))` to
`logger.info`, `logger.warning` and `logger.error`, so all three collapse into one undifferentiated
list. `test_the_provider_lookups_own_log_line_carries_no_sdk_message:493` asserts
`firebase_logs == [("firebase_provider_data_malformed", {})]` — which stays green if the line is
demoted to INFO. The sibling `_RecordingLogger` in `test_google_play_notifications.py:207-217` keeps
the level and is the shape to copy.

**Fix:** capture the level in the closure (`partial(_record, level=level)`) and expose
`records(level)`, as `_RecordingLogger` does.

### IN-83: five dead parameters in the Apple test's payload helpers

**File:** `tests/unit/test_app_store_notifications.py:187-188` (`revocation_date`, `expires_in`),
`:203-204` (`in_billing_retry`, `grace_period_in`), `:241-244` (`_notifications(app_apple_id=)`)

**Why:** none is ever overridden by a caller — grep for each keyword returns only the definition.
`revocation_date` feeds `revocationDate`, which `verify()` never reads (only `verify_transaction`'s
`_transaction_status` does, `app_store.py:60`); `in_billing_retry` feeds `isInBillingRetryPeriod`,
which no code path reads at all. They read as knobs a case exercises and are not.

**Fix:** drop the four unused keyword parameters and the `isInBillingRetryPeriod` field, or add the
cases they were written for.

### IN-84: two pairs of Play tests where the second strictly subsumes the first

**File:** `tests/unit/test_google_play_notifications.py:599-616`, `:618-634`

**Why:** `test_every_other_non_2xx_status_is_redelivered` (7 params) asserts
`pytest.raises(InternalError)`; `test_every_other_non_2xx_status_names_itself_in_one_error_line`
(the same 7 params) asserts the same raise *and* the log line. Same for
`test_a_transport_failure_is_redelivered` / `..._names_its_class_in_one_error_line`. Eight redundant
runs that cannot fail without their twin failing first.

**Fix:** delete the two weaker cases.

### IN-100: A frozen-dataclass assertion that any exception satisfies

**File:** `tests/unit/test_identity_accessors.py:330-332`
**Issue:** `pytest.raises(Exception)` around `_unlinked().user = _rows()[0]` passes on an
`AttributeError` from a misspelt attribute name just as readily as on the frozen-instance refusal
it means to prove.
**Fix:** `pytest.raises(dataclasses.FrozenInstanceError)`.

### IN-101: An unused parametrised argument, and one vacuous parametrisation

**File:** `tests/unit/test_purchases_crud.py:111-117`
**Issue:** `test_no_token_value_reaches_the_message` declares `missing` and never reads it; and for
the `no-store-row` seed no token value is in play at all, so that case asserts the absence of
something that was never present.
**Fix:** Drop the `missing` parameter and parametrise over the two seeded cases only.

### IN-102: The Retry-After anti-oracle comparison is taken where the ceiling hides a difference

**File:** `tests/unit/test_quota_resolver.py:453-457`
**Issue:** `test_an_absent_grant_names_the_same_instant` compares the two refusal branches at
`EVALUATED_AT`, where the rollover is ten days away and both branches are clamped to
`RETRY_AFTER_CEILING_SECONDS`. Two genuinely different raw values would still compare equal.
**Fix:** Repeat the comparison at `near_the_boundary` (the instant the sibling case at line 462
already uses), where the value is uncapped.

### IN-103: The scalars-only loop never enters its body for most of the tree

**File:** `tests/unit/test_rejection_vocabulary.py:195-215`
**Issue:** `_sample` falls back to `cls()` for every class absent from `CONSTRUCTOR_ARGUMENTS`, and
those classes answer `log_fields() == {}`, so `test_every_class_in_the_tree_contributes_only_scalars`
iterates nothing for them. `test_the_coverage_is_the_whole_tree_and_not_a_subset`
(`len(_production_family()) > 8`) counts classes, not contributed fields, so it does not close the
gap.
**Fix:** Count the classes whose sample actually produced at least one field and assert that count
against a written-down number, the way `EVENT_NAMES` is written down.

### IN-104: A global-state leak detector that depends on being the last test in its file

**File:** `tests/unit/test_logging.py:320-327`
**Issue:** `test_no_quieted_library_level_outlives_the_test_that_set_it` reads process-global
`logging` state and is meaningful only because it collects after every case that calls
`setup_logging`. Nothing states that dependency, and any order-shuffling plugin turns it into a
false alarm rather than a missing guard.
**Fix:** Move the check into the teardown half of the autouse `_reset_logging` fixture, where it
runs after every case in the file and depends on no ordering.

### IN-120: one quarter of the log-hygiene assertion is vacuous

**File:** `tests/e2e/test_app_store_webhook.py:78-85,499-533`

**Why:** `SENSITIVE_VALUES = (ENVELOPE, TOKEN, OTHER_TOKEN, STORE_TOKEN)`, but
`_drive_every_recording_arm` seeds `STORE_TOKEN` and drives `STORE_TOKEN` and `OTHER_TOKEN` only —
`TOKEN` never enters the request path in that walk, so `assert TOKEN not in rendered` is true by
construction and can never fail. It reads as a fourth guarded value and is not one.

**Fix:** Drop `TOKEN` from `SENSITIVE_VALUES`, or drive an arm that presents it (the walk already
seeds one store token; a second binding under `TOKEN` would make the constant load-bearing).

### IN-121: the Apple grace-window "control" varies two inputs, so it controls neither

**File:** `tests/schema/test_subscription_ingestion.py:442-451`

**Why:** `test_a_grace_window_already_past_leaves_no_effective_grant_control` says "the case above
passes on the window, not on the delivery reaching a write at all", but it changes both the window
(`grace_period_in=-1min`) **and** the status (`SubscriptionStatus.expired`). With `expired` the
writer takes the non-entitled branch and never consults the grace window at all, so the empty
`effective()` is earned by the status, not by the closed window — which is the one thing the
docstring claims it isolates.

**Fix:** Keep `status=SubscriptionStatus.grace_period` and move only the window, matching the Google
twin at :707-721, and assert the refusal that arm actually produces.

### IN-122: `_LOCAL_HOSTS` admits `::1`, which `dsn_for` interpolates unbracketed

**File:** `tests/schema/conftest.py:35,44-49`; `tests/schema/test_harness_guards.py:26-29`

**Why:** `dsn_for` builds `postgres://user:pass@{host}:{port}/{db}`. For `host="::1"` that yields
`…@::1:5432/…`, which is not a parseable DSN — an IPv6 literal needs brackets. The guard case
`test_every_loopback_spelling_is_allowed` only asserts `host in conftest.admin_dsn()`, so it blesses
a spelling that would fail at connect time rather than at the guard.

**Fix:** Bracket IPv6 literals in `dsn_for` (`f"@[{host}]"` when `":" in host`), and have the guard
case connect-parse the DSN rather than substring-match it — or drop `::1` from `_LOCAL_HOSTS`.

### IN-123: `flushes == 0` is documented as "the attempt wrote nothing", but only explicit flushes are counted

**File:** `tests/schema/test_subscription_race.py:105-106`; `tests/schema/test_restore_race.py:147-148`; `tests/schema/test_claim_race.py:181-190`

**Why:** `_RacingSession.flush` increments the counter, but `commit()` delegates straight to
`self._session.commit()`, whose autoflush is invisible to it. The comment "Every write the writer
emits goes through one of these, so zero means the attempt wrote nothing" is true only because every
current write path in `crud/subscriptions.py` (:131, :268, :294, :344, :392) flushes explicitly. A
writer that relied on autoflush would make the witness silently false. The assertions it backs are
today always paired with a row-count or snapshot assertion, so nothing passes vacuously yet.

**Fix:** Count autoflush too — wrap the session's `sync_session` `after_flush` event, or drop the
"wrote nothing" wording and keep the row-count assertion as the sole witness.

### IN-124: `test_create_atomicity.py`'s teardown deletes identity rows before challenges — the order `test_claim_race.py` was just corrected away from

**File:** `tests/schema/test_create_atomicity.py:57-60`

**Why:** `core.auth_challenges.bound_external_identity_id` references `core.external_identities`
with `NO ACTION` (`tests/schema/test_inventory.py:216`). This teardown deletes
`core.external_identities WHERE issuer` first and `core.auth_challenges WHERE preauth_issuer`
second — the inverse of the order `test_claim_race.py:72-80` was just fixed to, with the comment
"a challenge left behind here would both block the delete and leak into the scratch database". It is
safe only while every challenge this module commits is pre-auth-bound; the first bound challenge
here turns teardown into a foreign-key error and a permanent leak into the session-scoped scratch
database.

**Fix:** Delete challenges before identities here too, keyed on both `preauth_issuer` and
`bound_external_identity_id`, matching the sibling.

### IN-125: two class definitions sit directly on the preceding statement

**File:** `tests/e2e/test_sign_out_all.py:53-54`; `tests/e2e/test_restore_subscription.py:627-628`

**Why:** `class _NamedApp` starts on the line after `_auth`'s `return`, and
`class TestTheSameAccountBranchRunsNoOwnerUpdate` on the line after the previous class's last
assertion. Ruff's configured `E` set does not carry E301/E305 outside preview, so nothing catches
these; every other class in both files is separated by two blank lines.

**Fix:** Insert the two blank lines.
