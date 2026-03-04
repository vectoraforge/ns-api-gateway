import base64
from datetime import datetime
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import and_, delete, insert, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.exceptions import InvalidChatError
from app.models import Chat, Message


class Chats:
    @staticmethod
    def _encode_cursor(created_at: datetime, message_id: int) -> str:
        payload = f"{created_at.isoformat()}|{message_id}"
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, int]:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        created_at_raw, message_id_raw = raw.split("|", 1)
        return datetime.fromisoformat(created_at_raw), int(message_id_raw)

    async def create_chat_with_messages(
        self, db: AsyncSession, chat_id: UUID, user_id: str, human: str, assistant: str
    ) -> None:
        db.add(Chat(id=chat_id, user_id=user_id))
        await db.execute(
            insert(Message),
            [
                {"chat_id": chat_id, "role": "human", "content": human},
                {"chat_id": chat_id, "role": "assistant", "content": assistant},
            ],
        )

    async def delete_chat(self, db: AsyncSession, chat_id: UUID, user_id: str) -> None:
        result = await db.execute(
            delete(Chat).where(and_(Chat.id == chat_id, Chat.user_id == user_id))
        )
        if result.rowcount == 0:
            raise InvalidChatError(chat_id)

    async def load_history(
        self, db: AsyncSession, chat_id: UUID, user_id: str, limit: int | None = None
    ) -> list[HumanMessage | AIMessage]:
        statement = (
            select(Message.role, Message.content)
            .join(Chat, Message.chat_id == Chat.id)
            .where(and_(Message.chat_id == chat_id, Chat.user_id == user_id))
            .order_by(Message.created_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        results = (await db.exec(statement)).all()
        if not results:
            raise InvalidChatError(chat_id)
        messages = []
        for role, content in reversed(results):
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        return messages

    async def list_messages(
        self,
        db: AsyncSession,
        chat_id: UUID,
        user_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[Message], str | None]:
        statement = (
            select(Message)
            .join(Chat, Message.chat_id == Chat.id)
            .where(and_(Message.chat_id == chat_id, Chat.user_id == user_id))
        )
        if cursor:
            cursor_created_at, cursor_id = self._decode_cursor(cursor)
            statement = statement.where(
                or_(
                    Message.created_at < cursor_created_at,
                    and_(Message.created_at == cursor_created_at, Message.id < cursor_id),
                )
            )
        statement = statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)
        results = (await db.exec(statement)).all()

        if not results and cursor is None:
            raise InvalidChatError(chat_id)

        next_cursor = None
        if len(results) > limit:
            last = results.pop()
            if last.created_at is not None and last.id is not None:
                next_cursor = self._encode_cursor(last.created_at, last.id)
        return results, next_cursor

    async def save_messages(self, db: AsyncSession, chat_id: UUID, human: str, assistant: str) -> None:
        await db.execute(
            insert(Message),
            [
                {"chat_id": chat_id, "role": "human", "content": human},
                {"chat_id": chat_id, "role": "assistant", "content": assistant},
            ],
        )
