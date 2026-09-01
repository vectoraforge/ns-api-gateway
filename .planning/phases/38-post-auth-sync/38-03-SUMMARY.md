---
phase: 38-post-auth-sync
plan: 03
subsystem: api
tags: [fastapi, postgres, e2e, entitlements, auth, read-only]

# Dependency graph
requires:
  - phase: 38-01
    provides: "`tests/e2e/test_sync.py`, the happy-path case, and `SyncService` over the real stack"
  - phase: 38-02
    provides: "the zero-grant answer, the computed-never-written rollover and the three fail-closed tripwires this plan observes from outside"
  - phase: 35-foundation
    provides: "`get_identity` / `get_linked_identity`, whose 401 and 403 this route inherits without declaring anything"
provides:
  - "ROADMAP criterion 2 proven over real PostgreSQL by a direct body-to-body comparison"
  - "ROADMAP criterion 3 proven over real PostgreSQL by column-level before/after snapshots across three seeded states"
  - "`identity_provider` proven to come from the stored column, asserted against the value read back off the row"
  - "the barrier's 401 and 403 proven inherited by `/auth/sync`"
  - "one fail-closed 500 proven opaque end to end"
affects: [38-06, 39-users-me]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 3789
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Raw `SELECT *` snapshots, so GENERATED ALWAYS columns the ORM leaves unmapped are compared too"
    - "A control case seeded to be present, proving the absent cases are absent for the stated reason"

key-files:
  created: []
  modified:
    - tests/e2e/test_sync.py

key-decisions:
  - "The read-only snapshot is raw `SELECT *` rather than `model_dump()`: `core.access_grants` carries four `GENERATED ALWAYS AS STORED` columns the ORM deliberately leaves unmapped, and a snapshot over mapped columns alone would not have compared them"
  - "The 403's status and code are read off `PreAuthIdentityNotAllowed` rather than written as literals, per the plan; the 401 stays a literal `{\"code\": \"auth_required\"}`, matching `test_unauthenticated_access.py`"
  - "`identity_provider` is asserted against the provider read back out of `core.external_identities`, not against the fixture's own argument — the fixture argument would have proved only that the fixture was called"
  - "No live-concurrency case was added: the e2e harness binds every session to one connection inside an uncommitted transaction, so a second connection cannot see the seeded rows. Recorded in WINDOWS.md as entry 9 rather than silently skipped"
  - "SYNC-01 and SYNC-02 are left unchecked in REQUIREMENTS.md, which this plan does not modify — see the section below for exactly what is now proven and what 38-06 needs to weigh"

patterns-established:
  - "Snapshot by raw `SELECT *`: where a test claims a row is untouched, the comparison covers every column the database has, not every column the ORM happens to map"
  - "The absent case earns a present control: a test asserting exclusion is paired with a sibling asserting inclusion, so a broken fixture fails loudly instead of passing vacuously"

requirements-completed: []

coverage:
  - id: D1
    description: "Zero effective grants and a lapsed grant return byte-identical response bodies, compared as whole dicts against each other"
    requirement: SYNC-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTwoAbsentEntitlementsAreIndistinguishable::test_no_grant_and_a_lapsed_grant_return_the_same_body"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTwoAbsentEntitlementsAreIndistinguishable::test_the_body_they_share_is_the_no_grant_answer"
        status: pass
      - kind: other
        ref: "fault injection: the lapsed grant's `ends_at` flipped to the future, exactly the three exclusion cases failed, then reverted"
        status: pass
    human_judgment: false
  - id: D2
    description: "Neither `revoked` nor `expired` appears anywhere in the lapsed-grant response"
    requirement: SYNC-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTwoAbsentEntitlementsAreIndistinguishable::test_the_lapsed_answer_names_neither_revoked_nor_expired"
        status: pass
    human_judgment: false
  - id: D3
    description: "The window predicate is why the lapsed grant is absent: a grant closed a second ago is excluded while an open-ended started grant is present"
    requirement: SYNC-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTheWindowIsWhyTheGrantIsAbsent"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every column of the caller's access_grants, user_monthly_usage and users rows, plus the three table counts, is identical before and after a sync request across three seeded states"
    requirement: SYNC-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTheRequestChangesNothing"
        status: pass
      - kind: other
        ref: "fault injection: quota's rollover assignment reintroduced in services/sync.py, exactly the two stale-period cases failed, then reverted"
        status: pass
    human_judgment: false
  - id: D5
    description: "`identity_provider` on the wire equals the stored `core.external_identities.provider` value for a caller seeded non-google"
    requirement: SYNC-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTheProviderComesFromTheStoredColumn::test_a_non_google_caller_reports_its_stored_provider"
        status: pass
    human_judgment: false
  - id: D6
    description: "An unauthenticated caller receives 401 auth_required and a verified but unlinked caller receives 403 preauth_identity_not_allowed, both from the existing barrier"
    requirement: SYNC-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTheRouteInheritsTheBarriersRejections"
        status: pass
      - kind: other
        ref: "git diff --stat tests/e2e/test_unauthenticated_access.py — empty, and its 7 cases still pass"
        status: pass
    human_judgment: false
  - id: D7
    description: "An effective grant with no usage row returns 500 with body exactly {\"code\": \"internal_error\"} end to end"
    requirement: SYNC-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py#TestTheFailClosedFiveHundred::test_a_grant_with_no_usage_row_is_an_opaque_500"
        status: pass
    human_judgment: false
  - id: D8
    description: "Sync neither blocks nor is blocked by a genuinely concurrent quota charge or grant flip"
    verification: []
    human_judgment: true
    rationale: "Never observed live, and not observable in this harness: `_db_transaction` binds every session to one connection inside an uncommitted transaction, so a second connection cannot see the seeded rows. The claim rests on the compiled statements carrying no FOR UPDATE (38-01 unit) plus the tables being provably unchanged (D4). A human must not read this plan's green suite as a concurrency observation. Recorded as WINDOWS.md entry 9."

# Metrics
duration: 20min
completed: 2026-09-01
status: complete
---

# Phase 38 Plan 03: The End-to-End Proof Summary

**The three ROADMAP success criteria, the stored provider column, both barrier rejections and one opaque 500 are now proven against real PostgreSQL — with the one claim that is *not* observable in this harness named rather than implied.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-09-01
- **Tasks:** 3
- **Files modified:** 1 (0 created, 1 modified)
- **Cases:** 13 new e2e node ids (1 → 14 in `tests/e2e/test_sync.py`)

## The e2e suite was run under an explicit `-m` selection

The repository's `addopts` is `-m 'not e2e and not schema'`, so a bare `pytest` run silently deselects every case this plan wrote. Every count below comes from an explicit selection.

| Selection | Collected | Passed |
|---|---|---|
| `uv run pytest -m e2e tests/e2e/test_sync.py -v` | 14 | **14** |
| `uv run pytest -q -m 'e2e or schema'` | 308 | **308** (755 deselected) |
| `uv run pytest -q` (the default, for regression only) | 755 | **755** (308 deselected) |

The default run's 755 is unchanged from 38-02's 755; its deselected count rose 295 → 308, which is this plan's 13 new e2e cases and nothing else.

## Which ROADMAP success criteria are now proven against real PostgreSQL

| # | Criterion | Status |
|---|---|---|
| 1 | Grant, `current_period` and `monthly_used` all derive from one evaluation time and match what quota would act on | **Partly.** The values are proven correct e2e on every path here. That they derive from *one captured instant* is a structural fact proven at unit level in 38-01 — an e2e test cannot distinguish one clock read from three a microsecond apart. **Not newly proven by this plan.** |
| 2 | Zero effective grants and a lapsed grant return byte-identical responses | **Proven.** `test_no_grant_and_a_lapsed_grant_return_the_same_body` compares the two parsed bodies **to each other** as whole dicts. |
| 3 | Table state is unchanged across a request, comparing `core.*` before and after | **Proven.** Column-level snapshots of all three tables across three seeded states, with fault injection. |
| 4 | No durable audit row, no new per-attempt telemetry | **Not this plan's.** Owned by 38-04/38-05 (both landed) and 38-06's executable guards. Nothing here touches it. |

The one claim in this plan's `must_haves` that is **not** directly observed is truth 3's opening clause — "running beside a concurrent quota charge or grant flip, sync neither blocks nor is blocked". See "Issues Encountered".

## Whether SYNC-01 and SYNC-02 were checked off, and why

**Neither was checked. `REQUIREMENTS.md` is unmodified by this plan.** Both remain `- [ ]`.

This is a deliberate call, not an oversight, and the reasoning is recorded rather than left for a reader to reconstruct:

- **SYNC-01** — *"returns the effective grant, `current_period`, `monthly_used`, and stored `identity_provider`, all derived from one captured evaluation time."* Every element now has e2e evidence; the stored-provider clause was the last one missing and this plan supplied it (D5). The final clause, *derived from one captured evaluation time*, is proven only structurally at unit level. **I believe SYNC-01 is now fully evidenced across 38-01 + 38-02 + 38-03 and is checkable by 38-06.**
- **SYNC-02** — *"strictly read-only — no rollover, no grant-row flip, no invariant repair, no profile write."* The read-only half is now proven e2e at column level with fault injection (D4), which is the strongest evidence this requirement has ever had. But the ROADMAP and 38-02's handoff both framed 38-03 as proving the no-lock claim **under concurrency** against real PostgreSQL, and this plan's tasks did not ask for that and this harness cannot support it (D8). **Checking SYNC-02 here would paper over a real gap between what the phase expected of 38-03 and what 38-03's tasks specified.**

Rather than check a box that overstates the evidence, this plan hands 38-06 an explicit inventory: the coverage block above cites a node id for every clause of both requirements except D8. 38-06 owns the phase close and is the right place to weigh D8 and decide.

This also continues the precedent 38-01 and 38-02 each recorded. That three plans in a row have declined to check these boxes is itself worth a reader's attention — see "Blockers/concerns".

## Accomplishments

- **Criterion 2 is proven the strong way.** The two bodies are compared **to each other**, not each against a literal, so a shared drift in both answers cannot pass. The shared body is separately asserted to be the whole no-grant answer — all six entitlement fields plus the provider.
- **The equivalence is not vacuous.** Flipping the lapsed grant's `ends_at` into the future failed exactly the three exclusion cases, proving the grant really is seeded, really is visible, and really is excluded by the predicate rather than by a fixture that quietly wrote nothing.
- **Criterion 3 is snapshotted at column level, including columns the ORM cannot see.** `core.access_grants` carries four `GENERATED ALWAYS AS STORED` columns the SQLModel class deliberately leaves unmapped. The snapshot is raw `SELECT *`, so those four are compared too; a `model_dump()` snapshot would have skipped them silently.
- **The stale-period state is one of the three seeded cases**, and it is the one that matters: it is the branch where quota resolves *by writing*, and `get_db` commits on exit.
- **`identity_provider` is asserted against the value read back out of the row**, after a guard asserts that value differs from the happy-path fixture's `google`. Asserting against the fixture's own argument would have proved only that the fixture was called.
- **Both barrier rejections are proven inherited.** `tests/e2e/test_unauthenticated_access.py` is byte-identical (`git diff --stat` empty) and its 7 cases still pass — the route added no bypass and no exemption.

## Task Commits

Each task was committed atomically:

1. **Task 1: Zero grants and a lapsed grant answer identically** — `c70ff05` (test) — 5 node ids
2. **Task 2: The request changes nothing** — `5ce3db6` (test) — 4 node ids
3. **Task 3: The stored provider, the barrier's rejections, one fail-closed 500** — `7d5d751` (test) — 4 node ids

## Files Created/Modified

- `tests/e2e/test_sync.py` — +269/−3 lines; five new test classes, 13 new cases, plus `_entitlement_snapshot`, `_stored_provider`, `_absent_entitlement_body` and `_seed_lapsed_grant` helpers and one `apple_linked_identity` fixture. **No production file was modified: `git diff --stat src/` against the plan's base commit is empty.**

## Decisions Made

**The snapshot is raw SQL, not the ORM.** `_entitlement_snapshot` issues four `text()` statements — `SELECT *` over the caller's grant rows, over the usage rows joined to them, over the caller's user row, and the three whole-table counts — ordered by id so two snapshots are comparable. The plan asked for "every column". The ORM classes carry a comment saying the four `GENERATED ALWAYS AS STORED` columns are deliberately unmapped because Postgres rejects an explicit value for them, so "every column" and "every mapped column" are genuinely different sets here, and only the raw form satisfies the former.

**The 401 is a literal; the 403 is read off the class.** The plan directed reading the error class for the `preauth_identity_not_allowed` code rather than guessing it, so the 403 case asserts `PreAuthIdentityNotAllowed.status` and `PreAuthIdentityNotAllowed.code`. The 401 case keeps the literal `{"code": "auth_required"}`, matching the shape `test_unauthenticated_access.py` already uses for the same rejection — the two files now assert the same contract the same way.

**The exclusion cases got a present control.** `test_an_open_ended_grant_that_has_started_is_present` exists so that a `seed_grant` call that silently wrote nothing would fail a test rather than make three exclusion assertions pass for the wrong reason. It is the reason the fault injection below could be trusted.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Copied the gitignored `.env` into the worktree**

- **Found during:** Task 1 precondition check
- **Issue:** `.env` is gitignored, so this fresh worktree had no `DB_*` values or Firebase test credentials, and the plan's precondition (the tracer's happy path passing) could not be evaluated at all.
- **Fix:** copied `/home/init/native-speaker/ns-api-gateway/.env` into the worktree root — the same fix 38-01 and 38-02 each recorded.
- **Files modified:** none tracked; the file stays gitignored and is in no commit.
- **Verification:** `uv run pytest -m e2e tests/e2e/test_sync.py -v` → 1 passed, which is the precondition the plan named.

**2. [Rule 3 - Blocking] Shortened one class docstring to satisfy ruff E501**

- **Found during:** Task 1 verification
- **Issue:** `TestTwoAbsentEntitlementsAreIndistinguishable`'s docstring came to 121 characters against the repo's `line-length = 120`, failing `uv run ruff check src tests`, which is a task acceptance criterion.
- **Fix:** reworded the trailing clause; no assertion changed.
- **Committed in:** `c70ff05`

### Scope notes

**No live-concurrency case was added.** The plan's three tasks do not ask for one, and its `must_haves` truth 3 explicitly decomposes the concurrency claim into clauses that *are* proven (no `FOR UPDATE` in the compiled statements, nothing added to the session, no attribute assigned, no transaction ended, tables identical before and after). Adding one would have been scope the plan did not grant — and, as recorded below, this harness cannot express it. Recorded in `WINDOWS.md` rather than passed over.

---

**Total deviations:** 2 auto-fixed (both blocking; one environment, one lint), 0 behavioural
**Impact on plan:** none — no scope added, no task altered, no production code changed.

## Issues Encountered

**The Task 2 fault injection reproduced 38-02's finding at the e2e level, and sharpened it.** Quota's rollover assignment was reintroduced into `services/sync.py`:

```python
if usage.monthly_period != period:
    usage.monthly_used = 0
    usage.monthly_period = period
used = usage.monthly_used
```

Exactly the two stale-period cases failed:

```
FAILED tests/e2e/test_sync.py::TestTheRequestChangesNothing::test_a_stale_period_grant_is_left_untouched
FAILED tests/e2e/test_sync.py::TestTheRequestChangesNothing::test_a_repeated_request_answers_the_same_body_over_the_same_rows
=================== 2 failed, 8 passed, 37 warnings in 0.74s ===================
```

with the snapshot showing the row rewritten on disk:

```
E     {'usage': [(UUID('01a05c18-…'), '2026-09',  0, …)]}   # after the request
E  != {'usage': [(UUID('01a05c18-…'), '2020-01', 17, …)]}   # before it
```

The detail worth keeping: **the response-body assertion in the very same test still passed.** `response.json()["entitlement"]["monthly_used"] == 0` holds either way, because assigning zero and reading it back yields what computing zero yields. 38-02 found this against a stub session and warned that a suite asserting only the response body would pass while `/auth/sync` silently wrote a rollover on every read. This confirms it against a real database and a real `get_db` commit-on-exit: **the write really does reach disk, and only the snapshot sees it.** Anyone later tempted to drop `_entitlement_snapshot` as redundant should read this paragraph first. `git diff --stat src/` is empty after the revert.

**The concurrency claim cannot be expressed in this harness, and that is a structural fact, not a shortcut.** `_db_transaction` binds the app's session factory to a single `connection` holding an open transaction that is rolled back at test end, with `join_transaction_mode="create_savepoint"`. Every seeded row therefore lives inside an uncommitted transaction on that one connection. A genuinely concurrent quota charge would need a *second* connection, which by definition cannot see any of it. Proving "sync neither blocks nor is blocked" live would require committed fixtures and manual cleanup — a different harness, and a different plan. Recorded as `WINDOWS.md` entry 9 (`unmet-truth`, open) so it is visible at ship time rather than buried here.

**A note on `actuals.tokens`.** Recorded as 3789, chars/4 over the realized diff (15,155 characters in one file). The plan estimated 45,000 at `confidence: low` — a gap of roughly 12×, matching 38-01's 12× and sitting near 38-02's 19×, all in the same direction. Three data points in this phase now agree that these estimates are not measuring diff size. Not rounded toward the estimate.

## Known Stubs

**None.** No `TODO`, `FIXME`, skipped test or `xfail` was introduced — `grep -n "TODO\|FIXME\|skip\|xfail\|placeholder" tests/e2e/test_sync.py` returns nothing. Every `<verify>` in the plan was run and reported above; none was deferred.

One coverage gap exists and is deliberately **not** hidden here: D8, the live-concurrency observation, is recorded in `.planning/WINDOWS.md` as entry 9 and in the coverage block as `human_judgment: true`.

## Threat Flags

None — no new surface. All three `mitigate` dispositions in the plan's threat register were implemented and asserted:

- **T-38-09** (spoofing via the route's identity narrowing) — `TestTheRouteInheritsTheBarriersRejections` asserts the 401 and the 403 end to end, and `tests/e2e/test_unauthenticated_access.py` is unmodified, so the route declares no exemption.
- **T-38-10** (disclosure across two broken states) — the two bodies are asserted equal to each other, and neither `revoked` nor `expired` appears in the lapsed response.
- **T-38-11** (tampering via `get_db`'s commit-on-exit) — column-level snapshots across three states, with the fault injection above proving the guard catches a reintroduced write.

This plan adds tests only; it opens no trust boundary and touches no production file.

## Verification

| Check | Result |
|---|---|
| `uv run pytest -m e2e tests/e2e/test_sync.py -v` | **14 passed** (1 before this plan, 13 added) |
| `uv run pytest -q -m 'e2e or schema'` | **308 passed**, 755 deselected |
| `uv run pytest -q` | **755 passed**, 308 deselected — unchanged from 38-02's 755 |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/test_docstring_bar.py` | 9 passed — the baseline of 0 holds on every root |
| `uv run pytest tests/e2e/test_unauthenticated_access.py -m e2e` | 7 passed |
| `git diff --stat tests/e2e/test_unauthenticated_access.py` | empty — unmodified |
| `git diff --stat src/` | **empty** — this plan adds tests only |
| `git diff --stat migrations/` | empty |
| `git diff --stat .planning/` (excluding this summary) | empty — no STATE.md, no ROADMAP.md, no REQUIREMENTS.md change |

Node-id counts against the plan's minimums: Task 1 **5** (≥3), Task 2 **4** (≥4), Task 3 **4** (≥4).

Both mandated fault injections were run and observed, not asserted: Task 1's (the lapsed grant made live → 3 exclusion cases failed) and Task 2's (quota's rollover assignment reintroduced → exactly the 2 stale-period cases failed). Both were reverted and green restored.

## User Setup Required

None. Note for a fresh worktree: `.env` is gitignored and must be copied in before the e2e suite can run, and the suite must be selected explicitly with `-m e2e` or the repo's `addopts` will deselect all of it.

## Next Phase Readiness

**Ready.** `/auth/sync` is now proven end to end against real PostgreSQL on every path a real caller can reach: the entitlement it holds, the two indistinguishable absent states, the untouched tables, the stored provider, both rejections and one opaque 500.

**Ready for:**
- **38-06** — the phase close. It inherits a complete evidence inventory in the coverage block above, and two decisions to make: whether to check SYNC-01 (I believe yes — every clause is cited) and whether D8's harness limitation should block SYNC-02 or be waived in `WINDOWS.md` with a reason.
- **39 (`GET /users/me`)** — criterion 2 of Phase 39 requires `identity_provider` to come from the stored column and match what `/auth/sync` reports. `TestTheProviderComesFromTheStoredColumn` is the case Phase 39's equivalent must agree with, and `_stored_provider` is the helper it can reuse.

**Blockers/concerns:**
- **SYNC-01 and SYNC-02 are still unchecked after three consecutive plans.** Each declination was individually reasonable and individually recorded, but the cumulative effect is a phase whose requirements read as untouched while its evidence is in fact extensive. 38-06 should check them or record why not — leaving them open by inertia would be the wrong outcome.
- **`WINDOWS.md` entry 9 is open** and, with `workflow.windows_enforce` on, contributes to the 7 open entries blocking `/gsd:ship`. It is a genuine harness limitation, not a defect in the endpoint, so waiving with a reason may be the right disposition — but that is 38-06's call, not this plan's.

## Self-Check: PASSED

- `tests/e2e/test_sync.py` exists on disk (307 lines) and `.planning/phases/38-post-auth-sync/38-03-SUMMARY.md` is this file.
- All three task commits are present on `worktree-agent-a73ef00cb42a63f56`: `c70ff05`, `5ce3db6`, `7d5d751`.
- `git diff --stat src/` and `git diff --stat migrations/` are both empty against the plan's base commit `66c9e9f`.

---
*Phase: 38-post-auth-sync*
*Completed: 2026-09-01*
