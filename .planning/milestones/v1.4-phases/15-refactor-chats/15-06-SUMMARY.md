---
phase: 15-refactor-chats
plan: 06
subsystem: api
tags: [ty, type-checking, isinstance, type-narrowing, pydantic-settings]

requires:
  - phase: 15-refactor-chats/05
    provides: "Flattened module structure and redesigned message content model"
provides:
  - "Zero ty errors in app/service.py, app/api/main.py, app/config.py"
  - "isinstance-based type narrowing pattern for HumanContent/AIContent union"
  - "Assert-based None narrowing for optional config fields"
affects: [15-refactor-chats/07, 15-refactor-chats/08]

tech-stack:
  added: []
  patterns: [isinstance-narrowing-for-union-types, assert-narrowing-for-optional-fields, type-ignore-for-framework-patterns]

key-files:
  created: []
  modified: [app/service.py, app/api/main.py, app/config.py]

key-decisions:
  - "isinstance narrowing replaces Role enum check for type-safe content access"
  - "Assert-based narrowing for config/prompt fields known non-None at runtime"
  - "type: ignore annotations only for framework incompatibilities (FastAPI openapi, pydantic-settings _env_prefix)"
  - "Path() constructor wrapping for Field defaults instead of type: ignore"

patterns-established:
  - "isinstance narrowing: use isinstance(msg.content, HumanContent) instead of role enum checks when accessing union-typed content"
  - "assert narrowing: use assert x is not None before accessing optional fields known to be set at runtime"
  - "type: ignore scope: only for framework pattern mismatches (pydantic-settings, FastAPI), never for application logic"

requirements-completed: [REFACT-01, REFACT-04, REFACT-06]

duration: 2min
completed: 2026-03-16
---

# Phase 15 Plan 06: Fix ty Type Errors Summary

**Eliminated all 29 ty type-check errors across service.py, main.py, and config.py using isinstance narrowing, assert guards, and targeted type: ignore annotations**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-16T21:51:33Z
- **Completed:** 2026-03-16T21:53:43Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Resolved 6 unresolved-attribute errors in service.py via isinstance type narrowing on HumanContent/AIContent union
- Resolved 19 errors in main.py via assert narrowing for AppConfig|None and type: ignore for FastAPI openapi pattern
- Resolved 4 errors in config.py via Path() constructor wrapping and type: ignore for pydantic-settings internals
- Total ty errors reduced from ~40 to 12 remaining (in other files)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix type errors in app/service.py and app/api/main.py** - `d36078a` (fix)
2. **Task 2: Fix type errors in app/config.py** - `a537a99` (fix)

## Files Created/Modified
- `app/service.py` - isinstance narrowing in ask_llm for union content access, assert for message content
- `app/api/main.py` - Assert narrowing for config and prompt, type: ignore on openapi monkey-patch
- `app/config.py` - Path() wrapped Field defaults, type: ignore on _env_prefix kwarg

## Decisions Made
- Used isinstance narrowing instead of Role enum check in ask_llm loop -- serves same purpose but ty understands it for type narrowing
- Used assert-based narrowing for config fields known to be non-None at runtime (set by model_validator)
- Used Path() constructor wrapping instead of type: ignore for config Field defaults -- cleaner and more explicit
- Reserved type: ignore only for genuine framework pattern incompatibilities

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 12 ty errors remain in other files (routers, database, etc.) for plans 07-08
- All patterns established here (isinstance narrowing, assert guards) apply to remaining fixes

## Self-Check: PASSED

- All 3 modified files exist on disk
- Commit d36078a found in git log
- Commit a537a99 found in git log

---
*Phase: 15-refactor-chats*
*Completed: 2026-03-16*
