---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 01
subsystem: api
tags: [postgres, sqlalchemy, sqlmodel, fastapi, pytest, quota, entitlements]

requires:
  - phase: 37.5-restore-the-layered-architecture
    provides: QuotaService as the one merged charge, ChatService as its caller
  - phase: 38-auth-sync
    provides: the shared effective-grant predicate in crud/grants.py
provides:
  - The effective-grant predicate compares against func.clock_timestamp(), not a value the caller supplied
  - GrantsDB.lock_effective_grants and GrantsDB.read_effective_grants take user_id alone
  - QuotaService.charge takes user_id alone and reads the clock once
  - ChatService holds no datetime, and get_chat_service declares none
affects: [47-02, 47-03, 47-04, 47-05, 47-06, 47-07, 50]

actuals:
  tokens: 82690
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "A SQL comparison against the current time uses func.clock_timestamp(), never func.now()"
    - "One clock read per method, at the top, driving every value that method writes"
    - "A test reaches a period branch by controlling the stored month, not by pinning a clock"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/grants.py
    - src/nativespeaker/api/services/quota.py
    - src/nativespeaker/api/services/chats.py
    - src/nativespeaker/api/services/sync.py
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/app/dependencies.py
    - tests/unit/test_quota_resolver.py
    - tests/unit/test_quota_seam.py
    - tests/unit/conftest.py
    - tests/unit/test_sync_resolver.py
    - tests/e2e/test_quota.py
    - tests/schema/test_grant_locks.py
    - tests/schema/test_sync_lock_freedom.py

key-decisions:
  - "D-01 applied: the effective-grant predicate uses func.clock_timestamp(). func.now() is transaction_timestamp() and the e2e harness holds one outer transaction per test, so a seeded grant is invisible to it."
  - "seconds_until_rollover keeps its one parameter but the parameter is renamed to instant, because the acceptance criterion required zero occurrences of the old name in the module."
  - "Two unit cases that asserted the statement carried the threaded instant now assert it binds no datetime and carries the database clock on both bounds."
  - "Task 1 also updated services/quota.py and the unit-test fakes that mirror the reader signature, because the plan put them in later tasks and the suite has to be green at every commit."

patterns-established:
  - "Pattern 1: a comparison against the current time is made in SQL by func.clock_timestamp(), and the statement binds no datetime at all"
  - "Pattern 2: a period branch is reached by a stored month literal far in the past or far in the future, so the case never reads a clock"

requirements-completed: []

coverage:
  - id: D1
    description: "The effective-grant predicate compares starts_at and ends_at against func.clock_timestamp() and takes no datetime"
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py#TestEveryLockedReadIsKeyedOnWhatTheOneBeforeItNamed::test_both_grant_bounds_ask_the_database_for_the_time"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestEveryReadIsKeyedOnWhatTheOneBeforeItNamed::test_both_grant_bounds_ask_the_database_for_the_time"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'clock_timestamp' src/nativespeaker/api/crud/grants.py)\" = \"2\""
        status: pass
    human_judgment: false
  - id: D2
    description: "Both public readers and every caller in src/ and in the schema suites drop the datetime argument"
    verification:
      - kind: integration
        ref: ".venv/bin/pytest tests/schema/test_grant_locks.py tests/schema/test_sync_lock_freedom.py -m schema (48 passed)"
        status: pass
      - kind: other
        ref: "grep -n 'def _effective_grants_statement' src/nativespeaker/api/crud/grants.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "QuotaService.charge takes only user_id, reads the clock once, and that one read drives the Retry-After, the period and usage.updated_at"
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py#TestTheChargeReadsTheClockItself"
        status: pass
      - kind: other
        ref: "grep -c 'datetime.now(UTC)' src/nativespeaker/api/services/quota.py == 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "ChatService holds no datetime and get_chat_service declares none"
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_seam.py#TestTheChatServiceHoldsNoClockReading::test_no_attribute_of_the_service_is_a_datetime"
        status: pass
      - kind: other
        ref: "grep -c 'get_evaluated_at' src/nativespeaker/api/app/dependencies.py == 6"
        status: pass
    human_judgment: false
  - id: D5
    description: "The two paid-entitlement boundary cases still refuse: a term not begun and a term over"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py#test_a_not_yet_started_grant_is_no_grant, #test_an_already_ended_grant_is_no_grant (41 passed)"
        status: pass
    human_judgment: false
  - id: D6
    description: "The rollover and retry-after boundaries are proved from stored state and from seconds_until_rollover directly, with no timing marker added"
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_resolver.py#TestLazyRollover, #TestTheRolloverIsDerivedFromTheInstantItIsGiven"
        status: pass
      - kind: other
        ref: "grep -c 'pytest.mark.timing' tests/unit/test_quota_resolver.py == 0"
        status: pass
    human_judgment: false

duration: 20 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 01: The tracer — the charge chain carries no instant Summary

**The effective-grant predicate now asks PostgreSQL for the time with `func.clock_timestamp()`, and the whole charge chain — `get_chat_service` to `ChatService` to `QuotaService.charge` to `GrantsDB.lock_effective_grants` to SQL — carries no datetime.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-09-12T05:34:56Z
- **Completed:** 2026-09-12T05:55:00Z
- **Tasks:** 3
- **Files modified:** 18

## Accomplishments

- `_effective_grants_statement` takes `user_id` alone. Both bounds compare against
  `func.clock_timestamp()`. Every operator is byte-identical to before: `== active`,
  `<=` on `starts_at`, `>` on `ends_at`, the `or_` NULL arm, the ascending order and the
  absent `.limit(...)`. The entitlement window was not widened or narrowed.
- `lock_effective_grants` and `read_effective_grants` lost their datetime parameter.
  Every caller lost the argument in the same commit: two inside `crud/grants.py`,
  one in `services/quota.py`, one in `services/sync.py`, three in `services/auth.py`,
  and three in the schema suites.
- `QuotaService.charge(user_id=...)` reads `datetime.now(UTC)` once as its first
  statement. That one value drives the `Retry-After` seconds, the `monthly_period_for`
  comparison and `usage.updated_at`. A rollover and the refusal it may produce cannot
  disagree about the month.
- `ChatService` holds no datetime at all, and `get_chat_service` declares none.
  `get_evaluated_at` still exists for the five factories later plans own.
- The quota tests reach the rollover branches by controlling the stored month, not by
  pinning a clock. No `@pytest.mark.timing` was added.

## Task Commits

1. **Task 1 (tracer): the predicate asks the database for the time** - `b1efe41` (refactor)
2. **Task 2 RED: failing tests for the charge reading its own clock** - `13c6396` (test)
3. **Task 2 GREEN: charge reads the clock once, ChatService holds none** - `6d407b1` (feat)
4. **Task 3: the quota docstrings describe the current time** - `75502a7` (test)

## Files Created/Modified

- `src/nativespeaker/api/crud/grants.py` - the predicate, both public readers, two internal call sites
- `src/nativespeaker/api/services/quota.py` - `charge` reads the clock once; `seconds_until_rollover`'s parameter renamed
- `src/nativespeaker/api/services/chats.py` - the datetime field and the `datetime` import are gone
- `src/nativespeaker/api/services/sync.py` - one call site lost its argument
- `src/nativespeaker/api/services/auth.py` - three call sites lost their argument
- `src/nativespeaker/api/app/dependencies.py` - `get_chat_service` declares no instant
- `tests/unit/test_quota_resolver.py` - the rollover cases run off stored state; the retry-after boundary runs off `seconds_until_rollover`
- `tests/unit/test_quota_seam.py` - the seam fixtures are keyed to this calendar month; a new case pins that the service holds no datetime
- `tests/unit/conftest.py` - `recording_charge` mirrors the real signature
- `tests/unit/test_sync_resolver.py`, `tests/unit/test_spent_free_grant_refusal.py`,
  `tests/unit/test_conversion_carries_usage.py`, `tests/unit/test_claim_precedence.py` - fake reader signatures mirror the real ones
- `tests/unit/test_sync_clock_capture.py` - the chat-service row left one parametrized case
- `tests/e2e/test_quota.py` - the two boundary docstrings describe the current time
- `tests/schema/test_grant_locks.py`, `tests/schema/test_sync_lock_freedom.py`,
  `tests/schema/test_subscription_ingestion.py` - call sites lost their argument

## Decisions Made

**D-01 applied as planned.** `func.clock_timestamp()`, not `func.now()`. The measured
reason stands: `now()` is `transaction_timestamp()`, `tests/e2e/conftest.py` holds one
outer transaction open per test and joins every app session to it with
`create_savepoint`, so a grant the test seeds is invisible to `now()`. The e2e quota
file reports 41 passed with `clock_timestamp()`.

**`seconds_until_rollover` keeps its parameter, renamed.** The plan's action said the
helper keeps its parameter and its body unchanged. The plan's own acceptance criterion
said `grep -c 'evaluated_at' src/nativespeaker/api/services/quota.py` must print `0`.
Both cannot hold while the parameter is named `evaluated_at`. The parameter is now
`instant`, which is the local name the pattern map prescribes. The signature is still
one parameter, the behaviour is identical, and every caller passes it positionally.

**Two statement cases changed subject rather than being deleted.**
`test_both_grant_bounds_carry_the_one_captured_instant`, in the quota and the sync
resolver suites, asserted the compiled statement carried two bound datetimes equal to
the instant the caller supplied. That fact no longer exists. Each case now asserts the
statement binds **no** datetime and carries `clock_timestamp()` on both bounds. The
operator guards it shared a class with — `starts_at <=` and `ends_at >` — are untouched.

**`test_a_different_instant_produces_a_different_period` became
`test_the_period_is_taken_from_neither_the_row_nor_the_grant`.** Its old property was
"the period tracks the argument", and there is no argument. The rewrite is a real and
otherwise unguarded property: the written period equals this calendar month and equals
neither the stored `monthly_period` nor the month of `grant.starts_at`. Three distinct
months make a period copied from either column fail.

**`test_the_updated_at_stamp_is_the_captured_instant` moved rather than vanished.** It
is now `TestTheChargeReadsTheClockItself::test_the_stamp_lands_inside_the_call_and_names_the_period_written`,
which brackets the stamp between two clock reads around the call and asserts the written
period is `monthly_period_for` of that same stamp. No case was deleted for convenience:
the two classes that lost a case gained more than they lost, and the unit suite grew from
1917 to 1918.

**`PERIOD` in the quota resolver suite is now derived from the live clock**
(`monthly_period_for(datetime.now(UTC))`), because "this month" is what the charge
writes and a fixed literal would rot. `STALE_PERIOD` and `AHEAD_PERIOD` are literals
(`2000-01`, `9999-12`) that stay on their side of the comparison forever, so no case
reads a clock to name a past or a future month.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 also updated `services/quota.py` and four unit-test fakes**
- **Found during:** Task 1
- **Issue:** The plan gave Task 1 the reader signature change and gave `services/quota.py:50`
  to Task 2 and the fake reader signatures to Task 3. Task 1's own `<verify>` is
  `pytest -q` over the whole unit suite, which cannot pass while a caller still sends an
  argument the reader no longer takes.
- **Fix:** Task 1 dropped the argument at `services/quota.py:50` and shrank the fake
  `lock_effective` / `read_effective` signatures in `test_spent_free_grant_refusal.py`,
  `test_conversion_carries_usage.py`, `test_claim_precedence.py` and the two `_issued`
  lambdas in `test_sync_resolver.py`. This is the plan's own `key_links` rule — no caller
  is left passing a value nothing reads.
- **Files modified:** `src/nativespeaker/api/services/quota.py`, four unit test files
- **Verification:** 1917 unit passed, 291 schema passed, 41 e2e quota passed
- **Committed in:** `b1efe41`

**2. [Rule 3 - Blocking] Task 1 rewrote two statement cases the plan did not list**
- **Found during:** Task 1
- **Issue:** `test_both_grant_bounds_carry_the_one_captured_instant` in
  `test_quota_resolver.py` and `test_sync_resolver.py` asserted `instants == [EVALUATED_AT,
  EVALUATED_AT]` over the compiled statement's bound parameters. With the comparison in
  SQL the statement binds no datetime, so both went red.
- **Fix:** Each case now asserts no bound value is a datetime and the compiled text carries
  `clock_timestamp()` twice. Renamed and reworded so neither names the removed dependency.
- **Files modified:** `tests/unit/test_quota_resolver.py`, `tests/unit/test_sync_resolver.py`
- **Verification:** both cases pass; the neighbouring operator guards are unchanged and pass
- **Committed in:** `b1efe41`

**3. [Rule 3 - Blocking] Task 2 absorbed the test edits the new `charge` signature forces**
- **Found during:** Task 2
- **Issue:** The plan gave Task 2 the three source files and Task 3 the test pass. Task 2's
  `<verify>` is `pytest -q`, so the `_charge` and `_refusal` helpers, the `recording_charge`
  and `refusing_charge` monkeypatches, the `ChatService` constructions and the four cases
  that passed an instant all had to change in the same commit as the signature.
- **Fix:** Task 2's commit carries the source change plus every test edit the signature
  forces, done the way Task 3 prescribes — stored state for the rollover branches,
  `seconds_until_rollover` called directly for the retry-after boundary, a bracket for the
  stamp. Task 3 then carried the remaining work: the docstring rewordings and the two e2e
  boundary docstrings.
- **Files modified:** `tests/unit/test_quota_resolver.py`, `tests/unit/test_quota_seam.py`,
  `tests/unit/conftest.py`
- **Verification:** 1918 unit passed, ruff clean
- **Committed in:** `6d407b1`

**4. [Rule 3 - Blocking] `tests/schema/test_sync_lock_freedom.py` and
`tests/unit/test_sync_clock_capture.py` both name the changed shapes**
- **Found during:** Task 2
- **Issue:** The schema file called `QuotaService.charge(user_id=..., evaluated_at=...)`
  at two places, and `test_sync_clock_capture.py` parametrized
  `test_every_service_dependency_takes_the_one_captured_instant` over `get_chat_service`,
  which this plan is what removes. Neither file is in the plan's `files_modified`.
- **Fix:** Both charge calls dropped the keyword. `get_chat_service` left that one
  parametrized case; the file itself is plan 47-07's to delete.
- **Files modified:** `tests/schema/test_sync_lock_freedom.py`, `tests/unit/test_sync_clock_capture.py`
- **Verification:** 291 schema passed, 1918 unit passed
- **Committed in:** `6d407b1`

**5. [Rule 3 - Blocking] The `seconds_until_rollover` parameter was renamed**
- **Found during:** Task 2
- **Issue:** Acceptance criterion "`grep -c 'evaluated_at' src/nativespeaker/api/services/quota.py`
  prints `0`" contradicts the action's "`seconds_until_rollover` keeps its parameter and its
  body unchanged", because the parameter is named `evaluated_at`.
- **Fix:** Renamed to `instant`, the name the pattern map prescribes. The signature is still
  one parameter and the arithmetic is identical. No caller uses a keyword.
- **Files modified:** `src/nativespeaker/api/services/quota.py`
- **Verification:** the four `seconds_until_rollover` cases pass; ruff clean; the criterion prints `0`
- **Committed in:** `6d407b1`

---

**Total deviations:** 5 auto-fixed (5 blocking).
**Impact on plan:** No scope creep. Every deviation is a call site or a case that names a
shape this plan changes, pulled into the commit that changes it so the suite is green at
every commit. The plan's task boundaries moved; its content did not.

## Issues Encountered

**One pre-existing e2e failure, out of scope and not fixed.**
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`
expects the log event name `proof_rejected`; the code emits `purchase_proof_rejected`.
This was measured, not assumed: every plan 47-01 edit was reverted to HEAD (`1a3273d`),
the case was run alone, and it failed identically. Recorded in
`47-stop-threading-an-evaluation-instant-through-the-layers/deferred-items.md` and in
`.planning/WINDOWS.md`. The e2e suite is therefore 361 passed / 1 failed, and the 1 is not
this plan's.

**The type checker's baseline is unchanged.** `.venv/bin/ty check` reports 316 diagnostics
before and after this plan, measured both ways by reverting the changed files. No new
diagnostic was introduced.

## Threat Flags

None. T-47-01's mitigation held: every operator in the effective-grant predicate is
byte-identical and both `tests/e2e/test_quota.py` boundary cases pass. T-47-02 and T-47-03
were accepted in the plan and are unchanged. No package was installed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The architecture the whole phase rests on is proven on one full chain against the real
  database. A database-side clock in the entitlement predicate is not wrong: 41 e2e quota
  tests, 291 schema tests and 1918 unit tests are green with it.
- Plan 47-02 (strike the `SHARED-INVARIANTS.md` one-evaluation-time clause, D-02) and plan
  47-03 (the `crud/grants.py` writers) can both start. `activate_anonymous_device_grant`
  and `activate_registered_account_grant` still take `evaluated_at`, exactly as planned.
- `get_evaluated_at` and the five factories that still declare it are untouched, and
  `app/dependencies.py` is otherwise intact for Phase 50.
- One concern to carry forward: `tests/unit/test_sync_clock_capture.py` now asserts the
  one-captured-instant discipline over two factories instead of three. Plan 47-07 deletes
  the file; until then it is a weaker guard than it was.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*

## Self-Check: PASSED

Every file named in `key-files.modified` exists on disk and all four task commits are
reachable in `git log`.
