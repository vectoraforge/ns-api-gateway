---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Authentication & Entitlements
current_phase: 43
current_phase_name: POST /webhooks/app-store
status: executing
stopped_at: Completed 43-05-PLAN.md
last_updated: "2026-09-04T23:16:59.180Z"
last_activity: 2026-09-04
last_activity_desc: Phase 43 execution started
state_head: 0a1d6edc2e664977972db2e7e5ea5e1199f6adf0
progress:
  total_phases: 18
  completed_phases: 13
  total_plans: 103
  completed_plans: 102
  percent: 72
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-19)

**Core value:** The analysis pipeline must work reliably -- correct LLM invocation, proper resilience under load, and safe per-user data isolation.
**Current focus:** Phase 43 — POST /webhooks/app-store

## Current Position

Phase: 43 (POST /webhooks/app-store) — EXECUTING
Plan: 6 of 6
Status: Ready to execute
Last activity: 2026-09-04 — Phase 43 execution started

<!-- Counts read against disk rather than incremented (41-05). At Task 3 time: 90 PLAN files and 89
     SUMMARY files across .planning/phases/, which is exactly what the frontmatter already carried,
     so nothing needed correcting. 41-05's own summary is the ninetieth and landed after Task 3, at
     which point `state advance-plan` reported `last_plan` and `completed_plans` went 89 -> 90.
     Phase 41 itself: 5 plans, 5 summaries. The phase is executed, not yet verified, so
     `completed_phases` stays at 11. -->

<!-- Counts read against disk rather than incremented, as 41-05 did. At Task 3 time: 96 PLAN files and
     95 SUMMARY files across .planning/phases/, and the frontmatter carried 96 and 95. This plan's own
     summary is the ninety-sixth and lands after Task 3, at which point completed_plans goes 95 -> 96.
     Phase 42 itself: 6 plans, 6 summaries. The phase is executed, not yet verified, so
     completed_phases stays at 12. -->

**Phase 42 outcome.** `POST /auth/claim-registered-grant` ships. A linked **registered** caller — stored
provider `google` or `apple` — spends a challenge and reaches one of two destinations, chosen inside one
locked transaction. A clean account gets a new grant on the `registered` tier behind Apple's bit1. An
account holding an active `anonymous_device_grant` is **converted**: the anonymous row is expired, the
registered row is inserted after it, and the usage counters carry across unchanged. The conversion calls
Apple not at all. Three tables left the one migration with everything only they needed — the anti-abuse
receipt and the two provider-account tables — so an anonymous claim now writes three rows, not four.
Every outcome is an executed case: ten post-claim outcomes each consuming exactly once, four refusals
sharing one byte-identical 403, three Apple failure arms, and two live two-connection races, one per
destination. Six divergences from `07-claim-registered-grant.md` and `06-schema-reference.md` are
recorded as **flagged conflicts** under REGGRANT-01…03 rather than resolved by editing either file.
Suite **1001 unit / 237 e2e / 147 schema**, `ruff check src tests` clean. **Recorded as accepted rather
than fixed:** the unbounded Apple round trips on the new-grant path (D-16), on the Phase 41 D-20
precedent.

**Phase 41 outcome.** `POST /auth/claim-anonymous-grant` ships: a linked **anonymous** caller spends a
challenge, Apple's bit0 is read and set through the new ES256-signed `auth/devicecheck.py` seam, and
four rows go in one flush under the fixed two-tier lock order — the grant on the `anonymous` tier, its
anti-abuse row, its usage row and `free_grant_consumed_at`. Every non-happy outcome is an executed
case: the idempotent repeat, four refusals sharing one byte-identical 403 across three log events, and
three Apple failure arms. A live two-connection race against real PostgreSQL proves one allocation and
found a genuine 500 on the loser's path, now fixed. Four divergences from `06-claim-anonymous-grant.md`
are recorded as **flagged conflicts** under ANONGRANT-01…03 rather than resolved by editing the brief.
Suite **950 unit / 226 e2e / 134 schema**, `ruff check src tests` clean.

⚠️ **Corrected by Phase 42 (D-07), 2026-09-03.** The paragraph above says four rows go in one flush and
names the anti-abuse row among them. That was true until this date. `core.access_grants_anti_abuse` and
its model were deleted, and the anonymous writer stopped writing the receipt row, so **one successful
anonymous claim now writes three rows**: the grant, its usage row and `free_grant_consumed_at`. The
device platform is still recorded, on the identity row's `native_claim_platform` column, which survives
with the `core.native_claim_provider` enum that types it. Nothing else in the paragraph changed. The
text is left as written, because it records what Phase 41 delivered.

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
- RESOLVED (41-02, A-15): the database pool no longer exhausts at three concurrent chat posts. `config/config.yaml` declares `db.pool_size: 12` (`resilience.pool_size × 2 + 2`), and the pool wait no longer holds a provider permit — the permit moved off the admission path and around the retry loop (D-15). Original finding: the database pool exhausts at three concurrent chat posts. `db.pool_size` defaults to 5 (`config.py:25`) with `max_overflow=0` (`app/lifespan.py:34`) and a `POST /chats` holds two connections. Phase 37.5 did not create this but moved the stall inside the LLM permit, so a pool wait now also holds a provider permit. **Recorded, not fixed — the developer owns the choice.** One-line change: raise `db.pool_size` to at least `resilience.pool_size × 2 + 2` (12 at the configured values), or accept the ceiling.
- ACCEPTED (41-05, D-20): every eligible claim makes an unbounded pair of Apple DeviceCheck round trips. `06-claim-anonymous-grant.md:79` forbids any cached or coalesced substitute for the bit read or the bit write — every claim performs its own — and that rule is right, because a cached bit is a bit that can be stale in the direction that hands out a second grant. With the backend rate-limit engine deleted from the product (Phase 35 D-05) and the Envoy gateway contract deferred to v2.1 (Phase 35 D-08), a caller holding a valid ID token for an **eligible** anonymous account can make the backend call Apple as often as it can prepare challenges. **Mitigating:** it is one account looping on itself, not a fan-out — the caller must already hold a valid token for an existing linked anonymous account; the eligibility preflight (D-03) refuses an ineligible account before Apple is reached, so the loop is only open to an account that has not yet claimed; and each turn additionally costs a fresh challenge from `POST /auth/challenge`. **Closes with:** the v2.1 gateway contract. Recorded as **accepted, not as an open defect** — it is a consequence of a decision this project made three phases ago, and filing it as a new problem would misrepresent it. Same treatment Phase 40 D-22 gave the unbounded Firebase read; recorded under ANONGRANT-01 in `REQUIREMENTS.md`.
- ACCEPTED FACT ABOUT THE WORLD, not a gap the phase left (41-05, D-04): **no real round trip to Apple has ever been made.** No iOS app exists, so nothing can produce a real DeviceCheck device token. The wire shapes `auth/devicecheck.py` implements — the host, the query and update paths, the request bodies and the five ordered response-parse arms — come from secondary sources and are marked `[ASSUMED]`; no official Apple page was fetchable during research. `tests/unit/test_devicecheck_adapter.py` carries that provenance in its module docstring. **The first real 400 or 401 from Apple is authoritative over anything in this repository**, and reads as evidence about those literals rather than as a regression. Written down so a later reader does not treat the 21 green adapter unit cases as evidence the integration works — they pin the seam's behaviour, not the wire.
- ACCEPTED (42-06, D-16): every eligible **new-grant** claim on `POST /auth/claim-registered-grant` makes an unbounded pair of Apple DeviceCheck round trips, for the same reason the anonymous route does. **Mitigating:** the caller must already hold a valid token for a linked `google` or `apple` account; the preflight refuses an ineligible account before Apple is reached; each turn costs a fresh challenge. **Narrower than the anonymous route:** the conversion destination reaches Apple not at all (D-02), so an account holding an active anonymous grant cannot use this route to reach Apple even once. **Closes with:** the v2.1 gateway contract. Recorded as accepted, not as an open defect, and recorded under REGGRANT-01 in `REQUIREMENTS.md`.
- OPEN (37.5-06): a real coverage loss. `test_foundation_calls_no_adapter_method_anywhere_in_src` was the only enforcement that `get_user_provider_data` is named nowhere in `src/` outside `auth/adapters.py` and `auth/firebase.py`. The property holds today by grep, but nothing fails if a third file starts calling the adapter. ~25 lines to restore, with its allow-list and two controls. Not restored — unlike the two security cases the developer restored in `658895e`.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260325-jrd | Fix tests: POST /chats returns empty content field | 2026-03-25 | ea6bea1 | [260325-jrd-fix-tests-post-chats-returns-empty-conte](./quick/260325-jrd-fix-tests-post-chats-returns-empty-conte/) |
| 260326-h2r | Fix incorrect content->message renames in unit tests | 2026-03-26 | 93f95da | [260326-h2r-i-renamed-the-follow-up-message-field-se](./quick/260326-h2r-i-renamed-the-follow-up-message-field-se/) |
| 260326-ico | Add OpenAPI tags, summaries, descriptions to all endpoints | 2026-03-26 | 52b7173 | [260326-ico-the-api-endpoints-have-no-descriptions-i](./quick/260326-ico-the-api-endpoints-have-no-descriptions-i/) |

## Session Continuity

**Last session:** 2026-09-04T23:16:46.637Z

Last activity: 2026-08-31
Stopped at: Completed 43-05-PLAN.md
Resume file: None

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
| Phase 41 P01 | 20 min | 2 tasks | 27 files |
| Phase 41 P02 | 38 min | 3 tasks | 8 files |
| Phase 41 P03 | 20 min | 3 tasks | 8 files |
| Phase 41 P04 | 20 min | 2 tasks | 3 files |
| Phase 41 P05 | 12 min | 3 tasks | 3 files |
| Phase 42 P01 | 30m | 3 tasks | 10 files |
| Phase 42 P02 | ~45 min | 2 tasks | 9 files |
| Phase 42 P03 | ~10 min | 2 tasks | 2 files |
| Phase 42 P04 | ~20 min | 2 tasks | 2 files |
| Phase 42 P05 | ~40 min | 2 tasks | 1 files |
| Phase 42 P06 | ~35 min | 3 tasks | 5 files |
| Phase 42 P07 | 32 | 3 tasks | 11 files |
| Phase 43 P01 | 17min | 2 tasks | 23 files |
| Phase 43 P02 | 4min | 2 tasks | 2 files |
| Phase 43 P03 | 12min | 3 tasks | 9 files |
| Phase 43 P04 | 20min | 3 tasks | 7 files |
| Phase 43 P05 | 12min | 3 tasks | 4 files |

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
  - ⚠️ Corrected by Phase 42 (D-07), 2026-09-03: the table and both deferrable FKs are deleted, so a free-source grant now seeds with no companion row and `seed_grant` no longer takes `with_anti_abuse`. The default of `source=manual` is unchanged. The entry is kept, because the constraint it names was real when it was written.
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
  - ⚠️ Corrected by Phase 42 (D-07 and D-08), 2026-09-03: both tables are deleted, so neither column exists and the misattribution can no longer mislead anyone. D-08 declines to rebuild the hash, the key or the key version anywhere; `provider_uid` stays raw in `core.external_identities`. The entry is kept as the record of a real reporting error.
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
- [Phase 41]: D-14: the circuit breaker is consulted before every attempt, not only at admission — The per-attempt check sits inside the try with the (QueueFullError, CircuitOpenError) pass-through arm above the generic one, so the breaker refusal reaches the caller as its own 503 with Retry-After and is never recorded as a provider failure.
- [Phase 41]: D-15: admission takes the in-flight slot alone; the provider permit is taken around the retry loop — LLMExecutionGate.hold split into inflight_slot and concurrency, and hold was deleted (no caller outside the module). The quota charge commits and releases its connection before the request waits for a permit, and an open breaker or full queue still answers 503 having spent nothing.
- [Phase 41]: D-16: db.pool_size is 12, declared in the tracked config.yaml rather than as a Python default — The partial db: block deep-merges with the DB_* env nesting exactly as the jwt: precedent predicted, now proved by a case rather than assumed. Trade-off: the tracked YAML forecloses DB_POOL_SIZE from .env, which nothing sets and .env.example does not document.
- [Phase 41]: Free-grant lifetime arms evaluated before the other-source arm: an account both ineligible and holding another grant logs free_grant_already_consumed; the client answer is identical either way
- [Phase 41]: ClaimRefused is a pure group base raised from nowhere, exactly as ChallengeRejected and UpgradeRefused are
- [Phase 41]: Structural ast tests ship with a control, and the single-writer walk was additionally mutation-checked against the real tree
- [Phase 41]: 41-04: the race loser's rollback expired the two rows the router still reads, so a genuine claim race answered 500; the loser arm now reloads identity.user and identity.identity before returning — A SQLAlchemy rollback expires every instance in the session; the router's identity.user.id then lazy-loads with no greenlet. Found by the live two-connection race, invisible to the stub-session unit case.
- [Phase 41]: 41-04: lock tiers are asserted over the SQL the production writer actually emits (captured at before_cursor_execute), not over a literal that mirrors the crud — A mirrored literal can pin what the two known tiers look like but cannot detect a third tier a future writer adds, which is the threat the assertion exists for.
- [Phase 41]: 41-04: FREE_GRANT_SOURCES is tied to the live lifetime index predicate's membership, proven to fire by a mutation that was applied, observed to fail and reverted — Phase 42 narrowing the constant back to one member would silently reopen a spent lifetime slot for every account that already used one.
- [Phase 41]: The DeviceCheck Protocol is declared beside its implementation in `auth/devicecheck.py`, not in `auth/adapters.py` — that module is fenced by an import allowlist that excludes `httpx`, so a Protocol there would fail `test_adapter_interfaces.py`; it is also FOUND-08's forward-flag treatment, an interface defined with its first implementation rather than declared ahead of one.
- [Phase 41]: The seam holds no logger at all — not a redacting one — so no code path exists that could write a raw device token to a log line.
- [Phase 41]: The DeviceCheck update call carries both bits, with bit1 carried forward from the read rather than fabricated — writing a bit1 this phase invented would silently destroy state this phase does not own, and Phase 42's registered claim is the feature that owns it.
- [Phase 41]: The eligibility read carries no status predicate, because `ix_access_grants_one_free_grant_per_user_source` carries none — the lifetime rule and the index that enforces it must agree, or a revoked free grant reads as a fresh slot.
- [Phase 41]: For two simultaneous first claims the arbiter is the unique index, not the lock — with no grant row to lock, `FOR UPDATE` locks nothing, so the concurrency guarantee rests on `ix_access_grants_one_free_grant_per_user_source` and `ix_access_grants_one_active_per_user` refusing the second insert, and the IntegrityError is caught without naming a constraint or parsing a message.
- [Phase 41]: The shared completion sequence grew an injected post-claim callable rather than forking — `AuthService._complete` takes a `PostClaim`, and the two Firebase routes pass `partial(self._read_then_write, write=...)`; a second copy of locate-claim-commit-work-spend is the thing Phase 40 D-16 forbids.
- [Phase 41]: Both services on this route share one captured instant through a FastAPI dependency rather than reading the clock twice — `get_evaluated_at` makes SHARED-INVARIANTS § Grants' one-evaluation-time rule structural instead of a convention two call sites must remember.
- [Phase 41]: 41-05: a specification divergence is recorded under the requirement it belongs to, never resolved by editing the specification — the brief and SHARED-INVARIANTS.md stay verbatim — Four new flagged conflicts against 06-claim-anonymous-grant.md (iOS-only gate, database before Apple, anonymous claimants only, the idempotent repeat) live under ANONGRANT-01..03 with what the brief asks and what shipped, so a reader of the brief finds the divergence rather than discovering it.
- [Phase 41]: 41-05: a brief-versus-invariants conflict is resolved by precedence and counted only among the divergences, not among the flagged conflicts — The brief's step 11 locks the target user before the grant set and SHARED-INVARIANTS forbids it; the invariants win, so the code obeys binding text rather than diverging from it. A flagged conflict is reserved for a knowing divergence FROM binding text.
- [Phase 41]: 41-05: the header's flagged-conflict count is ten and the set of known divergences sixteen, re-derived against six named SHARED-INVARIANTS sections rather than inherited; the gap of six is enumerated — All four new conflicts are against the brief; not one invariant section produced a new divergence. The gap between the two numbers is the difference between a counted conflict and a recorded override, forward flag or precedence resolution, and has been kept deliberately since Phase 37.5.
- [Phase 42]: D-07 executed: the anti-abuse receipt table and the two provider-account tables left the one migration with everything only they needed; core.native_claim_provider stays as the record of the device platform
- [Phase 42]: D-08 held: no hash column, no key and no key-version surface exists anywhere in src/ or migrations/; provider_uid stays raw
- [Phase 42]: 42-02: research assumption A1 is false — SQLAlchemy 2.0.46 emits the conversion's UPDATE before its INSERT even in one flush; the explicit flush boundary is kept as the guard against an ORM upgrade inverting it
- [Phase 42]: 42-02: D-09's guard is the grant history read by source and status at both layers; neither free_grant_consumed_at nor has_prior_free_grant may be a blanket eligibility test, because both are true on the conversion path
- [Phase 42]: 42-02: AnonymousGrantClaimRequest is renamed GrantClaimRequest and shared by both claim routes; ClaimantNotRegistered is the fourth ClaimRefused leaf and adds no ErrorCode member
- [Phase 42]: 42-03: reuse by import, not by copy — the registered precedence module imports the anonymous module's stubs, which stays byte-identical
- [Phase 42]: 42-03: the four claim refusals are asserted byte-identical on the wire at both depths, so the route is no account-state oracle
- [Phase 42]: 42-04: two walk classes rather than one parametrized pair, so the anonymous cases stay byte-identical; the helpers took a defaulted member argument
- [Phase 42]: 42-05: the conversion race holds at the challenge commit, not the first flush — a conversion takes the grant row lock before it flushes, so a flush barrier deadlocks by construction
- [Phase 42]: 42-05: the conversion loser raises no IntegrityError — it is refused by the writer's in-lock re-decision having written nothing; the unique indexes arbitrate the new-grant destination only
- [Phase 42]: 42-06: a divergence is recorded under the requirement it belongs to, and the specification is never edited to remove it — this now covers a copy of the specification too. `.planning/auth-refactor-endpoint-changes.md` is verbatim brief text; it got a dated header note pointing at REQUIREMENTS.md, and not one edited step.
- [Phase 42]: 42-06: `requirements.mark-complete` applied nothing for the three REGGRANT ids and returned `table_unmatched` for all three — the traceability row is a range the tool does not expand, and the checkboxes were already ticked, so both surfaces were finished by hand. Measured, not predicted; the same result 41-05 recorded, one step worse.
- [Phase 42]: 42-06: ROADMAP criterion 4 is reworded, not withdrawn — an account holding an ACTIVE anonymous grant is converted rather than refused, so the criterion's single implied answer is two answers; the property it protects, that no account ends with two free entitlements, holds on both paths.
- [Phase 42]: 42-06: the flagged-conflict count is sixteen and the set of known divergences twenty-three, re-derived against six named SHARED-INVARIANTS sections rather than inherited; the gap of seven is enumerated. Not one invariant section produced a divergence, and the invariants name no anti-abuse row at all — the phase's largest deletion diverges from the schema reference and the brief, and from no invariant text.
- [Phase 42]: 42-06: two counts in the traceability table had been stale since Phase 41 updated the header alone; a count is re-derived against the sections it summarises, and a table that disagrees with its own header is corrected rather than left as evidence.
- [Phase 42]: 42-07: the index question is asked before Apple; the two predicates are answered by two reads, and the status-only read carries no time window because a partial index predicate must be IMMUTABLE
- [Phase 42]: 42-07: crud writers return a three-valued ActivationOutcome; refused is a 403 and only lost_race is the repeat's 200, with a backstop re-read after every race
- [Phase 42]: 42-07: only SQLSTATE 23505 is a lost race; the class is read off violation.orig.__cause__.sqlstate so the crud module still imports no driver
- [Phase 43]: 43-01: A mid-term tier change updates core.subscriptions.tier_id in place; the unique index on (provider, external_id) allows one row per lifecycle key, and old_tier_id/new_tier_id on the event record the change (43-CONTEXT.md discretion, recorded).
- [Phase 43]: 43-01: The ingestion lost race raises the generic InternalError, not a fourth error leaf, because the phase artifact list fixes the new exception classes at three; a WARNING with a closed-set provider label is written before the raise.
- [Phase 43]: 43-01: status_at's arm order is revoked, live expires_at, grace, billing retry, expired. Grace is tested before billing retry because Apple sets the retry flag during grace too. This closes 43-RESEARCH assumption A1.
- [Phase 43]: 43-02: The .env.example App Store block names no variable in its prose, only on the three assignment lines — the plan's own gate counts matching lines, so a helpfully repeated name would fail it
- [Phase 43]: 43-02: APP_STORE_ROOT_CERTIFICATE_PATH is named nowhere in .env.example, not even in a comment; the block states the default path config/certs/AppleRootCA-G3.cer instead
- [Phase 43]: 43-02: The gateway per-IP and per-URL limits the brief requires stay deferred to the v2.1 gateway contract (D-06, Phase 35 D-05/D-08); 43-06 should record this with 43-01's uncredentialed-route residual, because one limit closes both
- [Phase 43]: 43-03: core.store_purchases.identity_value is the presented attribution token whenever the notification carries one; a server-generated UUID only when the store gives none. The plan's broader spelling would make every repeat delivery of a token-bearing but unbound purchase a permanent AttributionConflict.
- [Phase 43]: 43-03: the conflict arm fires only when the notification presents a token; a delivery carrying no appAccountToken disagrees with nothing.
- [Phase 43]: 43-03: an owner is added to core.subscriptions.user_id, never cleared, so a token-less renewal cannot strip a link restore created.
- [Phase 43]: 43-04: the ingestion writer locks lock_active_grants first and lock_effective_grants second, mirroring the registered writer — a renewal's superseded grant is time-ended and outside the effective set, so the effective read alone would 500 on every Apple retry for ever
- [Phase 43]: 43-04: when the subscription is entitled, every grant the buyer holds is superseded, not this subscription's alone — ix_access_grants_one_active_per_user allows one active grant per user, so a manual or a second subscription's grant must end before the paid one lands
- [Phase 43]: 43-04: FREE_GRANT_SOURCES is not named by the subscription writer — the free grant is expired because it is one of the buyer's held grants, and a source test would be a second, narrower copy of a rule the index already carries
- [Phase 43]: 43-04: ENTITLED_STATUSES names the set core.subscriptions.product_entitled_subscription_id is generated over, once, in crud/subscriptions.py; the deferrable foreign key is the backstop and was shown to fail the commit, not the mechanism
- [Phase 43]: 43-05: REFUSAL_STAGES is derived from the library's VerificationStatus set less OK, with a control asserting the derivation, so an arm the library adds becomes a new parameter instead of a silent gap
- [Phase 43]: 43-05: the two library environment values that skip signature verification (Xcode, LocalTesting) are named as string literals in tests, never imported from the library enum, so the case catches a library change instead of following it
- [Phase 43]: 43-05: the unconfigured-seam e2e case swaps in a real AppStoreNotifications(verifier=None) rather than scripting Unavailable on the fake, so the 503 comes from the production fail-closed path
- [Phase 43]: 43-05: Phase 42's post-rollback expiry hazard does not recur on the ingestion path -- _settle logs off the frozen VerifiedNotification and the router reads nothing, so no re-read was added
