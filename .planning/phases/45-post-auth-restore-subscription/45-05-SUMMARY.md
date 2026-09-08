---
phase: 45-post-auth-restore-subscription
plan: 05
subsystem: testing
tags: [requirements, traceability, documentation, subscriptions, entitlements]

# Dependency graph
requires:
  - phase: 45-post-auth-restore-subscription
    provides: "45-01 through 45-04: the shipped route, its two proof checks, the three outcomes, the cap, and the four departures each plan recorded"
  - phase: 43-post-webhooks-app-store
    provides: APPLEHOOK-01, the requirement block D-09 amends, and 43 D-19's owner rule
  - phase: 40-post-auth-upgrade-anonymous
    provides: the forward flag on the restore_subscription operation label, open since 2026-09-02
provides:
  - "Six dated flagged conflicts against 10-restore-subscription.md, each by line, under RESTORE-01"
  - "RESTORE-02's record that the whole surface gate is D-01's 403 and D-02's proof_rejected"
  - "The D-09 amendment under APPLEHOOK-01, with the third mirror in services/subscriptions.py"
  - "The answered operation-label flag: no label is needed, and the migration is not edited"
  - "The accepted Play-read exposure, the two standing store facts, and four open product questions"
  - "The Phase 45 outcome paragraph and the D-09 decision line in STATE.md"
  - "The four marked ROADMAP success criteria, each naming what answers it"

affects: [46-post-auth-sign-out-all, phase 45 verification, v2.0 milestone close]

actuals:
  tokens: 17000
  tasks: 2
  commits: 5

tech-stack:
  added: []
  patterns:
    - "A divergence is recorded, never resolved by editing the specification (D-14, on the 43 D-27 precedent)"
    - "A stale sentence in an earlier phase's record is corrected in the new dated paragraph, never edited in place"

key-files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "D-08 is counted at both ends, where Phase 41's matching lock-order item was counted only at the second; the difference is stated rather than smoothed over, because D-08 also drops the store-subscription serialization the brief asks for"
  - "The e2e suite's blindness to a deferred foreign key is recorded under RESTORE-01 as an operational fact and in neither count, because it is a limit of this project's tests and not a divergence from the specification"
  - "The 45-01 F841 narrowing and the 45-02 _get refactor are summary-level departures and are NOT written into REQUIREMENTS.md: both were closed inside the phase and neither survives as a property of the shipped route"
  - "The answered operation-label flag does NOT close SIGNOUT-01's matching flag; Phase 46 must decide for sign_out_all on its own terms, and the reasoning is a precedent rather than an answer"
  - "The traceability RESTORE row is written by hand, because requirements mark-complete reports table_unmatched for the range-form row 'RESTORE-01 … RESTORE-02'"
  - "STATE.md counters are read from disk and written, never incremented, with the counting note the file's own convention requires"

patterns-established:
  - "Correct-in-place-forward: a stale count inside an earlier phase's sentence is left as written and corrected in the current phase's dated paragraph, where a later reader finds it"
  - "Name the ranking honestly: an accepted exposure is compared with its siblings on both axes rather than filed as the narrowest or the widest"

requirements-completed: [RESTORE-01, RESTORE-02]

coverage:
  - id: D1
    description: "Every departure this phase made from 10-restore-subscription.md is a dated flagged conflict in REQUIREMENTS.md, by line, and the brief itself is unedited"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "test \"$(grep -c '10-restore-subscription.md' .planning/REQUIREMENTS.md)\" -ge \"6\" (reads 16)"
        status: pass
      - kind: other
        ref: "sha256sum -c over 10-restore-subscription.md and SHARED-INVARIANTS.md"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-09's change to the ingestion owner rule is recorded under APPLEHOOK-01 and in STATE.md Decisions, so a later phase does not read it as a regression"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "grep -c 'D-09' .planning/REQUIREMENTS.md (>= 1) and grep 'An owner, once set on' .planning/STATE.md"
        status: pass
    human_judgment: false
  - id: D3
    description: "The Phase 40 forward flag on the restore_subscription operation label is answered: no label is needed"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "grep 'ANSWERED AND CLOSED by Phase 45 (D-13)' .planning/REQUIREMENTS.md"
        status: pass
    human_judgment: false
  - id: D4
    description: "The unbounded Play read is recorded as accepted, not filed as a new defect, and names the v2.1 gateway contract as what closes it"
    requirement: RESTORE-01
    verification:
      - kind: other
        ref: "grep 'FLAGGED, NOT COUNTED (Phase 45 D-05' .planning/REQUIREMENTS.md"
        status: pass
    human_judgment: false
  - id: D5
    description: "The ROADMAP success criteria for Phase 45 are marked with the decision that answers each, the 45-05 checkbox is flipped, and the counter reads 5/5"
    verification:
      - kind: other
        ref: "grep '5/5 plans executed' and '- [x] 45-05-PLAN.md' in .planning/ROADMAP.md"
        status: pass
    human_judgment: false
  - id: D6
    description: "The three suite counts recorded in STATE.md come from a green run made in this plan, and ruff is clean"
    verification:
      - kind: other
        ref: "uv run pytest -q (1246), uv run pytest -m e2e -q (321), uv run pytest -m schema -q (222), uv run ruff check src tests"
        status: pass
    human_judgment: false
  - id: D7
    description: "The prohibition: a divergence from the binding brief is not resolved by editing the brief; the record shows both what this project chose and what the specification says"
    verification: []
    human_judgment: true
    rationale: "The mechanical half is measured — both specification files are byte-identical, proved by sha256sum. Whether each entry states the divergence fairly, and whether a later reader can reconstruct the choice from it, is a judgment no test can make."

# Metrics
duration: 24 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 05: The dated RESTORE and APPLEHOOK amendments Summary

**Six departures from `10-restore-subscription.md` written into REQUIREMENTS.md by line, the operation-label flag answered and closed, D-09 recorded where a later phase will find it — and the brief itself byte-identical.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-09-08T02:11:39Z
- **Completed:** 2026-09-08T02:35:00Z
- **Tasks:** 2
- **Files modified:** 3 (0 created, 3 modified)

## Accomplishments

- **Six flagged conflicts under RESTORE-01**, each naming the brief's own lines: D-02 the proof-only surface gate (`:43`), D-03 the anonymous destination (`:50`/`:68`), D-04 the locally verified Apple proof (`:60`/`:71`/`:134`), D-07 the reused webhook grant writer (`:77`/`:84`/`:90`), D-08 the conditional owner UPDATE with no subscription lock (`:63`), and D-10 the one-move-per-UTC-month cap (`:48`/`:49`/`:112`). Each states what shipped, what it costs, and how reversible it is.
- **The Phase 40 forward flag is ANSWERED AND CLOSED: no label is needed.** Restore is not challenge-bearing and writes no audit row, so `core.auth_challenges.operation` — the only surviving consumer — never wanted it. The single migration is not edited.
- **D-09 under APPLEHOOK-01**, naming what it amends (43 D-19 and 43-03's "an owner is added, never cleared"), what it does not change (an unowned row is still attributed by the carried token), and the third mirror in `services/subscriptions.py::ingest` that neither CONTEXT nor the plan had located.
- **The eight untriggered brief result codes**, each by name with the decision that removed its trigger, plus the full inventory of obligations already dead before this phase began — the route registry, the two foundation seams, the audit row, the eleven rate-limit entries, the provider budgets, coalescing, the freshness bound and the attempt-identity retry — each with the phase and decision that removed it and the brief lines a later reader must not read as unmet work.
- **The accepted Play-read exposure**, ranked honestly on both axes rather than filed as the narrowest or the widest, closing with the v2.1 gateway contract.
- **Four open product questions**, each verified against the source before it was written: Family Sharing (`grep -rn 'inAppOwnershipType' src/ tests/` returns nothing), `linkedPurchaseToken` (parsed at `google_play.py:82`, never read), the Google `stage` set, and the migration comment at `:136` that D-10 made false.
- **STATE.md and ROADMAP.md**: the D-09 decision line in the v2.0 block, the Phase 45 outcome paragraph with `1246 / 321 / 222` measured in this plan, and the four success criteria marked against what answers each.

## Task Commits

1. **Task 1: Amend RESTORE-01, RESTORE-02 and APPLEHOOK-01** — `935edbb` (docs)
2. **Task 2: Record D-09 in STATE.md and mark the ROADMAP criteria** — `c63f54b` (docs)
3. **Task 2 follow-on: the traceability row and the conflict-count cell** — `ae410df` (docs)

**Plan metadata:** `9193672` carries this file, and `beb9b02` appends the self-check with the progress-table row `roadmap update-plan-progress 45` re-derived from disk. Five commits in all.

## Files Created/Modified

- `.planning/REQUIREMENTS.md` — the Phase 45 header paragraph; sixteen new blockquote entries under RESTORE-01, two under RESTORE-02 and one under APPLEHOOK-01; both requirement checkboxes flipped; the counts paragraph re-derived; the traceability row and the conflict-count cell updated
- `.planning/STATE.md` — the D-09 line in § Accumulated Context's v2.0 block, the Phase 45 outcome paragraph with its counting note, the frontmatter counters and the Current Position
- `.planning/ROADMAP.md` — the four Phase 45 success criteria marked, `- [x] 45-05-PLAN.md`, and `**Plans:** 5/5 plans executed`

## Decisions Made

- **D-08 is counted at both ends; Phase 41's matching item was counted only at the second.** Phase 41 D-13 met the same clash — a brief asking for a lock tier ahead of the grant locks, against § "Locks and transactions" — and filed it as a precedence resolution rather than a conflict. D-08 does more than resolve precedence: it also drops the store-subscription serialization the brief asks for, and `45-CONTEXT.md` names it a flagged conflict. The inconsistency between the two treatments is **stated in the record** rather than smoothed over by copying Phase 41's.
- **The e2e suite's blindness to a deferred foreign key is recorded, and in neither count.** It is a limit of this project's own tests, not a divergence from the specification, so it joins the file's existing "operational facts, recorded because none is a divergence" category. The rule a later plan must carry is written explicitly: never read an e2e pass as evidence about a deferred constraint.
- **The answered operation-label flag does not close SIGNOUT-01's matching flag.** A first draft of the counts paragraph said it did. That was wrong: `sign_out_all` is a different label on a different route, and Phase 46 must decide for itself. The sentence now says the reasoning is a precedent, never an answer.
- **A stale sentence in the counts paragraph is corrected forward, not edited.** That paragraph still reads *"none of the ten surviving flagged conflicts is against text either removal touched"* — a count current on 2026-09-03 and stale at every reading since, which Phases 42, 43 and 44 each left. The claim still holds at thirty; only the number is wrong. It is left as written, per the convention this file uses, and corrected in the Phase 45 paragraph where a later reader meets it first.
- **The Play-read exposure is not ranked as the narrowest.** Phase 44 called its own residual the narrowest of five, because an unverified push costs local computation only. This one costs a real network call to Google, so it is narrower than the two webhook residuals on credentials and wider on cost. Both axes are stated instead of one.
- **STATE.md counters were counted, not advanced.** `state advance-plan` and `state update-progress` were not run: the plan requires the counts be read from disk, and this plan's own summary does not exist when the counters are written. 115 PLAN files and 114 SUMMARY files were counted at 2026-09-08T02:11Z, the frontmatter already carried both, and `completed_plans` is written as 115 because this summary is the hundred-and-fifteenth.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] The traceability table still read `Pending` and carried a stale conflict count**

- **Found during:** Task 2, after the requirement checkboxes were flipped in Task 1
- **Issue:** `.planning/REQUIREMENTS.md` § Traceability holds two cells the plan's `<action>` does not name: the RESTORE status row, still reading *"Pending"*, and the *"Flagged conflicts against the binding specification, unresolved"* cell, still reading **Twenty-four**. Leaving them would have made the file disagree with itself in two places — a header paragraph claiming thirty conflicts and two requirements met, against a table claiming twenty-four and pending — which is exactly the ambiguity T-45-12 exists to prevent.
- **Fix:** the RESTORE row rewritten to `Complete`, naming what each requirement carries and the two forward flags answered; the count cell updated to **Thirty** in the dated-correction style Phases 42, 43 and 44 each used, naming the six conflicts by line and the five invariant sections re-read.
- **Files modified:** `.planning/REQUIREMENTS.md`
- **Verification:** `grep -c 'Flagged conflicts against the binding specification, unresolved | \*\*Thirty'` reads 1; the row reads `Complete`; all four of Task 1's `<verify>` blocks re-run and still pass.
- **Committed in:** `ae410df`

**2. [Rule 3 - Blocking] `requirements mark-complete` cannot match this file's range-form traceability row**

- **Found during:** Task 2
- **Issue:** `gsd-tools query requirements.mark-complete RESTORE-01 RESTORE-02` returned `{"updated": false, "table_unmatched": ["RESTORE-01", "RESTORE-02"]}`. The row is written as `| RESTORE-01 … RESTORE-02 | Phase 45 | … |`, a range with an ellipsis, and the verb matches a row per id. `requirements ready-ids` reported 2 of 2 ready, so readiness was not the blocker.
- **Fix:** the row is written by hand, in the same form Phases 41 to 44 wrote theirs. No verb behaviour was changed and no row form was invented.
- **Files modified:** `.planning/REQUIREMENTS.md`
- **Verification:** the row reads `Complete`; both checkboxes read `- [x]`.
- **Committed in:** `ae410df`

### Departures from the plan text (not auto-fixes)

**3. The plan says "Mark ROADMAP criteria 2, 3 and 4 answered" in CONTEXT D-13; the plan's own Task 2 says all four.** All four are marked. Criterion 1 is answerable — the three outcomes across both stores are executed cases — so leaving it unmarked would have been the odd choice.

**4. `roadmap update-plan-progress` was not used to flip the checkbox.** The verb counts PLAN against SUMMARY files on disk, and this plan's summary does not exist during Task 2, so the verb would have written `4/5` and left the box unticked. The line and the counter are written directly, and the verb is run after this summary lands as the disk-truth check — recorded in § Self-Check.

**5. Four departures the prior waves recorded are deliberately NOT in REQUIREMENTS.md.** Each was judged against one question: does it survive as a property of the shipped route? **(a) 45-01's uncalled `read_purchase` and `resolve_user` (ruff F841)** — a wave-order artifact. 45-03's adoption branch calls both, so the reads exist today and the slice narrowing left no trace. **(b) 45-01's `google_play` refusal arm** — retired by 45-02 and its ledger entry closed. **(c) 45-02's `_get` no longer classifying transport failures** — an internal refactor with no clause in the brief; what a client sees is D-05, which *is* recorded. The webhook's answer is byte-identical. **(d) 45-02's unlisted `dependencies.py` edit** — plan-text bookkeeping, not a divergence from the specification. **Three others do survive and ARE recorded:** 45-01's `RestoreProviderUnknown` standing alone (a named null result against § "Errors", in neither count) and its `transaction_without_original_id` refusal (under RESTORE-02); 45-03's third D-09 mirror (under APPLEHOOK-01); and 45-04's writer fix (under RESTORE-01, with the webhooks' unchanged behaviour stated).

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking), plus 3 documented departures from the plan text.
**Impact on plan:** No scope creep. Every file touched is one of the three the plan declares. Deviation 1 is the load-bearing one: without it the file would have asserted two different conflict counts and two different requirement states.

## Threat Flags

None. This plan installs no package, touches no source file and adds no network endpoint, auth path or schema change, so **T-45-SC stands accepted** as the plan's register states.

The register's own dispositions:

- **T-45-12** (a departure that is not written down is one a later phase silently re-decides) — **mitigated.** Every departure is a dated, line-referenced entry, and both specification files are byte-identical, proved by `sha256sum -c`. A reader now sees both what the specification says and what this project chose.
- **T-45-06** (the unbounded Play read) — **accepted and recorded** under RESTORE-01 with what bounds it, what closes it, and how it compares with its five siblings on both axes.
- **T-45-13** (Apple Family Sharing) — **transferred to the developer**, in the requirement record, with the reason it matters under D-10 and the measured fact that `inAppOwnershipType` is read nowhere in this repository.

The plan's `must_haves.prohibitions` entry — that a divergence must not be resolved by editing the brief — moves from `unverified` to **verified for its mechanical half** by the `sha256sum` gate, and stays a judgment for the rest: see coverage `D7`.

## Known Stubs

None. `src/` and `tests/` are untouched by this plan, and `.planning/WINDOWS.md` gained no entry: no stub was written, no test was skipped, and every `<verify>` block of both tasks was executed rather than deferred.

## Issues Encountered

**The `mark-complete` verb and this file's row form disagree, and the disagreement is older than this phase.** Every endpoint block in § Traceability is written as a range — `| APPLEHOOK-01 … APPLEHOOK-02 |`, `| PLAYHOOK-01 … PLAYHOOK-03 |` — and `requirements mark-complete` matches one row per id, so it reports `table_unmatched` for every phase in this file, not only this one. Phases 41 to 44 each wrote their row by hand without recording why. It is recorded here so the next phase does not spend the same minutes on it. Nothing is broken: `requirements ready-ids` works, and the checkbox half of the verb's job was done by the same edit that wrote the amendment.

No authentication gates. No `git stash` was run at any point in this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Phase 45 is executed and ready for verification.** All five plans have summaries. The phase checkbox itself is deliberately **not** marked and `phase.complete` was **not** run: the orchestrator owns phase completion after verification.
- **Phase 46 inherits three things from this record.** The `sign_out_all` operation-label flag is still open and is Phase 46's to decide; RESTORE-01's reasoning is a precedent for it and not an answer. SIGNOUT-02's fail-closed half is untouched by anything this phase did. And the counts a Phase 46 amendment starts from are **thirty and forty**, not twenty-four and thirty-three.
- **Four open product questions are on the developer's desk**, not in the backlog: Family Sharing against D-10's one move a month is the sharpest, and it should be decided before an iOS app ships.
- Flagged assumption A2 stands for both stores: no app exists on either platform, so no real store artifact has reached this deployment. The first real refusal from either store is authoritative over anything in this repository.

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*

## Self-Check: PASSED

- All three modified files exist on disk and carry this plan's changes; no file was created by this plan.
- All four commits (`935edbb`, `c63f54b`, `ae410df`, `9193672`) are in the log.
- Both tasks' `<verify>` blocks re-run and passing. Task 1: `RESTORE-01` occurs 9 times (≥ 2), `10-restore-subscription.md` 16 times (≥ 6), `D-09` 44 times (≥ 1), and `sha256sum -c` confirms `10-restore-subscription.md` and `SHARED-INVARIANTS.md` byte-identical to their pre-phase state. Task 2: `Phase 45 outcome` occurs exactly once; `uv run pytest -q` 1246 passed, `uv run pytest -m e2e -q` 321 passed, `uv run pytest -m schema -q` 222 passed, `uv run ruff check src tests` clean — run twice in this plan, before and after the STATE.md write.
- Every acceptance criterion of both tasks re-checked against the file on disk, not against the intent: the six named conflicts each carry a line reference; RESTORE-02 carries the two-refusal gate; APPLEHOOK-01 carries the dated D-09 amendment naming 43 D-19 and 43-03; the eight untriggered codes are listed by name with the decision that removed each; the operation-label flag reads "no label is needed"; the Play-read entry names the v2.1 gateway contract; and the four open questions each appear once in the record.
- **Tracking writes confirmed on disk, not merely issued.** `REQUIREMENTS.md`: both checkboxes read `- [x]`, the header carries the Phase 45 paragraph, and the traceability row reads `Complete`. `STATE.md`: `stopped_at: Completed 45-05-PLAN.md`, `completed_plans: 115`, the D-09 decision line, and one Phase 45 outcome paragraph. `ROADMAP.md`: all four criteria marked, `- [x] 45-05-PLAN.md`, `**Plans:** 5/5 plans executed`, and the progress table row re-derived from disk by `roadmap update-plan-progress 45`, which reports `plan_count: 5, summary_count: 5`.
- **Phase 45 itself is NOT marked complete and `phase.complete` was not run.** The verb reports `status: In Progress, complete: false`, which is correct: the orchestrator owns phase completion after verification.
