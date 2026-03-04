from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.config import ResilienceConfig
from app.exceptions import (
    ChatHistoryLimitError,
    InvalidChatError,
    PermanentLLMError,
    TransientLLMError,
    UnsupportedLanguageError,
)
from app.resilience import ResiliencePolicy
from app.schema import ChatResponse, ChatResponseLLM, ExamplesResponse, Issue
from app.services import ChatService


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
    chats.create_chat_with_messages = AsyncMock()
    chats.load_history = AsyncMock(return_value=[])
    chats.save_messages = AsyncMock()
    return chats


@pytest.fixture
def service(examples, mock_chats):
    policy = ResiliencePolicy(
        ResilienceConfig(
            pool_size=1,
            queue_size=1,
            queue_retry_after_seconds=1,
            timeout_seconds=1,
            retry_max_attempts=1,
            retry_backoff_base_seconds=0,
            retry_backoff_max_seconds=0,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_reset_seconds=60,
        )
    )
    svc = ChatService(
        prompt="{lang_directive} Analyze phrase: {phrase}",
        examples=examples,
        llm=MagicMock(),
        policy=policy,
        history_max_messages=50,
        message_max_chars=4096,
        chats=mock_chats,
    )
    svc.chain = MagicMock()
    return svc


class TestChat:
    @pytest.mark.asyncio
    async def test_new_chat_success(self, service, mock_chats, mock_db):
        llm_response = ChatResponseLLM(
            issues=[Issue(text_part="going to home", explanation="Should be 'going home'")],
            suggestions=["I am going home."],
            response="Minor grammar issue",
        )

        service.chain = AsyncMock()
        service.chain.ainvoke.return_value = llm_response

        result = await service.chat(mock_db, "I am going to home", "user-1", lang="en")

        assert isinstance(result, ChatResponse)
        assert result.text == "I am going to home"
        assert result.chat_id is not None
        assert len(result.issues) == 1
        assert result.response == "Minor grammar issue"
        mock_chats.create_chat_with_messages.assert_called_once()
        mock_chats.load_history.assert_not_called()
        mock_chats.save_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_continuation_with_chat_id(self, service, mock_chats, mock_db):
        """Continuation: chat_id provided, load_history returns existing messages."""
        chat_id = uuid4()
        mock_chats.load_history.return_value = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello"),
        ]

        llm_response = ChatResponseLLM(issues=[], suggestions=[], response="Good")

        service.chain = AsyncMock()
        service.chain.ainvoke.return_value = llm_response

        result = await service.chat(mock_db, "Test", "user-1", chat_id=chat_id)

        assert result.chat_id == chat_id
        mock_chats.save_messages.assert_called_once()
        mock_chats.create_chat_with_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.load_history.side_effect = InvalidChatError(chat_id)

        with pytest.raises(InvalidChatError) as exc_info:
            await service.chat(mock_db, "Test", "user-1", chat_id=chat_id)

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_unsupported_language(self, service, mock_db):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.chat(mock_db, "Test", "user-1", lang="fr")

        assert exc_info.value.lang == "fr"
        assert "en" in exc_info.value.supported

    @pytest.mark.asyncio
    async def test_llm_error(self, service, mock_db):
        service.chain = AsyncMock()
        original_exc = Exception("LLM API error")
        service.chain.ainvoke.side_effect = original_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.chat(mock_db, "Test phrase", "user-1", lang="en")

        assert "LLM API error" in str(exc_info.value)
        assert exc_info.value.__cause__ is original_exc

    @pytest.mark.asyncio
    async def test_transient_llm_error_exhausted(self, service, mock_db):
        """Retry exhaustion on a transient error raises TransientLLMError with __cause__."""
        service.chain = AsyncMock()
        original_exc = Exception("timeout")
        service.chain.ainvoke.side_effect = original_exc

        with patch("app.resilience._is_transient_error", return_value=True):
            with pytest.raises(TransientLLMError) as exc_info:
                await service.chat(mock_db, "Test phrase", "user-1", lang="en")

            assert exc_info.value.__cause__ is original_exc

    @pytest.mark.asyncio
    async def test_continuation_success(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.load_history.return_value = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello"),
        ]

        llm_response = ChatResponseLLM(issues=[], suggestions=[], response="Looks good")

        service.chain = AsyncMock()
        service.chain.ainvoke.return_value = llm_response

        result = await service.chat(mock_db, "Why is that wrong?", "user-1", chat_id=chat_id)

        assert isinstance(result, ChatResponse)
        assert result.chat_id == chat_id
        assert result.text == "Why is that wrong?"
        mock_chats.save_messages.assert_called_once()
        mock_chats.create_chat_with_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_continuation_invalid_chat_id(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.load_history.side_effect = InvalidChatError(chat_id)

        with pytest.raises(InvalidChatError):
            await service.chat(mock_db, "Hello", "user-1", chat_id=chat_id)

    @pytest.mark.asyncio
    async def test_continuation_llm_error(self, service, mock_chats, mock_db):
        chat_id = uuid4()
        mock_chats.load_history.return_value = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello"),
        ]

        service.chain = AsyncMock()
        original_exc = Exception("LLM failed")
        service.chain.ainvoke.side_effect = original_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.chat(mock_db, "Hello", "user-1", chat_id=chat_id)

        assert exc_info.value.__cause__ is original_exc

    @pytest.mark.asyncio
    async def test_continuation_capacity_exceeded(self, service, mock_chats, mock_db):
        """When load_history returns >= history_max_messages * 2 messages, ChatHistoryLimitError is raised."""
        chat_id = uuid4()
        history = [HumanMessage(content="q")] * 50 + [AIMessage(content="a")] * 50
        mock_chats.load_history.return_value = history

        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.chat(mock_db, "Test", "user-1", chat_id=chat_id)

        assert exc_info.value.max_messages == 50


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
