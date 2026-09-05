---
phase: 44-post-webhooks-google-play-rtdn
plan: 03
subsystem: payments
tags: [google-play, rtdn, pubsub, subscriptions, oidc, jwt, httpx, pytest]

requires:
  - phase: 44-post-webhooks-google-play-rtdn
    provides: "plan 44-01's auth/google_play.py — the one-state map, the undifferentiated non-2xx Play arm, and build_google_push_verifier with its guard unexecuted"
provides:
  - "The complete Google state map: nine published SUBSCRIPTION_STATE_ values onto four SubscriptionStatus members, with expired as the fall-through"
  - "grace_period_expires_at from the line item's own expiryTime during grace, so a grace-period grant is written with an end date"
  - "_play_answer_is_usable: 404 and 410 answer 200 having written nothing; every other failure still redelivers"
  - "tests/unit/test_google_play_notifications.py — 76 cases over the state map, the four no-write arms, the five push-token refusals and the JWKS boot guard"
affects: [44-04, 44-05, 44-06, 44-07, 45-restore-subscription]

actuals:
  tokens: 7375
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "A store state map keyed on the store's own prefixed literals, with the unentitled status as the dict default"
    - "The one value whose answer depends on a date is decided before the lookup, never inside the map"
    - "A provider response is classified in one ordered function with no default arm, following auth/devicecheck.py"

key-files:
  created:
    - tests/unit/test_google_play_notifications.py
  modified:
    - src/nativespeaker/api/auth/google_play.py
    - tests/unit/test_auth_package_shape.py

key-decisions:
  - "Every state literal carries Google's SUBSCRIPTION_STATE_ prefix: 44-CONTEXT.md D-11's bare words match nothing Google sends"
  - "SUBSCRIPTION_STATE_CANCELED is decided before the dict lookup, because it is the one value whose answer depends on a date"
  - "SubscriptionStatus.revoked is unreachable on the Google path and that is recorded in one comment, not left as an omission"
  - "In grace, the line item's own expiryTime is both expires_at and grace_period_expires_at, because SubscriptionPurchaseV2 has no grace field"
  - "404 and 410 from the Play read yield None and a 200, because Pub/Sub acknowledges only five statuses and a retry on a gone token loops until retention expires"

patterns-established:
  - "The skip arm for a provider body is a presence test on the one body we act on, pinned at the source by an AST case so no branch can enumerate the others"
  - "A claim the store may stop sending is compared after decode and never placed in the verifier's require list"
  - "A logger spy, not structlog capture_logs: the module-level logger caches its binding at import"

requirements-completed: []

coverage:
  - id: D1
    description: "All nine subscriptionState values Google publishes map onto core.subscription_status, and an unlisted or future value maps to expired rather than to an entitled status"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheStateMap::test_each_state_produces_its_status (13 parametrised inputs)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheStateMap::test_a_state_this_build_has_never_seen_is_not_entitled"
        status: pass
      - kind: other
        ref: "test \"$(grep -cE '\"(ACTIVE|IN_GRACE_PERIOD|ON_HOLD|PAUSED|CANCELED|EXPIRED|PENDING|UNSPECIFIED)\"' src/nativespeaker/api/auth/google_play.py)\" = \"0\" — no bare Google state word is a quoted key"
        status: pass
    human_judgment: false
  - id: D2
    description: "A Google subscription in SUBSCRIPTION_STATE_IN_GRACE_PERIOD produces a grace_period status whose grace_period_expires_at is the line item's own expiryTime, so the grant written for it is effective (P-01)"
    requirement: "PLAYHOOK-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheGraceWindowGoogleDoesNotName::test_a_grace_period_subscription_carries_the_end_of_its_window"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheGraceWindowGoogleDoesNotName::test_every_other_state_carries_no_grace_window (8 states)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A verified push whose message.data cannot be decoded logs at ERROR with closed-set labels and answers 200 with nothing written (D-04)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheUndecodableBody::test_the_decode_yields_none_and_records_one_error (4 payload shapes)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheUndecodableBody::test_the_decoder_itself_answers_none_rather_than_raising"
        status: pass
    human_judgment: false
  - id: D4
    description: "A verified RTDN that carries no subscriptionNotification logs which body it carried at INFO, makes no Play call, and answers 200 — decided on presence, never on a closed list of names (D-05)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheBodiesThatAreNotSubscriptions::test_each_body_yields_none_naming_itself_and_makes_no_play_call (4 bodies, against a Play seam that raises if called)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheBodiesThatAreNotSubscriptions::test_a_body_google_adds_later_answers_here_rather_than_falling_through"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheBodiesThatAreNotSubscriptions::test_no_function_in_the_module_names_the_four_other_bodies"
        status: pass
    human_judgment: false
  - id: D5
    description: "A message whose packageName differs from the configured package name is refused before any Play call is made (D-18)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePackageNameCheck::test_a_foreign_package_is_refused_before_any_play_call"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePackageNameCheck::test_the_configured_package_reaches_the_play_read_with_this_token"
        status: pass
    human_judgment: false
  - id: D6
    description: "A Play GET answering 404 or 410 logs one ERROR and yields None; every other non-2xx status and every httpx.HTTPError raises InternalError so Pub/Sub redelivers (OQ-5, D-20)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePlayResponseArms::test_a_gone_purchase_token_yields_none_and_records_one_error (404, 410)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePlayResponseArms::test_every_other_non_2xx_status_is_redelivered (400, 401, 403, 429, 500, 502, 503)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePlayResponseArms::test_a_transport_failure_is_redelivered"
        status: pass
    human_judgment: false
  - id: D7
    description: "A push token whose signature, aud, iss, email or email_verified is wrong is refused, all five with the same class and body and differing only in stage (D-09, T-44-12, T-44-15)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePushTokenCheck::test_each_arm_refuses_with_its_own_stage (5 arms against a real JWTVerifier)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestThePushTokenCheck::test_every_refusal_is_one_class_with_one_body"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheClaimPinsArePostDecodeComparisons::test_email_is_compared_after_decode_rather_than_required"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheClaimPinsArePostDecodeComparisons::test_bounded_reason_still_has_exactly_five_members"
        status: pass
    human_judgment: false
  - id: D8
    description: "An unreachable JWKS endpoint at boot yields a None verifier and one route's 503, never a pod that will not start (F-04; closes 44-01's D6)"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheJwksWarmUpGuard::test_an_unreachable_jwks_endpoint_raises_at_construction"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheJwksWarmUpGuard::test_the_builder_answers_none_and_lets_the_pod_boot"
        status: pass
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheJwksWarmUpGuard::test_an_unconfigured_value_answers_none_without_a_fetch (push_audience, push_service_account_email)"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-09-05
status: complete
---

# Phase 44 Plan 03: The Google seam filled out from the proven slice Summary

**All nine `SUBSCRIPTION_STATE_` values Google publishes now have an executed answer with `expired` as the fall-through, a grace-period subscriber's grant carries an end date taken from the line item's own `expiryTime`, and the four arms that answer 200 without writing are each reached by a named case rather than by a fall-through.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-09-05T11:17:02Z
- **Completed:** 2026-09-05T11:27:32Z
- **Tasks:** 3
- **Files modified:** 3 (1 created)

## Accomplishments

- `_STATES` grew from one entry to four, and `_status_for` gained the `SUBSCRIPTION_STATE_CANCELED` arm that decides on a date before the lookup. Every literal carries Google's own prefix. The thirteen parametrised inputs cover all nine published values, the three CANCELED date cases, and one value this build has never seen — which lands on `expired`, not on anything entitled.
- **The grace-window defect is closed.** `PlayDeveloperSubscriptions.read` sets `grace_period_expires_at` to the line item's `expiryTime` while the state is `SUBSCRIPTION_STATE_IN_GRACE_PERIOD`, and to `None` otherwise. Google carries no separate grace field, so leaving it `None` would have sent `ends_at=None` into every grace-period grant write — Phase 43's CR-02 reproduced from a different cause.
- `_play_answer_is_usable` classifies the Play answer in one ordered function with no default arm, following `auth/devicecheck.py`. 404 and 410 log one ERROR and yield `None`, so a purchase token Google says is gone stops the redelivery loop instead of running it until retention expires. Every other non-2xx status, and every `httpx.HTTPError`, still raises `InternalError`.
- The four arms that answer without writing are now **executed**, not merely written: the undecodable body over four payload shapes, the four non-subscription bodies against a Play seam that fails the case if it is called, a body Google has not shipped yet, and the `packageName` refusal.
- The push-token check runs against a **real** `JWTVerifier` over the offload suite's counted JWKS transport, with RS256 tokens minted from this suite's own keypair. All five refusal arms produce the same `NotificationRejected` class and the same one-field body, differing only in the `stage` log field.
- **44-01's D6 is closed.** The JWKS warm-up raise is now measured rather than assumed: `JWTVerifier.__init__` raises `PyJWKClientConnectionError` on an unreachable endpoint, and `build_google_push_verifier` answers `None` instead of propagating. An unconfigured `push_audience` or `push_service_account_email` answers `None` with the transport never touched.

## Task Commits

1. **Task 1 (RED): the failing state-map and grace-window cases** - `e958aaf` (test)
2. **Task 1 (GREEN): nine states onto five, and the grace window** - `515aa12` (feat)
3. **Task 2 (RED): the four arms that answer without writing** - `89c0668` (test)
4. **Task 2 (GREEN): the definitive 404/410 arm** - `cc8e89f` (feat)
5. **Task 3: the claim pins and the boot guard** - `83c1a31` (test)

**Plan metadata:** the `docs(44-03)` commit that carries this file.

## Files Created/Modified

- `tests/unit/test_google_play_notifications.py` - 76 cases: the state map, the grace window, the four no-write arms, the source-level presence pin, the five push-token refusals, the two claim pins and the JWKS boot guard
- `src/nativespeaker/api/auth/google_play.py` - the four-entry `_STATES`, the CANCELED arm, the grace window, `_GONE_STATUSES` and `_play_answer_is_usable`; `read` and the `PlaySubscriptionSource` Protocol widened to `VerifiedNotification | None`
- `tests/unit/test_auth_package_shape.py` - the recorded auth-package function count raised from 52 to 53

## Decisions Made

- **Every state literal carries the `SUBSCRIPTION_STATE_` prefix.** `44-CONTEXT.md` D-11's table is written with the bare words and its count of seven is short by two. A dict keyed on `"ACTIVE"` matches nothing Google sends and routes every subscriber to `expired`, so this correction is load-bearing rather than cosmetic. The `<verify>` grep for a bare quoted state word is the standing guard.
- **`SUBSCRIPTION_STATE_CANCELED` is handled before the dict lookup.** It is the one value whose answer depends on a date. Google's own field text says *canceled but not expired*, so an unexpired term is still entitled; the `else expired` branch is the safety net, not the normal path.
- **`SubscriptionStatus.revoked` is unreachable here, recorded in one comment.** `subscriptionsv2` publishes no citable revocation signal, and a revoked subscription reports `SUBSCRIPTION_STATE_EXPIRED` with the reason preserved in `event_type` 12. Plan 44-07 records the provider asymmetry under the requirement.
- **The D-05 skip arm stays a presence test, pinned at the source.** An AST case walks every function and method in the module and asserts that none of the four other body names appears in one. A three-member allow-list would let `pendingRefundReviewNotification` fall through into a Play call that has no purchase token to make.
- **The D-04 rationale in the code is Pub/Sub's real rule, not `44-CONTEXT.md`'s.** Cloud Pub/Sub acknowledges only 102, 200, 201, 202 and 204; there is no 4xx-is-permanent rule, so a 400 would loop for the whole retention window. The behaviour is unchanged and better supported: 200 is the only answer that stops a redelivery on a payload that can never parse. The same reasoning is what makes 404/410 an answer rather than a retry.
- **The push-token cases use a logger spy, not `structlog.testing.capture_logs`.** The module-level logger caches its binding at import, so capture would observe nothing — the same note `tests/unit/test_exception_handlers.py` already carries.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tests/unit/test_auth_package_shape.py` records the auth package's function count**
- **Found during:** Task 2
- **Issue:** `CURRENT = (8, 23, 52)` is a deliberate ratchet whose own docstring says *"A later phase that grows the package has to come here and write the new number down."* Adding `_play_answer_is_usable` to `auth/google_play.py` made the walk measure 53 and failed the case. The file is not in this plan's `files_modified`.
- **Fix:** Recorded the new number, `(8, 23, 53)`. Nothing else in the file changed, and its control case (`TestTheMeasurementFires`) is untouched.
- **Files modified:** tests/unit/test_auth_package_shape.py
- **Verification:** `uv run pytest -q` — 1164 passed at that commit
- **Committed in:** `cc8e89f`

### Departures worth naming

**2. `PlaySubscriptionSource.read` and `PlayDeveloperSubscriptions.read` widened to `VerifiedNotification | None`.** The plan's behaviour statement — *"a Play GET answering 404 or 410 … yields `None`"* — requires it. `app/dependencies.py` already declares `VerifiedNotification | None` and the route already guards on `None`, so no caller changed.

---

**Total deviations:** 1 auto-fixed (1 blocking), plus 1 type-signature departure the plan's own behaviour required.
**Impact on plan:** No scope creep. The ratchet update is the bookkeeping that file exists to force.

## Issues Encountered

None.

## User Setup Required

None in this plan. The three `GOOGLE_PLAY_` deployment values and the external-console steps are documented by plan 44-02 in `44-USER-SETUP.md`.

## Known Stubs

None. Both stubs recorded by plan 44-01 are closed here:

- `_STATES` held one state and `grace_period_expires_at` was always `None` — now four entries, the CANCELED arm, and the grace window.
- `PlayDeveloperSubscriptions.read` treated every non-2xx Play status the same — now the ordered classification with the definitive 404/410 arm.

## Threat Flags

None. Every surface this plan touches is in the plan's own threat register: the two claim pins (T-44-12), the RS256 pin inherited from `JWTVerifier` (T-44-13), the state map's unentitled fall-through (T-44-14), the one-class refusal (T-44-15) and the two arms that stop a redelivery loop (T-44-16). T-44-17, the Play quota, stays accepted and unchanged.

One register entry is worth restating. **T-44-14 is the reason this plan exists.** Before it, every Google subscriber whose state was not `SUBSCRIPTION_STATE_ACTIVE` — including every one in grace and every one on hold — fell through to `expired`. That failed closed, so nobody was over-entitled, but a paying customer in grace would have lost their entitlement silently. The state map and the grace window are each a correctness fix, not a completeness fix.

## Next Phase Readiness

- `auth/google_play.py` is complete for this phase. Plans 44-04 (configuration), 44-06 and 44-07 land on a seam with no remaining stubs.
- **`PLAYHOOK-01` and `PLAYHOOK-02` are not marked complete.** `requirements.ready-ids` reported 0 of 2 ready: both are declared by sibling plans in this phase that have no summary yet, and they stay open until the last declaring plan finishes.
- Plan 45 consumes `PlaySubscriptionSource`, whose `read` now answers `None` for a purchase token Google reports gone. A restore route calling it must handle that arm rather than assume a value type.
- No real Pub/Sub push and no real Play response has ever reached this code. Everything above is executed against minted tokens and stubbed transports; whether Google's live tokens and answers match Google's declared shapes is the standing untested-by-construction fact this suite's docstring records.

---
*Phase: 44-post-webhooks-google-play-rtdn*
*Completed: 2026-09-05*

## Self-Check: PASSED

- Every file named above exists on disk: `tests/unit/test_google_play_notifications.py`, `src/nativespeaker/api/auth/google_play.py`, `tests/unit/test_auth_package_shape.py`, and this summary.
- All five task commits exist in `git log`: `e958aaf`, `515aa12`, `89c0668`, `cc8e89f`, `83c1a31`.
- Every `coverage[].ref` names a case that exists in the file it names.
- All three tasks' acceptance criteria were re-run at close: 5 of 5 for Task 1, 5 of 5 for Task 2, 6 of 6 for Task 3.
- Plan verification re-run at close: `uv run pytest -q` 1178 passed, `uv run pytest -m e2e -q` 277 passed, `uv run pytest -m schema -q` 189 passed, `uv run ruff check src tests` clean, and `tests/unit/test_jwks_offload.py` is unchanged in `git diff be06c6f..HEAD`.
