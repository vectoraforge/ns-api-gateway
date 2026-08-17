---
phase: 26-service-and-database-rewiring
plan: 02
subsystem: service, api
tags: [fastapi, dependency-injection, quota, subscription-plan]

# Dependency graph
requires:
  - phase: 26-service-and-database-rewiring
    plan: 01
    provides: "UsageDB.try_increment with monthly_quota param, AppConfig.quotas as dict[SubscriptionPlan, int]"
provides:
  - "ChatService with quotas dict injection and user: User method signatures"
  - "Config-driven monthly_limit in GET /users/me (no DB lookup)"
  - "Chat routers passing user object to service layer"
affects: [26-test-updates, service-layer, quota-enforcement]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Caller-provided User object instead of user_id for quota-aware methods"]

key-files:
  created: []
  modified:
    - src/nativespeaker/api/services/chats.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/routers/chats.py
    - src/nativespeaker/api/routers/users.py

key-decisions:
  - "Only create_chat and send_message changed to user: User -- get_messages, list_chats, delete_chat keep user_id: UUID to avoid unnecessary churn"
  - "Users router uses config.quotas[user.subscription_plan] directly -- no intermediate service method needed"

patterns-established:
  - "Quota-aware service methods accept User object to resolve tier-specific limits from injected config"
  - "Config dependency injection via Depends(get_config) in router handlers that need quota data"

requirements-completed: [QUOTA-03, QUOTA-04]

# Metrics
duration: 3min
completed: 2026-03-23
---

# Phase 26 Plan 02: Service and Router Quota Wiring Summary

**Threaded config-driven quotas through ChatService via DI, changed create_chat/send_message to accept User objects, and replaced get_monthly_limit DB call with config.quotas lookup in /users/me**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-23T23:01:45Z
- **Completed:** 2026-03-23T23:05:15Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- ChatService now accepts quotas dict and resolves monthly_quota from user.subscription_plan before calling try_increment
- Chat routers pass full User object to create_chat/send_message instead of user.id
- GET /users/me resolves monthly_limit from config.quotas, eliminating the last get_monthly_limit DB call
- dependencies.py passes quotas=config.quotas to ChatService constructor

## Task Commits

Each task was committed atomically:

1. **Task 1: Add quotas to ChatService and change user_id to user** - `b9dffb1` (feat)
2. **Task 2: Update chat and user routers for new service signatures** - `5626d7f` (feat)

## Files Created/Modified
- `src/nativespeaker/api/services/chats.py` - Added quotas param to __init__, changed create_chat/send_message to accept user: User, quota resolution via self.quotas[user.subscription_plan]
- `src/nativespeaker/api/app/dependencies.py` - Added quotas=config.quotas to ChatService constructor call
- `src/nativespeaker/api/routers/chats.py` - Changed create_chat/send_message calls to pass user=user instead of user_id=user.id
- `src/nativespeaker/api/routers/users.py` - Added get_config/AppConfig imports, config param to get_me, replaced get_monthly_limit with config.quotas lookup

## Decisions Made
- Only create_chat and send_message changed to user: User -- get_messages, list_chats, delete_chat keep user_id: UUID to avoid unnecessary churn since they don't interact with quotas
- Users router uses config.quotas[user.subscription_plan] directly in the handler rather than introducing a service method, keeping the lookup simple and explicit

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All service and router layers now use config-driven quotas
- No references to get_monthly_limit remain in src/nativespeaker/api/
- No plans table JOINs remain in any source file
- Tests will need updating to match new ChatService constructor (quotas param) and method signatures (user: User)

## Self-Check: PASSED

- All 4 modified files verified present on disk
- Commit b9dffb1 (Task 1) verified in git log
- Commit 5626d7f (Task 2) verified in git log
- No get_monthly_limit references remain in src/nativespeaker/api/
- No plans table JOINs remain in src/nativespeaker/api/

---
*Phase: 26-service-and-database-rewiring*
*Completed: 2026-03-23*
