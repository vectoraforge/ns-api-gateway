---
phase: 38-post-auth-sync
plan: 05
subsystem: planning-record
tags: [requirements, roadmap, audit, flagged-conflicts, amendment]

# Dependency graph
requires:
  - phase: 38-post-auth-sync
    provides: "38-04 — § Audit deleted in full from SHARED-INVARIANTS.md, the § Errors core.auth_event_result clause deleted, the two live non-audit rules relocated into § Fail-closed defaults"
  - phase: 37.1-machine-generated-code-refactoring
    provides: "D-01 — the deletion that flagged SYNC-03, SIGNOUT-02, APPLEHOOK-02 and PLAYHOOK-03 forward, and the FOUND-05 flagged conflict this plan resolves"
provides:
  - "The dated SYNC-03 amendment: option (b), 2026-09-01, with the grounds and what exists in its place"
  - "Dated Phase 38 notes on SIGNOUT-02, APPLEHOOK-02 and PLAYHOOK-03, each naming which half is settled and which half still binds"
  - "The FOUND-05 flagged conflict resolved by removal, kept as a record with the removed obligation still quoted"
  - "The flagged-conflicts count at five in all three places it is stated, and the known-divergence set re-derived at six"
  - "ROADMAP Phase 38 success criterion 4 rewritten from a blocked obligation to what is built"
affects: [38-06, 39-users-me, 43-webhook-app-store, 44-webhook-google-play-rtdn, 46-sign-out-all]

actuals:
  tokens: 12000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A flagged conflict is resolved by rewriting its entry as resolved-by-removal, never by deleting the entry — the divergence's history outlives the divergence"
    - "A requirement whose mechanism was deleted but whose subject survives is amended, not withdrawn; the amended text states what is actually owed"

key-files:
  created:
    - .planning/phases/38-post-auth-sync/38-05-SUMMARY.md
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md

key-decisions:
  - "SYNC-03 is amended rather than withdrawn: its subject was attempt telemetry, and attempt telemetry survives as the RequestLoggingMiddleware `request` line plus one WARNING per rejection"
  - "The three siblings are amended in halves, never wholesale — APPLEHOOK-02 and PLAYHOOK-03 are explicitly NOT closed, because § 'Global deletions' survives the removal untouched"
  - "Phase 37.5's dated paragraphs stating the count as six and the divergence set as seven were left as that phase's record; the new numbers are stated in the Phase 38 paragraph, which names them as superseding"
  - "Three table cells outside the plan's stated scope were corrected because this plan's own edits made them false — see Deviations"

patterns-established:
  - "Self-referencing line numbers (`:50`, `:75`) in REQUIREMENTS.md drift whenever the header block grows; an amending plan must re-derive them"

requirements-completed: [SYNC-03]

coverage:
  - id: D1
    description: "SYNC-03 no longer describes a durable audit.auth_events row as an outstanding obligation; it records the decision, names option (b), dates it 2026-09-01, and names what actually exists in its place"
    requirement: SYNC-03
    verification:
      - kind: other
        ref: "grep -c 'BLOCKED' .planning/REQUIREMENTS.md → 0; the entry names `amended`, `(b)` and `2026-09-01`, and the requirement line now states the middleware `request` line and the per-rejection WARNING"
        status: pass
    human_judgment: true
    rationale: "Whether the rewritten requirement states what is owed without widening or narrowing it is a reading judgement; the greps only prove the old text is gone."
  - id: D2
    description: "APPLEHOOK-02, PLAYHOOK-03 and SIGNOUT-02 each carry a dated Phase 38 note stating exactly which half is settled and which half still binds"
    verification:
      - kind: other
        ref: "Each of the three notes contains a 'What is settled' / 'What is NOT settled and still binds' pair (SIGNOUT-02's as prose); both callback notes name § 'Global deletions' and the words 'NOT closed'"
        status: pass
    human_judgment: true
    rationale: "T-38-16 — an over-broad amendment closing APPLEHOOK-02/PLAYHOOK-03 entirely is a wording failure a grep cannot catch."
  - id: D3
    description: "SIGNOUT-01 and SIGNOUT-02's fail-closed half are untouched and still binding"
    verification:
      - kind: other
        ref: "git diff .planning/REQUIREMENTS.md | grep '^-' | grep -c 'SIGNOUT-01' → 0 across every commit; SIGNOUT-01's line and SIGNOUT-02's fail-closed clause are byte-identical, and the new note states the fail-closed half is untouched and fully binding"
        status: pass
    human_judgment: false
  - id: D4
    description: "The flagged-conflicts count drops from six to five and the FOUND-05 § Audit entry is recorded as resolved by removal rather than deleted without trace"
    verification:
      - kind: other
        ref: "grep -inE '\\*\\*six\\.?\\*\\*|count is six' → no output; the header paragraph reads Five, the treatment row reads **Five.**, and FOUND-05's paragraph survives quoting *\"Every on-path attempt writes exactly one durable `audit.auth_events` row…\"* (grep → 1)"
        status: pass
    human_judgment: false
  - id: D5
    description: "ROADMAP Phase 38 success criterion 4 describes what is built, and criteria 1 to 3 are unchanged"
    verification:
      - kind: other
        ref: "sed -n '/#### Phase 38/,/#### Phase 39/p' | grep -c 'BLOCKED' → 0; four numbered criteria remain; the whole ROADMAP diff for this task is 1 insertion / 1 deletion, and 'PROF-02' appears 0 times in it"
        status: pass
    human_judgment: false
  - id: D6
    description: "No phase brief under specs/auth-refactor-phases/ is edited, no migration file is touched, and no mutating git command ran against the parent repository"
    verification:
      - kind: other
        ref: "Only read-only `git -C /home/init/native-speaker status --porcelain -- specs/` and `diff --stat -- specs/` were run; the parent still reports the single pre-existing `?? specs/auth-refactor-phases/`. git diff --stat HEAD~3 HEAD lists exactly .planning/REQUIREMENTS.md and .planning/ROADMAP.md"
        status: pass
    human_judgment: false
  - id: D7
    description: "STATE.md is neither modified nor committed, and SYNC-01/SYNC-02 are left unchecked for 38-02"
    verification:
      - kind: other
        ref: "git status reports no modification to .planning/STATE.md at any point; SYNC-01 and SYNC-02 keep their `- [ ]` boxes, and no requirement checkbox anywhere in the file changed"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-09-01
status: complete
---

# Phase 38 Plan 05: The dated SYNC-03 amendment, the three sibling entries, the conflicts count and ROADMAP criterion 4 Summary

**The audit decision is now written where the project's readers look for it — SYNC-03 records a made decision instead of a pending one, the three siblings blocked on the same deleted mechanism each state exactly which half Phase 38 settles and which half still binds them, and for the first time in this file a flagged conflict is resolved rather than added: the count reads five, and the resolved one keeps its history.**

## Performance

- **Duration:** ~15 min (approximate — no start epoch was captured at spawn; see Deviations)
- **Completed:** 2026-09-01T08:20Z
- **Tasks:** 3, all `type="auto"`, no checkpoint
- **Files modified:** 2, both inside `ns-api-gateway/.planning/`

## Accomplishments

- **SYNC-03 rewritten to what is actually owed** and given a four-paragraph dated amendment: option **(b)**, 2026-09-01; the grounds stated concretely (the table back in the single initial migration, HMAC-SHA-256 actor hashing with key versioning, the six-key `details` shape, route→operation metadata before the barrier — not warranted for a read-only endpoint's attempt telemetry); D-02's no-success-event decision with the mechanism named (`api/logs.py`'s `RequestLoggingMiddleware`, `app/error_handlers.py::app_error_handler`); and the removal-at-source that plan 38-04 performed.
- **SIGNOUT-02 amended in halves.** The audit half is settled by the same stroke and Phase 46 inherits no audit decision; the standing instruction paragraph above it is explicitly marked as no longer open. The accepted consequence is named rather than glossed: an indeterminate revocation now leaves no durable record of the attempt, only the log lines. **SIGNOUT-01 and the fail-closed half are stated as untouched and fully binding, and neither was reworded.**
- **APPLEHOOK-02 and PLAYHOOK-03 amended only as far as the removal reaches.** Settled: the route→operation-metadata obligation and any audit-row obligation. Not settled, and stated as such in both notes: `SHARED-INVARIANTS.md` § "Global deletions" still forbids wildcard or path-prefix provider-callback membership, the routes are still enumerated individually by exact path and still never on the public allowlist, and PLAYHOOK-03's "second and last member" countability requirement still stands. Both notes say **NOT closed** in those words.
- **FOUND-05's flagged conflict resolved by removal, not deleted.** The paragraph now opens as `FLAGGED CONFLICT — RESOLVED BY REMOVAL by Phase 38 (D-03), 2026-09-01`, still quotes all three obligations the removed § "Audit" used to impose, and adds what is deliberately *not* fixed: `01-foundation.md §4` still states the same obligation in phase form, so a reader reaching the brief first meets an obligation the binding specification no longer carries.
- **The arithmetic re-derived rather than copied.** The header paragraph reads five conflicts and six known divergences, naming the Phase 35 `limits` override as the extra one and stating that both numbers dropped by one because Phase 38 resolved one conflict and added none. The treatment-table row reads **Five.** and names the resolved item with its date, in the style the row already used for Phase 37.4's two non-entries.
- **ROADMAP Phase 38 criterion 4** is one testable sentence about what is built, in the register of criteria 1–3.

## Task Commits

1. **Task 1 — the SYNC-03 amendment and the three sibling entries** — `12cd458` — `.planning/REQUIREMENTS.md` (+31 / −7)
2. **Task 2 — the flagged-conflicts arithmetic and the FOUND-05 resolution** — `a9db5e5` — `.planning/REQUIREMENTS.md` (+11 / −7)
3. **Task 3 — ROADMAP Phase 38 success criterion 4** — `c3edb9d` — `.planning/ROADMAP.md` (+1 / −1)

**Plan metadata:** `docs(38-05): complete the SYNC-03 amendment and roadmap-criterion plan` — this summary plus the `roadmap.update-plan-progress` bookkeeping (Phase 38 `2/6 → 3/6`, this plan's checkbox, the progress-table row). `.planning/STATE.md` is **not** in that commit: the orchestrator owns it for this wave.

## Acceptance criteria — measured

| Criterion | Result |
|---|---|
| `grep -c 'BLOCKED' .planning/REQUIREMENTS.md` | **0** |
| `grep -c 'Amended again by Phase 38' .planning/REQUIREMENTS.md` | **1** |
| SYNC-03 names `2026-09-01`, `amended`, option `(b)` | all three present; the two-option choice and the blocked lead are gone |
| `git diff … \| grep '^-' \| grep -c 'SIGNOUT-01'` | **0** |
| SIGNOUT-02 note states the fail-closed half untouched and binding | present, in those words, and SIGNOUT-01 is named in it |
| APPLEHOOK-02 / PLAYHOOK-03 notes name § "Global deletions" and do not claim closure | both; both carry the literal phrase **NOT closed** |
| `grep -inE '\*\*six\.?\*\*\|count is six'` | no output |
| Treatment row | `**Five.**`, § "Audit" item removed from the list and named in the trailing resolved sentence |
| `grep -c 'Last updated: 2026-09-01'` | **1**; exactly one `Previously updated` line survives (2026-08-31), the 2026-08-30 line rotated off as every prior amendment did |
| Removed lines containing `auth_events` | **1** — FOUND-05's old flagged-conflict paragraph; its quoted obligation survives verbatim in the replacement (`grep` → 1), so nothing is lost |
| Phase 38 entry `BLOCKED` count | **0**; four numbered criteria; Goal / Requirements / Depends-on byte-identical |
| ROADMAP removed lines | **1** content line, criterion 4; `PROF-02` appears **0** times in the diff, so Phase 39 is untouched |
| Files changed across the plan | exactly two, both under `.planning/` |
| `.planning/STATE.md` | **not modified, not staged, not committed** |
| Parent repository | no mutating command; still reports only the pre-existing `?? specs/auth-refactor-phases/` |

Cross-checked against the file 38-04 actually edited: `SHARED-INVARIANTS.md` has **0** case-insensitive matches for `audit`, **10** `## ` headings, and § "Global deletions" still present — which is what makes the APPLEHOOK-02 / PLAYHOOK-03 notes true as written.

## Decisions Made

- **Amended, not withdrawn, for SYNC-03.** Withdrawal is for a requirement whose subject stopped existing (SCHEMA-06, the old FOUND-05). SYNC-03's subject — telemetry about attempts — still exists; only the mechanism died. Writing it as withdrawn would have left Phase 38 looking as though it owes no attempt record at all, which is false: it owes the two log lines and now says so.
- **The two callback siblings were amended in halves rather than closed.** The tempting shortcut was one note per requirement saying "settled by Phase 38". It would have been wrong: the removal touched § "Audit", not § "Global deletions", and phases 43 and 44 still owe exact-path enumeration. Both notes state the surviving prohibition before anything else a planner might skim.
- **Phase 37.5's dated paragraphs were left alone.** They state the count as six and the divergence set as seven. Editing a dated record to match today's numbers is how a record loses its authority; the Phase 38 paragraph states the new numbers and says explicitly that 37.5 derived the old ones, so the progression is legible.
- **The `01-foundation.md §4` restatement was reported, not fixed.** Phase briefs are marked verbatim and are not this plan's to edit; the note names the hazard so a reader who meets the brief first knows which document wins.

## Deviations from Plan

### 1. [Rule 1 — Bug] Three table cells became false as a direct result of Task 1, and were corrected

- **Found during:** Task 1, after the sibling amendments landed.
- **Issue:** Task 2's action ends *"Do not touch any other requirement, table row or count."* But three cells stated as present fact something this plan's own edits falsified: the requirement-map row *"SYNC-03 blocked on a Phase 38 decision"*; the row *"SIGNOUT-02's audit half blocked on a Phase 46 decision"*; and the treatment row **Flagged forward — the owning phase decides**, which still listed all four siblings as awaiting their owning phase. That last one is the exact failure D-04 exists to prevent — a Phase 43 planner scanning the treatment table would read that APPLEHOOK-02's decision is still theirs to make.
- **Fix:** Each cell gained a dated clause naming what Phase 38 settled and, for the callbacks, what still binds. No count changed, no status changed, no checkbox moved, and no row was rewritten wholesale.
- **Files modified:** `.planning/REQUIREMENTS.md` only.
- **Committed in:** `12cd458`.

### 2. [Rule 1 — Bug] Three self-referencing line numbers drifted and were re-derived

- **Found during:** Task 2.
- **Issue:** Adding the Phase 38 blockquote to the header block shifted every line below it by two. `:48` (cited twice, for the Phase 35 `limits` override at the SCHEMA-06 note) and `:73` (the wire-contract divergence table under FOUND-01) both stopped resolving.
- **Fix:** Re-derived by grep and corrected to `:50` and `:75`. Two of the three sit inside Phase 37.5's dated paragraphs; this is a pointer-only correction of the kind Phase 37.5 itself made to FOUND-01, and no claim in those paragraphs was altered.
- **Committed in:** `a9db5e5`.

### 3. [Not a deviation, reported] `ROADMAP.md` Phase 46 criterion 3 is now stale and was deliberately left alone

Phase 46's success criterion 3 is still the **BLOCKED** paragraph reading *"requires a mechanism Phase 37.1 deleted. Phase 46 must decide."* After this plan, `REQUIREMENTS.md` SIGNOUT-02 says that decision is settled by removal — so the roadmap and the requirements now disagree about Phase 46. Task 3 forbids editing any other phase entry (*"Every other phase entry in the file is unchanged"*), so it was not touched. **It is a one-sentence fix and it belongs to whoever next edits Phase 46's roadmap entry.** `grep -c 'BLOCKED' .planning/ROADMAP.md` therefore returns **1**, not 0; the plan's own verification asks only that no occurrence remain in the Phase 38 entry, which holds.

### 4. [Not a deviation, recorded] State-file handlers were deliberately not run

The orchestrator owns `.planning/STATE.md` for this wave and writes it after the wave completes, so `state.advance-plan`, `state.update-progress`, `state.record-metric`, `state.add-decision` and `state.record-session` were all skipped — every one of them writes STATE.md. `requirements.mark-complete` was also skipped: Task 1 says *"Change no requirement checkbox in this task — the boxes are handled by plan 38-06 once the suite is green"*, and SYNC-01/SYNC-02 belong to 38-02, still in flight. `requirements-completed: [SYNC-03]` in this summary's frontmatter records that SYNC-03's decision work is done; **its checkbox is still `- [ ]` by design.**

---

**Total deviations:** 2 auto-fixed (both Rule 1, both staleness this plan's own edits caused), 2 recorded non-deviations.
**Impact on plan:** none on scope. Three table cells and three line-number pointers were corrected beyond the plan's letter, all inside the file the plan already owns.

## Issues Encountered

- **The first draft of the SYNC-03 amendment quoted the word it was removing.** The sentence read *"it carried a **BLOCKED** lead"*, which left `grep -c 'BLOCKED'` at 1 and would have failed the acceptance criterion for a purely cosmetic reason. Caught by running the criterion rather than assuming it; reworded to *"a lead declaring itself blocked on a deleted mechanism"*. Worth recording because the file's convention of quoting the text it supersedes collides with greps that test for that text's absence.
- **No start epoch was captured at spawn**, so the duration above is estimated from the surrounding commits rather than measured.

## Threat Flags

None. This plan changed no code and no security surface. The three threats in the plan's register were mitigation-by-wording and are covered above: **T-38-14** (a broad SIGNOUT edit relaxing a revocation rule) — SIGNOUT-01 appears in zero removed lines and the fail-closed sentence is present; **T-38-15** (resolving a conflict by deleting its record) — FOUND-05's paragraph is rewritten as resolved, still quoting the removed obligation; **T-38-16** (over-broad closure of the callback requirements) — both notes name the surviving § "Global deletions" prohibition and say **NOT closed**.

## Known Stubs

None.

## Next Phase Readiness

- **38-06 can check the boxes.** SYNC-03's text is final and no longer describes an unbuilt mechanism; SYNC-01 and SYNC-02 are untouched and still belong to 38-02.
- **Phases 43, 44 and 46 must read their notes as halves, not verdicts.** Each now says what Phase 38 settled *and* what still binds. The one thing 43 and 44 still owe is exact-path enumeration under § "Global deletions".
- **Two open items a later reader will meet:** `ROADMAP.md` Phase 46 criterion 3 still reads BLOCKED (Deviation 3), and `01-foundation.md §4` still states the audit obligation in phase form because phase briefs are verbatim (recorded inside FOUND-05).
- **The 38-04 concern still stands:** `specs/auth-refactor-phases/` is untracked in the parent working tree, so the removal that makes every claim in this plan true exists only on the filesystem until the developer commits it.

## Self-Check: PASSED

- `.planning/REQUIREMENTS.md` — FOUND, modified and committed in `12cd458` and `a9db5e5`.
- `.planning/ROADMAP.md` — FOUND, modified and committed in `c3edb9d`.
- `.planning/phases/38-post-auth-sync/38-05-SUMMARY.md` — FOUND (this file).
- Commits `12cd458`, `a9db5e5`, `c3edb9d` — all three found in `git log`, all on `gsd/phase-38-post-auth-sync`.
- No commit in this plan deleted a tracked file (`git diff --diff-filter=D HEAD~3 HEAD` — empty).

---
*Phase: 38-post-auth-sync*
*Completed: 2026-09-01*
