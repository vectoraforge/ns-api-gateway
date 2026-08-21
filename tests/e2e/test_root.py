"""`GET /` is an authenticated route (§8.1), so it serves only an admitted caller.

Since plan 06 the barrier resolves identity, and the real Firebase credential `async_client`
carries has no `core.external_identities` row of its own -- so this route now needs the pair
seeded before it can be reached. `linked_firebase_identity` does exactly that, inside the
per-test transaction, and rolls back with it.
"""
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
