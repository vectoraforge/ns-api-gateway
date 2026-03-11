import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.config import ResilienceConfig
from app.database.chats import ChatsDB
from app.database.models import Chat, Role
from app.exceptions import ChatHistoryLimitError, InvalidChatError, PermanentLLMError, UnsupportedLanguageError
from app.resilience import ResiliencePolicy
from app.schema import ChatResponse, ChatResponseLLM, ExamplesResponse, Issue
from app.services.chats import ChatService


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
    db.create = AsyncMock()
    db.save_message = AsyncMock()
    db.get_history = AsyncMock(return_value=(None, []))
    db.get_messages = AsyncMock(return_value=(None, [], None))
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

        assert isinstance(result, ChatResponse)
        assert result.chat_id is not None
        assert len(result.issues) == 1
        assert result.issues[0].text_part == "going to home"
        assert result.suggestions == ["I am going home."]
        assert result.response == "Minor grammar issue"
        mock_chats_db.create.assert_called_once()
        call_args = mock_chats_db.create.call_args
        assert call_args[0][1] == "I am going to home"  # phrase
        assert call_args[0][2] == "user-1"  # user_id
        mock_chats_db.save_message.assert_called_once()
        save_call = mock_chats_db.save_message.call_args
        assert save_call[0][1] == Role.ai
        saved_content = json.loads(save_call[0][2])
        assert saved_content["response"] == "Minor grammar issue"

    @pytest.mark.asyncio
    async def test_new_chat_with_comment(self, service, mock_chats_db):
        llm_response = ChatResponseLLM(issues=[],
                                        suggestions=[],
                                        response="Looks good")
        service.chain.ainvoke.return_value = llm_response

        await service.create_chat(phrase="I am going to home",
                                  user_id="user-1",
                                  comment="Is this too formal?",
                                  lang="en")

        mock_chats_db.create.assert_called_once()
        call_args = mock_chats_db.create.call_args
        assert call_args[0][3] == "Is this too formal?"  # comment

    @pytest.mark.asyncio
    async def test_new_chat_autodetect_lang(self, service, mock_chats_db):
        llm_response = ChatResponseLLM(issues=[], suggestions=[], response="OK")
        service.chain.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="Hola mundo",
                                           user_id="user-1")

        assert isinstance(result, ChatResponse)
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
        mock_chats_db.create.assert_not_called()


class TestFollowup:

    @pytest.mark.asyncio
    async def test_followup_success(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, phrase="hello", user_id="user-1")
        db_messages = [(Role.ai,
                        json.dumps({"response": "hi",
                                    "issues": [],
                                    "suggestions": []}))]
        mock_chats_db.get_history.return_value = (chat, db_messages)

        llm_response = ChatResponseLLM(issues=[], suggestions=[], response="Good point")
        service.chain.ainvoke.return_value = llm_response

        result = await service.followup(chat_id, "why?", "user-1")

        assert isinstance(result, ChatResponse)
        assert result.chat_id == chat_id
        assert result.response == "Good point"
        assert mock_chats_db.save_message.call_count == 2
        human_call = mock_chats_db.save_message.call_args_list[0]
        assert human_call[0][1] == Role.human
        assert human_call[0][2] == "why?"
        ai_call = mock_chats_db.save_message.call_args_list[1]
        assert ai_call[0][1] == Role.ai
        saved = json.loads(ai_call[0][2])
        assert saved["response"] == "Good point"

    @pytest.mark.asyncio
    async def test_followup_invalid_chat(self, service, mock_chats_db):
        chat_id = uuid4()
        mock_chats_db.get_history.return_value = (None, [])

        with pytest.raises(InvalidChatError) as exc_info:
            await service.followup(chat_id, "test", "user-1")

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_followup_capacity_exceeded(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, phrase="hello", user_id="user-1")
        db_messages = [(Role.ai, "response")] * 50
        mock_chats_db.get_history.return_value = (chat, db_messages)

        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.followup(chat_id, "another message", "user-1")

        assert exc_info.value.max_messages == 50

    @pytest.mark.asyncio
    async def test_followup_llm_error(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, phrase="hello", user_id="user-1")
        db_messages = [(Role.ai,
                        json.dumps({"response": "hi",
                                    "issues": [],
                                    "suggestions": []}))]
        mock_chats_db.get_history.return_value = (chat, db_messages)

        original_exc = Exception("LLM failed")
        service.chain.ainvoke.side_effect = original_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.followup(chat_id, "why?", "user-1")

        assert exc_info.value.__cause__ is original_exc
        mock_chats_db.save_message.assert_not_called()


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
