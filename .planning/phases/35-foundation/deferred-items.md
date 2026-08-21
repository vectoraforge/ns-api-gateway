# Phase 35 — Deferred Items

Out-of-scope discoveries logged during execution. Not fixed by the plan that found them.

## D-35-05-A: `uv.lock` is stale — pins `ns-api-gateway 1.5.0` against `pyproject.toml`'s 1.6.0

**Found during:** plan 35-05, the editable-install refresh the plan's recorded assumptions call for.
**Owner:** not plan 35-05 — `uv.lock` is outside its file list and nothing in this phase depends on
the pin.

Running `uv sync` (which does refresh the editable install correctly — the `auth/` subpackage is
discovered and no stale `exceptions.py` or `subscriptions.py` entry survives in
`src/ns_api_gateway.egg-info/SOURCES.txt`) rewrites two lines of `uv.lock`: the project version
`1.5.0` → `1.6.0`, and the lock-format field `revision = 2` → `3`.

The version bump is a genuine correction; the `revision` bump is a function of the locally
installed uv and could differ from the team's. Both were reverted rather than committed, since a
lockfile-format change is not something a model-repair plan should decide. Whoever next touches
dependencies should run `uv lock` deliberately and commit the result on its own.

## D-35-01-A: `tests/unit/test_logging.py` fails when the e2e suite runs in the same process

**Status: RESOLVED in plan 35-04** (commit for task 2). Fixed where it was diagnosed, in
`test_logging.py`'s own `_reset_logging` fixture — plan 35-04's task 2 acceptance criterion is
`pytest -q -m ""` exiting 0, and these two were the only thing left standing between the sweep and
that bar, so deferring them further was not available. The fixture now resets structlog defaults
*before* yielding as well as after, and additionally rebinds `logs.logger` to a fresh lazy proxy:
`reset_defaults()` resets the configuration but cannot reach into a proxy that already replaced its
own `_logger` with an instance built from the old one. Mutation-verified — suppressing the request
log line fails both tests, so they assert rather than merely observing an empty capture list.

**Found during:** plan 35-01, plan-level verification (`pytest -q -m ""`)
**Owner:** not plan 35-01 — pre-existing; resolved by plan 35-04 as a Rule 3 blocking auto-fix.

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
