---
phase: 20-structured-logging
plan: 01
subsystem: logging
tags: [structlog, middleware, contextvars, json-logging]

# Dependency graph
requires:
  - phase: 19-service-layer-refactoring
    provides: services/ and database/ package structure
provides:
  - Centralized structured logging via structlog with ProcessorFormatter pipeline
  - Request logging middleware with correlation ID and duration tracking
  - Dual output support (console always + optional JSON file)
  - user_id binding in auth dependency for request-scoped logs
affects: [api, middleware, observability]

# Tech tracking
tech-stack:
  added: [structlog 25.5.0]
  patterns: [ProcessorFormatter dual-output, contextvars request correlation, single request log line]

key-files:
  created: [app/logging.py, tests/unit/test_logging.py]
  modified: [app/config.py, app/api/main.py, app/api/errors.py, app/auth.py, app/api/dependencies.py, app/routers/chats.py, pyproject.toml]

key-decisions:
  - "structlog.testing.capture_logs() does not merge contextvars; contextvars binding tested separately from log output content"
  - "Dynamic log level dispatch in errors.py via _LEVEL_TO_METHOD dict + getattr instead of FilteringBoundLogger.log()"
  - "Removed auth.py inline logging entirely; AuthenticationError.log_level=WARNING handles it via error handler"

patterns-established:
  - "Centralized logging in app/logging.py: setup_logging() + RequestLoggingMiddleware"
  - "structlog.get_logger() for all module-level loggers (no stdlib getLogger)"
  - "contextvars for request correlation: request_id, method, path bound in middleware; user_id bound in auth dependency"
  - "Single structured log line per request on response (not start+finish)"

requirements-completed: [LOG-01, LOG-02, LOG-03, LOG-04]

# Metrics
duration: 8min
completed: 2026-03-20
---

# Phase 20 Plan 01: Structured Logging Summary

**structlog with ProcessorFormatter pipeline providing dual-output (console + optional JSON file), request correlation via contextvars, and single-line request logging middleware**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-20T07:25:42Z
- **Completed:** 2026-03-20T07:33:53Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- Centralized logging module (app/logging.py) with setup_logging() and RequestLoggingMiddleware
- Replaced all stdlib logging.getLogger(__name__) with structlog.get_logger() across 4 files
- 7 unit tests covering LOG-01 through LOG-04 (91 total tests passing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create logging module and update config** - `7353a7a` (feat)
2. **Task 2: Wire structlog into all application files** - `a11dd01` (refactor)
3. **Task 3: Add unit tests for structured logging** - `4575f76` (test)

## Files Created/Modified
- `app/logging.py` - Centralized logging: setup_logging() configures structlog + stdlib pipeline; RequestLoggingMiddleware logs one line per request
- `app/config.py` - Added json_log_path field to AppConfig
- `app/api/main.py` - Replaced stdlib logging with structlog, consolidated 5 startup lines to 1, registered middleware
- `app/api/errors.py` - Replaced stdlib logger with structlog, added _LEVEL_TO_METHOD for dynamic log level dispatch
- `app/auth.py` - Removed inline logging (error handler handles AuthenticationError logging)
- `app/api/dependencies.py` - Binds user_id to structlog contextvars after JWT verification
- `app/routers/chats.py` - Removed dead logging import and logger declaration
- `pyproject.toml` - Added structlog>=25.5 dependency
- `tests/unit/test_logging.py` - 7 unit tests for structured logging requirements

## Decisions Made
- Used _LEVEL_TO_METHOD dict for dynamic log level dispatch in errors.py because FilteringBoundLogger lacks .log() method
- Removed auth.py inline logger.warning() entirely since AuthenticationError has log_level=WARNING which the error handler respects
- capture_logs() does not merge contextvars in structlog 25.5.0; tested contextvars binding directly via get_contextvars() instead

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Structured logging foundation complete
- JSON_LOG_PATH env var can be set in production to enable file-based JSON logs
- All request-scoped logs include request_id for correlation

---
*Phase: 20-structured-logging*
*Completed: 2026-03-20*
