# Phase 30: E2E and Security Test Coverage - Research

**Researched:** 2026-03-24
**Domain:** Test coverage gap analysis (pytest + FastAPI)
**Confidence:** HIGH

## Summary

The phase objective is to ensure comprehensive test coverage across all API endpoints and security concerns. After auditing all 6 routers, 5 services, 4 database modules, and the entire existing test suite, I identified significant coverage gaps.

The existing test suite has **103 passing unit tests** and **18 e2e tests**, but two test modules (`test_models.py` and `test_services.py`) have **broken imports** from a prior refactor -- they import `Issue` from `nativespeaker.api.schema` but it now lives in `nativespeaker.api.models.content`. Additionally, there is **zero e2e coverage** for subscriptions, users, and webhooks endpoints, and several security scenarios lack unit-level verification.

**Primary recommendation:** Fix the broken imports first (Wave 0), then systematically add missing e2e tests for subscriptions/users/webhooks, expand security unit tests for auth edge cases and subscription-specific security, and add unit tests for currently untested code paths.

## Project Constraints (from CLAUDE.md)

- Use opening delimiter alignment style for multiline constructs
- Don't use string-based module references in Python tests
- Don't commit .planning dir
- Python 3.12+ features (project uses 3.14)
- pytest with pytest-asyncio in auto mode
- Tests use `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"`
- E2E tests use `pytest.mark.e2e` marker and `loop_scope="module"` on classes
- Unit tests run by default (`-m 'not e2e'` in addopts)

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=9.0 | Test framework | Project standard |
| pytest-asyncio | >=1.3 | Async test support | Project standard |
| pytest-cov | >=7.0 | Coverage reporting | Project standard |
| pytest-dotenv | >=0.5 | Env loading | Project standard |
| httpx | >=0.28 | Async HTTP client for e2e | Project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock | stdlib | Mocking for unit tests | Already used throughout |
| cryptography | (transitive via PyJWT) | RSA keypair for JWT tests | Already used in unit/conftest.py |

No new dependencies needed -- all required tooling is already in the project.

## Architecture Patterns

### Existing Test Structure
```
tests/
├── conftest.py              # Minimal shared root
├── e2e/
│   ├── conftest.py          # Real Firebase auth, real DB, transaction rollback
│   ├── test_chat_queries.py # GET/DELETE on pre-seeded chats
│   ├── test_chats.py        # POST /chats, POST /chats/{id} (via LLM)
│   ├── test_examples.py     # GET /examples
│   ├── test_flows.py        # Full chat lifecycle
│   ├── test_health.py       # GET /health/ready
│   ├── test_isolation.py    # Cross-user data isolation
│   └── test_root.py         # GET /
└── unit/
    ├── conftest.py          # Mock fixtures, JWT test infra, TestClient factory
    ├── test_config.py       # Config loading
    ├── test_error_contract.py # Error response format
    ├── test_exception_handlers.py # All exception types -> HTTP
    ├── test_jwt_security.py # JWT verification security
    ├── test_logging.py      # Structlog middleware
    ├── test_models.py       # BROKEN IMPORT (Issue from schema)
    ├── test_services.py     # BROKEN IMPORT (Issue from schema)
    ├── test_subscriptions.py # Subscription lifecycle mapping
    ├── test_usage.py        # Quota enforcement
    ├── test_users.py        # User profile, identity, isolation
    └── test_webhooks.py     # Apple webhook endpoint
```

### Pattern: Unit Test Fixture Structure
The unit test conftest builds a FastAPI TestClient with dependency overrides:
- `get_db` -> MagicMock
- `get_current_user` -> TEST_USER constant
- `get_chat_service` -> ChatService with mocked DB/LLM
- `get_config` -> mock config with quotas

For the webhook router, a separate `webhook_client` fixture overrides `get_subscription_service`.

### Pattern: E2E Test Structure
E2E tests use real Firebase auth, real DB via `_app_lifespan`, and transaction rollback via `_db_transaction`. Each test module runs in a module-scoped event loop. The `create_chat` helper seeds test data.

### Anti-Patterns to Avoid
- **String-based module references:** Forbidden by CLAUDE.md. Use direct module imports.
- **Importing from old module paths:** `Issue` must be imported from `nativespeaker.api.models.content`, NOT `nativespeaker.api.schema`.
- **Missing `pytest.mark.asyncio` on async tests in unit suite:** Some subscription tests are bare coroutines (`<Coroutine>` in collection output) -- they likely run but should have explicit markers.

## Comprehensive Coverage Gap Analysis

### Critical: Broken Test Modules (Wave 0)

| File | Issue | Fix |
|------|-------|-----|
| `tests/unit/test_models.py` | `from nativespeaker.api.schema import Issue` fails | Change to `from nativespeaker.api.models.content import Issue` |
| `tests/unit/test_services.py` | `from nativespeaker.api.schema import Issue` fails | Change to `from nativespeaker.api.models.content import Issue` |

These two files contain ~20+ tests that are currently **not running at all**.

### E2E Coverage Gaps

| Endpoint | Method | Currently Tested | Gap |
|----------|--------|-----------------|-----|
| `POST /chats` | POST | Yes (4 tests) | None |
| `POST /chats/{id}` | POST | Yes (1 test) | None |
| `GET /chats` | GET | Yes (1 test) | None |
| `GET /chats/{id}` | GET | Yes (1 test) | None |
| `DELETE /chats/{id}` | DELETE | Yes (1 test) | None |
| `GET /examples` | GET | Yes (2 tests) | None |
| `GET /health/ready` | GET | Yes (1 test) | None |
| `GET /` | GET | Yes (1 test) | None |
| **`GET /users/me`** | GET | **No e2e test** | **Needs e2e: profile fields, usage, plan** |
| **`POST /webhooks/apple`** | POST | **No e2e test** | **Needs e2e: happy path** (see note) |
| Cross-user isolation | Various | Yes (5 tests) | None |
| Full lifecycle | Multi | Yes (1 test) | None |
| **Subscription lifecycle e2e** | - | **No e2e test** | **Complex: requires Apple JWS mocking** |
| **Error cases e2e** | Various | **No e2e test** | **404 on nonexistent chat, unsupported lang, etc.** |
| **Quota exceeded e2e** | POST /chats | **No e2e test** | **Would need usage exhaustion in test** |

**Note on webhook e2e:** True e2e for `POST /webhooks/apple` requires a valid Apple-signed JWS payload. This is impractical without Apple's sandbox server. A unit-level integration test with mocked verifier is sufficient. However, we can add an e2e test that verifies the endpoint exists, rejects malformed payloads, and returns appropriate error codes.

### Unit Test Coverage Gaps

#### Security Gaps (Explicit User Request)

| Missing Test | Module | Priority |
|-------------|--------|----------|
| Bearer token with extra whitespace/malformation | auth/dependencies | HIGH |
| `Bearer ` prefix with empty token after strip | dependencies | HIGH |
| Auth header not starting with "Bearer " | dependencies | MEDIUM |
| Multiple Authorization headers | dependencies | LOW |
| JWTVerifier JWKS fetch failure during verify | auth.py | MEDIUM |
| Inactive user cannot access any endpoint (not just /users/me) | dependencies | HIGH |
| Subscription webhook replay attack (reused JWS) | services/subscriptions | MEDIUM |
| Subscription notification without transaction data | services/subscriptions | MEDIUM |
| Subscription new subscription (no existing) flow | services/subscriptions | HIGH |
| Rate limited error returns Retry-After header | exception_handlers | MEDIUM |
| QueueFullError returns Retry-After header | exception_handlers | MEDIUM |
| CircuitOpenError returns Retry-After header | exception_handlers | MEDIUM |

#### Service/DB Gaps

| Missing Test | Module | Priority |
|-------------|--------|----------|
| `ChatService.list_chats` | services/chats | MEDIUM |
| `ChatService.get_messages` success path | services/chats | MEDIUM |
| `ChatService.get_messages` raises InvalidChatError | services/chats | MEDIUM |
| `UserService.get_or_create` | services/users | MEDIUM |
| `UserService.get_by_id` | services/users | MEDIUM |
| New subscription creation flow (no existing sub) | services/subscriptions | HIGH |
| Subscription with missing appAccountToken | services/subscriptions | MEDIUM |
| Subscription notification with missing transaction data | services/subscriptions | MEDIUM |
| Usage reset on plan change | services/subscriptions | MEDIUM |
| `ResiliencePolicy` retry logic | resilience | LOW (complex) |
| `_is_transient_error` classification | resilience | MEDIUM |

#### Router-Level Gaps (Unit)

| Missing Test | Router | Priority |
|-------------|--------|----------|
| `GET /chats` returns correct ChatResponse shape | chats router | LOW (covered by e2e) |
| `GET /examples?lang=missing` returns 400 | examples router | LOW (covered by service test) |
| No unit tests for chats router at all | chats router | MEDIUM |
| Webhook router unit tests with `webhooks_router` included in `client` fixture | webhooks | LOW (already has dedicated `webhook_client`) |

### Async Test Marker Issue

Several tests in `test_subscriptions.py` are collected as `<Coroutine>` rather than `<Function>`, meaning they may not be running as proper async tests despite `asyncio_mode = "auto"`:
- `TestSubscriptionLifecycle.test_ignored_notification_types`
- `TestIdempotency.test_duplicate_notification_ignored`
- `TestPlanTierUpdate.test_plan_updated_on_subscription_change`
- `TestFirebaseSync.test_firebase_sync_on_tier_change`
- `TestFirebaseSync.test_uses_to_thread`
- `TestFirebaseSync.test_firebase_failure_does_not_raise`
- `TestFirebaseSync.test_no_firebase_sync_when_tier_unchanged`

These async tests inside classes need `@pytest.mark.asyncio` decorator to be properly recognized. With `asyncio_mode = "auto"`, top-level async functions are auto-detected, but async methods inside classes may need explicit markers.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT test tokens | Custom token generator | Existing `make_token()` in unit/conftest.py | Already battle-tested, covers all claim variations |
| Test database setup | Manual SQL setup | Existing `_db_transaction` rollback fixture | Handles transaction isolation correctly |
| Async test infrastructure | Custom async runners | pytest-asyncio auto mode | Already configured project-wide |
| Mock Apple payloads | Real Apple JWS tokens | Existing `_make_mock_payload` / `_make_mock_transaction` helpers | Apple JWS requires real certs |

## Common Pitfalls

### Pitfall 1: Broken Import Goes Unnoticed
**What goes wrong:** Tests with import errors silently fail to collect -- pytest reports errors but still shows a passing exit code if other tests pass.
**Why it happens:** `test_models.py` and `test_services.py` import `Issue` from old location.
**How to avoid:** Fix imports in Wave 0, then verify 0 collection errors.
**Warning signs:** `2 errors during collection` in pytest output.

### Pitfall 2: Async Tests in Classes Not Running
**What goes wrong:** Async test methods inside classes appear as `<Coroutine>` in collection, may silently pass without executing the async body.
**Why it happens:** `asyncio_mode = "auto"` auto-detects top-level async functions but class methods may need explicit `@pytest.mark.asyncio`.
**How to avoid:** Add `@pytest.mark.asyncio` to all async test methods in classes, or use `pytestmark = pytest.mark.asyncio` at module level.
**Warning signs:** Test collection shows `<Coroutine>` instead of `<Function>`.

### Pitfall 3: E2E Subscription Tests Require Mocking
**What goes wrong:** Trying to test the full subscription flow e2e requires a valid Apple-signed JWS.
**Why it happens:** `SignedDataVerifier.verify_and_decode_notification` validates Apple's certificate chain.
**How to avoid:** For subscription e2e, use a semi-integration approach: mock only the Apple verifier at app.state level, keep everything else real.
**Warning signs:** `VerificationException` in test output.

### Pitfall 4: E2E Tests Mutating Shared State
**What goes wrong:** E2E tests that modify user subscription plan or usage can affect other tests.
**Why it happens:** `_db_transaction` rollback is scoped to module, not individual tests.
**How to avoid:** Tests that change user state should be isolated or run last in their module.
**Warning signs:** Test order dependency, flaky failures.

## Code Examples

### Fix Broken Imports
```python
# In tests/unit/test_models.py and tests/unit/test_services.py
# BEFORE (broken):
from nativespeaker.api.schema import ExamplesResponse, Issue

# AFTER (fixed):
from nativespeaker.api.schema import ExamplesResponse
from nativespeaker.api.models.content import Issue
```

### E2E Test for GET /users/me
```python
# tests/e2e/test_users.py
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestUserProfile:
    async def test_get_user_profile(self, async_client):
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "subscription_plan" in data
        assert "requests_used" in data
        assert "monthly_limit" in data
        assert "resets_at" in data
        assert "name" in data
        assert "created_at" in data
        # Internal fields must NOT be exposed
        assert "id" not in data
        assert "jwt_sub" not in data
        assert "active" not in data

    async def test_profile_plan_is_valid_enum(self, async_client):
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["subscription_plan"] in ("free", "silver", "gold", "platinum")
```

### Security Unit Test: Auth Edge Cases
```python
# Additional tests for test_exception_handlers.py or a new test_auth_security.py
def test_bearer_with_only_whitespace(dep_client):
    response = dep_client.get("/protected",
                              headers={"Authorization": "Bearer   "})
    assert response.status_code == 401

def test_non_bearer_auth_scheme(dep_client):
    response = dep_client.get("/protected",
                              headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
```

### E2E Error Case Tests
```python
# tests/e2e/test_error_cases.py
import pytest
from uuid import uuid4

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestErrorCases:
    async def test_get_nonexistent_chat_returns_404(self, async_client):
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_delete_nonexistent_chat_returns_404(self, async_client):
        response = await async_client.delete(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_followup_nonexistent_chat_returns_404(self, async_client):
        response = await async_client.post(f"/chats/{uuid4()}",
                                           json={"content": "hello"})
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_unsupported_language_returns_400(self, async_client):
        response = await async_client.post("/chats",
                                           json={"phrase": "test", "lang": "xx"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    async def test_missing_phrase_returns_422(self, async_client):
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_unauthenticated_request_returns_401(self, _app_lifespan):
        """Request without Authorization header gets 401."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "unauthorized"
```

### Unit Test: New Subscription Creation Flow
```python
# Addition to tests/unit/test_subscriptions.py
class TestNewSubscription:
    """New subscription flow -- no existing subscription in DB."""

    async def test_creates_subscription_for_new_user(self,
                                                      subscription_service,
                                                      mock_verifier,
                                                      mock_subscriptions_db):
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.SUBSCRIBED,
            notification_uuid="new-sub-uuid",
        )
        user_id = uuid4()
        mock_verifier.verify_and_decode_notification.return_value = payload
        mock_verifier.verify_and_decode_signed_transaction.return_value = (
            _make_mock_transaction(
                product_id="com.example.nativespeaker.gold",
                app_account_token=str(user_id),
            )
        )

        # No existing subscription
        mock_subscriptions_db.get_subscription_by_external_id.return_value = None
        new_sub = MagicMock()
        new_sub.id = uuid4()
        new_sub.user_id = user_id
        mock_subscriptions_db.create_subscription.return_value = new_sub

        await subscription_service.process_apple_notification("signed.payload")

        mock_subscriptions_db.create_subscription.assert_called_once()
        mock_subscriptions_db.update_user_plan.assert_called_once_with(
            user_id=user_id, plan=SubscriptionPlan.gold
        )
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ with pytest-asyncio 1.3+ |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/unit/ -q` |
| Full suite command | `python -m pytest tests/unit/ -q && python -m pytest tests/e2e/ -m e2e -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FIX-01 | Broken imports in test_models.py and test_services.py fixed | unit | `python -m pytest tests/unit/test_models.py tests/unit/test_services.py -q` | Yes (but broken) |
| FIX-02 | Async test markers added to subscription tests | unit | `python -m pytest tests/unit/test_subscriptions.py -q` | Yes |
| E2E-01 | GET /users/me returns profile with all fields | e2e | `python -m pytest tests/e2e/test_users.py -m e2e -q` | No -- Wave 0 |
| E2E-02 | E2E error cases (404, 400, 422, 401) | e2e | `python -m pytest tests/e2e/test_error_cases.py -m e2e -q` | No -- Wave 0 |
| SEC-01 | Auth edge cases (empty bearer, non-bearer, whitespace) | unit | `python -m pytest tests/unit/test_auth_security.py -q` | No -- Wave 0 |
| SEC-02 | Subscription security (new sub, missing token, no txn) | unit | `python -m pytest tests/unit/test_subscriptions.py -q` | Partially |
| SEC-03 | Retry-After header on 503/429 errors | unit | `python -m pytest tests/unit/test_exception_handlers.py -q` | Partially |
| UNIT-01 | ChatService.list_chats and get_messages tested | unit | `python -m pytest tests/unit/test_services.py -q` | Yes (needs import fix) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -q`
- **Per wave merge:** `python -m pytest tests/unit/ -q && python -m pytest tests/e2e/ -m e2e -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Fix `tests/unit/test_models.py` broken import
- [ ] Fix `tests/unit/test_services.py` broken import
- [ ] `tests/e2e/test_users.py` -- covers E2E-01
- [ ] `tests/e2e/test_error_cases.py` -- covers E2E-02
- [ ] Additional security tests in existing files or new `tests/unit/test_auth_security.py` -- covers SEC-01

## Prioritized Implementation Order

### Wave 0: Fix Broken Tests (blocking)
1. Fix `Issue` import in `test_models.py` and `test_services.py`
2. Add `@pytest.mark.asyncio` to async test methods in `test_subscriptions.py` classes
3. Verify all 103+ tests collect and pass with 0 errors

### Wave 1: E2E Gaps (user-requested focus)
1. `tests/e2e/test_users.py` -- GET /users/me e2e coverage
2. `tests/e2e/test_error_cases.py` -- 404/400/422/401 error paths e2e
3. Expand existing e2e tests if needed (edge cases)

### Wave 2: Security Unit Tests (user-requested focus)
1. Auth edge cases: empty bearer, non-bearer scheme, whitespace token, malformed "Bearer" prefix
2. Inactive user blocking across multiple endpoints (not just /users/me)
3. Retry-After header verification for QueueFullError, CircuitOpenError
4. QuotaExceededError returns 429 with rate_limited code (already partially covered)

### Wave 3: Subscription Service Gaps
1. New subscription creation flow (no existing sub in DB)
2. Missing appAccountToken handling
3. Missing transaction data handling
4. Usage reset on plan change
5. Default match arm in _map_lifecycle_event

### Wave 4: Service/DB Unit Test Gaps
1. ChatService.list_chats, get_messages (success + error)
2. UserService.get_or_create, get_by_id
3. Additional ResiliencePolicy tests (transient error classification)

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: all source files in `src/nativespeaker/api/` and `tests/`
- `python -m pytest --co -q` collection output for both unit and e2e suites
- `python -m pytest tests/unit/ -q` execution (103 passed, 2 collection errors confirmed)

### Secondary (MEDIUM confidence)
- pytest-asyncio auto mode behavior with class-based async tests (documented in pytest-asyncio docs)

## Metadata

**Confidence breakdown:**
- Coverage gap analysis: HIGH - based on exhaustive codebase and test file comparison
- Broken import identification: HIGH - confirmed via pytest collection and Python import
- Security test gaps: HIGH - based on direct review of auth.py, dependencies.py, and existing test coverage
- Async marker issue: MEDIUM - `<Coroutine>` in collection strongly suggests but need to verify tests actually run correctly

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (stable codebase, no external dependency changes expected)
