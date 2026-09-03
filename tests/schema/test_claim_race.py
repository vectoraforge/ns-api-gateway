"""Simultaneous claims on one account, raced on two connections against real PostgreSQL."""
import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import object_session
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.devicecheck import BitState
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import AppError
from nativespeaker.api.schemas.auth import Entitlement, EntitlementStatus, EntitlementType
from nativespeaker.api.services import AuthService, SyncService

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# Bounded so a partner that fails before its flush shows up as a failure rather than as a hung suite.
BARRIER_TIMEOUT_SECONDS = 20


@dataclass
class _Harness:
    engine: object
    factory: async_sessionmaker
    issuer: str


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """A committing session factory plus this test's private issuer, cleaned up in FK order."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    subject = _Harness(engine=engine,
                       factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                  expire_on_commit=False),
                       issuer=f"ns-claim-race-{uuid.uuid4().hex[:10]}")
    try:
        yield subject
    finally:
        try:
            await clean_up(subject)
        finally:
            await engine.dispose()


async def clean_up(harness: _Harness) -> None:
    """Child-first: usage, grants, then the identity rows, then the users they pointed at."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        owned = (await conn.execute(
            text("SELECT user_id FROM core.external_identities WHERE issuer = :issuer"),
            {"issuer": harness.issuer})).all()
        user_ids = [row[0] for row in owned]

        for user_id in user_ids:
            for statement in (
                    "DELETE FROM core.user_monthly_usage WHERE grant_id IN "
                    "(SELECT id FROM core.access_grants WHERE user_id = :id)",
                    "DELETE FROM core.access_grants WHERE user_id = :id"):
                await conn.execute(text(statement), {"id": user_id})

        for statement in ("DELETE FROM core.external_identities WHERE issuer = :issuer",
                          "DELETE FROM core.auth_challenges WHERE preauth_issuer = :issuer"):
            await conn.execute(text(statement), {"issuer": harness.issuer})

        # Last: core.external_identities references core.users ON DELETE RESTRICT.
        for user_id in user_ids:
            await conn.execute(text("DELETE FROM core.users WHERE id = :id"), {"id": user_id})


async def read(harness: _Harness, sql: str, params: dict | None = None):
    """One read on a connection of its own -- never the one an attempt under test used."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        return (await conn.execute(text(sql), params or {})).all()


async def scalar(harness: _Harness, sql: str, params: dict | None = None):
    rows = await read(harness, sql, params)
    return rows[0][0] if rows else None


async def commit_anonymous_account(harness: _Harness, *, subject: str) -> uuid.UUID:
    """One anonymous identity and its user, committed, because each attempt reads them on its own connection."""
    user_id, identity_id = uuid.uuid4(), uuid.uuid4()
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(text("INSERT INTO core.users (id) VALUES (:id)"), {"id": user_id})
        # provider_uid stays NULL, which is the table's CHECK for exactly the anonymous arm.
        await conn.execute(
            text("INSERT INTO core.external_identities "
                 "(id, user_id, issuer, subject, provider, identity_state, created_at, updated_at) "
                 "VALUES (:id, :user_id, :issuer, :subject, 'anonymous', 'active', :now, :now)"),
            {"id": identity_id, "user_id": user_id, "issuer": harness.issuer,
             "subject": subject, "now": NOW})
    return user_id


async def commit_registered_account(harness: _Harness, *, subject: str) -> uuid.UUID:
    """One google identity and its user, committed, because each attempt reads them on its own connection."""
    user_id, identity_id = uuid.uuid4(), uuid.uuid4()
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(text("INSERT INTO core.users (id) VALUES (:id)"), {"id": user_id})
        # provider_uid must be non-empty here, which is the table's CHECK for exactly the google arm.
        await conn.execute(
            text("INSERT INTO core.external_identities "
                 "(id, user_id, issuer, subject, provider, provider_uid, identity_state, "
                 " created_at, updated_at) "
                 "VALUES (:id, :user_id, :issuer, :subject, 'google', :provider_uid, 'active', "
                 "        :now, :now)"),
            {"id": identity_id, "user_id": user_id, "issuer": harness.issuer,
             "subject": subject, "provider_uid": f"uid-{uuid.uuid4().hex[:16]}", "now": NOW})
    return user_id


async def commit_issued_challenge(harness: _Harness, *, subject: str,
                                  operation: str) -> tuple[uuid.UUID, str]:
    """One issued challenge; the completion under test claims it itself, so `claimed_at` starts NULL."""
    row_id = uuid.uuid4()
    challenge_id = f"handle-{uuid.uuid4().hex[:16]}"
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("INSERT INTO core.auth_challenges "
                 "(id, challenge_id, operation, preauth_issuer, preauth_subject, "
                 " expires_at, created_at) "
                 "VALUES (:id, :challenge_id, CAST(:operation AS core.auth_operation), "
                 "        :issuer, :subject, :expires_at, :now)"),
            {"id": row_id, "challenge_id": challenge_id, "operation": operation,
             "issuer": harness.issuer, "subject": subject,
             "expires_at": NOW + timedelta(seconds=300), "now": NOW})
    return row_id, challenge_id


class _NeverSetDevice:
    """The scripted seam: a never-set device for both attempts, so the vendor cannot make a race flaky."""

    def __init__(self) -> None:
        self.read_calls: list[str] = []
        self.write_calls: list[tuple[str, bool, bool]] = []

    async def read_bits(self, device_token: str) -> BitState:
        self.read_calls.append(device_token)
        return BitState(bit0=False, bit1=False)

    async def write_bits(self, device_token: str, *, bit0: bool, bit1: bool) -> None:
        self.write_calls.append((device_token, bit0, bit1))


class _RacingSession:
    """A real session that holds at a barrier, and records whether a violation arrived at the flush or the commit."""

    def __init__(self, session, before_first_flush=None, before_first_commit=None) -> None:
        self._session = session
        self._before_first_flush = before_first_flush
        self._before_first_commit = before_first_commit
        self.flushes = 0
        self.commits = 0
        self.integrity_at_flush = False
        self.integrity_at_commit = False

    async def flush(self, *args, **kwargs):
        self.flushes += 1
        if self.flushes == 1 and self._before_first_flush is not None:
            hook, self._before_first_flush = self._before_first_flush, None
            await hook()
        try:
            return await self._session.flush(*args, **kwargs)
        except IntegrityError:
            self.integrity_at_flush = True
            raise

    async def commit(self, *args, **kwargs):
        self.commits += 1
        if self.commits == 1 and self._before_first_commit is not None:
            hook, self._before_first_commit = self._before_first_commit, None
            await hook()
        # The inner session's own flush runs here, so a violation reaching commit never sets the flag above.
        try:
            return await self._session.commit(*args, **kwargs)
        except IntegrityError:
            self.integrity_at_commit = True
            raise

    def __getattr__(self, name):
        return getattr(self._session, name)


@dataclass
class _Attempt:
    """One completion's inputs and everything observable about what it did."""

    name: str
    subject: str
    challenge_row_id: uuid.UUID
    challenge_id: str
    operation: str = "claim_anonymous_grant"
    # What the call produced: the entitlement read after commit, or the rejection it raised.
    result: Entitlement | AppError | None = None
    grants_seen_at_barrier: int | None = None
    caller_rows_detached: bool | None = None
    integrity_at_flush: bool = False
    integrity_at_commit: bool = False
    # Every write the writer emits goes through one of these, so zero means the attempt wrote nothing.
    flushes: int = 0


def role_of(attempt: _Attempt) -> str:
    """The bucket an attempt lands in, and the only observable that separates them: who lost at the flush."""
    return "lost_at_flush" if attempt.integrity_at_flush else "won"


def status_of(attempt: _Attempt) -> int:
    """The status the route would have answered: an entitlement is a 200, a rejection carries its own."""
    return attempt.result.status if isinstance(attempt.result, AppError) else 200


async def prepare_attempt(harness: _Harness, *, name: str, subject: str,
                          operation: str = "claim_anonymous_grant") -> _Attempt:
    row_id, challenge_id = await commit_issued_challenge(harness, subject=subject,
                                                         operation=operation)
    return _Attempt(name=name, subject=subject, challenge_row_id=row_id,
                    challenge_id=challenge_id, operation=operation)


async def resolve_identity(harness: _Harness, subject: str):
    """Resolve the caller as `get_identity` does: on a session of its own, closed before the service runs."""
    async with harness.factory() as session:
        return await IdentitiesDB(session).resolve(issuer=harness.issuer,
                                                   subject=subject,
                                                   allow_preauth=False)


async def run_attempt(harness: _Harness, attempt: _Attempt, before_first_flush=None,
                      before_first_commit=None) -> _Attempt:
    """Drive the production completion once, on its own session and connection, as the route does."""
    store = ChallengesDB()
    identity = await resolve_identity(harness, attempt.subject)
    async with harness.factory() as real_session:
        session = _RacingSession(real_session, before_first_flush, before_first_commit)
        attempt.caller_rows_detached = all(
            object_session(row) is None for row in (identity.user, identity.identity))
        service = AuthService(db=session, challenge_store=store, adapter=None,
                              evaluated_at=NOW, devicecheck=_NeverSetDevice())
        completion = (service.complete_claim_registered_grant
                      if attempt.operation == "claim_registered_grant"
                      else service.complete_claim_anonymous_grant)
        try:
            await completion(
                identity=identity,
                challenge_id=attempt.challenge_id,
                device_token=f"device-{attempt.name}")
        except AppError as rejection:
            attempt.result = rejection
        else:
            # The route's own read, after the completion committed: the claim, the repeat and the loser share it.
            attempt.result = await SyncService(db=session,
                                               evaluated_at=NOW).read_entitlement(identity.user.id)
        attempt.integrity_at_flush = session.integrity_at_flush
        attempt.integrity_at_commit = session.integrity_at_commit
        attempt.flushes = session.flushes
    return attempt


def barrier_for(harness: _Harness, attempt: _Attempt, user_id: uuid.UUID,
                mine: asyncio.Event, theirs: asyncio.Event):
    """Announce that this attempt has re-resolved, then wait for its partner; the row count records the premise."""

    async def hold() -> None:
        attempt.grants_seen_at_barrier = await scalar(
            harness, "SELECT count(*) FROM core.access_grants WHERE user_id = :id", {"id": user_id})
        mine.set()
        await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)

    return hold


class TestTwoSimultaneousFirstClaimsAllocateOnce:
    """D-12. The database arbitrates: no advisory lock, no lease and no read-then-check in the application."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two challenges for one anonymous account, released together and held until both have re-resolved."""
        subject = f"claimant-{uuid.uuid4().hex[:8]}"
        user_id = await commit_anonymous_account(harness, subject=subject)
        first = await prepare_attempt(harness, name="first", subject=subject)
        second = await prepare_attempt(harness, name="second", subject=subject)

        first_ready, second_ready = asyncio.Event(), asyncio.Event()
        await asyncio.gather(
            run_attempt(harness, first,
                        barrier_for(harness, first, user_id, first_ready, second_ready)),
            run_attempt(harness, second,
                        barrier_for(harness, second, user_id, second_ready, first_ready)))

        return {"subject": subject, "user_id": user_id, "attempts": (first, second),
                "by_role": {role_of(attempt): attempt for attempt in (first, second)}}

    async def test_both_attempts_observed_an_account_with_no_grant(self, raced):
        """The premise: without this the case could be two sequential claims, and everything below vacuous."""
        assert [attempt.grants_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_neither_attempt_handed_the_service_a_row_of_its_own_session(self, raced):
        """The second premise: the caller's rows belong to no session, so refreshing either one would raise."""
        assert [attempt.caller_rows_detached for attempt in raced["attempts"]] == [True, True]

    async def test_exactly_one_attempt_lost_the_race(self, raced):
        """Both answer 200, so losing at the flush is the only thing that separates them."""
        assert set(raced["by_role"]) == {"won", "lost_at_flush"}

    async def test_exactly_one_grant_row_exists_on_the_anonymous_tier(self, harness, raced):
        """Two rows would mean the indexes did not arbitrate; zero would mean both rolled back."""
        rows = await read(
            harness,
            "SELECT source::text, status::text, tier_id FROM core.access_grants WHERE user_id = :id",
            {"id": raced["user_id"]})
        assert rows == [("anonymous_device_grant", "active", "anonymous")]

    async def test_exactly_one_usage_row_exists_at_zero_used(self, harness, raced):
        rows = await read(
            harness,
            "SELECT u.monthly_period, u.monthly_used FROM core.user_monthly_usage u "
            "JOIN core.access_grants g ON g.id = u.grant_id WHERE g.user_id = :id",
            {"id": raced["user_id"]})
        assert rows == [("2026-08", 0)]

    async def test_the_lifetime_marker_is_set_once(self, harness, raced):
        """Read as a single value, not as a count of writes: the column is set once and never cleared."""
        rows = await read(
            harness,
            "SELECT free_grant_consumed_at, native_claim_platform::text "
            "FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": raced["subject"]})
        assert rows == [(NOW, "ios_devicecheck")]

    async def test_both_challenges_were_consumed_and_their_verifiers_cleared(self, harness, raced):
        """The loser consumes too, so a retry needs a fresh prepare rather than a replay of either handle."""
        for attempt in raced["attempts"]:
            rows = await read(
                harness,
                "SELECT consumed_at, preauth_subject FROM core.auth_challenges WHERE id = :id",
                {"id": attempt.challenge_row_id})
            assert rows[0][0] is not None, f"the {attempt.name} attempt left its challenge unconsumed"
            assert rows[0][1] is None

    async def test_the_loser_answers_two_hundred_with_the_winners_entitlement(self, raced):
        """D-13, inverting the create race: the loser is answered as a repeat is, not with a rejection."""
        winner, loser = raced["by_role"]["won"], raced["by_role"]["lost_at_flush"]
        assert status_of(loser) == 200
        assert isinstance(loser.result, Entitlement)
        # Field for field, because both read the same row after the winner committed.
        assert loser.result.model_dump() == winner.result.model_dump()
        assert loser.result.type is EntitlementType.anonymous_device_grant
        assert loser.result.status is EntitlementStatus.active

    async def test_the_losers_violation_arrived_at_the_flush_and_not_at_the_commit(self, raced):
        """The two unique indexes fire per statement, so the violation arrives at the flush."""
        winner, loser = raced["by_role"]["won"], raced["by_role"]["lost_at_flush"]
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (True, False)
        assert (winner.integrity_at_flush, winner.integrity_at_commit) == (False, False)


class TestTwoSimultaneousRegisteredClaimsAllocateOnce:
    """D-11 and D-12. On a first claim there is no row to lock, so the unique indexes are the arbiter."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two challenges for one registered account, released together and held until both have re-resolved."""
        subject = f"claimant-{uuid.uuid4().hex[:8]}"
        user_id = await commit_registered_account(harness, subject=subject)
        first = await prepare_attempt(harness, name="first", subject=subject,
                                      operation="claim_registered_grant")
        second = await prepare_attempt(harness, name="second", subject=subject,
                                       operation="claim_registered_grant")

        first_ready, second_ready = asyncio.Event(), asyncio.Event()
        await asyncio.gather(
            run_attempt(harness, first,
                        barrier_for(harness, first, user_id, first_ready, second_ready)),
            run_attempt(harness, second,
                        barrier_for(harness, second, user_id, second_ready, first_ready)))

        return {"subject": subject, "user_id": user_id, "attempts": (first, second),
                "by_role": {role_of(attempt): attempt for attempt in (first, second)}}

    async def test_both_attempts_observed_an_account_with_no_grant(self, raced):
        """The premise: without this the case could be two sequential claims, and everything below vacuous."""
        assert [attempt.grants_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_neither_attempt_handed_the_service_a_row_of_its_own_session(self, raced):
        """The second premise: the caller's rows belong to no session, so refreshing either one would raise."""
        assert [attempt.caller_rows_detached for attempt in raced["attempts"]] == [True, True]

    async def test_exactly_one_attempt_lost_the_race(self, raced):
        """Both answer 200, so losing at the flush is the only thing that separates them."""
        assert set(raced["by_role"]) == {"won", "lost_at_flush"}

    async def test_exactly_one_grant_row_exists_on_the_registered_tier(self, harness, raced):
        """Two rows would mean the indexes did not arbitrate; zero would mean both rolled back."""
        rows = await read(
            harness,
            "SELECT source::text, status::text, tier_id FROM core.access_grants WHERE user_id = :id",
            {"id": raced["user_id"]})
        assert rows == [("registered_account_grant", "active", "registered")]

    async def test_exactly_one_usage_row_exists_at_zero_used(self, harness, raced):
        rows = await read(
            harness,
            "SELECT u.monthly_period, u.monthly_used FROM core.user_monthly_usage u "
            "JOIN core.access_grants g ON g.id = u.grant_id WHERE g.user_id = :id",
            {"id": raced["user_id"]})
        assert rows == [("2026-08", 0)]

    async def test_the_lifetime_marker_is_set_once(self, harness, raced):
        """Read as a single value, not as a count of writes: the column is set once and never cleared."""
        rows = await read(
            harness,
            "SELECT free_grant_consumed_at, native_claim_platform::text "
            "FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": raced["subject"]})
        assert rows == [(NOW, None)]

    async def test_both_challenges_were_consumed_and_their_verifiers_cleared(self, harness, raced):
        """The loser consumes too, so a retry needs a fresh prepare rather than a replay of either handle."""
        for attempt in raced["attempts"]:
            rows = await read(
                harness,
                "SELECT consumed_at, preauth_subject FROM core.auth_challenges WHERE id = :id",
                {"id": attempt.challenge_row_id})
            assert rows[0][0] is not None, f"the {attempt.name} attempt left its challenge unconsumed"
            assert rows[0][1] is None

    async def test_the_loser_answers_two_hundred_with_the_winners_entitlement(self, raced):
        """D-13, inverting the create race: the loser is answered as a repeat is, not with a rejection."""
        winner, loser = raced["by_role"]["won"], raced["by_role"]["lost_at_flush"]
        assert status_of(loser) == 200
        assert isinstance(loser.result, Entitlement)
        # Field for field, because both read the same row after the winner committed.
        assert loser.result.model_dump() == winner.result.model_dump()
        assert loser.result.type is EntitlementType.registered_account_grant
        assert loser.result.status is EntitlementStatus.active

    async def test_the_losers_violation_arrived_at_the_flush_and_not_at_the_commit(self, raced):
        """The two unique indexes fire per statement, so the violation arrives at the flush."""
        winner, loser = raced["by_role"]["won"], raced["by_role"]["lost_at_flush"]
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (True, False)
        assert (winner.integrity_at_flush, winner.integrity_at_commit) == (False, False)


# Deliberately not the period or the count a freshly minted usage row would carry at `NOW`.
SEEDED_PERIOD = "2026-07"
SEEDED_USED = 7


async def commit_active_anonymous_grant(harness: _Harness, *, user_id: uuid.UUID) -> uuid.UUID:
    """One active anonymous grant and its usage row, started strictly before `NOW`."""
    grant_id = uuid.uuid4()
    started_at = NOW - timedelta(days=30)
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("INSERT INTO core.access_grants "
                 "(id, user_id, tier_id, source, status, starts_at, created_at, updated_at) "
                 "VALUES (:id, :user_id, 'anonymous', 'anonymous_device_grant', 'active', "
                 "        :started_at, :started_at, :started_at)"),
            {"id": grant_id, "user_id": user_id, "started_at": started_at})
        await conn.execute(
            text("INSERT INTO core.user_monthly_usage "
                 "(grant_id, monthly_period, monthly_used, created_at, updated_at) "
                 "VALUES (:grant_id, :period, :used, :started_at, :started_at)"),
            {"grant_id": grant_id, "period": SEEDED_PERIOD, "used": SEEDED_USED,
             "started_at": started_at})
    return grant_id


def role_by_writes(attempt: _Attempt) -> str:
    """The bucket a conversion attempt lands in: the row lock serialises the two, so writing is what separates them."""
    return "won" if attempt.flushes else "lost_before_writing"


class TestTwoSimultaneousConversionsSupersedeOnce:
    """D-10 and D-13. One anonymous row expires, one registered row activates, and the counters cross once."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two conversions on one account holding an active anonymous grant, held until both have claimed."""
        subject = f"claimant-{uuid.uuid4().hex[:8]}"
        user_id = await commit_registered_account(harness, subject=subject)
        anonymous_id = await commit_active_anonymous_grant(harness, user_id=user_id)
        first = await prepare_attempt(harness, name="first", subject=subject,
                                      operation="claim_registered_grant")
        second = await prepare_attempt(harness, name="second", subject=subject,
                                       operation="claim_registered_grant")

        # Held before the challenge commit, not before the first flush: a conversion takes the grant
        # row lock before it flushes, so a partner held at that flush can never reach its own.
        first_ready, second_ready = asyncio.Event(), asyncio.Event()
        await asyncio.gather(
            run_attempt(harness, first, before_first_commit=barrier_for(
                harness, first, user_id, first_ready, second_ready)),
            run_attempt(harness, second, before_first_commit=barrier_for(
                harness, second, user_id, second_ready, first_ready)))

        return {"subject": subject, "user_id": user_id, "anonymous_id": anonymous_id,
                "attempts": (first, second),
                "by_role": {role_by_writes(attempt): attempt for attempt in (first, second)}}

    async def test_both_attempts_observed_the_account_holding_its_anonymous_grant(self, raced):
        """The premise: without this the case could be a conversion then a repeat, and everything below vacuous."""
        assert [attempt.grants_seen_at_barrier for attempt in raced["attempts"]] == [1, 1]

    async def test_the_seeded_grant_started_strictly_before_the_instant_that_expires_it(self,
                                                                                        harness,
                                                                                        raced):
        """The CHECK `ends_at > starts_at` is strict, so a same-instant seed would refuse the expiry."""
        started_at = await scalar(harness,
                                  "SELECT starts_at FROM core.access_grants WHERE id = :id",
                                  {"id": raced["anonymous_id"]})
        assert started_at < NOW

    async def test_neither_attempt_handed_the_service_a_row_of_its_own_session(self, raced):
        """The second premise: the caller's rows belong to no session, so refreshing either one would raise."""
        assert [attempt.caller_rows_detached for attempt in raced["attempts"]] == [True, True]

    async def test_exactly_one_attempt_wrote(self, raced):
        """Both answer 200, so writing is the only thing that separates them under the row lock."""
        assert set(raced["by_role"]) == {"won", "lost_before_writing"}

    async def test_exactly_one_active_grant_row_exists_on_the_registered_tier(self, harness, raced):
        """Two would mean the supersession interleaved; zero would mean the account lost its entitlement."""
        rows = await read(
            harness,
            "SELECT source::text, tier_id FROM core.access_grants "
            "WHERE user_id = :id AND status = 'active'",
            {"id": raced["user_id"]})
        assert rows == [("registered_account_grant", "registered")]

    async def test_exactly_one_row_expired_and_its_source_was_never_rewritten(self, harness, raced):
        """The anonymous row is expired once, at the request's instant, and stays the row it was."""
        rows = await read(
            harness,
            "SELECT id, source::text, ends_at FROM core.access_grants "
            "WHERE user_id = :id AND status = 'expired'",
            {"id": raced["user_id"]})
        assert rows == [(raced["anonymous_id"], "anonymous_device_grant", NOW)]

    async def test_the_user_holds_exactly_two_grant_rows(self, harness, raced):
        """The loser minted no third row, which a second insert against a stale read would have left."""
        assert await scalar(harness,
                            "SELECT count(*) FROM core.access_grants WHERE user_id = :id",
                            {"id": raced["user_id"]}) == 2

    async def test_the_counters_crossed_to_the_active_grant_exactly_once(self, harness, raced):
        """The seeded period and count, not the defaults a freshly minted row would carry."""
        rows = await read(
            harness,
            "SELECT u.monthly_period, u.monthly_used FROM core.user_monthly_usage u "
            "JOIN core.access_grants g ON g.id = u.grant_id "
            "WHERE g.user_id = :id AND g.status = 'active'",
            {"id": raced["user_id"]})
        assert rows == [(SEEDED_PERIOD, SEEDED_USED)]

    async def test_both_challenges_were_consumed_and_their_verifiers_cleared(self, harness, raced):
        """The loser consumes too, so a retry needs a fresh prepare rather than a replay of either handle."""
        for attempt in raced["attempts"]:
            rows = await read(
                harness,
                "SELECT consumed_at, preauth_subject FROM core.auth_challenges WHERE id = :id",
                {"id": attempt.challenge_row_id})
            assert rows[0][0] is not None, f"the {attempt.name} attempt left its challenge unconsumed"
            assert rows[0][1] is None

    async def test_the_loser_answers_two_hundred_with_the_winners_entitlement(self, raced):
        """D-13, inverting the create race: the loser is answered as a repeat is, not with a rejection."""
        winner, loser = raced["by_role"]["won"], raced["by_role"]["lost_before_writing"]
        assert status_of(loser) == 200
        assert isinstance(loser.result, Entitlement)
        # Field for field, because both read the same row after the winner committed.
        assert loser.result.model_dump() == winner.result.model_dump()
        assert loser.result.type is EntitlementType.registered_account_grant
        assert loser.result.status is EntitlementStatus.active

    async def test_the_loser_emitted_no_write_and_raised_no_violation(self, raced):
        """Measured, not predicted: the row lock serialises the two, so the loser is refused before it writes."""
        winner, loser = raced["by_role"]["won"], raced["by_role"]["lost_before_writing"]
        assert (loser.integrity_at_flush, loser.integrity_at_commit) == (False, False)
        assert loser.flushes == 0
        # The expiry, flushed alone, and then the rest of the conversion.
        assert winner.flushes == 2

    async def test_the_account_holds_free_entitlement_from_exactly_one_source(self, harness, raced):
        """The lifetime index permits one row of each free source, so this account-level rule is the application's."""
        assert await scalar(
            harness,
            "SELECT count(*) FROM core.access_grants WHERE user_id = :id AND status = 'active' "
            "AND source IN ('anonymous_device_grant', 'registered_account_grant')",
            {"id": raced["user_id"]}) == 1
