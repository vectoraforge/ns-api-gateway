from uuid import UUID, uuid7

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession


class UsageDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def try_increment(self,
                            user_id: UUID,
                            month: str,
                            monthly_quota: int) -> bool:
        """Atomically increment usage if under quota. Returns True if allowed."""
        await self.session.exec(text(
            "INSERT INTO usage_monthly (id, user_id, month, used) "
            "VALUES (:id, :user_id, :month, 0) "
            "ON CONFLICT (user_id, month) DO NOTHING"
        ), params={"id": uuid7(), "user_id": user_id, "month": month})

        result = await self.session.exec(text(
            "UPDATE usage_monthly u "
            "SET used = u.used + 1 "
            "WHERE u.user_id = :user_id "
            "  AND u.month = :month "
            "  AND u.used < :monthly_quota "
            "RETURNING u.used"
        ), params={"user_id": user_id, "month": month, "monthly_quota": monthly_quota})
        return result.first() is not None

    async def get_usage(self, user_id: UUID, month: str) -> int:
        """Get current usage count for a user in a given month."""
        result = await self.session.exec(text(
            "SELECT used FROM usage_monthly "
            "WHERE user_id = :user_id AND month = :month"
        ), params={"user_id": user_id, "month": month})
        row = result.first()
        return row[0] if row else 0

    async def reset_usage(self, user_id: UUID, month: str) -> None:
        """Zero out usage counter (called on plan change)."""
        await self.session.exec(text(
            "UPDATE usage_monthly SET used = 0 "
            "WHERE user_id = :user_id AND month = :month"
        ), params={"user_id": user_id, "month": month})
