"""The `core.external_identities` table and the three native enums it binds.

This is the only table in the schema that stores a recoverable external subject: `issuer` and
`subject` are the verified Firebase ID token's `iss`/`sub` in plaintext, held as a uniqueness
reservation. `core.auth_challenges` stores a keyed hash instead.

The stored `provider` column is the **sole** per-request classifier for every identity,
authorization, entitlement, grant-class, and audit decision. It is never rederived from token
claims, headers, client input, or live providerData outside the enumerated Firebase Admin read
points, and `core.users.registered_at` is reporting-only -- never a competing classifier.

The database owns every constraint. The provider/provider_uid agreement CHECK, the
`UNIQUE (issuer, subject)` auth-time lookup key, and the partial
`ix_external_identities_provider_account` index are declared in
`migrations/20260818_01_initial-release.sql` and are deliberately not re-encoded here: a Python
copy of a CHECK is a second source of truth that can drift from the one that actually enforces.
"""
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
    """Mirrors `core.identity_state`. Exactly two values.

    Identity rows are never deleted -- `historical` is a permanent tombstone reached by a state
    transition, and no path reverses it. The barrier admits `active` alone; every other value,
    NULL included, rejects rather than falling through to pre-auth.
    """
    active = "active"
    historical = "historical"


class NativeClaimProvider(StrEnum):
    """Mirrors `core.native_claim_provider` -- the platform an anonymous identity's native claim
    is pinned to, once and immutably."""
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
    # ON DELETE RESTRICT in the migration -- a guardrail against deleting a user row out from
    # under its identity row. `unique=True` mirrors the table's UNIQUE (user_id): one identity
    # row per user, at most.
    user_id: UUID = Field(foreign_key="core.users.id", unique=True)
    issuer: str = Field()
    subject: str = Field()
    provider: IdentityProvider = Field(sa_type=IdentityProviderType)
    provider_uid: str | None = Field(default=None)
    identity_state: IdentityState = Field(sa_type=IdentityStateType, default=IdentityState.active)
    native_claim_platform: NativeClaimProvider | None = Field(sa_type=NativeClaimProviderType, default=None)
    # Permanent per-account marker that the account consumed its one lifetime free grant.
    # Set once, never cleared.
    free_grant_consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    historical_at: datetime | None = Field(sa_type=DateTimeType, default=None)
