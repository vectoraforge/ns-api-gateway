from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlmodel import Field, SQLModel


class Role(StrEnum):
    human = "human"
    ai = "ai"


class Chat(SQLModel, table=True):
    __tablename__ = "chats"

    id: UUID = Field(primary_key=True)
    phrase: str
    comment: str | None = None
    lang: str | None = None
    user_id: str | None = Field(default=None, index=True)
    created_at: datetime | None = Field(default=None, sa_column_kwargs={"server_default": "now()"})


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: int | None = Field(default=None, primary_key=True)
    chat_id: UUID = Field(foreign_key="chats.id")
    role: Role
    content: str
    created_at: datetime | None = Field(default=None,
                                        sa_column_kwargs={"server_default": "now()"},
                                        primary_key=True)
