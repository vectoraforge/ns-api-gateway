---
phase: quick
plan: 260325-jrd
subsystem: api
tags: [pydantic, serialization, fastapi, testing]

# Dependency graph
requires: []
provides:
  - "MessageResponse.content properly serializes HumanContent and AIContent fields"
  - "Unit regression tests for content serialization"
  - "Hardened e2e assertions catching empty content dicts"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Use concrete union types (HumanContent | AIContent) instead of BaseModel for Pydantic v2 serialization"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/schema.py
    - tests/unit/test_models.py
    - tests/e2e/test_chats.py

key-decisions:
  - "Used HumanContent | AIContent union type instead of ContentUnion discriminated union -- simpler, works correctly for serialization"

patterns-established:
  - "Pydantic v2 union serialization: never use BaseModel as a field type when concrete subtypes are known"

requirements-completed: [FIX-SERIALIZATION, FIX-E2E-ASSERTIONS, FIX-UNIT-SERIALIZATION]

# Metrics
duration: 6min
completed: 2026-03-25
---

# Quick Fix 260325-jrd: Fix MessageResponse Content Serialization Summary

**Fixed MessageResponse.content from BaseModel to HumanContent | AIContent, added 3 serialization regression tests and hardened 4 e2e content assertions**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-25T21:18:20Z
- **Completed:** 2026-03-25T21:24:27Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Fixed root cause: `content: BaseModel` in MessageResponse caused Pydantic v2 to serialize content as `{}` (empty dict) because it had no knowledge of subclass fields
- Added 3 unit tests verifying `.model_dump()` produces correct field names for AIContent (response, issues, suggestions) and HumanContent (phrase, comment), plus a guard against empty content
- Hardened 4 e2e test methods to assert `"response" in data["content"]` and `data["content"] != {}`, catching serialization regressions at the HTTP layer

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix MessageResponse.content type and add serialization regression test**
   - `31fcf51` (test) - RED: add failing serialization tests
   - `ad75e91` (feat) - GREEN: fix schema type to HumanContent | AIContent
2. **Task 2: Harden e2e test assertions on content structure** - `ea6bea1` (test)

_Note: Task 1 followed TDD with RED/GREEN commits_

## Files Created/Modified
- `src/nativespeaker/api/schema.py` - Changed `content: BaseModel` to `content: HumanContent | AIContent`, added HumanContent import
- `tests/unit/test_models.py` - Added 3 new tests: test_ai_content_serialization, test_human_content_serialization, test_content_never_empty
- `tests/e2e/test_chats.py` - Added content structure assertions to test_create_chat_english, test_create_chat_spanish, test_create_chat_with_comment, test_followup_message

## Decisions Made
- Used `HumanContent | AIContent` plain union instead of `ContentUnion` discriminated union -- both serialize correctly, but the plain union is simpler and matches the schema's needs (no need for discriminator logic at the API response level)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Python worktree module resolution: the editable install (`pip install -e .`) points to the main repo's `src/`, not the worktree's `src/`. Tests were run with `PYTHONPATH` prepended to use the worktree's modified source. This is a pre-existing environment issue, not caused by this fix.
- Pre-existing `tests/` collection error: duplicate `test_users.py` filenames across `tests/unit/` and `tests/e2e/` causes pytest module import collision when running `pytest tests/` as a whole. Not in scope for this fix.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Serialization bug fixed, tests hardened
- No blockers

## Self-Check: PASSED

All 3 modified files verified on disk. All 3 commit hashes (31fcf51, ad75e91, ea6bea1) found in git log.

---
*Quick fix: 260325-jrd*
*Completed: 2026-03-25*
