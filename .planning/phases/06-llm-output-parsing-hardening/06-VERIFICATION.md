---
phase: 06-llm-output-parsing-hardening
verified: 2026-02-27T09:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 6: LLM Output Parsing Hardening Verification Report

**Phase Goal:** LLM responses are schema-guaranteed by the API provider, eliminating the fragile `JsonOutputParser` -> `model_validate` pipeline
**Verified:** 2026-02-27
**Status:** PASSED
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LLM responses are schema-guaranteed by the API provider, not parsed client-side | VERIFIED | `app/services.py` line 52-54: `self.llm.with_structured_output(AnalyzeResponseLLM, method="json_schema", strict=True)`; `JsonOutputParser` absent from all files |
| 2 | Both `analyze()` and `chat()` methods use structured output instead of `JsonOutputParser` | VERIFIED | Both methods use `self.chain` (built once in `__init__`); `response.model_dump()` at lines 136, 140, 151, 155 -- no dict parsing anywhere |
| 3 | Test mocks return `AnalyzeResponseLLM` Pydantic instances, not raw dicts | VERIFIED | `test_services.py` lines 63-67, 86, 147: all success-path tests construct `AnalyzeResponseLLM(...)` instances; `service.chain.ainvoke.return_value = llm_response` pattern used throughout |
| 4 | A malformed LLM response is classified as permanent (not transient), so it does not trigger retries | VERIFIED | `_is_transient_error(ValidationError(...))` returns `False`; `_is_transient_error(Exception("malformed"))` returns `False`; only OpenAI network/rate/server errors return `True` |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/schema.py` | `AnalyzeResponseLLM` Pydantic model for LLM structured output | VERIFIED | Lines 18-23: class with `issues`, `alternatives`, `assessment` fields; placed before `AnalyzeResponse` as planned |
| `app/services.py` | Chain construction using `with_structured_output` instead of `JsonOutputParser` | VERIFIED | Line 52-54: `self.llm.with_structured_output(AnalyzeResponseLLM, method="json_schema", strict=True)`; chain stored as `self.chain` |
| `tests/unit/test_services.py` | Updated test mocks returning `AnalyzeResponseLLM` instances | VERIFIED | Line 7 imports `AnalyzeResponseLLM, Issue`; 3 success tests use `AnalyzeResponseLLM(...)` instances; no `JsonOutputParser` or `ChatPromptTemplate` patches |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/services.py` | `app/schema.py` | `import AnalyzeResponseLLM` | WIRED | Line 10: `from app.schema import AnalyzeResponse, AnalyzeResponseLLM, ExamplesResponse` |
| `app/services.py` | `langchain_openai.ChatOpenAI.with_structured_output` | `self.llm.with_structured_output(AnalyzeResponseLLM, method='json_schema', strict=True)` | WIRED | Lines 52-54: exact pattern present; `self.chain = prompt_template | structured_llm` at line 60 |
| `app/services.py` | `AnalyzeResponse` constructor | `**response.model_dump()` dict unpacking | WIRED | Lines 140 and 155: `AnalyzeResponse(text=text, lang=lang, chat_id=chat_id, **response.model_dump())` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LLM-01 | 06-01-PLAN.md | Replace `JsonOutputParser()` with `self.llm.with_structured_output(AnalyzeResponseLLM)` for schema-guaranteed LLM responses; introduce `AnalyzeResponseLLM` intermediate Pydantic model; update test mocks | SATISFIED | `JsonOutputParser` absent from entire codebase; `AnalyzeResponseLLM` exists in `schema.py`; `with_structured_output(strict=True)` in `services.py`; all test mocks updated; 54 unit tests pass |

No orphaned requirements. REQUIREMENTS.md maps only LLM-01 to Phase 6 and that requirement is fully implemented.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | - |

No TODOs, FIXMEs, placeholders, empty implementations, or stub returns detected in the three modified files.

---

### Human Verification Required

None. All success criteria are verifiable programmatically:

- Structured output API call is a code-level construct (`with_structured_output`), not a visual or real-time behavior.
- Test suite runs and passes deterministically.
- Transient error classification is a pure function with deterministic output.

---

### Commit Verification

Both commits documented in SUMMARY.md are verified present in the repository:

- `2a599eb` -- feat(06-01): replace JsonOutputParser with structured output (`app/schema.py`, `app/services.py`)
- `5df8569` -- test(06-01): update test mocks for structured output chain (`tests/unit/test_services.py`)

---

### Test Suite Results

```
54 passed, 4 deselected in 0.19s
```

All 54 non-database unit tests pass. The 4 deselected tests require a live database (marked `db`) and are not applicable to this phase's changes. The SUMMARY's claim of "72 tests" refers to the combined unit + integration count from Phase 5; the unit-only count is 54.

---

## Summary

Phase 6 goal is fully achieved. The fragile `JsonOutputParser` -> `model_validate` pipeline has been eliminated entirely. The LLM chain now uses OpenAI Structured Outputs (`with_structured_output(strict=True)`) which enforces the `AnalyzeResponseLLM` schema at token-generation level -- before any response reaches the client. Both `analyze()` and `chat()` share a single chain instance built in `__init__`. Test mocks are correctly updated to return `AnalyzeResponseLLM` instances. Parsing failures are classified as permanent errors by `_is_transient_error`, so malformed responses do not trigger the retry loop.

---

_Verified: 2026-02-27_
_Verifier: Claude (gsd-verifier)_
