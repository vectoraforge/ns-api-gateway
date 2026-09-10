"""Which of the locked grant rows one subscription write is entitled to end, over a stub session.

T-45-08-01 and T-45-08-02 at the unit level: the writer receives more rows than it may change.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.errors import MissingUsageRowError
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    SubscriptionStatus,
    UserMonthlyUsage,
)

PAID_TIER_ID = "paid"
FREE_TIER_ID = "free"

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
TERM_END = NOW + timedelta(days=30)

# The month `NOW` falls in, and the one before it: the rule is the calendar month, not the term.
THIS_MONTH = "2026-09"
LAST_MONTH = "2026-08"

DESTINATION = uuid7()
OLD_OWNER = uuid7()
SUBSCRIPTION_A = uuid7()
SUBSCRIPTION_B = uuid7()


class _StubResult:
    """One row or none, on the shape `session.exec(...)` answers with."""

    def __init__(self, row) -> None:
        self._row = row

    def first(self):
        return self._row


class _StubSession:
    """Collects what the writer added, answers the grant and usage reads, and counts each of them."""

    def __init__(self, usage: UserMonthlyUsage | None = None,
                 prior: AccessGrant | None = None) -> None:
        self.added: list = []
        self.flushes = 0
        self.usage_reads = 0
        self.grant_reads = 0
        # The usage row `lock_grants` already locked, read back to carry the month's count across.
        self._usage = usage
        # A grant this subscription already had, at any status, which is the lapse guard's question.
        self._prior = prior

    async def exec(self, statement):
        if statement.column_descriptions[0]["entity"] is AccessGrant:
            self.grant_reads += 1
            return _StubResult(self._prior)
        self.usage_reads += 1
        return _StubResult(self._usage)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1


class _WarningSpy:
    """Stands in for the writer's whole `logger`; only the level this loss is recorded at exists."""

    def __init__(self, records: list[dict]) -> None:
        self.records = records

    def warning(self, event, **fields) -> None:
        self.records.append({"event": event} | fields)


def _writer_warnings(monkeypatch) -> list[dict]:
    """The whole `logger` name, never its level attributes: structlog's lazy proxy builds those on
    demand, so monkeypatch's undo would freeze one onto the proxy for the rest of the session."""
    records: list[dict] = []
    monkeypatch.setattr("nativespeaker.api.crud.subscriptions.logger", _WarningSpy(records))
    return records


def _usage(grant: AccessGrant, *, monthly_period: str, monthly_used: int) -> UserMonthlyUsage:
    return UserMonthlyUsage(grant_id=grant.id,
                            monthly_period=monthly_period,
                            monthly_used=monthly_used,
                            created_at=NOW,
                            updated_at=NOW)


def _minted(session: _StubSession) -> list[int]:
    """The count on every usage row the writer inserted, which is the allowance it handed out."""
    return [row.monthly_used for row in session.added if isinstance(row, UserMonthlyUsage)]


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
                 may_reactivate=False,
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
        may_reactivate=may_reactivate,
        evaluated_at=NOW)


@pytest.mark.asyncio
class TestTheDestinationLosesEverythingItHolds:
    """T-45-08-02: the `grant.user_id == user_id` clause keeps the destination's whole set, so
    `ix_access_grants_one_active_per_user` is satisfied by construction rather than by a caught 23505."""

    async def test_a_live_term_of_another_subscription_is_superseded_too(self):
        """One account holds one active grant, so a second store subscription's term ends here."""
        other = _grant(subscription_id=SUBSCRIPTION_A)
        session = _StubSession(_usage(other, monthly_period=THIS_MONTH, monthly_used=0))

        outcome = await _write(session, [other])

        assert outcome is WriteOutcome.applied
        assert (other.status, other.ends_at) == (AccessGrantStatus.expired, NOW)

    async def test_a_free_grant_is_superseded_too(self):
        free = _grant(source=AccessGrantSource.anonymous_device_grant, subscription_id=None,
                      ends_at=None, tier_id=FREE_TIER_ID)
        session = _StubSession(_usage(free, monthly_period=THIS_MONTH, monthly_used=0))

        outcome = await _write(session, [free])

        assert outcome is WriteOutcome.applied
        assert free.status is AccessGrantStatus.expired

    async def test_this_subscriptions_own_earlier_term_is_superseded(self):
        """A mid-term tier change takes the same expire-then-insert path as every other write."""
        own = _grant(subscription_id=SUBSCRIPTION_B, tier_id=FREE_TIER_ID)
        session = _StubSession(_usage(own, monthly_period=THIS_MONTH, monthly_used=0))

        outcome = await _write(session, [own])

        assert outcome is WriteOutcome.applied
        assert own.status is AccessGrantStatus.expired

    async def test_the_new_term_is_inserted_with_its_usage_row_control(self):
        """The control: the supersessions above are followed by the insert, not by an empty write."""
        other = _grant(subscription_id=SUBSCRIPTION_A)
        session = _StubSession(_usage(other, monthly_period=THIS_MONTH, monthly_used=0))

        await _write(session, [other])

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


@pytest.mark.asyncio
class TestTheMonthsCountSurvivesATermChangeInsideIt:
    """WR-48: the allowance is a UTC calendar month's, so a supersession inside one month carries
    its count. A fresh zero gave a grace bounce two allowances and a mid-term tier change a third,
    and `10-restore-subscription.md:80` forbids a fresh counter for the same paid entitlement."""

    async def test_a_term_change_inside_the_month_carries_the_count(self):
        own = _grant(subscription_id=SUBSCRIPTION_B, ends_at=TERM_END + timedelta(days=1))
        session = _StubSession(_usage(own, monthly_period=THIS_MONTH, monthly_used=45))

        await _write(session, [own])

        assert _minted(session) == [45]

    async def test_a_free_grants_count_is_never_carried_into_the_paid_counter(self):
        """`08-webhook-app-store.md`:38 seeds the paid counter at zero, so the month a buyer spent
        on the free tier is not a debt their first paid term inherits."""
        free = _grant(source=AccessGrantSource.anonymous_device_grant, subscription_id=None,
                      ends_at=None, tier_id=FREE_TIER_ID)
        session = _StubSession(_usage(free, monthly_period=THIS_MONTH, monthly_used=45))

        await _write(session, [free])

        assert _minted(session) == [0]

    async def test_a_supersession_from_an_earlier_month_still_starts_at_zero_control(self):
        """The control: the rule is the calendar month, so a renewal across the boundary is fresh
        and 43-04's ratified `its fresh usage row` still describes what a renewal does."""
        own = _grant(subscription_id=SUBSCRIPTION_B, ends_at=TERM_END + timedelta(days=1))
        session = _StubSession(_usage(own, monthly_period=LAST_MONTH, monthly_used=45))

        await _write(session, [own])

        assert _minted(session) == [0]

    async def test_the_old_owners_count_is_never_inherited_on_a_move(self):
        """On a move `superseded` also holds the old owner's row, and the month they spent is not
        this account's to inherit -- so that row is not even read."""
        theirs = _grant(user_id=OLD_OWNER, subscription_id=SUBSCRIPTION_B)
        session = _StubSession(_usage(theirs, monthly_period=THIS_MONTH, monthly_used=45))

        await _write(session, [theirs])

        assert (_minted(session), session.usage_reads) == ([0], 0)

    async def test_a_superseded_grant_with_no_usage_row_fails_closed(self):
        """CR-29: SHARED-INVARIANTS refuses a missing usage row for an existing grant, and reading
        it as zero used minted this account a monthly allowance it never bought."""
        own = _grant(subscription_id=SUBSCRIPTION_B, ends_at=TERM_END + timedelta(days=1))
        session = _StubSession(None)

        with pytest.raises(MissingUsageRowError) as failure:
            await _write(session, [own])

        assert failure.value.grant_id == own.id

    async def test_the_refusal_inserts_no_grant_and_no_counter(self):
        """The insert is what the free allowance would have ridden in on, so nothing is added."""
        own = _grant(subscription_id=SUBSCRIPTION_B, ends_at=TERM_END + timedelta(days=1))
        session = _StubSession(None)

        with pytest.raises(MissingUsageRowError):
            await _write(session, [own])

        assert session.added == []


@pytest.mark.asyncio
class TestALapsedTermIsNeverBroughtBackByIngestion:
    """CR-60: `08-webhook-app-store.md`:42 gives reactivation to restore alone, so an entitled
    notification about a subscription whose grant is already gone writes no grant at all."""

    async def test_an_entitled_notification_after_a_lapse_inserts_nothing(self):
        """EXPIRED then DID_RENEW on one subscription: the buyer waits for a restore."""
        lapsed = _grant(subscription_id=SUBSCRIPTION_B)
        lapsed.status = AccessGrantStatus.expired
        session = _StubSession(prior=lapsed)

        outcome = await _write(session, [])

        # `replayed`, because this write ended no grant and inserted none.
        assert (outcome, session.added) == (WriteOutcome.replayed, [])

    async def test_the_winning_subscriptions_live_grant_is_left_alone(self):
        """A later notification about the newest-wins loser must not take the winner's grant."""
        winner = _grant(subscription_id=SUBSCRIPTION_A)
        loser = _grant(subscription_id=SUBSCRIPTION_B)
        loser.status = AccessGrantStatus.expired
        session = _StubSession(_usage(winner, monthly_period=THIS_MONTH, monthly_used=0),
                               prior=loser)

        outcome = await _write(session, [winner])

        assert (outcome, session.added) == (WriteOutcome.replayed, [])
        assert (winner.status, winner.ends_at) == (AccessGrantStatus.active, TERM_END)

    async def test_a_first_verified_purchase_still_inserts_control(self):
        """The control: a subscription that never had a grant is a purchase, not a lapse."""
        session = _StubSession()

        outcome = await _write(session, [])

        assert (outcome, len(session.added)) == (WriteOutcome.applied, 2)

    async def test_restore_may_bring_the_lapsed_term_back_control(self):
        """The control: `may_reactivate` is the whole difference between the two callers."""
        lapsed = _grant(subscription_id=SUBSCRIPTION_B)
        lapsed.status = AccessGrantStatus.expired
        session = _StubSession(prior=lapsed)

        outcome = await _write(session, [], may_reactivate=True)

        assert (outcome, len(session.added)) == (WriteOutcome.applied, 2)


@pytest.mark.asyncio
class TestAnOperatorsGrantIsNotEndedSilently:
    """WR-61: `08-webhook-app-store.md`:40 names the free and the subscription grant as the rows
    ingestion may end, and D-18 gives no path back, so ending a `manual` one is recorded."""

    async def test_a_superseded_manual_grant_is_named_in_one_warning(self, monkeypatch):
        issued = _grant(source=AccessGrantSource.manual, subscription_id=None, ends_at=None)
        session = _StubSession(_usage(issued, monthly_period=THIS_MONTH, monthly_used=0))
        records = _writer_warnings(monkeypatch)

        await _write(session, [issued])

        assert issued.status is AccessGrantStatus.expired
        assert records == [{"event": "manual_grant_superseded",
                            "grant_id": str(issued.id),
                            "source": AccessGrantSource.manual}]

    async def test_a_withdrawal_never_reaches_the_operators_grant_control(self, monkeypatch):
        """The control on what the line carries: outside the entitled set the sweep is this
        subscription's own rows, so a manual grant is neither ended nor recorded."""
        issued = _grant(source=AccessGrantSource.manual, subscription_id=None, ends_at=None)
        session = _StubSession()
        records = _writer_warnings(monkeypatch)

        await _write(session, [issued], status=SubscriptionStatus.revoked)

        assert (issued.status, records) == (AccessGrantStatus.active, [])

    async def test_an_ordinary_supersession_is_not_recorded_control(self, monkeypatch):
        """The control: every entitled write supersedes something, so an unconditional line is noise."""
        free = _grant(source=AccessGrantSource.anonymous_device_grant, subscription_id=None,
                      ends_at=None, tier_id=FREE_TIER_ID)
        session = _StubSession(_usage(free, monthly_period=THIS_MONTH, monthly_used=0))
        records = _writer_warnings(monkeypatch)

        await _write(session, [free])

        assert records == []


class _LockStubResult:
    """The grant-tier read is taken with `.all()` and the usage-tier lock with `.first()`."""

    def __init__(self, answer) -> None:
        self._answer = answer

    def all(self):
        return self._answer

    def first(self):
        return self._answer


class _LockStubSession:
    """Answers the first read with the locked grant rows and every read after it with one usage row."""

    def __init__(self, grants: list[AccessGrant], usage: UserMonthlyUsage | None) -> None:
        self.grants = grants
        self.usage = usage
        self.reads = 0

    async def exec(self, statement):  # noqa: ARG002
        self.reads += 1
        return _LockStubResult(self.grants if self.reads == 1 else self.usage)


@pytest.mark.asyncio
class TestTheSecondLockTierRefusesAnAbsentUsageRow:
    """WR-33: `lock_usage` answers `None` for a row that is not there, which is the fail-closed
    signal. Refused here, no row is written and no lock has been spent on anything."""

    async def test_an_absent_usage_row_raises_under_the_locks(self):
        held = _grant(subscription_id=SUBSCRIPTION_A)
        session = _LockStubSession([held], None)

        with pytest.raises(MissingUsageRowError) as failure:
            await SubscriptionsDB(session).lock_grants_of([DESTINATION])

        assert failure.value.grant_id == held.id

    async def test_a_present_usage_row_answers_the_locked_set_control(self):
        """The control: the refusal above is the absent row and not every call to this method."""
        held = _grant(subscription_id=SUBSCRIPTION_A)
        session = _LockStubSession([held], _usage(held, monthly_period=THIS_MONTH, monthly_used=0))

        assert await SubscriptionsDB(session).lock_grants_of([DESTINATION]) == [held]

    async def test_the_usage_tier_is_taken_after_the_grant_tier_control(self):
        """The control: a refusal that preceded the grant-tier read would invert the lock order."""
        held = _grant(subscription_id=SUBSCRIPTION_A)
        session = _LockStubSession([held], None)

        with pytest.raises(MissingUsageRowError):
            await SubscriptionsDB(session).lock_grants_of([DESTINATION])

        assert session.reads == 2
