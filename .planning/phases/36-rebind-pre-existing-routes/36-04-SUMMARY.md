---
phase: 36-rebind-pre-existing-routes
plan: 04
subsystem: api
tags: [quota, entitlements, row-locking, postgres, sqlmodel, fail-closed, error-taxonomy]

# Dependency graph
requires:
  - phase: 36-03
    provides: consume_quota's marked slot, GrantsDB.lock_effective_grants and the lock order it fixes, require_quota's own-session boundary, seed_grant and the quota_grant fixture
  - phase: 36-01
    provides: AccessTier / AccessGrant / UserMonthlyUsage models and the seeded `registered` tier at 50 credits
  - phase: 36-02
    provides: the AnalyzeResponse list defaults (D-12) — which this plan discovered were never reaching the client
  - phase: 35-foundation
    provides: RequestContext.evaluated_at, the closed error registry and assert_registry_total, ServiceError plus its one data-driven handler
provides:
  - GrantsDB.lock_usage — the usage row FOR UPDATE, second in the lock order, never inserting
  - GrantsDB.monthly_credits — the tier allowance read, deliberately unlocked
  - MissingUsageRowError / MultipleEffectiveGrantsError / UnknownTierError — three INTERNAL_ERROR-mapped tripwires, no new registry entry
  - consume_quota complete — §8.4 steps 1-5 in one locked transaction, remaining floored at zero
  - seed_grant(with_usage=False) — the only way to reach D-09's branch from a test
  - tests/unit/test_quota_resolver.py — the stub-session proof of the branches PostgreSQL cannot produce
affects: [36-05 POST /chats/{chat_id} and the two-connection lock test, 38 auth-sync, 41 claim-anonymous-grant, 42 claim-registered-grant, 45 subscription grants]

actuals:
  tokens: 11900
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "A tripwire branch for a state a database constraint makes unreachable: raise, never tie-break, so dropping the constraint fails loudly instead of silently choosing"
    - "A stub session that dispatches rows by target entity rather than call position, so statement ordering is asserted once and explicitly rather than implied by the stub's own shape"
    - "Lazy period rollover inside the same locked transaction as the increment, applied before the allowance comparison"

key-files:
  created:
    - tests/unit/test_quota_resolver.py
  modified:
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/database/grants.py
    - src/nativespeaker/api/quota.py
    - src/nativespeaker/api/services/chats.py
    - tests/e2e/test_quota.py
    - tests/e2e/conftest.py

key-decisions:
  - "A third error class, `UnknownTierError`, beyond the plan's two. The plan requires the dangling-tier branch to `fail closed with an INTERNAL_ERROR-mapped raise` but names no vehicle; a bare `ServiceError` maps to 500 with `log_level = None`, so it would raise without logging and without a distinguishable `error_type`. It calls no `register_class`, so the registry total is unchanged."
  - "`usage.updated_at` is stamped from `evaluated_at` on the increment. The column is NOT NULL with no database DEFAULT and no `onupdate`, so nothing else would ever advance it and every charged row would carry its creation time forever. Using the captured instant keeps the module's no-clock property intact."
  - "No `session.add(usage)` on the increment. The row was loaded through the session and is already tracked; adding it would be a no-op that reads as a mint. The absence is stated in a comment so the next reader does not add one."
  - "The stub session dispatches by `statement.column_descriptions[0]['entity']`, not by call position. A position-keyed stub would hand the grant rows to a usage read if the two were ever swapped — silently passing the test written to catch that."
  - "The e2e boundary cases bracket each boundary from both sides rather than asserting the exactly-equal instant, which no client can name. The exact `starts_at == evaluated_at` / `ends_at == evaluated_at` claims are asserted against the compiled predicate in the unit module."

patterns-established:
  - "Mutation-probing a test-only task in place of a RED phase: four targeted mutations of the code under test (drop the zero floor, skip the count reset, tie-break on multi-grant, lazily mint) each fail 3-4 cases, which is the evidence RED would otherwise have supplied."
  - "Tripwire comment convention: state that the branch is unreachable, name the constraint that makes it so, and state what future change it is there to catch — so nobody deletes it as dead code."

requirements-completed: []

coverage:
  - id: D1
    description: "`monthly_used == allowance` rejects 429 without incrementing; `allowance - 1` is admitted and commits exactly at the allowance; the next request then rejects."
    requirement: REBIND-06
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestTheAllowanceIsSpent (4 cases, -k exhausted selects 2)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestRemainingNeverNegative (9 cases)"
        status: pass
    human_judgment: false
  - id: D2
    description: "`remaining` is never negative — an already-over-allowance row clamps to zero and rejects rather than producing a negative count or a second charge."
    requirement: REBIND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestRemainingNeverNegative::test_at_or_above_the_allowance_rejects[one-over|far-over] and ::test_a_rejection_leaves_the_count_untouched"
        status: pass
      - kind: other
        ref: "mutation probe: removing `max(..., 0)` fails 4 cases"
        status: pass
    human_judgment: false
  - id: D3
    description: "A grant with zero `core.user_monthly_usage` rows returns 500 `internal_error` and no usage row is minted."
    requirement: REBIND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestAGrantWithNoUsageRow (2 cases, -k missing_usage) — 500 + read-back of zero rows"
        status: pass
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestMissingUsageRow (3 cases) — `session.added == []`"
        status: pass
      - kind: other
        ref: "grep gate: no `INSERT INTO core.user_monthly_usage` and no `session.add(UserMonthlyUsage` in quota.py or grants.py, comments stripped first"
        status: pass
    human_judgment: false
  - id: D4
    description: "Two effective grants raise rather than tie-breaking, and the resolver does not pick either."
    requirement: REBIND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestMultipleEffectiveGrants (3 cases) — raises, issues no usage statement, maps to INTERNAL_ERROR not QUOTA_EXCEEDED"
        status: pass
      - kind: other
        ref: "mutation probe: replacing the raise with `pass` fails 3 cases"
        status: pass
    human_judgment: true
    rationale: "Unreachable in real PostgreSQL while `ix_access_grants_one_active_per_user` stands, so no e2e or schema test can produce the state. A stub is the only instrument, and whether a stub-only proof is sufficient for a tripwire is a judgment call — recorded rather than claimed as behavioural coverage."
  - id: D5
    description: "Lazy rollover happens inside the same locked transaction as the increment: a stale `monthly_period` resets `monthly_used` to 0 and rewrites the period before the allowance comparison."
    requirement: REBIND-06
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestTheAllowanceIsSpent::test_a_stale_period_rollover_resets_before_the_allowance_is_compared — stale + exhausted admits, reads back (current month, 1)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestLazyRollover (4 cases)"
        status: pass
    human_judgment: true
    rationale: "\"Both writes commit or neither does\" is argued from the code — one session, one caller-owned commit, no intermediate flush — not observed under a competing reader. Only a two-connection test can show it, and that is 36-05's `tests/schema/test_grant_locks.py`."
  - id: D6
    description: "Effective grants are locked `ORDER BY id ASC` before any usage row is locked, and the ordering is identical on every path through the resolver."
    requirement: REBIND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestGrantThenUsageOrder (5 cases — admitted, exhausted, rollover, missing-usage, and no user-row lock ahead of either)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestTheLockingStatements — grant statement FOR UPDATE + ORDER BY id ASC, usage statement FOR UPDATE, tier statement unlocked"
        status: pass
    human_judgment: true
    rationale: "Statement-level, not contention-level. The lock order is proven by the sequence of statements the resolver issues; that the locks actually serialise two concurrent POSTs is 36-05's two-connection test."
  - id: D7
    description: "Both effective-grant boundaries behave as specified: `starts_at` inclusive, `ends_at` exclusive."
    requirement: REBIND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestTheLockingStatements::test_the_lower_bound_is_inclusive / ::test_the_upper_bound_is_exclusive — compiled PostgreSQL predicate asserts `starts_at <=` and `ends_at >`, and the negations"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestThePredicateBoundaries (5 cases, -k boundary) — each boundary bracketed from both sides"
        status: pass
    human_judgment: false
  - id: D8
    description: "A correct phrase returns 200 with `issues == []` and `suggestions == []` — the D-12 half of REBIND-06, over the real transport."
    requirement: REBIND-06
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestACorrectPhraseIsServedAndCharged"
        status: pass
      - kind: other
        ref: "Required a source fix — see Deviations 1. The case failed with `KeyError: 'issues'` before it."
        status: pass
    human_judgment: false
  - id: D9
    description: "A grant referencing a tier with no `core.access_tiers` row fails closed, never as allowance 0 and never as an unbounded allowance."
    requirement: REBIND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py::TestUnknownTier (3 cases)"
        status: pass
    human_judgment: true
    rationale: "A foreign key makes it unreachable through PostgreSQL, so like D4 it is stub-only. Recorded as judgment rather than counted as behavioural coverage."

# Metrics
duration: 17min
completed: 2026-08-22
status: complete
---

# Phase 36 Plan 04: The Allowance Is Actually Spent Summary

**`POST /chats` now charges the grant it finds — usage row locked after the grant, lazy period rollover inside the same transaction, `remaining` floored at zero — and answers 500 rather than inventing an allowance when the stored state is broken.**

## Performance

- **Duration:** 17 min (first task commit to last)
- **Tasks:** 3 of 3
- **Files modified:** 7 (1 created, 6 modified)
- **Suite:** 1184 → 1234 passing (+50, no regression)

## Accomplishments

- **The tracer's gap is closed.** A caller holding an effective grant no longer passes uncharged.
  §8.4 steps 2-5 run inside the one transaction `require_quota` opens and commits before the
  handler: grant rows already locked ascending, then the usage row `FOR UPDATE`, then the period
  rollover, then the allowance read, then the comparison, then the increment. Nothing awaits a
  network call while the session is open.
- **Three fail-closed branches, none of which can invent entitlement.** A missing usage row, more
  than one effective grant, and a grant pointing at a tier with no row all raise
  `INTERNAL_ERROR`-mapped classes. None of them calls `register_class` — the client sees the
  registry's generic copy and `assert_registry_total()` still passes.
- **The never-lazily-mint rule is proven, not asserted.** The e2e case seeds the half-written pair a
  failed grant transaction would leave, gets its 500, then reads `core.user_monthly_usage` back and
  finds it still empty. The unit case asserts `session.added == []`. The grep gate confirms no
  insert exists in `src/` at all, comments stripped first.
- **Both predicate boundaries are pinned twice, at the level each is actually checkable.** The
  exactly-equal instants are asserted against the compiled PostgreSQL predicate — `starts_at <=`
  and `ends_at >`, plus the negations, so widening either to `<`/`>=` fails. The behavioural
  bracket either side of each boundary is e2e.
- **The unit module is mutation-probed rather than trusted.** Dropping the zero floor, skipping the
  count reset, tie-breaking on multi-grant, and lazily minting each fail 3-4 cases. That is the
  evidence a RED phase would have supplied for a task whose code was written one commit earlier.
- **A real defect in the D-12 deliverable surfaced and was fixed.** The correct-phrase case failed
  with `KeyError: 'issues'` — see Deviations 1. It was not a test bug.

## Task Commits

1. **Task 1 (RED): failing e2e cases for the allowance arithmetic and rollover** — `32a0d32` (test)
2. **Task 1 (GREEN): §8.4 steps 2-5** — `bc8e63c` (feat)
3. **Task 2: unit coverage of the resolver's pure policy** — `c97e5cf` (test)
4. **Task 3 auto-fix: persist the validated LLM model** — `c855e2d` (fix)
5. **Task 3: e2e coverage of the 500, the boundaries, and the correct phrase** — `e6abc71` (test)

## Files Created/Modified

- `src/nativespeaker/api/errors.py` — `MissingUsageRowError`, `MultipleEffectiveGrantsError`,
  `UnknownTierError` under a banner recording why none of them registers a class and why
  `log_level = logging.ERROR` is load-bearing
- `src/nativespeaker/api/database/grants.py` — `lock_usage` (never inserts) and `monthly_credits`
  (deliberately unlocked, with the serialisation reason in the docstring)
- `src/nativespeaker/api/quota.py` — §8.4 steps 2-5 as a flat sequence of branches, each carrying
  its reason beside it
- `src/nativespeaker/api/services/chats.py` — the validated model is persisted and returned
  instead of the raw provider dict
- `tests/unit/test_quota_resolver.py` — 38 cases over a stub session, 9 classes
- `tests/e2e/test_quota.py` — `TestTheAllowanceIsSpent`, `TestAGrantWithNoUsageRow`,
  `TestThePredicateBoundaries`, `TestACorrectPhraseIsServedAndCharged`, and the `usage_rows`
  read-back helper
- `tests/e2e/conftest.py` — `seed_grant(..., with_usage=False)`

## Decisions Made

See the `key-decisions` block above. The one worth restating in prose: **`UnknownTierError` is a
third class the plan's artifact table does not list.** The plan requires the branch's behaviour but
names no vehicle for it, and the two obvious alternatives are both worse — a bare `ServiceError`
maps to 500 but carries `log_level = None`, so it would raise without a traceback and without a
distinguishable `error_type` in the log, and reusing `MissingUsageRowError` would report a missing
usage row for a grant whose usage row is fine.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug / Rule 2 — Missing validation] The validated LLM model was discarded and the raw
provider dict persisted**

- **Found during:** Task 3, writing the correct-phrase case
- **Issue:** `services/chats.py::ask_llm` called `AnalyzeResponse.model_validate(llm_response)` and
  threw the result away, returning `Message(..., content=llm_response)` — the raw dict. D-12
  (plan 36-02) defaulted `AnalyzeResponse.issues` and `.suggestions` to `[]`, but a default only
  materialises **on the model**. For a grammatically correct phrase — the exact input the
  unconstrained chain answers with only `resolved_mode` and `response` — those two keys were simply
  absent from the stored row and from the response body. The 500 D-12 set out to fix was fixed; the
  empty arrays it promised never arrived. The plan's own must-have truth
  ("a correct phrase returns 200 with `issues == []` and `suggestions == []`") was therefore false,
  and the e2e case failed with `KeyError: 'issues'`.
  Second, smaller face of the same line: because the raw dict was stored, any extra key the model
  emitted was persisted verbatim and echoed to the client — unvalidated provider output crossing a
  trust boundary.
- **Fix:** Keep the validated model and return `content=validated.model_dump()`. The reasoning is
  recorded in a comment at the call site, including the pointer to
  `.planning/todos/pending/restore-strict-structured-output.md` as the general fix.
- **Files modified:** `src/nativespeaker/api/services/chats.py`
- **Commit:** `c855e2d`
- **Scope note:** `services/chats.py` is outside this plan's `files_modified`. Committed separately
  from the task-3 test commit so the task-3 acceptance criterion — `git show --stat HEAD` naming
  only `tests/e2e/test_quota.py` and `tests/e2e/conftest.py` — still holds literally, and so the
  source change is reviewable on its own. The alternative was to weaken the test to assert only
  what the code happened to do, which would have retired a must-have truth by editing the ruler.

### Documented departures from the plan text

**2. A third error class, `UnknownTierError`.** The plan's artifact table lists two. See Decisions
Made. `assert_registry_total()` still passes; no `ErrorCode` member was added.

**3. `usage.updated_at` is stamped on the increment.** Not asked for. The column is `NOT NULL` with
no database DEFAULT and no `onupdate`, so without this every charged row would carry its creation
time forever. Stamped from `evaluated_at`, so the module still reads no clock and the grep gate
still returns 0.

**4. Task 1's RED cases live in `tests/e2e/test_quota.py`, which the plan assigns to task 3.**
Task 1 carries `tdd="true"` but its `<files>` list is source-only, so RED had nowhere to go. The
cases were written where they permanently belong rather than in a scratch location, and task 3
extended the same file. Consequence: the `usage_rows` read-back helper the plan assigns to task 3
landed in task 1's RED commit, because task 1's RED cases need it.

**5. One of task 1's four RED cases passed on first run.**
`test_an_exhausted_grant_is_not_charged_for_the_request_it_refused` asserts a count is *unchanged*,
which was trivially true while nothing incremented. Kept as-is: it is vacuous only before the
feature exists and load-bearing after. The other three failed as intended
(`assert [('2026-07', 50)] == [('2026-08', 1)]` among them).

**6. Task 2 had no RED phase; it was mutation-probed instead.** The task carries `tdd="true"` but
its subject — the resolver — was written one commit earlier, so its cases pass by construction.
Four targeted mutations of `quota.py` were run against the new module and each failed 3-4 cases;
`quota.py` was restored and verified clean against HEAD afterwards. Recorded because "the tests
pass" is not evidence a test can fail.

**7. The rollover case was renamed in task 3.** Task 1 named it
`test_a_stale_period_rolls_over_...`, which `-k rollover` does not match. Renamed to
`..._rollover_resets_...` so the `36-VALIDATION.md` selector resolves, as task 3's action requires.

**8. Nine test classes in the unit module, not seven.** The plan names seven; `TestUnknownTier` and
`TestTheResolverReadsNoClock` are additions covering the dangling-tier branch (departure 2) and
D-06's single-instant property. The plan's `grep -cE` acceptance criterion counts only the seven
named classes and returns 7.

**9. REBIND-05 and REBIND-06 left unchecked, though the plan claims both.**
`requirements.mark-complete` was run and did flip both checkboxes; they were reverted. `36-05-PLAN.md`
also claims both, and `POST /chats/{chat_id}` is still ungated — so REBIND-06's "every pre-existing
route behaves as it did in v1.6" is not yet true, and REBIND-05's flow is not yet applied to every
route that needs it. Checking them here would report the phase's central behaviour as done while one
route of it is missing. Same call 36-03 made, for the same reason. Separately, the traceability
table carries a collapsed range row (`| REBIND-01 … REBIND-06 | Phase 36 | Pending |`) that the tool
cannot match per-ID; it reports `table_unmatched` and leaves the row alone, which is correct here.

**10. The e2e boundary cases bracket rather than touch the boundary.** The plan's `<behavior>` for
`-k boundary` lists future-`starts_at`, past-`ends_at`, and NULL-`ends_at`; two more were added at
one second either side, because a client cannot name the instant the barrier captures and the
exactly-equal case is only assertable against the compiled predicate — which the unit module does.
Five cases, so the "at least three" criterion holds.

---

**Total deviations:** 1 auto-fixed (Rule 1 + Rule 2), 9 documented departures.
**Impact on plan:** No scope change to the three tasks. The auto-fix is the only source edit outside
`files_modified`, and it exists because a must-have truth of this plan was false in the code the
plan inherited. `docker-compose.yml` and `uv.lock` were never staged (D-15).

## Issues Encountered

- **The Docker daemon socket is not accessible from this environment**
  (`permission denied ... /var/run/docker.sock`), so `docker compose up -d db` could not be run.
  PostgreSQL was already listening on `localhost:5432` and every e2e and schema case ran against
  it, so nothing was skipped — but the plan's manual verification step A1 cannot be executed as
  written from here.
- **`gsd-tools query state.update-progress`** still fails with "Progress field not found in
  STATE.md", as plans 36-01, 36-02 and 36-03 all reported. Known non-fatal tooling issue.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -q` | 961 passed, 273 deselected (was 923) |
| `uv run pytest -q -m ""` | **1234 passed** (baseline 1184; +50, no regression) |
| `uv run pytest tests/e2e -m e2e -q` | 193 passed (was 181) |
| `uv run pytest tests/e2e/test_quota.py -m e2e -q` | 20 passed (was 8) |
| `-k missing_usage` / `rollover` / `exhausted` / `no_grant` / `boundary` | 2 / 1 / 2 / 6 / 5 selected, all pass |
| `uv run pytest tests/unit/test_quota_resolver.py` | 38 passed; `-k multiple` selects 3 |
| `uv run ruff check src tests` | clean |
| `uv run ty check src` | clean |
| `MissingUsageRowError` / `MultipleEffectiveGrantsError` probe | `ok` — both `INTERNAL_ERROR`, both `logging.ERROR` |
| `assert_registry_total()` | `registry total unchanged` |
| `GrantsDB` method probe | `ok` — three methods present, `monthly_credits` has no `with_for_update` |
| `lock_usage` probe | `usage lock present` |
| grep gates (mint, `datetime.now`, `record_rejection`, `selectinload`/`joinedload`) | all `0`, comments stripped first |
| mutation probes (no floor / no reset / tie-break / lazy mint) | 4 / 3 / 3 / 4 cases fail respectively; restored clean |
| `seed_grant` signature probe | `with_usage ok` |
| class-count grep | `7` |
| `git log --stat -6 \| grep -cE 'docker-compose.yml\|uv.lock'` | 0 |
| `git status --porcelain` | `docker-compose.yml` and `uv.lock` still ` M`, unstaged (D-15) |
| deletion check across all 5 commits | no tracked file deleted |

## Threat Flags

None new — no network endpoint, route, or trust boundary is added. Against the plan's register:

- **T-36-mint:** mitigated, and proven at both levels. `lock_usage` never inserts; `None` raises.
  The grep gate finds no insert in `src/`; the unit case asserts `session.added == []`; the e2e case
  reads the table back after the 500 and finds it still empty.
- **T-36-bypass:** mitigated. The allowance comparison and the increment both happen after the
  grant and usage locks are taken in the same transaction, and every rejection raises before the
  increment — asserted by `test_a_rejection_leaves_the_count_untouched` and by the e2e read-back.
  Real two-connection contention remains 36-05's.
- **T-36-tierescalate:** mitigated. `grant.tier_id` comes from the locked grant row and never from
  the request. A dangling tier raises `UnknownTierError`; the two silent readings — allowance 0 and
  unbounded — are each pinned by their own unit case.
- **T-36-deadlock:** mitigated at statement level. `TestGrantThenUsageOrder` asserts
  `["grants", "usage", "allowance"]` on the admitted, exhausted and rollover paths and
  `["grants", "usage"]` on the missing-usage path, plus that no statement touches `core.users`.
- **T-36-negative:** mitigated. `max(allowance - monthly_used, 0)`; the over-allowance cases reject
  and leave the count untouched, and removing the floor fails four cases.
- **T-36-telemetry:** mitigated. Three `quota_integrity_failure` branches and one
  `quota_rejected` branch, each labelled with a fixed branch name and the route path template. No
  grant id, user id, subject or raw path in a label. `record_rejection` is not called and
  `AuthEventResult` is untouched — both grep-asserted.
- **T-36-oracle:** accepted disposition unchanged. The 429/500 split is intentional (D-08/D-09) and
  every identifier lives in the exception message, which `service_error_handler` logs server-side;
  the client receives `{"code": "internal_error"}` and nothing else — asserted exactly, as an
  equality on the whole body.
- **T-36-llmdrain:** accepted disposition unchanged, and now slightly narrower in practice:
  Deviation 1 removed one class of provider-shaped 500 (the correct-phrase case) that was burning a
  credit for a request that never reached the client.
- **T-36-SC:** upheld. Zero packages installed; `uv.lock` untouched.

**One improvement beyond the register:** unvalidated provider output is no longer persisted or
echoed. Before Deviation 1, whatever keys the model emitted went into `core.messages.content` and
back to the client verbatim.

## Known Stubs

None. No stub, placeholder, skipped test, or unrun `<verify>` was left behind.

## Known Gaps

- **The lock window and the atomicity of rollover-plus-increment are argued, not observed.** No
  test holds a competing lock. Deliverables D5 and D6 are routed to human judgment until
  `tests/schema/test_grant_locks.py` lands in 36-05.
- **Two branches are stub-only by necessity.** `MultipleEffectiveGrantsError` (D4) and
  `UnknownTierError` (D9) are unreachable through PostgreSQL — a partial unique index and a foreign
  key respectively — so no e2e or schema test can produce them. Both are recorded as human-judgment
  deliverables rather than counted as behavioural coverage.
- **REBIND-05's flagged assumption is still open.** The plan fixes the shared predicate's wording,
  its boundary inclusivity, and the reading of an already-over-allowance row as three assumptions
  rather than derivations. Phase 38 imports this predicate by name (D-03); if its reading of
  `03-sync.md §42-45` differs, that difference must be resolved there, not silently reconciled.
- **`POST /chats/{chat_id}` is still ungated.** Its wrapper and its `quota_checked=True` are plan
  36-05's, and condition 10 fails boot if either lands alone.

## User Setup Required

None. Note for anyone running the e2e suite by hand: PostgreSQL must be listening
(`docker compose up -d db && uv run pogo apply`), and `set -a; . ./.env; set +a` is still required
before running the app outside pytest.

## Next Phase Readiness

Ready. `36-05` inherits a complete resolver:

- `consume_quota` needs no further change for `POST /chats/{chat_id}` — only the new wrapper, the
  registry flag, and the wrapper tuple in `assert_route_enumeration`.
- The lock order is fixed and asserted, so `tests/schema/test_grant_locks.py` has a definite
  sequence to contend against: grants ascending by id, then the usage row, then an unlocked tier
  read.
- `seed_grant` now varies `source`, `status`, `starts_at`, `ends_at`, `monthly_period`,
  `monthly_used` and `with_usage`, which covers every seeding shape 36-05's cases need.
- `-k malformed` and `-k audit` are deliberately absent — they belong to 36-05.
- `docker-compose.yml` and `uv.lock` remain modified and uncommitted per D-15.

---
*Phase: 36-rebind-pre-existing-routes*
*Completed: 2026-08-22*

## Self-Check: PASSED

All eight claimed files exist on disk and all five claimed commits (`32a0d32`, `bc8e63c`,
`c97e5cf`, `c855e2d`, `e6abc71`) resolve in `git log`.
