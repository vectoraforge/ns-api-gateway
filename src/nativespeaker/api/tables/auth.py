"""The auth-domain enums, the auth request and response bodies, and the `core.auth_challenges` table."""
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

# `Field` is aliased because the unqualified name is sqlmodel's, which the `AuthChallenge` table below needs.
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import DateTime, Enum, LargeBinary
from sqlmodel import Field, SQLModel

from nativespeaker.api.tables.identities import IdentityProvider


class AuthOperation(StrEnum):
    """Mirrors `core.auth_operation` -- the canonical state-changing auth operations."""
    create_user = "create_user"
    upgrade_anonymous_to_registered = "upgrade_anonymous_to_registered"
    claim_anonymous_grant = "claim_anonymous_grant"
    claim_registered_grant = "claim_registered_grant"
    restore_subscription = "restore_subscription"
    sign_out_all = "sign_out_all"
    sync = "sync"


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
    challenge_id: str = PydanticField(..., min_length=1)


class CompletionResponse(BaseModel):
    """The completion body: the registration state. There is no backend session tier, so nothing is minted."""
    identity_provider: IdentityProvider


AuthOperationType = cast(Any, Enum(AuthOperation, name='auth_operation', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))
ByteaType = cast(Any, LargeBinary)


class AuthChallenge(SQLModel, table=True):
    """One challenge row. There is no state column: the lifecycle is discriminated by column nullability."""

    __tablename__ = "auth_challenges"
    __table_args__ = {"schema": "core"}

    # Logs correlate on this row id; the public `challenge_id` below is never logged.
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # A secret capability handle: body-only transport, never in a URL, a log, a trace, or error text.
    challenge_id: str = Field(unique=True)
    operation: AuthOperation = Field(sa_type=AuthOperationType)
    # Exactly one of this and the pre-auth pair below is populated.
    bound_external_identity_id: UUID | None = Field(default=None,
                                                    foreign_key="core.external_identities.id")
    # Plaintext on purpose: a deployment-known provider string shared by every user of that provider.
    preauth_issuer: str | None = Field(default=None)
    # Keyed hash of the verified subject, cleared by consumption. No key-version column: a rotation fails it.
    preauth_subject_hash: bytes | None = Field(sa_type=ByteaType, default=None)
    # Written by the application as now + 300s, and evaluated in exactly one place: the claim's WHERE.
    expires_at: datetime = Field(sa_type=DateTimeType)
    claimed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    claim_attempt_id: UUID | None = Field(default=None)
    consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType)
