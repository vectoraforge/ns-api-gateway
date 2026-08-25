"""ROADMAP criterion 3, against a real committing PostgreSQL: no partial account, ever.

§02 step 12 asks for two things at once, and they pull in opposite directions: a failed business
insert must leave **nothing** behind, while the challenge consumption that records the attempt was
spent must **survive** it and commit. A savepoint is the mechanism, and neither half of the
requirement is expressible against a mock -- "rolled back" and "committed" are claims about what
the database did, so this module makes the database do it.

**Where this lives, and why not `tests/e2e/`.** That package wraps every test in one outer
transaction with savepoint-joined sessions, so nothing it writes is ever committed and two
"concurrent" sessions share one connection. Both halves above would be unobservable there, and
adding a commit-for-real fixture to that package would defeat the isolation every other module in
it relies on. `tests/schema/` already owns a disposable scratch database with per-test connections
and is the only harness in the repo that can commit.

**This module imports application code and commits**, following the exception
`test_store_purchase_tokens.py` documents at length for RESEARCH A2 -- the same reasoning applies
unchanged and is not restated here. It cleans up after itself: every row it writes is keyed to a
per-test random issuer, and the fixture deletes them in FK order on teardown.

**The failure is forced the way production would hit it, not by patching the code under test.** For
the `(issuer, subject)` conflict a second connection commits the contested row at the one moment
that matters -- after this attempt's re-resolution has already seen an unlinked subject and before
its insert -- which is exactly §02 step 12's "two completions that both observed an unlinked
subject". The one case that cannot be arranged that way is the attribution-token conflict, whose
key is a fresh `uuid4()` by design and therefore unpredictable; that case pins the RNG so the value
is knowable, and the collision PostgreSQL then raises is entirely real.
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth import creation
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import ClientIpBucketKind, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import (
    PROVIDER_ACCOUNT_INDEX_NAME,
    RACE_CONSTRAINT_NAMES,
    create_account,
)
from nativespeaker.api.auth.keys import HmacConfig, HmacKeyring
from nativespeaker.api.auth.registry import lookup
from nativespeaker.api.models.auth import AuthEventResult
from nativespeaker.api.models.identities import IdentityProvider

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
KEY_MATERIAL = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # 32 bytes, base64 -- test-only

# Every UNIQUE *constraint* on the table, with its columns, read from the live catalog.
_UNIQUE_CONSTRAINTS = """
SELECT c.conname,
       (SELECT array_agg(a.attname::text ORDER BY a.attname)
          FROM unnest(c.conkey) AS k(attnum)
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS cols
  FROM pg_constraint c
 WHERE c.conrelid = 'core.external_identities'::regclass AND c.contype = 'u'
"""

# The partial unique *index*, which `pg_constraint` does not know about at all -- a standalone
# `CREATE UNIQUE INDEX ... WHERE ...` is not a constraint. asyncpg still reports it by name.
_PARTIAL_UNIQUE_INDEXES = """
SELECT i.relname,
       (SELECT array_agg(a.attname::text ORDER BY a.attname)
          FROM unnest(x.indkey) AS k(attnum)
          JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum) AS cols
  FROM pg_index x
  JOIN pg_class i ON i.oid = x.indexrelid
 WHERE x.indrelid = 'core.external_identities'::regclass
   AND x.indisunique AND x.indpred IS NOT NULL
"""


@dataclass
class _Harness:
    """A committing session factory over the scratch database, plus this test's private issuer."""

    engine: object
    factory: async_sessionmaker
    issuer: str
    owned_user_ids: list[uuid.UUID] = field(default_factory=list)

    async def connection(self):
        """A connection that is **not** the one the transaction under test used.

        Every read-back below goes through this, so "committed" means committed rather than
        "visible to the session that wrote it".
        """
        return self.engine.begin()  # ty: ignore[possibly-unbound-attribute]


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    subject = _Harness(engine=engine,
                       factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                  expire_on_commit=False),
                       issuer=f"ns-atomicity-{uuid.uuid4().hex[:12]}")
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
                # Users last: the identity FK is ON DELETE RESTRICT, so the identity rows above
                # have to go first. `core.store_purchase_tokens` cascades from the user.
                for user_id in {*subject.owned_user_ids, *(row[0] for row in rows)}:
                    await conn.execute(text("DELETE FROM core.users WHERE id = :id"),
                                       {"id": user_id})
        finally:
            await engine.dispose()


def keyring() -> HmacKeyring:
    return HmacKeyring(HmacConfig(active_version=1, keys={1: KEY_MATERIAL}))



def context(harness: _Harness, subject: str) -> RequestContext:
    """The production route metadata, looked up rather than hand-built."""
    return RequestContext(identity=PreAuthIdentity(issuer=harness.issuer, subject=subject),
                          route_metadata=lookup("POST", "/auth/create-user"),
                          client_ip_bucket_kind=ClientIpBucketKind.ipv4,
                          evaluated_at=NOW,
                          attempt_id=uuid.uuid4())


async def commit_user(harness: _Harness, *, active: bool = True) -> uuid.UUID:
    """Commit one `core.users` row on its own connection and register it for teardown."""
    user_id = uuid.uuid4()
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("INSERT INTO core.users (id, active, created_at, updated_at) "
                 "VALUES (:id, :active, :now, :now)"),
            {"id": user_id, "active": active, "now": NOW})
    harness.owned_user_ids.append(user_id)
    return user_id


async def commit_identity(harness: _Harness, *, user_id: uuid.UUID, subject: str,
                          provider: str = "anonymous", provider_uid: str | None = None) -> None:
    """Commit one ACTIVE `core.external_identities` row on its own connection."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        await conn.execute(
            text("INSERT INTO core.external_identities "
                 "(id, user_id, issuer, subject, provider, provider_uid, identity_state, "
                 " created_at, updated_at) "
                 "VALUES (:id, :user_id, :issuer, :subject, CAST(:provider AS core.identity_provider), "
                 "        :provider_uid, 'active', :now, :now)"),
            {"id": uuid.uuid4(), "user_id": user_id, "issuer": harness.issuer, "subject": subject,
             "provider": provider, "provider_uid": provider_uid, "now": NOW})


async def commit_claimed_challenge(harness: _Harness, *, subject: str,
                                   attempt_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    """Commit one challenge row already claimed under `attempt_id`, as step 5 would have left it.

    The consuming transaction is step 10 onward; it never claims and never re-checks expiry, so the
    row it is handed is a claimed one. `preauth_subject_hash` is the real derivation under the
    production keyring -- the table's binding CHECK requires a non-NULL value here until
    consumption clears it, and consumption clearing it is one of the things asserted below.
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


async def scalar(harness: _Harness, sql: str, params: dict | None = None):
    """Run one read on a fresh connection, outside every session under test."""
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        return (await conn.execute(text(sql), params or {})).scalar()


async def row(harness: _Harness, sql: str, params: dict | None = None):
    async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
        return (await conn.execute(text(sql), params or {})).first()


class _RacingSession:
    """A real session that lets a *second* connection commit a row right after this one's read.

    The wrapping is the point: `create_account` is called unmodified and issues exactly the
    statements it always issues, while the hook fires between its re-resolution and its insert --
    the window §02 step 12 is about. Racing two threads and hoping to land in that window would
    prove the same thing far less often and far less repeatably.
    """

    def __init__(self, session, after_first_read) -> None:
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


async def run_creation(harness: _Harness, *, subject: str, provider: IdentityProvider,
                       provider_uid: str | None, after_first_read=None,
                       ctx: RequestContext | None = None,
                       challenge: tuple[uuid.UUID, str] | None = None):
    """Drive the production consuming transaction once, on its own real session."""
    ctx = ctx or context(harness, subject)
    row_id, challenge_id_value = challenge or await commit_claimed_challenge(
        harness, subject=subject, attempt_id=ctx.attempt_id)

    class _Challenge:
        """The two fields the transaction reads, both taken from the row committed above.

        The non-secret `id` is what the tests below correlate on; the handle is what `consume`
        matches. Building this rather than re-reading the row keeps the transaction under test the
        only thing issuing statements on its session, so the read counter above stays meaningful.
        """

        id = row_id
        challenge_id = challenge_id_value

    async with harness.factory() as real_session:
        session = _RacingSession(real_session, after_first_read)
        result = await create_account(session,
                                      context=ctx,
                                      identity=ctx.identity,
                                      challenge=_Challenge(),
                                      provider=provider,
                                      provider_uid=provider_uid,
                                      email=None,
                                      challenge_store=ChallengeStore(keyring()))
    return result, row_id, challenge_id_value


class TestTheConstraintNamesInTheCodeAreTheOnesPostgresReports:
    """The discrimination keys are literals in `auth/creation.py`; the catalog is the authority.

    The migration names none of these rules explicitly, so all three names are generated and are
    not a stable contract. Asserting the literals against `pg_constraint` and `pg_class` here is
    what makes a rename break a test instead of silently turning every conflict into an unmapped
    re-raise -- which would surface to a client as a 500 rather than as its earned 409.
    """

    async def test_the_two_race_constraints_are_named_as_the_module_declares(self, harness):
        async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
            rows = (await conn.execute(text(_UNIQUE_CONSTRAINTS))).all()
        by_columns = {frozenset(cols): name for name, cols in rows}

        assert by_columns[frozenset({"issuer", "subject"})] == \
            "external_identities_issuer_subject_key"
        assert by_columns[frozenset({"user_id"})] == "external_identities_user_id_key"
        assert set(by_columns.values()) == set(RACE_CONSTRAINT_NAMES)

    async def test_the_provider_account_reservation_is_the_index_the_module_declares(self, harness):
        async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
            rows = (await conn.execute(text(_PARTIAL_UNIQUE_INDEXES))).all()

        assert [(name, sorted(cols)) for name, cols in rows] == \
            [(PROVIDER_ACCOUNT_INDEX_NAME, ["issuer", "provider", "provider_uid"])]


class TestAConflictOnTheIdentityInsertLeavesNoPartialAccount:
    """Criterion 3, forced on the second insert -- §02 step 12's `(issuer, subject)` conflict."""

    @pytest_asyncio.fixture
    async def collided(self, harness):
        """Run one creation whose contested identity row is committed mid-transaction.

        The seeded row's user exists *before* the run, so the `core.users` count taken here changes
        only if the rolled-back attempt left its own user row behind -- which is the whole question.
        """
        subject = f"contested-{uuid.uuid4().hex[:8]}"
        winner_user = await commit_user(harness)
        users_before = await scalar(harness, "SELECT count(*) FROM core.users")
        tokens_before = await scalar(harness, "SELECT count(*) FROM core.store_purchase_tokens")
        observed: dict = {}

        async def seed_the_winner():
            # Recorded so the premise is checked rather than assumed: at the instant the hook
            # fires, the re-resolution has already run and there is still no row for the pair.
            # That is §02 step 12's "two completions that both observed an unlinked subject", and
            # without this reading the whole case could be passing through the no-mutation arm.
            observed["identities_at_hook_time"] = await scalar(
                harness,
                "SELECT count(*) FROM core.external_identities "
                "WHERE issuer = :issuer AND subject = :s",
                {"issuer": harness.issuer, "s": subject})
            await commit_identity(harness, user_id=winner_user, subject=subject,
                                  provider="google", provider_uid=f"winner-{subject}")

        result, row_id, _ = await run_creation(harness, subject=subject,
                                               provider=IdentityProvider.anonymous,
                                               provider_uid=None,
                                               after_first_read=seed_the_winner)
        return {"result": result, "subject": subject, "challenge_row_id": row_id,
                "winner_user": winner_user, "users_before": users_before,
                "tokens_before": tokens_before, "observed": observed}

    async def test_the_attempt_genuinely_observed_an_unlinked_subject_first(self, collided):
        """The premise, checked. If the contested row had existed at re-resolution time the case
        would be exercising the no-mutation arm instead -- same result, none of the savepoint --
        and every count below would pass while proving nothing about a rollback."""
        assert collided["observed"]["identities_at_hook_time"] == 0

    async def test_the_conflict_earns_its_client_class_rather_than_escaping(self, collided):
        """§02 step 12: the uniqueness violation must never surface as a generic 500 (T-37-46).

        Reaching this assertion at all is half the proof -- an unhandled `IntegrityError` or a
        `PendingRollbackError` would have raised out of the fixture.
        """
        assert collided["result"] is AuthEventResult.identity_already_linked

    async def test_no_users_row_survives_the_rollback(self, harness, collided):
        assert await scalar(harness, "SELECT count(*) FROM core.users") == collided["users_before"]

    async def test_no_attribution_token_survives_the_rollback(self, harness, collided):
        """A rejected completion mints nothing (§02 step 10)."""
        assert await scalar(harness, "SELECT count(*) FROM core.store_purchase_tokens") == \
            collided["tokens_before"]

    async def test_exactly_one_identity_row_exists_for_the_contested_pair(self, harness, collided):
        """The seeded one. Not two, not a merged one, and not the loser's."""
        found = await scalar(
            harness,
            "SELECT count(*) FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": collided["subject"]})
        assert found == 1

    async def test_the_winners_row_is_untouched(self, harness, collided):
        """No merge and no overwrite: the loser's classified provider was `anonymous`, so a
        surviving overwrite would be visible here as a NULL `provider_uid` (T-37-43)."""
        found = await row(
            harness,
            "SELECT user_id, provider::text, provider_uid FROM core.external_identities "
            "WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": collided["subject"]})
        assert found[0] == collided["winner_user"]
        assert found[1] == "google"
        assert found[2] == f"winner-{collided['subject']}"

    async def test_the_challenge_consumption_committed_despite_the_rollback(self, harness, collided):
        """The savepoint's reason for existing, read back over a fresh connection.

        Without it the consume would have raised `PendingRollbackError` on a poisoned session and
        this row would still be claimed -- replayable, with the rejection unrecorded (T-37-42).
        """
        found = await row(
            harness,
            "SELECT consumed_at, preauth_subject_hash FROM core.auth_challenges WHERE id = :id",
            {"id": collided["challenge_row_id"]})
        assert found[0] is not None
        assert found[1] is None, "consumption clears the verifier in the same state transition"


class TestAConflictOnTheAttributionTokenInsertAlsoUndoesTheFirstTwo:
    """The case that exposes a savepoint scoped around only the user and the identity row.

    The attribution key is a fresh `uuid4()` by design, so the only way to make it collide is to
    know what it will be. Pinning the generator is not simulating the failure -- PostgreSQL raises
    a real `store_purchase_tokens_provider_identity_value_key` violation on a real duplicate.
    """

    @pytest_asyncio.fixture
    async def token_collision(self, harness, monkeypatch):
        subject = f"token-clash-{uuid.uuid4().hex[:8]}"
        minted = uuid.uuid4()
        other_user = await commit_user(harness)
        async with harness.engine.begin() as conn:  # ty: ignore[possibly-unbound-attribute]
            await conn.execute(
                text("INSERT INTO core.store_purchase_tokens "
                     "(user_id, provider, identity_value, created_at) "
                     "VALUES (:user_id, 'apple', :value, :now)"),
                {"user_id": other_user, "value": str(minted), "now": NOW})

        users_before = await scalar(harness, "SELECT count(*) FROM core.users")
        identities_before = await scalar(harness, "SELECT count(*) FROM core.external_identities")
        monkeypatch.setattr(creation, "uuid4", lambda: minted)

        with pytest.raises(IntegrityError) as raised:
            await run_creation(harness, subject=subject, provider=IdentityProvider.anonymous,
                               provider_uid=None)
        return {"error": raised.value, "users_before": users_before,
                "identities_before": identities_before, "subject": subject}

    async def test_an_unmapped_conflict_is_not_dressed_up_as_a_business_outcome(self,
                                                                               token_collision):
        """No `AuthEventResult` member describes an attribution collision, so inventing one would
        tell a client something false about their account."""
        assert isinstance(token_collision["error"], IntegrityError)

    async def test_no_users_row_survives_a_third_insert_failure(self, harness, token_collision):
        assert await scalar(harness, "SELECT count(*) FROM core.users") == \
            token_collision["users_before"]

    async def test_no_identity_row_survives_a_third_insert_failure(self, harness, token_collision):
        """The identity row went in *before* the token that failed. If the savepoint covered only
        the first two inserts, this count would have grown by one."""
        assert await scalar(harness, "SELECT count(*) FROM core.external_identities") == \
            token_collision["identities_before"]

    async def test_no_attribution_token_survives_for_the_would_be_user(self, harness,
                                                                       token_collision):
        found = await scalar(
            harness,
            "SELECT count(*) FROM core.store_purchase_tokens WHERE provider = 'google_play'")
        assert found == 0


class TestTheHappyPathStillCommitsEverything:
    """The control. Without it, every count above is equally consistent with a transaction that
    writes nothing at all."""

    async def test_an_uncontested_creation_commits_one_user_one_identity_and_two_tokens(self,
                                                                                       harness):
        subject = f"uncontested-{uuid.uuid4().hex[:8]}"
        result, row_id, _ = await run_creation(harness, subject=subject,
                                               provider=IdentityProvider.anonymous,
                                               provider_uid=None)
        assert result is AuthEventResult.succeeded

        user_id = await scalar(
            harness,
            "SELECT user_id FROM core.external_identities WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": subject})
        assert user_id is not None
        harness.owned_user_ids.append(user_id)

        assert await scalar(harness,
                            "SELECT count(*) FROM core.store_purchase_tokens WHERE user_id = :id",
                            {"id": user_id}) == 2
        assert await scalar(harness,
                            "SELECT consumed_at FROM core.auth_challenges WHERE id = :id",
                            {"id": row_id}) is not None
