# Phase 20: Structured Logging - Research

**Researched:** 2026-03-20
**Domain:** structlog integration with FastAPI, structured logging patterns
**Confidence:** HIGH

## Summary

This phase replaces stdlib `logging` with `structlog` throughout the application. The codebase currently uses stdlib logging in 5 files (`main.py`, `errors.py`, `auth.py`, `config.py`, `chats.py`), plus the `exceptions.py` module references `logging.ERROR` and `logging.WARNING` as numeric class attributes on exception classes.

The recommended architecture uses structlog's **stdlib integration via `ProcessorFormatter`** (option 4 in structlog docs). This is the only approach that supports dual output (console always + optional JSON file) while also capturing third-party stdlib log entries (uvicorn, httpx, sqlalchemy) through the same formatting pipeline. Structlog uses the same numeric log level constants as stdlib (`logging.INFO = 20`, `logging.WARNING = 30`), so the existing `log_level` class attributes on exception classes work without modification.

**Primary recommendation:** Use `structlog.stdlib.ProcessorFormatter` with stdlib `logging` handlers. Configure one `StreamHandler` for console (always) and one optional `FileHandler` for JSON (when `JSON_LOG_PATH` env var is set). Shared processor chain runs before the renderer fork.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Generate a fresh internal `request_id` (UUID) for every incoming HTTP request -- do NOT read client headers, do NOT return to client
- Bind `request_id`, `method`, `path` at request start via `structlog.contextvars.bind_contextvars()`; clear with `clear_contextvars()` at start of every request
- Bind `user_id` in the auth dependency (`get_user_id`) into the same request context
- Single log line per request emitted on response (not two lines for start + finish)
- Fields: method, path, status_code, duration_ms, request_id
- Use `time.perf_counter()` for duration measurement
- All requests logged at info level (including 2xx); all non-2xx at ERROR level
- Traceback included for 5xx only
- Exclude `/health/ready` from request logs
- Implement as FastAPI HTTP middleware
- Middleware handles HTTP request access logging only; error handlers in `errors.py` keep their exception-specific logging
- Remove `logger.warning("Authentication failure: %s", exc)` from `auth.py`
- Remove dead `logger` import from `chats.py`
- Consolidate 5 startup info messages into one structured log line with key config as fields
- One shutdown log line
- Always output human-readable console logs; if `JSON_LOG_PATH` env var is set, also write JSON logs to that file path
- Single `log_level` from AppConfig controls verbosity for both outputs
- Replace all `logging.getLogger(__name__)` with `structlog.get_logger()` throughout
- Full structlog API everywhere -- not a stdlib wrapper
- Suppress httpx, httpcore, sqlalchemy.engine to WARNING level

### Claude's Discretion
- structlog processor chain configuration details
- Timestamping format
- Testing approach for logging (caplog, structlog testing utilities, or skip)
- Where the middleware module lives (new file vs existing)
- structlog.configure() specifics
- JSON file handler implementation (rotation, buffering)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LOG-01 | Structured logging via structlog with JSON output in production | structlog 25.5.0 with ProcessorFormatter; JSON output via `JSONRenderer` on a `FileHandler` when `JSON_LOG_PATH` is set |
| LOG-02 | Console-formatted logs in development mode | `ConsoleRenderer` on a `StreamHandler` (always active, not just dev) -- per user decision, console is always-on |
| LOG-03 | Request ID context injected into all log entries via middleware | `structlog.contextvars.bind_contextvars(request_id=...)` with `merge_contextvars` as first shared processor |
| LOG-04 | Info level for request lifecycle, debug for implementation details | `make_filtering_bound_logger(logging.INFO)` default; middleware logs at INFO/ERROR per status code |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| structlog | 25.5.0 | Structured logging framework | De facto Python structured logging; zero dependencies, production-stable, native contextvars support |

### Supporting
No additional libraries needed. structlog ships with all required processors (`JSONRenderer`, `ConsoleRenderer`, `TimeStamper`, contextvars support). stdlib `logging` provides handler infrastructure (StreamHandler, FileHandler).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| structlog | python-json-logger | Wrapper around stdlib only; no contextvars, no processor chain, no ConsoleRenderer |
| structlog | loguru | Opinionated; harder to integrate with stdlib for third-party log capture |

**Installation:**
```bash
uv add "structlog>=25.5"
```

**Version verification:** structlog 25.5.0 released 2025-10-27 (confirmed via PyPI). Requires Python >=3.8, supports 3.14.

## Architecture Patterns

### Recommended Project Structure
```
app/
├── api/
│   ├── main.py              # lifespan calls setup_logging(); registers middleware
│   ├── errors.py            # Error handlers use structlog.get_logger()
│   └── dependencies.py      # get_user_id() binds user_id to contextvars
├── logging.py                # NEW: setup_logging(), configure_structlog(), middleware class
├── auth.py                   # Remove logger.warning() call
├── config.py                 # Add JSON_LOG_PATH field; LogLevel stays as-is
├── routers/
│   └── chats.py              # Remove dead logging import
└── exceptions.py             # No changes (logging.ERROR/WARNING constants still valid)
```

### Pattern 1: Centralized Logging Module (`app/logging.py`)

**What:** Single module containing structlog configuration, stdlib handler setup, and the request logging middleware class.
**When to use:** Always -- keeps logging concerns in one file, out of `main.py`.

```python
import logging
import sys
import time
import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from config import AppConfig


def setup_logging(log_level: str,
                  json_log_path: str | None = None) -> None:
    """Configure structlog + stdlib logging pipeline."""

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    # Console handler (always active)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(),
            ],
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))

    # Optional JSON file handler
    if json_log_path:
        file_handler = logging.FileHandler(json_log_path)
        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared_processors,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info,
                    structlog.processors.JSONRenderer(),
                ],
            )
        )
        root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
```

### Pattern 2: Request Logging Middleware

**What:** FastAPI HTTP middleware that logs one line per request on response.
**When to use:** Registered in `main.py` on the app.

```python
_EXCLUDED_PATHS = frozenset({"/health/ready"})

logger = structlog.get_logger()


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
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        if request.url.path not in _EXCLUDED_PATHS:
            log_method = logger.info if response.status_code < 400 else logger.error
            log_method("request",
                       status_code=response.status_code,
                       duration_ms=duration_ms)

        return response
```

### Pattern 3: user_id Binding in Auth Dependency

**What:** After JWT verification in `get_user_id()`, bind `user_id` into structlog contextvars.
**When to use:** In `app/api/dependencies.py`.

```python
import structlog

def get_user_id(request: Request, authorization: str | None = Header(None)) -> str:
    # ... existing auth logic ...
    user_id = verifier.verify(token)
    structlog.contextvars.bind_contextvars(user_id=user_id)
    return user_id
```

### Pattern 4: Consolidated Startup/Shutdown Logs

**What:** Replace 5 separate `logger.info()` calls with one structured log entry.
**When to use:** In `app/api/main.py` lifespan.

```python
logger = structlog.get_logger()

# Inside lifespan, after all setup:
logger.info("started",
            model=config.model.name,
            concurrency=config.resilience.pool_size,
            languages=list(config.examples.keys()))

# On shutdown:
logger.info("shutdown")
```

### Pattern 5: Error Handler Logging Migration

**What:** Replace `logging.getLogger(__name__)` with `structlog.get_logger()` in `errors.py`.
**When to use:** The error handlers already use `logger.log(exc.log_level, ...)` with numeric levels. With structlog, this must change slightly.

```python
import structlog

logger = structlog.get_logger()

async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        # structlog's FilteringBoundLogger provides .log() method
        logger.log(exc.log_level, str(exc),
                   error_type=type(exc).__name__,
                   exc_info=(exc.log_level >= logging.ERROR))
    return JSONResponse(...)
```

**Note:** `structlog.FilteringBoundLogger` does not have a `.log(level, msg)` method like stdlib. The structlog bound logger has `.info()`, `.error()`, `.warning()`, etc. For the dynamic log level pattern in `service_error_handler`, use `structlog.get_logger().log(level, event)` -- this works with `structlog.stdlib.BoundLogger` wrapper class. Alternatively, map the numeric level to the method name and call it dynamically. The simplest approach: since `make_filtering_bound_logger` creates methods for each level, use `getattr(logger, level_name)(...)` where `level_name` is derived from `logging.getLevelName(exc.log_level).lower()`.

### Anti-Patterns to Avoid
- **Inline log calls in business logic:** The user explicitly wants minimal logging. No `logger.debug()` scattered through service methods. Middleware and error handlers handle it.
- **Two log lines per request (start + finish):** User decision is one line on response only.
- **Wrapping structlog around stdlib:** Use full structlog API (`structlog.get_logger()`, not `logging.getLogger()` with structlog formatting).
- **Separate dev/prod format switch:** User wants console always + optional JSON file, not an either/or toggle.
- **Using `structlog.PrintLoggerFactory`:** Does not integrate with stdlib handlers. Must use `structlog.stdlib.LoggerFactory()` for dual-output via stdlib handlers.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request context propagation | Thread-local or manual passing | `structlog.contextvars` | Async-safe, automatic propagation through call chain |
| JSON log formatting | Custom JSON serializer | `structlog.processors.JSONRenderer()` | Handles all edge cases (datetime, UUID, bytes) |
| Console coloring | ANSI escape codes | `structlog.dev.ConsoleRenderer()` | Level-based colors, key-value alignment, exception formatting |
| Third-party log capture | Custom logging filter | `ProcessorFormatter` with `foreign_pre_chain` | Unifies all stdlib loggers (uvicorn, httpx, sqlalchemy) through same pipeline |
| Log level filtering | Custom if/else | `make_filtering_bound_logger()` | Zero-overhead no-op for filtered levels (method becomes `return None`) |

**Key insight:** structlog's `ProcessorFormatter` is the critical piece -- it processes both structlog-originated and stdlib-originated log entries through the same pipeline, ensuring consistent output format regardless of source.

## Common Pitfalls

### Pitfall 1: contextvars Isolation in Starlette/FastAPI
**What goes wrong:** Context variables set in synchronous code don't appear in async logs and vice versa in hybrid Starlette apps.
**Why it happens:** Python's `contextvars` storage mechanics differ between sync and async contexts.
**How to avoid:** The middleware runs in async context, which is where all FastAPI route handlers also run. Since this app is fully async (async def routes, asynccontextmanager lifespan), this is not an issue. Just ensure `clear_contextvars()` is called at the start of every request in the middleware.
**Warning signs:** Missing `request_id` in log entries from certain code paths.

### Pitfall 2: cache_logger_on_first_use Breaks Testing
**What goes wrong:** `capture_logs()` context manager has no effect when `cache_logger_on_first_use=True` because cached loggers bypass the new test configuration.
**Why it happens:** structlog caches the fully-configured logger on first `.info()/.error()` call. Test reconfiguration doesn't invalidate the cache.
**How to avoid:** Call `structlog.reset_defaults()` in test fixtures before reconfiguring, or use a fixture that calls `structlog.configure(cache_logger_on_first_use=False)` for test runs.
**Warning signs:** `capture_logs()` returns empty list despite log calls executing.

### Pitfall 3: ProcessorFormatter Without foreign_pre_chain
**What goes wrong:** Third-party stdlib log entries (uvicorn, httpx) come through as raw unformatted strings, missing timestamps and log levels.
**Why it happens:** `ProcessorFormatter` only applies its `processors` chain to structlog entries by default. Stdlib entries need `foreign_pre_chain` to run the same shared processors.
**How to avoid:** Always set `foreign_pre_chain=shared_processors` on every `ProcessorFormatter` instance.
**Warning signs:** Inconsistent format between your app logs and third-party library logs.

### Pitfall 4: format_exc_info Placement
**What goes wrong:** Exception tracebacks appear in console output as raw text or are missing from JSON output.
**Why it happens:** `format_exc_info` converts `exc_info` to a string. If placed in the shared processor chain, ConsoleRenderer can't format it nicely. If omitted from the JSON chain, tracebacks are lost.
**How to avoid:** Put `format_exc_info` in the JSON renderer's processor chain only (after `remove_processors_meta`), not in the shared chain. `ConsoleRenderer` handles `exc_info` natively.
**Warning signs:** Double-rendered tracebacks or missing tracebacks.

### Pitfall 5: LogLevel StrEnum and structlog Interaction
**What goes wrong:** `AppConfig.log_level` is a `LogLevel` StrEnum with string values like `"INFO"`. `make_filtering_bound_logger()` accepts int or string.
**Why it happens:** The StrEnum stores the string name, but `logging.basicConfig(level=...)` was using `getattr(logging, log_level)` to convert to int.
**How to avoid:** Continue using `getattr(logging, config.log_level, logging.INFO)` to get the numeric level for `make_filtering_bound_logger()`. Or pass the string directly since `make_filtering_bound_logger` accepts case-insensitive strings.
**Warning signs:** All log levels appear or none appear.

### Pitfall 6: Dynamic log() on FilteringBoundLogger
**What goes wrong:** `logger.log(exc.log_level, msg)` fails because `FilteringBoundLogger` doesn't have a `.log()` method.
**Why it happens:** `make_filtering_bound_logger()` creates a class with explicit `.info()`, `.error()`, `.warning()` methods, not a generic `.log(level, msg)`.
**How to avoid:** Map numeric level to method name: `getattr(logger, logging.getLevelName(level).lower())(msg)`. Or use `structlog.stdlib.BoundLogger` as wrapper class instead (has `.log()` method).
**Warning signs:** `AttributeError: 'FilteringBoundLogger' has no attribute 'log'`.

## Code Examples

### Complete setup_logging Configuration

```python
# Source: structlog 25.5.0 official docs (ProcessorFormatter pattern)
import logging
import sys

import structlog


def setup_logging(log_level: str,
                  json_log_path: str | None = None) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
        ],
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))

    if json_log_path:
        json_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
        )
        file_handler = logging.FileHandler(json_log_path)
        file_handler.setFormatter(json_formatter)
        root.addHandler(file_handler)

    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
```

### structlog Testing with capture_logs

```python
# Source: structlog 25.5.0 testing docs
import structlog
from structlog.testing import capture_logs


def test_request_logging():
    with capture_logs() as cap_logs:
        logger = structlog.get_logger()
        logger.info("request", status_code=200, duration_ms=42.5)

    assert len(cap_logs) == 1
    assert cap_logs[0]["event"] == "request"
    assert cap_logs[0]["status_code"] == 200
    assert cap_logs[0]["log_level"] == "info"
```

### Dynamic Log Level for Error Handlers

```python
import logging

import structlog


logger = structlog.get_logger()

_LEVEL_TO_METHOD = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "critical",
}


async def service_error_handler(_request, exc):
    if exc.log_level is not None:
        method_name = _LEVEL_TO_METHOD.get(exc.log_level, "error")
        log_method = getattr(logger, method_name)
        log_method(str(exc),
                   error_type=type(exc).__name__,
                   exc_info=(exc.log_level >= logging.ERROR))
    # ... return JSONResponse
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `structlog.PrintLoggerFactory()` | `structlog.stdlib.LoggerFactory()` with `ProcessorFormatter` | Stable since structlog 21.x | Unified pipeline for structlog + stdlib sources |
| `structlog.stdlib.AsyncBoundLogger` | `structlog.make_filtering_bound_logger()` + `.ainfo()` async methods | 23.1.0 (2023) | `AsyncBoundLogger` deprecated; use async `a`-prefixed methods on `FilteringBoundLogger` |
| Manual processor chains per output | `ProcessorFormatter` with `foreign_pre_chain` | Stable since 21.x | Single shared chain, per-handler renderers |

**Deprecated/outdated:**
- `structlog.stdlib.AsyncBoundLogger`: Deprecated since 23.1.0. Use `FilteringBoundLogger` with async `a*` methods instead.
- `structlog.stdlib.recreate_defaults()`: Quick-start helper, but insufficient for dual-output or custom setups.

## Open Questions

1. **JSON file rotation**
   - What we know: `logging.FileHandler` writes to a single file. `logging.handlers.RotatingFileHandler` adds size-based rotation.
   - What's unclear: Whether the user wants rotation or expects external log rotation (logrotate, container runtime).
   - Recommendation: Use plain `FileHandler` -- this is a container-deployed app where JSON logs are likely collected by a sidecar or runtime. If rotation is needed later, swap to `RotatingFileHandler` (one-line change).

2. **JSON_LOG_PATH config surface**
   - What we know: User said "env variable". Current config uses `pydantic-settings` with `BaseSettings`.
   - What's unclear: Whether to add it to `AppConfig` or read it directly with `os.environ.get()`.
   - Recommendation: Add `json_log_path: str | None = None` to `AppConfig` for consistency with existing config pattern. The `SettingsConfigDict(env_nested_delimiter="_")` means it would be set as `JSON_LOG_PATH` env var.

3. **Middleware class location**
   - What we know: User left this to Claude's discretion.
   - Recommendation: New `app/logging.py` module containing `setup_logging()` and `RequestLoggingMiddleware`. Keeps all logging concerns together, keeps `main.py` clean.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0 with pytest-asyncio >= 1.3 |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/unit/ -x` |
| Full suite command | `python -m pytest tests/unit/ -x && python -m pytest tests/e2e/ -m e2e -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOG-01 | JSON output when JSON_LOG_PATH set | unit | `python -m pytest tests/unit/test_logging.py::test_json_output -x` | No -- Wave 0 |
| LOG-02 | Console output always active | unit | `python -m pytest tests/unit/test_logging.py::test_console_output -x` | No -- Wave 0 |
| LOG-03 | Request ID in all log entries | unit | `python -m pytest tests/unit/test_logging.py::test_request_id_context -x` | No -- Wave 0 |
| LOG-04 | Info for lifecycle, debug for details | unit | `python -m pytest tests/unit/test_logging.py::test_log_levels -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x`
- **Per wave merge:** `python -m pytest tests/unit/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_logging.py` -- covers LOG-01 through LOG-04 using `structlog.testing.capture_logs()`
- [ ] Framework install: `uv add "structlog>=25.5"` -- structlog not yet in dependencies

## Sources

### Primary (HIGH confidence)
- [structlog 25.5.0 PyPI](https://pypi.org/project/structlog/) -- version, release date, Python support
- [structlog Getting Started](https://www.structlog.org/en/stable/getting-started.html) -- default config, processor chain basics
- [structlog Context Variables](https://www.structlog.org/en/stable/contextvars.html) -- bind/clear/merge_contextvars API, Flask example
- [structlog Configuration](https://www.structlog.org/en/stable/configuration.html) -- configure(), wrapper_class, logger_factory
- [structlog Standard Library Integration](https://www.structlog.org/en/stable/standard-library.html) -- ProcessorFormatter, foreign_pre_chain, four integration approaches
- [structlog Testing](https://www.structlog.org/en/stable/testing.html) -- capture_logs(), LogCapture, CapturingLogger
- [structlog API Reference](https://www.structlog.org/en/stable/api.html) -- JSONRenderer, ConsoleRenderer, TimeStamper, make_filtering_bound_logger, WriteLoggerFactory
- [structlog Bound Loggers](https://www.structlog.org/en/stable/bound-loggers.html) -- FilteringBoundLogger, log level constants same as stdlib

### Secondary (MEDIUM confidence)
- [FastAPI + structlog Gist by nymous](https://gist.github.com/nymous/f138c7f06062b7c43c060bf03759c29e) -- Complete production setup with ProcessorFormatter, middleware, Uvicorn integration
- [FastAPI structlog integration blog](https://ouassim.tech/notes/setting-up-structured-logging-in-fastapi-with-structlog/) -- Middleware pattern, ProcessorFormatter setup

### Tertiary (LOW confidence)
None -- all findings verified against official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- structlog 25.5.0 confirmed via PyPI, single library, no alternatives needed
- Architecture: HIGH -- ProcessorFormatter pattern verified in official docs; FastAPI middleware pattern verified in multiple sources
- Pitfalls: HIGH -- contextvars isolation documented officially; cache_logger_on_first_use testing issue documented in structlog testing docs; FilteringBoundLogger .log() limitation verified in API docs

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (structlog is stable, slow-moving library)
