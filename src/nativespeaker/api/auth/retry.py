"""The one retry policy for the providerData lookup: three attempts, then the unavailable pair."""
from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt

from nativespeaker.api.auth.adapters import ProviderDataOutcome, ProviderDataResult
from nativespeaker.api.errors import VERIFICATION_TEMPORARILY_UNAVAILABLE, ErrorClass
from nativespeaker.api.models.auth import AuthEventResult

FIREBASE_LOOKUP_ATTEMPTS = 3

LOOKUP_UNAVAILABLE_RESULT: AuthEventResult = AuthEventResult.firebase_lookup_unavailable
LOOKUP_UNAVAILABLE_ERROR_CLASS: ErrorClass = VERIFICATION_TEMPORARILY_UNAVAILABLE


def _is_retryable(result: ProviderDataResult) -> bool:
    return result.outcome is ProviderDataOutcome.retryable_failure


async def lookup_with_retry(adapter, issuer: str, subject: str) -> ProviderDataResult:
    """Call the adapter up to `FIREBASE_LOOKUP_ATTEMPTS` times, returning a result under every outcome."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        # `retry_if_result`, not `retry_if_exception_type`: the adapter returns rather than raises.
        retry=retry_if_result(_is_retryable),
        # Hands the last result back; with no original exception, `reraise=True` would not help.
        retry_error_callback=lambda retry_state: retry_state.outcome.result(),
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
