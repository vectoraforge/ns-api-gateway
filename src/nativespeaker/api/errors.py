"""The one client-visible error registry: one response model, one table, one factory, one hierarchy."""
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, get_args
from uuid import UUID

from pydantic import BaseModel
from starlette.responses import JSONResponse

# The codes the body may carry. A typo is a ValidationError at construction, not a runtime 500.
ErrorCode = Literal["auth_required",
                    "preauth_identity_not_allowed",
                    "account_unavailable",
                    "challenge_required",
                    "invalid_request",
                    "verification_temporarily_unavailable",
                    "rate_limited",
                    "validation_error",
                    "not_found",
                    "method_not_allowed",
                    "internal_error",
                    "service_unavailable",
                    "quota_exceeded",
                    "out_of_scope",
                    "identity_already_linked",
                    "operation_not_allowed"]


@dataclass(frozen=True, slots=True)
class ErrorClass:
    """One client-visible error class: exactly one status and one code."""
    name: str
    status: int
    code: ErrorCode


class ErrorResponse(BaseModel):
    """The single shared error body shape. Exactly one field -- do not add more."""
    code: ErrorCode


REGISTRY: dict[str, ErrorClass] = {}


def register_class(cls: ErrorClass) -> ErrorClass:
    """Append-only registration. A duplicate name or code is a programming error, not a merge."""
    if cls.name in REGISTRY:
        raise ValueError(f"error class {cls.name!r} is already registered")
    for existing in REGISTRY.values():
        if existing.code == cls.code:
            raise ValueError(f"error code {cls.code!r} is already registered by {existing.name!r}")
    REGISTRY[cls.name] = cls
    return cls


def error_response(cls: ErrorClass, *, headers: dict[str, str] | None = None) -> JSONResponse:
    """Build the shared response for a registered class -- every error body is produced here."""
    return JSONResponse(status_code=cls.status,
                        content=ErrorResponse(code=cls.code).model_dump(),
                        headers=headers)


# Neutral by construction: no branch within a class is distinguishable from another.
AUTH_REQUIRED = register_class(ErrorClass(
    name="auth_required",
    status=401,
    code="auth_required",
))

PREAUTH_IDENTITY_NOT_ALLOWED = register_class(ErrorClass(
    name="preauth_identity_not_allowed",
    status=403,
    code="preauth_identity_not_allowed",
))

ACCOUNT_UNAVAILABLE = register_class(ErrorClass(
    name="account_unavailable",
    status=403,
    code="account_unavailable",
))

CHALLENGE_REQUIRED = register_class(ErrorClass(
    name="challenge_required",
    status=409,
    code="challenge_required",
))

INVALID_REQUEST = register_class(ErrorClass(
    name="invalid_request",
    status=400,
    code="invalid_request",
))

VERIFICATION_TEMPORARILY_UNAVAILABLE = register_class(ErrorClass(
    name="verification_temporarily_unavailable",
    status=503,
    code="verification_temporarily_unavailable",
))

# The generic 429 every unspecialized rate-limit rejection carries, including Envoy's.
RATE_LIMITED = register_class(ErrorClass(
    name="rate_limited",
    status=429,
    code="rate_limited",
))

VALIDATION_ERROR = register_class(ErrorClass(
    name="validation_error",
    status=422,
    code="validation_error",
))

NOT_FOUND = register_class(ErrorClass(
    name="not_found",
    status=404,
    code="not_found",
))

# 405 keeps its own status. An unauthenticated caller can reach it, and it discloses only that the path exists.
METHOD_NOT_ALLOWED = register_class(ErrorClass(
    name="method_not_allowed",
    status=405,
    code="method_not_allowed",
))

INTERNAL_ERROR = register_class(ErrorClass(
    name="internal_error",
    status=500,
    code="internal_error",
))

SERVICE_UNAVAILABLE = register_class(ErrorClass(
    name="service_unavailable",
    status=503,
    code="service_unavailable",
))

QUOTA_EXCEEDED = register_class(ErrorClass(
    name="quota_exceeded",
    status=429,
    code="quota_exceeded",
))

OUT_OF_SCOPE = register_class(ErrorClass(
    name="out_of_scope",
    status=400,
    code="out_of_scope",
))

# Shares 409 with `challenge_required`: codes must be unique, statuses need not be.
IDENTITY_ALREADY_LINKED = register_class(ErrorClass(
    name="identity_already_linked",
    status=409,
    code="identity_already_linked",
))

OPERATION_NOT_ALLOWED = register_class(ErrorClass(
    name="operation_not_allowed",
    status=403,
    code="operation_not_allowed",
))

# No 415: `python-multipart` is absent, so a Form or File parameter cannot be declared at all.

# No status is ever folded into another; 403 is absent because neither class there is the generic one.
STATUS_TO_CLASS: dict[int, ErrorClass] = {
    400: INVALID_REQUEST,
    401: AUTH_REQUIRED,
    404: NOT_FOUND,
    405: METHOD_NOT_ALLOWED,
    409: CHALLENGE_REQUIRED,
    422: VALIDATION_ERROR,
    429: RATE_LIMITED,
    500: INTERNAL_ERROR,
    503: SERVICE_UNAVAILABLE,
}


def assert_registry_total() -> None:
    """Fail closed on a registry defect, from the lifespan, before the app serves traffic."""
    problems: list[str] = []

    for name, cls in REGISTRY.items():
        if cls.name != name:
            problems.append(f"class registered under {name!r} carries name {cls.name!r}")

    seen: dict[str, str] = {}
    for cls in REGISTRY.values():
        if cls.code in seen:
            problems.append(f"code {cls.code!r} is shared by {seen[cls.code]!r} and {cls.name!r}")
        else:
            seen[cls.code] = cls.name

    for status, cls in STATUS_TO_CLASS.items():
        if REGISTRY.get(cls.name) is not cls:
            problems.append(f"status {status} maps to unregistered class {cls.name!r}")
        elif cls.status != status:
            problems.append(f"status {status} maps to {cls.name!r}, which carries status {cls.status}")

    declared = set(get_args(ErrorCode))
    registered = {cls.code for cls in REGISTRY.values()}
    if declared != registered:
        if declared - registered:
            problems.append(f"ErrorCode declares unregistered codes: {sorted(declared - registered)}")
        if registered - declared:
            problems.append(f"registered codes absent from ErrorCode: {sorted(registered - declared)}")

    if problems:
        raise RuntimeError("error registry is not total:\n  " + "\n  ".join(problems))


class AppError(Exception):
    """Base for every failure that has a client-visible answer."""

    # A class declaring neither answers 500 `internal_error`: the fail-closed default, not a shortcut.
    status: int = 500
    code: ErrorCode = "internal_error"
    log_level: int | None = logging.WARNING
    answers_framework_status: bool = False

    def extra_headers(self) -> dict[str, str] | None:
        return None

    def log_fields(self) -> dict[str, str | None]:
        """The extra fields this failure contributes to its one log line, and the only such channel."""
        return {}


def _family[T](root: type[T]) -> list[type[T]]:
    """Every class under `root`, at any depth -- an intermediate base is not a place to hide."""
    found: list[type[T]] = []
    for subclass in root.__subclasses__():
        found.append(subclass)
        found.extend(_family(subclass))
    return found


def _undeclared(classes: Sequence[type], *, root: type) -> list[str]:
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


def _tree_problems(root: type[AppError], *,
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

    problems.extend(_undeclared(classes, root=root))

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
    """Fail closed on a defect in the error tree, from the lifespan, before traffic is served."""
    problems = _tree_problems(AppError, declared_codes=frozenset(get_args(ErrorCode)))
    if problems:
        raise RuntimeError("error tree is not total:\n  " + "\n  ".join(problems))


class AccountUnavailable(AppError):
    """A historical identity row, or an active row whose user is not active."""

    # Declared once here: making one leaf answer differently takes an override a reviewer sees.
    status = 403
    code = "account_unavailable"


class HistoricalIdentity(AccountUnavailable):
    """The identity row's state is anything other than active."""


class BlockedUser(AccountUnavailable):
    """The identity row is active, but the user it resolves to is not."""


# One `error_class` per subclass, so a status and a code can never be named in disagreement.
class ServiceError(Exception):
    """Base exception for service layer errors."""
    error_class: ErrorClass = INTERNAL_ERROR
    log_level: int | None = None

    def extra_headers(self) -> dict[str, str] | None:
        return None


class UnsupportedLanguageError(ServiceError):
    """Raised when an unsupported language is requested"""
    error_class = INVALID_REQUEST

    def __init__(self, lang: str, supported: list[str]):
        self.lang = lang
        self.supported = supported
        super().__init__(f"Language '{lang}' not supported. Supported: {', '.join(supported)}")


class AnalysisError(ServiceError):
    """Raised when phrase analysis fails"""
    error_class = INTERNAL_ERROR
    log_level = logging.ERROR


class TransientLLMError(AnalysisError):
    """All retries failed on a transient LLM error; `__cause__` holds the last one."""
    error_class = SERVICE_UNAVAILABLE
    log_level = None


class PermanentLLMError(AnalysisError):
    """The LLM call failed with a non-transient error; `__cause__` holds it."""
    error_class = SERVICE_UNAVAILABLE
    log_level = None


class InvalidChatError(ServiceError):
    error_class = NOT_FOUND

    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")


class InvalidCursorError(ServiceError):
    error_class = INVALID_REQUEST

    def __init__(self):
        super().__init__("Invalid cursor")


class PageSizeLimitError(ServiceError):
    error_class = INVALID_REQUEST

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Limit exceeds maximum page size of {limit}")


class QueueFullError(ServiceError):
    error_class = SERVICE_UNAVAILABLE

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM queue is full")

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}


class CircuitOpenError(ServiceError):
    error_class = SERVICE_UNAVAILABLE

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM circuit breaker is open")

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}


class QuotaExceededError(ServiceError):
    error_class = QUOTA_EXCEEDED


class ChatHistoryLimitError(ServiceError):
    error_class = INVALID_REQUEST

    def __init__(self, max_messages: int):
        self.max_messages = max_messages
        super().__init__("Chat history limit reached")


class OutOfScopeError(ServiceError):
    error_class = OUT_OF_SCOPE

    def __init__(self):
        super().__init__("The request is outside the scope of linguistic analysis")


class AuthenticationError(ServiceError):
    """Base for authentication failures -- maps to the one 401 class."""
    error_class = AUTH_REQUIRED
    log_level = logging.WARNING

    def extra_headers(self) -> dict[str, str]:
        return {"WWW-Authenticate": "Bearer"}


class WebhookVerificationError(ServiceError):
    """JWS signature verification failed on incoming webhook."""
    error_class = INVALID_REQUEST


class DatabaseNotInitializedError(ServiceError):
    """The DB session factory is not initialized -- maps to 500."""
    error_class = INTERNAL_ERROR
    log_level = logging.ERROR

    def __init__(self):
        super().__init__("Database session factory is not initialized")


# All three reuse INTERNAL_ERROR; ERROR level adds the traceback, and their messages stay server-side.
class MissingUsageRowError(ServiceError):
    """An effective grant with no `core.user_monthly_usage` row -- maps to 500."""
    # Never minted here: that would turn a detectable broken invariant into a silent free allowance.
    error_class = INTERNAL_ERROR
    log_level = logging.ERROR

    def __init__(self, grant_id: UUID):
        self.grant_id = grant_id
        super().__init__(f"Grant {grant_id} has no core.user_monthly_usage row")


class MultipleEffectiveGrantsError(ServiceError):
    """More than one effective grant for one user -- maps to 500."""
    # A unique index makes this unreachable; asserted so dropping it fails loudly, never tie-breaks.
    error_class = INTERNAL_ERROR
    log_level = logging.ERROR

    def __init__(self, count: int, user_id: UUID):
        self.count = count
        self.user_id = user_id
        super().__init__(f"{count} effective grants for user {user_id}; refusing to tie-break")


class UnknownTierError(ServiceError):
    """A grant whose `tier_id` has no `core.access_tiers` row -- maps to 500."""
    # A foreign key makes this unreachable; the silent readings are a wrong 429 or a free service.
    error_class = INTERNAL_ERROR
    log_level = logging.ERROR

    def __init__(self, tier_id: str, grant_id: UUID):
        self.tier_id = tier_id
        self.grant_id = grant_id
        super().__init__(f"Grant {grant_id} references tier {tier_id!r}, which has no row")
