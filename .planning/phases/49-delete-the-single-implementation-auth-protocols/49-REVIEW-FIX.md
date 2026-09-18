---
phase: 49-delete-the-single-implementation-auth-protocols
fixed_at: 2026-09-18T02:07:00Z
review_path: .planning/phases/49-delete-the-single-implementation-auth-protocols/49-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 49: Code Review Fix Report

**Source review:** `49-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 13 (8 warnings, 5 info; `fix_scope: all`)
- Fixed: 13 (12 commits; IN-02 rode WR-03's commit, IN-05 needed no change)
- Skipped: 0

## Where the gates ran

Every edit, test run and commit happened in an isolated git worktree at
`.claude/worktrees/rf-49-3940992-1789694724`, on branch `gsd-reviewfix/49-3940992`,
fast-forwarded into `gsd/v2.0-authentication-entitlements` at the end.

The worktree has no `.venv`, so the gates ran with the main checkout's interpreter
(`/home/init/native-speaker/ns-api-gateway/.venv`) over `PYTHONPATH=<worktree>/src`.
That ordering was verified before the first gate: `nativespeaker.api.routers.auth`
resolved to the worktree file, not to the editable install's
`src/` in the main checkout. `ty` ran with `--python <main>/.venv`.

That reproducibility was then checked rather than claimed: after the fast-forward, every
gate was re-run in the main checkout against its own `.venv`, with no `PYTHONPATH`
override. All five results are identical to the worktree run.

## Gate results

Each row was measured twice — once in the worktree, once in the main checkout after the
fast-forward — and both runs agree.

| Gate | Baseline (`fa73ccf`) | After |
|---|---|---|
| `ruff check` | clean | clean |
| `ty check` (whole project) | 306 diagnostics | **295** |
| `ty check tests/e2e/test_challenge_store.py` | 16 (22 at review HEAD) | **12** |
| `pytest tests/unit` | — | 1906 passed |
| `pytest tests/schema -m schema` | — | 297 passed |
| `pytest tests/e2e -m e2e` | — | 360 passed, 1 failed |

The one e2e failure is
`test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`.
It was reproduced in the **unmodified main checkout at `fa73ccf`**, so it is
pre-existing and is not caused by any fix here. It touches the restore path, which
no fix in this report goes near.

## Fixed Issues

### WR-01: The challenge handler constructs a crud class in its body

**Files modified:** `src/nativespeaker/api/app/dependencies.py`, `src/nativespeaker/api/routers/auth.py`
**Commit:** `a4be3cd`
**Applied fix:** Added `get_challenges_db` beside `get_purchases_db` and injected it into
`issue_challenge`, which now calls `challenges_db.issue(...)` instead of `ChallengesDB(session).issue(...)`.

Scope check before editing: `git log -L 58,68` on the handler shows
`IdentitiesDB(session)` on line 60 unchanged across both phase-49 commits (`6e4d3d7`,
`46a92ad`), so it is existing code and falls under AGENTS.md's "the rule binds new
code; leave the existing services as they are". Only the `ChallengesDB` construction
was new, and only it was changed.

### WR-02: AGENTS.md still lists the module this phase deleted

**Files modified:** `AGENTS.md`
**Commit:** `b3005f0`
**Applied fix:** Dropped `adapters.py` from the `auth/` package map. Confirmed against
the seven modules on disk.

### WR-03: The session-holding constructor forces fourteen call sites to fabricate a session

**Files modified:** `src/nativespeaker/api/crud/challenges.py`, `src/nativespeaker/api/services/auth.py`, `tests/unit/test_challenge_ids.py`, `tests/e2e/test_challenge_store.py`
**Commit:** `1150793`
**Applied fix:** `verify_binding` moved from a `ChallengesDB` method to a module-level
function, unchanged in body. `services/auth.py:148` calls it directly. All fourteen
test sites dropped their fabricated session; the five e2e sites no longer open a
PostgreSQL transaction that issues no statement.

Measured: whole-project `ty` fell 306 → 297 on this change alone.
`tests/unit/test_challenge_ids.py` went from reporting diagnostics to `All checks passed`.
The 32 e2e challenge-store tests pass.

`verify_binding` is imported from `crud.challenges` directly rather than added to
`crud/__init__.py`, whose `__all__` is a registry of crud classes.

### WR-04: The ten ty suppressions hide the check the phase's own annotations added

**Files modified:** `tests/schema/test_create_race.py`, `tests/schema/test_create_atomicity.py`, `tests/schema/test_claim_race.py`, `tests/unit/test_conflict_classification.py`, `tests/unit/test_create_user_rollback.py`
**Commit:** `e2d8e6a`
**Applied fix:** Two parts, and **all ten marks are gone** (verified by grep: zero
`ty: ignore[invalid-argument-type]` left in the five files).

1. `_ScriptedAdapter` now subclasses `FirebaseAdminLookup`, `_NeverSetDevice` subclasses
   `AppleDeviceCheck`. Bodies unchanged.
2. Every `adapter=None` / `devicecheck=None` became a real, correctly typed instance that
   fails closed with no vendor call: `FirebaseAdminLookup({})` — already the codebase's own
   idiom for this, asserted at `test_firebase_adapter.py:249,294` — and a local
   `_unreached_devicecheck()` returning `AppleDeviceCheck(key_id=None, team_id=None,
   private_key=None, client=httpx.AsyncClient())`, which raises `Unavailable` in
   `_service_jwt` before any request is sent.

No new doubles invent behaviour; both reuse the production fail-closed path.

**The restored checking was verified empirically, not assumed.** Dropping the
`subject` parameter from `_ScriptedAdapter.get_user_provider_data` raises
`test_create_race.py`'s diagnostic count from 5 to 6; with the mark in place that drift
was invisible. The edit was reverted immediately after measuring.

Per-file `ty` counts are **identical to baseline** — 5, 14, 14, 2, 0 — so removing the
ten marks surfaced no hidden error, including no `db=` mismatch at the two sites where
one mark covered three arguments.

Rejected on the merits: widening `AuthService.__init__` to `FirebaseAdminLookup | None`
(the review's alternative). `get_auth_service` always supplies both in production, so
the optionality would exist only for tests, and every `self.adapter` use inside the
service would then need narrowing.

### WR-05: Six new unsuppressed ty errors of the rule suppressed elsewhere

**Files modified:** `tests/e2e/test_challenge_store.py`
**Commit:** `d88a96e` (five of the six were fixed at the root by `1150793`)
**Applied fix:** Five went with WR-03. The sixth, at the `locate` call, now binds the row
and asserts it before reading `.challenge_id`.

Measured: this file reported 22 diagnostics at HEAD against a baseline of 16. It now
reports **12** — below baseline. All six new ones are gone.

### WR-06: A new ty ignore directive is unused

**Files modified:** `tests/unit/test_firebase_adapter.py`
**Commit:** `991d70b`
**Applied fix:** Deleted the `# ty: ignore[unresolved-attribute]` mark at the
`email_verified` assignment. `unused-ignore-comment` for this file is now zero. The
load-bearing sibling mark at the frozen-instance assignment was left in place.

### WR-07: A package-wide `store` fixture collides with a same-named module helper

**Files modified:** `tests/unit/conftest.py`, `tests/unit/test_claim_precedence.py`, `tests/unit/test_claim_precedence_registered.py`, `tests/unit/test_create_user_precedence.py`, `tests/unit/test_upgrade_precedence.py`
**Commit:** `e75155c`
**Applied fix:** The conftest fixture is renamed `store` → `challenges_db`, with its 335
uses in the four precedence suites renamed with it.

Scope was established by AST, not by grep: exactly four modules take the conftest
fixture. `test_challenge_endpoint.py` and `test_create_user_body.py` also have a `store`
parameter but declare their **own** module-level `store` fixture that shadows the
conftest one, so both were deliberately left untouched. Every one of the 335 renamed
occurrences was first classified as `store.<attr>` (214) or parameter/argument (121);
none was prose.

**The hazard was verified closed.** A throwaway test in `tests/unit/` declaring `store`
as a parameter now fails with `fixture 'store' not found`; before the rename it would
have silently received the fake with `locate`, `claim` and `consume` replaced. The probe
file was deleted.

### WR-08: One adapter parameter was left unannotated

**Files modified:** `src/nativespeaker/api/routers/auth.py`
**Commit:** `f3d7b1a`
**Applied fix:** `sign_out_all`'s `adapter` is now `adapter: FirebaseAdminLookup =
Depends(get_firebase_adapter)`, so the annotation on `revoke_with_retry` is checked at
the only place in `src/` that calls it.

### IN-01: Two dependency docstrings name a seam that no longer exists

**Files modified:** `src/nativespeaker/api/app/dependencies.py`
**Commit:** `171d4ab`
**Applied fix:** "The Firebase lookup the lifespan built." / "The DeviceCheck adapter the
lifespan built." The second docstring's trailing "declared like its Firebase sibling
above" went with it, since AGENTS.md forbids a docstring that describes code elsewhere.

### IN-02: `ChallengesDB`'s docstring undercounts its own methods

**Files modified:** `src/nativespeaker/api/crud/challenges.py`
**Commit:** `1150793` (with WR-03)
**Applied fix:** Resolved at the root rather than by editing the sentence. With
`verify_binding` moved out, the class exposes exactly `issue`, `locate`, `claim`,
`consume`, so "The four operations. No method commits." is now the count.

### IN-03: `__repr__` renders a call the constructor no longer accepts

**Files modified:** `src/nativespeaker/api/crud/challenges.py`
**Commit:** `96a8157`
**Applied fix:** Deleted. Nothing asserts it, and it claimed state the object does not
hold.

The DSN concern that motivated the override was checked before deleting:
`repr(ChallengesDB(...))` now yields `<nativespeaker.api.crud.challenges.ChallengesDB
object at 0x...>`, which renders no attribute, so the session still cannot reach a log.

### IN-04: The value type sits behind the Firebase SDK import

**Files modified:** `src/nativespeaker/api/auth/firebase.py`, `src/nativespeaker/api/schemas/auth.py`, `src/nativespeaker/api/services/auth.py`, and 11 test files
**Commit:** `0ee572f`
**Applied fix:** Took the first of the review's two options — moved
`VerifiedProviderIdentity` to `schemas/auth.py`, where AGENTS.md puts domain value types
and where `LinkedIdentity`, an identically shaped frozen slotted dataclass, already
lives. The 11 import sites were rewritten by AST, then `ruff --fix` normalised ordering.

No import cycle: `schemas/auth.py` imports only `tables/` plus stdlib and pydantic, and
nothing in `schemas/` imports `auth/`.

**The decoupling was verified, not assumed:** importing
`nativespeaker.api.schemas.auth` leaves `firebase_admin` out of `sys.modules`. A second
provider adapter, a schema or a crud class can now name the type without pulling in the
SDK.

The machine-checked shape guard in `test_auth_package_shape.py` fired on the move, as
designed, and its recorded tuple is rewritten `(7, 20, 60)` → `(7, 19, 60)`.

### IN-05: A stale build artifact still lists the deleted module

**Files modified:** none
**Commit:** none — no change was required
**Applied fix:** Verified the condition the finding asks for rather than assuming it.
`src/ns_api_gateway.egg-info/` is not tracked (`git ls-files` matches zero paths) and is
ignored by `.gitignore:7` (`*.egg-info/`). The finding's own remedy — "it should not be
tracked if it is" — already holds.

## Residual items for a human

1. **IN-04's two deleted guards are still unreplaced.** The move makes the SDK coupling
   structurally absent and that was measured, but no *test* now guards it. The deleted
   `test_the_source_imports_only_the_stdlib_and_this_project` does not transplant as
   written, because `schemas/auth.py` legitimately imports pydantic. A replacement would
   have to assert "no vendor SDK", not "stdlib only". Writing that guard plus the control
   case this codebase pairs with its guards is new test design, which is beyond a review
   fix; it is left for a decision.
2. **The pre-existing e2e failure** in `test_restore_subscription.py` is unrelated to
   phase 49 and was failing at `fa73ccf`. It is untouched here.
3. **`ty` still reports 295 diagnostics** project-wide. That is 11 fewer than the 306
   baseline, but the remaining count is pre-existing and outside this review's findings.

---

_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
