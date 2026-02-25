from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel


class Chat(SQLModel, table=True):
    __tablename__ = "chats"

    id: UUID = Field(primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    lang: str
    created_at: datetime | None = Field(default=None, sa_column_kwargs={"server_default": "now()"})


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: int | None = Field(default=None, primary_key=True)
    chat_id: UUID = Field(foreign_key="chats.id")
    role: str
    content: str
    created_at: datetime | None = Field(
        default=None,
        sa_column_kwargs={"server_default": "now()"},
        primary_key=True,
    )
