from uuid import uuid4

import pytest

from nativespeaker.api.schema import ExamplesResponse
from nativespeaker.api.models.content import Issue
from nativespeaker.api.exceptions import ChatHistoryLimitError, InvalidChatError, PermanentLLMError, UnsupportedLanguageError
from nativespeaker.api.models import AIContent, Chat, ChatRole, HumanContent, Message
from unit.conftest import TEST_USER


class TestCreateChat:

    @pytest.mark.asyncio
    async def test_new_chat_success(self, service, mock_chats_db):
        llm_response = AIContent(
            response="Minor grammar issue",
            issues=[Issue(text_part="going to home",
                          explanation="Should be 'going home'")],
            suggestions=["I am going home."]
        )
        service.llm_service.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="I am going to home",
                                           user=TEST_USER,
                                           lang="en")

        assert isinstance(result, Message)
        assert result.role == ChatRole.ai
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
        llm_response = AIContent(response="Looks good",
                                  issues=[],
                                  suggestions=[])
        service.llm_service.ainvoke.return_value = llm_response

        result = await service.create_chat(phrase="I am going to home",
                                           user=TEST_USER,
                                           comment="Is this too formal?",
                                           lang="en")

        assert isinstance(result, Message)
        mock_chats_db.create_chat.assert_called_once()
        chat_arg = mock_chats_db.create_chat.call_args[0][0]
        human_msg = [m for m in chat_arg.messages if m.role == ChatRole.human][0]
        assert human_msg.content.comment == "Is this too formal?"

    @pytest.mark.asyncio
    async def test_new_chat_autodetect_lang(self, service, mock_chats_db):
        llm_response = AIContent(response="OK", issues=[], suggestions=[])
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
                    content=HumanContent(phrase="hello")),
            Message(chat_id=chat_id, role=ChatRole.ai,
                    content=AIContent(response="hi", issues=[], suggestions=[]))
        ]
        mock_chats_db.get_chat.return_value = chat

        llm_response = AIContent(response="Good point", issues=[], suggestions=[])
        service.llm_service.ainvoke.return_value = llm_response

        result = await service.send_message(chat_id, user=TEST_USER, content="why?")

        assert isinstance(result, Message)
        assert result.chat_id == chat_id
        assert result.content.response == "Good point"
        assert len(chat.messages) == 4  # original 2 + new human + new ai

    @pytest.mark.asyncio
    async def test_followup_invalid_chat(self, service, mock_chats_db):
        chat_id = uuid4()
        mock_chats_db.get_chat.return_value = None

        with pytest.raises(InvalidChatError) as exc_info:
            await service.send_message(chat_id, user=TEST_USER, content="test")

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_followup_capacity_exceeded(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER.id)
        chat.messages = [
            Message(chat_id=chat_id, role=ChatRole.ai,
                    content=AIContent(response="r", issues=[], suggestions=[]))
            for _ in range(50)
        ]
        mock_chats_db.get_chat.return_value = chat

        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.send_message(chat_id, user=TEST_USER, content="another message")

        assert exc_info.value.max_messages == 50

    @pytest.mark.asyncio
    async def test_followup_llm_error(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER.id)
        chat.messages = [
            Message(chat_id=chat_id, role=ChatRole.human,
                    content=HumanContent(phrase="hello")),
            Message(chat_id=chat_id, role=ChatRole.ai,
                    content=AIContent(response="hi", issues=[], suggestions=[]))
        ]
        mock_chats_db.get_chat.return_value = chat

        llm_exc = PermanentLLMError("LLM failed")
        service.llm_service.ainvoke.side_effect = llm_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.send_message(chat_id, user=TEST_USER, content="why?")

        assert exc_info.value is llm_exc


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
