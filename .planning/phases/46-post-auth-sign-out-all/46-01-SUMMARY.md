---
phase: 46-post-auth-sign-out-all
plan: 01
subsystem: auth
tags: [firebase-admin, tenacity, fastapi, structlog, revocation]

# Dependency graph
requires:
  - phase: 37-post-auth-foundation
    provides: the issuer-keyed Admin apps dict, `run_in_threadpool`, the tenacity policy and `RetryableLookupError`
  - phase: 37.3-post-auth-error-tree
    provides: `ProviderLookupError` and its leaves, `app_error_handler`'s class-name event rule
  - phase: 45-post-auth-restore-subscription
    provides: the e2e client-plus-stub-verifier shape and the `seed_identity` fixture
provides:
  - "`POST /auth/sign-out-all`, the eighth auth route, 204 on a confirmed revocation"
  - "`FirebaseAdminAdapter.revoke_refresh_tokens` on the Protocol and on `FirebaseAdminLookup`"
  - "`FirebaseAdminLookup._revoke`, the synchronous body with its four ordered arms"
  - "`revoke_with_retry` and `_revocation_exhausted`, the revocation's own retry tier"
  - "`RevocationUnconfirmed`, 503 `verification_temporarily_unavailable`"
  - "`FakeFirebaseAdapter.revoke_refresh_tokens`, `.script_revocation`, `.revoke_answer`, `.revoke_calls`"
  - "`tests/e2e/test_sign_out_all.py` with its `_LogSpy` and `_spy_on` helpers"
affects: [46-02, 46-03, 46-04, 46-05]

actuals:
  tokens: 14259
  tasks: 1
  commits: 1

tech-stack:
  added: []
  patterns:
    - "A second seam method beside its twin, with its own exhaustion leaf rather than a shared wrapper"
    - "An INFO line naming the identity row and nothing else, on the `UpgradeRefused.log_fields` precedent"

key-files:
  created:
    - tests/e2e/test_sign_out_all.py
  modified:
    - src/nativespeaker/api/auth/adapters.py
    - src/nativespeaker/api/auth/firebase.py
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/routers/auth.py
    - tests/unit/conftest.py

key-decisions:
  - "The revocation's `ValueError` arm is definitive, not retryable: the SDK validates the uid before it sends the request, so another attempt answers the same (D-02, D-05)."
  - "`_revocation_exhausted` is its own callback: an exhausted revocation budget must raise `RevocationUnconfirmed`, and reusing `_exhausted` would raise `Unavailable` with a byte-identical wire answer that no test could see."
  - "`RevocationUnconfirmed` shares `verification_temporarily_unavailable` at 503 with `Unavailable`; the totality walk rejects one code at two statuses, not one code at one status."
  - "The handler declares `get_linked_identity` and `get_firebase_adapter` only: it opens no session and issues no statement (D-04)."
  - "The plan's `grep -c 'auth/sign-out-all' = 1` gate was replaced by a registration-count gate; the loose pattern also counts the module docstring the same plan mandates."

patterns-established:
  - "Twin seam methods: the revocation mirrors the read arm for arm, and each keeps its own exhaustion leaf so the log event name separates them."
  - "A confirmed side effect is proven by the whole call list and the whole log-entry list, never by a length."

requirements-completed: [SIGNOUT-01, SIGNOUT-02]

coverage:
  - id: D1
    description: "A confirmed revocation answers 204 with an empty body over the real router."
    requirement: SIGNOUT-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#test_a_confirmed_revocation_answers_204_with_an_empty_body"
        status: pass
    human_judgment: false
  - id: D2
    description: "The route makes exactly one revocation call, for the request-verified issuer and subject."
    requirement: SIGNOUT-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#test_it_makes_exactly_one_revocation_call_for_the_verified_pair"
        status: pass
    human_judgment: false
  - id: D3
    description: "One INFO record, event `sign_out_all_confirmed`, carrying `identity_row_id` and nothing else."
    requirement: SIGNOUT-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#test_it_writes_one_info_record_carrying_the_row_id_alone"
        status: pass
    human_judgment: false
  - id: D4
    description: "The seam selects the Admin app by issuer, passes `app=` explicitly, and fails closed with no call on an unconfigured issuer."
    requirement: SIGNOUT-02
    verification: []
    human_judgment: true
    rationale: "Written in this plan and read-verified, but the selection and no-call cases are plan 46-02's unit twins; nothing asserts them yet."
  - id: D5
    description: "Every unconfirmed outcome raises `RevocationUnconfirmed` (503) and a Firebase 'no such user' raises `UserNotFound` (401)."
    requirement: SIGNOUT-02
    verification: []
    human_judgment: true
    rationale: "The arms and the exhaustion callback are written and read-verified; the per-outcome and attempt-count assertions are plans 46-02 and 46-03."
  - id: D6
    description: "The handler declares no database session, so it opens none after the barrier."
    requirement: SIGNOUT-02
    verification:
      - kind: other
        ref: "test \"$(grep -v '^ *#' src/nativespeaker/api/routers/auth.py | grep -c 'get_db')\" = \"2\""
        status: pass
    human_judgment: false

duration: 6 min
completed: 2026-09-08
status: complete
---

# Phase 46 Plan 01: End-to-end sign-out-all Summary

**`POST /auth/sign-out-all` answers 204 only after `firebase_admin.auth.revoke_refresh_tokens` returns, through a
second seam method whose own exhaustion leaf, `RevocationUnconfirmed`, answers 503 for everything else.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-09-08T22:57:11Z
- **Completed:** 2026-09-08T23:03:00Z
- **Tasks:** 1 (tracer)
- **Files modified:** 6 (5 modified, 1 created)

## Accomplishments

- The whole revocation path traces end to end: the Protocol method, the seam method, the synchronous
  body, the retry tier, the error leaf, the route and the fake all landed in one commit, and a
  confirmed revocation answers 204 over the real router.
- The two known mirroring mistakes were avoided by construction. `auth.UserNotFoundError` is listed
  before the `exceptions.FirebaseError` it subclasses, so the 401 arm is reachable; and the
  `ValueError` arm raises `RevocationUnconfirmed`, not `RetryableLookupError`, because the SDK
  checks the uid before it sends the request.
- `_revocation_exhausted` is a separate callback from `_exhausted`, so an exhausted revocation budget
  is found in the logs under `revocation_unconfirmed` rather than hiding behind `unavailable` at an
  identical 503.
- The route declares `get_linked_identity` and `get_firebase_adapter` only. `get_db` still appears
  exactly twice in the module, which is the count it carried before this phase.

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end sign-out-all — the confirmed path only** - `8952504` (feat)

**Plan metadata:** `docs(46-01): complete end-to-end sign-out-all plan`, the commit carrying this file.

## Files Created/Modified

- `src/nativespeaker/api/auth/adapters.py` - the `revoke_refresh_tokens` line on the `FirebaseAdminAdapter` Protocol; no new import and no new value type
- `src/nativespeaker/api/auth/firebase.py` - `revoke_refresh_tokens`, `_revoke`, `_revocation_exhausted` and `revoke_with_retry`
- `src/nativespeaker/api/errors.py` - `RevocationUnconfirmed(ProviderLookupError)`, 503 `verification_temporarily_unavailable`; `ErrorCode` unedited
- `src/nativespeaker/api/routers/auth.py` - the eighth route, and the module docstring re-written to name eight routes in three lines
- `tests/unit/conftest.py` - `FakeFirebaseAdapter` gains `revoke_answer`, `revoke_calls`, `script_revocation` and `revoke_refresh_tokens`
- `tests/e2e/test_sign_out_all.py` - the confirmed 204, the single recorded call, and the single INFO record

## Decisions Made

- **The stage strings** (Claude's discretion under D-01): `issuer_selection` for no app, `subject_rejected`
  for the SDK's own uid refusal, and `token_revocation` for both the 401 arm and the exhausted budget.
- **`FirebaseAdminLookup` keeps its name.** The rename stays deferred, as CONTEXT.md permits.
- **Two wrappers, not one generic wrapper.** A shared wrapper would need its exhaustion callback passed
  in at each call site, and a comment at each site to say which leaf it raises.
- **The INFO event name is `sign_out_all_confirmed`**, unchanged from the plan's suggestion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The `auth/sign-out-all` verify gate is unsatisfiable as written**

- **Found during:** Task 1 (the verify run)
- **Issue:** The gate `test "$(grep -c 'auth/sign-out-all' src/.../routers/auth.py)" = "1"` reports 2 and
  fails. The same task requires the module docstring to name `/auth/sign-out-all`, so the literal appears
  once in the docstring and once in the decorator. This is systematic, not new: `grep -c 'auth/sync'` on
  the same file also reports 2, and has since Phase 38. The gate's own `fails_when` names the condition it
  means to catch — "the route path is absent or registered twice" — and a docstring mention is not a
  registration.
- **Fix:** The gate was run as `test "$(grep -c '@router.post("/auth/sign-out-all"' src/.../routers/auth.py)" = "1"`,
  which measures registrations. It passes. The docstring was left naming the route in the same
  `/auth/...` form as the other seven, because a docstring bent to satisfy a loose grep would be the
  symptom fix, not the cause fix.
- **Files modified:** none — this is a correction to the plan's verification, not to the code.
- **Verification:** `@router.post("/auth/sign-out-all"` appears exactly once; `/auth/sign-out-all` appears
  twice, in the docstring and the decorator, and both were read.
- **Committed in:** n/a (verification-only)

**2. [Rule 1 - Bug] The `firebase.py` module docstring claimed one adapter method**

- **Found during:** Task 1
- **Issue:** Line 1 read "one named app per issuer, one adapter method, never a [DEFAULT] app". After this
  plan the module holds two adapter methods, so the claim was stale the moment `revoke_refresh_tokens`
  landed. Pitfall 5 is the same failure mode one file over; the plan named it for `routers/auth.py` only.
- **Fix:** "one adapter method" became "two adapter methods". The docstring stays three lines.
- **Files modified:** `src/nativespeaker/api/auth/firebase.py`
- **Verification:** `uv run pytest tests/unit/test_docstring_bar.py -q` green, baseline still 0.
- **Committed in:** `8952504` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** No scope change. One is a verification correction, one is a one-word stale claim in a
docstring the plan already required to be true elsewhere.

## Issues Encountered

None. The plan's own scope note is holding as written: four hand-written unit literals now fail by
construction, and the unit suite is red between this plan and 46-02 by design.

## Verification Results

| Gate | Result |
|---|---|
| `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | 3 passed |
| `grep -c 'def revoke_refresh_tokens' auth/firebase.py` = 1 | pass |
| `grep -c 'revoke_refresh_tokens' auth/adapters.py` = 1 | pass |
| `grep -c 'class RevocationUnconfirmed' errors.py` = 1 | pass |
| route registered exactly once (corrected gate, deviation 1) | pass |
| `get_db` count in `routers/auth.py` = 2 | pass |
| `uv run pytest tests/unit/test_docstring_bar.py test_error_contract.py test_error_registry.py -q` | 73 passed |
| `uv run ruff check src tests` | clean |
| `sha256sum -c` on the two files under `specs/auth-refactor-phases/` | pass, both unchanged |

The tracer feedback gate re-ran every one of these after the task commit. All green.

## Known Stubs

None. Nothing in this plan returns a placeholder value or a hardcoded empty answer.

## Threat Flags

None. The route adds no surface outside the `<threat_model>`: it reads no table, writes no row, takes
no request body, and its one new outbound call is the Firebase revocation the register already names.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Wave 2 (plans 46-02 and 46-04) is unblocked. Every name those plans assert against now exists.

**Four unit literals are red by construction, as the plan predicted. Plan 46-02 owns all four:**

1. `tests/unit/test_adapter_interfaces.py::test_it_declares_exactly_the_one_surviving_method` — the
   method set is now `{"get_user_provider_data", "revoke_refresh_tokens"}`. The case name and the class
   docstring both still say "one method".
2. `tests/unit/test_auth_package_shape.py:13` — measured `(8, 24, 64)` against the recorded
   `CURRENT = (8, 24, 59)`. Use the measured triple; do not guess it.
3. `tests/unit/test_rejection_vocabulary.py::test_the_tree_spells_exactly_the_recorded_event_names` —
   `EVENT_NAMES` needs `revocation_unconfirmed`.
4. `tests/unit/test_rejection_vocabulary.py::test_every_class_in_the_tree_contributes_only_scalars[RevocationUnconfirmed]` —
   `CONSTRUCTOR_ARGUMENTS` needs an entry on the `Unavailable` model: `((), {"stage": "issuer_selection"})`.

`tests/unit/test_app_wiring.py` is **green**, not red: its two narrowed-route lists are additive, so the
absent path fails nothing today. Plan 46-02 must still add `/auth/sign-out-all` to both lists, or the
route-level narrowing this plan wrote goes unasserted.

Nothing else in the suite was run by this plan. `uv run pytest -q` is not a gate here and stays red until
46-02 lands.

---
*Phase: 46-post-auth-sign-out-all*
*Completed: 2026-09-08*

## Self-Check: PASSED

All seven listed files exist on disk. Both commits (`8952504`, and this metadata commit) are in the log. The working
tree is clean, so nothing this plan produced was left untracked.
