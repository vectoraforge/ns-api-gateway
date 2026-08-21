---
phase: 35-foundation
plan: 01
subsystem: auth
tags: [fastapi, starlette, asgi-middleware, jwt, route-registry, error-registry, pydantic]

requires:
  - phase: 34-schema
    provides: "the applied v2.0 schema — core.auth_operation and core.auth_event_result, mirrored verbatim into models/auth.py"
provides:
  - "errors.py — the one client-visible error registry at package root (D-10) with the seven §3.2 foundation classes, an append-only register_class, and the error_response factory"
  - "auth/wire.py — the §1.1 single-Authorization wire contract over the raw ASGI header list"
  - "auth/registry.py — the §2.2 declarative route metadata table (all ten routes declared) and the §2.3 nine-condition startup enumeration assertion"
  - "auth/barrier.py — the §1.5 pure-ASGI pre-handler barrier that returns registry responses instead of raising (D-01)"
  - "models/auth.py — AuthOperation and AuthEventResult StrEnums"
  - "The auth/ subpackage itself, with auth.py absorbed as auth/verification.py (D-23 groundwork)"
  - "app/main.py wiring: docs routes off, redirect_slashes off, barrier installed beneath the logging middleware"
  - "app/lifespan.py wiring: assert_route_enumeration(app) runs at real startup and fails closed"
affects: [35-02, 35-03, 35-04, 35-05, 35-06, 35-07, 35-08, 35-09, 35-10, 35-11, 36-rebinding]

actuals:
  tokens: 13011
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Pure-ASGI middleware that returns a Response awaited against (scope, receive, send) rather than raising"
    - "Router-interrogating route resolution: iterate scope['app'].router.routes and take the first Match.FULL"
    - "Declarative module-level metadata table validated by a fail-closed lifespan assertion"
    - "Append-only error class registry keyed by name, with duplicate name and duplicate code both rejected"

key-files:
  created:
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/models/auth.py
    - src/nativespeaker/api/auth/__init__.py
    - src/nativespeaker/api/auth/wire.py
    - src/nativespeaker/api/auth/registry.py
    - src/nativespeaker/api/auth/barrier.py
    - tests/e2e/test_startup_assertion.py
    - tests/unit/test_route_registry.py
    - tests/unit/test_app_wiring.py
  modified:
    - src/nativespeaker/api/app/main.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/auth/verification.py
    - tests/e2e/test_error_cases.py

key-decisions:
  - "REBIND-01 is satisfied by Phase 35: all ten routes the router registers today are declared in REGISTRY, so §2.3 set equality holds at real startup"
  - "errors.py holds the seven foundation classes only; plan 02 owns the D-09 absorb of exceptions.py"
  - "ErrorClass.code is typed as the ErrorCode Literal rather than bare str, so a class carrying an unregistered code is a static error as well as a runtime one"
  - "assert_route_enumeration gained a keyword-only verifiers= parameter and registry.py a NamedVerifier seam, because §2.3 conditions 4 and 5 cannot be expressed without a notion of a registered, configured verifier"
  - "auth.py was moved to auth/verification.py in this plan: a new auth/ package shadows a sibling auth.py module, so the package could not be created without it"
  - "The barrier treats an undeclared matched route as authenticated, not as pass-through — a route with no declaration gets the strictest treatment (§1.3)"
  - "quota_checked stays False on every entry: D-05 voided its only consumer (the quota_checked_request admission entry)"

patterns-established:
  - "Wire parsing counts Authorization field instances before inspecting any value, so no first-value or last-value selection path exists"
  - "The barrier caches nothing from app.state in __init__ — every read is per-request, so the e2e rollback fixture's factory swap takes effect"
  - "registry.py imports the barrier class inside the assertion function body to break the registry <-> barrier import cycle"
  - "Negative assertion tests assert on a condition-specific substring, never on full message equality"

requirements-completed: [FOUND-01, FOUND-02, FOUND-03, FOUND-04]

coverage:
  - id: D1
    description: "An unauthenticated GET / is rejected by the barrier with 401 {\"code\":\"auth_required\"}, produced by the shared error registry and returned rather than raised"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_unauthenticated_root_is_rejected_by_the_barrier"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_error_cases.py::TestUnauthenticatedAccess::test_no_auth_header_returns_401"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /health/ready is the whole §2.1 public allowlist and is reachable with no Authorization header"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_readiness_probe_is_reachable_unauthenticated"
        status: pass
    human_judgment: false
  - id: D3
    description: "The §1.1 single-Authorization wire contract rejects zero, duplicate, comma-joined, folded, non-Bearer, empty-token, and trailing-content values with bounded reasons"
    requirement: FOUND-02
    verification:
      - kind: other
        ref: ".venv/bin/python -c \"from nativespeaker.api.auth.wire import extract_bearer, BoundedReason as B; print(extract_bearer([(b'authorization', b'Bearer a'), (b'authorization', b'Bearer b')])[1] is B.duplicate_authorization)\" -> True"
        status: pass
    human_judgment: false
    rationale: "Exhaustive per-branch coverage is plan 35-06's tests/unit/test_barrier_wire_contract.py, which owns that file."
  - id: D4
    description: "The §2.3 route-enumeration assertion runs inside the real application lifespan, is two-direction set equality, and fails closed on all nine conditions"
    requirement: FOUND-03
    verification:
      - kind: unit
        ref: "tests/unit/test_route_registry.py (29 tests — TestCondition1..TestCondition9 plus TestEnumerateRegistered)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_lifespan_completed"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_assertion_passes_against_the_live_app"
        status: pass
    human_judgment: false
  - id: D5
    description: "The shared error registry owns one response model, one closed table, and one response factory, pre-populated with exactly the seven §3.2 foundation classes"
    requirement: FOUND-04
    verification:
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_unauthenticated_root_is_rejected_by_the_barrier (asserts the exact body {\"code\": \"auth_required\"})"
        status: pass
    human_judgment: false
    rationale: "Per-class status/body/copy coverage is plan 35-02's tests/unit/test_error_registry.py, which owns that file."
  - id: D6
    description: "No documentation route is registered, no trailing-slash 307 exists, and the middleware stack is [RequestLoggingMiddleware, AuthBarrierMiddleware] outermost-first"
    requirement: FOUND-03
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py (5 tests)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_documentation_routes_are_not_registered"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_trailing_slash_does_not_redirect"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-08-21
status: complete
---

# Phase 35 Plan 01: Foundation Tracer Summary

**An unauthenticated request to an authenticated route is now rejected by a pure-ASGI barrier with a response the shared error registry produced, while the nine-condition route-enumeration assertion runs for real inside the application lifespan.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-21T04:53:00Z
- **Completed:** 2026-08-21T05:04:00Z
- **Tasks:** 2 of 2
- **Files modified:** 13 (9 created, 3 modified, 1 renamed)

## Accomplishments

- The Phase 35 architecture is proven end to end on the thinnest real path. The barrier reads route
  metadata before dispatch, returns a registry response without raising, and the assertion executes
  at real startup — the three things that would have invalidated the whole phase design.
- **REBIND-01 is satisfied early, by Phase 35.** `REGISTRY` declares all ten `(method, path)` pairs
  the router registers today, so §2.3 set equality holds in both directions against the live router
  and whoever changes the router must change the table in the same commit.
- The exact registered set observed (10 entries, 0 problems, set-equal to the declaration):
  `GET /` · `GET /examples` · `GET /health/ready` · `GET /users/me` · `GET /chats` · `POST /chats` ·
  `GET /chats/{chat_id}` · `POST /chats/{chat_id}` · `DELETE /chats/{chat_id}` ·
  `POST /webhooks/apple`. Only `GET /health/ready` is `Category.public`; the other nine are
  `Category.authenticated` with the §8.1 defaults. Plan 04 deletes `GET /users/me` and
  `POST /webhooks/apple` from the router and this table together, leaving eight.
- **`errors.py` currently holds the seven §3.2 foundation classes only** — `auth_required` 401,
  `preauth_identity_not_allowed` 403, `account_unavailable` 403, `challenge_required` 409,
  `invalid_request` 400, `verification_temporarily_unavailable` 503, `rate_limited` 429. Plan 02
  owns the D-09 absorb: it moves every business class out of `exceptions.py` into this same module
  and deletes `exceptions.py`. `exceptions.py`, `app/errors.py`, and `models/api.py` are byte-identical
  to their pre-plan contents.
- All nine §2.3 conditions have fail-if-broken unit coverage, verified by mutation (see Issues).

## Task Commits

1. **Task 1 (tracer): End-to-end "unauthenticated request is rejected"** — `ed3bbc8` (feat)
2. **Task 2: Unit-prove the nine assertion conditions and the app-wiring invariants** — `68d275e` (test)

Task 2 is test-only — its `<files>` contain no source module, so the TDD gate's behavior-adding
predicate does not apply and there is no separate RED/GREEN pair. The implementation it proves
shipped in the tracer commit.

## Files Created/Modified

**Created**

- `src/nativespeaker/api/errors.py` — the one client-visible error registry at package root (D-10):
  `ErrorClass`, `ErrorResponse`, `REGISTRY`, `register_class`, `error_response`, and the seven
  foundation class constants.
- `src/nativespeaker/api/models/auth.py` — `AuthOperation` (7 members) and `AuthEventResult`
  (44 members), mirroring `core.auth_operation` and `core.auth_event_result` verbatim.
- `src/nativespeaker/api/auth/__init__.py` — the package barrel.
- `src/nativespeaker/api/auth/wire.py` — `BoundedReason` and `extract_bearer`.
- `src/nativespeaker/api/auth/registry.py` — `Category`, `RouteMetadata`, `NamedVerifier`,
  `REGISTRY`, `VERIFIERS`, `lookup`, `enumerate_registered`, `assert_route_enumeration`.
- `src/nativespeaker/api/auth/barrier.py` — `AuthBarrierMiddleware` and `_match_full`.
- `tests/e2e/test_startup_assertion.py` — 9 tests over the real, started app.
- `tests/unit/test_route_registry.py` — 29 tests, one class per §2.3 condition.
- `tests/unit/test_app_wiring.py` — 5 tests over D-03, D-04, and Pitfall 6.

**Modified**

- `src/nativespeaker/api/app/main.py` — `docs_url/redoc_url/openapi_url=None`,
  `router.redirect_slashes = False`, `add_middleware(AuthBarrierMiddleware)` before
  `add_middleware(RequestLoggingMiddleware)`. The `responses={...}` block, router registrations,
  and `register_exception_handlers(app)` are untouched.
- `src/nativespeaker/api/app/lifespan.py` — `assert_route_enumeration(app)` under its own banner,
  after `setup_logging` and before the database engine, so a registry mismatch aborts boot before
  any network or pool I/O.
- `src/nativespeaker/api/auth/verification.py` — renamed from `src/nativespeaker/api/auth.py`,
  content byte-identical (git records it as R100).
- `tests/e2e/test_error_cases.py` — two assertions retargeted from the retired `unauthorized`
  code to `auth_required`.

## Decisions Made

- **`ErrorClass.code` is typed as the `ErrorCode` Literal, not bare `str`.** The plan's interface
  block wrote `code: str`. `ErrorResponse.code` is the Literal, so `ErrorResponse(code=cls.code)`
  would not type-check against `ty` with a bare `str`, and the alternatives (a `cast`, or bypassing
  the model) both discard the "a typo is a ValidationError at construction, not a runtime 500"
  guarantee the project already relies on. `ErrorCode` is a subtype of `str`, so every consumer
  expecting `str` is unaffected. A later phase appending a class extends the Literal alongside its
  `register_class` call, which is the D-12 totality discipline anyway.
- **`registry.py` gained a `NamedVerifier` seam and `assert_route_enumeration` a keyword-only
  `verifiers=` parameter.** §2.3 condition 4 ("naming a verifier that is not registered") and
  condition 5 ("whose named verifier lacks required configuration") are not expressible without
  some notion of a registered, configured verifier. `VERIFIERS` is empty in foundation — phases 08
  and 09 register the real Apple and Pub/Sub verifiers with their routes. The parameter is
  keyword-only with a default, so the plan's pinned `assert_route_enumeration(app, registry=REGISTRY)`
  call shape is unchanged and every later plan's `assert_route_enumeration(app)` still works.
- **The barrier treats an undeclared matched route as authenticated.** `lookup` returning `None`
  is unreachable in a started process (the assertion aborts boot first), but the fallback must not
  be pass-through: §1.3 says a route carrying no declaration receives the strictest treatment and
  must never silently become public.
- **`quota_checked` is `False` on every entry.** §8.4 marks the chat POSTs `quota_checked = True`,
  but D-05 deleted the only consumer — the `quota_checked_request` admission entry — and this plan's
  action text pins the §8.1 defaults. The field exists because §2.2 requires it; nothing reads it
  this phase.
- **The assertion runs early in the lifespan** (after `setup_logging`, before the database engine)
  rather than immediately before `yield`. The plan requires only "before the yield, after
  `app.state.config` is set"; running it first means a broken registry aborts boot without opening
  a connection pool or fetching JWKS.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] A new `auth/` package shadows the sibling `auth.py` module**

- **Found during:** Task 1, before writing any `auth/` module.
- **Issue:** `src/nativespeaker/api/auth.py` exists and is imported by seven call sites
  (`app/lifespan.py`, `app/dependencies.py`, `database/users.py`, `services/users.py`,
  `tests/unit/conftest.py`, `tests/unit/test_users.py`, `tests/unit/test_exception_handlers.py`).
  CPython's `FileFinder` resolves a directory containing `__init__.py` **before** a same-named
  `.py` file, so creating `auth/__init__.py` — which this plan requires — makes `auth.py`
  unimportable and breaks every one of those imports at collection time. Verified empirically with
  a throwaway `pkg/sub.py` + `pkg/sub/__init__.py` pair: the package wins.
- **Fix:** `git mv src/nativespeaker/api/auth.py src/nativespeaker/api/auth/verification.py`
  (content byte-identical, recorded as R100), and `auth/__init__.py` re-exports `JWTVerifier`,
  `TokenVerifier`, and `UserIdentity` alongside the six symbols this plan's action text names. Every
  existing `from nativespeaker.api.auth import ...` keeps working with **zero** call-site edits.
- **Relationship to plan 02:** this is the mechanical half of D-23, which plan 02 owns. Plan 02's
  truth "`auth.py` no longer exists; `TokenVerifier` and `JWTVerifier` live at
  `auth/verification.py`" is now already true; plan 02 still layers the §1.2 verification rules onto
  the file and retargets importers to the full module path, at which point the three compatibility
  re-exports in the barrel can go.
- **Files modified:** `src/nativespeaker/api/auth/verification.py` (renamed),
  `src/nativespeaker/api/auth/__init__.py`.
- **Verification:** `pytest -q` 163 passed (unchanged baseline); `ruff check src tests` and
  `ty check src` clean.
- **Committed in:** `ed3bbc8`.

**2. [Rule 1 - Bug] Two e2e assertions pinned the D-11-retired `unauthorized` 401 code**

- **Found during:** Task 1, post-change e2e run (26 failed → 28 failed against the measured baseline).
- **Issue:** `tests/e2e/test_error_cases.py::TestUnauthenticatedAccess::test_no_auth_header_returns_401`
  and `test_no_auth_on_users_me_returns_401` asserted `response.json()["code"] == "unauthorized"`.
  With the barrier installed, those two paths are now rejected before `get_current_user` runs, so
  they emit `auth_required`. Both were passing before this task and failed because of it — my
  regressions, not the pre-existing v2.0 schema drift.
- **Fix:** retargeted both assertions (and their docstrings) at `auth_required`. This is exactly
  what D-11 mandates: "`auth_required` becomes the only 401 the service emits. Tests and `k8s/`
  references to the old string are updated in this phase." Only the two assertion strings changed —
  `test_invalid_bearer_token_returns_401` still correctly expects `unauthorized`, because token
  *verification* does not move onto the barrier until plan 06.
- **Files modified:** `tests/e2e/test_error_cases.py`.
- **Verification:** `pytest -q -m e2e` back to 26 failed / 16 passed — the exact pre-plan failure
  set, plus this plan's 9 new passing tests and the 2 repaired ones.
- **Committed in:** `ed3bbc8`.

**3. [Rule 2 - Missing critical functionality] `extract_bearer` could raise on non-ASCII token bytes**

- **Found during:** Task 1, writing `auth/wire.py`.
- **Issue:** the plan pins "the token bytes decoded as strict ASCII" but says nothing about a decode
  failure. `bytes.decode("ascii", "strict")` raises `UnicodeDecodeError` on any non-ASCII byte, and
  the barrier runs outside Starlette's `ExceptionMiddleware`, so a crafted header would have
  surfaced as a 500 from a trust boundary rather than a fail-closed rejection.
- **Fix:** the decode is wrapped and a failure returns `BoundedReason.malformed`, consistent with
  §1.1's treatment of every other ill-formed credential.
- **Files modified:** `src/nativespeaker/api/auth/wire.py`.
- **Verification:** covered by the module's own contract; exhaustive per-branch coverage is plan
  35-06's `tests/unit/test_barrier_wire_contract.py`, which owns that file.
- **Committed in:** `ed3bbc8`.

---

**Total deviations:** 3 auto-fixed (1 × Rule 1, 1 × Rule 2, 1 × Rule 3).
**Impact on plan:** No scope creep. Deviation 1 was a hard precondition for creating the package at
all; deviation 2 is D-11 being applied where this task's change made it bite; deviation 3 closes a
crash path on untrusted input. None changes the plan's deliverables or its interfaces.

## Issues Encountered

- **Verifying the negative tests actually fail if broken.** A test asserting `pytest.raises(RuntimeError)`
  can pass for the wrong reason when the assertion accumulates several problems. Every negative case
  therefore asserts on a condition-specific substring, and coverage was confirmed by five targeted
  mutations of `registry.py` — dropping condition 2, condition 5, condition 6, condition 9, and
  synthesizing a `HEAD` entry in `enumerate_registered`. Each mutation was caught (2, 1, 1, 1 and 4
  failing tests respectively), and `registry.py` was restored and confirmed byte-identical to the
  committed version afterwards.
- **Out of scope, logged not fixed:** `tests/unit/test_logging.py::test_middleware_logs_request_on_response`
  and `::test_middleware_error_level_for_non_2xx` fail in a combined `pytest -m ""` run while passing
  in the unit-only run — an e2e module's lifespan calls `setup_logging()`, which reconfigures
  structlog with `cache_logger_on_first_use=True` so `structlog.testing.capture_logs()` can no longer
  intercept `logs.py`'s cached logger. Proven to predate this plan by reproducing it with this plan's
  new e2e module excluded, and with `tests/e2e/test_error_cases.py` alone. Recorded in
  `.planning/phases/35-foundation/deferred-items.md`.

## Test Status

| Suite | Result | Note |
|---|---|---|
| Unit (`pytest -q`) | **197 passed**, 119 deselected | 163 baseline + 34 new; zero regressions |
| Schema (`pytest -q -m schema`) | **77 passed** | unchanged |
| E2E (`pytest -q -m e2e`) | 16 passed, **26 failed** | 26 failures are the pre-existing v2.0 schema drift (`column users.jwt_sub does not exist`), repaired by plan 35-05. All 9 new tests pass; the 2 tests this plan broke were repaired. |
| `ruff check src tests` | **All checks passed!** | |
| `ty check src` | **All checks passed!** | |

The plan's `<verification>` bullet "`pytest -q -m ""` is green" cannot hold at plan 01 — it is the
D-18 phase-end bar, and the 26 e2e failures it covers are plan 35-05's to repair.

## Known Stubs

None. Every symbol this plan declares is implemented and exercised. Three seams are deliberately
empty rather than stubbed, each with a named owner:

| Seam | State | Owner |
|---|---|---|
| `auth/registry.py::VERIFIERS` | empty dict — foundation registers no provider-callback verifier (§2.1, "Explicitly out of scope") | phases 08 / 09 (plans 35-08, 35-09) |
| Barrier steps 3–5 (verify token, resolve identity, admission matrix) | the barrier passes a well-formed token through unchanged | plan 35-06 |
| `errors.py` business classes | `exceptions.py` still holds them and is byte-identical | plan 35-02 (D-09) |

## Threat Flags

None. Every file this plan created or modified is covered by the plan's own `<threat_model>`; no new
network endpoint, auth path, file-access pattern, or schema change at a trust boundary was introduced
beyond it. The four `mitigate` dispositions on this plan's files are all implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-01-01 | `extract_bearer` counts `b"authorization"` instances from the raw scope list and rejects `len != 1` before any value is inspected |
| T-35-01-02 | `assert_route_enumeration` is two-direction set equality raising `RuntimeError` inside the lifespan |
| T-35-01-03 | `docs_url=None, redoc_url=None, openapi_url=None` — zero documentation routes registered |
| T-35-01-04 | `app.router.redirect_slashes = False` — `GET /chats/` is 404, not an unauthenticated 307 |
| T-35-01-05 | the reject path awaits the response against `(scope, receive, send)`; `self.app` is never called and nothing is raised |
| T-35-01-SC | no package was installed; the legitimacy gate stays vacuous for Phase 35 |

## Next Phase Readiness

Ready. Every plan 02–11 interface this plan owed exists at the pinned module path with the pinned
signature: `errors.ErrorClass` / `ErrorResponse` / `REGISTRY` / `register_class` / `error_response`
and the seven class constants; `auth.wire.BoundedReason` / `extract_bearer`;
`auth.registry.Category` / `RouteMetadata` / `REGISTRY` / `lookup` / `enumerate_registered` /
`assert_route_enumeration`; `auth.barrier.AuthBarrierMiddleware`; `models.auth.AuthOperation` /
`AuthEventResult`.

Notes for the plans that follow:

- **Plan 02** finds `auth/verification.py` already in place, byte-identical to the old `auth.py`. It
  still owns layering the §1.2 rules onto it, retargeting the seven importers to the full module
  path, and removing the three compatibility re-exports from `auth/__init__.py`. It also owns the
  D-09 absorb, extending the `ErrorCode` Literal for each business class it moves in.
- **Plan 04** must delete `GET /users/me` and `POST /webhooks/apple` from `auth/registry.py::REGISTRY`
  in the same commit as the router deletions, or the lifespan assertion aborts boot. The target is
  eight entries.
- **Plan 06** builds on the barrier's existing seam: `_token` is already extracted and discarded at
  the point where verification, identity resolution, and the typed context belong.
- **Known, accepted, not a task:** `k8s/templates/backend-traffic-policy.yaml:53` emits
  `'{"code":"quota_exceeded"}'` on a 429 where §3.2 wants `rate_limited`. D-08 forbids touching
  `k8s/` this phase.

## Self-Check: PASSED

All 10 claimed files exist on disk; both claimed commits (`ed3bbc8`, `68d275e`) are present in
`git log`.

---
*Phase: 35-foundation*
*Completed: 2026-08-21*
