"""§8.4 / REBIND-05: the quota gate on `POST /chats`, over the real app and the real transport.

Two classes, and each is the other's control:

* `TestNoEffectiveGrant` -- an **admitted** caller holding no effective grant is refused 429
  `quota_exceeded` before the handler is entered. The three ways a grant row can exist without
  being effective -- not yet started, already ended, status not `active` -- are refused
  identically, which is what makes the rejection a property of the shared effective-grant
  predicate rather than of "the table is empty".
* `TestASeededGrantIsAdmitted` -- the same caller, the same route, the same body, with the one
  difference that an effective grant and its usage row exist. It answers 200 from the handler.

Neither class means much alone. Without the positive control, every 429 above is equally
consistent with a route that is simply broken, or with a barrier that stopped admitting this
caller at all; without the negative cases, "the route serves" says nothing about whether the gate
runs. Read together they say the gate runs, refuses exactly the callers with no effective grant,
and lets everyone else through.

**Expected and correct after this plan:** a chat POST returns 429 for every user who has no
hand-seeded grant, and will keep doing so until Phase 41 or 42 mints one. `src/` still contains no
code that writes a grant row.

`TestTheEffectiveGrantStatement` covers the one property the transport cannot show: that the
selection statement takes row locks and orders ascending by grant id (SHARED-INVARIANTS:33). A
served 429 looks the same whether or not the rows were locked.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlmodel import col, select

from nativespeaker.api.models import AccessGrantStatus, UserMonthlyUsage

from .conftest import seed_grant

pytestmark = pytest.mark.e2e

PHRASE = {"phrase": "I am going to home.", "lang": "en"}

# The `registered` tier's seeded allowance (migrations/20260818_01_initial-release.sql:280-283).
# Named rather than repeated as a literal, because every arithmetic case below is expressed
# relative to it -- "at the allowance", "one below" -- and a bare 50 hides which of those a case
# means.
ALLOWANCE = 50


async def usage_rows(factory, grant_id: UUID) -> list[UserMonthlyUsage]:
    """Read `core.user_monthly_usage` back for one grant, through the test's own factory.

    The factory argument is `_db_transaction`'s swapped `async_sessionmaker`, never a fresh engine:
    every row this package writes lives inside one uncommitted transaction, so a second engine
    would open a connection that cannot see any of it and every assertion here would read zero
    rows. Same shape as `test_audit_writer.py::rows`.
    """
    async with factory() as session:
        statement = select(UserMonthlyUsage).where(col(UserMonthlyUsage.grant_id) == grant_id)
        return list((await session.exec(statement)).all())


@pytest.mark.asyncio(loop_scope="module")
class TestNoEffectiveGrant:
    """An admitted caller with nothing to spend. §8.4 step 1 routes this to the 429 contract."""

    async def test_a_caller_with_no_grant_is_refused(self, async_client,
                                                     linked_firebase_identity):
        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_the_no_grant_refusal_carries_the_shared_error_body(
            self, async_client, linked_firebase_identity):
        """The 429 is the shared `{code: ...}` shape -- not a 500, and not a bespoke payload."""
        response = await async_client.post("/chats", json=PHRASE)
        assert list(response.json().keys()) == ["code"]

    async def test_a_not_yet_started_grant_is_no_grant(self, async_client,
                                                       linked_firebase_identity,
                                                       _db_transaction):
        """`starts_at > evaluated_at`: the row exists, the entitlement has not begun."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id, starts_at=now + timedelta(days=1))

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_an_already_ended_grant_is_no_grant(self, async_client,
                                                      linked_firebase_identity,
                                                      _db_transaction):
        """`ends_at <= evaluated_at`: the row exists, the entitlement is over."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id,
                         starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1))

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    @pytest.mark.parametrize("status", [AccessGrantStatus.revoked, AccessGrantStatus.expired])
    async def test_a_grant_whose_status_is_not_active_is_no_grant(self, async_client,
                                                                  linked_firebase_identity,
                                                                  _db_transaction, status):
        """The predicate is `status == active`, never "not revoked" -- both terminal rows refuse."""
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id, status=status)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"


@pytest.mark.asyncio(loop_scope="module")
class TestASeededGrantIsAdmitted:
    """The positive control: the 429s above cannot be a route that refuses everyone."""

    async def test_a_seeded_grant_reaches_the_handler(self, async_client, quota_grant):
        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "ai"
        assert "response" in data["content"]


@pytest.mark.asyncio(loop_scope="module")
class TestTheAllowanceIsSpent:
    """§8.4 steps 2-5: the grant is not just *found*, it is charged -- and charged exactly once.

    Every case here reads `core.user_monthly_usage` back after the response, because the response
    alone cannot distinguish "admitted and charged" from "admitted for free", which is precisely
    the state the tracer left behind.
    """

    async def test_a_grant_at_its_allowance_is_exhausted(self, async_client,
                                                         linked_firebase_identity, _db_transaction):
        """`monthly_used == allowance` -- the exactly-touching case, not one past it."""
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id, monthly_used=ALLOWANCE)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_an_exhausted_grant_is_not_charged_for_the_request_it_refused(
            self, async_client, linked_firebase_identity, _db_transaction):
        """A rejection must not increment: a 429 that still spends is worse than no gate at all."""
        user, _ = linked_firebase_identity
        grant, _ = await seed_grant(_db_transaction, user_id=user.id, monthly_used=ALLOWANCE)

        await async_client.post("/chats", json=PHRASE)

        rows = await usage_rows(_db_transaction, grant.id)
        assert [row.monthly_used for row in rows] == [ALLOWANCE]

    async def test_one_below_the_allowance_is_admitted_and_commits_exactly_at_it(
            self, async_client, linked_firebase_identity, _db_transaction):
        """Adjacency, the other side: `allowance - 1` is admitted and lands on `allowance`."""
        user, _ = linked_firebase_identity
        grant, _ = await seed_grant(_db_transaction, user_id=user.id, monthly_used=ALLOWANCE - 1)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200

        rows = await usage_rows(_db_transaction, grant.id)
        assert [row.monthly_used for row in rows] == [ALLOWANCE]

    async def test_a_stale_period_rolls_over_before_the_allowance_is_compared(
            self, async_client, linked_firebase_identity, _db_transaction):
        """An exhausted row from *last* month must not refuse *this* month's first request.

        The stale period is derived from the current UTC month rather than hard-coded. A literal
        past month would read as stale forever, which is harmless, but the same habit applied to a
        literal *current* month silently stops testing anything the moment that month passes.
        """
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        stale_period = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        grant, _ = await seed_grant(_db_transaction, user_id=user.id,
                                    monthly_period=stale_period, monthly_used=ALLOWANCE)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200

        rows = await usage_rows(_db_transaction, grant.id)
        # 1, not `ALLOWANCE + 1`: the reset happens before the comparison and before the increment,
        # inside the same locked transaction, so the stale count is never carried forward.
        assert [(row.monthly_period, row.monthly_used) for row in rows] == [(now.strftime("%Y-%m"), 1)]


@pytest.mark.asyncio(loop_scope="module")
class TestTheEffectiveGrantStatement:
    """The lock and the order, which a served response cannot show (SHARED-INVARIANTS:33)."""

    async def test_the_statement_locks_the_rows_and_orders_ascending_by_grant_id(self):
        # Imported inside the test rather than at module scope: this is the only case here that
        # needs `GrantsDB`, and a module-scope import would turn every behavioural case above into
        # a collection error while the module is still being written.
        from nativespeaker.api.database import GrantsDB

        session = _StubSession()
        rows = await GrantsDB(session).lock_effective_grants(uuid7(), datetime.now(UTC))

        assert rows == []
        sql = str(session.statements[0])
        assert "FOR UPDATE" in sql
        assert "ORDER BY core.access_grants.id ASC" in sql
        # D-10: no row-count cap. The caller must be able to see a second effective grant rather
        # than have the database silently pick one for it.
        assert "LIMIT" not in sql


class _StubResult:
    def all(self):
        return []


class _StubSession:
    """Stands in for the short session `require_quota` opens, and keeps what it was asked to run."""

    def __init__(self):
        self.statements = []

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult()
