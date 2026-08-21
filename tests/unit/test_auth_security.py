from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import nativespeaker.api.app.dependencies as deps_module
from nativespeaker.api.app.dependencies import get_current_user, get_db
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.errors import AuthenticationError
from nativespeaker.api.models import User
from nativespeaker.api.routers import chats_router, users_router
from unit.conftest import make_test_verifier, make_token


@pytest.fixture(scope="module")
def dep_client():
    """Client with real auth dependency chain for testing Bearer token edge cases."""
    mock_user = User(jwt_sub="u1", email="u1@example.com", name="User 1")
    mock_db = MagicMock()

    app = FastAPI()
    register_exception_handlers(app)
    app.state.jwt_verifier = make_test_verifier()
    app.dependency_overrides[get_db] = lambda: mock_db

    @app.get("/protected")
    async def _protected(user: User = Depends(get_current_user)):
        return {"user_id": str(user.id)}

    with patch.object(deps_module, "UserService") as mock_user_svc_cls:
        mock_user_svc_cls.return_value.get_or_create = AsyncMock(return_value=mock_user)
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


class TestBearerTokenEdgeCases:
    """Auth edge case tests for Bearer token malformation."""

    def test_bearer_with_only_whitespace(self, dep_client):
        """Header 'Bearer    ' (only spaces) returns 401 after strip."""
        response = dep_client.get("/protected",
                                  headers={"Authorization": "Bearer    "})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_non_bearer_auth_scheme(self, dep_client):
        """Basic auth scheme is rejected -- only Bearer accepted."""
        response = dep_client.get("/protected",
                                  headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_bearer_prefix_no_space(self, dep_client):
        """'Bearertoken123' without space after Bearer is rejected."""
        response = dep_client.get("/protected",
                                  headers={"Authorization": "Bearertoken123"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_empty_authorization_header(self, dep_client):
        """Empty Authorization header returns 401."""
        response = dep_client.get("/protected",
                                  headers={"Authorization": ""})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_bearer_lowercase_rejected(self, dep_client):
        """Lowercase 'bearer' is rejected -- case-sensitive check."""
        response = dep_client.get("/protected",
                                  headers={"Authorization": "bearer " + make_token()})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"


class TestInactiveUserBlocking:
    """Verify inactive users are blocked across protected endpoints."""

    @pytest.fixture()
    def inactive_client(self):
        """Client where get_current_user always raises AuthenticationError."""
        mock_config = MagicMock()
        mock_config.quotas = {}

        app = FastAPI()
        app.include_router(chats_router)
        app.include_router(users_router)
        register_exception_handlers(app)

        async def _raise_inactive():
            raise AuthenticationError("Authentication failed")

        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_current_user] = _raise_inactive

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    def test_inactive_user_blocked_on_chats(self, inactive_client):
        """Inactive user gets 401 on POST /chats."""
        response = inactive_client.post("/chats", json={"phrase": "hello", "lang": "en"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_inactive_user_blocked_on_users_me(self, inactive_client):
        """Inactive user gets 401 on GET /users/me."""
        response = inactive_client.get("/users/me")
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"
