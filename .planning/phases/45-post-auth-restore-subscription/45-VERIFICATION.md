---
phase: 45-post-auth-restore-subscription
verified: 2026-09-08T22:15:00Z
status: passed
score: 7/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/7
  gaps_closed:
    - "A valid Apple artifact and a valid Google artifact each attach entitlement through their server-determined branch, correctly reflecting what was verified (ROADMAP SC1) — CR-02"
    - "A cross-account move expires only the source account's grant for the subscription being moved; the source account's grants for other subscriptions are untouched — CR-03"
    - "The Google Play verification request is sent to the endpoint and package the server intends, and is not redirectable by caller-supplied restore_proof content — CR-01"
  gaps_remaining: []
  regressions: []
---

# Phase 45: POST /auth/restore-subscription Verification Report

**Phase Goal:** Verify a native store artifact directly against Apple or Google and attach verified paid entitlement.
**Verified:** 2026-09-08
**Status:** passed
**Re-verification:** Yes — after gap closure (45-06 … 45-09)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A valid Apple and a valid Google artifact each attach entitlement through their server-determined branch, and the entitlement attached correctly reflects the verified state (ROADMAP SC1) | ✓ VERIFIED | `services/restore.py:62-67,144` binds `term_ends_at` once from the proof (grace window when status is `grace_period`, else `expires_at`), refuses before any write when it is absent or already past, and passes that same binding as `ends_at` — the checked term and the written term cannot drift. Empirically confirmed pre-fix/post-fix by `tests/e2e/test_restore_subscription.py::TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach` (6 cases) and two cases in `TestTheTwoRefusalsOfTheRestoreNotFoundFamily`, all run and passing in this session (`uv run pytest -m e2e "tests/e2e/test_restore_subscription.py::TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach" -v` → 6 passed). CR-02's two reachable defects (permanent `ends_at IS NULL`, bricked stale-term slot) are closed. **See WR-01 below: an under-grant scenario is a known, accepted residual, not a failure of this truth's own claim.** |
| 2 | All store verification completes before the mutating transaction opens; no network call runs under a lock (ROADMAP SC2) | ✓ VERIFIED | `services/restore.py:49` still calls `self._verify(...)` as the method's first statement, unchanged from the prior verification. `tests/unit/test_restore_proof.py`'s counting-session ordering cases pass (part of the 1255 unit total run in this session). |
| 3 | A non-native surface (a `provider` outside `PurchaseProvider`) receives 403 `operation_not_allowed` (ROADMAP SC3) | ✓ VERIFIED | `routers/auth.py:166-169`, unchanged from the prior verification: `body.provider not in PurchaseProvider` raises `RestoreProviderUnknown` before any proof check. Route registered exactly once (`grep -c 'router.post("/auth/restore-subscription"'` = 1). |
| 4 | An unverifiable artifact (a proof that does not verify) attaches nothing and leaves grant/usage/subscription/purchase row counts unchanged (ROADMAP SC4) | ✓ VERIFIED | e2e refusal matrix in `tests/e2e/test_restore_subscription.py` still drives four proof-rejection arms across both stores and asserts row counts unchanged and bodies byte-equal; part of the 333 e2e cases run and passing in this session. |
| 5 | The two-refusal surface gate (unserved provider, unverified proof) is the whole gate; no platform heuristic is applied | ✓ VERIFIED | `routers/auth.py` gate is unchanged: D-01 (provider membership) then the service's proof check (D-02); no header or stored column read. Confirmed by direct reading of the current router source. |
| 6 | A cross-account move expires only the source account's grant for the subscription being moved, leaving the source account's grants for other subscriptions untouched | ✓ VERIFIED | `crud/subscriptions.py:253-255` — `superseded` is now `[grant for grant in marked_active if grant.user_id == user_id or grant.subscription_id == subscription_id] if entitled else held`, narrowed from the prior unconditional `list(marked_active)`. Directly confirmed against the current source and empirically confirmed by running `tests/schema/test_restore_race.py::TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves` (4 cases) and `TestTheDestinationStillLosesEverythingItHeld` (3 cases) in this session against real PostgreSQL — 7/7 passed, including `test_the_source_keeps_its_active_grant_for_the_unrelated_subscription`, the case that reproduced CR-03 as a real `'expired' == 'active'` assertion failure pre-fix. **See WR-03 below: a latent (unreachable, per code-review construction attempt) asymmetry between the replay predicate and the widened supersede predicate is recorded as an open, non-blocking residual.** |
| 7 | The Google verification request cannot be redirected by caller-supplied `restore_proof` content — the service's own OAuth-signed call reaches only the intended `subscriptionsv2.get` endpoint | ✓ VERIFIED | `auth/google_play.py:154-156,259-264,314-317` — both interpolated URL segments are percent-escaped with `quote(value, safe="")` (closing the original CR-01 finding), **and** `_names_one_path_segment` refuses a purchase token or package name that is nothing but dots before any request is built, closing the dot-segment-removal gap the first closure missed (45-REVIEW's reopened CR-01, fixed by `f28047a`/`513ef70`/`f4c006c`). Empirically re-verified in this session, not read from the SUMMARY: `uv run pytest tests/unit/test_restore_proof.py::TestThePlayRequestUrlIsConfinedToOneResource -v` → 9/9 passed, including the three dot-only-token cases (`.`, `..`, `....`) each asserting `sent == []` (nothing reaches the transport) and `refusal.value.stage == GONE_STAGE`. |

**Score:** 7/7 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/services/restore.py` | `RestoreService` with `restore` method, four branches, term reconciliation | ✓ VERIFIED (exists, substantive, wired) — CR-02 closed |
| `src/nativespeaker/api/auth/app_store.py` | Local Apple proof verification | ✓ VERIFIED — unchanged; still reports `grace_period_expires_at=None` unconditionally (see WR-01) |
| `src/nativespeaker/api/auth/google_play.py` | `read_for_restore` Play proof read, escaped URL, dot-only guard | ✓ VERIFIED (exists, wired) — CR-01 closed, including the reopened dot-segment gap |
| `src/nativespeaker/api/crud/subscriptions.py` | `claim_subscription_owner`, D-09 owner rule, narrowed `superseded` scoping | ✓ VERIFIED (exists, wired) — CR-03 closed |
| `src/nativespeaker/api/crud/grants.py` | Two-user ascending grant lock | ✓ VERIFIED — unchanged |
| `src/nativespeaker/api/routers/auth.py` | `POST /auth/restore-subscription`, `Depends()`-only, surface gate | ✓ VERIFIED — unchanged, byte-identical per 45-06's own diff check |
| `src/nativespeaker/api/schemas/auth.py` | `RestoreRequest` with bounded `provider`/`restore_proof` | ✓ VERIFIED — `max_length=32` / `max_length=8192` present (WR-02 closed) |
| `src/nativespeaker/api/app/dependencies.py` | `get_restore_service` wiring `app_store`, `play`, `package_name` | ✓ VERIFIED — unchanged |
| `tests/e2e/test_restore_subscription.py` | e2e cases for all outcomes, refusals, term reconciliation | ✓ VERIFIED (333 e2e passing, run in this session) |
| `tests/schema/test_restore_race.py` | Race, atomicity, deferred-FK, move-scoping cases on real PostgreSQL | ✓ VERIFIED (229 schema passing, run in this session) |
| `tests/unit/test_restore_proof.py` | Apple/Google proof unit cases, ordering, URL-escaping, dot-only guard | ✓ VERIFIED (1255 unit passing, run in this session; 9/9 URL-confinement class run individually) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `app.state.app_store_notifications` | `RestoreService.restore` | `get_restore_service` dependency | ✓ WIRED | unchanged |
| `app.state.play_subscriptions` | `RestoreService.restore` | `get_restore_service` dependency | ✓ WIRED | unchanged |
| `RestoreService.restore` | `SubscriptionsDB.write_subscription_grant` | direct call, `services/restore.py:134-145` | ✓ WIRED | `ends_at` now names the single `term_ends_at` binding checked at line 65, closing the drift CR-02 named |
| `RestoreService._verify` (Google branch) | `PlayDeveloperSubscriptions.read_for_restore` | direct call | ✓ WIRED | now refuses a dot-only token/package name before `_get` is ever called |
| `routers/auth.py` | `get_restore_service` | `Depends()` only | ✓ WIRED | unchanged |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Route registered exactly once | `grep -c 'router.post("/auth/restore-subscription"' src/nativespeaker/api/routers/auth.py` | `1` | ✓ PASS |
| No debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) across all 10 phase-modified files | grep across `services/restore.py`, `auth/google_play.py`, `auth/app_store.py`, `crud/subscriptions.py`, `schemas/auth.py`, `routers/auth.py`, `app/dependencies.py`, and the three test files | no matches | ✓ PASS |
| CR-01 follow-up: dot-only Play tokens reach no transport | `uv run pytest tests/unit/test_restore_proof.py::TestThePlayRequestUrlIsConfinedToOneResource -v` | 9/9 passed, including `[.]`, `[..]`, `[....]` parametrizations, each asserting `sent == []` | ✓ PASS |
| CR-02 follow-up: term reconciliation e2e class | `uv run pytest -m e2e "tests/e2e/test_restore_subscription.py::TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach" -v` | 6/6 passed | ✓ PASS |
| CR-03 follow-up: move-scoping schema classes on real PostgreSQL | `uv run pytest -m schema "tests/schema/test_restore_race.py::TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves" "tests/schema/test_restore_race.py::TestTheDestinationStillLosesEverythingItHeld" -v` | 7/7 passed | ✓ PASS |
| Full suite, run in this verification (not copied from any SUMMARY) | `uv run pytest -q` | **1255 passed**, 562 deselected | ✓ PASS |
| Full suite, e2e marker | `uv run pytest -m e2e -q` | **333 passed**, 1484 deselected | ✓ PASS |
| Full suite, schema marker (real PostgreSQL) | `uv run pytest -m schema -q` | **229 passed**, 1588 deselected | ✓ PASS |
| Lint | `uv run ruff check src tests` | All checks passed | ✓ PASS |

All four counts match the orchestrator-observed figures (1255 / 333 / 229, ruff clean) exactly — run independently in this session against the current `HEAD` (`f4c006c`), not copied from any SUMMARY.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| RESTORE-01 | 45-01…45-05 (source), 45-06…45-09 (gap closure) | Verifies a native store artifact directly against Apple or Google and attaches verified paid-subscription entitlement through one of two server-determined branches | ✓ SATISFIED | Marked `[x]` in REQUIREMENTS.md with a dated 2026-09-08 gap-closure entry naming CR-01/CR-02/CR-03, their fixes, and their covering test classes by name. All three defects independently confirmed closed against the current source and by running the named tests myself in this session (not by reading the entry). |
| RESTORE-02 | 45-01, 45-02, 45-05, 45-06, 45-09 | The endpoint is a native-only surface; other surfaces receive `operation_not_allowed` | ✓ SATISFIED | Unaffected by the gap closure's source changes; the two-refusal gate remains D-01 (provider membership) then D-02 (proof verification), now additionally guarded by the two field length bounds ahead of both (WR-02, closed in 45-06). |

No orphaned requirements: `grep -n "^\- \[.\]" REQUIREMENTS.md \| grep -i restore` surfaces only RESTORE-01/02, and every phase plan (45-01 through 45-09) declares one or both in its `requirements:` frontmatter.

### Anti-Patterns Found

No debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) in any phase-modified file. The items below are correctness/documentation observations from 45-REVIEW.md (2026-09-08T21:42:08Z) and this session's own reading, none of which defeats an observable truth above.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/nativespeaker/api/services/restore.py` | 62-67 | An Apple proof's `grace_period_expires_at` is always `None` (`app_store.py:147`), so a stored `grace_period` row can never itself supply an open term for the new check to accept | ⚠️ Warning (WR-01, 45-REVIEW.md) | A legitimate Apple subscriber whose card failed and whose account is genuinely in Apple's billing grace period (up to 16 days) is refused (`404 restore_not_found`) when restoring on a new device, rather than granted entitlement. **Judged non-blocking**: this is a fail-closed under-grant, not an over-grant — nothing incorrect is ever attached, which is the direction CLAUDE.md's security guidance favors, and the only honest fix (persisting the grace window server-side from the webhook payload) is a schema change out of this gap closure's scope. Recorded here for a product decision, not resolved silently. |
| `src/nativespeaker/api/crud/subscriptions.py` | 240-249 | The replay short-circuit (`held`) is still narrowed to the destination's own rows, while the widened `superseded` set (245's fix) now also reaches the source's row for the moved subscription — the two predicates cover different sets | ℹ️ Info (WR-03, 45-REVIEW.md) | Reviewer could not construct a reachable sequence to the state this asymmetry would need (the one-active-grant-per-user index and every writer that could create the combination already expires it in the same transaction); confirmed latent, not live, by re-reading the code in this session. Recorded as a residual design asymmetry, not a live defect. |
| `tests/e2e/test_restore_subscription.py` | 382-400 | `test_a_term_ending_at_the_captured_instant_is_not_open` is named for the `==` boundary but its fixture only reaches `term_ends_at < evaluated_at` | ℹ️ Info (WR-04, 45-REVIEW.md) | The source code (`services/restore.py:65`, `<=`) correctly implements the closed boundary; only the named e2e case doesn't independently pin the exact-equality case (it is reachable at the unit level, where the evaluated instant is a fixed constant, per the reviewer's suggested fix). Coverage gap, not a functional defect. |
| `.planning/REQUIREMENTS.md` | 527 | The RESTORE-01 gap-closure entry's WR-01…WR-07/IN-01…IN-04 list is copied from the **pre-gap-closure** code review, whose WR-01 was about the unused `restore_bound_user_id` column — not the current 45-REVIEW.md's WR-01 (the Apple grace-period restore denial above), which post-dates 45-09's write of that entry | ℹ️ Info | REQUIREMENTS.md does not name the reopened-and-closed CR-01 dot-segment gap or the new WR-01/WR-03/WR-04 findings from the second (post-gap-closure) code review. Documentation staleness only — every finding was independently confirmed against the current source and test suite in this verification, not read from REQUIREMENTS.md. |

### Human Verification Required

None. All seven truths, the CR-01 reopened-and-closed fix, and the WR-01/WR-03/WR-04 residuals were independently confirmed in this session by direct source reading and by running the named tests myself (not by reading SUMMARY or REQUIREMENTS.md claims). WR-01's acceptability as a known, fail-closed, documented product trade-off was judged directly in this report per the task's explicit instruction to render a judgment rather than escalate a technically-resolved question.

### Gaps Summary

None. All three blocker gaps from the 2026-09-07 verification are closed and independently re-confirmed in this session, on the current source at `HEAD f4c006c`:

1. **CR-02 (truth 1)** — the status/term reconciliation check in `services/restore.py` closes both reachable defects the prior report named (the permanent `ends_at IS NULL` grant and the bricked stale-term slot). Confirmed by direct source reading and by running `TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach` (6/6 passed).
2. **CR-03 (truth 6)** — the narrowed `superseded` set in `crud/subscriptions.py` confines a move's expiry to the destination's whole set plus only the source's row for the subscription actually being moved. Confirmed by direct source reading and by running the two move-scoping schema classes on real PostgreSQL (7/7 passed).
3. **CR-01 (truth 7)** — the Play read URL is percent-escaped, **and** the reopened dot-segment-removal gap (found by 45-REVIEW.md after the first closure, closed by commits `f28047a`/`513ef70`/`f4c006c`) is independently confirmed closed in this session: driving the three adversarial tokens `.`, `..`, `....` through `TestThePlayRequestUrlIsConfinedToOneResource` shows nothing reaches the transport (`sent == []`).

The full suite — `uv run pytest -q` (1255 passed), `uv run pytest -m e2e -q` (333 passed), `uv run pytest -m schema -q` (229 passed), `uv run ruff check src tests` (clean) — was run independently in this verification session against the current `HEAD`, and matches the orchestrator-observed figures exactly.

**One warning is carried forward as an open, non-blocking residual rather than resolved**: WR-01 (an Apple subscriber genuinely inside a billing grace period cannot restore, because the client-presented proof carries no grace-window term for the server to check against). This is a fail-closed under-grant — no entitlement is ever incorrectly attached — introduced as the accepted cost of closing CR-02's over-grant, explicitly reasoned about in 45-REVIEW.md, and requiring a schema change (persisting the grace window server-side) to resolve properly. It does not defeat any of the phase's seven observable truths as written, and is recorded here for a product decision rather than silently dropped. WR-03 (a latent, unreachable predicate asymmetry) and WR-04 (an e2e boundary case that doesn't independently pin the `==` case the source already implements correctly) are lower-severity coverage/design notes, neither live nor blocking.

---

_Verified: 2026-09-08_
_Verifier: Claude (gsd-verifier)_
