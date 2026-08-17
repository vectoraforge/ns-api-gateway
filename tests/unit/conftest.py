import time
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid7

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import nativespeaker.api.routers.users as users_module
from nativespeaker.api.app.dependencies import (
    get_chat_service,
    get_config,
    get_current_user,
    get_db,
    get_identity_context,
    get_subscription_service,
    require_quota,
)
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth import UserIdentity
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.database import ChatsDB
from nativespeaker.api.database.usage import EffectiveGrant
from nativespeaker.api.exceptions import AuthenticationError
from nativespeaker.api.models import SubscriptionPlan, User
from nativespeaker.api.quota.grants import GrantRow
from nativespeaker.api.quota.rollover import (
    QUOTA_ADMISSION_ENTRY,
    QUOTA_ADMISSION_KEY_POLICY,
)
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import AdmissionLedger
from nativespeaker.api.routers import (
    build_webhooks_router,
    chats_router,
    examples_router,
    health_router,
    root_router,
    users_router,
)
from nativespeaker.api.services import ChatService, SubscriptionService

# ---------------------------------------------------------------------------
# JWT test infrastructure -- ephemeral RSA keypair and token factory
# (migrated from tests/jwt_helpers.py)
# ---------------------------------------------------------------------------

TEST_PROJECT_ID = "test-project"
TEST_ISSUER = f"https://securetoken.google.com/{TEST_PROJECT_ID}"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()

PRIVATE_KEY_PEM = _private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                             format=serialization.PrivateFormat.PKCS8,
                                             encryption_algorithm=serialization.NoEncryption())

PUBLIC_KEY_PEM = _public_key.public_bytes(encoding=serialization.Encoding.PEM,
                                          format=serialization.PublicFormat.SubjectPublicKeyInfo)


def make_token(sub: str = "test-user", *,
               aud: str = TEST_PROJECT_ID,
               iss: str = TEST_ISSUER,
               exp: float | None = None,
               iat: float | None = None,
               email_verified: bool = True,
               extra_claims: dict | None = None,
               algorithm: str = "RS256",
               private_key: bytes = PRIVATE_KEY_PEM,
               headers: dict | None = None) -> str:
    """Create a signed JWT for testing."""
    now = time.time()
    payload = {
        "sub": sub,
        "aud": aud,
        "iss": iss,
        "exp": exp if exp is not None else now + 3600,
        "iat": iat if iat is not None else now,
        "email_verified": email_verified,
    }
    if extra_claims:
        payload.update(extra_claims)
    return pyjwt.encode(payload, private_key, algorithm=algorithm, headers=headers)


class _FixedKeyVerifier:
    """Standalone verifier that uses a fixed public key instead of fetching JWKS."""

    def __init__(self):
        self._audience = TEST_PROJECT_ID
        self._issuer = TEST_ISSUER
        self._leeway = 30
        self._public_key = PUBLIC_KEY_PEM

    def verify(self, token: str) -> UserIdentity:
        try:
            payload = pyjwt.decode(token,
                                   self._public_key,
                                   algorithms=["RS256"],
                                   audience=self._audience,
                                   issuer=self._issuer,
                                   leeway=self._leeway,
                                   options={"require": ["exp", "iat", "aud", "iss", "sub"]})
        except pyjwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired") from None
        except pyjwt.InvalidAudienceError:
            raise AuthenticationError("Invalid audience") from None
        except pyjwt.InvalidIssuerError:
            raise AuthenticationError("Invalid issuer") from None
        except pyjwt.DecodeError:
            raise AuthenticationError("Token decode failed") from None
        except pyjwt.InvalidAlgorithmError:
            raise AuthenticationError("Invalid algorithm") from None
        except pyjwt.MissingRequiredClaimError as exc:
            raise AuthenticationError(f"Missing claim: {exc}") from None
        except Exception as exc:
            raise AuthenticationError(f"Token verification failed: {exc}") from None

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Missing sub claim")

        return UserIdentity(sub=str(sub),
                            email=payload.get("email", ""),
                            name=payload.get("name"))


def make_test_verifier() -> _FixedKeyVerifier:
    """Create a verifier that validates against the ephemeral test keypair."""
    return _FixedKeyVerifier()


TEST_USER = User(
    email="test@example.com",
    display_name="Test User",
    active=True,
)

# The effective grant the test user holds, and the tier allowance it points at.
TEST_GRANT = EffectiveGrant(grant_id=uuid7(), tier_id="free", monthly_credits=10)

# The barrier's typed verified identity context for the test user: the resolved linked identity
# and the stored `core.external_identities.provider` column it carries.
TEST_IDENTITY = VerifiedIdentityContext(issuer=TEST_ISSUER,
                                        subject="test-user",
                                        outcome=ResolutionOutcome.linked,
                                        user_id=TEST_USER.id,
                                        external_identity_id=uuid7(),
                                        provider=IdentityProvider.anonymous)

# The test user's persisted purchase-attribution tokens, one per store provider, as
# `core.store_purchase_tokens` holds them.
TEST_STORE_TOKENS = {StoreProvider.apple: str(uuid7()),
                     StoreProvider.google_play: str(uuid7())}


def store_tokens_db(tokens=None):
    """A stand-in for the `core.store_purchase_tokens` read `GET /users/me` performs."""
    db = AsyncMock()
    db.tokens_for = AsyncMock(return_value=dict(TEST_STORE_TOKENS if tokens is None else tokens))
    return db


@pytest.fixture
def mock_chats_db():
    db = AsyncMock(spec=ChatsDB)
    db.create_chat = MagicMock()
    db.get_chat = AsyncMock(return_value=None)
    db.get_messages = AsyncMock(return_value=[])
    db.delete = AsyncMock(return_value=1)
    db.list_chats = AsyncMock(return_value=[])
    db.count_chats = AsyncMock(return_value=0)
    return db


@pytest.fixture
def mock_usage_db():
    db = AsyncMock()
    db.get_usage = AsyncMock(return_value=0)
    db.reset_usage = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_grants_db():
    db = AsyncMock()
    db.effective_grant = AsyncMock(return_value=TEST_GRANT)
    return db


@pytest.fixture
def service(mock_chats_db):
    llm_service = AsyncMock()
    svc = ChatService(db=MagicMock(),
                      llm_service=llm_service,
                      examples={"en": ["Example 1", "Example 2"],
                                "es": ["Ejemplo 1"]},
                      messages_limit=50,
                      chats_limit=50)
    svc.chats_db = mock_chats_db
    return svc


@pytest.fixture
def client(mock_chats_db, mock_usage_db, mock_grants_db):
    mock_config = MagicMock()
    mock_config.quotas = {SubscriptionPlan.free: 10,
                          SubscriptionPlan.silver: 50,
                          SubscriptionPlan.gold: 200,
                          SubscriptionPlan.platinum: 1000}

    # Patch UsageDB/GrantsDB/StorePurchaseTokensDB in users router (GET /users/me creates them
    # directly)
    with (patch.object(users_module, "UsageDB", return_value=mock_usage_db),
          patch.object(users_module, "GrantsDB", return_value=mock_grants_db),
          patch.object(users_module, "StorePurchaseTokensDB", return_value=store_tokens_db())):
        app = FastAPI()
        app.include_router(root_router)
        app.include_router(chats_router)
        app.include_router(examples_router)
        app.include_router(health_router)
        app.include_router(users_router)
        register_exception_handlers(app)

        llm_service = AsyncMock()
        svc = ChatService(db=MagicMock(),
                          llm_service=llm_service,
                          examples={"en": ["Example 1", "Example 2"],
                                    "es": ["Ejemplo 1"]},
                          messages_limit=50,
                          chats_limit=50)
        svc.chats_db = mock_chats_db

        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        app.dependency_overrides[get_identity_context] = lambda: TEST_IDENTITY
        app.dependency_overrides[get_chat_service] = lambda: svc
        app.dependency_overrides[get_config] = lambda: mock_config
        app.dependency_overrides[require_quota] = lambda: None

        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client


@pytest.fixture
def service_instance(client):
    """The ChatService instance injected via DI overrides."""
    return client.app.dependency_overrides[get_chat_service]()


@pytest.fixture
def mock_subscription_service():
    service = AsyncMock(spec=SubscriptionService)
    service.process_apple_notification = AsyncMock(return_value=None)
    return service


@pytest.fixture
def webhook_client(mock_subscription_service):
    app = FastAPI()
    app.include_router(build_webhooks_router(["apple"]))
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_subscription_service] = lambda: mock_subscription_service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Quota enforcement helpers -- the effective-grant rows, the admission request,
# and the store the lazy monthly rollover sequence takes its statements against
# ---------------------------------------------------------------------------


def grant_row(*,
              grant_id: UUID | None = None,
              user_id: UUID | None = None,
              tier_id: str = "free",
              source: AccessGrantSource = AccessGrantSource.anonymous_device_grant,
              status: AccessGrantStatus = AccessGrantStatus.active,
              starts_at: datetime | None = None,
              ends_at: datetime | None = None,
              subscription_id: UUID | None = None,
              monthly_credits: int | None = 10) -> GrantRow:
    """One `core.access_grants` row as the enforcement paths read it."""
    return GrantRow(grant_id=grant_id or uuid7(),
                    user_id=user_id or uuid7(),
                    tier_id=tier_id,
                    source=source,
                    status=status,
                    starts_at=starts_at or datetime(2026, 1, 1, tzinfo=UTC),
                    ends_at=ends_at,
                    subscription_id=subscription_id,
                    tier_monthly_credits=monthly_credits)


class FakeRateLimiter:
    """A `quota_checked_request` verdict, without the `limits` storage behind it."""

    def __init__(self, *, allowed: bool = True, retry_after_seconds: int | None = 30):
        self.allowed = allowed
        self.retry_after_seconds = retry_after_seconds
        self.consumed: list[tuple[str, str]] = []

    def consume(self, name: str, key: str, *, cost: int | None = None) -> LimitDecision:
        self.consumed.append((name, key))
        return LimitDecision(allowed=self.allowed, limiter=name, charged=True,
                             retry_after_seconds=None if self.allowed
                             else self.retry_after_seconds)


def quota_request(*, method: str = "POST", path: str = "/chats",
                  limiter: FakeRateLimiter | None = None) -> Request:
    """A request carrying only what `require_quota` reads from it."""
    state = SimpleNamespace(rate_limiter=limiter or FakeRateLimiter())
    return cast(Request, SimpleNamespace(method=method,
                                         url=SimpleNamespace(path=path),
                                         app=SimpleNamespace(state=state)))


class FakeQuotaStore:
    """Records the four statements the rollover sequence takes, and the commit that ends its
    transaction. `calls` keeps them all in the order they were made."""

    def __init__(self,
                 rows: Sequence[GrantRow] = (),
                 usage: tuple[str, int] | None = ("2026-03", 0),
                 *,
                 increment_error: Exception | None = None):
        self.rows = list(rows)
        self.usage = usage
        self.increment_error = increment_error
        self.grant_reads: list[tuple[UUID, datetime]] = []
        self.usage_reads: list[UUID] = []
        self.rollovers: list[tuple[UUID, dict]] = []
        self.increments: list[tuple[UUID, str]] = []
        self.commits = 0
        self.calls: list[str] = []

    async def locked_grant_rows(self, user_id: UUID, now: datetime) -> Sequence[GrantRow]:
        self.calls.append("locked_grant_rows")
        self.grant_reads.append((user_id, now))
        return self.rows

    async def locked_usage_row(self, grant_id: UUID) -> tuple[str, int] | None:
        self.calls.append("locked_usage_row")
        self.usage_reads.append(grant_id)
        return self.usage

    async def write_rollover(self, grant_id: UUID, values) -> None:
        self.calls.append("write_rollover")
        self.rollovers.append((grant_id, dict(values)))

    async def increment_usage(self, grant_id: UUID, period: str) -> None:
        self.calls.append("increment_usage")
        self.increments.append((grant_id, period))
        if self.increment_error is not None:
            raise self.increment_error

    async def commit(self) -> None:
        self.calls.append("commit")
        self.commits += 1


def admitted_ledger(*, method: str = "POST", path: str = "/chats",
                    allowed: bool = True) -> AdmissionLedger:
    """A ledger that has taken the request as far as quota admission."""
    ledger = AdmissionLedger(method, path)
    ledger.verify_jwt()
    ledger.admit_barrier()
    ledger.evaluate(QUOTA_ADMISSION_ENTRY, QUOTA_ADMISSION_KEY_POLICY, allowed=allowed)
    return ledger
