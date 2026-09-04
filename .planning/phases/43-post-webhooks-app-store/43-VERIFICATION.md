---
phase: 43-post-webhooks-app-store
verified: 2026-09-04T00:00:00Z
status: gaps_found
score: 4/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Ingested notifications leave the buyer with the correct entitlement over time — a subscription's status is not corrupted by out-of-order delivery, a grace-period grant is actually effective, and an untokened-then-tokened purchase does not permanently break the route."
    status: failed
    reason: >
      Three critical, independently reproduced defects in the state machine that turns a verified
      notification into a subscription row and a grant (43-REVIEW.md CR-01, CR-02, CR-03), all
      unfixed as of this verification:
      (1) CR-01 — `status_at` reads only the incoming notification's own dates and
      `upsert_subscription`/`write_subscription_grant` overwrite the stored row unconditionally.
      The only replay guard is `notification_uuid`, which differs between distinct notifications,
      and Apple does not guarantee delivery order. A `DID_RENEW` for term N+1 followed by a
      delayed `EXPIRED` for term N ends with the buyer's grant flipped to `expired`, even though
      the buyer paid through term N+1. `tests/schema/test_subscription_ingestion.py`'s
      `TestTheNewestPurchaseWins` tests two *different* subscriptions for one buyer, and a
      same-subscription reorder case, confirmed absent by direct inspection.
      (2) CR-02 — reproduced independently in this verification (see artifacts): `status_at`
      correctly returns `grace_period` when the paid term has ended but Apple's grace window has
      not, but `write_subscription_grant` is called with `ends_at=notification.expires_at`, which
      is the already-past paid-term expiry, not the grace window. `_effective_grants_statement`
      requires `ends_at > evaluated_at`, so the resulting grant is written as `grace_period` but is
      never effective — the buyer holds zero allowance despite Apple still covering the gap,
      defeating the exact purpose the grace-before-billing-retry arm order in
      `services/subscriptions.py::status_at` states it exists for. No fixture in any test file
      (`tests/e2e/test_app_store_webhook.py`, `tests/unit/test_subscription_attribution.py`,
      `tests/schema/test_subscription_ingestion.py`) ever sets `grace_period_expires_at` to a
      non-`None` value, so this path is untested.
      (3) CR-03 — a purchase first observed with no `appAccountToken` stores a server-minted
      `str(uuid7())` as `identity_value` (`services/subscriptions.py:101-103`). A later, legitimate
      delivery for the same purchase that *does* carry a real `appAccountToken` then fails the
      conflict guard at `services/subscriptions.py:83` (`recorded.identity_value != token`),
      raising `AttributionConflict` — a 500 with no recovery path through this route. Apple retries
      for three days and gives up. Confirmed by direct code reading; the guard compares a
      server-minted value as if it were store-supplied, and nothing distinguishes the two in the
      `identity_value` column.
    artifacts:
      - path: src/nativespeaker/api/services/subscriptions.py
        issue: "status_at/write_subscription_grant (CR-01, CR-02); the attribution conflict guard at :83 (CR-03)"
      - path: src/nativespeaker/api/crud/subscriptions.py
        issue: "upsert_subscription overwrites the stored row unconditionally with no ordering/monotonicity check (CR-01)"
    missing:
      - "A monotonicity guard comparing the incoming notification's signing instant (or its transaction's expiresDate) against the stored row's last-updated instant, refusing to regress an already-applied later state (CR-01)."
      - "write_subscription_grant using notification.grace_period_expires_at as ends_at when status is grace_period, not notification.expires_at (CR-02)."
      - "A conflict guard keyed on a value that is only ever store-supplied (e.g. resolved_token_value) rather than the server-minted identity_value placeholder (CR-03)."
      - "A schema test exercising grace_period through write_subscription_grant, and a same-subscription out-of-order-delivery schema test."
  - truth: "With config.app_store incomplete, the application boots, logs one warning, and the route answers 503 — including when the App Store environment variables are present but malformed, which is the exact shape .env.example ships."
    status: failed
    reason: >
      The documented and tested fail-closed guarantee ("With config.app_store incomplete ...
      the application boots ... and the route answers 503", 43-01 must_have #6; ROADMAP SC1's
      supporting design) only holds when the three App Store environment variables are *absent*.
      `.env.example:105-107` ships `APP_STORE_APP_APPLE_ID=...` and `APP_STORE_ENVIRONMENT=...`.
      `app_apple_id` is `int | None` and `environment` is `StoreEnvironment | None` with no
      placeholder-tolerant validator, so pydantic-settings raises `ValidationError` at config load —
      before lifespan.py's own completeness check ever runs. Reproduced independently in this
      verification: `AppStoreConfig(app_apple_id='...', environment='...')` raises two
      `ValidationError`s. `pyproject.toml` sets `env_files = [".env"]`, and the file's own comment
      block instructs the reader to fill or leave these three values, which is the same workflow
      used for every other `.env.example` block (`OPENAI_API_KEY=...` etc. load fine as strings).
      A deployer following that instruction verbatim crashes the whole service's boot, not just the
      one route — the opposite of the recorded guarantee, and this specific malformed-but-present
      shape is exactly what the committed file ships (43-REVIEW.md CR-04).
    artifacts:
      - path: .env.example
        issue: "Lines 105-107 ship APP_STORE_APP_APPLE_ID=... and APP_STORE_ENVIRONMENT=..., both of which raise ValidationError rather than resolving to None"
      - path: src/nativespeaker/api/config.py
        issue: "AppStoreConfig has no validator degrading a malformed placeholder value to None the way absence already is"
    missing:
      - "A field_validator on app_apple_id/environment (or equivalent) that treats an unparsable placeholder as absent, so a malformed value costs the one route its 503 rather than the whole service its boot."
      - "Alternatively, comment out the three App Store lines in .env.example so copying the file does not supply any value for them."
advisory: []
---

# Phase 43: POST /webhooks/app-store Verification Report

**Phase Goal:** Ingest Apple App Store Server Notifications as the first of exactly two provider-callback routes.
**Verified:** 2026-09-04
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

The four ROADMAP.md success criteria are evaluated on their literal text first, then the phase's
own plan-level must-haves and the phase's own committed code review (`43-REVIEW.md`) are checked
for defects that undermine the substance behind those criteria, per this verifier's instruction to
weigh, not inherit, the review's findings.

| # | Truth (ROADMAP success criterion) | Status | Evidence |
|---|------|--------|----------|
| 1 | The route sits outside the auth dependency and authenticates solely by verifying Apple's `signedPayload` JWS | ✓ VERIFIED | `routers/webhooks.py` reads no `Authorization` header; `AppStoreNotifications.verify` (auth/app_store.py) is the sole gate, calling Apple's `SignedDataVerifier` three times (envelope, nested transaction, nested renewal info) against the vendored Apple Root CA G3. `tests/e2e/test_app_store_webhook.py::test_a_valid_firebase_token_does_not_change_the_refusal` proves a valid Firebase ID token changes nothing. |
| 2 | A payload with an invalid or absent signature is rejected without touching subscription state | ✓ VERIFIED | `verify_app_store_notification` (app/dependencies.py:145-149) takes only `Request` and the body — no `Depends(get_db)` in its own chain — and is declared as the webhooks router's own `dependencies=[...]`, which FastAPI resolves ahead of the handler's own parameter dependencies (`get_subscriptions_service`, which does depend on `get_db`). A rejection raises before any session opens. `tests/e2e/test_app_store_webhook.py::test_a_refused_payload_writes_nothing` asserts zero subscription and event rows after every reachable 401 arm. (WR-02 in 43-REVIEW.md notes this correctness rests on an internal FastAPI de-duplication behavior; the failure mode if that changed is a total, closed 422 outage of the route, not silent state corruption — it does not defeat this truth.) |
| 3 | The route appears in the provider-callback category by exact path | ✓ VERIFIED | `tests/unit/test_app_wiring.py` holds `PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}` as a literal, compared with `==` against `webhooks_router.routes`; `PUBLIC_PATHS == {"/health/ready"}` is asserted as a separate literal case so the callback route joining the "no identity accessor" structural exemption does not silently widen the true public allowlist. Confirmed by reading the test file directly (lines 16, 18, 65, 72, 89, 109). |
| 4 | Replayed notifications do not double-apply subscription state | ✓ VERIFIED | The replay key is `audit.subscription_events.notification_uuid`, read inside the transaction (`services/subscriptions.py:77`) before any write. `tests/schema/test_subscription_race.py::TestTwoDeliveriesOfOneStoreKeyCommitOnce` races two real PostgreSQL connections and was re-run in this verification (`uv run python -m pytest tests/schema/test_subscription_race.py -m schema -k TestTwoDeliveriesOfOneStoreKeyCommitOnce` → 8 passed): exactly one row lands in each of the three tables, the loser reads SQLSTATE 23505, rolls back, and answers 5xx; a third delivery finds the event row and answers 200. `tests/schema/test_subscription_ingestion.py::test_a_replayed_notification_uuid_leaves_every_count_unchanged` confirms the same for an identical `notificationUUID`. |
| 5 (derived, plan-level) | Ingested notifications leave the buyer with the correct entitlement over time — no false downgrade from reordering, no permanently-inert grace grant, no permanent lockout from an attribution conflict | ✗ FAILED | See Gaps below (CR-01, CR-02, CR-03). CR-02 was independently reproduced in this verification, not just read from the review. |
| 6 (derived, plan-level, 43-01 must_have #6) | An incomplete App Store configuration — including a malformed-but-present one, which is what `.env.example` ships — costs the route a 503, never the service its boot | ✗ FAILED | See Gaps below (CR-04). Independently reproduced in this verification: `AppStoreConfig(app_apple_id='...', environment='...')` raises `ValidationError`, and `.env.example` ships exactly those two placeholder values. |

**Score:** 4/6 truths verified (the 4 literal ROADMAP criteria hold; 2 derived truths tied to the phase's own plan intent and its own committed code review do not).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/auth/app_store.py` | JWS verification seam, `VerifiedNotification`, `StoreNotificationVerifier` | ✓ VERIFIED | Present; no logger, no `run_in_threadpool`, reads `rawNotificationType` for the event type. |
| `src/nativespeaker/api/schemas/webhooks.py` | Request body schema | ✓ VERIFIED | `AppStoreNotificationRequest.signedPayload` present (WR-01: no `max_length` bound — a warning, not a blocker). |
| `src/nativespeaker/api/routers/webhooks.py` | The one registered route | ✓ VERIFIED | `POST /webhooks/app-store`, exact path, thin handler. |
| `src/nativespeaker/api/crud/subscriptions.py` | `SubscriptionsDB` | ✓ VERIFIED, but substantively defective | Exists, wired, flushed in the right order — but see gap 5/CR-01. |
| `src/nativespeaker/api/services/subscriptions.py` | `SubscriptionsService`, `status_at` | ✓ VERIFIED, but substantively defective | Exists, wired, imports nothing from the Apple library (proved by the `ast` walk in `tests/unit/test_app_store_notifications.py`) — but see gap 5/CR-01, CR-02, CR-03. |
| `tests/unit/test_app_store_notifications.py` | Real-chain seam proof | ✓ VERIFIED | Contains both Apple OID literals, references the vendored root, control case present. |
| `tests/e2e/test_app_store_webhook.py` | End-to-end round trip | ✓ VERIFIED | Happy path, all refusal arms, replay, no-transaction case all present and passing. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `app/lifespan.py` | `app.state.app_store_notifications` | one `SignedDataVerifier` built at boot | ✓ WIRED | Confirmed by reading `verify_app_store_notification` reading `request.app.state.app_store_notifications`. |
| `routers/webhooks.py` | `verify_app_store_notification` | router-level `Depends()` | ✓ WIRED | Confirmed; see truth 2 evidence above and WR-02 caveat (non-blocking). |
| `services/subscriptions.py` | `crud/subscriptions.py` | `SubscriptionsDB` composition | ✓ WIRED | `SubscriptionsService.__init__` constructs `SubscriptionsDB(db)`. |
| `crud/subscriptions.py` | `core.subscriptions` / `audit.subscription_events` | SQLAlchemy `session.flush()` | ✓ WIRED, data flows | Subscription flushed before the event append (FK-ordering respected), confirmed by reading `crud/subscriptions.py:84-181`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Replay/race guarantee (criterion 4) | `uv run python -m pytest tests/schema/test_subscription_race.py -m schema -k TestTwoDeliveriesOfOneStoreKeyCommitOnce` | 8 passed | ✓ PASS |
| CR-02 grace-period grant term (gap 5) | inline script calling `status_at` then computing the `ends_at` the shipped `write_subscription_grant` call site passes | `status_at` returns `grace_period`; `ends_at` is already in the past; `_effective_grants_statement`'s `ends_at > evaluated_at` is `False` | ✗ FAIL (confirms gap) |
| CR-04 malformed `.env.example` values (gap 6) | `AppStoreConfig(app_apple_id='...', environment='...')` | Two `ValidationError`s raised | ✗ FAIL (confirms gap) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| APPLEHOOK-01 | 43-01 … 43-06 | Ingest Apple notifications outside the auth dependency, JWS-only auth | ⚠ PARTIALLY SATISFIED | The auth/verification half is solid (truths 1–2). The ingestion-correctness half the requirement's own text implies ("ingests") is undermined by gap 5 (CR-01/02/03) and gap 6 (CR-04). REQUIREMENTS.md marks it "met as written" on the literal auth text, which is defensible, but does not mention CR-01/02/03/04 at all — the amendment (plan 43-06) was written before/without incorporating the code review's findings. |
| APPLEHOOK-02 | 43-01, 43-06 | Route in the provider-callback category by exact path | ✓ SATISFIED | Truth 3, fully verified. No orphaned Phase 43 requirement IDs found in REQUIREMENTS.md's traceability table. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/nativespeaker/api/services/subscriptions.py` | 83-85, 87-131 | No monotonicity/ordering guard on subscription-state writes | 🛑 Blocker | CR-01 — see gap 5 |
| `src/nativespeaker/api/services/subscriptions.py` | 128-130 | `grace_period` grant written with an already-past `ends_at` | 🛑 Blocker | CR-02 — see gap 5, independently reproduced |
| `src/nativespeaker/api/services/subscriptions.py` | 83, 101-103 | Server-minted UUID indistinguishable from a real attribution token in the conflict guard | 🛑 Blocker | CR-03 — see gap 5 |
| `.env.example` | 105-107 | Placeholder values that raise `ValidationError` rather than resolving to `None` | 🛑 Blocker | CR-04 — see gap 6, independently reproduced |
| `src/nativespeaker/api/crud/subscriptions.py` | 121, 151, 177, 218, 248 | `violation.orig.sqlstate` accessed with no `getattr` guard (flagged by `ty`) | ⚠️ Warning | WR-03 in 43-REVIEW.md; not independently reproduced, not treated as a blocker here since it degrades a lost-race into an opaque 500 rather than corrupting data |
| `src/nativespeaker/api/routers/webhooks.py` | 13-14, 24 | Verifier dependency declared twice, correctness rests on undocumented FastAPI de-dup behavior | ⚠️ Warning | WR-02 in 43-REVIEW.md; failure mode is closed (a total, visible 422 outage), not open |
| `src/nativespeaker/api/tables/purchases.py` | 91-92 | `identity_value` conflates server-minted and store-supplied values with no discriminator column | ⚠️ Warning | WR-06 in 43-REVIEW.md; root cause of CR-03 |

No `TBD`/`FIXME`/`XXX` markers found in the phase's own new/modified files.

### Human Verification Required

None. All findings above were verified either by direct code reading, by re-running an existing automated test, or by independent reproduction with a standalone script (CR-02, CR-04) in this verification session.

### Gaps Summary

The route's authentication and callback-partition mechanics (ROADMAP criteria 1–3) and its literal
replay/idempotency guarantee (criterion 4) are all solidly built and independently confirmed —
this is not a superficial or stubbed implementation. The gap is downstream of verification, in the
state machine that turns a verified notification into a subscription row and a grant, exactly where
this phase's own committed code review (`43-REVIEW.md`, status `issues_found`, 4 critical findings)
already found it, and none of the four critical findings has been fixed by any plan in this phase
(43-06 is documentation-only; no 43-07 exists). Two of the four (CR-02, CR-04) were independently
reproduced in this verification rather than taken on the review's word.

The practical consequence: a paying customer's grant can be silently downgraded by an
out-of-order Apple delivery (CR-01), a subscriber Apple is actively covering during a grace period
can hold an entitlement label with zero actual allowance (CR-02), a purchase first seen without an
attribution token can never be attributed and permanently 500s on every subsequent delivery
(CR-03), and the checked-in `.env.example` — if a deployer follows its own instructions — crashes
the whole service's boot rather than costing only this route its documented 503 (CR-04). These are
not edge cases invented by this verification; three were reproduced against the real service over
the phase's own test stubs by the code review, and two were reproduced again, independently, here.

`08-webhook-app-store.md`'s flagged divergences (D-02, D-04, D-06, D-09) recorded under
APPLEHOOK-01 are legitimate, deliberate, and correctly documented — they are not part of this
report's gaps. The gaps above are implementation defects, not documented divergences.

---

_Verified: 2026-09-04_
_Verifier: Claude (gsd-verifier)_
