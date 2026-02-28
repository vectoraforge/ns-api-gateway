import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from app.exceptions import CircuitOpenError, QueueFullError

try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
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
