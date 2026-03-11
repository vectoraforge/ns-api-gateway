from uuid import UUID

from sqlalchemy import and_, delete, insert, or_, Sequence
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, col

from app.exceptions import InvalidChatError
from app.database.models import Chat, Message


class ChatsDB:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, chat_id: UUID, user_id: str) -> None:
        self.db.add(Chat(id=chat_id, user_id=user_id))

    async def delete(self, chat_id: UUID, user_id: str) -> int:
        statement = delete(Chat).where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        result = await self.db.exec(statement)
        return result.rowcount()

    async def get(self, chat_id: UUID, user_id: str) -> Chat | None:
        statement = (
            select(Chat)
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        )
        chat = (await self.db.exec(statement)).first()
        if chat is None:
            raise ValueError("Chat not found")
        return chat

    async def get_history(self, chat_id: UUID, user_id: str) -> Sequence:
        statement = (
            select(Message.role, Message.content)
            .join(Chat, col(Message.chat_id) == Chat.id)
            .where(Message.chat_id == chat_id, Chat.user_id == user_id)
            .order_by(Message.created_at)
        )
        return (await self.db.exec(statement)).all()

    async def get_messages(self,
                           chat_id: UUID,
                           user_id: str,
                           limit: int,
                           cursor: str | None = None) -> tuple[list[Message], str | None]:
        statement = (
            select(Message)
            .join(Chat, Message.chat_id == Chat.id)
            .where(and_(Message.chat_id == chat_id, Chat.user_id == user_id))
        )
        if cursor:
            cursor_created_at, cursor_id = self._decode_cursor(cursor)
            statement = statement.where(or_(Message.created_at < cursor_created_at,
                                            and_(Message.created_at == cursor_created_at,
                                                 Message.id < cursor_id)))
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

    async def save_messages(self, chat_id: UUID, human: str, assistant: str) -> None:
        await self.db.exec(insert(Message),
                         [{"chat_id": chat_id, "role": "human", "content": human},
                          {"chat_id": chat_id, "role": "assistant", "content": assistant}])
