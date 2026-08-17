---
phase: 15-refactor-chats
plan: 05
subsystem: structure
tags: [refactor, modules, pydantic, uuid7, imports]

requires:
  - phase: 15-refactor-chats-04
    provides: Working ChatService, ChatsDB, endpoints, and test suite
provides:
  - Flattened module structure (app/database.py, app/models.py, app/service.py)
  - API-layer files under app/api/ (dependencies, errors, main, schema)
  - Typed message content (HumanContent/AIContent with JSON storage)
  - UUID7 message IDs
  - Simplified API schemas (MessageRequest, MessageResponse, ChatResponse)
  - ResiliencePolicy.ainvoke rename
  - Python 3.14 requirement
affects: []

tech-stack:
  added: [uuid7]
  patterns: [typed-json-content, relationship-based-message-access, flattened-modules]

key-files:
  - path: app/api/schema.py
    role: API request/response schemas (simplified)
  - path: app/models.py
    role: Domain models with typed content and relationships
  - path: app/database.py
    role: Flattened database access layer
  - path: app/service.py
    role: Flattened business logic layer
---

## What Changed

### Module reorganization
- Moved API-layer files (dependencies, errors, main, schema) into `app/api/` package
- Flattened `app/database/chats.py` → `app/database.py`
- Flattened `app/database/models.py` → `app/models.py`
- Flattened `app/services/chats.py` → `app/service.py`
- Deleted old package directories (`app/database/`, `app/services/`)

### Model redesign
- Message content now uses typed Pydantic models: `HumanContent(phrase, comment)` and `AIContent(response, issues, suggestions)` stored as JSON column
- `Message.id` changed from auto-increment `int` to `UUID` via `uuid7`
- `Chat.phrase` renamed to `Chat.title`
- `Chat` has `Relationship()` to `messages`, with `ai_messages` and `human_messages` properties

### Schema simplification
- `FollowupRequest` → `MessageRequest`
- `ChatResponse` simplified to `(chat_id, title, created_at, lang)` — used for list/create responses
- `MessageResponse` changed to `(chat_id, role, content, created_at)` — used for message-level responses
- Removed `ChatMessagesResponse`, `ChatListItem` (no longer needed)
- `ChatResponseLLM` restored in schema (was incorrectly removed in earlier plan)

### Other changes
- `ResiliencePolicy.invoke` → `ResiliencePolicy.ainvoke`
- `config/prompt.txt` updated with new template format
- Python version bumped to `>=3.14` in pyproject.toml
- All import paths updated across routers, tests, and config files

## Deviations
None — user-authored changes committed as-is.