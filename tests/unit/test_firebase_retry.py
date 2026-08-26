"""Exact attempt counts per outcome: the adapter returns rather than raises, so only a result predicate fires."""
import pytest
import tenacity

from nativespeaker.api import errors
from nativespeaker.api.auth.adapters import (
    ProviderDataEntry,
    ProviderDataOutcome,
    ProviderDataResult,
)
from nativespeaker.api.auth.firebase import (
    FIREBASE_LOOKUP_ATTEMPTS,
    LOOKUP_UNAVAILABLE_ERROR_CLASS,
    LOOKUP_UNAVAILABLE_RESULT,
    lookup_with_retry,
)
from nativespeaker.api.models.auth import AuthEventResult

ISSUER = "https://securetoken.google.com/ns-prod"
SUBJECT = "firebase-uid-1"

DEFINITIVE = (ProviderDataOutcome.ok,
              ProviderDataOutcome.user_not_found,
              ProviderDataOutcome.selection_failure)


class CountingAdapter:
    """Returns a scripted sequence and records every call; it never raises, so the predicate reads outcomes."""

    def __init__(self, *outcomes: ProviderDataOutcome) -> None:
        self.scripted = tuple(ProviderDataResult(outcome=outcome) for outcome in outcomes)
        self.calls: list[tuple[str, str]] = []

    def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        self.calls.append((issuer, subject))
        if len(self.calls) > len(self.scripted):
            # Overrunning the script is the failure this file exists to catch, so name it.
            raise AssertionError(
                f"attempt {len(self.calls)} exceeds the scripted {len(self.scripted)}")
        return self.scripted[len(self.calls) - 1]


class AsyncCountingAdapter(CountingAdapter):
    """The same fake with an async method. Plan 37-05 may offload the sync SDK call to a thread."""

    async def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:  # type: ignore[override]
        return CountingAdapter.get_user_provider_data(self, issuer, subject)


class TestAttemptCountsPerOutcome:
    """Three attempts total for retryable causes only; every other outcome is definitive."""

    def test_the_attempt_budget_is_the_71_three(self):
        """"3 attempts total -- the initial call plus up to two additional" (budgets.py:49-50)."""
        assert FIREBASE_LOOKUP_ATTEMPTS == 3

    async def test_three_retryable_failures_cost_exactly_three_attempts(self):
        adapter = CountingAdapter(*[ProviderDataOutcome.retryable_failure] * 3)

        result = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert len(adapter.calls) == 3
        assert isinstance(result, ProviderDataResult)
        assert result.outcome is ProviderDataOutcome.retryable_failure

    async def test_the_exhausted_lookup_returns_the_last_result_rather_than_raising(self):
        """`retry_error_callback` hands the third result back; `RetryError` never escapes."""
        adapter = CountingAdapter(*[ProviderDataOutcome.retryable_failure] * 3)

        result = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert result is adapter.scripted[2]

    async def test_a_retryable_failure_then_an_ok_costs_exactly_two_attempts(self):
        adapter = CountingAdapter(ProviderDataOutcome.retryable_failure, ProviderDataOutcome.ok)

        result = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert len(adapter.calls) == 2
        assert result is adapter.scripted[1]
        assert result.outcome is ProviderDataOutcome.ok

    @pytest.mark.parametrize("outcome", DEFINITIVE, ids=lambda o: o.value)
    async def test_a_definitive_outcome_costs_exactly_one_attempt(self, outcome):
        """Retrying a definitive outcome would burn attempts proving a fact the provider already stated."""
        adapter = CountingAdapter(outcome)

        result = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert len(adapter.calls) == 1
        assert result is adapter.scripted[0]

    @pytest.mark.parametrize("outcome", list(ProviderDataOutcome), ids=lambda o: o.value)
    async def test_no_outcome_lets_a_retry_error_escape(self, outcome):
        """All four members of the closed outcome set, including the exhaustion path."""
        adapter = CountingAdapter(*[outcome] * FIREBASE_LOOKUP_ATTEMPTS)

        try:
            result = await lookup_with_retry(adapter, ISSUER, SUBJECT)
        except tenacity.RetryError as exc:  # pragma: no cover - the assertion this test exists for
            pytest.fail(f"RetryError escaped for {outcome.value}: {exc!r}")

        assert isinstance(result, ProviderDataResult)

    async def test_the_lookup_forwards_the_issuer_and_subject_on_every_attempt(self):
        """Selection happens per call, so no attempt may reach an ambient client."""
        adapter = CountingAdapter(*[ProviderDataOutcome.retryable_failure] * 3)

        await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert adapter.calls == [(ISSUER, SUBJECT)] * 3

    async def test_an_ok_result_carries_its_entries_through_untouched(self):
        """The policy is transparent: it decides whether to call again and nothing else."""
        entries = (ProviderDataEntry(provider_id="google.com", uid="g-1"),)
        adapter = CountingAdapter(ProviderDataOutcome.ok)
        adapter.scripted = (ProviderDataResult(outcome=ProviderDataOutcome.ok, entries=entries),)

        result = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert result.entries == entries

    async def test_the_policy_is_agnostic_to_a_sync_or_async_adapter(self):
        """`AsyncRetrying` awaits a coroutine function and calls a plain one; both count the same."""
        adapter = AsyncCountingAdapter(ProviderDataOutcome.retryable_failure,
                                       ProviderDataOutcome.ok)

        result = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert len(adapter.calls) == 2
        assert result.outcome is ProviderDataOutcome.ok


class TestTheExhaustionMapping:
    """Two named constants rather than a literal repeated at each read point, because a test can pin a name."""

    def test_the_internal_result_is_firebase_lookup_unavailable(self):
        assert LOOKUP_UNAVAILABLE_RESULT is AuthEventResult.firebase_lookup_unavailable

    def test_the_error_class_is_verification_temporarily_unavailable(self):
        assert LOOKUP_UNAVAILABLE_ERROR_CLASS is errors.VERIFICATION_TEMPORARILY_UNAVAILABLE

    def test_the_client_facing_pair_is_a_503_with_the_matching_code(self):
        """Byte-for-byte what budgets.py:65-66 declared, so nothing about the wire moved."""
        assert LOOKUP_UNAVAILABLE_ERROR_CLASS.status == 503
        assert LOOKUP_UNAVAILABLE_ERROR_CLASS.code == "verification_temporarily_unavailable"

    def test_exhaustion_is_not_the_user_not_found_mapping(self):
        """The two are routed apart: unavailable is a 503, unresolved is a 401."""
        assert LOOKUP_UNAVAILABLE_RESULT is not AuthEventResult.firebase_user_unresolved
