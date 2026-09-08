---
phase: 45-post-auth-restore-subscription
plan: 08
subsystem: database
tags: [postgres, sqlmodel, access-grants, restore, subscriptions, schema-tests]

requires:
  - phase: 45-post-auth-restore-subscription
    provides: "45-05's move branch — `lock_grants_of([current_owner, destination])` and the shared `write_subscription_grant`"
  - phase: 45-post-auth-restore-subscription
    provides: "45-04's `tests/schema/test_restore_race.py` harness: `_Harness`, `run_attempt`, `grants_of`, `owner_of`"
provides:
  - "The narrowed superseded set: a move ends the destination's whole set plus the old owner's row for the moved subscription, and nothing else"
  - "`TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves` — the source-side case VERIFICATION truth 6 names, on real PostgreSQL"
  - "`TestTheDestinationStillLosesEverythingItHeld` — the destination-side counterpart that stops a later over-narrowing"
  - "`commit_subscription` and `proof_for` take an optional `external_id`, so one harness can name two subscriptions"
affects: [restore, webhook ingestion, access-grant writes, phase 45 verification]

actuals:
  tokens: 2848
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A write decides for itself which of the rows its caller locked it is entitled to change"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/subscriptions.py
    - tests/schema/test_restore_race.py

key-decisions:
  - "The entitled arm of `superseded` keeps a grant when `grant.user_id == user_id or grant.subscription_id == subscription_id`: the two clauses are the two things this write is entitled to end"
  - "The fixture gives the source a grant for the moved subscription before the unrelated one, reproducing CR-03's three steps exactly, rather than the plan's five-step list which never wrote that row"
  - "No free-grant case on real PostgreSQL: `tests/e2e/test_restore_subscription.py` already covers a free grant superseded on the restore path"

patterns-established:
  - "Both directions of a narrowing are pinned: one case fails if the set keeps too much, another fails if it keeps too little"

requirements-completed: [RESTORE-01]

coverage:
  - id: D1
    description: "A cross-account move expires the source account's grant for the subscription being moved and leaves the source account's grants for other subscriptions active"
    requirement: RESTORE-01
    verification:
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves::test_the_source_keeps_its_active_grant_for_the_unrelated_subscription"
        status: pass
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves::test_the_moving_subscription_is_owned_by_the_destination_and_the_month_is_spent"
        status: pass
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves::test_the_source_holds_no_active_grant_for_the_moved_subscription"
        status: pass
    human_judgment: false
  - id: D2
    description: "The destination still ends every grant it held before the move, so `ix_access_grants_one_active_per_user` is satisfied by exactly one active grant per account"
    requirement: RESTORE-01
    verification:
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTheDestinationStillLosesEverythingItHeld::test_the_destinations_grant_for_another_subscription_is_ended_by_the_move"
        status: pass
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTheDestinationStillLosesEverythingItHeld::test_the_destination_ends_with_exactly_one_active_grant"
        status: pass
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTheDestinationStillLosesEverythingItHeld::test_the_unique_index_never_fired"
        status: pass
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves::test_the_destination_holds_exactly_one_active_grant_and_it_is_for_the_moved_subscription"
        status: pass
    human_judgment: false
  - id: D3
    description: "The narrowing changes no lock, no statement order and no SQLSTATE handling"
    verification:
      - kind: other
        ref: "grep -c 'with_for_update' src/nativespeaker/api/crud/subscriptions.py == 0 (unchanged); grep -c '23505' == 5 (unchanged)"
        status: pass
      - kind: other
        ref: "git diff faef7aa..8e01306 -- src/nativespeaker/api/crud/subscriptions.py: 5 insertions, 2 deletions, all inside the `superseded` assignment and its comment"
        status: pass
    human_judgment: false
  - id: D4
    description: "The same-account branch, the adoption branch and the webhook ingestion path are unchanged"
    requirement: RESTORE-01
    verification:
      - kind: integration
        ref: "uv run pytest -m schema -q — 229 passed"
        status: pass
      - kind: e2e
        ref: "uv run pytest -m e2e -q — 325 passed"
        status: pass
      - kind: unit
        ref: "uv run pytest -q — 1250 passed"
        status: pass
    human_judgment: false
  - id: D5
    description: "A restore removes no entitlement the presented proof says nothing about (the prohibition, as a property rather than as a case)"
    requirement: RESTORE-01
    verification: []
    human_judgment: true
    rationale: "The two schema cases prove the property for the one shape CR-03 describes: one source, one destination, one unrelated subscription each. The general statement — that no reachable state lets a caller end a third party's grant — is a judgment about the whole write, not something these two fixtures assert."
  - id: D6
    description: "A write that takes something away from a third party is not silent"
    verification: []
    human_judgment: true
    rationale: "Still true and still unfixed: a move writes no audit row (45-REVIEW WR-04, threat T-45-08-03, accepted). This plan removes the wrong taking; it does not add the signal. A human must weigh whether the accepted residual is acceptable at ship time."

duration: 8 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 08: A move takes only the grant for the subscription it moves Summary

**The entitled arm of `write_subscription_grant`'s superseded set is narrowed to the destination's own rows plus the old owner's row for the moved subscription, proved on real PostgreSQL by a case that returned `expired` before the fix.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-08T20:55:10Z
- **Completed:** 2026-09-08T21:03:14Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **VERIFICATION gap 2 (truth 6, 45-REVIEW CR-03) is closed.** `superseded` was
  `list(marked_active) if entitled else held`, and on a move `marked_active` holds both accounts'
  rows because `services/restore.py` locks `[current_owner, destination]` together. A source
  account that owned a second, unrelated subscription lost its grant for that subscription too.
  The entitled arm is now a comprehension keeping a grant when
  `grant.user_id == user_id or grant.subscription_id == subscription_id`.
- **The defect was observed before it was fixed, not reasoned about.**
  `test_the_source_keeps_its_active_grant_for_the_unrelated_subscription` was written first and run
  against the unchanged source: it returned `AssertionError: assert 'expired' == 'active'` — the
  unrelated grant, expired by a move that named a different subscription. That is CR-03's exact
  claim, measured.
- **Both directions of the narrowing are pinned.** The source-side class fails if the set keeps too
  much; `TestTheDestinationStillLosesEverythingItHeld` fails if it keeps too little. The second was
  confirmed red twice — once with `and` in place of `or`, once with the `subscription_id` clause
  alone — and the source reverted after each.
- **The narrowing is the membership test and only the membership test.** No lock was added or
  removed (`with_for_update` count 0, unchanged), no SQLSTATE handling changed (`23505` count 5,
  unchanged), and the `held` comprehension, the replay test, the `ended` status choice and the
  flush-alone block are byte-unchanged.
- Suite after the change: **1250 unit / 325 e2e / 229 schema**, `ruff check src tests` clean.

## Task Commits

1. **Task 1 (RED): the failing source-side case** — `faef7aa` (test)
2. **Task 1 (GREEN): the narrowed superseded set** — `8e01306` (fix)
3. **Task 2: the destination-side counterpart** — `2010727` (test)

_No REFACTOR commit: the fix is five lines inside one assignment and had nothing to clean up._

## Files Created/Modified

- `src/nativespeaker/api/crud/subscriptions.py` — the entitled arm of `superseded` in
  `write_subscription_grant`, and the two comment lines above it. No new function, no signature
  change, no migration.
- `tests/schema/test_restore_race.py` — `commit_subscription` and `proof_for` each take an optional
  `external_id`; two module-level readers (`active_grants`, `grants_for`); the two new classes and
  their seven cases.

## Decisions Made

- **The fixture reproduces CR-03's three steps, not the plan's five-step list.** The plan's list
  committed both subscriptions to the source and then ran one restore before the move, so the
  source never held a grant for the moving subscription — which made the plan's own instruction
  ("the source's grant for the moved subscription was already superseded by step 4") describe a row
  that did not exist, and made
  `test_the_source_holds_no_active_grant_for_the_moved_subscription` vacuous. One extra
  `run_attempt` was added: the source restores the moving subscription first, then the unrelated
  one, which supersedes the first grant. That is CR-03's reproduction exactly, it makes the plan's
  comment true, and it makes the fourth case non-vacuous.
- **The two new classes use class-level `pytest_asyncio.fixture`s, as every other class in the file
  does.** The plan asked for a module-scoped fixture; the `harness` fixture these depend on is
  function-scoped, so a module-scoped fixture cannot take it. Function scope also matches
  `raced`, `moved`, `interrupted` and `misordered`.
- **No free-grant case on real PostgreSQL**, as the plan directs:
  `tests/e2e/test_restore_subscription.py` already covers a free grant superseded on the restore
  path. Recorded in the class docstring so a later reader sees the decision rather than the absence.
- **The comment above the narrowed line is two lines, and says "the free one too" rather than "the
  free one included".** The longer phrasing put the line at 123 characters, over the project's
  `line-length = 120`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's fixture recipe never wrote the row its own comment described**

- **Found during:** Task 1
- **Issue:** The plan's five-step fixture list gives the source no grant for the moving
  subscription, but the plan then instructs the executor to comment that "the source's grant for
  the moved subscription was already superseded by step 4". Written as specified, the comment would
  have been false and
  `test_the_source_holds_no_active_grant_for_the_moved_subscription` would have asserted the
  absence of a row nothing had ever created.
- **Fix:** One extra `run_attempt` — the source restores the moving subscription before the
  unrelated one — which is CR-03's own step 1. The unrelated restore then supersedes that grant,
  which is CR-03's step 2, and the move is step 3.
- **Files modified:** `tests/schema/test_restore_race.py`
- **Verification:** The fourth case now reads a real expired row for the moved subscription;
  the source-side case still went red against the pre-fix source.
- **Committed in:** `faef7aa` (Task 1 RED commit)

**2. [Rule 3 - Blocking] The plan's comment wording exceeded the line-length limit**

- **Found during:** Task 1
- **Issue:** `uv run ruff check src tests` reported
  `E501 Line too long (123 > 120)` on the first of the two new comment lines.
- **Fix:** "the free one included" became "the free one too", which keeps both ideas and the index
  name at 118 characters.
- **Files modified:** `src/nativespeaker/api/crud/subscriptions.py`
- **Verification:** `uv run ruff check src tests` — All checks passed.
- **Committed in:** `8e01306` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both are inside the plan's own named files and named symbols. The first makes
the plan's stated intent true rather than widening it; the second is a formatting limit the project
already enforces. No scope creep.

## Issues Encountered

None. The precondition — a real PostgreSQL 17 instance behind `_schema_db_uri` — was checked before
any edit by running the existing `tests/schema/test_restore_race.py` (17 passed).

## Observed RED states

The plan requires both to be recorded here.

- **Source side, against the pre-fix source.**
  `TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves::test_the_source_keeps_its_active_grant_for_the_unrelated_subscription`
  failed with `AssertionError: assert 'expired' == 'active'`. The other three cases of that class
  passed pre-fix, which is what makes them controls rather than duplicates. Run: `1 failed, 20 passed`.
- **Destination side, against an over-narrowed condition.** With `and` in place of `or`, and again
  with the `subscription_id` clause alone, all three cases of
  `TestTheDestinationStillLosesEverythingItHeld` errored: the destination's grant for its own
  subscription survived, so the move's insert hit
  `ix_access_grants_one_active_per_user`, answered `lost_race`, and the fixture's
  `assert status_of(move) == 200` failed. The source was reverted with
  `git checkout -- src/nativespeaker/api/crud/subscriptions.py` after each experiment, and the
  restored line was re-read to confirm the `or`.

## Verification

| Command | Result |
|---------|--------|
| `uv run pytest -m schema tests/schema/test_restore_race.py -q` | 24 passed |
| `uv run pytest -m schema -q` | 229 passed |
| `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q` | 27 passed |
| `uv run pytest -m e2e -q` | 325 passed |
| `uv run pytest tests/unit/test_subscription_attribution.py -q` | 21 passed |
| `uv run pytest -q` | 1250 passed |
| `uv run ruff check src tests` | All checks passed |
| `grep -v '^ *#' src/…/crud/subscriptions.py \| grep -c 'list(marked_active)'` | `0` (was `1`) |
| `grep -c 'with_for_update' src/…/crud/subscriptions.py` | `0` (unchanged) |
| `grep -c '23505' src/…/crud/subscriptions.py` | `5` (unchanged) |

## Threat Flags

None. The change adds no network endpoint, no auth path, no file access and no schema change. The
threat register's own dispositions stand: T-45-08-01 and T-45-08-02 are mitigated by the narrowing
and pinned by the seven new cases; T-45-08-03 (a move writes no audit row) stays **accepted**, for
the reason the plan records — CONTEXT's "Carried forward" deletes `audit.auth_events`, and a
gap-closure plan may not reverse it.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- VERIFICATION truth 6 can be re-run and answered VERIFIED. Truth 1 (CR-02, the unreconciled
  status/term pair) stays open and is 45-07's work; truth 7 (CR-01) was closed by 45-06.
- RESTORE-01 stays **BLOCKED** in `45-VERIFICATION.md` until truth 1 is also closed: the
  requirement's own word "verified" needs both defects gone, and this plan closes one of the two.
- Nothing here changes the webhook ingestion path, so Phase 43's and Phase 44's guarantees are
  untouched — proved rather than assumed by the 325 e2e and 229 schema cases.

## Self-Check: PASSED

- `src/nativespeaker/api/crud/subscriptions.py` — FOUND
- `tests/schema/test_restore_race.py` — FOUND
- Commit `faef7aa` — FOUND
- Commit `8e01306` — FOUND
- Commit `2010727` — FOUND

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*
