import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from nativespeaker.api.errors import (
    INTERNAL_ERROR,
    STATUS_TO_CLASS,
    VALIDATION_ERROR,
    ServiceError,
    error_response,
)

logger = structlog.get_logger()

_LEVEL_TO_METHOD = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "critical",
}


async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        method_name = _LEVEL_TO_METHOD.get(exc.log_level, "error")
        log_method = getattr(logger, method_name)
        log_method(str(exc), error_type=type(exc).__name__,
                   exc_info=(exc.log_level >= logging.ERROR))
    return error_response(exc.error_class, headers=exc.extra_headers())


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Validation error", exc_info=exc)
    return error_response(VALIDATION_ERROR)


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Answer a framework-raised HTTPException with the one class that status declares.

    There is no status folding and no code fallback: `STATUS_TO_CLASS` is closed and every entry
    carries its own key as its status. A miss is a registry hole, so it is logged loudly at ERROR
    rather than defaulting silently -- the failure mode the deleted `_CODE_MAP.get(status, 500)`
    made invisible.
    """
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
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
