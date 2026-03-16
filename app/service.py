import json
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import AppConfig
from app.database.chats import ChatsDB
from app.models import Chat, Role, Message, HumanContent, AIContent
from app.exceptions import ChatHistoryLimitError, InvalidChatError, UnsupportedLanguageError
from app.resilience import ResiliencePolicy
from app.api.schema import ChatResponseLLM, MessageResponse, ExamplesResponse


def create_chain(llm, prompt: str):
    structured_llm = llm.with_structured_output(ChatResponseLLM, method="json_schema", strict=True)
    prompt_template = ChatPromptTemplate.from_messages([("system", prompt),
                                                        MessagesPlaceholder("history"),
                                                        ("human", "{content}")])
    return prompt_template | structured_llm


class ChatService:

    def __init__(self,
                 chain,
                 policy: ResiliencePolicy,
                 config: AppConfig,
                 db) -> None:
        self.chain = chain
        self.policy = policy
        self.config = config
        self.chats_db = ChatsDB(db)
        self.supported_languages = list(config.examples.keys())
        self.examples = config.examples

    async def ask_llm(self, chat: Chat, message: Message) -> Message:
        lang_directive = chat.lang or "various languages (autodetect)"
        history = []
        for message in chat.messages:
            if message.role == Role.human:
                history.append(HumanMessage(content=message.content))
            else:
                history.append(AIMessage(content=message.content))

        llm_response = await self.policy.ainvoke(
            lambda: self.chain.ainvoke({"history": history,
                                        "content": message.content,
                                        "lang": lang_directive})
        )
        return Message(chat_id=chat.id, role=Role.ai, content=AIContent(**llm_response))

    async def create_chat(self,
                          user_id: str,
                          phrase: str,
                          comment: str | None = None,
                          lang: str | None = None) -> Message:
        if lang and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)

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

        if len(chat.ai_messages) + 1 > self.config.history_max_messages:
            raise ChatHistoryLimitError(self.config.history_max_messages)

        human_message = Message(chat_id=chat.id, role=Role.human,
                                content=HumanContent(comment=content))
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

    async def get_chat_list(self, user_id: str) -> list[Chat]:
        return await self.chats_db.list_chats(user_id, self.config.chat_list_limit)

    async def delete_chat(self, chat_id: UUID, user_id: str) -> None:
        chats_deleted = await self.chats_db.delete(chat_id, user_id)
        if chats_deleted == 0:
            raise InvalidChatError(chat_id)

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)
        return ExamplesResponse(lang=lang, examples=examples)
