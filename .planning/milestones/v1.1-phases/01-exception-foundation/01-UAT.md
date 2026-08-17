---
status: diagnosed
phase: 01-exception-foundation
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md]
started: 2026-02-25T00:30:00Z
updated: 2026-02-25T00:35:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Missing auth token → 401 with uniform error shape
expected: A request to a protected endpoint with no Authorization header returns HTTP 401 with body {"status": 401, "error": "..."} — key is "error" not "detail".
result: issue
reported: "Missing Authorization header returns 422 instead of 401. FastAPI validates Header(...) as a required parameter and raises RequestValidationError before get_user_id() runs. Body shape is uniform {status: 422, error: 'Invalid request'} but status code is wrong."
severity: major

### 2. Invalid/malformed JWT → 401 with uniform error shape
expected: A request with a malformed Bearer token returns HTTP 401 with body {"status": 401, "error": "..."}.
result: pass

### 3. Cross-user chat access → 404 with non-revealing message
expected: Accessing a chat that belongs to another user returns HTTP 404 with a "not found" style message indistinguishable from a chat that doesn't exist. No 403.
result: pass

### 4. Unknown API route → 404 with uniform error shape
expected: A request to a route that doesn't exist returns HTTP 404 with body {"status": 404, "error": "Not Found"} — not Starlette's default {"detail": "Not Found"}.
result: pass

### 5. All error responses use uniform shape
expected: Any error response (401, 404, 422, 500) has shape {"status": <code>, "error": "<message>"}. No {"detail": ...} responses.
result: pass

## Summary

total: 5
passed: 4
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "A request with no Authorization header returns HTTP 401"
  status: failed
  reason: "Missing Authorization header triggers FastAPI's RequestValidationError (422) before get_user_id() runs. authorization: str = Header(...) makes it a required header — FastAPI validates this before dependencies execute. Body shape is correct ({status, error}) but status code is 422 instead of 401."
  severity: major
  test: 1
  root_cause: "In app/auth.py:19, Header(...) marks the Authorization header as required at the FastAPI level. When absent, FastAPI raises RequestValidationError (422) before the dependency function body runs — MissingTokenError (401) is never reached. The validation_error_handler maps all validation errors uniformly to 422 with no auth-awareness."
  artifacts:
    - path: "app/auth.py"
      issue: "Line 19: `Header(...)` makes FastAPI enforce the header before get_user_id executes. Fix: change to `Header(None)` with `str | None` annotation so the dependency always runs and raises MissingTokenError(401) when the header is absent."
    - path: "app/errors.py"
      issue: "validation_error_handler has no path to produce 401 — it maps all RequestValidationError to 422. This is correct for body/query errors; the fix must prevent the 422 from being raised by making the header optional."
  missing:
    - "Change `authorization: str = Header(...)` to `authorization: str | None = Header(None)` in app/auth.py:19"
    - "Add None check at start of get_user_id body: if not authorization: raise MissingTokenError()"
  debug_session: ""