from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum, Index, text
from sqlmodel import Field, SQLModel


class SubscriptionPlan(StrEnum):
    free = "free"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"


class SubscriptionProvider(StrEnum):
    apple = "apple"


class SubscriptionStatus(StrEnum):
    active = "active"
    grace_period = "grace_period"
    billing_retry = "billing_retry"
    expired = "expired"
    revoked = "revoked"


SubscriptionPlanType = cast(Any, Enum(SubscriptionPlan, name='subscription_plan', schema='core'))
SubscriptionProviderType = cast(Any, Enum(SubscriptionProvider, name='subscription_provider', schema='core'))
SubscriptionStatusType = cast(Any, Enum(SubscriptionStatus, name='subscription_status', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "ix_subscriptions_user_provider_active",
            "user_id", "provider",
            unique=True,
            postgresql_where=text("status NOT IN ('expired', 'revoked')")
        ),
        {"schema": "core"}
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # NULL for an unclaimed subscription: verified ingestion whose echoed attribution token
    # resolves to no binding records the canonical row unowned, with no subscription-backed
    # grant, and restore's adoption is what first links it.
    # [impl->req~schema-subscriptions-user-id-null-unclaimed~1]
    user_id: UUID | None = Field(default=None, foreign_key="core.users.id", index=True)
    provider: SubscriptionProvider = Field(sa_type=SubscriptionProviderType)
    external_id: str = Field()
    plan: SubscriptionPlan = Field(sa_type=SubscriptionPlanType)
    status: SubscriptionStatus = Field(sa_type=SubscriptionStatusType)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))


class SubscriptionEvent(SQLModel, table=True):
    __tablename__ = "subscription_events"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    subscription_id: UUID = Field(foreign_key="core.subscriptions.id", index=True)
    event_type: str = Field()
    notification_uuid: str = Field(unique=True)
    old_plan: SubscriptionPlan | None = Field(sa_type=SubscriptionPlanType, default=None)
    new_plan: SubscriptionPlan | None = Field(sa_type=SubscriptionPlanType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
