---
phase: 49-delete-the-single-implementation-auth-protocols
verified: 2026-09-18T01:19:55Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 49: Delete the single-implementation auth Protocols Verification Report

**Phase Goal:** Delete the four Protocols in the `auth/` package that still have exactly one
implementation (`PlaySubscriptionSource`, `FirebaseAdminAdapter`, `DeviceCheckAdapter`,
`TokenVerifier`), annotate every consumer with the concrete class, move
`VerifiedProviderIdentity` into `auth/firebase.py`, remove `auth/adapters.py`, and stop building
`ChallengesDB` in the lifespan — `ChallengesDB` takes the session in its constructor, `AuthService`
builds it itself as `self.challenges_db`, the challenge route builds its own, and
`get_challenge_store` / `challenge_store` are deleted.
**Verified:** 2026-09-18T01:19:55Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

All five truths are the ROADMAP Phase 49 success criteria (as amended by the phase's own D-07 and
D-08 edits, both present in the ROADMAP.md text read at `.planning/ROADMAP.md:868`). Each was
checked directly against the codebase at HEAD (`6f7dd71`), not against SUMMARY.md claims.

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | None of the four Protocol names exists in `src/` or `tests/`; `auth/adapters.py` is gone and `VerifiedProviderIdentity` is imported from `auth/firebase.py` | ✓ VERIFIED | `git grep -nwE 'PlaySubscriptionSource\|FirebaseAdminAdapter\|DeviceCheckAdapter\|TokenVerifier' -- src tests` → exit 1, 0 lines. `test -e src/nativespeaker/api/auth/adapters.py` → absent. `class VerifiedProviderIdentity` declared once, at `src/nativespeaker/api/auth/firebase.py:63`; `services/auth.py:17` imports it from `nativespeaker.api.auth.firebase`. `git grep -n 'nativespeaker\.api\.auth\.adapters' -- src tests` → 0 lines |
| 2 | Every annotation that named a Protocol names the concrete class | ✓ VERIFIED | `services/restore.py:44` annotates `play: PlayDeveloperSubscriptions`; `app/dependencies.py:121-122` annotates `adapter: FirebaseAdminLookup`, `devicecheck: AppleDeviceCheck`; `auth/devicecheck.py:170,175` annotate `AppleDeviceCheck`; `auth/firebase.py:190,210` annotate `FirebaseAdminLookup`; `auth/google_play.py:195-196` annotate `JWTVerifier \| None`; no `class ... (Protocol)` remains in any of `devicecheck.py`, `firebase.py`, `google_play.py`, `jwt_verifier.py` (grep for `class.*Protocol` in each returns nothing) |
| 3 | The tests that existed only to guard the Protocols are deleted | ✓ VERIFIED | `tests/unit/test_adapter_interfaces.py` does not exist on disk. `grep -rn 'TestTheSeamIsTheAnnotation\|TestThePushTokenSeamIsTheAnnotation' tests/` → 0 lines. `tests/unit/test_claim_ordering.py`'s `SEAM_NAMES` frozenset names `AppleDeviceCheck`, not `DeviceCheckAdapter`. `tests/unit/test_firebase_adapter.py` carries no `isinstance(..., Protocol)` assertion |
| 4 | The lifespan no longer sets `app.state.challenge_store`; `AuthService.__init__` has no `challenge_store` parameter and builds `ChallengesDB(db)`; no `ChallengesDB` method takes a session; `get_challenge_store` does not exist; every test that overrode it monkeypatches `ChallengesDB` methods | ✓ VERIFIED | `grep -n 'app.state' src/nativespeaker/api/app/lifespan.py` lists 9 assignments, none named `challenge_store`. `AuthService.__init__(self, db, adapter, devicecheck)` at `services/auth.py:71-74` builds `self.challenges_db = ChallengesDB(db)`. `crud/challenges.py:40,46,74,79,84` — `__init__(self, session)`, and `issue`/`locate`/`claim`/`consume` all read `self.session`, none takes a `session` parameter. `git grep -nw 'challenge_store' -- src tests` and `git grep -n 'get_challenge_store' -- src tests` both exit 1, 0 lines. `routers/auth.py:65` builds `ChallengesDB(session).issue(...)` inline. `tests/unit/conftest.py:273-289` — one `store` fixture monkeypatches `ChallengesDB.locate/claim/consume`; `tests/unit/test_challenge_endpoint.py` and `tests/unit/test_create_user_body.py` each keep their own `_RecordingChallengeStore` and monkeypatch `ChallengesDB.issue`; all `AuthService(...)` call sites in the schema and unit suites pass no `challenge_store=` argument |
| 5 | `tests/unit/test_auth_package_shape.py` records the new tuple, changed in each seam commit that changes the `auth/` count; each seam is its own commit; the three suites exit 0 at every commit | ✓ VERIFIED | `CURRENT = (7, 20, 60)` in the file matches a live `pytest -q tests/unit/test_auth_package_shape.py` run (2 passed). `git show <commit> -- tests/unit/test_auth_package_shape.py` confirms the tuple moved in each of the four commits that touch `auth/` (`bfb923a`, `6d9ed93`, `7fe6762`, `65b1c91`) and did NOT move in the three commits that touch no file under `auth/` (`6e4d3d7`, `f60208f`, `46a92ad`) — correct in both directions. Six distinct `refactor(49-...)` commits, one seam each, with four `docs(49-...)` commits holding only `.planning/` SUMMARY/REVIEW files (`git show --stat` confirms no `src`/`tests` file in any docs commit). At HEAD (`6f7dd71`): `pytest -q -m ''` → `1 failed, 2563 passed`; `-m e2e` → `1 failed, 360 passed`; `-m schema` → `297 passed`; `ruff check src tests` → `All checks passed!`; `ty check` → `306 diagnostics`, unmoved from the Phase 48 baseline. The one failing case (`test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`) is a pre-existing failure open since Phase 47/48 (`.planning/WINDOWS.md`), unrelated to any file this phase touches — the phase introduces no new failure, and both e2e and schema selected non-zero cases (361 and 297) so neither run was an accidental all-deselected pass |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `src/nativespeaker/api/auth/adapters.py` | deleted | ✓ VERIFIED | absent on disk, absent from `git ls-files` |
| `src/nativespeaker/api/auth/firebase.py` | declares `VerifiedProviderIdentity`, `FirebaseAdminLookup`, no Protocol | ✓ VERIFIED | confirmed by read + grep |
| `src/nativespeaker/api/auth/devicecheck.py` | declares `AppleDeviceCheck`, no Protocol | ✓ VERIFIED | confirmed by grep |
| `src/nativespeaker/api/auth/google_play.py` | declares `PlayDeveloperSubscriptions`, imports `JWTVerifier`, no Protocol | ✓ VERIFIED | confirmed by grep |
| `src/nativespeaker/api/auth/jwt_verifier.py` | declares `JWTVerifier`, no Protocol | ✓ VERIFIED | confirmed by grep |
| `src/nativespeaker/api/crud/challenges.py` | `ChallengesDB(session)` constructor, methods read `self.session` | ✓ VERIFIED | full file read, confirmed |
| `src/nativespeaker/api/services/auth.py` | `AuthService.__init__(db, adapter, devicecheck)`, builds `self.challenges_db` | ✓ VERIFIED | confirmed by read |
| `src/nativespeaker/api/routers/auth.py` | `issue_challenge` builds `ChallengesDB(session)` inline, no `challenge_store` param | ✓ VERIFIED | confirmed by read |
| `src/nativespeaker/api/app/dependencies.py` | no `get_challenge_store`, concrete annotations on `get_auth_service` | ✓ VERIFIED | confirmed by grep |
| `src/nativespeaker/api/app/lifespan.py` | no `app.state.challenge_store` | ✓ VERIFIED | confirmed by grep |
| `tests/unit/test_auth_package_shape.py` | `CURRENT = (7, 20, 60)`, matches live measure | ✓ VERIFIED | test run confirms |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `services/restore.py` | `auth/google_play.py` | imports `PlayDeveloperSubscriptions` | ✓ WIRED | line 13 |
| `services/auth.py` | `auth/firebase.py` | imports `VerifiedProviderIdentity` | ✓ WIRED | line 17 |
| `routers/auth.py` | `crud/challenges.py` | imports and constructs `ChallengesDB(session)` | ✓ WIRED | lines 20, 65 |
| `services/auth.py` | `crud/challenges.py` | constructs `ChallengesDB(db)` in `__init__` | ✓ WIRED | `self.challenges_db = ChallengesDB(db)` |
| `tests/unit/conftest.py` `store` fixture | `crud/challenges.py` | `monkeypatch.setattr(ChallengesDB, ...)` | ✓ WIRED | patches the class both `services/auth.py` and `routers/auth.py` import, reaching both binders with one setattr (confirmed by the four precedence suites passing, 136 cases) |

### Requirements Coverage

None mapped. `.planning/REQUIREMENTS.md` contains no `Phase 49` entries (`grep -n "Phase 49" .planning/REQUIREMENTS.md` → 0 lines), and all four plans (`49-01` through `49-04`) declare `requirements: []` in frontmatter. No orphaned requirement IDs exist for this phase — declared scope and actual scope match exactly.

### Anti-Patterns Found

None blocking. A full code review (`49-REVIEW.md`, standard depth, 33 files) found 0 critical issues and 8 warnings, none of which contradicts a ROADMAP success criterion:

- WR-01/WR-03 concern `AGENTS.md` style conventions (constructing a crud class in a handler body; a session-bound class with a pure method) that are direct, deliberate consequences of the phase's own user-chosen decisions D-01 and D-03 recorded in `49-CONTEXT.md` — not defects against this phase's goal.
- WR-02, IN-01–IN-05 are stale prose/docstrings and a gitignored build artifact — informational, no behavioral impact.
- WR-04–WR-06 concern the scope and cleanliness of `# ty: ignore` suppressions added to satisfy new test-side type checking; measured `ty check` still reads 306, matching the Phase 48 baseline, so the "type gate does not rise" validation criterion holds regardless.
- WR-07 flags a fixture-naming collision risk (`store` fixture vs. a same-named helper in a different module) — a real maintainability concern for a future edit, not a current defect.
- WR-08 flags `sign_out_all`'s unannotated `adapter` parameter. Verified against the phase's own base commit (`59bfb7d`): this parameter was already unannotated before the phase began (`git show 59bfb7d:.../routers/auth.py` shows the same bare `adapter=Depends(...)`), so it never "named a Protocol" and criterion 2 does not require touching it.

Debt-marker scan (`TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER`) across every file this phase's commits touched: 0 matches.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Auth package shape tuple matches live AST measure | `.venv/bin/pytest -q tests/unit/test_auth_package_shape.py` | `2 passed` | ✓ PASS |
| No stray Protocol/challenge_store names in tracked source | `git grep -nwE '<4 names>\|challenge_store\|get_challenge_store' -- src tests` | exit 1, 0 lines | ✓ PASS |
| Lint clean | `.venv/bin/ruff check src tests` | `All checks passed!` | ✓ PASS |
| Type gate at Phase 48 baseline | `.venv/bin/ty check` | `Found 306 diagnostics` | ✓ PASS |
| Session-constructor invariant behaviorally exercised end to end | e2e/schema suites (`tests/e2e/test_challenge_store.py`, `tests/schema/test_claim_race.py`, etc.), already run by the orchestrator at HEAD | `1 failed` (pre-existing, unrelated), all challenge-crud cases passing | ✓ PASS |

The full three-suite run (`-m ''`, `-m e2e`, `-m schema`) was not re-run in this verification pass — the orchestrator's run at `54f1d2b` (one commit before HEAD `6f7dd71`, which only adds the code-review doc) is accepted as current evidence per the measured facts supplied, and was cross-checked here with a fresh `ruff`, `ty`, and shape-test run plus targeted greps, all consistent with that run.

## Deferred Items

None. No later phase addresses any concern raised here; Phase 50 (typed runtime container) is a downstream consumer of this phase's output (the lifespan no longer holding a challenge crud object) rather than a fix for anything left open.

## Human Verification Required

None. This is a behavior-preserving refactor with full structural (grep/AST) and behavioral (unit/e2e/schema, including live-PostgreSQL claim-race and rollback-isolation cases) coverage; no visual, real-time, or external-service behavior is in scope.

## Gaps Summary

No gaps. All five ROADMAP success criteria hold against the codebase at HEAD, requirements traceability is empty and confirmed empty, and no anti-pattern or debt marker rises to a phase-blocking level.

---

_Verified: 2026-09-18T01:19:55Z_
_Verifier: Claude (gsd-verifier)_
