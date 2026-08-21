"""SCHEMA-01 and D-20 -- one migration file, a clean apply from empty, and a clean pogo rollback."""
import asyncpg
import pytest
from pogo_core.util import testing as pogo_testing

from schema.conftest import MIGRATIONS, POGO_SCHEMA, apply_migration, create_database, drop_database
from schema.helpers import insert_grant, insert_user

pytestmark = pytest.mark.schema

# Its own scratch database so the rollback proof cannot disturb the session fixture's.
ROLLBACK_TEST_DB = "ns_schema_test_rollback"

NAMESPACES = "SELECT count(*) FROM pg_namespace WHERE nspname IN ('core', 'audit')"


class TestMigrationDirectory:
    """SCHEMA-01: migrations/ holds exactly one .sql file, so pogo applies exactly that one."""

    def test_exactly_one_sql_file(self):
        found = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
        assert len(found) == 1, f"expected exactly one migration file in migrations/, found {found}"


class TestApply:
    """SCHEMA-01: the session fixture's from-empty apply produced both schemas."""

    async def test_core_and_audit_namespaces_exist(self, conn):
        present = {
            row["nspname"]
            for row in await conn.fetch("SELECT nspname FROM pg_namespace WHERE nspname IN ('core', 'audit')")
        }
        assert present == {"core", "audit"}, f"expected both schemas after apply, found {sorted(present)}"


class TestRollback:
    """D-20: the migration's own rollback section removes both schemas, proven via pogo's rollback."""

    async def test_pogo_rollback_leaves_neither_schema(self):
        uri = await create_database(ROLLBACK_TEST_DB)
        try:
            connection = await asyncpg.connect(uri)
            try:
                await apply_migration(connection)
                assert await connection.fetchval(NAMESPACES) == 2, "apply did not create core and audit"

                # pogo's own rollback path, not a hand-written DROP SCHEMA -- a hand-written drop
                # would prove nothing about the file's rollback section.
                await pogo_testing.rollback(MIGRATIONS, db=connection, schema_name=POGO_SCHEMA)

                remaining = await connection.fetch(
                    "SELECT nspname FROM pg_namespace WHERE nspname IN ('core', 'audit')"
                )
                assert remaining == [], f"rollback left namespaces behind: {[r['nspname'] for r in remaining]}"

                applied = await connection.fetchval(
                    "SELECT count(*) FROM public._pogo_migration WHERE schema_name = $1", POGO_SCHEMA
                )
                assert applied == 0, f"rollback left {applied} rows in _pogo_migration"
            finally:
                await connection.close()
        finally:
            await drop_database(ROLLBACK_TEST_DB)


class TestHarnessIsolation:
    """The per-test transaction rolls back, so no test observes another test's seed rows."""

    async def test_seed_helpers_insert_rows(self, conn, tier):
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier)
        assert await conn.fetchval("SELECT count(*) FROM core.users WHERE id = $1", user_id) == 1
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants WHERE id = $1", grant_id) == 1

    async def test_previous_test_rows_were_rolled_back(self, conn):
        for table in ("core.users", "core.access_grants", "core.access_tiers"):
            # table comes from the fixed literal tuple above, never from test input.
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")
            assert count == 0, f"{table} still holds {count} rows from a previous test"
