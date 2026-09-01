---
phase: 38-post-auth-sync
plan: 04
subsystem: auth
tags: [specification, audit, invariants, fail-closed]

# Dependency graph
requires:
  - phase: 37.1-machine-generated-code-refactoring
    provides: "D-01 — deletion of audit.auth_events, its writer and every call site; SYNC-03 flagged forward for Phase 38 to decide"
  - phase: 37.3-machine-generated-code-refactoring-part-2
    provides: "D-02/D-06 — deletion of the core.auth_event_result enum and of _reject/auth_rejected in favour of one WARNING per rejection from the shared handler"
  - phase: 36-rebind-identity
    provides: "D-15 — removal of the hand-rolled RejectionCounter, which is why the bounded-cardinality counter metric does not survive the relocation"
provides:
  - "SHARED-INVARIANTS.md with § Audit deleted in full and every audit-row obligation struck (D-03)"
  - "The two live non-audit rules relocated into § Fail-closed defaults — one structured security-log line per rejection, and no per-rejection database row from admission-phase rejections"
  - "Deletion of the § Errors core.auth_event_result clause, whose named type no longer exists"
  - "The deliberate absence of a new flagged-conflict entry: no surviving invariant text is left to conflict with"
affects: [38-05, 39-users-me, 43-webhook-app-store, 44-webhook-google-play-rtdn, 46-sign-out-all]

actuals:
  tokens: 3200
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Remove the invariant rather than carry a permanent flagged conflict (precedent: Phase 37.4's wire-contract removal)"

key-files:
  created:
    - .planning/phases/38-post-auth-sync/38-04-SUMMARY.md
  modified:
    - /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md

key-decisions:
  - "option-a — § Audit deleted entirely; the two surviving non-audit rules relocated into § Fail-closed defaults rather than left under a heading promising a mechanism that no longer exists"
  - "The § Errors core.auth_event_result clause is deleted: the enum was removed by Phase 37.3, and its live half (an internal result is never less specific than the returned class) is already covered by the anti-oracle rule directly above it"
  - "The bounded-cardinality counter metric does not come along — Phase 36 D-15 already removed it, so relocating it would have re-created an obligation this project deliberately dropped"
  - "No flagged-conflict entry added for this edit (D-03); resolving the already-recorded FOUND-05 conflict is plan 38-05's work"

patterns-established:
  - "Spec edits in the parent working tree are made but never committed by an executor: the developer commits /home/init/native-speaker/specs/ themselves"

requirements-completed: [SYNC-03]

coverage:
  - id: D1
    description: "SHARED-INVARIANTS.md contains no clause requiring an audit.auth_events row, an audited attempt path, route→operation metadata readable before the barrier, an actor_subject_hash, or a details shape"
    requirement: SYNC-03
    verification:
      - kind: other
        ref: "grep -icE 'auth_events|actor_subject_hash|audited attempt|audit row|auth_event_result' /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md  → 0 (case-insensitive grep for 'audit' anywhere in the file also returns no match)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The non-audit substance of the two mixed clauses survives in § Fail-closed defaults: a rejection still leaves exactly one structured security-log line, and admission-phase rejections still write no per-rejection database row"
    requirement: SYNC-03
    verification:
      - kind: other
        ref: "diff -u of the pre-edit copy against the edited file — the two surviving rules appear as the only added lines, quoted verbatim in § Surviving rules below"
        status: pass
    human_judgment: true
    rationale: "Whether the relocated wording preserves the original obligation without widening or narrowing it is a reading judgement, not something a grep can settle — T-38-13 in the plan's threat register exists for exactly this risk."
  - id: D3
    description: "The phase briefs under specs/auth-refactor-phases/ are unedited and byte-identical"
    verification:
      - kind: other
        ref: "md5sum of all 13 files in specs/auth-refactor-phases/ before and after — the 12 phase briefs are unchanged; only SHARED-INVARIANTS.md differs (1ec2109… → 07dbf43…)"
        status: pass
    human_judgment: false
  - id: D4
    description: "No new flagged-conflict entry was added for this edit (D-03)"
    verification:
      - kind: other
        ref: "REQUIREMENTS.md untouched by this plan — git status in ns-api-gateway shows no modification to .planning/REQUIREMENTS.md"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-09-01
status: complete
---

# Phase 38 Plan 04: Strike the audit invariants from the binding specification Summary

**§ "Audit" deleted in full from `SHARED-INVARIANTS.md` along with the § "Errors" `core.auth_event_result` clause, with the two live non-audit rules relocated into § "Fail-closed defaults" — the milestone's audit removal is now landed in the document that binds phases 39–46, so no later phase re-discovers a standing conflict.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-09-01T07:54Z
- **Completed:** 2026-09-01T08:00Z
- **Tasks:** 2 (1 checkpoint resolved by the orchestrator before dispatch, 1 auto)
- **Files modified:** 1 (in the parent working tree, uncommitted by design) + this summary

## Accomplishments

- Deleted § "Audit" entirely — the heading plus its five pure-audit clauses (the audited-attempt-path and route→operation-metadata clause, the exactly-one-durable-row clause, the first-class-rejection-rows clause with its bounded reason enumeration, the `succeeded` / `actor_subject_hash` clause, and the `details` shape and redaction clause).
- Deleted the § "Errors" clause naming `core.auth_event_result`, a type Phase 37.3 removed.
- Relocated the two surviving non-audit rules into § "Fail-closed defaults", keeping only their non-audit substance and adding no new rule.
- Left the flagged-conflicts table alone: after this edit there is no surviving invariant text to conflict with, which is the point of removing rather than diverging (D-03).

## Task Commits

1. **Task 1: checkpoint:decision (the exact clause set)** — resolved by the orchestrator before dispatch; no commit. Decision recorded under § "Checkpoint log" below.
2. **Task 2: Strike the audit invariants from the binding specification** — **no commit in this repository by design.** The edited file lives in the parent working tree at `/home/init/native-speaker/specs/`, outside the `ns-api-gateway` submodule; per the plan's `<repository_boundary>` no mutating git command was run against the parent repository. **The developer must commit `specs/auth-refactor-phases/SHARED-INVARIANTS.md` themselves.**

**Plan metadata:** `docs(38-04): complete strike-audit-invariants plan` — this summary only.

## Checkpoint log

**Task 1 (`checkpoint:decision`, gate=blocking) — answered by the developer this session: option-a, and the § "Errors" clause goes.**

- **option-a** — delete § "Audit" entirely and relocate the two surviving non-audit rules into § "Fail-closed defaults". Grounds: no section should survive whose name promises a mechanism that does not exist, and the two live rules belong under a heading whose subject they actually are.
- **The § "Errors" `core.auth_event_result` clause is deleted.** The enum was deleted by Phase 37.3, and its live half is already stated by the anti-oracle rule directly above it.
- The bounded-cardinality counter metric does **not** come along: Phase 36 D-15 already removed it.

## Surviving rules — quoted verbatim in their new § "Fail-closed defaults" home

```
- A rejection leaves exactly one structured security-log line carrying its stable internal result.
- Admission-phase rejections (gateway/backend rate limits, provider budgets, parsing, body-size, content-type, JSON syntax, mode-signal `invalid_request`) write NO per-rejection database row — aggregate telemetry only, naming the limiter that fired.
```

These are the only two added lines in the whole diff.

## Acceptance criteria — measured

| Criterion | Result |
|---|---|
| `grep -icE 'auth_events\|actor_subject_hash\|audited attempt\|audit row\|auth_event_result'` | **0** — and a bare case-insensitive `grep -i audit` over the file also returns no match at all |
| `grep -inE '…\|schema_version, context, verification'` (the plan's wider `<verify>` pattern) | no output |
| `grep -c '^## '` | **11 before, 10 after** — one fewer, as option-a requires |
| Added lines containing `MUST` / `must ` | **0** — no justification needed; the diff adds two rules relocated verbatim in substance and removes fifteen lines |
| Files changed under `specs/` | exactly one, `SHARED-INVARIANTS.md` (md5 `1ec2109…` → `07dbf43…`); all 12 phase briefs byte-identical by md5 |
| Mutating git commands against the parent repository | **none** — only read-only `git -C /home/init/native-speaker status --porcelain -- specs/` and `git diff --stat -- specs/` |
| Flagged-conflict entry added | none; `.planning/REQUIREMENTS.md` untouched by this plan |
| File length | 73 → 64 lines |

## Files Created/Modified

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — the binding specification, with the audit obligations removed. **Edited but NOT committed** (parent working tree, outside this submodule).
- `.planning/phases/38-post-auth-sync/38-04-SUMMARY.md` — this file.

## Decisions Made

- **option-a over option-b:** a section titled "Audit" that mandates no audit is exactly the stale-heading failure this project has repeatedly had to correct. Relocation costs a slightly noisier diff and is worth it.
- **option-a over option-c:** the two rules that survive are live fail-closed rules with nothing to do with auditing, and neither is stated anywhere else in the file. Deleting them would have removed real security substance under cover of an audit cleanup (T-38-13).
- **The counter metric was not relocated.** It was tempting to carry "increments the mandatory bounded-cardinality counter metric" along with the log-line rule since they sit in one sentence, but Phase 36 D-15 removed `RejectionCounter` and PROF-02's amendment already records that rejection rate is derived from the log. Relocating it would have re-created a build obligation this project deliberately dropped.
- **"exactly one" was kept in the relocated log rule.** The source clause said only "keeps its stable internal result in the structured security log"; the checkpoint answer, the plan's `must_haves` truth and REQUIREMENTS.md FOUND-05 all state the rule as *exactly one* structured log line. That is the rule as the project actually holds it, not a new obligation.

## Deviations from Plan

### 1. [Rule 3 — Blocking] The plan's diff-based acceptance criteria could not be satisfied as written

- **Found during:** Task 2, at the pre-edit baseline step.
- **Issue:** `specs/auth-refactor-phases/` is **untracked** in the parent repository (`git -C /home/init/native-speaker status` reports `?? specs/auth-refactor-phases/`). Both `git diff --stat -- specs/` and `git diff -- specs/auth-refactor-phases/SHARED-INVARIANTS.md` therefore produce empty output and can prove nothing about the change. Three acceptance criteria depend on that diff.
- **Fix:** Copied the file to `${TMPDIR:-/tmp}/SHARED-INVARIANTS.before.md` before editing, then used `diff -u` against the temp copy to produce the diff the criteria ask about, and `md5sum` over all 13 files in the directory to prove no phase brief was touched. The temp copy was deleted afterwards. This substitution was pre-identified by the orchestrator and applied as directed.
- **Files modified:** none beyond the planned file.
- **Verification:** `diff -u` output reviewed in full — two added lines, fifteen removed, no other hunk; md5sums of the 12 phase briefs unchanged across the edit.
- **Committed in:** n/a (measurement only).

### 2. [Not a deviation, recorded for the reader] Task 1's checkpoint was resolved before dispatch

The orchestrator put the `checkpoint:decision` to the developer and supplied the answer with the execution prompt, so this executor did not halt at Task 1. The decision is recorded verbatim under § "Checkpoint log".

---

**Total deviations:** 1 auto-fixed (1 blocking — verification method substituted, not scope).
**Impact on plan:** none on the edit itself; only on how the edit was measured. No scope creep.

## Issues Encountered

None. The edit landed in three surgical `Edit` calls and every acceptance measurement passed on the first run.

## User Setup Required

**One manual step, required by the repository boundary.** The developer must commit the spec edit themselves, from the parent working tree:

```
git -C /home/init/native-speaker add specs/auth-refactor-phases/SHARED-INVARIANTS.md
git -C /home/init/native-speaker commit -m "spec(auth): remove the audit invariants (Phase 38 D-03)"
```

Note the whole `specs/auth-refactor-phases/` directory is currently untracked in the parent repository — adding this one file will also raise the question of whether the twelve phase briefs beside it should be tracked. That is the developer's call, not this phase's.

## Next Phase Readiness

- **Plan 38-05 is unblocked and its job is now unambiguous:** it writes the dated SYNC-03 amendment to `.planning/REQUIREMENTS.md` and resolves the FOUND-05 flagged conflict, which as of this edit points at text that no longer exists. It should say so rather than re-describing the conflict.
- **Phases 39, 43, 44 and 46 inherit no audit obligation from the binding specification.** PROF-02, APPLEHOOK-02, PLAYHOOK-03 and SIGNOUT-02's audit half are settled by removal (D-04); their REQUIREMENTS.md entries are 38-05's work.
- **`SIGNOUT-01` and `SIGNOUT-02`'s fail-closed half are untouched** by this edit and stay fully binding.
- **Concern:** the spec edit is uncommitted in an untracked directory. Until the developer commits it, the removal exists only on the working filesystem and a `git clean` in the parent tree would take the whole directory with it.

## Self-Check: PASSED

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — FOUND, 64 lines, 10 `## ` headings, 0 matches for the audit vocabulary.
- `.planning/phases/38-post-auth-sync/38-04-SUMMARY.md` — FOUND.
- Task 2 has no commit hash to verify by design (parent-repository boundary); the summary commit is recorded in § "Task Commits".

---
*Phase: 38-post-auth-sync*
*Completed: 2026-09-01*
