"""§8.4 / REBIND-05, REBIND-06: the resolver's pure policy, proved without a database.

`tests/e2e/test_quota.py` proves the served behaviour against real rows over the real transport.
This module proves the branches the *database* cannot produce, and the properties a served
response cannot show.

`ix_access_grants_one_active_per_user` (`migrations/20260818_01_initial-release.sql:458-460`) is a
plain non-deferrable partial unique index permitting one `status='active'` row per user, and the
effective-grant predicate is a strict subset of that -- so two effective grants are unreachable in
real PostgreSQL. D-10 requires that state to raise rather than tie-break, and a stub session is the
only way to put it in front of `consume_quota`. The stub is also what makes the lock-order claim
checkable directly: it keeps every statement it was asked to run, in order, so
"the grant rows are locked before the usage row" is asserted rather than read off the source.

Both effective-grant boundaries -- `starts_at` inclusive, `ends_at` exclusive -- are asserted here
against the *compiled* predicate rather than behaviourally, because a stub returns whatever it is
handed and so cannot demonstrate a boundary at all. Their behavioural proof is
`tests/e2e/test_quota.py`'s boundary class.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy.dialects import postgresql

from nativespeaker.api.errors import (
    INTERNAL_ERROR,
    MissingUsageRowError,
    MultipleEffectiveGrantsError,
    QuotaExceededError,
    UnknownTierError,
)
from nativespeaker.api.models import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    AccessTier,
    UserMonthlyUsage,
)
from nativespeaker.api.quota import consume_quota

USER_ID = uuid7()
ROUTE = "/chats"
TIER_ID = "registered"
ALLOWANCE = 50
EVALUATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
PERIOD = "2026-08"
STALE_PERIOD = "2026-07"


class _StubResult:
    """Both accessor shapes the resolver uses, over one row list.

    `.all()` is what the identity analog's stub lacks: the effective-grant select carries no
    row-count cap (D-10), so its caller reads every row rather than the first.
    """

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _StubSession:
    """Stands in for the short session `require_quota` opens, and keeps what it was asked to run.

    Rows are dispatched by the statement's target entity, not by call position. That is deliberate:
    a position-keyed stub would happily hand the grant rows to a usage read if the resolver ever
    swapped the two, quietly passing the very test that exists to catch it. Ordering is asserted
    once, explicitly, by `TestGrantThenUsageOrder`.

    `add` records rather than acting, so "nothing was minted" is an assertion about a call that was
    never made rather than about a row that happens not to exist.
    """

    _ENTITY_KEY = {AccessGrant: "grants", UserMonthlyUsage: "usage", AccessTier: "allowance"}

    def __init__(self, *, grants=(), usage=None, allowance=ALLOWANCE):
        self._rows = {"grants": list(grants),
                      "usage": [] if usage is None else [usage],
                      "allowance": [] if allowance is None else [allowance]}
        self.statements = []
        self.added = []

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


async def _consume(*, grants=(), usage=None, allowance=ALLOWANCE) -> _StubSession:
    """Run the resolver against a stubbed session and return the session for inspection."""
    session = _StubSession(grants=grants, usage=usage, allowance=allowance)
    await consume_quota(session, user_id=USER_ID, evaluated_at=EVALUATED_AT, route=ROUTE)
    return session


def _one_effective_grant(**usage_kwargs):
    """The ordinary case: one grant and its usage row, varied only by `usage_kwargs`."""
    grant = _grant()
    return grant, _usage(grant, **usage_kwargs)


def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))


class TestNoEffectiveGrant:
    """D-08: allowance 0 read across §8.4 steps 1 and 5, so the existing 429 contract answers."""

    async def test_zero_rows_is_quota_exceeded(self):
        with pytest.raises(QuotaExceededError):
            await _consume(grants=())

    async def test_it_never_reaches_the_usage_row(self):
        """One statement, not two: there is no grant to look a usage row up for."""
        session = _StubSession()
        with pytest.raises(QuotaExceededError):
            await consume_quota(session, user_id=USER_ID, evaluated_at=EVALUATED_AT, route=ROUTE)
        assert session.entities == ["grants"]


class TestMultipleEffectiveGrants:
    """D-10: the tripwire. Unreachable in PostgreSQL, asserted anyway so a schema change is loud."""

    async def test_two_effective_grants_raise(self):
        with pytest.raises(MultipleEffectiveGrantsError):
            await _consume(grants=(_grant(), _grant()))

    async def test_it_does_not_pick_either_one(self):
        """No tie-break means no usage read: the resolver stops before choosing."""
        session = _StubSession(grants=(_grant(), _grant()))
        with pytest.raises(MultipleEffectiveGrantsError):
            await consume_quota(session, user_id=USER_ID, evaluated_at=EVALUATED_AT, route=ROUTE)
        assert session.entities == ["grants"]

    async def test_it_is_an_internal_error_not_an_entitlement_answer(self):
        """500, never 429: duplicated state is a broken invariant, not a used-up allowance."""
        with pytest.raises(MultipleEffectiveGrantsError) as caught:
            await _consume(grants=(_grant(), _grant()))
        assert caught.value.error_class is INTERNAL_ERROR
        assert not isinstance(caught.value, QuotaExceededError)


class TestMissingUsageRow:
    """D-09: fail closed, never lazily mint. A grant without a usage row is a failed write."""

    async def test_a_grant_with_no_usage_row_raises(self):
        with pytest.raises(MissingUsageRowError):
            await _consume(grants=(_grant(),), usage=None)

    async def test_nothing_is_minted(self):
        """The whole point of the branch: no row is added, so no free allowance is invented."""
        session = _StubSession(grants=(_grant(),), usage=None)
        with pytest.raises(MissingUsageRowError):
            await consume_quota(session, user_id=USER_ID, evaluated_at=EVALUATED_AT, route=ROUTE)
        assert session.added == []
        assert session.entities == ["grants", "usage"]

    async def test_it_is_an_internal_error_not_a_free_pass(self):
        with pytest.raises(MissingUsageRowError) as caught:
            await _consume(grants=(_grant(),), usage=None)
        assert caught.value.error_class is INTERNAL_ERROR


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
        assert caught.value.error_class is INTERNAL_ERROR

    async def test_it_does_not_silently_become_an_unbounded_allowance(self):
        grant, usage = _one_effective_grant()
        with pytest.raises(UnknownTierError):
            await _consume(grants=(grant,), usage=usage, allowance=None)
        assert usage.monthly_used == 0


class TestRemainingNeverNegative:
    """REBIND-05's "never lets `remaining` go negative", and the adjacency either side of it."""

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
        """Adjacency closed from both sides: admitting at `allowance - 1` must exhaust at
        `allowance`, which is the same row the previous case just wrote."""
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
    """§8.4 step 4: the reset happens before the allowance comparison, in the same transaction."""

    async def test_a_stale_period_resets_the_count_before_the_increment(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD, monthly_used=17)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_used == 1

    async def test_a_stale_period_is_rewritten_from_the_captured_instant(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_period == EVALUATED_AT.strftime("%Y-%m") == PERIOD

    async def test_a_stale_exhausted_row_does_not_refuse_the_new_period(self):
        """The ordering claim, stated as the failure it prevents: last month's exhaustion must
        not answer this month's first request."""
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD, monthly_used=ALLOWANCE)
        await _consume(grants=(grant,), usage=usage)
        assert (usage.monthly_period, usage.monthly_used) == (PERIOD, 1)

    async def test_a_matching_period_is_not_rewritten_and_the_count_carries_forward(self):
        grant, usage = _one_effective_grant(monthly_period=PERIOD, monthly_used=7)
        await _consume(grants=(grant,), usage=usage)
        assert (usage.monthly_period, usage.monthly_used) == (PERIOD, 8)


class TestTheLockingStatements:
    """The lock, the order, and the two predicate boundaries -- none of them observable in a
    response, and one of them (the tier read staying unlocked) invisible in any test that only
    checks results."""

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
        """`core.access_tiers` is three shared reference rows. Locking one on every chat POST
        would serialise every user on that tier against each other for no gain -- the value is
        compared, never incremented."""
        session = await self._admitted_session()
        assert "FOR UPDATE" not in _compiled(session.statements[2])

    async def test_the_lower_bound_is_inclusive(self):
        """A grant whose `starts_at` equals the evaluated instant is already effective."""
        session = await self._admitted_session()
        sql = _compiled(session.statements[0])
        assert "core.access_grants.starts_at <= " in sql
        assert "core.access_grants.starts_at < " not in sql

    async def test_the_upper_bound_is_exclusive(self):
        """A grant whose `ends_at` equals the evaluated instant is already over -- so a grant that
        ends exactly when its successor starts is effective for exactly one of them."""
        session = await self._admitted_session()
        sql = _compiled(session.statements[0])
        assert "core.access_grants.ends_at > " in sql
        assert "core.access_grants.ends_at >= " not in sql

    async def test_an_open_ended_grant_is_admitted_by_the_predicate(self):
        """Ruling 9.11 makes a NULL `ends_at` legal and effective forever."""
        session = await self._admitted_session()
        assert "core.access_grants.ends_at IS NULL" in _compiled(session.statements[0])


class TestGrantThenUsageOrder:
    """SHARED-INVARIANTS:33: the grant lock is held before the usage lock, on every path.

    The order must be identical on every branch that reaches the usage read, because two requests
    taking the same rows in different sequences is exactly how a deadlock is written.
    """

    async def test_the_admitted_path_locks_the_grant_first(self):
        grant, usage = _one_effective_grant()
        session = await _consume(grants=(grant,), usage=usage)
        assert session.entities == ["grants", "usage", "allowance"]

    async def test_the_exhausted_path_locks_in_the_same_order(self):
        grant, usage = _one_effective_grant(monthly_used=ALLOWANCE)
        session = _StubSession(grants=(grant,), usage=usage)
        with pytest.raises(QuotaExceededError):
            await consume_quota(session, user_id=USER_ID, evaluated_at=EVALUATED_AT, route=ROUTE)
        assert session.entities == ["grants", "usage", "allowance"]

    async def test_the_rollover_path_locks_in_the_same_order(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD, monthly_used=ALLOWANCE)
        session = await _consume(grants=(grant,), usage=usage)
        assert session.entities == ["grants", "usage", "allowance"]

    async def test_the_missing_usage_path_stops_after_the_usage_read(self):
        session = _StubSession(grants=(_grant(),), usage=None)
        with pytest.raises(MissingUsageRowError):
            await consume_quota(session, user_id=USER_ID, evaluated_at=EVALUATED_AT, route=ROUTE)
        assert session.entities == ["grants", "usage"]

    async def test_no_user_row_is_locked_ahead_of_either(self):
        """SHARED-INVARIANTS:33 forbids a user-row lock tier above the grants, not just a swap."""
        grant, usage = _one_effective_grant()
        session = await _consume(grants=(grant,), usage=usage)
        assert all("core.users" not in _compiled(s) for s in session.statements)


class TestTheResolverReadsNoClock:
    """D-06: one captured instant decides both the predicate and the period string.

    Without this, a request could select a grant against one instant and compute its period
    against another -- a rollover race that is unreproducible by construction.
    """

    async def test_the_period_is_the_evaluated_instants_utc_calendar_month(self):
        grant, usage = _one_effective_grant(monthly_period=STALE_PERIOD)
        await _consume(grants=(grant,), usage=usage)
        assert usage.monthly_period == "2026-08"

    async def test_a_different_instant_produces_a_different_period(self):
        """The period tracks the argument, which is the only thing that makes D-06 checkable."""
        grant = _grant()
        usage = _usage(grant, monthly_period=STALE_PERIOD)
        session = _StubSession(grants=(grant,), usage=usage)
        earlier = EVALUATED_AT - timedelta(days=60)
        await consume_quota(session, user_id=USER_ID, evaluated_at=earlier, route=ROUTE)
        assert usage.monthly_period == earlier.strftime("%Y-%m") == "2026-06"

    async def test_the_updated_at_stamp_is_the_captured_instant(self):
        grant, usage = _one_effective_grant()
        await _consume(grants=(grant,), usage=usage)
        assert usage.updated_at == EVALUATED_AT
