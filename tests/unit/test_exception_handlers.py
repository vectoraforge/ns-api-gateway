import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.errors import (
    AuthenticationError,
    ChatHistoryLimitError,
    CircuitOpenError,
    DatabaseNotInitializedError,
    InvalidChatError,
    InvalidCursorError,
    OutOfScopeError,
    PageSizeLimitError,
    PermanentLLMError,
    QueueFullError,
    TransientLLMError,
    UnsupportedLanguageError,
)

CASES = [
    ("missing_token", AuthenticationError("Missing Bearer token"), 401),
    ("invalid_token", AuthenticationError("Invalid token"), 401),
    ("expired_token", AuthenticationError("Expired token"), 401),
    ("db_not_init", DatabaseNotInitializedError(), 500),
    ("unsupported_lang", UnsupportedLanguageError("fr", ["en"]), 400),
    ("invalid_chat", InvalidChatError("xyz"), 404),
    ("invalid_cursor", InvalidCursorError(), 400),
    ("page_size_limit", PageSizeLimitError(100), 400),
    ("queue_full", QueueFullError(30), 503),
    ("circuit_open", CircuitOpenError(60), 503),
    ("history_limit", ChatHistoryLimitError(max_messages=50), 400),
    ("out_of_scope", OutOfScopeError(), 400),
    ("generic_exception", Exception("boom"), 500),
    ("starlette_http", StarletteHTTPException(status_code=404, detail="not found"), 404),
    ("transient_llm", TransientLLMError("upstream timeout"), 503),
    ("permanent_llm", PermanentLLMError("bad response format"), 503),
]


class _Body(BaseModel):
    required_field: str


def _make_raise_route(exc: Exception):
    async def _route():
        raise exc

    return _route


@pytest.fixture(scope="module")
def handler_client():
    app = FastAPI()
    register_exception_handlers(app)

    for name, exc, _ in CASES:
        app.add_api_route(f"/raise/{name}", _make_raise_route(exc), methods=["GET"])

    @app.post("/validate-body")
    async def _validate_route(body: _Body):
        return body

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("name,exc,expected_status", CASES)
def test_handler(handler_client, name, exc, expected_status):
    response = handler_client.get(f"/raise/{name}")
    assert response.status_code == expected_status
    body = response.json()
    assert list(body.keys()) == ["code"], f"Expected only 'code' key, got {list(body.keys())}"
    assert body["code"] in {
        "invalid_request",
        "auth_required",
        "not_found",
        "service_unavailable",
        "internal_error",
        "out_of_scope",
    }


def test_validation_error_handler(handler_client):
    response = handler_client.post("/validate-body", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"


# The token-verification and missing-header cases live in test_jwt_security.py and test_auth_security.py.


class TestRetryAfterHeaders:
    """Verify Retry-After header on 503 errors."""

    def test_queue_full_has_retry_after(self, handler_client):
        """QueueFullError(30) response includes Retry-After: 30."""
        response = handler_client.get("/raise/queue_full")
        assert response.status_code == 503
        assert response.headers.get("retry-after") == "30"

    def test_circuit_open_has_retry_after(self, handler_client):
        """CircuitOpenError(60) response includes Retry-After: 60."""
        response = handler_client.get("/raise/circuit_open")
        assert response.status_code == 503
        assert response.headers.get("retry-after") == "60"

    def test_transient_llm_no_retry_after(self, handler_client):
        """TransientLLMError does NOT include Retry-After (no extra_headers on base)."""
        response = handler_client.get("/raise/transient_llm")
        assert response.status_code == 503
        assert "retry-after" not in response.headers
