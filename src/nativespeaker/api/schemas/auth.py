"""The auth request and response bodies, and the identity a verified credential resolves to."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.purchases import PurchaseProvider
from nativespeaker.api.tables.users import User


class ChallengeRequest(BaseModel):
    """The issuance body. `operation` is a plain `str`, never a Literal: an unissuable value is the handler's 400."""
    operation: str


class PrepareResponse(BaseModel):
    """The prepare body: the handle and its expiry, and nothing else about the challenge is disclosed."""
    challenge_id: str
    expires_at: datetime


class CompletionRequest(BaseModel):
    """The completion body: the handle obtained from `/auth/challenge`, and nothing else."""
    # Required and non-empty, so an unusable handle is the framework's 422 rather than a not-found 409.
    # The length counts characters, so a padded handle stays a distinct value and reaches the store untrimmed.
    challenge_id: str = Field(..., min_length=1)


class AnonymousGrantClaimRequest(BaseModel):
    """The claim body: the handle, and the two single-use DeviceCheck tokens."""
    challenge_id: str = Field(..., min_length=1)
    # Two separate tokens, each used once: the query token is never reused for the update.
    query_token: str = Field(..., min_length=1)
    update_token: str = Field(..., min_length=1)


class CompletionResponse(BaseModel):
    """The completion body: the registration state, and nothing else."""
    identity_provider: IdentityProvider


class EntitlementType(StrEnum):
    """The entitlement kind on the wire: the four grant sources, and `none` for a caller holding no grant."""
    none = "none"
    subscription = "subscription"
    anonymous_device_grant = "anonymous_device_grant"
    registered_account_grant = "registered_account_grant"
    manual = "manual"


class EntitlementStatus(StrEnum):
    """The entitlement status on the wire: exactly `none` or `active`."""
    none = "none"
    active = "active"


class Entitlement(BaseModel):
    """The entitlement block: the grant, its tier allowance, and the current period's usage."""
    type: EntitlementType
    status: EntitlementStatus
    tier_id: str | None
    monthly_credits: int | None
    current_period: str
    monthly_used: int


class SyncResponse(BaseModel):
    """The sync body: the entitlement and the registration state, and nothing else."""
    entitlement: Entitlement
    identity_provider: IdentityProvider


class Profile(BaseModel):
    """The profile block: the account's contact fields, both left NULL until a provider record fills them."""
    email: str | None
    display_name: str | None


class MeResponse(BaseModel):
    """The profile body: the profile block, the registration state and the store tokens, and nothing else."""
    profile: Profile
    identity_provider: IdentityProvider
    purchase_tokens: dict[PurchaseProvider, str]


@dataclass(frozen=True, slots=True)
class Identity:
    """A verified `(issuer, subject)` and the rows it resolved to, both `None` when it is unlinked."""
    issuer: str
    subject: str
    user: User | None = None
    identity: ExternalIdentity | None = None
