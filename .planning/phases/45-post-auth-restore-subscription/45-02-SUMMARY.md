---
phase: 45-post-auth-restore-subscription
plan: 02
subsystem: api
tags: [fastapi, google-play, androidpublisher, httpx, subscriptions, entitlements]

# Dependency graph
requires:
  - phase: 44-post-webhooks-google-play-rtdn
    provides: PlayDeveloperSubscriptions, _get, _status_for, _GONE_STATUSES, PlaySubscription, GooglePlayConfig.package_name
  - phase: 45-post-auth-restore-subscription
    provides: "45-01: RestoreService, RestoredSubscription, the _verify seam, seed_subscription, the e2e restore module"
provides:
  - "PlayDeveloperSubscriptions.read_for_restore: one client-presented purchase token to a RestoredSubscription"
  - "The stages play_restore_read and play_token_gone, the restore read's whole log vocabulary"
  - "RestoreService._verify dispatching on both PurchaseProvider members, one store call per request"
  - "read_for_restore on the e2e Play fake, on the existing raise-or-return script contract"
  - "The four-arm refusal matrix of both stores, compared as one set of raw response bytes"
affects: [45-03 adoption and owner claim, 45-04 the capped move, 45-05 requirements amendments]

actuals:
  tokens: 25470
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A second entry point classifies the same transport's answer its own way: the webhook wants a redelivery, the app wants a later retry"
    - "The answer is classified at the source rather than by a caught base class, because the operator error subclasses the transport error"
    - "A refusal matrix spanning two stores, asserted equal to each other rather than each valid"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/auth/google_play.py
    - src/nativespeaker/api/services/restore.py
    - src/nativespeaker/api/app/dependencies.py
    - tests/unit/test_restore_proof.py
    - tests/unit/test_auth_package_shape.py
    - tests/e2e/conftest.py
    - tests/e2e/test_restore_subscription.py

key-decisions:
  - "The Play restore read is a second entry point on PlayDeveloperSubscriptions, not a reuse of read with synthesized notification fields, because restore has no source for event_type, notification_uuid or signed_at"
  - "read_for_restore classifies its own answer at the source, so UnmappedStoreProduct is never caught as an InternalError and an unmapped product stays a 500 rather than a 503"
  - "_get no longer maps a transport failure: the webhook wants a redelivery (500) and the app wants a later retry (503), so each entry point classifies httpx.HTTPError itself"
  - "A Play token of another package answers 404 and reaches play_token_gone, so package mismatch gets no stage of its own"
  - "RestoreService._verify names each PurchaseProvider member positively and raises RestoreProviderUnknown only on the unreachable fall-through the router already refuses"

patterns-established:
  - "Shared product resolution: _product_of is read by both entry points, so one product map and one UnmappedStoreProduct raise site serve the webhook and the restore"
  - "Cross-store refusal matrix: the arms of both stores are collected in one case and compared as a set of raw bodies, so an arm that says more than the others fails"

requirements-completed: [RESTORE-01, RESTORE-02]

coverage:
  - id: D1
    description: "A live Google purchase token is reported as a RestoredSubscription whose external id is the token, whose tier comes from the class's own product map and whose status comes from the shared state map"
    requirement: RESTORE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestThePlayReadReportsTheRestoreValueType"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_a_live_purchase_token_attaches_the_paid_grant_and_the_body_reports_it"
        status: pass
    human_judgment: false
  - id: D2
    description: "A caller whose account already owns the Google subscription gets 200, the sync body and Cache-Control no-store, and the one grant it wrote is the subscription grant with its usage row"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_the_one_grant_it_wrote_is_the_subscription_grant_and_its_usage_row"
        status: pass
    human_judgment: false
  - id: D3
    description: "A purchase token Google reports as gone (404 or 410) answers 403 proof_rejected, and no row changes"
    requirement: RESTORE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#test_a_gone_purchase_token_is_a_rejected_proof"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_a_gone_token_reached_play_and_wrote_nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "A Play transport failure, any other non-2xx status, or an absent credential answers 503 verification_temporarily_unavailable"
    requirement: RESTORE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestThePlayAnswerIsClassifiedBeforeItIsParsed"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_an_unconfigured_credential_is_temporarily_unavailable"
        status: pass
    human_judgment: false
  - id: D5
    description: "An unmapped Play product answers 500 internal_error and never 503 — the Pitfall 1 control, at both the unit and the route level"
    requirement: RESTORE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#test_an_unmapped_play_product_is_the_operator_error_and_not_a_503"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_an_unmapped_play_product_is_an_internal_error_and_never_a_503"
        status: pass
      - kind: other
        ref: "test \"$(grep -v '^ *#' src/nativespeaker/api/auth/google_play.py | grep -c 'except InternalError')\" = \"0\""
        status: pass
    human_judgment: false
  - id: D6
    description: "The Play read completes before the first session statement of the request, and exactly one store method is called per request"
    requirement: RESTORE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestTheStoreCallRunsBeforeTheSessionsFirstStatement"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every proof-rejection arm of both stores — the Apple chain, application and environment arms and the Play gone token — answers a byte-identical 403, and the caller's grant and usage row counts are unchanged"
    requirement: RESTORE-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing"
        status: pass
    human_judgment: false
  - id: D8
    description: "No stage, message or log field of the Play refusals carries any part of the purchase token"
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestThePlayRefusalNamesNoPartOfTheToken"
        status: pass
    human_judgment: false
  - id: D9
    description: "The auth package shape ratchet carries its new measured value"
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_package_shape.py#test_it_still_measures_the_recorded_current_shape"
        status: pass
    human_judgment: false

# Metrics
duration: 14 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 02: The Google Play restore branch Summary

**`purchases.subscriptionsv2.get` as a client-presented proof — a second entry point on the Phase 44 class that classifies its own answer, so a gone token is a 403, a transport failure is a 503 and an unmapped product stays a 500.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-09-08T01:04:00Z
- **Completed:** 2026-09-08T01:18:30Z
- **Tasks:** 2
- **Files modified:** 7 (0 created, 7 modified)

## Accomplishments

- `PlayDeveloperSubscriptions.read_for_restore`: keyword-only `package_name` and `purchase_token` to a `RestoredSubscription`, over the same signed read, the same product map and the same state map the webhook uses. No second client and no second credential.
- The answer is classified at the source in one order — no credential, transport failure, gone status, other non-2xx, then parse — so the base internal-error class is caught nowhere on the restore path. That is Pitfall 1, and it is proved absent by an executed case at both the unit and the route level.
- `_get` stopped deciding for its callers. The webhook still answers `InternalError` on a transport failure and Pub/Sub still redelivers; the restore answers `Unavailable` and the app retries later.
- `RestoreService._verify` names each `PurchaseProvider` member. Both stores report the same value type, so the entitled read, the grant locks, the writer and the one commit are one code path below the store call.
- The refusal matrix: three Apple arms and the Play gone token, collected in one case and compared as a set of raw response bytes. The bodies are asserted equal to each other, not merely each valid, and the caller's grant and usage row counts are unchanged across all four.
- Suite **1235 unit / 309 e2e / 205 schema**, `uv run ruff check src tests` clean.

## Task Commits

1. **Task 1 (RED): the failing Play restore cases** — `16f8616` (test)
2. **Task 1 (GREEN): the Play restore read and its classification** — `009e0f9` (feat)
3. **Task 2: the service's Google branch and the shared refusal shape** — `2211330` (feat)

**Plan metadata:** see the `docs(45-02)` commit that carries this file.

## Files Created/Modified

- `src/nativespeaker/api/auth/google_play.py` — `read_for_restore`, the two stage constants, the shared `_product_of`, and `_get` narrowed to sending the read
- `src/nativespeaker/api/services/restore.py` — `play` on the service, `_verify` async and dispatching on both members
- `src/nativespeaker/api/app/dependencies.py` — `get_restore_service` now passes `app.state.play_subscriptions`
- `tests/unit/test_restore_proof.py` — the Play value type, the five classification arms, the anti-oracle case, and the ordering cases for the second store
- `tests/unit/test_auth_package_shape.py` — the ratchet, re-measured at `(8, 24, 58)`
- `tests/e2e/conftest.py` — `read_for_restore`, `script_restore` and `restore_calls` on `FakePlaySubscriptions`
- `tests/e2e/test_restore_subscription.py` — the Google happy path, the four-arm refusal matrix, the 503 and the 500

## Decisions Made

- **A second entry point, not a reuse of `read`.** RESEARCH names this the preferred option, and the reason is structural: `VerifiedNotification` requires a non-optional `notification_uuid` and `event_type`, and a restore has no source for either. Synthesizing them would have put invented values in a value type the webhook path also reads.
- **The answer is classified at the source.** `UnmappedStoreProduct` subclasses `InternalError`, and so did the bare error `_get` used to raise for a transport failure. Any `except InternalError` on this path would have turned an operator configuration error into a 503 that tells the operator nothing. The ordered classification makes the two indistinguishable-by-class outcomes distinguishable by position instead.
- **`_get` no longer maps `httpx.HTTPError`.** The plan's classification order names "`httpx.HTTPError` from `_get`", but `_get` converted it to `InternalError` before any caller could see it, so that arm was unreachable as written. The mapping moved up into `read`, which leaves the webhook's answer byte-identical and lets the restore answer its own 503.
- **Package mismatch has no stage of its own.** The package name travels in the Play URL path, so a token belonging to another application answers 404 and arrives at `play_token_gone`. D-11 lists "package mismatch" among the proof-rejection stages; it is served by an existing stage rather than a new one, and the reasoning is one inline comment at the raise site.
- **`_product_of` is shared.** The line item, the product map lookup and the `UnmappedStoreProduct` raise are read by both entry points, so a later change to the product rule cannot apply to one store and not the other.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The service could not reach the Play class**
- **Found during:** Task 2 (`RestoreService`)
- **Issue:** `get_restore_service` passed `app_store` and `package_name` only. The Google branch had no reader to call, and `src/nativespeaker/api/app/dependencies.py` is not in the plan's `files_modified`.
- **Fix:** one argument, `play=request.app.state.play_subscriptions`, on the same `Request` the dependency already takes for the Apple class.
- **Files modified:** `src/nativespeaker/api/app/dependencies.py`
- **Verification:** every e2e case in `tests/e2e/test_restore_subscription.py` resolves the real dependency through the real router.
- **Committed in:** `2211330`

**2. [Rule 3 - Blocking] The `httpx.HTTPError` arm was unreachable as written**
- **Found during:** Task 1 (`read_for_restore`)
- **Issue:** The plan's step 2 says an `httpx.HTTPError` from `_get` raises `Unavailable`. `_get` caught it and raised `InternalError`, so a `try/except httpx.HTTPError` around the call would never have fired, and the only way to catch it would have been the base class Pitfall 1 forbids.
- **Fix:** `_get` now sends the read and nothing else. `read` wraps its own call and still raises `InternalError`; `read_for_restore` wraps its own and raises `Unavailable(stage="play_restore_read")`.
- **Files modified:** `src/nativespeaker/api/auth/google_play.py`
- **Verification:** `tests/unit/test_google_play_notifications.py::TestThePlayResponseArms::test_a_transport_failure_is_redelivered` still passes unchanged, and `test_a_transport_failure_is_temporarily_unavailable` is the new arm.
- **Committed in:** `009e0f9`

### Departures from the plan text (not auto-fixes)

**3. `tests/unit/test_restore_proof.py` was edited in Task 2 as well.** The plan lists that file under Task 1 only. `test_a_store_the_deployment_does_not_serve_runs_no_statement_at_all` asserted `RestoreProviderUnknown` for `google_play` — the arm 45-01 wrote as a stub and this plan replaces. Leaving it would have made Task 2's suite red. It is now two cases: the Play read runs while the statement count is still zero, and a gone token runs no statement at all. The Apple ordering case and the counting-session control are untouched.

**4. `PlaySubscriptionSource` grew the second entry point.** The Protocol is referenced nowhere but its own definition, so this is documentation rather than a type check. It described a seam with one entry point that now has two, and the service annotates its `play` member with it.

---

**Total deviations:** 2 auto-fixed (2 blocking), plus 2 documented departures from the plan text.
**Impact on plan:** No scope creep. Both blocking fixes were prerequisites for the plan's own stated behaviour, and neither changed what the webhook path answers.

## TDD Gate Compliance

Task 1 carries `tdd="true"` and both gates are present in order: `test(45-02)` at `16f8616` (18 failing cases, all `AttributeError: 'PlayDeveloperSubscriptions' object has no attribute 'read_for_restore'`), then `feat(45-02)` at `009e0f9`. No REFACTOR commit — the GREEN implementation needed no cleanup. Task 2 is a standard `type="auto"` task and is not gated.

The RED run failed for the right reason, and two of the new cases are their own controls: `test_a_subscription_outside_grace_carries_no_window_control` makes the grace-window assertion non-vacuous, and `test_a_gone_token_reached_play_and_wrote_nothing` counts the transport's requests so the refusal matrix cannot pass on a Play read that never happened.

## Known Stubs

| File | Line | Stub | Resolved by |
|---|---|---|---|
| `src/nativespeaker/api/services/restore.py` | 45-47 | No stored subscription row raises `RestoreSubscriptionNotEntitled` | 45-03 (adoption with creation) |
| `src/nativespeaker/api/services/restore.py` | 54-56 | Any owner other than the caller raises `RestoreSubscriptionNotEntitled` | 45-03 (adoption), 45-04 (the capped move) |

Both belong to later plans and carry inline comments naming them. This plan's own stub — 45-01's `_verify` refusal of every provider that is not Apple — is retired, and its ledger entry (`.planning/WINDOWS.md` #22) is closed. No new stub was written.

## Threat Flags

None. Every file touched is inside the plan's declared trust boundaries. T-45-03 (a fabricated token) and T-45-04 (the token in a label) both have executed cases; T-45-05 (the refusal bodies) is the refusal matrix. The prohibition recorded as `unverified` in the plan's `must_haves` — that the refusal must not become an enumeration oracle — is now verified by test: four causes across two stores answer one set of raw bytes, so a body naming which check refused fails the case.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 45-03: both stores now cross the `auth/` seam as `RestoredSubscription`, so the adoption branch is written once and serves both. `_verify` is the only place a provider is named.
- The two remaining refusal arms in `RestoreService.restore` are unchanged and still name the plans that replace them.
- `RESTORE-01` and `RESTORE-02` stay open in REQUIREMENTS.md: `requirements ready-ids` reports 0 of 2 ready, because 45-03, 45-04 and 45-05 also declare them and have no summaries yet.
- Flagged assumption A2 stands, and now covers the second store: no Android app exists either, so no real Play purchase token has reached this deployment. Google's first real answer is authoritative over anything this plan writes.

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*

## Self-Check: PASSED

- All seven modified files exist on disk and carry this plan's changes.
- All three task commits (`16f8616`, `009e0f9`, `2211330`) are in the log.
- Every task acceptance criterion re-run and passing, including both grep criteria: `except InternalError` occurs 0 times outside comments in `google_play.py`, and `read_for_restore` occurs exactly once in `services/restore.py`.
- Both task `<verify>` blocks and the plan-level `<verification>` green: `uv run pytest -q` (1235 passed), `uv run pytest -m e2e -q` (309 passed), `uv run pytest -m schema -q` (205 passed), `uv run ruff check src tests` clean.
</content>
</invoke>
