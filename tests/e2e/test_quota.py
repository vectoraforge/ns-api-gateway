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
from uuid import uuid7

import pytest

from nativespeaker.api.models import AccessGrantStatus

from .conftest import seed_grant

pytestmark = pytest.mark.e2e

PHRASE = {"phrase": "I am going to home.", "lang": "en"}


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
