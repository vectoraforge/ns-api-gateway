---
phase: 46-post-auth-sign-out-all
plan: 04
subsystem: testing
tags: [pytest, fastapi, httpx, firebase-admin, structlog, tenacity]

# Dependency graph
requires:
  - phase: 46-post-auth-sign-out-all
    provides: "plan 46-01's `/auth/sign-out-all` route, `revoke_with_retry`, `RevocationUnconfirmed`, the `FakeFirebaseAdapter` revocation methods and the `_LogSpy` / `_spy_on` helpers"
  - phase: 38-post-auth-sync
    provides: "`tests/e2e/test_sync.py`, the barrier-rejection answers this route is compared against"
  - phase: 45-post-auth-restore-subscription
    provides: "the two-refusals-compared-to-each-other model in `tests/e2e/test_restore_subscription.py`"
provides:
  - "The outage 503, the no-app 503 and the no-such-user 401 asserted at the wire over the real seam"
  - "The two 503 bodies compared as raw bytes and proven equal"
  - "The idempotent repeat: a second call after a confirmed one answers 204 again"
  - "`real_seam` and `sdk_revocations`, the e2e fixtures that keep the seam's own classification in the path"
  - "`_BARRIER_REJECTIONS`, the five rejections compared byte for byte against `/auth/sync`"
  - "`route_records`, the spy over both the router's and the error handler's loggers"
  - "The log-discipline cases: the refusal's one WARNING, and no identifier in any record"
affects: [46-03, 46-05]

actuals:
  tokens: 3972
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "An e2e refusal case runs the REAL seam over a monkeypatched SDK, because the fake replaces the very classification the case means to prove"
    - "A barrier-parity case names the error class each seeded state earns, so a row that reached a different barrier fails rather than passing on a coincidentally equal pair"

key-files:
  created: []
  modified:
    - tests/e2e/test_sign_out_all.py

key-decisions:
  - "The three refusal cases install `FirebaseAdminLookup` over a monkeypatched `auth.revoke_refresh_tokens` instead of scripting the fake: the fake IS the seam, so a fake scripted with an SDK error escapes unhandled and never becomes a 503."
  - "The two 503 cases each spell `verification_temporarily_unavailable` at the wire; the equality case compares the two responses' raw bytes to each other, never to a literal."
  - "Each barrier row carries the error class its seeded state earns (`InvalidExternalJwt`, `PreAuthIdentityNotAllowed`, `HistoricalIdentity`, `BlockedUser`), so parity cannot pass vacuously."
  - "The confirmed-record assertion is plan 46-01's existing case, not a second copy of it."
  - "The plan's `grep -c 'capture_logs' = 0` gate was run as `grep -c 'capture_logs('`: the file's one mention is the docstring saying the helper is a spy and NOT `capture_logs`."

patterns-established:
  - "The fake proves the route's own behaviour; the real seam proves the classification. A case that asserts a provider error's status must not replace the classifier."
  - "A log-discipline assertion runs over every field of every captured record, so a field added later cannot slip an identifier past it."

requirements-completed: [SIGNOUT-01, SIGNOUT-02]

coverage:
  - id: D1
    description: "A Firebase outage answers 503 `verification_temporarily_unavailable` and explicitly not 204 (D-05, T-46-01)."
    requirement: SIGNOUT-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestTheThreeRefusals::test_a_firebase_outage_answers_503_and_never_204"
        status: pass
    human_judgment: false
  - id: D2
    description: "An account the provider does not have answers 401 `auth_required` with the `WWW-Authenticate` challenge, after exactly one attempt (D-06)."
    requirement: SIGNOUT-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestTheThreeRefusals::test_an_account_the_provider_does_not_have_answers_401"
        status: pass
    human_judgment: false
  - id: D3
    description: "An issuer with no configured Admin app answers 503 with no SDK call made at all (D-01, D-05)."
    requirement: SIGNOUT-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestTheThreeRefusals::test_an_issuer_with_no_configured_app_answers_503_with_no_call_made"
        status: pass
    human_judgment: false
  - id: D4
    description: "The outage body and the no-app body are equal as raw bytes, so no body names which check refused (T-46-04)."
    requirement: SIGNOUT-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestTheThreeRefusals::test_the_outage_and_the_no_app_bodies_are_equal_to_each_other"
        status: pass
    human_judgment: false
  - id: D5
    description: "A second sign-out after a confirmed one answers 204 again and makes a second provider call."
    requirement: SIGNOUT-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestARepeatedSignOut::test_a_second_call_after_a_confirmed_one_answers_204_again"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every barrier rejection answers exactly what `/auth/sync` answers, status and raw bytes, and none reaches the provider (T-46-05)."
    requirement: SIGNOUT-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestEveryBarrierRejectionIsTheOneSyncAnswers::test_the_two_routes_answer_the_same_rejection[no-credential]"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestEveryBarrierRejectionIsTheOneSyncAnswers::test_the_two_routes_answer_the_same_rejection[an-unverifiable-token]"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestEveryBarrierRejectionIsTheOneSyncAnswers::test_the_two_routes_answer_the_same_rejection[a-pre-auth-subject]"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestEveryBarrierRejectionIsTheOneSyncAnswers::test_the_two_routes_answer_the_same_rejection[a-retired-identity]"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestEveryBarrierRejectionIsTheOneSyncAnswers::test_the_two_routes_answer_the_same_rejection[a-blocked-user]"
        status: pass
    human_judgment: false
  - id: D7
    description: "A refused call writes one WARNING record, event `revocation_unconfirmed`, carrying the stage alone and no confirmation line (T-46-03)."
    requirement: SIGNOUT-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestWhatEachOutcomeWritesDown::test_a_refused_call_writes_the_warning_and_no_confirmation"
        status: pass
    human_judgment: false
  - id: D8
    description: "Neither the subject nor the provider uid appears in any field of any record, over a confirmed, a refused and a rejected call (T-46-03)."
    requirement: SIGNOUT-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sign_out_all.py#TestWhatEachOutcomeWritesDown::test_no_record_of_any_outcome_carries_the_subject_or_the_provider_uid"
        status: pass
    human_judgment: false

duration: 11 min
completed: 2026-09-08
status: complete
---

# Phase 46 Plan 04: The refusals, the barrier and the records Summary

**Every unconfirmed revocation now reaches the client as a refusal over the real router — the outage and
the unconfigured issuer as one indistinguishable 503, the missing account as a 401 — and the five barrier
rejections answer byte for byte what `/auth/sync` answers while reaching the provider zero times.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-09-08T23:13:30Z
- **Completed:** 2026-09-08T23:24:25Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `tests/e2e/test_sign_out_all.py` grew from 3 cases to 15, all green, and the full `-m e2e` run is
  348 passed.
- The fail-closed rule of SIGNOUT-02 is now a wire fact, not a read claim. The outage arm asserts
  `status_code != 204` on its own line, so a swallowed raise is visible in the case name rather than
  hidden behind an otherwise-passing 503 check.
- The 401 arm proves the ordering that Pitfall 2 warns about. `auth.UserNotFoundError` reaches
  `UserNotFound`, not the `FirebaseError` arm it subclasses, and the case also asserts the call was made
  exactly once — a retryable misclassification would report three.
- The no-app arm proves fail-closed **above** the SDK: the recorded SDK call list is `[]`, not "one call
  that raised".
- The two 503 bodies are compared to each other as raw bytes. A body naming which check refused differs
  here and nowhere else on the wire.
- Five barrier rejections are compared against `/auth/sync` in one parametrized case, each row pinned to
  the error class its seeded state earns, and every row asserts the fake recorded zero revocation calls.
- One assertion sweeps every field of every record from a confirmed, a refused and a rejected call, so a
  field added later cannot slip the subject or the provider uid into a log line.

## Task Commits

Each task was committed atomically:

1. **Task 1: The three refusals and the one shared body** - `20cbd9b` (test)
2. **Task 2: The barrier rejections and the log discipline** - `3981a63` (test)

**Plan metadata:** `docs(46-04): complete the refusals and records plan`, the commit carrying this file.

## Files Created/Modified

- `tests/e2e/test_sign_out_all.py` - the module docstring re-written to cover refusals and records;
  `_PROVIDER_TEXT`, `_HANDLER_LOGGER`, `_NamedApp`, the `real_seam` and `sdk_revocations` fixtures, the
  `route_records` spy, `_configured`, the three subject constants and `_BARRIER_REJECTIONS`; four classes
  added — `TestTheThreeRefusals`, `TestARepeatedSignOut`,
  `TestEveryBarrierRejectionIsTheOneSyncAnswers` and `TestWhatEachOutcomeWritesDown`

## Decisions Made

- **The refusal cases run the real seam, not the fake.** See deviation 1. The fake replaces
  `FirebaseAdminLookup`, which is the object that owns the `except` arms; scripting it with an SDK error
  removes the classification the case exists to prove.
- **The barrier rows name their error class.** `test_sync.py` already reads status and code off the class
  rather than guessing them; here the class also proves the seeded state reached the barrier it was meant
  to reach, so a parity assertion cannot pass on two coincidentally equal answers.
- **"An unlinked subject" and "a pre-auth identity" are one outcome, not two.** `IdentitiesDB.resolve`
  returns an `Identity` with no user for a pair with no row, and `get_linked_identity` raises
  `PreAuthIdentityNotAllowed` for it. The fifth row is the caller with no credential at all, which is a
  distinct barrier arm the plan's list did not name.
- **The confirmed-record case was not rewritten.** Plan 46-01's
  `test_it_writes_one_info_record_carrying_the_row_id_alone` already asserts the whole entry list equals
  one `sign_out_all_confirmed` entry whose fields are exactly `identity_row_id`. Task 2's criterion is met
  by that case; a second copy would assert the same fact twice.
- **The no-leak case drives three outcomes, not one.** A confirmed 204, a no-app 503 and a
  no-such-user 401 in one case, then one comprehension over all their fields.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's refusal mechanism cannot produce the refusal it asserts**

- **Found during:** Task 1
- **Issue:** The plan directs each refusal case to script `scripted_firebase_adapter` through
  `script_revocation`, and the first two bullets require a `firebase_admin.exceptions.FirebaseError`
  subclass to answer 503 and an `auth.UserNotFoundError` to answer 401. That cannot happen. The fake
  **is** the seam: `app.state.firebase_adapter` is replaced wholesale, so `FirebaseAdminLookup._revoke`
  — the only code that converts an SDK exception into `UserNotFound` or `RetryableLookupError` — never
  runs. `revoke_with_retry` retries `RetryableLookupError` alone, so a raw SDK error is neither retried
  nor converted. Measured, not reasoned: a probe scripting the fake with
  `exceptions.UnavailableError` produced `Unhandled exception` from `app/error_handlers.py` and the
  error escaped the ASGI transport. No 503, no body, no header.
- **Fix:** The three refusal cases install the **real** seam over a monkeypatched SDK call. The
  `real_seam` fixture puts `FirebaseAdminLookup(apps)` on `app.state.firebase_adapter`; the
  `sdk_revocations` fixture monkeypatches `firebase_admin.auth.revoke_refresh_tokens` and records its
  calls, on the model of `get_user_calls` in `tests/unit/test_firebase_adapter.py`. The whole path then
  runs: selection, `run_in_threadpool`, the `except` arms in their declared order, the tenacity budget,
  the exhaustion callback and the error handler. Measured results: the outage answers 503 after three
  SDK calls, the missing account answers 401 with `WWW-Authenticate: Bearer error="invalid_token"` after
  one, and the unconfigured issuer answers 503 after none. The fake is kept for the confirmed path, the
  repeat and every barrier case, where the route's own behaviour — not the classification — is the
  subject.
- **Files modified:** `tests/e2e/test_sign_out_all.py`
- **Verification:** `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` — 15 passed. The probe that
  demonstrated the plan's mechanism failing was deleted before the commit.
- **Committed in:** `20cbd9b` (Task 1 commit)

**2. [Rule 3 - Blocking] The `capture_logs` verify gate counts the docstring that forbids it**

- **Found during:** Task 2 (the verify run)
- **Issue:** The gate `test "$(grep -c 'capture_logs' tests/e2e/test_sign_out_all.py)" = "0"` reports 1
  and fails. The one occurrence is line 43, plan 46-01's `_spy_on` docstring: *"A spy, not
  `capture_logs`: the module-level logger caches its binding, so capture sees nothing."* That sentence
  is the warning that keeps a later author from reaching for the helper — deleting the word to satisfy
  the grep would remove the only thing in the file that explains the choice. This is the third instance
  of the loose-literal pattern the 46-01 handoff flagged.
- **Fix:** The gate was run as `test "$(grep -c 'capture_logs(' tests/e2e/test_sign_out_all.py)" = "0"`,
  which counts a **call** rather than a mention — exactly what the gate's own `fails_when` describes
  ("the file uses a capture that sees nothing against a module-level logger"). It reports 0 and passes.
- **Files modified:** none — this is a correction to the plan's verification, not to the code.
- **Verification:** `grep -c 'capture_logs(' tests/e2e/test_sign_out_all.py` = 0;
  `grep -n 'capture_logs' tests/e2e/test_sign_out_all.py` returns the one docstring line and nothing
  else.
- **Committed in:** n/a (verification-only)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** No scope change and no new file. One deviation replaces the mechanism three cases use
so they can assert what the plan asked them to assert; the other corrects a grep. Every acceptance
criterion of both tasks is met.

## Issues Encountered

None. Every case passed on its first run after the seam mechanism was corrected.

## Verification Results

| Gate | Result |
|---|---|
| `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | 15 passed |
| `uv run pytest -m e2e -q` | 348 passed, 1490 deselected |
| `uv run ruff check src tests` | clean |
| `grep -c 'verification_temporarily_unavailable'` >= 2 | pass (2) |
| `grep -c 'auth_required'` >= 1 | pass (1) |
| `grep -c 'sign_out_all_confirmed'` >= 3 | pass (3) |
| `capture_logs` is never called (corrected gate, deviation 2) | pass (0) |
| `uv run pytest -q -m "not e2e"` | 1490 passed |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed, baseline still 0 |
| No file under `src/` in this plan's commits | pass — `git diff --name-only 20cbd9b^..HEAD` is one `tests/e2e/` path |
| No file deleted by either commit | pass |

### Prohibitions

| Statement | Status |
|---|---|
| No refusal body distinguishes an outage from a missing app or a rejected subject; the stage reaches the operator record alone. | verified — the two 503 bodies are equal as raw bytes, and `stage` appears only in the WARNING record's fields |
| No test asserts a 204 for an outcome in which the scripted adapter raised. | verified — every 204 assertion in the file follows `script_revocation(None)` or `sdk_revocations(None)` on a configured issuer |
| The subject and the provider uid must not appear in any captured log record for this route. | verified — one comprehension over every field of a confirmed, a refused and a rejected call returns empty |

## Known Stubs

None. Every case drives the real router and asserts a measured answer.

## Threat Flags

None. This plan edits one test file, adds no route and imports nothing that was not already a declared
dependency.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**For 46-03 (Wave 3, the unit attempt counts):** two attempt facts are now asserted end to end and need
no e2e twin — the outage spends three SDK calls and the missing account spends one. What 46-03 still owns
is the arm-by-arm table: the `ValueError` (malformed uid) arm has no case anywhere yet, and
`TestTheLookupArmsCarryStageAndOnlyABoundedCause` at `tests/unit/test_rejection_vocabulary.py:212` still
does not name `RevocationUnconfirmed`. `tests/unit/test_firebase_adapter.py` has no `get_user_calls` twin
for the revocation; the `sdk_revocations` fixture in `tests/e2e/test_sign_out_all.py` is the shape to
copy, and it deliberately records `{"uid": ..., "app": ...}` so an `app=` assertion is available.

**For 46-05 (Wave 4, the records):** the D-06 flagged conflict is now demonstrated on the wire, so the
REQUIREMENTS.md entry can cite
`TestTheThreeRefusals::test_an_account_the_provider_does_not_have_answers_401` rather than the decision
alone. The measured counts to write down are: `tests/e2e/test_sign_out_all.py` 15 cases, the full
`-m e2e` run 348 passed, and `-m "not e2e"` 1490 passed.

**One standing caution for both.** The auth-package ratchet is untouched at `(8, 24, 64)` because this
plan added nothing under `src/nativespeaker/api/auth/`. Any later plan that does must re-measure and
re-write `CURRENT` in `tests/unit/test_auth_package_shape.py`.

**And one for anyone editing this file.** The refusal cases only prove what they claim while the **real**
seam is in the path. Replacing `real_seam` with `scripted_firebase_adapter` to "simplify" would make the
outage case answer an unhandled 500 and the 401 case never reach `UserNotFound` — see deviation 1.

---
*Phase: 46-post-auth-sign-out-all*
*Completed: 2026-09-08*

## Self-Check: PASSED

The one modified file exists on disk. Both task commits (`20cbd9b`, `3981a63`) are in the log. Every
plan-level gate was re-run after the last task commit and all are green.
