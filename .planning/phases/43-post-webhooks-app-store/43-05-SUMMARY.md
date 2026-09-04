---
phase: 43-post-webhooks-app-store
plan: 05
subsystem: payments
tags: [concurrency, postgres, race, webhooks, config, logging, security]

# Dependency graph
requires:
  - phase: 43-01
    provides: "the route, the scripted seam fixture, `tests/e2e/test_app_store_webhook.py` and the refusal body constants"
  - phase: 43-03
    provides: "`core.store_purchases`, the inverse token read and `AttributionConflict`"
  - phase: 43-04
    provides: "the grant writer under two lock tiers, and `tests/schema/test_subscription_ingestion.py`'s buyer harness"
  - phase: 42-07
    provides: "the two-connection race harness in `tests/schema/test_claim_race.py` and the SQLSTATE 23505 idiom"
provides:
  - "`tests/schema/test_subscription_race.py`: two deliveries on two real connections, one winner, one loser that wrote nothing"
  - "The wire-level refusal matrix: `REJECTED_BODY` as raw bytes, compared with `response.content`"
  - "`REFUSAL_STAGES` derived from the library's status set, with a control that fails if it is narrowed"
  - "`unconfigured_app_store_notifications`: a real seam holding no verifier, in `tests/e2e/conftest.py`"
  - "The log-hygiene walk over every captured record, with a control that fails on an empty capture"
  - "The configuration gate: the two verification-skipping environments refused at load"
affects: [43-06, 44-webhook-google-play-rtdn, 45-restore-subscription]

actuals:
  tokens: 9000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A race module extends the claim race's session wrapper rather than writing a second one, adding only the SQLSTATE it carried"
    - "A refusal body is a module constant in two forms — a dict for equality and raw bytes for the wire"
    - "One spy over every level of both writing loggers, so a hygiene walk reads one list"

key-files:
  created:
    - tests/schema/test_subscription_race.py
  modified:
    - tests/e2e/test_app_store_webhook.py
    - tests/e2e/conftest.py
    - tests/unit/test_config.py

key-decisions:
  - "The race is unattributed on the seeded `paid` tier, so the three tables the plan names are the only ones written; the grant path is 43-04's and is already executed there."
  - "`REFUSAL_STAGES` is derived from `VerificationStatus` less `OK` rather than hand-written, with a control asserting the derivation, so an arm the library adds arrives as a new parameter instead of silently going untested."
  - "The unconfigured case swaps in a real `AppStoreNotifications(verifier=None)` rather than scripting `Unavailable` on the fake, because D-02's claim is about what an incomplete configuration leaves behind, not about what a fake can be told to raise."
  - "The two library environment values are written as string literals in `tests/unit/test_config.py`; importing the library's enum would make the case follow a library change instead of catching it."
  - "APPLEHOOK-01 is NOT marked complete by this plan — see Deviations, as 43-01, 43-03 and 43-04 recorded."

patterns-established:
  - "A control case beside every walk: the refusal-stage derivation, the log-record walk and the verifier builder each ship with a case that fails when the walk is made vacuous"

requirements-completed: []

coverage:
  - id: D29
    description: "Two simultaneous deliveries of one `notification_uuid` on two real connections leave exactly one committed set of rows; the loser reads SQLSTATE 23505, rolls back having written nothing, and answers 5xx"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_race.py::TestTwoDeliveriesOfOneStoreKeyCommitOnce"
        status: pass
    human_judgment: false
  - id: D30
    description: "A third delivery after the race finds the event row and answers 200 writing nothing, so Apple's retry schedule converges"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_race.py::TestTwoDeliveriesOfOneStoreKeyCommitOnce::test_a_third_delivery_finds_the_event_row_and_writes_nothing"
        status: pass
    human_judgment: false
  - id: D31
    description: "Two deliveries carrying different store keys for one `(provider, external_id)` leave one purchase row, arbitrated by a unique index and never by the pre-write read"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_race.py::TestTwoStoreKeysForOneLifecyclePairCommitOnce"
        status: pass
    human_judgment: false
  - id: D32
    description: "Every reachable verification failure answers the byte-identical body `{\"code\":\"auth_required\"}` at 401, compared on the wire; a valid Firebase ID token changes nothing"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestEveryVerificationFailureAnswersTheOneBody::test_each_refusal_answers_the_same_401_body"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestEveryVerificationFailureAnswersTheOneBody::test_a_valid_firebase_token_does_not_change_the_refusal"
        status: pass
    human_judgment: false
  - id: D33
    description: "An incomplete `app_store` configuration answers 503 `verification_temporarily_unavailable` on a route that is still registered"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestEveryVerificationFailureAnswersTheOneBody::test_the_route_is_still_registered_while_the_seam_is_unconfigured"
        status: pass
    human_judgment: false
  - id: D34
    description: "A verified notification whose product id is absent from the configured map answers 500, adds no row to any of the three tables, and logs once at ERROR"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestTheReplayAndTheEmptyNotificationWriteNothing::test_an_unmapped_product_answers_500_and_writes_nothing"
        status: pass
    human_judgment: false
  - id: D35
    description: "A notification with no transaction part answers 200, writes nothing, and produces exactly one INFO record carrying the event type"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestTheReplayAndTheEmptyNotificationWriteNothing::test_a_notification_with_no_transaction_part_writes_nothing"
        status: pass
    human_judgment: false
  - id: D36
    description: "No log record written on this route carries the signed payload, either attribution token or a store token value, proved by a walk with a control that fails on an empty capture"
    requirement: APPLEHOOK-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_app_store_webhook.py::TestNoRecordCarriesASensitiveValue"
        status: pass
    human_judgment: false
  - id: D37
    description: "`StoreEnvironment` accepts exactly `sandbox` and `production`; the two library environment values that skip signature verification are refused at configuration load"
    requirement: APPLEHOOK-01
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py::TestTheStoreEnvironmentCannotSkipSignatureVerification"
        status: pass
    human_judgment: false
  - id: D38
    description: "The three `APP_STORE_*` variables land on `AppConfig.app_store`, and the tracked partial `app_store:` block deep-merges with them"
    requirement: APPLEHOOK-01
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py::TestTheThreeDeployerVariablesLandOnTheConfig"
        status: pass
    human_judgment: false
  - id: D39
    description: "A `production` configuration with no `app_apple_id` yields no verifier rather than raising, and `root_certificate_path` defaults to the committed Apple Root CA G3 which reads as bytes"
    requirement: APPLEHOOK-01
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py::TestAnIncompleteConfigurationBootsAndHoldsNoVerifier"
        status: pass
      - kind: unit
        ref: "tests/unit/test_config.py::TestTheDefaultRootCertificateIsTheCommittedAppleRoot"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-04
status: complete
---

# Phase 43 Plan 05: The Race, the Wire and the Configuration Gate — Summary

**The three properties this route could only assert are now executed: two simultaneous deliveries on two real PostgreSQL connections leave exactly one committed set of rows with a loser that wrote nothing, every refusal is byte-identical on the wire including one carrying a valid Firebase token, and a configuration that would make the library skip signature verification cannot be expressed.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-04T23:01:49Z
- **Completed:** 2026-09-04T23:14:00Z
- **Tasks:** 3 of 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- **Replay suppression is measured under contention, not argued.** Two deliveries of one `notification_uuid` are released together at a bounded barrier after both have read the event table and found nothing. Exactly one commits; the loser meets SQLSTATE `23505` at its flush, rolls back, and answers the generic 500. Afterwards there is exactly one row in each of `core.subscriptions`, `core.store_purchases` and `audit.subscription_events` — which is the assertion that the loser wrote nothing. A third, sequential delivery of the same key then finds the event row, emits zero flushes and answers 200, so Apple's retry schedule converges.
- **The race was proved non-vacuous by mutation.** Replacing the `asyncio.gather` with two sequential runs failed **9 of the 12** cases: both premises, both lost-race cases in each class, and the row-count case in the second class (a sequential second store key writes a second event row). The concurrency is what the passing suite depends on.
- **The refusal body is compared on the wire.** `REJECTED_BODY` is now `b'{"code":"auth_required"}'` and every verification arm asserts `response.content ==` it, so a more helpful field added later is a test failure rather than an oracle a prober can read. The parametrized arms are no longer a hand-written four: `REFUSAL_STAGES` is derived from the library's whole `VerificationStatus` set less `OK` — **seven** arms — with a control case asserting the derivation, so a narrowed tuple fails visibly.
- **The unconfigured case now uses a real seam.** `tests/e2e/conftest.py` gained `unconfigured_app_store_notifications`, which swaps `app.state.app_store_notifications` for a genuine `AppStoreNotifications(verifier=None)` — what an incomplete configuration actually leaves behind — and restores the original in a `finally`. Two cases assert 503 and that `/webhooks/app-store` is still in `app.routes` while the seam holds no verifier, which is the whole content of D-02.
- **Nothing sensitive reaches a record, and the walk is controlled.** One spy replaces `info`, `warning` and `error` on both writing loggers, five deliveries drive every recording arm, and the walk asserts the signed payload, both attribution tokens and a seeded store token appear in none of them. Its control asserts the captured event set is exactly `{store_notification_without_transaction, notification_rejected, unmapped_store_product, attribution_conflict}`; emptying the capture fails that control while the hygiene case still passes, which is the acceptance criterion measured rather than assumed.
- **The configuration cannot express an open endpoint.** `StoreEnvironment`'s member set is asserted by equality against the two-member literal, and `Xcode` and `LocalTesting` — written as string literals, never imported from the library's enum — are each refused at load with a `ValidationError`, guarded by a control that a named environment still loads. `production` with no `app_apple_id` yields `None` from `build_app_store_verifier` rather than the `ValueError` that would kill the pod at boot (P-04), with a control that a complete configuration yields a verifier.

## Task Commits

1. **Task 1: Two deliveries, one winner** — `05439c1` (test)
2. **Task 2: The refusal matrix, compared on the wire** — `caf192c` (test)
3. **Task 3: The configuration gate** — `0a1d6ed` (test)

## Files Created/Modified

**Created**

- `tests/schema/test_subscription_race.py` — 12 cases in two classes over the real `SubscriptionsService` against the migrated scratch database. It imports `_RacingSession`, `read` and `scalar` from `tests/schema/test_claim_race.py` and `PRODUCT_ID` and `_notification` from `tests/schema/test_subscription_ingestion.py` rather than copying either, and defines only what differs: `BARRIER_TIMEOUT_SECONDS = 20`, the `_Harness` carrying this test's `notification_uuid` prefix and `(provider, external_id)` pair, the FK-ordered clean-up keyed on both, and `_RacedSession`, which adds one thing to the claim race's wrapper — the SQLSTATE its violation carried.

**Modified**

- `tests/e2e/test_app_store_webhook.py` — `REJECTED_BODY` became raw bytes; `REFUSAL_STAGES` became a derivation with its control; `_ErrorSpy` became `_LogSpy` behind `_spy_on`, with three fixtures (`error_records`, `info_records`, `captured_records`); `_counts` and `_seed_store_token` were added; the unconfigured case was rewritten against the real seam and gained the route-registration case; the unmapped-product and transaction-less cases gained their row-count and record assertions; `TestNoRecordCarriesASensitiveValue` was added with its control. **28 cases**, up from 21.
- `tests/e2e/conftest.py` — `unconfigured_app_store_notifications`, in the shape `scripted_devicecheck_adapter` uses, and `AppStoreNotifications` added to the existing import.
- `tests/unit/test_config.py` — `load_tracked_config`, the `_APP_STORE_ENV` and `VERIFICATION_SKIPPING_ENVIRONMENTS` literals, and four classes: the environment gate, the three deployer variables and the deep merge, the default root certificate, and the incomplete-configuration builder. **26 cases**, up from 13.

## Decisions Made

1. **The race runs unattributed on the seeded `paid` tier.** The three tables the plan names — subscriptions, purchases, events — are then the only ones written, so the counts are exactly the arbitration under test. The grant path under contention belongs to 43-04's lock tiers and is already an executed case there; racing it here would have measured the same locks a second time through a noisier harness.

2. **`REFUSAL_STAGES` is derived, not enumerated.** The acceptance criterion is "every reachable verification status, one parameter each", which a hand-written tuple can only satisfy on the day it is written. Deriving it from `VerificationStatus` less `OK` makes a library addition arrive as a new parameter; the control case asserts the derivation itself, so narrowing the tuple is a failure rather than a silent gap. This is the opposite of Task 3's rule and deliberately so — there the point is to *catch* a library change, here it is to *track* one.

3. **The unconfigured seam is real, not scripted.** 43-01's case scripted `Unavailable` on the fake, which proves the error handler maps 503 and nothing about configuration. The new fixture builds the same object lifespan builds when `build_app_store_verifier` returns `None`, so the 503 comes from the production fail-closed path.

4. **The two library environment names are string literals.** Importing `Environment.XCODE` would make the case say "whatever the library calls this today", which is exactly the change the case exists to catch. A comment states the ground on the line above.

5. **The incomplete-configuration case is at the builder, not at a started app.** `build_app_store_verifier` is lifespan's own function and is where P-04's `ValueError` would be raised; asserting it answers `None` without raising is the same fact a boot test would establish, at a fraction of the cost, and the e2e module already proves the route answers 503 on a started app with no verifier.

## Deviations from Plan

### Departures from the plan's letter, taken deliberately

**1. Task 2 extended an existing matrix rather than building one.** The plan's `<action>` reads as though the refusal matrix, the Authorization-header case and the unmapped-product case were still to be written; 43-01 had already shipped all three. What this plan actually changed is what makes them binding: the byte comparison (`response.text` → `response.content` against a `bytes` constant), the derivation of the stage set from four hand-written names to seven with a control, the real unconfigured seam, the missing row-count and record assertions, and the log walk. Every acceptance criterion in the task is met; the diff is smaller than the action implies because the shape was already there.

**2. `Unavailable` was removed from the e2e module's imports.** It had exactly one use — scripting the fake for the unconfigured case — and decision 3 replaced that case. No other module changed.

**3. The post-rollback expiry hazard the plan warned about does not recur, and nothing was added to guard it.** The plan asked me to watch for Phase 42's failure — a SQLAlchemy rollback expiring every instance, so an ORM attribute read after the loser's rollback lazy-loads with no greenlet and answers 500 instead of the intended status. It does not happen here: `SubscriptionsService._settle` rolls back, logs `provider` off the frozen `VerifiedNotification` (never an ORM row), and raises `InternalError`; `routers/webhooks.py` returns an empty `Response` and reads nothing. The race case asserts `type(loser.result) is InternalError` — the exact class, not a subclass — so a greenlet failure or a refusal leaf reaching that arm would both fail it. No re-read was added because none is needed.

**4. `requirements.mark-complete` was NOT run for APPLEHOOK-01, and `.planning/REQUIREMENTS.md` is unmodified.** 43-CONTEXT.md D-26 assigns the dated APPLEHOOK-01 and APPLEHOOK-02 amendments, the header's conflict counts and the ROADMAP criterion to plan 43-06, which is the next and last plan in this phase. Checking the box here would leave the file internally inconsistent: the traceability row still reads "Pending", the adapter-seam note flagged forward under APPLEHOOK-01 is still unanswered, and APPLEHOOK-02's exact-path enumeration clause is settled in code but not yet recorded. 43-01, 43-03 and 43-04 each left it unchecked for the same reason and this follows them; `requirements-completed` above is empty accordingly. **The evidence gap those three cited is now closed** — 43-01 recorded D9 as `human_judgment: true` with the rationale "no two-connection harness runs against real PostgreSQL in this plan; plan 43-05 owns `tests/schema/test_subscription_race.py`". It exists, and D29 above supersedes that entry with an executed verification.

---

**Total deviations:** 0 auto-fixed, plus 4 recorded departures from the plan's letter.
**Impact on plan:** No scope creep, no new artifact beyond the plan's four files, and no production module touched — this plan writes tests only. The one plan instruction that could not be followed as written (the post-rollback re-read) is because the hazard it guards against was measured absent, which is the outcome the instruction asked for.

## Verification

All four gates green at completion, quoted from the tail of each run:

| Command | Result | Baseline (after wave 3) |
|---|---|---|
| `uv run pytest -q` | **1089 passed**, 454 deselected | 1076 |
| `uv run pytest -m e2e -q` | **272 passed**, 1271 deselected | 265 |
| `uv run pytest -m schema -q` | **182 passed**, 1361 deselected | 170 |
| `uv run ruff check src tests` | **All checks passed!** | clean |

Every acceptance grep in the plan matched:

- `grep -c "23505" tests/schema/test_subscription_race.py` → `2`
- `grep -icE "ix_subscription|constraint name|violates unique constraint" tests/schema/test_subscription_race.py` → `0`
- `pytestmark = pytest.mark.schema` in the race module → `1`; `BARRIER_TIMEOUT_SECONDS` defined at module level → `1`
- `REJECTED_BODY` declared as a `bytes` literal → `1`; `REJECTED` declared as a dict → `1`; `response.text == REJECTED_BODY` → `0`, replaced by `response.content == REJECTED_BODY`
- `appstoreserverlibrary` in `tests/unit/test_config.py` → `0`; `VERIFICATION_SKIPPING_ENVIRONMENTS = ("Xcode", "LocalTesting")` → `1`
- `git status --porcelain -- migrations/ config/certs/` → empty; neither was modified

**Three controls were applied and observed, not assumed:**

1. Replacing the race's `asyncio.gather` with two sequential `await`s failed 9 of the 12 race cases, including both premises and every lost-race assertion. The barrier is what makes the contention real.
2. Making the hygiene walk return `[]` failed `test_the_walk_sees_the_records_the_deliveries_produced` while `test_no_record_carries_the_payload_an_attribution_token_or_the_store_token` still passed — exactly the acceptance criterion's demand that the control, not the hygiene case, is what catches an empty capture.
3. The two shipped controls in the source: `test_every_reachable_arm_is_covered_by_one_parameter` (a narrowed stage tuple fails) and `test_a_complete_production_configuration_yields_one` (a builder that always answered `None` would pass the three incomplete-configuration cases without it).

All mutations were reverted and each suite re-run green immediately afterwards.

## Known Stubs

None. No placeholder value was introduced. 43-01's one recorded stub — the placeholder App Store product id in `config/config.yaml` — is untouched; `tests/unit/test_config.py` now asserts that every value in that map is one of the three seeded tier ids, which fails loudly if the operator's edit points at a tier that does not exist.

## Threat Flags

None. This plan adds no network endpoint, no auth path and no schema change; it writes test modules only. The five `mitigate` dispositions in the plan's register are each an executed case:

| Threat | Mitigation, as executed |
|---|---|
| T-43-03 replay under contention | the two-connection race: one winner, one loser that wrote nothing, arbitrated by a unique index rather than the pre-write read |
| T-43-05 the refusal body as an oracle | every arm compared as raw response bytes, over the library's whole reachable status set |
| T-43-04 an environment that skips verification | `Xcode` and `LocalTesting` refused at load, asserted with string literals so the case survives a library change |
| T-43-19 a misconfigured deployment losing six days of notifications | `production` without `app_apple_id` yields no verifier rather than raising, and the route answers 503 while still registered |
| T-43-06 a sensitive value in a log record | one walk over every captured record, with a control proving the walk sees records |

T-43-SC is `accept` and holds: no package was installed and no dependency file was edited.

## Issues Encountered

**Two authoring errors, both caught before their commit.** `_counts` was first written as `tuple(await ... for model in ...)`, which Python reads as an async generator and which raised `TypeError: 'async_generator' object is not iterable`; it became an explicit loop. `_store(**overrides)` in the configuration class first passed its four fixed keywords beside `**overrides`, so every override collided; it became a dict merged with `|`. Neither reached a commit and neither changed any assertion.

**One import-order fix from `ruff --fix`** after `from sqlalchemy import func` was added to the e2e module.

**Nothing else.** No package was installed, no migration was touched, no dependency file was edited, and no authentication gate was reached.

## User Setup Required

None by this plan. The three App Store environment variables 43-02 documented are still what a deployer must supply; `tests/unit/test_config.py` now proves all three land on `AppConfig.app_store` and that omitting `app_apple_id` under `production` fails closed rather than crashing the pod.

## Next Phase Readiness

**Ready for 43-06**, the last plan in this phase. Three things this plan settled belong in its record:

- **APPLEHOOK-01's last evidence gap is closed.** 43-01's coverage entry D9 was `human_judgment: true` pending exactly this harness. The amendment can now state the concurrency guarantee as executed rather than as read from code.
- **The refusal arms are seven, not four.** P-11's operational point — that `INVALID_APP_IDENTIFIER` and `INVALID_ENVIRONMENT` in the `stage` field mean *this deployment is misconfigured* rather than *someone is probing you*, and that the operator has about six days before Apple stops retrying — is now backed by a parametrized case over the library's whole status set. Worth the one sentence P-11 asked for.
- **The environment gate is a security control with a test that names it.** D-11 states the two-member enum; what was not written down anywhere is that the two values it excludes make the library skip signature verification entirely, so a free-text field with a case transformation would turn a credential-free public route into an open endpoint. That belongs in the amendment beside D-09's divergence, not only in a test comment.

**For Phase 44 (Google Play).** `tests/schema/test_subscription_race.py` races the service, not the Apple seam: it builds a `VerifiedNotification` directly and never touches `AppStoreNotifications`. A Google class producing the same value type inherits the whole race proof unchanged, and `_Harness`'s private key is already `(notification_uuid prefix, external_id)` rather than anything Apple-specific.

**For Phase 45 (restore).** The race harness is the shape restore's own contention case wants: restore links a `core.subscriptions` row to a user while an ingestion may be writing the same row, and `_RacedSession` already records which flush the violation arrived at.

**One concern carried forward unchanged.** RESEARCH § Security residual 3 — the route is publicly reachable with no credential and no limiter at either layer, and each request costs a certificate-path build plus up to three ES256 verifications. Nothing in this plan changes it; 43-01's summary asks 43-06 to record it as accepted on the Phase 35 D-05/D-08 precedent, and in wording that says it is wider than its three predecessors rather than one more of the same.

## Self-Check: PASSED

`tests/schema/test_subscription_race.py` exists on disk, all three modified files are present, and the three task commits (`05439c1`, `caf192c`, `0a1d6ed`) are in `git log`.

---
*Phase: 43-post-webhooks-app-store*
*Completed: 2026-09-04*
