import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.exceptions import (
    UnsupportedLanguageError,
    AnalysisError,
    InvalidChatError,
    QueueFullError,
    CircuitOpenError,
    ChatHistoryLimitError,
    MessageTooLargeError,
)

logger = logging.getLogger(__name__)


async def unsupported_language_handler(_: Request, exc: UnsupportedLanguageError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": f"Unsupported language: '{exc.lang}'"})


async def analysis_error_handler(_: Request, exc: AnalysisError) -> JSONResponse:
    logger.error("Analysis failed: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Analysis failed"})


async def invalid_chat_handler(_: Request, exc: InvalidChatError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def queue_full_handler(_: Request, exc: QueueFullError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "LLM queue is full"},
        headers={"Retry-After": str(exc.retry_after_seconds)}
    )


async def circuit_open_handler(_: Request, exc: CircuitOpenError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "LLM circuit breaker is open"},
        headers={"Retry-After": str(exc.retry_after_seconds)}
    )


async def chat_history_limit_handler(_: Request, exc: ChatHistoryLimitError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "Chat history limit reached"},
    )


async def message_too_large_handler(_: Request, exc: MessageTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"detail": f"{exc.role.capitalize()} message exceeds {exc.limit} characters"},
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    logger.error("Validation error: %s", exc)
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UnsupportedLanguageError, unsupported_language_handler)
    app.add_exception_handler(AnalysisError, analysis_error_handler)
    app.add_exception_handler(InvalidChatError, invalid_chat_handler)
    app.add_exception_handler(QueueFullError, queue_full_handler)
    app.add_exception_handler(CircuitOpenError, circuit_open_handler)
    app.add_exception_handler(ChatHistoryLimitError, chat_history_limit_handler)
    app.add_exception_handler(MessageTooLargeError, message_too_large_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)
