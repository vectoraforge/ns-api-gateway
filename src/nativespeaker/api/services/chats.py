from datetime import datetime
from uuid import UUID

import orjson
import structlog
from langchain_core.messages import AIMessage, HumanMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud import ChatsDB
from nativespeaker.api.errors import (
    AnalysisError,
    ChatHistoryLimitError,
    InvalidChatError,
    OutOfScopeError,
    UnsupportedLanguageError,
)
from nativespeaker.api.resilience import Admitted
from nativespeaker.api.schemas.api import ExamplesResponse
from nativespeaker.api.schemas.llm import AnalyzeInput, AnalyzeResponse, FollowUpInput, FollowUpResponse
from nativespeaker.api.services.llm import LLMService
from nativespeaker.api.services.quota import QuotaService
from nativespeaker.api.tables import Chat, ChatRole, Message

logger = structlog.get_logger()


class ChatService:

    def __init__(self,
                 db: AsyncSession,
                 llm_service: LLMService,
                 examples: dict[str, list[str]],
                 messages_limit: int,
                 chats_limit: int,
                 quota_service: QuotaService,
                 evaluated_at: datetime) -> None:
        self.llm_service = llm_service
        self.session = db
        self.chats_db = ChatsDB(db)
        self.examples = examples
        self.messages_limit = messages_limit
        self.chats_limit = chats_limit
        # Required with no default: a `None` here would serve both quota-checked POSTs for free and fail nothing.
        self.quota_service = quota_service
        self.evaluated_at = evaluated_at

    @property
    def supported_languages(self) -> list[str]:
        return list(self.examples.keys())

    async def ask_llm(self, chat: Chat, message: Message, admitted: Admitted) -> Message:
        lang_directive = chat.lang or "various languages (autodetect)"
        history = []
        for history_msg in chat.messages:
            if history_msg.role == ChatRole.human:
                history.append(HumanMessage(content=orjson.dumps(history_msg.content).decode()))
            else:
                history.append(AIMessage(content=orjson.dumps(history_msg.content).decode()))

        llm_response = await self.llm_service.ainvoke(
            history=history,
            content=orjson.dumps(message.content).decode(),
            lang=lang_directive,
            admitted=admitted)

        resolved_mode = llm_response.get("resolved_mode")
        if resolved_mode == "reject":
            raise OutOfScopeError()
        elif resolved_mode == "analyze":
            validated: AnalyzeResponse | FollowUpResponse = \
                AnalyzeResponse.model_validate(llm_response)
        elif resolved_mode == "follow_up":
            validated = FollowUpResponse.model_validate(llm_response)
        else:
            raise AnalysisError(f"Unexpected resolved_mode: {resolved_mode}")

        # The validated model is persisted, not the raw dict: that materialises the list defaults and drops extra keys.
        return Message(chat_id=chat.id, role=ChatRole.ai, content=validated.model_dump())

    async def create_chat(self,
                          user_id: UUID,
                          phrase: str,
                          context: str | None = None,
                          lang: str | None = None) -> Message:
        # Absence is `None` and nothing else here: a truthiness test spelled it two ways and let
        # the empty string through the one check that names the supported set.
        if lang is not None and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        chats_count = await self.chats_db.count_chats(user_id)
        if chats_count >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)

        chat = Chat(user_id=user_id, title=phrase, lang=lang)
        input_model = AnalyzeInput(phrase=phrase, context=context)
        human_message = Message(chat_id=chat.id, role=ChatRole.human,
                                content=input_model.model_dump(exclude_none=True))
        # Ends the read above and returns its connection, so no request holds one across the provider call.
        await self.session.commit()
        async with self.llm_service.admission() as admitted:
            await self.quota_service.charge(user_id=user_id, evaluated_at=self.evaluated_at)
            ai_message = await self.ask_llm(chat, human_message, admitted)

        # Re-read in the transaction that writes, as `send_message` re-reads its chat below: the
        # count above was taken before the commit that ended its transaction and before the provider
        # round trip, so every concurrent request on an account one below the limit passed it.
        if await self.chats_db.count_chats(user_id) >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)

        chat.messages.append(human_message)
        chat.messages.append(ai_message)
        self.chats_db.create_chat(chat)
        # Deliberate commit: `charge` above spent a monthly credit in its own session and has already
        # committed it, so answering before these rows are durable can bill for a chat that never existed.
        await self._commit_the_charged_write(user_id, branch="create_chat")

        return ai_message

    async def send_message(self,
                           chat_id: UUID,
                           user_id: UUID,
                           message: str) -> Message:
        chat = await self.chats_db.get_chat(chat_id, user_id)
        if chat is None:
            raise InvalidChatError(chat_id)

        if len(chat.ai_messages) + 1 > self.messages_limit:
            raise ChatHistoryLimitError(self.messages_limit)

        input_model = FollowUpInput(message=message)
        human_message = Message(chat_id=chat.id, role=ChatRole.human,
                                content=input_model.model_dump(exclude_none=True))
        # Ends the read above and returns its connection; `expire_on_commit=False` keeps `chat` readable.
        await self.session.commit()
        async with self.llm_service.admission() as admitted:
            await self.quota_service.charge(user_id=user_id, evaluated_at=self.evaluated_at)
            ai_message = await self.ask_llm(chat=chat, message=human_message, admitted=admitted)

        # Re-read in the transaction that writes: a delete across the provider call orphans the inserts below.
        if await self.chats_db.get_chat(chat_id, user_id) is None:
            raise InvalidChatError(chat_id)

        chat.messages.append(human_message)
        chat.messages.append(ai_message)
        # Deliberate commit, as in `create_chat`: the credit is already spent when this returns.
        await self._commit_the_charged_write(user_id, branch="send_message")

        return ai_message

    async def _commit_the_charged_write(self, user_id: UUID, *, branch: str) -> None:
        """Commit the rows this request charged for, naming the spent credit if the commit fails."""
        try:
            await self.session.commit()
        except Exception:
            # Logged and re-raised unchanged: the credit is committed, so this line is all that finds the case.
            logger.error("charged_write_failed", user_id=str(user_id), branch=branch)
            raise

    async def get_messages(self,
                           chat_id: UUID,
                           user_id: UUID) -> list[Message]:
        messages = await self.chats_db.get_messages(chat_id=chat_id, user_id=user_id)
        if not messages:
            raise InvalidChatError(chat_id)

        return messages

    async def list_chats(self, user_id: UUID) -> list[Chat]:
        return await self.chats_db.list_chats(user_id)

    async def delete_chat(self, chat_id: UUID, user_id: UUID) -> None:
        chats_deleted = await self.chats_db.delete(chat_id, user_id)
        if chats_deleted == 0:
            raise InvalidChatError(chat_id)
        # Deliberate commit: a 204 states the chat is gone, so it must be gone before the route answers.
        await self.session.commit()

    def get_examples(self, lang: str) -> ExamplesResponse:
        # Membership, never truthiness: `supported_languages` is the configured keys, so testing the
        # value refused a key `create_chat` accepts while naming it as supported in the same refusal.
        if lang not in self.examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)
        return ExamplesResponse(lang=lang, examples=self.examples[lang])
