"""The auth rejection family: one exception per client-visible outcome, each carrying its own class.

Auth code raises the outcome it discovered and stops there. One handler reads `error_class` and
answers; nothing else in the codebase reads it. The class name is the outcome vocabulary -- the
handler snake_cases it into the structured log event -- so a rename here renames a log event.
"""
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    IDENTITY_ALREADY_LINKED,
    INTERNAL_ERROR,
    OPERATION_NOT_ALLOWED,
    PREAUTH_IDENTITY_NOT_ALLOWED,
    ErrorClass,
)


# `INTERNAL_ERROR` is the fail-closed control, not a convenience default: a subclass that forgets
# to declare its own class answers 500, never 200 and never something weaker than it owed.
class AuthRejected(Exception):
    """Base for every auth rejection, and deliberately outside the service-error tree in `errors.py`.

    This family gets its own handler because `service_error_handler` takes `_: Request` and so
    cannot supply the `route` field every rejection's log line is required to carry. That is the
    whole reason for the split; the class attribute idiom itself is copied unchanged.
    """

    error_class: ErrorClass = INTERNAL_ERROR

    def log_fields(self) -> dict[str, str | None]:
        """The extra fields this rejection contributes to its one log line, and the only such channel.

        Every value here is a plain scalar -- `str`, `UUID`, `BoundedReason`, `None` -- and never a
        SQLModel row. This is conformance, not a new rule: every `__init__` in `errors.py` already
        keeps it. The failure it prevents is concrete. A rollback on the way out of the request
        expires an ORM instance's attributes; the handler's read of one then attempts I/O outside a
        greenlet; the handler itself raises; and the client is answered 500 where a 409 was owed.
        """
        return {}


# The subclasses are grouped by arm, in the order D-17 converts them: admission arms, creation
# arms, lookup arms, challenge arms. Later plans append inside their own group. No plan reorganises
# this file, so an arm stays where the plan that wrote it put it.

# --- Admission arms: `auth/identity.py` and the barrier in `app/dependencies.py` ---


class PreAuthIdentityNotAllowed(AuthRejected):
    """A verified pair that matched no identity row, on a route that admits only linked callers."""

    error_class = PREAUTH_IDENTITY_NOT_ALLOWED


class IdentityUnresolvable(AuthRejected):
    """An identity row whose `user_id` resolves to nothing: unresolvable state, read fail-closed.

    The one class in the family that legitimately *declares* `INTERNAL_ERROR` rather than inheriting
    the base's fail-closed default -- a broken identity->user link is a real 500, not a leaf that
    forgot to name its class. Declared explicitly so the vocabulary test can tell the two apart.
    """

    error_class = INTERNAL_ERROR


# --- Creation arms: the consuming transaction in `auth/creation.py` ---


class IdentityAlreadyLinked(AuthRejected):
    """The pair already has an active identity backed by an active user: reconcile, do not create."""

    error_class = IDENTITY_ALREADY_LINKED


class ProviderAccountAlreadyLinked(AuthRejected):
    """The provider account is already reserved, so this attempt may not claim it for a second user."""

    error_class = OPERATION_NOT_ALLOWED


class AccountUnavailable(AuthRejected):
    """A historical identity row, or an active row whose user is not active.

    One class for both arms on purpose: the two are indistinguishable to clients, and telling them
    apart would make completion an account-state oracle. `cause` carries the distinction to the
    structured log and nowhere else -- it never reaches a response body.
    """

    error_class = ACCOUNT_UNAVAILABLE

    def __init__(self, *, cause: str) -> None:
        self.cause = cause
        super().__init__(f"account unavailable: {cause}")

    def log_fields(self) -> dict[str, str | None]:
        return {"cause": self.cause}
