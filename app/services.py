import asyncio
import time
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats import Chats
from app.schema import AnalyzeResponse, ExamplesResponse
from app.exceptions import (
    UnsupportedLanguageError,
    AnalysisError,
    TransientLLMError,
    PermanentLLMError,
    QueueFullError,
    CircuitOpenError,
    ChatHistoryLimitError,
    MessageTooLargeError,
)

try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        RateLimitError,
        InternalServerError,
        APIStatusError,
    )
except ImportError:  # pragma: no cover - openai is a runtime dependency
    APIConnectionError = APITimeoutError = RateLimitError = InternalServerError = APIStatusError = ()


def _extract_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
        return True
    if isinstance(exc, APIStatusError):
        status = _extract_status_code(exc)
        if status in {408, 409, 429, 500, 502, 503, 504}:
            return True
    status = _extract_status_code(exc)
    if status in {408, 409, 429, 500, 502, 503, 504}:
        return True
    return False


class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_seconds: int):
        # In-memory circuit breaker: _failure_count and _opened_at are process-local.
        # In a multi-instance deployment (e.g. multiple Uvicorn workers or Kubernetes pods),
        # each instance tracks failures independently — one pod can open its circuit while
        # others remain closed, causing inconsistent behavior under load.
        #
        # Migration path for multi-instance: replace _failure_count and _opened_at with
        # Redis keys (INCR for counts, SET EX for open-until timestamp). Use a single
        # atomic Lua script or Redis transactions to keep before_call / record_failure /
        # record_success consistent. The asyncio.Lock can be removed — Redis operations
        # are serialized by the Redis server. Library: redis-py with asyncio support
        # (redis.asyncio.Redis).
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._failure_count = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._reset_seconds:
                self._opened_at = None
                self._failure_count = 0
                return
            retry_after = max(1, int(self._reset_seconds - elapsed))
            raise CircuitOpenError(retry_after)

    async def record_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            self._opened_at = None

    async def record_failure(self) -> None:
        async with self._lock:
            if self._opened_at is not None:
                return
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._opened_at = time.monotonic()


class LLMExecutionGate:
    def __init__(self, max_concurrency: int, max_queue: int, retry_after_seconds: int):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        total_slots = max_concurrency + max_queue
        self._slots = asyncio.Queue(maxsize=total_slots)
        for _ in range(total_slots):
            self._slots.put_nowait(object())
        self._retry_after_seconds = retry_after_seconds

    @asynccontextmanager
    async def _inflight_slot(self):
        try:
            token = self._slots.get_nowait()
        except asyncio.QueueEmpty as exc:
            raise QueueFullError(self._retry_after_seconds) from exc
        try:
            yield
        finally:
            try:
                self._slots.put_nowait(token)
            except asyncio.QueueFull:
                pass

    async def run(self, operation: Callable[[], Awaitable]):
        async with self._inflight_slot():
            async with self._semaphore:
                return await operation()


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

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.prompt),
            MessagesPlaceholder("history"),
            ("human", "Analyze this phrase: {phrase}"),
        ])
        chain = prompt_template | self.llm | JsonOutputParser()

        history_limit = self.history_max_human_messages + self.history_max_assistant_messages
        history = await self.chats.load_history(db, chat_id, limit=history_limit)
        response = await self._invoke(chain, {"lang": lang, "phrase": text, "history": history})

        assistant_payload = str(response)
        self._ensure_message_size(assistant_payload, "assistant")
        await self.chats.save_messages(db, chat_id, f"Analyze this phrase: {text}", assistant_payload)

        return AnalyzeResponse.model_validate({**response, "text": text, "lang": lang, "chat_id": chat_id})

    async def chat(self, db: AsyncSession, chat_id: UUID, text: str, user_id: str) -> AnalyzeResponse:
        self._ensure_message_size(text, "user")
        lang = await self._get_chat_lang(db, chat_id, user_id=user_id)
        await self._ensure_history_capacity(db, chat_id)
        history_limit = self.history_max_human_messages + self.history_max_assistant_messages
        history = await self.chats.load_history(db, chat_id, limit=history_limit)
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.prompt),
            MessagesPlaceholder("history"),
            ("human", "Analyze this phrase: {phrase}"),
        ])
        chain = prompt_template | self.llm | JsonOutputParser()

        response = await self._invoke(chain, {"lang": lang, "history": history, "phrase": text})

        assistant_payload = str(response)
        self._ensure_message_size(assistant_payload, "assistant")
        await self.chats.save_messages(db, chat_id, text, assistant_payload)

        return AnalyzeResponse.model_validate({**response, "text": text, "lang": lang, "chat_id": chat_id})

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        return ExamplesResponse(lang=lang, examples=examples)
