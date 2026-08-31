"""The auth request and response bodies, and the identity a verified credential resolves to."""
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field

from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User


class ChallengeRequest(BaseModel):
    """The issuance body. `operation` is a plain `str`, never a Literal: an unissuable value is the handler's 400."""
    operation: str


class PrepareResponse(BaseModel):
    """The prepare body: the handle and its expiry, and nothing else about the challenge is disclosed."""
    challenge_id: str
    expires_at: datetime


class CreateUserRequest(BaseModel):
    """The completion body: the handle obtained from `/auth/challenge`, and nothing else."""
    # Required and non-empty, so an unusable handle is the framework's 422 rather than a not-found 409.
    # The length counts characters, so a padded handle stays a distinct value and reaches the store untrimmed.
    challenge_id: str = Field(..., min_length=1)


class CompletionResponse(BaseModel):
    """The completion body: the registration state, and nothing else."""
    identity_provider: IdentityProvider


@dataclass(frozen=True, slots=True)
class Identity:
    """A verified `(issuer, subject)` and the rows it resolved to, both `None` when it is unlinked."""
    issuer: str
    subject: str
    user: User | None = None
    identity: ExternalIdentity | None = None
