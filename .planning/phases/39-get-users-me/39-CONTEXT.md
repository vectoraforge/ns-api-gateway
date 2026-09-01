# Phase 39: GET /users/me - Context

**Gathered:** 2026-09-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `GET /users/me` — one read-only, authenticated route returning the resolved user's profile
fields (`email`, `display_name`), the account's stored registration state (`identity_provider`),
and the persisted per-store purchase-attribution tokens, unconditionally for every store provider.
The route was deleted by Phase 35 D-16 along with its router; this phase re-declares it. Nothing is
written, no lock is taken, and no provider is called.

The phase also lands one repo-wide convention change (D-05): `AGENTS.md` § "Package layout" is
amended so a router may call `crud/` directly, and a `services/` class is introduced only when the
handler body would otherwise become large or complicated.

**Out of scope:** the `users_me` backend rate-limit entry the brief mandates (the engine is deleted
from the product, not deferred — Phase 35 D-05, restated in `AGENTS.md` § Resilience); any
`audit.auth_events` row or the counter metric that was to replace it (both removed milestone-wide —
see "Carried forward" below); any minting, rotation, replacement or lazy re-mint of a purchase
token; any mutation of `core.external_identities`, `core.access_grants`, `core.subscriptions` or
`core.store_purchases`; challenge machinery; any Firebase Admin or `providerData` read; any grant
creation, flip, repair or rollover; schema changes of any kind.

</domain>

<decisions>
## Implementation Decisions

### The response body

- **D-01: The shape.** `profile` is a nested block; `identity_provider` and `purchase_tokens` sit
  beside it at top level. `purchase_tokens` is an object keyed by store provider whose values are
  the bare token strings.

  ```json
  {"profile": {"email": "a@b.com", "display_name": "Ada"},
   "identity_provider": "google",
   "purchase_tokens": {"apple": "…", "google_play": "…"}}
  ```

  Nesting follows sync's precedent of grouping a named block while leaving `identity_provider` at
  top level. The keyed-object form was chosen over an array of entries and over per-store field
  names: the key set is exactly the `PurchaseProvider` enum, so "an entry for every store" is
  structurally evident rather than asserted, and the client indexes instead of scanning. The cost,
  accepted: the client must know the `apple` value *is* the StoreKit `appAccountToken` and the
  `google_play` value *is* the Play Billing `obfuscatedExternalAccountId` — the wire shape does not
  say so. Field name `purchase_tokens` mirrors `core.store_purchase_tokens`.
  **The body carries nothing else** — no `user_id`, no `registered_at`. Both fields exist and were
  considered; the brief's payload enumeration is closed and anything a client later needs gets
  added deliberately.
  — **Reversibility:** one-way — a published client contract. The iOS client reads the `apple`
  value and passes that exact string into StoreKit at purchase time; `GET /users/me` and
  `/auth/sync` must also keep reporting the same `identity_provider` value (Phase 38 D-06).

- **D-02: Every store's token ships on every request, with no platform condition. Not open —
  recorded here so a planner does not reopen it.** This is PROF-01 and roadmap success criterion 1,
  and the brief states it three separate times. **The developer asked directly whether this is the
  industry standard; the honest answer is no** — most implementations return only the calling
  platform's token, and the unconditional shape is the less common choice. It is kept anyway
  because branching would let a client-supplied signal (User-Agent, an `X-Platform`-style header, a
  query parameter, a body flag) decide what the server reads and returns, and this codebase forbids
  that class of thing everywhere else: the barrier ignores every client and proxy identity header,
  and credentials are never accepted from query, cookie, body or `X-*` headers. A fixed shape has
  no branch to test and no platform-detection logic that can drift between client and server, and
  a genuinely cross-platform account needs no second round trip. The cost is one value the caller
  ignores; the tokens are opaque `uuid4()` strings that confer nothing, and the brief already
  accepts that a leaked ID token reads profile, entitlement and chats regardless.

### The read path

- **D-03: Profile fields come from the barrier's already-resolved row. No second query.**
  `get_linked_identity` returns an `Identity` carrying the loaded `User` row, and
  `app/lifespan.py:36` sets `expire_on_commit=False`, so `identity.user.email` and
  `identity.user.display_name` stay readable after the barrier's short session closes — `/auth/sync`
  already reads `identity.user.id` and `identity.identity.provider` exactly this way. The purchase-
  token read is therefore the request's **only** query.
  This is a **deliberate divergence from the brief's literal handler step 1** ("Load the resolved
  user's profile fields from `core.users`"). The step is satisfied in substance: the row *was*
  loaded from `core.users`, by the barrier, in this request. Re-reading would issue a second query
  for a row already in memory, and the freshness it would buy is empty — no path in this milestone
  edits either field (no email sync, and `display_name` is never populated from auth context; both
  are explicit deletions in the brief).

- **D-04: The purchase-token query lives in a new `crud/purchases.py`.** Every existing `crud/`
  module is named for its table family — challenges, chats, grants, identities — and this one pairs
  with `tables/purchases.py`. Reading tokens is not identity work, so it does not widen
  `IdentitiesDB`, whose stated job is identity resolution (it mints the rows in `insert_account`;
  read and mint live apart).

- **D-05: No service layer for this endpoint — the router calls `crud/` directly — and `AGENTS.md`
  is amended to state the general rule.** With profile coming from the barrier's row (D-03) and the
  fail-closed rejection staying with the query per `AGENTS.md` § Package layout exception 4, a
  `ProfileService` would contain one awaited read and nothing else, which is precisely the shape
  `AGENTS.md` § "Function shape" says to inline.
  **The developer's rule, to be written into `AGENTS.md` § "Package layout":** a router may call
  `crud/` directly; a `services/` class is introduced when the router body would otherwise become
  too big or complicated. This supersedes the current text's implication that business logic always
  routes through `services/`. Existing services are not refactored by this phase.
  — **Reversibility:** costly — this is a repo-wide convention that binds every later phase's
  layering, and `AGENTS.md` is read by every implementing agent. Reversing it means re-deciding the
  rule and revisiting whatever routers were written under it.

### Broken data

- **D-06: A missing token row raises a new `MissingPurchaseTokenError`.** An `InternalError`
  subclass at `log_level = logging.ERROR`, sitting beside `MissingUsageRowError`,
  `MultipleEffectiveGrantsError` and `UnknownTierError` and following their exact pattern. The
  client sees the opaque 500 `internal_error`; the operator gets one greppable ERROR event.
  Phase 38 D-07 reused existing classes because they already named its conditions — none names this
  one, and raising a bare `InternalError` would emit no ERROR line at all (`log_level = None`), so
  an invariant breach would page nobody.
  **It carries `user_id` and the missing provider(s)** — enough to find and repair the row, matching
  `MissingUsageRowError(grant_id)`. **Neither value is the token, so invariant 10's redaction rule
  is untouched: `identity_value` must never enter the exception message or any log field.**
  Per `AGENTS.md` § Package layout exception 4, the raise stays with the query in `crud/purchases.py`.

- **D-07: Completeness is checked against the `PurchaseProvider` enum — one row required per
  member.** Not "zero rows returned". This matches the brief's "an entry for EVERY store provider"
  and refuses a partial result rather than emitting a body missing a key the contract guarantees.
  **Known consequence, accepted:** adding a third store to `PurchaseProvider` later makes every
  pre-existing account fail closed on this endpoint until its rows are backfilled. That is the
  fail-closed reading and it fails loudly rather than silently.
  Never lazily minted — the brief forbids it, and minting here would convert a detectable broken
  invariant into a silent repair.

### The route and its headers

- **D-08: A new `routers/users.py`, with `Depends(get_linked_identity)` at router level.**
  `/users/me` is not an auth operation, and `routers/auth.py`'s docstring names three auth routes.
  A router-level narrowing means every future `/users/*` route inherits it rather than needing its
  own route-level override — the opposite of `routers/auth.py`, which is deliberately unnarrowed so
  create-user can answer an already-linked caller with 409. Requires an export in
  `routers/__init__.py` and an `include_router` call in `app/main.py`.

- **D-09: The response carries `Cache-Control: no-store`.** Following `/auth/challenge`, which sets
  it for its secret handle. This body is not secret but is private account metadata under invariant
  10. A shared cache already must not store an `Authorization`-bearing response, but a private
  client cache may — a mobile `URLSession` will by default. Set through an injected `Response` so
  the handler keeps returning the typed model rather than hand-building a `JSONResponse`.

- **D-10: No test asserting the token is absent from logs.** `RequestLoggingMiddleware` emits only
  `request_id`, `method`, `path` and `status_code`, and error handlers emit branch names; no code
  path carries a response body into a log, so such a test would assert something no code attempts.
  The redaction obligation is met by D-06's constraint on the exception message instead.

### Carried forward — decided in earlier phases, binding here, do NOT rebuild

The brief lists these under "Provided by foundation — call, never rebuild" or "This phase adds".
**Several no longer exist.** A planner reading `04-users-me.md` alone will try to build them.

- **No `audit.auth_events` row, ever — and nothing to write one with.** The table, its writer and
  every call site were deleted by Phase 37.1 D-01; Phase 38 D-03 struck § "Audit" from
  `SHARED-INVARIANTS.md` outright. PROF-02's audit clause is *trivially* true and is kept because it
  still binds. **Phase 39 inherits no obligation to build an audit writer.**
- **No bounded-cardinality counter metric.** The brief's "telemetry that replaces the audit row" is
  dead: Phase 36 D-15 removed the hand-rolled `RejectionCounter`, and rejection rate is derived from
  the structured log by the deployment's log pipeline. `.planning/REQUIREMENTS.md` PROF-02 says so
  explicitly, in as many words, precisely so this is not read as a standing instruction.
- **No `users_me` rate-limit entry, and no rate-limit engine to register it with.** Phase 35 D-05
  deleted the backend `limits` engine **from the product, not deferred** — `AGENTS.md` § Resilience
  states this, and `limits` is absent from `pyproject.toml`. The auth surface is knowingly unlimited
  this milestone (Phase 38 D-08).
- **No route registry and no startup enumeration assertion.** `auth/registry.py` was deleted by
  Phase 37.1 D-06; Phase 37.5 turned the startup totality walk into a test. Route categorisation is
  carried by `tests/unit/test_app_wiring.py` alone.
- **No new client-visible error class.** Every rejection this endpoint owes already exists:
  `InvalidExternalJwt` (401 `auth_required`), `PreAuthIdentityNotAllowed` (403),
  `HistoricalIdentity` / `BlockedUser` (403 `account_unavailable`), `IdentityUnresolvable` (500) for
  the orphan-user case. D-06 adds an *internal* class only — it answers the same opaque 500.
- **No success log line.** The middleware already emits one `request` line per attempt; Phase 38
  D-02 rejected a second. Do not add a `users_me_succeeded` event or any per-attempt telemetry.
- **The phase briefs under `specs/auth-refactor-phases/` are marked verbatim and are NOT edited.**
  Divergences are recorded as dated amendments in `.planning/REQUIREMENTS.md` (Phase 38 D-05
  precedent). D-03's divergence from handler step 1 and D-02's rate-limit omission belong there.

### Claude's Discretion

- **The `crud/purchases.py` class and method names**, and whether the completeness check reads as a
  dict comprehension over the enum or an explicit set difference.
- **How `tests/unit/test_app_wiring.py` gains its `/users/me` assertions.** It currently names
  `/auth/sync` in two dedicated tests (`test_the_sync_route_declares_the_linked_identity_narrowing`,
  `test_the_sync_route_is_in_neither_exemption_set`) rather than leaning on the generic case. A new
  authenticated route deserves the same treatment, but whether that is two parallel tests, a
  parametrised pair, or a widened generic assertion is the planner's call.
- **Test placement and depth**, within the existing `tests/unit` + `tests/e2e` split.
- **The exact wording of the `AGENTS.md` § "Package layout" amendment** required by D-05, so long as
  it states the rule the developer gave: router-to-crud is allowed; a service appears when the
  router body would otherwise be too big or complicated.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding specification (overrides phase briefs on conflict)
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — binds every phase.
  Read § "The barrier", § "Fail-closed defaults", § "Identity and ownership" and § "Global
  deletions". § "Audit" was removed by Phase 38 D-03 and § "Rate limits" is dead per Phase 35 D-05.
  **This phase does not edit it.**
- `/home/init/native-speaker/specs/auth-refactor-phases/04-users-me.md` — the phase brief. Marked
  verbatim, not edited. Its audit-row, counter-metric, route-registry and `users_me` rate-limit
  obligations are all superseded — see "Carried forward" above before implementing any of them.

### The source specification
- `/home/init/native-speaker/specs/auth-refactor/01-sessions-and-identity-resolution.md`
  § "API: GET /users/me" — the source the brief was cut from.
- `/home/init/native-speaker/specs/auth-refactor/06-schema-reference.md` — `store_purchase_tokens`
  shape and the `(user_id, provider)` uniqueness rule.

### Project planning
- `.planning/REQUIREMENTS.md` § PROF (:211-217) — PROF-01, PROF-02 and the Phase 37.1 amendment
  stating that Phase 39 inherits no audit-writer or counter obligation. **This phase appends its
  own dated amendments here** (D-02's rate-limit omission, D-03's divergence from handler step 1).
- `.planning/ROADMAP.md` Phase 39 (:508-518) — the four success criteria.
- `.planning/phases/38-post-auth-sync/38-CONTEXT.md` — the direct precedent. D-01/D-03 (audit
  removal), D-02 (no success log), D-06 (`identity_provider` must read consistently across both
  endpoints), D-07 (fail-closed posture), D-08 (rate limiting knowingly absent).
- `.planning/PROJECT.md` § Constraints — the one-migration rule and the spec-authority rule.

### Repo conventions
- `ns-api-gateway/AGENTS.md` — § "Package layout" (**amended by D-05**), § "Function shape",
  § "Comments and docstrings" (three-line docstrings, comments only to resolve ambiguity),
  § "Resilience" (the `limits` engine is deleted, not deferred).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/dependencies.py::get_linked_identity` — the barrier. Already raises every rejection this
  endpoint owes, and returns an `Identity` carrying the loaded `User` and `ExternalIdentity` rows.
  **No error path needs building.**
- `schemas/auth.py::Identity` — frozen dataclass; `identity.user.email`, `identity.user.display_name`
  and `identity.identity.provider` are the three fields D-03 reads straight from it.
- `schemas/auth.py::SyncResponse` — the model to imitate for shape and docstring register. The new
  response model belongs beside it in `schemas/auth.py`.
- `routers/auth.py::sync` — the closest handler analog: `Depends(get_linked_identity)`, one service
  call, typed model return.
- `routers/auth.py::issue_challenge` — the `Cache-Control` precedent D-09 follows (it hand-builds a
  `JSONResponse`; D-09 prefers an injected `Response` to keep the typed return).
- `tables/purchases.py::StorePurchaseToken` / `PurchaseProvider` — the table and the two-member enum
  D-07 checks completeness against. Composite PK is `(user_id, provider)`; the token column is
  `identity_value`.
- `errors.py::MissingUsageRowError` — the exact template for D-06: `InternalError` subclass,
  `log_level = logging.ERROR`, `__init__` capturing identifying context into the message.

### Established Patterns
- **Layering** (`AGENTS.md` § Package layout, amended by D-05): handler in `routers/`, queries in
  `crud/`, response bodies in `schemas/`, tables in `tables/`. A fail-closed read raises its own
  rejection in `crud/` (exception 4).
- **One captured instant per request** — every service takes `evaluated_at=datetime.now(UTC)` from
  its dependency. **This endpoint reads no clock at all**, so the pattern does not apply; do not add
  an `evaluated_at` for symmetry.
- **Docstring and comment bar is 0 by default** (37.4 D-12, 37.5): three lines maximum, comments only
  where they resolve a genuine ambiguity.
- **Detached-row reads are established, not novel** — `expire_on_commit=False` plus `/auth/sync`'s
  existing `identity.user.id` read is the proof D-03 relies on.

### Integration Points
- `app/main.py` — add `include_router(users_router)`; `routers/__init__.py` — add the export.
- `tests/unit/test_app_wiring.py` — `PUBLIC_PATHS` and `PREAUTH_CALLABLE_PATHS` are deliberate
  literals; `/users/me` belongs in neither, and `test_the_public_allowlist_is_exactly_the_readiness_probe`
  will fail if the router-level dependency is wrong.
- `migrations/20260818_01_initial-release.sql` — **not touched.** No schema change; `tests/schema/`
  stays as is.

### Naming Hazard
`identity_provider` and the `purchase_tokens` keys both use the value `"apple"`, meaning two
different things: the Firebase identity provider (`core.identity_provider`) and the store
(`core.subscription_provider`). The brief flags this explicitly. Keep `PurchaseProvider` and
`IdentityProvider` distinct at every seam; never derive one from the other.

</code_context>

<specifics>
## Specific Ideas

- The developer asked, plainly, whether returning every store's token to a single-platform client is
  the industry standard — and asked for the answer briefly and in plain English. It is not the
  standard; the reasoning for keeping it is recorded in D-02 rather than the appeal to convention.
- On layering: "Create a CRUD function in `crud/` and use it. Services are needed if the router body
  becomes too big or complicated. Adjust `AGENTS.md` accordingly." A service is earned by
  complexity, not assumed by category.
- Brevity is expected in answers. Long framing was cut short once during this discussion.

</specifics>

<deferred>
## Deferred Ideas

- **`user_id` and `registered_at` in the profile payload** — both considered and declined for this
  phase (D-01). If a client later needs either, it is a deliberate contract addition.
- **Restoring rate limiting to the auth and `/users` surface** — knowingly absent this milestone
  (Phase 35 D-05, Phase 38 D-08); the gateway contract is deferred to v2.1.
- **A test asserting the purchase token never reaches a log line** — declined for now (D-10) because
  no code path carries a body into a log. Worth revisiting if response-body logging is ever added.
- **Refactoring existing services under D-05's new rule** — the rule is written into `AGENTS.md` and
  binds new code; `SyncService`, `AuthService`, `QuotaService` and `ChatService` are not revisited
  here.

### Reviewed Todos (not folded)
All four keyword matches reviewed; none touches a read-only profile endpoint:
- `admission-holds-a-db-connection` (score 0.6) — LLM admission and the quota charge, a write path.
- `breaker-check-moved-to-admission` (score 0.6) — LLM provider resilience.
- `message-ordering-is-unspecified` (score 0.2) — chats.
- `secret-manager-integration` (score 0.2) — config; declined for the seventh consecutive phase.

</deferred>

---

*Phase: 39-get-users-me*
*Context gathered: 2026-09-01*
