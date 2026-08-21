from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import nativespeaker.api.routers.users as users_module
from nativespeaker.api.app.dependencies import get_config, get_current_user, get_db
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth import UserIdentity
from nativespeaker.api.models import SubscriptionPlan, User
from nativespeaker.api.routers import users_router

TEST_QUOTAS = {SubscriptionPlan.free: 10,
               SubscriptionPlan.silver: 50,
               SubscriptionPlan.gold: 200,
               SubscriptionPlan.platinum: 1000}


class TestGetUsersMe:
    """USER-02: User can retrieve their profile via GET /users/me"""

    def test_returns_profile(self, client):
        response = client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
        assert data["subscription_plan"] == "free"
        assert "created_at" in data

    def test_profile_excludes_internal_id(self, client):
        """USER-04: Internal id must not be exposed."""
        response = client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert "id" not in data
        assert "jwt_sub" not in data
        assert "active" not in data

    def test_profile_nullable_name(self):
        """Name can be None for Firebase accounts without name claim."""
        nameless_user = User(
            jwt_sub="nameless-user",
            email="nameless@example.com",
            name=None,
            subscription_plan=SubscriptionPlan.free,
            active=True,
        )

        with patch.object(users_module, "UsageDB") as MockUsageDB:
            mock_instance = MagicMock()
            mock_instance.get_usage = AsyncMock(return_value=0)
            MockUsageDB.return_value = mock_instance

            mock_config = MagicMock()
            mock_config.quotas = TEST_QUOTAS

            app = FastAPI()
            app.include_router(users_router)
            register_exception_handlers(app)
            app.dependency_overrides[get_current_user] = lambda: nameless_user
            app.dependency_overrides[get_db] = lambda: MagicMock()
            app.dependency_overrides[get_config] = lambda: mock_config

            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.get("/users/me")
                assert response.status_code == 200
                data = response.json()
                assert data["name"] is None
                assert data["email"] == "nameless@example.com"


class TestInactiveUser:
    """USER-04: Inactive users get opaque 401."""

    def test_inactive_user_rejected(self):
        """Inactive user receives the same 401 as invalid token -- no 'inactive' message."""
        from nativespeaker.api.errors import AuthenticationError

        async def mock_get_current_user():
            raise AuthenticationError("Authentication failed")

        app = FastAPI()
        app.include_router(users_router)
        register_exception_handlers(app)
        app.dependency_overrides[get_current_user] = mock_get_current_user

        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/users/me")
            assert response.status_code == 401
            data = response.json()
            assert data["code"] == "auth_required"
            # Must NOT reveal "inactive" or "deactivated" in any response field
            assert "inactive" not in str(data).lower()
            assert "deactivated" not in str(data).lower()


class TestUserIdentity:
    """USER-01: UserIdentity extracted from JWT claims."""

    def test_user_identity_fields(self):
        identity = UserIdentity(sub="abc123", email="test@example.com", name="Test")
        assert identity.sub == "abc123"
        assert identity.email == "test@example.com"
        assert identity.name == "Test"

    def test_user_identity_name_optional(self):
        identity = UserIdentity(sub="abc123", email="test@example.com")
        assert identity.name is None

    def test_user_identity_frozen(self):
        identity = UserIdentity(sub="abc123", email="test@example.com")
        with pytest.raises(AttributeError):
            identity.sub = "changed"  # type: ignore[misc]


class TestUserModel:
    """USER-01: User model defaults and constraints."""

    def test_default_plan_is_free(self):
        user = User(jwt_sub="test", email="test@example.com")
        assert user.subscription_plan == SubscriptionPlan.free

    def test_default_active_is_true(self):
        user = User(jwt_sub="test", email="test@example.com")
        assert user.active is True

    def test_uuid7_id_generated(self):
        user = User(jwt_sub="test", email="test@example.com")
        assert user.id is not None

    def test_subscription_plan_values(self):
        assert list(SubscriptionPlan) == [SubscriptionPlan.free, SubscriptionPlan.silver,
                                          SubscriptionPlan.gold, SubscriptionPlan.platinum]


class TestUserIsolation:
    """USER-04: Users cannot access other users' data."""

    def test_users_me_only_returns_own_profile(self, client):
        """GET /users/me always returns the authenticated user's profile."""
        response = client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        # The profile returned matches TEST_USER, not any other user
        assert data["email"] == "test@example.com"

    def test_no_user_id_path_param(self, client):
        """There is no GET /users/{id} endpoint -- only /users/me."""
        response = client.get("/users/some-other-id")
        assert response.status_code in (404, 405)


class TestUsersMeUsage:
    """ENVOY-05: GET /users/me returns usage data."""

    def test_response_includes_usage_fields(self, client):
        """Response includes requests_used, monthly_limit, resets_at."""
        response = client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert "requests_used" in data
        assert "monthly_limit" in data
        assert "resets_at" in data
        assert data["requests_used"] == 0
        assert data["monthly_limit"] == 10

    def test_resets_at_is_first_of_next_month(self, client):
        """resets_at is the first day of the next calendar month."""
        response = client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        resets_at = data["resets_at"]
        assert "T00:00:00" in resets_at
        from datetime import datetime
        dt = datetime.fromisoformat(resets_at)
        assert dt.day == 1
