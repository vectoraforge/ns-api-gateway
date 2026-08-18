---
phase: 13-endpoint-unification
plan: 01
subsystem: api
tags: [pydantic, fastapi, langchain, schema-rename, model-validator]

# Dependency graph
requires:
  - phase: 12-llm-dependency-injection
    provides: DI-based service injection, Depends() patterns in routes
provides:
  - ChatRequest schema with model_validator for conditional lang requirement
  - ChatResponse and ChatResponseLLM with renamed fields (suggestions, response)
  - ChatService with merged chat() method handling new-chat and continuation
  - Chat model without lang field
  - Updated prompt template with {lang_directive} and renamed JSON keys
affects: [13-02 routers and tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "model_validator(mode='after') for conditional field requirements"
    - "Conditional prompt template variable (lang_directive) for per-request LLM context"

key-files:
  created: []
  modified:
    - app/schema.py
    - app/services.py
    - app/models.py
    - app/chats.py
    - app/dependencies.py
    - config/prompt.txt
    - migrations/001_create_tables.sql
    - app/routers/prompts.py
    - app/routers/root.py
    - app/main.py

key-decisions:
  - "model_validator enforces lang requirement at Pydantic level -- maps to 400 via existing validation_error_handler"
  - "lang_directive built as full sentence or empty string -- avoids 'None' rendering in prompt"
  - "Prompt template uses {lang_directive} placeholder resolved at ainvoke() time -- no chain rebuild needed"

patterns-established:
  - "model_validator(mode='after') for cross-field validation in request schemas"
  - "Conditional prompt template variables for per-request LLM configuration"

requirements-completed: [EP-01, EP-03, EP-04]

# Metrics
duration: 6min
completed: 2026-03-03
---

# Phase 13 Plan 01: Endpoint Unification - Schema/Service/Model Contracts Summary

**Renamed schemas (ChatRequest/ChatResponse/ChatResponseLLM), merged analyze()+chat() into unified ChatService.chat(), removed lang from Chat model, updated prompt template with conditional lang_directive and renamed JSON keys (suggestions/response)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-03T06:17:56Z
- **Completed:** 2026-03-03T06:23:56Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Renamed all schema classes: AnalyzeRequest -> ChatRequest, AnalyzeResponse -> ChatResponse, AnalyzeResponseLLM -> ChatResponseLLM
- Added model_validator on ChatRequest enforcing lang when no chat_id (EP-04)
- Renamed fields: alternatives -> suggestions, assessment -> response across schema and prompt
- Merged analyze() and chat() into single ChatService.chat() method
- Removed lang from Chat model, create_chat(), get_chat_owned(), and migration SQL
- Updated prompt template with {lang_directive} placeholder and renamed JSON keys

## Task Commits

Each task was committed atomically:

1. **Task 1: Rename schemas and add model_validator for conditional lang** - `4383b66` (feat)
2. **Task 2: Rename service, merge methods, update models/chats/deps/prompt/migration** - `92382f9` (feat)

**Plan metadata:** (pending) (docs: complete plan)

## Files Created/Modified
- `app/schema.py` - Renamed schema classes, added model_validator, renamed fields, deleted ChatMessageRequest
- `app/services.py` - Renamed AnalysisService -> ChatService, merged chat() method, deleted analyze() and _get_chat_lang()
- `app/models.py` - Removed lang field from Chat model
- `app/chats.py` - Removed lang from create_chat() and get_chat_owned()
- `app/dependencies.py` - Updated import and type annotation to ChatService
- `config/prompt.txt` - {lang_directive} placeholder, suggestions/response JSON keys
- `migrations/001_create_tables.sql` - Removed lang column from chats table
- `app/routers/prompts.py` - Updated imports and type annotations to use new names (Rule 3 fix)
- `app/routers/root.py` - Updated import and type annotation to ChatService (Rule 3 fix)
- `app/main.py` - Updated import and instantiation to ChatService (Rule 3 fix)

## Decisions Made
- model_validator enforces lang requirement at Pydantic level -- maps to 400 via existing validation_error_handler, no new exception handler needed
- lang_directive is built as a full sentence ("You are a linguistic assistant...") or empty string -- avoids "None" rendering in prompt for continuations
- Prompt template uses {lang_directive} placeholder resolved at ainvoke() time -- chain built once in __init__, no per-call rebuild
- ChatMessageRequest deleted entirely (only used by the removed continuation endpoint)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed broken imports in prompts.py, root.py, main.py**
- **Found during:** Task 2 (after renaming AnalysisService -> ChatService)
- **Issue:** app/routers/prompts.py, app/routers/root.py, and app/main.py imported AnalysisService, AnalyzeRequest, AnalyzeResponse, ChatMessageRequest which no longer exist after renaming
- **Fix:** Updated all imports and type annotations in these files to use new names (ChatService, ChatRequest, ChatResponse); updated service method calls from analyze() to chat() with new signature
- **Files modified:** app/routers/prompts.py, app/routers/root.py, app/main.py
- **Verification:** All imports verified with `python -c` checks; grep for old names returns zero hits
- **Committed in:** 92382f9 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Import fix required for codebase consistency after rename. No scope creep -- these files were direct dependents of the renamed modules.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All production code contracts established (schema, service, models, chats, deps, prompt, migration)
- Plan 02 can now create new routers (chats.py, examples.py) consuming the renamed contracts
- Plan 02 can update tests to match new class/field names and new endpoint paths
- Old router file (prompts.py) has been updated with new names but still uses old endpoint paths -- Plan 02 will restructure into new router files

## Self-Check: PASSED

All 10 files verified present. Both commits (4383b66, 92382f9) verified in git log.

---
*Phase: 13-endpoint-unification*
*Completed: 2026-03-03*
