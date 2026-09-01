# Phase 39: GET /users/me - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-01
**Phase:** 39-get-users-me
**Areas discussed:** Response body shape, Where profile fields come from, Missing-token tripwire, Caching and redaction posture

---

## Response body shape

### Token container shape

| Option | Description | Selected |
|--------|-------------|----------|
| Object keyed by provider, value an object | Each store uses its own SDK's field name (`app_account_token`, `obfuscated_external_account_id`) | |
| Object keyed by provider, bare token string | Flattest; key set is exactly the `PurchaseProvider` enum | ✓ |
| Array of entries | Closest to the brief's literal "entry" wording; forces a generic field name and a client-side scan | |

**User's choice:** Object keyed by provider, bare token string.
**Notes:** The developer first asked whether returning every store's token to a single-platform
client is an industry standard, and then asked for the answer briefly and in plain English. Answered:
no — most implementations return only the calling platform's token, so the unconditional shape is the
less common choice. Kept because branching would require trusting a client signal (User-Agent, a
header) to steer a server-side read, which the codebase forbids everywhere else; and because it is
locked regardless by PROF-01 and roadmap success criterion 1. The underlying mechanism *is* standard:
Apple's StoreKit 2 `appAccountToken` (must be a UUID) and Google Play Billing's
`obfuscatedExternalAccountId` (max 64 chars), both minted as `str(uuid4())` in `crud/identities.py:90`.

### Profile field nesting

| Option | Description | Selected |
|--------|-------------|----------|
| Flat — `email`/`display_name` at top level | Only two fields exist; a wrapper earns little | |
| Nested under `profile` | Follows sync's precedent of nesting a named block; reads as three groups | ✓ |

**User's choice:** Nested under `profile`.

### Payload closure

| Option | Description | Selected |
|--------|-------------|----------|
| Exactly profile + `identity_provider` + tokens | The brief's enumeration is closed; sync's response is likewise | ✓ |
| Also `user_id` | Lets a client correlate support requests; authenticates nothing | |
| Also `registered_at` | Reporting-only column; risks a client reading it as a registration classifier | |

**User's choice:** Exactly those three — nothing else.

### Container field name

| Option | Description | Selected |
|--------|-------------|----------|
| `store_tokens` | Short; "store" is the disambiguator the brief leans on | |
| `purchase_tokens` | Mirrors `core.store_purchase_tokens` most closely | ✓ |
| `attribution_tokens` | Names the purpose; hardest to misread as a credential | |

**User's choice:** `purchase_tokens`.

---

## Where profile fields come from

### Source of `email` and `display_name`

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse the barrier's resolved row | `expire_on_commit=False` keeps it readable; makes the token read the only query | ✓ |
| Re-query `core.users` | Literal to the brief's handler step 1; a second query for a row already in memory | |

**User's choice:** Reuse the barrier's row.
**Notes:** The freshness a re-query would buy is empty — no path in this milestone edits either
field, both being explicit deletions in the brief.

### Service layer

| Option | Description | Selected |
|--------|-------------|----------|
| No service — router calls crud directly | A `ProfileService` would only forward one call | ✓ (with a rule change) |
| A `ProfileService` in `services/` | Symmetrical with `SyncService` | |

**User's choice (free text):** "Create a CRUD function in `crud/` and use it. Services are needed if
the router body becomes too big or complicated. Adjust `AGENTS.md` accordingly."
**Notes:** This goes beyond the endpoint — it is a repo-wide convention. Amending `AGENTS.md`
§ "Package layout" became a deliverable of this phase (CONTEXT.md D-05). Existing services are not
refactored.

### Query home

| Option | Description | Selected |
|--------|-------------|----------|
| New `crud/purchases.py` | Every crud module is named for its table family; pairs with `tables/purchases.py` | ✓ |
| Extend `crud/identities.py::IdentitiesDB` | Mint and read together; widens an identity-resolution class | |

**User's choice:** New `crud/purchases.py`.

---

## Missing-token tripwire

### How the failure is signalled

| Option | Description | Selected |
|--------|-------------|----------|
| New `MissingPurchaseTokenError` | Beside `MissingUsageRowError` at `log_level = ERROR`; own greppable event | ✓ |
| Reuse `IdentityUnresolvable` | Right shape, wrong subject — a broken identity link, not a missing token row | |
| Raise bare `InternalError` | `log_level = None`, so the breach would page nobody | |

**User's choice:** New `MissingPurchaseTokenError`.

### Completeness check

| Option | Description | Selected |
|--------|-------------|----------|
| One row per `PurchaseProvider` enum member | Enum is the source of truth; refuses partial results | ✓ |
| Only when zero rows return | Tolerates a partial result and emits a body missing a guaranteed key | |

**User's choice:** One row per enum member.
**Notes:** Accepted consequence — adding a third store later makes pre-existing accounts fail closed
until backfilled. Loud rather than silent, which is the fail-closed reading.

### Log context

| Option | Description | Selected |
|--------|-------------|----------|
| `user_id` and the missing provider(s) | Matches `MissingUsageRowError(grant_id)`; neither value is the token | ✓ |
| `user_id` only | Operator must query for which store's row is gone | |

**User's choice:** `user_id` and the missing provider(s).

---

## Caching and redaction posture

### Cache header

| Option | Description | Selected |
|--------|-------------|----------|
| `Cache-Control: no-store` | Matches `/auth/challenge`; private client caches would otherwise retain it | ✓ |
| No cache header | Leans on HTTP semantics; tokens are lifetime-stable so a cached copy is never wrong | |
| `Cache-Control: private, no-cache` | Middle ground buying little for a one-query endpoint | |

**User's choice:** `Cache-Control: no-store`.

### Log-redaction test

| Option | Description | Selected |
|--------|-------------|----------|
| Assert no log record contains the token | Guards invariant 10 against a future change that logs bodies | |
| No test — current logging shape is proof | Middleware logs only request_id/method/path/status; nothing carries a body | ✓ |

**User's choice:** No test.
**Notes:** The redaction obligation is met instead by constraining `MissingPurchaseTokenError` never
to carry `identity_value`.

### Route home

| Option | Description | Selected |
|--------|-------------|----------|
| New `routers/users.py` | Matches the URL family; router-level narrowing covers future `/users/*` | ✓ |
| Add to `routers/auth.py` | What `/auth/sync` did; no new wiring, but a `/users/*` path in an auth router | |

**User's choice:** New `routers/users.py`.

---

## Claude's Discretion

- Class and method names in `crud/purchases.py`, and the form of the enum completeness check.
- How `tests/unit/test_app_wiring.py` gains its `/users/me` assertions — two parallel tests
  mirroring the `/auth/sync` pair, a parametrised version, or a widened generic assertion.
- Test placement and depth within the existing `tests/unit` + `tests/e2e` split.
- Exact wording of the `AGENTS.md` § "Package layout" amendment, so long as it states the developer's
  rule.

## Deferred Ideas

- `user_id` and `registered_at` in the profile payload — considered and declined.
- Restoring rate limiting to the auth and `/users` surface — absent this milestone, deferred to v2.1.
- A log-redaction test for the purchase token — revisit if response-body logging is ever added.
- Refactoring existing services under the new layering rule — the rule binds new code only.
- Four pending todos reviewed against this phase, none folded: `admission-holds-a-db-connection`,
  `breaker-check-moved-to-admission`, `message-ordering-is-unspecified`, `secret-manager-integration`.
