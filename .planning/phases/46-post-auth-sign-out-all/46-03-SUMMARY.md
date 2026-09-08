---
phase: 46-post-auth-sign-out-all
plan: 03
subsystem: testing
tags: [pytest, firebase-admin, tenacity, monkeypatch]

# Dependency graph
requires:
  - phase: 46-post-auth-sign-out-all
    provides: "plan 46-01's `revoke_refresh_tokens`, `_revoke`, `revoke_with_retry`, `_revocation_exhausted` and `RevocationUnconfirmed`"
  - phase: 46-post-auth-sign-out-all
    provides: "plan 46-02's re-written unit literals, without which `uv run pytest -q` could not be green"
  - phase: 37-post-auth-foundation
    provides: "`get_user_calls`, `CountingAdapter` and the `DEFINITIVE` table — the two models these cases twin"
provides:
  - "`revoke_calls`, the revocation twin of `get_user_calls`, recording `{uid, app}` off a monkeypatched `auth.revoke_refresh_tokens`"
  - "`TestTheRevocation`: the explicit `app=`, the confirmed `None`, and the four raising arms"
  - "`CountingRevoker` and `REVOCATION_DEFINITIVE`, the revocation's attempt-count fake and its four one-attempt outcomes"
  - "`TestTheRevocationWrapper`: the exhaustion leaf asserted by class, not by status"
affects: [46-05]

actuals:
  tokens: 3174
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A fail-closed leaf that shares a status and a code with another leaf is asserted by class, and by a negative isinstance against the leaf it could be confused with"
    - "An attempt count is proven by a scripted fake whose overrun is its own AssertionError, so an extra call fails loudly rather than passing quietly"

key-files:
  created: []
  modified:
    - tests/unit/test_firebase_adapter.py
    - tests/unit/test_firebase_retry.py

key-decisions:
  - "The revocation cases live in their own class rather than joining `TestSelection` and `TestFailureMapping`: one class per seam method keeps the read's arms and the revocation's divergent `ValueError` arm side by side but never interleaved."
  - "`CountingRevoker` is a sibling of `CountingAdapter`, not a subclass: the two fakes share no method name, so no case can call the wrong seam through the wrong wrapper."
  - "The malformed-subject case asserts `not isinstance(raised.value, RetryableLookupError)` explicitly even though `pytest.raises(RevocationUnconfirmed)` already excludes it — the divergence from `_read` is the point of the case, so it is spelled out."
  - "The exhaustion case asserts the class four ways (not `RetryError`, not the marker, is `RevocationUnconfirmed`, not `Unavailable`) and the wire pair is a separate case, so a reused read callback fails on the class line and not on a status line that would still pass."

patterns-established:
  - "Twin fixtures for twin seam methods: `revoke_calls` mirrors `get_user_calls` field for field, so the `app=` proof reads identically for both calls."
  - "A definitive-outcome table is parametrized per wrapper, never shared: the read's table and the revocation's table name different classes and different stages."

requirements-completed: [SIGNOUT-01, SIGNOUT-02]

coverage:
  - id: D1
    description: "A configured issuer's revocation passes that issuer's own app explicitly, so no ambient client is reachable (D-01)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheRevocation::test_a_configured_issuer_passes_its_own_app_explicitly"
        status: pass
    human_judgment: false
  - id: D2
    description: "An unconfigured issuer, and an empty apps mapping, each raise `RevocationUnconfirmed` and call the SDK zero times (D-01, D-05)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheRevocation::test_an_unconfigured_issuer_fails_closed_and_calls_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheRevocation::test_an_empty_mapping_fails_closed_for_every_issuer"
        status: pass
    human_judgment: false
  - id: D3
    description: "A Firebase 'no such user' answer raises `UserNotFound` at 401, and a Firebase error raises the retry marker (D-06)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheRevocation::test_user_not_found_answers_the_401_arm_and_not_the_firebase_error_one"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheRevocation::test_a_firebase_error_is_retryable"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheRevocation::test_a_credential_refresh_failure_is_retryable_and_never_escapes"
        status: pass
    human_judgment: false
  - id: D4
    description: "A malformed subject costs exactly one attempt and raises `RevocationUnconfirmed`, never the retry marker (D-02, D-05)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_adapter.py#TestTheRevocation::test_a_malformed_subject_is_definitive_and_never_the_retry_marker"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py#TestTheRevocationWrapper::test_a_definitive_revocation_answer_costs_exactly_one_attempt[the SDK refused the uid before sending]"
        status: pass
    human_judgment: false
  - id: D5
    description: "An exhausted revocation budget raises `RevocationUnconfirmed`, and never `Unavailable`, `RetryError` or the internal marker (D-05, SIGNOUT-02, T-46-01)."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py#TestTheRevocationWrapper::test_neither_the_retry_error_nor_the_internal_marker_escapes"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py#TestTheRevocationWrapper::test_an_exhausted_budget_raises_the_revocation_leaf"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py#TestTheRevocationWrapper::test_exhaustion_is_not_the_user_not_found_mapping"
        status: pass
    human_judgment: false
  - id: D6
    description: "A completed revocation costs exactly one attempt, and a budget that was not exhausted returns after two calls (D-02)."
    requirement: SIGNOUT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py#TestTheRevocationWrapper::test_a_definitive_revocation_answer_costs_exactly_one_attempt[a confirmed revocation]"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py#TestTheRevocationWrapper::test_the_conversion_does_not_fire_on_a_budget_that_was_not_exhausted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py#TestTheRevocationWrapper::test_the_revocation_spends_the_whole_budget_and_no_more"
        status: pass
    human_judgment: false

duration: 4 min
completed: 2026-09-08
status: complete
---

# Phase 46 Plan 03: The revocation unit twins Summary

**Twenty unit cases now measure the two revocation properties no wire test can see: which Admin app each
call carried, and how many attempts each outcome cost — with the exhausted budget's leaf pinned by class,
because its 503 and its code are byte-identical to `Unavailable`'s.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-08T23:29:43Z
- **Completed:** 2026-09-08T23:33:56Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- The `app=` proof the whole no-`[DEFAULT]`-app rule rests on now exists for the revocation too. The
  recorded call is asserted as the whole list, `[{"uid": SUBJECT, "app": app}]`, so a forgotten `app=`
  fails on the identity of the app object rather than passing on a call count.
- The fail-closed arm is proven **above** the SDK: an unconfigured issuer and an empty apps mapping each
  leave the recorded call list `[]`, which is a stronger fact than "one call that raised".
- Pitfall 1's divergence is pinned. `_read` classes `ValueError` retryable; `_revoke` must not, because
  the SDK validates the uid before it sends the request. One adapter case asserts the class, and one
  retry case measures the cost: exactly one attempt, not three.
- T-46-01 is now detectable. `test_neither_the_retry_error_nor_the_internal_marker_escapes` asserts
  `isinstance(raised.value, RevocationUnconfirmed)` **and** `not isinstance(raised.value, Unavailable)`.
  A wrapper that reused `_exhausted` answers the same 503 and the same code on the wire, so this class
  line is the only assertion in the repository that could see the defect.
- The overrun `AssertionError` in `CountingRevoker` makes the budget a two-sided measurement: a fourth
  call is a loud failure, not a silently larger number.
- The full unit suite is green at **1281 passed** (1261 before this plan, plus this plan's 20), and
  `-m e2e` is unchanged at 348 passed.

## Task Commits

Each task was committed atomically:

1. **Task 1: The revocation cases in test_firebase_adapter.py** - `629e408` (test)
2. **Task 2: The attempt counts and the exhaustion conversion in test_firebase_retry.py** - `aacd02c` (test)

**Plan metadata:** `docs(46-03): complete the revocation unit twins plan`, the commit carrying this file.

## Files Created/Modified

- `tests/unit/test_firebase_adapter.py` - the `revoke_calls` fixture beside `get_user_calls`, and
  `TestTheRevocation` with nine cases: the explicit `app=`, the confirmed `None`, the two fail-closed
  selection arms, the 503 pair, the 401 arm, the definitive malformed subject, and the two retryable arms.
  `RevocationUnconfirmed` joined the `errors` import, which ruff reformatted into a parenthesized block.
- `tests/unit/test_firebase_retry.py` - `CountingRevoker`, the four-row `REVOCATION_DEFINITIVE` table and
  `TestTheRevocationWrapper` with eleven cases (four parametrized plus seven). `revoke_with_retry` and
  `RevocationUnconfirmed` joined the imports. The existing `lookup_with_retry` cases are untouched.

## Decisions Made

- **`CountingRevoker` is a sibling, not a subclass, of `CountingAdapter`.** The two fakes expose different
  method names, so no case can drive the wrong seam through the wrong wrapper. Subclassing, as
  `AsyncCountingAdapter` does, would have carried `get_user_provider_data` into a revocation fake.
- **The revocation gets one class per file, not cases spread through the existing classes.** The read's
  `ValueError` arm and the revocation's diverge; keeping them in separate classes means a reader compares
  two adjacent blocks rather than reconstructing the difference from interleaved cases.
- **No sync twin of `CountingRevoker`.** `test_the_policy_is_agnostic_to_a_sync_or_async_adapter` already
  proves `AsyncRetrying` counts both the same, and the production seam method is async. A second fake
  would restate a settled fact.
- **The exhaustion class assertion and the wire-pair assertion are separate cases.** If they shared one
  case, a future edit that dropped the class lines would leave a passing status assertion behind and the
  case name would still read as if the leaf were checked.

## Deviations from Plan

None - plan executed exactly as written.

Every gate ran in the form the plan wrote it. The three `grep -c` gates are `-ge` thresholds rather than
equalities, so the loose-literal problem recorded by 46-01 and 46-04 could not arise here: the measured
counts are 11, 5 and 1 against thresholds of 4, 4 and 1. The `not isinstance(raised.value, Unavailable)`
gate matches the exact source line, character for character.

## Issues Encountered

None. The wave handoff's promise held: every name this plan asserts against already existed, and no
failure in either file came from anything but a case being written.

## Verification Results

| Gate | Result |
|---|---|
| `uv run pytest tests/unit/test_firebase_adapter.py -q` | 61 passed |
| `grep -c 'revoke_refresh_tokens' test_firebase_adapter.py` >= 4 | 11, pass |
| `grep -c 'RevocationUnconfirmed' test_firebase_adapter.py` >= 4 | 5, pass |
| `uv run pytest tests/unit/test_firebase_retry.py -q` | 27 passed |
| `grep -c 'revoke_with_retry' test_firebase_retry.py` >= 5 | 10, pass |
| `grep -c 'not isinstance(raised.value, Unavailable)' test_firebase_retry.py` >= 1 | 1, pass |
| `uv run pytest tests/unit/test_firebase_adapter.py tests/unit/test_firebase_retry.py -q` | 88 passed |
| `uv run pytest -q` | **1281 passed**, 577 deselected |
| `uv run pytest -m e2e -q` | 348 passed, unchanged by this plan |
| `uv run ruff check src tests` | clean |

The three judgment prohibitions were each read against the written source and hold:

- **The exhaustion assertion tests the class, not the status.** `isinstance(..., RevocationUnconfirmed)`
  and `not isinstance(..., Unavailable)` are both present; the 503 and the code live in their own case.
- **No test asserts a success outcome for a call that raised.** Every raising case is inside
  `pytest.raises`; the only `is None` assertions are on the confirmed-revocation and non-exhausted-budget
  paths.
- **No test constructs a Firebase app or reaches a network endpoint.** The adapter file uses `RecordingApp`
  over a monkeypatched SDK function; the retry file imports no SDK symbol at all.

## Known Stubs

None. Every case added asserts a real outcome of the production seam or the production wrapper.

## Threat Flags

None. This plan edits two test files, adds no source symbol, installs no package and opens no new surface.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Wave 4 (plan 46-05, the phase close) is unblocked. Notes for it:

1. **Measured counts, as of this plan's last run:** unit `uv run pytest -q` = **1281 passed** (577
   deselected); `uv run pytest -m e2e -q` = **348 passed** (1510 deselected); `ruff check src tests`
   clean. `tests/unit/test_firebase_adapter.py` holds 61 cases and `tests/unit/test_firebase_retry.py`
   holds 27. The sign-out e2e file is unchanged at 15.
2. **The `ValueError` (malformed uid) arm is no longer unowned.** The wave handoff listed it as covered
   nowhere; it now has an adapter case (the class and the stage) and a retry case (the one-attempt cost).
3. **Still unowned:** `TestTheLookupArmsCarryStageAndOnlyABoundedCause` at
   `tests/unit/test_rejection_vocabulary.py:213` parametrizes a hand-picked three — `UserNotFound`,
   `Unavailable`, `NotLinked` — and does not name `RevocationUnconfirmed`. It is a sample, not a totality
   walk, so nothing fails today. Adding a fourth row is a one-line edit if 46-05 wants the new leaf's
   `stage`-only `log_fields` pinned there as well.
4. **The auth package ratchet stayed at `(8, 24, 64)`.** This plan added no file under
   `src/nativespeaker/api/auth/` and re-measured nothing.

---
*Phase: 46-post-auth-sign-out-all*
*Completed: 2026-09-08*

## Self-Check: PASSED

Both modified files exist on disk. Both task commits (`629e408`, `aacd02c`) are in the log. The working
tree was clean after each commit, so nothing this plan produced was left untracked.
