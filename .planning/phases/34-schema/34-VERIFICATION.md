---
phase: 34-schema
verified: 2026-08-21T01:20:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 34: Schema Verification Report

**Phase Goal:** Deliver the complete v2.0 auth schema as one migration applied in one pass against an empty database.
**Verified:** 2026-08-21T01:20:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A fresh `pogo apply` against an empty database produces the full schema with no error and no second migration file present | ✓ VERIFIED | Independently ran `pogo apply -v` (real CLI, not the pytest harness) against a freshly created scratch database `ns_verify_manual`. Exit code 0, output `Applying 20260818_01_initial-release`. Post-apply introspection: `core`/`audit` namespaces present, 17 tables (15 core + 2 audit). `ls migrations/*.sql` returns exactly one file. Scratch database dropped after verification. |
| 2 | `(issuer, subject)` → `core.users` resolution works through `core.external_identities`, with `identity_state` and tombstone retention expressible | ✓ VERIFIED | `core.external_identities` DDL (migration lines ~197-230) carries `identity_state` enum (`active`/`historical`), `historical_at`, and the `(issuer, subject)` unique constraint. `tests/schema/test_constraints.py::TestExternalIdentityConstraints::test_identity_duplicate_issuer_subject_rejected_when_existing_is_historical` proves the uniqueness reservation survives retirement — read directly from the file and confirmed passing in the live test run. |
| 3 | At most one `status='active'` grant per user is enforceable, and `core.user_monthly_usage` is keyed by grant id | ✓ VERIFIED | `ix_access_grants_one_active_per_user` partial unique index confirmed live via `pg_get_expr` = `(status = 'active'::core.access_grant_status)`, byte-identical to 34-INVENTORY-PG17.md. Test suite includes case R7 (second active grant rejected) and confirms `core.user_monthly_usage` PK is `grant_id` alone. |
| 4 | `audit.auth_events` rejects a row with partial actor fields per its CHECK constraints | ✓ VERIFIED | DDL read directly (migration lines 641-689): all-or-nothing actor CHECK plus five `details`-shape CHECKs plus the succeeded/operation CHECK. `TestAuthEventAuditConstraints` (6 tests, all passing) exercises A1-A6 including the accepted minimal-actor row (A6), which is the necessary counter-proof that the CHECKs are not rejecting everything. |
| 5 | Every acceptance check in `00-schema.md §10` passes | ✓ VERIFIED | Full `tests/schema -m schema` run (see below) is 77/77 green, covering the object inventory, index/predicate exact-set, four valid anti-abuse tuples, and all nine enumerated rejection cases. §10's literal first bullet (six-file sequence onto a baseline) is unsatisfiable by construction after the phase-context-locked D-01/D-02 overrides (predates this phase, recorded in 34-CONTEXT.md, explicitly not a deviation per orchestrator context) — its D-01-reinterpreted form (one migration, from empty, clean rollback) is exactly ROADMAP criterion 1, independently verified above. |

**Score:** 5/5 truths verified.

### Executed Verification (independent, not taken from SUMMARY)

| Check | Command | Result |
|-------|---------|--------|
| Full schema suite | `.venv/bin/pytest tests/schema -m schema -q` | **77 passed** in 3.45s |
| Constraint suite alone | `.venv/bin/pytest tests/schema/test_constraints.py -m schema -q --collect-only` | **40 tests collected** |
| Unit suite unaffected | `.venv/bin/pytest -q` (bare) | **163 passed, 110 deselected** |
| Fresh manual apply | `pogo apply -v` against a hand-created empty database, outside any test fixture | exit 0, `core`/`audit` created, 17 tables |
| Exactly one migration file | `ls migrations/*.sql \| wc -l` | `1` |
| `ruff check tests/schema` | | All checks passed |
| Debt-marker scan | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` over migration + tests/schema | no matches |

### Claims Checked Adversarially

1. **SCHEMA-07 legacy absence** — confirmed by reading the migration DDL directly: `core.users` has exactly 7 columns (`id, email, display_name, registered_at, active, created_at, updated_at`) — no `jwt_sub`, no `subscription_plan`. `core.access_grant_source` enum has exactly 4 labels (`subscription`, `anonymous_device_grant`, `registered_account_grant`, `manual`) — no `promo`. `core.usage_monthly` and `core.subscription_events` (in `core`) are absent from the DDL; `audit.subscription_events` exists (the table moved schemas, confirming it wasn't simply lost). VERIFIED, not merely claimed.

2. **Criterion 1 (exactly one file, fresh apply works)** — independently re-executed via the real `pogo` CLI against a hand-created empty database (not the pytest fixture), exit 0, schema created. VERIFIED.

3. **Criteria 2-4 enforced with real rows** — confirmed the full 77-test suite passes live against PostgreSQL 17.11, and spot-read the specific tests (identity historical-duplicate, audit actor CHECKs, grant uniqueness index) to confirm the tests exercise real INSERT/DELETE statements against the applied schema, not mocks. VERIFIED.

4. **34-04's R5/R6 "unreachable constraint" finding** — independently reproduced against the live database: queried `pg_constraint` for both CHECK definitions, confirmed `access_grants_anti_abuse_check` (four-arm) is a strict superset of `access_grants_anti_abuse_grant_source_check` (simple `grant_source IN (...)`), then executed a live INSERT with `grant_source='subscription'` and observed the actual PostgreSQL error: it reports `access_grants_anti_abuse_check`, not the named one. The reasoning in the SUMMARY is correct and the discharge (assert exception class + introspection test pinning the subsumption) is sound engineering, not a weakened test. The row is still rejected in every case. VERIFIED — this is the one place a test was changed to match observed behavior, and the change is justified and honestly documented.

5. **§10 first-bullet discharge** — the literal six-file/baseline bullet is unsatisfiable after D-01/D-02 (locked in 34-CONTEXT.md before this phase began, and the orchestrator explicitly flags D-02 as not a deviation). ROADMAP.md's own success criterion 1 already encodes the D-01-reinterpreted form ("fresh apply against an empty database... no second migration file"), which was independently verified above outside any test fixture. This is a legitimate, pre-existing-decision-backed discharge, not a gap being explained away.

6. **A1 closure (PG 17.11 == PG 16.2 constants)** — spot-checked live: `core` index count = 46, `audit` index count = 8 (matches INVENTORY-PG17.md exactly), and the `ix_access_grants_one_active_per_user` predicate string read live is byte-identical to the captured constant (`(status = 'active'::core.access_grant_status)`). No divergence found in the spot-check. VERIFIED.

### Requirements Coverage

| Requirement | Evidence | Status |
|---|---|---|
| SCHEMA-01 | Live `pogo apply` (independent run) + `test_apply_rollback.py` (5 tests, all pass) | ✓ SATISFIED |
| SCHEMA-02 | `TestExternalIdentityConstraints` (6 tests incl. historical-retirement case), DDL read | ✓ SATISFIED |
| SCHEMA-03 | `TestAccessGrantConstraints` + `TestAntiAbuseEvidenceConstraints` (20 tests), live index predicate check | ✓ SATISFIED |
| SCHEMA-04 | `TestSubscriptionConstraints` (9 selected), STORED generated column and deferred FKs confirmed in DDL | ✓ SATISFIED |
| SCHEMA-05 | `TestAuthChallengeConstraints` (5 tests), `restore_subscription` CHECK confirmed | ✓ SATISFIED |
| SCHEMA-06 | `TestAuthEventAuditConstraints` (6 tests incl. accepted-row A6), DDL read | ✓ SATISFIED |
| SCHEMA-07 | `TestLegacyStructuresAreGone` (6 tests), DDL grep confirms absence directly | ✓ SATISFIED |
| SCHEMA-08 | Full 77/77 green suite; every §10 check mapped to a passing test | ✓ SATISFIED |

No orphaned requirements found — `.planning/REQUIREMENTS.md` SCHEMA-01…08 all marked `[x]` Complete and match plan `requirements:` frontmatter across the four plans.

### Anti-Patterns Found

None. No debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`) in the migration or `tests/schema/`. `ruff check tests/schema` is clean. No stub patterns, no f-string SQL injection risk (row values bind via asyncpg `$1` parameters, confirmed by the plan's own gate script and spot-read).

### Deferred Items (not gaps — explicitly out of phase scope)

Per 34-CONTEXT.md `<deferred>`, correctly not attempted in this phase:
- Full §8 cascade-list introspection beyond D-16's single `ON DELETE RESTRICT` test — candidate for Phase 36.
- Actual `REVOKE DELETE` enforcement — blocked on database-role provisioning; documented in migration comment and PROJECT.md per D-10/D-11.
- Application/model alignment with the new schema — Phase 35/36 work; application code is expected to be broken by this migration per the phase boundary.

### Human Verification Required

None. All must-haves are machine-verifiable and were independently confirmed against a live PostgreSQL 17.11 instance, not inferred from SUMMARY.md claims.

### Gaps Summary

No gaps found. Every ROADMAP success criterion, every SCHEMA requirement, and every adversarial claim in the verification brief was independently re-executed or re-derived against the live database and the actual migration/test source, and all held.

---

_Verified: 2026-08-21T01:20:00Z_
_Verifier: Claude (gsd-verifier)_
