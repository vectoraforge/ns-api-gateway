"""The `core.external_identities` table and the three native enums it binds."""
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum
from sqlmodel import Field, SQLModel


class IdentityProvider(StrEnum):
    """Mirrors `core.identity_provider`. `provider_uid` is NULL exactly for `anonymous`."""
    anonymous = "anonymous"
    google = "google"
    apple = "apple"


class IdentityState(StrEnum):
    """Mirrors `core.identity_state`. Rows are never deleted, so a retired identity is `historical`, not absent."""
    active = "active"
    historical = "historical"


class NativeClaimProvider(StrEnum):
    """Mirrors `core.native_claim_provider` -- the platform a native claim is pinned to, immutably."""
    ios_devicecheck = "ios_devicecheck"
    android_play_integrity = "android_play_integrity"


IdentityProviderType = cast(Any, Enum(IdentityProvider, name='identity_provider', schema='core'))
IdentityStateType = cast(Any, Enum(IdentityState, name='identity_state', schema='core'))
NativeClaimProviderType = cast(Any, Enum(NativeClaimProvider, name='native_claim_provider', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class ExternalIdentity(SQLModel, table=True):
    """A verified `(issuer, subject)` bound to exactly one `core.users` row."""

    __tablename__ = "external_identities"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # ON DELETE RESTRICT in the migration: a user row cannot be deleted out from under its identity row.
    user_id: UUID = Field(foreign_key="core.users.id", unique=True)
    issuer: str = Field()
    subject: str = Field()
    # The sole per-request classifier for every identity, authorization and entitlement decision.
    provider: IdentityProvider = Field(sa_type=IdentityProviderType)
    provider_uid: str | None = Field(default=None)
    identity_state: IdentityState = Field(sa_type=IdentityStateType, default=IdentityState.active)
    native_claim_platform: NativeClaimProvider | None = Field(sa_type=NativeClaimProviderType, default=None)
    # Set once, never cleared: the account consumed its one lifetime free grant.
    free_grant_consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    historical_at: datetime | None = Field(sa_type=DateTimeType, default=None)
