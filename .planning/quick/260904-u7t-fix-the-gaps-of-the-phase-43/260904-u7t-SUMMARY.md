---
phase: 260904-u7t
plan: 01
subsystem: payments
tags: [app-store, subscriptions, entitlements, postgres, pydantic, sqlmodel]

requires:
  - phase: 43-post-webhooks-app-store
    provides: the verified route, the ingestion service, the subscription and purchase tables
provides:
  - core.subscriptions.store_signed_at, the store's own clock on the applied notification
  - VerifiedNotification.signed_at, carried from the envelope's signedDate
  - the superseded arm — a payload signed before the recorded state applies nothing (CR-01)
  - a grace-period grant whose term is Apple's grace window (CR-02)
  - the attribution conflict guard keyed on resolved_token_value (CR-03)
  - two AppStoreConfig validators degrading a malformed value to absent (CR-04)
affects: [restore, google-play ingestion, any later reader of core.subscriptions]

actuals:
  tokens: 9170          # chars/4 over the realized diff (36679 chars); the 12 changed files total 167079 chars
  tasks: 5
  commits: 9

tech-stack:
  added: []
  patterns:
    - "The store's clock and this server's clock are separate columns, never compared to each other"
    - "A malformed deployer value degrades to absent, because absent is already the fail-closed path"

key-files:
  created: []
  modified:
    - migrations/20260818_01_initial-release.sql
    - src/nativespeaker/api/auth/app_store.py
    - src/nativespeaker/api/tables/purchases.py
    - src/nativespeaker/api/crud/subscriptions.py
    - src/nativespeaker/api/services/subscriptions.py
    - src/nativespeaker/api/config.py
    - .env.example
    - tests/schema/test_subscription_ingestion.py
    - tests/unit/test_subscription_attribution.py
    - tests/unit/test_app_store_notifications.py
    - tests/unit/test_config.py
    - tests/e2e/test_app_store_webhook.py

key-decisions:
  - "The monotonicity guard compares two store instants, never the store's against this server's receipt instant — which is why a new column was added rather than reusing updated_at"
  - "A NULL store_signed_at is unknown, never newest: rows written before the column applies normally"
  - "The attribution guard keys on resolved_token_value, promoted with no new column (the plan's assumption_delta_decision)"
  - "A verification-skipping store environment now degrades to absent instead of raising at load; it still reaches no verifier, so the security property moved rather than weakened"

patterns-established:
  - "Pattern: an out-of-order store delivery is audited and not applied — the event row is appended, the status and grant are untouched, and the store still reads 200"
  - "Pattern: an entitlement case asserts effectiveness by calling GrantsDB.lock_effective_grants, never by re-spelling its predicate"

requirements-completed: [APPLEHOOK-01]

duration: ~35min
completed: 2026-09-04
status: complete
---

# Quick Task 260904-u7t: Fix the gaps of Phase 43 — Summary

**The four critical findings of the Phase 43 verification report are closed: an out-of-order Apple delivery no longer downgrades a paying buyer, a grace-period grant now carries the grace window and is actually effective, a purchase first seen without an `appAccountToken` accepts the first real one instead of permanently 500ing, and a malformed App Store value now costs `POST /webhooks/app-store` its 503 rather than the whole service its boot.**

## Performance

- **Duration:** ~35 min (first task commit 22:08, last 22:20, plus the verification gate)
- **Tasks:** 5 of 5
- **Commits:** 9 (three TDD RED/GREEN pairs, one tracer, one deviation fix, one config task)

## Measured suite counts

Run from the repository root after the last commit. Reported as measured.

| Suite | Baseline (Phase 43 close) | Measured now |
|-------|---------------------------|--------------|
| `uv run pytest -q` (unit) | 1089 | **1098** |
| `uv run pytest -m e2e -q` | 272 | **272** |
| `uv run pytest -m schema -q` | 182 | **189** |
| `uv run ruff check src tests` | clean | **clean** |

No count dropped. The nine new unit cases are two seam cases, two attribution cases and five config cases; the seven new schema cases are one persisted-column case, four out-of-order cases and two grace-period cases.

## The applied-migration step and its outcome

The `[BLOCKING]` step of Task 1 ran before any e2e verify:

```
uv run pogo rollback && uv run pogo apply
```

Both succeeded silently against the configured `DB_*` database (`nativespeaker` on localhost:5432, PostgreSQL 17.11). Confirmed by introspection rather than by the command's exit code alone: `core.subscriptions` went from 11 columns to 12, the twelfth being `store_signed_at timestamp with time zone`. The e2e suite was run only after that check. The migration was edited **in place under its existing id**, per the v2.0 rule in STATE.md and the 37-01 precedent.

## What each task delivered

1. **The signing instant, end to end (tracer).** `VerifiedNotification.signed_at` is set in `auth/app_store.py::_crossed` from the envelope payload's `signedDate` through the existing `_instant` helper — the envelope only; neither nested payload carries one. `core.subscriptions.store_signed_at` is nullable, unindexed, and mirrored on the `Subscription` model. `upsert_subscription` takes `signed_at`; the insert arm sets it, the update arm advances it only when the incoming value is not None, and the `replayed` arm still writes nothing. All four `VerifiedNotification` construction sites were updated.
2. **CR-01, the superseded arm.** In `SubscriptionsService.ingest`, after the `notification_uuid` replay check and **before** the attribution guard: when the stored row and the incoming payload both carry a signing instant and the incoming one is strictly earlier, the delivery appends its event row (recording `stored.tier_id` on both sides, because no transition was applied), logs `store_notification_superseded` with the event type only, commits and returns. Equality applies normally.
3. **CR-02, the grace window.** At the `write_subscription_grant` call site, `ends_at` is Apple's grace window whenever the resolved status is `grace_period`, and the transaction's expiry otherwise. `status_at` is that branch's one producer.
4. **CR-03, the conflict key.** The guard now compares `recorded.resolved_token_value`, and fires only when that value is not None.
5. **CR-04, the malformed value.** Two `field_validator`s in before mode on `AppStoreConfig`: `app_apple_id` keeps an int or an all-digit string, `environment` keeps a value that is one of the two `StoreEnvironment` members, and each degrades anything else to None. `.env.example` ships the three App Store lines commented out with values that parse.

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 — Bug] The e2e attribution-conflict class was set up on a purchase with no store-supplied owner**

- **Found during:** Task 5's `uv run pytest -m e2e -q` (the first full e2e run after Task 4 landed).
- **Issue:** `tests/e2e/test_app_store_webhook.py::TestAChangedAttributionIsRefusedAndNothingIsWritten` never seeded a `core.store_purchase_tokens` binding for `TOKEN`. Its first delivery therefore recorded a purchase with `resolved_token_value` NULL — the class even asserted that at line 388 — and the second delivery was read as a changed owner only because the old guard compared `identity_value`. Under the new guard that scenario **is** CR-03's first honest attribution, so three of its cases failed. Diagnosed to the setup, not to the assertion: the sibling class `TestNoRecordCarriesASensitiveValue` does seed a binding and its `attribution_conflict` expectation kept passing throughout, which is the evidence that the guard itself still fires end to end.
- **Fix:** `_record_then_conflict` now seeds the binding for `TOKEN` first, so the first delivery resolves an owner and records `resolved_token_value = TOKEN`; the second delivery is then a genuine changed owner and is refused with the shared 500. The case that documented the old accidental setup now asserts the owner it resolves. One case gained the `_db_transaction` fixture it needed, which also stops its writes leaking out of the test.
- **Files modified:** `tests/e2e/test_app_store_webhook.py`
- **Commit:** `a0f3a0c`

**2. [Rule 3 — Blocking] An existing config case asserted the load-time refusal that Task 5 removes by design**

- **Found during:** Task 5.
- **Issue:** `test_a_verification_skipping_environment_is_refused_at_load` asserted `ValidationError` for `APP_STORE_ENVIRONMENT` values `Xcode` and `LocalTesting`. Task 5's environment validator degrades exactly those to None instead of raising. The plan did not name this case.
- **Fix:** the case was rewritten rather than deleted or weakened. It is now `test_a_verification_skipping_environment_never_reaches_a_verifier` and asserts the same security property at its new location: the value degrades to None **and** `build_app_store_verifier` answers None for it, so neither library environment can reach a verifier. The property moved from "refused at load" to "degraded to absent, and absent holds no verifier"; it did not weaken. This is the deliberate trade the plan makes for T-U7T-03 — an operator's typo must not crash-loop the pod.
- **Files modified:** `tests/unit/test_config.py`
- **Commit:** `f9b2557`

**3. [Deliberate, recorded] The `_envelope` test builder gained a second knob rather than a sentinel**

- **Found during:** Task 1, writing the "no `signedDate` yields None" seam case.
- **Issue:** `_envelope`'s existing `signed_date=None` already means "mint one at now", so `None` could not also mean "omit it".
- **Fix:** a `with_signed_date: bool = True` parameter, so the case that needs an envelope with no signing date asks for one by name. No sentinel object and no changed meaning for the existing `signed_date` argument. Verified against the library: `_decode_signed_object` falls back to `time.time()` when `signedDate` is absent, so the chain walk still runs.
- **Commit:** `29082dd`

### Where the live code diverged from what the plan read at planning time

Two small differences, neither of which changed a decision:

- The plan says Task 3 should "replace the existing `ends_at` comment". There was no comment on `ends_at`; the comment above it belonged to `starts_at`. A new one-line comment was added above `ends_at` and the `starts_at` comment was left untouched.
- The plan says the unit attribution recorder may "conflate" `identity_value` and `resolved_token_value` and should be extended if so. It does not conflate them — `_RecordingSubscriptions.insert_purchase` already stores both separately — so no stub extension was needed. The recorder did need the two new `signed_at` arms, added in Task 1 to mirror the crud's rules.

## Accepted residual, recorded not fixed

**The purchase row is never backfilled.** `core.store_purchases` is written once per lifecycle key and never updated (`tables/purchases.py`). A purchase first recorded unattributed therefore keeps its server-minted `identity_value` and its NULL `resolved_token_value` forever, even after a later delivery carries a real `appAccountToken`. What recovers is the **subscription** row: it gains the owner, and the buyer gets their grant, which is what CR-03 was about. Backfilling the purchase row belongs to restore, and neither route does it today.

Recorded as a consequence of the `promote`-with-no-new-column decision in the plan's `<assumption_delta_decision>`, not as a new defect. **What would force a later promote to a real column:** any future writer that sets `resolved_token_value` for a purchase whose owner was not resolved from the store's own token. That would break the column's one guarantee, and the guard would lose its ground.

## Known Stubs

None. No placeholder value, no skipped test and no unrun `<verify>` was left behind; every `<verify>` in the plan was executed and is reported above.

## Threat Flags

None. No new network endpoint, auth path, file-access pattern or trust-boundary schema change was introduced beyond the register the plan already carries. `store_signed_at` is a nullable column on an existing table, written only from a payload Apple has already signed.

## Self-Check: PASSED

- All 12 modified files exist on disk.
- All 9 commits exist in `git log`: `29082dd`, `81949d1`, `46296d8`, `557c9e7`, `a64ceb7`, `c54359d`, `63415f3`, `a0f3a0c`, `f9b2557`.
- `core.subscriptions.store_signed_at` exists in the dev database, read back by introspection.
- The four measured gate results are recorded above exactly as the commands printed them.
