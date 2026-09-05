# Phase 44: POST /webhooks/google-play/rtdn - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-05 (started 2026-09-04)
**Phase:** 44-post-webhooks-google-play-rtdn
**Areas discussed:** The router and its gate; The Google class and the value type; The subscription key and the status; The Play client, its credential and config

---

## The router and its gate

| Option | Description | Selected |
|--------|-------------|----------|
| Drop the router-level gate | Each route declares its own verifier as a handler parameter; one router, one literal | ✓ |
| A second router | Two APIRouters, each with its own gate; the literal becomes a union | |
| Keep the gate, add a prefix router | Apple under a sub-router; same as two routers with nesting | |

| Option | Description | Selected |
|--------|-------------|----------|
| Assert the position in the wiring test | Verifier is element 0 of `route.dependant.dependencies` | ✓ |
| Trust parameter order, no test | Convention only | |
| Accept the session cost | Let `get_db` run either way | |

**Notes:** the user asked "ELI5" first, then "add a test where — to the tests or to the code?". Answer: `tests/unit/test_app_wiring.py`; nothing in `src/`.

| Option | Description | Selected |
|--------|-------------|----------|
| One dict literal | `PROVIDER_CALLBACK_VERIFIERS` path → callable; paths are its keys | ✓ (Claude's discretion) |
| Keep the set, accept either verifier | A route wired to the wrong verifier still passes | |
| Two literals, two test classes | The partition counted in two places | |

**User's choice:** "I don't care." Recorded as discretion; the dict literal was chosen.

| Option | Description | Selected |
|--------|-------------|----------|
| 200 and log it | Transport-envelope-only model; decode after the token check; ERROR log | ✓ |
| 422 from a strict model | A schema change on Google's side silently drops live messages | |
| 5xx so Pub/Sub retries | A message that redelivers for days and never succeeds | |

---

## The Google class and the value type

| Option | Description | Selected |
|--------|-------------|----------|
| Move it to its own module | `auth/store_notifications.py` | ✓ (for Phase 44) |
| Leave it in app_store.py | Google files import from Apple's module | |

**User's choice:** "Move all webhook-related code to `webhooks/`. Actually, let's change the entire project directory structure…" — a feature-sliced layout (`core/ db/ auth/ users/ … tests/`). Adapted with real names and shown; recorded as **Phase 44.1**, after 44, a pure move. The adapted layout:

```
src/nativespeaker/api/
├── main.py
├── core/      config.py · exceptions.py (errors + error_handlers) · logs.py · resilience.py · lifespan.py
├── db/        session.py (get_db, session_factory) · base.py (tables/__init__)
├── auth/      router · schemas · models (tables/auth + identities) · crud (identities + challenges) · service (auth + sync) · dependencies · firebase · devicecheck · jwt_verifier · adapters
├── users/     router · models · service
├── grants/    models (tables/grants) · crud (crud/grants) · service (quota)
├── webhooks/  router · schemas · models (tables/purchases) · crud (subscriptions + purchases) · service (subscriptions) · dependencies · notifications (the value type) · app_store · google_play
├── chats/     router · schemas (api + llm) · models · crud · service (chats + llm)
└── health/    router (health + root + examples)
tests/ unit/{auth,users,grants,webhooks,chats,app}/ · e2e/ · schema/
```

Notes given: `repository.py` is `crud.py` here (the codebase's term); `grants/` is its own slice because three slices read it; the move touches 48 source files and every test import.

| Option | Description | Selected |
|--------|-------------|----------|
| Its own phase, after 44 | Phase 44 ships into the current layout | ✓ ("It's own phase 44.1") |
| Its own phase, before 44 | Phase 44 waits on the move | |
| Fold it into Phase 44 | A 48-file rename beside new logic | |

| Option | Description | Selected |
|--------|-------------|----------|
| Its own Protocol, beside its implementation | Shared = value type + service, not the signature | ✓ |
| Widen the shared Protocol | One async Protocol over a union argument | |
| No Protocol for Google | Concrete class only | |

| Option | Description | Selected |
|--------|-------------|----------|
| Two classes | Bearer check; Play lookup. Phase 45 reuses the second alone | ✓ |
| One class | Both jobs, mirroring AppStoreNotifications | |

**Notes:** asked four times. "I don't get what both do" → explained the token check vs the Play lookup. "Why isn't it a dependency like with AppStore?" → it is; the dependency is one, the classes behind it are the question. "What phase 45?" → quoted the roadmap entry. Then, after the answer: "Why doesn't Apple restore have two classes?" → Apple's message proves itself; Google's proves only its sender.

| Option | Description | Selected |
|--------|-------------|----------|
| Extend JWTVerifier | Optional required claims; return the payload; Firebase tests unchanged | ✓ |
| A second verifier class | JWKS caching and the negative cache written twice | |

---

## The subscription key and the status

| Option | Description | Selected |
|--------|-------------|----------|
| The purchase token | Stable across renewals; persists a raw token against the DELETIONS line | ✓ |
| The base order id | `latestOrderId` without `..N`; can never re-query Google | |
| A hash of the purchase token | Opaque; unreadable when debugging | |

**Notes:** "What do people usually use?" → the purchase token, by a wide margin; `subscriptionsv2.get` accepts nothing else.

| Option | Description | Selected |
|--------|-------------|----------|
| Store the token; not a divergence | Read the clause's qualifier as excluding the key | |
| Store the token; record a divergence | Flagged under PLAYHOOK-01 | ✓ |
| Do not store the token | Base order id | |

| Option | Description | Selected |
|--------|-------------|----------|
| Map subscriptionState | Seven current-state values to five | ✓ |
| Derive from the dates, as Apple does | Fill expiry/grace and reuse `status_at` | |
| Show me the seven-to-five mapping first | | |

**Notes:** the user recalled that Phase 43 had offered a status map for Apple and chose dates. Confirmed from `43-DISCUSSION-LOG.md`: the alternative was a ~20-entry notification-type table. Then: "Are there two states Google has that cannot be derived from dates — doesn't Apple have them?" → corrected: on-hold is Apple's billing retry after grace (a flag, not a date); paused has no Apple counterpart and no enum word.

| Option | Description | Selected |
|--------|-------------|----------|
| Apple fetches live status too (App Store Server API) | `Get All Subscription Statuses`; a new API key; rework of 43 | |
| Keep Apple as shipped | | ✓ ("keep it as is") |

**Notes:** the user asked "Is it normal for Google to call their API on every event? Is it feasible for Apple?" — yes and yes — and rebuked the decision box that followed: "That's not what I asked." Then "Why can't Google avoid API calling?" → the message carries no state.

| Option | Description | Selected |
|--------|-------------|----------|
| Apple maps `data.status` from the signed envelope | 1:1 with `core.subscription_status`; `status_at` deleted | ✓ ("change Apple from dates to mapping too") |

**Notes:** verified in the installed library that `Data.status` exists with exactly the five values.

| Option | Description | Selected |
|--------|-------------|----------|
| A — refuse for both; existing guard; `eventTimeMillis` as `signed_at`; log → WARNING | | ✓ ("Option A approved") |
| B — two timestamps (`signed_at` = fetch instant, `event_at` = store's creation time) | | |
| C — a `state_fetched_live` flag on the value type | | |

**Notes:** a long thread. The user first asked what out-of-order has to do with signing time, then what `store_signed_at` is and where it came from (answered: `260904-u7t`, CR-01, commits `29082dd` and `46296d8`). The user proposed: use the field for Google, warn on a straggler, skip the field update — then "the same rule for Apple". Pushed back: applying a stale Apple payload is CR-01 again. The user clarified: same rule except the writes; asked whether each provider could just call or not call `ingest()` — no, the compared row is read inside the transaction under the locks. Asked for better options than the flag; A was recommended and approved. Corrected along the way: Google **does** carry a creation time (`eventTimeMillis`).

| Option | Description | Selected |
|--------|-------------|----------|
| 200, write nothing, log at INFO | Non-subscription RTDNs; no Play call | ✓ |
| Handle voidedPurchaseNotification too | The revoked state arrives separately anyway | |

---

## The Play client, its credential and config

| Option | Description | Selected |
|--------|-------------|----------|
| Application Default Credentials | The identity Firebase Admin already uses; no key file | ✓ |
| A dedicated service-account key file | A real secret in a file | |

| Option | Description | Selected |
|--------|-------------|----------|
| httpx with a google-auth token | google-auth becomes direct; one async GET | ✓ |
| google-api-python-client | Discovery client, sync, full surface for one method | |

| Option | Description | Selected |
|--------|-------------|----------|
| In each provider's class | Class resolves `tier_id`; the value type carries it; the service drops `products` | ✓ |
| The service takes a map per provider | `{provider: products}` in the service | |

| Option | Description | Selected |
|--------|-------------|----------|
| No — accept the Play call on redelivery | Dependency reads no DB row | ✓ |
| Yes — read the event row first | A second copy of the replay rule outside the transaction | |

---

## Claude's Discretion

- The dict literal's shape and name (D-03).
- Class and Protocol names in `auth/google_play.py`.
- The `revoked` mapping for Google if the API exposes a signal; the absent-`data.status` leaf.
- The `JWTVerifier` extension's signature; the Play response model's field set.
- Test shape; log field names; wave order.

## Deferred Ideas

- Phase 44.1 — the feature-sliced restructure (layout above).
- Apple live status from the App Store Server API (declined for now).
- Gateway rate limits on both webhook paths (v2.1 gateway contract).
- Provisioning the Pub/Sub topic, subscription, audience and push service account.
- A `paused` status word.
- Reviewed, not folded: `secret-manager-integration` (ADC adds no secret); `message-ordering-is-unspecified` (chats, unrelated).
