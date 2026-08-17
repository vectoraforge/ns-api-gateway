"""Monthly usage, owned by the access grant that authorizes the credits it counts.

Consumption is a `core.user_monthly_usage` row keyed by `grant_id`, never by user and never by
a plan column on `core.users`: a user's allowance comes from the tier their effective grant
points at, and the counter that spends it hangs off that same grant.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.entitlement import AccessGrantStatus
from nativespeaker.api.models.users import AccessGrant, AccessTier, UserMonthlyUsage
from nativespeaker.api.quota.grants import (
    EntitlementReport,
    GrantRow,
    TooManyActiveGrantsError,
    effective_tier,
    entitlement_report,
)
from nativespeaker.api.quota.usage import (
    NewUsageRow,
    derived_allowance,
    new_usage_row,
    period_of,
)

__all__ = [
    "EffectiveGrant",
    "GrantsDB",
    "QuotaStoreDB",
    "TooManyActiveGrantsError",
    "UsageDB",
    "current_period",
]


def current_period(now: datetime | None = None) -> str:
    """The current monthly period, computed from the clock."""
    return period_of(now)


@dataclass(frozen=True, slots=True)
class EffectiveGrant:
    """The user's single effective access grant and the allowance its tier configures."""
    grant_id: UUID
    tier_id: str
    monthly_credits: int


class GrantsDB:
    """Reads the effective access grant. Read paths own no repair: nothing here mutates grant
    state, and no path selects a grant by `status` alone."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def grant_rows(self,
                         user_id: UUID,
                         now: datetime,
                         *,
                         for_update: bool = False) -> list[GrantRow]:
        """The user's candidate grant rows under the shared effective-grant predicate, joined to
        their `core.access_tiers` row.

        `core.access_grants` is the single entitlement table read here — subscription-backed and
        non-subscription access alike — and the predicate is the whole conjunction, never
        `status` alone. The subscription table is not consulted: the deferrable foreign key
        already guarantees an active subscription-backed grant is product-entitled.
        """
        # [impl->req~quota-access-grants-single-entitlement-table~1]
        # [impl->req~quota-effective-tier-step-01~1]
        # [impl->req~quota-effective-tier-step-05~1]
        # [impl->req~schema-user-monthly-usage-allowance-derived-from-tier~1]
        # [impl->req~schema-access-tiers-monthly-credits-allowance~1]
        statement = (
            select(AccessGrant, AccessTier.monthly_credits)
            .join(AccessTier, col(AccessTier.id) == col(AccessGrant.tier_id))
            .where(col(AccessGrant.user_id) == user_id,
                   col(AccessGrant.status) == AccessGrantStatus.active,
                   col(AccessGrant.starts_at) <= now,
                   (col(AccessGrant.ends_at).is_(None)) | (col(AccessGrant.ends_at) > now)))
        if for_update:
            # 1. lock the grant row itself `FOR UPDATE`; the tier row is configuration and is
            #    not locked with it.
            # [impl->req~quota-rollover-step-01~1]
            statement = statement.with_for_update(of=AccessGrant)
        result = await self.session.exec(statement)
        return [GrantRow(grant_id=grant.id, user_id=grant.user_id, tier_id=grant.tier_id,
                         source=grant.source, status=grant.status, starts_at=grant.starts_at,
                         ends_at=grant.ends_at, subscription_id=grant.subscription_id,
                         tier_monthly_credits=derived_allowance(grant.tier_id, monthly_credits))
                for grant, monthly_credits in result.all()]

    async def effective_grant(self,
                              user_id: UUID,
                              now: datetime | None = None) -> EffectiveGrant | None:
        """The active grant for this user under the shared effective-grant predicate — `status =
        'active'` and `starts_at <= now` and (`ends_at IS NULL OR ends_at > now`) — joined to its
        tier. More than one is an invariant violation; none means an allowance of zero.

        The allowance comes from that join and from nothing else: it is a property of the tier
        the grant points at, never a stored column on the usage row.
        """
        # [impl->req~quota-shared-effective-grant-predicate~1]
        moment = now or datetime.now(UTC)
        tier = effective_tier(await self.grant_rows(user_id, moment), moment)
        if tier.grant is None:
            # [impl->req~quota-no-grant-zero-allowance~1]
            return None
        return EffectiveGrant(grant_id=tier.grant.grant_id, tier_id=tier.grant.tier_id,
                              monthly_credits=tier.allowance)

    async def entitlement(self,
                          user_id: UUID,
                          now: datetime | None = None) -> EntitlementReport:
        """The reported entitlement values, derived from one captured evaluation time. Strictly
        read-only: no lock, no rollover write, and no grant flip."""
        # [impl->req~quota-report-single-effective-grant~1]
        # [impl->req~quota-auth-sync-no-grant-defaults~1]
        moment = now or datetime.now(UTC)
        rows = await self.grant_rows(user_id, moment)
        stored: tuple[str, int] | None = None
        grant = effective_tier(rows, moment).grant
        if grant is not None:
            stored = await UsageDB(self.session).stored_usage(grant.grant_id)
        return entitlement_report(rows, now=moment,
                                  stored_period=stored[0] if stored else None,
                                  stored_used=stored[1] if stored else 0)


class UsageDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_for_grant(self,
                               grant_id: UUID,
                               *,
                               transaction: object,
                               carried: tuple[str, int] | None = None,
                               now: datetime | None = None) -> NewUsageRow:
        """Create this grant's usage row in the transaction that creates the grant itself —
        purchase ingestion, either free-grant claim, or restore's adoption of an unclaimed
        subscription. It initializes usage state only. A fresh grant starts at the current
        accounting month with a zero counter; a grant that supersedes another carries that
        grant's `(monthly_period, monthly_used)` across unchanged, so no conversion path needs
        an INSERT of its own."""
        # [impl->req~schema-user-monthly-usage-created-with-grant~1]
        # [impl->req~schema-user-monthly-usage-row-initializes-usage-only~1]
        stamp = now or datetime.now(UTC)
        row = new_usage_row(grant_id, now=stamp, carried=carried,
                            grant_transaction=transaction, usage_transaction=self.session)
        await self.session.exec(
            pg_insert(UserMonthlyUsage)
            .values(grant_id=row.grant_id, monthly_period=row.monthly_period,
                    monthly_used=row.monthly_used, created_at=stamp, updated_at=stamp)
        )
        return row

    async def stored_usage(self, grant_id: UUID,
                           *, for_update: bool = False) -> tuple[str, int] | None:
        """This grant's stored `(monthly_period, monthly_used)`, or `None` when the row is
        missing. `core.user_monthly_usage` is keyed by `grant_id` — the grant whose credits are
        being consumed — and carries no allowance of its own.
        """
        # [impl->req~quota-usage-model-owned-by-schema-file~1]
        statement = (
            select(UserMonthlyUsage.monthly_period, UserMonthlyUsage.monthly_used)
            .where(col(UserMonthlyUsage.grant_id) == grant_id))
        if for_update:
            # 2. the usage row is locked second, after its grant.
            # [impl->req~quota-rollover-step-02~1]
            statement = statement.with_for_update()
        result = await self.session.exec(statement)
        row = result.first()
        if row is None:
            return None
        return (row[0], row[1])

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


class QuotaStoreDB:
    """The four statements the lazy monthly rollover sequence takes, in the order it takes them:
    the grant row locked `FOR UPDATE`, its usage row locked second, the month's reset, and the
    increment. Nothing else runs inside those locks."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.grants = GrantsDB(session)
        self.usage = UsageDB(session)

    async def locked_grant_rows(self, user_id: UUID, now: datetime) -> Sequence[GrantRow]:
        # [impl->req~quota-rollover-step-01~1]
        return await self.grants.grant_rows(user_id, now, for_update=True)

    async def locked_usage_row(self, grant_id: UUID) -> tuple[str, int] | None:
        """The usage row, locked second. This path creates nothing: the row was written in the
        transaction that created its grant, so a grant without one is a server-side data error
        and the request fails closed rather than minting a counter."""
        # [impl->req~quota-rollover-step-02~1]
        # [impl->req~schema-user-monthly-usage-created-with-grant~1]
        return await self.usage.stored_usage(grant_id, for_update=True)

    async def write_rollover(self, grant_id: UUID, values: Mapping[str, Any]) -> None:
        """The lazy monthly reset, written in place on the row this transaction already holds:
        the first quota-checked request of a new month advances `monthly_period` and zeroes
        `monthly_used`, rather than carrying the old month's count forward."""
        # [impl->req~quota-rollover-step-04~1]
        # [impl->req~schema-user-monthly-usage-lazy-monthly-reset~1]
        await self.session.exec(
            update(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id)
            .values(**dict(values)))

    async def increment_usage(self, grant_id: UUID, period: str) -> None:
        """Consume usage by incrementing `monthly_used` — the consumption already recorded for
        the stored `monthly_period`, and the only counter this path writes."""
        # [impl->req~quota-rollover-step-08~1]
        # [impl->req~schema-user-monthly-usage-monthly-used-field~1]
        await self.session.exec(
            update(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id,
                   col(UserMonthlyUsage.monthly_period) == period)
            .values(monthly_used=col(UserMonthlyUsage.monthly_used) + 1,
                    updated_at=datetime.now(UTC)))

    async def commit(self) -> None:
        """End the sequence's own transaction, releasing the grant and usage locks before the
        handler runs. The rollover shares the grant-then-usage lock order with restore, never
        restore's longer transaction shape: nothing external happens under these locks, so they
        are not left open across the handler's outbound model call."""
        # [impl->req~quota-rollover-lock-scope~1]
        await self.session.commit()
