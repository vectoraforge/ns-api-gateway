from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schema import AnalyzeResponse
from app.exceptions import UnsupportedLanguageError, AnalysisError, InvalidChatError


class TestAnalyzeEndpoint:
    def test_analyze_success(self, client):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="I am going to home.",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Test",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "I am going to home.", "lang": "en"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "I am going to home."
        assert data["lang"] == "en"
        assert data["chat_id"] == str(chat_id)

    def test_analyze_default_language(self, client, mock_db):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Test phrase",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Good",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test phrase"},
        )

        assert response.status_code == 200
        client.app.state.service.analyze.assert_called_once_with(mock_db, "Test phrase", "en", "test-user", None)

    def test_analyze_with_chat_id(self, client, mock_db):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Follow up",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Good",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "Follow up", "chat_id": str(chat_id)},
        )

        assert response.status_code == 200
        client.app.state.service.analyze.assert_called_once_with(
            mock_db, "Follow up", "en", "test-user", chat_id
        )

    def test_analyze_unsupported_language(self, client):
        client.app.state.service.analyze = AsyncMock(
            side_effect=UnsupportedLanguageError("fr", ["en", "es"])
        )

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test", "lang": "fr"},
        )

        assert response.status_code == 400
        assert "fr" in response.json()["detail"]

    def test_analyze_invalid_chat(self, client):
        chat_id = uuid4()
        client.app.state.service.analyze = AsyncMock(
            side_effect=InvalidChatError(chat_id)
        )

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test", "chat_id": str(chat_id)},
        )

        assert response.status_code == 404

    def test_analyze_service_error(self, client):
        client.app.state.service.analyze = AsyncMock(
            side_effect=AnalysisError("LLM failed")
        )

        response = client.post(
            "/prompts/analyze",
            json={"text": "Test", "lang": "en"},
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Analysis failed"

    def test_analyze_missing_text(self, client):
        response = client.post(
            "/prompts/analyze",
            json={"lang": "en"},
        )

        assert response.status_code == 422

    def test_analyze_empty_text(self, client):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Empty",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "", "lang": "en"},
        )

        assert response.status_code == 200

    def test_analyze_spanish(self, client):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Yo soy va a casa.",
            lang="es",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Test",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"text": "Yo soy va a casa.", "lang": "es"},
        )

        assert response.status_code == 200
        assert response.json()["lang"] == "es"


class TestChatEndpoint:
    def test_chat_message_success(self, client):
        chat_id = uuid4()
        mock_response = AnalyzeResponse(
            text="Why is that wrong?",
            lang="en",
            chat_id=chat_id,
            issues=[],
            alternatives=[],
            assessment="Looks good",
        )

        client.app.state.service.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            f"/chats/{chat_id}/messages",
            json={"text": "Why is that wrong?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == str(chat_id)
        assert data["text"] == "Why is that wrong?"
        assert data["lang"] == "en"

    def test_chat_invalid_id(self, client):
        chat_id = uuid4()
        client.app.state.service.chat = AsyncMock(
            side_effect=InvalidChatError(chat_id)
        )

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

        assert response.status_code == 422


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

    def test_examples_unsupported_language(self, client):
        client.app.state.service.get_examples = MagicMock(
            side_effect=UnsupportedLanguageError("fr", ["en", "es"])
        )

        response = client.get("/prompts/examples?lang=fr")

        assert response.status_code == 400
        assert "fr" in response.json()["detail"]

    def test_examples_missing_lang_param(self, client):
        response = client.get("/prompts/examples")

        assert response.status_code == 422
