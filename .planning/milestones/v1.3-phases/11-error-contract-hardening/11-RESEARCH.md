# Phase 11: Error Contract Hardening - Research

**Researched:** 2026-03-02
**Domain:** FastAPI exception handling, OpenAPI schema customization, HTTP error contract enforcement
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ERR-01 | API returns exactly 5 status codes: 400, 401, 404, 503, 500 | Handler audit + StarletteHTTPException catch-all remapping |
| ERR-02 | Error responses use fixed string codes (invalid_request, unauthorized, not_found, service_unavailable, internal_error) | Replace `str(exc)` and raw text with opaque string literals in all handlers |
| ERR-03 | No raw exception text appears in error response bodies | Audit every handler for `str(exc)`, `exc.detail`, `exc.lang`, `exc.role`, `exc.limit` leaks |
| ERR-04 | ErrorResponse Pydantic model documented in OpenAPI schema | New `ErrorResponse` model + per-route `responses=` param + custom `app.openapi()` to remove stale 422 |
| ERR-05 | StarletteHTTPException catch-all maps non-contract codes to the 5-code set | Remap table in `http_exception_handler` |
| ERR-06 | Remappings applied: 409→400, 413→400, 422→400, 502→503, 500(DB)→503 | Fix `chat_history_limit_handler`, `message_too_large_handler`, `validation_error_handler`, `permanent_llm_error_handler` |
</phase_requirements>

---

## Summary

Phase 11 is primarily a codebase audit-and-fix phase rather than a new-library integration. The exception handling infrastructure in `app/errors.py` is already well-structured — the `register_exception_handlers` function covers every known exception type. The work is threefold: (1) fix the status codes and error bodies of handlers that currently emit non-contract codes (409, 413, 422, 502), (2) purge all raw exception text from response bodies and replace with the five fixed opaque strings, and (3) wire a Pydantic `ErrorResponse` model into the OpenAPI schema so it appears at `/docs`.

The biggest non-obvious challenge is making `ErrorResponse` visible in OpenAPI. FastAPI does not offer a single global toggle; the required approach is a combination of per-route `responses=` parameter declarations **and** a `custom_openapi()` function to strip the hardcoded `HTTPValidationError` 422 entry and optionally inject 400 entries that reference `ErrorResponse`. Both techniques are documented (official docs + verified community patterns) and require no new libraries.

A secondary challenge is the `http_exception_handler` in the current code: it currently passes `exc.status_code` directly through to the response. This must be replaced with a remap table that collapses all non-contract Starlette codes (405, 406, 415, etc.) into the nearest contract code (400 for 4xx client errors, 500 for unmapped 5xx).

**Primary recommendation:** Audit all existing handlers in `app/errors.py` for code and body compliance, fix in-place, add `ErrorResponse` to `app/schema.py`, then patch OpenAPI schema generation in `app/main.py`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.129.0 (installed) | Exception handler registration, route-level `responses=`, `app.openapi()` override | Already in use; all patterns are built-in |
| Starlette | 0.52.1 (installed) | `HTTPException`, `RequestValidationError` base types | FastAPI sits on Starlette; these are the canonical exception types to intercept |
| Pydantic | >=2.12 (installed) | `ErrorResponse` model definition, JSON Schema generation for OpenAPI | Already in use for all request/response models |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fastapi.openapi.utils.get_openapi` | built-in | Base for `custom_openapi()` function | Needed to post-process schema and strip 422 from all routes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-route `responses=` + `custom_openapi()` | Third-party FastAPI plugin | No mature plugin handles this globally; hand-rolling `custom_openapi()` is 15 lines and fully documented |
| Opaque string literals in handlers | Enum class for error codes | Enum is cleaner but adds a new type; requirements use literal strings — keep it simple unless planner decides otherwise |

**Installation:** No new packages required.

---

## Architecture Patterns

### Recommended Project Structure

No structural changes required. All modifications target:

```
app/
├── errors.py        # Fix handler bodies and status codes; add remap table
├── schema.py        # Add ErrorResponse Pydantic model
└── main.py          # Add custom_openapi() to strip 422 / inject ErrorResponse ref
tests/
└── unit/
    └── test_exception_handlers.py  # Update expected status codes and body assertions
```

### Pattern 1: Opaque Error Response Model

**What:** A single Pydantic model that all error handlers return, with a fixed `code` string field chosen from the 5-value set.

**When to use:** All error responses. The model gives OpenAPI schema visibility and enforces the fixed-string contract.

```python
# app/schema.py
from pydantic import BaseModel
from typing import Literal

ErrorCode = Literal[
    "invalid_request",
    "unauthorized",
    "not_found",
    "service_unavailable",
    "internal_error",
]

class ErrorResponse(BaseModel):
    code: ErrorCode
```

Note: The existing error response body shape is `{"status": int, "error": str}`. Phase 11 must decide whether to keep `status` alongside `code` or drop it. ERR-02 specifies `code` as a fixed string — the planner should clarify whether the integer `status` field survives. Based on current tests asserting `body["status"]` and `body["error"]`, it is safest to keep both fields and add `code`. The simplest interpretation of ERR-02 is that **the `error` field becomes one of the 5 fixed strings** (i.e., `error` is renamed to `code`, or `code` is a new field while `error` is dropped). This is a decision for the planner.

### Pattern 2: Status Code Remap Table in StarletteHTTPException Handler

**What:** A dict that maps any non-contract Starlette status code to the nearest contract code.

**When to use:** Inside `http_exception_handler` to absorb 405, 406, 409, 415, 502, etc. that Starlette itself might emit before reaching a custom handler.

```python
# Source: verified against FastAPI docs + Starlette source behavior
_STATUS_REMAP: dict[int, int] = {
    # 4xx non-contract → 400 (client error)
    405: 400,
    406: 400,
    409: 400,
    413: 400,
    415: 400,
    422: 400,
    # 5xx non-contract → 503 (upstream/gateway errors)
    502: 503,
    504: 503,
}

async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = _STATUS_REMAP.get(exc.status_code, exc.status_code)
    # status at this point should be one of 400, 401, 404, 503, 500
    # if somehow it's still not in contract set, default to 500
    if status not in {400, 401, 404, 503, 500}:
        status = 500
    code = _STATUS_TO_CODE[status]
    return JSONResponse(status_code=status, content={"code": code})
```

### Pattern 3: per-handler body cleanup (ERR-02, ERR-03)

Current handlers that leak raw exception text and need fixing:

| Handler | Current body (leaks raw text) | Fixed body |
|---------|-------------------------------|------------|
| `unsupported_language_handler` | `f"Unsupported language: '{exc.lang}'"` | `"invalid_request"` |
| `transient_llm_error_handler` | `str(exc)` | `"service_unavailable"` |
| `permanent_llm_error_handler` | `str(exc)` | `"service_unavailable"` (after 502→503 remap) |
| `invalid_chat_handler` | `str(exc)` | `"not_found"` |
| `invalid_cursor_error_handler` | `str(exc)` | `"invalid_request"` |
| `page_size_limit_handler` | `str(exc)` | `"invalid_request"` |
| `queue_full_handler` | `"LLM queue is full"` | `"service_unavailable"` |
| `circuit_open_handler` | `"LLM circuit breaker is open"` | `"service_unavailable"` |
| `message_too_large_handler` | `f"{exc.role.capitalize()} message exceeds {exc.limit} characters"` | `"invalid_request"` |
| `validation_error_handler` | `"Invalid request"` (fine, but status is 422 not 400) | fix status → 400, body `"invalid_request"` |
| `auth_error_handler` | `"Unauthorized"` (fine) | rename to `"unauthorized"` code |
| `chat_ownership_error_handler` | `str(exc)` | `"not_found"` |
| `http_exception_handler` | `exc.detail or "Error"` (leaks) | use remap table + fixed code string |

Note: `Retry-After` header on `queue_full_handler` and `circuit_open_handler` should be preserved — it is useful operational information and is not an error body field.

### Pattern 4: OpenAPI Schema Customization to Expose ErrorResponse

**What:** Override `app.openapi()` with a `custom_openapi()` function that:
1. Removes the autogenerated `422 HTTPValidationError` from every route's responses
2. Injects a `400` entry referencing `ErrorResponse` for routes with request bodies

Add `responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, ...}` on each router or at `FastAPI()` init level.

**Option A (simplest — recommended): per-route `responses=` + global schema post-processing**

```python
# app/main.py
from fastapi.openapi.utils import get_openapi
from app.schema import ErrorResponse

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Strip the 422 HTTPValidationError from every operation
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.get("responses", {}).pop("422", None)
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi
```

Source: [FastAPI extending-openapi docs](https://fastapi.tiangolo.com/advanced/extending-openapi/) + [Issue #3650](https://github.com/fastapi/fastapi/issues/3650)

**Option B: FastAPI `app = FastAPI(responses={...})` init-level defaults**

FastAPI accepts a `responses` kwarg at app level that sets defaults for all routes. This can pre-populate error codes in the schema without per-route decoration. However, these defaults do **not** suppress the hardcoded 422 — the `custom_openapi()` strip is still needed.

```python
app = FastAPI(
    ...,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
```

Confidence: MEDIUM (observed in community patterns; not explicitly in official docs for app-level; per-route is documented — verify behavior)

### Anti-Patterns to Avoid

- **Passing `exc.detail` through in `http_exception_handler`**: Starlette's 404/405/etc. `detail` field contains human-readable text that can reveal framework internals ("Not Found", "Method Not Allowed", "Unprocessable Entity"). Replace with fixed code strings.
- **Leaking Pydantic field names via `exc.errors()`**: The existing `validation_error_handler` already guards this by ignoring `exc.errors()`. Do not regress.
- **Only fixing handlers, not the OpenAPI schema**: If 422 remains visible at `/docs`, ERR-04 fails. Both handler and schema must be updated.
- **Forgetting the `permanent_llm_error_handler`**: It currently emits 502 with `str(exc)` — two violations (wrong code + raw text). Must be fixed to 503 + `"service_unavailable"`.
- **Forgetting `chat_history_limit_handler`**: Currently emits 409. Must remap to 400 + `"invalid_request"`.
- **Forgetting `message_too_large_handler`**: Currently emits 413. Must remap to 400 + `"invalid_request"`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stripping 422 from OpenAPI schema | Custom middleware or post-send hook | `custom_openapi()` post-processing function | Simpler; no request overhead; idiomatic FastAPI pattern |
| Pydantic error body validation | Manual dict assembly in each handler | `JSONResponse(content=ErrorResponse(code=...).model_dump())` | Ensures schema consistency; prevents typos in code strings |
| Per-exception status mapping | `if/elif` chains in generic handler | `_STATUS_REMAP` dict + `_STATUS_TO_CODE` dict | Readable, testable, and trivially extended |

**Key insight:** This phase is entirely about policy enforcement in existing infrastructure. No new middleware, no new routing, no new libraries.

---

## Common Pitfalls

### Pitfall 1: 405 Method Not Allowed leaks through StarletteHTTPException handler

**What goes wrong:** The current `http_exception_handler` passes `exc.status_code` directly. A request to a defined route with the wrong HTTP method returns 405, which is not in the contract set. Success Criterion 3 explicitly requires this to return 4xx within the 5-code set (i.e., 400).

**Why it happens:** Starlette's router raises `HTTPException(status_code=405)` for method-not-allowed before any custom logic. The existing catch-all handler does not remap.

**How to avoid:** Add `405: 400` (and other non-contract 4xx codes) to `_STATUS_REMAP`.

**Warning signs:** `test_wrong_method_returns_400` test fails with 405.

### Pitfall 2: `permanent_llm_error_handler` already registers before the generic `StarletteHTTPException` catch-all

**What goes wrong:** `PermanentLLMError` is caught by its own handler and emits 502 — the `http_exception_handler` remap table never sees it because it's not an `HTTPException`. The fix must be applied directly in `permanent_llm_error_handler`, not in the StarletteHTTPException catch-all.

**Why it happens:** Application-level exception handlers run before the generic `HTTPException` catch-all; the 502 never reaches `http_exception_handler`.

**How to avoid:** Fix `permanent_llm_error_handler` to return 503 directly.

### Pitfall 3: Test suite asserts 422 and 409 and 413 and 502 — all must be updated

**What goes wrong:** `test_exception_handlers.py` parametrizes CASES with `("history_limit", ..., 409)`, `("msg_too_large", ..., 413)`, `("permanent_llm", ..., 502)`, and `test_validation_error_handler` asserts `body["status"] == 422`. All these tests must be updated to match new contract codes.

**Why it happens:** Tests were written against pre-contract behavior.

**How to avoid:** Update CASES expected statuses and body assertions in the same commit as the handler changes.

### Pitfall 4: OpenAPI schema caching causes stale 422 entries

**What goes wrong:** FastAPI caches the OpenAPI schema in `app.openapi_schema` after first generation. If `custom_openapi()` is not wired before the first `/docs` request, the stale 422-containing schema persists for the lifetime of the process.

**Why it happens:** `app.openapi = custom_openapi` must be assigned **after** all routes are registered but **before** the first request.

**How to avoid:** Assign `app.openapi = custom_openapi` immediately after `app.include_router(...)` calls in `main.py`, not inside lifespan.

### Pitfall 5: Body shape mismatch — `{"status": int, "error": str}` vs `{"code": str}`

**What goes wrong:** Existing tests assert `body["status"]` and `body["error"]`. If `ErrorResponse` introduces a `code` field and drops `status`/`error`, every handler test that checks the body shape will fail.

**Why it happens:** ERR-02 is ambiguous about whether the integer `status` field and `error` field survive alongside `code`, or whether `code` replaces `error`.

**How to avoid:** The planner must resolve this. Recommendation: rename `error` → `code` in the response body, drop the integer `status` field (it duplicates the HTTP status code). This is a clean break. Update all tests accordingly.

---

## Code Examples

Verified patterns from official sources:

### Minimal `ErrorResponse` model and handler

```python
# app/schema.py — Source: Pydantic v2 docs
from pydantic import BaseModel
from typing import Literal

class ErrorResponse(BaseModel):
    code: Literal[
        "invalid_request",
        "unauthorized",
        "not_found",
        "service_unavailable",
        "internal_error",
    ]
```

```python
# app/errors.py — Source: FastAPI handling-errors docs
from app.schema import ErrorResponse

async def invalid_chat_handler(_: Request, exc: InvalidChatError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(code="not_found").model_dump(),
    )
```

### Status code remap table

```python
# app/errors.py
_STATUS_REMAP: dict[int, int] = {
    405: 400, 406: 400, 409: 400, 410: 404,
    413: 400, 415: 400, 422: 400,
    502: 503, 504: 503,
}

_CODE_MAP: dict[int, str] = {
    400: "invalid_request",
    401: "unauthorized",
    404: "not_found",
    503: "service_unavailable",
    500: "internal_error",
}

async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = _STATUS_REMAP.get(exc.status_code, exc.status_code)
    if status not in _CODE_MAP:
        status = 500
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=status,
        content={"code": _CODE_MAP[status]},
        headers=headers,
    )
```

### `custom_openapi()` to strip 422 and expose ErrorResponse

```python
# app/main.py — Source: https://fastapi.tiangolo.com/advanced/extending-openapi/
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.get("responses", {}).pop("422", None)
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi
```

### `FastAPI()` init-level default error responses

```python
# app/main.py
from app.schema import ErrorResponse

app = FastAPI(
    title="SpeakNative API Gateway",
    ...,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-handler status pass-through | Remap table in catch-all | Phase 11 | Collapses non-contract codes |
| `str(exc)` in response body | Fixed string literals from 5-code set | Phase 11 | ERR-02, ERR-03 compliance |
| No `ErrorResponse` model | Pydantic `ErrorResponse` with `Literal` code field | Phase 11 | ERR-04 OpenAPI visibility |
| 422 in `/docs` | 422 stripped via `custom_openapi()` | Phase 11 | ERR-04 compliance |

**Deprecated/outdated:**
- Numeric `"status"` field in error body: redundant once HTTP status code is correct; ERR-02 does not require it; drop.
- `"error"` field name: replace with `"code"` to match ERR-02 fixed-string naming.

---

## Open Questions

1. **Body shape: keep `{"status": int, "error": str}` or migrate to `{"code": str}`?**
   - What we know: ERR-02 says "fixed string codes" as the body content. Existing tests assert `body["status"]` and `body["error"]`.
   - What's unclear: Whether `status` and `error` survive or are replaced by `code`.
   - Recommendation: Replace both with `{"code": str}`. Cleaner, aligns with ERR-02 literal wording. All tests need updating anyway (status codes are changing). One migration is better than two.

2. **Should `410 Gone` remap to `404` or `400`?**
   - What we know: It's not in the success criteria, but `_STATUS_REMAP` should be complete.
   - What's unclear: Project preference.
   - Recommendation: 410 → 404 (semantically "this resource is gone, i.e. not found from caller's perspective").

3. **Should `auth_error_handler` preserve `WWW-Authenticate` header?**
   - What we know: AUTH-07 (Phase 10) requires this header. It must survive the Phase 11 body changes.
   - What's unclear: Nothing — preserve the header, just change the body to `{"code": "unauthorized"}`.
   - Recommendation: Keep `headers={"WWW-Authenticate": "Bearer"}` unchanged.

---

## Sources

### Primary (HIGH confidence)
- [FastAPI Handling Errors docs](https://fastapi.tiangolo.com/tutorial/handling-errors/) - exception handler registration, RequestValidationError override
- [FastAPI Additional Responses docs](https://fastapi.tiangolo.com/advanced/additional-responses/) - `responses=` parameter usage, per-route model declaration
- [FastAPI Extending OpenAPI docs](https://fastapi.tiangolo.com/advanced/extending-openapi/) - `custom_openapi()` pattern, `get_openapi()` usage
- Codebase: `app/errors.py`, `app/exceptions.py`, `app/schema.py`, `app/main.py` — current handler inventory

### Secondary (MEDIUM confidence)
- [FastAPI Issue #3650](https://github.com/fastapi/fastapi/issues/3650) - Confirmed: no built-in global 422 override; `custom_openapi()` post-processing is the recommended workaround
- [FastAPI Discussion #6695](https://github.com/fastapi/fastapi/discussions/6695) - Community patterns for disabling 422 in schema
- WebSearch: 405 behavior via StarletteHTTPException confirmed in multiple community sources

### Tertiary (LOW confidence)
- FastAPI app-level `responses=` parameter at `FastAPI()` init: community-reported to propagate to all routes; not explicitly documented for app-level (per-route is documented). Verify in practice.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all changes are in already-used FastAPI/Pydantic/Starlette APIs
- Architecture: HIGH — handler audit is codebase-specific and fully observable; remap table is a well-known pattern
- Pitfalls: HIGH for pitfalls 1-4 (verified against current test file and handler code); MEDIUM for pitfall 5 (body shape is a design decision, not a technical uncertainty)

**Research date:** 2026-03-02
**Valid until:** 2026-05-01 (FastAPI and Starlette stable; schema customization APIs unchanged across multiple major releases)
