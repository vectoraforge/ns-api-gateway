---
phase: 43-post-webhooks-app-store
plan: 06
subsystem: planning
tags: [requirements, roadmap, state, divergences, provider-callback, documentation]

# Dependency graph
requires:
  - phase: 43-01
    provides: "the partition, the seam, the service, and the residual it asked this plan to record in its own wording"
  - phase: 43-02
    provides: "the gateway rename and the deferral that compounds with that residual"
  - phase: 43-03
    provides: "the attribution decision and the `identity_value` correction against the plan's paraphrase"
  - phase: 43-04
    provides: "the grant writer, the two lock tiers, and the superseded `manual` grant as a recorded consequence"
  - phase: 43-05
    provides: "the executed race that closed 43-01's last evidence gap, and the environment gate"
  - phase: 42-06
    provides: "the amendment shape, the count re-derivation method, and the measured `table_unmatched` result"
provides:
  - "APPLEHOOK-01: three flagged conflicts, the Apple-guidance divergence, the dead-obligation inventory, and the accepted residual"
  - "APPLEHOOK-02: ANSWERED AND CLOSED — the mechanism Phase 44 reads instead of inventing a second partition"
  - "The re-derived counts: nineteen flagged conflicts, twenty-seven known divergences, a gap of eight"
  - "ROADMAP Phase 43 criterion 3, answered in the roadmap itself"
  - "STATE.md: the Phase 43 outcome, thirteen decisions with their grounds, and three accepted residuals"
affects: [44-webhook-google-play-rtdn, 45-restore-subscription]

actuals:
  tokens: 23987
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A divergence from a third party's guidance is recorded under the requirement but joins neither count, and is named in the header so its absence is not read as its non-existence"

key-files:
  created:
    - .planning/phases/43-post-webhooks-app-store/43-06-SUMMARY.md
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "D-09 is recorded under APPLEHOOK-01 in full but is placed in NEITHER count, because the two numbers measure divergences from the binding specification and neither spec file mandates an online revocation check. Filing it in either number would make the numbers mean two things at once; omitting it silently would hide it. It is named in the header instead."
  - "D-06's absent gateway limits are counted as a flagged conflict even though they are recorded as a deferral, because the brief's text is unamended and the divergence is knowing. The Phase 35 D-05/D-08 precedent supplies the ground, not an exemption from counting."
  - "The unbounded-request residual and D-06's deferral are written as one item seen from two ends, because the same v2.1 gateway limit closes both — 43-02 asked for exactly this."
  - "The 42-07 SQLSTATE spelling was verified against the shipped code before being repeated, and was found wrong; it is corrected in place with a dated note rather than repeated forward."
  - "APPLEHOOK-01 and APPLEHOOK-02 are ticked by hand on both surfaces, because `requirements.mark-complete` applied nothing and returned `table_unmatched` — measured, not predicted."

patterns-established:
  - "A count is re-derived by naming what each invariant section was examined for and stating the null result, so a reader can check the derivation rather than trust the number"
  - "A residual that is wider than its predecessors is written as wider, in the entry itself, rather than filed as one more instance of a known pattern"

requirements-completed: [APPLEHOOK-01, APPLEHOOK-02]

coverage:
  - id: D40
    description: "APPLEHOOK-01 and APPLEHOOK-02 are both ticked and each carries a dated Phase 43 amendment naming what shipped"
    requirement: APPLEHOOK-01
    verification:
      - kind: other
        ref: "grep -c '^- \\[x\\] \\*\\*APPLEHOOK-0' .planning/REQUIREMENTS.md == 2; grep -c 'Phase 43' == 27"
        status: pass
    human_judgment: false
  - id: D41
    description: "The APPLEHOOK-02 amendment names the dedicated router, `PROVIDER_CALLBACK_PATHS`, the exact-path registration, and PLAYHOOK-03 as the inheritor"
    requirement: APPLEHOOK-02
    verification:
      - kind: other
        ref: "`.planning/REQUIREMENTS.md` § APPLEHOOK-02, the 2026-09-04 'ANSWERED' block — four named cases, the § 'Global deletions' satisfaction, the P-05 cost, and the PLAYHOOK-03 paragraph"
        status: pass
    human_judgment: false
  - id: D42
    description: "D-02, D-04 and D-06 are each recorded as a flagged conflict naming what the brief asks and what shipped, and neither specification file is edited"
    requirement: APPLEHOOK-01
    verification:
      - kind: other
        ref: "sha256sum of `08-webhook-app-store.md` and `SHARED-INVARIANTS.md` identical before and after both tasks (a0f5c3bd…, c04c58c2…)"
        status: pass
      - kind: other
        ref: "git status --porcelain -- src tests config k8s migrations — empty after each task"
        status: pass
    human_judgment: false
  - id: D43
    description: "The D-09 entry states that with online checks off the validity window is evaluated at the payload's claimed signing date, and the unbounded-request entry says explicitly that it is wider than the three residuals under 40 D-22, 41 D-20 and 42 D-16"
    requirement: APPLEHOOK-01
    verification:
      - kind: other
        ref: "`.planning/REQUIREMENTS.md` § APPLEHOOK-01, the D-09 block and the 'FLAGGED, NOT COUNTED' block; mirrored as two ACCEPTED entries in `.planning/STATE.md` § Blockers/Concerns"
        status: pass
    human_judgment: false
  - id: D44
    description: "ROADMAP Phase 43 criterion 3 states the answer and no longer says the phase must answer it; criteria 1, 2 and 4 are marked against what shipped; the progress row reads 6/6"
    requirement: APPLEHOOK-02
    verification:
      - kind: other
        ref: "grep -c PROVIDER_CALLBACK_PATHS .planning/ROADMAP.md == 1; 'Phase 43 must answer it' in the Phase 43 block == 0; progress row '| 43. … | 6/6 | Complete | 2026-09-04 |'"
        status: pass
    human_judgment: false
  - id: D45
    description: "The header's flagged-conflict count and the divergence-set count both changed, and the summary table and traceability row agree with them"
    requirement: APPLEHOOK-01
    verification:
      - kind: other
        ref: "header 'Nineteen conflicts' and 'nineteen and twenty-seven'; the Standing table cell reads Nineteen; the traceability row reads Complete — all three read against each other after the edits"
        status: pass
    human_judgment: false
  - id: D46
    description: "Apple actually posts to the documented URL: the Server URLs are set in App Store Connect and a test notification returns one 200"
    requirement: APPLEHOOK-01
    verification: []
    human_judgment: true
    rationale: "Unchanged from 43-02's D4 and carried forward as the phase's one genuinely human deliverable. There is no iOS app and no App Store Connect record, so nothing can be set and no real notification can exist. Recorded in STATE.md as a fact about the world rather than a gap, with the difference from the DeviceCheck entry stated: these wire shapes come from Apple's own installed library and the chain walk runs for real in the unit suite."

duration: 14min
completed: 2026-09-04
status: complete
---

# Phase 43 Plan 06: The Dated APPLEHOOK Amendments and the Phase Close — Summary

**Every divergence this phase made is now written under the requirement it belongs to, with what the brief asks and what shipped; APPLEHOOK-02 — flagged forward on 2026-08-24 and open for eleven days — is answered and closed, so Phase 44 reads a mechanism instead of a question.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-09-04T23:16:00Z
- **Completed:** 2026-09-04T23:30:00Z
- **Tasks:** 2 of 2
- **Files modified:** 3 (0 created, 3 modified) plus this summary

## Accomplishments

- **APPLEHOOK-02 is closed, and closed with the mechanism rather than a description.** The amendment names the dedicated `APIRouter`, states that membership *is* the set of routes registered on it, and names `PROVIDER_CALLBACK_PATHS` as what makes the partition countable — which is precisely the property PLAYHOOK-03's "second and last member" clause needs. It states plainly that `SHARED-INVARIANTS.md` § "Global deletions" still binds and is satisfied by exact-path registration.
- **The cost of that mechanism is recorded, not glossed.** Two cases in `test_app_wiring.py` compute their sets structurally over `app.routes`, so the callback route joined them by itself and both had to take `PROVIDER_CALLBACK_PATHS` into their exemption union. The honest consequence is written down: the structural case now asserts "declares no identity accessor", which the callback route also satisfies, so it no longer holds the public allowlist to one member — **the separate literal case asserting `PUBLIC_PATHS == {"/health/ready"}` is what does.** D-01's own phrasing is marked true as intent and false as that assertion.
- **Three flagged conflicts, each with both halves.** D-02 (always registered, 503 on an incomplete configuration), D-04 (the shared one-field body), D-06 (no gateway limits). Each names the brief's line numbers, what shipped, the ground, and what is given up. D-06 is recorded as a **flagged deferral** on the Phase 35 D-05/D-08 precedent — and, following 43-02's request, it is written as **the same item** as the unbounded-request residual seen from the other end, because one v2.1 limit closes both.
- **D-09 is recorded in full and placed in neither count, with the reason stated.** The measured cost is written as measured: with online checks off, the library sets the certificate store's clock to the payload's claimed `signedDate`, so **leaf expiry is not enforced against wall-clock time** and a holder of an Apple-issued leaf key could keep using it by backdating that date. The decision stands on the size of the prerequisite, not on the rarity of a revoked intermediate.
- **The obligations that were already dead are named as dead.** The gateway limits and vendor budgets (Phase 35 D-05/D-08), the `audit.auth_events` row and the operation metadata (Phase 37.1 D-01, Phase 38 D-03, Phase 40 D-11), the route registry with its `Category`, `RouteMetadata`, `VERIFIERS` and `NamedVerifier` (Phase 37.1 D-06/D-10), and the foundation store-verification interface (Phase 37.2 D-09) — which this phase replaced by declaring its Protocol beside its first implementation, exactly as FOUND-08's forward flag directs.
- **The counts were re-derived, and the derivation is checkable.** Four `SHARED-INVARIANTS.md` sections were re-read and each null result says what it examined. Sixteen → **nineteen** flagged conflicts; twenty-three → **twenty-seven** known divergences; the gap is **eight** and every item is enumerated in the header. The Standing table cell and the traceability row were corrected in the same stroke, so no count disagrees with its own header.
- **A wrong fact was caught before it was repeated forward.** STATE.md's 42-07 entry and `43-CONTEXT.md` § "Carried forward" both say the SQLSTATE is read off `violation.orig.__cause__.sqlstate`. The shipped code reads `violation.orig.sqlstate`, with no `__cause__` step, in **both** `crud/grants.py` and `crud/subscriptions.py`. Verified before writing, and corrected in place with a dated note.

## Task Commits

1. **Task 1: The requirement amendments** — `1f3f197` (docs)
2. **Task 2: The roadmap criteria and the project state** — `126e3f8` (docs)

## Files Created/Modified

**Modified**

- `.planning/REQUIREMENTS.md` — the Phase 43 header paragraph; APPLEHOOK-01 ticked with nine dated blocks (met-as-written, three flagged conflicts, the D-09 divergence, the verification-skipping environments, the dead-obligation inventory, the operational facts, the accepted residual, and the count re-derivation); APPLEHOOK-02 ticked with the answered mechanism; the "Nineteen conflicts" paragraph with the eight-item gap; the traceability row; two cells of the Standing table; and the footer.
- `.planning/ROADMAP.md` — all four Phase 43 criteria marked, criterion 3 answered; Phase 44's criterion 3 left pointing at that answer without restating it; `43-06-PLAN.md` ticked; the plan count and the progress row.
- `.planning/STATE.md` — the frontmatter position and counters; the Phase 43 outcome paragraph with the counter comment and the baseline note; thirteen Phase 43 decisions; the dated correction to the 42-07 SQLSTATE entry; three entries in § Blockers/Concerns; session continuity; and the metrics row.

## Decisions Made

1. **D-09 joins neither count.** The two numbers in the header are defined as divergences from the binding specification. `08-webhook-app-store.md:48` mandates only that the chain be walked with Apple's official library, which it is, and `SHARED-INVARIANTS.md` says nothing about revocation checks. Counting it would make the numbers mean two different things at once. Leaving it silent would hide the phase's largest security-relevant departure. It is therefore recorded in full under APPLEHOOK-01 and **named in the header as a ninth divergence that is deliberately in neither number**, so a reader does not read its absence as its non-existence.

2. **D-06 is counted, even though it is a deferral.** A deferral explains *why* a divergence exists; it does not stop the text from being unamended and the divergence from being knowing. The brief requires the limits at `:24`, `:50` and `:51`, and none was added. The Phase 35 precedent supplies the ground and the closing condition, not an exemption from the count.

3. **The residual and the deferral are one item, written from two ends.** 43-02 asked for exactly this and gave the reason: the limit that closes the deferral is the limit that closes the residual. Writing them as two notes would let a reader close one and think the other was still open.

4. **The mid-term tier change is recorded as two facts about two rows.** 43-01 updates `core.subscriptions.tier_id` in place, because the unique index allows one subscription row per lifecycle key; 43-04 flips-and-inserts the **grant**, so the superseded term stays readable. Both are true; the STATE entry says so in one line rather than picking one and being half wrong.

5. **The suite counts were re-measured in this plan, not copied.** All four commands were run here: 1089 / 272 / 182 / ruff clean. The plan touches no source file, so the numbers were expected to match wave 4 and did — which is the point of running them rather than assuming.

## Deviations from Plan

### Auto-fixed Issues

None. Neither task required a fix.

### Departures from the plan's letter, taken deliberately

**1. Task 2's summary-count check cannot pass at the time the task runs, and was run after the summary landed.** The `<verify>` block requires `ls .planning/phases/43-post-webhooks-app-store/43-0*-SUMMARY.md | wc -l` to read `6` "at the time this task runs". It read **5**, and could not read anything else: this plan's own summary is written after its last task, by construction. That is not an accident of this run — it is the established convention in this very file, which both 41-05 and 42-06 recorded in their STATE.md counter comments ("this plan's own summary is the Nth and lands after Task 3"). The check was re-run after this summary was written and reads **6**. Recorded in `.planning/WINDOWS.md` as entry 18.

**2. STATE.md's `completed_plans` is written as 103 while 102 summaries were on disk.** Same cause, same convention, and the counter comment says so explicitly rather than leaving the one-off difference to be discovered. 103 PLAN files and 102 SUMMARY files were counted at 23:26Z; the frontmatter already carried 103 and 102, so nothing needed correcting, and this plan's own summary is the hundred-and-third.

**3. The Phase 43 plan list in ROADMAP.md was ticked, not rewritten.** The plan asks to "update the Phase 43 plan list to the six plans and their objectives". The list already carried all six with a one-line objective each; only `43-06-PLAN.md`'s checkbox was unticked. Rewriting lines that were already correct would have been a diff with no content, against the plan's own instruction to use scoped edits.

**4. `requirements.mark-complete` applied nothing, exactly as the plan predicted it would.** It returned `table_unmatched` for both `APPLEHOOK-01` and `APPLEHOOK-02`, with all four write-set surfaces `applied: false`, because the traceability row is the range `APPLEHOOK-01 … APPLEHOOK-02` which the tool does not expand. Both surfaces were finished by hand. The plan asked for this to be recorded as measured rather than predicted, and it is: the command was run, and its output is quoted above.

---

**Total deviations:** 0 auto-fixed, 4 recorded departures.
**Impact on plan:** None on substance. Three of the four are the same structural fact — a plan cannot observe its own summary — and the fourth is a tool result the plan told me to expect and measure.

## Verification

**Task 1:**

| Check | Expected | Actual |
|---|---|---|
| `grep -c "Phase 43" .planning/REQUIREMENTS.md` | non-zero | **27** |
| `grep -c '^- \[x\] \*\*APPLEHOOK-0' .planning/REQUIREMENTS.md` | `2` | **2** |
| `git status --porcelain -- src tests config k8s migrations` | empty | **empty** |
| `git status --porcelain -- .planning/ \| grep -c REQUIREMENTS.md` | `1` | **1** |

**Task 2:**

| Check | Expected | Actual |
|---|---|---|
| `grep -c "PROVIDER_CALLBACK_PATHS" .planning/ROADMAP.md` | non-zero | **1** |
| `grep -c "Phase 43 outcome" .planning/STATE.md` | non-zero | **1** |
| `ls …/43-0*-SUMMARY.md \| wc -l` | `6` | **5** at Task 2 time, **6** after this summary — see Deviation 1 |
| `git status --porcelain -- src tests config k8s migrations` | empty | **empty** |
| `"Phase 43 must answer it"` in the ROADMAP Phase 43 block | `0` | **0** |

**Neither specification file was written.** SHA-256 taken before Task 1 and again after Task 2:

- `08-webhook-app-store.md` — `a0f5c3bdd1276c5b6d38bf9e18d99d7a85c68551e52038c896e573dad34ee14d`, identical both times.
- `SHARED-INVARIANTS.md` — `c04c58c2305a828dc1fceeae0e9aef03485d7efa49c72a76a10acd90482a919b`, identical both times.

**The phase closes on a measured green**, all four commands run in this plan:

| Command | Result | Baseline (after wave 4) |
|---|---|---|
| `uv run pytest -q` | **1089 passed**, 454 deselected | 1089 |
| `uv run pytest -m e2e -q` | **272 passed**, 1271 deselected | 272 |
| `uv run pytest -m schema -q` | **182 passed**, 1361 deselected | 182 |
| `uv run ruff check src tests` | **All checks passed!** | clean |

**Two claims were verified against the source before being written**, rather than copied from a prior artifact:

1. **The SQLSTATE spelling.** `grep -n "sqlstate\|__cause__"` over `crud/subscriptions.py` and `crud/grants.py`: five and three hits respectively, every one of them `violation.orig.sqlstate`, and **zero** `__cause__` in either file. The prose in 43-CONTEXT.md and STATE.md was wrong about working code. Corrected in place.
2. **`rawNotificationType`.** `auth/app_store.py:52-53` reads `payload.rawNotificationType` with the ground in an inline comment, and 43-RESEARCH P-03's measurement of the library's `create_raw_attr` mechanism confirms the typed attribute is `None` for any type outside the installed twenty-member enum.

## Known Stubs

None introduced. **43-01's one recorded stub is untouched and still open** — the placeholder App Store product id `com.nativespeaker.subscription.monthly` in `config/config.yaml`. It is `.planning/WINDOWS.md` entry 16 and stays open deliberately: it is resolved by an operator edit once a real iOS product exists, not by any later plan. An unmapped product id is a logged 500 with nothing written, so a wrong entry fails loudly rather than silently granting a tier.

## Threat Flags

None. This plan added no code symbol, no file under `src/`, `tests/`, `config/`, `k8s/` or `migrations/`, no network endpoint, no auth path and no schema change. The two `mitigate` dispositions in the plan's own register are discharged in text: T-43-20 by recording every divergence under its requirement with both specification hashes unchanged, and T-43-21 by re-deriving the counts against the four named sections and correcting the Standing table cell that would otherwise have disagreed with the header. T-43-19 is discharged by writing Apple's 4xx retry schedule and the `stage` field that distinguishes a misconfiguration from a probe into the amendment. T-43-08 is `accept` and is recorded as accepted, in two places. T-43-SC is `accept` and holds: no package was installed and no dependency file was edited.

## Issues Encountered

**The plan's own count arithmetic had to be decided, not read.** The plan says to record D-09 as "a divergence from Apple's production guidance" and separately to re-derive "the set of known divergences". Those two instructions pull against each other: the set is defined in the file's header as divergences *from the binding specification*, and D-09 diverges from no text in it. Adding D-09 would silently redefine the set; omitting it without comment would look like an oversight. Resolved by keeping the set's definition intact and naming D-09 in the header as a ninth item deliberately in neither number, with the reason. Recorded here because a later phase facing a vendor-guidance divergence will meet the same fork.

**Nothing else.** No package was installed, no migration was touched, no dependency file was edited, no source file was read for modification, and no authentication gate was reached.

## User Setup Required

**Unchanged from 43-02, and it is the phase's one open human deliverable.** Three values in the deployment's gitignored `.env` — `APP_STORE_BUNDLE_ID`, `APP_STORE_APP_APPLE_ID`, `APP_STORE_ENVIRONMENT` — and then both the Production and Sandbox Server URLs set to `https://<gateway host>/webhooks/app-store` in App Store Connect, followed by a Test Notification returning 200. Until the three values are set the service boots, logs one `app_store_configuration_absent` warning and answers 503, which is the designed and tested behaviour. **The App Store Connect half cannot be done yet:** there is no iOS app and no App Store Connect record for one.

A fourth operator action is owed once a real product exists: replacing the placeholder id in `config/config.yaml`'s `app_store.products` map with the real App Store product id.

## Next Phase Readiness

**Phase 43 is executed and closed. Six of six plans, and the requirement that was flagged forward two phases ago is answered.**

**For Phase 44 (Google Play RTDN)** — three things are now inherited rather than owed:

- **The partition mechanism.** APPLEHOOK-02's amendment is the text to read. Phase 44 adds one route to `routers/webhooks.py` and one member to `PROVIDER_CALLBACK_PATHS`, and defines no second partition. PLAYHOOK-03's "second and last member" clause is satisfiable because the partition is countable in one place.
- **The service and the value type.** `services/subscriptions.py` is proved by an AST walk to name nothing from the Apple library, and `tests/schema/test_subscription_race.py` races the service rather than the seam, so a Google class producing the same `VerifiedNotification` inherits the whole race proof unchanged.
- **The gateway shape.** The RTDN route is a second `Exact` match in `k8s/templates/httproute-webhooks.yaml`, not a second template — and it will inherit D-06's deferral, which should be recorded under PLAYHOOK-01 rather than re-argued.

**For Phase 45 (restore)** — restore is the only path back to a grant for a lapsed buyer, because ingestion never reactivates one. `AccessGrantSource.subscription` has a single-writer walk that will fail the moment restore constructs a second grant of that source, which is the intended forcing function. An unclaimed subscription is findable two ways, and the second exists only because 43-03 records the real attribution token rather than a generated UUID.

**What the next phase must NOT read as unmet work.** `08-webhook-app-store.md` still states, verbatim and unamended, its route registry, its foundation store-verification interface, its "not registered while unconfigured", its "never the shared error classes" and its gateway rate limits. All five are dead or diverged from, and the inventory naming each by line is under APPLEHOOK-01. A planner reading the brief alone will try to build them.

## Self-Check: PASSED

- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` and `.planning/STATE.md` all exist on disk carrying the asserted content.
- `.planning/phases/43-post-webhooks-app-store/43-06-SUMMARY.md` exists.
- Both task commits are present in `git log`: `1f3f197` and `126e3f8`.
- Both specification files are byte-identical to their pre-task hashes.

---
*Phase: 43-post-webhooks-app-store*
*Completed: 2026-09-04*
