import logging

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

import nativespeaker.api.logs as logs_module
from nativespeaker.api.config import LogLevel
from nativespeaker.api.logs import RequestLoggingMiddleware, setup_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    """Save and restore logger state around each test; the reset runs before as well as after."""
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
    """Drop the concrete logger cached on first use: resetting the configuration cannot reach a bound proxy."""
    logs_module.logger = structlog.get_logger()


def test_console_output_always_active():
    setup_logging(log_level="INFO")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.StreamHandler)


def test_request_id_bound_in_context():
    """Request correlation travels through contextvars, which is what carries it into every record."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="test-req-123")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["request_id"] == "test-req-123"


@pytest.fixture
def _logging_app():
    """Minimal FastAPI app with RequestLoggingMiddleware for testing."""
    app = FastAPI()
    # ty cannot match BaseHTTPMiddleware subclasses against Starlette's factory protocol.
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


class TestEveryConfigurableLevelBoots:
    """setup_logging runs before any exception handler exists, so an unusable level crashloops."""

    @pytest.mark.parametrize("level", sorted(member.value for member in LogLevel))
    def test_the_config_admits_only_levels_setup_logging_can_use(self, level):
        """The whole bug: LogLevel admitted FATAL and structlog has no entry for it."""
        setup_logging(level)

        assert structlog.get_config()["wrapper_class"] is not None

    def test_the_level_the_enum_no_longer_admits_is_the_one_that_crashed(self):
        """The control: FATAL is a real stdlib level, so only the narrowing keeps it out."""
        assert "FATAL" in logging.getLevelNamesMapping()
        assert "FATAL" not in {member.value for member in LogLevel}
        with pytest.raises(KeyError):
            structlog.make_filtering_bound_logger("FATAL")
