import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestExamplesEndpoint:
    async def test_examples_english(self, async_client):
        response = await async_client.get("/examples?lang=en")
        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "en"
        assert isinstance(data["examples"], list)
        assert len(data["examples"]) > 0

    async def test_examples_spanish(self, async_client):
        response = await async_client.get("/examples?lang=es")
        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "es"
        assert isinstance(data["examples"], list)
