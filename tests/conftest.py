import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers import prompts_router, chats_router, root_router
from app.errors import register_exception_handlers
from app.services import AnalysisService


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.api_key = "test-api-key"
    config.log_level = "DEBUG"
    config.pool_size = 2
    config.model.name = "gpt-4o-mini"
    config.model.temperature = 0.3
    config.model.max_tokens = 1000
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
    chats.create_chat = AsyncMock()
    chats.get_chat = AsyncMock(return_value=None)
    chats.load_history = AsyncMock(return_value=[])
    chats.save_messages = AsyncMock()
    return chats


@pytest.fixture
def client(mock_config, mock_examples, mock_chats, mock_db):
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(prompts_router)
    app.include_router(chats_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: mock_db

    app.state.config = mock_config

    mock_llm = MagicMock()
    semaphore = asyncio.Semaphore(1)
    app.state.service = AnalysisService(
        prompt="Test prompt for {lang}: {phrase}",
        examples=mock_examples,
        llm=mock_llm,
        semaphore=semaphore,
        chats=mock_chats,
    )

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
