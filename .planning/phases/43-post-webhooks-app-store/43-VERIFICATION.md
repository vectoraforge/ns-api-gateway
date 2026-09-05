---
phase: 43-post-webhooks-app-store
verified: 2026-09-05T05:35:54Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/6
  gaps_closed:
    - "Ingested notifications leave the buyer with the correct entitlement over time — a subscription's status is not corrupted by out-of-order delivery, a grace-period grant is actually effective, and an untokened-then-tokened purchase does not permanently break the route."
    - "With config.app_store incomplete, the application boots, logs one warning, and the route answers 503 — including when the App Store environment variables are present but malformed, which is the exact shape .env.example ships."
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "core.store_purchases is never backfilled: a purchase first recorded unattributed keeps its server-minted identity_value and NULL resolved_token_value forever, even after a later delivery carries a real appAccountToken."
    category: architectural
    reason: >
      Explicitly recorded by the quick task as an accepted residual of the promote-with-no-new-column
      decision, not a new defect. The subscription row does gain the owner and the buyer does get
      their grant — the route recovers, which is what CR-03 was scoped to fix. Only the purchase row's
      own provenance stays stale. Judged acceptable at this phase's scope: backfilling the purchase row
      is restore's job (Phase 45), and neither route performs it today. Flagged so a future reader of
      core.store_purchases does not mistake a stale identity_value for a live one.
    evidence_status: "recorded in 260904-u7t-SUMMARY.md and in the code's own comment at services/subscriptions.py:100-101; not a gap"
---

# Phase 43: POST /webhooks/app-store Verification Report

**Phase Goal:** Ingest Apple App Store Server Notifications as the first of exactly two provider-callback routes.
**Verified:** 2026-09-05
**Status:** passed
**Re-verification:** Yes — after gap closure. This report supersedes the initial verification
(`43-VERIFICATION.md`, 2026-09-04, `status: gaps_found`, `score: 4/6`), which found two failed
derived truths tied to four critical findings in `43-REVIEW.md` (CR-01 … CR-04). Quick task
`260904-u7t` (commits `29082dd`..`f9b2557`, docs `db4f737`) claims to close all four. This report
re-derives all six truths independently — reading the live code, reproducing the two previously
hand-reproduced defects, and running every suite in this session — rather than accepting that claim.

## Goal Achievement

### Observable Truths

All six truths from the prior report were re-checked, not only the two that had failed — CR-01's
superseded arm sits on the same `ingest()` path as the replay guard behind criterion 4, and CR-04
touched `config.py`, which criterion 1's boot path reads.

| # | Truth (ROADMAP success criterion / derived) | Status | Evidence |
|---|------|--------|----------|
| 1 | The route sits outside the auth dependency and authenticates solely by verifying Apple's `signedPayload` JWS | ✓ VERIFIED | Unchanged by this quick task except one additive field (`VerifiedNotification.signed_at`, set in `_crossed` from `payload.signedDate`). `routers/webhooks.py` still reads no `Authorization` header; `tests/unit/test_app_store_notifications.py` (27 passed) and `tests/e2e/test_app_store_webhook.py::test_a_valid_firebase_token_does_not_change_the_refusal` re-run clean. |
| 2 | A payload with an invalid or absent signature is rejected without touching subscription state | ✓ VERIFIED | `verify_app_store_notification` is untouched by this quick task. `tests/e2e/test_app_store_webhook.py::test_a_refused_payload_writes_nothing` re-run clean as part of the 272-passed e2e run below. |
| 3 | The route appears in the provider-callback category by exact path | ✓ VERIFIED | `tests/unit/test_app_wiring.py` untouched by this quick task; re-run in this session, 23 passed. `PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}` still holds as a literal. |
| 4 | Replayed notifications do not double-apply subscription state | ✓ VERIFIED | The replay key (`notification_uuid`, read before any write) is untouched; the new superseded-arm check (truth 5 below) is placed *after* this guard, so it cannot weaken it. `tests/schema/test_subscription_race.py::TestTwoDeliveriesOfOneStoreKeyCommitOnce` re-run in this session — 8 passed. `tests/schema/test_subscription_ingestion.py::test_a_replayed_notification_uuid_leaves_every_count_unchanged` re-run clean as part of the 189-passed schema run below. |
| 5 (derived, plan-level) | Ingested notifications leave the buyer with the correct entitlement over time — no false downgrade from reordering, no permanently-inert grace grant, no permanent lockout from an attribution conflict | ✓ VERIFIED | All three defects closed and independently confirmed in this session — see "CR-01/02/03 Independent Reproduction" below. |
| 6 (derived, plan-level, 43-01 must_have #6) | An incomplete App Store configuration — including a malformed-but-present one, which is what `.env.example` ships — costs the route a 503, never the service its boot | ✓ VERIFIED | Independently reproduced in this session — see "CR-04 Independent Reproduction" below. |

**Score:** 6/6 truths verified.

### CR-01 Independent Reproduction (out-of-order delivery)

Read `services/subscriptions.py:81-96` directly: a superseded arm sits after the `notification_uuid`
replay check and before the attribution guard, keyed on `stored.store_signed_at` vs.
`notification.signed_at` (both present, incoming strictly earlier). It appends the event row (audited),
logs `store_notification_superseded`, commits, and returns — no status write, no grant write.

Ran the new schema tests directly (`tests/schema/test_subscription_ingestion.py::TestAPayloadSignedBeforeTheRecordedStateAppliesNothing`, 4 cases, part of the 189-passed run below). Read every case:
- `test_a_stale_expiry_leaves_the_term_and_the_status_alone` — a fresh `DID_RENEW` then a stale
  `EXPIRED` signed a day earlier: grant stays `active`, `ends_at` stays the fresh term, status stays
  `active`.
- `test_the_same_two_deliveries_in_the_stores_own_order_do_expire_it_control` — **the discriminating
  control**: same two deliveries, signing instants in Apple's actual order, DO expire the grant. This
  proves the guard (not delivery order in the test) is what saves the grant in the case above.
- `test_the_stale_delivery_is_still_audited_and_does_not_raise` — both notification UUIDs land in
  `audit.subscription_events`; the route does not raise.
- `test_a_row_carrying_no_store_clock_applies_the_delivery_normally` — a pre-migration row with
  `store_signed_at` NULL is not frozen by the new guard.

### CR-02 Independent Reproduction (grace-period grant)

Read `services/subscriptions.py:150-154`: `ends_at` is `notification.grace_period_expires_at` when
`status is SubscriptionStatus.grace_period`, else `notification.expires_at`.

Reproduced by hand in this session, independent of any test file:
```
status_at(...) -> grace_period
ends_at = grace_period_expires_at = 2026-09-21 05:34:40+00
effective (ends_at > evaluated_at)? True
```
This is the exact scenario the prior verification reproduced as FAILING (`ends_at` was the already-past
paid-term expiry); it now resolves to an effective grant.

Read the new schema tests
(`TestAGracePeriodDeliveryIsEntitledForTheGraceWindow`, part of the 189-passed run):
- `test_the_grant_runs_to_the_grace_window_and_the_read_returns_it` — asserts effectiveness by calling
  `GrantsDB.lock_effective_grants` on a real session, not by re-spelling the `ends_at > evaluated_at`
  predicate.
- `test_a_grace_window_already_past_leaves_no_effective_grant_control` — **the discriminating control**:
  same shape, grace window also past, yields `expired` and zero effective grants. Proves the case above
  passes on the window, not on the delivery reaching a write at all.

### CR-03 Independent Reproduction (attribution conflict guard)

Read `services/subscriptions.py:98-106`: the guard now compares `recorded.resolved_token_value`
(only ever store-supplied, per the table's CHECK and the code that sets it), firing only when that
value is not None and disagrees with the presented token.

Read the unit tests in `tests/unit/test_subscription_attribution.py::TestTheConflictArm`:
- `test_a_purchase_recorded_unattributed_accepts_a_later_real_token` — a purchase recorded with
  `attribution_token=None` (so `resolved_token_value is None`), then a real token arrives: no raise,
  the subscription gains the owner, a grant is written.
- `test_a_store_supplied_owner_that_disagrees_is_still_refused` — **the discriminating mirror case**:
  a purchase recorded with a real token (`resolved_token_value == TOKEN`), then a different token
  arrives: `AttributionConflict` still raises. This is the case the fix must not lose, and it does not.

Read the e2e deviation the SUMMARY records for `TestAChangedAttributionIsRefusedAndNothingIsWritten`:
before this fix, that class's setup recorded a purchase with **no** store binding, so under the new
guard its "conflict" was actually CR-03's first-honest-attribution case — three of its cases genuinely
failed after Task 4 landed, per the SUMMARY's own account, and this was caught by the plan's own gate
rather than concealed. The fix (`a0f3a0c`) now seeds `core.store_purchase_tokens` for `TOKEN` before
the first delivery, so the first delivery resolves a real owner
(`test_the_recorded_attribution_is_left_as_the_first_delivery_wrote_it` asserts
`resolved_token_value == TOKEN`, not None) and the second delivery under `OTHER_TOKEN` is a genuine
changed-owner conflict. Read the sibling class `TestNoRecordCarriesASensitiveValue`, which seeds a
binding throughout and never needed this fix — its conflict case passed unchanged before and after,
which is independent evidence the guard fired end to end the whole time and only the *other* class's
setup was wrong. **Verdict: this deviation is a legitimate bug fix in a test fixture, not a weakened
assertion — the conflict guard genuinely still fires end to end**, confirmed by reading both the
before/after setup and the sibling class's unaffected pass.

### CR-04 Independent Reproduction (malformed App Store config)

Reproduced by hand in this session, the same construction the prior verification used to prove the
defect:
```python
AppStoreConfig(app_apple_id='...', environment='...')
-> app_apple_id=None, environment=None   # no ValidationError
build_app_store_verifier(store) -> None
```
Read `config.py:85-98`: two `field_validator`s in `mode="before"` degrade an unparsable
`app_apple_id`/`environment` to `None` rather than raising. Read `.env.example:105-107`: the three
App Store lines now ship **commented out** with values that parse if uncommented
(`#APP_STORE_APP_APPLE_ID=6001234567`, `#APP_STORE_ENVIRONMENT=sandbox`), removing the
`ValidationError`-triggering shape the prior verification found shipped uncommented.

Scrutinized the recorded test-setup deviation for the security property: the pre-existing case
`test_a_verification_skipping_environment_is_refused_at_load` asserted `ValidationError` for the
library's two verification-skipping environments (`Xcode`, `LocalTesting`). It was rewritten to
`test_a_verification_skipping_environment_never_reaches_a_verifier`, which asserts **both**
`store.environment is None` **and** `build_app_store_verifier(store) is None` for each of the two
values (`tests/unit/test_config.py:232-238`), with a control
(`test_a_named_environment_still_loads`) proving a loader that refused everything would not
distinguish the two cases. Independently re-derived the underlying guarantee by reading
`_named_or_absent`: it keeps membership by value against `tuple(StoreEnvironment)`, which is
`{sandbox, production}` only — `Xcode` and `LocalTesting` are not members of that enum at all, so no
value reachable from `.env` can ever equal one of the two library environments that skip verification.
**Verdict: the security property moved from "refused at load" to "degraded to absent, which builds no
verifier" — it was not weakened.** A verification-skipping environment still cannot end up usable.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `core.subscriptions.store_signed_at` (migration + `Subscription` model) | The store's own clock, separate from `updated_at` | ✓ VERIFIED | Column confirmed present by direct introspection of the dev database (`information_schema.columns`, 12th column, `timestamp with time zone`). Migration edited in place under its existing id — only one file exists in `migrations/`, no incremental migration was added. |
| `VerifiedNotification.signed_at` | Carried from `payload.signedDate` | ✓ VERIFIED | `auth/app_store.py:26`, `:60`; all four construction sites updated (`_crossed` plus three test builders). |
| `services/subscriptions.py` superseded arm | Refuses a payload signed before the recorded state (CR-01) | ✓ VERIFIED, substantively | Present, wired before the attribution guard, exercised by 4 new schema cases with a discriminating control. |
| `services/subscriptions.py` grace-window `ends_at` | Grace grant carries the grace window, not the lapsed term (CR-02) | ✓ VERIFIED, substantively | Present, exercised by 2 new schema cases with a discriminating control, reproduced by hand. |
| Attribution conflict guard keyed on `resolved_token_value` (CR-03) | Only-ever-store-supplied value (CR-03) | ✓ VERIFIED, substantively | Present, exercised by 2 new unit cases (accept + still-refuses mirror) and corrected end-to-end e2e coverage. |
| `AppStoreConfig` validators (CR-04) | Degrade unparsable `app_apple_id`/`environment` to `None` | ✓ VERIFIED, substantively | Present, `mode="before"`, exercised by 5 new unit cases including a file-reads-constructible regression test over the committed `.env.example`. |
| Two named schema tests the prior report required as missing | Grace-period-through-`write_subscription_grant`, and same-subscription out-of-order-delivery | ✓ VERIFIED | Both exist: `TestAGracePeriodDeliveryIsEntitledForTheGraceWindow` and `TestAPayloadSignedBeforeTheRecordedStateAppliesNothing`, both in `tests/schema/test_subscription_ingestion.py`, both with discriminating controls, both re-run in this session. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `auth/app_store.py::_crossed` | `services/subscriptions.py::ingest` | `VerifiedNotification.signed_at` | ✓ WIRED | Read at `services/subscriptions.py:82` and `:115`. |
| `services/subscriptions.py::ingest` | `crud/subscriptions.py::upsert_subscription` | `signed_at` keyword, advances `store_signed_at` only when not None | ✓ WIRED | Confirmed by direct read of `crud/subscriptions.py:90-119`. |
| `services/subscriptions.py::ingest` | `crud/subscriptions.py::write_subscription_grant` | grace-branch `ends_at` | ✓ WIRED | Confirmed at `services/subscriptions.py:150-154`. |
| `config.py::AppStoreConfig` | `app/lifespan.py::build_app_store_verifier` | degraded `None` still yields no verifier, one warning, route 503 | ✓ WIRED | Confirmed by hand reproduction above; `lifespan.py`'s absence branch is untouched by this quick task. |

### Behavioral Spot-Checks / Independent Reproductions

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit suite | `uv run pytest -q` | 1098 passed, 461 deselected | ✓ PASS (matches SUMMARY's claimed 1098, up from baseline 1089) |
| Full schema suite | `uv run pytest -m schema -q` | 189 passed, 1370 deselected | ✓ PASS (matches SUMMARY's claimed 189, up from baseline 182) |
| Full e2e suite | `uv run pytest -m e2e -q` | 272 passed, 1287 deselected | ✓ PASS (matches SUMMARY's claimed 272, unchanged from baseline) |
| Lint | `uv run ruff check src tests` | All checks passed | ✓ PASS |
| CR-02 grace grant effectiveness | inline reproduction of `status_at` + the `ends_at` branch | `grace_period`, `ends_at` in the future, effective | ✓ PASS (was ✗ FAIL in prior verification) |
| CR-04 malformed config | `AppStoreConfig(app_apple_id='...', environment='...')` | Both fields `None`, no raise; `build_app_store_verifier` returns `None` | ✓ PASS (was ✗ FAIL — raised `ValidationError` — in prior verification) |
| `store_signed_at` column present | `information_schema.columns` query against the dev database | 12 columns, `store_signed_at timestamp with time zone` present | ✓ PASS |
| Migration edited in place | `ls migrations/` | One file: `20260818_01_initial-release.sql` | ✓ PASS |
| Race/replay guarantee (criterion 4) unaffected | `uv run pytest tests/schema/test_subscription_race.py -m schema -k TestTwoDeliveriesOfOneStoreKeyCommitOnce` | 8 passed | ✓ PASS |
| Wiring/callback partition (criterion 3) unaffected | `uv run pytest tests/unit/test_app_wiring.py -q` | 23 passed | ✓ PASS |
| Auth seam (criteria 1-2) unaffected | `uv run pytest tests/unit/test_app_store_notifications.py tests/e2e/test_app_store_webhook.py -m e2e -q` (run separately) | 27 passed / 28 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| APPLEHOOK-01 | 43-01 … 43-06, 260904-u7t | Ingest Apple notifications outside the auth dependency, JWS-only auth, correct entitlement over time | ✓ SATISFIED | Both the auth half (truths 1-2) and the ingestion-correctness half (truth 5, CR-01/02/03) now hold on independently gathered evidence. |
| APPLEHOOK-02 | 43-01, 43-06 | Route in the provider-callback category by exact path | ✓ SATISFIED | Truth 3, unaffected by this quick task, re-confirmed. |

No orphaned Phase 43 requirement IDs found in REQUIREMENTS.md's traceability table. Note:
REQUIREMENTS.md and ROADMAP.md still record the pre-quick-task counts (1089/272/182); this report
does not update either file — per this verification's scope, that is the orchestrator's job.

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers in any of the 12 files this quick task
modified. `ruff check src tests` is clean.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/nativespeaker/api/crud/subscriptions.py` | 126 (and 4 other sites) | `violation.orig.sqlstate` still accessed with no `getattr` guard | ⚠️ Warning | Pre-existing WR-03 from `43-REVIEW.md`, untouched by this quick task, explicitly out of scope per this task's instructions (not treated as a blocker: degrades a lost race into an opaque 500, does not corrupt data) |

### Advisory (New Scope, Unevidenced)

| # | Finding | Category | Why Advisory |
|---|---------|----------|--------------|
| 1 | `core.store_purchases` is never backfilled — a purchase first recorded unattributed keeps its server-minted `identity_value` and NULL `resolved_token_value` forever, even after a later delivery carries a real token | architectural | Explicitly recorded as an accepted residual in `260904-u7t-SUMMARY.md` and grounded in the code's own comment (`services/subscriptions.py:100-101`); the subscription row and the buyer's grant do recover, which is what CR-03 was scoped to fix. Backfilling the purchase row is Phase 45 (restore)'s job. Judged acceptable at this phase's scope — not a gap. |

### Human Verification Required

None. Every finding above was verified either by direct code reading, by re-running an existing or
new automated test in this session, or by independent hand reproduction of the exact scenario the
prior verification used to prove the four defects (CR-02's inert grace grant, CR-04's boot-crashing
placeholder), plus a fresh read of both recorded test-setup deviations to confirm neither weakened
the property it touches.

### Gaps Summary

No gaps remain. The two derived truths that failed in the initial verification — ingestion-correctness
over time (CR-01/02/03) and the fail-closed configuration guarantee under a malformed value (CR-04) —
now hold on evidence gathered independently in this session: direct code reading of the fix sites, the
same hand reproductions the prior verifier used (now resolving the opposite way), reading every new
test for a discriminating control rather than counting them, and reading both recorded test-setup
deviations closely enough to distinguish "papered over" from "a real bug in the old fixture, now fixed
correctly" — which is what both turned out to be. The four ROADMAP-literal criteria (1-4) were
re-confirmed unaffected by this quick task's changes. All three measured suite counts (1098 unit / 189
schema / 272 e2e) and the ruff-clean result were reproduced by running the commands directly in this
session, not taken from the SUMMARY.

One accepted residual (the purchase row's own provenance staying stale after a later honest
attribution) is recorded as advisory, not a gap, per the explicit scope decision in the quick task's
plan. The WARNING findings WR-01…WR-06 remain out of scope, as instructed, and none has become a
blocker as a result of this change — WR-03's unguarded `sqlstate` access is untouched and unchanged in
severity.

---

_Verified: 2026-09-05T05:35:54Z_
_Verifier: Claude (gsd-verifier)_
