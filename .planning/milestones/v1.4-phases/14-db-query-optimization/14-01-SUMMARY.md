---
phase: 14-db-query-optimization
plan: 01
subsystem: database
tags: [sqlalchemy, async, query-optimization, dead-code-removal]

# Dependency graph
requires:
  - phase: 13-endpoint-unification
    provides: Unified POST /chats endpoint, chats router, Chats data-access class
provides:
  - Single-query Chats methods with user_id JOIN filtering
  - Atomic create_chat_with_messages for deferred chat creation
  - Inline capacity check via len(history) in ChatService
  - Simplified history_max_messages config
affects: [14-02-PLAN (test rewrite)]

# Tech tracking
tech-stack:
  added: []
  patterns: [single-query-with-join, inline-capacity-check, deferred-creation]

key-files:
  created: []
  modified:
    - app/chats.py
    - app/services.py
    - app/config.py
    - app/main.py
    - app/routers/chats.py
    - app/exceptions.py
    - app/errors.py
    - config/config.yaml

key-decisions:
  - "Defer chat creation to after LLM success via create_chat_with_messages"
  - "Derive capacity from len(loaded_history) instead of separate get_message_counts query"
  - "Unified history_max_messages replaces separate human/assistant limits"

patterns-established:
  - "Single-query pattern: all DB reads use JOIN with user_id filter, returning 404 for non-existent or wrong-user resources"
  - "Deferred creation: create_chat_with_messages called only after LLM success, preventing orphan chat rows"
  - "Inline capacity check: len(history) >= max*2 derived from already-loaded data, no extra DB call"

requirements-completed: [QOPT-01, QOPT-02, QOPT-03, QOPT-04, QOPT-05, DEAD-01, DEAD-02, DEAD-03, DEAD-04]

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 14 Plan 01: DB Query Optimization Summary

**Single-query Chats methods with user_id JOIN filters, deferred chat creation, inline capacity check, and full dead code removal of ownership/count helpers**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-04T08:43:56Z
- **Completed:** 2026-03-04T08:48:13Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Refactored all Chats data access methods to use single JOIN queries with user_id filtering, eliminating N+1 query patterns
- Replaced separate create_chat + save_messages with atomic create_chat_with_messages, deferred to after LLM success
- Removed all dead production code: get_chat_owned, get_message_counts, _ensure_history_capacity, ChatOwnershipError class/handler/registration
- Simplified config from two history limit fields to one history_max_messages

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor Chats data access methods and config** - `ab84858` (feat)
2. **Task 2: Update ChatService and router to use new Chats API** - `6d93cf4` (feat)

## Files Created/Modified
- `app/chats.py` - Rewritten Chats class: create_chat_with_messages, delete_chat (single DELETE), load_history (JOIN+user_id), list_messages (JOIN+user_id); removed create_chat, get_chat_owned, get_message_counts
- `app/services.py` - ChatService: single history_max_messages param, inline capacity check, deferred creation, removed _ensure_history_capacity
- `app/config.py` - AppConfig: replaced history_max_human_messages + history_max_assistant_messages with history_max_messages
- `app/main.py` - Updated ChatService construction to pass history_max_messages
- `app/routers/chats.py` - list_chat_messages passes user_id to list_messages directly; delete_chat calls delete_chat instead of delete_chat_owned
- `app/exceptions.py` - Removed ChatOwnershipError class; simplified ChatHistoryLimitError(max_messages)
- `app/errors.py` - Removed ChatOwnershipError import, handler function, and registration
- `config/config.yaml` - Replaced history_max_human_messages + history_max_assistant_messages with history_max_messages: 50

## Decisions Made
- Defer chat creation to after LLM success via create_chat_with_messages (per user decision from CONTEXT.md)
- Derive capacity from len(loaded_history) instead of separate get_message_counts query
- Unified history_max_messages replaces separate human/assistant limits (both were 50, single field simplifies)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused `func` import from app/chats.py**
- **Found during:** Task 1 (Ruff verification)
- **Issue:** `func` was imported from sqlalchemy but no longer used after removing get_message_counts
- **Fix:** Removed `func` from the import line
- **Files modified:** app/chats.py
- **Verification:** ruff check passes clean
- **Committed in:** ab84858 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed line-length violation in app/services.py**
- **Found during:** Task 2 (Ruff verification)
- **Issue:** create_chat_with_messages call exceeded 120 char line limit
- **Fix:** Extracted `human_content` variable to shorten the line
- **Files modified:** app/services.py
- **Verification:** ruff check passes clean
- **Committed in:** 6d93cf4 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both auto-fixes were lint corrections required for clean ruff check. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All production code refactored and dead code removed
- Plan 14-02 (test rewrite) can proceed immediately to update unit and integration tests for the new API surface
- Phantom mock setups for removed methods (get_chat_owned, get_message_counts, _ensure_history_capacity) must be cleaned in tests

## Self-Check: PASSED

- All 9 files verified present
- Commit ab84858 (Task 1) verified in git log
- Commit 6d93cf4 (Task 2) verified in git log

---
*Phase: 14-db-query-optimization*
*Completed: 2026-03-04*
