import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.app.main import app
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.models import (
    Chat,
    ChatRole,
    ExternalIdentity,
    IdentityProvider,
    Message,
    User,
)


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
def test_user_id():
    """The Firebase test user's UID -- matches the 'sub' claim in the token."""
    return os.environ["FIREBASE_TEST_USER_ID"]


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _db_transaction(_app_lifespan):
    """Wrap each test in a transaction that rolls back on completion."""
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


async def create_chat(factory, issuer: str, subject: str):
    """Insert a chat with a human+AI message pair for `(issuer, subject)`; return chat_id.

    Seeds `core.users` and its matching `core.external_identities` row when the pair has none.
    The v1.6 version looked a user up by `jwt_sub` and inserted `User(jwt_sub=...)`; v2.0 dropped
    that column, and `(issuer, subject)` -- the table's auth-time lookup key -- is where an
    external subject lives now, so the pair is what identifies a seeded caller here too.

    This is **test seeding only**, and deliberately not a JIT-provisioning path: no route can
    reach it, and `src/` has no code that writes either table. `core.users` rows originate from
    `POST /auth/create-user` in Phase 37.

    The identity is seeded `anonymous` with a NULL `provider_uid` -- the left arm of the table's
    provider/provider_uid agreement CHECK, and the only shape available without inventing the
    sentinel `provider_uid` ruling 9.2 forbids. Plan 06's `seed_identity` owns provider variation
    and the barrier-resolvable case.
    """
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
