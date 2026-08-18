---
phase: 15-refactor-chats
plan: 02
subsystem: api
tags: [sqlmodel, langchain, fastapi, async, pydantic]

requires:
  - phase: 15-refactor-chats-01
    provides: Chat model with phrase/comment/lang, Role StrEnum, request/response schemas, AppConfig with chat_list_limit
provides:
  - ChatsDB with session-in-init pattern and all CRUD methods
  - ChatService with chain-based DI, create_chat and followup flows
  - create_chain() module-level function for lifespan setup
  - XML-tagged history construction for LLM context
affects: [15-03, 15-04]

tech-stack:
  added: []
  patterns: [session-in-init DB layer, chain-based DI for service, LLM-first persist-after, XML tags for history]

key-files:
  created: []
  modified:
    - app/database/chats.py
    - app/services/chats.py

key-decisions:
  - "create_chain uses MessagesPlaceholder('history') only -- no ('human', '{input}') slot since all messages go through history"
  - "get_history uses two separate queries (Chat ownership check + Message fetch) instead of JOIN"
  - "get_messages returns (Chat | None, list[Message], next_cursor) tuple for ownership verification at DB layer"
  - "Prompt template unchanged -- already compatible with {lang} variable from create_chain"

patterns-established:
  - "Session-in-init: ChatsDB.__init__(db) stores self.db, all methods use self.db"
  - "Service creates DB internally: ChatService.__init__ creates ChatsDB(db), router never touches ChatsDB"
  - "Default var binding in lambda for policy.ainvoke closures"

requirements-completed: [REFACT-03, REFACT-04]

duration: 2min
completed: 2026-03-11
---

# Phase 15 Plan 02: DB and Service Layer Summary

**ChatsDB with session-in-init pattern and 6 CRUD methods, ChatService with chain-based DI orchestrating LLM calls and XML-tagged history construction**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-11T04:59:27Z
- **Completed:** 2026-03-11T05:01:19Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- ChatsDB fully rewritten with session-in-init: create, save_message, get_history, get_messages, delete, list_chats
- ChatService rewritten with chain-based DI: create_chat (LLM-first, persist-after), followup (history load, capacity check, LLM call, dual message save)
- Cursor pagination transplanted from old Chats class with _encode_cursor/_decode_cursor static methods
- History construction uses XML tags for phrase/comment per CONTEXT.md decisions

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite ChatsDB with session-in-init pattern** - `93af4ce` (feat)
2. **Task 2: Rewrite ChatService and update prompt template** - `1ef2512` (feat)

## Files Created/Modified
- `app/database/chats.py` - Full rewrite: ChatsDB with session-in-init, 6 public methods, cursor pagination
- `app/services/chats.py` - Full rewrite: create_chain(), ChatService with chain/policy/config/db DI

## Decisions Made
- create_chain uses only MessagesPlaceholder("history") without a separate ("human", "{input}") slot, since all messages (including the initial phrase) are passed through history
- get_history uses two separate queries instead of a JOIN: first query verifies Chat ownership, second fetches messages -- simpler and clearer than JOIN with empty-result ambiguity
- get_messages returns a 3-tuple (Chat | None, list[Message], next_cursor) to combine ownership check with pagination in one call
- Prompt template left unchanged since the existing {lang} variable works with the new lang_directive pattern

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ChatsDB and ChatService fully functional and importable
- Plan 03 (router wiring, DI updates, main.py lifespan) can import and use both layers
- Plan 04 (tests) can test against new service and DB interfaces
- No blockers

## Self-Check: PASSED

All files verified present, all commit hashes found in git log.

---
*Phase: 15-refactor-chats*
*Completed: 2026-03-11*
