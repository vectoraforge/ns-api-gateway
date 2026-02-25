from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import func

from app.models import Chat, Message


class Chats:
    async def create_chat(self, db: AsyncSession, chat_id: UUID, lang: str) -> None:
        db.add(Chat(id=chat_id, lang=lang))
        await db.commit()

    async def get_chat(self, db: AsyncSession, chat_id: UUID) -> dict | None:
        chat = await db.get(Chat, chat_id)
        return {"id": chat.id, "lang": chat.lang} if chat else None

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

    async def save_messages(self, db: AsyncSession, chat_id: UUID, human: str, assistant: str) -> None:
        db.add(Message(chat_id=chat_id, role="human", content=human))
        db.add(Message(chat_id=chat_id, role="assistant", content=assistant))
        await db.commit()
