# Phase 32: Rewrite Models to Match Prompt Schema - Research

**Researched:** 2026-03-25
**Domain:** Pydantic model restructuring, LLM contract alignment, FastAPI schema changes
**Confidence:** HIGH

## Summary

This phase rewrites the entire content model layer to align with the LLM input/output contract defined in `config/prompt.txt`. The current approach uses typed Pydantic models (`HumanContent`, `AIContent`) with a custom `PydanticJSONB` SQLAlchemy type decorator and a discriminated union (`ContentUnion`). The new approach replaces all of this with plain `dict` for persistence and transport, using Pydantic models only for LLM input construction and output validation.

The scope is wide but mechanically straightforward: delete `models/content.py`, create `models/llm.py` with validation-only models, move `schema.py` to `models/api.py` with field renames, update `Message.content` to plain `dict` with `sa_type=JSONB`, rewrite `ChatService.ask_llm` for manual dispatch with reject handling, add `OutOfScopeError`, and update all imports across source and test files.

**Primary recommendation:** Execute in dependency order -- exceptions first, then models/llm.py, then models/api.py (moved from schema.py), then ORM column change, then service layer rewrite, then router/import updates, then test updates. Each step should leave unit tests passing before proceeding.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Discriminated union with 3 separate response models: `AnalyzeResponse` (resolved_mode="analyze", response, issues, suggestions), `FollowUpResponse` (resolved_mode="follow_up", response), `RejectResponse` (resolved_mode="reject", response)
- **D-02:** `AnalyzeResponse.issues` and `AnalyzeResponse.suggestions` are always present (non-optional), possibly empty lists. No `None` values.
- **D-03:** Discriminated union with 2 input models: `AnalyzeInput` (mode="analyze", phrase, context?) and `FollowUpInput` (mode="follow_up", question)
- **D-04:** These models are used to construct and validate LLM input, then `.model_dump(exclude_none=True)` produces the dict stored as content
- **D-05:** `Message.content` is a plain `dict` everywhere -- DB column, service layer, API responses. No Pydantic model wrapping at the persistence or transport layer.
- **D-06:** `Message.content` column defined as `dict = Field(sa_type=JSONB)`. `PydanticJSONB` and `ContentUnion` deleted entirely.
- **D-07:** `MessageResponse.content` is `dict` -- no typed content in API responses. OpenAPI shows it as `object`.
- **D-08:** LLM `resolved_mode="reject"` raises `OutOfScopeError` -> HTTP 400 with `out_of_scope` error code
- **D-09:** On reject, neither the human message nor the AI response is persisted to the database
- **D-10:** `out_of_scope` added as new value to `ErrorCode` Literal
- **D-11:** `ChatRequest.comment` renamed to `ChatRequest.context` (optional str, max 4096)
- **D-12:** `MessageRequest.comment` renamed to `MessageRequest.question` (required str, max 4096)
- **D-13:** Breaking API change accepted -- no backward compatibility needed
- **D-14:** `schema.py` moved to `models/api.py`
- **D-15:** New `models/llm.py` for LLM validation models (`Issue`, `AnalyzeInput`, `FollowUpInput`, `AnalyzeResponse`, `FollowUpResponse`, `RejectResponse`)
- **D-16:** `models/content.py` deleted entirely
- **D-17:** `models/__init__.py` re-exports from both `api.py` and `llm.py`
- **D-18:** Manual dispatch on `response["resolved_mode"]` in `ChatService.ask_llm` -- check for reject first, then validate against `AnalyzeResponse` or `FollowUpResponse`. No union type or TypeAdapter needed.
- **D-19:** LLM input built via `AnalyzeInput`/`FollowUpInput` models, then `.model_dump(exclude_none=True)` to get dict. Optional fields (like `context`) excluded when None to match prompt spec.
- **D-20:** History messages serialized with a fast minimal JSON serializer (e.g., `orjson`) since content is now plain dict
- **D-21:** Database will be wiped and recreated -- no data migration needed for existing JSONB content

### Claude's Discretion
- Choice of fast JSON serializer for history serialization (orjson or similar minimal dependency)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | LLM input/output validation models, API request/response schemas | Already in use; `model_dump(exclude_none=True)` and `model_validate()` are the primary tools |
| sqlmodel | >=0.0.22 | ORM with `Field(sa_type=JSONB)` for plain dict column | Already in use; switching from `PydanticJSONB` custom type to native JSONB |
| orjson | >=3.11 | Fast JSON serialization for history messages (dict -> str) | 3.11.7 already in venv; ~6x faster than stdlib json for dict serialization |
| fastapi | 0.135.1 | API framework, error handling | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlalchemy (postgresql dialect) | via sqlmodel | `JSONB` type import for sa_type | Column type definition |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| orjson | stdlib json | json.dumps works fine; orjson is ~6x faster but adds a dependency. Since content is plain dict (not Pydantic models), either works. orjson is already in the venv. |
| orjson | msgspec | Another fast JSON library, but heavier dependency; orjson is the most common choice. |

**Recommendation for Claude's Discretion (D-20):** Use `orjson`. It is already installed in the project venv (3.11.7), requires only adding `"orjson>=3.11"` to `pyproject.toml`, and provides the fastest dict-to-JSON-string path. The API is minimal: `orjson.dumps(d).decode()` returns a str.

**Installation:**
```bash
# orjson already in venv, just add to pyproject.toml dependencies
# "orjson>=3.11"
```

## Architecture Patterns

### Recommended Project Structure (after phase)
```
src/nativespeaker/api/
    models/
        __init__.py      # Re-exports from api.py, llm.py, chats.py, users.py, subscriptions.py
        api.py           # API request/response schemas (moved from schema.py)
        llm.py           # LLM validation models (NEW)
        chats.py         # Chat, Message SQLModels (content: dict)
        users.py         # User SQLModel (unchanged)
        subscriptions.py # Subscription models (unchanged)
    models/content.py    # DELETED
    schema.py            # DELETED (moved to models/api.py)
    exceptions.py        # +OutOfScopeError, +out_of_scope ErrorCode
    services/
        chats.py         # Rewritten ask_llm, create_chat, send_message
```

### Pattern 1: LLM Validation-Only Models (models/llm.py)
**What:** Pydantic models used exclusively for constructing LLM input and validating LLM output. Never persisted or transported.
**When to use:** Building the JSON payload sent to the LLM chain, and validating the raw dict returned by `JsonOutputParser`.
**Example:**
```python
from typing import Literal
from pydantic import BaseModel

class Issue(BaseModel):
    text_part: str
    explanation: str

class AnalyzeInput(BaseModel):
    mode: Literal["analyze"] = "analyze"
    phrase: str
    context: str | None = None

class FollowUpInput(BaseModel):
    mode: Literal["follow_up"] = "follow_up"
    question: str

class AnalyzeResponse(BaseModel):
    resolved_mode: Literal["analyze"]
    response: str
    issues: list[Issue]
    suggestions: list[str]

class FollowUpResponse(BaseModel):
    resolved_mode: Literal["follow_up"]
    response: str

class RejectResponse(BaseModel):
    resolved_mode: Literal["reject"]
    response: str
```

### Pattern 2: Manual Dispatch in ask_llm (D-18)
**What:** Check `response["resolved_mode"]` explicitly, handle reject first, then validate with the correct model.
**When to use:** In `ChatService.ask_llm` after receiving raw dict from LLM.
**Example:**
```python
import orjson
from nativespeaker.api.models.llm import AnalyzeInput, FollowUpInput, AnalyzeResponse, FollowUpResponse

async def ask_llm(self, chat: Chat, message: Message) -> Message:
    lang_directive = chat.lang or "various languages (autodetect)"
    history = []
    for history_msg in chat.messages:
        history.append(
            HumanMessage(content=orjson.dumps(history_msg.content).decode())
            if history_msg.role == ChatRole.human
            else AIMessage(content=orjson.dumps(history_msg.content).decode())
        )

    llm_response = await self.llm_service.ainvoke(
        history=history,
        content=orjson.dumps(message.content).decode(),
        lang=lang_directive
    )

    resolved_mode = llm_response.get("resolved_mode")
    if resolved_mode == "reject":
        raise OutOfScopeError()
    elif resolved_mode == "analyze":
        AnalyzeResponse.model_validate(llm_response)
    elif resolved_mode == "follow_up":
        FollowUpResponse.model_validate(llm_response)
    else:
        raise AnalysisError(f"Unexpected resolved_mode: {resolved_mode}")

    return Message(chat_id=chat.id, role=ChatRole.ai, content=llm_response)
```

### Pattern 3: Input Construction with model_dump (D-04, D-19)
**What:** Build LLM input as Pydantic model, then dump to dict for storage.
**When to use:** In `create_chat` and `send_message` when building the human message content.
**Example:**
```python
# create_chat: analyze mode
input_model = AnalyzeInput(phrase=phrase, context=context)
content = input_model.model_dump(exclude_none=True)
# Result: {"mode": "analyze", "phrase": "...", "context": "..."} or without context key if None
human_message = Message(chat_id=chat.id, role=ChatRole.human, content=content)

# send_message: follow_up mode
input_model = FollowUpInput(question=question)
content = input_model.model_dump(exclude_none=True)
# Result: {"mode": "follow_up", "question": "..."}
human_message = Message(chat_id=chat.id, role=ChatRole.human, content=content)
```

### Pattern 4: Reject Flow (D-08, D-09)
**What:** When LLM returns `resolved_mode="reject"`, raise `OutOfScopeError` before persisting any messages.
**When to use:** In `ask_llm`, checked before the messages get appended to the chat.
**Key insight:** `ask_llm` is called BEFORE `chat.messages.append(human_message)` and `chat.messages.append(ai_message)` in both `create_chat` and `send_message`. The exception propagates up, so neither message is ever appended or persisted. This is already the correct flow -- both callers do:
```python
ai_message = await self.ask_llm(chat, human_message)  # raises on reject
chat.messages.append(human_message)  # only reached if no reject
chat.messages.append(ai_message)
```

### Anti-Patterns to Avoid
- **Union type for LLM dispatch:** Do not use `TypeAdapter` or Pydantic discriminated union for validating LLM output. Manual dispatch is simpler and more explicit (D-18).
- **Pydantic models in persistence layer:** Do not wrap `Message.content` in any Pydantic model. It is plain `dict` at rest and in transit (D-05, D-06, D-07).
- **Optional issues/suggestions:** Do not make `AnalyzeResponse.issues` or `AnalyzeResponse.suggestions` optional. They are always present, possibly empty (D-02).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization of dict | Custom serializer or json.dumps | `orjson.dumps(d).decode()` | 6x faster, already available |
| LLM output schema validation | Manual dict key checking | Pydantic `model_validate()` | Catches type errors, missing fields, extra fields |
| JSONB column type | Custom `TypeDecorator` | `Field(sa_type=JSONB)` with `dict` annotation | SQLAlchemy handles serialization natively |

**Key insight:** The `PydanticJSONB` custom TypeDecorator was necessary when content was a Pydantic model. With plain `dict`, native `JSONB` column type handles everything.

## Common Pitfalls

### Pitfall 1: Import Cycle in models/__init__.py
**What goes wrong:** `models/chats.py` currently imports `ContentUnion` from `models/__init__.py` which re-exports from `models/content.py`. When moving things around, circular imports can appear.
**Why it happens:** `models/__init__.py` aggregates exports; `chats.py` imports from it.
**How to avoid:** After deleting `content.py`, `chats.py` should import `JSONB` directly from `sqlalchemy.dialects.postgresql`. Remove the `ContentUnion` import entirely. `chats.py` no longer needs any content-related imports.
**Warning signs:** `ImportError: cannot import name 'X' from partially initialized module`

### Pitfall 2: Stale Imports in Test Files
**What goes wrong:** Tests import `AIContent`, `HumanContent`, `Issue` from `models.content` and `schema`. These paths will break.
**Why it happens:** 6 test files import these symbols (unit: test_models.py, test_services.py, test_exception_handlers.py; e2e: conftest.py).
**How to avoid:** Systematic search-and-replace. After the move:
- `Issue` moves from `models.content` to `models.llm`
- `AIContent`, `HumanContent` are DELETED -- tests must use plain `dict` instead
- `ChatRequest`, `MessageRequest`, etc. move from `schema` to `models.api`
- `ErrorResponse` moves from `schema` to `models.api`
**Warning signs:** `ModuleNotFoundError` or `ImportError` in test runs

### Pitfall 3: E2E Tests Use Old Field Names
**What goes wrong:** E2E tests send `{"comment": "..."}` (D-11 renames to `context`) and `{"content": "..."}` (D-12 renames to `question`) in request bodies.
**Why it happens:** Field renames are breaking API changes (D-13 accepts this).
**How to avoid:** Update all e2e test request payloads:
- `test_chats.py` line 39: `"comment"` -> `"context"` in create_chat payload
- `test_chats.py` line 61: `"content"` -> `"question"` in followup payload
- `test_flows.py` line 21: `"content"` -> `"question"` in followup payload
- `test_error_cases.py` line 24: `"content"` -> `"question"` in followup payload
**Warning signs:** 422 validation errors in e2e tests

### Pitfall 4: ask_llm Return Value Change
**What goes wrong:** `ask_llm` currently returns `Message(..., content=AIContent.model_validate(llm_response))`. The new version returns `Message(..., content=llm_response)` (raw dict). Tests that assert `result.content.response` (attribute access on Pydantic model) must change to `result.content["response"]` (dict access).
**Why it happens:** Content changes from Pydantic BaseModel to plain dict.
**How to avoid:** Update all test assertions from `.content.X` attribute access to `.content["X"]` dict access.
**Warning signs:** `AttributeError: 'dict' object has no attribute 'response'`

### Pitfall 5: History Serialization Change
**What goes wrong:** Current code does `history_msg.content.model_dump_json()` which works on Pydantic models. With `dict` content, `model_dump_json()` does not exist.
**Why it happens:** `dict` has no `.model_dump_json()` method.
**How to avoid:** Replace with `orjson.dumps(history_msg.content).decode()`.
**Warning signs:** `AttributeError: 'dict' object has no attribute 'model_dump_json'`

### Pitfall 6: Mock Return Values in Service Tests
**What goes wrong:** Service tests mock `llm_service.ainvoke.return_value` as `AIContent(...)`. The new service expects `ainvoke` to return a raw `dict` (which `JsonOutputParser` already does in production).
**Why it happens:** Tests were testing the old code path where `ainvoke` returned Pydantic models.
**How to avoid:** Change mock return values from `AIContent(response=..., issues=..., suggestions=...)` to `{"resolved_mode": "analyze", "response": "...", "issues": [...], "suggestions": [...]}` raw dicts. Note: the new dicts must include `resolved_mode` since the dispatch logic needs it.
**Warning signs:** `KeyError: 'resolved_mode'` or Pydantic validation errors in tests

### Pitfall 7: ErrorCode Literal Must Include out_of_scope
**What goes wrong:** The `ErrorCode` Literal type constrains allowed values. Adding `out_of_scope` requires updating both the Literal definition AND the error handler's `_CODE_MAP`.
**Why it happens:** The error handler maps HTTP status codes to error codes. `OutOfScopeError` uses status 400, and `_CODE_MAP[400]` is currently `"invalid_request"`. Since `OutOfScopeError` extends `ServiceError`, it goes through `service_error_handler` which uses `exc.error_code` directly -- so `_CODE_MAP` does NOT need updating. But the `ErrorCode` Literal must include `"out_of_scope"` for type safety.
**How to avoid:** Add `"out_of_scope"` to the `ErrorCode` Literal. The exception handler test list (`CASES` in test_exception_handlers.py) should also include the new error.
**Warning signs:** Pydantic validation error when constructing `ErrorResponse(code="out_of_scope")`

### Pitfall 8: errors.py Imports ErrorResponse from schema.py
**What goes wrong:** `app/errors.py` and `app/main.py` both import `ErrorResponse` from `nativespeaker.api.schema`. After moving `schema.py` to `models/api.py`, these imports break.
**Why it happens:** Two import sites outside the models package reference schema.py directly.
**How to avoid:** Update imports to `from nativespeaker.api.models.api import ErrorResponse` or add `ErrorResponse` to `models/__init__.py` re-exports.
**Warning signs:** `ModuleNotFoundError: No module named 'nativespeaker.api.schema'`

## Code Examples

### New models/llm.py (complete)
```python
from typing import Literal

from pydantic import BaseModel


class Issue(BaseModel):
    text_part: str
    explanation: str


class AnalyzeInput(BaseModel):
    mode: Literal["analyze"] = "analyze"
    phrase: str
    context: str | None = None


class FollowUpInput(BaseModel):
    mode: Literal["follow_up"] = "follow_up"
    question: str


class AnalyzeResponse(BaseModel):
    resolved_mode: Literal["analyze"]
    response: str
    issues: list[Issue]
    suggestions: list[str]


class FollowUpResponse(BaseModel):
    resolved_mode: Literal["follow_up"]
    response: str


class RejectResponse(BaseModel):
    resolved_mode: Literal["reject"]
    response: str
```

### Updated exceptions.py (OutOfScopeError addition)
```python
ErrorCode = Literal["invalid_request",
                    "validation_error",
                    "unauthorized",
                    "not_found",
                    "service_unavailable",
                    "internal_error",
                    "rate_limited",
                    "out_of_scope"]

# ... existing exceptions ...

class OutOfScopeError(ServiceError):
    status_code = 400
    error_code = "out_of_scope"

    def __init__(self):
        super().__init__("The request is outside the scope of linguistic analysis")
```

### Updated Message model (chats.py)
```python
from sqlalchemy.dialects.postgresql import JSONB

class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    chat_id: UUID = Field(foreign_key="core.chats.id", ondelete="CASCADE")
    role: ChatRole = Field(sa_type=ChatRoleType)
    content: dict = Field(sa_type=JSONB)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```

### Updated ChatService.ask_llm
```python
import orjson
from nativespeaker.api.exceptions import AnalysisError, OutOfScopeError
from nativespeaker.api.models.llm import AnalyzeInput, AnalyzeResponse, FollowUpInput, FollowUpResponse

async def ask_llm(self, chat: Chat, message: Message) -> Message:
    lang_directive = chat.lang or "various languages (autodetect)"
    history = []
    for history_msg in chat.messages:
        if history_msg.role == ChatRole.human:
            history.append(HumanMessage(content=orjson.dumps(history_msg.content).decode()))
        else:
            history.append(AIMessage(content=orjson.dumps(history_msg.content).decode()))

    llm_response = await self.llm_service.ainvoke(
        history=history,
        content=orjson.dumps(message.content).decode(),
        lang=lang_directive
    )

    resolved_mode = llm_response.get("resolved_mode")
    if resolved_mode == "reject":
        raise OutOfScopeError()
    elif resolved_mode == "analyze":
        AnalyzeResponse.model_validate(llm_response)
    elif resolved_mode == "follow_up":
        FollowUpResponse.model_validate(llm_response)
    else:
        raise AnalysisError(f"Unexpected resolved_mode: {resolved_mode}")

    return Message(chat_id=chat.id, role=ChatRole.ai, content=llm_response)
```

### Updated create_chat and send_message
```python
async def create_chat(self,
                      user: User,
                      phrase: str,
                      context: str | None = None,
                      lang: str | None = None) -> Message:
    # ... validation ...
    chat = Chat(id=uuid4(), user_id=user.id, title=phrase, lang=lang)
    input_model = AnalyzeInput(phrase=phrase, context=context)
    human_message = Message(chat_id=chat.id, role=ChatRole.human,
                            content=input_model.model_dump(exclude_none=True))
    ai_message = await self.ask_llm(chat, human_message)
    chat.messages.append(human_message)
    chat.messages.append(ai_message)
    self.chats_db.create_chat(chat)
    return ai_message

async def send_message(self,
                       chat_id: UUID,
                       user: User,
                       question: str) -> Message:
    # ... validation ...
    input_model = FollowUpInput(question=question)
    human_message = Message(chat_id=chat.id, role=ChatRole.human,
                            content=input_model.model_dump(exclude_none=True))
    ai_message = await self.ask_llm(chat=chat, message=human_message)
    chat.messages.append(human_message)
    chat.messages.append(ai_message)
    return ai_message
```

## Impact Analysis: Complete File-by-File

### Source Files to Modify

| File | Change Type | Details |
|------|-------------|---------|
| `exceptions.py` | Add | `out_of_scope` to ErrorCode Literal; new `OutOfScopeError` class |
| `models/content.py` | Delete | Entire file removed |
| `models/llm.py` | Create | 6 new models: Issue, AnalyzeInput, FollowUpInput, AnalyzeResponse, FollowUpResponse, RejectResponse |
| `schema.py` -> `models/api.py` | Move+Modify | Move file; rename `ChatRequest.comment` -> `context`, `MessageRequest.comment` -> `question`, `MessageResponse.content` type -> `dict`; remove `HumanContent`/`AIContent` imports |
| `models/chats.py` | Modify | `Message.content` from `BaseModel = Field(sa_type=PydanticJSONB(ContentUnion))` to `dict = Field(sa_type=JSONB)` ; remove ContentUnion/PydanticJSONB imports |
| `models/__init__.py` | Modify | Remove content.py re-exports; add llm.py re-exports; add api.py re-exports |
| `services/chats.py` | Major rewrite | ask_llm dispatch logic, create_chat/send_message input construction, orjson imports, parameter renames |
| `routers/chats.py` | Modify | Import from `models.api` instead of `schema`; `body.comment` -> `body.context` / `body.question` |
| `routers/examples.py` | Modify | Import from `models.api` instead of `schema` |
| `routers/users.py` | Modify | Import from `models.api` instead of `schema` |
| `app/errors.py` | Modify | Import from `models.api` instead of `schema` |
| `app/main.py` | Modify | Import from `models.api` instead of `schema` |
| `pyproject.toml` | Modify | Add `"orjson>=3.11"` to dependencies |

### Test Files to Modify

| File | Change Type | Details |
|------|-------------|---------|
| `tests/unit/test_models.py` | Major rewrite | Remove AIContent/HumanContent tests; add llm model tests; update MessageResponse tests for dict content; update imports |
| `tests/unit/test_services.py` | Major rewrite | Mock returns become dicts with resolved_mode; assertions use dict access; parameter renames |
| `tests/unit/test_exception_handlers.py` | Modify | Add OutOfScopeError to CASES list |
| `tests/unit/conftest.py` | Modify | Remove AIContent/HumanContent imports; update service fixture for new parameter names |
| `tests/e2e/conftest.py` | Modify | `create_chat` helper uses plain dicts for content instead of HumanContent/AIContent |
| `tests/e2e/test_chats.py` | Modify | Field name changes: `"comment"` -> `"context"`, `"content"` -> `"question"` |
| `tests/e2e/test_flows.py` | Modify | Field name changes in request payloads |
| `tests/e2e/test_error_cases.py` | Modify | Field name changes in request payloads |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom PydanticJSONB TypeDecorator | Plain `dict` + native `JSONB` | This phase | Simpler ORM; no custom type decorator |
| Typed content in API responses | `dict` (OpenAPI: `object`) | This phase | Less strict API contract, but matches actual usage |
| `model_dump_json()` for history | `orjson.dumps(dict).decode()` | This phase | No Pydantic overhead for serialization |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.14.3 | -- |
| Pydantic | Model validation | Yes | 2.12.5 | -- |
| orjson | History serialization (D-20) | Yes | 3.11.7 | stdlib json (slower) |
| SQLAlchemy JSONB | Column type | Yes | via sqlmodel | -- |
| pytest | Unit tests | Yes | >=9.0 | -- |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:**
- orjson is in the venv but not in `pyproject.toml` -- must be added as an explicit dependency

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 + pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/unit/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | Three separate LLM response models validate correctly | unit | `python -m pytest tests/unit/test_models.py -x -q` | Needs update |
| D-02 | AnalyzeResponse.issues/suggestions are non-optional lists | unit | `python -m pytest tests/unit/test_models.py -x -q` | Needs update |
| D-03 | Two input models construct correctly, exclude_none works | unit | `python -m pytest tests/unit/test_models.py -x -q` | Needs update |
| D-05/D-06/D-07 | Message.content is dict, MessageResponse.content is dict | unit | `python -m pytest tests/unit/test_models.py -x -q` | Needs update |
| D-08 | OutOfScopeError -> HTTP 400 with out_of_scope code | unit | `python -m pytest tests/unit/test_exception_handlers.py -x -q` | Needs update |
| D-09 | Reject prevents message persistence | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs new test |
| D-11/D-12 | ChatRequest.context, MessageRequest.question field names | unit | `python -m pytest tests/unit/test_models.py -x -q` | Needs update |
| D-18 | Manual dispatch validates correct model per resolved_mode | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs update |
| D-19 | Input models produce correct dict via model_dump | unit | `python -m pytest tests/unit/test_models.py -x -q` | Needs new test |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `python -m pytest tests/unit/ -v`
- **Phase gate:** Full unit suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_models.py` -- rewrite for new model structure (LLM models, dict content, field renames)
- [ ] `tests/unit/test_services.py` -- rewrite mock returns and assertions for dict-based flow + reject test
- [ ] `tests/unit/test_exception_handlers.py` -- add OutOfScopeError case

## Project Constraints (from CLAUDE.md)

- **Don't commit .planning dir** -- git operations must exclude `.planning/`
- **Opening delimiter alignment style** -- multiline function signatures use the project's alignment style
- **Context7 MCP for library docs** -- use Context7 for API documentation
- **Don't use string-based module references in tests** -- import directly, no `"module.path"` strings
- **Shorter branch names** -- if creating a branch, keep it concise

## Open Questions

1. **E2E test `test_chats.py` follow-up uses `"content"` key**
   - What we know: The e2e test sends `json={"content": "Can you explain more?"}` for follow-up. D-12 renames this to `"question"`.
   - What's unclear: The e2e test uses the old field name `"content"` (not `"comment"` which is what `MessageRequest` currently expects). This suggests the e2e tests may already be slightly out of sync or using a different field.
   - Recommendation: The current `MessageRequest` model has field `comment`, not `content`. The e2e test sending `"content"` would currently fail validation. This is likely an e2e test that passes because the real LLM endpoint behavior differs. Update to `"question"` per D-12.

2. **orjson in pyproject.toml**
   - What we know: orjson 3.11.7 is installed in the venv but not listed in `pyproject.toml`
   - What's unclear: Whether it was intentionally left out or is a transitive dependency
   - Recommendation: Add `"orjson>=3.11"` to the `[project] dependencies` list since it becomes a direct import

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all affected files in the repository
- `config/prompt.txt` -- LLM input/output JSON schema (canonical reference)
- Python REPL verification of Pydantic model_dump, model_validate, SQLModel dict+JSONB, orjson serialization

### Secondary (MEDIUM confidence)
- [orjson PyPI](https://pypi.org/project/orjson/) -- version 3.11.7 confirmed current as of 2026-03-25

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use or verified in project venv
- Architecture: HIGH -- all patterns verified with working Python code
- Pitfalls: HIGH -- derived from direct code inspection of all import sites and test files

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, no fast-moving dependencies)
