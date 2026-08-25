"""ROADMAP criterion 4: two concurrent creates for one `(issuer, subject)` yield exactly one account.

§02 step 12 makes `UNIQUE (issuer, subject)` and `UNIQUE (user_id)` the **only** arbiters between
two completions that both observed an unlinked subject. There is no advisory lock, no serializable
isolation, no generation CAS and no loser-challenge cancellation anywhere in the design, so the
only way to know the rule holds is to run two real transactions on two real connections against a
real PostgreSQL and see which rows exist afterwards. That is what this module does.

**The loser's remediation is `POST /auth/sync`** -- which is Phase 38 and is not served by this
repo yet. That is what the 409 `identity_already_linked` is telling the client to do, and it is why
the loser must never receive idempotent success: a caller told "created" would never reconcile, and
would hold a handle to an account that is not the one its identity actually resolves to.

**The interleaving is arranged, not raced.** Both attempts are driven under `asyncio.gather`, and a
two-party barrier holds each one between its in-transaction re-resolution and its first insert
until the other has also finished re-resolving. Past that barrier nothing is coordinated: both
issue their inserts concurrently and PostgreSQL decides the winner, which is the part that must not
be simulated. Racing two threads without the barrier would test the same rule only on the runs that
happened to interleave, and would pass vacuously on the runs that did not -- so the barrier makes
the *premise* reliable while leaving the *outcome* genuinely up to the database. Each attempt also
records the identity-row count at its own barrier arrival, so "both observed an unlinked subject"
is asserted rather than assumed.

**This module imports application code and commits**, per the exception
`test_store_purchase_tokens.py` documents; and it drives `create_account` directly rather than
going over HTTP, because the race is a property of the database and a second transport would add a
variable without adding evidence.
"""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import create_account
from nativespeaker.api.auth.keys import HmacConfig, HmacKeyring
from nativespeaker.api.models.auth import AuthEventResult
from nativespeaker.api.models.identities import IdentityProvider

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
KEY_MATERIAL = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # 32 bytes, base64 -- test-only

# A barrier that is never reached means a coroutine failed before its re-resolution, and its partner
# would otherwise wait for it forever. Bounded so that shows up as a failure, not as a hung suite.
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


def keyring() -> HmacKeyring:
    return HmacKeyring(HmacConfig(active_version=1, keys={1: KEY_MATERIAL}))



async def read(harness: _Harness, sql: str, params: dict | None = None):
    """One read on a connection of its own -- never the one an attempt under test used."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        return (await conn.execute(text(sql), params or {})).all()


async def scalar(harness: _Harness, sql: str, params: dict | None = None):
    rows = await read(harness, sql, params)
    return rows[0][0] if rows else None


async def commit_claimed_challenge(harness: _Harness, *, subject: str,
                                   attempt_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    """One challenge row already claimed under `attempt_id`, as §02 step 5 would have left it.

    Each attempt gets its **own** challenge. That is not a convenience: §02 step 12 forbids
    cancelling the loser's challenge beyond single-use, and both attempts must consume their own.
    """
    row_id = uuid.uuid4()
    challenge_id = f"handle-{uuid.uuid4().hex[:16]}"
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("INSERT INTO core.auth_challenges "
                 "(id, challenge_id, operation, preauth_issuer, preauth_subject_hash, "
                 " expires_at, claimed_at, claim_attempt_id, created_at) "
                 "VALUES (:id, :challenge_id, 'create_user', :issuer, :hash, "
                 "        :expires_at, :now, :attempt_id, :now)"),
            {"id": row_id, "challenge_id": challenge_id, "issuer": harness.issuer,
             "hash": keyring().actor_subject_hash(harness.issuer, subject),
             "expires_at": NOW + timedelta(seconds=300), "now": NOW, "attempt_id": attempt_id})
    return row_id, challenge_id


class _HookedSession:
    """A real session that runs a callback once, immediately after its first read.

    `create_account` is driven unmodified; the wrapper only observes. The first read is the
    in-transaction re-resolution, so the callback fires in exactly the window §02 step 12 is about.
    """

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
    context: RequestContext
    challenge_row_id: uuid.UUID
    challenge_id: str
    result: AuthEventResult | None = None
    identities_seen_at_barrier: int | None = None


async def prepare_attempt(harness: _Harness, *, subject: str, provider: IdentityProvider,
                          provider_uid: str | None) -> _Attempt:
    context = RequestContext(identity=PreAuthIdentity(issuer=harness.issuer, subject=subject),
                             route="/auth/create-user",
                             evaluated_at=NOW,
                             attempt_id=uuid.uuid4())
    row_id, challenge_id = await commit_claimed_challenge(harness, subject=subject,
                                                          attempt_id=context.attempt_id)
    return _Attempt(subject=subject, provider=provider, provider_uid=provider_uid,
                    context=context, challenge_row_id=row_id, challenge_id=challenge_id)


async def run_attempt(harness: _Harness, attempt: _Attempt, after_first_read=None) -> _Attempt:
    """Drive the production consuming transaction once, on its own session and connection."""
    stored = type("_Challenge", (), {"id": attempt.challenge_row_id,
                                     "challenge_id": attempt.challenge_id})()
    async with harness.factory() as real_session:
        attempt.result = await create_account(_HookedSession(real_session, after_first_read),
                                              context=attempt.context,
                                              identity=attempt.context.identity,
                                              challenge=stored,
                                              provider=attempt.provider,
                                              provider_uid=attempt.provider_uid,
                                              email=None,
                                              challenge_store=ChallengeStore(keyring()))
    return attempt


def barrier_for(harness: _Harness, attempt: _Attempt, mine: asyncio.Event, theirs: asyncio.Event):
    """Announce that this attempt has re-resolved, then wait for its partner to do the same.

    Recording the identity-row count first is what makes the premise checkable: both attempts must
    have seen an unlinked subject, or the case is exercising the no-mutation arm and proving
    nothing about the constraint.
    """

    async def hold() -> None:
        attempt.identities_seen_at_barrier = await scalar(
            harness,
            "SELECT count(*) FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": attempt.subject})
        mine.set()
        await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)

    return hold


class TestTwoConcurrentCompletionsProduceExactlyOneAccount:
    """Criterion 4. The database arbitrates; nothing in the application does."""

    @pytest_asyncio.fixture
    async def raced(self, harness):
        """Two attempts on the same `(issuer, subject)`, released together past the barrier.

        Their classified providers deliberately **differ** -- one google, one apple. Two attempts
        can legitimately classify differently if the provider record changed between their reads,
        and the difference is what makes a merge or an overwrite visible: the surviving row must
        carry the winner's pair and nothing of the loser's.
        """
        subject = f"contested-{uuid.uuid4().hex[:8]}"
        first = await prepare_attempt(harness, subject=subject, provider=IdentityProvider.google,
                                      provider_uid=f"google-uid-{subject}")
        second = await prepare_attempt(harness, subject=subject, provider=IdentityProvider.apple,
                                       provider_uid=f"apple-uid-{subject}")

        first_ready, second_ready = asyncio.Event(), asyncio.Event()
        await asyncio.gather(
            run_attempt(harness, first, barrier_for(harness, first, first_ready, second_ready)),
            run_attempt(harness, second, barrier_for(harness, second, second_ready, first_ready)))

        by_result = {attempt.result: attempt for attempt in (first, second)}
        return {"subject": subject, "attempts": (first, second), "by_result": by_result}

    async def test_both_attempts_observed_an_unlinked_subject(self, raced):
        """§02 step 12's premise. Without this the case could be two sequential creations."""
        assert [attempt.identities_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_exactly_one_succeeded_and_the_other_is_already_linked(self, raced):
        """Never two successes, and never idempotent success for the loser: the loser is being
        told to reconcile through `/auth/sync`, which is a different instruction from "created"."""
        assert set(raced["by_result"]) == {AuthEventResult.succeeded,
                                           AuthEventResult.identity_already_linked}

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
        """A `core.users` row with no identity row is §02's partial account (T-37-45). Every user
        this test's issuer could have produced is reachable through an identity row, so any extra
        one is an orphan."""
        assert await scalar(
            harness,
            "SELECT count(*) FROM core.users u WHERE u.created_at = :now "
            "AND NOT EXISTS (SELECT 1 FROM core.external_identities i WHERE i.user_id = u.id)",
            {"now": NOW}) == 0

    async def test_the_surviving_row_carries_the_winners_pair_and_none_of_the_losers(self, harness,
                                                                                    raced):
        """No merge, no overwrite (T-37-43). The two attempts classified differently on purpose, so
        a row carrying the loser's provider or uid would be visible here rather than invisible
        behind two identical values."""
        winner = raced["by_result"][AuthEventResult.succeeded]
        loser = raced["by_result"][AuthEventResult.identity_already_linked]
        rows = await read(
            harness,
            "SELECT provider::text, provider_uid FROM core.external_identities "
            "WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": raced["subject"]})

        assert rows == [(winner.provider.value, winner.provider_uid)]
        assert rows[0][1] != loser.provider_uid

    async def test_the_winner_minted_two_tokens_and_the_loser_none(self, harness, raced):
        """"A rejected or replayed completion mints nothing" (§02 step 10), and the winner gets
        exactly one row per store -- so the total for the contested pair is two, not four."""
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
        """The loser consumes too (§02 step 13): every rejection at or after the provider read
        does, and retry requires a fresh prepare rather than a replay of this one."""
        for attempt in raced["attempts"]:
            rows = await read(
                harness,
                "SELECT consumed_at, preauth_subject_hash FROM core.auth_challenges WHERE id = :id",
                {"id": attempt.challenge_row_id})
            assert rows[0][0] is not None, f"{attempt.result} left its challenge unconsumed"
            assert rows[0][1] is None


class TestRunningTheSameCreationTwiceSequentially:
    """The "runs twice on the same input" question, answered beside the concurrent one.

    Both answers must be the same -- one account, the second call rejects, nothing extra minted --
    and they arrive by different routes: the concurrent loser is rejected by the constraint, the
    sequential one by the in-transaction re-resolution that finds the committed row.
    """

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
        assert twice["first"].result is AuthEventResult.succeeded
        assert twice["counts_after_first"] == (1, 1, 2)

    async def test_the_second_run_rejects_rather_than_returning_idempotent_success(self, twice):
        """Not "already created, here you go" -- a 409 whose remediation is `/auth/sync`."""
        assert twice["second"].result is AuthEventResult.identity_already_linked

    async def test_the_second_run_changes_no_row_count(self, twice):
        assert twice["counts_after_second"] == twice["counts_after_first"]

    async def test_the_second_run_overwrites_nothing_on_the_first_runs_row(self, twice, harness):
        """Byte-identical before and after, including the `user_id`: the second run declared a
        different provider and a different uid, and neither reached the row."""
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
