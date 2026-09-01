---
phase: 38-post-auth-sync
plan: 06
subsystem: api
tags: [tests, ast, audit-removal, requirements, phase-close]

# Dependency graph
requires:
  - phase: 38-01
    provides: "`SyncService`, the route, and the unit proof that no statement takes a lock"
  - phase: 38-02
    provides: "the five service branches, all proven against a stub session"
  - phase: 38-03
    provides: "the e2e proof over real PostgreSQL, and the evidence inventory this plan checks boxes against"
  - phase: 38-04
    provides: "the § Audit removal from SHARED-INVARIANTS.md that criterion 4 half-rests on"
  - phase: 38-05
    provides: "the dated SYNC-03 amendment this plan checks off"
provides:
  - "six syntax-tree guards that fail if the audit subsystem, the single migration, or a per-attempt sync event returns"
  - "SYNC-01, SYNC-02 and SYNC-03 checked in REQUIREMENTS.md against green suites"
  - "each of the four ROADMAP Phase 38 success criteria mapped to a named node id or declared unproven"
affects: [39-users-me, 43-apple-hook, 46-signout]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 1340
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A guard module that reasons about source with `ast` rather than about behaviour, following `tests/unit/error_tree.py`"
    - "A negative guard paired with a positive control, so an empty walk fails rather than passing vacuously"

key-files:
  created:
    - tests/unit/test_sync_audit_removal.py
  modified:
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Each of the plan's six behaviours got its own class, one test each, so every class docstring states exactly one rule; the acceptance criterion of exactly 6 node ids is met either way"
  - "Every guard was fault-injected, not just the three the plan named — six injections plus the control, because a guard trusted without injection is the failure this module exists to prevent"
  - "The sync-service guard was injected twice: the import arm short-circuits the call arm, so a call-only injection with no import was run separately to prove the second assertion independently"
  - "All three SYNC boxes are checked. SYNC-02 is checked on its written text — the four clauses it actually names — and the no-lock-under-live-concurrency inference, which its text does not contain, stays open as WINDOWS.md entry 9"
  - "WINDOWS.md entry 9 is deliberately NOT waived: it is the only durable reminder that observing the concurrency claim needs a harness with committed fixtures, and waiving it would trade that reminder for a green ship gate"

patterns-established:
  - "The control test is part of the guard, not decoration: narrowing the walk to an empty directory must fail a test, or every negative assertion in the module is unfalsifiable"
  - "Requirement boxes are checked in one commit, after the suites are green, with the clause-by-clause citation recorded in the summary rather than implied by the checkmark"

requirements-completed: [SYNC-01, SYNC-02, SYNC-03]

coverage:
  - id: D1
    description: "`tests/schema/test_inventory.py` still expects exactly one audit table, `{\"subscription_events\"}`, read from its syntax tree"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_audit_removal.py#TestTheAuditTableExpectationIsStillOneMember::test_the_expectation_names_only_subscription_events"
        status: pass
      - kind: other
        ref: "fault injection: `\"auth_events\"` added to EXPECTED_AUDIT_TABLES, this case failed, then reverted"
        status: pass
    human_judgment: false
  - id: D2
    description: "No SQL file under `migrations/` mentions `auth_events` or `auth_event_result` under any casing"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_audit_removal.py#TestNoMigrationNamesTheDeletedAuditTable::test_no_sql_file_mentions_either_deleted_name"
        status: pass
      - kind: other
        ref: "fault injection: `-- AUTH_EVENTS injection probe` appended to the migration, this case failed on the uppercase form, then reverted"
        status: pass
    human_judgment: false
  - id: D3
    description: "Exactly one `.sql` file exists under `migrations/`, so a rebuild that adds an incremental file fails this phase's own guard"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_audit_removal.py#TestTheMigrationIsStillTheOnlyOne::test_exactly_one_sql_file_exists_under_migrations"
        status: pass
      - kind: other
        ref: "fault injection: a second empty `.sql` file created under migrations/, this case failed, then removed"
        status: pass
    human_judgment: false
  - id: D4
    description: "`services/sync.py` imports no logging library and makes no logging call, so it emits no event of its own on any path"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_audit_removal.py#TestTheSyncServiceEmitsNoEventOfItsOwn::test_it_imports_no_logging_library_and_makes_no_logging_call"
        status: pass
      - kind: other
        ref: "fault injection A: `import structlog` plus a `.info()` call added, this case failed on the import arm, then reverted"
        status: pass
      - kind: other
        ref: "fault injection B: a bare `self.grants_db.warning(\"x\")` call with no import, this case failed on the call arm, then reverted"
        status: pass
    human_judgment: false
  - id: D5
    description: "No string constant anywhere under `src/` contains `auth_sync` or `auth_events`, so a per-attempt sync event under an obvious name fails here"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_audit_removal.py#TestNoPerAttemptSyncEventNameWasAdded::test_no_source_string_names_a_sync_event_or_the_deleted_table"
        status: pass
      - kind: other
        ref: "fault injection: `structlog.get_logger().info(\"auth_sync_succeeded\")` added to services/sync.py, this case failed, then reverted"
        status: pass
    human_judgment: false
  - id: D6
    description: "The `src/` walk is non-vacuous: it finds `quota_rejected`, an event name `services/quota.py` is known to emit"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_audit_removal.py#TestTheSourceWalkIsNotVacuous::test_the_walk_finds_an_event_name_quota_is_known_to_emit"
        status: pass
      - kind: other
        ref: "fault injection: SRC narrowed to an empty directory — this control case failed while D5 passed vacuously, which is exactly the failure it exists to catch, then reverted"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every `/auth/sync` attempt earns exactly one `request` line carrying request id, method, path, status code and duration"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_logging.py::test_middleware_logs_request_on_response"
        status: pass
      - kind: unit
        ref: "tests/unit/test_logging.py::test_middleware_excludes_health_ready"
        status: pass
      - kind: unit
        ref: "tests/unit/test_logging.py::test_request_id_bound_in_context"
        status: pass
    human_judgment: true
    rationale: "The middleware's one-line-per-non-excluded-path property is proven on a synthetic app, and `/auth/sync`'s membership in that set is structural — `_EXCLUDED_PATHS` is `frozenset({\"/health/ready\"})`, asserted by no test naming `/auth/sync`. The composition is sound but the second half is read, not run."
  - id: D8
    description: "Every rejection additionally earns one WARNING named for its exception class from the shared error handler"
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "tests/unit/test_exception_handlers.py#TestTheHandlerRecordsTheRejectionExactlyOnce::test_the_event_name_is_the_snake_cased_class_name"
        status: pass
      - kind: unit
        ref: "tests/unit/test_exception_handlers.py#TestAnAccountUnavailableArmTravelsTheWholeErrorPath::test_it_produces_exactly_one_warning_named_for_its_class"
        status: pass
    human_judgment: false
  - id: D9
    description: "The three suites and the linter are green at phase close, and the three SYNC boxes were checked only after that"
    verification:
      - kind: other
        ref: "uv run pytest -q → 761 passed; -m e2e → 194 passed; -m schema → 114 passed; -m '' → 1069 passed; ruff check src tests → exit 0"
        status: pass
      - kind: other
        ref: "git diff .planning/REQUIREMENTS.md | grep -c '^+- \\[x\\]' → 3, with 3 insertions and 3 deletions total in the file"
        status: pass
    human_judgment: false
  - id: D10
    description: "Sync neither blocks nor is blocked by a genuinely concurrent quota charge or grant flip"
    verification: []
    human_judgment: true
    rationale: "Still never observed live, and still not observable in this harness. Inherited unchanged from 38-03's D8 and left as WINDOWS.md entry 9, open and unwaived. SYNC-02 is checked on its written text, which does not contain this claim — a reader must not read the checked box as a concurrency observation."

# Metrics
duration: 35min
completed: 2026-09-01
status: complete
---

# Phase 38 Plan 06: The Removal Guards and the Phase Close Summary

**Six syntax-tree guards now fail if the audit subsystem, the single migration or a per-attempt sync event returns — each proven to fail by injecting the thing it forbids — and all three SYNC requirements are checked against 1069 passing tests and a clean linter, with the one claim that is still not observable named rather than absorbed into a checkmark.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-09-01
- **Tasks:** 2
- **Files:** 1 created, 1 modified

## Both pytest selections, run and reported

The repository's `addopts` is `-m 'not e2e and not schema'`, so a bare run silently deselects every e2e and schema case. Both selections were run.

| Command | Collected | Result |
|---|---|---|
| `uv run pytest -q` | 761 | **761 passed**, 308 deselected |
| `uv run pytest -m e2e -q` | 194 | **194 passed**, 875 deselected |
| `uv run pytest -m schema -q` | 114 | **114 passed**, 955 deselected |
| `uv run pytest -q -m 'e2e or schema'` | 308 | **308 passed**, 761 deselected |
| `uv run pytest -q -m ""` | 1069 | **1069 passed**, 0 deselected |
| `uv run ruff check src tests` | — | **All checks passed** (exit 0) |
| `uv run pytest tests/unit/test_sync_audit_removal.py -v` | 6 | **6 passed** |
| `uv run pytest tests/unit/test_docstring_bar.py` | 9 | **9 passed** — the bar of 0 holds on every root |

The default suite's **761** is **+6** against 38-03's 755, which is exactly this plan's six guards and nothing else. The e2e/schema selection's **308** is unchanged from 38-03.

### The delta against the 1016 recorded in STATE.md, fully accounted

`STATE.md:50` records **1016 passing with markers cleared** at the close of Phase 37.5. The same invocation now reports **1069** — a delta of **+53**, which decomposes exactly:

| Source | Node ids | Where |
|---|---|---|
| `188acd8` — the CR-02 security fix, landed after 37.5's count was recorded and before Phase 38's first commit | +2 | `tests/unit/test_exception_handlers.py` |
| 38-01 (the tracer) | +15 | 12 in `test_sync_resolver.py`, 2 in `test_app_wiring.py`, 1 in `test_sync.py` |
| 38-02 (the service branches) | +17 | `test_sync_resolver.py` |
| 38-03 (the e2e proof) | +13 | `test_sync.py` |
| 38-06 (this plan) | +6 | `test_sync_audit_removal.py` |
| **Total** | **+53** | 1016 → 1069 |

Cross-checked structurally: `git diff --stat c3037ab HEAD -- tests/` shows Phase 38 touched exactly four test files, and the three it created collect 29 + 14 + 6 = 49, plus the 2 added to `test_app_wiring.py` = **51**, which is +53 less the 2 from `188acd8`.

## The three SYNC requirements: each decided, none left undecided

Three consecutive plans declined to check SYNC-01 and SYNC-02, and 38-03 flagged the cumulative effect. **All three boxes are now checked**, in commit `3614745`, after the suites were green. Here is what each is checked on, clause by clause. Nothing is checked on evidence that does not exist.

### SYNC-01 — CHECKED

*"The endpoint returns the effective grant, `current_period`, `monthly_used`, and stored `identity_provider`, all derived from one captured evaluation time."*

| Clause | Evidence |
|---|---|
| returns the effective grant | `tests/e2e/test_sync.py::TestTheEntitlementHappyPath::test_a_linked_caller_reads_the_entitlement_it_holds` (e2e, real PostgreSQL); the zero-grant answer at `TestTwoAbsentEntitlementsAreIndistinguishable::test_the_body_they_share_is_the_no_grant_answer`; the predicate boundaries at `tests/unit/test_sync_resolver.py::TestThePredicateBoundaries` (5 cases) |
| `current_period` | `tests/unit/test_sync_resolver.py::TestTheZeroGrantAnswer::test_the_period_is_the_captured_instant_and_is_never_null` |
| `monthly_used` | `tests/unit/test_sync_resolver.py::TestTheRolloverIsComputedNeverWritten::test_a_stale_period_reports_zero_for_the_current_period` and `::test_a_matching_period_reports_the_stored_count` |
| stored `identity_provider` | `tests/e2e/test_sync.py::TestTheProviderComesFromTheStoredColumn::test_a_non_google_caller_reports_its_stored_provider` — asserted against the value read back out of `core.external_identities`, not against the fixture's argument. This was the last missing clause and 38-03 closed it. |
| all derived from one captured evaluation time | Structural, and cited as such: `app/dependencies.py::get_sync_service` passes `evaluated_at=datetime.now(UTC)` exactly once, `services/sync.py` contains no clock read at all, and the period is derived from that instant in the single line `period = self.evaluated_at.strftime("%Y-%m")`. `TestTheZeroGrantAnswer::test_the_period_is_the_captured_instant_and_is_never_null` asserts the wire value equals that instant's period, and `TestThePredicateBoundaries` asserts the grant statement's bounds are that same instant. |

The last clause is proven structurally rather than by observation, and always will be: an e2e test cannot distinguish one clock read from three a microsecond apart. That is stated here rather than glossed.

### SYNC-02 — CHECKED, on its written text

*"The endpoint is strictly read-only — no rollover, no grant-row flip, no invariant repair, no profile write."*

| Clause | Evidence |
|---|---|
| no rollover | `tests/unit/test_sync_resolver.py::TestTheRolloverIsComputedNeverWritten` (4 cases) and `tests/e2e/test_sync.py::TestTheRequestChangesNothing::test_a_stale_period_grant_is_left_untouched` — the e2e case fault-injected in 38-03 by reintroducing quota's rollover assignment, which failed exactly the two stale-period cases |
| no grant-row flip | `tests/e2e/test_sync.py::TestTheRequestChangesNothing` — raw `SELECT *` column-level snapshots of `core.access_grants` before and after, across three seeded states, covering the four `GENERATED ALWAYS AS STORED` columns the ORM leaves unmapped |
| no invariant repair | The three fail-closed branches raise instead of repairing: `TestTheUsageRowIsMissing`, `TestMultipleEffectiveGrants`, `TestTheTierHasNoRow` (unit) and `tests/e2e/test_sync.py::TestTheFailClosedFiveHundred::test_a_grant_with_no_usage_row_is_an_opaque_500` (e2e) |
| no profile write | `TestTheRequestChangesNothing` snapshots `core.users` too; `tests/unit/test_sync_resolver.py::TestThePredicateBoundaries::test_no_user_row_is_read_by_any_statement` |
| (supporting) the session is left clean, so `get_db`'s exit commit is a no-op | `tests/unit/test_sync_resolver.py::TestSyncTakesNoLock::test_the_request_session_is_left_clean` |

**What SYNC-02 is NOT checked on, stated so no reader infers it.** The no-lock claim **under genuine concurrency** — that sync neither blocks nor is blocked by a concurrent quota charge or grant flip — has never been observed live. It rests on the compiled statements carrying no `FOR UPDATE` (`TestSyncTakesNoLock`, 5 cases) plus the tables being provably unchanged. That claim **is not in SYNC-02's text**: the requirement names four writes and prohibits them, and each of those four has a citation above. It came from the ROADMAP framing and 38-01's `must_haves`, not from the requirement. Checking the box is therefore a claim about the four clauses, not about concurrency.

**`WINDOWS.md` entry 9 stays open and is deliberately not waived.** 38-03 handed this plan the choice. The call: leave it open. Waiving it would buy a cleaner ship gate at the cost of the only durable record that observing this claim requires a harness with committed fixtures and manual cleanup — a different harness than `_db_transaction` provides. Six other entries block `/gsd:ship` regardless, so the waiver buys nothing today and costs the reminder tomorrow.

### SYNC-03 — CHECKED

*"Every `/auth/sync` attempt earns exactly one `request` line … and every rejection additionally earns one WARNING named for its exception class … The endpoint writes no durable row and adds no per-attempt telemetry beyond those lines."*

| Clause | Evidence |
|---|---|
| exactly one `request` line per attempt, with status code and duration | `tests/unit/test_logging.py::test_middleware_logs_request_on_response` — asserts `len(request_logs) == 1`, `status_code`, `duration_ms`. Its control `test_middleware_excludes_health_ready` shows exclusion is what suppresses the line. `test_request_id_bound_in_context` covers the bound `request_id`; `method` and `path` are bound in the same `bind_contextvars` call. |
| …for `/auth/sync` specifically | **Structural, not run.** `logs.py`'s `_EXCLUDED_PATHS` is `frozenset({"/health/ready"})`, so `/auth/sync` is outside it. No test names `/auth/sync` against that set. This is the one clause in the three requirements whose evidence is read rather than executed, and it is recorded in the coverage block as `human_judgment: true` (D7). |
| one WARNING named for its exception class per rejection | `tests/unit/test_exception_handlers.py::TestTheHandlerRecordsTheRejectionExactlyOnce::test_the_event_name_is_the_snake_cased_class_name`, and `TestAnAccountUnavailableArmTravelsTheWholeErrorPath::test_it_produces_exactly_one_warning_named_for_its_class` |
| writes no durable row | `tests/e2e/test_sync.py::TestTheRequestChangesNothing` (three whole-table counts plus column-level snapshots), and this plan's D1–D3 guards over the schema expectation and the migration |
| adds no per-attempt telemetry beyond those lines | This plan's D4–D6: no logging import or call in `services/sync.py`, no `auth_sync`/`auth_events` string anywhere under `src/`, and a control proving the walk actually scans |
| the decision is recorded | 38-05's dated amendment under SYNC-03 in `REQUIREMENTS.md` — option (b), 2026-09-01 |

## What this phase deliberately did not build

**Nothing was rebuilt, and the list of what was not built is the point.** No `audit.auth_events` table went back into `migrations/20260818_01_initial-release.sql`, which is byte-identical and whose last touching commit is `5aa7793` from Phase 37.4. No audit writer, no HMAC actor hashing, no key versioning, no `{schema_version, context, verification, resolved, mutation, failure}` details shape. No call site in the route or the service. No `auth_sync_succeeded` event or any other per-attempt event — `services/sync.py` imports no logging library and makes no logging call. No counter metric, in a project that already deleted its hand-rolled `RejectionCounter` in Phase 36 D-15. No route-to-operation metadata readable before the barrier.

**Two records exist in their place, and they were already there.** `RequestLoggingMiddleware` in `api/logs.py` writes one `request` line per attempt carrying the request id, method, path, status code and duration, and `/auth/sync` is not among its `_EXCLUDED_PATHS`. Every rejection additionally earns one WARNING from `app/error_handlers.py::app_error_handler`, named for the snake-cased exception class — `invalid_external_jwt`, `pre_auth_identity_not_allowed`, `historical_identity`, `blocked_user` — because `AppError.log_level` defaults to `WARNING`. A second line announcing that a 200 succeeded would be duplication, which is why D-02 declined it.

## The four ROADMAP success criteria, each mapped to named evidence

| # | Criterion | Proving evidence |
|---|---|---|
| 1 | Grant, `current_period` and `monthly_used` all derive from one evaluation time and match what quota enforcement would independently act on at the same instant | **Split, and honestly so.** *The values:* `tests/e2e/test_sync.py::TestTheEntitlementHappyPath::test_a_linked_caller_reads_the_entitlement_it_holds` plus `TestTwoAbsentEntitlementsAreIndistinguishable` and `TestTheRolloverIsComputedNeverWritten`. *The agreement with quota:* `tests/unit/test_sync_resolver.py::TestThePredicateIsOneDefinition::test_the_grant_reads_differ_only_by_the_lock_clause` and `::test_the_usage_reads_differ_only_by_the_lock_clause` — the locking and non-locking reads compile to identical PostgreSQL apart from the trailing `FOR UPDATE`, which is the strongest form this claim has: not two implementations agreeing, one definition used twice. *The one instant:* **no single proving node id exists, and none can.** It is structural — one `datetime.now(UTC)` in `get_sync_service`, no clock read below it — supported by `TestTheZeroGrantAnswer::test_the_period_is_the_captured_instant_and_is_never_null` and `TestThePredicateBoundaries`. |
| 2 | Zero effective grants and a lapsed grant return byte-identical responses | **Proven, e2e.** `tests/e2e/test_sync.py::TestTwoAbsentEntitlementsAreIndistinguishable::test_no_grant_and_a_lapsed_grant_return_the_same_body` compares the two parsed bodies *to each other* as whole dicts, so shared drift cannot pass; `::test_the_lapsed_answer_names_neither_revoked_nor_expired`; and `TestTheWindowIsWhyTheGrantIsAbsent` proves the exclusion is the predicate's doing, with a present control and 38-03's fault injection. |
| 3 | Table state is unchanged across a request — verified by comparing `core.*` before and after | **Proven, e2e.** `tests/e2e/test_sync.py::TestTheRequestChangesNothing` (4 cases) — raw `SELECT *` snapshots of `core.access_grants`, `core.user_monthly_usage` and `core.users` plus three whole-table counts, across three seeded states including the stale-period branch, fault-injected in 38-03 by reintroducing quota's rollover assignment. |
| 4 | No durable audit row on any path, no per-attempt telemetry beyond the middleware line and the rejection WARNING, with the decision recorded in `REQUIREMENTS.md` and the removal made in `SHARED-INVARIANTS.md` | **Proven, in three parts.** *No durable row and no new telemetry:* this plan's six guards, `tests/unit/test_sync_audit_removal.py` (all 6, each fault-injected). *The decision recorded:* the dated option-(b) amendment under SYNC-03 in `.planning/REQUIREMENTS.md`, written by 38-05 (`12cd458`). *The removal made:* `grep -c -i audit /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` → **0**, and the section list runs Identity → Barrier → Wire contract → Tokens → Fail-closed defaults → Locks → Grants → Errors → Rate limits → Global deletions, with no § "Audit". Verified read-only; that edit lives uncommitted in the parent working tree by design and was not touched. |

**One claim named unproven rather than assigned loosely:** the concurrency half of the phase's `must_haves` — that sync neither blocks nor is blocked by a live concurrent charge — has no proving node id, is not part of any of the four criteria as written, and remains `WINDOWS.md` entry 9.

## Task Commits

1. **Task 1: The executable guards that nothing was rebuilt** — `7f308d4` — `tests/unit/test_sync_audit_removal.py`, +105 lines, 6 node ids
2. **Task 2: Close the phase against green suites** — `3614745` — `.planning/REQUIREMENTS.md`, +3/−3, the three SYNC boxes

## Files Created/Modified

- **Created** `tests/unit/test_sync_audit_removal.py` — 105 lines, 4650 bytes. Six classes, one test each, three module-level `ast` helpers (`_expected_audit_tables`, `_source_strings`, `_imported_roots`). Placed in `tests/unit/` so it runs in the default invocation; a guard behind a deselected marker is a guard that does not run.
- **Modified** `.planning/REQUIREMENTS.md` — three checkboxes, nothing else. `git diff --stat` reports exactly 3 insertions and 3 deletions.
- **Not modified:** `git diff --stat src/ migrations/ tests/schema/` is empty across the whole plan, and `git log --oneline -1 -- migrations/` is `5aa7793` from Phase 37.4 — no Phase 38 commit touches it.

## Fault injection, one per guard — seven injections for six guards

Every guard was injected, not only the three the plan named. A guard trusted without injection is the failure this module exists to prevent.

| # | Injection | Observed | Reverted |
|---|---|---|---|
| 1 | `"auth_events"` added to `EXPECTED_AUDIT_TABLES` | `test_the_expectation_names_only_subscription_events` failed: `Extra items in the left set: 'auth_events'` | `git checkout --` |
| 2 | `-- AUTH_EVENTS injection probe` appended to the migration | `test_no_sql_file_mentions_either_deleted_name` failed on the **uppercase** form, proving case-insensitivity | `git checkout --` |
| 3 | Second empty `migrations/20260902_02_probe.sql` created | `test_exactly_one_sql_file_exists_under_migrations` failed | file removed |
| 4A | `import structlog` + `structlog.get_logger().info("auth_sync_succeeded")` in `services/sync.py` | `test_it_imports_no_logging_library_and_makes_no_logging_call` failed on the **import** arm, and `test_no_source_string_names_a_sync_event_or_the_deleted_table` failed on `'auth_sync_succeeded'` — injections 4 and 5 in one | `git checkout --` |
| 4B | `self.grants_db.warning("x")` with **no** import | the same case failed on the **call** arm: `assert ['warning'] == []` | `git checkout --` |
| 6 | `SRC` narrowed to an empty directory | `test_the_walk_finds_an_event_name_quota_is_known_to_emit` failed: `assert 'quota_rejected' in []` | edit reverted |

**Injection 4B exists because 4A did not prove what it appeared to.** The guard asserts the import set first and the call list second, so an injection carrying both short-circuits on the import and the call assertion is never reached. Running a call with no import proved the second assertion independently. Worth inheriting: a two-assertion test needs two injections, or one of its assertions is untested.

**Injection 6 is the one that justifies the control's existence.** With `SRC` pointing at an empty directory, `test_no_source_string_names_a_sync_event_or_the_deleted_table` **passed** — it found no offenders because it looked nowhere. Only the control failed. Without it, narrowing or breaking the walk would turn D5 into a permanently green assertion about nothing.

## Decisions Made

**Six classes, one test each.** The plan's action reads *"Each behaviour above becomes one test in a class whose one-line docstring states the rule it defends."* Read literally, that gives one class per rule, which is what was built — each docstring states exactly one rule, and the acceptance criterion of exactly 6 node ids is satisfied. Grouping D5 with its control D6 in one class would also have given 6 node ids, but would have forced a two-rule docstring.

**Syntax trees everywhere, never a substring scan of raw Python.** `_source_strings` collects `ast.Constant` string values, so a comment mentioning `auth_events` cannot fail a check and a name appearing only in a comment cannot satisfy one. The one deliberate exception is the migration guard, which scans raw SQL text — SQL has no Python syntax tree, and a SQL comment naming the deleted table is itself a reason to look.

**The migration guard pins the filename, not just the count.** `test_exactly_one_sql_file_exists_under_migrations` asserts the list equals `["20260818_01_initial-release.sql"]`. A rebuild that replaces the single migration under a new id — the exact move D-01 names as the cost of reversal — fails this too, where a bare count of 1 would not.

**All three boxes checked; the gap recorded rather than absorbed.** See the SYNC sections above. The alternative — leaving SYNC-01 and SYNC-02 open for a fourth consecutive plan — was the outcome 38-03 explicitly warned against, and would have left the phase reading as untouched while carrying four plans of evidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Copied the gitignored `.env` into the worktree**

- **Found during:** Task 2 precondition check
- **Issue:** `.env` is gitignored, so this fresh worktree had no `DB_*` values or Firebase test credentials; the e2e and schema suites could not run at all, and reporting a deselected suite as green is precisely what the precondition forbids.
- **Fix:** copied `/home/init/native-speaker/ns-api-gateway/.env` into the worktree root — the same fix 38-01, 38-02 and 38-03 each recorded.
- **Files modified:** none tracked; the file stays gitignored and is in no commit.
- **Verification:** `uv run pytest -m e2e tests/e2e/test_health.py -q` → 1 passed, confirming PostgreSQL is reachable and the fixtures resolve.

### Scope notes

**Four fault injections beyond the three the plan named.** The plan's acceptance criteria name three injections plus the control. Guards D2 and D3 got their own, and D4 got a second, because the plan's own words are *"Fault injection recorded in the summary, one per guard"*. This adds evidence, not scope: no test was added or altered.

---

**Total deviations:** 1 auto-fixed (environment, blocking), 0 behavioural
**Impact on plan:** none — no scope added, no task altered, no production code changed.

## Issues Encountered

**None blocking.** One observation worth passing on: the `-m ""` invocation is the only way to reproduce the 1016 figure `STATE.md` records, because `addopts` deselects e2e and schema and neither `-m e2e` nor `-m schema` alone can reach the total. Any future plan comparing against a recorded count should confirm which selection produced it before reading a delta as a regression — 761 against 1016 looks like a catastrophic loss and is nothing of the kind.

## Known Stubs

**None.** No `TODO`, `FIXME`, skipped test, `xfail` or placeholder was introduced. Every `<verify>` in the plan was run and its output is reported above; none was deferred.

Two gaps are deliberately **not** hidden here:

- **`WINDOWS.md` entry 9** (`unmet-truth`, phase 38, open, unwaived) — the live-concurrency observation. Disposition decided by this plan: **leave open**, reasoning under SYNC-02 above. No new ledger entry was appended, because this plan introduced no new defect; entry 9 already carries the claim.
- **D7's second half** — that `/auth/sync` specifically is outside `_EXCLUDED_PATHS` is read from a one-member frozenset rather than asserted by a test. Recorded in the coverage block as `human_judgment: true`. A future plan wanting this executable would assert `"/auth/sync" not in _EXCLUDED_PATHS`, which is one line.

## Threat Flags

None — no new surface. This plan adds one test module and edits three checkboxes; it opens no trust boundary and touches no production file. All three `mitigate` dispositions in the plan's threat register were implemented and asserted:

- **T-38-17** (disclosure through structured-log labels on the sync path) — `TestTheSyncServiceEmitsNoEventOfItsOwn` fails if a logging call or import appears in the module, so no per-account value can reach a label from it. No user id, external subject or provider value was put into any label; none was added at all.
- **T-38-18** (repudiation from the absent durable record) — accepted milestone-wide under D-01, unchanged. The middleware line and the rejection WARNING are named in the summary as the records that exist.
- **T-38-19** (tampering by a later phase reintroducing the audit table) — D1, D2 and D3 assert the one-member expectation, the absent name and the single migration file, each proven to fail by injection before being trusted.

No package-manager install was performed, so no package-legitimacy gate applied.

## Verification

| Check | Result |
|---|---|
| `uv run pytest tests/unit/test_sync_audit_removal.py -v` | **6 passed**, exactly 6 node ids collected |
| `uv run pytest -q` | **761 passed**, 308 deselected |
| `uv run pytest -m e2e -q` | **194 passed**, 875 deselected |
| `uv run pytest -m schema -q` | **114 passed**, 955 deselected |
| `uv run pytest -q -m 'e2e or schema'` | **308 passed**, 761 deselected |
| `uv run pytest -q -m ""` | **1069 passed**, 0 deselected |
| `uv run ruff check src tests` | All checks passed (exit 0) |
| `uv run pytest tests/unit/test_docstring_bar.py` | 9 passed — bar of 0 holds on every root |
| `git diff --stat migrations/` | empty |
| `git log --oneline -1 -- migrations/` | `5aa7793` (Phase 37.4) — no Phase 38 commit |
| `git diff --stat tests/schema/` | empty |
| `git diff --stat src/` | empty |
| `git diff .planning/REQUIREMENTS.md \| grep -c '^+- \[x\]'` | **3**, with 3 insertions / 3 deletions in the whole file |
| `grep -c -i audit` on `SHARED-INVARIANTS.md` | **0** — read-only check; the parent working tree was not modified |
| `.planning/STATE.md`, `.planning/ROADMAP.md` | untouched — the orchestrator owns them |

## User Setup Required

None. Note for a fresh worktree: `.env` is gitignored and must be copied in before the e2e or schema suites can run, and those suites must be selected explicitly with `-m` or `addopts` will deselect all of them.

## Next Phase Readiness

**Phase 38 is closed.** `POST /auth/sync` is proven end to end against real PostgreSQL on every path a real caller can reach, its three requirements are checked with clause-level citations, all four ROADMAP success criteria are mapped to named evidence, and the removal the milestone chose is now guarded by six tests that fail if it is undone.

**Ready for:**
- **Phase 39 (`GET /users/me`)** — inherits `TestTheProviderComesFromTheStoredColumn` as the case its own `identity_provider` must agree with, and the `_stored_provider` helper to reuse. PROF-02's audit clause is already trivially true and carries no obligation to build a writer or a counter.
- **Phases 43 and 46** — `APPLEHOOK-02`, `PLAYHOOK-03` and `SIGNOUT-02` each still own their half of the audit decision. Phase 38 settled only its own; 38-05's sibling entries say which half each still carries. `SIGNOUT-02` in particular must weigh it differently: a sign-out-all that fails closed leaves *nothing* recording the attempt, which is a different exposure from a read-only sync losing attempt telemetry.

**Blockers/concerns:**
- **`WINDOWS.md` entry 9 is open and unwaived by decision.** With `workflow.windows_enforce` on it is one of seven open entries blocking `/gsd:ship`. It is a harness limitation, not an endpoint defect. Resolving it needs committed fixtures and manual cleanup on a second connection — a different e2e harness, and a plan of its own.
- **Six other `WINDOWS.md` entries from phases 36 and 37 remain open** and are untouched by this phase. They will need triage before ship regardless of entry 9's disposition.

## Self-Check: PASSED

- `tests/unit/test_sync_audit_removal.py` exists on disk (105 lines, 4650 bytes) and collects 6 node ids.
- `.planning/phases/38-post-auth-sync/38-06-SUMMARY.md` is this file.
- Both task commits are present on `worktree-agent-a56e6cbd8375797c9`: `7f308d4` and `3614745`.
- `git diff --stat src/ migrations/ tests/schema/` is empty against the plan's base commit `ef27fc8`.
- `.planning/STATE.md` and `.planning/ROADMAP.md` are unmodified; no mutating git command was run against the parent repository.

---
*Phase: 38-post-auth-sync*
*Completed: 2026-09-01*
