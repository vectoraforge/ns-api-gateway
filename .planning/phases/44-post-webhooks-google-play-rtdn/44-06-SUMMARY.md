---
phase: 44-post-webhooks-google-play-rtdn
plan: 06
subsystem: testing
tags: [google-play, rtdn, pubsub, oidc, jwt, fastapi, httpx, e2e, logging, pytest]

requires:
  - phase: 44-post-webhooks-google-play-rtdn
    provides: "plan 44-01's route, real_google_play_seam and composite replay key; plan 44-03's nine-state map, the four no-write arms and the five push-token refusals proved at unit level"
provides:
  - "tests/e2e/conftest.py — FakePlaySubscriptions, scripted_play_subscriptions, scripted_google_play and unconfigured_google_play"
  - "The Google refusal matrix on the wire: seven stages, nine pushes, one byte-identical 401 body"
  - "A source-read control asserting the parameter set equals the set of reachable refusal arms"
  - "The two 200-without-writing arms and the three 500 arms executed through the real application"
  - "The sensitive-value walk covering the push token, the envelope, both attribution tokens and the Google purchase token"
  - "AttributionConflict logs the purchase row's own key, never the lifecycle key"
affects: [44-07, 45-restore-subscription]

actuals:
  tokens: 35397
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A refusal matrix whose completeness control reads the raise sites as source, so a stage added later fails the control rather than shipping untested"
    - "A raise site that carries the database row's own primary key, so the operator's log handle contains no store-supplied value"
    - "Two Google seam fixtures: the real verifier for the arms that must be genuinely verified, the scripted read for the arms that must fail"

key-files:
  created: []
  modified:
    - tests/e2e/conftest.py
    - tests/e2e/test_google_play_webhook.py
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/services/subscriptions.py
    - tests/unit/test_subscription_attribution.py
    - tests/unit/test_rejection_vocabulary.py
    - tests/e2e/test_app_store_webhook.py

key-decisions:
  - "AttributionConflict is raised with the store_purchases row id and logs purchase_id: on the Google path external_id is the purchase token itself, so the Phase 43 field was a credential in an ERROR record"
  - "The refusal matrix drives the real seam rather than scripting a raise, because the stage set is the thing under test and only the real verifier produces the five bounded reasons"
  - "The completeness control reads both raise sites with ast, so it measures the code rather than restating the parameter list"
  - "unconfigured_google_play replaces 44-01's unconfigured_google_play_seam rather than joining it: one fixture, and it now unconfigures both Google classes"
  - "The unconfigured Play client is a transport that fails the case if it is reached, so 'an incomplete deployment calls nothing' is measured and not assumed"

patterns-established:
  - "Refusal completeness control: walk the raise sites' AST for the literal stage strings, widen the one computed stage to its bounded-reason enum, compare to the parameter set"
  - "A log field that identifies a row carries the row's primary key when any candidate business key is provider-supplied"

requirements-completed: []

coverage:
  - id: D1
    description: "Every refusal arm of the Google route answers a byte-identical 401 body, so the response tells a caller nothing about which check refused it (D-20, T-44-25)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestEveryRefusalAnswersTheOneBody::test_each_refusal_answers_the_same_401_body (9 pushes over 7 stages)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestEveryRefusalAnswersTheOneBody::test_a_refused_push_writes_nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "The refusal matrix is complete: the parameter set equals the set of arms the code can actually refuse with, read from the two raise sites as source"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestEveryRefusalAnswersTheOneBody::test_every_reachable_arm_is_covered_by_one_parameter"
        status: pass
    human_judgment: false
  - id: D3
    description: "A deployment with no Play configuration still registers the route and answers 503 rather than 404 (D-14, D-18)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestAnIncompleteDeploymentStillRegistersTheRoute::test_an_unconfigured_deployment_answers_503"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestAnIncompleteDeploymentStillRegistersTheRoute::test_both_callback_routes_are_registered_while_the_seam_is_unconfigured"
        status: pass
    human_judgment: false
  - id: D4
    description: "A verified push with an undecodable payload answers 200 having written nothing and having called Play not at all (D-04, T-44-28)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestTheTwoArmsThatAnswerWithoutWriting::test_an_undecodable_body_answers_200_and_records_one_error"
        status: pass
    human_judgment: false
  - id: D5
    description: "A verified push carrying pendingRefundReviewNotification and no subscriptionNotification answers 200, names the body it carried at INFO, and makes no Play call (D-05)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestTheTwoArmsThatAnswerWithoutWriting::test_a_body_this_route_does_not_act_on_answers_200_and_makes_no_play_call"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'pendingRefundReviewNotification' tests/e2e/test_google_play_webhook.py)\" -ge 1 — 3 occurrences"
        status: pass
    human_judgment: false
  - id: D6
    description: "A failed Play call, an unmapped product and an attribution conflict each answer 500 with the shared internal body so Pub/Sub redelivers, and none writes a row (D-20)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestEveryFailedReadAnswersTheShared500::test_each_failure_answers_500_and_writes_nothing (3 failures)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestEveryFailedReadAnswersTheShared500::test_the_scripted_read_was_asked_for_this_delivery"
        status: pass
    human_judgment: false
  - id: D7
    description: "A Firebase bearer the application itself would admit produces the same 401 here, so the application's own identity gate does not leak into this route (T-44-27)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestEveryRefusalAnswersTheOneBody::test_a_valid_firebase_token_does_not_change_the_refusal"
        status: pass
    human_judgment: false
  - id: D8
    description: "No log record produced by the route carries the OIDC push token, the base64 envelope, an attribution token or the Google purchase token (T-44-26)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestNoRecordCarriesASensitiveValue::test_no_record_carries_a_token_the_envelope_or_the_purchase_token"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestNoRecordCarriesASensitiveValue::test_the_walk_sees_the_records_the_deliveries_produced"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_google_play_webhook.py#TestNoRecordCarriesASensitiveValue::test_the_conflicting_delivery_left_the_first_owner_as_it_was"
        status: pass
    human_judgment: false
  - id: D9
    description: "The attribution refusal identifies the disputed purchase by the row's own primary key, so no store-supplied value reaches the ERROR record on either provider"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_subscription_attribution.py#TestTheConflictArm::test_the_refusal_carries_the_rows_own_key_and_not_the_token"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py#TestAChangedAttributionIsRefusedAndNothingIsWritten::test_the_refusal_logs_once_and_never_carries_the_attribution_token"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-09-05
status: complete
---

# Phase 44 Plan 06: The Google answer surface on the wire Summary

**Every status `/webhooks/google-play/rtdn` can answer is now executed against the real application — seven refusal stages behind one byte-identical 401, a 503 from a route that is still registered, two 200s that write nothing and three 500s that make Pub/Sub redeliver — and the walk that proves no log carries a token found one that did.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-09-05T12:00:22Z
- **Completed:** 2026-09-05T12:10:52Z
- **Tasks:** 2
- **Files modified:** 7 (0 created)

## Accomplishments

- **The refusal matrix is closed.** Nine pushes over the seven stages this route can refuse with — no credential, four ways for the signature or the pinned claims to fail, a foreign audience, a foreign issuer, an expired token, an empty subject, and a foreign package name — each answer 401 with the same 24 bytes on the wire. The distinguishing detail exists in exactly one place: the WARNING record the operator reads.
- **The completeness control reads the code, not the list.** `_raised_refusal_stages` walks the AST of `verify_google_play_notification` and of `auth/google_play.py`, collects every `NotificationRejected(stage=...)`, and widens the one computed stage to all five `BoundedReason` members. An eighth arm added later fails this control rather than shipping untested. It is measured, not asserted: the walk finds the two literal stages and the computed one, and the seven-member union matches the parameter set exactly.
- **The fail-closed pair now unconfigures the whole seam.** `unconfigured_google_play` replaces both Google classes with the `None`-holding pair an incomplete configuration leaves behind, over a Play transport that fails the case if it is reached at all. The route answers 503 and stays in the registered route set.
- **Both 200-without-writing arms run through the real application.** An undecodable `message.data` answers 200 with one ERROR record and no row and no Play call; a body carrying `pendingRefundReviewNotification` and no `subscriptionNotification` answers 200, names itself at INFO, and reaches Play not at all. That body is deliberate: it is the one D-05 does not name, so a closed three-member list would let it fall through into a Play call it has no purchase token to make.
- **The three 500 arms are proved on the wire.** A failed Play call, an unmapped product and an attribution conflict each answer the shared `internal_error` body with no subscription row and no event row, which is the answer that makes Pub/Sub redeliver rather than acknowledge.
- **A Firebase bearer the application would admit buys a bad push nothing.** The case verifies the token against the app's own verifier first, so it cannot pass vacuously against a token nothing would have accepted.
- **The sensitive-value walk found a real leak, and it is fixed.** See the deviation below.

## Task Commits

1. **Task 1: the two scripted Google fixtures** — `94c9daa` (test)
2. **Deviation fix: the attribution refusal names the row, not the lifecycle key** — `c444499` (fix)
3. **Task 2: the answer surface on the wire** — `6bd45e1` (test)

**Plan metadata:** the `docs(44-06)` commit that carries this file.

## Files Created/Modified

- `tests/e2e/conftest.py` — `FakePlaySubscriptions` (a raise-or-return fake behind `PlaySubscriptionSource` with an `async` read, no default answer and a record of every call), `AcceptingPushTokens`, the `scripted_play_subscriptions` and `scripted_google_play` fixtures, and `unconfigured_google_play` in place of 44-01's `unconfigured_google_play_seam`
- `tests/e2e/test_google_play_webhook.py` — 26 cases: the tracer's five, the nine-parameter refusal matrix with its source-read control, the refused-push write check, the Firebase case, the two 200 arms, the three 500 arms with their call control, and the three-case sensitive-value walk
- `src/nativespeaker/api/errors.py` — `AttributionConflict` takes the purchase row id and logs `purchase_id`
- `src/nativespeaker/api/services/subscriptions.py` — the refusal is raised with `recorded.id`
- `tests/unit/test_subscription_attribution.py` — the log-field case renamed and widened to assert the lifecycle key is absent
- `tests/unit/test_rejection_vocabulary.py` — the constructor sample takes a UUID
- `tests/e2e/test_app_store_webhook.py` — the Apple conflict case reads `purchase_id`

## Decisions Made

- **`AttributionConflict` identifies the row by its own primary key.** Phase 43 decided the lifecycle key was the operator's handle and that decision was right for Apple, whose `originalTransactionId` is not a credential. 44 D-10 made `external_id` the Google purchase token, which turned the same field into a credential written at ERROR. The row id is a strictly better handle — `SELECT * FROM core.store_purchases WHERE id = …` resolves `external_id` and everything else — and it carries nothing the store supplied. No operator capability is lost; the Apple path is improved by the same edit.
- **The refusal matrix drives the real seam, not a scripted raise.** The Apple file scripts `NotificationRejected(stage=…)` because Apple's stages come from a library enum. Google's five come out of a real `JWTVerifier`, so scripting the raise would assert the parameter list against itself. Every arm here is produced by an actual token or an actual body.
- **The completeness control is an AST walk, not a restated list.** A hand-written set of expected stages would drift silently. Reading the two raise sites means the control fails when the code grows an arm, which is the only version of the control worth having.
- **`unconfigured_google_play` replaces the 44-01 fixture rather than joining it.** Two fixtures for one condition would leave a reader asking which is authoritative. The replacement is a superset: it unconfigures the Play read as well as the push token, and the two 44-01 cases now run against the stronger state.
- **The unconfigured Play client is a transport that raises.** "An incomplete deployment reaches for nothing" is otherwise an untested claim; a transport that fails the case makes it a measurement.
- **`real_google_play_seam` for the verified arms, `scripted_google_play` for the failing reads.** Both fixtures swap the same two `app.state` attributes, so a case uses one or the other. The arms the plan words as *verified* use the real verifier; the arms that need a scripted failure use the fake with the push check neutralised.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Every attribution conflict wrote the Google purchase token into an ERROR record**
- **Found during:** Task 2 (the sensitive-value walk)
- **Issue:** `AttributionConflict.log_fields()` returned `{"provider", "external_id"}`. On the Google path `external_id` *is* the purchase token (44 D-10), so `test_no_record_carries_a_token_the_envelope_or_the_purchase_token` failed on a real leak: `attribution_conflict` records carried `a-synthetic-google-purchase-token`. This is T-44-26 in the plan's own threat register, disposition `mitigate`, and the plan's action text names the case explicitly — *"The purchase token is now persisted as `external_id` under the D-10 flagged divergence, and it must still never reach a log line."* The planner asserted the property; the code did not have it.
- **Why this is not Rule 4:** the change is one dict in one error class plus its raise site. It reverses no structure, adds no layer and breaks no client-visible contract — the 500 body is unchanged. The plan's threat register assigns `mitigate` to exactly this surface, which the deviation rules make a correctness requirement.
- **Fix:** `AttributionConflict(provider, purchase_id)` is raised with `recorded.id`, the `core.store_purchases` primary key already in hand at the guard, and logs `purchase_id`. Three dependent assertions were updated: the unit log-field case (now also asserting the lifecycle key is absent), the rejection-vocabulary constructor sample, and the Apple e2e conflict case.
- **Files modified:** src/nativespeaker/api/errors.py, src/nativespeaker/api/services/subscriptions.py, tests/unit/test_subscription_attribution.py, tests/unit/test_rejection_vocabulary.py, tests/e2e/test_app_store_webhook.py
- **Verification:** `uv run pytest -q` 1190 passed, `uv run pytest -m e2e -q` 298 passed, `uv run pytest -m schema -q` 205 passed
- **Committed in:** `c444499`

**2. [Rule 3 - Blocking] 44-01's `unconfigured_google_play_seam` had two call sites**
- **Found during:** Task 1
- **Issue:** The plan asks for a fixture named `unconfigured_google_play` that unconfigures both Google classes. Adding it beside the 44-01 fixture would have left a dead near-duplicate; removing the old one without touching its callers would have left the e2e suite red, against Task 1's own acceptance criterion.
- **Fix:** The 44-01 fixture was replaced and its two cases in `tests/e2e/test_google_play_webhook.py` repointed in the same commit. That file is Task 2's, not Task 1's, but the change is the two-word rename the removal forces.
- **Files modified:** tests/e2e/test_google_play_webhook.py
- **Verification:** `uv run pytest -m e2e -q` — 277 passed at that commit
- **Committed in:** `94c9daa`

### Departures worth naming

**3. The three 500 arms are scripted raises, and the attribution conflict in the walk is real.** The plan says to script all three failures on the Play fake, which `TestEveryFailedReadAnswersTheShared500` does. The sensitive-value walk additionally drives a *genuine* Google attribution conflict — a seeded `core.store_purchase_tokens` row, one delivery that records the owner, and a later delivery under a different `obfuscatedExternalAccountId` — because a scripted raise would have hidden the defect found above: the leak is in the value the real raise site passes, not in the class's answer.

**4. The refusal matrix carries nine parameters for seven stages.** `bad_signature` is reachable three ways (a foreign signing key, a foreign push service account, `email_verified: false`), and all three must produce the same bytes for T-44-25 to hold. The completeness control compares stage sets, so the extra parameters do not weaken it.

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking) and 2 documented departures.
**Impact on plan:** No scope creep. The missing-critical fix is the one the plan's own threat register and its own walk demanded; the rest is the mechanical cost of the fixture the plan asked for.

## Issues Encountered

- The first run of the sensitive-value walk's control reported no `attribution_conflict` record. Root cause: both attributed deliveries in the walk posted the same `eventTimeMillis`, so the second repeated the composite replay key and was refused by the replay guard before it ever reached the attribution guard. The later delivery now carries an instant 1000 ms on, which is what makes it a fresh delivery. The control existed for exactly this: without it the hygiene case would have passed while never driving the arm.
- `requirements.ready-ids` reported 0 of 1 ready for `PLAYHOOK-01`. Plan 44-07 also declares it and has no summary yet, so the id stays open until the last declaring plan finishes. Nothing was hand-edited.

## User Setup Required

None. This plan adds no deployment value. The `e2e` marker is deselected by default, so these cases run under `uv run pytest -m e2e -q`.

## Known Stubs

None. No case asserts a placeholder, and none is skipped or commented out.

## Threat Flags

None. Every surface touched is in this plan's own register: T-44-25 (the refusal oracle), T-44-26 (the log walk, whose defect is fixed above), T-44-27 (credential confusion) and T-44-28 (the redelivery loop). No new network surface, auth path, file access or schema change was introduced.

One entry is worth restating. **T-44-26 was not a formality.** Before this plan, every Google attribution conflict wrote the purchase token into an ERROR record at the exact moment an operator would be reading the logs. Plan 45 consumes the purchase token as the handle a restore route presents, which is what makes a token in a log line an escalation path rather than a tidiness complaint.

## Next Phase Readiness

- Every answer `/webhooks/google-play/rtdn` can give is regression-guarded on the wire, so plan 44-07 and plan 45 can change the seam and find out immediately if any status, body or log line moves.
- Plan 45 inherits `scripted_play_subscriptions`: a restore-route case scripts a `VerifiedNotification` or a raise on `app.state.play_subscriptions` with no token to mint. `scripted_google_play` is the Pub/Sub-specific companion and is not what a restore route wants.
- **`PLAYHOOK-01` is still open.** It is declared by plan 44-07 as well, and `requirements.ready-ids` blocks it until that plan produces its summary.
- No real Pub/Sub push and no real Play response has reached this code. Every case here runs against minted tokens and stubbed transports; whether Google's live tokens and answers match Google's declared shapes remains the standing untested-by-construction fact 44-03 recorded.

---
*Phase: 44-post-webhooks-google-play-rtdn*
*Completed: 2026-09-05*

## Self-Check: PASSED

- Every file named above exists on disk, and this summary with them.
- All three task commits exist in `git log`: `94c9daa`, `c444499`, `6bd45e1`.
- Every `coverage[].ref` names a case that exists in the file it names, verified against `pytest --collect-only` (26 cases in `tests/e2e/test_google_play_webhook.py`).
- Both tasks' acceptance criteria were re-run at close: 5 of 5 for Task 1, 7 of 7 for Task 2, including the D-05 grep (3 occurrences).
- Plan verification re-run at close: `uv run pytest -q` 1190 passed, `uv run pytest -m e2e -q` 298 passed, `uv run pytest -m schema -q` 205 passed, `uv run ruff check src tests` clean.
