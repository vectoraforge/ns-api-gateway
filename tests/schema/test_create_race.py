"""Two concurrent creates for one (issuer, subject) yield exactly one account, with the unique indexes deciding."""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import AppError
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.services.auth import AuthService
from nativespeaker.api.tables.identities import IdentityProvider

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# Bounded so a partner that fails before its re-resolution shows up as a failure rather than a hung suite.
BARRIER_TIMEOUT_SECONDS = 20


@dataclass
class _Harness:
    engine: object
    factory: async_sessionmaker
    issuer: str
    owned_user_ids: list[uuid.UUID] = field(default_factory=list)


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """A committing session factory plus this test's private issuer, cleaned up in FK order."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    subject = _Harness(engine=engine,
                       factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                  expire_on_commit=False),
                       issuer=f"ns-race-{uuid.uuid4().hex[:12]}")
    try:
        yield subject
    finally:
        try:
            async with engine.begin() as conn:
                rows = (await conn.execute(
                    text("SELECT user_id FROM core.external_identities WHERE issuer = :issuer"),
                    {"issuer": subject.issuer})).all()
                for statement in (
                        "DELETE FROM core.external_identities WHERE issuer = :issuer",
                        "DELETE FROM core.auth_challenges WHERE preauth_issuer = :issuer"):
                    await conn.execute(text(statement), {"issuer": subject.issuer})
                for user_id in {*subject.owned_user_ids, *(row[0] for row in rows)}:
                    await conn.execute(text("DELETE FROM core.users WHERE id = :id"),
                                       {"id": user_id})
        finally:
            await engine.dispose()



async def read(harness: _Harness, sql: str, params: dict | None = None):
    """One read on a connection of its own -- never the one an attempt under test used."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        return (await conn.execute(text(sql), params or {})).all()


async def scalar(harness: _Harness, sql: str, params: dict | None = None):
    rows = await read(harness, sql, params)
    return rows[0][0] if rows else None


async def commit_claimed_challenge(harness: _Harness, *,
                                   subject: str) -> tuple[uuid.UUID, str]:
    """One already-claimed challenge; each attempt gets its own and must consume it."""
    row_id = uuid.uuid4()
    challenge_id = f"handle-{uuid.uuid4().hex[:16]}"
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("INSERT INTO core.auth_challenges "
                 "(id, challenge_id, operation, preauth_issuer, preauth_subject, "
                 " expires_at, claimed_at, created_at) "
                 "VALUES (:id, :challenge_id, 'create_user', :issuer, :subject, "
                 "        :expires_at, :now, :now)"),
            {"id": row_id, "challenge_id": challenge_id, "issuer": harness.issuer,
             "subject": subject,
             "expires_at": NOW + timedelta(seconds=300), "now": NOW})
    return row_id, challenge_id


class _HookedSession:
    """A real session that runs a callback once after its first read, which is the in-transaction re-resolution."""

    def __init__(self, session, after_first_read=None) -> None:
        self._session = session
        self._after_first_read = after_first_read
        self.reads = 0

    async def exec(self, statement):
        result = await self._session.exec(statement)
        self.reads += 1
        if self.reads == 1 and self._after_first_read is not None:
            hook, self._after_first_read = self._after_first_read, None
            await hook()
        return result

    def __getattr__(self, name):
        return getattr(self._session, name)


@dataclass
class _Attempt:
    """One completion's inputs and everything observable about what it did."""

    subject: str
    provider: IdentityProvider
    provider_uid: str | None
    identity: Identity
    challenge_row_id: uuid.UUID
    challenge_id: str
    # What the call produced: the new user's id on success, the rejection it raised otherwise.
    result: uuid.UUID | AppError | None = None
    identities_seen_at_barrier: int | None = None


def outcome_name(attempt: _Attempt) -> str:
    """The bucket an attempt lands in: `succeeded` for a returned id, the class name for a rejection."""
    return "succeeded" if isinstance(attempt.result, uuid.UUID) else type(attempt.result).__name__


async def prepare_attempt(harness: _Harness, *, subject: str, provider: IdentityProvider,
                          provider_uid: str | None) -> _Attempt:
    identity = Identity(issuer=harness.issuer, subject=subject)
    row_id, challenge_id = await commit_claimed_challenge(harness, subject=subject)
    return _Attempt(subject=subject, provider=provider, provider_uid=provider_uid,
                    identity=identity,
                    challenge_row_id=row_id, challenge_id=challenge_id)


async def run_attempt(harness: _Harness, attempt: _Attempt, after_first_read=None) -> _Attempt:
    """Drive the production consuming transaction once, on its own session and connection."""
    store = ChallengesDB()
    async with harness.factory() as real_session:
        session = _HookedSession(real_session, after_first_read)
        try:
            service = AuthService(db=session, challenge_store=store, adapter=None,
                                  evaluated_at=NOW)
            attempt.result = await service.create_user(identity=attempt.identity,
                                                       provider=attempt.provider,
                                                       provider_uid=attempt.provider_uid,
                                                       email=None)
        except AppError as rejection:
            # The route's own except arm (`routers/auth.py::_complete`): the conflicting inserts are
            # rolled back, then the handle is spent and committed before the client is answered.
            # Driving the transaction without it would read the missing half as a leaked challenge.
            await session.rollback()
            attempt.result = rejection
        await store.consume(session, challenge_id=attempt.challenge_id, now=NOW)
        await session.commit()
    return attempt


def barrier_for(harness: _Harness, attempt: _Attempt, mine: asyncio.Event, theirs: asyncio.Event):
    """Announce that this attempt has re-resolved, then wait for its partner; the row count records the premise."""

    async def hold() -> None:
        attempt.identities_seen_at_barrier = await scalar(
            harness,
            "SELECT count(*) FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": attempt.subject})
        mine.set()
        await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)

    return hold


class TestTwoConcurrentCompletionsProduceExactlyOneAccount:
    """Criterion 4. The crud arbitrates; nothing in the application does."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two attempts on the same pair, released together; their providers differ so an overwrite is visible."""
        subject = f"contested-{uuid.uuid4().hex[:8]}"
        first = await prepare_attempt(harness, subject=subject, provider=IdentityProvider.google,
                                      provider_uid=f"google-uid-{subject}")
        second = await prepare_attempt(harness, subject=subject, provider=IdentityProvider.apple,
                                       provider_uid=f"apple-uid-{subject}")

        first_ready, second_ready = asyncio.Event(), asyncio.Event()
        await asyncio.gather(
            run_attempt(harness, first, barrier_for(harness, first, first_ready, second_ready)),
            run_attempt(harness, second, barrier_for(harness, second, second_ready, first_ready)))

        by_result = {outcome_name(attempt): attempt for attempt in (first, second)}
        return {"subject": subject, "attempts": (first, second), "by_result": by_result}

    async def test_both_attempts_observed_an_unlinked_subject(self, raced):
        """The premise: without this the case could be two sequential creations."""
        assert [attempt.identities_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_exactly_one_succeeded_and_the_other_is_already_linked(self, raced):
        """Never two successes, and never idempotent success: the loser is told to reconcile, not "created"."""
        assert set(raced["by_result"]) == {"succeeded", "IdentityAlreadyLinked"}

    async def test_exactly_one_identity_row_exists_for_the_contested_pair(self, harness, raced):
        """Two rows would mean the constraint did not arbitrate; zero would mean both rolled back."""
        assert await scalar(
            harness,
            "SELECT count(*) FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": raced["subject"]}) == 1

    async def test_exactly_one_users_row_backs_that_identity(self, harness, raced):
        rows = await read(
            harness,
            "SELECT count(*) FROM core.users u "
            "JOIN core.external_identities i ON i.user_id = u.id "
            "WHERE i.issuer = :issuer AND i.subject = :s",
            {"issuer": harness.issuer, "s": raced["subject"]})
        assert rows[0][0] == 1

    async def test_the_loser_left_no_orphaned_user_row(self, harness, raced):
        """A core.users row with no identity row is a partial account, so any extra one is an orphan."""
        assert await scalar(
            harness,
            "SELECT count(*) FROM core.users u WHERE u.created_at = :now "
            "AND NOT EXISTS (SELECT 1 FROM core.external_identities i WHERE i.user_id = u.id)",
            {"now": NOW}) == 0

    async def test_the_surviving_row_carries_the_winners_pair_and_none_of_the_losers(self, harness,
                                                                                    raced):
        """No merge and no overwrite: the attempts classified differently, so the loser's pair would show here."""
        winner = raced["by_result"]["succeeded"]
        loser = raced["by_result"]["IdentityAlreadyLinked"]
        rows = await read(
            harness,
            "SELECT provider::text, provider_uid FROM core.external_identities "
            "WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": raced["subject"]})

        assert rows == [(winner.provider.value, winner.provider_uid)]
        assert rows[0][1] != loser.provider_uid

    async def test_the_winner_minted_two_tokens_and_the_loser_none(self, harness, raced):
        """A rejected completion mints nothing and the winner gets one row per store, so the total is two."""
        assert await scalar(
            harness,
            "SELECT count(*) FROM core.store_purchase_tokens t "
            "JOIN core.external_identities i ON i.user_id = t.user_id "
            "WHERE i.issuer = :issuer AND i.subject = :s",
            {"issuer": harness.issuer, "s": raced["subject"]}) == 2

        assert await scalar(
            harness,
            "SELECT count(*) FROM core.store_purchase_tokens t "
            "WHERE t.created_at = :now AND NOT EXISTS "
            "(SELECT 1 FROM core.external_identities i WHERE i.user_id = t.user_id)",
            {"now": NOW}) == 0

    async def test_both_challenges_were_consumed_and_their_verifiers_cleared(self, harness, raced):
        """The loser consumes too, so a retry needs a fresh prepare rather than a replay of this one."""
        for attempt in raced["attempts"]:
            rows = await read(
                harness,
                "SELECT consumed_at, preauth_subject FROM core.auth_challenges WHERE id = :id",
                {"id": attempt.challenge_row_id})
            assert rows[0][0] is not None, f"{outcome_name(attempt)} left its challenge unconsumed"
            assert rows[0][1] is None


class TestRunningTheSameCreationTwiceSequentially:
    """The same input run twice must answer as the race does, though re-resolution rejects rather than an index."""

    @pytest_asyncio.fixture
    async def twice(self, harness):
        subject = f"repeated-{uuid.uuid4().hex[:8]}"
        first = await run_attempt(harness, await prepare_attempt(
            harness, subject=subject, provider=IdentityProvider.google,
            provider_uid=f"google-uid-{subject}"))

        after_first = await read(
            harness,
            "SELECT provider::text, provider_uid, user_id FROM core.external_identities "
            "WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": subject})
        counts_after_first = await self._counts(harness, subject)

        # A *different* classified pair on the second run, so an overwrite would be visible.
        second = await run_attempt(harness, await prepare_attempt(
            harness, subject=subject, provider=IdentityProvider.apple,
            provider_uid=f"apple-uid-{subject}"))

        return {"subject": subject, "first": first, "second": second,
                "row_after_first": after_first, "counts_after_first": counts_after_first,
                "counts_after_second": await self._counts(harness, subject)}

    @staticmethod
    async def _counts(harness: _Harness, subject: str) -> tuple[int, int, int]:
        identities = await scalar(
            harness,
            "SELECT count(*) FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": subject})
        users = await scalar(
            harness,
            "SELECT count(*) FROM core.users u JOIN core.external_identities i ON i.user_id = u.id "
            "WHERE i.issuer = :issuer AND i.subject = :s",
            {"issuer": harness.issuer, "s": subject})
        tokens = await scalar(
            harness,
            "SELECT count(*) FROM core.store_purchase_tokens t "
            "JOIN core.external_identities i ON i.user_id = t.user_id "
            "WHERE i.issuer = :issuer AND i.subject = :s",
            {"issuer": harness.issuer, "s": subject})
        return identities, users, tokens

    async def test_the_first_run_creates_the_account(self, twice):
        assert isinstance(twice["first"].result, uuid.UUID)
        assert twice["counts_after_first"] == (1, 1, 2)

    async def test_the_second_run_rejects_rather_than_returning_idempotent_success(self, twice):
        """Not "already created, here you go" -- a 409 whose remediation is `/auth/sync`."""
        assert outcome_name(twice["second"]) == "IdentityAlreadyLinked"

    async def test_the_second_run_changes_no_row_count(self, twice):
        assert twice["counts_after_second"] == twice["counts_after_first"]

    async def test_the_second_run_overwrites_nothing_on_the_first_runs_row(self, twice, harness):
        """Identical before and after: the second run declared a different provider and uid, and neither landed."""
        after_second = await read(
            harness,
            "SELECT provider::text, provider_uid, user_id FROM core.external_identities "
            "WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": twice["subject"]})
        assert after_second == twice["row_after_first"]
        assert after_second[0][0] == IdentityProvider.google.value

    async def test_the_second_run_consumed_its_own_challenge(self, harness, twice):
        rows = await read(
            harness,
            "SELECT consumed_at IS NOT NULL FROM core.auth_challenges WHERE id = :id",
            {"id": twice["second"].challenge_row_id})
        assert rows == [(True,)]
