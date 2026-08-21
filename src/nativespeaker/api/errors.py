"""The one client-visible error registry (D-10, spec 01-foundation.md §3).

One response model, one closed registry table, one response factory. Later phases append classes
here by calling `register_class`; no phase defines its own response shape or handler.

This plan registers only the seven §3.2 foundation classes. Plan 02 completes D-09 by absorbing
the existing business classes out of `exceptions.py` into this same module.
"""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from starlette.responses import JSONResponse

# The machine-readable class codes the body may carry. A typo is a ValidationError at construction
# rather than a runtime 500. Later phases extend this Literal alongside their `register_class` call.
ErrorCode = Literal["auth_required",
                    "preauth_identity_not_allowed",
                    "account_unavailable",
                    "challenge_required",
                    "invalid_request",
                    "verification_temporarily_unavailable",
                    "rate_limited"]


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


# The seven §3.2 foundation classes. Copy is neutral by construction: it names no issuer, no
# integration, and no failed check, so no branch within a class is distinguishable from another.
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
