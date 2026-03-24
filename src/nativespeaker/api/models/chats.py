from datetime import datetime, UTC
from enum import StrEnum
from uuid import UUID, uuid7

from pydantic import BaseModel
from sqlalchemy import Column
from sqlmodel import SQLModel, Field, Relationship

from nativespeaker.api.models import ContentUnion
from nativespeaker.api.models.users import User
from nativespeaker.api.models.content import PydanticJSONB


class ChatRole(StrEnum):
    human = "human"
    ai = "ai"


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    chat_id: UUID = Field(foreign_key="core.chats.id", ondelete="CASCADE")
    role: ChatRole = Field()
    content: BaseModel = Field(sa_column=Column(PydanticJSONB(ContentUnion)))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chat(SQLModel, table=True):
    __tablename__ = "chats"
    __table_args__ = {"schema": "core"}


    id: UUID = Field(primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    title: str = Field()
    lang: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    messages: list[Message] = Relationship(cascade_delete=True, passive_deletes=True)
    user: User = Relationship()

    @property
    def ai_messages(self):
        return list(filter(lambda m: m.role == ChatRole.ai, self.messages))

    @property
    def human_messages(self):
        return list(filter(lambda m: m.role == ChatRole.human, self.messages))
