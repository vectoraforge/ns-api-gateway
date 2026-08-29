from uuid import UUID, uuid4

import orjson
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
from nativespeaker.api.tables import Chat, ChatRole, Message
from nativespeaker.api.schemas.api import ExamplesResponse
from nativespeaker.api.schemas.llm import AnalyzeInput, AnalyzeResponse, FollowUpInput, FollowUpResponse
from nativespeaker.api.quota import QuotaGate
from nativespeaker.api.services.llm import LLMService


class ChatService:

    def __init__(self,
                 db: AsyncSession,
                 llm_service: LLMService,
                 examples: dict[str, list[str]],
                 messages_limit: int,
                 chats_limit: int,
                 quota_gate: QuotaGate) -> None:
        self.llm_service = llm_service
        self.chats_db = ChatsDB(db)
        self.examples = examples
        self.messages_limit = messages_limit
        self.chats_limit = chats_limit
        # Required with no default: a `None` here would serve both quota-checked POSTs for free and fail nothing.
        self.quota_gate = quota_gate

    @property
    def supported_languages(self) -> list[str]:
        return list(self.examples.keys())

    async def ask_llm(self, chat: Chat, message: Message) -> Message:
        lang_directive = chat.lang or "various languages (autodetect)"
        history = []
        for history_msg in chat.messages:
            if history_msg.role == ChatRole.human:
                history.append(HumanMessage(content=orjson.dumps(history_msg.content).decode()))
            else:
                history.append(AIMessage(content=orjson.dumps(history_msg.content).decode()))

        # The charge is handed to the resilience layer: it fires after this service's rejections and after admission.
        async def charge() -> None:
            # `chat.user_id`, not a parameter: the charge lands on the owner of the chat being served.
            await self.quota_gate.charge(chat.user_id)

        llm_response = await self.llm_service.ainvoke(
            history=history,
            content=orjson.dumps(message.content).decode(),
            lang=lang_directive,
            on_admitted=charge)

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
        if lang and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        chats_count = await self.chats_db.count_chats(user_id)
        if chats_count >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)

        chat = Chat(id=uuid4(), user_id=user_id, title=phrase, lang=lang)
        input_model = AnalyzeInput(phrase=phrase, context=context)
        human_message = Message(chat_id=chat.id, role=ChatRole.human,
                                content=input_model.model_dump(exclude_none=True))
        ai_message = await self.ask_llm(chat, human_message)

        chat.messages.append(human_message)
        chat.messages.append(ai_message)
        self.chats_db.create_chat(chat)

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
        ai_message = await self.ask_llm(chat=chat, message=human_message)

        chat.messages.append(human_message)
        chat.messages.append(ai_message)

        return ai_message

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

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)
        return ExamplesResponse(lang=lang, examples=examples)
