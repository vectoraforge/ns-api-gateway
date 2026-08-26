import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from unit.conftest import FakeFirebaseAdapter, make_test_verifier

from nativespeaker.api.app.main import app
from nativespeaker.api.auth.firebase import _application_default_credential
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.models import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    Chat,
    ChatRole,
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    Message,
    User,
    UserMonthlyUsage,
)

# The tier the migration seeds as reference data at 50 monthly credits, well above any module's use.
REGISTERED_TIER_ID = "registered"


@pytest.fixture(scope="session")
def _app_config():
    """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
    return EnvironmentConfig().app_config


@pytest.fixture(scope="session")
def firebase_token(_app_config):
    """Obtain a real Firebase ID token via REST API for the dedicated test user."""
    api_key = _app_config.jwt.api_key
    assert api_key, "JWT_API_KEY env var required for e2e tests"
    email = os.environ["FIREBASE_TEST_EMAIL"]
    password = os.environ["FIREBASE_TEST_PASSWORD"]
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={api_key}",
        json={"email": email,
              "password": password,
              "returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["idToken"]
    # Store the test user's UID (from Firebase 'localId') for seeding assertions
    os.environ.setdefault("FIREBASE_TEST_USER_ID", data["localId"])
    return token


def _admin_credential_configured() -> bool:
    """Whether build_admin_apps would find a credential, asked with the one call it makes."""
    return _application_default_credential() is not None


_NO_ADMIN_CREDENTIAL = (
    "no Firebase Admin credential: set GOOGLE_APPLICATION_CREDENTIALS (Application Default "
    "Credentials) in .env"
)


# firebase_token signs in with a password, whose providerData the classifier rejects; only signUp is anonymous.
@pytest.fixture(scope="session")
def anonymous_firebase_credential(_app_config):
    """A genuinely anonymous Firebase user, minted for real; returns (id_token, local_id), or skips."""
    if not _admin_credential_configured():
        pytest.skip(_NO_ADMIN_CREDENTIAL)
    # Each call leaves a permanent user in the shared Firebase project, and nothing deletes it.
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={_app_config.jwt.api_key}",
        json={"returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    # Subscripting rather than .get(): if returnSecureToken were ever ignored, this fails loudly.
    return data["idToken"], data["localId"]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan():
    """Start app lifespan (config, DB engine, verifier, LLM service)."""
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def async_client(_app_lifespan, firebase_token):
    """Async HTTP client wired to the real app with Firebase auth."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {firebase_token}"
        yield client


@pytest.fixture(scope="module")
def test_user_id(firebase_token):
    """The Firebase test user's UID, matching the token's sub claim; firebase_token is what sets it."""
    _ = firebase_token
    return os.environ["FIREBASE_TEST_USER_ID"]


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _db_transaction(_app_lifespan):
    """Wrap each test in a transaction that rolls back: the app's session factory is swapped so its writes join it."""
    original_factory = _app_lifespan.state.session_factory

    # async_sessionmaker stores bind in its kw dict
    engine = original_factory.kw["bind"]

    async with engine.connect() as connection:
        transaction = await connection.begin()

        test_factory = async_sessionmaker(
            bind=connection,
            class_=SQLModelAsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        _app_lifespan.state.session_factory = test_factory
        try:
            yield test_factory
        finally:
            _app_lifespan.state.session_factory = original_factory
            await transaction.rollback()


@pytest.fixture
def stub_verifier(_app_lifespan):
    """Swap app.state.jwt_verifier for an ephemeral-RSA one; the app reads it per request, so the real path runs."""
    original = _app_lifespan.state.jwt_verifier
    _app_lifespan.state.jwt_verifier = make_test_verifier()
    try:
        yield _app_lifespan.state.jwt_verifier
    finally:
        _app_lifespan.state.jwt_verifier = original


@pytest.fixture
def scripted_firebase_adapter(_app_lifespan):
    """Swap app.state.firebase_adapter for a scripted fake, defaulting to ok with empty providerData."""
    original = _app_lifespan.state.firebase_adapter
    adapter = FakeFirebaseAdapter()
    _app_lifespan.state.firebase_adapter = adapter
    try:
        yield adapter
    finally:
        _app_lifespan.state.firebase_adapter = original


@pytest_asyncio.fixture(loop_scope="module")
async def linked_firebase_identity(_db_transaction, _app_config, test_user_id):
    """Seed the real Firebase credential's identity pair, so async_client is admitted."""
    return await seed_identity(_db_transaction,
                               issuer=_app_config.jwt.issuer,
                               subject=test_user_id)


async def seed_identity(factory, *,
                        issuer: str,
                        subject: str,
                        identity_state: IdentityState = IdentityState.active,
                        user_active: bool = True,
                        provider: IdentityProvider = IdentityProvider.google):
    """Insert a core.users row and its matching core.external_identities row; return both."""
    # The table's CHECK ties the two together: provider_uid is NULL exactly for anonymous.
    provider_uid = None if provider is IdentityProvider.anonymous else f"{provider}-uid-{subject}"
    async with factory() as session:
        user = User(active=user_active)
        session.add(user)
        await session.flush()
        identity = ExternalIdentity(user_id=user.id,
                                    issuer=issuer,
                                    subject=subject,
                                    provider=provider,
                                    provider_uid=provider_uid,
                                    identity_state=identity_state)
        session.add(identity)
        await session.commit()
    return user, identity


@pytest_asyncio.fixture(loop_scope="module")
async def quota_grant(_db_transaction, linked_firebase_identity):
    """One effective grant plus its usage row for the seeded caller; without it a quota route answers 429."""
    user, _ = linked_firebase_identity
    return await seed_grant(_db_transaction, user_id=user.id)


@pytest_asyncio.fixture(loop_scope="module")
async def own_chat(_db_transaction, linked_firebase_identity) -> UUID:
    """A chat owned by the seeded caller, written directly because POST /chats is itself quota-checked."""
    user, _ = linked_firebase_identity
    chat_id = uuid4()
    async with _db_transaction() as session:
        chat = Chat(id=chat_id, user_id=user.id, title="seeded for a quota refusal case")
        chat.messages.append(Message(chat_id=chat_id, role=ChatRole.human,
                                     content={"mode": "analyze", "phrase": "seeded"}))
        chat.messages.append(Message(chat_id=chat_id, role=ChatRole.ai,
                                     content={"resolved_mode": "analyze", "response": "seeded",
                                              "issues": [], "suggestions": []}))
        session.add(chat)
        await session.commit()
    return chat_id


async def seed_grant(factory, *,
                     user_id: UUID,
                     tier_id: str = REGISTERED_TIER_ID,
                     source: AccessGrantSource = AccessGrantSource.manual,
                     status: AccessGrantStatus = AccessGrantStatus.active,
                     monthly_period: str | None = None,
                     monthly_used: int = 0,
                     starts_at: datetime | None = None,
                     ends_at: datetime | None = None,
                     with_usage: bool = True):
    """Insert a core.access_grants row and its core.user_monthly_usage row; return both."""
    # A grant with no usage row is a 500 rather than a 429, so with_usage=False is only for that case.
    now = datetime.now(UTC)
    async with factory() as session:
        # source defaults to manual: the free sources need an anti-abuse row nothing here can seed.
        grant = AccessGrant(user_id=user_id,
                            tier_id=tier_id,
                            source=source,
                            status=status,
                            starts_at=now if starts_at is None else starts_at,
                            ends_at=ends_at)
        session.add(grant)
        await session.flush()
        usage = None
        if with_usage:
            usage = UserMonthlyUsage(grant_id=grant.id,
                                     monthly_period=monthly_period or now.strftime("%Y-%m"),
                                     monthly_used=monthly_used)
            session.add(usage)
        await session.commit()
    return grant, usage


async def create_chat(factory, issuer: str, subject: str):
    """Insert a chat with a human+AI message pair for (issuer, subject), seeding the pair if absent."""
    async with factory() as session:
        result = await session.exec(select(ExternalIdentity)
                                    .where(ExternalIdentity.issuer == issuer,
                                           ExternalIdentity.subject == subject))
        identity = result.first()
        if identity is None:
            user = User()
            session.add(user)
            await session.flush()
            identity = ExternalIdentity(user_id=user.id,
                                        issuer=issuer,
                                        subject=subject,
                                        provider=IdentityProvider.anonymous)
            session.add(identity)
            await session.flush()

        chat_id = uuid4()
        chat = Chat(id=chat_id, user_id=identity.user_id, title="test phrase")
        human = Message(chat_id=chat_id, role=ChatRole.human,
                        content={"mode": "analyze", "phrase": "test phrase"})
        ai = Message(chat_id=chat_id, role=ChatRole.ai,
                     content={"resolved_mode": "analyze",
                              "response": "test answer",
                              "issues": [], "suggestions": []})
        chat.messages.append(human)
        chat.messages.append(ai)
        session.add(chat)
        await session.commit()
    return chat_id
