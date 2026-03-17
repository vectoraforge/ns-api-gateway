import time
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_service, get_config, get_db, get_user_id
from app.api.errors import register_exception_handlers
from app.config import ResilienceConfig
from app.database import ChatsDB
from app.exceptions import AuthenticationError
from app.resilience import ResiliencePolicy
from app.routers import chats_router, examples_router, health_router, root_router
from app.service import ChatService

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

    def verify(self, token: str) -> str:
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

        return str(sub)


def make_test_verifier() -> _FixedKeyVerifier:
    """Create a verifier that validates against the ephemeral test keypair."""
    return _FixedKeyVerifier()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.prompt = "Test prompt for {lang}"
    config.examples = {"en": ["Example 1", "Example 2"],
                       "es": ["Ejemplo 1"]}
    config.history_max_messages = 50
    config.messages_max_page_size = 100
    config.chat_list_limit = 50
    config.model.name = "gpt-4o-mini"
    config.model.temperature = 0.3
    config.model.max_tokens = 1000
    return config


@pytest.fixture
def mock_chats_db():
    db = AsyncMock(spec=ChatsDB)
    db.create_chat = MagicMock()
    db.get_chat = AsyncMock(return_value=None)
    db.get_messages = AsyncMock(return_value=[])
    db.delete = AsyncMock(return_value=1)
    db.list_chats = AsyncMock(return_value=[])
    return db


@pytest.fixture
def service(mock_config, mock_chats_db):
    chain = AsyncMock()
    policy = ResiliencePolicy(ResilienceConfig(pool_size=1,
                                               queue_size=1,
                                               queue_retry_after_seconds=1,
                                               timeout_seconds=1,
                                               retry_max_attempts=1,
                                               retry_backoff_base_seconds=0,
                                               retry_backoff_max_seconds=0,
                                               circuit_breaker_failure_threshold=3,
                                               circuit_breaker_reset_seconds=60))
    svc = ChatService(chain=chain,
                      policy=policy,
                      config=mock_config,
                      db=MagicMock())
    svc.chats_db = mock_chats_db
    svc.chain = chain
    return svc


@pytest.fixture
def client(mock_config, mock_chats_db):
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(chats_router)
    app.include_router(examples_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    chain = AsyncMock()
    policy = ResiliencePolicy(ResilienceConfig(pool_size=1,
                                               queue_size=1,
                                               queue_retry_after_seconds=1,
                                               timeout_seconds=1,
                                               retry_max_attempts=1,
                                               retry_backoff_base_seconds=0,
                                               retry_backoff_max_seconds=0,
                                               circuit_breaker_failure_threshold=3,
                                               circuit_breaker_reset_seconds=60))
    service = ChatService(chain=chain,
                          policy=policy,
                          config=mock_config,
                          db=MagicMock())
    service.chats_db = mock_chats_db

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_config] = lambda: mock_config
    app.dependency_overrides[get_user_id] = lambda: "test-user"
    app.dependency_overrides[get_chat_service] = lambda: service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def service_instance(client):
    """The ChatService instance injected via DI overrides."""
    return client.app.dependency_overrides[get_chat_service]()
