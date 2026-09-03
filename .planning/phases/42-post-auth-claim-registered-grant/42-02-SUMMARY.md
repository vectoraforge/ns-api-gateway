---
phase: 42-post-auth-claim-registered-grant
plan: 02
subsystem: auth
tags: [route, grants, conversion, devicecheck, lock-order, tracer, d-01, d-09, d-10]
status: complete

requires:
  - "42-01 (seed_grant with no companion row; the three-row anonymous writer as the model)"
  - "AuthService._complete (the generic locate/claim/commit/post-claim/consume sequence)"
  - "AuthOperation.claim_registered_grant (already in the Python enum and the database type)"
provides:
  - "POST /auth/claim-registered-grant, serving both destinations end to end"
  - "GrantsDB.activate_registered_account_grant — the one writer of a registered_account_grant row"
  - "ClaimantNotRegistered — the fourth ClaimRefused leaf"
  - "GrantClaimRequest — the body both claim routes share"
  - "REGISTERED_TIER_ID in services/auth.py"
  - "The registered writer's emitted statements, captured and asserted against real PostgreSQL"
affects:
  - "plan 42-03 (its precedence matrix parametrizes the five destinations mapped below)"
  - "plan 42-04 (its single-writer and ordering walks read the writer and the claim written here)"
  - "plan 42-05 (its race classes drive complete_claim_registered_grant on two connections)"

tech-stack:
  added: []
  patterns:
    - "One crud writer with an internal destination branch, re-deciding inside the lock"
    - "An explicit flush boundary forcing the expiry ahead of the insert, kept as a version guard"
    - "Emitted SQL captured at before_cursor_execute, one sibling fixture per destination"

key-files:
  created:
    - tests/e2e/test_claim_registered_grant.py
  modified:
    - src/nativespeaker/api/crud/grants.py
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/routers/auth.py
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/schemas/auth.py
    - tests/schema/test_grant_locks.py
    - tests/unit/test_app_wiring.py
    - tests/unit/test_rejection_vocabulary.py

decisions:
  - "D-09 built whole in both layers: five destinations in the preflight, the same five re-decided inside the lock"
  - "One writer with an internal branch, per research Open Question 1 — one construction site for the registered source"
  - "AnonymousGrantClaimRequest renamed GrantClaimRequest rather than duplicated: three call sites, one fact"
  - "Research assumption A1 is measurably FALSE for SQLAlchemy 2.0.46 — the ORM emitted the UPDATE before the INSERT with the flush boundary removed. The boundary is kept anyway as the guard against an ORM upgrade inverting it"

metrics:
  duration: "~45 min"
  completed: 2026-09-03
  tasks: 2
  commits: 2

actuals:
  tokens: 30365
  tasks: 2
  commits: 2
---

# Phase 42 Plan 02: The Registered Grant Claim Summary

`POST /auth/claim-registered-grant` serves a real caller through every layer: a clean account gets a
new registered grant behind Apple's bit1, and an account holding an active anonymous device grant is
converted in one transaction that expires before it inserts.

## What Was Built

Six files carry the route. The body `GrantClaimRequest` (a rename of
`AnonymousGrantClaimRequest`, now used by both claim routes) reaches
`routers/auth.py::claim_registered_grant`, which is `claim_anonymous_grant`'s shape with a new path,
a new summary and a new service method. `AuthService.complete_claim_registered_grant` passes
`AuthOperation.claim_registered_grant` and a `partial` post-claim into the untouched `_complete`.
`_claim_registered_grant` runs D-09's decision, calls Apple on one arm only, and rolls back for the
race loser. `GrantsDB.activate_registered_account_grant` holds both destinations under the fixed lock
order. `ClaimantNotRegistered` is the fourth `ClaimRefused` leaf, and it adds no error code.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | End-to-end registered-grant claim, both destinations | `645da2d` | `crud/grants.py`, `services/auth.py`, `routers/auth.py`, `errors.py`, `schemas/auth.py`, `tests/e2e/test_claim_registered_grant.py`, `tests/unit/test_app_wiring.py`, `tests/unit/test_rejection_vocabulary.py` |
| 2 | The registered writer's emitted SQL | `8bf2996` | `tests/schema/test_grant_locks.py` |

## Verification

| Gate | Before | After |
|------|--------|-------|
| `pytest -m e2e tests/e2e/test_claim_registered_grant.py -q` | — | 6 passed, zero skipped |
| `pytest -m e2e -q` | 225 passed | 231 passed |
| `pytest -m schema -q` | 119 passed | 126 passed |
| `pytest -m schema tests/schema/test_grant_locks.py -q` | 8 collected | 15 passed |
| `pytest -q` | 952 passed | 957 passed |
| `ruff check src tests` | clean | clean |
| `ErrorCode` members | 18 | 18 |
| `routers/auth.py` module docstring | 3 lines, 5 routes | 3 lines, 6 routes |

Commands were run as `.venv/bin/python -m pytest` and `.venv/bin/ruff`, which is the same interpreter
`uv run` resolves to; the plan's `uv run` spellings were not otherwise altered.

## D-09's Five Destinations, Mapped to Both Layers

Plan 42-03 needs a list rather than a search. Line numbers are as committed at `8bf2996`.

| D-09 | Destination | `services/auth.py::_claim_registered_grant` | `crud/grants.py::activate_registered_account_grant` |
|------|-------------|--------------------------------------------|------------------------------------------------------|
| (a) | repeat | `:205` `if AccessGrantSource.registered_account_grant in sources:` → bare `return` | `:149` same test over `held` → `return False` |
| (b) | `OtherActiveGrantHeld` | `:208-209` `if any(source is not AccessGrantSource.anonymous_device_grant for source in sources):` | `:151-152` the same `any(...)` → `return False` |
| (c) | conversion | falls through `:211` `if not held:` (the block is skipped) into the writer call at `:224` | `:153` `superseded = grants[0] if grants else None`, then `:159` `if superseded is not None:` |
| (d) | new grant | inside `:211` `if not held:`, past the history read, through the two Apple calls at `:216-222` | `:153` leaves `superseded` as `None`, and `:170` builds the row with `carried is None` |
| (e) | `FreeGrantAlreadyConsumed` | `:213-214` `if await self.grants_db.has_prior_free_grant(...)` inside `if not held:` | `:155-156` `if superseded is None and await self.has_prior_free_grant(user_id):` |

Two absences are as load-bearing as the branches. The preflight never tests
`identity.identity.free_grant_consumed_at`, and it calls `has_prior_free_grant` only inside the arm
where no active grant is held — both are already true on the conversion path (Pitfall 4), so either
one used as a blanket guard would refuse the destination this phase exists to add. The refusal for
an anonymous caller is `:200-201`, the first statement of the post-claim work, tested positively
against `google` and `apple`; the writer repeats it at `:145-146` against the re-read row.

The Apple gate is reached from one place only, `:216-222`, inside `if not held:`. The conversion arm
never enters that block, which is what the e2e case's two empty call lists prove.

## Research Assumption A1 — Closed by Measurement, and It Is False

A1 read: *"SQLAlchemy orders INSERTs before UPDATEs within one flush, so the conversion needs an
explicit flush boundary or an `update()` statement."*

**Measured answer: no.** With the flush boundary removed from the conversion branch, so that the
expiry assignment and `session.add(activated)` fall into one flush, SQLAlchemy 2.0.46 (SQLModel
0.0.37) emitted the `UPDATE core.access_grants` **before** the `INSERT INTO core.access_grants`
against real PostgreSQL 17. The whole schema file stayed green (15 passed), and the six e2e cases
stayed green.

The recorded sequence for the conversion is identical with the boundary and without it:

```
[0] SELECT ... FROM core.access_grants ... ORDER BY core.access_grants.id ASC FOR UPDATE
[1] SELECT ... FROM core.user_monthly_usage WHERE grant_id = $1 FOR UPDATE
[2] SELECT ... FROM core.external_identities WHERE issuer = $1 AND subject = $2      -- plain
[3] UPDATE core.access_grants SET status=..., ends_at=..., updated_at=...
[4] INSERT INTO core.access_grants (...)
[5] INSERT INTO core.user_monthly_usage (...)
[6] UPDATE core.external_identities SET free_grant_consumed_at=..., updated_at=...
```

**The boundary is kept.** It buys one extra round trip per conversion and costs nothing else, and it
makes D-10's ordering a property of this writer rather than of an ORM internal that a version bump
could invert silently. If it ever inverted, every conversion would catch `IntegrityError`, return
false, and answer a stale 200 as though it had lost a race. The ordering case in
`tests/schema/test_grant_locks.py` asserts the emitted **order**, not the mechanism, so it stays the
standing detector whichever of the two mechanisms is producing that order.

## Mutation Testing — Three Mutations, and One That Did Not Bite

Every mutation was applied to `src/nativespeaker/api/crud/grants.py` alone and reverted with
`git checkout -- <path>`. `tests/schema/test_grant_locks.py` was never touched: its SHA-256 is
`4261b469…7060a9` both before and after the cycle, and `git status` after the last revert showed only
that one file modified (it was uncommitted at the time; it is committed unchanged as `8bf2996`).

**Mutation 1 — the plan's proposed one: remove the flush boundary so the ORM's default ordering
applies.**
Result: **no case failed.** 15 passed. This is the A1 finding above: two independent mechanisms were
producing the same order, so removing one of them changed nothing observable. Recorded rather than
worked around — a mutation that does not bite is evidence about the world, not a defect in the case.

**Mutation 1b — the violation the ordering case actually exists to catch: delete the three lines that
expire the anonymous row, so the conversion inserts without superseding.**
Result: **3 failed, 12 passed.**

| Node id | Observed failure |
|---------|------------------|
| `TestTheConversionExpiresBeforeItInserts::test_the_update_of_the_anonymous_row_precedes_the_insert_of_the_registered_one` | `AssertionError: no expiry statement was emitted at all, got [...]` / `assert -1 >= 0` |
| `TestTheConversionExpiresBeforeItInserts::test_the_usage_row_is_inserted_after_the_grant_it_belongs_to` | `AssertionError: assert 3 < -1` — `ix_access_grants_one_active_per_user` refused the insert, so the usage insert never ran |
| `TestTheRegisteredWriterAddsNoThirdLockTier::test_the_conversion_revalidates_the_identity_row_by_a_plain_re_read` | `assert False is True` — the writer returned false, so the "it wrote" control fired |

**Mutation 2 — add a third lock tier: `lock_identity_and_user` called before the plain re-read.**
Result: **3 failed, 12 passed.**

| Node id | Observed failure |
|---------|------------------|
| `TestTheRegisteredWriterAddsNoThirdLockTier::test_exactly_two_distinct_lock_tiers_are_taken_on_the_conversion` | `AssertionError: assert 3 == 2 where 3 = len({'core.access_grants', 'core.external_identities', 'core.user_monthly_usage'})` |
| `TestTheRegisteredWriterAddsNoThirdLockTier::test_the_conversion_locks_the_grant_rows_then_their_usage_rows` | the tier list gained `core.external_identities` |
| `TestTheRegisteredWriterAddsNoThirdLockTier::test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row` | same, on the clean-account arm |

## The Registered Source Is Named Twice in `crud/grants.py`

`ast` counts two `Attribute` reads of `registered_account_grant` in that module, both inside the new
writer: `:149`, the in-lock repeat test, and `:172`, the one
`AccessGrant(source=AccessGrantSource.registered_account_grant)` construction. Exactly one is a
construction. Plan 42-04's single-writer walk should baseline `== 2` inside the writer and `== 1` for
the construction site, and will need `NAMING_MODULES` for this member to be
`{crud/grants.py, services/auth.py, tables/grants.py, schemas/auth.py}` — `EntitlementType` spells
the member in the schema module as a string value, not off `AccessGrantSource`, so an
`_names_the_member`-shaped walk will not see it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `request.getfixturevalue` cannot resolve an async fixture inside a running loop**

- **Found during:** Task 2, first run of the new schema cases
- **Issue:** the plan's control was written once and parametrized over both arms via
  `request.getfixturevalue(arm)`. pytest-asyncio raised
  `RuntimeError: Runner.run() cannot be called from a running event loop`, because an async fixture
  requested lazily from inside an already-running test loop is set up with `asyncio.Runner.run`.
- **Fix:** split it into two named cases, one per arm, sharing a module-level
  `assert_one_plain_identity_re_read` helper. This is also closer to the plan's own instruction that
  each case be named for the fact it holds.
- **Files modified:** `tests/schema/test_grant_locks.py`
- **Commit:** `8bf2996`

**2. [Rule 1 - Bug] The identity re-read filter counted the writer's own identity UPDATE**

- **Found during:** Task 2, second run
- **Issue:** the control copied from the anonymous fixture filters statements by
  `"core.external_identities" in statement and "FOR UPDATE" not in statement`. That is exact for the
  anonymous writer, which returns false before writing anything, but the registered writer also
  emits `UPDATE core.external_identities SET free_grant_consumed_at=...` — which matches both terms.
  The case failed with `assert 2 == 1`.
- **Fix:** narrowed the filter to `statement.startswith("SELECT")`. The assertion is unweakened: it
  still counts exactly one non-locking read of that relation, and mutation 2 proves it bites.
- **Files modified:** `tests/schema/test_grant_locks.py`
- **Commit:** `8bf2996`

### Judgement Calls Inside Claude's Discretion

**The request model was renamed, not duplicated.** `GrantClaimRequest` replaces
`AnonymousGrantClaimRequest` at three sites: the class, the import in `routers/auth.py`, and the
anonymous handler's annotation. `hasattr(schemas.auth, 'AnonymousGrantClaimRequest')` is now `False`.
The one-line comment above `device_token` recording the Phase 41 review finding is unchanged.

**The two-lock-tier assertion lives on the conversion arm, and the clean-account arm has its own
case.** A clean account holds no grant row, so `lock_effective_grants` returns an empty list and
`lock_usage` is never called — one lock tier, not two. Asserting `len(set(taken)) == 2` on that arm
would have been false. `test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row` states
what is true there and still refuses `core.external_identities` and `core.users`; mutation 2 fails it.

**The conversion's seeded grant gets an explicit earlier `starts_at`.** `insert_grant` leaves
`starts_at` at `CURRENT_TIMESTAMP`, and the fixture's `evaluated_at` is taken a few milliseconds
later — almost certainly strictly greater, but not provably so, and `CHECK (ends_at IS NULL OR
ends_at > starts_at)` is strict (Pitfall 2). The fixture issues one extra setup `UPDATE` setting
`starts_at` an hour back. `tests/schema/helpers.py` was not modified.

### Acceptance Criteria, Read Literally

Every criterion in the plan was run. Two are worth stating exactly:

- `grep -c "except IntegrityError"` and `grep -c "try:"` over the comment-stripped `crud/grants.py`
  both return `3`, equal and at most `3` as required: the anonymous writer's one flush, and the
  registered writer's early conversion flush and its final flush. `begin_nested` and `commit()` both
  return `0`.
- `grep -c "session.refresh"` over the comment-stripped `services/auth.py` returns `1` — the
  pre-existing call inside `_complete`. The loser arm is `if not activated: await
  self.session.rollback()` and nothing after it, so the Phase 41 detached-instance defect is not
  reintroduced.

## Threat Model

| Threat ID | Disposition | Outcome |
|-----------|-------------|---------|
| T-42-02-01 | mitigate | Held. The stored provider is tested positively at `services/auth.py:200` and again at `crud/grants.py:145` against the re-read row; the e2e anonymous-caller case answers 403 with `{"code": "operation_not_allowed"}` and writes nothing. |
| T-42-02-02 | mitigate | Held. The guard is the history read by source and status at both layers; `free_grant_consumed_at` is read only to decide whether to set it, never to refuse. |
| T-42-02-03 | mitigate | Held, and now measured. The emitted order is `UPDATE core.access_grants` then `INSERT INTO core.access_grants`, asserted from captured SQL and mutation-tested. |
| T-42-02-04 | mitigate | Held. `GrantClaimRequest` carries two string fields; no bit value is read from the body, and the backend reads bits itself on every new-grant claim. |
| T-42-02-05 | mitigate | Held. One `device_token` field drives both Apple calls; the e2e case asserts the read list and the write list name the same token. |
| T-42-02-06 | mitigate | Held. `ClaimantNotRegistered` declares no status, no code, no `__init__` and no field; `ErrorCode` still carries 18 members and `tests/unit/test_rejection_vocabulary.py` enforces all four absences per arm across four arms now. |
| T-42-02-07 | mitigate | Held. Both Apple calls sit inside `if not held:` in the service, strictly before the writer opens its transaction; the writer's captured statements contain no I/O beyond the database. |
| T-42-02-08 | accept | As accepted (D-02). The conversion arm makes zero Apple calls, asserted by the e2e case's two empty lists. |
| T-42-02-09 | accept | As accepted (D-16). No rate limiting was added. |
| T-42-02-10 | accept | As accepted (D-01). No pending-state machine, reconciler or healer was built. |
| T-42-02-11 | accept | As accepted (Open Question 3). The in-lock revalidation is `resolve_existing`, a plain SELECT; `lock_identity_and_user` is not called on this path, which mutation 2 confirms is detectable. |
| T-42-SC | mitigate | Held. No package was installed, added, moved or upgraded. |

## Not Done Here, By Design

The plan's own scope note holds: what the later plans add is proof, not behaviour. Absent from this
plan and owned elsewhere — the precedence and consumption matrix (42-03), the registered
single-writer and ordering AST walks (42-04), and the two-connection races for both destinations
(42-05). The three Apple failure arms (`ProofRejected`, `Unavailable`, and the write-side failures)
have no e2e case on this route yet; they run through the same `read_bits_with_retry` /
`write_bits_with_retry` seam the anonymous route already covers, and 42-03's matrix names them.

## Known Stubs

None. No stub, TODO, FIXME or placeholder was introduced, and no test was skipped or marked xfail.
The changed files were scanned before this summary was written; the one grep hit for "not available"
is pre-existing prose in a `test_grant_locks.py` docstring about `SET LOCAL lock_timeout`.

## Threat Flags

One new endpoint was added, and it is `POST /auth/claim-registered-grant` — the subject of this
plan's own threat register above, not new surface outside it. No other network endpoint, auth path,
file access pattern or trust-boundary schema change was introduced.

## For the Next Plan

- `complete_claim_registered_grant(identity=, challenge_id=, device_token=)` is the seam 42-05's race
  harness drives; the challenge operation literal is `claim_registered_grant`.
- `activate_registered_account_grant` takes keyword-only `user_id`, `identity_row`, `tier_id`,
  `evaluated_at` and returns `bool`.
- A conversion fixture must seed `starts_at` strictly before the claim's instant, or the strict
  `ends_at > starts_at` CHECK rolls the transaction back and the case passes as a race loss.
- `CLAIM_ARMS` is four members; `EVENT_NAMES` gained `claimant_not_registered`; `ErrorCode` is
  unchanged at 18.
- Test counts after this plan: unit 957, schema 126, e2e 231.

## Self-Check: PASSED

- `tests/e2e/test_claim_registered_grant.py` exists on disk; all eight modified files exist.
- `645da2d` and `8bf2996` are both present in git history.
