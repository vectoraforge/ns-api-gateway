import ast
import io
import logging
import re
import uuid
from pathlib import Path

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

import nativespeaker.api.logs as logs_module
from nativespeaker.api.config import LogLevel
from nativespeaker.api.logs import _QUIETED_LIBRARIES, RequestLoggingMiddleware, setup_logging

_SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture(autouse=True)
def _reset_logging():
    """Save and restore logger state around each test; the reset runs before as well as after."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    # `setup_logging` writes the root's level and the level of every quieted library. Snapshot
    # both, or the nine library levels a test sets stay pinned for the rest of the session.
    original_levels = {name: logging.getLogger(name).level for name in _QUIETED_LIBRARIES}
    _uncache_module_logger()
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()
    _uncache_module_logger()
    for name, level in original_levels.items():
        logging.getLogger(name).setLevel(level)
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


def test_the_middleware_binds_the_correlation_fields_onto_every_record(_logging_app):
    """WR-70: `capture_logs` does not merge contextvars, so the bindings are read where they are
    set. The case this replaces bound a contextvar itself and read it back, which stayed green
    with the whole `bind_contextvars` call deleted from the middleware."""
    seen: list[dict] = []

    @_logging_app.get("/bound")
    async def _bound():
        seen.append(dict(structlog.contextvars.get_contextvars()))
        return {"ok": True}

    with TestClient(_logging_app) as client:
        client.get("/bound")
        client.get("/bound")

    assert [sorted(ctx) for ctx in seen] == [["method", "path", "request_id"]] * 2
    assert [ctx["method"] for ctx in seen] == ["GET", "GET"]
    assert [ctx["path"] for ctx in seen] == ["/bound", "/bound"]
    # A fresh id per request, or correlation groups two requests into one.
    assert uuid.UUID(seen[0]["request_id"]) != uuid.UUID(seen[1]["request_id"])


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


class TestEveryEventNameIsGreppable:
    """WR-26. D-02 made the event name the outcome vocabulary, so a name that does not match the
    shape an alert or dashboard filters on is a record those consumers drop without saying so."""

    _LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})
    _NAME = re.compile(r"^[a-z][a-z0-9_]*$")

    def _literal_event_names(self):
        """Every literal first argument to a `logger.<level>(...)` call under `src`."""
        for path in sorted((_SRC).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in self._LEVELS or not node.args:
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    yield str(path.relative_to(_SRC)), first.value

    def test_no_event_name_departs_from_snake_case(self):
        offenders = [(where, name) for where, name in self._literal_event_names()
                     if not self._NAME.match(name)]
        assert offenders == [], f"event names an `^[a-z_]+$` filter drops: {offenders}"

    def test_the_walk_reaches_the_handler_that_was_wrong(self):
        """The control: a walk that found nothing would pass the assertion above unconditionally."""
        found = {name for _where, name in self._literal_event_names()}
        assert "unhandled_exception" in found
        assert len(found) > 20


def test_third_party_loggers_suppressed():
    setup_logging(log_level="INFO")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING


class TestRaisingTheLevelNeverOpensAContentChannel:
    """WR-03. `openai` logs the whole chat-completion body at DEBUG -- the system prompt, the user's
    phrase and the chat's history -- and `DEBUG` is a level an operator may configure."""

    @pytest.mark.parametrize("name", _QUIETED_LIBRARIES)
    def test_a_quieted_library_stays_quiet_at_debug(self, name):
        setup_logging(log_level="DEBUG")

        assert logging.getLogger(name).getEffectiveLevel() >= logging.INFO

    def test_openai_is_one_of_them(self):
        """Named rather than only enumerated: the list is what an edit can silently shorten."""
        assert "openai" in _QUIETED_LIBRARIES

    def test_the_applications_own_logger_still_follows_the_configured_level(self):
        """The control: pinning every logger would pass the cases above and log nothing at all."""
        setup_logging(log_level="DEBUG")

        assert logging.getLogger("nativespeaker.api").getEffectiveLevel() == logging.DEBUG


class TestQuietingALibraryNeverRaisesItAboveTheApplication:
    """WR-20. A level set on a child outranks the root in both directions, so the flat WARNING pin
    inverted the signal at LOG_LEVEL=ERROR: an operator cutting noise during an incident lost the
    application's own WARNING vocabulary and kept the nine libraries' chatter."""

    @pytest.mark.parametrize("name", _QUIETED_LIBRARIES)
    def test_a_quieted_library_never_outranks_the_configured_level(self, name):
        setup_logging(log_level="ERROR")

        assert logging.getLogger(name).getEffectiveLevel() >= logging.ERROR

    def test_the_pin_is_still_a_ceiling_below_warning(self):
        """The control: a pin that simply followed the root would open `openai`'s body at DEBUG."""
        setup_logging(log_level="DEBUG")

        assert logging.getLogger("openai").getEffectiveLevel() >= logging.WARNING


class TestOnlyOneAccessLineIsWrittenPerRequest:
    """WR-03. Uvicorn gives `uvicorn.access` its own handler and `propagate=False`, so clearing the
    root handlers left a second, unstructured line per request that ignored `_EXCLUDED_PATHS`."""

    def test_uvicorn_writes_no_access_line_at_the_configured_level(self):
        setup_logging(log_level="INFO")

        assert not logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO)

    def test_it_stays_silent_when_an_operator_raises_the_level_to_debug(self):
        setup_logging(log_level="DEBUG")

        assert not logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO)

    def test_uvicorn_access_is_named_in_the_quieted_list(self):
        """Named rather than only enumerated: the list is what an edit can silently shorten."""
        assert "uvicorn.access" in _QUIETED_LIBRARIES

    def test_uvicorn_error_still_reports_a_failed_start_control(self):
        """The control: silencing all of uvicorn would pass the cases above and hide a dead boot."""
        setup_logging(log_level="INFO")

        assert logging.getLogger("uvicorn.error").isEnabledFor(logging.INFO)


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


def test_no_quieted_library_level_outlives_the_test_that_set_it():
    """Reads what every case above left behind: `setup_logging` pins nine named loggers to
    WARNING, and only `_reset_logging` puts them back. A level still pinned here escaped this
    file and would silence those nine for every later test in the session."""
    pinned = {name: logging.getLogger(name).level for name in _QUIETED_LIBRARIES
              if logging.getLogger(name).level != logging.NOTSET}

    assert pinned == {}
