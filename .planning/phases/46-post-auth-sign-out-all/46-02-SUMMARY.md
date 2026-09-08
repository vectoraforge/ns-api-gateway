---
phase: 46-post-auth-sign-out-all
plan: 02
subsystem: testing
tags: [pytest, fastapi, ast, protocol, structlog]

# Dependency graph
requires:
  - phase: 46-post-auth-sign-out-all
    provides: "plan 46-01's `revoke_refresh_tokens` on the Protocol and the seam, `RevocationUnconfirmed`, and the `/auth/sign-out-all` route"
  - phase: 37.3-post-auth-error-tree
    provides: "`EVENT_NAMES` and `CONSTRUCTOR_ARGUMENTS`, the recorded rejection vocabulary and its constructor table"
provides:
  - "The Protocol method-set literal reads `{get_user_provider_data, revoke_refresh_tokens}`, and the case name and class docstring say two methods"
  - "Two cases pinning `revoke_refresh_tokens`: a `None` return annotation and an `issuer` parameter"
  - "The auth-package ratchet at the measured `(8, 24, 64)`"
  - "`revocation_unconfirmed` in `EVENT_NAMES` and `RevocationUnconfirmed` in `CONSTRUCTOR_ARGUMENTS`"
  - "`/auth/sign-out-all` in both narrowed-route parametrize tuples"
  - "`TestTheSignOutRouteOpensNoSession`, the one case proving the handler declares no `get_db` (D-04)"
affects: [46-03, 46-04, 46-05]

actuals:
  tokens: 10938
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A recorded literal is re-written together with the name and docstring that describe it, so no case survives claiming the pre-phase shape"
    - "Route-level narrowing is proven by `_declared`, which names only what the route resolved, so an absent `get_db` is the whole proof of no session"

key-files:
  created: []
  modified:
    - tests/unit/test_adapter_interfaces.py
    - tests/unit/test_auth_package_shape.py
    - tests/unit/test_rejection_vocabulary.py
    - tests/unit/test_app_wiring.py

key-decisions:
  - "The ratchet's third element is `64`, read from the failing run's own text (`assert (8, 24, 64) == (8, 24, 59)`), never derived from the plan."
  - "The revocation gets two cases, not one: the read's return-annotation case and its issuer-parameter case are the model the plan names, and the file keeps one assertion per case."
  - "The no-session case is its own class, `TestTheSignOutRouteOpensNoSession`, so its docstring can name D-04; the file already carries one-case classes."
  - "`revocation_unconfirmed` sits between `unavailable` and `not_linked`, the order `errors.py` declares the leaves in."
  - "`RevocationUnconfirmed`'s constructor entry reuses the `Unavailable` stage string `issuer_selection`, a stage the leaf really raises with."

patterns-established:
  - "The recorded-shape files are re-written in one commit per plan, so a reader sees the whole new shape at one revision."

requirements-completed: [SIGNOUT-01, SIGNOUT-02]

coverage:
  - id: D1
    description: "The recorded Protocol method set names both seam calls, so the second Firebase Admin call is declared, not smuggled (D-01)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py#TestFirebaseAdminAdapter::test_it_declares_exactly_the_two_surviving_methods"
        status: pass
    human_judgment: false
  - id: D2
    description: "`revoke_refresh_tokens` returns nothing and takes the issuer, so confirmation is the return itself and selection is per call."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py#TestFirebaseAdminAdapter::test_revoke_refresh_tokens_returns_nothing_at_all"
        status: pass
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py#TestFirebaseAdminAdapter::test_the_revocation_method_takes_the_issuer_so_selection_is_per_call"
        status: pass
    human_judgment: false
  - id: D3
    description: "The auth-package ratchet counts the four new functions rather than being switched off (T-46-11)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_package_shape.py#TestThePackageShrank::test_it_still_measures_the_recorded_current_shape"
        status: pass
    human_judgment: false
  - id: D4
    description: "The recorded rejection vocabulary names `revocation_unconfirmed`, so the new refusal is an admitted one (D-05)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_rejection_vocabulary.py#TestTheEventVocabularyIsWrittenDown::test_the_tree_spells_exactly_the_recorded_event_names"
        status: pass
      - kind: unit
        ref: "tests/unit/test_rejection_vocabulary.py#TestEveryLeafKeepsItsLogFieldsToPlainScalars::test_every_class_in_the_tree_contributes_only_scalars[RevocationUnconfirmed]"
        status: pass
    human_judgment: false
  - id: D5
    description: "The recorded route inventory names `/auth/sign-out-all` in both wiring lists, so the route is pinned as narrowed (T-46-05, D-04)."
    requirement: SIGNOUT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestEveryRouteIsAuthenticated::test_a_narrowed_route_declares_the_linked_identity_narrowing[/auth/sign-out-all]"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestEveryRouteIsAuthenticated::test_a_narrowed_route_is_in_neither_exemption_set[/auth/sign-out-all]"
        status: pass
    human_judgment: false
  - id: D6
    description: "The handler declares no database session, which is the whole proof of D-04."
    requirement: SIGNOUT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheSignOutRouteOpensNoSession::test_sign_out_all_declares_no_database_session"
        status: pass
    human_judgment: false
  - id: D7
    description: "The whole unit suite is green after the four hand-written literals are re-written."
    requirement: SIGNOUT-01
    verification:
      - kind: unit
        ref: "uv run pytest -q (1261 passed, 0 failed)"
        status: pass
    human_judgment: false

duration: 7 min
completed: 2026-09-08
status: complete
---

# Phase 46 Plan 02: The recorded shape after the revocation Summary

**The four hand-written literals now record the auth package plan 46-01 built — two Protocol methods, a
ratchet of `(8, 24, 64)`, `revocation_unconfirmed` in the vocabulary, and `/auth/sign-out-all` in both
narrowed-route lists — and one new case proves the handler declares no database session.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-08T23:05:30Z
- **Completed:** 2026-09-08T23:13:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- The unit suite is green again: 1261 passed, 0 failed. The four cases plan 46-01 left red by
  construction are all re-written, and no case, name or docstring still describes the pre-phase shape.
- The ratchet was re-measured, not guessed. The failing run printed `assert (8, 24, 64) == (8, 24, 59)`
  and `64` is the number written down, which is what T-46-11 asks for: the ratchet keeps counting.
- `/auth/sign-out-all` joins both narrowed-route parametrize tuples, so the route-level
  `Depends(get_linked_identity)` plan 46-01 wrote is now asserted by name rather than by the generic
  case alone (T-46-05).
- One line proves D-04: `get_db not in _declared(_route_at("/auth/sign-out-all"))`. `_declared` names
  only the callables the route itself resolved, so the barrier's own short session is not counted and
  no fixture is needed. Research Q3 rejected a session stand-in for this reason.
- The suite grew by five cases: two on the Protocol's revocation method, two parametrize instances on
  the new path, and the no-session case.

## Task Commits

Each task was committed atomically:

1. **Task 1: The three recorded-shape literals** - `4fe0299` (test)
2. **Task 2: The route inventory and the no-session case** - `e2fcbcc` (test)

**Plan metadata:** `docs(46-02): complete the recorded shape plan`, the commit carrying this file.

## Files Created/Modified

- `tests/unit/test_adapter_interfaces.py` - the method-set literal is both names; the case is renamed
  `test_it_declares_exactly_the_two_surviving_methods`; `TestFirebaseAdminAdapter`'s docstring reads
  "Two methods"; two new cases pin the revocation's `None` return and its `issuer` parameter
- `tests/unit/test_auth_package_shape.py` - `CURRENT = (8, 24, 64)`, the measured triple
- `tests/unit/test_rejection_vocabulary.py` - `revocation_unconfirmed` in `EVENT_NAMES`, between
  `unavailable` and `not_linked`; `RevocationUnconfirmed: ((), {"stage": "issuer_selection"})` in
  `CONSTRUCTOR_ARGUMENTS`, on the `Unavailable` model
- `tests/unit/test_app_wiring.py` - `/auth/sign-out-all` in both parametrize tuples; the new
  `TestTheSignOutRouteOpensNoSession` class and its one case

## Decisions Made

- **Two cases for the revocation, not one.** The plan's action names "the two cases that already do
  this for the read" as the model, and the file keeps one assertion per case. The acceptance criterion
  is met in substance: one case asserts the `None` return annotation, one asserts the `issuer`
  parameter.
- **The no-session case is its own class.** `TestTheSignOutRouteOpensNoSession` carries a docstring
  naming D-04. Folding the case into `TestEveryRouteIsAuthenticated` would have put a
  session-declaration fact under an authentication docstring.
- **`issuer_selection` is the constructor's stage string.** It is one of the three stages plan 46-01
  really raises `RevocationUnconfirmed` with, so the constructed sample is a real one.
- **`TestTheLookupArmsCarryStageAndOnlyABoundedCause`'s three-arm parametrize was left alone.** It is a
  hand-picked sample of three arms, not a totality walk, and it is green. Per-outcome status
  assertions for the revocation are plan 46-03's, not this plan's.

## Deviations from Plan

None - plan executed exactly as written.

The three loose-grep risks the 46-01 handoff flagged did not fire. Each gate in this plan was already
written to match what it means: `grep -c 'revocation_unconfirmed' = 1` counts the one event-name
literal (the constructor entry spells `RevocationUnconfirmed`, which does not match), and the two
`>=` gates on `revoke_refresh_tokens` and `/auth/sign-out-all` count 4 and 3.

**Total deviations:** 0
**Impact on plan:** None. Every change is a test literal; no file under `src/` appears in either commit.

## Issues Encountered

None.

## Verification Results

| Gate | Result |
|---|---|
| `uv run pytest tests/unit/test_adapter_interfaces.py test_auth_package_shape.py test_rejection_vocabulary.py -q` | 147 passed |
| `grep -c 'revocation_unconfirmed' tests/unit/test_rejection_vocabulary.py` = 1 | pass |
| `grep -c 'revoke_refresh_tokens' tests/unit/test_adapter_interfaces.py` >= 2 | pass (4) |
| `uv run pytest -q` | 1261 passed, 0 failed |
| `grep -c '/auth/sign-out-all' tests/unit/test_app_wiring.py` >= 3 | pass (3) |
| `uv run ruff check src tests` | clean |
| No file under `src/` in this plan's commits | pass — `git diff --name-only 4fe0299^..e2fcbcc` is four `tests/unit/` paths |
| No file deleted by either commit | pass |

### Prohibitions

| Statement | Status |
|---|---|
| A ratchet number must be read from the failing run, never guessed and never derived from a plan. | verified — the run printed `(8, 24, 64)` before the edit |
| A case name or a docstring must not survive the edit still claiming the pre-phase shape. | verified — the case name and the class docstring were re-written with the literal |
| No source file under `src/` is edited by this plan; every change is a test literal. | verified — both commits touch `tests/unit/` only |

## Known Stubs

None. Nothing in this plan returns a placeholder value or a hardcoded empty answer.

## Threat Flags

None. This plan adds no surface: it edits four test files and imports nothing new.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**For 46-04 (same wave, runs next):** the unit suite is green, so 46-04 starts from a clean run and any
failure it sees is its own. `revoke_refresh_tokens` now has three assertions on the Protocol
(`test_adapter_interfaces.py`), so 46-04 need not re-assert the seam's declaration — only its behaviour.
The auth-package ratchet is at `(8, 24, 64)`: any plan that adds a function, a method or a class under
`src/nativespeaker/api/auth/` must re-measure and re-write `CURRENT` in
`tests/unit/test_auth_package_shape.py`, and both 46-04 and 46-03 should expect that.

**For 46-03 (Wave 3):** the per-outcome status assertions are still unwritten.
`TestTheLookupArmsCarryStageAndOnlyABoundedCause` at `tests/unit/test_rejection_vocabulary.py:212`
parametrizes three arms — `user_not_found`, `unavailable`, `not_linked` — and does not name
`RevocationUnconfirmed`. It is green because the list is a sample, not a walk. If 46-03 wants the 503
asserted beside its siblings, that is the list to join. `EVENT_NAMES` and `CONSTRUCTOR_ARGUMENTS` are
already correct and need no further edit.

`tests/unit/test_app_wiring.py` now names `/auth/sign-out-all` in three places: both parametrize tuples
and the no-session case. Any later plan that renames the path has to change all three.

---
*Phase: 46-post-auth-sign-out-all*
*Completed: 2026-09-08*

## Self-Check: PASSED

All four modified test files exist on disk. Both task commits (`4fe0299`, `e2fcbcc`) are in the log.
Every plan-level gate was re-run after the last task commit and all are green.
