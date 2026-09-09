"""One migration file, a clean apply from empty, and a clean rollback through pogo's own path."""
import asyncpg
import pytest
from pogo_core.util import testing as pogo_testing

from schema.conftest import MIGRATIONS, POGO_SCHEMA, apply_migration, create_database, drop_database
from schema.helpers import insert_grant, insert_user

pytestmark = pytest.mark.schema

# Its own scratch database so the rollback proof cannot disturb the session fixture's.
ROLLBACK_TEST_DB = "ns_schema_test_rollback"

NAMESPACES = "SELECT count(*) FROM pg_namespace WHERE nspname IN ('core', 'audit')"

# The reference rows the migration seeds; TestSeededTiers below is the only place the credits are pinned.
SEEDED_TIERS = {"anonymous", "registered", "paid"}


class TestMigrationDirectory:
    """migrations/ holds exactly one .sql file, so pogo applies exactly that one."""

    def test_exactly_one_sql_file(self):
        found = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
        assert len(found) == 1, f"expected exactly one migration file in migrations/, found {found}"


class TestApply:
    """The session fixture's from-empty apply produced both schemas."""

    async def test_core_and_audit_namespaces_exist(self, conn):
        present = {
            row["nspname"]
            for row in await conn.fetch("SELECT nspname FROM pg_namespace WHERE nspname IN ('core', 'audit')")
        }
        assert present == {"core", "audit"}, f"expected both schemas after apply, found {sorted(present)}"


class TestRollback:
    """The migration's own rollback section removes both schemas, driven through pogo's rollback."""

    async def test_pogo_rollback_leaves_neither_schema(self):
        uri = await create_database(ROLLBACK_TEST_DB)
        try:
            connection = await asyncpg.connect(uri)
            try:
                await apply_migration(connection)
                assert await connection.fetchval(NAMESPACES) == 2, "apply did not create core and audit"

                # pogo's own rollback path: a hand-written DROP would prove nothing about the file's rollback.
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


class TestSeededTiers:
    """The migration seeds core.access_tiers as reference data, overriding 00-schema.md:249."""

    async def test_seeded_tiers_and_credits(self, conn):
        """Keyed to the three seeded ids: `_schema_db_uri` is session-scoped and sibling modules
        COMMIT throwaway tiers into it, so a whole-table read answers for their rows too."""
        rows = await conn.fetch("SELECT id, monthly_credits FROM core.access_tiers "
                                "WHERE id = ANY($1) ORDER BY id", sorted(SEEDED_TIERS))
        assert {row["id"]: row["monthly_credits"] for row in rows} == {
            "anonymous": 10,
            "registered": 50,
            "paid": 1000,
        }

    async def test_registered_is_not_smaller_than_anonymous(self, conn):
        """A registered claim carries monthly_used across, so a smaller registered tier would clamp remaining."""
        anonymous, registered = await conn.fetchrow(
            "SELECT (SELECT monthly_credits FROM core.access_tiers WHERE id = 'anonymous'),"
            "       (SELECT monthly_credits FROM core.access_tiers WHERE id = 'registered')"
        )
        assert registered >= anonymous


class TestHarnessIsolation:
    """WR-35. The per-test transaction is never committed, so no test observes another's seed rows.
    Each case stands alone: a pair that hands rows to the next case through module state fails when
    it is run alone, re-run with --lf, or distributed, for a reason that is not the schema's."""

    async def test_seed_helpers_insert_rows(self, conn, tier):
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier)
        assert await conn.fetchval("SELECT count(*) FROM core.users WHERE id = $1", user_id) == 1
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants WHERE id = $1", grant_id) == 1

    async def test_the_seeded_rows_are_invisible_to_a_second_connection(self, conn, tier,
                                                                       _schema_db_uri):
        """The guarantee itself, read from outside: what this case writes lives in a transaction the
        fixture only ever rolls back, so no committed row of it can reach the next case."""
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier)
        observer = await asyncpg.connect(_schema_db_uri)
        try:
            seen = await observer.fetchval(
                "SELECT count(*) FROM core.access_grants WHERE id = $1", grant_id)
        finally:
            await observer.close()

        # The premise: the row is there on this connection, so the zero above is isolation and
        # never a mistyped id.
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants WHERE id = $1",
                                   grant_id) == 1
        assert seen == 0, "a seeded row was visible outside its own transaction"
