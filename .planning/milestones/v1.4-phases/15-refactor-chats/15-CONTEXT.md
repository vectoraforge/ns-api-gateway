# Phase 15: Refactor Chats - Context

**Gathered:** 2026-03-10
**Updated:** 2026-03-16
**Status:** Ready for re-planning (post-execution update)

<domain>
## Phase Boundary

Restructure the chat data model, API surface, and code organization. Chat table has `title` and `lang` fields. Typed message content (HumanContent/AIContent) stored as JSON on Message. Separate endpoints for new chat vs followup. Server loads history from DB for LLM context. Flat file organization (service.py, database.py, models.py). ChatService per-request via DI. Breaking API change -- no backward compatibility required.

</domain>

<decisions>
## Implementation Decisions

### Data model
- Chat table: `id`, `user_id`, `title` (required), `lang` (optional, nullable), `created_at`
- No `phrase` or `comment` on Chat -- `title` is the display name derived from the initial phrase
- Message.content is typed: `HumanContent | AIContent` stored as JSON column
- `HumanContent(phrase: str, comment: str | None)` -- comment is per-message context, not per-chat
- `AIContent(response: str, issues: list[Issue], suggestions: list[str])` -- structured LLM output
- `Role` is `StrEnum` with `human` and `ai` values
- field_validator on Message dispatches to HumanContent or AIContent based on role
- field_serializer on Message converts content to dict via model_dump()

### Endpoints
- `POST /chats` -- new chat (phrase + optional comment + optional lang). Returns MessageResponse
- `POST /chats/{id}` -- followup (content). Returns MessageResponse
- `GET /chats/{id}` -- returns `list[MessageResponse]` (messages only, no chat metadata, no cursor pagination)
- `GET /chats` -- list user's chats. Returns `list[ChatResponse]` (chat_id, title, created_at, lang)
- `DELETE /chats/{id}` -- delete chat. 204 on success
- `GET /examples` -- stays as-is
- All paths use plural `/chats`

### Request schemas
- `ChatRequest`: phrase (required, max_length=4096), comment (optional), lang (optional)
- `MessageRequest`: content (required, max_length=4096)
- Separate Pydantic models per endpoint, no conditional validation

### Response schemas
- `ChatResponse`: chat_id, title, created_at, lang -- used for GET /chats list
- `MessageResponse`: chat_id, role, content (HumanContent | AIContent), created_at -- used for POST and GET messages
- MessageResponse.content is typed union, FastAPI serializes naturally via model_dump()
- No raw JSON strings in responses -- structured data throughout

### Chat creation flow
- LLM first, persist after: call LLM -> if success, insert Chat + human Message + AI Message
- Transaction handled by get_db() dependency (existing pattern)

### Followup flow
- Load chat + messages via get_chat with selectinload (ownership verified by user_id filter)
- Capacity limit: count ai_messages, check against history_max_messages (default 50)
- Call LLM with history
- Append human Message + AI Message to chat.messages

### History construction for LLM
- Past human messages: `msg.content.model_dump_json()` (JSON string of HumanContent)
- Past AI messages: `msg.content.model_dump_json()` (JSON string of AIContent)
- Current turn: passed via `{content}` slot in prompt template, also as model_dump_json()
- Consistent format: all messages to LLM are JSON representations of typed content

### Prompt template
- `create_chain` uses: `("system", prompt)`, `MessagesPlaceholder("history")`, `("human", "{content}")`
- History holds past messages, {content} is the current user input -- explicit separation

### Validation
- `lang` validated against supported languages when provided (on chat creation only)
- Followup endpoint does not accept `lang` -- language locked at chat creation time
- Error contract unchanged: 5 status codes (400/401/404/503/500), 5 error codes

### DI pattern
- ChatService created per-request via `get_chat_service()` dependency
- LLM chain built once in `lifespan()`, stored on `app.state.chain`
- ResiliencePolicy created once in `lifespan()`, stored on `app.state.policy`
- `get_chat_service()` receives: chain and policy from `app.state`, config from `get_config`, db session from `get_db`
- ChatService.__init__ creates ChatsDB(db) internally
- ChatService wraps all DB operations -- router never touches ChatsDB directly

### DB layer
- ChatsDB takes AsyncSession in __init__
- `create_chat(chat)` -- adds Chat (with messages via relationship) to session
- `get_chat(chat_id, user_id)` -- selectinload for messages, returns Chat | None
- `get_messages(chat_id, user_id)` -- JOIN query, returns list[Message]
- `list_chats(user_id, limit)` -- ordered by created_at desc
- `delete(chat_id, user_id)` -- returns rowcount; service raises InvalidChatError if 0

### File organization
- Flat structure: `app/service.py`, `app/database.py`, `app/models.py`
- `app/api/` package: main.py, schema.py, dependencies.py, errors.py (no __init__.py)
- `app/routers/` package: chats.py, examples.py, health.py, root.py (with __init__.py for exports)
- Remove `app/api/__init__.py` (untracked, not needed)
- No database/ or services/ subpackages

### Import fixes
- Fix unresolved langchain imports in service.py (AIMessage, HumanMessage, ChatPromptTemplate, MessagesPlaceholder)
- These are runtime-valid but LSP reports them as unresolved -- fix import paths

### Tests
- Full rewrite for new API surface, endpoints, schemas, and typed content model
- AsyncMock(spec=ChatsDB) prevents phantom mocks
- Mock replacement on service instance after construction

### Claude's Discretion
- get_chat return shape details (selectinload is decided, exact query tuning is flexible)
- Exact prompt text content (template structure is decided)
- Config key naming for chat list limit
- Test organization and fixture details

</decisions>

<specifics>
## Specific Ideas

- Chain built once in lifespan, passed to ChatService as pre-built chain
- MessageResponse.content should be `HumanContent | AIContent` union type -- let FastAPI handle serialization, no manual model_dump_json() in router
- Human message content for LLM history: `msg.content.model_dump_json()` -- consistent JSON format for all messages
- GET /chats returns ChatResponse with title + lang (not minimal)

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs -- requirements fully captured in decisions above and in REQUIREMENTS.md (REFACT-01 through REFACT-09).

### Requirements
- `.planning/REQUIREMENTS.md` -- REFACT-01 through REFACT-09 define acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models.py`: Chat, Message, Role, HumanContent, AIContent models (already implemented)
- `app/database.py`: ChatsDB class with session-in-init pattern (already implemented)
- `app/service.py`: ChatService with create_chain, ask_llm, create_chat, send_message (already implemented)
- `app/api/schema.py`: ChatRequest, MessageRequest, ChatResponse, MessageResponse, ChatResponseLLM (already implemented)
- `app/api/dependencies.py`: get_chat_service DI function (already implemented)

### Established Patterns
- `get_db()` handles commit/rollback via context manager -- transaction boundary
- Opaque error contract: 5 status codes, 5 error codes -- no changes needed
- selectinload for eager loading messages with chat
- ResiliencePolicy.ainvoke() wraps LLM calls with circuit breaker + retry
- field_validator/field_serializer for typed JSON content on SQLModel

### Integration Points
- `app/api/main.py`: lifespan() builds chain, stores on app.state.chain
- `app/api/dependencies.py`: get_chat_service() wires chain + policy from app.state
- `app/routers/chats.py`: All chat endpoints use ChatService via DI
- `app/api/errors.py`: Exception handlers unchanged

</code_context>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 15-refactor-chats*
*Context gathered: 2026-03-10*
*Context updated: 2026-03-16*
