from uuid import UUID, uuid7

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.models.users import UsageMonthly


class UsageDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def try_increment(self,
                            user_id: UUID,
                            month: str,
                            monthly_quota: int) -> bool:
        """Atomically increment usage if under quota. Returns True if allowed."""
        await self.session.exec(
            pg_insert(UsageMonthly)
            .values(id=uuid7(), user_id=user_id, month=month, used=0)
            .on_conflict_do_nothing(index_elements=["user_id", "month"])
        )

        result = await self.session.exec(
            update(UsageMonthly)
            .where(col(UsageMonthly.user_id) == user_id,
                   col(UsageMonthly.month) == month,
                   col(UsageMonthly.used) < monthly_quota)
            .values(used=col(UsageMonthly.used) + 1)
            .returning(col(UsageMonthly.used))
        )
        return result.first() is not None

    async def get_usage(self, user_id: UUID, month: str) -> int:
        """Get current usage count for a user in a given month."""
        result = await self.session.exec(
            select(UsageMonthly.used)
            .where(UsageMonthly.user_id == user_id, UsageMonthly.month == month)
        )
        used = result.first()
        return used if used is not None else 0

    async def reset_usage(self, user_id: UUID, month: str) -> None:
        """Zero out usage counter (called on plan change)."""
        await self.session.exec(
            update(UsageMonthly)
            .where(col(UsageMonthly.user_id) == user_id, col(UsageMonthly.month) == month)
            .values(used=0)
        )
