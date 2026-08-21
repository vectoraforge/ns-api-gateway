---
phase: 34-schema
plan: 04
subsystem: testing
tags: [postgres, pytest, asyncpg, constraints, deferred-fk, conformance]

requires:
  - phase: 34-02
    provides: migrations/20260818_01_initial-release.sql -- the schema under test
  - phase: 34-03
    provides: the tests/schema harness -- scratch-database session fixture, per-test rollback conn fixture, tier fixture, and the insert_user / insert_tier / insert_grant seed helpers
provides:
  - "tests/schema/test_constraints.py -- 40 tests proving the section 10 rejection cases with real rows"
  - "SCHEMA-02 proof: the (issuer, subject) reservation survives retirement; the provider/provider_uid agreement CHECK; D-16's ON DELETE RESTRICT"
  - "SCHEMA-03 proof: one active grant per user, the lifetime free-grant slot, the anti-abuse declarative quartet, the four valid evidence tuples"
  - "SCHEMA-04 proof: the STORED generated column and both deferred entitlement foreign keys, at COMMIT"
  - "SCHEMA-05 proof: ruling 9.8's operation partition plus the lifecycle and binding CHECKs"
  - "SCHEMA-06 proof: the all-or-nothing actor CHECK, the succeeded/operation CHECK, and the details shape CHECKs"
  - "A savepoint-scoped rejection helper that keeps the transaction usable after a rejected statement"
  - "The first genuine exercise of the conn fixture's P-6 deferred-rollback guard"
affects: [35-foundation, 36-rebind]

actuals:
  tokens: 24800
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Savepoint-scoped rejection assertion: SAVEPOINT / ROLLBACK TO SAVEPOINT around the offending statement, so a test can still query what did and did not land"
    - "Explicit COMMIT-time assertion for DEFERRABLE INITIALLY DEFERRED constraints, with no ROLLBACK afterwards"
    - "SET CONSTRAINTS ALL IMMEDIATE to prove a deferred constraint accepts a valid row without committing it"

key-files:
  created:
    - tests/schema/test_constraints.py
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/phases/34-schema/34-VALIDATION.md

key-decisions:
  - "Cases R5 and R6 assert the exception class only: on PostgreSQL 17.11 they report access_grants_anti_abuse_check, not the access_grants_anti_abuse_grant_source_check RESEARCH observed on 16.2. The named CHECK is subsumed and unreachable as a reported violation; a new introspection test pins that reason rather than leaving the name silently dropped"
  - "Added a savepoint-scoped _rejects helper after discovering that a rejected statement aborts the whole transaction, making every post-rejection query fail with InFailedSQLTransactionError"
  - "Added a valid-pair counterpart to case LB using SET CONSTRAINTS ALL IMMEDIATE, so the anti-abuse lower bound is proven to reject for absence rather than always"
  - "Asserted the truncated composite FK name for case OWN, because it is the only way to show OWN rejects on the ownership FK rather than on the entitlement FK"

requirements-completed: [SCHEMA-02, SCHEMA-03, SCHEMA-04, SCHEMA-05, SCHEMA-06, SCHEMA-08]

coverage:
  - id: D1
    description: "The (issuer, subject) reservation rejects a duplicate whether the existing row is active or historical, the provider/provider_uid agreement CHECK rejects both malformed shapes, identity_state defaults to active, and ON DELETE RESTRICT blocks deleting a user that has an identity row"
    requirement: SCHEMA-02
    verification:
      - kind: integration
        ref: "pytest tests/schema/test_constraints.py -m schema -k identity -x (TestExternalIdentityConstraints, 6 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Cases R7, R8, SUB, LB, V1-V4 and R1-R6: one active grant per user, the lifetime free-grant slot surviving expiry, one active grant per subscription, the grant-keyed usage primary key, and the whole anti-abuse declarative quartet"
    requirement: SCHEMA-03
    verification:
      - kind: integration
        ref: "pytest tests/schema/test_constraints.py -m schema -k grant -x (TestAccessGrantConstraints + TestAntiAbuseEvidenceConstraints, 20 tests)"
        status: pass
      - kind: other
        ref: "mutation check: removed the anti-abuse insert from the SET CONSTRAINTS ALL IMMEDIATE test, suite went red with access_grants_anti_abuse_required_grant_id_fkey, restored, green again"
        status: pass
    human_judgment: false
  - id: D3
    description: "Case GEN rejects a direct write to the STORED generated column; cases E1, E2 and OWN reject at COMMIT on the two deferred foreign keys; cases UNO and MS are accepted"
    requirement: SCHEMA-04
    verification:
      - kind: integration
        ref: "pytest tests/schema/test_constraints.py -m schema -k subscription -x (TestSubscriptionConstraints, 9 selected)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Case R9 plus the other half of ruling 9.8's partition, the lifecycle CHECK, the binding CHECK, and one accepted well-formed claimed-and-consumed row"
    requirement: SCHEMA-05
    verification:
      - kind: integration
        ref: "pytest tests/schema/test_constraints.py -m schema -k challenge -x (TestAuthChallengeConstraints, 5 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Cases A1-A5 rejected and case A6 accepted with the DDL's default details skeleton, proving the audit CHECKs are not simply rejecting everything"
    requirement: SCHEMA-06
    verification:
      - kind: integration
        ref: "pytest tests/schema/test_constraints.py -m schema -k audit -x (TestAuthEventAuditConstraints, 6 tests)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every acceptance check in 00-schema.md section 10 now has a green automated command; all eight rows of 34-VALIDATION.md's per-requirement map are green"
    requirement: SCHEMA-08
    verification:
      - kind: integration
        ref: "pytest tests/schema -m schema -x -q -> 77 passed; all eight per-requirement commands executed individually"
        status: pass
    human_judgment: false

duration: 38min
completed: 2026-08-20
status: complete
---

# Phase 34 Plan 04: Constraint Conformance Suite Summary

**Forty tests that write real rows at the v2.0 schema and prove it rejects what `00-schema.md §10` says it must reject — including the four COMMIT-time deferred-constraint cases nothing in this phase had exercised before, and the four valid anti-abuse evidence tuples that stop a CHECK which rejects everything from passing the suite.**

## Performance

- **Duration:** ~38 min
- **Tasks:** 2 of 2
- **Files created:** 1 (`tests/schema/test_constraints.py`, 793 lines, 40 tests)
- **Files modified:** 2 (planning documents only)
- **Tests:** 40 new; `tests/schema` now 77 passing; `tests/unit` unchanged at 163

## §10 Coverage — every check accounted for

`§10` has four bullets. The first two belong to plans 34-02 and 34-03; the last two are this plan's.

| §10 check | Where proven | Status |
|-----------|--------------|--------|
| Apply onto a baseline database, each rollback clean in reverse | 34-02 (real apply/rollback/re-apply) and 34-03 (`test_apply_rollback.py`) | covered — **note the D-01 reinterpretation below** |
| Final object inventory: schemas, 11 enums, 15 + 2 tables, legacy absences | 34-03 `test_inventory.py` | covered |
| Five unique indexes with exact predicates, two non-unique partial indexes | 34-03 `TestIndexPredicates` | covered |
| Four valid anti-abuse tuples insert successfully | V1–V4, this plan | covered |
| `anonymous_device_grant` with both `native_claim_provider` and `idp_account_hash` NULL rejected | R1 | covered |
| Native row carrying `idp_account_hash` rejected | R2 | covered |
| Web-anonymous or registered row carrying a `native_claim_provider` rejected | R3, R4 | covered |
| A `subscription` or `manual` grant cannot get an anti-abuse row at all | R5, R6 | covered — **see the PostgreSQL 17 divergence below** |
| A second `status='active'` grant for one user rejected | R7 | covered |
| A second free grant of the same source rejected even after the first is expired | R8 | covered |
| `auth_challenges` row with `operation='restore_subscription'` rejected | R9 | covered |

**No `§10` check is uncovered.** The one clarification worth stating plainly: `§10`'s first bullet says "`pogo` applies all six migrations onto a database holding only `20260322_01_initial-release`". D-01 overrode the six-file sequence and D-02 deleted that baseline, so the check as literally written is unsatisfiable by construction — it was discharged in its D-01 form (one migration, from empty, rollback clean) by plans 34-02 and 34-03. That reinterpretation predates this plan; it is restated here so a later reader does not mistake it for an omission.

Cases beyond `§10` also covered here, from RESEARCH's 32-case matrix: D16, I1, I2, LB, E1, E2, OWN, SUB, GEN, MS, UNO, A1–A6. RB1 and RB2 belong to 34-03. Every one of the 30 non-inventory matrix rows now has a test.

## PostgreSQL 17 divergence from RESEARCH's PostgreSQL 16.2 capture

**One divergence found — cases R5 and R6.**

RESEARCH Code Example 5 records R5 as rejecting with `CheckViolationError access_grants_anti_abuse_grant_source_check`, and the plan's acceptance criteria require asserting that name. On PostgreSQL 17.11 the reported constraint is **`access_grants_anti_abuse_check`** — the four-arm shape CHECK — not the named one.

This is not a schema defect and the tests were not weakened to accommodate it. Read from the live catalog:

- `access_grants_anti_abuse_grant_source_check` is `CHECK (grant_source = ANY (ARRAY['anonymous_device_grant', 'registered_account_grant']))`.
- **Both arms** of `access_grants_anti_abuse_check` already begin `grant_source = 'anonymous_device_grant'` / `grant_source = 'registered_account_grant'`.

So no row can satisfy the four-arm CHECK and still violate the `grant_source` CHECK: the former strictly subsumes the latter. PostgreSQL evaluates a table's CHECKs in constraint-name order, and `access_grants_anti_abuse_check` sorts before `access_grants_anti_abuse_grant_source_check`, so the subsuming constraint always reports first. **The named CHECK is unreachable as a reported violation for any row.** It is redundant belt-and-braces, which is exactly what the migration comment at `20260818_01_initial-release.sql:461-463` says it is ("With the composite FK below, this forbids an anti-abuse row for a 'subscription' or 'manual' grant at all").

Disposition: R5 and R6 assert the exception class and that no row landed. A new test, `test_grant_anti_abuse_grant_source_check_is_subsumed`, reads `pg_get_constraintdef` and asserts the named CHECK exists, admits exactly the two free sources, and names neither `subscription` nor `manual` — so the constraint the plan wanted named is still verified, by introspection rather than by a message that PostgreSQL will never emit. The alternative — deleting the assertion quietly — would have hidden a real fact about the schema.

RESEARCH's 16.2 observation was most likely taken with a row shape or a DDL ordering that differed; it cannot be reproduced on the target version, and the target version is what binds.

**Everything else matched.** The other 29 matrix cases produced exactly the exception class RESEARCH recorded, including all four COMMIT-time deferred-FK cases and `GeneratedAlwaysError`.

## The P-6 guard is now genuinely exercised

Plan 34-03 left the `conn` fixture's `try`/`except` around `tx.rollback()` written but untested. Four tests now hit it — LB, E1, E2 and OWN each end with an aborted server-side transaction that asyncpg still believes is open. All four pass, and the suite leaves no residue: `datname LIKE 'ns_schema_test%'` returns no rows after a run, and every test that follows one of them sees an empty database.

## Task Commits

1. **Task 1: Identity and grant constraints — SCHEMA-02, SCHEMA-03, D-16** — `912baff` (test)
2. **Task 2: Subscription, challenge, audit, and anti-abuse constraints — SCHEMA-04/05/06** — `33147b4` (test)

## Test Count per Requirement Group

| Selector | Requirement | Selected | Result |
|----------|-------------|----------|--------|
| `-k identity` | SCHEMA-02 | 6 | 6 passed |
| `-k grant` | SCHEMA-03 | 20 | 20 passed |
| `-k subscription` | SCHEMA-04 | 9 | 9 passed |
| `-k challenge` | SCHEMA-05 | 5 | 5 passed |
| `-k audit` | SCHEMA-06 | 6 | 6 passed |
| whole module | SCHEMA-02 … SCHEMA-06 | 40 | 40 passed |

`-k subscription` selects 9 rather than 6 because three tests in other groups legitimately name a subscription (case SUB, case R5, and case R9's `restore_subscription` operation). Every selector is non-empty, closing 34-VALIDATION.md's per-requirement test map.

## Decisions Made

- **The savepoint-scoped `_rejects` helper.** A rejected statement aborts the entire PostgreSQL transaction, so `assert count == 0` after a `pytest.raises` fails with `InFailedSQLTransactionError` rather than asserting anything. `_rejects` wraps the offending statement in `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`, so the follow-up queries work. Its docstring states plainly that the savepoint is *not* what proves the rejection — the exception class and the stable constraint name are — so a later reader does not mistake a post-savepoint absence check for the real assertion. Deliberately not used for the four COMMIT-time cases: there is no savepoint to return to once a deferred failure ends the transaction.
- **Asserted the truncated composite FK name.** `access_grants_active_subscription_grant_subscription_id_ac_fkey` is what survives 63-character truncation. It looks fragile, but it is derived from explicit column names rather than declaration order, and asserting it is the only way to show case OWN rejects on the *ownership* FK rather than on the entitlement FK that E1 and E2 name. The reason is written next to the constant.
- **A valid-pair counterpart to case LB.** `SET CONSTRAINTS ALL IMMEDIATE` forces deferred checking inside the per-test transaction, proving a free grant *with* its anti-abuse row satisfies the quartet — without committing and without breaking per-test rollback. Without it, case LB would pass identically if the FK rejected every free grant.
- **Case R8 asserts the first grant is `expired` before attempting the second.** Otherwise the test silently degrades into a second copy of R7 the moment someone reorders it.
- **Case SUB uses a second user for the second grant.** A second grant for the same owner trips `ix_access_grants_one_active_per_user` first and never reaches the per-subscription index.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] A rejected statement aborts the transaction, so no post-rejection query could run**

- **Found during:** Task 1
- **Issue:** Six of the first twelve tests failed with `asyncpg.exceptions.InFailedSQLTransactionError: current transaction is aborted`. The plan's acceptance criterion asks each rejection test to prove the row is absent afterwards; inside the fixture's single transaction that query is unrunnable once the rejection has fired.
- **Fix:** Added the `_rejects` async context manager (savepoint around the offending statement). No assertion was loosened — every one of those tests still asserts its exception class, and five of them still assert a stable constraint or index name.
- **Files modified:** `tests/schema/test_constraints.py`
- **Verification:** 12 passed after the change; `ruff check` clean.
- **Committed in:** `912baff`

**2. [Rule 2 — Verification integrity] Case LB had no valid-pair counterpart**

- **Found during:** Task 1
- **Issue:** T-34-04-01 is the threat that a test passes for the wrong reason. Case LB proves a free grant with no anti-abuse row is rejected at COMMIT — but it would pass just as well if the deferred FK rejected *every* free grant, which would break the two live free-grant flows in Phase 37 without any test noticing.
- **Fix:** Added `test_grant_free_source_with_anti_abuse_row_passes_the_deferred_check`, using `SET CONSTRAINTS ALL IMMEDIATE`.
- **Verification:** Mutation-checked — removing the anti-abuse insert makes the new test fail with `access_grants_anti_abuse_required_grant_id_fkey`, confirming `SET CONSTRAINTS ALL IMMEDIATE` genuinely enforces rather than no-opping. Restored, green again.
- **Committed in:** `912baff`

**3. [Rule 1 — Incorrect expectation] Cases R5 and R6 cannot assert the constraint name the plan specified**

- **Found during:** Task 2
- **Issue:** Both tests failed asserting `access_grants_anti_abuse_grant_source_check`; PostgreSQL 17.11 reports `access_grants_anti_abuse_check`. Investigated via `pg_get_constraintdef` before touching either test.
- **Fix:** R5 and R6 assert the exception class and row absence; the *reason* the name cannot appear is pinned by a new introspection test rather than dropped. Full analysis in the divergence section above.
- **Note:** This deviates from two of the plan's acceptance criteria (R5 "asserts the rejection names `access_grants_anti_abuse_grant_source_check`"). The criteria encode RESEARCH's 16.2 observation, which does not hold on the target version. The schema was **not** changed to make the assertion true — that would have meant deleting a redundant CHECK the spec asked for, purely to make a test message match.
- **Committed in:** `33147b4`

**4. [Rule 3 — Blocking] The plan's Task 2 gate script counts zero tests on a correct suite**

- **Found during:** Task 2
- **Issue:** The gate runs `pytest ... -q --collect-only` and greps for `test_constraints.py::`. `addopts` carries `-v`, so a single `-q` nets to verbosity 0 and pytest prints the indented tree instead of node ids — the grep finds 0 and the gate fails on a passing suite. Same class of `addopts` interaction that produced deviation 5 in plan 34-03.
- **Fix:** Ran the gate with `-q -q`. The script's assertion and threshold were left exactly as written; only the invocation changed. Result: `OK 40 constraint tests collected`.
- **Files modified:** none (verification-only).

**5. [Plan `<output>`] `34-VALIDATION.md` per-requirement map filled in**

- **Found during:** Task 2 wrap-up
- **Issue:** All eight rows still read `❌ W0 | ⬜ pending` with `TBD` task/plan/wave columns, including the three requirements plan 34-03 completed.
- **Fix:** Ran all eight commands individually, then set each row's plan, wave, File Exists and Status. Also ticked the Wave 0 requirement checklist.
- **Files modified:** `.planning/phases/34-schema/34-VALIDATION.md`

**6. [State] `REQUIREMENTS.md` range row flipped by hand**

- **Found during:** Wrap-up
- **Issue:** Row 142 is a range row (`SCHEMA-01 … SCHEMA-08 | Phase 34 | Pending`) that `requirements mark-complete` cannot match per-ID, exactly as 34-03 warned.
- **Fix:** Edited to `Complete`. The eight per-ID checkboxes were already `[x]` — verified via `git show HEAD~2` that they were ticked by an earlier plan, not by this one, so nothing there needed changing.
- **Files modified:** `.planning/REQUIREMENTS.md`

---

**Total deviations:** 6 (2 × Rule 3, 1 × Rule 2, 1 × Rule 1, 2 × bookkeeping)
**Impact on plan:** No scope creep and no schema change. Deviations 1 and 4 are environmental facts the plan could not have known. Deviation 2 hardens a case the threat register singles out. Deviation 3 is the only substantive departure from the plan's letter, and it is documented above rather than resolved by quietly relaxing an assertion.

## Issues Encountered

**An unused `exc_info` binding** survived the R5 rewrite and was caught by `ruff` (F841), not by the test run. Removed.

**No auth gates, no architectural decisions, no package installs.** `[project] dependencies` is byte-identical; `pyproject.toml` is untouched by this plan entirely. `docker-compose.yml` still shows ` M` — the developer's uncommitted `env_file` edit was left exactly as found and never staged.

## Known Stubs

None. Every test in the module executes real SQL against the applied schema; no test is skipped, xfailed, or marked todo; no helper is unexercised.

## Verification Evidence

All executed, none inferred:

| Check | Result |
|-------|--------|
| `pytest tests/schema -m schema -x -q` | **77 passed** in 3.53s |
| `pytest tests/schema/test_constraints.py -m schema -q` | **40 passed** |
| `-k identity` / `-k grant` / `-k subscription` / `-k challenge` / `-k audit` | **6 / 20 / 9 / 5 / 6 passed**, all exit 0 |
| `pytest tests/unit -q` | **163 passed** |
| `pytest` (bare) | **163 passed, 110 deselected** — 70 + the 40 new schema tests |
| `ruff check tests/schema` | All checks passed |
| Task 1 gate script | `OK identity/grant constraint suite structurally sound` |
| Task 2 gate script (with `-q -q`) | `OK 40 constraint tests collected` |
| Mutation check on the deferred-accept test | red with the expected FK, green after restore |
| `git diff --stat -- pyproject.toml` | empty |
| `git status --short docker-compose.yml` | ` M` — left as found, not staged |
| No string matching `_check<digit>` | confirmed by the gate script |
| No f-string carrying a row value into SQL | confirmed by regex over non-comment lines |

## Next Phase Readiness

Phase 34 is complete. All eight SCHEMA requirements have a green automated command in 34-VALIDATION.md's test map.

What Phase 35 and 36 inherit:

- **A schema proven to reject, not merely proven to exist.** Every constraint Phases 35–46 write through has a test that exercises it with real rows.
- **`tests/schema/` runs while the application is broken** — zero application imports, so it stays a usable gate through the Phase 35/36 rebind.
- **Two facts worth carrying forward.** `access_grants_anti_abuse_grant_source_check` is redundant and unreachable as a reported violation; do not remove it (the spec asks for it) and do not write application code that matches on its name. And the four deferred constraints — the anti-abuse lower bound, both entitlement FKs, and the ownership FK — fail at COMMIT, so Phase 37's grant-issuance transactions must be prepared to handle a `ForeignKeyViolationError` raised by their commit rather than by any individual statement.
- **The `REVOKE DELETE` requirement is still open** (D-10/D-11), unchanged by this plan.

---
*Phase: 34-schema*
*Completed: 2026-08-20*

## Self-Check: PASSED

`tests/schema/test_constraints.py` and this summary verified present on disk; both task commit hashes verified in `git log`.
