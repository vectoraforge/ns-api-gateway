"""The configured access tiers, as they live in PostgreSQL.

The tier catalogue is product configuration: the application configuration file declares it and
`core.access_tiers` stores it, one row per tier keyed by the tier's stable `id`. Startup writes
the configured values through this module, and the tier-sizing invariant is re-checked here so
an edited catalogue is refused rather than applied silently.
"""

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.models.users import AccessTier
from nativespeaker.api.quota.tiers import AccessTierEntry, assert_tier_sizing, tier_rows


class AccessTiersDB:
    """Writes the configured tier catalogue to `core.access_tiers`."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def sync(self, catalogue: Mapping[str, AccessTierEntry]) -> list[str]:
        """Apply the configured catalogue: one row per tier, inserted or updated in place under
        its stable `id`, so grants and subscriptions keep pointing at the same identifier while
        its credit amount changes. The sizing invariant is enforced before anything is written —
        a violating catalogue is rejected outright and no row is touched."""
        # [impl->req~schema-access-tiers-sizing-invariant-enforced~1]
        assert_tier_sizing(catalogue)
        now = datetime.now(UTC)
        # Access tiers are product configuration in PostgreSQL: additional tiers are additional
        # rows here, and no per-user numeric credit override exists anywhere.
        # [impl->req~schema-access-tiers-product-configuration~1]
        # [impl->req~schema-access-tiers-custom-tiers-as-rows~1]
        for row in tier_rows(catalogue, now=now):
            # [impl->req~schema-access-tiers-id-stable-identifier~1]
            await self.session.exec(
                pg_insert(AccessTier)
                .values(id=row.id, monthly_credits=row.monthly_credits,
                        created_at=now, updated_at=now)
                .on_conflict_do_update(index_elements=["id"],
                                       set_={"monthly_credits": row.monthly_credits,
                                             "updated_at": now})
            )
        return sorted(catalogue)
