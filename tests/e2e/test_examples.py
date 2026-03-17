import pytest


@pytest.mark.db
class TestExamplesEndpoint:
    def test_examples_english(self, real_client):
        response = real_client.get("/examples?lang=en")
        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "en"
        assert isinstance(data["examples"], list)
        assert len(data["examples"]) > 0

    def test_examples_spanish(self, real_client):
        response = real_client.get("/examples?lang=es")
        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "es"
        assert isinstance(data["examples"], list)
