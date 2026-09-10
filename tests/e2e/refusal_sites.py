"""Where `NotificationRejected` is raised, read from the package's source rather than imported.
One copy for both webhook routes: `REFUSAL_FILES` is a control both of them assert against, and
two copies of it meant a fourth raising file had to be added twice or one route stayed red for a
reason that no longer described the code."""
import ast
from pathlib import Path

import nativespeaker.api

# The application package on disk, read as text so the scan below imports nothing.
_PACKAGE = Path(nativespeaker.api.__file__).parent

# Every file of the package that raises the refusal, so one appearing elsewhere fails the control
# that reads it rather than shrinking both sides of the equality it guards.
REFUSAL_FILES = frozenset({"app/dependencies.py", "auth/app_store.py", "auth/google_play.py"})

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


def files_raising_the_refusal() -> set[str]:
    """Every file of the application package carrying a `NotificationRejected(...)` call."""
    return {path.relative_to(_PACKAGE).as_posix() for path in _PACKAGE.rglob("*.py")
            if refusal_calls(path.read_text())}


def raised_refusal_stages(sources: tuple[str, ...]) -> set[str]:
    """Every `NotificationRejected(stage=...)` these modules raise, read from their own source."""
    stages = set()
    for source in sources:
        for node in refusal_calls(source):
            for keyword in node.keywords:
                if keyword.arg == "stage":
                    stages.add(keyword.value.value
                               if isinstance(keyword.value, ast.Constant) else COMPUTED)
    return stages
