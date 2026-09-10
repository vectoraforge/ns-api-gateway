"""How one integrity violation is classified, asked in a single place by every writer."""
from sqlalchemy.exc import IntegrityError

UNIQUE_VIOLATION = "23505"


def is_unique_violation(violation: IntegrityError) -> bool:
    """Whether the unique index refused this write, read fail-closed."""
    return getattr(violation.orig, "sqlstate", None) == UNIQUE_VIOLATION
