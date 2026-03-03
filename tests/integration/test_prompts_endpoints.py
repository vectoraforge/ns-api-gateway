from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.exceptions import AnalysisError, InvalidChatError, UnsupportedLanguageError
from app.schema import ChatResponse


class TestPostChatsEndpoint:
    def test_create_chat_success(self, client, service_instance):
        chat_id = uuid4()
        mock_response = ChatResponse(
            text="I am going to home.",
            chat_id=chat_id,
            issues=[],
            suggestions=[],
            response="Test",
        )

        service_instance.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            "/chats",
            json={"text": "I am going to home.", "lang": "en"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "I am going to home."
        assert data["chat_id"] == str(chat_id)

    def test_missing_lang_returns_400(self, client):
        response = client.post("/chats", json={"text": "Test phrase"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_with_chat_id(self, client, service_instance, mock_db):
        chat_id = uuid4()
        mock_response = ChatResponse(
            text="Follow up",
            chat_id=chat_id,
            issues=[],
            suggestions=[],
            response="Good",
        )

        service_instance.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            "/chats",
            json={"text": "Follow up", "chat_id": str(chat_id)},
        )

        assert response.status_code == 200
        service_instance.chat.assert_called_once_with(mock_db, "Follow up", "test-user", lang=None, chat_id=chat_id)

    def test_unsupported_language(self, client, service_instance):
        service_instance.chat = AsyncMock(side_effect=UnsupportedLanguageError("fr", ["en", "es"]))

        response = client.post(
            "/chats",
            json={"text": "Test", "lang": "fr"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_invalid_chat(self, client, service_instance):
        chat_id = uuid4()
        service_instance.chat = AsyncMock(side_effect=InvalidChatError(chat_id))

        response = client.post(
            "/chats",
            json={"text": "Test", "chat_id": str(chat_id)},
        )

        assert response.status_code == 404

    def test_service_error(self, client, service_instance):
        service_instance.chat = AsyncMock(side_effect=AnalysisError("LLM failed"))

        response = client.post(
            "/chats",
            json={"text": "Test", "lang": "en"},
        )

        assert response.status_code == 500
        assert response.json()["code"] == "internal_error"

    def test_missing_text(self, client):
        response = client.post(
            "/chats",
            json={"lang": "en"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_empty_text(self, client, service_instance):
        chat_id = uuid4()
        mock_response = ChatResponse(
            text="",
            chat_id=chat_id,
            issues=[],
            suggestions=[],
            response="Empty",
        )

        service_instance.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            "/chats",
            json={"text": "", "lang": "en"},
        )

        assert response.status_code == 200

    def test_spanish(self, client, service_instance):
        chat_id = uuid4()
        mock_response = ChatResponse(
            text="Yo soy va a casa.",
            chat_id=chat_id,
            issues=[],
            suggestions=[],
            response="Test",
        )

        service_instance.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            "/chats",
            json={"text": "Yo soy va a casa.", "lang": "es"},
        )

        assert response.status_code == 200

    def test_continuation_success(self, client, service_instance):
        chat_id = uuid4()
        mock_response = ChatResponse(
            text="Why is that wrong?",
            chat_id=chat_id,
            issues=[],
            suggestions=[],
            response="Looks good",
        )
        service_instance.chat = AsyncMock(return_value=mock_response)
        response = client.post("/chats", json={"text": "Why is that wrong?", "chat_id": str(chat_id)})
        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == str(chat_id)
        assert data["text"] == "Why is that wrong?"
        assert "suggestions" in data
        assert "response" in data


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
        service_instance.get_examples = MagicMock(side_effect=UnsupportedLanguageError("fr", ["en", "es"]))

        response = client.get("/examples?lang=fr")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_examples_missing_lang_param(self, client):
        response = client.get("/examples")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"


class TestRemovedRoutes:
    def test_post_prompts_analyze_returns_404(self, client):
        response = client.post("/prompts/analyze", json={"text": "Test", "lang": "en"})
        assert response.status_code == 404

    def test_post_chat_messages_returns_400(self, client):
        """POST to /chats/{id}/messages returns 400 -- path exists for GET,
        so Starlette returns 405 which remaps to 400 via error contract."""
        chat_id = uuid4()
        response = client.post(f"/chats/{chat_id}/messages", json={"text": "Hello"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_get_prompts_examples_returns_404(self, client):
        response = client.get("/prompts/examples?lang=en")
        assert response.status_code == 404
