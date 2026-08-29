"""The auth rejection family: one exception per client-visible outcome, each carrying its own class.

Auth code raises the outcome it discovered and stops there. One handler reads `error_class` and
answers; nothing else in the codebase reads it. The class name is the outcome vocabulary -- the
handler snake_cases it into the structured log event -- so a rename here renames a log event.
"""
from nativespeaker.api.auth.extract_bearer import BoundedReason
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    AUTH_REQUIRED,
    CHALLENGE_REQUIRED,
    IDENTITY_ALREADY_LINKED,
    INTERNAL_ERROR,
    OPERATION_NOT_ALLOWED,
    PREAUTH_IDENTITY_NOT_ALLOWED,
    VERIFICATION_TEMPORARILY_UNAVAILABLE,
    ErrorClass,
)


# `INTERNAL_ERROR` is the fail-closed control, not a convenience default: a subclass that forgets
# to declare its own class answers 500, never 200 and never something weaker than it owed.
class AuthRejected(Exception):
    """Base for every auth rejection, and deliberately outside the service-error tree in `error_handlers.py`.

    This family gets its own handler because `service_error_handler` takes `_: Request` and so
    cannot supply the `route` field every rejection's log line is required to carry. That is the
    whole reason for the split; the class attribute idiom itself is copied unchanged.
    """

    error_class: ErrorClass = INTERNAL_ERROR

    def log_fields(self) -> dict[str, str | None]:
        """The extra fields this rejection contributes to its one log line, and the only such channel.

        Every value here is a plain scalar -- `str`, `UUID`, `BoundedReason`, `None` -- and never a
        SQLModel row. This is conformance, not a new rule: every `__init__` in `error_handlers.py` already
        keeps it. The failure it prevents is concrete. A rollback on the way out of the request
        expires an ORM instance's attributes; the handler's read of one then attempts I/O outside a
        greenlet; the handler itself raises; and the client is answered 500 where a 409 was owed.
        """
        return {}


# The subclasses are grouped by arm, in the order D-17 converts them: admission arms, creation
# arms, lookup arms, challenge arms. Later plans append inside their own group. No plan reorganises
# this file, so an arm stays where the plan that wrote it put it.

# --- Admission arms: `auth/resolve_identity.py` and the barrier in `app/dependencies.py` ---


class InvalidExternalJwt(AuthRejected):
    """No usable bearer credential: either none was presented, or the one presented did not verify.

    One class for both arms, because today they are one outcome to the client -- the same 401 and
    the same body -- and `bounded_reason` is the only thing that tells them apart. Splitting them
    would put that distinction in the class name, which D-02 makes the log event, without either
    half meaning anything different to a caller.
    """

    error_class = AUTH_REQUIRED

    def __init__(self, *, bounded_reason: BoundedReason | None) -> None:
        self.bounded_reason = bounded_reason
        super().__init__(f"invalid external jwt: {bounded_reason}")

    def log_fields(self) -> dict[str, str | None]:
        # A `StrEnum` member, stringified here exactly as the deleted `_reject` stringified it, so
        # the field's type in the log pipeline is unchanged by the migration.
        return {"bounded_reason": None if self.bounded_reason is None else str(self.bounded_reason)}


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


# --- Creation arms: the consuming transaction in `auth/create_user.py` ---


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


# --- Lookup arms: the providerData read in `auth/firebase.py` ---


class ProviderLookupError(AuthRejected):
    """The provider lookup's rejections, and never raised itself -- it is the group's shared shape.

    They consolidate here rather than beside the seam in `auth/adapters.py` so that the whole family
    keeps one `add_exception_handler` registration and one vocabulary test. Like the rest of the
    family these are outside the service-error tree in `error_handlers.py`.

    Per D-12 there is no `result` attribute: the internal outcome enum these arms used to carry has
    no consumer once the class itself is the vocabulary.
    """

    def __init__(self, *, stage: str, cause: str | None = None) -> None:
        # Plain strings, both of them ours: no provider text is ever admissible in either field.
        self.stage = stage
        self.cause = cause
        super().__init__(f"{type(self).__name__.lower()} at {stage}")

    def log_fields(self) -> dict[str, str | None]:
        fields: dict[str, str | None] = {"stage": self.stage}
        if self.cause is not None:
            fields["cause"] = self.cause
        return fields


class UserNotFound(ProviderLookupError):
    """The provider stated the account does not exist: definitive, and it spends no retry budget."""

    error_class = AUTH_REQUIRED


class Unavailable(ProviderLookupError):
    """The read could not be completed: an exhausted retry budget, or no app configured for the issuer.

    Retryable to the client, which is the whole reason it is not collapsed into the 401 above: a 503
    tells a caller to come back, and a 401 tells it its token is no good.
    """

    error_class = VERIFICATION_TEMPORARILY_UNAVAILABLE


class NotLinked(ProviderLookupError):
    """A providerData shape outside the accept set, so no provider account may be claimed for it.

    `cause` names the real reason and is a bounded string of our own choosing. The real reason never
    reaches the client -- the body is the shared one-field `operation_not_allowed` and nothing else.
    """

    error_class = OPERATION_NOT_ALLOWED


# --- Challenge arms: the binding comparison in `auth/challenges.py`, and the precedence block in
# `routers/auth.py::_complete` that surrounds it ---


class ChallengeRejected(AuthRejected):
    """The five challenge rejections' one shape, and never raised itself -- only its leaves are.

    The 409 is declared here and nowhere below, deliberately. Completion must not become a
    challenge-enumeration oracle, so there is exactly *one* answer for all five, in one place: a
    future edit cannot make one of them answer differently without overriding this on purpose,
    where a reviewer sees it. That is a deliberate divergence from the
    `AnalysisError`/`TransientLLMError` pair in `error_handlers.py`, which re-declares `error_class` on the
    child; here the re-declaration is the failure mode, not the convention.

    None of the five carries an `__init__` or a field, so none can be handed the secret challenge
    handle to put in a log line. The vocabulary test's leaf rule is satisfied by inheritance from
    this class -- a strict ancestor other than `AuthRejected` -- rather than by five declarations.
    """

    error_class = CHALLENGE_REQUIRED


class ChallengeNotFound(ChallengeRejected):
    """No row carries the handle presented, compared byte for byte and never trimmed."""


class ChallengeExpired(ChallengeRejected):
    """The claim found the row still unclaimed but past its expiry -- the one expiry evaluation."""


class ChallengeConsumed(ChallengeRejected):
    """The handle was already spent, or another attempt holds the claim; there is no replay."""


class ChallengeIdentityMismatch(ChallengeRejected):
    """The row is bound to an identity that is not the caller's, linked or pre-auth."""


class ChallengeOperationMismatch(ChallengeRejected):
    """The row was issued for another operation, so this route may not spend it."""
