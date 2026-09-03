---
phase: 41-post-auth-claim-anonymous-grant
plan: 03
subsystem: auth
tags: [devicecheck, grants, entitlements, fastapi, sqlmodel, ast, structural-tests]

requires:
  - phase: 41-post-auth-claim-anonymous-grant
    provides: "41-01's DeviceCheck seam, the generalised _complete sequence, the ClaimRefused family and the crud activation writer"
  - phase: 40-post-auth-upgrade-anonymous
    provides: "test_upgrade_precedence.py's in-memory challenge store, boundary-recording stub session and shared-refusal-body-by-equality idiom"
provides:
  - "FreeGrantAlreadyConsumed and OtherActiveGrantHeld — the two remaining ClaimRefused leaves, replacing the tracer's placeholder base raise"
  - "seed_grant(with_anti_abuse=True) — the e2e helper that makes a free-source grant seedable at all"
  - "The endpoint's full case matrix: the repeat, four refusals, three Apple arms, each with body, vendor call count and challenge consumption asserted"
  - "tests/unit/test_claim_precedence.py — the rejection order and the consumption disposition of every branch"
  - "tests/unit/test_grant_sources.py — ANONGRANT-01's single-writer assertion, with controls"
  - "tests/unit/test_claim_ordering.py — ANONGRANT-02's no-network-under-a-lock assertion, with controls"
affects: [41-04, 41-05, "phase 42 registered account grant"]

actuals:
  tokens: 30428
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A refusal family declares status and code once on its base and its leaves add only a name; asserted structurally per family in test_rejection_vocabulary.py"
    - "A structural ast test ships with a control whose synthetic input makes the measurement produce a different, asserted number"
    - "A precedence unit test records one ordered timeline of boundaries, crud calls and seam calls, so ordering is asserted rather than inferred"

key-files:
  created:
    - tests/unit/test_claim_precedence.py
    - tests/unit/test_grant_sources.py
    - tests/unit/test_claim_ordering.py
  modified:
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/services/auth.py
    - tests/e2e/conftest.py
    - tests/e2e/test_claim_anonymous_grant.py
    - tests/unit/test_rejection_vocabulary.py

key-decisions:
  - "The free-grant lifetime arms are evaluated before the other-source arm, so an account that is both ineligible and holding another grant logs free_grant_already_consumed"
  - "A fourth refusal case was added — a revoked free grant with the marker unset — because it is the only one that exercises has_prior_free_grant alone"
  - "The unavailable arm scripts the retryable marker rather than the converted rejection, so the three-attempt budget and its conversion to 503 are both asserted"
  - "ClaimRefused is now a pure group base, raised nowhere, exactly as ChallengeRejected and UpgradeRefused are"

patterns-established:
  - "Per-family anti-oracle assertion: the leaves of a shared-status base declare neither status nor code, and the set of leaves is written down rather than derived"
  - "Transaction-state recording in a stub session: the writer recorder opens it, the seam records it at call time, so 'no network under a lock' is a boolean the test reads"

requirements-completed: [ANONGRANT-01, ANONGRANT-03]

coverage:
  - id: D1
    description: "A repeat claim by an account already holding an active anonymous_device_grant answers 200 with the same body a fresh claim returns, writes nothing, and reaches Apple not at all"
    requirement: "ANONGRANT-03"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#TestTheRepeatIsIdempotent::test_a_repeat_answers_the_fresh_claim_body_writes_nothing_and_never_reaches_apple"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py#TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_the_repeat_answers_two_hundred_and_still_consumes"
        status: pass
    human_judgment: false
  - id: D2
    description: "An account whose free grant was consumed but is no longer active is refused 403 operation_not_allowed and never reaches Apple; the preflight carries no status predicate, matching the lifetime index"
    requirement: "ANONGRANT-03"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#TestTheFourRefusals::test_a_revoked_free_grant_is_refused_because_the_read_carries_no_status_predicate"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#TestTheFourRefusals::test_a_consumed_marker_with_no_active_grant_is_refused"
        status: pass
      - kind: other
        ref: "crud/grants.py::_prior_free_grant_statement carries no status predicate; tests/unit/test_grant_sources.py asserts it filters on FREE_GRANT_SOURCES rather than a literal pair"
        status: pass
    human_judgment: false
  - id: D3
    description: "An account holding an active grant of another source is refused 403 operation_not_allowed, because one user holds at most one active grant"
    requirement: "ANONGRANT-03"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#TestTheFourRefusals::test_an_active_grant_of_another_source_is_refused"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py#TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_an_active_grant_of_another_source_is_refused_and_still_consumes"
        status: pass
    human_judgment: false
  - id: D4
    description: "A registered caller is refused 403 operation_not_allowed and waits for Phase 42 (D-08)"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#TestTheFourRefusals::test_a_registered_caller_is_refused_and_waits_for_phase_42"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py#TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_a_registered_claimant_is_refused_and_still_consumes"
        status: pass
    human_judgment: false
  - id: D5
    description: "All four refusals answer a byte-identical one-field body and are distinguished only by the structured-log event name their class produces"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#TestTheFourRefusals — four cases assert response.json() == REFUSED by equality"
        status: pass
      - kind: unit
        ref: "tests/unit/test_rejection_vocabulary.py#TestTheThreeClaimArmsAnswerOneThingAndLogThree"
        status: pass
    human_judgment: false
  - id: D6
    description: "A device whose bit0 Apple reports set answers 403 device_grant_exhausted with no device state; a refused token answers 403 proof_rejected; an exhausted or ambiguous Apple answer answers 503; none of the three writes anything"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#TestTheThreeAppleFailureArms"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py#TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce — the three Apple arms, each asserting activates == 0"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every outcome from the claim onward consumes the challenge exactly once, and no rejection before the claim claims or consumes anything"
    verification:
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py#TestTheConsumptionCounterIsOneForEveryPostClaimOutcome — ten parametrized outcomes"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py#TestTheRejectionsBeforeTheClaimSpendNothing — three cases at counter 0"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py — all seven cases read the challenge row back and assert consumed_at is not None"
        status: pass
    human_judgment: false
  - id: D8
    description: "The literal anonymous_device_grant is written from exactly one site in src/, which is the crud activation writer"
    requirement: "ANONGRANT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_grant_sources.py#TestTheAnonymousDeviceGrantHasExactlyOneWriter"
        status: pass
      - kind: other
        ref: "Mutation check: a second construction site added to the crud writer failed two cases; reverted, file byte-identical to HEAD"
        status: pass
    human_judgment: false
  - id: D9
    description: "No network call is issued from inside the activation transaction or from any code reachable while a lock is held"
    requirement: "ANONGRANT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_claim_ordering.py#TestTheCrudWriterCannotReachTheVendor"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_ordering.py#TestBothVendorCallsPrecedeTheActivation"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py#TestNoVendorCallHappensUnderALockOrInsideTheTransaction"
        status: pass
    human_judgment: false
  - id: D10
    description: "The negative half of ANONGRANT-03 — that no other path in the application creates a grant, free credit or usage row as a side effect"
    requirement: "ANONGRANT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_grant_sources.py — the single-writer walk and the recorded set of modules naming the member"
        status: pass
    human_judgment: true
    rationale: "The walk bounds today's source tree, not a path a future phase adds. The planner recorded this as flagged assumption EDGE-ANONGRANT-03-unclassified and it remains unresolved: the negative half is enforced by a grep-shaped test and a reviewer, not by the database."

duration: 20min
completed: 2026-09-03
status: complete
---

# Phase 41 Plan 03: The claim's full case matrix and its two structural claims Summary

**Every non-happy outcome of `POST /auth/claim-anonymous-grant` is now an executed case — the idempotent repeat, four refusals sharing one byte-identical body across three log events, and the three Apple failure arms — plus two `ast` walks that hold ANONGRANT-01's single-writer and ANONGRANT-02's no-network-under-a-lock claims as checks that are proven to fire.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-09-03T05:36:42Z
- **Completed:** 2026-09-03T05:56:30Z
- **Tasks:** 3
- **Files modified:** 8 (3 created, 5 modified)

## Accomplishments

- The tracer's placeholder `raise ClaimRefused` is gone: `FreeGrantAlreadyConsumed` and `OtherActiveGrantHeld` join `ClaimantNotAnonymous` as leaves declaring neither status nor code, so one client answer and three log events is structural rather than asserted three times.
- `seed_grant` can seed a free-source grant for the first time. Until `AccessGrantAntiAbuse` existed the deferred FK refused one at commit, which is exactly why the helper's `source` defaulted to `manual`; the two prior-free-grant refusals were unseedable before this.
- Nine e2e cases through the real router against a live PostgreSQL: the repeat, four refusals, the three Apple arms and the pre-existing happy path. Every one reads the challenge row back; every refusal asserts the DeviceCheck fake's call lists.
- 27 unit cases in `test_claim_precedence.py` pin the rejection precedence and the consumption disposition of every branch — three at counter zero before the claim, ten at exactly one after it, and two ordering cases proving the claim's commit precedes the seam and the activation opens its transaction only after both vendor calls.
- Two structural modules, each with a control, and the single-writer walk additionally proven against the *real* tree by a mutation that was applied, observed to fail, and reverted.

## Task Commits

1. **Task 1: The repeat, the four refusals, and the three Apple arms** — `ce0f449` (feat)
2. **Task 2: The rejection precedence and the consumption accounting** — `d2d8d91` (test)
3. **Task 3: The two structural claims the requirements make about the whole tree** — `cea60c0` (test)

## Files Created/Modified

- `src/nativespeaker/api/errors.py` — `FreeGrantAlreadyConsumed`, `OtherActiveGrantHeld`
- `src/nativespeaker/api/services/auth.py` — the one combined placeholder raise split into two named branches, free-grant lifetime before other-source, both still before Apple
- `tests/e2e/conftest.py` — `seed_grant(with_anti_abuse=...)`, and the comment it obsoletes rewritten
- `tests/e2e/test_claim_anonymous_grant.py` — `REFUSED`, four per-case helpers, and the eight new cases
- `tests/unit/test_rejection_vocabulary.py` — two new event names, `CLAIM_ARMS`, and the claim family asserted as the challenge and upgrade families already are
- `tests/unit/test_claim_precedence.py` — the precedence, the consumption counter and the ordering timeline
- `tests/unit/test_grant_sources.py` — the single-writer walk, the recorded naming set, the `FREE_GRANT_SOURCES` arity, and four control cases
- `tests/unit/test_claim_ordering.py` — the seam-name check, the import-root allowlist, the clean-subprocess import check, the source-order assertion, and four control cases

## Decisions Made

- **The free-grant arms are evaluated before the other-source arm.** The plan set that order. It changes two things worth naming: `has_prior_free_grant` now issues its query even when a grant is held (it no longer short-circuits behind `held`), and an account that is *both* ineligible and holding a manual grant now logs `free_grant_already_consumed` rather than `other_active_grant_held`. The client answer is identical either way, which is the point of the shared base.
- **`ClaimRefused` is now a pure group base**, raised from nowhere, exactly as `ChallengeRejected` and `UpgradeRefused` are. The comment in `test_rejection_vocabulary.py` that said the preflight still raises it was updated rather than left to mislead.
- **The unavailable arm scripts the retryable marker, not the converted rejection.** Handing the fake an already-built `Unavailable` would assert only that a 503 propagates. Scripting `RetryableDeviceCheckError` makes the real three-attempt budget run and exhaust, so the case asserts `read_calls == [QUERY_TOKEN] * DEVICECHECK_ATTEMPTS` as well as the 503.
- **Transaction state is a boolean the seam records.** The `_RecordingGrants` activation recorder opens the stub session's transaction; the scripted seam records `session.in_transaction` at each call. "No network under a lock" is then read directly rather than inferred from call ordering alone.

## The consumption disposition, as the code actually behaves

The plan asked for this to be reported rather than adjusted to. **All seven outcomes are decided after the claim, and all seven consume exactly once** — including case 4, the registered caller, whose check is the first thing the post-claim work does. Nothing among the seven rejects before the claim. The only pre-claim rejections are the three handle-level ones (unknown handle, identity mismatch, operation mismatch), plus the two losses of the claim's own conditional update (expired, already consumed); all five spend nothing, asserted in Task 2.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The `EVENT_NAMES` literal ratchet went red on the two new classes**

- **Found during:** Task 1
- **Issue:** `test_rejection_vocabulary.py::test_the_tree_spells_exactly_the_recorded_event_names` derives the vocabulary from the tree and compares it against a written-down set. Two new classes is exactly the visible edit that ratchet exists to demand.
- **Fix:** Added `free_grant_already_consumed` and `other_active_grant_held`, and corrected the neighbouring comment, which claimed the preflight still raises the base.
- **Files modified:** `tests/unit/test_rejection_vocabulary.py`
- **Verification:** `uv run pytest tests/unit/test_rejection_vocabulary.py tests/unit/test_error_registry.py -q` — 148 passed
- **Committed in:** `ce0f449`

**2. [Rule 2 - Missing Critical] The claim family had no anti-oracle structural assertion**

- **Found during:** Task 1
- **Issue:** T-41-16 is mitigated by "the base declares status and code once, and the leaves add only a name". `test_rejection_vocabulary.py` asserts precisely that for the challenge family, the account family and the upgrade family — and had nothing for the claim family, whose leaves this plan doubled. Four e2e body comparisons prove today's behaviour; they do not prevent a leaf being given its own `code` tomorrow.
- **Fix:** Added `TestTheThreeClaimArmsAnswerOneThingAndLogThree`, mirroring the upgrade family's class: the three are exactly the leaves under the base, none declares status or code, none has an `__init__` or log fields, and the three snake-cased names are three distinct events.
- **Files modified:** `tests/unit/test_rejection_vocabulary.py`
- **Verification:** 8 new cases pass; a leaf given its own `code` now fails a named case
- **Committed in:** `ce0f449`

**3. [Plan-literal deviation] Case 1 cannot compare against the refusal constant, so a fourth refusal case was written instead**

- **Found during:** Task 1
- **Issue:** Task 1's acceptance criterion says "Cases 1 through 4 each assert the response body equals one shared module-level refusal constant". Case 1 is the D-09 repeat, which answers **200**. Its body cannot equal a 403 refusal body; the criterion and the plan's own action text ("a body equal to the fresh claim's body") disagree.
- **Fix:** Case 1 asserts `repeat.json() == first.json()` — the fresh claim's body, by equality, which is the D-09 property. To keep four bodies compared against the one constant, the free-grant refusal was split into the two arms that reach it: the marker set with no grant row, and a **revoked** free grant with the marker unset. The second is the only case in the suite that exercises `has_prior_free_grant` alone, so it is the one that actually proves the read carries no status predicate.
- **Files modified:** `tests/e2e/test_claim_anonymous_grant.py`
- **Verification:** 9 collected, 0 skipped; four cases assert `== REFUSED`
- **Committed in:** `ce0f449`

**4. [Plan-literal deviation] The unavailable arm scripts the retryable marker rather than the exhausted-budget rejection**

- **Found during:** Task 1
- **Issue:** "Script the fake to raise the exhausted-budget rejection" read literally means handing the fake a pre-built `Unavailable`, which skips the budget the arm exists to describe.
- **Fix:** Scripted `RetryableDeviceCheckError`, so `tenacity` spends the real three attempts and `_read_exhausted` performs the conversion. The case asserts the 503, the code, three read attempts and zero writes.
- **Files modified:** `tests/e2e/test_claim_anonymous_grant.py`, `tests/unit/test_claim_precedence.py`
- **Committed in:** `ce0f449`, `d2d8d91`

**5. [Rule 3 - Blocking] The new precedence module's docstring exceeded the three-line bar**

- **Found during:** Task 2
- **Issue:** `test_docstring_bar.py` holds every root at a baseline of zero over-long docstrings; the four-line module docstring broke `tests/unit`.
- **Fix:** Compressed to three lines with no content dropped.
- **Files modified:** `tests/unit/test_claim_precedence.py`
- **Committed in:** `d2d8d91`

---

**Total deviations:** 5 (2 auto-fixed blocking, 1 missing critical, 2 plan-literal readings resolved in favour of the plan's stated intent)
**Impact on plan:** No scope was added and no decision was reinterpreted. Deviations 3 and 4 both strengthen what the criterion asked for; deviation 2 is the structural half of a threat the plan mitigates only behaviourally.

## Verification

Re-run whole after the final task commit:

| Check | Result |
|---|---|
| `uv run pytest -m e2e tests/e2e/test_claim_anonymous_grant.py -q` | 9 passed, 0 skipped |
| `uv run pytest -q` | 950 passed (baseline after 41-02: 893) |
| `uv run pytest -m e2e -q` | 226 passed (baseline 218) |
| `uv run pytest -m schema -q` | 121 passed |
| `uv run ruff check src tests` | exit 0 |
| `ErrorCode` member count | 18 — the refusals added classes, not codes |
| `grep -c caplog` in `test_claim_precedence.py` | 0 — the vocabulary is asserted through classes |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed |

**Mutation check (Task 3 acceptance criterion).** A second `AccessGrant(source=AccessGrantSource.anonymous_device_grant)` construction was added to `crud/grants.py::activate_anonymous_device_grant`. `test_grant_sources.py` failed two cases — `test_the_whole_tree_holds_exactly_one_construction_site` and `test_the_one_site_is_inside_the_crud_activation_writer`. The edit was reverted and `git diff` reports the file byte-identical to HEAD. The assertion is therefore known to fire against the real tree, not only against its synthetic control.

## Issues Encountered

None. The precondition — a live PostgreSQL 17 carrying the applied v2.0 schema — was verified reachable by running the existing tracer case before Task 1 began.

## Carried-forward caveat, preserved

41-01 recorded that the Apple DeviceCheck wire shapes are `[ASSUMED]`: no official Apple page was fetchable during research and no iOS app exists to produce a real device token (D-04). **Nothing in this plan promotes an assumed literal to a verified one.** The three Apple failure arms here drive the *seam*, not the wire — a scripted `BitState`, a `ProofRejected` instance and the internal retryable marker — so no request body, response body or status literal is asserted anywhere in this plan's cases. The caveat in `tests/unit/test_devicecheck_adapter.py`'s module docstring remains the sole record of the wire contract's provenance and was not touched.

## Known Stubs

None. No hardcoded empty value, placeholder string, skipped test or `xfail` was introduced; nothing was added to `.planning/WINDOWS.md` because this plan left no defect to record.

## Flagged assumption still unresolved

`EDGE-ANONGRANT-03-unclassified` remains as the planner recorded it. The negative half of ANONGRANT-03 — that no other path creates a grant, free credit or usage row as a side effect — is now bounded by `test_grant_sources.py`'s walk over today's `src/` and by the recorded set of modules naming the member. That is a grep-shaped guarantee, not a database one: it does not bound a path a future phase adds. It is stated here as it is rather than resolved with a criterion that would read stronger than the check.

## User Setup Required

None beyond what 41-01 already recorded (the three `DEVICECHECK_*` variables). This plan declares no `user_setup` frontmatter and adds no external dependency.

## Next Phase Readiness

- **41-04** inherits the two new leaves, the seedable free-source grant helper and the ordering assertions, and owns the live two-connection race that proves D3 and the loser's 200. `test_claim_precedence.py::test_the_race_loser_answers_two_hundred_and_still_consumes` pins the loser's behaviour at the service level; 41-04 pins it at the database.
- **41-05** inherits a complete refusal vocabulary to document: four classes, one body, three log events.
- **Phase 42** inherits `test_grant_sources.py`, which is the check a registered-account-grant writer will trip. That is deliberate: the number it changes is the one a reviewer reads.

**Concerns:** none new. D3 from 41-01's coverage (the lock order itself) is still asserted only by reading the writer; 41-04's race is the standing proof and it has not landed yet.

---
*Phase: 41-post-auth-claim-anonymous-grant*
*Completed: 2026-09-03*

## Self-Check: PASSED

All three created files exist on disk (`tests/unit/test_claim_precedence.py`, `tests/unit/test_grant_sources.py`, `tests/unit/test_claim_ordering.py`); all three task commits resolve in `git log` (`ce0f449`, `d2d8d91`, `cea60c0`). Every task's acceptance criteria were executed and pass, and the plan-level verification block above was re-run whole after the final commit.
