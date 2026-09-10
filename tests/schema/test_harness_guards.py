"""The scratch-database harness's own guards: which server it may drop on, and under whose name."""
import os

import asyncpg
import pytest

from schema import conftest, test_apply_rollback

pytestmark = pytest.mark.schema


class TestTheAdminTargetMustBeLoopback:
    """`admin_dsn` is the DSN `DROP DATABASE ... WITH (FORCE)` runs on, and `.env` names the host."""

    def test_a_remote_host_is_refused(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "db.staging.internal")
        monkeypatch.delenv("NS_SCHEMA_TEST_ALLOW_REMOTE", raising=False)
        with pytest.raises(RuntimeError, match="refusing to create and drop scratch databases"):
            conftest.admin_dsn()

    def test_the_opt_out_lets_a_remote_host_through(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "db.staging.internal")
        monkeypatch.setenv("NS_SCHEMA_TEST_ALLOW_REMOTE", "1")
        assert "db.staging.internal" in conftest.admin_dsn()

    @pytest.mark.parametrize("host", sorted(conftest._LOCAL_HOSTS))
    def test_every_loopback_spelling_is_allowed(self, host, monkeypatch):
        monkeypatch.setenv("DB_HOST", host)
        assert host in conftest.admin_dsn()


class TestTheScratchNamesArePerSession:
    """Setup force-drops these names, so two concurrent runs sharing one would kill each other."""

    @pytest.mark.parametrize("name", [conftest.SCHEMA_TEST_DB, test_apply_rollback.ROLLBACK_TEST_DB])
    def test_the_name_carries_this_process_id(self, name):
        assert name.endswith(f"_{os.getpid()}")
        assert conftest._SAFE_IDENTIFIER.fullmatch(name), f"{name!r} is not a usable identifier"


class TestTheConnectionFixtureNeverLeaks:
    """`tx.start()` raises on a server at its connection limit, and the socket must not survive it."""

    async def test_a_transaction_that_cannot_start_still_closes_the_connection(self, monkeypatch):
        closed: list[bool] = []

        class _Transaction:
            async def start(self):
                raise asyncpg.exceptions.TooManyConnectionsError("no connection slots")

        class _Connection:
            def transaction(self):
                return _Transaction()

            async def close(self):
                closed.append(True)

        async def _connect(_uri):
            return _Connection()

        monkeypatch.setattr(conftest.asyncpg, "connect", _connect)
        fixture = conftest.conn.__wrapped__("postgres://unused/unused")
        with pytest.raises(asyncpg.exceptions.TooManyConnectionsError):
            await anext(fixture)

        assert closed == [True], "the connection opened before the failed start was never closed"
