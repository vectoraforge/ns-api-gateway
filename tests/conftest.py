import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import prompts_router, root_router
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
def client(mock_config, mock_examples):
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(prompts_router)
    register_exception_handlers(app)

    app.state.config = mock_config

    mock_llm = MagicMock()
    semaphore = asyncio.Semaphore(1)
    app.state.service = AnalysisService(
        prompt="Test prompt for {lang}: {phrase}",
        examples=mock_examples,
        llm=mock_llm,
        semaphore=semaphore,
    )

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
