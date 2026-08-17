# Phase 10: JWT Authentication - Research

**Researched:** 2026-03-02
**Domain:** JWT RS256 verification, PyJWT, Firebase JWKS, FastAPI auth middleware
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Firebase Authentication is the identity provider (project: native-speaker-488021)
- JWKS live key fetch via PyJWKClient (AUTH-09 pulled from v2 into v1.3)
- Trust PyJWKClient default behavior for kid (key ID) matching
- No `email_verified` enforcement — remove from JWTVerifier and update affected tests
- Strictly `sub` claim for user identity — no `user_id` fallback
- Don't restrict by sign-in method — any valid Firebase token accepted
- Move AUTH-09 formally from v2 to v1.3 in REQUIREMENTS.md and ROADMAP.md
- Crash at startup if JWKS endpoint is unreachable (fail fast)
- On runtime JWKS refresh failure: use cached keys, log the error, retry on next request
- No offline/dev mode escape hatch — internet required
- JWT config section **required** in config.yaml — app won't start without it
- Fields: `project_id`, `jwks_url`, `leeway_seconds` (default 30), `jwks_cache_ttl_seconds`
- Audience derived from project_id; issuer derived as `https://securetoken.google.com/{project_id}`
- Environment variable overrides following existing pydantic-settings pattern (`JWT_PROJECT_ID`, etc.)
- `project_id` stored as plain string (not SecretStr — it's public info)
- Configurable leeway (default 30s) and JWKS cache TTL
- Delete `UnsafeBase64Verifier` and `_decode_jwt_payload` entirely from `app/auth.py`
- No dev mode toggle or fallback — one verifier for all environments
- Integration tests use `_FixedKeyVerifier` from `tests/jwt_helpers.py`
- Log Firebase project ID at startup (follows existing pattern for LLM model, concurrency)
- Keep `TokenVerifier` Protocol; `JWTVerifier` implements it with constructor args for config
- Rename `AuthError` to `AuthenticationError` across entire codebase
- Remove subclasses: `MissingTokenError`, `InvalidTokenError`, `ExpiredTokenError`
- `get_user_id` raises `AuthenticationError("Missing Bearer token")` directly
- `JWTVerifier.verify()` raises `AuthenticationError` with specific message strings
- `WWW-Authenticate: Bearer` header on all 401 responses (AUTH-07, simple format)
- Opaque 401 response body: `{"status": 401, "error": "Unauthorized"}` — no reason details to client
- Log specific auth failure reason at WARNING level server-side

### Claude's Discretion

- JWKS cache TTL default value (based on Firebase key rotation patterns)
- Required claims beyond the standard 5 (exp, iat, aud, iss, sub)
- PyJWKClient configuration details
- Test modifications for removed email_verified enforcement
- Exact startup validation sequence for JWKS warm-up

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope (AUTH-09 was formally pulled in rather than deferred).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | JWTVerifier verifies RS256 signatures using a configurable public key PEM | PyJWT 2.11.0 `jwt.decode()` with `algorithms=["RS256"]` and JWKS-fetched signing key; `_FixedKeyVerifier` in jwt_helpers.py shows exact pattern |
| AUTH-02 | JWTVerifier validates audience, issuer, and expiration claims from config | `jwt.decode(audience=..., issuer=..., leeway=...)` enforces aud/iss/exp automatically when not disabled via options |
| AUTH-03 | JWTVerifier rejects tokens with disallowed algorithms (HS256, none) | `algorithms=["RS256"]` hard-coded; PyJWT raises `InvalidAlgorithmError` for any other alg; key from JWKS cannot verify HS256/none |
| AUTH-04 | JWTVerifier extracts user identity from `sub` claim (replacing `user_id`) | `options={"require": ["exp", "iat", "aud", "iss", "sub"]}` ensures sub present; return `payload["sub"]` |
| AUTH-05 | AuthenticationError exception type maps to 401 responses | Rename `AuthError` → `AuthenticationError`; update `auth_error_handler` in `app/errors.py` to register on new name with `WWW-Authenticate` header and opaque body |
| AUTH-06 | JWT config (audience, issuer, leeway, public_key_pem) loaded from config.yaml | New `JWTConfig` Pydantic `BaseModel` nested in `AppConfig`; loaded via existing YAML+env-override pattern in `app/config.py` |
| AUTH-07 | All 401 responses include `WWW-Authenticate: Bearer` header (RFC 6750) | `auth_error_handler` must return `JSONResponse(..., headers={"WWW-Authenticate": "Bearer"})` |
</phase_requirements>

## Summary

Phase 10 replaces the stub `UnsafeBase64Verifier` with a production-grade `JWTVerifier` that fetches signing keys from Firebase's JWKS endpoint and validates RS256-signed tokens. The project already has PyJWT 2.11.0 installed (with the `cryptography` extra), the complete test suite written (`test_jwt_security.py`, 21 tests), and a working test helper (`_FixedKeyVerifier` in `jwt_helpers.py`) that reveals the exact implementation pattern to use.

The primary work falls into four areas: (1) exception rename (`AuthError` → `AuthenticationError`, flatten subclasses), (2) config extension (`JWTConfig` added to `AppConfig`), (3) `JWTVerifier` implementation using `PyJWKClient` for live JWKS and `jwt.decode()` for token validation, and (4) fixing all call sites: `app/main.py`, `app/auth.py`, `app/errors.py`, and both `conftest.py` files. The 21 test file has 2 tests for `email_verified` that must be removed/updated because the user decided not to enforce that claim. After removal there are 19 tests; the CONTEXT.md says "20 tests" but the file actually contains 21 — the planner must reconcile this by counting after email_verified cleanup.

**Primary recommendation:** Add `AuthenticationError` to `app/exceptions.py` first (Wave 0), because it unblocks test collection for all 21 pre-written tests. Then implement config, then `JWTVerifier`, then wire everything together.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyJWT | 2.11.0 (installed) | JWT decode, signature verification, claims validation | De-facto Python JWT library; `python-jose` explicitly excluded from project |
| cryptography | 46.0.5 (installed) | RSA key parsing/serialization (`pyjwt[cryptography]` extra) | Required for RS256 algorithm support in PyJWT |
| pydantic | >=2.12 (installed) | Config model `JWTConfig` with validation | Already used for all other config sections |
| pydantic-settings | >=2.13 (installed) | Env variable overrides (`JWT_PROJECT_ID`, etc.) | Existing `BaseConfig` pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PyJWKClient | part of PyJWT 2.11.0 | Fetches and caches JWKS from Firebase endpoint | Used in `JWTVerifier.__init__` to warm up keys at startup |
| urllib (stdlib) | built-in | PyJWKClient's internal HTTP — synchronous | PyJWKClient.fetch_data() uses urllib.request.urlopen internally |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyJWT | python-jose | python-jose explicitly out-of-scope (abandoned library per REQUIREMENTS.md) |
| PyJWKClient | httpx + manual key parse | PyJWKClient handles kid matching, TTL cache, and refresh logic; no value in hand-rolling |

**Installation:**

No new installation needed. PyJWT 2.11.0 and cryptography 46.0.5 are already installed. Verify `pyjwt[cryptography]` extra is satisfied (it is — `cryptography` is already present):

```bash
uv pip show pyjwt cryptography
```

## Architecture Patterns

### Recommended Project Structure

```
app/
├── auth.py           # TokenVerifier Protocol, JWTVerifier class (UnsafeBase64Verifier DELETED)
├── config.py         # JWTConfig BaseModel added to AppConfig
├── exceptions.py     # AuthenticationError (replaces AuthError + subclasses)
├── errors.py         # auth_error_handler updated: opaque body + WWW-Authenticate header
└── main.py           # lifespan: UnsafeBase64Verifier() → JWTVerifier(config.jwt)

config/
└── config.yaml       # jwt: section added

tests/
├── conftest.py       # UnsafeBase64Verifier → make_test_verifier() from jwt_helpers
├── integration/
│   └── conftest.py   # Same verifier swap
├── jwt_helpers.py    # _FixedKeyVerifier stays; email_verified check removed from verify()
└── unit/
    └── test_jwt_security.py  # 2 email_verified tests removed/updated
```

### Pattern 1: JWTVerifier with PyJWKClient

**What:** `JWTVerifier` holds a `PyJWKClient` instance created at constructor time. The `verify()` method calls `jwks_client.get_signing_key_from_jwt(token)` to do kid-matching, then passes the resolved key to `jwt.decode()`.

**When to use:** All production auth paths.

**Key insight:** `PyJWKClient.get_signing_key_from_jwt()` is synchronous. It reads the token header (without verifying signature) to extract `kid`, looks up the key in its TTL-cached JWKS set, and auto-refreshes if the kid is unknown. This is safe because signature verification still happens in `jwt.decode()` afterward.

**Example (from `_FixedKeyVerifier` pattern + JWKS wiring):**

```python
# Source: PyJWT 2.11.0 installed, jwt_helpers.py _FixedKeyVerifier

from jwt import PyJWKClient
import jwt
from exceptions import AuthenticationError


class JWTVerifier:
    def __init__(self, jwks_url: str, audience: str, issuer: str, leeway: int = 30,
                 cache_ttl_seconds: float = 3600):
        # cache_jwk_set=True, lifespan maps to cache_ttl_seconds
        self._jwks_client = PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=cache_ttl_seconds,
        )
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway
        # Warm up at startup — raises PyJWKClientConnectionError if unreachable
        self._jwks_client.get_signing_keys()

    def verify(self, token: str) -> str:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired") from None
        except jwt.InvalidAudienceError:
            raise AuthenticationError("Invalid audience") from None
        except jwt.InvalidIssuerError:
            raise AuthenticationError("Invalid issuer") from None
        except jwt.DecodeError:
            raise AuthenticationError("Token decode failed") from None
        except jwt.InvalidAlgorithmError:
            raise AuthenticationError("Invalid algorithm") from None
        except jwt.MissingRequiredClaimError as exc:
            raise AuthenticationError(f"Missing claim: {exc}") from None
        except Exception as exc:
            raise AuthenticationError(f"Token verification failed: {exc}") from None

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Missing sub claim")
        return str(sub)
```

**Note on algorithms parameter when passing PyJWK:** When `signing_key` is a `PyJWK` object (returned by `get_signing_key_from_jwt`), PyJWT defaults to the key's algorithm. However, explicitly passing `algorithms=["RS256"]` is the correct defensive pattern — it prevents algorithm confusion attacks and satisfies AUTH-03.

### Pattern 2: JWTConfig in AppConfig

**What:** A new `JWTConfig(BaseModel)` is added alongside `ModelConfig` and `DatabaseConfig`. `AppConfig` gains a `jwt: JWTConfig` field. The YAML loader pattern in `MainConfig` already handles nested models.

**Audience and issuer derivation:**

```python
from pydantic import BaseModel, Field, model_validator

class JWTConfig(BaseModel):
    project_id: str
    jwks_url: str = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
    leeway_seconds: int = Field(default=30, ge=0)
    jwks_cache_ttl_seconds: float = Field(default=3600, gt=0)

    # Derived — not in YAML
    audience: str = ""
    issuer: str = ""

    @model_validator(mode="after")
    def derive_claims(self) -> "JWTConfig":
        if not self.audience:
            self.audience = self.project_id
        if not self.issuer:
            self.issuer = f"https://securetoken.google.com/{self.project_id}"
        return self
```

**config/config.yaml addition:**

```yaml
jwt:
  project_id: ns-api-gateway-488021
  jwks_cache_ttl_seconds: 3600
```

**Environment overrides** (pydantic-settings with `env_nested_delimiter="_"`):
- `JWT_PROJECT_ID`
- `JWT_JWKS_URL`
- `JWT_LEEWAY_SECONDS`
- `JWT_JWKS_CACHE_TTL_SECONDS`

### Pattern 3: Exception Rename — AuthError → AuthenticationError

**What:** `AuthError` renamed to `AuthenticationError`. Three subclasses (`MissingTokenError`, `InvalidTokenError`, `ExpiredTokenError`) deleted. All call sites updated to raise `AuthenticationError(message)` directly.

**Affected files:**
- `app/exceptions.py`: rename class, delete 3 subclasses
- `app/auth.py`: `get_user_id` raises `AuthenticationError("Missing Bearer token")`
- `app/errors.py`: handler registered on `AuthenticationError` instead of `AuthError`; body changed to opaque; `WWW-Authenticate` header added
- `tests/conftest.py`: remove `_make_token` and `UnsafeBase64Verifier` references
- `tests/integration/conftest.py`: same
- `tests/jwt_helpers.py`: remove `email_verified` check from `_FixedKeyVerifier.verify()`

### Pattern 4: Startup JWKS Warm-Up

**What:** In `lifespan()` in `main.py`, replace `UnsafeBase64Verifier()` with `JWTVerifier(...)` constructed from `config.jwt`. `JWTVerifier.__init__` calls `self._jwks_client.get_signing_keys()` which calls `fetch_data()` (synchronous urllib) — this is fine in a sync lifespan context.

**Fail-fast behavior:** `PyJWKClientConnectionError` raised if the endpoint is unreachable. Do not catch it — let it propagate, crashing startup as intended.

```python
# app/main.py lifespan
from auth import JWTVerifier

app.state.verifier = JWTVerifier(
    jwks_url=config.jwt.jwks_url,
    audience=config.jwt.audience,
    issuer=config.jwt.issuer,
    leeway=config.jwt.leeway_seconds,
    cache_ttl_seconds=config.jwt.jwks_cache_ttl_seconds,
)
logger.info(f"Firebase project ID: {config.jwt.project_id}")
```

### Pattern 5: auth_error_handler Update

```python
async def auth_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    logger.warning("Authentication failure: %s", exc)
    return JSONResponse(
        status_code=401,
        content={"status": 401, "error": "Unauthorized"},
        headers={"WWW-Authenticate": "Bearer"},
    )
```

Handler registered on `AuthenticationError`. The `AuthError` registration must be updated. If `AuthError` is removed entirely (it can be, since `AuthenticationError` takes its place as the sole auth exception), only one registration is needed.

### Pattern 6: conftest.py Swap

Both `tests/conftest.py` and `tests/integration/conftest.py` use `UnsafeBase64Verifier()` and a `_make_token()` that creates Base64-only tokens with `user_id`. These must be replaced with `make_test_verifier()` from `jwt_helpers.py` and `make_token()` for the auth header fixture.

```python
# tests/conftest.py - after patch
from tests.jwt_helpers import make_test_verifier, make_token

@pytest.fixture
def auth_header():
    token = make_token("test-user")
    return {"Authorization": f"Bearer {token}"}

# In client fixture:
app.state.verifier = make_test_verifier()
```

### Anti-Patterns to Avoid

- **Algorithm confusion:** Never derive `algorithms=` from the token's own header. Always hard-code `["RS256"]`. PyJWT documentation explicitly warns about this (RFC 8725 §2.1).
- **Catching all exceptions silently:** The bare `except Exception` in `verify()` should still re-raise as `AuthenticationError`, not swallow. The pattern in `_FixedKeyVerifier` is correct.
- **Blocking the event loop with synchronous JWKS fetch at verify time:** `PyJWKClient.fetch_data()` uses synchronous urllib. This is acceptable at startup warm-up. At runtime, the TTL cache means fetch only happens if cache expires — acceptable for an infrequent background re-fetch, but if high concurrency is a concern, move the fetch to `asyncio.to_thread`. For this phase, synchronous is fine (cache hit is the fast path).
- **Storing `PyJWKClient` as a module-level singleton:** It belongs on `app.state` via `JWTVerifier`, not as a global.
- **Leaving email_verified checks in `_FixedKeyVerifier`:** The CONTEXT.md decision removes email_verified enforcement. The `_FixedKeyVerifier.verify()` currently checks `email_verified` at line 96. This check must be removed, and the 2 email_verified tests in `test_jwt_security.py` must also be removed/updated.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWKS fetch and kid matching | Custom HTTP + JWK parsing | `PyJWKClient` | Handles TTL caching, auto-refresh on kid miss, SSL, timeout, JWK Set parsing |
| Algorithm restriction | String comparison on token header | `algorithms=["RS256"]` parameter | PyJWT enforces at decode time; header field is untrusted attacker input |
| RS256 key parsing | Manual PEM/DER parsing | `jwt.decode()` with PyJWK | cryptography library handles padding, encoding, key type validation |
| Required claim validation | Manual `payload.get()` checks | `options={"require": ["exp","iat","aud","iss","sub"]}` | PyJWT raises `MissingRequiredClaimError` with specifics |
| Leeway for clock skew | `time.time() - exp < leeway` | `leeway=N` parameter to `jwt.decode()` | Applied symmetrically to `exp` and `nbf` |

**Key insight:** The entire `UnsafeBase64Verifier` + `_decode_jwt_payload` is replaced by ~30 lines wrapping PyJWT. Every piece of custom logic in the old verifier becomes a library parameter.

## Common Pitfalls

### Pitfall 1: Test Collection Failure Blocks All 21 Tests

**What goes wrong:** `test_jwt_security.py` imports `AuthenticationError` from `app.exceptions` at module level. Until `AuthenticationError` exists, the entire test file fails to collect with `ImportError`. This is the current state (verified: `pytest` collection fails with ImportError).

**Why it happens:** `app.exceptions` currently only has `AuthError`; `AuthenticationError` doesn't exist yet.

**How to avoid:** The very first task of Phase 10 must be: add `AuthenticationError` to `app/exceptions.py`. This unblocks the 21 pre-written tests. Do this before any other implementation.

**Warning signs:** `ImportError: cannot import name 'AuthenticationError'` in pytest collection output.

### Pitfall 2: email_verified Mismatch Between jwt_helpers.py and test_jwt_security.py

**What goes wrong:** `_FixedKeyVerifier.verify()` in `jwt_helpers.py` currently enforces `email_verified` (line 96). The CONTEXT.md decision removes this check. But `test_jwt_security.py` has `test_rejects_unverified_email` and `test_rejects_missing_email_verified` — two tests that expect `AuthenticationError` when `email_verified` is false/absent. After removing the check, these tests will fail.

**How to avoid:** Remove the `email_verified` check from `_FixedKeyVerifier.verify()`. Remove (or update) the 2 email_verified tests. After removal: 21 - 2 = 19 tests remain. The CONTEXT.md mentions "20 tests" — investigate whether the count refers to a pre-existing count, or if there's an expectation to add a replacement test.

**Recommendation:** Remove both email_verified tests. The 19 remaining tests fully cover the AUTH-01 through AUTH-07 security surface.

### Pitfall 3: PyJWKClient is Synchronous — asyncio Blocking

**What goes wrong:** `PyJWKClient.fetch_data()` uses `urllib.request.urlopen` — a blocking synchronous call. If called in an async context (inside a route handler or async dependency), it blocks the event loop.

**Why it happens:** PyJWT 2.11.0 does not provide an async JWKS client.

**How to avoid:** Call `get_signing_keys()` (the warm-up) only from the `lifespan()` context manager (which runs synchronously before yield). At runtime, `JWTVerifier.verify()` is called from `get_user_id()` — a FastAPI dependency that is sync (not `async def`). Sync dependencies run in a thread pool by FastAPI, so blocking is acceptable. Confirm `get_user_id` remains `def` (not `async def`) — it currently is `async def` in the codebase. **This is a key issue: `get_user_id` is currently `async def`. If it stays async, `verify()` calling `fetch_data()` on a cache miss blocks the event loop.** The safe options are:
  - Change `get_user_id` to sync `def` (FastAPI runs sync deps in threadpool) — simplest fix
  - Or wrap the blocking call in `asyncio.to_thread()` inside verify

**Warning signs:** Any slow 401 response under concurrent load, or uvicorn warnings about event loop blocked.

### Pitfall 4: `algorithms=["RS256"]` Must Be Explicit When Passing PyJWK

**What goes wrong:** When `signing_key` is a `PyJWK` object, PyJWT may default to the key's advertised algorithm from the JWKS JSON. An attacker who controls their own JWKS (if using a different jwks_url) could inject a key with a different alg.

**How to avoid:** Always pass `algorithms=["RS256"]` explicitly, even when the key is a `PyJWK` instance.

### Pitfall 5: AuthError References Across the Codebase

**What goes wrong:** `AuthError` is imported and registered in `app/errors.py`, imported in `app/auth.py` (via subclass imports), and potentially in tests. Missing a reference causes `NameError` at runtime or import errors in tests.

**How to avoid:** Use grep to find all `AuthError` occurrences before editing. The complete list: `app/exceptions.py`, `app/auth.py`, `app/errors.py`, `tests/conftest.py`, `tests/integration/conftest.py`. Check with:

```bash
grep -r "AuthError\|MissingTokenError\|InvalidTokenError\|ExpiredTokenError" app/ tests/
```

### Pitfall 6: conftest.py Token Factory Still Uses user_id Claim

**What goes wrong:** `tests/conftest.py` and `tests/integration/conftest.py` both have a `_make_token()` helper that creates a Base64 payload with `{"user_id": user_id}`. This was valid for `UnsafeBase64Verifier`. After swapping the verifier, these tokens will fail because `_FixedKeyVerifier` expects a real RS256 JWT with `sub` claim.

**How to avoid:** Replace `_make_token()` and `UnsafeBase64Verifier` in both conftest files with `make_token()` and `make_test_verifier()` from `tests/jwt_helpers.py`.

## Code Examples

Verified patterns from official PyJWT 2.11.0 (inspected source directly):

### PyJWKClient Constructor

```python
# Source: PyJWT 2.11.0 source (verified via python -c "import inspect, jwt; ...")
from jwt import PyJWKClient

client = PyJWKClient(
    uri="https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com",
    cache_jwk_set=True,        # Enable TTL caching
    lifespan=3600,             # Seconds before cache expires (default: 300)
    timeout=30,                # HTTP request timeout
)

# Startup warm-up — raises PyJWKClientConnectionError on failure
client.get_signing_keys()

# Runtime — gets key by kid from token header; auto-refresh on miss
signing_key = client.get_signing_key_from_jwt(token_str)
```

### jwt.decode() with JWKS-resolved key

```python
# Source: PyJWT 2.11.0 jwt.decode() signature (verified)
import jwt

payload = jwt.decode(
    token,
    signing_key,              # PyJWK object from get_signing_key_from_jwt
    algorithms=["RS256"],     # MUST be explicit even with PyJWK
    audience="ns-api-gateway-488021",
    issuer="https://securetoken.google.com/native-speaker-488021",
    leeway=30,                # Seconds of leeway for exp/nbf
    options={"require": ["exp", "iat", "aud", "iss", "sub"]},
)
sub = payload["sub"]
```

### Exception Types Available in PyJWT 2.11.0

```python
# Verified: python -c "import jwt; print(dir(jwt))"
jwt.ExpiredSignatureError        # exp has passed (respects leeway)
jwt.InvalidAudienceError         # aud mismatch
jwt.InvalidIssuerError           # iss mismatch
jwt.DecodeError                  # malformed token, bad signature, wrong key
jwt.InvalidAlgorithmError        # algorithm not in allowed list
jwt.MissingRequiredClaimError    # claim in options.require is absent
jwt.PyJWKClientConnectionError   # JWKS fetch failure (network)
jwt.PyJWKClientError             # JWKS parse/match failure
```

### JWTConfig Pydantic Model

```python
# Pattern: follows DatabaseConfig / ResilienceConfig in app/config.py
from pydantic import BaseModel, Field, model_validator

class JWTConfig(BaseModel):
    project_id: str
    jwks_url: str = Field(
        default="https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
    )
    leeway_seconds: int = Field(default=30, ge=0)
    jwks_cache_ttl_seconds: float = Field(default=3600.0, gt=0)

    audience: str = ""
    issuer: str = ""

    @model_validator(mode="after")
    def derive_audience_and_issuer(self) -> "JWTConfig":
        if not self.audience:
            self.audience = self.project_id
        if not self.issuer:
            self.issuer = f"https://securetoken.google.com/{self.project_id}"
        return self
```

### auth_error_handler with RFC 6750 header

```python
# Source: app/errors.py pattern, RFC 6750 §3
async def auth_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    logger.warning("Authentication failure: %s", exc)
    return JSONResponse(
        status_code=401,
        content={"status": 401, "error": "Unauthorized"},
        headers={"WWW-Authenticate": "Bearer"},
    )
```

### Firebase JWKS URL and Token Claims

Firebase Auth tokens (RS256):
- **JWKS URL:** `https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com`
- **Issuer:** `https://securetoken.google.com/{project_id}`
- **Audience:** `{project_id}` (the Firebase project ID)
- **Standard claims:** `sub` (Firebase UID), `exp`, `iat`, `aud`, `iss`
- **Firebase-specific claims:** `firebase.sign_in_provider`, `email`, `email_verified`, `name`, `picture` — all optional, none required by this phase

### JWKS cache TTL recommendation

Firebase rotates keys approximately every 6 hours, but each key has a 24-hour validity window. A TTL of 3600 seconds (1 hour) is a safe default: it reduces JWKS fetch frequency while not extending far past a potential key rotation.

Source: Firebase documentation (MEDIUM confidence — verified via WebSearch cross-referencing with the CONTEXT.md decision to use a configurable TTL).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `UnsafeBase64Verifier` (no sig check) | `JWTVerifier` with RS256 + JWKS | Phase 10 | Real security |
| `AuthError` + 3 subclasses | `AuthenticationError` flat | Phase 10 | Simpler exception hierarchy |
| Opaque 401 reveals reason | Opaque body `{"status":401,"error":"Unauthorized"}` | Phase 10 | AUTH-07 compliance |
| `user_id` claim | `sub` claim (standard JWT) | Phase 10 | Standards compliance |
| `MissingTokenError` / `InvalidTokenError` | `AuthenticationError(message)` | Phase 10 | Flatter hierarchy |

**Deprecated/outdated:**
- `UnsafeBase64Verifier`: delete entirely
- `_decode_jwt_payload`: delete entirely
- `MissingTokenError`, `InvalidTokenError`, `ExpiredTokenError`: delete all three subclasses
- `_make_token()` helpers in both `tests/conftest.py` and `tests/integration/conftest.py`: replace with `make_token()` from jwt_helpers

## Open Questions

1. **`get_user_id` is currently `async def` — must decide sync vs async**
   - What we know: `JWTVerifier.verify()` calls `PyJWKClient.get_signing_key_from_jwt()` which may invoke `fetch_data()` (blocking urllib) on cache miss
   - What's unclear: The CONTEXT.md does not specify whether to change `get_user_id` to sync `def`
   - Recommendation: Change `get_user_id` to sync `def`. FastAPI automatically wraps sync dependencies in a thread pool. This avoids event loop blocking with zero code complexity cost. The existing `get_user_id` body has no awaits, so the change is trivial.

2. **Test count discrepancy: CONTEXT.md says "20 tests", file has 21**
   - What we know: `test_jwt_security.py` has 21 `def test_` functions. CONTEXT.md says "All 20 tests in `test_jwt_security.py` pass". The decision also says to remove `email_verified` enforcement.
   - What's unclear: The 21st test may have been added after the CONTEXT.md was written, or the count was slightly off.
   - Recommendation: After removing the 2 email_verified tests (`test_rejects_unverified_email`, `test_rejects_missing_email_verified`), 19 tests remain. Run them all to green. The planner can note the actual count as 19 post-cleanup.

3. **`AppConfig.jwt` field required vs optional**
   - What we know: CONTEXT.md says "JWT config section required in config.yaml — app won't start without it"
   - What's unclear: Whether `jwt: JWTConfig` should have no default (required) or have a default that is never valid
   - Recommendation: Declare `jwt: JWTConfig` with no default in `AppConfig`. Pydantic will raise `ValidationError` at startup if the YAML doesn't include the `jwt:` section, achieving the fail-fast behavior.

## Sources

### Primary (HIGH confidence)

- PyJWT 2.11.0 (installed) — source inspected directly via `inspect.getsource()`:
  - `PyJWKClient.__init__`, `fetch_data`, `get_jwk_set`, `get_signing_keys`, `get_signing_key`, `get_signing_key_from_jwt`
  - `jwt.decode()` signature with all parameters
  - All exception class names (verified via `dir(jwt)`)
- `tests/jwt_helpers.py` — `_FixedKeyVerifier.verify()` is the reference implementation pattern
- `tests/unit/test_jwt_security.py` — 21 tests (counted via `grep -c`), collection failure confirmed
- `app/exceptions.py` — current `AuthError` hierarchy, all subclasses
- `app/auth.py` — current `UnsafeBase64Verifier`, `get_user_id`, `TokenVerifier` Protocol
- `app/config.py` — exact Pydantic/pydantic-settings patterns for nested config
- `app/errors.py` — current `auth_error_handler` (lines 92-93)
- `app/main.py` — `lifespan()`, `app.state.verifier` wiring (line 46)
- `tests/conftest.py` — `_make_token`, `UnsafeBase64Verifier` usage (lines 9, 54-57, 78)
- `tests/integration/conftest.py` — same patterns (lines 12, 39-42, 60)
- `pyproject.toml` — PyJWT 2.11.0 confirmed installed, cryptography 46.0.5 confirmed

### Secondary (MEDIUM confidence)

- Firebase JWKS URL `https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com` — cross-referenced with CONTEXT.md (explicitly stated) and Firebase documentation patterns
- Firebase key rotation frequency (~6h rotation, 24h validity) — from CONTEXT.md specifics + Firebase auth documentation patterns; supports 3600s TTL recommendation

### Tertiary (LOW confidence)

- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyJWT 2.11.0 installed and source-inspected; no uncertainty
- Architecture: HIGH — Exact patterns from `_FixedKeyVerifier` reference implementation, verified API signatures
- Pitfalls: HIGH — Collection failure verified live with pytest; async issue identified from source inspection; remaining pitfalls from direct code reading

**Research date:** 2026-03-02
**Valid until:** 2026-04-01 (PyJWT stable; Firebase JWKS URL stable)
