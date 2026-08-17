"""Monthly usage, owned by the access grant that authorizes the credits it counts.

Consumption is a `core.user_monthly_usage` row keyed by `grant_id`, never by user and never by
a plan column on `core.users`: a user's allowance comes from the tier their effective grant
points at, and the counter that spends it hangs off that same grant.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.entitlement import AccessGrantStatus
from nativespeaker.api.models.users import AccessGrant, AccessTier, UserMonthlyUsage
from nativespeaker.api.quota.usage import (
    NewUsageRow,
    derived_allowance,
    needs_rollover,
    new_usage_row,
    period_of,
    require_usage_row,
)


def current_period(now: datetime | None = None) -> str:
    """The current monthly period, computed from the clock."""
    return period_of(now)


@dataclass(frozen=True, slots=True)
class EffectiveGrant:
    """The user's single effective access grant and the allowance its tier configures."""
    grant_id: UUID
    tier_id: str
    monthly_credits: int


class TooManyActiveGrantsError(RuntimeError):
    """More than one active grant was found for one user: an invariant violation, not a choice
    between them."""


class GrantsDB:
    """Reads the effective access grant. Read paths own no repair: nothing here mutates grant
    state, and no path selects a grant by `status` alone."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def effective_grant(self,
                              user_id: UUID,
                              now: datetime | None = None) -> EffectiveGrant | None:
        """The active grant for this user under the shared effective-grant predicate — `status =
        'active'` and `starts_at <= now` and (`ends_at IS NULL OR ends_at > now`) — joined to its
        tier. More than one is an invariant violation; none means an allowance of zero.

        The allowance comes from that join and from nothing else: it is a property of the tier
        the grant points at, never a stored column on the usage row.
        """
        # [impl->req~schema-user-monthly-usage-allowance-derived-from-tier~1]
        # [impl->req~schema-access-tiers-monthly-credits-allowance~1]
        moment = now or datetime.now(UTC)
        result = await self.session.exec(
            select(AccessGrant.id, AccessGrant.tier_id, AccessTier.monthly_credits)
            .join(AccessTier, col(AccessTier.id) == col(AccessGrant.tier_id))
            .where(col(AccessGrant.user_id) == user_id,
                   col(AccessGrant.status) == AccessGrantStatus.active,
                   col(AccessGrant.starts_at) <= moment,
                   (col(AccessGrant.ends_at).is_(None)) | (col(AccessGrant.ends_at) > moment))
        )
        rows = result.all()
        if not rows:
            return None
        if len(rows) > 1:
            raise TooManyActiveGrantsError(f"{user_id} has {len(rows)} active access grants")
        grant_id, tier_id, monthly_credits = rows[0]
        return EffectiveGrant(grant_id=grant_id, tier_id=tier_id,
                              monthly_credits=derived_allowance(tier_id, monthly_credits))


class UsageDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_for_grant(self,
                               grant_id: UUID,
                               *,
                               transaction: object,
                               now: datetime | None = None) -> NewUsageRow:
        """Create this grant's usage row in the transaction that creates the grant itself —
        purchase ingestion, either free-grant claim, or restore's adoption of an unclaimed
        subscription. It initializes usage state only: the current accounting month and a zero
        counter."""
        # [impl->req~schema-user-monthly-usage-created-with-grant~1]
        # [impl->req~schema-user-monthly-usage-row-initializes-usage-only~1]
        stamp = now or datetime.now(UTC)
        row = new_usage_row(grant_id, now=stamp,
                            grant_transaction=transaction, usage_transaction=self.session)
        await self.session.exec(
            pg_insert(UserMonthlyUsage)
            .values(grant_id=row.grant_id, monthly_period=row.monthly_period,
                    monthly_used=row.monthly_used, created_at=stamp, updated_at=stamp)
        )
        return row

    async def try_increment(self,
                            grant_id: UUID,
                            period: str,
                            monthly_quota: int) -> bool:
        """Atomically increment this grant's usage if under its allowance. Returns True if
        allowed. A row whose stored period is not the current one is rolled over in place rather
        than carried forward.

        This path creates nothing: the row was written with the grant, so a grant without one is
        a server-side data error and the request fails closed.
        """
        now = datetime.now(UTC)
        stored = await self.session.exec(
            select(UserMonthlyUsage.monthly_period)
            .where(col(UserMonthlyUsage.grant_id) == grant_id)
        )
        # [impl->req~schema-user-monthly-usage-created-with-grant~1]
        stored_period = require_usage_row(stored.first(), grant_id)
        # The lazy monthly reset: the first quota-checked request of a new month advances
        # `monthly_period` and zeroes `monthly_used` in place.
        # [impl->req~schema-user-monthly-usage-lazy-monthly-reset~1]
        if needs_rollover(stored_period, period):
            await self.session.exec(
                update(UserMonthlyUsage)
                .where(col(UserMonthlyUsage.grant_id) == grant_id,
                       col(UserMonthlyUsage.monthly_period) != period)
                .values(monthly_period=period, monthly_used=0, updated_at=now)
            )
        # [impl->req~schema-user-monthly-usage-monthly-used-field~1]
        result = await self.session.exec(
            update(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id,
                   col(UserMonthlyUsage.monthly_period) == period,
                   col(UserMonthlyUsage.monthly_used) < monthly_quota)
            .values(monthly_used=col(UserMonthlyUsage.monthly_used) + 1, updated_at=now)
            .returning(col(UserMonthlyUsage.monthly_used))
        )
        return result.first() is not None

    async def get_usage(self, grant_id: UUID, period: str) -> int:
        """This grant's consumption in the given period. A stored row for another period counts
        as zero for this one."""
        result = await self.session.exec(
            select(UserMonthlyUsage.monthly_used)
            .where(UserMonthlyUsage.grant_id == grant_id,
                   UserMonthlyUsage.monthly_period == period)
        )
        used = result.first()
        return used if used is not None else 0

    async def reset_usage(self, grant_id: UUID, period: str) -> None:
        """Zero out this grant's counter for the period (called on a tier change)."""
        await self.session.exec(
            update(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id,
                   col(UserMonthlyUsage.monthly_period) == period)
            .values(monthly_used=0, updated_at=datetime.now(UTC))
        )
