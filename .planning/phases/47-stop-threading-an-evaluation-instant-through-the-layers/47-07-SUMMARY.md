---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 07
subsystem: api
tags: [fastapi, sqlmodel, pytest, sync, entitlements, dependencies]

requires:
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-01: the effective-grant predicate takes no datetime, so the sync grant read needs none"
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-05: no test overrides the dependency, and the period-constant pattern for a live clock"
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-06: get_auth_service declares no datetime, leaving get_sync_service as the last caller"
provides:
  - SyncService takes db alone and read_entitlement reads the clock once
  - get_evaluated_at is deleted, with its docstring, from app/dependencies.py
  - get_sync_service declares no datetime and app/dependencies.py imports none
  - tests/unit/test_sync_clock_capture.py is deleted
  - tests/unit/test_instant_is_not_threaded.py makes roadmap criteria 1, 2 and 4 executable
affects: [48, 49, 50]

actuals:
  tokens: 6402
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "An absence guard is a plain text walk over rglob('*.py'), never an AST walk"
    - "An absence guard excludes its own path from every walk, because it carries the strings it forbids"
    - "An absence guard carries a positive control, a matcher control and a near-miss control"

key-files:
  created:
    - tests/unit/test_instant_is_not_threaded.py
  modified:
    - src/nativespeaker/api/services/sync.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/tables/grants.py
    - tests/unit/test_sync_resolver.py
    - tests/schema/test_sync_lock_freedom.py
    - tests/schema/test_claim_race.py

key-decisions:
  - "get_evaluated_at is deleted. SyncService was its last reader, so roadmap criterion 1 is met in full."
  - "tests/unit/test_sync_clock_capture.py was deleted in Task 1, not Task 2. Five of its cases assert the discipline Task 1 inverts, and Task 1's verify is the whole unit suite."
  - "The ahead-period case uses AHEAD_PERIOD, not the plan's past month literal. A past literal would invert the case's own property and duplicate the stale case beside it."
  - "The guard excludes its own path from every walk, so the plan's grep-based verification command 4 reports 1 rather than 0. Excluding the guard it reports 0."
  - "The guard carries four controls, not the plan's three. The fourth proves the scope exclusion rather than stating it in prose only."

patterns-established:
  - "Pattern 1: a criterion the roadmap states in prose becomes one guard module with its controls, not a claim in a summary"
  - "Pattern 2: a mutation check is run on the guard and both outcomes are recorded, so the guard is known to fail on a reintroduction"

requirements-completed: []

coverage:
  - id: D1
    description: "SyncService takes db alone, holds no datetime and reads the clock once in read_entitlement"
    verification:
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestTheServiceKeepsNoSessionHandle::test_the_service_holds_only_the_reads"
        status: pass
      - kind: other
        ref: "grep -c 'evaluated_at' src/nativespeaker/api/services/sync.py == 0; grep -c 'datetime.now(UTC)' == 1"
        status: pass
    human_judgment: false
  - id: D2
    description: "get_evaluated_at is deleted and no Depends in dependencies.py or any router supplies a datetime"
    verification:
      - kind: unit
        ref: "tests/unit/test_instant_is_not_threaded.py#TestTheDependencyIsGone::test_no_file_names_the_dependency"
        status: pass
      - kind: other
        ref: "grep -rn 'datetime' src/nativespeaker/api/app/dependencies.py src/nativespeaker/api/routers/ prints nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "/auth/sync answers exactly as before, including the two fail-closed raises"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_sync.py (14 passed)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sync_resolver.py#TestTheUsageRowIsMissing, #TestTheTierHasNoRow (6 cases)"
        status: pass
      - kind: integration
        ref: ".venv/bin/pytest tests/schema/test_sync_lock_freedom.py tests/schema/test_claim_race.py -m schema (33 passed)"
        status: pass
    human_judgment: false
  - id: D4
    description: "No comment or docstring in src/ or tests/ names the removed dependency or the shared instant"
    verification:
      - kind: unit
        ref: "tests/unit/test_instant_is_not_threaded.py#TestNoProseNamesTheRemovedSubject::test_no_file_carries_a_banned_spelling"
        status: pass
      - kind: other
        ref: "grep -rniE 'captured instant|shared instant|one instant|evaluation time' src/ | wc -l == 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "The tables/grants.py timestamp comment is cut to one sentence and the crud/grants.py IMMUTABLE-index comment survives"
    verification:
      - kind: other
        ref: "grep -c 'The creating transaction owns the clock' tables/grants.py == 0; grep -c 'a partial index predicate must be IMMUTABLE' crud/grants.py == 1"
        status: pass
    human_judgment: false
  - id: D6
    description: "tests/unit/test_sync_clock_capture.py is deleted and one guard module replaces it"
    verification:
      - kind: other
        ref: "ls tests/unit/test_sync_clock_capture.py exits 2; the unit suite fell by exactly its 21 cases"
        status: pass
      - kind: unit
        ref: "tests/unit/test_instant_is_not_threaded.py (7 passed)"
        status: pass
    human_judgment: false
  - id: D7
    description: "The guard is not vacuous: it reads real files, its matcher matches, and it ignores a near miss and the three helpers that keep the parameter name"
    verification:
      - kind: unit
        ref: "tests/unit/test_instant_is_not_threaded.py#TestTheWalkIsNotVacuous (4 cases)"
        status: pass
      - kind: other
        ref: "the mutation check: a 'captured instant' line appended to services/sync.py made the criterion-4 case fail naming the file and the spelling; reverting it made it pass"
        status: pass
    human_judgment: false

duration: 21 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 07: The dependency is deleted and one guard keeps it gone Summary

**`SyncService` takes `db` alone and reads `datetime.now(UTC)` once, `get_evaluated_at` is deleted
with its docstring, and `tests/unit/test_instant_is_not_threaded.py` makes roadmap criteria 1, 2 and
4 executable with four controls.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-09-12T07:31:00Z
- **Completed:** 2026-09-12T07:52:00Z
- **Tasks:** 3
- **Files created/modified/deleted:** 1 created, 6 modified, 1 deleted

## Accomplishments

- `SyncService.__init__` takes `db` alone and sets `self.grants_db` only.
  `read_entitlement` reads `instant = datetime.now(UTC)` as its first statement and that one
  value derives the period. The grant read takes no datetime, as plan 47-01 left it.
- `get_evaluated_at` is **deleted**, with its docstring. `get_sync_service` now reads like
  `get_quota_service` above it, and `app/dependencies.py` imports no `datetime` at all.
  `verify_google_play_notification` was checked first: it holds `signed_at` through
  `instant_from_millis`, which needs no `datetime` name.
- Nothing else in `app/dependencies.py` moved. `get_session_factory`, `get_firebase_adapter`,
  `get_devicecheck_adapter` and `get_challenge_store` grep to `8` before and after, so Phase 49
  and Phase 50 see the shape they planned against.
- Roadmap criterion 1 is met in full: no `Depends(...)` in `app/dependencies.py` and no parameter
  in any router supplies a datetime. `grep -rn 'datetime'` over both prints nothing.
- Roadmap criterion 2 is met in full: no file under `app`, `crud`, `routers` or `services`
  contains `evaluated_at`.
- Roadmap criterion 4 is met in full. Every row of RESEARCH Finding 5 was walked top to bottom;
  plans 47-01 through 47-06 had already closed all but two, and Task 1 and Task 2 closed those.
  `tables/grants.py`'s comment is one sentence, `# The timestamps carry no default.`
- The protected comment survives. `crud/grants.py`'s note that a partial index predicate must be
  IMMUTABLE greps to `1`, and the guard does not touch it: its subject is the index.
- `tests/unit/test_sync_clock_capture.py` is deleted with its `_clock_reads` and `_clock_aliases`
  walkers. One guard module replaces it, and the guard fails on a reintroduction.
- Suites: **1921 unit / 291 schema / 360 e2e**, `ruff check src tests` clean, `ty check` **311**
  diagnostics against a **313** baseline measured from a clean export of `d314899`.

## Task Commits

1. **Task 1 RED: drive the sync service with no datetime** - `7cdeefd` (test)
2. **Task 1 GREEN: sync reads its own instant and the dependency is deleted** - `d985a8e` (feat)
3. **Task 2: the table comment is cut to the sentence that stays true** - `53a14c6` (docs)
4. **Task 3: one absence guard for criteria 1, 2 and 4** - `863accb` (test)

## Files Created/Modified

- `tests/unit/test_instant_is_not_threaded.py` - **new**; three properties and four controls
- `tests/unit/test_sync_clock_capture.py` - **deleted**; 21 cases, 163 lines
- `src/nativespeaker/api/services/sync.py` - the constructor, one clock read, two docstrings, one comment
- `src/nativespeaker/api/app/dependencies.py` - `get_evaluated_at` deleted, `get_sync_service` narrowed, the import dropped
- `src/nativespeaker/api/tables/grants.py` - the timestamp comment cut to its first sentence
- `tests/unit/test_sync_resolver.py` - the period constants, the `_read` helper, three cases, the shape assertion
- `tests/schema/test_sync_lock_freedom.py` - the harness field, its seed and both call sites
- `tests/schema/test_claim_race.py` - one call site

## Decisions Made

**The clock-capture module was deleted in Task 1, not Task 2.** Five of its cases assert the
discipline Task 1 inverts: `TestSyncServiceReadsNoClock` asserts `services/sync.py` makes no clock
call, and two more assert `get_evaluated_at` exists and that `get_sync_service` declares it. Task
1's own `<verify>` is `pytest -q` over the whole unit suite, which cannot pass while the file
stands. The file is dead the moment the source changes, so it goes in the commit that changes it.
The file was read in full before deleting, as Task 2 required, and its vacuity-control shape is
what Task 3's guard carries forward.

**The ahead-period case uses `AHEAD_PERIOD`, not a past month literal.** The plan's action said to
set the stub's `monthly_period` to a past month literal. That case's property is WR-47 — *a stored
period ahead of this month keeps its own count* — and a past literal takes the other branch,
asserting zero used. It would have duplicated `test_a_stale_period_reports_zero_for_the_current_period`
three lines above it and silently deleted the ahead-branch property. The constants now follow
`tests/unit/test_quota_resolver.py` exactly: `PERIOD = monthly_period_for(datetime.now(UTC))`,
`STALE_PERIOD = "2000-01"`, `AHEAD_PERIOD = "9999-12"`. Both branches are covered and no case
reads a clock to name a past or a future month.

**`EVALUATED_AT` in the sync resolver suite is now `SEEDED_AT`.** It is only the date the in-memory
`AccessGrant` rows carry; the stub session never compares it. This is the rename plans 47-03,
47-05 and 47-06 each made.

**The guard is a plain text walk, and it excludes its own path.** The deleted module's AST walkers
had no other caller. A text walk is enough for an absence guard and is cheaper, which is what
`47-PATTERNS.md` Cluster 9 prescribes. `_sources` skips `Path(__file__).resolve()`, because the
module carries `BANNED_SPELLINGS` and a synthetic positive control and would otherwise fail on
itself rather than on a defect.

**The guard carries four controls, not three.** The plan mandated three: the walk reads real files,
the matcher matches, the near miss is not reported. The fourth asserts the scope exclusion instead
of only stating it — it reads `auth/app_store.py`, `auth/google_play.py` and `tables/grants.py`,
confirms all three genuinely carry the parameter name, and asserts the four-package walk does not
report them. T-47-22 asked for the scope to be written down and asserted; a prose docstring alone
would not fail if a later reader widened the walk.

**The mutation check was run and both outcomes recorded.** A line reading
`# MUTATION PROBE: the captured instant` was appended to `src/nativespeaker/api/services/sync.py`.
`TestNoProseNamesTheRemovedSubject::test_no_file_carries_a_banned_spelling` failed and named both
the file and the spelling: `{'src/nativespeaker/api/services/sync.py': ['captured instant']}`. The
line was then removed with the editor, not with `git checkout`, `git restore` or `git stash`.
`git diff --stat` over that file is empty and the guard reports 7 passed again.

**`_Harness.evaluated_at` in the schema suite was deleted rather than renamed.** Its only two
readers were the two `SyncService(...)` constructions. The usage seed that also used it now reads
`datetime.now(UTC)` inline, and its comment states the fact that remains true: the seeded period
must be this month or every read reports zero used. The stale first comment, about the instant
being captured after the insert so the predicate would not exclude the grant, was deleted — plan
47-01 moved that predicate onto `func.clock_timestamp()`, so the sentence was already false.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 deleted `tests/unit/test_sync_clock_capture.py`, which the plan gives to Task 2**
- **Found during:** Task 1
- **Issue:** With the source change in place the unit suite reported 5 failed / 1930 passed, and all
  five failures were in that file. Task 1's `<verify>` is `pytest -q` over the whole unit suite.
- **Fix:** `git rm` in Task 1's GREEN commit. The file was read in full first, as Task 2 requires.
- **Files modified:** `tests/unit/test_sync_clock_capture.py` (deleted)
- **Verification:** 1914 unit passed, which is 1935 less that file's 21 collected cases exactly
- **Committed in:** `d985a8e`

**2. [Rule 1 - Bug] The ahead-period case would have lost its property under the plan's wording**
- **Found during:** Task 1
- **Issue:** Described in full under Decisions. A past month literal inverts the branch the case
  guards and duplicates its neighbour.
- **Fix:** `AHEAD_PERIOD = "9999-12"`, the constant `tests/unit/test_quota_resolver.py` uses for the
  same branch. The case name changed from `..._of_this_request_...` to `..._of_this_month_...`.
- **Files modified:** `tests/unit/test_sync_resolver.py`
- **Verification:** both rollover branches pass; `TestTheRolloverIsComputedNeverWritten` is 5 cases
- **Committed in:** `7cdeefd`

**3. [Rule 3 - Blocking] The sync resolver suite's period constants had to move to the live clock**
- **Found during:** Task 1
- **Issue:** `PERIOD = "2026-08"` was derived from a fixed `EVALUATED_AT`. Once the service reads
  its own clock, every case asserting `entitlement.current_period == PERIOD` compares this month
  against a literal a month in the past. The plan named only the stale-period case.
- **Fix:** `PERIOD` is `monthly_period_for(datetime.now(UTC))` and `STALE_PERIOD` is `"2000-01"`,
  the split plan 47-01 established. `test_the_period_is_the_captured_instant_and_is_never_null`
  became `test_the_period_is_this_month_and_is_never_null` and derives the month independently
  rather than from the module constant, so it is not tautological against the case above it.
- **Files modified:** `tests/unit/test_sync_resolver.py`
- **Verification:** 41 cases in the file pass; `timedelta` became unused and was dropped, ruff clean
- **Committed in:** `7cdeefd`

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug).
**Impact on plan:** No scope creep. Two are files or constants that state a fact this plan deletes,
corrected in the commit that deletes it so every suite is green at every commit. One corrects a
sentence in the plan's action that would have removed a guarded property. The plan's task
boundaries moved; its content did not.

## Issues Encountered

**The plan's verification command 4 is unreachable by construction, and the plan says why.**
`grep -rl 'get_evaluated_at' src/ tests/ | wc -l` prints `1`, not `0`. The one file is
`tests/unit/test_instant_is_not_threaded.py`, which holds the name as the data its criterion-1 case
matches on. The plan's own `key_links` states this: "The absence guard must exclude its own file
from every walk: it necessarily contains the strings it forbids." Excluding the guard, the command
prints `0`. The grep is superseded by the guard, which asserts the same property over every other
file and is itself proved to fail on a reintroduction.

**Task 2's verify miscounts the table's parameter, and it was recorded rather than forced.**
`test "$(grep -v '^\s*#' src/nativespeaker/api/tables/grants.py | grep -c 'evaluated_at')" = "1"`
reports `2`. `grep -c` counts **lines**, and the one `monthly_period_for` parameter is spelled on
two: its signature at line 31 and its body at line 33. The criterion's intent — that the only
occurrence left is that one parameter — holds exactly. It was not forced by renaming the parameter:
criterion 3 allows a pure helper to take the datetime it computes from, and the plan's `key_links`
names `monthly_period_for` as one of the helpers that keep the name by design. This is the same
line-versus-occurrence miscount plan 47-05 recorded twice.

**Task 2's case-count criterion moved to Task 1 with the deletion.** "`uv run pytest -q` reports
roughly a dozen fewer collected cases than before" was satisfied at Task 1, where the unit suite
fell from 1935 to 1914 — exactly the deleted file's 21 collected cases and nothing more. Task 2's
own run was flat at 1914, because Task 2 changed one comment.

**One pre-existing e2e failure, out of scope and not fixed.**
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`
expects the log event `proof_rejected` while the code emits `purchase_proof_rejected`. Plans 47-01
through 47-06 each measured it at HEAD before this phase started; it is already recorded in
`deferred-items.md` and in `.planning/WINDOWS.md`, so no new entry was appended. The e2e suite is
360 passed / 1 failed and the 1 is not this plan's. Any "e2e exits 0" criterion is unreachable
while it stands.

**The type checker's baseline improved by two, and nothing was added.** `ty check` reports 311
against 313. This was diffed, not counted: `d314899` was exported with `git archive` to `/tmp`, the
venv was symlinked in, and the two sorted diagnostic sets were compared. Three diagnostic locations
were removed, all of them in the deleted `tests/unit/test_sync_clock_capture.py` and the
`stdlib/builtins.pyi` overload its `zip(..., strict=True)` call raised. Zero were added.

## Known Stubs

None. No hardcoded empty value, placeholder string or unwired component was written.

## Threat Flags

None. No new endpoint, auth path, file access pattern or schema change was introduced.

- **T-47-20 (sync reporting a grant the charge would refuse) held.** The grant read compares
  against `func.clock_timestamp()` and the period comes from one Python read taken in the same
  method. Both fail-closed raises are byte-identical and their comments were kept, because their
  subject is the refusal and not the instant. `tests/e2e/test_sync.py` is 14 passed, and the two
  schema files are 33 passed.
- **T-47-21 (a guard that passes for the wrong reason) held.** Four controls, and the mutation
  check was run: the guard failed on an injected reintroduction, naming the file and the spelling,
  and passed after the revert. Both outcomes are recorded above.
- **T-47-22 (the guard's own scope) held.** The exclusion is stated in the class docstring in one
  line and asserted by a fourth control that reads the three helper files, confirms they carry the
  name, and proves the walk does not report them.
- **T-47-SC:** no package was installed and no manifest was touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Roadmap criteria 1, 2 and 4 are met in full and are now executable rather than claimed. The
  guard fails on a reintroduction, which was measured.
- `app/dependencies.py` carries no `datetime` import, no `get_evaluated_at` and no changes outside
  `get_sync_service`. Phase 49 and Phase 50 see the file they planned against: `get_session_factory`,
  `get_firebase_adapter`, `get_devicecheck_adapter`, `get_challenge_store`, every
  `request.app.state.*` read and every `Request` parameter are untouched.
- `tests/unit/test_auth_package_shape.py` is byte-identical, so Phase 49's ratchet rewrite is
  unaffected.
- This is the last code plan of the phase. One thing to carry forward: the guard's criterion-2 walk
  is scoped to four packages. A future phase that moves `monthly_period_for`, `_transaction_status`
  or `_status_for` into `services/` or `crud/` must rename the parameter at the same time, or the
  guard will report it.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*

## Self-Check: PASSED

`tests/unit/test_instant_is_not_threaded.py` exists on disk, `tests/unit/test_sync_clock_capture.py`
does not, every file named in `key-files.modified` exists, and all four task commits of this plan
are reachable in `git log`.
