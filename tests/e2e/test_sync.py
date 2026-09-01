"""What `/auth/sync` answers over the real stack: the entitlement it holds, and the two absent states."""
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlmodel import col, select
from unit.conftest import make_token

from nativespeaker.api.errors import PreAuthIdentityNotAllowed
from nativespeaker.api.schemas.auth import EntitlementStatus, EntitlementType
from nativespeaker.api.tables import AccessTier, ExternalIdentity, IdentityProvider

from .conftest import seed_grant, seed_identity

pytestmark = pytest.mark.e2e

# A grant seeded to have started well before the request and, where the case needs it, to have already closed.
_LONG_AGO = timedelta(days=60)
_A_DAY = timedelta(days=1)

# A period that is never the current one, carrying a non-zero count: a rollover written here would be visible.
_STALE_PERIOD = "2020-01"
_STALE_USED = 17
_CURRENT_USED = 5

# Never seeded anywhere, so a token naming it verifies and still resolves to no identity row.
_UNLINKED_SUBJECT = "sync-unlinked-subject"


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


# `SELECT *`, not the mapped columns: access_grants carries four GENERATED ALWAYS columns the ORM leaves unmapped.
_GRANT_ROWS = text("SELECT * FROM core.access_grants WHERE user_id = :user_id ORDER BY id")
_USAGE_ROWS = text("SELECT u.* FROM core.user_monthly_usage u"
                   " JOIN core.access_grants g ON g.id = u.grant_id"
                   " WHERE g.user_id = :user_id ORDER BY u.grant_id")
_USER_ROW = text("SELECT * FROM core.users WHERE id = :user_id")
_TABLE_COUNTS = text("SELECT (SELECT count(*) FROM core.access_grants),"
                     " (SELECT count(*) FROM core.user_monthly_usage),"
                     " (SELECT count(*) FROM core.users)")


async def _entitlement_snapshot(factory, user_id) -> dict:
    """Every column of the caller's grant, usage and user rows, plus the three whole-table counts."""
    async with factory() as session:
        params = {"user_id": user_id}
        return {"grants": [tuple(r) for r in (await session.execute(_GRANT_ROWS, params)).all()],
                "usage": [tuple(r) for r in (await session.execute(_USAGE_ROWS, params)).all()],
                "user": [tuple(r) for r in (await session.execute(_USER_ROW, params)).all()],
                "counts": tuple((await session.execute(_TABLE_COUNTS)).one())}


async def _stored_provider(factory, issuer: str, subject: str):
    """The provider value actually on the row, read back rather than taken from the fixture's argument."""
    async with factory() as session:
        statement = select(ExternalIdentity.provider).where(col(ExternalIdentity.issuer) == issuer,
                                                            col(ExternalIdentity.subject) == subject)
        return (await session.exec(statement)).one()


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


@pytest.mark.asyncio(loop_scope="module")
class TestTheRequestChangesNothing:
    """ROADMAP criterion 3: the caller's rows and the three table counts are identical before and after a sync."""

    async def test_a_current_period_grant_is_left_untouched(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id, monthly_used=_CURRENT_USED)
        before = await _entitlement_snapshot(_db_transaction, user.id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert await _entitlement_snapshot(_db_transaction, user.id) == before

    async def test_a_stale_period_grant_is_left_untouched(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        # The branch quota resolves by writing: an assignment here would ride `get_db`'s commit-on-exit to disk.
        await seed_grant(_db_transaction, user_id=user.id,
                         monthly_period=_STALE_PERIOD, monthly_used=_STALE_USED)
        before = await _entitlement_snapshot(_db_transaction, user.id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        # Reported as zero for the current period, while the row still says exactly what it said.
        assert response.json()["entitlement"]["monthly_used"] == 0
        assert await _entitlement_snapshot(_db_transaction, user.id) == before

    async def test_no_grant_at_all_leaves_the_tables_untouched(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        before = await _entitlement_snapshot(_db_transaction, user.id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert await _entitlement_snapshot(_db_transaction, user.id) == before

    async def test_a_repeated_request_answers_the_same_body_over_the_same_rows(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id,
                         monthly_period=_STALE_PERIOD, monthly_used=_STALE_USED)
        before = await _entitlement_snapshot(_db_transaction, user.id)

        # What a client reconciling after a lost response actually does; the stale row makes it the sharp case.
        first = await async_client.post("/auth/sync")
        second = await async_client.post("/auth/sync")

        assert (first.status_code, second.status_code) == (200, 200), second.text
        assert first.json() == second.json()
        assert await _entitlement_snapshot(_db_transaction, user.id) == before


@pytest_asyncio.fixture(loop_scope="module")
async def apple_linked_identity(_db_transaction, _app_config, test_user_id):
    """The real credential's identity pair, stored with a provider the happy-path fixture never seeds."""
    return await seed_identity(_db_transaction,
                               issuer=_app_config.jwt.issuer,
                               subject=test_user_id,
                               provider=IdentityProvider.apple)


@pytest.mark.asyncio(loop_scope="module")
class TestTheProviderComesFromTheStoredColumn:
    """`identity_provider` is the value in `core.external_identities.provider`, not a default or a token claim."""

    async def test_a_non_google_caller_reports_its_stored_provider(
            self, async_client, _db_transaction, _app_config, test_user_id, apple_linked_identity):
        stored = await _stored_provider(_db_transaction, _app_config.jwt.issuer, test_user_id)
        # The happy-path fixture seeds google; a row equal to it would leave the case proving nothing.
        assert stored != IdentityProvider.google

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert response.json()["identity_provider"] == stored


@pytest.mark.asyncio(loop_scope="module")
class TestTheRouteInheritsTheBarriersRejections:
    """Both rejections come from the existing dependencies; the route adds no handling and no exemption."""

    async def test_a_caller_with_no_credential_is_rejected(self, _app_lifespan):
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/auth/sync")

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_a_verified_but_unlinked_caller_is_rejected(self, _app_lifespan, stub_verifier):
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/auth/sync", headers={"Authorization": f"Bearer {make_token(sub=_UNLINKED_SUBJECT)}"})

        # Status and code read off the error class rather than guessed, so a renamed code fails here first.
        assert response.status_code == PreAuthIdentityNotAllowed.status
        assert response.json() == {"code": PreAuthIdentityNotAllowed.code}


@pytest.mark.asyncio(loop_scope="module")
class TestTheFailClosedFiveHundred:
    """An effective grant whose usage row is missing answers an opaque 500, never the zero a brief would report."""

    async def test_a_grant_with_no_usage_row_is_an_opaque_500(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        # with_usage=False is the case the fixture's own comment says the parameter exists for.
        await seed_grant(_db_transaction, user_id=user.id, with_usage=False)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 500
        # The whole body as a literal: an added detail field would name which condition tripped.
        assert response.json() == {"code": "internal_error"}
