# Phase 13: Endpoint Unification - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Merge two analysis paths (POST /prompts/analyze + POST /chats/{chat_id}/messages) into a single POST /chats endpoint. Rename `alternatives` -> `suggestions` and `assessment` -> `response` across all layers. Remove `lang` from the Chat model and make it a per-request hint. Old routes return 404. Surviving endpoints reorganized into dedicated routers.

</domain>

<decisions>
## Implementation Decisions

### Surviving Endpoints
- `GET /examples` — move from `/prompts/examples` to top-level `/examples` in a new `app/routers/examples.py`
- `GET /chats/{chat_id}/messages` — keep as-is (cursor-paginated message listing)
- `DELETE /chats/{chat_id}` — keep as-is
- All `/chats/*` endpoints live in a new dedicated `app/routers/chats.py`
- Delete `app/routers/prompts.py` entirely — all its endpoints are removed or relocated
- Old routes (`POST /prompts/analyze`, `POST /chats/{chat_id}/messages`) hard-removed — 404, no deprecation
- Authentication (JWT Bearer) unchanged for all endpoints

### Field Renames (Full Depth)
- `alternatives` -> `suggestions` — renamed in API schema, LLM output schema, LLM prompt template (`config/prompt.txt`), and all tests
- `assessment` -> `response` — same full-depth treatment across all layers
- Field descriptions updated to match new names (e.g., "Suggested corrections" instead of "Corrected alternatives")

### Model Renames
- `AnalyzeRequest` -> `ChatRequest`
- `AnalyzeResponse` -> `ChatResponse`
- `AnalyzeResponseLLM` -> `ChatResponseLLM`
- `AnalysisService` -> `ChatService`
- `ChatMessageRequest` — deleted (only used by removed continuation endpoint)
- `services.py` filename kept (generic, accommodates future services)

### Lang Behavior
- Remove `lang` column from `Chat` SQLModel class and `migrations/001_create_tables.sql`
- `lang` field in `ChatRequest`: `str | None = Field(default=None)`
- **New chat (no chat_id):** `lang` is REQUIRED — return 400 `invalid_request` if both `lang` is None and `chat_id` is None (EP-04)
- **Continuation (chat_id provided):** `lang` is ignored entirely — LLM uses conversation history for language context
- When provided on new chat: validate against `supported_languages`, pass to LLM prompt
- Remove `lang` from `ChatResponse` entirely — caller already knows what they sent
- Remove `_get_chat_lang()` from service (no longer needed — lang not stored on chat)
- `GET /examples?lang=en` keeps its lang parameter — unrelated to chat lang removal
- `supported_languages` property stays on service for validation when lang IS provided
- `Chats.create_chat()` signature: remove `lang` parameter (no longer stored)

### Prompt Template
- Single `config/prompt.txt` file with conditional lang section
- Service inserts `Language: {lang}` as a directive when lang provided, or empty string when None
- Keep current directive style: "You are a linguistic assistant for advanced non-native speakers of {lang}." when lang present
- For continuations (no lang): prompt omits the language directive — LLM infers from history
- Rename JSON keys in prompt: `alternatives` -> `suggestions`, `assessment` -> `response`
- Update field descriptions in prompt to match new names

### Response Shape
- `ChatResponse` fields: `{text, chat_id, issues, suggestions, response}` — no `lang`
- No new fields (no is_continuation, message_count, or created_at)
- `Issue` model unchanged: `{text_part, explanation}`
- `ChatMessagesResponse` and `ChatMessage` unchanged
- `ChatResponseLLM` fields: `{issues, suggestions, response}` — field renames only

### Error Behavior
- Missing lang on new chat (no chat_id) -> 400 `invalid_request`
- Invalid chat_id (nonexistent chat) -> 404 `not_found` (current InvalidChatError behavior preserved)
- Wrong owner on chat_id -> 404 `not_found` (current ChatOwnershipError behavior preserved)
- Unsupported lang -> 400 `invalid_request` (current UnsupportedLanguageError behavior preserved)
- Old routes -> 404 (removed, not deprecated)

### Service Layer Merge
- Merge `analyze()` and `chat()` into a single `chat()` method on `ChatService`
- `Chats` class stays in `app/chats.py` — remove `lang` from `create_chat()` signature
- Single unified method handles both new-chat (no `chat_id`) and continuation (`chat_id` provided)
- For new chat: validate lang, create chat (without lang), load empty history, invoke LLM with lang
- For continuation: verify ownership, check history capacity, load history, invoke LLM without lang

### Router/Test Restructure
- `app/routers/chats.py` — POST /chats, GET /chats/{id}/messages, DELETE /chats/{id}
- `app/routers/examples.py` — GET /examples
- Delete `app/routers/prompts.py`
- Update `app/routers/__init__.py` exports
- Update `app/main.py` router includes
- Test files: rename/split to match new router structure
- Add explicit 404 tests for removed routes (POST /prompts/analyze, POST /chats/{id}/messages) — validates success criteria #5

### Config
- No config changes needed — examples config stays, supported_languages concept stays
- `AppConfig` unchanged

### Claude's Discretion
- Exact prompt template wording for conditional lang handling
- Test file organization details (exact split strategy)
- Import cleanup strategy
- LLM schema field descriptions (as long as field names are correct)

</decisions>

<specifics>
## Specific Ideas

- Each message in a chat can be in a different language — lang is a per-request hint, not a chat-level property
- The LLM should be capable of auto-detecting language when no hint is provided (continuation case)
- For new chats, the caller MUST declare intent by providing lang — no silent defaults

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/chats.py` (Chats class): Chat CRUD and message operations — stays with `create_chat()` signature change (remove lang)
- `app/dependencies.py`: DI setup with get_service, get_db, get_user_id, get_config — reusable in new chats/examples routers
- `app/resilience.py` (ResiliencePolicy): LLM call resilience — unchanged, used by ChatService
- `app/errors.py`: Exception handlers — unchanged, 5-code contract handles all error types

### Established Patterns
- FastAPI router pattern: separate router files with APIRouter, included in main.py
- Pydantic models in `app/schema.py` for all request/response shapes
- DI via `Depends()` for service, db, user_id, config (Phase 12 pattern)
- LLM structured output via `with_structured_output()` on LangChain BaseChatModel
- Error contract: 5 status codes, opaque error codes, ErrorResponse model (Phase 11 pattern)

### Integration Points
- `app/main.py`: Router includes need updating (remove prompts_router, add chats_router, examples_router)
- `app/routers/__init__.py`: Export changes
- `config/prompt.txt`: LLM system prompt needs field renames and conditional lang handling
- `migrations/001_create_tables.sql`: Remove lang column from chats table
- `app/models.py`: Remove lang from Chat SQLModel class
- `tests/integration/test_prompts_endpoints.py`: Rename/restructure to match new router layout

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 13-endpoint-unification*
*Context gathered: 2026-03-02*
