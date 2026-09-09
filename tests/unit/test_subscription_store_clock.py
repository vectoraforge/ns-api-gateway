"""The store clock `core.subscriptions.store_signed_at` carries, over a stub session.

The out-of-order guard compares against this column, so what moves it is what that guard can see.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.tables import PurchaseProvider, Subscription, SubscriptionStatus

PAID_TIER_ID = "paid"
EXTERNAL_ID = "original-transaction-under-test"
OWNER = uuid7()

T1 = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
T2 = T1 + timedelta(minutes=5)


class _StubResult:

    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _StubSession:
    """Answers the one read `upsert_subscription` makes and counts the flush it ends with."""

    def __init__(self, stored: Subscription | None):
        self._stored = stored
        self.flushes = 0
        self.added: list = []

    async def exec(self, statement):  # noqa: ARG002
        return _StubResult(self._stored)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1


def _stored(store_signed_at: datetime | None) -> Subscription:
    return Subscription(provider=PurchaseProvider.apple,
                        external_id=EXTERNAL_ID,
                        user_id=OWNER,
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
