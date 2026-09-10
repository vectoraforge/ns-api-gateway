import logging
import sys
import time
import typing
import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_EXCLUDED_PATHS = frozenset({"/health/ready"})

# Capped at no lower than WARNING, on one criterion: a library that logs a request body, a
# request line or SQL. `openai` logs the whole chat-completion body at DEBUG, an admitted level.
# `uvicorn.access` is the duplicate of the line `RequestLoggingMiddleware` writes below, and it
# honours neither `_EXCLUDED_PATHS` nor the structured format.
_QUIETED_LIBRARIES = ("httpx", "httpcore", "sqlalchemy.engine",
                      "openai", "langchain", "langchain_core",
                      "urllib3", "google.auth", "uvicorn.access")

logger = structlog.get_logger()


def setup_logging(log_level: str,
                  log_stream: typing.TextIO = sys.stderr) -> None:
    """Configure structlog + stdlib logging pipeline."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[*shared_processors,
                    structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level.upper()),
        cache_logger_on_first_use=True,
    )

    console_handler = logging.StreamHandler(log_stream)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
                # `colors` defaults to "not Windows" rather than to `isatty`, so without this every
                # line carries escape codes into a stderr that is never a terminal.
                structlog.dev.ConsoleRenderer(colors=False,
                                              exception_formatter=structlog.dev.plain_traceback),
            ],
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.setLevel(log_level.upper())

    for name in _QUIETED_LIBRARIES:
        # A ceiling, never a floor. A level set on a child outranks the root in both directions: at
        # LOG_LEVEL=ERROR a flat WARNING would raise these nine above the application's own loggers,
        # so an operator cutting noise during an incident would lose `notification_rejected` and its
        # `stage` and keep the httpx and SQL chatter. `root.level`, not the argument, because
        # `setLevel` above is what turned the name into a number.
        logging.getLogger(name).setLevel(max(logging.WARNING, root.level))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,
                       request: Request,
                       call_next: Callable) -> Response:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid.uuid4()),
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # `ServerErrorMiddleware` sits outside this one and answers 500, so nothing else logs it.
            self._log_request(request, status_code=500, start=start)
            raise

        self._log_request(request, status_code=response.status_code, start=start)
        return response

    def _log_request(self, request: Request, *, status_code: int, start: float) -> None:
        """One access-log line per request, written on the raising exit as well as the ordinary one."""
        if request.url.path in _EXCLUDED_PATHS:
            return
        # Split at 500, not at 400: an access line at ERROR for a 401 probe or a 404 typo would
        # page on a client's mistake.
        if status_code >= 500:
            log_method = logger.error
        elif status_code >= 400:
            log_method = logger.warning
        else:
            log_method = logger.info
        log_method("request", status_code=status_code,
                   duration_ms=round((time.perf_counter() - start) * 1000, 2))
