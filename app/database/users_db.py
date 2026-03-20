from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth import UserIdentity
from app.models import User


class UsersDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, identity: UserIdentity) -> User:
        stmt = (
            pg_insert(User)
            .values(jwt_sub=identity.sub, email=identity.email, name=identity.name)
            .on_conflict_do_nothing(index_elements=["jwt_sub"])
        )
        await self.session.exec(stmt)
        result = await self.session.exec(
            select(User).where(User.jwt_sub == identity.sub)
        )
        return result.one()

    async def get_by_id(self, user_id) -> User | None:
        result = await self.session.exec(
            select(User).where(User.id == user_id)
        )
        return result.first()
