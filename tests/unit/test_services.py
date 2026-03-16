from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.schema import ChatResponseLLM, ExamplesResponse, Issue
from app.config import ResilienceConfig
from app.database import ChatsDB
from app.exceptions import ChatHistoryLimitError, InvalidChatError, PermanentLLMError, UnsupportedLanguageError
from app.models import AIContent, Chat, HumanContent, Message, Role
from app.resilience import ResiliencePolicy
from app.service import ChatService


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.prompt = "Test prompt for {lang}"
    config.examples = {"en": ["Example 1", "Example 2"],
                       "es": ["Ejemplo 1"]}
    config.history_max_messages = 50
    config.messages_max_page_size = 100
    config.chat_list_limit = 50
    return config


@pytest.fixture
def mock_chats_db():
    db = AsyncMock(spec=ChatsDB)
    db.create_chat = MagicMock()
    db.get_chat = AsyncMock(return_value=None)
    db.get_messages = AsyncMock(return_value=[])
    db.delete = AsyncMock(return_value=1)
    db.list_chats = AsyncMock(return_value=[])
    return db


@pytest.fixture
def service(mock_config, mock_chats_db):
    chain = AsyncMock()
    policy = ResiliencePolicy(ResilienceConfig(pool_size=1,
                                               queue_size=1,
                                               queue_retry_after_seconds=1,
                                               timeout_seconds=5,
                                               retry_max_attempts=1,
                                               retry_backoff_base_seconds=0,
                                               retry_backoff_max_seconds=0,
                                               circuit_breaker_failure_threshold=3,
                                               circuit_breaker_reset_seconds=60))
    svc = ChatService(chain=chain,
                      policy=policy,
                      config=mock_config,
                      db=MagicMock())
    svc.chats_db = mock_chats_db
    svc.chain = chain
    return svc


class TestCreateChat:

    @pytest.mark.asyncio
    async def test_new_chat_success(self, service, mock_chats_db):
        llm_response = ChatResponseLLM(
            issues=[Issue(text_part="going to home",
                          explanation="Should be 'going home'")],
            suggestions=["I am going home."],
            response="Minor grammar issue"
        )
        service.chain.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="I am going to home",
                                           user_id="user-1",
                                           lang="en")

        assert isinstance(result, Message)
        assert result.role == Role.ai
        assert result.content.response == "Minor grammar issue"
        assert len(result.content.issues) == 1
        assert result.content.issues[0].text_part == "going to home"
        assert result.content.suggestions == ["I am going home."]
        mock_chats_db.create_chat.assert_called_once()
        chat_arg = mock_chats_db.create_chat.call_args[0][0]
        assert isinstance(chat_arg, Chat)
        assert chat_arg.title == "I am going to home"
        assert len(chat_arg.messages) == 2

    @pytest.mark.asyncio
    async def test_new_chat_with_comment(self, service, mock_chats_db):
        llm_response = ChatResponseLLM(issues=[],
                                        suggestions=[],
                                        response="Looks good")
        service.chain.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="I am going to home",
                                           user_id="user-1",
                                           comment="Is this too formal?",
                                           lang="en")

        assert isinstance(result, Message)
        mock_chats_db.create_chat.assert_called_once()
        chat_arg = mock_chats_db.create_chat.call_args[0][0]
        human_msg = [m for m in chat_arg.messages if m.role == Role.human][0]
        assert human_msg.content.comment == "Is this too formal?"

    @pytest.mark.asyncio
    async def test_new_chat_autodetect_lang(self, service, mock_chats_db):
        llm_response = ChatResponseLLM(issues=[], suggestions=[], response="OK")
        service.chain.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="Hola mundo",
                                           user_id="user-1")

        assert isinstance(result, Message)
        invoke_args = service.chain.ainvoke.call_args[0][0]
        assert invoke_args["lang"] == "various languages (autodetect)"

    @pytest.mark.asyncio
    async def test_new_chat_unsupported_language(self, service):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.create_chat(phrase="Bonjour",
                                      user_id="user-1",
                                      lang="fr")

        assert exc_info.value.lang == "fr"
        assert "en" in exc_info.value.supported

    @pytest.mark.asyncio
    async def test_new_chat_llm_error(self, service, mock_chats_db):
        original_exc = Exception("LLM API error")
        service.chain.ainvoke.side_effect = original_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.create_chat(phrase="Test phrase",
                                      user_id="user-1",
                                      lang="en")

        assert "LLM API error" in str(exc_info.value)
        assert exc_info.value.__cause__ is original_exc
        mock_chats_db.create_chat.assert_not_called()


class TestFollowup:

    @pytest.mark.asyncio
    async def test_followup_success(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id="user-1")
        chat.messages = [
            Message(chat_id=chat_id, role=Role.human,
                    content=HumanContent(phrase="hello")),
            Message(chat_id=chat_id, role=Role.ai,
                    content=AIContent(response="hi", issues=[], suggestions=[]))
        ]
        mock_chats_db.get_chat.return_value = chat

        llm_response = ChatResponseLLM(issues=[], suggestions=[], response="Good point")
        service.chain.ainvoke.return_value = llm_response

        result = await service.send_message(chat_id, "user-1", "why?")

        assert isinstance(result, Message)
        assert result.chat_id == chat_id
        assert result.content.response == "Good point"
        assert len(chat.messages) == 4  # original 2 + new human + new ai

    @pytest.mark.asyncio
    async def test_followup_invalid_chat(self, service, mock_chats_db):
        chat_id = uuid4()
        mock_chats_db.get_chat.return_value = None

        with pytest.raises(InvalidChatError) as exc_info:
            await service.send_message(chat_id, "user-1", "test")

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_followup_capacity_exceeded(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id="user-1")
        chat.messages = [
            Message(chat_id=chat_id, role=Role.ai,
                    content=AIContent(response="r", issues=[], suggestions=[]))
            for _ in range(50)
        ]
        mock_chats_db.get_chat.return_value = chat

        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.send_message(chat_id, "user-1", "another message")

        assert exc_info.value.max_messages == 50

    @pytest.mark.asyncio
    async def test_followup_llm_error(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id="user-1")
        chat.messages = [
            Message(chat_id=chat_id, role=Role.human,
                    content=HumanContent(phrase="hello")),
            Message(chat_id=chat_id, role=Role.ai,
                    content=AIContent(response="hi", issues=[], suggestions=[]))
        ]
        mock_chats_db.get_chat.return_value = chat

        original_exc = Exception("LLM failed")
        service.chain.ainvoke.side_effect = original_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.send_message(chat_id, "user-1", "why?")

        assert exc_info.value.__cause__ is original_exc


class TestDeleteChat:

    @pytest.mark.asyncio
    async def test_delete_success(self, service, mock_chats_db):
        chat_id = uuid4()
        mock_chats_db.delete.return_value = 1

        await service.delete_chat(chat_id, "user-1")

        mock_chats_db.delete.assert_called_once_with(chat_id, "user-1")

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service, mock_chats_db):
        chat_id = uuid4()
        mock_chats_db.delete.return_value = 0

        with pytest.raises(InvalidChatError) as exc_info:
            await service.delete_chat(chat_id, "user-1")

        assert exc_info.value.chat_id == chat_id


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
        service.examples["en"] = []

        with pytest.raises(UnsupportedLanguageError):
            service.get_examples("en")
