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
from nativespeaker.api.schemas.auth import AuthIdentity
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

    def __init__(self, session, before_first_update=None, before_first_commit=None,
                 before_first_flush=None) -> None:
        super().__init__(session, before_first_flush, before_first_commit)
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

    def verify_transaction(self, signed_transaction: str) -> RestoredSubscription:
        return self.proof


def proof_for(harness: _Harness, *, external_id: str | None = None) -> RestoredSubscription:
    """One verified proof for one lifecycle key, shared so every attempt of it sees one term."""
    # A second key names a second subscription, so one account can hold two proofs at once.
    # One term for one subscription, as a store reports it: a re-read never moves the expiry.
    return RestoredSubscription(provider=PurchaseProvider.apple,
                                external_id=harness.external_id if external_id is None else external_id,
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
                              transfer_month: date | None = None,
                              external_id: str | None = None) -> uuid.UUID:
    """One canonical row on this test's lifecycle key, committed for the attempts to read."""
    subscription_id = uuid.uuid4()
    # A caller's own key must start with the harness key, because `clean_up` deletes on that
    # `LIKE :lifecycle` pattern alone and a key outside it would leak between runs.
    key = harness.external_id if external_id is None else external_id
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
             "external_id": key, "tier_id": TIER_ID,
             "transfer_month": transfer_month, "now": NOW})
    return subscription_id


def identity_of(user_id: uuid.UUID) -> AuthIdentity:
    """The admitted caller the route hands the service, carrying nothing but the account it resolved."""
    return AuthIdentity(issuer="ns-restore-race", subject=str(user_id), user=User(id=user_id))


async def run_attempt(harness: _Harness, attempt: _Attempt, proof: RestoredSubscription,
                      before_first_update=None, before_first_commit=None,
                      before_first_flush=None) -> _Attempt:
    """Drive the production restore once, on its own session and connection, as one request does."""
    async with harness.factory() as real_session:
        session = _RecordingSession(real_session, before_first_update, before_first_commit,
                                    before_first_flush)
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

    async def test_the_loser_saw_no_violation_at_all_because_the_update_arbitrated(self, raced):
        """D-08: the UPDATE refused this attempt before any write, so no integrity code reached it.
        `is None`, not `in (None, "23505")`: a code is recorded only inside an `IntegrityError`
        handler that also raises a flag, so the wider form could not fail once the flags are False."""
        loser = raced["by_role"]["lost"]
        assert loser.sqlstate is None
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (False, False)


@pytest.mark.asyncio
class TestTheUniqueIndexArbitratesWhereTheOwnerUpdateCannot:
    """The grant backstop the class above names, where the owner UPDATE refuses nobody: 23505 and
    nothing else. WR-82: this is not the only 23505 path a restore has. The create branch races
    `ix_subscriptions_provider_external_id`, and the class below is that one."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """One account restoring two subscriptions at once: each claims a row of its own, so the
        conditional owner UPDATE refuses neither and `ix_access_grants_one_active_per_user` decides."""
        destination = await commit_account(harness)
        second_key = f"{harness.external_id}-second"
        first_id = await commit_subscription(harness)
        second_id = await commit_subscription(harness, external_id=second_key)
        first = _Attempt(name="first", user_id=destination)
        second = _Attempt(name="second", user_id=destination)
        first_ready, second_ready = asyncio.Event(), asyncio.Event()
        await asyncio.gather(
            run_attempt(harness, first, proof_for(harness),
                        barrier_for(harness, first, first_id, first_ready, second_ready)),
            run_attempt(harness, second, proof_for(harness, external_id=second_key),
                        barrier_for(harness, second, second_id, second_ready, first_ready)))
        return {"attempts": (first, second), "destination": destination,
                "subscription_ids": (first_id, second_id),
                "by_role": {role_of(attempt): attempt for attempt in (first, second)}}

    async def test_no_owner_update_refused_either_attempt(self, raced):
        """The premise: both rows were unowned at the barrier, and each attempt claims a different one."""
        assert [attempt.owner_seen_at_barrier for attempt in raced["attempts"]] == [None, None]
        assert raced["subscription_ids"][0] != raced["subscription_ids"][1]

    async def test_exactly_one_attempt_lost(self, raced):
        assert set(raced["by_role"]) == {"won", "lost"}

    async def test_the_loser_carries_the_unique_violation_and_carries_it_at_the_flush(self, raced):
        """42-07: 23505 is the only integrity code a lost race may carry, on the path that has one.
        A writer that began reading a foreign-key or CHECK violation as a lost race fails here."""
        loser = raced["by_role"]["lost"]
        assert loser.sqlstate == "23505"
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (True, False)

    async def test_the_loser_answers_the_retryable_five_hundred(self, raced):
        """A lost race tells the client nothing and invites the retry that reads the winner's rows."""
        assert status_of(raced["by_role"]["lost"]) == 500

    async def test_the_account_is_left_holding_exactly_one_active_grant(self, harness, raced):
        """The index's whole rule: two would mean it never fired, zero that both attempts rolled back."""
        active = [row for row in await grants_of(harness, raced["destination"])
                  if str(row[1]) == "active"]
        assert len(active) == 1


@pytest.mark.asyncio
class TestTheCreateBranchLosesToAWebhookThatCommittedFirst:
    """WR-82, D-06. The adoption-with-creation branch is the restore's second 23505 path: no
    canonical row at the plain read, and a webhook commits one before the insert flushes.
    `ix_subscriptions_provider_external_id` arbitrates here, not the grant index and not the UPDATE."""

    @pytest_asyncio.fixture
    async def lost(self, harness):
        """No canonical row to read, and one committed from a second connection at the insert's flush."""
        destination = await commit_account(harness)
        attempt = _Attempt(name="creator", user_id=destination)
        committed: list[uuid.UUID] = []

        async def commit_the_webhooks_row() -> None:
            committed.append(await commit_subscription(harness))

        await run_attempt(harness, attempt, proof_for(harness),
                          before_first_flush=commit_the_webhooks_row)
        return {"attempt": attempt, "destination": destination,
                "subscription_id": committed[0]}

    async def test_the_rival_row_was_committed_before_the_insert_flushed(self, lost):
        """The premise: a hook that never ran would leave the insert unopposed and every case vacuous."""
        assert lost["attempt"].flushes == 1

    async def test_the_lost_create_carries_the_unique_violation_at_its_flush(self, lost):
        """The lifecycle index refused the insert, so the code arrives at the flush and not at COMMIT."""
        attempt = lost["attempt"]
        assert attempt.sqlstate == "23505"
        assert (attempt.integrity_at_flush, attempt.integrity_at_commit) == (True, False)

    async def test_the_lost_create_answers_the_retryable_five_hundred(self, lost):
        """A lost race tells the client nothing and invites the retry that reads the winner's row."""
        assert status_of(lost["attempt"]) == 500

    async def test_exactly_one_canonical_row_holds_the_lifecycle_key(self, harness, lost):
        """Two would mean the index never fired; the winner's row is the one a retry then reads."""
        rows = await read(harness,
                          "SELECT id FROM core.subscriptions WHERE external_id = :key",
                          {"key": harness.external_id})
        assert [row[0] for row in rows] == [lost["subscription_id"]]

    async def test_the_lost_create_left_the_account_no_grant(self, harness, lost):
        """The rollback is what makes the retry clean: a grant written here would be an orphan."""
        assert await grants_of(harness, lost["destination"]) == []


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


def active_grants(rows: list[tuple]) -> list[tuple]:
    """The rows of `grants_of` still marked active; every other row is history."""
    return [row for row in rows if row[1] == "active"]


def grants_for(rows: list[tuple], subscription_id: uuid.UUID) -> list[tuple]:
    """The rows of `grants_of` that belong to one subscription, in any status."""
    return [row for row in rows if row[4] == subscription_id]


@pytest.mark.asyncio
class TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves:
    """CR-03, T-45-08-01. A move ends the source's grant for the moved subscription and no other."""

    @pytest_asyncio.fixture
    async def moved(self, harness):
        """The source owns two subscriptions and holds a grant for the second; the first then moves."""
        source = await commit_account(harness)
        destination = await commit_account(harness)
        moving_id = await commit_subscription(harness, user_id=source)
        unrelated_key = f"{harness.external_id}-unrelated"
        unrelated_id = await commit_subscription(harness, user_id=source,
                                                 external_id=unrelated_key)
        moving_proof = proof_for(harness)
        unrelated_proof = proof_for(harness, external_id=unrelated_key)
        # Every grant here is written by the production writer, so no hand-inserted row can
        # disagree with the shape a real restore leaves behind.
        await run_attempt(harness, _Attempt(name="hold-the-moving-one", user_id=source),
                          moving_proof)
        await run_attempt(harness, _Attempt(name="hold-the-unrelated-one", user_id=source),
                          unrelated_proof)
        move = await run_attempt(harness, _Attempt(name="move", user_id=destination),
                                 moving_proof)
        return {"move": move, "accounts": (source, destination),
                "subscriptions": (moving_id, unrelated_id)}

    async def test_the_source_keeps_its_active_grant_for_the_unrelated_subscription(
            self, harness, moved):
        """VERIFICATION truth 6: the restoring caller's proof said nothing about this subscription."""
        source, _ = moved["accounts"]
        _, unrelated_id = moved["subscriptions"]

        kept = grants_for(await grants_of(harness, source), unrelated_id)

        assert len(kept) == 1
        # The status, the term and the counter together: an expiry rewrites the first two.
        assert kept[0][1] == "active"
        assert kept[0][2] == NOW + _A_MONTH
        assert kept[0][5] == 0

    async def test_the_moving_subscription_is_owned_by_the_destination_and_the_month_is_spent(
            self, harness, moved):
        """The premise: a move that wrote nothing would make every case here vacuous."""
        _, destination = moved["accounts"]
        moving_id, _ = moved["subscriptions"]
        assert status_of(moved["move"]) == 200
        assert await owner_of(harness, moving_id) == (destination, THIS_MONTH, None)

    async def test_the_destination_holds_exactly_one_active_grant_and_it_is_for_the_moved_subscription(
            self, harness, moved):
        """The index invariant on the winning side: one account may hold one active grant."""
        _, destination = moved["accounts"]
        moving_id, _ = moved["subscriptions"]

        held = active_grants(await grants_of(harness, destination))

        assert len(held) == 1
        assert held[0][4] == moving_id

    async def test_the_source_holds_no_active_grant_for_the_moved_subscription(self, harness,
                                                                               moved):
        """D-10: the account that loses the subscription loses its access to it in the same transaction."""
        source, _ = moved["accounts"]
        moving_id, _ = moved["subscriptions"]
        # The source's own row for the moved subscription was already superseded, by the restore
        # of the unrelated subscription above. So this asserts the absence of an active row for
        # that subscription, not the presence of a row this move expired.
        assert grants_for(active_grants(await grants_of(harness, source)), moving_id) == []


@pytest.mark.asyncio
class TestTheDestinationStillLosesEverythingItHeld:
    """T-45-08-02. The narrowing keeps the destination's whole set, so it may not spare a row.
    No free-grant case here: `tests/e2e/test_restore_subscription.py` already covers a free grant
    superseded on the restore path, and a second copy on real PostgreSQL buys nothing."""

    @pytest_asyncio.fixture
    async def moved(self, harness):
        """The destination holds a grant for a subscription of its own, then a second one moves to it."""
        source = await commit_account(harness)
        destination = await commit_account(harness)
        moving_id = await commit_subscription(harness, user_id=source)
        own_key = f"{harness.external_id}-destination"
        own_id = await commit_subscription(harness, user_id=destination, external_id=own_key)
        # Written by the production writer, so the row the move must end has a real restore's shape.
        await run_attempt(harness, _Attempt(name="hold-its-own", user_id=destination),
                          proof_for(harness, external_id=own_key))
        move = await run_attempt(harness, _Attempt(name="move", user_id=destination),
                                 proof_for(harness))
        assert status_of(move) == 200
        return {"move": move, "accounts": (source, destination),
                "subscriptions": (moving_id, own_id)}

    async def test_the_destinations_grant_for_another_subscription_is_ended_by_the_move(
            self, harness, moved):
        """The counterpart of the source-side case: this is what stops the narrowing going too far."""
        _, destination = moved["accounts"]
        _, own_id = moved["subscriptions"]

        ended = grants_for(await grants_of(harness, destination), own_id)

        assert len(ended) == 1
        assert ended[0][1] == "expired"
        # The move's own instant, which is what the writer ends a superseded term at.
        assert ended[0][2] == NOW

    async def test_the_destination_ends_with_exactly_one_active_grant(self, harness, moved):
        """`ix_access_grants_one_active_per_user` reads one row, and so must this."""
        _, destination = moved["accounts"]
        moving_id, _ = moved["subscriptions"]

        held = active_grants(await grants_of(harness, destination))

        assert len(held) == 1
        assert held[0][4] == moving_id

    async def test_the_unique_index_never_fired(self, harness, moved):
        """The answer came from the writer's own set, not from an index violation it caught."""
        assert moved["move"].sqlstate is None
        assert (moved["move"].integrity_at_flush, moved["move"].integrity_at_commit) == (False,
                                                                                         False)
