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
                structlog.dev.ConsoleRenderer(exception_formatter=structlog.dev.plain_traceback),
            ],
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.setLevel(log_level.upper())

    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)


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
        log_method = logger.info if status_code < 400 else logger.error
        log_method("request", status_code=status_code,
                   duration_ms=round((time.perf_counter() - start) * 1000, 2))
