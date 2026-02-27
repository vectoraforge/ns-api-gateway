import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

from app.schema import AnalyzeResponse, ExamplesResponse
from app.exceptions import UnsupportedLanguageError, AnalysisError, InvalidChatError, PermanentLLMError, TransientLLMError
from app.services import AnalysisService, LLMExecutionGate, CircuitBreaker


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
    chats.get_chat_owned = AsyncMock(return_value=None)
    chats.load_history = AsyncMock(return_value=[])
    chats.get_message_counts = AsyncMock(return_value={"human": 0, "assistant": 0})
    chats.save_messages = AsyncMock()
    return chats


@pytest.fixture
def service(examples, mock_chats):
    gate = LLMExecutionGate(max_concurrency=1, max_queue=1, retry_after_seconds=1)
    circuit_breaker = CircuitBreaker(failure_threshold=3, reset_seconds=60)
    return AnalysisService(
        prompt="Analyze {lang} phrase: {phrase}",
        examples=examples,
        llm=MagicMock(),
        gate=gate,
        circuit_breaker=circuit_breaker,
        timeout_seconds=1,
        retry_max_attempts=1,
        retry_backoff_base_seconds=0,
        retry_backoff_max_seconds=0,
        history_max_human_messages=50,
        history_max_assistant_messages=50,
        message_max_chars=4096,
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

            result = await service.analyze(mock_db, "I am going to home", "en", "user-1")

            assert isinstance(result, AnalyzeResponse)
            assert result.text == "I am going to home"
            assert result.lang == "en"
            assert result.chat_id is not None
            assert len(result.issues) == 1
            assert result.assessment == "Minor grammar issue"

    @pytest.mark.asyncio
    async def test_with_existing_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat_owned.return_value = {"id": chat_id, "lang": "es", "user_id": "user-1"}

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

            result = await service.analyze(mock_db, "Test", "en", "user-1", chat_id)

            assert result.chat_id == chat_id
            assert result.lang == "es"
            mock_chats.create_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat_owned.side_effect = InvalidChatError(chat_id)

        with pytest.raises(InvalidChatError) as exc_info:
            await service.analyze(mock_db, "Test", "en", "user-1", chat_id)

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_unsupported_language(self, service, mock_db):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.analyze(mock_db, "Test", "fr", "user-1")

        assert exc_info.value.lang == "fr"
        assert "en" in exc_info.value.supported

    @pytest.mark.asyncio
    async def test_llm_error(self, service, mock_db):
        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"):

            mock_chain = AsyncMock()
            original_exc = Exception("LLM API error")
            mock_chain.ainvoke.side_effect = original_exc

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            with pytest.raises(PermanentLLMError) as exc_info:
                await service.analyze(mock_db, "Test phrase", "en", "user-1")

            assert "LLM API error" in str(exc_info.value)
            assert exc_info.value.__cause__ is original_exc

    @pytest.mark.asyncio
    async def test_transient_llm_error_exhausted(self, service, mock_db):
        """Retry exhaustion on a transient error raises TransientLLMError with __cause__."""
        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"), \
             patch("app.services._is_transient_error", return_value=True):

            mock_chain = AsyncMock()
            original_exc = Exception("timeout")
            mock_chain.ainvoke.side_effect = original_exc

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            with pytest.raises(TransientLLMError) as exc_info:
                await service.analyze(mock_db, "Test phrase", "en", "user-1")

            assert exc_info.value.__cause__ is original_exc


class TestChat:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat_owned.return_value = {"id": chat_id, "lang": "en", "user_id": "user-1"}

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

            result = await service.chat(mock_db, chat_id, "Why is that wrong?", "user-1")

            assert isinstance(result, AnalyzeResponse)
            assert result.chat_id == chat_id
            assert result.text == "Why is that wrong?"
            assert result.lang == "en"
            mock_chats.save_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat_owned.side_effect = InvalidChatError(chat_id)

        with pytest.raises(InvalidChatError):
            await service.chat(mock_db, chat_id, "Hello", "user-1")

    @pytest.mark.asyncio
    async def test_llm_error(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.get_chat_owned.return_value = {"id": chat_id, "lang": "en", "user_id": "user-1"}

        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser"):

            mock_chain = AsyncMock()
            original_exc = Exception("LLM failed")
            mock_chain.ainvoke.side_effect = original_exc

            mock_prompt_inst = mock_prompt.from_messages.return_value
            mock_pipe = mock_prompt_inst.__or__.return_value
            mock_pipe.__or__.return_value = mock_chain

            with pytest.raises(PermanentLLMError) as exc_info:
                await service.chat(mock_db, chat_id, "Hello", "user-1")

            assert exc_info.value.__cause__ is original_exc


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
