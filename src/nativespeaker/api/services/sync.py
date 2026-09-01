"""Auth-state reconciliation: the entitlement one caller holds at one instant, read and never written."""
from datetime import datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud import GrantsDB
from nativespeaker.api.schemas.auth import Entitlement, EntitlementStatus, EntitlementType


class SyncService:

    def __init__(self, db: AsyncSession, evaluated_at: datetime) -> None:
        self.session = db
        self.grants_db = GrantsDB(db)
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at

    async def read_entitlement(self, user_id: UUID) -> Entitlement:
        """Report the entitlement `user_id` holds at the captured instant, taking no lock and writing nothing."""
        # The only place the period is derived, and always from the request's captured instant.
        period = self.evaluated_at.strftime("%Y-%m")

        grants = await self.grants_db.read_effective_grants(user_id, self.evaluated_at)
        if not grants:
            # Not an error: this is the ordinary answer for a caller who has never claimed a grant.
            return Entitlement(type=EntitlementType.none,
                               status=EntitlementStatus.none,
                               tier_id=None,
                               monthly_credits=None,
                               current_period=period,
                               monthly_used=0)

        grant = grants[0]

        usage = await self.grants_db.read_usage(grant.id)
        allowance = await self.grants_db.monthly_credits(grant.tier_id)

        # A count from an earlier period is selected past, never assigned away: this read must not roll over.
        used = 0 if usage.monthly_period != period else usage.monthly_used

        return Entitlement(type=EntitlementType(grant.source.value),
                           status=EntitlementStatus.active,
                           tier_id=grant.tier_id,
                           monthly_credits=allowance,
                           current_period=period,
                           monthly_used=used)
