import asyncio
from uuid import UUID, uuid4

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats import Chats
from app.exceptions import (
    ChatHistoryLimitError,
    CircuitOpenError,
    MessageTooLargeError,
    PermanentLLMError,
    QueueFullError,
    TransientLLMError,
    UnsupportedLanguageError,
)
from app.resilience import CircuitBreaker, LLMExecutionGate, _is_transient_error
from app.schema import AnalyzeResponse, AnalyzeResponseLLM, ExamplesResponse


class AnalysisService:
    def __init__(
        self,
        prompt: str,
        examples: dict[str, list[str]],
        llm: ChatOpenAI,
        gate: LLMExecutionGate,
        circuit_breaker: CircuitBreaker,
        timeout_seconds: float,
        retry_max_attempts: int,
        retry_backoff_base_seconds: float,
        retry_backoff_max_seconds: float,
        history_max_human_messages: int,
        history_max_assistant_messages: int,
        message_max_chars: int,
        chats: Chats,
    ):
        self.prompt = prompt
        self.examples = examples
        self.llm = llm
        self.gate = gate
        self.circuit_breaker = circuit_breaker
        self.timeout_seconds = timeout_seconds
        self.retry_max_attempts = retry_max_attempts
        self.retry_backoff_base_seconds = retry_backoff_base_seconds
        self.retry_backoff_max_seconds = retry_backoff_max_seconds
        self.history_max_human_messages = history_max_human_messages
        self.history_max_assistant_messages = history_max_assistant_messages
        self.message_max_chars = message_max_chars
        self.chats = chats
        structured_llm = self.llm.with_structured_output(AnalyzeResponseLLM, method="json_schema", strict=True)
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

    async def _get_chat_lang(self, db: AsyncSession, chat_id: UUID, user_id: str) -> str:
        chat = await self.chats.get_chat_owned(db, chat_id, user_id)
        return chat["lang"]

    async def _ensure_history_capacity(self, db: AsyncSession, chat_id: UUID) -> None:
        counts = await self.chats.get_message_counts(db, chat_id)
        human_count = counts.get("human", 0)
        assistant_count = counts.get("assistant", 0)
        if human_count >= self.history_max_human_messages or assistant_count >= self.history_max_assistant_messages:
            raise ChatHistoryLimitError(
                max_human=self.history_max_human_messages,
                max_assistant=self.history_max_assistant_messages,
            )

    def _ensure_message_size(self, content: str, role: str) -> None:
        if len(content) > self.message_max_chars:
            raise MessageTooLargeError(role=role, limit=self.message_max_chars)

    async def _invoke(self, chain, params: dict):
        for attempt in range(1, self.retry_max_attempts + 1):
            await self.circuit_breaker.before_call()
            try:

                async def operation():
                    return await asyncio.wait_for(chain.ainvoke(params), timeout=self.timeout_seconds)

                response = await self.gate.run(operation)
                await self.circuit_breaker.record_success()
                return response
            except QueueFullError:
                raise
            except CircuitOpenError:
                raise
            except Exception as e:
                await self.circuit_breaker.record_failure()
                if attempt >= self.retry_max_attempts or not _is_transient_error(e):
                    if _is_transient_error(e):
                        raise TransientLLMError(str(e)) from e
                    else:
                        raise PermanentLLMError(str(e)) from e
                backoff = min(
                    self.retry_backoff_max_seconds,
                    self.retry_backoff_base_seconds * (2 ** (attempt - 1)),
                )
                if backoff > 0:
                    await asyncio.sleep(backoff)
        raise TransientLLMError("LLM request failed after all retries")

    async def analyze(
        self,
        db: AsyncSession,
        text: str,
        lang: str,
        user_id: str,
        chat_id: UUID | None = None,
    ) -> AnalyzeResponse:
        self._ensure_message_size(text, "user")
        if lang not in self.examples:
            raise UnsupportedLanguageError(lang=lang, supported=self.supported_languages)

        if chat_id:
            lang = await self._get_chat_lang(db, chat_id, user_id=user_id)
            await self._ensure_history_capacity(db, chat_id)
        else:
            chat_id = uuid4()
            await self.chats.create_chat(db, chat_id, lang, user_id=user_id)

        history_limit = self.history_max_human_messages + self.history_max_assistant_messages
        history = await self.chats.load_history(db, chat_id, limit=history_limit)
        response = await self._invoke(self.chain, {"lang": lang, "phrase": text, "history": history})

        assistant_payload = str(response.model_dump())
        self._ensure_message_size(assistant_payload, "assistant")
        await self.chats.save_messages(db, chat_id, f"Analyze this phrase: {text}", assistant_payload)

        return AnalyzeResponse(text=text, lang=lang, chat_id=chat_id, **response.model_dump())

    async def chat(self, db: AsyncSession, chat_id: UUID, text: str, user_id: str) -> AnalyzeResponse:
        self._ensure_message_size(text, "user")
        lang = await self._get_chat_lang(db, chat_id, user_id=user_id)
        await self._ensure_history_capacity(db, chat_id)
        history_limit = self.history_max_human_messages + self.history_max_assistant_messages
        history = await self.chats.load_history(db, chat_id, limit=history_limit)

        response = await self._invoke(self.chain, {"lang": lang, "history": history, "phrase": text})

        assistant_payload = str(response.model_dump())
        self._ensure_message_size(assistant_payload, "assistant")
        await self.chats.save_messages(db, chat_id, text, assistant_payload)

        return AnalyzeResponse(text=text, lang=lang, chat_id=chat_id, **response.model_dump())

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        return ExamplesResponse(lang=lang, examples=examples)
