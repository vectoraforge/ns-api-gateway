import asyncio
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.app.main import app
from nativespeaker.api.config import MainConfig
from nativespeaker.api.models import AIContent, Chat, HumanContent, Message, Role, User


@pytest.fixture(scope="session")
def _app_config():
    """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
    return MainConfig().app_config


@pytest.fixture(scope="session")
def ensure_tables(_app_config):
    """Create all SQLModel tables and seed plans data once per session."""
    async def _create():
        engine = create_async_engine(_app_config.db.url, pool_size=1, max_overflow=0)
        async with engine.begin() as conn:  # type: ignore[arg-type]
            await conn.run_sync(SQLModel.metadata.create_all)
            await conn.execute(text(
                "INSERT INTO plans (tier, monthly_quota) VALUES "
                "('free', 150), ('silver', 1500), ('gold', 3000), ('platinum', 30000) "
                "ON CONFLICT (tier) DO NOTHING"
            ))
        await engine.dispose()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_create())


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
async def _app_lifespan(ensure_tables):
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


async def create_chat(factory, user_id: str):
    """Insert a chat with human+AI message pair, return chat_id.

    Creates a User record for the given Firebase UID if one doesn't exist,
    then creates a Chat referencing the user's UUID primary key.
    """
    async with factory() as session:
        # Ensure user exists (JIT-like provisioning for test data)
        from sqlmodel import select
        result = await session.exec(select(User).where(User.jwt_sub == user_id))
        user = result.first()
        if user is None:
            user = User(jwt_sub=user_id, email=f"{user_id}@test.example.com")
            session.add(user)
            await session.flush()

        chat_id = uuid4()
        chat = Chat(id=chat_id, user_id=user.id, title="test phrase")
        human = Message(chat_id=chat_id, role=Role.human,
                        content=HumanContent(phrase="test phrase"))
        ai = Message(chat_id=chat_id, role=Role.ai,
                     content=AIContent(response="test answer", issues=[], suggestions=[]))
        chat.messages.append(human)
        chat.messages.append(ai)
        session.add(chat)
        await session.commit()
    return chat_id
