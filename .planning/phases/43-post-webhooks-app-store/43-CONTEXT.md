# Phase 43: POST /webhooks/app-store - Context

**Gathered:** 2026-09-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `POST /webhooks/app-store`. Apple's store server posts a `signedPayload` JWS to it. The route
checks the signature and the certificate chain with Apple's `app-store-server-library`, decodes
the notification, and applies it: the canonical `core.subscriptions` row is upserted, one
`core.store_purchases` row is written once, one `audit.subscription_events` row is appended, and
the subscription-backed `core.access_grants` row with its `core.user_monthly_usage` row is
expired and inserted per term. No Firebase token, no Authorization header, no identity.

**This phase answers APPLEHOOK-02** (D-01). The provider-callback partition is a dedicated router.
Membership is the set of routes on it, and the wiring test counts them by literal.

**This phase owns the service Phase 44 reuses** (D-13 … D-18). The service reads one value type
with our own field names. It imports no Apple type. Phase 44's Google class produces the same type.

**Out of scope:** Google Play (44); restore and the adoption of an unclaimed subscription (45);
every rate-limit entry and vendor budget; any `audit.auth_events` row; a secret URL token, an IP
allowlist, certificate pinning beyond Apple's root, mTLS; online certificate revocation checks.

</domain>

<decisions>
## Implementation Decisions

### The partition

- **D-01: A dedicated router.** `routers/webhooks.py` holds one `APIRouter` whose router-level
  dependency is `verify_app_store_notification`. Membership in the provider-callback partition is
  the set of routes on that router. `tests/unit/test_app_wiring.py` gets a third literal beside
  the two it has: `PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}`. It asserts: the literal
  equals the routes on the webhooks router; each of them declares `verify_app_store_notification`
  by callable identity and declares neither `get_identity` nor `get_linked_identity`; no route
  outside the literal declares it; the public allowlist is still exactly `/health/ready`.
  Widening the partition is a visible one-line edit. Phase 44 adds one route and one literal
  member. — **Reversibility:** costly — Phase 44 inherits the mechanism (PLAYHOOK-03).

- **D-02: Always registered; fails closed when unconfigured.** The router is included in
  `app/main.py` like every other router. When `config.app_store` is incomplete, lifespan logs a
  warning (as `devicecheck_credential_absent` does) and the route answers 503, so Apple retries.
  The route set is the same in every environment, which is what the wiring test assumes: it
  imports the app object, and config loads in lifespan after the routes exist.
  **FLAGGED CONFLICT** against `08-webhook-app-store.md` "not registered at all while Apple's
  store integration is unconfigured" and "startup fails closed if the registered route lacks
  configuration".

- **D-03: The dependency is the admission gate.** `verify_app_store_notification` lives in
  `app/dependencies.py`, takes `Request` and the request body, and is one line:
  `return request.app.state.app_store_notifications.verify(body.signedPayload)`. It runs before
  the handler and before `get_db`, so a bad payload never opens a session. The handler declares
  the same dependency again as a parameter to receive the value; FastAPI resolves it once per
  request, as `get_linked_identity` is resolved on the auth routes. Not `request.state`.

- **D-04: Two error-tree leaves, no new `ErrorCode`.** `NotificationRejected` (401,
  `auth_required`) is one class for every verification failure, so the route is no oracle about
  which check failed; the library's `VerificationStatus` name goes to the log as `stage`.
  `Unavailable` (503, `verification_temporarily_unavailable`) is reused for absent config. Both
  reach `app_error_handler`, so the body is the shared `{code}` shape. **FLAGGED CONFLICT** against
  the brief's "never the shared client-visible error classes": the body shape is shared, the
  classes are the route's own, and no `ErrorCode` member is added. The brief's "plain status"
  cannot be answered any other way here — even a bare `HTTPException` is mapped to the class its
  status declares.

- **D-05: An Authorization header is ignored.** The route never reads it. A valid Firebase ID
  token with a bad payload is 401 like any other bad payload; the wiring proof sends exactly that.

- **D-06: `k8s/templates/httproute-webhooks.yaml` is renamed only.** `/webhooks/apple` becomes
  `/webhooks/app-store`. No rate-limit entries are added. The brief's per-IP and per-URL gateway
  limits are a **flagged deferral** to the v2.1 gateway contract (Phase 35 D-05), not an omission.

### The Apple class

- **D-07: One class, one method, on `app.state`.** `auth/app_store.py` declares
  `AppStoreNotifications` with `verify(signed_payload: str) -> VerifiedNotification`. Lifespan
  builds the library's `SignedDataVerifier` once from `config.app_store` and passes it in;
  when config is incomplete it passes `None`, and `verify` raises `Unavailable` on use, the shape
  `AppleDeviceCheck` already has. `verify` calls the library three times — the envelope
  (`verify_and_decode_notification`), the nested signed transaction, and the nested renewal
  info — catches `VerificationException`, and raises `NotificationRejected(stage=status.name)`.
  It is called inline, not through `run_in_threadpool`: with D-09 there is no I/O in it.
  A Protocol is declared beside the class (D-24), as `DeviceCheckAdapter` is.
  — **Reversibility:** costly — Phase 44's class must match the Protocol and the value type.

- **D-08: The value type is ours.** `VerifiedNotification` is a frozen dataclass beside the class,
  with our field names: `provider`, `notification_uuid`, `event_type` (Apple's type as received),
  and an optional transaction part — `external_id` (`originalTransactionId`), `transaction_id`,
  `product_id`, `attribution_token` (`appAccountToken`, may be absent), `purchased_at`,
  `expires_at`, `revoked_at`, `grace_period_expires_at`, `in_billing_retry`. The service reads only
  this. A TEST or summary notification has no transaction part (D-22).

- **D-09: No online revocation check.** `enable_online_checks=False`. Verification is then pure
  computation on the `x5c` chain, with no per-request network call on the admission path (the
  Phase 35 barrier rule). Divergence from Apple's production guidance, recorded with its reason:
  a revoked Apple intermediate is rare, and the exposure is one wrongly accepted notification for
  a sub-$5 subscription.

- **D-10: Apple's root CA is vendored.** The Apple Root CA G3 DER file is committed under
  `config/`, and `AppStoreConfig.root_certificate_path` defaults to it. It is public, not a
  secret; pinning Apple's own root is what the brief allows. A rotation is a commit.

- **D-11: `AppStoreConfig` in `config.py`,** every field optional like `DeviceCheckConfig`:
  `bundle_id`, `app_apple_id` (the library requires it for Production), `environment`
  (`sandbox` | `production`, **no default** — `None` means unconfigured, because Sandbox
  purchases are free to anyone with a test build and Apple signs their notifications too, so a
  production deployment must state `production` in a visible line), `root_certificate_path`
  (defaults to D-10's file), and `products` (D-14).

### The service

- **D-12: Handler, service, crud.** The handler is thin: it takes the value from the dependency
  and calls the service. The service is earned here: one transaction that upserts the
  subscription, writes the purchase row, appends the event, expires the old grant and inserts the
  new one with its usage row. Crud writes rows and receives plain values, never a payload.
  `commit()` lives in the service, so 200 is returned only after the commit.

- **D-13: Status from the dates.** One function derives `core.subscriptions.status` from
  `revoked_at`, `expires_at`, `grace_period_expires_at` and `in_billing_retry` against
  `evaluated_at`. The notification type is only recorded as `event_type`. An unknown or new type
  costs nothing.

- **D-14: Product → tier is a config map.** `AppStoreConfig.products: dict[str, str]` maps a store
  product id to a `core.access_tiers.id`. A verified notification whose product id is not in the
  map is refused with 500 (D-21). Only `paid` exists today; a second tier is one more line.

- **D-15: A term is the grant's `ends_at`.** The subscription grant row records the term:
  `starts_at` = the term's purchase date, `ends_at` = `expires_at`. "Same term" is an active grant
  for this subscription with the same `ends_at`, and it is an idempotent no-op before any grant or
  usage write. A renewal flips the time-ended active row to `expired` and inserts the next term's
  row with a fresh usage row (`monthly_used = 0`, `monthly_period` = `evaluated_at`'s month).
  No new column.

- **D-16: Grant locks and unique indexes serialize.** The user is resolved from
  `attribution_token` through `core.store_purchase_tokens (provider, identity_value)` before the
  transaction. Inside it: lock the user's grant rows ascending, then their usage rows (the fixed
  order); read the event row (D-20); upsert the subscription by `(provider, external_id)`; insert
  the purchase row once; append the event; expire-then-insert the grant. With no user
  (unattributed) there is nothing to lock, and `ix_subscriptions_provider_external_id` plus
  `notification_uuid UNIQUE` arbitrate. No subscription-row lock: it would be a lock tier ahead
  of the grant locks, and it does not exist on the first insert.

- **D-17: The unattributed case is written as the brief says.** No token, or a token resolving to
  no binding: the subscription is inserted with `user_id NULL`, the purchase row with
  `purchase_user_id NULL` and `resolved_token_value NULL` (a server-generated UUID as
  `identity_value` when the store gives none), no grant and no usage row. Restore links it later.

- **D-18: The lapsed subscriber ends with zero credits — accepted.** A buyer's active free grant is
  expired (never deleted) before the paid grant is inserted, and the free slot is lifetime-once
  (`ix_access_grants_one_free_grant_per_user_source`). When the subscription later leaves the
  entitled set, its grant is marked `expired` or `revoked` with `ends_at` in the same transaction,
  and the user holds no grant at all. Ingestion never reactivates a grant; restore (Phase 45) is
  the only path back. A product consequence, not a divergence.

- **D-19: The rest of the brief's lifecycle rules ship as written:** newest verified purchase wins
  across two different subscriptions (the same expire-then-insert path); repeat events for an
  existing `(provider, external_id)` update the canonical row in place with no second purchase
  row; a new `external_id` under the same token inserts a new purchase row; a status, tier or
  owner change updates the grant in the same transaction or the deferrable FK fails the commit.

### Replay and responses

- **D-20: The event row is read first, then every 23505 is a race.** Inside the transaction,
  after the grant locks, the service reads `audit.subscription_events` by `notification_uuid`.
  Found: nothing is written, the response is 200. Not found: the writes run, and any SQLSTATE
  23505 after that is a lost race — roll back, answer 5xx, and Apple's resend finds the row and
  answers 200. No constraint name is read (Phase 42-07).

- **D-21: Two `InternalError` leaves answer 500.** `AttributionConflict` (an existing purchase
  row's `identity_value` differs from the token presented) and `UnmappedStoreProduct` (D-14),
  each logged at ERROR with `provider` and `external_id`, nothing written. Apple retries on its
  schedule and lists the failure in App Store Connect; for the missing mapping that is the right
  loop — an operator adds the line and the next retry succeeds.

- **D-22: A notification with no transaction answers 200.** TEST and the summary types verify but
  carry nothing to write (`audit.subscription_events.subscription_id` is NOT NULL). The handler
  answers 200, writes nothing, and logs the type at INFO.

- **D-23: 5xx, never 200, on internal failure.** A failed commit, a lost race (D-20), the two
  refusals (D-21) and absent config (D-02) all answer 5xx so Apple's retry schedule covers them.

- **D-24: Real chain in unit tests, scripted fake in e2e.** Unit tests generate a throwaway root
  CA, intermediate and leaf, build `AppStoreNotifications` with that root, and mint real signed
  payloads, so the library's chain check runs for real; a control proves the vendored Apple root
  refuses them. The e2e route and service cases script a fake behind the Protocol, as the
  DeviceCheck fake in `tests/e2e/conftest.py` does. Database behaviour — the writer's outcomes,
  the replay, the race — is measured on real PostgreSQL in `tests/schema`, as 42-07 did.

### Comment style

- **D-25: Every comment this phase writes is ASD-STE100, inline where possible.** Short sentences,
  one idea each, the same word for the same thing. This is in addition to `AGENTS.md`
  § "Comments and docstrings" (only where necessary, one line each).

### Documentation deliverables

- **D-26: Amend APPLEHOOK-01 and APPLEHOOK-02 in `.planning/REQUIREMENTS.md`** with dated
  entries: D-01 as the answer to APPLEHOOK-02; D-02, D-04 and D-06 as flagged conflicts against
  `08-webhook-app-store.md`; D-09 as a divergence from Apple's guidance; the obligations already
  dead before this phase (rate limits and budgets, the audit row, the route registry, the
  foundation store-verification interface). Update the header's conflict counts. Mark the ROADMAP
  criterion 3 answered.
- **D-27: `08-webhook-app-store.md` and `SHARED-INVARIANTS.md` are NOT edited.** Divergences live
  in REQUIREMENTS.md.

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `08-webhook-app-store.md` alone will try to build all of these. **None exists.**

- **No route registry, no `Category`, no `RouteMetadata`, no `VERIFIERS`** (Phase 37.1 D-06/D-10).
  D-01 is the replacement.
- **No foundation store-verification interface** (Phase 37.2 D-09). D-07 declares it beside its
  first implementation.
- **No rate limiting and no vendor budgets, backend or gateway** (Phase 35 D-05). D-06.
- **No `audit.auth_events` row, no operation enum value, no audit result value** (37.1 D-01,
  38 D-03). Log event names come from exception class names.
- **Outcomes are exception classes, never an enum** (Phase 37.3 D-12). D-04, D-21.
- **`IntegrityError` is caught by SQLSTATE 23505 only, read off `orig.__cause__.sqlstate`,
  never by constraint name** (Phase 42-07). D-20.
- **Lock order:** grant rows ascending, then usage rows; no other tier ahead (SHARED-INVARIANTS
  § Locks). D-16.
- **No network call while a lock is held or a transaction is open.** Verification runs in the
  dependency, before `get_db`.
- **One captured instant per request** (`get_evaluated_at`).
- **`commit()` and `rollback()` live in `services/`** (AGENTS.md).
- **No success log line** (Phase 38 D-02); `RequestLoggingMiddleware` writes the one request line.

### Claude's Discretion

- The exact field set of `VerifiedNotification` beyond D-08, and the request model's name
  (`signedPayload` is the one field).
- The service's file and class name (`services/subscriptions.py` is the natural home), and the
  crud module for `core.subscriptions`, `core.store_purchases` and `audit.subscription_events`
  (models go in `tables/purchases.py` beside `StorePurchaseToken`).
- The name of the Protocol beside `AppStoreNotifications`, and where the throwaway test chain is
  generated.
- Whether a mid-term tier change updates `tier_id` in place or flips and inserts; moot with one
  paid tier. Record the choice.
- Plan wave order. The `k8s/` rename and the vendored certificate are independent of the code.
- The log field names on the two 500 leaves and the INFO line of D-22.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding specification (overrides phase briefs on conflict)

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — § "Global
  deletions" (no wildcard or prefix membership; the control D-01 makes real), § "Locks and
  transactions" (D-16), § "Grants and evaluation time" (D-15, D-18), § "Fail-closed defaults".
  § "Rate limits" is dead. Not edited (D-27).
- `/home/init/native-speaker/specs/auth-refactor-phases/08-webhook-app-store.md` — the brief,
  verbatim, **not edited** (D-27). Read "This phase adds", the ingestion transaction, the
  lifecycle rules, "Security hardenings" and DELETIONS. **Its route registry, its foundation
  store-verification interface, its "not registered while unconfigured", its "never the shared
  error classes", and its gateway rate limits are diverged from or dead** — read "Carried
  forward" first.

### The next consumer of this phase's service

- `/home/init/native-speaker/specs/auth-refactor-phases/09-webhook-google-play-rtdn.md` — Phase
  44 calls the service D-12 builds and produces the value type D-08 declares; its "This phase
  adds" names what the Google class must yield.
- `/home/init/native-speaker/specs/auth-refactor-phases/10-restore-subscription.md` § "This
  phase adds" — restore adopts the unclaimed subscription D-17 writes.

### The source specification

- `/home/init/native-speaker/specs/auth-refactor/06-schema-reference.md` — § `core.subscriptions`
  (:772, :800), § `core.store_purchases`, § `core.store_purchase_tokens`,
  § `audit.subscription_events` (:1408-1421), § `core.access_grants` (:1024 — the ingestion
  grant rule).
- `/home/init/native-speaker/specs/auth-refactor/04-subscription-restore-and-entitlement-transfer.md`
  — owns the `notification_uuid` deduplication and ingestion rules the schema reference points at.

### Project planning

- `.planning/REQUIREMENTS.md` § APPLEHOOK (:363-377) — **this phase appends its dated amendments
  here** (D-26). § PLAYHOOK (:379-392) inherits D-01.
- `.planning/ROADMAP.md` Phase 43 (:636-646) — criterion 3 is answered by D-01.
- `.planning/phases/42-post-auth-claim-registered-grant/42-CONTEXT.md` — D-10 (the expire-then-
  insert order and the flush boundary), D-13 (the two-connection race harness), and the
  "Carried forward" list.
- `.planning/phases/41-post-auth-claim-anonymous-grant/41-CONTEXT.md` — the DeviceCheck class,
  its Protocol beside it, and the fake in e2e: the model for D-07 and D-24.
- `.planning/STATE.md` § Decisions — the 42-07 entries on `ActivationOutcome` and SQLSTATE 23505.

### Repo conventions and the deployment

- `ns-api-gateway/AGENTS.md` — § "Package layout", § "Function shape", § "Comments and
  docstrings" (D-25 adds to it).
- `k8s/templates/httproute-webhooks.yaml` — the path D-06 renames;
  `k8s/templates/security-policy.yaml` — already excludes the webhook route from the JWT policy.
- `tests/unit/test_app_wiring.py` — the two literals D-01 joins.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `auth/devicecheck.py` — `AppleDeviceCheck` with `DeviceCheckAdapter` beside it, `BitState` as
  the frozen value, absent credentials raising `Unavailable` on use: the model for D-07/D-08.
  Note its import fence: `auth/adapters.py` may import only stdlib and this project
  (`tests/unit/test_adapter_interfaces.py`), so the new class lives in its own module.
- `app/lifespan.py` — builds each client once on `app.state` and warns on absent credentials;
  D-02 and D-07 add `app_store_notifications` there.
- `app/dependencies.py` — every dependency lives here; `get_identity` is the shape of a
  router-level gate; `get_evaluated_at` is the one instant.
- `errors.py` — `ProviderLookupError` leaves (`stage`, `cause` log fields) for
  `NotificationRejected`; `Unavailable` reused; `InternalError` leaves
  (`MissingUsageRowError`, `UnknownTierError`) for D-21.
- `crud/grants.py` — `lock_effective_grants`, `lock_usage`, `activate_registered_account_grant`
  (expire-then-insert with an explicit flush boundary), `ActivationOutcome`, the SQLSTATE read.
- `crud/purchases.py::PurchasesDB` and `tables/purchases.py::StorePurchaseToken`,
  `PurchaseProvider` (`apple` | `google_play`) — the token resolution D-16 needs; rows are
  written at user creation in `crud/identities.py:107`.
- `tables/grants.py` — `AccessGrant`, `AccessGrantSource.subscription`, `UserMonthlyUsage`,
  `AccessTier`. Note: the four generated columns are omitted from the model (36-01).
- `services/quota.py`, `services/sync.py` — the `monthly_period` rollover D-15's fresh usage row
  must agree with.
- `migrations/20260818_01_initial-release.sql` :128-207 — the four tables already exist; no
  migration edit is expected.
- `tests/e2e/conftest.py` — the scripted DeviceCheck fake (D-24); `tests/schema/test_claim_race.py`
  — the two-connection race harness D-20 extends.
- `appstoreserverlibrary.signed_data_verifier.SignedDataVerifier` (3.0.0, installed) —
  `__init__(root_certificates: list[bytes], enable_online_checks, environment, bundle_id,
  app_apple_id)`; raises `ValueError` for Production without `app_apple_id`; `VerificationStatus`
  names the failure.

### Established Patterns

- Layering per `AGENTS.md`; a service is earned by complexity (D-12).
- Fail-closed reads raise in `crud/`; `commit()` in `services/`.
- A `try` holds only the statement that can raise; no nested `try`.
- Structured-log labels from a closed set, never a token or provider text.
- Divergences are recorded under the requirement, never by editing the specification.

### Integration Points

- New: `routers/webhooks.py`, `auth/app_store.py`, `services/subscriptions.py` (name at
  discretion), a crud module, models in `tables/purchases.py`, `AppStoreConfig` in `config.py`,
  the vendored root certificate under `config/`, `config/config.yaml` (`app_store.products`),
  `.env.example` (the Apple block).
- Edited: `app/main.py` (include the router), `app/lifespan.py`, `app/dependencies.py`,
  `errors.py` (three leaves), `routers/__init__.py`, `tests/unit/test_app_wiring.py` (the third
  literal), `k8s/templates/httproute-webhooks.yaml`, `.planning/REQUIREMENTS.md`,
  `.planning/STATE.md`.

### Naming Hazard

Four things are called "apple": `IdentityProvider.apple`, `PurchaseProvider.apple`, Apple as the
DeviceCheck vendor, and Apple as the store server. Keep them apart at every seam.

</code_context>

<specifics>
## Specific Ideas

- **Use the codebase's own terms.** The developer had to ask four times what "ingestion module",
  "seam", "verifier" and "adapter" meant. Name things by their layer: dependency, handler,
  service, crud, config, lifespan, and the class on `app.state`. Do not mention a layer the
  question does not touch.
- **Give the best option, not the smallest one that works.** "Many things work; it doesn't mean
  you should give me the worse option." D-07 is a class because it is better, not because a
  function was impossible.
- **Keep one answer.** Switching between a function and a class across turns cost the discussion
  more than either choice.
- **Ask one thing at a time.** Bundling the "next area" check with open questions made an
  unanswered question look answered.
- **ASD-STE100** for prose and, this phase, for comments (D-25).
- **Verify before asserting; follow the chain to the root** — Phase 42 notes still hold.

</specifics>

<deferred>
## Deferred Ideas

- **Gateway per-IP and per-URL limits on `/webhooks/app-store`** — the brief requires them; the
  v2.1 gateway contract owns every gateway limit (D-06).
- **Online certificate revocation checks** — off (D-09); reopen if the threat model changes.
- **A way back to a free-tier grant for a lapsed subscriber** — D-18 accepts zero credits; any
  path reopens the lifetime slot and needs its own rules.
- **A mid-term tier change policy** — moot with one paid tier; recorded at discretion.
- **Google Play** — Phase 44; **restore and adoption** — Phase 45.
- **One test asserting each Python enum's values equal its `core.*` type's labels** — still
  deferred.

### Reviewed Todos (not folded)

- `message-ordering-is-unspecified` (score 0.4) — chats; unrelated.
- `secret-manager-integration` (score 0.2) — config; declined. This phase adds no secret: the
  root certificate, the bundle id and the app id are public values.

</deferred>

---

*Phase: 43-post-webhooks-app-store*
*Context gathered: 2026-09-04*
