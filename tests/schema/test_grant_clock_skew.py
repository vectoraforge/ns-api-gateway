"""The written `starts_at` comes from the database clock, against real PostgreSQL.
The effective-grant predicate compares `starts_at` with `clock_timestamp()`, so a start stamped from
any other clock can read back as not yet effective for the width of the difference."""
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.crud.grants import ActivationOutcome, GrantsDB, _effective_grants_statement
from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.tables import AccessGrantSource, SubscriptionStatus
from nativespeaker.api.tables.identities import NativeClaimProvider
from schema.helpers import insert_subscription, insert_tier, insert_user

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

SEEDED_AT = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _sessions(schema_db_uri: str):
    engine = create_async_engine(schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    return engine, async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)


async def _clean(schema_db_uri: str, user_id: uuid.UUID, issuer: str, tier_id: str) -> None:
    cleanup = await asyncpg.connect(schema_db_uri)
    try:
        await cleanup.execute("DELETE FROM core.user_monthly_usage WHERE grant_id IN "
                              "(SELECT id FROM core.access_grants WHERE user_id = $1)", user_id)
        await cleanup.execute("DELETE FROM core.access_grants WHERE user_id = $1", user_id)
        await cleanup.execute("DELETE FROM core.external_identities WHERE issuer = $1", issuer)
        await cleanup.execute("DELETE FROM core.subscriptions WHERE user_id = $1", user_id)
        await cleanup.execute("DELETE FROM core.users WHERE id = $1", user_id)
        await cleanup.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)
    finally:
        await cleanup.close()


@pytest_asyncio.fixture
async def anonymous_claim(_schema_db_uri):
    """Drive the anonymous writer once, bracketing it with the database's own clock."""
    subject = f"clock-skew-{uuid.uuid4().hex[:10]}"
    issuer = f"ns-clock-skew-{uuid.uuid4().hex[:10]}"

    setup = await asyncpg.connect(_schema_db_uri)
    try:
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        await setup.execute(
            "INSERT INTO core.external_identities "
            "(id, user_id, issuer, subject, provider, identity_state, created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, 'anonymous', 'active', $5, $5)",
            uuid.uuid4(), user_id, issuer, subject, SEEDED_AT)
    finally:
        await setup.close()

    engine, factory = _sessions(_schema_db_uri)
    try:
        async with factory() as session:
            before = await session.scalar(select(func.clock_timestamp()))
            outcome, _ = await GrantsDB(session).activate_anonymous_device_grant(
                user_id=user_id, issuer=issuer, subject=subject,
                claim_platform=NativeClaimProvider.ios_devicecheck, tier_id=tier_id)
            after = await session.scalar(select(func.clock_timestamp()))
            await session.commit()
            effective = list((await session.exec(_effective_grants_statement(user_id))).all())
        yield {"outcome": outcome, "before": before, "after": after, "effective": effective}
    finally:
        await engine.dispose()
        await _clean(_schema_db_uri, user_id, issuer, tier_id)


@pytest_asyncio.fixture
async def future_term(_schema_db_uri):
    """Drive the subscription writer with a `starts_at` one hour past the database clock."""
    issuer = f"ns-clock-clamp-{uuid.uuid4().hex[:10]}"

    setup = await asyncpg.connect(_schema_db_uri)
    try:
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        subscription_id = await insert_subscription(setup, external_id=f"clamp-{uuid.uuid4().hex}",
                                                    tier_id=tier_id, user_id=user_id)
    finally:
        await setup.close()

    engine, factory = _sessions(_schema_db_uri)
    try:
        async with factory() as session:
            clock = await session.scalar(select(func.clock_timestamp()))
            outcome = await SubscriptionsDB(session).write_subscription_grant(
                user_id=user_id, subscription_id=subscription_id,
                status=SubscriptionStatus.active, marked_active=[], tier_id=tier_id,
                starts_at=clock + timedelta(hours=1), ends_at=clock + timedelta(days=30),
                may_reactivate=False)
            after = await session.scalar(select(func.clock_timestamp()))
            await session.commit()
            effective = list((await session.exec(_effective_grants_statement(user_id))).all())
        yield {"outcome": outcome, "clock": clock, "after": after, "effective": effective}
    finally:
        await engine.dispose()
        await _clean(_schema_db_uri, user_id, issuer, tier_id)


class TestTheAnonymousWriterStampsFromTheDatabaseClock:
    async def test_it_activated_control(self, anonymous_claim):
        assert anonymous_claim["outcome"] is ActivationOutcome.activated

    async def test_the_written_start_lies_between_two_database_clock_reads(self, anonymous_claim):
        written = anonymous_claim["effective"] or []
        assert len(written) == 1
        assert anonymous_claim["before"] <= written[0].starts_at <= anonymous_claim["after"]

    async def test_the_committed_grant_reads_back_as_effective(self, anonymous_claim):
        assert [grant.source for grant in anonymous_claim["effective"]] == [
            AccessGrantSource.anonymous_device_grant]


class TestAStartAheadOfTheDatabaseClockIsClamped:
    async def test_it_applied_control(self, future_term):
        assert future_term["outcome"] is WriteOutcome.applied

    async def test_the_committed_grant_reads_back_as_effective(self, future_term):
        assert len(future_term["effective"]) == 1

    async def test_the_written_start_is_the_database_clock_and_not_the_hour_ahead(self, future_term):
        written = future_term["effective"][0].starts_at
        assert future_term["clock"] <= written <= future_term["after"]
