# Phase 12: LLM Dependency Injection - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Centralize all FastAPI dependencies into `app/dependencies.py`. Routes use `Depends()` instead of `request.app.state.*`. Service keeps its current LLM/chain construction. This is a DI access-pattern refactor, not a deep LLM decoupling.

**Note:** Original requirements DI-01, DI-02, DI-03 and success criteria describe deep LLM decoupling (remove llm from __init__, build chain per-call, get_llm as standalone dep). User chose a lighter approach — requirements must be rewritten to match decisions below.

</domain>

<decisions>
## Implementation Decisions

### Dependency provider location
- New `app/dependencies.py` module hosts ALL FastAPI dependencies: `get_service`, `get_config`, `get_db`, `get_user_id`
- `get_db` moves from `database.py`, `get_user_id` moves from `auth.py` — originals deleted, not re-exported
- `get_service` reads `app.state.service` (built in lifespan with llm passed to `__init__`)
- `get_config` reads `app.state.config`
- No standalone `get_llm` dependency — LLM stays internal to AnalysisService
- Verifier stays accessed via `app.state` inside `get_user_id` (not a route-level dependency)
- Routes completely stop importing `Request` — clean signatures with only `Depends()` params and body models

### Chain build strategy
- No changes — `self.chain` stays built once at startup in `AnalysisService.__init__`

### Service type annotations
- Replace `from langchain_openai import ChatOpenAI` with `BaseChatModel` from `langchain_core` in `services.py`
- Service becomes provider-agnostic at the type level

### Route signature cleanup
- Replace `request.app.state.service` with `service: AnalysisService = Depends(get_service)`
- Replace `request.app.state.config` with `config: AppConfig = Depends(get_config)`
- Remove `request: Request` from all route handler signatures
- Claude identifies additional cleanup opportunities during planning (type annotations, param ordering, etc.)

### Test override pattern
- `dependency_overrides[get_service]` returns real `AnalysisService` constructed with mock LLM
- `dependency_overrides[get_config]` returns mock config
- `dependency_overrides[get_user_id]` returns `'test-user'` directly (skips JWT verification in unit tests)
- `dependency_overrides[get_db]` stays as-is (already uses this pattern)
- No more `app.state.service = ...` or `app.state.verifier = ...` in test setup

### Claude's Discretion
- Route signature cleanup details (param ordering, annotation improvements)
- Internal structure of `app/dependencies.py` (function ordering, grouping)
- Whether `get_service` and `get_config` use `Request` internally or access `app.state` differently

</decisions>

<specifics>
## Specific Ideas

- All `app.state` access from routes should go through `Depends()` — no direct `request.app.state.*` patterns remain
- `get_user_id` still uses `Request` internally to access verifier from `app.state`, but routes don't see `Request`
- Phase name "LLM Dependency Injection" is now a misnomer — this is really "Dependency Centralization", but keeping the name for roadmap continuity

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_db` in `database.py`: Established dependency pattern — will move to `dependencies.py`
- `get_user_id` in `auth.py`: JWT verification dependency — will move to `dependencies.py`
- `dependency_overrides[get_db]` in `tests/conftest.py`: Existing DI test pattern to replicate for other deps

### Established Patterns
- Lifespan function in `main.py` builds all state objects — this stays unchanged
- `app.state.*` is the state transport mechanism — deps read from it
- `ResiliencePolicy` wraps LLM invocation — stays coupled to service

### Integration Points
- `app/routers/prompts.py`: 5 route handlers need signature updates
- `app/routers/root.py`: May reference `request.app.state` — needs check
- `tests/conftest.py`: Main fixture file needs DI override migration
- `tests/integration/conftest.py`: Also uses `dependency_overrides[get_db]`

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-llm-dependency-injection*
*Context gathered: 2026-03-02*
