from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.exceptions import AnalysisError, InvalidChatError, UnsupportedLanguageError
from app.models import AIContent, Message, Role


class TestPostChatsEndpoint:
    def test_create_chat_success(self, client, service_instance):
        ai_message = Message(chat_id=uuid4(), role=Role.ai,
                             content=AIContent(response="Test", issues=[], suggestions=[]))
        service_instance.create_chat = AsyncMock(return_value=ai_message)

        response = client.post("/chats",
                               json={"phrase": "I am going to home.", "lang": "en"})

        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"
        assert "content" in data

    def test_missing_phrase_returns_400(self, client):
        response = client.post("/chats", json={"lang": "en"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_followup_success(self, client, service_instance):
        chat_id = uuid4()
        ai_message = Message(chat_id=chat_id, role=Role.ai,
                             content=AIContent(response="Good point", issues=[], suggestions=[]))
        service_instance.send_message = AsyncMock(return_value=ai_message)

        response = client.post(f"/chats/{chat_id}",
                               json={"content": "Why is that wrong?"})

        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == str(chat_id)
        assert data["role"] == "ai"

    def test_unsupported_language(self, client, service_instance):
        service_instance.create_chat = AsyncMock(
            side_effect=UnsupportedLanguageError("fr", ["en", "es"]))

        response = client.post("/chats",
                               json={"phrase": "Test", "lang": "fr"})

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_invalid_chat(self, client, service_instance):
        chat_id = uuid4()
        service_instance.send_message = AsyncMock(
            side_effect=InvalidChatError(chat_id))

        response = client.post(f"/chats/{chat_id}",
                               json={"content": "Test"})

        assert response.status_code == 404

    def test_service_error(self, client, service_instance):
        service_instance.create_chat = AsyncMock(
            side_effect=AnalysisError("LLM failed"))

        response = client.post("/chats",
                               json={"phrase": "Test", "lang": "en"})

        assert response.status_code == 500
        assert response.json()["code"] == "internal_error"

    def test_empty_phrase(self, client, service_instance):
        ai_message = Message(chat_id=uuid4(), role=Role.ai,
                             content=AIContent(response="Empty", issues=[], suggestions=[]))
        service_instance.create_chat = AsyncMock(return_value=ai_message)

        response = client.post("/chats",
                               json={"phrase": "", "lang": "en"})

        assert response.status_code == 200

    def test_spanish(self, client, service_instance):
        ai_message = Message(chat_id=uuid4(), role=Role.ai,
                             content=AIContent(response="Test", issues=[], suggestions=[]))
        service_instance.create_chat = AsyncMock(return_value=ai_message)

        response = client.post("/chats",
                               json={"phrase": "Yo soy va a casa.", "lang": "es"})

        assert response.status_code == 200


class TestExamplesEndpoint:
    def test_examples_success(self, client):
        response = client.get("/examples?lang=en")

        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "en"
        assert isinstance(data["examples"], list)
        assert len(data["examples"]) > 0

    def test_examples_spanish(self, client):
        response = client.get("/examples?lang=es")

        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "es"

    def test_examples_unsupported_language(self, client, service_instance):
        service_instance.get_examples = MagicMock(
            side_effect=UnsupportedLanguageError("fr", ["en", "es"]))

        response = client.get("/examples?lang=fr")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_examples_missing_lang_param(self, client):
        response = client.get("/examples")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"


class TestRemovedRoutes:
    def test_post_prompts_analyze_returns_404(self, client):
        response = client.post("/prompts/analyze", json={"phrase": "Test", "lang": "en"})
        assert response.status_code == 404

    def test_get_prompts_examples_returns_404(self, client):
        response = client.get("/prompts/examples?lang=en")
        assert response.status_code == 404
