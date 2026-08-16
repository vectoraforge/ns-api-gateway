from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from nativespeaker.api.models.subscriptions import SubscriptionPlan, SubscriptionPlanType

DateTimeType = cast(Any, DateTime(timezone=True))


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    jwt_sub: str = Field(unique=True, index=True, )
    email: str = Field()
    name: str | None = Field(default=None, )
    subscription_plan: SubscriptionPlan = Field(sa_type=SubscriptionPlanType, default=SubscriptionPlan.free)
    active: bool = Field(default=True)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))


class UsageMonthly(SQLModel, table=True):
    __tablename__ = "usage_monthly"
    __table_args__ = (
        UniqueConstraint("user_id", "month"),
        {"schema": "core"}
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    month: str = Field()
    used: int = Field(default=0)
