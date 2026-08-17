# Phase 10: JWT Authentication - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the stub `UnsafeBase64Verifier` with real RS256 JWT verification using Firebase Auth and live JWKS key fetching. All 20 pre-written tests in `test_jwt_security.py` must pass (with modifications for removed email_verified check). AUTH-09 (JWKS live key rotation) pulled from v2 into this phase.

</domain>

<decisions>
## Implementation Decisions

### Auth Provider
- Firebase Authentication is the identity provider (project: native-speaker-488021)
- JWKS live key fetch via PyJWKClient (AUTH-09 pulled from v2 into v1.3)
- Trust PyJWKClient default behavior for kid (key ID) matching
- No `email_verified` enforcement — remove from JWTVerifier and update affected tests
- Strictly `sub` claim for user identity — no `user_id` fallback
- Don't restrict by sign-in method — any valid Firebase token accepted
- Move AUTH-09 formally from v2 to v1.3 in REQUIREMENTS.md and ROADMAP.md

### JWKS Resilience
- Crash at startup if JWKS endpoint is unreachable (fail fast)
- On runtime JWKS refresh failure: use cached keys, log the error, retry on next request
- No offline/dev mode escape hatch — internet required

### Config Structure
- JWT config section **required** in config.yaml — app won't start without it
- Fields: `project_id`, `jwks_url`, `leeway_seconds` (default 30), `jwks_cache_ttl_seconds`
- Audience derived from project_id; issuer derived as `https://securetoken.google.com/{project_id}`
- Environment variable overrides following existing pydantic-settings pattern (`JWT_PROJECT_ID`, etc.)
- `project_id` stored as plain string (not SecretStr — it's public info)
- Configurable leeway (default 30s) and JWKS cache TTL

### Dev Mode & Cleanup
- Delete `UnsafeBase64Verifier` and `_decode_jwt_payload` entirely from `app/auth.py`
- No dev mode toggle or fallback — one verifier for all environments
- Integration tests use `_FixedKeyVerifier` from `tests/jwt_helpers.py`
- Log Firebase project ID at startup (follows existing pattern for LLM model, concurrency)
- Keep `TokenVerifier` Protocol; `JWTVerifier` implements it with constructor args for config

### Exception Hierarchy
- Rename `AuthError` to `AuthenticationError` across entire codebase
- Remove subclasses: `MissingTokenError`, `InvalidTokenError`, `ExpiredTokenError`
- `get_user_id` raises `AuthenticationError("Missing Bearer token")` directly
- `JWTVerifier.verify()` raises `AuthenticationError` with specific message strings

### Error Responses
- `WWW-Authenticate: Bearer` header on all 401 responses (AUTH-07, simple format)
- Opaque 401 response body: `{"status": 401, "error": "Unauthorized"}` — no reason details to client
- Log specific auth failure reason at WARNING level server-side

### Claude's Discretion
- JWKS cache TTL default value (based on Firebase key rotation patterns)
- Required claims beyond the standard 5 (exp, iat, aud, iss, sub)
- PyJWKClient configuration details
- Test modifications for removed email_verified enforcement
- Exact startup validation sequence for JWKS warm-up

</decisions>

<specifics>
## Specific Ideas

- Test helper `_FixedKeyVerifier` in `jwt_helpers.py` already shows the verify implementation pattern — use `jwt.decode()` with `algorithms=["RS256"]`, audience, issuer, leeway, required claims
- Tests already import `from app.auth import JWTVerifier` — this class needs to be created
- Firebase JWKS URL: `https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com`
- Firebase project ID: `native-speaker-488021`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TokenVerifier` Protocol (`app/auth.py`): defines `verify(token: str) -> str` interface — JWTVerifier implements this
- `get_user_id()` dependency (`app/auth.py`): extracts Bearer token, calls verifier — needs MissingTokenError -> AuthenticationError change
- `_FixedKeyVerifier` (`tests/jwt_helpers.py`): test verifier with ephemeral RSA keypair — stays as-is for tests
- `make_token()` (`tests/jwt_helpers.py`): token factory for tests — stays as-is
- Exception handler registration (`app/errors.py`): `auth_error_handler` needs WWW-Authenticate header and opaque body

### Established Patterns
- Config: Pydantic `BaseModel` nested in `AppConfig`, loaded from YAML with env overrides (`pydantic-settings`)
- Startup: `lifespan()` in `main.py` creates service objects and attaches to `app.state`
- Error handling: exception type -> handler function -> JSONResponse with status code and error message
- Logging: `logger.info()` for startup info, `logger.error()` for failures

### Integration Points
- `app/main.py:46`: `app.state.verifier = UnsafeBase64Verifier()` -> replace with `JWTVerifier(config)`
- `app/config.py`: `AppConfig` needs new `jwt: JWTConfig` field
- `config/config.yaml`: needs new `jwt:` section with real values
- `app/errors.py:92-93`: `auth_error_handler` needs `WWW-Authenticate` header and opaque body
- `app/exceptions.py:79-98`: `AuthError` -> `AuthenticationError`, remove subclasses
- `tests/conftest.py` and `tests/integration/conftest.py`: may need verifier fixture updates

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope (AUTH-09 was formally pulled in rather than deferred).

</deferred>

---

*Phase: 10-jwt-authentication*
*Context gathered: 2026-03-02*
