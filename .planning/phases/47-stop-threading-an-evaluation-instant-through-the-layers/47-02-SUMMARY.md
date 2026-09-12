---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 02
subsystem: infra
tags: [requirements, shared-invariants, record, sync]

requires:
  - phase: 38-auth-sync
    provides: SYNC-01, the requirement that claims the one-evaluation-time property was met
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "47-01 deleted the property in code — the record follows it here"
provides:
  - The SHARED-INVARIANTS.md one-evaluation-time clause is struck; its current_period rule survives
  - SYNC-01 carries a dated Phase 47 (D-02) amendment and stays checked
  - The SYNC-01 … SYNC-03 traceability row names Phase 47
affects: [47-03, 47-04, 47-05, 47-06, 47-07, 47-08, 48, 49, 50]

actuals:
  tokens: 1700
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "An invariant this milestone gives up is struck at its source, not carried as a permanent flagged conflict"

key-files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
    - /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md

key-decisions:
  - "D-02 applied: the invariant was struck, not flagged. RESEARCH Finding 7 and PATTERNS Cluster 12 both recommended flagging; the user overrode both on the Phase 38 plan 38-04 precedent."
  - "No checkpoint was emitted for the one-way task. D-02, dated 2026-09-11, is the human decision the gate exists to collect."
  - "Task 1 produced no commit. Its only file lives outside this repository's git tree, so there was nothing to stage."
  - "The flagged-conflict count is left unchanged. This phase resolves its conflict by removal and files no new one, which is the Phase 38 D-03 precedent."
  - "actuals.tokens is chars/4 over the realized diff (~6700 chars). Plan 47-01 measured whole changed files instead, so the two numbers are not on the same scale."

patterns-established:
  - "Pattern 1: the record moves before the code contradicts it, so no commit lands against a live invariant it violates"

requirements-completed: []

coverage:
  - id: D1
    description: "The SHARED-INVARIANTS.md bullet no longer binds any phase to one captured evaluation time per request, and its current_period rule survives word for word"
    verification:
      - kind: other
        ref: "grep -c 'ONE captured evaluation time' SHARED-INVARIANTS.md == 0"
        status: pass
      - kind: other
        ref: "grep -c 'current_period. is .YYYY-MM., UTC calendar month' SHARED-INVARIANTS.md == 1"
        status: pass
      - kind: other
        ref: "grep -c 'consistent snapshot per request' SHARED-INVARIANTS.md == 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "The shared effective-grant predicate one line above the struck bullet is unchanged"
    verification:
      - kind: other
        ref: "grep -c \"starts_at <= now AND (ends_at IS NULL OR ends_at > now)\" SHARED-INVARIANTS.md == 1"
        status: pass
      - kind: other
        ref: "grep -c '^## Grants and evaluation time' SHARED-INVARIANTS.md == 1"
        status: pass
    human_judgment: false
  - id: D3
    description: "SYNC-01 carries a dated Phase 47 (D-02) amendment, stays checked, and the traceability row names Phase 47"
    verification:
      - kind: other
        ref: "grep -c 'Amended by Phase 47 (D-02), 2026-09-11' .planning/REQUIREMENTS.md == 1"
        status: pass
      - kind: other
        ref: "grep -c '\\[x\\] \\*\\*SYNC-01\\*\\*' .planning/REQUIREMENTS.md == 1"
        status: pass
      - kind: other
        ref: "grep -n 'SYNC-01 … SYNC-03' .planning/REQUIREMENTS.md | grep -c 'Phase 47' == 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "The amendment names what replaces the deleted property and why a database-side now() would not restore it"
    verification:
      - kind: other
        ref: "grep -q 'clock_timestamp' .planning/REQUIREMENTS.md"
        status: pass
      - kind: other
        ref: "grep -c 'transaction_timestamp\\|several transactions' .planning/REQUIREMENTS.md >= 1"
        status: pass
    human_judgment: false
  - id: D5
    description: "Nothing outside the submodule is staged, committed or pushed"
    verification:
      - kind: other
        ref: "git status --porcelain lists only .planning paths inside ns-api-gateway"
        status: pass
    human_judgment: false

duration: 2 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 02: Strike the invariant, amend the requirement Summary

**`SHARED-INVARIANTS.md` no longer binds any phase to one captured evaluation time per request, and SYNC-01 carries a dated Phase 47 (D-02) amendment saying what the endpoint rests on instead.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-12T05:58:56Z
- **Completed:** 2026-09-12T06:00:06Z
- **Tasks:** 2
- **Files modified:** 2 (one inside this repository, one outside it)

## Accomplishments

- The bullet in § "Grants and evaluation time" is now one sentence: `` `current_period` is
  `YYYY-MM`, UTC calendar month.`` The derivation rule that opened it is gone. It was not
  replaced by a weaker version of itself — there is no "where practical", no "per transaction"
  and no "prefer".
- The shared effective-grant predicate one line above it is untouched. Phase 47 keeps that
  predicate's shape and changes only what supplies the compared value; the invariant's wording
  already said `now`.
- SYNC-01 carries a six-paragraph dated blockquote, in the shape of the SYNC-03 amendment three
  lines below it. It states the deleted property, what replaces it, why a database-side `now()`
  would not restore it, that the treatment is amended rather than withdrawn, that the source
  obligation was removed rather than diverged from, and that Phase 38's success criterion 1 is
  superseded.
- The traceability row `SYNC-01 … SYNC-03 | Phase 38` names Phase 47. The row stays a range, as
  every row in that table is.
- Nothing outside `/home/init/native-speaker/ns-api-gateway` was staged, committed or pushed.

## Task Commits

1. **Task 1: strike the one-evaluation-time clause** — no commit. See "Decisions Made".
2. **Task 2: amend SYNC-01 and its traceability row** — `d8bbd88` (docs)

## Files Created/Modified

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — one bullet
  rewritten in § "Grants and evaluation time". No other line, section or heading changed.
- `.planning/REQUIREMENTS.md` — the SYNC-01 amendment and the traceability row.

## Decisions Made

**D-02 applied as the user locked it: strike, not flag.** RESEARCH Finding 7 recommends recording
the conflict and explicitly says the planner should not edit `SHARED-INVARIANTS.md`. PATTERNS
Cluster 12 repeats that instruction. Both are overridden by D-02, dated 2026-09-11. The precedent
is Phase 38 plan 38-04, which struck § "Audit" from the same file under a decision the developer
had taken. This is recorded here so a reviewer reading the two research artifacts does not read
the plan as having ignored them.

**No checkpoint was emitted for the `one-way` task, and that is the plan's own instruction.** The
human decision the reversibility gate exists to collect has already been taken — it is D-02. A
checkpoint would have stopped the run to re-ask an answered question.

**Task 1 produced no commit, and an empty commit was not manufactured.** The only file the task
touches is outside this repository's git tree. `git status --porcelain` shows no path for it, so
there was nothing to stage. The plan forbids any git command against that path. Task 2's
amendment is the in-repository record of the strike, which is what T-47-07 asks for.

**The flagged-conflict count in the "Standing after…" table is left alone.** The plan's action
directs this, and the ground is the Phase 38 D-03 precedent: after the clause is struck there is
no surviving invariant text to diverge from, so this phase files no new flagged conflict. The
amendment states that in its own fifth paragraph, so a later reader finds the reasoning beside
the unchanged count rather than only here.

**`actuals.tokens` is measured over the realized diff, not over whole changed files.** The diff
is about 6700 characters, so 1700 on the chars/4 scale, against a 20000 estimate. Plan 47-01
measured whole changed files and reported 82690. The two numbers are therefore not comparable.
The template names the diff, so the diff is what is reported, and the difference in method is
named here so a later calibrator does not read it as a real gap.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**One verify command errors, and its result is still correct.** Task 1's fourth `<automated>`
check is `git -C …/ns-api-gateway status --porcelain -- /home/init/native-speaker/specs | wc -l
| grep -qx 0`. Git refuses the pathspec with *"'/home/init/native-speaker/specs' is outside
repository"* and writes nothing to stdout, so `wc -l` prints `0` and the check passes. The exit
status is what the plan asked for, and the fact it asserts — no out-of-submodule path is staged
— is separately confirmed by a bare `git status --porcelain`, which lists only
`.planning/REQUIREMENTS.md` and three untracked phase directories for phases 48, 49 and 50 that
predate this plan.

## Threat Flags

None. T-47-06 held: three greps pin the struck phrase at zero, the surviving clause at one and
the untouched shared predicate at one, and the section heading is unchanged. T-47-07's record is
Task 2's amendment, which names the decision, the date and what replaces the property. T-47-08
held: no git command in this plan referenced the specification path, and `git status --porcelain`
lists no path outside the submodule. T-47-SC: nothing was installed and no manifest was touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The record now matches the code for the chain 47-01 changed. No later commit in this phase
  lands against a live invariant it violates.
- Plans 47-03 through 47-08 can proceed without owing a record edit; this plan is the phase's
  whole record obligation.
- One thing to carry forward: the SYNC-01 bullet text itself still reads "all derived from one
  captured evaluation time". That is deliberate — the bullet is not edited, and the amendment
  below it is what a reader is meant to reach. A future reader grepping the bullet text alone
  would get a false answer.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*

## Self-Check: PASSED

Both modified files exist on disk, the plan's four verification commands pass, and commit
`d8bbd88` is reachable in `git log`.
