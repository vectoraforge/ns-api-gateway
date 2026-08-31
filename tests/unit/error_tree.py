"""The error tree's totality check."""
from collections.abc import Sequence
from typing import get_args

from nativespeaker.api.errors import AppError, ErrorCode, _family


def undeclared(classes: Sequence[type], *, root: type) -> list[str]:
    """Leaves that would answer the root's fail-closed default because nothing below it declares."""
    problems: list[str] = []
    for cls in classes:
        if cls.__subclasses__():
            # An intermediate base answers through its leaves; the one-409 challenge base is this.
            continue
        declared = any(ancestor is not root and "code" in vars(ancestor)
                       for ancestor in cls.__mro__)
        if not declared:
            problems.append(f"{cls.__name__} declares no status or code and inherits none below "
                            f"{root.__name__}, so it would answer the base default")
    return problems


def tree_problems(root: type[AppError], *,
                  declared_codes: frozenset[str] | None = None) -> list[str]:
    """Every defect under `root`, collected so one run reports them all rather than the first."""
    classes = _family(root)
    problems: list[str] = []

    status_of_code: dict[str, tuple[str, int]] = {}
    for cls in classes:
        own = vars(cls)
        if ("status" in own) != ("code" in own):
            problems.append(f"{cls.__name__} declares only "
                            f"{'status' if 'status' in own else 'code'}; declare both or neither")
        code, status = own.get("code"), own.get("status")
        if code is None or status is None:
            continue
        owner, owned_status = status_of_code.get(code, (None, status))
        if owner is not None and owned_status != status:
            problems.append(f"code {code!r} is claimed at status {owned_status} by {owner} and at "
                            f"status {status} by {cls.__name__}")
        else:
            status_of_code[code] = (cls.__name__, status)

    problems.extend(undeclared(classes, root=root))

    if declared_codes is not None:
        carried = {cls.code for cls in classes}
        if declared_codes - carried:
            problems.append(f"ErrorCode declares codes the tree never carries: "
                            f"{sorted(declared_codes - carried)}")
        if carried - declared_codes:
            problems.append(f"the tree carries codes absent from ErrorCode: "
                            f"{sorted(carried - declared_codes)}")

    answering: dict[int, str] = {}
    for cls in classes:
        if not vars(cls).get("answers_framework_status"):
            continue
        if cls.status in answering:
            problems.append(f"status {cls.status} is answered by both {answering[cls.status]} "
                            f"and {cls.__name__}")
        else:
            answering[cls.status] = cls.__name__

    return problems


def assert_tree_total() -> None:
    """Raise on a defect in the error tree, naming every one of them in the one message."""
    problems = tree_problems(AppError, declared_codes=frozenset(get_args(ErrorCode)))
    if problems:
        raise RuntimeError("error tree is not total:\n  " + "\n  ".join(problems))
