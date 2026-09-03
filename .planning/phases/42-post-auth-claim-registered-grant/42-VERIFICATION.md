---
phase: 42-post-auth-claim-registered-grant
verified: 2026-09-03T22:10:00Z
status: human_needed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
behavior_unverified_items: []
human_verification:
  - test: "Decide whether CR-01 (code review, critical) — the predicate mismatch between `_effective_grants_statement` (time-windowed) and `ix_access_grants_one_active_per_user` (no time predicate) — must be fixed before this phase is considered closed, or accepted and tracked as a blocking prerequisite for Phase 43."
    expected: "A recorded decision: fix now in a 42-07 closure plan, or accept-and-track with an explicit gate on Phase 43 (POST /webhooks/app-store) not landing a subscription/manual grant writer until the crud writer's `IntegrityError -> False` and `read_effective_grants`/index predicate mismatch are reconciled."
    why_human: "This is a severity/timing product decision, not a fact a verifier can resolve. The bug is real and reproduced (confirmed independently below), but is not reachable through any write path shipped by this phase or any prior phase — no code under src/ writes a manual or subscription grant yet, and nothing flips `status` to `expired` when `ends_at` elapses. It becomes reachable the moment Phase 43 (the very next phase) ships a subscription-grant writer with a term `ends_at`. Whether that risk is acceptable to carry into Phase 43 unfixed is a judgment call for the developer."
---

# Phase 42: POST /auth/claim-registered-grant Verification Report

**Phase Goal:** Ship the sole creator of `registered_account_grant` grants, including supersession of an active anonymous device grant.
**Verified:** 2026-09-03T22:10:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

The four truths below are the ROADMAP success criteria verbatim (Option A — roadmap contract).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | This is the only code path that writes a grant row with `source='registered_account_grant'` | VERIFIED | `crud/grants.py::activate_registered_account_grant` is the sole construction site (confirmed by reading the file: exactly one `AccessGrant(source=AccessGrantSource.registered_account_grant, ...)` literal, line 172). `tests/unit/test_grant_sources.py::TestTheRegisteredAccountGrantHasExactlyOneWriter` walks every module under `src/`, and `TestTheRegisteredWalkFires` mutation-tests it (confirmed present and named per plan 42-04's acceptance criteria; file exists, 9718 bytes, dated 2026-09-03 13:06). |
| 2 | Superseding an active anonymous grant happens in one transaction and never leaves two `status='active'` grants | VERIFIED | `activate_registered_account_grant` (`crud/grants.py:158-168`) flushes the expiry `UPDATE` before the `INSERT`, inside one session/transaction; `ix_access_grants_one_active_per_user` (`migrations/20260818_01_initial-release.sql:256-258`) is `UNIQUE(user_id) WHERE status='active'`, non-deferrable. `tests/schema/test_grant_locks.py::TestTheConversionExpiresBeforeItInserts` asserts the emitted-SQL order from `before_cursor_execute` capture (not a mirrored literal). `tests/schema/test_claim_race.py::TestTwoSimultaneousConversionsSupersedeOnce` (class confirmed present, line 487) races two real connections against real PostgreSQL and asserts exactly one active + one expired row. |
| 3 | The supersession honors the same fixed global lock order as Phase 41 | VERIFIED | `activate_registered_account_grant` calls `lock_effective_grants` (grant rows, `FOR UPDATE`, ascending by id) then `lock_usage` per grant, and re-reads the identity row with a plain `resolve_existing` (no lock) — identical tier structure to Phase 41's `activate_anonymous_device_grant`. `tests/schema/test_grant_locks.py::TestTheRegisteredWriterAddsNoThirdLockTier` (line 423) asserts exactly two distinct lock tiers and that neither is `core.external_identities` nor `core.users`, over statements captured from a real session — not a hand-mirrored literal. |
| 4 | An account that already consumed its free grant as anonymous does not receive a second free entitlement (reworded, per ROADMAP: conversion vs. refusal split) | VERIFIED | `_claim_registered_grant` (`services/auth.py:203-222`) reads effective grants and prior free-grant history by **source and status**, never by the blanket `free_grant_consumed_at`/`has_prior_free_grant(...)` alone — confirmed by reading the code (line 213 gates `has_prior_free_grant` only inside `if not held:`). An active anonymous grant converts (no second allowance: one row expires, one row inserts, usage counters copied); a revoked/expired anonymous grant with no active grant is refused `FreeGrantAlreadyConsumed`. `tests/unit/test_claim_precedence_registered.py` (28 cases, per 42-03-SUMMARY.md) and `tests/e2e/test_claim_registered_grant.py::TestTheFourRefusals` cover both branches; `tests/schema/test_claim_race.py::TestTwoSimultaneousConversionsSupersedeOnce` proves no double-allocation under contention. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/20260818_01_initial-release.sql` | Three tables + everything only they need removed (D-07) | VERIFIED | `grep -c "access_grants_anti_abuse\|provider_accounts\|gate_consumption"` returns `0`. Dev DB rebuilt and probed live: 12 core tables, none of the three deleted names (`access_grants`, `access_tiers`, `auth_challenges`, `chats`, `external_identities`, `manual_grant_issuances`, `messages`, `store_purchase_tokens`, `store_purchases`, `subscriptions`, `user_monthly_usage`, `users`). |
| `src/nativespeaker/api/tables/grants.py`, `tables/__init__.py`, `crud/grants.py` | `AccessGrantAntiAbuse` removed, `FREE_GRANT_SOURCES` untouched | VERIFIED | `grep -c "AccessGrantAntiAbuse"` returns `0` in all three files. |
| `src/nativespeaker/api/routers/auth.py` | `POST /auth/claim-registered-grant` behind `get_linked_identity`, `SyncResponse`, `no-store` | VERIFIED | Route present at line 123, handler `claim_registered_grant` at line 129, calls `service.complete_claim_registered_grant`. |
| `src/nativespeaker/api/services/auth.py` | `REGISTERED_TIER_ID`, `complete_claim_registered_grant`, `_claim_registered_grant` implementing D-09's five-arm decision | VERIFIED | Read in full; matches D-09's order exactly: repeat (line 205-207), other-source refusal (208-209), conversion (`if not held` false branch falls to writer with no Apple call), new grant with bit1 gate (211-222), history-by-source guard (213). |
| `src/nativespeaker/api/crud/grants.py` | `activate_registered_account_grant`, one writer, two branches, fixed lock order, expiry flushed before insert | VERIFIED | Read in full; matches plan 42-02's spec verbatim, including the separated flush boundary (line 164-168) that forces UPDATE before INSERT. |
| `src/nativespeaker/api/errors.py` | Fourth `ClaimRefused` leaf, `ClaimantNotRegistered`, no fields/status/code/`__init__` | VERIFIED | Line 448-449: declares nothing but a docstring. |
| `src/nativespeaker/api/schemas/auth.py` | Shared `GrantClaimRequest` replacing `AnonymousGrantClaimRequest` | VERIFIED | Line 31-35: `challenge_id`, `device_token`, both `min_length=1`. |
| Six new/extended test files (`test_claim_registered_grant.py`, `test_claim_precedence_registered.py`, `test_grant_locks.py`, `test_claim_race.py`, `test_grant_sources.py`, `test_claim_ordering.py`) | Substantive, not stubs | VERIFIED | All exist, all non-trivial in size (9.7KB–32KB), all contain named classes matching plan descriptions (spot-checked class names against plan text). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `routers/auth.py::claim_registered_grant` | `services/auth.py::complete_claim_registered_grant` | direct call, forwards handle + token | VERIFIED | Line 136 of `routers/auth.py`. |
| `services/auth.py::_claim_registered_grant` | `auth/devicecheck.py::read_bits_with_retry`/`write_bits_with_retry` | new-grant arm only, after commit, before writer | VERIFIED | Lines 217, 222; gated inside `if not held:` and further inside the `has_prior_free_grant` check — never on the conversion arm. |
| `services/auth.py::_claim_registered_grant` | `crud/grants.py::activate_registered_account_grant` | writer call, both arms | VERIFIED | Line 224. |
| `crud/grants.py` writer | `migrations/...sql::ix_access_grants_one_active_per_user` | expiry flushed before insert | VERIFIED, mutation-tested | Per 42-02-SUMMARY.md and plan 42-02 Task 2's acceptance criteria (mutation removing the flush boundary, observing the ordering case fail, reverting). |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| REGGRANT-01 | 42-02, 42-03, 42-04, 42-06 | Sole creator, across prepare/completion | SATISFIED | AST walk + mutation test; route registered and narrowed in `test_app_wiring.py`. |
| REGGRANT-02 | 42-01, 42-02, 42-05, 42-06 | Supersession in one transaction, fixed lock order | SATISFIED | Emitted-SQL order proof + two-connection race, both against real PostgreSQL. |
| REGGRANT-03 | 42-01, 42-02, 42-03, 42-05, 42-06 | One-free-grant-per-account interplay resolves without double-allocation | SATISFIED | History-by-source-and-status guard; precedence matrix; conversion race. |

No orphaned requirements found — `.planning/REQUIREMENTS.md` § REGGRANT covers exactly REGGRANT-01…03, matching the plans' `requirements:` frontmatter, and all three are marked `[x]` with dated Phase 42 amendments (`grep -n "REGGRANT" .planning/REQUIREMENTS.md`).

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any file this phase modified (grepped across all 23 `key-files` entries from the six SUMMARY files plus the three planning-ledger files). Working tree is clean; `1001 unit / 147 schema / 237 e2e` all pass, matching the orchestrator's pre-verification baseline exactly (re-ran the unit suite independently: `1001 passed, 384 deselected`).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Deletion landed and dev DB rebuilt | Live `asyncpg` query against `core.pg_tables` | 12 core tables, none of the three deleted names | PASS |
| Single-construction-site claim | `grep` count of `AccessGrantAntiAbuse` across `tables/grants.py`, `tables/__init__.py`, `crud/grants.py` | `0, 0, 0` | PASS |
| Unit suite green | `.venv/bin/python -m pytest -q` | `1001 passed, 384 deselected` | PASS |
| No status-flip-on-expiry writer exists in `src/` | `grep -rn "ends_at" src/nativespeaker/api/crud src/nativespeaker/api/services` | Only the two lines inside `crud/grants.py` (the effective-grants predicate and the conversion's own expiry write) | PASS (confirms CR-01's precondition below) |
| No manual/subscription grant writer exists in `src/` yet | `grep -rln "manual_grant_issuances\|ManualGrantIssuance"` and `grep -rn "AccessGrantSource.manual\|AccessGrantSource.subscription"` over `src/nativespeaker/api` | No output (no writer for either source) | PASS (confirms CR-01 is not reachable via any shipped write path today) |

### Probe Execution

Not applicable — this phase is not a migration/tooling phase with declared `scripts/*/tests/probe-*.sh` probes. Skipped.

## Independent Assessment of the Code Review (42-REVIEW.md)

The orchestrator asked me to judge, not inherit, CR-01's verdict against the phase goal. I read the review, then independently read `services/auth.py` and `crud/grants.py` in full and confirmed CR-01's two load-bearing facts directly from source and from the migration and a live database probe:

1. **The predicate mismatch is real.** `_effective_grants_statement` (`crud/grants.py:22-34`) filters `status='active' AND starts_at<=evaluated_at AND (ends_at IS NULL OR ends_at>evaluated_at)`. `ix_access_grants_one_active_per_user` (`migrations/...sql:256-258`) is `UNIQUE(user_id) WHERE status='active'` — no time predicate at all. A `status='active'` row whose `ends_at` has passed is invisible to the read but present to the index.
2. **Nothing in `src/` ever flips `status` to `expired` when `ends_at` elapses** (`grep -rn "ends_at"` over `crud/` and `services/` shows only the effective-grants predicate and the conversion's own explicit expiry write) — so such a row, once created, stays that way until acted on.
3. **No writer for `manual` or `subscription` grants exists anywhere in `src/` today** (`grep` for `manual_grant_issuances`, `ManualGrantIssuance`, `AccessGrantSource.manual`, `AccessGrantSource.subscription` over `src/nativespeaker/api` returns nothing).

Fact 3 changes the practical verdict from what CR-01's prose implies. The review reproduced the defect by driving `activate_registered_account_grant` directly against a row it seeded by hand — a valid way to test a precondition, but that precondition (a `status='active'`, past-`ends_at` `manual`/`subscription` grant) **cannot be produced by any code this phase, or any prior phase, has shipped.** No caller reaching this route through the real API today can trigger CR-01, WR-01, WR-02, WR-03 or WR-04. I also traced each plan's `must_haves.prohibitions` against the review's findings and confirmed none of the six plans' prohibitions is actually violated: in every failure mode the review describes, the writer's own flush-then-rollback discipline means a failed activation leaves the database exactly as it was before the attempt (confirmed by reading the `try`/`except IntegrityError: return False` blocks at `crud/grants.py:164-168` and `:189-194`, and the caller's `if not activated: await self.session.rollback()` at `services/auth.py:229-231`) — no partial supersession, no duplicate grant, no data corruption. The defect's actual shape is narrower than "the goal is not achieved": it is "a genuine write is silently reported as an idempotent 200 instead of a 403 or 500, and — specifically in CR-01's case — an irreversible DeviceCheck bit is spent first."

**My explicit judgment: these are defects alongside a met criterion, not violations of ROADMAP success criteria 1–4.** None of the four criteria requires "every possible future grant state resolves correctly" — they require sole-creator, no-double-active-grant, fixed-lock-order and no-double-free-entitlement, and all four hold under every state reachable by code this phase or any prior phase shipped. I verified this by reading the writer's rollback discipline directly rather than accepting the review's framing.

**Why this still needs a human decision rather than a silent pass.** CR-01 is CRITICAL severity, independently reproduced, and touches an explicitly irreversible, explicitly fail-closed, explicitly load-bearing control (D-01's bit1). It is not reachable today, but Phase 43 — the very next phase on the roadmap — ships `POST /webhooks/app-store`, whose entire purpose is to write subscription grants with a term `ends_at`. The moment that writer lands, CR-01 becomes live for any caller. `SHARED-INVARIANTS.md` § "Fail-closed defaults" is stated in `.planning/REQUIREMENTS.md`'s Phase 42 amendment as diverging "none" — that statement is accurate for what Phase 42 itself does, but it does not account for the shared `crud/grants.py` machinery Phase 42 both relies on and extends, which fails open in exactly the scenario CR-01 describes. Whether to fix this now, or to explicitly gate Phase 43 on fixing it first, is a product/timing decision I cannot make on the codebase's behalf — hence `human_needed` rather than `passed` or `gaps_found`.

I did **not** downgrade CR-01 to WARNING or drop it, and I did **not** inherit REVIEW.md's `critical: 1` framing wholesale into a blocking gap either — I am reporting the narrower, independently-verified fact pattern and escalating the decision.

### Human Verification Required

### 1. CR-01 disposition — fix now, or accept-and-gate Phase 43

**Test:** Review CR-01 in `42-REVIEW.md` and the "Independent Assessment" section above; decide whether `crud/grants.py`'s `IntegrityError -> return False` (overloaded to mean both "lost a race" and "write is impossible") and the `_effective_grants_statement`/`ix_access_grants_one_active_per_user` predicate mismatch must be fixed before this phase closes, or whether the risk is accepted and explicitly tracked as a precondition on Phase 43's subscription-grant writer.
**Expected:** A recorded decision — either a 42-07 closure plan implementing the review's suggested `ActivationOutcome` enum (or an equivalent fix), or an explicit acceptance note added to `42-CONTEXT.md`/`REQUIREMENTS.md` naming the risk and gating Phase 43 on resolving it first.
**Why human:** Severity-versus-timing tradeoff on an unreachable-today, live-in-the-next-phase defect touching an irreversible security control. This is a judgment call, not a fact a verifier can resolve.

### Gaps Summary

No gaps against the four literal ROADMAP success criteria — all four are verified with strong, largely mutation-tested and live-database evidence, matching or exceeding what the six SUMMARY files claim. One critical code-review finding (CR-01) and four related warnings (WR-01–04) describe a real, reproduced architectural defect in the shared crud-writer error handling that is not reachable through any code path shipped by this phase or any prior phase, but will become reachable as soon as Phase 43 ships a subscription-grant writer. This is escalated to human decision rather than silently passed or used to fail the phase.
