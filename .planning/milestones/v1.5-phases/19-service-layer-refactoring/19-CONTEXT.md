# Phase 19: Service Layer Refactoring - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Split `app/service.py` into an `app/services/` package with separate `llm_service.py` and `chat_service.py` modules. Split `app/database.py` into an `app/database/` package with a `chats_db.py` module. Zero behavior changes — all existing tests must pass unchanged.

</domain>

<decisions>
## Implementation Decisions

### Import path convention
- Re-export classes from package `__init__.py` files
- Importers use short paths: `from app.services import ChatService`, `from app.database import ChatsDB`
- `__init__.py` handles internal wiring — importers don't need to know module names

### Database package scope
- Minimal structure: `database/__init__.py` + `chats_db.py` only
- No base class or shared utilities — add when Phase 21 introduces UsersDB
- Keep the existing session-in-init pattern on ChatsDB unchanged

### Old module cleanup
- Delete `app/service.py` and `app/database.py` immediately after split
- No compatibility shims or re-export stubs — clean break
- All 7 import sites updated in one pass

### Claude's Discretion
- Exact ordering of imports within new `__init__.py` files
- Whether to add `__all__` to new packages
- Test file import updates (same convention, just new paths)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source files being split
- `app/service.py` — Contains `LLMService` and `ChatService` classes (target: split into `services/llm_service.py` and `services/chat_service.py`)
- `app/database.py` — Contains `ChatsDB` class (target: move to `database/chats_db.py`)

### Import sites to update
- `app/api/dependencies.py` — `from app.service import ChatService` (line 10)
- `app/api/main.py` — `from app.service import LLMService` (line 15)
- `app/routers/chats.py` — `from app.service import ChatService` (line 8)
- `app/routers/root.py` — `from app.service import ChatService` (line 6)
- `app/routers/examples.py` — `from app.service import ChatService` (line 5)
- `tests/unit/conftest.py` — `from app.database import ChatsDB` and `from app.service import ChatService` (lines 13, 16)

### Application wiring
- `app/api/dependencies.py` — `get_db` and `get_chat_service` dependency injection pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LLMService` class (21 lines): self-contained, only depends on config + resilience — clean module boundary
- `ChatService` class (97 lines): depends on `ChatsDB`, `LLMService`, and domain models — imports `from app.database import ChatsDB`
- `ChatsDB` class (55 lines): self-contained, only depends on SQLAlchemy/SQLModel and `app.models`

### Established Patterns
- Session-in-init: `ChatsDB(session)` — session passed at construction via `get_chat_service` dependency
- All FastAPI dependencies live in `app/api/dependencies.py`
- `app.state.llm_service` set during app lifespan in `main.py`

### Integration Points
- `app/api/dependencies.py:get_chat_service` — constructs `ChatService` with injected DB session and LLM service
- `app/api/main.py:lifespan` — creates `LLMService` singleton on startup
- Internal cross-reference: `ChatService` imports `ChatsDB` from database module

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

*Phase: 19-service-layer-refactoring*
*Context gathered: 2026-03-19*
