import pytest


@pytest.mark.llm
class TestRealLLM:

    @pytest.fixture
    def real_client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            yield client

    def test_analyze_real_phrase_english(self, real_client):
        response = real_client.post(
            "/prompts/analyze",
            json={
                "phrase": "I am going to home.",
                "lang": "en"
            }
        )

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["phrase"] == "I am going to home."
        assert data["lang"] == "en"
        assert "issues" in data
        assert "alternatives" in data
        assert "assessment" in data

        assert len(data["issues"]) > 0 or len(data["alternatives"]) > 0

    def test_analyze_real_phrase_spanish(self, real_client):
        response = real_client.post(
            "/prompts/analyze",
            json={
                "phrase": "Yo soy va a casa.",
                "lang": "es"
            }
        )

        assert response.status_code == 200, response.text
        data = response.json()

        assert data["lang"] == "es"
        assert "issues" in data
        assert "alternatives" in data

    def test_analyze_correct_phrase(self, real_client):
        response = real_client.post(
            "/prompts/analyze",
            json={
                "phrase": "I am going home.",
                "lang": "en"
            }
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert "assessment" in data

    def test_root_with_real_config(self, real_client):
        response = real_client.get("/")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["name"] == "SpeakNative API Gateway"
