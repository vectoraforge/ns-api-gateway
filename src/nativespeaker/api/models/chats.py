from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

from nativespeaker.api.models.users import User


class ChatRole(StrEnum):
    human = "human"
    ai = "ai"


ChatRoleType = cast(Any, Enum(ChatRole, name='chat_role', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    chat_id: UUID = Field(foreign_key="core.chats.id", ondelete="CASCADE")
    role: ChatRole = Field(sa_type=ChatRoleType)
    content: dict = Field(sa_type=JSONB)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))


class Chat(SQLModel, table=True):
    __tablename__ = "chats"
    __table_args__ = {"schema": "core"}


    id: UUID = Field(primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    title: str = Field()
    lang: str | None = Field(default=None)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))

    messages: list[Message] = Relationship(cascade_delete=True, passive_deletes=True)
    user: User = Relationship()

    @property
    def ai_messages(self):
        return list(filter(lambda m: m.role == ChatRole.ai, self.messages))

    @property
    def human_messages(self):
        return list(filter(lambda m: m.role == ChatRole.human, self.messages))
