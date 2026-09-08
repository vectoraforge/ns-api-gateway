---
phase: 45-post-auth-restore-subscription
plan: 01
subsystem: api
tags: [fastapi, sqlmodel, postgres, app-store-server-library, subscriptions, entitlements]

# Dependency graph
requires:
  - phase: 43-post-webhooks-app-store
    provides: AppStoreNotifications and its pinned-root SignedDataVerifier, SubscriptionsDB.write_subscription_grant, lock_grants, ENTITLED_STATUSES
  - phase: 44-post-webhooks-google-play-rtdn
    provides: GooglePlayConfig.package_name and the two Play classes on app.state
  - phase: 42-post-auth-claim-registered-grant
    provides: SyncService.read_entitlement and the SyncResponse-with-no-store response shape
provides:
  - "POST /auth/restore-subscription, the seventh auth route, under get_linked_identity"
  - "RestoredSubscription, the value type a client-presented store proof crosses the auth/ seam as"
  - "AppStoreNotifications.verify_transaction and _transaction_status: the local Apple proof check"
  - "RestoreService: the store call first, then the entitled read, the grant locks, the writer, one commit"
  - "RestoreRefused/RestoreSubscriptionNotEntitled at 404 restore_not_found, RestoreProviderUnknown at 403"
  - "seed_subscription, the e2e factory for a core.subscriptions row with a nullable owner"
affects: [45-02 google play restore, 45-03 adoption and owner claim, 45-04 the capped move, 45-05 requirements amendments]

actuals:
  tokens: 37338
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "The store call is the service's first statement, measured by a counting session rather than asserted in prose"
    - "A second entry point on an existing auth/ store class, returning a second value type beside VerifiedNotification"
    - "A tracer arm that refuses what a later plan will serve, each one naming the plan that replaces it"

key-files:
  created:
    - src/nativespeaker/api/services/restore.py
    - tests/e2e/test_restore_subscription.py
    - tests/unit/test_restore_proof.py
  modified:
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/auth/store_notifications.py
    - src/nativespeaker/api/auth/app_store.py
    - src/nativespeaker/api/schemas/auth.py
    - src/nativespeaker/api/services/__init__.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/routers/auth.py
    - tests/e2e/conftest.py
    - tests/unit/test_error_contract.py
    - tests/unit/test_rejection_vocabulary.py
    - tests/unit/test_app_wiring.py
    - tests/unit/test_auth_package_shape.py

key-decisions:
  - "RestoreProviderUnknown declares 403 operation_not_allowed on its own rather than joining ClaimRefused, because every ClaimRefused leaf describes a grant claim; the totality walk permits a second class at the same code and status"
  - "The service refuses provider google_play with RestoreProviderUnknown rather than handing a Play purchase token to the Apple verifier; 45-02 replaces that arm with the Play read"
  - "verify_transaction refuses a transaction carrying no originalTransactionId with ProofRejected(stage=transaction_without_original_id), so an absent lifecycle key never becomes a lookup key"
  - "read_purchase and resolve_user are not called in this slice: nothing on the same-account path consumes either, and an unused local fails ruff F841; 45-03's adoption and attribution branches are where both earn their place"
  - "The e2e seed_subscription statement casts provider, status and the transfer month in SQL, because a bound parameter reaches PostgreSQL as text and the two enum columns refuse it"

patterns-established:
  - "Counting session: a session stand-in that counts exec calls, so 'the network call ran before the first statement' is an executed assertion and not a comment"
  - "Tracer refusal arms name the plan that replaces them, so a reader of the arm knows it is a stop and not a rule"

requirements-completed: [RESTORE-01, RESTORE-02]

coverage:
  - id: D1
    description: "A caller whose account already owns the Apple subscription the proof names gets 200 and the sync body, with Cache-Control no-store"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_a_verified_proof_attaches_the_paid_grant_and_the_body_reports_it"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_the_one_grant_it_wrote_is_the_subscription_grant_and_its_usage_row"
        status: pass
    human_judgment: false
  - id: D2
    description: "A repeat restore of the same Apple proof writes no new grant row and no new usage row, and the monthly counter keeps its value"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_a_repeat_restore_writes_no_new_row_and_resets_no_counter"
        status: pass
    human_judgment: false
  - id: D3
    description: "A caller naming a store the server does not serve gets 403 operation_not_allowed, byte-identical to the claim routes' refusal body, and no proof check runs"
    requirement: RESTORE-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_a_store_the_server_does_not_serve_is_refused_before_any_proof_check"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#test_an_empty_store_name_is_the_frameworks_own_refusal"
        status: pass
    human_judgment: false
  - id: D4
    description: "The Apple proof check completes before the first session statement, and a request refused by the surface gate or by the proof check runs no session statement at all"
    requirement: RESTORE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestTheStoreCallRunsBeforeTheSessionsFirstStatement"
        status: pass
    human_judgment: false
  - id: D5
    description: "A signed transaction that does not verify gets 403 proof_rejected, and the stage is a closed-set name carrying no part of the proof; the vendored Apple root refuses the throwaway chain"
    requirement: RESTORE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestAProofThatDoesNotVerifyIsRefusedWithoutNamingItself"
        status: pass
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#test_the_vendored_apple_root_refuses_the_same_proof_control"
        status: pass
    human_judgment: false
  - id: D6
    description: "Apple's status derived from a bare signed transaction: revoked, active or expired, with grace and billing retry proved unreachable"
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestTheStatusComesFromTheTransactionAlone"
        status: pass
    human_judgment: false
  - id: D7
    description: "The four hand-maintained ratchets carry their new values: the error-code mirror, the rejection vocabulary, the narrowed-route lists and the auth package shape"
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_app_wiring.py tests/unit/test_error_contract.py tests/unit/test_rejection_vocabulary.py tests/unit/test_auth_package_shape.py tests/unit/test_docstring_bar.py -q"
        status: pass
    human_judgment: false
  - id: D8
    description: "The native-only gate refuses no paying customer on a surface heuristic: only an unserved store name and an artifact that does not verify may refuse"
    requirement: RESTORE-02
    verification: []
    human_judgment: true
    rationale: "The prohibition is a judgment about what the code does NOT do. No test can assert the absence of a future heuristic; a reader must confirm the handler reads no platform header and no native_claim_platform column."

# Metrics
duration: 15 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 01: End-to-end same-account Apple restore Summary

**`POST /auth/restore-subscription` shipped for one path — a StoreKit 2 signed transaction verified locally against the vendored Apple root, then the webhook's own grant writer under the standard lock order, answering the sync body.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-09-08T00:48:49Z
- **Completed:** 2026-09-08T01:03:00Z
- **Tasks:** 2
- **Files modified:** 15 (3 created, 12 modified)

## Accomplishments

- The seventh auth route, `POST /auth/restore-subscription`, under `get_linked_identity`, `Depends()`-only, answering `SyncResponse` with `Cache-Control: no-store`.
- `AppStoreNotifications.verify_transaction`: the library's own `verify_and_decode_signed_transaction` — chain, both Apple OIDs, ES256, bundle id and environment — refused with `ProofRejected` rather than the webhook's 401 `NotificationRejected`.
- `RestoreService`: the store call is the first statement of the request, then the non-locking entitled read, then `lock_grants`, then `write_subscription_grant` unchanged, then one deliberate `commit()`.
- Idempotence proved on the wire: a second identical restore leaves the grant row id and the monthly counter untouched, because the term expression matches `SubscriptionsService.ingest`'s and the writer answers `replayed`.
- All four hand-maintained ratchets updated, the `auth/` package shape re-measured at `(8, 24, 55)` rather than guessed.

## Task Commits

1. **Task 1: End-to-end same-account Apple restore — one path only** — `97e7bb9` (feat)
2. **Task 2: Unit proof of the Apple check and the call ordering** — `2492560` (test)

**Plan metadata:** see the `docs(45-01)` commit that carries this file.

## Files Created/Modified

- `src/nativespeaker/api/services/restore.py` — `RestoreService`; the proof check, the entitled read, the locks, the writer, one commit
- `src/nativespeaker/api/auth/app_store.py` — `verify_transaction` and the module-level `_transaction_status`
- `src/nativespeaker/api/auth/store_notifications.py` — `RestoredSubscription`, the restore value type beside `VerifiedNotification`
- `src/nativespeaker/api/errors.py` — the `restore_not_found` code, `RestoreRefused` and its leaf, `RestoreProviderUnknown`
- `src/nativespeaker/api/schemas/auth.py` — `RestoreRequest`, both fields `Field(..., min_length=1)`, `provider` a plain `str`
- `src/nativespeaker/api/app/dependencies.py` — `get_restore_service`, taking `Request` for the store class on `app.state`
- `src/nativespeaker/api/routers/auth.py` — the route, the surface gate, and the docstring now naming seven routes
- `src/nativespeaker/api/services/__init__.py` — `RestoreService` in `__all__` and the import block
- `tests/e2e/conftest.py` — `seed_subscription`, and the restore entry point on `FakeAppStoreNotifications`
- `tests/e2e/test_restore_subscription.py` — the happy path, the rows it wrote, the repeat, and the two gate refusals
- `tests/unit/test_restore_proof.py` — the real chain, the real-root control, the three rejection arms, the status derivation, the ordering
- `tests/unit/test_error_contract.py`, `tests/unit/test_rejection_vocabulary.py`, `tests/unit/test_app_wiring.py`, `tests/unit/test_auth_package_shape.py` — the four ratchets

## Decisions Made

- **`RestoreProviderUnknown` stands alone rather than joining `ClaimRefused`.** The totality walk permits a second class carrying `operation_not_allowed` at 403, because it only refuses one code at two *different* statuses. Every `ClaimRefused` leaf describes a grant claim, so a fifth sibling would read oddly — RESEARCH § Pattern 5 said as much.
- **A `google_play` proof is refused by the service, not verified by the Apple check.** The router's gate only rejects a string outside `PurchaseProvider`; `google_play` is a member. Without an explicit arm, a Play purchase token would have been handed to `SignedDataVerifier`. 45-02 replaces the arm with the Play read.
- **`verify_transaction` refuses a transaction with no `originalTransactionId`.** That field is the lifecycle key the subscription row is looked up by; letting it be absent would make the lookup key `None`.
- **The e2e `seed_subscription` statement casts its enum parameters in SQL.** The analog hard-codes `'apple'` and `'active'` as literals, so the cast never came up before; a bound parameter reaches PostgreSQL as `character varying` and the two enum columns refuse it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The `seed_subscription` INSERT was refused by PostgreSQL**
- **Found during:** Task 1 (the e2e cases)
- **Issue:** `DatatypeMismatchError: column "provider" is of type core.subscription_provider but expression is of type character varying`. The lifted column list came from a statement whose provider and status were SQL literals, so no cast was needed there.
- **Fix:** `CAST(:provider AS core.subscription_provider)`, `CAST(:status AS core.subscription_status)` and `CAST(:transfer_month AS DATE)` in the statement.
- **Files modified:** `tests/e2e/conftest.py`
- **Verification:** all five cases in `tests/e2e/test_restore_subscription.py` pass.
- **Committed in:** `97e7bb9`

**2. [Rule 2 - Missing Critical] An unserved-but-known store would have reached the Apple verifier**
- **Found during:** Task 1 (`RestoreService`)
- **Issue:** The plan says to build the Apple path only and not the Google branch, but says nothing about what a `provider` of `google_play` does. The router gate admits it, so a Play purchase token would have been passed to `verify_and_decode_signed_transaction`.
- **Fix:** `RestoreService._verify` raises `RestoreProviderUnknown` for any provider that is not Apple, with an inline comment naming 45-02 as the plan that replaces the arm.
- **Files modified:** `src/nativespeaker/api/services/restore.py`
- **Verification:** `tests/unit/test_restore_proof.py::test_a_store_the_deployment_does_not_serve_runs_no_statement_at_all`
- **Committed in:** `97e7bb9`

**3. [Rule 2 - Missing Critical] A transaction with no `originalTransactionId` had no refusal**
- **Found during:** Task 1 (`verify_transaction`)
- **Issue:** `JWSTransactionDecodedPayload.originalTransactionId` is `str | None`. An absent value would have become the lifecycle key the subscription row is read by.
- **Fix:** `raise ProofRejected(stage="transaction_without_original_id")` before the value type is built, so nothing is read and nothing is written.
- **Files modified:** `src/nativespeaker/api/auth/app_store.py`
- **Verification:** `RestoredSubscription.external_id` is typed `str`, and `uv run pytest -q` is green.
- **Committed in:** `97e7bb9`

### Departures from the plan text (not auto-fixes)

**4. `read_purchase` and `resolve_user` are not called in this slice.** The plan's step 2 lists three non-locking reads in `SubscriptionsService.ingest`'s order. Nothing on the same-account path consumes the purchase row or the resolved token, and an assigned-but-unused local fails `uv run ruff check` (F841), which the plan lists as an acceptance criterion. `PurchasesDB` is therefore not constructed either. 45-03's adoption branch and its attribution comparison are where both reads earn their place, and the read order they must take is unchanged.

**5. The term expression differs from `services/subscriptions.py`'s by its receiver name only.** The acceptance criterion asks for a textually identical `starts_at`/`ends_at` expression. The value crossing the seam here is `RestoredSubscription`, not `VerifiedNotification`, so the receiver is `proof.` rather than `notification.`. Operands, operator order, line breaks and both comments match character for character, which is what makes `grant.ends_at == ends_at` match and the repeat restore a replay — proved on the wire by `test_a_repeat_restore_writes_no_new_row_and_resets_no_counter`.

---

**Total deviations:** 3 auto-fixed (1 blocking, 2 missing critical), plus 2 documented departures from the plan text.
**Impact on plan:** No scope creep. The two missing-critical fixes close paths the plan did not name; the two departures narrow the slice rather than widening it, and both name the plan that closes them.

## TDD Gate Compliance

Task 2 carries `tdd="true"`, but Task 1 is a `type="tracer"` task that ships the behaviour Task 2 measures. A RED gate was therefore not reachable: the cases pass on first run because the tracer already built the code they exercise. Task 2 is committed as one `test(45-01)` commit. Two of its cases are their own controls — the vendored-root case makes the chain assertion non-vacuous, and `test_the_counting_session_really_counts_control` makes the two zero-statement assertions non-vacuous.

## Known Stubs

| File | Line | Stub | Resolved by |
|---|---|---|---|
| `src/nativespeaker/api/services/restore.py` | 81-83 | `_verify` refuses every provider that is not Apple | 45-02 (the Play read) |
| `src/nativespeaker/api/services/restore.py` | 45-47 | No stored subscription row raises `RestoreSubscriptionNotEntitled` | 45-03 (adoption with creation) |
| `src/nativespeaker/api/services/restore.py` | 54-56 | Any owner other than the caller raises `RestoreSubscriptionNotEntitled` | 45-03 (adoption), 45-04 (the capped move) |

Each stub is a refusal that writes nothing, and each carries an inline comment naming the plan that replaces it. None of them prevents this plan's goal: the same-account Apple restore works end to end.

## Threat Flags

None. Every file touched is inside the plan's declared trust boundaries, and no new network endpoint, auth path or schema change was introduced beyond the route the threat register already covers.

## Issues Encountered

None beyond the three auto-fixed deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 45-02: `RestoredSubscription` and the `_verify` seam are the two places the Play read plugs into, and `RestoreService.package_name` is already carried for it.
- 45-03 inherits two refusal arms to replace and the read order to complete; the lock order and the writer call it will reuse are already in place and under test.
- Flagged assumption A2 stands unchanged: no iOS app exists, so no real Apple artifact has ever reached this deployment. The first real refusal from Apple is authoritative over anything this plan writes. 45-05 records it in REQUIREMENTS.md.

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*

## Self-Check: PASSED

- All three created files exist on disk.
- Both task commits (`97e7bb9`, `2492560`) are in the log.
- Every task acceptance criterion re-run and passing; both task `<verify>` blocks and the plan-level `<verification>` green: `uv run pytest -q` (1215 passed), `uv run pytest -m e2e -q` (303 passed), `uv run ruff check src tests` clean, and the route decorator literal appears exactly once.
