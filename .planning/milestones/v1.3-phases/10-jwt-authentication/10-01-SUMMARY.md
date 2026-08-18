---
phase: 10-jwt-authentication
plan: "01"
subsystem: auth
tags: [jwt, pyjwt, fastapi, pydantic, firebase, exception-handling]

# Dependency graph
requires: []
provides:
  - "AuthenticationError exception class (replaces AuthError + 3 subclasses)"
  - "auth_error_handler returning opaque 401 with WWW-Authenticate: Bearer header"
  - "JWTConfig(BaseModel) with project_id, jwks_url, leeway_seconds, jwks_cache_ttl_seconds and derived audience/issuer"
  - "JWTVerifier base class stub in app/auth.py (unblocks test collection for Plan 02)"
  - "jwt section in config/config.yaml with Firebase project_id"
affects: [10-02, 11-error-contract]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single AuthenticationError replaces auth exception hierarchy — opaque 401 with WWW-Authenticate"
    - "model_validator(mode=after) to derive audience/issuer from project_id in JWTConfig"
    - "Required field (no default) in AppConfig causes fail-fast ValidationError at startup"

key-files:
  created: []
  modified:
    - app/exceptions.py
    - app/auth.py
    - app/errors.py
    - app/config.py
    - config/config.yaml
    - tests/unit/test_exception_handlers.py
    - tests/unit/test_config.py

key-decisions:
  - "AuthenticationError is the sole auth exception — no subclasses. All auth failures raise AuthenticationError with descriptive message."
  - "Error handler returns opaque body {status:401, error:Unauthorized} — never exposes internal error text."
  - "jwt: JWTConfig has no default in AppConfig — startup fails fast if jwt section missing from config.yaml."
  - "JWTVerifier base class added as stub to unblock test collection (jwt_helpers.py imports it) ahead of Plan 02 implementation."

patterns-established:
  - "Auth errors: raise AuthenticationError('descriptive message') — handler makes body opaque"
  - "Config required fields: no Field(default=...) means ValidationError at startup if YAML section missing"

requirements-completed: [AUTH-05, AUTH-06, AUTH-07]

# Metrics
duration: 3min
completed: 2026-03-02
---

# Phase 10 Plan 01: JWT Auth Foundation Summary

**AuthenticationError exception hierarchy collapsed to single class, opaque 401 handler with WWW-Authenticate header, and JWTConfig with Firebase project_id and auto-derived audience/issuer**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-02T10:44:57Z
- **Completed:** 2026-03-02T10:47:56Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Renamed `AuthError` to `AuthenticationError` and deleted the 3 subclasses (`MissingTokenError`, `InvalidTokenError`, `ExpiredTokenError`)
- Updated `auth_error_handler` to return opaque `{"status": 401, "error": "Unauthorized"}` with `WWW-Authenticate: Bearer` header
- Added `JWTConfig(BaseModel)` to `app/config.py` with auto-derived `audience` and `issuer` via `model_validator`
- Added `jwt:` section to `config/config.yaml` with Firebase project_id `native-speaker-488021`
- All 75 unit tests pass with 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Rename AuthError to AuthenticationError and update error handler** - `e7f039d` (feat)
2. **Task 2: Add JWTConfig to AppConfig and jwt section to config.yaml** - `c3077d9` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `app/exceptions.py` - AuthError renamed to AuthenticationError; MissingTokenError/InvalidTokenError/ExpiredTokenError deleted
- `app/auth.py` - Updated imports/raises; added JWTVerifier base class stub
- `app/errors.py` - auth_error_handler updated with opaque body, WWW-Authenticate header, and logging
- `app/config.py` - JWTConfig class added; jwt: JWTConfig required field in AppConfig
- `config/config.yaml` - jwt section added with project_id: native-speaker-488021
- `tests/unit/test_exception_handlers.py` - Updated CASES to use AuthenticationError directly
- `tests/unit/test_config.py` - Added jwt section to test YAML fixture

## Decisions Made

- `AuthenticationError` is the sole auth exception type — no subclasses needed since the error handler obscures the message anyway
- Error body is always opaque `Unauthorized` — never exposes internal exception text per CONTEXT.md security requirement
- `jwt: JWTConfig` has no default in `AppConfig` — deliberate fail-fast at startup if config is missing
- Added `JWTVerifier` base class stub to `app/auth.py` because `tests/jwt_helpers.py` subclasses it; needed for test collection in Plan 01

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added JWTVerifier base class stub to app/auth.py**
- **Found during:** Task 1 (rename AuthError and update error handler)
- **Issue:** `tests/jwt_helpers.py` does `from app.auth import JWTVerifier` and subclasses it. Without this, `test_jwt_security.py` would fail to collect, violating the done criteria.
- **Fix:** Added `class JWTVerifier:` base class with `verify()` raising `NotImplementedError`. Plan 02 will replace with full implementation.
- **Files modified:** `app/auth.py`
- **Verification:** `pytest tests/unit/test_jwt_security.py --collect-only` shows 21 collected items with no errors
- **Committed in:** `e7f039d` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed test_config.py missing jwt section in test fixture**
- **Found during:** Task 2 (add JWTConfig to AppConfig)
- **Issue:** `test_main_config_loads_yaml_and_content` used minimal YAML without `jwt:` section. After making `jwt: JWTConfig` required in `AppConfig`, the test raised `ValidationError: jwt Field required`.
- **Fix:** Added `jwt:\n  project_id: test-project` to the test YAML content.
- **Files modified:** `tests/unit/test_config.py`
- **Verification:** All 4 config tests pass; all 75 unit tests pass
- **Committed in:** `c3077d9` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correctness — no scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## Next Phase Readiness

- `AuthenticationError` importable and fully wired; Plan 02 can raise it from `JWTVerifier.verify()`
- `JWTConfig` available in `AppConfig` with correct fields and derivations; Plan 02 can read `app.state.config.jwt`
- `test_jwt_security.py` collects all 21 tests; Plan 02 implementation will make them pass
- No blockers for Plan 02

---
*Phase: 10-jwt-authentication*
*Completed: 2026-03-02*

## Self-Check: PASSED

- app/exceptions.py: FOUND
- app/auth.py: FOUND
- app/errors.py: FOUND
- app/config.py: FOUND
- config/config.yaml: FOUND
- .planning/phases/10-jwt-authentication/10-01-SUMMARY.md: FOUND
- Commit e7f039d: FOUND
- Commit c3077d9: FOUND
