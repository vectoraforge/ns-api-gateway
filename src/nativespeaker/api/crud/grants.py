"""Entitlement reads over `core.access_grants`. Global lock order: grant rows ascending by id, then usage rows."""
from datetime import datetime
from uuid import UUID

from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.tables import AccessGrant, AccessGrantStatus, AccessTier, UserMonthlyUsage


class GrantsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."""
        statement = (
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id,
                   # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
                   col(AccessGrant.status) == AccessGrantStatus.active,
                   col(AccessGrant.starts_at) <= evaluated_at,
                   or_(col(AccessGrant.ends_at).is_(None),
                       col(AccessGrant.ends_at) > evaluated_at))
            .order_by(col(AccessGrant.id).asc())
            # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
            .with_for_update()
        )
        # No `.limit(...)`: the caller must see a second effective grant and fail closed on it.
        return list((await self.session.exec(statement)).all())

    async def lock_usage(self, grant_id: UUID) -> UserMonthlyUsage | None:
        """Lock and return `grant_id`'s usage row, or `None`. Second in the lock order and never first."""
        # Never inserts: `None` is the fail-closed signal, not a cue to mint a row and hand out an allowance.
        statement = (
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id)
            .with_for_update()
        )
        return (await self.session.exec(statement)).first()

    async def monthly_credits(self, tier_id: str) -> int | None:
        statement = select(AccessTier.monthly_credits).where(col(AccessTier.id) == tier_id)
        return (await self.session.exec(statement)).first()
