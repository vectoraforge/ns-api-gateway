---
phase: 40-post-auth-upgrade-anonymous
reviewed: 2026-09-09T00:00:00Z
depth: standard
files_reviewed: 139
files_reviewed_list:
  - AGENTS.md
  - config/config.yaml
  - docker-compose.yml
  - Dockerfile
  - .dockerignore
  - .env.example
  - .gitignore
  - k8s/templates/deployment.yaml
  - k8s/templates/httproute-app.yaml
  - k8s/templates/httproute-auth.yaml
  - k8s/templates/httproute-health.yaml
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
  - tests/e2e/test_google_play_webhook.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/e2e/test_sign_out_all.py
  - tests/e2e/test_sync.py
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
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_tables_metadata.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users_me.py
  - tests/unit/test_users.py
  - uv.lock
findings:
  critical: 2
  warning: 31
  info: 38
  total: 71
status: issues_found
---

# Phase 40: Code Review Report

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 139
**Status:** issues_found

## Summary

Re-review of phase 40. Scope is the git diff since the previous `40-REVIEW.md` commit
(`2cb3170`), which is every source and test file the phases that followed have touched —
139 files. The scope was split across seven `gsd-code-reviewer` agents by module,
each holding a disjoint finding-ID block, and merged here without narrowing. Each reviewer
checked `.planning/REQUIREMENTS.md` and the phase decision records (D-nn / A-nn / OQ-n) before
filing, and dropped every candidate a ratified decision had already settled; those drops are
recorded in the per-reviewer summaries below.

Findings: 2 critical, 31 warning, 38 info (71 total).

### Reviewer 1 — infrastructure, deployment, app wiring, config, errors, logging, resilience

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 25 (`uv.lock` inspected for version drift only)
**Status:** issues_found

#### Summary

This group is the application shell: configuration loading, the FastAPI wiring,
the error registry, the log pipeline, the LLM resilience policy, the container
image, the Helm chart, and the single migration. Correctness at the request level
is high — every mutating service commits explicitly, the error tree is closed and
anti-oracle clean, the JWT barrier is not re-derivable from headers, and `ruff`
passes on `src/`. No injection, secret-in-repo, or authorization-bypass defect
was found, and every registered route is covered by exactly one HTTPRoute.

The defects that remain are of two kinds, and both are silent:

1. **Configuration values that cannot be changed where they are meant to be
   changed.** `config/config.yaml` is `init_settings`, so it outranks the
   environment for every key it declares. It declares `log_level` and
   `db.pool_size`. Both are per-deployment settings, and both silently ignore the
   environment and the chart's `env` escape hatch (WR-02, WR-03). Conversely,
   `OPENAI_API_KEY` is boot-blocking but appears in no config model and no chart
   documentation, so an operator following `k8s/values.yaml` literally ships a
   crashloop (WR-04).
2. **Failure paths that run after the answer has already left.** `get_db` commits
   in the dependency teardown, which FastAPI runs after the response body is on
   the wire — verified empirically. A handler that forgets its own commit returns
   `200` for a transaction that rolls back, with no exception reaching the client
   (WR-01).

Findings marked "empirically verified" were reproduced against this repository's
`.venv` (fastapi 0.135.1, pydantic-settings 2.13.1, structlog 25.5.0), not
inferred from reading.

Nothing here contradicts a ratified decision. Phase 35 D-05/D-07 (no backend rate
limiting, `rate_limited` stays registered), Phase 37.5 D-11 (the breaker and the
gate stay, costed at `pool_size: 5` / `queue_size: 25`), Phase 40 D-11 (the
shrunken `core.auth_operation`), and `req~schema-ddl-as-written~1` (the DDL
fence, including its `DEFAULT CURRENT_TIMESTAMP` columns) were all checked and
the candidate findings they settle were dropped before filing.

### Reviewer 2 — auth/ adapters and schemas/

**Reviewed:** 2026-09-09T22:30:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

#### Summary

Group 2 covers the seven provider-adapter modules under `auth/` and the four
Pydantic schema modules. The adapters are dense and heavily commented, and most
of the obvious hazards are already closed: path segments are escaped and
dot-guarded, out-of-range store stamps fail closed, the DeviceCheck key is
parsed at boot, and no adapter that handles an attribution token holds a logger.

The one blocker is a cross-module type hazard that these files own: the
`term_end_for(status, term)` helper takes the status and the term from two
independent arguments, and `services/restore.py` supplies them from two
different sources. Combined with `app_store.py`'s unconditional
`grace_period_expires_at=None`, an entitled Apple subscriber whose canonical row
reads `grace_period` is refused their restore every time.

The warnings are dominated by two DeviceCheck classification defects and two
findings Phase 41's review already recorded as **open, not resolved**
(`REQUIREMENTS.md:38` names them by ID). They are still live in the code under
review, so they are re-filed here with their prior IDs cited.

Ratified decisions checked and NOT filed: the Google replay key being a
payload-derived composite rather than `message.messageId` (Phase 44 OQ-4,
`REQUIREMENTS.md:438`); the webhook routes answering the shared one-field error
body rather than a bare status (Phase 43 D-04 / Phase 44 D-20); the single
`device_token` field replacing the spec's two tokens (Phase 41 code review,
`REQUIREMENTS.md:339`); iOS-only device gating (Phase 41 D-01).

### Reviewer 3 — crud/ and tables/

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

#### Summary

The eleven files in this group are the persistence layer for the entitlement,
identity and store-subscription work. I traced the lock order in
`crud/grants.py` and `crud/subscriptions.py` against SHARED-INVARIANTS lines
33-44 and against the DDL in `migrations/20260818_01_initial-release.sql`, and
the order holds: every path takes `core.access_grants` rows `FOR UPDATE`
ascending by id before any `core.user_monthly_usage` row, and no path takes an
account-row lock ahead of the grant tier. `_effective_grants_statement` matches
the shared effective predicate exactly. `is_unique_violation` reads
`orig.sqlstate`, which SQLAlchemy's asyncpg adapter does populate on the
translated error, so the classification is sound. Every chat read is scoped by
`user_id`, so there is no IDOR in `crud/chats.py`. `ruff` and `ty` are clean.

I found no BLOCKER. The four warnings are all fail-open or
misclassification seams: a lost race on the provider-account unique index is
reported to the client as the wrong conflict; `lost_race` is returned from
`activate_registered_account_grant` in states where the caller's re-read cannot
tell a winner from a no-op; `write_subscription_grant` silently takes the last
matching usage row instead of failing closed; and
`activate_anonymous_device_grant` is the one grant-locking site in the codebase
that drops a `None` usage row on the floor.

#### Structural Findings (fallow)

No `<structural_findings>` block was supplied for this part. The unused-symbol
observations below (IN-40, IN-41, IN-45) were derived by direct reference
counting over `src/` and `tests/`.

#### Narrative Findings (AI reviewer)

### Reviewer 4 — routers/ and services/

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

#### Summary

Reviewed the seven router modules and seven service modules against
`specs/auth-refactor-phases/SHARED-INVARIANTS.md`, `05-upgrade-anonymous.md`,
`10-restore-subscription.md`, and the ratified decision records in
`.planning/phases/40-*`, `41-*`, `42-*`, `43-*`, `45-*`.

The completion sequence in `services/auth.py::_complete`, the challenge lifecycle, the
grant lock ordering (`lock_active_grants` → `lock_effective_grants` → `lock_usage`,
ascending, consistent across `GrantsDB`, `SubscriptionsDB.lock_grants_of` and
`QuotaService.charge`), the restore/ingest race classification, and the fail-closed
providerData classifier all hold up under trace. Two findings survive; four are quality
items.

**Findings dropped after the mandatory pre-filing check** (recorded so a later reviewer
does not re-file them):

- `RestoreService.restore` never rejects an anonymous destination, contradicting
  `10-restore-subscription.md:50`. Settled by **Phase 45 D-\<anonymous-gate\>**
  (`45-CONTEXT.md:50-54`): `restore_destination_anonymous` is deliberately not built.
- `_apply_upgrade` re-checks only `provider` under the lock, not `identity_state` /
  `users.active`, contradicting `05-upgrade-anonymous.md` step 8. Settled and waived as
  **ledger window 12** (`40-UAT.md:19`).
- No client-supplied target `provider` at prepare or completion, contradicting
  `05-upgrade-anonymous.md` steps 3–4. Settled by **Phase 40 D-01**.
- Any linked caller can obtain a `claim_*_grant` challenge with no endpoint to spend it
  at. Settled by **Phase 40 D-11** ("Accepted cost").
- `read_event` (the replay short-circuit) runs after `lock_grants`, so a pure replay still
  takes locks and can 500 on `MissingUsageRowError`. Settled by
  **43-04-SUMMARY.md:181** — the ordering is deliberate so no token read happens under a lock.
- `audit.subscription_events.old_tier_id` is taken from the pre-lock read
  (`services/subscriptions.py:53`) rather than the under-lock `settled` row. Already filed
  as **IN-41 in `39-REVIEW.md`** and explicitly declined in `39-REVIEW-FIX.md:106-107`.
- The DeviceCheck bit0/bit1 read-then-write window lets two concurrent claims from one
  device on two accounts both pass. Structurally mandated by SHARED-INVARIANTS
  ("No provider ... network call may run while any DB lock is held"); not fixable in
  this design.

#### Narrative Findings (AI reviewer)

### Reviewer 5 — tests/unit (conftest .. test_firebase_retry)

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 24
**Status:** issues_found

#### Summary

Twenty-four unit test files, reviewed against the test-reliability contract only: wrong
expectations, tautological assertions, missing assertions, order dependence, leaking fixtures,
and names that promise more than the body checks. Style was not reviewed.

Empirical baseline established before filing: all 666 cases pass together
(`uv run pytest <the 24 files> -q` → 666 passed in 12 s) and every file also passes **alone**,
so there is no cross-file order dependence in this group. `pytest-randomly` is not installed,
so ordering is deterministic. `asyncio_mode = "auto"` makes the bare `async def` cases real.
`tests/unit/__init__.py` exists and `tests/` is on `sys.path`, so the two import spellings in
use (`from .conftest import …` and `from unit.conftest import …`) resolve to the same module
object — no duplicated-fixture hazard.

The suite is unusually strong: nearly every structural guard carries an explicit control case
that proves the walk is not silently empty, the two claim-precedence modules share one fake of
the only serialization point rather than drifting copies, and `_FixedKeyVerifier` imports
production's algorithms, leeway and options instead of restating them.

What survived that scrutiny is one **proven no-op test** (WR-70, verified by executing the
helper against the live `.env.example`), one **structural guard whose docstring claims coverage
it cannot have** (WR-71, verified by executing the import in a fresh interpreter), and one
**security-relevant assertion that exists only in the e2e suite the default `addopts`
deselects** (WR-72). The five INFO items are narrower holes in otherwise sound guards.

Two candidate findings were dropped after the mandatory ratified-decision check:
- The DeviceCheck read-then-write carry-forward that `test_the_other_bit_is_carried_forward_rather_than_fabricated`
  pins in both claim suites. Spec 06 §74 and spec 01 §390 say the anonymous transaction "must not
  touch bit1", and a carried write does touch it (and can lose a concurrent registered claim's
  update). This was settled by **WR-69** (`.planning/phases/38-post-auth-sync/38-REVIEW-FIX.md:792-814`,
  with a recorded mutation proof) and by **37.1 WR/CR** on the same lines; it is current code, not
  a regression, so it is not re-filed here.
- The split `query_token` / `update_token` body that spec 06 §43 describes and
  `test_a_body_naming_no_device_is_rejected_before_the_gate` now rejects with 422. Settled by
  **WR-70 of phase 38** (`tests/unit/test_claim_precedence.py:631`).

### Reviewer 6 — tests/unit (test_google_play_notifications .. test_users)

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 27 (all test files; reviewed for test reliability and correctness only)
**Status:** issues_found

#### Summary

All 27 files collect and pass, both together (`1672 passed`) and each on its own, so
nothing here is order-dependent in the sense of failing. The defects are the opposite
kind: guards that cannot fail.

Every finding below was reproduced, not inferred. One is a proven tautology — a group of
assertions written to protect against user phrases reaching the `openai` DEBUG log cannot
detect that guard being deleted, because the fixture that claims to restore logger state
restores only the root logger. Three more are guards whose promise is wider than what they
measure: two AST walks that match exactly one spelling of the thing they forbid, and a
"bound off by one" control that never goes near the bound. One is a pair of classes named
and documented for a log line that is asserted nowhere in the tree.

The remaining files are strong. `test_quota_resolver.py`, `test_sync_resolver.py`,
`test_subscription_attribution.py` and `test_restore_proof.py` in particular pair almost
every claim with a discriminating control, and the bound-value assertions
(`_bound(statement) == [USER_ID]`) close the "the entity is not the key" hole properly.

#### Narrative Findings (AI reviewer)

### Reviewer 7 — tests/e2e and tests/schema

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 26
**Status:** issues_found

#### Summary

Twenty-six test files across the `e2e` and `schema` suites. They cover phases 41–46 (claim-anonymous-grant, claim-registered-grant, both store webhooks, restore-subscription, sign-out-all) plus the schema-conformance rework, roughly 7 600 added lines.

I ran both suites against the live PostgreSQL on `localhost:5432` to verify the claims below rather than infer them:

- `tests/schema` — 249 passed in 27 s.
- The six in-scope e2e modules that do not need network — 167 passed.
- Each schema module run alone also passes, so the shared session-scoped scratch database does not introduce cross-module order dependence today.

The race harnesses (`test_claim_race.py`, `test_restore_race.py`, `test_subscription_race.py`) are the strongest work here: they drive the real production writers on two real connections, hold both attempts at a named barrier, and assert the premise ("both attempts saw no grant") before asserting the outcome. The lock-order fixtures in `test_grant_locks.py` read the emitted SQL from a `before_cursor_execute` listener rather than mirroring it, and I confirmed against `crud/grants.py` that both activation writers take the lock tiers unconditionally before branching, so measuring the order on the refused arm is sound.

Findings below are five reliability/maintainability defects and four cosmetic ones. Nothing here blocks the phase: no test asserts a wrong expectation, and I found no test that passes because of a broken premise. The recurring theme is *tests that cannot detect the regression their name promises* — a fake that drops the parameter under test, a parametrisation that repeats one code path three times, and a fixture that leaks a real external resource on an error path the codebase already fixed everywhere else.

**Ratified decisions checked and findings dropped as a result:**

- Phase 41 **D-09** ("A repeat claim answers 200 with the same body as a fresh claim") and **D-13** ("The loser answers 200, as a repeat would") settle the apparent conflict between `TestTheRepeatIsIdempotent` (both claim files) and `06-claim-anonymous-grant.md` step 9, which says an existing active `anonymous_device_grant` "is never idempotent success". Phase 41 **D-19** records that the brief is deliberately not edited. Dropped.
- Phase 41 **D-01** (iOS DeviceCheck only; Android and web deferred) settles the absence of any Play Integrity / Turnstile branch coverage in `test_claim_anonymous_grant.py` and `test_claim_registered_grant.py`. Dropped.
- Phase 38 **D-01/D-03** and Phase 37.1 **D-01** (the `audit.auth_events` table and its writer were removed) settle the absence of audit-row assertions that `06`/`07`/`10`/`11` require. Dropped.
- Phase 35 **D-05/D-08** (rate-limit engine deleted, Envoy entries deferred to v2.1) settle the absence of any `claim_*_prepare` / `claim_*_ip` admission-limit case. Dropped.
- Phase 39 **WR-90** (assert the status each quota case is about) and **WR-91** (open the fixture `try` where the resource starts existing) are current code, not regressions — WR-110 below is a *remaining* instance of the WR-91 rule, not a re-flag of the fixed one.

## Critical Issues

### CR-20: `term_end_for` reads the term field chosen by a status from a different object, so an Apple grace-period restore is always refused

**File:** `src/nativespeaker/api/auth/store_notifications.py:62-67`
(with `src/nativespeaker/api/auth/app_store.py:191-192` and the call site
`src/nativespeaker/api/services/restore.py:112`)

**Issue:** `term_end_for` takes `status` and `term` as two independent
parameters and picks a field of `term` based on a value it never checks came
from `term`:

```python
def term_end_for(status: SubscriptionStatus,
                 term: VerifiedNotification | RestoredSubscription) -> datetime | None:
    return (term.grace_period_expires_at if status is SubscriptionStatus.grace_period
            else term.expires_at)
```

`services/restore.py:61` sets `status = proof.status if stored is None else
stored.status` — the **stored row's** status when a canonical row exists — and
then `restore.py:112` calls `term_end_for(status, proof)` with the **proof's**
term. The two disagree whenever a canonical row moved and the proof reports a
different lifecycle word.

Traced end to end on the Apple path, where it fires unconditionally:

1. An Apple purchase carrying no `appAccountToken` (offer-code redemption, Ask
   to Buy, store-managed resubscription) is ingested unclaimed:
   `core.subscriptions.user_id` NULL, no grant row (spec 08, unattributed case).
2. Billing fails; a later notification moves that row to `grace_period`.
   `grace_period` is in `ENTITLED_STATUSES`, so nothing else changes.
3. The buyer signs in and calls `POST /auth/restore-subscription` with the
   signed transaction. `AppStoreNotifications.verify_transaction` returns a
   `RestoredSubscription` whose `grace_period_expires_at` is **hard-coded to
   `None`** (`app_store.py:191-192` — "Apple's grace window lives in the renewal
   payload, which this proof does not carry"), and whose `status` can only ever
   be `active`, `expired` or `revoked` (`_transaction_status`, `app_store.py:57-65`).
4. In `restore`: `stored` is not None, so `status = stored.status = grace_period`
   and the `ENTITLED_STATUSES` check at `restore.py:63` passes.
5. `marked_active` holds no grant with `grant.subscription_id == stored.id`
   (there is no grant — step 1), so `recorded_term` is empty.
6. `term_end_for(grace_period, proof)` returns `proof.grace_period_expires_at`,
   which is `None`, so `restore.py:113` raises `RestoreSubscriptionNotEntitled`.

The subscriber is refused a paid entitlement the canonical row says they hold,
permanently — every retry takes the same branch.

The same defect is reachable on the Play path with the opposite drift: a
subscription that recovered from grace before its RTDN landed has
`stored.status == grace_period` while `read_for_restore` sets
`grace_period_expires_at = None` (`google_play.py:341,354`, because
`in_grace` is False for the live `SUBSCRIPTION_STATE_ACTIVE` read), so an
adoption or a post-supersession restore is refused the same way.

**Fix:** make the helper read the status of the object it is given, so the two
can never be sourced apart, and let the caller pass the stored status
explicitly only where that is the intent:

```python
def term_end_for(term: VerifiedNotification | RestoredSubscription) -> datetime | None:
    """The end of the term this artifact's own status is in."""
    return (term.grace_period_expires_at
            if term.status is SubscriptionStatus.grace_period
            else term.expires_at)
```

`services/subscriptions.py:116-121` already passes `notification.status`, so it
is unaffected. `services/restore.py:112` becomes `term_end_for(proof)`, which
reads the proof's own term for the proof's own status — the value the artifact
actually carries. If the stored status must still gate entitlement (the D-06
rule at `restore.py:60`), keep that check where it is and derive the term from
the proof alone; do not cross them.

### CR-90: The quieted-library assertions cannot fail — the reset fixture restores only the root logger

**File:** `tests/unit/test_logging.py:22-33` (fixture), `:244`, `:251-259`, `:272-283` (the inert assertions)

**Issue:**
`_reset_logging` is documented as "Save and restore logger state around each test", but it
snapshots and restores only `logging.getLogger()` — its handlers and its level.
`setup_logging` also mutates nine *named* loggers:

```python
# src/nativespeaker/api/logs.py:63-64
for name in _QUIETED_LIBRARIES:
    logging.getLogger(name).setLevel(logging.WARNING)
```

Those nine levels are never restored. `test_console_output_always_active` (line 41) is the
first test in the file and calls `setup_logging(log_level="INFO")`, which pins all nine to
WARNING for the rest of the process. Every later assertion about them therefore reads a
level a previous test set, not a level the call under test set.

Reproduced two ways.

Leak, measured by a probe test appended to the same session:

```
levels leaked out of test_logging.py: {'httpx': 30, 'httpcore': 30,
 'sqlalchemy.engine': 30, 'openai': 30, 'langchain': 30, 'langchain_core': 30,
 'urllib3': 30, 'google.auth': 30, 'uvicorn.access': 30}
```

Tautology, measured by deleting the guard and re-running the assertions verbatim:

```python
def test_quieting_assertions_survive_the_quieting_being_deleted(monkeypatch):
    setup_logging(log_level="INFO")                        # what line 41 does first
    monkeypatch.setattr(logs, "_QUIETED_LIBRARIES", ())    # the regression
    setup_logging(log_level="DEBUG")                       # what line 256 does
    for name in _QUIETED_LIBRARIES:
        assert logging.getLogger(name).getEffectiveLevel() >= logging.INFO
    assert not logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO)
# 1 passed in 0.16s
```

So `test_third_party_loggers_suppressed` (:244), the nine parametrisations of
`test_a_quieted_library_stays_quiet_at_debug` (:256),
`test_uvicorn_writes_no_access_line_at_the_configured_level` (:276) and
`test_it_stays_silent_when_an_operator_raises_the_level_to_debug` (:281) all stay green
with the quieting removed entirely. The class docstring at :251 states what that costs:
"`openai` logs the whole chat-completion body at DEBUG — the system prompt, the user's
phrase and the chat's history". That is the one content-leak guard in the file, and it is
inert.

The leak is also live for the rest of the run: after `test_logging.py` every one of those
nine loggers stays at WARNING for every later test in the session.

**Fix:** snapshot and restore the levels `setup_logging` writes, not just the root's.

```python
@pytest.fixture(autouse=True)
def _reset_logging():
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    # Every logger setup_logging writes to, so a level it set cannot outlive the test
    # that set it -- which is what made the quieting assertions unable to fail.
    original_levels = {name: logging.getLogger(name).level
                       for name in (*_QUIETED_LIBRARIES, "nativespeaker.api")}
    _uncache_module_logger()
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()
    _uncache_module_logger()
    for name, level in original_levels.items():
        logging.getLogger(name).setLevel(level)
    root.handlers = original_handlers
    root.setLevel(original_level)
```

With that restore in place, confirm each of the four tests above now fails when
`_QUIETED_LIBRARIES` is emptied — otherwise the fix is not done.

## Warnings

### WR-01: `get_db` commits after the response body is sent, so a failed commit answers 200

**File:** `src/nativespeaker/api/app/dependencies.py:44-51`

**Issue:** `get_db` is an async-generator dependency with the default scope, so
FastAPI enters it on `request.scope["fastapi_inner_astack"]`. In
`fastapi/routing.py:112-118` that stack is exited *after*
`await response(scope, receive, send)` — the teardown runs once the response
body is already on the wire.

Verified empirically against this repo's `.venv`:

```
200 ['handler', 'response-body-sent', 'teardown-commit']
```

and, with the teardown raising, the client still receives `200 {"ok":true}`
while the transaction rolls back — the registered `Exception` handler never
produces a body, because the response has already started.

Today no route depends on this: `ChatService`, `AuthService`, `SyncService`,
`SubscriptionsService` and `RestoreService` all commit explicitly, and
`routers/auth.py:72-74` carries a comment saying exactly why it must. That is the
problem — the hazard is live, undetectable in test (a forgotten commit still
returns 200 in the happy path), and the codebase already had to paper over it
once. `services/sync.py:21` even describes the teardown commit as an active write
channel ("a session kept here is a way to write"), which it is, just not one whose
failure any caller can observe.

**Fix:** move the teardown ahead of the response send. FastAPI 0.135 supports
this directly (`fastapi/dependencies/utils.py:669-673` selects
`fastapi_function_astack` for `scope="function"`, and that stack closes before
`await response(...)`):

```python
# routers/*.py, every use site
session: AsyncSession = Depends(get_db, scope="function")
```

Alternatively drop the teardown commit entirely and let it be a rollback-only
guard, making the explicit commit in each service the sole write channel:

```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

### WR-02: `config.yaml` pins `log_level`, so `LOG_LEVEL` is silently ignored in every environment

**File:** `config/config.yaml:1`

**Issue:** `config/config.yaml` reaches `AppConfig` as `init_settings`
(`config.py:180`), and pydantic-settings ranks `init_settings` above
`env_settings`. Every key the file declares therefore outranks the environment.
The file's own rule at line 25 says "Add a key here only when it must NOT vary per
deployment" — and line 1 declares `log_level`, the single most
deployment-variable setting the service has.

Verified empirically:

```
log_level: INFO (env said DEBUG)
```

`k8s/values.yaml:84` ships an `env: []` escape hatch that an operator would
reach for during an incident (`--set env[0].name=LOG_LEVEL --set env[0].value=DEBUG`);
`deployment.yaml:81-83` renders it faithfully, and it does nothing. There is no
error, no warning, and `.env.example` never mentions `LOG_LEVEL` at all, so
nothing tells the operator the lever is dead.

**Fix:** delete `log_level` from `config/config.yaml` — `AppConfig.log_level`
already defaults to `INFO` (`config.py:131`) — and document `LOG_LEVEL` in
`.env.example` and `k8s/values.yaml` as the supported override.

### WR-03: `config.yaml` pins `db.pool_size`, so the connection pool cannot be sized per deployment

**File:** `config/config.yaml:18-19`

**Issue:** Same mechanism as WR-02, verified empirically:

```
db.pool_size: 12 (env said 3)
```

Pool size is a function of two things the file cannot see: the Postgres server's
`max_connections`, and `k8s/values.yaml:1 replicaCount`. The engine is built with
`max_overflow=0` (`lifespan.py:178`), so the fleet's ceiling is exactly
`replicaCount * 12` and there is no lever below a rebuild. Scaling to four
replicas against a default `max_connections=100` shared with anything else in the
cluster ends in `FATAL: sorry, too many clients already` — recoverable only by
editing a tracked file and cutting a new image.

`resilience.*` has the same shape, but Phase 37.5 D-11 costed those specific
values deliberately, so they are out of scope here; `db.pool_size` was never
costed against `replicaCount`.

**Fix:** remove the `db:` block from `config/config.yaml` and let `DB_POOL_SIZE`
carry it (the field already defaults to 5, `config.py:34`). The comment at lines
16-17 documents the reasoning and should move to `.env.example` beside the other
`DB_*` variables.

### WR-04: `OPENAI_API_KEY` is boot-blocking but is in no config model and in neither chart list

**File:** `k8s/values.yaml:53-60`, `k8s/templates/deployment.yaml:67-69`, `src/nativespeaker/api/config.py:130-146`

**Issue:** `values.yaml:54-56` names "the six settings the process cannot boot
without: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME and JWT_PROJECT_ID", and
`deployment.yaml:69`'s `required` message repeats that list verbatim. Line 58 then
relegates `OPENAI_API_KEY` to "any other setting the deployment needs", alongside
the DeviceCheck ids — which genuinely are optional and fail closed at 503.

`OPENAI_API_KEY` is not optional. `lifespan.py:184` constructs `LLMService`
unconditionally, and `ChatOpenAI` resolves its key from the ambient environment.
Verified empirically:

```
RAISED: OpenAIError The api_key client option must be set either by passing
api_key to the client or by setting the OPENAI_API_KEY environment variable
```

So the seventh boot-blocking setting is documented as optional, and its absence
is not a pydantic `ValidationError` naming a field but an `OpenAIError` from a
third-party library that names no setting of this application. Every other
credential in this service is a typed field on `AppConfig`; this one is ambient.

**Fix:** declare it, so the failure is a config error like the other six:

```python
class ModelConfig(BaseModel):
    api_key: SecretStr = Field(description="OpenAI API key")   # required, no default
    name: str = Field(default="gpt-4o-mini")
```

pass it to `ChatOpenAI(api_key=...)` in `LLMService`, and add `MODEL_API_KEY`
(or keep `OPENAI_API_KEY` via `validation_alias`) to the six-name list in
`values.yaml:54-56` and `deployment.yaml:69`.

### WR-05: the database engine has no `pool_pre_ping` or `pool_recycle`, so every stale connection costs a request

**File:** `src/nativespeaker/api/app/lifespan.py:178`

**Issue:**

```python
db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
```

`pool_pre_ping` defaults to `False` and `pool_recycle` to `-1` (never). A pod is
long-lived and this product has almost no traffic, so pooled connections sit idle
for hours — exactly the condition under which a managed Postgres idle timeout, a
failover, or a NAT/conntrack expiry silently kills the server side. The next
request to draw that connection raises `asyncpg.ConnectionDoesNotExistError` /
`InterfaceError` out of the CRUD layer. That is not an `AppError`, so it lands on
`generic_error_handler` (`error_handlers.py:77-83`) as an opaque 500 —
and on a chat route it lands *after* `QuotaService.charge` has already committed
a spent credit.

With `max_overflow=0` and `pool_size=12`, up to twelve consecutive requests can
fail this way before the pool has recycled itself, and nothing retries. This point
has not been raised in any prior review (`grep pool_pre_ping .planning/` is empty;
36-REVIEW discussed `pool_timeout` only).

**Fix:**

```python
db_engine = create_async_engine(config.db.url,
                                pool_size=config.db.pool_size,
                                max_overflow=0,
                                pool_pre_ping=True,
                                pool_recycle=1800)
```

### WR-06: `SecurityPolicy.spec.jwt.optional` is silently dropped on Envoy Gateway < v1.2

**File:** `k8s/templates/security-policy.yaml:27-28`, `k8s/templates/NOTES.txt:6-10`

**Issue:** The template's own comment states the requirement — "Requires Envoy
Gateway >= v1.2, which is where `spec.jwt.optional` was added" — but nothing
enforces or surfaces it. CRD structural schemas prune unknown fields silently by
default, so on an older gateway the policy installs green, `helm install`
succeeds, both probes pass, and `optional` is simply gone.

The consequence is the exact failure `NOTES.txt:6-10` promises is prevented: a
request with no `Authorization` header is answered by Envoy's JWT filter with the
plain-text body `Jwt is missing` instead of the shared
`{"code": "auth_required"}` the client's decoder is written against. That is the
single most common error response the product will ever emit, and the only
signal that it is wrong is a client-side parse failure in production.

`k8s/Chart.yaml` declares no `kubeVersion`, no `dependencies`, and no annotation
recording the gateway floor, and `NOTES.txt` does not mention it either.

**Fix:** state the floor where the operator reads it. Add to `NOTES.txt` beside
the SecurityPolicy bullet, and to `k8s/values.yaml` above the `gateway:` block:

```
Requires Envoy Gateway >= v1.2. On an older gateway `spec.jwt.optional` is
pruned without error and an unauthenticated request receives Envoy's plain-text
"Jwt is missing" instead of {"code": "auth_required"}.
```

A `helm` `required`-style guard is not possible here (the chart cannot read the
CRD schema), so the documented floor plus a post-install smoke check on
`curl -s $GW/ | jq -e .code` is the whole fix.

### WR-07: the quota credit is charged before an unbounded wait for a provider permit

**File:** `src/nativespeaker/api/resilience.py:115-119` and `:208-210`, `config/config.yaml:6-13`

**Issue:** `LLMExecutionGate.concurrency()` is `async with self._semaphore` with
no timeout, and `ainvoke` enters it *after* the caller has already committed the
quota charge (`services/chats.py:100-102` charges inside `admission()`, then calls
`ask_llm` → `ainvoke`). `asyncio.wait_for` at `resilience.py:192` bounds the
provider call only, never the permit wait.

At the configured values a permit is held for up to
`retry_max_attempts * timeout_seconds` plus backoff = `3 * 30 + 1.5` ≈ 91.5 s.
With `pool_size: 5` and `queue_size: 25`, thirty requests can be admitted and the
last one waits roughly `(25 / 5) * 91.5` ≈ 457 s for its permit — with a credit
already spent. Envoy's default route timeout is 15 s, so that caller has long
since received a 504 and been charged for nothing.

Phase 37.5 D-11 costed these same numbers, but only for the question it was
asked — whether deleting the breaker would flip the answer from 503 to 429. It
did not consider the charge-before-permit ordering, so this is not settled by it.

**Fix:** bound the permit wait so a request that cannot be served promptly is
refused before it is charged, and make `QueueFullError`'s advice honest:

```python
@asynccontextmanager
async def concurrency(self):
    try:
        await asyncio.wait_for(self._semaphore.acquire(), timeout=self._permit_wait_seconds)
    except TimeoutError as exc:
        raise QueueFullError(self._retry_after_seconds) from exc
    try:
        yield
    finally:
        self._semaphore.release()
```

with `permit_wait_seconds` added to `ResilienceConfig`. Cheaper alternative, if
the wait is to stay unbounded: cut `queue_size` to a value whose worst-case wait
is under the gateway timeout (`queue_size: 5` gives ≈ 91 s; anything above one
wave already exceeds 15 s).

### WR-08: the Apple root certificate path is resolved independently of `config_dir`

**File:** `src/nativespeaker/api/config.py:89-90`, `src/nativespeaker/api/app/lifespan.py:53-57`

**Issue:** `AppStoreConfig.root_certificate_path` defaults to the literal
`"config/certs/AppleRootCA-G3.cer"`, resolved relative to the process working
directory. `EnvironmentConfig.config_dir` (`config.py:160`) is a separate,
independently overridable notion of where the config tree lives, and nothing ties
the two together.

Setting `CONFIG_DIR=/etc/ns/config/` — a supported, documented variable
(`.env.example:2`) — moves `config.yaml`, `prompt.txt` and `examples.yaml` but
leaves the certificate lookup at `./config/certs/...`. `build_app_store_verifier`
then takes the `root.is_file()` arm at line 55, returns `None`, and
`POST /webhooks/app-store` answers 503 `verification_temporarily_unavailable`
for the life of the deployment. The only signal is one
`app_store_configuration_absent` warning at boot, which reads identically to a
deployment that simply has no App Store credentials — and Apple retries into the
void, exactly the invisible-failure shape `.env.example:140-147` warns about for
the Google audience.

**Fix:** derive it, so the two roots cannot diverge:

```python
# config.py — default to None and let EnvironmentConfig fill it
root_certificate_path: str | None = Field(default=None, ...)

# EnvironmentConfig.load_config, before constructing AppConfig
mapping.setdefault("app_store", {}).setdefault(
    "root_certificate_path", str(self.config_dir / "certs" / "AppleRootCA-G3.cer"))
```

Or, at minimum, have `lifespan` log the resolved path on the absent arm so the
two causes are distinguishable.

### WR-20: Every DeviceCheck 400 is a definitive `proof_rejected`, including the never-set body and this service's own body faults

**File:** `src/nativespeaker/api/auth/devicecheck.py:106-122`

**Issue:** two problems on the same three lines.

(a) `_parse_bit_state` calls `_reject_or_retry` **before** it looks at the body:

```python
def _parse_bit_state(response, *, stage):
    _reject_or_retry(response, stage=stage)      # 400 -> ProofRejected, raised here
    body = response.text.strip()
    if body in _NEVER_SET_BODIES:                # never reached for a 400
        return BitState(bit0=False, bit1=False)
```

`_NEVER_SET_BODIES` contains `"Failed to find bit state"`, and the module's own
comment (`devicecheck.py:26`) asserts Apple returns it with HTTP 200. Apple is
also widely observed returning that exact text with **HTTP 400**. If it does,
the eligible first-ever claim — the only case the free grant exists for — is
classified as `ProofRejected` (403 `proof_rejected`) and the anonymous grant
feature never grants anything to anybody. Phase 41's review filed this as WR-02
and `REQUIREMENTS.md:38` records it as still open; it is unfixed.

(b) Even setting (a) aside, `_reject_or_retry` maps *every* 400 to
`ProofRejected`, and Apple's DeviceCheck answers 400 for faults in the request
this service built, not in the device token: "Invalid or missing timestamp"
(`_shared_body` sends `int(datetime.now(UTC).timestamp() * 1000)`, so a pod
clock skew produces it), "Invalid or missing transaction id", and "Missing or
incorrectly formatted device token payload". Spec 06 (`:83`) requires the
opposite mapping: `verification_temporarily_unavailable` for
`native_claim_unavailable`, and "Transient failures must never surface as
`device_grant_exhausted`/`verification_required` unless durable state was
independently observed". A drifted clock currently denies every anonymous claim
with a 403 that tells the client its proof is bad.

**Fix:** read the body first, then classify the status, and reserve
`ProofRejected` for the 400 bodies that name the device token:

```python
_TOKEN_REJECTED_BODIES = frozenset({"Missing or incorrectly formatted device token payload",
                                    "Unable to verify device token"})


def _reject_or_retry(response: httpx.Response, *, stage: str) -> None:
    if response.status_code == 400:
        if response.text.strip() in _TOKEN_REJECTED_BODIES:
            raise ProofRejected(stage=stage, cause="rejected")
        # Our own request, not the caller's token: retry, then 503.
        raise RetryableDeviceCheckError("status 400")
    if response.status_code // 100 != 2:
        raise RetryableDeviceCheckError(f"status {response.status_code}")


def _parse_bit_state(response: httpx.Response, *, stage: str) -> BitState:
    if response.text.strip() in _NEVER_SET_BODIES:
        # Checked before the status, because Apple carries this body on more than one status.
        return BitState(bit0=False, bit1=False)
    _reject_or_retry(response, stage=stage)
    ...
```

### WR-21: Both provider retry budgets have no backoff, so three attempts fire back to back

**File:** `src/nativespeaker/api/auth/devicecheck.py:176-183`,
`src/nativespeaker/api/auth/firebase.py:191-196` and `205-213`

**Issue:** all three `AsyncRetrying` constructions pass `stop` and `retry` but no
`wait`, so tenacity uses `wait_none()`. `DEVICECHECK_ATTEMPTS = 3` and
`FIREBASE_LOOKUP_ATTEMPTS = 3` are therefore spent inside a few milliseconds:
against a transient Apple or Firebase blip the budget buys essentially nothing,
while tripling this service's request rate at exactly the moment the provider is
degraded. This project already knows the pattern — `resilience.py:214` gives the
LLM provider `wait_exponential(multiplier=..., max=...)` from a config field.
Phase 41's review filed this as WR-08; it is unfixed.

Note it also compounds WR-20(b): a 400 that should be retryable would be retried
three times in under a millisecond.

**Fix:** give both helpers a bounded wait, matching `resilience.py`:

```python
from tenacity import wait_exponential

def _retrying(exhausted) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(DEVICECHECK_ATTEMPTS),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(RetryableDeviceCheckError),
        retry_error_callback=exhausted,
    )
```

and the same `wait=` on `lookup_with_retry` and `revoke_with_retry` in
`firebase.py` (which are otherwise byte-identical to each other — see IN-24).

### WR-22: A JWKS endpoint that answers 200 with an unusable key set produces a fleet-wide 401 storm with no operator signal

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:209-219`

**Issue:** the `jwks_endpoint_unreachable` log exists for exactly this
scenario — its own comment says an unnamed JWKS outage "rejects the whole fleet
labelled `bad_signature` and the spike alert reads it as mass forgery" — but it
is gated on `PyJWKClientConnectionError` alone:

```python
except PyJWKClientError as exc:
    if isinstance(exc, PyJWKClientConnectionError):
        logger.error("jwks_endpoint_unreachable")
    elif cache_key is not None and _DEFINITIVE_KID_MISS in str(exc):
        self._record_unknown(cache_key)
    return None, bounded_reason_for(exc)
```

PyJWT raises a plain `PyJWKClientError` — not the connection subclass — for two
reachable endpoint conditions: `"The JWKS endpoint did not return a JSON
object"` (`PyJWKClient.get_jwk_set`) and `"The JWKS endpoint did not contain any
signing keys"` (`PyJWKClient.get_signing_keys`). Both are what a misconfigured
proxy, an HTML error page served at 200, or a botched key rotation looks like.
Neither matches `_DEFINITIVE_KID_MISS`, so both fall straight through to
`bounded_reason_for` → `bad_signature`, and every request in the fleet is a 401
with no log line naming the cause. The constructor's own warm-up wrapper
(`jwt_verifier.py:154-159`) shows the author already knew these two failures are
not `PyJWKClientConnectionError`; the runtime arm was not given the same
treatment.

**Fix:** log the operator line for every `PyJWKClientError` that is not the
definitive key-id miss:

```python
except PyJWKClientError as exc:
    definitive_miss = _DEFINITIVE_KID_MISS in str(exc)
    if not definitive_miss:
        # Connection refused, a non-JSON 200, an empty key set: all one outage to the fleet.
        logger.error("jwks_endpoint_unusable", failure=type(exc).__name__)
    elif cache_key is not None:
        self._record_unknown(cache_key)
    return None, bounded_reason_for(exc)
```

### WR-23: A Firebase record with empty `providerData` but a verified email writes that address onto an anonymous account, and it can never be corrected

**File:** `src/nativespeaker/api/auth/firebase.py:146-149`
(invariant stated at `src/nativespeaker/api/auth/adapters.py:17-18`)

**Issue:** `adapters.py:17-18` states the invariant — "Absent by default because
an anonymous record has no verified address to carry" — and `_read` does not
enforce it. `_resolve_provider` returns `(IdentityProvider.anonymous, None)`
whenever `entries` is empty, but `email=_verified_email(email, email_verified)`
is computed from the same `getUser` response regardless of which arm was taken:

```python
provider, provider_uid = _resolve_provider(entries)
return VerifiedProviderIdentity(provider=provider,
                                provider_uid=provider_uid,
                                email=_verified_email(email, email_verified))
```

Firebase produces `providerData == []` with `email` still populated after a
client unlinks its last provider (`user.unlink('google.com')` clears the
providerData entry; the record-level `email` and `email_verified` persist).
`services/auth.py:315-321` then calls `create_user(provider=anonymous,
provider_uid=None, email=facts.email)`, writing a real address onto a row whose
identity provider is `anonymous`.

The consequence is not cosmetic: `crud/identities.py:155-157` refuses to
overwrite a non-NULL `user.email` (`"A stored address is never overwritten"`),
so when that account later performs a genuine `POST /auth/upgrade-anonymous` to
Google or Apple, `flip_provider` skips the email write and the account keeps the
stale pre-upgrade address forever. `GET /users/me` returns it as
`profile.email`. There is no repair path — `04-users-me.md:53` deletes every
rotation and replacement route.

**Fix:** make the invariant the code's, in the one place that knows the arm:

```python
provider, provider_uid = _resolve_provider(entries)
return VerifiedProviderIdentity(
    provider=provider,
    provider_uid=provider_uid,
    # `None` for the anonymous arm: an account with no provider record has no
    # address this read may attribute to it (`adapters.py:17`).
    email=(None if provider is IdentityProvider.anonymous
           else _verified_email(email, email_verified)))
```

### WR-24: `challenge_id`, `device_token` and the entitlement bodies carry no upper length bound

**File:** `src/nativespeaker/api/schemas/auth.py:31`, `36`, `38`

**Issue:** `CompletionRequest.challenge_id`, `GrantClaimRequest.challenge_id`
and `GrantClaimRequest.device_token` all carry `min_length=1` and no
`max_length`, while every neighbouring field in the same module is bounded and
says why (`operation` at `:18` "Bounded well above every member of
core.auth_operation"; `provider` at `:45`; `restore_proof` at `:47`). The
`device_token` value is forwarded verbatim into the JSON body this service posts
to `api.devicecheck.apple.com` (`devicecheck.py:93`), so an unbounded string is
relayed to a third party at this service's expense and inside its own 8-second
timeout. `challenge_id` is a handle `ChallengesDB` mints at a fixed 22
characters, so anything longer is a guaranteed miss that still costs a store
lookup. Phase 41's review filed this as WR-09 and `REQUIREMENTS.md:38` records
it as still open; it is unfixed.

Envoy's body limit is a different layer and does not bound the field — and there
is no request-body-size middleware anywhere in `src/` (`grep -rn
"max_body\|body_size" src/` returns nothing).

**Fix:**

```python
class CompletionRequest(BaseModel):
    # `ChallengesDB.new_challenge_id` mints 22 characters; the bound is well above it.
    challenge_id: str = Field(..., min_length=1, max_length=64)


class GrantClaimRequest(BaseModel):
    challenge_id: str = Field(..., min_length=1, max_length=64)
    # Bounded well above a real DeviceCheck token, which this value is relayed to Apple as.
    device_token: str = Field(..., min_length=1, max_length=4096)
```

### WR-35: `insert_account` reports a provider-account race as `IdentityAlreadyLinked`

**File:** `src/nativespeaker/api/crud/identities.py:124-134`

**Issue:** The comment on line 132 states "The only uniqueness this insert can
lose is `(issuer, subject)`." That is false. The flush inserts an
`ExternalIdentity` carrying `provider` and `provider_uid`, and the migration
declares a second reachable unique index over exactly those columns:

```sql
CREATE UNIQUE INDEX ix_external_identities_provider_account
    ON core.external_identities (issuer, provider, provider_uid)
    WHERE provider_uid IS NOT NULL;
```

`AuthService.create_user` pre-checks that index with `resolve_provider_account`
(services/auth.py:376-383), but the pre-check is a read outside any lock, so the
routine race — two create-user completions for the same Google/Apple account
under two different Firebase subjects — still lands on this `except`. Both then
get `IdentityAlreadyLinked`, whose remediation routes the client to
`/auth/sync`. `/auth/sync` resolves nothing for a subject that was never
linked, so the loser of the race is handed a dead end instead of
`ProviderAccountAlreadyLinked`, which is the answer 02 step 11 requires and
which `flip_provider` already produces for the same index (line 167).

The `StorePurchaseToken` rows added in the same flush carry a third unique
constraint, `UNIQUE (provider, identity_value)`; a `uuid4` collision there is
not a practical concern, but it is a further counterexample to the comment.

**Fix:** Resolve the conflict rather than assuming it, in the arm that already
knows `provider_uid` is present:

```python
except IntegrityError as conflict:
    if not is_unique_violation(conflict):
        raise
    if provider_uid is not None:
        # The pre-check in `create_user` is racy; this is the losing side of it.
        raise ProviderAccountAlreadyLinked(identity_row_id=None,
                                           stored_provider=provider,
                                           live_provider=provider) from conflict
    raise IdentityAlreadyLinked() from conflict
```

If `ProviderAccountAlreadyLinked` cannot be raised without a row id, roll back
and re-run `resolve_provider_account` / `resolve_existing` on a fresh
transaction and raise whichever conflict the winner actually left behind. Either
way, correct the comment on line 132 — it is load-bearing documentation in this
codebase and it currently asserts something the schema contradicts.

### WR-36: `activate_registered_account_grant` returns `lost_race` where no winner row exists

**File:** `src/nativespeaker/api/crud/grants.py:308-317`

**Issue:** The module's contract for `lost_race` is stated twice — line 84
("Another writer holds the slot, and the caller re-reads the winner's row") and
line 259-260 ("the one row the caller's re-read can answer with"). The final
flush arm (line 316) returns `lost_race` for **any** unique violation, but not
every unique violation this insert can lose leaves a winner's row to read.

The insert holds `FOR UPDATE` on every grant row the user had at lock time. Row
locks do not block inserts, so a concurrent writer — the store webhook's
`write_subscription_grant`, for example — can commit a new `status='active'`
grant for the same user in the window, and this insert then breaches
`ix_access_grants_one_active_per_user` rather than
`ix_access_grants_one_free_grant_per_user_source`. The caller,
`AuthService._settle` (services/auth.py:300-312), distinguishes the two cases
only by "did `read_effective_grants` return anything after the rollback", which
is true in both. So a registered-grant claim that wrote nothing is answered with
HTTP 200 and whatever grant happens to be effective — the caller's own untouched
`anonymous_device_grant` when the rival has not committed, or the rival
subscription grant when it has. The response body is truthful about the
entitlement, but the claim is reported as having succeeded when it did not, and
the client has no signal to retry.

This is a defect in the crud contract, not only in the caller: `lost_race` is
being used for two states that need different answers.

**Fix:** Make the outcome carry which slot was lost, so the caller can answer
each correctly:

```python
except IntegrityError as violation:
    if not is_unique_violation(violation):
        raise
    # Only the lifetime free-grant slot leaves a registered row to read back.
    if await self.holds_grant_of_source(user_id,
                                        AccessGrantSource.registered_account_grant):
        return ActivationOutcome.lost_race
    return ActivationOutcome.refused
```

That read must run on a fresh transaction (the flush failure poisons this one),
so the cleanest shape is a fourth `ActivationOutcome` member — e.g.
`destination_taken` — returned from this arm and resolved by `_settle` after its
rollback. `ActivationOutcome.refused` already routes to `ClaimRefusedUnderLock`,
which is the correct client-visible answer for "another active grant took the
slot".

### WR-37: `write_subscription_grant` takes the last carried usage row instead of failing closed

**File:** `src/nativespeaker/api/crud/subscriptions.py:370-381`

**Issue:**

```python
for grant in superseded:
    if grant.user_id != user_id:
        continue
    usage = await self.grants_db.read_usage(grant.id)
    if usage is None:
        raise MissingUsageRowError(grant.id)
    if usage.monthly_period == period:
        carried = usage.monthly_used
```

`carried` is overwritten on every iteration. The comment on lines 372-373 argues
the loop can match at most one row because
`ix_access_grants_one_active_per_user` allows one active grant per user — but
that index is exactly the invariant every other multi-row site in these two
modules refuses to trust. `crud/grants.py:172-174` and `:236-239` both raise
`MultipleEffectiveGrantsError` as an explicit tripwire for the same condition,
and `services/quota.py:69-72` does it a third time. Here the same broken state
is absorbed silently, and it absorbs it in the fail-open direction: with two
current-period usage rows the loop keeps the **last** one by grant id, so a
lower `monthly_used` erases a higher one and hands the account free credits.
SHARED-INVARIANTS line 40 ("More than one `status='active'` grant is an internal
integrity failure: log and fail closed — no tie-break") makes silent last-wins
the wrong behaviour even as a tie-break.

**Fix:** Fail closed on the same tripwire the sibling paths use:

```python
mine = [grant for grant in superseded if grant.user_id == user_id]
if len(mine) > 1:
    raise MultipleEffectiveGrantsError(len(mine), user_id)
for grant in mine:
    usage = await self.grants_db.read_usage(grant.id)
    if usage is None:
        raise MissingUsageRowError(grant.id)
    if usage.monthly_period == period:
        carried = usage.monthly_used
```

### WR-38: `activate_anonymous_device_grant` discards a missing usage row

**File:** `src/nativespeaker/api/crud/grants.py:157-159`

**Issue:**

```python
grants = await self.lock_effective_grants(user_id, evaluated_at)
for grant in grants:
    await self.lock_usage(grant.id)
```

The return value is thrown away, so `lock_usage` returning `None` — an existing
grant with no `core.user_monthly_usage` row — is tolerated here. Every other
grant-locking site in the codebase treats that state as a broken invariant and
raises: `SubscriptionsDB.lock_grants_of` (subscriptions.py:93-96), the sibling
`activate_registered_account_grant` (grants.py:270-274), `services/sync.py:45-48`
and `services/quota.py:80-82`. SHARED-INVARIANTS line 43 is explicit: "A missing
usage row for an existing grant fails closed — never lazily minted."

Nothing is minted here, and the downstream `sync`/`quota` reads do eventually
raise `MissingUsageRowError`, so the blast radius is bounded. But the failure is
reported from a later request against a different grant id than the one that is
actually broken, which makes the operator-repair path this codebase relies on
strictly harder, and this is the one site where the rule is written down in the
module docstring (lines 1-2) and then not applied.

**Fix:**

```python
for grant in grants:
    if await self.lock_usage(grant.id) is None:
        # Fail closed, never mint: the same rule the registered sibling applies.
        raise MissingUsageRowError(grant.id)
```

### WR-50: The DeviceCheck bit-write swallow is narrower than the fail-open contract it states

**File:** `src/nativespeaker/api/services/auth.py:230-235` and `src/nativespeaker/api/services/auth.py:293-298`

**Issue:** Both grant-claim arms commit the grant, then write the Apple bit under a
comment that promises the write can never become the client's answer:

```python
await self.session.commit()
if wrote:
    # Fail-open by design, and it never becomes the answer: the grant above is durable, so a
    # failure here costs the device bit alone. ...
    try:
        await write_bits_with_retry(self.devicecheck, device_token, bit0=True, bit1=state.bit1)
    except AppError as failure:
        logger.error("devicecheck_bit_write_failed", failure=type(failure).__name__)
```

`except AppError` does not make that promise true. Trace the write path:

- `write_bits_with_retry` (`auth/devicecheck.py:193`) wraps the call in
  `retry_if_exception_type(RetryableDeviceCheckError)`, so **only** that internal marker
  is retried; anything else is re-raised unchanged.
- `AppleDeviceCheck._post` (`auth/devicecheck.py:156-163`) converts **only**
  `httpx.HTTPError` into the marker.
- `_service_jwt` (`auth/devicecheck.py:79-87`) raises `Unavailable` (an `AppError`) for a
  missing key, but otherwise calls `jwt.encode`, whose failures (`PyJWTError`,
  `TypeError`) are neither an `AppError` nor the marker.
- A shared `httpx.AsyncClient` closed during pod shutdown raises
  `RuntimeError("Cannot send a request, as the client has been closed.")`, which is **not**
  an `httpx.HTTPError` and so is neither converted nor caught.

Any of those escapes the `except AppError`, escapes `_claim_*_grant`, and escapes
`_complete` — whose own handler at `:157` is also `except AppError`. The request then
lands on `generic_error_handler` as an opaque 500 **after** the grant is committed and
after the device bit may or may not have been written, and with the challenge left
claimed-but-unconsumed. That is exactly the outcome the comment says is impossible, and
it is the one case where the client cannot tell a fully-successful claim from a failed
one.

The module already knows the correct idiom: `_consume_quietly` (`:401-411`) catches bare
`Exception` precisely because its whole job is not raising.

**Fix:** widen both swallows to the same total catch `_consume_quietly` uses, keeping the
closed-set label rule:

```python
    try:
        await write_bits_with_retry(self.devicecheck, device_token,
                                    bit0=True, bit1=state.bit1)
    except Exception as failure:
        # A closed-set label only: the class name, never the token and never Apple's body.
        # Total, not `AppError`: the grant is already durable, so nothing raised here may
        # become the answer -- including a transport or signing failure the seam does not classify.
        logger.error("devicecheck_bit_write_failed", failure=type(failure).__name__)
```

Apply the identical change at `:296`.

---

### WR-51: `QuotaService.charge` logs the three integrity failures twice, and `SyncService` logs them zero times

**File:** `src/nativespeaker/api/services/quota.py:71`, `:80`, `:94`

**Issue:** All three branches emit their own line and then raise a class that the shared
handler logs again:

| quota.py | raises | class `log_level` |
|---|---|---|
| `:71` `logger.error("quota_integrity_failure", branch="multiple_effective_grants")` | `MultipleEffectiveGrantsError` | `logging.ERROR` (`errors.py:244`) |
| `:80` `logger.error("quota_integrity_failure", branch="missing_usage_row")` | `MissingUsageRowError` | `logging.ERROR` (`errors.py:234`) |
| `:94` `logger.error("quota_integrity_failure", branch="unknown_tier")` | `UnknownTierError` | `logging.ERROR` (`errors.py:255`) |

`app_error_handler` (`app/error_handlers.py:36-45`) logs whenever `exc.log_level is not
None`, so each of these rejections leaves **two** records: `quota_integrity_failure` and
`multiple_effective_grants_error` / `missing_usage_row_error` / `unknown_tier_error`.
SHARED-INVARIANTS § Fail-closed defaults requires "exactly one structured security-log
line carrying its stable internal result".

The second half of the defect is worse than the duplication. `SyncService.read_entitlement`
(`services/sync.py:41`, `:48`, `:53`) raises the **same three classes** for the **same three
conditions** and emits no extra line. So `branch=` is not a complete label set: an operator
alerting on `quota_integrity_failure` sees the charge path only and silently misses every
occurrence detected by `/auth/sync`, `/users/me`'s siblings and the claim routes. The
label reads like a census and is not one.

`38-PATTERNS.md:244-247` noted the lines were "optional, since the errors already log at
`ERROR` via `AppError.log_level`" and told sync not to mirror them — which is how the
asymmetry arrived, but it leaves the duplicate half unresolved.

**Fix:** delete the three `logger.error("quota_integrity_failure", ...)` calls and let the
registry's own event names be the single record, matching what `sync.py` already does.
The branch is already recoverable from the class name. If the `branch` label is wanted as
a joinable dimension, move it onto the exception instead so both call sites carry it:

```python
class MissingUsageRowError(InternalError):
    def log_fields(self) -> dict[str, str | None]:
        return {"grant_id": str(self.grant_id)}
```

Do not keep both.

### WR-70: `test_the_app_store_lines_it_ships_are_constructible` is a no-op today, and its control cannot see that

**File:** `tests/unit/test_config.py:579-591` (helper at `:542-546`)
**Issue:** The case exists to catch CR-04 — the shipped `.env.example` placeholders parsing as an
int and an enum and killing the pod at boot. It builds its input from `_uncommented(.env.example)`,
which drops every line starting with `#`. All three `APP_STORE_*` assignments in the tracked
`.env.example` are commented out (`.env.example:115-117`), so the comprehension yields `{}` and
the assertion degenerates to `isinstance(AppStoreConfig(), AppStoreConfig)` — a bare default
construction that proves nothing about any shipped value.

Verified by executing the file's own helper against the tracked file:

```
APP_STORE fields the test builds from: {}
DB_HOST present: True
```

The companion control, `test_the_reader_finds_the_assignments_that_file_does_ship_control`
(`:589-591`), asserts only that `DB_HOST` is found — a *different* prefix, one that happens to
ship uncommented. It therefore passes while the case it is meant to guard checks nothing. Every
other structural guard in this repository carries a control that would catch exactly this; this
one does not.

**Fix:** make the emptiness fatal, and make the control name the prefix under test.

```python
def test_the_app_store_lines_it_ships_are_constructible(self):
    shipped = _uncommented(REPOSITORY_ROOT / ".env.example")
    fields = {key.removeprefix("APP_STORE_").lower(): value
              for key, value in shipped.items() if key.startswith("APP_STORE_")}

    # The control, inline: an all-commented block would otherwise construct a bare default
    # and prove nothing about the placeholders CR-04 was about.
    assert fields, ".env.example ships no uncommented APP_STORE_ assignment: this checked nothing"
    assert isinstance(AppStoreConfig(**fields), AppStoreConfig)
```

If the block is meant to stay commented, read the commented placeholders instead — that is what a
deployer uncomments and boots against:

```python
def _placeholders(path: Path) -> dict[str, str]:
    """Every assignment the file ships, commented or not: a copied .env uncomments them."""
    pairs = (line.lstrip("# ").split("=", 1)
             for line in path.read_text().splitlines() if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs}
```

### WR-71: `TestNoProviderDependency` claims package-wide coverage it does not and cannot have

**File:** `tests/unit/test_adapter_interfaces.py:50-58`
**Issue:** The class docstring reads "No `firebase_admin` in `sys.modules`, so a convenience import
anywhere in the auth package fails this too." That is false. The snippet imports one module:

```python
result = _run("import sys, nativespeaker.api.auth.adapters; print('firebase_admin' in sys.modules)")
```

`src/nativespeaker/api/auth/__init__.py` deliberately exposes and imports nothing ("The auth
package exposes nothing from its root"), so importing `adapters` loads nothing else in the
package. Verified in a fresh interpreter:

```
firebase_admin in sys.modules: False
auth submodules: ['nativespeaker.api.auth', 'nativespeaker.api.auth.adapters']
```

A `firebase_admin` import added to `auth/devicecheck.py`, `auth/google_play.py`,
`auth/store_notifications.py` or `auth/jwt_verifier.py` passes this case unchanged. The claim
could never be true either way, because `auth/firebase.py` imports `firebase_admin` legitimately,
so a genuine package-wide assertion would fail as shipped. A reader relying on this docstring
believes a guard exists that does not.

**Fix:** state what is measured, and if package-wide coverage is wanted, name the modules it
applies to rather than the package.

```python
class TestNoProviderDependency:
    """`adapters` and everything it imports pull in no provider SDK. Package-wide is not
    assertable: `auth.firebase` imports `firebase_admin` by design, so the set is named."""

    # The modules that may never reach a provider SDK; `firebase` is excluded by design.
    SDK_FREE = ("adapters", "devicecheck", "google_play", "store_notifications", "jwt_verifier")

    @pytest.mark.parametrize("module", SDK_FREE)
    def test_importing_the_module_does_not_import_firebase_admin(self, module):
        result = _run(f"import sys, nativespeaker.api.auth.{module}; "
                      "print('firebase_admin' in sys.modules)")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "False"
```

### WR-72: no unit case asserts that a *successful* create-user consumes its challenge

**File:** `tests/unit/test_create_user_precedence.py:362-377`
**Issue:** The challenge handle is a secret capability. Every rejection arm in this file asserts
it is spent — `TestEveryProviderStageRejectionConsumes` (`:380-398`) for the provider stage,
`TestTheTransactionRejectionIsObservedAtTheHandler` (`:493-503`) for the transaction stage. The
one success case, `test_one_recognized_entry_with_a_uid_reaches_the_consuming_transaction`,
asserts the 200, the body, and the three facts handed to the creator — and asserts nothing about
`store.consume_calls` or `store.row.consumed_at`. Grepping the whole unit tree confirms no other
unit module asserts it either.

A regression that leaves the handle live after a successful account creation — a replayable
capability, and the exact hazard `test_a_replay_after_a_rejection_is_challenge_required_and_mints_nothing`
(`:400-415`) exists to close on the rejection side — is caught only by
`tests/e2e/test_create_user.py:140`. `pyproject.toml:64` sets
`addopts = "-v --tb=short -m 'not e2e and not schema'"`, so the default run deselects it. The
class name `TestEveryProviderStageRejectionConsumes` is honest about covering rejections only;
the gap is that nothing covers the other half.

**Fix:** add the two assertions the rejection arms already make, to the success case.

```python
    def test_one_recognized_entry_with_a_uid_reaches_the_consuming_transaction(
            self, client, store, creator, fake_firebase_adapter):
        ...
        assert response.status_code == 200
        assert response.json() == {"identity_provider": "google"}
        # The handle is spent on success as it is on every rejection: a live handle after a
        # created account is a replayable capability.
        assert store.consume_calls == 1
        assert store.row.consumed_at is not None
        assert store.row.preauth_subject is None
        assert len(creator.calls) == 1
        ...
```

### WR-91: The lost-race record both `TestTheDeferredKeysAreClassifiedWhereTheyAreEvaluated` classes are written for is asserted nowhere

**File:** `tests/unit/test_restore_proof.py:755-767`, `tests/unit/test_subscription_attribution.py:709-720`

**Issue:**
Both classes exist for one behaviour, stated in the docstring at
`test_restore_proof.py:759`: the deferred-key violation at COMMIT is "a state this file's
other writers report as an ordinary race in one line", not "`unhandled_exception` with a
full traceback". Neither test asserts the line. Both assert only
`pytest.raises(InternalError)` and `(commits, rollbacks) == (1, 1)`.

The line is the whole observable difference. `InternalError.log_level is None`
(`src/nativespeaker/api/errors.py:142`), so the shared handler writes nothing for it; the
only record either path produces is the explicit call inside `_settle`:

- `src/nativespeaker/api/services/restore.py:232` — `logger.warning("restore_grant_race_lost", provider=...)`
- `src/nativespeaker/api/services/subscriptions.py:195` — `logger.warning("store_notification_race_lost", provider=...)`

Neither event name appears anywhere under `tests/`:

```
$ grep -rn "store_notification_race_lost\|restore_grant_race_lost" tests/ src/
src/nativespeaker/api/services/subscriptions.py:195: ... "store_notification_race_lost" ...
```

Delete either `logger.warning` and the 500 becomes completely silent to an operator while
both tests stay green — which is the regression the class name claims to hold.

**Fix:** spy on the service logger (the pattern already used in
`test_services.py::TestAChargedWriteThatFailsIsFindable` and
`test_google_play_notifications.py::play_logs`) and assert the one record, including that
it carries the store name and nothing from the payload.

```python
@pytest.fixture
def warnings(monkeypatch) -> list[tuple[str, dict]]:
    entries: list[tuple[str, dict]] = []
    monkeypatch.setattr("nativespeaker.api.services.restore.logger.warning",
                        lambda event, **kw: entries.append((event, kw)))
    return entries

async def test_a_violation_at_commit_is_the_lost_race_the_flushes_report(self, warnings):
    session = _CommittingSession(IntegrityError("COMMIT", {}, Exception("23503")))

    with pytest.raises(InternalError):
        await _same_account_restore(EVALUATED_AT - timedelta(days=1), session=session)

    assert (session.commits, session.rollbacks) == (1, 1)
    # The one line, and only it: the 500 itself logs nothing at all.
    assert warnings == [("restore_grant_race_lost", {"provider": "PurchaseProvider.apple"})]
```

(Assert whatever `str(proof.provider)` actually renders; the point is that the record is
pinned rather than absent.) Do the same for the `store_notification_race_lost` sibling.

### WR-92: The Pub/Sub "bound off by one" control never goes near the bound

**File:** `tests/unit/test_models.py:382-387`

**Issue:**
The docstring says "The control: a bound off by one here would drop every genuine RTDN at
the ceiling." The payload it builds is about eighty bytes:

```python
payload = b64encode(json.dumps({"packageName": "com.example",
                                "eventTimeMillis": 1}).encode()).decode()
assert len(payload) <= PUBSUB_DATA_LIMIT      # 80 <= 16384
assert developer_notification_from(payload) is not None
```

`PUBSUB_DATA_LIMIT` is 16384 and the guard is
`if len(data) > PUBSUB_DATA_LIMIT` (`src/nativespeaker/api/auth/google_play.py:140`).
Change that `>` to `>=` and a genuine 16384-byte RTDN is dropped and silently acknowledged
— and this test still passes, because it never presents a body at the ceiling. The
just-over case is covered (`test_the_decoder_drops_an_out_of_range_body_rather_than_refusing_it`,
`"a" * (PUBSUB_DATA_LIMIT + 1)`), so the boundary is closed on one side only. The Apple
sibling in the same class gets this right: `test_a_body_at_the_bound_is_accepted` uses
`"a" * limit`.

**Fix:** present a decodable body whose encoded length is exactly the limit.

```python
def test_a_body_at_the_bound_still_reaches_the_decoder(self):
    """The control: a bound off by one here would drop every genuine RTDN at the ceiling."""
    # Padded inside the envelope so the base64 text lands exactly on the bound, which is
    # the only length an off-by-one distinguishes from the one above it.
    envelope = {"packageName": "com.example", "eventTimeMillis": 1, "pad": ""}
    overhead = len(b64encode(json.dumps(envelope).encode()).decode())
    envelope["pad"] = "a" * ((PUBSUB_DATA_LIMIT - overhead) // 4 * 3)
    payload = b64encode(json.dumps(envelope).encode()).decode()

    assert len(payload) == PUBSUB_DATA_LIMIT
    assert developer_notification_from(payload) is not None
```

### WR-93: The single-writer walk matches one spelling, so a second writer can arrive silently

**File:** `tests/unit/test_grant_sources.py:54-76` (the walks), `:93`, `:116`, `:217` (the claims)

**Issue:**
The file's whole premise is at `:91`: "A second writer added by a later phase has to come
here and change a number someone reads," and `:214` names Phase 45's restore as the
specific future writer it guards against. `_construction_sites` only matches
`ast.Name('AccessGrant')` calls, and `_names_the_member` only matches
`ast.Attribute` on `ast.Name('AccessGrantSource')`. Measured against the real helpers:

```
'g = tables.AccessGrant(source=AccessGrantSource.subscription)'   -> sites [] mentions 1
'g = AccessGrant(**{"source": AccessGrantSource.subscription})'   -> sites [] mentions 1
'g = AccessGrant(source=SOURCE)'                                  -> sites [] mentions 0
'from ... import AccessGrantSource as S; AccessGrant(source=S.subscription)'
                                                                  -> sites [] mentions 0
'g = AccessGrant(source=getattr(AccessGrantSource, "subscription"))'
                                                                  -> sites [] mentions 0
```

The first two are still caught by `test_only_the_recorded_modules_name_the_member_at_all`.
The last three escape both walks entirely: a new module writing a subscription grant
through an aliased enum import, an indirection variable, or `getattr` adds a second writer
with all thirty-one cases green. The near-miss controls at `:170` and `:250` test the other
direction (that a wrong member is not counted) and so do not close this.

**Fix:** resolve the local binding rather than assuming the canonical spelling, and refuse
the shapes the walk cannot decide.

```python
def _enum_aliases(tree: ast.Module) -> set[str]:
    """Every local name bound to `AccessGrantSource`, so an aliased import is still seen."""
    aliases = {ENUM}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            aliases |= {a.asname or a.name for a in node.names if a.name == ENUM}
    return aliases


def _undecidable_sites(source: str) -> list[int]:
    """`AccessGrant(**fields)` and `getattr(...)`: shapes the walk cannot rule on, so they
    are reported rather than passed over as absent."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _is_access_grant(node.func):
            if any(kw.arg is None for kw in node.keywords):
                found.append(node.lineno)
    return found
```

and widen `_is_access_grant` to accept `ast.Attribute(attr="AccessGrant")` as well as
`ast.Name`. Then add a case asserting `_undecidable_sites` is empty across `src/`, and
extend the `TestTheWalkFires` controls with the five spellings above so the widening is
itself measured.

### WR-94: The sync clock walk matches one spelling of a clock read

**File:** `tests/unit/test_sync_clock_capture.py:13`, `:50-56`

**Issue:**
`CLOCK_CALLS` is four `(name, attr)` pairs and `_clock_calls` requires
`isinstance(n.func.value, ast.Name)`. Measured against the real helper:

```
'x = datetime.datetime.now(UTC)'                    -> 0 clock calls
'from datetime import datetime as dt; x = dt.now()' -> 0
'x = time.monotonic()'                              -> 0
'x = time.perf_counter()'                           -> 0
'now = datetime.now; x = now(UTC)'                  -> 0
'x = datetime.now(tz=UTC)'                          -> 1
```

`test_sync_service_makes_no_clock_call_on_any_path` (:52) and
`test_no_service_dependency_reads_the_clock_itself` (:114) therefore pass for a service
that reads `time.monotonic()`, or that imports `datetime` under any other name. The
companion case `test_the_datetime_import_is_used_only_as_a_type_annotation` (:55) closes
the aliased-`datetime` hole for `sync.py` alone — it does not run against
`dependencies.py`, and it says nothing about the `time` module either way.

Requirement `req~sessions-sync-single-evaluation-time~2` is what this file exists to hold,
and a second instant read through any of the four spellings above is exactly the defect.

**Fix:** widen the shape set and resolve aliases the same way.

```python
# The modules a clock can be read from, and the members of each that read one.
CLOCK_MEMBERS = {"datetime": {"now", "utcnow", "today", "fromtimestamp"},
                 "date": {"today"},
                 "time": {"time", "monotonic", "perf_counter", "time_ns", "monotonic_ns"}}


def _clock_calls(node: ast.AST, aliases: dict[str, str] | None = None) -> list[ast.Call]:
    """Every call reading a clock, whatever local name its module was imported under."""
    aliases = {} if aliases is None else aliases
    found = []
    for n in ast.walk(node):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        base = n.func.value
        # `datetime.datetime.now(...)` as well as `datetime.now(...)`.
        name = (base.attr if isinstance(base, ast.Attribute)
                else base.id if isinstance(base, ast.Name) else None)
        canonical = aliases.get(name, name)
        if n.func.attr in CLOCK_MEMBERS.get(canonical, ()):
            found.append(n)
    return found
```

Build `aliases` from the module's `ImportFrom`/`Import` nodes, and add each escaping
spelling above to `TestTheClockWalkIsNotVacuous` so the widening is measured rather than
asserted.

### WR-110: `anonymous_firebase_credential` leaks a permanent Firebase user when app selection fails

**File:** `tests/e2e/conftest.py:106-127`

**Issue:** The `signUp` call at line 113 creates a real user in the shared Firebase project. The user exists from the moment `resp.raise_for_status()` (line 118) returns. But two statements then run *outside* the `try`:

```python
    local_id = data["localId"]                                            # 121
    admin_app = firebase_admin.get_app(name=f"issuer:{_app_config.jwt.issuer}")  # 123
    try:
        yield data["idToken"], local_id
    finally:
        auth.delete_user(local_id, app=admin_app)
```

`firebase_admin.get_app(name=...)` raises `ValueError` when no app is registered under that name. The guard at line 111 checks only that Application Default Credentials are *findable* (`_application_default_credential() is not None`) — a different condition from "the lifespan actually registered an app named `issuer:<issuer>`". If `build_admin_apps` failed, was renamed, or the configured issuer drifted, the just-minted user is never deleted.

The fixture's own docstring states the cost: *"the project is shared, so a user left behind is permanent, and one accumulates per run."*

This is the rule the repository has already ratified twice and applied everywhere else:

- `google_linked_firebase_credential` (lines 150-185) resolves `admin_app` at line 156 — *before* the signup at line 162 — and its comment says so explicitly: *"The try opens where the user starts existing, not where it is yielded."*
- Commit `d9fa720` (`fix(39): WR-91 open the fixture try where the engine starts existing`) applied the same rule to `_contended_challenge` in `tests/e2e/test_challenge_store.py:78-81`.

`anonymous_firebase_credential` is the only remaining outlier.

**Fix:** Resolve the admin app before creating the user, exactly as the Google twin does:

```python
    if not _admin_credential_configured():
        pytest.skip(_NO_ADMIN_CREDENTIAL)
    # The app the lifespan already built, reached by its documented name -- resolved before the
    # signUp, so nothing between the user starting to exist and the try that deletes it can raise.
    admin_app = firebase_admin.get_app(name=f"issuer:{_app_config.jwt.issuer}")
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={_identity_toolkit_key(_app_config)}",
        json={"returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    local_id = data["localId"]
    try:
        yield data["idToken"], local_id
    finally:
        auth.delete_user(local_id, app=admin_app)
```

---

### WR-111: the Apple restore fake drops `evaluated_at`, so no case can detect the branch re-reading the clock

**File:** `tests/e2e/conftest.py:328-334`

**Issue:** `FakeAppStoreNotifications.verify_transaction` accepts `evaluated_at` and throws it away:

```python
    def verify_transaction(self, signed_transaction: str,
                           evaluated_at: datetime) -> RestoredSubscription:
        self.restore_calls.append(signed_transaction)   # evaluated_at is never recorded
```

`SHARED-INVARIANTS.md` § "Grants and evaluation time" binds every path: *"Derive every time-dependent value from ONE captured evaluation time or one consistent snapshot per request."* `src/nativespeaker/api/services/restore.py:216` does forward `self.evaluated_at` today — but if it were changed to `datetime.now(UTC)` at the call site, **every case in `tests/e2e/test_restore_subscription.py` would still pass**, because the value never reaches an assertion.

The Play twin in the same file shows the intended shape — `FakePlaySubscriptions.read_for_restore` (lines 455-463) records `evaluated_at` in its `restore_calls` dict — but no case asserts it there either (`test_restore_subscription.py:717-718` reads only `call["purchase_token"]`). I checked the unit suite as well: `tests/unit/test_restore_proof.py:478-498` uses two fakes that also discard the parameter. So the forwarding of the captured instant into either store seam is unasserted anywhere in the repository.

**Fix:** Record the pair in the Apple fake and assert it on the happy path of both stores.

```python
    def verify_transaction(self, signed_transaction: str,
                           evaluated_at: datetime) -> RestoredSubscription:
        # The pair, not the artifact alone: the captured instant is what SHARED-INVARIANTS binds.
        self.restore_calls.append((signed_transaction, evaluated_at))
```

and in `test_restore_subscription.py`, on the tracer case, compare the recorded instant to the one the response reports rather than to a fresh `datetime.now(UTC)` (a second reading of the clock would pass a `>= before` check).

---

### WR-112: `APPLE_REJECTION_STAGES` is one code path repeated three times, and the class claims four causes

**File:** `tests/e2e/test_restore_subscription.py:73, 743-766`

**Issue:** `TestEveryRejectedProofOfBothStoresAnswersOneBody` docstring: *"T-45-05: one status and one body for **four causes**, so the refusal is no enumeration oracle."*

The four "causes" are three `ProofRejected(stage=...)` values plus one Google 404. But `stage` is a field of `ProviderLookupError.__init__` (`src/nativespeaker/api/errors.py:418-431`) that reaches only `log_fields()` — it never touches the status or the body. The seam is `FakeAppStoreNotifications`, which raises back exactly the exception the test handed it (`tests/e2e/conftest.py:330-331`). So the three Apple parameters drive the *same* branch with a different log string, and the test asserts no log record at all. `APPLE_REJECTION_STAGES` therefore proves nothing that one parameter would not.

The webhook twin shows the pattern done properly: `test_app_store_webhook.py:300-330` asserts the log record carries the stage (`refusal_records.entries == [("notification_rejected", stage)]`) **and** carries two controls (`test_every_reachable_arm_is_covered_by_one_parameter`, `test_no_raise_site_lives_where_neither_route_control_reads_it`) that fail when the parameter list stops being exhaustive. The restore file has neither, and its `APPLE_REJECTION_STAGES` names only 3 of the library's 7 non-`OK` statuses with no control to say why.

**Fix:** Either assert the distinguishing detail so the parameters mean something —

```python
    async def test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing(
            self, restore_client, _db_transaction, scripted_app_store_notifications,
            real_google_play_seam, refusal_records):
        ...
        for stage in APPLE_REJECTION_STAGES:
            scripted_app_store_notifications.script_restore(ProofRejected(stage=stage))
            answers.append(await _restore(restore_client))
        # The distinguishing detail exists, and only in the log: without this the three arms
        # are one arm run three times, since `stage` never reaches the response.
        assert [fields["stage"] for _event, fields in refusal_records.entries] == \
            list(APPLE_REJECTION_STAGES)
```

— or drop to one Apple parameter and correct the docstring to "two causes".

---

### WR-113: ~96 lines duplicated verbatim between the two webhook e2e files, including a control constant

**File:** `tests/e2e/test_app_store_webhook.py:60-104,124-169`; `tests/e2e/test_google_play_webhook.py:222-266,267-313`

**Issue:** A `difflib` block match over the two files reports seven identical runs totalling 96 lines:

| Apple lines | Google lines | size |
|---|---|---|
| 63-70 | 225-232 | 8 |
| 72-93 | 234-255 | 22 |
| 95-104 | 257-266 | 10 |
| 126-155 | 270-299 | 30 |
| 307-314 | 399-406 | 8 |
| 326-331 | 418-423 | 6 |

The duplicated block is the whole AST-scanning harness — `_called_name`, `_refusal_calls`, `_files_raising_the_refusal`, `_raised_refusal_stages`, `_PACKAGE`, `_COMPUTED` — plus `_LogSpy` / `_spy_on` and the four spy fixtures.

The sharpest hazard is the control constant, defined identically in both files:

```python
_REFUSAL_FILES = frozenset({"app/dependencies.py", "auth/app_store.py", "auth/google_play.py"})
```

Two separate tests (`test_app_store_webhook.py:330` and `test_google_play_webhook.py:422`) assert `_files_raising_the_refusal() == _REFUSAL_FILES` against these two copies. A fourth file gaining a `NotificationRejected(...)` raise site must be added to both frozensets; updating one leaves the other red for a reason that no longer describes the code.

`_LogSpy` / `_spy_on` exists in four places repo-wide — the two webhook files, `tests/e2e/test_sign_out_all.py:32-48`, and a variant (`_RecordedLogs`) in `tests/schema/test_subscription_ingestion.py:295-315`. `AGENTS.md` asks that programming this app not consume many tokens; four copies of one spy is the opposite.

**Fix:** Lift the shared harness into `tests/e2e/conftest.py` (the spy and its fixtures) and a small `tests/e2e/refusal_sites.py` (the AST scan plus the single `_REFUSAL_FILES` frozenset). Each webhook file then supplies only its own `_REFUSAL_SOURCES` tuple, which is the part that genuinely differs.

---

### WR-114: the anonymous claim's platform-pinning refusal has no test anywhere in the repository

**File:** `tests/schema/test_grant_locks.py:740-763` (`TestTheAnonymousWriterNamesWhyItRefused`)

**Issue:** `06-claim-anonymous-grant.md` step 7 is normative: *"**Anonymous-claimant platform pinning**: `external_identities.native_claim_platform` is set once at the identity's first verified device attestation, immutable; material from the other platform is thereafter rejected."*

`GrantsDB.activate_anonymous_device_grant` implements it (`src/nativespeaker/api/crud/grants.py`):

```python
        if (stored.native_claim_platform is not None
                and stored.native_claim_platform is not claim_platform):
            return ActivationOutcome.refused
```

Grepping the whole test tree for `native_claim_platform` / `android_play_integrity` returns five hits: two in `tests/unit/test_identity_accessors.py` (column shape and enum labels), one in `tests/schema/test_inventory.py` (enum labels), one in `tests/e2e/test_claim_anonymous_grant.py:108` (asserts it is *set* to `ios_devicecheck`), and two in `tests/schema/test_claim_race.py:356,447` (asserts the committed value). **No test ever passes `android_play_integrity` to the writer**, so the refusal branch is never taken.

This is not merely dead code that D-01 defers: D-01 defers the Android *adapter*, but the writer's guard is already shipped, it is the sole enforcement of an immutability rule the brief calls out, and `_account_holding(..., provider="anonymous")` plus `_Account.activate_anonymous` already give the harness needed to reach it in about six lines.

**Fix:** Add the case beside the two the class already has:

```python
    async def test_material_from_the_other_platform_is_refused_once_the_pin_is_set(
            self, _schema_db_uri):
        """06 step 7: the pin is immutable, so a claim from the other platform is refused and
        never restamps the identity row."""
        async with _account_holding(_schema_db_uri, (), provider="anonymous") as account:
            assert await account.activate_anonymous() is ActivationOutcome.activated
            # A second identity claiming from Android against a row pinned to iOS.
            refused = await GrantsDB(account.session).activate_anonymous_device_grant(
                user_id=account.user_id, identity_row=account.identity_row,
                claim_platform=NativeClaimProvider.android_play_integrity,
                tier_id=account.tier_id, evaluated_at=account.evaluated_at)
            assert refused is ActivationOutcome.refused
            assert await account.grants() == [("anonymous_device_grant", "active")]
```

(The pin must already be set for the guard to fire, so activating first is what puts the row in the state under test.)

## Info

### IN-09: `responses={...}` on the `FastAPI()` constructor is dead configuration

**File:** `src/nativespeaker/api/app/main.py:30-41`

**Issue:** `responses` affects OpenAPI schema generation and nothing else. Lines
27-29 set `docs_url=None`, `redoc_url=None` and `openapi_url=None`, so no schema
is ever generated or served and this twelve-line mapping is never read by
anything. It reads as the error contract, which invites a future reader to
maintain it in step with `errors.py` for no effect.

**Fix:** delete it, or replace it with a one-line comment pointing at
`errors.py`'s `ErrorCode` literal as the real contract.

### IN-10: `[tool.pogo] schema = 'api'` names a schema nothing creates or uses

**File:** `pyproject.toml:85`

**Issue:** `pogo_core.util.sql.get_connection` runs `SET search_path TO api`
before applying migrations. No migration creates an `api` schema
(`migrations/20260818_01_initial-release.sql:6-7` creates `core` and `audit`),
and no ORM table declares one (`grep 'schema=' src/.../tables/` returns `core`
only). PostgreSQL does not error on a `search_path` naming a missing schema, so
this is harmless today only because every DDL statement in the migration is
schema-qualified. The first unqualified `CREATE` in a future migration fails with
"no schema has been selected to create in", and `pogo apply --create-schema`
would materialise an empty `api` schema nothing uses.

**Fix:** `schema = 'core'`, or drop the key and let it default to `public`.

### IN-11: the chart's `appVersion` trails the package version by a minor release

**File:** `pyproject.toml:3`, `k8s/Chart.yaml:6`

**Issue:** `pyproject.toml` declares `version = "1.6.0"`; `Chart.yaml` declares
`appVersion: "1.5.0"`. `_helpers.tpl` renders `app.kubernetes.io/version` from
`.Chart.AppVersion`, so every pod, Service and HTTPRoute is labelled `1.5.0`
while `main.py:24` reports `1.6.0` on `GET /`. Anything selecting or grouping by
that label — a dashboard, a rollout query — reads the wrong release.

**Fix:** bump `appVersion` to `1.6.0` and add the bump to whatever step already
edits `pyproject.toml`'s version.

### IN-12: the chart description advertises rate limiting the chart no longer ships

**File:** `k8s/templates/NOTES.txt:14-20`, `k8s/Chart.yaml:3`

**Issue:** `NOTES.txt:14` is explicit — "No rate-limit policy ships in this
chart: the BackendTrafficPolicy that carried the only one was removed" (the
ratified 37.1 CR-61 fix). `Chart.yaml:3` still reads "NativeSpeaker API Gateway -
Linguistic analysis API with Envoy Gateway rate limiting". `helm search` and
`helm show chart` surface the description, not `NOTES.txt`, so the stale claim is
what a reader meets first.

**Fix:** `description: NativeSpeaker API Gateway - Linguistic analysis API`.
(`Chart.yaml` is outside this review's file set; filed here because `NOTES.txt`
is the document it contradicts.)

### IN-13: a lost admission slot is swallowed by a bare `pass`

**File:** `src/nativespeaker/api/resilience.py:110-113`

**Issue:** Carry-over of 37.3 IN-26, still unfixed — that review's fix pass
recorded "Info was out of scope — no `--all`", so it was never dispositioned on
merits.

```python
finally:
    try:
        self._slots.put_nowait(token)
    except asyncio.QueueFull:
        pass
```

Tokens are conserved by construction, so `QueueFull` is unreachable; if it ever
fires, the service permanently loses one unit of admission capacity with no
record, and the only symptom is `QueueFullError` 503s arriving earlier than
`queue_size` predicts. A bare `pass` on a broken invariant is the shape this
codebase otherwise refuses (`services/quota.py:74-76`, "A tripwire, not a
recovery branch").

**Fix:** `logger.error("llm_gate_slot_lost")` in place of `pass`.

### IN-14: `exc_info` is decided from the unclamped log level

**File:** `src/nativespeaker/api/app/error_handlers.py:38-45`

**Issue:** Carry-over of 37.3 IN-27, still unfixed (the surrounding lines were
rewritten for a different reason — passing `exc` rather than `True` — without
picking this up).

```python
level = exc.log_level if exc.log_level in _LOGGABLE else logging.ERROR
record = getattr(logger, logging.getLevelName(level).lower())
record(..., exc_info=exc if exc.log_level >= logging.ERROR else False, ...)
```

`level` is clamped; `exc_info` still tests the raw `exc.log_level`. A class
declaring, say, `log_level = 15` would be recorded at ERROR — where this codebase
pages — with no traceback. Unreachable today (every class declares a standard
level or `None`), so this is a latent inconsistency in the fallback that exists
precisely to absorb non-standard values.

**Fix:** `exc_info=exc if level >= logging.ERROR else False`.

### IN-15: `QueueFullError` is unreachable in `attempt()`'s guard arm

**File:** `src/nativespeaker/api/resilience.py:193`

**Issue:**

```python
except (QueueFullError, CircuitOpenError):
    # First, and it must stay first: the breaker's own refusal is not the provider's failure.
    raise
```

Nothing inside the `try` can raise `QueueFullError`: the in-flight slot is taken
in `admission()` (`:165`), which is a different call, and `attempt()` touches only
`before_call`, `current_generation` and `operation()`. The comment justifies the
arm's *position*, which remains correct for `CircuitOpenError`, but the
`QueueFullError` member is dead and implies a coupling that does not exist.

**Fix:** `except CircuitOpenError: raise`, keeping the comment.

### IN-16: the rationale pinning the log-level set names two values that are in fact supported

**File:** `src/nativespeaker/api/config.py:9-11`

**Issue:**

```python
# The levels both libraries share: `logging` also admits FATAL, WARN and NOTSET, which
# `structlog.make_filtering_bound_logger` has no entry for and crashloops the pod at startup.
```

Checked against the pinned structlog 25.5.0:
`sorted(structlog._log_levels.NAME_TO_LEVEL)` is
`['critical', 'debug', 'error', 'exception', 'info', 'notset', 'warn', 'warning']`,
and `make_filtering_bound_logger("NOTSET")` and `("WARN")` both succeed. Only
`FATAL` raises `KeyError`. The five-member restriction is still the right call —
one of the three named values really does crashloop — but two thirds of the
stated reason is wrong, which is the kind of comment a future reader trusts when
deciding whether the restriction can be relaxed.

**Fix:** narrow the claim to the value it holds for:

```python
# The levels both libraries share. `logging` also admits FATAL, which
# `structlog.make_filtering_bound_logger` has no entry for and which crashloops the pod at startup.
```

### IN-20: `read()` does not apply to `package_name` the path guard `read_for_restore` applies to the same value

**File:** `src/nativespeaker/api/auth/google_play.py:254-260` vs `312-317`

**Issue:** both entry points reach the same `_get`, and `read_for_restore`
guards both segments (`if not package_name or not
_names_one_path_segment(package_name)`), while `read` guards only
`purchase_token`. Today this is safe — `app/dependencies.py:213` refuses any
`packageName` that differs from `config.google_play.package_name` before `read`
is called — but the guard sits one module away from the URL it protects, and the
asymmetry reads as an oversight rather than a decision. (Separately,
`not package_name` at `:312` is redundant: `"".strip(".")` is `""`, so
`_names_one_path_segment("")` is already False.)

**Fix:** hoist both segment checks into `_get`, where the URL is actually built,
and let each entry point keep only its own classification of the refusal.

### IN-21: `PubSubPushRequest.subscription` is declared and never read

**File:** `src/nativespeaker/api/schemas/webhooks.py:39`

**Issue:** `grep -rn "\.subscription\b" src/` matches only this declaration.
Four lines above it, the module records the rule that killed `messageId`:
"nothing read it … so requiring it made an envelope shape change a permanent 422
in exchange for validating a value the service never used". `subscription` is
optional so it costs no 422, but it is the same unread field the module argues
against carrying.

**Fix:** delete the field, or add one line saying why this one is kept when
`messageId` was not.

### IN-22: Two stale line references in comments

**File:** `src/nativespeaker/api/auth/app_store.py:141`,
`src/nativespeaker/api/auth/store_notifications.py:31`

**Issue:** `app_store.py:141` says "Verified and unwritable, exactly as line 98
above" — line 98 is `self._products = products`; the intended reference is the
matching early return at line 127. `store_notifications.py:31` cites
"`crud/subscriptions.py:300`" for the by-identity status read; line 300 is
`new_tier_id=new_tier_id,` and the identity comparison
(`status is SubscriptionStatus.revoked`) is at line 346.

**Fix:** name the function rather than the line
(`AppStoreNotifications.verify`'s test-notification arm;
`SubscriptionsDB._grant_end_for`), so the reference survives the next edit.

### IN-23: The `email_verified` pin accepts a numeric `1`

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:229-236`

**Issue:** `payload.get(claim) != expected` with `expected is True` compares by
equality, and `1 == True` in Python. A push token carrying `"email_verified": 1`
satisfies the pin that `app/lifespan.py:83` sets to guard spec 09's "require
`email_verified`". Google will not send that, so this is not exploitable today —
but the pin is looser than it reads, and the same loophole applies to any future
boolean claim added to `required_claims`.

**Fix:** compare by type as well where the expected value is a bool:

```python
value = payload.get(claim)
if value != expected or isinstance(expected, bool) != isinstance(value, bool):
    return None, BoundedReason.required_claim_mismatch
```

### IN-24: `lookup_with_retry` and `revoke_with_retry` are the same eight lines twice

**File:** `src/nativespeaker/api/auth/firebase.py:188-213`

**Issue:** the two functions differ only in the callback they pass and the
adapter method they call; `devicecheck.py:176-183` already factors the identical
shape into `_retrying(exhausted)`. Phase 46's review filed this as IN-01; it is
unfixed, and WR-21 above requires editing both copies in lockstep to add the
`wait=`, which is exactly the cost duplication imposes.

**Fix:** adopt `devicecheck.py`'s shape:

```python
def _retrying(exhausted) -> AsyncRetrying:
    return AsyncRetrying(stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
                         wait=wait_exponential(multiplier=0.5, max=2),
                         retry=retry_if_exception_type(RetryableLookupError),
                         retry_error_callback=exhausted)
```

### IN-39: Dead `lost_race` arm on the supersession flush

**File:** `src/nativespeaker/api/crud/grants.py:278-286`

**Issue:** The flush guarded here issues only an UPDATE that sets
`status = expired` and `ends_at` on one already-locked row. That statement
cannot breach any unique index in the schema:
`ix_access_grants_one_active_per_user` is partial on `status = 'active'`, so the
update removes the row from it; `ix_access_grants_one_free_grant_per_user_source`
keys `(user_id, source)`, neither of which changes, and Postgres does not
conflict a tuple with its own prior version;
`ix_access_grants_one_per_subscription` excludes `subscription_id IS NULL`, which
an `anonymous_device_grant` always is. The only integrity error reachable here
is the `CHECK (ends_at IS NULL OR ends_at > starts_at)`, which the guard
correctly re-raises. `return ActivationOutcome.lost_race` on line 286 is
therefore unreachable, and the comment on line 278 ("the one-active index is
per-statement") explains a hazard that does not apply to an update that only
leaves the index.

**Fix:** Keep the isolating flush and the non-unique re-raise, but drop the
`lost_race` return and say what the flush is actually for — ordering the update
ahead of the insert so the ORM does not emit the insert first.

### IN-40: `Chat.human_messages` is dead

**File:** `src/nativespeaker/api/tables/chats.py:60-62`

**Issue:** Zero references across `src/` and `tests/`. Its sibling
`ai_messages` has one real consumer (`services/chats.py:121`).

**Fix:** Delete the property.

### IN-41: `Chat.user` relationship is unused and would fail if it were used

**File:** `src/nativespeaker/api/tables/chats.py:54`

**Issue:** `user: User = Relationship()` has no consumer — every route reads the
user from the barrier's identity context (`identity.user.id`), never through the
chat row. It is also a lazy-loading relationship on an `AsyncSession`, so the
first access would raise `MissingGreenlet` rather than return a `User`, and the
declared non-optional `User` annotation promises otherwise.

**Fix:** Delete it, or give it `sa_relationship_kwargs={"lazy": "raise"}` so the
trap is explicit if it is being kept for a future reader.

### IN-42: `count_chats` is the only method in its module that bypasses `exec`/`col`

**File:** `src/nativespeaker/api/crud/chats.py:26-28`

**Issue:** Two inconsistencies in three lines. It uses `self.session.scalar`
where every other method uses `self.session.exec`, and it writes
`Chat.user_id == user_id` where every other predicate in the file is wrapped in
`col(...)`. `session.scalar` is typed to return `Any`, so the declared `-> int`
is unverified by `ty` — it happens to be true because `func.count()` always
yields a row, but nothing in the signature says so.

**Fix:**

```python
statement = select(func.count()).select_from(Chat).where(col(Chat.user_id) == user_id)
return (await self.session.exec(statement)).one()
```

### IN-43: `WriteOutcome.replayed` is returned after a real column write

**File:** `src/nativespeaker/api/crud/subscriptions.py:32-36, 218-227`

**Issue:** The enum docstring says `replayed` means "it changed nothing". The
`store_signed_at` advance on lines 218-224 runs before the `settled` branch and
writes both `store_signed_at` and `updated_at`, after which line 227 still
returns `replayed`. No caller currently branches on anything but `lost_race`, so
there is no behavioural bug today, but the name now misdescribes the outcome for
the next reader.

**Fix:** Reword the member docstring to "no lifecycle state changed" and note
that the store clock may still have advanced, or track the write and return
`applied`.

### IN-44: `tables/grants.py` comment misstates what the database does with an omitted timestamp

**File:** `src/nativespeaker/api/tables/grants.py:70-71`

**Issue:** "No default on any timestamp in this module: the creating transaction
owns the clock, so a forgotten value is a NOT NULL violation rather than a
second reading of it." The DDL disagrees — `core.access_grants` declares
`starts_at`, `created_at` and `updated_at` all as
`TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`, so an omitted value would get
exactly the second clock reading the comment says it cannot. The stated outcome
is delivered by SQLModel/pydantic making the field required at construction, not
by the schema.

**Fix:** Say so: "required at construction, so the creating transaction's clock
is the only one that reaches the column — the DDL default is a backstop this
package never relies on."

### IN-45: `crud/__init__.py` exposes only half the package's public surface

**File:** `src/nativespeaker/api/crud/__init__.py:1-8`

**Issue:** The facade re-exports the six `*DB` classes, but `ActivationOutcome`,
`WriteOutcome`, `ENTITLED_STATUSES` and `is_unique_violation` are equally part of
the contract and are imported from submodules instead
(`services/auth.py:15`, `services/subscriptions.py:11-15`,
`services/restore.py:18`). Every caller therefore uses both import styles at
once, and the `__all__` on line 1 is not a description of what the package
offers.

**Fix:** Re-export the outcome enums and `ENTITLED_STATUSES` from the package and
add them to `__all__`, or drop the facade and import from submodules
consistently. Either is fine; the mix is what costs a reader.

### IN-46: `Chat` and `Message` take a second clock reading per request

**File:** `src/nativespeaker/api/tables/chats.py:32, 45`

**Issue:** `default_factory=lambda: datetime.now(UTC)` on both `created_at`
columns reads the clock at row construction rather than taking the request's
captured `evaluated_at`, which is what SHARED-INVARIANTS line 44 requires
("Derive every time-dependent value from ONE captured evaluation time or one
consistent snapshot per request") and what `tables/grants.py` and
`tables/purchases.py` do deliberately. A chat and its first message can land on
two different instants, and neither matches the instant the rest of the request
was evaluated at.

**Fix:** Drop the `default_factory` and pass `evaluated_at` from
`ChatsService`, matching the grant and purchase tables. This predates phase 40
and the columns are not entitlement state, so it is informational.

### IN-52: `/auth/sync` is still the only `SyncResponse` route without `Cache-Control: no-store`

**File:** `src/nativespeaker/api/routers/auth.py:183-192`

**Issue:** `claim_anonymous_grant` (`:128`), `claim_registered_grant` (`:151`) and
`restore_subscription` (`:179`) each take `response: Response` and set
`Cache-Control: no-store`, each under the same explanatory comment. `sync` returns the
byte-identical `SyncResponse` model and sets nothing. The divergence carries no comment,
so the next reader cannot tell whether it is a decision or an omission.

Already filed as **IN-34 in `38-REVIEW.md:2035`**; it appears nowhere in
`38-REVIEW-FIX.md`, so it was never dispositioned. Re-filed because the anomaly has since
widened from one-of-two routes to one-of-four. Risk remains low (all four are POSTs, which
no shared cache stores by default) and it is not a spec violation — the no-store
requirement in the specs binds prepare responses only.

**Fix:** either add the two lines to match the siblings, or add one comment on `sync`
stating why it does not need them.

---

### IN-53: the `/examples` `lang` query parameter is unbounded while the same value is capped at 16 elsewhere

**File:** `src/nativespeaker/api/routers/examples.py:15`

**Issue:** `lang: str = Query(..., description="Language code (e.g., 'en', 'es')")` has no
`max_length`. `ChatRequest.lang` (`schemas/api.py:16`) bounds the same concept at
`max_length=16` with an explicit rationale comment. An oversized value reaches
`ChatService.get_examples` → `self.examples.get(lang, [])` → `UnsupportedLanguageError(lang,
supported)`, whose `__init__` interpolates the whole value into an f-string. That string
never reaches the body (`ErrorResponse` carries `code` alone) and never reaches a log
(`InvalidRequest.log_level is None`), so this is waste rather than exposure — but the two
spellings of one bound will drift.

**Fix:** `lang: str = Query(..., max_length=16, description="Language code (e.g., 'en', 'es')")`.

---

### IN-54: `create_chat` never re-checks the chat-count limit after the provider call

**File:** `src/nativespeaker/api/services/chats.py:90-92`

**Issue:** `chats_count >= self.chats_limit` is evaluated, the read transaction is then
ended at `:99`, and the insert happens at `:106` after an unbounded provider round trip.
Nothing re-reads the count, and no unique constraint backs the limit, so N concurrent
`POST /chats` from one user all pass the check and all insert — `chats_limit` is exceeded
by up to N-1.

The sibling `send_message` re-reads under exactly this reasoning (`:133-139`), so the
asymmetry is unexplained. Filed as Info rather than Warning: each excess chat still costs
a monthly credit, so `QuotaService` bounds the overshoot, and AGENTS.md is explicit about
not over-engineering a pre-launch product.

**Fix:** if it is worth closing, re-read the count in the writing transaction next to the
existing `get_chat` re-read; otherwise state in a comment that the quota charge is the
real bound and `chats_limit` is advisory.

---

### IN-55: two handlers omit the return annotation every sibling carries

**File:** `src/nativespeaker/api/routers/chats.py:22`, `src/nativespeaker/api/routers/root.py:15`

**Issue:** `list_chats` and `root` have no `-> ...`. Every other handler in the reviewed
routers is annotated (`get_chat_messages -> list[MessageResponse]`, `create_chat ->
MessageResponse`, `delete_chat -> Response`, all eight in `auth.py`, `me -> MeResponse`,
both webhooks). Without the annotation the checker cannot confirm the handler agrees with
its own `response_model`.

**Fix:** `async def list_chats(...) -> list[ChatResponse]:` and give `root` an explicit
return type (a small `TypedDict` or `dict[str, object]`; `root` declares no
`response_model`, so nothing checks its shape today).

### IN-70: `test_no_further_row_is_added_after_the_failure` never inspects the rows added

**File:** `tests/unit/test_conflict_classification.py:180-183`
**Issue:** The name promises that no row is added after the conflict; the body asserts
`session.flushes == 2`. `_ConflictingSession.added` (`:85`, `:95-96`) records every instance and
is never read, so a row appended after the `IntegrityError` — without a further flush — passes.
The sibling case in `tests/unit/test_create_user_rollback.py:114-118` does make the row
assertion (`session.added == session.added_at_failure`), which is what this name describes.
**Fix:** keep the flush count and add the row check, or rename to
`test_no_second_flush_is_issued_after_the_failure`.

```python
    async def test_no_further_row_is_added_after_the_failure(self):
        _, _, session = await _insert()
        assert session.flushes == 2
        # The name's own claim: `added` is recorded and must stop at the four the arm pended.
        assert [type(instance).__name__ for instance in session.added] == [
            "User", "ExternalIdentity", "StorePurchaseToken", "StorePurchaseToken"]
```

### IN-71: the four-row assertion counts three kinds but never bounds the total

**File:** `tests/unit/test_create_user_rollback.py:100-108`
**Issue:** The class is `TestAllFourRowsAreAddedInOneTransaction` and the docstring says "One
transaction over all four rows". The body asserts `kinds.count(User) == 1`,
`kinds.count(ExternalIdentity) == 1`, `kinds.count(StorePurchaseToken) == 2` — and never
`len(kinds) == 4`. A fifth pending row of a fourth type passes unnoticed, which is the case where
"one transaction over all four rows" has quietly become five.
**Fix:** add the bound.

```python
        kinds = [type(instance) for instance in session.added_at_failure]
        # The count, not only the three memberships: a fourth kind is a new row in this transaction.
        assert len(kinds) == 4
        assert kinds.count(User) == 1
```

### IN-72: the module-level-collection walk does not match a comprehension

**File:** `tests/unit/test_challenge_endpoint.py:285-300` (control at `:309-315`)
**Issue:** `_module_level_collections` matches `ast.List | ast.Set | ast.Dict | ast.Tuple`
displays and calls to `_COLLECTION_BUILDERS`. It does not match `ast.ListComp`, `ast.SetComp`,
`ast.DictComp` or `ast.GeneratorExp`, so a re-introduced module-level operation list written as
`_ISSUABLE = [name for name in ("create_user", "sync")]` passes
`test_the_router_module_declares_no_module_level_collection`. WR-65 widened this walk once
already — for the annotated binding and the constructor call — and the control at `:309-315`
covers only the three spellings the walk already handles, so it cannot reveal the fourth.
**Fix:** add the comprehension nodes to the match and to the control's source.

```python
_COMPREHENSIONS = ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp

builds_a_collection = (isinstance(node.value, ast.List | ast.Set | ast.Dict | ast.Tuple)
                       or isinstance(node.value, _COMPREHENSIONS)
                       or (isinstance(node.value, ast.Call)
                           and getattr(node.value.func, "id", None) in _COLLECTION_BUILDERS))
```

### IN-73: two config cases build their environment from the developer's own, while the rest of the file is hermetic

**File:** `tests/unit/test_config.py:135-136`, `tests/unit/test_config.py:150-151`
**Issue:** `test_main_config_loads_yaml_and_content` and `test_main_config_missing_file` use
`env_clean = {k: v for k, v in os.environ.items() if k not in _DOTENV_KEYS}` with `clear=True` —
that is, the whole ambient environment minus `CONFIG_DIR`. Every other case in the file uses
`patch.dict(os.environ, _ENV_SECRETS, clear=True)`, and the file's own comment at `:42-43` says
the synthetic values exist "so these cases ignore a developer's environment". These two do not.
`EnvironmentConfig` reads `CONFIG_FILENAME`, `PROMPT_FILENAME` and `EXAMPLES_FILENAME` from the
environment (`config.py:161-163`), so any of those three exported in a shell turns
`test_main_config_loads_yaml_and_content` into a `FileNotFoundError` that reads as a config-loader
regression. (Nested `AppConfig` fields are safe here only because the init source deep-merges over
the env source — `MODEL_NAME=leaked` was tried and did not change the result.)
**Fix:** use the same hermetic base the rest of the file uses.

```python
    with patch.dict(os.environ, _ENV_SECRETS, clear=True):
```

### IN-74: `test_adapter_interfaces._run` duplicates `error_tree.fresh_interpreter`

**File:** `tests/unit/test_adapter_interfaces.py:30-31`; original at `tests/unit/error_tree.py:22-26`
**Issue:** `error_tree.py` exists precisely to hold "the fresh-interpreter runner its subprocess
cases share" (module docstring, `:1`), including a named `SUBPROCESS_TIMEOUT_SECONDS = 120` with a
recorded reason. `test_adapter_interfaces.py` re-declares the same two-line runner with the
timeout inlined as a bare `120` and without the `PYTHONPATH` propagation. It works today only
because its snippets import the installed package rather than anything under `tests/`; a future
snippet that imports a test helper fails with an unhelpful `ModuleNotFoundError`.
`test_claim_ordering.py:126-127` carries a third copy of the same helper.
**Fix:** import the shared runner.

```python
from unit.error_tree import fresh_interpreter as _run
```

### IN-95: A frozen-dataclass case catches any exception, including one from its own setup

**File:** `tests/unit/test_identity_accessors.py:330-332`

**Issue:**
```python
def test_a_frozen_identity_cannot_be_relinked(self):
    with pytest.raises(Exception):
        _unlinked().user = _rows()[0]
```
The right-hand side is evaluated first. If `_rows()` ever raises — a model field renamed, a
validator added — the case passes without touching the frozen attribute it is named for.
The sibling above it already asserts `Identity.__dataclass_params__.frozen`, so this one is
the behavioural half and should name the exception.

**Fix:**
```python
import dataclasses

def test_a_frozen_identity_cannot_be_relinked(self):
    identity, user = _unlinked(), _rows()[0]   # built before the assertion window
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.user = user  # ty: ignore[invalid-assignment]
```

### IN-96: Four retry cases request the `spy` fixture, which builds a `BreakerSpy` on a policy they discard

**File:** `tests/unit/test_resilience_retry.py:157`, `:363`, `:374`, `:385`

**Issue:**
Each of these takes `spy`, which wraps the module `policy` fixture's breaker, then
immediately builds its own `ResiliencePolicy` and its own `BreakerSpy(policy)`. The
injected `spy` is never read. It costs a throwaway policy per case and, more importantly,
reads as though the assertions below it are about that spy's counts when they are not.

**Fix:** drop `spy` from those four signatures; keep `sleeps`, which they do need.

### IN-97: A decoder case requests the logging spy and asserts nothing about it

**File:** `tests/unit/test_google_play_notifications.py:315-316`

**Issue:**
```python
def test_the_decoder_itself_answers_none_rather_than_raising(self, play_logs):
    assert developer_notification_from("this is not base64 at all!!") is None
```
Every other user of `play_logs` in the file asserts on the records. Here the spy is
inert — the case would read identically without it, and its presence suggests a record
assertion that was dropped. The undecodable-body record is in fact asserted by the
parametrised case just above it, so either drop the parameter or add the record here.

**Fix:**
```python
def test_the_decoder_itself_answers_none_rather_than_raising(self, play_logs):
    assert developer_notification_from("this is not base64 at all!!") is None
    assert play_logs.records("error") == [("google_play_message_undecodable", {})]
```

### IN-98: The "written exactly once" period check matches only the double-quoted spelling

**File:** `tests/unit/test_monthly_period.py:11`, `:41-43`

**Issue:**
`FORMAT = '"%Y-%m"'` and the walk is a substring test over the file text. A second
derivation written as `'%Y-%m'` or as an f-string format spec (`f"{instant:%Y-%m}"`) is not
found, so `test_only_the_one_function_formats_a_period` would still pass with a second copy
present — which is exactly the state the class docstring says caused the original defect
("Five copies is what let two of them each claim to be the only one"). The double-quote
convention is enforced by formatting today, so this is latent rather than live.

**Fix:** match the bare directive and exclude the one longer format that legitimately
contains it.

```python
DIRECTIVE = "%Y-%m"
# `logs.py`'s timestamper is a different format that contains this one as a prefix.
ALLOWED_ELSEWHERE = {SRC / "api" / "logs.py"}

def _files_formatting_a_period(self) -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py")
                  if DIRECTIVE in path.read_text() and path not in ALLOWED_ELSEWHERE)
```

### IN-115: a no-op secret assertion in the App Store log-hygiene walk

**File:** `tests/e2e/test_app_store_webhook.py:121, 580-588`

**Issue:** `SENSITIVE_VALUES = (ENVELOPE, TOKEN, OTHER_TOKEN, STORE_TOKEN)`, and the hygiene case asserts each is absent from the rendered log records. But `_drive_every_recording_arm` (lines 554-566) puts only `ENVELOPE`, `STORE_TOKEN` and `OTHER_TOKEN` on the wire — `TOKEN` is used exclusively by `TestAChangedAttributionIsRefusedAndNothingIsWritten` and never reaches this walk. `assert TOKEN not in rendered` therefore cannot fail, in this build or any future one, and gives the class docstring's "**both** attribution tokens" claim more credit than it earns.

**Fix:** Either drop `TOKEN` from `SENSITIVE_VALUES`, or drive the walk with `TOKEN` in place of `OTHER_TOKEN`'s partner so all four values genuinely travel.

### IN-116: test modules import each other's private helpers and fixtures

**File:** `tests/schema/test_grant_locks.py:30`; `tests/schema/test_restore_race.py:20`; `tests/schema/test_subscription_race.py:18-19`; `tests/schema/test_registration_pairing.py:14-15`

**Issue:** Four schema modules reach into three others for underscore-prefixed names:

```python
from schema.test_subscription_ingestion import _clean, _notification       # test_grant_locks
from schema.test_claim_race import _RacingSession, read, scalar            # test_restore_race
from schema.test_subscription_ingestion import _notification               # test_subscription_race
from schema.test_create_atomicity import harness as creation_harness       # test_registration_pairing
```

The leading underscore says "module-private", and the import says otherwise. A signature change to `_clean` or `_RacingSession.__init__` breaks modules a reader has no reason to open. I confirmed every module still passes when run alone, so this is coupling rather than breakage — but the fixture re-export in particular (`harness as creation_harness`, needing a `# noqa: F811` on its consumer) is a pattern that will not scale to a fifth borrower.

**Fix:** Promote the genuinely shared pieces to `tests/schema/harness.py` (the `_RacingSession` wrapper, `read`/`scalar`, `_clean`, `_notification`) and drop the underscore from names that three modules use.

### IN-117: two comments describe assertions that are not the assertions made

**File:** `tests/e2e/test_claim_anonymous_grant.py:282`; `tests/e2e/test_claim_registered_grant.py:39`; `tests/e2e/test_restore_subscription.py:626`

**Issue:** Three comments state something the code does not do:

1. `test_claim_anonymous_grant.py:282-283` — *"The revoked row and its **anti-abuse row** are still the only ones"* precedes `assert await _row_counts(...) == (1, 1)`. `_row_counts` (line 171) returns `(grants, usage)`, and this build's migration has no anti-abuse table at all (`migrations/20260818_01_initial-release.sql` declares twelve `core` tables, none of them anti-abuse). The `(1, 1)` is one grant and one usage row.
2. `test_claim_registered_grant.py:39` — *"The same body **as bytes**, so the four refusals are compared on the wire"* precedes `REFUSED_BODY = '{"code":"operation_not_allowed"}'`, a `str` compared against `refusal.text`, which is decoded. The Apple/Google webhook files get this right with a `b'...'` literal compared against `response.content`.
3. `test_restore_subscription.py:626-627` — *"Compared as bytes, so a more helpful field on this body fails here"* precedes `assert refused.text == REFUSED_BODY`, again a `str`.

The comparison is still exact in all three, so nothing is broken — but (2) and (3) claim a stronger property (byte-for-byte on the wire) than `.text` delivers, and (1) will send a reader looking for a table that does not exist.

**Fix:** Correct (1) to name the grant and usage rows. For (2)/(3), either make the constants `bytes` and compare against `.content` — matching the two webhook files and delivering the property the comment claims — or reword the comments.

### IN-118: `TestTheTwoRefusalsOfTheRestoreNotFoundFamily` holds three arms

**File:** `tests/e2e/test_restore_subscription.py:492-590`

**Issue:** The class is named for two refusals and its docstring says *"three causes, one body"*; it contains four cases, the last of which (`test_the_three_arms_of_the_family_answer_the_same_bytes`, line 560) exercises a third arm — the absent-term refusal — that the class name excludes. Line 591 also carries a single blank line before the next class declaration where the file uses two everywhere else.

**Fix:** Rename to `TestTheRestoreNotFoundFamily` (the arm count is already in the docstring and will drift again), and restore the blank line at 591.

---

_Reviewed: 2026-09-09_
_Reviewer: Claude (gsd-code-reviewer) x7, merged by the code-review orchestrator_
_Depth: standard_
