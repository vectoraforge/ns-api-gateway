from collections.abc import AsyncGenerator
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.chats import Chats
from app.config import ResilienceConfig
from app.dependencies import get_config, get_db, get_service, get_user_id
from app.errors import register_exception_handlers
from app.resilience import ResiliencePolicy
from app.routers import chats_router
from app.services import ChatService
from tests.jwt_helpers import make_token

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/nativespeaker"


@pytest.fixture(scope="module")
def db_engine():
    engine = create_async_engine(TEST_DB_URL, pool_size=2, max_overflow=0)
    yield engine
    engine.sync_engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


def auth_token(user_id: str) -> str:
    """Create a Bearer token for integration tests."""
    return make_token(user_id)


@pytest.fixture
def integration_client(db_session):
    """TestClient wired to real DB session, no LLM."""
    app = FastAPI()
    app.include_router(chats_router)
    register_exception_handlers(app)

    async def override_get_db():
        yield db_session

    mock_config = MagicMock()
    mock_config.messages_max_page_size = 100

    mock_llm = MagicMock()
    policy = ResiliencePolicy(
        ResilienceConfig(
            pool_size=1,
            queue_size=1,
            queue_retry_after_seconds=1,
            timeout_seconds=5,
            retry_max_attempts=1,
            retry_backoff_base_seconds=0,
            retry_backoff_max_seconds=0,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_reset_seconds=60,
        )
    )
    service = ChatService(
        prompt="Test prompt",
        examples={"en": ["example"]},
        llm=mock_llm,
        policy=policy,
        history_max_human_messages=50,
        history_max_assistant_messages=50,
        message_max_chars=4096,
        chats=Chats(),
    )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_config] = lambda: mock_config
    app.dependency_overrides[get_user_id] = lambda: "test-user"
    app.dependency_overrides[get_service] = lambda: service

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


async def create_chat(db_session: AsyncSession, user_id: str) -> UUID:
    """Insert a chat row directly and return its ID."""
    chats = Chats()
    chat_id = uuid4()
    await chats.create_chat(db_session, chat_id, user_id)
    return chat_id


async def cleanup_chat(db_session: AsyncSession, chat_id: UUID) -> None:
    """Delete a chat row (messages cascade via FK)."""
    from app.models import Chat

    chat = await db_session.get(Chat, chat_id)
    if chat:
        await db_session.delete(chat)
        await db_session.commit()
