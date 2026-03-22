import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.api.schema import ErrorResponse
from app.exceptions import ServiceError

logger = structlog.get_logger()

_LEVEL_TO_METHOD = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "critical",
}

_STATUS_REMAP: dict[int, int] = {
    405: 400,
    406: 400,
    409: 400,
    410: 404,
    413: 400,
    415: 400,

    502: 503,
    504: 503,
}

_CODE_MAP: dict[int, str] = {
    400: "invalid_request",
    401: "unauthorized",
    404: "not_found",
    422: "validation_error",
    429: "rate_limited",
    503: "service_unavailable",
    500: "internal_error",
}


async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        method_name = _LEVEL_TO_METHOD.get(exc.log_level, "error")
        log_method = getattr(logger, method_name)
        log_method(str(exc), error_type=type(exc).__name__,
                   exc_info=(exc.log_level >= logging.ERROR))
    return JSONResponse(status_code=exc.status_code,
                        content=ErrorResponse(code=exc.error_code).model_dump(),
                        headers=exc.extra_headers())


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Validation error", exc_info=exc)
    return JSONResponse(status_code=422, content=ErrorResponse(code="validation_error").model_dump())


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = _STATUS_REMAP.get(exc.status_code, exc.status_code)
    if status not in _CODE_MAP:
        status = 500
    return JSONResponse(status_code=status,
                        content=ErrorResponse(code=_CODE_MAP[status]).model_dump(),  # type: ignore[invalid-argument-type]
                        headers=getattr(exc, "headers", None))


async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content=ErrorResponse(code="internal_error").model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
