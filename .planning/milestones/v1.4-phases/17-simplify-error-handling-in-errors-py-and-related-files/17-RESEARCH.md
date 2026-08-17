# Phase 17: Simplify Error Handling in errors.py and Related Files - Research

**Researched:** 2026-03-18
**Domain:** FastAPI exception handling, Python exception hierarchy design
**Confidence:** HIGH

## Summary

The current error handling in `app/api/errors.py` has 12 individual handler functions that are nearly identical -- each maps an exception class to a `(status_code, error_code)` pair and returns a `JSONResponse(status_code=X, content=ErrorResponse(code="Y").model_dump())`. This is textbook boilerplate duplication. Of those 12 handlers, only 4 have any distinguishing behavior: 2 add a `Retry-After` header (QueueFullError, CircuitOpenError), and 4 log before responding (AnalysisError, AuthenticationError, DatabaseNotInitializedError, RequestValidationError).

The simplification strategy is to encode HTTP status code and error code directly on the exception classes in `exceptions.py`, then replace the 12 handler functions with a single data-driven handler. The `_STATUS_REMAP` and `_CODE_MAP` tables, the `http_exception_handler`, and `generic_error_handler` remain as they handle framework-level exceptions (StarletteHTTPException, unhandled Exception) that are not part of the app's exception hierarchy.

**Primary recommendation:** Add `status_code` and `error_code` class attributes to `ServiceError` base class; replace per-exception handler functions with a single `service_error_handler` that reads these attributes, plus optional `headers()` method and `log_level` attribute for the 4 special cases.

## Architecture Patterns

### Current State: One Handler Per Exception (12 functions)

```
app/api/errors.py:
  unsupported_language_handler      -> 400, "invalid_request"
  transient_llm_error_handler       -> 503, "service_unavailable"
  permanent_llm_error_handler       -> 503, "service_unavailable"
  analysis_error_handler            -> 500, "internal_error"         [logs]
  invalid_chat_handler              -> 404, "not_found"
  invalid_cursor_error_handler      -> 400, "invalid_request"
  page_size_limit_handler           -> 400, "invalid_request"
  queue_full_handler                -> 503, "service_unavailable"    [Retry-After header]
  circuit_open_handler              -> 503, "service_unavailable"    [Retry-After header]
  chat_history_limit_handler        -> 400, "invalid_request"
  validation_error_handler          -> 400, "invalid_request"        [logs]
  auth_error_handler                -> 401, "unauthorized"           [logs, WWW-Authenticate header]
  database_not_initialized_handler  -> 500, "internal_error"         [logs]
  http_exception_handler            -> remapped status               [framework exceptions]
  generic_error_handler             -> 500, "internal_error"         [catch-all]
```

### Target State: Data-Driven Single Handler

```python
# app/exceptions.py -- add metadata to base class
class ServiceError(Exception):
    status_code: int = 500
    error_code: str = "internal_error"
    log_level: int | None = None        # None = don't log, logging.WARNING, logging.ERROR

    def extra_headers(self) -> dict[str, str] | None:
        return None

class UnsupportedLanguageError(ServiceError):
    status_code = 400
    error_code = "invalid_request"
    # ... existing __init__ unchanged

class AuthenticationError(ServiceError):
    status_code = 401
    error_code = "unauthorized"
    log_level = logging.WARNING

    def extra_headers(self) -> dict[str, str]:
        return {"WWW-Authenticate": "Bearer"}

class QueueFullError(ServiceError):
    status_code = 503
    error_code = "service_unavailable"

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}
```

```python
# app/api/errors.py -- single handler replaces 12 functions
async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        logger.log(exc.log_level, "%s: %s", type(exc).__name__, exc,
                   exc_info=(exc.log_level >= logging.ERROR))
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(code=exc.error_code).model_dump(),
        headers=exc.extra_headers(),
    )

def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
```

### Key Design Decisions

1. **ServiceError as handler base:** FastAPI dispatches exception handlers by walking the MRO. Registering a handler for `ServiceError` catches all subclasses. This is how Starlette's handler lookup works -- it checks `isinstance` against registered exception types and uses the most specific match.

2. **validation_error_handler stays separate:** `RequestValidationError` is a Starlette/FastAPI exception, not a `ServiceError` subclass. It must keep its own handler.

3. **http_exception_handler stays separate:** `StarletteHTTPException` is a framework exception with status code remapping logic. It stays.

4. **generic_error_handler stays separate:** Catch-all for unhandled `Exception`. It stays.

5. **extra_headers() method:** Only QueueFullError, CircuitOpenError, and AuthenticationError need custom headers. A method returning `dict | None` keeps the base simple without requiring subclass override in the common case.

6. **log_level attribute:** Only 4 of 12 exceptions log. Using `None` as default means no logging for most exceptions. The handler checks `if exc.log_level is not None` and uses `logger.log(level, ...)`.

### Recommended Project Structure (files changed)

```
app/
  exceptions.py          # Add status_code, error_code, log_level, extra_headers()
  api/
    errors.py            # Replace 12 handlers with 1 service_error_handler
tests/
  unit/
    test_exception_handlers.py  # May need minor adjustments (still works if behavior unchanged)
    test_error_contract.py      # No changes needed
```

### Anti-Patterns to Avoid

- **Do NOT move validation_error_handler logic into ServiceError:** RequestValidationError is not under our exception hierarchy. It must stay as a separate handler.
- **Do NOT use class decorators or metaclasses:** Simple class attributes are sufficient. No need for a decorator pattern like `@error(400, "invalid_request")`.
- **Do NOT change the API error contract:** The 5 status codes (400/401/404/500/503) and 5 error codes remain identical. This is purely internal refactoring.
- **Do NOT change exception constructors:** Keep existing `__init__` signatures on all exceptions. Only add class-level attributes and the `extra_headers()` method.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exception-to-HTTP mapping | Per-exception handler functions | Class attributes on exception + single handler | Starlette's handler dispatch already walks MRO for `isinstance` matching |

## Common Pitfalls

### Pitfall 1: FastAPI Exception Handler MRO Dispatch
**What goes wrong:** Registering a handler for `ServiceError` might not catch subclasses if FastAPI uses exact-type matching instead of isinstance.
**Why it happens:** Misunderstanding of Starlette's exception handler lookup.
**How to avoid:** Starlette's `ExceptionMiddleware._lookup_exception_handler` walks `type(exc).__mro__` to find the first registered handler. Registering for `ServiceError` WILL catch all subclasses. This is verified in Starlette source code.
**Warning signs:** Test failures in `test_exception_handlers.py` where specific exception subclasses get caught by `generic_error_handler` instead.
**Confidence:** HIGH -- verified in Starlette source.

### Pitfall 2: Registration Order Matters
**What goes wrong:** If `ServiceError` handler is registered before `StarletteHTTPException` handler, and a StarletteHTTPException is raised, the MRO walk might find `Exception` (generic) before `StarletteHTTPException`.
**How to avoid:** The MRO walk checks the raised exception's MRO, not the registration order. `StarletteHTTPException` is not a subclass of `ServiceError`, so registration order between these two does not matter. But `Exception` catch-all should still be registered last for clarity.
**Confidence:** HIGH

### Pitfall 3: AnalysisError Hierarchy
**What goes wrong:** `AnalysisError` is the parent of `TransientLLMError` and `PermanentLLMError`. Currently, `AnalysisError` maps to 500/internal_error while its children map to 503/service_unavailable. With a single handler on `ServiceError`, the handler reads the class attributes from the actual raised exception class, NOT the parent. So `TransientLLMError.status_code = 503` will be used, not `AnalysisError.status_code = 500`.
**How to avoid:** Set `status_code` and `error_code` on every exception class that can be raised directly, not just leaf classes. `AnalysisError` keeps `status_code = 500` for cases where it's raised directly (the `analysis_error_handler` path).
**Confidence:** HIGH

### Pitfall 4: Losing Logging Behavior
**What goes wrong:** Current handlers log at different levels for different exceptions. If the single handler doesn't replicate this, error visibility is lost.
**How to avoid:** Map the exact current logging behavior to `log_level` attributes:
  - `AnalysisError`: `logging.ERROR` (with `exc_info=True` implied by `logger.error`)
  - `AuthenticationError`: `logging.WARNING`
  - `DatabaseNotInitializedError`: `logging.ERROR` (with `exc_info=True`)
  - `RequestValidationError`: `logging.ERROR` -- stays in its own handler
  - All others: `None` (no logging)
**Confidence:** HIGH

### Pitfall 5: type: ignore Annotation on ErrorResponse
**What goes wrong:** Line 118 of current `errors.py` has `# type: ignore[invalid-argument-type]` on `ErrorResponse(code=_CODE_MAP[status])`. This is because `_CODE_MAP` returns `str` but `ErrorResponse.code` expects `ErrorCode` (Literal type). This stays in the `http_exception_handler` which is not being removed.
**How to avoid:** No action needed -- this handler stays unchanged.
**Confidence:** HIGH

## Code Examples

### Complete Exception Base Class

```python
# app/exceptions.py
import logging

class ServiceError(Exception):
    """Base exception for service layer errors."""
    status_code: int = 500
    error_code: str = "internal_error"
    log_level: int | None = None

    def extra_headers(self) -> dict[str, str] | None:
        return None
```

### Exception Subclass with Custom Headers

```python
class QueueFullError(ServiceError):
    status_code = 503
    error_code = "service_unavailable"

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM queue is full")

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}
```

### Single Service Error Handler

```python
async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        logger.log(exc.log_level, "%s: %s", type(exc).__name__, exc,
                   exc_info=(exc.log_level >= logging.ERROR))
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(code=exc.error_code).model_dump(),
        headers=exc.extra_headers(),
    )
```

### Complete Exception-to-Attribute Mapping

| Exception Class | status_code | error_code | log_level | extra_headers |
|----------------|-------------|------------|-----------|---------------|
| ServiceError (base) | 500 | internal_error | None | None |
| UnsupportedLanguageError | 400 | invalid_request | None | None |
| AnalysisError | 500 | internal_error | ERROR | None |
| TransientLLMError | 503 | service_unavailable | None | None |
| PermanentLLMError | 503 | service_unavailable | None | None |
| InvalidChatError | 404 | not_found | None | None |
| InvalidCursorError | 400 | invalid_request | None | None |
| PageSizeLimitError | 400 | invalid_request | None | None |
| QueueFullError | 503 | service_unavailable | None | Retry-After |
| CircuitOpenError | 503 | service_unavailable | None | Retry-After |
| ChatHistoryLimitError | 400 | invalid_request | None | None |
| AuthenticationError | 401 | unauthorized | WARNING | WWW-Authenticate: Bearer |
| DatabaseNotInitializedError | 500 | internal_error | ERROR | None |

### Simplified register_exception_handlers

```python
def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
```

## Impact Assessment

### Lines of Code Reduction

**Before (errors.py):** ~143 lines, 15 handler functions, 15 registrations
**After (errors.py):** ~50 lines, 4 handler functions, 4 registrations

**Before (exceptions.py):** ~78 lines, no HTTP metadata
**After (exceptions.py):** ~90 lines, HTTP metadata on each class (+12 lines)

**Net reduction:** ~80 lines removed, behavior identical

### Test Impact

The existing test suite in `test_exception_handlers.py` should pass WITHOUT changes because:
1. The test creates a FastAPI app, calls `register_exception_handlers(app)`, and raises specific exceptions
2. The parametrized `CASES` list tests that each exception maps to the correct status code
3. As long as the handler produces the same `(status_code, error_code, headers)` for each exception, all tests pass

The `test_error_contract.py` tests are purely about the API surface (status codes, OpenAPI schema) and are unaffected.

### Files Changed

| File | Change | Risk |
|------|--------|------|
| `app/exceptions.py` | Add class attributes + extra_headers() method | LOW -- additive |
| `app/api/errors.py` | Remove 12 handlers, add 1 generic handler, reduce registrations | MEDIUM -- core change |
| Tests | Should pass unchanged | LOW |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `python -m pytest tests/unit/test_exception_handlers.py tests/unit/test_error_contract.py -x` |
| Full suite command | `python -m pytest tests/unit/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| N/A | All 12 exceptions map to same status/code/headers as before | unit | `python -m pytest tests/unit/test_exception_handlers.py -x` | Yes |
| N/A | Error contract (5 codes, 5 statuses, no 422) preserved | unit | `python -m pytest tests/unit/test_error_contract.py -x` | Yes |
| N/A | Validation errors still return 400 | unit | `python -m pytest tests/unit/test_exception_handlers.py::test_validation_error_handler -x` | Yes |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/test_exception_handlers.py tests/unit/test_error_contract.py -x`
- **Per wave merge:** `python -m pytest tests/unit/ -x`
- **Phase gate:** Full suite green

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. The existing `test_exception_handlers.py` parametrized tests are a complete behavioral regression suite for this refactoring.

## Open Questions

1. **Should `import logging` be added to exceptions.py?**
   - What we know: `log_level` values like `logging.WARNING` and `logging.ERROR` require importing `logging`
   - What's unclear: Whether the project prefers keeping exceptions.py import-free
   - Recommendation: Yes, import `logging` in exceptions.py. It's a stdlib import with zero cost and keeps the metadata self-contained on the exception class.

2. **Should TransientLLMError/PermanentLLMError inherit log_level from AnalysisError?**
   - What we know: Currently `analysis_error_handler` logs at ERROR, but `transient_llm_error_handler` and `permanent_llm_error_handler` do NOT log
   - What's unclear: Whether LLM errors being logged at AnalysisError level is intentional
   - Recommendation: Set `log_level = None` explicitly on TransientLLMError and PermanentLLMError to match current behavior. AnalysisError's `log_level = logging.ERROR` only applies when AnalysisError itself is raised (not its subclasses), BUT with class attribute inheritance the subclasses WOULD inherit. Must explicitly override to `None` on the subclasses to preserve current behavior.

## Sources

### Primary (HIGH confidence)
- Direct code analysis of `app/api/errors.py`, `app/exceptions.py`, `app/api/main.py`
- Direct code analysis of `tests/unit/test_exception_handlers.py`, `tests/unit/test_error_contract.py`
- Starlette ExceptionMiddleware source: handler lookup walks `type(exc).__mro__`

### Secondary (MEDIUM confidence)
- FastAPI exception handling documentation (well-known pattern)

## Metadata

**Confidence breakdown:**
- Architecture: HIGH - straightforward refactoring with clear before/after states
- Pitfalls: HIGH - all pitfalls identified by direct code analysis
- Test impact: HIGH - existing parametrized tests serve as behavioral regression suite

**Research date:** 2026-03-18
**Valid until:** No expiry -- this is internal refactoring, not dependent on external library versions
