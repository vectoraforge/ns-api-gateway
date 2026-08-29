import logging
import re

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from nativespeaker.api.auth.exceptions import AuthRejected
from nativespeaker.api.errors import (
    INTERNAL_ERROR,
    STATUS_TO_CLASS,
    VALIDATION_ERROR,
    ServiceError,
    error_response,
)

logger = structlog.get_logger()

_LOGGABLE = frozenset({logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL})

_FIRST = re.compile(r"(.)([A-Z][a-z]+)")
_REST = re.compile(r"([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    r"""An exception class name as the log event name it stands for.

    Two substitutions rather than one, because a single `\B([A-Z])` rule splits inside an acronym:
    `IdentityAlreadyLinked` -> `identity_already_linked`, and `InvalidExternalJwt` ->
    `invalid_external_jwt` rather than `invalid_external_j_w_t`.
    """
    return _REST.sub(r"\1_\2", _FIRST.sub(r"\1_\2", name)).lower()


async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        # structlog's filtering logger indexes the five standard levels and raises on any other.
        level = exc.log_level if exc.log_level in _LOGGABLE else logging.ERROR
        logger.log(level, str(exc), error_type=type(exc).__name__,
                   exc_info=(exc.log_level >= logging.ERROR))
    return error_response(exc.error_class, headers=exc.extra_headers())


async def auth_rejected_handler(request: Request, exc: Exception) -> JSONResponse:
    """Record one auth rejection, then answer with the class the exception declared."""
    assert isinstance(exc, AuthRejected)
    logger.warning(camel_to_snake(type(exc).__name__),
                   route=getattr(request.scope.get("route"), "path", None),
                   **exc.log_fields())
    return error_response(exc.error_class)


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Validation error", exc_info=exc)
    return error_response(VALIDATION_ERROR)


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Answer a framework-raised HTTPException with the one class that status declares."""
    # STATUS_TO_CLASS is closed, so a miss is a registry hole and is logged rather than defaulted.
    assert isinstance(exc, StarletteHTTPException)
    error_class = STATUS_TO_CLASS.get(exc.status_code)
    if error_class is None:
        logger.error("error_registry_unmapped_status", unmapped_status=exc.status_code)
        return error_response(INTERNAL_ERROR)
    # Forwarding `headers` is how the router's `Allow` header survives a 405.
    return error_response(error_class, headers=getattr(exc, "headers", None))


async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", exc_info=exc)
    return error_response(INTERNAL_ERROR)


def register_exception_handlers(app: FastAPI) -> None:
    # One entry covers every subclass: Starlette resolves a handler by walking `type(exc).__mro__`.
    app.add_exception_handler(AuthRejected, auth_rejected_handler)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
