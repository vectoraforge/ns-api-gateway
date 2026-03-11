import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.models import Chat, Message, Role


class ChatsDB:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self,
                     chat_id: UUID,
                     phrase: str,
                     user_id: str,
                     comment: str | None = None,
                     lang: str | None = None) -> None:
        self.db.add(Chat(id=chat_id,
                         phrase=phrase,
                         comment=comment,
                         lang=lang,
                         user_id=user_id))

    async def save_message(self,
                           chat_id: UUID,
                           role: Role,
                           content: str) -> None:
        self.db.add(Message(chat_id=chat_id, role=role, content=content))

    async def get_history(self,
                          chat_id: UUID,
                          user_id: str) -> tuple[Chat | None, list[tuple[Role, str]]]:
        chat_stmt = (
            select(Chat)
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        )
        chat = (await self.db.exec(chat_stmt)).first()
        if chat is None:
            return None, []

        msg_stmt = (
            select(Message.role, Message.content)
            .where(col(Message.chat_id) == chat_id)
            .order_by(Message.created_at)
        )
        messages = (await self.db.exec(msg_stmt)).all()
        return chat, messages

    async def get_messages(self,
                           chat_id: UUID,
                           user_id: str,
                           limit: int,
                           cursor: str | None = None) -> tuple[Chat | None, list[Message], str | None]:
        chat_stmt = (
            select(Chat)
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        )
        chat = (await self.db.exec(chat_stmt)).first()
        if chat is None:
            return None, [], None

        statement = (
            select(Message)
            .where(col(Message.chat_id) == chat_id)
        )
        if cursor:
            cursor_created_at, cursor_id = self._decode_cursor(cursor)
            statement = statement.where(or_(Message.created_at < cursor_created_at,
                                            and_(Message.created_at == cursor_created_at,
                                                 Message.id < cursor_id)))
        statement = statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)
        results = list((await self.db.exec(statement)).all())

        next_cursor = None
        if len(results) > limit:
            last = results.pop()
            if last.created_at is not None and last.id is not None:
                next_cursor = self._encode_cursor(last.created_at, last.id)
        return chat, results, next_cursor

    async def delete(self,
                     chat_id: UUID,
                     user_id: str) -> int:
        statement = delete(Chat).where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        result = await self.db.exec(statement)
        return result.rowcount

    async def list_chats(self,
                         user_id: str,
                         limit: int) -> list[Chat]:
        statement = (
            select(Chat)
            .where(col(Chat.user_id) == user_id)
            .order_by(Chat.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.exec(statement)).all())

    @staticmethod
    def _encode_cursor(created_at: datetime, message_id: int) -> str:
        payload = f"{created_at.isoformat()}|{message_id}"
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, int]:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        created_at_raw, message_id_raw = raw.split("|", 1)
        return datetime.fromisoformat(created_at_raw), int(message_id_raw)
