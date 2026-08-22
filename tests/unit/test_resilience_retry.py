"""`ResiliencePolicy.ainvoke`'s retry contract, pinned by counts and classes (37 D-05).

This is a **characterization** suite: it was written and made green against the hand-rolled
`for attempt in range(...)` loop *before* that loop was converted to `tenacity`, so a behavioural
drift introduced by the conversion is a red test here rather than a production incident on
`POST /chats`.

It exists because nothing else covers this code. `tests/unit/test_services.py` mocks
`llm_service` wholesale -- `tests/unit/conftest.py` says so in as many words -- so the real
`on_admitted` callback never fires there and the resilience layer is never entered. The plan
described `test_services.py` as this conversion's primary oracle for the once-only contract; it is
not one, and before this file the only coverage of the once-only rule lived in `tests/e2e/`,
behind real infrastructure. That is the gap this file closes.

Three behaviours are the whole point, and each is a way to lose a user's money or the product's
primary route:

1. **`on_admitted` fires at most once across every attempt.** It debits a paid allowance, so a
   second fire is a second charge for one request (T-37-20). A callback that *raises* has still
   had its one chance -- the flag is set before the await, deliberately -- so a retry must not
   call it again to find out whether it raises twice.
2. **A permanent error costs exactly one provider call** (T-37-21). A predicate that ignores
   `_is_transient_error` turns every permanent failure into three calls.
3. **The `_AdmissionRejected` path records no circuit-breaker failure** (T-37-22). It is the
   caller's own callback refusing, not the provider; counting it would let one caller's exhausted
   allowance trip the breaker and take the route down for everyone.

Every assertion below is a count or an exception class. The breaker is *wrapped*, never replaced,
so its own state transitions stay real -- `test_circuit_open_propagates_unwrapped` depends on the
real breaker actually opening.
"""
import asyncio

import pytest

from nativespeaker.api.config import ResilienceConfig
from nativespeaker.api.errors import (
    CircuitOpenError,
    PermanentLLMError,
    QueueFullError,
    QuotaExceededError,
    TransientLLMError,
)
from nativespeaker.api.resilience import ResiliencePolicy

MAX_ATTEMPTS = 3
BACKOFF_BASE = 0.5
BACKOFF_MAX = 1.5

# `TimeoutError` is `asyncio.TimeoutError` since 3.11 -- the same object `_is_transient_error`
# tests first. A real class, not a mock, so the predicate is exercised rather than stubbed.
TRANSIENT = TimeoutError
# Nothing in `_is_transient_error` matches a bare ValueError: no timeout base, no openai class, no
# `status_code`, no `response.status_code`. It is the permanent case by construction.
PERMANENT = ValueError


def make_config(**overrides) -> ResilienceConfig:
    """A config whose gate never rejects and whose breaker never opens, unless a case says so.

    Isolating one seam at a time is the point: with `pool_size`/`queue_size` roomy and the failure
    threshold far above any single case's failure count, a retry-count assertion cannot be
    satisfied (or broken) by the gate or the breaker instead of the retry policy.
    """
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
    """An async operation that raises or returns a scripted step per call, and counts its calls.

    The last step repeats, so `ScriptedOperation(TRANSIENT)` fails on every attempt. Steps are
    exception *classes*, not instances: a fresh instance per call keeps the `__context__` chain
    that `raise ... from e` builds free of self-reference.
    """

    def __init__(self, *steps):
        self.steps = steps
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        step = self.steps[min(self.calls - 1, len(self.steps) - 1)]
        if isinstance(step, type) and issubclass(step, BaseException):
            raise step(f"scripted failure on call {self.calls}")
        return step


class CountingCallback:
    """An `on_admitted` that counts every fire, and optionally raises a caller-owned error.

    The count is what proves the once-only rule; `raises` is what proves a raising callback is
    still spent.
    """

    def __init__(self, raises: BaseException | None = None):
        self.calls = 0
        self.raises = raises

    async def __call__(self) -> None:
        self.calls += 1
        if self.raises is not None:
            raise self.raises


class BreakerSpy:
    """Counts `record_failure` / `record_success` by wrapping the real methods on the real breaker.

    Wrapping rather than replacing is load-bearing: the breaker's own failure counting and opening
    must keep happening, because `test_circuit_open_propagates_unwrapped` drives it through a real
    open transition rather than asserting against a stub.
    """

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
    """Record every backoff duration instead of waiting it out; returns the list of durations.

    Patching the `asyncio` module attribute (rather than a name bound inside `resilience`) keeps
    this working across the conversion: the hand-rolled loop and the converted policy both reach
    `asyncio.sleep` by attribute lookup at call time. Delegating to a real zero-second sleep
    preserves the event-loop yield, so concurrency-shaped behaviour is unchanged while the whole
    file stays well inside the 30 s feedback budget.
    """
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


class TestOnAdmittedFiresAtMostOnce:
    """T-37-20. Each case is one request; `admit.calls` must be 1 in all of them, never 2."""

    async def test_fires_once_when_the_first_attempt_succeeds(self, policy, spy, sleeps):
        operation = ScriptedOperation("ok")
        admit = CountingCallback()

        assert await policy.ainvoke(operation, on_admitted=admit) == "ok"

        assert admit.calls == 1
        assert operation.calls == 1
        assert (spy.successes, spy.failures) == (1, 0)
        assert sleeps == []

    async def test_fires_once_when_a_transient_first_attempt_is_retried(self, policy, spy, sleeps):
        operation = ScriptedOperation(TRANSIENT, "ok")
        admit = CountingCallback()

        assert await policy.ainvoke(operation, on_admitted=admit) == "ok"

        # Two provider calls, one charge. Firing again on the retry is the double-spend.
        assert admit.calls == 1
        assert operation.calls == 2
        assert (spy.successes, spy.failures) == (1, 1)

    async def test_fires_once_when_every_attempt_fails(self, policy, spy, sleeps):
        operation = ScriptedOperation(TRANSIENT)
        admit = CountingCallback()

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(operation, on_admitted=admit)

        assert admit.calls == 1
        assert operation.calls == MAX_ATTEMPTS

    async def test_a_raising_callback_is_spent_and_never_re_invoked(self, policy, spy, sleeps):
        rejection = QuotaExceededError("allowance used up")
        admit = CountingCallback(raises=rejection)
        operation = ScriptedOperation("ok")

        with pytest.raises(QuotaExceededError) as exc_info:
            await policy.ainvoke(operation, on_admitted=admit)

        # The caller's own class and instance, not a TransientLLMError and not a PermanentLLMError:
        # `_AdmissionRejected` is unwrapped, so a 429 stays a 429 instead of becoming a 503.
        assert exc_info.value is rejection
        assert exc_info.value.__cause__ is None  # `raise ... from None`
        assert admit.calls == 1

    async def test_a_raising_callback_stops_the_provider_call_and_the_breaker(self, policy, spy, sleeps):
        admit = CountingCallback(raises=QuotaExceededError("allowance used up"))
        operation = ScriptedOperation("ok")

        with pytest.raises(QuotaExceededError):
            await policy.ainvoke(operation, on_admitted=admit)

        # T-37-22: a caller's own rejection must not count against the circuit breaker, or one
        # exhausted allowance would open it for everybody.
        assert (spy.failures, spy.successes) == (0, 0)
        assert operation.calls == 0
        assert sleeps == []

    async def test_no_callback_is_a_supported_call(self, policy, spy, sleeps):
        operation = ScriptedOperation("ok")

        assert await policy.ainvoke(operation) == "ok"

        assert operation.calls == 1
        assert spy.successes == 1


class TestErrorClassification:

    async def test_transient_error_exhausts_the_budget_then_raises_transient(self, policy, spy, sleeps):
        operation = ScriptedOperation(TRANSIENT)

        with pytest.raises(TransientLLMError) as exc_info:
            await policy.ainvoke(operation, on_admitted=CountingCallback())

        assert operation.calls == MAX_ATTEMPTS
        # `__cause__` carries the last failed attempt's original exception (errors.py pins this).
        assert isinstance(exc_info.value.__cause__, TRANSIENT)

    async def test_permanent_error_raises_after_exactly_one_call(self, policy, spy, sleeps):
        operation = ScriptedOperation(PERMANENT)

        with pytest.raises(PermanentLLMError) as exc_info:
            await policy.ainvoke(operation, on_admitted=CountingCallback())

        # T-37-21: one call, not three. A predicate that ignores `_is_transient_error` triples the
        # cost and the latency of every permanent failure.
        assert operation.calls == 1
        assert isinstance(exc_info.value.__cause__, PERMANENT)
        assert sleeps == []

    async def test_a_permanent_error_after_a_transient_one_stops_immediately(self, policy, spy, sleeps):
        operation = ScriptedOperation(TRANSIENT, PERMANENT, "ok")

        with pytest.raises(PermanentLLMError):
            await policy.ainvoke(operation, on_admitted=CountingCallback())

        assert operation.calls == 2
        assert spy.failures == 2

    async def test_an_operation_timeout_is_transient(self, spy, sleeps):
        # The `asyncio.wait_for` wrapper, not a scripted raise: the timeout path is the one
        # transient case the policy produces itself rather than receiving from the provider.
        policy = ResiliencePolicy(make_config(timeout_seconds=0.01))
        BreakerSpy(policy)
        calls = 0

        async def slow_operation():
            nonlocal calls
            calls += 1
            await asyncio.get_running_loop().create_future()  # never resolves

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(slow_operation, on_admitted=CountingCallback())

        assert calls == MAX_ATTEMPTS


class TestGateAndBreakerErrorsAreNeverWrapped:
    """`QueueFullError` and `CircuitOpenError` are already the right answer with the right status."""

    async def test_queue_full_propagates_unwrapped_and_is_not_retried(self, policy, spy, sleeps):
        # Drain every in-flight slot so the next admission is refused. Holding them with concurrent
        # blocked operations would test the same branch less deterministically.
        while True:
            try:
                policy._gate._slots.get_nowait()
            except asyncio.QueueEmpty:
                break

        operation = ScriptedOperation("ok")
        admit = CountingCallback()

        with pytest.raises(QueueFullError):
            await policy.ainvoke(operation, on_admitted=admit)

        assert operation.calls == 0
        assert admit.calls == 0  # refused before admission, so nothing is charged
        assert (spy.failures, spy.successes) == (0, 0)
        assert sleeps == []

    async def test_circuit_open_propagates_unwrapped_and_is_not_retried(self, sleeps):
        # A real open transition: one permanent failure trips a threshold of one.
        policy = ResiliencePolicy(make_config(circuit_breaker_failure_threshold=1))
        spy = BreakerSpy(policy)
        with pytest.raises(PermanentLLMError):
            await policy.ainvoke(ScriptedOperation(PERMANENT), on_admitted=CountingCallback())
        assert spy.failures == 1

        operation = ScriptedOperation("ok")
        admit = CountingCallback()

        with pytest.raises(CircuitOpenError):
            await policy.ainvoke(operation, on_admitted=admit)

        assert operation.calls == 0
        assert admit.calls == 0
        assert spy.failures == 1  # unchanged: `before_call` refusing is not a new failure


class TestFailureAccounting:

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
            await policy.ainvoke(operation, on_admitted=CountingCallback())
        except (TransientLLMError, PermanentLLMError):
            pass

        assert spy.failures == expected_failures
        assert spy.successes == expected_successes
        assert spy.failures + spy.successes == operation.calls


class TestBackoffSchedule:
    """T-37-23. The converted policy must not lengthen the wait a caller already waits."""

    async def test_schedule_matches_the_exponential_formula(self, policy, spy, sleeps):
        with pytest.raises(TransientLLMError):
            await policy.ainvoke(ScriptedOperation(TRANSIENT), on_admitted=CountingCallback())

        # One sleep between attempts, none after the last: MAX_ATTEMPTS - 1 in total.
        assert sleeps == [expected_backoff(attempt) for attempt in range(1, MAX_ATTEMPTS)]
        assert sleeps == [0.5, 1.0]

    async def test_schedule_is_capped_at_the_configured_maximum(self, spy, sleeps):
        policy = ResiliencePolicy(make_config(retry_max_attempts=5))
        BreakerSpy(policy)

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(ScriptedOperation(TRANSIENT), on_admitted=CountingCallback())

        assert sleeps == [expected_backoff(attempt) for attempt in range(1, 5)]
        # 0.5, 1.0, then the 2.0 and 4.0 the formula wants, both clamped to BACKOFF_MAX.
        assert sleeps == [0.5, 1.0, 1.5, 1.5]

    async def test_a_single_attempt_budget_never_sleeps(self, spy, sleeps):
        policy = ResiliencePolicy(make_config(retry_max_attempts=1))
        BreakerSpy(policy)
        operation = ScriptedOperation(TRANSIENT)

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(operation, on_admitted=CountingCallback())

        assert operation.calls == 1
        assert sleeps == []

    async def test_zero_backoff_records_no_sleep_at_all(self, spy, sleeps):
        # `retry_backoff_base_seconds` is `ge=0`, so 0 is a legal config. The hand-rolled loop
        # guards with `if backoff > 0`, so it issues no sleep call whatsoever -- not a sleep(0).
        policy = ResiliencePolicy(make_config(retry_backoff_base_seconds=0.0,
                                              retry_backoff_max_seconds=0.0))
        BreakerSpy(policy)
        operation = ScriptedOperation(TRANSIENT)

        with pytest.raises(TransientLLMError):
            await policy.ainvoke(operation, on_admitted=CountingCallback())

        assert operation.calls == MAX_ATTEMPTS
        assert sleeps == []
