---
phase: 01-exception-foundation
verified: 2026-02-27T05:33:47Z
status: gaps_found
score: 5/7 must-haves verified
re_verification: true
re_verification_meta:
  previous_status: passed
  previous_score: 7/7
  previous_verified: 2026-02-25T00:30:00Z
  reason: "Re-verified after UAT, 01-03 gap closure, and REQUIREMENTS.md traceability update. Previous verification predated UAT which revealed the 422 gap; 01-03 fixed missing-header 422→401 but REQUIREMENTS.md now records EXCP-01 as partial and EXCP-02 as pending Phase 4."
  gaps_closed:
    - "Missing Authorization header returns 422 instead of 401 (fixed by 01-03)"
  gaps_remaining:
    - "ExpiredTokenError has no production raise site — auth.py does not check the exp claim"
    - "ChatOwnershipError has no production raise site — router raises InvalidChatError instead"
  regressions: []
gaps:
  - truth: "A request with an expired token receives a 401 with a structured body via ExpiredTokenError"
    status: failed
    reason: "ExpiredTokenError is defined in exceptions.py, its handler is registered in errors.py, and it is tested via direct handler invocation — but auth.py never inspects the exp claim in the JWT payload. A real request carrying an expired token reaches get_user_id, decodes successfully (no exp check), and returns 200 if user_id is present. The exception is unreachable in production."
    artifacts:
      - path: "app/auth.py"
        issue: "No exp claim inspection. _decode_jwt_payload returns the full payload dict but get_user_id only checks payload.get('user_id'). The exp field is never read. ExpiredTokenError is imported in exceptions.py but not imported or raised anywhere in auth.py."
    missing:
      - "Read payload.get('exp') in get_user_id; compare against time.time(); raise ExpiredTokenError() when past expiry"
      - "Import ExpiredTokenError in app/auth.py"
  - truth: "A request accessing another user's chat receives a 404 via ChatOwnershipError, not InvalidChatError"
    status: failed
    reason: "ChatOwnershipError is defined, its handler is registered and tested via direct injection — but no route or service raises it in production. The router in prompts.py raises InvalidChatError at lines 74 and 105; services.py raises InvalidChatError at line 162. ChatOwnershipError is completely unreachable from any real request path. REQUIREMENTS.md traceability table explicitly marks EXCP-02 as Pending → Phase 4."
    artifacts:
      - path: "app/routers/prompts.py"
        issue: "Lines 74 and 105 raise InvalidChatError for missing/non-owned chats. ChatOwnershipError is never imported or raised. The distinction between 'chat does not exist' and 'chat exists but belongs to another user' is not enforced."
      - path: "app/services.py"
        issue: "Line 162 raises InvalidChatError. No ownership check that distinguishes own vs. other-user's chat."
    missing:
      - "Ownership check in the service or router: verify chat.user_id == user_id; raise ChatOwnershipError(chat_id) when mismatched"
      - "Import ChatOwnershipError in the router or service layer"
human_verification: []
---

# Phase 1: Exception Foundation Verification Report

**Phase Goal:** Typed exceptions cover all error cases; HTTP handlers return consistent, well-shaped error responses
**Verified:** 2026-02-27T05:33:47Z
**Status:** gaps_found
**Re-verification:** Yes — after 01-03 gap closure and REQUIREMENTS.md traceability update

## Context

The previous VERIFICATION.md (2026-02-25) was produced before the UAT run. The UAT revealed a 422 regression (missing Authorization header returned 422 instead of 401). Plan 01-03 fixed that gap. However, a fresh review of the codebase against the Phase 1 success criteria from ROADMAP.md reveals two truths that were marked VERIFIED prematurely: the `ExpiredTokenError` and `ChatOwnershipError` raise sites do not exist in production code. REQUIREMENTS.md now records EXCP-01 as "partial" and EXCP-02 as "pending Phase 4", which is consistent with this finding.

---

## Goal Achievement

### Observable Truths

Truths are taken directly from the Phase 1 success criteria in ROADMAP.md.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1a | A request with a **missing** token receives a 401 with structured body | VERIFIED | `auth.py` line 19: `str \| None = Header(None)`; line 21: `raise MissingTokenError()`; `test_missing_auth_header_returns_401` passes |
| 1b | A request with an **invalid/malformed** token receives a 401 with structured body | VERIFIED | `auth.py` raises `InvalidTokenError` on decode failure and missing user_id; `test_invalid_bearer_token_returns_401` passes |
| 1c | A request with an **expired** token receives a 401 with structured body | FAILED | `ExpiredTokenError` is defined and its handler tested, but `auth.py` never checks the `exp` claim — a real expired token reaches the route unimpeded |
| 2 | A request accessing another user's chat receives a 404 via `ChatOwnershipError` | FAILED | `ChatOwnershipError` handler is registered and tested in isolation, but no route or service raises it — `prompts.py` raises `InvalidChatError` instead (lines 74, 105) |
| 3 | Database startup failure raises `DatabaseNotInitializedError` (not bare `Exception`) | VERIFIED | `database.py` line 19: `raise DatabaseNotInitializedError()`; no bare `raise Exception` anywhere in `database.py` |
| 4 | A parametrized test for each exception handler passes, asserting HTTP status code and response body shape | VERIFIED | 17 tests pass: 13 parametrized handler cases + 1 validation error + 3 dep_client integration tests; `pytest tests/unit/test_exception_handlers.py`: 17 passed |
| 5 | All error responses use `{"status": <code>, "error": "<message>"}` with no framework internals exposed | VERIFIED | All 11 handlers in `errors.py` return `JSONResponse` with `{"status": ..., "error": ...}`; no `"detail"` key in any handler; `StarletteHTTPException` intercepted and reformatted; two bare `HTTPException` raises in `prompts.py` (lines 69, 81) pass through `http_exception_handler` which reformats them correctly |

**Score:** 5/7 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/exceptions.py` | Complete typed exception hierarchy | VERIFIED | 81 lines; contains `AuthError`, `MissingTokenError`, `InvalidTokenError`, `ExpiredTokenError`, `ChatOwnershipError`, `DatabaseNotInitializedError` plus all pre-existing types |
| `app/errors.py` | Exception handlers returning uniform `{status, error}` shape | VERIFIED | 108 lines; `register_exception_handlers` registers 13 handlers; all use `{"status": ..., "error": ...}`; no `"detail"` key |
| `app/auth.py` | `get_user_id` raises `AuthError` subtypes for all auth failure modes | PARTIAL | 35 lines; raises `MissingTokenError` (missing/malformed header) and `InvalidTokenError` (bad payload) — but never raises `ExpiredTokenError`; no `exp` claim check |
| `app/database.py` | `get_db` raises `DatabaseNotInitializedError` instead of bare `Exception` | VERIFIED | 27 lines; imports and raises `DatabaseNotInitializedError` on `session_factory is None` |
| `tests/unit/test_exception_handlers.py` | Parametrized exception handler tests | VERIFIED | 123 lines; 13 parametrized cases + validation error test + 3 dep_client tests; all 17 pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/auth.py` | `app/exceptions.py` | raises `MissingTokenError` / `InvalidTokenError` | WIRED | Lines 21, 23, 26 raise `MissingTokenError`; lines 30, 33 raise `InvalidTokenError`; imported at line 6 |
| `app/auth.py` | `app/exceptions.py` | raises `ExpiredTokenError` | NOT WIRED | `ExpiredTokenError` is not imported in `auth.py`; no `exp` claim check present; the class exists in `exceptions.py` but has no production raise site |
| `app/database.py` | `app/exceptions.py` | raises `DatabaseNotInitializedError` | WIRED | Line 19 raises `DatabaseNotInitializedError`; imported at line 5 |
| `app/errors.py` | FastAPI exception handlers | `register_exception_handlers` registers all handlers | WIRED | Lines 94-107 register all 13 handlers including `AuthError`, `ChatOwnershipError`, `DatabaseNotInitializedError`, `StarletteHTTPException`, `Exception` catch-all |
| Any route/service | `app/exceptions.py` | raises `ChatOwnershipError` | NOT WIRED | `ChatOwnershipError` is registered and tested in isolation but no route or service imports or raises it; `prompts.py` lines 74 and 105 raise `InvalidChatError` for all missing/non-owned chats |
| `tests/unit/test_exception_handlers.py` | `app/errors.py` + `app/auth.py` | `TestClient` with real `Depends(get_user_id)` | WIRED | `dep_client` fixture wires real dependency; `handler_client` exercises all 13 handlers |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| EXCP-01 | 01-01-PLAN.md, 01-03-PLAN.md | API returns typed 401 responses for missing, invalid, and expired tokens | PARTIAL | Missing-token 401: verified (`auth.py` line 21). Invalid-token 401: verified (`auth.py` lines 30, 33). Expired-token 401: NOT implemented — `auth.py` does not check `exp` claim; `ExpiredTokenError` is unreachable in production. REQUIREMENTS.md traceability: "partial — exp claim check remains in Phase 4" |
| EXCP-02 | 01-01-PLAN.md | API returns typed 404 when a user accesses another user's chat via `ChatOwnershipError` | NOT SATISFIED | `ChatOwnershipError` handler exists and is tested; but no route raises it. Router raises `InvalidChatError` for all chat-not-found cases regardless of ownership. REQUIREMENTS.md traceability: "Pending — Phase 4" |
| EXCP-03 | 01-01-PLAN.md | Database startup failure raises `DatabaseNotInitializedError` instead of bare `Exception` | SATISFIED | `database.py` line 19 raises `DatabaseNotInitializedError`; no bare exception |
| EXCP-04 | 01-02-PLAN.md | Each exception handler is covered by a parametrized test verifying HTTP status and response body shape | SATISFIED | 17 tests pass; 13 parametrized handler cases cover all registered handlers; 3 dep_client tests cover real dependency path |

**Orphaned requirements check:** REQUIREMENTS.md maps EXCP-01 and EXCP-02 to Phase 1 (and Phase 4 for closure). No Phase 1 requirements are absent from the plans.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/routers/prompts.py` | 69 | `raise HTTPException(status_code=400, detail="Limit exceeds maximum page size")` | Warning | Bare `HTTPException` — response shape is still uniform because `http_exception_handler` intercepts it, but it is an untyped raise in production code. Planned for Phase 4 cleanup. |
| `app/routers/prompts.py` | 81 | `raise HTTPException(status_code=400, detail="Invalid cursor") from None` | Warning | Same as above — bare `HTTPException` for invalid cursor. Planned for Phase 3 as CURS-01. |

Neither anti-pattern breaks the uniform response shape (the `http_exception_handler` reformats them), but both represent residual untyped error paths that the Phase 1 goal intended to eliminate.

---

### Human Verification Required

None. All truths are verifiable programmatically through source inspection and the passing test suite.

---

## Gaps Summary

Two truths fail against the Phase 1 success criteria from ROADMAP.md:

**Gap 1 — ExpiredTokenError has no production raise site**

`ExpiredTokenError` is defined, its handler is registered in `errors.py`, and it is exercised in the unit test via direct exception injection. However, `auth.py` never inspects the JWT `exp` claim. `_decode_jwt_payload` returns the decoded payload dict, and `get_user_id` only reads `payload.get("user_id")`. A token with `"exp": 1000000` (long past) would be accepted as valid. The Phase 1 success criterion "expired token receives 401" is not satisfied in production — only in the isolated handler test.

This is acknowledged in REQUIREMENTS.md: EXCP-01 is marked "partial", with the exp claim check deferred to Phase 4.

**Gap 2 — ChatOwnershipError has no production raise site**

`ChatOwnershipError` is defined, its handler is registered, and it appears in the parametrized test. But every route that checks chat membership raises `InvalidChatError` instead:
- `prompts.py` line 74: `raise InvalidChatError(chat_id)` — chat not found after `get_chat(db, chat_id, user_id=user_id)`
- `prompts.py` line 105: `raise InvalidChatError(chat_id)` — chat not found after `delete_chat`
- `services.py` line 162: `raise InvalidChatError(chat_id)` — chat not found in service layer

The Phase 1 success criterion "request accessing another user's chat receives a 404 via ChatOwnershipError" is not satisfied — the exception class exists but ownership distinction is not enforced in production code.

This is acknowledged in REQUIREMENTS.md: EXCP-02 is marked "Pending → Phase 4".

**Root cause of both gaps:** Phase 1 built the exception infrastructure (class hierarchy + handlers + tests) but did not wire the raise sites for `ExpiredTokenError` and `ChatOwnershipError` into production paths. The infrastructure work is complete; the integration work is deferred to Phase 4.

**What Phase 4 must deliver:**
- `auth.py`: read `payload.get("exp")`; raise `ExpiredTokenError()` when expired
- Router/service: check chat ownership explicitly; raise `ChatOwnershipError(chat_id)` on mismatch
- `prompts.py` lines 69 and 81: replace bare `HTTPException` with typed domain exceptions

---

_Verified: 2026-02-27T05:33:47Z_
_Verifier: Claude (gsd-verifier)_
