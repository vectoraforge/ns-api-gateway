"""Which of the locked grant rows one subscription write is entitled to end, over a stub session.

The writer receives more rows than it may change, so each case asserts what it did to each row.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.errors import MultipleEffectiveGrantsError
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    SubscriptionStatus,
)

PAID_TIER_ID = "paid"
FREE_TIER_ID = "free"

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
TERM_END = NOW + timedelta(days=30)

DESTINATION = uuid7()
OLD_OWNER = uuid7()
SUBSCRIPTION_A = uuid7()
SUBSCRIPTION_B = uuid7()


class _StubSession:
    """Collects what the writer added and counts the flushes it asked for; nothing raises."""

    def __init__(self) -> None:
        self.added: list = []
        self.flushes = 0

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1


def _grant(*, user_id=DESTINATION, source=AccessGrantSource.subscription,
           subscription_id=SUBSCRIPTION_A, ends_at=TERM_END,
           tier_id=PAID_TIER_ID) -> AccessGrant:
    return AccessGrant(user_id=user_id,
                       tier_id=tier_id,
                       source=source,
                       subscription_id=subscription_id,
                       status=AccessGrantStatus.active,
                       starts_at=NOW - timedelta(days=1),
                       ends_at=ends_at,
                       created_at=NOW - timedelta(days=1),
                       updated_at=NOW - timedelta(days=1))


async def _write(session: _StubSession, marked_active: list[AccessGrant], *,
                 subscription_id=SUBSCRIPTION_B,
                 status=SubscriptionStatus.active) -> WriteOutcome:
    """Run the real writer for one term of `subscription_id` over the rows the caller locked."""
    return await SubscriptionsDB(session).write_subscription_grant(
        user_id=DESTINATION,
        subscription_id=subscription_id,
        status=status,
        marked_active=marked_active,
        tier_id=PAID_TIER_ID,
        starts_at=NOW,
        ends_at=TERM_END,
        evaluated_at=NOW)


@pytest.mark.asyncio
class TestASecondLiveSubscriptionIsNotSuperseded:
    """WR-43: expiring it would leave that subscription entitled with no grant row."""

    async def test_a_live_term_of_another_subscription_refuses_the_write(self):
        rival = _grant(subscription_id=SUBSCRIPTION_A)

        with pytest.raises(MultipleEffectiveGrantsError):
            await _write(_StubSession(), [rival])

    async def test_the_refused_write_leaves_the_other_term_active(self):
        session = _StubSession()
        rival = _grant(subscription_id=SUBSCRIPTION_A)

        with pytest.raises(MultipleEffectiveGrantsError):
            await _write(session, [rival])

        assert (rival.status, rival.ends_at) == (AccessGrantStatus.active, TERM_END)
        assert (session.added, session.flushes) == ([], 0)

    async def test_a_term_that_has_already_ended_is_superseded_as_before(self):
        """An ended term strands no entitlement, so the write takes it rather than refusing."""
        session = _StubSession()
        stale = _grant(subscription_id=SUBSCRIPTION_A, ends_at=NOW - timedelta(days=2))

        outcome = await _write(session, [stale])

        assert outcome is WriteOutcome.applied
        assert (stale.status, stale.ends_at) == (AccessGrantStatus.expired, NOW)

    async def test_a_free_grant_is_superseded_as_before_control(self):
        """The control: the supersession this write is entitled to make is untouched."""
        session = _StubSession()
        free = _grant(source=AccessGrantSource.anonymous_device_grant, subscription_id=None,
                      ends_at=None, tier_id=FREE_TIER_ID)

        outcome = await _write(session, [free])

        assert outcome is WriteOutcome.applied
        assert free.status is AccessGrantStatus.expired

    async def test_this_subscriptions_own_earlier_term_is_superseded_control(self):
        """The second control: a mid-term tier change still takes the expire-then-insert path."""
        session = _StubSession()
        own = _grant(subscription_id=SUBSCRIPTION_B, tier_id=FREE_TIER_ID)

        outcome = await _write(session, [own])

        assert outcome is WriteOutcome.applied
        assert own.status is AccessGrantStatus.expired

    async def test_the_old_owners_live_term_is_not_read_as_a_rival(self):
        """On a move the caller locks two accounts; only the destination's own rows can be rivals."""
        session = _StubSession()
        theirs = _grant(user_id=OLD_OWNER, subscription_id=SUBSCRIPTION_B)

        outcome = await _write(session, [theirs])

        assert outcome is WriteOutcome.applied
        assert theirs.status is AccessGrantStatus.expired

    async def test_a_status_outside_the_entitled_set_ends_its_own_term_only(self):
        """A withdrawal writes no term, so it has no slot to contend for and never refuses."""
        session = _StubSession()
        rival = _grant(subscription_id=SUBSCRIPTION_A)

        outcome = await _write(session, [rival], status=SubscriptionStatus.expired)

        assert outcome is WriteOutcome.replayed
        assert rival.status is AccessGrantStatus.active
