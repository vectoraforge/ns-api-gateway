import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from app.schema import AnalyzeResponse, ExamplesResponse
from app.exceptions import UnsupportedLanguageError, AnalysisError
from app.services import AnalysisService


@pytest.fixture
def examples():
    return {
        "en": ["Example 1", "Example 2"],
        "es": ["Ejemplo 1"],
    }


@pytest.fixture
def service(examples):
    return AnalysisService(
        prompt="Analyze {lang} phrase: {phrase}",
        examples=examples,
        llm=MagicMock(),
        semaphore=asyncio.Semaphore(1),
    )


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_success(self, service):
        llm_response = {
            "phrase": "I am going to home",
            "lang": "en",
            "issues": [{"phrase_part": "going to home", "explanation": "Should be 'going home'"}],
            "alternatives": ["I am going home."],
            "assessment": "Minor grammar issue",
        }

        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser") as mock_parser:

            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = llm_response

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            result = await service.analyze("I am going to home", "en")

            assert isinstance(result, AnalyzeResponse)
            assert result.phrase == "I am going to home"
            assert result.lang == "en"
            assert len(result.issues) == 1
            assert result.assessment == "Minor grammar issue"
            mock_chain.ainvoke.assert_called_once_with({"lang": "en", "phrase": "I am going to home"})

    @pytest.mark.asyncio
    async def test_unsupported_language(self, service):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.analyze("Test", "fr")

        assert exc_info.value.lang == "fr"
        assert "en" in exc_info.value.supported

    @pytest.mark.asyncio
    async def test_llm_error(self, service):
        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"):

            mock_chain = AsyncMock()
            mock_chain.ainvoke.side_effect = Exception("LLM API error")

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            with pytest.raises(AnalysisError) as exc_info:
                await service.analyze("Test phrase", "en")

            assert "LLM API error" in str(exc_info.value)


class TestGetExamples:
    def test_success(self, service):
        result = service.get_examples("en")

        assert isinstance(result, ExamplesResponse)
        assert result.lang == "en"
        assert result.examples == ["Example 1", "Example 2"]

    def test_unsupported_language(self, service):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            service.get_examples("fr")

        assert exc_info.value.lang == "fr"

    def test_empty_list(self, service):
        service.examples = {"en": []}

        with pytest.raises(UnsupportedLanguageError):
            service.get_examples("en")
