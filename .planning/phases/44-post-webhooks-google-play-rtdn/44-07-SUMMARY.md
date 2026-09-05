---
phase: 44-post-webhooks-google-play-rtdn
plan: 07
subsystem: infra
tags: [requirements, roadmap, traceability, divergence-record, google-play, rtdn, playhook]

requires:
  - phase: 44-post-webhooks-google-play-rtdn
    provides: "plans 44-01 … 44-06 — the route, the gateway match, the nine-state map, the catalogue, the PostgreSQL guarantees and the answer surface, each with its own summary this plan reads rather than restates"
  - phase: 43-post-webhooks-app-store
    provides: "the APPLEHOOK amendment whose voice and structure this amendment follows, and D-01's partition that PLAYHOOK-03 closes on"
provides:
  - "The dated Phase 44 amendment under PLAYHOOK-01 … PLAYHOOK-03, on a basis measured in this plan"
  - "PLAYHOOK-03 answered and closed — the last of the four flags Phase 37.1 raised on the deleted route registry"
  - "Five flagged conflicts against 09-webhook-google-play-rtdn.md, and the re-derived counts 24 / 33"
  - "The two research corrections in the record: the SUBSCRIPTION_STATE_ prefix, and Pub/Sub's five acknowledging statuses"
  - "Dated notes under APPLEHOOK-01 amending 43 D-13 and 43 D-14"
  - "ROADMAP criterion 3 answered; STATE.md carrying the Phase 44 outcome and seven new decision entries"
affects: [45-restore-subscription, 46-sign-out-all]

actuals:
  tokens: 21500
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A divergence is recorded under the requirement it belongs to and counted against each binding passage it diverges from, never once per idea"
    - "A verification gate that cannot pass for a reason unrelated to its subject is replaced by checks that measure the property, and the replacement is recorded"

key-files:
  created:
    - .planning/phases/44-post-webhooks-google-play-rtdn/44-07-SUMMARY.md
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "OQ-4's composite replay key is recorded as a fifth flagged conflict, not only as a decision: :24 and :41 mandate the Pub/Sub message ID and are unamended"
  - "Phase 43's three conflicts are counted a second time against the 09 brief's own lines, because a conflict is counted per binding passage, not per idea"
  - "The traceability row stays a range; requirements.mark-complete returning table_unmatched is accepted rather than fixed by reshaping a shared table"
  - "The plan's specs/ gate was replaced: specs/auth-refactor-phases/ has never been tracked, so the gate fired on untracked-ness rather than on an edit"
  - "The phase is NOT marked complete in ROADMAP.md — only plan progress; the phase checkbox is the verifier's and the orchestrator's"

patterns-established:
  - "A stale forward reference in a prior plan's summary is corrected in the requirement record, where a later reader looks, and both summaries are left as written"

requirements-completed: [PLAYHOOK-01, PLAYHOOK-02, PLAYHOOK-03]

coverage:
  - id: D1
    description: "REQUIREMENTS.md carries a dated Phase 44 amendment naming PLAYHOOK-03 as answered and closed by inheriting Phase 43's partition with one added route and one added literal member"
    requirement: "PLAYHOOK-03"
    verification:
      - kind: other
        ref: "grep -c 'ANSWERED AND CLOSED by Phase 44' .planning/REQUIREMENTS.md — 2 occurrences (the checkbox line and the dated note)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py:22 — PROVIDER_CALLBACK_PATHS = set(PROVIDER_CALLBACK_VERIFIERS), read at source: the literal the amendment claims is the key set, is"
        status: pass
    human_judgment: false
  - id: D2
    description: "The three PLAYHOOK checkboxes are marked met, citing counts produced by the four commands run in this plan rather than copied from Phase 43"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "grep -c '^- \\[x\\] \\*\\*PLAYHOOK-0' .planning/REQUIREMENTS.md = 3"
        status: pass
      - kind: unit
        ref: "uv run pytest -q — 1190 passed; uv run pytest -m e2e -q — 298 passed; uv run pytest -m schema -q — 205 passed; uv run ruff check src tests — exit 0. Run twice in this plan, once per task."
        status: pass
    human_judgment: false
  - id: D3
    description: "D-10 appears as a new flagged divergence with the 09 brief's DELETIONS line cited, and OQ-4's composite key as a fifth, against :24 and :41"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "grep -c 'DELETIONS line at `:53`' .planning/REQUIREMENTS.md — 4 occurrences across the entry, the header and the two tables"
        status: pass
      - kind: other
        ref: "The five conflicts are enumerated in the header paragraph, the FLAGGED block under PLAYHOOK-01, the traceability row and the standing table, and the four agree"
        status: pass
    human_judgment: false
  - id: D4
    description: "The SUBSCRIPTION_STATE_ prefix correction and the Pub/Sub acknowledgement correction both appear in the record"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "test \"$(grep -c 'SUBSCRIPTION_STATE_' .planning/REQUIREMENTS.md)\" -ge 1 — 5 lines"
        status: pass
      - kind: other
        ref: "grep -c '102, 200, 201, 202 and 204' .planning/REQUIREMENTS.md — 2 occurrences"
        status: pass
    human_judgment: false
  - id: D5
    description: "The notification_uuid decision is recorded with its rationale and its one-way rating"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "test \"$(grep -c 'notification_uuid' .planning/REQUIREMENTS.md)\" -ge 1 — 3 lines; 'one-way' recorded on 5 lines"
        status: pass
    human_judgment: false
  - id: D6
    description: "The Apple-only reachability of revoked and the linkedPurchaseToken stale-row consequence are both recorded"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "grep -c 'linkedPurchaseToken' .planning/REQUIREMENTS.md — 3 occurrences; the revoked asymmetry appears under PLAYHOOK-01 and in STATE.md § Decisions"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_store_notifications.py#TestRevokedIsAnAppleOnlyWord::test_no_google_state_reaches_revoked_on_either_side_of_its_expiry — the record's claim is the suite's claim"
        status: pass
    human_judgment: false
  - id: D7
    description: "Dated notes under APPLEHOOK-01 record the amendments to 43 D-13 and 43 D-14, and OQ-2's unverified outcome"
    verification:
      - kind: other
        ref: "grep -c '43 D-13 is REPLACED\\|43 D-14 is RELOCATED' .planning/REQUIREMENTS.md = 2"
        status: pass
    human_judgment: false
  - id: D8
    description: "No file under /home/init/native-speaker/specs/ is modified (D-22)"
    verification:
      - kind: other
        ref: "git status --porcelain --untracked-files=no -- specs/ — empty (0 modified tracked files)"
        status: pass
      - kind: other
        ref: "find specs/ -type f -newermt '2026-09-05 00:00' — 0 files; the two briefs' mtimes are 2026-08-18 and SHARED-INVARIANTS.md's is 2026-09-01"
        status: pass
    human_judgment: false
  - id: D9
    description: "ROADMAP.md § Phase 44 records criterion 3 as answered and lists all seven plans as complete, with every other phase section byte-identical in the diff"
    requirement: "PLAYHOOK-03"
    verification:
      - kind: other
        ref: "test \"$(git diff --unified=0 -- .planning/ROADMAP.md | grep -cE '^[-+]#### Phase (4[0-3]|3[0-9]|45|46):')\" = 0 — no phase heading but 44's body appears in the diff"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'PLAN.md' .planning/ROADMAP.md)\" -ge 7 — 110"
        status: pass
    human_judgment: false
  - id: D10
    description: "STATE.md carries a dated Phase 44 entry naming the two classes, the credential, the value-type promotion, the notification_uuid scheme and the prefix correction, and its counters match a count taken from disk"
    verification:
      - kind: other
        ref: "test \"$(ls .planning/phases/*/*-PLAN.md | wc -l)\" = \"$(grep -oP 'total_plans:\\s*\\K[0-9]+' .planning/STATE.md)\" — 110 = 110"
        status: pass
    human_judgment: false
  - id: D11
    description: "The record reads as a true account of what shipped — that the amendment's prose is accurate, proportionate and legible to the Phase 45 planner who will read it cold"
    verification: []
    human_judgment: true
    rationale: "Every mechanical property above is measured, but whether the amendment actually tells the next phase's planner what is true — and whether counting Phase 43's three conflicts a second time against a second brief is the right call rather than double-counting — is a reading judgment no command makes. This is the deliverable a human should read before the phase is verified."

duration: 22min
completed: 2026-09-05
status: complete
---

# Phase 44 Plan 07: The phase closed in the record Summary

**`PLAYHOOK-01 … PLAYHOOK-03` are met on a basis measured in this plan — 1190 unit / 298 e2e / 205 schema, ruff clean — `PLAYHOOK-03` is answered and closed by adding one route and one literal member to Phase 43's partition rather than a second mechanism, and five divergences from `09-webhook-google-play-rtdn.md` are recorded under the requirement rather than resolved by editing the brief.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-09-05T12:18:54Z
- **Completed:** 2026-09-05T12:40:00Z
- **Tasks:** 2
- **Files modified:** 3 (1 created — this summary)

## Accomplishments

- **`PLAYHOOK-03` is closed, and it is the last of the four flags Phase 37.1 raised on the deleted route registry** — open since 2026-08-24. `SYNC-03` was decided, `SIGNOUT-02`'s audit half settled, `APPLEHOOK-02` closed by Phase 43, and this one closes here. It closed the way the flag asked: by **inheriting** Phase 43 D-01 with one added route and one added literal member, never a second partition. `PROVIDER_CALLBACK_VERIFIERS` maps each exact path to its own verifier and `PROVIDER_CALLBACK_PATHS` is its **key set** — verified at source, `tests/unit/test_app_wiring.py:22` — so no second table can disagree with the first and "second and last member" is a property of a dict rather than a claim in prose.
- **The record now says the mechanism changed.** Phase 43's partition carried a **router-level** verifier, which cannot express two routes with two verifiers. `webhooks_router` declares no `dependencies=` and each route declares its own verifier as parameter 0 (D-01), with a flattened resolution walk pinning that it resolves **before `get_db`** (D-02) — an ordering Phase 43 assumed and this phase measured, for both providers.
- **Five flagged conflicts, and the reason there are five rather than two is stated rather than assumed.** Three are Phase 43's three — the always-registered router answering 503, the shared one-field body, the absent gateway limits — **counted again**, because `09-webhook-google-play-rtdn.md` states the same three rules in its own unamended text. A conflict is counted against each binding passage it diverges from, not once per idea. Two are this phase's own: **D-10**'s raw purchase token persisted as `external_id`, and **OQ-4**'s composite replay key.
- **OQ-4 is recorded as a conflict, not only as a decision.** The brief mandates the Pub/Sub **message ID** at `:24` and `:41`, both unamended. The phase shipped `google_play:{purchase_token}:{event_time_millis}:{event_type}` — chosen by the user at 44-01's blocking checkpoint, rated one-way — because it dedupes a redelivery *and* a Play republish without resting on a delivery-id stability guarantee Google's reference never states. Recording the decision without recording the divergence would have left it undiscoverable to a reader auditing the brief.
- **Both research corrections are in the record with their consequences.** `44-CONTEXT.md` D-11's table uses bare state words and counts seven; Google publishes **nine**, all prefixed — a dict keyed on the bare words would have routed **every** subscriber to `expired`. And D-04's ground is factually wrong: Pub/Sub acknowledges only 102, 200, 201, 202 and 204 and **resends on everything else**, so a 4xx redelivers exactly like a 5xx. The 200 decision is unchanged and better supported, and the operational corollary is recorded — a misconfigured `push_audience` turns every genuine RTDN into a 401 retried until retention expires, and `stage` is the only signal separating that from a forgery.
- **`43 D-13` is replaced and `43 D-14` relocated**, dated under APPLEHOOK-01, with the reason the first was **forced** rather than chosen: a date-derived status in the shared service would have silently overruled the live `subscriptionState` Play reports. OQ-2's outcome is recorded honestly — Apple's documentation page returned 404 during research, so the always-present claim is **unverified** and the 500 leaf stands with a named case behind it.

## Task Commits

1. **Task 1: the measured basis, and the dated PLAYHOOK and APPLEHOOK amendments** — `770782d` (docs)
2. **Task 2: the roadmap criterion and the project state** — `4748fed` (docs)

**Plan metadata:** the `docs(44-07)` commit that carries this file.

## Files Created/Modified

- `.planning/REQUIREMENTS.md` — the dated Phase 44 header amendment; PLAYHOOK-01's twelve-paragraph entry (met-as-written with the measured basis, five flagged conflicts, two corrections, two consequences, the dead-obligation inventory, three operational facts, the uncounted residual, the re-derived counts); PLAYHOOK-02's structural-reuse note; PLAYHOOK-03 closed; three dated notes under APPLEHOOK-01; the traceability row, the standing table's two cells and the "last updated" footer
- `.planning/ROADMAP.md` — Phase 44 only: all four criteria marked against what the phase measured, criterion 3 answered, the seventh plan ticked, 7/7 executed
- `.planning/STATE.md` — the Phase 44 outcome paragraph, the disk-count comment, seven new § Decisions entries, the session block, the metrics row and the frontmatter counters

## Decisions Made

- **OQ-4's composite key is a counted flagged conflict, not only a recorded decision.** The plan asked for the decision, its rationale and its one-way rating. It did not ask for it to be counted. But `:24` and `:41` mandate the Pub/Sub message ID in unamended text and the phase knowingly shipped something else, which is this project's own definition of a flagged conflict. Recording it only as a decision would have meant a reader auditing `09-webhook-google-play-rtdn.md` against the count would not have found it — exactly the failure T-44-29 exists to prevent.
- **Phase 43's three conflicts are counted a second time.** The alternative reading — that they are three ideas already counted — would make the count measure ideas rather than divergences-from-binding-text, and the file's own header says it measures the latter. The brief states each rule in its own lines and no passage of it is amended, so each is a live divergence from a second binding passage. Stated explicitly in the header, the traceability row and the standing table, so the arithmetic cannot be mistaken for double-counting.
- **The counts are twenty-four and thirty-three, gap nine**, re-derived against four named `SHARED-INVARIANTS.md` sections rather than inherited. Not one invariant section produced a divergence; all five conflicts are against the brief. The one new uncounted item is the unbounded unauthenticated request cost on this second callback route — recorded as the **narrowest** of the five such residuals, because one RS256 verification against an already-cached JWKS document is smaller work than Apple's certificate-path build plus three ES256 verifications.
- **The traceability row stays a range.** `requirements.mark-complete` returned `table_unmatched` for all three ids and applied nothing — measured, not predicted, and the same result 41-05, 42-06, 43-06 and 44-05 each recorded. The row has no per-id anchor because **every** row in that table is a range. Reshaping this one to satisfy a parser would make it inconsistent with the twelve others and would fix the tool for none of them. Both surfaces were finished by hand in Task 1.
- **The `44-01` stale forward reference is corrected in `REQUIREMENTS.md`, not in the summary that carries it.** 44-01 says the three `GOOGLE_PLAY_` values are documented by plan 44-04; they are documented by **44-02**. Both summaries are left as written, per the standing convention that a completed plan artifact records what it said on the day it closed, and the correction lands under PLAYHOOK-01 where a reader looking for the deployment surface will meet it.
- **The phase is not marked complete in `ROADMAP.md`.** Plan progress advanced to 7/7 executed; the phase checkbox and `completed_phases` are the verifier's and the orchestrator's, and `completed_phases` stays at 14.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's `specs/` cleanliness gate cannot pass in this repository, for a reason unrelated to what it tests**

- **Found during:** Task 1
- **Issue:** The gate is `git -C /home/init/native-speaker status --porcelain -- specs/ | tee /dev/stderr | wc -l | grep -qx 0`, and it fails — it prints `?? specs/auth-refactor-phases/`. That is a **`??`**, not an `M`: the directory has **never been tracked** in the parent repository. (`git ls-files specs/` returns `specs/auth-refactor/…` and nothing under `specs/auth-refactor-phases/`.) So the gate fires on untracked-ness rather than on an edit, and would fail identically for a plan that touched nothing at all. Written as specified it proves nothing about D-22 and would have to be either failed or waved through — and waving a gate through is how a real edit gets missed later.
- **Fix:** Replaced with two checks that measure the property the gate exists for. **(a)** `git status --porcelain --untracked-files=no -- specs/` — empty, so no *tracked* specification file is modified. **(b)** `find specs/ -type f -newermt "$(date -u +%F) 00:00"` — zero files, so nothing under `specs/` was written today at all; `08-webhook-app-store.md` and `09-webhook-google-play-rtdn.md` both carry mtime 2026-08-18 and `SHARED-INVARIANTS.md` 2026-09-01. D-22 holds, proven two independent ways.
- **Files modified:** none — this is a change to a verification command, not to a file
- **Verification:** both checks run and recorded above; the distinction is recorded in `STATE.md` § Decisions and in `.planning/WINDOWS.md` (entry 21) so the next phase inheriting this gate does not rediscover it
- **Committed in:** `770782d` (the amendment the gate guards)

### Deliberate departures from the written plan

**2. OQ-4's composite key is recorded as a fifth flagged conflict.** The plan's action text lists the OQ-4 decision under "the named decision OQ-4 asked for" and separately lists D-10 as "a new flagged divergence" — so it anticipates **four** conflicts, not five. Neither `44-CONTEXT.md` D-21 nor `44-RESEARCH.md` OQ-4 noticed that `:24` and `:41` mandate the message ID in binding text. They do, verbatim, and the phase diverged from them knowingly. Counted, with the reasoning stated in the record rather than left implicit.

**3. The `.planning/REQUIREMENTS.md` range-row question is answered by leaving it alone, and saying so.** The plan does not raise it; 44-05 met it and declined to act. This plan makes the declining explicit and gives the ground, so the next phase meeting `table_unmatched` finds a decision rather than a fourth silent recurrence.

---

**Total deviations:** 1 auto-fixed (1 bug) and 2 documented departures.
**Impact on plan:** No scope creep. The gate fix makes an unsatisfiable acceptance criterion measurable; the fifth conflict is the plan's own convention applied to a passage the planning artifacts missed.

## Issues Encountered

- `requirements.mark-complete` applied nothing for all three ids and returned `table_unmatched` for each. Expected, and handled in Task 1 before the tool was run: both the checkboxes and the traceability row were amended by hand. Recorded as a decision rather than a defect — see above.
- `requirements.ready-ids` reported **3 of 3 ready**, which is the unblocking every prior Phase 44 summary predicted: PLAYHOOK-01 and PLAYHOOK-02 were held open only because this plan declared them and had no summary yet.

## User Setup Required

None new in this plan. The deployment surface is documented by plan **44-02** in `.env.example` and `44-USER-SETUP.md` — the three `GOOGLE_PLAY_` variables, both egress hosts, the `androidpublisher` grant made in **Play Console → Users and permissions** rather than GCP IAM, the Pub/Sub topic and push subscription, and the Android client's `obfuscatedAccountId` obligation. `44-01-SUMMARY.md`'s pointer at 44-04 is stale and is corrected under PLAYHOOK-01.

## Known Stubs

None. This plan added no code path and no test. Every claim it writes into the record is either measured in this plan or cites the plan and the case that measured it.

## Threat Flags

None. Every surface this plan touches is in its own register: T-44-29 (the divergence record — every divergence recorded under its requirement with the brief's own line cited, and D-22 proved by the two checks above), T-44-30 (the ROADMAP amended with `Edit`, with a gate failing if any other phase heading appears in the diff — it does not), T-44-31 (the four commands run in this plan and their counts are what the amendment cites), and T-44-SC (no package installed).

**T-44-31 is worth restating, because it is the whole point of this plan.** The numbers in the amendment — 1190 / 298 / 205 — were produced twice in this plan, once per task, and never copied from Phase 43's paragraph or from a sibling summary. Phase 43's own record shows why the rule exists: its `1089 / 272 / 182` was measured before four critical findings were fixed, and the phase's first verification read `gaps_found`. A copied number records a moment that has already passed.

## Next Phase Readiness

- **Phase 45 (`POST /auth/restore-subscription`) is unblocked on this phase's record**, which is the thing it most needs. It inherits: `PlaySubscriptionSource` and `PlayDeveloperSubscriptions` as a **separate** class from the Pub/Sub token check, precisely so a restore route can make the Play lookup with no push token to verify; `scripted_play_subscriptions` for its own cases; the provider-aware `_buyer` harness; and the `google_play.products` catalogue rather than a second one.
- **Three facts Phase 45 must read before it plans.** (1) `PlaySubscriptionSource.read` answers `None` for a purchase token Google reports gone (404/410) — a restore route must handle that arm rather than assume a value type. (2) The Google purchase token **is** `external_id` (D-10), so it is the handle a restore route presents and a credential it must never log; the `AttributionConflict` leak 44-06 found and fixed is the shape of that mistake. (3) `audit.subscription_events.notification_uuid` is `UNIQUE NOT NULL` and Phase 45 writes through it, so the composite scheme is a one-way door already walked through.
- **One advisory residual is inherited from Phase 43 and still belongs to Phase 45:** `core.store_purchases` is never backfilled, so a purchase first recorded unattributed keeps its server-minted `identity_value` forever.
- **The phase is executed, not verified.** `completed_phases` stays at 14 and the ROADMAP phase entry reads 7/7 **executed**. `/gsd:verify-work 44` is the next step, and the one deliverable it should put in front of a human is D11 — whether the amendment reads true to someone who was not here.

---
*Phase: 44-post-webhooks-google-play-rtdn*
*Completed: 2026-09-05*

## Self-Check: PASSED

- Every modified file exists on disk with the changes described, and this summary with them.
- Both task commits exist in `git log`: `770782d`, `4748fed`.
- All of Task 1's eight acceptance criteria pass, with the `specs/` one satisfied by the replacement checks recorded under Deviations. All five of Task 2's pass, including the ROADMAP diff gate at 0 and `total_plans` matching disk at 110.
- Plan verification re-run at close, and run **twice** in this plan rather than once: `uv run pytest -q` 1190 passed, `uv run pytest -m e2e -q` 298 passed, `uv run pytest -m schema -q` 205 passed, `uv run ruff check src tests` clean.
- D-22 holds: `git status --untracked-files=no -- specs/` is empty and no file under `specs/` has an mtime inside 2026-09-05.
- The five conflicts are enumerated identically in the four places the file states them — the header amendment, the FLAGGED blocks under PLAYHOOK-01, the traceability row and the standing table's count cell — and the arithmetic 19 → 24 and 27 → 33 with a gap of nine is consistent across all four.
