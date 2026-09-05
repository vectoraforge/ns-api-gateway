# Phase 44: POST /webhooks/google-play/rtdn - Research

**Researched:** 2026-09-05
**Domain:** Google Play Real-time Developer Notifications over a Cloud Pub/Sub push subscription; Google OIDC push-token verification; the Play Developer API `purchases.subscriptionsv2.get` read
**Confidence:** HIGH for the in-repo seams and the Google wire formats; MEDIUM for two Pub/Sub delivery properties; LOW for nothing that blocks the plan

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Copied from `44-CONTEXT.md` § Implementation Decisions. The full text of each decision is in that
file; this list is the binding index the planner must honour. Do not plan an alternative to any of
these.

**The router and the partition**

- **D-01: No router-level gate.** `webhooks_router` declares no `dependencies=`. Each route
  declares its own verifier as a handler parameter, and declares it **first**, so it resolves
  before `get_db` takes a pooled connection. Replaces the router-level
  `Depends(verify_app_store_notification)` of 43 D-01, which parsed Apple's body for every route.
  Membership is still the set of routes on the router. — **Reversibility:** costly.
- **D-02: The wiring test pins the order.** `tests/unit/test_app_wiring.py` asserts, for every
  callback route, that its verifier is element 0 of `route.dependant.dependencies` and that
  `get_db` resolves after it. Nothing is added to `src/` for this.
- **D-03: One dict literal counts the partition.** `PROVIDER_CALLBACK_VERIFIERS` maps each exact
  path to its verifier callable; `PROVIDER_CALLBACK_PATHS` is its key set. The test asserts the
  router's routes equal the keys, each route declares its own mapped verifier, and neither
  verifier appears off the partition. The public allowlist stays exactly `/health/ready`.
- **D-04: A verified message with an undecodable payload answers 200.** The request model
  validates only the transport envelope: `message.messageId` present, `message.data` a non-empty
  string. Base64 and JSON decoding happen **after** the token check, inside the dependency. A
  decode failure logs at ERROR and answers 200 with nothing written.
- **D-05: A verified RTDN that is not a `subscriptionNotification` answers 200.**
  `testNotification`, `oneTimeProductNotification` and `voidedPurchaseNotification` write
  nothing, make no Play call, and log the type at INFO — the 43 D-22 rule.

**The Google classes and the value type**

- **D-06: `VerifiedNotification` moves to `auth/store_notifications.py`.** Both provider modules
  import it; neither imports the other.
- **D-07: `google_play.py` declares its own Protocol beside its implementation.**
  `StoreNotificationVerifier` stays Apple's. The two providers share the value type and the
  service, not the call signature.
- **D-08: Two classes on `app.state` behind one dependency.** `verify_google_play_notification`
  in `app/dependencies.py` calls, in order: a class that verifies the Pub/Sub OIDC bearer and
  raises `NotificationRejected` on any failure; then a class that calls
  `purchases.subscriptionsv2.get` and returns `VerifiedNotification`. Class names at discretion.
  — **Reversibility:** costly — Phase 45 builds on the second class.
- **D-09: The bearer check extends `JWTVerifier`.** `auth/jwt_verifier.py` gains an optional
  required-claims argument and returns the verified payload beside `VerifiedClaims`, so the
  Google instance can enforce `email == <configured push service account>` and
  `email_verified is true`. The Firebase instance's tests stay green **unchanged**. Google's
  instance: issuer `https://accounts.google.com`, JWKS
  `https://www.googleapis.com/oauth2/v3/certs`, audience the exact configured value, RS256 only.
  It runs via `run_in_threadpool` as the Firebase one does.

**The subscription key and the status**

- **D-10: `external_id` is the purchase token.** **FLAGGED DIVERGENCE** from
  `09-webhook-google-play-rtdn.md` DELETIONS. — **Reversibility:** one-way.
- **D-11: Both providers map a store status word; `status_at` is deleted.** Amends 43 D-13.
  Apple: `data.status`. Google: `subscriptionState`, seven to five. The mapping lives in each
  provider's class. `VerifiedNotification` carries the finished `status`; the service only
  writes it. The notification type is still recorded only as `event_type`.
- **D-12: The out-of-order guard runs unchanged for both providers.** Google's class puts
  `DeveloperNotification.eventTimeMillis` into `signed_at`. The
  `store_notification_superseded` log line goes from INFO to **WARNING**.
- **D-13: Apple stays as shipped.** No App Store Server API call is added to the Apple path.

**The credential, the client and the config**

- **D-14: Application Default Credentials.** `google.auth.default()` with the
  `https://www.googleapis.com/auth/androidpublisher` scope. An absent credential logs a warning
  at boot and the route answers 503.
- **D-15: `httpx` makes the one GET; `google-auth` mints the token.** `google-auth` is added to
  `pyproject.toml` as a **direct** dependency. The token refresh is synchronous and runs in the
  threadpool; the GET is async on the loop. One response model in this project's field names;
  the Play response is never persisted or logged. The call happens in the dependency, before
  `get_db`.
- **D-16: The product→tier map is applied in each provider's class.** `GooglePlayConfig.products`
  and `AppStoreConfig.products` each feed their own class. `VerifiedNotification` carries
  `tier_id`; `SubscriptionsService` drops its `products` argument. Amends the **location** of
  43 D-14, not its rule.
- **D-17: A redelivery pays one Play call.** The dependency reads no database row; the replay
  rule stays in the service under the locks.
- **D-18: `GooglePlayConfig` in `config.py`,** every field optional like `AppStoreConfig`:
  `package_name`, `push_audience`, `push_service_account_email`, and `products`. Incomplete →
  503. The Google class refuses a message whose `packageName` differs from `package_name`
  before any Play call.
- **D-19: `k8s/templates/httproute-webhooks.yaml` gains one exact-path match** for
  `/webhooks/google-play/rtdn`, `POST`. The Authorization header must reach the backend
  unchanged; the route stays outside the JWT SecurityPolicy. No rate-limit entries.

**Responses**

- **D-20: Plain status, shared body — inherited.** 401 `NotificationRejected`; 503 `Unavailable`;
  500 for `AttributionConflict`, `UnmappedStoreProduct`, a lost race, or a failed Play call;
  200 only after commit.

**Documentation deliverables**

- **D-21: Amend PLAYHOOK-01 … PLAYHOOK-03 in `.planning/REQUIREMENTS.md`** with dated entries,
  plus notes under APPLEHOOK-01 and in `STATE.md` § Decisions, plus the header counts, plus
  ROADMAP criterion 3.
- **D-22: `09-webhook-google-play-rtdn.md`, `08-webhook-app-store.md` and
  `SHARED-INVARIANTS.md` are NOT edited.**
- **D-23: Every comment this phase writes is ASD-STE100, inline where possible.**

**Carried forward — decided earlier, binding here, do NOT rebuild**

No route registry, no `Category`, no `RouteMetadata`, no `VERIFIERS`, no named-verifier table.
No foundation store-verification interface. No rate limiting and no vendor budgets. No
`audit.auth_events` row, no operation enum value, no audit result value. Outcomes are exception
classes, never an enum. The service is Phase 43's, called as-is.
`store_purchase_tokens.identity_value` is a server-minted `uuid4()` per user per store.
`store_signed_at` exists and the guard exists. No network call while a lock is held or a
transaction is open. One captured instant per request. `commit()` and `rollback()` live in
`services/`. No success log line. `IntegrityError` is caught by SQLSTATE 23505 only.

### Claude's Discretion

- The two class names and the Protocol name in `auth/google_play.py`; the dict literal's exact
  name (D-03).
- The `revoked` word for Google: `subscriptionState` has no revoked value. Map to `revoked` if
  `subscriptionsv2` exposes a revocation signal the researcher can cite; otherwise a revocation
  is recorded as `EXPIRED` with `event_type` 12 preserving the reason. Record the choice.
  → **Answered in this document. See § Open Questions OQ-1. It exposes no such signal.**
- An Apple subscription transaction with no `data.status`: refuse as a 500 leaf so Apple retries
  and it is visible, unless research shows Apple always sends it for auto-renewable
  subscriptions. → **See OQ-2. Research could not confirm. Keep the 500 leaf.**
- The `JWTVerifier` extension's exact signature (D-09), provided the Firebase tests are
  unchanged.
- The Play response model's field set beyond `productId`, `expiryTime`, `subscriptionState`,
  `latestOrderId`, `linkedPurchaseToken`, `startTime`, `obfuscatedExternalAccountId`.
- Test shape, on the 43 D-24 model.
- Log field names on the new leaves; the INFO line of D-05; the ERROR line of D-04.
- Plan wave order. The `k8s/` edit and the `pyproject.toml` dependency are independent of the
  code.

### Deferred Ideas (OUT OF SCOPE)

- **Phase 44.1 — the feature-sliced restructure.** `core/ db/ auth/ users/ grants/ webhooks/
  chats/ health/`. A pure move with no behaviour change, after Phase 44.
- **Apple live status from the App Store Server API** (`Get All Subscription Statuses`).
  Declined for now (D-13).
- **Gateway per-IP and per-URL limits on both webhook paths** — the v2.1 gateway contract.
- **Provisioning the Pub/Sub topic, the push subscription, its audience and its push service
  account** — infrastructure, not this repository.
- **A `paused` subscription status** — Google has one, our enum does not; `expired` stands in.
- `secret-manager-integration` (score 0.6) — declined again.
- `message-ordering-is-unspecified` (score 0.6) — unrelated.

Also out of scope, from § Phase Boundary: restore and the adoption of an unclaimed subscription
(45); any App Store Server API call on the Apple path; every rate-limit entry and vendor budget;
any `audit.auth_events` row; a secret URL token, an IP allowlist, mTLS.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAYHOOK-01 | The endpoint ingests Google Play RTDN via a Cloud Pub/Sub push subscription, authenticated solely by backend verification of Google's signed OIDC push token | § Standard Stack (google-auth, PyJWT); § Pattern 1 (the two-class dependency); § Pattern 2 (the OIDC claim set); F-01 … F-05; § Code Examples 1 and 2 |
| PLAYHOOK-02 | The endpoint reuses the shared store-ingestion module owned by Phase 43 rather than forking it | § Existing seams table; § Pattern 4 (what the service reads off the value type); P-01 (the `grace_period_expires_at` trap); § Don't Hand-Roll |
| PLAYHOOK-03 | The route is enumerated individually by exact path in the closed provider-callback category, as the second and last member of that partition | § Pattern 3 (the partition literal); F-06, F-07; § Code Examples 4 |
</phase_requirements>

---

## Summary

This phase is not a new subsystem. It is a second provider behind an ingestion path that already
exists and is verified. Almost all the risk is in three places: the exact spelling of Google's
enum values, the exact shape of the value type the Phase 43 service reads, and one boot-time
failure mode that the Apple path never met.

The Google side is well documented and every field name in this document comes from Google's own
reference pages, not from memory. Two things in `44-CONTEXT.md` are wrong against those pages and
must be corrected in the plan, not carried through. First, the `subscriptionState` values all
carry a `SUBSCRIPTION_STATE_` prefix; a mapping table written with the bare words in D-11 will
match nothing and send every subscription to `expired`. Second, D-04 says Pub/Sub reads a 4xx as
permanent and drops the message. It does not: Pub/Sub acknowledges only `102`, `200`, `201`, `202`
and `204`, and it resends on every other status. D-04's *decision* (answer 200) is still correct
and is in fact better justified than its stated ground, because a 4xx would be retried until
message retention expires rather than dropped.

The riskiest in-repo item is not the Google API at all. `JWTVerifier.__init__` fetches the JWKS
document at construction and **raises** if the endpoint is unreachable — measured in this session,
not assumed. The Apple verifier degrades to `None` and costs one route a 503; a second
`JWTVerifier` built the same way in `lifespan` turns a Google outage or an egress block into a pod
that will not start. The plan must build the Google verifier behind the same
`try` → warn → `None` shape that `build_app_store_verifier` already uses.

**Primary recommendation:** Write `auth/google_play.py` as two classes over a hand-written httpx
call and a `google.auth.default(scopes=[...])` credential, map `SUBSCRIPTION_STATE_*` (with the
prefix) to `core.subscription_status` inside that module, and set
`grace_period_expires_at = expiryTime` when the state is `SUBSCRIPTION_STATE_IN_GRACE_PERIOD` —
otherwise the grant written for a grace-period Google subscription repeats Phase 43's CR-02 defect
exactly.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Pub/Sub push transport envelope validation | API — `schemas/webhooks.py` | — | A Pydantic request model is the framework's own 422 path; D-04 keeps it to the envelope only |
| Google OIDC push-token verification | API — `auth/` (external-SDK seam) | — | `AGENTS.md` § Package layout: `auth/` is external-SDK seams only; `JWTVerifier` already lives there |
| `purchases.subscriptionsv2.get` read | API — `auth/google_play.py` | — | It is an external-vendor read, like `auth/firebase.py` and `auth/devicecheck.py`; Phase 45 reuses this class alone |
| Base64 + JSON decode of `message.data` | API — the `auth/google_play.py` class | — | D-04 puts it after the token check, inside the dependency, so a forged body is never parsed |
| `subscriptionState` → `core.subscription_status` | API — `auth/google_play.py` | — | D-11: the mapping lives in each provider's class, so the service writes a finished word |
| `productId` → `tier_id` | API — `auth/google_play.py` | — | D-16 relocates 43 D-14 into the provider class |
| Attribution-token → user resolution | API — `crud/purchases.py` | — | Already built; `PurchasesDB.resolve_user` takes the provider, so it is provider-neutral already |
| Replay, out-of-order, lock order, grants, commit | API — `services/subscriptions.py` | `crud/subscriptions.py` | PLAYHOOK-02 binds this phase to the Phase 43 service; it is called as-is |
| Gateway path admission | CDN / Gateway — `k8s/templates/httproute-webhooks.yaml` | — | D-19; the route stays outside the JWT `SecurityPolicy` because Envoy cannot verify a Google-signed token |

**One misassignment worth naming:** it is tempting to put the OIDC verification at the Envoy
`SecurityPolicy` tier, because Envoy already runs a JWT filter for Firebase. Do not. The existing
policy targets the app-routes and llm-routes `HTTPRoute`s only, and
`SHARED-INVARIANTS.md` § "Wire contract" states that Envoy's JWT filter is defence-in-depth only
and that no backend correctness may depend on it. PLAYHOOK-01 says "backend verification"
explicitly.

---

## Project Constraints (from CLAUDE.md / AGENTS.md)

`./CLAUDE.md` is one line: `@AGENTS.md`. Two AGENTS.md files bind, and both were read.

**From `/home/init/native-speaker/AGENTS.md` (the superrepo):**

- First version of the app, built by a startup. No users yet.
- The product is a sub-$5/month AI grammar-fix chat. **Do not over-engineer for the theft threat
  model.** Do not skip normal security measures either.
- **Keep specs short.** Programming this app must not consume many tokens.
- The app runs in Kubernetes behind Envoy Gateway, which authenticates by JWT and rate-limits by
  IP, user and URL.

**From `/home/init/native-speaker/ns-api-gateway/AGENTS.md` (this repo):**

- **Docstrings — three lines maximum.** State what the entity does. Nothing else. Do not describe
  what lives elsewhere, what the entity is not, or how the application works in general.
- **Comments — only where necessary**, to resolve a genuine ambiguity or prevent a misreading.
  Default to none. **One line each**; a comment explains the lines below it and never the design.
- **Package layout.** `services/` business logic and transaction boundaries; `crud/` database
  access; `schemas/` Pydantic bodies and domain value types; `tables/` SQLModel tables and mirror
  enums; `routers/` HTTP handlers, `Depends()` only; `auth/` **external-SDK seams only**.
- A router may call `crud/` directly. A `services/` class is earned by complexity.
- `Depends()` only binds the handler: take the session and the barrier from a dependency, never
  construct a database class in the body.
- Four exceptions: `errors.py` owns the client-visible error shape; `BoundedReason` stays in
  `auth/jwt_verifier.py`; `commit()`/`rollback()` live in `services/`; a fail-closed read may
  raise its own rejection in `crud/`.
- **Function shape.** Delete a function that is only a step. Keep one that states a rule or marks
  a boundary — a lock, a transaction, or a callable a library requires. The check: inline it, and
  if the call site then needs a comment, the name was carrying meaning.

**Planner compliance notes:**

1. `auth/google_play.py` fits the `auth/` fence — it is an external-SDK seam. The Play **response
   model** (D-15) is a domain value type and would normally belong in `schemas/`. Phase 43 set the
   precedent by keeping `VerifiedNotification` in `auth/app_store.py`, and D-06 moves it to
   `auth/store_notifications.py` rather than to `schemas/`. Keep the Play response model beside
   its only consumer in `auth/google_play.py` and follow that precedent; do not open a new
   layering question in this phase.
2. The Pub/Sub **request** envelope is a client-facing body and belongs in `schemas/webhooks.py`,
   beside `AppStoreNotificationRequest` (D-04 and § Integration Points already say so).
3. § "Function shape" bears on the mapping helpers. A `_status_from(state, expiry, evaluated_at)`
   function states a rule and is not a step, so it survives the check. A one-line
   `_instant(millis)` helper already exists in `auth/app_store.py:42-44` and is the precedent.
4. **Keep specs short** applies to the plan itself. This is a second provider on a built path.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-auth` | 2.49.1 | Mints the OAuth2 access token for the Play Developer API from Application Default Credentials | Google's own auth library. **Already installed and already imported by this repo** at `auth/firebase.py:8-9`, arriving transitively through `firebase-admin`. D-15 promotes it to a direct dependency. `[VERIFIED: .venv/lib/python3.14/site-packages/google_auth-2.49.1.dist-info; uv.lock:378-380 `name = "google-auth"` / `version = "2.49.1"` / `source = { registry = "https://pypi.org/simple" }`]` |
| `httpx` | 0.28.1 | The one async GET to `androidpublisher.googleapis.com` | Already a direct dependency (`pyproject.toml:24`) and already the client for `auth/devicecheck.py`. `[VERIFIED: pyproject.toml:24 `"httpx >=0.28"`]` |
| `PyJWT[crypto]` | 2.12.1 | RS256 verification of the Pub/Sub OIDC token through the existing `JWTVerifier` | Already a direct dependency (`pyproject.toml:18`) and already the whole of `auth/jwt_verifier.py`. D-09 extends that class rather than adding a library. `[VERIFIED: pyproject.toml:18 `"PyJWT[crypto]>=2.9.0"`]` |

**No new package is required by this phase.** `google-auth` moves from transitive to direct; that
is a one-line `pyproject.toml` edit and a `uv lock` refresh, not an install.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `google.auth.transport.requests.Request` | (in google-auth) | The transport object `credentials.refresh()` needs | Inside the threadpool call that refreshes the access token |
| `pydantic` | >=2.12 | The Pub/Sub envelope model and the Play response model | Already the project's body layer |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `httpx` + hand-written URL | `google-api-python-client` (`androidpublisher` discovery client) | Adds a large synchronous dependency with its own httplib2 transport, no async support, and a discovery-document fetch at build time. One GET does not earn it. It is also not installed. |
| `JWTVerifier` extension (D-09) | `google.oauth2.id_token.verify_oauth2_token(token, request, audience)` | One call and no `JWTVerifier` change — but it uses its own `requests`-backed transport with its own cache, so this project would then have two JWKS caches, two timeout policies and two never-raises disciplines. It also raises rather than returning a reason, which is the opposite of this project's rule. D-09 is the right call. `[VERIFIED: probed `inspect.signature(google.oauth2.id_token.verify_oauth2_token)` → `(id_token, request, audience=None, clock_skew_in_seconds=0)`]` |
| Backend verification | Envoy `SecurityPolicy` JWT provider for `accounts.google.com` | Forbidden by `SHARED-INVARIANTS.md` § "Wire contract" (Envoy is defence-in-depth only) and by PLAYHOOK-01's "backend verification". |

**Installation:**

```bash
# One line added to pyproject.toml [project].dependencies, then:
uv lock && uv sync
```

`google-auth` needs no version pin beyond what the lockfile already resolves. Match the style of
its neighbours: `"google-auth>=2.49"`.

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `google-auth` | PyPI | Long-established (2.49.1 resolved in this repo's lockfile from `https://pypi.org/simple`) | Not measured — see note | `github.com/googleapis/google-auth-library-python` | OK | Approved |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

**Why this is `OK` without a download count.** `google-auth` is not a package this research
discovered by search. It is **already installed in this repo's virtual environment and already
imported by shipped code** — `src/nativespeaker/api/auth/firebase.py:8-9` reads
`import google.auth` / `import google.auth.exceptions`, and `auth/firebase.py:50-53` calls
`google.auth.default()`. It arrives as a declared dependency of `firebase-admin`, which is itself
a direct dependency (`pyproject.toml:22`), through `google-api-core` (`uv.lock:360`). Promoting a
transitive dependency that Google's own SDK already pulls in is not a supply-chain decision; it is
a declaration of a fact. `[VERIFIED: src/nativespeaker/api/auth/firebase.py:8-9, :50-53;
uv.lock:360, :378-380]`

**No other package is added by this phase.** The audit is therefore one row.

---

## Findings

Each finding carries its provenance. `[VERIFIED: …]` means a file was opened this session or a
command was executed this session, with the value quoted verbatim.

### F-01 — Google's OIDC issuer, JWKS endpoint and algorithm

D-09's three values are correct. Google's own discovery document gives:

- issuer: `https://accounts.google.com`
- jwks_uri: `https://www.googleapis.com/oauth2/v3/certs`
- id_token_signing_alg_values_supported: `RS256`

`[CITED: https://accounts.google.com/.well-known/openid-configuration]`

### F-02 — The Pub/Sub push token's claim set

The push request carries `Authorization: Bearer {encoded_jwt}`. The decoded claim set contains
`iss` (`"https://accounts.google.com"`), `aud` (the configured audience), `azp` (the service
account's numeric id), `email` (the service account email), `email_verified`, `sub` (the same
numeric id), `iat` and `exp`. The header carries `"alg":"RS256"`. It is an OpenID Connect ID
token. `[CITED: https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions]`

**This matters for D-09 because the existing verifier already requires exactly those claims.**
`jwt_verifier.py:155` passes `options={"require": ["exp", "iat", "aud", "iss", "sub"]}`, and every
one of the five is present in Google's token. No relaxation is needed.
`[VERIFIED: src/nativespeaker/api/auth/jwt_verifier.py:149-155, verbatim:
`payload = jwt.decode(token, signing_key, algorithms=["RS256"], audience=self._audience,
issuer=self._issuer, leeway=self._leeway, options={"require": ["exp", "iat", "aud", "iss",
"sub"]})`]`

`email` and `email_verified` are **not** in the require list and are **not** returned by
`claims_from_payload`, which is exactly the gap D-09 exists to close (see F-03).

### F-03 — What `JWTVerifier` returns today, and the minimum D-09 must change

```
VerificationResult = tuple[VerifiedClaims | None, BoundedReason | None]
```

and

```
@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub`, never reconstructed from transport metadata."""
    issuer: str
    subject: str
```

`claims_from_payload(payload)` builds that pair and **discards the rest of the payload**.
`[VERIFIED: src/nativespeaker/api/auth/jwt_verifier.py:38-46, :70-75]`

So the Google instance cannot see `email` or `email_verified` through today's return type. D-09's
"returns the verified payload beside `VerifiedClaims`" is the minimum change. Two shapes satisfy
it and keep the Firebase tests byte-identical:

- Widen the tuple to a 3-tuple. **This breaks every existing caller** — `app/dependencies.py:53-54`
  unpacks two values, and `tests/unit/test_jwks_offload.py` and `unit/conftest.py`'s
  `make_test_verifier` do too. Rejected.
- Add an **optional** `payload: dict | None` field to `VerifiedClaims`, defaulted to `None`, and
  populate it only when a `required_claims` argument was given. The tuple arity is unchanged, so
  every existing caller and test is untouched, and `slots=True` still holds because a default on a
  slotted frozen dataclass is legal. **Recommended.**

The `required_claims` argument itself is best expressed as a `dict[str, object] | None` of exact
expected values, checked after `jwt.decode` returns and before `claims_from_payload`, with a
mismatch returning `(None, BoundedReason.bad_signature)` — never a raise, because
`jwt_verifier.py:163-165` makes never-raises structural and the module comment at `:1` says callers
rely on it.

**Do not add a new `BoundedReason` member for the email mismatch.** `BoundedReason` has exactly
five members today and `errors.py` imports it (the `AGENTS.md` carve-out). Reusing
`bad_signature` keeps the client answer identical for every arm, which is the anti-oracle property
APPLEHOOK-01 records as the one the brief was protecting. Put the distinguishing detail in the
`stage` log field on `NotificationRejected`, which is where the Apple path already puts it.
`[VERIFIED: src/nativespeaker/api/auth/jwt_verifier.py:22-29, :163-165; src/nativespeaker/api/auth/app_store.py:83 `raise NotificationRejected(stage=failure.status.name) from failure`]`

### F-04 — `JWTVerifier.__init__` raises when the JWKS endpoint is unreachable. This is a boot-killer.

```
        # Warm the JWKS cache, and fail fast at startup if the endpoint is unreachable.
        self._jwks_client.get_signing_keys()
```

`[VERIFIED: src/nativespeaker/api/auth/jwt_verifier.py:104-105, verbatim]`

Probed this session against an unreachable endpoint:

```
$ .venv/bin/python -c "JWTVerifier(jwks_url='https://127.0.0.1:9/nope', ...)"
RAISED AT CONSTRUCTION: jwt.exceptions.PyJWKClientConnectionError Fail to fetch data from the
url, err: "<urlopen error [Errno 111] Connection refused>"
```

`[VERIFIED: executed probe, 2026-09-05]`

The Firebase instance already carries this risk and it was accepted. A **second** instance
multiplies it: a Google outage, an egress rule, or an air-gapped test environment now stops the
pod from starting at all, where the Apple path costs one route a 503 and boots.

**This directly contradicts the shape D-14 and D-18 require** — "an absent credential logs a
warning at boot and the route answers 503, the shape of `firebase_admin_credential_absent` and
43 D-02", and "Incomplete → 503". A raised `PyJWKClientConnectionError` in `lifespan` is neither.

**Required in the plan.** Build the Google verifier the way `build_app_store_verifier` builds
Apple's — return `None` on any failure, log one warning, and let the class answer `Unavailable`:

```python
def build_google_push_verifier(play: GooglePlayConfig) -> JWTVerifier | None:
    """The Pub/Sub push-token verifier, or `None` when this deployment cannot build one."""
    if not (play.push_audience and play.push_service_account_email):
        return None
    try:
        return JWTVerifier(jwks_url=GOOGLE_JWKS_URL, audience=play.push_audience,
                           issuer=GOOGLE_ISSUER, required_claims={...})
    except PyJWTError:
        # The warm-up fetch raises on an unreachable JWKS, and one route's 503 beats a dead pod.
        return None
```

`build_app_store_verifier` is the precedent and its comment names the same concern:
`# Production needs the app id too: the library raises ValueError without it, and that would stop
boot.` `[VERIFIED: src/nativespeaker/api/app/lifespan.py:33-45]`

### F-05 — `google.auth.default()` and the Play access token

`google.auth.default` accepts scopes:

```
(scopes: 'Optional[Sequence[str]]' = None, request: "Optional[google.auth.transport.Request]" = None,
 quota_project_id: 'Optional[str]' = None, default_scopes: 'Optional[Sequence[str]]' = None)
 -> "tuple[google.auth.credentials.Credentials, Optional[str]]"
```

`[VERIFIED: executed `inspect.signature(google.auth.default)` against the installed
google-auth 2.49.1]`

The required scope for `purchases.subscriptionsv2.get` is
`https://www.googleapis.com/auth/androidpublisher`.
`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get]`

`auth/firebase.py` already calls `google.auth.default()` with no scopes and discards the result,
using it only as an availability probe:

```python
def _application_default_credential() -> credentials.ApplicationDefault | None:
    """ADC if the environment supplies it, `None` if it does not -- never a raise."""
    try:
        google.auth.default()
    except google.auth.exceptions.DefaultCredentialsError:
        return None
```

`[VERIFIED: src/nativespeaker/api/auth/firebase.py:48-55]`

The Google Play class needs the credential object itself, scoped. The same
`DefaultCredentialsError` guard applies, and it is the same "absent credential → warn → `None` →
503" shape D-14 asks for.

### F-06 — The partition literal today, and exactly what D-02/D-03 change

```python
PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}
```

`[VERIFIED: tests/unit/test_app_wiring.py:18, verbatim]`

Four cases in `TestTheProviderCallbackPartition` consume it, and **three of them hard-code
`verify_app_store_notification` by name** — `test_each_callback_route_declares_the_verifier_and_neither_identity`
and `test_no_route_outside_the_partition_declares_the_verifier`. Those two must become
map-driven under D-03, because a Google route declaring only its own verifier fails the first one
as written. `[VERIFIED: tests/unit/test_app_wiring.py, class `TestTheProviderCallbackPartition`]`

Two cases in `TestEveryRouteIsAuthenticated` also read the literal —
`test_every_route_but_the_two_exemptions_requires_a_linked_identity` and
`test_no_route_serves_without_an_identity_or_a_callback_declaration`. Both compute structurally
over `app.routes` and take `PROVIDER_CALLBACK_PATHS` into their exemption union, so both widen
correctly by the one-line literal edit alone. `[VERIFIED: tests/unit/test_app_wiring.py, class
`TestEveryRouteIsAuthenticated`]`

The router today declares the gate D-01 removes:

```python
router = APIRouter(tags=["webhooks"],
                   dependencies=[Depends(verify_app_store_notification)])
```

`[VERIFIED: src/nativespeaker/api/routers/webhooks.py:13-14, verbatim]`

### F-07 — How FastAPI orders `route.dependant.dependencies`, and what D-02 can and cannot assert

Probed this session on a minimal app with the same shape the phase will build:

```
top-level dependant.dependencies: ['verifier', 'get_service']
  verifier -> sub: []
  get_service -> sub: ['get_db']
reversed declaration order: ['get_service', 'verifier']
```

`[VERIFIED: executed probe against the installed fastapi 0.135.1, 2026-09-05]`

Three consequences the plan must build on:

1. **Element order follows the handler's parameter declaration order.** D-01's "declares it
   **first**" is therefore enforceable, and D-02's "element 0 of `route.dependant.dependencies`"
   is a real assertion. Reversing the parameters visibly reverses the list.
2. **`get_db` is NOT an element of `route.dependant.dependencies`.** It is a sub-dependency of
   `get_subscriptions_service`. D-02's second clause — "`get_db` resolves after it" — cannot be
   written as a flat index comparison. Write it as: `get_db` does not appear at index 0's subtree,
   and appears only under an element at a later index. A helper that flattens the tree in
   resolution order is the clean form.
3. FastAPI's `solve_dependencies` walks the tree in list order, sequentially and depth-first, so
   element 0 fully resolves — and can raise — before element 1's subtree opens a session. The
   ordering property D-01 wants is real, not decorative.

### F-08 — `SUBSCRIPTION_STATE_` is a prefix. D-11's Google table is written without it.

The complete `SubscriptionState` enum, verbatim:

- `SUBSCRIPTION_STATE_UNSPECIFIED`
- `SUBSCRIPTION_STATE_PENDING`
- `SUBSCRIPTION_STATE_ACTIVE`
- `SUBSCRIPTION_STATE_PAUSED`
- `SUBSCRIPTION_STATE_IN_GRACE_PERIOD`
- `SUBSCRIPTION_STATE_ON_HOLD`
- `SUBSCRIPTION_STATE_CANCELED`
- `SUBSCRIPTION_STATE_EXPIRED`
- `SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED`

`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2]`

That is **nine** values, not the seven D-11 counts. D-11 names eight of the nine (it omits nothing
substantive — it merges `UNSPECIFIED` into the catch-all and counts loosely), but every one of its
literals is missing the prefix. A `dict` keyed on `"ACTIVE"` matches nothing Google sends.

The descriptions, verbatim, which settle two of D-11's judgement calls:

- `SUBSCRIPTION_STATE_ON_HOLD`: *"Subscription is on hold (suspended)."*
- `SUBSCRIPTION_STATE_CANCELED`: *"Subscription is canceled but not expired yet."*

`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2]`

The CANCELED description confirms D-11's rule directly: canceled-but-not-expired is still an
entitled term, so `active` while a line item's `expiryTime` is after `evaluated_at` is right, and
the `else expired` arm is the safety net rather than the normal path.

### F-09 — `purchases.subscriptionsv2.get`: URL, scope, and the fields the value type needs

```
GET https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{packageName}/purchases/subscriptionsv2/tokens/{token}
```

Path parameters: `packageName` (e.g. `com.some.thing`) and `token` ("The token provided to the
user's device when the subscription was purchased"). Request body empty. Scope
`https://www.googleapis.com/auth/androidpublisher`.
`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get]`

Response fields relevant to this phase, with Google's own descriptions where they decide something:

| Field | Google's description | Use |
|-------|---------------------|-----|
| `subscriptionState` | "The current state of the subscription." | → `status` (F-08) |
| `startTime` | "Time at which the subscription was granted. **Not set for pending subscriptions** (subscription was created but awaiting payment during signup)." | → `purchased_at` |
| `latestOrderId` | — | → `transaction_id` |
| `linkedPurchaseToken` | "The purchase token of the old subscription if this subscription is one of the following: Re-signup of a canceled but non-lapsed subscription; Upgrade/downgrade from a previous subscription; Convert from prepaid to auto renewing subscription; Convert from an auto renewing subscription to prepaid; Topup a prepaid subscription." | Not written by this phase. See OQ-3. |
| `lineItems[].productId` | — | → the products map (D-16) and `product_id` |
| `lineItems[].expiryTime` | "time at which the subscription expired or will expire" | → `expires_at`, and → `grace_period_expires_at` in grace (P-01) |
| `externalAccountIdentifiers.obfuscatedExternalAccountId` | "An obfuscated version of the id that is uniquely associated with the user's account in your app. Present for the following purchases: If account linking happened as part of the subscription purchase flow. It was specified using BillingFlowParams.Builder#setobfuscatedaccountid when the purchase was made." | → `attribution_token` |
| `acknowledgementState` | — | Not used. This phase does not acknowledge. |
| `canceledStateContext` | Union of `userInitiatedCancellation`, `systemInitiatedCancellation`, `developerInitiatedCancellation`, `replacementCancellation` | Not used. See OQ-1. |
| `pausedStateContext.autoResumeTime` | — | Not used; D-11 maps PAUSED to `expired`. |

`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2]`

### F-10 — `DeveloperNotification` and the RTDN notification types

```json
{
  "version": string,
  "packageName": string,
  "eventTimeMillis": long,
  "oneTimeProductNotification": OneTimeProductNotification,
  "subscriptionNotification": SubscriptionNotification,
  "voidedPurchaseNotification": VoidedPurchaseNotification,
  "pendingRefundReviewNotification": PendingRefundReviewNotification,
  "testNotification": TestNotification
}
```

```json
SubscriptionNotification: { "version": string, "notificationType": int, "purchaseToken": string }
```

`[CITED: https://developer.android.com/google/play/billing/rtdn-reference]`

**Note a fifth body D-05 does not name:** `pendingRefundReviewNotification`. D-05 lists
`testNotification`, `oneTimeProductNotification` and `voidedPurchaseNotification`. The rule D-05
states — anything that is not a `subscriptionNotification` writes nothing and answers 200 — covers
it correctly, so no decision changes. But the plan must implement the rule as *"if
`subscriptionNotification` is absent, log the type and return"*, **never** as an explicit
three-member allow-list, or a `pendingRefundReviewNotification` falls through an `else` into a
Play call with no purchase token.

`notificationType` values, verbatim:

| # | Name | | # | Name |
|---|------|-|---|------|
| 1 | SUBSCRIPTION_RECOVERED | | 12 | SUBSCRIPTION_REVOKED |
| 2 | SUBSCRIPTION_RENEWED | | 13 | SUBSCRIPTION_EXPIRED |
| 3 | SUBSCRIPTION_CANCELED | | 17 | SUBSCRIPTION_ITEMS_CHANGED |
| 4 | SUBSCRIPTION_PURCHASED | | 18 | SUBSCRIPTION_CANCELLATION_SCHEDULED |
| 5 | SUBSCRIPTION_ON_HOLD | | 19 | SUBSCRIPTION_PRICE_CHANGE_UPDATED |
| 6 | SUBSCRIPTION_IN_GRACE_PERIOD | | 20 | SUBSCRIPTION_PENDING_PURCHASE_CANCELED |
| 7 | SUBSCRIPTION_RESTARTED | | 22 | SUBSCRIPTION_PRICE_STEP_UP_CONSENT_UPDATED |
| 8 | SUBSCRIPTION_PRICE_CHANGE_CONFIRMED (DEPRECATED) | | | |
| 9 | SUBSCRIPTION_DEFERRED | | | |
| 10 | SUBSCRIPTION_PAUSED | | | |
| 11 | SUBSCRIPTION_PAUSE_SCHEDULE_CHANGED | | | |

`[CITED: https://developer.android.com/google/play/billing/rtdn-reference]`

**The numbering is sparse — 14, 15, 16 and 21 do not exist, and 22 is newer than 20.** This is
exactly why `audit.subscription_events.event_type` is `str` and not an enum:
`# Plain text, not an enum: a store type this build does not know is recorded, never refused.`
`[VERIFIED: src/nativespeaker/api/tables/purchases.py:76-77]` Record the integer (or its name if
known) as text and never validate against a closed set.

### F-11 — Pub/Sub acknowledges only 5 statuses. Every other status is a redelivery.

> "The following HTTP status codes from a push endpoint count as acknowledgments: `102`, `200`,
> `201`, `202`, and `204`. … To send a negative acknowledgment for the message, return any other
> status code. … Pub/Sub resends the message." Messages are redelivered, not dropped.

`[CITED: https://docs.cloud.google.com/pubsub/docs/push]`

**D-04's stated ground is factually wrong.** It reads: *"Pub/Sub reads any 4xx as permanent and
drops the message; a 5xx would redeliver a payload that can never parse until retention expires."*
There is no 4xx/5xx distinction. A 4xx redelivers exactly like a 5xx.

**D-04's decision is unchanged and is now better supported.** Answering 200 to a verified message
with an undecodable payload is the *only* way to stop the redelivery loop, because a 400 would
loop for the whole retention window. Correct the ground in the plan's rationale; do not change the
behaviour.

**A second consequence for D-20.** The 401 arm is correct as a security answer, but the operator
must understand that a misconfigured `push_audience` turns every genuine RTDN into a 401 that
Pub/Sub retries until retention expires — the Google analogue of the Apple operational fact
recorded under APPLEHOOK-01. The `stage` field on `notification_rejected` is again the only thing
that tells "this deployment is misconfigured" apart from "this token is not Google's".

### F-12 — Play Developer API quota

The daily query limit is 200,000, resetting at midnight Pacific Time. Since a 2025 change the APIs
are also grouped into per-minute buckets (Subscriptions, One-time Purchases, Orders, Publishing)
with a default of 3,000 queries per minute per bucket, each bucket independent.
`[CITED: https://developers.google.com/android-publisher/quotas]`

D-17's "200,000-per-day quota is accepted" is correct. The **per-minute** bucket is new
information D-17 does not consider, and it is the tighter constraint for a redelivery storm: 3,000
Subscriptions-bucket calls per minute. For a product with no users this is not a concern, and
`AGENTS.md` says not to over-engineer. Record it and move on.

### F-13 — `google-auth` is already in the tree, imported by shipped code

```python
import google.auth
import google.auth.exceptions
```

`[VERIFIED: src/nativespeaker/api/auth/firebase.py:8-9, verbatim]`

Installed version 2.49.1, resolved from `https://pypi.org/simple`, reached through
`google-api-core` → `firebase-admin`. `[VERIFIED: uv.lock:360, :378-380]`

---

## Architecture Patterns

### System Architecture Diagram

```
   Google Play                      Cloud Pub/Sub                    Envoy Gateway
   (subscription event)  ──RTDN──▶  topic ──push──▶ POST /webhooks/google-play/rtdn
                                     │                     │
                                     │            HTTPRoute: Exact path, POST
                                     │            OUTSIDE the JWT SecurityPolicy
                                     │            Authorization passes through unchanged
                                     ▼                     ▼
                          ┌──────────────────────────────────────────────────────┐
                          │  FastAPI route  (webhooks_router, no router gate)    │
                          │                                                       │
                          │  param 0: verify_google_play_notification  ◀── D-01   │
                          │      │                                                │
                          │      ├─▶ [1] PushTokenVerifier (app.state)            │
                          │      │      JWTVerifier(RS256, accounts.google.com,   │
                          │      │        oauth2/v3/certs, aud=push_audience)     │
                          │      │      + email == push_service_account_email     │
                          │      │      + email_verified is true                  │
                          │      │      run_in_threadpool                         │
                          │      │      fail ─▶ NotificationRejected 401 ─▶ STOP  │
                          │      │                                                │
                          │      ├─▶ base64 decode message.data      ── D-04      │
                          │      │      json parse ─▶ DeveloperNotification       │
                          │      │      fail ─▶ log ERROR ─▶ 200, nothing written │
                          │      │                                                │
                          │      ├─▶ packageName != config ─▶ reject  ── D-18     │
                          │      ├─▶ no subscriptionNotification                  │
                          │      │      ─▶ log INFO ─▶ 200, no Play call ─ D-05   │
                          │      │                                                │
                          │      └─▶ [2] PlaySubscriptions (app.state)            │
                          │             google.auth ADC ─▶ access token           │
                          │               (refresh in threadpool)                 │
                          │             httpx GET androidpublisher v3             │
                          │               subscriptionsv2/tokens/{purchaseToken}  │
                          │             fail ─▶ 500 ─▶ Pub/Sub redelivers         │
                          │             map subscriptionState ─▶ status           │
                          │             map productId ─▶ tier_id   ── D-16        │
                          │             build VerifiedNotification                │
                          │                                                       │
                          │  param 1: get_subscriptions_service                   │
                          │      └─▶ get_db  ◀── opens ONLY after param 0 passed  │
                          │                                                       │
                          │  handler: await service.ingest(notification)          │
                          └───────────────────────┬───────────────────────────────┘
                                                  ▼
                          ┌──────────────────────────────────────────────────────┐
                          │  SubscriptionsService.ingest  (Phase 43, unchanged    │
                          │  except D-11/D-12/D-16)                              │
                          │   resolve_user(provider, attribution_token)  [no lock]│
                          │   read_subscription  [plain read, no lock]            │
                          │   lock_grants(owner)  ── grants asc, then usage rows  │
                          │   read_event(notification_uuid)  ─▶ replay ─▶ return  │
                          │   store_signed_at guard  ─▶ superseded ─▶ WARNING     │
                          │   attribution conflict  ─▶ 500                        │
                          │   upsert_subscription / insert_purchase /             │
                          │     append_event / write_subscription_grant           │
                          │   commit()  ─▶ 200                                    │
                          └───────────────────────┬───────────────────────────────┘
                                                  ▼
                                     PostgreSQL: core.subscriptions,
                                     core.store_purchases,
                                     audit.subscription_events,
                                     core.access_grants, core.user_monthly_usage
```

### Recommended Project Structure

```
src/nativespeaker/api/
├── auth/
│   ├── store_notifications.py   # NEW (D-06): VerifiedNotification, imported by both providers
│   ├── app_store.py             # EDITED: import the value type; data.status map; products map
│   ├── google_play.py           # NEW: the Protocol, the two classes, the Play response model
│   └── jwt_verifier.py          # EDITED (D-09): optional required_claims + payload on VerifiedClaims
├── app/
│   ├── dependencies.py          # EDITED: verify_google_play_notification; get_subscriptions_service
│   └── lifespan.py              # EDITED: build the two Google classes; guard the JWKS warm-up (F-04)
├── config.py                    # EDITED: GooglePlayConfig; AppConfig.google_play
├── routers/webhooks.py          # EDITED: no router gate (D-01); second route
├── schemas/webhooks.py          # EDITED: the Pub/Sub push envelope
└── services/subscriptions.py    # EDITED: delete status_at; drop products; raise one log level
```

### Pattern 1: The two-class dependency (D-08)

**What:** One dependency function calls two independent classes held on `app.state`, in a fixed
order, and returns the shared value type.

**When to use:** When two external systems with two failure modes sit behind one admission step,
and a later phase needs one of them alone. Phase 45 needs the Play lookup with no Pub/Sub token.

**Why two and not one:** A single class would give Phase 45 a method it must call around a
verification it does not have. The seam is the class boundary, not a flag.

**The precedent this follows:**

```python
def verify_app_store_notification(request: Request,
                                  body: AppStoreNotificationRequest) -> VerifiedNotification:
    """Turn the posted envelope into a verified notification, before the handler and before `get_db`."""
    # Never `run_in_threadpool`: with online checks off, no code path in the seam performs I/O.
    return request.app.state.app_store_notifications.verify(body.signedPayload)
```

`[VERIFIED: src/nativespeaker/api/app/dependencies.py:145-149, verbatim]`

**What differs for Google, and it is the whole reason the comment above cannot be copied:** the
Google dependency performs I/O twice — a possible JWKS fetch and a certain Play GET. It must be
`async def`. The token verification goes through `run_in_threadpool` exactly as
`get_identity` does at `dependencies.py:52-54`; the Play GET is `await`ed on the loop because
httpx is async.

### Pattern 2: Verifying the push token through the existing verifier

**What:** Reuse `JWTVerifier`'s RS256 path, its JWKS cache, its unknown-`kid` negative cache and
its never-raises rule, and add only the two Google-specific claim checks.

**Why not `google.oauth2.id_token`:** see § Alternatives Considered.

**The two extra checks, and why they are the security of this route:** `aud` alone is not enough,
because the audience is a value the deployer chooses and anyone who learns it could mint a Google
ID token for it from their own service account. Pinning `email` to the configured push service
account is what binds the token to *this* Pub/Sub subscription, and `email_verified is true` is
what stops a self-asserted email. The Pub/Sub documentation names both claims for exactly this
purpose. `[CITED: https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions]`

### Pattern 3: The partition literal (D-03)

**What:** One `dict` maps each exact path to its verifier callable; the key set is the partition.

```python
PROVIDER_CALLBACK_VERIFIERS = {
    "/webhooks/app-store": verify_app_store_notification,
    "/webhooks/google-play/rtdn": verify_google_play_notification,
}
PROVIDER_CALLBACK_PATHS = set(PROVIDER_CALLBACK_VERIFIERS)
```

**Why a map and not two sets:** with D-01 removing the router-level gate, each route carries a
*different* verifier. A flat set of paths plus a single named verifier — the shape the file has
today — cannot express that, and the two existing cases that name
`verify_app_store_notification` directly would pass vacuously for the Google route or fail it
outright.

**What the four cases become:**

1. `{route.path for route in webhooks_router.routes} == PROVIDER_CALLBACK_PATHS` — unchanged.
2. Parametrised over `PROVIDER_CALLBACK_VERIFIERS.items()`: each route declares **its own mapped
   verifier**, and neither `get_identity` nor `get_linked_identity`.
3. No route outside the partition declares **any** verifier in
   `PROVIDER_CALLBACK_VERIFIERS.values()`.
4. Disjointness from `PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS` — unchanged.

Plus the two D-02 cases (element-0 order, and `get_db` only below a later element — see F-07).

### Pattern 4: What the Phase 43 service still reads off the value type

`SubscriptionsService.ingest` reads these fields. Google's class must supply every one of them, and
D-11's "the service only writes the status" is true of the *status word* only — it is **not** true
of the dates.

| Field | Read at | Google source |
|-------|---------|---------------|
| `external_id` | `:51`, `:67`, `:98`, `:110`, `:127` | the purchase token (D-10) |
| `product_id` | `:51`, `:57`, `:60` | `lineItems[].productId` |
| `notification_uuid` | `:77`, `:88`, `:136` | **see OQ-4 — undecided** |
| `event_type` | `:54`, `:87`, `:135` | `subscriptionNotification.notificationType` |
| `attribution_token` | `:62` | `externalAccountIdentifiers.obfuscatedExternalAccountId` |
| `signed_at` | `:82-83`, `:115` | `eventTimeMillis` (D-12) |
| `provider` | `:60`, `:65`, `:67`, `:98`, `:106`, `:110`, `:122`, `:168` | `PurchaseProvider.google_play` |
| `transaction_id` | `:125` | `latestOrderId` |
| `purchased_at` | `:150-151` | `startTime` |
| `expires_at` | `:154` | `lineItems[].expiryTime` |
| `grace_period_expires_at` | `:153-154` | `lineItems[].expiryTime` **when in grace** — see P-01 |
| `revoked_at` | `:20` (inside `status_at` only) | **zero readers after D-11** — see P-02 |
| `in_billing_retry` | `:30` (inside `status_at` only) | **zero readers after D-11** — see P-02 |

`[VERIFIED: src/nativespeaker/api/services/subscriptions.py, line numbers as listed; and by
`grep -rn "revoked_at\|in_billing_retry\|grace_period_expires_at\|status_at\|\.products" src/ tests/`
executed this session]`

### Anti-Patterns to Avoid

- **A three-member allow-list for D-05.** Google ships five notification bodies, not four (F-10).
  Test for the *presence* of `subscriptionNotification`, never for the absence of three names.
- **A closed enum for `notificationType`.** The numbering is sparse (14–16 and 21 are unused) and
  Google adds values. `event_type` is deliberately `str`.
- **A `google` prefix that means five different things.** `44-CONTEXT.md` § Naming Hazard is
  right: `IdentityProvider.google` (Firebase sign-in), the Firebase Admin credential, the Pub/Sub
  push identity, the Play Developer API and `PurchaseProvider.google_play` all coexist. Name the
  two new classes for what they talk to, not for the vendor.
- **Building the second `JWTVerifier` unguarded in lifespan.** F-04. This turns a Google outage
  into a pod that will not start.
- **A second `notification_uuid` scheme that is not stable across a Pub/Sub redelivery.** OQ-4.
- **Logging the purchase token, the Play response, or the OIDC token.** `auth/app_store.py`'s
  module docstring records that the Apple seam holds no logger for exactly this reason, and D-15
  says the Play response is never persisted or logged. The purchase token is now `external_id`,
  which *is* persisted (D-10, the flagged divergence) — but it must still never reach a log line.
  `UnmappedStoreProduct.log_fields` and `AttributionConflict.log_fields` each carry a one-line
  comment saying the token is not admissible; do not widen them.
  `[VERIFIED: src/nativespeaker/api/errors.py:272-274, :288-290]`

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RS256 verification of Google's push token | A second verifier beside `JWTVerifier` | Extend `JWTVerifier` (D-09) | Two verifiers means two JWKS caches, two timeout policies, two negative caches and two never-raises disciplines to keep correct |
| Minting the Play access token | A hand-rolled JWT-bearer grant against `oauth2.googleapis.com/token` | `google.auth.default(scopes=[...])` + `credentials.refresh()` | The library handles the ADC search order, workload identity, metadata-server credentials, key rotation and refresh timing. Hand-rolling is the single most common source of "works locally, 401 in the cluster" |
| Store-subscription ingestion | Any second copy of the replay guard, the lock order or the grant write | `SubscriptionsService.ingest` as-is | PLAYHOOK-02 binds it, and Phase 43's review found four defects in that logic. A fork inherits none of the fixes |
| Base64 decoding `message.data` | A custom decoder with padding fixes | `base64.b64decode(value, validate=True)` inside a `try` | Pub/Sub emits standard base64 with padding. `validate=True` makes a forged body a clean exception, which D-04 turns into the ERROR-and-200 arm |
| Subscription-status truth | A local status derived from dates | `subscriptionState` from the live Play read | This is the whole point of the phase boundary: "The message is a trigger only; every written value comes from the Play response" |
| Deduplication | A cache, a Redis key, or a seen-set | `audit.subscription_events.notification_uuid`, which is `UNIQUE` | Already built, already durable, already under the locks |

**Key insight:** almost every "don't hand-roll" item in this phase is *"do not build a second copy
of something this repository already has"*. That is the shape of a second-provider phase, and it is
also what PLAYHOOK-02 and PLAYHOOK-03 are each protecting from a different angle.

---

## Common Pitfalls

### P-01: A grace-period Google subscription writes a grant with no end date

**What goes wrong:** The grant row for a subscription in `SUBSCRIPTION_STATE_IN_GRACE_PERIOD` is
written with `ends_at=None`, or with an already-past end.

**Why it happens:** The service picks the grant's end date like this:

```python
                # During grace the term is Apple's grace window, because the paid term has lapsed.
                ends_at=(notification.grace_period_expires_at
                         if status is SubscriptionStatus.grace_period else notification.expires_at),
```

`[VERIFIED: src/nativespeaker/api/services/subscriptions.py:152-154, verbatim]`

Apple carries a **separate** `gracePeriodExpiresDate` on the renewal payload. **Google does not.**
`SubscriptionPurchaseV2` has no grace-period field at all; during grace the line item's own
`expiryTime` *is* the end of the grace window. So a Google class that populates only `expires_at`
and leaves `grace_period_expires_at` as `None` sends `ends_at=None` into the grant write for every
grace-period subscription.

**How to avoid:** In `auth/google_play.py`, set both fields from `expiryTime` when the state is
`SUBSCRIPTION_STATE_IN_GRACE_PERIOD`:

```python
    expiry = _line_item_expiry(response)
    in_grace = response.subscriptionState == "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"
    # Google carries no separate grace field: in grace, the line item's own expiry ends the window.
    grace_period_expires_at = expiry if in_grace else None
```

**Warning signs:** This is not hypothetical. It is Phase 43's own CR-02, recorded under
APPLEHOOK-01 as *"a grace-period grant was written with an already-past term and was never
effective"*. The Google path can reproduce it from a different cause. A schema test that ingests a
grace-period Google notification and asserts the grant is effective at `evaluated_at` is the
control.

### P-02: `revoked_at` and `in_billing_retry` become dead fields, and five test files construct them

**What goes wrong:** D-11 deletes `status_at`. After that deletion, `revoked_at` and
`in_billing_retry` have **zero** readers anywhere in `src/`.

**Why it happens:** `status_at` was their only consumer. Verified by grep this session: the only
`src/` hits for both names outside `auth/app_store.py`'s own construction are
`services/subscriptions.py:20` and `:30`, both inside `status_at`.

**How to avoid:** Decide explicitly and record it. Two defensible answers:

- **Delete both fields** from `VerifiedNotification`. Cleanest, and `AGENTS.md` § Function shape's
  spirit favours it. **Cost:** five test files construct the value type by keyword and must be
  edited — `tests/unit/test_subscription_attribution.py:45-47` and `:386`,
  `tests/unit/test_app_store_notifications.py:275`/`:278`/`:287`/`:317`,
  `tests/e2e/test_app_store_webhook.py:123-125`,
  `tests/schema/test_subscription_ingestion.py:37-38`/`:54-56`/`:100-101`.
- **Keep both**, populated by Apple, `None`/`False` for Google, as a record of what the store said.
  **Cost:** two fields no code reads, which the next reader will delete anyway.

Recommend deleting them; the edit is mechanical and the plan already touches four of those five
files for D-06's import move.

**Warning signs:** a plan that says nothing about these two fields will silently ship the second
option by accident.

### P-03: A missing `sub` or the wrong `require` set silently locks out the route

**What goes wrong:** The route rejects every genuine push with `bad_signature`.

**Why it happens:** `jwt_verifier.py:155` requires `["exp", "iat", "aud", "iss", "sub"]` and
`claims_from_payload` rejects an empty `sub`. Google's push token carries all five (F-02), so
this is safe as written — but if D-09's implementation adds `email` to the **`require`** list
rather than checking it after decode, and Google ever ships a token shape without it, every push
fails with no way to tell it from a forgery.

**How to avoid:** Check `email` and `email_verified` *after* `jwt.decode` returns, as explicit
equality tests, and give each its own `stage` label on the resulting `NotificationRejected`.

### P-04: The Firebase `JWTVerifier` tests must stay green **unchanged** (D-09)

**What goes wrong:** The D-09 signature change breaks `tests/unit/test_jwks_offload.py` or
`unit/conftest.py::make_test_verifier`.

**Why it happens:** Those files construct `JWTVerifier(...)` positionally-adjacent to the keyword
set it has today, and `app/dependencies.py:53-54` unpacks the return as a 2-tuple.

**How to avoid:** F-03's recommended shape — an **optional** `required_claims=None` keyword and an
**optional, defaulted** `payload` field on `VerifiedClaims` — changes neither the constructor's
required arguments nor the tuple arity. Verify by running the two files before and after with no
edits.

### P-05: `obfuscatedExternalAccountId` only exists if the mobile app set it

**What goes wrong:** Every Google subscription ingests unattributed, and no buyer ever gets a
grant from the webhook.

**Why it happens:** Google's own wording is conditional — the field is present *"If account linking
happened as part of the subscription purchase flow"* or *"It was specified using
BillingFlowParams.Builder#setobfuscatedaccountid when the purchase was made."*
`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2]`
It is **not** minted by Google. The Android client must pass this project's server-minted
`store_purchase_tokens.identity_value` at purchase time.

**How to avoid:** This is a client-side obligation **outside this repository**, and the plan cannot
close it. Record it as an operational prerequisite in the `.env.example` block beside
`GOOGLE_PLAY_PACKAGE_NAME`, the way the Apple block already explains where each value is read.

**Warning signs:** The path degrades correctly rather than failing — an unattributed subscription
is ingested with a server-minted `uuid7()` placeholder (`services/subscriptions.py:124`) and
adopted later by restore (Phase 45). So this will not raise. It will just quietly grant nobody
anything.

### P-06: Egress to two new hosts

**What goes wrong:** The route works in development and 503s or 500s in the cluster.

**Why it happens:** The pod must reach `https://www.googleapis.com` (JWKS, and it already does for
Firebase — `config.py:54-55` names `www.googleapis.com/service_accounts/v1/jwk/…`) and
**`https://androidpublisher.googleapis.com`**, which is a host this application has never called.

**How to avoid:** Name both hosts in the plan's environment notes. F-04's guard turns the JWKS
half into a 503 rather than a dead pod; the Play half is a 500 that Pub/Sub retries.

---

## Code Examples

### 1. Building the two Google classes in `lifespan`, in the shape D-14/D-18 require

```python
# Follows build_app_store_verifier: a deployment that cannot build one gets None and one warning.
google_push_verifier = build_google_push_verifier(config.google_play)
google_credential = _play_credential()
if google_push_verifier is None or google_credential is None:
    logger.warning("google_play_configuration_absent",
                   consequence="POST /webhooks/google-play/rtdn fails closed as "
                               "verification_temporarily_unavailable until the Play package name, "
                               "push audience, push service account and Application Default "
                               "Credentials are available in this environment")
# Set unconditionally, so the route set is the same in every environment.
app.state.google_push_notifications = GooglePushTokens(verifier=google_push_verifier, ...)
app.state.play_subscriptions = PlaySubscriptions(credential=google_credential, client=play_client, ...)
```

Source: the shape at `src/nativespeaker/api/app/lifespan.py:75-83`, verbatim comment
`# Set unconditionally, so the route set is the same in every environment.`
`[VERIFIED: src/nativespeaker/api/app/lifespan.py:75-83]`

That last comment is load-bearing and must be preserved for the Google pair: it is the ground of
APPLEHOOK-01's flagged conflict, and it is why the wiring test can count the partition at import
time.

### 2. The scoped ADC credential and the one GET

```python
PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
PLAY_URL = ("https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            "{package_name}/purchases/subscriptionsv2/tokens/{purchase_token}")


def _play_credential():
    """ADC scoped for the Play Developer API, or `None` if the environment supplies none."""
    try:
        credential, _project = google.auth.default(scopes=[PLAY_SCOPE])
    except google.auth.exceptions.DefaultCredentialsError:
        return None
    return credential
```

`google.auth.default`'s signature and return type were probed this session; the scope string is
from Google's method reference. `[VERIFIED: executed probe; CITED:
https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get]`

The refresh is synchronous and can block on a network call, so it runs off the loop — the same
rule `app/dependencies.py:52-53` states for `JWTVerifier.verify`:

```python
        # `refresh` is synchronous and can block on a token fetch, so it never runs on the event loop.
        await run_in_threadpool(self._credential.refresh, google.auth.transport.requests.Request())
        response = await self._client.get(
            PLAY_URL.format(package_name=package_name, purchase_token=purchase_token),
            headers={"Authorization": f"Bearer {self._credential.token}"})
```

`google.auth.credentials.Credentials` already caches the token and only refreshes when it is near
expiry, so calling `refresh` unconditionally per request is wrong — use
`credential.before_request(...)` or test `credential.valid` first. Prefer:

```python
        if not self._credential.valid:
            await run_in_threadpool(self._credential.refresh, Request())
```

### 3. The status mapping, with the prefix (F-08)

```python
_STATES = {
    "SUBSCRIPTION_STATE_ACTIVE": SubscriptionStatus.active,
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": SubscriptionStatus.grace_period,
    # On hold is Play's billing retry: the paid term ended and Google is still charging.
    "SUBSCRIPTION_STATE_ON_HOLD": SubscriptionStatus.billing_retry,
    # Our enum carries no paused word; the auto-resume arrives as a fresh ACTIVE.
    "SUBSCRIPTION_STATE_PAUSED": SubscriptionStatus.expired,
}


def _status_for(state: str, expiry: datetime | None,
                evaluated_at: datetime) -> SubscriptionStatus:
    """The subscription's status from Play's own state word, which is the only source here."""
    if state == "SUBSCRIPTION_STATE_CANCELED":
        # Canceled but not expired is still a paid term: Google says so in the field's own text.
        return (SubscriptionStatus.active if expiry is not None and expiry > evaluated_at
                else SubscriptionStatus.expired)
    # Every unlisted state — EXPIRED, PENDING, PENDING_PURCHASE_CANCELED, UNSPECIFIED, and any
    # value Google adds later — is not entitled.
    return _STATES.get(state, SubscriptionStatus.expired)
```

Every literal above is quoted from Google's enum list (F-08). Every `SubscriptionStatus` member is
quoted from `tables/purchases.py:16-22`:

```python
class SubscriptionStatus(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_status` -- exactly five values."""
    active = "active"
    grace_period = "grace_period"
    billing_retry = "billing_retry"
    expired = "expired"
    revoked = "revoked"
```

`[VERIFIED: src/nativespeaker/api/tables/purchases.py:16-22, verbatim]`

**`revoked` is unreachable on the Google path.** See OQ-1.

### 4. The Apple side of D-11, with the library's own enum

```python
_APPLE_STATUSES = {
    Status.ACTIVE: SubscriptionStatus.active,
    Status.EXPIRED: SubscriptionStatus.expired,
    Status.BILLING_RETRY: SubscriptionStatus.billing_retry,
    Status.BILLING_GRACE_PERIOD: SubscriptionStatus.grace_period,
    Status.REVOKED: SubscriptionStatus.revoked,
}
```

The library's enum, read from the installed package this session:

```python
class Status(IntEnum, metaclass=AppStoreServerLibraryEnumMeta):
    """
    The status of an auto-renewable subscription.
    https://developer.apple.com/documentation/appstoreserverapi/status
    """
    ACTIVE = 1
    EXPIRED = 2
    BILLING_RETRY = 3
    BILLING_GRACE_PERIOD = 4
    REVOKED = 5
```

`[VERIFIED: .venv/…/appstoreserverlibrary/models/Status.py, verbatim, read this session]`

D-11's Apple table is exactly right, and the mapping is one-to-one onto the five
`SubscriptionStatus` members. `Data` carries both `status` and `rawStatus`:
`[VERIFIED: executed `dir(appstoreserverlibrary.models.Data.Data)` → includes `'rawStatus'`,
`'status'`, `'signedRenewalInfo'`, `'signedTransactionInfo'`]` Read `status` (the typed member)
for the map and fall back to the 500 leaf when it is `None` (OQ-2).

### 5. The wiring test's order assertion (D-02), given F-07

```python
def _flattened(route: APIRoute) -> list:
    """Every dependency callable in resolution order, sub-dependencies depth-first under their parent."""
    order = []
    def walk(dependencies):
        for dependency in dependencies:
            order.append(dependency.call)
            walk(dependency.dependencies)
    walk(route.dependant.dependencies)
    return order


@pytest.mark.parametrize("path,verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.items()))
def test_the_verifier_resolves_before_any_session_is_taken(path, verifier):
    """A reordered parameter list costs a pooled connection per junk request; this is what catches it."""
    route = next(r for r in _api_routes() if r.path == path)
    assert route.dependant.dependencies[0].call is verifier
    assert _flattened(route).index(verifier) < _flattened(route).index(get_db)
```

`route.dependant.dependencies` element order following parameter declaration order, and `get_db`
appearing only as a sub-dependency, were both measured this session (F-07).

---

## Runtime State Inventory

This is not a rename or refactor phase, but it does add runtime state, so the same five questions
are answered here rather than skipped.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `core.subscriptions.external_id` will hold **Google purchase tokens** for the first time (D-10). No migration is needed — the column is `str` and provider-scoped by `ix_subscriptions_provider_external_id`. `core.store_purchases.identity_value` and `.resolved_token_value` will hold Google `obfuscatedExternalAccountId` values. | None — code only. The `core.store_purchase_tokens` rows for `google_play` **already exist for every user**, minted at user creation (`crud/identities.py:105-109`). |
| Live service config | The Pub/Sub topic, the push subscription, its `oidcToken.audience` and its push service account live in Google Cloud, not in git. The `androidpublisher` grant is made in **Play Console**, not GCP IAM. | Out of scope (§ Deferred). The plan must name them as prerequisites so a deployer knows the route cannot work until they exist. |
| OS-registered state | None — verified: this repository registers no OS-level tasks, and the deployment is a Kubernetes `Deployment` behind Envoy. | None. |
| Secrets/env vars | **No new secret.** D-14 uses ADC, which is the identity the pod already runs on for Firebase. Three new **non-secret** env vars: `GOOGLE_PLAY_PACKAGE_NAME`, `GOOGLE_PLAY_PUSH_AUDIENCE`, `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL`. The products map goes in `config/config.yaml`, which is tracked. | Add the three to `.env.example`, commented out with parsing values, matching the `APP_STORE_*` block at `.env.example:83-110`. **Note `env_nested_max_split=1`** (`config.py:21`) — verify the three names split as `google_play` + remainder before shipping them. |
| Build artifacts | None — `google-auth` is already installed at the resolved version, so promoting it to direct changes `pyproject.toml` and `uv.lock` metadata only, with no new wheel. | `uv lock` to record the direct edge. |

**One item worth a second look.** `env_nested_delimiter="_"` with `env_nested_max_split=1` means
`GOOGLE_PLAY_PACKAGE_NAME` splits into field `google` and remainder `play_package_name` — **not**
into `google_play` + `package_name`. `[VERIFIED: src/nativespeaker/api/config.py:20-22, verbatim:
`model_config = SettingsConfigDict(env_nested_delimiter="_", env_nested_max_split=1,
hide_input_in_errors=True)`]` `APP_STORE_BUNDLE_ID` works today because the field is `app_store`
and the split is `app` + `store_bundle_id`… which would also not match. The `AppConfig` field is
`app_store`, and `APP_STORE_BUNDLE_ID` is documented as working in `.env.example`. **The plan must
verify the actual splitting behaviour empirically before choosing the three variable names** —
`tests/unit/test_config.py` already exercises the App Store block and is the place to prove it.
This is a real, cheap-to-check trap that would otherwise surface as "the config is silently empty
and the route 503s".

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `google-auth` | The Play access token (D-15) | ✓ | 2.49.1 | — |
| `httpx` | The Play GET (D-15) | ✓ | 0.28.1 | — |
| `PyJWT[crypto]` | The push-token check (D-09) | ✓ | 2.12.1 | — |
| `app-store-server-library` | The Apple half of D-11 | ✓ | installed; `Status` enum read this session | — |
| Python | Runtime | ✓ | 3.14 (`requires-python = ">=3.14"`) | — |
| `https://www.googleapis.com` egress | JWKS fetch | Already required by Firebase (`config.py:54-55`) | — | F-04's guard: warn + `None` + 503 |
| `https://androidpublisher.googleapis.com` egress | The Play GET | **Never called by this application before** | — | 500, and Pub/Sub redelivers |
| Application Default Credentials with the `androidpublisher` scope granted in Play Console | The Play GET | Deployment-dependent | — | Warn at boot, 503 on use (D-14) |
| A provisioned Pub/Sub topic + push subscription with an `oidcToken` audience | The whole route | Out of this repository | — | None — the route is unreachable without it |

**Missing dependencies with no fallback:**
- The Pub/Sub topic and push subscription. Explicitly deferred as infrastructure. The route ships
  and answers 503/401 correctly without them; it simply receives nothing.

**Missing dependencies with fallback:**
- ADC and the Play Console grant → 503, the D-14 shape.
- JWKS reachability at boot → **only if F-04's guard is built.** Without it there is no fallback
  and the pod does not start.

---

## Validation Architecture

`workflow.nyquist_validation` is `true` in `.planning/config.json`.
`[VERIFIED: .planning/config.json, `"nyquist_validation": true`]`

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 with pytest-asyncio >=1.3 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest -q` (unit only — `addopts = "-v --tb=short -m 'not e2e and not schema'"`) |
| Full suite command | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q && uv run ruff check src tests` |

`[VERIFIED: pyproject.toml:52-66, verbatim `addopts = "-v --tb=short -m 'not e2e and not schema'"`
and the two markers]`

The `schema` and `e2e` markers are **deselected by default**, so a plan that only runs
`pytest -q` proves nothing about the database behaviour. Phase 43 was marked met on all four
commands run in-plan; match that.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAYHOOK-01 | A push with an invalid OIDC token is refused 401 with nothing written | unit | `uv run pytest tests/unit/test_google_play_notifications.py -q` | ❌ Wave 0 |
| PLAYHOOK-01 | `email != push_service_account_email` refuses; `email_verified is false` refuses | unit | same file | ❌ Wave 0 |
| PLAYHOOK-01 | Every refusal arm answers a byte-identical body (the anti-oracle property) | e2e | `uv run pytest tests/e2e/test_google_play_webhook.py -m e2e -q` | ❌ Wave 0 |
| PLAYHOOK-01 | A verified token with an undecodable `message.data` answers 200 and writes nothing (D-04) | e2e | same file | ❌ Wave 0 |
| PLAYHOOK-01 | A non-`subscriptionNotification` body answers 200 with no Play call (D-05) | unit | `tests/unit/test_google_play_notifications.py` | ❌ Wave 0 |
| PLAYHOOK-01 | `packageName` mismatch refuses before any Play call (D-18) | unit | same file | ❌ Wave 0 |
| PLAYHOOK-01 | An absent config/credential answers 503 (D-14/D-18) | e2e | `tests/e2e/test_google_play_webhook.py` | ❌ Wave 0 |
| PLAYHOOK-01 | The JWKS warm-up failure yields `None`, not a raised lifespan (F-04) | unit | `tests/unit/test_google_play_notifications.py` | ❌ Wave 0 |
| PLAYHOOK-02 | The Google path reaches `SubscriptionsService.ingest`, and a grace-period Google subscription writes an **effective** grant (P-01) | schema | `uv run pytest tests/schema/test_subscription_ingestion.py -m schema -q` | ✅ extend |
| PLAYHOOK-02 | The out-of-order guard refuses an older `eventTimeMillis` for Google (D-12) | schema | same file | ✅ extend |
| PLAYHOOK-02 | A redelivery under the same `notification_uuid` writes nothing (D-17, OQ-4) | schema | same file | ✅ extend |
| PLAYHOOK-02 | Nine `subscriptionState` values map to the five `SubscriptionStatus` members (F-08) | unit | `tests/unit/test_google_play_notifications.py`, parametrised over all nine | ❌ Wave 0 |
| PLAYHOOK-02 | Apple's five `Status` values map one-to-one (D-11) | unit | `tests/unit/test_app_store_notifications.py` | ✅ extend |
| PLAYHOOK-03 | The router's route set equals `PROVIDER_CALLBACK_PATHS`, now two members | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ edit |
| PLAYHOOK-03 | Each callback route declares **its own** mapped verifier, and neither identity accessor | unit | same file | ✅ edit (must become map-driven, F-06) |
| PLAYHOOK-03 | Neither verifier appears off the partition | unit | same file | ✅ edit |
| PLAYHOOK-03 | `PUBLIC_PATHS == {"/health/ready"}` still holds | unit | same file | ✅ unchanged |
| PLAYHOOK-03 | The verifier is element 0 and `get_db` resolves after it (D-02) | unit | same file | ❌ Wave 0 (new cases; see F-07 for the shape) |
| D-09 | The Firebase `JWTVerifier` tests pass **unchanged** | unit | `uv run pytest tests/unit/test_jwks_offload.py -q` | ✅ must not be edited |
| D-16 | `google_play.products` values are a subset of the three tier ids | unit | `tests/unit/test_config.py` | ✅ extend (`:257-258` is the precedent) |

### Sampling Rate

- **Per task commit:** `uv run pytest -q`
- **Per wave merge:** `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q`
- **Phase gate:** all four commands (including `ruff check src tests`) green, run in-plan, before
  `/gsd:verify-work`. Phase 43's requirement text records that they must be run rather than copied.

### Wave 0 Gaps

- [ ] `tests/unit/test_google_play_notifications.py` — the RS256-against-a-fake-JWKS harness plus
      `httpx.MockTransport` for Play. Extend `tests/unit/test_jwks_offload.py`'s
      `CountedJwksTransport` / `jwks_body()` / `install_counted_transport` rather than writing a
      second one. `[VERIFIED: tests/unit/test_jwks_offload.py:23-60]`
- [ ] `tests/e2e/test_google_play_webhook.py` — modelled on `tests/e2e/test_app_store_webhook.py`.
- [ ] Two fixtures in `tests/e2e/conftest.py` beside `scripted_app_store_notifications` and
      `unconfigured_app_store_notifications` (`:267-307`), scripting the two Google classes behind
      the Protocol.
- [ ] New cases in `tests/unit/test_app_wiring.py` for D-02's ordering (F-07's `_flattened` helper).
- [ ] No framework install needed.

---

## Security Domain

`security_enforcement` is not present in `.planning/config.json`, so it is treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | The route's sole credential is Google's OIDC push token, verified backend-side through `JWTVerifier` (RS256, pinned issuer, pinned audience, pinned `email`, `email_verified is true`). No `Authorization` bearer of this project's own is read. |
| V3 Session Management | no | The route mints and reads no session. `SHARED-INVARIANTS.md` § "Global deletions" forbids backend session minting and this route does none. |
| V4 Access Control | yes | The route is outside the auth dependency by design and inside the enumerated provider-callback partition. `tests/unit/test_app_wiring.py` is the control that a wildcard or an accidental exemption cannot widen it silently. |
| V5 Input Validation | yes | `pydantic` on the Pub/Sub envelope only (D-04); `base64.b64decode(..., validate=True)` and `json.loads` inside a `try` **after** the token check; `packageName` equality against config before any Play call (D-18); `productId` against the configured map (D-16). |
| V6 Cryptography | yes | Never hand-rolled. RS256 via PyJWT with `algorithms=["RS256"]` pinned, which is what makes `alg: none` and HS256-over-the-public-key fail before any check runs (`jwt_verifier.py:148`). |
| V7 Error handling & logging | yes | One class per refusal, a byte-identical body per status, the distinguishing detail in the `stage` log field only. No token, email or payload value in any log line. |
| V9 Communications | yes | Both Google calls are HTTPS to Google-owned hosts. The JWKS fetch has an explicit `timeout=` because PyJWT defaults to 30 seconds, which would pin a worker (`jwt_verifier.py:90-94`). The Play GET must carry an explicit httpx timeout for the same reason — `DEVICECHECK_HTTP_TIMEOUT_SECONDS` is the precedent. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Forged push with a self-minted Google ID token for a guessed audience | Spoofing | Pin `email` to the configured push service account **and** `email_verified is true`, not `aud` alone (Pattern 2) |
| `alg` confusion / `alg: none` | Spoofing | `algorithms=["RS256"]` pinned in `jwt.decode` |
| Replay of a captured genuine push | Tampering | `exp` is required, and `audit.subscription_events.notification_uuid` is `UNIQUE` with the replay read before any write |
| Out-of-order delivery downgrading a paying buyer's grant | Tampering | The `store_signed_at` guard fed by `eventTimeMillis` (D-12). This is Phase 43's CR-01, already fixed and inherited |
| Attribution takeover — a changed owner on a recorded purchase | Elevation of privilege | `AttributionConflict` refuses and never repairs (`services/subscriptions.py:102-106`) |
| Unbounded unauthenticated request cost | Denial of service | **Accepted and flagged**, inheriting APPLEHOOK-01's uncounted residual. Note this route is *worse* than Apple's: a forged Google push costs one JWKS-cached RS256 verification (cheap), but a **genuine-looking** one that passes the token check costs one outbound Play GET. The refusal path is still local and pre-`get_db`. |
| Token/PII leakage into logs | Information disclosure | The Apple seam holds no logger by construction; the Google seam must follow. `log_fields()` on both 500 leaves already excludes the token |
| A `postinstall`-style supply-chain vector | Tampering | Not applicable — no new package, and `google-auth` is already resolved in `uv.lock` from PyPI |

**One security note the plan must not lose.** `SHARED-INVARIANTS.md` § "Locks and transactions"
requires no network call under a lock or inside a transaction. Both Google calls run in the
dependency, before `get_db`, which makes it structural rather than reviewed — D-15 says so and
F-07 proves FastAPI resolves in that order. This also means the route's expensive work happens
*before* a database connection is taken, which is the same property that makes the Apple route's
unbounded-cost residual a CPU-burn vector rather than a pool-exhaustion vector.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `purchases.subscriptions.get` (v1) | `purchases.subscriptionsv2.get` | v2 is current; v1 is documented as deprecated | Use v2. The response shape is different — line items rather than flat fields — and every field name in this document is v2's. |
| Bare `subscriptionState` words in a mapping | `SUBSCRIPTION_STATE_*` prefixed values | Always — v2 shipped this way | F-08. `44-CONTEXT.md` D-11's table is written without the prefix and must be corrected in the plan. |
| Daily quota only | Daily 200,000 **plus** per-minute per-bucket (default 3,000/min) | 2025 | F-12. Not a concern at this product's scale; recorded so it is not rediscovered. |
| A shared `google-auth` arriving transitively | A declared direct dependency | This phase (D-15) | No install; a `pyproject.toml` line and a `uv lock`. |

**Deprecated/outdated:**

- `purchases.subscriptions.get` (v1): superseded by `subscriptionsv2`. Do not use.
- `SUBSCRIPTION_PRICE_CHANGE_CONFIRMED` (notificationType 8): marked DEPRECATED in Google's own
  table. It still arrives; `event_type` is `str`, so it is recorded and ignored like any other
  non-state-changing type. `[CITED: https://developer.android.com/google/play/billing/rtdn-reference]`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A Pub/Sub redelivery carries the **same** `messageId`. Google's reference says only *"assigned by the server when the message is published. Guaranteed to be unique within the topic"* and does **not** state redelivery stability. Inferred from "assigned at publish", not stated. `[ASSUMED]` | OQ-4, § Pattern 4 | If `messageId` changes per delivery and it is used as `notification_uuid`, the replay guard misses. A second `audit.subscription_events` row is written (no `UNIQUE` violation, because the key differs), the same state is re-upserted, and a duplicate grant write runs. Not a data-corruption bug, but a duplicated audit trail and a wasted lock cycle per redelivery. |
| A2 | `credential.valid` / `credential.refresh()` is the correct google-auth pattern for a cached access token, and `before_request` is its higher-level form. Based on the library's general contract, not verified against 2.49.1's source this session. `[ASSUMED]` | § Code Examples 2 | An unconditional `refresh()` per request adds one blocking token round trip to every notification. Correctness is unaffected; latency and quota are. |
| A3 | A 410 `purchaseTokenNoLongerValid` from `subscriptionsv2.get` means the token is permanently dead (a deleted Google account, for example), not a transient failure. Sourced from community issue trackers, not from Google's own error reference. `[ASSUMED]` | OQ-5 | If a 410 is treated as a 500, Pub/Sub redelivers a call that can never succeed until retention expires — the exact loop D-04 exists to avoid, on a different arm. |
| A4 | Apple always sends `data.status` for auto-renewable subscription notifications. **Could not be verified** — the Apple documentation URL returned 404 this session. `[ASSUMED]` | OQ-2 | If `status` is absent for some notification type, the 500 leaf fires and Apple retries five times over six days, then stops. Visible, which is what the discretion note wanted, but it is a live Apple path this phase would newly break. |
| A5 | `GOOGLE_PLAY_*` environment variable names split correctly under `env_nested_max_split=1`. The setting was read verbatim; the resulting split for a two-word field name was **not** executed this session. `[ASSUMED]` | § Runtime State Inventory | The three config values silently stay at their defaults, `GooglePlayConfig` reads incomplete, and the route answers 503 in every environment with no error anywhere. Cheap to falsify in `tests/unit/test_config.py`. |
| A6 | `SUBSCRIPTION_STATE_PAUSED` auto-resume arrives as a fresh `SUBSCRIPTION_RECOVERED` (type 1) / `ACTIVE` state, so mapping PAUSED to `expired` is recoverable. Google's type-1 description says *"recovered from account hold **or resumed from pause**"*, which supports it, but the never-silently-reactivate rule means the user must tap Restore regardless. `[ASSUMED]` on the user-experience half | D-11, § Deferred | A paused user is treated as lapsed. This is D-11's accepted cost and is already recorded as a deferred idea; the risk is only that it is worse in practice than expected. |

---

## Open Questions

### OQ-1: The `revoked` word for Google — **answered: there is no citable signal**

- **What we know:** `SubscriptionState` has nine values and none of them is a revocation
  (F-08). `SubscriptionPurchaseV2` has no revocation or refund field; the reference lists a
  `revoke` *method* on the resource but no status field. `canceledStateContext` distinguishes
  user- / system- / developer-initiated cancellation and replacement, but a **revoked** subscription
  reports `SUBSCRIPTION_STATE_EXPIRED`, not `CANCELED`.
  `[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2]`
- **What's unclear:** nothing material. The discretion note's condition — *"Map to `revoked` if
  `subscriptionsv2` exposes a revocation signal the researcher can cite"* — is **not met**.
- **Recommendation:** take the fallback the note already specifies. A revocation is recorded as
  `expired` with `event_type` `12` / `SUBSCRIPTION_REVOKED` preserving the reason. **Record the
  consequence:** `SubscriptionStatus.revoked` becomes an Apple-only value. That is a real
  asymmetry between the two providers and belongs in the D-21 requirement amendment, not only in a
  code comment.

### OQ-2: Apple's `data.status` optionality — **could not be verified**

- **What we know:** `Data` carries both `status` and `rawStatus`, and the library types `status`
  as optional. `[VERIFIED: executed `dir()` on the installed `appstoreserverlibrary.models.Data`]`
  Phase 43 already handles a `data` that is `None` entirely (`app_store.py:86-88`).
- **What's unclear:** Apple's documentation page for the `data` object returned **404** this
  session, so the "always present for auto-renewable subscriptions" claim could not be confirmed
  or refuted.
- **Recommendation:** take the discretion note's default. Refuse a subscription transaction with
  no `data.status` as a 500 leaf so Apple retries and it is visible. Do **not** silently fall back
  to a date-derived status — that would resurrect `status_at`, which D-11 deletes, and would hide
  the case. Add one named unit case so the arm is not vacuous.

### OQ-3: `linkedPurchaseToken` on an upgrade or re-signup

- **What we know:** Google returns the **old** subscription's purchase token when this
  subscription is a re-signup, an upgrade/downgrade, a prepaid conversion or a top-up.
  `[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2]`
  D-10 says a new token on upgrade or re-signup "expire-then-insert already handles (43 D-19)".
- **What's unclear:** whether the old subscription row is left `active` when the new one lands. The
  service supersedes **every** grant the buyer holds before inserting the new one
  (`services/subscriptions.py:74-75`, `:142-155`), so the *grant* is correct. But
  `core.subscriptions` will hold two rows for the same buyer, the old one still reading its last
  known status, until Google sends its own expiry notification for the old token.
- **Recommendation:** do not act on `linkedPurchaseToken` in this phase. Include it in the Play
  response model (the discretion note already lists it) so the value is available, and record the
  stale-row consequence in the D-21 amendment. Acting on it would mean a second subscription write
  outside the notification's own lifecycle key, which is a bigger change than this phase's scope.
  Google will send `SUBSCRIPTION_EXPIRED` for the old token on its own schedule.

### OQ-4: What is `notification_uuid` for Google? — **the one genuine design gap**

- **What we know:** `VerifiedNotification.notification_uuid` is `str` and **not** optional, and
  `audit.subscription_events.notification_uuid` is `UNIQUE`.
  `[VERIFIED: src/nativespeaker/api/auth/app_store.py:20; src/nativespeaker/api/tables/purchases.py:78,
  verbatim `notification_uuid: str = Field(unique=True)`]` The service's replay read at
  `services/subscriptions.py:77` is the only thing that stops a redelivery re-writing.
- **What's unclear:** `44-CONTEXT.md` never says where Google's value comes from. Apple supplies
  `notificationUUID` in the signed envelope. **Google supplies no such field** — F-10's
  `DeveloperNotification` has `version`, `packageName`, `eventTimeMillis` and the notification
  bodies, and none of them is a delivery id. D-04 requires `message.messageId` to be present in the
  envelope, which strongly suggests it is the intended source, but D-04 gives the requirement as a
  validation rule, not as an assignment.
- **Two candidates, and they behave differently:**
  1. **`message.messageId`.** Simple, and it is a real unique id within the topic. It depends on
     A1 (redelivery stability), which Google's reference does not state.
  2. **A payload-derived composite**, e.g.
     `f"google_play:{purchaseToken}:{eventTimeMillis}:{notificationType}"`. It is deterministic
     from the RTDN itself, so it dedupes a Pub/Sub redelivery **and** a Play republish of the same
     event, and it does not depend on A1 at all. It is longer, and it is this project's
     construction rather than the store's.
- **Recommendation:** **use the composite.** The requirement the column serves is "the store's own
  key is already recorded, so this delivery writes nothing"
  (`services/subscriptions.py:77-78`, verbatim comment), and a payload-derived key satisfies that
  under strictly weaker assumptions than `messageId` does. Prefix it with the provider so an Apple
  UUID and a Google composite can never collide in the shared `UNIQUE` index. Whichever the
  planner picks, **this must be a named decision in the plan with a schema test that ingests the
  same RTDN twice and asserts exactly one `audit.subscription_events` row** — the property is
  otherwise untested and its failure is silent.

### OQ-5: The failure taxonomy of the Play GET

- **What we know:** D-20 says a failed Play call answers 500 so Pub/Sub redelivers. Community
  sources report a `410 Gone` with `purchaseTokenNoLongerValid` for a token whose Google account
  was deleted (A3).
- **What's unclear:** Google publishes no error-code reference for this method that this research
  could reach, so the full set is not enumerable.
- **Recommendation:** keep D-20's blanket 500 for this phase — it is the fail-closed answer and
  `AGENTS.md` says not to over-engineer. **But add one arm for 404 and 410**: a token Google says
  is gone can never resolve, so a 500 there is an infinite redelivery until retention expires
  (F-11). Treat 404/410 as the D-04 arm — log at ERROR, answer 200, write nothing. That is one
  `if` and it closes a loop that would otherwise be invisible until an operator reads the Pub/Sub
  backlog metric.

---

## Sources

### Primary (HIGH confidence)

- Files opened with `Read` or `cat` this session, quoted verbatim above:
  `src/nativespeaker/api/auth/app_store.py`, `auth/jwt_verifier.py`, `auth/firebase.py`,
  `app/dependencies.py`, `app/lifespan.py`, `routers/webhooks.py`, `routers/__init__.py`,
  `services/subscriptions.py`, `crud/subscriptions.py`, `crud/purchases.py`, `crud/identities.py`,
  `schemas/webhooks.py`, `tables/purchases.py`, `config.py`, `errors.py` (the five reused classes),
  `tests/unit/test_app_wiring.py`, `tests/unit/test_jwks_offload.py`, `tests/e2e/conftest.py`,
  `pyproject.toml`, `config/config.yaml`, `.env.example`, `k8s/templates/httproute-webhooks.yaml`,
  `k8s/templates/security-policy.yaml`, `.planning/config.json`, `.planning/REQUIREMENTS.md`
  (§ APPLEHOOK, § PLAYHOOK), `.planning/STATE.md` (§ Decisions), both `AGENTS.md` files,
  `.venv/…/appstoreserverlibrary/models/Status.py`, `uv.lock`.
- Commands executed this session: the `JWTVerifier` unreachable-JWKS probe (F-04); the FastAPI
  `route.dependant.dependencies` ordering probe (F-07); `inspect.signature(google.auth.default)`
  and `inspect.signature(google.oauth2.id_token.verify_oauth2_token)` (F-05); the
  `revoked_at`/`in_billing_retry`/`grace_period_expires_at`/`status_at`/`.products` grep (P-02);
  `dir()` on `appstoreserverlibrary.models.Data` (§ Code Examples 4).

### Secondary (MEDIUM confidence — official vendor documentation)

- https://accounts.google.com/.well-known/openid-configuration — issuer, `jwks_uri`, RS256 (F-01)
- https://developer.android.com/google/play/billing/rtdn-reference — `DeveloperNotification`,
  `SubscriptionNotification`, the notificationType table, the Pub/Sub envelope (F-10)
- https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2 —
  the `SubscriptionState` enum, `ExternalAccountIdentifiers`, `SubscriptionPurchaseLineItem`,
  `linkedPurchaseToken`, `startTime`, `canceledStateContext`, `pausedStateContext` (F-08, F-09)
- https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get —
  the request URL, path parameters, OAuth scope (F-09)
- https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions — the OIDC token, its
  claims, RS256, the Authorization header form (F-02)
- https://docs.cloud.google.com/pubsub/docs/push — the five acknowledging status codes and the
  redelivery rule (F-11)
- https://docs.cloud.google.com/pubsub/docs/reference/rest/v1/PubsubMessage — `messageId` and
  `data` descriptions (A1)
- https://developers.google.com/android-publisher/quotas — 200,000/day and the per-minute buckets
  (F-12)

### Tertiary (LOW confidence — community sources, marked for validation)

- https://github.com/voltrue2/in-app-purchase/issues/153 — the 410 / `purchaseTokenNoLongerValid`
  behaviour (A3, OQ-5). Not from Google. Treat OQ-5's recommendation as a cheap safety arm, not as
  a documented contract.
- https://developer.apple.com/documentation/appstoreserverapi/data — **returned 404 this session.**
  Recorded as *no observation*, not as evidence either way (A4, OQ-2).

---

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — no new package; every version read from the installed environment and
  the lockfile.
- Architecture: **HIGH** — every seam read from source this session, and the two behavioural
  claims that could have been assumed (dependency ordering, JWKS warm-up failure) were executed
  instead.
- Google wire formats: **MEDIUM-HIGH** — all from Google's own reference pages, cited by URL. The
  `SUBSCRIPTION_STATE_` prefix correction and the Pub/Sub acknowledgement correction are the two
  findings most likely to change the plan.
- Pitfalls: **HIGH** for P-01 and P-02 (both derived from code read this session, and P-01
  reproduces a defect Phase 43 already recorded); **MEDIUM** for P-03 through P-06.
- Open questions: OQ-4 is a genuine gap in the locked decisions and needs a named plan decision.
  OQ-1 and OQ-2 are discretion items this document resolves. OQ-3 and OQ-5 are advisory.

**Research date:** 2026-09-05
**Valid until:** 2026-10-05 — the Play Developer API and the Pub/Sub push contract are stable.
Re-check the quota page sooner if traffic ever approaches the per-minute bucket.
