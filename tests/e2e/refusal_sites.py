"""Where `NotificationRejected` is raised, read from the package's source rather than imported.
One copy for both webhook routes: `REFUSAL_FILES` is a control both assert against, and a second
copy of it left one route red for a reason that no longer described the code."""
import ast
from pathlib import Path

import nativespeaker.api

# The application package on disk, read as text so the scan below imports nothing.
_PACKAGE = Path(nativespeaker.api.__file__).parent

# The package files each route's refusals are raised in, scanned whole. `app/dependencies.py`
# carries the dependency raises, so a refusal added anywhere in it reaches the Play route's control.
APP_STORE_REFUSAL_FILES = frozenset({"auth/app_store.py"})
GOOGLE_PLAY_REFUSAL_FILES = frozenset({"app/dependencies.py", "auth/google_play.py"})

# Derived from the two, never hand-listed: a refusal in a file neither route scans fails the
# control that reads this rather than shrinking both sides of the equality it guards.
REFUSAL_FILES = APP_STORE_REFUSAL_FILES | GOOGLE_PLAY_REFUSAL_FILES

# What a `stage=` that is not a literal leaves behind: a value computed at the raise site, which is
# the library's own `VerificationStatus.name` on the Apple path and a bounded reason on the Google one.
COMPUTED = "<computed at the raise site>"


def _called_name(node: ast.Call) -> str | None:
    """The callee's own name, whether it was called bare or through its module."""
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)


def refusal_calls(source: str) -> list[ast.Call]:
    """Every `NotificationRejected(...)` call one module's source makes."""
    return [node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and _called_name(node) == "NotificationRejected"]


def _stage_of(node: ast.Call) -> str:
    """The literal stage one raise site names, or the marker for a stage computed there."""
    for keyword in node.keywords:
        if keyword.arg == "stage":
            return (keyword.value.value if isinstance(keyword.value, ast.Constant) else COMPUTED)
    return COMPUTED


def files_raising_the_refusal() -> set[str]:
    """Every file of the application package carrying a `NotificationRejected(...)` call."""
    # `encoding="utf-8"`, never the locale's: three files of the package carry non-ASCII bytes, so
    # an ASCII locale makes this scan raise before the controls reading it can compare anything.
    return {path.relative_to(_PACKAGE).as_posix() for path in _PACKAGE.rglob("*.py")
            if refusal_calls(path.read_text(encoding="utf-8"))}


def raised_refusal_stages(files: frozenset[str]) -> set[str]:
    """Every stage these package files raise the refusal with, read whole rather than per function.
    A function-level scan missed every other raise site in a file it already named."""
    return {_stage_of(node) for name in files
            for node in refusal_calls((_PACKAGE / name).read_text(encoding="utf-8"))}
