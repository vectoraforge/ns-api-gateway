---
phase: 48-narrow-identity-to-the-verified-pair
fixed_at: 2026-09-16T17:40:00Z
review_path: .planning/phases/48-narrow-identity-to-the-verified-pair/48-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 48: Code Review Fix Report

**Fixed at:** 2026-09-16T17:40:00Z
**Source review:** `.planning/phases/48-narrow-identity-to-the-verified-pair/48-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

Every gate ran in the main checkout on branch `gsd/v2.0-authentication-entitlements`, not in an
isolated worktree: the tools live in `.venv/` and the schema suite needs the live PostgreSQL that
this checkout is configured against, so the numbers below are reproducible from this tree.

## Fixed Issues

### WR-01: Body and vocabulary refusals now outrank the account-state rejections

**Files modified:** `.planning/WINDOWS.md`, `.planning/phases/48-narrow-identity-to-the-verified-pair/48-CONTEXT.md`
**Commit:** 2da5b3e
**Applied fix:** The record amendment, not the code reordering. D-06 and D-07 decided the shape the
code has, and `TestEveryRefusalLeavesNothingBehind` pins that a refused body issues no statement, so
reordering would undo a decided shape and could not restore create-user's 422 arm at all. Both
records now state the change in plain terms: on `/auth/challenge` and `/auth/create-user` a bad body
or an unknown operation is refused with 400 or 422 before the account state is read, where the same
request from a historical row or a blocked user answered 403 `account_unavailable` before. WINDOWS
entry 33 was amended in both of its representations, the table row and the JSON block.

The reviewer's note that D-07's own consequence does not ship is **confirmed in the code** and said
in one sentence in both amendments: `AuthService.complete` (`services/auth.py:81`) calls
`resolve` before `_complete`, so a historical row or a blocked user raises before
`challenge_store.claim` runs; `_reject_existing_identity` (`services/auth.py:374`) is reached only
from `create_user`, after the claim, on the racing re-resolution. D-07 itself was left untouched.
Two new cases added under WR-02 now pin this: `store.row.claimed_at is None` on both arms.

### WR-02: Nothing tested the row rejections on the two narrowed routes

**Files modified:** `tests/unit/test_challenge_endpoint.py`, `tests/unit/test_create_user_precedence.py`
**Commit:** b133bc0
**Applied fix:** Two cases per route, in the modules the finding names, on their own existing session
stubs. Each module gained the `_identity_row(identity_state=..., user_active=...)` helper that
`tests/unit/test_exception_handlers.py:337` already uses, two session fixtures and two client
fixtures.

- `TestTheRowRejectionsAreThisRoutesOwn` drives `/auth/challenge` with a historical row and with a
  blocked user, parametrized over every member of `AuthOperation`: 403 `account_unavailable`,
  `store.issued == []`, no commit.
- `TestTheRowRejectionsOutrankTheChallenge` drives `/auth/create-user` with the same two rows against
  a live issued handle: 403 `account_unavailable`, the logged result is `historical_identity` or
  `blocked_user`, and `store.row.claimed_at is None` with `store.consume_calls == 0`.

`_StubSession` in `test_create_user_precedence.py` took an optional `row`, and `_EmptyResult` became
`_StubResult(row)`; the app construction moved into `_client_for`, which the three client fixtures
share.

Checked empirically that the new cases are not vacuous: with `linked = None` substituted for both
`resolve` call sites (`routers/auth.py:63`, `services/auth.py:81`), the run is 23 failed / 63 passed
and every new case is among the failures. The source was restored with `git checkout --` before the
commit.

### WR-03: The cache-contract test's `same` assertion could no longer fail

**Files modified:** `tests/unit/test_app_wiring.py`
**Commit:** cec8eec
**Applied fix:** As the finding sketches. The handler returns
`{"resolved_user": str(linked.user.id), "subject": admitted.subject}` and the case asserts the whole
body against the user the test built and the subject the token was minted with. The tautological
`same` comparison is gone, and with it the test's read of `linked.identity.issuer` and
`linked.identity.subject`, which D-08 keeps out of `src/`.

Checked empirically: with `get_claims` returning a hardcoded subject, this case fails; it passes
again once the source is restored.

### WR-04: The schema harness dereferenced `resolve`'s `None` arm

**Files modified:** `tests/schema/test_claim_race.py`
**Commit:** c9dbcaf
**Applied fix:** The assertion the finding sketches, on the line after `resolve_identity`, so a
seeding failure or a subject typo names itself instead of surfacing as an `AttributeError` two lines
later.

## Verification

Run in the main checkout after the last commit:

- `.venv/bin/ruff check src tests` - All checks passed!
- `.venv/bin/ty check src` - All checks passed!
- `.venv/bin/pytest tests/unit -q -p no:cacheprovider` - 1925 passed (1915 before this run; the 10
  new cases are WR-02's two parametrized over four operations, plus two).
- `.venv/bin/pytest tests/schema/test_claim_race.py -q -p no:cacheprovider -m schema` - **30
  collected, 30 passed, 0 deselected.** The database on localhost:5432 was reachable and the module
  ran for real; this is not an all-deselected result.

No source file under `src/` was changed by any of the four fixes. The two temporary mutations used to
prove the new cases fail closed were reverted with `git checkout --` and are not in any commit.

---

_Fixed: 2026-09-16T17:40:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
