"""Where `NotificationRejected` is raised, read from the package's source rather than imported.
One copy for both webhook routes: `REFUSAL_FILES` is a control both assert against, and a second
copy of it left one route red for a reason that no longer described the code."""
import ast
from pathlib import Path

import nativespeaker.api

_PACKAGE = Path(nativespeaker.api.__file__).parent

APP_STORE_REFUSAL_FILES = frozenset({"auth/app_store.py"})
GOOGLE_PLAY_REFUSAL_FILES = frozenset({"app/dependencies.py", "auth/google_play.py"})

REFUSAL_FILES = APP_STORE_REFUSAL_FILES | GOOGLE_PLAY_REFUSAL_FILES

COMPUTED = "<computed at the raise site>"

UNREADABLE = "<a raise site this scan cannot read>"


def _called_name(node: ast.Call) -> str | None:
    """The callee's own name, whether it was called bare or through its module."""
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)


def refusal_calls(source: str) -> list[ast.Call]:
    """Every `NotificationRejected(...)` call one module's source makes."""
    return [node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and _called_name(node) == "NotificationRejected"]


def _stage_of(node: ast.Call) -> str:
    """The literal stage one raise site names, the marker for one computed there, or the marker
    for a call shape carrying no readable `stage=` at all."""
    for keyword in node.keywords:
        if keyword.arg == "stage":
            return (keyword.value.value if isinstance(keyword.value, ast.Constant) else COMPUTED)
    return UNREADABLE


def files_raising_the_refusal() -> set[str]:
    """Every file of the application package carrying a `NotificationRejected(...)` call."""
    # The package files carry non-ASCII bytes. Read them with utf-8, not the locale encoding.
    return {path.relative_to(_PACKAGE).as_posix() for path in _PACKAGE.rglob("*.py")
            if refusal_calls(path.read_text(encoding="utf-8"))}


def raised_refusal_stages(files: frozenset[str]) -> set[str]:
    """Every stage these package files raise the refusal with, read whole rather than per function.
    A function-level scan missed every other raise site in a file it already named."""
    return {_stage_of(node) for name in files
            for node in refusal_calls((_PACKAGE / name).read_text(encoding="utf-8"))}
