---
phase: 39-get-users-me
plan: 02
subsystem: docs
tags: [conventions, layering, requirements, agents-md, amendments]

# Dependency graph
requires:
  - phase: 38-post-auth-sync
    provides: The dated-amendment format under a requirement bullet (D-05 precedent) that this plan copies
  - phase: 35-purchase-and-grants
    provides: D-05's deletion of the backend `limits` engine — the ground for the rate-limit omission recorded here
provides:
  - "AGENTS.md § Package layout states the router-to-crud rule: a router may call `crud/` directly, and a `services/` class is earned by the router body becoming too big or complicated"
  - "The `Depends()`-only constraint on handlers, restated explicitly so the new latitude is not read as permission to construct a database class inline"
  - "A dated Phase 39 amendment under PROF-01 recording D-03's divergence from the brief's handler step 1 and D-02's omission of the `users_me` rate-limit entry"
affects: [39-01, 40-upgrade-anonymous, 41-claim-anonymous-grant, 42-claim-registered-grant, any later phase writing a router]

# Actuals (#2632) — chars/4 over the two files actually changed (127387 chars), the same
# whole-file scale the plan's estimate of 20000 was built on. The realized diff alone is 5048 chars.
actuals:
  tokens: 31847
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Router-to-crud direct call; a service is earned by complexity, not assumed by category"
    - "A divergence from a verbatim brief is recorded as a dated amendment where the requirement lives, never edited into the brief"

key-files:
  created: []
  modified:
    - AGENTS.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "The amendment restates `Depends()` only as its own paragraph rather than relying on the bullet alone — the new latitude is about which layer a handler calls, not about how it obtains its collaborators"
  - "The `services/` bullet was reworded to `business logic a router body has outgrown`, so the layer is defined by the condition that produces it rather than by category"
  - "The rule is stated as binding new code with the existing services explicitly left alone, so no later agent reads it as a refactor instruction"
  - "Both divergences went into one amendment block under PROF-01 rather than two, because they share a subject: where this phase departs from `04-users-me.md`"

patterns-established:
  - "Layering: handler in routers/, queries in crud/, a services/ class only when the handler body would otherwise be too big or complicated"

requirements-completed: []  # Deliberately empty — see Deviations. The plan prohibits ticking either PROF box; the phase is not complete at this point.

coverage:
  - id: D1
    description: "AGENTS.md § Package layout states the router-to-crud rule while keeping the Depends()-only clause and all four numbered exceptions"
    requirement: "PROF-01"
    verification:
      - kind: other
        ref: "grep -n 'routers/' AGENTS.md | grep -cF 'Depends()' == 1"
        status: pass
      - kind: other
        ref: "grep -cE '^[1-4]\\. ' AGENTS.md == 4"
        status: pass
      - kind: other
        ref: "grep -c 'the rejection stays with' AGENTS.md == 1"
        status: pass
      - kind: unit
        ref: "uv run pytest -q (767 passed, 311 deselected)"
        status: pass
    human_judgment: true
    rationale: "The plan specifies a human-check: the amended section must be read end to end against D-05's wording. The greps prove the constraints survived; they cannot prove the new rule reads as the developer stated it, or that it matches the file's register."
  - id: D2
    description: "A dated Phase 39 amendment under PROF-01 records D-03's divergence from handler step 1 and D-02's omission of the users_me rate-limit entry, with PROF-02's Phase 37.1 block untouched and no brief under specs/ edited"
    requirement: "PROF-01"
    verification:
      - kind: other
        ref: "grep -c 'Amended by Phase 39' .planning/REQUIREMENTS.md == 1"
        status: pass
      - kind: other
        ref: "awk '/PROF-01/,/PROF-02/' .planning/REQUIREMENTS.md | grep -c 'Amended by Phase 39' == 1"
        status: pass
      - kind: other
        ref: "grep -c 'expire_on_commit' .planning/REQUIREMENTS.md == 1"
        status: pass
      - kind: other
        ref: "awk '/### PROF/,/### UPGRADE/' .planning/REQUIREMENTS.md | grep -c '^- \\[x\\]' == 0"
        status: pass
      - kind: other
        ref: "git diff --numstat -- .planning/REQUIREMENTS.md == 5 insertions / 0 deletions (PROF-02's block byte-identical)"
        status: pass
    human_judgment: false

# Metrics
duration: 10min
completed: 2026-09-01
status: complete
---

# Phase 39 Plan 02: Documentation Deliverables Summary

**AGENTS.md § "Package layout" now lets a router call `crud/` directly with a `services/` class earned by complexity, and PROF-01 carries a dated Phase 39 amendment recording the detached-row profile read and the absent rate-limit entry**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-09-01T20:20:00-07:00
- **Completed:** 2026-09-01T20:30:23-07:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **The layering rule D-05 asked for is in `AGENTS.md`**, in the file's own register: a router may call `crud/` directly, a `services/` class is introduced when the router body would otherwise become too big or complicated, and a service is earned by complexity rather than assumed by category. The one-awaited-read case is named explicitly and pointed at § "Function shape", which is the rule the amendment leans on.
- **The constraints that make the new latitude safe survived and are asserted.** The `routers/` bullet keeps `Depends()` only, and a following paragraph restates it — take the session and the barrier from a dependency, never construct a database class in the body — so no later agent reads "call `crud/` directly" as permission to skip the dependency. All four numbered exceptions are intact, exception 4 included; it is what places this phase's fail-closed raise in `crud/purchases.py`.
- **The amendment binds new code only.** "The rule binds new code; leave the existing services as they are" is stated in the section, so `SyncService`, `AuthService`, `QuotaService` and `ChatService` are not reopened by a later reader.
- **Both of this phase's divergences from `04-users-me.md` are on the record under PROF-01**, dated, naming their decision ids, each stating what the brief says, what the phase does instead, and the ground. No file under `specs/` was touched.

## Task Commits

1. **Task 1: Amend the layering rule (D-05)** - `32b018b` (docs)
2. **Task 2: Record this phase's two divergences under PROF-01** - `0058ee8` (docs)

## Files Created/Modified

- `AGENTS.md` - § "Package layout": `services/` and `routers/` bullets reworded, three paragraphs added stating the router-to-crud rule, the surviving `Depends()`-only constraint, and that the rule binds new code. +15 / -2.
- `.planning/REQUIREMENTS.md` - One dated amendment blockquote appended under the PROF-01 bullet, covering D-03 and D-02. +5 / -0.

## Decisions Made

- **The `Depends()`-only rule got its own paragraph, not just the bullet it already had.** The plan required the clause to survive; the risk it guards against is a reader taking "a router may call `crud/`" as licence to instantiate a database class in the handler. Stating the constraint next to the new latitude is what prevents that reading, and it costs three lines.
- **`services/` is now defined by the condition that produces it** — "business logic a router body has outgrown" — rather than by the category "business logic". The old wording is what implied every business operation routes through a service, and that implication is exactly what D-05 supersedes.
- **One amendment block, not two.** The Phase 38 precedent uses one dated blockquote per requirement carrying several paragraphs. Both divergences share a subject and a phase, so they are two bolded paragraphs inside one block; this also keeps `grep -c "Amended by Phase 39"` at 1, as the plan's criteria require.
- **The amendment cites `04-users-me.md:41`, `:26` and `:52` by line.** A later reader can find the brief text being diverged from without re-reading the whole brief, and the citation makes it evident the divergence is from something specific rather than from a general impression.

## Deviations from Plan

**1. [Criterion correction, no code change] Task 2's `Amended by Phase 37.1` acceptance criterion is unsatisfiable as literally written**
- **Found during:** Task 2, before editing
- **Issue:** The criterion reads *"`grep -c "Amended by Phase 37.1" .planning/REQUIREMENTS.md` equals 1 — the existing PROF-02 block survives"*. That string occurs **3 times file-wide at baseline** (lines 12, 143 and 215); only line 215 is PROF-02's. Satisfying the number literally would mean deleting two unrelated Phase 37.1 amendment blocks, which the plan's own prohibitions forbid.
- **Fix:** The criterion's stated *intent* — PROF-02's block survives — was verified instead, by two checks that prove it more strongly than the count would: the file-wide count is **unchanged at 3** before and after, and `git diff --numstat` for the commit is **5 insertions, 0 deletions**, so nothing existing was reworded or removed and PROF-02's block is byte-identical.
- **Files modified:** None (verification substitution)
- **Verification:** `grep -c "Amended by Phase 37.1"` = 3 before, 3 after; `git diff --numstat` = `5 0 .planning/REQUIREMENTS.md`
- **Committed in:** n/a — the plan file was not edited; the miscount is recorded here rather than corrected in `39-02-PLAN.md`

**2. [Prohibition over template default] `requirements-completed` left empty**
- **Found during:** Summary creation
- **Issue:** The summary template says to copy all IDs from the plan's `requirements` frontmatter (`PROF-01`, `PROF-02`). The plan's prohibitions say **"No requirement checkbox is ticked by this plan — the phase is not complete at this point."** Populating the field would signal completion of requirements whose endpoint does not yet exist in this worktree.
- **Fix:** `requirements-completed: []`, with the reason stated inline in the frontmatter. PROF-01/PROF-02 are completed by the phase as a whole once `39-01` ships the endpoint, not by this documentation plan.
- **Files modified:** `.planning/phases/39-get-users-me/39-02-SUMMARY.md`
- **Verification:** `awk '/### PROF/,/### UPGRADE/' .planning/REQUIREMENTS.md | grep -c '^- \[x\]'` = 0 — neither box was ticked in the requirements file either
- **Committed in:** the summary commit

**3. [Environment note] `git status --porcelain specs/` is trivially empty**
- **Found during:** Task 2 verification
- **Issue:** The criterion assumes `specs/` is tracked in this repository. It is not — the briefs live at `/home/init/native-speaker/specs/`, outside the `ns-api-gateway` repo, so the command can never report a modification here.
- **Fix:** Verified equivalently with `git diff --name-only HEAD | grep -c '^specs/'` = 0, and by the fact that every access to `04-users-me.md` in this plan was a `grep`. No write of any kind was issued against a file under `specs/`.
- **Files modified:** None
- **Verification:** `git status --short` clean; working diff touched only the two intended files
- **Committed in:** n/a

---

**Total deviations:** 3 (1 unsatisfiable criterion verified by intent, 1 template default overridden by an explicit plan prohibition, 1 environment assumption noted)
**Impact on plan:** None on substance. Every `must_have` truth and every prohibition holds; no fix altered what the plan asked to be written.

## Issues Encountered

None. The suite was green before the first edit (767 passed, 311 deselected) and green after both (same counts), and `uv run ruff check` reported "All checks passed!" throughout — as expected for a plan that changes no code.

## Known Stubs

None.

## Threat Flags

None. This plan changes two documentation files and introduces no network endpoint, auth path, file access pattern or schema change. T-39-08 and T-39-09 are mitigated as the threat model specifies (the `Depends()`-only clause and all four exceptions were asserted intact before commit; both divergences are dated and name their decision ids). T-39-10 holds: nothing under `specs/` was written.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **`39-01` can rely on the amended rule.** `routers/users.py` calling `crud/purchases.py` with no `ProfileService` is now the documented layering, not a divergence needing its own justification, and exception 4 still places `MissingPurchaseTokenError`'s raise in `crud/`.
- **Later phases inherit the rule.** Phases 40-42 write routers under it; a handler that grows past one or two reads is expected to earn a service rather than default to one.
- **No blockers.** The two files this plan owns are complete and committed; nothing else in the phase depends on them being read first.

## Self-Check: PASSED

- `AGENTS.md` — FOUND, modified, +15/-2
- `.planning/REQUIREMENTS.md` — FOUND, modified, +5/-0
- `.planning/phases/39-get-users-me/39-02-SUMMARY.md` — FOUND
- Commit `32b018b` — FOUND
- Commit `0058ee8` — FOUND
- Working tree clean; no file deleted by any commit in this plan

---
*Phase: 39-get-users-me*
*Completed: 2026-09-01*
