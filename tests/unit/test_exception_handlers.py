import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from unittest.mock import AsyncMock, MagicMock, patch

from nativespeaker.api.app.dependencies import get_current_user, get_db
from nativespeaker.api.models import User
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.exceptions import (
    AuthenticationError,
    ChatHistoryLimitError,
    CircuitOpenError,
    DatabaseNotInitializedError,
    InvalidChatError,
    InvalidCursorError,
    PageSizeLimitError,
    PermanentLLMError,
    QueueFullError,
    TransientLLMError,
    UnsupportedLanguageError,
)
from unit.conftest import make_test_verifier, make_token

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
        "unauthorized",
        "not_found",
        "service_unavailable",
        "internal_error",
    }


def test_validation_error_handler(handler_client):
    response = handler_client.post("/validate-body", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"


@pytest.fixture(scope="module")
def dep_client():
    mock_user = User(jwt_sub="u1", email="u1@example.com", name="User 1")
    mock_db = MagicMock()

    app = FastAPI()
    register_exception_handlers(app)
    app.state.verifier = make_test_verifier()
    app.dependency_overrides[get_db] = lambda: mock_db

    @app.get("/protected")
    async def _protected(user: User = Depends(get_current_user)):
        return {"user_id": str(user.id)}

    with patch("app.app.dependencies.UserService") as mock_user_svc_cls:
        mock_user_svc_cls.return_value.get_or_create = AsyncMock(return_value=mock_user)
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


def test_missing_auth_header_returns_401(dep_client):
    response = dep_client.get("/protected")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "unauthorized"


def test_invalid_bearer_token_returns_401(dep_client):
    response = dep_client.get("/protected", headers={"Authorization": "Bearer notajwt"})
    assert response.status_code == 401


def test_valid_bearer_token_resolves_user(dep_client):
    token = make_token("u1")
    response = dep_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert "user_id" in body


def test_expired_token_returns_401(dep_client):
    token = make_token("u1", exp=1)
    response = dep_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "unauthorized"


@pytest.fixture(scope="module")
def state_client():
    """Confirms verifier is resolved from app.state -- swapping it changes behavior."""
    from nativespeaker.api.auth import UserIdentity

    mock_user = User(jwt_sub="hardcoded-user", email="hw@example.com", name="Hardcoded")
    mock_db = MagicMock()

    class _AlwaysUser:
        def verify(self, token: str) -> UserIdentity:
            return UserIdentity(sub="hardcoded-user", email="hw@example.com",
                                name="Hardcoded")

    app = FastAPI()
    register_exception_handlers(app)
    app.state.verifier = _AlwaysUser()
    app.dependency_overrides[get_db] = lambda: mock_db

    @app.get("/whoami")
    async def _whoami(user: User = Depends(get_current_user)):
        return {"user_id": user.jwt_sub}

    with patch("app.app.dependencies.UserService") as mock_user_svc_cls:
        mock_user_svc_cls.return_value.get_or_create = AsyncMock(return_value=mock_user)
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


def test_verifier_swappable_via_state(state_client):
    """Any token resolves to hardcoded-user -- proves verifier comes from app.state."""
    response = state_client.get("/whoami", headers={"Authorization": "Bearer any.token.here"})
    assert response.status_code == 200
    assert response.json()["user_id"] == "hardcoded-user"
