---
phase: 35-foundation
plan: 02
subsystem: errors
tags: [fastapi, starlette, error-registry, exception-handlers, jwt, pyjwt, pydantic]

requires:
  - phase: 35-foundation
    plan: 01
    provides: "errors.py with ErrorClass/ErrorResponse/REGISTRY/register_class/error_response and the seven §3.2 foundation classes; auth/wire.py BoundedReason; auth/verification.py already moved off auth.py"
provides:
  - "errors.py — the complete single registry: 14 classes, ErrorResponse, ServiceError and its 15 subclasses, STATUS_TO_CLASS, and assert_registry_total"
  - "app/errors.py — four handlers reading the registry instead of a status-folding table"
  - "auth/verification.py — §1.2 verification returning (VerifiedClaims | None, BoundedReason | None) instead of raising"
  - "tests/unit/test_error_registry.py — 36 tests over registry totality, the framework mapping, and the loud unmapped-status path"
affects: [35-03, 35-04, 35-05, 35-06, 35-07, 35-08, 35-09, 35-10, 35-11, 36-rebinding]

actuals:
  tokens: 22236
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "One frozen ErrorClass per client-visible condition; the exception subclass points at a class rather than declaring a status and a code that could disagree"
    - "A closed status→class table whose every entry carries its own key as its status, so folding is structurally impossible and provable"
    - "A lifespan self-check that fails closed on registry defects a later phase could introduce"
    - "Verification returning a two-tuple rather than raising, because the barrier sits outside Starlette's ExceptionMiddleware"
    - "A test stub that imports the production mapping rather than reimplementing it, so it cannot drift from what it stands in for"

key-files:
  created:
    - tests/unit/test_error_registry.py
  modified:
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/app/errors.py
    - src/nativespeaker/api/app/main.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/auth/verification.py
    - src/nativespeaker/api/auth/__init__.py
    - src/nativespeaker/api/models/api.py
    - src/nativespeaker/api/models/__init__.py
    - src/nativespeaker/api/resilience.py
    - src/nativespeaker/api/services/chats.py
    - src/nativespeaker/api/services/subscriptions.py
    - src/nativespeaker/api/services/users.py
    - src/nativespeaker/api/database/users.py
    - src/nativespeaker/api/routers/webhooks.py
    - tests/unit/conftest.py
    - tests/unit/test_jwt_security.py
    - tests/unit/test_error_contract.py
    - tests/unit/test_exception_handlers.py
    - tests/unit/test_auth_security.py
    - tests/unit/test_users.py
    - tests/unit/test_usage.py
    - tests/unit/test_webhooks.py
    - tests/unit/test_models.py
    - tests/unit/test_services.py
    - tests/e2e/test_error_cases.py
  deleted:
    - src/nativespeaker/api/exceptions.py

key-decisions:
  - "STATUS_TO_CLASS deliberately omits 403: two classes sit there and neither is generic, so any entry would be the arbitrary lie D-12 deletes. Both 403 classes are emitted by the barrier through error_response, which needs no status lookup."
  - "WebhookVerificationError moves to invalid_request (400). It declared the validation_error code at status 400 while validation_error is pinned at 422 — one class, one status makes that pair unrepresentable."
  - "ServiceError.error_class replaces the status_code/error_code pair outright, so no subclass can name a status and a code that disagree."
  - "UsersDB/UserService take the verified subject rather than an identity object: VerifiedClaims carries no email or name, and §1.2 forbids deriving them."
  - "The unmapped-status ERROR log is asserted with a recording spy, not structlog.testing.capture_logs, which cannot intercept a cached logger after an e2e lifespan calls setup_logging."
  - "PyJWTError is the catch boundary in verify(): it covers PyJWT's whole declared taxonomy while letting a genuinely alien exception propagate loudly."

patterns-established:
  - "Registry mutation tests restore both module-level dicts in a finally block, mutating the same objects production holds rather than rebinding a local name"
  - "Negative registry assertions match on a defect-specific substring, never on full message equality"
  - "Coverage of a self-check is proven by mutating the checked module, then confirming it byte-identical afterwards"

requirements-completed: [FOUND-01, FOUND-04]

coverage:
  - id: D1
    description: "Exactly one module declares every client-visible error class; exceptions.py no longer exists"
    requirement: FOUND-04
    verification:
      - kind: other
        ref: "test ! -e src/nativespeaker/api/exceptions.py; python -c 'import nativespeaker.api.exceptions' -> ModuleNotFoundError"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestRegistryTotality (6 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "No two registered classes share a code, and every class has exactly one status"
    requirement: FOUND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestRegistryTotality::test_no_two_classes_share_a_code, ::test_every_class_carries_exactly_one_status"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestRegistryTotalityCatchesDefects (5 tests, each mutation-verified)"
        status: pass
    human_judgment: false
  - id: D3
    description: "No status-folding table and no status→code fallback: an unmapped status logs error_registry_unmapped_status at ERROR and returns internal_error"
    requirement: FOUND-04
    verification:
      - kind: other
        ref: "python -c \"import nativespeaker.api.app.errors as m; print(hasattr(m,'_STATUS_REMAP'), hasattr(m,'_CODE_MAP'))\" -> False False"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestHttpExceptionHandler (6 tests) and ::TestStatusToClass::test_no_status_is_folded_onto_another"
        status: pass
    human_judgment: false
  - id: D4
    description: "Handlers are registered in one place in a fixed specificity order, and within a class status, body and copy are identical regardless of branch"
    requirement: FOUND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestServiceErrorHandler (3 tests — byte-identical bodies across two subclasses of one class)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_exception_handlers.py (25 tests over the four-handler registration)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The D-11-retired 401 code is absent from the registry, the ErrorCode Literal, the response model and the OpenAPI responses block"
    requirement: FOUND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestRetired401Code (6 tests)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_error_cases.py::TestUnauthenticatedAccess::test_invalid_bearer_token_returns_401 (retargeted to auth_required)"
        status: pass
    human_judgment: false
  - id: D6
    description: "A framework 409 surfaces as challenge_required at 409, not as a 400 — the collision the deleted remap table caused is gone"
    requirement: FOUND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestStatusToClass::test_409_is_challenge_required_not_invalid_request, ::TestHttpExceptionHandler::test_409_surfaces_as_challenge_required"
        status: pass
    human_judgment: false
  - id: D7
    description: "A wrong-method request to a registered path surfaces as method_not_allowed at 405 with the router's Allow header preserved"
    requirement: FOUND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestHttpExceptionHandler::test_405_preserves_the_routers_allow_header"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_contract.py::TestStatusCodeRemapping::test_wrong_method_returns_405 (over a live client)"
        status: pass
    human_judgment: false
  - id: D8
    description: "No class is declared for 415, because python-multipart is absent and no branch can reach it"
    requirement: FOUND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestNo415Class (3 tests, including a guard on the premise itself)"
        status: pass
    human_judgment: false
  - id: D9
    description: "auth.py no longer exists; TokenVerifier and JWTVerifier live at auth/verification.py and every importer points there"
    requirement: FOUND-01
    verification:
      - kind: other
        ref: "test ! -e src/nativespeaker/api/auth.py && test -f src/nativespeaker/api/auth/verification.py; grep for `nativespeaker.api.auth import` -> no verification symbols imported via the barrel by src/"
        status: pass
    human_judgment: false
  - id: D10
    description: "Verification pins iss and aud to the one configured integration, verifies RS256 only, requires a non-empty sub, and makes no per-request network call"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_jwt_security.py::TestProductionVerifier (6 tests over the real JWTVerifier with only the JWKS transport stubbed, including zero-additional-fetch)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_jwt_security.py::TestClaimValidation, ::TestAlgorithmSecurity, ::TestSignatureVerification (12 tests)"
        status: pass
    human_judgment: false
  - id: D11
    description: "Every verification failure maps to exactly one BoundedReason and returns the identical auth_required status, body and copy; the response names no issuer, integration, or failed check"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_jwt_security.py::TestAntiOracle (6 tests — every branch returns the same two-tuple shape and exactly one slot is populated)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_registry.py::TestServiceErrorHandler::test_the_exception_message_never_reaches_the_body"
        status: pass
    human_judgment: false

duration: 24min
completed: 2026-08-20
status: complete
---

# Phase 35 Plan 02: Error Registry Absorb and §1.2 Verification Summary

**One module now declares every client-visible error class in the service, the status-folding table that would have surfaced a challenge as a shape error is gone, and token verification returns a bounded reason instead of raising into a 500.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-08-20T22:01Z
- **Completed:** 2026-08-20T22:25Z
- **Tasks:** 3 of 3
- **Files modified:** 28 (1 created, 26 modified, 1 deleted)

## Accomplishments

- **D-09 is complete.** `errors.py` holds all fourteen client-visible classes, `ErrorResponse`,
  `ServiceError` and its fifteen subclasses. `exceptions.py` is deleted and every one of its
  seventeen importers points at the registry.
- **D-12 is complete.** `_STATUS_REMAP` and `_CODE_MAP` are gone outright, replaced by a closed
  `STATUS_TO_CLASS` whose every entry carries its own key as its status — so folding is not a
  discipline, it is unrepresentable, and `assert_registry_total` proves it at boot.
- **D-11 is complete.** The `unauthorized` code is absent from the registry, the `ErrorCode`
  Literal, `ErrorResponse`, and the app's OpenAPI `responses` block. `auth_required` is the only
  401 the service emits.
- **§1.2 is implemented.** `verify` returns `(VerifiedClaims | None, BoundedReason | None)`.
  `VerifiedClaims` carries exactly the verified `iss` and `sub`; the `email` and `name` the v1.6
  `UserIdentity` read off the token do not survive, per §1.2 and SHARED-INVARIANTS.
- The unit suite grew **197 → 249** (+52) with zero regressions, and both gates stay clean.

### The final `ErrorCode` set (14 codes)

| Class | Status | Code | Origin |
|---|---|---|---|
| `auth_required` | 401 | `auth_required` | §3.2 foundation (plan 01) |
| `preauth_identity_not_allowed` | 403 | `preauth_identity_not_allowed` | §3.2 foundation (plan 01) |
| `account_unavailable` | 403 | `account_unavailable` | §3.2 foundation (plan 01) |
| `challenge_required` | 409 | `challenge_required` | §3.2 foundation (plan 01) |
| `invalid_request` | 400 | `invalid_request` | §3.2 foundation (plan 01) |
| `verification_temporarily_unavailable` | 503 | `verification_temporarily_unavailable` | §3.2 foundation (plan 01) |
| `rate_limited` | 429 | `rate_limited` | §3.2 foundation (plan 01) |
| `validation_error` | 422 | `validation_error` | absorbed, verbatim |
| `not_found` | 404 | `not_found` | absorbed, verbatim |
| `method_not_allowed` | 405 | `method_not_allowed` | **new** (A1) |
| `internal_error` | 500 | `internal_error` | absorbed, verbatim |
| `service_unavailable` | 503 | `service_unavailable` | absorbed, verbatim |
| `quota_exceeded` | 429 | `quota_exceeded` | absorbed, verbatim |
| `out_of_scope` | 400 | `out_of_scope` | absorbed, verbatim |

Two pairs share a status (`preauth_identity_not_allowed`/`account_unavailable` at 403,
`rate_limited`/`quota_exceeded` at 429, `verification_temporarily_unavailable`/`service_unavailable`
at 503). That is allowed and intended — §3.1 pins *one status per class*, not one class per status.

### `STATUS_TO_CLASS` contents (9 entries)

| Status | Class |
|---|---|
| 400 | `invalid_request` |
| 401 | `auth_required` |
| 404 | `not_found` |
| 405 | `method_not_allowed` |
| 409 | `challenge_required` |
| 422 | `validation_error` |
| 429 | `rate_limited` |
| 500 | `internal_error` |
| 503 | `service_unavailable` |

**No class carries status 415, and 415 is not a key in `STATUS_TO_CLASS`.** `python-multipart` is
not installed, so a `Form` or `File` parameter cannot be declared and no branch can reach that
status. `TestNo415Class::test_python_multipart_is_not_installed` guards the premise itself: if the
package ever appears, that test fails and tells the reader 415 now needs a declared class.

## Task Commits

1. **Task 1: Absorb every business class and delete exceptions.py** — `d610cda` (feat)
2. **Task 2 (TDD): §1.2 verification rules** — `685a3d2` (test, RED) → `69077f3` (feat, GREEN)
3. **Task 3: Prove registry totality and the framework mapping** — `1582e6e` (test)

Task 2's RED commit left 178 unit tests passing and `test_jwt_security.py` failing at collection
(`VerifiedClaims` did not yet exist); the GREEN commit took it to 213. Task 3 is test-only — its
`<files>` contain no source module, so the behavior-adding predicate does not apply and there is no
separate RED/GREEN pair.

## Decisions Made

- **`STATUS_TO_CLASS` deliberately omits 403.** Two classes sit at 403 —
  `preauth_identity_not_allowed` and `account_unavailable` — and neither is the generic answer, so
  any entry would be an arbitrary lie of exactly the kind D-12 deletes. Both are emitted by the
  barrier through `error_response`, which takes a class and needs no status lookup, so the
  omission costs nothing: a bare framework 403 is a programming error and takes the loud
  unmapped-status path. Picking one would have been actively harmful — surfacing a stray 403 as
  `account_unavailable` would hand a client the terminal "discard your tokens, contact support"
  contract for what is a bug. The plan's truth *"every status the service can emit maps to exactly
  one declared class"* cannot hold literally for 403, because two classes declare it; it holds in
  the sense that matters, since the class is the source there and the status is never the key.
- **`ServiceError.error_class` replaces the `status_code`/`error_code` pair outright** rather than
  keeping both and deriving one. That is what made the `WebhookVerificationError` defect below
  visible at all, and it makes a disagreeing pair unrepresentable for every future subclass.
- **`assert_registry_total` accumulates problems and raises once** with all of them listed, rather
  than raising on the first. A phase that appends a class carelessly usually breaks more than one
  invariant, and reporting them separately is the same discipline `assert_route_enumeration` uses
  for its two set differences.
- **`PyJWTError` is the catch boundary in `verify`.** It is the root of PyJWT's entire declared
  taxonomy (`InvalidTokenError`, `InvalidKeyError`, and `PyJWKClientError` all derive from it), so
  it covers every verification failure the library defines while letting a genuinely alien
  exception propagate. That satisfies the plan's "catch the specific types, not a bare `Exception`"
  at the right granularity — a `TypeError` from a future refactor still surfaces loudly.
- **`bounded_reason_for` and `claims_from_payload` are public in `verification.py`** so the test
  fixed-key verifier imports the production mapping instead of reimplementing it. The old
  `_FixedKeyVerifier` duplicated eight `except` clauses; a drift between it and the real verifier
  would have made `test_jwt_security.py` test the stub's opinion rather than the service's.
- **A missing `exp` or `iat` maps to `bad_signature`, not `expired`.** The plan enumerates only
  `ExpiredSignatureError`/`ImmatureSignatureError` as `expired`, and every remaining verification
  failure as `bad_signature`. A missing required claim is arguably a temporal failure, but the
  bounded reason is audit- and metric-only and never client-visible, so following the plan's
  enumeration exactly is worth more than the semantic nuance. A missing `sub` is the one
  documented exception, mapping to `empty_subject`.
- **The `403` and `429` OpenAPI `responses` entries were left as they were**, and `405` was added
  alongside the reworded 401. The block is documentation, not the registry; adding 405 records the
  one genuinely new status a client can now see.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `WebhookVerificationError` declared a 422 code at status 400**

- **Found during:** Task 1, moving the fifteen subclasses into the registry.
- **Issue:** `exceptions.py` gave it `status_code = 400` and `error_code = "validation_error"`,
  while `validation_error` is pinned at 422. Under the old two-attribute shape the disagreement was
  invisible; under `error_class: ErrorClass` it is unrepresentable, because a class carries exactly
  one status. Keeping the pair would have meant registering a second 400 class named
  `validation_error`, which is both the near-duplicate §3.1 forbids and a duplicate code
  `register_class` rejects.
- **Fix:** pointed it at `INVALID_REQUEST` — status 400 unchanged, code `invalid_request`. §3.2
  describes `invalid_request` as covering "request-shape rejections before any operation-specific
  meaning", which is exactly what its two raise sites are (a missing `signedPayload`, a failed JWS
  signature). The status the client sees is unchanged; only the code string moves.
- **Files modified:** `src/nativespeaker/api/errors.py`, `tests/unit/test_webhooks.py` (two
  assertions).
- **Scope note:** `routers/webhooks.py` and `services/subscriptions.py` are deleted by plan 04, so
  this code string has one plan left to live.
- **Committed in:** `d610cda`.

**2. [Rule 1 - Bug] Two e2e tests and seven unit assertions pinned the retired 401 code**

- **Found during:** Task 1, post-change runs. E2E went 26 → 27 failures against the measured
  baseline; the extra one was mine.
- **Issue:** `AuthenticationError` now points at `AUTH_REQUIRED`, so every path that used to emit
  `unauthorized` emits `auth_required`. `tests/e2e/test_error_cases.py::test_invalid_bearer_token_returns_401`
  (which plan 01 deliberately left on the old code, expecting plan 06 to move verification onto the
  barrier), five assertions in `test_auth_security.py`, two in `test_exception_handlers.py`, and one
  in `test_users.py` all pinned the old string.
- **Fix:** retargeted all of them at `auth_required` — exactly what D-11 mandates ("Tests and `k8s/`
  references to the old string are updated in this phase"). The e2e test's docstring now records
  *why* it changed a plan earlier than plan 01 expected: D-11 bites at the class, not at the barrier.
- **Verification:** e2e back to 26 failed / 16 passed — the exact measured baseline.
- **Committed in:** `d610cda`.

**3. [Rule 3 - Blocking] `UserIdentity` had four consumers outside task 2's file list**

- **Found during:** Task 2, removing `UserIdentity`.
- **Issue:** the plan lists `app/lifespan.py` and `app/dependencies.py` as the importers to
  repoint, but `services/users.py`, `database/users.py`, `tests/unit/test_users.py`, and
  `tests/unit/test_exception_handlers.py` also imported it. `UsersDB.get_or_create(identity)` read
  `identity.sub`, `.email`, and `.name` — two of which §1.2 forbids carrying forward.
- **Fix:** `UsersDB.get_or_create` and `UserService.get_or_create` now take the verified
  `subject: str`, and the insert no longer copies `email`/`name` off the token. `get_current_user`
  unpacks the two-tuple and raises `AuthenticationError` when the claims are `None` — the reason is
  discarded there, unused until plan 06 audits it. `test_exception_handlers.py`'s `_AlwaysUser` stub
  returns the new two-tuple. This path is already dead at runtime (`column users.jwt_sub does not
  exist`) and plan 04 deletes both modules; the change keeps the tree importable and the suite green
  at every commit without inventing a fabricated email.
- **Files modified:** `src/nativespeaker/api/services/users.py`,
  `src/nativespeaker/api/database/users.py`, `src/nativespeaker/api/app/dependencies.py`,
  `tests/unit/test_exception_handlers.py`, `tests/unit/test_users.py`.
- **Committed in:** `69077f3`.

**4. [Rule 3 - Blocking] `test_users.py::TestUserIdentity` tested a symbol this plan removes**

- **Found during:** Task 2.
- **Issue:** three tests constructed `UserIdentity(sub=..., email=..., name=...)`. Deleting them
  outright would have dropped USER-01's value-object coverage and the unit count with it.
- **Fix:** moved the coverage to `test_jwt_security.py::TestVerifiedClaims`, beside the rules that
  produce the object, and strengthened it: it now also asserts the field set is *exactly*
  `{issuer, subject}` and that no `email` or `name` attribute exists — turning three tests of a
  removed class into four tests of the §1.2 constraint that removed it. `test_users.py` keeps a
  pointer comment.
- **Committed in:** `69077f3`.

**5. [Rule 3 - Blocking] The HS256-over-public-key test could not be written with `pyjwt.encode`**

- **Found during:** Task 2 GREEN, first full run — two of my own new tests errored.
- **Issue:** PyJWT refuses to *encode* HS256 with a PEM key
  (`InvalidKeyError: The specified key is an asymmetric key ... should not be used as an HMAC
  secret`). That guard is on the encode side only, so the test could not express the attack it was
  meant to reproduce — but an attacker has no such guard.
- **Fix:** added an `hs256_over(secret, payload)` helper that hand-builds the compact form with
  `hmac`/`base64`, which is what an attacker actually emits. Both tests now genuinely exercise the
  decode-side rejection, at the stub and at the real `JWTVerifier`.
- **Committed in:** `69077f3`.

---

**Total deviations:** 5 auto-fixed (2 × Rule 1, 3 × Rule 3). No Rule 4 architectural questions
arose. None changes the plan's deliverables or its interfaces.

## Issues Encountered

- **A mutation that silently did nothing.** The first pass of the "re-add `unauthorized` to the
  `ErrorCode` Literal" mutation reported all 36 tests still passing, which would have meant a real
  coverage hole. The mutation itself was the bug: its anchor string carried twenty spaces of
  indentation, but the first Literal member sits on the `ErrorCode = Literal[` line, so the replace
  matched nothing. Re-run correctly, it fails four tests. Recorded because a green mutation run is
  the exact shape of a false negative that plan 01 warned about — a mutation must be confirmed to
  have applied before its result means anything.
- **Ten mutations, all caught.** Coverage of the self-check was verified by mutating the checked
  modules: restoring the `409 → 400` fold (4 failures), dropping the unmapped-status ERROR log (1),
  dropping the `Allow` header forwarding (1), re-adding the retired code (4), removing each of the
  four `assert_registry_total` clauses (1 each), removing the `register_class` duplicate-code guard
  (1), registering an unreachable 415 class (1), and leaking `str(exc)` into the response body (2).
  `git diff --exit-code -- src/` confirmed both modules byte-identical to the committed versions
  afterwards.
- **`structlog.testing.capture_logs` was avoided on purpose.** It is the helper the plan names, but
  `deferred-items.md` already records that it cannot intercept a module-level cached logger once an
  e2e lifespan has called `setup_logging()` — which is why two `test_logging.py` tests fail in a
  combined run. Using it for the unmapped-status assertion would have knowingly added a third. A
  recording spy installed with `monkeypatch` asserts the same thing (event name, field, and ERROR
  level) with no dependency on structlog's configuration state, and passes in both run modes.
- **Out of scope, unchanged:** the two `test_logging.py` failures in a combined `pytest -m ""` run
  are the pre-existing deferred item, reproduced unchanged. Not touched.

## Test Status

| Suite | Result | Note |
|---|---|---|
| Unit (`pytest -q`) | **249 passed**, 119 deselected | 197 baseline + 52 net; zero regressions |
| Schema (`pytest -q -m schema`) | **77 passed** | unchanged |
| E2E (`pytest -q -m e2e`) | 16 passed, **26 failed** | exactly the measured baseline — pre-existing v2.0 schema drift (`column users.jwt_sub does not exist`), repaired by plan 35-05 |
| Combined (`pytest -q -m ""`) | 340 passed, **28 failed** | the 26 e2e above + the 2 known `test_logging.py` deferred items |
| `ruff check src tests` | **All checks passed!** | |
| `ty check src` | **All checks passed!** | |

No `xfail` markers exist anywhere in `tests/` (D-18).

The plan's `<verification>` bullet "`pytest -q -m ""` is green with no xfail" cannot hold at plan
02, for the same reason it could not at plan 01: it is the D-18 phase-end bar, and the 26 e2e
failures it covers are plan 35-05's to repair.

**App boots:** `assert_registry_total()` runs at `app/lifespan.py:31`, immediately before
`assert_route_enumeration(app)` at line 32, and both pass against the live app —
`tests/e2e/test_startup_assertion.py` (9 tests) exercises the real started application.

## Known Stubs

None. Every symbol this plan declares is implemented and exercised.

Two seams are deliberately narrow rather than stubbed, each with a named owner:

| Seam | State | Owner |
|---|---|---|
| `get_current_user` discards the `BoundedReason` it now receives | the reason is audit- and metric-only; nothing consumes it until the barrier owns verification | plan 35-06 |
| `AuthenticationError` still exists as a class | plan 04 deletes its v1.6 raise sites; plan 03's three identity accessors become its only ones | plans 35-03 / 35-04 |

## Threat Flags

None. Every file this plan created or modified is covered by the plan's own `<threat_model>`. No
new network endpoint, auth path, file-access pattern, or schema change at a trust boundary was
introduced. The five `mitigate` dispositions are all implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-02-01 | `algorithms=["RS256"]` passed explicitly in `verify`; `alg: none`, HS256, and hand-built HS256-over-the-public-key all land on `bad_signature`, each with a retained regression test |
| T-35-02-02 | `issuer` pinned to the single configured `JWTConfig.issuer`; a mismatch returns `issuer_mismatch` before any Admin work, and no ambient/default/fallback client is constructible |
| T-35-02-03 | one class per condition, no free-text field on `ErrorResponse`; `test_the_exception_message_never_reaches_the_body` proves `str(exc)` cannot leak into the body |
| T-35-02-04 | `STATUS_TO_CLASS[409]` is `challenge_required`; `test_no_status_is_folded_onto_another` makes the whole table's honesty an assertion |
| T-35-02-05 | `error_registry_unmapped_status` logged at ERROR with the status as a field, asserted by two tests including one that proves a *mapped* status logs nothing |
| T-35-02-06 | timing differences between `account_unavailable` branches remain accepted per D-13, not mitigated — documented, not omitted |
| T-35-02-SC | no package was installed; the legitimacy gate stays vacuous for Phase 35 |

The **prohibition** on accusatory, shaming, or fault-attributing copy is satisfied by judgment over
all fourteen classes. Each states the condition and the remediation without telling the caller they
did something wrong or implying abuse. The two the prohibition names explicitly:
`account_unavailable` reads "Account unavailable -- contact support." and `rate_limited` reads "Too
many requests. Wait for the indicated interval and retry." `quota_exceeded`, the other class that
could easily have accused, reads "The allowance for the current period is used up. It refreshes
next period." — a statement about the allowance, not about the user.

## Next Phase Readiness

Ready. Every interface plans 03–11 import from this plan exists at the pinned module path:

- `errors.ErrorClass` / `ErrorCode` / `ErrorResponse` / `REGISTRY` / `STATUS_TO_CLASS` /
  `error_response` / `register_class` / `assert_registry_total` / `ServiceError` and the fourteen
  class constants.
- `auth.verification.VerifiedClaims` / `TokenVerifier` / `JWTVerifier` / `VerificationResult` /
  `bounded_reason_for` / `claims_from_payload`.

Notes for the plans that follow:

- **Appending a class is a three-part edit**, and the self-check enforces all three: add the code to
  the `ErrorCode` Literal, call `register_class`, and — only if the framework can raise that status
  — add a `STATUS_TO_CLASS` entry whose class carries that same status. Omitting any part aborts
  boot with a message naming the omission.
- **Plan 06** inherits the verification seam ready to use: `verify` already returns the bounded
  reason the barrier must record in `details.failure` and in the metric label. `get_current_user`
  currently discards it.
- **Plan 04** deletes `routers/webhooks.py`, `services/subscriptions.py`, `services/users.py`, and
  `database/users.py`; `WebhookVerificationError` goes with them, and `AuthenticationError`'s v1.6
  raise sites go with `get_current_user`.
- **Plan 11** writes the final `auth/__init__.py` barrel. It currently exports `VerifiedClaims`
  alongside `JWTVerifier` and `TokenVerifier`; every `src/` importer already uses the full module
  path, so the barrel entries are for external convenience only.
- **Known, accepted, not a task:** `k8s/templates/backend-traffic-policy.yaml:53` emits
  `'{"code":"quota_exceeded"}'` on a 429 where §3.2 wants `rate_limited`. D-08 forbids touching
  `k8s/` this phase. Both codes are now registered, so the chart's string is at least a declared
  class — just the wrong one for that surface.

## Self-Check: PASSED

All 28 claimed files are in their claimed state on disk (`exceptions.py` absent,
`test_error_registry.py` present, the other 26 modified). All four claimed commits — `d610cda`,
`685a3d2`, `69077f3`, `1582e6e` — are present in `git log`.

---
*Phase: 35-foundation*
*Completed: 2026-08-20*
