---
phase: 13-endpoint-unification
verified: 2026-03-02T00:00:00Z
status: gaps_found
score: 9/10 must-haves verified
re_verification: false
gaps:
  - truth: "REQUIREMENTS.md correctly reflects EP-02 as complete"
    status: failed
    reason: "EP-02 checkbox remains unchecked ([ ]) and traceability row shows 'Pending' despite the old routes being removed from the codebase and verified absent"
    artifacts:
      - path: ".planning/REQUIREMENTS.md"
        issue: "EP-02 marked '[ ]' and 'Pending' at lines 39 and 87; should be '[x]' and 'Complete'"
    missing:
      - "Change '- [ ] **EP-02**' to '- [x] **EP-02**' on line 39"
      - "Change '| EP-02 | Phase 13 | Pending |' to '| EP-02 | Phase 13 | Complete |' on line 87"
---

# Phase 13: Endpoint Unification Verification Report

**Phase Goal:** A single POST /chats endpoint handles both new analysis and chat continuation; old routes are removed; response schema uses suggestions
**Verified:** 2026-03-02T00:00:00Z
**Status:** gaps_found
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                              | Status      | Evidence                                                                                     |
|----|----------------------------------------------------------------------------------------------------|-------------|----------------------------------------------------------------------------------------------|
| 1  | POST /chats with text+lang creates a new chat and returns analysis with suggestions/response fields | VERIFIED  | `app/routers/chats.py` routes POST /chats to `create_or_continue_chat`; calls `service.chat(db, body.text, user_id, lang=body.lang, chat_id=body.chat_id)`; `ChatResponse` has `suggestions` and `response` fields |
| 2  | POST /chats with text+chat_id continues an existing conversation                                   | VERIFIED  | `ChatService.chat()` branches on `if chat_id:` -- continuation path calls `get_chat_owned` + `_ensure_history_capacity` then proceeds; unit test `test_continuation_success` confirms |
| 3  | POST /chats with text only (no lang, no chat_id) returns 400 invalid_request                       | VERIFIED  | `ChatRequest.require_lang_for_new_chat` model_validator raises `ValueError` when both `lang` and `chat_id` are None; integration test `test_missing_lang_returns_400` passes |
| 4  | POST /prompts/analyze returns 404 (route removed)                                                  | VERIFIED  | Route not present in `app.routes` (confirmed via runtime inspection); `TestRemovedRoutes.test_post_prompts_analyze_returns_404` passes |
| 5  | POST /chats/{id}/messages returns 400 (route removed, path exists for GET so 405->400)             | VERIFIED  | Only GET method is registered for `/chats/{chat_id}/messages`; `test_post_chat_messages_returns_400` verifies the 405->400 remap via Phase 11 error contract |
| 6  | GET /examples?lang=en returns examples (moved from /prompts/examples)                              | VERIFIED  | `app/routers/examples.py` registers `GET /examples`; wired in `app/main.py` via `examples_router`; `TestExamplesEndpoint` tests pass |
| 7  | GET /prompts/examples returns 404 (route removed)                                                  | VERIFIED  | `/prompts/examples` absent from registered routes; `test_get_prompts_examples_returns_404` passes |
| 8  | All tests pass with zero references to old model/field names                                       | VERIFIED  | `grep` for `AnalyzeRequest|AnalyzeResponse|AnalyzeResponseLLM|AnalysisService|ChatMessageRequest` returns zero hits; 98 tests pass |
| 9  | ChatRequest/ChatResponse/ChatResponseLLM schemas use renamed fields                                 | VERIFIED  | `ChatResponse` has `suggestions` + `response` fields (no `alternatives`, no `assessment`, no `lang`); `ChatResponseLLM` same; confirmed in `app/schema.py` |
| 10 | REQUIREMENTS.md correctly reflects EP-02 as complete                                               | FAILED    | EP-02 checkbox is `[ ]` (unchecked) at line 39; traceability table at line 87 shows "Pending"; the old routes are actually removed in code |

**Score:** 9/10 truths verified

---

### Required Artifacts

#### Plan 01 Artifacts

| Artifact                          | Expected                                                          | Status    | Details                                                                                                                  |
|-----------------------------------|-------------------------------------------------------------------|-----------|--------------------------------------------------------------------------------------------------------------------------|
| `app/schema.py`                   | ChatRequest with model_validator, ChatResponse, ChatResponseLLM  | VERIFIED  | `ChatRequest` with `require_lang_for_new_chat` validator; `ChatResponse` has text, chat_id, issues, suggestions, response; `ChatResponseLLM` matches |
| `app/services.py`                 | ChatService with merged chat() method                             | VERIFIED  | `class ChatService` exists; `chat()` handles both paths; no `analyze()`, no `_get_chat_lang()`, no `AnalysisService`    |
| `app/models.py`                   | Chat model without lang field                                     | VERIFIED  | `Chat` has `id`, `user_id`, `created_at` -- no `lang` field                                                             |
| `app/chats.py`                    | create_chat without lang param, get_chat_owned without lang in return | VERIFIED  | `create_chat(self, db, chat_id, user_id)` -- no lang; `get_chat_owned` returns `{"id": ..., "user_id": ...}` -- no lang |
| `app/dependencies.py`             | get_service returning ChatService type                            | VERIFIED  | `from app.services import ChatService`; `def get_service(request: Request) -> ChatService:`                              |
| `config/prompt.txt`               | Prompt with {lang_directive}, suggestions, response JSON keys    | VERIFIED  | First line is `{lang_directive}`; JSON schema uses `"response"` and `"suggestions"`; no `"assessment"` or `"alternatives"` |
| `migrations/001_create_tables.sql`| chats table without lang column                                   | VERIFIED  | chats table has `id`, `user_id`, `created_at` -- no `lang TEXT NOT NULL` column                                          |

#### Plan 02 Artifacts

| Artifact                  | Expected                                                          | Status    | Details                                                                                                            |
|---------------------------|-------------------------------------------------------------------|-----------|--------------------------------------------------------------------------------------------------------------------|
| `app/routers/chats.py`    | POST /chats, GET /chats/{id}/messages, DELETE /chats/{id}        | VERIFIED  | All three routes registered; `create_or_continue_chat` function exists; imports `ChatRequest`, `ChatResponse`      |
| `app/routers/examples.py` | GET /examples                                                     | VERIFIED  | `get_examples` function exists; imports `ExamplesResponse`, `ChatService`                                          |
| `app/routers/__init__.py` | Exports chats_router, examples_router, health_router, root_router | VERIFIED  | `__all__` lists all four; all imports resolve                                                                       |
| `app/main.py`             | Router includes for chats, examples, health, root; ChatService    | VERIFIED  | `app.include_router(chats_router)`, `app.include_router(examples_router)` wired; `ChatService` in lifespan         |
| `app/routers/prompts.py`  | DELETED                                                           | VERIFIED  | File does not exist; confirmed with `ls` returning "No such file or directory"                                      |

---

### Key Link Verification

#### Plan 01 Key Links

| From                  | To                | Via                                   | Pattern                                    | Status    | Details                                                   |
|-----------------------|-------------------|---------------------------------------|--------------------------------------------|-----------|------------------------------------------------------------|
| `app/services.py`     | `app/schema.py`   | ChatResponse, ChatResponseLLM imports | `from app\.schema import ChatResponse`    | VERIFIED  | `from app.schema import ChatResponse, ChatResponseLLM, ExamplesResponse` at line 10 |
| `app/services.py`     | `app/chats.py`    | create_chat() call without lang       | `create_chat\(db, chat_id, user_id=`      | VERIFIED  | `await self.chats.create_chat(db, chat_id, user_id=user_id)` at line 83 |
| `app/dependencies.py` | `app/services.py` | ChatService import and type annotation| `from app\.services import ChatService`   | VERIFIED  | `from app.services import ChatService` at line 10          |
| `app/services.py`     | `config/prompt.txt` | chain invocation with lang_directive| `lang_directive`                           | VERIFIED  | `{"lang_directive": lang_directive, "phrase": text, "history": history}` at line 96 |

#### Plan 02 Key Links

| From                   | To                    | Via                                   | Pattern                                              | Status    | Details                                                      |
|------------------------|-----------------------|---------------------------------------|------------------------------------------------------|-----------|--------------------------------------------------------------|
| `app/routers/chats.py` | `app/services.py`     | ChatService via Depends(get_service)  | `from app\.dependencies import.*get_service`        | VERIFIED  | `from app.dependencies import get_config, get_db, get_service, get_user_id` at line 9 |
| `app/routers/chats.py` | `app/schema.py`       | ChatRequest, ChatResponse imports     | `from app\.schema import ChatRequest, ChatResponse` | VERIFIED  | Imports both at lines 11-16                                  |
| `app/routers/examples.py` | `app/schema.py`   | ExamplesResponse import               | `from app\.schema import ExamplesResponse`          | VERIFIED  | `from app.schema import ExamplesResponse` at line 3          |
| `app/main.py`          | `app/routers/__init__.py` | chats_router, examples_router imports | `from app\.routers import chats_router, examples_router` | VERIFIED  | `from app.routers import chats_router, examples_router, health_router, root_router` at line 16 |
| `tests/conftest.py`    | `app/services.py`     | ChatService import for test fixture   | `from app\.services import ChatService`             | VERIFIED  | Integration conftest imports `ChatService` for test fixture  |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                             | Status       | Evidence                                                                                                   |
|-------------|------------|-----------------------------------------------------------------------------------------|--------------|------------------------------------------------------------------------------------------------------------|
| EP-01       | 13-01, 13-02 | Unified POST /chats endpoint handles both new analysis and chat continuation            | SATISFIED  | `POST /chats` registered in `app/routers/chats.py`; `ChatService.chat()` handles both paths              |
| EP-02       | 13-02      | Old routes (POST /prompts/analyze, POST /chats/{id}/messages) removed                   | SATISFIED (code) / DOCUMENTATION GAP | Routes absent from `app.routes` at runtime; `app/routers/prompts.py` deleted; but REQUIREMENTS.md still marks as `[ ]` Pending |
| EP-03       | 13-01      | `alternatives` field renamed to `suggestions` in response schema                        | SATISFIED  | `ChatResponse.suggestions` and `ChatResponseLLM.suggestions` exist; zero grep hits for old field name     |
| EP-04       | 13-01      | `lang` is required when `chat_id` is absent (no silent English default)                 | SATISFIED  | `ChatRequest.require_lang_for_new_chat` model_validator enforces this; test confirms 400 returned          |

**Note on EP-02:** The implementation satisfies EP-02 -- the routes are gone. The gap is that REQUIREMENTS.md has not been updated to reflect this: line 39 still shows `- [ ] **EP-02**` and the traceability table at line 87 still shows `| EP-02 | Phase 13 | Pending |`.

**Note on orphaned requirements:** No additional Phase 13 requirements exist in REQUIREMENTS.md beyond EP-01 through EP-04.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | -- | No TODO/FIXME/placeholder comments found in phase-modified files | -- | -- |
| None | -- | No empty implementations (return null/return {}) found | -- | -- |
| None | -- | No console.log-only handlers found | -- | -- |

**Anti-pattern scan result:** Clean. Zero blockers or warnings in any phase-modified file.

---

### Human Verification Required

None. All automated checks are sufficient for this phase's goal. The endpoint behavior (validation, routing, schema) is fully covered by the 98 passing tests.

---

### Gaps Summary

**One gap found: REQUIREMENTS.md documentation mismatch for EP-02.**

The implementation is complete and correct. All four routes are correctly registered or absent:
- `POST /chats` -- active (new unified endpoint)
- `POST /prompts/analyze` -- not registered (404 confirmed by test)
- `POST /chats/{chat_id}/messages` -- only GET is registered (POST returns 400 via 405->400 remap, confirmed by test)
- `GET /prompts/examples` -- not registered (404 confirmed by test)

The sole gap is that `.planning/REQUIREMENTS.md` was not updated to mark EP-02 as complete. Line 39 retains `[ ]` instead of `[x]`, and the traceability table at line 87 still shows "Pending" instead of "Complete". This is a documentation-only gap with no code consequence.

**Fix required:**
1. Line 39: `- [ ] **EP-02**` -> `- [x] **EP-02**`
2. Line 87: `| EP-02 | Phase 13 | Pending |` -> `| EP-02 | Phase 13 | Complete |`

---

_Verified: 2026-03-02T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
