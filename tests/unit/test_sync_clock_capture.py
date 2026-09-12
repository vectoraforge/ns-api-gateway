"""SYNC-01: the sync service reads the clock nowhere; one dependency captures it exactly once."""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
SYNC_SERVICE = SRC / "nativespeaker" / "api" / "services" / "sync.py"
DEPENDENCIES = SRC / "nativespeaker" / "api" / "app" / "dependencies.py"

CLOCK_MEMBERS = {"datetime": frozenset({"now", "utcnow", "today"}),
                 "date": frozenset({"today"}),
                 "time": frozenset({"time", "time_ns", "monotonic", "monotonic_ns",
                                    "perf_counter", "perf_counter_ns"})}


def _clock_aliases(tree: ast.Module) -> dict[str, str]:
    """Every local name bound to one of those modules. `import datetime as dt` reads the same
    clock under another name, and a walk pinned to the canonical spelling never saw it."""
    aliases = {name: name for name in CLOCK_MEMBERS}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            aliases |= {alias.asname or alias.name: alias.name
                        for alias in node.names if alias.name in CLOCK_MEMBERS}
        elif isinstance(node, ast.Import):
            aliases |= {alias.asname or alias.name: alias.name
                        for alias in node.names if alias.name in CLOCK_MEMBERS}
    return aliases


def _clock_reads(node: ast.AST, aliases: dict[str, str] | None = None) -> list[ast.Attribute]:
    """Every reference to a clock-reading member under `node`, whatever local name its module was
    imported under. References rather than calls: `now = datetime.now` is the same second read,
    deferred by one line, and a call-shaped walk passed straight over it."""
    aliases = _clock_aliases(node) if aliases is None and isinstance(node, ast.Module) else aliases
    aliases = {name: name for name in CLOCK_MEMBERS} if aliases is None else aliases
    found = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Attribute):
            continue
        base = n.value
        name = (base.attr if isinstance(base, ast.Attribute)
                else base.id if isinstance(base, ast.Name) else None)
        if n.attr in CLOCK_MEMBERS.get(aliases.get(name, name), ()):
            found.append(n)
    return found


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
        assert _clock_reads(ast.parse(SYNC_SERVICE.read_text())) == []

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


class TestTheInstantIsCapturedOnceAndSharedByEveryService:
    """`req~sessions-sync-single-evaluation-time~2`: one `datetime.now(UTC)` call, not zero and not two."""

    def test_get_evaluated_at_calls_the_clock_exactly_once(self):
        tree = ast.parse(DEPENDENCIES.read_text())
        function = _function(tree, "get_evaluated_at")
        assert len(_clock_reads(function, _clock_aliases(tree))) == 1

    @pytest.mark.parametrize("name", ("get_sync_service", "get_auth_service", "get_chat_service"))
    def test_no_service_dependency_reads_the_clock_itself(self, name):
        """A read here would hand two services two instants on the one request that uses both."""
        tree = ast.parse(DEPENDENCIES.read_text())
        assert _clock_reads(_function(tree, name), _clock_aliases(tree)) == []

    @pytest.mark.parametrize("name", ("get_sync_service", "get_auth_service"))
    def test_every_service_dependency_takes_the_one_captured_instant(self, name):
        """FastAPI caches a dependency per request, so declaring it is what makes the instant shared."""
        function = _function(ast.parse(DEPENDENCIES.read_text()), name)
        assert _depends_on(function, "evaluated_at") == "get_evaluated_at"


class TestTheClockWalkIsNotVacuous:
    """A guard that finds no clock call anywhere would pass for the wrong reason, so it must find some."""

    def test_the_walk_finds_the_clock_call_dependencies_genuinely_makes(self):
        """37.4 WR-03: exactly one, and it is `get_evaluated_at`'s. Every service factory takes the
        captured instant, so a second call anywhere in this module is a second instant per request."""
        tree = ast.parse(DEPENDENCIES.read_text())
        reads = _clock_reads(tree)
        assert len(reads) == 1
        assert _clock_reads(_function(tree, "get_evaluated_at"), _clock_aliases(tree)) == reads

    def test_the_default_walk_reads_a_declared_dependency_and_not_every_call(self):
        """The control: `_depends_on` must distinguish a `Depends()` default from any other call."""
        tree = ast.parse("def f(a = Depends(g), b = dict()): pass")
        function = _function(tree, "f")
        assert (_depends_on(function, "a"), _depends_on(function, "b")) == ("g", None)

    @pytest.mark.parametrize("source", [
        "x = datetime.datetime.now(UTC)",
        "from datetime import datetime as dt\nx = dt.now()",
        "import datetime as dt\nx = dt.datetime.now()",
        "x = time.monotonic()",
        "x = time.perf_counter()",
        "import time as clock\nx = clock.time()",
        "now = datetime.now\nx = now(UTC)",
        "x = datetime.now(tz=UTC)",
        "x = date.today()",
    ], ids=["qualified", "aliased_class", "aliased_module", "monotonic", "perf_counter",
            "aliased_time", "bound_then_called", "keyword_tz", "date_today"])
    def test_every_spelling_of_a_second_read_is_seen(self, source):
        """Each of these read a clock and were counted as zero, so `req~sessions-sync-single-
        evaluation-time~2` held only against the one spelling the walk happened to match."""
        assert _clock_reads(ast.parse(source)) != []

    @pytest.mark.parametrize("source", [
        "x = row.date\nx = obj.now",
        "x = self.evaluated_at",
        "from mine import time\nx = time",
    ], ids=["a_member_of_something_else", "the_captured_instant", "a_name_that_is_not_a_call"])
    def test_a_near_miss_is_not_counted(self, source):
        """The control: a walk matching the member name alone would report every one of these."""
        assert _clock_reads(ast.parse(source)) == []
