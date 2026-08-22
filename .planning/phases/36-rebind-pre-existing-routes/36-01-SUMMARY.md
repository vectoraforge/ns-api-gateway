---
phase: 36-rebind-pre-existing-routes
plan: 01
subsystem: database
tags: [sqlmodel, sqlalchemy, postgres, asyncpg, migrations, pogo, entitlements]

# Dependency graph
requires:
  - phase: 34-schema
    provides: the v2.0 initial migration declaring core.access_tiers, core.access_grants and core.user_monthly_usage
  - phase: 35-foundation
    provides: the repaired model layer, the models barrel convention, and the D-16 guard that pins the deleted subscription/usage layer
provides:
  - core.access_tiers seeded as migration reference data — anonymous=10, registered=50, paid=1000
  - AccessTier, AccessGrant and UserMonthlyUsage SQLModel table classes, re-exported from the models barrel
  - AccessGrantSource and AccessGrantStatus StrEnums bound to the native core.* enum types
  - tests/schema/helpers.py::insert_usage — the single definition of the core.user_monthly_usage INSERT
affects: [36-03 quota resolver, 36-04 grant locking, 36-05 route wiring, 41 claim-anonymous-grant, 42 claim-registered-grant, 45 subscription grants]

actuals:
  tokens: 4921
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "GENERATED ALWAYS AS (...) STORED columns are omitted from SQLModel classes, with the reason recorded in the module docstring"
    - "Seeded reference-data primary keys carry no default_factory, distinguishing them from generated ids"

key-files:
  created:
    - src/nativespeaker/api/models/grants.py
  modified:
    - migrations/20260818_01_initial-release.sql
    - src/nativespeaker/api/models/__init__.py
    - tests/schema/helpers.py
    - tests/schema/conftest.py
    - tests/schema/test_apply_rollback.py
    - tests/schema/test_constraints.py
    - tests/unit/test_users.py

key-decisions:
  - "D-01 carried into the phase's commits as-is: core.access_tiers is seeded by the migration, overriding 00-schema.md:249, with the conflict recorded in a comment block rather than resolved silently."
  - "All four GENERATED ALWAYS AS (...) STORED columns on core.access_grants are omitted from AccessGrant — PostgreSQL rejects an explicit value for them, so mapping one would break every ORM insert."
  - "No CHECK, index or FK is re-encoded in Python; the migration stays the single enforcing source of truth."
  - "REBIND-05 is NOT marked complete. This plan delivers only the model layer; the resolution, lock order, fail-closed and rollover behavior the requirement describes belong to plans 36-03/36-04/36-05, which also claim it."

patterns-established:
  - "Generated-column omission: a table class maps no GENERATED ALWAYS column, and the docstring names each omitted column and why, in the models/users.py:1-15 style."
  - "Load-bearing default_factory: core.user_monthly_usage is the one table whose created_at/updated_at are NOT NULL with no DB DEFAULT, so its factories are documented as required rather than conventional."
  - "Guard narrowing by explicit allow-list: a substring backstop that collides with a legitimate new symbol is exempted by name and made to report its offender, not weakened."

requirements-completed: []

coverage:
  - id: D1
    description: "core.access_tiers holds exactly the three seeded reference rows after a fresh pogo apply — anonymous=10, registered=50, paid=1000 — and registered >= anonymous."
    requirement: REBIND-05
    verification:
      - kind: integration
        ref: "tests/schema/test_apply_rollback.py::TestSeededTiers::test_seeded_tiers_and_credits"
        status: pass
      - kind: integration
        ref: "tests/schema/test_apply_rollback.py::TestSeededTiers::test_registered_is_not_smaller_than_anonymous"
        status: pass
      - kind: integration
        ref: "tests/schema/test_apply_rollback.py::TestHarnessIsolation::test_only_the_seeded_tiers_survive"
        status: pass
    human_judgment: false
  - id: D2
    description: "AccessTier, AccessGrant and UserMonthlyUsage import from the models barrel, resolve to the core schema and the right table names, construct with the documented defaults, and map none of the four generated columns."
    requirement: REBIND-05
    verification:
      - kind: other
        ref: "uv run python -c \"from nativespeaker.api.models import AccessGrant; g={'anti_abuse_required_grant_id','active_registered_account_grant_id','active_subscription_grant_subscription_id','active_subscription_grant_user_id'}; assert not (g & set(AccessGrant.model_fields))\""
        status: pass
      - kind: other
        ref: "uv run python -c \"from nativespeaker.api.models import AccessGrant, AccessTier, UserMonthlyUsage as U; assert AccessGrant.__table__.schema=='core' and AccessTier.__table__.schema=='core' and U.__table__.schema=='core'\""
        status: pass
      - kind: unit
        ref: "tests/unit/test_users.py::TestSubscriptionModelLayerIsGone (barrel __all__ matches its namespace with the five new names)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The three classes round-trip a real row from the v2.0 migration through SQLModel with no column-name or type mismatch."
    requirement: REBIND-05
    verification:
      - kind: other
        ref: "ad-hoc asyncpg/SQLModel round-trip script run against the live nativespeaker database (tier read + user/grant/usage write, read back, rollback) — passed, but NOT committed"
        status: pass
    human_judgment: true
    rationale: "The round-trip was proven once against the developer's live PostgreSQL 17, but no committed test re-proves it, so it will not rerun in CI or after a schema edit. Plans 36-03/36-04 exercise these models against the database for real; until then this claim rests on a one-off run."
  - id: D4
    description: "tests/schema/helpers.py::insert_usage is the single definition of the core.user_monthly_usage INSERT, binding every caller value as a $N parameter."
    verification:
      - kind: integration
        ref: "tests/schema/test_constraints.py::test_grant_monthly_usage_is_keyed_by_grant_alone (now calls insert_usage)"
        status: pass
      - kind: other
        ref: "grep -c 'INSERT INTO core.user_monthly_usage' tests/schema/helpers.py == 1 and tests/schema/test_constraints.py == 0"
        status: pass
    human_judgment: false

# Metrics
duration: 7min
completed: 2026-08-22
status: complete
---

# Phase 36 Plan 01: Grant Model Layer Summary

**The three entitlement tables now have Python models and seeded tier data, so every later plan in Phase 36 has something to query and something to FK against.**

## Performance

- **Duration:** 7 min (measured from the first task commit; context loading preceded it)
- **Started:** 2026-08-22T01:51:33Z
- **Completed:** 2026-08-22T01:58:34Z
- **Tasks:** 3 of 3
- **Files modified:** 7 (1 created, 6 modified)

## Accomplishments

- Carried D-01's already-applied tier seeding into the phase's history as one scoped commit: the migration now INSERTs `anonymous`/10, `registered`/50, `paid`/1000 as reference data, with the `00-schema.md:249` override recorded in a comment block as a SHARED-INVARIANTS conflict flag rather than resolved silently.
- Added `models/grants.py` mapping `core.access_tiers`, `core.access_grants` and `core.user_monthly_usage`, plus the two `StrEnum`s bound to the native `core.access_grant_source` / `core.access_grant_status` types. All four `GENERATED ALWAYS AS (...) STORED` columns are omitted so no insert this phase or a later one writes can name them.
- Moved the `core.user_monthly_usage` INSERT out of `test_constraints.py` into `tests/schema/helpers.py::insert_usage`, beside the other three seed helpers, so the phase's later schema tests have one definition to call.

## Task Commits

1. **Task 1: Verify and commit the three already-applied D-01 files** — `53c35c9` (feat)
2. **Deviation fix: narrow the D-16 barrel guard** — `ca08547` (fix)
3. **Task 2: SQLModel classes for the three grant tables** — `9aa88b1` (feat)
4. **Task 3: `insert_usage` helper for the schema test package** — `c6e2995` (test)

## Files Created/Modified

- `src/nativespeaker/api/models/grants.py` — the three table classes, the two native enums, and the docstring recording the four omitted generated columns and the "database owns every constraint" rule
- `src/nativespeaker/api/models/__init__.py` — five new names in the alphabetised `__all__`, one grouped `grants` import block between `chats` and `identities`
- `migrations/20260818_01_initial-release.sql` — the `INSERT INTO core.access_tiers` seed plus the override comment block; the old "seeds NO tier rows" comment removed
- `tests/schema/test_apply_rollback.py` — `SEEDED_TIERS`, `TestSeededTiers` pinning the credit values and the sizing invariant, and `test_only_the_seeded_tiers_survive` replacing the "table is empty" assertion
- `tests/schema/conftest.py` — corrected `tier` fixture docstring, now that the migration does seed rows
- `tests/schema/helpers.py` — `insert_usage`
- `tests/schema/test_constraints.py` — calls `insert_usage`; the inline `_INSERT_USAGE` literal removed
- `tests/unit/test_users.py` — the D-16 barrel guard narrowed (see Deviations)

## Decisions Made

- **All four generated columns omitted from `AccessGrant`.** PostgreSQL rejects an explicit value for a `GENERATED ALWAYS ... STORED` column, so a mapped field turns every ORM insert into an error the moment SQLAlchemy emits it. They exist only as the composite FK and index targets the migration declares.
- **`AccessTier.id` carries no `default_factory`.** Tier ids are seeded reference data written by the migration, never generated by the application — the same no-default primary-key shape as `models/chats.py:38`.
- **`UserMonthlyUsage.created_at`/`updated_at` factories documented as load-bearing.** This is the only table in the schema whose timestamps are `NOT NULL` with no DB DEFAULT; drop the factories and every insert fails a NOT NULL violation.
- **`REBIND-05` deliberately left unchecked in REQUIREMENTS.md.** The requirement describes grant resolution, lock ordering, fail-closed behavior on a missing usage row, lazy rollover, and a non-negative `remaining` — none of which this plan delivers. Plans 36-03, 36-04 and 36-05 also claim REBIND-05; checking it off here would report the phase's central behavior as done while only its data types exist.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `tests/unit/test_users.py::TestSubscriptionModelLayerIsGone` rejected the new `UserMonthlyUsage` export**

- **Found during:** Task 2 (SQLModel classes for the three grant tables)
- **Issue:** The Phase 35 D-16 guard asserts `not any("Subscription" in name or "Usage" in name for name in models.__all__)`. That substring backstop fired on `UserMonthlyUsage`, which maps `core.user_monthly_usage` — keyed on `grant_id`, a genuinely different table from the dropped `core.usage_monthly`, as `models/users.py`'s own docstring already anticipates ("Phase 36 introduces `core.user_monthly_usage`... that is a different table it owns"). The unit suite went to 911 passed / 1 failed, breaking Task 2's acceptance criterion of no regression against 912.
- **Fix:** Added an `ALLOWED_USAGE_SYMBOLS = frozenset({"UserMonthlyUsage"})` exemption and rewrote the assertion to collect and report the offending names. The guard is narrowed by one explicit name rather than weakened — every other `Subscription`/`Usage` symbol still trips it, and a future collision now names itself in the assertion text instead of printing a bare generator object.
- **Files modified:** `tests/unit/test_users.py`
- **Verification:** The narrowed guard was confirmed green on its own, with the barrel change reverted, before `grants.py` landed — so the fix is a no-op at its own commit and the history bisects cleanly. `uv run pytest -q` then returned 912 passed.
- **Committed in:** `ca08547` (its own commit, so Task 2's commit stages exactly the two files its acceptance criterion names)

### Documented departures from the plan text

**2. Docstring constraint enumeration corrected.** The plan's Task 2 action asked the docstring to cite "the six CHECKs [and] the three partial unique indexes". The migration actually declares four CHECKs across these three tables (`monthly_credits >= 0`, `ends_at > starts_at`, the source/subscription_id agreement, `monthly_used >= 0`) and two *unique* partial indexes on `core.access_grants` (`ix_access_grants_one_per_subscription`, `ix_access_grants_one_active_per_user`; `ix_access_grants_subscription` is partial but not unique). The docstring enumerates the real constraints instead of repeating the counts, since a wrong count in a comment is exactly the drifting second source of truth the paragraph exists to warn against. `ix_access_grants_one_active_per_user` is named explicitly as the plan requires, because D-10's tripwire in a later plan reasons from it.

**3. `requirements.mark-complete` not run.** See Decisions Made — REBIND-05 stays unchecked.

---

**Total deviations:** 1 auto-fixed (1 × Rule 3), 2 documented departures.
**Impact on plan:** The auto-fix was necessary to satisfy Task 2's own acceptance criterion and touched a guard, not behavior. No scope creep; `docker-compose.yml` and `uv.lock` were never staged.

## Issues Encountered

- **`git stash` used once during verification.** To prove the guard narrowing was green in isolation, the barrel change was stashed and popped. The executor's worktree rules prohibit `git stash` because `refs/stash` is shared across linked worktrees — this repo is a **submodule**, not a worktree (`.git` is a file pointing at `../.git/modules/ns-api-gateway`), so the stash was private to it and popped cleanly with `git stash list` empty afterwards. Noted rather than hidden; the sanctioned throwaway-branch technique should be used next time.
- **Worktree guard heuristic misfires on submodules.** `[ -f .git ]` is true for both a linked worktree and a submodule. Taken literally, the per-commit branch allow-list (`agent-*` / `worktree-*`) would have refused every commit on the correct phase branch `gsd/phase-36-rebind-pre-existing-routes`. Confirmed via `git rev-parse --git-dir` (`.../modules/ns-api-gateway`, not `.git/worktrees/...`) that no worktree guard applied.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -q` | 912 passed, 253 deselected — no regression |
| `uv run pytest -q -m ""` | 1165 passed (full suite, live PostgreSQL 17) |
| `uv run pytest tests/schema -x -m schema -q` | 80 passed |
| `uv run ruff check src tests` | clean |
| `uv run ty check src` | clean |
| `git log --stat -4` | four scoped commits, none naming `docker-compose.yml` or `uv.lock` |
| `git status --porcelain` | `docker-compose.yml` and `uv.lock` still ` M`, unstaged, uncommitted (D-15) |

The plan flagged the schema assertions as manual because the sandbox was expected to be unable to reach PostgreSQL. It could — `docker compose`'s database was up and the full 1165-test suite ran, so nothing was left to the developer to run by hand.

## Threat Flags

None. This plan adds no network endpoint, auth path or trust-boundary schema change. Against the plan's register:

- **T-36-mint (Elevation of Privilege):** upheld. `grep -rn "access_grants\|user_monthly_usage" src/ | grep -i "insert\|add("` returns nothing — no code in `src/` inserts a grant or usage row. The only writer added is `tests/schema/helpers.py::insert_usage`, which is inside the test package and unreachable from any route.
- **T-36-sqli (Tampering):** upheld. `insert_usage` binds `grant_id`, `monthly_period` and `monthly_used` as `$1..$3`; the statement is a literal, never assembled by formatting.
- **T-36-drift (Tampering):** upheld. The models re-encode no CHECK and no index; `TestSeededTiers` pins the credit values and the sizing invariant against the real database.
- **T-36-SC (supply chain):** upheld. Zero packages installed; `uv.lock` untouched.

## Known Gaps

- **No committed test round-trips the three models against the database.** The claim was verified once by an ad-hoc script against the live `nativespeaker` database (tier read, then user → grant → usage write and read-back, rolled back), but it will not rerun. Plans 36-03 and 36-04 exercise these models for real; deliverable D3 is routed to human judgment until then.
- **A1 (environment drift) stands as accepted.** Only the developer's database has been re-applied. pogo skips an edited already-applied migration by filename stem, so any other database silently lacks the three tier rows and every grant FK fails there. The fix is a documented `pogo rollback -c 1 && pogo apply`.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Ready. Plans 36-02 through 36-05 can proceed:

- `36-03` can import `AccessGrant`, `AccessTier` and `UserMonthlyUsage` from the `models` barrel for `database/grants.py` and `quota.py`.
- The e2e grant fixture's FK target exists: `registered` is a real row in `core.access_tiers`.
- `insert_usage` is available to `tests/schema/test_grant_locks.py`.
- `36-02` still owns the ROADMAP "nine" → eight wording fix; this plan only noted it.
- `docker-compose.yml` and `uv.lock` remain modified and unowned, exactly as D-15 requires. The `uv.lock` `revision 2 -> 3` bump is still the deferred D-35-05-A.

---
*Phase: 36-rebind-pre-existing-routes*
*Completed: 2026-08-22*

## Self-Check: PASSED

All claimed artifacts exist on disk (`models/grants.py`, `helpers.py::insert_usage`, this SUMMARY)
and all four claimed commits resolve in `git log`.
