"""SYNC-01: the sync service reads the clock nowhere; one dependency captures it exactly once."""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
SYNC_SERVICE = SRC / "nativespeaker" / "api" / "services" / "sync.py"
DEPENDENCIES = SRC / "nativespeaker" / "api" / "app" / "dependencies.py"

# The shapes a clock read takes in this codebase, reused from the logging-call walk's own shape.
CLOCK_CALLS = frozenset({("datetime", "now"), ("datetime", "utcnow"), ("date", "today"), ("time", "time")})


def _clock_calls(node: ast.AST) -> list[ast.Call]:
    """Every call under `node` matching one of the known clock-reading shapes."""
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and (n.func.value.id, n.func.attr) in CLOCK_CALLS]


def _function(tree: ast.Module, name: str) -> ast.AST:
    """The one function bound to `name`, found by the syntax tree rather than imported."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined")


def _annotation_subtree_ids(tree: ast.Module) -> set[int]:
    """The id() of every node sitting inside a type annotation anywhere in `tree`."""
    marked: set[int] = set()
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            annotations = [a.annotation for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)
                           if a.annotation is not None]
            if node.returns is not None:
                annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            annotations = [node.annotation]
        for sub in annotations:
            marked.update(id(n) for n in ast.walk(sub))
    return marked


class TestSyncServiceReadsNoClock:
    """`current_period` must come from the one instant the dependency captured, never a fresh read below it."""

    def test_sync_service_makes_no_clock_call_on_any_path(self):
        assert _clock_calls(ast.parse(SYNC_SERVICE.read_text())) == []

    def test_the_datetime_import_is_used_only_as_a_type_annotation(self):
        tree = ast.parse(SYNC_SERVICE.read_text())
        marked = _annotation_subtree_ids(tree)
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "datetime"]
        assert names != []
        assert all(id(n) in marked for n in names)


def _depends_on(function: ast.AST, parameter: str) -> str | None:
    """The dependency `parameter`'s default declares, or `None` when it declares none."""
    args = function.args
    named = [*args.posonlyargs, *args.args]
    defaults = dict(zip(named[len(named) - len(args.defaults):], args.defaults, strict=True))
    default = defaults.get(next((arg for arg in named if arg.arg == parameter), None))
    if not isinstance(default, ast.Call) or getattr(default.func, "id", None) != "Depends":
        return None
    return getattr(default.args[0], "id", None)


class TestTheInstantIsCapturedOnceAndSharedByBothServices:
    """`req~sessions-sync-single-evaluation-time~2`: one `datetime.now(UTC)` call, not zero and not two."""

    def test_get_evaluated_at_calls_the_clock_exactly_once(self):
        function = _function(ast.parse(DEPENDENCIES.read_text()), "get_evaluated_at")
        assert len(_clock_calls(function)) == 1

    @pytest.mark.parametrize("name", ("get_sync_service", "get_auth_service"))
    def test_neither_service_dependency_reads_the_clock_itself(self, name):
        """A read here would hand the two services two instants on the one request that uses both."""
        function = _function(ast.parse(DEPENDENCIES.read_text()), name)
        assert _clock_calls(function) == []

    @pytest.mark.parametrize("name", ("get_sync_service", "get_auth_service"))
    def test_both_service_dependencies_take_the_one_captured_instant(self, name):
        """FastAPI caches a dependency per request, so declaring it is what makes the instant shared."""
        function = _function(ast.parse(DEPENDENCIES.read_text()), name)
        assert _depends_on(function, "evaluated_at") == "get_evaluated_at"


class TestTheClockWalkIsNotVacuous:
    """A guard that finds no clock call anywhere would pass for the wrong reason, so it must find some."""

    def test_the_walk_finds_the_clock_calls_dependencies_genuinely_makes(self):
        assert len(_clock_calls(ast.parse(DEPENDENCIES.read_text()))) >= 2

    def test_the_default_walk_reads_a_declared_dependency_and_not_every_call(self):
        """The control: `_depends_on` must distinguish a `Depends()` default from any other call."""
        tree = ast.parse("def f(a = Depends(g), b = dict()): pass")
        function = _function(tree, "f")
        assert (_depends_on(function, "a"), _depends_on(function, "b")) == ("g", None)
