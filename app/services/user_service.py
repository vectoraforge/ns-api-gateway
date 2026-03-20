from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth import UserIdentity
from app.database import UsersDB
from app.models import User


class UserService:

    def __init__(self, db: AsyncSession):
        self.users_db = UsersDB(db)

    async def get_or_create(self, identity: UserIdentity) -> User:
        return await self.users_db.get_or_create(identity)

    async def get_by_id(self, user_id) -> User | None:
        return await self.users_db.get_by_id(user_id)
