"""Quota consumption: the one place an allowance is resolved and spent.
A failed provider call is not refunded."""
import math
from collections.abc import Callable
from datetime import UTC, datetime
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
from nativespeaker.api.tables import monthly_period_for

logger = structlog.get_logger()

RETRY_AFTER_CEILING_SECONDS = 300


def seconds_until_rollover(instant: datetime) -> int:
    """Whole seconds from this instant to the UTC month boundary the allowance rolls over on."""
    utc = instant.astimezone(UTC)
    december = utc.month == 12
    rollover = utc.replace(year=utc.year + (1 if december else 0),
                           month=1 if december else utc.month + 1,
                           day=1, hour=0, minute=0, second=0, microsecond=0)
    return max(math.ceil((rollover - instant).total_seconds()), 1)


class QuotaService:

    def __init__(self, session_factory: async_sessionmaker | Callable[[], AsyncSession]) -> None:
        self.session_factory = session_factory

    async def charge(self, *, user_id: UUID) -> None:
        """Spend one unit of `user_id`'s allowance, or raise. Commits on success."""
        instant = datetime.now(UTC)
        retry_after_seconds = min(seconds_until_rollover(instant),
                                  RETRY_AFTER_CEILING_SECONDS)

        # Its own short session: no grant or usage row lock is held across the provider round trip.
        async with self.session_factory() as session:
            try:
                grants_db = GrantsDB(session)
                grants = await grants_db.lock_effective_grants(user_id)

                if not grants:
                    # Labels come from a closed set only: a fixed branch name, never an id or a raw path.
                    logger.warning("quota_rejected", branch="no_effective_grant")
                    raise QuotaExceededError("No effective grant for this user",
                                             retry_after_seconds=retry_after_seconds)

                if len(grants) > 1:
                    # A tripwire, not a recovery branch: a partial unique index makes it unreachable.
                    raise MultipleEffectiveGrantsError(len(grants), user_id)

                grant = grants[0]

                # Second in the lock order, always after the grant rows.
                usage = await grants_db.lock_usage(grant.id)
                if usage is None:
                    # Fail closed, never mint: a grant without a usage row is a failed write, not a fresh allowance.
                    raise MissingUsageRowError(grant.id)

                period = monthly_period_for(instant)

                if usage.monthly_period < period:  # Use "<", never "!=": a month ahead keeps its count.
                    # Rollover runs before the comparison and in the same transaction: no reset commits uncharged.
                    usage.monthly_used = 0
                    usage.monthly_period = period

                allowance = await grants_db.monthly_credits(grant.tier_id)
                if allowance is None:
                    # Fail closed: a missing tier row is neither a zero allowance nor an unbounded one.
                    raise UnknownTierError(grant.tier_id, grant.id)

                # Floored at zero: a stored count above the allowance is ordinary exhaustion.
                remaining = max(allowance - usage.monthly_used, 0)
                if remaining == 0:
                    # Raised before the increment: a request the service refused must never be charged.
                    logger.warning("quota_rejected", branch="allowance_exhausted")
                    raise QuotaExceededError("The allowance for the current period is used up",
                                             retry_after_seconds=retry_after_seconds)

                usage.monthly_used += 1
                usage.updated_at = instant

                await session.commit()
            except Exception:
                await session.rollback()
                raise
