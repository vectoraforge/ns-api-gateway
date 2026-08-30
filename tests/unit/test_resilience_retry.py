"""A characterization suite for `ResiliencePolicy.ainvoke`: every assertion is a call count or an exception class."""
import asyncio

import pytest

from nativespeaker.api.config import ResilienceConfig
from nativespeaker.api.errors import (
    CircuitOpenError,
    PermanentLLMError,
    QueueFullError,
    TransientLLMError,
)
from nativespeaker.api.resilience import ResiliencePolicy

MAX_ATTEMPTS = 3
BACKOFF_BASE = 0.5
BACKOFF_MAX = 1.5

# A real class, not a mock, so `_is_transient_error` is exercised rather than stubbed.
TRANSIENT = TimeoutError
# Nothing in `_is_transient_error` matches a bare ValueError, so it is permanent by construction.
PERMANENT = ValueError


def make_config(**overrides) -> ResilienceConfig:
    """A config whose gate never rejects and whose breaker never opens, so a count can only move for one reason."""
    return ResilienceConfig(**{"pool_size": 4,
                               "queue_size": 8,
                               "queue_retry_after_seconds": 2,
                               "timeout_seconds": 5.0,
                               "retry_max_attempts": MAX_ATTEMPTS,
                               "retry_backoff_base_seconds": BACKOFF_BASE,
                               "retry_backoff_max_seconds": BACKOFF_MAX,
                               "circuit_breaker_failure_threshold": 100,
                               "circuit_breaker_reset_seconds": 60,
                               **overrides})


def expected_backoff(attempt: int, *, base: float = BACKOFF_BASE, cap: float = BACKOFF_MAX) -> float:
    """The hand-rolled schedule, restated once so the assertions below quote a formula, not digits."""
    return min(cap, base * (2 ** (attempt - 1)))


class ScriptedOperation:
    """An async operation raising or returning a scripted step per call; the last step repeats forever."""

    def __init__(self, *steps):
        self.steps = steps
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        step = self.steps[min(self.calls - 1, len(self.steps) - 1)]
        if isinstance(step, type) and issubclass(step, BaseException):
            raise step(f"scripted failure on call {self.calls}")
        return step


class BreakerSpy:
    """Counts by wrapping the real breaker's methods, so its own failure counting and opening keep happening."""

    def __init__(self, policy: ResiliencePolicy):
        breaker = policy._circuit_breaker
        self.failures = 0
        self.successes = 0
        real_failure = breaker.record_failure
        real_success = breaker.record_success

        async def counting_failure() -> None:
            self.failures += 1
            await real_failure()

        async def counting_success() -> None:
            self.successes += 1
            await real_success()

        breaker.record_failure = counting_failure
        breaker.record_success = counting_success


@pytest.fixture
def sleeps(monkeypatch):
    """Record every backoff duration instead of waiting it out; returns the list of durations."""
    recorded: list[float] = []
    real_sleep = asyncio.sleep

    async def recording_sleep(delay, *args, **kwargs):
        recorded.append(delay)
        return await real_sleep(0, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", recording_sleep)
    return recorded


@pytest.fixture
def policy() -> ResiliencePolicy:
    return ResiliencePolicy(make_config())


@pytest.fixture
def spy(policy) -> BreakerSpy:
    return BreakerSpy(policy)


class TestErrorClassification:

    async def test_transient_error_exhausts_the_budget_then_raises_transient(self, policy, spy, sleeps):
        operation = ScriptedOperation(TRANSIENT)

        with pytest.raises(TransientLLMError) as exc_info:
            await policy.ainvoke(operation)

        assert operation.calls == MAX_ATTEMPTS
        # `__cause__` carries the last failed attempt's original exception (error_handlers.py pins this).
        assert isinstance(exc_info.value.__cause__, TRANSIENT)

    async def test_permanent_error_raises_after_exactly_one_call(self, policy, spy, sleeps):
        operation = ScriptedOperation(PERMANENT)

        with pytest.raises(PermanentLLMError) as exc_info:
            await policy.ainvoke(operation)

        # One call, not three: a predicate ignoring `_is_transient_error` triples every permanent failure.
        assert operation.calls == 1
        assert isinstance(exc_info.value.__cause__, PERMANENT)
        assert sleeps == []

    async def test_a_permanent_error_after_a_transient_one_stops_immediately(self, policy, spy, sleeps):
        operation = ScriptedOperation(TRANSIENT, PERMANENT, "ok")

        with pytest.raises(PermanentLLMError):
            await policy.ainvoke(operation)

        assert operation.calls == 2
        assert spy.failures == 2

    async def test_an_operation_timeout_is_transient(self, spy, sleeps):
        # The timeout is the one transient case the policy produces itself rather than receiving.
        policy = ResiliencePolicy(make_config(timeout_seconds=0.01))
        BreakerSpy(policy)
        calls = 0

        async def slow_operation():
            nonlocal calls
            calls += 1
            await asyncio.get_running_loop().create_future()  # never resolves

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(slow_operation)

        assert calls == MAX_ATTEMPTS


class TestGateAndBreakerErrorsAreNeverWrapped:
    """`QueueFullError` and `CircuitOpenError` are already the right answer with the right status."""

    async def test_queue_full_propagates_unwrapped_and_is_not_retried(self, policy, spy, sleeps):
        # Drain every in-flight slot so the next admission is refused, deterministically.
        while True:
            try:
                policy._gate._slots.get_nowait()
            except asyncio.QueueEmpty:
                break

        operation = ScriptedOperation("ok")

        with pytest.raises(QueueFullError):
            await policy.ainvoke(operation)

        assert operation.calls == 0
        assert (spy.failures, spy.successes) == (0, 0)
        assert sleeps == []

    async def test_circuit_open_propagates_unwrapped_and_is_not_retried(self, sleeps):
        # A real open transition: one permanent failure trips a threshold of one.
        policy = ResiliencePolicy(make_config(circuit_breaker_failure_threshold=1))
        spy = BreakerSpy(policy)
        with pytest.raises(PermanentLLMError):
            await policy.ainvoke(ScriptedOperation(PERMANENT))
        assert spy.failures == 1

        operation = ScriptedOperation("ok")

        with pytest.raises(CircuitOpenError):
            await policy.ainvoke(operation)

        assert operation.calls == 0
        assert spy.failures == 1  # unchanged: `before_call` refusing is not a new failure


class TestFailureAccounting:

    async def test_a_successful_call_returns_the_operations_value(self, policy, spy, sleeps):
        """Carried over from the deleted admission suite, which was the only place the return value was pinned."""
        operation = ScriptedOperation("ok")

        assert await policy.ainvoke(operation) == "ok"

        assert operation.calls == 1
        assert (spy.successes, spy.failures) == (1, 0)
        assert sleeps == []

    @pytest.mark.parametrize("steps,expected_failures,expected_successes", [
        (("ok",), 0, 1),
        ((TRANSIENT, "ok"), 1, 1),
        ((TRANSIENT, TRANSIENT, "ok"), 2, 1),
        ((TRANSIENT,), MAX_ATTEMPTS, 0),
        ((PERMANENT,), 1, 0),
    ])
    async def test_record_failure_fires_once_per_failed_provider_attempt(
            self, policy, spy, sleeps, steps, expected_failures, expected_successes):
        operation = ScriptedOperation(*steps)

        try:
            await policy.ainvoke(operation)
        except (TransientLLMError, PermanentLLMError):
            pass

        assert spy.failures == expected_failures
        assert spy.successes == expected_successes
        assert spy.failures + spy.successes == operation.calls


class TestBackoffSchedule:
    """The converted policy must not lengthen the wait a caller already waits."""

    async def test_schedule_matches_the_exponential_formula(self, policy, spy, sleeps):
        with pytest.raises(TransientLLMError):
            await policy.ainvoke(ScriptedOperation(TRANSIENT))

        # One sleep between attempts, none after the last: MAX_ATTEMPTS - 1 in total.
        assert sleeps == [expected_backoff(attempt) for attempt in range(1, MAX_ATTEMPTS)]
        assert sleeps == [0.5, 1.0]

    async def test_schedule_is_capped_at_the_configured_maximum(self, spy, sleeps):
        policy = ResiliencePolicy(make_config(retry_max_attempts=5))
        BreakerSpy(policy)

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(ScriptedOperation(TRANSIENT))

        assert sleeps == [expected_backoff(attempt) for attempt in range(1, 5)]
        # 0.5, 1.0, then the 2.0 and 4.0 the formula wants, both clamped to BACKOFF_MAX.
        assert sleeps == [0.5, 1.0, 1.5, 1.5]

    async def test_a_single_attempt_budget_never_sleeps(self, spy, sleeps):
        policy = ResiliencePolicy(make_config(retry_max_attempts=1))
        BreakerSpy(policy)
        operation = ScriptedOperation(TRANSIENT)

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(operation)

        assert operation.calls == 1
        assert sleeps == []

    async def test_zero_backoff_records_no_sleep_at_all(self, spy, sleeps):
        # A base of 0 is a legal config, and it must issue no sleep call at all rather than a sleep(0).
        policy = ResiliencePolicy(make_config(retry_backoff_base_seconds=0.0,
                                              retry_backoff_max_seconds=0.0))
        BreakerSpy(policy)
        operation = ScriptedOperation(TRANSIENT)

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(operation)

        assert operation.calls == MAX_ATTEMPTS
        assert sleeps == []
