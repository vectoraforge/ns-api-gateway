from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schema import AnalyzeResponse
from app.exceptions import UnsupportedLanguageError, AnalysisError


class TestAnalyzeEndpoint:
    def test_analyze_success(self, client):
        mock_response = AnalyzeResponse(
            phrase="I am going to home.",
            lang="en",
            issues=[],
            alternatives=[],
            assessment="Test",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"phrase": "I am going to home.", "lang": "en"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["phrase"] == "I am going to home."
        assert data["lang"] == "en"

    def test_analyze_default_language(self, client):
        mock_response = AnalyzeResponse(
            phrase="Test phrase",
            lang="en",
            issues=[],
            alternatives=[],
            assessment="Good",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"phrase": "Test phrase"},
        )

        assert response.status_code == 200
        client.app.state.service.analyze.assert_called_once_with("Test phrase", "en")

    def test_analyze_unsupported_language(self, client):
        client.app.state.service.analyze = AsyncMock(
            side_effect=UnsupportedLanguageError("fr", ["en", "es"])
        )

        response = client.post(
            "/prompts/analyze",
            json={"phrase": "Test", "lang": "fr"},
        )

        assert response.status_code == 400
        assert "fr" in response.json()["detail"]

    def test_analyze_service_error(self, client):
        client.app.state.service.analyze = AsyncMock(
            side_effect=AnalysisError("LLM failed")
        )

        response = client.post(
            "/prompts/analyze",
            json={"phrase": "Test", "lang": "en"},
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Analysis failed"

    def test_analyze_missing_phrase(self, client):
        response = client.post(
            "/prompts/analyze",
            json={"lang": "en"},
        )

        assert response.status_code == 422

    def test_analyze_empty_phrase(self, client):
        mock_response = AnalyzeResponse(
            phrase="",
            lang="en",
            issues=[],
            alternatives=[],
            assessment="Empty",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"phrase": "", "lang": "en"},
        )

        assert response.status_code == 200

    def test_analyze_spanish(self, client):
        mock_response = AnalyzeResponse(
            phrase="Yo soy va a casa.",
            lang="es",
            issues=[],
            alternatives=[],
            assessment="Test",
        )

        client.app.state.service.analyze = AsyncMock(return_value=mock_response)

        response = client.post(
            "/prompts/analyze",
            json={"phrase": "Yo soy va a casa.", "lang": "es"},
        )

        assert response.status_code == 200
        assert response.json()["lang"] == "es"


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
