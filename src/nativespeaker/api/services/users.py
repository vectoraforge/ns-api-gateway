from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.database import UsersDB
from nativespeaker.api.models import User


class UserService:

    def __init__(self, db: AsyncSession):
        self.users_db = UsersDB(db)

    async def get_or_create(self, subject: str) -> User:
        return await self.users_db.get_or_create(subject)

    async def get_by_id(self, user_id) -> User | None:
        return await self.users_db.get_by_id(user_id)
