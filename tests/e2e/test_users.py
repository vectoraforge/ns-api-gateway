import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestUserProfile:
    async def test_get_user_profile_returns_200(self, async_client):
        """GET /users/me returns 200 with all expected profile fields."""
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "name" in data
        assert "subscription_plan" in data
        assert "created_at" in data
        assert "requests_used" in data
        assert "monthly_limit" in data
        assert "resets_at" in data

    async def test_profile_excludes_internal_fields(self, async_client):
        """Internal database fields must NOT be exposed in the profile response."""
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert "id" not in data
        assert "jwt_sub" not in data
        assert "active" not in data

    async def test_subscription_plan_is_valid_enum(self, async_client):
        """subscription_plan is one of the valid SubscriptionPlan values."""
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["subscription_plan"] in ("free", "silver", "gold", "platinum")

    async def test_resets_at_is_first_of_month(self, async_client):
        """resets_at is the first day of the next calendar month at 00:00:00."""
        from datetime import datetime
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        dt = datetime.fromisoformat(data["resets_at"])
        assert dt.day == 1
        assert "T00:00:00" in data["resets_at"]

    async def test_requests_used_is_non_negative_integer(self, async_client):
        """requests_used must be a non-negative integer."""
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["requests_used"], int)
        assert data["requests_used"] >= 0

    async def test_monthly_limit_is_positive_integer(self, async_client):
        """monthly_limit must be a positive integer."""
        response = await async_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["monthly_limit"], int)
        assert data["monthly_limit"] > 0
