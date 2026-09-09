import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_chat_service,
    get_db,
    get_linked_identity,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.auth.jwt_verifier import (
    DECODE_ALGORITHMS,
    DECODE_OPTIONS,
    DEFAULT_LEEWAY,
    BoundedReason,
    VerificationResult,
    bounded_reason_for,
    claims_from_payload,
)
from nativespeaker.api.crud import ChatsDB
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.resilience import Admitted
from nativespeaker.api.routers import chats_router, examples_router, health_router, root_router
from nativespeaker.api.schemas.auth import LinkedIdentity
from nativespeaker.api.services import ChatService, QuotaService
from nativespeaker.api.tables.auth import AuthChallenge
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.users import User

# JWT test infrastructure: an ephemeral RSA keypair and a token factory.

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
    """A fixed public key instead of JWKS; every other rule is imported from production, so this cannot drift."""

    def __init__(self):
        self._audience = TEST_PROJECT_ID
        self._issuer = TEST_ISSUER
        # Imported, never restated: widening production's algorithms, leeway or required claims
        # must reach this double too, or the cases running against it would stay green through it.
        self._leeway = DEFAULT_LEEWAY
        self._public_key = PUBLIC_KEY_PEM

    def verify(self, token: str) -> VerificationResult:
        try:
            payload = pyjwt.decode(token,
                                   self._public_key,
                                   algorithms=DECODE_ALGORITHMS,
                                   audience=self._audience,
                                   issuer=self._issuer,
                                   leeway=self._leeway,
                                   options=DECODE_OPTIONS)
        except pyjwt.PyJWTError as exc:
            return None, bounded_reason_for(exc)
        except Exception:
            # The same structural "never raises" clause production carries: an escape here would
            # 500 a caller owed a 401, and a double that can raise proves a weaker property.
            return None, BoundedReason.bad_signature

        return claims_from_payload(payload)


def make_test_verifier() -> _FixedKeyVerifier:
    """Create a verifier that validates against the ephemeral test keypair."""
    return _FixedKeyVerifier()


# Handlers read identity.user.id and nothing else, so the id is the whole contract.
TEST_SUBJECT = "test-user"
TEST_USER_ID = uuid7()
# `LinkedIdentity`, because this is what `get_linked_identity` is overridden with: a plain
# `Identity` here would stand in for a narrowing the production dependency cannot return.
TEST_IDENTITY = LinkedIdentity(
    user=User(id=TEST_USER_ID, active=True),
    identity=ExternalIdentity(id=uuid7(),
                              user_id=TEST_USER_ID,
                              issuer=TEST_ISSUER,
                              subject=TEST_SUBJECT,
                              provider=IdentityProvider.google,
                              provider_uid="google-account-test",
                              identity_state=IdentityState.active),
    issuer=TEST_ISSUER,
    subject=TEST_SUBJECT,
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


EVALUATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def charge_calls(monkeypatch) -> list[UUID]:
    """Records the user each charge would bill, in place of resolving one: the resolver has its own suite."""
    calls: list[UUID] = []

    async def recording_charge(self, *, user_id: UUID, evaluated_at: datetime) -> None:
        calls.append(user_id)

    monkeypatch.setattr(QuotaService, "charge", recording_charge)
    return calls


@asynccontextmanager
async def _granted_admission():
    """A real async context manager, because `ChatService` enters one; an `AsyncMock` attribute is not."""
    yield Admitted()


@pytest.fixture
def service(mock_chats_db, charge_calls):
    llm_service = AsyncMock()
    llm_service.admission = _granted_admission
    # Explicit arguments, not omitted ones: ChatService requires both, so a wiring slip cannot serve free.
    # `AsyncMock`, because the service commits the request session before it enters admission.
    svc = ChatService(db=AsyncMock(),
                      llm_service=llm_service,
                      examples={"en": ["Example 1", "Example 2"],
                                "es": ["Ejemplo 1"]},
                      messages_limit=50,
                      chats_limit=50,
                      quota_service=QuotaService(MagicMock()),
                      evaluated_at=EVALUATED_AT)
    svc.chats_db = mock_chats_db
    return svc


@pytest.fixture
def client(mock_chats_db, service):
    """Four routers with the identity supplied: one override covers both the router-level and endpoint declaration."""
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(chats_router)
    app.include_router(examples_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: service
    app.dependency_overrides[get_linked_identity] = lambda: TEST_IDENTITY
    # No quota override is needed: the charge is called by the ChatService replaced above, and `charge_calls` stubs it.

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client




ANONYMOUS_IDENTITY = VerifiedProviderIdentity(provider=IdentityProvider.anonymous,
                                              provider_uid=None)


class FakeFirebaseAdapter:
    """A scriptable stand-in for the provider seam; async because a synchronous fake would fail against real wiring.

    It scripts the seam's answer and nothing behind it: no classification and no email rule.
    """

    def __init__(self) -> None:
        self.answer: BaseException | VerifiedProviderIdentity = ANONYMOUS_IDENTITY
        self.calls: list[tuple[str, str]] = []
        # A second answer and a second call list, so each method is scripted and counted on its own.
        self.revoke_answer: BaseException | None = None
        self.revoke_calls: list[tuple[str, str]] = []

    def script(self, answer: BaseException | VerifiedProviderIdentity) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted identity is returned."""
        self.answer = answer

    def script_revocation(self, answer: BaseException | None) -> None:
        """Raise-or-confirm: a scripted exception is raised, `None` confirms the revocation."""
        self.revoke_answer = answer

    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        self.calls.append((issuer, subject))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    async def revoke_refresh_tokens(self, issuer: str, subject: str) -> None:
        self.revoke_calls.append((issuer, subject))
        if isinstance(self.revoke_answer, BaseException):
            raise self.revoke_answer


@pytest.fixture
def fake_firebase_adapter() -> FakeFirebaseAdapter:
    """A fresh fake per test, defaulting to the anonymous identity -- what an empty read establishes."""
    return FakeFirebaseAdapter()


class FakeChallengeStore:
    """One in-memory row whose `claim` and `consume` mirror the real conditional updates clause for
    clause. Defined once and imported by all four precedence suites: two drifting fakes of the
    system's only serialization point is the hazard, and three copies were what they carried."""

    def __init__(self) -> None:
        self._binding = ChallengesDB()
        self.row: AuthChallenge | None = None
        self.consume_calls = 0

    async def locate(self, session, challenge_id: str) -> AuthChallenge | None:
        if self.row is not None and self.row.challenge_id == challenge_id:
            return self.row
        return None

    def verify_binding(self, row, identity):
        return self._binding.verify_binding(row, identity)

    async def claim(self, session, *, challenge_id, now) -> bool:
        row = self.row
        if row is None or row.challenge_id != challenge_id:
            return False
        if row.claimed_at is not None or row.expires_at <= now:
            return False
        row.claimed_at = now
        return True

    async def consume(self, session, *, challenge_id, now) -> bool:
        self.consume_calls += 1
        row = self.row
        if row is None or row.challenge_id != challenge_id:
            return False
        if row.claimed_at is None or row.consumed_at is not None:
            return False
        row.consumed_at = now
        row.preauth_subject = None
        return True
