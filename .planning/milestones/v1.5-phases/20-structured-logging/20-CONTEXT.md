# Phase 20: Structured Logging - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace stdlib `logging` with structlog throughout the application. Always output human-readable console logs; optionally also write JSON-formatted logs to a file when `JSON_LOG_PATH` env variable is set. Use request-scoped context via `structlog.contextvars` to correlate logs within a request. Logging must be minimal — middleware handles request lifecycle, error handlers handle exception detail, no scattered inline log calls.

</domain>

<decisions>
## Implementation Decisions

### Request ID
- Generate a fresh internal `request_id` (UUID) for every incoming HTTP request
- Do NOT read `X-Request-ID` or any client-provided header
- Do NOT return request ID to the client in headers or response body
- Request ID is internal-only for log correlation
- Bind `request_id`, `method`, `path` at request start via `structlog.contextvars.bind_contextvars()`
- Clear context at start of every request with `structlog.contextvars.clear_contextvars()`
- Bind `user_id` in the auth dependency (`get_user_id`) into the same request context

### Request boundary logging (middleware)
- Single log line per request, emitted on response (not two lines for start + finish)
- Fields: method, path, status_code, duration_ms, request_id
- Use `time.perf_counter()` for duration measurement
- All requests logged at info level (including 2xx)
- All non-2xx responses logged at ERROR level
- Traceback included for 5xx only
- Exclude `/health/ready` from request logs (Kubernetes probe noise)
- Implement as FastAPI HTTP middleware

### Error logging consolidation
- Middleware handles HTTP request access logging only
- Error handlers in `errors.py` keep their exception-specific logging (detail, traceback for severe errors)
- Remove inline logging that duplicates what middleware provides:
  - Remove `logger.warning("Authentication failure: %s", exc)` from `auth.py`
  - Remove dead `logger` import from `chats.py`
- Error handler log_level per-exception-class remains in `errors.py`

### Startup/shutdown logs
- Consolidate 5 startup info messages into one structured log line with key config as fields (model, concurrency, languages)
- One shutdown log line
- No per-config-item separate log messages

### Output format
- Always output human-readable console logs (structlog ConsoleRenderer or equivalent)
- If `JSON_LOG_PATH` env variable is set, ALSO write JSON-formatted logs to the specified file path
- This is dual output (console always + optional JSON file), NOT a prod/dev switch
- Single `log_level` from AppConfig controls verbosity for both outputs

### structlog integration
- Replace all `logging.getLogger(__name__)` with `structlog.get_logger()` throughout
- Full structlog API everywhere — not a stdlib wrapper
- Configure structlog processors in one place (setup function in main.py or dedicated module)

### Third-party noise
- Suppress httpx, httpcore, sqlalchemy.engine to WARNING level (extends current behavior)

### Claude's Discretion
- structlog processor chain configuration details
- Timestamping format
- Testing approach for logging (caplog, structlog testing utilities, or skip)
- Where the middleware module lives (new file vs existing)
- structlog.configure() specifics
- JSON file handler implementation (rotation, buffering)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Application entry point
- `app/api/main.py` — Current `setup_logging()`, lifespan startup logs, app factory
- `app/config.py` — `LogLevel` enum, `AppConfig.log_level` field

### Error handling
- `app/api/errors.py` — Error handlers with per-exception logging (service_error_handler, generic_error_handler)
- `app/exceptions.py` — Exception classes with `log_level` class attribute

### Auth (inline logging to remove)
- `app/auth.py` — `logger.warning("Authentication failure: %s", exc)` on line 47

### Dependencies (user_id binding point)
- `app/api/dependencies.py` — `get_user_id()` where `user_id` should be bound to structlog context

### Dead imports to clean up
- `app/routers/chats.py` — `import logging` and `logger = logging.getLogger(__name__)` on lines 1, 10 (never used)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LogLevel` StrEnum in `config.py` — maps Python log level names, reusable with structlog
- `AppConfig.log_level` field — existing config surface for verbosity control
- `service_error_handler` pattern — reads `exc.log_level` from exception class, logs with appropriate severity

### Established Patterns
- All FastAPI dependencies in `app/api/dependencies.py` — `user_id` binding goes here
- Session-in-init pattern on DB classes
- Exception classes carry HTTP metadata (`status_code`, `error_code`, `log_level`)
- `register_exception_handlers()` centralizes all error handling setup

### Integration Points
- `app/api/main.py:lifespan()` — structlog configuration goes here (or called from here)
- `app/api/dependencies.py:get_user_id()` — bind `user_id` to structlog contextvars after auth
- New middleware registered on the FastAPI app — likely in `main.py` near router includes
- `JSON_LOG_PATH` env variable — new config surface, either in AppConfig or read directly

</code_context>

<specifics>
## Specific Ideas

- "Always log into console, and add an additional json output if the corresponding env variable is set. The variable specifies the file where to log this additional json"
- User wants `structlog.contextvars` for request-scoped context — clear at start, bind progressively (request_id → method/path → user_id)
- User wants `time.perf_counter()` specifically for duration measurement
- Middleware pattern must keep code minimal — no scattered inline log calls in business logic

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 20-structured-logging*
*Context gathered: 2026-03-20*
