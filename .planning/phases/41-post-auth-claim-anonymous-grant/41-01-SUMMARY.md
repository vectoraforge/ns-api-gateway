---
phase: 41-post-auth-claim-anonymous-grant
plan: 01
subsystem: auth
tags: [devicecheck, apple, httpx, pyjwt, es256, tenacity, sqlmodel, postgres, fastapi, grants]

requires:
  - phase: 40-post-auth-upgrade-anonymous
    provides: "AuthService._complete's locate-claim-commit-work-spend sequence, the scripted-fake pattern, the IntegrityError-without-naming-a-constraint rule"
  - phase: 38-post-auth-sync
    provides: "SyncService.read_entitlement and the six-field Entitlement block the claim's response reuses"
  - phase: 37.2-challenge-issuance
    provides: "POST /auth/challenge, which already issues for claim_anonymous_grant"
provides:
  - "POST /auth/claim-anonymous-grant, behind get_linked_identity, answering SyncResponse with Cache-Control: no-store"
  - "auth/devicecheck.py — the Apple DeviceCheck seam: the Protocol, BitState, the ES256 service JWT, both wire calls, five ordered parse arms and the three-attempt budget"
  - "GrantsDB.activate_anonymous_device_grant — the one writer of an anonymous_device_grant, four rows in one flush under the fixed lock order"
  - "GrantsDB.has_prior_free_grant and FREE_GRANT_SOURCES — the lifetime free-grant membership, named once"
  - "AccessGrantAntiAbuse — the core.access_grants_anti_abuse model, its generated column left unmapped"
  - "AuthService._complete generalised over an injected post_claim callable, plus _read_then_write for the two Firebase routes"
  - "get_evaluated_at — one captured instant per request, shared by the auth and sync services by construction"
  - "ProofRejected, DeviceGrantExhausted, ClaimRefused, ClaimantNotAnonymous; ErrorCode 16 to 18"
affects: [41-02, 41-03, 41-04, 41-05, "phase 42 registered account grant"]

actuals:
  tokens: 117797
  tasks: 2
  commits: 2

tech-stack:
  added: ["httpx >=0.28 promoted from the dev group into [project].dependencies"]
  patterns:
    - "An external-SDK seam that handles secret material holds no logger, mirroring crud/challenges.py"
    - "A vendor response is classified by ordered arms with nothing falling through to a default"
    - "A crud writer takes both lock tiers, re-reads the identity row without a lock, and flushes once"
    - "The shared completion sequence takes an injected post-claim callable rather than forking"
    - "One captured instant per request comes from a FastAPI dependency, so co-used services share it"

key-files:
  created:
    - src/nativespeaker/api/auth/devicecheck.py
    - tests/e2e/test_claim_anonymous_grant.py
    - tests/unit/test_devicecheck_adapter.py
  modified:
    - src/nativespeaker/api/crud/grants.py
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/routers/auth.py
    - src/nativespeaker/api/tables/grants.py
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/schemas/auth.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/config.py
    - .env.example
    - pyproject.toml
    - tests/e2e/conftest.py

key-decisions:
  - "The DeviceCheck Protocol is declared beside its implementation in auth/devicecheck.py, not in auth/adapters.py, whose import allowlist excludes httpx"
  - "The seam holds no logger at all, so no code path exists that could write a raw device token"
  - "Unavailable is reused for every ambiguity and exhaustion arm; no third error class was minted"
  - "activate_anonymous_device_grant returns a bool rather than raising, so the race loser and the in-window ineligibility both fall through to the shared post-commit read"
  - "get_evaluated_at makes the shared instant structural: the auth and sync services on this route now take one cached value instead of two independent clock reads"
  - "The three non-anonymous preflight refusals raise the ClaimRefused base until plan 41-03 gives them leaves"

patterns-established:
  - "Ordered vendor-response parse arms: definitive refusal, retryable status, documented plain-text arm, the structured arm, then fail closed"
  - "A bit read from a vendor is an input to the write it precedes, never re-derived"
  - "Lock tier one is the grant rows, tier two their usage rows, and the identity row is revalidated by a plain re-read"

requirements-completed: [ANONGRANT-01, ANONGRANT-02]

coverage:
  - id: D1
    description: "A linked anonymous caller obtains a handle for claim_anonymous_grant and spends it at POST /auth/claim-anonymous-grant, receiving 200 with a SyncResponse body and Cache-Control: no-store"
    requirement: "ANONGRANT-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#test_a_never_set_device_claims_the_grant_and_the_body_reports_it"
        status: pass
    human_judgment: false
  - id: D2
    description: "One successful claim leaves exactly four writes: the grant row on the anonymous tier, its anti-abuse row carrying ios_devicecheck with both hash columns NULL, its usage row at zero, and the identity row's free_grant_consumed_at and native_claim_platform"
    requirement: "ANONGRANT-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_claim_anonymous_grant.py#test_a_never_set_device_claims_the_grant_and_the_body_reports_it"
        status: pass
    human_judgment: false
  - id: D3
    description: "The activation transaction takes grant rows FOR UPDATE ascending by id, then their usage rows, and no third tier; the identity row is revalidated by a plain non-locking re-read"
    requirement: "ANONGRANT-02"
    verification:
      - kind: other
        ref: "grep -c lock_identity_and_user src/nativespeaker/api/services/auth.py returns 1 (the upgrade's pre-existing call); the writer calls lock_effective_grants then lock_usage then resolve_existing"
        status: pass
    human_judgment: true
    rationale: "The grep pins that no second user-row lock was added, but the ordering itself is asserted structurally only by plan 41-04's live two-connection race; until that lands a reader must confirm the order by reading the writer."
  - id: D4
    description: "Both Apple calls run strictly after the challenge claim is committed and strictly before the activation transaction opens, so no network call happens under a held lock"
    requirement: "ANONGRANT-02"
    verification: []
    human_judgment: true
    rationale: "The ordering is visible in _claim_anonymous_grant but nothing asserts it yet; plan 41-03's structural ordering test is the standing proof."
  - id: D5
    description: "The DeviceCheck update carries bit0 true and the bit1 the query returned, never a fabricated bit1"
    verification:
      - kind: unit
        ref: "tests/unit/test_devicecheck_adapter.py#TestTheBit1CarryForward::test_a_query_answering_bit1_true_produces_an_update_carrying_bit1_true"
        status: pass
      - kind: unit
        ref: "tests/unit/test_devicecheck_adapter.py#TestTheBit1CarryForward::test_a_query_answering_both_false_produces_an_update_carrying_bit1_false"
        status: pass
    human_judgment: false
  - id: D6
    description: "Only Apple's explicit confirmation permits activation: an exhausted budget, an unparseable body and a body that is neither a bit-state object nor the documented never-set string all answer 503 and write nothing"
    verification:
      - kind: unit
        ref: "tests/unit/test_devicecheck_adapter.py#TestTheParseArms"
        status: pass
    human_judgment: false
  - id: D7
    description: "The ES256 service JWT decodes with kid in the header, alg ES256, iss the team id and an integer iat, minted fresh per call, with a transaction id that is never the challenge handle"
    verification:
      - kind: unit
        ref: "tests/unit/test_devicecheck_adapter.py#TestTheServiceJwt"
        status: pass
      - kind: unit
        ref: "tests/unit/test_devicecheck_adapter.py#TestTheRequestBodies::test_two_calls_carry_two_transaction_ids_and_neither_is_the_handle"
        status: pass
    human_judgment: false
  - id: D8
    description: "A raw device token cannot reach a log line: the seam module holds no logger and every error field comes from a closed set"
    verification:
      - kind: other
        ref: "python -c \"import nativespeaker.api.auth.devicecheck as m; print(hasattr(m,'logger'), hasattr(m,'structlog'))\" prints False False"
        status: pass
    human_judgment: false
  - id: D9
    description: "An absent DeviceCheck credential lets boot proceed and fails the route closed as 503, with no bypass on any code path"
    verification:
      - kind: unit
        ref: "tests/unit/test_devicecheck_adapter.py#TestAnAbsentCredentialFailsClosed"
        status: pass
    human_judgment: false
  - id: D10
    description: "A caller whose stored identity row is registered is refused 403 operation_not_allowed, read off the stored provider column and nothing else"
    verification: []
    human_judgment: true
    rationale: "ClaimantNotAnonymous is built and wired but the tracer exercises only the anonymous path; plan 41-03 owns the case matrix that drives this branch."

duration: 20min
completed: 2026-09-03
status: complete
---

# Phase 41 Plan 01: The anonymous device-grant claim tracer Summary

**A linked anonymous caller now claims an `anonymous_device_grant` end to end — Apple's bit0 read and set through a new ES256-signed DeviceCheck seam, four rows written in one locked transaction, and the entitlement read back after commit through the real router against a real database.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-09-03T05:01:05Z
- **Completed:** 2026-09-03T05:21:06Z
- **Tasks:** 2
- **Files modified:** 27

## Accomplishments

- `POST /auth/claim-anonymous-grant` exists and works: challenge in, `SyncResponse` out, `Cache-Control: no-store`, verified end to end against a live PostgreSQL through the real router.
- A new external-SDK seam, `auth/devicecheck.py`, mirroring `auth/firebase.py`'s structure — module constants, an internal retryable marker that never escapes, per-call ES256 signing, five ordered parse arms and a three-attempt budget — with **no logger**, so no code path could write a raw device token.
- One crud writer, `GrantsDB.activate_anonymous_device_grant`, taking both lock tiers and no third, re-reading the identity row without a lock, and writing the grant, its anti-abuse row, its usage row and the identity marker in **one flush** with an `IntegrityError` arm that names no constraint.
- `AuthService._complete` generalised over an injected `post_claim` callable rather than forked; the two Firebase routes now pass `partial(self._read_then_write, write=...)` and behave identically.
- `get_evaluated_at` makes "one captured instant per request" structural: the auth and sync services this route uses together now take one cached value instead of two independent clock reads.
- The Apple wire contract is executable rather than prose — 21 unit cases over `httpx.MockTransport`, including the bit1 carry-forward scripted **true** as well as false, and exact attempt counts at the transport.

## Task Commits

1. **Task 1: End-to-end anonymous device-grant claim (tracer)** - `7f5b424` (feat)
2. **Task 2: The Apple wire contract, pinned** - `9179ad3` (test)

## Files Created/Modified

- `src/nativespeaker/api/auth/devicecheck.py` — the seam: `DEVICECHECK_HOST`, `QUERY_PATH`, `UPDATE_PATH`, `DEVICECHECK_ATTEMPTS`, `BitState`, `DeviceCheckAdapter`, `AppleDeviceCheck`, `RetryableDeviceCheckError`, `_service_jwt`, `_parse_bit_state`, `read_bits_with_retry`, `write_bits_with_retry`, `read_private_key`
- `src/nativespeaker/api/crud/grants.py` — `_prior_free_grant_statement`, `has_prior_free_grant`, `activate_anonymous_device_grant`
- `src/nativespeaker/api/services/auth.py` — `PostClaim`, `_read_then_write`, `complete_claim_anonymous_grant`, `_claim_anonymous_grant`, `ANONYMOUS_TIER_ID`
- `src/nativespeaker/api/routers/auth.py` — the fifth route, and the docstring's count
- `src/nativespeaker/api/tables/grants.py` — `FREE_GRANT_SOURCES`, `AccessGrantAntiAbuse`
- `src/nativespeaker/api/errors.py` — `ProofRejected`, `DeviceGrantExhausted`, `ClaimRefused`, `ClaimantNotAnonymous`, `ErrorCode` 16→18
- `src/nativespeaker/api/schemas/auth.py` — `AnonymousGrantClaimRequest`
- `src/nativespeaker/api/app/dependencies.py` — `get_devicecheck_adapter`, `get_evaluated_at`, both wired in
- `src/nativespeaker/api/app/lifespan.py` — the adapter built at boot from an `httpx.AsyncClient` closed on shutdown, warning on an absent credential
- `src/nativespeaker/api/config.py` / `.env.example` — `DeviceCheckConfig` and its three variables; `config/config.yaml` deliberately untouched
- `pyproject.toml` — `httpx >=0.28` promoted into `[project].dependencies`
- `tests/e2e/conftest.py` — `FakeDeviceCheckAdapter` with two separate call lists, and `scripted_devicecheck_adapter`
- `tests/e2e/test_claim_anonymous_grant.py`, `tests/unit/test_devicecheck_adapter.py` — the new cases

## Decisions Made

- **The Protocol lives beside its implementation.** `auth/adapters.py` is fenced by an import allowlist that excludes `httpx`; putting `DeviceCheckAdapter` there fails `test_adapter_interfaces.py`.
- **No third error class for ambiguity.** `Unavailable` already answers 503 `verification_temporarily_unavailable`, so the exhausted budget, the timeout and the unrecognised body all converge on it.
- **`activate_anonymous_device_grant` returns a `bool`, it does not raise.** The race loser and an account that became ineligible inside the window both fall through to the same post-commit read, which is what makes the claim, the repeat and the loser answer one shape by construction rather than by three matching branches.
- **A transport failure is retryable.** `httpx.HTTPError` is converted to the internal marker carrying only the exception's class name, so a timeout exhausts to 503 rather than escaping as a 500.
- **`_service_jwt` fails closed before signing.** An absent key id, team id or PEM raises `Unavailable` with no request issued — the same shape `build_admin_apps` takes with no Firebase credential.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Four literal ratchets the plan did not enumerate went red**

- **Found during:** Task 1, after the implementation landed
- **Issue:** Adding four error classes and two `ErrorCode` members broke three literal registries the plan named none of — `tests/unit/test_rejection_vocabulary.py` (`EVENT_NAMES`, `CONSTRUCTOR_ARGUMENTS`), `tests/unit/test_error_registry.py` (the sorted 403-code list) and `tests/unit/test_error_contract.py` (`CONTRACT_CODES`). Each is a deliberate write-it-down ratchet, so each demanded the edit it exists to demand.
- **Fix:** Added the four new event names, the two new constructor rows, and the two new codes to the 403 list and the contract set.
- **Files modified:** `tests/unit/test_rejection_vocabulary.py`, `tests/unit/test_error_registry.py`, `tests/unit/test_error_contract.py`
- **Verification:** `uv run pytest -q` green at 888 passed
- **Committed in:** `7f5b424`

**2. [Rule 3 - Blocking] `test_sync_clock_capture.py` guarded a premise this plan deliberately moved**

- **Found during:** Task 1
- **Issue:** The file asserted `get_sync_service` calls the clock **exactly once**. The plan's own instruction — take the instant from `get_evaluated_at` so the two services on this route share one value — makes that count zero, and drops the vacuity control's floor from three clock calls in `dependencies.py` to two.
- **Fix:** Rewrote the class to assert the stronger invariant the change establishes: `get_evaluated_at` calls the clock exactly once, neither service dependency calls it at all, and both declare `Depends(get_evaluated_at)` for `evaluated_at`. Added a control proving the new `_depends_on` walk distinguishes a `Depends()` default from any other call, and lowered the vacuity floor to two with the reason.
- **Files modified:** `tests/unit/test_sync_clock_capture.py`
- **Verification:** the four new cases pass; the requirement tag `req~sessions-sync-single-evaluation-time~2` still names the class
- **Committed in:** `7f5b424`

**3. [Rule 3 - Blocking] Three precedence test apps had no `devicecheck_adapter` on `app.state`**

- **Found during:** Task 1 (58 failures)
- **Issue:** `get_auth_service` now declares `get_devicecheck_adapter`, which reads `request.app.state.devicecheck_adapter`. The three precedence files build a bare `FastAPI()` with no lifespan, so every auth route on them answered 500.
- **Fix:** Added `app.dependency_overrides[get_devicecheck_adapter] = lambda: None` beside each file's existing `get_firebase_adapter` override. Rejected the alternative of a `getattr(..., None)` default inside `get_devicecheck_adapter`: that would be production code shaped by a test's convenience, and `get_firebase_adapter` sets the opposite precedent.
- **Files modified:** `tests/unit/test_upgrade_precedence.py`, `tests/unit/test_create_user_body.py`, `tests/unit/test_create_user_precedence.py`
- **Verification:** all 58 restored to green
- **Committed in:** `7f5b424`

**4. [Rule 2 - Missing Critical] `AuthService.devicecheck` defaults to `None`**

- **Found during:** Task 1
- **Issue:** Four existing test files construct `AuthService` by keyword without a device-gate adapter. A required parameter would have broken them for no gain.
- **Fix:** `devicecheck=None` as the last parameter, exactly as `adapter=None` is already passed by those same call sites. The claim path is unreachable from any of them.
- **Files modified:** `src/nativespeaker/api/services/auth.py`
- **Committed in:** `7f5b424`

**5. [Rule 3 - Blocking] `.env.example` mentioned the key-path variable twice**

- **Found during:** Task 1 acceptance verification
- **Issue:** The acceptance criterion requires `grep -c "DEVICECHECK_PRIVATE_KEY_PATH" .env.example` to return exactly `1`; the explanatory comment repeated the literal name, making it 2.
- **Fix:** Reworded the comment to say "the key path below". Nothing is lost — the variable is on the next screen.
- **Committed in:** `7f5b424`

**6. [Rule 2 - Missing Critical] `AccessGrantAntiAbuse` and `FREE_GRANT_SOURCES` added to the `tables` barrel**

- **Found during:** Task 1
- **Issue:** `crud/grants.py` imports every other table from `nativespeaker.api.tables`. Leaving the two new names out would have forced a second import style in one file.
- **Fix:** Two lines in `src/nativespeaker/api/tables/__init__.py`, matching the convention `AccessGrant` already follows.
- **Committed in:** `7f5b424`

**7. [Rule 3 - Blocking] Two GSD scratch files were untracked and not ignored**

- **Found during:** Task 1 pre-commit review
- **Issue:** `.planning/state.json` and `.planning/milestone.lock` are runtime scratch, and commit `016ff4c` had already established the convention of ignoring GSD scratch.
- **Fix:** Two lines in `.gitignore`.
- **Committed in:** `7f5b424`

---

**Total deviations:** 7 auto-fixed (5 blocking, 2 missing critical)
**Impact on plan:** All seven are consequences of the plan's own instructions meeting ratchets it did not enumerate. No scope was added and none of the plan's decisions were reinterpreted. The one judgement call — deviation 2 — strengthened the guard rather than relaxing it.

## The `ClaimRefused` base-class branches, for plan 41-03

The plan asked for this list rather than a search. Three branches in
`AuthService._claim_anonymous_grant` currently raise the **base** `ClaimRefused`, and each needs its
own leaf so the log tells them apart while the client answer stays one body:

1. **An active grant of another source is held** — `held` is non-empty and no member has
   `source == anonymous_device_grant` (a subscription or a `manual` grant). One active grant per user.
2. **The lifetime marker is already set** — `identity.identity.free_grant_consumed_at is not None`
   with no active anonymous grant: a free grant that was consumed and is no longer active.
3. **A prior free grant of either source exists** — `GrantsDB.has_prior_free_grant` is true, in any
   status, matching `ix_access_grants_one_free_grant_per_user_source`.

`ClaimantNotAnonymous` (D-08) is the one leaf that already exists. All four answer
`403 operation_not_allowed` with the one-field body today; only the structured-log event name is
coarse for the three above.

## Deliberately Deferred (recorded, not missing)

- **`POST /v1/validate_device_token`** — not called. The query call already refuses an invalid token
  with a 400, which is the only answer this phase acts on; a separate validation round trip would
  double the Apple cost for no new decision.
- **bit1 as a *new* value** — read and carried forward, never written with a value this phase
  invented. Phase 42's registered claim owns it.
- **`api.development.devicecheck.apple.com`** — the host is a module constant with no config switch,
  so nothing a client can influence selects it.
- **The three refusal leaves above** — plan 41-03.

## Issues Encountered

None. The precondition (a live PostgreSQL 17 carrying the applied v2.0 schema) was verified reachable
before Task 1 began, and the e2e case's insert of the anti-abuse row succeeded against the live
schema on the first run — which is only possible while the table's stored generated column stays
unmapped.

## User Setup Required

**External credentials are needed before this route can reach Apple.** `.env.example` documents the
block: `DEVICECHECK_KEY_ID`, `DEVICECHECK_TEAM_ID` and `DEVICECHECK_PRIVATE_KEY_PATH`, the last
pointing at a `.p8` kept outside this repository at mode 600. No `USER-SETUP.md` was generated — the
plan declares no `user_setup` frontmatter, and their absence is a supported mode: boot proceeds with
a logged warning and the route fails closed as 503.

## Next Phase Readiness

Every layer the rest of the phase expands into is now proven by one path rather than assumed:

- **41-03** inherits the seam, the completion sequence and the refusal family, and owns the case
  matrix plus the structural proofs (the ordering test for D4 above, and the three refusal leaves).
- **41-04** inherits `FREE_GRANT_SOURCES`, the `IntegrityError` arm and the fixed lock order, and owns
  the live two-connection race that proves D3 and the loser's 200.
- **Phase 42** inherits an untouched bit1 and the *other* arm of the anti-abuse table's exclusive-or
  CHECK, so the registered claim still costs no migration.

**Concerns:** the Apple wire shapes remain `[ASSUMED]` — no official Apple page was fetchable during
research, and no iOS app exists to produce a real device token (D-04). `tests/unit/test_devicecheck_adapter.py`
carries that caveat in its module docstring, so the first real 400 from Apple reads as evidence about
those literals rather than as a regression.

---
*Phase: 41-post-auth-claim-anonymous-grant*
*Completed: 2026-09-03*

## Self-Check: PASSED

All three created files exist on disk; both task commits resolve in `git log`. The plan-level
verification was re-run whole after the final commit: `uv run pytest -m e2e tests/e2e/test_claim_anonymous_grant.py -q`
1 passed, `uv run pytest -q` 888 passed (baseline 856), `uv run pytest -m e2e -q` 218 passed,
`uv run pytest -m schema -q` 121 passed, `uv run ruff check src tests` clean, `ErrorCode` carries 18
members, the seam module has no logger, and `crud/grants.py` flushes exactly once.
