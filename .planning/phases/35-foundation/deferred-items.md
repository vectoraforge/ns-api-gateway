# Phase 35 — Deferred Items

Out-of-scope discoveries logged during execution. Not fixed by the plan that found them.

## D-35-01-A: `tests/unit/test_logging.py` fails when the e2e suite runs in the same process

**Found during:** plan 35-01, plan-level verification (`pytest -q -m ""`)
**Owner:** not plan 35-01 — pre-existing; likely resolved alongside plan 35-05's e2e repair, or by
its own conftest fix.

`test_middleware_logs_request_on_response` and `test_middleware_error_level_for_non_2xx` pass in the
unit-only run and fail in a combined `-m ""` run. `structlog.testing.capture_logs()` returns `[]`
even though the `"request"` line is demonstrably emitted (it appears in captured stderr).

**Cause:** an e2e module's `_app_lifespan` fixture calls `setup_logging()`, which reconfigures
structlog with `cache_logger_on_first_use=True`. `logs.py`'s module-level `logger` proxy then binds
to a concrete bound logger that `capture_logs` cannot intercept. `test_logging.py`'s autouse
`_reset_logging` fixture restores state *after* each test, not before, so it never undoes the
lifespan's reconfiguration.

**Proof it predates plan 35-01:** reproduced with plan 35-01's new e2e module excluded
(`pytest -q -m "" tests/e2e tests/unit/test_logging.py --ignore=tests/e2e/test_startup_assertion.py`)
— the same two failures appear. Also reproduces with `tests/e2e/test_error_cases.py` alone, whose
logging behaviour plan 35-01 did not touch.

**Suggested fix:** have `test_logging.py`'s `_reset_logging` fixture call `structlog.reset_defaults()`
*before* yielding as well as after, or set `cache_logger_on_first_use=False` under test.
