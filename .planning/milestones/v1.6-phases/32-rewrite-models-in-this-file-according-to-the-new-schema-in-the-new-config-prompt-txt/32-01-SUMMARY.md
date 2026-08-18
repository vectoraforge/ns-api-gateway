---
phase: 32-rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt
plan: 01
subsystem: api
tags: [pydantic, sqlalchemy, jsonb, models, exceptions]

requires:
  - phase: 31-move-quota-check-to-a-dependency
    provides: stable exception hierarchy and model structure to extend

provides:
  - OutOfScopeError exception with HTTP 400 and out_of_scope error code
  - LLM validation models in models/llm.py (Issue, AnalyzeInput, FollowUpInput, AnalyzeResponse, FollowUpResponse, RejectResponse)
  - API schemas in models/api.py with renamed fields (ChatRequest.context, MessageRequest.question, MessageResponse.content as dict)
  - Message.content as plain dict with JSONB column type
  - Clean models/__init__.py re-exports from llm.py and api.py

affects: [32-02 service/router rewiring, 32-03 test updates]

tech-stack:
  added: [orjson]
  patterns: [LLM validation models separate from API schemas, plain dict for internal content representation]

key-files:
  created:
    - src/nativespeaker/api/models/llm.py
    - src/nativespeaker/api/models/api.py
  modified:
    - src/nativespeaker/api/exceptions.py
    - src/nativespeaker/api/models/chats.py
    - src/nativespeaker/api/models/__init__.py
    - pyproject.toml

key-decisions:
  - "MessageRequest field renamed from content to question (actual field was content, not comment as described in plan interface)"
  - "Plain dict for Message.content with JSONB -- no Pydantic model wrapping at persistence layer"

patterns-established:
  - "LLM validation models in models/llm.py, API schemas in models/api.py -- separate concerns"
  - "Non-optional list types for AnalyzeResponse.issues and suggestions -- always present, possibly empty"

requirements-completed: []

duration: 2min
completed: 2026-03-26
---

# Phase 32 Plan 01: Model Foundation Summary

**OutOfScopeError exception, 6 LLM validation models in models/llm.py, API schemas moved to models/api.py with field renames, Message.content as plain dict with JSONB**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-26T06:34:02Z
- **Completed:** 2026-03-26T06:36:52Z
- **Tasks:** 2
- **Files modified:** 7 (3 modified, 2 created, 2 deleted)

## Accomplishments
- Added OutOfScopeError exception (HTTP 400, out_of_scope code) and extended ErrorCode Literal
- Created models/llm.py with all 6 LLM validation models matching config/prompt.txt contract exactly
- Moved schema.py to models/api.py with field renames: ChatRequest.comment->context, MessageRequest.content->question, MessageResponse.content as dict
- Converted Message.content from PydanticJSONB(ContentUnion) to plain dict with sa_type=JSONB
- Deleted content.py and schema.py, updated __init__.py re-exports
- Added orjson>=3.11 to pyproject.toml dependencies

## Task Commits

Each task was committed atomically:

1. **Task 1: Create OutOfScopeError, models/llm.py, and add orjson dependency** - `9f1f99b` (feat)
2. **Task 2: Move schema.py to models/api.py, update Message model, update __init__.py, delete content.py** - `c49febb` (feat)

## Files Created/Modified
- `src/nativespeaker/api/exceptions.py` - Added out_of_scope to ErrorCode, OutOfScopeError class
- `src/nativespeaker/api/models/llm.py` - New file: Issue, AnalyzeInput, FollowUpInput, AnalyzeResponse, FollowUpResponse, RejectResponse
- `src/nativespeaker/api/models/api.py` - New file (moved from schema.py): ErrorResponse, ChatRequest, ChatResponse, MessageRequest, MessageResponse, ExamplesResponse, UserProfileResponse
- `src/nativespeaker/api/models/chats.py` - Message.content changed to dict with JSONB, removed PydanticJSONB/ContentUnion imports
- `src/nativespeaker/api/models/__init__.py` - Re-exports from llm.py and api.py instead of content.py
- `src/nativespeaker/api/models/content.py` - Deleted
- `src/nativespeaker/api/schema.py` - Deleted (moved to models/api.py)
- `pyproject.toml` - Added orjson>=3.11 dependency

## Decisions Made
- MessageRequest field was actually named `content` (not `comment` as plan interface stated) -- renamed to `question` per plan intent (D-12)
- Followed plan exactly for all other field renames and type changes

## Deviations from Plan

None - plan executed exactly as written. The only discrepancy was the plan's interface section showing `MessageRequest.comment` when the actual field was `MessageRequest.content`, but the rename target (`question`) was correct per the decision (D-12).

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All new type contracts are in place for Plan 02 (service/router wiring)
- Services and routers still import from old locations (schema.py, content.py) -- Plan 02 updates those
- Tests reference old models and fields -- Plan 03 updates those

## Self-Check: PASSED

All files verified present (or confirmed deleted). All commits found in git log.

---
*Phase: 32-rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt*
*Completed: 2026-03-26*
