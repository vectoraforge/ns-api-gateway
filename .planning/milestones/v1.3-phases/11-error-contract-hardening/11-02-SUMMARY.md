---
phase: 11-error-contract-hardening
plan: "02"
subsystem: api
tags: [openapi, error-contract, fastapi, testing, schema]

dependency_graph:
  requires:
    - phase: 11-01
      provides: ErrorResponse model and _STATUS_REMAP dict in app/errors.py
  provides:
    - custom_openapi() strips 422 from all routes in the OpenAPI schema
    - app-level responses= param registers all 5 contract codes in the schema
    - ErrorResponse visible in /docs schema components
    - 8 contract enforcement tests verifying schema shape and edge-case routing
  affects: [app/main.py, tests/unit/test_error_contract.py]

tech-stack:
  added: []
  patterns:
    - "custom_openapi pattern: override app.openapi to post-process schema dict"
    - "app-level responses= param propagates error shapes to all route schemas"
    - "Isolated contract_client fixture: minimal FastAPI app with only error handlers for edge-case routing tests"

key-files:
  created:
    - tests/unit/test_error_contract.py
  modified:
    - app/main.py

key-decisions:
  - "custom_openapi() strips 422 via schema post-processing (not per-route override) — one place to maintain"
  - "app-level responses= param used (not per-router) so all routes inherit the 5 contract codes automatically"
  - "contract_client fixture uses a minimal app with no lifespan/DB — isolates handler infrastructure from startup concerns"
  - "OpenAPI tests use real_app import directly — tests the actual schema, not a copy"

patterns-established:
  - "Schema post-processing: iterate paths.values() -> methods.values() -> responses.pop() for 422 removal"
  - "Module-scope test client fixtures for contract/integration tests avoid per-test startup overhead"

requirements-completed: [ERR-04]

duration: 1min
completed: "2026-03-02"
---

# Phase 11 Plan 02: OpenAPI Schema Hardening Summary

**custom_openapi() strips 422 from all routes and registers ErrorResponse across all 5 contract codes in OpenAPI, verified by 8 new contract enforcement tests.**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-02T19:49:02Z
- **Completed:** 2026-03-02T19:50:28Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `custom_openapi()` to `app/main.py` that post-processes the generated schema to strip all `422` response entries
- Added `responses=` param to the `FastAPI()` constructor with all 5 contract status codes (400/401/404/500/503) referencing `ErrorResponse`
- Created `tests/unit/test_error_contract.py` with 8 tests covering wrong-method remapping (405→400), undefined route (404), exact body shape, and OpenAPI schema assertions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add custom_openapi() and app-level error responses** - `2ac9deb` (feat)
2. **Task 2: Add error contract enforcement tests** - `846bfbd` (feat)

## Files Created/Modified

- `app/main.py` - Added `from fastapi.openapi.utils import get_openapi`, `from app.schema import ErrorResponse`, `responses=` kwarg on FastAPI constructor, `custom_openapi()` function, and `app.openapi = custom_openapi` assignment
- `tests/unit/test_error_contract.py` - 8 tests in two classes: `TestStatusCodeRemapping` (wrong method, undefined route, body shape, code set) and `TestOpenAPISchema` (no 422, ErrorResponse present, code field, code enum)

## Decisions Made

1. **Schema post-processing via custom_openapi():** Iterates `schema["paths"]` values after generation to `.pop("422", None)` from every operation's responses dict — one location to maintain, no per-route changes needed.

2. **app-level `responses=` param:** Registering the 5 error codes at the `FastAPI()` constructor level means every route in the app inherits them automatically, without modifying individual routers.

3. **Minimal `contract_client` fixture:** Uses a plain `FastAPI()` app with only `register_exception_handlers(app)` and a single GET route — no lifespan, no DB, no JWT setup. Isolates the handler infrastructure from startup concerns cleanly.

4. **Direct `real_app.openapi()` in schema tests:** The OpenAPI tests import `app` from `app.main` and call `.openapi()` directly, ensuring they test the actual schema as served at `/openapi.json`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Error contract is fully visible in the OpenAPI docs at `/docs`
- No 422 responses appear anywhere in the schema
- Both `test_error_contract.py` (8 tests) and `test_exception_handlers.py` (23 tests) pass — 81 unit tests total pass
- Phase 11 complete, ready for Phase 12 (LLM DI)

---
*Phase: 11-error-contract-hardening*
*Completed: 2026-03-02*

## Self-Check: PASSED

- [x] app/main.py modified (custom_openapi, app-level responses=, imports)
- [x] tests/unit/test_error_contract.py created (8 tests, all pass)
- [x] Commit 2ac9deb exists (Task 1)
- [x] Commit 846bfbd exists (Task 2)
- [x] 81 unit tests pass total
