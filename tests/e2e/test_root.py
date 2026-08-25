"""GET / is authenticated, and the test credential has no identity row, so each case seeds the link first."""
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestRootEndpoint:
    async def test_root_returns_app_info(self, async_client, linked_firebase_identity):
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "NativeSpeaker API Gateway"
        assert "version" in data
        assert isinstance(data["supported_languages"], list)
        assert len(data["supported_languages"]) > 0
