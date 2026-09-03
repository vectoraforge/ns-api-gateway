---
phase: 42-post-auth-claim-registered-grant
plan: 05
subsystem: tests
tags: [concurrency, race, schema, postgres, d-10, d-11, d-12, d-13]
status: complete

requires:
  - "42-02 (complete_claim_registered_grant and activate_registered_account_grant, the entry point and the writer both races drive)"
  - "tests/schema/test_claim_race.py (the Phase 41 two-connection harness)"
  - "migrations/20260818_01_initial-release.sql (the two partial unique indexes and the external_identities provider CHECK)"
provides:
  - "TestTwoSimultaneousRegisteredClaimsAllocateOnce — the new-grant destination raced at a barrier"
  - "TestTwoSimultaneousConversionsSupersedeOnce — the conversion destination raced at a barrier"
  - "commit_registered_account and commit_active_anonymous_grant — the two seeding helpers"
  - "_RacingSession.before_first_commit — a barrier seam ahead of the grant row lock"
  - "_Attempt.flushes — the observable that separates a conversion's winner from its loser"
affects:
  - "plan 42-06 (the ledger close reads this summary's assumption findings)"

tech-stack:
  added: []
  patterns:
    - "A barrier placed ahead of the lock the code under test takes, not merely ahead of its first write"
    - "Race roles read off measured observables rather than assumed from the attempt order"

key-files:
  created: []
  modified:
    - tests/schema/test_claim_race.py

decisions:
  - "The conversion race holds at the challenge commit, not the first flush: a conversion takes the grant row lock before it flushes, so a flush barrier deadlocks by construction"
  - "The conversion loser is separated by whether it wrote, not by where a violation arrived — it raises no IntegrityError at all"
  - "The challenge operation and the completion driven are parameters of the shared helpers rather than a forked harness, so the Phase 41 anonymous race keeps running unchanged"

metrics:
  duration: "~40 min"
  completed: 2026-09-03
  tasks: 2
  commits: 2

actuals:
  tokens: 8043
  tasks: 2
  commits: 2
---

# Phase 42 Plan 05: The Registered Claim Under Contention Summary

Both destinations of `POST /auth/claim-registered-grant` are raced at a barrier on two real
connections against PostgreSQL 17: two first claims allocate exactly one grant, and two conversions
supersede exactly once with the counters carried across intact.

## What Was Built

One file grew by 286 lines. `tests/schema/test_claim_race.py` now carries two race classes beside
Phase 41's. `TestTwoSimultaneousRegisteredClaimsAllocateOnce` is the Phase 41 harness with three
mechanical changes — a `google` identity carrying a non-empty `provider_uid`, a
`claim_registered_grant` challenge, and `complete_claim_registered_grant` as the completion each
attempt drives. `TestTwoSimultaneousConversionsSupersedeOnce` seeds an active anonymous grant
starting thirty days before the fixed instant and races two conversions on it.

The harness itself gained three additive things and lost nothing: an `operation` parameter threaded
through `commit_issued_challenge` and `prepare_attempt`, a `before_first_commit` barrier seam on
`_RacingSession`, and a `flushes` count on `_Attempt`. Phase 41's anonymous race runs unchanged.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | The new-grant race — two attempts, one grant | `d715713` | `tests/schema/test_claim_race.py` |
| 2 | The conversion race — one supersession, one allowance | `6fda366` | `tests/schema/test_claim_race.py` |

## Verification

| Gate | Before | After |
|------|--------|-------|
| `pytest -m schema tests/schema/test_claim_race.py -q` | 9 passed | 30 passed, zero skipped |
| `pytest -m schema -q` | 135 passed (126 before Task 1) | 147 passed |
| `pytest -q` | 989 passed | 1001 passed |
| `ruff check src tests` | clean | clean |
| `grep -c complete_claim_registered_grant tests/schema/test_claim_race.py` | 0 | 1 |
| `provider_uid` occurrences in the module | 1 | 5 |

Commands were run as `.venv/bin/python -m pytest` and `.venv/bin/ruff`, the same interpreter
`uv run` resolves to, as plan 42-02 also recorded.

The new-grant class was run twice in a row: 9 passed both times, with `second` the winning attempt on
both runs. The conversion class was run twice in a row: 30 passed both times for the whole module,
and across the run and the probes the winner alternated between `first` and `second`. No case reads
the winner from the attempt order; every role is read off a measured observable, which is why the
alternation changes nothing.

## The Barrier Had to Move, and the Measurement That Forced It

The plan directed that the conversion race reuse the Phase 41 barrier unchanged — `before_first_flush`
on `_RacingSession`. **That barrier deadlocks on the conversion path, by construction.** It was tried
first and measured, not reasoned around:

```
tests/schema/test_claim_race.py:171: in flush
    await hook()
tests/schema/test_claim_race.py:270: in hold
    await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)
E   TimeoutError
========================= 1 warning, 1 error in 21.22s =========================
```

The cause is the ordering inside the writer. On a first claim there is no grant row, so
`lock_effective_grants` locks nothing and both attempts reach their first flush freely — which is
exactly why Phase 41's barrier works. On a conversion there **is** a row: the first attempt takes
`FOR UPDATE` on it, walks on to the expiry flush, and holds there waiting for its partner; the
partner is blocked inside PostgreSQL on that same row lock and can never reach a flush of its own.
The holder waits twenty seconds and raises.

The fix is to hold at a point ahead of the lock. `_complete` commits the challenge claim before any
post-claim work runs, so `_RacingSession` gained an optional `before_first_commit` hook, shaped
exactly like the flush hook. Both attempts now claim their challenges, hold together, release
together, and enter the writer at the same moment — where PostgreSQL's row lock serialises them,
which is the real question a conversion race asks.

This is an additive change. `before_first_flush` is untouched, and Phase 41's anonymous race and this
plan's new-grant race both still hold at the flush.

## The Conversion Loser Raises No Violation — Measured, Not Predicted

The plan predicted the conversion loser would surface an `IntegrityError` at its flush, as the
new-grant loser does. **It does not, and it never can.** Traced observation:

```
TRACE [('lock_effective_grants', "[AccessGrant(source=anonymous_device_grant, status=active, ...)]"),
       ('lock_effective_grants', '[]'),
       ('has_prior_free_grant', 'True')]
PROBE winner: flushes=2  integrity_at_flush=False
PROBE loser:  flushes=0  integrity_at_flush=False
```

The loser blocks on `FOR UPDATE`. When the winner commits and the lock releases, PostgreSQL re-checks
the locked row against the statement's predicate under READ COMMITTED: the row is now `expired`, so
it no longer qualifies and is dropped. The winner's new registered row is invisible to that statement,
whose snapshot was taken before the winner committed. So the loser's lock read returns `[]`,
`superseded` is `None`, and `has_prior_free_grant` — which has no status predicate, deliberately —
returns `True` against the expired anonymous row. The writer returns false there, having emitted no
write at all.

That is the correct behaviour and it satisfies D-13: the loser rolls back, re-reads and answers 200.
But the mechanism is the in-lock re-decision, not the unique index, so the case asserts what is true:
`test_the_loser_emitted_no_write_and_raised_no_violation` asserts the loser's flush count is zero and
neither violation flag is set, and the winner's flush count is two. The predicted assertion would have
asserted a false thing about the production code.

The unique-index arbitration the plan describes is real and is proven — on the **new-grant**
destination, where there is no row to lock. That is
`TestTwoSimultaneousRegisteredClaimsAllocateOnce::test_the_losers_violation_arrived_at_the_flush_and_not_at_the_commit`,
which passes as written.

## Mutation Testing — Two Mutations, Both Reverted

Both mutations were applied to `src/nativespeaker/api/crud/grants.py` alone and reverted with
`git checkout -- <path>`. Its SHA-256 is `f5959dda1880989e25a15ecdb3332c67bbdfca903582839c84cc414d9298a8ce`
both before the cycle and after the last revert, and `git diff --stat` on that path is empty.

**Mutation A — the plan's proposed one: remove the flush boundary between the expiry and the insert.**
Result: **1 failed, 29 passed.**

| Node id | Observed failure |
|---------|------------------|
| `TestTwoSimultaneousConversionsSupersedeOnce::test_the_loser_emitted_no_write_and_raised_no_violation` | `AssertionError: assert 1 == 2` on `winner.flushes == 2` |

The class detects the mutation, but structurally — the boundary is gone, so the winner flushes once
rather than twice — and not through a broken outcome. Every data assertion stayed green: one active
registered row, one expired anonymous row at the instant, two rows in total, the counters carried.
This is the contention-level confirmation of plan 42-02's A1 finding: SQLAlchemy 2.0.46 emits the
`UPDATE` before the `INSERT` on its own, so removing the explicit boundary changes nothing the
database sees. Two mechanisms were producing one order; removing one of them left the other.

**Mutation B — the violation the class exists to catch: delete the block that expires the anonymous
row, so the conversion inserts without superseding.**
Result: **6 failed, 24 passed.**

| Node id | Observed failure |
|---------|------------------|
| `...::test_exactly_one_attempt_wrote` | `AssertionError: assert {'won'} == {'lost_before_writing', 'won'}` — both attempts flushed and both were refused |
| `...::test_exactly_one_active_grant_row_exists_on_the_registered_tier` | `assert [('anonymous_device_grant', 'anonymous')] == [('registered_account_grant', 'registered')]` |
| `...::test_exactly_one_row_expired_and_its_source_was_never_rewritten` | `assert [] == [(UUID(...), 'anonymous_device_grant', datetime(2026, 8, 23, 12, 0, tzinfo=utc))]` |
| `...::test_the_user_holds_exactly_two_grant_rows` | `assert 1 == 2` |
| `...::test_the_loser_answers_two_hundred_with_the_winners_entitlement` | the roles collapsed to one bucket |
| `...::test_the_loser_emitted_no_write_and_raised_no_violation` | the roles collapsed to one bucket |

This is Pitfall 1 exactly: `ix_access_grants_one_active_per_user` refused both inserts, both callers
were reported as race losses, and both answered 200 carrying the stale anonymous entitlement.
Together with plan 42-02's statement-order proof, research assumption A1 is now closed at both the
statement level and the contention level.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The conversion barrier had to move ahead of the grant row lock**
- **Found during:** Task 2
- **Issue:** The plan directed reuse of `before_first_flush` unchanged. Measured: it deadlocks on the
  conversion path — the holder owns the `FOR UPDATE` row lock its partner is blocked on, so the
  partner can never reach a flush. `TimeoutError` after twenty seconds, reproduced above.
- **Fix:** `_RacingSession` gained an optional `before_first_commit` hook, shaped exactly like the
  flush hook. `run_attempt` gained the matching parameter. Both existing flush-barrier races are
  untouched and still pass.
- **Files modified:** `tests/schema/test_claim_race.py`
- **Commit:** `6fda366`

**2. [Rule 1 - Bug] The predicted loser-separation observable does not exist on the conversion path**
- **Found during:** Task 2
- **Issue:** The plan's case list specified "the loser's `IntegrityError` surfaced at the flush and
  not at the commit" for the conversion race. Traced measurement shows the loser raises no
  `IntegrityError` at all — it is refused by the writer's in-lock `has_prior_free_grant` guard having
  emitted zero writes. `role_of`, which keys on `integrity_at_flush`, collapses both attempts into
  one bucket and makes the whole class vacuous.
- **Fix:** Added `_Attempt.flushes` and a sibling `role_by_writes`. The case asserts the measured
  truth: the loser's flush count is zero and neither violation flag is set; the winner's is two. The
  finding is reported in full above rather than the assertion being softened.
- **Files modified:** `tests/schema/test_claim_race.py`
- **Commit:** `6fda366`

**3. [Rule 3 - Blocking] The seeding helpers are parameterised rather than forked**
- **Found during:** Task 1
- **Issue:** The plan said to change the operation literal in `commit_issued_challenge` to
  `claim_registered_grant` and swap the completion call in `run_attempt`. Done literally, both edits
  break Phase 41's `TestTwoSimultaneousFirstClaimsAllocateOnce`, which shares those helpers.
- **Fix:** `operation` became a parameter of `commit_issued_challenge` and `prepare_attempt` and a
  field on `_Attempt`, and `run_attempt` selects the completion from it. The anonymous default keeps
  the Phase 41 class identical. Only the account-seeding helper was genuinely forked, as the plan
  intended, because a `google` row's `provider_uid` CHECK is incompatible with the anonymous one.
- **Files modified:** `tests/schema/test_claim_race.py`
- **Commit:** `d715713`

### Auth Gates

None.

## Assumption Findings for the Ledger Close

Plan 42-06 should record two:

- **A1 is closed at both levels and is FALSE.** Plan 42-02 measured the emitted statement order with
  the boundary removed; this plan measured the observable outcome under contention with the boundary
  removed. Neither changed. The boundary is kept as the guard against an ORM upgrade inverting the
  default, and Mutation B shows the class still catches the failure the boundary exists to prevent.
- **The unique indexes are not the arbiter on every destination.** They arbitrate the new-grant race,
  where there is no row to lock. The conversion is arbitrated by the row lock plus the writer's
  in-lock re-decision, and the loser never reaches a constraint. Both outcomes satisfy D-13; the
  phase's prose should not claim one mechanism for both.

## Known Stubs

None. Both classes drive the production completion end to end; nothing is mocked but the Apple
device-check seam, which is the harness's pre-existing scripted double.

## Threat Flags

None. This plan adds tests only and introduces no endpoint, auth path, file access or schema change.

## Self-Check: PASSED

- `tests/schema/test_claim_race.py` — FOUND
- `.planning/phases/42-post-auth-claim-registered-grant/42-05-SUMMARY.md` — FOUND
- commit `d715713` — FOUND
- commit `6fda366` — FOUND
