import logging
import re

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from nativespeaker.api.errors import (
    AppError,
    ErrorResponse,
    InternalError,
    ValidationError,
    class_answering_status,
)

logger = structlog.get_logger()

_LOGGABLE = frozenset({logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL})

_FIRST = re.compile(r"(.)([A-Z][a-z]+)")
_REST = re.compile(r"([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    r"""An exception class name as the log event name it stands for.
    Two substitutions, because a single `\B([A-Z])` rule splits an acronym:
    `InvalidExternalJwt` -> `invalid_external_jwt`, not `invalid_external_j_w_t`."""
    return _REST.sub(r"\1_\2", _FIRST.sub(r"\1_\2", name)).lower()


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Record the failure once, then answer with the status and code its class declared."""
    assert isinstance(exc, AppError)
    if exc.log_level is not None:
        # structlog's filtering logger indexes the five standard levels and raises on any other.
        level = exc.log_level if exc.log_level in _LOGGABLE else logging.ERROR
        record = getattr(logger, logging.getLevelName(level).lower())
        record(camel_to_snake(type(exc).__name__),
               exc_info=(exc.log_level >= logging.ERROR), **exc.log_fields())
    return JSONResponse(status_code=exc.status,
                        content=ErrorResponse(code=exc.code).model_dump(),
                        headers=exc.extra_headers())


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Validation error", exc_info=exc)
    return await app_error_handler(request, ValidationError())


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Answer a framework-raised HTTPException with the one class that status declares."""
    # The marked classes are closed, so a miss is a hole in the tree and is logged rather than defaulted.
    assert isinstance(exc, StarletteHTTPException)
    answering = class_answering_status(exc.status_code)
    if answering is None:
        logger.error("error_registry_unmapped_status", unmapped_status=exc.status_code)
        return await app_error_handler(request, InternalError())
    # Forwarding `headers` is how the router's `Allow` header survives a 405.
    return await app_error_handler(request, answering(headers=getattr(exc, "headers", None)))


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", exc_info=exc)
    return await app_error_handler(request, InternalError())


def register_exception_handlers(app: FastAPI) -> None:
    # One entry covers every subclass: Starlette resolves a handler by walking `type(exc).__mro__`.
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
