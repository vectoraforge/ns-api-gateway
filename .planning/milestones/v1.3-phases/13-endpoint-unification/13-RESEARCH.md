# Phase 13: Endpoint Unification - Research

**Researched:** 2026-03-02
**Domain:** FastAPI endpoint consolidation, Pydantic schema renames, service layer merge
**Confidence:** HIGH

## Summary

Phase 13 merges two analysis entry points (`POST /prompts/analyze` and `POST /chats/{chat_id}/messages`) into a single `POST /chats` endpoint, renames schema fields (`alternatives` -> `suggestions`, `assessment` -> `response`), removes `lang` from the Chat model, and restructures routers into dedicated files. The `GET /examples` endpoint moves from `/prompts/examples` to top-level `/examples`.

The implementation is primarily a refactoring exercise with no new external dependencies. All changes use existing FastAPI/Pydantic patterns already established in the codebase (router files, `Depends()`, `model_validator`, Pydantic schemas, exception handlers). The service layer merge collapses `analyze()` and `chat()` into a single `chat()` method. The prompt template requires conditional lang handling -- inserting a language directive only when `lang` is provided.

**Primary recommendation:** Execute as an atomic rename-and-restructure. The field renames (`alternatives` -> `suggestions`, `assessment` -> `response`) must be done in lockstep across schema, LLM output schema, prompt template, service layer, and all tests. The router restructure (delete `prompts.py`, create `chats.py` and `examples.py`) should happen in the same commit to avoid broken intermediate states.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- `GET /examples` moves from `/prompts/examples` to top-level `/examples` in a new `app/routers/examples.py`
- `GET /chats/{chat_id}/messages` kept as-is (cursor-paginated message listing)
- `DELETE /chats/{chat_id}` kept as-is
- All `/chats/*` endpoints live in a new dedicated `app/routers/chats.py`
- Delete `app/routers/prompts.py` entirely
- Old routes (`POST /prompts/analyze`, `POST /chats/{chat_id}/messages`) hard-removed -- 404, no deprecation
- Authentication (JWT Bearer) unchanged
- Field renames: `alternatives` -> `suggestions`, `assessment` -> `response` (full depth: API schema, LLM output schema, prompt template, all tests)
- Field descriptions updated to match new names
- Model renames: `AnalyzeRequest` -> `ChatRequest`, `AnalyzeResponse` -> `ChatResponse`, `AnalyzeResponseLLM` -> `ChatResponseLLM`, `AnalysisService` -> `ChatService`
- `ChatMessageRequest` deleted (only used by removed continuation endpoint)
- `services.py` filename kept
- Remove `lang` column from `Chat` SQLModel class and `migrations/001_create_tables.sql`
- `lang` in `ChatRequest`: `str | None = Field(default=None)`
- New chat (no chat_id): `lang` is REQUIRED -- return 400 `invalid_request` if both `lang` is None and `chat_id` is None
- Continuation (chat_id provided): `lang` is ignored entirely
- When provided on new chat: validate against `supported_languages`, pass to LLM prompt
- Remove `lang` from `ChatResponse` entirely
- Remove `_get_chat_lang()` from service
- `GET /examples?lang=en` keeps its lang parameter unchanged
- `supported_languages` property stays on service for validation
- `Chats.create_chat()` signature: remove `lang` parameter
- Single `config/prompt.txt` file with conditional lang section
- Service inserts `Language: {lang}` directive when lang provided, empty string when None
- For continuations: prompt omits language directive -- LLM infers from history
- Rename JSON keys in prompt: `alternatives` -> `suggestions`, `assessment` -> `response`
- `ChatResponse` fields: `{text, chat_id, issues, suggestions, response}` -- no `lang`
- No new fields
- `Issue` model unchanged
- `ChatMessagesResponse` and `ChatMessage` unchanged
- `ChatResponseLLM` fields: `{issues, suggestions, response}`
- Error behavior: missing lang on new chat -> 400, invalid chat_id -> 404, wrong owner -> 404, unsupported lang -> 400, old routes -> 404
- Merge `analyze()` and `chat()` into a single `chat()` method on `ChatService`
- `Chats` class stays in `app/chats.py`
- Router/test restructure as specified
- Update `app/routers/__init__.py` exports
- Update `app/main.py` router includes
- No config changes needed

### Claude's Discretion
- Exact prompt template wording for conditional lang handling
- Test file organization details (exact split strategy)
- Import cleanup strategy
- LLM schema field descriptions (as long as field names are correct)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EP-01 | Unified `POST /chats` endpoint handles both new analysis and chat continuation | New `app/routers/chats.py` with `POST /chats` handler; `ChatRequest` schema with `model_validator` for conditional lang; merged `ChatService.chat()` method |
| EP-02 | Old routes (`POST /prompts/analyze`, `POST /chats/{id}/messages`) removed | Delete `app/routers/prompts.py` entirely; old routes return 404 automatically; explicit 404 tests validate removal |
| EP-03 | `alternatives` field renamed to `suggestions` in response schema | Full-depth rename across `ChatResponseLLM`, `ChatResponse`, prompt template `config/prompt.txt`, and all test assertions |
| EP-04 | `lang` is required when `chat_id` is absent (no silent English default) | `ChatRequest.lang` defaults to `None` (not `"en"`); `model_validator` raises `ValueError` when both `lang` and `chat_id` are `None`; Pydantic validation error maps to 400 `invalid_request` via existing `validation_error_handler` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | installed | Web framework, routing, dependency injection | Already in use; `APIRouter`, `Depends()` patterns established |
| Pydantic | installed (v2) | Request/response schemas, validation | Already in use; `model_validator`, `Field`, `BaseModel` patterns established |
| SQLModel | installed | ORM models for Chat, Message tables | Already in use for `Chat` and `Message` models |
| LangChain | installed | LLM structured output, prompt templates | `ChatPromptTemplate`, `with_structured_output()` already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | installed | Test framework | All test files already use pytest |
| httpx/TestClient | installed | HTTP test client | `fastapi.testclient.TestClient` already used in all test conftest files |

### Alternatives Considered
None -- this phase uses only libraries already in the project. No new dependencies required.

## Architecture Patterns

### Recommended Project Structure
```
app/
├── routers/
│   ├── __init__.py      # Export chats_router, examples_router, health_router, root_router
│   ├── chats.py         # POST /chats, GET /chats/{id}/messages, DELETE /chats/{id}
│   ├── examples.py      # GET /examples
│   ├── health.py        # GET /health/ready (unchanged)
│   └── root.py          # GET / (unchanged)
├── schema.py            # ChatRequest, ChatResponse, ChatResponseLLM, Issue, etc.
├── services.py          # ChatService (renamed from AnalysisService)
├── models.py            # Chat (lang removed), Message
├── chats.py             # Chats class (create_chat signature updated)
├── dependencies.py      # get_service, get_db, get_user_id, get_config (unchanged)
├── errors.py            # Exception handlers (unchanged)
├── exceptions.py        # Exception hierarchy (unchanged)
├── main.py              # Router includes updated
└── config.py            # Unchanged
config/
└── prompt.txt           # Field renames + conditional lang directive
migrations/
└── 001_create_tables.sql  # lang column removed from chats table
```

### Pattern 1: Pydantic model_validator for Conditional Required Fields
**What:** Use `model_validator(mode="after")` on `ChatRequest` to enforce that `lang` is required when `chat_id` is absent. This avoids discriminated unions (FastAPI known issue #13213, per REQUIREMENTS.md Out of Scope).
**When to use:** When field requirement depends on the value of another field.
**Example:**
```python
# Source: established codebase pattern (app/config.py uses model_validator)
from pydantic import BaseModel, Field, model_validator

class ChatRequest(BaseModel):
    text: str = Field(..., max_length=4096, description="The phrase to analyze")
    lang: str | None = Field(default=None, description="Language code (e.g., 'en', 'es')")
    chat_id: UUID | None = Field(default=None, description="Existing chat ID for continuation")

    @model_validator(mode="after")
    def require_lang_for_new_chat(self) -> "ChatRequest":
        if self.chat_id is None and self.lang is None:
            raise ValueError("'lang' is required when starting a new chat (no chat_id)")
        return self
```
**Confidence:** HIGH -- `model_validator(mode="after")` is used twice in `app/config.py` already. Pydantic v2 `ValueError` from validators becomes `RequestValidationError` in FastAPI, which the existing `validation_error_handler` maps to 400 `invalid_request`.

### Pattern 2: Conditional Prompt Template Variable
**What:** Use Python string formatting to conditionally insert a language directive into the system prompt. The prompt template uses `{lang_directive}` placeholder; the service sets it to `"Language: {lang}\n"` or `""`.
**When to use:** When the same prompt template must handle both lang-aware (new chat) and lang-agnostic (continuation) invocations.
**Example:**
```python
# Service builds the lang_directive before chain invocation
if lang:
    lang_directive = f"You are a linguistic assistant for advanced non-native speakers of {lang}."
else:
    lang_directive = ""

# Prompt template has {lang_directive} placeholder
response = await self._invoke(chain, {
    "lang_directive": lang_directive,
    "phrase": text,
    "history": history,
})
```
**Confidence:** HIGH -- `ChatPromptTemplate.from_messages()` with variable substitution is already in use (current prompt uses `{lang}`).

### Pattern 3: Router File Split with Clean Exports
**What:** Each router lives in its own file under `app/routers/`. The `__init__.py` exports named routers. `main.py` imports and includes them.
**When to use:** Always -- this is the established project pattern.
**Example:**

```python
# app/routers/__init__.py
__all__ = ["chats_router", "examples_router", "health_router", "root_router"]

from routers import router as chats_router
from routers.examples import router as examples_router
from routers.health import router as health_router
from routers.root import router as root_router
```
**Confidence:** HIGH -- directly follows the existing `__init__.py` pattern.

### Anti-Patterns to Avoid
- **Discriminated union request body:** FastAPI has known issues with `Union[NewChatRequest, ContinueChatRequest]` as top-level body parameter (fastapi/fastapi#13213). Use flat schema with `model_validator` instead. This is already in REQUIREMENTS.md Out of Scope.
- **Leaving dead code:** After merging to single `chat()` method, do not leave `analyze()` or `_get_chat_lang()` as dead methods. Remove them in the same commit.
- **Renaming fields piecemeal:** `alternatives` -> `suggestions` and `assessment` -> `response` must change atomically across schema, LLM schema, prompt template, service, and tests. A partial rename will cause runtime failures (LLM returns old field names if prompt is not updated, or Pydantic validation fails if schema and LLM output disagree).
- **Silently defaulting lang:** Current `AnalyzeRequest` has `lang: str | None = Field(default="en")`. The new `ChatRequest` MUST default to `None` to enable the validator. Defaulting to `"en"` silently would violate EP-04.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Conditional required field validation | Custom route-level `if` checks | Pydantic `model_validator(mode="after")` | Pydantic validators produce `RequestValidationError` which flows through existing error contract; route handler stays clean |
| Schema field rename consistency | Manual find-and-replace hoping nothing is missed | Grep for old field names after rename and verify zero hits | One missed reference causes silent runtime failures |
| Route removal verification | Manual testing | Explicit 404 assertions in test suite for old routes | Automated regression prevents accidental re-registration |

**Key insight:** This phase is a restructuring/renaming exercise, not new feature development. The risk is not in complexity but in completeness -- missing one reference to an old field name or model name causes a runtime failure. Use systematic search-and-verify after every rename.

## Common Pitfalls

### Pitfall 1: LLM Output Schema Diverges from Prompt Template
**What goes wrong:** The prompt template tells the LLM to produce `"alternatives"` and `"assessment"` JSON keys, but the Pydantic `ChatResponseLLM` schema expects `"suggestions"` and `"response"`. The LLM follows the prompt instructions and produces the old keys. `with_structured_output()` fails or returns empty fields.
**Why it happens:** Schema rename and prompt template rename done in separate commits, or prompt template forgotten entirely.
**How to avoid:** Rename JSON keys in `config/prompt.txt` in the same atomic change as `ChatResponseLLM` field names. The prompt text explicitly shows the JSON schema to the LLM -- both the key names and the field descriptions must match.
**Warning signs:** LLM tests return empty `suggestions` or `response` fields despite non-trivial input.

### Pitfall 2: Chat.lang Column Removal Breaks Existing Data
**What goes wrong:** The `Chat` SQLModel removes `lang`, but the migration still has `lang TEXT NOT NULL` in the CREATE TABLE. Or existing rows in the database have `lang` values that are now unreadable.
**Why it happens:** Migration file not updated, or migration applied without considering existing data.
**How to avoid:** Update `migrations/001_create_tables.sql` to remove the `lang` column. This migration is the schema source of truth for fresh deployments. For existing databases, the column simply becomes unused (no ALTER TABLE needed in this phase since `lang` is being removed from the ORM model, not added). SQLAlchemy will ignore unmapped columns in SELECT.
**Warning signs:** `Chat` model instantiation fails due to extra column, or `create_chat()` still tries to insert `lang`.

### Pitfall 3: Continuation Sends lang=None to Prompt Template
**What goes wrong:** For chat continuations, `lang` is `None`. If the prompt template still has a `{lang}` placeholder without conditional handling, LangChain renders it as `"None"` string, and the LLM receives `"You are a linguistic assistant for advanced non-native speakers of None."`.
**Why it happens:** The current prompt uses `{lang}` directly. After removing `lang` from the continuation path, the prompt template must handle `None` gracefully.
**How to avoid:** Use a `{lang_directive}` placeholder that the service populates as a full sentence (when lang provided) or empty string (when `None`). Do not pass `lang=None` as a raw template variable.
**Warning signs:** LLM responses mention "None" as a language, or language detection fails for continuations.

### Pitfall 4: model_validator ValueError Not Mapped to 400
**What goes wrong:** `model_validator` raises `ValueError`, but the developer expects it to map to 400. If the error contract handler registration is wrong, it could map elsewhere.
**Why it happens:** Misunderstanding of FastAPI validation pipeline.
**How to avoid:** This is already handled correctly. Pydantic `ValueError` inside validators becomes `RequestValidationError`, which is caught by the existing `validation_error_handler` -> 400 `invalid_request`. No new handler needed. Verify with a test.
**Warning signs:** Missing `lang` without `chat_id` returns a status code other than 400.

### Pitfall 5: Test Fixtures Still Reference Old Model Names
**What goes wrong:** Tests import `AnalyzeResponse`, `AnalyzeRequest`, `AnalysisService` after they have been renamed. Import errors across the test suite.
**Why it happens:** Renaming production code without updating all test imports.
**How to avoid:** After renaming, grep the entire codebase for every old name (`AnalyzeRequest`, `AnalyzeResponse`, `AnalyzeResponseLLM`, `AnalysisService`, `ChatMessageRequest`) and verify zero hits outside of git history.
**Warning signs:** `ImportError` or `ModuleNotFoundError` in test collection.

### Pitfall 6: get_chat_owned Returns dict with "lang" Key
**What goes wrong:** `Chats.get_chat_owned()` currently returns `{"id": chat.id, "lang": chat.lang, "user_id": chat.user_id}`. After removing `lang` from the `Chat` model, accessing `chat.lang` raises `AttributeError`.
**Why it happens:** `get_chat_owned()` dict construction not updated after model change.
**How to avoid:** Remove `"lang"` from the returned dict in `get_chat_owned()`. The continuation path no longer needs `lang` from the chat record.
**Warning signs:** `AttributeError: 'Chat' object has no attribute 'lang'` in service layer.

## Code Examples

Verified patterns from the existing codebase:

### ChatRequest Schema (New)
```python
# app/schema.py
from pydantic import BaseModel, Field, model_validator
from uuid import UUID

class ChatRequest(BaseModel):
    text: str = Field(..., max_length=4096, description="The phrase to analyze")
    lang: str | None = Field(default=None, description="Language code (e.g., 'en', 'es')")
    chat_id: UUID | None = Field(default=None, description="Existing chat ID for continuation")

    @model_validator(mode="after")
    def require_lang_for_new_chat(self) -> "ChatRequest":
        if self.chat_id is None and self.lang is None:
            raise ValueError("'lang' is required when starting a new chat")
        return self
```

### ChatResponse Schema (Renamed)
```python
# app/schema.py
class ChatResponse(BaseModel):
    text: str = Field(..., description="The original phrase")
    chat_id: UUID = Field(..., description="Chat session ID")
    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    suggestions: list[str] = Field(default_factory=list, description="Suggested corrections")
    response: str = Field(..., description="Overall assessment of naturalness")
    # NOTE: no lang field -- caller already knows what they sent
```

### ChatResponseLLM Schema (Renamed)
```python
# app/schema.py
class ChatResponseLLM(BaseModel):
    """Schema for LLM structured output."""
    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    suggestions: list[str] = Field(default_factory=list, description="Suggested corrections")
    response: str = Field(..., description="Overall assessment of naturalness")
```

### Unified Router Handler

```python
# app/routers/chats.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_service, get_user_id
from app.schema import ChatRequest, ChatResponse
from services import ChatService

router = APIRouter()


@router.post("/chats", response_model=ChatResponse)
async def create_or_continue_chat(
        body: ChatRequest,
        db: AsyncSession = Depends(get_db),
        user_id: str = Depends(get_user_id),
        service: ChatService = Depends(get_service),
) -> ChatResponse:
    return await service.chat(db, body.text, user_id, lang=body.lang, chat_id=body.chat_id)
```

### Merged Service Method
```python
# app/services.py - ChatService.chat() merges analyze() and chat()
async def chat(
    self,
    db: AsyncSession,
    text: str,
    user_id: str,
    lang: str | None = None,
    chat_id: UUID | None = None,
) -> ChatResponse:
    self._ensure_message_size(text, "user")

    if chat_id:
        # Continuation: verify ownership, check capacity, load history
        await self.chats.get_chat_owned(db, chat_id, user_id)
        await self._ensure_history_capacity(db, chat_id)
    else:
        # New chat: validate lang, create chat
        if lang not in self.examples:
            raise UnsupportedLanguageError(lang=lang, supported=self.supported_languages)
        chat_id = uuid4()
        await self.chats.create_chat(db, chat_id, user_id=user_id)

    history_limit = self.history_max_human_messages + self.history_max_assistant_messages
    history = await self.chats.load_history(db, chat_id, limit=history_limit)

    # Build lang_directive conditionally
    lang_directive = (
        f"You are a linguistic assistant for advanced non-native speakers of {lang}."
        if lang else ""
    )

    response = await self._invoke(
        self.chain,
        {"lang_directive": lang_directive, "phrase": text, "history": history}
    )

    assistant_payload = str(response.model_dump())
    self._ensure_message_size(assistant_payload, "assistant")
    await self.chats.save_messages(db, chat_id, f"Analyze this phrase: {text}", assistant_payload)

    return ChatResponse(text=text, chat_id=chat_id, **response.model_dump())
```

### Conditional Prompt Template
```
{lang_directive}
Your task is to make their sentences sound fully native while keeping the original meaning and most original words.
...
{{
  "response": "Always present. For phrases: headline-style summary of issues or 'No issues found'. For questions: your answer.",
  "issues": [
    {{
      "text_part": "Smallest text span containing the issue",
      "explanation": "Short explanation of the issue"
    }}
  ],
  "suggestions": [
    "Corrected versions of the entire phrase"
  ]
}}
```

### Updated Chat Model (lang removed)
```python
# app/models.py
class Chat(SQLModel, table=True):
    __tablename__ = "chats"
    id: UUID = Field(primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    created_at: datetime | None = Field(default=None, sa_column_kwargs={"server_default": "now()"})
    # lang column removed
```

### Updated Chats.create_chat (lang removed)
```python
# app/chats.py
async def create_chat(self, db: AsyncSession, chat_id: UUID, user_id: str) -> None:
    db.add(Chat(id=chat_id, user_id=user_id))
    await db.commit()
```

### Updated get_chat_owned (lang removed from return)
```python
# app/chats.py
async def get_chat_owned(self, db: AsyncSession, chat_id: UUID, user_id: str) -> dict:
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise InvalidChatError(chat_id)
    if chat.user_id != user_id:
        raise ChatOwnershipError(chat_id)
    return {"id": chat.id, "user_id": chat.user_id}
    # "lang" key removed -- no longer stored on chat
```

### Examples Router (New File)

```python
# app/routers/examples.py
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_service
from app.schema import ExamplesResponse
from services import ChatService

router = APIRouter()


@router.get("/examples", response_model=ExamplesResponse)
async def get_examples(
        lang: str = Query(..., description="Language code (e.g., 'en', 'es')"),
        service: ChatService = Depends(get_service),
) -> ExamplesResponse:
    return service.get_examples(lang)
```

### Updated main.py Router Includes

```python
# app/main.py
from routers import chats_router, examples_router, health_router, root_router

# prompts_router removed

app.include_router(root_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
```

### Updated Router __init__.py

```python
# app/routers/__init__.py
__all__ = ["chats_router", "examples_router", "health_router", "root_router"]

from routers import router as chats_router
from routers.examples import router as examples_router
from routers.health import router as health_router
from routers.root import router as root_router
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `lang` stored on Chat model | `lang` is per-request hint | Phase 13 | Each message in a chat can be in a different language |
| Separate analyze + chat endpoints | Single `POST /chats` | Phase 13 | Simpler API surface, consistent behavior |
| `alternatives` field name | `suggestions` field name | Phase 13 | Breaking change -- clients must update |
| `assessment` field name | `response` field name | Phase 13 | Breaking change -- clients must update |
| `default="en"` for lang | `default=None` with validator | Phase 13 | Explicit lang required -- no silent English default |

**Deprecated/outdated (removed in this phase):**
- `POST /prompts/analyze`: replaced by `POST /chats`
- `POST /chats/{chat_id}/messages`: replaced by `POST /chats` with `chat_id` in body
- `GET /prompts/examples`: replaced by `GET /examples`
- `AnalyzeRequest`, `AnalyzeResponse`, `AnalyzeResponseLLM`, `AnalysisService`: renamed
- `ChatMessageRequest`: deleted
- `_get_chat_lang()`: deleted
- `service.analyze()`: merged into `service.chat()`

## Open Questions

1. **Chain construction with conditional prompt**
   - What we know: The current `AnalysisService.__init__` builds `self.chain` once at construction with a fixed prompt template containing `{lang}`. The new service must handle `{lang_directive}` which changes per-call (empty for continuations, populated for new chats).
   - What's unclear: Whether the chain should be rebuilt per-call or if the template variable substitution is sufficient. Current evidence suggests `ChatPromptTemplate` variable substitution at `ainvoke()` time handles this -- `{lang_directive}` is just another template variable like `{phrase}`.
   - Recommendation: Keep `self.chain` built in `__init__` with `{lang_directive}` placeholder. The template variable is resolved at `ainvoke()` time. This is how `{lang}` and `{phrase}` already work. No need to rebuild the chain per-call. **Confidence: HIGH** -- this is how LangChain `ChatPromptTemplate` works; variables are resolved at invocation, not at construction.

2. **SQLAlchemy behavior with unmapped columns**
   - What we know: Removing `lang` from the `Chat` SQLModel means the ORM no longer maps that column. For fresh deployments, the migration is updated. For existing databases, the `lang` column still exists in the table.
   - What's unclear: Whether SQLAlchemy will error when the table has a column not mapped by the ORM.
   - Recommendation: SQLAlchemy ignores unmapped columns in `SELECT` queries -- this is standard ORM behavior. The `Chat` model simply will not include `lang` in its column list. Existing data is unaffected. No `ALTER TABLE` needed. **Confidence: HIGH** -- verified behavior of SQLAlchemy ORM.

3. **Cross-user isolation test updates**
   - What we know: `tests/integration/test_cross_user_isolation.py` currently tests `POST /chats/{chat_id}/messages` (line 49) which is being removed. It also references old error contract format (`body["status"]`, `body["error"]`) from pre-Phase-11 era.
   - What's unclear: Whether these tests should be updated or left as-is (they seem to already be stale from the Phase 11 error contract changes).
   - Recommendation: The cross-user isolation tests need updating to use the new `POST /chats` endpoint (with `chat_id` in body) and the current error contract format (`body["code"]`). These tests are integration tests that require a real DB, so they may be updated to match the new endpoint shape.

## Comprehensive Impact Analysis

### Files to Create
| File | Purpose |
|------|---------|
| `app/routers/chats.py` | New unified chats router: `POST /chats`, `GET /chats/{id}/messages`, `DELETE /chats/{id}` |
| `app/routers/examples.py` | New examples router: `GET /examples` |

### Files to Modify
| File | Changes |
|------|---------|
| `app/schema.py` | Rename `AnalyzeRequest` -> `ChatRequest` (add `model_validator`), `AnalyzeResponse` -> `ChatResponse` (remove `lang`, rename fields), `AnalyzeResponseLLM` -> `ChatResponseLLM` (rename fields), delete `ChatMessageRequest` |
| `app/services.py` | Rename `AnalysisService` -> `ChatService`, merge `analyze()` + `chat()` -> `chat()`, delete `_get_chat_lang()`, update chain construction for `{lang_directive}` |
| `app/models.py` | Remove `lang` field from `Chat` model |
| `app/chats.py` | Remove `lang` param from `create_chat()`, remove `"lang"` from `get_chat_owned()` return dict |
| `app/routers/__init__.py` | Update exports: remove `prompts_router`, `chats_router`; add new `chats_router`, `examples_router` |
| `app/main.py` | Update imports and `include_router()` calls; rename `AnalysisService` -> `ChatService` in lifespan |
| `app/dependencies.py` | Update import: `AnalysisService` -> `ChatService`; update type annotation in `get_service()` |
| `config/prompt.txt` | Rename JSON keys `alternatives` -> `suggestions`, `assessment` -> `response`; change first line to `{lang_directive}` placeholder |
| `migrations/001_create_tables.sql` | Remove `lang TEXT NOT NULL` from chats table |
| `tests/conftest.py` | Update all imports, model names, field names; update `client` fixture for new router structure |
| `tests/integration/conftest.py` | Update `create_chat()` helper (remove `lang` param), update imports, update router includes |
| `tests/integration/test_prompts_endpoints.py` | Rename to match new router; update endpoint paths, model names, field names; add 404 tests for old routes |
| `tests/unit/test_services.py` | Update class/method names, field names in assertions and mock data |
| `tests/unit/test_models.py` | Update schema class names and field names in all assertions |
| `tests/llm/test_real_llm.py` | Update endpoint path from `/prompts/analyze` to `/chats`, update field assertions |
| `tests/integration/test_cross_user_isolation.py` | Update endpoint path for POST test, fix error contract assertions |

### Files to Delete
| File | Reason |
|------|--------|
| `app/routers/prompts.py` | All endpoints moved to `chats.py` and `examples.py` |

### Rename Manifest (Exhaustive)
| Old Name | New Name | Files Affected |
|----------|----------|----------------|
| `AnalyzeRequest` | `ChatRequest` | `schema.py`, `services.py` (type hint if any), `test_models.py`, `test_prompts_endpoints.py` |
| `AnalyzeResponse` | `ChatResponse` | `schema.py`, `services.py`, `routers/chats.py`, `test_prompts_endpoints.py`, `test_services.py`, `test_models.py` |
| `AnalyzeResponseLLM` | `ChatResponseLLM` | `schema.py`, `services.py`, `test_services.py` |
| `AnalysisService` | `ChatService` | `services.py`, `dependencies.py`, `main.py`, `conftest.py`, `integration/conftest.py`, `test_services.py`, `routers/root.py`, `routers/chats.py`, `routers/examples.py` |
| `alternatives` (field) | `suggestions` | `schema.py` (2 models), `prompt.txt`, `test_services.py`, `test_models.py`, `test_prompts_endpoints.py`, `test_real_llm.py` |
| `assessment` (field) | `response` | `schema.py` (2 models), `prompt.txt`, `test_services.py`, `test_models.py`, `test_prompts_endpoints.py`, `test_real_llm.py` |
| `ChatMessageRequest` | (deleted) | `schema.py`, `test_models.py` |
| `prompts_router` | (deleted) | `routers/__init__.py`, `main.py`, `conftest.py` |

## Sources

### Primary (HIGH confidence)
- Codebase direct inspection: `app/schema.py`, `app/services.py`, `app/main.py`, `app/models.py`, `app/chats.py`, `app/dependencies.py`, `app/errors.py`, `app/exceptions.py`, `app/config.py`, `app/routers/prompts.py`, `app/routers/__init__.py`, `app/routers/root.py`, `app/routers/health.py`, `config/prompt.txt`, `migrations/001_create_tables.sql`
- Test files: `tests/conftest.py`, `tests/integration/conftest.py`, `tests/integration/test_prompts_endpoints.py`, `tests/unit/test_services.py`, `tests/unit/test_models.py`, `tests/unit/test_exception_handlers.py`, `tests/unit/test_error_contract.py`, `tests/integration/test_cross_user_isolation.py`, `tests/llm/test_real_llm.py`
- `.planning/research/ARCHITECTURE.md` -- prior architecture research for v1.3
- `.planning/research/FEATURES.md` -- prior feature research including model_validator pattern
- `.planning/REQUIREMENTS.md` -- EP-01 through EP-04 requirements and Out of Scope notes

### Secondary (MEDIUM confidence)
- Pydantic v2 `model_validator(mode="after")` -- established in codebase (`app/config.py` lines 55, 93), consistent with Pydantic v2 docs
- FastAPI `RequestValidationError` -> error handler pipeline -- verified by existing `validation_error_handler` in `app/errors.py`
- SQLAlchemy unmapped column behavior -- standard ORM behavior, not codebase-specific

### Tertiary (LOW confidence)
- None -- all findings verified against codebase or established patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all libraries already in use
- Architecture: HIGH -- follows established codebase patterns (routers, DI, model_validator, error contract)
- Pitfalls: HIGH -- all pitfalls identified from direct codebase inspection and prior research docs

**Research date:** 2026-03-02
**Valid until:** 2026-04-01 (30 days -- stable domain, no external dependency changes)
