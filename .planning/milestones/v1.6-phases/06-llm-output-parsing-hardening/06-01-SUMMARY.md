---
phase: 06-llm-output-parsing-hardening
plan: 01
subsystem: api
tags: [langchain, pydantic, structured-output, openai]

requires:
  - phase: 05-config-fix-dead-code
    provides: clean services.py with working analyze/chat pipeline
provides:
  - AnalyzeResponseLLM Pydantic model for schema-guaranteed LLM output
  - with_structured_output chain construction in AnalysisService.__init__
  - Simplified test mock pattern (direct chain assignment)
affects: []

tech-stack:
  added: []
  patterns:
    - "with_structured_output(strict=True) for constrained decoding"
    - "Chain built once in __init__, reused across methods"
    - "Separate LLM schema (AnalyzeResponseLLM) from API schema (AnalyzeResponse)"

key-files:
  created: []
  modified:
    - app/schema.py
    - app/services.py
    - tests/unit/test_services.py

key-decisions:
  - "Used method='json_schema' with strict=True for constrained decoding at token-generation level"
  - "Chain built once in __init__ rather than per-call to avoid redundant construction"

patterns-established:
  - "LLM output schema separate from API response schema: AnalyzeResponseLLM vs AnalyzeResponse"
  - "Test mocks assign service.chain directly instead of patching internal constructors"

requirements-completed: [LLM-01]

duration: 3min
completed: 2026-02-28
---

# Phase 06 Plan 01: LLM Output Parsing Hardening Summary

**Replaced JsonOutputParser with OpenAI Structured Outputs via with_structured_output(strict=True) for schema-guaranteed LLM responses**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T05:31:27Z
- **Completed:** 2026-02-28T05:34:28Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Eliminated fragile JsonOutputParser -> model_validate pipeline entirely
- LLM responses now schema-guaranteed at token-generation level via OpenAI constrained decoding
- Chain constructed once in __init__, reused by both analyze() and chat() methods
- Test mocks simplified from 6-line patch blocks to 2-line direct assignments

## Task Commits

Each task was committed atomically:

1. **Task 1: Add AnalyzeResponseLLM model and refactor services.py** - `2a599eb` (feat)
2. **Task 2: Update test mocks for structured output chain** - `5df8569` (test)

## Files Created/Modified
- `app/schema.py` - Added AnalyzeResponseLLM model (LLM output subset of AnalyzeResponse)
- `app/services.py` - Replaced JsonOutputParser with with_structured_output, chain in __init__
- `tests/unit/test_services.py` - Updated all mocks to use AnalyzeResponseLLM instances and direct chain assignment

## Decisions Made
- Used `method="json_schema"` with `strict=True` for full constrained decoding (OpenAI Structured Outputs API)
- Built chain once in `__init__` to avoid redundant construction on every analyze/chat call
- Separated LLM schema (`AnalyzeResponseLLM`) from API schema (`AnalyzeResponse`) since LLM does not produce text, lang, or chat_id fields

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Structured output foundation complete
- All 72 tests pass with zero failures
- _is_transient_error correctly classifies parsing errors as non-transient (verified by existing behavior, no code change needed)

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 06-llm-output-parsing-hardening*
*Completed: 2026-02-28*
