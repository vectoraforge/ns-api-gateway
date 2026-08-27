"""Exact attempt counts per outcome: the adapter raises now, so only an exception predicate fires."""
import pytest
import tenacity

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.auth.exceptions import NotLinked, Unavailable, UserNotFound
from nativespeaker.api.auth.firebase import (
    FIREBASE_LOOKUP_ATTEMPTS,
    RetryableLookupError,
    lookup_with_retry,
)
from nativespeaker.api.models.identities import IdentityProvider

ISSUER = "https://securetoken.google.com/ns-prod"
SUBJECT = "firebase-uid-1"

ANONYMOUS = VerifiedProviderIdentity(provider=IdentityProvider.anonymous, provider_uid=None)


def _retryable() -> RetryableLookupError:
    return RetryableLookupError("the provider's own text, for the log only")


# Every answer the policy must not retry: two terminal rejections and a completed read.
DEFINITIVE = [
    (ANONYMOUS, "a completed read"),
    (UserNotFound(stage="provider_lookup"), "the provider stated the account does not exist"),
    (Unavailable(stage="issuer_selection"), "no app is configured for the issuer"),
    (NotLinked(stage="provider_classification", cause="invalid-shape"), "an unclassifiable shape"),
]


class CountingAdapter:
    """Raises or returns a scripted sequence and records every call; overrunning the script is an error."""

    def __init__(self, *answers) -> None:
        self.scripted = answers
        self.calls: list[tuple[str, str]] = []

    def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        self.calls.append((issuer, subject))
        if len(self.calls) > len(self.scripted):
            # Overrunning the script is the failure this file exists to catch, so name it.
            raise AssertionError(
                f"attempt {len(self.calls)} exceeds the scripted {len(self.scripted)}")
        answer = self.scripted[len(self.calls) - 1]
        if isinstance(answer, BaseException):
            raise answer
        return answer


class AsyncCountingAdapter(CountingAdapter):
    """The same fake with an async method, matching the production adapter's own signature."""

    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:  # type: ignore[override]
        return CountingAdapter.get_user_provider_data(self, issuer, subject)


class TestAttemptCountsPerOutcome:
    """Three attempts total for the retryable marker only; every other answer is definitive."""

    def test_the_attempt_budget_is_the_71_three(self):
        """"3 attempts total -- the initial call plus up to two additional" (budgets.py:49-50)."""
        assert FIREBASE_LOOKUP_ATTEMPTS == 3

    async def test_three_retryable_failures_cost_exactly_three_attempts(self):
        adapter = CountingAdapter(*[_retryable() for _ in range(3)])

        with pytest.raises(Unavailable):
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert len(adapter.calls) == 3

    async def test_a_retryable_failure_then_a_completed_read_costs_exactly_two_attempts(self):
        adapter = CountingAdapter(_retryable(), ANONYMOUS)

        identity = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert len(adapter.calls) == 2
        assert identity is ANONYMOUS

    @pytest.mark.parametrize("answer,why", DEFINITIVE, ids=[case[1] for case in DEFINITIVE])
    async def test_a_definitive_answer_costs_exactly_one_attempt(self, answer, why):
        """Retrying a definitive answer would burn attempts proving a fact already established."""
        adapter = CountingAdapter(answer)

        if isinstance(answer, BaseException):
            with pytest.raises(type(answer)):
                await lookup_with_retry(adapter, ISSUER, SUBJECT)
        else:
            assert await lookup_with_retry(adapter, ISSUER, SUBJECT) is answer

        assert len(adapter.calls) == 1, why

    async def test_the_lookup_forwards_the_issuer_and_subject_on_every_attempt(self):
        """Selection happens per call, so no attempt may reach an ambient client."""
        adapter = CountingAdapter(*[_retryable() for _ in range(3)])

        with pytest.raises(Unavailable):
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert adapter.calls == [(ISSUER, SUBJECT)] * 3

    async def test_a_completed_read_is_carried_through_untouched(self):
        """The policy is transparent: it decides whether to call again and nothing else."""
        identity = VerifiedProviderIdentity(provider=IdentityProvider.google,
                                            provider_uid="g-1",
                                            email="a@b.test")
        adapter = CountingAdapter(identity)

        assert await lookup_with_retry(adapter, ISSUER, SUBJECT) is identity

    async def test_the_policy_is_agnostic_to_a_sync_or_async_adapter(self):
        """`AsyncRetrying` awaits a coroutine function and calls a plain one; both count the same."""
        adapter = AsyncCountingAdapter(_retryable(), ANONYMOUS)

        identity = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert len(adapter.calls) == 2
        assert identity is ANONYMOUS


class TestTheExhaustionConversion:
    """An exhausted budget is the one place a 500 could silently replace the 503 the caller is owed."""

    async def test_an_exhausted_budget_raises_the_unavailable_rejection(self):
        adapter = CountingAdapter(*[_retryable() for _ in range(FIREBASE_LOOKUP_ATTEMPTS)])

        with pytest.raises(Unavailable) as raised:
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert raised.value.stage == "provider_lookup"

    async def test_no_retry_error_escapes(self):
        """`RetryError` matches no handler, so it would answer 500 where a 503 was owed."""
        adapter = CountingAdapter(*[_retryable() for _ in range(FIREBASE_LOOKUP_ATTEMPTS)])

        try:
            await lookup_with_retry(adapter, ISSUER, SUBJECT)
        except tenacity.RetryError as exc:  # pragma: no cover - the assertion this test exists for
            pytest.fail(f"RetryError escaped the retry frame: {exc!r}")
        except Unavailable:
            pass

    async def test_the_client_facing_pair_is_a_503_with_the_matching_code(self):
        """Byte-for-byte what budgets.py:65-66 declared, so nothing about the wire moved."""
        adapter = CountingAdapter(*[_retryable() for _ in range(FIREBASE_LOOKUP_ATTEMPTS)])

        with pytest.raises(Unavailable) as raised:
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert raised.value.error_class.status == 503
        assert raised.value.error_class.code == "verification_temporarily_unavailable"

    async def test_exhaustion_is_not_the_user_not_found_mapping(self):
        """The two are routed apart: unavailable is a 503, unresolved is a 401."""
        adapter = CountingAdapter(*[_retryable() for _ in range(FIREBASE_LOOKUP_ATTEMPTS)])

        with pytest.raises(Unavailable) as raised:
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert not isinstance(raised.value, UserNotFound)
        assert raised.value.error_class.status != UserNotFound.error_class.status
