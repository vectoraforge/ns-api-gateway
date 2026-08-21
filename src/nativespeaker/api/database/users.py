from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.models import User


class UsersDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, subject: str) -> User:
        # Takes the verified `sub` only. §1.2 forbids deriving identity from other claims, so the
        # `email` and `name` this used to copy off the token are gone with `UserIdentity`.
        # Plan 04 deletes this module; plan 03's identity resolver replaces it and never creates.
        stmt = (
            pg_insert(User)
            .values(jwt_sub=subject)
            .on_conflict_do_nothing(index_elements=["jwt_sub"])
        )
        await self.session.exec(stmt)
        result = await self.session.exec(
            select(User).where(User.jwt_sub == subject)
        )
        return result.one()

    async def get_by_id(self, user_id) -> User | None:
        result = await self.session.exec(
            select(User).where(User.id == user_id)
        )
        return result.first()
