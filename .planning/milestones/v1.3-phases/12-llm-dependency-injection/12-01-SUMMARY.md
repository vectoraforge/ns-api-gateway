---
phase: 12-llm-dependency-injection
plan: 01
subsystem: api
tags: [fastapi, dependency-injection, langchain, basechatmodel]

# Dependency graph
requires:
  - phase: 11-error-contract-hardening
    provides: Error handlers and exception infrastructure used by dependencies
provides:
  - app/dependencies.py with all 4 FastAPI dependency functions (get_db, get_user_id, get_service, get_config)
  - Route handlers using Depends() instead of request.app.state
  - BaseChatModel type annotation on AnalysisService (provider-agnostic)
affects: [12-02-test-migration, 13-endpoint-merge]

# Tech tracking
tech-stack:
  added: []
  patterns: [centralized-di-module, depends-over-request-state, basechatmodel-annotation]

key-files:
  created: [app/dependencies.py]
  modified: [app/services.py, app/routers/prompts.py, app/routers/root.py, app/auth.py, app/database.py]

key-decisions:
  - "All 4 FastAPI dependencies consolidated in app/dependencies.py — single import source"
  - "get_db and get_user_id deleted from original modules (not re-exported)"
  - "AnalysisService llm annotation changed from ChatOpenAI to BaseChatModel (provider-agnostic)"
  - "Route handlers have zero Request imports — clean Depends()-only signatures"

patterns-established:
  - "Centralized DI: all FastAPI dependency functions live in app/dependencies.py"
  - "Depends() for app.state access: routes never import Request or touch app.state directly"
  - "BaseChatModel annotation: services reference langchain_core base class, not vendor-specific"

requirements-completed: [DI-01, DI-02]

# Metrics
duration: 6min
completed: 2026-03-02
---

# Phase 12 Plan 01: LLM Dependency Injection Summary

**Centralized all FastAPI dependencies into app/dependencies.py, migrated route handlers to Depends(), and changed AnalysisService llm type to BaseChatModel**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-02T22:52:14Z
- **Completed:** 2026-03-02T22:58:52Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Created `app/dependencies.py` with all 4 dependency functions: `get_db`, `get_user_id`, `get_service`, `get_config`
- Migrated all 5 prompts.py route handlers and root.py handler to use `Depends()` instead of `request.app.state.*`
- Removed `Request` from all route handler signatures across both router files
- Changed `AnalysisService.__init__` llm type annotation from `ChatOpenAI` to `BaseChatModel`
- Deleted `get_db` from `database.py` and `get_user_id` from `auth.py` (originals removed, not re-exported)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create app/dependencies.py and update services.py type annotation** - `40d7eb1` (feat)
2. **Task 2: Migrate route handlers to Depends() and delete original dependency functions** - `104f8f6` (feat)

## Files Created/Modified
- `app/dependencies.py` - New module hosting all 4 FastAPI dependency functions
- `app/services.py` - Changed llm type annotation from ChatOpenAI to BaseChatModel
- `app/routers/prompts.py` - All 5 handlers use Depends(get_service/get_config), no Request import
- `app/routers/root.py` - Root handler uses Depends(get_service), no Request import
- `app/auth.py` - Removed get_user_id function and fastapi imports
- `app/database.py` - Removed get_db function, AsyncGenerator import, and exceptions import

## Decisions Made
- Import order in dependencies.py follows isort convention: stdlib, third-party, local
- get_service and get_config accept Request internally to read app.state (routes never see Request)
- get_user_id retains internal app.state.verifier access per CONTEXT.md decision
- Removed unused imports from database.py (AsyncGenerator, AsyncSession, DatabaseNotInitializedError) and auth.py (Header, Request from fastapi)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed import ordering in services.py**
- **Found during:** Task 1
- **Issue:** After replacing langchain_openai import with langchain_core.language_models, ruff flagged unsorted imports
- **Fix:** Reordered langchain_core imports alphabetically (language_models before prompts)
- **Files modified:** app/services.py
- **Verification:** ruff check passed
- **Committed in:** 40d7eb1 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor import reordering for linter compliance. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Production code fully migrated to Depends() pattern
- Plan 12-02 (test migration) can proceed: tests need to update imports from app.database/app.auth to app.dependencies and switch from app.state assignments to dependency_overrides
- test_exception_handlers.py intentionally NOT touched (tests get_user_id internal behavior with app.state.verifier)

## Self-Check: PASSED

- FOUND: app/dependencies.py
- FOUND: 12-01-SUMMARY.md
- FOUND: commit 40d7eb1 (Task 1)
- FOUND: commit 104f8f6 (Task 2)

---
*Phase: 12-llm-dependency-injection*
*Completed: 2026-03-02*
