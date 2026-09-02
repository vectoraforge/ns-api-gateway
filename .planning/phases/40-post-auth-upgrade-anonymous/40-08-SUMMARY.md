---
phase: 40-post-auth-upgrade-anonymous
plan: 08
subsystem: planning
tags: [requirements, roadmap, divergence-record, flagged-conflict, traceability]

# Dependency graph
requires:
  - phase: 40-06
    provides: "the account-less issuance condition, and the deferral of UPGRADE-02's traceability to a central plan"
  - phase: 40-07
    provides: "the green gates this plan cites when marking UPGRADE-01 and UPGRADE-02 met"
provides:
  - "the dated Phase 40 amendment naming all four divergences, under UPGRADE-01 and UPGRADE-02"
  - "one new flagged conflict — D-01's removed client declaration — taking the milestone count from five to six"
  - "the enum shrink flagged forward to phases 45 and 46, whose briefs name labels that no longer exist"
  - "the SCHEMA-01 note for the migration's second in-place edit"
  - "ROADMAP Phase 40 success criterion 2, reworded to the design that shipped"
affects: [45-restore-subscription, 46-sign-out-all]

# Actuals (#2632) — same estimateTokens scale (chars/4) as the plan's estimate.
actuals:
  tokens: 8400
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A divergence is recorded forward, in the requirements ledger, never by editing the specification it diverges from nor the context entry that recorded the decision it reverses"
    - "A conflict count is re-derived by naming the sections re-read and what each produced, because a null result is only useful if it says what it examined"
    - "A superseded criterion is reworded rather than quoted: the stale wording survives in the ledger, not in the file a reader greps"

key-files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md

key-decisions:
  - "D-01's removal of the client-declared target provider is filed as a NEW FLAGGED CONFLICT against unamended text in 05-upgrade-anonymous.md, taking the count from five to six — the brief states the declaration six times and none of it is amended"
  - "D-11's enum shrink is filed as a FORWARD FLAG to phases 45 and 46 rather than a counted conflict, on the Phase 37.1 precedent: that phase deleted audit.auth_events against 00-schema.md and recorded it by withdrawing SCHEMA-06, filing its counted conflict against SHARED-INVARIANTS.md instead"
  - "D-22's unbounded Firebase read is flagged but NOT counted — it is a consequence of the pre-existing Phase 35 D-05 limits override, the same treatment PROF-01 gives the users_me entry"
  - "The identical declaration removal at create-user (Phase 37 D-12) was never filed as a conflict; that gap is reported and left as Phase 37's to close rather than re-filed here, on the grounds Phase 37.5 used to leave the limits override in Phase 35's category"
  - "Forward-flag pointers were added under RESTORE-01 and SIGNOUT-01 beyond the plan's letter (Rule 2), because a phase-45 or phase-46 planner reads their own block, not this phase's amendment"
  - "The ROADMAP reword does not quote the superseded wording, because its own acceptance criterion greps for that string's absence; the verbatim history lives in REQUIREMENTS.md"

patterns-established:
  - "When a reword's acceptance criterion is a grep for the old string's absence, the old string cannot survive as a quotation in the same file — point at the ledger instead"

requirements-completed: [UPGRADE-01, UPGRADE-02]

coverage:
  - id: D1
    description: "UPGRADE-01 and UPGRADE-02 carry a dated amendment naming all four decisions new to this phase"
    requirement: "UPGRADE-01"
    verification:
      - kind: command
        ref: "grep -c 'Phase 40' .planning/REQUIREMENTS.md -> 19 (was 2)"
        status: pass
      - kind: manual
        ref: ".planning/REQUIREMENTS.md:34 (header), :244 (declaration), :47 (enum shrink), :250 (Firebase exposure), :252 (D-18 reversal)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The amendment states that the brief's rate-limit and audit obligations were already dead before this phase began"
    requirement: "UPGRADE-02"
    verification:
      - kind: manual
        ref: ".planning/REQUIREMENTS.md:263 — names Phase 35 D-05, Phase 37.1 D-01 and Phase 38 D-03 against the brief's :19/:29/:30/:66/:88/:89"
        status: pass
    human_judgment: false
  - id: D3
    description: "SCHEMA-01 carries a note recording the second in-place migration edit"
    requirement: "SCHEMA-01"
    verification:
      - kind: manual
        ref: ".planning/REQUIREMENTS.md:45 — the in-place edit and both database re-applies; :47 — the forward flag to phases 45 and 46"
        status: pass
    human_judgment: false
  - id: D4
    description: "ROADMAP Phase 40 criterion 2 no longer describes prepare as a mode on this endpoint"
    requirement: "UPGRADE-02"
    verification:
      - kind: command
        ref: "grep -c 'Prepare and completion modes both work' .planning/ROADMAP.md -> 0"
        status: pass
      - kind: command
        ref: "git diff .planning/ROADMAP.md — touches only the Phase 40 block, only criterion 2 and the note it discharges"
        status: pass
    human_judgment: false
  - id: D5
    description: "The flagged-conflict count is re-derived against the binding specification and stated"
    requirement: "UPGRADE-01"
    verification:
      - kind: manual
        ref: ".planning/REQUIREMENTS.md:256 — five SHARED-INVARIANTS sections named with what each produced; result five -> six"
        status: pass
    human_judgment: true
    rationale: "Whether D-01's removal is a counted conflict or an uncounted divergence is a judgement, not a measurement. It is filed as counted because the brief text is unamended and nothing removed it; the contrary precedent — Phase 37 D-12's identical removal, never filed — is reported in the entry rather than used to justify silence."
  - id: D6
    description: "No specification file was edited and no existing requirement statement rewritten"
    requirement: "UPGRADE-01"
    verification:
      - kind: command
        ref: "ls -l /home/init/native-speaker/specs/auth-refactor-phases/ — every brief unmodified since 2026-08-18; SHARED-INVARIANTS.md since 2026-09-01 (Phase 38)"
        status: pass
      - kind: command
        ref: "git diff -U0 .planning/REQUIREMENTS.md | grep -E '^[-+]- \\[' — only the two UPGRADE checkboxes changed; statement text byte-identical"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-09-02
status: complete
---

# Phase 40 Plan 08: The Divergence Record Summary

**Phase 40's four decisions that differ from what was asked for are now written down where a reader meets them — one filed as a new flagged conflict taking the milestone count from five to six, two flagged forward to the phases they land on, and one recorded as a reversal of this phase's own decision — with no brief edited and no decision rewritten.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-09-02
- **Tasks:** 2
- **Files modified:** 2 (0 created, 2 modified)

## Task Commits

1. **Task 1: The dated UPGRADE amendment and the SCHEMA-01 note** — `7360155`
2. **Task 2: Correct ROADMAP Phase 40 success criterion 2** — `fb900ea`

## The five subjects, with the line each is on

`grep -c "Phase 40" .planning/REQUIREMENTS.md` returned **2** before this task and **19** after.

| # | Subject | Line in `.planning/REQUIREMENTS.md` |
|---|---|---|
| — | The dated Phase 40 header amendment | `:34` |
| 1 | The removed client declaration — **new flagged conflict** | `:244` |
| 2 | The operation-enum shrink — in-place edit note `:45`, **forward flag** | `:47` |
| 3 | The accepted unbounded Firebase exposure — flagged, not counted | `:250` |
| 4 | The D-18 credential-mechanism reversal, with its cause | `:252` |
| 5 | The already-dead rate-limit and audit obligations | `:263` |
| — | The re-derived conflict count and the sections re-read | `:256` |

Two further forward-flag pointers were added so the phases that inherit the enum shrink meet it in their own block: under **RESTORE-01** (phase 45) and **SIGNOUT-01** (phase 46).

## The D-18 item's two-halved cause, quoted from the entry

Both halves are stated at `:252`, verbatim from the committed text:

> first, this machine's Application Default Credentials resolve to an `authorized_user` — a user credential with no `client_email` and no signer — so `firebase_admin.auth.create_custom_token` raises *"Failed to determine service account … Make sure to initialize the SDK with service account credentials or specify a service account ID with `iam.serviceAccounts.signBlob` permission"*

> second, the project's org policy sets `iam.disableServiceAccountKeyCreation`, recorded in `.env.example`, so **no service-account key can be minted here at all** to supply one.

The mechanism that replaced it is named in the same entry: **exchange-and-link** — one by-hand browser consent yields a long-lived Google refresh token in `.env`, and each run redeems it for a Google ID token, creates a fresh anonymous Firebase user over Identity Toolkit REST, links the Google credential onto it, and deletes the user afterwards.

## The conflict count, re-derived rather than inherited

**Result: five → six.** One new conflict; three uncounted divergences, so the set of known divergences goes six → nine.

Re-read before stating it, per the plan's instruction not to inherit the claim — five sections of `SHARED-INVARIANTS.md` (§ "Identity and ownership", § "The barrier", § "Fail-closed defaults", § "Locks and transactions", § "Global deletions"), `05-upgrade-anonymous.md` in full, and `00-schema.md:190`, `01-foundation.md:137`, `10-restore-subscription.md:25`, `11-sign-out-all.md:25` for the shrink's reach.

**The new conflict — D-01, the removed client-declared target provider.** The brief states the declaration six times and **none of that text is amended**: `:26` (the immutable `operation_variant`), `:46` (the REQUIRED field at prepare), `:53` (the byte-for-byte re-check before any Firebase lookup), `:56` ("Classified provider must equal the declaration for any success"), `:60`/`:61` (the (c) and (d) rejections phrased in terms of the declaration), `:81` ("missing or invalid declared target provider" in the mandatory rejection scope). What shipped: `CompletionRequest` is exactly `{challenge_id}` and `ChallengeRequest` exactly `{operation}` — neither carries a provider field, verified by reading `src/nativespeaker/api/schemas/auth.py`.

**Why counted rather than overridden.** The four sections that produced nothing produced nothing for stated reasons, recorded at `:256`. This one produced a live divergence from unamended text with nothing having removed it — which is the file's own test for a flagged conflict, applied to CREATE-02's plaintext subject and CREATE-04's provider-account collapse alike, both against a phase brief rather than the shared invariants.

**The contrary precedent, reported rather than used as cover.** Phase 37 D-12 made the *identical* removal at create-user against `02-create-user.md:48` and `:58`, and it was never filed in `REQUIREMENTS.md` as a conflict at all. That gap is stated in the entry and left as Phase 37's to close — the same treatment Phase 37.5 gave the `limits` override, where re-filing would have rewritten an earlier phase's own decision. A reader auditing divergences is told the shape exists twice and is counted once.

**The three uncounted divergences**, which is why the two numbers differ by three rather than one: the `limits` mandate (a Phase 35 D-05 override, already the gap before this phase); the enum shrink (forward-flagged); and the unbounded Firebase read (a consequence of the `limits` override, not a fresh divergence).

## The enum shrink: forward flag, not counted conflict

`00-schema.md:190` still reads that `core.auth_operation` *"lists all seven state-changing operations, including `restore_subscription`, `sign_out_all`, and `sync`"*, and `10-restore-subscription.md:25` and `11-sign-out-all.md:25` still name labels the type no longer carries. Filed as a **forward flag** rather than a counted conflict, on the Phase 37.1 precedent: that phase deleted the whole of `audit.auth_events` against `00-schema.md` and the record was a **withdrawal** of SCHEMA-06, with the counted conflict filed against `SHARED-INVARIANTS.md` § "Audit" instead. `SHARED-INVARIANTS.md` says nothing about `core.auth_operation`, before or after Phase 38's edit, so there is no invariant text here to diverge from.

**Nothing in the product lost a value it could use:** the labels' only consumers were `audit.auth_events` (Phase 37.1 D-01) and the route registry's route→operation metadata (Phase 37.1 D-06), and restore and sign-out are explicitly **not** challenge-bearing by their own briefs, so neither ever belonged in the surviving consumer, `core.auth_challenges.operation`. What phases 45 and 46 inherit is a naming question, not a mechanism.

## Traceability settled centrally, as 40-06 deferred

Plan 40-06 left `REQUIREMENTS.md` alone and said so: UPGRADE-02 is shared with 40-04 and 40-07, two worktrees were live in that wave, and marking it mid-wave would race. This plan owns it. **UPGRADE-01 and UPGRADE-02 are both checked**, and the traceability row reads Complete with each requirement's amendment named.

The command that established it, run in this worktree after the wave merged:

| Gate | Result |
|---|---|
| `uv run pytest -q` | **857 passed**, 337 deselected |
| `uv run pytest -m 'e2e or schema' -q` | **337 passed**, 857 deselected (216 e2e + 121 schema) |

## Files Modified

- `.planning/REQUIREMENTS.md` — the dated Phase 40 header amendment; the SCHEMA-01 in-place-edit note and its forward flag; six new notes under UPGRADE-01 and UPGRADE-02; forward-flag pointers under RESTORE-01 and SIGNOUT-01; the conflict enumeration, the standing table, both traceability rows and the footer updated from five to six. 43 insertions, 8 deletions.
- `.planning/ROADMAP.md` — Phase 40 success criterion 2 reworded, and the forward-pointing note it discharges removed. 1 insertion, 3 deletions.

## Deviations from Plan

**Two additions beyond the plan's letter, both recorded rather than silent.**

- **[Rule 2 — Missing critical functionality] Forward-flag pointers added under RESTORE-01 and SIGNOUT-01.** The plan's action names the header block, UPGRADE-01/02 and SCHEMA-01. But the plan's own success criterion is that a reader finds the divergence "without having to read any plan or any commit", and a phase-45 or phase-46 planner reads their own requirement block — not Phase 40's amendment. Two dated one-paragraph notes were added so the label's absence is met where it lands. Both are additions; no existing text was rewritten.
- **The ROADMAP reword does not quote the superseded wording.** The plan's convention instruction ("say it is reworded rather than withdrawn, give the date, name the phase") does not require a verbatim quote, and the task's own acceptance criterion requires `grep -c "Prepare and completion modes both work"` to return `0` — which a quotation would defeat. A first draft quoted it and returned `1`; the quote was removed and the criterion now returns `0`. `REQUIREMENTS.md` UPGRADE-02 carries the history of what the mechanism used to be. This is `ROADMAP.md`'s own existing convention: the reworded criteria at `:213`, `:251` and `:604` describe the superseded design without quoting it.

**One judgement the plan left open, resolved and flagged as a judgement.** The plan said to re-derive the conflict count and "if this phase adds none, say so". It adds one. Filing D-01 as a counted conflict is a judgement rather than a measurement — see coverage item D5's rationale, and the contrary precedent reported in the entry itself.

**Nothing else deviated.** No brief was edited, no requirement statement text was rewritten, and `40-CONTEXT.md` was not touched at all — D-18's body is deliberately left describing the reversed mechanism, carrying only the dated one-line pointer the planner had already added beneath it.

## Issues Encountered

- **`.env` had to be copied into the worktree.** It is gitignored, so the parallel worktree was created without it, and the e2e and schema suites cannot reach PostgreSQL, Firebase or Google without it. Copied from the main checkout as the dispatch directed. It was never staged and never committed — `git status --short` is empty at both commits.
- **`git status --porcelain /home/init/native-speaker/specs/` cannot run from this worktree**, because `specs/` lives in the parent repository and is outside this repository entirely. The criterion's intent was verified a stronger way: `ls -l --time-style=long-iso` shows every phase brief unmodified since **2026-08-18** and `SHARED-INVARIANTS.md` since **2026-09-01** (Phase 38's edit). Nothing in `specs/` was touched today, and from inside this worktree it is structurally impossible to have staged it.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -q` | 857 passed, 337 deselected |
| `uv run pytest -m 'e2e or schema' -q` | 337 passed, 857 deselected |
| `grep -c "Phase 40" .planning/REQUIREMENTS.md` | **19** (was **2**) |
| `grep -c "Prepare and completion modes both work" .planning/ROADMAP.md` | **0** |
| `git diff -U0 .planning/REQUIREMENTS.md \| grep -E '^[-+]- \['` | only the two UPGRADE checkboxes; statement text byte-identical |
| `git diff .planning/ROADMAP.md` | Phase 40 block only; criterion 2 and the note it discharges; criteria 1, 3, 4 untouched |
| `specs/auth-refactor-phases/` mtimes | every brief 2026-08-18; `SHARED-INVARIANTS.md` 2026-09-01 — none edited today |
| `git diff --diff-filter=D` over both commits | no deletions |
| `git status --short` | empty at both commits |

## Known Stubs

None. This plan adds no code symbol and touches no source file.

## Threat Flags

None. The plan's register is discharged as written: **T-40-08-01** (the accepted Firebase exposure is recorded with its mitigating facts and the event that closes it, at `:250`); **T-40-08-02** (no brief edited — verified by mtime; the entry is appended and dated, and no requirement statement text is rewritten); **T-40-08-03** (the SCHEMA-01 note at `:45` explains the shape a later reader finds in the diff); **T-40-08-SC** (not reachable — nothing installed, no source file touched).

## Self-Check: PASSED

- `.planning/phases/40-post-auth-upgrade-anonymous/40-08-SUMMARY.md` — FOUND
- `.planning/REQUIREMENTS.md` — FOUND and modified
- `.planning/ROADMAP.md` — FOUND and modified
- Commits `7360155`, `fb900ea` — both FOUND in `git log`
- `specs/auth-refactor-phases/` — unmodified, confirmed by mtime
- `.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md` — unmodified, absent from both commits
