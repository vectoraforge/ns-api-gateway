"""What `upsert_subscription` writes over a stub session: the store clock, and the owner.
The out-of-order guard compares against `core.subscriptions.store_signed_at`, so what moves that
column is what that guard can see; the owner is written by a statement carrying its own rule.
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


class _StubResult:

    def __init__(self, row, rowcount: int):
        self._row = row
        # The conditional owner update answers with a row count and nothing else.
        self.rowcount = rowcount

    def first(self):
        return self._row


class _StubSession:
    """Answers the reads `upsert_subscription` makes, keeps its statements, and counts its flush."""

    def __init__(self, stored: Subscription | None, claimed: bool = True):
        self._stored = stored
        # What the conditional owner update finds: one row, or none because a restore won it.
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
        evaluated_at=T2)


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
        evaluated_at=T2)
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
        # Nothing after the refused claim ran: no flush, and the owner is left as it was read.
        assert (session.flushes, row.user_id) == (0, None)
