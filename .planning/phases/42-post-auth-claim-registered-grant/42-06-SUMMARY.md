---
phase: 42-post-auth-claim-registered-grant
plan: 06
subsystem: planning
tags: [ledger, divergence, requirements, roadmap, state, d-14, d-15, d-16, reggrant-01, reggrant-02, reggrant-03]
status: complete

requires:
  - "42-01 … 42-05 (the shipped behaviour every amendment describes)"
  - ".planning/REQUIREMENTS.md § ANONGRANT (the Phase 41 amendment, the model for form and tone)"
  - "specs/auth-refactor-phases/07-claim-registered-grant.md and specs/auth-refactor/06-schema-reference.md (read for line numbers, not edited)"
provides:
  - "Six dated flagged conflicts under REGGRANT-01 … REGGRANT-03, each naming what the brief asks and what shipped"
  - "The inventory of obligations that were already dead before this phase began, by brief line"
  - "The re-derived counts: sixteen flagged conflicts, twenty-three known divergences, a gap of seven enumerated"
  - "Corrections in place for every active entry naming the deleted receipt row"
  - "A ROADMAP Phase 42 entry that matches what shipped, and a STATE outcome paragraph with measured counts"
affects:
  - "Phase 43 and later — the traceability table and the two count paragraphs are now consistent again"

tech-stack:
  added: []
  patterns:
    - "A divergence is recorded under the requirement it belongs to; the specification and its copies stay verbatim"
    - "A count is re-derived against the sections it summarises, never inherited"
    - "A superseded entry is corrected beside its original text, never deleted"

key-files:
  created:
    - .planning/phases/42-post-auth-claim-registered-grant/42-06-SUMMARY.md
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md
    - .planning/ROADMAP.md
    - .planning/auth-refactor-endpoint-changes.md
    - .planning/WINDOWS.md

decisions:
  - "The six divergences are distributed by subject, not by convenience: D-04 and D-05 under REGGRANT-01, D-02 and D-07/D-08 under REGGRANT-02, D-06 and D-09(b) under REGGRANT-03"
  - "A verbatim copy of the specification inside .planning/ gets a dated header note, never an edited step — D-15 applied to a copy"
  - "The brief-versus-invariants lock order is the same item ANONGRANT-02 records, applied to a second route, so it adds nothing to either count"
  - "Two counts in the traceability table, stale since Phase 41 updated the header alone, were corrected rather than left"
  - "ROADMAP criterion 4 is reworded because the conversion is not a refusal; criterion 1 needed no reword, against the plan's prediction"

metrics:
  duration: "~35 min"
  completed: 2026-09-03
  tasks: 3
  commits: 3

actuals:
  tokens: 16500
  tasks: 3
  commits: 3
---

# Phase 42 Plan 06: The Ledger Close Summary

Every difference between what `07-claim-registered-grant.md` and `06-schema-reference.md` ask for and
what this phase shipped is now written under the requirement a reader hits it from, with its date and
its reason, and neither specification file was touched.

## What Was Built

No code symbol. Dated entries in four planning documents.

**`.planning/REQUIREMENTS.md`.** A Phase 42 header paragraph, three per-requirement amendment blocks,
two corrections to Phase 41's ANONGRANT entries, an updated traceability row and two corrected counts
in the standing table.

**`.planning/STATE.md`.** A Phase 42 outcome paragraph, three corrections, six decisions, one accepted
exposure and a moved position.

**`.planning/ROADMAP.md`.** Four success criteria with explicit dispositions, the plan list closed and
the progress table row completed.

**`.planning/auth-refactor-endpoint-changes.md`.** One dated header note. Not one edited step.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | The dated REGGRANT amendments and the dead-obligation inventory | `809082f` | `REQUIREMENTS.md` |
| 2 | Correct every prior entry naming the deleted receipt row | `4fcfa4c` | `REQUIREMENTS.md`, `STATE.md`, `auth-refactor-endpoint-changes.md` |
| 3 | Mark the three requirements met and close the phase | `261473c` | `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md` |

## Verification

All four commands were run in this plan, and the numbers written into the ledger are the numbers these
runs printed. They were run once before Task 1 and again in Task 3, and were identical both times.

| Gate | Result |
|------|--------|
| `pytest -q` | **1001 passed**, 384 deselected |
| `pytest -m e2e -q` | **237 passed**, zero skipped |
| `pytest -m schema -q` | **147 passed**, zero skipped |
| `ruff check src tests` | All checks passed |
| `grep -c "\[x\] \*\*REGGRANT-0" REQUIREMENTS.md` | 3 |
| `grep -c "held_grant_ends_at" REQUIREMENTS.md` | 2 (was 0) |
| `grep -c "2026-09-0" REQUIREMENTS.md` | 60 (was 47) |
| `grep -c "REGGRANT" ROADMAP.md` | 6 |
| PLAN files on disk / SUMMARY files | 96 / 96 with this file |

Commands were run as `.venv/bin/python -m pytest` and `.venv/bin/ruff`, the same interpreter `uv run`
resolves to, as plans 42-02 … 42-05 also recorded.

## The Six Flagged Conflicts, and Where Each Sits

| Decision | What the brief asks | What shipped | Recorded under |
|----------|---------------------|--------------|----------------|
| D-04 | separate query and update DeviceCheck tokens (`:52`) | one `device_token` driving both Apple calls | REGGRANT-01 |
| D-05 | `verification_required` (`:47`) and a mandatory `getUser` on every branch (`:51`, `:67`, `:73`) | the stored `provider` column alone; no Firebase read on this route | REGGRANT-01 |
| D-02 | the device gate on every iOS claim (`:52`, `:53`, `:55`) | the conversion path calls Apple not at all | REGGRANT-02 |
| D-07 + D-08 | three tables and their hash evidence (`06-schema-reference.md:287`/`:349`/`:357`/`:1127`/`:1257`; brief `:48`/`:59`/`:60`/`:61`) | all three deleted from the one migration; no hash, key or key version anywhere | REGGRANT-02 |
| D-06 | `core.provider_accounts` uniqueness and `account_already_claimed` (`:25`, `:61`, `:72`) | the indexes the schema already carries; `ErrorCode` stays at 18 | REGGRANT-03 |
| D-09(b) | `held_grant_ends_at` on the refusal (`:25`, `:58`, `:67`) | the bare one-field 403 every refusal on this route returns | REGGRANT-03 |

The Apple exposure (D-16) is recorded under REGGRANT-01 as **accepted and flagged**, not as a conflict,
on the Phase 41 D-20 and Phase 40 D-22 precedent, with its mitigating facts and what closes it. The
entry states plainly that this route's exposure is narrower than the anonymous route's, because the
conversion destination reaches Apple not at all.

## The Counts, Re-derived Rather Than Inherited

Six `SHARED-INVARIANTS.md` sections were re-read against what shipped before any number was written.
**Every one produced a verdict of "none".** The verdicts are written into REGGRANT-01 with what each
section was examined against — Identity and ownership, The barrier, Fail-closed defaults, Locks and
transactions, Grants and evaluation time, Global deletions.

**One null result is worth naming here as well: `SHARED-INVARIANTS.md` names no anti-abuse row
anywhere.** A `grep` over the whole file for `anti_abuse`, `anti-abuse`, `provider_accounts`,
`provider_account_gate_consumptions` and `gate_consumption` returns nothing. So the phase's largest
deletion diverges from `06-schema-reference.md` and from the brief, and from no invariant text. The
plan anticipated a passage there and instructed that the divergence go in the ledger if one existed;
none does.

**The arithmetic, shown:**

| | Before | After | Why |
|---|---|---|---|
| Flagged conflicts | 10 | **16** | six new conflicts, counted at both ends |
| Known divergences | 16 | **23** | the same six, plus one uncounted item |
| The gap | 6 | **7** | the one uncounted item this phase adds |

The one uncounted item is D-16's unbounded Apple read on this route. **The gap's seven members are
enumerated in the header, item by item, and not reconciled away:** the `limits` override (Phase 35),
Phase 40's `core.auth_operation` forward flag, Phase 40's unbounded Firebase read, Phase 41's
lock-order precedence resolution, Phase 41's 422 collapse, Phase 41's unbounded Apple read, and Phase
42's unbounded Apple read.

**Two items that look like new divergences and are not.** The brief's lock order (`:56`, `:76`) puts a
user-row lock ahead of the grant locks, which § "Locks and transactions" forbids; the invariants win,
the code obeys them, and this is the identical item ANONGRANT-02 already records — one item met on a
second route, not a second item. The 422 collapse for an absent or empty device token is the same
field on the same shared request model, renamed `GrantClaimRequest` and used by both routes; it is
already in the set under ANONGRANT-01.

## The Already-Dead Obligations, Inventoried

Written into REGGRANT-01 so no later reader treats them as work this phase failed to do. Each names
the decision that killed it and the brief lines that still state it.

| Obligation | Killed by | Brief lines |
|------------|-----------|-------------|
| Rate limits and vendor budgets | Phase 35 D-05 | `:7`, `:17`, `:19`, `:28`, `:29`, `:43`, `:49`, `:52`, `:53`, `:74` |
| The `audit.auth_events` row and its result vocabulary | Phase 37.1 D-01 with Phase 38 D-03 | `:18`, `:27`, `:41`, `:47`, `:49`, `:51`, `:53`, `:58`, `:61`, `:62`, `:67`, `:75` |
| The mode signal and its classifier | Phase 37.2 | `:7`, `:41`, `:43` |
| `claim_attempt_id` and its consumption condition | Phase 37.4 D-03 | `:50`, `:64` |
| The HMAC keyring | Phase 37.4 D-11, and D-08 here | `:31`, `:48`, `:72`, `:74`, `:75` |
| The route registry and its enumeration assertion | Phase 37.1 D-06 | `:7`, `:16`, `:26` |
| The two Firebase confirmation points | Phase 41 D-08, and D-05 here | `:51`, `:73` |

## Every Planning-Directory Hit, With Its Disposition

The correction was driven by a grep for `access_grants_anti_abuse`, `AccessGrantAntiAbuse`,
`anti_abuse` and `anti-abuse row` over `.planning/**/*.md`, not by the plan's hand-written list. Every
hit is dispositioned below.

**Corrected — five sites in three active documents.**

| File | Site | Correction |
|------|------|------------|
| `REQUIREMENTS.md` | ANONGRANT-01, "Why the deferral costs no migration" | The premise is now **false**: the table it points at is gone, so the web branch does cost a schema change. The price is unchanged and named. |
| `REQUIREMENTS.md` | ANONGRANT-03, the four-row race claim | One anonymous claim now writes **three** rows; the device platform is on `external_identities.native_claim_platform`, which survives with the enum that types it. |
| `STATE.md` | the Phase 41 outcome paragraph | Same correction, same wording. |
| `STATE.md` | the 36-03 decision on `seed_grant` | The table and both deferrable FKs are gone, so a free-source grant seeds with no companion row. |
| `STATE.md` | the 37.4-07 decision on the orphan hash columns | Both tables are deleted, so neither column exists and the misattribution can no longer mislead. |

**Noted, not edited — one document.** `.planning/auth-refactor-endpoint-changes.md` is a verbatim copy
of the specification's endpoint text, and eight of its lines write one of the deleted tables. **Editing
those steps would resolve a divergence by editing the specification, which is exactly what D-15
forbids** — and the rule does not stop applying because the copy sits under `.planning/`. It got one
dated header note instead: what was deleted, where the divergence is recorded, and where the corrected
row count lives. No step was changed.

**Left as written — completed phases' own artifacts.** Every remaining hit is inside a finished
phase's plan, summary, research, patterns or inventory file, and each records what that phase actually
delivered against the schema of its day. Rewriting them would falsify their own delivery, which this
file's convention has forbidden since Phase 37.1. The files are: `34-02-PLAN.md`, `34-02-SUMMARY.md`,
`34-04-PLAN.md`, `34-04-SUMMARY.md`, `34-RESEARCH.md`, `34-PATTERNS.md`, `34-INVENTORY-PG17.md`,
`34-VERIFICATION.md`, `36-01-PLAN.md`, `36-01-SUMMARY.md`, `36-03-SUMMARY.md`, `36-05-SUMMARY.md`,
`36-RESEARCH.md`, `36-PATTERNS.md`, `37.4-CONTEXT.md`, `37.4-RESEARCH.md`, `37.4-05-SUMMARY.md`,
`37.4-07-SUMMARY.md`, `37.5-09-SUMMARY.md`, and eleven files under `41-post-auth-claim-anonymous-grant/`.
`git diff` over the Phase 41 directory is empty.

## What the Requirements Tool Actually Returned

Reported as measured, not as the plan predicted.

```
"updated": false,
"marked_complete": [],
"already_complete": [],
"not_found": [],
"table_unmatched": ["REGGRANT-01", "REGGRANT-02", "REGGRANT-03"],
"write_set": [ six entries, every one "applied": false ]
```

**The tool applied nothing at all — both surfaces, all three ids.** `41-LEARNINGS.md` predicted the
traceability half, and the prediction held: that row is written as a range covering three ids and the
per-id matcher cannot address it. The checkbox half is one step worse than 41-05 saw. Plan 42-02's run
had already ticked the three checkboxes; with them already `[x]`, this run reported them as
`table_unmatched` rather than `already_complete`, and applied nothing. So the tool's contribution to
this phase's close was zero, and the traceability row was written by hand, as every prior endpoint
phase has written it.

## Deviations from Plan

### Acceptance Criteria That Were Wrong as Written

**1. Task 1: "`git -C /home/init/native-speaker status --porcelain -- specs/` is empty".**
It is not, and cannot be. The command prints `?? specs/auth-refactor-phases/` — that directory is
**untracked** in the parent repository and has been since before this phase, so `git status` reports it
whatever any agent does. The criterion's substance was checked by the assertions that can hold, and all
three do: `git status --porcelain -- specs/auth-refactor/` (the tracked half, holding
`06-schema-reference.md`) is empty; `07-claim-registered-grant.md` has an mtime of 2026-08-18 and
`SHARED-INVARIANTS.md` of 2026-09-01, both before today; and no task in this plan opened either file
for writing. Recorded in `WINDOWS.md`.

**2. Task 2: the verify block's allow-list is narrower than the task's own action text.**
`<fails_when>` fails the task if the grep names any file outside `41-*`, `42-*`, `milestones/` and the
two ledgers. Nineteen files under phases 34, 36, 37.4 and 37.5 name the deleted table, none of them
touched by this phase. The action text states the correct rule one paragraph above — correct the hits
and leave *"a historical artifact of a completed phase whose own summary must stay as written"* — so
the action was followed and every hit is dispositioned in the table above. Recorded in `WINDOWS.md`.

### Judgement Calls Inside Claude's Discretion

**1. Two stale counts in the traceability table were corrected, beyond the plan's letter.**
The plan directs re-deriving *"the header's flagged-conflict count"*. The § Traceability standing table
carries the same two numbers in prose, and both had been stale since 2026-09-02: the cell still read
**six** conflicts and **nine** divergences after Phase 41 took them to ten and sixteen. Phase 41
updated the header and not the table. A ledger that states one number in two places and disagrees with
itself is worse than one that is merely out of date, and this plan's own prohibition — *"a count must
never be inherited"* — applies to a table as much as to a header. Both cells now carry the current
numbers with a dated note saying what was stale and when. The six conflicts the cell enumerates are
left as written, and the note says they are the six that predate Phases 41 and 42.

**2. The `REQUIREMENTS.md` footer gained two lines, not one.**
The "Last updated" line still named Phase 40 plan 08 on 2026-09-02: Phase 41 amended the file twice on
2026-09-03 and added no footer line either time. Rather than write a Phase 41 line the phase did not
write, the new Phase 42 line is followed by a short line recording that Phase 41's two amendments are
in the header block and left no footer entry — so a reader who wonders why the dates jump from Phase 40
to Phase 42 finds the answer instead of a gap.

**3. ROADMAP criterion 1 needed no reword, against the plan's prediction.**
The plan instructed that criterion 1 be checked most carefully, because *"across prepare and completion
modes"* describes a partition Phase 37.2 replaced. **That clause is not in criterion 1.** The criterion
reads *"This is the only code path that writes a grant row with `source='registered_account_grant'`"*
and is met as written. The mode-partition wording is in **REGGRANT-01**, which carries the reword on
the ANONGRANT-01 model. The criterion is marked met and the discrepancy is stated in its own note, per
`41-LEARNINGS.md` § "Verify the state before acting on what the plan predicted".

**4. Criterion 4 was reworded, as the plan expected, and the reword names both answers.**
The criterion implies one answer — a refusal — for an account that already consumed its free grant as
anonymous. Two answers ship, and the difference is whether that grant is still active: an active grant
is **converted**, a spent one is **refused**. The property the criterion protects, that no account ends
with two free entitlements, holds on both paths, so the criterion is reworded rather than withdrawn.
The matching amendment is under REGGRANT-03.

### Auth Gates

None.

## Threat Model

| Threat ID | Disposition | Outcome |
|-----------|-------------|---------|
| T-42-06-01 | mitigate | Held. No file under `specs/` was opened for writing; the tracked half is clean and both briefs' mtimes predate this phase. The rule was additionally extended to the copy of the brief inside `.planning/`, which got a note and no edit. |
| T-42-06-02 | mitigate | Held. A grep drove the correction, not the plan's list, and every hit is dispositioned in the table above — five corrected, one noted, the rest left with the reason stated. |
| T-42-06-03 | mitigate | Held. All four commands were run in this plan, twice, with identical results, and the ledger quotes 1001 / 237 / 147. No count was copied from a plan or a summary. |
| T-42-06-04 | mitigate | Held. The Apple exposure is recorded as accepted and flagged with its mitigating facts and what closes it, and is explicitly not counted as a conflict. |
| T-42-SC | mitigate | Held. No package was installed, added, moved or upgraded. |

## Known Stubs

None. This plan writes prose into planning documents. No stub, TODO, FIXME or placeholder was
introduced, no test was skipped, and every `<verify>` command in the plan was run.

## Threat Flags

None. No source file was modified. No network endpoint, auth path, file access pattern or
trust-boundary schema change was introduced.

## For the Next Phase

- `REQUIREMENTS.md` now reads **sixteen** flagged conflicts and **twenty-three** known divergences,
  with a gap of seven enumerated in the header. Phase 43 re-derives these against its own sections
  rather than inheriting them.
- The traceability table and the header agree again. If a phase updates one, it must update both.
- `requirements.mark-complete` cannot address a range traceability row, and reports an already-ticked
  checkbox as `table_unmatched` rather than `already_complete`. Expect to write both surfaces by hand,
  and report what the tool returned.
- `.planning/auth-refactor-endpoint-changes.md` is a verbatim specification copy. It carries a dated
  header note now; add to that note rather than editing a step.
- Phase 42 is executed, not verified. `completed_phases` stays at 12 for that reason.

## Self-Check: PASSED

- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/ROADMAP.md` and
  `.planning/auth-refactor-endpoint-changes.md` all exist on disk and are modified.
- `.planning/phases/42-post-auth-claim-registered-grant/42-06-SUMMARY.md` exists on disk.
- Commits `809082f`, `4fcfa4c` and `261473c` are all present in git history.
