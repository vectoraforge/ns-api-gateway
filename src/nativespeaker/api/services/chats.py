from datetime import UTC, datetime
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from nativespeaker.api.schema import ExamplesResponse
from nativespeaker.api.database import ChatsDB, UsageDB
from nativespeaker.api.exceptions import ChatHistoryLimitError, InvalidChatError, QuotaExceededError, UnsupportedLanguageError
from nativespeaker.api.models import AIContent, Chat, ChatRole, HumanContent, Message, SubscriptionPlan, User
from nativespeaker.api.services.llm import LLMService


class ChatService:

    def __init__(self,
                 db: AsyncSession,
                 llm_service: LLMService,
                 examples: dict[str, list[str]],
                 messages_limit: int,
                 chats_limit: int,
                 quotas: dict[SubscriptionPlan, int]) -> None:
        self.llm_service = llm_service
        self.chats_db = ChatsDB(db)
        self.usage_db = UsageDB(db)
        self.examples = examples
        self.messages_limit = messages_limit
        self.chats_limit = chats_limit
        self.quotas = quotas

    @property
    def supported_languages(self) -> list[str]:
        return list(self.examples.keys())

    async def ask_llm(self, chat: Chat, message: Message) -> Message:
        lang_directive = chat.lang or "various languages (autodetect)"
        history = []
        for history_msg in chat.messages:
            if history_msg.role == ChatRole.human:
                history.append(HumanMessage(content=history_msg.content.model_dump_json()))
            else:
                history.append(AIMessage(content=history_msg.content.model_dump_json()))

        llm_response = await self.llm_service.ainvoke(history=history,
                                                      content=message.content.model_dump_json(),
                                                      lang=lang_directive)
        return Message(chat_id=chat.id, role=ChatRole.ai, content=AIContent.model_validate(llm_response))

    async def create_chat(self,
                          user: User,
                          phrase: str,
                          comment: str | None = None,
                          lang: str | None = None) -> Message:
        if lang and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        chats_count = await self.chats_db.count_chats(user.id)
        if chats_count >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)

        month = datetime.now(UTC).strftime("%Y-%m")
        monthly_quota = self.quotas[user.subscription_plan]
        if not await self.usage_db.try_increment(user.id, month, monthly_quota):
            raise QuotaExceededError("Monthly quota exceeded")

        chat = Chat(id=uuid4(), user_id=user.id, title=phrase, lang=lang)
        human_message = Message(chat_id=chat.id, role=ChatRole.human,
                                content=HumanContent(phrase=phrase, comment=comment))
        ai_message = await self.ask_llm(chat, human_message)

        chat.messages.append(human_message)
        chat.messages.append(ai_message)
        self.chats_db.create_chat(chat)

        return ai_message

    async def send_message(self,
                           chat_id: UUID,
                           user: User,
                           content: str) -> Message:
        chat = await self.chats_db.get_chat(chat_id, user.id)
        if chat is None:
            raise InvalidChatError(chat_id)

        if len(chat.ai_messages) + 1 > self.messages_limit:
            raise ChatHistoryLimitError(self.messages_limit)

        month = datetime.now(UTC).strftime("%Y-%m")
        monthly_quota = self.quotas[user.subscription_plan]
        if not await self.usage_db.try_increment(user.id, month, monthly_quota):
            raise QuotaExceededError("Monthly quota exceeded")

        human_message = Message(chat_id=chat.id, role=ChatRole.human,
                                content=HumanContent(phrase=content))
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
