from uuid import UUID, uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats import Chats
from app.exceptions import ChatHistoryLimitError, UnsupportedLanguageError
from app.resilience import ResiliencePolicy
from app.schema import ChatResponse, ChatResponseLLM, ExamplesResponse


class ChatService:
    def __init__(self,
                 prompt: str,
                 examples: dict[str, list[str]],
                 llm: BaseChatModel,
                 policy: ResiliencePolicy,
                 history_max_messages: int,
                 chats: Chats):
        self.prompt = prompt
        self.examples = examples
        self.llm = llm
        self.policy = policy
        self.history_max_messages = history_max_messages
        self.chats = chats
        structured_llm = self.llm.with_structured_output(ChatResponseLLM, method="json_schema", strict=True)
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", self.prompt),
                MessagesPlaceholder("history"),
                ("human", "Analyze this phrase: {phrase}"),
            ]
        )
        self.chain = prompt_template | structured_llm

    @property
    def supported_languages(self) -> list[str]:
        return list(self.examples.keys())

    async def _invoke(self, chain, params: dict):
        return await self.policy.invoke(lambda: chain.ainvoke(params))

    async def chat(self, db: AsyncSession, text: str, user_id: str,
                   lang: str | None = None,
                   chat_id: UUID | None = None) -> ChatResponse:
        if chat_id:
            history = await self.chats.load_history(db, chat_id, user_id, limit=self.history_max_messages * 2)
            if len(history) >= self.history_max_messages * 2:
                raise ChatHistoryLimitError(max_messages=self.history_max_messages)
        else:
            if lang not in self.examples:
                raise UnsupportedLanguageError(lang=lang, supported=self.supported_languages)
            chat_id = uuid4()
            history = []

        lang_directive = (
            f"You are a linguistic assistant for advanced non-native speakers of {lang}."
            if lang else ""
        )

        response = await self._invoke(
            self.chain,
            {"lang_directive": lang_directive, "phrase": text, "history": history},
        )

        assistant_payload = str(response.model_dump())

        human_content = f"Analyze this phrase: {text}"
        if not history:
            await self.chats.create_chat_with_messages(db, chat_id, user_id,
                                                       human_content, assistant_payload)
        else:
            await self.chats.save_messages(db, chat_id, human_content, assistant_payload)

        return ChatResponse(text=text, chat_id=chat_id, **response.model_dump())

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        return ExamplesResponse(lang=lang, examples=examples)
