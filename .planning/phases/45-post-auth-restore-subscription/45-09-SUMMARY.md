---
phase: 45-post-auth-restore-subscription
plan: 09
subsystem: testing
tags: [verification, requirements, gap-closure, restore, pytest, ruff]

# Dependency graph
requires:
  - phase: 45-post-auth-restore-subscription
    provides: "45-06's escaped Play read URL and the two bounded request fields (truth 7 / CR-01, WR-02)"
  - phase: 45-post-auth-restore-subscription
    provides: "45-07's term check before any write (truth 1 / CR-02)"
  - phase: 45-post-auth-restore-subscription
    provides: "45-08's narrowed superseded set (truth 6 / CR-03)"
provides:
  - "One run of the four suite commands against all three gap-closure fixes at once, on real PostgreSQL"
  - "The dated 2026-09-08 gap-closure record under RESTORE-01: the three defects, the three fixes, the three covering test classes"
  - "Every 45-REVIEW finding this plan set did not incorporate, named with its reason"
  - "The migration comment D-10 made false, recorded as a known-stale comment with the wording it needs"
affects: [45 re-verification, 46-sign-out-all, v2.0 milestone close]

actuals:
  tokens: 8186
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A requirement is marked met on commands the marking plan itself ran, never on a count carried from an earlier run"

key-files:
  created: []
  modified:
    - .planning/STATE.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "The `git diff --quiet -- ../specs` acceptance check cannot run here — the specs live in the parent superrepo — so D-14 was proved by file mtime instead, read-only and without any git command against the parent"
  - "The e2e total rose by twelve rather than the eleven the plan predicted, because 45-07 added one case beyond its named five; the run is recorded as it printed, not as the plan expected"
  - "The header's conflict counts are left unchanged, and the entry states why: this gap closure moves the code toward the brief and adds no new divergence"
  - "`requirements.mark-complete` answers `table_unmatched` for both ids, as the PLAYHOOK note in the same table predicts for a range row; the checkboxes and the row were written by hand"
  - "The phase is recorded as executed and awaiting re-verification, never as complete: `/gsd:verify-phase 45` decides that"

patterns-established:
  - "A gap-closure plan set ends with one joint run: each fix verified its own files while the others were in flight, so nothing had yet tested the three together"
  - "A closing record names the defect, the fix, the covering case AND the reason the green suite missed it — the last part is the one a later reader needs"

requirements-completed: [RESTORE-01, RESTORE-02]

coverage:
  - id: D1
    description: "The three gap-closure fixes are green together on the whole suite, on real PostgreSQL, with counts observed in this plan's own run"
    requirement: RESTORE-01
    verification:
      - kind: unit
        ref: "uv run pytest -q — 1250 passed, 562 deselected"
        status: pass
      - kind: e2e
        ref: "uv run pytest -m e2e -q — 333 passed, 1479 deselected"
        status: pass
      - kind: integration
        ref: "uv run pytest -m schema -q — 229 passed, 1583 deselected"
        status: pass
      - kind: other
        ref: "uv run ruff check src tests — All checks passed!"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every total is strictly above the 45-05 figure it must exceed, so no case was silently uncollected"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "1250 > 1246 (45-06's four URL cases); 333 > 321 (45-06's four length cases plus 45-07's eight); 229 > 222 (45-08's seven cases)"
        status: pass
    human_judgment: false
  - id: D3
    description: "REQUIREMENTS.md carries a dated 2026-09-08 gap-closure entry under RESTORE-01 naming all three defects, all three fixes and all three covering test classes"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "grep -c 'CR-01' / 'CR-02' / 'CR-03' .planning/REQUIREMENTS.md — 8 / 5 / 6, all non-zero"
        status: pass
      - kind: other
        ref: "grep -c for each of TestThePlayRequestUrlIsConfinedToOneResource, TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach, TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves, TestTheDestinationStillLosesEverythingItHeld — 1 each"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every 45-REVIEW finding this plan set did not incorporate is named with its reason, WR-01 and WR-04 at more length"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "grep -c for WR-01, WR-03, WR-04, WR-05, WR-06, WR-07, IN-01, IN-02, IN-03, IN-04 — all non-zero"
        status: pass
    human_judgment: false
  - id: D5
    description: "RESTORE-02 carries the one-line note that a length 422 from the new bounds precedes both refusals of the two-refusal gate"
    requirement: RESTORE-02
    verification:
      - kind: other
        ref: "grep -c 'TestTheSurfaceGateIsTheStoreNameAndTheProof' .planning/REQUIREMENTS.md — 2"
        status: pass
    human_judgment: false
  - id: D6
    description: "Neither `10-restore-subscription.md` nor `SHARED-INVARIANTS.md` is edited (D-14)"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "mtime read: 10-restore-subscription.md 2026-08-18 23:40, SHARED-INVARIANTS.md 2026-09-01 00:55, both far before this phase's gap closure; `git status --short` in this repository shows only .planning/ files"
        status: pass
    human_judgment: false
  - id: D7
    description: "The record is honest evidence rather than a copied claim — the prohibition this plan exists to hold"
    verification: []
    human_judgment: true
    rationale: "That every count in the entry came from this plan's own run, and that no number was carried from 45-05 or from the three gap-closure summaries, is a judgment about the writing and not something a command can assert. The plan marked it `verification: judgment`. A reader must weigh the entry itself."
  - id: D8
    description: "The phase is ready for `/gsd:verify-phase 45` to answer VERIFIED on all seven truths"
    requirement: RESTORE-01
    verification: []
    human_judgment: true
    rationale: "The three failed truths are closed in the source and covered by named cases, but whether the verifier answers VERIFIED is the verifier's reading of the source, not this plan's to assert. `45-VERIFICATION.md` still reads `gaps_found` and will until it is re-run."

# Metrics
duration: 9 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 09: The three fixes proved together, and the record of what was wrong Summary

**One green run of the four suite commands against 45-06, 45-07 and 45-08 at once — 1250 unit, 333 e2e, 229 schema, ruff clean — and the dated gap-closure record under RESTORE-01 naming each defect, its fix, its covering case, and every review finding left open on purpose.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-09-08T21:21:17Z
- **Completed:** 2026-09-08T21:30:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **The three fixes are green together, which nothing had yet shown.** Each of 45-06, 45-07 and
  45-08 verified its own files while the other two were in flight. This plan ran the four commands
  once, on real PostgreSQL, with all three fixes present. They do not interact.
- **Every count rose, so no case was silently uncollected.** The unit total rose by 45-06's four
  URL cases, the schema total by 45-08's seven cases, and the e2e total by 45-06's four length
  cases and 45-07's eight.
- **RESTORE-01 carries the closing record.** A later reader now finds why the phase was re-opened,
  what changed, what proves it, and what was knowingly left alone — rather than a silence between a
  requirement marked met, reverted, and marked met again.
- **The lesson is recorded, not just the fix.** The phase's own 1246 / 321 / 222 passing suite caught
  none of the three defects, because no case set up a stored status that disagreed with the proof's
  term, a source account with a second unrelated subscription, or an adversarial token value. The
  code review found all three; the test run found none.
- **Ten review findings are recorded as decisions rather than omissions**, each by name with its
  reason. WR-01's stale migration comment carries the wording it needs, and WR-04's absent audit
  trail is stated as a carried-forward decision (37.1 D-01, 38 D-03) rather than an oversight.

## The four commands, quoted from this plan's own run

Run from the repository root, in this order, on 2026-09-08. No count below is copied from 45-05 or
from any of the three gap-closure summaries.

| Command | Summary line | 45-05 figure |
|---|---|---|
| `uv run pytest -q` | `1250 passed, 562 deselected, 9 warnings in 35.67s` | 1246 |
| `uv run pytest -m e2e -q` | `333 passed, 1479 deselected, 155 warnings in 47.10s` | 321 |
| `uv run pytest -m schema -q` | `229 passed, 1583 deselected, 1 warning in 28.77s` | 222 |
| `uv run ruff check src tests` | `All checks passed!` | clean |

`uv run pytest -q` was run a second time after the REQUIREMENTS.md edit, as Task 2's own `<verify>`
requires: `1250 passed, 562 deselected, 9 warnings in 37.28s`. No line beginning `FAILED` appeared in
any of the five runs, and `ruff` printed no rule code.

**The e2e rise is twelve, where the plan predicted eleven.** The plan expected 45-06's four length
cases and 45-07's seven. 45-07 shipped eight: it added
`test_an_active_proof_carrying_no_expiry_attaches_nothing` beyond its five named cases, as a
documented Rule 2 deviation, to cover a truth that plan declared and its own case list did not
reach. The run is recorded as it printed.

## Task Commits

1. **Task 1 (tracer): the four commands run once, against all three fixes together** — `8869423` (docs)
2. **Task 2: the record of what was wrong, what changed, and what was left open** — `e488552` (docs)

**Plan metadata:** the `docs(45-09)` commit that carries this file.

_Task 1 is a `type="tracer"` task whose `<verify>` is four automated commands and no human check,
with `workflow.human_verify_mode` at its default `end-of-phase`. The tracer feedback gate therefore
re-ran the verify rather than raising a checkpoint. All four were green, so the plan expanded to
Task 2._

## Files Created/Modified

- `.planning/STATE.md` — § Current Position rewritten: the three closed gaps named by truth number
  and review id, the joint run's counts, and the plain statement that the phase awaits
  re-verification and that `/gsd:verify-phase 45` — not this file — decides completion.
  `last_activity_desc` updated. The counters were read off disk at 2026-09-08T21:23Z (119 PLAN
  files, 118 SUMMARY files; Phase 45 itself 9 and 8) and `completed_plans` written as 119 because
  this plan's own summary lands after Task 2. `status:` stays `executing`; `completed_phases` stays
  at 15 and `percent` at 83, because the phase is executed and not verified.
- `.planning/REQUIREMENTS.md` — a dated 2026-09-08 gap-closure entry under RESTORE-01 in seven
  blockquote paragraphs; a dated gap-closure line under RESTORE-02; both checkboxes marked `[x]`;
  the traceability row rewritten to name 45-01 … 45-05 as the source plans and 45-06 … 45-09 as the
  gap-closure plans, and to read `Complete, awaiting re-verification`.

## Decisions Made

- **D-14 was proved by mtime, because the acceptance-criterion command cannot run here.** See the
  deviation below. `../specs` is in the parent superrepo, outside this repository.
- **The header's conflict counts are unchanged, and the entry says why.** This gap closure adds no
  divergence from `10-restore-subscription.md`. Every change moves the code toward what the brief
  and `SHARED-INVARIANTS.md` already require: the brief's step 8 asks the verification call to reach
  the store, § "Fail-closed defaults" refuses a value of unexpected shape, and D-10 expires *the old
  owner's subscription grant* — that grant, not every grant it holds. Counting nothing is the
  correct answer, and the entry states it so a later reader does not read the unchanged number as a
  forgotten update.
- **`requirements.mark-complete` reports `table_unmatched` for both ids.** That is the documented
  behaviour for a range row, recorded in this same table under PLAYHOOK-01: every row here is a
  range, and reshaping one to suit the parser would make it inconsistent with the twelve others. The
  checkboxes and the traceability row were written by hand.
- **The phase is not marked complete anywhere.** `45-VERIFICATION.md` still reads `gaps_found` and
  still records RESTORE-01 as BLOCKED. Re-verification changes those, and this plan says so in both
  files it touches.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The `git diff --quiet -- ../specs` acceptance check cannot run in this repository**

- **Found during:** Task 2 (verifying the acceptance criteria)
- **Issue:** The plan's criterion is `git diff --quiet -- ../specs` reports no change. `../specs`
  resolves to `/home/init/native-speaker/specs`, which belongs to the parent superrepo;
  `ns-api-gateway` is a submodule of it. The command answers
  `fatal: ../specs: '../specs' is outside repository at '/home/init/native-speaker/ns-api-gateway'`
  and a non-zero exit, which reads as "the specs changed" when the truth is that git cannot see
  them from here. Running it against the parent repository is outside this execution's scope.
- **Fix:** D-14 was proved read-only and without any git command against the parent: both spec files
  were read by mtime — `10-restore-subscription.md` at 2026-08-18 23:40 and `SHARED-INVARIANTS.md`
  at 2026-09-01 00:55, each far earlier than this phase's gap closure — and `git status --short` in
  this repository shows only `.planning/` files across the whole plan.
- **Files modified:** none; this is a verification-method change.
- **Verification:** The mtime read and the status output are both recorded above and under coverage
  entry D6.
- **Committed in:** no code change; recorded here and under RESTORE-01.

**2. [Rule 2 - Missing Critical] The plan's own acceptance criterion needed IN-02 and IN-03 named individually**

- **Found during:** Task 2 (checking the criteria after the first draft)
- **Issue:** The entry first named the four Info findings as the range `IN-01 … IN-04` with one
  shared reason, which is how 45-06's `<source_audit>` records them. The plan's acceptance criterion
  requires `IN-01`, `IN-02`, `IN-03` and `IN-04` each named with a reason. `grep -c 'IN-02'` and
  `grep -c 'IN-03'` both read `0` against the first draft, so a later reader searching for either id
  would have found nothing.
- **Fix:** The range was expanded to four named items, each with its own one-line reason — the
  second clock source, the `-> None` return value, the unguarded `identity.user.id` dereference, and
  the eight-times-duplicated SQLSTATE block — keeping the shared closing statement that all four are
  hygiene.
- **Files modified:** `.planning/REQUIREMENTS.md`
- **Verification:** `grep -c` for each of IN-01 … IN-04 now reads 1.
- **Committed in:** `e488552` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Neither changes what the plan set out to prove. The first replaces an
unrunnable check with a stronger read-only one and keeps the scope limit against the parent
repository. The second makes the record findable by the ids a later reviewer will search for. No
source file was touched by this plan, and no file outside `<files_modified>` was changed.

## Estimate vs actuals

The plan estimated 20000 tokens (40000 raw). The realized diff across `.planning/STATE.md` and
`.planning/REQUIREMENTS.md` is 32746 characters, so **8186** on the same `chars/4` scale — about
two fifths of the estimate. The estimate is not adjusted to look closer. Task counts and confidence
were both accurate: two tasks, and the plan's `confidence: high` held, with no checkpoint reached.

## Issues Encountered

None. The precondition held on both halves: 45-06, 45-07 and 45-08 are all committed on
`gsd/v2.0-authentication-entitlements` (`bc01e99`, `25e56cf`, `8e01306` and their siblings, verified
in `git log` before any command ran), and PostgreSQL 17 answered on this repository's `.env` `DB_*`
credentials — the e2e and schema markers both opened real sessions and both were green.

## Known Stubs

None. This plan touches no source file and introduces no debt marker, placeholder or hardcoded
empty value.

## Known residuals, carried into re-verification

- **`45-VERIFICATION.md` still reads `gaps_found`, and still records RESTORE-01 as BLOCKED.** That
  is correct: a report records what it observed on 2026-09-07. `/gsd:verify-phase 45` is what
  supersedes it.
- **The stale migration comment on `last_cross_account_transfer_month`** (45-REVIEW WR-01) is
  recorded under RESTORE-01 with the wording it needs, and the migration is not edited (D-14).
- **A restore still writes no audit row** (45-REVIEW WR-04). It is a carried-forward decision
  (37.1 D-01, 38 D-03) and not an oversight, and it is stated as such in the record.
- **`TestTheTwoRefusalsOfTheRestoreNotFoundFamily` still says "Two" while holding three arms**
  (45-07's own recorded residual). One-line rename, no other reference in the repository.

## Threat Flags

None. This plan adds no network endpoint, no auth path, no file access pattern and no schema change.
Its own register is satisfied: **T-45-09-01** (repudiation — a count copied from an earlier run)
is mitigated, because every count in the entry comes from the run recorded above and RESTORE-01 was
marked met only after that run was green; **T-45-09-02** (tampering with the binding brief) is
mitigated, because neither spec file was edited and both were checked; **T-45-09-SC** stands
accepted, because no package was installed and `uv.lock` is untouched.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **`/gsd:verify-phase 45` can be re-run.** All three failed truths are closed in the source, each
  covered by named cases, and the four commands are green together.
- **Phase 46 (`POST /auth/sign-out-all`) is unblocked by this plan and unaffected by it.** The
  `sign_out_all` operation-label flag under SIGNOUT-01 stays open: RESTORE-01's answer is a
  precedent for it and never an answer to it.
- **v2.0 milestone close** should read RESTORE-01's gap-closure entry before it reads the "Met as
  written" paragraph above it — the second is the phase's first claim, and the first is what
  survived verification.

## Self-Check

- `.planning/phases/45-post-auth-restore-subscription/45-09-SUMMARY.md` — FOUND
- `.planning/STATE.md` — FOUND
- `.planning/REQUIREMENTS.md` — FOUND
- Commit `8869423` — FOUND in `git log`
- Commit `e488552` — FOUND in `git log`

## Self-Check: PASSED

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*
