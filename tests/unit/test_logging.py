import io
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
    async def health_ready(boom: bool = False):
        if boom:
            raise RuntimeError("a readiness probe that failed")
        return {"status": "ok"}

    @app.get("/boom")
    async def boom_route():
        raise RuntimeError("a handler failure no registered handler claims")

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


def test_middleware_error_level_for_a_server_error(_logging_app):
    with capture_logs() as cap_logs:
        with TestClient(_logging_app) as client:
            client.get("/error")

    request_logs = [log for log in cap_logs if log["event"] == "request"]
    assert len(request_logs) == 1
    assert request_logs[0]["log_level"] == "error"


def test_middleware_warning_level_for_a_client_error(_logging_app):
    """ERROR is what an operator is paged on, so an unmatched path may not reach it."""
    with capture_logs() as cap_logs:
        with TestClient(_logging_app) as client:
            response = client.get("/no-such-path")

    assert response.status_code == 404
    request_logs = [log for log in cap_logs if log["event"] == "request"]
    assert [(log["status_code"], log["log_level"]) for log in request_logs] == [(404, "warning")]


def test_middleware_logs_the_request_when_the_handler_raises(_logging_app):
    """WR-07: `ServerErrorMiddleware` sits outside every user middleware, so the 500 exits past it."""
    with capture_logs() as cap_logs:
        with TestClient(_logging_app, raise_server_exceptions=False) as client:
            response = client.get("/boom")

    assert response.status_code == 500
    request_logs = [log for log in cap_logs if log["event"] == "request"]
    assert len(request_logs) == 1
    assert request_logs[0]["status_code"] == 500
    assert request_logs[0]["log_level"] == "error"
    assert "duration_ms" in request_logs[0]


def test_middleware_still_excludes_the_probe_path_when_it_raises(_logging_app):
    """The exclusion applies to both exits, so a failing probe stays out of the access log."""
    with capture_logs() as cap_logs:
        with TestClient(_logging_app, raise_server_exceptions=False) as client:
            client.get("/health/ready?boom=true")

    assert [log for log in cap_logs if log["event"] == "request"] == []


def test_the_line_is_written_under_the_production_error_handlers():
    """The registered bare-`Exception` handler installs on `ServerErrorMiddleware`, outside this one."""
    from nativespeaker.api.app.error_handlers import register_exception_handlers

    app = FastAPI()

    @app.get("/boom")
    async def boom_route():
        raise RuntimeError("a handler failure no registered handler claims")

    register_exception_handlers(app)
    # ty cannot match BaseHTTPMiddleware subclasses against Starlette's factory protocol.
    app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]

    with capture_logs() as cap_logs:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom")

    assert (response.status_code, response.json()) == (500, {"code": "internal_error"})
    # Only the access-log line: the handler's own logger is a module-level proxy another test may hold.
    request_logs = [log for log in cap_logs if log["event"] == "request"]
    assert [(log["status_code"], log["log_level"]) for log in request_logs] == [(500, "error")]


class TestTheRenderedLineIsPlainText:
    """WR-23. structlog picks `colors` off the platform, never off `isatty`, so on Linux the
    escape codes land in the aggregated log store where every field extractor has to strip them."""

    def test_no_record_carries_an_escape_sequence(self):
        stream = io.StringIO()
        setup_logging(log_level="INFO", log_stream=stream)

        logs_module.logger.warning("auth_challenge_operation_not_issuable", operation="x")

        assert "\x1b" not in stream.getvalue()

    def test_the_event_and_its_fields_still_render(self):
        """The control: an empty line, or one rendered by some other renderer, would also pass above."""
        stream = io.StringIO()
        setup_logging(log_level="INFO", log_stream=stream)

        logs_module.logger.warning("auth_challenge_operation_not_issuable", operation="x")

        written = stream.getvalue()
        assert "auth_challenge_operation_not_issuable" in written
        assert "operation=x" in written


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
