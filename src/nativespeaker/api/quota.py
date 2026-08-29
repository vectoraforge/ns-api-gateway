"""Quota consumption: the one place an allowance is resolved and spent. A failed provider call is not refunded."""
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud import GrantsDB
from nativespeaker.api.errors import (
    MissingUsageRowError,
    MultipleEffectiveGrantsError,
    QuotaExceededError,
    UnknownTierError,
)

logger = structlog.get_logger()


async def consume_quota(session: AsyncSession, *, user_id: UUID, evaluated_at: datetime,
                        route: str) -> None:
    """Spend one unit of `user_id`'s allowance, or raise. `route` is a path template used as a telemetry label."""
    grants_db = GrantsDB(session)
    grants = await grants_db.lock_effective_grants(user_id, evaluated_at)

    if not grants:
        # Labels come from closed sets only: a fixed branch name and the route template, never an id or a raw path.
        logger.warning("quota_rejected", branch="no_effective_grant", route=route)
        raise QuotaExceededError("No effective grant for this user")

    if len(grants) > 1:
        # A tripwire, not a recovery branch: a partial unique index makes this unreachable, and there is no tie-break.
        logger.error("quota_integrity_failure", branch="multiple_effective_grants", route=route)
        raise MultipleEffectiveGrantsError(len(grants), user_id)

    grant = grants[0]

    # Second in the lock order, always after the grant rows.
    usage = await grants_db.lock_usage(grant.id)
    if usage is None:
        # Fail closed, never mint: a grant without a usage row is a failed write, not a fresh allowance.
        logger.error("quota_integrity_failure", branch="missing_usage_row", route=route)
        raise MissingUsageRowError(grant.id)

    # The only place the period is derived, and always from the request's captured instant, never a clock.
    period = evaluated_at.strftime("%Y-%m")

    if usage.monthly_period != period:
        # The rollover runs before the comparison and in the same transaction, so a reset never commits uncharged.
        usage.monthly_used = 0
        usage.monthly_period = period

    allowance = await grants_db.monthly_credits(grant.tier_id)
    if allowance is None:
        # Fail closed: a missing tier row is neither a zero allowance nor an unbounded one.
        logger.error("quota_integrity_failure", branch="unknown_tier", route=route)
        raise UnknownTierError(grant.tier_id, grant.id)

    # Floored at zero: a stored count above the allowance is ordinary exhaustion, not a negative remainder.
    remaining = max(allowance - usage.monthly_used, 0)
    if remaining == 0:
        # Raised before the increment: a request the service refused must never be charged.
        logger.warning("quota_rejected", branch="allowance_exhausted", route=route)
        raise QuotaExceededError("The allowance for the current period is used up")

    # `usage` is already tracked by this session; `updated_at` is stamped from the captured instant, not a clock.
    usage.monthly_used += 1
    usage.updated_at = evaluated_at


class QuotaGate:
    """One caller's ability to spend, bound to one request. `charge` runs as the provider-admission callback."""

    def __init__(self,
                 session_factory: async_sessionmaker | Callable[[], AsyncSession],
                 *,
                 evaluated_at: datetime,
                 route: str) -> None:
        self._session_factory = session_factory
        # Both come from the request context captured once for this request, and are fixed for this object's life.
        self._evaluated_at = evaluated_at
        self._route = route

    async def charge(self, user_id: UUID) -> None:
        """Spend one unit of `user_id`'s allowance, or raise. Commits on success."""
        # Its own short session: no grant or usage row lock is held across the provider round trip.
        async with self._session_factory() as session:
            try:
                await consume_quota(session,
                                    user_id=user_id,
                                    evaluated_at=self._evaluated_at,
                                    route=self._route)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
