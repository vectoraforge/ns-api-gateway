---
phase: 41-post-auth-claim-anonymous-grant
plan: 04
subsystem: testing
tags: [postgres, concurrency, sqlalchemy, asyncpg, locks, unique-index, grants]

requires:
  - phase: 41-post-auth-claim-anonymous-grant
    provides: "41-01's DeviceCheck seam, the generalised _complete sequence, the single crud activation writer and the fixed lock order"
  - phase: 40-post-auth-upgrade-anonymous
    provides: "tests/schema/test_create_race.py — the harness, the hooked session, the barrier and the FK-ordered teardown"
provides:
  - "tests/schema/test_claim_race.py — the live two-connection race: one grant, one anti-abuse row, one usage row, the marker once, both challenges consumed, the loser answered 200"
  - "The proof that the loser's IntegrityError arrives at the flush and never at the commit, so the deferred anti-abuse FKs stay off the caller's path"
  - "tests/schema/test_grant_locks.py's activation cases — the writer's locking SQL captured against a real database and asserted as exactly two tiers in the fixed order"
  - "The application's FREE_GRANT_SOURCES asserted equal to the live lifetime index predicate's membership"
  - "A production fix: the race loser no longer answers 500 — the rollback's expired instances are reloaded before the router reads them"
affects: [41-05, "phase 42 registered account grant"]

actuals:
  tokens: 11850
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A concurrency case records its premise at a barrier, so it cannot silently degrade into two sequential runs"
    - "Lock order is asserted from the SQL the production writer actually emits, captured at the engine, not from a literal that mirrors it"
    - "A structural claim about a named constant is tied to the live catalogue object that enforces it, so narrowing the constant goes red"

key-files:
  created:
    - tests/schema/test_claim_race.py
  modified:
    - tests/schema/test_grant_locks.py
    - src/nativespeaker/api/services/auth.py

key-decisions:
  - "The two challenges are seeded issued rather than pre-claimed, because this race drives the whole production completion and that completion performs its own claim"
  - "The barrier is held before the first flush rather than after the first read: the re-resolution has happened by then, which is exactly the pre-state the premise needs"
  - "Winner and loser are bucketed by where the IntegrityError arrived, because both answer 200 and nothing else separates them"
  - "The lock-order proof captures the writer's real SQL at the engine rather than asserting a mirrored literal, so a third tier cannot hide behind a helper"

patterns-established:
  - "Barrier-before-flush: the hook fires inside the wrapped session's first flush, which is the only point where both attempts are past re-resolution and neither has written"
  - "Flush-versus-commit attribution: the wrapper records an IntegrityError raised by its own flush separately from one raised by the inner session's commit"

requirements-completed: [ANONGRANT-02, ANONGRANT-03]

coverage:
  - id: D1
    description: "Two simultaneous first claims for one anonymous account, driven through the production completion on two independent connections against real PostgreSQL, leave exactly one grant row, one anti-abuse row, one usage row and one free_grant_consumed_at value"
    requirement: "ANONGRANT-03"
    verification:
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_exactly_one_grant_row_exists_on_the_anonymous_tier"
        status: pass
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_exactly_one_anti_abuse_row_carries_the_ios_provider"
        status: pass
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_exactly_one_usage_row_exists_at_zero_used"
        status: pass
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_the_lifetime_marker_is_set_once"
        status: pass
    human_judgment: false
  - id: D2
    description: "The premise is recorded rather than assumed: both attempts observed an account with no grant row before either wrote, so the case cannot degrade into two sequential claims"
    requirement: "ANONGRANT-03"
    verification:
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_both_attempts_observed_an_account_with_no_grant"
        status: pass
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_exactly_one_attempt_lost_the_race"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both challenges are consumed, so a retry needs a fresh prepare rather than a replay of either handle (D-06)"
    requirement: "ANONGRANT-03"
    verification:
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_both_challenges_were_consumed_and_their_verifiers_cleared"
        status: pass
    human_judgment: false
  - id: D4
    description: "The loser answers 200 carrying the winner's entitlement, field for field, by the same path a repeat takes, rather than a rejection (D-13)"
    requirement: "ANONGRANT-03"
    verification:
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_the_loser_answers_two_hundred_with_the_winners_entitlement"
        status: pass
    human_judgment: false
  - id: D5
    description: "The loser's IntegrityError arrives at the flush and not at the commit: the two unique indexes are ordinary and per-statement, and correct code never reaches the deferred anti-abuse foreign keys"
    requirement: "ANONGRANT-03"
    verification:
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_the_losers_violation_arrived_at_the_flush_and_not_at_the_commit"
        status: pass
    human_judgment: false
  - id: D6
    description: "The claim path introduces no third lock tier: the SQL the activation issues locks grant rows ascending by id and then their usage rows, and nothing else"
    requirement: "ANONGRANT-02"
    verification:
      - kind: integration
        ref: "tests/schema/test_grant_locks.py#TestTheActivationAddsNoThirdLockTier::test_the_writer_locks_the_grant_rows_then_their_usage_rows"
        status: pass
      - kind: integration
        ref: "tests/schema/test_grant_locks.py#TestTheActivationAddsNoThirdLockTier::test_exactly_two_distinct_lock_tiers_are_taken_on_the_claim_path"
        status: pass
      - kind: integration
        ref: "tests/schema/test_grant_locks.py#TestTheActivationAddsNoThirdLockTier::test_the_identity_row_is_revalidated_by_a_plain_re_read"
        status: pass
    human_judgment: false
  - id: D7
    description: "The named free-grant source set in the application equals the membership carried by the live lifetime index predicate, so narrowing the constant back to one member goes red against the database"
    requirement: "ANONGRANT-02"
    verification:
      - kind: integration
        ref: "tests/schema/test_grant_locks.py#TestTheFreeGrantSourceSetMatchesTheIndex::test_the_named_set_equals_the_live_index_predicate"
        status: pass
      - kind: other
        ref: "Mutation check: FREE_GRANT_SOURCES narrowed to one member failed that case; reverted, file byte-identical to HEAD"
        status: pass
    human_judgment: false
  - id: D8
    description: "A production defect the race found: the loser's rollback expired the two rows the router still reads, so a genuine race answered 500 instead of 200. Both instances are now reloaded before the service returns"
    requirement: "ANONGRANT-03"
    verification:
      - kind: integration
        ref: "tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_the_loser_answers_two_hundred_with_the_winners_entitlement"
        status: pass
    human_judgment: true
    rationale: "The schema race proves the fix on a real session, and the whole suite is green, but no e2e case drives two concurrent HTTP requests at the router. The 500 was reachable through the router and only the service layer is asserted against it here."

duration: 20min
completed: 2026-09-03
status: complete
---

# Phase 41 Plan 04: The claim's live concurrency proof Summary

**Two simultaneous first claims for one anonymous account, driven through `complete_claim_anonymous_grant` on two real connections against real PostgreSQL, are proven to allocate exactly once with the loser answered 200 — and the race found a live defect that made that loser a 500.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-09-03T05:54:00Z
- **Completed:** 2026-09-03T06:14:26Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- The one claim in this phase that no unit test and no e2e case could make is now an executed case: with no grant row to lock, the `FOR UPDATE` locks nothing and the two unique indexes arbitrate, and the barrier records that both attempts saw an account with no grant before either wrote.
- **A real bug, found exactly where the plan predicted a 500 could hide.** The loser's `session.rollback()` expires every instance in its session, and the router then reads `identity.user.id` and `identity.identity.provider` off those expired rows — a lazy load with no greenlet, i.e. `MissingGreenlet` and a 500, on the one path D-13 requires to answer 200. Three lines in `services/auth.py` reload both instances where an `await` still can.
- The loser's integrity violation is asserted to arrive at the **flush**, not the commit — which is what keeps the deferred anti-abuse foreign keys off the caller's path and pins that all three rows go in one flush.
- The lock-order proof now covers the path this phase added, and covers it by capturing the SQL the production writer actually emits at the engine rather than by comparing a mirrored literal: two tiers, in the fixed order, and neither `core.external_identities` nor `core.users` among them.
- `FREE_GRANT_SOURCES` is tied to the live index predicate that enforces it, and the tie is proven to fire: narrowing the constant to one member was applied, observed to fail the case, and reverted.

## Task Commits

1. **Task 1: Two attempts, one grant (D-12)** — `72a9b80` (test)
2. **Task 2: No third lock tier, and the source set matches the index** — `278a8aa` (test)

## Files Created/Modified

- `tests/schema/test_claim_race.py` — the harness (`_Harness`, `clean_up`, `commit_anonymous_account`, `commit_issued_challenge`), `_NeverSetDevice`, `_RacingSession`, `_Attempt`, `role_of`, `status_of`, `run_attempt`, `barrier_for`, and the nine cases
- `tests/schema/test_grant_locks.py` — `activation_statements`, `locking`, `relation_of`, `TestTheActivationAddsNoThirdLockTier` (3 cases) and `TestTheFreeGrantSourceSetMatchesTheIndex` (1 case); the module docstring now names all three subjects
- `src/nativespeaker/api/services/auth.py` — the loser arm reloads `identity.user` and `identity.identity` after its rollback

## Decisions Made

- **The challenges are seeded issued, not pre-claimed.** The analog pre-claims because it drives `create_user` directly — the post-claim half only — and consumes the handle itself. This case drives the whole of `complete_claim_anonymous_grant`, which performs its own claim, so a pre-claimed row is rejected as `ChallengeConsumed` before the race ever starts. Recorded below as a plan-literal deviation.
- **The barrier is held before the first flush.** The plan asks for "after each has re-resolved and before either flushes", and in `activate_anonymous_device_grant` the re-resolution is the statement immediately before the flush, so the wrapped session's first `flush()` is the exact point. It is also the only wrapper method the crud calls between the two.
- **Winner and loser are bucketed by where the `IntegrityError` landed.** Both attempts answer 200 with byte-identical entitlements, which is the property under test, so the outcome cannot be the bucket key the way it is in `test_create_race.py`. `role_of` reads the flush flag, and one case asserts the two roles are exactly `{won, lost_at_flush}` — which is itself the "never two winners" assertion.
- **The lock tiers are read off the emitted SQL.** A literal mirroring the crud, as the existing cases use, cannot see a third tier that a future writer adds; a `before_cursor_execute` capture of the real writer can. The mirrored literals stay for the contention cases, which need executable SQL of their own.
- **The activation capture uses `datetime.now(UTC)`, not the module's fixed instant.** The seeded held grant's `starts_at` is `CURRENT_TIMESTAMP`; an earlier evaluated instant makes it ineffective, the writer takes one tier instead of two and then falls through to a rejected insert. That is precisely what the first run did — see Issues Encountered.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The race loser answered 500, not the 200 D-13 requires**

- **Found during:** Task 1, on the first run of the race
- **Issue:** `_claim_anonymous_grant`'s loser arm calls `await self.session.rollback()`. A SQLAlchemy rollback expires every instance in the session, including the `User` and `ExternalIdentity` rows `get_identity` loaded and handed to the router. The router then evaluates `sync_service.read_entitlement(identity.user.id)` and `identity.identity.provider`, each of which triggers a lazy refresh on an expired instance from plain attribute access — `sqlalchemy.exc.MissingGreenlet`, and a 500 on exactly the path this plan exists to prove answers 200. Nothing caught it before: `test_claim_precedence.py`'s loser case uses a stub session that neither expires nor lazy-loads, and no e2e case can produce a real index conflict.
- **Fix:** `await self.session.refresh(identity.user)` and `await self.session.refresh(identity.identity)` immediately after the rollback, where an `await` is still available. Three lines, no branch, no new state.
- **Files modified:** `src/nativespeaker/api/services/auth.py`
- **Verification:** `test_the_loser_answers_two_hundred_with_the_winners_entitlement` fails without it (`MissingGreenlet` out of `identity.user.id`) and passes with it; 950 unit, 226 e2e and 134 schema all green afterwards
- **Committed in:** `72a9b80` (Task 1 commit)

### Plan-literal deviations

**2. The challenges are seeded issued rather than "each already claimed"**

- **Found during:** Task 1
- **Issue:** The plan's action text says both to seed the challenges "each already claimed" (following the analog's helper) and to drive both attempts "through the production completion — `AuthService.complete_claim_anonymous_grant` — never through a re-implementation of the write". Those are incompatible: `_complete`'s conditional claim requires `claimed_at IS NULL` and answers a pre-claimed row with `ChallengeConsumed` before any post-claim work runs. The analog can pre-claim only because it bypasses `_complete` and calls `create_user` directly.
- **Fix:** `commit_issued_challenge` writes the row without `claimed_at`, and the production completion claims, commits, works and consumes exactly as the route does. This resolves in favour of the plan's stated intent — the strictly stronger reading, since the claim and the consumption are now inside what the case drives rather than around it.
- **Files modified:** `tests/schema/test_claim_race.py`
- **Committed in:** `72a9b80`

**3. The lock-tier count is asserted over captured SQL, not over a mirrored literal**

- **Found during:** Task 2
- **Issue:** The plan asks for "literals that mirror the crud, so a divergence between the two is visible in a diff rather than hidden behind a helper", and separately for a case asserting the tier count is exactly 2. A mirrored literal can assert what the two known tiers look like, but it cannot detect a *third* tier the writer adds — the thing T-41-24 is about.
- **Fix:** The existing mirrored literals are untouched and still serve the contention cases, which need executable SQL. The new cases capture the writer's own statements at `before_cursor_execute` and assert the ordered relations, the distinct count, and the absence of `core.external_identities` and `core.users`. A future third tier fails a named case.
- **Files modified:** `tests/schema/test_grant_locks.py`
- **Committed in:** `278a8aa`

---

**Total deviations:** 3 (1 auto-fixed bug, 2 plan-literal readings resolved in favour of the plan's stated intent)
**Impact on plan:** No scope was added. Deviations 2 and 3 both make the case stronger than the literal reading would have. Deviation 1 is a genuine production defect that this plan's own subject matter exposed on its first run, which is the outcome a concurrency proof is written to produce.

## Verification

Re-run whole after the final task commit:

| Check | Result |
|---|---|
| `uv run pytest -m schema tests/schema/test_claim_race.py -q` | 9 passed, 0 skipped (twice in a row, cold database each time) |
| `uv run pytest -m schema tests/schema/test_grant_locks.py -q` | 8 passed (baseline 4) |
| `uv run pytest -m schema -q` | 134 passed (baseline 121) |
| `uv run pytest -q` | 950 passed |
| `uv run pytest -m e2e -q` | 226 passed |
| `uv run ruff check src tests` | exit 0 |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed |

**Mutation check (Task 2 acceptance criterion).** `FREE_GRANT_SOURCES` was narrowed to
`frozenset({AccessGrantSource.anonymous_device_grant})`.
`test_the_named_set_equals_the_live_index_predicate` failed, reporting
`registered_account_grant` as an extra member carried by the live predicate. The edit was reverted and
`git diff` reports `src/nativespeaker/api/tables/grants.py` byte-identical to HEAD. The assertion is
therefore known to fire against the real tree, not only in principle.

**The premise is non-vacuous.** `test_both_attempts_observed_an_account_with_no_grant` reads the grant
count for the user on an independent connection at the barrier, inside the first flush of each attempt
and before either has written, and asserts `[0, 0]`. `test_exactly_one_attempt_lost_the_race` then
asserts the two roles are exactly one winner and one loser-at-the-flush, so neither "both won" nor
"they ran sequentially" can pass.

## Issues Encountered

**The activation capture measured one tier, and the control did not catch it.** Task 2's first run
asserted `activated is False` as its control, which held — but for the wrong reason. The module's fixed
`NOW` (2026-08-23) precedes the seeded grant's `starts_at` (`CURRENT_TIMESTAMP`), so the held grant was
not effective, the writer took only the grant-rows tier, fell through every check and was rejected by
`ix_access_grants_one_active_per_user` at the flush. `False` came from the `IntegrityError` arm, not the
held-grant arm. Resolved by evaluating at `datetime.now(UTC)` and by replacing the control with one that
cannot be satisfied that way: the writer must issue **no `INSERT` at all**. Recorded here rather than
quietly fixed, because it is the exact failure mode — a count that reads correct for the wrong reason —
that these cases exist to prevent elsewhere.

## Known Stubs

None. No hardcoded empty value, placeholder, skipped test or `xfail` was introduced.

## User Setup Required

None. This plan adds no dependency and no external service; the schema suite's only precondition is the
live PostgreSQL 17 the suite creates and drops its own database against, which 41-01 already recorded.

## Next Phase Readiness

- **41-05** inherits a phase whose every claim is now executed rather than argued, including the one
  behaviour (the loser's 200) that was documented as intended and was in fact broken until this plan ran.
- **Phase 42** inherits two checks it will trip on purpose: `test_the_named_set_equals_the_live_index_predicate`
  if it narrows `FREE_GRANT_SOURCES`, and `TestTheActivationAddsNoThirdLockTier` if its registered-account
  writer locks an identity or user row ahead of the grant rows. Both fail by name.

**Concerns:** the fix in deviation 1 is proven at the service layer by a real two-connection race, but no
case drives two concurrent HTTP requests through the router. The same expiry-after-rollback hazard exists
anywhere a service rolls back and its caller then reads an instance loaded before the rollback; only this
one path is asserted. Recorded as coverage D8 with `human_judgment: true` rather than closed.

---
*Phase: 41-post-auth-claim-anonymous-grant*
*Completed: 2026-09-03*

## Self-Check: PASSED

`tests/schema/test_claim_race.py` exists on disk; both task commits resolve in `git log` (`72a9b80`,
`278a8aa`). Every acceptance criterion of both tasks was executed, and the plan-level verification block
above was re-run whole after the final task commit.
