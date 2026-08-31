"""Whether the SQLAlchemy mapper accepts an ORM-level composite key the database does not have, and commits."""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.tables import PurchaseProvider, StorePurchaseToken, User

pytestmark = pytest.mark.schema

# _schema_db_uri is an asyncpg DSN; SQLAlchemy needs the dialect form of the same string.
_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

# Read from the live catalog, so a name the migration later declares explicitly cannot pass by luck.
_UNIQUE_CONSTRAINTS = """
SELECT c.conname,
       (SELECT array_agg(a.attname::text ORDER BY a.attname)
          FROM unnest(c.conkey) AS k(attnum)
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS cols
  FROM pg_constraint c
 WHERE c.conrelid = 'core.store_purchase_tokens'::regclass
   AND c.contype = 'u'
"""

_PRIMARY_KEY_CONSTRAINTS = """
SELECT count(*) FROM pg_constraint
 WHERE conrelid = 'core.store_purchase_tokens'::regclass AND contype = 'p'
"""

# Teardown only; the token table cascades from the user FK, so deleting the user removes its tokens.
_DELETE_USER = text("DELETE FROM core.users WHERE id = :id")


@dataclass(frozen=True)
class _Harness:
    """A session factory over the scratch database, plus the engine and the rows to clean up."""
    factory: async_sessionmaker
    engine: object
    owned_user_ids: list[uuid.UUID]


@pytest_asyncio.fixture
async def orm(_schema_db_uri):
    """An async engine over the scratch database, disposed per test so no connection outlives its loop."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    owned: list[uuid.UUID] = []
    harness = _Harness(factory=factory, engine=engine, owned_user_ids=owned)
    try:
        yield harness
    finally:
        try:
            # Raw DELETE on its own connection: SQLModel's exec() takes a select, and teardown needs neither.
            async with engine.begin() as cleanup:
                for user_id in owned:
                    await cleanup.execute(_DELETE_USER, {"id": user_id})
        finally:
            await engine.dispose()


async def _commit_user(harness: _Harness) -> uuid.UUID:
    """Insert and commit one `core.users` row through the ORM, registering it for teardown."""
    user = User()
    async with harness.factory() as session:
        session.add(user)
        await session.commit()
    harness.owned_user_ids.append(user.id)
    return user.id


async def _commit_token(harness: _Harness, *, user_id: uuid.UUID, provider: PurchaseProvider,
                        identity_value: str) -> None:
    """Insert and commit one token; created_at is explicit because the creating transaction owns the clock."""
    async with harness.factory() as session:
        session.add(StorePurchaseToken(user_id=user_id, provider=provider,
                                       identity_value=identity_value,
                                       created_at=datetime.now(UTC)))
        await session.flush()
        await session.commit()


async def _catalog(harness: _Harness, sql: str):
    """Run a pg_catalog query on its own connection, outside any ORM session."""
    async with harness.engine.connect() as connection:  # ty: ignore[possibly-unbound-attribute]
        return (await connection.execute(text(sql))).all()


async def _constraint_name_for(harness: _Harness, columns: set[str]) -> str:
    """The live name of the UNIQUE constraint over exactly `columns`."""
    rows = await _catalog(harness, _UNIQUE_CONSTRAINTS)
    matches = [name for name, cols in rows if set(cols) == columns]
    assert len(matches) == 1, f"expected one UNIQUE over {sorted(columns)}, got {rows}"
    return matches[0]


def _asyncpg_cause(error: IntegrityError):
    """Walk to the asyncpg exception, so constraint_name is read off the driver rather than parsed out."""
    cause = error.orig
    while cause is not None and not hasattr(cause, "constraint_name"):
        cause = cause.__cause__
    assert cause is not None, f"no asyncpg cause carrying constraint_name under {error!r}"
    return cause


class TestTheMapperCommitsAgainstAPkLessTable:
    """A2, executed. This is the assertion 37-07's create transaction rests on."""

    async def test_both_providers_commit_for_one_user_and_round_trip(self, orm):
        """Two rows sharing half the ORM composite key commit and re-read, neither overwriting the other."""
        user_id = await _commit_user(orm)
        minted = {
            PurchaseProvider.apple: str(uuid.uuid4()),
            PurchaseProvider.google_play: str(uuid.uuid4()),
        }
        for provider, identity_value in minted.items():
            await _commit_token(orm, user_id=user_id, provider=provider,
                                identity_value=identity_value)

        async with orm.factory() as session:
            rows = (await session.exec(
                select(StorePurchaseToken).where(StorePurchaseToken.user_id == user_id)
            )).all()

        assert {row.provider for row in rows} == {PurchaseProvider.apple,
                                                  PurchaseProvider.google_play}
        assert {row.identity_value for row in rows} == set(minted.values())
        # Two rows for one user must differ: a token derived from the user's identity would repeat here.
        assert len({row.identity_value for row in rows}) == 2
        assert all(row.created_at is not None for row in rows)

    async def test_a_committed_token_is_visible_to_a_fresh_session(self, orm):
        """The control: re-reading through the same session could be the identity map, not the database."""
        user_id = await _commit_user(orm)
        identity_value = str(uuid.uuid4())
        await _commit_token(orm, user_id=user_id, provider=PurchaseProvider.apple,
                            identity_value=identity_value)

        rows = await _catalog(orm, _UNIQUE_CONSTRAINTS)  # forces a second connection to exist
        assert rows

        async with orm.factory() as session:
            found = (await session.exec(
                select(StorePurchaseToken).where(StorePurchaseToken.user_id == user_id)
            )).all()
        assert [row.identity_value for row in found] == [identity_value]


class TestTheDatabaseOwnsTheUniquenessRules:
    """Both UNIQUE constraints fire, and are told apart by name rather than by message text."""

    async def test_one_token_per_user_per_store(self, orm):
        """`UNIQUE (user_id, provider)` -- the rule the ORM key mirrors."""
        user_id = await _commit_user(orm)
        await _commit_token(orm, user_id=user_id, provider=PurchaseProvider.apple,
                            identity_value=str(uuid.uuid4()))

        with pytest.raises(IntegrityError) as exc_info:
            await _commit_token(orm, user_id=user_id, provider=PurchaseProvider.apple,
                                identity_value=str(uuid.uuid4()))

        expected = await _constraint_name_for(orm, {"user_id", "provider"})
        assert _asyncpg_cause(exc_info.value).constraint_name == expected

    async def test_one_owner_per_provider_identity_value(self, orm):
        """UNIQUE (provider, identity_value) is a composite, so the model declares no single-column unique."""
        first_user = await _commit_user(orm)
        second_user = await _commit_user(orm)
        identity_value = str(uuid.uuid4())
        await _commit_token(orm, user_id=first_user, provider=PurchaseProvider.google_play,
                            identity_value=identity_value)

        with pytest.raises(IntegrityError) as exc_info:
            await _commit_token(orm, user_id=second_user, provider=PurchaseProvider.google_play,
                                identity_value=identity_value)

        expected = await _constraint_name_for(orm, {"provider", "identity_value"})
        assert _asyncpg_cause(exc_info.value).constraint_name == expected

    async def test_the_same_identity_value_is_free_under_a_different_provider(self, orm):
        """The control: the rule is the composite, not identity_value alone."""
        user_id = await _commit_user(orm)
        identity_value = str(uuid.uuid4())
        await _commit_token(orm, user_id=user_id, provider=PurchaseProvider.apple,
                            identity_value=identity_value)
        await _commit_token(orm, user_id=user_id, provider=PurchaseProvider.google_play,
                            identity_value=identity_value)

        async with orm.factory() as session:
            rows = (await session.exec(
                select(StorePurchaseToken).where(StorePurchaseToken.user_id == user_id)
            )).all()
        assert len(rows) == 2


class TestTheTableStillHasNoPrimaryKey:
    """The table is deliberately PK-less, and nothing was added to make the mapper happy."""

    async def test_zero_primary_key_constraints(self, orm):
        rows = await _catalog(orm, _PRIMARY_KEY_CONSTRAINTS)
        assert rows[0][0] == 0, "core.store_purchase_tokens must keep its documented PK-less shape"

    async def test_the_orm_key_is_not_backed_by_a_database_key(self, orm):
        """States the A2 shape in one place: the mapper has a key the table does not."""
        assert {column.name for column in StorePurchaseToken.__table__.primary_key.columns} == \
            {"user_id", "provider"}
        rows = await _catalog(orm, _PRIMARY_KEY_CONSTRAINTS)
        assert rows[0][0] == 0
