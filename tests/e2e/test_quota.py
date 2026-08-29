"""The quota gate on the two chat POSTs: refused without an effective grant, and charged exactly once."""
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER

from nativespeaker.api.tables import AccessGrantStatus, UserMonthlyUsage

from .conftest import seed_grant, seed_identity

pytestmark = pytest.mark.e2e

PHRASE = {"phrase": "I am going to home.", "lang": "en"}

# The registered tier's seeded allowance, named because every case below is expressed relative to it.
ALLOWANCE = 50

FOLLOWUP = {"message": "Can you explain more?"}

# The two gated routes as (path template, body); {chat_id} is filled from a chat the caller really owns.
QUOTA_ROUTES = [("/chats", PHRASE), ("/chats/{chat_id}", FOLLOWUP)]
QUOTA_ROUTE_IDS = ["create_chat", "send_message"]

# The other six routes; GET/DELETE on an unknown chat id answer 404, which is irrelevant to the counter.
UNCHARGED_ROUTES = [("GET", "/"),
                    ("GET", "/health/ready"),
                    ("GET", "/examples"),
                    ("GET", "/chats"),
                    ("GET", f"/chats/{uuid7()}"),
                    ("DELETE", f"/chats/{uuid7()}")]
UNCHARGED_ROUTE_IDS = ["root", "health_ready", "examples", "list_chats", "get_messages",
                       "delete_chat"]


async def usage_rows(factory, grant_id: UUID) -> list[UserMonthlyUsage]:
    """Read core.user_monthly_usage back for one grant through the test's own factory, never a fresh engine."""
    async with factory() as session:
        statement = select(UserMonthlyUsage).where(col(UserMonthlyUsage.grant_id) == grant_id)
        return list((await session.exec(statement)).all())


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("path, body", QUOTA_ROUTES, ids=QUOTA_ROUTE_IDS)
class TestNoEffectiveGrant:
    """An admitted caller with nothing to spend is refused 429, on both gated routes."""

    async def test_a_caller_with_no_grant_is_refused(self, async_client,
                                                     linked_firebase_identity, own_chat, path, body):
        response = await async_client.post(path.format(chat_id=own_chat), json=body)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_the_no_grant_refusal_carries_the_shared_error_body(
            self, async_client, linked_firebase_identity, own_chat, path, body):
        """The 429 is the shared `{code: ...}` shape -- not a 500, and not a bespoke payload."""
        response = await async_client.post(path.format(chat_id=own_chat), json=body)
        assert list(response.json().keys()) == ["code"]

    async def test_a_not_yet_started_grant_is_no_grant(self, async_client,
                                                       linked_firebase_identity,
                                                       _db_transaction, own_chat, path, body):
        """`starts_at > evaluated_at`: the row exists, the entitlement has not begun."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id, starts_at=now + timedelta(days=1))

        response = await async_client.post(path.format(chat_id=own_chat), json=body)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_an_already_ended_grant_is_no_grant(self, async_client,
                                                      linked_firebase_identity,
                                                      _db_transaction, own_chat, path, body):
        """`ends_at <= evaluated_at`: the row exists, the entitlement is over."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id,
                         starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1))

        response = await async_client.post(path.format(chat_id=own_chat), json=body)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    @pytest.mark.parametrize("status", [AccessGrantStatus.revoked, AccessGrantStatus.expired])
    async def test_a_grant_whose_status_is_not_active_is_no_grant(self, async_client,
                                                                  linked_firebase_identity,
                                                                  _db_transaction, own_chat,
                                                                  status, path, body):
        """The predicate is `status == active`, never "not revoked" -- both terminal rows refuse."""
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id, status=status)

        response = await async_client.post(path.format(chat_id=own_chat), json=body)
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

    async def test_the_follow_up_route_is_admitted_and_charged_exactly_once(
            self, async_client, quota_grant, _db_transaction):
        """The counter is read between the two POSTs, since [2] alone cannot say which route charged twice."""
        grant, _ = quota_grant

        create = await async_client.post("/chats", json=PHRASE)
        assert create.status_code == 200
        chat_id = create.json()["chat_id"]
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == [1]

        followup = await async_client.post(f"/chats/{chat_id}", json=FOLLOWUP)
        assert followup.status_code == 200
        assert followup.json()["chat_id"] == chat_id
        assert followup.json()["role"] == "ai"
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == [2]


@pytest.mark.asyncio(loop_scope="module")
class TestTheOtherSixRoutesConsumeNothing:
    """Exactly two of the eight routes are gated, so the other six must leave the counter untouched."""

    @pytest.mark.parametrize("method, path", UNCHARGED_ROUTES, ids=UNCHARGED_ROUTE_IDS)
    async def test_the_route_spends_no_credit(self, async_client, quota_grant, _db_transaction,
                                              method, path):
        grant, _ = quota_grant

        await async_client.request(method, path)

        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == [0]


@pytest.mark.asyncio(loop_scope="module")
class TestTheAllowanceIsSpent:
    """The grant is not just found but charged, and charged once, so every case reads the counter back."""

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

    async def test_a_stale_period_rollover_resets_before_the_allowance_is_compared(
            self, async_client, linked_firebase_identity, _db_transaction):
        """An exhausted row from last month must not refuse this month's first request."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        stale_period = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        grant, _ = await seed_grant(_db_transaction, user_id=user.id,
                                    monthly_period=stale_period, monthly_used=ALLOWANCE)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200

        rows = await usage_rows(_db_transaction, grant.id)
        # 1, not ALLOWANCE + 1: the reset happens before the comparison and the increment, in one transaction.
        assert [(row.monthly_period, row.monthly_used) for row in rows] == [(now.strftime("%Y-%m"), 1)]


@pytest.mark.asyncio(loop_scope="module")
class TestAGrantWithNoUsageRow:
    """A grant with no usage row answers 500 and mints nothing; only a seeded half-pair reaches the branch."""

    async def test_a_missing_usage_row_is_an_internal_error_not_a_free_allowance(
            self, async_client, linked_firebase_identity, _db_transaction):
        """500, not 200 and not 429: exhaustion and divergent state stay distinguishable."""
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id, with_usage=False)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 500
        assert response.json() == {"code": "internal_error"}

    async def test_the_missing_usage_row_is_still_missing_afterwards(
            self, async_client, linked_firebase_identity, _db_transaction):
        """Nothing is lazily minted: a convenience insert would hand out a fresh allowance and hide the break."""
        user, _ = linked_firebase_identity
        grant, _ = await seed_grant(_db_transaction, user_id=user.id, with_usage=False)

        await async_client.post("/chats", json=PHRASE)

        assert await usage_rows(_db_transaction, grant.id) == []


@pytest.mark.asyncio(loop_scope="module")
class TestThePredicateBoundaries:
    """The starts_at and ends_at boundaries, bracketed behaviourally from either side."""

    async def test_boundary_a_grant_that_started_a_moment_ago_is_effective(
            self, async_client, linked_firebase_identity, _db_transaction):
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id,
                         starts_at=datetime.now(UTC) - timedelta(seconds=1))

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200

    async def test_boundary_a_grant_that_starts_tomorrow_is_not_effective(
            self, async_client, linked_firebase_identity, _db_transaction):
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id,
                         starts_at=datetime.now(UTC) + timedelta(days=1))

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_boundary_a_grant_that_ended_a_moment_ago_is_not_effective(
            self, async_client, linked_firebase_identity, _db_transaction):
        """The upper bound is exclusive, so a grant is over the instant `ends_at` passes."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id,
                         starts_at=now - timedelta(days=1), ends_at=now - timedelta(seconds=1))

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_boundary_a_grant_that_ends_in_an_hour_is_still_effective(
            self, async_client, linked_firebase_identity, _db_transaction):
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id, ends_at=now + timedelta(hours=1))

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200

    async def test_boundary_an_open_ended_grant_is_effective(
            self, async_client, linked_firebase_identity, _db_transaction):
        """A NULL ends_at is legal, and the grant stays effective for as long as it has no end."""
        user, _ = linked_firebase_identity
        grant, _ = await seed_grant(_db_transaction, user_id=user.id, ends_at=None)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == [1]


@pytest.mark.asyncio(loop_scope="module")
class TestACorrectPhraseIsServedAndCharged:
    """A grammatically correct phrase is served and charged; it is the input that used to answer 500."""

    async def test_a_correct_phrase_returns_200_with_empty_issue_and_suggestion_lists(
            self, async_client, quota_grant):
        response = await async_client.post(
            "/chats", json={"phrase": "I am going home.", "lang": "en"})

        assert response.status_code == 200
        content = response.json()["content"]
        assert content["issues"] == []
        assert content["suggestions"] == []


@pytest.mark.asyncio(loop_scope="module")
class TestAMalformedRequestIsNotCharged:
    """A request the app itself refused must not spend a credit; each case reads monthly_used either side."""

    async def test_a_malformed_create_chat_body_is_not_charged(
            self, async_client, quota_grant, _db_transaction):
        """`POST /chats` with `phrase` omitted."""
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post("/chats", json={"lang": "en"})

        assert response.status_code == 422
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before

    async def test_a_malformed_follow_up_body_is_not_charged(
            self, async_client, quota_grant, _db_transaction):
        """`POST /chats/{chat_id}` with `message` omitted, on a well-formed chat id."""
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post(f"/chats/{uuid7()}", json={"note": "hello"})

        assert response.status_code == 422
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before

    async def test_a_malformed_chat_id_in_the_path_is_not_charged(
            self, async_client, quota_grant, _db_transaction):
        """The quota dependency must declare chat_id as well as body, or it commits before the path is rejected."""
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post("/chats/not-a-uuid", json=FOLLOWUP)

        assert response.status_code == 422
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before


@pytest.mark.asyncio(loop_scope="module")
class TestNoPreProviderRejectionIsCharged:
    """A request refused before any provider call costs nothing: five rejections across both gated routes."""

    async def test_an_unsupported_language_is_not_charged(
            self, async_client, quota_grant, _db_transaction):
        """lang is an unconstrained str, so this passes request validation and is refused by the service."""
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post("/chats", json={"phrase": "I am going to home.",
                                                           "lang": "zz"})

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before

    async def test_a_chat_that_does_not_exist_is_not_charged(
            self, async_client, quota_grant, _db_transaction):
        """An unknown chat id takes the same 404 branch another user's chat would, and charges nothing."""
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post(f"/chats/{uuid7()}", json=FOLLOWUP)

        assert response.status_code == 404
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before

    async def test_the_chat_history_limit_is_not_charged(
            self, async_client, quota_grant, _db_transaction, _app_lifespan):
        """The limit is driven to zero rather than seeded up to, since the subject is the counter."""
        grant, _ = quota_grant
        original = _app_lifespan.state.config.chats_limit
        _app_lifespan.state.config.chats_limit = 0
        try:
            before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

            response = await async_client.post("/chats", json=PHRASE)

            assert response.status_code == 400
            assert [row.monthly_used
                    for row in await usage_rows(_db_transaction, grant.id)] == before
        finally:
            _app_lifespan.state.config.chats_limit = original

    async def test_the_message_history_limit_is_not_charged(
            self, async_client, quota_grant, _db_transaction, _app_lifespan):
        """The chat is created first and legitimately charges one, so the refused follow-up must add nothing."""
        grant, _ = quota_grant

        create = await async_client.post("/chats", json=PHRASE)
        assert create.status_code == 200
        chat_id = create.json()["chat_id"]
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]
        assert before == [1]

        original = _app_lifespan.state.config.messages_limit
        _app_lifespan.state.config.messages_limit = 0
        try:
            response = await async_client.post(f"/chats/{chat_id}", json=FOLLOWUP)

            assert response.status_code == 400
            assert [row.monthly_used
                    for row in await usage_rows(_db_transaction, grant.id)] == before
        finally:
            _app_lifespan.state.config.messages_limit = original

    async def test_an_open_circuit_is_not_charged(
            self, async_client, quota_grant, _db_transaction, _app_lifespan):
        """The breaker is opened directly, since the subject is what an open circuit costs, not the threshold."""
        grant, _ = quota_grant
        breaker = _app_lifespan.state.llm_service.policy._circuit_breaker
        breaker._opened_at = time.monotonic()
        try:
            before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

            response = await async_client.post("/chats", json=PHRASE)

            assert response.status_code == 503
            assert response.json()["code"] == "service_unavailable"
            assert [row.monthly_used
                    for row in await usage_rows(_db_transaction, grant.id)] == before
        finally:
            breaker._opened_at = None
            breaker._failure_count = 0


@pytest.mark.asyncio(loop_scope="module")
class TestOneUsersGrantIsNotAnothers:
    """The effective-grant predicate is scoped to the caller, proven with a second grant holder present."""

    async def test_a_second_users_active_grant_is_neither_read_nor_charged(
            self, async_client, quota_grant, _db_transaction):
        own_grant, _ = quota_grant
        stranger, _ = await seed_identity(_db_transaction,
                                          issuer=TEST_ISSUER,
                                          subject="quota-scope-stranger")
        stranger_grant, _ = await seed_grant(_db_transaction, user_id=stranger.id)

        response = await async_client.post("/chats", json=PHRASE)

        # A 500 means the predicate lost its scope; a 200 with the wrong counter means it matched the wrong grant.
        assert response.status_code == 200
        assert [row.monthly_used for row in await usage_rows(_db_transaction, own_grant.id)] == [1]
        assert [row.monthly_used
                for row in await usage_rows(_db_transaction, stranger_grant.id)] == [0]


@pytest.mark.asyncio(loop_scope="module")
class TestTheEffectiveGrantStatement:
    """The lock and the order, which a served response cannot show (SHARED-INVARIANTS:33)."""

    async def test_the_statement_locks_the_rows_and_orders_ascending_by_grant_id(self):
        # Imported inside the test: this is the only case here that needs GrantsDB.
        from nativespeaker.api.crud import GrantsDB

        session = _StubSession()
        rows = await GrantsDB(session).lock_effective_grants(uuid7(), datetime.now(UTC))

        assert rows == []
        sql = str(session.statements[0])
        assert "FOR UPDATE" in sql
        assert "ORDER BY core.access_grants.id ASC" in sql
        # The tenant scope: the stub session ignores WHERE, so only the compiled text can show the term is there.
        assert "core.access_grants.user_id = " in sql
        assert "core.access_grants.status = " in sql
        # No row-count cap: a second effective grant must be visible rather than silently picked over.
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
