from typing import Any
from uuid import UUID, uuid4

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schema import ExamplesResponse
from app.config import ModelConfig, ResilienceConfig
from app.database import ChatsDB
from app.exceptions import ChatHistoryLimitError, InvalidChatError, UnsupportedLanguageError
from app.models import AIContent, Chat, HumanContent, Message, Role
from app.resilience import ResiliencePolicy


class LLMService:
    def __init__(self,
                 model_config: ModelConfig,
                 resilence_config: ResilienceConfig,
                 system_prompt: str):
        self.llm = init_chat_model(model=model_config.name,
                                   temperature=model_config.temperature,
                                   max_tokens=model_config.max_tokens)
        self.policy = ResiliencePolicy(resilence_config)
        self.chain = self.create_chain(prompt=system_prompt)

    @staticmethod
    def create_chain(self, prompt: str) -> RunnableSerializable[dict, dict[str, Any] | BaseModel]:
        json_parser = JsonOutputParser()
        prompt_template = ChatPromptTemplate.from_messages([("system", prompt),
                                                            MessagesPlaceholder("history"),
                                                            ("human", "{content}")])
        return prompt_template | json_parser

    async def ainvoke(self, history: list[HumanMessage | AIMessage], content: str, lang: str) -> dict:
        return await self.policy.ainvoke(
            lambda: self.chain.ainvoke({"history": history, "content": content, "lang": lang})
        )


class ChatService:

    def __init__(self,
                 db: AsyncSession,
                 llm_service: LLMService,
                 examples: dict[str, list[str]],
                 messages_limit: int,
                 chats_limit) -> None:
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
            if history_msg.role == Role.human:
                history.append(HumanMessage(content=history_msg.content.model_dump_json()))
            else:
                history.append(AIMessage(content=history_msg.content.model_dump_json()))

        llm_response = await self.llm_service.ainvoke(history=history,
                                                      content=message.content.model_dump_json(),
                                                      lang=lang_directive)
        return Message(chat_id=chat.id, role=Role.ai, content=AIContent.model_validate(llm_response))

    async def create_chat(self,
                          user_id: str,
                          phrase: str,
                          comment: str | None = None,
                          lang: str | None = None) -> Message:
        if lang and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        chats_count = await self.chats_db.count_chats(user_id)
        if chats_count >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)

        chat = Chat(id=uuid4(), user_id=user_id, title=phrase, lang=lang)
        human_message = Message(chat_id=chat.id, role=Role.human,
                                content=HumanContent(phrase=phrase, comment=comment))
        ai_message = await self.ask_llm(chat, human_message)

        chat.messages.append(human_message)
        chat.messages.append(ai_message)
        self.chats_db.create_chat(chat)

        return ai_message

    async def send_message(self,
                           chat_id: UUID,
                           user_id: str,
                           content: str) -> Message:
        chat = await self.chats_db.get_chat(chat_id, user_id)
        if chat is None:
            raise InvalidChatError(chat_id)

        if len(chat.ai_messages) + 1 > self.messages_limit:
            raise ChatHistoryLimitError(self.messages_limit)

        human_message = Message(chat_id=chat.id, role=Role.human,
                                content=HumanContent(phrase=content))
        ai_message = await self.ask_llm(chat=chat, message=human_message)

        chat.messages.append(human_message)
        chat.messages.append(ai_message)

        return ai_message

    async def get_messages(self,
                           chat_id: UUID,
                           user_id: str) -> list[Message]:
        messages = await self.chats_db.get_messages(chat_id=chat_id, user_id=user_id)
        if not messages:
            raise InvalidChatError(chat_id)

        return messages

    async def list_chats(self, user_id: str) -> list[Chat]:
        return await self.chats_db.list_chats(user_id)

    async def delete_chat(self, chat_id: UUID, user_id: str) -> None:
        chats_deleted = await self.chats_db.delete(chat_id, user_id)
        if chats_deleted == 0:
            raise InvalidChatError(chat_id)

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)
        return ExamplesResponse(lang=lang, examples=examples)
