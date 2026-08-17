---
phase: 15-refactor-chats
plan: 01
subsystem: api
tags: [pydantic, sqlmodel, schema, migration, fastapi]

requires:
  - phase: 14-db-query-optimization
    provides: Chat/Message models, JOIN query pattern
provides:
  - Chat model with phrase/comment/lang columns
  - Role StrEnum (human/ai)
  - New request/response schemas (ChatRequest, FollowupRequest, ChatResponse, ChatMessagesResponse, ChatResponseLLM)
  - AppConfig with chat_list_limit
  - DB migration for new columns and role constraint
  - Package declarations for app.database and app.services
affects: [15-02, 15-03, 15-04]

tech-stack:
  added: []
  patterns: [separated request schemas per endpoint, flat chat detail response, LLM output schema]

key-files:
  created:
    - migrations/002_add_chat_columns.sql
  modified:
    - app/database/models.py
    - app/schema.py
    - app/config.py
    - pyproject.toml

key-decisions:
  - "Separate ChatRequest (new chat) and FollowupRequest (followup) schemas instead of conditional validation"
  - "ChatMessagesResponse is flat: id, phrase, comment, lang, created_at, messages[], next_cursor"
  - "ChatResponseLLM as dedicated LLM output schema separate from API ChatResponse"

patterns-established:
  - "Per-endpoint request models: one Pydantic model per API endpoint"
  - "No langchain types in schema.py: schema is pure Pydantic, service layer handles conversion"

requirements-completed: [REFACT-01, REFACT-02, REFACT-07, REFACT-08]

duration: 2min
completed: 2026-03-11
---

# Phase 15 Plan 01: Foundation Layer Summary

**Chat model with phrase/comment/lang, rewritten request/response schemas, DB migration for column additions and role constraint update**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-11T04:53:04Z
- **Completed:** 2026-03-11T04:55:43Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Chat model extended with `lang` column for language storage at chat level
- Complete schema.py rewrite: 10 Pydantic models replacing old ChatMessage hierarchy, no langchain imports
- AppConfig gains `chat_list_limit` (default 50) for GET /chats endpoint
- DB migration covers column additions, NOT NULL backfill, and role constraint update from 'assistant' to 'ai'
- Package declarations updated for app.database and app.services sub-packages

## Task Commits

Each task was committed atomically:

1. **Task 1: Update models, schema, and config** - `f9b8a81` (feat)
2. **Task 2: Create DB migration and update pyproject.toml** - `7f5b4bf` (chore)

## Files Created/Modified
- `app/database/models.py` - Added lang column to Chat model
- `app/schema.py` - Full rewrite with ChatRequest, FollowupRequest, ChatResponse, ChatMessagesResponse, ChatResponseLLM, ChatListItem, MessageResponse, Issue, ExamplesResponse, ErrorResponse
- `app/config.py` - Added chat_list_limit field to AppConfig
- `migrations/002_add_chat_columns.sql` - DDL for phrase/comment/lang columns and role constraint migration
- `pyproject.toml` - Added app.database and app.services to packages list

## Decisions Made
- Separate ChatRequest and FollowupRequest schemas instead of conditional validation on a single model
- ChatMessagesResponse is flat (id, phrase, comment, lang, created_at, messages[], next_cursor) rather than nested
- ChatResponseLLM is a dedicated LLM output schema, separate from the API-facing ChatResponse

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed import order in models.py**
- **Found during:** Task 1
- **Issue:** Imports were not sorted alphabetically, causing ruff I001 lint failure
- **Fix:** Reordered stdlib imports to alphabetical (datetime, enum, uuid)
- **Files modified:** app/database/models.py
- **Verification:** ruff check passes
- **Committed in:** f9b8a81 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial import ordering fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All foundation types established and importable
- Downstream plans (15-02 DB layer, 15-03 service, 15-04 router/tests) can import from these modules
- No blockers

## Self-Check: PASSED

All files verified present, all commit hashes found in git log.

---
*Phase: 15-refactor-chats*
*Completed: 2026-03-11*
