---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 04
subsystem: api
tags: [fastapi, httpx, pytest, app-store, google-play, entitlements, adapters]

requires:
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-01: the tracer — one clock read per method, and the pattern for relocating a boundary onto a pure helper"
  - phase: 45-restore-a-subscription
    provides: the two store read seams and the restore service that calls them
provides:
  - AppStoreNotifications.verify_transaction takes the proof alone and reads the clock once
  - PlayDeveloperSubscriptions.read and .read_for_restore take no datetime and read the clock once each
  - The PlaySubscriptionSource Protocol declares no datetime on either method
  - verify_google_play_notification declares no datetime dependency
  - The Apple and Play term boundaries are pinned by unit cases over the helpers that still take one
affects: [47-05, 47-06, 47-07, 49, 50]

actuals:
  tokens: 10795
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "An adapter reads datetime.now(UTC) once and hands it to the pure helper that judges the status"
    - "A term boundary is pinned over the helper that takes its datetime, never over the seam that reads a clock"
    - "A test that drives a live read dates its open term from the live clock, not from a fixed constant"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/auth/app_store.py
    - src/nativespeaker/api/auth/google_play.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/services/restore.py
    - tests/unit/test_restore_proof.py
    - tests/unit/test_google_play_notifications.py
    - tests/unit/test_app_store_notifications.py
    - tests/e2e/conftest.py
    - tests/e2e/test_restore_subscription.py
    - tests/schema/test_restore_race.py

key-decisions:
  - "The two store boundaries moved onto the helpers with microsecond parametrization. Apple's is pinned by varying the instant around a fixed expiry, because Apple encodes its stamps in milliseconds and a microsecond offset on the expiry cannot survive that encoding."
  - "Three Apple status cases and two Play state-map rows had to date their term from the live clock. Their fixed term was 2026-06-01 + 10 days, which is now in the past, so a seam reading the live clock reports expired where the case asserted active."
  - "The vacuous Play state-map row `(CANCELED, EVALUATED_AT, expired)` was deleted rather than kept. Against a live clock it only repeats the LAPSED row; the equality it used to pin now lives in the `_status_for` class."
  - "`_transaction_status` is driven through a real `JWSTransactionDecodedPayload`, not a stand-in, so the boundary cases add no type-checker ignore."
  - "Each task folded in the call sites its own signature change breaks, so the unit suite is green at every commit. The e2e restore suite is the exception and is green from the third commit."

patterns-established:
  - "Pattern 1: a boundary that needed a pinned clock is parametrized over the pure helper, with the instant varied around a fixed term when the term's own encoding is too coarse"
  - "Pattern 2: a module constant derived from the live clock (OPEN_TERM) is what keeps a case about an open term true, where a fixed literal rots"

requirements-completed: []

coverage:
  - id: D1
    description: "AppStoreNotifications.verify_transaction takes the proof alone, reads the clock once, and hands it to the unchanged _transaction_status"
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestTheRealChainVerifiesTheRestoreProof, #TestTheStatusComesFromTheTransactionAlone"
        status: pass
      - kind: other
        ref: "grep -c 'datetime.now(UTC)' src/nativespeaker/api/auth/app_store.py == 1 and grep -c evaluated_at == 2"
        status: pass
    human_judgment: false
  - id: D2
    description: "The Apple term boundary is pinned over _transaction_status: an expiry equal to the instant is over"
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestTheAppleTermBoundaryIsJudgedByTheHelperAlone::test_transaction_status_reads_a_term_ending_at_the_instant_as_over (3 cases)"
        status: pass
      - kind: other
        ref: ".venv/bin/pytest -q tests/unit/test_restore_proof.py -k transaction_status (3 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "All four Play signatures lost the parameter in one commit, and both concrete methods read the clock once"
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py (the concrete class still conforms to the Protocol)"
        status: pass
      - kind: other
        ref: "grep -c 'datetime.now(UTC)' src/nativespeaker/api/auth/google_play.py == 2 and grep -c 'class PlaySubscriptionSource' == 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "The Play term boundary is pinned over _status_for, with the equality and both one-tick sides"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheCanceledTermIsJudgedByTheHelperThatTakesTheInstant (5 cases plus a control)"
        status: pass
    human_judgment: false
  - id: D5
    description: "verify_google_play_notification declares no datetime dependency and its check order is unchanged"
    verification:
      - kind: unit
        ref: "tests/unit/test_google_play_notifications.py#TestTheRefusalsDifferOnlyInStage, #TestThePushTokenIsCheckedBeforeTheBodyIsParsed"
        status: pass
      - kind: other
        ref: "grep -c 'get_evaluated_at' src/nativespeaker/api/app/dependencies.py == 5"
        status: pass
    human_judgment: false
  - id: D6
    description: "The three scripted store seams in the e2e harness match the real signatures and record no instant"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py (36 passed, 1 pre-existing failure that is not this plan's)"
        status: pass
      - kind: other
        ref: "grep -c 'evaluated_at' tests/e2e/conftest.py == 0"
        status: pass
    human_judgment: false
  - id: D7
    description: "tests/unit/test_auth_package_shape.py passes untouched, because no function was added under auth/"
    verification:
      - kind: unit
        ref: "tests/unit/test_auth_package_shape.py (CURRENT = (8, 24, 67) unchanged)"
        status: pass
      - kind: other
        ref: "git diff --stat tests/unit/test_auth_package_shape.py is empty"
        status: pass
    human_judgment: false

duration: 20 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 04: The store adapters read their own instant Summary

**`verify_transaction`, `read` and `read_for_restore` each read `datetime.now(UTC)` once and hand it to `_transaction_status` or `_status_for`; the Protocol and the Google Play webhook dependency declare no datetime, and both store term boundaries are pinned over the helpers that still take one.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-09-12T06:24:00Z
- **Completed:** 2026-09-12T06:44:35Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- `AppStoreNotifications.verify_transaction(signed_transaction)` takes one argument. It reads
  `instant` once, after the last refusal arm and before the value type is built, and hands that
  value to `_transaction_status`. `grep -c 'datetime.now(UTC)'` over the module prints `1` and
  `grep -c 'evaluated_at'` prints `2` — the helper's parameter and its use, nothing else.
- All four Play signatures changed in one commit: the `PlaySubscriptionSource` Protocol's `read`
  and `read_for_restore`, and the concrete `PlayDeveloperSubscriptions` pair. RESEARCH Pitfall 5
  never arose — `tests/unit/test_adapter_interfaces.py` is green and the Protocol is still there
  for Phase 49 to delete.
- `verify_google_play_notification` declares no `Depends` supplying a datetime. Its control flow is
  byte-identical: the push-token check, the decode, the package-name check and the Play read keep
  their order, and `signed_at=instant_from_millis(...)` and the comment above it are untouched.
- Both term boundaries were relocated, not dropped. `_transaction_status` is pinned by three cases
  around a fixed expiry — one microsecond inside is `active`, the equality is `expired`, one
  microsecond past is `expired`. `_status_for` is pinned by five, carrying the same equality plus
  a day on each side, and a control that a canceled term with no expiry is never entitled.
- The three scripted seams in `tests/e2e/conftest.py` match the real signatures. The Apple fake
  records the signed transaction alone, as its `verify` sibling four lines above already did.
  `grep -c 'evaluated_at'` over that file prints `0`.
- `tests/unit/test_auth_package_shape.py` is untouched and passes: no function was added under
  `auth/`, so RESEARCH Open Question 5's disposition held.
- Suites: **1928 unit / 361 e2e / 291 schema**, `ruff check src tests` clean, `ty check` **314**
  diagnostics against a **315** baseline.

## Task Commits

1. **Task 1 RED: drive the Apple restore seam with no datetime** - `970561c` (test)
2. **Task 1 GREEN: the Apple adapter reads its own instant** - `f29a052` (feat)
3. **Task 2 RED: drive all four Play signatures with no datetime** - `b4d3b92` (test)
4. **Task 2 GREEN: the Play seam drops the instant from all four signatures** - `c66c847` (feat)
5. **Task 3: the scripted store seams match the real signatures** - `b0241c5` (test)

## Files Created/Modified

- `src/nativespeaker/api/auth/app_store.py` - `verify_transaction` takes the proof alone and reads one instant
- `src/nativespeaker/api/auth/google_play.py` - the Protocol's two methods and the concrete two, one read each
- `src/nativespeaker/api/app/dependencies.py` - the webhook dependency declares no datetime
- `src/nativespeaker/api/services/restore.py` - both `_verify` branches dropped the argument
- `tests/unit/test_restore_proof.py` - the Apple boundary class, `_decoded` and `_live` helpers, every call site
- `tests/unit/test_google_play_notifications.py` - the `_status_for` boundary class, `OPEN_TERM`, every call site
- `tests/unit/test_app_store_notifications.py` - one call site lost its argument
- `tests/e2e/conftest.py` - the three scripted seams
- `tests/e2e/test_restore_subscription.py` - the two threading assertions rewritten
- `tests/schema/test_restore_race.py` - the scripted Apple seam mirrors the real signature

## Decisions Made

**The Apple boundary varies the instant, not the expiry.** The plan asked for an expiry one
microsecond before, at, and after the instant. Apple encodes every stamp as UNIX **milliseconds**
(`_milliseconds` is `int(moment.timestamp() * 1000)`), so a microsecond offset on the expiry is
rounded away and all three cases would have carried the same expiry. The three cases instead fix
the expiry at `EVALUATED_AT` and vary the instant by one microsecond on each side. The property is
identical — the comparison is `>` and the equality is `expired` — and it is now expressible.

**`_transaction_status` is driven through a real `JWSTransactionDecodedPayload`.** The library's
model accepts keyword construction, so `_decoded(offset)` builds a genuine payload from the same
dict `_dated` hands the chain. A `SimpleNamespace` stand-in would have needed a
`# ty: ignore[invalid-argument-type]`, and the boundary cases add none.

**Three Apple status cases and two Play state-map rows had to date from the live clock.** Both test
modules pin `EVALUATED_AT = 2026-06-01`, which is three months in the past. Once the seam reads its
own clock, a term at `EVALUATED_AT + 10 days` is over, so `_proof_through(chain, _dated(10 days))`
reported `expired` where the case asserted `active`. The three Apple cases now use `_live(offset)`,
which dates the term from the wall clock; the Play state map and the zone-less-stamp control use
`OPEN_TERM = datetime.now(UTC) + timedelta(days=10)`. The fixed constants stay everywhere they name
a value the body itself carries — `expires_at == UNEXPIRED`, `purchased_at == PURCHASED_AT` — because
those are exact and do not read a clock.

**Two test names were corrected rather than left false.**
`test_a_term_ending_after_the_captured_instant_reports_active` and its sibling became
`..._after_the_instant_the_seam_reads_...`. The name stated a fact the code no longer has.

**The vacuous Play state-map row was deleted.** `("SUBSCRIPTION_STATE_CANCELED", EVALUATED_AT,
expired)` existed to pin the equality at the state-map level. Against a live clock it is merely a
second lapsed term and proves nothing the `LAPSED` row does not. The equality it carried is now
pinned directly on `_status_for`, at microsecond resolution and on both sides.

**`TestTheEntitlementDecisionUsesTheInstantTheRequestCaptured` was renamed, not deleted.** Its class
docstring cited WR-27 and the removed threading. It is now
`TestTheCanceledTermIsJudgedByTheHelperThatTakesTheInstant`, carrying the same
`test_the_class_holds_no_clock_of_its_own_to_fall_back_to` constructor ratchet with a docstring that
states what the signature now pins: the constructor holds no date, so each read takes its own.

**The e2e restore suite is red between the first and the third commit, by the plan's design.**
Tasks 1 and 2 gate on `pytest -q`, which is the unit suite alone; the scripted e2e seams are
Task 3's. The unit, schema and e2e suites are all at baseline at the final commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 also dropped the Apple argument in `services/restore.py`**
- **Found during:** Task 1
- **Issue:** The plan gave `services/restore.py::_verify` to Task 2. Task 1's own `<verify>` is
  `pytest -q` over the whole unit suite, which cannot pass while `_verify` still hands
  `verify_transaction` a second argument the adapter no longer takes.
- **Fix:** The Apple half of `_verify` dropped its argument in Task 1's GREEN commit. The Play half
  stayed for Task 2, which is where it changed.
- **Files modified:** `src/nativespeaker/api/services/restore.py`
- **Verification:** 1926 unit passed at Task 1's GREEN; `grep -c 'evaluated_at'` over the file still
  prints `9` at the end of Task 2, exactly as the plan's own criterion requires
- **Committed in:** `f29a052`

**2. [Rule 3 - Blocking] Two test files the plan does not name carry the Apple signature**
- **Found during:** Task 1
- **Issue:** `tests/unit/test_app_store_notifications.py:587` calls
  `verify_transaction(signed, datetime.now(UTC))`, and `tests/schema/test_restore_race.py:168`
  defines a scripted Apple seam with the two-parameter signature. The plan's Task 2 describes the
  latter as "the fake store seam whose method mirrors `read_for_restore`", which is not what that
  file holds — its fake is `verify_transaction`.
- **Fix:** Both dropped the parameter in Task 1's RED commit, which is where the signature is driven.
- **Files modified:** `tests/unit/test_app_store_notifications.py`, `tests/schema/test_restore_race.py`
- **Verification:** 1928 unit passed, 291 schema passed — the measured schema baseline exactly
- **Committed in:** `970561c`

**3. [Rule 3 - Blocking] Task 2 also changed the Play call sites in `tests/unit/test_restore_proof.py`**
- **Found during:** Task 2
- **Issue:** That file makes nine `read_for_restore` calls and defines the `_ScriptedPlay` fake whose
  signature mirrors the real one. It is in Task 1's file list, not Task 2's, but every one of those
  names the Play signature Task 2 changes.
- **Fix:** All nine call sites and the fake dropped the argument in Task 2's RED commit.
- **Files modified:** `tests/unit/test_restore_proof.py`
- **Verification:** 114 failed at RED, 1928 passed at GREEN
- **Committed in:** `b4d3b92`

**4. [Rule 1 - Bug] Five cases asserted a status a live clock can no longer produce**
- **Found during:** Task 1 and Task 2
- **Issue:** `test_a_term_ending_after_the_captured_instant_reports_active`,
  `test_revocation_wins_over_a_term_that_has_not_ended`,
  `test_grace_period_is_unreachable_from_a_proof_that_carries_no_renewal_payload`, the
  `("SUBSCRIPTION_STATE_CANCELED", UNEXPIRED, active)` state-map row and
  `test_the_same_term_carrying_an_offset_is_read_normally_control` all built a term ending
  2026-06-11 and asserted `active`. With the seam reading the live clock that term is over.
- **Fix:** Each now dates its open term from the live clock — `_live(offset)` on the Apple side,
  `OPEN_TERM` on the Play side. No assertion was weakened; the term moved, not the expectation.
- **Files modified:** `tests/unit/test_restore_proof.py`, `tests/unit/test_google_play_notifications.py`
- **Verification:** all five pass; the neighbouring exact-equality assertions on `expires_at` and
  `purchased_at` are untouched and pass
- **Committed in:** `f29a052` and `c66c847`

**5. [Rule 1 - Bug] Two docstrings named a captured instant the seam no longer holds**
- **Found during:** Task 1 and Task 2
- **Issue:** `_play_reader` in both test modules read "over a stubbed transport and a captured
  instant" / "and this module's captured instant". Neither is true once the reader takes no instant.
  The plan named only the two Apple helper docstrings.
- **Fix:** Both now state what the helper builds. The comment above `EVALUATED_AT` in the Play module
  was deleted for the same reason the plan deletes the Apple one.
- **Files modified:** `tests/unit/test_restore_proof.py`, `tests/unit/test_google_play_notifications.py`
- **Verification:** ruff clean; the modules are green
- **Committed in:** `f29a052` and `c66c847`

---

**Total deviations:** 5 auto-fixed (3 blocking, 2 bugs).
**Impact on plan:** No scope creep. Three deviations are call sites that name a signature this plan
changes, pulled into the commit that changes it so the unit suite is green at every commit. Two are
assertions and docstrings that state a fact the plan deletes, corrected where the fact dies. The
plan's task boundaries moved; its content did not.

## Issues Encountered

**One pre-existing e2e failure, out of scope and not fixed.**
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`
expects the log event `proof_rejected` while the code emits `purchase_proof_rejected`. The failure
message was read this session and is identical to the one plans 47-01 and 47-03 measured at HEAD
before this phase started. It is recorded in `deferred-items.md` and in `.planning/WINDOWS.md`. The
restore e2e file is therefore 36 passed / 1 failed and the whole e2e suite is 361 passed / 1 failed.

**One acceptance criterion cannot be met as written because of it.** Task 3's criterion
"`uv run pytest -q -m e2e tests/e2e/test_restore_subscription.py` exits 0" is unreachable while that
failure stands. Every other criterion of that task passes, and the file's exit code is what it was
before this plan.

**One ruff fix was applied mechanically.** Adding `_CANCELED_STATE` and `_status_for` to the Play
module's import block left it unsorted; `ruff check --fix` reordered it and nothing else.

## Known Stubs

None. No hardcoded empty value, placeholder string or unwired component was written.

## Threat Flags

None. T-47-11's mitigation held: `_transaction_status` and `_status_for` keep their signatures,
their bodies and their `>` comparisons verbatim, and both now carry parametrized cases pinning the
exact equality. T-47-12's mitigation held: all four Play signatures changed in one commit and
`tests/unit/test_adapter_interfaces.py` ran in the same task. T-47-13's mitigation held: the webhook
dependency lost one parameter and one argument and no control flow line moved. T-47-04's mitigation
held: both boundaries relocated onto helpers that take their datetime. No package was installed and
no manifest was touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The `auth/` package is done for this phase. Neither adapter takes a datetime, and the package
  shape ratchet `CURRENT = (8, 24, 67)` is untouched, so Phase 49 still sees the tuple it planned
  against.
- `PlaySubscriptionSource` is still declared, with both methods now free of the parameter, so the
  concrete class conforms until Phase 49 deletes the Protocol.
- `app/dependencies.py` is down to five `get_evaluated_at` occurrences: the definition and the four
  service factories plans 47-05, 47-06 and 47-07 own. `get_session_factory`, `get_firebase_adapter`,
  `get_devicecheck_adapter`, `get_challenge_store`, every `request.app.state.*` read and every
  `Request` parameter are untouched for Phases 49 and 50.
- `services/restore.py` keeps its constructor field and its seven remaining readers for plan 47-05,
  which also relocates `test_a_term_ending_at_the_captured_instant_is_not_open` onto the new
  `_open_term` helper and deletes the `pinned_evaluation_instant` fixture. That fixture and its one
  surviving consumer are both still in place, as the plan required.
- One thing to carry forward: `OPEN_TERM` in `tests/unit/test_google_play_notifications.py` and
  `_live(offset)` in `tests/unit/test_restore_proof.py` read the wall clock at import and at call.
  Both name a term ten days out, so no ordinary run can straddle it, but they are now clock-dependent
  where they were not.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*

## Self-Check: PASSED

Every file named in `key-files.modified` exists on disk, and all five task commits of this plan are
reachable in `git log`.
