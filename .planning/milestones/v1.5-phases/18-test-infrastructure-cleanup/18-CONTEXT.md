# Phase 18: Test Infrastructure Cleanup - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace manual `cleanup_chat()` try/finally blocks with transaction-based test isolation. Each e2e test runs inside a database transaction that auto-rollbacks on completion, leaving zero artifacts. Unit tests are unaffected (they use mocks).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion

All implementation areas deferred to Claude's judgment. Recommended defaults based on codebase analysis:

**Transaction scope:**
- Per-test rollback — each test gets a clean database slate
- Use SAVEPOINT-based nested transactions so the app's own commit/rollback inside `get_db` works within the test's outer transaction
- Override `app.state.session_factory` in e2e fixtures to bind all sessions to the test transaction

**Seed data pattern:**
- Keep `create_chat()` as an async helper (it's clear and direct) — just remove `cleanup_chat()` and all try/finally blocks
- Transaction rollback handles cleanup automatically

**Test boundary:**
- Transaction isolation applies to e2e tests only
- Unit tests stay on `AsyncMock(spec=ChatsDB)` — no changes needed

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Test infrastructure
- `tests/e2e/conftest.py` — Current e2e fixtures: `test_db_factory`, `create_chat()`, `cleanup_chat()`, `real_client`, `firebase_token`
- `tests/unit/conftest.py` — Unit test fixtures: mock DB, service, client, JWT helpers
- `tests/conftest.py` — Root conftest (minimal, just comments)

### Application DB layer
- `app/api/dependencies.py` — `get_db` dependency with commit/rollback pattern (lines 17-24)
- `app/api/main.py` — App lifespan and `session_factory` setup on `app.state`

### Tests using cleanup
- `tests/e2e/test_isolation.py` — 5 tests with `cleanup_chat()` try/finally
- `tests/e2e/test_chat_queries.py` — 3 tests with `cleanup_chat()` try/finally

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `create_chat()` helper in `tests/e2e/conftest.py` — reusable as-is once cleanup is removed
- `test_db_factory` fixture — creates independent async engine/session factory for test setup
- `ensure_tables` fixture — session-scoped table creation (CREATE TABLE IF NOT EXISTS)

### Established Patterns
- `get_db` dependency uses `async with session_factory() as session` with try/commit/except/rollback — the SAVEPOINT approach must work within this
- Session-in-init pattern on ChatsDB — session passed at construction
- `dependency_overrides` used in unit tests for DI swapping

### Integration Points
- `app.state.session_factory` — the connection point for injecting a transaction-bound session factory
- `real_client` fixture (scope=module) — TestClient with real app lifespan; transaction fixture needs compatible scope
- `@pytest.mark.e2e` marker — all e2e tests use this; transaction fixture should be automatic for e2e-marked tests

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 18-test-infrastructure-cleanup*
*Context gathered: 2026-03-19*
