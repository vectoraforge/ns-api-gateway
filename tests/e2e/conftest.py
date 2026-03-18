import asyncio
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.api.main import app
from app.config import MainConfig
from app.models import AIContent, Chat, HumanContent, Message, Role

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def _app_config():
    """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
    return MainConfig().app_config


@pytest.fixture(scope="session")
def ensure_tables(_app_config):
    """Create all SQLModel tables (CREATE TABLE IF NOT EXISTS) once per session."""
    async def _create():
        engine = create_async_engine(_app_config.db.url, pool_size=1, max_overflow=0,
                                            connect_args=_app_config.db.connect_args)
        async with engine.begin() as conn:  # type: ignore[arg-type]
            await conn.run_sync(SQLModel.metadata.create_all)
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


@pytest.fixture(scope="module")
def real_client(firebase_token, ensure_tables):
    """TestClient wired to the real app with Firebase auth and lifespan."""
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {firebase_token}"
        yield client


@pytest.fixture(scope="module")
def test_user_id():
    """The Firebase test user's UID -- matches the 'sub' claim in the token."""
    return os.environ["FIREBASE_TEST_USER_ID"]


async def create_chat(factory, user_id: str):
    """Insert a chat with human+AI message pair, return chat_id."""
    chat_id = uuid4()
    chat = Chat(id=chat_id, user_id=user_id, title="test phrase")
    human = Message(chat_id=chat_id, role=Role.human,
                    content=HumanContent(phrase="test phrase"))
    ai = Message(chat_id=chat_id, role=Role.ai,
                 content=AIContent(response="test answer", issues=[], suggestions=[]))
    chat.messages.append(human)
    chat.messages.append(ai)
    async with factory() as session:
        session.add(chat)
        await session.commit()
    return chat_id


async def cleanup_chat(factory, chat_id):
    """Delete a chat row (messages cascade via FK)."""
    async with factory() as session:
        chat = await session.get(Chat, chat_id)
        if chat:
            await session.delete(chat)
            await session.commit()


@pytest_asyncio.fixture
async def test_db_factory(_app_config, ensure_tables):
    """Async session factory for test setup/teardown, independent of app engine."""
    engine = create_async_engine(
        _app_config.db.url, pool_size=1, max_overflow=0,
        connect_args=_app_config.db.connect_args,
    )
    factory = async_sessionmaker(
        engine, class_=SQLModelAsyncSession, expire_on_commit=False,
    )
    yield factory
    await engine.dispose()
