"""The one retry policy for the §7.1 Firebase providerData lookup (D-04, superseding 35 D-06).

**The predicate is `retry_if_result`, not `retry_if_exception_type`**, because
`FirebaseAdminAdapter.get_user_provider_data` *returns* a closed `ProviderDataResult` and never
raises -- an exception predicate would match nothing, no attempt would ever be retried, and §7.1's
three-attempt budget would silently become a one-attempt budget.

**`retry_error_callback` is mandatory here, not a nicety, and `reraise=True` cannot replace it.**
`reraise` re-raises the *original exception*; a result-based retry has none, so exhaustion raises
`tenacity.RetryError` regardless. A caller expecting a `ProviderDataResult` back would not catch
it, the `firebase_lookup_unavailable` -> `verification_temporarily_unavailable` mapping would be
lost, and a 503 the spec earns would surface as a 500 whose stack trace carries provider text.

**Only `retryable_failure` is retried.** `user_not_found` and `selection_failure` are definitive:
they resolve on the first attempt and spend no further one. Retrying `user_not_found` would burn
two attempts proving a fact Firebase already stated, and it maps to `firebase_user_unresolved` ->
`auth_required`, not to the unavailable pair below.

There is deliberately no wait, backoff, or jitter. §02 step 8 specifies attempt counts only, and
each attempt already carries the adapter's fixed 5-10 s per-attempt transport timeout -- a wait
strategy would push the request's worst case past what the spec bounds.
"""
from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt

from nativespeaker.api.auth.adapters import ProviderDataOutcome, ProviderDataResult
from nativespeaker.api.errors import VERIFICATION_TEMPORARILY_UNAVAILABLE, ErrorClass
from nativespeaker.api.models.auth import AuthEventResult

# §7.1: 3 attempts total -- the initial call plus up to two additional -- for retryable causes only.
FIREBASE_LOOKUP_ATTEMPTS = 3

# The §7.1 exhaustion mapping, named rather than repeated. `budgets.BudgetExhausted` carried this
# pair as class data; §7.1 has five providerData read points, and a literal repeated at each of
# them is a mapping that can drift four ways. A name is also something a test can pin.
LOOKUP_UNAVAILABLE_RESULT: AuthEventResult = AuthEventResult.firebase_lookup_unavailable
LOOKUP_UNAVAILABLE_ERROR_CLASS: ErrorClass = VERIFICATION_TEMPORARILY_UNAVAILABLE


def _is_retryable(result: ProviderDataResult) -> bool:
    """True for `retryable_failure` alone -- outage, malformed response, integration-auth failure.

    `ok` is a success and the other two outcomes are definitive, so each of those three ends the
    policy on the attempt that produced it.
    """
    return result.outcome is ProviderDataOutcome.retryable_failure


async def lookup_with_retry(adapter, issuer: str, subject: str) -> ProviderDataResult:
    """Call `adapter.get_user_provider_data(issuer, subject)` up to `FIREBASE_LOOKUP_ATTEMPTS`.

    Returns a `ProviderDataResult` under every outcome, including exhaustion -- the caller maps a
    returned `retryable_failure` onto `LOOKUP_UNAVAILABLE_RESULT` / `LOOKUP_UNAVAILABLE_ERROR_CLASS`
    and writes its own audit row. `tenacity.RetryError` never escapes.

    `issuer` is forwarded on every attempt, so §7.1's per-call client selection holds for retries
    too and no attempt can reach an ambient or fallback client.
    """
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        retry=retry_if_result(_is_retryable),
        # Hands the last ProviderDataResult back instead of raising RetryError. See the module
        # docstring: with no original exception, `reraise=True` would not help.
        retry_error_callback=lambda retry_state: retry_state.outcome.result(),
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
