# Phase 46: POST /auth/sign-out-all - Context

**Gathered:** 2026-09-08
**Status:** Ready for planning

<domain>
## Phase Boundary

One authenticated route, `POST /auth/sign-out-all`. The handler calls Firebase Admin to revoke the
caller's refresh tokens through the Admin app the request-verified issuer selects. Success is
returned only when Firebase confirms the revocation. There is no request body, no database write,
no challenge, and no read of the stored provider.

**In scope:** the route, the revocation method on the Firebase seam and its Protocol, one new
error leaf, one INFO log line, the wiring-test list edits, unit and e2e tests, and the
REQUIREMENTS.md and ROADMAP.md amendments.

**Out of scope:** any rate limit or provider budget, coalescing, a retry queue or durable
revocation state, an audit row, an operation enum value, a `checkRevoked` check, a per-device
sign-out, any change to `SHARED-INVARIANTS.md` or the brief, and the two pending todos that
matched on keywords (see Deferred).

</domain>

<decisions>
## Implementation Decisions

### The revocation call

- **D-01: A second method on `FirebaseAdminLookup`.** `auth/firebase.py` gains
  `revoke_refresh_tokens(issuer, subject)` beside `get_user_provider_data`. It selects the Admin
  app from the same apps dict by the request-verified issuer, and it calls
  `firebase_admin.auth.revoke_refresh_tokens(subject, app=app)` through `run_in_threadpool`, as
  the read does. No app for the issuer fails closed with no call made. The `FirebaseAdminAdapter`
  Protocol in `auth/adapters.py` grows by this one method. This answers the FOUND-08 forward flag
  the way it directs: the seam is declared beside its first implementation. The class name
  `Lookup` is now imprecise; a rename is at Claude's discretion.
  — **Reversibility:** reversible — one method, one Protocol line, one fake.

- **D-02: The same retry budget as `getUser`.** Three attempts through the existing tenacity
  policy and the existing attempts constant. Retryable: `FirebaseError` and `GoogleAuthError`.
  Definitive after one attempt: Firebase `UserNotFoundError` (D-06) and the SDK's `ValueError` on
  a malformed uid (D-05). The recorded cost: each attempt can hold up to two SDK transport tries
  at the app-level 8s timeout, so a Firebase outage holds one request for about 48s before the
  client is told to retry (the 37-10 measurement). The user chose one retry rule for every
  Firebase call over a shorter sign-out-specific budget.

- **D-03: Confirmation is the SDK call returning without raising.** No read-back and no
  `getUser` call. The brief forbids a providerData read on this route, and the SDK returns
  nothing on success.

### What the client gets back

- **D-04: 204 No Content.** The brief defines no response fields, the client is about to discard
  its local state, and entitlement did not change. The handler declares `get_linked_identity` and
  the Firebase seam accessor only: no `get_db`, so no session is opened for the request beyond the
  barrier's own short one. No service is earned: the handler body is one awaited call, which
  `AGENTS.md` § "Package layout" keeps in the handler.

- **D-05: One leaf for every unconfirmed outcome.** `RevocationUnconfirmed(ProviderLookupError)`
  in `errors.py`, status 503, code `verification_temporarily_unavailable`, the code every Firebase
  Admin failure already maps to. It is raised for a Firebase error response, a transport failure,
  a timeout, an exhausted retry budget, no app for the issuer, and a malformed uid. The `stage`
  field distinguishes them in the WARNING log line and nowhere else. No new `ErrorCode` member.
  The user chose a leaf of its own over `Unavailable` with a stage so the attempt that neither
  confirmed nor demonstrably failed is found in the logs by its own event name.

- **D-06: Firebase "no such user" answers 401 `auth_required`.** The existing `UserNotFound` leaf
  is raised with a revocation stage. The token verified and the identity row is linked, but the
  IDP has no account behind the uid: nothing exists to revoke and no token can be minted for it
  again. The client's 401 handling ends the session. The alternative, 503 on every attempt for up
  to an hour until the ID token expires, was declined. **FLAGGED CONFLICT** against
  `11-sign-out-all.md` § "Error classes and triggers": the brief lists `auth_required` for
  barrier failures only and puts every non-confirmed revocation on the server-error surface.
  — **Reversibility:** reversible — one `except` arm.

- **D-07: One INFO line on confirmation.** Event `sign_out_all_confirmed` carrying
  `identity_row_id`, a field `UpgradeRefused` already logs. For an anonymous account this route
  is the one-way door, and the middleware `request` line carries no id, so without this line no
  operator can answer "did account X sign out everywhere". Never the subject, never a token.
  This narrows 38 D-02 ("no success log line") to sync; it does not reopen it there. The
  SIGNOUT-02 amendment by Phase 38 permits exactly this: "Phase 46 may still choose to log more
  on its own terms".

### Records

- **D-08: No operation label; the Phase 40 flag is closed.** Sign-out is not challenge-bearing
  and writes no audit row, so the enum's one surviving consumer,
  `core.auth_challenges.operation`, never reads it. `core.auth_operation` keeps its four values
  and the single migration is not edited. Same reasoning and same outcome as RESTORE-01's twin,
  decided here on this route's own terms as the flag requires.

- **D-09: Amend `.planning/REQUIREMENTS.md` on the Phase 45 model, in full.** Dated entries under
  SIGNOUT-01 and SIGNOUT-02: the two forward flags closed (the adapter seam, the label); one new
  flagged conflict (D-06) by brief line; the inventory of obligations already dead before this
  phase, each by brief line and by the phase that removed its mechanism — the route registry and
  its inventory table (Phase 37.1 D-06, FOUND-01), the audit row and the `revocation_unconfirmed`
  and `succeeded` result values (Phase 37.1 D-01, Phase 38 D-03), the backend rate-limit exemption
  clauses (Phase 35 D-05), coalescing (Phase 35 D-05), the exactly-one-`Authorization` wire
  contract at `:42` (developer removal 2026-08-30, FOUND-01), the gateway per-IP and per-user
  entries (v2.1 gateway contract); the unbounded Firebase revocation write per attempt recorded
  as an uncounted divergence on the Phase 40 D-22 precedent (one subject looping on itself, a
  valid token for a linked account required first); the header's counts re-derived. Mark
  SIGNOUT-01 and SIGNOUT-02 met on measured suite counts. In `ROADMAP.md`, rewrite success
  criterion 3 from "Phase 46 must decide" the audit question to what is built (D-05, D-07, the
  middleware line, no row), and record criteria 1, 2 and 4 as met when they are.

- **D-10: `11-sign-out-all.md` and `SHARED-INVARIANTS.md` are NOT edited** (43 D-27, 45 D-14).
  Divergences live in REQUIREMENTS.md.

- **D-11: Every comment this phase writes is ASD-STE100, inline where possible** (45 D-15), under
  `AGENTS.md` § "Comments and docstrings".

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `11-sign-out-all.md` alone will try to build all of these. **None exists.**

- **No route registry, no route metadata, no inventory table** (Phase 37.1 D-06/D-10). The
  route joins `routers/auth.py` under a route-level `Depends(get_linked_identity)`;
  `tests/unit/test_app_wiring.py` gains `/auth/sign-out-all` in its two narrowed-route lists.
- **No `audit.auth_events` row, no audit writer, no `core.auth_event_result` value**
  (Phase 37.1 D-01, Phase 38 D-03/D-04). The record is the middleware `request` line, one
  WARNING per rejection from `app_error_handler`, and D-07's INFO line.
- **No backend rate limit, no provider budget, no coalescing** (Phase 35 D-05). `/auth` paths
  are in no HTTPRoute today; the gateway contract is v2.1.
- **Outcomes are exception classes, never an enum** (Phase 37.3 D-12). Log event names come from
  the class name.
- **The barrier is `get_identity` then `get_linked_identity`** and is not re-implemented. Every
  barrier rejection this route owes already exists: `InvalidExternalJwt` (401),
  `PreAuthIdentityNotAllowed` (403), `HistoricalIdentity` and `BlockedUser` (403
  `account_unavailable`), `IdentityUnresolvable` (500). No route-specific exception for blocked
  or retired subjects.
- **One named Admin app per issuer on Application Default Credentials, never a `[DEFAULT]` app**
  (Phase 37 D-08 as amended by 37-10, Phase 37.2 D-06…D-08). An absent credential returns an
  empty apps dict at boot and the route fails closed as D-05.
- **Every synchronous SDK call runs in `run_in_threadpool`** (35-12).
- **No provider read, no `checkRevoked`, no retry queue, no durable revocation state, no
  per-device sign-out, no challenge** — the brief's own deletions, unchanged.

### Claude's Discretion

- **Names:** the class rename (`FirebaseAdminLookup` to something covering both calls, or left),
  the attempts constant rename, the `stage` strings on `RevocationUnconfirmed` and on the
  `UserNotFound` arm, the INFO event name if `sign_out_all_confirmed` reads badly.
- **The retry wrapper:** a second `*_with_retry` function beside `lookup_with_retry`, or one
  generic wrapper both calls share. The exhausted-budget callback must raise
  `RevocationUnconfirmed`, not `Unavailable`.
- **The handler's declaration order** and the OpenAPI `summary` and `description`, including
  whether the description states that an anonymous account becomes unreachable after this call.
- **Test shape, on the 43 D-24 / 44 / 45 model:** unit tests script
  `firebase_admin.auth.revoke_refresh_tokens` as `tests/unit/test_firebase_adapter.py` scripts
  `get_user`; attempt counts per outcome as `tests/unit/test_firebase_retry.py` does;
  `FakeFirebaseAdapter` in `tests/unit/conftest.py` gains the method; e2e cases through the real
  router with the scripted fake: confirmed answers 204 with an empty body and one INFO line,
  a scripted `FirebaseError` answers 503 with the shared body, no such user answers 401, no app
  for the issuer answers 503, and every barrier rejection is byte-identical to `/auth/sync`'s.
  Whether to add a session stand-in proving the handler runs zero statements after the barrier,
  as Phase 45 did, is the planner's call.
- **Plan wave order.**

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding brief and its invariants
- `/home/init/native-speaker/specs/auth-refactor-phases/11-sign-out-all.md` — the phase brief.
  Read it for the handler steps, the semantics and the DELETIONS list, then read the decisions
  above for what this phase departs from and for what is already dead. Not edited (D-10).
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — § "Fail-closed
  defaults" (never treat an exhausted retry as success; identical status, body and timing per
  class), § "Tokens and sessions", § "Global deletions" (no `checkRevoked`, no backend token).
  Not edited (D-10).
- `.planning/REQUIREMENTS.md` § SIGNOUT (:517-530) — SIGNOUT-01/02, the adapter-seam flag
  (Phase 37.2), the label flag (Phase 40), the audit settlement (Phase 38). D-09 amends this
  block and the header counts at :46-48.
- `.planning/ROADMAP.md` Phase 46 — success criteria; criterion 3 is rewritten by D-09.

### Prior-phase decisions this phase builds on
- `.planning/phases/38-post-auth-sync/38-CONTEXT.md` — D-01…D-05: the audit removal, no success
  log line (narrowed here by D-07), the sibling settlement of SIGNOUT-02's audit half.
- `.planning/phases/45-post-auth-restore-subscription/45-CONTEXT.md` — D-13/D-14/D-15: the
  records model D-09 follows, the operation-label precedent D-08 follows, the ASD-STE100 rule.
- `.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md` — D-11: why
  `core.auth_operation` has four values; D-22: the unbounded-Firebase-read precedent D-09 cites.
- `.planning/REQUIREMENTS.md` FOUND-08 (:150) — the "beside its first implementation" rule D-01
  answers.

### Conventions
- `AGENTS.md` (repo root) — package layout, when a service is earned (not here), comment and
  docstring rules.
- `.env.example` § "Firebase Admin credential" — Application Default Credentials only; the
  e2e real-credential case skips when absent.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auth/firebase.py` — `FirebaseAdminLookup(apps)` holds the issuer-keyed apps dict and the
  `run_in_threadpool` pattern; `_read` shows the exception arms to mirror (`UserNotFoundError`
  definitive, `ValueError`, `GoogleAuthError`, `FirebaseError`); `lookup_with_retry`,
  `RetryableLookupError`, `_exhausted` and `FIREBASE_LOOKUP_ATTEMPTS` are the retry policy D-02
  reuses; `build_admin_apps` is unchanged.
- `auth/adapters.py` — `FirebaseAdminAdapter` Protocol, one method today; D-01 adds the second.
- `errors.py` — `ProviderLookupError(stage, cause)` with `log_fields`; `UserNotFound` (401) for
  D-06; `Unavailable` (503) is the shape `RevocationUnconfirmed` copies.
- `app/dependencies.py` — `get_linked_identity` (the barrier), `get_firebase_adapter` (the seam
  accessor the handler declares).
- `routers/auth.py` — seven routes today; `sync` is the closest shape (no body, narrowed,
  one call). `delete_chat` in `routers/chats.py` is the existing 204 pattern.
- `logs.py` — `RequestLoggingMiddleware` writes the `request` line; `structlog` contextvars
  carry `request_id`.
- `tests/unit/conftest.py::FakeFirebaseAdapter`, `tests/e2e/conftest.py::scripted_firebase_adapter`
  — the fakes D-01's method joins.
- `tests/unit/test_firebase_adapter.py`, `tests/unit/test_firebase_retry.py` — the models for
  scripting the SDK and counting attempts.

### Established Patterns
- A narrowed route declares `Depends(get_linked_identity)` at route level; the router-level
  `get_identity` stays unnarrowed for create-user.
- A Firebase call is one seam method, run off the loop, wrapped by one retry policy, raising
  a `ProviderLookupError` leaf; provider text goes to the log, never to a body.
- One class per outcome, status and code declared once, no field leaks which check refused.
- No success log line is the default (38 D-02); D-07 is a recorded exception for this route.

### Integration Points
- `routers/auth.py` — the eighth auth route.
- `auth/adapters.py`, `auth/firebase.py`, `errors.py` — the seam, the call, the leaf.
- `tests/unit/test_app_wiring.py` — the two parametrized narrowed-route lists.
- `tests/unit/test_error_registry.py` / `error_tree.py` — the error-tree totality checks a new
  leaf must satisfy.
- `k8s/` — no change: `/auth` paths are in no HTTPRoute today.

</code_context>

<specifics>
## Specific Ideas

- **The user reversed one decision mid-discussion.** Both keyword-matched todos were folded and
  then unfolded: "Do not fold the 2 todos into this phase." Neither is in scope.
- **One question at a time, recommended option first, real trade-off in the description**
  worked throughout; every recommended option was taken.
- **Plain English, ASD-STE100, the codebase's own terms** — the 43, 44 and 45 notes still hold.

</specifics>

<deferred>
## Deferred Ideas

- **Gateway rate limits on the auth surface**, including the Firebase revocation write per
  attempt — the v2.1 gateway contract (Phase 35 D-05, 41 D-20).
- **`/auth` paths in the gateway HTTPRoutes** — absent today; a gateway concern.
- **Phase 44.1, the feature-sliced restructure** — after this phase, as recorded in 44-CONTEXT.
- **One test asserting each Python enum's values equal its `core.*` type's labels** — still
  deferred.
- **Renaming `FirebaseAdminLookup`** if left as is under D-01's discretion.

### Reviewed Todos (not folded)

- `message-ordering-is-unspecified` (score 0.6) — chats; matched on the word "phase". Selected,
  then withdrawn by the user. Stays pending.
- `secret-manager-integration` (score 0.2) — config. Selected, then withdrawn by the user. Stays
  pending. Note for whoever picks it up: its "why now" names HMAC key material that no longer
  exists (the audit writer and the challenge hash were deleted); the secrets left are the DB
  password, the OpenAI key, the JWT API key and the DeviceCheck private key path.

</deferred>

---

*Phase: 46-post-auth-sign-out-all*
*Context gathered: 2026-09-08*
