---
phase: 38-post-auth-sync
reviewed: 2026-09-09T20:00:01Z
depth: standard
files_reviewed: 141
files_reviewed_list:
  - AGENTS.md
  - config/config.yaml
  - docker-compose.yml
  - Dockerfile
  - .env.example
  - .gitignore
  - k8s/templates/deployment.yaml
  - k8s/templates/httproute-auth.yaml
  - k8s/templates/httproute-webhooks.yaml
  - k8s/templates/NOTES.txt
  - k8s/templates/security-policy.yaml
  - k8s/values.yaml
  - migrations/20260818_01_initial-release.sql
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/error_handlers.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/devicecheck.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/chats.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/__init__.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/crud/violations.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/logs.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/__init__.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/routers/webhooks.py
  - src/nativespeaker/api/schemas/api.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/schemas/llm.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/quota.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/services/sync.py
  - src/nativespeaker/api/tables/auth.py
  - src/nativespeaker/api/tables/chats.py
  - src/nativespeaker/api/tables/grants.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/purchases.py
  - tests/e2e/conftest.py
  - tests/e2e/test_app_store_webhook.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/e2e/test_create_user.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_google_play_webhook.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/e2e/test_sign_out_all.py
  - tests/e2e/test_sync.py
  - tests/e2e/test_upgrade_anonymous.py
  - tests/e2e/test_users_me.py
  - tests/schema/conftest.py
  - tests/schema/helpers.py
  - tests/schema/test_apply_rollback.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_constraints.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_inventory.py
  - tests/schema/test_registration_pairing.py
  - tests/schema/test_restore_race.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/schema/test_sync_lock_freedom.py
  - tests/unit/conftest.py
  - tests/unit/error_tree.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_chats_crud.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_config.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_conversion_carries_usage.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_identities_crud.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_identity_flip.py
  - tests/unit/test_jwks_offload.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_logging.py
  - tests/unit/test_models.py
  - tests/unit/test_monthly_period.py
  - tests/unit/test_purchases_crud.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_services.py
  - tests/unit/test_spent_free_grant_refusal.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_subscription_grant_write.py
  - tests/unit/test_subscription_store_clock.py
  - tests/unit/test_sync_clock_capture.py
  - tests/unit/test_sync_error_reuse.py
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_tables_metadata.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users_me.py
  - tests/unit/test_users.py
  - uv.lock
findings:
  critical: 1
  warning: 26
  info: 41
  total: 68
status: issues_found
---

# Phase 38: Code Review Report

**Reviewed:** 2026-09-09T20:00:01Z
**Depth:** standard
**Files Reviewed:** 141
**Status:** issues_found

## Summary

Re-review of phase 38 (`POST /auth/sync`) scoped incrementally to everything that changed
since the previous `38-REVIEW.md` commit (`52ac09d`) — 578 commits and 141 source files,
covering the phase 35-37.5 review-and-fix passes that landed on this branch. The scope was
split across seven parallel reviewers by module, each with a disjoint finding-ID block, then
merged here without narrowing.

Every reviewer checked `.planning/REQUIREMENTS.md` and the phase decision records before
filing, and dropped findings already settled by a ratified decision; those drops are recorded
per part below with their decision citations.

**Totals: 1 Critical, 26 Warning, 41 Info (68 findings).**

### Scope split

| Part | Module group | Files | ID block | C/W/I |
|---|---|---|---|---|
| 1 | infra + app/ + top-level src | 23 | 01-14 | 0/5/9 |
| 2 | auth/ + schemas/ + tables/ | 16 | 15-28 | 0/2/6 |
| 3 | crud/ + routers/ + services/ | 21 | 29-44 | 1/4/3 |
| 4 | tests/e2e | 15 | 45-56 | 0/4/6 |
| 5 | tests/schema | 14 | 57-68 | 0/5/7 |
| 6 | tests/unit (A-G) | 26 | 69-82 | 0/3/5 |
| 7 | tests/unit (H-Z) | 26 | 83-96 | 0/3/5 |

### Per-part reviewer summaries

#### Part 1

Reviewed the foundation slice of phase 38: the four `app/` modules, `config.py`,
`errors.py`, `logs.py`, `resilience.py`, the Helm chart, the single migration,
`config/config.yaml`, `Dockerfile`, `docker-compose.yml`, `.env.example`,
`.gitignore`, `pyproject.toml`, `AGENTS.md` and `uv.lock`.

No critical finding. The error registry, the identity barrier dependency, the
DSN construction and the store-verifier builders all hold up under trace: the
duplicate-`Authorization` count reads the raw ASGI scope before any merged view,
`class_answering_status` has no status collision across the nine marked classes,
`URL.create` closes the DSN re-partition hole, and the `SignedDataVerifier`
guard correctly stops the library's `ValueError` on a production build with no
`app_apple_id`. I verified the pydantic-settings nesting by reading
`explode_env_vars`: `env_nested_max_split=1` strips the field prefix *before*
splitting, so `APP_STORE_BUNDLE_ID` and `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL`
do map onto the nested fields, and `config.yaml` outranks env per leaf key
exactly as its own comment claims.

The five warnings are: a boot-time configuration check whose condition does not
cover the value its own message names; an unbounded provider-permit wait that
now sits after the committed quota charge; uvicorn's own access log left
enabled beside the structured one; a Helm `required` that contradicts the
documented degraded path; and the comment register that `AGENTS.md` itself
outlawed in this phase.

**Findings dropped for a ratified decision (rule 1):**

- The migration's removal of `core.access_grants_anti_abuse`,
  `core.provider_accounts`, `core.provider_account_gate_consumptions` and
  `core.gate_consumption_kind` contradicts `specs/auth-refactor-phases/00-schema.md`
  (:397, :457, :465, :646). Ratified by **42-01-PLAN.md:131-136** and
  **42-04-PLAN.md:97-99**. Dropped.
- The shrink of `core.auth_operation` from seven labels to four and the removal
  of the `core.auth_challenges` operation-membership CHECK contradict
  `00-schema.md:111-113` and `:597`. Ratified by **40-01-PLAN.md:31,51**.
  Dropped.
- The absence of the Python `limits` library from `pyproject.toml` and of any
  `rate_limits` block in `config/config.yaml` contradicts
  `SHARED-INVARIANTS.md` § Rate limits and `oft-conventions.md`'s
  `req~ratelimit-config-shape-and-defaults~1`. Ratified by **Phase 35 D-05**
  (backend rate limiting deleted from the product) and **D-08** (the Envoy
  contract deferred to v2.1), recorded at `.planning/ROADMAP.md:217` and
  restated in `AGENTS.md:95-97`. Dropped.

**Finding dropped as spec-mandated (rule 2):** `core.external_identities`
carries three indexes over `user_id` — the auto-index behind `UNIQUE (user_id)`
(:100), `ix_external_identities_user_id` (:110) and
`ix_external_identities_user_active` (:112) — of which two are pure duplicates
given the uniqueness cap. `00-schema.md:647` enumerates the index set, so
removing them would violate the binding spec. Not filed.

---

#### Part 2

Reviewed the seven `api/auth/` integration modules (Firebase Admin, JWT verification, App Store
notifications, Google Play RTDN + subscriptions read, DeviceCheck, the two store value types, the
providerData adapter seam), the four `api/schemas/` modules, and the five `api/tables/` modules, at
standard depth with cross-file tracing into `crud/`, `services/`, `app/dependencies.py` and the two
vendor SDKs actually installed in `.venv`.

The store-verification paths hold up under adversarial reading. I traced every raise in
`app_store.py` and `google_play.py` through to its client-visible status and to the store's own
retry behaviour, checked the Apple SDK source to confirm that `bundleId`, `appAppleId` and
`environment` really are enforced inside `verify_and_decode_signed_transaction` /
`verify_and_decode_notification` (they are, so `verify_transaction` is not accepting another app's
proof), confirmed that `data.status` is `Optional[Status]` so an out-of-enum `rawStatus` reaches
`UnknownStoreSubscriptionStatus` rather than a silent `expired`, and confirmed the
`VerifiedNotification` invariant "`tier_id` is absent exactly when `product_id` is" holds on all
four Apple arms and both Play arms. `_names_one_path_segment` plus `quote(..., safe="")` does close
the path-traversal hole on the Play read: I checked that the only remaining `..`-shaped input is
refused and that a percent-encoded slash is not a dot segment httpx would remove. The negative
`kid` cache in `jwt_verifier.py` is sound because `PyJWKClient.get_signing_key` already refetches
before declaring a miss, so nothing is cached that a fresh JWKS would have resolved. I verified
empirically that `LinkedIdentity`'s re-declared `user`/`identity` really do lose the base class's
`None` defaults under `slots=True` (they do — the "present by construction" claim is true), that
`DECODE_OPTIONS` is not mutated by this PyJWT version, and that every mapped-row construction in
`crud/` supplies the timestamps the tables declare.

No Critical findings. Two Warnings: a JWT rejection-reason mislabel that feeds the forgery spike
alert, and a dormant second clock source on the grant tables that contradicts the ratified
single-evaluation-time rule and a provably false comment beside it.

**Findings dropped as already ratified:**

- `PubSubPushRequest.subscription` is declared and read by nothing in `src/` or `tests/`, which is
  the same defect `PubSubPushMessage`'s own comment says was fixed by deleting `messageId`. Dropped:
  `.planning/phases/44-post-webhooks-google-play-rtdn/44-01-PLAN.md:275` specifies "an optional
  `subscription: str | None`".
- An unmapped store product raising a 500 (`UnmappedStoreProduct`) so the store retries for days,
  rather than acknowledging. Dropped: `src/nativespeaker/api/errors.py:277` states the intent — "an
  operator edits the map and the store's next retry succeeds; nothing is written meanwhile".
- `developer_notification_from` answering 200 for an unusable body instead of 422. Dropped: 44 D-04,
  recorded at `.planning/phases/37.5-machine-generated-code-refactoring-part-4/37.5-REVIEW-FIX.md:695-707`.
  Only the log level and label survive, as IN-20.
- `AuthChallenge.challenge_id` storing a secret capability handle in plaintext. Dropped: the column
  is `TEXT NOT NULL UNIQUE` in `migrations/20260818_01_initial-release.sql:296`, which is bound by
  `req~schema-ddl-as-written~1`; hashing it would require a spec amendment, and the threat model in
  `AGENTS.md` does not justify one.

IN-17 was previously reported as `37.2-REVIEW.md` IN-21 and is re-filed rather than dropped: the
37.2 fix pass ran without `--all`, so all 33 Info findings were out of scope
(`37.2-REVIEW-FIX.md:20`). It was never ratified, only unaddressed.

#### Part 3

Reviewed the 21 files of the core business-logic group at standard depth, with the adversarial
focus the assignment named: the read-only guarantee of `POST /auth/sync`, the single captured
instant, inclusive/exclusive grant bounds, transaction and lock ordering in `crud/`, and
error-contract leakage in `routers/`.

The phase's own endpoint holds up. `SyncService.read_entitlement` issues three plain SELECTs, takes
no lock, assigns to no mapped attribute and calls neither `commit()` nor `rollback()`; the ordered
`usage.monthly_period < period` comparison computes the rollover as a value instead of writing it.
`get_evaluated_at` is a solver-cached dependency, so every clock-dependent value on a request —
`monthly_period_for`, the effective-grant predicate, the grant writes — comes from one instant, and
no file in this group reads the clock itself (`grep` for `datetime.now|utcnow|date.today` over all
21 files returns nothing). The effective predicate lives once, in `_effective_grants_statement`,
with `starts_at <= t` and `ends_at > t`; every writer that closes a term sets `ends_at =
evaluated_at`, so the two bounds meet without a gap or an overlap. `ruff` and `ty` both pass clean.
The lock order also holds: every writer takes the `status='active'` grant set first, ascending by
id, then usage rows in the same order, and no provider call runs inside an open transaction —
`_claim_anonymous_grant` and `_claim_registered_grant` both `rollback()` the preflight read before
the DeviceCheck round trip and `commit()` before the bit write. Error bodies carry only `code`; the
`user_id`/`grant_id`/`tier_id` values the integrity classes hold reach the log and never the wire.

What is wrong is one fail-closed hole and a set of consistency defects. `write_subscription_grant`
is the single place in the codebase that reads a missing `core.user_monthly_usage` row as "zero
used" instead of refusing, and it mints the replacement counter from that reading — that is CR-29.
Beyond it: a dead session handle on the one service whose contract is that it writes nothing, a
second derivation of the UTC month boundary that does not normalize its input the way the first one
does, and the repository's own comment rule broken at scale in these files by the most recent
commits on the branch.

**Ratified decisions checked and findings dropped:** three.

- Sync raising `MissingUsageRowError` / `UnknownTierError` rather than reporting `monthly_used = 0`
  is a deliberate divergence from the verbatim brief, ratified as **38 D-07**. Not filed.
- No durable `audit.auth_events` row and no success event for `/auth/sync` is **38 D-01/D-02/D-03**
  (SYNC-03, amended 2026-09-01). Not filed.
- `routers/auth.py`'s router-level dependency being the unnarrowed `Depends(get_identity)` rather
  than `get_linked_identity` is **38 D-06 (Claude's Discretion, "Where the route lives")**, and
  `tests/unit/test_app_wiring.py::test_every_route_but_the_two_exemptions_requires_a_linked_identity`
  is the enumeration assertion that catches a later route added without its own narrowing. Not filed.

---

#### Part 4

Reviewed the fifteen `tests/e2e/` modules assigned to part 4 at standard depth, against
`SHARED-INVARIANTS.md`, `oft-conventions.md`, Phase 38's `38-CONTEXT.md` decision block, and the
ratified findings carried by the 37.2/37.3/37.5 review-and-fix passes. The suite is unusually
disciplined for generated tests: nearly every "nothing was written" case is paired with a control
that fails on a dead seam, rejection bodies are compared as raw bytes so no arm can become an
oracle, and log hygiene is asserted over `repr()` rather than over string fields only. `uv run ruff
check tests/e2e/` passes clean.

The four warnings are all test-validity defects, not style. Two of them are the same failure class
this project has already paid for twice: a *control* that appears to prove completeness but can pass
while the thing it guards is untested (WR-45, WR-47). One is a set of tautological assertions that
query keys no code path could ever have written — the exact pattern `37.3-REVIEW.md` WR-83 named
(WR-48). One is a seeded distinguishing value that is then discarded, leaving the phase's own route
with no wire-level proof that `monthly_used` is not hard-coded (WR-46).

**Findings dropped under Rule 1 (ratified overrides):**

- `test_challenge_store.py:96-104` — the `_contended_challenge` teardown deletes *every* committed
  `core.auth_challenges` row carrying this module's `preauth_issuer`, not just the handle it wrote,
  which would let two concurrent sessions against one database sweep each other's live rows. Settled
  by the ratified **37.2 WR-85** fix ("own the rows the challenge-store module counts and sweeps"),
  cited in `.planning/phases/37.3-machine-generated-code-refactoring-part-2/37.3-REVIEW.md:1533-1536`.
  `pyproject.toml` `addopts` carries no `-n`, so the sweep is serially safe as shipped. Dropped.
- `test_sync.py:301-311` — `/auth/sync` answering an opaque 500 for an effective grant whose usage
  row is missing, rather than the brief's literal `monthly_used: 0`. Ratified by Phase 38 **D-07**
  (`38-CONTEXT.md`), a deliberate divergence. Dropped.
- `test_sync.py` asserting no per-attempt success telemetry — ratified by Phase 38 **D-02**
  ("Do not add an `auth_sync_succeeded` event"). Dropped.

#### Part 5

Reviewed the 14 `tests/schema/` files assigned to part 5 at standard depth, against the shipped
migration `migrations/20260818_01_initial-release.sql`, `SHARED-INVARIANTS.md`, `00-schema.md` and
the production crud/service code the race cases drive (`crud/grants.py`, `services/sync.py`,
`services/subscriptions.py`, `crud/identities.py`).

The suite is unusually strong for a race suite: nearly every contention case carries an explicit
"control"/"premise" assertion that would fail if the case degenerated into two sequential
transactions, the barriers are bounded so a partner that dies surfaces as a failure rather than a
hang, and the cleanup helpers are child-first against the real FK graph. I traced each named
invariant to the statement that would actually violate it and found no case that is structurally
unable to fail — with one exception (WR-60).

**No BLOCKERs.** Five WARNINGs: one wall-clock flake vector that skips the repo's own `timing`
marker convention, one mirror-to-production pinning claim that the pinning test does not make, one
lock-order assertion that is weaker on the registered writer than on the anonymous twin that
justifies it, one half-vacuous pairing scan, and one contention case with no control on its premise.
Seven INFO items.

**Findings dropped under mandatory rule 1 (ratified overrides):**

- The shipped schema drops `audit.auth_events`, `core.access_grants_anti_abuse`,
  `core.provider_accounts`, `core.provider_account_gate_consumptions` and `core.auth_event_result`,
  and stores `core.auth_challenges.preauth_subject` in plaintext rather than as
  `preauth_subject_hash BYTEA` — all contrary to `00-schema.md` §3/§6/§7 and ruling 9.4. The tests
  (`test_inventory.py:108-116`, `test_constraints.py:68-73`, `test_create_race.py:292-300`) encode
  that shipped shape. **Dropped:** `.planning/REQUIREMENTS.md:32` records the Phase 38 amendment
  (D-01/D-03/D-04) that struck § "Audit" from `SHARED-INVARIANTS.md` in full and removed the
  `core.auth_event_result` obligation at its source.
- `core.auth_operation` carries four labels, not the seven `00-schema.md` §3 enumerates, so
  `test_constraints.py:534-545` asserts `InvalidTextRepresentationError` where the spec expects a
  CHECK rejection. **Dropped** for the same amendment: `restore_subscription`, `sign_out_all` and
  `sync` are challenge-free by ruling 9.8 and carry no audit obligation after D-03.
- `test_apply_rollback.py:23-25` asserts exactly one migration file where `00-schema.md` §1 mandates
  six, and `test_apply_rollback.py:68-88` pins three seeded `core.access_tiers` rows where
  `00-schema.md`:249 says Phase 00 seeds none. **Dropped:** the test's own docstring at :69 cites the
  override, and `test_inventory.py:302` cites D-09 for the sibling trigger rule.

#### Part 6

Reviewed the 26 unit-test files in my slice (~9,180 lines) at standard depth: `conftest.py`,
`error_tree.py`, and 24 `test_*.py` modules covering the adapter seam, app wiring, the challenge
and create-user completion paths, both grant claims, config loading, the error registry and
handlers, the Firebase/DeviceCheck/App Store/Google Play adapters, and the grant-source walks.
All 714 collected cases pass (`.venv/bin/python -m pytest ... -q` → `714 passed in 11.71s`), so
nothing here is a broken build.

The suite is unusually disciplined — nearly every case ships a named control, the fakes import
production constants rather than restating them (`conftest._FixedKeyVerifier` takes
`DECODE_ALGORITHMS`/`DECODE_OPTIONS`/`DEFAULT_LEEWAY` from `jwt_verifier.py`), and
`conftest.FakeChallengeStore.claim`/`consume` mirror `ChallengesDB`'s conditional updates clause for
clause (verified against `crud/challenges.py:64-88`). I found **no critical defect**: I traced every
production behaviour the suite pins and each one is correct — the Apple five-status map is total and
injective, Google's `ON_HOLD → billing_retry` is correctly outside
`ENTITLED_STATUSES = {active, grace_period}` (`crud/subscriptions.py:28`), `_family(AppError)` is the
same 62 classes with or without `app.main` imported (so the subprocess totality checks see the whole
tree), and `_order`'s `index("commit")` is unambiguous because each claim method calls `commit`
exactly once.

What I did find is three places where a case measures less than its own prose claims, plus five
smaller robustness items. The sharpest is WR-69: both claim suites assert the DeviceCheck bit is
"carried forward from the query, never fabricated", but every path that reaches the write is scripted
with `BitState(bit0=False, bit1=False)`, so the carried bit is always `False` and the assertion cannot
tell a real carry-forward from a hardcoded constant.

**Ratified decisions I dropped rather than filed (3):**

1. `/auth/challenge` admitting a pre-auth caller, which reads against SHARED-INVARIANTS line 14
   ("Only `POST /auth/create-user` is pre-auth-callable"). Settled by **D-10**
   (`.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md:129`), which explicitly names
   `test_app_wiring.py::PREAUTH_CALLABLE_PATHS` as the pin for this fact. Dropped.
2. `AppStoreConfig` silently degrading a malformed `APP_STORE_ENVIRONMENT` to `None` — so
   `APP_STORE_ENVIRONMENT=Production` (capital P) 503s the Apple webhook forever with no boot
   failure. Settled by **CR-04 / D-02 / P-04**, cited at `test_config.py:447` and `:527-528`
   ("an operator error costs one route its 503, never the pod its boot"). Dropped.
3. `CompletionRequest.challenge_id` carrying `min_length=1` but no `max_length`, beside
   `ChallengeRequest.operation`'s `max_length=64`. Settled by **WR-01**
   (`test_challenge_endpoint.py:267`): the bound exists only because the refusal log carries the
   operation verbatim, and `test_create_user_precedence.py:281-289` asserts the handle reaches no
   log at all. Dropped.

#### Part 7

Twenty-six unit test files, read in full and executed. All 574 assigned tests pass, the
whole `tests/unit` directory passes (1620 tests), and re-running the assigned files in a
different order produced no cross-file state leak. `asyncio_mode = "auto"` is set in
`pyproject.toml:62`, so the bare `async def` tests in `test_sync_resolver.py`,
`test_purchases_crud.py` and the rest are genuinely awaited and none passes vacuously.

The findings are not style. Three of them were proved by mutation: I copied `src/` to a
scratch directory, changed one line, and ran the guarding tests over the copy with
`PYTHONPATH` (verified live by printing `module.__file__`). No source file in the repository
was modified.

The substantive result is that the stub sessions in this phase's own suite dispatch on the
*entity class* of the statement and ignore the statement itself. Because of that, no
assertion anywhere in `test_sync_resolver.py` observes which `user_id`, which `grant_id`,
which `tier_id` or which instant the resolver actually passed down. The same pattern in
`test_purchases_crud.py` / `test_users_me.py` lets the tenant-scoping predicate be removed
from `PurchasesDB.read_tokens` — the read behind `GET /users/me` — with 33 out of 33 tests
still green. The production code is correct today; what is missing is the guard.

The three sync files named in the brief were scrutinised hardest.
`test_sync_resolver.py`'s period-comparison guard is real: mutating `<` to `!=` or to `>`
fails `TestTheRolloverIsComputedNeverWritten::test_a_period_ahead_of_this_request_reports_the_stored_count`
in both directions. `test_sync_error_reuse.py` is narrow but honest about its narrowing.
`test_sync_clock_capture.py` proves the structural half of
`req~sessions-sync-single-evaluation-time~2` (one clock call in `dependencies.py`, none in
`sync.py`) but not that the captured instant is the one the grant predicate receives.

**Findings dropped as already ratified (mandatory rule 1):**

- `test_identity_accessors.py:388` `test_a_padded_credential_value_is_accepted_which_loosens_the_wire_contract`
  asserts that `Bearer   <token>  ` authenticates, which reads against
  `SHARED-INVARIANTS.md:18-19` and `03-sync.md:61`. Dropped: **A-09** ratified this as the
  fifth recorded, unresolved conflict against the binding spec
  (`.planning/phases/37.4-machine-generated-code-refactoring-part-3/37.4-07-PLAN.md:213`,
  kept verbatim by 37.5-08).
- `test_identity_accessors.py:406` `test_trailing_content_after_the_token_degrades_to_a_verification_failure`
  records a divergence from `03-sync.md:61`'s "trailing content ... reject as
  `invalid_external_jwt`". Dropped: same ratified conflict set (**D-10**).
- `test_restore_proof.py:768` `test_a_violation_at_commit_is_the_lost_race_the_flushes_report`
  uses sqlstate `23503` for a claim about deferred keys. Not a finding after checking
  `migrations/20260818_01_initial-release.sql:241-247`: both `DEFERRABLE INITIALLY DEFERRED`
  constraints really are FOREIGN KEYs, so `23503` is the correct exemplar.

None.


## Narrative Findings (AI reviewer)

## Critical Issues

### CR-29: `write_subscription_grant` reads a missing usage row as "zero used" and mints a fresh allowance

**File:** `src/nativespeaker/api/crud/subscriptions.py:382-390`

**Issue:** When a subscription grant supersedes the grants the buyer holds, the replacement usage
counter is seeded from the superseded row:

```python
carried = 0
for grant in superseded:
    if grant.user_id != user_id:
        continue
    usage = await self.grants_db.read_usage(grant.id)
    if usage is not None and usage.monthly_period == period:
        carried = usage.monthly_used
```

`read_usage` returning `None` — an existing grant with no `core.user_monthly_usage` row — falls
through silently and leaves `carried = 0`, and line 402 then inserts a brand-new counter at that
value. The account is handed a full monthly allowance it did not buy, and the broken invariant that
produced the missing row is erased rather than surfaced.

This is the exact case `SHARED-INVARIANTS.md` § "Grants and evaluation time" names: *"A missing
usage row for an existing grant fails closed — never lazily minted."* Every sibling path in this
codebase obeys it and this one does not:

- `crud/grants.py:274-278` — `activate_registered_account_grant`, the other supersession-with-carry
  writer, raises `MissingUsageRowError(superseded.id)` for the identical condition, with the comment
  *"reading it as a fresh allowance hands the account free credits"*.
- `services/quota.py:68-71` — `charge` raises `MissingUsageRowError`.
- `services/sync.py:44-47` — `read_entitlement` raises `MissingUsageRowError` (38 D-07).

The condition is reachable on every renewal, mid-term tier change and restore, because
`lock_grants_of` (`crud/subscriptions.py:89-92`) calls `lock_usage` on each grant and discards a
`None` result without checking it either — so nothing between the lock and this read notices.

Note that the `usage.monthly_period == period` half of the condition is correct and must stay: a
row naming an earlier month legitimately carries zero. Only the `None` arm is the defect, and it
has to be split out from the stale-period arm.

**Fix:**

```python
carried = 0
for grant in superseded:
    if grant.user_id != user_id:
        continue
    usage = await self.grants_db.read_usage(grant.id)
    if usage is None:
        # Fail closed, never mint: a grant with no usage row is a failed write, not a fresh allowance.
        raise MissingUsageRowError(grant.id)
    if usage.monthly_period == period:
        carried = usage.monthly_used
```

with `MissingUsageRowError` added to the `nativespeaker.api.errors` import already at
`crud/subscriptions.py:13`. AGENTS.md exception 4 ("a fail-closed read may raise its own rejection,
so the rejection stays with the query in `crud/`") puts the raise here rather than in the service.

---

## Warnings

### WR-01: the Google Play boot check never looks at `package_name`, so a partly-configured deployment refuses every genuine RTDN with no warning

**File:** `src/nativespeaker/api/app/lifespan.py:169-176` (with
`src/nativespeaker/api/app/lifespan.py:77-79` and
`src/nativespeaker/api/app/dependencies.py:220-222`)

**Issue:** The warning condition is

```python
google_push_verifier = build_google_push_verifier(config.google_play)
play_credential = _play_credential()
if google_push_verifier is None or play_credential is None:
    logger.warning("google_play_configuration_absent",
                   consequence="... until the Play package name, push audience, push service "
                               "account and Application Default Credentials are available ...")
```

`build_google_push_verifier` (`:79`) tests only `push_audience` and
`push_service_account_email`. `_play_credential()` tests only ADC. Nothing on
this path reads `config.google_play.package_name`, yet the message names it
first.

So a deployment that sets `GOOGLE_PLAY_PUSH_AUDIENCE` and
`GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL` and has ADC, but omits
`GOOGLE_PLAY_PACKAGE_NAME`, boots **silently**: no
`google_play_configuration_absent` line is written. Every genuine Pub/Sub
delivery then verifies its token, reaches
`dependencies.py:220`

```python
if notification.packageName != request.app.state.config.google_play.package_name:
    raise NotificationRejected(stage="package_name_mismatch")
```

with the right side `None`, and is refused 401 — forever. That is precisely the
invisible-failure mode `.env.example:140-147` warns about for a mistyped
audience, except here there is not even the boot warning to contradict.
`PlayDeveloperSubscriptions` is also handed `products=config.google_play.products`
(`lifespan.py:183`) with no check that the map is non-empty; an empty map turns
every verified product id into `UnmappedStoreProduct` (500) with no boot signal
either.

**Fix:** make the condition cover every value the message names, and add the
product map:

```python
play = config.google_play
if (google_push_verifier is None or play_credential is None
        or not play.package_name or not play.products):
    logger.warning("google_play_configuration_absent", consequence=...)
```

### WR-02: the provider permit is acquired with no timeout, after the caller's quota credit has already been committed

**File:** `src/nativespeaker/api/resilience.py:102-106,193-205` (call site
`src/nativespeaker/api/services/chats.py:100-102,128-130`)

**Issue:** This phase moved the semaphore out of `admission()` and into
`ainvoke`:

```python
async with self._gate.concurrency():   # resilience.py:193 -- unbounded wait
    retrying = AsyncRetrying(...)
    return await retrying(attempt)
```

`concurrency()` is a bare `async with self._semaphore` (`:105`) with no
timeout. `ChatService` enters `admission()`, calls
`quota_service.charge(...)` — which **commits a spent monthly credit in its own
session** — and only then calls `ainvoke`. So the credit is durable before the
permit wait begins.

`queue_size` bounds *how many* callers wait; nothing bounds *how long*. With the
shipped `config/config.yaml` values (`pool_size: 5`, `queue_size: 25`,
`timeout_seconds: 30`, `retry_max_attempts: 3`) the last admitted caller waits
behind 25 predecessors at ~91.5s each over 5 permits — roughly eight minutes,
with the credit already spent and the client long gone. Before this phase the
same wait existed but sat in `admission()`, i.e. *before* the charge, so a
client that gave up lost nothing.

I am filing this against the decision recorded in `AGENTS.md:92-93` ("the
provider permit is taken around the retry loop, so no gate hold spans a database
round trip") because that decision settles *where* the permit is taken, not
whether the wait is bounded; the two are independent and the fix below keeps the
ratified ordering intact.

**Fix:** bound the permit wait with the value the gate already carries, and shed
with the class the gate already owns:

```python
@asynccontextmanager
async def concurrency(self):
    """Hold one provider permit, or refuse once the wait budget is spent."""
    try:
        await asyncio.wait_for(self._semaphore.acquire(),
                               timeout=self._permit_wait_seconds)
    except TimeoutError as exc:
        raise QueueFullError(self._retry_after_seconds) from exc
    try:
        yield
    finally:
        self._semaphore.release()
```

with `permit_wait_seconds` added to `ResilienceConfig` and `config/config.yaml`
beside `queue_retry_after_seconds`.

### WR-03: uvicorn's own access log is left on, so every request emits a second unstructured line and the probe exclusion does not hold

**File:** `Dockerfile:40`, with `src/nativespeaker/api/logs.py:12,62-68,93-96`

**Issue:** `logs.py` builds one structured access line per request and
deliberately suppresses the probe:

```python
_EXCLUDED_PATHS = frozenset({"/health/ready"})
...
root.handlers.clear()
root.addHandler(console_handler)
```

Clearing the **root** handlers does not touch uvicorn's access logger. Uvicorn's
`LOGGING_CONFIG` (verified in
`.venv/.../uvicorn/config.py:89-99`) gives `uvicorn.access` its own stdout
handler with `"propagate": False`, and `access_log` defaults to `True`
(`config.py:198`). `configure_logging()` runs at server start, before the app is
imported and long before the lifespan calls `setup_logging`, so nothing here
disables it.

Consequences, all of them real in the shipped image:

- every request produces two access lines, one structured and one in uvicorn's
  plain `'%s - "%s %s HTTP/%s" %d'` format that no field extractor can read;
- `_EXCLUDED_PATHS` is defeated — readiness every 10s and liveness every 30s
  (`k8s/values.yaml:38,42`) are logged by uvicorn regardless;
- `uvicorn.error` startup/shutdown lines go to stderr in uvicorn's own format,
  interleaved with the structured ones.

**Fix:** turn off the duplicate at the one place that starts the server:

```dockerfile
CMD ["uvicorn", "nativespeaker.api.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
```

### WR-04: the DeviceCheck Secret is `required` in the template, contradicting the degraded path `values.yaml` documents

**File:** `k8s/templates/deployment.yaml:106-113` and `:91-94`, against
`k8s/values.yaml:55-59`

**Issue:** `values.yaml:55-59` documents the DeviceCheck Secret as a thing whose
absence degrades:

```
# ... Without it both free-grant claims
# fail closed as 503 for the life of the deployment.
deviceCheckSecretName: ""
```

The template makes that state unreachable:

```yaml
secretName: {{ required "credentials.deviceCheckSecretName must name a Secret holding the Apple DeviceCheck .p8" .Values.credentials.deviceCheckSecretName }}
```

`helm install` fails at render with the shipped default. So the documented
degraded mode — which `lifespan.py:146-151` implements, and which
`.env.example:84-85` also describes ("Everything except the claim runs without
them") — cannot be reached through this chart at all. The inconsistency is
visible one file over: the ADC Secret, whose absence degrades identically, is
guarded with `{{- if }}` on both the mount (`:95-99`) and the volume
(`:114-122`), while the DeviceCheck mount (`:91-94`) and volume are
unconditional.

**Fix:** guard the DeviceCheck mount, volume and `DEVICECHECK_PRIVATE_KEY_PATH`
the way the ADC ones are guarded, and drop the `required`:

```yaml
{{- if .Values.credentials.deviceCheckSecretName }}
- name: DEVICECHECK_PRIVATE_KEY_PATH
  value: /etc/ns/devicecheck/{{ .Values.credentials.deviceCheckKey }}
{{- end }}
```

…or, if the intent really is to make the key mandatory, delete the "without it"
paragraph from `values.yaml:55-59` so the two stop disagreeing.

### WR-05: the comment register `AGENTS.md` outlawed in this phase is still in force across the files this phase touched

**File:** `AGENTS.md:17-22` against `src/nativespeaker/api/app/lifespan.py:60-64,100-106,114-118,200-202,215-217`,
`src/nativespeaker/api/config.py:9-13,138-141,158-161,179-183`,
`src/nativespeaker/api/app/dependencies.py:71-79,85-88,100-102,136-138`,
`src/nativespeaker/api/logs.py:14-19,52-55,97-99`,
`config/config.yaml:22-37`, `k8s/templates/deployment.yaml:19-21,24-26,30-32,40-42,46-48,71-73`

**Issue:** `AGENTS.md` was amended in this phase to say, of comments:

> **One line each.** A comment explains the specific line or lines below it. It
> never explains the design, the request lifecycle, a rule enforced in another
> module, or a decision that was made elsewhere.

and "These rules bind all code in this repository." Every file listed above
still carries multi-paragraph comments that do exactly what the rule forbids.
`config.py:138-141` explains what pydantic would report if the field were
declared differently. `dependencies.py:71-79` is a nine-line essay on
`HTTPBearer`'s four return shapes and RFC 6750. `logs.py:14-19` explains the
retention policy of the log store. `deployment.yaml:71-73` restates a rule
enforced in `config.py`. `config/config.yaml:22-37` is sixteen lines of
pydantic-settings precedence theory in a values file.

This is not a style preference: it is the convention the project ratified in
this same phase, and leaving the register in place makes the amendment
inoperative on the files it was written for.

**Fix:** cut each block to the one line that resolves the ambiguity at the line
below it, and move the reasoning to the phase record. For example
`dependencies.py:71-79` becomes:

```python
# `HTTPBearer` also answers `None` for a non-Bearer scheme and an empty token, which spec 01 §1.1
# calls `malformed`; only zero field values are `missing_token`.
presented = request.headers.get("authorization") is not None
```

---

### WR-15: a JWT missing `aud`, `iss`, `exp` or `iat` is labelled `bad_signature`, the forgery label

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:82-99`

**Issue:** `bounded_reason_for` special-cases `MissingRequiredClaimError` only for `sub`
(line 91-92). Every other required claim falls past the `DecodeError` arm — `MissingRequiredClaimError`
subclasses `InvalidTokenError`, not `DecodeError` — and lands on the line-99 catch-all,
`BoundedReason.bad_signature`. Verified directly:

```
$ .venv/bin/python -c "...bounded_reason_for(MissingRequiredClaimError(c))..."
aud bad_signature
iss bad_signature
exp bad_signature
iat bad_signature
sub empty_subject
```

PyJWT runs `_validate_required_claims` **before** the issuer and audience checks
(`.venv/.../jwt/api_jwt.py:394` vs `:407`, `:410`), so a token that simply omits `aud` never reaches
`InvalidAudienceError` and can never be labelled `audience_mismatch`. This contradicts the closed
set's own stated purpose eight lines above it (`:29-31`): "the first three separate the three
populations the `invalid_external_jwt` spike alert is labelled by — clients that send nothing,
clients that send garbage, and an actor forging signatures". A signature-valid token that is merely
missing a claim is a client bug or a foreign issuer, not a forgery, and it currently inflates
exactly the counter that is supposed to detect one. The comment at `:98` ("Everything else:
signature failure, algorithm confusion, unknown key id") does not name this case, so it is an
unhandled fall-through rather than a considered mapping.

**Fix:** map each missing claim onto the label that already exists for its present-but-wrong twin,
before the `DecodeError` arm:

```python
_MISSING_CLAIM_REASONS = {
    "sub": BoundedReason.empty_subject,
    "iss": BoundedReason.issuer_mismatch,
    "aud": BoundedReason.audience_mismatch,
    "exp": BoundedReason.expired,
    "iat": BoundedReason.expired,
}

# A claim `require` demands and the token omits: the same failure as one present and wrong,
# reached one check earlier, so it carries the same label rather than the forgery one.
if isinstance(exc, MissingRequiredClaimError):
    return _MISSING_CLAIM_REASONS.get(exc.claim, BoundedReason.malformed)
```

`tests/unit/test_jwt_security.py:172-183` and `:316-321` both assert `bad_signature` for a token
without `exp` and must be updated to `expired`; neither docstring claims the label itself is the
property under test ("dropping a claim from it must fail here").

### WR-16: the grant tables carry a dormant second clock, under a comment that says they do not

**File:** `src/nativespeaker/api/tables/grants.py:52-53`, `:70`, `:72-73`, `:86-88`

**Issue:** Seven columns across `AccessTier`, `AccessGrant` and `UserMonthlyUsage` default to
`default_factory=lambda: datetime.now(UTC)` — including `AccessGrant.starts_at` (`:70`), which is
half of the shared effective-grant predicate. `SHARED-INVARIANTS.md:44` requires every
time-dependent value to come from ONE captured evaluation time per request, and
`google_play.py:238-241` spells out the exact failure these factories re-open: "a clock called from
inside this class would give `_status_for` a different instant from the one the grant writer
computes `ends_at` against, and a term crossing between the two commits an active grant outside its
own term."

The factories are dormant today — I checked all four creators, and every one passes explicit values
(`crud/grants.py:189-200`, `:292-306`; `crud/subscriptions.py:392-403`). That makes the comment at
`:86` factually false: "NOT NULL with no database DEFAULT: **these factories are the only source of
a value**" — they are the source of no value that is ever written. And it makes the defaults a
silent trap: a fifth creator that forgets `starts_at` gets a plausible-looking grant whose start
instant differs from the one its own `ends_at` and `monthly_period` were derived from, with no
error and no `NOT NULL` violation to catch it. `AccessTier`'s two are pure dead weight — the
docstring on `:44` says the rows are "seeded reference data ... written by the migration", and no
code constructs one.

The sibling module already states the correct policy and follows it: `tables/purchases.py` declares
`created_at`/`updated_at` with no factory on all four tables, and `37-04-SUMMARY.md:208` records the
reason as ratified — "the creating transaction owns both the clock (35 D-02's single
`evaluated_at`) and the RNG". `tables/auth.py:42-45` follows the same policy. `tables/grants.py`
is the outlier.

**Fix:** drop the seven wall-clock factories so a forgotten timestamp is a loud `NOT NULL` violation
instead of a second clock reading, matching `tables/purchases.py`:

```python
    # No default: the creating transaction owns the clock (35 D-02's single `evaluated_at`),
    # so a forgotten value is a NOT NULL violation and never a second reading.
    starts_at: datetime = Field(sa_type=DateTimeType)
    created_at: datetime = Field(sa_type=DateTimeType)
    updated_at: datetime = Field(sa_type=DateTimeType)
```

and delete the false claim on `:86`. `AccessGrant.id`'s `default_factory=uuid7` stays — that is the
RNG, not the clock, and `crud` reads `activated.id` before flush. Note that `tables/identities.py`
and `tables/users.py` carry the same four factories; they belong to another reviewer's scope, but
the fix should land as one change so the package states one policy.

### WR-30: `SyncService` holds a live handle to the committing session and never uses it

**File:** `src/nativespeaker/api/services/sync.py:20`

**Issue:** `self.session = db` is assigned in `__init__` and never read. `read_entitlement` reaches
the database only through `self.grants_db`, and `self.evaluated_at` is the only other field the
method touches. `ruff`'s configured rule set (`E,W,F,I,UP` — no `B`, no `ARG`) does not catch a dead
instance attribute, so nothing flags it.

It is more than dead code on this particular class. `get_db` commits on teardown
(`app/dependencies.py:44-51`), so the field is a live, writable handle to a session that *will*
commit, sitting on the one service whose entire contract (SYNC-02, spec § 7 "Strictly read-only")
is that it writes nothing. The read-only property is currently argued only by tests and by a source
`grep` in plan 38-02's acceptance criteria; removing the field makes it structural — a future edit
to this class would have no session to write through.

**Fix:** delete the assignment and take only what the service uses.

```python
def __init__(self, db: AsyncSession, evaluated_at: datetime) -> None:
    self.grants_db = GrantsDB(db)
    # One instant for this request; nothing below it reads the clock again.
    self.evaluated_at = evaluated_at
```

### WR-31: `seconds_until_rollover` derives the UTC month boundary without normalizing its input

**File:** `src/nativespeaker/api/services/quota.py:24-32`

**Issue:** Two functions derive the same UTC calendar-month boundary from `evaluated_at`, and only
one of them defends the derivation:

- `tables/grants.py:31-36` — `monthly_period_for` calls `.astimezone(UTC)` first, with the comment
  *"a non-UTC instant would name the wrong month and split one allowance across two period strings"*.
- `services/quota.py:28-30` — `seconds_until_rollover` calls `evaluated_at.replace(...)` directly,
  which reads the stored wall clock of whatever `tzinfo` it was handed.

Handed an instant in any non-UTC zone, the two disagree: `monthly_period_for` names the UTC month
that governs the counter, while `Retry-After` names the boundary of a different month — up to ~26
hours away, and on the wrong side of the real rollover for a zone ahead of UTC, so the client is
told to retry before its allowance actually resets. Both values are computed from the same argument
in the same call (`charge`, lines 45 and 73), so they are supposed to describe one boundary.

The defect is currently latent, not live: the only production source is `get_evaluated_at`
(`app/dependencies.py:119-121`), which returns `datetime.now(UTC)`. But `seconds_until_rollover` is
a module-level function with no such precondition stated or enforced, its sibling defends against
exactly this, and unit tests construct their own instants.

**Fix:** normalize once, the way the sibling does.

```python
def seconds_until_rollover(evaluated_at: datetime) -> int:
    """Whole seconds from this instant to the UTC month boundary the allowance rolls over on."""
    # Converted first, as `monthly_period_for` is: the boundary is the UTC month's, not the argument's.
    instant = evaluated_at.astimezone(UTC)
    december = instant.month == 12
    rollover = instant.replace(year=instant.year + (1 if december else 0),
                               month=1 if december else instant.month + 1,
                               day=1, hour=0, minute=0, second=0, microsecond=0)
    return max(math.ceil((rollover - evaluated_at).total_seconds()), 1)
```

(`UTC` is already imported at `quota.py:5`.)

### WR-32: the comment and docstring rules in `AGENTS.md` are broken at scale in these files

**File:** `src/nativespeaker/api/services/restore.py:105-115`, `src/nativespeaker/api/crud/subscriptions.py:375-381`, `src/nativespeaker/api/services/quota.py:75-82`, `src/nativespeaker/api/crud/grants.py:178-184`, `src/nativespeaker/api/services/auth.py:224-229` and `:293-296`, `src/nativespeaker/api/services/chats.py:145-149`, `src/nativespeaker/api/crud/identities.py:88-90` and `:134-135`

**Issue:** `ns-api-gateway/AGENTS.md` § "Comments and docstrings" is explicit and says it binds all
code in the repository: *"**One line each.** A comment explains the specific line or lines below it.
It never explains the design, the request lifecycle, a rule enforced in another module, or a
decision that was made elsewhere."* The reviewed files violate it systematically. The worst case is
an eleven-line block:

```
# The window travels with the status that decided entitlement. Where the canonical row
# decided it, the webhook that wrote that status also wrote the grant carrying the window
# it wrote it with, and `lock_grants_of` above holds that row. Reading the window off the
# proof instead asked a second artifact for it, and an Apple proof states no grace window
# at all -- `verify_transaction` sets `grace_period_expires_at=None` unconditionally,
# ...
```
(`services/restore.py:105-115`, above a two-line list comprehension.)

These blocks do the three things the rule names: they explain the design, they narrate a rule
enforced in another module (`verify_transaction`, `write_subscription_grant`,
`activate_registered_account_grant`, `ix_access_grants_one_active_per_user`), and they record
decisions made elsewhere — several are literally the text of a prior review finding, pasted above
the line that answered it.

I am filing this against the standing instruction that 37.x fixes are current intended code,
because the timeline shows the rule and the violations are moving in opposite directions: the
comment rules landed in `20aa543` (37.4), and `559deaa` (`fix(37.5): CR-25 read the restore term
from whatever decided the status`) then *added* the eleven-line block above. The 37.5 fix pass is
re-growing the prose register that 37.4 wrote the rule to remove. Left alone, the rule becomes
inoperative and the next reviewer has no ground to hold anything to it.

The cost is concrete, not aesthetic: several of these blocks assert facts about code in another
module that nothing checks (`services/restore.py:112-113` states what
`verify_transaction` does with `grace_period_expires_at`), so a change there leaves a confidently
wrong comment here.

**Fix:** for each block, keep the one line that resolves the ambiguity at the line below it and
delete the narration. For `services/restore.py:105-115`, that is roughly:

```python
# At most one row answers: an entitled write supersedes this subscription's active grants first.
recorded_term = [grant.ends_at for grant in marked_active ...]
```

and the deleted reasoning belongs in `38-REVIEW-FIX.md` / the phase summary, which is where a
decision record is readable without being load-bearing in the source.

### WR-33: `lock_grants_of` locks usage rows and discards the `None` that means the row is absent

**File:** `src/nativespeaker/api/crud/subscriptions.py:89-92`

**Issue:**

```python
marked_active = await self.grants_db.lock_active_grants_of(user_ids)
for grant in marked_active:
    await self.grants_db.lock_usage(grant.id)
return marked_active
```

`lock_usage` is typed `UserMonthlyUsage | None` (`crud/grants.py:128-131`) and its own docstring in
`_usage_statement` says *"`None` is the fail-closed signal, not a cue to mint a row"*
(`crud/grants.py:43`). Here the return value is dropped on the floor, so the fail-closed signal is
discarded at the exact point the second lock tier is taken — the last place before
`write_subscription_grant` where a grant missing its usage row could be refused cheaply, with no
rows written and no locks yet used for anything.

This is the upstream half of CR-29: fixing only `write_subscription_grant` leaves this method
silently "locking" a row that does not exist, which is also why nothing in the ingest and restore
paths notices the broken invariant before it reaches the carry-over read. The two should be fixed
together, and this one additionally gives the refusal a location where nothing is pending on the
session.

**Fix:** raise on the absent row rather than discarding it, keeping the raise beside the query per
AGENTS.md exception 4.

```python
for grant in marked_active:
    # Second in the lock order, always after the grant rows.
    if await self.grants_db.lock_usage(grant.id) is None:
        raise MissingUsageRowError(grant.id)
```

If the refusal is deliberately deferred to the writer instead, the discard needs to be explicit
(`_ = await ...`) plus a one-line comment saying who does refuse — but the silent drop as written
reads as an oversight, and CR-29 shows nobody downstream picks it up.

---

### WR-45: the Google log-hygiene walk checks the wrong credential and the wrong envelope

**File:** `tests/e2e/test_google_play_webhook.py:502-529`, `:554-563`

**Issue:** `_drive_every_recording_arm` returns `(verified, body)` and the hygiene case asserts those
two values reach no log record. Neither value belongs to the arm that is actually at risk:

- `verified` (`:505`) is the *good* push token used by deliveries 2-6. The one delivery that produces
  a `notification_rejected` record — the arm where a credential is most likely to be logged — is sent
  at `:510-512` with a **different** token, `_push_token(private_key=FOREIGN_PRIVATE_KEY_PEM)`, which
  is never captured and never checked.
- `body` is rebound inside the loop at `:527`, so the returned envelope is the *last* delivery's
  (`EVENT_TIME_MILLIS + 1000`, the attribution-conflict arm). The envelope the refused push carried
  (`:506`, `_push_body(PURCHASE_TOKEN)`) is a different base64 string and is likewise unchecked, as
  are `_undecodable_push_body()` and `_refund_review_push_body()`.

So the file's stated property — "the push token, the envelope ... reach no record" (`:500`) — is
proven only for arms that never see a credential. A regression that logged `credential.credentials`
or `body.message.data` from `verify_google_play_notification`'s refusal path would pass this suite.
The Apple twin gets this right by construction: `test_app_store_webhook.py:47` uses one shared
`ENVELOPE` constant across every delivery, so its walk covers the refused arm.

**Fix:** Capture every credential and every envelope the walk sends, and assert over all of them:

```python
    async def _drive_every_recording_arm(self, client, seam, factory) -> tuple[list[str], list[str]]:
        await _seed_store_token(factory, ATTRIBUTION_TOKEN)
        verified = _push_token()
        foreign = _push_token(private_key=FOREIGN_PRIVATE_KEY_PEM)
        headers = {"Authorization": f"Bearer {verified}"}
        # Every credential and every envelope this walk puts on the wire, so the hygiene case
        # below covers the refusal arm rather than only the arms that carry no credential.
        sent: list[dict] = []

        for bearer, pushed in ((foreign, _push_body(PURCHASE_TOKEN)),
                               (verified, _undecodable_push_body()),
                               (verified, _refund_review_push_body())):
            sent.append(pushed)
            await client.post(PATH, json=pushed,
                              headers={"Authorization": f"Bearer {bearer}"})
        ...
        return [verified, foreign], [pushed["message"]["data"] for pushed in sent]
```

and in the assertion:

```python
        credentials, envelopes = await self._drive_every_recording_arm(...)
        for secret in (*credentials, *envelopes, PURCHASE_TOKEN,
                       ATTRIBUTION_TOKEN, OTHER_ATTRIBUTION_TOKEN):
            assert secret not in rendered, f"a log record carries {secret!r}"
```

---

### WR-46: no e2e case asserts a non-zero `monthly_used` on the wire, and the one that seeds it discards it

**File:** `tests/e2e/test_sync.py:26`, `:197-206`

**Issue:** `_CURRENT_USED = 5` exists solely to seed a current-period grant with a distinguishing
count, and `test_a_current_period_grant_is_left_untouched` seeds it (`:200`) — then never reads it
back off the response:

```python
        await seed_grant(_db_transaction, user_id=user.id, monthly_used=_CURRENT_USED)
        before = await _entitlement_snapshot(_db_transaction, user.id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert await _entitlement_snapshot(_db_transaction, user.id) == before   # only the rows
```

Every other e2e sync case reports `monthly_used == 0`: the "whole body" happy path (`:92-110`) uses
`quota_grant`, which `conftest.py:593-622` seeds at `monthly_used=0`; `:171-190` likewise; and the
stale-period case (`:208-221`) *asserts* zero. The two absent-entitlement bodies are zero by
definition. The net effect is that a handler hard-coding `"monthly_used": 0` passes every case in
`test_sync.py`, including the three that compare the whole body as a literal — which is exactly the
lie ROADMAP criterion 1 and D-07 exist to prevent ("Reporting '0 of 500 used' to a client whose every
chat request returns 500").

`tests/unit/test_sync_resolver.py:262-264` does prove the resolver returns `7`, so the logic is
covered — but not through the router, the response model, or JSON serialization, which is where
`test_sync.py` claims to assert "the whole body, not two known keys" (`:101`). The seeded constant
promises coverage the file does not have.

**Fix:** Read the seeded count off the wire in the case that already seeds it:

```python
        assert response.status_code == 200, response.text
        # The seeded count reaches the wire: without this the whole file passes on a hard-coded 0.
        assert response.json()["entitlement"]["monthly_used"] == _CURRENT_USED
        assert await _entitlement_snapshot(_db_transaction, user.id) == before
```

---

### WR-47: the refusal-arm completeness control reads a hard-coded pair of sources and matches only a bare call name

**File:** `tests/e2e/test_app_store_webhook.py:58-60`, `:66-78`, `:292-301`;
`tests/e2e/test_google_play_webhook.py:220-222`, `:228-240`, `:385-393`

**Issue:** `_raised_refusal_stages()` walks the AST of a fixed two-element `_REFUSAL_SOURCES` tuple
and only records a call whose `node.func` has an `.id` equal to `"NotificationRejected"`. Both
narrowings are silent:

1. **Only two modules are read.** The Apple tuple is
   `(inspect.getsource(verify_app_store_notification), inspect.getsource(app_store))`. That dependency
   function (`app/dependencies.py:191-195`) contains *no* raise site at all, so the entire non-enum
   half of the Apple control derives from `auth/app_store.py` alone. A `NotificationRejected` added to
   a shared helper in `app/dependencies.py`, to `auth/store_notifications.py`, or to
   `services/subscriptions.py` is invisible to `raised` — and, being new, is equally absent from the
   hand-written `REFUSAL_STAGES`. Both sides of `assert set(REFUSAL_STAGES) == (raised - {_COMPUTED})
   | (KNOWN_STATUSES - {"OK"})` shrink together and the control passes with the arm untested.
2. **Only a bare `Name` call matches.** `getattr(node.func, "id", None)` returns `None` for an
   `ast.Attribute`, so `raise errors.NotificationRejected(stage=...)` — a perfectly ordinary import
   style, and the one the file would be rewritten to if `errors` were ever imported as a module — is
   skipped with the same silent-shrink effect.

The comment at `:58` claims the opposite ("read as source so a third one arrives here"). This control
class has already rotted twice in this repository (37.3 WR at `37.3-REVIEW.md:1441`, 37.5 at
`37.5-REVIEW.md:1895`), each time by deriving one side of an equality from a source that moved. This
is not a request to reverse the ratified 37.3 fix — that fix replaced enum-derivation with source
reading, which is strictly better — it is the residual gap the fix did not close.

**Fix:** Read the package rather than two hand-named modules, and match the attribute form too:

```python
import pkgutil

import nativespeaker.api as _api


def _api_sources() -> tuple[str, ...]:
    """Every module of the application package, so a raise site added anywhere arrives here."""
    return tuple(inspect.getsource(importlib.import_module(name))
                 for _, name, _ in pkgutil.walk_packages(_api.__path__, f"{_api.__name__}."))


def _called_name(node: ast.Call) -> str | None:
    """The callee's own name, whether it was called bare or through its module."""
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
```

If walking the package is judged too broad, at minimum add a second control that greps the whole
`src/` tree for `NotificationRejected(` and asserts the hit count equals the number of `ast.Call`
nodes `_raised_refusal_stages` found — so a raise site outside `_REFUSAL_SOURCES` fails loudly
instead of shrinking both sides of the equality.

---

### WR-48: three assertions in the unmapped-product case query keys no code path could ever have written

**File:** `tests/e2e/test_app_store_webhook.py:381-400` (specifically `:384`, `:393-395`)

**Issue:** The case mints `notification = _notification()` at `:384`, then scripts the seam to
**raise** at `:385-386`:

```python
        notification = _notification()
        scripted_app_store_notifications.script(
            UnmappedStoreProduct(PurchaseProvider.apple, UNMAPPED_PRODUCT_ID))
        ...
        assert await _subscriptions_of(_db_transaction, notification.external_id) == []
        assert await _purchases_of(_db_transaction, notification.external_id) == []
        assert await _events_of(_db_transaction, notification.notification_uuid) == []
```

`FakeAppStoreNotifications.verify` (`conftest.py:321-326`) raises before returning, so the
application never sees `notification`. Its `external_id` and `notification_uuid` are fresh `uuid4()`
values (`:161-163`) that no code path could have written under any implementation. All three
assertions are tautologies, and `notification` is otherwise dead. Only `assert await
_counts(_db_transaction) == before` (`:396`) carries weight.

The sibling case `test_a_refused_payload_writes_nothing` (`:303-316`) documents this exact trap in a
four-line comment and avoids it by counting the three tables instead — so the pattern was recognized
here and then reintroduced twelve lines later. It is the same defect class as ratified 37.3 **WR-83**
("the attribution-token rollback assertion is vacuous — it queries a row that is never written on
that path").

**Fix:** Drop the dead notification and the three tautologies; keep the count, which is the real
claim, and add the one non-vacuous key check the raising seam permits:

```python
    async def test_an_unmapped_product_answers_500_and_writes_nothing(
            self, webhook_client, scripted_app_store_notifications, _db_transaction, error_records):
        """D-14, D-21. An operator adds the map line and Apple's next retry succeeds; nothing is written."""
        # The seam raises instead of returning, so this case names no key: count the three tables,
        # as `test_a_refused_payload_writes_nothing` does, rather than query a uuid4 nothing wrote.
        scripted_app_store_notifications.script(
            UnmappedStoreProduct(PurchaseProvider.apple, UNMAPPED_PRODUCT_ID))
        before = await _counts(_db_transaction)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 500
        assert response.json() == INTERNAL
        assert await _counts(_db_transaction) == before
        assert len(error_records.entries) == 1
        ...
```

### WR-57: Wall-clock assertion in the lock-order control is not marked `timing`

**File:** `tests/schema/test_grant_locks.py:215-249` (assertion at `:244`; constants at `:87-90`)

**Issue:** `test_the_fixed_order_does_not_deadlock` proves contention by measuring how long
connection B waited for A's grant lock and asserting `waited >= _BLOCKED_FOR_SECONDS` (0.15 s) while
A holds for `_A_HOLDS_FOR_SECONDS` (0.2 s). The margin is 50 ms of event-loop scheduling jitter:
`b_takes_the_same_order_and_waits()` and `a_finishes_shortly()` are gathered on one loop, so if B's
coroutine is scheduled more than 50 ms after A's `asyncio.sleep(0.2)` starts, `waited` falls below
the floor and the case goes red for a reason that has nothing to do with the lock order. The repo
already has a marker for exactly this class of test — `pyproject.toml:68` defines
`timing: marks tests whose assertion is wall-clock dependent`, and `tests/unit/test_jwks_offload.py:160,179`
use it — but this case does not carry it, so it cannot be excluded or reported separately.

**Fix:** Mark it, and take the jitter out of the margin by measuring A's release rather than
assuming it:

```python
@pytest.mark.timing
async def test_the_fixed_order_does_not_deadlock(self, committed_grant, contenders):
    ...
    released_at = None

    async def a_finishes_shortly():
        nonlocal released_at
        await asyncio.sleep(_A_HOLDS_FOR_SECONDS)
        released_at = time.monotonic()
        await tx_a.rollback()
    ...
    # B cannot have taken the lock before A let go of it, whenever the loop got round to either.
    assert released_at is not None and started < released_at
```

### WR-58: The lock "mirrors" are never compared to production, though the file says they are

**File:** `tests/schema/test_grant_locks.py:33-47` (the claim at `:34`), `:50-78`

**Issue:** Every case in `TestTheGrantLockExcludes` and `TestTheLockOrderIsLoadBearing` issues the
hand-written `_LOCK_GRANTS` / `_LOCK_USAGE` strings on a raw asyncpg connection, and the comment at
`:34` states "Pinned to production by `TestTheMirrorsStillMatchProduction` below, so a drift there
fails here." That class does not compare the mirrors to anything. It compiles
`_effective_grants_statement(...).with_for_update()` and asserts that five substrings are *present*
in the compiled production SQL (`:60-71`); it never reads `_LOCK_GRANTS`, never asserts the compiled
statement carries no *additional* predicate, and never asserts the two are equivalent. Two drifts
pass green today:

1. A predicate added to `_effective_grants_statement` (say `AND source <> 'manual'`) leaves all five
   substrings present, while the mirror keeps locking the seeded `manual` grant — the deadlock and
   exclusion cases would then be proving things about a statement production never issues, on a row
   production never locks.
2. A term deleted from the mirror string itself is invisible to every assertion in the file.

The same hole applies to `_LOCK_USAGE` at `:73-78`.

**Fix:** Delete the mirrors and derive the executed SQL from the production statement, so there is
nothing left to drift:

```python
def _mirror_of(statement) -> str:
    """The exact SQL production compiles, with the bound instant inlined so asyncpg can run it."""
    return str(statement.compile(compile_kwargs={"literal_binds": True}))

_LOCK_GRANTS = _mirror_of(_effective_grants_statement(USER_ID, EVALUATED_AT).with_for_update())
```

If the hand-written form must stay, add the missing direction — normalize both strings and assert
equality modulo the bound instant, rather than asserting one-way substring containment.

### WR-59: The registered writer's lock-order case drops the ORDER BY check its anonymous twin calls load-bearing

**File:** `tests/schema/test_grant_locks.py:490-498` and `:508-514`

**Issue:** The anonymous claim's lock-order case asserts the ordering clause on **every**
grant-tier locking read, and states why at `:358`: *"Every grant-tier read, not the first alone: an
unordered second one is a second order."*

```python
for statement in taken[:2]:
    assert "ORDER BY core.access_grants.id ASC" in statement
```

`activate_registered_account_grant` (`src/nativespeaker/api/crud/grants.py:224-228`) takes the same
two grant-tier reads — `lock_active_grants` then `lock_effective_grants` — but
`test_the_conversion_locks_the_grant_rows_then_their_usage_rows` checks only `taken[0]` (`:498`),
and `test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row` (`:508-514`) asserts no
ordering at all. `_active_grants_statement` losing its `ORDER BY` is therefore caught on the
anonymous route and missed on the registered one, even though `SHARED-INVARIANTS.md:34` binds both
("ascending grant id … binding every current and future path") and the registered route is the one
that locks two grants at once during a conversion.

**Fix:** Use the anonymous form in both places:

```python
# `taken[:2]`, not `taken[0]`: an unordered second grant-tier read is a second lock order.
for statement in taken[:2]:
    assert "ORDER BY core.access_grants.id ASC" in statement
```

and add the same loop to `test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row`.

### WR-60: Half of the registration-pairing assertion can never count anything

**File:** `tests/schema/test_registration_pairing.py:119-137` (the vacuous line at `:133-134`)

**Issue:** `TestTheProductionWriterLeavesNeitherHalf` has one case,
`test_a_created_registered_account_satisfies_both_halves`, and it drives
`run_creation(..., provider=IdentityProvider.google, ...)`. Under `creation_harness.issuer` that
leaves exactly one identity row, with `provider = 'google'`. The first scan is

```sql
... WHERE u.registered_at IS NOT NULL AND i.provider = 'anonymous' AND i.issuer = :issuer
```

so its `i.provider = 'anonymous'` term matches nothing under that issuer no matter what the writer
did, and `assert ... == 0` at `:133-134` is structurally incapable of failing. Only the second scan
carries weight, which makes the case name ("both halves") and the class docstring ("the only writer
that can reach the third state") wrong.

The arm that can regress that scan is the anonymous one, and it is real:
`src/nativespeaker/api/crud/identities.py:101` writes
`registered_at=None if provider is IdentityProvider.anonymous else evaluated_at`. Flipping that
conditional puts every anonymous account into the third state, and nothing in this file — the only
file that scans the pairing over production-written rows — would notice.

**Fix:** Parametrize the case over both providers, so each scan is exercised on the arm that can
break it:

```python
@pytest.mark.parametrize("provider,provider_uid", [
    (IdentityProvider.google, "uid_"),      # exercises _REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER
    (IdentityProvider.anonymous, None),     # exercises _REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY
])
async def test_a_created_account_satisfies_both_halves(self, creation_harness, provider, provider_uid):
    ...
```

(The anonymous arm needs `provider_uid=None`, which is what the table's own CHECK requires.)

### WR-61: The converse lock-freedom case asserts no premise, so it can pass on a closed reader

**File:** `tests/schema/test_sync_lock_freedom.py:140-153`

**Issue:** `test_a_charge_is_not_blocked_by_an_open_sync_read` is the case the docstring calls "the
one that matters in production": the charge must commit while a sync read is still open. Its only
assertion is `stored_usage(harness) == SEEDED_USED + 1` — i.e. that the charge committed. Nothing
asserts the reader's transaction was actually open and holding a connection at the moment the charge
ran. Its sibling at `:110-138` carries three explicit `"control: …"` assertions for exactly this
reason (it proves the holder really holds both rows before asserting sync reads through them); this
one has none.

`SyncService.read_entitlement` (`src/nativespeaker/api/services/sync.py:25-64`) does not commit
today, so the case is sound as written. But the day it does — or the day the session factory gains
autocommit — the case silently becomes two serialized transactions and stays green, which is the
same failure mode the module's own header comment (`:2-4`) says it exists to avoid.

**Fix:** Assert the premise the way the sibling does:

```python
async with harness.factory() as reader:
    await (await reader.connection()).execute(text(f"SET LOCAL lock_timeout = '{_NO_WAIT}'"))
    await SyncService(reader, harness.evaluated_at).read_entitlement(harness.user_id)

    # control: the read must still be inside its transaction, or the charge below contends with nothing.
    assert reader.in_transaction(), "the reader's transaction ended, so this case races nothing"
    ...
```

### WR-69: The "carried forward, never fabricated" bit assertions cannot distinguish a hardcoded `False`

**File:** `tests/unit/test_claim_precedence.py:541-542`, `tests/unit/test_claim_precedence.py:557`,
`tests/unit/test_claim_precedence_registered.py:336-337`,
`tests/unit/test_claim_precedence_registered.py:352`

**Issue:** Production carries the sibling bit across from the read
(`src/nativespeaker/api/services/auth.py:236-237` writes `bit0=True, bit1=state.bit1`; `:302-303`
writes `bit0=state.bit0, bit1=True`), and both suites carry a comment asserting exactly that
property:

```python
# tests/unit/test_claim_precedence.py:541
# bit1 carried forward from the query, never fabricated.
assert devicecheck.write_calls == [(DEVICE_TOKEN, True, False)]
```

But `_ScriptedDeviceCheck.answer` defaults to `BitState(bit0=False, bit1=False)`
(`test_claim_precedence.py:149`), and **no case in either suite scripts a `True` carried bit on a
path that reaches the write**. In the anonymous suite the only override is
`BitState(bit0=True, bit1=False)` (`:448`, `:643`), which refuses at
`DeviceGrantExhausted` before the write. In the registered suite the only override is
`BitState(bit0=False, bit1=True)` (`:358`, `:571`), which refuses the same way. So the carried bit is
`False` in every write the suite ever observes, and both assertions would pass unchanged if
`services/auth.py` hardcoded `bit1=False` / `bit0=False`.

This is the exact regression the comment exists to prevent, and it matters: Apple writes both bits in
one call and nothing in this product ever clears a bit, so a fabricated `False` silently returns a
spent slot to a device.

**Fix:** Script the opposite bit as set on one case per suite. Anonymous — a device that already
spent its registered slot must still get its anonymous grant, carrying bit1 forward:

```python
# tests/unit/test_claim_precedence.py, in TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce
def test_the_other_bit_is_carried_forward_rather_than_fabricated(self, client, store, account,
                                                                 grants, devicecheck):
    """bit1 is this device's registered slot: writing False here would hand it back."""
    identity_row, _ = account
    store.row = _issued_row(bound_to=identity_row.id)
    devicecheck.script(BitState(bit0=False, bit1=True))

    assert _claim(client).status_code == 200
    assert devicecheck.write_calls == [(DEVICE_TOKEN, True, True)]
```

and the mirror in `test_claim_precedence_registered.py` with
`devicecheck.script(BitState(bit0=True, bit1=False))` expecting
`[(DEVICE_TOKEN, True, True)]`.

### WR-70: `test_a_body_offering_a_second_token_is_rejected_before_the_gate` earns its 422 from the missing required field, not from any rejection of a second token

**File:** `tests/unit/test_claim_precedence.py:600-613`

**Issue:** The case posts a body carrying `challenge_id`, `query_token` and `update_token` — and no
`device_token` — then asserts 422, under the docstring "The split body is gone from the wire, so
there is no second token left to substitute." The 422 comes entirely from `device_token` being
required (`schemas/auth.py:38`, `Field(..., min_length=1)`); the two extra keys contribute nothing.
`GrantClaimRequest` declares no `model_config`, so it takes pydantic's default `extra='ignore'`,
which I verified directly:

```
$ .venv/bin/python -c "from nativespeaker.api.schemas.auth import GrantClaimRequest; \
    print(GrantClaimRequest(challenge_id='h', device_token='real-token', update_token='attacker-device'))"
challenge_id='h' device_token='real-token'
```

So a body offering a second token *alongside* a valid `device_token` is accepted, and the case would
pass unchanged whether the model ignored extras, allowed them, or forbade them. It measures the
required-field arm that `_UNUSABLE_BODIES`-style cases already cover, not the property it names.

(The invariant itself holds — the handler reads only `device_token` and passes it to both seam calls,
which `test_the_token_the_gate_reads_is_the_token_it_then_writes` at `:589-598` does pin. This is a
test-strength defect, not a shipped one.)

**Fix:** Keep a valid `device_token` in the body so the extra keys are the only thing under test, and
assert the ignored keys never reach the seam:

```python
def test_a_body_offering_a_second_token_never_reaches_the_gate_with_it(self, client, store,
                                                                       account, devicecheck):
    identity_row, _ = account
    store.row = _issued_row(bound_to=identity_row.id)

    response = client.post("/auth/claim-anonymous-grant",
                           json={"challenge_id": HANDLE,
                                 "device_token": DEVICE_TOKEN,
                                 "query_token": "device-a-never-written-to",
                                 "update_token": "device-b-already-set"})

    assert response.status_code == 200
    # The extra keys are ignored, so one device is named on both calls and neither substitute lands.
    assert devicecheck.read_calls == [DEVICE_TOKEN]
    assert [token for token, _, _ in devicecheck.write_calls] == [DEVICE_TOKEN]
```

Alternatively set `model_config = ConfigDict(extra="forbid")` on `GrantClaimRequest` and assert the
422 — but that changes the wire contract and should go through a spec change, so the assertion above
is the honest fix for this file.

### WR-71: `test_the_preauth_callable_route_still_resolves_the_identity` passes vacuously if a pre-auth route is unregistered

**File:** `tests/unit/test_app_wiring.py:64-68`

**Issue:** The body is a loop with an `if route.path in PREAUTH_CALLABLE_PATHS` guard and no
assertion that either path is registered at all:

```python
def test_the_preauth_callable_route_still_resolves_the_identity(self):
    for route in _api_routes():
        if route.path in PREAUTH_CALLABLE_PATHS:
            assert get_identity in _declared(route), route.path
```

If `/auth/create-user` or `/auth/challenge` were renamed or dropped, the loop body simply never runs
and the case is green. Its own sibling two methods down knows this and guards for it —
`test_a_narrowed_route_declares_the_linked_identity_narrowing` (`:75-79`) asserts
`declared, f"{path} is not a registered route"` first. No other case in the file backstops it: both
`test_the_public_allowlist_is_exactly_the_readiness_probe` (`:91-97`) and
`test_no_route_serves_without_an_identity_or_a_callback_declaration` (`:99-104`) build their sets
from the *live* routes, so a vanished route only shrinks them and both still pass. Confirmed
empirically — today the loop runs for `['/auth/challenge', '/auth/create-user']` and would silently
run for fewer.

This matters more than the usual vacuity case because D-10
(`.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md:129`) names this literal as the
authoritative record of which routes admit an unlinked caller.

**Fix:** Drive the case off the literal rather than off the live routes, exactly as `:75-79` does:

```python
@pytest.mark.parametrize("path", sorted(PREAUTH_CALLABLE_PATHS))
def test_the_preauth_callable_route_still_resolves_the_identity(self, path):
    """Create-user is exempt from the narrowing, not from authentication: a linked caller is owed a 409."""
    declared = [_declared(route) for route in _api_routes() if route.path == path]
    assert declared, f"{path} is not a registered route"
    assert all(get_identity in calls for calls in declared)
```

### WR-83: The sync stub session ignores every lookup key, so the resolver's ownership scoping and its evaluation instant are unasserted

**File:** `tests/unit/test_sync_resolver.py:76-79` (`_StubSession.exec`), `:196-206`
(`TestThePredicateBoundaries`)

**Issue:** `_StubSession.exec` resolves its answer from
`statement.column_descriptions[0]["entity"]` alone and returns a pre-canned row list. It
never inspects the `WHERE` clause or the bound parameters. `_compiled()` renders bound
values as `%(user_id_1)s` placeholders, so the SQL-text assertions in
`TestThePredicateBoundaries` cannot recover them either. The consequence is that not one of
the four values `SyncService.read_entitlement` passes downward is observable:

| mutation applied to `src/nativespeaker/api/services/sync.py` | result |
|---|---|
| `read_effective_grants(UUID(int=1), …)` instead of `user_id` | 30 passed |
| `read_usage(UUID(int=2))` instead of `grant.id` | 30 passed |
| `monthly_credits("some-other-tier")` instead of `grant.tier_id` | 30 passed |
| `read_effective_grants(user_id, datetime(2000,1,1,UTC))` instead of `self.evaluated_at` | 30 + 11 passed |

The first mutation is a cross-tenant entitlement read;
`SHARED-INVARIANTS.md:5` makes `core.users.id` the sole ownership key. The fourth defeats
`03-sync.md:42` ("Derive everything from ONE captured evaluation time ... grant selection,
`current_period` computation, and the usage read") — the period would still come from the
captured instant while grant selection came from a different one, and
`test_sync_clock_capture.py` cannot see it because it only walks the syntax tree for clock
*calls*.

This is a regression against the file's own sibling: `test_quota_resolver.py:319-321`
(`test_the_effective_grant_statement_is_scoped_and_uncapped`) explicitly asserts
`"core.access_grants.user_id = " in sql` and calls it "the tenant scope". The sync mirror
dropped that assertion while keeping the four boundary assertions around it.

**Fix:** Record the arguments at the crud seam rather than only the compiled statement, and
assert them. Minimal change — give `_StubSession` a per-entity call log by wrapping
`GrantsDB`, or add a recording `GrantsDB` double used alongside the existing statement
assertions:

```python
class _RecordingGrantsDB(GrantsDB):
    def __init__(self, session):
        super().__init__(session)
        self.calls: list[tuple] = []

    async def read_effective_grants(self, user_id, evaluated_at):
        self.calls.append(("grants", user_id, evaluated_at))
        return await super().read_effective_grants(user_id, evaluated_at)

    async def read_usage(self, grant_id):
        self.calls.append(("usage", grant_id))
        return await super().read_usage(grant_id)

    async def monthly_credits(self, tier_id):
        self.calls.append(("allowance", tier_id))
        return await super().monthly_credits(tier_id)


async def test_every_read_is_keyed_on_the_caller_the_handler_named(self):
    grant = _grant()
    session = _StubSession(grants=(grant,), usage=_usage(grant))
    service = SyncService(db=session, evaluated_at=EVALUATED_AT)
    service.grants_db = _RecordingGrantsDB(session)

    await service.read_entitlement(USER_ID)

    assert service.grants_db.calls == [("grants", USER_ID, EVALUATED_AT),
                                       ("usage", grant.id),
                                       ("allowance", grant.tier_id)]
```

and add the tenant-scope text assertion its quota sibling already carries:

```python
assert "core.access_grants.user_id = " in sql
```

### WR-84: Removing the tenant predicate from the `/users/me` token read leaves both guarding suites green

**File:** `tests/unit/test_purchases_crud.py:44-47` (`_StubSession.exec`),
`tests/unit/test_users_me.py:56-58` (`_RecordingSession.exec`)

**Issue:** Both stubs answer `exec()` with `self._tokens.items()` regardless of the
statement. `test_purchases_crud.py` does assert statement text — `:127`
`"core.store_purchase_tokens" in _compiled(...)`, `:133` no `FOR UPDATE`, `:138` no
`core.users` — so it demonstrably *can* reach the compiled SQL, and yet nothing asserts the
`user_id` predicate. Same in `test_users_me.py:138-152`.

Proved by mutation: replacing

```python
.where(col(StorePurchaseToken.user_id) == user_id)
```

in `src/nativespeaker/api/crud/purchases.py:19` with a predicate that matches every row
leaves **33 of 33** tests passing across `test_purchases_crud.py` and `test_users_me.py`.
That mutation makes `GET /users/me` return every account's Apple and Google Play purchase
tokens to any authenticated caller, and `test_no_token_value_reaches_the_message`
(`:114`) and `test_the_refusal_carries_no_cache_header_and_no_identifier` (`:206`) — the two
cases written specifically to stop store tokens leaking — do not fire, because on the happy
path there is no refusal to inspect. `SHARED-INVARIANTS.md:5` and `03-sync.md:70` make the
scoping key the whole ownership contract.

**Fix:** Assert the predicate where the compiled statement is already in hand:

```python
async def test_the_statement_is_scoped_to_the_caller(self):
    _, session = await _read(SEEDED)
    sql = _compiled(session.statements[0])

    assert "core.store_purchase_tokens.user_id = " in sql
```

and, in `test_users_me.py`, assert the bound value reaches the crud by recording it:

```python
class _RecordingSession:
    def __init__(self, tokens):
        ...
        self.params: list[dict] = []

    async def exec(self, statement):
        self.statements.append(statement)
        self.params.append(statement.compile(dialect=postgresql.dialect()).params)
        return _RecordingResult(self._tokens.items())


def test_the_read_is_keyed_on_the_barrier_resolved_user(self, client, session, identity):
    client.get("/users/me")

    assert identity.user.id in session.params[0].values()
```

### WR-85: `SyncService`'s source-to-wire type mapping is exercised for one of the four spec-enumerated sources

**File:** `tests/unit/test_sync_resolver.py:84-93` (`_grant`, `source=AccessGrantSource.manual`),
`:271` (`TestTheRolloverIsComputedNeverWritten`)

**Issue:** Every grant this suite builds carries `source=AccessGrantSource.manual`. The
production line is a lossy value conversion between two independently declared enums:

```python
type=EntitlementType(grant.source.value)   # src/nativespeaker/api/services/sync.py:65
```

`AccessGrantSource` (`src/nativespeaker/api/tables/grants.py:11-16`) and `EntitlementType`
(`src/nativespeaker/api/schemas/auth.py:55-61`) agree today, but nothing asserts they do.
If a member is renamed on one side only — or a fifth `core.access_grant_source` value is
added — `EntitlementType(...)` raises `ValueError`, which is not one of the three tripwire
classes `sync.py` raises and is not an `AppError`, so it surfaces as an unhandled 500 for
every affected caller. `03-sync.md:45` enumerates all four sources as reportable `type`
values and calls out `subscription` and `manual` by name.

`grep -rn EntitlementType tests/` shows the other three members are only reached in
`tests/e2e/test_sync.py` and `tests/schema/test_claim_race.py`, both deselected by the
default `addopts = "-v --tb=short -m 'not e2e and not schema'"` (`pyproject.toml:64`), so
nothing in the default suite covers them.

**Fix:** Pin the two enums against each other and drive the resolver over each source:

```python
def test_every_grant_source_has_a_wire_type():
    assert {m.value for m in AccessGrantSource} <= {m.value for m in EntitlementType}


@pytest.mark.parametrize("source", list(AccessGrantSource), ids=lambda s: s.value)
async def test_each_source_is_reported_as_its_own_type(self, source):
    grant = _grant()
    grant.source = source
    entitlement = await _read(_StubSession(grants=(grant,), usage=_usage(grant)))

    assert entitlement.type.value == source.value
    assert entitlement.status is EntitlementStatus.active
```

## Info

### IN-06: `json_log_path` is a config field nothing reads

**File:** `src/nativespeaker/api/config.py:134`

**Issue:** `json_log_path: str | None` is declared on `AppConfig` and referenced
by exactly one thing in the repository — a comment in
`k8s/templates/deployment.yaml:40` explaining that it is unset. `setup_logging`
(`logs.py:27-68`) takes no such parameter and writes only to `log_stream`. A
deployment that sets `JSON_LOG_PATH` gets silence.

**Fix:** delete the field, and with it the deployment comment that leans on it.

### IN-07: `resilence_config` is misspelled in the one keyword that names it

**File:** `src/nativespeaker/api/app/lifespan.py:192` (declared at
`src/nativespeaker/api/services/llm.py:16,21`)

**Issue:** `LLMService(model_config=..., resilence_config=config.resilience, ...)`
— "resilence". It is a public keyword parameter, so the typo is load-bearing at
the call site and cannot be fixed on one side alone.

**Fix:** rename to `resilience_config` in `services/llm.py:16,21` and at this
call site in the same commit.

### IN-08: the `QueueFull` arm in the slot release is unreachable and would silently shrink the queue if it were not

**File:** `src/nativespeaker/api/resilience.py:96-100`

**Issue:**

```python
finally:
    try:
        self._slots.put_nowait(token)
    except asyncio.QueueFull:
        pass
```

`self._slots` has `maxsize=total_slots` and is filled to exactly `total_slots`
at construction (`:82-84`); the context manager only ever returns a token it
took. `QueueFull` cannot fire. If a future change made it fire, `pass` would
permanently destroy one in-flight slot per occurrence and the gate would quietly
narrow until it refused everything.

**Fix:** drop the guard, so a real invariant break surfaces:

```python
finally:
    self._slots.put_nowait(token)
```

### IN-09: the "cannot be reached from outside the module" claim on `_ADMISSION` is contradicted by the test suite

**File:** `src/nativespeaker/api/resilience.py:109-114`

**Issue:** The comment states the token "is proof of admission only because this
object cannot be reached from outside the module". It can:
`tests/unit/conftest.py:32` and `tests/unit/test_resilience_retry.py:14` both do
`from nativespeaker.api.resilience import _ADMISSION`. Python has no module
privacy; the leading underscore is a convention. The guard at `:157-160` still
catches the accidental `Admitted()` it was written for, but the stated guarantee
is not one.

**Fix:** state what the check actually buys — "a caller that skipped
`admission()` and built its own token is refused here" — and delete the
unreachability claim.

### IN-10: `httpx` is declared twice, in `dependencies` and in the `dev` group

**File:** `pyproject.toml:31` and `pyproject.toml:40`

**Issue:** `"httpx >=0.28"` appears in both `[project].dependencies` and
`[dependency-groups].dev`. It is a runtime dependency (`lifespan.py:152,177`
build `httpx.AsyncClient`), so the `dev` entry is redundant and invites the two
constraints to drift.

**Fix:** delete line 40.

### IN-11: `[tool.pogo] schema = 'api'` names a schema no migration creates and the application never uses

**File:** `pyproject.toml:85`, against
`migrations/20260818_01_initial-release.sql:6-7`

**Issue:** The migration creates `core` and `audit`. Nothing creates `api`.
`pogo apply` runs `SET search_path TO api`
(`.venv/.../pogo_core/util/sql.py:24`), which PostgreSQL accepts silently for a
non-existent schema, and records the bookkeeping rows under
`schema_name = 'api'` in `public._pogo_migration`. It works today only because
every statement in the migration is schema-qualified. Two latent consequences:
any future unqualified DDL fails with "no schema has been selected to create
in", and a later `pogo apply` run without `--schema api` would see zero applied
migrations and try to re-apply this one.

**Fix:** set `schema = 'core'` (the schema the migration actually owns), or
delete the key and let it default to `public`, whichever matches how the
bookkeeping table is intended to be addressed. Then re-check
`.pogo_migration` on any environment already migrated.

### IN-12: there is no `.dockerignore`

**File:** `Dockerfile:15-16,29` (no `.dockerignore` at the repository root)

**Issue:** The whole repository is sent as build context, including `.venv/`
(several hundred MB), `.git/`, `.planning/` and a developer's gitignored `.env`.
`COPY src ./src` additionally bakes any `src/**/__pycache__` from the host into
the builder image. Nothing currently `COPY`s the secret-bearing paths, so this
is hygiene rather than exposure — but the guard that keeps it that way is a
reviewer noticing, not a file.

**Fix:** add a `.dockerignore`:

```
.venv/
.git/
.planning/
.env
.env.*
!.env.example
**/__pycache__/
htmlcov/
.coverage
tests/
```

### IN-13: two Apple root certificates are shipped that no configuration path can select

**File:** `config/certs/AppleIncRootCertificate.cer`,
`config/certs/AppleRootCA-G2.cer`, against
`src/nativespeaker/api/config.py:91`

**Issue:** `root_certificate_path` defaults to
`config/certs/AppleRootCA-G3.cer`, and `.env.example:106-107` states that no
path is configurable in practice ("No root certificate path is listed"). The
other two `.cer` files are referenced by nothing in `src/`, `tests/`, `config/`
or `k8s/`, and `Dockerfile:29` copies all three into the runtime image. A
reviewer cannot tell whether they are a fallback chain or leftovers.

**Fix:** delete both files, or state in `config/certs/` which deployment selects
them.

### IN-14: the exception-info decision reads the raw `log_level`, not the sanitized one two lines above

**File:** `src/nativespeaker/api/app/error_handlers.py:38,45`

**Issue:**

```python
level = exc.log_level if exc.log_level in _LOGGABLE else logging.ERROR
record = getattr(logger, logging.getLevelName(level).lower())
record(camel_to_snake(type(exc).__name__),
       exc_info=exc if exc.log_level >= logging.ERROR else False, **exc.log_fields())
```

Line 38 exists because a non-standard level would crash structlog's filtering
logger; line 45 then ignores that repair and compares the unsanitized value. A
class declaring `log_level = 15` is recorded through `logger.error` — the
fallback — while `exc_info` is suppressed, so the loudest line the service can
emit carries no traceback. The two lines should read the same variable.

**Fix:**

```python
exc_info=exc if level >= logging.ERROR else False
```

### IN-17: two dead members on `Chat`, one of them an async lazy-load landmine

**File:** `src/nativespeaker/api/tables/chats.py:54`, `:60-62`

**Issue:** `user: User = Relationship()` (`:54`) and the `human_messages` property (`:60-62`) have
no reader anywhere in `src/` or `tests/` — confirmed by grep; only `ai_messages` is used
(`services/chats.py:121`). `Chat.user` is worse than merely dead: it is a lazily-loaded
many-to-one on a model only ever handled inside an `AsyncSession`, and `crud/chats.py` eager-loads
`Chat.messages` and nothing else, so the first attribute access from any async path raises
`MissingGreenlet` — a bare 500 — rather than returning the row. This was reported as
`37.2-REVIEW.md` IN-21 and never addressed; the 37.2 fix pass excluded all Info findings
(`37.2-REVIEW-FIX.md:20`), so it is unaddressed rather than ratified.

**Fix:** delete both. `Chat.user_id` is the ownership key on every query already
(`crud/chats.py:22`, `:33`, `:44`, `:54`), and `AGENTS.md`'s "don't over-engineer" applies: nothing
needs the navigation.

### IN-18: all three of `ty check src`'s remaining diagnostics sit in these files, unsuppressed

**File:** `src/nativespeaker/api/auth/app_store.py:145`, `src/nativespeaker/api/auth/devicecheck.py:127`

**Issue:** `.venv/bin/ty check src` reports exactly three `invalid-argument-type` errors and all
three are here: `_APPLE_STATUSES.get(data.status)` where `data.status` is `Status | None`
(app_store.py:145), and both `payload.get(...)` calls where `isinstance(payload, dict)` narrows
`object` to `dict[Never, Never]` (devicecheck.py:127). Neither is a runtime bug — `.get(None)`
returning `None` is exactly what line 146 tests for, and the `isinstance(bit0, bool)` guard on
line 128 is the real check — but leaving them unsuppressed means `ty check src` can never be a
green gate, and a genuinely new type error would arrive as "Found 4 diagnostics" and read as noise.
The codebase's own convention is a targeted suppression: `crud/chats.py:21` carries
`# type: ignore[invalid-argument-type]` for the same class of SQLAlchemy/stdlib stub mismatch.

**Fix:** suppress both sites the way `crud/chats.py:21` does, with the reason on the line above:

```python
        # `.get(None)` is the None line 146 tests for; the stub declares the key non-optional.
        status = _APPLE_STATUSES.get(data.status)  # type: ignore[invalid-argument-type]
```

and for devicecheck, annotate the narrow instead so no suppression is needed:
`payload: dict[str, object] = ...` after an `isinstance(payload, dict)` guard, or change `_decoded`
to return `dict[str, object] | None` and do the `isinstance` there.

### IN-19: two comments cite line numbers that point at the wrong code

**File:** `src/nativespeaker/api/auth/store_notifications.py:31`, `src/nativespeaker/api/schemas/api.py:10`

**Issue:** Both comments navigate the reader to a specific line, and both are already wrong.
`store_notifications.py:31` says readers ask the status field "by identity (`crud/subscriptions.py:300`,
`term_end_for` below)"; `crud/subscriptions.py:300` is a parameter in `append_event`'s signature —
the identity comparison it means is at `:349-352` (`status is SubscriptionStatus.revoked`).
`schemas/api.py:10` says "`create_chat` spends the monthly allowance at `services/chats.py:96`";
line 96 constructs the human `Message`, and the charge is at `services/chats.py:101`
(`await self.quota_service.charge(...)`). A cross-reference that points at the wrong line is worse
than none: it costs the next reader a search and teaches them not to trust the next one.

**Fix:** cite the symbol, not the line — `crud/subscriptions.py`'s `activate_subscription_grant` and
`ChatService.create_chat`'s `quota_service.charge` call — so the reference survives the next edit.
Every other comment in these modules already names symbols this way.

### IN-20: a Pub/Sub-permitted attributes-only delivery is logged at ERROR as "out of range"

**File:** `src/nativespeaker/api/auth/google_play.py:134-139`

**Issue:** `if not data or len(data) > PUBSUB_DATA_LIMIT` folds two unrelated conditions into one
`logger.error("google_play_message_out_of_range", length=len(data))`. The empty case is not out of
range and is not an anomaly: `schemas/webhooks.py:32-34` documents that `data` defaults to `""`
precisely because "Pub/Sub permits an attributes-only message", and 44 D-04 ratified answering 200
for it. So a delivery the system explicitly supports emits an ERROR line whose label says the body
was too big and whose `length=0` contradicts it. On a pre-launch service with no traffic that is
noise; once alerting is wired to ERROR it is a false page.

**Fix:** split the arms so the label matches the condition, and drop the empty case to `info` — it
is a supported shape, not a failure:

```python
    if not data:
        # Attributes-only: a shape Pub/Sub permits, carrying no notification to read.
        logger.info("google_play_message_without_data")
        return None
    if len(data) > PUBSUB_DATA_LIMIT:
        logger.error("google_play_message_out_of_range", length=len(data))
        return None
```

### IN-21: the `tables` package mirrors two UNIQUE rules and deliberately refuses to mirror the rest

**File:** `src/nativespeaker/api/tables/auth.py:32`, `src/nativespeaker/api/tables/purchases.py:78`

**Issue:** `AuthChallenge.challenge_id: str = Field(unique=True)` and
`SubscriptionEvent.notification_uuid: str = Field(unique=True)` put two `UniqueConstraint`s into
`SQLModel.metadata` — confirmed by introspection:

```
core.auth_challenges     constraints= [... ('UniqueConstraint', None, ['challenge_id'])]
audit.subscription_events constraints= [... ('UniqueConstraint', None, ['notification_uuid'])]
```

Their siblings state the opposite policy in comments, three times:
`purchases.py:40` ("Deliberately not `unique=True`: the table's rule is the composite UNIQUE
(provider, identity_value)"), `:56`, `:95`. The package docstring
(`tables/__init__.py:2-3`) declares one rule — "`SQLModel.metadata` never states a second version of
the schema that could drift from that file" — and the package now states a partial version of it.
The guard that exists for this cannot see it: `tests/unit/test_tables_metadata.py:17-21` walks
`table.indexes`, and a SQLModel `unique=True` produces a `UniqueConstraint` in `table.constraints`,
so the test passes vacuously on both. No behaviour is wrong today — the migration's column-level
`UNIQUE` at `migrations/20260818_01_initial-release.sql:208` and `:296` compiles to the same
unnamed constraint — but the rule the package claims to hold is not the rule it holds, and its own
test cannot tell.

**Fix:** pick one and make the test enforce it. The cheaper direction matches the three existing
comments: drop both `unique=True` markers (the crud paths already treat the database as the
arbiter — `crud/subscriptions.py:284-291` and `:315-322` classify `IntegrityError` via
`is_unique_violation` and never name a constraint), and widen the guard:

```python
    def test_no_mapped_table_declares_a_unique_constraint(self):
        declared = sorted(f"{name}.{col.name}"
                          for name, table in TABLES.items()
                          for c in table.constraints if isinstance(c, UniqueConstraint)
                          for col in c.columns)

        assert declared == []
```

### IN-22: `Chat.id` is the only mapped primary key with no generator

**File:** `src/nativespeaker/api/tables/chats.py:40`, `src/nativespeaker/api/services/chats.py:94`

**Issue:** Every other mapped table generates its own key — `Message.id`, `AuthChallenge.id`,
`AccessGrant.id`, `Subscription.id`, `SubscriptionEvent.id`, `StorePurchase.id`,
`ExternalIdentity.id`, `User.id` all carry `default_factory=uuid7`. `Chat.id: UUID =
Field(primary_key=True)` carries none, and its sole creator supplies `uuid4()`
(`services/chats.py:94`) rather than the `uuid7` every sibling uses. Two consequences, both small:
a `Chat(...)` written without an explicit id gets `id=None` and fails at flush as a `NOT NULL`
violation instead of getting a key, and chat ids are not time-ordered while `Message.id` is —
`tables/chats.py:52` relies on exactly that property of `Message.id` ("`Message.id` is uuid7, so
ascending id is chronological"), so the inconsistency is one a reader will trip over.

**Fix:** `id: UUID = Field(default_factory=uuid7, primary_key=True)` and drop the explicit
`id=uuid4()` at `services/chats.py:94`. `create_chat` reads `chat.id` at `:96` and `:125`, which
works the same way `crud/grants.py:196` reads `activated.id` before flush.

### IN-34: `/auth/sync` is the only route returning `SyncResponse` without `Cache-Control: no-store`

**File:** `src/nativespeaker/api/routers/auth.py:186-193`

**Issue:** Four routes return the same `SyncResponse` body — the caller's entitlement, tier,
allowance, usage and stored `identity_provider`. Three set the header
(`routers/auth.py:128`, `:151`, `:179`), as does `/users/me` (`routers/users.py:24`, *"the tokens
are secrets, and a revalidatable copy is a copy"*). `/auth/sync` does not, and no middleware adds it
(`grep -rn "Cache-Control" src/` returns only those five sites).

Not a spec violation: `req~sessions-challenge-transport-no-store~1` binds prepare responses only,
and a POST response is not cacheable by a shared cache without explicit freshness information. It is
an unexplained inconsistency between four routes with one body shape, and the one route named after
the shape is the odd one out. This was previously filed as IN-03 in `38-REVIEW.md` and is still open.

**Fix:** take `response: Response` and set `response.headers["Cache-Control"] = "no-store"`, matching
the three siblings — or, if the deliberate answer is that sync does not need it, say so in one line
where the siblings say the opposite.

### IN-35: chat and message rows take their `created_at` from a fresh clock, not the request's instant

**File:** `src/nativespeaker/api/services/chats.py:94`, `:96-97`, `:125-126`, and `tables/chats.py:32`, `:45`

**Issue:** `ChatService` is constructed with `evaluated_at` and uses it for exactly one thing, the
quota charge (`services/chats.py:101`, `:130`). `Chat(...)` and `Message(...)` are constructed
without `created_at`, so both fall back to `default_factory=lambda: datetime.now(UTC)` on the model.
Every other writer in this group passes the captured instant explicitly — `crud/grants.py:192-200`,
`crud/subscriptions.py:396-406`, `crud/identities.py:100-124`, `crud/challenges.py:55` — and both
values are client-visible (`ChatResponse.created_at`, `MessageResponse.created_at`).

Low impact: `get_messages` orders by `Message.id` (uuid7), not by `created_at`, so no ordering
depends on it, and `SHARED-INVARIANTS.md`'s one-instant rule is aimed at time-dependent *decisions*
rather than at record timestamps. Recorded because `chats.py` is the only writer left that does not
follow the convention, which makes the exception invisible.

**Fix:** pass `created_at=self.evaluated_at` at the four construction sites, or state in one line
why a chat transcript deliberately wants two distinct wall-clock instants for the human and AI turns.

### IN-36: `issue_challenge` places a transaction boundary in the handler

**File:** `src/nativespeaker/api/routers/auth.py:70-76`

**Issue:** `AGENTS.md` § "Package layout", exception 3: *"`commit()` and `rollback()` are transaction
boundaries and therefore business logic; they live in `services/`."* `issue_challenge` calls
`await session.commit()` in the router body, and it is the only handler in the file that does — the
other seven delegate their boundary to `AuthService`, `RestoreService` or `get_db`'s teardown. The
handler also takes a raw `AsyncSession` and hand-orchestrates validate → narrow → issue → commit →
set header, which is closer to a service than to the `Depends()`-only shape the same section asks of
`routers/`.

The commit is load-bearing — the comment at `:72-73` is right that a handle returned before its row
is durable is a bug — which is the argument for moving it somewhere a later edit to the handler
cannot drop it.

**Fix:** move the body into a `ChallengeService.issue(...)` alongside `AuthService`, leaving the
handler with the rejection branches and the header, or record the exception in `AGENTS.md` if
issuance is deliberately allowed to keep its boundary in the handler.

### IN-49: seven helpers are copied verbatim across the e2e modules

**File:** `tests/e2e/test_sign_out_all.py:32-48`; `tests/e2e/test_app_store_webhook.py:66-78`,
`:105-121`; `tests/e2e/test_google_play_webhook.py:228-240`, `:249-265`;
`tests/e2e/test_claim_anonymous_grant.py:165-196`; `tests/e2e/test_claim_registered_grant.py:77-114`;
`tests/e2e/test_restore_subscription.py:122-153`; `tests/e2e/test_sync.py:249-255` vs
`tests/e2e/test_users_me.py:103-109`

**Issue:** `_LogSpy` and `_spy_on` are byte-identical in three modules; `_raised_refusal_stages` and
`_COMPUTED` in two; `_challenge_for`, `_grants_of`, `_row_counts`, `_usage_of` and `_auth` across the
claim and restore modules; and the `apple_linked_identity` fixture is defined twice with the same
name, docstring and body. Each copy is a place the next fix has to be applied by hand — WR-47 above
would have to be fixed twice today, and the 37.2 `WR-86` hygiene-walk fix already had to be applied
to two of the three `_LogSpy` copies.

**Fix:** Move `_LogSpy` / `_spy_on` and the `apple_linked_identity` fixture into `tests/e2e/conftest.py`
beside `FakeDeviceCheckAdapter`; move `_raised_refusal_stages` / `_COMPUTED` into a shared helper
imported by both webhook modules. The row-count helpers differ enough per module to leave alone.

---

### IN-50: the challenge TTL is hard-coded as 299/300 seconds rather than read from the store

**File:** `tests/e2e/test_challenge_store.py:167-175`, `:355-360`

**Issue:** `test_a_row_one_second_from_expiry_still_claims` claims at `now + timedelta(seconds=299)`
and `plant()` writes `expires_at=now + timedelta(seconds=300)`. Both encode the store's TTL as a
literal. If the TTL is shortened the first test fails with a name that has become false ("one second
from expiry"); if it is lengthened the test no longer probes the boundary it is named for and passes
for the wrong reason. Every other module in this set reads its constant from the module under test —
`DEVICECHECK_ATTEMPTS` (`test_claim_anonymous_grant.py:12`), `GOOGLE_ISSUER`/`GOOGLE_JWKS_URL`
(`conftest.py:23-28`), `GRACE_STATE` (`test_restore_subscription.py:12`).

**Fix:** Import the store's own TTL constant and derive both values from it
(`now + CHALLENGE_TTL - timedelta(seconds=1)`, `now + CHALLENGE_TTL`), or take `expires_at` from the
`issue()` return the fixture already discards at `:170`.

---

### IN-51: the profile happy path only ever sees NULL `email` and `display_name`

**File:** `tests/e2e/test_users_me.py:55-68`

**Issue:** `seed_identity` (`conftest.py:545-566`) constructs `User(active=user_active)` and never
populates `email` or `display_name`, so every e2e profile assertion reduces to
`{"email": None, "display_name": None}`. A handler returning two hard-coded `None`s passes the whole
module, including the "whole body, not three known keys" literal at `:65-68`. The values are proven
only at unit level (`tests/unit/test_users_me.py:32`, `:70-77`), which is why this is Info and not a
Warning — but the e2e file reads as if it covers them.

**Fix:** Give `seed_identity` optional `email` / `display_name` keywords defaulting to `None`, and
have the happy-path case seed distinguishable values so the readback is non-trivial.

---

### IN-52: two `httpx.AsyncClient` objects are constructed per test and never closed

**File:** `tests/e2e/conftest.py:427`, `:528`

**Issue:** `real_google_play_seam` and `unconfigured_google_play` build
`httpx.AsyncClient(transport=httpx.MockTransport(...))` inline and restore the previous
`state.play_subscriptions` on teardown without closing the client they created. Both fixtures are
function-scoped and used by several dozen cases across `test_google_play_webhook.py` and
`test_restore_subscription.py`, so one unclosed client accumulates per test. `MockTransport` opens no
socket, so this leaks objects rather than file descriptors — but every other seam in this file is
torn down symmetrically, and this is the exception.

**Fix:** Build the client with `async with`, or close it in the `finally` beside the restore:

```python
    finally:
        (…) = original
        await _app_lifespan.state.play_subscriptions.client.aclose()
```

---

### IN-53: `_seed_subscription_grant` re-implements `conftest.seed_subscription` and has already diverged

**File:** `tests/e2e/test_claim_registered_grant.py:117-139` vs `tests/e2e/conftest.py:625-649`

**Issue:** Both write a raw `INSERT INTO core.subscriptions`. The local copy hard-codes `'apple'`,
`'registered'` and `'active'` as SQL literals rather than casting bound parameters, and omits
`last_cross_account_transfer_month` — the column `conftest.seed_subscription` was extended with for
the restore module. The docstring's justification ("`seed_grant` cannot carry the id") explains why a
*grant* helper is needed, not why the subscription INSERT is duplicated.

**Fix:** Call `seed_subscription(factory, external_id=…, user_id=user_id, tier_id="registered")` for
the row, then add the `AccessGrant` + `UserMonthlyUsage` pair around the id it returns.

---

### IN-54: `test_users_me.py` imports a private helper from a sibling test module

**File:** `tests/e2e/test_users_me.py:12`

**Issue:** `from .test_sync import _stored_provider` couples the two modules at collection time —
importing `test_sync` executes its module body (including the `text()` statement constructions at
`:51-58`) whenever `test_users_me` is collected, and an underscore-prefixed name crossing a module
boundary signals that the helper has outgrown its home. `apple_linked_identity` is then duplicated
between the same two files (IN-49) rather than shared the same way, so the coupling is not even
consistent.

**Fix:** Move `_stored_provider` to `tests/e2e/conftest.py` as `stored_provider` alongside
`seed_identity`, and import it from there in both modules.

### IN-62: `_Harness.owned_user_ids` is dead in the create-race harness

**File:** `tests/schema/test_create_race.py:36`, teardown at `:59-61`

**Issue:** `owned_user_ids: list[uuid.UUID] = field(default_factory=list)` is declared and read in
the teardown (`{*subject.owned_user_ids, *(row[0] for row in rows)}`), but nothing in the module ever
appends to it — unlike its twin in `test_create_atomicity.py:82,350`, which does. The teardown
therefore only deletes users reachable through a surviving identity row, and reads as if it also
sweeps orphans it never sees. Harmless today (a losing attempt's user row rolls back), but it makes
the cleanup look broader than it is.

**Fix:** Delete the field and the `{*subject.owned_user_ids, ...}` union, or append in the places
that commit a user directly.

### IN-63: The anonymous writer's lock-tier count is captured only on the arm that writes nothing

**File:** `tests/schema/test_grant_locks.py:286-341` (fixture), `:344-379` (assertions)

**Issue:** `activation_statements` seeds a held `manual` grant, so
`activate_anonymous_device_grant` returns `ActivationOutcome.refused` — which
`test_the_identity_row_is_revalidated_by_a_plain_re_read` asserts at `:375-379`, along with "the
writer must stop at the held grant and write nothing". Every assertion in
`TestTheActivationAddsNoThirdLockTier`, including `len(set(taken)) == 2` and
`"core.external_identities" not in taken` (`:361-367`), is therefore measured on the refusal arm
only. Its registered twin deliberately captures both arms (`conversion_statements` and
`new_grant_statements`, `:471-482`).

Today the locking prefix in `grants.py:155-159` runs unconditionally before every branch, so the
activating arm cannot differ — which is why this is INFO and not a Warning. But the regression the
class names ("a writer that locks the identity or user row first fails here, not in production")
would go unseen if it were introduced after the branch, on the arm that actually writes.

**Fix:** Add a clean-account fixture in the shape of `new_grant_statements` and run the same three
assertions against `ActivationOutcome.activated`.

### IN-64: Setup outside the `try` leaks a connection and a tier row into the shared scratch database

**File:** `tests/schema/test_subscription_ingestion.py:728-748`

**Issue:**

```python
conn = await asyncpg.connect(_schema_db_uri)
tier_id = await insert_tier(conn)
user_id = await insert_user(conn)
try:
    ...
finally:
    await _clean(conn, user_id=user_id, tier_id=tier_id)
    await conn.close()
```

`insert_tier` and `insert_user` run before the `try`, on an autocommitting connection. If
`insert_user` raises, the connection is never closed and the committed `core.access_tiers` row is
never cleaned — and `_schema_db_uri` is session-scoped, so the leftover survives for every later
module. Every other fixture in the suite (`_buyer`, `_account_holding`, `committed_grant`,
`_registered_writer_run`) puts its seeds inside a `try`/`finally` pair.

**Fix:** Open the connection, then do both inserts inside the `try`.

### IN-65: `DROP DATABASE ... WITH (FORCE)` on a fixed name destroys a concurrent suite run

**File:** `tests/schema/conftest.py:60-69`, `:18`, and `tests/schema/test_apply_rollback.py:12`

**Issue:** The session fixture unconditionally issues `DROP DATABASE IF EXISTS ns_schema_test WITH
(FORCE)` before `CREATE DATABASE`. `WITH (FORCE)` terminates other sessions' backends. Two schema
runs against one PostgreSQL — two terminals, two CI jobs on a shared instance, or any future move to
`pytest-xdist` (each worker gets its own session-scoped fixture) — will FORCE-drop each other's
database mid-run, producing failures that look like schema defects. The same applies to
`ns_schema_test_rollback`.

**Fix:** Suffix the scratch names per run, e.g.
`SCHEMA_TEST_DB = f"ns_schema_test_{os.getpid()}"`, or gate on an advisory lock taken against the
maintenance database.

### IN-66: A disjunction in the restore race that cannot discriminate

**File:** `tests/schema/test_restore_race.py:352-356`

**Issue:**

```python
assert loser.sqlstate in (None, "23505")
assert (loser.integrity_at_flush, loser.integrity_at_commit) == (False, False)
```

`sqlstate` is only ever assigned inside the two `except IntegrityError` handlers
(`:120-123`, `:128-131`), and each of those handlers runs only after `_RacingSession` has already set
`integrity_at_flush` or `integrity_at_commit`. The second assertion therefore forces
`sqlstate is None`, making the `in (None, "23505")` disjunction unreachable in its `"23505"` leg —
the case cannot distinguish "no violation" from "the right violation", which is what its docstring
claims it does.

**Fix:** Keep the flags assertion and state the outcome plainly:
`assert loser.sqlstate is None, "the conditional UPDATE, not an index, must be what refused"`.

### IN-67: A case description that disagrees with the path it exercises

**File:** `tests/schema/test_subscription_ingestion.py:368-383`

**Issue:** The class docstring says "Same term is a no-op reached before any write", and the case is
named `test_the_same_term_writes_nothing_to_either_table`. `SubscriptionsService.ingest` has no
same-term early return: the second delivery carries a fresh `notification_uuid` (default at
`test_subscription_ingestion.py:59`), so it falls through to
`subscriptions_db.append_event(...)` (`services/subscriptions.py:173-180`) and **does** write one
`audit.subscription_events` row. The case's assertions only cover `core.access_grants` and
`core.user_monthly_usage`, so they are correct — but the description points a reader at a write path
that is not the one under test, and nothing here asserts what the event table did.

**Fix:** Rename to `test_the_same_term_changes_no_grant_and_no_counter`, drop "before any write" from
the docstring, and add the missing observation:
`assert await buyer.events_under(second_uuid) == 1` (the event row is appended, the entitlement is
not touched).

### IN-68: `insert_usage` defaults `monthly_period` to a literal month that is now in the past

**File:** `tests/schema/helpers.py:113-128` (the default at `:117`)

**Issue:** `monthly_period: str = "2026-08"` is a fixed literal with no relationship to the
evaluation instant any caller uses. Callers that seed with the default and then drive a writer at
`datetime.now(UTC)` — `test_grant_locks.py:109`, `:298`, `:429`, `:622`, `:805` and
`test_subscription_ingestion.py:84` — are now seeding a *past* period. `SyncService.read_entitlement`
resolves that as a rollover (`services/sync.py:57`: `used = 0 if usage.monthly_period < period else
usage.monthly_used`), so any case that seeds a non-zero count with the default and reads it back
through sync or quota will see `0` and pass for the wrong reason. Today no caller does — every case
that cares about the counter passes an explicit period (`test_claim_race.py:482`,
`test_sync_lock_freedom.py:66`) — but the default is a trap that gets worse every month.

**Fix:** Derive it, and make callers state the instant they mean:

```python
async def insert_usage(conn, *, grant_id, monthly_period: str | None = None, monthly_used: int = 0):
    # Derived, never a literal: a fixed month drifts into the past and reads back as a rollover.
    monthly_period = monthly_period or datetime.now(UTC).strftime("%Y-%m")
```

### IN-72: The `ActiveGrantOutsideItsTerm` arm is driven but its client answer is never asserted

**File:** `tests/unit/test_claim_precedence.py:637-639` (setup), `:673-675` (registration),
`:681-691` (the only case that runs it); mirrored at
`tests/unit/test_claim_precedence_registered.py:563-567` and `:601-604`

**Issue:** `_marked_outside_its_term` exists specifically to reach
`services/auth.py:197 → raise ActiveGrantOutsideItsTerm`, but its only consumer is
`TestTheConsumptionCounterIsOneForEveryPostClaimOutcome::test_each_outcome_consumes_exactly_once`,
which discards the response entirely (`_claim(client)` with no binding) and asserts only
`store.consume_calls == 1` and `store.row.consumed_at is not None`. Every *other* post-claim arm has
a named case pinning status and body — registered claimant, spent slot, prior free grant, other
source held, repeat, device spent, proof refused, budget exhausted, race lost, refused write,
lost-race-empty, success, and the two-grant tripwire. This one does not, in either suite. The arm
answers correctly today (`ActiveGrantOutsideItsTerm` → 403 `operation_not_allowed`, verified), but a
remap to 200 or 500 would leave both suites green.

**Fix:** Add the missing named case beside its siblings:

```python
def test_a_grant_marked_active_outside_its_term_is_refused_and_still_consumes(
        self, client, store, account, grants, devicecheck):
    """The one-active index's own question: a row the effective read cannot see still blocks."""
    identity_row, _ = account
    grants.marked_active = [_a_grant(AccessGrantSource.anonymous_device_grant)]
    store.row = _issued_row(bound_to=identity_row.id)

    response = _claim(client)

    assert response.status_code == 403
    assert response.json() == REFUSED
    assert store.consume_calls == 1
    assert grants.activates == 0
    assert devicecheck.read_calls == []
```

### IN-73: `undeclared()` excuses every intermediate class, including ones that are raised directly

**File:** `tests/unit/error_tree.py:29-41`

**Issue:** `undeclared()` skips any class with subclasses (`if cls.__subclasses__(): continue`,
`:33-35`) on the stated ground that "an intermediate base answers through its leaves". Two
intermediates today declare neither `status` nor `code` — `AnalysisError` and `ProviderLookupError` —
and `AnalysisError` is raised **directly** at `src/nativespeaker/api/services/chats.py:75`. It
therefore answers the base's fail-closed 500 `internal_error`, which is the right answer here, but
`assert_tree_total()` reports nothing about it either way, so the checker's promise ("Leaves that
would answer the root's fail-closed default") is narrower than the tree it is asked to make total.

**Fix:** Either narrow the docstring to say the check covers leaves only, or count directly-raised
intermediates too, e.g. by also flagging an intermediate whose module tree contains a
`raise <ClassName>` and that declares nothing.

### IN-74: The operation bound is read by positional metadata index

**File:** `tests/unit/test_challenge_endpoint.py:260`

**Issue:** `_OPERATION_LIMIT = ChallengeRequest.model_fields["operation"].metadata[0].max_length`
assumes `metadata[0]` is the `MaxLen` constraint. It is today
(`[MaxLen(max_length=64)]`, verified), but adding any second constraint — a `min_length`, a pattern —
can reorder the list and turn this into an `AttributeError` at import, which is a collection error
for the whole module rather than a readable failure of the one case that cares.

**Fix:**

```python
_OPERATION_LIMIT = next(c.max_length for c in ChallengeRequest.model_fields["operation"].metadata
                        if hasattr(c, "max_length"))
```

### IN-75: A docstring contradicts the assertion it explains

**File:** `tests/unit/test_exception_handlers.py:214-218`

**Issue:** `test_a_rejection_carrying_no_extra_fields_logs_none` is documented as "The base
contributes `{}`, so nothing rides along that a subclass did not put there" but asserts
`warnings.entries[0][1] == {"exc_info": False}`. The base contributes `exc_info` too. In a suite
whose whole method is prose-as-contract — and where the same `{"exc_info": False}` shape is asserted
again at `:403` and `:419` — a docstring that names the wrong expected value is the kind of drift a
later reader will resolve in favour of the prose.

**Fix:** "`log_fields()` contributes `{}`, so the only field on the line is the handler's own
`exc_info`; nothing rides along that a subclass did not put there."

### IN-76: A control that constructs the value it then asserts

**File:** `tests/unit/test_firebase_adapter.py:304-307`

**Issue:** `test_the_provider_lookup_still_answers_the_401_arm_control` asserts
`"provider_lookup" == UserNotFound(stage="provider_lookup").stage`, which is true for any class that
stores its keyword. As the stated control for WR-29 ("the revocation narrows alone, and spec 11 does
map the read to 401") it carries only its first line, `assert UserNotFound.status == 401`; the second
line adds nothing the sibling cases at `:385-391` do not already establish against a real adapter
call.

**Fix:** Drop the second line, or replace it with the fact the control is actually for — that the
read path still raises `UserNotFound` where the revocation raises `RevocationUnconfirmed`, which
`:288-302` and `:385-391` already prove between them.

### IN-86: The "every service dependency" parametrize list has already drifted from `dependencies.py`

**File:** `tests/unit/test_sync_clock_capture.py:78-95`

**Issue:** `TestTheInstantIsCapturedOnceAndSharedByEveryService` parametrizes over
`("get_sync_service", "get_auth_service", "get_chat_service")`. `dependencies.py` declares
five factories taking `evaluated_at: datetime = Depends(get_evaluated_at)` — the three above
plus `get_subscriptions_service` (`:176-179`) and `get_restore_service` (`:183-190`). The
class name and both docstrings say "every service"; the hand-maintained tuple is a subset,
and it drifted when 43-01 and 45-01 added the two newer factories.

**Fix:** Derive the list instead of writing it down:

```python
def _clock_taking_factories(tree: ast.Module) -> list[str]:
    return [n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("get_") and n.name.endswith("_service")]
```

then parametrize over that, keeping `get_evaluated_at` itself excluded.

### IN-87: The single-derivation guard for `YYYY-MM` recognises one spelling of the format literal

**File:** `tests/unit/test_monthly_period.py:11`, `:44-46`

**Issue:** `FORMAT = '"%Y-%m"'` — the double-quoted literal only. `_files_formatting_a_period`
greps raw file text for that exact string, so `dt.strftime('%Y-%m')` (single quotes) or
`f"{dt:%Y-%m}"` would add a second derivation site and `test_only_the_one_function_formats_a_period`
would still pass. The docstring at `:41` ("Five copies is what let two of them each claim to
be the only one; the claim is now checkable") overstates what is checked. Nothing in `src/`
uses the other spellings today, so this is latent.

**Fix:** Match on the format string without its quoting, e.g.
`FORMAT = "%Y-%m"` plus an explicit exclusion of `"%Y-%m-%d"`, or walk the AST for
`strftime` calls and f-string `FormattedValue` specs rather than grepping text.

### IN-88: A test name promises a cache-header assertion the body does not make

**File:** `tests/unit/test_users_me.py:204-213`

**Issue:** `test_the_refusal_carries_no_cache_header_and_no_identifier` asserts only
`set(response.json()) == {"code"}` and that neither token string appears in
`response.text`. It never reads `response.headers`. A reader scanning names would conclude
the 500 path's caching behaviour is pinned; it is not, and the happy-path
`Cache-Control: no-store` assertion at `:130` does not cover the error path.

**Fix:** Either add the missing assertion or rename the case:

```python
assert "cache-control" not in response.headers
```

### IN-89: `/users/me` only ever sees one `identity_provider`, so a constant would satisfy the suite

**File:** `tests/unit/test_users_me.py:71-80` (`_linked_identity`), `:31-33` (`EXPECTED_BODY`)

**Issue:** Every identity this module builds carries `provider=IdentityProvider.google`, and
`EXPECTED_BODY` hardcodes `IdentityProvider.google.value`. Replacing
`identity_provider=identity.identity.provider` in `src/nativespeaker/api/routers/users.py:27`
with a literal `IdentityProvider.google` leaves 18 of 18 tests passing (verified by
mutation). `SHARED-INVARIANTS.md:7` makes the stored `provider` column the sole per-request
classifier, so a route that stopped reading it is exactly the defect worth guarding.

**Fix:** Parametrize the identity fixture over all three members:

```python
@pytest.mark.parametrize("provider", list(IdentityProvider), ids=lambda p: p.value)
def test_the_body_reports_the_stored_provider_column(self, session, provider):
    identity = _linked_identity()
    identity.identity.provider = provider

    with _client_for(identity, session) as client:
        assert client.get("/users/me").json()["identity_provider"] == provider.value
```

### IN-90: The clock-call walk and the async-synchronisation helper both rest on shapes that are easy to step outside

**File:** `tests/unit/test_sync_clock_capture.py:16`, `tests/unit/test_quota_seam.py:100-112`

**Issue:** Two separate brittle-instrument notes in the phase's own suites.

`CLOCK_CALLS = frozenset({("datetime", "now"), ("datetime", "utcnow"), ("date", "today"),
("time", "time")})` matches only `Name.attr(...)`. It misses `time.monotonic()`,
`datetime.datetime.now()` (whose `func.value` is an `Attribute`, not a `Name`), and any
aliased import such as `from datetime import datetime as dt`. For `sync.py` the companion
case `test_the_datetime_import_is_used_only_as_a_type_annotation` (`:52`) closes most of the
hole; for `dependencies.py` the "exactly one clock call" guard at `:97` does not.

`_take_every_permit` (`test_quota_seam.py:105-110`) decrements `asyncio.Semaphore._value`
directly rather than acquiring, and `_settle` (`:113-116`) yields a fixed ten times as a
substitute for waiting on a condition. Both are CPython-internal / iteration-count
assumptions supporting assertions (`events == ["session_opened", "session_committed",
"session_closed"]`) that would read as a production ordering defect if either assumption
stopped holding.

**Fix:** For the walk, match a resolved dotted name rather than a two-tuple, and add
`("time", "monotonic")` and `("time", "perf_counter")`. For `_settle`, replace the fixed
loop with an `asyncio.Event` the recording session sets on close, awaited under
`asyncio.wait_for`, so the case waits on the condition it means rather than on a tick count.

---

_Reviewed: 2026-09-09T20:00:01Z_
_Reviewer: Claude (gsd-code-reviewer) x7, merged by orchestrator_
_Depth: standard_
