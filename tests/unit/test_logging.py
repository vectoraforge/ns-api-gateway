import logging

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.logging import RequestLoggingMiddleware, setup_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    """Save and restore root logger state and structlog defaults around each test."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    structlog.reset_defaults()
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_console_output_always_active():
    setup_logging(log_level="INFO")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.StreamHandler)


def test_json_file_output_when_path_set(tmp_path):
    json_path = str(tmp_path / "test.json")
    setup_logging(log_level="INFO", json_log_path=json_path)
    root = logging.getLogger()
    assert len(root.handlers) == 2
    assert isinstance(root.handlers[0], logging.StreamHandler)
    assert isinstance(root.handlers[1], logging.FileHandler)


def test_request_id_bound_in_context():
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="test-req-123")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["request_id"] == "test-req-123"


@pytest.fixture
def _logging_app():
    """Minimal FastAPI app with RequestLoggingMiddleware for testing."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

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
