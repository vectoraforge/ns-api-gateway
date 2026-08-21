---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Authentication & Entitlements
current_phase: 35
current_phase_name: foundation
status: executing
stopped_at: Phase 35 context gathered
last_updated: "2026-08-21T21:17:35.532Z"
last_activity: 2026-08-20
last_activity_desc: Phase 34 complete, transitioned to Phase 35
progress:
  total_phases: 13
  completed_phases: 1
  total_plans: 16
  completed_plans: 4
  percent: 8
state_head: 08c16c14206afbc9669122abe33fa76ab19d7e5c
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-19)

**Core value:** The analysis pipeline must work reliably -- correct LLM invocation, proper resilience under load, and safe per-user data isolation.
**Current focus:** Phase 35 — foundation

## Current Position

Phase: 35 (foundation) — EXECUTING
Plan: 1 of 11
Status: Ready to execute
Last activity: 2026-08-20 — Phase 35 execution resumed (wave continue)

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

None.

### Blockers/Concerns

- RESOLVED (34-01): the PostgreSQL 17 blocker is cleared — developer started a postgres:17 container; server_version 17.11 (Debian 17.11-1.pgdg13+2) reachable on localhost:5432, database `nativespeaker` created and empty.
- OPEN: RESEARCH.md assumption A1 — introspection constants were captured on PostgreSQL 16.2 but the target is 17.11; plan 34-03 must re-capture them rather than copying RESEARCH.md Code Example 4.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260325-jrd | Fix tests: POST /chats returns empty content field | 2026-03-25 | ea6bea1 | [260325-jrd-fix-tests-post-chats-returns-empty-conte](./quick/260325-jrd-fix-tests-post-chats-returns-empty-conte/) |
| 260326-h2r | Fix incorrect content->message renames in unit tests | 2026-03-26 | 93f95da | [260326-h2r-i-renamed-the-follow-up-message-field-se](./quick/260326-h2r-i-renamed-the-follow-up-message-field-se/) |
| 260326-ico | Add OpenAPI tags, summaries, descriptions to all endpoints | 2026-03-26 | 52b7173 | [260326-ico-the-api-endpoints-have-no-descriptions-i](./quick/260326-ico-the-api-endpoints-have-no-descriptions-i/) |

## Session Continuity

**Last session:** 2026-08-21T02:25:36.309Z

Last activity: 2026-03-26
Stopped at: Phase 35 context gathered
Resume file: .planning/phases/35-foundation/35-CONTEXT.md

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 34 P01 | 3m | 1 tasks | 1 files |
| Phase 34 P01 | 10m | 2 tasks | 1 files |
| Phase 34 P02 | ~25 min | 3 tasks | 6 files |
| Phase 34 P03 | 42min | 3 tasks | 8 files |
| Phase 34 P04 | 38min | 2 tasks | 3 files |

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
