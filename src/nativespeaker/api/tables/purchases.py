from datetime import date, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum
from sqlmodel import Field, SQLModel


class PurchaseProvider(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_provider` -- exactly two values."""
    apple = "apple"
    google_play = "google_play"


class SubscriptionStatus(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_status` -- exactly five values."""
    active = "active"
    grace_period = "grace_period"
    billing_retry = "billing_retry"
    expired = "expired"
    revoked = "revoked"


# `name=` pins the pre-existing type; without it SQLAlchemy derives a second, differently-named enum.
PurchaseProviderType = cast(Any, Enum(PurchaseProvider, name='subscription_provider', schema='core'))
SubscriptionStatusType = cast(Any, Enum(SubscriptionStatus, name='subscription_status', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class StorePurchaseToken(SQLModel, table=True):
    """One purchase-attribution token per user per store, for the account's life."""

    __tablename__ = "store_purchase_tokens"
    __table_args__ = {"schema": "core"}

    # The table has no crud primary key; these two markers are ORM-level, met by UNIQUE (user_id, provider).
    user_id: UUID = Field(foreign_key="core.users.id", primary_key=True)
    provider: PurchaseProvider = Field(sa_type=PurchaseProviderType, primary_key=True)
    # Deliberately not `unique=True`: the table's rule is the composite UNIQUE (provider, identity_value).
    identity_value: str = Field()
    created_at: datetime = Field(sa_type=DateTimeType)


# The table's GENERATED ALWAYS AS STORED column is deliberately unmapped: Postgres rejects an explicit value.
class Subscription(SQLModel, table=True):
    """One store subscription, keyed by the lifecycle pair the store owns."""

    __tablename__ = "subscriptions"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # Nullable: an unclaimed store subscription is ingested unowned, and restore is what first links it.
    user_id: UUID | None = Field(default=None, foreign_key="core.users.id")
    provider: PurchaseProvider = Field(sa_type=PurchaseProviderType)
    # Deliberately not `unique=True`: the table's rule is `ix_subscriptions_provider_external_id`.
    external_id: str = Field()
    tier_id: str = Field(foreign_key="core.access_tiers.id")
    status: SubscriptionStatus = Field(sa_type=SubscriptionStatusType)
    last_cross_account_transfer_month: date | None = Field(default=None)
    restore_bound_user_id: UUID | None = Field(default=None, foreign_key="core.users.id")
    created_at: datetime = Field(sa_type=DateTimeType)
    updated_at: datetime = Field(sa_type=DateTimeType)


class SubscriptionEvent(SQLModel, table=True):
    """One append-only record of one store notification, keyed by the store's own replay key."""

    __tablename__ = "subscription_events"
    __table_args__ = {"schema": "audit"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    subscription_id: UUID = Field(foreign_key="core.subscriptions.id")
    # Plain text, not an enum: a store type this build does not know is recorded, never refused.
    event_type: str = Field()
    notification_uuid: str = Field(unique=True)
    old_tier_id: str | None = Field(default=None, foreign_key="core.access_tiers.id")
    new_tier_id: str | None = Field(default=None, foreign_key="core.access_tiers.id")
    created_at: datetime = Field(sa_type=DateTimeType)
