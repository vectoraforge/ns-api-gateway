from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid7

from pydantic import BaseModel, field_serializer, field_validator
from sqlalchemy import Index, TypeDecorator, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

from nativespeaker.api.schema import Issue


class PydanticJSONB(TypeDecorator):
    """JSONB column that auto-serialises Pydantic models on write."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, BaseModel):
            return value.model_dump()
        return value


class Role(StrEnum):
    human = "human"
    ai = "ai"


class Tier(StrEnum):
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


class HumanContent(BaseModel):
    phrase: str
    comment: str | None = None


class AIContent(BaseModel):
    response: str
    issues: list[Issue] | None = None
    suggestions: list[str] | None = None


class BaseTable(SQLModel):
    pass


class Message(BaseTable, table=True):
    __tablename__ = "core.messages"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    chat_id: UUID = Field(foreign_key="core.chats.id", ondelete="CASCADE")
    role: Role = Field()
    content: HumanContent | AIContent = Field(sa_type=PydanticJSONB)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("content", mode="before")
    @classmethod
    def parse_content(cls, value, info):
        if isinstance(value, BaseModel):
            return value
        match info.data.get("role"):
            case Role.human:
                return HumanContent(**value)
            case Role.ai:
                return AIContent(**value)
        return None

    @field_serializer("content")
    def serialize_content(self, v: BaseModel) -> dict:
        return v.model_dump()


@event.listens_for(Message, "load")
def _reconstitute_content(target, context):
    """Parse raw dict back into the correct Pydantic content model after DB load."""
    raw = target.content
    if isinstance(raw, dict):
        match target.role:
            case Role.human:
                target.content = HumanContent(**raw)
            case Role.ai:
                target.content = AIContent(**raw)


class User(BaseTable, table=True):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    jwt_sub: str = Field(unique=True, index=True, )
    email: str = Field()
    name: str | None = Field(default=None, )
    plan: str = Field(default="free", foreign_key="core.plans.tier")
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Subscription(BaseTable, table=True):
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
    plan: str = Field(foreign_key="core.plans.tier")
    status: SubscriptionStatus = Field()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SubscriptionEvent(BaseTable, table=True):
    __tablename__ = "subscription_events"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    subscription_id: UUID = Field(foreign_key="core.subscriptions.id", index=True)
    event_type: str = Field()
    notification_uuid: str = Field(unique=True)
    old_tier: str | None = Field(default=None)
    new_tier: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Plan(BaseTable, table=True):
    __tablename__ = "plans"
    __table_args__ = {"schema": "core"}

    tier: str = Field(primary_key=True)
    monthly_quota: int = Field()


class UsageMonthly(BaseTable, table=True):
    __tablename__ = "usage_monthly"
    __table_args__ = (
        UniqueConstraint("user_id", "month"),
        {"schema": "core"}
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    month: str = Field()
    used: int = Field(default=0)


class Chat(BaseTable, table=True):
    __tablename__ = "chats"
    __table_args__ = {"schema": "core"}


    id: UUID = Field(primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    title: str = Field()
    lang: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    messages: list[Message] = Relationship(cascade_delete=True, passive_deletes=True)
    user: "User" = Relationship()

    @property
    def ai_messages(self):
        return list(filter(lambda m: m.role == Role.ai, self.messages))

    @property
    def human_messages(self):
        return list(filter(lambda m: m.role == Role.human, self.messages))
