---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Authentication & Entitlements
current_phase: 37.1
current_phase_name: Refactor machine-generated code
status: planning
stopped_at: Phase 37.1 context gathered
last_updated: "2026-08-24T22:41:58.691Z"
last_activity: 2026-08-23
last_activity_desc: 37-10 complete — D-09's split fully realized; all 10 plans of phase 37 executed
progress:
  total_phases: 14
  completed_phases: 4
  total_plans: 31
  completed_plans: 31
  percent: 29
state_head: 74f719641dcb5c703b9d1e3311ad264ffb3ce4bb
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-19)

**Core value:** The analysis pipeline must work reliably -- correct LLM invocation, proper resilience under load, and safe per-user data isolation.
**Current focus:** Phase 37.1 — refactor-machine-generated-code

## Current Position

Phase: 37.1 — Refactor machine-generated code
Plan: Not started
Status: Ready to plan
Last activity: 2026-08-23 — Phase 37 complete, transitioned to Phase 38

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

None.

### Roadmap Evolution

- Phase 37.1 inserted after Phase 37: Refactor machine-generated code (URGENT)

### Blockers/Concerns

- RESOLVED (34-01): the PostgreSQL 17 blocker is cleared — developer started a postgres:17 container; server_version 17.11 (Debian 17.11-1.pgdg13+2) reachable on localhost:5432, database `nativespeaker` created and empty.
- OPEN: RESEARCH.md assumption A1 — introspection constants were captured on PostgreSQL 16.2 but the target is 17.11; plan 34-03 must re-capture them rather than copying RESEARCH.md Code Example 4.
- Deferred (37-10): the ~48s worst-case provider latency on the completion path is a policy decision on a shared budget — resolve with phases 40/41/42, which share the adapter seam.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260325-jrd | Fix tests: POST /chats returns empty content field | 2026-03-25 | ea6bea1 | [260325-jrd-fix-tests-post-chats-returns-empty-conte](./quick/260325-jrd-fix-tests-post-chats-returns-empty-conte/) |
| 260326-h2r | Fix incorrect content->message renames in unit tests | 2026-03-26 | 93f95da | [260326-h2r-i-renamed-the-follow-up-message-field-se](./quick/260326-h2r-i-renamed-the-follow-up-message-field-se/) |
| 260326-ico | Add OpenAPI tags, summaries, descriptions to all endpoints | 2026-03-26 | 52b7173 | [260326-ico-the-api-endpoints-have-no-descriptions-i](./quick/260326-ico-the-api-endpoints-have-no-descriptions-i/) |

## Session Continuity

**Last session:** 2026-08-24T22:41:58.671Z

Last activity: 2026-03-26
Stopped at: Phase 37.1 context gathered
Resume file: .planning/phases/37.1-refactor-machine-generated-code/37.1-CONTEXT.md

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
