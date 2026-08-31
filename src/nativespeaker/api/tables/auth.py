"""The auth-domain enums and the `core.auth_challenges` table."""
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum
from sqlmodel import Field, SQLModel


class AuthOperation(StrEnum):
    """Mirrors `core.auth_operation` -- the canonical state-changing auth operations."""
    create_user = "create_user"
    upgrade_anonymous_to_registered = "upgrade_anonymous_to_registered"
    claim_anonymous_grant = "claim_anonymous_grant"
    claim_registered_grant = "claim_registered_grant"
    restore_subscription = "restore_subscription"
    sign_out_all = "sign_out_all"
    sync = "sync"


AuthOperationType = cast(Any, Enum(AuthOperation, name='auth_operation', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


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
    # The verified subject in plaintext, cleared by consumption.
    preauth_subject: str | None = Field(default=None)
    # Written by the application as now + 300s, and evaluated in exactly one place: the claim's WHERE.
    expires_at: datetime = Field(sa_type=DateTimeType)
    claimed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType)
