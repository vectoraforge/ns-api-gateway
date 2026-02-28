import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import UnsafeBase64Verifier
from app.config import ResilienceConfig
from app.database import get_db
from app.errors import register_exception_handlers
from app.resilience import ResiliencePolicy
from app.routers import chats_router, health_router, prompts_router, root_router
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
    chats.create_chat = AsyncMock()
    chats.load_history = AsyncMock(return_value=[])
    chats.get_message_counts = AsyncMock(return_value={"human": 0, "assistant": 0})
    chats.save_messages = AsyncMock()
    return chats


def _make_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8")).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": user_id}).encode("utf-8")).rstrip(b"=")
    return f"{header.decode('utf-8')}.{payload.decode('utf-8')}.signature"


@pytest.fixture
def auth_header():
    token = _make_token("test-user")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(mock_config, mock_examples, mock_chats, mock_db, auth_header):
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(prompts_router)
    app.include_router(chats_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: mock_db

    app.state.config = mock_config
    app.state.verifier = UnsafeBase64Verifier()

    mock_llm = MagicMock()
    policy = ResiliencePolicy(
        ResilienceConfig(
            pool_size=1,
            queue_size=1,
            queue_retry_after_seconds=1,
            timeout_seconds=1,
            retry_max_attempts=1,
            retry_backoff_base_seconds=0,
            retry_backoff_max_seconds=0,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_reset_seconds=60,
        )
    )
    app.state.service = AnalysisService(
        prompt="Test prompt for {lang}: {phrase}",
        examples=mock_examples,
        llm=mock_llm,
        policy=policy,
        history_max_human_messages=50,
        history_max_assistant_messages=50,
        message_max_chars=4096,
        chats=mock_chats,
    )

    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.headers.update(auth_header)
        yield test_client
