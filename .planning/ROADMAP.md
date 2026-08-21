# Roadmap: ns-api-gateway

## Milestones

- ✅ **v1.1 Security & Quality** — Phases 1-4 (shipped 2015-02-27)
- ✅ **v1.2 Cleanup & Tech Debt** — Phases 5-9 (shipped 2015-02-28)
- ✅ **v1.3 Feature Integration** — Phases 10-13 (shipped 2015-03-03)
- ✅ **v1.4 Incremental Improvements** — Phases 14-17 (shipped 2026-03-20)
- ✅ **v1.5 User Management & Subscriptions** — Phases 18-24 (shipped 2026-03-22)
- ✅ **v1.6 Schema Hardening** — Phases 25-33 (shipped 2026-03-26)
- ◆ **v2.0 Authentication & Entitlements** — Phases 34-46 (in progress)

## Phases

<details>
<summary>✅ v1.1 Security & Quality (Phases 1-4) — SHIPPED 2015-02-27</summary>

- [x] Phase 1: Exception Foundation (3/3 plans) — completed 2015-02-26
- [x] Phase 2: Auth Structure + LLM Errors (2/2 plans) — completed 2015-02-27
- [x] Phase 3: Validation + Security Tests (2/2 plans) — completed 2015-02-27
- [x] Phase 4: Exception Integration Completeness (1/1 plan) — completed 2015-02-27

Archive: `.planning/milestones/v1.1-ROADMAP.md`

</details>

<details>
<summary>✅ v1.2 Cleanup & Tech Debt (Phases 5-9) — SHIPPED 2015-02-28</summary>

- [x] Phase 5: Config Fix + Dead Code Removal (1/1 plan) — completed 2015-02-28
- [x] Phase 6: LLM Output Parsing Hardening (1/1 plan) — completed 2015-02-28
- [x] Phase 7: PEP8 Compliance (1/1 plan) — completed 2015-02-28
- [x] Phase 8: Resilience Layer Extraction (1/1 plan) — completed 2015-02-28
- [x] Phase 9: Health Endpoint Simplification (1/1 plan) — completed 2015-02-28

Archive: `.planning/milestones/v1.2-ROADMAP.md`

</details>

<details>
<summary>✅ v1.3 Feature Integration (Phases 10-13) — SHIPPED 2015-03-03</summary>

- [x] Phase 10: JWT Authentication (2/2 plans) — completed 2015-03-02
- [x] Phase 11: Error Contract Hardening (2/2 plans) — completed 2015-03-02
- [x] Phase 12: LLM Dependency Injection (2/2 plans) — completed 2015-03-02
- [x] Phase 13: Endpoint Unification (2/2 plans) — completed 2015-03-03

Archive: `.planning/milestones/v1.3-ROADMAP.md`

</details>

<details>
<summary>✅ v1.4 Incremental Improvements (Phases 14-17) — SHIPPED 2026-03-20</summary>

- [x] Phase 14: DB Query Optimization (2/2 plans) — completed 2015-03-04
- [x] Phase 15: Refactor Chats (8/8 plans) — completed 2026-03-16
- [x] Phase 16: Update Tests (4/4 plans) — completed 2026-03-17
- [x] Phase 17: Simplify Error Handling (1/1 plan) — completed 2026-03-19

Archive: `.planning/milestones/v1.4-ROADMAP.md`

</details>

<details>
<summary>✅ v1.5 User Management & Subscriptions (Phases 18-24) — SHIPPED 2026-03-22</summary>

- [x] Phase 18: Test Infrastructure Cleanup (1/1 plan) — completed 2026-03-20
- [x] Phase 19: Service Layer Refactoring (1/1 plan) — completed 2026-03-20
- [x] Phase 20: Structured Logging (1/1 plan) — completed 2026-03-20
- [x] Phase 21: User Management (3/3 plans) — completed 2026-03-20
- [x] Phase 22: Apple Subscription Integration (3/3 plans) — completed 2026-03-20
- [x] Phase 23: Envoy Gateway Rate Limiting (4/4 plans) — completed 2026-03-22
- [x] Phase 24: Migration Merge (2/2 plans) — completed 2026-03-22

Archive: `.planning/milestones/v1.5-ROADMAP.md`

</details>

<details>
<summary>✅ v1.6 Schema Hardening (Phases 25-33) — SHIPPED 2026-03-26</summary>

- [x] Phase 25: Config and Model Foundation (2/2 plans) — completed 2026-03-23
- [x] Phase 26: Service and Database Rewiring (2/2 plans) — completed 2026-03-23
- [x] Phase 27: Migration (1/1 plan) — completed 2026-03-24
- [x] Phase 28: Test Updates (1/1 plan) — completed 2026-03-24
- [x] Phase 29: Replace Raw SQL with ORM (1/1 plan) — completed 2026-03-24
- [x] Phase 30: E2E and Security Test Coverage (3/3 plans) — completed 2026-03-25
- [x] Phase 31: Move Quota Check to Dependency (2/2 plans) — completed 2026-03-25
- [x] Phase 32: Rewrite Models to Match Prompt Schema (3/3 plans) — completed 2026-03-26
- [x] Phase 33: Propagate quota_exceeded Rename (1/1 plan) — completed 2026-03-26

Archive: `.planning/milestones/v1.6-ROADMAP.md`

</details>

### ◆ v2.0 Authentication & Entitlements (Phases 34-46)

Spec: `/home/init/native-speaker/specs/auth-refactor-phases/`. One phase per spec file, except `01-foundation.md`, which splits into Phase 35 (machinery, §1–§4 + §6 + §7) and Phase 36 (pre-existing route rebinding, §8). `§5` is deleted from the product and `§9` is deferred to v2.1 — see Phase 35. `SHARED-INVARIANTS.md` binds every phase and overrides any conflicting phase brief — flag conflicts, never resolve them silently.

Each phase reads only its own spec file plus `SHARED-INVARIANTS.md` at plan time. The spec dir is ~90k tokens in total and is never loaded at once.

**Dependency graph:**

```
34 (schema) → 35 (foundation) → ┬─ 36 rebind pre-existing routes
                                ├─ 37 create-user ─┬─ 40 upgrade-anon ──┐
                                │                  ├─ 41 claim-anon ────┴─→ 42 claim-registered
                                │                  ├─ 38 sync    (soft 37)
                                │                  └─ 39 users/me (soft 37)
                                ├─ 43 app-store ──→ 44 google-play (soft 43)
                                ├─ 45 restore-subscription (needs 37, 43, 44)
                                └─ 46 sign-out-all
```

Phase 35 is the first **booting** app (D-14) — imports, lifespan, and the startup enumeration assertion all run. Phase 36 is the first **fully working** one, once the chat quota path is rewired onto the grant model.

#### Phase 34: Schema

**Goal:** Deliver the complete v2.0 auth schema in one apply against an empty database as `migrations/20260818_01_initial-release.sql`, which replaces the deleted `20260322_01_initial-release.sql`.
**Requirements:** SCHEMA-01 … SCHEMA-08
**Depends on:** nothing — root of the graph
**Plans:** 4/4 plans complete

Plans:
**Wave 1**

- [x] 34-01-PLAN.md — Provision a reachable, empty PostgreSQL 17 and gate the phase on it (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 34-02-PLAN.md — Tracer: the single v2.0 initial migration, applied and rolled back end-to-end; close CONFLICT-1 in the three docs naming the old file (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 34-03-PLAN.md — tests/schema harness, apply/rollback proof, and the exact-set object inventory captured from real PostgreSQL 17 (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 34-04-PLAN.md — Constraint conformance: every §10 rejection case, the four valid anti-abuse tuples, and D-16 (wave 4)

**Success criteria:**

1. A fresh `pogo apply` against an empty database produces the full schema with no error and no second migration file present
2. `(issuer, subject)` → `core.users` resolution works through `core.external_identities`, with `identity_state` and tombstone retention expressible
3. At most one `status='active'` grant per user is enforceable, and `core.user_monthly_usage` is keyed by grant id
4. `audit.auth_events` rejects a row with partial actor fields per its CHECK constraints
5. Every acceptance check in `00-schema.md §10` passes

> Application code referencing dropped columns breaks at this commit. Expected — see Phase 36.

#### Phase 35: Foundation

**Goal:** Build the shared machinery every later phase calls and none rebuilds — barrier, route registry, error registry, audit writer, provider-call budget seam, challenge store, adapter interfaces — and repair the model layer so the application boots and the enumeration assertion runs for real.
**Requirements:** FOUND-01 … FOUND-08
**Depends on:** 34
**Plans:** 9/11 plans executed across 10 waves

Plans:
**Wave 1**

- [x] 35-01-PLAN.md — Tracer: unauthenticated request rejected end-to-end at real startup

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 35-02-PLAN.md — Error registry completion (D-09/D-11/D-12) and the §1.2 verification module

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 35-03-PLAN.md — Typed identity context (§1.4) and the fail-loudly `Depends()` accessors
- [x] 35-07-PLAN.md — Provider-call budget seam and adapter interfaces (zero implementations)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 35-04-PLAN.md — Dead-surface deletion (D-16) in one atomic sweep, and the suite back to green

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 35-05-PLAN.md — v2.0 model layer repair and removal of the Apple/quota config surface

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 35-06-PLAN.md — Barrier identity resolution, admission matrix, telemetry, and the e2e harness

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 35-08-PLAN.md — Shared HMAC keyring and its fail-closed startup policy

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 35-09-PLAN.md — `audit.auth_events` writer: two modes, details shape, redaction, barrier hook

**Wave 9** *(blocked on Wave 8 completion)*

- [ ] 35-10-PLAN.md — Challenge store, claim/consume atomicity, and the §6.5 mode-signal check

**Wave 10** *(blocked on Wave 9 completion)*

- [ ] 35-11-PLAN.md — Publish the `auth/` seam, restore e2e coverage, gate the suite green, COVERAGE.md

**Success criteria:**

1. The route-enumeration assertion passes, and a route declared in zero or in two categories fails it
2. Zero, duplicate, comma-joined, empty, and trailing-content Authorization values each reject as `auth_required` with identical body, status, and copy
3. The barrier admits only `identity_state='active'` AND `users.active` TRUE; every other combination rejects with nothing falling through to pre-auth
4. A barrier rejection produces exactly one `audit.auth_events` row with all three actor fields NULL and a bounded reason
5. The application boots clean — `nativespeaker.api` imports, the lifespan runs, and the `§2.3` enumeration assertion executes at real startup against the real router

> Scope changed by the Phase 35 discussion (`35-CONTEXT.md`): `§5` backend rate limiting is deleted from the product (D-05, Envoy Gateway owns request-rate enforcement) and `§9` the Envoy contract is deferred to v2.1 (D-08). Per D-14/D-15 the phase now ends booting — chat and quota routes still fail at runtime until Phase 36 rewires them.

#### Phase 36: Rebind Pre-existing Routes

**Goal:** Put the nine pre-existing routes behind the barrier and rewire the chat quota path onto the grant model, restoring a running application.
**Requirements:** REBIND-01 … REBIND-06
**Depends on:** 34, 35
**Success criteria:**

1. The application starts and every pre-existing route serves as it did in v1.6, apart from auth rejections now using the shared error classes
2. `GET /health/ready` is reachable unauthenticated; `GET /`, `GET /examples`, and all five `/chats` routes reject an unauthenticated caller
3. No `audit.auth_events` row is written by any of these routes, including on barrier rejection — the bounded counter metric increments instead
4. A missing usage row fails a quota-checked chat request closed rather than minting one (the `quota_checked_request` admission entry is void — Phase 35 D-05)
5. Lazy rollover resets `monthly_used` inside the same locked transaction when the stored period is stale, with grant-then-usage lock order and no network call under lock

#### Phase 37: POST /auth/create-user

**Goal:** Ship the only pre-auth-callable route — first-time account creation linking a verified Firebase `(issuer, subject)` to one new user plus exactly one active identity row.
**Requirements:** CREATE-01 … CREATE-04
**Depends on:** 34, 35
**Success criteria:**

1. An unlinked caller succeeds here and is rejected with `preauth_identity_not_allowed` on every other route
2. Prepare mode and completion mode partition correctly on the mode signal
3. One transaction produces the user row, exactly one ACTIVE identity row, and both store purchase-attribution tokens — a forced mid-transaction failure leaves no partial account
4. Two concurrent creates for the same `(issuer, subject)` yield one account; the loser reconciles via `/auth/sync`

#### Phase 38: POST /auth/sync

**Goal:** Ship the read-only auth-state reconciliation surface clients call after sign-in or a lost response.
**Requirements:** SYNC-01 … SYNC-03
**Depends on:** 34, 35 (soft: 37)
**Success criteria:**

1. Grant, `current_period`, and `monthly_used` all derive from one evaluation time and match what quota enforcement would independently act on at the same instant
2. Zero effective grants and a lapsed grant return byte-identical responses
3. Table state is unchanged across a request — verified by comparing `core.*` before and after
4. Every attempt writes exactly one `audit.auth_events` row with `operation='sync'`, barrier rejections included

#### Phase 39: GET /users/me

**Goal:** Rewrite the profile endpoint to return profile fields, stored registration state, and per-store purchase-attribution tokens.
**Requirements:** PROF-01, PROF-02
**Depends on:** 34, 35 (soft: 37)
**Success criteria:**

1. The response carries an entry for every store provider regardless of client platform, User-Agent, or any client-supplied signal
2. `identity_provider` comes from the stored column and matches what `/auth/sync` reports
3. No `audit.auth_events` row is ever written by this route, including on barrier rejection
4. A missing purchase-token row fails closed as an internal error rather than returning a null entry

#### Phase 40: POST /auth/upgrade-anonymous

**Goal:** Record the client-side same-Firebase-UID anonymous→registered upgrade by flipping the existing identity row's provider in place.
**Requirements:** UPGRADE-01, UPGRADE-02
**Depends on:** 34, 35, 37
**Success criteria:**

1. The existing `core.external_identities` row's provider flips in place — no new identity row, no user merge, no row deletion
2. Prepare and completion modes both work; only an authenticated linked identity may call it
3. `GET /users/me` and `/auth/sync` report the new provider afterward
4. Purchase-attribution tokens are unchanged across the upgrade

#### Phase 41: POST /auth/claim-anonymous-grant

**Goal:** Ship the sole creator of `anonymous_device_grant` access grants.
**Requirements:** ANONGRANT-01 … ANONGRANT-03
**Depends on:** 34, 35, 37
**Success criteria:**

1. This is the only code path that writes a grant row with `source='anonymous_device_grant'`
2. The grant transaction locks grant rows ascending by id, then their usage rows, with no network call while any lock is held
3. A second claim on an account that already holds a free grant does not allocate a second one
4. Prepare and completion modes partition on the mode signal with a server-determined branch

#### Phase 42: POST /auth/claim-registered-grant

**Goal:** Ship the sole creator of `registered_account_grant` grants, including supersession of an active anonymous device grant.
**Requirements:** REGGRANT-01 … REGGRANT-03
**Depends on:** 34, 35, 40, 41
**Success criteria:**

1. This is the only code path that writes a grant row with `source='registered_account_grant'`
2. Superseding an active anonymous grant happens in one transaction and never leaves two `status='active'` grants
3. The supersession honors the same fixed global lock order as Phase 41
4. An account that already consumed its free grant as anonymous does not receive a second free entitlement

#### Phase 43: POST /webhooks/app-store

**Goal:** Ingest Apple App Store Server Notifications as the first of exactly two provider-callback routes.
**Requirements:** APPLEHOOK-01, APPLEHOOK-02
**Depends on:** 34, 35
**Success criteria:**

1. The route sits outside the barrier and authenticates solely by verifying Apple's `signedPayload` JWS
2. A payload with an invalid or absent signature is rejected without touching subscription state
3. The route appears in the provider-callback category by exact path and the enumeration assertion still passes
4. Replayed notifications do not double-apply subscription state

#### Phase 44: POST /webhooks/google-play/rtdn

**Goal:** Ingest Google Play RTDN via Cloud Pub/Sub push as the second and last provider-callback route.
**Requirements:** PLAYHOOK-01 … PLAYHOOK-03
**Depends on:** 34, 35 (soft: 43)
**Success criteria:**

1. The route authenticates solely by backend verification of Google's signed OIDC push token
2. It calls Phase 43's shared ingestion module rather than a forked copy
3. The provider-callback category contains exactly these two routes, both by exact path
4. A push with an invalid OIDC token is rejected without touching subscription state

#### Phase 45: POST /auth/restore-subscription

**Goal:** Verify a native store artifact directly against Apple or Google and attach verified paid entitlement.
**Requirements:** RESTORE-01, RESTORE-02
**Depends on:** 34, 35, 37, 43, 44
**Success criteria:**

1. A valid Apple artifact and a valid Google artifact each attach entitlement through their server-determined branch
2. All store verification completes before the mutating transaction opens — no network call under lock
3. A non-native surface receives `operation_not_allowed`
4. An unverifiable artifact attaches nothing and leaves grant state untouched

#### Phase 46: POST /auth/sign-out-all

**Goal:** Revoke the verified subject's Firebase refresh tokens through the issuer-selected Admin client.
**Requirements:** SIGNOUT-01, SIGNOUT-02
**Depends on:** 34, 35
**Success criteria:**

1. Success is returned only after Firebase confirms revocation
2. An indeterminate or failed revocation fails closed — never a success response
3. Exactly one `audit.auth_events` row is written per attempt
4. No backend token, session, or generation counter is introduced

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Exception Foundation | v1.1 | 3/3 | Complete | 2015-02-26 |
| 2. Auth Structure + LLM Errors | v1.1 | 2/2 | Complete | 2015-02-27 |
| 3. Validation + Security Tests | v1.1 | 2/2 | Complete | 2015-02-27 |
| 4. Exception Integration Completeness | v1.1 | 1/1 | Complete | 2015-02-27 |
| 5. Config Fix + Dead Code Removal | v1.2 | 1/1 | Complete | 2015-02-28 |
| 6. LLM Output Parsing Hardening | v1.2 | 1/1 | Complete | 2015-02-28 |
| 7. PEP8 Compliance | v1.2 | 1/1 | Complete | 2015-02-28 |
| 8. Resilience Layer Extraction | v1.2 | 1/1 | Complete | 2015-02-28 |
| 9. Health Endpoint Simplification | v1.2 | 1/1 | Complete | 2015-02-28 |
| 10. JWT Authentication | v1.3 | 2/2 | Complete | 2015-03-02 |
| 11. Error Contract Hardening | v1.3 | 2/2 | Complete | 2015-03-02 |
| 12. LLM Dependency Injection | v1.3 | 2/2 | Complete | 2015-03-02 |
| 13. Endpoint Unification | v1.3 | 2/2 | Complete | 2015-03-03 |
| 14. DB Query Optimization | v1.4 | 2/2 | Complete | 2015-03-04 |
| 15. Refactor Chats | v1.4 | 8/8 | Complete | 2026-03-16 |
| 16. Update Tests | v1.4 | 4/4 | Complete | 2026-03-17 |
| 17. Simplify Error Handling | v1.4 | 1/1 | Complete | 2026-03-19 |
| 18. Test Infrastructure Cleanup | v1.5 | 1/1 | Complete | 2026-03-20 |
| 19. Service Layer Refactoring | v1.5 | 1/1 | Complete | 2026-03-20 |
| 20. Structured Logging | v1.5 | 1/1 | Complete | 2026-03-20 |
| 21. User Management | v1.5 | 3/3 | Complete | 2026-03-20 |
| 22. Apple Subscription Integration | v1.5 | 3/3 | Complete | 2026-03-20 |
| 23. Envoy Gateway Rate Limiting | v1.5 | 4/4 | Complete | 2026-03-22 |
| 24. Migration Merge | v1.5 | 2/2 | Complete | 2026-03-22 |
| 25. Config and Model Foundation | v1.6 | 2/2 | Complete | 2026-03-23 |
| 26. Service and Database Rewiring | v1.6 | 2/2 | Complete | 2026-03-23 |
| 27. Migration | v1.6 | 1/1 | Complete | 2026-03-24 |
| 28. Test Updates | v1.6 | 1/1 | Complete | 2026-03-24 |
| 29. Replace Raw SQL with ORM | v1.6 | 1/1 | Complete | 2026-03-24 |
| 30. E2E and Security Test Coverage | v1.6 | 3/3 | Complete | 2026-03-25 |
| 31. Move Quota Check to Dependency | v1.6 | 2/2 | Complete | 2026-03-25 |
| 32. Rewrite Models to Match Prompt Schema | v1.6 | 3/3 | Complete | 2026-03-26 |
| 33. Propagate quota_exceeded Rename | v1.6 | 1/1 | Complete | 2026-03-26 |
| 34. Schema | v2.0 | 4/4 | Complete    | 2026-08-20 |
| 35. Foundation | v2.0 | 9/11 | In Progress|  |
| 36. Rebind Pre-existing Routes | v2.0 | 0/? | Pending | — |
| 37. POST /auth/create-user | v2.0 | 0/? | Pending | — |
| 38. POST /auth/sync | v2.0 | 0/? | Pending | — |
| 39. GET /users/me | v2.0 | 0/? | Pending | — |
| 40. POST /auth/upgrade-anonymous | v2.0 | 0/? | Pending | — |
| 41. POST /auth/claim-anonymous-grant | v2.0 | 0/? | Pending | — |
| 42. POST /auth/claim-registered-grant | v2.0 | 0/? | Pending | — |
| 43. POST /webhooks/app-store | v2.0 | 0/? | Pending | — |
| 44. POST /webhooks/google-play/rtdn | v2.0 | 0/? | Pending | — |
| 45. POST /auth/restore-subscription | v2.0 | 0/? | Pending | — |
| 46. POST /auth/sign-out-all | v2.0 | 0/? | Pending | — |
