from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import ResilienceConfig
from app.dependencies import get_config, get_db, get_service, get_user_id
from app.errors import register_exception_handlers
from app.resilience import ResiliencePolicy
from app.routers import chats_router, examples_router, health_router, root_router
from app.services import ChatService


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.api_key = "test-api-key"
    config.log_level = "DEBUG"

    config.model.name = "gpt-4o-mini"
    config.model.temperature = 0.3
    config.model.max_tokens = 1000
    config.messages_max_page_size = 100
    return config


@pytest.fixture
def mock_examples():
    return {
        "en": ["I am going to home.", "He do not like it."],
        "es": ["Yo soy va a casa."],
    }


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_chats():
    chats = AsyncMock()
    chats.create_chat_with_messages = AsyncMock()
    chats.load_history = AsyncMock(return_value=[])
    chats.save_messages = AsyncMock()
    chats.list_messages = AsyncMock(return_value=([], None))
    chats.delete_chat = AsyncMock()
    return chats


@pytest.fixture
def client(mock_config, mock_examples, mock_chats, mock_db):
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(chats_router)
    app.include_router(examples_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    mock_llm = MagicMock()
    policy = ResiliencePolicy(ResilienceConfig(pool_size=1,
                                              queue_size=1,
                                              queue_retry_after_seconds=1,
                                              timeout_seconds=1,
                                              retry_max_attempts=1,
                                              retry_backoff_base_seconds=0,
                                              retry_backoff_max_seconds=0,
                                              circuit_breaker_failure_threshold=3,
                                              circuit_breaker_reset_seconds=60))
    service = ChatService(prompt="Test prompt {lang_directive}: {phrase}",
                          examples=mock_examples,
                          llm=mock_llm,
                          policy=policy,
                          history_max_messages=50,
                          chats=mock_chats)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_config] = lambda: mock_config
    app.dependency_overrides[get_user_id] = lambda: "test-user"
    app.dependency_overrides[get_service] = lambda: service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def service_instance(client):
    """The ChatService instance injected via DI overrides."""
    return client.app.dependency_overrides[get_service]()
