# Phase 15: Refactor Chats - Research

**Researched:** 2026-03-10
**Domain:** FastAPI service restructuring -- data model, API surface, DI pattern, file organization
**Confidence:** HIGH

## Summary

This phase is a comprehensive refactoring of the chat system. The codebase is already mid-transition: files have been moved to `app/database/` and `app/services/` packages, models partially updated, and new skeletons created. However, the in-progress code has significant issues -- broken imports (`app.database.engine` doesn't exist), incomplete method implementations, role enum mismatch with DB schema (`ai` vs `assistant`), and stale references throughout.

The refactoring touches every layer: data model (Chat gains `phrase`, `comment`, `lang`), API surface (separate new-chat vs followup endpoints), service layer (per-request DI with pre-built chain), DB layer (session-in-init pattern replacing static methods), and schema (new request/response models). The scope is well-defined by CONTEXT.md decisions, leaving no ambiguity on architecture choices.

**Primary recommendation:** Execute as a layered rewrite -- models/schema first, then DB layer, then service layer, then router/DI, then cleanup/tests -- ensuring each layer compiles before moving to the next. The partially-written code in the working tree should be treated as scaffolding, not finished work.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Chat table gains `phrase` (required) and `comment` (optional, user context/note) columns
- `lang` stored on Chat only (not on Message). Nullable, defaults to None (autodetect)
- `Role` becomes a `StrEnum` (`human`, `ai`) on Message model
- Initial request: phrase+comment live on Chat row. No human Message for the first exchange
- First Message row for a new chat has role='ai' (the AI response)
- Followup messages: human Message (raw content) + AI Message (JSON string of response)
- AI responses stored as proper JSON string (`json.dumps(response.model_dump())`)
- When building LLM history, AI messages passed as-is (raw JSON string, not parsed)
- `POST /chats` -- new chat (phrase + optional comment + optional lang). Returns ChatResponse
- `POST /chats/{id}` -- followup (content). Returns ChatResponse
- `GET /chats/{id}` -- chat detail + paginated messages (flat response)
- `GET /chats` -- list user's chats. Returns last N chats (configurable, default 50)
- `DELETE /chats/{id}` -- delete chat. 204 on success
- `ChatRequest`: phrase (required, max_length=4096), comment (optional), lang (optional)
- `FollowupRequest`: content (required, max_length=4096)
- `ChatResponse`: chat_id, issues, suggestions, response. No text/phrase echo. Same shape for both
- `ChatMessagesResponse`: flat -- id, phrase, comment, lang, created_at, messages[], next_cursor
- ChatService created per-request via `get_chat_service()` dependency
- LLM chain built once in `lifespan()`, stored on `app.state.chain`
- ResiliencePolicy created once in `lifespan()`, stored on `app.state.policy`
- `get_chat_service()` receives: chain and policy from `app.state`, config from `get_config`, db session from `get_db`
- ChatService.__init__ creates ChatsDB(db) internally
- ChatService wraps all DB operations -- router never touches ChatsDB directly
- `app/database/models.py` -- Chat, Message, Role models
- `app/database/chats.py` -- ChatsDB class (session in __init__)
- `app/services/chats.py` -- ChatService class
- No `__init__.py` for database/ or services/ packages
- `create_chain()` function stays in services/chats.py, called in lifespan()
- ChatsDB takes AsyncSession in __init__
- Generic `save_message(chat_id, role, content)` -- called twice per followup
- `get_history` returns Chat data + Messages in single JOIN query (raw data, not LangChain types)
- Cursor pagination kept for GET /chats/{id} messages
- `delete()` returns rowcount; service raises InvalidChatError if 0
- Full test rewrite for new API surface, endpoints, schemas, and data model
- LLM first, create after: call LLM -> if success, insert Chat + AI response Message
- Transaction handled by get_db() dependency (existing pattern)

### Claude's Discretion
- get_history return shape (tuple, dataclass, or flat rows from JOIN)
- Exact tag format for LLM prompt (XML-style tags for phrase/comment)
- File cleanup -- identify all old files to remove vs keep
- Prompt template adjustments for new phrase+comment model
- Config key naming for chat list limit

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.129 | Web framework, DI, routing | Already in use |
| SQLModel | >=0.0.22 | ORM models (Chat, Message) | Already in use, combines SQLAlchemy + Pydantic |
| Pydantic | >=2.12 | Request/response schemas, validation | Already in use |
| LangChain | >=1.2 | LLM client, prompt templates | Already in use |
| asyncpg | >=0.30 | Async PostgreSQL driver | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | >=2.13 | Config loading | AppConfig for new chat_list_limit |
| sqlalchemy | (via sqlmodel) | JOIN queries, insert(), delete() | ChatsDB layer |
| langchain-core | >=1.2 | HumanMessage, AIMessage, ChatPromptTemplate | History construction |

No new libraries needed. This is purely a restructuring of existing code using the same stack.

## Architecture Patterns

### Recommended Project Structure
```
app/
├── database/
│   ├── models.py          # Chat, Message, Role (SQLModel)
│   └── chats.py           # ChatsDB (session-in-init, raw data out)
├── services/
│   └── chats.py           # ChatService + create_chain()
├── routers/
│   ├── __init__.py        # Router exports
│   ├── chats.py           # POST /chats, POST /chats/{id}, GET /chats, GET /chats/{id}, DELETE /chats/{id}
│   ├── examples.py        # GET /examples
│   ├── root.py            # GET /
│   └── health.py          # GET /health
├── schema.py              # Request/response Pydantic models
├── config.py              # AppConfig + new chat_list_limit
├── dependencies.py        # get_db, get_config, get_chat_service, get_user_id
├── exceptions.py          # Error classes (no changes)
├── errors.py              # Exception handlers (no changes)
├── auth.py                # JWT verification (no changes)
├── resilience.py          # ResiliencePolicy (no changes)
└── main.py                # lifespan(), app factory
```

### Pattern 1: Per-Request Service via DI
**What:** ChatService instantiated per-request via FastAPI dependency, receiving pre-built chain and policy from app.state.
**When to use:** Always -- this is the new DI pattern replacing the old singleton.
**Example:**
```python
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(chain=request.app.state.chain,
                       policy=request.app.state.policy,
                       config=config,
                       db=db)
```

### Pattern 2: Session-in-Init for DB Layer
**What:** ChatsDB receives AsyncSession in __init__, uses self.db for all queries.
**When to use:** All DB operations.
**Example:**
```python
class ChatsDB:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_message(self, chat_id: UUID, role: Role, content: str) -> None:
        self.db.add(Message(chat_id=chat_id, role=role, content=content))
```

### Pattern 3: Service Creates DB Internally
**What:** ChatService.__init__ creates ChatsDB(db), router never touches ChatsDB.
**When to use:** All service methods that need DB access.
**Example:**
```python
class ChatService:
    def __init__(self, chain, policy, config, db):
        self.chats_db = ChatsDB(db)
        # ... store other dependencies
```

### Pattern 4: LLM-First, Persist-After
**What:** Call LLM first, only create DB records on success.
**When to use:** Both new chat and followup flows.

### Anti-Patterns to Avoid
- **Router calling ChatsDB directly:** All DB access goes through ChatService
- **Passing db session through method params:** Session lives on ChatsDB instance (via self.db), not passed per-call
- **Building LangChain messages in DB layer:** DB returns raw data (role, content); service converts to LangChain types
- **Reusing old ChatService constructor signature:** Old took `(db, system_prompt, examples, llm, policy, max_chat_size)`; new takes `(chain, policy, config, db)` with chain pre-built

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cursor encoding/decoding | Custom base64 parsing | Keep existing `_encode_cursor`/`_decode_cursor` from old Chats class | Already tested, handles edge cases |
| Transaction management | Manual commit/rollback | `get_db()` context manager | Existing pattern, handles rollback on exception |
| Structured LLM output | Manual JSON parsing | `llm.with_structured_output(ChatResponseLLM)` | Already works, handles schema validation |
| JSON serialization for AI messages | `str(dict)` | `json.dumps(response.model_dump())` | CONTEXT.md decision -- proper JSON string, not Python repr |

**Key insight:** The old Chats class has well-tested cursor pagination logic. Transplant `_encode_cursor`/`_decode_cursor` static methods and the pagination query pattern directly into the new ChatsDB class.

## Common Pitfalls

### Pitfall 1: Role Enum Mismatch with Database
**What goes wrong:** The new `Role` StrEnum uses `ai` but the existing DB migration CHECK constraint expects `assistant`. The DB will reject inserts with role='ai'.
**Why it happens:** CONTEXT.md decided Role uses `human`/`ai`, but the SQL migration has `CHECK (role IN ('human', 'assistant'))`.
**How to avoid:** A new SQL migration must ALTER the CHECK constraint to allow `'human'` and `'ai'`, OR the Role enum must use `assistant` to match the existing DB. The CONTEXT.md explicitly says `Role` uses `human`/`ai`, so a migration is needed.
**Warning signs:** `asyncpg.exceptions.CheckViolationError` on message insert.

### Pitfall 2: Missing Database Migration for New Chat Columns
**What goes wrong:** The Chat model now has `phrase`, `comment`, and `lang` columns that don't exist in the DB.
**Why it happens:** Only the SQLModel was updated; no ALTER TABLE migration was written.
**How to avoid:** Write a migration adding `phrase TEXT NOT NULL`, `comment TEXT`, and `lang TEXT` columns to the chats table. The `phrase NOT NULL` requires either a default or handling existing rows.
**Warning signs:** `asyncpg.exceptions.UndefinedColumnError`.

### Pitfall 3: Broken Imports from app.database.engine
**What goes wrong:** `app/main.py` and `tests/integration/conftest.py` import `from app.database.engine import Chats` and `create_session_factory` -- these don't exist.
**Why it happens:** Partial migration left stale imports. `app/database.py` (the old engine module) was deleted but imports weren't fully updated.
**How to avoid:** Remove all `app.database.engine` imports. In main.py, the `Chats()` instantiation is no longer needed (ChatsDB is created inside ChatService). Session factory creation uses `async_sessionmaker` directly.
**Warning signs:** `ModuleNotFoundError` on startup.

### Pitfall 4: Missing setuptools Package Declarations
**What goes wrong:** `app.database` and `app.services` not listed in `pyproject.toml` `[tool.setuptools] packages`.
**Why it happens:** New package directories added without updating build config.
**How to avoid:** Update `packages = ["app", "app.routers", "app.database", "app.services"]` in pyproject.toml.
**Warning signs:** ImportError in production when installed as package.

### Pitfall 5: Old Code Has `policy.invoke()`, New Has `policy.ainvoke()`
**What goes wrong:** The old `app/services.py` calls `self.policy.invoke()` but `ResiliencePolicy` only has `ainvoke()`.
**Why it happens:** Stale reference from old code. The new `app/services/chats.py` already uses `ainvoke` correctly.
**How to avoid:** Ensure all LLM invocations use `policy.ainvoke()`.
**Warning signs:** `AttributeError: 'ResiliencePolicy' object has no attribute 'invoke'`.

### Pitfall 6: Prompt Template Variable Mismatch
**What goes wrong:** The current prompt.txt uses `{lang}` as a direct template variable in the system prompt text, but the new `create_chain()` needs to handle the phrase+comment model differently.
**Why it happens:** The prompt template and chain construction must be updated together.
**How to avoid:** The prompt template currently has `("human", "{text}")` in the old code. The new model needs `("human", "{input}")` with phrase+comment formatted using XML tags. The system prompt's `{lang}` placeholder needs to remain a LangChain template variable.
**Warning signs:** `KeyError` on chain invocation.

### Pitfall 7: Transaction Boundary with LLM-First Pattern
**What goes wrong:** If LLM succeeds but DB insert fails, `get_db()` rollbacks automatically. However, the LLM response is lost.
**Why it happens:** This is by design -- LLM-first means occasionally wasting an LLM call. But the service must NOT catch the DB exception and try to return the LLM response.
**How to avoid:** Let exceptions propagate naturally. The `get_db()` context manager handles rollback. Don't add try/except around DB operations within the service.
**Warning signs:** Returning partial responses to clients after DB failures.

### Pitfall 8: `db.exec()` vs `db.execute()` in SQLModel
**What goes wrong:** The current `app/database/chats.py` line 59 uses `await db.exec(statement)` but `db` is `self.db` and `db` is a local variable that doesn't exist.
**Why it happens:** Copy-paste error in the partially-written new code.
**How to avoid:** Use `self.db` consistently in ChatsDB methods. Also note SQLModel's `exec()` vs SQLAlchemy's `execute()` -- both work but `exec()` is the SQLModel wrapper.
**Warning signs:** `NameError: name 'db' is not defined`.

## Code Examples

### Chat Model with New Columns
```python
# app/database/models.py
from uuid import UUID
from enum import StrEnum
from datetime import datetime
from sqlmodel import Field, SQLModel


class Role(StrEnum):
    human = "human"
    ai = "ai"


class Chat(SQLModel, table=True):
    __tablename__ = "chats"

    id: UUID = Field(primary_key=True)
    phrase: str
    comment: str | None = None
    lang: str | None = None
    user_id: str | None = Field(default=None, index=True)
    created_at: datetime | None = Field(default=None,
                                        sa_column_kwargs={"server_default": "now()"})
```

### New Request/Response Schemas
```python
# app/schema.py
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class ChatRequest(BaseModel):
    phrase: str = Field(..., max_length=4096)
    comment: str | None = Field(default=None, max_length=4096)
    lang: str | None = Field(default=None)

class FollowupRequest(BaseModel):
    content: str = Field(..., max_length=4096)

class Issue(BaseModel):
    text_part: str = Field(...)
    explanation: str = Field(...)

class ChatResponseLLM(BaseModel):
    """Schema for LLM structured output."""
    issues: list[Issue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    response: str = Field(...)

class ChatResponse(BaseModel):
    chat_id: UUID
    issues: list[Issue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    response: str
```

### ChatsDB.create() with Phrase/Comment
```python
async def create(self,
                 chat_id: UUID,
                 phrase: str,
                 user_id: str,
                 comment: str | None = None,
                 lang: str | None = None) -> None:
    self.db.add(Chat(id=chat_id,
                     phrase=phrase,
                     comment=comment,
                     lang=lang,
                     user_id=user_id))
```

### Generic save_message
```python
async def save_message(self,
                       chat_id: UUID,
                       role: Role,
                       content: str) -> None:
    self.db.add(Message(chat_id=chat_id, role=role, content=content))
```

### get_history with JOIN (raw data out)
```python
async def get_history(self,
                      chat_id: UUID,
                      user_id: str) -> tuple[Chat | None, list[tuple[Role, str]]]:
    # Single JOIN returning Chat data + Messages
    chat_stmt = (
        select(Chat)
        .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
    )
    chat = (await self.db.exec(chat_stmt)).first()
    if chat is None:
        return None, []

    msg_stmt = (
        select(Message.role, Message.content)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at)
    )
    messages = (await self.db.exec(msg_stmt)).all()
    return chat, messages
```

### History Construction in Service (XML Tags)
```python
def _build_history(self,
                   chat: Chat,
                   db_messages: list[tuple[Role, str]]) -> list[HumanMessage | AIMessage]:
    """Convert Chat + DB messages to LangChain message list."""
    history = []

    # First human message from Chat row (phrase + comment)
    parts = [f"<phrase>{chat.phrase}</phrase>"]
    if chat.comment:
        parts.append(f"<comment>{chat.comment}</comment>")
    history.append(HumanMessage(content="".join(parts)))

    # DB messages (first is AI response, then alternating human/AI)
    for role, content in db_messages:
        if role == Role.ai:
            history.append(AIMessage(content=content))
        else:
            history.append(HumanMessage(content=f"<comment>{content}</comment>"))

    return history
```

### Lifespan with Pre-Built Chain
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    config = MainConfig().app
    setup_logging(log_level=config.log_level)

    llm = init_chat_model(model=config.model.name,
                          temperature=config.model.temperature,
                          max_tokens=config.model.max_tokens)

    app.state.config = config
    app.state.chain = create_chain(llm, config.prompt)
    app.state.policy = ResiliencePolicy(config.model.resilience)
    # ... db engine, session factory, verifier setup ...
```

### Updated get_chat_service
```python
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(chain=request.app.state.chain,
                       policy=request.app.state.policy,
                       config=config,
                       db=db)
```

### New Chat Endpoint
```python
@router.post("/chats", response_model=ChatResponse)
async def create_chat(body: ChatRequest,
                      user_id: str = Depends(get_user_id),
                      service: ChatService = Depends(get_chat_service)) -> ChatResponse:
    return await service.create_chat(phrase=body.phrase,
                                     comment=body.comment,
                                     user_id=user_id,
                                     lang=body.lang)
```

### Followup Endpoint
```python
@router.post("/chats/{chat_id}", response_model=ChatResponse)
async def followup_chat(chat_id: UUID,
                        body: FollowupRequest,
                        user_id: str = Depends(get_user_id),
                        service: ChatService = Depends(get_chat_service)) -> ChatResponse:
    return await service.followup(chat_id=chat_id,
                                  content=body.content,
                                  user_id=user_id)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Chats()` singleton with static-like methods taking `db` param | `ChatsDB(db)` per-request with session-in-init | This phase | Eliminates db param threading through every call |
| Single `POST /chats` with optional `chat_id` | Separate `POST /chats` + `POST /chats/{id}` | This phase | Separate request schemas, no conditional validation |
| `ChatService` receives `llm` and builds chain in __init__ | Chain pre-built in `lifespan()`, passed to service | This phase | Chain built once, not per-request |
| `str(response.model_dump())` for AI storage | `json.dumps(response.model_dump())` | This phase | Proper JSON string, parseable |
| `role: str` on Message model | `role: Role` (StrEnum) | This phase | Type safety |
| `ChatResponse` includes `text` field | No phrase echo in response | This phase | Breaking API change |

**Deprecated/outdated:**
- `app/chats.py`: Replaced by `app/database/chats.py`
- `app/database.py`: Replaced by session factory in `main.py` lifespan
- `app/models.py`: Moved to `app/database/models.py`
- `app/services.py`: Moved to `app/services/chats.py`
- `from app.database.engine import Chats`: Dead import, must be removed

## Files to Remove or Modify

### Files to Remove (already deleted in working tree)
- `app/chats.py` -- replaced by `app/database/chats.py`
- `app/database.py` -- old engine module, session factory now in lifespan
- `app/models.py` -- moved to `app/database/models.py`
- `app/services.py` -- moved to `app/services/chats.py`

### Files to Fully Rewrite
- `app/database/chats.py` -- new ChatsDB with session-in-init, new methods
- `app/services/chats.py` -- new ChatService with chain param, new flows
- `app/schema.py` -- new request/response models
- `app/routers/chats.py` -- new endpoints
- `app/dependencies.py` -- updated get_chat_service
- `app/main.py` -- updated lifespan (build chain, remove old imports)
- `tests/conftest.py` -- match new ChatService constructor
- `tests/unit/test_services.py` -- full rewrite for new API
- `tests/integration/conftest.py` -- remove old Chats() references

### Files to Modify
- `app/config.py` -- add `chat_list_limit` config key
- `app/routers/examples.py` -- minor: adjust to new DI (ChatService no longer has examples directly, or keep via config)
- `app/routers/root.py` -- minor: adjust to new DI
- `app/routers/__init__.py` -- unchanged
- `pyproject.toml` -- add `app.database`, `app.services` to packages
- `config/prompt.txt` -- adjust for phrase+comment model

### Database Migration Required
```sql
-- New migration: 002_add_chat_columns.sql
ALTER TABLE chats ADD COLUMN phrase TEXT;
ALTER TABLE chats ADD COLUMN comment TEXT;
ALTER TABLE chats ADD COLUMN lang TEXT;

-- Update existing rows (if any) with a default phrase
UPDATE chats SET phrase = '' WHERE phrase IS NULL;
ALTER TABLE chats ALTER COLUMN phrase SET NOT NULL;

-- Update role check constraint for ai instead of assistant
ALTER TABLE messages DROP CONSTRAINT messages_role_check;
ALTER TABLE messages ADD CONSTRAINT messages_role_check CHECK (role IN ('human', 'ai'));
```

## Open Questions

1. **Role Enum: `ai` vs `assistant`**
   - What we know: CONTEXT.md says `Role` uses `human`/`ai`. DB migration has CHECK for `human`/`assistant`.
   - What's unclear: Whether the user wants to update the DB constraint or adapt the code. Existing data uses `assistant`.
   - Recommendation: Write a DB migration to change the CHECK constraint. Update any existing `assistant` rows to `ai`. This aligns with the CONTEXT.md decision.

2. **Prompt Template for phrase+comment**
   - What we know: Current prompt has `{lang}` placeholder. New model sends phrase+comment as first human message with XML tags.
   - What's unclear: Whether the prompt template's `("human", "Analyze this phrase: {phrase}")` placeholder needs to change to `("human", "{input}")` with the actual phrase+comment content built in service code.
   - Recommendation: Use `MessagesPlaceholder("history")` to carry the full conversation (including the phrase+comment as first human message). The template's human message slot can be removed since the first human message is part of history. Alternatively, keep `("human", "{input}")` where `{input}` is the formatted phrase+comment for new chats or the followup content.

3. **GET /chats list -- what config key name?**
   - What we know: Default 50, configurable. AppConfig already has `history_max_messages` and `messages_max_page_size`.
   - What's unclear: Exact config field name.
   - Recommendation: `chat_list_limit: int = Field(default=50, ge=1)` on AppConfig. Simple and consistent.

4. **Examples endpoint and root endpoint dependency on ChatService**
   - What we know: Currently `examples.py` and `root.py` depend on `get_chat_service`, which now requires a DB session.
   - What's unclear: Whether examples/root should still depend on ChatService (which now creates a DB session per-request) for just reading examples/supported_languages.
   - Recommendation: Keep as-is for now since the DB session creation is lightweight. The examples and supported_languages come from config, which ChatService receives. Alternatively, these endpoints could depend on `get_config` directly, but that changes the current pattern.

## Sources

### Primary (HIGH confidence)
- Existing codebase analysis (all files read directly)
- CONTEXT.md decisions (user-locked)
- Git history and diff analysis

### Secondary (MEDIUM confidence)
- FastAPI dependency injection patterns (from existing codebase patterns, well-established)
- SQLModel/SQLAlchemy async session patterns (from existing codebase usage)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all existing
- Architecture: HIGH - all patterns decided in CONTEXT.md, existing codebase provides templates
- Pitfalls: HIGH - identified from direct code analysis of broken imports, enum mismatches, missing migrations
- File organization: HIGH - CONTEXT.md specifies exact file layout

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable -- internal refactoring, no external dependencies changing)
