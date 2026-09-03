---
phase: 41-post-auth-claim-anonymous-grant
plan: 05
subsystem: docs
tags: [requirements, roadmap, state, flagged-conflicts, ledger, devicecheck, apple]

# Dependency graph
requires:
  - phase: 41-post-auth-claim-anonymous-grant
    provides: "41-01 through 41-04 — the shipped endpoint, the case matrix, the live race and its production fix; the amendments state what shipped, so they could not be written before it did"
  - phase: 40-post-auth-upgrade-anonymous
    provides: "UPGRADE-01/02's amendment shape, the count-re-derivation convention, the D-22 accepted-vendor-exposure precedent and criterion 2's reword"
provides:
  - "The dated ANONGRANT-01…03 amendments: four new flagged conflicts against `06-claim-anonymous-grant.md`, each stating the brief's requirement then what shipped"
  - "The brief-versus-invariants lock order recorded as resolved by precedence, excluded from the flagged count and counted only among the divergences"
  - "The dead-obligation inventory — six obligations the brief states that were already deleted from the product, each with the phase and decision that killed it"
  - "The header's two counts re-derived against six SHARED-INVARIANTS sections: six to ten conflicts, nine to sixteen divergences, with the gap of six enumerated"
  - "ROADMAP Phase 41 criterion 4, reworded off the mode-signal partition Phase 37.2 replaced"
  - "STATE.md: the Apple exposure accepted, the absent vendor round trip recorded as a fact about the world, and seven of this phase's decisions carried forward as one-line rules"
affects: ["phase 42 registered account grant", "phase 45 restore", "phase 46 sign-out-all", "v2.0 milestone audit"]

actuals:
  tokens: 14225
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A divergence from a binding specification is recorded under the requirement it belongs to; the specification is never edited to agree with the code"
    - "A count stated in the header is re-derived against the named sections it summarises, and the sections that produced nothing say what they examined"
    - "A blocker is closed in place with its measurement intact, never deleted"

key-files:
  created:
    - .planning/phases/41-post-auth-claim-anonymous-grant/41-05-SUMMARY.md
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "The lock-order item is recorded as resolved by precedence rather than flagged, because the binding text tells this project what to do and the code does it — a flagged conflict is reserved for a knowing divergence from binding text"
  - "The absent-token 422 collapse is recorded as a divergence but not counted as a conflict: the client sees a different status, but the decision applies an existing project convention rather than making a fresh one against the brief"
  - "`verification_required`'s absence is a consequence of the iOS-only scope, counted at neither end — every producer the brief gives it lives in the deferred web branch"
  - "A-15 was verified already closed by 41-02 and left alone rather than closed twice"
  - "The ANONGRANT traceability row was updated by hand because it is a range row (`ANONGRANT-01 … ANONGRANT-03`) that `requirements.mark-complete` cannot address per-ID"

patterns-established:
  - "Consequence versus divergence versus conflict: a consequence dissolves with the decision that caused it and is counted at neither end; a divergence is counted only in the set; a conflict is counted at both"
  - "The gap between the conflict count and the divergence set is enumerated item by item rather than reconciled away"

requirements-completed: [ANONGRANT-01, ANONGRANT-02, ANONGRANT-03]

coverage:
  - id: D1
    description: "The ANONGRANT section carries three dated amendment blocks, one per requirement, and all three checkboxes read as met"
    requirement: "ANONGRANT-01"
    verification:
      - kind: other
        ref: "uv run python -c \"... .split('### ANONGRANT')[1].split('### REGGRANT')[0] ...\" -> 29226 13 7 3 (length, dated entries, 'flagged' occurrences, met marks)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Four new flagged conflicts — iOS-only gate (D-01), database before Apple (D-03), anonymous claimants only (D-08), the idempotent repeat (D-09) — each stating the brief's requirement with its line citations, then what shipped, then the decision that made it"
    requirement: "ANONGRANT-01"
    verification:
      - kind: other
        ref: "Each of the four cites named brief text (:7/:42–:45/:70/:75/:76; :73–:78; :51/:83; :26/:78) and was read against the brief in full during authoring"
        status: pass
    human_judgment: true
    rationale: "Whether an amendment states the conflict a reader of the brief would actually hit — and states it in the order the convention requires — is a reading of two prose documents against each other. No command asserts it."
  - id: D3
    description: "The brief-versus-invariants lock order is recorded as resolved by precedence, explicitly excluded from the flagged count, and counted only among the divergences"
    requirement: "ANONGRANT-02"
    verification:
      - kind: other
        ref: ".planning/REQUIREMENTS.md § ANONGRANT-02, and item (4) of the header's enumerated six-item gap"
        status: pass
    human_judgment: true
    rationale: "The categorisation — resolved rather than flagged — is a judgment about what a flagged conflict means in this ledger, not a property a check can read off the file."
  - id: D4
    description: "The dead-obligation inventory names six obligations the brief states that were already deleted from the product, each with the phase and decision that removed it"
    requirement: "ANONGRANT-01"
    verification:
      - kind: other
        ref: "Rate limits and vendor budgets (Phase 35 D-05), the audit row and its result vocabulary (Phase 37.1 D-01 / Phase 38 D-03), the mode-signal partition (Phase 37.2), claim_attempt_id (Phase 37.4 D-03), the HMAC keyring (Phase 37.4 D-11), the route registry (Phase 37.1 D-06)"
        status: pass
    human_judgment: true
    rationale: "The count of six is checkable; the claim that these are ALL of the brief's dead obligations is a reading of the brief against five phases of decisions. A missed one reads as unmet work to the next reader."
  - id: D5
    description: "Neither `06-claim-anonymous-grant.md` nor `SHARED-INVARIANTS.md` was edited — the divergences are recorded, never resolved by rewriting what they diverge from"
    verification:
      - kind: other
        ref: "ls -l on both spec files shows mtimes 2026-08-18 and 2026-09-01, both predating this session; neither appears in any commit of this plan"
        status: pass
    human_judgment: false
  - id: D6
    description: "Both header counts re-derived against six named SHARED-INVARIANTS sections rather than inherited: six to ten flagged conflicts, nine to sixteen divergences, with the six-item gap enumerated"
    requirement: "ANONGRANT-01"
    verification:
      - kind: other
        ref: ".planning/REQUIREMENTS.md § ANONGRANT-01, final paragraph — the six sections, what each examined, and why five produced nothing"
        status: pass
    human_judgment: true
    rationale: "The arithmetic is checkable but the re-derivation is not: whether re-reading § Identity, § The barrier, § Fail-closed, § Locks, § Grants and § Global deletions against this phase genuinely produced no seventeenth divergence is exactly the judgment the exercise exists to make."
  - id: D7
    description: "ROADMAP Phase 41 criterion 4 no longer describes the mode-signal partition; it names the shared challenge route as the prepare step and the handle binding as the ordering guarantee"
    verification:
      - kind: other
        ref: "uv run python -c \"... split('#### Phase 41')[1] ...\" -> False True (phrase absent, challenge named); git diff --stat .planning/ROADMAP.md -> 1 insertion, 1 deletion"
        status: pass
    human_judgment: true
    rationale: "The command proves the deleted phrase and the confined diff. Whether the replacement names the property the criterion was actually protecting, in the register the other three use, is a reading."
  - id: D8
    description: "A-15 is marked resolved in place with its original measurement, the value that shipped and the file it was set in; no blocker entry is deleted"
    verification:
      - kind: other
        ref: "uv run python -c \"... print('A-15' in s, s.count('RESOLVED'), 'DeviceCheck' in s ...)\" -> True 2 True; git diff .planning/STATE.md deletes only the two Current Position lines that were rewritten"
        status: pass
    human_judgment: false
  - id: D9
    description: "The unbounded Apple exposure is recorded as accepted with what mitigates it and what closes it, and the absence of any real vendor round trip is recorded as a fact about the world rather than a gap"
    requirement: "ANONGRANT-01"
    verification:
      - kind: other
        ref: ".planning/STATE.md § Blockers/Concerns — two new ACCEPTED entries; the exposure is also under ANONGRANT-01 as FLAGGED, NOT COUNTED"
        status: pass
    human_judgment: true
    rationale: "Whether an accepted risk reads as accepted rather than as an unnoticed defect is precisely the thing a later reader gets wrong, and no check can tell the difference."
  - id: D10
    description: "This phase's decisions are carried forward into STATE.md § Decisions as one-line rules — the seam's placement, the bit1 carry-forward, the status-predicate-free eligibility read, the unique index as race arbiter, the injected post-claim callable, the shared captured instant, and the free-grant source set tied to its index"
    verification:
      - kind: other
        ref: "grep -c '^- \\[Phase 41\\]' .planning/STATE.md -> 16 (nine from 41-02/03/04, seven added here)"
        status: pass
    human_judgment: true
    rationale: "Whether a one-line rule carries enough of its ground that the next phase does not rebuild the thing it forbids is a judgment about writing, not a count."
  - id: D11
    description: "The three requirements are marked met on a named suite result quoted in the amendment, not on the strength of the plans having run"
    requirement: "ANONGRANT-03"
    verification:
      - kind: unit
        ref: "uv run pytest -q -> 950 passed, 360 deselected"
        status: pass
      - kind: e2e
        ref: "uv run pytest -m e2e -q -> 226 passed"
        status: pass
      - kind: integration
        ref: "uv run pytest -m schema -q -> 134 passed"
        status: pass
      - kind: other
        ref: "uv run ruff check src tests -> All checks passed! (exit 0)"
        status: pass
    human_judgment: false

# Metrics
duration: 12 min
completed: 2026-09-03
status: complete
---

# Phase 41 Plan 05: The ANONGRANT amendments, criterion 4's reword, and the ledger Summary

**A reader can now open `06-claim-anonymous-grant.md` and `.planning/REQUIREMENTS.md` together and tell, for every obligation the brief states, whether it was met, diverged from with a reason, or killed by an earlier decision — four new flagged conflicts, one resolved by precedence, two consequences, six dead obligations, and both header counts re-derived from six to ten and nine to sixteen.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-03T06:19:00Z
- **Completed:** 2026-09-03T06:31:26Z
- **Tasks:** 3
- **Files modified:** 3 (plus this summary)

## Accomplishments

- **The four new flagged conflicts are written where a reader of the brief will find them**, each stating the brief's requirement with its line citations first and what shipped second: the **iOS-only gate** (D-01, against `:7`/`:42`–`:45`/`:70`/`:75`/`:76`), **database before Apple** (D-03, against steps 8 and 9 at `:73`–`:78`), **anonymous claimants only** (D-08, against `:51` and `:83`), and **the idempotent repeat** (D-09, against `:26` and `:78`). Each names the decision that made it and the thing it gives up — the deferred branches' dissolution list, the vendor round trip an ineligible account no longer costs, the registered user's fallback, and the two states that still refuse.
- **The lock-order item is recorded as resolved, not flagged.** The brief's step 11 locks the target user before the grant set; `SHARED-INVARIANTS.md` § Locks forbids exactly that. This is a conflict **inside the specification**, and the invariants win by the rule stated at the top of that file — so the code obeys binding text rather than diverging from it. It is counted only in the set of divergences, because a reader comparing brief to code still finds a difference and is owed the reason.
- **Six dead obligations are named individually with the decision that killed each**, as prose a reader can check against the brief: every rate-limit entry and vendor budget for this route (Phase 35 D-05), the `audit.auth_events` row and its seventeen internal-result values (Phase 37.1 D-01, Phase 38 D-03), the mode-signal partition and its query flag (Phase 37.2), `claim_attempt_id` (Phase 37.4 D-03), the HMAC keyring (Phase 37.4 D-11), and the route registry with its startup enumeration assertion (Phase 37.1 D-06).
- **Both counts re-derived rather than inherited**, against six named `SHARED-INVARIANTS.md` sections read against what shipped — and the five that produced nothing say what they examined, because a null result that does not name its subject proves nothing. The count goes six → **ten**; the set of known divergences nine → **sixteen**; and the gap of **six** is enumerated item by item rather than reconciled away.
- **ROADMAP criterion 4 now describes a property this endpoint has** rather than machinery Phase 37.2 removed it from having: challenge-bearing, prepare served by the shared `POST /auth/challenge` route, completion requiring a handle that route issued and bound to the caller's identity row.
- **STATE.md carries the two things this phase accepted rather than solved** — the unbounded Apple round trips (mitigated, closing with the v2.1 gateway contract) and the fact that **no real round trip to Apple has ever been made** — plus **seven** new one-line decision rules, so Phase 42 inherits rules instead of four summaries to re-read. (Task 3's commit message says "six"; the count is seven — the seam's absent logger is the one it undercounts.)

## Task Commits

1. **Task 1: The four new flagged conflicts and the one resolved by precedence** — `27ba524` (docs)
2. **Task 2: The ROADMAP criterion that describes machinery Phase 37.2 deleted** — `12e76e5` (docs)
3. **Task 3: The Apple exposure, A-15 closed, and the decisions carried forward** — `09cd60f` (docs)

## Files Created/Modified

- `.planning/REQUIREMENTS.md` — three dated ANONGRANT amendment blocks; a new Phase 41 header amendment paragraph; the standing count paragraph rewritten from six/nine to ten/sixteen with the four new conflicts enumerated and the six uncounted divergences listed; the ANONGRANT traceability row moved from `Pending` to `Complete` with what each requirement carries
- `.planning/ROADMAP.md` — Phase 41 success criterion 4, reworded (one line changed, criteria 1–3 byte-identical)
- `.planning/STATE.md` — two new `ACCEPTED` blocker entries (the Apple exposure; the absent vendor round trip); seven new `[Phase 41]` decision lines (taking the phase's total in that section to 16); the Current Position block and a Phase 41 outcome paragraph; the disk-truth count check recorded as a comment

## Decisions Made

- **Resolved-by-precedence is a third category, not a softer conflict.** A flagged conflict in this ledger means the project knowingly diverges from binding text. For the lock order the binding text says what to do and the code does it, so flagging it would misfile obedience as divergence. It is counted once, in the set of divergences, because the brief-to-code difference is still real.
- **The 422 collapse is a divergence, the absent `verification_required` is not.** The client genuinely sees a different status for an empty device token, so it is recorded and counted in the set. `verification_required` has no producer outside the deferred web branch, so it dissolves with D-01 exactly as Phase 40's declaration-dependent rejections dissolved with its D-01 — counted at neither end.
- **A-15 was verified before acting and left alone.** Plan 41-02 had already closed it in place, with the original measurement, `db.pool_size: 12`, the `resilience.pool_size × 2 + 2` relation and `config/config.yaml` all named. D-21's ask was already satisfied; closing it a second time would have added a duplicate entry and cost the history the entry exists to keep.
- **The Apple exposure is recorded in two places on purpose.** `REQUIREMENTS.md` needs it because the header's divergence count includes it; `STATE.md` needs it because that is where the next phase reads accepted risk. Phase 40 recorded the Firebase one the same way, so the two read as one pattern rather than two unrelated notes.
- **The counts were re-derived before being stated, and the invariants produced nothing.** All four new conflicts are against the brief. Not one of the six `SHARED-INVARIANTS.md` sections yielded a new divergence — § Grants' one-evaluation-time rule is in fact now *more* satisfied than before, because `get_evaluated_at` made it structural rather than a convention two call sites must remember.

## Deviations from Plan

### Plan-literal deviations

**1. Task 3's A-15 half was already done, and was verified rather than repeated**

- **Found during:** Task 3
- **Issue:** The plan's action text asks to "mark A-15 resolved in place … and add what closed it, with the value that shipped and the file it was set in." Plan 41-02 had already done exactly that on 2026-09-02. The upstream brief warned about this and asked for the state to be verified before acting.
- **Resolution:** Verified the existing entry against all three of Task 3's acceptance criteria for it — resolved in place ✓, original measurement retained ✓, value and file named ✓ — and changed nothing. `s.count('RESOLVED')` is 2 as the verify requires, unchanged.
- **Impact:** none. Writing a second closure would have produced a duplicate entry and diluted the history the entry exists to preserve.

**2. `requirements.mark-complete` was a no-op, and the traceability row was updated by hand**

- **Found during:** the requirements gate
- **Issue:** `requirements.ready-ids` released all three IDs (`3/3 requirement(s) ready to mark complete`) — the shared-ID gate cleared because this is the last declaring plan, exactly as the upstream brief predicted. `requirements.mark-complete` then returned `updated: false` with all three under `table_unmatched` and every `write_set` entry `applied: false`.
- **Cause:** the checkboxes were already `[x]` (Task 1 set them, because that task's own `<verify>` requires exactly three met marks inside the ANONGRANT block), so there was nothing to flip; and the traceability row is a **range** row — `| ANONGRANT-01 … ANONGRANT-03 | Phase 41 | … |` — which the tool cannot address per-ID. Every other endpoint phase in that table uses the same range form, which is why prior phases also edited it by hand.
- **Resolution:** the row was updated in Task 1's commit, from `Pending` to `Complete` with a note naming what each of the three carries. Reported rather than worked around: the `table_unmatched` result is a property of the table's range rows, not a failure of this plan.
- **Impact:** none on the ledger's content. Worth knowing for Phase 42, which will hit the identical result on `REGGRANT-01 … REGGRANT-03`.

### Auto-fixed Issues

None. No bug, missing critical functionality or blocker was encountered — three tasks, three commits, no fix attempts.

---

**Total deviations:** 2, both plan-literal readings resolved by verifying the world rather than by writing what the plan predicted.
**Impact on plan:** No scope was added and no decision was reinterpreted. Both deviations are instances of the same rule the plan itself states — read the state, do not assume it.

## Verification

Re-run whole after the final task commit. **The suite numbers quoted in the amendments were re-run here rather than only quoted from `41-04-SUMMARY.md`**, so the met marks rest on a result this plan observed:

| Check | Result |
|---|---|
| `uv run pytest -q` | **950 passed**, 360 deselected |
| `uv run pytest -m e2e -q` | **226 passed** |
| `uv run pytest -m schema -q` | **134 passed** |
| `uv run ruff check src tests` | **All checks passed!** (exit 0) |
| ANONGRANT block shape (length, dated entries, `flagged`, met marks) | `29226 13 7 3` — three met marks, as required |
| Phase 41 ROADMAP section (`'mode signal' in p`, `'challenge' in p`) | `False True` |
| `git diff --stat .planning/ROADMAP.md` | 1 file, 1 insertion, 1 deletion |
| STATE.md (`'A-15' in s`, `count('RESOLVED')`, DeviceCheck named) | `True 2 True` |
| Sibling summaries on disk while Task 3 ran | 4 |
| Specification directory | unchanged — `06-claim-anonymous-grant.md` mtime 2026-08-18, `SHARED-INVARIANTS.md` 2026-09-01, neither in any commit of this plan |
| Blocker entries deleted by `git diff .planning/STATE.md` | 0 |

## Issues Encountered

None. Both surprises — A-15 already closed, and `mark-complete` unable to address a range row — are recorded above as plan-literal deviations rather than problems, because in both cases the state on disk was already what the plan wanted and the correct action was to verify and report.

## Known Stubs

None. This plan produces no source symbols, introduced no placeholder or TODO marker, and skipped no test. Nothing was appended to `.planning/WINDOWS.md`: this plan left no defect to record.

## Threat Flags

None. The plan's register (T-41-26 … T-41-30, T-41-SC) is fully mitigated: no specification file was edited (T-41-28), every divergence is recorded under the requirement it belongs to (T-41-26), every dead obligation is named with the decision that removed it (T-41-27), the vendor exposure and the absent round trip are both recorded as accepted rather than as oversights (T-41-29), and the three files received no configuration value, key material or token (T-41-30). T-41-SC is unreachable — nothing was installed and no dependency manifest was touched.

## User Setup Required

None. Nothing beyond what 41-01 already recorded — the three `DEVICECHECK_*` variables in `.env.example`, whose absence is a supported mode: boot proceeds with a logged warning and the route fails closed as 503.

## Next Phase Readiness

**Phase 41 is complete: 5 of 5 plans, all five summaries on disk.** The endpoint ships, every claim it makes is executed rather than argued, and the ledger now describes what shipped rather than what was asked for.

What Phase 42 inherits from this plan specifically:

- **A ledger it must extend, not restart.** `REGGRANT-01 … REGGRANT-03` will hit the same range-row behaviour in the traceability table, and the counts it inherits are **ten** and **sixteen** — to be re-derived, not copied.
- **Two checks that will fail by name if it does the wrong thing**, both already recorded here: `test_the_named_set_equals_the_live_index_predicate` if it narrows `FREE_GRANT_SOURCES`, and `TestTheActivationAddsNoThirdLockTier` if its registered-account writer locks an identity or user row ahead of the grant rows.
- **An untouched bit1 and the other arm of the anti-abuse CHECK**, so the registered claim still costs no migration.
- **The fallback D-08 declined**, recorded under Deferred Ideas in `41-CONTEXT.md` — a registered user whose provider account already spent its grant — which is Phase 42's question to answer, not a gap this phase left.

**Concerns carried forward, none new:**

- **No real round trip to Apple has ever been made.** The wire shapes are `[ASSUMED]` from secondary sources. The first real 400 or 401 from Apple is authoritative over anything in this repository. Now recorded in `STATE.md` where the next reader finds it.
- **The expire-after-rollback hazard 41-04 fixed is proven only at the service layer.** No case drives two concurrent HTTP requests through the router, and the same hazard exists anywhere a service rolls back and its caller then reads a previously loaded instance. Open as coverage `D8` with `human_judgment: true`.
- **`EDGE-ANONGRANT-03-unclassified` remains unresolved.** The negative half of ANONGRANT-03 is bounded by a walk over today's `src/`, which is a grep-shaped guarantee rather than a database one. Stated as it is under ANONGRANT-03 rather than closed with a criterion that would read stronger than the check.
- **The unbounded Apple exposure is accepted, not fixed**, and closes with the v2.1 gateway contract — the same fate as Phase 40's Firebase exposure and Phase 37's unlimited account creation.

---
*Phase: 41-post-auth-claim-anonymous-grant*
*Completed: 2026-09-03*

## Self-Check: PASSED

`41-05-SUMMARY.md` exists on disk and all three modified files are present; all four commits resolve in `git log --all` (`27ba524`, `12e76e5`, `09cd60f`, `1bd8fed`). Every task's acceptance criteria were executed, and the plan-level verification block above was re-run whole after the final task commit. **One correction made after the first summary commit:** the decision-line count read 15/six-added and is in fact **16/seven-added** — `grep -c '^- \[Phase 41\]' .planning/STATE.md` returns 16. Task 3's commit message still says "six" and is left as written; the count here is authoritative.
