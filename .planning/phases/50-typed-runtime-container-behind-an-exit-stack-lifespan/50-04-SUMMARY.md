---
phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
plan: 04
subsystem: app
tags: [runtime, dependencies, lifespan, session, jwt, pytest]

requires:
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "`Runtime`, `get_runtime` and `app.state.runtime` (50-03)"
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "`make_runtime(**overrides)` in `tests/unit/conftest.py` (50-03)"
provides:
  - "`get_db`, `get_identity` and `get_quota_service` served off the container, with no `Request`"
  - "`get_claims` served off the container, keeping `Request` for the authorization header alone"
  - "the `dataclasses.replace` fixture pattern for the e2e suite, proven under nesting"
affects: [50-05, 50-06, 50-07]

actuals:
  tokens: 9800
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "An e2e fixture saves the container FIELD, replaces the field, and restores the field, so a nested fixture's swap is never reverted"
    - "A unit app sets one `app.state.runtime = make_runtime(...)` naming only the fields that file reads"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/app/lifespan.py
    - tests/e2e/conftest.py
    - tests/unit/test_identity_accessors.py
    - tests/unit/test_jwks_offload.py
    - tests/unit/test_app_wiring.py
    - tests/unit/test_auth_security.py
    - tests/unit/test_exception_handlers.py
    - tests/unit/test_create_user_precedence.py
    - tests/unit/test_claim_precedence.py
    - tests/unit/test_claim_precedence_registered.py

key-decisions:
  - "`runtime` is the last parameter of `get_claims`, after `credential`, so the two `Depends()` defaults read in declaration order"
  - "The `ty` count rose by one and no suppression was added; the new diagnostic is the pre-existing `TestClient.app` weakness, not D-04"
  - "The signature-pinning case in `test_identity_accessors.py` was updated, not deleted: it is what pins that `get_claims` keeps its `Request`"

requirements-completed: []

coverage:
  - id: D1
    description: "`get_db`, `get_identity`, `get_claims` and `get_quota_service` reach the session factory and the verifier through `Depends(get_runtime)`, never through `request.app.state` (D-01)"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn 'get_session_factory\\|state.session_factory\\|state.jwt_verifier' src tests --include='*.py')\""
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestAccessorsCannotProvision::test_each_accessor_declares_the_parameters_its_own_work_needs"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e"
        status: pass
    human_judgment: false
  - id: D2
    description: "`get_session_factory` is deleted and `get_claims` keeps its `Request` for the authorization header alone"
    verification:
      - kind: other
        ref: "grep -n 'def get_session_factory' src/nativespeaker/api/app/dependencies.py — no match"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestNoCredentialIsRefused::test_no_authorization_header_answers_auth_required"
        status: pass
      - kind: unit
        ref: "tests/unit/test_auth_security.py#TestBearerTokenEdgeCases"
        status: pass
    human_judgment: false
  - id: D3
    description: "The nested e2e fixtures swap the container field, not the container, so no inner swap is reverted (threat T-50-04-03)"
    verification:
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e — 361 passed"
        status: pass
    human_judgment: false
  - id: D4
    description: "`opened_sessions` stays a plain `app.state` attribute and the lifespan never builds it"
    verification:
      - kind: other
        ref: "grep -c 'opened_sessions' tests/unit/test_identity_accessors.py — 4, unchanged"
        status: pass
      - kind: other
        ref: "grep -c 'opened_sessions' src/nativespeaker/api/app/lifespan.py — 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "The `ty` diagnostic count is re-measured against the 295 baseline and recorded, not copied"
    verification:
      - kind: other
        ref: ".venv/bin/ty check — Found 296 diagnostics, read from this run's own output"
        status: pass
    human_judgment: false

duration: 14 min
completed: 2026-09-18
status: complete
---

# Phase 50 Plan 04: The session factory and the verifier move into the container Summary

**Every session and every token check is now served off `Runtime`; `get_session_factory` is gone, and `app.state` carries two fewer lifespan-built attributes.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-09-18T08:23:00Z
- **Completed:** 2026-09-18T08:37:34Z
- **Tasks:** 2
- **Files created or modified:** 11

## Accomplishments

- `get_db` and `get_identity` drop `request: Request` and take `runtime: Runtime = Depends(get_runtime)`. Each opens `runtime.session_factory()`.
- `get_claims` takes the container too and calls `runtime.jwt_verifier.verify` through `run_in_threadpool`. It keeps `request: Request`, for `request.headers.get("authorization")` alone.
- `get_session_factory` is deleted, with the `async_sessionmaker` import it was the last user of in that file.
- `get_quota_service` takes the container and passes `session_factory=runtime.session_factory`. Its comment about the charge committing in its own session is unchanged.
- The lifespan drops `app.state.session_factory` and `app.state.jwt_verifier`. Both locals stay and still feed the one `Runtime(...)` call.
- `_db_transaction` and `stub_verifier` in `tests/e2e/conftest.py` read and write through `state.runtime`. Each saves the field value, replaces the field, and restores the field.
- Eight unit files build one `app.state.runtime = make_runtime(...)` each, naming only the fields that file reads.
- `tests/unit/test_identity_accessors.py` keeps `app.state.opened_sessions` exactly as it was, at four occurrences.

## Task Commits

1. **Task 1: the session factory and the verifier move into the container** — `5ea5371`
2. **Task 2: re-measure the `ty` baseline** — no commit; the measurement needed no file change (see Deviations).

## Files Created/Modified

- `src/nativespeaker/api/app/dependencies.py` — four dependency signatures rewritten, `get_session_factory` and the `async_sessionmaker` import deleted.
- `src/nativespeaker/api/app/lifespan.py` — two `app.state` assignments deleted.
- `tests/e2e/conftest.py` — `replace` imported; `_db_transaction` and `stub_verifier` swap the container field.
- `tests/unit/test_identity_accessors.py` — `_client` builds one container; the mid-test verifier swap uses `replace`; the signature-pinning case reads the new parameter lists.
- `tests/unit/test_jwks_offload.py`, `test_app_wiring.py`, `test_auth_security.py` — one `make_runtime(jwt_verifier=..., session_factory=...)` each.
- `tests/unit/test_exception_handlers.py`, `test_create_user_precedence.py`, `test_claim_precedence.py`, `test_claim_precedence_registered.py` — one `make_runtime(session_factory=...)` each.

## Decisions Made

- `runtime` is declared last in `get_claims`, after `credential`. Both are `Depends()` defaults, and the plan's own artifact line writes them in that order.
- The e2e fixtures save the field value, never the container. `_db_transaction` is `autouse`, so `stub_verifier`, `scripted_firebase_adapter` and the other five nest inside it. A saved whole container restored on the way out would have reverted every inner swap made after it was saved.
- No `# ty: ignore` was added anywhere. The one added diagnostic is `unresolved-attribute` on `TestClient.app.state`, which the same file already carries four times and the repository does not suppress. Suppressing it would have hidden a pre-existing weakness to make a number match.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A signature-pinning case the plan did not list**

- **Found during:** Task 1
- **Issue:** `tests/unit/test_identity_accessors.py:282` asserts the exact parameter lists of both accessors: `["request", "credential"]` and `["request", "claims"]`. D-01 changes both. The plan named the file but listed only lines 105-135 and 215-235 to read, so this case at line 280 was not in the plan's picture. It failed on the first unit run.
- **Fix:** Updated the two assertions to `["request", "credential", "runtime"]` and `["runtime", "claims"]`, and rewrote both failure messages. The case was kept, not deleted: it is now the thing that pins the second half of D-01, that `get_claims` keeps its `Request` while `get_identity` does not.
- **Files modified:** `tests/unit/test_identity_accessors.py`
- **Verification:** `.venv/bin/pytest -q -p no:cacheprovider` — 1894 passed, exit 0.
- **Commit:** `5ea5371`

### Task 2 produced no file change

The task's `<files>` line reads "tests/unit/test_create_user_precedence.py (and any unit test file a new diagnostic names)". No new diagnostic names any file, so nothing was edited and Task 2 has no commit of its own. Its deliverable is the measurement below, which lands in this summary's commit. This is the task's own instruction followed, not a skipped task: it says to add a suppression only "where a new diagnostic names a deliberately wrong-typed test value".

---

**Total deviations:** 1 auto-fixed. **Impact on plan:** none on any acceptance criterion. The fixed case now asserts D-01 rather than contradicting it.

## The `ty` measurement

| Reading | Count |
|---|---|
| Research baseline at HEAD (`50-RESEARCH.md` line 225) | 295 |
| Measured after `5ea5371`, read from `.venv/bin/ty check` output | **296** |
| Delta | **+1** |

The rule tally at 296 is: 171 `invalid-argument-type`, 80 `unresolved-attribute`, 22 `ignore-comment-unknown-rule`, 9 `missing-argument`, 4 `unused-ignore-comment`, 4 `invalid-return-type`, 3 `invalid-assignment`, 2 `no-matching-overload`, 1 `unsupported-operator`.

Where the one came from: `test_identity_accessors.py:226` was `client.app.state.jwt_verifier = _UnlabelledVerifier()`, one `client.app.state` read and one diagnostic. It is now `client.app.state.runtime = replace(client.app.state.runtime, ...)`, two reads on one line and two diagnostics. `ty` cannot see `state` on `TestClient.app`; the same file carried four of these before this plan and carries six now.

Assumption A3 held. `grep 'session_factory'` over the whole `ty` output returns nothing, so D-04's `async_sessionmaker[SQLModelAsyncSession]` annotation added no diagnostic at any lambda session factory in the unit tests. The `+1` is unrelated to the annotation.

## Issues Encountered

None beyond the deviation above. The unit suite stayed at 1894 cases: this plan added and removed none.

## Threat Notes

- **T-50-04-01** (spoofing at `get_claims`): the verifier moved from an attribute read to a container field and nothing else changed. The `credential is None` split, the `claims is None` guard, the `BoundedReason` mapping and the `run_in_threadpool` offload are carried over line for line. `tests/unit/test_auth_security.py` and `tests/unit/test_jwks_offload.py` both pass.
- **T-50-04-02** (elevation at `get_identity`): the `PreAuthIdentityNotAllowed` raise on an unresolved pair is unchanged. `tests/unit/test_identity_accessors.py` passes, including the 403 case and the two-direction narrowing cases.
- **T-50-04-03** (tampering through nested e2e fixtures): both rewritten fixtures save the field and replace the field, reading the then-current container on the way in and on the way out. The `-m e2e` run passes at 361, the same count as after plan 50-03, and `stub_verifier` nests inside the `autouse` `_db_transaction`.
- **T-50-04-SC**: no package was installed or upgraded. `uv.lock` is untouched.

## Verification Results

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` | 1894 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m e2e` | 361 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m schema` | 297 passed, exit 0 |
| `.venv/bin/ruff check src tests` | All checks passed! |
| `.venv/bin/ty check` | Found 296 diagnostics, exit read for the count |
| `test -z "$(grep -rn 'get_session_factory\|state.session_factory\|state.jwt_verifier' src tests --include='*.py')"` | empty, exit 0 |
| `get_db`, `get_identity`, `get_quota_service` declare a `request` parameter | no |
| `grep -c 'opened_sessions' tests/unit/test_identity_accessors.py` | 4, unchanged |
| `git diff --diff-filter=D --name-only HEAD~1 HEAD` | empty, no file deleted |

One acceptance criterion is reported as written rather than as passed. The plan asks that `grep -c 'Request' src/nativespeaker/api/app/dependencies.py` count "only `get_runtime` and `get_claims` plus the import". It counts 12 lines, because `get_firebase_adapter`, `get_devicecheck_adapter`, `get_restore_service` and the two webhook verifiers still take a `Request`, and `AppStoreNotificationRequest` and `PubSubPushRequest` contain the word. Those five are plans 50-05 and 50-06. The operative half of the criterion, that `get_db`, `get_identity` and `get_quota_service` declare no `request`, holds.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Criterion 5 is now half done. `get_config` went in 50-03 and `get_session_factory` goes here. `get_firebase_adapter` and `get_devicecheck_adapter` remain, for plan 50-05.
- `dependencies.py` holds 10 `request.app.state` reads, down from 14 after plan 50-03.
- Criterion 6: `tests/e2e/conftest.py` is the one test file left that sets a lifespan-built attribute on `app.state`, across six fixtures — the firebase and devicecheck adapters, the two store classes, and one `config` read. No unit file sets one any more. `opened_sessions` is not a lifespan attribute and stays.
- The `replace`-the-field pattern is now proven in the e2e suite under nesting. Plans 50-05 and 50-06 apply it to the five remaining fixtures with no new argument to settle.

## Self-Check: PASSED

- `src/nativespeaker/api/app/dependencies.py` — FOUND
- `src/nativespeaker/api/app/lifespan.py` — FOUND
- `tests/e2e/conftest.py` — FOUND
- `tests/unit/test_identity_accessors.py` — FOUND
- `tests/unit/test_jwks_offload.py` — FOUND
- `tests/unit/test_app_wiring.py` — FOUND
- `tests/unit/test_auth_security.py` — FOUND
- `tests/unit/test_exception_handlers.py` — FOUND
- `tests/unit/test_create_user_precedence.py` — FOUND
- `tests/unit/test_claim_precedence.py` — FOUND
- `tests/unit/test_claim_precedence_registered.py` — FOUND
- commit `5ea5371` — FOUND
- Both tasks' `<acceptance_criteria>` re-run after the commit — PASS
- The plan `<verification>` block re-run after the commit — PASS

---
*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Completed: 2026-09-18*
