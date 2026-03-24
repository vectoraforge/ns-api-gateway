from datetime import datetime, UTC
from enum import StrEnum
from uuid import UUID, uuid7

from sqlalchemy import Index, text
from sqlmodel import SQLModel, Field


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
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    provider: SubscriptionProvider = Field()
    external_id: str = Field()
    plan: SubscriptionPlan = Field()
    status: SubscriptionStatus = Field()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SubscriptionEvent(SQLModel, table=True):
    __tablename__ = "subscription_events"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    subscription_id: UUID = Field(foreign_key="core.subscriptions.id", index=True)
    event_type: str = Field()
    notification_uuid: str = Field(unique=True)
    old_plan: SubscriptionPlan | None = Field(default=None)
    new_plan: SubscriptionPlan | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
