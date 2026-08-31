"""The resolver's pure policy: the branches a real crud cannot produce, and the lock order it cannot show."""
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy.dialects import postgresql

from nativespeaker.api.errors import (
    MissingUsageRowError,
    MultipleEffectiveGrantsError,
    QuotaExceededError,
    UnknownTierError,
)
from nativespeaker.api.services.quota import QuotaService
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    AccessTier,
    UserMonthlyUsage,
)

USER_ID = uuid7()
TIER_ID = "registered"
ALLOWANCE = 50
EVALUATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
PERIOD = "2026-08"
STALE_PERIOD = "2026-07"


class _StubResult:
    """Both accessor shapes the resolver uses, over one row list."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _StubSession:
    """Stands in for the short session the charge opens, keeping every statement it was asked to run."""

    _ENTITY_KEY = {AccessGrant: "grants", UserMonthlyUsage: "usage", AccessTier: "allowance"}

    def __init__(self, *, grants=(), usage=None, allowance=ALLOWANCE):
        self._rows = {"grants": list(grants),
                      "usage": [] if usage is None else [usage],
                      "allowance": [] if allowance is None else [allowance]}
        self.statements = []
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    def add(self, instance):
        self.added.append(instance)

    async def exec(self, statement):
        self.statements.append(statement)
        entity = statement.column_descriptions[0]["entity"]
        return _StubResult(self._rows[self._ENTITY_KEY[entity]])

    @property
    def entities(self) -> list[str]:
        """The target entity of each statement, in the order the resolver issued them."""
        return [self._ENTITY_KEY[s.column_descriptions[0]["entity"]] for s in self.statements]


def _grant(*, user_id=..., tier_id=TIER_ID, status=AccessGrantStatus.active,
           starts_at=..., ends_at=None) -> AccessGrant:
    """One grant row shaped exactly as `lock_effective_grants` returns one."""
    return AccessGrant(id=uuid7(),
                       user_id=USER_ID if user_id is ... else user_id,
                       tier_id=tier_id,
                       source=AccessGrantSource.manual,
                       status=status,
                       starts_at=EVALUATED_AT if starts_at is ... else starts_at,
                       ends_at=ends_at)


def _usage(grant: AccessGrant, *, monthly_period=..., monthly_used=0) -> UserMonthlyUsage:
    return UserMonthlyUsage(grant_id=grant.id,
                            monthly_period=PERIOD if monthly_period is ... else monthly_period,
                            monthly_used=monthly_used)


async def _charge(session: _StubSession, *, evaluated_at=EVALUATED_AT) -> None:
    """Run the merged charge, handing the service a factory that yields the stub as its short session."""
    await QuotaService(lambda: session).charge(user_id=USER_ID, evaluated_at=evaluated_at)


async def _consume(*, grants=(), usage=None, allowance=ALLOWANCE) -> _StubSession:
    """Run the resolver against a stubbed session and return the session for inspection."""
    session = _StubSession(grants=grants, usage=usage, allowance=allowance)
    await _charge(session)
    return session


def _one_effective_grant(**usage_kwargs):
    """The ordinary case: one grant and its usage row, varied only by `usage_kwargs`."""
    grant = _grant()
    return grant, _usage(grant, **usage_kwargs)


def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))


class TestNoEffectiveGrant:
    """An allowance of 0 is read across the whole flow, so the existing 429 contract answers."""

    async def test_zero_rows_is_quota_exceeded(self):
        with pytest.raises(QuotaExceededError):
            await _consume(grants=())

    async def test_it_never_reaches_the_usage_row(self):
        """One statement, not two: there is no grant to look a usage row up for."""
        session = _StubSession()
        with pytest.raises(QuotaExceededError):
            await _charge(session)
        assert session.entities == ["grants"]


class TestMultipleEffectiveGrants:
    """The tripwire: unreachable in PostgreSQL, asserted anyway so a schema change is loud."""

    async def test_two_effective_grants_raise(self):
        with pytest.raises(MultipleEffectiveGrantsError):
            await _consume(grants=(_grant(), _grant()))

    async def test_it_does_not_pick_either_one(self):
        """No tie-break means no usage read: the resolver stops before choosing."""
        session = _StubSession(grants=(_grant(), _grant()))
        with pytest.raises(MultipleEffectiveGrantsError):
            await _charge(session)
        assert session.entities == ["grants"]

    async def test_it_is_an_internal_error_not_an_entitlement_answer(self):
        """500, never 429: duplicated state is a broken invariant, not a used-up allowance."""
        with pytest.raises(MultipleEffectiveGrantsError) as caught:
            await _consume(grants=(_grant(), _grant()))
        assert (caught.value.status, caught.value.code) == (500, "internal_error")
        assert not isinstance(caught.value, QuotaExceededError)


class TestMissingUsageRow:
    """Fail closed, never lazily mint: a grant without a usage row is a failed write."""

    async def test_a_grant_with_no_usage_row_raises(self):
        with pytest.raises(MissingUsageRowError):
            await _consume(grants=(_grant(),), usage=None)

    async def test_nothing_is_minted(self):
        """The whole point of the branch: no row is added, so no free allowance is invented."""
        session = _StubSession(grants=(_grant(),), usage=None)
        with pytest.raises(MissingUsageRowError):
            await _charge(session)
        assert session.added == []
        assert session.entities == ["grants", "usage"]

    async def test_it_is_an_internal_error_not_a_free_pass(self):
        with pytest.raises(MissingUsageRowError) as caught:
            await _consume(grants=(_grant(),), usage=None)
        assert (caught.value.status, caught.value.code) == (500, "internal_error")


class TestUnknownTier:
    """A grant pointing at a tier with no row: fail closed, never allowance 0 and never unbounded."""

    async def test_a_missing_tier_row_raises(self):
        grant, usage = _one_effective_grant()
        with pytest.raises(UnknownTierError):
            await _consume(grants=(grant,), usage=usage, allowance=None)

    async def test_it_does_not_silently_become_an_exhausted_allowance(self):
        """Reading a missing tier as 0 would be an unexplained 429 for a paying customer."""
        grant, usage = _one_effective_grant()
        with pytest.raises(UnknownTierError) as caught:
            await _consume(grants=(grant,), usage=usage, allowance=None)
        assert not isinstance(caught.value, QuotaExceededError)
        assert (caught.value.status, caught.value.code) == (500, "internal_error")

    async def test_it_does_not_silently_become_an_unbounded_allowance(self):
        grant, usage = _one_effective_grant()
        with pytest.raises(UnknownTierError):
            await _consume(grants=(grant,), usage=usage, allowance=None)
        assert usage.monthly_used == 0


class TestRemainingNeverNegative:
    """`remaining` never goes negative, and the adjacency either side of that boundary."""

    @pytest.mark.parametrize("used", [ALLOWANCE, ALLOWANCE + 1, ALLOWANCE + 49],
                             ids=["exactly-at", "one-over", "far-over"])
    async def test_at_or_above_the_allowance_rejects(self, used):
        """An over-allowance row -- only reachable by a future tier downgrade -- is exhaustion."""
        grant, usage = _one_effective_grant(monthly_used=used)
        with pytest.raises(QuotaExceededError):
            await _consume(grants=(grant,), usage=usage)

    @pytest.mark.parametrize("used", [ALLOWANCE, ALLOWANCE + 1, ALLOWANCE + 49],
                             ids=["exactly-at", "one-over", "far-over"])
    async def test_a_rejection_leaves_the_count_untouched(self, used):
        """A refused request must never be charged -- and must never wrap into a second charge."""
        grant, usage = _one_effective_grant(monthly_used=used)
        with pytest.raises(QuotaExceededError):
            await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_used == used

    async def test_one_below_the_allowance_is_admitted_and_lands_exactly_on_it(self):
        grant, usage = _one_effective_grant(monthly_used=ALLOWANCE - 1)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_used == ALLOWANCE

    async def test_the_next_request_after_that_rejects(self):
        """Adjacency closed from both sides, against the same row the previous case just wrote."""
        grant, usage = _one_effective_grant(monthly_used=ALLOWANCE - 1)
        await _consume(grants=(grant,), usage=usage)
        with pytest.raises(QuotaExceededError):
            await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_used == ALLOWANCE

    async def test_a_fresh_row_is_charged_exactly_once(self):
        grant, usage = _one_effective_grant(monthly_used=0)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_used == 1


class TestLazyRollover:
    """The reset happens before the allowance comparison, in the same transaction."""

    async def test_a_stale_period_resets_the_count_before_the_increment(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD, monthly_used=17)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_used == 1

    async def test_a_stale_period_is_rewritten_from_the_captured_instant(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_period == EVALUATED_AT.strftime("%Y-%m") == PERIOD

    async def test_a_stale_exhausted_row_does_not_refuse_the_new_period(self):
        """The ordering claim as the failure it prevents: last month's exhaustion must not answer this month."""
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD, monthly_used=ALLOWANCE)
        await _consume(grants=(grant,), usage=usage)
        assert (usage.monthly_period, usage.monthly_used) == (PERIOD, 1)

    async def test_a_matching_period_is_not_rewritten_and_the_count_carries_forward(self):
        grant, usage = _one_effective_grant(monthly_period=PERIOD, monthly_used=7)
        await _consume(grants=(grant,), usage=usage)
        assert (usage.monthly_period, usage.monthly_used) == (PERIOD, 8)


class TestTheLockingStatements:
    """The lock, the order and the two predicate boundaries, none of which a response can show."""

    async def _admitted_session(self) -> _StubSession:
        grant, usage = _one_effective_grant()
        return await _consume(grants=(grant,), usage=usage)

    async def test_the_effective_grant_statement_locks_and_orders_ascending_by_id(self):
        session = await self._admitted_session()
        sql = _compiled(session.statements[0])
        assert "FOR UPDATE" in sql
        assert "ORDER BY core.access_grants.id ASC" in sql

    async def test_the_usage_statement_locks(self):
        session = await self._admitted_session()
        assert "FOR UPDATE" in _compiled(session.statements[1])

    async def test_the_tier_statement_takes_no_lock(self):
        """The tier value is compared, never incremented, so locking it would serialise a whole tier for no gain."""
        session = await self._admitted_session()
        assert "FOR UPDATE" not in _compiled(session.statements[2])

    async def test_the_lower_bound_is_inclusive(self):
        """A grant whose `starts_at` equals the evaluated instant is already effective."""
        session = await self._admitted_session()
        sql = _compiled(session.statements[0])
        assert "core.access_grants.starts_at <= " in sql
        assert "core.access_grants.starts_at < " not in sql

    async def test_the_upper_bound_is_exclusive(self):
        """A grant ending exactly when its successor starts is effective for exactly one of them."""
        session = await self._admitted_session()
        sql = _compiled(session.statements[0])
        assert "core.access_grants.ends_at > " in sql
        assert "core.access_grants.ends_at >= " not in sql

    async def test_an_open_ended_grant_is_admitted_by_the_predicate(self):
        """A NULL `ends_at` is legal and effective forever."""
        session = await self._admitted_session()
        assert "core.access_grants.ends_at IS NULL" in _compiled(session.statements[0])


class TestGrantThenUsageOrder:
    """The grant lock is held before the usage lock on every path, because two orders is how a deadlock is written."""

    async def test_the_admitted_path_locks_the_grant_first(self):
        grant, usage = _one_effective_grant()
        session = await _consume(grants=(grant,), usage=usage)
        assert session.entities == ["grants", "usage", "allowance"]

    async def test_the_exhausted_path_locks_in_the_same_order(self):
        grant, usage = _one_effective_grant(monthly_used=ALLOWANCE)
        session = _StubSession(grants=(grant,), usage=usage)
        with pytest.raises(QuotaExceededError):
            await _charge(session)
        assert session.entities == ["grants", "usage", "allowance"]

    async def test_the_rollover_path_locks_in_the_same_order(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD, monthly_used=ALLOWANCE)
        session = await _consume(grants=(grant,), usage=usage)
        assert session.entities == ["grants", "usage", "allowance"]

    async def test_the_missing_usage_path_stops_after_the_usage_read(self):
        session = _StubSession(grants=(_grant(),), usage=None)
        with pytest.raises(MissingUsageRowError):
            await _charge(session)
        assert session.entities == ["grants", "usage"]

    async def test_no_user_row_is_locked_ahead_of_either(self):
        """SHARED-INVARIANTS:33 forbids a user-row lock tier above the grants, not just a swap."""
        grant, usage = _one_effective_grant()
        session = await _consume(grants=(grant,), usage=usage)
        assert all("core.users" not in _compiled(s) for s in session.statements)


class TestTheResolverReadsNoClock:
    """One captured instant decides both the predicate and the period, so a rollover cannot race itself."""

    async def test_the_period_is_the_evaluated_instants_utc_calendar_month(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_period == "2026-08"

    async def test_a_different_instant_produces_a_different_period(self):
        """The period tracks the argument, which is the only thing that makes the captured instant checkable."""
        grant = _grant()
        usage = _usage(grant, monthly_period=STALE_PERIOD)
        session = _StubSession(grants=(grant,), usage=usage)
        earlier = EVALUATED_AT - timedelta(days=60)
        await _charge(session, evaluated_at=earlier)
        assert usage.monthly_period == earlier.strftime("%Y-%m") == "2026-06"

    async def test_the_updated_at_stamp_is_the_captured_instant(self):
        grant, usage = _one_effective_grant()
        await _consume(grants=(grant,), usage=usage)
        assert usage.updated_at == EVALUATED_AT
