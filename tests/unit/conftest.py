import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_service, get_current_user, get_db, get_subscription_service
from app.api.errors import register_exception_handlers
from app.auth import UserIdentity
from app.database import ChatsDB
from app.exceptions import AuthenticationError
from app.models import PlanTier, User
from app.routers import chats_router, examples_router, health_router, root_router, users_router, webhooks_router
from app.services import ChatService, SubscriptionService

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
    jwt_sub="test-user",
    email="test@example.com",
    name="Test User",
    plan=PlanTier.free,
    active=True,
)


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
    db.try_increment = AsyncMock(return_value=True)
    db.get_usage = AsyncMock(return_value=0)
    db.get_monthly_limit = AsyncMock(return_value=150)
    db.reset_usage = AsyncMock(return_value=None)
    return db


@pytest.fixture
def service(mock_chats_db, mock_usage_db):
    llm_service = AsyncMock()
    svc = ChatService(db=MagicMock(),
                      llm_service=llm_service,
                      examples={"en": ["Example 1", "Example 2"],
                                "es": ["Ejemplo 1"]},
                      messages_limit=50,
                      chats_limit=50)
    svc.chats_db = mock_chats_db
    svc.usage_db = mock_usage_db
    return svc


@pytest.fixture
def client(mock_chats_db, mock_usage_db):
    with patch("app.routers.users.UsageDB") as MockUsageDB:
        MockUsageDB.return_value = mock_usage_db

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
        svc.usage_db = mock_usage_db

        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        app.dependency_overrides[get_chat_service] = lambda: svc

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
    app.include_router(webhooks_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_subscription_service] = lambda: mock_subscription_service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
