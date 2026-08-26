"""The providerData adapter seam: an interface and its result types, with no provider SDK import and no
I/O. Its implementation must make no provider call while a database lock is held, must bound each attempt
at a fixed 5-10 seconds, and must never leak provider text to clients."""
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ProviderDataOutcome(StrEnum):
    ok = "ok"
    # Terminal: Firebase stated the account does not exist, so no retry attempt is spent on it.
    user_not_found = "user_not_found"
    # The only outcome the retry budget is for: outage, malformed response, or integration failure.
    retryable_failure = "retryable_failure"
    # Terminal: the issuer did not match the configured integration. Fails closed, never falls back.
    selection_failure = "selection_failure"


@dataclass(frozen=True, slots=True)
class ProviderDataEntry:
    provider_id: str
    uid: str


@dataclass(frozen=True, slots=True)
class ProviderDataResult:
    """One providerData read. `entries`, `email` and `email_verified` are set only on `ok`."""

    outcome: ProviderDataOutcome
    entries: tuple[ProviderDataEntry, ...] = ()
    email: str | None = None
    email_verified: bool = False


class FirebaseAdminAdapter(Protocol):
    """One configured integration, one client selected by issuer match, and no ambient fallback."""

    def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        """The providerData read. Retry-gated, and never called on an ordinary request path."""
        ...
