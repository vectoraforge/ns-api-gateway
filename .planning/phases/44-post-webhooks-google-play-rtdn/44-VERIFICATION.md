---
phase: 44-post-webhooks-google-play-rtdn
verified: 2026-09-05T13:30:00Z
status: gaps_found
score: 8/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "A Google subscription in an entitled state (active or grace_period) writes an access grant that terminates, never one effective forever (plan 44-05 must-have: 'A Google subscription in grace produces an access grant that is effective at evaluated_at rather than one with an absent or already-past end date', P-01)."
    status: failed
    reason: >
      PlayDeveloperSubscriptions.read() copies the optional line-item expiryTime through with no
      guard (src/nativespeaker/api/auth/google_play.py:206-233). When Play answers an entitled
      state (SUBSCRIPTION_STATE_ACTIVE or SUBSCRIPTION_STATE_IN_GRACE_PERIOD) with no line-item
      expiryTime, `expires_at` and `grace_period_expires_at` are both None. SubscriptionsService
      then writes AccessGrant(ends_at=None), and `_effective_grants_statement`
      (crud/grants.py:24-36) treats a NULL ends_at as effective at every future instant — a
      permanent, unterminable paid entitlement written from provider-supplied data on a paid
      subscription product. This is 44-REVIEW.md CR-01 (critical), found by a review committed
      2026-09-05 05:47 — 14 minutes after the phase-close plan (44-07) committed at 05:33 — and it
      was never fixed or formally accepted afterward. Plan 44-05's own must-have proves only the
      case where Play supplies a real expiryTime; its "control" case
      (tests/schema/test_subscription_ingestion.py, test_an_absent_grace_end_writes_a_grant_carrying_no_end_at_all_control)
      drives exactly the failure scenario through SubscriptionsService.ingest and asserts the
      unbounded outcome (`ends_at is None`) as CORRECT rather than catching it, so the must-have's
      own parenthetical guarantee ("rather than one with an absent ... end date") does not hold
      against real Play responses that omit expiryTime.
    artifacts:
      - path: "src/nativespeaker/api/auth/google_play.py"
        issue: "PlayDeveloperSubscriptions.read() (lines ~206-233) writes expires_at/grace_period_expires_at from the line item's optional expiryTime with no guard against None on an entitled status; the module's own comment names the risk without a fix ('Left as None, every grace-period subscriber's grant would be written with no end date')."
      - path: "tests/schema/test_subscription_ingestion.py"
        issue: "test_an_absent_grace_end_writes_a_grant_carrying_no_end_at_all_control (~line 691) asserts the unbounded outcome as the expected/correct result rather than as a defect to refuse."
    missing:
      - "A guard in PlayDeveloperSubscriptions.read (or the symmetric point in services/subscriptions.py) that refuses (raises InternalError, per 44-REVIEW.md's suggested fix) an entitled status carrying no expiry, so Pub/Sub retries instead of a permanent free grant being written."
      - "Either a fix, or an explicit accepted override in this file's frontmatter recording that the developer knowingly accepts this risk for now."
human_verification: []
---

# Phase 44: POST /webhooks/google-play/rtdn Verification Report

**Phase Goal:** Ingest Google Play RTDN via Cloud Pub/Sub push as the second and last provider-callback route.
**Verified:** 2026-09-05
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

The four ROADMAP.md success criteria for Phase 44, plus the cross-plan must-haves that support
them, were checked directly against the current codebase and a fresh test run (not copied from any
SUMMARY.md).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The route authenticates solely by backend verification of Google's signed OIDC push token (ROADMAP SC1 / PLAYHOOK-01) | ✓ VERIFIED | `src/nativespeaker/api/auth/google_play.py::PubSubPushTokens.verify` runs the bearer through the real `JWTVerifier` pinned to `GOOGLE_ISSUER`/RS256/configured `aud`, with `email`/`email_verified` passed as `required_claims` (compared post-decode, not in `jwt.decode`'s `require` list — confirmed in `app/lifespan.py::build_google_push_verifier`). `app/dependencies.py::verify_google_play_notification` is declared as the route's dependency parameter 0. No Firebase identity is read on this path (`get_identity`/`get_linked_identity` absent from its dependency list — `tests/unit/test_app_wiring.py`). |
| 2 | It calls Phase 43's shared ingestion module rather than a forked copy (ROADMAP SC2 / PLAYHOOK-02) | ✓ VERIFIED | `routers/webhooks.py::google_play_notification` calls `service.ingest(notification)`, the same `SubscriptionsService.ingest` Apple's handler calls, with no provider branch inside it (`services/subscriptions.py` — confirmed no `if provider == google_play` anywhere in `ingest`). `VerifiedNotification` lives in the shared `auth/store_notifications.py`, filled by each provider's own class. Four PostgreSQL guarantees (replay, out-of-order refusal, two-connection race, one-transaction atomicity) are executed for `google_play` in `tests/schema/test_subscription_ingestion.py` and `test_subscription_race.py`, not merely reasoned from Apple's. |
| 3 | The provider-callback category contains exactly these two routes, both by exact path (ROADMAP SC3 / PLAYHOOK-03) | ✓ VERIFIED | `tests/unit/test_app_wiring.py:20-22`: `PROVIDER_CALLBACK_VERIFIERS = {"/webhooks/app-store": ..., "/webhooks/google-play/rtdn": ...}`, `PROVIDER_CALLBACK_PATHS = set(PROVIDER_CALLBACK_VERIFIERS)` — the key set, so no second table can disagree. `webhooks_router` registers exactly these two exact-path POST routes (`routers/webhooks.py`); neither is on `PUBLIC_PATHS = {"/health/ready"}`. Confirmed by running the wiring suite (part of the 1190-passed run below). |
| 4 | A push with an invalid OIDC token is rejected without touching subscription state (ROADMAP SC4 / PLAYHOOK-01) | ✓ VERIFIED | `test_the_verifier_is_the_routes_first_declared_dependency` and `test_the_verifier_resolves_before_any_session_is_taken` (`tests/unit/test_app_wiring.py`) assert, per route, that the verifier is `dependant.dependencies[0].call` and resolves before `get_db` in the flattened walk. `tests/e2e/test_google_play_webhook.py`'s refusal matrix (`TestEveryRefusalAnswersTheOneBody`) drives 9 pushes over 7 refusal stages and asserts a byte-identical 401 body each time, with a source-read AST control asserting the parameter set equals the reachable refusal arms. |
| 5 | The Google replay key is the user-selected composite, not `messageId` or a hash (blocking-checkpoint decision, plan 44-01) | ✓ VERIFIED | `src/nativespeaker/api/auth/google_play.py::notification_key_for` returns exactly `f"google_play:{purchase_token}:{event_time_millis}:{event_type}"` — matches the `composite` option selected at the plan's checkpoint. No `messageId` field is read anywhere in `google_play.py`. |
| 6 | `AttributionConflict.log_fields()` no longer writes the Google purchase token into ERROR records (T-44-26 fix, plan 44-06) | ✓ VERIFIED | `src/nativespeaker/api/errors.py:277-291`: `AttributionConflict.__init__` takes `purchase_id: UUID` and `log_fields()` returns `{"provider", "purchase_id"}` — the `core.store_purchases` row's own primary key, not `external_id`. `services/subscriptions.py` raises it with `recorded.id`. |
| 7 | A Google subscription in an entitled state always produces a grant that terminates, never one effective forever (plan 44-05 must-have, P-01) | ✗ FAILED | See Gaps below (CR-01). The code has no guard against an entitled status with no line-item `expiryTime`; the schema suite's own "control" case for this exact input asserts the unbounded outcome as correct. |
| 8 | Every non-2xx/transport Play-read failure is diagnosable in logs (implicit operational expectation; not a stated must-have) | ⚠️ Not a scored truth — see Anti-Patterns (CR-02, Warning) | `_play_answer_is_usable` and `_get` in `google_play.py` raise `InternalError` (whose `log_level = None`, so the shared error handler emits nothing) for every non-2xx status outside 404/410 and every `httpx.HTTPError`, with no `logger.error` call on that path. Not tied to any plan's `must_haves.truths`, so it does not fail a scored truth, but it is flagged because an operator cannot distinguish a Play misconfiguration (e.g. a 403) from any other 500 in this route. |
| 9 | A deployment with no Play configuration still boots, registers both routes, and answers 503 (plan 44-01 must-have, D-14/D-18) | ✓ VERIFIED | `tests/e2e/test_google_play_webhook.py::TestAnIncompleteDeploymentStillRegistersTheRoute` (both cases), driven through `unconfigured_google_play`, which replaces both Google classes with `None`-holding instances over a transport that fails the case if reached. Confirmed by direct test run (below). Note: this must-have is proven only for the "nothing configured" case; a *partial*-configuration edge case (package_name absent, audience+account present) is a separate, narrower gap recorded under Anti-Patterns (WR-03) rather than counted against this truth, because no plan's must-have states the partial-config behavior. |

**Score:** 8/9 truths verified (1 failed; item 8 is an unscored operational finding, not one of the 9 counted truths — the denominator is the 9 truths enumerated above minus item 8, i.e. 8 of 9 scored truths pass).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/auth/store_notifications.py` | Shared `VerifiedNotification` with `status`/`tier_id`, no `revoked_at`/`in_billing_retry` | ✓ VERIFIED | Confirmed present and imported by both `auth/google_play.py` and `auth/app_store.py`. |
| `src/nativespeaker/api/auth/google_play.py` | Push-token class, Play-read class, Protocol, response models, 9-state map | ✓ VERIFIED | All symbols present; `_STATES` covers the four non-date-derived states plus the `SUBSCRIPTION_STATE_CANCELED` date-decided arm = 9 total published states handled, `expired` as fall-through for anything unlisted. |
| `k8s/templates/httproute-webhooks.yaml` | Second exact-path match for the Google callback | ✓ VERIFIED | Contains exactly one `/webhooks/google-play/rtdn` `Exact` POST match on the same rule as `/webhooks/app-store`, sharing one `backendRefs` block. |
| `.env.example` | `GOOGLE_PLAY_*` block with operational facts | ✓ VERIFIED | Three commented variables present, `androidpublisher.googleapis.com`, `verification_temporarily_unavailable` (x2), `obfuscated` all present as required. |
| `config/config.yaml` | `google_play.products` tracked map | ✓ VERIFIED | `google_play:` block present with `nativespeaker.subscription.monthly -> paid`. |
| `tests/e2e/test_google_play_webhook.py` | End-to-end proof, refusal matrix, fail-closed pair, no-write arms, sensitive-value walk | ✓ VERIFIED | 26 cases present and passing (part of the 298-passed e2e run below). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `routers/webhooks.py` | `app/dependencies.py` | `verify_google_play_notification` declared as handler parameter 0 | ✓ WIRED | Confirmed by source read and by `test_the_verifier_is_the_routes_first_declared_dependency`. |
| `app/dependencies.py` | `auth/google_play.py` | `app.state` holds both Google classes, built in lifespan | ✓ WIRED | `app/lifespan.py::build_google_push_verifier`, `_play_credential`, and both `app.state.google_push_tokens`/`app.state.play_subscriptions` assignments confirmed present. |
| `auth/google_play.py` | `services/subscriptions.py` | `VerifiedNotification` carries the finished status and tier_id | ✓ WIRED | `PlayDeveloperSubscriptions.read` builds `VerifiedNotification(status=..., tier_id=...)`; `services/subscriptions.py` reads `notification.status`/`notification.tier_id` directly, no re-derivation. |
| `k8s/templates/httproute-webhooks.yaml` | `src/nativespeaker/api/routers/webhooks.py` | Gateway path equals the registered application path | ✓ WIRED | Both name the literal `/webhooks/google-play/rtdn`. |

### Behavioral Spot-Checks / Test Run (fresh, this verification)

| Command | Result | Status |
|---------|--------|--------|
| `uv run pytest -q` | 1190 passed, 503 deselected | ✓ PASS |
| `uv run pytest -m e2e -q` | 298 passed, 1395 deselected | ✓ PASS |
| `uv run pytest -m schema -q` | 205 passed, 1488 deselected | ✓ PASS |
| `uv run ruff check src tests` | All checks passed! | ✓ PASS |

These four commands were re-run independently in this verification (not copied from any SUMMARY.md) and match the counts claimed in `.planning/REQUIREMENTS.md`'s Phase 44 amendment and in `44-07-SUMMARY.md`.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PLAYHOOK-01 | 44-01, 44-02, 44-03, 44-04, 44-06, 44-07 | RTDN ingestion authenticated solely by Google OIDC push-token verification | ✓ SATISFIED (with a flagged residual — see Gaps) | Verified truths 1, 4, 5, 6, 9 above. `REQUIREMENTS.md` records this requirement's five knowing divergences from `09-webhook-google-play-rtdn.md` (D-18/D-19/D-20/D-10/OQ-4) in detail — all confirmed present in code. CR-01/CR-02 from `44-REVIEW.md` are **not** mentioned anywhere in `REQUIREMENTS.md`'s Phase 44 amendment, even though the review was committed after the requirement was marked met; this is a genuine gap in the record, not merely in the code. |
| PLAYHOOK-02 | 44-01, 44-05 | Reuses Phase 43's shared ingestion module rather than forking it | ✓ SATISFIED | Verified truth 2 above; four database guarantees executed on real PostgreSQL for `google_play` in `tests/schema/`. |
| PLAYHOOK-03 | 44-01, 44-07 | Provider-callback category closed at exactly two exact-path routes | ✓ SATISFIED | Verified truth 3 above; `REQUIREMENTS.md` records this as ANSWERED AND CLOSED, matching the dict-based partition found in code. |

No orphaned requirements: PLAYHOOK-01…03 is the complete range for Phase 44 and all three are declared across the phase's plans.

### Anti-Patterns Found

| File | Line(s) | Pattern | Severity | Impact |
|------|---------|---------|----------|--------|
| `src/nativespeaker/api/auth/google_play.py` | ~206-233 | Unbounded entitlement: an entitled state with no line-item `expiryTime` writes `ends_at=None`, effective forever | 🛑 Blocker | Permanent free paid-tier grant possible from provider-supplied data; the phase's own review flagged this as critical and it was never fixed or accepted (see Gaps). |
| `src/nativespeaker/api/auth/google_play.py` | 151 (`_play_answer_is_usable`), 246-247 (`_get`) | Every non-2xx/transport Play-read failure raises `InternalError` (log_level=None) with no log call | ⚠️ Warning | A Play misconfiguration (e.g. 403 from a missing `androidpublisher` grant) produces a 500 with zero diagnostic trace; an outage is invisible for as long as it lasts (44-REVIEW.md CR-02). |
| `src/nativespeaker/api/app/lifespan.py` / `dependencies.py` | 128-135 / 179-181 | The "configuration absent" check tests only `push_audience`/`push_service_account_email`, not `package_name`; a `package_name`-only omission answers 401-forever instead of the documented 503 | ⚠️ Warning | Narrow partial-misconfiguration case (44-REVIEW.md WR-03); not covered by any plan's stated must-have, so not counted as a failed truth, but worth fixing before a real partial rollout. |
| `pyproject.toml` / `src/nativespeaker/api/auth/google_play.py:7` | 25 / 7 | `google.auth.transport.requests` imported at module scope; `requests` is not a declared dependency of `google-auth`, only present transitively today | ⚠️ Warning | If the transitive edge is ever lost, the whole application fails to import (not just this route) — the opposite of the fail-closed posture the phase otherwise follows (44-REVIEW.md WR-01). |

No `TBD`/`FIXME`/`XXX` debt markers found in any file this phase modified.

### Human Verification Required

None required to determine the phase's pass/fail status — the blocking finding (CR-01) is a code-level, mechanically confirmed defect, not a judgment call. The following items are recorded for completeness because they were flagged `human_judgment: true` in plan summaries, but they do not change the `gaps_found` status:

1. **44-02 (D5):** Whether `.env.example`'s `GOOGLE_PLAY_` prose actually reads clearly to an unfamiliar deployer, in the App Store block's own voice — a reading judgment, not a command.
2. **44-02 (D6):** The external Play Console / Pub/Sub / Android-client setup steps in `44-USER-SETUP.md` cannot be exercised or observed from this repository.
3. **44-07 (D11):** Whether the `REQUIREMENTS.md` amendment reads as a true, proportionate account to a Phase 45 planner meeting it cold.
4. **helm rendering (WINDOWS.md #19):** `helm template` was not run because `helm` is not installed in this environment (confirmed: `which helm` found nothing here either). The gateway template was instead checked by substituting Helm expressions and parsing the result with PyYAML. This is honestly logged as an `unrun-verify`, not claimed as a pass, and is accepted as such — it is not counted as a gap.

### Gaps Summary

Every ROADMAP.md success criterion for Phase 44 is met, and every requirement (PLAYHOOK-01…03) is
satisfied on the specific claims made in `.planning/REQUIREMENTS.md`. The routing, authentication
ordering, partition-counting, and shared-service-reuse work — which is what the four stated success
criteria actually test — is solid and independently re-verified in this pass (fresh 1190/298/205
test run, ruff clean).

However, the phase's own committed code review (`44-REVIEW.md`, committed *after* the phase-close
plan) found a critical, unfixed defect that this verification confirms still exists in the shipped
code: **`PlayDeveloperSubscriptions.read()` can write a permanently unbounded (`ends_at=None`)
access grant for a paying Google subscriber** when Play's response carries an entitled state with
no line-item `expiryTime`. This is not a hypothetical: the schema suite that plan 44-05 wrote to
prove the opposite property (`must_haves.truths`: "a Google subscription in grace produces an
access grant that is effective ... rather than one with an absent ... end date") contains a case
that drives this exact input and asserts the unbounded outcome as the *correct* result, rather than
refusing it. Nothing in `REQUIREMENTS.md`'s extensive Phase 44 amendment — which records five other
knowing divergences from the brief in detail — mentions this finding at all, which means it was
never formally accepted as a risk; it appears simply to have been missed after the review ran.

A second critical finding, that every non-2xx/transport failure from the Play read produces a 500
with zero log trace (making an outage such as a missing `androidpublisher` grant invisible), is real
and confirmed in code, but does not correspond to any plan's stated `must_haves.truths` or the
ROADMAP's success criteria, so it is recorded as a Warning rather than a blocking gap.

**Recommendation:** either (a) fix CR-01 before this route is exposed to a real Play deployment —
`44-REVIEW.md`'s suggested fix (refuse an entitled state with no expiry, forcing a Pub/Sub retry
rather than a silent permanent grant) is small and self-contained — or (b) add an explicit override
to this file's frontmatter recording that the developer knowingly accepts the risk for now, given
this is a pre-launch product with no real users yet. Given AGENTS.md's own framing (a sub-$5/month
product not worth over-engineering against theft), a considered "accept for now, fix before Play
goes live" decision would be reasonable — but it should be an explicit decision, not a silent gap
carried forward by a test that calls the bug "correct."

---

_Verified: 2026-09-05_
_Verifier: Claude (gsd-verifier)_
