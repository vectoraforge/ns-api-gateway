---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 08
subsystem: infra
tags: [pytest, ruff, record, roadmap, entitlements, regression]

requires:
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-02: the struck invariant and the dated SYNC-01 amendment (D-02)"
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-07: the deleted dependency and the absence guard that makes criteria 1, 2 and 4 executable"
provides:
  - The three suites and the linter measured on this run, against the finished tree
  - Each of the five roadmap criteria re-derived with the command that proves it
  - A new defect found and named - the one-minute open term in the attribution suite
  - The ROADMAP Phase 47 entry closed with measured annotations, criterion 5 recorded NOT MET
  - STATE.md carrying D-01, D-02 and the forward notes for Phases 49 and 50
affects: [48, 49, 50]

actuals:
  tokens: 5100
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A closing plan runs every command itself; a count copied from an earlier summary is not proof"
    - "A suspected clock-dependent failure is proved by a probe that reproduces the gap, not by reading the code"

key-files:
  created:
    - .planning/phases/47-stop-threading-an-evaluation-instant-through-the-layers/47-08-SUMMARY.md
  modified:
    - .planning/ROADMAP.md
    - .planning/STATE.md
    - .planning/phases/47-stop-threading-an-evaluation-instant-through-the-layers/deferred-items.md
    - .planning/WINDOWS.md

key-decisions:
  - "Criterion 5 is recorded NOT MET. Two suites exit non-zero. The result was not rounded up to a pass."
  - "A second failure was found, and it is this phase's own: a one-minute open term in tests/unit/test_subscription_attribution.py, introduced by plan 47-05."
  - "The defect was not repaired. This plan writes no source and its own action forbids repair; the fix belongs in a gap-closure plan."
  - "Criterion 3 is closed as met in spirit with the D-01 deviation named in its own annotation, not in a footnote."
  - "The record was still closed, red criterion and all. Stopping without a SUMMARY would leave the phase record open and say nothing."

patterns-established:
  - "Pattern 1: a failure suspected of depending on elapsed time is proved with a plugin that sleeps after collection and before execution, which is the exact gap under suspicion"
  - "Pattern 2: a phase gate records a red criterion in the ROADMAP annotation itself, so the next reader meets the truth before the plan list"

requirements-completed: []

coverage:
  - id: D1
    description: "Criterion 1 - get_evaluated_at does not exist, no Depends supplies a datetime, and the e2e override is gone"
    verification:
      - kind: other
        ref: "grep -rl 'get_evaluated_at' src/ lists nothing; grep -rl 'get_evaluated_at' tests/e2e/ lists nothing"
        status: pass
      - kind: other
        ref: "grep -rn 'datetime' src/nativespeaker/api/app/dependencies.py src/nativespeaker/api/routers/ prints nothing (exit 1)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_instant_is_not_threaded.py (7 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Criterion 2 - no service or crud file carries an evaluated_at parameter"
    verification:
      - kind: other
        ref: "grep -rl 'evaluated_at' src/nativespeaker/api/{services,crud,routers,app} lists nothing (count 0)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Criterion 3 - the SQL comparisons are database-side and every Python read is one per method"
    verification:
      - kind: other
        ref: "grep -rc 'clock_timestamp' crud/grants.py crud/challenges.py == 2 and 3; grep -rn 'func.now()' src/ prints nothing"
        status: pass
      - kind: other
        ref: "19 datetime.now(UTC) reads, one per method, named in this SUMMARY; 2 more predate the phase in auth/devicecheck.py"
        status: pass
    human_judgment: true
    rationale: "The criterion is worded now() and the code uses clock_timestamp(). D-01 resolved it. A human reading the record must accept the substitution rather than a command deciding it."
  - id: D4
    description: "Criterion 4 - no comment or docstring names the removed dependency, and the clock-capture module is gone"
    verification:
      - kind: other
        ref: "grep -rniE 'captured instant|shared instant|one instant|evaluation time|get_evaluated_at' src/ prints nothing (exit 1)"
        status: pass
      - kind: other
        ref: "ls tests/unit/test_sync_clock_capture.py exits 2"
        status: pass
      - kind: unit
        ref: "tests/unit/test_instant_is_not_threaded.py#TestNoProseNamesTheRemovedSubject"
        status: pass
    human_judgment: false
  - id: D5
    description: "Criterion 5 - the three suites all exit 0"
    verification:
      - kind: integration
        ref: ".venv/bin/pytest -q -m schema tests/schema (291 passed, exit 0)"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -m e2e tests/e2e (360 passed, 1 failed, exit 1)"
        status: fail
      - kind: regression
        ref: ".venv/bin/pytest -q -m '' (2571 passed, 2 failed, exit 1, 2573 collected)"
        status: fail
    human_judgment: true
    rationale: "The criterion is NOT met. One failure is pre-existing and predates the phase; one is new and this phase's own. Neither is repaired here. A human decides whether the phase ships with them open."
  - id: D6
    description: "The ROADMAP entry and STATE.md carry the close, and the ROADMAP diff touches only the Phase 47 entry and its progress row"
    verification:
      - kind: other
        ref: "git diff -U0 .planning/ROADMAP.md shows four hunks: lines 793, 796-800, 828, 936"
        status: pass
      - kind: other
        ref: "grep -c '#### Phase 4[89]:|#### Phase 50:' .planning/ROADMAP.md == 3"
        status: pass
      - kind: other
        ref: "git status --porcelain lists no path outside the submodule"
        status: pass
    human_judgment: false

duration: 42 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 08: The phase gate Summary

**Four criteria are met and re-derived here with the command that proves each; criterion 5 is measured red, with one pre-existing failure and one new defect this phase introduced — a test term that stays open for only one minute after module import.**

## Performance

- **Duration:** 42 min
- **Started:** 2026-09-12T07:55:00Z
- **Completed:** 2026-09-12T08:37:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- **Every number below was measured in this plan's own run.** No count is copied from an
  earlier summary. That is this project's convention, set in plans 45-09 and 46-05.
- All four commands were run. Three are green. Two suites exit non-zero.
- **A new defect was found, and it is this phase's own.** It is named, located to the
  line, and proved by a probe rather than by reading the code.
- The five roadmap criteria are re-derived with their commands and their answers.
- The ROADMAP entry and STATE.md carry the close, and the ROADMAP diff touches only the
  Phase 47 entry and its progress row.

## Task 1 — the measured run

Run in this order. **`-m ''` is everything and needs the database. A bare
`.venv/bin/pytest -q` is the unit suite only, because `addopts` in `pyproject.toml` already
carries `-m 'not e2e and not schema'`. They are different suites, and reporting the second
as the first would claim the e2e and schema suites passed when they never ran.**

| Command | Result | Exit |
|---|---|---|
| `.venv/bin/pytest -q -m ''` | **2571 passed, 2 failed**, 2573 collected, 131.11 s | **1** |
| `.venv/bin/pytest -q -m e2e` | **360 passed, 1 failed**, 50.98 s | **1** |
| `.venv/bin/pytest -q -m schema` | **291 passed**, 34.13 s | 0 |
| `uv run ruff check src tests` | `All checks passed!` | 0 |

Two extra readings, taken for context and not asked for by the criterion:

| Command | Result | Exit |
|---|---|---|
| `.venv/bin/pytest tests/unit -q` (the bare unit suite) | **1921 passed**, 57.74 s | 0 |
| `.venv/bin/ty check` | **311 diagnostics** | 1 |

`ruff` was run in both forms — `.venv/bin/ruff check src tests` and the plan's literal
`uv run ruff check src tests`. Both print `All checks passed!` and exit 0.

`ty check` reads 311 against the **316** this phase started from. Five diagnostics went and
none was added, measured by earlier plans with a diff of the sorted sets rather than a count.
`ty` is not part of any criterion.

### The delta from the baseline, accounted for

RESEARCH measured the pre-phase baselines before the phase began: **2570** collected for
`-m ''`, **1917** for the bare unit run, **362** for `-m e2e`, **291** for `-m schema`.

| Suite | Before | Now | Change |
|---|---|---|---|
| `-m ''` collected | 2570 | **2573** | +3 |
| bare unit passed | 1917 | **1921** | +4 |
| `-m e2e` collected | 362 | **361** | −1 |
| `-m schema` passed | 291 | **291** | 0 |

The movement is small and every part of it is accounted for:

- `tests/unit/test_sync_clock_capture.py` was **deleted** by plan 47-07 — **−21 cases**.
- `tests/unit/test_open_term.py` was **added** by plan 47-05 — **+8 cases**.
- `tests/unit/test_instant_is_not_threaded.py` was **added** by plan 47-07 — **+7 cases**.
- The rest is the cases plans 47-01 through 47-06 added while pinning a single clock read,
  minus the one e2e case plan 47-05 deleted when it relocated the restore term boundary onto
  `_open_term`, and minus one row of a parametrized unit case each in plans 47-01 and 47-06.

**A drop larger than the deleted module's own 21 cases would have been a defect.** There was
no drop at all: the suite grew.

The schema count is the control. This phase touched no migration, so 291 is what Phase 46
left and what every plan of Phase 47 measured.

## Task 1 — the two failures

### Failure 1 — pre-existing, and not this phase's

```
tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody
    ::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing
```

The case expects log event `proof_rejected`; the code emits `purchase_proof_rejected`. Two
earlier executors measured it at HEAD `1a3273d`, **before this phase began**, with every edit
reverted, and it failed identically. It makes any "e2e exits 0" criterion unreachable as
literally worded, and it was unreachable from the first commit of the phase. It is recorded in
`deferred-items.md` and in `.planning/WINDOWS.md`. It is out of scope and is not fixed.

### Failure 2 — new, and this phase's own

```
tests/unit/test_subscription_attribution.py
    ::TestAnEntitledNotificationWithNoOpenTermIsRefusedBeforeAnyWrite
    ::test_a_term_still_open_when_the_ingestion_reads_is_written_control
```

**The root cause, to the line.** `tests/unit/test_subscription_attribution.py:964` builds the
notification with `expires_at=NOW + timedelta(minutes=1)`. `NOW` is `datetime.now(UTC)` read at
**module import**, line 33. The case is a control: it asserts that a term still open when
`SubscriptionsService.ingest` reads its own clock **is written**. The open window is therefore
one minute measured from import, not from the moment the case runs.

pytest imports every test module during collection. Any run longer than one minute between
that import and this case closes the term, so `ingest` refuses it and raises `InternalError` at
`src/nativespeaker/api/services/subscriptions.py:109`.

**Measured, not reasoned about.** Three readings:

1. The case run alone passes in **0.03 s**.
2. Under `.venv/bin/pytest -q -m ''` — 2573 cases over **131 s** — it fails.
3. A throwaway pytest plugin outside this repository, hooking `pytest_collection_finish` to
   sleep **65 s** — after every import, before any case runs — makes the case fail on its own,
   with the same raise site and the same captured log line
   `store_notification_without_term event_type=SUBSCRIBED`. That is the gap under suspicion,
   reproduced deliberately.

**The margin is thinner than it looks.** The bare unit run took **57.74 s** in this session and
passed. It is about two seconds under the window. The unit suite is not reliably green either;
it happened to be green today.

**Who introduced it.** Plan 47-05, deviation 3, which moved five test modules onto the live
clock because their fixed terms had fallen into the past. Its sibling terms are ten to thirty
days out. This one is one minute.

**The production code is correct.** The guard in `ingest` refuses a term that has run out,
which is exactly what CR-20 asks of it. Only the test's window is too small.

**It is not repaired here.** This plan writes no source, and its own action says a defect found
at the gate belongs in a gap-closure plan. It is logged in `deferred-items.md` and in
`.planning/WINDOWS.md` as an open entry, with the fix named: a wider window, or an open term
derived at call time rather than at import.

## Task 2 — the five criteria re-derived

### Criterion 1 — the dependency is gone — MET

> `get_evaluated_at` does not exist; no `Depends(...)` in `dependencies.py` or a router supplies
> a `datetime`, and `tests/e2e/test_restore_subscription.py` no longer overrides one.

| Command | Answer |
|---|---|
| `grep -rl 'get_evaluated_at' src/` | nothing |
| `grep -rn 'datetime' src/nativespeaker/api/app/dependencies.py src/nativespeaker/api/routers/` | nothing, exit 1 |
| `grep -rl 'get_evaluated_at' tests/e2e/` | nothing |
| `grep -rl 'get_evaluated_at' src/ tests/` | **one file** |

The function is deleted with its docstring. The second command is the stronger of the two: the
name `datetime` does not appear anywhere in `app/dependencies.py` or in the whole `routers/`
package, so no `Depends(...)` in either can supply one — the module does not import the name.

**The one remaining file is not a residue and the plan's own verify command cannot pass.** The
plan's Task 2 gate is `test "$(grep -rl 'get_evaluated_at' src/ tests/ | wc -l)" = "0"`. It
prints `1` and exits 1. The file is `tests/unit/test_instant_is_not_threaded.py`, the absence
guard plan 47-07 built, which **holds `get_evaluated_at` as the data its criterion-1 case matches
on** and excludes its own path from every walk. Plan 47-07 recorded the same thing and its plan
said so in advance: *"The absence guard must exclude its own file from every walk: it necessarily
contains the strings it forbids."* Excluding the guard, the command prints `0` and exits 0 —
measured here. The grep is superseded by the guard, which asserts the same property over every
other file, carries four controls, and **was proved to fail on a reintroduction** by a mutation
probe that named both the file and the spelling.

### Criterion 2 — no service or crud parameter — MET

> No service constructor and no service method has an `evaluated_at` parameter, and no crud
> method receives one from a service.

`grep -rl 'evaluated_at' src/nativespeaker/api/services src/nativespeaker/api/crud
src/nativespeaker/api/routers src/nativespeaker/api/app` lists **nothing**. Count `0`.

Three occurrences survive in `src/`, and **criterion 3 explicitly allows all three**. They are
pure helpers that take the datetime they compute from and read no clock:

| Helper | File |
|---|---|
| `monthly_period_for(evaluated_at)` | `src/nativespeaker/api/tables/grants.py:31` |
| `_status_for(..., evaluated_at)` | `src/nativespeaker/api/auth/google_play.py:198` |
| `_transaction_status(..., evaluated_at)` | `src/nativespeaker/api/auth/app_store.py:37` |

`seconds_until_rollover` in `services/quota.py` is a fourth helper of the same kind. Plan 47-01
renamed its parameter to `instant`, so it does not appear in the count. `auth/` and `tables/` are
deliberately outside the guard's four-package walk for this reason.

### Criterion 3 — the SQL comparisons and the Python reads — MET IN SPIRIT, DEVIATION NAMED

> Every SQL comparison against the current time uses `now()`; every Python read of the current
> time is a `datetime.now(UTC)` call at the point of use, with at most a small pure helper taking
> the datetime it computes from.

**The deviation, stated plainly.** The criterion is worded `now()`. **D-01 resolved it to
`func.clock_timestamp()`.** The reason was measured, not argued: PostgreSQL's `now()` is
`transaction_timestamp()`, and `tests/e2e/conftest.py` holds one outer transaction open per test
and joins every app session to it with `create_savepoint`, so a grant a test seeds is invisible
to `now()`. RESEARCH Finding 1 measured **11 of 41 quota tests turning red** under it.

**Criterion 3 is therefore closed as met in spirit, with the deviation named — not as met as
written.** What the criterion asks for is that the comparison happen database-side, and it does.
The function is a different one.

The two SQL sites, by name:

| Site | File | Reads |
|---|---|---|
| `_effective_grants_statement` | `crud/grants.py:34,36` | both bounds, `starts_at <=` and `ends_at >` |
| `ChallengesDB.claim` (`_claim_statement`) | `crud/challenges.py:31,32` | the expiry predicate and the `claimed_at` write, one evaluation in one statement |

`ChallengesDB.consume` stamps `consumed_at` from the same clock at `crud/challenges.py:86`.
`grep -rc 'clock_timestamp'` prints `2` for `crud/grants.py` and `3` for `crud/challenges.py`;
neither is zero. `grep -rn 'func.now()' src/` prints nothing, exit 1.

**The Python half is met as written.** Nineteen reads, one per method, each the first statement
of the method that stamps from it:

| Method | File |
|---|---|
| `QuotaService.charge` | `services/quota.py:43` |
| `SyncService.read_entitlement` | `services/sync.py:24` |
| `RestoreService.restore` | `services/restore.py:57` |
| `SubscriptionsService.ingest` | `services/subscriptions.py:32` |
| `GrantsDB.activate_anonymous_device_grant` | `crud/grants.py:169` |
| `GrantsDB.activate_registered_account_grant` | `crud/grants.py:231` |
| `IdentitiesDB.insert_account` | `crud/identities.py:96` |
| `IdentitiesDB.flip_provider` | `crud/identities.py:134` |
| `SubscriptionsDB.insert_subscription` | `crud/subscriptions.py:157` |
| `SubscriptionsDB.upsert_subscription` | `crud/subscriptions.py:180` |
| `SubscriptionsDB.claim_subscription_owner` | `crud/subscriptions.py:236` |
| `SubscriptionsDB.hold_subscription_clock` | `crud/subscriptions.py:250` |
| `SubscriptionsDB.insert_purchase` | `crud/subscriptions.py:263` |
| `SubscriptionsDB.append_event` | `crud/subscriptions.py:291` |
| `SubscriptionsDB.write_subscription_grant` | `crud/subscriptions.py:321` |
| `ChallengesDB.issue` | `crud/challenges.py:46` |
| `PlayDeveloperSubscriptions.read` | `auth/google_play.py:305` |
| `PlayDeveloperSubscriptions.read_for_restore` | `auth/google_play.py:365` |
| `AppStoreNotifications.verify_transaction` | `auth/app_store.py:136` |

Confirmed by count. `grep -rn 'datetime.now(UTC)' src/nativespeaker/api/{services,crud,auth}`
reports **21** occurrences. Nineteen are the reads above. The other two are in
`auth/devicecheck.py` at lines 78 and 89, and they **predate the phase** — `git show
1a3273d:…/auth/devicecheck.py` counts `2` as well, so the phase changed neither. Every other file
in the walk counted `0` before this phase and counts its listed number now.

### Criterion 4 — no comment names the removed subject — MET

> No comment or docstring names the removed dependency or the shared instant;
> `tests/unit/test_sync_clock_capture.py` goes with it.

| Command | Answer |
|---|---|
| `grep -rniE 'captured instant\|shared instant\|one instant\|evaluation time\|get_evaluated_at' src/` | nothing, exit 1 |
| `ls tests/unit/test_sync_clock_capture.py` | **exit 2** — the file is gone |
| `uv run pytest -q tests/unit/test_instant_is_not_threaded.py` | **7 passed**, exit 0 |
| `grep -c 'a partial index predicate must be IMMUTABLE' src/nativespeaker/api/crud/grants.py` | `1` |

The clock-capture module and its 21 cases went in plan 47-07. One guard of 7 cases with four
controls replaced it. The protected note in `crud/grants.py` survives the sweep, because its
subject is the index and not the instant.

### Criterion 5 — the three suites — NOT MET

Task 1's table above is the answer. `-m schema` exits 0. `-m e2e` and `-m ''` exit **1**.

**This is stated as a failure and not rounded up.** Of the two failures, one predates the phase
and one is the phase's own. Neither is repaired here. A gap-closure plan owns both.

## Task 2 — what this phase gave up

Recorded here so a later reader finds it rather than rediscovers it.

1. **The one-evaluation-time property is gone, and the invariant that stated it was struck.**
   Under **D-02** the bullet binding every phase to ONE captured evaluation time per request was
   deleted from `SHARED-INVARIANTS.md`, rather than carried as a permanent flagged conflict.
   SYNC-01 carries a dated amendment; Phase 38's success criterion 1 is superseded. A request now
   reads the clock several times, microseconds apart, and two reads in one request can disagree.
2. **The exact-equality expiry boundary in the challenge store is no longer observable end to
   end.** A live database clock never lands on a stored value. The property is now asserted over
   the **compiled SQL** — the rendered statement carries `expires_at > clock_timestamp()` and
   carries no `>=` — with a positive control that the render is not empty. What is lost is the
   round trip through PostgreSQL, not the guarantee.
3. **A superseded grant's `ends_at` can fall microseconds before its replacement's `starts_at`.**
   Within one writer call the two come from one read and stay equal, which a schema case asserts.
   Across a service calling several writers the reads differ. No machinery was built to prevent
   it.
4. **`func.clock_timestamp()` is VOLATILE, so the effective-grant predicate cannot drive an index
   scan on `starts_at` or `ends_at`.** Accepted on a table holding a handful of rows per user and
   already filtered by `user_id` and `status`.

**A fifth, added by this plan's own measurement.** Nine test modules now derive a term or a period
from the wall clock where they used fixed literals before. That is the price of a live clock in the
code under them, and it was accepted knowingly. **The new defect in Task 1 is the first bill for
it, and it arrived within the same phase.**

## Task 3 — the record

`.planning/ROADMAP.md`, scoped edits only. Four hunks, confirmed with `git diff -U0`:

| Line | Change |
|---|---|
| 793 | `**Plans:** 7/8 plans executed` → `8/8 plans complete` |
| 796–800 | the five criteria, each annotated with its measured result and the date |
| 828 | `- [ ] 47-08-PLAN.md` → `- [x]` |
| 936 | the progress row: `7/8 \| In Progress` → `8/8 \| Executed — criterion 5 unmet \| 2026-09-12` |

No other phase entry was touched. The three later phase entries are present, count `3`. The eight
plans were already listed under their six waves with a one-line objective each, so only the last
checkbox needed checking — which is the smallest diff that closes the entry, and what T-47-25 asks
for.

Criterion 3's annotation names `clock_timestamp()` and D-01 **in the criterion's own text**, not
in a footnote. Criterion 5's annotation states both failures and names which one is the phase's
own, so a reader meets the truth before the plan list.

`.planning/STATE.md`: the position moved past Phase 47, recorded **executed and not verified**.
D-01 and D-02 are in the accumulated context with their measured reasons. The two forward notes
are there: Phase 49 still owns the `PlaySubscriptionSource` deletion and the `ChallengesDB`
construction move, and Phase 50 still owns the `dependencies.py` rewrite, which this phase left
otherwise intact by design.

`completed_phases` stays at **17** and `percent` stays at **77**. This file's own convention is
that only `/gsd:verify-phase` moves them, and it should not move them while criterion 5 stands.

Nothing outside `/home/init/native-speaker/ns-api-gateway` was staged, committed or pushed.
`git status --porcelain` lists no path under the external specification tree. Phase 46's plans pin
that file's sha256 in their verify commands; those pins are stale by design after plan 47-02, they
were not re-run, and the changed digest is not a defect.

## Task Commits

1. **Task 1: record the defect the gate measured** — `6a89283` (docs)
2. **Task 2: no commit of its own** — its whole output is this SUMMARY
3. **Task 3: close the record in ROADMAP.md and STATE.md** — `a7adf5d` (docs)

Task 2 manufactured no empty commit. This follows plan 47-02, which recorded the same thing for
the same reason: a task whose only product is prose in the SUMMARY commits when the SUMMARY does.

## Files Created/Modified

- `.planning/ROADMAP.md` — the Phase 47 entry's criteria, plan count, last checkbox and progress row
- `.planning/STATE.md` — position, the Phase 47 outcome paragraph, D-01, D-02 and the two forward notes
- `.planning/phases/47-…/deferred-items.md` — the new defect, with its root cause and its proof
- `.planning/WINDOWS.md` — the same defect as an open ledger entry
- `.planning/phases/47-…/47-08-SUMMARY.md` — this file

## Decisions Made

**Criterion 5 is recorded NOT MET, and the phase is recorded executed rather than complete.**
Two suites exit non-zero. The plan's own project rules say a partial result is not rounded up to a
pass, and the ROADMAP progress row and the STATE status both say so where a reader meets them
first.

**The new defect was diagnosed to the line and proved, not guessed.** A case that passes alone and
fails in a long run is the classic shape of a stale module-level clock read, but that shape is a
hypothesis until something reproduces it. The 65-second post-collection sleep is what turned it
into a fact, and it reproduced the same raise site and the same log line.

**The defect was not repaired.** This plan writes no source and its action says so twice. Repairing
it here would also have meant a source edit landing in the same commit as the measurement that
found it, which is the opposite of an honest gate.

**The record was still closed, red criterion and all.** The plan's action says to stop and report a
red suite. Reading that as "abort and write nothing" would leave the phase record open and silent,
which is worse than a record that names its own failure. Tasks 2 and 3 are the report.

**Criterion 1's own verify command is unreachable, and it was recorded rather than forced.** The
guard necessarily holds the string it forbids. Deleting the string from the guard would delete the
guard's subject; excluding the guard from the grep gives the answer the criterion means, and that
was measured too.

## Deviations from Plan

### Recorded, not auto-fixed

**1. [Rule 1 - Bug] A new failing test was found and deliberately left unfixed**
- **Found during:** Task 1
- **Issue:** `tests/unit/test_subscription_attribution.py:964` builds an open term one minute past
  a module-import `NOW`. Any run longer than a minute between collection and the case closes the
  term, so `ingest` raises `InternalError`. It fails under `-m ''`. Introduced by plan 47-05.
- **Why it was not fixed:** Rule 1 would normally auto-fix. This plan's action overrides it in two
  places — *"Do not repair source in this plan: a defect found here belongs in a gap-closure plan,
  and this plan's job is to measure honestly"* — and the plan writes no source at all. The more
  specific instruction wins.
- **What was done instead:** the root cause was located to the line, proved with a probe, and
  written into `deferred-items.md`, `.planning/WINDOWS.md`, the ROADMAP criterion-5 annotation and
  the STATE.md outcome paragraph, with the fix named.
- **Committed in:** `6a89283`

**2. [Rule 3 - Blocking] Task 2's fourth verify command cannot pass**
- **Found during:** Task 2
- **Issue:** `test "$(grep -rl 'get_evaluated_at' src/ tests/ | wc -l)" = "0"` prints `1`. The one
  file is the absence guard, which holds the string as its own test data.
- **Fix:** none is possible or wanted. The variant excluding the guard was run and exits 0, and
  both readings are recorded under criterion 1. Plan 47-07 recorded the same result, and its plan
  predicted it in its `key_links`.
- **Verification:** `grep -rl 'get_evaluated_at' src/ tests/ | grep -v test_instant_is_not_threaded | wc -l` is `0`
- **Committed in:** n/a — a record, not a change

---

**Total deviations:** 2 recorded, 0 auto-fixed.
**Impact on plan:** The plan's content stands. One deviation is a real defect this plan is
forbidden to repair and therefore reports as loudly as it can. The other is a gate that was known
to be unreachable before this plan started.

## Issues Encountered

**The first suite run's exit code was masked and had to be re-measured.** `-m ''` was first run
through `| tail -40`, which reports the exit status of `tail` and not of pytest. The result looked
like exit 0 with two failures in the text. Every command in the table above was re-run with its own
exit code captured directly. A pipeline is not a gate.

**`ty check` exits 1 and always has.** It reports 311 diagnostics. That is not a regression — the
phase started at 316 — and `ty` is in no criterion. It is recorded so a later reader does not read
the non-zero exit as new.

**The bare unit suite took 57.74 s, not the ~20 s the validation strategy estimates.** This matters
only because of the new defect: the one-minute window is about two seconds away from failing the
unit suite as well.

## Known Stubs

None. This plan wrote no source and no test.

## Threat Flags

None. No endpoint, auth path, file access pattern or schema change was introduced.

- **T-47-23 (criterion 5 reported on a deselected suite) held.** `-m ''` collected **2573**, far
  above the gate's 2400 floor, so the suite was not deselected and no marker was lost. The database
  was reachable and no substitution was made. The distinction between `-m ''` and the bare unit run
  is stated in Task 1 and both numbers are reported separately.
- **T-47-24 (a copied count) held.** All four commands ran in this plan. Every number in this
  SUMMARY has a command beside it that produced it in this session.
- **T-47-25 (a whole-file rewrite of ROADMAP.md) held.** Four scoped hunks, confirmed with
  `git diff -U0`. The three later phase entries are present, count `3`.
- **T-47-08 (git scope) held.** `git status --porcelain` lists no path outside the submodule. No git
  command in this plan referenced the external specification path. The stale Phase 46 sha256 pins
  were not re-run.
- **T-47-SC:** nothing was installed and no manifest was touched. The only file created outside the
  repository was a throwaway pytest plugin in `/tmp`, used once as a probe.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Phase 47 is executed. It is not verified, and it should not be verified green while criterion
  5 stands.** `/gsd:verify-phase 47` is the decision point, and this record is deliberately shaped
  so that command meets the red criterion first.
- **Two entries are open in `.planning/WINDOWS.md` and both need a gap-closure plan.** The
  pre-existing `proof_rejected` log-event mismatch, which is a one-word fix in either the case or
  the code and belongs to whoever owns the restore vocabulary. And the one-minute open term, which
  is this phase's own and should be fixed by widening the window or deriving the term at call time.
- **Phase 48 is unblocked and always was** — its roadmap entry says it is independent of Phase 47.
- **Phase 49 sees the shape it planned against.** `PlaySubscriptionSource` is still declared with
  both methods free of the datetime, `ChallengesDB` is still built in the lifespan behind
  `get_challenge_store`, and `tests/unit/test_auth_package_shape.py` is byte-identical through all
  eight plans.
- **Phase 50 sees the shape it planned against.** `app/dependencies.py` changed only where a
  factory declared the deleted dependency; it now imports no `datetime`, and every
  `request.app.state.*` read, every `Request` parameter and the three one-line getters are intact.
- **One thing to carry forward, and it is the phase's real residue.** Nine test modules now read
  the wall clock at import or at call. The new defect proves that class of test is fragile in a way
  the old fixed literals were not. A later phase adding a clock-dependent case should derive its
  term at call time, and should choose a window measured in days rather than minutes.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*
