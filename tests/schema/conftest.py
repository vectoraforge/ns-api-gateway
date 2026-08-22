"""Fixtures for the schema-conformance suite -- a scratch database, a fresh apply, per-test rollback."""
import asyncio
import os
import pathlib
import re

import asyncpg
import pytest
import pytest_asyncio
from pogo_core.util import testing as pogo_testing

from schema.helpers import insert_tier

# The pogo entry point above is pogo_core.util.testing, NOT pogo_migrate.testing. The latter
# evaluates its config's database_dsn eagerly as an argument and raises InvalidConfigurationError
# when a DB_* variable is unset, even though it was handed a live connection (RESEARCH P-4).

MIGRATIONS = pathlib.Path(__file__).parents[2] / "migrations"
POGO_SCHEMA = "api"  # matches [tool.pogo] schema
SCHEMA_TEST_DB = "ns_schema_test"

# .env.example:4-8 defaults, so the suite still runs when a DB_* variable is unset. DB_NAME falls
# back to the always-present "postgres" maintenance database rather than to .env.example's
# application database name: this connection only ever issues CREATE/DROP DATABASE, so the
# maintenance database is both the conventional target and the one guaranteed to exist.
_DB_DEFAULTS = {
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_USER": "postgres",
    "DB_PASSWORD": "postgres",
    "DB_NAME": "postgres",
}

# A database name is an identifier and cannot be bound as a parameter, so CREATE/DROP DATABASE
# interpolate it. Every caller passes a module constant, and this pattern is the belt-and-braces
# guard that keeps it that way (T-34-03-01).
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def _env(name: str) -> str:
    """Read a DB_* variable, falling back to its .env.example default."""
    return os.environ.get(name) or _DB_DEFAULTS[name]


# Deliberately postgres:// and not the postgresql+asyncpg:// dialect URL that the application's
# own config module builds -- asyncpg rejects the SQLAlchemy prefix. That module is not imported
# here and neither is any other application module: D-13 forbids it, because this suite has to run
# while the application is knowingly broken.
def dsn_for(database: str) -> str:
    """Build an asyncpg DSN for one database."""
    return (
        f"postgres://{_env('DB_USER')}:{_env('DB_PASSWORD')}"
        f"@{_env('DB_HOST')}:{_env('DB_PORT')}/{database}"
    )


def admin_dsn() -> str:
    """DSN for the configured DB_NAME database -- used only to CREATE and DROP scratch databases."""
    return dsn_for(_env("DB_NAME"))


def _check_identifier(name: str) -> str:
    """Reject any database name that is not a plain lowercase identifier."""
    if not _SAFE_IDENTIFIER.fullmatch(name):
        msg = f"refusing to interpolate {name!r} as a database identifier"
        raise ValueError(msg)
    return name


async def create_database(name: str) -> str:
    """Drop and recreate a scratch database, returning its DSN."""
    _check_identifier(name)
    admin = await asyncpg.connect(admin_dsn())
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        await admin.execute(f"CREATE DATABASE {name}")
    finally:
        await admin.close()
    return dsn_for(name)


async def drop_database(name: str) -> None:
    """Drop a scratch database if it exists."""
    _check_identifier(name)
    admin = await asyncpg.connect(admin_dsn())
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    finally:
        await admin.close()


async def apply_migration(conn: asyncpg.Connection) -> None:
    """Apply migrations/ into the connected database through pogo's own parser.

    In-process rather than subprocess.run(["pogo", "apply"]): it exercises the same parser
    production uses, needs no environment at all, and raises a real exception on failure.
    """
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
    """Create a scratch database, apply the migration into it, drop it afterwards (D-14).

    Synchronous on purpose. pyproject.toml sets asyncio_mode = "auto" with
    asyncio_default_fixture_loop_scope = "function", so a session-scoped async fixture would hand
    the tests objects bound to a loop they do not run in. Wrapping the one-shot setup and teardown
    in asyncio.run() sidesteps that and needs no loop_scope= marker anywhere in this package.
    """
    uri = asyncio.run(_create_and_apply(SCHEMA_TEST_DB))
    yield uri
    asyncio.run(drop_database(SCHEMA_TEST_DB))


@pytest_asyncio.fixture
async def conn(_schema_db_uri):
    """Connection to the migrated scratch database, inside a transaction that always rolls back."""
    connection = await asyncpg.connect(_schema_db_uri)
    tx = connection.transaction()
    await tx.start()
    try:
        yield connection
    finally:
        try:
            await tx.rollback()
        except Exception:  # a deferred-constraint failure already aborted it -- RESEARCH P-6
            pass
        await connection.close()


@pytest_asyncio.fixture
async def tier(conn):
    """Insert one throwaway core.access_tiers row and return its id.

    Distinct from the three reference tiers the migration seeds: this one carries a randomised
    id so a test can own a tier without depending on, or disturbing, the seeded set.
    """
    return await insert_tier(conn)
