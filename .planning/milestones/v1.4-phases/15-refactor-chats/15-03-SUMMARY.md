---
phase: 15-refactor-chats
plan: 03
subsystem: api
tags: [fastapi, dependency-injection, langchain, async, pydantic]

requires:
  - phase: 15-refactor-chats-02
    provides: ChatsDB with session-in-init pattern, ChatService with chain-based DI, create_chain() function
provides:
  - Updated DI layer wiring chain/policy from app.state
  - 5 chat endpoints matching CONTEXT.md spec (create, followup, list, detail, delete)
  - Lifespan building chain once via create_chain()
  - ChatService get_messages, get_chat_list, delete_chat methods
affects: [15-04]

tech-stack:
  added: []
  patterns: [chain-on-app-state DI, service-only router pattern, cursor validation in router]

key-files:
  created: []
  modified:
    - app/dependencies.py
    - app/routers/chats.py
    - app/services/chats.py
    - app/main.py

key-decisions:
  - "ChatService.get_messages returns ChatMessagesResponse directly (service builds response from Chat + messages)"
  - "ChatService.get_chat_list uses config.chat_list_limit internally -- router does not pass limit"
  - "ChatService.delete_chat raises InvalidChatError when rowcount is 0"
  - "examples.py and root.py unchanged -- imports already compatible with new service DI"

patterns-established:
  - "Router never touches ChatsDB: all operations through ChatService"
  - "Cursor validation in router layer before calling service"
  - "Service methods return Pydantic response models directly"

requirements-completed: [REFACT-05, REFACT-06]

duration: 3min
completed: 2026-03-11
---

# Phase 15 Plan 03: Router Wiring and DI Layer Summary

**Full API surface wired with 5 chat endpoints, DI injecting chain/policy from app.state, and lifespan building chain once via create_chain()**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-11T05:05:14Z
- **Completed:** 2026-03-11T05:08:38Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Rewrote get_chat_service to inject chain and policy from app.state instead of old constructor args
- Rewrote chats router with 5 endpoints: POST /chats, POST /chats/{id}, GET /chats, GET /chats/{id}, DELETE /chats/{id}
- Updated main.py lifespan to build chain once via create_chain(), removed broken database.engine imports and old Chats() usage
- Added get_messages, get_chat_list, and delete_chat methods to ChatService (missing from Plan 02)

## Task Commits

Each task was committed atomically:

1. **Task 1: Update DI and rewrite chats router** - `b88f954` (feat)
2. **Task 2: Update main.py lifespan, examples router, and root router** - `ff415ac` (feat)

## Files Created/Modified
- `app/dependencies.py` - Rewrote get_chat_service with chain/policy from app.state, removed unused imports
- `app/routers/chats.py` - Full rewrite with 5 endpoints, service-only pattern
- `app/services/chats.py` - Added get_messages, get_chat_list, delete_chat methods
- `app/main.py` - Lifespan uses create_chain(), removed broken imports and old Chats()

## Decisions Made
- ChatService.get_messages returns ChatMessagesResponse directly -- the service builds the full response object from Chat metadata + paginated messages, keeping the router thin
- ChatService.get_chat_list uses self.config.chat_list_limit internally rather than receiving limit from router -- single source of truth for the limit
- ChatService.delete_chat raises InvalidChatError when ChatsDB.delete returns rowcount 0 -- consistent 404 behavior
- examples.py and root.py required no changes -- their imports from app.dependencies and app.services.chats were already compatible

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added get_messages, get_chat_list, delete_chat to ChatService**
- **Found during:** Task 1 (router rewrite)
- **Issue:** Plan 02 did not implement these three service methods that the router endpoints depend on
- **Fix:** Added get_messages (builds ChatMessagesResponse from DB tuple), get_chat_list (delegates to ChatsDB.list_chats with config limit), delete_chat (delegates to ChatsDB.delete with rowcount check)
- **Files modified:** app/services/chats.py
- **Verification:** Import check passes, all endpoints reachable
- **Committed in:** b88f954 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Auto-fix was anticipated by the plan ("If these were not implemented in Plan 02, add them now"). No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full API surface wired and importable without errors
- All 5 chat endpoints matching CONTEXT.md specification
- Plan 04 (test rewrite) can test against the complete endpoint/service/DB stack
- No blockers

## Self-Check: PASSED

All files verified present, all commit hashes found in git log.

---
*Phase: 15-refactor-chats*
*Completed: 2026-03-11*
