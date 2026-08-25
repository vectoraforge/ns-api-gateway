("Adapter seams: interfaces and result types only, with no provider SDK import and no I/O. Every "
 "implementation must make no provider call while a database lock is held, must bound each attempt "
 "at a fixed 5-10 seconds, and must never leak provider text to clients.")
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from nativespeaker.api.auth.verification import VerifiedClaims


class ProviderDataOutcome(StrEnum):
    ok = "ok"
    # Terminal: Firebase stated the account does not exist, so no retry attempt is spent on it.
    user_not_found = "user_not_found"
    # The only outcome the retry budget is for: outage, malformed response, or integration failure.
    retryable_failure = "retryable_failure"
    # Terminal: the issuer did not match the configured integration. Fails closed, never falls back.
    selection_failure = "selection_failure"


class RevocationOutcome(StrEnum):
    """Two-valued on purpose: `confirmed` only when Firebase confirmed, everything else is not."""

    confirmed = "confirmed"
    unconfirmed = "unconfirmed"


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

    def verify_id_token(self, raw_token: str) -> VerifiedClaims:
        ...

    def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        """The providerData read. Retry-gated, and never called on an ordinary request path."""
        ...

    def revoke_refresh_tokens(self, issuer: str, subject: str) -> RevocationOutcome:
        """Revoke the subject's refresh tokens. An issuer mismatch fails closed before any call."""
        ...


@dataclass(frozen=True, slots=True)
class VerifiedNotification:
    """A provider callback the named verifier proved. `notification_id` is the idempotency key."""

    provider: str
    route_verifier_id: str
    notification_id: str


@dataclass(frozen=True, slots=True)
class VerifiedTransaction:
    """A verified client-presented store artifact. Every field is store-checked, not client-said."""

    provider: str
    external_id: str
    transaction_identity: str
    purchase_uuid: UUID | None
    app_id: str
    product_id: str
    environment: str


@dataclass(frozen=True, slots=True)
class StoreState:
    """One live store-state observation. `observed_at` is server-issued, never from the payload."""

    provider: str
    external_id: str
    entitled: bool
    observed_at: datetime


class StoreAdapter(Protocol):
    """Store verification and reads. Every rejection is an undistinguished `None`; lookups coalesce."""

    def verify_provider_callback(self, route_verifier_id: str, request: object) -> VerifiedNotification | None:
        """Verify a provider callback under the verifier the route named. `None` is rejected."""
        ...

    def verify_store_artifact(self, provider: str, artifact: str) -> VerifiedTransaction | None:
        """Verify a client-presented artifact. The resolved identity is an output, never an input."""
        ...

    def fetch_subscription_state(self, provider: str, external_id: str) -> StoreState | None:
        """Live store-state read. `None` is unavailable, and unavailable always rejects."""
        ...


class ClaimKind(StrEnum):
    """Which device slot a vendor-proof call addresses: `anonymous` is bit0, `registered` is bit1."""

    anonymous = "anonymous"
    registered = "registered"


class DeviceBitState(StrEnum):
    """Three closed states. `unavailable` is never read as `unset` -- an unreadable bit fails closed."""

    set = "set"
    unset = "unset"
    unavailable = "unavailable"


class VendorProofAdapter(Protocol):
    """Free-grant device-check material. No value here may become a rate-limit key or a device principal."""

    def read_device_bit(self, platform: str, claim_kind: ClaimKind, material: str) -> DeviceBitState:
        """Read the slot `claim_kind` selects. Never served from a coalesced or cached value."""
        ...

    def write_device_bit(self, platform: str, claim_kind: ClaimKind, material: str) -> bool:
        """Write the slot `claim_kind` selects. `True` is vendor-confirmed; anything else failed."""
        ...

    def verify_integrity_verdict(self, material: str) -> object | None:
        """Verify an attestation verdict. `None` is rejected-or-unavailable, undistinguished."""
        ...

    def verify_bot_check(self, token: str, remote_ip: str | None) -> bool | None:
        """Bot-check verification. `True` ok, `False` rejected, `None` unavailable. Nothing is stored."""
        ...
