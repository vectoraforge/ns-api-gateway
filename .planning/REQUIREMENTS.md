# Requirements: ns-api-gateway — v2.0 Authentication & Entitlements

**Defined:** 2026-08-19
**Core Value:** The analysis pipeline must work reliably — correct LLM invocation, proper resilience under load, and safe per-user data isolation.

**Specification:** `/home/init/native-speaker/specs/auth-refactor-phases/` — one file per phase. `SHARED-INVARIANTS.md` binds every phase and wins over any phase brief on conflict.

**Organizing principle:** one phase = one REQ-ID prefix, 1:1. Endpoint phases implement exactly one endpoint. No requirement spans phases.

**Phase map:** 34 SCHEMA · 35 FOUND · 36 REBIND · 37 CREATE · 38 SYNC · 39 PROF · 40 UPGRADE · 41 ANONGRANT · 42 REGGRANT · 43 APPLEHOOK · 44 PLAYHOOK · 45 RESTORE · 46 SIGNOUT

> **Amended by Phase 37.1 (2026-08-24) for two deletions.** The auth-event audit subsystem was deleted outright (D-01) and the auth barrier middleware plus the route registry were replaced by a router-level FastAPI dependency (D-06). Every requirement those deletions touched carries a note saying which treatment it got and why: **amended** (mechanism changed, substance intact), **withdrawn** (its subject no longer exists), or **flagged forward** (an unbuilt phase must decide for itself). One requirement was deleted outright — see the FOUND block.
>
> **Amended again by Phase 37.2 (2026-08-25) for the auth-module simplification.** Challenge issuance moved out of create-user's prepare mode onto its own `POST /auth/challenge` route (D-01/D-03/D-05), the Firebase service-account credential path was deleted in favour of Application Default Credentials (D-06…D-08), and the zero-consumer adapter interfaces were deleted along with the lazy re-export facade (D-09/D-11). CREATE-01/02 and FOUND-08 are **amended**; FOUND-08 is additionally **flagged forward** to phases 43–46. This phase deleted and withdrew nothing — every requirement it touched kept its substance.
>
> **Amended again by Phase 37.3 (2026-08-26) for the returned-rejection refactor.** Four sites that *returned* a rejection vocabulary — the consuming transaction, identity resolution, the provider lookup and the challenge binding — now raise DRF-style exceptions carrying their own `ErrorClass`, answered by one handler (D-01/D-02). The `AuthEventResult` outcome enum, the `ProviderData*` result types and the `Admit`/`Reject` union are deleted (D-03/D-09/D-12). **FOUND-08 is amended again** and its forward flag to phases 43–46 is carried unchanged. Zero client-visible change: every status, error class and body is byte-identical, and only the structured-log event vocabulary moved. No requirement was deleted, withdrawn or unchecked, and **no new conflict against `SHARED-INVARIANTS.md` was found** — the three below are still the three.
>
> **Three conflicts against `SHARED-INVARIANTS.md` are recorded as FLAGGED, not resolved** — under FOUND-01 (D-06 against its pre-handler-barrier rule), under FOUND-05 (D-01 against its audit obligation), and under CREATE-01 (Phase 37.2 D-08, Application Default Credentials against its no-ambient-credential rule). That document binds every phase, wins over any phase brief, and **has not been amended**. Per the standing rule from `37-CONTEXT.md`, such conflicts are flagged so a later reader finds the divergence rather than discovering it.

## v2.0 Requirements

### SCHEMA — Phase 34 (`00-schema.md`)

- [x] **SCHEMA-01**: The single initial migration `migrations/20260818_01_initial-release.sql` replaces the deleted prior migration and creates the complete v2.0 schema in one apply against an empty database — no incremental migration files are added
  > **Upheld against a later conflicting decision (Phase 37, plan 37-01 Task 1, 2026-08-22).** `37-CONTEXT.md` D-13 called for "a new migration" to drop `core.auth_challenges.operation_variant`. That mechanism was rejected in favor of this requirement: the initial migration is **edited in place** and the disposable dev/test database is dropped and re-applied. SCHEMA-01 is unamended and `tests/schema/test_apply_rollback.py::test_exactly_one_sql_file` stays green unmodified. The consequence for any future v2.0 schema change is the same: edit in place, re-apply, never add a file.

- [x] **SCHEMA-02**: `core.users`, `core.external_identities`, and the `core.identity_provider` enum support `(issuer, subject)` → user resolution, with `identity_state` and permanently-retained tombstone rows
- [x] **SCHEMA-03**: `core.access_grants`, `core.access_tiers`, and `core.user_monthly_usage` enforce at most one active grant per user, with monthly usage keyed by grant id
- [x] **SCHEMA-04**: `core.subscriptions`, `core.store_purchases`, and `core.store_purchase_tokens` support both stores, with `product_entitled_subscription_id` as a STORED generated column over `('active','grace_period')`
- [x] **SCHEMA-05**: `core.auth_challenges` supports the claim/consume protocol for challenge-bearing operations
- [x] **SCHEMA-06** — **WITHDRAWN.** Delivered by Phase 34 exactly as written, and true until 2026-08-24: `audit.auth_events` enforces the actor-field CHECK constraints and the `core.auth_operation` / `core.auth_event_result` enums in full
  > **Withdrawn by Phase 37.1 (D-01), 2026-08-24.** The `audit.auth_events` table, its nine CHECK constraints and its four `ix_auth_events_*` indexes were deleted from the initial migration, along with the `core.auth_event_result` type. Nothing this requirement asserts is checkable any more, so it is withdrawn rather than reworded into something true — the schema it describes really did ship, and editing that away would falsify Phase 34's own delivery. `tests/schema/test_constraints.py`'s `TestAuthEventAuditConstraints` class (6 cases) went with it.
  >
  > **Only half the enum clause fell. `core.auth_operation` survives** — `core.auth_challenges.operation` stores it and `auth/creation.py` uses the matching `AuthOperation` enum — as do the `audit` **schema** and `audit.subscription_events` (D-02), so phases 43 and 44 still have a recorded home for store notifications. Only `core.auth_event_result` was dropped.
  >
  > **Consequence for later phases:** no phase may assert anything about `audit.auth_events`. One-way: restoring the table means re-editing the single initial migration under SCHEMA-01.
  >
  > *Corrected by Phase 37.3 (D-12), 2026-08-26.* This note previously read that `AuthEventResult` "survives in Python as a plain 44-member `StrEnum` backed by no database type (D-04)". It does not survive: all 44 members were deleted from `models/auth.py`. The internal rejection vocabulary is the `AuthRejected` exception-class family in `auth/exceptions.py` now, and the class name snake_cased is the structured log event. Nothing persisted changed — the enum had been backed by no database type since this phase-37.1 deletion, so there is no column and no migration. `AuthOperation` is unaffected and still backs `core.auth_challenges.operation`.
- [x] **SCHEMA-07**: Legacy structures are gone — `core.users.jwt_sub`, `core.users.subscription_plan`, `core.usage_monthly`, `core.subscription_events`, the `core.subscription_plan` enum, and the `promo` grant source
- [x] **SCHEMA-08**: Every acceptance check in `00-schema.md §10` passes against a freshly migrated database

### FOUND — Phase 35 (`01-foundation.md §1–§4, §6, §7`)

Shared machinery only. Rebinding the pre-existing routes is Phase 36.

> Scope narrowed by the Phase 35 discussion (`35-CONTEXT.md`): `§5` (backend rate-limit engine) is **deleted from the product** — Envoy Gateway is the sole request-rate enforcement point (D-05), overriding `SHARED-INVARIANTS.md` § Rate limits and `01-foundation.md §5`. `§9` (the Envoy contract) is **deferred to v2.1** (D-08). The `§7.1` provider-call budget seam survives as FOUND-06 (D-06).

- [x] **FOUND-01**: A mandatory, default-on pre-handler dependency — declared on every non-public `APIRouter` and again on each endpoint — is the only place JWT acceptance and identity resolution happen; it admits only `identity_state='active'` AND `users.active` exactly TRUE
  > **Mechanism amended by Phase 37.1 (D-06/D-07/D-11), 2026-08-24. Substance unchanged — every property this requirement asserts still holds.** The pure-ASGI `AuthBarrierMiddleware` was deleted; `get_request_context` now does the work. It is **mandatory** and **default-on** (declared on the `APIRouter`, so an endpoint that forgets its own `Depends` is still authenticated), it runs **before the handler**, and it is the **only** place JWT acceptance and identity resolution happen. FastAPI's per-request dependency cache resolves the router-level and endpoint-level declarations to one execution. Only the word "barrier" stopped being true.
  >
  > The admission rule above is carried **verbatim** and is not amended. `auth/verification.py`, `auth/wire.py` and `auth/identity.py` were kept and re-hosted rather than rewritten, so the admission matrix moved intact: `tests/e2e/test_admission.py`'s 23 cases passed the swap with **zero** edits to any status code or body literal.
  >
  > **FLAGGED CONFLICT against the binding specification — recorded, NOT resolved.** `SHARED-INVARIANTS.md` § "The barrier — the only place identity happens" still reads *"JWT acceptance and identity resolution happen ONLY in the shared, mandatory, default-on pre-handler **barrier**"*, and still requires that *"Every registered route sits in exactly one of three categories … The CI/startup route-enumeration assertion must pass"*. That document binds every phase and wins over any conflicting phase brief, and **it has not been amended**. This project has knowingly diverged: the barrier is a FastAPI dependency, and the route registry and its enumeration assertion are gone (withdrawn just below). Recorded here per the standing rule from `37-CONTEXT.md` — conflicts against `SHARED-INVARIANTS.md` are flagged, never silently resolved — so a later reader finds the divergence rather than discovering it.

- [ ] **FOUND-02**: The auth dependency enforces the exactly-one-Authorization wire contract — zero values, duplicate field instances, comma-joined values, multiple credentials, empty tokens, and trailing content all reject as `invalid_external_jwt`
  > **Reworded by Phase 37.1 (D-06), 2026-08-24 — one noun, nothing else.** The wire contract is untouched: `auth/wire.py` is unchanged and only its caller moved. `tests/unit/test_wire_contract.py` and `tests/e2e/test_wire_contract.py` (both renamed from `test_barrier_wire_contract.py`) carry the same expectations against the dependency. See the flagged `SHARED-INVARIANTS.md` conflict under FOUND-01 for the mechanism change itself.

> **FOUND-03 was withdrawn outright by Phase 37.1 (D-06), 2026-08-24 — it is the one requirement this project has deleted rather than amended.** It required a route registry placing every registered route in exactly one of three categories plus a startup/CI enumeration assertion, and `auth/registry.py`, the assertion and `tests/unit/test_route_registry.py` were all deleted; nothing of it survives to amend. The fail-closed property its first two conditions protected is now obtained **structurally** instead of by assertion — the router a route is registered on *is* its declaration, so there is no second table left to disagree with, and `tests/unit/test_app_wiring.py::TestEveryRouteIsAuthenticated` asserts the property directly over `app.routes` (negative-controlled against an injected undeclared route). What was genuinely lost: the closed provider-callback category, flagged forward to phases 43 and 44 under APPLEHOOK-02 and PLAYHOOK-03. The conflict this creates with `SHARED-INVARIANTS.md` is flagged under FOUND-01.

- [ ] **FOUND-04**: One shared error-registry module owns the single client-visible response shape, statuses, copy, and exception handlers; within an error class the body, status, and copy are identical across every triggering branch
- [ ] **FOUND-05** — **WITHDRAWN.** As written: an audit writer emits exactly one durable `audit.auth_events` row per on-path attempt before the response returns, with redacted `details` and an HMAC-SHA-256 `actor_subject_hash` carrying its key version
  > **Withdrawn by Phase 37.1 (D-01), 2026-08-24.** `auth/audit.py`, the `AuditWriter`, `build_details`, `redact`, the `AuthEvent` model and all five call sites were deleted together with the table. **No auth audit row is written anywhere, on any path** — the requirement is not merely unmet, its subject no longer exists, so it is withdrawn rather than reworded. The developer's judgement, consistent with `AGENTS.md`: auditing every auth attempt to a dedicated Postgres schema is over-engineering for a pre-launch sub-$5/month grammar app; the subsystem was built because the specification mandates it, not because a threat model asked for it. One-way — restoring it means re-editing the single initial migration and rebuilding roughly 1,600 lines of code and tests.
  >
  > **What compensates, and what does not.** The rejection log was deliberately kept (D-03) — it lives in `app/dependencies.py::_reject`, folded into the dependency that raises the rejection by Phase 37.2 (D-10), 2026-08-25 — and still emits the `auth_rejected` structured security-log event carrying the stable internal result, the bounded reason and the route template on **every** rejection. That log line is now the **only** record a rejection leaves. There is no durable queryable trail, no success record, no redacted `details`, and no HMAC `actor_subject_hash` — so nothing derives attack volume or reconstructs an attempt after the fact except the deployment's log pipeline.
  >
  > *Mechanism corrected by Phase 37.3 (D-02/D-06), 2026-08-26 — the compensating record still exists; only its shape changed.* `_reject` and the single `auth_rejected` event are both gone. Every rejection now raises an `AuthRejected` subclass, answered by one handler in `app/errors.py` that emits **one** WARNING per rejection, named for the exception class snake_cased, carrying the matched route's path template and whatever bounded scalars that class declares. There is no single greppable rejection event any more; that was accepted knowingly, no dashboard or log pipeline being deployed. The substance of the paragraph above is unchanged — a rejection still leaves exactly one structured log line and still leaves no durable row — so the conflict flagged below stands exactly as recorded.
  >
  > **FLAGGED CONFLICT against the binding specification — recorded, NOT resolved.** `SHARED-INVARIANTS.md` § "Audit" still mandates that *"Every on-path attempt writes exactly one durable `audit.auth_events` row for its terminal outcome, before the response returns"*, that *"Barrier rejections are first-class rows, never collapsed into a generic 401 log line"*, and that route metadata be *"readable BEFORE the barrier runs, so barrier rejections are audited with the operation set"* (`01-foundation.md §4` states the same obligation in phase form). That document binds every phase and wins over any conflicting phase brief, and **it has not been amended**. This project has knowingly diverged. Recorded here per the standing rule from `37-CONTEXT.md` so a later reader finds the divergence rather than discovering it — and so phases 38 and 46, which still owe a row, can see both sides of the question they inherit.
- [ ] **FOUND-06**: A `§7.1` provider-call budget seam meters outbound provider calls per request with plain in-process counters — the 3-attempt Firebase `getUser` retry budget, plus a helper that checks every applicable budget non-destructively from broadest to narrowest and charges them together only on success; exhaustion maps to internal `firebase_lookup_unavailable` → client `verification_temporarily_unavailable`. No `limits` dependency, no Redis/Valkey, no traffic rate limiting
- [ ] **FOUND-07**: A challenge store implements the claim/consume protocol that challenge-bearing operations depend on
- [x] **FOUND-08**: Adapter interfaces are defined as interfaces only — no store, device-check, or Firebase Admin implementations ship in this phase
  > **Amended by Phase 37.2 (D-09), 2026-08-25 — delivered exactly as written by Phase 35 and true until this date; what survives is the one seam the live code consumes.** Eight zero-consumer adapter types were deleted — `StoreAdapter`, `VendorProofAdapter`, `VerifiedNotification`, `VerifiedTransaction`, `StoreState`, `ClaimKind`, `DeviceBitState` and `RevocationOutcome` — together with `FirebaseAdminAdapter`'s two unconsumed Protocol methods, `verify_id_token` and `revoke_refresh_tokens`. Nothing regressed on the way out: every one of them had zero implementations and zero callers, so no behavior left with them. What remains in `auth/adapters.py` is the **providerData** surface the create-user flow actually calls — `ProviderDataOutcome`, `ProviderDataEntry`, `ProviderDataResult`, and a one-method `FirebaseAdminAdapter` carrying `get_user_provider_data`. `tests/unit/test_adapter_interfaces.py::TestNoProviderDependency` still holds: that seam imports no `firebase_admin`.
  >
  > **Flagged forward to phases 43, 44, 45 and 46 — the replacement is deliberately NOT designed here.** Each of those phases defines its adapter interface **beside its first implementation**, the same treatment Phase 37.1 gave the provider-callback category and for the same reason: designing a seam from outside the phase that owns it is how twelve unconsumed Protocols came to exist in the first place. The requirement's own principle still binds anything those phases declare ahead of building it — an interface ships with no implementation behind it in the phase that only declares it. APPLEHOOK-01, PLAYHOOK-02, RESTORE-01 and SIGNOUT-01 each carry the flag.
  >
  > **Amended by Phase 37.3 (D-09/D-19), 2026-08-26 — the surviving providerData surface named above was true until this date, and has now itself been replaced.** `ProviderDataOutcome`, `ProviderDataEntry` and `ProviderDataResult` are deleted. The seam carries **one** immutable value type, `VerifiedProviderIdentity(provider, provider_uid, email)`, frozen and slotted, and the read **raises** rather than returning an outcome to be translated: a `ProviderLookupError` hierarchy — `UserNotFound` (→ `AUTH_REQUIRED`), `Unavailable` (→ `VERIFICATION_TEMPORARILY_UNAVAILABLE`) and `NotLinked` (→ `OPERATION_NOT_ALLOWED`) — each carrying its own `error_class` and answered by one FastAPI handler. Classification and the email-copy rule moved inline into `firebase.py::_read`, behind the seam, so they live in exactly one place. `FirebaseAdminAdapter` is still the one-method Protocol; only its return type changed.
  >
  > **The requirement's actual content is still met, and that is what was checked.** `tests/unit/test_adapter_interfaces.py::TestNoProviderDependency` still holds: `auth/adapters.py` imports no `firebase_admin` and no provider SDK of any kind. **No client-visible behaviour changed** — every status, error class and body is byte-identical, gated by an unedited `tests/e2e/test_admission.py` and by a `tests/unit/test_create_user_precedence.py` carrying zero edits to any status code or body literal. FOUND-08 stays satisfied and is **not** unchecked.
  >
  > **The forward flag to phases 43–46 is carried unchanged**, with one addition from D-12: `AuthEventResult` — the 44-member internal outcome enum those phases' briefs reference — was deleted entirely by this phase. Phases 43, 44, 45 and 46 name their outcomes as **exception classes** in the `AuthRejected` family rather than re-growing an outcome enum, and they still define each adapter interface beside its first implementation.

> **FOUND-09 is deferred to v2.1** per D-08 — see Future Requirements below. Nothing in `k8s/` is touched by Phase 35.

> Phase 35 ends with a **booting** application (D-14): the model layer is repaired against the v2.0 schema, so imports and lifespan run at real startup against the real router. Chat and quota routes still fail at runtime until Phase 36 rewires them onto the grant model (D-15).
>
> *Amended by Phase 37.1 (D-06), 2026-08-24: this note also named the `§2.3` enumeration assertion running at real startup. That assertion was deleted with the route registry. The boot-clean half of D-14 is unchanged and still holds.*

### REBIND — Phase 36 (`01-foundation.md §8`)

- [x] **REBIND-01**: Partition membership is declared for every pre-existing route — `GET /health/ready` public; `GET /`, `GET /examples`, and the `/chats` family authenticated — and no route can sit outside its declared partition
  > **Enumeration half amended by Phase 37.1 (D-06), 2026-08-24 — now satisfied structurally rather than by assertion.** "The enumeration assertion passes in both directions" described set equality between a parallel declaration table and the live router, and the whole failure class it guarded was that table drifting. Membership is now declared once, by which router a route is registered on, so the two cannot disagree — there is no second table. `tests/unit/test_app_wiring.py::TestEveryRouteIsAuthenticated` asserts the property directly over `app.routes`: the public allowlist is exactly `{/health/ready}` and every other `APIRoute` declares the auth dependency. **Membership itself is unchanged** — the same eight routes sit in the same partitions, and no route changed its authentication status.
- [x] **REBIND-02**: These routes are off the audited attempt path and write no `audit.auth_events` row ever; rejections keep their internal result in the structured security log (the hand-rolled `RejectionCounter` metric was removed — see D-15 below; rejection rate is derived from the log by the deployment's log pipeline, not by a counter subsystem the service maintains itself)
  > **Audit half became *trivially* true — Phase 37.1 (D-01), 2026-08-24 — so it is kept, not withdrawn.** "Write no `audit.auth_events` row ever" still holds, but now because *no route anywhere* writes one and the table itself is gone, not because these routes sit off a path that still exists. The statement is not falsified; it has simply stopped discriminating between routes.
  >
  > **The substantive half survives intact and is now load-bearing.** Rejections keep their stable internal result in the structured security log because D-03 deliberately kept the rejection log — `app/dependencies.py::_reject` since Phase 37.2 (D-10), 2026-08-25 — the requirement this one already depended on. After D-01 that log event is the only record of a rejection anywhere in the system, which is exactly the argument D-03 made for keeping it.
- [ ] **REBIND-03**: Auth rejections on these routes surface through the shared error taxonomy and response shape, while their existing non-auth business error contracts are unchanged
- **REBIND-04** — **Void.** The named `quota_checked_request` admission entry it required no longer exists: Phase 35 D-05 deletes backend rate limiting from the product. REBIND-05's grant resolution, lock order, and lazy rollover are unaffected.
- [x] **REBIND-05**: The quota flow resolves one effective grant under the shared predicate, locks grant-then-usage in ascending grant id, fails closed on a missing usage row, performs lazy monthly rollover in the same locked transaction, and never lets `remaining` go negative
- [x] **REBIND-06**: The application starts and every pre-existing route behaves as it did in v1.6, apart from auth rejections now using the shared error classes

### CREATE — Phase 37 (`02-create-user.md`) — `POST /auth/create-user`

- [x] **CREATE-01**: Pre-auth admission is a closed, enumerated set of exactly two routes — `POST /auth/challenge` and `POST /auth/create-user`; every other route rejects an unlinked caller with `preauth_identity_not_allowed`
  > **Amended by Phase 37.2 (D-01/D-03), 2026-08-25 — the count changed from one route to two; the substance did not.** As written this read *"The endpoint is the only pre-auth-callable route"*, and it was true until this date. Challenge issuance moved out of `POST /auth/create-user`'s prepare mode onto its own `POST /auth/challenge` route, and that route **must** be pre-auth-callable: an unlinked caller needs a challenge in order to create an account at all, so demanding a link first would make account creation unreachable. What this requirement protects is unchanged — pre-auth admission is still a **closed** set, still **enumerated** in one place, and every route outside it still rejects an unlinked caller with `preauth_identity_not_allowed`. Neither route is exempt from *authentication*: both still resolve the request context, which is why an already-linked caller is owed a 409 rather than silence.
  >
  > **The enforcement point is `tests/unit/test_app_wiring.py`'s `PREAUTH_CALLABLE_PATHS` literal** — today exactly `{"/auth/create-user", "/auth/challenge"}`. It is deliberately hand-maintained rather than derived from the routers, so widening the set is a visible edit to a two-element literal that a reviewer meets in the diff. A third pre-auth-callable route added without touching it fails `TestEveryRouteIsAuthenticated::test_every_route_but_the_two_exemptions_requires_a_linked_identity`, so a later phase widening this set walks into both a written statement and a failing test rather than neither.
  >
  > **FLAGGED CONFLICT against the binding specification — recorded, NOT resolved.** `SHARED-INVARIANTS.md` § "Wire contract" reads *"Exactly one configured Firebase integration; every Admin call goes through the client selected by the request-verified issuer. No ambient, default, global, or fallback client exists; selection fails closed, and an issuer mismatch rejects at the barrier before any Admin work."* That document binds every phase, wins over any conflicting phase brief, and **it has not been amended**. This project has knowingly diverged at the **credential** layer: Phase 37.2 (D-06/D-08) deleted the explicit service-account credential branch, so the Admin app is now built from **Application Default Credentials** — ambient by definition, discovered from the environment, and in a developer's shell capable of silently resolving to that developer's own `gcloud` user credentials. That last property is precisely why Phase 37 D-08 rejected ADC, and **Phase 37 D-08 is superseded** by the developer's directive.
  >
  > **The reasoning, written down so a later reader can re-examine it rather than rediscover it:** production runs on GKE, where Application Default Credentials means Workload Identity — no key material at rest, nothing to rotate, nothing to leak — which is strictly better than the mounted service-account key the deleted branch loaded. Maintaining a parallel credential path purely to satisfy the letter of the rule is not justified by this product's threat model, a pre-launch sub-$5/month grammar app (`AGENTS.md`). **What is unchanged is the named-app-per-issuer discipline:** `build_admin_apps` still builds one named Admin app per configured issuer and never a `[DEFAULT]` app, every Admin call still goes through the client the request-verified issuer selects, and selection still fails closed — so the no-ambient-***client*** rule is still satisfied at the app-selection layer. The divergence is confined to where that client's credential comes from. Recorded here per the standing rule from `37-CONTEXT.md` — conflicts against `SHARED-INVARIANTS.md` are flagged, never silently resolved.
- [x] **CREATE-02**: The operation has both a prepare phase and a completion phase, partitioned by route — `POST /auth/challenge` issues the challenge, `POST /auth/create-user` completes against it
  > **Amended by Phase 37.2 (D-01/D-03/D-05), 2026-08-25 — the partition mechanism changed; both phases still exist, so this is amended rather than retired.** As written it read *"The endpoint implements both prepare mode and completion mode, partitioned by the mode signal"*. Deleted: the `?challenge=true` query-parameter signal, `auth/modesignal.py` and its `classify_mode_signal`, the `get_raw_query_string` dependency, and the `_prepare` handler branch. Replacing them: **one route per phase**. `POST /auth/create-user` now parses no query string, dispatches on no mode, and reads only its body.
  >
  > **The substance survives intact.** Both phases still exist, both are still challenge-bearing, and their order is still enforced — completion still requires a handle the prepare phase issued, and `tests/unit/test_create_user_precedence.py` still pins the rejection precedence below the challenge lookup with **zero** edits to any status code or body literal. What a route cannot express that a query parameter could is an *ambiguous* mode — two signals, neither signal, a non-`true` value — so the e2e cases guarding that ambiguity were deleted rather than moved: the ambiguity is no longer expressible at all.
  >
  > **Two status codes moved, both sanctioned as part of the split.** A malformed or unusable `challenge_id` is now the framework's `422 validation_error` rather than a hand-rolled `400 invalid_request` (D-04) — the `Any`-typed field existed only to route unusable handles into the mode signal's 400, and died with it. An already-linked caller now hears `409 identity_already_linked` at **completion**, raised by the in-transaction constraint conflict, instead of from a best-effort racy pre-check at prepare (D-03); the accepted consequence is that such a caller spends a challenge row and one Firebase lookup before hearing it. No other status code in the operation moved.
- [x] **CREATE-03**: The creation transaction atomically produces one `core.users` row, exactly one ACTIVE `core.external_identities` row, and the per-store purchase-attribution tokens — never a partial account
- [x] **CREATE-04**: Concurrent create-user attempts for the same `(issuer, subject)` never produce duplicate accounts; the losing caller reconciles through `POST /auth/sync`

### SYNC — Phase 38 (`03-sync.md`) — `POST /auth/sync`

- [ ] **SYNC-01**: The endpoint returns the effective grant, `current_period`, `monthly_used`, and stored `identity_provider`, all derived from one captured evaluation time
- [ ] **SYNC-02**: The endpoint is strictly read-only — no rollover, no grant-row flip, no invariant repair, no profile write
- [ ] **SYNC-03** — **BLOCKED: requires a mechanism Phase 37.1 deleted. Phase 38 must decide.** As written: the endpoint writes exactly one `audit.auth_events` row with `operation='sync'` per attempt despite mutating nothing, admission rejections included
  > **Flagged forward to Phase 38 by Phase 37.1 (D-01/D-12), 2026-08-24 — recorded, NOT resolved here.** The `audit.auth_events` table, the writer and every call site were deleted before this phase was built, so this requirement's mechanism does not exist. It is neither deleted nor quietly reworded: deleting it would hide an obligation the phase actually owes, and rewording it would decide Phase 38's design from outside the phase.
  >
  > **Phase 38 owns the decision and must make it explicitly, choosing one:** **(a)** rebuild a durable record for `operation='sync'`, accepting that this reintroduces the subsystem D-01 removed and reopens the cost argument that removed it; or **(b)** drop the durable-row obligation and satisfy the intent with the structured log — the rejection log in `app/dependencies.py::_reject` already covers the rejection arm, so only a success event would be new. Note what is actually at stake here: SYNC-02 makes this endpoint strictly read-only, so the row was never a mutation record — it was attempt telemetry, which is the cheaper of the two cases. See the flagged `SHARED-INVARIANTS.md` conflict under FOUND-05: the binding specification still mandates the row.

### PROF — Phase 39 (`04-users-me.md`) — `GET /users/me`

- [ ] **PROF-01**: The endpoint returns profile fields, the stored `identity_provider`, and per-store purchase-attribution tokens unconditionally for every store provider, with no platform or client-signal branching
- [ ] **PROF-02**: The endpoint is off the audited attempt path and writes no `audit.auth_events` row ever; rejections keep their stable internal result in the structured security log instead
  > **Amended by Phase 37.1 (D-01/D-03), 2026-08-24 — both clauses, for different reasons.** The **audit clause became *trivially* true**: no route anywhere writes an auth audit row and the table is gone, so it is kept rather than withdrawn, exactly as REBIND-02's matching clause was. The **counter clause was already false before this phase** — Phase 36 D-15 removed the hand-rolled `RejectionCounter`, and REBIND-02 records that rejection rate is derived from the log by the deployment's log pipeline. It has been reworded to name what actually exists: the `auth_rejected` event, emitted by `app/dependencies.py::_reject` since Phase 37.2 (D-10), 2026-08-25.
  >
  > **Consequence: Phase 39 inherits no obligation to build either subsystem** — not an audit writer, not a counter. Correcting the stale counter clause now is the point of saying so; left as written it would have read as a standing instruction to build a metric this project deliberately removed.

### UPGRADE — Phase 40 (`05-upgrade-anonymous.md`) — `POST /auth/upgrade-anonymous`

- [ ] **UPGRADE-01**: The endpoint records the client-side same-Firebase-UID `linkWithCredential` upgrade by flipping the existing `core.external_identities` row's provider in place
- [ ] **UPGRADE-02**: The endpoint is challenge-bearing with prepare and completion modes, callable only by an authenticated linked identity

### ANONGRANT — Phase 41 (`06-claim-anonymous-grant.md`) — `POST /auth/claim-anonymous-grant`

- [ ] **ANONGRANT-01**: The endpoint is the only operation that may create a `core.access_grants` row with `source='anonymous_device_grant'`, across the prepare/completion mode partition with a server-determined branch
- [ ] **ANONGRANT-02**: The grant transaction honors the fixed global lock order — grant rows `FOR UPDATE` ascending by id, then their `core.user_monthly_usage` rows — with no provider or network call while a lock is held
- [ ] **ANONGRANT-03**: The one-free-grant-per-account rule is enforced here; no grant row, free credit, or usage row is created as a side effect of any other path

### REGGRANT — Phase 42 (`07-claim-registered-grant.md`) — `POST /auth/claim-registered-grant`

- [ ] **REGGRANT-01**: The endpoint is the only creator of `source='registered_account_grant'` rows, across prepare and completion modes
- [ ] **REGGRANT-02**: Supersession conversion of an active anonymous device grant happens inside one transaction under the same fixed global lock order, never leaving two active grants
- [ ] **REGGRANT-03**: The one-free-grant-per-account interplay with an existing anonymous device grant resolves without double-allocating entitlement

### APPLEHOOK — Phase 43 (`08-webhook-app-store.md`) — `POST /webhooks/app-store`

- [ ] **APPLEHOOK-01**: The endpoint ingests Apple App Store Server Notifications outside the auth dependency, authenticated solely by verifying Apple's signed `signedPayload` JWS
  > **Adapter seam flagged forward by Phase 37.2 (D-09), 2026-08-25 — the loss is recorded; the replacement is not designed here.** `StoreAdapter`, `VerifiedNotification`, `VerifiedTransaction` and `StoreState` — the store-ingestion Protocols Phase 35 declared under FOUND-08 — were deleted as zero-consumer code before this phase exists. Nothing regressed: they had no implementations and no callers. Phase 43 defines its store adapter interface **beside its first implementation** rather than inheriting a declared-only seam, the same treatment Phase 37.1 gave the provider-callback category under APPLEHOOK-02.
- [ ] **APPLEHOOK-02** — **The category machinery this names was deleted by Phase 37.1. Phase 43 must answer it.** As written: the route is enumerated individually by exact path in the closed provider-callback category — never by wildcard or prefix, never on the public allowlist
  > **Flagged forward to Phase 43 by Phase 37.1 (D-06/D-10/D-12), 2026-08-24. The loss is recorded; the replacement is explicitly NOT designed here.** `Category`, `RouteMetadata`, `VERIFIERS` and `NamedVerifier` were deleted with the route registry, before this phase exists. Nothing regressed on the way out — `VERIFIERS` had no members — but **the control this requirement names is real**: individual exact-path enumeration is what stops a wildcard or prefix accidentally admitting an unauthenticated route, and `SHARED-INVARIANTS.md` § "Global deletions" still forbids wildcard or path-prefix provider-callback membership. The prohibition binds; only the machinery that enforced it is gone.
  >
  > **A pointer, not a design:** under D-08 the natural shape is a dedicated `APIRouter` carrying a named-verifier dependency, whose membership is then simply the set of routes registered on it. Phase 43 evaluates that on its own terms and is free to reject it. This phase adds **no** requirement describing a replacement mechanism — designing the provider-callback seam from outside the phase that owns it is how the deleted registry got built in the first place. APPLEHOOK-01's "outside the barrier" was reworded to "outside the auth dependency" in the same pass; same mechanism change, no substantive difference.

### PLAYHOOK — Phase 44 (`09-webhook-google-play-rtdn.md`) — `POST /webhooks/google-play/rtdn`

- [ ] **PLAYHOOK-01**: The endpoint ingests Google Play RTDN via a Cloud Pub/Sub push subscription, authenticated solely by backend verification of Google's signed OIDC push token
- [ ] **PLAYHOOK-02**: The endpoint reuses the shared store-ingestion module owned by Phase 43 rather than forking it
  > **Adapter seam flagged forward by Phase 37.2 (D-09), 2026-08-25.** The store-ingestion Protocols Phase 35 declared under FOUND-08 were deleted as zero-consumer code before this phase exists. Phase 44 inherits **Phase 43's** adapter interface along with the shared module this requirement already binds it to, and defines no second store seam of its own — the same argument PLAYHOOK-03 makes about competing partition mechanisms applies to competing adapter seams.
- [ ] **PLAYHOOK-03** — **The category machinery this names was deleted by Phase 37.1. Phase 44 must answer it.** As written: the route is enumerated individually by exact path in the closed provider-callback category, as the second and last member of that partition
  > **Flagged forward to Phase 44 by Phase 37.1 (D-06/D-12), 2026-08-24 — not redesigned here.** The same loss as APPLEHOOK-02: the closed-category machinery is gone before this phase exists. Phase 44 should inherit whatever Phase 43 defines rather than inventing a second answer — PLAYHOOK-02 already binds it to Phase 43's shared module, and two competing partition mechanisms would recreate exactly the drift the registry died of. The **"second and last member"** clause is the part that needs care: it requires the partition to be *countable*, so whatever Phase 43 builds must make its membership enumerable in one place. This phase adds no replacement mechanism.

### RESTORE — Phase 45 (`10-restore-subscription.md`) — `POST /auth/restore-subscription`

- [ ] **RESTORE-01**: The endpoint verifies a native store artifact (`restore_proof`) directly against Apple or Google and attaches verified paid-subscription entitlement through one of two server-determined branches
  > **Adapter seam flagged forward by Phase 37.2 (D-09), 2026-08-25.** `VendorProofAdapter`, `ClaimKind` and `DeviceBitState` — the native-artifact verification Protocols Phase 35 declared under FOUND-08 — were deleted as zero-consumer code before this phase exists. Nothing regressed: they had no implementations and no callers. Phase 45 defines its verification interface **beside its first implementation**.
- [ ] **RESTORE-02**: The endpoint is a native-only surface; other surfaces receive `operation_not_allowed`

### SIGNOUT — Phase 46 (`11-sign-out-all.md`) — `POST /auth/sign-out-all`

- [ ] **SIGNOUT-01**: The endpoint revokes the verified subject's Firebase refresh tokens through the issuer-selected Firebase Admin client, returning success only on Firebase-confirmed revocation
  > **Adapter seam flagged forward by Phase 37.2 (D-09), 2026-08-25.** `FirebaseAdminAdapter`'s `revoke_refresh_tokens` method and the `RevocationOutcome` type were deleted as zero-consumer code before this phase exists; the surviving one-method `FirebaseAdminAdapter` carries `get_user_provider_data` only. Phase 46 adds the revocation call **beside its first implementation**. **The rule this requirement states is untouched** — `build_admin_apps` still builds one named Admin app per configured issuer, never a `[DEFAULT]` one, and revocation still goes through the client the request-verified issuer selects. What did change is where that client's credential comes from: see the flagged credential conflict under CREATE-01.
- [ ] **SIGNOUT-02** — **Audit half BLOCKED: requires a mechanism Phase 37.1 deleted. Phase 46 must decide. Fail-closed half untouched and still binding.** As written: the endpoint is an audited state-changing operation writing exactly one `audit.auth_events` row; an indeterminate or failed revocation fails closed rather than reporting success
  > **Flagged forward to Phase 46 by Phase 37.1 (D-01/D-12), 2026-08-24 — recorded, NOT resolved here.** Only the audit half lost its mechanism. **The fail-closed half is unamended and fully binding**: an indeterminate or failed revocation must never report success, SIGNOUT-01 states the same rule independently, and `SHARED-INVARIANTS.md` § "Fail-closed defaults" binds it a third time.
  >
  > **Phase 46 owns the audit decision and must make it explicitly** — the same choice Phase 38 faces under SYNC-03 — but it must weigh it on this operation's own terms, because they are not the same case. This is a **state-changing** operation that fails closed on an indeterminate outcome: drop the durable-row obligation outright and a revocation that neither confirmed nor demonstrably failed leaves *nothing* behind recording that it was attempted, on the one endpoint whose whole purpose is revoking access. A read-only sync losing its attempt telemetry is a smaller loss than that. Rebuilding a record here does not require rebuilding the whole subsystem D-01 removed. See the flagged `SHARED-INVARIANTS.md` conflict under FOUND-05.

## Future Requirements

Tracked but deferred beyond v2.0.

### Gateway contract — deferred from Phase 35

- **FOUND-09**: The Envoy Gateway config forwards `Authorization` unchanged, injects no identity headers, pins `xff_num_trusted_hops`, overrides the shared 429 body, and the backend ignores every client- or proxy-supplied identity header (`01-foundation.md §9`). Deferred per Phase 35 D-08. Accepted consequences for v2.0: only the v1.6 chart's rate limiting ships, unverified against `§9`; Envoy's 429s keep their empty body, which does not satisfy the client error contract; and `xff_num_trusted_hops` stays unpinned. No backend correctness depends on this — `§9` is explicit that the backend is the sole authoritative verifier.
  > **Third accepted consequence amended by Phase 37.1 (D-01), 2026-08-24.** It used to end *"so the client address recorded in audit `details` is trusted rather than proven"*. There is no audit `details` any more, and `RequestContext` no longer carries a client-IP bucket field at all, so **the backend records no client address anywhere** — trusted or otherwise. The unpinned hop count is now purely a gateway-side concern, which narrows what v2.1 owes here rather than widening it.

### Observability

- **OBS-01**: Proactive quota warnings via an `X-RateLimit-Remaining` response header
- **OBS-02**: Grace-period transparency in `GET /users/me` — `core.subscriptions.status` models `grace_period` but `04-users-me.md` does not surface it
- **OBS-03**: Webhook retry reconciliation via App Store Server API polling
- **OBS-04**: Startup exhaustiveness check for quota config (QUOTA-06)

## Out of Scope

Explicitly excluded. `SHARED-INVARIANTS.md` "Global deletions" binds every phase — none of these may be built in any phase.

| Feature | Reason |
|---------|--------|
| Backend-minted tokens or sessions | Authentication is per-request via the Firebase ID token only; no cookie, no secondary auth state, no generation counter |
| `checkRevoked` / per-request revocation checks | Already-minted ID tokens are never force-expired |
| `promo` grant source | Deleted from the enum and from every rule, example, and remediation that referenced it |
| Scheduled cleanup, purge, reconciliation, or background-healer jobs | Indefinite retention; no recovery-scan of challenge rows, empty accounts, or provider state |
| Device-fingerprint or device-check components in rate-limit keys | Excluded in any form |
| Claim-header authentication or header-derived identity | The gateway injects no identity headers and the backend ignores every client/proxy identity header |
| Distributed locks, leases, or multi-phase-commit machinery | Short database-only transactions under a fixed global lock order suffice |
| Wildcard or path-prefix provider-callback membership | Callback routes are named individually by exact path, added only by a spec change |
| Identity row deletion | Rows are tombstones; retirement is permanent and no path reverses it |
| Data migration, backfill, compatibility shims, dual-write windows, deprecated aliases | Pre-launch database with disposable data |
| `display_name` population from auth context | Never sourced from the Admin record or token claims |
| Incremental migration files during v2.0 | One initial migration, renamed and replaced |
| Multi-IdP support | Exactly one configured Firebase integration; store providers are not IdPs |
| Admin user management | Own profile only (`GET /users/me`) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCHEMA-01 … SCHEMA-08 | Phase 34 | Complete (SCHEMA-06 withdrawn by Phase 37.1) |
| FOUND-01 … FOUND-08 | Phase 35 | Pending (FOUND-01/02 amended; FOUND-05 withdrawn; one further requirement deleted outright — all by Phase 37.1, see the FOUND block; FOUND-08 amended and flagged forward to phases 43–46 by Phase 37.2, and **amended again by Phase 37.3** — the providerData result types became one raised hierarchy; FOUND-05's compensating-log mechanism corrected by Phase 37.3) |
| FOUND-09 | v2.1 backlog | Deferred (D-08) |
| REBIND-01 … REBIND-06 | Phase 36 | Complete (REBIND-03 partial by design, REBIND-04 void; REBIND-01/02 amended by Phase 37.1) |
| CREATE-01 … CREATE-04 | Phase 37 | Complete (CREATE-01/02 amended by Phase 37.2 — pre-auth admission is two enumerated routes, and the prepare/completion partition is by route; the credential conflict is flagged under CREATE-01) |
| SYNC-01 … SYNC-03 | Phase 38 | Pending (SYNC-03 blocked on a Phase 38 decision — Phase 37.1) |
| PROF-01 … PROF-02 | Phase 39 | Pending (PROF-02 amended by Phase 37.1) |
| UPGRADE-01 … UPGRADE-02 | Phase 40 | Pending |
| ANONGRANT-01 … ANONGRANT-03 | Phase 41 | Pending |
| REGGRANT-01 … REGGRANT-03 | Phase 42 | Pending |
| APPLEHOOK-01 … APPLEHOOK-02 | Phase 43 | Pending (APPLEHOOK-02 flagged forward to its own phase — Phase 37.1; the store adapter seam flagged forward under APPLEHOOK-01 — Phase 37.2) |
| PLAYHOOK-01 … PLAYHOOK-03 | Phase 44 | Pending (PLAYHOOK-03 flagged forward to its own phase — Phase 37.1; the store adapter seam inherited from Phase 43 under PLAYHOOK-02 — Phase 37.2) |
| RESTORE-01 … RESTORE-02 | Phase 45 | Pending (the vendor-proof adapter seam flagged forward under RESTORE-01 — Phase 37.2) |
| SIGNOUT-01 … SIGNOUT-02 | Phase 46 | Pending (SIGNOUT-02's audit half blocked on a Phase 46 decision — Phase 37.1; the revocation adapter seam flagged forward under SIGNOUT-01 — Phase 37.2) |

**Coverage:**

- v2.0 requirements: 48 total (49 defined; one deleted outright by Phase 37.1)
- Mapped to phases: 48
- Unmapped: 0 ✓
- Prefixes spanning more than one phase: 0 ✓

**Standing after Phase 37.1's two deletions (2026-08-24), Phase 37.2's auth-module simplification (2026-08-25) and Phase 37.3's returned-rejection refactor (2026-08-26):**

| Treatment | Requirements |
|-----------|--------------|
| Deleted outright | one FOUND requirement — the route registry and its enumeration assertion (see the FOUND block) |
| Withdrawn, subject no longer exists | SCHEMA-06, FOUND-05 |
| Amended, substance intact | Phase 37.1: FOUND-01, FOUND-02, REBIND-01, REBIND-02, PROF-02, APPLEHOOK-01, FOUND-09. Phase 37.2: **CREATE-01**, **CREATE-02**, **FOUND-08**. Phase 37.3: **FOUND-08** again |
| Flagged forward — the owning phase decides | Phase 37.1: SYNC-03 (38), SIGNOUT-02 (46), APPLEHOOK-02 (43), PLAYHOOK-03 (44). Phase 37.2: FOUND-08's adapter seam → 43, 44, 45 and 46, each defining its interface beside its first implementation, carried unchanged by Phase 37.3 with D-12's addition that those phases name their outcomes as exception classes rather than re-growing an outcome enum |
| Flagged conflicts against `SHARED-INVARIANTS.md`, unresolved | 37.1 D-01 vs § "Audit" (under FOUND-05); 37.1 D-06 vs § "The barrier" (under FOUND-01); **37.2 D-08 — Application Default Credentials vs § "Wire contract"'s no-ambient-credential rule (under CREATE-01)** |

---
*Requirements defined: 2026-08-19*
*Last updated: 2026-08-26 — amended by Phase 37.3 plan 04 for the returned-rejection refactor: FOUND-08's providerData surface replaced by `VerifiedProviderIdentity` and a raised `ProviderLookupError` hierarchy, and FOUND-05's compensating-log mechanism corrected*
