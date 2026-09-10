"""The scratch-database harness's own guards: which server it may drop on, and under whose name."""
import os

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
