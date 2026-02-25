import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

from app.schema import AnalyzeResponse, ExamplesResponse
from app.exceptions import UnsupportedLanguageError, AnalysisError, InvalidChatError
from app.services import AnalysisService


@pytest.fixture
def examples():
    return {
        "en": ["Example 1", "Example 2"],
        "es": ["Ejemplo 1"],
    }


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_chats():
    chats = AsyncMock()
    chats.create_chat = AsyncMock()
    chats.get_chat = AsyncMock(return_value=None)
    chats.load_history = AsyncMock(return_value=[])
    chats.save_messages = AsyncMock()
    return chats


@pytest.fixture
def service(examples, mock_chats):
    return AnalysisService(
        prompt="Analyze {lang} phrase: {phrase}",
        examples=examples,
        llm=MagicMock(),
        semaphore=asyncio.Semaphore(1),
        chats=mock_chats,
    )


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        llm_response = {
            "issues": [{"text_part": "going to home", "explanation": "Should be 'going home'"}],
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

            result = await service.analyze(mock_db, "I am going to home", "en")

            assert isinstance(result, AnalyzeResponse)
            assert result.text == "I am going to home"
            assert result.lang == "en"
            assert result.chat_id is not None
            assert len(result.issues) == 1
            assert result.assessment == "Minor grammar issue"

    @pytest.mark.asyncio
    async def test_with_existing_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat.return_value = {"id": chat_id, "lang": "es"}

        llm_response = {
            "issues": [],
            "alternatives": [],
            "assessment": "Good",
        }

        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"):

            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = llm_response

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            result = await service.analyze(mock_db, "Test", "en", chat_id)

            assert result.chat_id == chat_id
            assert result.lang == "es"
            mock_chats.create_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat.return_value = None

        with pytest.raises(InvalidChatError) as exc_info:
            await service.analyze(mock_db, "Test", "en", chat_id)

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_unsupported_language(self, service, mock_db):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.analyze(mock_db, "Test", "fr")

        assert exc_info.value.lang == "fr"
        assert "en" in exc_info.value.supported

    @pytest.mark.asyncio
    async def test_llm_error(self, service, mock_db):
        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"):

            mock_chain = AsyncMock()
            mock_chain.ainvoke.side_effect = Exception("LLM API error")

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            with pytest.raises(AnalysisError) as exc_info:
                await service.analyze(mock_db, "Test phrase", "en")

            assert "LLM API error" in str(exc_info.value)


class TestChat:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat.return_value = {"id": chat_id, "lang": "en"}

        llm_response = {
            "issues": [],
            "alternatives": [],
            "assessment": "Looks good",
        }

        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"):

            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = llm_response

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            result = await service.chat(mock_db, chat_id, "Why is that wrong?")

            assert isinstance(result, AnalyzeResponse)
            assert result.chat_id == chat_id
            assert result.text == "Why is that wrong?"
            assert result.lang == "en"
            mock_chats.save_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat.return_value = None

        with pytest.raises(InvalidChatError):
            await service.chat(mock_db, chat_id, "Hello")

    @pytest.mark.asyncio
    async def test_llm_error(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat.return_value = {"id": chat_id, "lang": "en"}

        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"):

            mock_chain = AsyncMock()
            mock_chain.ainvoke.side_effect = Exception("LLM failed")

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            with pytest.raises(AnalysisError):
                await service.chat(mock_db, chat_id, "Hello")


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
