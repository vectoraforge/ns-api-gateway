---
phase: 11-error-contract-hardening
verified: 2026-03-02T20:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
gaps: []
---

# Phase 11: Error Contract Hardening Verification Report

**Phase Goal:** The API exposes exactly 5 status codes with fixed opaque error codes; no raw exception text reaches callers
**Verified:** 2026-03-02T20:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                              | Status     | Evidence                                                                                         |
|----|----------------------------------------------------------------------------------------------------|------------|--------------------------------------------------------------------------------------------------|
| 1  | Every error response body contains exactly one field: `code`, set to one of the 5 fixed strings   | VERIFIED   | All 17 handlers use `ErrorResponse(code=...).model_dump()`; test_handler asserts `list(body.keys()) == ["code"]`; 17 tests confirm |
| 2  | No raw exception text appears in any error response body                                           | VERIFIED   | `grep 'str(exc)' app/errors.py` = 0; `grep 'exc.detail' app/errors.py` = 0; no `exc.lang`, `exc.role`, `exc.limit` in response content |
| 3  | Status codes 409, 413, 502, 422 never appear in responses; remapped to 400, 400, 503, 400         | VERIFIED   | No `status_code=409/413/502/422` in any handler return; `_STATUS_REMAP` covers all 4; parametrized test cases confirm 400/503 |
| 4  | Undefined route returns 404 with `code not_found`; wrong HTTP method returns 400 with `code invalid_request` | VERIFIED | `test_undefined_route_returns_404` and `test_wrong_method_returns_400` both pass via `http_exception_handler` + `_STATUS_REMAP` |
| 5  | `ErrorResponse` Pydantic model is visible in OpenAPI schema at `/docs` with no 422 entries         | VERIFIED   | `test_openapi_schema_contains_error_response`, `test_openapi_schema_has_no_422`, `test_openapi_error_response_code_is_enum` all pass |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                                     | Expected                                                  | Status     | Details                                                                                     |
|----------------------------------------------|-----------------------------------------------------------|------------|----------------------------------------------------------------------------------------------|
| `app/schema.py`                              | ErrorResponse Pydantic model with Literal code field      | VERIFIED   | `ErrorCode = Literal[5 strings]`, `class ErrorResponse(BaseModel): code: ErrorCode` at lines 7-17 |
| `app/errors.py`                              | All handlers returning opaque ErrorResponse bodies; `_STATUS_REMAP` dict | VERIFIED   | `_STATUS_REMAP` at line 28 (10 entries), `_CODE_MAP` at line 41, 17 handlers all use `ErrorResponse(code=...).model_dump()` |
| `app/main.py`                                | `custom_openapi()` function and `app.openapi = custom_openapi` assignment | VERIFIED   | `custom_openapi()` at line 97, `app.openapi = custom_openapi` at line 114; `responses=` kwarg at lines 81-87 |
| `tests/unit/test_exception_handlers.py`      | Updated assertions for new body shape and remapped codes  | VERIFIED   | CASES uses 400 for `history_limit`/`msg_too_large`, 503 for `permanent_llm`; body asserts `list(body.keys()) == ["code"]` |
| `tests/unit/test_error_contract.py`          | Contract enforcement tests: wrong method, undefined route, OpenAPI schema shape | VERIFIED   | 8 tests in `TestStatusCodeRemapping` and `TestOpenAPISchema`; all pass |

### Key Link Verification

| From             | To                   | Via                               | Status   | Details                                                              |
|------------------|----------------------|-----------------------------------|----------|----------------------------------------------------------------------|
| `app/errors.py`  | `app/schema.py`      | `from app.schema import ErrorResponse` | WIRED | Line 24 of errors.py: `from app.schema import ErrorResponse`         |
| `app/errors.py`  | all handlers         | `ErrorResponse(code=...).model_dump()` | WIRED | 17 occurrences of `ErrorResponse(code=` in errors.py confirmed       |
| `app/main.py`    | `app/schema.py`      | `from app.schema import ErrorResponse` | WIRED | Line 17 of main.py: `from app.schema import ErrorResponse`           |
| `app/main.py`    | FastAPI `app.openapi` | `app.openapi = custom_openapi`   | WIRED    | Line 114 of main.py: `app.openapi = custom_openapi`                  |

### Requirements Coverage

| Requirement | Source Plan | Description                                                              | Status    | Evidence                                                                                  |
|-------------|-------------|--------------------------------------------------------------------------|-----------|-------------------------------------------------------------------------------------------|
| ERR-01      | 11-01       | API returns exactly 5 status codes: 400, 401, 404, 503, 500             | SATISFIED | All 17 handlers emit only these 5 codes; `_STATUS_REMAP` covers all other Starlette codes |
| ERR-02      | 11-01       | Error responses use fixed string codes                                   | SATISFIED | `ErrorCode = Literal["invalid_request", "unauthorized", "not_found", "service_unavailable", "internal_error"]` enforces at model level |
| ERR-03      | 11-01       | No raw exception text appears in error response bodies                   | SATISFIED | Zero `str(exc)`, `exc.detail`, `exc.lang`, `exc.role`, `exc.limit` in handler response content |
| ERR-04      | 11-02       | ErrorResponse Pydantic model documented in OpenAPI schema                | SATISFIED | `custom_openapi()` + `responses=` kwarg; `test_openapi_schema_contains_error_response` passes |
| ERR-05      | 11-01       | StarletteHTTPException catch-all maps non-contract codes to the 5-code set | SATISFIED | `http_exception_handler` uses `_STATUS_REMAP` + `_CODE_MAP` with 500 fallback; `test_wrong_method_returns_400` passes |
| ERR-06      | 11-01       | Remappings applied: 409→400, 413→400, 422→400, 502→503, 500(DB)→503    | SATISFIED | `_STATUS_REMAP` dict contains all mappings; handler status codes verified; parametrized tests confirm |

**All 6 requirements satisfied. No orphaned requirements.**

### Anti-Patterns Found

None. Scan of `app/errors.py`, `app/schema.py`, `app/main.py`, `tests/unit/test_exception_handlers.py`, `tests/unit/test_error_contract.py` returned:
- Zero TODO/FIXME/HACK/PLACEHOLDER comments
- Zero `return null`, empty implementations, or stub handlers
- Zero raw exception text in response bodies (`str(exc)`, `exc.detail`, `"status"`, `"error"`)
- Zero non-contract status codes (409, 413, 422, 502) as direct `status_code=` values

### Human Verification Required

None. All contract properties are verifiable programmatically. The test suite directly exercises:
- Handler-level behavior (parametrized exceptions into TestClient)
- HTTP method remapping (405 -> 400 via live TestClient request)
- OpenAPI schema shape (direct `app.openapi()` inspection)
- Body field enumeration (exact `list(body.keys()) == ["code"]` assertion)

The only behaviors that could warrant human review are the `/docs` Swagger UI rendering — that the schema displays correctly in a browser — but this is a cosmetic concern covered by the programmatic schema assertions.

### Test Results

| Suite                                  | Tests | Result  |
|----------------------------------------|-------|---------|
| `tests/unit/test_exception_handlers.py` | 23    | All passed |
| `tests/unit/test_error_contract.py`    | 8     | All passed |
| **Total**                              | **31**| **All passed** |

### Gaps Summary

No gaps. All 5 observable truths are verified, all 5 artifacts are substantive and wired, all 4 key links are confirmed, all 6 requirements are satisfied, and 31 tests pass with zero anti-patterns.

---

_Verified: 2026-03-02T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
