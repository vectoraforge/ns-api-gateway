"""Sync's no-lock claim, observed live rather than inferred from compiled SQL. Closes WINDOWS.md entry 9."""
# Why not e2e: tests/e2e/conftest.py binds every session to one connection inside an uncommitted
# transaction, so a second connection sees no seeded rows and every such case passes vacuously.
# Committed rows and two real connections are the only arrangement in which a lock can contend.
import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.crud import GrantsDB
from nativespeaker.api.schemas.auth import EntitlementStatus
from nativespeaker.api.services.quota import QuotaService
from nativespeaker.api.services.sync import SyncService
from schema.helpers import insert_grant, insert_tier, insert_usage, insert_user

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

# Short on purpose: the claim is that sync never waits, so any wait must surface as a failure and not a pause.
_NO_WAIT = "500ms"

# Bounded so a "lock-free" path that is really a hang fails this test instead of hanging the suite.
_DEADLINE_SECONDS = 10

MONTHLY_CREDITS = 100

# Non-zero, so a read that silently rolled the period over is distinguishable from a correct one.
SEEDED_USED = 7

# Enough passes that a race landing on only one side of the commit is not mistaken for determinism.
ROUNDS = 12


@dataclass(frozen=True)
class _Harness:
    engine: object
    factory: async_sessionmaker
    user_id: uuid.UUID
    tier_id: str
    grant_id: uuid.UUID
    evaluated_at: datetime


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """Committed rows and a committing session factory; uncommitted rows would be invisible to the second connection."""
    setup = await asyncpg.connect(_schema_db_uri)
    try:
        # No transaction block: asyncpg autocommits each statement, which is the commit these rows need.
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup, monthly_credits=MONTHLY_CREDITS)
        grant_id = await insert_grant(setup, user_id=user_id, tier_id=tier_id, source="manual")
        # Captured after the insert so it is at or past the grant's defaulted starts_at, or the predicate excludes it.
        evaluated_at = datetime.now(UTC)
        # The seeded period must match the evaluated instant, or every read reports zero used instead of the count.
        await insert_usage(setup, grant_id=grant_id,
                           monthly_period=evaluated_at.strftime("%Y-%m"),
                           monthly_used=SEEDED_USED)
    finally:
        await setup.close()

    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    try:
        yield _Harness(engine=engine,
                       factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                  expire_on_commit=False),
                       user_id=user_id, tier_id=tier_id, grant_id=grant_id,
                       evaluated_at=evaluated_at)
    finally:
        await engine.dispose()
        cleanup = await asyncpg.connect(_schema_db_uri)
        try:
            await cleanup.execute("DELETE FROM core.access_grants WHERE user_id = $1", user_id)
            await cleanup.execute("DELETE FROM core.users WHERE id = $1", user_id)
            await cleanup.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)
        finally:
            await cleanup.close()


async def stored_usage(harness: _Harness) -> int:
    """The committed count, read on a connection of its own -- never one a case under test is using."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        return (await conn.execute(
            text("SELECT monthly_used FROM core.user_monthly_usage WHERE grant_id = :grant_id"),
            {"grant_id": harness.grant_id})).scalar_one()


async def sync_with_a_bounded_lock_wait(harness: _Harness):
    """One real `SyncService.read_entitlement` whose transaction refuses to wait for a lock."""
    # SET LOCAL lock_timeout is the instrument: a statement taking no lock is unaffected by it, so
    # surviving it IS the assertion. Were any of sync's reads to take FOR UPDATE this raises instead.
    async with harness.factory() as session:
        await (await session.connection()).execute(text(f"SET LOCAL lock_timeout = '{_NO_WAIT}'"))
        return await SyncService(session, harness.evaluated_at).read_entitlement(harness.user_id)


@pytest.mark.asyncio
class TestSyncWaitsOnNoLock:
    """The read path holds no lock and is stopped by none."""

    async def test_sync_reads_through_the_locks_a_charge_is_holding(self, harness):
        """A charge holds both rows FOR UPDATE, uncommitted; sync must still answer, with the pre-charge state."""
        async with harness.factory() as holder:
            grants_db = GrantsDB(holder)

            held = await grants_db.lock_effective_grants(harness.user_id, harness.evaluated_at)
            assert [grant.id for grant in held] == [harness.grant_id], \
                "control: the holder must really hold the grant row, or sync has nothing to read through"
            assert await grants_db.lock_usage(harness.grant_id) is not None, \
                "control: the holder must also hold the usage row, second in the lock order"

            entitlement = await asyncio.wait_for(sync_with_a_bounded_lock_wait(harness),
                                                 _DEADLINE_SECONDS)
            await holder.rollback()

        assert entitlement.status is EntitlementStatus.active
        assert entitlement.tier_id == harness.tier_id
        assert entitlement.monthly_credits == MONTHLY_CREDITS
        # The holder's work is uncommitted, and READ COMMITTED cannot see it: the pre-charge count is the only answer.
        assert entitlement.monthly_used == SEEDED_USED

    async def test_a_charge_is_not_blocked_by_an_open_sync_read(self, harness):
        """The converse, and the one that matters in production: a read taking no lock cannot stall the writer."""
        async with harness.factory() as reader:
            await (await reader.connection()).execute(text(f"SET LOCAL lock_timeout = '{_NO_WAIT}'"))
            await SyncService(reader, harness.evaluated_at).read_entitlement(harness.user_id)

            # The reader's transaction stays open across the charge: that a charge still commits is the point.
            await asyncio.wait_for(
                QuotaService(harness.factory).charge(user_id=harness.user_id,
                                                     evaluated_at=harness.evaluated_at),
                _DEADLINE_SECONDS)
            await reader.rollback()

        assert await stored_usage(harness) == SEEDED_USED + 1


@pytest.mark.asyncio
class TestSyncNeverReportsAPairingThatNeverExisted:
    """Lock-free is not enough: the answer must also be one a caller could legitimately have seen."""

    async def test_a_racing_sync_lands_on_one_side_of_the_commit_or_the_other(self, harness):
        """Sync and a committing charge, raced repeatedly on separate connections."""
        # The charge moves the count and nothing else, so the skew WR-06 accepts (tier and usage row
        # from different snapshots) cannot yield a wrong allowance here. The count is the pre- or the
        # post-charge value; anything else is a partial read straddling the commit.
        for round_number in range(ROUNDS):
            entitlement, _ = await asyncio.wait_for(
                asyncio.gather(
                    sync_with_a_bounded_lock_wait(harness),
                    QuotaService(harness.factory).charge(user_id=harness.user_id,
                                                         evaluated_at=harness.evaluated_at)),
                _DEADLINE_SECONDS)

            assert entitlement.status is EntitlementStatus.active
            assert entitlement.tier_id == harness.tier_id, \
                f"round {round_number}: the tier changed under a charge that never touches it"
            assert entitlement.monthly_credits == MONTHLY_CREDITS, \
                f"round {round_number}: the allowance no longer belongs to the reported tier"

            before = SEEDED_USED + round_number
            assert entitlement.monthly_used in (before, before + 1), (
                f"round {round_number}: {entitlement.monthly_used} is neither the pre-charge count "
                f"{before} nor the post-charge count {before + 1} -- a partial read straddling the commit")

        assert await stored_usage(harness) == SEEDED_USED + ROUNDS, \
            "every raced charge must have committed exactly once"
