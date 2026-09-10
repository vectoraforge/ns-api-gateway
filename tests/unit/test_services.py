from uuid import uuid4, uuid7

import pytest

from nativespeaker.api.errors import (
    ChatHistoryLimitError,
    InvalidChatError,
    OutOfScopeError,
    PermanentLLMError,
    UnsupportedLanguageError,
)
from nativespeaker.api.schemas.api import ExamplesResponse
from nativespeaker.api.tables import Chat, ChatRole, Message
from unit.conftest import TEST_USER_ID


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
                                           user_id=TEST_USER_ID,
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
                                           user_id=TEST_USER_ID,
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
                                           user_id=TEST_USER_ID)

        assert isinstance(result, Message)
        invoke_kwargs = service.llm_service.ainvoke.call_args.kwargs
        assert invoke_kwargs["lang"] == "various languages (autodetect)"

    @pytest.mark.asyncio
    async def test_new_chat_unsupported_language(self, service):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.create_chat(phrase="Bonjour",
                                      user_id=TEST_USER_ID,
                                      lang="fr")

        assert exc_info.value.lang == "fr"
        assert "en" in exc_info.value.supported

    @pytest.mark.asyncio
    async def test_new_chat_empty_language(self, service):
        """WR-63: the empty string is falsy, so a truthiness guard let it past the supported set
        and stored it as the chat's language, which is not a language code."""
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await service.create_chat(phrase="Bonjour", user_id=TEST_USER_ID, lang="")

        assert exc_info.value.lang == ""

    @pytest.mark.asyncio
    async def test_new_chat_chats_limit_exceeded(self, service, mock_chats_db):
        mock_chats_db.count_chats.return_value = 50
        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.create_chat(phrase="Test", user_id=TEST_USER_ID, lang="en")
        assert exc_info.value.max_messages == 50

    @pytest.mark.asyncio
    async def test_a_chat_that_reached_the_limit_across_the_provider_call_is_not_inserted(
            self, service, mock_chats_db):
        """WR-63: the guard and the insert are separated by a commit and an LLM round trip, and
        nothing in the database caps the count, so the last read before the insert is the guard."""
        service.llm_service.ainvoke.return_value = {"resolved_mode": "analyze", "response": "OK",
                                                    "issues": [], "suggestions": []}
        # 49 when the request arrives, 50 by the time it comes back from the provider.
        mock_chats_db.count_chats.side_effect = [49, 50]

        with pytest.raises(ChatHistoryLimitError):
            await service.create_chat(phrase="Test", user_id=TEST_USER_ID, lang="en")

        mock_chats_db.create_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_chat_llm_error(self, service, mock_chats_db):
        llm_exc = PermanentLLMError("LLM API error")
        service.llm_service.ainvoke.side_effect = llm_exc

        with pytest.raises(PermanentLLMError) as exc_info:
            await service.create_chat(phrase="Test phrase",
                                      user_id=TEST_USER_ID,
                                      lang="en")

        assert "LLM API error" in str(exc_info.value)
        assert exc_info.value is llm_exc
        mock_chats_db.create_chat.assert_not_called()


class TestFollowup:

    @pytest.mark.asyncio
    async def test_followup_success(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER_ID)
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

        result = await service.send_message(chat_id, user_id=TEST_USER_ID, message="why?")

        assert isinstance(result, Message)
        assert result.chat_id == chat_id
        assert result.content["response"] == "Good point"
        assert len(chat.messages) == 4  # original 2 + new human + new ai

    @pytest.mark.asyncio
    async def test_followup_invalid_chat(self, service, mock_chats_db):
        chat_id = uuid4()
        mock_chats_db.get_chat.return_value = None

        with pytest.raises(InvalidChatError) as exc_info:
            await service.send_message(chat_id, user_id=TEST_USER_ID, message="test")

        assert exc_info.value.chat_id == chat_id

    @pytest.mark.asyncio
    async def test_followup_on_a_chat_deleted_across_the_provider_call_is_a_refusal(
            self, service, mock_chats_db):
        """WR-42: the two inserts would point at no `core.chats` row, and the foreign key is not an
        `AppError` -- an opaque 500 raised after the credit was already committed."""
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER_ID)
        # The second read is the one taken in the transaction that writes.
        mock_chats_db.get_chat.side_effect = [chat, None]
        service.llm_service.ainvoke.return_value = {"resolved_mode": "analyze", "response": "r",
                                                    "issues": [], "suggestions": []}

        with pytest.raises(InvalidChatError) as exc_info:
            await service.send_message(chat_id, user_id=TEST_USER_ID, message="why?")

        assert exc_info.value.chat_id == chat_id
        assert chat.messages == []

    @pytest.mark.asyncio
    async def test_followup_on_a_chat_that_is_still_there_writes_control(self, service,
                                                                        mock_chats_db):
        """The control: the case above must refuse because the chat went, not because a second
        read was introduced that no chat survives."""
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER_ID)
        mock_chats_db.get_chat.side_effect = [chat, chat]
        service.llm_service.ainvoke.return_value = {"resolved_mode": "analyze", "response": "r",
                                                    "issues": [], "suggestions": []}

        await service.send_message(chat_id, user_id=TEST_USER_ID, message="why?")

        assert [message.role for message in chat.messages] == [ChatRole.human, ChatRole.ai]

    @pytest.mark.asyncio
    async def test_followup_capacity_exceeded(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER_ID)
        chat.messages = [
            Message(chat_id=chat_id, role=ChatRole.ai,
                    content={"resolved_mode": "analyze", "response": "r",
                             "issues": [], "suggestions": []})
            for _ in range(50)
        ]
        mock_chats_db.get_chat.return_value = chat

        with pytest.raises(ChatHistoryLimitError) as exc_info:
            await service.send_message(chat_id, user_id=TEST_USER_ID, message="another message")

        assert exc_info.value.max_messages == 50

    @pytest.mark.asyncio
    async def test_followup_llm_error(self, service, mock_chats_db):
        chat_id = uuid4()
        chat = Chat(id=chat_id, title="hello", user_id=TEST_USER_ID)
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
            await service.send_message(chat_id, user_id=TEST_USER_ID, message="why?")

        assert exc_info.value is llm_exc


class TestRejectHandling:

    @pytest.mark.asyncio
    async def test_reject_raises_out_of_scope(self, service, mock_chats_db):
        llm_response = {"resolved_mode": "reject",
                        "response": "The request is outside the scope of linguistic analysis"}
        service.llm_service.ainvoke.return_value = llm_response

        with pytest.raises(OutOfScopeError):
            await service.create_chat(phrase="What is the weather?",
                                      user_id=TEST_USER_ID, lang="en")

        mock_chats_db.create_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_no_messages_persisted(self, service, mock_chats_db):
        """On reject, neither human nor AI message is persisted."""
        llm_response = {"resolved_mode": "reject",
                        "response": "Out of scope"}
        service.llm_service.ainvoke.return_value = llm_response

        with pytest.raises(OutOfScopeError):
            await service.create_chat(phrase="Tell me a joke",
                                      user_id=TEST_USER_ID, lang="en")

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

    def test_a_configured_key_with_no_examples_answers_with_an_empty_list(self, service):
        """WR-62: `create_chat` accepts any configured key, so refusing one here made the two routes
        disagree on the one membership question -- and named the key as supported while refusing it."""
        service.examples["en"] = []

        result = service.get_examples("en")

        assert (result.lang, result.examples) == ("en", [])
        assert "en" in service.supported_languages


class TestTheLlmHistoryIsOrdered:
    """`ask_llm` iterates `chat.messages`, so the relationship must carry the ORDER BY itself."""

    def test_the_messages_relationship_orders_by_the_time_ordered_id(self):
        """Without this the loader emits a bare SELECT and PostgreSQL may shuffle the turns."""
        ordering = Chat.__mapper__.relationships["messages"].order_by

        assert [str(clause) for clause in ordering] == ["messages.id"]

    def test_the_id_it_orders_by_is_the_time_ordered_one(self):
        """The control: ascending id is chronological only because `Message.id` is uuid7."""
        assert Message.model_fields["id"].default_factory is uuid7


class TestAChargedWriteThatFailsIsFindable:
    """WR-51: `charge` commits a credit in its own session and nothing reverses it, so a commit
    that fails after it bills a chat that does not exist. Not a ledger and no compensating write --
    one line an operator can match a support request against."""

    @pytest.fixture
    def errors(self, monkeypatch) -> list[tuple[str, dict]]:
        """A recording spy on the service's own logger, as `test_identity_accessors.py` does."""
        entries: list[tuple[str, dict]] = []
        monkeypatch.setattr("nativespeaker.api.services.chats.logger.error",
                            lambda event, **kw: entries.append((event, kw)))
        return entries

    @staticmethod
    def _failing_after_the_charge(service) -> None:
        """The first commit ends the read; the second is the one the charge has already paid for."""
        service.session.commit.side_effect = [None, RuntimeError("the connection dropped")]

    @pytest.mark.asyncio
    async def test_a_failed_create_names_the_user_and_the_branch(self, service, mock_chats_db,
                                                                 errors):
        service.llm_service.ainvoke.return_value = {"resolved_mode": "analyze",
                                                    "response": "ok",
                                                    "issues": [],
                                                    "suggestions": []}
        self._failing_after_the_charge(service)

        with pytest.raises(RuntimeError):
            await service.create_chat(phrase="I am going to home", user_id=TEST_USER_ID, lang="en")

        assert errors == [("charged_write_failed",
                           {"user_id": str(TEST_USER_ID), "branch": "create_chat"})]

    @pytest.mark.asyncio
    async def test_a_failed_follow_up_names_its_own_branch(self, service, mock_chats_db, errors):
        """The same on the other charged route, named apart so the two are distinguishable."""
        chat = Chat(id=uuid4(), user_id=TEST_USER_ID, title="Existing chat")
        mock_chats_db.get_chat.return_value = chat
        service.llm_service.ainvoke.return_value = {"resolved_mode": "follow_up",
                                                    "response": "ok"}
        self._failing_after_the_charge(service)

        with pytest.raises(RuntimeError):
            await service.send_message(chat_id=chat.id, user_id=TEST_USER_ID, message="Why?")

        assert errors == [("charged_write_failed",
                           {"user_id": str(TEST_USER_ID), "branch": "send_message"})]

    @pytest.mark.asyncio
    async def test_a_commit_that_succeeds_writes_no_line_control(self, service, mock_chats_db,
                                                                 errors):
        """The control: the line names a failure, so an ordinary chat must not produce one."""
        service.llm_service.ainvoke.return_value = {"resolved_mode": "analyze",
                                                    "response": "ok",
                                                    "issues": [],
                                                    "suggestions": []}

        await service.create_chat(phrase="I am going to home", user_id=TEST_USER_ID, lang="en")

        assert errors == []


class TestADiscardedAnswerTheCallerPaidForIsFindable:
    """WR-01: both late checks run after `charge` has committed a credit and after the provider has
    answered. `ChatHistoryLimitError` and `InvalidChatError` both declare `log_level = None`, so
    without this line the case is indistinguishable from a client mistake that cost nothing."""

    @pytest.fixture
    def warnings(self, monkeypatch) -> list[tuple[str, dict]]:
        """A recording spy on the service's own logger, as the sibling class above does."""
        entries: list[tuple[str, dict]] = []
        monkeypatch.setattr("nativespeaker.api.services.chats.logger.warning",
                            lambda event, **kw: entries.append((event, kw)))
        return entries

    @pytest.mark.asyncio
    async def test_a_chat_limit_reached_across_the_provider_call_names_its_branch(
            self, service, mock_chats_db, warnings):
        service.llm_service.ainvoke.return_value = {"resolved_mode": "analyze",
                                                    "response": "ok",
                                                    "issues": [],
                                                    "suggestions": []}
        # Below the limit before the commit and at it after: the concurrent case the re-read exists for.
        mock_chats_db.count_chats.side_effect = [0, service.chats_limit]

        with pytest.raises(ChatHistoryLimitError):
            await service.create_chat(phrase="I am going to home", user_id=TEST_USER_ID, lang="en")

        assert warnings == [("charged_answer_discarded",
                             {"user_id": str(TEST_USER_ID), "branch": "create_chat"})]

    @pytest.mark.asyncio
    async def test_a_chat_deleted_across_the_provider_call_names_its_own_branch(
            self, service, mock_chats_db, warnings):
        """The same on the other charged route, named apart so the two are distinguishable."""
        chat = Chat(id=uuid4(), user_id=TEST_USER_ID, title="Existing chat")
        service.llm_service.ainvoke.return_value = {"resolved_mode": "follow_up", "response": "ok"}
        # Present before the commit and gone after: the delete the re-read exists for.
        mock_chats_db.get_chat.side_effect = [chat, None]

        with pytest.raises(InvalidChatError):
            await service.send_message(chat_id=chat.id, user_id=TEST_USER_ID, message="Why?")

        assert warnings == [("charged_answer_discarded",
                             {"user_id": str(TEST_USER_ID), "branch": "send_message"})]

    @pytest.mark.asyncio
    async def test_an_answer_that_is_stored_writes_no_line_control(self, service, mock_chats_db,
                                                                   warnings):
        """The control: the line names a discarded answer, so an ordinary chat must not produce one."""
        service.llm_service.ainvoke.return_value = {"resolved_mode": "analyze",
                                                    "response": "ok",
                                                    "issues": [],
                                                    "suggestions": []}

        await service.create_chat(phrase="I am going to home", user_id=TEST_USER_ID, lang="en")

        assert warnings == []
