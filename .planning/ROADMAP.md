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

Phase 35 is the first **booting** app (D-14) — imports and lifespan all run. Phase 36 is the first **fully working** one, once the chat quota path is rewired onto the grant model.

> **Phase 37.1 amended this milestone's criteria on 2026-08-24** for two deletions: the auth-event audit subsystem (D-01) and the auth barrier middleware plus route registry (D-06). Criteria below are marked **withdrawn** (subject deleted), **reworded** (mechanism changed, substance intact), **confirmed** (became trivially true), or **blocked** (an unbuilt phase must decide). Completed-plan checkboxes record what was built and are left exactly as written. Two conflicts against `SHARED-INVARIANTS.md` are flagged, not resolved — see `REQUIREMENTS.md` under FOUND-01 and FOUND-05. This line originally also named the startup enumeration assertion, which went with the route registry.

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
4. ~~`audit.auth_events` rejects a row with partial actor fields per its CHECK constraints~~ — **WITHDRAWN by Phase 37.1 (D-01), 2026-08-24.** Delivered as written by Phase 34 and true until that date; the table, its nine CHECK constraints and its four indexes were then deleted from the initial migration, together with the `core.auth_event_result` type. The `audit` schema, `audit.subscription_events` and `core.auth_operation` all survive (D-02/D-04). Matching requirement: SCHEMA-06, withdrawn.
5. Every acceptance check in `00-schema.md §10` passes

> Application code referencing dropped columns breaks at this commit. Expected — see Phase 36.

#### Phase 35: Foundation

**Goal:** Build the shared machinery every later phase calls and none rebuilds — barrier, route registry, error registry, audit writer, provider-call budget seam, challenge store, adapter interfaces — and repair the model layer so the application boots and the enumeration assertion runs for real. **[AMENDED by Phase 37.1 — three items on this list no longer exist; see the note below.]**

> **Amended by Phase 37.1 (D-01/D-06), 2026-08-24 — the goal text above is left as written, because it records what Phase 35 actually set out to build and did build.** Three items on that list no longer exist: the **audit writer** was deleted outright, and the **barrier** and **route registry** were replaced by a router-level FastAPI dependency, taking the enumeration assertion with them. Still standing: the error registry, the provider-call budget seam, the challenge store, the adapter interfaces, and the admission matrix and wire contract the barrier held — those were re-hosted into the dependency, not lost.

**Requirements:** FOUND-01 … FOUND-08
**Depends on:** 34
**Plans:** 12/12 plans complete

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

- [x] 35-10-PLAN.md — Challenge store, claim/consume atomicity, and the §6.5 mode-signal check

**Wave 10** *(blocked on Wave 9 completion)*

- [x] 35-11-PLAN.md — Publish the `auth/` seam, restore e2e coverage, gate the suite green, COVERAGE.md

**Wave 11** *(blocked on Wave 10 completion)*

- [x] 35-12-PLAN.md — Gap closure (CR-01): offload JWKS verification off the event loop, bound the fetch timeout, add the negative-`kid` cache, replace the vacuous test (wave 11)

**Success criteria:**

1. ~~The route-enumeration assertion passes, and a route declared in zero or in two categories fails it~~ — **WITHDRAWN by Phase 37.1 (D-06), 2026-08-24.** The assertion and the parallel declaration table it compared against are both deleted. The fail-closed property it protected is now obtained **structurally**: the router a route is registered on *is* its declaration, so there is no second table left to drift, and `tests/unit/test_app_wiring.py::TestEveryRouteIsAuthenticated` asserts over `app.routes` that the public allowlist is exactly `{/health/ready}` and every other route declares the auth dependency — negative-controlled against an injected undeclared route. Matching requirement: FOUND-03, deleted outright.
2. Zero, duplicate, comma-joined, empty, and trailing-content Authorization values each reject as `auth_required` with identical body, status, and copy
3. The auth dependency admits only `identity_state='active'` AND `users.active` TRUE; every other combination rejects with nothing falling through to pre-auth — **noun reworded by Phase 37.1 (D-06/D-11), 2026-08-24; the admission rule is unchanged and still holds.** `tests/e2e/test_admission.py`'s 23-case matrix passed the move with zero edits to any status code or body literal. Matching requirement: FOUND-01.
4. ~~A barrier rejection produces exactly one `audit.auth_events` row with all three actor fields NULL and a bounded reason~~ — **WITHDRAWN by Phase 37.1 (D-01), 2026-08-24.** No auth audit row is written anywhere, on any path. What survives is the rejection log — folded into `app/dependencies.py::_reject` by Phase 37.2 (D-10), 2026-08-25 — which emits the `auth_rejected` structured log event carrying the same stable internal result, the same bounded reason and the route template on every rejection (D-03) — a log line, not a durable queryable row. Matching requirement: FOUND-05, withdrawn, where the `SHARED-INVARIANTS.md` conflict is flagged.
5. The application boots clean — `nativespeaker.api` imports and the lifespan runs at real startup against the real router — **amended by Phase 37.1 (D-06), 2026-08-24:** this criterion also named the `§2.3` enumeration assertion executing at startup, which was deleted with the route registry. The boot-clean half is unchanged and still holds.

> Scope changed by the Phase 35 discussion (`35-CONTEXT.md`): `§5` backend rate limiting is deleted from the product (D-05, Envoy Gateway owns request-rate enforcement) and `§9` the Envoy contract is deferred to v2.1 (D-08). Per D-14/D-15 the phase now ends booting — chat and quota routes still fail at runtime until Phase 36 rewires them.

#### Phase 36: Rebind Pre-existing Routes

**Goal:** Put the eight pre-existing routes behind the barrier and rewire the chat quota path onto the grant model, restoring a running application. (The ninth was `GET /users/me`, deleted by Phase 35 D-16 alongside its router and re-declared in Phase 39 — `auth/registry.py` and success criterion 2 below both total eight.) **[AMENDED by Phase 37.1 — the barrier is now a dependency and `auth/registry.py` is deleted; see the note below.]**

> **Amended by Phase 37.1 (D-06), 2026-08-24.** "Behind the barrier" now means behind the router-level auth dependency, and `auth/registry.py` is deleted — the eight-route count is carried by success criterion 2 and `tests/unit/test_app_wiring.py` alone. **Which routes are authenticated did not change**, and neither did the quota rewiring this goal is mostly about.

**Requirements:** REBIND-01 … REBIND-06 (REBIND-04 is void — see `REQUIREMENTS.md:49`)
**Depends on:** 34, 35
**Plans:** 5/5 plans complete

Plans:
**Wave 1**

- [x] 36-01-PLAN.md — Carry the applied D-01 tier seeding into the phase's commits and land the SQLModel layer for the three grant tables (wave 1)
- [x] 36-02-PLAN.md — D-12 empty-array defaults, the D-13 documentation corrections, and the nine-to-eight route-count fix (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 36-03-PLAN.md — Tracer: end-to-end quota gate on `POST /chats`, no effective grant returns 429, with the registry cross-check enforcing the flag (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 36-04-PLAN.md — Complete the quota flow: usage lock, the two fail-closed 500s, lazy rollover, and the increment (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 36-05-PLAN.md — Second quota route, the audit off-path proof for all eight routes, and the two-connection lock-order test (wave 4)

**Success criteria:**

1. The application starts and every pre-existing route serves as it did in v1.6, apart from auth rejections now using the shared error classes
2. `GET /health/ready` is reachable unauthenticated; `GET /`, `GET /examples`, and all five `/chats` routes reject an unauthenticated caller
3. No `audit.auth_events` row is written by any of these routes, including on admission rejection — the rejection's stable internal result goes to the structured security log instead. **CONFIRMED and reworded by Phase 37.1 (D-01/D-03), 2026-08-24:** the audit clause became **trivially true** rather than false — no route anywhere writes one and the table is gone — so it is kept rather than deleted, because it still binds. The counter clause was already false: Phase 36 D-15 removed the hand-rolled `RejectionCounter`. Matching requirement: REBIND-02.
4. A missing usage row fails a quota-checked chat request closed rather than minting one (the `quota_checked_request` admission entry is void — Phase 35 D-05)
5. Lazy rollover resets `monthly_used` inside the same locked transaction when the stored period is stale, with grant-then-usage lock order and no network call under lock

#### Phase 37: POST /auth/create-user

**Goal:** Ship the only pre-auth-callable route — first-time account creation linking a verified Firebase `(issuer, subject)` to one new user plus exactly one active identity row.
**Requirements:** CREATE-01 … CREATE-04
**Depends on:** 34, 35
**Plans:** 10/10 plans complete
**Success criteria:**

1. An unlinked caller succeeds here and is rejected with `preauth_identity_not_allowed` on every other route
2. Prepare mode and completion mode partition correctly on the mode signal
3. One transaction produces the user row, exactly one ACTIVE identity row, and both store purchase-attribution tokens — a forced mid-transaction failure leaves no partial account
4. Two concurrent creates for the same `(issuer, subject)` yield one account; the loser reconciles via `/auth/sync`

Plans:
**Wave 1**

- [x] 37-01-PLAN.md — Remove `core.auth_challenges.operation_variant` outright (D-13); apply the migration and repair the fallout — blocking decision checkpoint on the SCHEMA-01 conflict
- [x] 37-02-PLAN.md — Promote `tenacity` to a direct dependency (D-06), retire `auth/budgets.py` (D-04), land the one Firebase retry policy
- [x] 37-03-PLAN.md — Register `identity_already_linked` (409) and `operation_not_allowed` (403); add `FirebaseConfig` from `.env` only

**Wave 2**

- [x] 37-04-PLAN.md — `SubscriptionProvider` + `StorePurchaseToken` over the PK-less table; prove RESEARCH assumption A2 against PostgreSQL
- [x] 37-05-PLAN.md — The concrete issuer-selected Firebase Admin adapter and §02 step 9's closed providerData classifier
- [x] 37-06-PLAN.md — Convert `resilience.py`'s hand-rolled retry loop to the same tenacity policy (D-05), own commit

**Wave 3**

- [x] 37-07-PLAN.md — TRACER: end-to-end anonymous account creation, prepare + completion, registry entry and router in one commit

**Wave 4**

- [x] 37-08-PLAN.md — Completion rejection precedence: the five challenge rejections, the Admin outcomes, the classifier rejection
- [x] 37-09-PLAN.md — Conflict discrimination by constraint name; criteria 3 and 4 proven in `tests/schema/` with real commits

**Wave 5**

- [x] 37-10-PLAN.md — Registered flow and field rules via substituted adapter; Firebase credential checkpoint; the real-anonymous e2e (D-09)

#### Phase 37.1: Refactor machine-generated code (INSERTED)

**Goal:** Strip the machine-generated excess out of phases 34-37: delete the auth-event audit subsystem, replace the auth barrier middleware and route registry with FastAPI dependencies, and rewrite the prose across `src/`, `tests/` and the migration in plain English. Behavior-reducing only — no endpoint changes shape and no route changes its authentication status.
**Requirements**: none mapped — this phase is tracked against the CONTEXT.md decisions D-01 … D-17
**Depends on:** Phase 37
**Plans:** 8/8 plans complete

Plans:
**Wave 1**

- [x] 37.1-01-PLAN.md — TRACER: delete the auth-event audit subsystem, its call sites, and its schema objects (D-01…D-05) [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 37.1-02-PLAN.md — Replace the auth barrier middleware and route registry with FastAPI dependencies (D-06…D-11) [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 37.1-03-PLAN.md — Prose: the eight highest-density `auth/` modules (D-13…D-16) [wave 3]
- [x] 37.1-04-PLAN.md — Prose: remaining `auth/`, the `app/` composition root, `errors.py`; plus D-17's `logger.log` [wave 3]
- [x] 37.1-05-PLAN.md — Prose: routers, the `models/` package, and the top-level service modules (D-13…D-16) [wave 3]
- [x] 37.1-06-PLAN.md — Prose: `tests/e2e/`, `tests/schema/`, and the migration (D-13…D-16) [wave 3]
- [x] 37.1-07-PLAN.md — Prose: `tests/unit/` (D-13…D-16) [wave 3]
- [x] 37.1-08-PLAN.md — Amend REQUIREMENTS.md and ROADMAP.md for both deletions; flag the SHARED-INVARIANTS conflicts (D-12) [wave 3]

**Cross-cutting constraints:**

- No surviving comment or docstring in these files cites a spec section symbol, a ruling number, a decision id, a planning filename, a review ticket id, or a research pitfall number
- .venv/bin/pytest -q -m '', -m e2e and -m schema all exit 0

#### Phase 37.2: Simplify auth module (INSERTED)

**Goal:** Continue Phase 37.1's de-complication into the auth feature itself: collapse the `auth/` package (currently 14 files, 28 classes, 57 functions for one create-user feature) to the minimum that carries the behavior, drop the `credentials.Certificate()` path so Firebase initializes via ADC only, move the request/response models out of `routers/auth.py` into `models/auth.py`, and replace the `?challenge=true` mode signal with an explicit `POST /auth/challenge` endpoint taking `{"operation": "create_user"}` — deleting the mode-signal classifier that existed only to disambiguate the old shape.
**Requirements**: none mapped — scope is the five directives recorded in this entry; admission rules, status codes, and the Phase 37 e2e matrix must survive unchanged except where the challenge endpoint split explicitly moves them
**Depends on:** Phase 37.1
**Plans:** 7/7 plans complete

**Success Criteria:**

1. `credentials.Certificate()` and the credential-dict path are gone from `auth/firebase.py`; Firebase initializes via Application Default Credentials only
2. `CreateUserRequest`, `PrepareResponse`, and `CompletionResponse` live in `models/auth.py`; `routers/auth.py` defines no Pydantic models
3. Challenge issuance is its own route — `POST /auth/challenge`, taking the operation in the **body** as `{"operation": "create_user"}` — and every non-issuable operation is a single rejection class: a value outside the `AuthOperation` enum and a valid member whose phase is unbuilt both answer `400 invalid_request`, so the endpoint discloses nothing about the operation vocabulary. The accepted set is exactly `{create_user}` today and later phases widen it. The `?challenge=true` query-parameter mode, `auth/modesignal.py` and its `classify_mode_signal`, and the `get_raw_query_string` dependency are all deleted, and `POST /auth/create-user` handles **completion only** — it parses no query string and dispatches on no mode
4. `_classification_cause` and functions like it — single-caller indirections that exist to name a value rather than compute one — are inlined or deleted
5. The `auth/` package is measurably smaller in files, classes, and functions than the 14/28/57 baseline, with every deletion justified as carrying no behavior; the e2e admission matrix and unit suites pass with edits only where the challenge-endpoint split moved a contract

Plans:

**Wave 1**

- [x] 37.2-01-PLAN.md — TRACER: `POST /auth/challenge` wired end to end, models move to `models/auth.py` (D-01, D-02) [wave 1]
- [x] 37.2-02-PLAN.md — Firebase collapses to Application Default Credentials; the service-account config surface is deleted (D-06…D-08) [wave 1]
- [x] 37.2-03-PLAN.md — Folded todo: strict structured output bound at the LLM call, with a real-provider gate [wave 1]

**Wave 2** *(blocked on Wave 1)*

- [x] 37.2-04-PLAN.md — Delete the zero-consumer adapter interfaces and the lazy re-export facade (D-09, D-11) [wave 2]

**Wave 3** *(blocked on Wave 2)*

- [x] 37.2-05-PLAN.md — `POST /auth/create-user` becomes completion-only; the mode signal and its query accessor die (D-03…D-05) [wave 3]

**Wave 4** *(blocked on Wave 3)*

- [x] 37.2-06-PLAN.md — Cohesion merges, the single-caller inline sweep, and the package-shape gate (D-10, directives 4 and 5) [wave 4]

**Wave 5** *(blocked on Wave 4)*

- [x] 37.2-07-PLAN.md — Amend REQUIREMENTS.md and ROADMAP.md; record the third flagged conflict (CREATE-01, CREATE-02, FOUND-08) [wave 5]

**Cross-cutting constraints:**

- `tests/e2e/test_admission.py`'s 23-case admission matrix passed with **zero edits** — no route changed its authentication status, and no admission status code or body literal moved
- `tests/unit/test_create_user_precedence.py` passed with **zero edits** to any status code or body literal — the rejection precedence below the challenge lookup is unchanged, and its four helpers were left byte-identical and un-reordered
- The only status codes that moved are the two the split sanctions: a malformed or unusable `challenge_id` from a hand-rolled `400 invalid_request` to the framework's `422 validation_error` (D-04), and `409 identity_already_linked` from issuance to completion, raised by the in-transaction constraint conflict rather than a racy pre-check (D-03)

**Measured outcome:** the `auth/` package is **10 files, 19 classes, 44 functions**, down from the recorded 14/28/57 baseline — 1 module from the mode-signal deletion plus 3 absorbed by cohesion merges; 9 classes from the mode signal and the eight adapter interfaces; 13 functions from those plus the nine adapter methods, the two re-export facade functions and the rejection log. `tests/unit/test_auth_package_shape.py` carries the baseline and the current shape as literals with two controls, so the numbers are a checked fact rather than a claim, and any regrowth is a visible edit.

#### Phase 37.3: Machine-generated code refactoring, part 2 (INSERTED)

**Goal:** Kill the last machine-generated pattern in `auth/` — functions that *return* a rejection vocabulary (enums, result dataclasses, mapping dicts) which callers then translate into client responses. It is replaced by a DRF-style exception family raised where the rejection is discovered and answered by one FastAPI handler, with zero client-visible change: every status code, error class, body, header, consumption semantic and admission decision is preserved exactly. Only the structured-log event vocabulary changes, which is sanctioned.
**Requirements**: No new requirement IDs — this phase *amends* FOUND-08 (whose Phase 37.2 amendment names the `ProviderData*` surface this phase deletes). The requirement set is decisions D-01…D-19 in `37.3-CONTEXT.md`.
**Depends on:** Phase 37.2
**Plans:** 4/4 plans complete

Plans:
**Wave 1**

- [x] 37.3-01-PLAN.md — The exception family, its one handler, and the consuming transaction (`auth/creation.py`) converted to raise

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 37.3-02-PLAN.md — `resolve_identity` and `get_request_context` raise inline; the re-logging helper, the zero-declarer accessor and two stranded registry symbols die

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 37.3-03-PLAN.md — The provider lookup: one seam value type, a raised lookup hierarchy, inline classification, and retry by exception type

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 37.3-04-PLAN.md — The challenge binding raises under one 409 base; the outcome enum dies; FOUND-08 amended

#### Phase 37.4: Machine-generated code refactoring, part 3 (INSERTED)

**Goal:** Continue 37.1/37.2/37.3's de-complication on four fronts. **The identity types collapse:** the `LinkedIdentity`/`PreAuthIdentity`/`IdentityKind` union and the `RequestContext` carrier all die, replaced by one `Identity` class whose nullable fields carry the distinction, and one accessor pair — `get_identity` admits, `get_linked_identity` narrows. **The error architecture unifies:** the two parallel exception trees, the `ErrorClass` indirection and the module-level registry between an exception and its response collapse into one tree rooted at `AppError` whose classes carry their own status and code, served by one response builder and gated at startup by a registry-free totality walk over `__subclasses__()`. **Code-shape rules land:** docstrings capped at three lines, comments cut to the necessary ones and collapsed to a line each, one-function modules folded, and the quota gate demoted from a class-plus-callback-chain to a plain `charge_quota()` called on one visible line inside each of the two service methods. **Named disproportionate machinery is deleted**, each against an explicit spec requirement and each flagged: the HMAC keyring and its key-version machinery (432 lines protecting for 300 seconds a subject the schema already stores forever in plaintext one table over), the hand-rolled bearer extractor (replaced by `fastapi.security.HTTPBearer`), and `claim_attempt_id` (a compare-and-swap guard whose condition could never fail, because nothing anywhere un-claims a challenge). **Client-visible scope, stated honestly:** no client-visible change except the two movements D-06 and D-10 sanction — the race-path provider-account conflict moving from `403 operation_not_allowed` to `409 identity_already_linked`, and the wire shapes the framework's credential extractor resolves differently from the hand-rolled one — plus the sanctioned log-event vocabulary change, where each rejection's event name is now its exception class snake_cased.
**Requirements**: No new requirement IDs — this phase's requirement set is decisions D-01…D-16 and addenda A-00…A-10 in `37.4-CONTEXT.md`. **Three conflicts against the binding specification are recorded as FLAGGED in `.planning/REQUIREMENTS.md`, not resolved:** the plaintext pre-auth subject (D-11, under CREATE-02), the dropped attempt-id consumption condition (D-03, under CREATE-02) and the provider-account collapse (D-06, under CREATE-04). The two wire-contract divergences the phase planned to flag (D-10's first/last resolution and A-09's padding loosening) are **recorded as losses rather than flagged**, because the developer deleted the invariant asserting them from `SHARED-INVARIANTS.md` and deleted FOUND-02 outright — see the FOUND-01 record, which also reports the same rule surviving unamended in two phase briefs.
**Depends on:** Phase 37.3
**Plans:** 7/7 plans complete

Plans:

**Wave 1** *(the A-00 precondition repair — pre-existing breakage from `d466a4b`, not 37.4 scope)*

- [x] 37.4-01-PLAN.md — Repair the 13 stale module paths and 9 stale class names; re-baseline lint, typecheck and the package-shape ratchet

**Wave 2** *(the tracer — blocked on Wave 1)*

- [x] 37.4-02-PLAN.md — One exception tree in `errors.py`, one handler, a registry-free startup totality walk, and D-05's two account classes

**Wave 3** *(blocked on Wave 2)*

- [x] 37.4-03-PLAN.md — The identity collapse: one `Identity`, two accessors, `RequestContext` retired, `auth/identity.py` folded

**Wave 4** *(two parallel plans, blocked on Wave 3, no shared file)*

- [x] 37.4-04-PLAN.md — The quota seam: `charge_quota()` called inside the two service methods, the callback chain deleted
- [x] 37.4-05-PLAN.md — The two in-place migration edits, the HMAC keyring's deletion, and the dev-database re-apply *(has a blocking decision checkpoint)*

**Wave 5** *(blocked on Wave 4)*

- [x] 37.4-06-PLAN.md — The create-user conflict collapse and the `HTTPBearer` substitution

**Wave 6** *(blocked on Wave 5)*

- [x] 37.4-07-PLAN.md — The ROADMAP goal, the five flagged conflicts, and the phase's records

#### Phase 37.5: Machine-generated code refactoring, part 4 (INSERTED)

**Goal:** Restore the layered architecture and write it down — business logic in `services/`, database access in `crud/`, bodies in `schemas/`, tables in `tables/`, handlers in `routers/`, external-SDK seams in `auth/` — then apply the docstring and comment rules to every file in `src/` and `tests/`, inline the functions that are only a step, move the error-tree self-check out of production code, and move the quota charge so a request that never reached the provider is never billed. **Delivered:** `Identity` lives in `schemas/auth.py`, the identity queries in `crud/identities.py`, the completion in `services/auth.py::AuthService` and the quota in `services/quota.py::QuotaService` as one merged charge; `auth/identity.py`, `auth/create_user.py` and the top-level `quota.py` are deleted; the rules are in `AGENTS.md` and the docstring gate at `tests/unit/test_docstring_bar.py` measures **0** on every root (`src`, `tests`, `tests/unit`, `tests/e2e`, `tests/schema`) against a measured pre-sweep 29; `assert_tree_total` moved to `tests/unit/error_tree.py`; and `ResiliencePolicy.admission()` hands out an `Admitted` token with the charge inside admission and outside the retry, so an open circuit or a full queue is no longer billed. Suite **1016 passing** with markers cleared, `ruff check` clean.
**Requirements:** D-01 … D-15 and A-01 … A-17 (`37.5-CONTEXT.md`) — this phase has no REQ-ID prefix; its decisions and post-research addenda are its requirement set. **No new conflict against `SHARED-INVARIANTS.md` is recorded and none is resolved** (D-15, re-read rather than assumed): the count of flagged conflicts stays at **six**. Two adjacent items are recorded instead — A-07's `ErrorResponse` carve-out, which is a carve-out in `AGENTS.md` and not a divergence, and A-16's bookkeeping item, the `limits` mandate that is already on record as a Phase 35 **override** and is deliberately not counted. **FOUND-04 is amended** (the startup totality walk became a test) and three prior notes are **corrected** — FOUND-01's and FOUND-03's, which named modules and a negative control that this phase found do not exist as described. Three findings are recorded and **not** acted on: the database pool, `test_app_wiring.py`'s missing negative control with three vacuous resolver cases, and one coverage loss from the test cut. See `REQUIREMENTS.md` § Phase 37.5 records.
**Depends on:** Phase 37.4
**Plans:** 10/10 plans executed — phase verification pending

Plans:

**Wave 1**

- [x] 37.5-01-PLAN.md — `AGENTS.md`'s layering, function-shape and resilience rules, and the docstring gate with its measured pre-sweep baseline

**Wave 2** *(the tracer — blocked on Wave 1)*

- [x] 37.5-02-PLAN.md — The auth vertical: `schemas/auth.py`, `crud/identities.py`, `services/auth.py`, two thin handlers, `auth/` down to its three seam files

**Wave 3** *(two parallel plans, no shared file)*

- [x] 37.5-03-PLAN.md — `services/quota.py::QuotaService`, the two quota halves merged, the top-level module deleted
- [x] 37.5-04-PLAN.md — The `errors.py` trim: the tree checker rehosted into `tests/`, four dead classes deleted, `ChallengeRequired` kept

**Wave 4**

- [x] 37.5-05-PLAN.md — The admission seam: `admission()` and the `Admitted` token, the charge moved inside admission and outside the retry

**Wave 5**

- [x] 37.5-06-PLAN.md — The `src/` docstring and comment sweep, and the adapter test cut that must precede it

**Wave 6**

- [x] 37.5-07-PLAN.md — `tests/unit/` sweep and cuts: the error, challenge and JWT clusters

**Wave 7**

- [x] 37.5-08-PLAN.md — `tests/unit/` sweep and cuts: the create-user, identity, quota and firebase clusters

**Wave 8**

- [x] 37.5-09-PLAN.md — `tests/e2e/` and `tests/schema/` sweep, one file renamed, every gate baseline at zero

**Wave 9**

- [x] 37.5-10-PLAN.md — The roadmap goal, the dated requirements amendment, D-08's classification record and the unactioned findings

#### Phase 38: POST /auth/sync

**Goal:** Ship the read-only auth-state reconciliation surface clients call after sign-in or a lost response.
**Requirements:** SYNC-01 … SYNC-03
**Depends on:** 34, 35 (soft: 37)
**Plans:** 6/6 plans complete
**Success criteria:**

1. Grant, `current_period`, and `monthly_used` all derive from one evaluation time and match what quota enforcement would independently act on at the same instant
2. Zero effective grants and a lapsed grant return byte-identical responses
3. Table state is unchanged across a request — verified by comparing `core.*` before and after
4. No durable audit row is written on any path and no per-attempt telemetry is added beyond what already exists — one `request` line per attempt from the request middleware and one WARNING per rejection from the shared error handler — with the decision to drop the durable-row obligation recorded in `REQUIREMENTS.md` under SYNC-03 and the matching removal made in `SHARED-INVARIANTS.md`

Plans:

**Wave 1** *(two parallel plans, no shared file)*

- [x] 38-01-PLAN.md — The tracer: `POST /auth/sync` end to end for one linked caller with one effective grant, the non-locking effective-grant read, the four response types, `SyncService`, the route
- [x] 38-04-PLAN.md — Strike the audit invariants from `SHARED-INVARIANTS.md` *(has a blocking decision checkpoint — one-way door)*

**Wave 2** *(two parallel plans, blocked on Wave 1, no shared file)*

- [x] 38-02-PLAN.md — The service branches: the zero-grant answer, the stale period computed and never written, the three fail-closed tripwires reusing the existing classes
- [x] 38-05-PLAN.md — The dated SYNC-03 amendment, the three sibling entries, the conflicts count, and ROADMAP criterion 4

**Wave 3** *(blocked on Wave 2)*

- [x] 38-03-PLAN.md — End-to-end proof of the three success criteria: the byte-identical equivalence, the unchanged table state, the stored provider column and the barrier's rejections

**Wave 4** *(blocked on Wave 3)*

- [x] 38-06-PLAN.md — The executable guards that nothing was rebuilt, and the phase close against green suites

#### Phase 39: GET /users/me

**Goal:** Rewrite the profile endpoint to return profile fields, stored registration state, and per-store purchase-attribution tokens.
**Requirements:** PROF-01, PROF-02
**Depends on:** 34, 35 (soft: 37)
**Plans:** 4/4 plans complete
**Success criteria:**

1. The response carries an entry for every store provider regardless of client platform, User-Agent, or any client-supplied signal
2. `identity_provider` comes from the stored column and matches what `/auth/sync` reports
3. No `audit.auth_events` row is ever written by this route, including on admission rejection — **CONFIRMED by Phase 37.1, 2026-08-24: trivially true**, since no route anywhere writes one and the table is gone. Kept rather than deleted, because it still binds. Matching requirement: PROF-02, whose counter clause was reworded to the structured log — Phase 36 D-15 had already removed the counter, so **Phase 39 inherits no obligation to build either subsystem**.
4. A missing purchase-token row fails closed as an internal error rather than returning a null entry

Plans:

**Wave 1** *(two parallel plans, no shared file)*

- [x] 39-01-PLAN.md — The tracer: `GET /users/me` end to end for one linked caller with a complete token set — the new error class and its vocabulary ratchet, `crud/purchases.py`, the `Depends()` accessor, the two response models, the route and its wiring, plus the two ratchets the new route and class make claims about
- [x] 39-02-PLAN.md — The `AGENTS.md` § "Package layout" amendment (D-05, router-to-crud) and the dated `REQUIREMENTS.md` amendments for the rate-limit omission and the divergence from the brief's handler step 1

**Wave 2** *(two parallel plans, blocked on Wave 1, no shared file)*

- [x] 39-03-PLAN.md — The unit proofs: the closed unconditional body, the enum key set, `Cache-Control: no-store`, the single unlocked query, client-signal invariance, and the completeness rule's zero-row and one-row refusals
- [x] 39-04-PLAN.md — The end-to-end proofs: the stored provider read back and agreeing with `/auth/sync`, the fail-closed 500 on a missing and on a partial token set, the barrier's 401/403, and unchanged table state across a request

#### Phase 40: POST /auth/upgrade-anonymous

**Goal:** Record the client-side same-Firebase-UID anonymous→registered upgrade by flipping the existing identity row's provider in place.
**Requirements:** UPGRADE-01, UPGRADE-02
**Depends on:** 34, 35, 37
**Plans:** 8/8 plans executed
**Success criteria:**

1. The existing `core.external_identities` row's provider flips in place — no new identity row, no user merge, no row deletion
2. Preparation and completion are partitioned by route — `POST /auth/challenge` issues the challenge, `POST /auth/upgrade-anonymous` completes against it — and only an authenticated linked identity may call the completion — **reworded by Phase 40 (D-24), 2026-09-02; the partition and the admission rule are both delivered.** As written, this criterion described preparation as a **mode** on this endpoint, and it was true of the design it described until **Phase 37.2** (D-01/D-03/D-05) replaced the mode-signal partition with a dedicated issuance route; `classify_mode_signal` does not exist in this codebase, so prepare is a separate route here rather than a mode. The full amendment, including why the mode-signal partition is not rebuilt here and what replaced it, is under UPGRADE-02 in `REQUIREMENTS.md`. Reworded rather than withdrawn: both phases still exist, their order is still enforced because completion requires a handle prepare issued, and `get_linked_identity` still narrows the completion route to an authenticated, linked, active caller. Matching requirement: UPGRADE-02, amended on the same date.
3. `GET /users/me` and `/auth/sync` report the new provider afterward
4. Purchase-attribution tokens are unchanged across the upgrade

Plans:

**Wave 1** *(prerequisites — the schema, the vocabulary, and the credential mechanism)*

- [x] 40-01-PLAN.md — Shrink `core.auth_operation` to its four challenge-bearing values, drop the redundant CHECK, re-apply both databases *(has a blocking decision checkpoint — one-way door)*
- [x] 40-02-PLAN.md — The two upgrade refusals under one shared 403 base, and one completion request model for both routes
- [x] 40-03-PLAN.md — The per-run Google-linked Firebase session: exchange, link, teardown — no signing credential anywhere

**Wave 2** *(the tracer — blocked on Wave 1)*

- [x] 40-04-PLAN.md — TRACER: end-to-end anonymous→registered upgrade, one path, flipped in place through the real router

**Wave 3** *(two parallel plans, blocked on Wave 2, no shared file)*

- [x] 40-05-PLAN.md — The rest of the case matrix: the idempotent repeat, the three refusals, and the precedence and consumption proofs
- [x] 40-06-PLAN.md — The issuance rules: the account-less condition, and the challenge-endpoint file restated against the four-value vocabulary

**Wave 4** *(blocked on Wave 3)*

- [x] 40-07-PLAN.md — The real Google-linked account, the cross-endpoint flow proof, and the third-state schema scan

**Wave 5** *(blocked on Wave 4)*

- [x] 40-08-PLAN.md — The dated UPGRADE amendment, the SCHEMA-01 note, and criterion 2's reword

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

1. The route sits outside the auth dependency and authenticates solely by verifying Apple's `signedPayload` JWS *(noun reworded by Phase 37.1 (D-06), 2026-08-24 — the barrier is a FastAPI dependency now; the requirement is unchanged)*
2. A payload with an invalid or absent signature is rejected without touching subscription state
3. **The category machinery this names was deleted by Phase 37.1. Phase 43 must answer it.** As written: the route appears in the provider-callback category by exact path and the enumeration assertion still passes. `Category`, `RouteMetadata`, `VERIFIERS` and `NamedVerifier` went with the route registry (D-06/D-10), 2026-08-24, before this phase exists. `VERIFIERS` had no members, so nothing regressed — but **the control is real**: exact-path enumeration is what stops a wildcard or prefix accidentally admitting an unauthenticated route, and `SHARED-INVARIANTS.md` still forbids wildcard or prefix membership. **A pointer, not a design:** a dedicated `APIRouter` carrying a named-verifier dependency, whose membership is the set of routes registered on it. Phase 43 evaluates that on its own terms; Phase 37.1 adds no replacement mechanism. Matching requirement: APPLEHOOK-02.
4. Replayed notifications do not double-apply subscription state

#### Phase 44: POST /webhooks/google-play/rtdn

**Goal:** Ingest Google Play RTDN via Cloud Pub/Sub push as the second and last provider-callback route.
**Requirements:** PLAYHOOK-01 … PLAYHOOK-03
**Depends on:** 34, 35 (soft: 43)
**Success criteria:**

1. The route authenticates solely by backend verification of Google's signed OIDC push token
2. It calls Phase 43's shared ingestion module rather than a forked copy
3. The provider-callback category contains exactly these two routes, both by exact path — **in whatever form Phase 43 defines, since Phase 37.1 deleted the category machinery (D-06), 2026-08-24.** Phase 44 inherits Phase 43's answer rather than inventing a second one; PLAYHOOK-02 already binds it to Phase 43's shared module, and two competing partition mechanisms would recreate the drift the registry died of. The "exactly two" clause needs that partition to be countable. Matching requirement: PLAYHOOK-03.
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
3. **BLOCKED: requires a mechanism Phase 37.1 deleted. Phase 46 must decide.** As written: exactly one `audit.auth_events` row is written per attempt. The table, the writer and every call site were deleted by Phase 37.1 (D-01), 2026-08-24, before this phase was built. **Phase 46 owns the decision** — the same choice Phase 38 faces — but must weigh it on this operation's own terms: criterion 2's fail-closed rule is untouched and still binding, and a sign-out-all that fails closed on an indeterminate revocation leaves *nothing* recording the attempt if the obligation is simply dropped. That is a different exposure from a read-only sync losing its attempt telemetry. Matching requirement: SIGNOUT-02.
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
| 35. Foundation | v2.0 | 12/12 | Complete    | 2026-08-21 |
| 36. Rebind Pre-existing Routes | v2.0 | 5/5 | Complete    | 2026-08-21 |
| 37. POST /auth/create-user | v2.0 | 10/10 | Complete    | 2026-08-23 |
| 38. POST /auth/sync | v2.0 | 6/6 | Complete    | 2026-09-01 |
| 39. GET /users/me | v2.0 | 4/4 | Complete    | 2026-09-01 |
| 40. POST /auth/upgrade-anonymous | v2.0 | 8/8 | In Progress|  |
| 41. POST /auth/claim-anonymous-grant | v2.0 | 0/? | Pending | — |
| 42. POST /auth/claim-registered-grant | v2.0 | 0/? | Pending | — |
| 43. POST /webhooks/app-store | v2.0 | 0/? | Pending | — |
| 44. POST /webhooks/google-play/rtdn | v2.0 | 0/? | Pending | — |
| 45. POST /auth/restore-subscription | v2.0 | 0/? | Pending | — |
| 46. POST /auth/sign-out-all | v2.0 | 0/? | Pending | — |
