from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import col, delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Chat, Message


class ChatsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    def create_chat(self, obj: Chat):
        self.session.add(obj)

    async def get_chat(self, chat_id: UUID, user_id: UUID) -> Chat | None:
        statement = (
            select(Chat)
            .options(selectinload(Chat.messages))  # type: ignore[invalid-argument-type]
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        )
        return (await self.session.exec(statement)).first()

    async def count_chats(self, user_id: UUID) -> int:
        statement = select(func.count()).select_from(Chat).where(Chat.user_id == user_id)
        return await self.session.scalar(statement)

    async def list_chats(self, user_id: UUID) -> list[Chat]:
        statement = (
            select(Chat)
            .where(col(Chat.user_id) == user_id)
            .order_by(col(Chat.created_at).desc())
        )
        return list((await self.session.exec(statement)).all())

    async def get_messages(self,
                           chat_id: UUID,
                           user_id: UUID) -> list[Message]:
        statement = (
            select(Message)
            .join(Chat, col(Message.chat_id) == col(Chat.id))
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
            .order_by(col(Message.id).desc())
        )
        return list((await self.session.exec(statement)).all())

    async def delete(self,
                     chat_id: UUID,
                     user_id: UUID) -> int:
        statement = delete(Chat).where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        result = await self.session.exec(statement)
        return result.rowcount
