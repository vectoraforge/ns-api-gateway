"""Auth-state reconciliation: the entitlement one caller holds at one instant, read and never written."""
from datetime import datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud import GrantsDB
from nativespeaker.api.errors import (
    MissingUsageRowError,
    MultipleEffectiveGrantsError,
    UnknownTierError,
)
from nativespeaker.api.schemas.auth import Entitlement, EntitlementStatus, EntitlementType
from nativespeaker.api.tables import monthly_period_for


class SyncService:

    def __init__(self, db: AsyncSession, evaluated_at: datetime) -> None:
        self.grants_db = GrantsDB(db)
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at

    async def read_entitlement(self, user_id: UUID) -> Entitlement:
        """Report the entitlement `user_id` holds at the captured instant, taking no lock and writing nothing."""
        period = monthly_period_for(self.evaluated_at)

        grants = await self.grants_db.read_effective_grants(user_id)
        if not grants:
            # Not an error: this is the ordinary answer for a caller who has never claimed a grant.
            return Entitlement(type=EntitlementType.none,
                               status=EntitlementStatus.none,
                               tier_id=None,
                               monthly_credits=None,
                               current_period=period,
                               monthly_used=0)

        if len(grants) > 1:
            # A tripwire, not a recovery branch: a partial unique index makes it unreachable.
            raise MultipleEffectiveGrantsError(len(grants), user_id)

        grant = grants[0]

        usage = await self.grants_db.read_usage(grant.id)
        if usage is None:
            # Fail closed: reporting zero used would promise an allowance the charge refuses at this same instant.
            raise MissingUsageRowError(grant.id)

        allowance = await self.grants_db.monthly_credits(grant.tier_id)
        if allowance is None:
            # Fail closed: a missing tier row is neither a zero allowance nor an unbounded one.
            raise UnknownTierError(grant.tier_id, grant.id)

        # A stored period ahead of this month keeps its own count.
        used = 0 if usage.monthly_period < period else usage.monthly_used

        return Entitlement(type=EntitlementType(grant.source.value),
                           status=EntitlementStatus.active,
                           tier_id=grant.tier_id,
                           monthly_credits=allowance,
                           current_period=period,
                           monthly_used=used)
