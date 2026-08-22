---
phase: 36-rebind-pre-existing-routes
verified: 2026-08-21T00:00:00Z
status: gaps_found
score: 4/6 truths verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Every pre-existing route serves as it did in v1.6, apart from auth rejections now using the shared error classes (ROADMAP SC1 / REBIND-06)."
    status: failed
    reason: >
      Three confirmed, independent code paths charge a paying user's monthly allowance for a
      request the application itself rejected before the LLM provider was ever contacted — a
      behaviour change that is not an auth rejection and therefore falls outside SC1's stated
      exception. `consume_quota` (src/nativespeaker/api/quota.py:153) commits the increment
      unconditionally inside `require_quota`'s own session
      (src/nativespeaker/api/app/dependencies.py:117-144), which closes and commits before the
      handler body is entered — so nothing downstream of that point can roll the charge back.
      (1) `POST /chats/{nonexistent-uuid}` with a valid body: 404, `monthly_used` 0→1 (executors'
      own documented and deliberately-unresolved REBIND-06 divergence, Known Gaps 1 in
      36-05-SUMMARY.md). (2) `POST /chats {"lang":"zz"}`: 400 `invalid_request`, credit still
      spent — `ChatRequest.lang` (src/nativespeaker/api/models/api.py:18) is unvalidated free
      text and the supported-set check runs in `ChatService.create_chat`, after the charge
      (CR-02 in 36-REVIEW.md, confirmed by reading `tests/e2e/test_error_cases.py:60-71`, which
      asserts only the status code and never reads `monthly_used`). (3) A circuit-open or
      queue-full 503 (backpressure raised in `resilience.py:56` / `resilience.py:86`, both before
      any provider call): credit still spent, and the response's `Retry-After` header explicitly
      tells the client to retry — compounding the loss for the duration of the open window
      (CR-01 in 36-REVIEW.md). No e2e case in the repo asserts `monthly_used` across a 503.
    artifacts:
      - path: "src/nativespeaker/api/app/dependencies.py"
        issue: "require_quota commits its own session unconditionally before the handler runs, with no compensating decrement for pre-provider rejections other than the D-14 malformed-request case (422)."
      - path: "src/nativespeaker/api/models/api.py"
        issue: "ChatRequest.lang has no validation constraint, so the language check happens after the charge instead of at the FastAPI validation boundary."
      - path: "tests/e2e/test_error_cases.py"
        issue: "test_followup_nonexistent_chat_returns_404 and test_unsupported_language_returns_400 both seed a grant to reach their branch but never assert monthly_used afterward, so the charge is silently untested."
    missing:
      - "A resolution decision on D-11's scope (accept the burn and narrow REBIND-06's wording, or fund a compensation/pre-admission path) — the phase's own SUMMARY already frames this as unresolved and escalates it as a Rule-4 architectural decision, not a bug fix."
      - "At minimum, e2e coverage that makes the charge on 404/400/503 an asserted, intentional fact rather than a silent side effect, so a future regression fixing one arm doesn't quietly reopen another."
deferred: []
human_verification:
  - test: "Whether REBIND-02's 'increment the bounded-cardinality counter metric' on rejection covers quota rejections (429) in addition to barrier/auth rejections."
    expected: "A ruling on whether the phase's own flagged, deliberately-unresolved reading (structured log only, no counter increment, for quota 429s) satisfies REBIND-02 as marked complete in REQUIREMENTS.md, or whether a second counter is required."
    why_human: "This is a requirement-text interpretation question the phase's authors explicitly declined to resolve by fiat (36-05-SUMMARY.md, 'Flagged assumption carried forward — REBIND-02'), not a code defect — grep and test evidence cannot adjudicate it."
  - test: "Whether the credit-burn-on-app-rejection defect family (404/400/503) blocks the milestone from proceeding past Phase 36, or is accepted as a known v2.0 launch gap to fix in a follow-up phase."
    expected: "A go/no-go decision, since every mechanical fix the plan's own decisions considered (refund, reserve-then-settle, moving consumption after the ownership check) is explicitly ruled out by D-04/D-11 as currently scoped."
    why_human: "Rule-4 architectural decision, already escalated by the executors themselves and independently corroborated by the code review (CR-01, CR-02)."
---

# Phase 36: Rebind Pre-existing Routes Verification Report

**Phase Goal:** Put the eight pre-existing routes behind the barrier and rewire the chat quota path onto the grant model, restoring a running application — "Phase 36 is the first fully working application."
**Verified:** 2026-08-21
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /health/ready` is reachable unauthenticated; `GET /`, `GET /examples`, and all five `/chats` routes reject an unauthenticated caller (SC2 / REBIND-01). | ✓ VERIFIED | `src/nativespeaker/api/auth/registry.py:69-84` declares exactly the 8-route partition (1 public, 7 authenticated). `tests/unit/test_route_registry.py -k quota_checked` (7 passed) proves condition 10 fails boot on wrapper/flag disagreement in either direction. `tests/e2e/test_audit_writer.py::TestOffPathRequestsWriteNothing` (10 passed, run directly) drives all 7 authenticated routes unauthenticated → 401. |
| 2 | No `audit.auth_events` row is written by any of the eight routes at any outcome, including on rejection (SC3 / REBIND-02). | ✓ VERIFIED | `TestOffPathRequestsWriteNothing` and `tests/e2e/test_quota.py::TestAQuotaRejectionWritesNoAuditRow` (both re-run, pass) assert `row_count == 0` across 401, 200, and 429 outcomes on all 8 routes. The counter-increment half of REBIND-02's text is not proven for quota 429s specifically — see Human Verification. |
| 3 | The quota flow resolves one effective grant, locks grant-then-usage ascending by id, fails closed on a missing usage row, performs lazy rollover in the same transaction, and never lets `remaining` go negative (REBIND-05). | ✓ VERIFIED | `src/nativespeaker/api/quota.py:54-154` and `src/nativespeaker/api/database/grants.py:29-56` read exactly as described (max-floor at :142, rollover before comparison at :119-125, `MissingUsageRowError` fail-closed at :100-110, no lazy mint). `tests/schema/test_grant_locks.py` (4 passed, re-run) proves the lock order under two live PostgreSQL connections — reverse order deadlocks, fixed order serialises. `tests/e2e/test_quota.py -k missing_usage` (2 passed, re-run) confirms the fail-closed 500 with no row minted. |
| 4 | The application starts and every pre-existing route serves as it did in v1.6, apart from auth rejections now using the shared error classes (SC1 / REBIND-06). | ✗ FAILED | See Gaps. Confirmed by direct code reading: `require_quota` (dependencies.py:117-144) commits unconditionally before the handler runs; `ChatRequest.lang` (models/api.py:18) is unvalidated so the 400 fires after the charge; `CircuitBreaker.before_call`/`LLMExecutionGate._inflight_slot` (resilience.py:56,86) raise 503 after the charge too. None of the three is an auth rejection. |
| 5 | Auth rejections on the eight routes surface through the shared error taxonomy while existing non-auth business error contracts are unchanged (REBIND-03). | ✓ VERIFIED (partial, by design) | `tests/unit/test_error_contract.py` (8 passed, re-run) proves the auth-rejection half is untouched by this phase's changes. The "business contracts unchanged" half is explicitly left an unresolved, flagged reading in the phase's own plans (36-02-PLAN.md "Flagged assumption — REBIND-03") because D-12's field-default change is a knowing narrow exception; REQUIREMENTS.md correctly leaves REBIND-03 unchecked rather than claiming full satisfaction. Not counted as a gap — the phase's own artifact already reflects this honestly. |
| 6 | A missing usage row fails a quota-checked chat request closed rather than minting one — the `quota_checked_request` admission entry is void per D-05 (SC4). | ✓ VERIFIED | Same evidence as truth 3: `MissingUsageRowError` raised, no `core.user_monthly_usage` row created on that path (grep-asserted by the phase's own SUMMARY and confirmed by reading `quota.py:100-110`). |

**Score:** 4/6 truths verified (REBIND-03 counted as satisfied on its own explicitly-scoped reading; the credit-burn-on-rejection truth is the one BLOCKER)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/models/grants.py` | SQLModel layer for the three grant tables | ✓ VERIFIED | Exists, re-exported via `models/__init__.py`, used by `database/grants.py` and `quota.py`. |
| `src/nativespeaker/api/database/grants.py` | `GrantsDB` — shared lock order | ✓ VERIFIED | `lock_effective_grants`, `lock_usage`, `monthly_credits` present, correct predicate incl. `user_id` scoping (grants.py:38). |
| `src/nativespeaker/api/quota.py` | `consume_quota` — the §8.4 resolver | ✓ VERIFIED | Full resolver present, matches the docstring's own claims on reading. |
| `src/nativespeaker/api/app/dependencies.py` | `require_quota`, `require_quota_create_chat`, `require_quota_send_message` | ✓ VERIFIED (wired), ✗ but see Gaps for its commit-boundary consequence | Both wrappers present, both routes wired. |
| `src/nativespeaker/api/auth/registry.py` | 8-route partition, condition 10 | ✓ VERIFIED | Confirmed above. |
| `tests/schema/test_grant_locks.py` | Two-connection lock-order proof | ✓ VERIFIED | Re-run, 4 passed. |
| `tests/e2e/test_quota.py`, `tests/e2e/conftest.py::seed_grant` | Quota e2e coverage + test-only grant seeder | ✓ VERIFIED | Present; `seed_grant` confirmed unreachable from any route (grant creation is `src/`-absent by grep, per SUMMARY, spot-checked no `INSERT` into `access_grants` outside `tests/`). |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `app.state.session_factory` | `require_quota`'s own session | Own-session commit, no `Depends(get_db)` | ✓ WIRED | `dependencies.py:133` — confirmed by reading, matches D-04. |
| registry `quota_checked=True` | decorator `Depends(require_quota_*)` | Condition 10 cross-check | ✓ WIRED | Confirmed by test run (`test_route_registry.py -k quota_checked`, 7 passed) and by reading `registry.py:205-231`. |
| `GrantsDB.lock_effective_grants` | `GrantsDB.lock_usage` | Fixed lock order | ✓ WIRED | Confirmed by `test_grant_locks.py` re-run (deadlock on reverse order, serialisation on fixed order). |
| `require_quota`'s commit | the handler body / provider dispatch | **Absence** of any compensating link on non-422 pre-provider rejections | ✗ NOT_WIRED (by design, and the defect) | This is the root cause of the FAILED truth above: nothing connects a post-charge, pre-provider rejection (404/400/503) back to the charge to reverse it. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| REBIND-01 | 36-03, 36-05 | Route partition + enumeration assertion | ✓ SATISFIED | See truth 1. Marked `[x]` in REQUIREMENTS.md — justified. |
| REBIND-02 | 36-05 | No audit row on these routes; counter increments on rejection | ✓ SATISFIED (no-row half unambiguous; counter half rests on a flagged, undecided reading — see Human Verification) | Marked `[x]` in REQUIREMENTS.md — justified, but the flagged assumption should be surfaced to a human rather than silently closed. |
| REBIND-03 | 36-02 | Shared error taxonomy for auth rejections; business contracts unchanged | ? NEEDS HUMAN (auth half satisfied; business-contract half explicitly unresolved) | Correctly left `[ ]` in REQUIREMENTS.md. Not a gap — the artifact already reflects the true state. |
| REBIND-04 | — | Void | N/A | Correctly annotated void in both ROADMAP.md and REQUIREMENTS.md. |
| REBIND-05 | 36-01, 36-03, 36-04, 36-05 | Grant resolution, lock order, lazy rollover, non-negative remaining | ✓ SATISFIED | See truths 3 and 6. Marked `[x]` in REQUIREMENTS.md — justified. |
| REBIND-06 | 36-02, 36-03, 36-04, 36-05 | App starts, every route behaves as v1.6 except auth rejections | ✗ BLOCKED | Correctly left `[ ]` in REQUIREMENTS.md — the executors' own honest assessment. This verification independently confirms the block and additionally surfaces two more instances (CR-01, CR-02) beyond the one the executors documented. |

No orphaned requirements — REBIND-01 … REBIND-06 in REQUIREMENTS.md map 1:1 onto this phase's plans' `requirements:` fields.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/nativespeaker/api/models/api.py` | 18 | `lang: str \| None = Field(default=None)` — no validation despite a known supported-set config | 🛑 Blocker | Root cause of CR-02: the 400 for an unsupported language fires after the credit is already spent. |
| `tests/e2e/test_error_cases.py` | 60-71 | Test seeds a grant to reach the 400 branch but never reads `monthly_used` | ⚠️ Warning | The charge this phase's own D-14 prohibition forbids is exercised by the suite and silently passes. |
| `tests/e2e/test_quota.py` | — | No case exists for a circuit-open or queue-full 503 | ⚠️ Warning | CR-01 is entirely untested; nothing in the suite would catch a regression or confirm a fix. |
| `tests/unit/test_quota_resolver.py` | 286-330 | `TestTheLockingStatements` asserts `starts_at`, `ends_at`, `FOR UPDATE`, `ORDER BY` but never `core.access_grants.user_id =` | ⚠️ Warning (WR-01) | Deleting the tenant-scoping predicate term from `grants.py:38` would pass the entire suite unnoticed — confirmed by reading the assertion list, no `user_id` string present. The production code itself is currently correct (verified: `col(AccessGrant.user_id) == user_id` is present at grants.py:38); this is a test-coverage gap, not a live defect. |

No `TBD`/`FIXME`/`XXX` markers found in the phase's modified files.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Condition 10 enforcement (both directions, determinism, empty-input no-op) | `uv run pytest tests/unit/test_route_registry.py -q -k quota_checked` | 7 passed | ✓ PASS |
| No-effective-grant → 429, seeded grant → admitted, 12 quota e2e cases | `uv run pytest tests/e2e/test_quota.py -q -k no_grant -m e2e` | 12 passed | ✓ PASS |
| Off-path routes write zero audit rows at every outcome (401/200/429) | `uv run pytest tests/e2e/test_audit_writer.py::TestOffPathRequestsWriteNothing -q -m e2e` | 10 passed | ✓ PASS |
| Two-connection grant-then-usage lock order (exclusion, release, reverse-order deadlock, fixed-order safety) | `uv run pytest tests/schema/test_grant_locks.py -q -m schema` | 4 passed | ✓ PASS |
| Fail-closed 500 on a missing usage row, no row minted | `uv run pytest tests/e2e/test_quota.py -q -k missing_usage -m e2e` | 2 passed | ✓ PASS |
| Shared auth error taxonomy unaffected by D-12's response-shape change | `uv run pytest tests/unit/test_error_contract.py -q` | 8 passed | ✓ PASS |
| Lint / type gates | `uv run ruff check src tests` / `uv run ty check src` | clean / clean | ✓ PASS |
| Full suite (relied on known-state claim, not independently re-run in full to respect the single-full-run rule) | `uv run pytest -q -m ""` | 1258 passed (per known_state and 36-05-SUMMARY.md verification table) | ✓ PASS (accepted) |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention or explicit probe declarations found in this phase's PLAN/SUMMARY files. Step 7c: SKIPPED — no runnable probe scripts declared.

### Human Verification Required

### 1. REBIND-02's counter-increment scope for quota rejections

**Test:** Read `36-05-SUMMARY.md`'s "Flagged assumption carried forward — REBIND-02" section and decide whether a quota 429 on `POST /chats` or `POST /chats/{chat_id}` must also increment a bounded-cardinality counter, or whether the current structured-log-only treatment satisfies the requirement text.
**Expected:** A ruling recorded either as an accepted reading (no code change) or as a follow-up task to add a second counter.
**Why human:** Requirement-text interpretation the phase's own authors declined to resolve unilaterally; not decidable from code or tests alone.

### 2. Scope decision on the credit-burn-on-app-rejection defect family

**Test:** Review the three confirmed instances (404 on nonexistent/foreign chat, 400 on unsupported language, 503 on circuit-open/queue-full backpressure) where `monthly_used` increments for a request the application rejected before contacting the LLM provider.
**Expected:** A decision: (a) accept the burn for v2.0 and narrow REBIND-06's text to say so explicitly, (b) fund a fix in a follow-up phase before shipping, or (c) block this phase from being considered complete until at least the 400/503 arms (which are new findings, not previously known) are fixed or explicitly accepted.
**Why human:** Rule-4 architectural decision. Every mechanical fix inside this phase's existing decisions (D-04, D-11) is explicitly foreclosed by those same decisions; resolving it requires revisiting D-11's scope, which is a product/architecture call, not an implementation task.

### Gaps Summary

The phase's structural claims — route partition, audit-path exclusion, the grant/usage lock order, lazy rollover, fail-closed behavior on broken state — are all real, wired, and independently confirmed by re-running the phase's own tests plus direct code reading. REBIND-01, REBIND-02, and REBIND-05 are justifiably marked complete.

The phase goal itself — "Phase 36 is the first fully working application" / "every pre-existing route serves as it did in v1.6, apart from auth rejections" — is not yet true. `require_quota`'s architecture (an own-session commit that closes before the handler runs, adopted deliberately under D-04 to avoid holding grant locks across the LLM round trip) has no compensating mechanism for any pre-provider rejection except the one class D-14 targets (422 on malformed input). Three separate, confirmed code paths now charge a credit for a request the service itself refused: a nonexistent/foreign chat id (404, previously known and honestly left unmarked as REBIND-06 by the executors), an unsupported language code (400, newly surfaced by code review as CR-02), and sustained backpressure (503, newly surfaced as CR-01, and arguably the most severe because it is a *sustained* window during which every request in it is charged and refused). REBIND-06 is correctly left unchecked in REQUIREMENTS.md; this verification does not change that, but it does confirm the gap is real, wired into the architecture (not a leftover TODO), and larger than the one instance previously documented — a Rule-4 decision is needed before this phase's stated goal can be considered achieved.

---

_Verified: 2026-08-21_
_Verifier: Claude (gsd-verifier)_
