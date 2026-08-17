from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import get_current_user, get_db
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.exceptions import AuthenticationError
from nativespeaker.api.routers import chats_router, users_router
from unit.conftest import make_token
from unit.test_auth_barrier import FakeResolver, build_app, make_writer


@pytest.fixture(scope="module")
def dep_client():
    """A client behind the shared pre-handler barrier. Bearer acceptance lives there and
    nowhere else, so these edge cases are exercised against the only implementation of it."""
    app = build_app([("GET", "/protected")], resolver=FakeResolver(), writer=make_writer())
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

    def test_a_second_authorization_header_is_rejected(self, dep_client):
        """The header is the sole identity carrier: exactly one field, never two."""
        token = make_token()
        response = dep_client.get(
            "/protected",
            headers=[("Authorization", f"Bearer {token}"), ("Authorization", f"Bearer {token}")])
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_a_verified_token_reaches_the_handler(self, dep_client):
        """The barrier hands the handler its typed verified identity context."""
        response = dep_client.get("/protected",
                                  headers={"Authorization": f"Bearer {make_token('u1')}"})
        assert response.status_code == 200
        assert response.json()["subject"] == "u1"


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
        assert response.json()["code"] == "unauthorized"

    def test_inactive_user_blocked_on_users_me(self, inactive_client):
        """Inactive user gets 401 on GET /users/me."""
        response = inactive_client.get("/users/me")
        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"
