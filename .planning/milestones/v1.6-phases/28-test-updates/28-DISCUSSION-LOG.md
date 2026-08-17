# Phase 28: Test Updates - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-03-23
**Phase:** 28-test-updates
**Areas discussed:** Enum creation in E2E conftest, Test discovery scope, Plans seed data cleanup

---

## Enum Creation in E2E Conftest

| Option | Description | Selected |
|--------|-------------|----------|
| Raw SQL CREATE TYPE | Execute CREATE TYPE IF NOT EXISTS for each enum directly via connection.execute() before create_all() | |
| Derive from Python StrEnums | Build CREATE TYPE statements dynamically from the StrEnum classes | |
| Run migration instead | Use pogo-migrate to apply the migration file | |
| Tests don't create DB objects | Tests assume a pre-migrated database -- no create_all(), no CREATE TYPE, no migrations from tests | ✓ |

**User's choice:** Tests should NOT create database objects at all. The database must be fully set up before tests run.
**Notes:** User was emphatic about this -- corrected twice when presented with options that involved creating objects from tests. The `ensure_tables` fixture should be removed.

---

## Test Discovery Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Run pytest, fix failures | Let failures guide what needs updating | |
| Audit first, then fix | Grep all test files for stale references before running | ✓ |
| You decide | Claude picks the approach | |

**User's choice:** Audit first, then fix
**Notes:** Catches issues even in skipped or mocked test paths that wouldn't surface from just running pytest.

---

## Plans Seed Data Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, include in audit | Grep for plans/Plan/seed across test files as part of the audit | ✓ |
| Skip, already handled | Trust Phase 25 removed everything | |

**User's choice:** Yes, include in audit
**Notes:** Belt and suspenders -- even though Phase 25 removed the Plan model.

---

## Claude's Discretion

- How to handle `ensure_tables` removal (delete or replace with connectivity check)
- Specific grep patterns for the audit step
- Order of fixes after audit

## Deferred Ideas

None -- discussion stayed within phase scope.
