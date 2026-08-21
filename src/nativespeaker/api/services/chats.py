from uuid import UUID, uuid4

import orjson
from langchain_core.messages import AIMessage, HumanMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.database import ChatsDB
from nativespeaker.api.errors import (
    AnalysisError,
    ChatHistoryLimitError,
    InvalidChatError,
    OutOfScopeError,
    UnsupportedLanguageError,
)
from nativespeaker.api.models import Chat, ChatRole, Message, User
from nativespeaker.api.models.api import ExamplesResponse
from nativespeaker.api.models.llm import AnalyzeInput, AnalyzeResponse, FollowUpInput, FollowUpResponse
from nativespeaker.api.services.llm import LLMService


class ChatService:

    def __init__(self,
                 db: AsyncSession,
                 llm_service: LLMService,
                 examples: dict[str, list[str]],
                 messages_limit: int,
                 chats_limit: int) -> None:
        self.llm_service = llm_service
        self.chats_db = ChatsDB(db)
        self.examples = examples
        self.messages_limit = messages_limit
        self.chats_limit = chats_limit

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

        llm_response = await self.llm_service.ainvoke(
            history=history,
            content=orjson.dumps(message.content).decode(),
            lang=lang_directive)

        resolved_mode = llm_response.get("resolved_mode")
        if resolved_mode == "reject":
            raise OutOfScopeError()
        elif resolved_mode == "analyze":
            AnalyzeResponse.model_validate(llm_response)
        elif resolved_mode == "follow_up":
            FollowUpResponse.model_validate(llm_response)
        else:
            raise AnalysisError(f"Unexpected resolved_mode: {resolved_mode}")

        return Message(chat_id=chat.id, role=ChatRole.ai, content=llm_response)

    async def create_chat(self,
                          user: User,
                          phrase: str,
                          context: str | None = None,
                          lang: str | None = None) -> Message:
        if lang and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        chats_count = await self.chats_db.count_chats(user.id)
        if chats_count >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)

        chat = Chat(id=uuid4(), user_id=user.id, title=phrase, lang=lang)
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
                           user: User,
                           message: str) -> Message:
        chat = await self.chats_db.get_chat(chat_id, user.id)
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
