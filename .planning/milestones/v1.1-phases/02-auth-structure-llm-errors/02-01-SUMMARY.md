---
phase: 02-auth-structure-llm-errors
plan: "01"
subsystem: auth
tags: [jwt, auth, protocol, dependency-injection, pluggable-verifier]

dependency_graph:
  requires:
    - phase: 01-exception-foundation
      provides: MissingTokenError, InvalidTokenError, ExpiredTokenError exception types
  provides:
    - TokenVerifier protocol in app/auth.py (structural subtyping, no ABC required)
    - UnsafeBase64Verifier class satisfying TokenVerifier protocol (dev stub)
    - get_user_id reads verifier from request.app.state.verifier (not import-time coupling)
    - app.state.verifier wired in lifespan to UnsafeBase64Verifier
    - TransientLLMError and PermanentLLMError exception classes (stubs for 02-02)
    - HTTP handlers for TransientLLMError (503) and PermanentLLMError (502) in errors.py
  affects: [02-02-auth-structure-llm-errors, app/auth.py, app/main.py, app/errors.py, app/exceptions.py]

tech_stack:
  added: []
  patterns:
    - app.state provider pattern for swappable auth verifiers
    - TokenVerifier Protocol via typing.Protocol (structural subtyping)
    - Verifier resolved at request-time from app.state, not at import-time

key_files:
  created: []
  modified:
    - app/auth.py
    - app/main.py
    - app/errors.py
    - app/exceptions.py
    - tests/unit/test_exception_handlers.py
    - tests/conftest.py

key_decisions:
  - "TokenVerifier uses typing.Protocol (structural subtyping) — conforming classes do not need to import or inherit from it"
  - "get_user_id resolves verifier from request.app.state.verifier at request-time — enables zero-code swapping of auth providers in tests and at startup"
  - "TransientLLMError and PermanentLLMError stubbed in 02-01 (with handlers) so test CASES can be written ahead of 02-02 which implements _invoke changes"
  - "Integration test conftest.py client fixture requires app.state.verifier = UnsafeBase64Verifier() since lifespan is bypassed in test setup"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03]

metrics:
  duration: ~4 min
  completed: 2026-02-27
  tasks_completed: 2
  files_modified: 6
---

# Phase 2 Plan 1: TokenVerifier Protocol and Pluggable Auth Summary

**TokenVerifier Protocol with UnsafeBase64Verifier as dev stub; get_user_id resolves verifier from app.state enabling zero-code auth provider swapping**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-02-27T06:43:27Z
- **Completed:** 2026-02-27T06:47:23Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- `TokenVerifier` Protocol established — any class with `verify(token: str) -> str` satisfies it without subclassing
- `UnsafeBase64Verifier` extracts existing decode/exp/user_id logic from `get_user_id` into a swappable class
- `get_user_id` now reads verifier from `request.app.state.verifier` — future auth providers (Auth0, Cognito) slot in by changing one line in lifespan
- `test_verifier_swappable_via_state` proves AUTH-03: a stub verifier swapped via state changes behavior without touching route or dependency code

## Task Commits

Each task was committed atomically:

1. **Task 1: Define TokenVerifier protocol and UnsafeBase64Verifier** - `dea7386` (feat)
2. **Task 2: Wire lifespan, add state_client test, stub LLM errors** - `1ef106e` (feat)
3. **Auto-fix: LLM handlers + integration conftest verifier** - `14490bf` (fix)

## Files Created/Modified
- `app/auth.py` - TokenVerifier Protocol, UnsafeBase64Verifier class, updated get_user_id
- `app/main.py` - added `app.state.verifier = UnsafeBase64Verifier()` in lifespan
- `app/exceptions.py` - TransientLLMError and PermanentLLMError stub classes added
- `app/errors.py` - transient_llm_error_handler (503) and permanent_llm_error_handler (502) added
- `tests/unit/test_exception_handlers.py` - UnsafeBase64Verifier import, dep_client verifier, state_client fixture, test_verifier_swappable_via_state, LLM CASES
- `tests/conftest.py` - app.state.verifier added to client fixture

## Decisions Made
- Used `typing.Protocol` for structural subtyping — conforming classes do not need to import TokenVerifier
- Verifier resolved at request-time from `app.state` (not import-time) to enable test-time swapping
- Stubbed `TransientLLMError`/`PermanentLLMError` and their handlers in this plan so the CASES written to `test_exception_handlers.py` pass immediately without waiting for 02-02

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added TransientLLMError/PermanentLLMError stubs and handlers to make LLM CASES pass**
- **Found during:** Task 2 verification (overall plan verification)
- **Issue:** CASES for `transient_llm` and `permanent_llm` were added to `test_exception_handlers.py` but `TransientLLMError`/`PermanentLLMError` did not exist yet (02-02 was supposed to add them); caused ImportError blocking test collection
- **Fix:** Added stub exception classes to `app/exceptions.py` and HTTP handlers (503/502) to `app/errors.py` ahead of 02-02
- **Files modified:** `app/exceptions.py`, `app/errors.py`
- **Verification:** All 67 tests pass; only 2 pre-existing test_config.py failures remain
- **Committed in:** `14490bf`

**2. [Rule 3 - Blocking] Fixed integration conftest.py client fixture missing app.state.verifier**
- **Found during:** Task 2 verification (overall plan verification)
- **Issue:** `get_user_id` now reads `request.app.state.verifier` but the `client` fixture in `tests/conftest.py` didn't set this attribute, causing `AttributeError` in all integration tests that use authentication
- **Fix:** Added `app.state.verifier = UnsafeBase64Verifier()` to the `client` fixture
- **Files modified:** `tests/conftest.py`
- **Verification:** All integration tests pass
- **Committed in:** `14490bf`

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both auto-fixes required for test suite to be collectable and integration tests to pass. Stubbing LLM errors early means 02-02 only needs to update `_invoke` in services.py — exception classes and handlers are already in place.

## Issues Encountered
None — all deviations handled automatically per Rule 3.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `TokenVerifier` protocol is established — 02-02 and future plans can reference it
- `TransientLLMError` and `PermanentLLMError` classes and handlers are already in place for 02-02 to use
- 02-02 only needs to update `_invoke` in `services.py` and add service-level tests

## Self-Check: PASSED

Files verified:
- `app/auth.py` — FOUND, contains TokenVerifier Protocol and UnsafeBase64Verifier
- `app/main.py` — FOUND, sets app.state.verifier = UnsafeBase64Verifier() in lifespan
- `app/exceptions.py` — FOUND, contains TransientLLMError and PermanentLLMError
- `app/errors.py` — FOUND, handlers for TransientLLMError (503) and PermanentLLMError (502)
- `tests/unit/test_exception_handlers.py` — FOUND, state_client fixture, LLM CASES
- `tests/conftest.py` — FOUND, app.state.verifier in client fixture

Commits verified:
- `dea7386` — feat(02-01): introduce TokenVerifier protocol and UnsafeBase64Verifier
- `1ef106e` — feat(02-01): wire UnsafeBase64Verifier in lifespan, add swappable verifier test, stub LLM errors
- `14490bf` — fix(02-01): add LLM error handlers, fix integration test verifier state

---
*Phase: 02-auth-structure-llm-errors*
*Completed: 2026-02-27*
