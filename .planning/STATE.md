---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Authentication & Entitlements (Phases 34-46)
current_phase: 37.5
current_phase_name: machine-generated-code-refactoring-part-4
status: executing
stopped_at: Phase 38 context gathered
last_updated: "2026-09-01T07:45:20.483Z"
last_activity: 2026-08-31
last_activity_desc: Phase 37.5 plan 10 — roadmap, requirements amendment and phase records written
state_head: 24ac1c4b62d7bda66d901c3986db753f4b18fb3c
progress:
  total_phases: 18
  completed_phases: 9
  total_plans: 73
  completed_plans: 67
  percent: 44
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-19)

**Core value:** The analysis pipeline must work reliably -- correct LLM invocation, proper resilience under load, and safe per-user data isolation.
**Current focus:** Phase 37.5 — machine-generated-code-refactoring-part-4

## Current Position

Phase: 37.5 (machine-generated-code-refactoring-part-4) — ALL PLANS LANDED, VERIFICATION PENDING
Plan: 10 of 10
Status: Phase 37.5 plans complete; the phase itself is not marked complete until the verifier runs
Last activity: 2026-08-31 — Phase 37.5 plan 10 wrote the roadmap entry, the dated requirements amendment and the phase records

<!-- The same counter hazard recurred in 37.5 and is corrected here the same way. Waves 2 through 8
     ran as parallel worktree agents which deliberately do not write STATE.md, so the counter sat at
     1 while nine plans landed. Ten is disk truth: ten SUMMARY files exist (37.5-01..37.5-10). The
     frontmatter's completed_plans went 57 -> 67 for the same reason; completed_phases stays at 8
     because the phase is not verified yet. -->

**Phase 37.5 outcome.** The layered architecture is restored and written into `AGENTS.md`: `Identity`
in `schemas/auth.py`, the identity queries in `crud/identities.py`, the completion in
`services/auth.py::AuthService`, the quota in `services/quota.py::QuotaService` as one merged charge.
`auth/identity.py`, `auth/create_user.py` and the top-level `quota.py` are deleted. The docstring and
comment bar is at **0 on every root** against a measured pre-sweep 29. `assert_tree_total` moved to
`tests/unit/error_tree.py`. `ResiliencePolicy.admission()` hands out an `Admitted` token with the
charge inside admission and outside the retry, so **a request that never reached the provider is no
longer billed**. Suite **1016 passing** with markers cleared and 0 deselected; `ruff check` clean.
Six items are recorded as **open**, not done — see `REQUIREMENTS.md` § Phase 37.5 records.

<!-- The plan counter was corrected from 3 to 8 on 2026-08-23, and from 9 to 10 on 2026-08-24, for
     the same reason both times. Waves 1, 2 and 4 ran as parallel worktree agents which deliberately
     do not write STATE.md (last-write-wins hazard), so the counter never advanced with them and
     `state advance-plan` increments a stale value. Ten is disk truth: ten SUMMARY files exist
     (37-01..37-10), which is every plan in the phase. -->

## Wave 3 outcome (37-07, the tracer)

`POST /auth/create-user` is registered, declared, and serving both modes end to end for the
anonymous happy path. The architectural facts later plans build on, all proven against real
PostgreSQL: the challenge claim commits in its own transaction **before** the provider read; no
transaction is open across that read; the consuming transaction is a plain function
(`auth/creation.py::create_account`) reachable without FastAPI; and `begin_nested()` wraps the
business inserts so consumption and the audit row survive a rollback.

Four rejection branches are deliberately unfinished and marked in code with their owning plan —
see 37-07-SUMMARY.md § Known Stubs. Two have client-visible consequences and are 37-08/37-09's
first work: `user_not_found` currently earns 503 where §02 earns 401, and a genuine
`UNIQUE (issuer, subject)` race would surface as a 500 until the savepoint's rollback arm lands.

## Accumulated Context

### Key Decisions (carry forward)

- Error contract: 5 status codes / 5 opaque codes — SUPERSEDED in v2.0 by the shared auth error registry (anti-oracle within class)
- All FastAPI dependencies in app/dependencies.py; routes use Depends() only
- Session-in-init DB pattern for all DB classes
- CORS and security headers deferred to Envoy Gateway; rate limiting SUPERSEDED in v2.0 by the backend `limits` engine (Envoy = defense-in-depth)
- HTTP metadata on exception classes; single data-driven service_error_handler
- Firebase claim propagation delay (up to 1hr) accepted -- DB is authoritative
- Per-test transaction rollback via join_transaction_mode=create_savepoint
- structlog with ProcessorFormatter dual-output pipeline; contextvars for request correlation
- JIT user provisioning via INSERT ON CONFLICT DO NOTHING + SELECT
- Atomic quota enforcement via INSERT ON CONFLICT + conditional UPDATE with caller-provided monthly_quota
- Bare dict[SubscriptionPlan, int] for quotas -- simpler than QuotaConfig wrapper
- UsageDB.try_increment accepts monthly_quota as caller-provided int -- decouples DB layer from plans table
- Envoy Gateway local rate limiting; PostgreSQL quota is authoritative
- Separate HTTPRoutes per auth level: app (JWT), llm (JWT+rate-limit), webhooks (public), health (public)
- Plain dict for Message.content with JSONB -- no Pydantic model wrapping at persistence layer
- LLM validation models in models/llm.py, API schemas in models/api.py -- separate concerns
- require_quota FastAPI dependency for quota enforcement -- ChatService single-responsibility
- OutOfScopeError for LLM reject responses with resolved_mode dispatch

**v2.0 (Authentication & Entitlements):**

- Spec authority: /home/init/native-speaker/specs/auth-refactor-phases/ — SHARED-INVARIANTS.md binds every phase and overrides any conflicting phase brief; flag conflicts, never resolve silently
- One initial migration, renamed and replaced rather than rewritten under its old id; never add incremental migrations during v2.0 (overrides 00-schema.md §1/§2)
- Schema (34) and foundation (35) stay separate phases — different acceptance gates; Phase 34 knowingly leaves the app non-starting
- Phase numbering continues at 34–45; spec file number + 34 = phase number
- Roadmap built from spec metadata; each phase reads only its own spec file + SHARED-INVARIANTS.md at plan time (~90k tokens total, never loaded at once)
- One endpoint = one phase = one REQ-ID prefix; no requirement spans phases
- Identity is only backend-verified (issuer, subject); core.users.id is never an authentication key
- The pre-handler barrier is the only place identity resolution happens; handlers never re-verify
- Fixed global lock order on every grant path: grant rows FOR UPDATE ascending by id, then their usage rows
- No network call while any DB lock is held or a consuming transaction is open
- Database credentials in .env use the DB_* prefix (read by pogo's database_config and AppConfig.db); POSTGRES_* exists only for the postgres:17 image, and the image's database key is POSTGRES_DB, never POSTGRES_NAME
- Phase 34 dev database is the developer's local postgres:17 container on localhost:5432 — PostgreSQL 17.11; RESEARCH.md's introspection constants were captured on 16.2 and plan 34-03 must re-capture them (assumption A1 still open)

### Pending Todos

- **Run `/gsd:docs-update` for `README.md`** — queued by Phase 37.4 (A-10), which deliberately did
  **not** edit it (zero changed lines across the phase branch) rather than widen the phase. Three
  specific stalenesses, each verified at 2026-08-30:

  - **Endpoints that no longer exist** — `README.md:91` documents `POST /prompts/analyze`. The v2.0
    surface is the `/auth/*`, `/chats/*`, `/users/me` and `/health/ready` set.

  - **A package layout that no longer exists** — `README.md:194-199` shows an `app/` tree with
    `models.py`. The tree is `src/nativespeaker/api/` and `models/` was split into `tables/` and
    `schemas/` with `database/` renamed `crud/` by `d466a4b`.

  - **A Python version that no longer applies** — `README.md:14` says "Python 3.12+";
    `pyproject.toml:4` requires `>=3.14`.

- **Refresh `.planning/codebase/*.md`** — the seven files there were captured 2026-02-24, are three
  milestones behind and predate the `d466a4b` renames entirely. `37.4-CONTEXT.md` marks them
  **stale, do not trust — read the source**, and its deferred list says the refresh is best done
  after this phase lands. It has landed. **Now also behind Phase 37.5's layering moves** —
  `auth/identity.py`, `auth/create_user.py` and `quota.py` are gone and `crud/identities.py`,
  `schemas/auth.py`, `services/auth.py` and `services/quota.py` are new.

- **Queued by Phase 37.5, each recorded in `REQUIREMENTS.md` § Phase 37.5 records and none done:**

  - **`tables/__init__.py` still re-exports the `schemas/` names** — eleven of them. `37.5-PATTERNS.md`
    lists this as the phase's layering work; no plan claimed it. It is layering, not prose, so no
    sweep would have reached it.

  - **`tests/unit/test_app_wiring.py::TestEveryRouteIsAuthenticated` has no negative control against
    an injected undeclared route**, contrary to what FOUND-03's note claimed — corrected in
    `REQUIREMENTS.md`. With it, three vacuous cases stand in `test_quota_resolver.py`
    (`test_two_effective_grants_raise`, `test_a_grant_with_no_usage_row_raises`,
    `test_a_missing_tier_row_raises`), left because widening a deletion past its named targets is
    the costlier deviation.

  - **`tests/schema/conftest.py:56` still calls the database "a crud"** —
    `"refusing to interpolate {name!r} as a crud identifier"`. The last `d466a4b` artefact. Left by
    plan `37.5-09` because it is a string literal, not prose: changing it would have changed the AST
    under that plan's no-logic-change proof. One-line fix: `crud identifier` → `database identifier`.

  - **`config/config.yaml:18-31`'s orphaned HMAC key-material comment block** (`37.4-REVIEW.md` WR-04)
    still describes keys that no longer exist, above `chats_limit: 50`. D-12's sweep is scoped to
    `.py` files and could not reach a YAML comment.

### Roadmap Evolution

- Phase 37.1 inserted after Phase 37: Refactor machine-generated code (URGENT)
- Phase 37.2 inserted after Phase 37: Simplify auth module: ADC-only Firebase, models out of routers, POST /auth/challenge replaces ?challenge=true, delete single-caller indirections, shrink auth/ from 14/28/57 (URGENT)
- Phase 37.3 inserted after Phase 37: Machine-generated code refactoring, part 2 (URGENT)
- Phase 37.4 inserted after Phase 37.3: Machine-generated code refactoring, part 3 (URGENT)
- Phase 37.5 inserted after Phase 37.4: Machine-generated code refactoring, part 4 (URGENT)

### Blockers/Concerns

- RESOLVED (34-01): the PostgreSQL 17 blocker is cleared — developer started a postgres:17 container; server_version 17.11 (Debian 17.11-1.pgdg13+2) reachable on localhost:5432, database `nativespeaker` created and empty.
- OPEN: RESEARCH.md assumption A1 — introspection constants were captured on PostgreSQL 16.2 but the target is 17.11; plan 34-03 must re-capture them rather than copying RESEARCH.md Code Example 4.
- Deferred (37-10): the ~48s worst-case provider latency on the completion path is a policy decision on a shared budget — resolve with phases 40/41/42, which share the adapter seam.
- OPEN (37.5-10, A-15): the database pool exhausts at three concurrent chat posts **today**. `db.pool_size` defaults to 5 (`config.py:25`) with `max_overflow=0` (`app/lifespan.py:34`) and a `POST /chats` holds two connections. Phase 37.5 did not create this but moved the stall inside the LLM permit, so a pool wait now also holds a provider permit. **Recorded, not fixed — the developer owns the choice.** One-line change: raise `db.pool_size` to at least `resilience.pool_size × 2 + 2` (12 at the configured values), or accept the ceiling.
- OPEN (37.5-06): a real coverage loss. `test_foundation_calls_no_adapter_method_anywhere_in_src` was the only enforcement that `get_user_provider_data` is named nowhere in `src/` outside `auth/adapters.py` and `auth/firebase.py`. The property holds today by grep, but nothing fails if a third file starts calling the adapter. ~25 lines to restore, with its allow-list and two controls. Not restored — unlike the two security cases the developer restored in `658895e`.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260325-jrd | Fix tests: POST /chats returns empty content field | 2026-03-25 | ea6bea1 | [260325-jrd-fix-tests-post-chats-returns-empty-conte](./quick/260325-jrd-fix-tests-post-chats-returns-empty-conte/) |
| 260326-h2r | Fix incorrect content->message renames in unit tests | 2026-03-26 | 93f95da | [260326-h2r-i-renamed-the-follow-up-message-field-se](./quick/260326-h2r-i-renamed-the-follow-up-message-field-se/) |
| 260326-ico | Add OpenAPI tags, summaries, descriptions to all endpoints | 2026-03-26 | 52b7173 | [260326-ico-the-api-endpoints-have-no-descriptions-i](./quick/260326-ico-the-api-endpoints-have-no-descriptions-i/) |

## Session Continuity

**Last session:** 2026-09-01T07:10:12.857Z

Last activity: 2026-08-31
Stopped at: Phase 38 context gathered
Resume file: .planning/phases/38-post-auth-sync/38-CONTEXT.md

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 34 P01 | 3m | 1 tasks | 1 files |
| Phase 34 P01 | 10m | 2 tasks | 1 files |
| Phase 34 P02 | ~25 min | 3 tasks | 6 files |
| Phase 34 P03 | 42min | 3 tasks | 8 files |
| Phase 34 P04 | 38min | 2 tasks | 3 files |
| Phase 35 P12 | 22min | 3 tasks | 4 files |
| Phase 36 P01 | 7min | 3 tasks | 7 files |
| Phase 36 P02 | 6min | 3 tasks | 5 files |
| Phase 36 P03 | 7min | 2 tasks | 13 files |
| Phase 36 P04 | 17min | 3 tasks | 7 files |
| Phase 36 P05 | 12min | 3 tasks | 9 files |
| Phase 37 P01 | ~20min | 3 tasks | 8 files |
| Phase 37 P07 | 35min | 3 tasks | 12 files |
| Phase 37 P10 | ~55 min | 3 tasks | 5 files |
| Phase 37.3 P01 | 41min | 4 tasks | 12 files |
| Phase 37.3 P02 | 34min | 3 tasks | 9 files |
| Phase 37.3 P03 | 31min | 4 tasks | 13 files |
| Phase 37.3 P04 | 38min | 4 tasks | 13 files |
| Phase 37.4 P07 | ~50min | 3 tasks | 5 files |
| Phase 37.5 P06 | ~55min | 3 tasks | 20 files |
| Phase 37.5 P07 | ~50min | 3 tasks | 10 files |
| Phase 37.5 P08 | ~65min | 3 tasks | 11 files |
| Phase 37.5 P09 | ~55min | 3 tasks | 18 files |
| Phase 37.5 P10 | ~40min | 3 tasks | 3 files |

## Decisions

- [Phase ?]: Phase 34 delivers the v2.0 schema as ONE migration file (34-02 task-1 one-way door resolved as one-file); the six-file sequence in 00-schema.md §1 is overridden and infeasible — no v1.6 baseline database exists to migrate from
- [Phase ?]: 00-schema.md §3–§7 is a DELTA, not a complete file: seven objects its own §10 inventory requires are never created by it and must be hand-written (schemas core/audit, enums chat_role and subscription_status, tables users/chats/messages, index ix_chats_user_id)
- [Phase ?]: core.users is taken from the §2 TARGET-shape table at 00-schema.md:84-94, never from the baseline CREATE TABLE — the baseline shape would reintroduce jwt_sub and violate SCHEMA-07 while the apply still succeeds
- [Phase ?]: Migration rollback is two DROP SCHEMA … CASCADE statements rather than a reverse-order object list, because the list drifts out of sync with the apply body and the two-statement form cannot
- [Phase ?]: PostgreSQL 17.11 reproduced every 16.2-derived constant this plan could check (54 indexes, 104 internal triggers, 0 user triggers/views/matviews) — corroborating evidence for RESEARCH.md A1, not its closure; 34-03 still re-captures
- [Phase ?]: 34-03: registered the `schema` pytest marker and extended addopts to -m 'not e2e and not schema' -- every schema command must now pass -m schema explicitly
- [Phase ?]: 34-03: PostgreSQL 17.11 capture matched RESEARCH.md's PG 16.2 constants exactly across all six groups -- assumption A1 closed as confirmed, OQ-1 answered 'no divergence'
- [Phase ?]: 34-03: index-predicate assertions pin search_path to the asyncpg default rather than normalizing pg_get_expr output, keeping expected strings literal (P-5)
- [Phase ?]: Cases R5/R6 assert the exception class only: the named grant_source CHECK is subsumed by the four-arm CHECK and unreachable as a reported violation on PostgreSQL 17.11
- [Phase ?]: Savepoint-scoped rejection helper, because a rejected statement aborts the whole transaction and blocks any post-rejection query
- [Phase ?]: SET CONSTRAINTS ALL IMMEDIATE proves a deferred constraint accepts a valid row without committing it
- [Phase ?]: 35-12: D10's fifth conjunct restated as 'no per-request network call ON THE EVENT LOOP' — a first unrecognized kid still costs one bounded (3s), off-loop fetch; repeats cost none for the life of a 60s negative-cache entry
- [Phase ?]: 35-12: any synchronous call on the barrier's request path that can perform I/O is awaited through starlette.concurrency.run_in_threadpool — never called inline (verify() stays sync per D-01)
- [Phase ?]: 35-12: an absent, empty, or non-string kid keys on a shared empty-string sentinel in the negative cache — PyJWT forces a real refresh on every unmatched kid, so omitting one header field was otherwise an unbounded per-request fetch
- [Phase ?]: 35-12: PyJWKClientConnectionError never records a kid — an endpoint outage must not become a longer self-inflicted auth outage; distinct unknown kids still cost one bounded off-loop fetch each (accepted as T-35-12-03)
- [Phase ?]: 35-12: fetch/IO counts are asserted at the transport seam under a real client, never against a substituted client class, and every bounded-count assertion ships with a control that makes the count non-zero
- [Phase ?]: 36-01: all four GENERATED ALWAYS AS (...) STORED columns on core.access_grants are omitted from the AccessGrant model — PostgreSQL rejects an explicit value for them, so mapping one breaks every ORM insert
- [Phase ?]: 36-01: D-01 tier seeding committed as migration reference data (anonymous=10, registered=50, paid=1000), overriding 00-schema.md:249 with the conflict recorded as a SHARED-INVARIANTS flag rather than resolved silently
- [Phase ?]: 36-01: REBIND-05 left unchecked — this plan delivers only the model layer; the resolution, lock order, fail-closed and rollover behavior the requirement describes is owned by plans 36-03/36-04/36-05, which also claim it
- [Phase ?]: D-12 shipped as plain `= []` defaults on AnalyzeResponse; a test proves Pydantic v2's per-instance deep-copy rather than assuming it, so no default_factory was needed.
- [Phase ?]: resolved_mode and response stay required on AnalyzeResponse, pinned by a new test — T-36-llmshape's 'exactly two field defaults' is now enforced, not just asserted in a comment.
- [Phase ?]: The withdrawn PROJECT.md constrained-decoding claim stays in place marked '✗ Withdrawn — never shipped' rather than being deleted, so the over-claim that made D-35-11-A reachable leaves a trace.
- [Phase ?]: 36-03: seed_grant defaults to source=manual — the two free grant sources require a core.access_grants_anti_abuse row via a deferrable FK, and that table has no model in this phase
- [Phase ?]: 36-03: consume_quota takes a required keyword-only route parameter, so the fail-closed branch can log the route path template as a closed-set telemetry label
- [Phase ?]: 36-03: registry condition 10 matches route.dependencies by callable identity, never route.dependant.dependencies (which conflates parameter-level dependencies)
- [Phase ?]: 36-04: the resolver never mints a usage row — a missing one is a 500 tripwire, not a free allowance (D-09)
- [Phase ?]: 36-04: UnknownTierError added as a third INTERNAL_ERROR class so a dangling tier fails closed rather than reading as allowance 0 or unbounded
- [Phase ?]: 36-04: ask_llm persists the validated LLM model, not the raw provider dict — D-12's empty-list defaults never reached the client before this
- [Phase ?]: REBIND-06 left unmarked at phase end: a post-gate 404 on POST /chats/{chat_id} burns a credit, which v1.6's yield-dependency rolled back. Verified by probe (0 -> 1). Resolution is a decision about D-11's scope, not a re-plan.
- [Phase ?]: 37-01: Task 1 one-way gate resolved as option-a — the single initial migration is edited in place and the disposable dev/test DB re-applied; D-13's 'new migration' wording loses to shipped SCHEMA-01, recorded as a flagged conflict in both 37-CONTEXT.md and REQUIREMENTS.md
- [Phase ?]: 37-01: the four-arm Ruling-9.8 CHECK is now a bare operation-membership test over the four challenge-bearing operations; lifecycle and binding CHECKs left byte-identical
- [Phase ?]: 37-01: Phase 40 (POST /auth/upgrade-anonymous) has LOST its database-level provider binding (was operation_variant IN ('google','apple')) and must supply its own at completion — flagged forward, explicitly not Phase 37's to solve
- [Phase ?]: 37-01: CREATE-02 left unchecked — this plan only removes a column; plans 37-02/06/07/08 also claim it and are the ones that complete it (same treatment as 36-01/REBIND-05)
- [Phase ?]: 37-07: POST /auth/create-user reads the identity variant off RequestContext rather than Depends(get_preauth_identity) — it is the only route admitting both variants, because §02 prepare step 1's already-linked rejection (409) is unreachable when the accessor raises 401 on a linked caller (A-37-07-1)
- [Phase ?]: 37-07: the challenge claim commits in its own transaction before the Firebase read — a crash mid-lookup leaves a permanently-claimed dead row (§6.2's design), whereas holding the claim uncommitted would let a second attempt win it
- [Phase ?]: 37-07: the consuming transaction is auth/creation.py::create_account, a plain function over (session + resolved facts), so 37-09 can drive it with two real sessions; begin_nested() wraps the business inserts
- [Phase ?]: D-08 amended (37-10): the Firebase Admin credential arrives via Application Default Credentials, not a service-account key — org policy iam.disableServiceAccountKeyCreation forbids minting one. Named per-issuer app, explicit projectId and no [DEFAULT] app are unchanged; only the credential source moved.
- [Phase ?]: RESEARCH A5 closed by measurement (37-10): httpTimeout bounds each get_user transport attempt exactly, but the SDK makes two per call — one get_user costs up to 2x httpTimeout (16s at 8s), and with auth/retry.py's 3 attempts a worst-case completion holds ~48s. Fails closed; latency exposure only.
- [Phase ?]: 37.3 Task 1: the auth package-shape class ceiling is removed by decision, not widened; D-01 stands and the family lives in auth/exceptions.py
- [Phase ?]: 37.3: no deployed dashboard keys on the retiring log event names, so D-02 may retire auth_rejected, create_user_challenge_rejected and create_user_lookup_rejected freely
- [Phase ?]: 37.3 (RESEARCH OQ 2): _complete owns the post-claim consume for raising arms; create_account keeps it for the success path only
- [Phase ?]: InvalidExternalJwt is one class for both wire arms; bounded_reason distinguishes them in the log (37.3-02)
- [Phase ?]: The log event pre_auth_identity_not_allowed diverges from the client code preauth_identity_not_allowed, by decision (37.3-02)
- [Phase ?]: Ratchet literals (event vocabulary, package shape) are extended in the commit that adds each class, not batched (37.3-02)
- [Phase ?]: The shared provider-seam fake scripts the seam's answer, not the read's inputs: classification and the email rule live behind the seam, and a fake that re-applied them would be a second copy of the rule (37.3-03)
- [Phase ?]: The plan's zero-edit gate on tests/unit/test_adapter_interfaces.py was unsatisfiable — that file imports all three deleted result types by name; the closed-outcome-set cases became a seam-declares-no-enum claim instead (37.3-03)
- [Phase ?]: D-13 instance: the bounded cause 'empty' had no producer (an empty providerData classifies as anonymous and never reaches the rejection) and went with the sweep (37.3-03)
- [Phase 37.3]: 37.3-04: the five challenge rejections share one 409 declared once on ChallengeRejected; no subclass declares an error_class, so the anti-oracle property is structural
- [Phase 37.3]: 37.3-04: pre-claim rejections escape to the handler with no local catch — get_db is the single rollback boundary, and the test doubles are now faithful async generators
- [Phase 37.3]: 37.3-04: AuthEventResult deleted entirely — 44 members, not D-12's 43. AuthOperation survives for core.auth_challenges.operation
- [Phase 37.3]: 37.3-04: FOUND-08 carries a dated Phase 37.3 amendment naming VerifiedProviderIdentity and the raised ProviderLookupError hierarchy; SHARED-INVARIANTS re-check found no new conflict
- [Phase ?]: 37.4-07: three flagged conflicts, not five — the developer deleted the exactly-one-Authorization wire contract from SHARED-INVARIANTS.md and deleted FOUND-02, so D-10 and A-09 have no surviving binding text to diverge from; both are recorded under FOUND-01 as properties given up
- [Phase ?]: 37.4-07: the deleted wire rule survives verbatim in 01-foundation.md:40-46, 02-create-user.md:81/:69, 06-claim-anonymous-grant.md:86 and 11-sign-out-all.md:42 — reported under FOUND-01, not resolved; whether the phase briefs follow SHARED-INVARIANTS.md is a spec decision this phase had no direction on
- [Phase ?]: 37.4-07: the orphan idp-account-hash columns are on core.access_grants_anti_abuse, NOT core.provider_accounts as plan 37.4-05 reported — a later phase acting on the misattributed name would edit the wrong table
- [Phase 37.5]: The layering rule is in AGENTS.md and applies at write time: business logic in services/, database access in crud/, bodies in schemas/, tables in tables/, handlers in routers/, external-SDK seams in auth/ — with a one-line carve-out for errors.py, because SHARED-INVARIANTS.md requires the one shared error module to own the client-visible response shape (A-07/P-08)
- [Phase 37.5]: resolve_identity's four rejections stay with the query in crud/identities.py, and the admission rule stays in one place, app/dependencies.py::get_identity — splitting them would let a caller read a broken link as an unlinked pair (A-06)
- [Phase 37.5]: D-08's rule — delete a function that is only a step, keep one that states a rule or marks a boundary (a lock, a transaction, or a callable a library requires). A recursive function is NEVER a step: it cannot be inlined. 21 private single-caller definitions classified, 3 deleted and 18 kept, each with a written ground
- [Phase 37.5]: _sleep_if_positive is kept, correcting D-08's own deletion list — it is the callable tenacity's sleep= requires. The deletions are three, not four (A-04)
- [Phase 37.5]: QueueFullError has ALWAYS answered 503, not 429 — it subclasses ServiceUnavailable and declares no status. D-07's and D-11's status-flip argument is withdrawn as factually wrong (A-02/P-01); D-11's decision stands on the surviving arguments
- [Phase 37.5]: The circuit breaker and the execution gate stay hand-rolled. tenacity bounds one request (~91.5s) and nothing across requests; no installed package replaces a breaker, so finishing the idea means a NEW dependency. SHARED-INVARIANTS.md mandating `limits` is why the question keeps returning — the developer was reading the spec, not misremembering
- [Phase 37.5]: The quota charge sits inside ResiliencePolicy.admission() and outside tenacity's attempt(). Charging inside attempt() fails three ways at once — triple charge, 429 wrapped into a 503, and the quota rejection counted as a breaker failure. 37.4-REVIEW WR-01's diagnosis was adopted and its proposed on_admitted callback never was (A-01/P-03/P-04)
- [Phase 37.5]: assert_tree_total left src/ for tests/unit/error_tree.py — a module, not a conftest, because five cases invoke it from a bare `python -c` subprocess needing an explicit PYTHONPATH. Accepted consequence: a defective error tree no longer refuses to boot (D-09)
- [Phase 37.5]: ChallengeRequired had zero name references and is load-bearing — it is the only class answering a bare framework 409. A name-level assertion now stops a reference-grep reading it as dead. D-10's mandated-code ground is withdrawn; the dispatch ground carries the keep alone (A-12/P-05)
- [Phase 37.5]: A `pytest -k` gate that collects zero cases still passes. Three plans hit this — `-k` matches node-id substrings case-sensitively and the subjects were CamelCase class names. Verify by node id, and audit each `-k` term separately rather than the disjunction
- [Phase 37.5]: Deleted coverage leaves visibly: every plan names each deleted case and flags the ones whose survivor is an argument rather than a case. Two security cases cut without a survivor were restored by the developer in 658895e; one architectural guarantee was not, and is recorded as an open loss
