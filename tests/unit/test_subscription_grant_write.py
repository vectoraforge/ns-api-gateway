"""Which of the locked grant rows one subscription write is entitled to end, over a stub session.

T-45-08-01 and T-45-08-02 at the unit level: the writer receives more rows than it may change.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
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
class TestTheDestinationLosesEverythingItHolds:
    """T-45-08-02: the `grant.user_id == user_id` clause keeps the destination's whole set, so
    `ix_access_grants_one_active_per_user` is satisfied by construction rather than by a caught 23505."""

    async def test_a_live_term_of_another_subscription_is_superseded_too(self):
        """One account holds one active grant, so a second store subscription's term ends here."""
        session = _StubSession()
        other = _grant(subscription_id=SUBSCRIPTION_A)

        outcome = await _write(session, [other])

        assert outcome is WriteOutcome.applied
        assert (other.status, other.ends_at) == (AccessGrantStatus.expired, NOW)

    async def test_a_free_grant_is_superseded_too(self):
        session = _StubSession()
        free = _grant(source=AccessGrantSource.anonymous_device_grant, subscription_id=None,
                      ends_at=None, tier_id=FREE_TIER_ID)

        outcome = await _write(session, [free])

        assert outcome is WriteOutcome.applied
        assert free.status is AccessGrantStatus.expired

    async def test_this_subscriptions_own_earlier_term_is_superseded(self):
        """A mid-term tier change takes the same expire-then-insert path as every other write."""
        session = _StubSession()
        own = _grant(subscription_id=SUBSCRIPTION_B, tier_id=FREE_TIER_ID)

        outcome = await _write(session, [own])

        assert outcome is WriteOutcome.applied
        assert own.status is AccessGrantStatus.expired

    async def test_the_new_term_is_inserted_with_its_usage_row_control(self):
        """The control: the supersessions above are followed by the insert, not by an empty write."""
        session = _StubSession()

        await _write(session, [_grant(subscription_id=SUBSCRIPTION_A)])

        inserted = [row for row in session.added if isinstance(row, AccessGrant)]
        assert len(inserted) == 1
        assert (inserted[0].subscription_id, inserted[0].ends_at) == (SUBSCRIPTION_B, TERM_END)


@pytest.mark.asyncio
class TestTheOldOwnerKeepsWhatThisWriteDoesNotName:
    """T-45-08-01: on a move the caller locks two accounts, and the source keeps every other row."""

    async def test_the_old_owners_term_for_the_moved_subscription_is_ended(self):
        session = _StubSession()
        moving = _grant(user_id=OLD_OWNER, subscription_id=SUBSCRIPTION_B)

        outcome = await _write(session, [moving])

        assert outcome is WriteOutcome.applied
        assert moving.status is AccessGrantStatus.expired

    async def test_the_old_owners_term_for_another_subscription_is_left_alone(self):
        """The proof named neither that subscription nor that account's other entitlement."""
        session = _StubSession()
        unrelated = _grant(user_id=OLD_OWNER, subscription_id=SUBSCRIPTION_A)

        outcome = await _write(session, [unrelated])

        assert outcome is WriteOutcome.applied
        assert (unrelated.status, unrelated.ends_at) == (AccessGrantStatus.active, TERM_END)


@pytest.mark.asyncio
class TestAWithdrawalEndsItsOwnTermOnly:
    """A status outside the entitled set writes no term, so it supersedes only its own rows."""

    async def test_another_subscriptions_term_survives_a_withdrawal(self):
        session = _StubSession()
        other = _grant(subscription_id=SUBSCRIPTION_A)

        outcome = await _write(session, [other], status=SubscriptionStatus.expired)

        assert outcome is WriteOutcome.replayed
        assert other.status is AccessGrantStatus.active

    async def test_its_own_term_is_revoked_where_the_store_withdrew_it_control(self):
        """The control: the withdrawal arm does end a row, so the case above is not a no-op."""
        session = _StubSession()
        own = _grant(subscription_id=SUBSCRIPTION_B)

        outcome = await _write(session, [own], status=SubscriptionStatus.revoked)

        assert outcome is WriteOutcome.applied
        assert own.status is AccessGrantStatus.revoked
