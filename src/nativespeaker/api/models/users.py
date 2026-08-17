"""The mapped `core` identity, entitlement and usage tables.

These declarations follow the applied schema: `core.users` is the internal owner row and carries
no plan, free-access or tier column; the external `(issuer, subject)` mapping lives on
`core.external_identities`; entitlement lives on `core.access_grants` joined to
`core.access_tiers`; and monthly consumption is a `core.user_monthly_usage` row owned by the
grant that authorizes its credits.
"""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum, UniqueConstraint
from sqlmodel import Field, SQLModel

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import IdentityState
from nativespeaker.api.auth.operations import IdentityProvider

DateTimeType = cast(Any, DateTime(timezone=True))
IdentityProviderType = cast(Any, Enum(IdentityProvider, name="identity_provider", schema="core"))
IdentityStateType = cast(Any, Enum(IdentityState, name="identity_state", schema="core"))
AccessGrantSourceType = cast(
    Any, Enum(AccessGrantSource, name="access_grant_source", schema="core"))
AccessGrantStatusType = cast(
    Any, Enum(AccessGrantStatus, name="access_grant_status", schema="core"))


class User(SQLModel, table=True):
    """The internal owner row. Subscription plan, free access and tier are deliberately absent:
    a user's access is the state of their `core.access_grants` rows, never a column here."""
    # [impl->req~schema-users-no-plan-fields~1]
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # [impl->req~schema-users-email-display-name-canonical~1]
    email: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    registered_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    active: bool = Field(default=True)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))


class ExternalIdentity(SQLModel, table=True):
    """The external `(issuer, subject)` mapping onto an internal user."""
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("user_id"),
        UniqueConstraint("issuer", "subject"),
        {"schema": "core"},
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    issuer: str = Field()
    subject: str = Field()
    provider: IdentityProvider = Field(sa_type=IdentityProviderType)
    provider_uid: str | None = Field(default=None)
    identity_state: IdentityState = Field(sa_type=IdentityStateType,
                                          default=IdentityState.active)
    free_grant_consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    historical_at: datetime | None = Field(sa_type=DateTimeType, default=None)


class AccessTier(SQLModel, table=True):
    """The configured monthly allowance of a tier. Numeric monthly limits live here."""
    __tablename__ = "access_tiers"
    __table_args__ = {"schema": "core"}

    id: str = Field(primary_key=True)
    monthly_credits: int = Field()
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))


class AccessGrant(SQLModel, table=True):
    """One user's entitlement to one tier. This, not a column on `core.users`, is what says a
    user has access."""
    # [impl->req~schema-users-access-via-access-grants~1]
    __tablename__ = "access_grants"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    tier_id: str = Field(foreign_key="core.access_tiers.id")
    source: AccessGrantSource = Field(sa_type=AccessGrantSourceType)
    subscription_id: UUID | None = Field(default=None)
    status: AccessGrantStatus = Field(sa_type=AccessGrantStatusType,
                                      default=AccessGrantStatus.active)
    starts_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    ends_at: datetime | None = Field(sa_type=DateTimeType, default=None)


class UserMonthlyUsage(SQLModel, table=True):
    """Monthly consumption, owned by the grant that authorizes the credits it counts. There is
    no `user_id` here: usage follows the grant, not the user."""
    # [impl->req~schema-users-usage-via-user-monthly-usage~1]
    __tablename__ = "user_monthly_usage"
    __table_args__ = {"schema": "core"}

    grant_id: UUID = Field(foreign_key="core.access_grants.id", primary_key=True)
    monthly_period: str = Field()
    monthly_used: int = Field(default=0)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
