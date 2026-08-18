---
phase: 24
reviewers: [gemini, codex]
reviewed_at: 2026-03-22T00:00:00Z
plans_reviewed: [24-01-PLAN.md, 24-02-PLAN.md]
---

# Cross-AI Plan Review — Phase 24

## Gemini Review

# Phase 24: Migration Merge — Plan Review

The proposed plans provide a clean and effective strategy for consolidating the database schema and enforcing referential integrity via foreign keys. Since the project is in a pre-production state, "squashing" migrations is the correct architectural choice to avoid technical debt in the migration history. The approach correctly identifies the dependency graph and ensures that both the database layer (SQL) and the application layer (SQLModel) stay in sync.

### Strengths
- **Correct Dependency Ordering**: Plan 24-01 accurately identifies the FK dependency graph (Plans -> Users/Subscriptions -> Others), which is critical for successful table creation and deletion.
- **Synchronization**: Updating both the `.sql` migrations and the `SQLModel` definitions ensures that the ORM and the raw SQL remain consistent, preventing "drift" where the application expects constraints the DB doesn't have (or vice versa).
- **Idempotent Test Seeding**: Using `ON CONFLICT (tier) DO NOTHING` in the E2E test setup is a robust practice that prevents test failures if the database state persists between runs or if the migration already seeded the data.
- **Clean Slate Approach**: Plan 24-02 correctly identifies that `pogo-migrate` will lose track of its migration state after a merge/rename, and provides a clear path to reset the environment.

### Concerns
- **SQLModel vs. Pogo Redundancy (LOW)**: If E2E tests use `SQLModel.metadata.create_all()`, they bypass the `.sql` migration files entirely. While Plan 24-01 seeds the plans in `conftest.py`, any other logic (like triggers or complex constraints) added to the SQL migration would be missing in tests.
    - *Clarification*: Ensure that the `SQLModel` definitions in `models.py` are exhaustive enough that `create_all` produces a schema identical to the merged migration.
- **Hardcoded Schema (LOW)**: Plan 24-02 references a hardcoded `api` schema. If the project configuration allows for dynamic schema names (e.g., via environment variables), this manual step might fail or target the wrong schema in some environments.
- **Rollback Completeness (LOW)**: Plan 24-01 mentions rollbacks in reverse order. It's important to ensure that `DROP TABLE ... CASCADE` isn't used lazily, but rather that the rollback script explicitly handles the reverse dependency order to verify the migration is reversible.

### Suggestions
- **Unified Seeding Logic**: Instead of duplicating seed data in the `.sql` migration and `conftest.py`, consider moving the seed data to a shared JSON/YAML file or a Python constant that both the test suite and a migration-seeding script can consume. This prevents "seed drift."
- **Verification of Cascade**: In the merged migration, explicitly use `ALTER TABLE ... DROP CONSTRAINT` or ensure `DROP TABLE` statements are ordered correctly in the `ROLLBACK` section.
- **Automated Reset Option**: For Plan 24-02, if this is a common task in pre-production, consider adding a `make db-reset` or `uv run task db-reset` command that performs the `DROP SCHEMA` and `pogo apply` steps to reduce human error during the manual checkpoint.

### Risk Assessment: LOW
The risk is low because the project is pre-production. The plan is surgically focused on migration health and referential integrity. The "blocking" human action in Wave 2 is the safest way to handle a broken migration history, and the explicit seeding in tests mitigates the most common failure point (FK violations during test execution).

**Final Verdict**: The plans are well-structured, satisfy all requirements (MIG-01 through MIG-03), and follow industry best practices for early-stage schema management.

---

## Codex Review

## Plan 24-01 Review

### Summary
Plan 24-01 is directionally correct and aligned with the phase goal: it merges the migrations, fixes the schema-level integrity gap, updates SQLModel declarations, and accounts for test seeding so E2E runs remain valid under the new FK constraints. The main weakness is that its verification is too shallow for a migration-sensitive change: simple `grep` checks and unit tests do not prove that the merged migration actually applies cleanly, that FK constraints exist in PostgreSQL as intended, or that rollback order is valid.

### Strengths
- Directly targets all three requirements: merged migration, model FK declarations, and E2E seed compatibility.
- Uses correct FK dependency ordering with `plans` created before dependent tables.
- Recognizes the existing integrity gap between application joins and database constraints.
- Includes rollback ordering, which is important once dependency edges are introduced.
- Seeds `plans` in tests with idempotent insertion, which is appropriate for repeated test setup.
- Avoids unnecessary migration compatibility work given the stated pre-production/no-live-data context.

### Concerns
- **HIGH**: Verification does not prove the migration actually runs successfully via `pogo apply`; `grep` is not enough for migration correctness.
- **HIGH**: Seeding `plans` inside the migration and again in E2E setup introduces dual ownership of canonical seed data. If values diverge later, tests and real schema can drift.
- **MEDIUM**: The plan assumes `plans.tier` is a valid FK target without explicitly confirming it is `PRIMARY KEY` or `UNIQUE`. PostgreSQL requires that.
- **MEDIUM**: It does not explicitly validate that existing model field types, nullability, and defaults remain compatible with the new FK constraint.
- **MEDIUM**: Updating `tests/e2e/conftest.py` "after `create_all`" may be conceptually inconsistent if E2E uses migrations in some environments and `create_all` in others. That split should be made explicit.
- **LOW**: Deleting old migration files is fine here, but the plan does not mention checking for references to old migration names in tooling, docs, CI scripts, or developer setup notes.

### Suggestions
- Replace `grep`-style verification with real database validation:
  - run `uv run pogo apply` on a clean DB
  - inspect `pg_constraint` or `information_schema` for both FK constraints
  - run at least targeted E2E tests that create users/subscriptions with valid plans
- Choose one canonical source for `plans` seed data:
  - either seed in migration and let tests rely on migrated schema
  - or keep test-only seeding separate, but document why
- Explicitly confirm `plans.tier` is declared `PRIMARY KEY` or `UNIQUE` in the merged migration and SQLModel.
- Add a negative-path verification:
  - inserting a user or subscription with a nonexistent `plan` should fail at the DB level
- Clarify whether E2E uses migrations, `SQLModel.metadata.create_all()`, or both. If both exist, explain why and constrain the responsibility of each.
- Expand verification to include rollback once, since drop order is a stated implementation detail.

### Risk Assessment
**MEDIUM**. The implementation approach is sound and likely to meet the phase goals, but migration work is unforgiving, and the current verification plan is not strong enough to catch broken DDL, FK target issues, or schema/test drift.

---

## Plan 24-02 Review

### Summary
Plan 24-02 addresses a real operational consequence of merging migration files: pogo's migration history will no longer match the rewritten migration set. In a pre-production environment, resetting the schema is a reasonable approach. The plan is acceptable as an operational follow-up, but it is incomplete as written because it assumes the `api` schema is the only relevant state, does not verify the migration bookkeeping state carefully enough, and leaves too much implicit for a destructive human action.

### Strengths
- Correctly identifies migration-history mismatch as the main consequence of rewriting migration files.
- Uses a pragmatic reset strategy appropriate for a no-live-data environment.
- Separates destructive DB reset from code changes, which is good operationally.
- Includes post-apply validation via `pogo history`.

### Concerns
- **HIGH**: Dropping only the `api` schema may not reset `_pogo_migration` if that table lives in another schema or search path location. The plan may leave migration state inconsistent.
- **HIGH**: Human-action guidance is destructive but does not require explicit environment validation, increasing the chance of running against the wrong database.
- **MEDIUM**: Verification is incomplete; "1 migration applied" does not prove the schema matches requirements or that FK constraints exist.
- **MEDIUM**: It does not specify how to verify seed rows are correct, only that there are 4 rows.
- **MEDIUM**: There is no check that application startup and tests still work against the recreated schema.
- **LOW**: Depending on local DB permissions and schema ownership, `DROP SCHEMA api CASCADE` may fail; the plan does not mention expected failure modes.

### Suggestions
- Before any destructive action, require explicit environment checks:
  - print current `DB_HOST`, `DB_PORT`, `DB_NAME`, and current user
  - verify this is a non-production database
- Confirm where `_pogo_migration` lives before proposing schema-only reset. If needed, reset migration bookkeeping explicitly rather than assuming schema drop is sufficient.
- Expand verification to include:
  - introspection of FK constraints on `users.plan` and `subscriptions.plan`
  - validation that `plans` contains the expected tiers, not just row count
  - at least one E2E or integration test run after migration
- Prefer a reproducible reset command sequence documented in one place, including expected outputs and failure handling.
- If the team routinely rewrites migrations pre-production, add a note about this workflow so the destructive reset is not rediscovered ad hoc next time.

### Risk Assessment
**MEDIUM-HIGH**. The reset strategy is probably correct for this project stage, but destructive manual DB work is easy to get wrong, and the plan does not yet sufficiently guard against migration-state mismatch or wrong-environment execution.

---

## Cross-Plan Assessment

### Summary
Together, the two plans cover the technical change and the operational cleanup needed after rewriting migration history. The overall design is sensible for a pre-production system, with limited scope and no obvious over-engineering. The main systemic issue is weak verification: both plans rely too much on static checks and high-level expectations, and not enough on proving that the actual PostgreSQL schema, migration state, and E2E flows behave correctly under the new FK constraints.

### Overall Risk Assessment
**MEDIUM**. The plans are fundamentally aligned with the phase goals and likely workable, but schema rewrites need stronger operational safeguards and real DB-level verification before this should be considered complete.

---

## Consensus Summary

### Agreed Strengths
- **Correct FK dependency ordering** — Both reviewers confirm the plans table must be created first, and the dependency graph is correctly identified
- **Appropriate strategy for pre-production** — Both agree that merging migrations is the right call with no live data, avoiding unnecessary ALTER TABLE complexity
- **SQL/ORM synchronization** — Both note the plan correctly updates both the SQL migration and SQLModel definitions in lockstep
- **Idempotent test seeding** — Both approve of `ON CONFLICT DO NOTHING` for safe repeated test execution

### Agreed Concerns
- **Seed data dual ownership (MEDIUM-HIGH)** — Both reviewers flag that seeding plans in both the migration file AND the e2e conftest creates drift risk. If values change, they must be updated in two places.
- **Verification is too shallow (HIGH)** — Codex explicitly rates this HIGH; Gemini implies it. `grep` checks don't prove the migration actually applies or that FK constraints work at the database level. Real DB validation is needed.
- **Plan 24-02 schema reset assumptions (MEDIUM-HIGH)** — Both note the `DROP SCHEMA api CASCADE` may not fully reset pogo's `_pogo_migration` state if it lives outside the api schema. Codex rates this HIGH.

### Divergent Views
- **Overall risk level**: Gemini rates the overall risk as **LOW**, while Codex rates it as **MEDIUM**. The divergence centers on verification depth — Gemini trusts the plan's static checks more, while Codex demands real database-level proof.
- **Scope of suggestions**: Gemini suggests additional tooling (make db-reset, shared seed config), while Codex focuses on verification rigor (negative FK tests, constraint introspection, E2E runs). Both perspectives are valid but reflect different priorities (developer experience vs. correctness guarantees).
