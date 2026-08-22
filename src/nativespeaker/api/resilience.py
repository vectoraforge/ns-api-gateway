import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, RateLimitError
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


class _AdmissionRejected(Exception):
    """Carries whatever an `on_admitted` callback raised back out through the retry loop.

    The callback runs where the provider call is about to be made, which is inside the block
    `ResiliencePolicy.ainvoke` wraps in its retry/classify handler. Without this wrapper a quota
    rejection raised by the callback would be read as a provider failure: recorded against the
    circuit breaker, retried, and finally re-raised as a `PermanentLLMError` 503 -- turning a 429
    into a 503 and tripping the breaker on a caller's exhausted allowance.

    Existing only to be unwrapped keeps `resilience.py` free of any quota import: the layer does
    not need to know what the callback does, only that its failures are not the provider's.
    """

    def __init__(self, cause: BaseException):
        super().__init__(str(cause))
        self.cause = cause


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

    async def run(self, operation: Callable[[], Awaitable],
                  on_admitted: Callable[[], Awaitable] | None = None):
        """Run `operation` under the gate, calling `on_admitted` once admission is certain.

        `on_admitted` fires after the in-flight slot AND the concurrency semaphore are held, so it
        runs only for a call this service is actually about to make. That ordering is the whole
        point: a caller refused by `_inflight_slot` (503 `QueueFullError`) or held out by the
        circuit breaker upstream must not have had it run. It is awaited before `operation` rather
        than concurrently with it, so a callback that raises stops the provider call.
        """
        async with self._inflight_slot():
            async with self._semaphore:
                if on_admitted is not None:
                    try:
                        await on_admitted()
                    except Exception as exc:
                        raise _AdmissionRejected(exc) from exc
                return await operation()


def _should_retry(exc: BaseException) -> bool:
    """`ResiliencePolicy.ainvoke`'s retry predicate: `TransientLLMError` and nothing else.

    **This is `retry_if_exception`, whereas `auth/retry.py` uses `retry_if_result`, and neither is
    a mistake.** They share one library and one idiom; the predicates differ because the two seams
    differ. The Firebase providerData lookup that module wraps *returns* a closed outcome enum and
    never raises, so only a result predicate can fire there. This seam signals by raising, so only
    an exception predicate can fire here. A reader comparing the two files should not "fix" either.

    (The adapter method's own name is deliberately not written out above: `test_adapter_interfaces`
    scans every `src/` module for adapter method names, and only `auth/` modules are exempt.)

    Reading the class rather than re-deriving the classification is deliberate: the attempt body
    below has already triaged the failure -- `_AdmissionRejected`, `QueueFullError` and
    `CircuitOpenError` leave it untouched, and everything else leaves it as exactly one of
    `TransientLLMError` / `PermanentLLMError` per `_is_transient_error`. Re-running that judgement
    here would be a second answer to one question, and the two could drift apart.
    """
    return isinstance(exc, TransientLLMError)


async def _sleep_if_positive(seconds: float) -> None:
    """The retry policy's sleep: a zero-length backoff issues no sleep call at all.

    `retry_backoff_base_seconds` is `ge=0`, so a zero schedule is a legal configuration, and the
    hand-rolled loop this replaced guarded its sleep with `if backoff > 0`. Passing `asyncio.sleep`
    straight through would instead yield to the event loop once per attempt -- the same elapsed
    time, but not the same behaviour, and `tests/unit/test_resilience_retry.py` pins the difference.
    """
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

    async def ainvoke(self, operation: Callable[[], Awaitable],
                      on_admitted: Callable[[], Awaitable] | None = None) -> Any:
        """Run `operation` under the circuit breaker, the gate and the retry policy.

        `on_admitted` is called at most ONCE across every attempt, on the first admission. A retry
        is the same caller request making a second try at the same provider call, so firing the
        callback again would charge a second credit for one request -- the exact double-spend the
        `admitted` flag below exists to prevent.
        """
        admitted = False

        async def admit_once() -> None:
            nonlocal admitted
            if admitted or on_admitted is None:
                return
            # Set BEFORE awaiting, not after: a callback that raises has still had its one
            # chance, and a retry must not call it again to find out whether it raises twice.
            admitted = True
            await on_admitted()

        async def attempt() -> Any:
            """One attempt, already triaged. Everything `_should_retry` reads is decided in here.

            tenacity evaluates its predicate *after* this returns, so the `record_failure` call and
            the transient/permanent translation have to live here rather than in a
            `retry_error_callback` -- moving them out would record a failure per policy, not per
            attempt, and would leave the predicate reading raw provider exceptions.
            """
            await self._circuit_breaker.before_call()
            try:

                async def timed_op():
                    return await asyncio.wait_for(operation(), timeout=self._timeout_seconds)

                result = await self._gate.run(timed_op, on_admitted=admit_once)
            except _AdmissionRejected:
                # Not a provider failure: no `record_failure`, no retry, no `TransientLLMError`
                # wrapping. Deliberately still wrapped at this point and unwrapped below, outside
                # the policy: if the callback's own exception were re-raised here, `_should_retry`
                # would inspect the caller's error class, and a caller raising something that
                # happens to be a `TransientLLMError` would get its rejection retried.
                raise
            except (QueueFullError, CircuitOpenError):
                raise
            except Exception as e:
                await self._circuit_breaker.record_failure()
                if _is_transient_error(e):
                    raise TransientLLMError(str(e)) from e
                raise PermanentLLMError(str(e)) from e
            await self._circuit_breaker.record_success()
            return result

        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._retry_max_attempts),
            # `multiplier * exp_base ** (attempt_number - 1)`, clamped to `max` -- byte-for-byte the
            # hand-rolled `min(backoff_max, backoff_base * 2 ** (attempt - 1))`, and
            # `TestBackoffSchedule` asserts the resulting durations rather than trusting the
            # restatement.
            wait=wait_exponential(multiplier=self._retry_backoff_base,
                                  exp_base=2,
                                  max=self._retry_backoff_max),
            retry=retry_if_exception(_should_retry),
            sleep=_sleep_if_positive,
            # Correct here precisely because there IS an original exception -- the opposite of
            # `auth/retry.py`, where a result-based retry has none and `retry_error_callback` is
            # therefore mandatory. Exhaustion re-raises the last attempt's `TransientLLMError`
            # (`__cause__` intact), so no `tenacity.RetryError` can reach a caller and no
            # fall-through guard is needed below.
            reraise=True,
        )
        try:
            return await retrying(attempt)
        except _AdmissionRejected as rejected:
            # Re-raised exactly as the callback raised it so the caller sees its own error class
            # and status -- a quota 429 stays a 429 instead of becoming a 503.
            raise rejected.cause from None
