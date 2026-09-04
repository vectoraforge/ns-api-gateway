# Phase 43: POST /webhooks/app-store - Research

**Researched:** 2026-09-04
**Domain:** Apple App Store Server Notifications V2 ingestion — JWS verification, a provider-callback router partition, and one subscription-entitlement transaction
**Confidence:** HIGH

## Summary

Everything this phase needs is installed and mostly already in the repository. `app-store-server-library` 3.0.0 is a pinned dependency, the Apple Root CA G3 DER file is **already committed and tracked** at `config/certs/AppleRootCA-G3.cer`, the four database tables exist in the single migration, and `PostgreSQL 17.11` is reachable. No new package is needed. The phase is code, tests, config and one k8s rename.

The research was run mostly as **measurement against the installed source**, not as reading. Fifteen premises of `43-CONTEXT.md` were checked; **twelve held and three are corrected**, and nine further facts the context file does not name were found. The three corrections that change the shape of the plan are: `event_type` must be read off `rawNotificationType` and never `notificationType` (P-03), the vendored certificate D-10 asks for already exists (P-01), and two named cases in `tests/unit/test_app_wiring.py` break the moment the route is registered — D-01 names neither (P-05).

The rest of this file is arranged so a planner can go straight to § "Corrections to the Context File", § "Common Pitfalls" and § "Test Ratchets This Phase Trips", which are the parts a plan written from `43-CONTEXT.md` alone would get wrong.

**Primary recommendation:** Plan the phase as written in `43-CONTEXT.md`, applying corrections P-01 … P-15 below. Read `rawNotificationType`. Guard the `SignedDataVerifier` construction against `ValueError`. Budget one task for the three ratchet literals the phase trips.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**The partition**

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

**The Apple class**

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

**The service**

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

**Replay and responses**

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

**Comment style**

- **D-25: Every comment this phase writes is ASD-STE100, inline where possible.** Short sentences,
  one idea each, the same word for the same thing. This is in addition to `AGENTS.md`
  § "Comments and docstrings" (only where necessary, one line each).

**Documentation deliverables**

- **D-26: Amend APPLEHOOK-01 and APPLEHOOK-02 in `.planning/REQUIREMENTS.md`** with dated
  entries: D-01 as the answer to APPLEHOOK-02; D-02, D-04 and D-06 as flagged conflicts against
  `08-webhook-app-store.md`; D-09 as a divergence from Apple's guidance; the obligations already
  dead before this phase (rate limits and budgets, the audit row, the route registry, the
  foundation store-verification interface). Update the header's conflict counts. Mark the ROADMAP
  criterion 3 answered.
- **D-27: `08-webhook-app-store.md` and `SHARED-INVARIANTS.md` are NOT edited.** Divergences live
  in REQUIREMENTS.md.

**Carried forward — decided earlier, binding here, do NOT rebuild**

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
  never by constraint name** (Phase 42-07). D-20. *(→ corrected by P-02 below.)*
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

### Deferred Ideas (OUT OF SCOPE)

- **Gateway per-IP and per-URL limits on `/webhooks/app-store`** — the brief requires them; the
  v2.1 gateway contract owns every gateway limit (D-06).
- **Online certificate revocation checks** — off (D-09); reopen if the threat model changes.
- **A way back to a free-tier grant for a lapsed subscriber** — D-18 accepts zero credits; any
  path reopens the lifetime slot and needs its own rules.
- **A mid-term tier change policy** — moot with one paid tier; recorded at discretion.
- **Google Play** — Phase 44; **restore and adoption** — Phase 45.
- **One test asserting each Python enum's values equal its `core.*` type's labels** — still
  deferred.
- `message-ordering-is-unspecified` (score 0.4) — chats; unrelated.
- `secret-manager-integration` (score 0.2) — config; declined. This phase adds no secret: the
  root certificate, the bundle id and the app id are public values.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **APPLEHOOK-01** | The endpoint ingests Apple App Store Server Notifications outside the auth dependency, authenticated solely by verifying Apple's signed `signedPayload` JWS | § Code Examples 1–4 (the dependency, the class, the value type); § Pitfalls 1, 2, 4, 6, 9 (what the library actually checks and what it does not); § Corrections P-03, P-04, P-08, P-09, P-12. The seam is declared beside its first implementation, which is FOUND-08's forward-flag treatment. |
| **APPLEHOOK-02** | The route is enumerated individually by exact path in the closed provider-callback category — never by wildcard or prefix, never on the public allowlist | § Correction P-05 — measured: exactly two cases in `tests/unit/test_app_wiring.py` break when the route lands, and both need `PROVIDER_CALLBACK_PATHS` added to their exemption union. § Code Example 5 gives the assertion shape D-01 describes. `SHARED-INVARIANTS.md:63` (§ Global deletions) is quoted verbatim in § Security Domain and still binds. |
</phase_requirements>

## Corrections to the Context File

Measured against the installed source and the running application this session. **Three change the shape of the plan** (P-01, P-03, P-05). The remaining twelve are facts `43-CONTEXT.md` does not carry.

### P-01 — The Apple Root CA G3 file already exists, committed and tracked. D-10 is a default, not a task.

`43-CONTEXT.md` D-10 reads *"The Apple Root CA G3 DER file is committed under `config/`"* as work this phase does, and § Claude's Discretion budgets a wave for it: *"the `k8s/` rename and the vendored certificate are independent of the code."*

**It is already there.** `config/certs/` holds three files, all tracked (`git ls-files config/certs` lists all three; `git check-ignore` exits 1 for the G3 file), committed in `e908ea6` *"Add certificates and expand .gitignore"*:

```
config/certs/AppleIncRootCertificate.cer   subject=C=US, O=Apple Inc., OU=Apple Certification Authority, CN=Apple Root CA
config/certs/AppleRootCA-G2.cer            subject=CN=Apple Root CA - G2, OU=Apple Certification Authority, O=Apple Inc., C=US
config/certs/AppleRootCA-G3.cer            subject=CN=Apple Root CA - G3, OU=Apple Certification Authority, O=Apple Inc., C=US
                                           notBefore=Apr 30 18:19:06 2014 GMT   notAfter=Apr 30 18:19:06 2039 GMT
                                           sha256=63:34:3A:BF:B8:9A:6A:03:EB:B5:7E:9B:3F:5F:A7:BE:7C:4F:5C:75:6F:30:17:B3:A8:C4:88:C3:65:3E:91:79
```

[VERIFIED: `openssl x509 -inform DER -in config/certs/AppleRootCA-G3.cer -noout -subject -dates -fingerprint -sha256`, run this session]

That fingerprint is byte-for-byte Apple's published Apple Root CA G3 SHA-256 fingerprint [CITED: developer.apple.com forums thread 693351, via WebSearch]. The file is genuine and current; it does not expire until 2039.

**Plan impact:** `AppStoreConfig.root_certificate_path` defaults to `config/certs/AppleRootCA-G3.cer`. Nothing is added to the repository. The "vendored certificate" half of the discretion note has no file to write; only the default and a test that the default path resolves and loads.

### P-02 — The SQLSTATE is read off `violation.orig.sqlstate`, not `violation.orig.__cause__.sqlstate`.

`43-CONTEXT.md` § "Carried forward" states the rule as *"read off `orig.__cause__.sqlstate`"* and cites Phase 42-07. **That spelling was replaced by 42-07's own last commit,** `6b14231` *"refactor(42-07): read the SQLSTATE straight off the wrapped error"* — the head of this branch before the phase begins. The `UNIQUE_VIOLATION` module constant was deleted in the same commit. The three shipped sites read:

```python
except IntegrityError as violation:
    # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
    if violation.orig.sqlstate != "23505":
        # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
        raise
    return ActivationOutcome.lost_race
```

[VERIFIED: `src/nativespeaker/api/crud/grants.py:174-181`, quoted verbatim above; `git show 6b14231`]

**Plan impact:** D-20's writer copies the shipped spelling. A plan that writes `orig.__cause__.sqlstate` produces a second, divergent idiom in the same package — and `getattr(..., "sqlstate", None)` on the wrong object silently never equals `"23505"`, so **every** unique violation would re-raise as a 500 instead of being read as a lost race.

### P-03 — `event_type` must be read off `rawNotificationType`. `notificationType` is `None` for any type the installed library does not know.

D-08 says `event_type` is *"Apple's type as received"* and D-13 says *"an unknown or new type costs nothing."* Only one of the two attributes delivers that. Measured against the installed library:

```
UNKNOWN TYPE -> notificationType: None | rawNotificationType: 'SOME_FUTURE_TYPE'
```

[VERIFIED: measured this session — a payload minted with `notificationType="SOME_FUTURE_TYPE"` and verified through `SignedDataVerifier.verify_and_decode_notification`; output pasted above]

The mechanism is `AppStoreServerLibraryEnumMeta.create_raw_attr`, which sets the typed attribute only when the raw string is a member of the enum: `newValue = c(value) if value in c else None` [VERIFIED: `.venv/lib/python3.14/site-packages/appstoreserverlibrary/models/LibraryUtility.py:38`, quoted verbatim]. The installed `NotificationTypeV2` carries exactly twenty members, verbatim:

`SUBSCRIBED`, `DID_CHANGE_RENEWAL_PREF`, `DID_CHANGE_RENEWAL_STATUS`, `OFFER_REDEEMED`, `DID_RENEW`, `EXPIRED`, `DID_FAIL_TO_RENEW`, `GRACE_PERIOD_EXPIRED`, `PRICE_INCREASE`, `REFUND`, `REFUND_DECLINED`, `CONSUMPTION_REQUEST`, `RENEWAL_EXTENDED`, `REVOKE`, `TEST`, `RENEWAL_EXTENSION`, `REFUND_REVERSED`, `EXTERNAL_PURCHASE_TOKEN`, `ONE_TIME_CHARGE`, `RESCIND_CONSENT`

[VERIFIED: `.venv/lib/python3.14/site-packages/appstoreserverlibrary/models/NotificationTypeV2.py:12-31`]

**Plan impact:** `event_type = decoded.rawNotificationType`. Reading `notificationType` would write `None` into a `NOT NULL TEXT` column the first time Apple ships a twenty-first type, turning D-13's "costs nothing" into a 500 at the flush. The same rule applies to every `raw*` pair the phase touches — `rawSubtype`, `rawEnvironment`, `rawStatus`.

### P-04 — `SignedDataVerifier.__init__` raises `ValueError`, not `VerificationException`, when `environment` is Production and `app_apple_id` is absent. Lifespan must guard it or boot dies.

```
Production verifier with app_apple_id=None -> ValueError: appAppleId is required when the environment is Production
```

[VERIFIED: measured this session; the raise is at `.venv/.../signed_data_verifier.py:41-42`]

`43-CONTEXT.md` § "Existing Code Insights" notes the `ValueError` but does not connect it to D-02, which says lifespan *"logs a warning … and the route answers 503"* when config is incomplete. A config that names `environment: production` and omits `app_apple_id` **is** incomplete, and D-11 makes `app_apple_id` optional, so this state is reachable from a plain YAML edit.

**Plan impact:** the lifespan completeness test is not "are the fields set" but "can the verifier be built". Either check `app_apple_id` explicitly whenever `environment` is `production` before constructing, or wrap the construction and treat a `ValueError` as unconfigured — pass `None` to `AppStoreNotifications`, log the warning, and let the route answer 503. `firebase_admin`'s and DeviceCheck's precedent is the former: lifespan tests the fields and warns, it does not catch. Whichever is chosen, a case must exist for it: a Production-without-app-apple-id config must boot and answer 503, not crash the pod on start.

### P-05 — Exactly two cases in `tests/unit/test_app_wiring.py` break when the route is registered. D-01 names neither.

D-01 lists what the new assertions must say but treats the existing file as additive. It is not: two of the six cases in `TestEveryRouteIsAuthenticated` compute their sets structurally over `app.routes`, so a route declaring neither identity accessor lands in them automatically. Measured by injecting a webhook-shaped router into the real `app` object:

```
case 1 `every route but the two exemptions` -> missing: ['/webhooks/app-store']
case 5 `public allowlist is exactly readiness` -> unauthenticated set: ['/health/ready', '/webhooks/app-store']
case 5 passes? False
declared on the hook route: ['verify_app_store_notification', 'verify_app_store_notification']
```

[VERIFIED: measured this session against `nativespeaker.api.app.main.app`]

The two that break, quoted verbatim from `tests/unit/test_app_wiring.py:29-33` and `:62-68`:

```python
    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   and get_linked_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"
```

```python
    def test_the_public_allowlist_is_exactly_the_readiness_probe(self):
        """A second public route would have to be added to `PUBLIC_PATHS` above to pass."""
        unauthenticated = {route.path for route in _api_routes()
                           if get_linked_identity not in _declared(route)
                           and get_identity not in _declared(route)}
        assert unauthenticated == PUBLIC_PATHS
```

Both need `PROVIDER_CALLBACK_PATHS` in their exemption union. **D-01's wording "the public allowlist is still exactly `/health/ready`" stays true as intent and false as this assertion** — the assertion measures "declares no identity accessor", which the callback route also satisfies. The honest replacement asserts `unauthenticated == PUBLIC_PATHS | PROVIDER_CALLBACK_PATHS` **and** adds a separate case that `PUBLIC_PATHS == {"/health/ready"}` as a literal, so widening the true public allowlist is still a one-line visible edit.

The other four cases survive untouched: two are `@pytest.mark.parametrize`d over named auth paths, one iterates `PREAUTH_CALLABLE_PATHS`, and one walks `__wrapped__`.

The fourth line of output also matters: `_declared()` returns `verify_app_store_notification` **twice** — once from the router-level `dependencies=[...]` and once from the handler's parameter. D-01's "declares it by callable identity" is a membership test and is fine; a count-based assertion would have to expect two.

### P-06 — `tests/unit/test_auth_package_shape.py` is an equality on a measured triple. Adding `auth/app_store.py` fails it.

```python
# What it measures now: modules, classes, functions.
CURRENT = (5, 12, 35)
...
    def test_it_still_measures_the_recorded_current_shape(self):
        """A later phase that grows the package has to come here and write the new number down."""
        assert _measure(AUTH_PACKAGE) == CURRENT
```

[VERIFIED: `tests/unit/test_auth_package_shape.py:13` and `:31-34`, quoted verbatim]

Re-measured per module this session, agreeing exactly:

```
__init__.py          classes=  0 functions=  0
adapters.py          classes=  2 functions=  1
devicecheck.py       classes=  4 functions= 17
firebase.py          classes=  2 functions=  9
jwt_verifier.py      classes=  4 functions=  8
TOTAL: (5, 12, 35)
```

The count is an `ast.walk`, so nested helpers and methods count. `auth/app_store.py` carrying `AppStoreNotifications`, its Protocol and `VerifiedNotification` moves the triple to `(6, 15+, 35+n)`. The plan re-measures and writes the literal down **in the commit that adds the module**, per the standing rule from 37.3-02 (*"Ratchet literals … are extended in the commit that adds each class, not batched"*).

### P-07 — `tests/unit/test_rejection_vocabulary.py::EVENT_NAMES` is a frozenset asserted with `==`, one entry per class in the error tree.

```python
    def test_the_tree_spells_exactly_the_recorded_event_names(self):
        derived = {camel_to_snake(cls.__name__) for cls in _production_family()}
        assert derived == EVENT_NAMES
```

[VERIFIED: `tests/unit/test_rejection_vocabulary.py:134-137`, quoted verbatim]

D-04's `NotificationRejected` and D-21's `AttributionConflict` and `UnmappedStoreProduct` each need an entry (`notification_rejected`, `attribution_conflict`, `unmapped_store_product`). `Unavailable` is reused and already listed. A class whose `__init__` insists on arguments additionally needs a `CONSTRUCTOR_ARGUMENTS` entry in the same file, or `TestEveryLeafKeepsItsLogFieldsToPlainScalars` fails at instantiation.

### P-08 — D-03's "a bad payload never opens a session" is true for an unverifiable payload and false for a malformed one.

Measured with a router-level dependency taking a Pydantic body, beside a handler-level `Depends(get_db)`:

```
OK  200 {'v': 'VERIFIED:good'} ['verify', 'get_db_open', 'handler', 'get_db_close']
BAD 401 {'detail': 'nope'}     ['verify']
422 422 {...}                  ['get_db_open', 'get_db_close']
```

[VERIFIED: measured this session against the installed fastapi 0.135.1 / starlette]

The **BAD** line is D-03's claim and it holds: a well-shaped body that fails verification short-circuits, and `get_db` never runs. The **422** line is the correction: a body that fails Pydantic validation does **not** short-circuit, because FastAPI collects validation errors across the whole dependant rather than raising at the first — `verify` is skipped (its body param did not validate) while `get_db` opens and closes. No query is issued and nothing is written, so this is a wording correction, not a defect; the plan should not write a case asserting "no session is opened for a malformed body", because that case fails.

The **OK** line also confirms D-03's other half: `verify` appears **once**, so FastAPI's per-request dependency cache resolves the router-level and handler-level declarations to one execution, exactly as `get_linked_identity` is resolved on the auth routes.

One cosmetic consequence: the 422 body lists the same missing field twice, once per declaration site. The project maps 422 to `ValidationError` and answers the one-field `{"code": "validation_error"}`, so nothing client-visible changes.

### P-09 — With `enable_online_checks=False`, the certificate-validity window is evaluated at the payload's own claimed `signedDate`. D-09 does not name this.

```python
signed_date = decoded_jwt.get('signedDate') if decoded_jwt.get('signedDate') is not None else decoded_jwt.get('receiptCreationDate')
effective_date = time.time() if self._enable_online_checks or signed_date is None else int(signed_date) // 1000
```

[VERIFIED: `.venv/.../signed_data_verifier.py:164-165`, quoted verbatim; `decoded_jwt` on the line above comes from `jwt.decode(signed_obj, options={"verify_signature": False})`]

That date is then handed to `trusted_store.set_time(...)` before `verify_certificate()`. Measured with a deliberately expired leaf:

```
EXPIRED leaf + backdated signedDate, online checks OFF -> OK u
EXPIRED leaf + current signedDate (control)            -> VERIFICATION_FAILURE
```

[VERIFIED: measured this session; the chain's leaf `notAfter` was set 30 days in the past and the payload claimed a `signedDate` 90 days old]

**What this means, stated precisely.** D-09 buys away the OCSP round trip, and the honest cost is larger than "a revoked Apple intermediate is rare": with online checks off, *certificate expiry* on the leaf is also not enforced against wall-clock time, because the attacker supplies the clock. An attacker who obtained an Apple-issued signing leaf's private key could keep using it indefinitely by backdating `signedDate`. The mitigating fact is unchanged and decisive for this product: the attacker must first hold an **Apple-issued** leaf key chaining to Apple Root CA G3, which no ordinary attacker has, and the prize is one wrongly-applied subscription for a sub-$5 app. D-09's decision stands; its recorded reason should carry this sentence so a later reader is not surprised.

`enable_strict_checks` defaults to `True`, so `X509_STRICT` is set on the store [VERIFIED: `.venv/.../signed_data_verifier.py:179`, `:207-208`].

### P-10 — A throwaway chain verifies only if it carries two Apple OIDs, is exactly three certificates long, and is ordered leaf-intermediate-root. D-24 is buildable; here is what it needs.

```python
self.check_oid(trusted_chain[0].to_cryptography(), "1.2.840.113635.100.6.11.1")   # leaf
self.check_oid(trusted_chain[1].to_cryptography(), "1.2.840.113635.100.6.2.1")    # intermediate
```

[VERIFIED: `.venv/.../signed_data_verifier.py:222-223`, quoted verbatim; `if len(certificates) != 3: raise VerificationException(VerificationStatus.INVALID_CHAIN_LENGTH)` at `:201-202`]

Built and run this session — the full recipe is § Code Example 6:

```
VERIFIED OK -> NotificationTypeV2.TEST | raw: TEST | uuid-1
CONTROL OK -> apple root refuses: VERIFICATION_FAILURE
```

[VERIFIED: measured this session]

Both halves of D-24's unit contract work: a locally generated root/intermediate/leaf mints payloads the library accepts, and the **vendored real Apple root refuses that same payload** with `VERIFICATION_FAILURE`. That control is worth writing exactly as measured — it is the one case proving the chain check is not vacuous.

### P-11 — Apple retries on 4xx as well as 5xx, five times at 1, 12, 24, 48 and 72 hours.

> *"Send HTTP 200, or any HTTP code between 200 and 206, if the post was successful. Send HTTP 50x or 40x to have the App Store retry the notification."* … *"For version 2 notifications, it retries five times, at 1, 12, 24, 48, and 72 hours after the previous attempt."*

[CITED: https://developer.apple.com/documentation/appstoreservernotifications/responding-to-app-store-server-notifications and https://developer.apple.com/documentation/appstoreservernotifications/app-store-server-notifications-v2]

D-23 is correct that 5xx earns a retry. The corollary it does not state is that **D-04's 401 also earns five retries**, which matters in exactly one situation and it is an operational one: a misconfigured `bundle_id`, `app_apple_id` or `environment` turns every *genuine* Apple notification into `INVALID_APP_IDENTIFIER` or `INVALID_ENVIRONMENT` → 401. Apple then retries for roughly six days and gives up, and the subscription state is silently lost. A forged payload from a third party is never retried, because Apple did not send it.

**Plan impact:** the `NotificationRejected` WARNING carries `stage=<VerificationStatus name>` (D-04), which is what distinguishes this failure. `INVALID_APP_IDENTIFIER` and `INVALID_ENVIRONMENT` in that field mean *this deployment is misconfigured*, not *someone is probing you*, and the operator has about six days to notice. Worth one line in the log-field choice and one sentence in the requirement amendment.

Apple's own guidance also independently endorses D-20: *"If you receive a retried notification that does have the same notificationUUID, it is recommended to respond with 200 even if you believe it is a duplicate."* [CITED: developer.apple.com, via WebSearch]

### P-12 — Apple's own documented example iterates `signedTransactionInfo` as if it were a list. It is a single string.

Apple's autodoc for the Python library shows:

```python
            for signed_txn in notification.data.signedTransactionInfo:
                transaction = verifier.verify_and_decode_signed_transaction(signed_txn)
```

[CITED: https://github.com/apple/app-store-server-library-python/blob/main/_autodocs/api-reference/SignedDataVerifier.md, via Context7]

The model declares `signedTransactionInfo: Optional[str] = attr.ib(default=None)` [VERIFIED: `.venv/.../models/Data.py:52`, quoted verbatim]. Iterating it yields one character per loop and every call fails. Do not copy the documented example; call `verify_and_decode_signed_transaction(decoded.data.signedTransactionInfo)` once.

### P-13 — `config/config.yaml` is `init_settings` and outranks every environment variable for anything it declares.

The file says so itself, and Phase 41 D-16 proved the partial-block deep-merge with a case:

> *"The YAML is authoritative for anything it declares: AppConfig is built as AppConfig(**yaml_data, ...) and pydantic-settings ranks init_settings above env_settings, so no environment variable can override a key declared here."*

[VERIFIED: `config/config.yaml:19-27`, quoted verbatim; the construction is `AppConfig(**yaml_data, prompt=..., examples=...)` at `src/nativespeaker/api/config.py:99-101`]

**Plan impact:** `app_store.products` (D-14) belongs in `config/config.yaml` — it is a public map and an operator edit is the intended loop for `UnmappedStoreProduct` (D-21). `bundle_id`, `app_apple_id`, `environment` and `root_certificate_path` should **not** be declared there, or `.env` can never set them. A partial `app_store: {products: {...}}` block deep-merges with `APP_STORE_*` env nesting exactly as the `db: {pool_size: 12}` block does with `DB_*`.

### P-14 — `app_store` works as a config field name despite `env_nested_max_split=1`.

`BaseConfig` sets `env_nested_delimiter="_"` with `env_nested_max_split=1` [VERIFIED: `src/nativespeaker/api/config.py:14-16`], which reads as if a two-word section name could not work. Measured on the installed pydantic-settings 2.13.1:

```
--- field=app_store prefix=APP_STORE ---
bundle_id='b' app_apple_id=7 environment='production' root_certificate_path='/p' products={}
```

[VERIFIED: measured this session]

`APP_STORE_BUNDLE_ID`, `APP_STORE_APP_APPLE_ID`, `APP_STORE_ENVIRONMENT` and `APP_STORE_ROOT_CERTIFICATE_PATH` all land. D-11's field name is safe and the `devicecheck`-style single-word alternative is unnecessary. One recorded caveat from the same experiment: with a sibling field literally named `appstore` present on the same model, `APP_STORE_APP_APPLE_ID` became ambiguous and did **not** land — not a risk here, since only one field will exist, but a reason not to add an alias.

### P-15 — Three of the four tables have no SQLModel model, and there is no Python enum for `core.subscription_status`.

`tables/purchases.py` carries exactly `PurchaseProvider` and `StorePurchaseToken` [VERIFIED: `src/nativespeaker/api/tables/purchases.py`, whole file read]. `tables/__init__.py`'s `__all__` confirms it: no `Subscription`, no `StorePurchase`, no `SubscriptionEvent`, no `SubscriptionStatus` [VERIFIED: `src/nativespeaker/api/tables/__init__.py:1-10`].

This phase writes all four. The enum mirrors `core.subscription_status`, whose labels are, verbatim:

```sql
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');
```

[VERIFIED: `migrations/20260818_01_initial-release.sql:11`, quoted verbatim] — these five are D-13's whole output vocabulary. The `PurchaseProviderType = cast(Any, Enum(PurchaseProvider, name='subscription_provider', schema='core'))` idiom in `tables/purchases.py:17` is the pattern to copy: without `name=`, SQLAlchemy derives a second, differently-named type.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| JWS signature + `x5c` chain verification | API — `auth/` external-SDK seam | — | `AGENTS.md` § Package layout: `auth/` is external-SDK seams only. The library is an external SDK. |
| Admission (turn an unverified body into a verified value or a rejection) | API — `app/dependencies.py` | — | `AGENTS.md`: every FastAPI dependency lives there; routes use `Depends()` only. It is the same tier `get_identity` occupies. |
| Provider-callback partition membership | API — `routers/webhooks.py` + `app/main.py` | Test — `tests/unit/test_app_wiring.py` | D-01: membership *is* the set of routes on the router; the literal in the test is what makes it countable (PLAYHOOK-03's requirement). |
| Ingestion transaction, `commit()` | API — `services/` | — | `AGENTS.md` exception 3: `commit()`/`rollback()` are transaction boundaries and therefore business logic. D-12. |
| Row reads and writes, lock acquisition | API — `crud/` | Database — unique indexes | `AGENTS.md`: `crud/` is database access. The indexes arbitrate what the locks cannot (D-16). |
| Replay suppression | Database — `audit.subscription_events.notification_uuid UNIQUE` | API — the pre-write read (D-20) | The read is the fast path; the UNIQUE index is the correctness guarantee under concurrency. |
| Product-id → tier mapping | Config — `config/config.yaml` | — | D-14. Server-controlled, never client-supplied (brief `:38`). An operator edit is the remediation loop for `UnmappedStoreProduct`. |
| Path exposure and TLS | Gateway — `k8s/templates/httproute-webhooks.yaml` | — | D-06 renames only. `security-policy.yaml` already omits the webhook route from the JWT `SecurityPolicy` targetRefs, so no Envoy change is needed. |
| Rate limiting | **Nowhere** — deliberately absent | — | Phase 35 D-05 deleted the backend engine; Phase 35 D-08 deferred the gateway contract to v2.1. D-06 flags the deferral. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `app-store-server-library` | 3.0.0 (pinned in `uv.lock`; spec `>=3.0.0`) | `SignedDataVerifier` — JWS verification, `x5c` chain to Apple's root, typed decode of the notification and its nested payloads | Apple's own library. The brief mandates it by name: *"using Apple's official App Store Server Library (no hand-written chain logic)"* (`08-webhook-app-store.md:48`). Already a dependency. |
| `fastapi` | 0.135.1 (pinned `==`) | `APIRouter` with a router-level dependency — D-01's partition mechanism | Already the framework; the mechanism is the same one `get_identity` uses. |
| `sqlmodel` / `sqlalchemy` | 0.0.37 / 2.0.46 | The four tables, `FOR UPDATE` locks, `IntegrityError` | Already the persistence layer. |
| `structlog` | 25.5+ | The two ERROR lines on D-21, the INFO line on D-22 | Already the logging layer. |

**Nothing is installed.** [VERIFIED: `pyproject.toml:22` declares `app-store-server-library>=3.0.0`; `uv.lock:36-38` pins 3.0.0]

### Supporting — transitive, already present, no action

| Library | Version | Purpose | Note |
|---------|---------|---------|------|
| `pyOpenSSL` | 26.0.0 | The library's `X509StoreContext` chain verification | Pulled in by `app-store-server-library`. |
| `cryptography` | 46.0.5 | Certificate parsing; also what a throwaway test chain is built with (P-10) | Already present for `PyJWT[crypto]`. |
| `attrs` / `cattrs` | 26.1.0 / 26.1.0 | The library's decoded models and their `raw*` fallback (P-03) | Transitive. |
| `PyJWT` | 2.12.1 | The library's JWS decode; also mints test payloads | Already a direct dependency. |
| `requests` | 2.32.5 | Imported at module scope by `signed_data_verifier`, used only by `check_ocsp_status` | **Never called with `enable_online_checks=False`** (D-09). No event-loop-blocking HTTP is reachable. |
| `asn1` | 3.2.0 | OCSP responder-key-hash decoding | Same — unreachable under D-09. |

[VERIFIED: `uv run python -c "from importlib.metadata import version; ..."` this session]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `app-store-server-library` `SignedDataVerifier` | `PyJWT` + hand-rolled `x5c` chain walk | Forbidden by the brief (`:48`, `:26`) and by `AGENTS.md`'s standing preference. It would also have to re-derive the two Apple OID checks and the strict-mode flags — see § Don't Hand-Roll. |
| Pinning 3.0.0 | Upgrading to 3.1.2 (current on PyPI) | **Out of scope.** `uv.lock` pins 3.0.0 and the spec is `>=3.0.0`, so a `uv lock --upgrade` would move it. Every measurement in this file was taken against 3.0.0. If a plan touches the lockfile, the chain-check and `raw*` behaviour must be re-measured. Recommendation: do not touch it this phase. |

**Installation:** none required.

**Version verification:**
```bash
uv run python -c "from importlib.metadata import version; print(version('app-store-server-library'))"   # 3.0.0
```
PyPI currently lists 3.1.2 as latest; 3.0.0 was uploaded 2026-03-12. [VERIFIED: PyPI JSON API, queried this session]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `app-store-server-library` | PyPI | 3.0.0 uploaded 2026-03-12; latest release 2026-06-01 | unknown (registry metadata carries none) | none in PyPI metadata; upstream is `github.com/apple/app-store-server-library-python` | **SUS** | **Approved — pre-existing dependency, upstream identity confirmed** |

```
{ "name": "app-store-server-library", "verdict": "SUS",
  "signals": { "exists": true, "publishedAt": "2026-06-01T18:36:35.946528Z",
               "weeklyDownloads": null, "repoUrl": null, "deprecated": false,
               "postinstall": null, "ecosystem": "pypi" },
  "reasons": ["unknown-downloads", "no-repository"] }
```
[VERIFIED: `gsd-tools query package-legitimacy check --ecosystem pypi app-store-server-library`, run this session]

**Reading the verdict honestly.** Both reasons are **metadata absences, not risk signals**: the PyPI JSON API returns no download statistics at all for this package and the release carries no `project_urls` repository entry. Neither is evidence of anything. The package's identity is independently confirmed from an authoritative source — Context7 resolves it as `/apple/app-store-server-library-python`, *"Apple"*, source reputation High, and the installed source at `.venv/lib/python3.14/site-packages/appstoreserverlibrary/signed_data_verifier.py:1` carries `# Copyright (c) 2023 Apple Inc. Licensed under MIT License.` [VERIFIED: read this session]. There is no `postinstall` equivalent; it is a pure-Python wheel already installed and already exercised by nothing.

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `app-store-server-library` — **no `checkpoint:human-verify` is needed.** It is not being installed by this phase; it has been a pinned dependency since before Phase 43 exists (`pyproject.toml:22`, `uv.lock:36`), and this phase adds no dependency at all. A checkpoint gating an install that does not happen would be noise.

## Architecture Patterns

### System Architecture Diagram

```
  Apple App Store server
          │  POST /webhooks/app-store   { "signedPayload": "<JWS>" }
          │  (no Authorization header, no shared secret)
          ▼
  ┌───────────────────────────────────────────────────────────────┐
  │ Envoy Gateway                                                 │
  │  httproute-webhooks.yaml  Exact path match, POST              │
  │  security-policy.yaml     does NOT target this route  ────────┼── no JWT requirement
  │  TLS termination only. No rate-limit entry (Phase 35 D-05).   │
  └───────────────────────────────┬───────────────────────────────┘
                                  ▼
  ┌───────────────────────────────────────────────────────────────┐
  │ RequestLoggingMiddleware — binds request_id/method/path;       │
  │ never reads the body, so `signedPayload` cannot reach a log.   │
  └───────────────────────────────┬───────────────────────────────┘
                                  ▼
  ┌───────────────────────────────────────────────────────────────┐
  │ webhooks APIRouter  dependencies=[Depends(verify_app_store_…)] │
  │   ← membership in the provider-callback partition IS this set  │
  └───────────────────────────────┬───────────────────────────────┘
                                  ▼
        verify_app_store_notification  (app/dependencies.py)
                                  │
                                  ▼
        app.state.app_store_notifications.verify(signedPayload)
                    (auth/app_store.py — AppStoreNotifications)
                                  │
              ┌───────────────────┼────────────────────┐
              ▼                   ▼                    ▼
   verify_and_decode_      verify_and_decode_   verify_and_decode_
      notification          signed_transaction     renewal_info
   (envelope; bundle_id,   (bundle_id +          (environment)
    app_apple_id, env)      environment)
              │                   │                    │
              └───────────────────┴────────────────────┘
                                  │
        ┌─────────────────────────┴─────────────────────────┐
        │ VerificationException            │  no verifier    │
        ▼                                  ▼                 ▼
  NotificationRejected              Unavailable        VerifiedNotification
  401 auth_required                 503                (our frozen dataclass —
  stage=<VerificationStatus>        verification_          no Apple type crosses
        │                           temporarily_            this line)
        │                           unavailable                    │
        └────────────┬──────────────────────┘                      │
                     ▼                                             ▼
              app_error_handler                     handler (routers/webhooks.py)
              one WARNING, {"code": …}                             │
                     │                              no transaction part? ──► 200,
                     ▼                              log INFO, write nothing (D-22)
              Apple retries: 1,12,24,48,72h                        │
                                                                   ▼
                                      resolve user from attribution_token
                                      via core.store_purchase_tokens
                                      (provider, identity_value)     ← before the
                                                                       transaction
                                                                   │
                                                                   ▼
                                      ┌────────────────────────────────────────┐
                                      │ SubscriptionsService — ONE transaction │
                                      │  1. lock grants ascending by id        │
                                      │  2. lock their usage rows              │
                                      │  3. read audit.subscription_events     │
                                      │       by notification_uuid ──► found?  │
                                      │         yes: write nothing, 200 (D-20) │
                                      │  4. upsert core.subscriptions          │
                                      │       by (provider, external_id)       │
                                      │  5. insert core.store_purchases once   │
                                      │  6. append audit.subscription_events   │
                                      │  7. expire old grant, insert new grant │
                                      │       + core.user_monthly_usage        │
                                      │  8. commit()  ──────────────► 200      │
                                      │  SQLSTATE 23505 anywhere in 4–7:       │
                                      │       rollback, 5xx, Apple resends     │
                                      └────────────────────────────────────────┘
```

### Recommended Project Structure

```
src/nativespeaker/api/
├── auth/app_store.py          # NEW  AppStoreNotifications, its Protocol, VerifiedNotification
├── routers/webhooks.py        # NEW  the APIRouter that IS the partition
├── services/subscriptions.py  # NEW  the one ingestion transaction + commit()
├── crud/subscriptions.py      # NEW  row reads/writes over the three tables
├── schemas/…                  # NEW  the one-field request body
├── tables/purchases.py        # EDIT Subscription, StorePurchase, SubscriptionEvent,
│                              #      SubscriptionStatus beside StorePurchaseToken
├── config.py                  # EDIT AppStoreConfig + AppConfig.app_store
├── app/dependencies.py        # EDIT verify_app_store_notification, get_subscriptions_service
├── app/lifespan.py            # EDIT build SignedDataVerifier once -> app.state
├── app/main.py                # EDIT include_router(webhooks_router)
├── routers/__init__.py        # EDIT export webhooks_router
├── crud/__init__.py           # EDIT export the new DB class
├── services/__init__.py       # EDIT export the new service
├── tables/__init__.py         # EDIT export the four new names
└── errors.py                  # EDIT NotificationRejected, AttributionConflict, UnmappedStoreProduct
config/
├── certs/AppleRootCA-G3.cer   # ALREADY PRESENT (P-01) — nothing to add
└── config.yaml                # EDIT app_store.products only (P-13)
k8s/templates/httproute-webhooks.yaml   # EDIT /webhooks/apple -> /webhooks/app-store
.env.example                            # EDIT the Apple App Store block
tests/unit/test_app_wiring.py           # EDIT P-05: two cases + the third literal
tests/unit/test_auth_package_shape.py   # EDIT P-06: re-measure CURRENT
tests/unit/test_rejection_vocabulary.py # EDIT P-07: three EVENT_NAMES entries
```

[VERIFIED: the file list is the current tree, `find src -name '*.py'`, run this session]

### Pattern 1: The class-plus-Protocol-plus-frozen-value seam

**What:** an external SDK is wrapped by one class with one method, its Protocol is declared in the same module, and the value crossing the seam is a frozen dataclass carrying this project's own field names.

**When to use:** every `auth/` module. It is what `auth/devicecheck.py` already is — `AppleDeviceCheck` / `DeviceCheckAdapter` / `BitState` — and D-07/D-08 name it as the model.

**Why the Protocol lives beside the implementation and not in `auth/adapters.py`:** that module is fenced by an import allowlist:

```python
# Only the standard library and this project; a provider SDK or credential source here is the drift.
ALLOWED_IMPORT_ROOTS = {"dataclasses", "datetime", "enum", "typing", "uuid", "nativespeaker"}
```
[VERIFIED: `tests/unit/test_adapter_interfaces.py:23-24`, quoted verbatim]

`appstoreserverlibrary` is not in that set, so a Protocol there typed against library types fails the fence. This is also FOUND-08's forward-flag treatment — an interface defined with its first implementation rather than declared ahead of one — and the precedent Phase 41 set for `DeviceCheckAdapter`.

### Pattern 2: The router-level dependency as partition membership

**What:** an `APIRouter` constructed with `dependencies=[Depends(gate)]`; every route registered on it inherits the gate, and the set of routes on it is the partition.

**When to use:** D-01. It is the same mechanism `routers/auth.py:36` uses (`APIRouter(tags=["auth"], dependencies=[Depends(get_identity)])`) and the structural replacement FOUND-03's note describes: *"the router a route is registered on is its declaration, so there is no second table left to disagree with."*

**Why this satisfies `SHARED-INVARIANTS.md:63`:** the invariant forbids *wildcard or path-prefix* membership. A route registered with `@router.post("/webhooks/app-store")` is an exact path in FastAPI's route table, and `PROVIDER_CALLBACK_PATHS` in the wiring test is a literal set compared with `==`, so a second member is a visible one-line edit — which is precisely PLAYHOOK-03's *"countable in one place"* requirement.

### Pattern 3: Locks first, replay read second, writes third

**What:** inside the one transaction, take both lock tiers before asking any question whose answer a concurrent writer could change.

**When to use:** D-16 and D-20. `crud/grants.py::activate_registered_account_grant` is the shipped shape: `lock_active_grants` → `lock_effective_grants` → `lock_usage` per grant → *then* re-decide → *then* write. Note the flush boundary it keeps:

```python
        if superseded is not None:
            superseded.status = AccessGrantStatus.expired
            superseded.ends_at = evaluated_at
            superseded.updated_at = evaluated_at
            # Flushed alone and first: the ORM emits inserts before updates, and the one-active index is per-statement.
```
[VERIFIED: `src/nativespeaker/api/crud/grants.py:216-221`, quoted verbatim]

Phase 42's own research assumption A1 — that SQLAlchemy would emit the UPDATE before the INSERT unaided — was measured **false**, and the explicit flush was kept as the guard against an ORM upgrade inverting it (STATE.md § Decisions, `42-02`). D-15's expire-then-insert renewal needs the same boundary for the same reason.

### Pattern 4: The scripted fake behind the Protocol, in `tests/e2e/conftest.py`

`FakeDeviceCheckAdapter` is the model D-24 names: a raise-or-return scriptable stand-in swapped onto `app.state` by a fixture that restores the original in a `finally`. [VERIFIED: `tests/e2e/conftest.py:224-263`, read this session]

### Anti-Patterns to Avoid

- **Reading `notificationType` instead of `rawNotificationType`** — writes `None` into a `NOT NULL` column the first time Apple ships a new type (P-03).
- **Reading `violation.orig.__cause__.sqlstate`** — a second idiom in the same package, and one that silently never matches (P-02).
- **A `/webhooks/*` prefix or wildcard route** — forbidden by `SHARED-INVARIANTS.md:63` and the whole point of APPLEHOOK-02.
- **Letting an Apple type cross the service boundary** — D-08 exists so Phase 44's Google class can produce the same value type. `services/subscriptions.py` must import nothing from `appstoreserverlibrary`; a unit case asserting that is cheap and mirrors `TestNoProviderDependency`.
- **Calling `verify` through `run_in_threadpool`** — D-07 forbids it and D-09 makes it unnecessary. With `enable_online_checks=False` no code path in `signed_data_verifier` reaches `requests`, so nothing blocks the loop.
- **Logging `signedPayload`, `appAccountToken` or `identity_value`** — `auth/devicecheck.py` holds no logger at all for exactly this reason (Phase 41 decision). `AppStoreNotifications` should do the same.
- **A `checkRevoked`-style per-request network call** — `SHARED-INVARIANTS.md:60`, and the Phase 35 barrier rule.
- **Locking the subscription row** — D-16 forbids it: it would be a lock tier ahead of the grant locks, against `SHARED-INVARIANTS.md` § Locks, and it does not exist on the first insert.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWS `x5c` chain validation | A `PyJWT` decode plus a manual `X509Store` walk | `SignedDataVerifier` | It performs six checks a hand-roll forgets: exactly-3 chain length, `X509_STRICT` flags, Apple OID `1.2.840.113635.100.6.11.1` on the leaf, OID `1.2.840.113635.100.6.2.1` on the intermediate, `alg == ES256` enforced from the header, and a non-empty `x5c`. Mandated by the brief (`:48`). [VERIFIED: `signed_data_verifier.py:158-231`] |
| Bundle-id / app-apple-id / environment binding | Comparing decoded fields in the handler | `SignedDataVerifier`'s own `_verify_notification` and the per-payload checks | It already does it, and it applies the app-apple-id check **only in Production**, which is the correct asymmetry and easy to get wrong by hand. |
| Notification-type parsing | A `StrEnum` mirroring Apple's twenty types | `rawNotificationType` as plain text | D-13 records `event_type` as received. A mirrored enum is a maintenance obligation that buys nothing and breaks on Apple's next release (P-03). |
| Replay suppression | An application-level seen-set or cache | `audit.subscription_events.notification_uuid UNIQUE` + the pre-write read | The index is the only correct arbiter under two concurrent deliveries; the read is a fast path, not the guarantee. D-20. |
| One-active-grant enforcement | A read-then-write check | `ix_access_grants_one_active_per_user` (partial, non-deferrable) | Phase 41's decision: with no grant row to lock, `FOR UPDATE` locks nothing, so the unique index *is* the concurrency guarantee. |
| Constraint identification | Parsing the `IntegrityError` message or naming the constraint | `violation.orig.sqlstate != "23505"` | Phase 42-07. A message parse breaks on a PostgreSQL upgrade or a locale change. |
| Certificate acquisition | Fetching Apple's root at runtime | The committed DER at `config/certs/AppleRootCA-G3.cer` | A runtime fetch is a network call on the admission path and a trust-on-first-use hole. It is already committed (P-01). |
| Rate limiting on this route | Any backend limiter | Nothing, deliberately | Phase 35 D-05 deleted the engine from the product; D-06 flags the gateway deferral. Building one here re-opens a settled milestone decision. |

**Key insight:** every rule in D-13 through D-21 is a rule about *when to write*, and every one of them is ultimately arbitrated by a database constraint that already exists in the single migration. The application code's job is to ask the questions in the right order under the right locks; it is never to be the last line of defence. Where the two disagree, the constraint wins loudly — `08-webhook-app-store.md:42` says so explicitly: *"no reconciliation sweep exists — a writer's bug surfaces as a loud commit failure."*

## The Four Tables, As They Actually Exist

The migration is not edited by this phase. These are the exact shapes the models must match, quoted verbatim from `migrations/20260818_01_initial-release.sql`.

**`core.subscriptions` (`:128-149`)** — note `user_id` is nullable (D-17's unclaimed row), `product_entitled_subscription_id` is `GENERATED ALWAYS AS … STORED` and **must be omitted from the model** (the 36-01 rule: PostgreSQL rejects an explicit value), and `UNIQUE (id, user_id)` exists *"solely as a composite FK target"*.

```sql
    product_entitled_subscription_id UUID GENERATED ALWAYS AS (
        CASE WHEN status IN ('active', 'grace_period') THEN id END
    ) STORED,
```
```sql
CREATE UNIQUE INDEX ix_subscriptions_provider_external_id
    ON core.subscriptions (provider, external_id);
```

**`core.store_purchases` (`:170-190`)** — the write order is forced by two composite foreign keys:

```sql
    UNIQUE (provider, external_id),
    -- Keeps resolved_token_value from drifting away from identity_value.
    CHECK (resolved_token_value IS NULL OR resolved_token_value = identity_value),
    FOREIGN KEY (provider, external_id)
        REFERENCES core.subscriptions (provider, external_id),
    -- MATCH SIMPLE: a NULL resolved_token_value skips the check, so an unattributed purchase still records.
    FOREIGN KEY (provider, resolved_token_value)
        REFERENCES core.store_purchase_tokens (provider, identity_value)
```

The subscription row must be flushed before the purchase row. The `CHECK` also constrains D-17: `resolved_token_value` is either `NULL` or exactly equal to `identity_value` — it can never be a third value.

**`audit.subscription_events` (`:196-205`)** — `subscription_id` is `NOT NULL`, which is D-22's whole reason:

```sql
CREATE TABLE audit.subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES core.subscriptions (id),
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_tier_id TEXT REFERENCES core.access_tiers (id),
    new_tier_id TEXT REFERENCES core.access_tiers (id),
    created_at TIMESTAMPTZ NOT NULL
);
```

**`core.access_grants` (`:208-240`)** — the two deferrable FKs D-19 names:

```sql
    -- Deferred so ingestion and restore can write both rows in one transaction, in either order.
    FOREIGN KEY (active_subscription_grant_subscription_id, active_subscription_grant_user_id)
        REFERENCES core.subscriptions (id, user_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (active_subscription_grant_subscription_id)
        REFERENCES core.subscriptions (product_entitled_subscription_id)
        DEFERRABLE INITIALLY DEFERRED
```
```sql
-- Superseded term rows stay in history while at most one active grant per subscription exists.
CREATE UNIQUE INDEX ix_access_grants_one_per_subscription
    ON core.access_grants (subscription_id)
    WHERE source = 'subscription' AND subscription_id IS NOT NULL AND status = 'active';
```

[VERIFIED: all four blocks read from `migrations/20260818_01_initial-release.sql` this session and quoted verbatim]

`ix_access_grants_one_per_subscription` is the index that makes D-15's flip-then-insert mandatory: two active grants for one subscription is refused per-statement, so the old term must be flipped and flushed before the new one is inserted — the same shape and the same reason as `crud/grants.py`'s conversion path (Pattern 3).

**Three seeded tiers** (`:123-126`): `('anonymous', 10)`, `('registered', 50)`, `('paid', 1000)`. D-14's map targets `'paid'`.

## Common Pitfalls

### Pitfall 1: `notificationType` is `None` for an unrecognised type

**What goes wrong:** `event_type` is written as `None` into `audit.subscription_events.event_type TEXT NOT NULL`; the flush raises, the route answers 5xx, and Apple retries five times and gives up. Subscription state is lost for every notification of the new type.
**Why it happens:** `create_raw_attr` sets the typed attribute only when the raw string is an enum member (P-03).
**How to avoid:** `event_type = decoded.rawNotificationType`. Same for `rawSubtype`, `rawEnvironment`, `rawStatus`.
**Warning signs:** any use of `NotificationTypeV2` outside a test. D-13 says the type is *only* recorded, never branched on, so the enum should not appear in `src/` at all.

### Pitfall 2: `SignedDataVerifier` construction raises `ValueError` and kills the pod

**What goes wrong:** `environment: production` with no `app_apple_id` → `ValueError` inside lifespan → the app never starts (P-04).
**Why it happens:** the library validates the combination in `__init__`, not at verify time, and `ValueError` is not an `AppError` so no handler catches it.
**How to avoid:** treat Production-without-app-apple-id as *unconfigured* — warn and pass `None`, exactly as an absent `bundle_id` is treated.
**Warning signs:** a lifespan completeness test that checks fields individually rather than the combination.

### Pitfall 3: the two wiring cases fail and look like a bad merge

**What goes wrong:** `uv run pytest -q` drops two cases the moment `app/main.py` includes the router (P-05).
**How to avoid:** plan the `tests/unit/test_app_wiring.py` edit in the **same** task as the `include_router` call, and re-measure `CURRENT` in `test_auth_package_shape.py` (P-06) in the same task as `auth/app_store.py`.
**Warning signs:** a wave order that registers the route before the test file is touched.

### Pitfall 4: nested payloads verified by the envelope alone

**What goes wrong:** `data.signedTransactionInfo` is used as purchase evidence without its own verification. The envelope's signature says nothing about the nested JWS.
**Why it happens:** the envelope decodes into a typed object whose `signedTransactionInfo` is already populated with a string, so it *looks* verified.
**How to avoid:** D-07's three calls. The brief is explicit (`:48`): *"the outer envelope alone is insufficient."*
**Measured detail worth knowing:** the two nested verifiers check different things. `verify_and_decode_signed_transaction` checks `bundleId` **and** `environment`; `verify_and_decode_renewal_info` checks `environment` only, because renewal info carries no `bundleId` field. Feeding a renewal-info JWS to the transaction verifier is caught anyway — measured `-> INVALID_APP_IDENTIFIER`. [VERIFIED: measured this session; source at `signed_data_verifier.py:57-77`]

### Pitfall 5: copying Apple's own documented loop

`for signed_txn in notification.data.signedTransactionInfo:` iterates a string. P-12.

### Pitfall 6: `X509_STRICT` and the OIDs make a naive throwaway chain fail

**What goes wrong:** D-24's unit chain is generated without the two Apple OIDs, or with a two-cert or four-cert `x5c`, and every case fails with `VERIFICATION_FAILURE` or `INVALID_CHAIN_LENGTH` — reading as "the seam is broken" rather than "the fixture is wrong".
**How to avoid:** § Code Example 6, which is the recipe measured working this session (P-10).
**Warning signs:** a chain builder that omits `SubjectKeyIdentifier`/`AuthorityKeyIdentifier`/`BasicConstraints`; `X509_STRICT` is on by default.

### Pitfall 7: a misconfigured deployment silently loses six days of notifications

**What goes wrong:** a wrong `bundle_id` or `environment` makes every genuine Apple notification a 401. Apple retries at 1, 12, 24, 48 and 72 hours, then stops (P-11). Nothing is written and nothing alerts.
**How to avoid:** `stage=<VerificationStatus name>` on the `notification_rejected` WARNING (D-04) distinguishes `INVALID_APP_IDENTIFIER` / `INVALID_ENVIRONMENT` — a configuration fault — from `VERIFICATION_FAILURE` — a forged or corrupt payload. Name that distinction in the requirement amendment so an operator knows what to look for.

### Pitfall 8: the request body reaches a log line

**What goes wrong:** `signedPayload` or `appAccountToken` in a structured log. `appAccountToken` is a lifetime attribution token and `store_purchase_tokens.identity_value` is its stored twin.
**How to avoid:** `RequestLoggingMiddleware` never reads the body [VERIFIED: `src/nativespeaker/api/logs.py:56-76`, whole method read — it binds `request_id`, `method`, `url.path` and logs `status_code` and `duration_ms`, nothing else]. Give `auth/app_store.py` no logger at all, as `auth/devicecheck.py` has none. `validation_error_handler` already logs only `loc` and `type`, never `input`.
**Warning signs:** any `logger` binding inside the seam; any log field carrying a value the store supplied.

### Pitfall 9: `get_db` opens for a malformed body

Not a defect, but do not write a case asserting the opposite. P-08.

### Pitfall 10: an unattributed purchase needs a generated `identity_value`

**What goes wrong:** `core.store_purchases.identity_value` is `TEXT NOT NULL`, so the unattributed case (D-17) cannot leave it empty. Only `resolved_token_value` is nullable.
**How to avoid:** D-17 already says it — *"a server-generated UUID as `identity_value` when the store gives none"*. The `CHECK (resolved_token_value IS NULL OR resolved_token_value = identity_value)` then passes trivially, because `resolved_token_value` is `NULL`.

## Code Examples

### 1. Building the verifier in lifespan, guarded against P-04

```python
# Source: pattern of app/lifespan.py:36-49 (devicecheck) + signed_data_verifier.py:32-42
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

store = config.app_store
root = Path(store.root_certificate_path) if store.root_certificate_path else None
# Production needs the app id too: the library raises ValueError without it, and that would stop boot.
complete = bool(store.bundle_id and store.environment and root and root.is_file()) and (
    store.environment != "production" or store.app_apple_id is not None)
if not complete:
    logger.warning("app_store_configuration_absent",
                   consequence="POST /webhooks/app-store fails closed as "
                               "verification_temporarily_unavailable until the App Store bundle id, "
                               "environment and root certificate are available in this environment")
verifier = SignedDataVerifier(
    root_certificates=[root.read_bytes()],
    enable_online_checks=False,          # D-09: no network call on the admission path.
    environment=Environment(store.environment.capitalize()),
    bundle_id=store.bundle_id,
    app_apple_id=store.app_apple_id,
) if complete else None
app.state.app_store_notifications = AppStoreNotifications(verifier=verifier)
```

Note `Environment` members are `"Sandbox"` and `"Production"` (capitalised strings), not `"sandbox"`/`"production"` [VERIFIED: `models/Environment.py:12-15`, quoted verbatim: `SANDBOX = "Sandbox"`, `PRODUCTION = "Production"`, `XCODE = "Xcode"`, `LOCAL_TESTING = "LocalTesting"`]. D-11's config values are lowercase, so the mapping is explicit. **`XCODE` and `LOCAL_TESTING` skip signature verification entirely** — see § Security Domain.

### 2. The seam's `verify`, three calls and one catch

```python
# Source: shape of auth/devicecheck.py; call contract from signed_data_verifier.py:44-113
def verify(self, signed_payload: str) -> VerifiedNotification:
    """Verify Apple's envelope and both nested payloads, then return our value type."""
    if self._verifier is None:
        raise Unavailable(stage="app_store_verify")
    try:
        decoded = self._verifier.verify_and_decode_notification(signed_payload)
    except VerificationException as failure:
        raise NotificationRejected(stage=failure.status.name) from failure
    ...
```

`failure.status` is a `VerificationStatus`, whose eight members are, verbatim: `OK = 0`, `VERIFICATION_FAILURE = 1`, `INVALID_APP_IDENTIFIER = 2`, `INVALID_CERTIFICATE = 3`, `INVALID_CHAIN_LENGTH = 4`, `INVALID_CHAIN = 5`, `INVALID_ENVIRONMENT = 6`, `RETRYABLE_VERIFICATION_FAILURE = 7` [VERIFIED: `signed_data_verifier.py:357-365`, quoted verbatim]. `.name` is therefore a closed set of eight strings — a safe structured-log label under the project's "closed set, never provider text" rule.

Note `RETRYABLE_VERIFICATION_FAILURE` is produced **only** by `check_ocsp_status`, which is unreachable with `enable_online_checks=False`. Under D-09 the reachable set is seven.

### 3. Mapping Apple's fields to `VerifiedNotification` (D-08)

All timestamps are **UNIX milliseconds as `int`**, and every field is `Optional`.

| Our field (D-08) | Apple source | Apple type | Note |
|---|---|---|---|
| `notification_uuid` | `ResponseBodyV2DecodedPayload.notificationUUID` | `str` | the replay key |
| `event_type` | `.rawNotificationType` | `str` | **not** `.notificationType` (P-03) |
| `external_id` | `JWSTransactionDecodedPayload.originalTransactionId` | `str` | |
| `transaction_id` | `.transactionId` | `str` | |
| `product_id` | `.productId` | `str` | D-14's map key |
| `attribution_token` | `.appAccountToken` | `str` | may be absent (D-17) |
| `purchased_at` | `.purchaseDate` | `int` ms | |
| `expires_at` | `.expiresDate` | `int` ms | D-15's term boundary |
| `revoked_at` | `.revocationDate` | `int` ms | `None` when not revoked |
| `grace_period_expires_at` | `JWSRenewalInfoDecodedPayload.gracePeriodExpiresDate` | `int` ms | **renewal info, not transaction** |
| `in_billing_retry` | `.isInBillingRetryPeriod` | `bool` | **renewal info, not transaction** |

[VERIFIED: field names and types read from `models/JWSTransactionDecodedPayload.py` and `models/JWSRenewalInfoDecodedPayload.py` this session]

The last two live on the **renewal info** payload only, which is why D-07's third library call is not optional for a subscription notification. Conversion:

```python
_ms = lambda v: datetime.fromtimestamp(v / 1000, UTC) if v is not None else None
```

### 4. Deriving `core.subscriptions.status` from the dates (D-13)

The five labels are `'active'`, `'grace_period'`, `'billing_retry'`, `'expired'`, `'revoked'` (P-15), evaluated against the one captured `evaluated_at`:

```python
def status_at(n: VerifiedNotification, evaluated_at: datetime) -> SubscriptionStatus:
    """The subscription's status from its dates alone. The notification type is only recorded."""
    if n.revoked_at is not None:
        return SubscriptionStatus.revoked
    if n.expires_at is not None and n.expires_at > evaluated_at:
        return SubscriptionStatus.active
    if n.grace_period_expires_at is not None and n.grace_period_expires_at > evaluated_at:
        return SubscriptionStatus.grace_period
    if n.in_billing_retry:
        return SubscriptionStatus.billing_retry
    return SubscriptionStatus.expired
```

The arm order is the plan's to fix and to justify; what is fixed by the schema is that `('active', 'grace_period')` is the entitled set — `product_entitled_subscription_id` is generated over exactly those two, and the two deferrable FKs on `core.access_grants` bind an active subscription grant to it. Anything else must leave the grant `expired` or `revoked` in the same transaction (D-18/D-19) or the commit fails.

### 5. The wiring assertions D-01 describes, against the shipped helpers

```python
# Source: tests/unit/test_app_wiring.py, extending its existing `_api_routes` / `_declared` helpers.
PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}

def test_the_partition_is_exactly_the_routes_on_the_webhooks_router(self):
    from nativespeaker.api.routers import webhooks_router
    on_router = {route.path for route in webhooks_router.routes}
    assert on_router == PROVIDER_CALLBACK_PATHS

def test_each_callback_route_declares_the_verifier_and_no_identity(self):
    for route in _api_routes():
        if route.path in PROVIDER_CALLBACK_PATHS:
            assert verify_app_store_notification in _declared(route)
            assert get_identity not in _declared(route)
            assert get_linked_identity not in _declared(route)

def test_no_route_outside_the_partition_declares_the_verifier(self):
    leaked = [route.path for route in _api_routes()
              if route.path not in PROVIDER_CALLBACK_PATHS
              and verify_app_store_notification in _declared(route)]
    assert leaked == []

def test_the_public_allowlist_is_still_exactly_the_readiness_probe(self):
    """Separated from the structural set below, which the callback route also joins."""
    assert PUBLIC_PATHS == {"/health/ready"}
```

and the two existing cases become (P-05):

```python
    if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS | PROVIDER_CALLBACK_PATHS
```
```python
    assert unauthenticated == PUBLIC_PATHS | PROVIDER_CALLBACK_PATHS
```

### 6. The throwaway chain for D-24, measured working

```python
# Source: measured this session; requirements read from signed_data_verifier.py:199-231.
LEAF_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.11.1")   # required on the leaf
INT_OID  = x509.ObjectIdentifier("1.2.840.113635.100.6.2.1")    # required on the intermediate

# root: BasicConstraints(ca=True) critical, KeyUsage(key_cert_sign, crl_sign) critical,
#       SubjectKeyIdentifier. Self-signed with its own EC P-256 key.
# intermediate: BasicConstraints(ca=True, path_length=0) critical, the same KeyUsage,
#       SubjectKeyIdentifier, AuthorityKeyIdentifier.from_issuer_public_key(root),
#       and UnrecognizedExtension(INT_OID, b"\x05\x00").  Signed by the root key.
# leaf: BasicConstraints(ca=False) critical, KeyUsage(digital_signature) critical,
#       SubjectKeyIdentifier, AuthorityKeyIdentifier.from_issuer_public_key(intermediate),
#       and UnrecognizedExtension(LEAF_OID, b"\x05\x00").  Signed by the intermediate key.

x5c = [b64encode(c.public_bytes(Encoding.DER)).decode() for c in (leaf, intermediate, root)]
token = pyjwt.encode(payload, leaf_key, algorithm="ES256", headers={"x5c": x5c})
```

Order is leaf, intermediate, root, and the list must be exactly three long. All three certificates need SHA-256 signatures and EC P-256 keys (`alg` must be `ES256`). `b"\x05\x00"` is a DER NULL — the OID's presence is what is checked, never its value.

Measured result, both halves of D-24's contract:

```
VERIFIED OK -> NotificationTypeV2.TEST | raw: TEST | uuid-1
CONTROL OK -> apple root refuses: VERIFICATION_FAILURE
```

A minimum envelope payload the library accepts (a payload carrying **neither** `data` nor `summary` is rejected `INVALID_APP_IDENTIFIER` — measured):

```python
{"notificationType": "TEST", "notificationUUID": "…", "version": "2.0",
 "signedDate": int(time.time() * 1000),
 "data": {"environment": "Sandbox", "appAppleId": 123, "bundleId": "com.example.app"}}
```

## Test Ratchets This Phase Trips

Every one of these is an `==` against a written-down literal, deliberately so, and each is the file's own instruction to a later phase.

| File | Literal | Why it trips | Fix, and where it belongs |
|---|---|---|---|
| `tests/unit/test_app_wiring.py` | `PUBLIC_PATHS` used in two structural set comparisons | The callback route declares no identity accessor (P-05, measured) | Add `PROVIDER_CALLBACK_PATHS` to both unions; add a separate literal case for `PUBLIC_PATHS`. Same task as `include_router`. |
| `tests/unit/test_auth_package_shape.py` | `CURRENT = (5, 12, 35)` | `auth/app_store.py` is a sixth module (P-06) | Re-measure and write the triple down, in the commit that adds the module. |
| `tests/unit/test_rejection_vocabulary.py` | `EVENT_NAMES` frozenset, `==` | Three new classes in the error tree (P-07) | Three entries; plus `CONSTRUCTOR_ARGUMENTS` for any class with required kwargs. |
| `tests/unit/test_docstring_bar.py` | `BASELINE = {…: 0}` for all five roots, `==` | Any docstring over three lines in new `src/` or `tests/` code | Keep every docstring at three lines or fewer. D-25 and `AGENTS.md` already require it; this is the gate. |

**Measured as NOT tripping:** `tests/unit/test_grant_sources.py`. Its `_construction_sites` and `_mentions` walks filter on `AccessGrantSource.anonymous_device_grant` and `AccessGrantSource.registered_account_grant` specifically; a new writer naming only `AccessGrantSource.subscription` is invisible to all four cases and to both `NAMING_MODULES` sets. [VERIFIED: `tests/unit/test_grant_sources.py:19-35` and `:41-62`, read this session]

That is worth naming as a **gap, not a relief**: the subscription grant will be this project's third grant source and the only one with no single-writer walk behind it. A third class mirroring `TestTheRegisteredAccountGrantHasExactlyOneWriter` is roughly 25 lines and is the cheapest way to keep Phase 45's restore from quietly becoming a second writer. Recommended, at the planner's discretion.

## Common Verification Commands

Reused verbatim from prior phases; all four run clean at the baseline measured this session.

```bash
uv run pytest -q                  # 1016 passed, 395 deselected, 33.97s
uv run pytest -m e2e -q           #  241 passed, 1170 deselected, 43.14s
uv run pytest -m schema -q        #  154 passed, 1257 deselected, 17.68s
uv run ruff check src tests       # All checks passed!
```

[VERIFIED: each command run this session; output quoted from the tail of each run]

`pyproject.toml:58` sets `addopts = "-v --tb=short -m 'not e2e and not schema'"`, so the default invocation is the unit suite alone and the two markers must be passed explicitly. **These baselines supersede STATE.md's Phase 42 record of 1001/237/147** — that was the count at the moment Phase 42 marked its requirements, and the suite has grown by 15/4/7 since.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | the `tests/schema` suite, the dev database | ✓ | 17.11 (Debian 17.11-1.pgdg13+2), `localhost:5432`, databases `nativespeaker` and `postgres` both reachable | — |
| `uv` | every verify command | ✓ | 0.12.5 | — |
| `app-store-server-library` | D-07 | ✓ | 3.0.0 (`uv.lock` pinned) | — |
| `cryptography` | D-24's throwaway chain | ✓ | 46.0.5 | — |
| `pyOpenSSL` | the library's chain check | ✓ | 26.0.0 | — |
| `openssl` CLI | inspecting the vendored certificate | ✓ | 3.5.7 | not needed at runtime |
| Apple Root CA G3 DER | D-10 | ✓ | `config/certs/AppleRootCA-G3.cer`, tracked, valid to 2039-04-30 | — |
| `psql` / `pg_isready` CLI | nothing | ✗ | — | the suites use `asyncpg` directly; `tests/schema/conftest.py` creates and drops its own scratch database `ns_schema_test` over asyncpg |
| A real Apple App Store server | a real end-to-end round trip | ✗ | — | **No fallback, and none needed — see below** |

[VERIFIED: every row probed this session]

**Missing dependencies with no fallback:** none that block execution.

**The one that matters, recorded as a fact about the world rather than a gap.** No round trip to Apple's App Store server has ever been made and none can be: there is no iOS app, so nothing can produce a genuine `signedPayload`. This is the same standing fact STATE.md records for DeviceCheck (41-05 D-04). The difference, and it is a large one in this phase's favour: **DeviceCheck's wire shapes were `[ASSUMED]` from secondary sources, and this phase's are not.** Verification here is pure local computation through Apple's own library, and D-24's throwaway chain exercises the real code path end to end — the chain walk, the OID checks, the `ES256` enforcement and the signature check all run for real against a locally minted payload (P-10, measured). What remains untested by construction is only whether Apple's *production* notifications match the shapes Apple's own library declares, which is a much smaller residual than a hand-derived wire contract.

**Recommendation:** carry a short note in the seam's module docstring or a test module docstring, as `tests/unit/test_devicecheck_adapter.py` does, saying which parts are exercised for real and which are not, so a later reader does not read green unit cases as evidence the integration is live.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x with pytest-asyncio 1.3 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (:52-68) |
| Quick run command | `uv run pytest -q` (34s at baseline) |
| Full suite command | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` |

Markers: `e2e` and `schema`, both deselected by `addopts`.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APPLEHOOK-01 | A payload signed by a chain rooting in the configured root verifies, and the value type carries our field names | unit | `uv run pytest tests/unit/test_app_store_notifications.py -q` | ❌ Wave 0 |
| APPLEHOOK-01 | The vendored Apple root refuses the throwaway chain (the control that makes the case above non-vacuous) | unit | same file | ❌ Wave 0 |
| APPLEHOOK-01 | Each of the seven reachable `VerificationStatus` outcomes becomes one 401 `auth_required` with its own `stage` | unit | same file | ❌ Wave 0 |
| APPLEHOOK-01 | A nested transaction or renewal payload that fails on its own is 401 even when the envelope verifies | unit | same file | ❌ Wave 0 |
| APPLEHOOK-01 | An unrecognised `notificationType` yields `event_type` as the raw string (P-03) | unit | same file | ❌ Wave 0 |
| APPLEHOOK-01 | Absent or incomplete config answers 503 `verification_temporarily_unavailable`, including Production-without-app-apple-id (P-04) | unit + e2e | `uv run pytest tests/unit/test_app_store_notifications.py tests/e2e/test_app_store_webhook.py -q` | ❌ Wave 0 |
| APPLEHOOK-01 | A valid Firebase ID token with a bad payload is still 401 (D-05) | e2e | `uv run pytest tests/e2e/test_app_store_webhook.py -q` | ❌ Wave 0 |
| APPLEHOOK-01 | `services/` imports nothing from `appstoreserverlibrary` (the D-08 boundary) | unit (ast walk + control) | `uv run pytest tests/unit/test_app_store_notifications.py -q` | ❌ Wave 0 |
| APPLEHOOK-02 | The partition equals the routes on the webhooks router | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ extend |
| APPLEHOOK-02 | Each callback route declares the verifier and neither identity accessor | unit | same file | ✅ extend |
| APPLEHOOK-02 | No route outside the partition declares the verifier | unit | same file | ✅ extend |
| APPLEHOOK-02 | `PUBLIC_PATHS` is still exactly `{"/health/ready"}` as a literal | unit | same file | ✅ extend |
| APPLEHOOK-02 | The route is reachable with no Authorization header (brief `:49`) | e2e | `uv run pytest tests/e2e/test_unauthenticated_access.py -q` | ✅ extend |
| D-13/D-15/D-17/D-18/D-19 | The ingestion writer's outcomes on real PostgreSQL: attributed, unattributed, renewal flip-then-insert, same-term no-op, newest-wins, non-entitled transition | schema | `uv run pytest tests/schema/test_subscription_ingestion.py -q` | ❌ Wave 0 |
| D-20 | Replay: the second delivery of one `notification_uuid` writes nothing and answers 200 | schema | same file | ❌ Wave 0 |
| D-20 | Two simultaneous deliveries on two connections: one applies, the loser sees 23505 and answers 5xx | schema | `uv run pytest tests/schema/test_subscription_race.py -q` | ❌ Wave 0 |
| D-16 | The emitted SQL takes grant locks before usage locks and no third tier | schema | `uv run pytest tests/schema/test_grant_locks.py -q` | ✅ extend |
| D-21 | `AttributionConflict` and `UnmappedStoreProduct` answer 500, log at ERROR, write nothing | e2e | `uv run pytest tests/e2e/test_app_store_webhook.py -q` | ❌ Wave 0 |
| D-22 | A TEST notification answers 200, writes nothing, logs at INFO | e2e | same file | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -q && uv run ruff check src tests`
- **Per wave merge:** `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q`
- **Phase gate:** all four green before `/gsd:verify-work`, quoted with their counts as Phases 41 and 42 did

### Wave 0 Gaps

- [ ] `tests/unit/test_app_store_notifications.py` — the seam; **needs a throwaway-chain fixture** (§ Code Example 6). The chain generation is the single largest piece of new test infrastructure in the phase and nothing like it exists in the repository today.
- [ ] `tests/e2e/test_app_store_webhook.py` — the route; needs a `scripted_app_store_notifications` fixture in `tests/e2e/conftest.py` mirroring `scripted_devicecheck_adapter` (:254-263).
- [ ] `tests/schema/test_subscription_ingestion.py` — the writer against real PostgreSQL; needs `insert_subscription` / `insert_store_purchase` helpers in `tests/schema/helpers.py` beside the existing `insert_grant` / `insert_usage` / `insert_tier` / `insert_user`.
- [ ] `tests/schema/test_subscription_race.py` — the two-connection race; `tests/schema/test_claim_race.py` is the harness to extend (its `_Harness` dataclass, per-test private issuer, `BARRIER_TIMEOUT_SECONDS = 20`, and FK-ordered cleanup).
- [ ] Framework install: none — pytest, pytest-asyncio and a real PostgreSQL are all present.

**Note on generation cost:** the throwaway chain is three EC key generations plus three certificate signings. Measured at well under a second in the probe above, so a module-scoped fixture is ample and a session-scoped one is unnecessary.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | **yes** | The whole of it. `SignedDataVerifier` JWS + `x5c` chain to Apple Root CA G3 is the only credential; no header, no shared secret, no token. Failure → 401, fail closed. |
| V3 Session Management | no | The route creates no session and mints nothing (brief `:52`). |
| V4 Access Control | **yes** | Handler authority is narrow (brief `:52`): entitlement only, on the account the subscription is already linked to. It never creates a `core.users` or `core.external_identities` row. |
| V5 Input Validation | **yes** | Pydantic on the one-field body; every business value comes from a **verified** payload, never from the request envelope. |
| V6 Cryptography | **yes** | Apple's library — ES256 verification and X.509 path building. **Never hand-rolled** (brief `:48`). |
| V7 Error Handling & Logging | **yes** | One class for every verification failure (D-04), so the route is no oracle. No body field ever logged (Pitfall 8). |
| V8 Data Protection | **yes** | `appAccountToken` and `identity_value` are lifetime attribution tokens; the brief's DELETIONS forbid persisting raw signed payloads outside the verification path (`:54`). |
| V13 API & Web Service | **yes** | Exact-path route, `redirect_slashes = False`, no wildcard (`SHARED-INVARIANTS.md:63`). |

### Known Threat Patterns for a public unauthenticated webhook

| Pattern | STRIDE | Standard Mitigation | Status here |
|---|---|---|---|
| Forged notification | Spoofing | Full JWS + chain verification against a **pinned** root before any business logic | D-07. The pinned root is the vendored G3 (P-01) — the chain's own third element is never trusted as sent. |
| Envelope-only verification (nested payload injection) | Tampering | Verify each nested JWS independently | D-07's three calls; brief `:48` |
| Replay | Tampering | `notification_uuid UNIQUE` + pre-write read | D-20. Endorsed by Apple's own guidance (P-11). |
| Sandbox notification accepted in production | Spoofing / Elevation | `environment` bound at verifier construction; the library checks it on the envelope **and** on each nested payload | D-11's no-default. Measured: `Sandbox payload against Production verifier -> INVALID_ENVIRONMENT` |
| Wrong-app notification accepted | Spoofing | `bundle_id` on the envelope and the transaction; `app_apple_id` in Production | Measured: `bundleId mismatch -> INVALID_APP_IDENTIFIER` |
| Error-message oracle | Information Disclosure | One class, one body, for every verification failure; the reason goes to the server-side log only | D-04, and the shipped `ErrorResponse` is one field |
| Attribution hijack | Elevation of Privilege | An existing purchase row's `identity_value` differing from the presented token is refused, never reassigned | D-21 `AttributionConflict`; brief `:43` |
| Client-supplied purchase evidence | Elevation of Privilege | Restore (Phase 45) is behind the auth dependency; this route accepts nothing client-submitted | brief `:53` |
| Unbounded request volume | Denial of Service | **None, deliberately.** No backend limiter (Phase 35 D-05), no gateway entry (D-06, deferred to v2.1) | See the residual below |
| Secret in a log line | Information Disclosure | Middleware never reads the body; the seam holds no logger | Pitfall 8 |

### Two residuals worth writing into the requirement amendment

**1. `Environment.XCODE` and `Environment.LOCAL_TESTING` skip signature verification entirely.**

```python
            if self._environment == Environment.XCODE or self._environment == Environment.LOCAL_TESTING:
                # Data is not signed by the App Store, and verification should be skipped
                # The environment MUST be checked in the public method calling this
                return decoded_jwt
```
[VERIFIED: `.venv/.../signed_data_verifier.py:157-160`, quoted verbatim — the library's own comment]

D-11 restricts `environment` to `sandbox | production`, which closes this. **That restriction is now load-bearing security, not tidiness**, and the plan should enforce it as a typed config value (a `StrEnum` or `Literal["sandbox", "production"]`) rather than a free `str`, with a case proving `"Xcode"` and `"LocalTesting"` are refused at config load. A free-text field with a `.capitalize()` mapping would accept `"xcode"` and silently turn the route into an open endpoint.

**2. `enable_online_checks=False` moves the certificate-validity clock to the payload (P-09).** Measured. D-09's recorded reason should carry it.

**3. The unbounded-request residual, on the standing precedent.** This route is publicly reachable with no credential and no limiter at either layer, and each request costs a full certificate-path build plus three ES256 verifications — more CPU per request than the DeviceCheck routes, and, unlike them, reachable by **anyone**, with no valid Firebase token required first. That is a genuinely wider exposure than the three accepted residuals STATE.md already records (40 D-22, 41 D-20, 42 D-16), each of which needs a valid token for an existing account.

Mitigating, and it is the reason this is a record and not a blocker: the work is bounded and local (no network call, no database session — verification runs and fails **before** `get_db`, P-08), a rejected payload writes nothing, and the answer is a constant-size body. It is a CPU-burn vector, not an amplification or a data vector. **Closes with:** the v2.1 gateway contract, which D-06 already flags as a deferral for this exact path. Recommend recording it under APPLEHOOK-01 as **accepted, on the Phase 35 D-05 / D-08 precedent**, and — because it is wider than its three predecessors — saying so in the entry rather than filing it as one more of the same.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Verify the receipt with `verifyReceipt` (the App Store Receipt Validation endpoint) | App Store Server Notifications V2 + local JWS verification | V2 notifications; `verifyReceipt` is deprecated | No outbound call to Apple to verify a notification — which is what makes D-09's "no network call on the admission path" reachable at all. |
| Hand-rolled `x5c` chain walking | Apple's official server library | 2023, when Apple published it | Mandated by the brief. Removes six easily-forgotten checks (§ Don't Hand-Roll). |
| A route registry with a three-way category and a startup enumeration assertion | A dedicated `APIRouter` whose membership is the set of routes on it | Phase 37.1 D-06 deleted the registry, 2026-08-24 | D-01. The prohibition in `SHARED-INVARIANTS.md:63` survived the machinery that enforced it, which is the whole of APPLEHOOK-02. |
| `AuthEventResult`, a 44-member outcome enum | Exception classes in one tree under `AppError` | Phase 37.3 D-12 | D-04 and D-21 add leaves, never enum members. |

**Deprecated / outdated in this repo:**
- `orig.__cause__.sqlstate` and the `UNIQUE_VIOLATION` constant — deleted by `6b14231` (P-02).
- `/webhooks/apple` in `k8s/templates/httproute-webhooks.yaml` — renamed by D-06.
- STATE.md's suite counts of 1001/237/147 — superseded by 1016/241/154 measured this session.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The five arms and their order in § Code Example 4's `status_at` match what the product wants — `revoked` first, then a live `expires_at`, then grace, then billing retry, then expired. The **five labels** are verified from the migration; the **precedence between them** is my construction from D-13's wording, not a rule stated anywhere. | Code Examples (4) | A wrong order mislabels a subscription in grace period as expired, or vice versa, and the entitled set `('active', 'grace_period')` is what the generated column and both deferrable FKs key on — so a wrong arm order becomes a wrong grant, not just a wrong label. The plan should fix and justify the order explicitly rather than inherit this sketch. |
| A2 | `AppStoreNotifications.verify` being synchronous and called inline is safe because `enable_online_checks=False` makes `check_ocsp_status` unreachable. I traced the call graph and it is the only site that touches `requests`, but I did not measure the CPU cost of one verification. | Anti-Patterns; D-07 | If a full path build plus three ES256 verifications is slow enough to matter under concurrency, an inline call blocks the event loop. Cheap to close: time one `verify()` call in a unit case and assert an upper bound, as `test_jwt_security.py` bounds its fetch counts. |
| A3 | Three new error classes (`NotificationRejected`, `AttributionConflict`, `UnmappedStoreProduct`) is the right count, and none of them needs a new `ErrorCode` member. `auth_required`, `verification_temporarily_unavailable` and `internal_error` all exist in the `ErrorCode` Literal. | Test Ratchets (P-07) | Understating the count means `EVENT_NAMES` is edited twice. Low cost either way. |
| A4 | `services/subscriptions.py`, `crud/subscriptions.py` and `tests/schema/test_subscription_ingestion.py` are the file names. These are at the planner's discretion per CONTEXT and I used them for concreteness only. | Project Structure; Validation Architecture | None. Naming only. |
| A5 | The e2e fixture will swap `app.state.app_store_notifications` the way `scripted_devicecheck_adapter` swaps `app.state.devicecheck_adapter`. I read that fixture but did not write and run a webhook equivalent. | Wave 0 Gaps | Low. The mechanism is identical and already proven by three routes. |
| A6 | A third single-writer walk for `AccessGrantSource.subscription` is worth roughly 25 lines. Estimated from the shape of the existing two classes, not written. | Test Ratchets | Estimation only; the recommendation stands regardless of the exact size. |

## Open Questions (RESOLVED)

All five were closed during planning. Each carries its answer and the plan that holds it.

1. **Does `AppStoreConfig.environment` become a typed value or stay a free string?**
   - **RESOLVED — typed.** 43-01 Task 1 § Config declares `StoreEnvironment`, a StrEnum with exactly
     `sandbox` and `production`, and lifespan maps it to the library enum by an explicit two-arm
     mapping, so `Xcode` and `LocalTesting` are unreachable. 43-05 Task 3 asserts the member set by
     equality and asserts that both skipping values are refused at load. Carried as threat T-43-04.
   - What we know: D-11 says `sandbox | production` with no default, and the library's `Environment` enum also carries `Xcode` and `LocalTesting`, which **skip signature verification entirely** (verified, quoted above).
   - What's unclear: whether D-11 intended `Literal["sandbox", "production"]` or a plain `str | None`.
   - Recommendation: **typed**, with a case proving `"Xcode"` and `"LocalTesting"` are refused at config load. This is the one place where a config-validation choice is a security control rather than a convenience, and it should be decided deliberately rather than fall out of an implementation.

2. **What is the arm order in `status_at`, and what justifies it?** (A1.)
   - **RESOLVED — order fixed and grounded.** 43-01 Task 1 § Service states the five arms in order —
     revoked, live `expires_at`, grace, billing retry, expired — each carrying its one-line ground in
     the code, and grace is tested before billing retry because Apple sets the billing-retry flag
     during grace too. The arms are exercised where they have a consequence: the entitled set is
     exactly `active` and `grace_period` (43-04 Task 1), and 43-04 Task 2 runs one real-database case
     per entitlement arm.
   - What we know: the five labels, the entitled set, and that the notification type is only recorded.
   - What's unclear: the precedence, especially between `grace_period` and `billing_retry`, and whether a live `expires_at` should outrank a set `grace_period_expires_at`.
   - Recommendation: the plan states the order with a one-line ground for each arm and a table-driven unit case per arm, in the shape `tests/unit/test_claim_precedence.py` uses. This is D-13's whole content and deserves its own task.

3. **Does the phase add a single-writer walk for the subscription grant?**
   - **RESOLVED — yes.** 43-04 Task 3 extends `tests/unit/test_grant_sources.py` with a third
     single-writer class for `AccessGrantSource.subscription`, and mutation-checks it by adding a
     second construction site and showing the case fail.
   - What we know: measured — `test_grant_sources.py` does not cover it, and this will be the third source with the first two guarded.
   - Recommendation: yes, ~25 lines with its control, on the Phase 41 precedent that a structural `ast` test ships with a control. Phase 45's restore is the specific future writer it protects against.

4. **Does the phase bound `verify()`'s cost?** (A2.)
   - **RESOLVED — no, and the reason is recorded.** 43-01 `<flagged_assumptions>` states that A2 is
     closed structurally rather than by timing: no code path in the seam performs I/O, asserted by
     `enable_online_checks=False` at construction and by the negative greps on the seam. A wall-clock
     bound would be the flakiest kind of case and would not prove the property.
   - Recommendation: one unit case timing a verification, if it is cheap to write. Not a blocker.

5. **Where does the throwaway chain live?**
   - **RESOLVED — in the seam's own unit test file.** 43-01 Task 2 builds it as a module-scoped
     fixture in `tests/unit/test_app_store_notifications.py`, not in `tests/unit/conftest.py`.
   - What we know: it is the biggest new test fixture and D-24 leaves the location at discretion.
   - Recommendation: a module-scoped fixture in the seam's own unit test file rather than `tests/unit/conftest.py`, until Phase 44 needs it. Phase 44 verifies a Google OIDC token, not an Apple chain, so it probably never will.

## Sources

### Primary (HIGH confidence — measured against installed source this session)

- `.venv/lib/python3.14/site-packages/appstoreserverlibrary/signed_data_verifier.py` — `SignedDataVerifier.__init__`, all five `verify_and_decode_*` methods, `_decode_signed_object`, `_ChainVerifier._verify_chain_without_caching`, `check_oid`, `check_ocsp_status`, `VerificationStatus`, `VerificationException`
- `.venv/.../appstoreserverlibrary/models/` — `ResponseBodyV2DecodedPayload`, `Data`, `JWSTransactionDecodedPayload`, `JWSRenewalInfoDecodedPayload`, `Environment`, `Status`, `NotificationTypeV2`, `LibraryUtility`
- Six executed probes: the throwaway chain + Apple-root control (P-10), the unknown-type raw fallback (P-03), the seven verification failure arms and the expired-leaf/backdated-signedDate pair (P-09), FastAPI dependency ordering with a body-taking router dependency (P-08), pydantic-settings env nesting for `app_store` (P-14), and the wiring-assertion injection against the real app object (P-05)
- `migrations/20260818_01_initial-release.sql` — the four tables, their indexes, the two deferrable FKs, the six enum types, the three seeded tiers
- `src/nativespeaker/api/` — `config.py`, `errors.py`, `logs.py`, `app/{main,lifespan,dependencies,error_handlers}.py`, `auth/devicecheck.py`, `crud/{grants,purchases}.py`, `routers/{auth,health,__init__}.py`, `tables/{grants,purchases,__init__}.py`, `services/{quota,sync,__init__}.py`
- `tests/unit/{test_app_wiring,test_auth_package_shape,test_rejection_vocabulary,test_docstring_bar,test_adapter_interfaces,test_grant_sources}.py`; `tests/e2e/{conftest,test_unauthenticated_access}.py`; `tests/schema/{conftest,test_claim_race}.py`
- `git show 6b14231` — the SQLSTATE change (P-02)
- `openssl x509` against all three files in `config/certs/` (P-01)
- Suite baselines: `uv run pytest -q`, `-m e2e -q`, `-m schema -q`, `ruff check src tests`

### Secondary (MEDIUM confidence — official documentation)

- https://developer.apple.com/documentation/appstoreservernotifications/responding-to-app-store-server-notifications — the retry schedule (5 retries at 1/12/24/48/72 hours)
- https://developer.apple.com/documentation/appstoreservernotifications/app-store-server-notifications-v2 — 200-206 success, 4xx/5xx retry
- https://github.com/apple/app-store-server-library-python/blob/main/_autodocs/api-reference/SignedDataVerifier.md — construction and usage, via Context7 `/apple/app-store-server-library-python` (source reputation High); **its `signedTransactionInfo` loop is wrong** (P-12)
- https://github.com/apple/app-store-server-library-python/blob/main/_autodocs/configuration.md — obtaining root certificates in DER format
- Apple Root CA G3 SHA-256 fingerprint, cross-checked against the vendored file
- Project documents: `08-webhook-app-store.md` (the brief, verbatim), `SHARED-INVARIANTS.md` § "Global deletions" `:57-64`, `.planning/REQUIREMENTS.md` § APPLEHOOK/PLAYHOOK, `.planning/STATE.md`, `AGENTS.md`, `43-CONTEXT.md`

### Tertiary (LOW confidence — none load-bearing)

- WebSearch summaries of Apple Developer Forums threads, used only to locate the official documentation pages above. No claim in this file rests on a forum post.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — nothing new is installed; every version read from the installed distribution and the lockfile
- Library behaviour: **HIGH** — read from the installed source and confirmed by six executed probes, not from documentation or memory
- Existing-codebase claims: **HIGH** — every file opened this session, every quoted value verbatim with a path and line range
- Test ratchets: **HIGH** — P-05 measured by injection; P-06 measured per module; P-07 and the `test_grant_sources.py` non-trip read from the assertions themselves
- Apple's operational contract (retries, status codes): **MEDIUM** — Apple's own documentation, `[CITED]`, not executable here
- Pitfalls: **HIGH** for the nine measured; **MEDIUM** for Pitfall 7, which reasons from the cited retry schedule
- D-13's status precedence: **LOW** — A1, the one substantive gap, flagged as an open question

**Research date:** 2026-09-04
**Valid until:** 2026-10-04 for the library and codebase findings (stable; `uv.lock` pins 3.0.0). **Immediately invalid if `uv.lock` moves to 3.1.x** — every measurement above was taken against 3.0.0 and the `raw*` fallback and chain-check behaviour would need re-measuring.
