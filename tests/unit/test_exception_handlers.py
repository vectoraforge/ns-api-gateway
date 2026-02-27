import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import register_exception_handlers
from app.exceptions import (
    MissingTokenError,
    InvalidTokenError,
    ExpiredTokenError,
    ChatOwnershipError,
    DatabaseNotInitializedError,
    UnsupportedLanguageError,
    InvalidChatError,
    QueueFullError,
    CircuitOpenError,
    ChatHistoryLimitError,
    MessageTooLargeError,
)

CASES = [
    ("missing_token", MissingTokenError(), 401),
    ("invalid_token", InvalidTokenError(), 401),
    ("expired_token", ExpiredTokenError(), 401),
    ("chat_ownership", ChatOwnershipError("abc"), 404),
    ("db_not_init", DatabaseNotInitializedError(), 500),
    ("unsupported_lang", UnsupportedLanguageError("fr", ["en"]), 400),
    ("invalid_chat", InvalidChatError("xyz"), 404),
    ("queue_full", QueueFullError(30), 503),
    ("circuit_open", CircuitOpenError(60), 503),
    ("history_limit", ChatHistoryLimitError(50, 50), 409),
    ("msg_too_large", MessageTooLargeError("human", 4096), 413),
    ("generic_exception", Exception("boom"), 500),
    ("starlette_http", StarletteHTTPException(status_code=404, detail="not found"), 404),
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
    assert "status" in body
    assert "error" in body
    assert body["status"] == expected_status
    assert isinstance(body["error"], str)
    assert body["error"]


def test_validation_error_handler(handler_client):
    response = handler_client.post("/validate-body", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422
    assert "error" in body
    assert body["error"]


from app.auth import get_user_id


@pytest.fixture(scope="module")
def dep_client():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/protected")
    async def _protected(user_id: str = Depends(get_user_id)):
        return {"user_id": user_id}

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_missing_auth_header_returns_401(dep_client):
    response = dep_client.get("/protected")
    assert response.status_code == 401
    body = response.json()
    assert body["status"] == 401
    assert "error" in body


def test_invalid_bearer_token_returns_401(dep_client):
    response = dep_client.get("/protected", headers={"Authorization": "Bearer notajwt"})
    assert response.status_code == 401


def test_valid_bearer_token_resolves_user(dep_client):
    import base64
    import json
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": "u1"}).encode()).rstrip(b"=").decode()
    token = f"header.{payload}.sig"
    response = dep_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user_id"] == "u1"


def test_expired_token_returns_401(dep_client):
    import base64
    import json
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": "u1", "exp": 1}).encode()).rstrip(b"=").decode()
    token = f"header.{payload}.sig"
    response = dep_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    body = response.json()
    assert body["status"] == 401
    assert "error" in body
