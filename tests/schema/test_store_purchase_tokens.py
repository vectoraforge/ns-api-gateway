"""CREATE-03 / RESEARCH A2 -- `StorePurchaseToken` against the real `core.store_purchase_tokens`.

**This module is the one documented exception to this package's no-application-imports rule, and
no other module in it may follow.** `conftest.py:45` records why the rule exists: this suite has
to run while the application is knowingly broken, so it imports no application module and its
`conn` fixture is asyncpg rather than SQLAlchemy. A2 is specifically a claim *about the
SQLAlchemy mapper* -- that it accepts an ORM-level composite primary key on a table whose
database definition has none, and INSERTs correctly -- so there is nowhere else it can be
settled. A mock would prove nothing; the whole question is what PostgreSQL does. This module
therefore imports `StorePurchaseToken`, `PurchaseProvider` and `User`, and builds its own async
engine against the scratch database's DSN. If the application is broken, this module fails and
the rest of the package still runs, which is exactly the property the rule was protecting.

**Its rows are committed, not rolled back.** A2 is a claim about a committed INSERT, so the
`conn` fixture's per-test rollback would leave the load-bearing half unexercised. The harness
below therefore records every `core.users` row it creates and deletes them on teardown in a
`finally`; `core.store_purchase_tokens` has `ON DELETE CASCADE` on its user FK, so removing the
user removes its tokens. `test_grant_locks.py` is the other module in this package that commits,
and for the same kind of reason.
"""
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

from nativespeaker.api.models import PurchaseProvider, StorePurchaseToken, User

pytestmark = pytest.mark.schema

# `_schema_db_uri` is an asyncpg DSN (conftest.py builds `postgres://` deliberately, because
# asyncpg rejects the SQLAlchemy prefix). SQLAlchemy needs the dialect form of the same DSN.
_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

# Every UNIQUE constraint on the table, with its column names, read from the live catalog. The
# constraint-name assertions below compare against whatever PostgreSQL actually named these --
# a hardcoded guess at `store_purchase_tokens_user_id_provider_key` would pass for the wrong
# reason the day someone names the constraint explicitly in the migration.
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

# Teardown only. `core.store_purchase_tokens` has ON DELETE CASCADE on its user FK, so removing
# the user removes every token this module committed for it.
_DELETE_USER = text("DELETE FROM core.users WHERE id = :id")


@dataclass(frozen=True)
class _Harness:
    """A session factory over the scratch database, plus the engine and the rows to clean up."""
    factory: async_sessionmaker
    engine: object
    owned_user_ids: list[uuid.UUID]


@pytest_asyncio.fixture
async def orm(_schema_db_uri):
    """An async engine and session factory over the migrated scratch database.

    Function-scoped and disposed in a `finally`: `asyncio_default_fixture_loop_scope` is
    `function`, so an engine that outlived the test would hold connections bound to a loop that
    is already closed.
    """
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    owned: list[uuid.UUID] = []
    harness = _Harness(factory=factory, engine=engine, owned_user_ids=owned)
    try:
        yield harness
    finally:
        try:
            # Raw DELETE on its own connection rather than through the session: the ORM path is
            # `session.execute()`, which SQLModel deprecates in favour of `exec()`, and `exec()`
            # takes a select. Teardown has no reason to care either way.
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
    """Insert and commit one attribution token through the mapped class.

    `created_at` is passed explicitly because the model declares no default factory: the creating
    transaction owns the clock (35 D-02).
    """
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
    """Walk to the asyncpg exception underneath a SQLAlchemy IntegrityError.

    Reading `constraint_name` off the driver exception rather than parsing `str(exc)` is the
    whole point: the two UNIQUE rules on this table are told apart by constraint name, and a
    substring match on the message would silently accept either one.
    """
    cause = error.orig
    while cause is not None and not hasattr(cause, "constraint_name"):
        cause = cause.__cause__
    assert cause is not None, f"no asyncpg cause carrying constraint_name under {error!r}"
    return cause


class TestTheMapperCommitsAgainstAPkLessTable:
    """A2, executed. This is the assertion 37-07's create transaction rests on."""

    async def test_both_providers_commit_for_one_user_and_round_trip(self, orm):
        """One user, two tokens, two providers, committed -- then re-read.

        The ORM-level composite key is `(user_id, provider)`, so these two rows share half of it.
        If SQLAlchemy's identity map or the missing database primary key were a problem, this is
        where it would surface: at the flush, at the commit, or as one row overwriting the other.
        """
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
        # T-37-11: two rows for one user must carry *different* values. A scheme that derived the
        # token from the user's identity would produce one value twice and fail here.
        assert len({row.identity_value for row in rows}) == 2
        assert all(row.created_at is not None for row in rows)

    async def test_a_committed_token_is_visible_to_a_fresh_session(self, orm):
        """The control for the case above: re-reading through the same session could be the
        identity map answering rather than the database."""
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
        """`UNIQUE (provider, identity_value)` -- a composite, which is why the model declares no
        single-column `unique=True` on `identity_value` (T-37-13)."""
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
        """The control: the rule is the composite, not `identity_value` alone.

        Without this case, the case above is equally consistent with a single-column uniqueness
        rule -- which is the drift the model deliberately does not declare.
        """
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
    """T-37-12: nothing in this phase added one to make the mapper happy."""

    async def test_zero_primary_key_constraints(self, orm):
        rows = await _catalog(orm, _PRIMARY_KEY_CONSTRAINTS)
        assert rows[0][0] == 0, "core.store_purchase_tokens must keep its documented PK-less shape"

    async def test_the_orm_key_is_not_backed_by_a_database_key(self, orm):
        """States the A2 shape in one place: the mapper has a key the table does not."""
        assert {column.name for column in StorePurchaseToken.__table__.primary_key.columns} == \
            {"user_id", "provider"}
        rows = await _catalog(orm, _PRIMARY_KEY_CONSTRAINTS)
        assert rows[0][0] == 0
