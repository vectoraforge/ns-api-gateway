---
phase: 45-post-auth-restore-subscription
verified: 2026-09-07T00:00:00Z
status: gaps_found
score: 4/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "A valid Apple artifact and a valid Google artifact each attach entitlement through their server-determined branch, correctly reflecting what was verified (ROADMAP SC1)"
    status: failed
    reason: "The stored subscription's status decides entitlement (services/restore.py:58) while the grant term (starts_at/ends_at) is taken unreconciled from the client-presented proof (services/restore.py:134-139). A stored row at status=grace_period combined with an Apple proof (which always reports grace_period_expires_at=None, per app_store.py's hardcoded value) writes a grant with ends_at=NULL — a never-expiring paid grant reachable through the documented D-06 entitlement rule. A stale/expired proof against an active stored row writes an already-past ends_at that occupies the account's one grant slot and cannot self-heal (a repeat restore replays it). Confirmed by reading services/restore.py:56-60 and 134-139 directly; no test in tests/unit/test_restore_proof.py or tests/e2e/test_restore_subscription.py exercises a stored status that disagrees with the proof's own term."
    artifacts:
      - path: "src/nativespeaker/api/services/restore.py"
        issue: "Lines 56-60 (status source) and 134-139 (term source) draw from two different, unreconciled inputs; nothing rejects a proof whose term does not support the status the stored row claims."
    missing:
      - "A check, before any write, that the proof's own term (grace_period_expires_at when status is grace_period, otherwise expires_at) is present and in the future; refuse RestoreSubscriptionNotEntitled otherwise, joining the existing byte-identical restore_not_found family."
      - "A test case seeding a stored subscription at grace_period status and restoring an Apple proof against it, asserting the written grant is NOT ends_at=NULL."
  - truth: "A cross-account move expires only the source account's grant for the subscription being moved; the source account's grants for other subscriptions are untouched (implied by ROADMAP SC1's 'the old owner's subscription grant is expired... in the same transaction')"
    status: failed
    reason: "crud/subscriptions.py:252 sets `superseded = list(marked_active) if entitled else held` — on a move, marked_active holds BOTH accounts' active grant rows (services/restore.py:94-95 locks [current_owner, destination]), so every active grant of the source account is expired, not only the one for the subscription being moved. An account that owns subscription S1 (active grant G1) and separately owns subscription S2, and loses S1 to a restoring caller D, has G2 (its S2 grant) silently expired even though D's proof said nothing about S2. This strips a paying customer of an unrelated, currently-paid entitlement. Confirmed by reading crud/subscriptions.py:240-259 directly. Neither tests/schema/test_restore_race.py nor tests/e2e/test_restore_subscription.py seeds the source account with a second, unrelated subscription — the code review (45-REVIEW.md CR-03) states this and the source confirms the gap: no such seed exists in either file."
    artifacts:
      - path: "src/nativespeaker/api/crud/subscriptions.py"
        issue: "Line 252 supersedes every grant in marked_active rather than narrowing to the destination's own rows plus the source's row for the specific subscription_id being moved."
    missing:
      - "Narrow the superseded set: `[g for g in marked_active if g.user_id == user_id or g.subscription_id == subscription_id]` (per 45-REVIEW.md CR-03's suggested fix)."
      - "A schema case seeding the source account with an active grant for a second, unrelated subscription, running the move, and asserting that grant is untouched and still active."
  - truth: "The Google Play verification request is sent to the endpoint and package the server intends, and is not redirectable by caller-supplied restore_proof content (bears on ROADMAP SC1 'verify... against Google' and SC4 'an unverifiable artifact attaches nothing')"
    status: failed
    reason: "auth/google_play.py:302-304 builds the request URL with plain str.format (`PLAY_URL.format(package_name=package_name, purchase_token=purchase_token)`), and purchase_token is restore_proof taken unmodified from the request body (schemas/auth.py:38-42, no max_length, no pattern). str.format performs no percent-encoding, and httpx normalises dot-segments, so a caller-supplied token containing path-traversal sequences repoints the deployment's OAuth-bearer-signed GET at an arbitrary androidpublisher.googleapis.com path. Verified empirically in this session: formatting purchase_token='a/../../../../v3/applications/evil/edits' against package_name='com.ns.app' yields a URL whose path resolves (after httpx's own dot-segment collapse) outside the intended purchases/subscriptionsv2/tokens/{token} resource. This is the service's own Google-scoped credential being pointed at attacker-chosen endpoints, defeating the package-name guard the code's own comment at google_play.py:261-262 relies on. No unit or e2e case in tests/unit/test_restore_proof.py or tests/e2e/test_restore_subscription.py asserts the request path is confined to the expected shape for an adversarial token."
    artifacts:
      - path: "src/nativespeaker/api/auth/google_play.py"
        issue: "_get (lines 296-304) interpolates package_name and purchase_token into PLAY_URL with str.format and no percent-encoding."
    missing:
      - "Percent-encode both path segments with urllib.parse.quote(..., safe=\"\") before interpolation, so a caller-supplied token can only ever name one path segment."
      - "A unit case asserting a token containing '../' and '?' produces a request whose path is still /androidpublisher/v3/applications/{package}/purchases/subscriptionsv2/tokens/... and whose query string is empty."
deferred: []
---

# Phase 45: POST /auth/restore-subscription Verification Report

**Phase Goal:** Verify a native store artifact directly against Apple or Google and attach verified paid entitlement.
**Verified:** 2026-09-07
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A valid Apple and a valid Google artifact each attach entitlement through their server-determined branch, and the entitlement attached correctly reflects the verified state (ROADMAP SC1) | ✗ FAILED | `services/restore.py:56-60,134-139` — status and term are drawn from two unreconciled sources; a stored `grace_period` row plus an Apple proof (whose `grace_period_expires_at` is hardcoded `None`, `app_store.py`) writes `ends_at=NULL`, a never-expiring paid grant. See 45-REVIEW.md CR-02, confirmed against the current source in this session. |
| 2 | All store verification completes before the mutating transaction opens; no network call runs under a lock (ROADMAP SC2) | ✓ VERIFIED | `services/restore.py:49` calls `self._verify(...)` as the method's first statement, before any `session.exec`/`read_subscription` call at lines 53-54. `tests/unit/test_restore_proof.py::TestTheStoreCallRunsBeforeTheSessionsFirstStatement` (counting-session recorder) passes; both stores' entry points are confirmed as the first call. |
| 3 | A non-native surface (a `provider` outside `PurchaseProvider`) receives 403 `operation_not_allowed` (ROADMAP SC3) | ✓ VERIFIED | `routers/auth.py:166-169` checks `body.provider not in PurchaseProvider` and raises `RestoreProviderUnknown` before any proof check. `RestoreProviderUnknown` declares `status=403, code="operation_not_allowed"` (`errors.py`). Route registered exactly once: `grep -c 'router.post("/auth/restore-subscription"'` = 1. |
| 4 | An unverifiable artifact (a proof that does not verify) attaches nothing and leaves grant/usage/subscription/purchase row counts unchanged (ROADMAP SC4) | ✓ VERIFIED | e2e refusal matrix (`tests/e2e/test_restore_subscription.py`) drives four proof-rejection arms across both stores through the real router and asserts row counts unchanged and bodies byte-equal; unit ordering cases assert zero session statements on refusal. |
| 5 | The two-refusal surface gate (unserved provider, unverified proof) is the whole gate; no platform heuristic is applied | ✓ VERIFIED | `routers/auth.py` gate is exactly D-01 (provider membership) then the service's proof check (D-02); no header or stored column read. Confirmed by direct reading of the router and service. |
| 6 | A cross-account move expires only the source account's grant for the subscription being moved, leaving the source account's grants for other subscriptions untouched | ✗ FAILED | `crud/subscriptions.py:252` — `superseded = list(marked_active) if entitled else held` supersedes **every** grant of both accounts (`marked_active` holds both, per `restore.py:94-95`), not merely the one tied to the moving subscription. A source account holding an unrelated, currently-paid subscription loses that grant silently on any move it loses. See 45-REVIEW.md CR-03, confirmed against current source; untested by both `tests/schema/test_restore_race.py` and `tests/e2e/test_restore_subscription.py`. |
| 7 | The Google verification request cannot be redirected by caller-supplied `restore_proof` content — the service's own OAuth-signed call reaches only the intended `subscriptionsv2.get` endpoint | ✗ FAILED | `auth/google_play.py:296-304` builds the request URL with unencoded `str.format`; `restore_proof` (no `max_length`, no pattern — `schemas/auth.py:38-42`) flows unmodified into the path. Empirically reproduced in this session: a token containing `../` sequences relocates the resolved path outside `purchases/subscriptionsv2/tokens/{token}`. See 45-REVIEW.md CR-01, confirmed against current source. |

**Score:** 4/7 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/services/restore.py` | `RestoreService` with `restore` method, four branches | ✓ VERIFIED (exists, substantive, wired) — but see truths 1 and 6 for correctness defects inside it |
| `src/nativespeaker/api/auth/app_store.py` | Local Apple proof verification | ✓ VERIFIED |
| `src/nativespeaker/api/auth/google_play.py` | `read_for_restore` Play proof read | ✓ VERIFIED (exists, wired) — see truth 7 for the unencoded-URL defect inside `_get` |
| `src/nativespeaker/api/crud/subscriptions.py` | `claim_subscription_owner`, D-09 owner rule, `write_subscription_grant` account-scoped replay fix | ✓ VERIFIED (exists, wired) — see truth 6 for the `superseded` scoping defect |
| `src/nativespeaker/api/crud/grants.py` | Two-user ascending grant lock | ✓ VERIFIED |
| `src/nativespeaker/api/routers/auth.py` | `POST /auth/restore-subscription`, `Depends()`-only, surface gate | ✓ VERIFIED |
| `src/nativespeaker/api/app/dependencies.py` | `get_restore_service` wiring `app_store`, `play`, `package_name` | ✓ VERIFIED |
| `tests/e2e/test_restore_subscription.py` | e2e cases for all outcomes and refusals | ✓ VERIFIED (321 e2e passing) — coverage gap: no case with a source account holding an unrelated second subscription during a move |
| `tests/schema/test_restore_race.py` | Race, atomicity, deferred-FK cases on real PostgreSQL | ✓ VERIFIED (222 schema passing) — same coverage gap as above |
| `tests/unit/test_restore_proof.py` | Apple/Google proof unit cases, ordering | ✓ VERIFIED — coverage gap: no adversarial-token URL-shape assertion |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `app.state.app_store_notifications` | `RestoreService.restore` | `get_restore_service` dependency | ✓ WIRED | `dependencies.py:155-162` reads `request.app.state.app_store_notifications` |
| `app.state.play_subscriptions` | `RestoreService.restore` | `get_restore_service` dependency | ✓ WIRED | same function, `play=request.app.state.play_subscriptions` |
| `RestoreService.restore` | `SubscriptionsDB.write_subscription_grant` | direct call, `services/restore.py:127-139` | ✓ WIRED | confirmed by direct read |
| `RestoreService.restore`'s `starts_at`/`ends_at` expression | `SubscriptionsService.ingest`'s expression | textual match (D-07) | ✓ WIRED (mechanically identical) — see truth 1: identical expression, but the *inputs* feeding it are unreconciled across the status/term sources |
| `routers/auth.py` | `get_restore_service` | `Depends()` only | ✓ WIRED | route handler takes no manual construction |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Route registered exactly once | `grep -c 'router.post("/auth/restore-subscription"' src/nativespeaker/api/routers/auth.py` | `1` | ✓ PASS |
| No debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) in phase files | grep across all 10 phase-modified source files | no matches | ✓ PASS |
| Play URL path-injection reproduction | `PLAY_URL.format(package_name='com.ns.app', purchase_token='a/../../../../v3/applications/evil/edits')` | resolves outside `purchases/subscriptionsv2/tokens/{token}` after httpx's dot-segment normalisation | ✗ FAIL (confirms CR-01) |
| `get_restore_service` wiring | direct read of `dependencies.py:155-162` | both `app_store` and `play` sourced from `request.app.state`, `package_name` from config | ✓ PASS |

Full suite (evidence supplied by orchestrator, not re-run in this verification): `uv run pytest -q` 1246 passed, `uv run pytest -m e2e -q` 321 passed, `uv run pytest -m schema -q` 222 passed, `uv run ruff check src tests` clean. **A green suite does not certify truths 1, 6 and 7 above** — none of the 1246+321+222 cases exercises a stored-status/proof-term mismatch, a source account with an unrelated second subscription during a move, or an adversarial `restore_proof` value used as a Play path segment.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| RESTORE-01 | 45-01, 45-02, 45-03, 45-04, 45-05 | Verifies a native store artifact directly against Apple or Google and attaches verified paid-subscription entitlement through one of two server-determined branches | ✗ BLOCKED | Marked `[x]` in REQUIREMENTS.md, but the entitlement attached is not reliably "verified": CR-02 shows a reachable combination producing a never-expiring or already-dead grant from an unreconciled status/term pair, and CR-03 shows a move can silently strip an unrelated, currently-paid entitlement from the source account. The requirement's own word "verified" is not honestly met while these hold. |
| RESTORE-02 | 45-01, 45-02, 45-05 | The endpoint is a native-only surface; other surfaces receive `operation_not_allowed` | ✓ SATISFIED | The two-refusal gate (D-01 provider membership, D-02 proof verification) is implemented and tested as designed; not affected by CR-01/02/03, which concern the verification mechanism's internal correctness rather than the surface gate. |

No orphaned requirements: `grep -E "Phase 45"` against REQUIREMENTS.md surfaces only RESTORE-01/02, both declared in the plans' frontmatter.

### Anti-Patterns Found

None (no TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers in any phase-modified file). The three defects below are correctness/security bugs identified by direct code reading, corroborated by the phase's own 45-REVIEW.md.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/nativespeaker/api/auth/google_play.py` | 302-304 | Caller-supplied token interpolated into an OAuth-signed request URL with no percent-encoding | 🛑 Blocker | Path-traversal/SSRF-adjacent: an authenticated caller can redirect the deployment's own Google credential to arbitrary `androidpublisher.googleapis.com` endpoints |
| `src/nativespeaker/api/services/restore.py` | 56-60, 134-139 | Entitlement status and grant term drawn from two unreconciled sources | 🛑 Blocker | Reachable never-expiring or dead paid grant; contradicts "verified paid entitlement" |
| `src/nativespeaker/api/crud/subscriptions.py` | 252 | `superseded` set not scoped to the subscription/account the write is about | 🛑 Blocker | A move can silently strip a paying customer's unrelated, currently-active entitlement |

### Human Verification Required

None. All three gaps are demonstrable by direct code reading and (for CR-01) empirical reproduction; no item requires subjective/visual/runtime judgment beyond what this report already performed.

### Gaps Summary

The phase delivers a large, well-tested surface — three outcomes (same-account, adoption, move) across two stores, ordering guarantees, a two-refusal gate, and real-PostgreSQL race/atomicity coverage — and the vast majority of the roadmap's stated success criteria and the plans' own must-haves are genuinely proven by executed cases, not merely claimed. SC2 (verification-before-lock) and SC3 (surface gate) are solid.

However, three defects identified in the phase's own code review (45-REVIEW.md CR-01, CR-02, CR-03) remain unfixed in the current source, and each one strikes at the phase's core goal — "verify a native store artifact... and attach verified paid entitlement":

1. **CR-01** — the Google verification call is not defended against a caller-supplied path-traversal token, so "verify... against Google" can be redirected by the very input it is meant to check.
2. **CR-02** — the status decided from the stored row and the term taken from the proof are never reconciled, so "attach verified paid entitlement" can mint a grant whose term does not correspond to anything actually verified (including a grant that never expires).
3. **CR-03** — the move's write scoping supersedes every active grant of the source account rather than only the grant for the subscription being moved, so a customer paying for an unrelated subscription can silently lose it.

None of the three is covered by the phase's own test suite (1246 unit / 321 e2e / 222 schema all green), because none of those cases sets up the specific state each defect requires (a stored/proof status-term mismatch, a source account with a second unrelated subscription, or an adversarial token value). The green suite is real evidence for what it tests; it is not evidence against these three gaps, which is exactly why 45-REVIEW.md's code review — not the test run — is what surfaced them.

These are BLOCKER-level findings: they are must-fix before this phase can be said to have achieved its goal soundly, not follow-on hardening. All three have concrete, narrow fixes recorded in 45-REVIEW.md (CR-01, CR-02, CR-03) that this report's `gaps:` frontmatter restates for `/gsd:plan-phase --gaps`.

Not classified as gaps (recorded for completeness, non-blocking): 45-REVIEW.md's seven Warnings (WR-01 through WR-07) and four Info items (IN-01 through IN-04) describe real but lower-severity issues — an unused `restore_bound_user_id` binding column with stale migration comments, unbounded `provider`/`restore_proof` field lengths, an ingestion/restore owner-read race, a missing audit trail for restores, a NULL `purchase_user_id` on adoption, same-account-two-devices returning 500 instead of the idempotent answer, and a shared clock-source inconsistency. None of these was found to defeat a roadmap success criterion on inspection, but WR-02 (unbounded `restore_proof`/`provider` length) is the same input surface CR-01 exploits and should be fixed in the same change.

---

_Verified: 2026-09-07_
_Verifier: Claude (gsd-verifier)_
