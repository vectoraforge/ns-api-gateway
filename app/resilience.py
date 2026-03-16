import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from app.config import ResilienceConfig
from app.exceptions import CircuitOpenError, PermanentLLMError, QueueFullError, TransientLLMError

from openai import (APIConnectionError,
                    APIStatusError,
                    APITimeoutError,
                    InternalServerError,
                    RateLimitError)


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


class ResiliencePolicy:
    def __init__(self, config: ResilienceConfig):
        self._circuit_breaker = CircuitBreaker(failure_threshold=config.circuit_breaker_failure_threshold,
                                               reset_seconds=config.circuit_breaker_reset_seconds)
        self._gate = LLMExecutionGate(max_concurrency=config.pool_size,
                                      max_queue=config.queue_size,
                                      retry_after_seconds=config.queue_retry_after_seconds)
        self._timeout_seconds = config.timeout_seconds
        self._retry_max_attempts = config.retry_max_attempts
        self._retry_backoff_base = config.retry_backoff_base_seconds
        self._retry_backoff_max = config.retry_backoff_max_seconds

    async def ainvoke(self, operation: Callable[[], Awaitable]) -> Any:
        for attempt in range(1, self._retry_max_attempts + 1):
            await self._circuit_breaker.before_call()
            try:

                async def timed_op():
                    return await asyncio.wait_for(operation(), timeout=self._timeout_seconds)

                result = await self._gate.run(timed_op)
                await self._circuit_breaker.record_success()
                return result
            except (QueueFullError, CircuitOpenError):
                raise
            except Exception as e:
                await self._circuit_breaker.record_failure()
                if attempt >= self._retry_max_attempts or not _is_transient_error(e):
                    if _is_transient_error(e):
                        raise TransientLLMError(str(e)) from e
                    raise PermanentLLMError(str(e)) from e
                backoff = min(self._retry_backoff_max,
                              self._retry_backoff_base * (2 ** (attempt - 1)))
                if backoff > 0:
                    await asyncio.sleep(backoff)
        raise TransientLLMError("LLM request failed after all retries")
