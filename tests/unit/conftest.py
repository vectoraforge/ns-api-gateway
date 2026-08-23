import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid7

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
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.adapters import (
    ProviderDataEntry,
    ProviderDataOutcome,
    ProviderDataResult,
)
from nativespeaker.api.auth.context import LinkedIdentity
from nativespeaker.api.auth.verification import VerificationResult, bounded_reason_for, claims_from_payload
from nativespeaker.api.database import ChatsDB
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.models.users import User
from nativespeaker.api.routers import chats_router, examples_router, health_router, root_router
from nativespeaker.api.services import ChatService

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
    """Standalone verifier that uses a fixed public key instead of fetching JWKS.

    It differs from `JWTVerifier` in exactly one respect -- where the key comes from. The
    algorithm pin, the `require` list, the exception -> bounded-reason mapping and the
    non-empty-`sub` rule are the production ones, imported rather than reimplemented, so this stub
    cannot drift away from what it stands in for.
    """

    def __init__(self):
        self._audience = TEST_PROJECT_ID
        self._issuer = TEST_ISSUER
        self._leeway = 30
        self._public_key = PUBLIC_KEY_PEM

    def verify(self, token: str) -> VerificationResult:
        try:
            payload = pyjwt.decode(token,
                                   self._public_key,
                                   algorithms=["RS256"],
                                   audience=self._audience,
                                   issuer=self._issuer,
                                   leeway=self._leeway,
                                   options={"require": ["exp", "iat", "aud", "iss", "sub"]})
        except pyjwt.PyJWTError as exc:
            return None, bounded_reason_for(exc)

        return claims_from_payload(payload)


def make_test_verifier() -> _FixedKeyVerifier:
    """Create a verifier that validates against the ephemeral test keypair."""
    return _FixedKeyVerifier()


# The v1.6 `TEST_USER` was built from four columns the v2.0 schema dropped, so what stands in for
# an authenticated caller now is the §1.4 identity context the barrier attaches -- built over the
# real model classes, at their repaired shape. Handlers read `identity.user.id` and nothing else,
# so the id is the whole contract.
TEST_SUBJECT = "test-user"
TEST_USER_ID = uuid7()
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


@pytest.fixture
def service(mock_chats_db):
    llm_service = AsyncMock()
    # An explicit stub gate, not an omitted argument: `ChatService` requires one so that a wiring
    # slip serves both quota-checked POSTs free instead of failing. These cases' subject is chat
    # behaviour, not the charge, and `llm_service` is an `AsyncMock` here -- so the real
    # `on_admitted` callback never fires and this gate is never called. `tests/e2e/test_quota.py`
    # is where the charge itself is proven, against the real resilience layer.
    quota_gate = AsyncMock()
    svc = ChatService(db=MagicMock(),
                      llm_service=llm_service,
                      examples={"en": ["Example 1", "Example 2"],
                                "es": ["Ejemplo 1"]},
                      messages_limit=50,
                      chats_limit=50,
                      quota_gate=quota_gate)
    svc.chats_db = mock_chats_db
    return svc


@pytest.fixture
def client(mock_chats_db, service):
    """The four surviving routers with the identity context supplied instead of the barrier.

    `get_linked_identity` is overridden rather than the barrier being installed: this fixture's
    subject is what a handler does *once admitted*. What happens when the barrier did **not** admit
    is `test_identity_accessors.py`'s and `test_auth_security.py`'s subject, and neither overrides
    the accessor.
    """
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(chats_router)
    app.include_router(examples_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: service
    app.dependency_overrides[get_linked_identity] = lambda: TEST_IDENTITY
    # No quota override is needed, and there is nothing left to override (REBIND-06). The charge
    # used to be two decorator dependencies, each needing its own line here because overrides key
    # on the exact callable; it now travels inside the `ChatService` the line above already
    # replaces, whose `quota_gate` is a stub. This app still has no `state.session_factory`, and
    # no longer needs one: nothing on these paths reaches real quota code.

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# The shared §7.1 provider-seam fake (37-07 Task 3)
#
# It lives here rather than in a per-test module because every substituted create-user test needs
# it: this phase's mode-signal, precedence and transaction suites, 37-08's rejection matrix, and
# 37-10's step-10 email cases. `tests/e2e/conftest.py` imports it too, for the same reason it
# already imports `make_test_verifier` from this file -- `pythonpath = ["."]` makes both packages
# importable, and two copies of a fake are two things that can drift apart.
# ---------------------------------------------------------------------------


class FakeFirebaseAdapter:
    """A stand-in for the provider seam whose answer the caller writes.

    Scriptable on **all four** of `ProviderDataResult`'s fields -- `outcome`, `entries`, `email`
    and `email_verified`. The last two are not optional extras: §02 step 10's copy rule reads that
    pair, and a fake that could not vary them would send 37-10 looking for a second fake.

    `calls` records every `(issuer, subject)` pair, so a test can assert both *that* the provider
    was read and *how often*. §02 step 8 pins exactly one read per completion, and only a
    `retryable_failure` may ever spend more -- an assertion on `len(calls)` is what keeps a future
    stray second read visible instead of merely slow.

    `async def`, matching the concrete adapter rather than the Protocol: `FirebaseAdminLookup`
    offloads its blocking SDK call to a threadpool and is therefore awaitable, and `auth/retry.py`
    awaits whatever it is handed. A synchronous fake would pass against itself and fail against
    production wiring.
    """

    def __init__(self) -> None:
        self.result = ProviderDataResult(ProviderDataOutcome.ok)
        self.calls: list[tuple[str, str]] = []

    def script(self, outcome: ProviderDataOutcome = ProviderDataOutcome.ok, *,
               entries: tuple[ProviderDataEntry, ...] = (),
               email: str | None = None,
               email_verified: bool = False) -> None:
        self.result = ProviderDataResult(outcome, entries,
                                         email=email, email_verified=email_verified)

    async def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        self.calls.append((issuer, subject))
        return self.result


@pytest.fixture
def fake_firebase_adapter() -> FakeFirebaseAdapter:
    """A fresh fake per test, defaulting to `ok` with empty providerData -- the anonymous shape."""
    return FakeFirebaseAdapter()
