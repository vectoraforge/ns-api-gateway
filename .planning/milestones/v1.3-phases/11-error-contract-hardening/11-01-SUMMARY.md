---
phase: 11-error-contract-hardening
plan: "01"
subsystem: error-handling
tags: [error-contract, api-design, security, pydantic]
dependency_graph:
  requires: []
  provides: [ErrorResponse model, opaque error bodies, status code remapping]
  affects: [app/schema.py, app/errors.py, tests/unit/test_exception_handlers.py]
tech_stack:
  added: []
  patterns: [ErrorCode Literal type, _STATUS_REMAP dict, _CODE_MAP dict, ErrorResponse.model_dump()]
key_files:
  modified:
    - app/schema.py
    - app/errors.py
    - tests/unit/test_exception_handlers.py
decisions:
  - "ErrorResponse uses Pydantic Literal to enforce exactly 5 allowed code strings at model validation time"
  - "_STATUS_REMAP covers all non-contract Starlette status codes (405, 406, 409, 410, 413, 415, 422, 429, 502, 504)"
  - "http_exception_handler falls back to 500/internal_error for any unknown status not in _CODE_MAP"
metrics:
  duration: "2 min"
  completed_date: "2026-03-02"
  tasks_completed: 2
  files_modified: 3
---

# Phase 11 Plan 01: Error Contract Hardening Summary

**One-liner:** Opaque ErrorResponse Pydantic model with 5 Literal codes replaces all raw-text error bodies, with _STATUS_REMAP eliminating non-contract status codes (409, 413, 422, 502).

## What Was Built

Added `ErrorCode` Literal type and `ErrorResponse` Pydantic model to `app/schema.py`, then rewrote every exception handler in `app/errors.py` to emit `{"code": "fixed_string"}` — no `status` integer, no `error` text, no raw exception details. Added `_STATUS_REMAP` and `_CODE_MAP` module-level dicts to normalize Starlette status codes to the 5 contract codes (400, 401, 404, 503, 500). Updated `tests/unit/test_exception_handlers.py` to assert the new body shape and remapped status codes.

## Tasks Completed

| # | Name | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Add ErrorResponse model and fix all exception handlers | 8ba0206 | app/schema.py, app/errors.py |
| 2 | Update test assertions for new body shape and remapped status codes | 20dc168 | tests/unit/test_exception_handlers.py |

## Decisions Made

1. **ErrorResponse Literal enforcement:** Using `Pydantic Literal` type for `ErrorCode` enforces the 5 allowed values at model construction time — any typo raises a `ValidationError` immediately, not a runtime 500.

2. **_STATUS_REMAP covers 10 non-contract codes:** 405, 406, 409, 410, 413, 415, 422, 429, 502, 504 — all map to one of the 4 client-facing codes (400/404/503). The `http_exception_handler` falls back to 500 for any unknown status not in `_CODE_MAP`.

3. **logger calls preserved:** `logger.error(...)` and `logger.warning(...)` remain in `analysis_error_handler`, `validation_error_handler`, `auth_error_handler`, `database_not_initialized_handler`, and `generic_error_handler`. Opaque response bodies do not imply silent failures.

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- `python -m pytest tests/unit/test_exception_handlers.py -x -v` — 23 passed
- `ErrorResponse(code='invalid_request')` — model importable and validates
- `grep 'str(exc)' app/errors.py` — 0 matches
- `grep 'exc.detail' app/errors.py` — 0 matches
- `grep '"status"' app/errors.py` — 0 matches
- `grep '"error"' app/errors.py` — 0 matches

## Self-Check: PASSED

- [x] app/schema.py modified (ErrorCode + ErrorResponse added)
- [x] app/errors.py modified (_STATUS_REMAP, _CODE_MAP, all handlers fixed)
- [x] tests/unit/test_exception_handlers.py modified (23 tests pass)
- [x] Commit 8ba0206 exists (Task 1)
- [x] Commit 20dc168 exists (Task 2)
