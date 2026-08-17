---
phase: 10-jwt-authentication
plan: 02
subsystem: auth
tags: [jwt, pyjwt, rs256, jwks, firebase, authentication]

# Dependency graph
requires:
  - phase: 10-01
    provides: AuthenticationError exception class, JWTConfig in AppConfig, stub JWTVerifier base class
provides:
  - JWTVerifier class with PyJWKClient JWKS-based RS256 signature verification
  - Startup JWKS warm-up for fail-fast behavior
  - app/main.py wired to JWTVerifier from config.jwt
  - Full test infrastructure using ephemeral RSA keypairs (make_test_verifier, make_token)
  - 19 JWT security tests green
affects: [11-error-contract, 12-llm-di, 13-endpoint-merge]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JWTVerifier uses PyJWKClient for JWKS-based key fetching with TTL caching"
    - "Startup warm-up via get_signing_keys() — fail-fast if JWKS endpoint unreachable"
    - "get_user_id is sync def (not async) — FastAPI runs sync dependencies in threadpool"
    - "_FixedKeyVerifier satisfies TokenVerifier Protocol structurally (duck typing, no inheritance)"
    - "Test tokens created with make_token() using ephemeral RSA keypair from jwt_helpers"

key-files:
  created:
    - tests/jwt_helpers.py
    - tests/unit/test_jwt_security.py
  modified:
    - app/auth.py
    - app/main.py
    - tests/conftest.py
    - tests/integration/conftest.py
    - tests/integration/test_cross_user_isolation.py
    - tests/unit/test_exception_handlers.py

key-decisions:
  - "UnsafeBase64Verifier and _decode_jwt_payload deleted — no compatibility shim needed"
  - "_FixedKeyVerifier decoupled from JWTVerifier — standalone class satisfying Protocol structurally"
  - "No email_verified enforcement — extra claims ignored per CONTEXT.md decision"
  - "get_user_id changed from async def to sync def — PyJWKClient uses urllib (blocking I/O)"

patterns-established:
  - "TokenVerifier Protocol: any class with verify(token: str) -> str is a valid verifier"
  - "Test verifiers use fixed RSA keypairs; production uses JWKS-fetched keys"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-09]

# Metrics
duration: 8min
completed: 2026-03-02
---

# Phase 10 Plan 02: JWT Authentication Summary

**RS256 JWTVerifier via PyJWKClient JWKS fetching with startup warm-up, replacing UnsafeBase64Verifier; all 19 JWT security tests pass green**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-02T10:51:02Z
- **Completed:** 2026-03-02T10:58:50Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- JWTVerifier verifies RS256 signatures via PyJWKClient with audience, issuer, expiry, and required claim validation
- JWKS cache warm-up at startup provides fail-fast behavior if Firebase JWKS endpoint is unreachable
- All test infrastructure migrated from UnsafeBase64Verifier (alg:none tokens) to proper RS256-signed tokens via ephemeral RSA keypair
- 19 JWT security tests pass covering algorithm rejection, signature verification, claim validation, malformed tokens, and cross-user isolation

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement JWTVerifier and wire into application** - `a089f32` (feat)
2. **Task 2: Migrate test infrastructure and fix JWT security tests** - `3fb4399` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified
- `app/auth.py` - JWTVerifier with PyJWKClient, TokenVerifier Protocol, sync get_user_id; UnsafeBase64Verifier and _decode_jwt_payload deleted
- `app/main.py` - Wires JWTVerifier from config.jwt with Firebase project ID log
- `tests/jwt_helpers.py` - _FixedKeyVerifier (standalone, no JWTVerifier inheritance), email_verified check removed
- `tests/conftest.py` - Migrated to make_test_verifier() and make_token(); _make_token() deleted
- `tests/integration/conftest.py` - Migrated to make_test_verifier() and auth_token(); _make_token() deleted
- `tests/integration/test_cross_user_isolation.py` - Imports auth_token instead of _make_token
- `tests/unit/test_exception_handlers.py` - Uses make_test_verifier(), make_token(); UnsafeBase64Verifier removed
- `tests/unit/test_jwt_security.py` - Removed test_rejects_unverified_email and test_rejects_missing_email_verified (19 tests remain)

## Decisions Made
- `_FixedKeyVerifier` decoupled from JWTVerifier — the production class now requires JWKS constructor args; test verifier uses a fixed public key via duck typing
- No `email_verified` enforcement — per CONTEXT.md: "No email_verified enforcement" — extra claims are ignored
- `get_user_id` changed from `async def` to `def` — PyJWKClient.get_signing_key_from_jwt() may invoke urllib on cache miss; FastAPI threadpool handles it safely

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required (JWKS URL defaults to Firebase production endpoint in config).

## Next Phase Readiness
- JWTVerifier is production-ready with RS256 JWKS verification
- All auth requirements AUTH-01 through AUTH-04 and AUTH-09 satisfied
- Ready for Phase 11 (error contract) and Phase 12 (LLM DI)

---
*Phase: 10-jwt-authentication*
*Completed: 2026-03-02*
