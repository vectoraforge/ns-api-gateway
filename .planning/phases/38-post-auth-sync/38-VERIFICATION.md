---
phase: 38-post-auth-sync
verified: 2026-09-01T00:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 1
overrides_applied: 0
human_verification:

  - test: "Run two genuinely concurrent requests against a committed (non-transactional) test database — one POST /auth/sync and one concurrent QuotaService.charge or grant-flip on the same user/grant, using two real, independent connections (not the e2e harness's single-connection uncommitted-transaction fixture)."
    expected: "Sync's statements (no FOR UPDATE) neither block on nor are blocked by the concurrent charge's locks, and sync's response and the post-charge table state are each internally consistent (no partial read straddling the charge's commit in a way that produces an impossible tier/usage pairing worse than the already-accepted READ COMMITTED skew noted in 38-REVIEW.md WR-06)."
    why_human: "This is a state/ordering invariant (no-lock behavior under real concurrency) that grep/static analysis and the existing e2e harness cannot exercise — `tests/e2e/conftest.py`'s `_db_transaction` binds every session to one connection inside an uncommitted transaction, so a second connection cannot see the seeded rows. This is already tracked as WINDOWS.md entry 9 (open, unwaived) and 38-06's own coverage block (D10, human_judgment: true). Reported here as directed, not as a new finding."
---

# Phase 38: POST /auth/sync Verification Report

**Phase Goal:** Ship the read-only auth-state reconciliation surface clients call after sign-in or a lost response.
**Verified:** 2026-09-01
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Grant, `current_period`, and `monthly_used` all derive from one evaluation time and match what quota enforcement would independently act on at the same instant | ✓ VERIFIED | `app/dependencies.py::get_sync_service` captures `evaluated_at=datetime.now(UTC)` exactly once; `services/sync.py` contains no clock read. The predicate-equality proof (`tests/unit/test_sync_resolver.py::TestThePredicateIsOneDefinition`, 2 cases) shows the locking (quota) and non-locking (sync) reads compile to identical PostgreSQL text apart from the trailing `FOR UPDATE` — the strongest available form of "matches what quota would act on," one definition used twice, not two implementations kept in sync by hand. Ran locally: `uv run pytest tests/unit/test_sync_resolver.py -q` → 29 passed. |
| 2 | Zero effective grants and a lapsed grant return byte-identical responses | ✓ VERIFIED | `tests/e2e/test_sync.py::TestTwoAbsentEntitlementsAreIndistinguishable::test_no_grant_and_a_lapsed_grant_return_the_same_body` compares the two parsed bodies to each other (not each against a literal), plus a present-control case proving the lapsed grant really is seeded/visible/excluded. Ran locally against real PostgreSQL: `uv run pytest -m e2e tests/e2e/test_sync.py -v` → 14 passed. |
| 3 | Table state is unchanged across a request — verified by comparing `core.*` before and after | ✓ VERIFIED | `tests/e2e/test_sync.py::TestTheRequestChangesNothing` (4 cases) does raw `SELECT *` snapshots (not ORM `model_dump()`, which would miss `core.access_grants`'s 4 `GENERATED ALWAYS` columns) of `core.access_grants`, `core.user_monthly_usage`, `core.users` plus three whole-table counts, across 3 seeded states including the stale-period branch where quota itself would write. 38-03's own recorded fault injection (quota's rollover assignment reintroduced into `services/sync.py`) failed exactly the two stale-period cases and left the response-body assertion passing — confirming the snapshot, not the body check, is what catches this class of bug. Independently confirmed passing in this run. |
| 4 | No durable audit row is written on any path and no per-attempt telemetry is added beyond what already exists — one `request` line per attempt from the request middleware and one WARNING per rejection from the shared error handler — with the decision to drop the durable-row obligation recorded in `REQUIREMENTS.md` under SYNC-03 and the matching removal made in `SHARED-INVARIANTS.md` | ✓ VERIFIED | See "Criterion 4 — the two-repository check" below. |

**Score:** 4/4 ROADMAP success criteria verified. One additional, narrower must-have from plan 38-01/38-06 (the no-lock claim under *genuine* concurrency) is present and structurally supported but not behaviorally exercised — see Human Verification.

### Criterion 4 — the two-repository check (verified independently, not from SUMMARY claims)

**`REQUIREMENTS.md` half (this repo, committed).** `.planning/REQUIREMENTS.md:198-200` — SYNC-01, SYNC-02, SYNC-03 all `- [x]`. SYNC-03's text now reads as attempt telemetry ("one `request` line... one WARNING per rejection... writes no durable row"), with a dated amendment blockquote naming option (b), 2026-09-01. The `Amended again by Phase 38` blockquote (`:32`) and FOUND-05's "RESOLVED BY REMOVAL" paragraph (`:120-124`) are both present and read as expected. Flagged-conflicts count reads **Five** in the treatment table (`:489`) and in the header blockquote (`:34`), consistent with FOUND-05's conflict being retired.

**`SHARED-INVARIANTS.md` half (parent tree, deliberately uncommitted/untracked).** Read directly from disk at `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md`: `grep -ic audit` over the file → **0** — no "Audit" heading, no `auth_events`, no `actor_subject_hash`, no `auth_event_result`. The two live non-audit rules ("a rejection leaves exactly one structured security-log line," "admission-phase rejections... write NO per-rejection database row") are present under `## Fail-closed defaults` (lines 30-31 of the current file). `git -C /home/init/native-speaker status` shows `specs/auth-refactor-phases/` as `??` (untracked) — confirmed this is the plan's explicit `<repository_boundary>` instruction (38-04-PLAN.md), not an oversight, and it was **not** committed by this verification per instructions.

**Code-level confirmation of "no durable row, no new telemetry":** `tests/unit/test_sync_audit_removal.py` (6 guards, all fault-injected per its own summary) asserts: `tests/schema/test_inventory.py::EXPECTED_AUDIT_TABLES == {"subscription_events"}`; no migration SQL file mentions `auth_events`/`auth_event_result`; exactly one migration file exists; `services/sync.py` imports no logging library and makes no logging call; no `auth_sync`/`auth_events` string constant exists anywhere under `src/`; and a positive control proves the source walk is non-vacuous. Independently confirmed on disk: `migrations/20260818_01_initial-release.sql` contains `audit.subscription_events` only (no `auth_events` table), and `ls migrations/` shows exactly one file. Ran locally: `uv run pytest tests/unit/test_sync_audit_removal.py -v` → 6 passed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/services/sync.py` | `SyncService`, read-only entitlement aggregate | ✓ VERIFIED | Exists, substantive (58 lines, 5 branches: happy path, zero-grant, multiple-grant tripwire, missing-usage tripwire, unknown-tier tripwire), imports no logging, assigns no attribute on a loaded row. Wired: imported by `app/dependencies.py::get_sync_service` and `services/__init__.py`. |
| `src/nativespeaker/api/schemas/auth.py` (additions) | `EntitlementType`, `EntitlementStatus`, `Entitlement`, `SyncResponse` | ✓ VERIFIED | All four types present, wired into `routers/auth.py`'s `sync` handler and `SyncService.read_entitlement`'s return type. |
| `src/nativespeaker/api/crud/grants.py` (additions) | `read_effective_grants`, `read_usage` non-locking siblings | ✓ VERIFIED | Both present; unit test proves compiled-SQL equality against the locking pair apart from `FOR UPDATE`. |
| `POST /auth/sync` route | `routers/auth.py` | ✓ VERIFIED | Registered, narrowed with `Depends(get_linked_identity)`, not in `PUBLIC_PATHS` or `PREAUTH_CALLABLE_PATHS` (`tests/unit/test_app_wiring.py`, 2 new node ids passing). |
| `tests/e2e/test_sync.py` | End-to-end proof, real PostgreSQL | ✓ VERIFIED | 14 node ids, all passing against a live PostgreSQL instance in this environment. |
| `tests/unit/test_sync_resolver.py` | Compiled-SQL proof, no-lock proof | ✓ VERIFIED | 29 node ids, all passing. |
| `tests/unit/test_sync_audit_removal.py` | Executable removal guards | ✓ VERIFIED | 6 node ids, all passing, each independently fault-injection-proven per the SUMMARY (spot-checked one: `EXPECTED_AUDIT_TABLES` is genuinely `{"subscription_events"}` on disk). |
| `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` | § Audit removed | ✓ VERIFIED | Content confirmed on disk (0 audit matches); uncommitted status confirmed intentional per plan's repository boundary. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `routers/auth.py::sync` | `services/sync.py::SyncService.read_entitlement` | `Depends(get_sync_service)`, one `await` call | ✓ WIRED | Confirmed by reading `routers/auth.py:82-86`. |
| `services/sync.py` | `crud/grants.py::GrantsDB` | `read_effective_grants` / `read_usage` / `monthly_credits` | ✓ WIRED | Confirmed. |
| `app/dependencies.py::get_sync_service` | `services/sync.py::SyncService` | constructs with `evaluated_at=datetime.now(UTC)` | ✓ WIRED | Confirmed; single capture point. |
| `.planning/REQUIREMENTS.md` SYNC-03 | `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` | FOUND-05 conflict resolved by the removal plan 38-04 performed | ✓ WIRED | Confirmed both sides independently; text and removal match. |

### Behavioral Spot-Checks / Test Runs (executed by this verifier, not taken from SUMMARY.md)

| Check | Command | Result | Status |
|---|---|---|---|
| Sync unit suite | `uv run pytest tests/unit/test_sync_audit_removal.py tests/unit/test_sync_resolver.py -q` | 35 passed | ✓ PASS |
| Sync e2e suite (real PostgreSQL) | `uv run pytest -m e2e tests/e2e/test_sync.py -v` | 14 passed | ✓ PASS |
| Default suite (regression) | `uv run pytest -q` | 761 passed, 308 deselected | ✓ PASS (matches 38-06-SUMMARY.md's claimed 761) |
| Linter | `uv run ruff check src tests` | All checks passed | ✓ PASS |
| Audit-table inventory on disk | `grep -in audit migrations/20260818_01_initial-release.sql` | Only `audit` schema / `audit.subscription_events` | ✓ PASS |
| SHARED-INVARIANTS.md audit vocabulary | `grep -ic audit SHARED-INVARIANTS.md` | 0 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| SYNC-01 | 38-01, 38-02, 38-03, 38-06 | Returns effective grant, `current_period`, `monthly_used`, stored `identity_provider`, one captured evaluation time | ✓ SATISFIED | Checked `[x]` in REQUIREMENTS.md with clause-by-clause citations in 38-06-SUMMARY.md, each independently spot-checked above. |
| SYNC-02 | 38-01, 38-02, 38-03, 38-06 | Strictly read-only — no rollover, no grant-row flip, no invariant repair, no profile write | ✓ SATISFIED (on its written text) | Checked `[x]`. All four named clauses have unit + e2e evidence with fault injection. The broader "no-lock under genuine concurrency" framing (from 38-01's own `must_haves`, not from SYNC-02's or ROADMAP's text) is NOT part of what was checked — see "Independent judgment" below and Human Verification. |
| SYNC-03 | 38-04, 38-05, 38-06 | Attempt telemetry via existing middleware/handler only; no durable row; decision recorded in both specs | ✓ SATISFIED | Checked `[x]`. Both repository halves independently verified above. |

No orphaned requirements: REQUIREMENTS.md maps exactly SYNC-01/02/03 to Phase 38, matching the phase directive.

### Anti-Patterns Found

None blocking. `38-REVIEW.md` (0 Critical, 6 Warning, 4 Info) was read and spot-checked against the current code:

- **WR-01** (guard checks `identity.user` but route also dereferences `identity.identity`) — confirmed present in `app/dependencies.py:57-61` and `routers/auth.py:86` exactly as described. Real but currently unreachable (single construction site sets both fields together); correctly scored Warning, not Blocker.
- **WR-02** through **WR-06**, **IN-01** through **IN-04** — read, not independently re-derived line-by-line; nothing among them describes a missing artifact, broken wiring, or a failed success criterion. These are legitimate code-quality/robustness observations for a future pass, not phase-goal blockers.

No unresolved `TODO`/`FIXME`/`XXX` found in the phase's touched files (`tests/unit/test_sync_audit_removal.py` confirms no such marker via its own summary; spot-checked `services/sync.py` and `routers/auth.py` — none present).

### Independent judgment requested by the task: 38-06's SYNC-01/SYNC-02 checkbox decision

**I agree with 38-06's treatment.** Three consecutive plans (38-01, 38-02, 38-03) each declined to check SYNC-01/SYNC-02, reasoning that they individually proved only part of the requirement (happy path only; branches only; e2e proof of 2 of 3 ROADMAP criteria plus a harness limitation on concurrency). 38-06 then checked all three SYNC boxes with a clause-by-clause citation table in its SUMMARY.

For SYNC-02 specifically: I read `.planning/REQUIREMENTS.md:199`'s actual text — *"The endpoint is strictly read-only — no rollover, no grant-row flip, no invariant repair, no profile write."* This is the canonical, binding wording (REQUIREMENTS.md, not a phase brief). It names four concrete prohibitions and does **not** mention lock-freedom or behavior under concurrent access. I also checked ROADMAP.md's Phase 38 success criterion 3 — *"Table state is unchanged across a request — verified by comparing `core.*` before and after"* — which is satisfied by a single-request before/after comparison and likewise does not require a live-concurrency demonstration. The "sync neither blocks nor is blocked... running beside a concurrent quota charge" framing traces to 38-01-PLAN.md's own `must_haves.truths` (an elaboration the planner added, echoing the phase brief's richer language) and to 38-01's `<probe_coverage>` table, not to SYNC-02's or the ROADMAP's actual text.

Given that, checking SYNC-02 against its four named clauses — each backed by unit-level fault-injected proof and e2e column-level snapshots with fault injection — is checking the requirement as written, not overstating evidence. 38-06 did not hide the gap: it explicitly states "SYNC-02 is checked on its written text" and "a reader must not read the checked box as a concurrency observation," and it left `WINDOWS.md` entry 9 open and unwaived rather than closing it for a cleaner ship gate. That is the correct disposition — honest, documented, and consistent with the project's own convention (seen throughout REQUIREMENTS.md) of recording exactly what was and was not proved rather than rounding up. I would have made the same call.

### Known-open items (reported as open, not counted as failures, per task instruction)

1. **`WINDOWS.md` entry 9** (`unmet-truth`, phase 38, open, unwaived) — sync's no-lock claim under genuine concurrency is inferred from compiled SQL carrying no `FOR UPDATE`, never observed live; the e2e harness binds every session to one connection in an uncommitted transaction. Confirmed present in `.planning/WINDOWS.md` exactly as described. This is the one item routed to Human Verification above.
2. **`38-REVIEW.md`**: 0 Critical, 6 Warning, 4 Info — confirmed present, advisory, already recorded, spot-checked (WR-01) and consistent with the current code.
3. **No `38-SECURITY.md` exists.** Confirmed absent from `.planning/phases/38-post-auth-sync/`. Reported as open per task instruction; this verifier did not locate a project-level `workflow.security_enforcement` setting file to confirm whether it is currently `true`, so the significance of the absence is left to the developer's own workflow configuration rather than asserted here.

## Gaps Summary

No gaps found. All four ROADMAP success criteria are independently verified against the live codebase and a live test run (not taken from SUMMARY.md claims), REQUIREMENTS.md SYNC-01/02/03 are checked with evidence that holds up under spot-checking, and the two-repository criterion-4 check was independently confirmed on both sides. The phase routes to `human_needed` solely because of one already-known, already-flagged, non-blocking behavioral gap (live-concurrency observation) that the project itself correctly declined to paper over.

---

_Verified: 2026-09-01_
_Verifier: Claude (gsd-verifier)_
