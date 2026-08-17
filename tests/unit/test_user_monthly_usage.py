"""`core.user_monthly_usage`: one mutable counter per access grant.

Structural expectations are transcribed from the specification. The database behaviour is
exercised against a recording session so the statements the quota path actually issues — and the
ones it must never issue — are checked directly.
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid7

import pytest
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.app.dependencies import require_quota
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.database.usage import GrantsDB, UsageDB, current_period
from nativespeaker.api.exceptions import QuotaExceededError
from nativespeaker.api.models.users import AccessGrant
from nativespeaker.api.quota.usage import (
    MissingUsageRowError,
    UsageRowError,
    assert_allowance_not_stored,
    assert_grants_no_access,
    assert_monthly_used,
    assert_one_row_per_grant,
    assert_period,
    assert_stays_with_grant,
    derived_allowance,
    needs_rollover,
    new_usage_row,
    period_of,
    require_usage_row,
    rolled_over,
    usage_state,
)
from unit.conftest import quota_request


class FakeResult:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def first(self):
        return self._value

    def all(self):
        return self._rows


class FakeSession:
    """Records every statement the module under test issues, and the commits, in order. A commit
    is recorded as the literal `COMMIT` so its position among the statements is visible."""

    def __init__(self, *results: FakeResult):
        self.results = list(results)
        self.statements: list[object] = []
        self.commits = 0

    async def exec(self, statement):
        self.statements.append(statement)
        return self.results.pop(0) if self.results else FakeResult()

    async def commit(self) -> None:
        self.statements.append("COMMIT")
        self.commits += 1

    def sql(self) -> list[str]:
        return [str(statement) for statement in self.statements]


def db(session: FakeSession) -> AsyncSession:
    """The recording session, as the database modules type their session argument."""
    return cast(AsyncSession, session)


USAGE_TABLE = SQLModel.metadata.tables["core.user_monthly_usage"]
GRANTS_TABLE = SQLModel.metadata.tables["core.access_grants"]


def live_grant(user_id, *, tier_id: str = "free") -> AccessGrant:
    """One effective `core.access_grants` row for this user."""
    return AccessGrant(user_id=user_id, tier_id=tier_id,
                       source=AccessGrantSource.anonymous_device_grant,
                       status=AccessGrantStatus.active,
                       starts_at=datetime(2026, 1, 1, tzinfo=UTC))


async def quota_checked_request(session: FakeSession, user_id) -> None:
    """One quota-checked request, driving the live enforcement path against the recording
    session: backend admission, then the lazy monthly rollover sequence."""
    user = MagicMock()
    user.id = user_id
    await require_quota(quota_request(), user=user, db=db(session))


# --- The row and its fields --------------------------------------------------------------------

# [utest->req~schema-user-monthly-usage-grant-id-field~1]
# [utest->req~schema-user-monthly-usage-one-row-per-grant~1]
def test_grant_id_is_the_primary_key_and_references_the_grant():
    """`grant_id` names the grant whose credits are consumed; being the primary key is what
    caps the table at one row per grant."""
    assert [column.name for column in USAGE_TABLE.primary_key.columns] == [
        "grant_id"]
    targets = {str(key.target_fullname) for key in USAGE_TABLE.foreign_keys}
    assert targets == {"core.access_grants.id"}
    assert "user_id" not in USAGE_TABLE.columns.keys()


# [utest->req~schema-user-monthly-usage-one-row-per-grant~1]
def test_a_second_row_for_the_same_grant_is_refused():
    first, second = uuid7(), uuid7()
    assert_one_row_per_grant([first, second])
    with pytest.raises(UsageRowError):
        assert_one_row_per_grant([first, second, first])


# [utest->req~schema-user-monthly-usage-monthly-period-field~1]
def test_monthly_period_is_the_utc_calendar_month_in_yyyy_mm():
    assert period_of(datetime(2026, 3, 9, 12, 0, tzinfo=UTC)) == "2026-03"
    # The recommended convention is the UTC calendar month, so a local-time new year that is
    # still December in UTC counts as December.
    east = timezone(timedelta(hours=5))
    assert period_of(datetime(2026, 1, 1, 0, 30, tzinfo=east)) == "2025-12"
    assert current_period(datetime(2026, 3, 9, 12, 0, tzinfo=UTC)) == "2026-03"
    for bad in ("2026-13", "202603", "2026-3", "march"):
        with pytest.raises(UsageRowError):
            assert_period(bad)


# [utest->req~schema-user-monthly-usage-monthly-used-field~1]
def test_monthly_used_is_consumption_for_the_stored_period():
    assert assert_monthly_used(0) == 0
    assert assert_monthly_used(7) == 7
    with pytest.raises(UsageRowError):
        assert_monthly_used(-1)


# [utest->req~schema-user-monthly-usage-monthly-used-field~1]
@pytest.mark.asyncio
async def test_the_increment_is_bounded_by_the_allowance_of_the_period():
    """The live enforcement path increments `monthly_used` for the stored period, and only while
    the allowance the grant's tier configures leaves something to consume."""
    user_id = uuid7()
    grant = live_grant(user_id)
    period = current_period()
    session = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult((period, 3)))
    await quota_checked_request(session, user_id)
    update = session.sql()[-2]  # the increment, then the sequence's own commit
    assert "UPDATE core.user_monthly_usage" in update
    assert "monthly_used" in update and "monthly_period" in update

    # A counter already at the tier's allowance is ordinary exhaustion: nothing is written.
    exhausted = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult((period, 10)))
    with pytest.raises(QuotaExceededError):
        await quota_checked_request(exhausted, user_id)
    assert [sql for sql in exhausted.sql() if sql.startswith("UPDATE")] == []


# --- The lazy monthly reset --------------------------------------------------------------------

# [utest->req~schema-user-monthly-usage-lazy-monthly-reset~1]
def test_the_counter_rolls_over_when_the_month_changes():
    assert needs_rollover("2026-02", "2026-03") is True
    assert needs_rollover("2026-03", "2026-03") is False
    assert rolled_over("2026-02", 9, current="2026-03") == ("2026-03", 0)
    assert rolled_over("2026-03", 9, current="2026-03") == ("2026-03", 9)


# [utest->req~schema-user-monthly-usage-lazy-monthly-reset~1]
@pytest.mark.asyncio
async def test_the_reset_happens_on_the_first_quota_checked_request_of_the_new_month():
    """A stale period is advanced and zeroed in place by the request that noticed; a row already
    on the current period is not rewritten."""
    user_id = uuid7()
    grant = live_grant(user_id)
    stale = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult(("2020-01", 10)))
    await quota_checked_request(stale, user_id)
    # the grant read, the usage read, the reset, the increment, then the commit
    assert len(stale.statements) == 5
    rollover = stale.sql()[2]
    assert rollover.startswith("UPDATE core.user_monthly_usage SET monthly_period=")
    assert "monthly_used=:monthly_used" in rollover  # zeroed, not carried forward

    current = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult((current_period(), 1)))
    await quota_checked_request(current, user_id)
    assert len(current.statements) == 4  # the two reads, the increment, then the commit


# --- The allowance is the tier's, and is not stored here ---------------------------------------

# [utest->req~schema-user-monthly-usage-allowance-derived-from-tier~1]
@pytest.mark.asyncio
async def test_the_allowance_comes_from_the_grant_joined_to_its_tier():
    user_id = uuid7()
    row = AccessGrant(user_id=user_id, tier_id="gold",
                      source=AccessGrantSource.registered_account_grant,
                      status=AccessGrantStatus.active,
                      starts_at=datetime(2026, 1, 1, tzinfo=UTC))
    session = FakeSession(FakeResult(rows=[(row, 200)]))
    grant = await GrantsDB(db(session)).effective_grant(user_id)
    assert grant is not None
    assert (grant.tier_id, grant.monthly_credits) == ("gold", 200)
    statement = session.sql()[0]
    assert "core.access_tiers" in statement and "monthly_credits" in statement
    assert "core.user_monthly_usage" not in statement


# [utest->req~schema-user-monthly-usage-allowance-derived-from-tier~1]
def test_a_grant_with_no_tier_row_has_no_allowance():
    assert derived_allowance("gold", 200) == 200
    assert derived_allowance(None, None) == 0


# [utest->req~schema-user-monthly-usage-allowance-not-stored~1]
def test_the_allowance_is_not_a_column_of_the_usage_table():
    columns = set(USAGE_TABLE.columns.keys())
    assert columns == {"grant_id", "monthly_period", "monthly_used", "created_at", "updated_at"}
    for forbidden in ("monthly_credits", "allowance", "monthly_limit", "tier_id"):
        assert forbidden not in columns
        with pytest.raises(UsageRowError):
            assert_allowance_not_stored(["grant_id", forbidden])
    # The tier keeps it: the grant points at the tier that carries the number.
    assert "tier_id" in GRANTS_TABLE.columns.keys()


# --- Creation, and what creation means ---------------------------------------------------------

# [utest->req~schema-user-monthly-usage-row-initializes-usage-only~1]
def test_creating_the_row_initializes_usage_state_only():
    grant_id = uuid7()
    transaction = object()
    row = new_usage_row(grant_id, now=datetime(2026, 3, 9, tzinfo=UTC),
                        grant_transaction=transaction, usage_transaction=transaction)
    assert (row.grant_id, row.monthly_period, row.monthly_used) == (grant_id, "2026-03", 0)
    assert usage_state({"grant_id": grant_id, "monthly_period": "2026-03", "monthly_used": 0})
    with pytest.raises(UsageRowError):
        usage_state({"grant_id": grant_id, "monthly_credits": 200})


# [utest->req~schema-user-monthly-usage-created-with-grant~1]
def test_the_row_is_created_in_the_transaction_that_creates_its_grant():
    grant_id = uuid7()
    with pytest.raises(UsageRowError):
        new_usage_row(grant_id, grant_transaction=object(), usage_transaction=object())


# [utest->req~schema-user-monthly-usage-created-with-grant~1]
@pytest.mark.asyncio
async def test_the_quota_path_never_creates_the_row_and_fails_closed_without_one():
    """A missing row for an existing grant is a server-side data error, not a fresh counter."""
    user_id = uuid7()
    grant = live_grant(user_id)
    session = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult(None))
    with pytest.raises(MissingUsageRowError):
        await quota_checked_request(session, user_id)
    assert all("INSERT" not in sql for sql in session.sql())
    assert session.commits == 0  # nothing is persisted behind a data error either

    with_row = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult((current_period(), 1)))
    await quota_checked_request(with_row, user_id)
    assert all("INSERT" not in sql for sql in with_row.sql())

    assert require_usage_row("2026-03", grant.id) == "2026-03"
    with pytest.raises(MissingUsageRowError):
        require_usage_row(None, grant.id)


# [utest->req~schema-user-monthly-usage-created-with-grant~1]
@pytest.mark.asyncio
async def test_grant_creation_writes_the_usage_row_in_the_same_transaction():
    grant_id = uuid7()
    session = FakeSession()
    row = await UsageDB(db(session)).create_for_grant(grant_id, transaction=session)
    assert row.monthly_used == 0
    assert "INSERT INTO core.user_monthly_usage" in session.sql()[0]
    other = FakeSession()
    with pytest.raises(UsageRowError):
        await UsageDB(db(other)).create_for_grant(grant_id, transaction=object())
    assert other.statements == []


# The one creation point also serves a grant that supersedes another: the superseded grant's
# period and counter cross over unchanged — no reset, no clamping, no prorating.
# [utest->req~schema-user-monthly-usage-row-initializes-usage-only~1]
@pytest.mark.asyncio
async def test_a_superseding_grant_carries_the_counter_across_unchanged():
    session = FakeSession()
    row = await UsageDB(db(session)).create_for_grant(uuid7(), transaction=session,
                                                      carried=("2026-03", 7))
    assert (row.monthly_period, row.monthly_used) == ("2026-03", 7)
    fresh = new_usage_row(uuid7(), now=datetime(2026, 8, 16, tzinfo=UTC),
                          grant_transaction=None, usage_transaction=None)
    assert (fresh.monthly_period, fresh.monthly_used) == ("2026-08", 0)


# --- The row is not entitlement, and does not travel -------------------------------------------

# [utest->req~schema-user-monthly-usage-grants-no-access~1]
def test_a_usage_row_allocates_no_grant_and_no_introductory_entitlement():
    # Creating the row allocates nothing else — no grant row, no introductory entitlement.
    assert_grants_no_access()
    for allocated in (["core.access_grants"], ["introductory_entitlement"]):
        with pytest.raises(UsageRowError):
            assert_grants_no_access(allocated)


# [utest->req~schema-user-monthly-usage-grants-no-access~1]
@pytest.mark.asyncio
async def test_quota_refuses_a_user_without_a_grant_before_reading_any_counter():
    """The grant read is the only statement a grantless user's quota check issues: no counter
    is read, and none is created."""
    session = FakeSession(FakeResult(rows=[]))
    user = MagicMock()
    user.id = uuid7()
    with pytest.raises(QuotaExceededError):
        await require_quota(quota_request(), user=user, db=db(session))
    assert len(session.statements) == 1
    assert "core.user_monthly_usage" not in session.sql()[0]


# [utest->req~schema-user-monthly-usage-stays-with-grant~1]
def test_the_counter_stays_with_its_grant_and_is_never_minted_afresh():
    grant_id, other = uuid7(), uuid7()
    assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=grant_id)
    with pytest.raises(UsageRowError):
        assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=other)
    with pytest.raises(UsageRowError):
        assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=grant_id,
                                minted_fresh=True)
