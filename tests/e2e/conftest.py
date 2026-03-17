import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.api.main import app
from app.models import AIContent, Chat, HumanContent, Message, Role

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def firebase_token():
    """Obtain a real Firebase ID token via REST API for the dedicated test user."""
    api_key = os.environ["FIREBASE_API_KEY"]
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


def _db_url() -> str:
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "postgres")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "nativespeaker")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


@pytest.fixture(scope="session")
def ensure_tables():
    """Create all SQLModel tables (CREATE TABLE IF NOT EXISTS) once per session."""
    async def _create():
        engine = create_async_engine(_db_url(), pool_size=1, max_overflow=0)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await engine.dispose()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_create())


@pytest.fixture
async def db_session(ensure_tables):
    engine = create_async_engine(_db_url(), pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def create_chat(session: AsyncSession, user_id: str):
    """Insert a chat with human+AI message pair, return chat_id."""
    chat_id = uuid4()
    chat = Chat(id=chat_id, user_id=user_id, title="test phrase")
    human = Message(chat_id=chat_id, role=Role.human,
                    content=HumanContent(phrase="test phrase"))
    ai = Message(chat_id=chat_id, role=Role.ai,
                 content=AIContent(response="test answer", issues=[], suggestions=[]))
    chat.messages.append(human)
    chat.messages.append(ai)
    session.add(chat)
    await session.commit()
    return chat_id


async def cleanup_chat(session: AsyncSession, chat_id):
    """Delete a chat row (messages cascade via FK)."""
    chat = await session.get(Chat, chat_id)
    if chat:
        await session.delete(chat)
        await session.commit()
