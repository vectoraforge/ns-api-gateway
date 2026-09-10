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

from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.errors import AppError, InternalError
from nativespeaker.api.services.subscriptions import SubscriptionsService
from nativespeaker.api.tables import PurchaseProvider
from schema.test_claim_race import _RacingSession, read, scalar
from schema.test_subscription_ingestion import _notification

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
    """The claim race's session, plus the SQLSTATE its violation carried and a write barrier."""

    def __init__(self, session, before_first_flush=None, before_first_write=None) -> None:
        super().__init__(session, before_first_flush)
        self.sqlstate: str | None = None
        self._before_first_write = before_first_write

    async def exec(self, statement, *args, **kwargs):
        """Hold at the first statement that writes; everything before it is what this attempt read."""
        if self._before_first_write is not None and not getattr(statement, "is_select", False):
            hook, self._before_first_write = self._before_first_write, None
            await hook()
        return await self._session.exec(statement, *args, **kwargs)

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
    # The committed store clock this delivery decided against, read at the write barrier below.
    clock_seen_at_barrier: datetime | None = None
    # Every write the writer emits goes through one of these, so zero means the attempt wrote nothing.
    flushes: int = 0


def role_of(attempt: _Attempt) -> str:
    """The bucket an attempt lands in, and the only observable that separates them: who lost at the flush."""
    return "lost_at_flush" if attempt.integrity_at_flush else "won"


def status_of(attempt: _Attempt) -> int:
    """The status the route would have answered: a completed ingestion is a 200."""
    return attempt.result.status if isinstance(attempt.result, AppError) else 200


def notification_for(harness: _Harness, *, store_key: str = "one", tier_id: str = TIER_ID,
                     provider: PurchaseProvider = PurchaseProvider.apple,
                     signed_at: datetime | None = None) -> VerifiedNotification:
    """One verified, unattributed delivery on this test's private keys."""
    # The key is this test's own, not the Google composite: its stability is the ingestion file's subject.
    return _notification(external_id=harness.external_id,
                         token=None,
                         tier_id=tier_id,
                         provider=provider,
                         purchased_at=NOW - _A_MONTH,
                         expires_at=NOW + _A_MONTH,
                         # Defaulted to the purchase instant by the builder, as every case above wants.
                         signed_at=signed_at,
                         notification_uuid=f"{harness.uuid_prefix}-{store_key}")


async def run_attempt(harness: _Harness, attempt: _Attempt, before_first_flush=None,
                      before_first_write=None) -> _Attempt:
    """Drive the production ingestion once, on its own session and connection, as one request does."""
    async with harness.factory() as real_session:
        session = _RacedSession(real_session, before_first_flush, before_first_write)
        service = SubscriptionsService(db=session, evaluated_at=NOW)
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


def google_notification_for(harness: _Harness, **placement) -> VerifiedNotification:
    """One verified, unattributed Google delivery: the lifecycle key is the purchase token itself."""
    return notification_for(harness, provider=PurchaseProvider.google_play, **placement)


@pytest.mark.asyncio
class TestTwoGoogleDeliveriesOfOnePurchaseTokenCommitOnce:
    """PLAYHOOK-01. Pub/Sub can push one RTDN twice at once; the unique indexes are the only arbiter."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two deliveries for one purchase token, released together once both have read the event table."""
        return await race(harness,
                          _Attempt(name="first", notification=google_notification_for(harness)),
                          _Attempt(name="second", notification=google_notification_for(harness)))

    async def test_both_deliveries_read_the_event_table_before_either_wrote(self, raced):
        """The premise: without this the case is a delivery and its replay, and everything below vacuous."""
        assert [attempt.events_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_exactly_one_delivery_lost_the_race(self, raced):
        assert set(raced["by_role"]) == {"won", "lost_at_flush"}

    async def test_exactly_one_row_exists_in_each_of_the_three_tables(self, harness, raced):
        """The loser wrote nothing: two rows would mean no arbitration, zero that both rolled back."""
        assert await counts(harness) == (1, 1, 1)

    async def test_the_winner_committed_and_answered_two_hundred(self, raced):
        winner = raced["by_role"]["won"]
        assert status_of(winner) == 200
        assert winner.result is None

    async def test_the_loser_read_the_unique_violation_off_the_sqlstate(self, raced):
        """D-20, 42-07. The SQLSTATE is the whole classification; no index and no message is read."""
        loser = raced["by_role"]["lost_at_flush"]
        assert loser.sqlstate == "23505"
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (True, False)

    async def test_the_loser_answers_the_five_hundred_that_makes_pubsub_redeliver(self, raced):
        """D-23. The exact class, not a subclass: Pub/Sub acknowledges the status and resends on a 5xx."""
        loser = raced["by_role"]["lost_at_flush"]
        assert status_of(loser) == 500
        assert type(loser.result) is InternalError

    async def test_the_redelivery_finds_the_event_row_and_writes_nothing(self, harness, raced):
        """What the loser's 500 buys: Pub/Sub's resend is a replay, and the replay read stops it."""
        resent = await run_attempt(harness, _Attempt(name="resent",
                                                     notification=google_notification_for(harness)))

        assert status_of(resent) == 200
        assert resent.flushes == 0
        assert await counts(harness) == (1, 1, 1)

    async def test_an_integrity_failure_that_is_not_a_unique_violation_still_surfaces_control(
            self, harness):
        """The control on the classification: 23505 alone is a lost race, and a 23503 must not be read as one."""
        attempt = _Attempt(name="unmapped",
                           notification=google_notification_for(harness, tier_id="tier_never_seeded"))

        with pytest.raises(IntegrityError) as violation:
            await run_attempt(harness, attempt)

        assert violation.value.orig.sqlstate == "23503"
        assert await counts(harness) == (0, 0, 0)


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


# The three clocks WR-10 is about: what the settled row already said, and the two deliveries that
# raced over it. Both are newer than the settled one, so the out-of-order guard passes for both.
CLOCK_SETTLED = NOW - timedelta(hours=2)
CLOCK_OLDER = NOW - timedelta(hours=1)
CLOCK_NEWER = NOW - timedelta(minutes=30)


async def seed_settled_lifecycle(harness: _Harness, *, store_signed_at: datetime) -> None:
    """Commit the canonical row and its purchase row, which is the state both unique indexes go quiet in."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("INSERT INTO core.subscriptions (id, user_id, provider, external_id, tier_id, "
                 "status, store_signed_at, created_at, updated_at) VALUES "
                 "(:id, NULL, 'google_play', :lifecycle, :tier, 'expired', :clock, :now, :now)"),
            {"id": uuid.uuid4(), "lifecycle": harness.external_id, "tier": TIER_ID,
             "clock": store_signed_at, "now": NOW})
        # The second row is what makes this a race and not an insert pair: with it recorded,
        # `insert_purchase` is skipped, so `UNIQUE (provider, external_id)` arbitrates nothing.
        await conn.execute(
            text("INSERT INTO core.store_purchases (id, provider, identity_value, external_id, "
                 "purchase_user_id, resolved_token_value, created_at) VALUES "
                 "(:id, 'google_play', :identity, :lifecycle, NULL, NULL, :now)"),
            {"id": uuid.uuid4(), "identity": str(uuid.uuid4()),
             "lifecycle": harness.external_id, "now": NOW})


async def settled_clock(harness: _Harness) -> datetime | None:
    """The store clock the canonical row carries now, read on a connection of its own."""
    return await scalar(harness,
                        "SELECT store_signed_at FROM core.subscriptions WHERE external_id = :key",
                        {"key": harness.external_id})


def clock_barrier(harness: _Harness, attempt: _Attempt, mine: asyncio.Event,
                  theirs: asyncio.Event):
    """Record the committed clock this delivery decided against, then wait for its partner."""

    async def hold() -> None:
        attempt.clock_seen_at_barrier = await settled_clock(harness)
        mine.set()
        await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)

    return hold


@pytest.mark.asyncio
class TestTwoDeliveriesCarryingDifferentStoreClocksCommitOnce:
    """WR-10. Newest-wins is decided by re-reading the canonical row, and that row is never locked:
    an unattributed subscription takes no grant lock at all, so nothing serialized the two writes
    and the older delivery could land last, moving the clock backwards over the newer state."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two deliveries of one purchase token, released once both have read and neither has written."""
        await seed_settled_lifecycle(harness, store_signed_at=CLOCK_SETTLED)
        older = _Attempt(name="older", notification=google_notification_for(
            harness, store_key="older", signed_at=CLOCK_OLDER))
        newer = _Attempt(name="newer", notification=google_notification_for(
            harness, store_key="newer", signed_at=CLOCK_NEWER))
        older_ready, newer_ready = asyncio.Event(), asyncio.Event()
        await asyncio.gather(
            run_attempt(harness, older,
                        before_first_write=clock_barrier(harness, older, older_ready,
                                                         newer_ready)),
            run_attempt(harness, newer,
                        before_first_write=clock_barrier(harness, newer, newer_ready,
                                                         older_ready)))
        return {"older": older, "newer": newer}

    async def test_both_deliveries_decided_against_the_settled_clock(self, raced):
        """The premise: neither saw the other's write, so the guard passed for both and both applied."""
        assert [raced["older"].clock_seen_at_barrier,
                raced["newer"].clock_seen_at_barrier] == [CLOCK_SETTLED, CLOCK_SETTLED]

    async def test_exactly_one_delivery_lost_the_race(self, raced):
        """Both committing is the defect: the row would then carry whichever wrote last."""
        assert sorted(status_of(attempt)
                      for attempt in (raced["older"], raced["newer"])) == [200, 500]

    async def test_the_loser_answers_the_five_hundred_that_makes_pubsub_redeliver(self, raced):
        loser = next(attempt for attempt in (raced["older"], raced["newer"])
                     if status_of(attempt) == 500)
        assert type(loser.result) is InternalError

    async def test_the_settled_clock_is_the_winners_and_never_the_last_writers(self, harness,
                                                                               raced):
        """The point of the whole guard: the clock this row carries is the one that won it."""
        winner = next(attempt for attempt in (raced["older"], raced["newer"])
                      if status_of(attempt) == 200)
        assert await settled_clock(harness) == winner.notification.signed_at

    async def test_only_the_winners_event_row_was_recorded(self, harness, raced):
        """The loser rolled back whole: its event row is not left behind to block the redelivery."""
        assert await counts(harness) == (1, 1, 1)
