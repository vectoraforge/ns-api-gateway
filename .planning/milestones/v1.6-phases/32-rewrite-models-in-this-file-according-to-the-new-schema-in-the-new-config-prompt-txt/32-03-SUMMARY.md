---
phase: 32-rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt
plan: 03
subsystem: testing
tags: [pytest, pydantic, dict-content, llm-models, out-of-scope]

# Dependency graph
requires:
  - phase: 32-02
    provides: "Rewritten service layer with dict content, orjson, LLM dispatch, and reject handling"
provides:
  - "Full unit test suite green against new model contracts"
  - "LLM model test coverage (AnalyzeInput, FollowUpInput, AnalyzeResponse, FollowUpResponse, RejectResponse)"
  - "Service tests with dict mock returns and dict access assertions"
  - "OutOfScopeError and reject flow test coverage"
  - "E2E test payloads updated with new field names (context, question)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dict mock returns with resolved_mode keys for service tests"
    - "Dict access assertions (content['response']) replacing attribute access"

key-files:
  created: []
  modified:
    - tests/unit/test_models.py
    - tests/unit/test_services.py
    - tests/unit/test_exception_handlers.py
    - tests/unit/test_error_contract.py
    - tests/e2e/conftest.py
    - tests/e2e/test_chats.py
    - tests/e2e/test_flows.py
    - tests/e2e/test_error_cases.py

key-decisions:
  - "Dict access in assertions (content['response']) matches new dict-based Message.content contract"
  - "TestRejectHandling covers both OutOfScopeError raise and no-persistence guarantee (D-09)"

patterns-established:
  - "Service test mocks return raw dicts with resolved_mode keys matching LLM response contract"
  - "E2E test payloads use context for create_chat, question for followup"

requirements-completed: []

# Metrics
duration: 5min
completed: 2026-03-26
---

# Phase 32 Plan 03: Test Suite Alignment Summary

**Full unit test suite (163 tests) rewritten to validate dict-based content, LLM model contracts, and reject/out-of-scope flow**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-26T06:47:25Z
- **Completed:** 2026-03-26T06:53:18Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- All 163 unit tests pass against new model contracts with zero failures
- LLM model tests added: AnalyzeInput, FollowUpInput, AnalyzeResponse, FollowUpResponse, RejectResponse
- Service tests rewritten: dict mocks, dict assertions, question= kwarg, TestRejectHandling with OutOfScopeError
- OutOfScopeError added to exception handler CASES and error code assertion set
- E2E test payloads updated: comment -> context, content -> question in all JSON payloads
- All references to AIContent, HumanContent, schema module, and models.content removed from test files

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite unit test files for new model and service contracts** - `af4b2fa` (test)
2. **Task 2: Update e2e test payloads for field renames and dict content** - `32032ce` (test)

## Files Created/Modified
- `tests/unit/test_models.py` - Rewrote imports, added LLM model tests, converted MessageResponse tests to dict content
- `tests/unit/test_services.py` - Rewrote mocks to return dicts, added TestRejectHandling, renamed methods/kwargs
- `tests/unit/test_exception_handlers.py` - Added OutOfScopeError import, CASES entry, and code assertion
- `tests/unit/test_error_contract.py` - Added out_of_scope to CONTRACT_CODES set (deviation fix)
- `tests/e2e/conftest.py` - Removed AIContent/HumanContent imports, create_chat helper uses plain dicts
- `tests/e2e/test_chats.py` - comment -> context, content -> question in JSON payloads
- `tests/e2e/test_flows.py` - content -> question in followup payload
- `tests/e2e/test_error_cases.py` - content -> question in followup payload

## Decisions Made
- Dict access in assertions (content["response"]) matches new dict-based Message.content contract
- TestRejectHandling covers both OutOfScopeError raise and no-persistence guarantee (D-09)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed CONTRACT_CODES set missing out_of_scope**
- **Found during:** Task 1 (unit test rewrite)
- **Issue:** test_error_contract.py CONTRACT_CODES set did not include "out_of_scope", causing test_openapi_error_response_code_is_enum to fail because ErrorCode Literal was updated in Plan 01
- **Fix:** Added "out_of_scope" to CONTRACT_CODES set
- **Files modified:** tests/unit/test_error_contract.py
- **Verification:** All 163 unit tests pass
- **Committed in:** af4b2fa (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix necessary for correctness -- ErrorCode was expanded in Plan 01 but the contract test was not updated. No scope creep.

## Issues Encountered
- test_webhooks.py line 16 already used `response.content` (not `response.comment` as plan stated) -- no change needed

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full unit test suite green (163 tests)
- E2E test payloads ready for live execution (requires Firebase + PostgreSQL + OpenAI)
- Phase 32 complete -- all 3 plans executed

---
*Phase: 32-rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt*
*Completed: 2026-03-26*
