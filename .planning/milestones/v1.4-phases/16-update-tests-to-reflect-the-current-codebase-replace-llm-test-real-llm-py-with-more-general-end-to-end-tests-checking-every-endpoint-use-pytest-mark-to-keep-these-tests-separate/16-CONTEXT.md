# Phase 16: Update Tests - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace `tests/llm/test_real_llm.py` with general end-to-end tests covering every endpoint. Remove `tests/integration/` and `tests/llm/` directories entirely. New `tests/e2e/` directory with real DB + real LLM tests. Reorganize conftest files so mocked fixtures live in `tests/unit/`. Use `@pytest.mark.db` and `@pytest.mark.llm` to keep e2e tests separate from default test runs.

</domain>

<decisions>
## Implementation Decisions

### E2E definition
- Full stack: real PostgreSQL + real OpenAI LLM
- Real FastAPI app imported from `app.api.main` -- lifespan runs, real DI, real config
- Real Firebase tokens from the production Firebase project with a dedicated test user
- Rollback-per-test via db_session fixture for data isolation
- Assertions check response structure only (status code, required fields, correct types) -- not specific LLM content

### Marker strategy
- Two markers: `@pytest.mark.db` and `@pytest.mark.llm` (both already exist in pyproject.toml)
- LLM-calling endpoints (POST /chats, POST /chats/{id}): both `@db` and `@llm`
- Non-LLM endpoints (GET /, GET /health/ready, GET /examples, GET /chats, GET /chats/{id}, DELETE /chats/{id}): `@db` only
- Non-LLM endpoint tests seed data directly via ORM fixtures, no LLM calls needed
- Run all e2e: `-m 'db'`; LLM-only e2e: `-m 'llm and db'`; DB-only e2e: `-m 'db and not llm'`
- Default addopts unchanged: `-m 'not llm and not db'` excludes all e2e

### Coverage scope
- Happy path only -- error contract already proven by unit tests
- One multi-step flow test: create chat -> followup -> get messages -> delete (full lifecycle)
- Cross-user isolation tests moved from integration/ to e2e/ -- remain @db only with seeded data
- All endpoints covered: POST /chats, POST /chats/{id}, GET /chats, GET /chats/{id}, DELETE /chats/{id}, GET /examples, GET /health/ready, GET /

### File organization
- New directory: `tests/e2e/`
- Remove entirely: `tests/llm/`, `tests/integration/`, `tests/jwt_helpers.py`
- One file per endpoint group:
  - `test_chats.py` -- POST /chats, POST /chats/{id} (LLM tests)
  - `test_chat_queries.py` -- GET /chats, GET /chats/{id}, DELETE /chats/{id} (DB-only, seeded)
  - `test_examples.py` -- GET /examples (DB-only)
  - `test_health.py` -- GET /health/ready (DB-only)
  - `test_root.py` -- GET / (DB-only)
  - `test_isolation.py` -- cross-user isolation (DB-only, seeded, moved from integration/)
  - `test_flows.py` -- full lifecycle flow (LLM + DB)
- `tests/e2e/conftest.py` -- real-infra fixtures (real app client, db_session, Firebase auth)
- Mocked fixtures (mock_config, mock_chats_db, client, service) move from `tests/conftest.py` to `tests/unit/conftest.py`
- `tests/conftest.py` becomes minimal (shared config only)

### Claude's Discretion
- Firebase Admin SDK setup for generating test tokens
- Exact fixture design for real app client with auth headers
- Test data seeding helpers for non-LLM endpoint tests
- conftest.py minimal shared content

</decisions>

<specifics>
## Specific Ideas

- Real app from `app.api.main` with lifespan running -- tests the actual boot path, not a test assembly
- Firebase test user from same project as production -- simplest auth setup
- Structure-only assertions for LLM responses prevent flakiness from non-deterministic output

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs -- requirements fully captured in decisions above.

### Existing test infrastructure
- `tests/conftest.py` -- current mocked fixtures to be relocated to unit/conftest.py
- `tests/integration/conftest.py` -- current real-DB fixtures pattern (db_engine, db_session, create_chat helper)
- `tests/llm/test_real_llm.py` -- current real-LLM test pattern to be replaced
- `tests/integration/test_cross_user_isolation.py` -- isolation tests to be moved to e2e/

### Configuration
- `pyproject.toml` [tool.pytest.ini_options] -- markers, addopts, asyncio_mode settings

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db_engine`/`db_session` fixtures from `tests/integration/conftest.py` -- rollback-per-test pattern, reuse in e2e/conftest.py
- `create_chat`/`cleanup_chat` helpers from `tests/integration/conftest.py` -- data seeding for non-LLM tests
- `Chat`, `Message`, `Role`, `HumanContent`, `AIContent` models from `app/models.py` -- for seeding test data

### Established Patterns
- `AsyncMock(spec=ChatsDB)` for unit test mocking -- stays in unit/ untouched
- `@pytest.mark.db` class-level decorator for real-DB tests
- `@pytest.mark.asyncio` for async test methods
- `TestClient(app, raise_server_exceptions=False)` for HTTP-level testing
- `dependency_overrides` for DI replacement in test apps

### Integration Points
- `app.api.main:app` -- the real FastAPI app instance for e2e tests
- `app.api.dependencies` -- DI functions (get_db, get_config, get_user_id, get_chat_service)
- `app.api.errors:register_exception_handlers` -- error handler registration

</code_context>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 16-update-tests*
*Context gathered: 2026-03-17*
