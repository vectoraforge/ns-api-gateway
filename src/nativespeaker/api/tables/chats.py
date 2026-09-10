from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


class ChatRole(StrEnum):
    human = "human"
    ai = "ai"


ChatRoleType = cast(Any, Enum(ChatRole, name='chat_role', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # ON DELETE CASCADE in the migration, which owns every referential action: the relationship
    # below is what makes this package's own deletes leave the rows to the database.
    chat_id: UUID = Field(foreign_key="core.chats.id")
    role: ChatRole = Field(sa_type=ChatRoleType)
    content: dict = Field(sa_type=JSONB)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))


class Chat(SQLModel, table=True):
    __tablename__ = "chats"
    __table_args__ = {"schema": "core"}


    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # `ix_chats_user_id` in the migration, which owns every index; this metadata declares none.
    user_id: UUID = Field(foreign_key="core.users.id")
    title: str = Field()
    lang: str | None = Field(default=None)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))

    # Ordered explicitly: the LLM history is built by iterating this list, and an unordered
    # SELECT returns physical row order, which a VACUUM or a plan change can shuffle.
    messages: list[Message] = Relationship(
        cascade_delete=True,
        passive_deletes=True,
        # `Message.id` is uuid7, so ascending id is chronological.
        sa_relationship_kwargs={"order_by": "Message.id"})

    @property
    def ai_messages(self):
        return list(filter(lambda m: m.role == ChatRole.ai, self.messages))

    @property
    def human_messages(self):
        return list(filter(lambda m: m.role == ChatRole.human, self.messages))
