"""One linked caller with one effective grant reads its entitlement over the real stack."""
from datetime import UTC, datetime

import pytest
from sqlmodel import col, select

from nativespeaker.api.tables import AccessTier

pytestmark = pytest.mark.e2e


async def _monthly_credits(factory, tier_id: str) -> int:
    """The seeded tier's allowance, read back through the test's own factory rather than assumed."""
    async with factory() as session:
        statement = select(AccessTier.monthly_credits).where(col(AccessTier.id) == tier_id)
        return (await session.exec(statement)).one()


@pytest.mark.asyncio(loop_scope="module")
class TestTheEntitlementHappyPath:
    """One linked caller, one effective grant, and the whole body the route answers with."""

    async def test_a_linked_caller_reads_the_entitlement_it_holds(
            self, async_client, _db_transaction, linked_firebase_identity, quota_grant):
        _, identity = linked_firebase_identity
        grant, usage = quota_grant
        allowance = await _monthly_credits(_db_transaction, grant.tier_id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        # The whole body, not two known keys: a seventh field would pass the weaker check.
        assert response.json() == {
            "entitlement": {"type": grant.source.value,
                            "status": "active",
                            "tier_id": grant.tier_id,
                            "monthly_credits": allowance,
                            "current_period": datetime.now(UTC).strftime("%Y-%m"),
                            "monthly_used": usage.monthly_used},
            "identity_provider": identity.provider.value,
        }
