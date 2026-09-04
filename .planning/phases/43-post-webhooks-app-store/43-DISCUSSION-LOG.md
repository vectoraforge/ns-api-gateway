# Phase 43: POST /webhooks/app-store - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-04
**Phase:** 43-post-webhooks-app-store
**Areas discussed:** Provider-callback partition, Apple verification class, Service rules, Replay and responses

---

## General

**User instruction with the area selection:** "Rewrite all comments in ASD-STE100 style. Use inline comments when possible." Recorded as D-25.

**Todos:** both matches (`message-ordering-is-unspecified` 0.4, `secret-manager-integration` 0.2) reviewed, neither folded.

---

## Provider-callback partition

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated router | `routers/webhooks.py`, router-level dependency is the Apple check, membership = routes on it, third literal in the wiring test | ✓ |
| Handler-level verifier only | No router dependency; a second route can forget it | |
| A named constant | A registry again; a second table that drifts | |

| Option | Description | Selected |
|--------|-------------|----------|
| Always registered, fail closed | Lifespan warns; the route answers 503; same route set everywhere | ✓ |
| Conditional registration in lifespan | Matches the brief; route set depends on the environment | |
| Refuse to boot without Apple config | Every environment must carry Apple config | |

| Option | Description | Selected |
|--------|-------------|----------|
| Rename the path only | `/webhooks/apple` → `/webhooks/app-store`; limits deferred to v2.1 | ✓ |
| Rename and add limits | Pick numbers the brief does not give | |
| Do not touch k8s/ | Backend and gateway disagree on the path | |

| Option | Description | Selected |
|--------|-------------|----------|
| Two new leaves | `NotificationRejected` 401 + reuse `Unavailable` 503; shared body, no new code | ✓ |
| Raise HTTPException | Mapped to the generic classes; no bounded log field | |
| Return a bare Response | Gives up the router-level dependency | |

| Option | Description | Selected |
|--------|-------------|----------|
| Ignore an Authorization header | The route never reads it | ✓ |
| Reject it with 401 | One more check and test | |

| Option | Description | Selected |
|--------|-------------|----------|
| Same dependency, declared twice | FastAPI resolves once; the handler receives the value | ✓ |
| request.state | Handler takes Request | |

**Notes:** the user asked why the check is a dependency and not the handler body. Answer: it is the admission gate; it runs before the handler and before `get_db`. The user chose "dependency" after that.

| Option | Description | Selected |
|--------|-------------|----------|
| Third literal, same style | `PROVIDER_CALLBACK_PATHS`; widening is a visible edit | ✓ |
| Derive from the router | A wildcard on the router would also pass | |

---

## Apple verification class

| Option | Description | Selected |
|--------|-------------|----------|
| Vendored in the repo | Apple Root CA G3 DER under `config/` | ✓ |
| Path outside the repo | Treats a public certificate as a secret | |
| Fetch from apple.com at boot | Boot depends on apple.com | |

| Option | Description | Selected |
|--------|-------------|----------|
| OCSP off | Pure computation; no per-request network call | ✓ |
| OCSP on, in the threadpool | Apple's recommendation; one round trip per notification | |

| Option | Description | Selected |
|--------|-------------|----------|
| Our own value type | The service never sees an Apple field | ✓ |
| The library's decoded Apple object | The service maps Apple, then Google, fields itself | |

**Notes:** the user asked "ELI5", then "what ingestion module", "the handler?", "what verifier", "what adapter", "what library", "why do I need an adapter". Each was a term I had coined or imported from the brief. The answer settled as: one class `AppStoreNotifications` in `auth/app_store.py` with one `verify` method, built in lifespan on `app.state`; the dependency is one line. I first said "a function, no class", then reversed to the class when the user asked why hold the verifier and a separate function on `app.state`. The user: "Many things work, it doesn't mean you should give me the worse option." `run_in_threadpool` was dropped: no I/O with OCSP off.

| Option | Description | Selected |
|--------|-------------|----------|
| No default for `environment` | `None` = unconfigured; production must be stated | ✓ |
| Default Sandbox | A forgotten line accepts free sandbox purchases | |

---

## Service rules

| Option | Description | Selected |
|--------|-------------|----------|
| Status from the dates | One function over `expires_at`, `revoked_at`, `grace_period_expires_at`, `in_billing_retry` | ✓ |
| From a notification-type table | About twenty entries to maintain | |

**Notes:** asked three times; the first phrasing used "adapter", the second the user dismissed, the third was in plain terms ("`core.subscriptions` has a `status` column…"). Answer: 2 (the dates).

| Option | Description | Selected |
|--------|-------------|----------|
| Config map | `AppStoreConfig.products: dict[product_id, tier_id]` | ✓ |
| A constant: every product is paid | A test product would grant paid access | |
| A table `core.store_products` | A migration edit and a model for three rows | |

| Option | Description | Selected |
|--------|-------------|----------|
| The grant's `ends_at` | Same term = active grant with the same `ends_at`; no new column | ✓ |
| Store the term's transaction id | A column for one comparison | |

| Option | Description | Selected |
|--------|-------------|----------|
| Grant locks and unique indexes | Resolve the user first; lock grants; indexes arbitrate; loser 5xx | ✓ |
| Lock the subscription row first | A new lock tier ahead of the grant locks | |

| Option | Description | Selected |
|--------|-------------|----------|
| Accept zero credits for a lapsed subscriber | What the indexes and the brief produce; restore is the way back | ✓ |
| Defer a fix to a later phase | Any path reopens the lifetime slot | |

---

## Replay and responses

| Option | Description | Selected |
|--------|-------------|----------|
| Read the event row first | Then every 23505 is a race; no constraint name read | ✓ |
| Parse the constraint name | Rejected in 42-07 | |

| Option | Description | Selected |
|--------|-------------|----------|
| 500 via InternalError leaves | `AttributionConflict`, `UnmappedStoreProduct`; Apple retries | ✓ |
| 200 and a WARNING | Apple's record is gone; breaks "200 means persisted" | |

| Option | Description | Selected |
|--------|-------------|----------|
| 200, nothing written, INFO | TEST and summaries verify but carry nothing to write | ✓ |
| 500 | Apple retries a TEST forever | |

| Option | Description | Selected |
|--------|-------------|----------|
| Real chain in unit, fake in e2e | Throwaway CA in unit tests; scripted fake behind a Protocol in e2e | ✓ |
| Real chain everywhere | Certificate setup in every service case | |
| Fake everywhere | The library never runs in a test | |

---

## Claude's Discretion

- Field set of `VerifiedNotification`; request model name.
- Service and crud module names; model placement in `tables/purchases.py`.
- Protocol name; where the throwaway test chain is generated.
- Mid-term tier change policy (moot with one paid tier).
- Plan wave order; log field names.

## Deferred Ideas

- Gateway per-IP/per-URL limits on the webhook path (v2.1 gateway contract).
- Online certificate revocation checks.
- A way back to a free-tier grant for a lapsed subscriber.
- Google Play (44); restore and adoption (45).
