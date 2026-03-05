import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.exceptions import (
    AnalysisError,
    AuthenticationError,
    ChatHistoryLimitError,
    CircuitOpenError,
    DatabaseNotInitializedError,
    InvalidChatError,
    InvalidCursorError,
    PageSizeLimitError,
    PermanentLLMError,
    QueueFullError,
    TransientLLMError,
    UnsupportedLanguageError,
)
from app.schema import ErrorResponse

logger = logging.getLogger(__name__)

_STATUS_REMAP: dict[int, int] = {
    405: 400,
    406: 400,
    409: 400,
    410: 404,
    413: 400,
    415: 400,
    422: 400,
    429: 503,
    502: 503,
    504: 503,
}

_CODE_MAP: dict[int, str] = {
    400: "invalid_request",
    401: "unauthorized",
    404: "not_found",
    503: "service_unavailable",
    500: "internal_error",
}


async def unsupported_language_handler(_: Request, exc: UnsupportedLanguageError) -> JSONResponse:
    return JSONResponse(status_code=400, content=ErrorResponse(code="invalid_request").model_dump())


async def transient_llm_error_handler(_: Request, exc: TransientLLMError) -> JSONResponse:
    return JSONResponse(status_code=503, content=ErrorResponse(code="service_unavailable").model_dump())


async def permanent_llm_error_handler(_: Request, exc: PermanentLLMError) -> JSONResponse:
    return JSONResponse(status_code=503, content=ErrorResponse(code="service_unavailable").model_dump())


async def analysis_error_handler(_: Request, exc: AnalysisError) -> JSONResponse:
    logger.error("Analysis failed: %s", exc)
    return JSONResponse(status_code=500, content=ErrorResponse(code="internal_error").model_dump())


async def invalid_chat_handler(_: Request, exc: InvalidChatError) -> JSONResponse:
    return JSONResponse(status_code=404, content=ErrorResponse(code="not_found").model_dump())


async def invalid_cursor_error_handler(_: Request, exc: InvalidCursorError) -> JSONResponse:
    return JSONResponse(status_code=400, content=ErrorResponse(code="invalid_request").model_dump())


async def page_size_limit_handler(_: Request, exc: PageSizeLimitError) -> JSONResponse:
    return JSONResponse(status_code=400, content=ErrorResponse(code="invalid_request").model_dump())


async def queue_full_handler(_: Request, exc: QueueFullError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(code="service_unavailable").model_dump(),
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


async def circuit_open_handler(_: Request, exc: CircuitOpenError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(code="service_unavailable").model_dump(),
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


async def chat_history_limit_handler(_: Request, exc: ChatHistoryLimitError) -> JSONResponse:
    return JSONResponse(status_code=400, content=ErrorResponse(code="invalid_request").model_dump())


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    logger.error("Validation error: %s", exc)
    return JSONResponse(status_code=400, content=ErrorResponse(code="invalid_request").model_dump())


async def auth_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    logger.warning("Authentication failure: %s", exc)
    return JSONResponse(
        status_code=401,
        content=ErrorResponse(code="unauthorized").model_dump(),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def database_not_initialized_handler(_: Request, exc: DatabaseNotInitializedError) -> JSONResponse:
    logger.error("Database not initialized: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content=ErrorResponse(code="internal_error").model_dump())


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = _STATUS_REMAP.get(exc.status_code, exc.status_code)
    if status not in _CODE_MAP:
        status = 500
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(code=_CODE_MAP[status]).model_dump(),
        headers=getattr(exc, "headers", None),
    )


async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content=ErrorResponse(code="internal_error").model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UnsupportedLanguageError, unsupported_language_handler)
    app.add_exception_handler(TransientLLMError, transient_llm_error_handler)
    app.add_exception_handler(PermanentLLMError, permanent_llm_error_handler)
    app.add_exception_handler(AnalysisError, analysis_error_handler)
    app.add_exception_handler(InvalidChatError, invalid_chat_handler)
    app.add_exception_handler(InvalidCursorError, invalid_cursor_error_handler)
    app.add_exception_handler(PageSizeLimitError, page_size_limit_handler)
    app.add_exception_handler(QueueFullError, queue_full_handler)
    app.add_exception_handler(CircuitOpenError, circuit_open_handler)
    app.add_exception_handler(ChatHistoryLimitError, chat_history_limit_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(AuthenticationError, auth_error_handler)
    app.add_exception_handler(DatabaseNotInitializedError, database_not_initialized_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
