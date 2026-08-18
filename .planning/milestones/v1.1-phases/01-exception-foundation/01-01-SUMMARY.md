---
phase: 01-exception-foundation
plan: "01"
subsystem: exceptions
tags: [exceptions, error-handling, auth, database]
dependency_graph:
  requires: []
  provides: [typed-exception-hierarchy, uniform-error-shape, auth-error-types, db-error-type]
  affects: [app/exceptions.py, app/errors.py, app/auth.py, app/database.py]
tech_stack:
  added: []
  patterns: [typed-exception-hierarchy, uniform-error-shape, opaque-ownership-error]
key_files:
  created: []
  modified:
    - app/exceptions.py
    - app/errors.py
    - app/auth.py
    - app/database.py
    - tests/integration/test_prompts_endpoints.py
    - tests/llm/test_real_llm.py
decisions:
  - "ChatOwnershipError uses same 'not found' message as InvalidChatError to avoid revealing resource existence"
  - "StarletteHTTPException handler registered before Exception handler to ensure correct priority"
  - "DatabaseNotInitializedError handler returns opaque 'Internal server error' to clients, logs full detail"
metrics:
  duration: ~15 minutes
  completed: 2026-02-25
  tasks_completed: 2
  files_modified: 6
---

# Phase 1 Plan 1: Exception Hierarchy and Uniform Error Shape Summary

JWT auth raises typed subtypes; DB startup raises typed error; all error responses use `{"status": <code>, "error": "<message>"}` with no framework internals exposed.

## What Was Built

### Task 1: Extended exception hierarchy (app/exceptions.py)

Added six new exception classes to the existing hierarchy:

- `AuthError(ServiceError)` — base for authentication failures, maps to 401
- `MissingTokenError(AuthError)` — missing or empty Bearer token
- `InvalidTokenError(AuthError)` — malformed JWT or missing `user_id` claim
- `ExpiredTokenError(AuthError)` — expired token (available for future JWT verification)
- `ChatOwnershipError(ServiceError)` — ownership check failure, maps to 404 with opaque message
- `DatabaseNotInitializedError(ServiceError)` — DB session factory not ready, maps to 500

### Task 2: Uniform error shape and new handlers (app/errors.py, app/auth.py, app/database.py)

**app/errors.py:**
- Changed all existing handler responses from `{"detail": "..."}` to `{"status": <code>, "error": "..."}` shape
- Added `auth_error_handler` (401), `chat_ownership_error_handler` (404), `database_not_initialized_handler` (500)
- Added `http_exception_handler` to intercept and reformat Starlette's default HTTPException responses
- Registered new handlers in `register_exception_handlers()`

**app/auth.py:**
- Removed `HTTPException` import
- Replaced `raise HTTPException(status_code=401, ...)` with `raise MissingTokenError()` and `raise InvalidTokenError()`

**app/database.py:**
- Added `DatabaseNotInitializedError` import
- Replaced `raise Exception("session_factory is not initialized")` with `raise DatabaseNotInitializedError()`

**Tests updated:**
- `tests/integration/test_prompts_endpoints.py`: Updated 3 assertions from `["detail"]` to `["error"]`

## Decisions Made

1. **ChatOwnershipError message**: Uses `"Chat '{chat_id}' not found"` — identical to `InvalidChatError` — so clients cannot distinguish between "chat doesn't exist" and "chat belongs to another user." Security requirement.

2. **StarletteHTTPException override**: Handler registered before the catch-all `Exception` handler so Starlette's 404s (e.g., unknown routes) return `{"status": 404, "error": "Not Found"}` instead of Starlette's default `{"detail": "Not Found"}`.

3. **DatabaseNotInitializedError response**: Returns `{"status": 500, "error": "Internal server error"}` to clients (opaque). Logs full exception detail server-side.

## Test Results

- 46 tests pass (integration + unit)
- 2 pre-existing failures in `tests/unit/test_config.py` (unrelated to this plan — config YAML loading issue present before this work)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed syntax error in tests/llm/test_real_llm.py**
- **Found during:** Task 2 verification (running test suite)
- **Issue:** File contained backslash-escaped quotes (`\"`) making it a Python SyntaxError, blocking pytest collection
- **Fix:** Replaced escaped quotes with standard Python string quoting
- **Files modified:** `tests/llm/test_real_llm.py`
- **Commit:** 3468ed8

## Self-Check: PASSED

Files verified:
- `app/exceptions.py` — FOUND, contains all 6 new exception classes
- `app/errors.py` — FOUND, all handlers use `{status, error}` shape
- `app/auth.py` — FOUND, raises MissingTokenError/InvalidTokenError
- `app/database.py` — FOUND, raises DatabaseNotInitializedError

Commits verified:
- `ad525a9` — feat(01-01): extend exception hierarchy
- `3468ed8` — feat(01-01): standardize error shape and wire new exception handlers
