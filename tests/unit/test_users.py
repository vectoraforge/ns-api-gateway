from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import nativespeaker.api.routers.users as users_module
from nativespeaker.api.app.dependencies import (
    get_current_user,
    get_db,
    get_identity_context,
)
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth import UserIdentity
from nativespeaker.api.models import SubscriptionPlan, User
from nativespeaker.api.routers import users_router
from unit.conftest import TEST_GRANT, TEST_IDENTITY, store_tokens_db


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
            email="nameless@example.com",
            display_name=None,
            active=True,
        )

        with (patch.object(users_module, "UsageDB") as MockUsageDB,
              patch.object(users_module, "GrantsDB") as MockGrantsDB,
              patch.object(users_module, "StorePurchaseTokensDB",
                           return_value=store_tokens_db())):
            mock_instance = MagicMock()
            mock_instance.get_usage = AsyncMock(return_value=0)
            MockUsageDB.return_value = mock_instance
            grants = MagicMock()
            grants.effective_grant = AsyncMock(return_value=TEST_GRANT)
            MockGrantsDB.return_value = grants

            app = FastAPI()
            app.include_router(users_router)
            register_exception_handlers(app)
            app.dependency_overrides[get_current_user] = lambda: nameless_user
            app.dependency_overrides[get_identity_context] = lambda: replace(
                TEST_IDENTITY, user_id=nameless_user.id)
            app.dependency_overrides[get_db] = lambda: MagicMock()

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
        from nativespeaker.api.exceptions import AuthenticationError

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
            assert data["code"] == "unauthorized"
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


def _table(name: str):
    """The mapped table, read from the shipped SQLModel metadata."""
    from sqlmodel import SQLModel
    return SQLModel.metadata.tables[name]


class TestUserModel:
    """USER-01: User model defaults and constraints."""

    def test_no_plan_free_access_or_tier_column_is_stored_on_the_user(self):
        # Subscription plan, free access and tier are not `core.users` columns: access is the
        # state of the user's `core.access_grants` rows.
        # [utest->req~schema-users-no-plan-fields~1]
        columns = {column.name for column in _table("core.users").columns}
        assert columns == {"id", "email", "display_name", "registered_at", "active",
                           "created_at", "updated_at"}
        for forbidden in ("subscription_plan", "plan", "tier", "tier_id", "free_access"):
            assert forbidden not in columns

    def test_monthly_usage_is_keyed_by_the_grant_that_authorizes_it(self):
        # [utest->req~schema-users-usage-via-user-monthly-usage~1]
        usage = _table("core.user_monthly_usage")
        columns = {column.name for column in usage.columns}
        assert "user_id" not in columns
        grant_id = usage.columns["grant_id"]
        assert grant_id.primary_key
        assert {fk.target_fullname for fk in grant_id.foreign_keys} == {"core.access_grants.id"}

    def test_default_active_is_true(self):
        user = User(email="test@example.com")
        assert user.active is True

    def test_uuid7_id_generated(self):
        user = User(email="test@example.com")
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
