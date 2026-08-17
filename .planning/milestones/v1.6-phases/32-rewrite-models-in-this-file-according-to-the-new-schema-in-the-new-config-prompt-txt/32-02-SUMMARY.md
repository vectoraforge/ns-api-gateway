---
phase: 32-rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt
plan: 02
subsystem: api
tags: [orjson, pydantic, fastapi, services, routers, llm-dispatch]

requires:
  - phase: 32-01
    provides: LLM validation models (llm.py), API schemas (api.py), OutOfScopeError, Message.content as dict

provides:
  - ChatService rewritten with orjson serialization, resolved_mode dispatch, and OutOfScopeError reject handling
  - All service and router imports rewired from schema to models.api
  - Field renames applied in routers (body.context, body.question)
  - AnalyzeInput/FollowUpInput used to build human message content with model_dump(exclude_none=True)

affects: [32-03 test updates]

tech-stack:
  added: []
  patterns: [orjson for dict-to-JSON serialization in LLM history, manual resolved_mode dispatch with model_validate]

key-files:
  created: []
  modified:
    - src/nativespeaker/api/services/chats.py
    - src/nativespeaker/api/routers/chats.py
    - src/nativespeaker/api/routers/examples.py
    - src/nativespeaker/api/routers/users.py
    - src/nativespeaker/api/app/errors.py
    - src/nativespeaker/api/app/main.py

key-decisions:
  - "orjson.dumps().decode() for all dict-to-string serialization in LLM history and content"
  - "Reject check before validation -- OutOfScopeError raised before any messages persisted"

patterns-established:
  - "Manual resolved_mode dispatch: reject -> raise, analyze/follow_up -> model_validate, else -> AnalysisError"
  - "Input models (AnalyzeInput/FollowUpInput) with model_dump(exclude_none=True) for content construction"

requirements-completed: []

duration: 3min
completed: 2026-03-26
---

# Phase 32 Plan 02: Service/Router Rewiring Summary

**ChatService rewritten with orjson serialization, LLM resolved_mode dispatch, OutOfScopeError reject handling; all 5 consumer files rewired from schema to models.api with field renames**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-26T06:40:43Z
- **Completed:** 2026-03-26T06:44:27Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Rewrote ChatService.ask_llm with orjson serialization for history/content, manual resolved_mode dispatch, and OutOfScopeError for reject responses
- Replaced AIContent/HumanContent model wrapping with AnalyzeInput/FollowUpInput.model_dump(exclude_none=True)
- Renamed create_chat parameter comment->context, send_message parameter content->question
- Updated all 5 consumer files (3 routers, 2 app modules) from schema to models.api imports
- Applied field renames in chats router: body.comment->body.context, body.content->body.question

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite ChatService with orjson, LLM dispatch, reject handling, and field renames** - `0228363` (feat)
2. **Task 2: Update all router and app imports from schema to models.api** - `a6ab6b3` (feat)

## Files Created/Modified
- `src/nativespeaker/api/services/chats.py` - Rewritten ask_llm with orjson + dispatch, create_chat/send_message with input models
- `src/nativespeaker/api/routers/chats.py` - Import from models.api, field renames body.context/body.question
- `src/nativespeaker/api/routers/examples.py` - Import ExamplesResponse from models.api
- `src/nativespeaker/api/routers/users.py` - Import UserProfileResponse from models.api
- `src/nativespeaker/api/app/errors.py` - Import ErrorResponse from models.api
- `src/nativespeaker/api/app/main.py` - Import ErrorResponse from models.api

## Decisions Made
- Used orjson.dumps().decode() consistently for all dict-to-string serialization (history messages and current content)
- Reject check happens first in ask_llm, before any validation or message persistence

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- App import verification (`from nativespeaker.api.app.main import app`) cannot run in worktree since installed package resolves to main repo. Verified via AST parsing and file content checks instead.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All src/ code is rewired to new model contracts
- No references to old schema.py, AIContent, HumanContent, ContentUnion, or PydanticJSONB remain in src/
- Test files still reference old models and fields -- Plan 03 will update those

## Self-Check: PASSED

All files verified present. All commits found in git log.
