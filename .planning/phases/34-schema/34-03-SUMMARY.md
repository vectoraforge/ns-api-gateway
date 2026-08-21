---
phase: 34-schema
plan: 03
subsystem: testing
tags: [postgres, pytest, pytest-asyncio, asyncpg, pogo-migrate, pg_catalog, introspection]

requires:
  - phase: 34-01
    provides: A reachable PostgreSQL 17.11 server, the five DB_* keys in .env, and a role with working CREATE DATABASE
  - phase: 34-02
    provides: migrations/20260818_01_initial-release.sql as the only migration, applied and rollback-proven structurally
provides:
  - "tests/schema/ -- a schema-conformance package with zero application imports, runnable while the app is broken"
  - "A session fixture that creates a scratch database, applies the real migration in-process, and drops it"
  - "insert_user / insert_tier / insert_grant seed helpers with per-test transaction rollback"
  - "SCHEMA-01 and D-20 proof: exactly one migration file, clean apply, clean pogo rollback"
  - "SCHEMA-07 and SCHEMA-08 proof: exact-set inventory of enums, tables, indexes, predicates, and legacy absences"
  - "A registered `schema` pytest marker, deselected from the default run"
  - ".planning/phases/34-schema/34-INVENTORY-PG17.md -- the PostgreSQL 17 constant capture"
affects: [34-04, 35-foundation, 36-rebind]

actuals:
  tokens: 12325
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Scratch-database session fixture: synchronous @pytest.fixture wrapping asyncio.run, sidestepping asyncio_default_fixture_loop_scope = function"
    - "In-process migration apply via pogo_core.util.testing, never pogo_migrate.testing and never a subprocess"
    - "Exact-set schema introspection assertions with symmetric-difference failure output"

key-files:
  created:
    - .planning/phases/34-schema/34-INVENTORY-PG17.md
    - tests/schema/__init__.py
    - tests/schema/conftest.py
    - tests/schema/helpers.py
    - tests/schema/test_apply_rollback.py
    - tests/schema/test_inventory.py
  modified:
    - pyproject.toml
    - .planning/phases/34-schema/34-VALIDATION.md

key-decisions:
  - "Registered the `schema` marker and extended addopts to -m 'not e2e and not schema' (DIRECTIVE-2), so a bare pytest stays green without PostgreSQL; every schema command now needs -m schema explicitly"
  - "Pinned the predicate assertions to the default search_path ('$user', public) rather than normalizing pg_get_expr output, keeping expected strings literal"
  - "Defaulted DB_NAME to the `postgres` maintenance database rather than .env.example's application database, since the admin connection only issues CREATE/DROP DATABASE"
  - "Proved the rollback on a second scratch database (ns_schema_test_rollback) so it cannot disturb the session fixture's"

patterns-established:
  - "tests/schema/__init__.py roots cross-module imports at tests/, so schema modules import `from schema.helpers import ...`"
  - "Every schema test module declares pytestmark = pytest.mark.schema after its imports"
  - "Database identifiers interpolated into CREATE/DROP DATABASE pass through a lowercase-identifier regex guard; every row value binds as an asyncpg $N parameter"

requirements-completed: [SCHEMA-01, SCHEMA-07, SCHEMA-08]

coverage:
  - id: D1
    description: "migrations/ holds exactly one .sql file, and a from-empty apply produces both the core and audit schemas"
    requirement: SCHEMA-01
    verification:
      - kind: integration
        ref: "tests/schema/test_apply_rollback.py::TestMigrationDirectory::test_exactly_one_sql_file"
        status: pass
      - kind: integration
        ref: "tests/schema/test_apply_rollback.py::TestApply::test_core_and_audit_namespaces_exist"
        status: pass
    human_judgment: false
  - id: D2
    description: "The migration's own rollback section, run through pogo's rollback path, leaves neither core nor audit in pg_namespace and empties _pogo_migration"
    requirement: SCHEMA-01
    verification:
      - kind: integration
        ref: "tests/schema/test_apply_rollback.py::TestRollback::test_pogo_rollback_leaves_neither_schema"
        status: pass
    human_judgment: false
  - id: D3
    description: "Exact-set object inventory: 11 core enum types with ordered labels, 15 core and 2 audit tables, 46 core and 8 audit indexes, 7 index predicates, zero user triggers/views/matviews"
    requirement: SCHEMA-08
    verification:
      - kind: integration
        ref: "tests/schema/test_inventory.py -m schema (TestEnumTypes, TestTables, TestIndexes, TestIndexPredicates, TestNoProceduralObjects)"
        status: pass
      - kind: other
        ref: "mutation check: renamed ix_users_registered_at in the migration, suite went red naming the symmetric difference, reverted, green again"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every v1.6 legacy structure is absent from the schema, not merely unused: the subscription_plan enum, core.usage_monthly, core.subscription_events, users.jwt_sub, users.subscription_plan; core.users has exactly its seven target columns and audit.subscription_events still exists"
    requirement: SCHEMA-07
    verification:
      - kind: integration
        ref: "tests/schema/test_inventory.py -m schema -k legacy (TestLegacyStructuresAreGone, 6 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The schema suite is selectable and is deselected from the default run, keeping a bare pytest green on a machine with no PostgreSQL"
    verification:
      - kind: other
        ref: "pytest --collect-only -q collects 0 paths under tests/schema/; bare pytest -> 163 passed, 70 deselected"
        status: pass
    human_judgment: false
  - id: D6
    description: "The PostgreSQL 17 inventory constants were re-captured from the live server and reconciled against RESEARCH.md's PostgreSQL 16.2 capture, closing assumption A1"
    requirement: SCHEMA-08
    verification:
      - kind: other
        ref: "task 1 verification script: 54 indexes and 44 auth_event_result labels present in 34-INVENTORY-PG17.md, server_version recorded; traceability script maps all 76 labels / 17 tables / 54 indexes / 7 predicates / 7 users columns back to the doc"
        status: pass
    human_judgment: false

duration: 42min
completed: 2026-08-20
status: complete
---

# Phase 34 Plan 03: Schema-Conformance Harness and Object Inventory Summary

**A `tests/schema/` package that creates its own scratch database, applies the real migration through pogo's own parser, and asserts the applied schema's 11 enums, 17 tables, 54 indexes, and 7 index predicates as exact sets — with zero imports from the knowingly-broken application.**

## Performance

- **Duration:** ~42 min
- **Tasks:** 3 of 3
- **Files created:** 6
- **Files modified:** 2
- **Tests:** 37 schema tests, all passing; 163 unit tests still passing

## Accomplishments

- **Closed RESEARCH.md assumption A1 with a real PostgreSQL 17.11 capture.** All six constant groups match the PostgreSQL 16.2 baseline exactly — zero divergence. Details below.
- **Built the harness the rest of the phase runs on.** A synchronous session fixture creates `ns_schema_test`, applies `migrations/20260818_01_initial-release.sql` in-process via `pogo_core.util.testing.apply`, and drops it. Every test runs in a transaction that always rolls back.
- **Proved the migration's rollback section works** — on a second scratch database, through pogo's own `rollback`, not a hand-written `DROP SCHEMA`. Neither `core` nor `audit` survives, and `_pogo_migration` is emptied.
- **Made the inventory assertions bite.** Exact-set equality, verified by actually renaming an index in the migration and watching the suite go red with `unexpected: ['ix_users_registered_at_mutant']; absent: ['ix_users_registered_at']`, then reverting to green.
- **Kept the default run green on a machine with no PostgreSQL.** `pytest` alone is 163 passed / 70 deselected.

## Task Commits

1. **Task 1: Capture the inventory constants from the real PostgreSQL 17 apply** — `d8c78b5` (docs)
2. **Task 2: Build the tests/schema harness and prove apply/rollback through it** — `20491fa` (feat)
3. **Task 3: Assert the exact-set object inventory and the absence of every legacy structure** — `d2e709c` (test)

## Files Created/Modified

- `.planning/phases/34-schema/34-INVENTORY-PG17.md` — the PostgreSQL 17.11 capture: 11 enum label lists in `enumsortorder`, 15 + 2 table names, all 54 index names with unique flags and predicates, predicates under both `search_path` settings, filtered and unfiltered trigger counts, the SCHEMA-07 negatives, and the reconciliation table. The source of every constant in `test_inventory.py`.
- `tests/schema/__init__.py` — empty, and load-bearing: it stops pytest's rootdir walk at `tests/`, which is what makes `from schema.helpers import ...` resolve.
- `tests/schema/conftest.py` — DSN construction from `DB_*`, scratch-database create/drop with an identifier guard, in-process apply, the session `_schema_db_uri` fixture, the per-test `conn` fixture with the P-6 rollback guard, and the `tier` fixture.
- `tests/schema/helpers.py` — `insert_user`, `insert_tier`, `insert_grant`, all `$N`-parameterised, none committing.
- `tests/schema/test_apply_rollback.py` — SCHEMA-01, D-20, and a rollback-isolation proof.
- `tests/schema/test_inventory.py` — SCHEMA-07 and SCHEMA-08, 32 tests.
- `pyproject.toml` — the `schema` marker plus the `addopts` change. `[project] dependencies` byte-identical.
- `.planning/phases/34-schema/34-VALIDATION.md` — every command reconciled to carry `-m schema`.

## The PostgreSQL 17 Reconciliation (assumption A1, OQ-1)

Captured from PostgreSQL **17.11 (Debian 17.11-1.pgdg13+2)**. Compared against RESEARCH.md Code Example 4, which came from PostgreSQL 16.2:

| # | Constant group | Verdict |
|---|----------------|---------|
| 1 | `EXPECTED_ENUM_LABEL_COUNTS` — 11 types | **matched**, identical names and counts |
| 2 | `EXPECTED_CORE_TABLES` — 15 | **matched**, symmetric difference empty |
| 3 | `EXPECTED_AUDIT_TABLES` — 2 | **matched**, symmetric difference empty |
| 4 | `EXPECTED_CORE_INDEXES` — 46 | **matched**, symmetric difference empty |
| 5 | `EXPECTED_AUDIT_INDEXES` — 8 | **matched**, symmetric difference empty |
| 6 | `EXPECTED_INDEX_PREDICATES` — 7 entries | **matched**, all 7 byte-identical under the default `search_path` |

Beyond the six groups, also matched: `core.auth_event_result`'s 44 labels in identical `enumsortorder` (compared as an ordered sequence, not a set); 0 user triggers and 104 internal triggers; 0 views and 0 matviews; all four `GONE` negatives.

**Differences found: none.** A1 is closed as *confirmed*, not *corrected*. OQ-1 is answered "no divergence". Plan 34-04 can inherit these constraint expectations without re-deriving them — but the values that bind are the ones in `34-INVENTORY-PG17.md`, because those were read from the target version.

Two traps RESEARCH.md flagged were confirmed live on 17.11 and are handled in code, not worked around:

- **P-7 (`tgisinternal`).** A correct schema has 104 rows in `pg_trigger` for `core` + `audit`. `USER_TRIGGERS` filters `NOT t.tgisinternal`, so the zero-trigger assertion means "no user-defined trigger" rather than "no foreign keys". Both numbers are recorded in the capture doc so a later reader can see why the filter exists.
- **P-5 (`search_path`).** `ix_access_grants_one_active_per_user` renders as `(status = 'active'::core.access_grant_status)` under the default `search_path` and as `(status = 'active'::access_grant_status)` under `core, public`. `TestIndexPredicates` pins the former before reading.

## Decisions Made

- **Pinned rather than normalized.** The predicate test executes `SET search_path TO "$user", public` before reading `pg_get_expr`, instead of stripping `core.` from the returned string. One statement, and `EXPECTED_INDEX_PREDICATES` stays a set of literals that can be diffed against the capture doc by eye.
- **A second scratch database for the rollback proof.** `ns_schema_test_rollback` is created and dropped inside the test, so applying and rolling back cannot disturb the session fixture's database. Both are dropped on teardown; `datname LIKE 'ns_schema_test%'` returns no rows after a run.
- **`pogo_core.util.testing.rollback`, not `DROP SCHEMA`.** D-20 exists to prove the migration file's own rollback section works. A hand-written drop would prove nothing about it, and neither does the session fixture's `DROP DATABASE`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] The `DB_NAME` default collided with task 2's own D-13 gate**

- **Found during:** Task 2
- **Issue:** The plan specifies `.env.example` values as fallbacks for the five `DB_*` variables. `.env.example` sets `DB_NAME=nativespeaker`, so `_DB_DEFAULTS` contained the literal string `nativespeaker` — which task 2's acceptance gate reads as an application import on a non-comment line. Two docstrings citing `src/nativespeaker/api/config.py` hit the same gate.
- **Fix:** The gate was left exactly as written; the code changed. `DB_NAME` now falls back to `postgres`, the maintenance database. This is the better default independently of the gate: that connection only ever issues `CREATE DATABASE` / `DROP DATABASE`, so the maintenance database is both the conventional target and the one guaranteed to exist — falling back to an application database that may not exist yet would fail setup for no reason. The `DB_NAME` environment variable still wins when set. The two docstrings became `#` comments, which the gate strips, losing no explanation.
- **Files modified:** `tests/schema/conftest.py`
- **Verification:** Task 2's gate script exits 0; the full suite passes.
- **Committed in:** `20491fa`

**2. [Rule 3 — Blocking] The P-4 note was a trailing comment and defeated its own gate**

- **Found during:** Task 2
- **Issue:** `from pogo_core.util import testing as pogo_testing  # NOT pogo_migrate.testing -- see P-4` put the forbidden string on a code line. The gate strips only full-line comments, so the warning tripped the check it was warning about.
- **Fix:** Moved the note to a standalone comment block below the import group (ruff's `I` rule rejects a comment inside a sorted import block).
- **Files modified:** `tests/schema/conftest.py`
- **Verification:** `ruff check tests/schema` and the gate script both exit 0.
- **Committed in:** `20491fa`

**3. [Rule 2 — Missing critical functionality] The seed helpers would have shipped unexercised**

- **Found during:** Task 2
- **Issue:** `helpers.py` is required by the plan's artifact spec, but nothing in plans 34-01 through 34-03 called `insert_user` or `insert_grant` — only `insert_tier`, via the `tier` fixture. They would have shipped as untested code that plan 34-04 depends on, and a latent bug in a seed helper corrupts every constraint test built on it.
- **Fix:** Added `TestHarnessIsolation` to `test_apply_rollback.py` — two tests that seed a user and a grant, then confirm from a later test that `core.users`, `core.access_grants` and `core.access_tiers` are all empty again. This reproduces the 3-test shape RESEARCH.md Code Example 2 verified, and proves the per-test rollback boundary at the same time.
- **Files modified:** `tests/schema/test_apply_rollback.py`
- **Verification:** Both tests pass; the isolation test would fail if rollback were not happening.
- **Committed in:** `20491fa`

**4. [Rule 2 — Security] Identifier guard on `CREATE`/`DROP DATABASE`**

- **Found during:** Task 2
- **Issue:** Threat T-34-03-01 permits exactly one f-string — the scratch database *name*, since identifiers cannot be parameterized. The plan's control is "keep it a module constant". That is a convention, enforced by nothing.
- **Fix:** `_check_identifier` rejects any name not matching `^[a-z][a-z0-9_]*$` before interpolation, in both `create_database` and `drop_database`. Convention plus a mechanism.
- **Files modified:** `tests/schema/conftest.py`
- **Verification:** Suite passes; both call sites still pass module constants.
- **Committed in:** `20491fa`

**5. [DIRECTIVE-2] `34-VALIDATION.md` reconciled to the marker change**

- **Found during:** Task 2
- **Issue:** Every command in VALIDATION.md's per-requirement map omitted `-m schema`. After the `addopts` change those commands collect nothing and report success — a silently empty run, which is worse than a failing one.
- **Fix:** Added `-m schema` to all 8 per-requirement commands, the quick-run and full-suite commands, and both sampling-rate commands. Added a note recording that DIRECTIVE-2 resolved the open question the file's "New marker required" paragraph had left hanging.
- **Files modified:** `.planning/phases/34-schema/34-VALIDATION.md`
- **Verification:** `grep -n "pytest tests/schema"` shows `-m schema` on every line.
- **Committed in:** `20491fa`

---

**Total deviations:** 5 auto-fixed (2 × Rule 3, 2 × Rule 2, 1 × orchestrator directive)
**Impact on plan:** No scope creep. Deviations 1 and 2 are the plan's own gates working correctly — in both cases the code moved, never the assertion. Deviations 3 and 4 harden artifacts the plan already required. Deviation 5 is DIRECTIVE-2's explicit instruction.

## Issues Encountered

**A trailing `# noqa: S608` and a function-local import** were written into `test_apply_rollback.py` on the first pass and cleaned up before the commit: `S` is not in the repo's ruff `select` list, so the `noqa` was dead, and the `pogo_testing` import belonged at module level. Caught by reading the file back, not by a tool.

**Nothing else.** No auth gates, no architectural decisions, no package installs — the plan's threat register was right that this plan has zero install surface. `asyncpg`, `pytest`, `pytest-asyncio` and `pogo-core` were all already installed.

## Known Stubs

None. Every file created is exercised by a passing test: `helpers.py` via `TestHarnessIsolation` and the `tier` fixture, `conftest.py` via all 37 tests, and both test modules by the suite itself.

## Verification Evidence

All executed, none inferred:

| Check | Result |
|-------|--------|
| `pytest tests/schema -m schema -x -q` | **37 passed** in 1.93s |
| `pytest tests/schema/test_inventory.py -m schema -k legacy -x -q` | **6 passed**, 26 deselected |
| `pytest` (bare) | **163 passed, 70 deselected** |
| `pytest tests/unit -q` | **163 passed** |
| `pytest --collect-only -q \| grep -c "tests/schema/"` | **0** |
| `ruff check tests/schema pyproject.toml src` | All checks passed |
| Index-rename mutation | Suite **failed** naming the symmetric difference, then **passed** after revert |
| `datname LIKE 'ns_schema_test%'` after the run | no rows |
| `git diff` on `[project] dependencies` | empty |
| `git diff --stat 34-RESEARCH.md` | empty |
| `git status --short docker-compose.yml` | ` M` — left exactly as found, not staged |

## Next Phase Readiness

Plan **34-04** (`tests/schema/test_constraints.py`) is unblocked and inherits:

- The `conn` and `tier` fixtures, and `insert_user` / `insert_tier` / `insert_grant` — all exercised.
- The `-m schema` selector, which its `<verify>` blocks must use.
- The confirmed PostgreSQL 17 constants, so no constraint expectation needs re-deriving.
- **The P-6 warning stands.** Nothing in this plan exercised a deferred-constraint failure. The `conn` fixture guards `tx.rollback()` with `try`/`except`, but the three `@COMMIT` cases in RESEARCH.md's conformance matrix (the free-grant lower bound, the non-entitled-subscription case, the owner-mismatch case) still need explicit `BEGIN`/`COMMIT` control rather than the fixture's transaction wrapper. That guard is written but untested.

Two pre-existing untracked paths were left alone as out of scope: `.gsd/` and `.planning/research/.cache/`.

---
*Phase: 34-schema*
*Completed: 2026-08-20*

## Self-Check: PASSED

All 7 files verified present on disk; all 3 task commit hashes verified in `git log`.
