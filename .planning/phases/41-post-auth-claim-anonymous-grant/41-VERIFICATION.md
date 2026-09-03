---
phase: 41-post-auth-claim-anonymous-grant
verified: 2026-09-03T07:30:33Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 41: POST /auth/claim-anonymous-grant Verification Report

**Phase Goal:** Ship the sole creator of `anonymous_device_grant` access grants.
**Verified:** 2026-09-03T07:30:33Z
**Status:** passed
**Re-verification:** No — this is the first VERIFICATION.md for this phase. A code review (`41-REVIEW.md`) ran first and found 2 critical defects; both are fixed and committed (`ed95eae`, `e2e18de`), and this report verifies the fixes directly against the codebase rather than trusting either the original SUMMARYs or the fix commit messages.

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP Success Criterion) | Status | Evidence |
|---|---|---|---|
| 1 | This is the only code path that writes a grant row with `source='anonymous_device_grant'` | ✓ VERIFIED | `grep -n "anonymous_device_grant" src/` shows the value constructed as `AccessGrant(...)`/`AccessGrantAntiAbuse(...)` only in `crud/grants.py:108,115` (`activate_anonymous_device_grant`); other hits are enum definitions (`schemas/auth.py:47`, `tables/grants.py:16`) or reads (`services/auth.py:154,173`). `tests/unit/test_grant_sources.py::TestTheAnonymousDeviceGrantHasExactlyOneWriter` walks the whole `src/` tree and is proven to fire (a second construction site was added, observed to fail, and reverted) — passes. |
| 2 | The grant transaction locks grant rows ascending by id, then their usage rows, with no network call while any lock is held | ✓ VERIFIED | `crud/grants.py::activate_anonymous_device_grant` calls `lock_effective_grants` (`FOR UPDATE`, `ORDER BY id ASC`) then `lock_usage` per grant, with only a plain non-locking re-read of the identity row after. Both Apple calls (`read_bits_with_retry`, `write_bits_with_retry`) run in `services/auth.py::_claim_anonymous_grant` strictly before `activate_anonymous_device_grant` is invoked — no lock is open during either. Confirmed live against real Postgres by `tests/schema/test_grant_locks.py::TestTheActivationAddsNoThirdLockTier` (captures actual SQL via `before_cursor_execute`, asserts exactly 2 lock tiers, neither `core.external_identities` nor `core.users`) and structurally by `tests/unit/test_claim_ordering.py::TestTheCrudWriterCannotReachTheVendor` (AST + subprocess import check: the crud writer names no DeviceCheck seam member and cannot import an HTTP client). All pass. |
| 3 | A second claim on an account that already holds a free grant does not allocate a second one | ✓ VERIFIED | Sequential repeat: `_claim_anonymous_grant` returns early (no Apple call, no write) when `read_effective_grants` finds an existing `anonymous_device_grant`; when the free-grant marker is set but the grant is no longer active, `has_prior_free_grant`/`free_grant_consumed_at` (no status predicate) still refuse via `FreeGrantAlreadyConsumed`. Concurrent case proven live: `tests/schema/test_claim_race.py::TestTwoSimultaneousFirstClaimsAllocateOnce` drives two real completions on independent connections/sessions against real Postgres to a barrier, and asserts exactly one grant row, one anti-abuse row, one usage row, one `free_grant_consumed_at`, both challenges consumed, and the loser answered **200 with the winner's entitlement** (not a 500). All 10 cases in this class pass. |
| 4 | The endpoint is challenge-bearing: prepare is served by shared `POST /auth/challenge`, completion requires a handle that route issued and bound to the caller's identity row — reworded by Phase 41 (D-18) | ✓ VERIFIED | `routers/auth.py::issue_challenge` (`POST /auth/challenge`) issues handles for `claim_anonymous_grant` via the shared `ChallengesDB.issue`. `claim_anonymous_grant` route requires `get_linked_identity` and calls `AuthService.complete_claim_anonymous_grant` → `_complete`, whose first steps are `challenge_store.locate` + `challenge_store.verify_binding(located, identity)` + operation-match check, before any claim/consume happens. ROADMAP.md Phase 41 criterion 4 carries the exact reworded text quoted in this verification task, dated 2026-09-03, with the ANONGRANT-01 amendment cross-referenced in REQUIREMENTS.md. `tests/unit/test_claim_precedence.py::TestTheRejectionsBeforeTheClaimSpendNothing` and the challenge-lifecycle cases in the same file pass. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/services/auth.py` | Single completion sequence; race-loser arm answers 200, not 500 | ✓ VERIFIED | `_claim_anonymous_grant`'s `if not activated:` arm (line ~180) now reads only `await self.session.rollback()` — both `session.refresh(identity.user)`/`session.refresh(identity.identity)` calls from CR-01 are deleted (commit `ed95eae`). |
| `src/nativespeaker/api/schemas/auth.py` | `AnonymousGrantClaimRequest` binds one device to both the DeviceCheck read and write | ✓ VERIFIED | Single `device_token: str = Field(..., min_length=1)` field; the old `query_token`/`update_token` pair is gone (commit `e2e18de`). |
| `src/nativespeaker/api/crud/grants.py` | Single writer, fixed two-tier lock order | ✓ VERIFIED | `activate_anonymous_device_grant` is the only construction site; lock order is `lock_effective_grants` → `lock_usage` per grant → plain re-read. |
| `tests/schema/test_claim_race.py` | Regression coverage for CR-01 (detached-row shape) | ✓ VERIFIED | `resolve_identity` uses `harness.factory()` closed before the service session is built, matching `get_identity`'s shape; `test_neither_attempt_handed_the_service_a_row_of_its_own_session` asserts `caller_rows_detached == [True, True]`; `test_the_loser_answers_two_hundred_with_the_winners_entitlement` asserts status 200. |
| `tests/unit/test_claim_precedence.py` | Regression coverage for CR-01 and CR-02 | ✓ VERIFIED | Stub `_StubSession.refresh` now raises `InvalidRequestError` on any caller-row refresh (would fail if the refresh calls reappeared); `TestTheDeviceReadAndTheDeviceWriteNameOneDevice` asserts the read token equals the write token and that a two-token body is rejected 422 before the gate. |

### Data-Flow Trace

Not applicable — this is a backend transactional endpoint with no rendered UI; the relevant "flow" is the DB write path, verified directly above via live-database schema tests (`test_grant_locks.py`, `test_claim_race.py`) rather than a grep-only trace.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full unit suite (partition 1 of 3) | `uv run pytest -q -m "not e2e and not schema"` | `952 passed, 361 deselected` | ✓ PASS |
| Full e2e suite (partition 2 of 3) | `uv run pytest -q -m e2e` | `226 passed, 1087 deselected` | ✓ PASS |
| Full schema suite (partition 3 of 3, real Postgres) | `uv run pytest -q -m schema` | `135 passed, 1178 deselected` | ✓ PASS |
| Lint | `uv run ruff check src tests` | `All checks passed!` | ✓ PASS |
| No unresolved debt markers in phase-modified files | `grep -nE "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER" <files>` | no matches | ✓ PASS |

Total across the three partitions: 952 + 226 + 135 = 1313, 0 failed, 0 skipped — a complete, non-overlapping partition of the suite, re-run independently in this verification (not taken from SUMMARY.md or the fix commit messages).

### Requirements Coverage

| Requirement | Source Plan(s) | Status | Evidence |
|---|---|---|---|
| ANONGRANT-01 | 41-01, 41-03, 41-05 | ✓ SATISFIED | Single-writer test passes; challenge-binding verified in code and tests; REQUIREMENTS.md carries the dated amendment and reworded ROADMAP criterion 4. |
| ANONGRANT-02 | 41-01, 41-04, 41-05 | ✓ SATISFIED | Lock-order proven live against real Postgres (`test_grant_locks.py`); no-network-under-lock proven structurally (`test_claim_ordering.py`) and by the passing e2e/schema suites. |
| ANONGRANT-03 | 41-03, 41-04, 41-05 | ✓ SATISFIED | Sequential and concurrent no-double-allocation proven; race-loser now answers 200 (post-CR-01-fix), verified directly against the fixed code, not the pre-fix REVIEW.md description. |

No orphaned requirements found for Phase 41 in REQUIREMENTS.md beyond the three declared.

### Anti-Patterns Found

None blocking. `grep` for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` and empty-return/stub patterns across every file this phase's plans declared modified (`devicecheck.py`, `errors.py`, `schemas/auth.py`, `tables/grants.py`, `crud/grants.py`, `services/auth.py`, `routers/auth.py`, `app/dependencies.py`, `app/lifespan.py`, `config.py`, `resilience.py`) returned no matches.

### Open Findings Carried Forward (Not Goal-Blocking)

These are recorded per the task's instruction to note them, not treat them as verification failures — each was independently confirmed still present in the current codebase:

- **WR-05** (`crud/grants.py` docstring vs. success path): confirmed still open. `tests/schema/test_grant_locks.py::TestTheActivationAddsNoThirdLockTier::test_the_identity_row_is_revalidated_by_a_plain_re_read` explicitly asserts `activated is False` and `not [INSERT statements]` — i.e., the "never a third tier" claim is proven only on the branch that writes nothing, not on the branch that actually inserts (which additionally takes an FK-enforced `KEY SHARE` on `core.users` and a row-exclusive lock via the `UPDATE core.external_identities`). This is a real deadlock hazard against `/auth/upgrade-anonymous`'s opposite lock order, not fabricated by the reviewer.
- **WR-01** (`IntegrityError` over-broad classification): confirmed still open in `crud/grants.py:128-133` — any `IntegrityError` at flush, not just the unique-index violation, is read as a race loss. The "anonymous" tier id assumption it flagged is, however, confirmed correct against `migrations/20260818_01_initial-release.sql:124-127` (`INSERT INTO core.access_tiers ... ('anonymous', 10)`), so that specific sub-risk is lower than the review implied, though the broad `except IntegrityError` remains unnarrowed.
- **WR-02, WR-04, WR-09** and the 7 INFO findings: not independently re-verified item-by-item in this pass (they are style/robustness findings against `devicecheck.py` and `resilience.py`/`lifespan.py`, orthogonal to the four ROADMAP success criteria and to CR-01/CR-02), but spot-checked for continued presence — `devicecheck.py`'s `_parse_bit_state` still classifies before parsing the body (WR-02), `schemas/auth.py`'s `device_token`/`challenge_id` fields still carry no `max_length` (WR-09).
- **Stale suite counts in `REQUIREMENTS.md`**: the ANONGRANT amendment (line 36) quotes "950 passed / 226 passed / 134 passed" from before the CR-01/CR-02 fix commits, which added one unit test and one schema test (now 952/226/135). The counts moved up, not down — no regression — but the quoted numbers in the ledger are now stale by two tests. Not a goal-blocker; flagged for the next docs pass.
- **41-01-PLAN.md / 41-RESEARCH.md §564-565 / 41-01-SUMMARY.md**: still describe the superseded two-token (`query_token`/`update_token`) claim body. Confirmed: these planning artifacts were not edited after CR-02. Per this milestone's stated convention (record divergences rather than edit history), this is consistent practice, but the task explicitly asked me to flag whether the ANONGRANT amendment needs an entry for this — it currently does not have one, and CR-02 is a fix commit that lands *after* all five plans' SUMMARYs and REQUIREMENTS.md's ANONGRANT amendment were written, so nothing in the ledger documents that the shipped wire shape changed from two tokens to one after 41-05 closed the phase. This is a documentation gap worth a follow-up note but does not affect the code's correctness, which was verified directly.

### Human Verification Required

None. All four ROADMAP success criteria are verified either structurally (single-writer walk, AST/import checks) or behaviorally against a real, uncached Postgres database (lock order, concurrent race, repeat/refusal precedence), and the full three-partition suite plus lint were re-run independently in this verification pass rather than trusted from SUMMARY.md.

### Gaps Summary

No gaps block the phase goal. The two review-flagged critical defects (CR-01: race-loser 500 via refresh of detached rows; CR-02: unbound device-token pair defeating the one-grant-per-device gate) are both confirmed fixed in the code, and the regression tests added alongside each fix are shaped so that reintroducing either defect would fail a named test (`_StubSession.refresh` now raises; the two-token body now 422s before the gate). The open WARNING/INFO findings from `41-REVIEW.md` (WR-01, WR-02, WR-04, WR-05, WR-09, IN-01..07) remain as recorded, are orthogonal to this phase's four success criteria, and are carried forward rather than treated as verification failures, per the task's explicit instruction.

---

_Verified: 2026-09-03T07:30:33Z_
_Verifier: Claude (gsd-verifier)_
