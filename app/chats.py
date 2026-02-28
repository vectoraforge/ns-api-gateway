import base64
from datetime import datetime
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import func, and_, or_, insert, delete

from app.models import Chat, Message
from app.exceptions import ChatOwnershipError, InvalidChatError


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

    async def create_chat(self, db: AsyncSession, chat_id: UUID, lang: str, user_id: str) -> None:
        db.add(Chat(id=chat_id, user_id=user_id, lang=lang))
        await db.commit()

    async def get_chat_owned(self, db: AsyncSession, chat_id: UUID, user_id: str) -> dict:
        """Return chat dict if owned by user_id. Raise ChatOwnershipError if exists but wrong owner,
        InvalidChatError if it doesn't exist."""
        chat = await db.get(Chat, chat_id)
        if chat is None:
            raise InvalidChatError(chat_id)
        if chat.user_id != user_id:
            raise ChatOwnershipError(chat_id)
        return {"id": chat.id, "lang": chat.lang, "user_id": chat.user_id}

    async def delete_chat_owned(self, db: AsyncSession, chat_id: UUID, user_id: str) -> None:
        """Delete chat owned by user_id. Raise ChatOwnershipError if exists but wrong owner,
        InvalidChatError if doesn't exist."""
        chat = await db.get(Chat, chat_id)
        if chat is None:
            raise InvalidChatError(chat_id)
        if chat.user_id != user_id:
            raise ChatOwnershipError(chat_id)
        await db.delete(chat)
        await db.commit()

    async def load_history(
        self, db: AsyncSession, chat_id: UUID, limit: int | None = None
    ) -> list[HumanMessage | AIMessage]:
        statement = (
            select(Message.role, Message.content)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        results = (await db.exec(statement)).all()
        messages = []
        for role, content in reversed(results):
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        return messages

    async def get_message_counts(self, db: AsyncSession, chat_id: UUID) -> dict[str, int]:
        statement = (
            select(Message.role, func.count(Message.id))
            .where(Message.chat_id == chat_id)
            .group_by(Message.role)
        )
        results = (await db.exec(statement)).all()
        return {role: count for role, count in results}

    async def list_messages(
        self,
        db: AsyncSession,
        chat_id: UUID,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[Message], str | None]:
        statement = select(Message).where(Message.chat_id == chat_id)
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
        await db.commit()
