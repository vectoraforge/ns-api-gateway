---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 03
subsystem: api
tags: [postgres, sqlalchemy, sqlmodel, pytest, entitlements, grants, identities]

requires:
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-01: the effective-grant predicate compares against func.clock_timestamp(), and the readers take user_id alone"
  - phase: 38-auth-sync
    provides: the shared effective-grant predicate in crud/grants.py
provides:
  - GrantsDB.activate_anonymous_device_grant takes no datetime and reads the clock once
  - GrantsDB.activate_registered_account_grant takes no datetime and reads the clock once
  - IdentitiesDB.insert_account takes no datetime and reads the clock once
  - IdentitiesDB.flip_provider takes no datetime and reads the clock once
  - AuthService hands no crud writer an instant; only the two challenge calls still carry one
affects: [47-04, 47-05, 47-06, 47-07, 48, 50]

actuals:
  tokens: 9988
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "One clock read per writer method, as its first statement, driving every column that method stamps"
    - "A case proves the single read by an equality between two columns one write stamped, plus a bracket around the call"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/grants.py
    - src/nativespeaker/api/crud/identities.py
    - src/nativespeaker/api/services/auth.py
    - tests/unit/test_conversion_carries_usage.py
    - tests/unit/test_spent_free_grant_refusal.py
    - tests/unit/test_claim_precedence.py
    - tests/unit/test_identity_flip.py
    - tests/unit/test_upgrade_precedence.py
    - tests/schema/test_grant_locks.py
    - tests/schema/test_claim_race.py
    - tests/e2e/test_claim_anonymous_grant.py
    - tests/e2e/test_claim_registered_grant.py

key-decisions:
  - "The CHECK-violation schema case could not be rewritten as the plan prescribed. Seeding the grant row directly cannot raise inside the writer's flush, which is the property under test. The case now flushes a row breaking `ends_at > starts_at` with the writer's own inserts, and the driver's real 23514 is asserted."
  - "A state the old case reached is now unreachable: the writer always stamps a time after any grant it can supersede, so `ends_at <= starts_at` cannot arise from the writer itself."
  - "tests/schema/test_claim_race.py had to change with the writers. Five cases compared a stored column against the fixed instant the harness supplied. Each now reads the value the writer stamped and pins it to a sibling column."
  - "Two test-local constants named EVALUATED_AT were renamed SEEDED_AT, because their role changed from the instant handed to the writer to the instant the seed rows are dated from."

patterns-established:
  - "Pattern 1: a writer's single read is proved by a set equality over every column it stamped, with a bracket case as the control that the value is read inside the call"
  - "Pattern 2: a schema case that needs a non-unique IntegrityError from the writer's own flush adds the offending row through the flush-interception proxy the file already carries"

requirements-completed: []

coverage:
  - id: D1
    description: "Both free-grant writers take no datetime and read the clock exactly once each"
    verification:
      - kind: unit
        ref: "tests/unit/test_conversion_carries_usage.py#TestOneConversionStampsEveryColumnWithOneValue::test_every_column_the_conversion_writes_carries_the_same_value"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conversion_carries_usage.py#TestOneConversionStampsEveryColumnWithOneValue::test_the_value_is_read_inside_the_call_and_not_copied_from_the_old_grant"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'datetime.now(UTC)' src/nativespeaker/api/crud/grants.py)\" = \"2\" and grep -c evaluated_at == 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "The two e2e equality assertions still hold, which is the proof the read is once per method"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py, tests/e2e/test_claim_registered_grant.py (28 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both identity writers take no datetime, read the clock once, and keep the anonymous-provider condition on registered_at"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_flip.py#TestOneFlipStampsEveryColumnWithOneValue::test_the_three_columns_the_flip_writes_carry_the_same_value"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_flip.py#TestTheFlipSetsWhereUnsetAndNeverOverwrites (6 cases)"
        status: pass
      - kind: other
        ref: "grep -c 'registered_at=None if provider is IdentityProvider.anonymous' src/nativespeaker/api/crud/identities.py == 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "AuthService hands no crud writer an instant; the field serves the two challenge calls alone"
    verification:
      - kind: other
        ref: "grep -c 'evaluated_at' src/nativespeaker/api/services/auth.py == 4"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py, test_claim_precedence_registered.py, test_upgrade_precedence.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "No schema case hands an activation writer a datetime, and the suite is at its baseline count"
    verification:
      - kind: integration
        ref: ".venv/bin/pytest tests/schema -m schema (291 passed, the measured baseline)"
        status: pass
      - kind: other
        ref: "grep -c 'activate_.*_grant(.*evaluated_at' tests/schema/test_grant_locks.py == 0"
        status: pass
    human_judgment: false
  - id: D6
    description: "The refusal of a non-unique IntegrityError is still proved against the real driver"
    verification:
      - kind: integration
        ref: "tests/schema/test_grant_locks.py#TestTheRegisteredWriterNamesWhyItRefused::test_a_check_violation_is_raised_and_never_read_as_a_lost_race"
        status: pass
    human_judgment: false

duration: 23 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 03: The grant and identity writers read their own clock Summary

**The two free-grant writers and the two identity writers take no datetime. Each reads `datetime.now(UTC)` once, as its first statement, and stamps every column of its write from that one read.**

## Performance

- **Duration:** 23 min
- **Started:** 2026-09-12T06:03:42Z
- **Completed:** 2026-09-12T06:26:30Z
- **Tasks:** 3
- **Files modified:** 12

## Accomplishments

- `activate_anonymous_device_grant` and `activate_registered_account_grant` lost their
  `evaluated_at` parameter. Each reads `instant` once. Nine uses and ten uses became one
  read each. `grep -c 'datetime.now(UTC)'` over `crud/grants.py` prints `2`, which is one
  per writer and not one per assignment.
- `insert_account` and `flip_provider` did the same. The anonymous-provider condition on
  `registered_at` is pinned verbatim by a grep and still reads `None` for an anonymous
  account.
- `AuthService` hands none of the four crud writers an instant. Its field has two readers
  left, both `challenge_store` calls, exactly as the plan required.
- The two e2e equality assertions survive and pass. `identity.free_grant_consumed_at ==
  grant.starts_at` is what a second clock read inside either writer would break. Their
  one-line comments are deleted; the assertions are not.
- Three new unit cases prove the single read at the writer: a set equality over every
  column one conversion stamps, a bracket that the value is read inside the call, and the
  same equality for the flip's three columns.
- Suites: **1921 unit / 361 e2e / 291 schema**, `ruff check src tests` clean, `ty check`
  **315** diagnostics against a **316** baseline measured at the pre-plan commit.

## Task Commits

1. **Task 1 RED: drive the free-grant writers with no datetime** - `ef9dfd0` (test)
2. **Task 1 GREEN: the two free-grant writers read their own instant** - `d98f3ea` (refactor)
3. **Task 2 RED: drive the identity writers with no datetime** - `8548701` (test)
4. **Task 2 GREEN: the two identity writers read their own instant** - `1c46024` (refactor)
5. **Task 3: the schema cases drive the writers with no datetime** - `f26a518` (test)
6. **Type-checker baseline kept flat** - `2552426` (fix)

## Files Created/Modified

- `src/nativespeaker/api/crud/grants.py` - both activation writers read their own instant
- `src/nativespeaker/api/crud/identities.py` - both identity writers read their own instant
- `src/nativespeaker/api/services/auth.py` - four call sites lost the keyword
- `tests/unit/test_conversion_carries_usage.py` - the one-read cases, and a helper for the superseded usage row
- `tests/unit/test_spent_free_grant_refusal.py` - the writer is driven with no datetime
- `tests/unit/test_claim_precedence.py` - the shared `_RecordingGrants.activate` fake mirrors the real signature
- `tests/unit/test_identity_flip.py` - the flip is driven with no datetime; the one-read case is new
- `tests/unit/test_upgrade_precedence.py` - the fake `flip` reads its own datetime
- `tests/schema/test_grant_locks.py` - every `activate_*` call and the two locals that fed them; the CHECK-violation case rewritten
- `tests/schema/test_claim_race.py` - five cases read the value the writer stamped
- `tests/e2e/test_claim_anonymous_grant.py`, `tests/e2e/test_claim_registered_grant.py` - the two comments deleted, the assertions kept

## Decisions Made

**The CHECK-violation schema case was rewritten, but not the way the plan said.** The plan
directed the "past-term" case to seed its grant row directly with a raw INSERT. Two facts
made that wrong, both measured rather than reasoned about. First, the `evaluated_before`
knob of `_account_holding` that the pattern map pointed at had **no caller at all**; it was
dead and is now deleted. Second, the case that actually broke is
`test_a_check_violation_is_raised_and_never_read_as_a_lost_race`. It seeded a grant with
`starts_before=timedelta(0)` so the writer's own expiry UPDATE set `ends_at == starts_at`
and broke the table's strict CHECK. The property under test is that the narrowed
`except IntegrityError` **re-raises** a non-unique code instead of reporting `lost_race`.
A directly seeded row cannot raise inside the writer's flush, so the plan's rewrite would
have deleted the property. The case now uses the file's own `_CommitsBeforeTheFlush` proxy
to add a row breaking `ends_at > starts_at` to the writer's session just before its flush.
The driver's real code was probed and is **23514**, so the assertion was strengthened from
`!= "23505"` to `== "23514"`.

**One state is now unreachable, and that is the design, not a gap.** For the writer to
produce `ends_at <= starts_at` on the superseded row, the grant it supersedes would have to
start at or after the writer's own clock read. A grant that starts after that read is not
effective, so the writer never locks it. The old case reached the state only because a
caller could hand the writer an instant from the past. That caller is gone.

**`tests/schema/test_claim_race.py` is not in the plan's file list but names the shapes this
plan changes.** Five cases compared a stored column against the harness's fixed `NOW`. Each
now reads the value the writer stamped: the usage period is this calendar month, the
lifetime marker is compared to the grant's own `starts_at`, and the expired row's `ends_at`
is compared to the replacement's `starts_at`. Two of these are stronger than what they
replaced, because they pin the single read across a supersession rather than an equality
with a constant.

**Two test-local constants were renamed `SEEDED_AT`.** In
`test_conversion_carries_usage.py` and `test_spent_free_grant_refusal.py` the constant was
the instant handed to the writer. It is now only the date the seeded rows carry. The old
name would read as threading that no longer exists. `FRESH_PERIOD` in the first file is
derived from the live clock for the same reason: the period the writer writes is this
month, not the month of a fixed literal.

**The superseded-term overlap the plan accepted was not closed.** Within one call to
`activate_registered_account_grant` the superseded `ends_at` and the replacement `starts_at`
come from one read and stay equal, which a schema case now asserts. Across a service that
calls several writers the reads differ by microseconds. No machinery was added.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 also changed three unit test files the plan did not list**
- **Found during:** Task 1
- **Issue:** `tests/unit/test_conversion_carries_usage.py` and
  `tests/unit/test_spent_free_grant_refusal.py` drive the real registered writer with
  `evaluated_at=`, and `tests/unit/test_claim_precedence.py` holds the shared
  `_RecordingGrants.activate` fake whose signature both claim-precedence suites monkeypatch
  in. Task 1's own `<verify>` is the whole unit suite, which cannot pass while a caller
  still sends an argument the writer no longer takes.
- **Fix:** All three dropped the keyword in Task 1's RED commit, which is also where the
  new one-read cases were written.
- **Files modified:** the three files named above
- **Verification:** 49 failed at RED, 1920 passed at GREEN
- **Committed in:** `ef9dfd0` and `d98f3ea`

**2. [Rule 3 - Blocking] Two cases in `test_identity_flip.py` compared a column against `NOW`**
- **Found during:** Task 2
- **Issue:** The plan said to drop `evaluated_at=NOW` and delete `NOW` if nothing else read
  it. Two cases did read it: `user.registered_at == NOW` and `user.updated_at == NOW`.
- **Fix:** The first brackets the stamp between two clock reads around the call. The second
  asserts `updated_at > REGISTERED_AT`, which is the control's own property — that the
  repair records that it ran. `NOW` and the `timedelta` import then had no reader and went.
- **Files modified:** `tests/unit/test_identity_flip.py`
- **Verification:** the six cases of that class pass; the file is green
- **Committed in:** `8548701`

**3. [Rule 3 - Blocking] `tests/schema/test_claim_race.py` broke on the new writers**
- **Found during:** Task 3
- **Issue:** Five cases in a file the plan does not name compared stored columns against the
  harness's fixed `NOW`. The schema suite went from 291 to 286 passed.
- **Fix:** Each case now reads the value the writer stamped. Detailed under Decisions.
- **Files modified:** `tests/schema/test_claim_race.py`
- **Verification:** 291 schema passed, which is the measured baseline exactly
- **Committed in:** `f26a518`

**4. [Rule 1 - Bug] Three new cases raised five `ty` diagnostics**
- **Found during:** the plan-level verification
- **Issue:** `ty check` read 321 against a baseline of 316. The bracket over the optional
  `user.registered_at`, two more `UserMonthlyUsage(...)` constructions missing their two
  stamps, and one more `_Account(session=<proxy>)` construction.
- **Fix:** `registered_at` is asserted present before it is bracketed. The superseded usage
  row is built by one `_spent_usage` helper that supplies `created_at` and `updated_at`,
  which also removed the one pre-existing diagnostic of that shape. The proxy construction
  carries the same `# ty: ignore[invalid-argument-type]` the repository already uses for a
  session stand-in.
- **Files modified:** `tests/unit/test_identity_flip.py`,
  `tests/unit/test_conversion_carries_usage.py`, `tests/schema/test_grant_locks.py`
- **Verification:** 315 diagnostics, measured against 316 read from a clean checkout of the
  pre-plan commit in `/tmp`
- **Committed in:** `2552426`

**5. [Rule 1 - Bug] The plan's Task 3 rewrite did not fit the case it named**
- **Found during:** Task 3
- **Issue:** Described in full under Decisions. The `evaluated_before` knob the plan and the
  pattern map both pointed at had no caller, and the case that actually failed needs the
  IntegrityError to be raised **inside** the writer's flush.
- **Fix:** The dead knob is deleted. The case flushes an offending row with the writer's own
  inserts through the existing interception proxy, and asserts the driver's real 23514.
- **Files modified:** `tests/schema/test_grant_locks.py`
- **Verification:** the sqlstate was probed and printed before the assertion was written;
  45 cases in the file pass
- **Committed in:** `f26a518`

---

**Total deviations:** 5 auto-fixed (3 blocking, 2 bugs).
**Impact on plan:** No scope creep. Three deviations are call sites or cases that name a
shape this plan changes, pulled into the commit that changes it so every suite is green at
every commit. One keeps the type checker's baseline flat. One replaces a rewrite the plan
prescribed with one that preserves the property the case exists to prove.

## Issues Encountered

**One command destroyed uncommitted work and it had to be redone.** A `git checkout --` on
`tests/schema/test_grant_locks.py`, used to revert a temporary probe line, reverted the
whole file and lost every Task 3 edit in it. The edits were reapplied from the same reads.
Nothing committed was affected and no other file was touched. The lesson is the one this
project's own rules already state: a blanket revert is never the way to undo one line.

**One pre-existing e2e failure, out of scope and not fixed.**
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`
expects the log event `proof_rejected` while the code emits `purchase_proof_rejected`. Plan
47-01 measured it at HEAD before this phase started and recorded it in
`deferred-items.md` and `.planning/WINDOWS.md`. The e2e suite is 361 passed / 1 failed and
the 1 is not this plan's.

## Known Stubs

None. No hardcoded empty value, placeholder string or unwired component was written.

## Threat Flags

None. T-47-09's mitigation held: the one read per method is what the three new unit cases
and the two kept e2e equality assertions prove. T-47-10's mitigation held: the
anonymous-provider condition is byte-identical and its grep prints `1`. T-47-05 was
accepted in the plan and no machinery was added. No package was installed and no manifest
was touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The four writers this plan owns take no datetime. `crud/subscriptions.py` and
  `crud/challenges.py` still do, which is plan 47-04's and 47-05's work.
- `AuthService.evaluated_at` is down to two readers, both `challenge_store` calls. Plan
  47-06 removes them and the field, and nothing else now blocks that.
- `app/dependencies.py` and `get_evaluated_at` are untouched, so Phase 50 still sees the
  shape it planned against.
- One thing to carry forward: `tests/schema/test_claim_race.py` now derives an expected
  monthly period from the live clock inside two assertions. A run that straddles a UTC month
  boundary between the request and the read would fail. The window is one instant a month
  and the alternative was a literal that rots, so it is recorded rather than guarded.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*

## Self-Check: PASSED

Every file named in `key-files.modified` exists on disk, and all seven commits of this plan
are reachable in `git log`.
