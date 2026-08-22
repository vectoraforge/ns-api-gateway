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

Both chat POSTs are gated, and only those two of the eight pre-existing routes (D-07). The
refusal cases run against both, and `TestTheOtherSixRoutesConsumeNothing` is the other half of
that claim -- without it, "these two are checked" is consistent with "all eight are".
"""
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy import func
from sqlmodel import col, select

from nativespeaker.api.models import AccessGrantStatus, UserMonthlyUsage
from nativespeaker.api.models.auth import AuthEvent

from .conftest import seed_grant

pytestmark = pytest.mark.e2e

PHRASE = {"phrase": "I am going to home.", "lang": "en"}

# The `registered` tier's seeded allowance (migrations/20260818_01_initial-release.sql:280-283).
# Named rather than repeated as a literal, because every arithmetic case below is expressed
# relative to it -- "at the allowance", "one below" -- and a bare 50 hides which of those a case
# means.
ALLOWANCE = 50

FOLLOWUP = {"message": "Can you explain more?"}

# The two quota-checked routes as `(path, body)`, fixed at collection time. The follow-up entry
# deliberately names a chat that does not exist: the quota dependency is a DECORATOR dependency and
# completes before the handler body, so a caller with no effective grant is refused 429 and the chat
# is never looked up. A 404 from any case below would mean the gate ran late, or not at all.
QUOTA_ROUTES = [("/chats", PHRASE), (f"/chats/{uuid7()}", FOLLOWUP)]
QUOTA_ROUTE_IDS = ["create_chat", "send_message"]

# The other six of the eight pre-existing routes (D-07). `GET`/`DELETE` on a chat id that does not
# exist answer 404 -- irrelevant here, because the subject of those cases is the counter, not the
# status.
UNCHARGED_ROUTES = [("GET", "/"),
                    ("GET", "/health/ready"),
                    ("GET", "/examples"),
                    ("GET", "/chats"),
                    ("GET", f"/chats/{uuid7()}"),
                    ("DELETE", f"/chats/{uuid7()}")]
UNCHARGED_ROUTE_IDS = ["root", "health_ready", "examples", "list_chats", "get_messages",
                       "delete_chat"]


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


async def auth_event_count(factory) -> int:
    """`audit.auth_events` row count, read through the same swapped factory as everything else.

    Same form as `test_audit_writer.py::row_count`, and deliberately a copy rather than an import:
    that module builds its own app with its own registry to reach the audited path at all, and
    importing from it would drag that fixture graph into a module whose subject is the quota gate.
    """
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(AuthEvent))


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("path, body", QUOTA_ROUTES, ids=QUOTA_ROUTE_IDS)
class TestNoEffectiveGrant:
    """An admitted caller with nothing to spend. §8.4 step 1 routes this to the 429 contract.

    Every case runs against **both** quota-checked POSTs. Parametrized rather than duplicated so a
    third gated route is one list entry away from being covered by all of them -- and so a route
    that carries the flag but lost its wrapper cannot pass here by being tested only on the other
    one.
    """

    async def test_a_caller_with_no_grant_is_refused(self, async_client,
                                                     linked_firebase_identity, path, body):
        response = await async_client.post(path, json=body)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_the_no_grant_refusal_carries_the_shared_error_body(
            self, async_client, linked_firebase_identity, path, body):
        """The 429 is the shared `{code: ...}` shape -- not a 500, and not a bespoke payload."""
        response = await async_client.post(path, json=body)
        assert list(response.json().keys()) == ["code"]

    async def test_a_not_yet_started_grant_is_no_grant(self, async_client,
                                                       linked_firebase_identity,
                                                       _db_transaction, path, body):
        """`starts_at > evaluated_at`: the row exists, the entitlement has not begun."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id, starts_at=now + timedelta(days=1))

        response = await async_client.post(path, json=body)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    async def test_an_already_ended_grant_is_no_grant(self, async_client,
                                                      linked_firebase_identity,
                                                      _db_transaction, path, body):
        """`ends_at <= evaluated_at`: the row exists, the entitlement is over."""
        user, _ = linked_firebase_identity
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id,
                         starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1))

        response = await async_client.post(path, json=body)
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    @pytest.mark.parametrize("status", [AccessGrantStatus.revoked, AccessGrantStatus.expired])
    async def test_a_grant_whose_status_is_not_active_is_no_grant(self, async_client,
                                                                  linked_firebase_identity,
                                                                  _db_transaction, status,
                                                                  path, body):
        """The predicate is `status == active`, never "not revoked" -- both terminal rows refuse."""
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id, status=status)

        response = await async_client.post(path, json=body)
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
        """The second gated route, driven against a chat that really exists.

        The counter is read between the two POSTs, not only at the end. `[2]` alone is consistent
        with a follow-up that charged twice and a create that charged nothing, which is precisely
        the mix-up a single trailing read cannot tell apart.
        """
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
    """D-07: exactly two of the eight pre-existing routes are quota-checked, and these are not.

    The backstop to every case above. "Both POSTs are gated" is equally true of an app that gates
    all eight, and gating a read would charge a user for looking at what they already paid for.
    The counter is read back with a grant seeded, so a charge would be visible rather than
    swallowed by a 429 the case never asserted against.
    """

    @pytest.mark.parametrize("method, path", UNCHARGED_ROUTES, ids=UNCHARGED_ROUTE_IDS)
    async def test_the_route_spends_no_credit(self, async_client, quota_grant, _db_transaction,
                                              method, path):
        grant, _ = quota_grant

        await async_client.request(method, path)

        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == [0]


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

    async def test_a_stale_period_rollover_resets_before_the_allowance_is_compared(
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
class TestAGrantWithNoUsageRow:
    """D-09 over the real transport: a broken invariant answers 500, and nothing is minted.

    `src/` cannot reach this state -- no route writes either table -- so the only way to observe
    the branch is to seed the half-written pair a failed Phase 41/42/45 transaction would leave.
    """

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
        """The never-lazily-mint rule, read back rather than argued.

        A convenience insert on this path would hand out a fresh allowance every time the
        invariant broke -- and would hide the break while doing it.
        """
        user, _ = linked_firebase_identity
        grant, _ = await seed_grant(_db_transaction, user_id=user.id, with_usage=False)

        await async_client.post("/chats", json=PHRASE)

        assert await usage_rows(_db_transaction, grant.id) == []


@pytest.mark.asyncio(loop_scope="module")
class TestThePredicateBoundaries:
    """REBIND-05's `starts_at`/`ends_at` boundaries, bracketed from both sides.

    The exactly-equal instants -- `starts_at == evaluated_at` and `ends_at == evaluated_at` -- are
    not reachable from here: the client cannot name the instant the barrier captures. They are
    asserted against the compiled predicate in
    `tests/unit/test_quota_resolver.py::TestTheLockingStatements`. What these cases add is the
    behavioural bracket either side of each boundary, which is what says the compiled predicate is
    the one actually running.
    """

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
        """Ruling 9.11: a NULL `ends_at` is legal, and effective for as long as the grant is."""
        user, _ = linked_firebase_identity
        grant, _ = await seed_grant(_db_transaction, user_id=user.id, ends_at=None)

        response = await async_client.post("/chats", json=PHRASE)
        assert response.status_code == 200
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == [1]


@pytest.mark.asyncio(loop_scope="module")
class TestACorrectPhraseIsServedAndCharged:
    """The D-12 half of REBIND-06, over the real transport rather than at the model.

    A grammatically correct phrase is exactly the input that made the product's primary route
    answer 500 (D-35-11-A): the unconstrained chain returns only `resolved_mode` and `response`,
    and `AnalyzeResponse` had no defaults for the two lists. It is also the input a user gets when
    their sentence is already right -- so under D-11 the 500 burned a credit for a request that
    was never served.
    """

    async def test_a_correct_phrase_returns_200_with_empty_issue_and_suggestion_lists(
            self, async_client, quota_grant):
        response = await async_client.post(
            "/chats", json={"phrase": "I am going home.", "lang": "en"})

        assert response.status_code == 200
        content = response.json()["content"]
        assert content["issues"] == []
        assert content["suggestions"] == []


@pytest.mark.asyncio(loop_scope="module")
class TestAQuotaRejectionWritesNoAuditRow:
    """REBIND-02 on the phase's new code path: a quota 429 writes nothing to `audit.auth_events`.

    True by construction -- audited-path entry is gated solely on `meta.operation is not None`
    (`auth/barrier.py:170-180`), all eight registry entries leave `operation` at its `None` default,
    and the quota path never touches `AuditWriter`. Asserted anyway, because ROADMAP criterion 3's
    "including on barrier rejection" leaves the *quota* rejection -- which is not a barrier
    rejection, and is the one rejection this phase invented -- otherwise unproven on these routes.

    The counter is read before and after rather than asserted against zero, so the case keeps
    working if a future fixture ever seeds an unrelated row.
    """

    @pytest.mark.parametrize("path, body", QUOTA_ROUTES, ids=QUOTA_ROUTE_IDS)
    async def test_a_quota_429_writes_no_audit_row(self, async_client, linked_firebase_identity,
                                                   _db_transaction, path, body):
        before = await auth_event_count(_db_transaction)

        response = await async_client.post(path, json=body)

        assert response.status_code == 429
        assert await auth_event_count(_db_transaction) == before

    async def test_an_admitted_and_charged_request_writes_no_audit_row_either(
            self, async_client, quota_grant, _db_transaction):
        """The served outcome, not only the refused one -- REBIND-02 says "no row, ever"."""
        before = await auth_event_count(_db_transaction)

        response = await async_client.post("/chats", json=PHRASE)

        assert response.status_code == 200
        assert await auth_event_count(_db_transaction) == before


@pytest.mark.asyncio(loop_scope="module")
class TestAMalformedRequestIsNotCharged:
    """D-14 over the real transport: a request the app itself refused must not spend a credit.

    All three shapes below are ones the suite already sends elsewhere -- `{"lang": "en"}` to
    `POST /chats` in `test_error_cases.py::test_missing_phrase_returns_422` and
    `test_chats.py::test_the_refusal_precedes_body_validation`, and a follow-up with the wrong body
    on `POST /chats/{chat_id}`. Without D-14 every one of them would 422 **and** silently burn a
    credit: D-04 has the quota dependency commit in a session of its own, so without the wrapper
    declaring the route's path and body parameters that commit runs ahead of validation. That is a
    regression against v1.6, whose yield-dependency rolled the increment back, and this class is the
    thing that stops it coming back.

    Each case reads `monthly_used` **before and after**. Reading only afterwards would assert that
    the seed value is still whatever it was seeded to, which is not the same claim.
    """

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
        """`POST /chats/not-a-uuid` with a perfectly good body.

        This is the case that makes `require_quota_send_message` declare `chat_id` as well as
        `body`. A wrapper that declared only the body would validate the body, pass, commit its
        increment, and only then have FastAPI reject the path segment -- so a client with a broken
        chat id would drain a paying user's allowance one 422 at a time.
        """
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post("/chats/not-a-uuid", json=FOLLOWUP)

        assert response.status_code == 422
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before


@pytest.mark.asyncio(loop_scope="module")
class TestNoPreProviderRejectionIsCharged:
    """REBIND-06 / ROADMAP SC1: a request the app refused before calling the provider costs nothing.

    `TestAMalformedRequestIsNotCharged` above covers the rejections FastAPI performs *while solving
    the dependency* -- a 422 from a bad body or path segment. This class covers the rest of the
    class of failure, and it is a strictly larger set: every rejection the app reaches on its own,
    after admission and before a single token is sent to the provider.

    There are five, spread across both gated routes and three layers -- request validation
    (`lang`), the service's own business rules (both history limits, chat ownership), and the
    resilience layer's local backpressure (circuit open, queue full). What makes them one case
    rather than five is that they share a cause: consumption committing in its own session before
    the work is known to be reachable. Fixing them one at a time is how two of them stayed live
    after the first three were found.

    D-11's accepted loss is narrower than this and stays intact: a credit spent on a request that
    *did* reach the provider and failed there is not refunded. Backpressure is not a provider
    failure -- it is this service declining to make the call -- and a 503 carrying `Retry-After`
    that also spends a credit invites the client to pay again for the same refusal.

    Every case reads `monthly_used` before and after, for the reason the D-14 class gives.
    """

    async def test_an_unsupported_language_is_not_charged(
            self, async_client, quota_grant, _db_transaction):
        """`POST /chats` with a well-formed body naming a language the service does not support.

        `ChatRequest.lang` is unconstrained `str | None`, so this passes request validation and is
        refused by `ChatService.create_chat` instead -- after the commit, under the old wiring.
        """
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post("/chats", json={"phrase": "I am going to home.",
                                                           "lang": "zz"})

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before

    async def test_a_chat_that_does_not_exist_is_not_charged(
            self, async_client, quota_grant, _db_transaction):
        """`POST /chats/{unknown}` with a perfectly good body.

        The ownership filter is `ChatsDB.get_chat(chat_id, user_id)`, so this is also the shape a
        caller reaching for *another user's* chat takes: both answer 404 from the same branch.
        """
        grant, _ = quota_grant
        before = [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)]

        response = await async_client.post(f"/chats/{uuid7()}", json=FOLLOWUP)

        assert response.status_code == 404
        assert [row.monthly_used for row in await usage_rows(_db_transaction, grant.id)] == before

    async def test_the_chat_history_limit_is_not_charged(
            self, async_client, quota_grant, _db_transaction, _app_lifespan):
        """`POST /chats` when the caller is already at `chats_limit`.

        The limit is driven to zero rather than seeded up to: the subject is the counter, not the
        limit's arithmetic, and fifty seeded chats would make this the slowest case in the package
        while proving exactly the same thing.
        """
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
        """`POST /chats/{chat_id}` on a real chat that is already at `messages_limit`.

        The chat is created first, which legitimately spends one credit -- so the assertion is that
        the *refused follow-up* adds nothing to it, not that the counter is still zero.
        """
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
        """`POST /chats` while the breaker is open.

        The breaker is opened directly rather than by driving real failures through the provider:
        the subject is what an open circuit costs the caller, not the threshold that opens it, and
        `CircuitBreaker` records the open instant on `_opened_at` with no other state involved.

        This is the worst of the five. The breaker stays open for `circuit_breaker_reset_seconds`,
        so under the old wiring every request in that window paid for its own refusal -- and the
        503 carries `Retry-After`, telling the client to come back and do it again.
        """
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
