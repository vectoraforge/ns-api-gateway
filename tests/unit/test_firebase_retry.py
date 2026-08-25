"""§7.1's Firebase providerData retry: exact attempt counts per outcome, and no escaping RetryError.

The value of this file is that it counts. `FirebaseAdminAdapter.get_user_provider_data` **returns**
a closed `ProviderDataResult` and never raises, so the only predicate that can fire is a
result-based one -- `retry_if_exception_type` would match nothing and the three-attempt budget
would silently become a one-attempt budget (T-37-04). A wrong predicate is invisible in review and
obvious here: every test below pins an exact call count, so the collapse is a red test rather than
a production 503 on the first recoverable blip.

The second thing it pins is that exhaustion **returns**. A result-based retry raises `RetryError`
on exhaustion even with `reraise=True` -- there is no original exception for `reraise` to re-raise
-- so without `retry_error_callback` the caller gets an exception it does not catch, the
`firebase_lookup_unavailable` -> `verification_temporarily_unavailable` mapping is lost, and a
503 the spec earns becomes a 500 carrying provider text (T-37-06).
"""
import pytest
import tenacity

from nativespeaker.api import errors
from nativespeaker.api.auth.adapters import (
    ProviderDataEntry,
    ProviderDataOutcome,
    ProviderDataResult,
)
from nativespeaker.api.auth.retry import (
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
    """Returns a scripted sequence of `ProviderDataResult`s and records every call.

    Sync, exactly as the `FirebaseAdminAdapter` Protocol declares the method -- and it never
    raises, which is the whole reason the policy's predicate has to read the outcome enum.
    """

    def __init__(self, *outcomes: ProviderDataOutcome) -> None:
        self.scripted = tuple(ProviderDataResult(outcome=outcome) for outcome in outcomes)
        self.calls: list[tuple[str, str]] = []

    def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        self.calls.append((issuer, subject))
        if len(self.calls) > len(self.scripted):
            # Overrunning the script is the failure this file exists to catch, so say so rather
            # than letting an IndexError describe it.
            raise AssertionError(
                f"attempt {len(self.calls)} exceeds the scripted {len(self.scripted)}")
        return self.scripted[len(self.calls) - 1]


class AsyncCountingAdapter(CountingAdapter):
    """The same fake with an async method. Plan 37-05 may offload the sync SDK call to a thread."""

    async def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:  # type: ignore[override]
        return CountingAdapter.get_user_provider_data(self, issuer, subject)


class TestAttemptCountsPerOutcome:
    """§7.1: 3 attempts total for retryable causes only; every other outcome is definitive."""

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
        """`user_not_found` and `selection_failure` spend no further attempt; `ok` is a success.

        Retrying `user_not_found` would burn two attempts proving a fact Firebase already stated,
        and it maps to `firebase_user_unresolved` -> `auth_required`, not to a 503 (T-37-05).
        """
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
        """§7.1: selection happens per call, so no attempt may reach an ambient client."""
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
    """What `budgets.BudgetExhausted` carried as class data, now as two named module constants.

    Naming them is the point: a literal repeated at each of §7.1's five read points is a mapping
    that drifts four ways, and a test can pin a name but not a literal.
    """

    def test_the_internal_result_is_firebase_lookup_unavailable(self):
        assert LOOKUP_UNAVAILABLE_RESULT is AuthEventResult.firebase_lookup_unavailable

    def test_the_error_class_is_verification_temporarily_unavailable(self):
        assert LOOKUP_UNAVAILABLE_ERROR_CLASS is errors.VERIFICATION_TEMPORARILY_UNAVAILABLE

    def test_the_client_facing_pair_is_a_503_with_the_matching_code(self):
        """Byte-for-byte what budgets.py:65-66 declared, so nothing about the wire moved."""
        assert LOOKUP_UNAVAILABLE_ERROR_CLASS.status == 503
        assert LOOKUP_UNAVAILABLE_ERROR_CLASS.code == "verification_temporarily_unavailable"

    def test_exhaustion_is_not_the_user_not_found_mapping(self):
        """§7.1 routes the two apart: unavailable is a 503, unresolved is a 401."""
        assert LOOKUP_UNAVAILABLE_RESULT is not AuthEventResult.firebase_user_unresolved
