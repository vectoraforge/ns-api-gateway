---
phase: 37-post-auth-create-user
verified: 2026-08-23T19:30:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 37: Post-Auth Create-User Verification Report

**Phase Goal:** Ship the only pre-auth-callable route — first-time account creation linking a
verified Firebase `(issuer, subject)` to one new user plus exactly one active identity row.

**Verified:** 2026-08-23T19:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP success criterion) | Status | Evidence |
|---|---|---|---|
| 1 | An unlinked caller succeeds at create-user and is rejected with `preauth_identity_not_allowed` on every other route | ✓ VERIFIED | Structural: `registry.py` condition 6 (`_PREAUTH_CALLABLE_ROUTE`) fails boot if any route other than `POST /auth/create-user` declares `preauth_callable=True`; `auth/identity.py:87-90` rejects with `PREAUTH_IDENTITY_NOT_ALLOWED` for every route whose metadata has `preauth_callable=False` on outcome-1'. `tests/unit/test_route_registry.py::TestAssertionPasses::test_real_app_registry_matches_the_real_router` proves the declared table matches the live router, closing the gap between "declared" and "actually registered". `tests/e2e/test_create_user.py::TestCreate01AdmittedHereAndRefusedEverywhereElse` drives one token through both `POST /auth/create-user` (200) and `GET /examples` (403 `preauth_identity_not_allowed`) on the wire. Ran `pytest tests/e2e/test_create_user.py tests/e2e/test_barrier_admission.py -m e2e`: 44 passed. |
| 2 | Prepare mode and completion mode partition correctly on the mode signal | ✓ VERIFIED | `routers/auth.py:150-174` classifies via `classify_mode_signal` (query `challenge=true` XOR body `challenge_id`) before dispatching to `_prepare` / `_complete`; both-or-neither is `invalid_request` with no side effects. `tests/unit/test_create_user_modes.py` (`TestTheTwoModesDispatch`, `TestTheInvalidRequestPartition`, `TestTheWhitespaceAsymmetry`, `TestTheRejectionHasNoSideEffects`) exercises the partition directly against the live route. Ran `pytest tests/unit/test_create_user_modes.py`: passed as part of the 90-test run below. |
| 3 | One transaction produces the user row, exactly one ACTIVE identity row, and both store purchase-attribution tokens — a forced mid-transaction failure leaves no partial account | ✓ VERIFIED | `auth/creation.py::_insert_account` wraps all three inserts (`User`, `ExternalIdentity`, two `StorePurchaseToken` rows) in one `session.begin_nested()` savepoint; `classify_insert_conflict` reads `constraint_name` off the driver exception chain. `tests/schema/test_create_atomicity.py` (16 tests) forces both an `(issuer, subject)` conflict on the identity insert and an attribution-token key collision, against a real, committing PostgreSQL — asserting zero leaked rows, the surviving row is the winner's untouched, the consumption and rejection audit row commit despite the rollback. **Independently mutation-tested by this verifier**: removed `await savepoint.rollback()`, re-ran the module — result was **7 passed, 9 errors** (`PendingRollbackError`), byte-for-byte matching 37-09-SUMMARY.md's claimed "9 of 16" mutation result; file restored and `git diff` confirmed clean, then re-ran green (16 passed). |
| 4 | Two concurrent creates for the same `(issuer, subject)` yield one account; the loser reconciles via `/auth/sync` | ✓ VERIFIED | `tests/schema/test_create_race.py::TestTwoConcurrentCompletionsProduceExactlyOneAccount` drives two real `create_account` calls under `asyncio.gather` on two separate connections, synchronized by a two-party barrier that releases both attempts only after each has independently re-resolved and seen the subject unlinked (asserted, not assumed: `identities_seen_at_barrier == [0, 0]`). Reads exactly one identity row, one user row, two tokens (winner's), zero orphaned user rows, both challenges consumed, both audit rows committed, and the loser gets `identity_already_linked` (never idempotent success — the signal `/auth/sync` remediation depends on). `TestRunningTheSameCreationTwiceSequentially` covers the non-concurrent replay case. Ran the module directly: 15 passed. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/routers/auth.py` | Single route, mode dispatch, §02 rejection precedence order | ✓ VERIFIED | 615 lines; mode dispatch, `_prepare`, `_complete`, `_challenge_rejected`, `_consuming_rejection` all present and wired to real dependencies (`ChallengeStore`, `AuditWriter`, Firebase adapter via `lookup_with_retry`) |
| `src/nativespeaker/api/auth/creation.py` | Consuming transaction: savepoint-wrapped inserts, re-resolution, race classification | ✓ VERIFIED | 371 lines; `create_account`, `_insert_account`, `classify_insert_conflict`, `RACE_CONSTRAINT_NAMES` all present, called from `routers/auth.py:451` |
| `src/nativespeaker/api/auth/registry.py` | Declarative route table + boot-time enumeration assertion | ✓ VERIFIED | `POST /auth/create-user` is the sole `preauth_callable=True` entry; `assert_route_enumeration` enforces set-equality against the live router at startup (`app/lifespan.py`, confirmed by grep) |
| `src/nativespeaker/api/auth/modesignal.py` | Prepare/completion mode-signal classifier | ✓ VERIFIED | Pure function, no side effects, correctly rejects ambiguous/duplicate/malformed signals |
| `src/nativespeaker/api/auth/firebase.py` | Firebase Admin providerData read, fail-closed | ✓ VERIFIED | `_read` now includes the CR-01 fix (`google.auth.exceptions.GoogleAuthError` arm) — confirmed present in the file and in `git log` (`9ab4c4a fix(37): retry a credential-refresh failure instead of 500ing (CR-01)`) |
| `tests/schema/test_create_atomicity.py` | Criterion 3 proof against real PostgreSQL | ✓ VERIFIED | 16 tests, all pass; mutation-tested by this verifier (see truth 3 above) |
| `tests/schema/test_create_race.py` | Criterion 4 proof against real PostgreSQL | ✓ VERIFIED | 15 tests, all pass, genuine `asyncio.gather` concurrency with barrier-asserted premise |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `routers/auth.py::create_user` | `auth/modesignal.py::classify_mode_signal` | direct call, before any side effect | WIRED | Confirmed by reading and by `test_create_user_modes.py` exercising the live route |
| `routers/auth.py::_complete` | `auth/creation.py::create_account` | direct call, after provider read, with no open transaction across the call | WIRED | Confirmed by reading `_complete` (creation.py:451) and by e2e completion tests |
| `routers/auth.py::_complete` | `auth/retry.py::lookup_with_retry` → `auth/firebase.py::FirebaseAdminLookup` | `Depends(get_firebase_adapter)` injection | WIRED | Confirmed via `tests/e2e/test_create_user.py::TestTheRealAnonymousCompletion` (real Admin SDK call) and `test_firebase_retry.py` (18 tests) |
| `auth/creation.py::_insert_account` | PostgreSQL `UNIQUE` constraints (`external_identities_issuer_subject_key`, `external_identities_user_id_key`, `ix_external_identities_provider_account`) | `session.begin_nested()` + `IntegrityError.orig.__cause__.constraint_name` | WIRED | `tests/schema/test_create_atomicity.py::TestTheConstraintNamesInTheCodeAreTheOnesPostgresReports` reads the live catalog (`pg_constraint`, `pg_class`) and asserts equality with the module's literals |
| `auth/identity.py::resolve_identity` | `auth/registry.py::RouteMetadata.preauth_callable` | barrier passes `meta` per matched route | WIRED | Confirmed by reading; e2e `TestCreate01AdmittedHereAndRefusedEverywhereElse` proves it on the wire |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| CREATE-01 | 37-07, 37-08, 37-10 | Only pre-auth-callable route; every other route rejects with `preauth_identity_not_allowed` | ✓ SATISFIED | Registry boot assertion + e2e wire test (see Truth 1) |
| CREATE-02 | 37-01 (deliberately unchecked), 37-02, 37-06, 37-07, 37-08 | Prepare/completion mode partition | ✓ SATISFIED | See discussion below |
| CREATE-03 | 37-03, 37-04, 37-05, 37-07, 37-09, 37-10 | Atomic transaction, no partial account | ✓ SATISFIED | Mutation-tested (see Truth 3) |
| CREATE-04 | 37-09, 37-10 | Concurrent creates yield one account | ✓ SATISFIED | Real-concurrency test (see Truth 4) |

**On CREATE-02's traceability (flagged per verification instructions).** 37-01's SUMMARY deliberately leaves `requirements-completed: []` and explains explicitly: the plan only removes the `operation_variant` column, and marking CREATE-02 complete there "would make the traceability table lie." Four other plans (37-02, 37-06, 37-07, 37-08) each list `requirements-completed: [CREATE-02]` (37-07 and 37-08 also add CREATE-01/03). Checking the actual code: the requirement's literal text — "the endpoint implements both prepare mode and completion mode, partitioned by the mode signal" — is genuinely satisfied by `routers/auth.py`'s `create_user` handler (37-07's tracer route) dispatching on `classify_mode_signal`, with `_prepare`/`_complete` as the two bodies. 37-08 (challenge rejection collapsing) and 37-06 (tenacity retry wiring test infrastructure) support completion mode but are not themselves "the partition." 37-02's claim (promoting `tenacity`, deleting `auth/budgets.py`, building `auth/retry.py`) is the most tangential of the four — it is infrastructure completion mode later calls, not partitioning logic itself. None of this changes the verdict: the requirement is genuinely met in the codebase, just claimed more broadly across plans than is precise. This is a minor traceability-table imprecision, not a functional gap.

### Anti-Patterns Found

None. Scanned all 46 files from `37-REVIEW.md`'s `files_reviewed_list` for `TBD`/`FIXME`/`XXX` (debt-marker gate) — zero hits. Scanned the 16 core `src/` files for `TODO`/`HACK`/`PLACEHOLDER` and stub-language — one match, a docstring comment in `creation.py:316` explaining *why* a placeholder value is not used (not a stub itself).

### Behavioral Spot-Checks / Test Execution (run by this verifier, not taken from SUMMARY claims)

| Check | Command | Result | Status |
|---|---|---|---|
| Full suite | `pytest -m ""` | 1524 passed, 0 failed | ✓ PASS |
| Lint | `ruff check src/ tests/` | All checks passed | ✓ PASS |
| Schema tests (criteria 3+4) | `pytest -m schema tests/schema/test_create_atomicity.py tests/schema/test_create_race.py` | 31 passed | ✓ PASS |
| e2e create-user + barrier | `pytest -m e2e tests/e2e/test_create_user.py tests/e2e/test_barrier_admission.py` | 44 passed | ✓ PASS |
| Unit mode/precedence/rollback/conflict | `pytest tests/unit/test_create_user_modes.py tests/unit/test_create_user_precedence.py tests/unit/test_create_user_rollback.py tests/unit/test_conflict_classification.py` | 90 passed | ✓ PASS |
| Mutation test: `savepoint.rollback()` removed, atomicity module only | `pytest -m schema tests/schema/test_create_atomicity.py` | 7 passed, 9 errors (`PendingRollbackError`) — reproduces 37-09-SUMMARY.md's claimed "9 of 16" exactly | ✓ PASS (confirms the durability proof is genuine, not vacuous) |
| Mutation test: same, both atomicity + race modules | `pytest -m schema tests/schema/test_create_atomicity.py tests/schema/test_create_race.py` | 12 passed, 19 errors | ✓ PASS (extends the same conclusion to the race module) |

File was restored to its committed state after each mutation test and re-verified green (`git diff --stat` clean, 16/31 passed respectively).

### Known Open Issues (from 37-REVIEW.md — not new findings, factored into verdict per instructions)

These are pre-existing, documented findings. Not reported as new gaps. Confirmed their described state still matches the current code:

- **CR-01 (FIXED, commit `9ab4c4a`):** confirmed present — `firebase.py::_read` now catches `google.auth.exceptions.GoogleAuthError` and returns `retryable_failure`.
- **CR-02 (OPEN, accepted by user):** confirmed still present — `routers/auth.py::_prepare` reads `linked.provider` at line 205, after `await session.rollback()` at line 196. This is a real defect (an already-linked pre-auth caller hitting the race window gets `MissingGreenlet` → 500 instead of 409, with no audit row) on a narrow, real path. The user has explicitly decided to remove audit writes from this path in a later phase, which removes the `rollback()` call and moots the bug — deferred by decision, not by oversight. Does not block this verification.
- **WR-01..WR-04 (OPEN):** lifespan cleanup not in try/finally, `ty check` failing on `_LOOKUP_REJECTIONS`, `creation.py::_details` omitting `challenge_consumed`, and completion-internal-errors writing no audit row. All confirmed still present in the code, all pre-existing and known, none block the ROADMAP success criteria for this phase.

### Additional Observation (informational, not a gap)

`.planning/WINDOWS.md` carries three "open" phase-37 window items (rows 4, 6, 8) whose described defects — `_lookup_rejected` mis-mapping `user_not_found` and writing no audit rows, `_challenge_rejected` lacking per-rejection internal results, and `_completion_response` mis-mapping `provider_account_already_linked` — are **not** present in the current code. Reading `routers/auth.py` directly shows `_LOOKUP_REJECTIONS` correctly maps `user_not_found` → `AUTH_REQUIRED`/401, `_challenge_rejected` writes a full audit row with the specific internal result, and `_completion_response` maps through `CLIENT_CLASS_FOR_RESULT` correctly (including `provider_account_already_linked` → `OPERATION_NOT_ALLOWED`). These were evidently closed by later plans in the same wave (37-08/37-09) but the tracker rows were never marked `fixed`. Tracking hygiene issue only — does not affect the goal-achievement verdict.

### Deviations Recorded (not gaps)

- **Credential model (D-08 deviation).** `build_admin_apps` now accepts three sources — explicit `FIREBASE_SERVICE_ACCOUNT_JSON`, Application Default Credentials, or absent — rather than the key-only source D-08 specified, because the project's org policy (`iam.disableServiceAccountKeyCreation`) makes minting a key impossible. Recorded in 37-10's plan/summary. Confirmed consistent with `firebase.py`'s comments and `config.py`.

### Human Verification Required

None. All four ROADMAP success criteria are covered by automated tests this verifier independently ran (including two of the highest-risk ones — the durability savepoint and the concurrent-race arbitration — mutation-tested against a real, committing PostgreSQL rather than trusted from SUMMARY claims).

### Gaps Summary

None. All four ROADMAP success criteria for Phase 37 are genuinely implemented, wired, and independently verified against real code execution (not SUMMARY narrative). The phase goal — shipping the only pre-auth-callable route with a genuinely atomic, race-safe account-creation transaction — is achieved.

---

_Verified: 2026-08-23T19:30:00Z_
_Verifier: Claude (gsd-verifier)_
