from uuid import uuid4

import pytest

from nativespeaker.api.exceptions import (
    ChatHistoryLimitError,
    InvalidChatError,
    OutOfScopeError,
    PermanentLLMError,
    UnsupportedLanguageError,
)
from nativespeaker.api.models import Chat, ChatRole, Message
from nativespeaker.api.models.api import ExamplesResponse
from unit.conftest import TEST_USER


class TestCreateChat:

    @pytest.mark.asyncio
    async def test_new_chat_success(self, service, mock_chats_db):
        llm_response = {"resolved_mode": "analyze",
                        "response": "Minor grammar issue",
                        "issues": [{"text_part": "going to home",
                                    "explanation": "Should be 'going home'"}],
                        "suggestions": ["I am going home."]}
        service.llm_service.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="I am going to home",
                                           user=TEST_USER,
                                           lang="en")

        assert isinstance(result, Message)
        assert result.role == ChatRole.ai
        assert result.content["response"] == "Minor grammar issue"
        assert len(result.content["issues"]) == 1
        assert result.content["issues"][0]["text_part"] == "going to home"
        assert result.content["suggestions"] == ["I am going home."]
        mock_chats_db.create_chat.assert_called_once()
        chat_arg = mock_chats_db.create_chat.call_args[0][0]
        assert isinstance(chat_arg, Chat)
        assert chat_arg.title == "I am going to home"
        assert len(chat_arg.messages) == 2

    @pytest.mark.asyncio
    async def test_new_chat_with_context(self, service, mock_chats_db):
        llm_response = {"resolved_mode": "analyze",
                        "response": "Looks good",
                        "issues": [], "suggestions": []}
        service.llm_service.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="I am going to home",
                                           user=TEST_USER,
                                           context="Is this too formal?",
                                           lang="en")

        assert isinstance(result, Message)
        mock_chats_db.create_chat.assert_called_once()
        chat_arg = mock_chats_db.create_chat.call_args[0][0]
        human_msg = [m for m in chat_arg.messages if m.role == ChatRole.human][0]
        assert human_msg.content["context"] == "Is this too formal?"

    @pytest.mark.asyncio
    async def test_new_chat_autodetect_lang(self, service, mock_chats_db):
        llm_response = {"resolved_mode": "analyze", "response": "OK",
                        "issues": [], "suggestions": []}
        service.llm_service.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="Hola mundo",
                                           user=TEST_USER)

        assert isinstance(result, Message)
        invoke_kwargs = service.llm_service.ainvoke.call_args.kwargs
        assert invoke_kwargs["lang"] == "various languages (autodetect)"

    @pytest.mark.asyncio
    async def test_new_chat_unsupported_language(self, service):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.create_chat(phrase="Bonjour",
                                      user=TEST_USER,
                                      lang="fr")

        assert exc_info.value.lang == "fr"
        assert "en" in exc_info.value.supported

    @pytest.mark.asyncio
    async def test_new_chat_chats_limit_exceeded(self, service, mock_chats_db):
        mock_chats_db.count_chats.return_value = 50
        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.create_chat(phrase="Test", user=TEST_USER, lang="en")
        assert exc_info.value.max_messages == 50

    @pytest.mark.asyncio
    async def test_new_chat_llm_error(self, service, mock_chats_db):
        llm_exc = PermanentLLMError("LLM API error")
        service.llm_service.ainvoke.side_effect = llm_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.create_chat(phrase="Test phrase",
                                      user=TEST_USER,
                                      lang="en")

        assert "LLM API error" in str(exc_info.value)
        assert exc_info.value is llm_exc
        mock_chats_db.create_chat.assert_not_called()


class TestFollowup:

    @pytest.mark.asyncio
    async def test_followup_success(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER.id)
        chat.messages = [
            Message(chat_id=chat_id, role=ChatRole.human,
                    content={"mode": "analyze", "phrase": "hello"}),
            Message(chat_id=chat_id, role=ChatRole.ai,
                    content={"resolved_mode": "analyze", "response": "hi",
                             "issues": [], "suggestions": []})
        ]
        mock_chats_db.get_chat.return_value = chat

        llm_response = {"resolved_mode": "analyze", "response": "Good point",
                        "issues": [], "suggestions": []}
        service.llm_service.ainvoke.return_value = llm_response

        result = await service.send_message(chat_id, user=TEST_USER, message="why?")

        assert isinstance(result, Message)
        assert result.chat_id == chat_id
        assert result.content["response"] == "Good point"
        assert len(chat.messages) == 4  # original 2 + new human + new ai

    @pytest.mark.asyncio
    async def test_followup_invalid_chat(self, service, mock_chats_db):
        chat_id = uuid4()
        mock_chats_db.get_chat.return_value = None

        with pytest.raises(InvalidChatError) as exc_info:
            await service.send_message(chat_id, user=TEST_USER, message="test")

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_followup_capacity_exceeded(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER.id)
        chat.messages = [
            Message(chat_id=chat_id, role=ChatRole.ai,
                    content={"resolved_mode": "analyze", "response": "r",
                             "issues": [], "suggestions": []})
            for _ in range(50)
        ]
        mock_chats_db.get_chat.return_value = chat

        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.send_message(chat_id, user=TEST_USER, message="another message")

        assert exc_info.value.max_messages == 50

    @pytest.mark.asyncio
    async def test_followup_llm_error(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER.id)
        chat.messages = [
            Message(chat_id=chat_id, role=ChatRole.human,
                    content={"mode": "analyze", "phrase": "hello"}),
            Message(chat_id=chat_id, role=ChatRole.ai,
                    content={"resolved_mode": "analyze", "response": "hi",
                             "issues": [], "suggestions": []})
        ]
        mock_chats_db.get_chat.return_value = chat

        llm_exc = PermanentLLMError("LLM failed")
        service.llm_service.ainvoke.side_effect = llm_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.send_message(chat_id, user=TEST_USER, message="why?")

        assert exc_info.value is llm_exc


class TestRejectHandling:

    @pytest.mark.asyncio
    async def test_reject_raises_out_of_scope(self, service, mock_chats_db):
        llm_response = {"resolved_mode": "reject",
                        "response": "The request is outside the scope of linguistic analysis"}
        service.llm_service.ainvoke.return_value = llm_response

        with pytest.raises(OutOfScopeError):
            await service.create_chat(phrase="What is the weather?",
                                      user=TEST_USER, lang="en")

        mock_chats_db.create_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_no_messages_persisted(self, service, mock_chats_db):
        """D-09: On reject, neither human nor AI message is persisted."""
        llm_response = {"resolved_mode": "reject",
                        "response": "Out of scope"}
        service.llm_service.ainvoke.return_value = llm_response

        with pytest.raises(OutOfScopeError):
            await service.create_chat(phrase="Tell me a joke",
                                      user=TEST_USER, lang="en")

        # create_chat not called means no messages were appended/persisted
        mock_chats_db.create_chat.assert_not_called()


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
