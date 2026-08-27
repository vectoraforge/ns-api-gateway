"""No partial account, ever: a failed business insert leaves nothing, while the challenge consumption commits."""
import ast
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth import creation
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import create_account
from nativespeaker.api.auth.exceptions import AuthRejected, IdentityAlreadyLinked
from nativespeaker.api.auth.keys import HmacConfig, HmacKeyring
from nativespeaker.api.models.identities import IdentityProvider

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
KEY_MATERIAL = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # 32 bytes, base64 -- test-only

# The names the production arm now writes as literals inline. Declared here so the cases below read
# plainly, and checked against the source itself below, so neither side can be renamed alone.
RACE_CONSTRAINT_NAMES = ("external_identities_issuer_subject_key",
                         "external_identities_user_id_key")
PROVIDER_ACCOUNT_INDEX_NAME = "ix_external_identities_provider_account"


def constraint_names_in_the_source() -> set[str]:
    """Every constraint name the transaction names, read off the code rather than re-declared here."""
    tree = ast.parse(Path(creation.__file__).read_text())
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and "external_identities" in node.value}

# Every UNIQUE *constraint* on the table, with its columns, read from the live catalog.
_UNIQUE_CONSTRAINTS = """
SELECT c.conname,
       (SELECT array_agg(a.attname::text ORDER BY a.attname)
          FROM unnest(c.conkey) AS k(attnum)
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS cols
  FROM pg_constraint c
 WHERE c.conrelid = 'core.external_identities'::regclass AND c.contype = 'u'
"""

# The partial unique index, which pg_constraint does not know about at all; asyncpg still reports its name.
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
        """A connection that is not the one the transaction under test used, so "committed" means committed."""
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
                # Users last: the identity FK is ON DELETE RESTRICT, so the identity rows have to go first.
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
                          route="/auth/create-user",
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
    """Commit one challenge already claimed under attempt_id, which is the state the consuming transaction sees."""
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
    """A real session whose hook lets a second connection commit a row between the re-resolution and the insert."""

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
        """The two fields the transaction reads, built rather than re-read so the read counter stays meaningful."""

        id = row_id
        challenge_id = challenge_id_value

    store = ChallengeStore(keyring())
    async with harness.factory() as real_session:
        session = _RacingSession(real_session, after_first_read)
        try:
            result = await create_account(session,
                                          context=ctx,
                                          identity=ctx.identity,
                                          challenge=_Challenge(),
                                          provider=provider,
                                          provider_uid=provider_uid,
                                          email=None,
                                          challenge_store=store)
        except AuthRejected as rejection:
            # The route's own except arm (`routers/auth.py::_complete`): a rejection after the claim
            # consumes and commits before the client is answered. That commit surviving the
            # savepoint rollback is the property this file exists to measure, so the driver has to
            # perform it here rather than leaving half the choreography out.
            await store.consume(session,
                                challenge_id=challenge_id_value,
                                claim_attempt_id=ctx.attempt_id,
                                now=ctx.evaluated_at)
            await session.commit()
            result = rejection
    return result, row_id, challenge_id_value


class TestTheConstraintNamesInTheCodeAreTheOnesPostgresReports:
    """The discrimination keys are literals in the source and the names are generated, so a rename breaks here."""

    def test_the_source_names_exactly_the_three_constraints_this_file_declares(self):
        """The helper and its two constants were deleted, so the literals in the arm are the declaration."""
        assert constraint_names_in_the_source() == {*RACE_CONSTRAINT_NAMES,
                                                    PROVIDER_ACCOUNT_INDEX_NAME}

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
    """No partial account, forced on the second insert by an (issuer, subject) conflict."""

    @pytest_asyncio.fixture
    async def collided(self, harness):
        """Run one creation whose contested identity row is committed mid-transaction; its user exists first."""
        subject = f"contested-{uuid.uuid4().hex[:8]}"
        winner_user = await commit_user(harness)
        users_before = await scalar(harness, "SELECT count(*) FROM core.users")
        tokens_before = await scalar(harness, "SELECT count(*) FROM core.store_purchase_tokens")
        observed: dict = {}

        async def seed_the_winner():
            # Recorded so the premise is checked: at the hook, re-resolution has run and there is still no row.
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
        """The premise, checked: had the contested row existed at re-resolution, no savepoint would be used."""
        assert collided["observed"]["identities_at_hook_time"] == 0

    async def test_the_conflict_earns_its_client_class_rather_than_escaping(self, collided):
        """The uniqueness violation earns its client class rather than surfacing as a generic 500."""
        assert isinstance(collided["result"], IdentityAlreadyLinked)
        assert collided["result"].error_class.status == 409

    async def test_no_users_row_survives_the_rollback(self, harness, collided):
        assert await scalar(harness, "SELECT count(*) FROM core.users") == collided["users_before"]

    async def test_no_attribution_token_survives_the_rollback(self, harness, collided):
        """A rejected completion mints nothing."""
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
        """No merge and no overwrite: an overwrite would be visible here as a NULL provider_uid."""
        found = await row(
            harness,
            "SELECT user_id, provider::text, provider_uid FROM core.external_identities "
            "WHERE issuer = :issuer AND subject = :s",
            {"issuer": harness.issuer, "s": collided["subject"]})
        assert found[0] == collided["winner_user"]
        assert found[1] == "google"
        assert found[2] == f"winner-{collided['subject']}"

    async def test_the_challenge_consumption_committed_despite_the_rollback(self, harness, collided):
        """The savepoint's reason for existing: without it this row would still be claimed, and replayable."""
        found = await row(
            harness,
            "SELECT consumed_at, preauth_subject_hash FROM core.auth_challenges WHERE id = :id",
            {"id": collided["challenge_row_id"]})
        assert found[0] is not None
        assert found[1] is None, "consumption clears the verifier in the same state transition"


class TestAConflictOnTheAttributionTokenInsertAlsoUndoesTheFirstTwo:
    """The attribution key is a fresh uuid4, so the generator is pinned; the collision raised is a real one."""

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
        """No member of the rejection family describes an attribution collision, so raising one would lie."""
        assert isinstance(token_collision["error"], IntegrityError)

    async def test_no_users_row_survives_a_third_insert_failure(self, harness, token_collision):
        assert await scalar(harness, "SELECT count(*) FROM core.users") == \
            token_collision["users_before"]

    async def test_no_identity_row_survives_a_third_insert_failure(self, harness, token_collision):
        """The identity row went in before the token that failed, so a narrower savepoint would leave it."""
        assert await scalar(harness, "SELECT count(*) FROM core.external_identities") == \
            token_collision["identities_before"]

    async def test_no_attribution_token_survives_for_the_would_be_user(self, harness,
                                                                       token_collision):
        found = await scalar(
            harness,
            "SELECT count(*) FROM core.store_purchase_tokens WHERE provider = 'google_play'")
        assert found == 0


class TestTheHappyPathStillCommitsEverything:
    """The control: without it every count above is equally consistent with a transaction writing nothing."""

    async def test_an_uncontested_creation_commits_one_user_one_identity_and_two_tokens(self,
                                                                                       harness):
        subject = f"uncontested-{uuid.uuid4().hex[:8]}"
        result, row_id, _ = await run_creation(harness, subject=subject,
                                               provider=IdentityProvider.anonymous,
                                               provider_uid=None)
        assert isinstance(result, uuid.UUID)

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
