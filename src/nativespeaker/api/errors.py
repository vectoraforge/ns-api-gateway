"""The one client-visible error registry (D-10, spec 01-foundation.md §3).

One response model, one closed registry table, one response factory, one exception hierarchy.
Later phases append classes here by calling `register_class`; no phase defines its own response
shape or handler.

D-09 is complete as of plan 02: every client-visible class in the service lives here.
`exceptions.py` no longer exists and `models/api.py` no longer declares the error body.
"""
import logging
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel
from starlette.responses import JSONResponse

# The machine-readable class codes the body may carry. A typo is a ValidationError at construction
# rather than a runtime 500. Later phases extend this Literal alongside their `register_class` call.
#
# D-11: the v1.3 401 code `"unauthorized"` is retired. `auth_required` is the only 401 the service
# emits -- once the barrier owns acceptance nothing else can produce one, so keeping both would
# leave a code no branch reaches, which §3.1 forbids.
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
                    "out_of_scope"]


@dataclass(frozen=True, slots=True)
class ErrorClass:
    """One client-visible error class: exactly one status, one code, one copy (§3.1 anti-oracle)."""
    name: str
    status: int
    code: ErrorCode
    copy: str


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
    """Build the shared response for a registered class.

    The barrier awaits the returned object against `(scope, receive, send)`; it never raises it.
    `add_middleware` places user middleware outside Starlette's ExceptionMiddleware, so a raised
    registry error would bypass every registered handler and surface as a 500 (D-01).
    """
    return JSONResponse(status_code=cls.status,
                        content=ErrorResponse(code=cls.code).model_dump(),
                        headers=headers)


# ---------------------------------------------------------------------------
# The seven §3.2 foundation classes
#
# Copy is neutral by construction: it names no issuer, no integration, and no failed check, so no
# branch within a class is distinguishable from another. It also never tells the caller they did
# something wrong or implies abuse -- it states the condition and the remediation.
# ---------------------------------------------------------------------------

AUTH_REQUIRED = register_class(ErrorClass(
    name="auth_required",
    status=401,
    code="auth_required",
    copy="Authentication is required. Sign in again and retry with a fresh token.",
))

PREAUTH_IDENTITY_NOT_ALLOWED = register_class(ErrorClass(
    name="preauth_identity_not_allowed",
    status=403,
    code="preauth_identity_not_allowed",
    copy="Account setup must be completed before this request.",
))

ACCOUNT_UNAVAILABLE = register_class(ErrorClass(
    name="account_unavailable",
    status=403,
    code="account_unavailable",
    copy="Account unavailable -- contact support.",
))

CHALLENGE_REQUIRED = register_class(ErrorClass(
    name="challenge_required",
    status=409,
    code="challenge_required",
    copy="Prepare a fresh challenge and retry.",
))

INVALID_REQUEST = register_class(ErrorClass(
    name="invalid_request",
    status=400,
    code="invalid_request",
    copy="The request is invalid. Correct it and resend.",
))

VERIFICATION_TEMPORARILY_UNAVAILABLE = register_class(ErrorClass(
    name="verification_temporarily_unavailable",
    status=503,
    code="verification_temporarily_unavailable",
    copy="Temporarily unavailable. Retry the whole operation later with backoff.",
))

# Registered even though D-05 removed backend traffic limiting: per D-07 this is the class Envoy's
# 429 body must name once the gateway contract lands, and §3.2 pins it as the generic 429 every
# unspecialized rate-limit rejection carries.
RATE_LIMITED = register_class(ErrorClass(
    name="rate_limited",
    status=429,
    code="rate_limited",
    copy="Too many requests. Wait for the indicated interval and retry.",
))

# ---------------------------------------------------------------------------
# The pre-existing business classes, absorbed from exceptions.py (D-09)
#
# Each keeps its v1.6 code and status verbatim so §8.3's "existing non-auth error contracts
# unchanged" holds. `invalid_request` (400) is reused above rather than re-minted: §3.1 forbids
# near-duplicates.
# ---------------------------------------------------------------------------

VALIDATION_ERROR = register_class(ErrorClass(
    name="validation_error",
    status=422,
    code="validation_error",
    copy="The request body did not match the expected shape. Correct it and resend.",
))

NOT_FOUND = register_class(ErrorClass(
    name="not_found",
    status=404,
    code="not_found",
    copy="No such resource at this path.",
))

# A1: 405 gets its own class at its own status rather than folding into invalid_request. Folding is
# the same lie as the deleted `_STATUS_REMAP` 405 -> 400 entry, and there is no anti-oracle cost --
# a 405 is only reachable by a caller the barrier already admitted.
METHOD_NOT_ALLOWED = register_class(ErrorClass(
    name="method_not_allowed",
    status=405,
    code="method_not_allowed",
    copy="This path does not serve that method. The Allow header lists the ones it does.",
))

INTERNAL_ERROR = register_class(ErrorClass(
    name="internal_error",
    status=500,
    code="internal_error",
    copy="The request could not be completed. Retry later.",
))

SERVICE_UNAVAILABLE = register_class(ErrorClass(
    name="service_unavailable",
    status=503,
    code="service_unavailable",
    copy="The service is busy. Wait for the indicated interval and retry.",
))

QUOTA_EXCEEDED = register_class(ErrorClass(
    name="quota_exceeded",
    status=429,
    code="quota_exceeded",
    copy="The allowance for the current period is used up. It refreshes next period.",
))

OUT_OF_SCOPE = register_class(ErrorClass(
    name="out_of_scope",
    status=400,
    code="out_of_scope",
    copy="This request is outside the scope of linguistic analysis. Send a phrase to analyse.",
))

# No class is declared for 415. `python-multipart` is not installed, so a `Form` or `File`
# parameter cannot even be declared and no branch can reach that status. Declaring an unreachable
# class is exactly the defect D-11 corrects for the retired 401 code -- apply it consistently.

# ---------------------------------------------------------------------------
# Framework-exception mapping (D-12)
#
# This replaces `app.errors._STATUS_REMAP` + `_CODE_MAP`, which were deleted outright rather than
# trimmed: one entry folded 409 -> 400, and the registry uses 409 for `challenge_required`, so a
# framework 409 would have surfaced as `invalid_request`. Every key here maps to a class carrying
# that same status -- no status is ever folded into a different one, and `assert_registry_total`
# proves it.
#
# 403 is deliberately absent. Two classes sit at 403 -- `preauth_identity_not_allowed` and
# `account_unavailable` -- and neither is the generic answer, so any entry would be an arbitrary
# lie of exactly the kind D-12 deletes. Both are emitted by the barrier through `error_response`,
# which needs no status lookup. A bare framework 403 is therefore a programming error and takes
# the loud unmapped-status path.
# ---------------------------------------------------------------------------

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
    """Fail closed on a registry defect. Called from the lifespan, before the app serves traffic.

    Four invariants, each of which a later phase could break by appending a class carelessly:
    every registered class carries exactly one status under its own name, no two classes share a
    code, every status maps to a registered class carrying that same status, and the `ErrorCode`
    Literal set equals the set of registered codes exactly.
    """
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


# ---------------------------------------------------------------------------
# The service exception hierarchy, absorbed from exceptions.py (D-09)
#
# The v1.6 `status_code: int` / `error_code: ErrorCode` class-attribute pair is replaced by a
# single `error_class: ErrorClass`. A subclass can no longer name a status and a code that
# disagree, which is how `WebhookVerificationError` came to carry the 422 code at status 400.
# ---------------------------------------------------------------------------


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
    """Raised when all retry attempts failed due to a transient LLM error.
    __cause__ holds the original exception from the last failed attempt."""
    error_class = SERVICE_UNAVAILABLE
    log_level = None


class PermanentLLMError(AnalysisError):
    """Raised when the LLM call failed with a non-transient error (no retry possible).
    __cause__ holds the original exception."""
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
    """Base for authentication failures -- maps to the one 401 class (D-11).

    Plan 04 deletes its v1.6 raise sites, after which plan 03's three identity accessors are its
    only remaining ones.
    """
    error_class = AUTH_REQUIRED
    log_level = logging.WARNING

    def extra_headers(self) -> dict[str, str]:
        return {"WWW-Authenticate": "Bearer"}


class WebhookVerificationError(ServiceError):
    """JWS signature verification failed on incoming webhook."""
    error_class = INVALID_REQUEST


class DatabaseNotInitializedError(ServiceError):
    """Raised when DB session factory is not initialized -- maps to 500."""
    error_class = INTERNAL_ERROR
    log_level = logging.ERROR

    def __init__(self):
        super().__init__("Database session factory is not initialized")
