from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid7

from pydantic import BaseModel, field_serializer, field_validator
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship, SQLModel

from app.api.schema import Issue


class Role(StrEnum):
    human = "human"
    ai = "ai"


class HumanContent(BaseModel):
    phrase: str
    comment: str | None = None


class AIContent(BaseModel):
    response: str
    issues: list[Issue] | None = None
    suggestions: list[str] | None = None


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    chat_id: UUID = Field(foreign_key="chats.id")
    role: Role
    content: HumanContent | AIContent = Field(sa_type=JSON)
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


class Chat(SQLModel, table=True):
    __tablename__ = "chats"

    id: UUID = Field(primary_key=True)
    user_id: str = Field(..., index=True)
    title: str
    lang: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    messages: list[Message] = Relationship()

    @property
    def ai_messages(self):
        return list(filter(lambda m: m.role == Role.ai, self.messages))

    @property
    def human_messages(self):
        return list(filter(lambda m: m.role == Role.human, self.messages))
