"""The sync service's statements: no lock, the shared predicate, the boundaries and the read order."""
from datetime import UTC, datetime
from uuid import uuid7

from sqlalchemy.dialects import postgresql

from nativespeaker.api.crud import GrantsDB
from nativespeaker.api.schemas.auth import Entitlement, EntitlementStatus, EntitlementType
from nativespeaker.api.services.sync import SyncService
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

# The whole difference between the locking and the non-locking read, as PostgreSQL receives it.
LOCK_CLAUSE = " FOR UPDATE"


class _StubResult:
    """Both accessor shapes the service uses, over one row list."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _StubSession:
    """Stands in for the request session, keeping every statement it was asked to run."""

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
        """The target entity of each statement, in the order the service issued them."""
        return [self._ENTITY_KEY[s.column_descriptions[0]["entity"]] for s in self.statements]


def _grant(*, user_id=..., tier_id=TIER_ID, status=AccessGrantStatus.active,
           starts_at=..., ends_at=None) -> AccessGrant:
    """One grant row shaped exactly as `read_effective_grants` returns one."""
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


def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))


def _without_the_lock(sql: str) -> str:
    """The compiled locking text with its trailing lock clause removed, and nothing else changed."""
    assert sql.endswith(LOCK_CLAUSE), sql
    return sql[:-len(LOCK_CLAUSE)]


async def _read(session: _StubSession) -> Entitlement:
    """The entitlement the service reports over `session` at the fixed instant."""
    return await SyncService(db=session, evaluated_at=EVALUATED_AT).read_entitlement(USER_ID)


async def _happy_path() -> _StubSession:
    """Read one effective grant with its usage row, and return the session the service used."""
    grant = _grant()
    session = _StubSession(grants=(grant,), usage=_usage(grant))
    await _read(session)
    return session


async def _issued(reader) -> str:
    """The compiled text of the single statement `reader` issues against a recording session."""
    session = _StubSession(grants=(), usage=None)
    await reader(GrantsDB(session))
    return _compiled(session.statements[0])


class TestSyncTakesNoLock:
    """Every statement sync issues is lock-free, which is the exact inverse of what the charge issues."""

    async def test_the_effective_grant_statement_takes_no_lock(self):
        session = await _happy_path()
        assert "FOR UPDATE" not in _compiled(session.statements[0])

    async def test_the_usage_statement_takes_no_lock(self):
        session = await _happy_path()
        assert "FOR UPDATE" not in _compiled(session.statements[1])

    async def test_the_tier_statement_takes_no_lock(self):
        session = await _happy_path()
        assert "FOR UPDATE" not in _compiled(session.statements[2])

    async def test_the_read_order_is_grants_then_usage_then_allowance(self):
        session = await _happy_path()
        assert session.entities == ["grants", "usage", "allowance"]

    async def test_the_request_session_is_left_clean(self):
        """`get_db` commits on exit, so anything this service dirtied would silently persist."""
        session = await _happy_path()
        assert session.added == []
        assert (session.committed, session.rolled_back) == (False, False)


class TestThePredicateIsOneDefinition:
    """The locking and non-locking reads compile to one text apart from the trailing lock clause."""

    async def test_the_grant_reads_differ_only_by_the_lock_clause(self):
        locking = await _issued(lambda db: db.lock_effective_grants(USER_ID, EVALUATED_AT))
        non_locking = await _issued(lambda db: db.read_effective_grants(USER_ID, EVALUATED_AT))
        assert locking != non_locking
        assert _without_the_lock(locking) == non_locking

    async def test_the_usage_reads_differ_only_by_the_lock_clause(self):
        grant_id = uuid7()
        locking = await _issued(lambda db: db.lock_usage(grant_id))
        non_locking = await _issued(lambda db: db.read_usage(grant_id))
        assert locking != non_locking
        assert _without_the_lock(locking) == non_locking


class TestThePredicateBoundaries:
    """The grant currentness rule, asserted against the statement sync issues rather than the charge's."""

    async def test_the_lower_bound_is_inclusive(self):
        """A grant whose `starts_at` equals the evaluated instant is already effective."""
        sql = _compiled((await _happy_path()).statements[0])
        assert "core.access_grants.starts_at <= " in sql
        assert "core.access_grants.starts_at < " not in sql

    async def test_the_upper_bound_is_exclusive(self):
        """A grant ending exactly when its successor starts is effective for exactly one of them."""
        sql = _compiled((await _happy_path()).statements[0])
        assert "core.access_grants.ends_at > " in sql
        assert "core.access_grants.ends_at >= " not in sql

    async def test_an_open_ended_grant_is_admitted_by_the_predicate(self):
        """A NULL `ends_at` is legal and effective forever."""
        sql = _compiled((await _happy_path()).statements[0])
        assert "core.access_grants.ends_at IS NULL" in sql

    async def test_it_orders_by_the_grant_id_ascending_and_takes_no_row_limit(self):
        """A second effective grant must stay visible to the caller that has to fail closed on it."""
        sql = _compiled((await _happy_path()).statements[0])
        assert "ORDER BY core.access_grants.id ASC" in sql
        assert "LIMIT" not in sql

    async def test_no_user_row_is_read_by_any_statement(self):
        """SHARED-INVARIANTS:33 forbids a user-row tier above the grants on any path, not just a swap."""
        session = await _happy_path()
        assert all("core.users" not in _compiled(s) for s in session.statements)


class TestTheZeroGrantAnswer:
    """A caller holding no grant is answered with the no-grant defaults, not refused and not invented."""

    async def test_it_reports_all_six_no_grant_fields(self):
        entitlement = await _read(_StubSession(grants=()))
        assert (entitlement.type, entitlement.status) == (EntitlementType.none, EntitlementStatus.none)
        assert (entitlement.tier_id, entitlement.monthly_credits) == (None, None)
        assert (entitlement.current_period, entitlement.monthly_used) == (PERIOD, 0)

    async def test_the_period_is_the_captured_instant_and_is_never_null(self):
        """`current_period` is not nullable even with nothing to report, so it cannot come from a grant."""
        entitlement = await _read(_StubSession(grants=()))
        assert entitlement.current_period == EVALUATED_AT.strftime("%Y-%m") == PERIOD

    async def test_it_stops_at_the_grant_read(self):
        """No grant means there is no usage row and no tier to look up."""
        session = _StubSession(grants=())
        await _read(session)
        assert session.entities == ["grants"]

    async def test_it_writes_nothing_on_the_way_out(self):
        session = _StubSession(grants=())
        await _read(session)
        assert session.added == []
        assert (session.committed, session.rolled_back) == (False, False)


class TestTheRolloverIsComputedNeverWritten:
    """The mirror of `test_quota_resolver.py::TestLazyRollover`: the same rule, with no effect on the row."""

    @staticmethod
    def _seeded(*, monthly_period, monthly_used) -> tuple[UserMonthlyUsage, _StubSession]:
        grant = _grant()
        usage = _usage(grant, monthly_period=monthly_period, monthly_used=monthly_used)
        return usage, _StubSession(grants=(grant,), usage=usage)

    async def test_a_stale_period_reports_zero_for_the_current_period(self):
        _, session = self._seeded(monthly_period=STALE_PERIOD, monthly_used=17)
        entitlement = await _read(session)
        assert (entitlement.current_period, entitlement.monthly_used) == (PERIOD, 0)

    async def test_a_stale_row_is_left_exactly_as_it_was_found(self):
        """`get_db` commits on exit, so an assignment here would persist a rollover from a read."""
        usage, session = self._seeded(monthly_period=STALE_PERIOD, monthly_used=17)
        await _read(session)
        assert (usage.monthly_period, usage.monthly_used) == (STALE_PERIOD, 17)
        assert session.added == []
        assert (session.committed, session.rolled_back) == (False, False)

    async def test_a_matching_period_reports_the_stored_count(self):
        _, session = self._seeded(monthly_period=PERIOD, monthly_used=7)
        entitlement = await _read(session)
        assert (entitlement.current_period, entitlement.monthly_used) == (PERIOD, 7)

    async def test_a_matching_period_row_is_left_untouched_too(self):
        usage, session = self._seeded(monthly_period=PERIOD, monthly_used=7)
        await _read(session)
        assert (usage.monthly_period, usage.monthly_used) == (PERIOD, 7)
        assert session.added == []
        assert (session.committed, session.rolled_back) == (False, False)
