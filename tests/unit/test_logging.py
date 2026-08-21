import logging

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

import nativespeaker.api.logs as logs_module
from nativespeaker.api.logs import RequestLoggingMiddleware, setup_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    """Save and restore root logger state and structlog defaults around each test.

    The reset runs *before* the test as well as after. `setup_logging` configures structlog with
    `cache_logger_on_first_use=True`, so once any other module has called it -- an e2e module's
    `_app_lifespan` fixture does, in a combined run -- `logs.py`'s module-level lazy proxy has
    already bound and cached a concrete logger that `capture_logs` cannot intercept, and these
    tests see an empty capture list. Restoring only afterwards never undid that, which is why they
    passed alone and failed in a combined run (deferred item D-35-01-A).
    """
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    _uncache_module_logger()
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()
    _uncache_module_logger()
    root.handlers = original_handlers
    root.setLevel(original_level)


def _uncache_module_logger():
    """Drop the concrete logger `logs.logger` cached on first use, restoring the lazy proxy.

    `structlog.reset_defaults()` resets the *configuration*; it cannot reach into a proxy that has
    already replaced its own `_logger` with a bound instance built from the old configuration.
    """
    logs_module.logger = structlog.get_logger()


def test_console_output_always_active():
    setup_logging(log_level="INFO")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.StreamHandler)


def test_request_id_bound_in_context():
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="test-req-123")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["request_id"] == "test-req-123"


@pytest.fixture
def _logging_app():
    """Minimal FastAPI app with RequestLoggingMiddleware for testing."""
    app = FastAPI()
    # See app/main.py: ty cannot match BaseHTTPMiddleware subclasses against
    # Starlette's _MiddlewareFactory ParamSpec protocol.
    app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]

    @app.get("/test")
    async def test_route():
        return {"ok": True}

    @app.get("/health/ready")
    async def health_ready():
        return {"status": "ok"}

    @app.get("/error")
    async def error_route():
        from starlette.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": "fail"})

    return app


def test_middleware_logs_request_on_response(_logging_app):
    with capture_logs() as cap_logs:
        with TestClient(_logging_app) as client:
            client.get("/test")

    request_logs = [log for log in cap_logs if log["event"] == "request"]
    assert len(request_logs) == 1
    entry = request_logs[0]
    assert entry["status_code"] == 200
    assert "duration_ms" in entry
    assert entry["log_level"] == "info"


def test_middleware_excludes_health_ready(_logging_app):
    with capture_logs() as cap_logs:
        with TestClient(_logging_app) as client:
            client.get("/health/ready")

    request_logs = [log for log in cap_logs if log["event"] == "request"]
    assert len(request_logs) == 0


def test_middleware_error_level_for_non_2xx(_logging_app):
    with capture_logs() as cap_logs:
        with TestClient(_logging_app) as client:
            client.get("/error")

    request_logs = [log for log in cap_logs if log["event"] == "request"]
    assert len(request_logs) == 1
    assert request_logs[0]["log_level"] == "error"


def test_third_party_loggers_suppressed():
    setup_logging(log_level="INFO")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
