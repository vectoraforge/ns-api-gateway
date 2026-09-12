"""The `SubscriptionsDB` statements one delivery issues, over a stub session: the store clock and
the owner `upsert_subscription` writes, and the replay key `read_event` is keyed on. The
out-of-order guard reads `core.subscriptions.store_signed_at`, so what moves it is what it sees.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy.dialects import postgresql

from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.tables import PurchaseProvider, Subscription, SubscriptionStatus

PAID_TIER_ID = "paid"
EXTERNAL_ID = "original-transaction-under-test"
OWNER = uuid7()

T1 = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
T2 = T1 + timedelta(minutes=5)

NOTIFICATION_UUID = "notification-uuid-under-test"

LOCK_CLAUSE = " FOR UPDATE"


class _StubResult:

    def __init__(self, row, rowcount: int):
        self._row = row
        self.rowcount = rowcount

    def first(self):
        return self._row


class _StubSession:
    """Answers the reads `upsert_subscription` makes, keeps its statements, and counts its flush."""

    def __init__(self, stored: Subscription | None, claimed: bool = True):
        self._stored = stored
        self._claimed = claimed
        self.flushes = 0
        self.added: list = []
        self.statements: list = []

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._stored, 1 if self._claimed else 0)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1


def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))


def _bound(statement) -> list:
    """The values the statement carries, which the compiled text renders only as placeholders."""
    return list(statement.compile(dialect=postgresql.dialect()).params.values())


def _stored(store_signed_at: datetime | None, user_id: UUID | None = OWNER) -> Subscription:
    return Subscription(provider=PurchaseProvider.apple,
                        external_id=EXTERNAL_ID,
                        user_id=user_id,
                        tier_id=PAID_TIER_ID,
                        status=SubscriptionStatus.active,
                        store_signed_at=store_signed_at,
                        created_at=T1,
                        updated_at=T1)


async def _upsert(stored: Subscription, *, signed_at: datetime | None,
                  status: SubscriptionStatus = SubscriptionStatus.active,
                  tier_id: str = PAID_TIER_ID) -> tuple[Subscription, WriteOutcome]:
    """Run the real crud method over the stub session, with the stored row it should find."""
    return await SubscriptionsDB(_StubSession(stored)).upsert_subscription(
        provider=PurchaseProvider.apple,
        external_id=EXTERNAL_ID,
        user_id=OWNER,
        tier_id=tier_id,
        status=status,
        signed_at=signed_at,
        clock_read=stored.store_signed_at)


@pytest.mark.asyncio
class TestTheClockMovesWithoutAStateChange:
    """WR-40: a delivery carrying no change still carries a store clock the guard must see."""

    async def test_a_replayed_delivery_advances_the_stored_clock(self):
        stored = _stored(T1)

        row, outcome = await _upsert(stored, signed_at=T2)

        assert (outcome, row.store_signed_at) == (WriteOutcome.replayed, T2)

    async def test_a_replayed_delivery_is_still_reported_as_a_replay_control(self):
        """The control: only the clock moves, so the caller still learns nothing was recorded."""
        stored = _stored(T1)

        _, outcome = await _upsert(stored, signed_at=T2)

        assert outcome is WriteOutcome.replayed

    async def test_a_stored_row_with_no_clock_takes_the_one_the_delivery_carries(self):
        stored = _stored(None)

        row, _ = await _upsert(stored, signed_at=T2)

        assert row.store_signed_at == T2

    async def test_a_delivery_carrying_no_clock_clears_nothing(self):
        stored = _stored(T1)

        row, _ = await _upsert(stored, signed_at=None)

        assert row.store_signed_at == T1

    async def test_an_older_clock_never_moves_the_stored_one_back(self):
        """The service refuses this delivery first; the writer holds the same rule on its own."""
        stored = _stored(T2)

        row, _ = await _upsert(stored, signed_at=T1)

        assert row.store_signed_at == T2

    async def test_a_delivery_that_does_change_state_advances_it_too_control(self):
        """The control: the applied arm kept the behaviour the replay arm was missing."""
        stored = _stored(T1)

        row, outcome = await _upsert(stored, signed_at=T2, status=SubscriptionStatus.grace_period)

        assert (outcome, row.store_signed_at) == (WriteOutcome.applied, T2)


async def _adopt(*, claimed: bool) -> tuple[Subscription, WriteOutcome, _StubSession]:
    """Run the real crud method over an unowned stored row the delivery's token resolves an owner for."""
    session = _StubSession(_stored(T1, user_id=None), claimed=claimed)
    row, outcome = await SubscriptionsDB(session).upsert_subscription(
        provider=PurchaseProvider.apple,
        external_id=EXTERNAL_ID,
        user_id=OWNER,
        tier_id=PAID_TIER_ID,
        status=SubscriptionStatus.active,
        signed_at=T2,
        clock_read=T1)
    return row, outcome, session


@pytest.mark.asyncio
class TestAnUnownedRowIsTakenConditionally:
    """WR-31: `core.subscriptions` is never locked here, so the statement that attributes an unowned
    row must say so itself. An update keyed on the id alone overwrites the owner a restore settled
    in the window since the read, leaving that account's active grant pointing at another owner."""

    async def test_the_owner_write_carries_the_unowned_predicate(self):
        _, _, session = await _adopt(claimed=True)

        updates = [_compiled(statement) for statement in session.statements
                   if _compiled(statement).startswith("UPDATE")]
        assert updates and "user_id IS NOT DISTINCT FROM" in updates[0]

    async def test_the_taken_owner_reaches_the_caller_that_writes_the_grant(self):
        """The control: the statement wrote the column, and `ingest` reads this attribute to decide
        whether a subscription grant is written at all."""
        row, outcome, _ = await _adopt(claimed=True)

        assert (row.user_id, outcome) == (OWNER, WriteOutcome.applied)

    async def test_a_restore_that_took_the_row_first_is_a_lost_race(self):
        """Zero rows means the predicate no longer holds: the store resends and reads the settled owner."""
        row, outcome, session = await _adopt(claimed=False)

        assert outcome is WriteOutcome.lost_race
        assert (session.flushes, row.user_id) == (0, None)


async def _write_over(stored: Subscription, *, clock_read: datetime | None,
                      signed_at: datetime | None = T2,
                      status: SubscriptionStatus = SubscriptionStatus.grace_period,
                      claimed: bool = True) -> tuple[Subscription, WriteOutcome, _StubSession]:
    """Run the real crud method over an owned stored row, keeping the statements it issued."""
    session = _StubSession(stored, claimed=claimed)
    row, outcome = await SubscriptionsDB(session).upsert_subscription(
        provider=PurchaseProvider.apple,
        external_id=EXTERNAL_ID,
        user_id=OWNER,
        tier_id=PAID_TIER_ID,
        status=status,
        signed_at=signed_at,
        clock_read=clock_read)
    return row, outcome, session


@pytest.mark.asyncio
class TestTheCanonicalRowIsTakenOnTheClockItWasReadAt:
    """WR-10: this row is never locked and a buyer with no grant marked active takes no grant lock
    either, so an update keyed on the id alone let two deliveries of one lifecycle key be
    last-writer-wins -- and the older one could land last, moving the clock backwards."""

    async def test_the_write_is_conditional_on_the_clock_the_caller_read(self):
        _, _, session = await _write_over(_stored(T1), clock_read=T1)

        updates = [_compiled(statement) for statement in session.statements
                   if _compiled(statement).startswith("UPDATE")]
        assert updates and "store_signed_at IS NOT DISTINCT FROM" in updates[0]

    async def test_the_predicate_carries_the_clock_the_caller_named(self):
        """The predicate is not enough on its own: a second read of the row would compile the same."""
        _, _, session = await _write_over(_stored(T1), clock_read=T1)

        update = next(statement for statement in session.statements
                      if _compiled(statement).startswith("UPDATE"))
        assert T1 in _bound(update)

    async def test_it_takes_no_lock_of_its_own(self):
        """43 D-16: the write lock this statement holds is the whole mechanism, and `FOR UPDATE`
        here would be a lock tier the two writers do not share."""
        _, _, session = await _write_over(_stored(T1), clock_read=T1)

        update = next(statement for statement in session.statements
                      if _compiled(statement).startswith("UPDATE"))
        assert LOCK_CLAUSE not in _compiled(update)

    async def test_a_rival_that_moved_the_clock_first_is_a_lost_race(self):
        """Zero rows means the row no longer reads what the guard decided on: the store resends."""
        row, outcome, session = await _write_over(_stored(T1), clock_read=T1, claimed=False)

        assert outcome is WriteOutcome.lost_race
        assert (session.flushes, row.status) == (0, SubscriptionStatus.active)

    async def test_a_delivery_that_records_nothing_takes_the_row_at_all_control(self):
        """The control on the condition: a redelivery that writes nothing must not queue behind
        the row lock, or every replay would wait on whatever delivery is mid-flight."""
        _, outcome, session = await _write_over(_stored(T1), clock_read=T1, signed_at=T1,
                                                status=SubscriptionStatus.active)

        assert outcome is WriteOutcome.replayed
        assert [statement for statement in session.statements
                if _compiled(statement).startswith("UPDATE")] == []


@pytest.mark.asyncio
class TestTheReplayKeyIsApplesNotificationUuid:
    """`08-webhook-app-store.md`:44 keys the whole replay contract on the notification UUID, so a
    read keyed on anything coarser swallows redeliveries this route has never applied."""

    async def test_the_statement_is_keyed_on_the_uuid_column(self):
        """The column, not only the value: a predicate moved to `event_type` carries the same bind."""
        session = _StubSession(None)

        await SubscriptionsDB(session).read_event(NOTIFICATION_UUID)

        assert len(session.statements) == 1
        assert "audit.subscription_events.notification_uuid = " in _compiled(session.statements[0])

    async def test_the_key_it_carries_is_the_one_the_caller_named(self):
        """The predicate is not enough on its own: the compiled text renders its value as a placeholder."""
        session = _StubSession(None)

        await SubscriptionsDB(session).read_event(NOTIFICATION_UUID)

        assert _bound(session.statements[0]) == [NOTIFICATION_UUID]

    async def test_it_reads_the_event_table_and_takes_no_lock(self):
        """A lock here would hold every redelivery behind the grant locks the replay arm skips."""
        session = _StubSession(None)

        await SubscriptionsDB(session).read_event(NOTIFICATION_UUID)

        compiled = _compiled(session.statements[0])
        assert "audit.subscription_events" in compiled
        assert LOCK_CLAUSE not in compiled
