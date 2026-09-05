---
phase: 44-post-webhooks-google-play-rtdn
plan: 05
subsystem: testing
tags: [google-play, rtdn, pubsub, postgresql, subscriptions, concurrency, idempotency, app-store]

requires:
  - phase: 44-post-webhooks-google-play-rtdn
    provides: "plan 44-01's promoted VerifiedNotification, the composite notification_key_for, the WARNING superseded line, and the unforked Phase 43 service"
provides:
  - "The Google half of tests/schema/test_subscription_ingestion.py: replay, out-of-order, grace and the one-transaction guarantee, on real PostgreSQL"
  - "TestTwoGoogleDeliveriesOfOnePurchaseTokenCommitOnce — two connections raced past the replay read for one purchase token"
  - "The 23503 control that keeps 'a lost race' meaning SQLSTATE 23505 and nothing else"
  - "The Apple five-status map re-measured as total and injective after the status word moved into the provider class"
affects: [44-06, 44-07, 45-restore-subscription]

actuals:
  tokens: 8082
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "One notification factory with a provider keyword, so a Google case is one call and not a second factory"
    - "A grant case is written with its negative control beside it, so the positive one cannot pass vacuously"
    - "A session whose commit records what the transaction held and then raises, which measures atomicity without a second connection"

key-files:
  created: []
  modified:
    - tests/schema/test_subscription_ingestion.py
    - tests/schema/test_subscription_race.py
    - tests/unit/test_app_store_notifications.py

key-decisions:
  - "The absent-grace-end control asserts an UNBOUNDED grant, not an ineffective one: a NULL ends_at is effective by _effective_grants_statement, so the plan's wording did not match the code"
  - "A second control was added for the ineffective half — a grace window already closed — which is Phase 43's CR-02 verbatim"
  - "The race cases keep the harness's own notification key rather than the Google composite, because the composite's stability is the ingestion file's subject and the race is about the unique index"
  - "The one-transaction case interrupts at the commit rather than counting flushes, so it does not break when the service's write order changes"
  - "The Google no-revoked sweep drives the real PlayDeveloperSubscriptions.read through the sibling test's _read, never the private _status_for"

patterns-established:
  - "Provider-aware buyer harness: one `provider` keyword seeds the token row, places the lifecycle key and parametrises every committed read"
  - "A log-level claim is asserted with a monkeypatched module logger, because the service binds its logger at import"

requirements-completed: [PLAYHOOK-02]

coverage:
  - id: D1
    description: "Ingesting the same Google RTDN twice writes exactly one audit.subscription_events row and one core.subscriptions row; the second delivery changes nothing (D-17, OQ-4)"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestAGoogleRedeliveryWritesNothing::test_the_same_rtdn_delivered_twice_leaves_every_count_and_every_grant_unchanged"
        status: pass
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestAGoogleRedeliveryWritesNothing::test_a_later_rtdn_for_the_same_token_does_record_its_own_event_row_control"
        status: pass
    human_judgment: false
  - id: D2
    description: "A Google notification whose eventTimeMillis is older than the stored store_signed_at is refused, the newer state survives, and one WARNING is written (D-12)"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestAnOlderGoogleDeliveryDoesNotDowngradeTheSubscriber::test_the_newer_state_survives_and_the_refusal_is_recorded_at_warning"
        status: pass
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestAnOlderGoogleDeliveryDoesNotDowngradeTheSubscriber::test_the_same_two_deliveries_in_googles_own_order_do_expire_it_control"
        status: pass
    human_judgment: false
  - id: D3
    description: "Two concurrent deliveries for one purchase token produce exactly one committed subscription; the loser raises on SQLSTATE 23505, answers 500, writes nothing partial, and is redelivered by Pub/Sub (PLAYHOOK-01)"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: integration
        ref: "tests/schema/test_subscription_race.py#TestTwoGoogleDeliveriesOfOnePurchaseTokenCommitOnce::test_exactly_one_row_exists_in_each_of_the_three_tables"
        status: pass
      - kind: integration
        ref: "tests/schema/test_subscription_race.py#TestTwoGoogleDeliveriesOfOnePurchaseTokenCommitOnce::test_the_loser_read_the_unique_violation_off_the_sqlstate"
        status: pass
      - kind: integration
        ref: "tests/schema/test_subscription_race.py#TestTwoGoogleDeliveriesOfOnePurchaseTokenCommitOnce::test_an_integrity_failure_that_is_not_a_unique_violation_still_surfaces_control"
        status: pass
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestOneGoogleDeliveryIsOneTransaction::test_an_interrupted_delivery_commits_neither_the_subscription_nor_its_grant"
        status: pass
    human_judgment: false
  - id: D4
    description: "A Google subscription in grace produces an access grant effective at evaluated_at rather than one with an absent or already-past end date (P-01)"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestAGoogleGracePeriodGrantIsEffective::test_the_grant_ends_after_the_captured_instant_and_the_read_returns_it"
        status: pass
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestAGoogleGracePeriodGrantIsEffective::test_an_absent_grace_end_writes_a_grant_carrying_no_end_at_all_control"
        status: pass
      - kind: integration
        ref: "tests/schema/test_subscription_ingestion.py#TestAGoogleGracePeriodGrantIsEffective::test_a_grace_window_already_closed_leaves_no_effective_grant_control"
        status: pass
    human_judgment: false
  - id: D5
    description: "Apple's five Status values still map one-to-one onto the five SubscriptionStatus members after the status word moved into the provider class (D-11, D-13)"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py#TestApplesFiveStatusesStillMapOneToOne::test_the_map_is_total_and_injective_over_apples_five"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py#TestApplesFiveStatusesStillMapOneToOne::test_a_subscription_payload_with_no_status_raises_rather_than_deriving_one"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py#TestRevokedIsAnAppleOnlyWord::test_no_google_state_reaches_revoked_on_either_side_of_its_expiry"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-09-05
status: complete
---

# Phase 44 Plan 05: The Google path measured on real PostgreSQL Summary

**The four database guarantees PLAYHOOK-02 claims the Google path inherits — replay, ordering, concurrency and the grace-period grant — are now executed against real PostgreSQL for `google_play` rather than reasoned about, and Apple's five-status map is re-measured as total and injective after the status word moved into the provider classes.**

## Performance

- **Duration:** 20 min
- **Completed:** 2026-09-05
- **Tasks:** 3
- **Files modified:** 3 (0 created)

## Accomplishments

- The `_notification` factory takes a `provider` keyword and `_Buyer` carries it, so every committed read is parametrised on `provider::text` instead of the literal `'apple'`. A Google case is one call, not a second factory, and all 19 pre-existing Apple cases pass through it unchanged.
- **Replay:** one RTDN ingested twice under the key `notification_key_for` derives from the body alone leaves every count, every grant row and every `updated_at` untouched — with the control that a *later* `eventTimeMillis` yields a different key and does record its own event row, so the case passes on the key repeating rather than on the token being seen twice.
- **Ordering:** a straggler carrying an older `eventTimeMillis` leaves a paying subscriber's `active` row and grant alone, and the refusal is asserted to be at WARNING and not INFO — the level plan 44-01 raised. The control delivers the same two messages in Google's own order and does expire the subscription.
- **Concurrency:** two connections driven past the replay read for one purchase token commit exactly one subscription, one purchase and one event row; the loser fails at the flush on SQLSTATE 23505, answers the generic 500 Pub/Sub redelivers, and the resend finds the event row and flushes nothing.
- **Atomicity:** an ingest interrupted at its commit is proved to have held both the subscription row and its grant inside one transaction, and to have committed neither — so no interruption can leave a subscription row without its grant.
- **Grace:** a grace-period Google subscriber's grant ends after `evaluated_at` and is returned by the real entitlement read, against two controls that fail differently without the fix.
- **Apple:** the five `Status` members are asserted total and injective onto the five `SubscriptionStatus` members, an absent `data.status` is executed and raises, and `revoked` is shown reachable from Apple and from none of Google's nine published states swept on both sides of their expiry.

## Task Commits

1. **Task 1: the redelivery and the grace-period grant** — `d8bbc9e` (test)
2. **Task 2: the older message loses, and two deliveries produce one winner** — `92111e4` (test)
3. **Task 3: Apple's five values, still one-to-one** — `77d91b1` (test)

**Plan metadata:** see the `docs(44-05)` commit that follows this file.

## Files Created/Modified

- `tests/schema/test_subscription_ingestion.py` — the `provider` keyword on the factory and the buyer harness; `events_under`, `subscription_rows`, `built`, `interrupt` and `rtdn_key`; the `service_logs` spy; four new Google classes (redelivery, ordering, one-transaction, grace)
- `tests/schema/test_subscription_race.py` — `provider` and `tier_id` on `notification_for`, `google_notification_for`, and `TestTwoGoogleDeliveriesOfOnePurchaseTokenCommitOnce` with its 23503 control
- `tests/unit/test_app_store_notifications.py` — `APPLE_STATUS_WORDS`, `TestApplesFiveStatusesStillMapOneToOne` and `TestRevokedIsAnAppleOnlyWord`

## Decisions Made

- **The absent-grace-end control asserts an unbounded grant, not an ineffective one.** See the deviation below. `_effective_grants_statement` treats `ends_at IS NULL` as effective, so `grace_period_expires_at = None` does not produce the ineffective grant the plan's wording expected — it produces a grant with no end at all, which is P-01's own first failure mode and a *different* defect.
- **A second control covers the ineffective half.** A grace window already closed writes a grant the entitlement read never returns, which is Phase 43's CR-02 verbatim. The two controls together are what make the positive case non-vacuous: the end written comes from the grace value and from nothing else.
- **The race cases keep the harness's own `notification_uuid`.** The property they measure is the unique index arbitrating two simultaneous writers; the composite key's stability across a redelivery is Task 1's subject and is measured there. Threading the Google composite through the race harness would have meant changing the shared `clean_up` and `counts` LIKE patterns for no gain.
- **The one-transaction case interrupts at the commit, not at the Nth flush.** Counting flushes to find the boundary between the subscription write and the grant write would break the moment the service reorders its writes. Interrupting at the commit records what the transaction held and asserts nothing survived, which is the same claim with no dependence on write order.
- **The Google no-revoked sweep drives the real class.** It imports `_read` and `PUBLISHED_STATES` from `tests/unit/test_google_play_notifications.py` and reads through `PlayDeveloperSubscriptions`, rather than calling the private `_status_for` — the same sibling-import pattern `tests/schema/test_subscription_race.py` already uses for `_notification`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's negative control asserts a state the code does not produce**
- **Found during:** Task 1
- **Issue:** The plan's acceptance criterion reads *"A negative control demonstrates that an absent grace end produces an **ineffective** grant"*. It does not. `_effective_grants_statement` (`src/nativespeaker/api/crud/grants.py:24-36`) matches `ends_at IS NULL` **or** `ends_at > evaluated_at`, so a grant written with `grace_period_expires_at = None` is unbounded and is returned by the entitlement read forever. Writing the control as specified would have asserted something false and failed.
- **Fix:** Split the control in two, so both of P-01's stated failure modes are measured: `test_an_absent_grace_end_writes_a_grant_carrying_no_end_at_all_control` asserts `ends_at is None` (the unbounded grant, P-01's first sentence), and `test_a_grace_window_already_closed_leaves_no_effective_grant_control` asserts the entitlement read returns nothing for an already-past window (CR-02 verbatim, and the genuinely *ineffective* case). The plan's intent — that the positive case cannot pass vacuously — is satisfied more strongly by two controls than by the one that was written.
- **Files modified:** tests/schema/test_subscription_ingestion.py
- **Verification:** `uv run pytest -m schema tests/schema/test_subscription_ingestion.py -q` — 24 passed
- **Committed in:** `d8bbc9e`

**2. [Rule 3 - Blocking] `session.execute()` inside the interrupting session raised a SQLModel DeprecationWarning**
- **Found during:** Task 2
- **Issue:** Reading the uncommitted row counts through `AsyncSession.execute()` emits SQLModel's *"You probably want to use `session.exec()`"* warning, and `exec()` does not accept a `text()` construct. A new test that ships a deprecation warning is noise the next reader has to re-diagnose.
- **Fix:** Took the session's own connection with `await self._session.connection()` and ran the read there, which sees the same uncommitted transaction and emits nothing.
- **Files modified:** tests/schema/test_subscription_ingestion.py
- **Verification:** `uv run pytest -m schema -q` — 205 passed, 1 warning (the unrelated pre-existing pydantic-v1 one)
- **Committed in:** `92111e4`

### Deliberate departures from the written plan

**3. `_notification` did not need `status` and `tier_id` added.** The plan's Task 1 action says to give the factory *"plus the `status` and `tier_id` keywords the promoted value type now requires"*. Plan 44-01's deviation 1 already added both when it re-greened the schema suite against the promoted value type. Only `provider` was missing, and only `provider` was added.

**4. `deliver` was refactored into `built` + `deliver` rather than extended.** The `interrupt` case needs the *notification* rather than an ingestion, and duplicating `deliver`'s eight-keyword term placement into a second method would have been the second copy this phase exists to avoid. `deliver(**placement)` now forwards to `built(**placement)`; every existing call site is unchanged because all of them already pass keywords.

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking) and 2 documented departures.
**Impact on plan:** No scope creep. The bug fix strengthens the acceptance criterion it could not satisfy literally; the rest is mechanical.

## Issues Encountered

- Both preconditions held on first check: the scratch PostgreSQL applied the migration and the two-connection race harness ran without contention.
- `requirements mark-complete PLAYHOOK-02` ticked the checkbox but reported `table_unmatched` for the traceability surface. That table records the phase as one range row, `PLAYHOOK-01 … PLAYHOOK-03`, which carries no per-id anchor for the tool to rewrite. The row already names PLAYHOOK-02 and its Phase 43 binding in prose, so nothing was hand-edited: rewriting a shared range row to satisfy a tool's parser is not this plan's scope.

## User Setup Required

None. The `schema` marker is deselected by default, so these cases run under `uv run pytest -m schema -q` and require the `DB_*` environment `tests/schema/conftest.py` already documents.

## Known Stubs

None. No case in this plan asserts a placeholder, and no assertion was left commented out or skipped.

## Threat Flags

None. Every case added maps onto a row already in this plan's threat register — T-44-21 (replay), T-44-22 (out-of-order), T-44-23 (concurrent delivery) and T-44-24 (grant term). No new network surface, auth path, file access or schema change was introduced: this plan writes only tests.

## Next Phase Readiness

- The four `google_play` guarantees are now regression-guarded, so plans 44-06 and 44-07 can change the Google seam and find out immediately if any of them breaks.
- Plan 45 inherits the provider-aware `_buyer` harness: a restore-route case is `_buyer(uri, provider=PurchaseProvider.google_play)` with no further harness work.
- `SubscriptionStatus.revoked` is now measured as Apple-only rather than only recorded in OQ-1, so a later plan that wants a Google revocation signal will fail `test_no_google_state_reaches_revoked_on_either_side_of_its_expiry` and be forced to say so.

---
*Phase: 44-post-webhooks-google-play-rtdn*
*Completed: 2026-09-05*

## Self-Check: PASSED

- Every modified file exists on disk, and this summary with them.
- Every task commit exists in `git log`: `d8bbc9e`, `92111e4`, `77d91b1`.
- Every `coverage[].ref` names a case that exists in the file it names, verified by `pytest --collect-only`.
- Plan verification re-run at close: `uv run pytest -m schema -q` 205 passed, `uv run pytest -q` 1190 passed, `uv run ruff check src tests` clean.
