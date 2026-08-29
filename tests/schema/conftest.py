"""Fixtures for the schema-conformance suite -- a scratch crud, a fresh apply, per-test rollback."""
import asyncio
import os
import pathlib
import re

import asyncpg
import pytest
import pytest_asyncio
from pogo_core.util import testing as pogo_testing

from schema.helpers import insert_tier

# pogo_core.util.testing, not pogo_migrate.testing: the latter reads DB_* eagerly and raises when unset.

MIGRATIONS = pathlib.Path(__file__).parents[2] / "migrations"
POGO_SCHEMA = "api"  # matches [tool.pogo] schema
SCHEMA_TEST_DB = "ns_schema_test"

# Defaults so the suite runs with DB_* unset; DB_NAME falls back to the maintenance crud, which exists.
_DB_DEFAULTS = {
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_USER": "postgres",
    "DB_PASSWORD": "postgres",
    "DB_NAME": "postgres",
}

# A crud name cannot be bound as a parameter, so CREATE/DROP DATABASE interpolate it behind this guard.
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def _env(name: str) -> str:
    """Read a DB_* variable, falling back to its .env.example default."""
    return os.environ.get(name) or _DB_DEFAULTS[name]


# postgres:// and not postgresql+asyncpg://: asyncpg rejects the SQLAlchemy prefix, and no app module is imported.
def dsn_for(database: str) -> str:
    """Build an asyncpg DSN for one crud."""
    return (
        f"postgres://{_env('DB_USER')}:{_env('DB_PASSWORD')}"
        f"@{_env('DB_HOST')}:{_env('DB_PORT')}/{database}"
    )


def admin_dsn() -> str:
    """DSN for the configured DB_NAME crud -- used only to CREATE and DROP scratch databases."""
    return dsn_for(_env("DB_NAME"))


def _check_identifier(name: str) -> str:
    """Reject any crud name that is not a plain lowercase identifier."""
    if not _SAFE_IDENTIFIER.fullmatch(name):
        msg = f"refusing to interpolate {name!r} as a crud identifier"
        raise ValueError(msg)
    return name


async def create_database(name: str) -> str:
    """Drop and recreate a scratch crud, returning its DSN."""
    _check_identifier(name)
    admin = await asyncpg.connect(admin_dsn())
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        await admin.execute(f"CREATE DATABASE {name}")
    finally:
        await admin.close()
    return dsn_for(name)


async def drop_database(name: str) -> None:
    """Drop a scratch crud if it exists."""
    _check_identifier(name)
    admin = await asyncpg.connect(admin_dsn())
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    finally:
        await admin.close()


async def apply_migration(conn: asyncpg.Connection) -> None:
    """Apply migrations/ through pogo's own parser, in process so failure raises a real exception."""
    await pogo_testing.apply(MIGRATIONS, db=conn, schema_name=POGO_SCHEMA)


async def _create_and_apply(name: str) -> str:
    uri = await create_database(name)
    conn = await asyncpg.connect(uri)
    try:
        await apply_migration(conn)
    finally:
        await conn.close()
    return uri


@pytest.fixture(scope="session")
def _schema_db_uri():
    """Create a scratch crud, apply the migration, drop it; synchronous so no loop is shared with a test."""
    uri = asyncio.run(_create_and_apply(SCHEMA_TEST_DB))
    yield uri
    asyncio.run(drop_database(SCHEMA_TEST_DB))


@pytest_asyncio.fixture
async def conn(_schema_db_uri):
    """Connection to the migrated scratch crud, inside a transaction that always rolls back."""
    connection = await asyncpg.connect(_schema_db_uri)
    tx = connection.transaction()
    await tx.start()
    try:
        yield connection
    finally:
        try:
            await tx.rollback()
        except Exception:  # a deferred-constraint failure has already aborted it
            pass
        await connection.close()


@pytest_asyncio.fixture
async def tier(conn):
    """Insert one throwaway core.access_tiers row with a randomised id, distinct from the seeded tiers."""
    return await insert_tier(conn)
