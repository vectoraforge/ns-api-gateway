---
phase: 46-post-auth-sign-out-all
verified: 2026-09-08T00:00:00Z
status: passed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 46: POST /auth/sign-out-all Verification Report

**Phase Goal:** Revoke the verified subject's Firebase refresh tokens through the issuer-selected Admin client.
**Verified:** 2026-09-08
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria, as rewritten by 46-05)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Success is returned only after Firebase confirms revocation | ✓ VERIFIED | `routers/auth.py::sign_out_all` awaits `revoke_with_retry` and only then logs and returns `Response(status_code=204)` (`src/nativespeaker/api/routers/auth.py:203-209`). `revoke_refresh_tokens` in `auth/firebase.py:73-80` makes exactly one call through `run_in_threadpool(self._revoke, app, subject)`; `_revoke` (auth/firebase.py:82-102) never returns a value on success — confirmation is the SDK call not raising. e2e case `test_a_confirmed_revocation_answers_204_with_an_empty_body` passes; unit case `test_a_configured_issuer_passes_its_own_app_explicitly` asserts the recorded call is `[{"uid": SUBJECT, "app": app}]`, proving `app=` is passed explicitly (no `[DEFAULT]` app reachable). |
| 2 | An indeterminate or failed revocation fails closed — never a success response | ✓ VERIFIED | Every non-success arm in `_revoke` raises (`UserNotFound`, `RevocationUnconfirmed`, or `RetryableLookupError` en route to `RevocationUnconfirmed`); none returns. `_revocation_exhausted` (auth/firebase.py:181-183) is its own callback, distinct from `_exhausted`, and raises `RevocationUnconfirmed` on budget exhaustion. Unit case `test_neither_the_retry_error_nor_the_internal_marker_escapes` in `test_firebase_retry.py` asserts `isinstance(raised.value, RevocationUnconfirmed)` **and** `not isinstance(raised.value, Unavailable)` — the only assertion in the repo that could catch a wrapper reusing the read's exhaustion leaf. e2e cases assert a Firebase outage answers 503 and explicitly not 204, and an unconfigured issuer answers 503 with zero SDK calls recorded. |
| 3 | (rewritten by 46-05) Every unconfirmed outcome is one leaf (`RevocationUnconfirmed`) whose class name is its WARNING event name; one INFO line records a confirmed revocation with the identity row id; the middleware writes one `request` line per attempt; no durable row is written | ✓ VERIFIED | `ROADMAP.md:764` states this criterion in full and cites the answering evidence. `errors.py:414-417` defines `RevocationUnconfirmed(ProviderLookupError)`, 503 `verification_temporarily_unavailable`. `routers/auth.py:208` logs `logger.info("sign_out_all_confirmed", identity_row_id=str(identity.identity.id))` and nothing else. e2e case `test_a_refused_call_writes_the_warning_and_no_confirmation` and `test_no_record_of_any_outcome_carries_the_subject_or_the_provider_uid` confirm the log discipline. `grep` confirms no `audit.auth_events` writer or `core.auth_event_result` reference was reintroduced anywhere under `src/`. REQUIREMENTS.md SIGNOUT-02 entry records the audit half as inherited-closed from Phase 38 D-03. |
| 4 | No backend token, session, or generation counter is introduced | ✓ VERIFIED | `sign_out_all` declares only `get_linked_identity` and `get_firebase_adapter` — no `get_db`. `grep -v '^ *#' routers/auth.py \| grep -c get_db` = 2, the same count the file carried before this phase (the other two routes' `get_db` uses). Unit case `TestTheSignOutRouteOpensNoSession::test_sign_out_all_declares_no_database_session` asserts `get_db not in _declared(_route_at("/auth/sign-out-all"))`. `grep -rn "generation_counter"` and `grep -rn "checkRevoked"` under `src/` and `tests/` both return empty. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/auth/adapters.py` | `revoke_refresh_tokens` on `FirebaseAdminAdapter` Protocol, returns `None` | ✓ VERIFIED | Line 28-30, confirmed by direct read. |
| `src/nativespeaker/api/auth/firebase.py` | `revoke_refresh_tokens`, `_revoke`, `_revocation_exhausted`, `revoke_with_retry` | ✓ VERIFIED | All four present, arms in the required order (`UserNotFoundError` before `FirebaseError`; `ValueError` definitive, not retryable). |
| `src/nativespeaker/api/errors.py` | `RevocationUnconfirmed(ProviderLookupError)`, 503, `verification_temporarily_unavailable` | ✓ VERIFIED | Declared beside `Unavailable`; `ErrorCode` unedited (no new member — code already existed). |
| `src/nativespeaker/api/routers/auth.py` | `POST /auth/sign-out-all`, 204, `Depends(get_linked_identity)`, no `get_db` | ✓ VERIFIED | Route registered once, narrowing comment present, handler body is one awaited call plus one log line. |
| `tests/unit/conftest.py::FakeFirebaseAdapter` | `revoke_refresh_tokens`, `revoke_calls`, `script_revocation`, `revoke_answer` | ✓ VERIFIED | All four present (lines 198-222). |
| `tests/e2e/test_sign_out_all.py` | Confirmed path, refusals, barrier parity, log discipline | ✓ VERIFIED | 15 test functions/parametrized cases, all pass. |
| `tests/unit/test_firebase_adapter.py::TestTheRevocation` | App selection and four raising arms | ✓ VERIFIED | Present, 61 cases pass in file. |
| `tests/unit/test_firebase_retry.py::TestTheRevocationWrapper` | Attempt counts, exhaustion-by-class | ✓ VERIFIED | Present, 27 cases pass in file. |
| `.planning/REQUIREMENTS.md` | SIGNOUT-01/02 amended, header counts re-derived | ✓ VERIFIED | Checked `[x]`, dated entries present, header reads thirty-one/forty-two/eleven as claimed. |
| `.planning/ROADMAP.md` | Criterion 3 rewritten, no "BLOCKED" | ✓ VERIFIED | `grep -c 'BLOCKED: requires a mechanism Phase 37.1 deleted'` = 0; criterion 3 states what was built. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `routers/auth.py::sign_out_all` | `auth/firebase.py::revoke_with_retry` | direct await | ✓ WIRED | Confirmed by read and by e2e 204 case. |
| `revoke_with_retry` | `FirebaseAdminLookup.revoke_refresh_tokens` | `AsyncRetrying(...)(adapter.revoke_refresh_tokens, ...)` | ✓ WIRED | Confirmed by read; retry policy uses `FIREBASE_LOOKUP_ATTEMPTS` and `RetryableLookupError` predicate. |
| `revoke_refresh_tokens` | `firebase_admin.auth.revoke_refresh_tokens` | `run_in_threadpool(self._revoke, app, subject)` → `auth.revoke_refresh_tokens(subject, app=app)` | ✓ WIRED | Confirmed by read; `app=` passed explicitly, proven by unit test asserting the recorded call's app identity. |
| `RevocationUnconfirmed` | `app_error_handler` | class-name-derived WARNING event, 503 body | ✓ WIRED | Confirmed by e2e case asserting the WARNING event `revocation_unconfirmed` and the 503 wire response. |
| `app/dependencies.py::get_firebase_adapter` | `app.state.firebase_adapter` | `Depends(get_firebase_adapter)` | ✓ WIRED | Confirmed by route declaration and e2e fixtures (`scripted_firebase_adapter`, `real_seam`). |

### Data-Flow Trace (Level 4)

Not applicable in the traditional sense (no rendered UI data). The relevant flow — issuer/subject through to the SDK call — was traced above and confirmed by the unit test asserting the recorded SDK call carries the exact `{"uid": SUBJECT, "app": app}` pair, not a static/mock value.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit suite | `uv run pytest -q` | 1281 passed, 577 deselected | ✓ PASS (matches expected 1281) |
| Sign-out e2e file | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | 15 passed | ✓ PASS (matches expected 15) |
| Full e2e suite | `uv run pytest -m e2e -q` | 348 passed, 1510 deselected | ✓ PASS (matches expected 348) |
| Lint | `uv run ruff check src tests` | All checks passed | ✓ PASS |
| Spec files unedited | `sha256sum -c` on `11-sign-out-all.md` and `SHARED-INVARIANTS.md` | both match recorded hashes | ✓ PASS |
| No `checkRevoked` / generation counter | `grep -rn` under `src/`, `tests/` | 0 matches for both | ✓ PASS |
| No migration touched | `git log` on `migrations/` since phase start | no commits | ✓ PASS |

All commands run directly by this verifier in its own process (not copied from SUMMARY.md).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SIGNOUT-01 | 46-01, 46-02, 46-03, 46-04, 46-05 | Endpoint revokes verified subject's Firebase refresh tokens through issuer-selected Admin client, success only on confirmed revocation | ✓ SATISFIED | Route, seam, and app-selection proof all confirmed above; REQUIREMENTS.md checked `[x]` with dated entries citing measured suite counts. |
| SIGNOUT-02 | 46-01, 46-02, 46-03, 46-04, 46-05 | Fail-closed half: an indeterminate or failed revocation must never report success (audit half settled by Phase 38 removal, inherited-closed) | ✓ SATISFIED | `RevocationUnconfirmed` leaf, exhaustion-by-class assertion, and wire-level 503/401 refusal cases confirmed above; REQUIREMENTS.md records the audit half as inherited-closed rather than reopened, consistent with Phase 38 D-03. |

No orphaned requirements found under Phase 46 in REQUIREMENTS.md.

### Anti-Patterns Found

None. No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, or `PLACEHOLDER` markers found in the phase's modified files (`src/nativespeaker/api/auth/firebase.py`, `auth/adapters.py`, `errors.py`, `routers/auth.py`). No hardcoded empty returns feeding a real code path — `_revoke` and `revoke_refresh_tokens` return `None` intentionally per the design (confirmation is the call returning without raising, per D-03), and this is proven by tests asserting the SDK call actually fires with real arguments, not stubbed.

## Prohibitions (must_haves.prohibitions, judgment-tier)

All prohibitions across the five plans were judgment-tier. Spot-checked against the codebase directly rather than accepted from SUMMARY claims:

| Statement | Status | Evidence |
|-----------|--------|----------|
| A success response must never be sent for a revocation Firebase did not confirm | verified | Every raising arm in `_revoke` precedes any success path; `sign_out_all` returns 204 only after the awaited call completes without raising. |
| No log line/body carries subject, provider uid, or token | verified | `logger.info("sign_out_all_confirmed", identity_row_id=...)` is the only success log call; e2e case sweeps every field of every captured record across confirmed/refused/rejected outcomes and finds none. |
| No `getUser` call, no `providerData` read on this route | verified | `sign_out_all` calls only `revoke_with_retry`; `revoke_refresh_tokens`/`_revoke` never call `auth.get_user`. |
| No `checkRevoked` check added anywhere | verified | `grep -rn checkRevoked` under `src/` and `tests/` returns nothing. |
| No backend token, session, or generation counter introduced | verified | No `get_db` on the route; `grep -rn generation_counter` returns nothing. |
| No durable audit row/writer rebuilt | verified | No `audit.auth_events` insert anywhere touched by this phase; REQUIREMENTS.md explicitly records the audit half as inherited-closed. |
| No `[DEFAULT]` Firebase app created/reachable | verified | `app=` passed explicitly at every call site; unit test asserts recorded call carries the exact app object. |
| Specs directory not edited | verified | sha256 match confirmed directly. |
| No operation label added, migration not edited | verified | `git log` on `migrations/` shows no phase-46 commits; `core.auth_operation` untouched. |

## Human Verification Required

None required to certify the phase goal. One item is explicitly recorded (not hidden) as a standing production-only exposure that no automated test can resolve, and it does not block phase completion because it was flagged and accepted by design, not silently skipped:

### 1. Assumption A1 — real Firebase "no such user" mapping

**Test:** With Application Default Credentials present, call `firebase_admin.auth.revoke_refresh_tokens` for a uid deleted from the configured Firebase project.
**Expected:** `auth.UserNotFoundError` is raised, confirming the 401 `auth_required` arm (D-06) fires correctly in production.
**Why human:** Both suites script this exception directly rather than calling a live Firebase project; the mapping is verified only from installed SDK source and a corroborating upstream issue report, not from a live probe. This is documented explicitly in REQUIREMENTS.md as a production-only exposure with a known remedy, and was a deliberate, disclosed decision by the phase — not a gap the phase tried to hide.

This item is manual-only by construction (no live Firebase credential test path exists in this repository) and was already surfaced in `46-VALIDATION.md`'s "Manual-Only Verifications" table before verification began. It does not gate phase completion.

## Gaps Summary

No gaps found. All four ROADMAP success criteria (including the criterion 3 rewrite by plan 46-05) are verified against the actual codebase, not merely claimed in SUMMARY.md. All prohibitions hold. Both requirement IDs (SIGNOUT-01, SIGNOUT-02) are satisfied and correctly cross-referenced in REQUIREMENTS.md with dated, line-referenced amendment entries. All measured test counts reproduced independently by this verifier match the counts recorded in the plan summaries and REQUIREMENTS.md exactly (1281 unit / 15 sign-out e2e / 348 full e2e / ruff clean). The one item requiring human action (a live-credential probe against a deleted Firebase account) is a disclosed, non-blocking production-only exposure, not a phase defect.

---

*Verified: 2026-09-08*
*Verifier: Claude (gsd-verifier)*
