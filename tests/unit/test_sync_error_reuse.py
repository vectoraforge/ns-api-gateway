"""SYNC-02/D-07: sync raises no error class quota does not, and introduces no sibling of its own.
Narrowed to this equality claim: `test_error_registry.py` already pins the error tree's full totality.
"""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
SYNC_SERVICE = SRC / "nativespeaker" / "api" / "services" / "sync.py"
QUOTA_SERVICE = SRC / "nativespeaker" / "api" / "services" / "quota.py"

# The three classes D-07 names, derived once here for the assertion -- not a second copy of a raise list.
EXPECTED_SYNC_RAISES = frozenset({"MissingUsageRowError", "MultipleEffectiveGrantsError", "UnknownTierError"})


def _raised_class_names(path: Path) -> set[str]:
    """The name of every class a bare `raise SomeError(...)` in `path` constructs."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            names.add(exc.func.id)
        elif isinstance(exc, ast.Name):
            names.add(exc.id)
    return names


class TestSyncRaisesExactlyTheThreeReusedClasses:
    """No fourth class was added: the set sync raises is exactly the three D-07 names."""

    def test_sync_service_raises_exactly_three_named_classes(self):
        assert _raised_class_names(SYNC_SERVICE) == EXPECTED_SYNC_RAISES


class TestSyncRaisesNoSiblingOfQuota:
    """Every class sync raises is a class quota also raises: sync introduced no error class of its own."""

    def test_every_class_sync_raises_is_also_raised_by_quota(self):
        assert _raised_class_names(SYNC_SERVICE) <= _raised_class_names(QUOTA_SERVICE)
