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
    """The configured access tiers and their monthly credit limits. Numeric monthly limits live
    here, as product configuration, and nowhere else."""
    # [impl->req~schema-access-tiers-purpose~1]
    # [impl->req~schema-access-tiers-product-configuration~1]
    __tablename__ = "access_tiers"
    __table_args__ = {"schema": "core"}

    # The stable tier identifier: what grants and subscriptions point at, and the key a tier's
    # credit value is edited under rather than replaced.
    # [impl->req~schema-access-tiers-id-stable-identifier~1]
    id: str = Field(primary_key=True)
    # [impl->req~schema-access-tiers-monthly-credits-allowance~1]
    monthly_credits: int = Field()
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))


class AccessGrant(SQLModel, table=True):
    """One user's entitlement to one tier, free or paid. This, not a column on `core.users`, is
    what says a user has access, and it carries entitlement state only: the anti-abuse evidence
    of a free-credit grant lives on `core.access_grants_anti_abuse`."""
    # [impl->req~schema-users-access-via-access-grants~1]
    # [impl->req~schema-access-grants-purpose~1]
    __tablename__ = "access_grants"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # Every grant belongs to one `core.users` row.
    # [impl->req~schema-access-grants-one-user-per-grant~1]
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    # A grant names its tier by that tier's stable `id`, never by a copy of its credit amount.
    # [impl->req~schema-access-tiers-id-stable-identifier~1]
    # [impl->req~schema-access-grants-one-tier-per-grant~1]
    tier_id: str = Field(foreign_key="core.access_tiers.id")
    source: AccessGrantSource = Field(sa_type=AccessGrantSourceType)
    subscription_id: UUID | None = Field(default=None)
    status: AccessGrantStatus = Field(sa_type=AccessGrantStatusType,
                                      default=AccessGrantStatus.active)
    starts_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    ends_at: datetime | None = Field(sa_type=DateTimeType, default=None)


class UserMonthlyUsage(SQLModel, table=True):
    """Mutable monthly usage state for an access grant, owned by the grant that authorizes the
    credits it counts. There is no `user_id` here: usage follows the grant, not the user. There
    is no allowance column either — that is derived from the grant's tier.
    """
    # [impl->req~schema-users-usage-via-user-monthly-usage~1]
    # [impl->req~schema-user-monthly-usage-purpose~1]
    # [impl->req~schema-user-monthly-usage-allowance-not-stored~1]
    __tablename__ = "user_monthly_usage"
    __table_args__ = {"schema": "core"}

    # The grant whose credits are being consumed: the primary key of this table, so at most one
    # row exists per grant, and a foreign key onto `core.access_grants.id`.
    # The grant row owns this usage state: consumption is keyed by `grant_id` and by nothing else.
    # [impl->req~schema-user-monthly-usage-grant-id-field~1]
    # [impl->req~schema-user-monthly-usage-one-row-per-grant~1]
    # [impl->req~schema-access-grants-owns-monthly-usage~1]
    grant_id: UUID = Field(foreign_key="core.access_grants.id", primary_key=True)
    # [impl->req~schema-user-monthly-usage-monthly-period-field~1]
    monthly_period: str = Field()
    # [impl->req~schema-user-monthly-usage-monthly-used-field~1]
    monthly_used: int = Field(default=0)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
