---
phase: 13-endpoint-unification
plan: 02
subsystem: api
tags: [fastapi, routers, endpoint-migration, test-migration, error-contract]

# Dependency graph
requires:
  - phase: 13-endpoint-unification
    plan: 01
    provides: ChatRequest/ChatResponse/ChatResponseLLM schemas, ChatService with merged chat(), Chat model without lang
provides:
  - POST /chats unified endpoint (new chat + continuation)
  - GET /examples endpoint (moved from /prompts/examples)
  - GET /chats/{id}/messages cursor-paginated listing (unchanged)
  - DELETE /chats/{id} (unchanged)
  - Old routes removed (/prompts/analyze, POST /chats/{id}/messages, /prompts/examples)
  - All tests migrated to new schema/service/endpoint names
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Unified POST /chats with optional chat_id for continuation vs lang for new chat"
    - "Separate examples router (app/routers/examples.py) for GET /examples"

key-files:
  created:
    - app/routers/chats.py
    - app/routers/examples.py
  modified:
    - app/routers/__init__.py
    - app/main.py
    - tests/conftest.py
    - tests/unit/test_services.py
    - tests/unit/test_models.py
    - tests/integration/conftest.py
    - tests/integration/test_prompts_endpoints.py
    - tests/integration/test_cross_user_isolation.py
    - tests/llm/test_real_llm.py

key-decisions:
  - "POST /chats/{id}/messages 404 test adjusted to 400 -- path exists for GET so Starlette returns 405 which remaps to 400 via Phase 11 error contract"
  - "Cross-user isolation POST test uses POST /chats with chat_id in body instead of POST /chats/{id}/messages"
  - "Error contract assertions updated from body['status']/body['error'] to body['code'] per Phase 11 contract"

patterns-established:
  - "Router-per-resource pattern: chats.py, examples.py, health.py, root.py"
  - "TestRemovedRoutes class pattern for verifying old routes return 404/400"

requirements-completed: [EP-01, EP-02, EP-03, EP-04]

# Metrics
duration: 6min
completed: 2026-03-03
---

# Phase 13 Plan 02: Endpoint Unification - Router Migration and Test Update Summary

**New chats/examples routers replacing prompts.py, all tests migrated to POST /chats with ChatRequest/ChatResponse, old routes verified removed with 404/400 tests, cross-user isolation updated to Phase 11 error contract**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-03T06:27:30Z
- **Completed:** 2026-03-03T06:34:10Z
- **Tasks:** 2
- **Files modified:** 11 (4 app + 7 test)

## Accomplishments
- Created app/routers/chats.py with POST /chats (unified new+continuation), GET messages, DELETE chat
- Created app/routers/examples.py with GET /examples (moved from /prompts/examples)
- Deleted app/routers/prompts.py and all references to prompts_router
- Migrated all 7 test files: renamed schemas, services, endpoints, and field names
- Added TestRemovedRoutes verifying POST /prompts/analyze (404), POST /chats/{id}/messages (400), GET /prompts/examples (404)
- Updated cross-user isolation tests to use POST /chats with chat_id in body and Phase 11 error contract
- Zero grep hits for old names (AnalyzeRequest, AnalyzeResponse, AnalysisService, ChatMessageRequest, prompts_router)
- All 98 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Create new router files, delete prompts.py, update __init__.py and main.py** - `802dc8b` (feat)
2. **Task 2: Migrate all test files to new schema/service/endpoint names** - `10a7006` (feat)

**Plan metadata:** (pending) (docs: complete plan)

## Files Created/Modified
- `app/routers/chats.py` - New router with POST /chats, GET /chats/{id}/messages, DELETE /chats/{id}
- `app/routers/examples.py` - New router with GET /examples
- `app/routers/prompts.py` - DELETED (all endpoints moved or removed)
- `app/routers/__init__.py` - Updated exports: chats_router, examples_router, health_router, root_router
- `app/main.py` - Updated router includes (removed prompts_router, added examples_router)
- `tests/conftest.py` - AnalysisService -> ChatService, prompts_router -> examples_router, prompt template updated
- `tests/unit/test_services.py` - TestAnalyze/TestChat merged, chat() signature, ChatResponseLLM fields renamed
- `tests/unit/test_models.py` - ChatRequest/ChatResponse tests, model_validator test, TestChatModels deleted
- `tests/integration/conftest.py` - ChatService, create_chat() without lang param
- `tests/integration/test_prompts_endpoints.py` - POST /chats endpoint tests, TestRemovedRoutes, examples at /examples
- `tests/integration/test_cross_user_isolation.py` - POST /chats with chat_id, Phase 11 error contract assertions
- `tests/llm/test_real_llm.py` - /chats endpoint, suggestions/response field names

## Decisions Made
- POST /chats/{id}/messages returns 400 (not 404) because the path exists for GET and Starlette returns 405 which maps to 400 via the Phase 11 _STATUS_REMAP
- Cross-user isolation POST test changed from POST /chats/{id}/messages to POST /chats with chat_id in body (matching new unified endpoint)
- Error contract assertions in cross-user isolation updated from body["status"]/body["error"] to body["code"] per Phase 11 contract

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Adjusted POST /chats/{id}/messages 404 test to expect 400**
- **Found during:** Task 2 (TestRemovedRoutes verification)
- **Issue:** Plan specified 404 for POST /chats/{id}/messages, but the path exists for GET so Starlette returns 405 Method Not Allowed, which _STATUS_REMAP converts to 400 invalid_request
- **Fix:** Changed test assertion from 404 to 400 with code="invalid_request", added docstring explaining the 405->400 mapping
- **Files modified:** tests/integration/test_prompts_endpoints.py
- **Verification:** Test passes, behavior is correct per Phase 11 error contract
- **Committed in:** 10a7006 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Corrected test expectation to match actual error contract behavior. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Endpoint unification complete -- all routes use new unified API shape
- Phase 13 fully complete (both plans done)
- All production code and tests aligned on new schema/service/endpoint names

## Self-Check: PASSED

All files verified present (chats.py, examples.py created; prompts.py deleted). Both commits (802dc8b, 10a7006) verified in git log.
