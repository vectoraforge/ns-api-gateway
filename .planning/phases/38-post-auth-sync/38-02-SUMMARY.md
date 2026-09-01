---
phase: 38-post-auth-sync
plan: 02
subsystem: api
tags: [fastapi, sqlmodel, pydantic, entitlements, auth, fail-closed]

# Dependency graph
requires:
  - phase: 38-01
    provides: "`SyncService.read_entitlement`'s happy path, the `_StubSession` harness, `STALE_PERIOD`, and the `allowance=None` stub arm"
  - phase: 36-rebind-routes
    provides: "`MissingUsageRowError`, `MultipleEffectiveGrantsError` and `UnknownTierError`, reused unchanged"
provides:
  - "the zero-grant answer — `type=none, status=none`, both nullable fields null, `monthly_used=0`, a non-null `current_period`"
  - "the stale-period rule computed as a value and never as an assignment, so a read cannot persist a rollover"
  - "the three fail-closed tripwires, raised where `QuotaService.charge` raises them, with no new error class"
  - "a complete `SyncService.read_entitlement` — every branch reachable and covered"
affects: [38-03, 38-06, 39-users-me]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 2874
  tasks: 3
  commits: 6

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mirror-test class: the same seeded fixture as an existing class, with the opposite assertions"
    - "Fault injection as an acceptance criterion — the guard is run against the bug it exists to catch"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/services/sync.py
    - tests/unit/test_sync_resolver.py

key-decisions:
  - "The stale-period comparison is written `0 if usage.monthly_period != period else usage.monthly_used` rather than the more natural `== period` form, because the plan's mandated source grep for `\\.monthly_period =` matches the substring inside `.monthly_period ==` and would have reported a comparison as an assignment"
  - "The fault injection proved the row-untouched guard, not the value assertion, is what catches a persisted rollover: with quota's assignment reintroduced the reported value stayed 0 and only `test_a_stale_row_is_left_exactly_as_it_was_found` failed"
  - "SYNC-01 and SYNC-02 are left unchecked in REQUIREMENTS.md, following 38-01's recorded precedent: 38-03 still claims both and 38-06 claims SYNC-02, so marking either complete here would be false"
  - "No e2e case was added for the five branches — the plan scoped them to unit level, and 38-03 owns the real-PostgreSQL proof"

patterns-established:
  - "Mirror test: where one service mutates and another must not, the read-only service's test class reuses the mutating class's fixture verbatim and inverts its assertions, so the pair reads as one decision"
  - "A read-only branch that shadows a writing one is proved by fault injection, not by inspection: reintroduce the write, watch exactly the guard fail, revert"

requirements-completed: []

coverage:
  - id: D1
    description: "A caller with zero effective grants receives the six no-grant defaults with a non-null `current_period`, issuing one statement, writing nothing and logging nothing"
    requirement: SYNC-01
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestTheZeroGrantAnswer"
        status: pass
    human_judgment: false
  - id: D2
    description: "A usage row naming an earlier period reports `monthly_used=0` for the current period while `monthly_period` and `monthly_used` stay byte-identical and the session is never committed"
    requirement: SYNC-02
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestTheRolloverIsComputedNeverWritten"
        status: pass
      - kind: other
        ref: "fault injection: quota's two assignment lines reintroduced, exactly test_a_stale_row_is_left_exactly_as_it_was_found failed, then reverted"
        status: pass
    human_judgment: false
  - id: D3
    description: "An effective grant whose usage row is missing raises `MissingUsageRowError` rather than reporting `monthly_used=0`"
    requirement: SYNC-01
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestTheUsageRowIsMissing"
        status: pass
    human_judgment: false
  - id: D4
    description: "Two effective grants raise `MultipleEffectiveGrantsError` and a grant whose tier has no row raises `UnknownTierError`, both reusing the existing classes, both answering 500 `internal_error`"
    requirement: SYNC-01
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestMultipleEffectiveGrants"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestTheTierHasNoRow"
        status: pass
    human_judgment: false
  - id: D5
    description: "The three fail-closed branches raise from the service, matching where `QuotaService` raises them, and no new error class is added to `errors.py`"
    requirement: SYNC-01
    verification:
      - kind: other
        ref: "git diff --stat src/nativespeaker/api/errors.py — empty"
        status: pass
    human_judgment: false
  - id: D6
    description: "The five branches behave identically against real PostgreSQL through the HTTP surface, not only against the stub session"
    verification: []
    human_judgment: true
    rationale: "Every case here is a unit test over `_StubSession`. The plan scoped it that way and 38-03 owns the real-database proof, so this plan's green suite must not be read as end-to-end evidence for the five branches."

# Metrics
duration: 12min
completed: 2026-09-01
status: complete
---

# Phase 38 Plan 02: The Branches Around the Tracer Summary

**`SyncService.read_entitlement` is complete: the zero-grant caller is answered rather than crashed, a stale usage row reports zero without the row being written, and the three broken-data conditions fail closed on the same classes `QuotaService.charge` uses.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-09-01T08:08Z
- **Completed:** 2026-09-01T08:20Z
- **Tasks:** 3
- **Files modified:** 2 (0 created, 2 modified)

## 38-01's Five Stubs: All Five Closed, None Remaining

This is the plan's reason to exist, so it is stated first and explicitly.

| # | 38-01 stub | Status | Closed by | Proven by |
|---|---|---|---|---|
| 1 | `grants[0]` with no bounds check — zero grants raised `IndexError` → 500 | **CLOSED** | Task 1 (`0fad6d4`) | `TestTheZeroGrantAnswer` (4 cases) |
| 2 | Two effective grants silently reported the first | **CLOSED** | Task 3 (`4b5ee49`) | `TestMultipleEffectiveGrants` (3 cases) |
| 3 | `usage.monthly_used` with no `None` check — `AttributeError` → 500 | **CLOSED** | Task 3 (`4b5ee49`) | `TestTheUsageRowIsMissing` (3 cases) |
| 4 | `monthly_credits` of `None` reported as `monthly_credits: null` | **CLOSED** | Task 3 (`4b5ee49`) | `TestTheTierHasNoRow` (3 cases) |
| 5 | A stale `monthly_period` reported last month's `monthly_used` | **CLOSED** | Task 2 (`f1c00af`) | `TestTheRolloverIsComputedNeverWritten` (4 cases) |

**No stub remains in `services/sync.py`.** Every branch of `read_entitlement` is now reachable and covered. `STALE_PERIOD`, which 38-01 left unused in the harness, is now used by two cases.

The one thing the endpoint still cannot claim is in the coverage block as **D6**: all seventeen new cases run against `_StubSession`, not real PostgreSQL. 38-03 owns that.

## Accomplishments

- **The zero-grant caller is answered, not refused.** The empty-result branch sits exactly where `QuotaService.charge` puts its own `if not grants:` test, and returns the `none` members of both public enums with both nullable fields null. Where quota raises exhaustion, sync reports the no-grant defaults — the ordinary answer for someone who never claimed a grant.
- **The period is derived once, above the branch**, so the zero-grant and granted answers cannot drift to different instants. A test asserts `current_period == EVALUATED_AT.strftime("%Y-%m")`, not merely that `type` is `none`.
- **The rollover is a value, never a state change.** `used = 0 if usage.monthly_period != period else usage.monthly_used` produces what quota produces by assigning. Because `get_db` commits on exit, quota's two assignment lines here would have silently persisted a rollover from a strictly read-only endpoint.
- **The read-only guarantee is proved against the bug, not asserted.** Reintroducing quota's assignment failed exactly one case; reverting restored green. The detail that matters is *which* case failed — see Issues below.
- **All three tripwires reuse the existing classes unchanged.** `errors.py` is untouched, `quota.py` is untouched, `migrations/` is untouched. Each tripwire test asserts the carried attributes (the grant id, the tier id, the count and user id) and the `(500, "internal_error")` pair, so no branch is distinguishable from another on the wire.
- **No log line was added anywhere.** All three classes already declare `log_level = ERROR`, so the shared handler emits one line per occurrence; a second would be the duplication D-02 rejects.

## Task Commits

Each task ran RED then GREEN and was committed at both gates:

1. **Task 1: The zero-grant answer** — `ce73f66` (test, RED) → `0fad6d4` (feat, GREEN)
2. **Task 2: The stale period is computed, never written** — `40c4d41` (test, RED) → `f1c00af` (feat, GREEN)
3. **Task 3: The three fail-closed tripwires** — `49bd1e7` (test, RED) → `4b5ee49` (feat, GREEN)

## Files Created/Modified

- `src/nativespeaker/api/services/sync.py` — the zero-grant branch, the three tripwire raises, and the computed-not-assigned rollover; +34 lines, no import of `structlog`, no assignment to any loaded row
- `tests/unit/test_sync_resolver.py` — five new classes, 17 new cases (12 → 29); `_read()` extracted so a case can assert the reported entitlement rather than only the recorded statements

## Decisions Made

**The stale-period comparison is written with `!=` rather than `==`.** Task 2's acceptance criterion requires `grep -cE '...\.monthly_period =...'` over the source to output `0`. The natural form, `usage.monthly_used if usage.monthly_period == period else 0`, makes that grep output `1` — the pattern `\.monthly_period =` matches the first two characters of `==`. The criterion is a mechanical gate against *assignment*, and a comparison tripping it would either force the gate to be weakened or leave a permanent false positive for every later reader. Inverting to `0 if usage.monthly_period != period else usage.monthly_used` keeps the gate exact and reads at least as well: the stale case, which is the one this phase diverges over, now comes first. No behaviour differs.

**REQUIREMENTS.md is left unmodified.** SYNC-01 is claimed by 38-01, 38-02 and 38-03; SYNC-02 by 38-01, 38-02, 38-03 and 38-06. 38-03 proves the no-lock and no-mutation claims under concurrency against real PostgreSQL, which is the half of SYNC-02 this plan does not touch, and D6 above records that this plan's evidence is unit-level. Checking either box now would assert more than was proved. This follows the precedent 38-01 recorded for itself and 36-01/REBIND-05.

**No e2e case was added.** The plan's `<verify>` for all three tasks is the unit file, and its `files_modified` names only the two files touched. Adding e2e coverage for the five branches would have been scope this plan was not given and would have overlapped 38-03.

## Deviations from Plan

**None affecting behaviour.** The three tasks were executed as written, in order, with the TDD gates observed at each.

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Copied the gitignored `.env` into the worktree**

- **Found during:** environment setup, before Task 1
- **Issue:** `.env` is gitignored, so this fresh worktree had none. `pytest-dotenv` loads it and the default suite (`uv run pytest -q`, Task 3's verify) collects the e2e modules even while deselecting them.
- **Fix:** copied `/home/init/native-speaker/ns-api-gateway/.env` into the worktree root — the same fix 38-01 recorded.
- **Files modified:** none tracked; the file stays gitignored and is in no commit.

### Notes on the plan's own text

**The `.monthly_period =` grep is imprecise as written** and is the reason the comparison is inverted. It is recorded here rather than silently worked around, because the same criterion appears in 38-02's `must_haves` and any later plan copying it will hit the same false positive. The gate is still worth keeping — it caught nothing real here only because nothing real was wrong.

---

**Total deviations:** 1 auto-fixed (1 blocking, environment only), 0 behavioural
**Impact on plan:** none — no scope added, no task altered.

## Issues Encountered

**The fault injection found something worth recording.** Task 2's criterion asks for quota's assignment to be reintroduced and the stale-period test observed failing. It was, and the result was sharper than expected:

```
FAILED tests/unit/test_sync_resolver.py::TestTheRolloverIsComputedNeverWritten::test_a_stale_row_is_left_exactly_as_it_was_found
=================== 1 failed, 19 passed, 1 warning in 0.12s ====================
```

Exactly one case failed — and it was **not** `test_a_stale_period_reports_zero_for_the_current_period`. With quota's assignment in place the *reported value is still 0*, because assigning zero to the row and then reading it back yields the same answer as selecting zero. The value assertion cannot see this bug at all. Only the guard holding a reference to the seeded object and checking `(usage.monthly_period, usage.monthly_used) == (STALE_PERIOD, 17)` catches it.

That is the whole case for the mirror-test pattern: a test suite that only asserted the response body of `/auth/sync` would have passed while the endpoint silently wrote a rollover on every read. Anyone later tempted to drop the row-untouched assertions as redundant should read this paragraph first.

**A note on RED honesty for Task 2.** Only 1 of the 4 new cases failed at RED; the three row-untouched guards passed immediately, because 38-01 had left no assignment to remove. They are regression guards, not behaviour drivers, and this was not taken as a green light — the fault injection above is exactly what establishes they are not vacuous.

**A note on `actuals.tokens`.** Recorded as 2874, chars/4 over the realized diff (11,494 characters across the two files). The plan estimated 55,000 at `confidence: low` — a gap of roughly 19×, in the same direction and of the same order as 38-01's 12×. Two data points now agree that this phase's estimates are not measuring diff size. Not rounded toward the estimate.

## Known Stubs

**None.** All five stubs 38-01 recorded are closed, as tabulated above. No new stub, `TODO`, `FIXME` or skipped test was introduced. Every `<verify>` in the plan was run; none was deferred.

`.planning/WINDOWS.md` needed no new entry — this plan opened no defect. It carried no phase-38 entries before this plan and carries none after.

## Threat Flags

None. Every file touched stays inside the threat surface the plan's `<threat_model>` enumerates, and all three `mitigate` dispositions were implemented and asserted:

- **T-38-05** (information disclosure across the tripwires) — each of the three test classes asserts `(500, "internal_error")`, so no branch is distinguishable on the wire.
- **T-38-06** (tampering via `get_db`'s commit-on-exit) — the source grep for the three assigned attribute names, `session.add`, `commit(` and `rollback(` outputs `0`, and the fault injection proves the test catches a reintroduced assignment.
- **T-38-08** (reporting an allowance quota would refuse) — the missing-usage-row and missing-tier-row cases raise instead of reporting zero, asserted per branch.

**T-38-07** (the zero-grant path emitting no record) was dispositioned `accept` and is implemented as accepted: the branch writes no log line, per D-02.

The plan's prohibition — never report an entitlement rosier than what quota would act on at the same instant — holds by construction: on every path where quota refuses, sync now either reports `none` or raises the same class quota raises.

## Verification

| Check | Result |
|---|---|
| `uv run pytest tests/unit/test_sync_resolver.py -v` | 29 passed (12 before this plan, 17 added) |
| `uv run pytest -q` | 755 passed, 295 deselected (baseline after 38-01: 738) |
| `uv run pytest -q -m 'e2e or schema'` | 295 passed — both suites the default `addopts` silently skips |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/test_docstring_bar.py` | 9 passed — the baseline of 0 holds on every root |
| `uv run pytest tests/unit/test_quota_resolver.py` | passed, unmodified |
| `git diff --stat src/nativespeaker/api/errors.py` | empty — no error class added, edited or subclassed |
| `git diff --stat src/nativespeaker/api/services/quota.py` | empty |
| `git diff --stat tests/unit/test_quota_resolver.py` | empty |
| `git diff --stat migrations/` | empty |

Grep-form acceptance criteria, all as specified:

| Grep over `services/sync.py` | Required | Actual |
|---|---|---|
| `logger\|structlog` (Tasks 1 and 3) | 0 | **0** |
| `\.monthly_used =\|\.monthly_period =\|\.updated_at =\|session\.add\|commit(\|rollback(` (Task 2) | 0 | **0** |

Node-id counts against the plan's minimums: zero-grant 4 (≥4), stale-period and current-period 4 (≥4), tripwires 9 (≥6).

## User Setup Required

None. Note for a fresh worktree: `.env` is gitignored and must be copied in before the suite can be collected.

## Next Phase Readiness

**Ready.** `/auth/sync` is now behaviourally complete: it answers correctly for a caller with no grant and for one with a well-formed grant, reports a stale period as zero without touching the row, and fails closed with an indistinguishable 500 on each of the three broken-data conditions. The blocker 38-01 flagged — "38-02 is not optional" — is cleared.

**Ready for the plans that build on it:**
- **38-03** proves the no-lock and no-mutation claims under concurrency against real PostgreSQL. It inherits D6: the five branches are proved at unit level only, and the read-only guarantee in particular deserves its real-database counterpart, since the failure mode is a commit that only a real session performs.
- **38-06** owns the REQUIREMENTS/ROADMAP amendments and the `SHARED-INVARIANTS.md` edit, and will be the plan able to check SYNC-01 and SYNC-02.
- **39 (`GET /users/me`)** must report consistently with `SyncResponse`; the fail-closed rule established here (D-07) applies to it identically, since it reads the same rows.

**Blockers/concerns:**
- SYNC-01 and SYNC-02 remain unchecked in `REQUIREMENTS.md` by design. Anyone auditing phase 38 for completeness should read the coverage block and this section rather than the checkboxes.
- The `.monthly_period =` acceptance grep is imprecise and will produce a false positive for any future plan that writes the comparison in the `==` form. Worth correcting in the source of that criterion rather than re-deriving the workaround.

## Self-Check: PASSED

Both modified files exist on disk and all six task commits are present on `worktree-agent-a9fcd02cfabf8eab7`: `ce73f66`, `0fad6d4`, `40c4d41`, `f1c00af`, `49bd1e7`, `4b5ee49`.

---
*Phase: 38-post-auth-sync*
*Completed: 2026-09-01*
</content>
</invoke>
