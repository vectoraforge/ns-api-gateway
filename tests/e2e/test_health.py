import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestHealthEndpoint:
    async def test_health_ready_returns_up(self, async_client):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "up"}
