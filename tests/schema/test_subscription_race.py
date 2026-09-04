"""Simultaneous deliveries of one store notification, raced on two connections against real PostgreSQL."""
import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.errors import AppError, InternalError
from nativespeaker.api.services.subscriptions import SubscriptionsService
from schema.test_claim_race import _RacingSession, read, scalar
from schema.test_subscription_ingestion import PRODUCT_ID, _notification

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# The tier the migration seeds for a paid subscription, and the one this test's product map targets.
TIER_ID = "paid"

_A_MONTH = timedelta(days=30)

# Bounded so a partner that fails before its flush shows up as a failure rather than as a hung suite.
BARRIER_TIMEOUT_SECONDS = 20


@dataclass
class _Harness:
    engine: object
    factory: async_sessionmaker
    uuid_prefix: str
    external_id: str


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """A committing session factory plus this test's private store key and lifecycle key."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    private = uuid.uuid4().hex[:10]
    subject = _Harness(engine=engine,
                       factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                  expire_on_commit=False),
                       uuid_prefix=f"ns-subscription-race-{private}",
                       external_id=f"original-{private}")
    try:
        yield subject
    finally:
        try:
            await clean_up(subject)
        finally:
            await engine.dispose()


async def clean_up(harness: _Harness) -> None:
    """Child-first: the event rows, then the purchase rows, then the subscriptions they pointed at."""
    keys = {"events": f"{harness.uuid_prefix}%", "lifecycle": f"{harness.external_id}%"}
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("DELETE FROM audit.subscription_events WHERE notification_uuid LIKE :events"),
            keys)
        # Last: core.store_purchases and core.subscriptions are both keyed on the lifecycle pair.
        for statement in ("DELETE FROM core.store_purchases WHERE external_id LIKE :lifecycle",
                          "DELETE FROM core.subscriptions WHERE external_id LIKE :lifecycle"):
            await conn.execute(text(statement), keys)


class _RacedSession(_RacingSession):
    """The claim race's session, plus the SQLSTATE its violation carried."""

    def __init__(self, session, before_first_flush=None) -> None:
        super().__init__(session, before_first_flush)
        self.sqlstate: str | None = None

    async def flush(self, *args, **kwargs):
        try:
            return await super().flush(*args, **kwargs)
        except IntegrityError as violation:
            # The classification is the SQLSTATE alone; nothing here reads a message or an index.
            self.sqlstate = violation.orig.sqlstate
            raise


@dataclass
class _Attempt:
    """One delivery's notification and everything observable about what it did."""

    name: str
    notification: VerifiedNotification
    # What the call produced: nothing when it committed, or the rejection it raised.
    result: AppError | None = None
    events_seen_at_barrier: int | None = None
    sqlstate: str | None = None
    integrity_at_flush: bool = False
    integrity_at_commit: bool = False
    # Every write the writer emits goes through one of these, so zero means the attempt wrote nothing.
    flushes: int = 0


def role_of(attempt: _Attempt) -> str:
    """The bucket an attempt lands in, and the only observable that separates them: who lost at the flush."""
    return "lost_at_flush" if attempt.integrity_at_flush else "won"


def status_of(attempt: _Attempt) -> int:
    """The status the route would have answered: a completed ingestion is a 200."""
    return attempt.result.status if isinstance(attempt.result, AppError) else 200


def notification_for(harness: _Harness, *, store_key: str = "one") -> VerifiedNotification:
    """One verified, unattributed delivery on this test's private keys."""
    return _notification(external_id=harness.external_id,
                         token=None,
                         purchased_at=NOW - _A_MONTH,
                         expires_at=NOW + _A_MONTH,
                         notification_uuid=f"{harness.uuid_prefix}-{store_key}")


async def run_attempt(harness: _Harness, attempt: _Attempt, before_first_flush=None) -> _Attempt:
    """Drive the production ingestion once, on its own session and connection, as one request does."""
    async with harness.factory() as real_session:
        session = _RacedSession(real_session, before_first_flush)
        service = SubscriptionsService(db=session, evaluated_at=NOW,
                                       products={PRODUCT_ID: TIER_ID})
        try:
            await service.ingest(attempt.notification)
        except AppError as rejection:
            attempt.result = rejection
        attempt.sqlstate = session.sqlstate
        attempt.integrity_at_flush = session.integrity_at_flush
        attempt.integrity_at_commit = session.integrity_at_commit
        attempt.flushes = session.flushes
    return attempt


async def counts(harness: _Harness) -> tuple[int, ...]:
    """Committed row counts of the three tables one delivery writes, on this test's private keys."""
    rows = await read(
        harness,
        "SELECT (SELECT count(*) FROM core.subscriptions WHERE external_id LIKE :lifecycle), "
        "(SELECT count(*) FROM core.store_purchases WHERE external_id LIKE :lifecycle), "
        "(SELECT count(*) FROM audit.subscription_events WHERE notification_uuid LIKE :events)",
        {"lifecycle": f"{harness.external_id}%", "events": f"{harness.uuid_prefix}%"})
    return tuple(rows[0])


def barrier_for(harness: _Harness, attempt: _Attempt, mine: asyncio.Event, theirs: asyncio.Event):
    """Announce that this delivery has read the event table, then wait for its partner."""

    async def hold() -> None:
        attempt.events_seen_at_barrier = await scalar(
            harness,
            "SELECT count(*) FROM audit.subscription_events WHERE notification_uuid LIKE :events",
            {"events": f"{harness.uuid_prefix}%"})
        mine.set()
        await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)

    return hold


async def race(harness: _Harness, first: _Attempt, second: _Attempt) -> dict:
    """Release two deliveries together, each held until both have read the event table."""
    first_ready, second_ready = asyncio.Event(), asyncio.Event()
    await asyncio.gather(
        run_attempt(harness, first, barrier_for(harness, first, first_ready, second_ready)),
        run_attempt(harness, second, barrier_for(harness, second, second_ready, first_ready)))
    return {"attempts": (first, second),
            "by_role": {role_of(attempt): attempt for attempt in (first, second)}}


@pytest.mark.asyncio
class TestTwoDeliveriesOfOneStoreKeyCommitOnce:
    """D-20, D-23. The unique indexes arbitrate; the pre-write event read is the fast path, never the arbiter."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two deliveries of one notification_uuid, released together once both have read the event table."""
        return await race(harness,
                          _Attempt(name="first", notification=notification_for(harness)),
                          _Attempt(name="second", notification=notification_for(harness)))

    async def test_both_deliveries_read_the_event_table_before_either_wrote(self, raced):
        """The premise: without this the case could be a delivery and its replay, and everything below vacuous."""
        assert [attempt.events_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_exactly_one_delivery_lost_the_race(self, raced):
        assert set(raced["by_role"]) == {"won", "lost_at_flush"}

    async def test_exactly_one_row_exists_in_each_of_the_three_tables(self, harness, raced):
        """The loser wrote nothing: two rows would mean no arbitration, zero that both rolled back."""
        assert await counts(harness) == (1, 1, 1)

    async def test_the_winner_answered_two_hundred(self, raced):
        winner = raced["by_role"]["won"]
        assert status_of(winner) == 200
        assert winner.result is None

    async def test_the_loser_read_the_unique_violation_off_the_sqlstate(self, raced):
        """D-20, 42-07. The SQLSTATE is the whole classification; no index and no message is read."""
        loser = raced["by_role"]["lost_at_flush"]
        assert loser.sqlstate == "23505"

    async def test_the_loser_answers_the_generic_five_hundred_and_not_a_refusal(self, raced):
        """D-23. The exact class, not a subclass: a refusal leaf here would mean the wrong arm ran."""
        loser = raced["by_role"]["lost_at_flush"]
        assert status_of(loser) == 500
        assert type(loser.result) is InternalError

    async def test_the_losers_violation_arrived_at_the_flush_and_not_at_the_commit(self, raced):
        """The unique indexes fire per statement, so the violation arrives at the flush."""
        winner, loser = raced["by_role"]["won"], raced["by_role"]["lost_at_flush"]
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (True, False)
        assert (winner.integrity_at_flush, winner.integrity_at_commit) == (False, False)

    async def test_a_third_delivery_finds_the_event_row_and_writes_nothing(self, harness, raced):
        """D-20. Apple's retry schedule converges: the store's own key is recorded, so this one writes nothing."""
        third = await run_attempt(harness, _Attempt(name="third",
                                                    notification=notification_for(harness)))

        assert status_of(third) == 200
        assert third.flushes == 0
        assert await counts(harness) == (1, 1, 1)


@pytest.mark.asyncio
class TestTwoStoreKeysForOneLifecyclePairCommitOnce:
    """D-20. Two notification keys on one `(provider, external_id)` are arbitrated by a unique index too."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two deliveries carrying different store keys for one lifecycle pair, released together."""
        return await race(
            harness,
            _Attempt(name="first", notification=notification_for(harness, store_key="one")),
            _Attempt(name="second", notification=notification_for(harness, store_key="two")))

    async def test_both_deliveries_read_the_event_table_before_either_wrote(self, raced):
        """The premise: neither delivery could have found the other's event row, so both went on to write."""
        assert [attempt.events_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_exactly_one_delivery_lost_the_race(self, raced):
        assert set(raced["by_role"]) == {"won", "lost_at_flush"}

    async def test_exactly_one_row_exists_in_each_of_the_three_tables(self, harness, raced):
        """One purchase row for the lifecycle pair, whichever store key reached it first."""
        assert await counts(harness) == (1, 1, 1)

    async def test_the_loser_read_the_unique_violation_off_the_sqlstate(self, raced):
        loser = raced["by_role"]["lost_at_flush"]
        assert loser.sqlstate == "23505"
        assert type(loser.result) is InternalError
