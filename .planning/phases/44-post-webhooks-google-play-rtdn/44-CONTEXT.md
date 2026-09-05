# Phase 44: POST /webhooks/google-play/rtdn - Context

**Gathered:** 2026-09-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `POST /webhooks/google-play/rtdn`. Google's Cloud Pub/Sub pushes one RTDN message to it with
a Google-signed OIDC bearer token. The route verifies that token, decodes the message, calls
`purchases.subscriptionsv2.get` for the authoritative state, and hands one `VerifiedNotification`
to the service Phase 43 built. The message is a trigger only; every written value comes from the
Play response. It is the second and last route in the provider-callback partition.

**This phase answers PLAYHOOK-03** by inheriting Phase 43 D-01: one more route on
`webhooks_router`, one more member in the wiring test's literal. No second partition mechanism.

**This phase amends four Phase 43 decisions** because they were written for one provider:
D-01 (the router-level gate), D-13 (status from dates), D-14 (the products map in the service),
and the location of the value type. Each amendment is recorded below with what it replaces.

**Out of scope:** restore and the adoption of an unclaimed subscription (45); the feature-sliced
repository restructure (44.1, new); any App Store Server API call on the Apple path; every
rate-limit entry and vendor budget; any `audit.auth_events` row; a secret URL token, an IP
allowlist, mTLS; provisioning the Pub/Sub topic and push subscription themselves.

</domain>

<decisions>
## Implementation Decisions

### The router and the partition

- **D-01: No router-level gate.** `webhooks_router` declares no `dependencies=`. Each route
  declares its own verifier as a handler parameter, and declares it **first**, so it resolves
  before `get_db` takes a pooled connection. Replaces the router-level
  `Depends(verify_app_store_notification)` of 43 D-01, which parsed Apple's body for every route.
  Membership is still the set of routes on the router. — **Reversibility:** costly — both
  handlers, the wiring test, and 43-CONTEXT's description of the partition.

- **D-02: The wiring test pins the order.** `tests/unit/test_app_wiring.py` asserts, for every
  callback route, that its verifier is element 0 of `route.dependant.dependencies` and that
  `get_db` resolves after it. Nothing is added to `src/` for this; a reordered parameter list
  fails a named test instead of quietly costing a connection per junk request.

- **D-03: One dict literal counts the partition.** `PROVIDER_CALLBACK_VERIFIERS` maps each exact
  path to its verifier callable; `PROVIDER_CALLBACK_PATHS` is its key set. The test asserts the
  router's routes equal the keys, each route declares its own mapped verifier, and neither
  verifier appears off the partition. The public allowlist stays exactly `/health/ready`.

- **D-04: A verified message with an undecodable payload answers 200.** The request model
  validates only the transport envelope: `message.messageId` present, `message.data` a non-empty
  string. Base64 and JSON decoding happen **after** the token check, inside the dependency. A
  decode failure logs at ERROR and answers 200 with nothing written. Pub/Sub reads any 4xx as
  permanent and drops the message; a 5xx would redeliver a payload that can never parse until
  retention expires.

- **D-05: A verified RTDN that is not a `subscriptionNotification` answers 200.**
  `testNotification`, `oneTimeProductNotification` and `voidedPurchaseNotification` write
  nothing, make no Play call, and log the type at INFO — the 43 D-22 rule. A refund reaches us
  separately as a `subscriptionNotification` of type `SUBSCRIPTION_REVOKED` (12).

### The Google classes and the value type

- **D-06: `VerifiedNotification` moves to `auth/store_notifications.py`.** `auth/app_store.py`
  and the new `auth/google_play.py` both import it; neither provider module imports the other.
  Phase 44.1 later moves that file to `webhooks/notifications.py` as part of the restructure.

- **D-07: `google_play.py` declares its own Protocol beside its implementation.**
  `StoreNotificationVerifier` (sync, one string, no I/O) stays Apple's. The two providers share
  the value type and the service — which is what PLAYHOOK-02 binds — not the call signature.
  Phase 37.2 D-09: an interface is declared beside its first implementation.

- **D-08: Two classes on `app.state` behind one dependency.** `verify_google_play_notification`
  in `app/dependencies.py` calls, in order: a class that verifies the Pub/Sub OIDC bearer and
  raises `NotificationRejected` on any failure; then a class that calls
  `purchases.subscriptionsv2.get` and returns `VerifiedNotification`. They are separate because
  they talk to two Google systems with two failure modes, and because Phase 45's restore route
  needs the Play lookup alone with no Pub/Sub token to check. Class names at discretion.
  — **Reversibility:** costly — Phase 45 builds on the second class.

- **D-09: The bearer check extends `JWTVerifier`.** `auth/jwt_verifier.py` gains an optional
  required-claims argument and returns the verified payload beside `VerifiedClaims`, so the
  Google instance can enforce `email == <configured push service account>` and
  `email_verified is true`. One JWKS fetch, one negative cache, one never-raises discipline.
  The Firebase instance's tests stay green **unchanged**. Google's instance: issuer
  `https://accounts.google.com`, JWKS `https://www.googleapis.com/oauth2/v3/certs`, audience the
  exact configured value, RS256 only. It runs via `run_in_threadpool` as the Firebase one does.

### The subscription key and the status

- **D-10: `external_id` is the purchase token.** It is what `purchases.subscriptionsv2.get`
  accepts as its only handle, so a backend that does not store it can never ask Google about that
  subscription again. Stable across renewals; a new token on upgrade or resignup, which
  expire-then-insert already handles (43 D-19). **FLAGGED DIVERGENCE** from
  `09-webhook-google-play-rtdn.md` DELETIONS: *"No raw purchase tokens … persisted outside the
  minimum verification path."* Recorded under PLAYHOOK-01 as a knowing divergence on the
  43 D-02/D-04/D-06 precedent. — **Reversibility:** one-way — rows are keyed on it;
  changing the key is a data migration of `core.subscriptions` and `core.store_purchases`.

- **D-11: Both providers map a store status word; `status_at` is deleted.** Amends 43 D-13.
  - Apple: the signed envelope's `data.status` — `ACTIVE=1, EXPIRED=2, BILLING_RETRY=3,
    BILLING_GRACE_PERIOD=4, REVOKED=5` — is one-to-one with `core.subscription_status`. No
    API call; no notification-type table. Not the twenty-entry event table 43 turned down.
  - Google: `subscriptionState`, seven to five: `ACTIVE → active`; `IN_GRACE_PERIOD →
    grace_period`; `ON_HOLD → billing_retry` (the same condition as Apple's billing retry after
    grace); `PAUSED → expired` (our enum has no pause; the auto-resume arrives as a fresh
    `ACTIVE` and, under never-silently-reactivate, the user taps Restore); `CANCELED → active`
    while a line item's `expiryTime` is after `evaluated_at`, else `expired`; `EXPIRED`,
    `PENDING`, `PENDING_PURCHASE_CANCELED`, `UNSPECIFIED → expired`.
  - The mapping lives in each provider's class. `VerifiedNotification` carries the finished
    `status`; the service only writes it. The notification type is still recorded only as
    `event_type`.

- **D-12: The out-of-order guard runs unchanged for both providers.** Google's class puts
  `DeveloperNotification.eventTimeMillis` — the moment the event happened on Play — into
  `signed_at`, and the existing `store_signed_at` comparison in `services/subscriptions.py`
  refuses an older message for Google as it does for Apple. The `store_notification_superseded`
  log line goes from INFO to **WARNING**. Nothing is lost by refusing a Google straggler: the
  newer message already applied live state, and any later change sends its own RTDN. Rejected:
  a "state fetched live" flag on the value type; a second timestamp; Pub/Sub's `publishTime`.

- **D-13: Apple stays as shipped.** No App Store Server API call is added to the Apple path
  (`Get All Subscription Statuses` was considered and declined: a new App Store Connect key, a
  network call on an admission path that has none, and rework of a verified phase).

### The credential, the client and the config

- **D-14: Application Default Credentials.** `google.auth.default()` with the
  `https://www.googleapis.com/auth/androidpublisher` scope — the identity Firebase Admin already
  runs on (`auth/firebase.py:48-55`). No key file, no new secret; one grant in Play Console.
  An absent credential logs a warning at boot and the route answers 503, the shape of
  `firebase_admin_credential_absent` and 43 D-02.

- **D-15: `httpx` makes the one GET; `google-auth` mints the token.** `google-auth` is added to
  `pyproject.toml` as a **direct** dependency (today it arrives only through `firebase-admin`).
  The token refresh is synchronous and runs in the threadpool; the GET is async on the loop.
  One response model in this project's field names; the Play response is never persisted or
  logged. The call happens in the dependency, before `get_db`, so no network call ever runs
  under a lock or inside a transaction — structurally, as SHARED-INVARIANTS § "Locks" requires.

- **D-16: The product→tier map is applied in each provider's class.** `GooglePlayConfig.products`
  and `AppStoreConfig.products` each feed their own class; the class resolves `tier_id` from the
  line item's `productId` (Apple: `productId`) and raises `UnmappedStoreProduct` itself.
  `VerifiedNotification` carries `tier_id`; `SubscriptionsService` drops its `products`
  argument. Amends the **location** of 43 D-14, not its rule.

- **D-17: A redelivery pays one Play call.** The dependency reads no database row; the replay rule
  stays in the service under the locks (43 D-20). One extra call per redelivery against a
  200,000-per-day quota is accepted.

- **D-18: `GooglePlayConfig` in `config.py`,** every field optional like `AppStoreConfig`:
  `package_name`, `push_audience` (the exact `aud`), `push_service_account_email`, and
  `products`. Incomplete → 503 (43 D-02 inherited, and its **flagged conflict** with the brief's
  "not registered while unconfigured" is inherited too). The Google class refuses a message
  whose `packageName` differs from `package_name` before any Play call.

- **D-19: `k8s/templates/httproute-webhooks.yaml` gains one exact-path match** for
  `/webhooks/google-play/rtdn`, `POST`. The Authorization header must reach the backend
  unchanged; the route stays outside the JWT SecurityPolicy as the Apple one is. No rate-limit
  entries (43 D-06's flagged deferral to the v2.1 gateway contract, inherited).

### Responses

- **D-20: Plain status, shared body — inherited.** 401 `NotificationRejected` for every bearer
  failure with the reason as a log `stage`; 503 `Unavailable` for absent config or credential;
  500 for `AttributionConflict`, `UnmappedStoreProduct`, a lost race, or a failed Play call so
  Pub/Sub redelivers; 200 only after commit. The body is the shared `{code}` shape — 43 D-04's
  flagged conflict with the brief's "never the shared client-visible error classes" is
  inherited and counted again against `09-webhook-google-play-rtdn.md`.

### Documentation deliverables

- **D-21: Amend PLAYHOOK-01 … PLAYHOOK-03 in `.planning/REQUIREMENTS.md`** with dated entries:
  PLAYHOOK-03 **closed** by inheriting 43 D-01 with one literal member (D-03); D-10 as a new
  flagged divergence; the three inherited flagged conflicts (always-registered/503, shared body,
  no gateway limits) counted against the 09 brief's own lines; the obligations already dead
  before this phase (route registry, foundation store-verification interface, the audit row,
  rate limits and budgets). Record the amendments to 43 D-13 and D-14 as dated notes under
  APPLEHOOK-01 and in `STATE.md` § Decisions. Update the header's counts. Mark ROADMAP
  criterion 3 answered.
- **D-22: `09-webhook-google-play-rtdn.md`, `08-webhook-app-store.md` and `SHARED-INVARIANTS.md`
  are NOT edited** (43 D-27). Divergences live in REQUIREMENTS.md.
- **D-23: Every comment this phase writes is ASD-STE100, inline where possible** (43 D-25).

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `09-webhook-google-play-rtdn.md` alone will try to build all of these.
**None exists.**

- **No route registry, no `Category`, no `RouteMetadata`, no `VERIFIERS`, no named-verifier
  table** (Phase 37.1 D-06/D-10). 43 D-01 as amended by D-01/D-03 here is the replacement.
- **No foundation store-verification interface** (Phase 37.2 D-09). D-07 declares one beside
  its first implementation.
- **No rate limiting and no vendor budgets, backend or gateway** (Phase 35 D-05). D-19.
- **No `audit.auth_events` row, no operation enum value, no audit result value** (37.1 D-01,
  38 D-03). Log event names come from exception class names.
- **Outcomes are exception classes, never an enum** (Phase 37.3 D-12).
- **The service is Phase 43's, called as-is:** `SubscriptionsService.ingest()`, `SubscriptionsDB`,
  the lock order (grant rows ascending, then usage rows), the replay read before any write, the
  SQLSTATE-23505-is-a-race rule, the unattributed case, expire-then-insert, never-silently-
  reactivate, the attribution-conflict refusal (43 D-12, D-15 … D-21). This phase edits the
  service only to remove `status_at` and `products` (D-11, D-16) and to raise one log level (D-12).
- **`store_purchase_tokens.identity_value` is a server-minted `uuid4()` per user per store,
  written at user creation** (`crud/identities.py:107`). Google's
  `externalAccountIdentifiers.obfuscatedExternalAccountId` is resolved against it, exactly as
  Apple's `appAccountToken` is.
- **`store_signed_at` exists and the guard exists** (quick task 260904-u7t, CR-01 of
  `43-REVIEW.md`; commits `29082dd`, `46296d8`). D-12 feeds it, never bypasses it.
- **No network call while a lock is held or a transaction is open.** Both Google calls run in
  the dependency, before `get_db`.
- **One captured instant per request** (`get_evaluated_at`).
- **`commit()` and `rollback()` live in `services/`** (AGENTS.md).
- **No success log line** (Phase 38 D-02); `RequestLoggingMiddleware` writes the one request line.
- **`IntegrityError` is caught by SQLSTATE 23505 only** (Phase 42-07).

### Claude's Discretion

- The two class names and the Protocol name in `auth/google_play.py`; the dict literal's exact
  name (D-03 — the user said "I don't care").
- The `revoked` word for Google: `subscriptionState` has no revoked value. Map to `revoked` if
  `subscriptionsv2` exposes a revocation signal the researcher can cite; otherwise a revocation
  is recorded as `EXPIRED` with `event_type` 12 preserving the reason. Record the choice.
- An Apple subscription transaction with no `data.status` (the field is optional in the
  library): refuse as a 500 leaf so Apple retries and it is visible, unless research shows Apple
  always sends it for auto-renewable subscriptions.
- The `JWTVerifier` extension's exact signature (D-09), provided the Firebase tests are unchanged.
- The Play response model's field set beyond `productId`, `expiryTime`, `subscriptionState`,
  `latestOrderId`, `linkedPurchaseToken`, `startTime`, `obfuscatedExternalAccountId`.
- Test shape, on the 43 D-24 model: unit tests mint RS256 tokens against a fake JWKS transport
  (`tests/unit/test_jwks_offload.py` has the harness) and script Play with
  `httpx.MockTransport`; e2e scripts fakes behind the Protocol in `tests/e2e/conftest.py`;
  database behaviour on real PostgreSQL in `tests/schema`.
- Log field names on the new leaves; the INFO line of D-05; the ERROR line of D-04.
- Plan wave order. The `k8s/` edit and the `pyproject.toml` dependency are independent of the code.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding specification (overrides phase briefs on conflict)

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — § "Global
  deletions" (exact-path membership; D-01/D-03), § "Locks and transactions" (D-15, D-17),
  § "Grants and evaluation time", § "Fail-closed defaults". § "Rate limits" is dead. Not edited.
- `/home/init/native-speaker/specs/auth-refactor-phases/09-webhook-google-play-rtdn.md` — the
  brief, verbatim, **not edited** (D-22). Read "This phase adds", the business logic, "Security
  hardenings" and DELETIONS. **Its route registry, its foundation interface, its "not registered
  while unconfigured", its "never the shared error classes", its gateway limits, and its
  "no raw purchase tokens persisted" are diverged from or dead** — read "Carried forward" and
  D-10 first.
- `/home/init/native-speaker/specs/auth-refactor-phases/08-webhook-app-store.md` — Apple's
  brief; the lifecycle rules this phase calls through the service.

### Phase 43 — the service and the decisions this phase amends

- `.planning/phases/43-post-webhooks-app-store/43-CONTEXT.md` — D-01 (amended by D-01/D-03
  here), D-02/D-04/D-06 (inherited flagged conflicts), D-07/D-08 (the class and the value type;
  D-06 here moves it), D-13 (replaced by D-11), D-14 (relocated by D-16), D-15 … D-24.
- `.planning/phases/43-post-webhooks-app-store/43-REVIEW.md` — CR-01, the origin of
  `store_signed_at` and the guard D-12 feeds.
- `.planning/phases/43-post-webhooks-app-store/43-VERIFICATION.md` :63-77, :164-191 — the
  guard's verified behaviour and the column's provenance.

### The next consumer

- `/home/init/native-speaker/specs/auth-refactor-phases/10-restore-subscription.md` — Phase 45
  reuses D-08's Play class alone, and adopts the unclaimed subscription this phase may write.

### The source specification

- `/home/init/native-speaker/specs/auth-refactor/06-schema-reference.md` — § `core.subscriptions`,
  § `core.store_purchases`, § `core.store_purchase_tokens`, § `audit.subscription_events`,
  § `core.access_grants`.
- `/home/init/native-speaker/specs/auth-refactor/04-subscription-restore-and-entitlement-transfer.md`
  — the `notification_uuid` deduplication and ingestion rules.

### Google's own documentation (the researcher verifies field names here, never from memory)

- https://developer.android.com/google/play/billing/rtdn-reference — `DeveloperNotification`,
  `eventTimeMillis`, `subscriptionNotification.notificationType` values, the three other bodies.
- https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2 —
  `subscriptionState`, `lineItems[].expiryTime`, `externalAccountIdentifiers`,
  `linkedPurchaseToken`, `canceledStateContext`, `pausedStateContext`.
- https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions — the OIDC token, its
  `aud`, `email` and `email_verified` claims, the issuer and JWKS endpoint.

### Project planning

- `.planning/REQUIREMENTS.md` § PLAYHOOK (:411-418) — **this phase appends its dated amendments
  here** (D-21); § APPLEHOOK (:363-377) — the notes on 43 D-13/D-14 go here.
- `.planning/ROADMAP.md` Phase 44 (:672-682) — criterion 3 is answered by D-03.
- `.planning/STATE.md` § Decisions — the 42-07 and 43 entries.

### Repo conventions and the deployment

- `ns-api-gateway/AGENTS.md` — § "Package layout", § "Function shape", § "Comments and
  docstrings".
- `k8s/templates/httproute-webhooks.yaml` — D-19; `k8s/templates/security-policy.yaml` — the
  JWT policy the webhook route stays outside.
- `tests/unit/test_app_wiring.py` — the literals D-02/D-03 change.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `auth/jwt_verifier.py::JWTVerifier` — RS256 over a `PyJWKClient` with a warm-up fetch, an
  unknown-`kid` negative cache and the never-raises rule; D-09 extends it. Called through
  `run_in_threadpool` at `app/dependencies.py:53`.
- `auth/firebase.py:48-55` — `credentials.ApplicationDefault()`: the credential path D-14 shares.
- `auth/app_store.py` — `VerifiedNotification` (D-06 moves it), `StoreNotificationVerifier`,
  `AppStoreNotifications`; the Apple class gains the `data.status` and product mappings
  (D-11, D-16). `payload.data.status` / `rawStatus` are on the library's `Data` model.
- `app/dependencies.py::verify_app_store_notification` — the one-line shape D-08's dependency
  follows; `get_subscriptions_service` drops `products` (D-16).
- `app/lifespan.py` — builds each client once on `app.state` and warns on absent credentials;
  the two Google classes are built here.
- `services/subscriptions.py` — `ingest()` is called as-is; `status_at` (:17-33) is deleted;
  `:81-96` is the guard D-12 feeds; `:93` is the log line whose level rises.
- `crud/subscriptions.py::SubscriptionsDB` — untouched.
- `tables/purchases.py` — `PurchaseProvider.google_play` already exists; `Subscription`,
  `SubscriptionEvent`, `StorePurchase` untouched.
- `errors.py` — `NotificationRejected` (:458), `Unavailable` (:405), `UnmappedStoreProduct`
  (:262), `AttributionConflict` (:277), `InternalError` (:136): all reused, none added unless a
  failed Play call needs its own 5xx leaf.
- `config.py::AppStoreConfig` (:71-98) — the shape of `GooglePlayConfig`, validators included.
- `tests/unit/test_jwks_offload.py` — a fake JWKS transport and a real `JWTVerifier`; the
  harness D-09's tests extend. `tests/unit/test_app_store_notifications.py` — the throwaway
  chain; the test file whose imports D-06 moves.
- `tests/e2e/conftest.py` — the scripted App Store fake; the Google fakes sit beside it.
- `httpx` (direct), `google-auth` (transitive today; direct after D-15). `PyJWT[crypto]` direct.

### Established Patterns

- Layering per `AGENTS.md`: dependency → handler → service → crud; the class on `app.state` is
  built in lifespan and holds the client.
- Absent configuration or credential: boot proceeds with a warning; the route answers 503.
- Fail-closed reads raise in `crud/`; `commit()` in `services/`; a `try` holds one statement.
- Structured-log labels from a closed set, never a token, an email, or a payload value.
- Divergences are recorded under the requirement, never by editing the specification.

### Integration Points

- New: `auth/google_play.py` (two classes, one Protocol, the Play response model),
  `auth/store_notifications.py` (D-06), `GooglePlayConfig` in `config.py`, the Google block in
  `config/config.yaml` (`google_play.products`) and `.env.example`.
- Edited: `routers/webhooks.py` (no router gate; second route), `app/dependencies.py`
  (`verify_google_play_notification`; `get_subscriptions_service`), `app/lifespan.py`,
  `auth/jwt_verifier.py` (D-09), `auth/app_store.py` (imports; `data.status`; products),
  `services/subscriptions.py` (D-11, D-12, D-16), `schemas/webhooks.py` (the Pub/Sub envelope),
  `pyproject.toml` (`google-auth`), `tests/unit/test_app_wiring.py` (D-02, D-03),
  `k8s/templates/httproute-webhooks.yaml`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`.

### Naming Hazard

Five things are called "Google": `IdentityProvider.google` (Firebase sign-in), the Firebase
Admin credential, the Pub/Sub push identity, the Play Developer API, and
`PurchaseProvider.google_play`. Keep them apart at every seam, as 43 kept the four "apple"s.

</code_context>

<specifics>
## Specific Ideas

- **Answer the question that was asked, then stop.** Twice this discussion, an explain question
  ("is it normal for Google…", "why can't Google avoid…") was answered and then followed by a
  decision box the user had not asked for. The user said so. An explanation ends without a
  question.
- **"ELI5" and "English, please" mean plain words and no layer names.** The status question was
  answered only when the column, the five words, and who picks the word were said in that order.
- **Verify before asserting; follow the chain to the root.** Three claims this discussion made
  were wrong until checked: that Google has no creation time (it has `eventTimeMillis`); that
  on-hold has no Apple counterpart (it is billing retry after grace); that `store_signed_at` was
  a Phase 43 design (it is a yesterday's review fix, `260904-u7t`). Each was corrected by reading
  the source, and each correction changed a decision.
- **Give the best option, keep one answer, ask one thing at a time** — 43's notes still hold.
- **Use the codebase's own terms**: dependency, handler, service, crud, config, lifespan, the
  class on `app.state`. The user asked "why isn't it a dependency like with AppStore?" when a
  class was named without its dependency beside it.
- **ASD-STE100** for prose and comments (D-23).

</specifics>

<deferred>
## Deferred Ideas

- **Phase 44.1 — the feature-sliced restructure.** The user asked for
  `core/ db/ auth/ users/ grants/ webhooks/ chats/ health/`, each slice holding
  `router.py schemas.py models.py crud.py service.py dependencies.py`, with `tests/` sliced the
  same way. It is a pure move with no behaviour change, after Phase 44, so that 44's review reads
  new logic and not a 48-file rename. The adapted layout with real names is in
  `44-DISCUSSION-LOG.md`. Notes from the sketch: `repository.py` is called `crud.py` here;
  `grants/` is a slice of its own because auth, webhooks and chats all read it; `store_notifications.py`
  becomes `webhooks/notifications.py`. Create it with `/gsd:phase add`.
- **Apple live status from the App Store Server API** (`Get All Subscription Statuses`, whose
  five status values are exactly `core.subscription_status`). Considered; declined for now
  (D-13). Reopen if the Apple path ever needs server-side state instead of the signed snapshot.
- **Gateway per-IP and per-URL limits on both webhook paths** — the v2.1 gateway contract
  (43 D-06).
- **Provisioning the Pub/Sub topic, the push subscription, its audience and its push service
  account** — infrastructure, not this repository.
- **A `paused` subscription status** — Google has one, our enum does not; `expired` stands in
  (D-11). Reopen if a paused user's experience needs to differ from a lapsed one's.

### Reviewed Todos (not folded)

- `secret-manager-integration` (score 0.6) — declined again. D-14 uses Application Default
  Credentials, so this phase adds no secret; the todo's scope is unchanged.
- `message-ordering-is-unspecified` (score 0.6) — chats; matched on words only. Unrelated.

</deferred>

---

*Phase: 44-post-webhooks-google-play-rtdn*
*Context gathered: 2026-09-05*
