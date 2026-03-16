from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import ResilienceConfig
from app.database.chats import ChatsDB
from app.api.dependencies import get_chat_service, get_config, get_db, get_user_id
from app.api.errors import register_exception_handlers
from app.resilience import ResiliencePolicy
from app.routers import chats_router, examples_router, health_router, root_router
from app.service import ChatService


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
    db.create = AsyncMock()
    db.save_message = AsyncMock()
    db.get_history = AsyncMock(return_value=(None, []))
    db.get_messages = AsyncMock(return_value=(None, [], None))
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
