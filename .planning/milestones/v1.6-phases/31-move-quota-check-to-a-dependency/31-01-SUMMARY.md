---
phase: 31-move-quota-check-to-a-dependency
plan: 01
subsystem: api
tags: [fastapi, depends, quota, dependency-injection, single-responsibility]

# Dependency graph
requires:
  - phase: 26-rewrite-usagedb-config-quotas
    provides: "UsageDB.try_increment with caller-provided monthly_quota"
provides:
  - "require_quota FastAPI dependency in app/dependencies.py"
  - "ChatService free of quota/usage logic (single-responsibility)"
  - "POST /chats and POST /chats/{chat_id} enforce quota via Depends(require_quota)"
affects: [31-02, testing, chat-routes]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Side-effect dependencies via _param: None = Depends(fn) for pre-route guards"]

key-files:
  created: []
  modified:
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/services/chats.py
    - src/nativespeaker/api/routers/chats.py

key-decisions:
  - "require_quota placed after get_current_user in dependency resolution order to share user instance"
  - "_quota: None = Depends(require_quota) pattern for side-effect-only dependencies"

patterns-established:
  - "Side-effect guard dependency: _param: None = Depends(guard_fn) in route signatures for pre-execution checks"

requirements-completed: [DEP-01, DEP-02, DEP-03, DEP-04, DEP-05]

# Metrics
duration: 5min
completed: 2026-03-25
---

# Phase 31 Plan 01: Move Quota Check to a Dependency Summary

**Extracted quota enforcement from ChatService into require_quota FastAPI dependency wired on POST chat routes**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-25T08:30:13Z
- **Completed:** 2026-03-25T08:35:26Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created `require_quota` async dependency in `dependencies.py` that atomically increments usage via `UsageDB.try_increment` and raises `QuotaExceededError` on limit
- Removed all quota/usage logic from `ChatService` (no `quotas` param, no `self.usage_db`, no `try_increment` calls, no `QuotaExceededError` import)
- Wired `_quota: None = Depends(require_quota)` into `POST /chats` and `POST /chats/{chat_id}` routes only; GET/DELETE routes unaffected

## Task Commits

Each task was committed atomically:

1. **Task 1: Add require_quota dependency and strip quota from ChatService** - `a7ce60d` (refactor)
2. **Task 2: Wire require_quota into chat POST routes** - `c981b7b` (feat)

## Files Created/Modified
- `src/nativespeaker/api/app/dependencies.py` - Added `require_quota` async dependency; removed `quotas=config.quotas` from `get_chat_service`; added imports for `UsageDB`, `QuotaExceededError`, `datetime`
- `src/nativespeaker/api/services/chats.py` - Removed `quotas` param, `self.usage_db`, `self.quotas`, quota check blocks from `create_chat` and `send_message`; removed unused imports (`datetime`, `UsageDB`, `QuotaExceededError`, `SubscriptionPlan`)
- `src/nativespeaker/api/routers/chats.py` - Added `require_quota` import; added `_quota: None = Depends(require_quota)` to `create_chat` and `send_message` signatures

## Decisions Made
- Used `_quota: None = Depends(require_quota)` pattern (underscore-prefixed, None-typed) for side-effect-only dependency -- consistent with FastAPI convention for guard dependencies
- Placed `require_quota` after `get_current_user` in dependency graph so FastAPI reuses the same `User` and `AsyncSession` instances (no duplicate auth or DB session)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Production code refactored; ready for Plan 02 (test updates) to adjust test fixtures that previously passed `quotas` to `ChatService`
- Any test constructing `ChatService` directly will need the `quotas` parameter removed

## Self-Check: PASSED

- All 3 modified files exist on disk
- Both task commits (a7ce60d, c981b7b) found in git history
- SUMMARY.md created at expected path

---
*Phase: 31-move-quota-check-to-a-dependency*
*Completed: 2026-03-25*
