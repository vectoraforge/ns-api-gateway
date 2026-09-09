"""How one integrity violation is classified, asked in a single place by every writer."""
from sqlalchemy.exc import IntegrityError

# PostgreSQL's `unique_violation`. The indexes are the arbiter; no constraint is ever named.
UNIQUE_VIOLATION = "23505"


def is_unique_violation(violation: IntegrityError) -> bool:
    """Whether the unique index refused this write, read fail-closed."""
    # `orig` is Optional -- SQLAlchemy raises this class itself as well as wrapping the driver's --
    # and the code attribute is the driver's own, so an absent or unreadable code is not a race.
    # Dereferencing it inside the except block raised `AttributeError` and lost the classification.
    return getattr(violation.orig, "sqlstate", None) == UNIQUE_VIOLATION
