# Requirements: ns-api-gateway — v2.0 Authentication & Entitlements

**Defined:** 2026-08-19
**Core Value:** The analysis pipeline must work reliably — correct LLM invocation, proper resilience under load, and safe per-user data isolation.

**Specification:** `/home/init/native-speaker/specs/auth-refactor-phases/` — one file per phase. `SHARED-INVARIANTS.md` binds every phase and wins over any phase brief on conflict.

**Organizing principle:** one phase = one REQ-ID prefix, 1:1. Endpoint phases implement exactly one endpoint. No requirement spans phases.

**Phase map:** 34 SCHEMA · 35 FOUND · 36 REBIND · 37 CREATE · 38 SYNC · 39 PROF · 40 UPGRADE · 41 ANONGRANT · 42 REGGRANT · 43 APPLEHOOK · 44 PLAYHOOK · 45 RESTORE · 46 SIGNOUT

## v2.0 Requirements

### SCHEMA — Phase 34 (`00-schema.md`)

- [x] **SCHEMA-01**: The single initial migration `migrations/20260818_01_initial-release.sql` replaces the deleted prior migration and creates the complete v2.0 schema in one apply against an empty database — no incremental migration files are added
  > **Upheld against a later conflicting decision (Phase 37, plan 37-01 Task 1, 2026-08-22).** `37-CONTEXT.md` D-13 called for "a new migration" to drop `core.auth_challenges.operation_variant`. That mechanism was rejected in favor of this requirement: the initial migration is **edited in place** and the disposable dev/test database is dropped and re-applied. SCHEMA-01 is unamended and `tests/schema/test_apply_rollback.py::test_exactly_one_sql_file` stays green unmodified. The consequence for any future v2.0 schema change is the same: edit in place, re-apply, never add a file.
- [x] **SCHEMA-02**: `core.users`, `core.external_identities`, and the `core.identity_provider` enum support `(issuer, subject)` → user resolution, with `identity_state` and permanently-retained tombstone rows
- [x] **SCHEMA-03**: `core.access_grants`, `core.access_tiers`, and `core.user_monthly_usage` enforce at most one active grant per user, with monthly usage keyed by grant id
- [x] **SCHEMA-04**: `core.subscriptions`, `core.store_purchases`, and `core.store_purchase_tokens` support both stores, with `product_entitled_subscription_id` as a STORED generated column over `('active','grace_period')`
- [x] **SCHEMA-05**: `core.auth_challenges` supports the claim/consume protocol for challenge-bearing operations
- [x] **SCHEMA-06**: `audit.auth_events` enforces the actor-field CHECK constraints and the `core.auth_operation` / `core.auth_event_result` enums in full
- [x] **SCHEMA-07**: Legacy structures are gone — `core.users.jwt_sub`, `core.users.subscription_plan`, `core.usage_monthly`, `core.subscription_events`, the `core.subscription_plan` enum, and the `promo` grant source
- [x] **SCHEMA-08**: Every acceptance check in `00-schema.md §10` passes against a freshly migrated database

### FOUND — Phase 35 (`01-foundation.md §1–§4, §6, §7`)

Shared machinery only. Rebinding the pre-existing routes is Phase 36.

> Scope narrowed by the Phase 35 discussion (`35-CONTEXT.md`): `§5` (backend rate-limit engine) is **deleted from the product** — Envoy Gateway is the sole request-rate enforcement point (D-05), overriding `SHARED-INVARIANTS.md` § Rate limits and `01-foundation.md §5`. `§9` (the Envoy contract) is **deferred to v2.1** (D-08). The `§7.1` provider-call budget seam survives as FOUND-06 (D-06).

- [x] **FOUND-01**: A mandatory, default-on pre-handler barrier is the only place JWT acceptance and identity resolution happen; it admits only `identity_state='active'` AND `users.active` exactly TRUE
- [ ] **FOUND-02**: The barrier enforces the exactly-one-Authorization wire contract — zero values, duplicate field instances, comma-joined values, multiple credentials, empty tokens, and trailing content all reject as `invalid_external_jwt`
- [ ] **FOUND-03**: A route registry places every registered route in exactly one of three categories (public allowlist, provider-callback by exact path, authenticated), and a startup/CI enumeration assertion fails when a route is in zero or multiple categories
- [ ] **FOUND-04**: One shared error-registry module owns the single client-visible response shape, statuses, copy, and exception handlers; within an error class the body, status, and copy are identical across every triggering branch
- [ ] **FOUND-05**: An audit writer emits exactly one durable `audit.auth_events` row per on-path attempt before the response returns, with redacted `details` and an HMAC-SHA-256 `actor_subject_hash` carrying its key version
- [ ] **FOUND-06**: A `§7.1` provider-call budget seam meters outbound provider calls per request with plain in-process counters — the 3-attempt Firebase `getUser` retry budget, plus a helper that checks every applicable budget non-destructively from broadest to narrowest and charges them together only on success; exhaustion maps to internal `firebase_lookup_unavailable` → client `verification_temporarily_unavailable`. No `limits` dependency, no Redis/Valkey, no traffic rate limiting
- [ ] **FOUND-07**: A challenge store implements the claim/consume protocol that challenge-bearing operations depend on
- [x] **FOUND-08**: Adapter interfaces are defined as interfaces only — no store, device-check, or Firebase Admin implementations ship in this phase

> **FOUND-09 is deferred to v2.1** per D-08 — see Future Requirements below. Nothing in `k8s/` is touched by Phase 35.

> Phase 35 ends with a **booting** application (D-14): the model layer is repaired against the v2.0 schema, so imports, lifespan, and the `§2.3` enumeration assertion all run at real startup against the real router. Chat and quota routes still fail at runtime until Phase 36 rewires them onto the grant model (D-15).

### REBIND — Phase 36 (`01-foundation.md §8`)

- [x] **REBIND-01**: Partition membership is declared for every pre-existing route — `GET /health/ready` public; `GET /`, `GET /examples`, and the `/chats` family authenticated — and the enumeration assertion passes in both directions
- [x] **REBIND-02**: These routes are off the audited attempt path and write no `audit.auth_events` row ever; rejections keep their internal result in the structured security log (the hand-rolled `RejectionCounter` metric was removed — see D-15 below; rejection rate is derived from the log by the deployment's log pipeline, not by a counter subsystem the service maintains itself)
- [ ] **REBIND-03**: Auth rejections on these routes surface through the shared error taxonomy and response shape, while their existing non-auth business error contracts are unchanged
- **REBIND-04** — **Void.** The named `quota_checked_request` admission entry it required no longer exists: Phase 35 D-05 deletes backend rate limiting from the product. REBIND-05's grant resolution, lock order, and lazy rollover are unaffected.
- [x] **REBIND-05**: The quota flow resolves one effective grant under the shared predicate, locks grant-then-usage in ascending grant id, fails closed on a missing usage row, performs lazy monthly rollover in the same locked transaction, and never lets `remaining` go negative
- [x] **REBIND-06**: The application starts and every pre-existing route behaves as it did in v1.6, apart from auth rejections now using the shared error classes

### CREATE — Phase 37 (`02-create-user.md`) — `POST /auth/create-user`

- [ ] **CREATE-01**: The endpoint is the only pre-auth-callable route; every other route rejects an unlinked caller with `preauth_identity_not_allowed`
- [ ] **CREATE-02**: The endpoint implements both prepare mode and completion mode, partitioned by the mode signal
- [ ] **CREATE-03**: The creation transaction atomically produces one `core.users` row, exactly one ACTIVE `core.external_identities` row, and the per-store purchase-attribution tokens — never a partial account
- [ ] **CREATE-04**: Concurrent create-user attempts for the same `(issuer, subject)` never produce duplicate accounts; the losing caller reconciles through `POST /auth/sync`

### SYNC — Phase 38 (`03-sync.md`) — `POST /auth/sync`

- [ ] **SYNC-01**: The endpoint returns the effective grant, `current_period`, `monthly_used`, and stored `identity_provider`, all derived from one captured evaluation time
- [ ] **SYNC-02**: The endpoint is strictly read-only — no rollover, no grant-row flip, no invariant repair, no profile write
- [ ] **SYNC-03**: The endpoint writes exactly one `audit.auth_events` row with `operation='sync'` per attempt despite mutating nothing, barrier rejections included

### PROF — Phase 39 (`04-users-me.md`) — `GET /users/me`

- [ ] **PROF-01**: The endpoint returns profile fields, the stored `identity_provider`, and per-store purchase-attribution tokens unconditionally for every store provider, with no platform or client-signal branching
- [ ] **PROF-02**: The endpoint is off the audited attempt path and writes no `audit.auth_events` row ever; rejections increment the bounded-cardinality counter metric instead

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

- [ ] **APPLEHOOK-01**: The endpoint ingests Apple App Store Server Notifications outside the barrier, authenticated solely by verifying Apple's signed `signedPayload` JWS
- [ ] **APPLEHOOK-02**: The route is enumerated individually by exact path in the closed provider-callback category — never by wildcard or prefix, never on the public allowlist

### PLAYHOOK — Phase 44 (`09-webhook-google-play-rtdn.md`) — `POST /webhooks/google-play/rtdn`

- [ ] **PLAYHOOK-01**: The endpoint ingests Google Play RTDN via a Cloud Pub/Sub push subscription, authenticated solely by backend verification of Google's signed OIDC push token
- [ ] **PLAYHOOK-02**: The endpoint reuses the shared store-ingestion module owned by Phase 43 rather than forking it
- [ ] **PLAYHOOK-03**: The route is enumerated individually by exact path in the closed provider-callback category, as the second and last member of that partition

### RESTORE — Phase 45 (`10-restore-subscription.md`) — `POST /auth/restore-subscription`

- [ ] **RESTORE-01**: The endpoint verifies a native store artifact (`restore_proof`) directly against Apple or Google and attaches verified paid-subscription entitlement through one of two server-determined branches
- [ ] **RESTORE-02**: The endpoint is a native-only surface; other surfaces receive `operation_not_allowed`

### SIGNOUT — Phase 46 (`11-sign-out-all.md`) — `POST /auth/sign-out-all`

- [ ] **SIGNOUT-01**: The endpoint revokes the verified subject's Firebase refresh tokens through the issuer-selected Firebase Admin client, returning success only on Firebase-confirmed revocation
- [ ] **SIGNOUT-02**: The endpoint is an audited state-changing operation writing exactly one `audit.auth_events` row; an indeterminate or failed revocation fails closed rather than reporting success

## Future Requirements

Tracked but deferred beyond v2.0.

### Gateway contract — deferred from Phase 35

- **FOUND-09**: The Envoy Gateway config forwards `Authorization` unchanged, injects no identity headers, pins `xff_num_trusted_hops`, overrides the shared 429 body, and the backend ignores every client- or proxy-supplied identity header (`01-foundation.md §9`). Deferred per Phase 35 D-08. Accepted consequences for v2.0: only the v1.6 chart's rate limiting ships, unverified against `§9`; Envoy's 429s keep their empty body, which does not satisfy the client error contract; and `xff_num_trusted_hops` stays unpinned, so the client address recorded in audit `details` is trusted rather than proven. No backend correctness depends on this — `§9` is explicit that the backend is the sole authoritative verifier.

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
| SCHEMA-01 … SCHEMA-08 | Phase 34 | Complete |
| FOUND-01 … FOUND-08 | Phase 35 | Pending |
| FOUND-09 | v2.1 backlog | Deferred (D-08) |
| REBIND-01 … REBIND-06 | Phase 36 | Complete (REBIND-03 partial by design, REBIND-04 void) |
| CREATE-01 … CREATE-04 | Phase 37 | Pending |
| SYNC-01 … SYNC-03 | Phase 38 | Pending |
| PROF-01 … PROF-02 | Phase 39 | Pending |
| UPGRADE-01 … UPGRADE-02 | Phase 40 | Pending |
| ANONGRANT-01 … ANONGRANT-03 | Phase 41 | Pending |
| REGGRANT-01 … REGGRANT-03 | Phase 42 | Pending |
| APPLEHOOK-01 … APPLEHOOK-02 | Phase 43 | Pending |
| PLAYHOOK-01 … PLAYHOOK-03 | Phase 44 | Pending |
| RESTORE-01 … RESTORE-02 | Phase 45 | Pending |
| SIGNOUT-01 … SIGNOUT-02 | Phase 46 | Pending |

**Coverage:**

- v2.0 requirements: 49 total
- Mapped to phases: 49
- Unmapped: 0 ✓
- Prefixes spanning more than one phase: 0 ✓

---
*Requirements defined: 2026-08-19*
*Last updated: 2026-08-19 after v2.0 milestone start*
