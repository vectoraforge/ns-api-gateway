import json
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import AppConfig
from app.database.chats import ChatsDB
from app.database.models import Chat, Role
from app.exceptions import ChatHistoryLimitError, InvalidChatError, UnsupportedLanguageError
from app.resilience import ResiliencePolicy
from app.schema import ChatMessagesResponse, ChatResponse, ChatResponseLLM, ExamplesResponse, MessageResponse


def create_chain(llm, prompt: str):
    structured_llm = llm.with_structured_output(ChatResponseLLM,
                                                 method="json_schema",
                                                 strict=True)
    prompt_template = ChatPromptTemplate.from_messages([("system", prompt),
                                                        MessagesPlaceholder("history")])
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

    async def create_chat(self,
                          phrase: str,
                          user_id: str,
                          comment: str | None = None,
                          lang: str | None = None) -> ChatResponse:
        if lang and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        parts = [f"<phrase>{phrase}</phrase>"]
        if comment:
            parts.append(f"<comment>{comment}</comment>")
        input_text = "".join(parts)

        lang_directive = lang or "various languages (autodetect)"
        history = [HumanMessage(content=input_text)]

        response = await self.policy.ainvoke(
            lambda h=history, ld=lang_directive: self.chain.ainvoke({"history": h,
                                                                     "lang": ld})
        )

        chat_id = uuid4()
        await self.chats_db.create(chat_id, phrase, user_id, comment, lang)
        await self.chats_db.save_message(chat_id, Role.ai, json.dumps(response.model_dump()))

        return ChatResponse(chat_id=chat_id, **response.model_dump())

    async def followup(self,
                       chat_id: UUID,
                       content: str,
                       user_id: str) -> ChatResponse:
        chat, db_messages = await self.chats_db.get_history(chat_id, user_id)
        if chat is None:
            raise InvalidChatError(chat_id)

        history = self._build_history(chat, db_messages)

        ai_count = sum(1 for role, _ in db_messages if role == Role.ai)
        if ai_count + 1 > self.config.history_max_messages:
            raise ChatHistoryLimitError(self.config.history_max_messages)

        lang_directive = chat.lang or "various languages (autodetect)"
        history.append(HumanMessage(content=f"<comment>{content}</comment>"))

        response = await self.policy.ainvoke(
            lambda h=history, ld=lang_directive: self.chain.ainvoke({"history": h,
                                                                     "lang": ld})
        )

        await self.chats_db.save_message(chat_id, Role.human, content)
        await self.chats_db.save_message(chat_id, Role.ai, json.dumps(response.model_dump()))

        return ChatResponse(chat_id=chat_id, **response.model_dump())

    def _build_history(self,
                       chat: Chat,
                       db_messages: list[tuple[Role, str]]) -> list[HumanMessage | AIMessage]:
        history: list[HumanMessage | AIMessage] = []

        parts = [f"<phrase>{chat.phrase}</phrase>"]
        if chat.comment:
            parts.append(f"<comment>{chat.comment}</comment>")
        history.append(HumanMessage(content="".join(parts)))

        for role, content in db_messages:
            if role == Role.ai:
                history.append(AIMessage(content=content))
            else:
                history.append(HumanMessage(content=f"<comment>{content}</comment>"))

        return history

    async def get_messages(self,
                           chat_id: UUID,
                           user_id: str,
                           limit: int,
                           cursor: str | None = None) -> ChatMessagesResponse:
        chat, messages, next_cursor = await self.chats_db.get_messages(chat_id=chat_id,
                                                                       user_id=user_id,
                                                                       limit=limit,
                                                                       cursor=cursor)
        if chat is None:
            raise InvalidChatError(chat_id)

        items = [MessageResponse(id=m.id,
                                 role=m.role,
                                 content=m.content,
                                 created_at=m.created_at)
                 for m in messages]
        return ChatMessagesResponse(id=chat.id,
                                    phrase=chat.phrase,
                                    comment=chat.comment,
                                    lang=chat.lang,
                                    created_at=chat.created_at,
                                    messages=items,
                                    next_cursor=next_cursor)

    async def get_chat_list(self, user_id: str) -> list[Chat]:
        return await self.chats_db.list_chats(user_id, self.config.chat_list_limit)

    async def delete_chat(self, chat_id: UUID, user_id: str) -> None:
        rowcount = await self.chats_db.delete(chat_id, user_id)
        if rowcount == 0:
            raise InvalidChatError(chat_id)

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)
        return ExamplesResponse(lang=lang, examples=examples)
