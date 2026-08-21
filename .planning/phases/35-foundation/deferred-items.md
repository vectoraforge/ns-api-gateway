# Phase 35 — Deferred Items

Out-of-scope discoveries logged during execution. Not fixed by the plan that found them.

## D-35-11-A: a grammatically **correct** phrase makes `POST /chats` return 500

**Found during:** plan 35-11, task 2 — restoring `test_chats.py::TestCreateChat::
test_create_chat_autodetect_lang`, whose original phrase (`"I am going home."`) is correct English.
**Owner:** unowned. Phase 36 rewrites these routes (REBIND-04/05) and is the natural home, but this
is a product/prompt decision rather than a rebinding one and needs an explicit call.

`config/prompt.txt` asks the model for `issues` and `suggestions` **conditionally** — "if issues
exist → provide 3 to 5 distinct suggestions", "if nearly perfect → provide 1 to 2 suggestions" —
while `models/llm.py::AnalyzeResponse` declares both as **required** fields. For a phrase with
nothing to correct the model returns `{resolved_mode, response}` and nothing else,
`AnalyzeResponse.model_validate` raises `ValidationError`, and the request answers **500**.

Reproduced four ways, so it is a defect and not LLM flake:

| Request | Result |
|---|---|
| `{"phrase": "I am going home."}` (correct, no `lang`) | **500** |
| `{"phrase": "I am going home.", "lang": "en"}` (correct) | **500** |
| `{"phrase": "I am going to home."}` (incorrect, no `lang`) | 200 |
| `{"phrase": "I am going to home.", "lang": "en"}` (incorrect) | 200 |

Correctness of the phrase is the variable; `lang` is not.

**Why plan 35-11 did not fix it.** `src/nativespeaker/api/models/llm.py` and `config/prompt.txt` are
outside the plan's file list and outside Phase 35 altogether — this is the auth foundation, and
`01-foundation.md §8.3` requires existing non-auth contracts to stay unchanged. The fix is also a
real choice rather than a typo: either `AnalyzeResponse` defaults both fields to `[]` (a correct
phrase then returns 200 with empty arrays, changing the client contract), or the prompt is changed
to always emit them. That is a product decision.

**Why it went unnoticed.** The only e2e case that sent a correct phrase was the autodetect case,
which has been absent since plan 35-04's sweep and was failing on v2.0 schema drift before that.
No unit test covers the served LLM path. Plan 35-11 restored the case against the incorrect phrase
its four neighbours use, so autodetect is covered and the defect is recorded here rather than
pinned as expected behaviour — a test asserting the 500 would make it look intended and would have
to be deleted the moment it is fixed.

**Severity note.** This is the primary route of a grammar-fixing product, and it fails for exactly
the input a user gets when their sentence is already right.

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

## D-35-06-A: the §1.2 bounded-cardinality counter has no exporter — the required alert cannot fire

**Found during:** plan 35-06, task 1 (flagged in the plan's own recorded assumptions).
**Owner:** unowned. Needs a phase or an explicit entry on the v2.0 accepted-consequences list.

`auth/telemetry.py::RejectionCounter` implements exactly what §1.2 and §8.2 require — a counter
labeled by result × bounded reason × route, incremented wherever the barrier rejects — and
`snapshot()` makes it readable. **Nothing reads it.** This deployment ships no Prometheus client,
no scrape endpoint and no exporter, and adding one is outside FOUND-01…FOUND-08.

Consequences, to be accepted rather than rediscovered:

- the operational alert §1.2 calls for cannot fire, because nothing exports the counter;
- a systemic verification break is, by §1.2's own design, client-indistinguishable from ordinary
  session expiry, so this alert is the **only** detection path — and it is currently dark;
- the counter is per-process and in-memory: each replica holds its own view, and a restart discards
  it.

Sits alongside D-08's deferred gateway contract as a known v2.0 gap. Either schedule an exporter or
record the acceptance explicitly.
