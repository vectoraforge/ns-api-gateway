import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats import Chats
from app.schema import AnalyzeResponse, ExamplesResponse
from app.exceptions import UnsupportedLanguageError, AnalysisError, InvalidChatError, QueueFullError


class LLMExecutionGate:
    def __init__(self, max_concurrency: int, max_queue: int, retry_after_seconds: int):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._queue = asyncio.Queue(maxsize=max_queue)
        self._retry_after_seconds = retry_after_seconds

    async def run(self, operation: Callable[[], Awaitable]):
        token_added = False
        token_removed = False
        acquired = False
        try:
            try:
                self._queue.put_nowait(object())
                token_added = True
            except asyncio.QueueFull as exc:
                raise QueueFullError(self._retry_after_seconds) from exc

            await self._semaphore.acquire()
            acquired = True

            try:
                self._queue.get_nowait()
                token_removed = True
            except asyncio.QueueEmpty:
                token_removed = True

            return await operation()
        finally:
            if acquired:
                self._semaphore.release()
            if token_added and not token_removed:
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass


class AnalysisService:
    def __init__(
        self,
        prompt: str,
        examples: dict[str, list[str]],
        llm: ChatOpenAI,
        gate: LLMExecutionGate,
        chats: Chats,
    ):
        self.prompt = prompt
        self.examples = examples
        self.llm = llm
        self.gate = gate
        self.chats = chats

    @property
    def supported_languages(self) -> list[str]:
        return list(self.examples.keys())

    async def _get_chat_lang(self, db: AsyncSession, chat_id: UUID) -> str:
        chat = await self.chats.get_chat(db, chat_id)
        if not chat:
            raise InvalidChatError(chat_id)
        return chat["lang"]

    async def _invoke(self, chain, params: dict):
        try:
            return await self.gate.run(lambda: chain.ainvoke(params))
        except Exception as e:
            raise AnalysisError(str(e)) from e

    async def analyze(self, db: AsyncSession, text: str, lang: str, chat_id: UUID | None = None) -> AnalyzeResponse:
        if lang not in self.examples:
            raise UnsupportedLanguageError(lang=lang, supported=self.supported_languages)

        if chat_id:
            lang = await self._get_chat_lang(db, chat_id)
        else:
            chat_id = uuid4()
            await self.chats.create_chat(db, chat_id, lang)

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.prompt),
            MessagesPlaceholder("history"),
            ("human", "Analyze this phrase: {phrase}"),
        ])
        chain = prompt_template | self.llm | JsonOutputParser()

        history = await self.chats.load_history(db, chat_id)
        response = await self._invoke(chain, {"lang": lang, "phrase": text, "history": history})

        await self.chats.save_messages(db, chat_id, f"Analyze this phrase: {text}", str(response))

        return AnalyzeResponse.model_validate({**response, "text": text, "lang": lang, "chat_id": chat_id})

    async def chat(self, db: AsyncSession, chat_id: UUID, text: str) -> AnalyzeResponse:
        lang = await self._get_chat_lang(db, chat_id)
        history = await self.chats.load_history(db, chat_id)

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.prompt),
            MessagesPlaceholder("history"),
            ("human", "Analyze this phrase: {phrase}"),
        ])
        chain = prompt_template | self.llm | JsonOutputParser()

        response = await self._invoke(chain, {"lang": lang, "history": history, "phrase": text})

        await self.chats.save_messages(db, chat_id, text, str(response))

        return AnalyzeResponse.model_validate({**response, "text": text, "lang": lang, "chat_id": chat_id})

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        return ExamplesResponse(lang=lang, examples=examples)
