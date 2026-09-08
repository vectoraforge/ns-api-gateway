---
phase: 46-post-auth-sign-out-all
plan: 05
subsystem: testing
tags: [requirements, roadmap, state, records, asd-ste100]

# Dependency graph
requires:
  - phase: 46-post-auth-sign-out-all
    provides: "plans 46-01 … 46-04 — the route, the seam method, the leaf, the re-written literals, the unit twins and the wire refusals this plan records"
  - phase: 38-post-auth-sync
    provides: "D-03/D-04 — the audit settlement that made SIGNOUT-02's audit half inherit-free and criterion 3 answerable"
  - phase: 45-post-auth-restore-subscription
    provides: "the RESTORE-01 amendment shape this entry follows, and D-13, the operation-label precedent D-08 weighs against"
provides:
  - "The dated SIGNOUT-01 and SIGNOUT-02 amendment entries in .planning/REQUIREMENTS.md"
  - "Two closed forward flags: the adapter seam (Phase 37.2 D-09) and the sign_out_all operation label (Phase 40 D-11)"
  - "One new flagged conflict against 11-sign-out-all.md, D-06, by brief line"
  - "The inventory of six obligations already dead before this phase, each by brief line and by the phase that removed the mechanism"
  - "The unbounded Firebase revocation write recorded as an accepted, uncounted divergence"
  - "The re-derived header counts: thirty-one conflicts, forty-two divergences, eleven uncounted"
  - "Four v2.0 decision lines and the Phase 46 outcome paragraph in .planning/STATE.md"
  - "The rewritten Phase 46 success criteria in .planning/ROADMAP.md"
affects: [46-verification, 47, milestone-close]

actuals:
  tokens: 11284
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A header count is re-derived by enumerating the file's own list, never by incrementing the previous number"
    - "A textual collision between a dead specification value and a live class name is called out in the record, with a sentence saying which of the two exists"

key-files:
  created:
    - .planning/phases/46-post-auth-sign-out-all/46-05-SUMMARY.md
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "The `11-sign-out-all.md` sha256 gate was run before Task 1 and again after it: the brief and SHARED-INVARIANTS.md are byte-identical to their pre-phase state, so every divergence lives in REQUIREMENTS.md and nowhere else (D-10)."
  - "The header's three numbers were enumerated from the file rather than incremented: eleven per-requirement conflict groups sum to thirty-one, the uncounted list's own (1)…(11) markers sum to eleven, and forty-two is their sum."
  - "The Phase 43 D-09 sentence calling itself 'an eleventh divergence' was left as written and corrected in this phase's amendment paragraph, per the convention this file uses for superseded text."
  - "The two known mistakes are described as two arms of one except chain rather than as 'two orderings', because only one of them is an ordering: the second is a classification copied from the read."
  - "The ROADMAP Progress table row reads 5/5 with status `In Progress`: the orchestrator's verification step marks the phase complete, not this plan."

patterns-established:
  - "A phase-close plan runs its suites before it writes anything, so every number in the record comes from one measured run rather than from four plan summaries."

requirements-completed: [SIGNOUT-01, SIGNOUT-02]

coverage:
  - id: D1
    description: "Both forward flags standing under SIGNOUT-01 are closed: the adapter seam by D-01, and the sign_out_all operation label by D-08."
    requirement: SIGNOUT-01
    verification:
      - kind: other
        ref: "test \"$(grep -c 'SIGNOUT-01' .planning/REQUIREMENTS.md)\" -ge 12 — reads 13"
        status: pass
    human_judgment: false
  - id: D2
    description: "The one departure from 11-sign-out-all.md, D-06's 401 on a Firebase no-such-user, is recorded as a dated flagged conflict by brief line."
    requirement: SIGNOUT-01
    verification:
      - kind: other
        ref: "test \"$(grep -c 'D-06' .planning/REQUIREMENTS.md)\" -ge 1 — reads 53"
        status: pass
      - kind: other
        ref: "test \"$(grep -c '11-sign-out-all.md' .planning/REQUIREMENTS.md)\" -ge 10 — reads 11"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every obligation the brief states that was already dead before this phase is listed by brief line and by the phase that removed its mechanism."
    requirement: SIGNOUT-01
    verification: []
    human_judgment: true
    rationale: "Six inventory items, each a prose claim tying a brief line to a prior phase decision. No command can assert that the six are the right six or that each line reference is the right line; a reader must compare the entry against the brief."
  - id: D4
    description: "The unbounded Firebase revocation write per attempt is recorded as an accepted, uncounted divergence rather than filed as a defect."
    requirement: SIGNOUT-01
    verification: []
    human_judgment: true
    rationale: "The judgment is whether accepting the exposure is right for this product, which no test can decide. The record's own consistency was checked: the item is (11) in the uncounted list and is absent from the conflict enumeration."
  - id: D5
    description: "SIGNOUT-01 and SIGNOUT-02 are marked met on suite counts measured in this plan, not copied from Phase 45."
    requirement: SIGNOUT-02
    verification:
      - kind: unit
        ref: "uv run pytest -q — 1281 passed, 577 deselected"
        status: pass
      - kind: e2e
        ref: "uv run pytest -m e2e -q — 348 passed, 1510 deselected"
        status: pass
      - kind: other
        ref: "uv run pytest -m schema -q — 229 passed, 1629 deselected (the untouched-suite control)"
        status: pass
      - kind: other
        ref: "uv run ruff check src tests — All checks passed!"
        status: pass
      - kind: other
        ref: "test \"$(grep -c '\\- \\[ \\] \\*\\*SIGNOUT-01' .planning/REQUIREMENTS.md)\" = 0 — reads 0"
        status: pass
    human_judgment: false
  - id: D6
    description: "ROADMAP success criterion 3 states what was built and no longer says Phase 46 must decide."
    requirement: SIGNOUT-02
    verification:
      - kind: other
        ref: "test \"$(grep -c 'BLOCKED: requires a mechanism Phase 37.1 deleted' .planning/ROADMAP.md)\" = 0 — reads 0"
        status: pass
    human_judgment: false
  - id: D7
    description: "The four v2.0 decisions and the Phase 46 outcome paragraph are in STATE.md, where a later phase reads decisions."
    requirement: SIGNOUT-02
    verification:
      - kind: other
        ref: "test \"$(grep -c 'Phase 46 outcome' .planning/STATE.md)\" = 1 — reads 1"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'sign_out_all_confirmed' .planning/STATE.md)\" -ge 1 — reads 1"
        status: pass
    human_judgment: false
  - id: D8
    description: "The files under /home/init/native-speaker/specs are byte-identical to their pre-phase state (D-10)."
    requirement: SIGNOUT-01
    verification:
      - kind: other
        ref: "sha256sum -c on 11-sign-out-all.md and SHARED-INVARIANTS.md — both OK, exit 0"
        status: pass
    human_judgment: false

duration: 15 min
completed: 2026-09-08
status: complete
---

# Phase 46 Plan 05: The phase record Summary

**The one departure from `11-sign-out-all.md` — a 401 on a Firebase "no such user" — is now a dated,
line-referenced flagged conflict; both forward flags standing under SIGNOUT-01 are closed; and the
header's counts were re-derived from the file at thirty-one conflicts, forty-two divergences and a
gap of eleven.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-09-08T23:36Z
- **Completed:** 2026-09-08T23:51Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- **The suites were run before anything was written**, so every number in the record comes from one
  measured run in this plan rather than from four plan summaries: **1281 unit / 348 e2e / 229
  schema**, `uv run ruff check src tests` clean. The schema count is the control and reads exactly
  what Phase 45 left, which is the evidence that this phase moved nothing outside its own scope.
- **Two forward flags are closed on this route's own terms.** The adapter-seam flag Phase 37.2
  raised on 2026-08-25 is answered by D-01: the revocation method is declared beside its first
  implementation, so `FirebaseAdminAdapter` carries two methods and no `RevocationOutcome` value
  type came back. The `sign_out_all` operation-label flag Phase 40 raised on 2026-09-02 is answered
  by D-08: no label, four values kept, migration unedited. The entry states in words that Phase 45's
  matching decision is a precedent and not the answer.
- **One new flagged conflict is recorded, not resolved.** D-06's 401 is written against
  `11-sign-out-all.md:59`, `:62` and `:24`, with the ground, the rejected alternative — a 503 for up
  to an hour until the ID token expires — and the case that demonstrates it on the wire. The brief
  is not edited.
- **Six obligations that were already dead are inventoried**, each by brief line and by the phase
  that removed the mechanism, so a later reader does not read them as unmet work. The inventory
  calls out the textual collision it contains: the brief's dead `core.auth_event_result` value and
  this phase's new error class both read `revocation_unconfirmed`, and only the log event name
  derived from `RevocationUnconfirmed` exists.
- **The header's three numbers were enumerated rather than incremented.** The eleven per-requirement
  conflict groups sum to thirty-one; the uncounted list's own `(1)`…`(11)` markers sum to eleven;
  forty-two is their sum. Phase 43 D-09's "an eleventh divergence" sentence is now stale and is
  corrected in this phase's amendment paragraph rather than edited in place.
- **ROADMAP criterion 3 no longer hands Phase 46 a decision Phase 38 settled.** It states what was
  built: one 503 leaf whose class name is its WARNING event name, one INFO line carrying the
  identity row id, the middleware `request` line per attempt, and no durable row.

## Task Commits

Each task was committed atomically:

1. **Task 1: Amend SIGNOUT-01 and SIGNOUT-02 and re-derive the header counts** - `ce8a138` (docs)
2. **Task 2: Record the decisions in STATE.md and rewrite the ROADMAP criteria** - `c00ee88` (docs)

**Plan metadata:** the commit carrying this file.

## Files Created/Modified

- `.planning/REQUIREMENTS.md` - SIGNOUT-01 and SIGNOUT-02 checked and given seven new dated
  blockquote entries between them; the Phase 46 amendment paragraph added to the header; the counts
  paragraph re-derived at thirty-one, forty-two and eleven, with the new conflict added to the
  enumeration and the new uncounted item added as `(11)`
- `.planning/STATE.md` - four v2.0 decision lines (D-01/D-02, D-05, D-06, D-07); the Phase 46
  outcome paragraph with its disk-read counting note; `completed_plans` and the Current Position
  progress line corrected by count
- `.planning/ROADMAP.md` - criterion 3 rewritten in full and criteria 1, 2 and 4 marked with what
  answers each; the plan checklist entry for 46-05 checked; the Progress table row moved to 5/5

## Decisions Made

- **The two known mistakes are described as two arms of one `except` chain**, not as "two
  orderings". Only the first is an ordering — `auth.UserNotFoundError` must precede its own
  superclass `exceptions.FirebaseError`. The second is a classification: the `ValueError` arm must
  raise `RevocationUnconfirmed` rather than `RetryableLookupError`, because the SDK validates the
  uid before it sends the request. Writing both as orderings would have made the record wrong about
  one of them.
- **The Progress table row stays `In Progress` at 5/5.** The orchestrator's verification step marks
  the phase complete; this plan's writes are plan-level only.
- **The sha256 gate was run twice**, once before Task 1 and once after, so the "not edited" claim is
  measured at the moment the amendment landed rather than assumed from the start of the plan.
- **The `TestTheLookupArmsCarryStageAndOnlyABoundedCause` sample is recorded as knowingly left**, in
  the STATE.md outcome paragraph, rather than closed by this plan. It is a hand-picked three-arm
  sample, it does not name `RevocationUnconfirmed`, and nothing fails.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] The ROADMAP Progress table row was left `In Progress`, against the plan's acceptance criterion**

- **Found during:** Task 2
- **Issue:** The plan's acceptance criterion reads "The Phase 46 row of the ROADMAP Progress table
  shows the phase complete with its plan count." The execution instructions for this plan forbid
  marking the phase itself complete — verification runs after this plan and owns that write. A
  `Complete` status here would assert a verification result that does not exist yet.
- **Fix:** The row reads `5/5` with status `In Progress` and an empty completion date. The plan
  count half of the criterion is met; the status half is deliberately left to the verification step.
- **Files modified:** `.planning/ROADMAP.md`
- **Verification:** `grep '^| 46\.' .planning/ROADMAP.md` reads `5/5 | In Progress|`.
- **Committed in:** `c00ee88` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** No scope change. One acceptance criterion is met in part, by design, because the
write it asks for belongs to a later step.

## Issues Encountered

None. Both tasks are record writes; no source file was read for edit and none was changed.

## Verification Results

| Gate | Result |
|---|---|
| `uv run pytest -q` | 1281 passed, 577 deselected |
| `uv run pytest -m e2e -q` | 348 passed, 1510 deselected |
| `uv run pytest -m schema -q` | 229 passed, 1629 deselected — the control, unchanged from Phase 45 |
| `uv run ruff check src tests` | All checks passed, exit 0 |
| `grep -c 'SIGNOUT-01' .planning/REQUIREMENTS.md` >= 12 | pass (13) |
| `grep -c '11-sign-out-all.md' .planning/REQUIREMENTS.md` >= 10 | pass (11) |
| `grep -c 'D-06' .planning/REQUIREMENTS.md` >= 1 | pass (53) |
| `grep -c '\- \[ \] \*\*SIGNOUT-01' .planning/REQUIREMENTS.md` = 0 | pass (0) |
| `sha256sum -c` on `11-sign-out-all.md` and `SHARED-INVARIANTS.md` | pass, both OK |
| `grep -c 'Phase 46 outcome' .planning/STATE.md` = 1 | pass (1) |
| `grep -c 'BLOCKED: requires a mechanism Phase 37.1 deleted' .planning/ROADMAP.md` = 0 | pass (0) |
| `grep -c 'sign_out_all_confirmed' .planning/STATE.md` >= 1 | pass (1) |
| No file deleted by either commit | pass — `git diff --diff-filter=D` empty across both |

### Prohibitions

| Statement | Status |
|---|---|
| A divergence from the binding brief must not be resolved by editing the brief. | verified — the sha256 gate passes after Task 1; both spec files are byte-identical to their pre-phase state |
| No operation label is added to `core.auth_operation` and the single migration is not edited (D-08). | verified — no commit in this phase touches `migrations/`; the D-08 entry states the four values are kept |
| No durable audit row and no audit writer is reintroduced by this record. | verified — the SIGNOUT-02 entry states the audit half was settled by removal and that nothing durable is written |
| Suite counts must not be carried forward from an earlier phase's paragraph. | verified — all four commands were run in this plan before any file was edited, and the schema control reads 229 |

## Known Stubs

None. This plan writes prose records; it returns no placeholder value and adds no code.

**Knowingly left open, recorded rather than closed:**
`TestTheLookupArmsCarryStageAndOnlyABoundedCause` at `tests/unit/test_rejection_vocabulary.py` is a
hand-picked three-arm sample and does not name `RevocationUnconfirmed`. It is green and nothing
fails. It is recorded in the STATE.md Phase 46 outcome paragraph so a later plan finds it.

## Threat Flags

None. This plan adds no surface: it edits three files under `.planning/` and imports nothing.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Phase 46 is executed and awaits verification.** All five plans have summaries. The record a
verifier needs is in place: SIGNOUT-01 and SIGNOUT-02 are checked with their evidence, the ROADMAP
criteria state what answers each, and the departures are dated and line-referenced.

**Two items a verifier or a later phase should carry forward.**

1. **Assumption A1 is production-only exposure.** The mapping from the Identity Toolkit's
   `accounts:update` answer for a non-existent account to `USER_NOT_FOUND` is read from the
   installed SDK source and corroborated by an upstream issue report. It is not probed against a
   live project, and both suites pass either way because every case scripts the exception directly.
   One real-credential call against a deleted uid would settle it.
2. **The unbounded Firebase revocation write** is the sixth accepted residual this project carries
   and the first that is a **write** at the provider. It closes with the v2.1 gateway contract, and
   `/auth` paths are in no HTTPRoute today.

---
*Phase: 46-post-auth-sign-out-all*
*Completed: 2026-09-08*

## Self-Check: PASSED

`.planning/phases/46-post-auth-sign-out-all/46-05-SUMMARY.md` exists on disk. Both task commits,
`ce8a138` and `c00ee88`, are in the log. All three modified files exist. Every gate in the table
above was run in this plan; none was copied.
