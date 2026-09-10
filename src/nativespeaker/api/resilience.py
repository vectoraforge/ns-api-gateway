import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from nativespeaker.api.config import ResilienceConfig
from nativespeaker.api.errors import CircuitOpenError, PermanentLLMError, QueueFullError, TransientLLMError


def _extract_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None


# The retry-eligible statuses, named once. A second copy is what lets the two drift apart, and the
# split would be invisible: this predicate decides whether the circuit breaker counts a failure,
# which decides whether the whole fleet answers 503.
_TRANSIENT_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
        return True
    # No `APIStatusError` arm: it read the same status off the same exception and compared it against
    # the same set, so the wider check below already answers for it and answered first either way.
    return _extract_status_code(exc) in _TRANSIENT_STATUSES


class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_seconds: int):
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._failure_count = 0
        self._opened_at: float | None = None
        # Bumped on every trip, so an attempt can stamp the state it began under. "Open right now"
        # is not that state: `before_call`'s elapsed arm clears `_opened_at` while an attempt
        # admitted before the trip is still in flight.
        self._generation = 0
        self._lock = asyncio.Lock()

    async def before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._reset_seconds:
                self._opened_at = None
                # Half-open: one failure reopens, rather than a whole fresh tally of the threshold.
                self._failure_count = self._failure_threshold - 1
                return
            retry_after = max(1, int(self._reset_seconds - elapsed))
            raise CircuitOpenError(retry_after)

    async def current_generation(self) -> int:
        """The trip counter as of now. An attempt stamps it before calling the provider."""
        async with self._lock:
            return self._generation

    async def record_success(self, generation: int) -> None:
        async with self._lock:
            if generation != self._generation:
                # An attempt in flight when the breaker tripped predates it, so its answer says
                # nothing about the provider now. Stamped rather than read from `_opened_at`: one
                # retry chain outlives `circuit_breaker_reset_seconds`, so by the time such an
                # answer lands the elapsed arm has already cleared `_opened_at` and the straggler
                # would zero a tally accumulated entirely after the reset.
                return
            self._failure_count = 0

    async def record_failure(self, generation: int) -> None:
        async with self._lock:
            if generation != self._generation or self._opened_at is not None:
                # Stamped, not read: `before_call`'s elapsed arm primes the tally at
                # `_failure_threshold - 1`, so a failure from before the trip reopened the
                # breaker on its own and the whole fleet paid another reset window of 503.
                return
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._opened_at = time.monotonic()
                self._generation += 1


class LLMExecutionGate:
    def __init__(self, max_concurrency: int, max_queue: int, retry_after_seconds: int):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        total_slots = max_concurrency + max_queue
        self._slots = asyncio.Queue(maxsize=total_slots)
        for _ in range(total_slots):
            self._slots.put_nowait(object())
        self._retry_after_seconds = retry_after_seconds

    @asynccontextmanager
    async def inflight_slot(self):
        """Hold one in-flight slot, or raise `QueueFullError`. It never waits: a full queue refuses at once."""
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

    @asynccontextmanager
    async def concurrency(self):
        """Hold one provider permit, waiting for one when the concurrency budget is spent."""
        async with self._semaphore:
            yield


# The one value `Admitted.proof` may carry. A token is proof of admission only because this object
# cannot be reached from outside the module, so a hand-built `Admitted` carries something else and
# `ainvoke` refuses it. Without this, the token was a name rather than a guarantee: `Admitted()` was
# spellable anywhere, and a caller that spelled it took no in-flight slot, so the `queue_size` bound
# and its `QueueFullError` never fired for it.
_ADMISSION = object()


@dataclass(frozen=True, slots=True)
class Admitted:
    """Proof that the breaker was closed and a slot is held. Only `ResiliencePolicy.admission` mints one:
    `proof` has exactly one accepted value and it is module-private."""

    proof: object


def _should_retry(exc: BaseException) -> bool:
    """The retry predicate: `TransientLLMError` and nothing else, already classified by the attempt body."""
    return isinstance(exc, TransientLLMError)


async def _sleep_if_positive(seconds: float) -> None:
    """The retry sleep. A zero-length backoff issues no sleep call, rather than yielding to the event loop."""
    if seconds > 0:
        await asyncio.sleep(seconds)


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

    @asynccontextmanager
    async def admission(self):
        """Admit one request: the breaker is consulted and an in-flight slot is taken. Both are instantaneous."""
        await self._circuit_breaker.before_call()
        async with self._gate.inflight_slot():
            yield Admitted(_ADMISSION)

    async def ainvoke(self, operation: Callable[[], Awaitable], admitted: Admitted) -> Any:
        """Run `operation` under one provider permit, the timeout and the retry policy, on the caller's admission."""
        if admitted.proof is not _ADMISSION:
            # A programming error, not a runtime condition: the only way here is a caller that built
            # its own token instead of entering `admission()`, and so holds no in-flight slot.
            raise RuntimeError("ainvoke was given a token `admission()` did not mint")
        attempted = False

        async def attempt() -> Any:
            """One attempt, already triaged: everything `_should_retry` reads is decided here."""
            nonlocal attempted
            # Per attempt, not once at admission: a provider declared dead mid-flight costs one
            # attempt. Never on the first one, though: the permit above is an unbounded wait, so
            # re-deciding here what `admission()` already decided refuses a request that has made
            # no provider call while its caller's quota charge -- committed against the admission
            # verdict -- stands. A charged request always reaches the provider at least once.
            if attempted:
                await self._circuit_breaker.before_call()
            attempted = True
            # Stamped here, immediately before the provider call: a trip after this instant makes
            # this attempt's answer a straggler's, and both arms below discard a straggler's answer.
            generation = await self._circuit_breaker.current_generation()
            try:
                result = await asyncio.wait_for(operation(), timeout=self._timeout_seconds)
            except (QueueFullError, CircuitOpenError):
                # First, and it must stay first: the breaker's own refusal is not the provider's failure.
                raise
            except Exception as e:
                # Everything reaching here came out of `operation` itself, so every classification is the provider's.
                if _is_transient_error(e):
                    # Counted only on this arm: the classification is the provider's, but the cause
                    # of a permanent rejection is the request -- one user's phrase refused by the
                    # content policy would otherwise open the breaker on everybody.
                    await self._circuit_breaker.record_failure(generation)
                    raise TransientLLMError(str(e)) from e
                raise PermanentLLMError(str(e)) from e
            await self._circuit_breaker.record_success(generation)
            return result

        # The permit covers all three attempts as one unit, and is taken only once the caller is
        # ready to talk to the provider -- after its quota charge has committed and released its connection.
        async with self._gate.concurrency():
            retrying = AsyncRetrying(
                stop=stop_after_attempt(self._retry_max_attempts),
                # multiplier * 2 ** (attempt - 1), clamped to max.
                wait=wait_exponential(multiplier=self._retry_backoff_base,
                                      exp_base=2,
                                      max=self._retry_backoff_max),
                retry=retry_if_exception(_should_retry),
                sleep=_sleep_if_positive,
                # Exhaustion re-raises the last attempt's `TransientLLMError`, so no `RetryError` reaches a caller.
                reraise=True,
            )
            return await retrying(attempt)
