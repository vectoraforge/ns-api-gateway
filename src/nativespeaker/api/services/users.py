from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth import UserIdentity
from nativespeaker.api.database import UsersDB
from nativespeaker.api.models import User


class UserService:

    def __init__(self, db: AsyncSession):
        self.users_db = UsersDB(db)

    async def get_or_create(self, identity: UserIdentity, *, issuer: str) -> User:
        """Resolve or create the internal user behind a backend-verified `(issuer, subject)`."""
        return await self.users_db.get_or_create(identity, issuer=issuer)

    async def get_by_id(self, user_id) -> User | None:
        return await self.users_db.get_by_id(user_id)
