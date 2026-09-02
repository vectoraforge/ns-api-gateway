---
phase: 40-post-auth-upgrade-anonymous
plan: 04
subsystem: auth
tags: [fastapi, sqlmodel, postgres, row-lock, challenge, firebase, tracer]

# Dependency graph
requires:
  - phase: 40-01
    provides: "`AuthOperation` narrowed to the four challenge-bearing labels, so `not in AuthOperation` is a complete membership test"
  - phase: 40-02
    provides: "`UpgradeRefused` and its two silent leaves, and `CompletionRequest` as the one completion body"
  - phase: 40-03
    provides: "`google_linked_firebase_credential` and the e2e file this plan extends"
  - phase: 37-post-auth-create-user
    provides: "`AuthService.complete`, the sequence this plan shares rather than copies, and `insert_account`'s IntegrityError arm"
provides:
  - "`POST /auth/upgrade-anonymous`, narrowed at the route level to linked callers, spending a challenge and returning the provider the transaction settled on"
  - "`AuthService._complete`, the one completion sequence with an operation seam and a write seam; `complete` and `complete_upgrade` are its two one-line callers"
  - "`IdentitiesDB.lock_identity_and_user`, the inner-join `.with_for_update()` revalidation, and `IdentitiesDB.flip_provider`, the sole writer of both halves of the flip"
  - "`AuthService._consume_quietly`, the named non-raising spend that discharges D-17 in the shared rollback arm"
  - "the issuance handler's membership test against the enum, so every one of the four labels is issuable"
affects: [40-05, 40-06, 40-07, 40-08, 41-claim-anonymous-grant, 42-claim-registered-grant]

# Actuals (#2632) — same estimateTokens scale (chars/4) as the plan's estimate.
actuals:
  tokens: 14296
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A shared sequence parameterised by two seams — the operation checked for and the write performed — rather than a base class or a second service"
    - "A row lock expressed as `.with_for_update()` over a purpose-built inner join, never as raw SQL and never over the outer join a resolving read uses"
    - "A swallow that must not raise lives in its own named function, so no `try` is ever nested inside an `except`"
    - "An unbuilt branch of a shipped route raises a real refusal the phase already owns, never a not-yet-built marker"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/identities.py
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/routers/auth.py
    - tests/e2e/test_upgrade_anonymous.py
    - tests/unit/test_challenge_endpoint.py
    - tests/unit/test_app_wiring.py
    - tests/unit/test_conflict_classification.py

key-decisions:
  - "`_complete` returns the write seam's value, not `facts.provider`: `_apply_create_user` and `_apply_upgrade` each return the provider their transaction settled on, so 40-05's idempotent no-op can return the stored provider without changing the shared sequence"
  - "`flip_provider` captures `identity_row.provider` before the first assignment, because `ProviderAccountAlreadyLinked` must name the stored provider and the assignment has already overwritten it by the time the flush raises"
  - "`lock_identity_and_user` returns `| None` and the service converts it to `IdentityUnresolvable` — the existing fail-closed class for a broken link — rather than asserting a row that the barrier already proved exists"
  - "The unbuilt combinations raise `ProviderTransitionNotAllowed`, the 403 the phase already owns, so the shipped route never carries a not-yet-built marker; the exact list 40-05 must split is below"

patterns-established:
  - "The two seams of a challenge-bearing completion are a `Callable[[Identity, VerifiedProviderIdentity], Awaitable[IdentityProvider]]` and an `AuthOperation` — phases 41 and 42 add a completion by writing one seam function and one one-line caller"

requirements-completed: []

coverage:
  - id: D1
    description: "A linked caller with a stored-anonymous row and a live google read obtains an upgrade handle, spends it, and receives 200 with exactly `{\"identity_provider\": \"google\"}`"
    requirement: "UPGRADE-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheAnonymousToRegisteredHappyPath"
        status: pass
    human_judgment: false
  - id: D2
    description: "The flip is in place: the same identity row id carries the new provider and its confirmed uid afterwards, with exactly one identity row for the pair and the user row registered"
    requirement: "UPGRADE-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheAnonymousToRegisteredHappyPath (row id before == after, len(identities) == 1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The route admits only a linked identity, through its own route-level `get_linked_identity`, and is in neither permissive literal"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestEveryRouteIsAuthenticated (both named-route parametrizations)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The row lock is `.with_for_update()` over an inner join, and no second race arbiter appears in either edited module"
    requirement: "UPGRADE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheModuleUsesNoSecondRaceArbiter"
        status: pass
      - kind: other
        ref: "grep -in 'for update' over both modules returns nothing; grep -c isouter returns 1"
        status: pass
    human_judgment: false

# Metrics
duration: 38min
completed: 2026-09-02
status: complete
---

# Phase 40 Plan 04: The Anonymous-to-Registered Tracer Summary

**One path through every layer: `POST /auth/challenge` issues an upgrade handle, `POST /auth/upgrade-anonymous` spends it, and a stored-anonymous identity row is flipped in place to its real Google provider with its user row registered in the same transaction.**

## Performance

- **Duration:** ~38 min
- **Completed:** 2026-09-02
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- `AuthService.complete` is now a one-line caller of `_complete`, which takes the operation to check for and the write to perform. Everything between locate and spend is byte-identical in behaviour: the same pre-claim rejections in the same order consuming nothing, the same claim, the same deliberate commit before the provider call, the same retry-wrapped lookup, the same rollback-then-spend arm. `complete_upgrade` is its twin.
- `_complete` returns what the write seam returned, not `facts.provider`. On the create path they are equal by construction; on the upgrade path this is what lets 40-05's idempotent repeat return the *stored* provider without touching the shared sequence.
- `IdentitiesDB.flip_provider` issues both halves of the flip in the caller's transaction and commits nothing. It writes exactly `identity.provider`, `identity.provider_uid`, `identity.updated_at`, `user.registered_at`, `user.updated_at`, and `user.email` only when the stored value is still `None`. It never touches `display_name`, `identity_state`, `historical_at` or `free_grant_consumed_at`.
- `IdentitiesDB.lock_identity_and_user` is a new statement with an **inner** join and `.with_for_update()`. It is not a reuse of `resolve` — PostgreSQL refuses a row lock on the nullable side of an outer join, and the barrier has already served the outer join's purpose by the time the completion transaction opens. The module docstring now declares its lock order, the way `crud/grants.py` declares its own.
- D-17 is discharged in the shared arm: the swallow moved out of a `try` nested inside an `except` and into `_consume_quietly`, a named function whose whole job is not raising. No status code, log event or consumption disposition moved with it — the `challenge_consume_failed` line and its two fields are unchanged.
- The issuance handler now tests membership against the enum and passes the caller's operation through it, so all four labels are issuable. Both existing comments and the `no-store` response block are unchanged; D-10's account-less condition is untouched and remains 40-06's.

## Task Commits

1. **Task 1 (tracer): End-to-end anonymous-to-registered upgrade** — `1f7a426`
2. **Task 2: The two ratchets the new route makes claims about** — `3cab83f`

The tracer feedback gate ran between them: `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q` was re-run against the committed tree and reported 4 passed before any expansion work began.

## Files Created/Modified

- `src/nativespeaker/api/crud/identities.py` — the two-line module docstring carrying the lock-order declaration, `lock_identity_and_user`, `flip_provider`, and the `ProviderAccountAlreadyLinked` import
- `src/nativespeaker/api/services/auth.py` — the `Write` seam alias, `complete`/`complete_upgrade` as one-line callers, `_complete`, `_apply_create_user`, `_apply_upgrade`, `_consume_quietly`, and three new imports
- `src/nativespeaker/api/routers/auth.py` — the module docstring, the membership test and enum-valued `operation=` argument, and the `upgrade_anonymous` handler with `sync`'s narrowing comment
- `tests/e2e/test_upgrade_anonymous.py` — `upgrade_client`, `_auth`, the two scripted constants, and `TestTheAnonymousToRegisteredHappyPath`
- `tests/unit/test_challenge_endpoint.py` — `claim_anonymous_grant` removed from `_NOT_ISSUABLE`, and the issued-operations case parametrized off `AuthOperation`
- `tests/unit/test_app_wiring.py` — `/auth/upgrade-anonymous` added to both named-route parametrizations
- `tests/unit/test_conflict_classification.py` — two docstring lines recording that the upgrade path's lock is revalidation, not arbitration

## The combinations that currently reach the placeholder raise

`_apply_upgrade` refuses with `ProviderTransitionNotAllowed` whenever the stored provider is not `anonymous` **or** the live provider is `anonymous`. Crossed against the case matrix (RESEARCH § Architecture Pattern 3), the branch is the *final* class for some of those and a *placeholder* for the rest. Plan 40-05 needs the second list, so both are written out.

**Reaches the placeholder and is currently answered wrongly — 40-05's work:**

| stored | live | uid comparison | what it must become |
|---|---|---|---|
| `anonymous` | `anonymous` | — | `NotLinked(cause="empty")` → 403. The client called before its own linking finished; it is recoverable, and the placeholder currently names it as drift. |
| `google` | `google` | uid equal | 200 with `{"identity_provider": "google"}` — D-04's idempotent no-op, currently a 403. |
| `apple` | `apple` | uid equal | 200 with `{"identity_provider": "apple"}` — the same no-op, currently a 403. |

**Reaches the same branch and is already the class it will keep — 40-05 splits the condition, not the class:**

| stored | live | uid comparison |
|---|---|---|
| `google` | `google` | uid differs |
| `apple` | `apple` | uid differs |
| `google` | `apple`, or `anonymous` | — |
| `apple` | `google`, or `anonymous` | — |

The branch does **no uid comparison at all** today, which is exactly why the two idempotent rows above fall into it. That comparison is the single condition 40-05 must add to separate the first table from the second.

Two other arms exist and are not placeholders: `ProviderAccountAlreadyLinked` is raised from `flip_provider`'s `IntegrityError` catch and is reachable today (stored `anonymous`, live `google`/`apple` whose `(issuer, provider, provider_uid)` triple is already held), and `IdentityUnresolvable` is raised when the locked read finds no row — unreachable in practice, since identity rows are never deleted and the user row is `ON DELETE RESTRICT`.

## Decisions Made

- **`_complete` returns the seam's value.** The plan required it and the reason is worth restating: a shared seam that returned `facts.provider` would, on 40-05's idempotent repeat, report the live read rather than what the transaction settled on — laundering a divergence into a success. Both seams return an `IdentityProvider`, and the `Write` type alias states that as a signature rather than a convention.
- **`flip_provider` captures the stored provider before assigning.** `ProviderAccountAlreadyLinked` carries the stored and live provider names (D-06), but by the time the flush raises, `identity_row.provider` already holds the new value. One local read at the top of the method is the whole fix; the alternative — passing the stored provider in as a parameter the caller already has — would let a caller pass a value that disagrees with the row.
- **The absent-row arm raises `IdentityUnresolvable`.** `lock_identity_and_user` returns `| None` like every other read in the module rather than asserting. `IdentityUnresolvable` is the existing fail-closed class for exactly this shape of broken state; no new class was introduced for a branch that cannot be reached.
- **The challenge-endpoint edit widened the positive case rather than leaving it pinned.** `_NOT_ISSUABLE` named `claim_anonymous_grant`, which the membership test makes issuable, so removing it was forced. Removing it alone would have dropped that operation's coverage entirely, so the positive case was parametrized off `AuthOperation` — which is also the form 40-06's acceptance criteria require ("derived from the enum, not written out"). The class was renamed to the plural and its docstring corrected, because "the one value this route issues for today" had become false; the not-issuable comment, the anti-oracle class docstring and D-10's cases were left untouched for 40-06.

## Deviations from Plan

None on the code. Two notes:

- **[Rule 3 - Blocking] `.env` had to be copied into the worktree.** It is gitignored, so the parallel worktree was created without it and neither `tests/e2e` nor the DB-backed verification can run. Copied from the main checkout as the dispatch directed. Never staged, never committed — `git status --short` is empty at both commits.
- **The challenge-endpoint class was renamed and its docstring rewritten** (`TestTheIssuableOperation` → `TestTheIssuableOperations`). The plan asked for the two corrections and reserved the class's full restatement for 40-06; a class docstring reading "the one value this route issues for today" above a four-case parametrization would have been false, so the one line was corrected with it. 40-06's restatement is unaffected — its criterion is "strictly more cases than before this plan", and this plan leaves 4 where there was 1.

## Issues Encountered

None. RESEARCH Pitfalls 1 and 2 both predicted their failure modes exactly and both were avoided by construction: `.with_for_update()` does not match the forbidden `"for update"` literal, and the inner join was written as a new statement rather than a reuse of `resolve`. Pitfall 2 could only have surfaced against a real database, and the e2e case is what cleared it.

## Verification

| Gate | Result |
|---|---|
| `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q` | **4 passed, 0 skipped** (3 before this plan) |
| `uv run pytest -q` | **823 passed**, 327 deselected (819 before this plan) |
| `uv run pytest -m e2e -q` | 210 passed |
| `uv run pytest -m schema -q` | 117 passed |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed — the bar holds at 0 on every root |
| `/auth` route list | `['/auth/challenge', '/auth/create-user', '/auth/sync', '/auth/upgrade-anonymous']` |
| `grep -in "for update"` over both edited modules | nothing |
| `grep -c "with_for_update" src/.../crud/identities.py` | `1` |
| `grep -c "begin_nested"` over both edited modules | `0` and `0` |
| `grep -c "isouter" src/.../crud/identities.py` | `1` |
| `test_app_wiring.py --collect-only` | both named-route cases collect with id `[/auth/upgrade-anonymous]` |
| `/auth/upgrade-anonymous` on the `PREAUTH_CALLABLE_PATHS` line | `False` |
| `git diff tests/unit/test_conflict_classification.py` | two docstring lines; no `assert`, no parametrize argument changed |

## Known Stubs

One, and it is a deliberate, shipped refusal rather than a silent placeholder:

| Stub | File | Line | Reason |
|---|---|---|---|
| `_apply_upgrade`'s single refusal condition answers three combinations with the wrong class | `src/nativespeaker/api/services/auth.py` | the `ProviderTransitionNotAllowed` raise in `_apply_upgrade` | This is a tracer: only the flip path is built. The three combinations, and the uid comparison that separates them, are listed by name above and are plan 40-05's whole subject. The route never returns a not-yet-built marker — every unbuilt combination gets a real 403 `operation_not_allowed` that is indistinguishable to the client from the final one. |

No other stub: no hardcoded empty collection, no placeholder text, no unwired data source.

## Threat Flags

None new. The register's seven entries stand as written:

- **T-40-04-01 (tampering with the target provider/uid).** The body is exactly `{challenge_id}`; both written values come only from `lookup_with_retry`'s classified read. Nothing from the request reaches `flip_provider`.
- **T-40-04-02 (elevation of privilege on the route).** `Depends(get_linked_identity)` at the route level, plus `verify_binding` proving the presenter is the identity row the handle was issued to. Named in both wiring parametrizations and absent from both permissive literals.
- **T-40-04-03 (the two-row invariant).** One method issues both writes inside one transaction; there is no code path that can set `registered_at` without the provider or the reverse. 40-07's schema scan is the standing proof.
- **T-40-04-04 (denial of service).** The provider read runs strictly after the claim commit and strictly before `lock_identity_and_user` opens the write transaction, so no network call happens under a held lock.
- **T-40-04-05 (challenge replay).** Unchanged: the claim is the sole serialisation point, and every outcome at or after the provider call spends the handle through the same two call sites, with no branch on which outcome it was.
- **T-40-04-06 (the provider-account triple).** The partial unique index is the arbiter; `flip_provider` catches its breach and converts it without naming a constraint, parsing a message or opening a savepoint.
- **T-40-04-SC (package installs).** Unreachable — nothing installed, `pyproject.toml` untouched.

## User Setup Required

None — no external service configuration required beyond the `.env` the environment already carries.

## Next Phase Readiness

- **40-05** owns the two tables under "the combinations that currently reach the placeholder raise". The single condition to add is the `provider_uid` comparison; the class for the drift arms is already the right one, and the shared sequence needs no change to accommodate either the idempotent 200 or `NotLinked(cause="empty")` — `_apply_upgrade` is the only function that moves.
- **40-06** inherits a membership test and an enum-derived positive parametrization. `_NOT_ISSUABLE` still carries `sync`, `sign_out_all` and `restore_subscription`, which are no longer enum members at all — the comment above the list still calls them "members of the operation vocabulary whose phases are unbuilt", which is now false and is 40-06's to rewrite.
- **41 and 42** add a completion by writing one seam function of type `Write` and one one-line caller beside `complete_upgrade`. Nothing in `_complete` should need to change again.

---
*Phase: 40-post-auth-upgrade-anonymous*
*Completed: 2026-09-02*

## Self-Check: PASSED

- `.planning/phases/40-post-auth-upgrade-anonymous/40-04-SUMMARY.md` — FOUND
- All seven modified source and test files — FOUND
- Commits `1f7a426`, `3cab83f`, `f63ecd7`, `ceec8dd` — all FOUND in `git log`
- `.env` present in the worktree, gitignored, and absent from every commit; working tree clean
