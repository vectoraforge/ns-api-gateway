from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.exceptions import AnalysisError, InvalidChatError, UnsupportedLanguageError
from app.schema import AnalyzeResponse


class TestAnalyzeEndpoint:
    def test_analyze_success(self, client, service_instance):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="I am going to home.",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Test",
        )

        service_instance.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "I am going to home.", "lang": "en"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "I am going to home."
        assert data["lang"] == "en"
        assert data["chat_id"] == str(chat_id)

    def test_analyze_default_language(self, client, service_instance, mock_db):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Test phrase",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Good",
        )

        service_instance.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test phrase"},
        )

        assert response.status_code == 200
        service_instance.analyze.assert_called_once_with(mock_db, "Test phrase", "en", "test-user", None)

    def test_analyze_with_chat_id(self, client, service_instance, mock_db):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Follow up",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Good",
        )

        service_instance.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "Follow up", "chat_id": str(chat_id)},
        )

        assert response.status_code == 200
        service_instance.analyze.assert_called_once_with(mock_db, "Follow up", "en", "test-user", chat_id)

    def test_analyze_unsupported_language(self, client, service_instance):
        service_instance.analyze = AsyncMock(side_effect=UnsupportedLanguageError("fr", ["en", "es"]))

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test", "lang": "fr"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_analyze_invalid_chat(self, client, service_instance):
        chat_id = uuid4()
        service_instance.analyze = AsyncMock(side_effect=InvalidChatError(chat_id))

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test", "chat_id": str(chat_id)},
        )

        assert response.status_code == 404

    def test_analyze_service_error(self, client, service_instance):
        service_instance.analyze = AsyncMock(side_effect=AnalysisError("LLM failed"))

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test", "lang": "en"},
        )

        assert response.status_code == 500
        assert response.json()["code"] == "internal_error"

    def test_analyze_missing_text(self, client):
        response = client.post(
            "/prompts/analyze",
            json={"lang": "en"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_analyze_empty_text(self, client, service_instance):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Empty",
        )

        service_instance.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "", "lang": "en"},
        )

        assert response.status_code == 200

    def test_analyze_spanish(self, client, service_instance):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Yo soy va a casa.",
            lang="es",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Test",
        )

        service_instance.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "Yo soy va a casa.", "lang": "es"},
        )

        assert response.status_code == 200
        assert response.json()["lang"] == "es"


class TestChatEndpoint:
    def test_chat_message_success(self, client, service_instance):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Why is that wrong?",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Looks good",
        )

        service_instance.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            f"/chats/{chat_id}/messages",
            json={"text": "Why is that wrong?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == str(chat_id)
        assert data["text"] == "Why is that wrong?"
        assert data["lang"] == "en"

    def test_chat_invalid_id(self, client, service_instance):
        chat_id = uuid4()
        service_instance.chat = AsyncMock(side_effect=InvalidChatError(chat_id))

        response = client.post(
            f"/chats/{chat_id}/messages",
            json={"text": "Hello"},
        )

        assert response.status_code == 404

    def test_chat_missing_text(self, client):
        chat_id = uuid4()

        response = client.post(
            f"/chats/{chat_id}/messages",
            json={},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"


class TestExamplesEndpoint:
    def test_examples_success(self, client):
        response = client.get("/prompts/examples?lang=en")

        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "en"
        assert isinstance(data["examples"], list)
        assert len(data["examples"]) > 0

    def test_examples_spanish(self, client):
        response = client.get("/prompts/examples?lang=es")

        assert response.status_code == 200
        data = response.json()
        assert data["lang"] == "es"

    def test_examples_unsupported_language(self, client, service_instance):
        service_instance.get_examples = MagicMock(side_effect=UnsupportedLanguageError("fr", ["en", "es"]))

        response = client.get("/prompts/examples?lang=fr")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_examples_missing_lang_param(self, client):
        response = client.get("/prompts/examples")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"
