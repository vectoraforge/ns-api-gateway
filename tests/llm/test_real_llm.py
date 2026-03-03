import base64
import json

import pytest


@pytest.mark.llm
class TestRealLLM:
    @pytest.fixture
    def real_client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8")).rstrip(b"=")
            payload = base64.urlsafe_b64encode(json.dumps({"user_id": "real-user"}).encode("utf-8")).rstrip(b"=")
            token = f"{header.decode('utf-8')}.{payload.decode('utf-8')}.signature"
            client.headers.update({"Authorization": f"Bearer {token}"})
            yield client

    def test_analyze_real_phrase_english(self, real_client):
        response = real_client.post("/chats", json={"text": "I am going to home.", "lang": "en"})

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["text"] == "I am going to home."
        assert "chat_id" in data
        assert "issues" in data
        assert "suggestions" in data
        assert "response" in data

        assert len(data["issues"]) > 0 or len(data["suggestions"]) > 0

    def test_analyze_real_phrase_spanish(self, real_client):
        response = real_client.post("/chats", json={"text": "Yo soy va a casa.", "lang": "es"})

        assert response.status_code == 200, response.text
        data = response.json()

        assert "issues" in data
        assert "suggestions" in data

    def test_analyze_correct_phrase(self, real_client):
        response = real_client.post("/chats", json={"text": "I am going home.", "lang": "en"})

        assert response.status_code == 200, response.text
        data = response.json()
        assert "response" in data

    def test_root_with_real_config(self, real_client):
        response = real_client.get("/")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["name"] == "SpeakNative API Gateway"
