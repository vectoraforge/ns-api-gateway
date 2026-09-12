---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 05
subsystem: api
tags: [postgres, sqlalchemy, sqlmodel, fastapi, pytest, subscriptions, restore, entitlements]

requires:
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-01: one clock read per method, and the pattern for relocating a boundary onto a pure helper"
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-04: both store adapters take no datetime, so the restore path below them is free to stop threading one"
provides:
  - The seven SubscriptionsDB writers take no datetime and read the clock once each
  - services/restore.py::_open_term(candidates, instant) is a module-level pure helper
  - RestoreService and SubscriptionsService hold no datetime
  - get_restore_service and get_subscriptions_service declare no datetime dependency
  - tests/unit/test_open_term.py pins the term boundary the e2e suite could no longer reach
  - No test in this repository overrides get_evaluated_at
affects: [47-06, 47-07, 49, 50]

actuals:
  tokens: 18068
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "One clock read per crud writer method, as its first statement, stamping every column of that write"
    - "A value the writer stamped is asserted by a bracket between two clock reads around the call"
    - "A value the notification itself carries keeps exact equality; only the writer's own stamps move"
    - "A stored monthly period is asserted by membership in the two months the bracket spans"

key-files:
  created:
    - tests/unit/test_open_term.py
  modified:
    - src/nativespeaker/api/crud/subscriptions.py
    - src/nativespeaker/api/services/restore.py
    - src/nativespeaker/api/services/subscriptions.py
    - src/nativespeaker/api/app/dependencies.py
    - tests/unit/test_subscription_store_clock.py
    - tests/unit/test_subscription_grant_write.py
    - tests/unit/test_subscription_attribution.py
    - tests/unit/test_restore_proof.py
    - tests/schema/test_subscription_ingestion.py
    - tests/schema/test_restore_race.py
    - tests/schema/test_subscription_race.py
    - tests/schema/test_grant_locks.py
    - tests/e2e/test_restore_subscription.py

key-decisions:
  - "The e2e boundary case was deleted and its property relocated onto _open_term in the same commit. Nothing was dropped: the equality it pinned is now one of seven cases in a new unit module."
  - "Five test modules had to date their terms from the live clock. Their fixed NOW was in the past, so a service reading its own clock refused every term built around it."
  - "Test-local instants that are now only the test's own value were renamed: the ingestion buyer's field to instant, the grant-locks fixture local to instant."
  - "Two of the plan's acceptance criteria count wrong and were recorded rather than forced: one counts lines where it means occurrences, and one names one remaining services file where two remain."
  - "The plan says uv run pytest. The project rule is .venv/bin/pytest with the schema and e2e markers, which is what was run; without the marker both suites are silently deselected."

patterns-established:
  - "Pattern 1: a bracket reads before and after around the call under test and asserts before <= value <= after, marked @pytest.mark.timing"
  - "Pattern 2: a term a test needs open is dated from datetime.now(UTC), because a fixed literal rots once the code under it reads a live clock"

requirements-completed: []

coverage:
  - id: D1
    description: "The seven SubscriptionsDB writers take no datetime and read the clock exactly once each"
    verification:
      - kind: unit
        ref: "tests/unit/test_subscription_store_clock.py, tests/unit/test_subscription_grant_write.py (the whole files)"
        status: pass
      - kind: other
        ref: "grep -c 'datetime.now(UTC)' src/nativespeaker/api/crud/subscriptions.py == 7 and grep -c evaluated_at == 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "clock_read keeps its name, its type and its is_not_distinct_from comparison"
    verification:
      - kind: unit
        ref: "tests/unit/test_subscription_store_clock.py#TestTheCanonicalRowIsTakenOnTheClockItWasReadAt (5 cases)"
        status: pass
      - kind: other
        ref: "grep -c clock_read src/nativespeaker/api/crud/subscriptions.py == 6, unchanged from before the edit"
        status: pass
    human_judgment: false
  - id: D3
    description: "_open_term returns the first candidate strictly after the instant; a term ending at the instant is not open"
    verification:
      - kind: unit
        ref: "tests/unit/test_open_term.py#TestATermEndingAtTheInstantIsNotOpen (3 cases), #TestTheFirstOpenCandidateIsTheAnswer (5 cases)"
        status: pass
      - kind: other
        ref: "grep -c 'def _open_term' src/nativespeaker/api/services/restore.py == 1; grep -rc _open_term src/nativespeaker/api/auth/ == 0 for every file"
        status: pass
    human_judgment: false
  - id: D4
    description: "RestoreService holds no datetime, restore() reads once, and the four refusals answer as before"
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py (95 passed with test_open_term.py)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py (35 passed, 1 pre-existing failure that is not this plan's)"
        status: pass
      - kind: other
        ref: "grep -c 'datetime.now(UTC)' src/nativespeaker/api/services/restore.py == 1 and grep -c evaluated_at == 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "The repository's only get_evaluated_at dependency override is deleted"
    verification:
      - kind: other
        ref: "grep -rl get_evaluated_at tests/e2e/ | wc -l == 0"
        status: pass
      - kind: e2e
        ref: "tests/e2e (360 passed, 1 pre-existing failure); no fixture error names pinned_evaluation_instant"
        status: pass
    human_judgment: false
  - id: D6
    description: "SubscriptionsService holds no datetime and ingest() reads once for the clamp and the term guard"
    verification:
      - kind: integration
        ref: ".venv/bin/pytest tests/schema -m schema (291 passed, the measured baseline)"
        status: pass
      - kind: other
        ref: "grep -c 'datetime.now(UTC)' src/nativespeaker/api/services/subscriptions.py == 1 and grep -c evaluated_at == 0"
        status: pass
    human_judgment: false
  - id: D7
    description: "The ingestion schema suite brackets what the writer stamps and passes twice in a row"
    verification:
      - kind: integration
        ref: ".venv/bin/pytest tests/schema/test_subscription_ingestion.py -m schema, run twice (27 passed, 27 passed)"
        status: pass
      - kind: other
        ref: "grep -c 'pytest.mark.timing' == 4 and grep -c strftime == 0 in tests/schema/test_subscription_ingestion.py"
        status: pass
    human_judgment: false
  - id: D8
    description: "tests/unit/test_auth_package_shape.py passes with its recorded tuple unedited"
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_package_shape.py (2 passed)"
        status: pass
      - kind: other
        ref: "git diff --stat tests/unit/test_auth_package_shape.py is empty"
        status: pass
    human_judgment: false

duration: 24 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 05: The subscription write path carries no instant Summary

**The seven `SubscriptionsDB` writers each read `datetime.now(UTC)` once, `RestoreService` and `SubscriptionsService` hold no datetime, the restore term check is the pure helper `_open_term(candidates, instant)`, and the repository's only `get_evaluated_at` override is gone.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-09-12T06:47:00Z
- **Completed:** 2026-09-12T07:11:00Z
- **Tasks:** 3
- **Files created/modified:** 14

## Accomplishments

- `insert_subscription`, `upsert_subscription`, `claim_subscription_owner`,
  `hold_subscription_clock`, `insert_purchase`, `append_event` and `write_subscription_grant`
  take no datetime. Each reads `instant` as its first statement.
  `grep -c 'datetime.now(UTC)'` over `crud/subscriptions.py` prints `7` — one per writer,
  not one per assignment.
- `clock_read` is untouched. Its name, its `datetime | None` type and its
  `is_not_distinct_from` comparison are byte-identical, and its grep count is `6` before and
  after. The store's own clock and a current-time read were never confused.
- `_open_term(candidates, instant)` sits in `services/restore.py`, above the class, and
  **not** under `auth/`. `tests/unit/test_auth_package_shape.py` is untouched and passes, so
  Phase 49 still sees the tuple it planned against.
- The boundary was relocated, not dropped. `tests/unit/test_open_term.py` carries eight cases:
  one microsecond before the instant is closed, the **equality is closed**, one microsecond
  after is open, plus the first-open-wins rule, a missing candidate, a closed candidate, an
  all-`None` sequence and an empty sequence.
- `tests/e2e/test_restore_subscription.py` overrides no dependency to supply a datetime.
  The `pinned_evaluation_instant` fixture, its `dependency_overrides[get_evaluated_at]` line
  and the one case that consumed it are gone, and the control beside it is kept and green.
  `grep -rl 'get_evaluated_at' tests/e2e/ | wc -l` prints `0`, which is roadmap criterion 1.
- `restore()` and `ingest()` each read the clock once and hand that one value to everything
  below. `app/dependencies.py` is down to three `get_evaluated_at` occurrences: the definition
  plus `get_auth_service` (47-06) and `get_sync_service` (47-07).
- Suites: **1936 unit / 360 e2e / 291 schema**, `ruff check src tests` clean, `ty check`
  **314** diagnostics against the **314** baseline this plan started from.

## Task Commits

1. **Task 1 RED: drive the subscription writers with no datetime** - `5d921db` (test)
2. **Task 1 GREEN: the seven subscription writers read their own instant** - `ccb10ed` (feat)
3. **Task 2 RED: carry the restore term boundary onto a pure helper** - `ebaa566` (test)
4. **Task 2 GREEN: restore reads once and the term check is a pure helper** - `d7c84f2` (feat)
5. **Task 3: ingestion reads once and the schema suite brackets the stamps** - `32291d6` (feat)

## Files Created/Modified

- `tests/unit/test_open_term.py` - **new**; the relocated term boundary and the ordinary cases
- `src/nativespeaker/api/crud/subscriptions.py` - seven writers, one read each
- `src/nativespeaker/api/services/restore.py` - `_open_term`, one read in `restore()`, `_this_month(instant)`
- `src/nativespeaker/api/services/subscriptions.py` - one read in `ingest()`, no field
- `src/nativespeaker/api/app/dependencies.py` - both service factories declare no datetime
- `tests/unit/test_subscription_store_clock.py` - three writer calls lost the keyword
- `tests/unit/test_subscription_grant_write.py` - the writer call, one bracket, two period constants
- `tests/unit/test_subscription_attribution.py` - the service construction, one bracket, live terms
- `tests/unit/test_restore_proof.py` - the service construction, `OPEN_TERM`, two brackets
- `tests/schema/test_subscription_ingestion.py` - the buyer field renamed, four brackets, the period by membership
- `tests/schema/test_restore_race.py` - one writer call, one bracket, live `NOW` and `THIS_MONTH`
- `tests/schema/test_subscription_race.py` - the service construction and live `NOW`
- `tests/schema/test_grant_locks.py` - both service constructions and one renamed local
- `tests/e2e/test_restore_subscription.py` - the fixture, its override, its case and its import

## Decisions Made

**The term boundary moved onto the helper in the same commit that deleted it.** The e2e case
asserted that a term ending at the exact instant the request captured is over. A live clock
never lands on that equality, so the case could not survive at the route level. `_open_term`
lifts the comparison out verbatim — `end is not None and end > instant` — and a parametrized
class pins the equality with one microsecond on each side. The deletion and the replacement
are in `ebaa566`, one commit, so no revision of this repository is without the property.

**`_open_term` lives in `services/restore.py`.** RESEARCH Open Question 5 disposed of this and
it held: `tests/unit/test_auth_package_shape.py` counts files, classes and functions under
`auth/`, and Phase 49 rewrites that ratchet. A helper added there would have forced this phase
to edit a tuple it does not own. The file's diff is empty.

**Five test modules now date their terms from the live clock.** This is the largest single
change and it was not optional. `tests/unit/test_subscription_attribution.py` pinned
`NOW = 2026-09-04`, `tests/schema/test_restore_race.py` and `tests/schema/test_subscription_race.py`
pinned `2026-08-23`, and `tests/unit/test_restore_proof.py` built every proof term from
`EVALUATED_AT = 2026-06-01`. Each is in the past. Once the service reads its own clock, a term
built as `NOW + 30 days` is already over and the service refuses it — 17 cases in
`test_restore_proof.py` alone raised `RestoreSubscriptionNotEntitled`. Each module now derives
its open term from `datetime.now(UTC)`: `OPEN_TERM` in the restore proof suite, a live `NOW` in
the other three. No assertion was weakened. The term moved, not the expectation.

**Fixed literals were kept wherever they stay on their side of the comparison.**
`LAST_MONTH` in `tests/unit/test_subscription_grant_write.py` is now `"2000-01"` rather than
`"2026-08"`: a month that is forever in the past proves the carried-count rule without reading
a clock. `THIS_MONTH` in the same file is `monthly_period_for(datetime.now(UTC))`, because the
period the writer writes is this month and a literal for it rots. This is the split plan 47-01
established.

**Group A and Group B were split exactly as the plan asked, and the split is load-bearing.**
In `tests/schema/test_subscription_ingestion.py` a `starts_at` equal to the buyer's instant
minus one month, and every `ends_at` equal to a term the notification carries, come from
`notification.purchased_at` and `term_end_for`. Those keep exact equality and would catch a
writer that started stamping them itself. Only the four values the writer stamps from its own
read became brackets.

**The stored monthly period is asserted by membership, not by a second derivation.**
`usage["monthly_period"] in {monthly_period_for(before), monthly_period_for(after)}`, with
`monthly_period_for` imported from `nativespeaker.api.tables`. `grep -c strftime` over that
file prints `0`, so `tests/unit/test_monthly_period.py`'s single-derivation ratchet is intact.

**Three test-local names were corrected.** The ingestion buyer's `evaluated_at` field is now
`instant`, because it is the test's own value and is never handed to production code. The
`test_grant_locks.py` fixture local of the same name is now `instant` for the same reason.
Two docstrings and two case names that stated "the captured instant" now state what the code
actually compares.

**The multiple-read window inside one upsert was accepted, not closed.** `upsert_subscription`
calls `claim_subscription_owner` and `hold_subscription_clock`, so one upsert reads the clock
up to three times, microseconds apart, all writing `updated_at`. The last write wins, as it
does today. No parameter was added to pass an instant between them under another name.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 also changed two test files the plan gave to later tasks**
- **Found during:** Task 1
- **Issue:** `tests/unit/test_restore_proof.py:1196` calls `insert_subscription` directly, and
  `tests/unit/test_subscription_attribution.py` forwards `**fields` to the real
  `upsert_subscription` and reads `fields["evaluated_at"]` off a recorded `insert_purchase`.
  Task 1's own `<verify>` is `pytest -q` over the whole unit suite, which cannot pass while a
  caller still sends an argument the writer no longer takes.
- **Fix:** Both dropped the keyword in Task 1's GREEN commit. The recording fake's stand-in
  purchase row now dates itself with `datetime.now(UTC)`, which is what the real writer does.
- **Files modified:** `tests/unit/test_restore_proof.py`, `tests/unit/test_subscription_attribution.py`
- **Verification:** 1928 unit passed at Task 1's GREEN, which is the measured baseline exactly
- **Committed in:** `ccb10ed`

**2. [Rule 1 - Bug] A schema case compared a superseded term against the harness's fixed instant**
- **Found during:** Task 1
- **Issue:** `tests/schema/test_restore_race.py::TestTheDestinationStillLosesEverythingItHeld`
  asserted `ended[0][2] == NOW`. That value is the writer's own stamp, so it can never equal a
  constant again. The plan's rule for this shape is a bracket; the plan did not name this case.
- **Fix:** The fixture reads `before` and `after` around the move it drives and returns them;
  the case asserts `before <= ends_at <= after` and carries `@pytest.mark.timing`.
- **Files modified:** `tests/schema/test_restore_race.py`
- **Verification:** 34 cases in the file pass; 59 passed across both race files
- **Committed in:** `ccb10ed`

**3. [Rule 1 - Bug] Five modules asserted terms a live clock can no longer read as open**
- **Found during:** Tasks 2 and 3
- **Issue:** Detailed under Decisions. 17 cases in `tests/unit/test_restore_proof.py`, three in
  `tests/schema/test_restore_race.py` and the whole open-term half of
  `tests/unit/test_subscription_attribution.py` were refused, because their terms were built
  from constants three months in the past.
- **Fix:** Each module derives its open term from the live clock. `OPEN_TERM`,
  `GRACE_WINDOW_ENDS`, and a live `NOW` in three files. `THIS_MONTH` in
  `tests/schema/test_restore_race.py` is derived from `NOW` rather than spelled as a literal,
  because it is now the month the service's own read lands in.
- **Files modified:** `tests/unit/test_restore_proof.py`, `tests/unit/test_subscription_attribution.py`,
  `tests/schema/test_restore_race.py`, `tests/schema/test_subscription_race.py`
- **Verification:** 1936 unit passed, 291 schema passed, 360 e2e passed
- **Committed in:** `d7c84f2` and `32291d6`

**4. [Rule 3 - Blocking] Two service constructions the plan does not list broke on the narrowed constructors**
- **Found during:** Tasks 2 and 3
- **Issue:** `tests/schema/test_grant_locks.py` constructs both `RestoreService` and
  `SubscriptionsService`, and `tests/schema/test_subscription_race.py` constructs
  `SubscriptionsService`. The plan named the first pair but expected the third to be Task 1's
  concern, where it was explicitly left alone.
- **Fix:** All three dropped the keyword in the commit that narrowed the constructor.
- **Files modified:** `tests/schema/test_grant_locks.py`, `tests/schema/test_subscription_race.py`
- **Verification:** 291 schema passed, the measured baseline
- **Committed in:** `d7c84f2` and `32291d6`

---

**Total deviations:** 4 auto-fixed (2 blocking, 2 bugs).
**Impact on plan:** No scope creep. Two deviations are call sites that name a signature this
plan changes, pulled into the commit that changes it so every suite is green at every commit.
Two are assertions that state a fact the plan deletes, corrected where the fact dies. The
plan's task boundaries moved; its content did not.

## Issues Encountered

**Two acceptance criteria count wrong and were recorded rather than forced.**

- Task 1: "`grep -c 'evaluated_at' src/nativespeaker/api/services/subscriptions.py` prints `5`".
  `grep -c` counts **lines**, and the identifier sits on four lines as six occurrences. Neither
  number is `5`. The criterion's intent — the field survives Task 1 for Task 3 — was met and is
  proved by the file being unchanged apart from its five writer call sites.
- Task 3: "`grep -rc 'evaluated_at' src/nativespeaker/api/services/ | grep -v ':0' | wc -l` is
  `1`, only `services/auth.py` may carry it". It is `2`: `services/auth.py` (plan 47-06) and
  `services/sync.py` (plan 47-07). `services/sync.py` was never this plan's, and plan 47-01's
  summary already records it as 47-07's work. The criterion undercounts by one file.

**One pre-existing e2e failure, out of scope and not fixed.**
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`
expects the log event `proof_rejected` while the code emits `purchase_proof_rejected`. Plans
47-01, 47-03 and 47-04 measured it at HEAD before this phase started and recorded it in
`deferred-items.md` and `.planning/WINDOWS.md`. The restore e2e file is 35 passed / 1 failed —
35 and not 36 because this plan deleted one case by design — and the whole e2e suite is 360
passed / 1 failed. Task 2's criterion "`pytest -m e2e tests/e2e/test_restore_subscription.py`
exits 0" is unreachable while that failure stands, exactly as plan 47-04 recorded.

**The suites are more clock-dependent than they were, and that is now a phase-wide fact.**
Nine modules in this phase derive a term or a period from the wall clock at import or at call.
None can straddle its own boundary in an ordinary run — every open term is ten to thirty days
out — but two assertions in this plan's files compare a stored monthly period against the
month a bracket spans. Those use membership over both months, so a run crossing a UTC month
boundary answers correctly rather than failing for the wrong reason.

## Known Stubs

None. No hardcoded empty value, placeholder string or unwired component was written.

## Threat Flags

None.

- **T-47-14 (the restore term-open check) held.** The comparison was lifted verbatim into
  `_open_term` — `end > instant`, never `>=` — and three parametrized cases pin the equality
  and both one-microsecond sides. The e2e case was deleted in the same commit its replacement
  landed in, never before.
- **T-47-15 (`hold_subscription_clock`'s `clock_read`) held.** The parameter's name, type and
  `is_not_distinct_from` comparison are unchanged and its grep count is `6` before and after.
  Five cases in `tests/unit/test_subscription_store_clock.py` drive the conditional take.
- **T-47-16 (the one-move-per-UTC-month rule) held.** `_this_month` keeps its derivation and
  only changed where its datetime comes from. `tests/schema/test_restore_race.py` runs the two
  transfer-month cases and both pass.
- **T-47-05 (multiple reads inside one upsert) was accepted in the plan** and no machinery was
  built to prevent it.
- **T-47-SC:** no package was installed and no manifest was touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The subscription write path is done. No `crud/subscriptions.py` writer, `RestoreService` or
  `SubscriptionsService` holds or receives a datetime, which is roadmap criterion 2 for this
  path.
- Roadmap criterion 1 is met in full: no test in this repository overrides a dependency to
  supply a datetime. `tests/unit/test_sync_clock_capture.py` still names `get_evaluated_at` in
  a parametrized row, but it overrides nothing; plan 47-07 deletes the file.
- `app/dependencies.py` carries three `get_evaluated_at` occurrences — the definition,
  `get_auth_service` and `get_sync_service`. Plan 47-06 and plan 47-07 own those two and can
  both start. Nothing else in that file was touched, so Phase 50 sees the shape it planned
  against.
- `tests/unit/test_auth_package_shape.py` is byte-identical, so Phase 49's ratchet rewrite is
  unaffected.
- One thing to carry forward: `tests/schema/test_restore_race.py` and
  `tests/schema/test_subscription_race.py` now read the wall clock at module import. Their
  terms are a month out, so no ordinary run straddles one, but a very long-lived collected
  session would.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*

## Self-Check: PASSED

`tests/unit/test_open_term.py` exists on disk, every file named in `key-files.modified` exists,
and all five task commits of this plan are reachable in `git log`.
