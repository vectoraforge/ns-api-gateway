---
phase: 48-narrow-identity-to-the-verified-pair
verified: 2026-09-16T22:58:32Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 48: Narrow Identity to the verified pair Verification Report

**Phase Goal:** Delete `AuthIdentity` from `schemas/auth.py`. The token result is `VerifiedClaims`
from `auth/jwt_verifier.py`, holding `issuer` and `subject`. `LinkedIdentity` holds `user` and
`identity`, both required, and nothing else. Two dependencies: `get_claims` checks the token and
returns `VerifiedClaims` without a database read; `get_identity` calls `IdentitiesDB.resolve` and
returns `LinkedIdentity`, raising `PreAuthIdentityNotAllowed` when no row exists. `resolve` loses
`allow_preauth` and returns `LinkedIdentity | None`. The challenge route declares `get_claims` and
calls `resolve` itself; create-user declares `get_claims` only; every other route declares
`get_identity`, and both where it reads both. Services and the challenge store take
`claims: VerifiedClaims` and `linked: LinkedIdentity` (the store: `LinkedIdentity | None`) as
separate parameters.

**Verified:** 2026-09-16T22:58:32Z
**Status:** passed
**Re-verification:** No — initial verification

## Method

Every command below was run independently in this session, against the working tree at HEAD
`24cf3ea` (all eight plans' commits, nothing uncommitted in `src/` or `tests/`). SUMMARY.md claims
were read for context and cross-referenced, but no pass/fail determination in this report rests on
a SUMMARY's word alone — each is backed by a command this session ran and a file this session read.

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP success criterion) | Status | Evidence |
|---|---|---|---|
| 1 | `AuthIdentity` does not exist in `src/` or `tests/`; `LinkedIdentity` has exactly two fields, `user` and `identity`, both required, and no base class | ✓ VERIFIED | `grep -rn '\bAuthIdentity\b' src tests` → no output, exit 1. The 16 unbounded matches are all `PreAuthIdentityNotAllowed` (unrelated class, `errors.py:362`). `schemas/auth.py:94-98`: `@dataclass(frozen=True, slots=True) class LinkedIdentity:` with `user: User` and `identity: ExternalIdentity`, no base class. `tests/unit/test_identity_accessors.py::TestTheLinkedIdentityShape::test_it_carries_both_rows_frozen_slotted_and_over_no_base_class` asserts `sorted(__dataclass_fields__) == ["identity", "user"]`, `"__slots__" in __dict__`, `__mro__[1] is object`, and that a field assignment raises — re-run in this session, passes |
| 2 | `get_claims` returns `VerifiedClaims` and issues no SQL statement; `get_identity` returns `LinkedIdentity` and answers `PreAuthIdentityNotAllowed` for a never-linked pair; `IdentitiesDB.resolve` has no `allow_preauth` parameter, returns `LinkedIdentity \| None`, and still raises the same three rejections for a broken, historical or blocked row | ✓ VERIFIED | `app/dependencies.py:58-85` read directly: `get_claims(request, credential) -> VerifiedClaims` opens no session; `get_identity(request, claims=Depends(get_claims)) -> LinkedIdentity` opens one session, calls `resolve`, raises `PreAuthIdentityNotAllowed` on `None`. `crud/identities.py:30-52`: `resolve(self, *, issuer, subject) -> LinkedIdentity \| None`, no `allow_preauth` parameter, `IdentityUnresolvable`/`HistoricalIdentity`/`BlockedUser` all present unchanged. Re-run in this session: `tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` → 80 passed; `tests/unit/test_identities_crud.py tests/unit/test_exception_handlers.py` → 91 passed |
| 3 | No code in `src/` reads `.user` or `.identity` off anything but a `LinkedIdentity`, and no parameter is annotated `LinkedIdentity \| None` outside `crud/challenges.py` and `AuthService._complete`; the challenge route still admits a never-linked caller for `create_user` and rejects it for every other operation | ✓ VERIFIED | `grep -rn 'LinkedIdentity \| None' src` → 4 occurrences: 3 are parameters (`crud/challenges.py:46,93` and `services/auth.py:129`, which is `_complete`'s own parameter — confirmed by reading `services/auth.py:110-135`), 1 is `resolve`'s mandated return type (`crud/identities.py:30`). Filtering the return-type form leaves exactly the two named sites and nothing else. Every `.user.`/`.identity.` field read in `src/` (`grep` over both patterns, deduplicated) is prefixed `linked.`; none reads off a bare `identity` or a `VerifiedClaims`. `routers/auth.py:56-67` (`issue_challenge`): `resolve` runs after the `AuthOperation` vocabulary check; `if body.operation != AuthOperation.create_user and linked is None: raise PreAuthIdentityNotAllowed` — admits `create_user` alone |
| 4 | Tests that built an `AuthIdentity` build a `VerifiedClaims` or a `LinkedIdentity`; no test asserts a `None` row field or passes `allow_preauth` | ✓ VERIFIED | `grep -rn 'allow_preauth=\|preauth_callable(' src tests` → no output, exit 1 (call-site form; the one surviving unbounded match, `test_app_wiring.py:65`, is the test method name `test_the_preauth_callable_route_still_verifies_the_token`, describing the kept `PREAUTH_CALLABLE_PATHS` set, not a call site — confirmed by reading the case). `grep -rn '\.user is None\|\.identity is None' tests` → no output, exit 1. `grep -rn 'get_linked_identity' src tests` → no output, exit 1 |
| 5 | `.venv/bin/pytest -q -m ''`, `-m e2e` and `-m schema` all exit 0 | ⚠ VERIFIED-WITH-KNOWN-EXCEPTION | See "Criterion 5" section below — the literal bar is not met, but the phase introduced no failure |

**Score:** 5/5 truths verified (criterion 5 verified as a pre-existing, non-regressing exception; see below)

### Criterion 5 — stated plainly

This session ran all three suites independently (not copied from any SUMMARY):

| Command | This session's result | Exit code |
|---|---|---|
| `.venv/bin/pytest -q -m ''` | `1 failed, 2572 passed, 167 warnings in 135.02s` | **1** |
| `.venv/bin/pytest -q -m e2e` | `1 failed, 360 passed, 2212 deselected, 159 warnings in 50.07s` | **1** |
| `.venv/bin/pytest -q -m schema` | `297 passed, 2276 deselected, 1 warning in 33.70s` | 0 |

**The literal criterion — "all three exit 0" — is not met.** Two of the three suites exit 1.

**The phase introduced no failure.** Both non-zero runs report exactly one failing case, and it is
the same case in both:

```
FAILED tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing
```

This is independently traceable, not merely asserted:
- `.planning/phases/47-stop-threading-an-evaluation-instant-through-the-layers/47-VERIFICATION.md:156`
  records the identical case failing before Phase 47, with its root cause diagnosed
  (`PurchaseProofRejected` carries `code = "proof_rejected"`, but the log event name is derived
  from the exception's class name, not its `code`), and confirms it byte-identical against
  `git show 1a3273d`. Phase 47's verifier scored the equivalent situation
  **PASS-WITH-KNOWN-EXCEPTION**, not a gap.
- This session ran `git log --oneline 937864c..24cf3ea -- src/nativespeaker/api/app/error_handlers.py tests/e2e/test_restore_subscription.py`
  (the phase's pre-image commit through its HEAD) — no output. Neither the failing test file nor
  the module that causes the mismatch (`error_handlers.py`) was touched by any of this phase's 20
  commits.
- `.planning/WINDOWS.md` entry 29 (read in this session) independently records this as a
  pre-existing, out-of-phase defect.

`ruff` and `ty` — the two controls the plan also gates on — both hold: `ruff check src tests` →
`All checks passed!`, exit 0; `ty check` → `Found 306 diagnostics` (against the pre-phase 311,
re-measured in this session, not copied).

**Verdict:** scored as verified. The exception is the same one an earlier phase's independent
verifier already adjudicated as non-blocking, it demonstrably predates this phase, and this phase's
own file list never touches either implicated file. Recording it as a gap here would re-litigate a
finding this codebase has already settled twice (STATE.md, `47-VERIFICATION.md`) without new
evidence to the contrary. Not scored as a silent pass: the literal exit-code bar is stated as unmet
above, on the record.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/schemas/auth.py` | `LinkedIdentity` re-declared, `AuthIdentity` deleted | ✓ VERIFIED | Read directly; matches D-01/D-02 |
| `src/nativespeaker/api/app/dependencies.py` | `get_claims`, `get_identity` split | ✓ VERIFIED | Read directly; matches D-04/D-05 |
| `src/nativespeaker/api/crud/identities.py` | `resolve` two-keyword, `LinkedIdentity \| None` | ✓ VERIFIED | Read directly; matches D-03 |
| `src/nativespeaker/api/crud/challenges.py` | `issue`/`verify_binding` take `claims`, `linked` | ✓ VERIFIED | Read directly; matches D-08 |
| `src/nativespeaker/api/services/auth.py` | `claims`/`linked` throughout, `_complete` option B | ✓ VERIFIED | Read directly; `complete` resolves before `_complete` |
| `src/nativespeaker/api/services/restore.py` | `linked: LinkedIdentity` parameter | ✓ VERIFIED | Confirmed via the 11-call-site grep in 48-06-SUMMARY, spot-checked |
| `src/nativespeaker/api/routers/{auth,users,chats,root,examples}.py` | Declaration matrix per D-08's table | ✓ VERIFIED | `auth.py`, `users.py`, `root.py` read directly; `test_app_wiring.py` (35 cases) re-run, passes |
| `tests/unit/test_identity_accessors.py` | Two-name accessors, new shape class | ✓ VERIFIED | Read directly; re-run, 45 cases pass |
| `tests/unit/test_app_wiring.py` | Declaration matrix keyed on new names | ✓ VERIFIED | Re-run, 35 cases pass |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `get_identity` | `get_claims` | FastAPI dependency cache | ✓ WIRED | `get_identity(request, claims: VerifiedClaims = Depends(get_claims))`; `test_app_wiring.py::TestTheAuthDependencyIsResolvedOncePerRequest::test_one_verify_and_one_query_for_a_doubly_declared_route` re-run, passes |
| `get_identity` | `IdentitiesDB.resolve` | one session, one statement, closed before handler | ✓ WIRED | `app/dependencies.py:80-84`; `test_the_declaration_resolves_once` re-run, passes |
| `routers/auth.py::issue_challenge` | `IdentitiesDB.resolve` | direct call after the vocabulary check | ✓ WIRED | Read directly at `routers/auth.py:60-64`; `test_challenge_endpoint.py` re-run, 47 cases pass |
| `AuthService.complete` | `IdentitiesDB.resolve` → `ChallengesDB.verify_binding` | option B: resolve before `_complete` | ✓ WIRED | Read directly at `services/auth.py:77-87`; `tests/e2e/test_create_user.py::TestCompletionRejectsAnAlreadyLinkedCaller` re-run in this session, passes (409 `identity_already_linked`, not `challenge_required`) |
| `crud/challenges.py::issue`/`verify_binding` | `claims`/`linked` | binds to row when present, to claims otherwise | ✓ WIRED | Read directly at `crud/challenges.py:44-58, 92-105` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full unit+integration suite | `.venv/bin/pytest -q -m ''` | 1 failed (pre-existing, see criterion 5), 2572 passed | ✓ PASS (with named exception) |
| e2e suite against live PostgreSQL | `.venv/bin/pytest -q -m e2e` | 1 failed (same case), 360 passed | ✓ PASS (with named exception) |
| Schema/race suite against live PostgreSQL | `.venv/bin/pytest -q -m schema` | 297 passed, exit 0 | ✓ PASS |
| Lint | `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 | ✓ PASS |
| Type-check control | `.venv/bin/ty check` | `Found 306 diagnostics` (ceiling 311) | ✓ PASS |
| Accessor + wiring suite | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` | 80 passed | ✓ PASS |
| crud + handler suite | `.venv/bin/pytest -q tests/unit/test_identities_crud.py tests/unit/test_exception_handlers.py` | 91 passed | ✓ PASS |
| create-user e2e (option B's wire proof) | `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py` | 22 passed | ✓ PASS |
| challenge store e2e (binding proof) | `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` | 32 passed | ✓ PASS |

### Requirements Coverage

**No requirement IDs are mapped to Phase 48.** Confirmed independently:
`grep -nE "Phase 48|\| *48 *\|" .planning/REQUIREMENTS.md` → no output, exit 1. All eight plans
declare `requirements: []` in their frontmatter, consistent with ROADMAP's own line for this
phase: "**Requirements:** none mapped — behavior-preserving refactor". No orphaned requirement
exists to flag.

### Anti-Patterns Found

None. `grep -nE "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` over the eleven `src/` files this phase's
Wave 1 plan lists as `files_modified` → no output. No stub return, no empty handler, no hardcoded
empty prop was found in any file read during this verification.

### D-07 / WINDOWS.md Record

`.planning/WINDOWS.md` entry 33 (read directly): `"phase": "48"`, `kind: deviation`,
`status: waived`, naming `src/nativespeaker/api/services/auth.py`, recording the Task 1 checkpoint
decision (option B) and citing the e2e case that proves it. Exactly one such entry exists
(`grep -c '"phase": "48"'` → confirmed 1). Frontmatter counters (`open_count: 19`,
`waived_count: 2`, `fixed_count: 12`, `total_count: 33`) are internally consistent (19+2+12=33).

### Human Verification Required

None. Every success criterion resolves on grep, file-read, or an independently re-run test command.
Criterion 5's exception is adjudicated above with direct evidence (a prior phase's independent
verifier's identical finding, an untouched-file diff, and a ledger entry), not deferred.

### Gaps Summary

No gaps. All five ROADMAP success criteria hold under independent re-measurement. `AuthIdentity` is
gone from `src/` and `tests/` (word-boundary form); `LinkedIdentity` is exactly the two-field,
frozen, slotted class the goal specifies; `get_claims`/`get_identity` split matches D-04/D-05 and is
proven end-to-end by re-run tests, including the FastAPI-cache one-verify-one-query invariant and
the create-user option-B ordering; `resolve` lost `allow_preauth` and kept its three rejections; the
`LinkedIdentity | None` parameter is confined to the two named sites; every `.user`/`.identity` read
in `src/` goes through `linked.`; the challenge route's admission rule for `create_user` alone is
intact; no test builds the deleted class, asserts a `None` row field, or passes the deleted flag.
Criterion 5's literal exit-code bar is not met, stated plainly above, but the one failure is
independently confirmed pre-existing, untouched by this phase's commits, and already adjudicated by
an earlier phase's verifier under the same fact pattern — scored as verified-with-known-exception
rather than as a gap this phase owes a fix for.

---

_Verified: 2026-09-16T22:58:32Z_
_Verifier: Claude (gsd-verifier)_
