"""Restores raced, capped and interrupted on two connections against real PostgreSQL."""
import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import Update, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.crud.subscriptions import SubscriptionsDB
from nativespeaker.api.errors import AppError, RestoreTransferRejected
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.services.restore import RestoreService
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus, User
from schema.test_claim_race import _RacingSession, read, scalar

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# The month the cap writes for `NOW`, spelled out rather than derived, so the case pins the value.
THIS_MONTH = date(2026, 8, 1)

# The tier the migration seeds for a paid subscription, and the one this test's proof names.
TIER_ID = "paid"

_A_MONTH = timedelta(days=30)

# Bounded so a partner that fails before its update shows up as a failure rather than as a hung suite.
BARRIER_TIMEOUT_SECONDS = 20

# The seam is scripted, so the artifact's content is never parsed and its value never matters.
RESTORE_PROOF = "a-signed-transaction-the-scripted-seam-accepts"

# The Play branch is never taken here: every attempt of this file names Apple.
PACKAGE_NAME = "com.nativespeaker.app"


class _Interrupted(Exception):
    """Raised inside the recording session to stop one restore at its commit, and nowhere else."""


@dataclass
class _Harness:
    engine: object
    factory: async_sessionmaker
    external_id: str
    user_ids: list[uuid.UUID]


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """A committing session factory plus this test's private lifecycle key and its accounts."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    private = uuid.uuid4().hex[:10]
    subject = _Harness(engine=engine,
                       factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                  expire_on_commit=False),
                       external_id=f"restore-{private}",
                       user_ids=[])
    try:
        yield subject
    finally:
        try:
            await clean_up(subject)
        finally:
            await engine.dispose()


async def clean_up(harness: _Harness) -> None:
    """Child-first: usage, then grants, then the purchase and subscription rows, then the users."""
    keys = {"lifecycle": f"{harness.external_id}%"}
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        # Ahead of the subscriptions they point at, unlike the ingestion analog, which writes neither.
        for user_id in harness.user_ids:
            for statement in (
                    "DELETE FROM core.user_monthly_usage WHERE grant_id IN "
                    "(SELECT id FROM core.access_grants WHERE user_id = :id)",
                    "DELETE FROM core.access_grants WHERE user_id = :id"):
                await conn.execute(text(statement), {"id": user_id})

        for statement in ("DELETE FROM core.store_purchases WHERE external_id LIKE :lifecycle",
                          "DELETE FROM core.subscriptions WHERE external_id LIKE :lifecycle"):
            await conn.execute(text(statement), keys)

        # Last: core.access_grants references core.users, so every grant above is gone by now.
        for user_id in harness.user_ids:
            await conn.execute(text("DELETE FROM core.users WHERE id = :id"), {"id": user_id})


class _RecordingSession(_RacingSession):
    """The claim race's session, plus the SQLSTATE its violation carried at either boundary."""

    def __init__(self, session, before_first_update=None, before_first_commit=None) -> None:
        super().__init__(session, None, before_first_commit)
        self._before_first_update = before_first_update
        self.updates = 0
        self.sqlstate: str | None = None

    async def exec(self, statement, *args, **kwargs):
        """Hold at the door of the conditional owner UPDATE, which is the only arbiter of a race."""
        if isinstance(statement, Update):
            self.updates += 1
            if self.updates == 1 and self._before_first_update is not None:
                hook, self._before_first_update = self._before_first_update, None
                await hook()
        return await self._session.exec(statement, *args, **kwargs)

    async def flush(self, *args, **kwargs):
        try:
            return await super().flush(*args, **kwargs)
        except IntegrityError as violation:
            # The classification is the SQLSTATE alone; nothing here reads a message or an index.
            self.sqlstate = violation.orig.sqlstate
            raise

    async def commit(self, *args, **kwargs):
        try:
            return await super().commit(*args, **kwargs)
        except IntegrityError as violation:
            # The deferred foreign keys are checked here, so a recorder wrapping flush alone is blind.
            self.sqlstate = violation.orig.sqlstate
            raise


@dataclass
class _Attempt:
    """One restore's caller and everything observable about what it did."""

    name: str
    user_id: uuid.UUID
    # What the call produced: nothing when it committed, or the rejection it raised.
    result: AppError | None = None
    owner_seen_at_barrier: uuid.UUID | None = None
    rows_seen_at_barrier: int | None = None
    sqlstate: str | None = None
    integrity_at_flush: bool = False
    integrity_at_commit: bool = False
    # Every write the writer emits goes through one of these, so zero means the attempt wrote nothing.
    flushes: int = 0


def role_of(attempt: _Attempt) -> str:
    """The bucket an attempt lands in: the one that committed, and the one the UPDATE refused."""
    return "won" if attempt.result is None else "lost"


def status_of(attempt: _Attempt) -> int:
    """The status the route would have answered: a completed restore is a 200."""
    return attempt.result.status if isinstance(attempt.result, AppError) else 200


class _ScriptedAppStore:
    """The Apple seam, answering one proof: this suite verifies no artifact and reaches no network."""

    def __init__(self, proof: RestoredSubscription) -> None:
        self.proof = proof

    def verify_transaction(self, signed_transaction: str,
                           evaluated_at: datetime) -> RestoredSubscription:
        return self.proof


def proof_for(harness: _Harness) -> RestoredSubscription:
    """One verified proof for this test's lifecycle key, shared so every attempt sees one term."""
    # One term for one subscription, as a store reports it: a re-read never moves the expiry.
    return RestoredSubscription(provider=PurchaseProvider.apple,
                                external_id=harness.external_id,
                                product_id="com.nativespeaker.subscription.monthly",
                                tier_id=TIER_ID,
                                attribution_token=None,
                                status=SubscriptionStatus.active,
                                purchased_at=NOW - _A_MONTH,
                                expires_at=NOW + _A_MONTH,
                                grace_period_expires_at=None)


async def commit_account(harness: _Harness) -> uuid.UUID:
    """One core.users row, committed, because each attempt reads it on its own connection."""
    user_id = uuid.uuid4()
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(text("INSERT INTO core.users (id) VALUES (:id)"), {"id": user_id})
    harness.user_ids.append(user_id)
    return user_id


async def commit_subscription(harness: _Harness, *, user_id: uuid.UUID | None = None,
                              transfer_month: date | None = None) -> uuid.UUID:
    """One canonical row on this test's lifecycle key, committed for the attempts to read."""
    subscription_id = uuid.uuid4()
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            # The two enum columns are cast in the statement: a bound parameter arrives as text.
            text("INSERT INTO core.subscriptions"
                 " (id, user_id, provider, external_id, tier_id, status,"
                 "  last_cross_account_transfer_month, created_at, updated_at)"
                 " VALUES (:id, :user_id, CAST(:provider AS core.subscription_provider),"
                 "         :external_id, :tier_id, CAST('active' AS core.subscription_status),"
                 "         CAST(:transfer_month AS DATE), :now, :now)"),
            {"id": subscription_id, "user_id": user_id, "provider": str(PurchaseProvider.apple),
             "external_id": harness.external_id, "tier_id": TIER_ID,
             "transfer_month": transfer_month, "now": NOW})
    return subscription_id


def identity_of(user_id: uuid.UUID) -> Identity:
    """The admitted caller the route hands the service, carrying nothing but the account it resolved."""
    return Identity(issuer="ns-restore-race", subject=str(user_id), user=User(id=user_id))


async def run_attempt(harness: _Harness, attempt: _Attempt, proof: RestoredSubscription,
                      before_first_update=None, before_first_commit=None) -> _Attempt:
    """Drive the production restore once, on its own session and connection, as one request does."""
    async with harness.factory() as real_session:
        session = _RecordingSession(real_session, before_first_update, before_first_commit)
        service = RestoreService(db=session, evaluated_at=NOW,
                                 app_store=_ScriptedAppStore(proof),
                                 # Never read: every attempt of this file names the Apple store.
                                 play=None, package_name=PACKAGE_NAME)
        try:
            await service.restore(identity_of(attempt.user_id), PurchaseProvider.apple,
                                  RESTORE_PROOF)
        except AppError as rejection:
            attempt.result = rejection
        attempt.sqlstate = session.sqlstate
        attempt.integrity_at_flush = session.integrity_at_flush
        attempt.integrity_at_commit = session.integrity_at_commit
        attempt.flushes = session.flushes
    return attempt


async def owner_of(harness: _Harness, subscription_id: uuid.UUID) -> tuple:
    """The three columns of the canonical row a restore can write, read on a connection of its own."""
    rows = await read(harness,
                      "SELECT user_id, last_cross_account_transfer_month, restore_bound_user_id"
                      " FROM core.subscriptions WHERE id = :id", {"id": subscription_id})
    return tuple(rows[0])


async def grants_of(harness: _Harness, user_id: uuid.UUID) -> list[tuple]:
    """Every grant of one account with the fields a restore rewrites, and its own usage counter."""
    return [tuple(row) for row in await read(
        harness,
        "SELECT g.id, g.status, g.ends_at, g.tier_id, g.subscription_id, u.monthly_used"
        " FROM core.access_grants g"
        " LEFT JOIN core.user_monthly_usage u ON u.grant_id = g.id"
        " WHERE g.user_id = :id ORDER BY g.id", {"id": user_id})]


async def committed_grants(harness: _Harness, subscription_id: uuid.UUID) -> int:
    """Committed grant rows for one subscription, whatever account holds them."""
    return await scalar(harness,
                        "SELECT count(*) FROM core.access_grants WHERE subscription_id = :id",
                        {"id": subscription_id})


async def state_of(harness: _Harness, subscription_id: uuid.UUID,
                   *user_ids: uuid.UUID) -> tuple:
    """The whole committed picture a second move must leave exactly as it found it."""
    return (await owner_of(harness, subscription_id),
            *[await grants_of(harness, user_id) for user_id in user_ids])


def barrier_for(harness: _Harness, attempt: _Attempt, subscription_id: uuid.UUID,
                mine: asyncio.Event, theirs: asyncio.Event):
    """Announce that this restore has read the subscription row, then wait for its partner."""

    async def hold() -> None:
        rows = await read(harness, "SELECT user_id FROM core.subscriptions WHERE id = :id",
                          {"id": subscription_id})
        attempt.rows_seen_at_barrier = len(rows)
        attempt.owner_seen_at_barrier = rows[0][0] if rows else None
        mine.set()
        await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)

    return hold


async def race(harness: _Harness, subscription_id: uuid.UUID, proof: RestoredSubscription,
               first: _Attempt, second: _Attempt) -> dict:
    """Release two restores together, each held at its owner UPDATE until both have read the row."""
    first_ready, second_ready = asyncio.Event(), asyncio.Event()
    await asyncio.gather(
        run_attempt(harness, first, proof,
                    barrier_for(harness, first, subscription_id, first_ready, second_ready)),
        run_attempt(harness, second, proof,
                    barrier_for(harness, second, subscription_id, second_ready, first_ready)))
    return {"attempts": (first, second),
            "by_role": {role_of(attempt): attempt for attempt in (first, second)}}


@pytest.mark.asyncio
class TestTwoAdoptersOfOneSubscriptionCommitOneGrant:
    """T-45-09, D-08. The conditional UPDATE is the only arbiter; the unique index is the backstop."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two accounts adopting one unowned subscription, released together at the owner UPDATE."""
        subscription_id = await commit_subscription(harness)
        proof = proof_for(harness)
        first = _Attempt(name="first", user_id=await commit_account(harness))
        second = _Attempt(name="second", user_id=await commit_account(harness))
        raced = await race(harness, subscription_id, proof, first, second)
        return {**raced, "subscription_id": subscription_id}

    async def test_both_restores_read_the_row_unowned_before_either_claimed_it(self, raced):
        """The premise: without it the case could be an adoption and its repeat, and the rest vacuous."""
        assert [attempt.rows_seen_at_barrier for attempt in raced["attempts"]] == [1, 1]
        assert [attempt.owner_seen_at_barrier for attempt in raced["attempts"]] == [None, None]

    async def test_exactly_one_restore_lost_the_race(self, raced):
        assert set(raced["by_role"]) == {"won", "lost"}

    async def test_exactly_one_grant_is_committed_for_the_raced_subscription(self, harness, raced):
        """Two rows would mean no arbitration; zero would mean both attempts rolled back."""
        assert await committed_grants(harness, raced["subscription_id"]) == 1

    async def test_the_winner_owns_the_row_and_answers_two_hundred(self, harness, raced):
        winner = raced["by_role"]["won"]
        assert status_of(winner) == 200
        owner, month, bound = await owner_of(harness, raced["subscription_id"])
        assert owner == winner.user_id
        # Adoption spends none of D-10's cap, and D-10 replaces the binding column entirely.
        assert (month, bound) == (None, None)

    async def test_the_loser_wrote_nothing_at_all(self, harness, raced):
        """Zero flushes is the writer's own witness: every row it writes goes through one."""
        loser = raced["by_role"]["lost"]
        assert loser.flushes == 0
        assert await grants_of(harness, loser.user_id) == []

    async def test_the_loser_answers_what_the_winners_state_earns_and_never_a_five_hundred(
            self, raced):
        """D-08: the losing arm re-reads and answers as the winner left it, which is a refusal here."""
        loser = raced["by_role"]["lost"]
        assert 400 <= status_of(loser) < 500
        assert status_of(loser) == 404

    async def test_any_violation_the_loser_saw_was_the_unique_one(self, raced):
        """42-07: 23505 is the only integrity code a lost race may carry, and none is also correct."""
        loser = raced["by_role"]["lost"]
        assert loser.sqlstate in (None, "23505")
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (False, False)


@pytest.mark.asyncio
class TestTheSecondMoveOfOneMonthWritesNothing:
    """D-10, T-45-10. The cap is per subscription, and it refuses before any lock is taken."""

    @pytest_asyncio.fixture
    async def moved(self, harness):
        """One subscription adopted, then moved once, so the cap is already spent for this month."""
        subscription_id = await commit_subscription(harness)
        proof = proof_for(harness)
        owner = await commit_account(harness)
        mover = await commit_account(harness)
        third = await commit_account(harness)
        await run_attempt(harness, _Attempt(name="adopt", user_id=owner), proof)
        moved = await run_attempt(harness, _Attempt(name="move", user_id=mover), proof)
        assert status_of(moved) == 200
        return {"subscription_id": subscription_id, "proof": proof,
                "accounts": (owner, mover, third)}

    async def test_the_first_move_left_the_subscription_with_the_mover_and_spent_the_month(
            self, harness, moved):
        """The premise: a first move that wrote nothing would make every case below vacuous."""
        owner, mover, _ = moved["accounts"]
        assert await owner_of(harness, moved["subscription_id"]) == (mover, THIS_MONTH, None)
        assert [row[1] for row in await grants_of(harness, owner)] == ["expired"]
        assert [row[1] for row in await grants_of(harness, mover)] == ["active"]

    async def test_a_second_move_in_the_same_month_answers_the_conflict(self, harness, moved):
        _, _, third = moved["accounts"]

        refused = await run_attempt(harness, _Attempt(name="second-move", user_id=third),
                                    moved["proof"])

        assert status_of(refused) == 409
        assert type(refused.result) is RestoreTransferRejected
        assert refused.result.code == "restore_transfer_rejected"

    async def test_the_refused_move_changed_neither_account_nor_the_row(self, harness, moved):
        owner, mover, third = moved["accounts"]
        before = await state_of(harness, moved["subscription_id"], owner, mover, third)

        refused = await run_attempt(harness, _Attempt(name="second-move", user_id=third),
                                    moved["proof"])

        assert status_of(refused) == 409
        # Zero flushes and an unchanged picture: the cap refuses ahead of every lock and every write.
        assert refused.flushes == 0
        assert await state_of(harness, moved["subscription_id"], owner, mover, third) == before


@pytest.mark.asyncio
class TestARestoreInterruptedAtItsCommitChangesNothing:
    """SHARED-INVARIANTS: one transaction, so a move that does not reach COMMIT is not a partial move."""

    @pytest_asyncio.fixture
    async def interrupted(self, harness):
        """One adopted subscription, then a move stopped at the door of its commit."""
        subscription_id = await commit_subscription(harness)
        proof = proof_for(harness)
        owner = await commit_account(harness)
        mover = await commit_account(harness)
        await run_attempt(harness, _Attempt(name="adopt", user_id=owner), proof)
        before = await state_of(harness, subscription_id, owner, mover)

        async def interrupt() -> None:
            raise _Interrupted

        with pytest.raises(_Interrupted):
            await run_attempt(harness, _Attempt(name="move", user_id=mover), proof,
                              before_first_commit=interrupt)
        return {"subscription_id": subscription_id, "before": before,
                "accounts": (owner, mover)}

    async def test_the_subscription_still_names_the_account_that_adopted_it(self, harness,
                                                                           interrupted):
        owner, _ = interrupted["accounts"]
        assert await owner_of(harness, interrupted["subscription_id"]) == (owner, None, None)

    async def test_no_grant_of_either_account_changed_and_none_was_added(self, harness,
                                                                        interrupted):
        owner, mover = interrupted["accounts"]
        assert await state_of(harness, interrupted["subscription_id"],
                              owner, mover) == interrupted["before"]
        assert await committed_grants(harness, interrupted["subscription_id"]) == 1

    async def test_the_account_it_would_have_moved_to_holds_nothing(self, harness, interrupted):
        """The control: the move had really got as far as its commit, so this is a rollback."""
        _, mover = interrupted["accounts"]
        assert await grants_of(harness, mover) == []


@pytest.mark.asyncio
class TestTheDeferredForeignKeysFireAtCommitAndNotAtAFlush:
    """RESEARCH Pitfall 2. Where a mis-ordered move surfaces, proved once so a reader knows to look."""

    @pytest_asyncio.fixture
    async def misordered(self, harness):
        """Change the owner and commit without expiring the old owner's active subscription grant."""
        subscription_id = await commit_subscription(harness)
        proof = proof_for(harness)
        owner = await commit_account(harness)
        mover = await commit_account(harness)
        await run_attempt(harness, _Attempt(name="adopt", user_id=owner), proof)

        async with harness.factory() as real_session:
            session = _RecordingSession(real_session)
            # The owner update alone, which is exactly the write the diagram orders the expiries after.
            claimed = await SubscriptionsDB(session).claim_subscription_owner(
                subscription_id=subscription_id, owner_read=owner, month_read=None,
                destination=mover, transfer_month=THIS_MONTH, evaluated_at=NOW)
            assert claimed
            with pytest.raises(IntegrityError) as violation:
                await session.commit()
        return {"subscription_id": subscription_id, "session": session,
                "violation": violation.value, "accounts": (owner, mover)}

    async def test_the_violation_is_the_foreign_key_code_and_not_the_unique_one(self, misordered):
        """23503, so a guard written for 23505 at a flush would let this one through untouched."""
        assert misordered["violation"].orig.sqlstate == "23503"

    async def test_it_arrived_at_the_commit_and_at_no_flush(self, misordered):
        session = misordered["session"]
        assert (session.integrity_at_flush, session.integrity_at_commit) == (False, True)
        assert session.sqlstate == "23503"

    async def test_the_aborted_transaction_left_the_owner_where_it_was(self, harness, misordered):
        owner, _ = misordered["accounts"]
        assert await owner_of(harness, misordered["subscription_id"]) == (owner, None, None)

    async def test_the_production_order_commits_the_same_move(self, harness, misordered):
        """The control: the write this case mis-orders is legal, so the case is about order alone."""
        _, mover = misordered["accounts"]
        moved = await run_attempt(harness, _Attempt(name="move", user_id=mover),
                                  proof_for(harness))

        assert status_of(moved) == 200
        assert await owner_of(harness, misordered["subscription_id"]) == (mover, THIS_MONTH, None)
