---
phase: 42-post-auth-claim-registered-grant
plan: 07
subsystem: auth
tags: [postgres, sqlmodel, asyncpg, devicecheck, partial-unique-index, sqlstate, fastapi]

requires:
  - phase: 42-post-auth-claim-registered-grant
    provides: "the registered claim route, its crud writer, and the six plans this one repairs"
  - phase: 41-post-auth-claim-anonymous-grant
    provides: "the anonymous claim, its writer, and the DeviceCheck bit0 gate this plan also guards"
provides:
  - "Two index-shaped reads that ask what the unique indexes ask, with no time window in either"
  - "A three-valued ActivationOutcome, so a refusal and a lost race stop sharing one answer"
  - "Both claim preflights refusing, before Apple, every state the indexes will refuse"
  - "A narrowed IntegrityError catch: only SQLSTATE 23505 is a race, every other violation surfaces"
  - "The second-effective-grant tripwire on both writers and on the registered preflight"
affects: [43-app-store-webhook, subscription-grants, quota-enforcement]

actuals:
  tokens: 16573
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "One question, one read: an entitlement read carries the time window, an index question never does"
    - "A writer names why it refused; the route, not the writer, decides the status code"
    - "A driver error class is read off an attribute (`sqlstate`), never by importing the driver"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/grants.py
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/services/auth.py
    - tests/e2e/test_claim_registered_grant.py
    - tests/e2e/test_claim_anonymous_grant.py
    - tests/schema/test_grant_locks.py
    - tests/unit/test_claim_precedence.py
    - tests/unit/test_claim_precedence_registered.py
    - tests/unit/test_claim_ordering.py
    - tests/unit/test_rejection_vocabulary.py
    - tests/unit/test_grant_sources.py

key-decisions:
  - "The status-only read mirrors ix_access_grants_one_active_per_user exactly and carries no time window, because a partial index predicate must be IMMUTABLE and now() cannot appear in one"
  - "The Apple bit write stays after the database decision; the fix asks the index's question earlier, it never reorders the two writes"
  - "In the registered writer the conversion-loser branch is tested before holds_grant_of_source, because a fresh statement snapshot would otherwise see the winner's committed row and turn a race loser into a 403"
  - "`enum` was added to the crud module's import allow-list; `asyncpg` was not, and the SQLSTATE is read off an attribute"
  - "The plan's third CR-01 case is unseedable and was dropped: ix_access_grants_one_active_per_user forbids the two active rows it asks for"

patterns-established:
  - "Index-shaped read: a read whose predicate is a partial index's predicate, character for character, and whose comment names the index"
  - "Three-valued writer outcome: activated / lost_race / refused, with the assignment rule written in the enum's own comment"
  - "Backstop re-read: after a lost race the service re-reads, and a re-read that finds nothing is a refusal, so a 200 reporting a grant the caller does not hold is structurally impossible"

requirements-completed: [REGGRANT-01, REGGRANT-02, REGGRANT-03, ANONGRANT-02]

coverage:
  - id: D1
    description: "CR-01 closed on the registered route: a term-lapsed active row is refused 403 before the DeviceCheck bit1 is read or written"
    requirement: "REGGRANT-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_registered_grant.py::TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple::test_a_term_lapsed_active_grant_is_refused_and_no_bit_is_read_or_written"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_claim_registered_grant.py::TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple::test_an_expired_row_is_not_a_term_lapsed_active_row_and_the_claim_succeeds"
        status: pass
    human_judgment: false
  - id: D2
    description: "CR-01 closed on the anonymous route on the same terms with bit0"
    requirement: "ANONGRANT-02"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py::TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple::test_a_term_lapsed_active_grant_is_refused_and_no_bit_is_read_or_written"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-02 closed: a revoked registered grant refuses the conversion instead of answering 200 with the unchanged anonymous entitlement"
    requirement: "REGGRANT-03"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_registered_grant.py::TestASpentRegisteredSlotRefusesTheConversion::test_a_revoked_registered_grant_refuses_the_conversion_and_leaves_the_anonymous_row"
        status: pass
      - kind: integration
        ref: "tests/schema/test_grant_locks.py::TestTheRegisteredWriterNamesWhyItRefused::test_a_spent_registered_slot_is_refused_and_not_lost"
        status: pass
    human_judgment: false
  - id: D4
    description: "WR-03 closed: the writers answer with a three-valued ActivationOutcome, so 403 is a refusal and 200 is only a race with a row to read back"
    requirement: "REGGRANT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_claim_precedence_registered.py::TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_a_refused_write_rolls_back_answers_four_hundred_and_three_and_refreshes_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence_registered.py::TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_a_lost_race_whose_re_read_finds_nothing_is_refused_rather_than_reported_as_a_grant"
        status: pass
      - kind: integration
        ref: "tests/schema/test_grant_locks.py::TestTheRegisteredWriterNamesWhyItRefused"
        status: pass
    human_judgment: false
  - id: D5
    description: "WR-01 closed: only SQLSTATE 23505 becomes a lost race; a CHECK violation is re-raised and surfaces as the 500 it is"
    requirement: "REGGRANT-02"
    verification:
      - kind: integration
        ref: "tests/schema/test_grant_locks.py::TestTheRegisteredWriterNamesWhyItRefused::test_a_check_violation_is_raised_and_never_read_as_a_lost_race"
        status: pass
      - kind: integration
        ref: "tests/schema/test_grant_locks.py::TestTheDriverCarriesTheSqlstateTheNarrowingReads::test_a_duplicate_active_grant_carries_sqlstate_23505"
        status: pass
    human_judgment: false
  - id: D6
    description: "WR-04 closed: the registered preflight and both writers raise MultipleEffectiveGrantsError on a second effective grant"
    requirement: "REGGRANT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_claim_precedence_registered.py::TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_a_second_effective_grant_trips_the_wire_rather_than_choosing_between_them"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every race outcome the phase already proved is unchanged: tests/schema/test_claim_race.py passes unedited"
    requirement: "REGGRANT-02"
    verification:
      - kind: integration
        ref: ".venv/bin/python -m pytest -q -m schema tests/schema/test_claim_race.py (30 passed, git diff --stat empty)"
        status: pass
    human_judgment: false

duration: 32min
completed: 2026-09-03
status: complete
---

# Phase 42 Plan 07: CR-01 Gap Closure Summary

**The claim routes now ask the unique indexes' own question before Apple's one-way bit is spent, and the crud writers say which of three things happened, so a refusal is a 403 and only a real race is a 200.**

## Performance

- **Duration:** 32 min
- **Started:** 2026-09-03T22:22Z
- **Completed:** 2026-09-03T22:54Z
- **Tasks:** 3 of 3
- **Files modified:** 11

## Accomplishments

- **CR-01 is closed on both routes.** An account holding a row with `status='active'` whose `ends_at` has passed is refused 403 `operation_not_allowed`, and the DeviceCheck fake records zero reads and zero writes. The one-way bit is never spent on a claim the index will refuse.
- **The two questions are now asked by two reads.** `read_effective_grants` keeps its time window and answers "what is this person entitled to now". `read_active_grants` and `holds_grant_of_source` carry no time window at all and answer "would the index refuse an insert", because a partial index predicate must be IMMUTABLE and `now()` therefore cannot appear in one.
- **The writers name why they refused.** `ActivationOutcome` has three members. A state the preflight tested that changed under the lock is `lost_race`; a state it could not test, or that leaves nothing to read back, is `refused`. The route maps `refused` to a 403 and `lost_race` to the repeat's 200.
- **A broken invariant is no longer reported as success.** Only SQLSTATE `23505` becomes a lost race. A `CHECK` violation is re-raised, proven against real PostgreSQL in both directions.
- **No answer of 200 reports a grant the caller does not hold.** After a lost race the service re-reads in the fresh transaction the rollback opened, and a re-read that finds nothing is a refusal.
- **Nothing the phase already proved moved.** `tests/schema/test_claim_race.py` passes unedited with 30 collected, the migration is byte-identical, and `ErrorCode` still carries exactly 18 members.

## Task Commits

1. **Task 1: Ask the index's own question before the bit is spent — both routes** — `47fb5e9` (fix)
2. **Task 2: The writer says why it refused, so a refusal is a 403 and only a race is a 200** — `9e6cbc9` (fix)
3. **Task 3: The three outcomes and the narrowed catch, measured against real PostgreSQL** — `4961331` (test)

## Files Created/Modified

- `src/nativespeaker/api/crud/grants.py` — the two index-shaped statement builders, `read_active_grants`, `lock_active_grants`, `holds_grant_of_source`, `ActivationOutcome`, `UNIQUE_VIOLATION`, both writers' three-valued mapping, the narrowed catches and the tripwire.
- `src/nativespeaker/api/errors.py` — the fifth and sixth `ClaimRefused` leaves, `ActiveGrantOutsideItsTerm` and `ClaimRefusedUnderLock`. No new `ErrorCode` member and no new status.
- `src/nativespeaker/api/services/auth.py` — both preflights' index questions, the registered preflight's tripwire, and `_settle`, the one place an outcome becomes an answer.
- `tests/e2e/test_claim_registered_grant.py` — CR-01 and WR-02 reproduced end to end, plus the expired-row control.
- `tests/e2e/test_claim_anonymous_grant.py` — CR-01's bit0 half, and the `REFUSED_BODY`, `_grants_of` and `_identity_of` helpers it needed.
- `tests/schema/test_grant_locks.py` — the writer's three outcomes, both violations, the driver's SQLSTATE, and the two updated lock-tier expectations.
- `tests/unit/test_claim_precedence.py` / `..._registered.py` — the outcome-scriptable shared fake, the new recorders, and the five new cases.
- `tests/unit/test_claim_ordering.py` — `lock_active_grants` added to both forbidden-name sets; `enum` added to the import allow-list.
- `tests/unit/test_rejection_vocabulary.py` — the fifth and sixth claim arms, in four coordinated edits each.
- `tests/unit/test_grant_sources.py` — two mention counts moved (see Deviations).

## Measured Before and After — CR-01 on the Registered Route

Measured on the unfixed tree with a throwaway e2e case, then deleted:

```
MEASURED status: 200
MEASURED body: {"entitlement":{"type":"none","status":"none",...},"identity_provider":"google"}
MEASURED read_calls: ['device-token-registered-tracer']
MEASURED write_calls: [('device-token-registered-tracer', False, True)]
MEASURED grants: [(manual, active)]
```

After the fix, the same seeded state: **403**, body `{"code":"operation_not_allowed"}` on the wire, `read_calls == []`, `write_calls == []`, and the seeded row byte-identical including `updated_at`.

## Mutation Testing — Six Mutations, All Reverted

Every mutated path ends at an empty `git diff --stat`. Two mutations found real test weaknesses before they found code weaknesses; both are recorded below rather than quietly fixed.

**A — restore the time window in `_active_grants_statement`** (Task 1, `crud/grants.py`).
Failed, as required:
- `tests/e2e/test_claim_registered_grant.py::TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple::test_a_term_lapsed_active_grant_is_refused_and_no_bit_is_read_or_written`
- `tests/e2e/test_claim_anonymous_grant.py::TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple::test_a_term_lapsed_active_grant_is_refused_and_no_bit_is_read_or_written`

Observed: `AssertionError: {"entitlement":{"type":"none",...}} assert 200 == 403`. The two controls stayed green. Result: **2 failed, 2 passed.**

**B — delete the `holds_grant_of_source` call from the registered preflight** (Task 1, `services/auth.py`).
Failed, as required:
- `tests/e2e/test_claim_registered_grant.py::TestASpentRegisteredSlotRefusesTheConversion::test_a_revoked_registered_grant_refuses_the_conversion_and_leaves_the_anonymous_row`

Observed: `AssertionError: {"entitlement":{"type":"anonymous_device_grant",...}} assert 200 == 403` — WR-02's reported symptom exactly. Result: **1 failed, 3 passed.**

**C — collapse `refused` into `lost_race` in `AuthService._settle`** (Task 2, `services/auth.py`).
**First run: 66 passed — the mutation survived.** The two `refused` cases scripted no readable grant after the rollback, so the backstop raised for them whether the outcome was consulted or not. The cases were strengthened to script a readable grant, which is the state that makes the outcome load-bearing and is also WR-02's real shape. Re-run after strengthening, failed as required:
- `tests/unit/test_claim_precedence.py::TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_a_refused_write_answers_four_hundred_and_three_and_still_consumes`
- `tests/unit/test_claim_precedence_registered.py::TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_a_refused_write_rolls_back_answers_four_hundred_and_three_and_refreshes_nothing`

Observed: `assert 200 == 403`. Result: **2 failed, 64 passed.**

**D — delete the tripwire from the registered preflight** (Task 2, `services/auth.py`).
Failed, as required:
- `tests/unit/test_claim_precedence_registered.py::TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_a_second_effective_grant_trips_the_wire_rather_than_choosing_between_them`

Observed: `assert 200 == 500`. Result: **1 failed, 32 passed.**

**E — widen the narrowed catch back to every `IntegrityError`** (Task 3, `crud/grants.py`).
**First run: 22 passed — the mutation survived**, because it was applied to only two of the three flush boundaries. The conversion's expiry catch sits one indent level deeper and is the one the `CHECK` case exercises. Re-applied to all three, failed as required:
- `tests/schema/test_grant_locks.py::TestTheRegisteredWriterNamesWhyItRefused::test_a_check_violation_is_raised_and_never_read_as_a_lost_race`

Observed: `Failed: DID NOT RAISE <class 'sqlalchemy.exc.IntegrityError'>`. The same run also failed `test_a_spent_registered_slot_is_refused_and_not_lost` for an unrelated reason, which exposed an order-dependent assertion of mine — see Deviations. Result after both were addressed: **1 failed, 21 passed.**

**F — map the term-lapsed branch to `lost_race`** (Task 3, `crud/grants.py`).
Failed, as required:
- `tests/schema/test_grant_locks.py::TestTheRegisteredWriterNamesWhyItRefused::test_a_term_lapsed_active_row_is_refused_and_not_lost`

Observed: `AssertionError: assert <ActivationOutcome.lost_race> is <ActivationOutcome.refused>`. Result: **1 failed, 21 passed.**

## Measured Facts About the Driver

Both measured against real PostgreSQL 17 through the installed `asyncpg` 0.31.0:

- `violation.orig.__cause__` **does** carry a `sqlstate` attribute. A duplicate active grant yields class `UniqueViolationError` with `sqlstate == "23505"`. This is the attribute the narrowing's fail-closed direction rests on, and it is asserted by `TestTheDriverCarriesTheSqlstateTheNarrowingReads`.
- The conversion's expiry `UPDATE` against a row whose `starts_at` equals the writer's instant yields class `CheckViolationError`, `sqlstate == "23514"`, message `new row for relation "access_grants" violates check constraint "access_grants_check"`. That is the violation the widened catch used to report as a lost race.

## Decisions Made

- **The branch order inside `activate_registered_account_grant` is load-bearing, and not the order the plan listed.** `superseded is None and has_prior_free_grant → lost_race` is tested **before** `holds_grant_of_source → refused`. Under READ COMMITTED each statement takes a fresh snapshot, so a conversion race loser that unblocked after the winner committed would see the winner's registered row in `holds_grant_of_source` and be turned into a 403. Testing the conversion-loser branch first shields it. `tests/schema/test_claim_race.py::TestTwoSimultaneousConversionsSupersedeOnce` is the case that would have gone red.
- **The status-only lock is taken first, before `lock_effective_grants`.** The status-only set contains the effective set, so locking it first keeps one grant-tier order ascending by id and leaves the two-tier order the phase proved intact.
- **`ends_at` is named three times in `crud/grants.py`,** all pre-existing: twice in `_effective_grants_statement` and once in the conversion's own expiry write. Neither new statement builder names it.

## Deviations from Plan

### 1. [Rule 1 — Plan defect] The plan's third CR-01 case cannot be seeded

- **Found during:** Task 1
- **Issue:** The plan's `<behavior>` asks for "a linked `google` caller [who] holds an active `anonymous_device_grant` **and** the same lapsed `manual` row". `ix_access_grants_one_active_per_user` is `UNIQUE (user_id) WHERE status = 'active'`, so an account can never hold two active rows. Probed directly against the live database: `UniqueViolationError 23505 duplicate key value violates unique constraint "ix_access_grants_one_active_per_user"`. The plan's own "fails today as" line for that case describes WR-02's symptom, not CR-01's, so the two appear to have been conflated.
- **Fix:** The case was dropped. WR-02's seedable equivalent — a **revoked** registered grant beside an active anonymous grant, which is one active row — is covered instead, at both the route and the writer.
- **Files:** `tests/e2e/test_claim_registered_grant.py`
- **Committed in:** `47fb5e9`

### 2. [Rule 3 — Blocking] `enum` added to the crud module's import allow-list

- **Found during:** Task 2
- **Issue:** The plan puts `ActivationOutcome`, a `StrEnum`, in `crud/grants.py`. That makes `enum` a new import root and `test_claim_ordering.py::test_the_module_imports_only_the_stdlib_the_orm_and_this_project` goes red. The plan's acceptance criterion says the allow-list prints "the same five roots it prints today".
- **Fix:** `enum` was added beside `datetime` and `uuid`, with a comment saying so. The alternative — moving the enum out of `crud/` — would put a crud return type in `tables/` (which AGENTS.md reserves for enums mirroring database types) or in `schemas/`, to satisfy a count.
- **Why this is not the widening the plan forbids:** the prohibition is against admitting `asyncpg` to close WR-01, and that was not done — the SQLSTATE is read off an attribute. `enum` is the standard library, which the guard's own list already admits twice, and it cannot reach a network. `test_importing_the_module_pulls_in_no_http_client`, the guard that actually catches drift, is untouched and still passes.
- **Files:** `tests/unit/test_claim_ordering.py`
- **Committed in:** `9e6cbc9`

### 3. [Rule 3 — Blocking] The recorders the plan assigns to Task 2 had to land in Task 1

- **Found during:** Task 1
- **Issue:** Task 1's preflights call `read_active_grants` and `holds_grant_of_source`. The unit precedence fixtures monkeypatch every crud call, and `_StubSession.exec` raises on any unstubbed query, so Task 1 could not reach a green `pytest -q` without the recorders the plan schedules in Task 2.
- **Fix:** The two recorders landed in Task 1. Task 2 then made the fake's `activate` outcome-scriptable as planned.
- **Files:** `tests/unit/test_claim_precedence.py`, `tests/unit/test_claim_precedence_registered.py`
- **Committed in:** `47fb5e9`

### 4. [Rule 1 — Bug] An order-dependent assertion of my own, found by mutation E

- **Found during:** Task 3
- **Issue:** `_Account.grants()` ordered by `id ASC` and the case compared against a list in seeding order. Grant ids are `uuid4`, so ascending id order is not seeding order and the case would fail on roughly half of all runs.
- **Fix:** `grants()` now returns a sorted list and the expectation is sorted too, with a comment naming the reason.
- **Files:** `tests/schema/test_grant_locks.py`
- **Committed in:** `4961331`

### 5. [Rule 3 — Blocking] Two schema lock-tier cases fixed in Task 2, not Task 3

- **Found during:** Task 2
- **Issue:** Task 2's own `<verify>` requires `pytest -m schema` green, but Task 2's new grant-tier lock read makes five `test_grant_locks.py` cases red. The plan schedules that file for Task 3.
- **Fix:** The minimal expectation moves landed in Task 2 (see the moved-expectations table below) and Task 3 added the new cases on top.
- **Files:** `tests/schema/test_grant_locks.py`
- **Committed in:** `9e6cbc9`

---

**Total deviations:** 5 (1 plan defect, 3 blocking, 1 bug). No guard was weakened or deleted, no schema change, no package installed, and the Apple write was not moved ahead of the database decision.

## Every Changed Expectation, Named

| Node id | Old | New | Why |
|---|---|---|---|
| `test_grant_locks.py::TestTheActivationAddsNoThirdLockTier::test_the_identity_row_is_revalidated_by_a_plain_re_read` | `activated is False` | `outcome is ActivationOutcome.refused` | WR-03: the writer returns an outcome, not a bool. The fixture key was renamed `activated` → `outcome` for the same reason. |
| `test_grant_locks.py` `assert_one_plain_identity_re_read` | `activated is True` | `outcome is ActivationOutcome.activated` | Same. |
| `test_grant_locks.py::TestTheRegisteredWriterAddsNoThirdLockTier::test_the_conversion_locks_the_grant_rows_then_their_usage_rows` | 2 locking statements | 3, with `core.access_grants` twice then `core.user_monthly_usage` | CR-01: the writer takes the status-only lock read first. The asserted property — grant tier before usage tier, ordered by id, never a third relation — is unchanged. |
| `test_grant_locks.py::TestTheRegisteredWriterAddsNoThirdLockTier::test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row` | `["core.access_grants"]` | `["core.access_grants", "core.access_grants"]` | Same, on the arm that holds no row. |
| `test_grant_sources.py::TestTheAnonymousDeviceGrantHasExactlyOneWriter::test_the_one_site_is_inside_the_crud_activation_writer` | member named 1× in the writer | 2× | WR-03: the writer's new in-lock repeat test names `anonymous_device_grant`. `test_the_whole_tree_holds_exactly_one_construction_site` — the case that actually pins one writer — is untouched and still passes. |
| `test_grant_sources.py::TestTheRegisteredAccountGrantHasExactlyOneWriter::test_the_one_site_is_inside_the_crud_activation_writer` | 2× | 3× | WR-02: the writer's `holds_grant_of_source` call names `registered_account_grant`. Same control untouched. |
| `test_rejection_vocabulary.py::TestTheFourClaimArms...` | four arms | six arms, class and case names renamed | Two new `ClaimRefused` leaves; four coordinated edits per arm as the fourth arm needed. |
| `test_claim_precedence*.py` race-loser cases | `activation_wins = False` | `outcome = lost_race` with the winner's row scripted | The name now says the state the case always described, and the loser's re-read needs a winner's row to find. |

No case was softened to keep a count. The suites grew: unit 1001 → 1016, schema 147 → 154, e2e 237 → 241.

## Issues Encountered

- **`git checkout --` destroyed uncommitted work once.** Reverting mutation A with `git checkout -- src/nativespeaker/api/crud/grants.py` reset the file to HEAD, which at that point still predated Task 1. The Task 1 crud edits were reapplied by hand and re-verified. Every later mutation was reverted from a `cp` backup taken immediately before it. The revert itself was clean each time; `git diff --stat` on every mutated path is empty.
- **The plan's Task 2 mutation "map `refused` to `lost_race` in the registered writer" is not observable from Task 2's own cases**, because those cases mock the writer out. It was run at the service seam instead (mutation C) and at the writer against real PostgreSQL in Task 3 (mutation F). Both directions are recorded.

## Known Stubs

None. No hardcoded empty value, placeholder string or unwired component was introduced.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or schema change at a trust boundary. The migration is byte-identical and `ErrorCode` still carries 18 members, so the refusal surface gained no oracle.

## Final Suite Counts

| Suite | Pre-plan | Final | Command |
|---|---|---|---|
| unit | 1001 | **1016** | `.venv/bin/python -m pytest -q` |
| schema | 147 | **154** | `.venv/bin/python -m pytest -q -m schema` |
| e2e | 237 | **241** | `.venv/bin/python -m pytest -q -m e2e` |
| lint | clean | **clean** | `.venv/bin/ruff check src tests` |

`tests/schema/test_claim_race.py` — 30 passed, `git diff --stat` empty.
`migrations/20260818_01_initial-release.sql` — `git diff --stat` empty.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Phase 43's `POST /webhooks/app-store` is the first writer that will create `subscription` grants with a term `ends_at`, which is the state that makes CR-01 reachable through the API. That state is now refused with a 403 instead of costing the caller an irreversible DeviceCheck bit.

One thing stays open and is Phase 43's to own: **nothing in this system moves `status` to `expired` when `ends_at` elapses** (T-42-07-09, accepted). An account holding such a row is refused rather than half-served, and repair remains an operator action. A background healer is forbidden by `SHARED-INVARIANTS.md`; the subscription writer must expire before it activates, as `migrations/20260818_01_initial-release.sql:255` already says.

Left open by this plan and named in its objective: WR-05 (the untested `free_grant_consumed_at` branch), WR-06 (D-02's understated consequence table), WR-07 (the byte-identical `device_grant_exhausted` diagnostics) and IN-01 … IN-05. None shares CR-01's root cause and none is a wrong answer to a caller.

---
*Phase: 42-post-auth-claim-registered-grant*
*Completed: 2026-09-03*
