"""The audit subsystem D-01 dropped and the success event D-02 declined, guarded so a rebuild fails here."""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
MIGRATIONS = REPO / "migrations"
INVENTORY = REPO / "tests" / "schema" / "test_inventory.py"
SYNC_SERVICE = SRC / "nativespeaker" / "api" / "services" / "sync.py"

DELETED_AUDIT_NAMES = ("auth_events", "auth_event_result")
LOG_MODULES = frozenset({"structlog", "logging"})
LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "log"})
KNOWN_PRESENT_EVENT = "quota_rejected"


def _expected_audit_tables(path: Path) -> set[str]:
    """The set literal bound to `EXPECTED_AUDIT_TABLES`, read from the syntax tree rather than imported."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "EXPECTED_AUDIT_TABLES" not in names:
            continue
        if not isinstance(node.value, ast.Set):
            raise AssertionError("EXPECTED_AUDIT_TABLES is no longer a set literal this guard can read")
        return {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    raise AssertionError(f"EXPECTED_AUDIT_TABLES is not assigned at all in {path}")


def _source_strings(root: Path) -> list[str]:
    """Every string constant of every module below `root`, so a comment mentioning a name cannot trip a check."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.append(node.value)
    return found


def _imported_roots(tree: ast.Module) -> set[str]:
    """The top-level package of every import in `tree`."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class TestTheAuditTableExpectationIsStillOneMember:
    """The schema suite still expects exactly one audit table, so a reintroduced auth-event table fails there."""

    def test_the_expectation_names_only_subscription_events(self):
        assert _expected_audit_tables(INVENTORY) == {"subscription_events"}


class TestNoMigrationNamesTheDeletedAuditTable:
    """The deleted `audit.auth_events` and its result enum appear in no migration, under any casing."""

    def test_no_sql_file_mentions_either_deleted_name(self):
        offenders = [(path.name, name)
                     for path in sorted(MIGRATIONS.glob("*.sql"))
                     for name in DELETED_AUDIT_NAMES
                     if name in path.read_text().lower()]
        assert offenders == []


class TestTheMigrationIsStillTheOnlyOne:
    """SCHEMA-01 forbids incremental migration files, so a rebuild that adds one fails this phase's own guard."""

    def test_exactly_one_sql_file_exists_under_migrations(self):
        assert [p.name for p in sorted(MIGRATIONS.glob("*.sql"))] == ["20260818_01_initial-release.sql"]


class TestTheSyncServiceEmitsNoEventOfItsOwn:
    """D-02: the sync service logs nothing on any path, so it imports no logging library and calls no log method."""

    def test_it_imports_no_logging_library_and_makes_no_logging_call(self):
        tree = ast.parse(SYNC_SERVICE.read_text())
        assert _imported_roots(tree) & LOG_MODULES == set()
        calls = [node.func.attr
                 for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        assert [attr for attr in calls if attr in LOG_METHODS] == []


class TestNoPerAttemptSyncEventNameWasAdded:
    """D-01/D-02: no string anywhere under `src/` names a sync event or the deleted audit table."""

    def test_no_source_string_names_a_sync_event_or_the_deleted_table(self):
        offenders = [text for text in _source_strings(SRC)
                     if "auth_sync" in text or "auth_events" in text]
        assert offenders == []


class TestTheSourceWalkIsNotVacuous:
    """A guard that scans nothing passes for the wrong reason, so the walk must find a name known to be present."""

    def test_the_walk_finds_an_event_name_quota_is_known_to_emit(self):
        assert KNOWN_PRESENT_EVENT in _source_strings(SRC)
