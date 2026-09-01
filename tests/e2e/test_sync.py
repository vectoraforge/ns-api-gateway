"""What `/auth/sync` answers over the real stack: the entitlement it holds, and the two absent states."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import col, select

from nativespeaker.api.schemas.auth import EntitlementStatus, EntitlementType
from nativespeaker.api.tables import AccessTier

from .conftest import seed_grant

pytestmark = pytest.mark.e2e

# A grant seeded to have started well before the request and, where the case needs it, to have already closed.
_LONG_AGO = timedelta(days=60)
_A_DAY = timedelta(days=1)


async def _monthly_credits(factory, tier_id: str) -> int:
    """The seeded tier's allowance, read back through the test's own factory rather than assumed."""
    async with factory() as session:
        statement = select(AccessTier.monthly_credits).where(col(AccessTier.id) == tier_id)
        return (await session.exec(statement)).one()


def _absent_entitlement_body(identity, at: datetime) -> dict:
    """The whole body a caller holding no effective grant is answered with, all six fields plus the provider."""
    return {"entitlement": {"type": EntitlementType.none.value,
                            "status": EntitlementStatus.none.value,
                            "tier_id": None,
                            "monthly_credits": None,
                            "current_period": at.strftime("%Y-%m"),
                            "monthly_used": 0},
            "identity_provider": identity.provider.value}


async def _seed_lapsed_grant(factory, user_id, *, closed_for: timedelta = _A_DAY):
    """A grant whose window opened long ago and has since closed, with its usage row present."""
    now = datetime.now(UTC)
    # with_usage stays True: the grant must be absent because the predicate excludes it, not because a row is missing.
    return await seed_grant(factory, user_id=user_id,
                            starts_at=now - _LONG_AGO,
                            ends_at=now - closed_for)


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


@pytest.mark.asyncio(loop_scope="module")
class TestTwoAbsentEntitlementsAreIndistinguishable:
    """ROADMAP criterion 2: nothing on the wire separates a caller who never held a grant from one whose lapsed."""

    async def test_no_grant_and_a_lapsed_grant_return_the_same_body(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity

        no_grant = await async_client.post("/auth/sync")
        await _seed_lapsed_grant(_db_transaction, user.id)
        lapsed = await async_client.post("/auth/sync")

        assert (no_grant.status_code, lapsed.status_code) == (200, 200), lapsed.text
        # The two bodies against each other, not each against a literal: a shared drift would pass the weaker check.
        assert no_grant.json() == lapsed.json()

    async def test_the_body_they_share_is_the_no_grant_answer(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, identity = linked_firebase_identity
        await _seed_lapsed_grant(_db_transaction, user.id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert response.json() == _absent_entitlement_body(identity, datetime.now(UTC))

    async def test_the_lapsed_answer_names_neither_revoked_nor_expired(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await _seed_lapsed_grant(_db_transaction, user.id)

        response = await async_client.post("/auth/sync")

        # Which internal condition applies is the caller's to not know; the public status enum has no such member.
        assert "revoked" not in response.text
        assert "expired" not in response.text


@pytest.mark.asyncio(loop_scope="module")
class TestTheWindowIsWhyTheGrantIsAbsent:
    """The lapsed grant is excluded by the `ends_at` predicate, not by a seeding accident that would hide a bug."""

    async def test_a_grant_whose_window_closed_a_moment_ago_is_absent(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, identity = linked_firebase_identity
        # A live clock cannot be made to hit `ends_at` exactly; that boundary is proved deterministically
        # against the compiled statement in tests/unit/test_sync_resolver.py. Here a second suffices.
        await _seed_lapsed_grant(_db_transaction, user.id, closed_for=timedelta(seconds=1))

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert response.json() == _absent_entitlement_body(identity, datetime.now(UTC))

    async def test_an_open_ended_grant_that_has_started_is_present(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, identity = linked_firebase_identity
        now = datetime.now(UTC)
        grant, usage = await seed_grant(_db_transaction, user_id=user.id,
                                        starts_at=now - _A_DAY, ends_at=None)
        allowance = await _monthly_credits(_db_transaction, grant.tier_id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert response.json() == {
            "entitlement": {"type": grant.source.value,
                            "status": EntitlementStatus.active.value,
                            "tier_id": grant.tier_id,
                            "monthly_credits": allowance,
                            "current_period": now.strftime("%Y-%m"),
                            "monthly_used": usage.monthly_used},
            "identity_provider": identity.provider.value,
        }
