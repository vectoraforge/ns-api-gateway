# Phase 28: Test Updates - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

All tests pass against the new schema with native PG enum types and config-driven quotas. No new features, no schema changes, no migration work.

</domain>

<decisions>
## Implementation Decisions

### E2E Test Database Setup
- **D-01:** Tests do NOT create database objects -- no `create_all()`, no `CREATE TYPE`, no running migrations from test code. The database must be fully set up (migrations applied) before tests run.
- **D-02:** Remove the `ensure_tables` fixture from `tests/e2e/conftest.py` that currently calls `SQLModel.metadata.create_all`
- **D-03:** E2E tests assume a pre-migrated database -- the migration is applied externally before `pytest` runs

### Test Discovery Approach
- **D-04:** Audit all test files for stale references before running pytest -- grep for old names, old signatures, plans table references, etc.
- **D-05:** Fix all stale references found in audit, then verify with full `pytest` run

### Plans Table Cleanup
- **D-06:** Include plans table references in the audit -- grep for `plans`, `Plan`, `seed` across all test files even though Phase 25 removed the model
- **D-07:** Remove any residual plans references found (imports, seeding, assertions)

### Claude's Discretion
- How to handle `ensure_tables` removal -- whether to delete entirely or replace with a lightweight DB connectivity check
- Specific grep patterns for the audit step
- Order of fixes after audit

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Test Infrastructure
- `tests/e2e/conftest.py` -- E2E fixtures including `ensure_tables` (to remove), `_db_transaction`, `create_chat` helper
- `tests/unit/conftest.py` -- Unit fixtures including `service`, `client`, `TEST_USER`, JWT infrastructure
- `tests/conftest.py` -- Root conftest (minimal)

### Test Files to Audit
- `tests/unit/test_usage.py` -- Quota enforcement tests (TEST-02)
- `tests/unit/test_services.py` -- ChatService tests
- `tests/unit/test_users.py` -- User endpoint tests
- `tests/unit/test_subscriptions.py` -- Subscription tests
- `tests/unit/test_webhooks.py` -- Webhook tests
- `tests/e2e/test_chats.py` -- E2E chat tests
- `tests/e2e/test_flows.py` -- E2E flow tests
- `tests/e2e/test_isolation.py` -- Cross-user isolation tests

### Models (source of truth for current names)
- `src/nativespeaker/api/models.py` -- StrEnum classes (ChatRole, SubscriptionPlan, SubscriptionProvider, SubscriptionStatus), no Plan model

### Requirements
- `.planning/REQUIREMENTS.md` -- TEST-01, TEST-02

### Prior Phase Context
- `.planning/phases/25-config-and-model-foundation/25-CONTEXT.md` -- D-07 through D-11 (renames, Plan deletion)
- `.planning/phases/26-service-and-database-rewiring/26-CONTEXT.md` -- D-04 through D-07 (User object, try_increment signature)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/unit/conftest.py` already updated for Phase 25-26 changes: `SubscriptionPlan` imports, quotas dict, `TEST_USER` with `subscription_plan` field
- `tests/e2e/conftest.py:create_chat` helper already uses `ChatRole`, `HumanContent`, `AIContent`
- `_db_transaction` fixture pattern (savepoint rollback) is independent of schema setup

### Established Patterns
- Session-scoped fixtures for expensive setup (`_app_config`, `firebase_token`)
- Module-scoped fixtures for app lifespan and client
- Autouse `_db_transaction` for per-test rollback isolation
- `dependency_overrides` for unit test DI

### Integration Points
- `ensure_tables` fixture is depended on by `_app_lifespan` (via fixture chain)
- Removing `ensure_tables` requires updating `_app_lifespan` dependency chain
- pogo-migrate configured in `pyproject.toml [tool.pogo]`

</code_context>

<specifics>
## Specific Ideas

- User was emphatic: tests must NEVER create database objects -- they assume a pre-migrated database
- Audit-first approach chosen over run-and-fix -- catches issues in skipped/mocked paths
- Plans table grep included as belt-and-suspenders even though Phase 25 likely cleaned it up

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 28-test-updates*
*Context gathered: 2026-03-23*
