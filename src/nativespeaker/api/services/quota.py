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

# The ceiling on the shared `Retry-After`. An absent grant becomes effective the instant a claim or
# a restore commits -- both write `starts_at=evaluated_at`, which the shared effective predicate
# reads on the very next request -- so the raw rollover strands a caller who has just paid for up
# to a month. An early retry on the exhausted branch is refused again and grants nothing.
RETRY_AFTER_CEILING_SECONDS = 300


def seconds_until_rollover(evaluated_at: datetime) -> int:
    """Whole seconds from this instant to the UTC month boundary the allowance rolls over on."""
    # Converted first, as `monthly_period_for` is: `replace` reads the stored wall clock, so a
    # non-UTC instant would name the boundary of a month other than the one the counter is keyed by.
    instant = evaluated_at.astimezone(UTC)
    december = instant.month == 12
    rollover = instant.replace(year=instant.year + (1 if december else 0),
                               month=1 if december else instant.month + 1,
                               day=1, hour=0, minute=0, second=0, microsecond=0)
    # Rounded up and floored at one: `Retry-After: 0` invites the immediate retry this refuses.
    return max(math.ceil((rollover - evaluated_at).total_seconds()), 1)


class QuotaService:

    def __init__(self, session_factory: async_sessionmaker | Callable[[], AsyncSession]) -> None:
        self.session_factory = session_factory

    async def charge(self, *, user_id: UUID, evaluated_at: datetime) -> None:
        """Spend one unit of `user_id`'s allowance, or raise. Commits on success."""
        # One value for both refusal branches: SHARED-INVARIANTS requires the header on a 429, and
        # requires the branches within a class to stay indistinguishable. Capped rather than the
        # raw rollover, for the reason the ceiling states: an absent grant does change before the
        # period does, so the rollover is a floor under one branch only.
        retry_after_seconds = min(seconds_until_rollover(evaluated_at),
                                  RETRY_AFTER_CEILING_SECONDS)

        # Its own short session: no grant or usage row lock is held across the provider round trip.
        async with self.session_factory() as session:
            try:
                grants_db = GrantsDB(session)
                grants = await grants_db.lock_effective_grants(user_id, evaluated_at)

                if not grants:
                    # Labels come from a closed set only: a fixed branch name, never an id or a raw path.
                    logger.warning("quota_rejected", branch="no_effective_grant")
                    raise QuotaExceededError("No effective grant for this user",
                                             retry_after_seconds=retry_after_seconds)

                if len(grants) > 1:
                    # A tripwire, not a recovery branch: a partial unique index makes it unreachable.
                    # No line of its own: the class declares `log_level = ERROR`, so the shared
                    # handler records it once under its own name, as `services/sync.py` already relies on.
                    raise MultipleEffectiveGrantsError(len(grants), user_id)

                grant = grants[0]

                # Second in the lock order, always after the grant rows.
                usage = await grants_db.lock_usage(grant.id)
                if usage is None:
                    # Fail closed, never mint: a grant without a usage row is a failed write, not a fresh allowance.
                    raise MissingUsageRowError(grant.id)

                period = monthly_period_for(evaluated_at)

                # Ordered, never `!=`: an instant behind the stored period spends that month, never resets it.
                if usage.monthly_period < period:
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

                # `updated_at` is stamped from the captured instant, not a clock.
                usage.monthly_used += 1
                usage.updated_at = evaluated_at

                await session.commit()
            except Exception:
                await session.rollback()
                raise
