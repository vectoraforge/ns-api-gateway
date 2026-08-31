"""The docstring bar of AGENTS.md, measured rather than asserted.

This is the ratchet whose recorded baselines plans 06 through 09 drive to zero.
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_Definition = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def _named(node: ast.AST, prefix: str = "") -> list[tuple[_Definition, str]]:
    """Every class, function and method below `node`, each with its qualified name."""
    found: list[tuple[_Definition, str]] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((child, prefix + child.name))
            found.extend(_named(child, prefix + child.name + "."))
        else:
            found.extend(_named(child, prefix))
    return found


def over_long(root: Path, *, recurse: bool = True) -> list[tuple[str, str, int]]:
    """Every docstring under `root` whose stripped body runs past three lines."""
    found = []
    for path in sorted(root.rglob("*.py") if recurse else root.glob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        nodes: list[tuple[ast.Module | _Definition, str]] = [(tree, "<module>"), *_named(tree)]
        for node, name in nodes:
            doc = ast.get_docstring(node, clean=True)
            if doc and len(doc.strip().splitlines()) > 3:
                found.append((str(path.relative_to(root)), name, len(doc.strip().splitlines())))
    return sorted(found)


BASELINE: dict[str, int] = {
    "src": 0,
    "tests": 0,
    "tests/e2e": 4,
    "tests/schema": 0,
    "tests/unit": 0,
}


def _measure(root: str) -> int:
    """The root `tests` is its own top level alone; every other root is walked whole."""
    return len(over_long(REPO / root, recurse=root != "tests"))


class TestTheBarHolds:
    """The recorded counts, checked instead of described."""

    @pytest.mark.parametrize("root", sorted(BASELINE))
    def test_each_root_matches_its_recorded_baseline(self, root):
        """Equality, not `<=`: a sweep that forgot to lower a number fails as loudly as a new violation."""
        assert _measure(root) == BASELINE[root]


class TestTheMeasurementFires:
    """The control: a gate that quietly reported nothing would pass every recorded baseline."""

    def test_a_four_line_docstring_is_reported(self, tmp_path):
        """Four lines is the first length over the bar."""
        (tmp_path / "m.py").write_text('"""One.\n\nTwo.\nThree.\n"""\n')
        assert over_long(tmp_path) == [("m.py", "<module>", 4)]

    def test_a_three_line_docstring_is_not_reported(self, tmp_path):
        """The boundary case, which a gate reporting everything would fail."""
        (tmp_path / "m.py").write_text('"""One.\nTwo.\nThree.\n"""\n')
        assert over_long(tmp_path) == []

    def test_the_walk_reaches_a_method_inside_a_class(self, tmp_path):
        """A module-level-only read would report nothing here."""
        (tmp_path / "m.py").write_text("class C:\n"
                                       "    def method(self):\n"
                                       '        """One.\n'
                                       "\n"
                                       "        Two.\n"
                                       "        Three.\n"
                                       '        """\n'
                                       "        return None\n")
        assert over_long(tmp_path) == [("m.py", "C.method", 4)]

    def test_a_file_without_docstrings_contributes_nothing(self, tmp_path):
        """Absence is not an error."""
        (tmp_path / "m.py").write_text("x = 1\n")
        assert over_long(tmp_path) == []
