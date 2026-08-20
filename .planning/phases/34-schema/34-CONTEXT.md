# Phase 34: Schema - Context

**Gathered:** 2026-08-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the complete v2.0 auth schema as a single pogo-migrate SQL migration that applies in one shot against an empty database. The only artifacts are the migration file and schema-conformance tests.

Explicitly NOT in this phase: application code, routes, handlers, SQLModel models, repository/query layer, config, or any test of business behavior. Existing code in `src/nativespeaker/api/` references dropped columns and tables (`core.users.jwt_sub`, `core.users.subscription_plan`, `core.usage_monthly`, `core.subscription_events`, the `core.subscription_plan` enum) and **will not import after this commit**. That is expected and accepted — Phase 35 builds the foundation and Phase 36 is the first bootable integration gate. Do not soften the schema to keep legacy code alive, and do not retain legacy columns "just in case".

Pre-launch database, no production users, disposable data. Destructive drops are correct: no data migration, no backfill, no compatibility shim, no dual-write window, no deprecated aliases.

</domain>

<decisions>
## Implementation Decisions

### Migration File Shape

- **D-01:** One migration file, rewritten from scratch — the six-file sequence in `00-schema.md §1`/`§2` is **overridden**. There is no baseline to migrate *from*: the apply target is an empty database, so the teardown migration (`§2`) has nothing to tear down and its `ALTER TABLE core.users` collapses into a direct `CREATE TABLE`. Carried forward from PROJECT.md Key Decisions and the Phase 27 precedent (D-01, v1.6). Recorded here per the SHARED-INVARIANTS conflict rule — flagged, not silently resolved. — **Reversibility:** one-way — once the file is the sole migration and the dev database is rebuilt from it, restoring a six-file incremental sequence means reconstructing a baseline state that no longer exists anywhere.

- **D-02:** The file is **renamed** to `migrations/20260818_01_initial-release.sql`. The old `20260322_01_initial-release.sql` is deleted, not edited in place. The `initial-release` slug is kept — it is still literally the initial release — and the `20260818` date matches the ids the spec's own sequence used (`20260818_01…05`). — **Reversibility:** costly — the filename stem *is* pogo's migration id, so any database with the old id applied must be dropped and rebuilt. `§9.13` already mandates exactly that for the disposable dev database.

- **D-03:** `-- depends:` stays **empty**. This remains the root migration; nothing precedes it.

- **D-04:** The description header is rewritten to describe the v2.0 schema. The current line ("initial release with users, subscriptions, and usage") names tables this migration no longer creates.

- **D-05:** `-- migrate: rollback` is two statements: `DROP SCHEMA IF EXISTS audit CASCADE;` then `DROP SCHEMA IF EXISTS core CASCADE;`. Chosen over an explicit ~35-object reverse-order drop list specifically because it cannot drift out of sync with the apply section. — **Reversibility:** reversible — the rollback body is independent of everything else in the file.

- **D-06:** The apply section is organized into **five banner-commented sections in the spec's order**: enums → identity/tiers → subscriptions/store → grants/anti-abuse/usage → challenges/audit. This preserves `§1`'s non-negotiable statement ordering by construction and makes the single file reviewable against `00-schema.md §3–§7` section by section.

### Schema Content

- **D-07:** Every table, column, enum, CHECK, foreign key, delete behavior, and index is **dictated by `00-schema.md §3–§8`** — transcription, not design. No gray areas were opened here and none should be invented during planning.

- **D-08:** `00-schema.md §9` rulings supersede any contrary prose elsewhere in the spec. Do not "restore" an older shape that reads more naturally. In particular: `promo` is deleted from `core.access_grant_source` (four values only); `invalid_attestation_or_integrity_proof` is deleted from `core.auth_event_result`; the product-entitled set in the `core.subscriptions` generated column is fixed at `('active','grace_period')` and is never a runtime toggle; open-ended grants are legal (`ends_at` nullable).

- **D-09:** `§1`'s prohibition holds absolutely — no triggers, stored procedures, rules, views, materialized views, extensions, partitioning, `NULLS NOT DISTINCT`, invented format CHECKs, scheduled-job scaffolding, or `ON UPDATE`/`ON DELETE` clauses beyond those `§8` enumerates. `updated_at` is maintained by application writes, never by a trigger.

### Database Role / REVOKE

- **D-10:** Take the **comment-only branch** of `§8`'s final bullet. This repository defines no database role — only a `DB_USER` placeholder in `[tool.pogo] database_config` and `docker-compose.yml`. A prominent comment at the `core.external_identities` definition states the `REVOKE DELETE ON core.external_identities` requirement for whoever provisions roles. Do **not** invent a role; `§8` explicitly warns against it and it would collide with whatever the Kubernetes deployment actually provisions.

- **D-11:** The REVOKE requirement is **also** recorded in PROJECT.md's "Known areas for future work". The migration comment reaches whoever reads the SQL; the project note reaches whoever provisions the cluster — different people.

### Conformance Tests

- **D-12:** The `§10` constraint-rejection tests **ship in this phase**. `§10` calls them "optional but recommended" but SCHEMA-08 requires every `§10` check to pass, and `§10` enumerates nine specific rejection cases. They are also the only tests that can run at all until Phase 36.

- **D-13:** They live in a **new `tests/schema/` package**, sibling to `unit/` and `e2e/`, with its own `conftest.py` and a raw driver connection. **Zero imports from `nativespeaker.api`** — `tests/e2e/conftest.py` imports `nativespeaker.api.app.main` and runs the app lifespan, and pytest applies that conftest to every subdirectory beneath it, so nothing under `tests/e2e/` can run while the app is broken. The root `tests/conftest.py` is already minimal and adds nothing that would break. — **Reversibility:** reversible — a self-contained new directory.

- **D-14:** A **session-scoped fixture runs `pogo apply`** against a dedicated test database and drops it afterward. This makes the suite self-contained and turns `§10`'s first acceptance check — a fresh apply against an empty database succeeds — into something the suite exercises rather than merely asserts about.

- **D-15:** Seeding uses **small typed insert helpers** (`insert_user()`, `insert_tier()`, `insert_grant(...)`, each returning the new id) with per-test transaction rollback. Rejected session-scoped shared rows: the tests asserting "a second active grant for one user is rejected" and "a second free grant of the same source is rejected even after the first is expired" mutate shared state and would become order-dependent.

- **D-16:** Add a test that **`core.external_identities.user_id`'s `ON DELETE RESTRICT` blocks deleting a `core.users` row that has an identity row.** Not in `§10`'s list, but it is the one part of "identity rows are never deleted" the schema can enforce without a role, and `§8` calls that FK out as deliberate.

### Acceptance Proof

- **D-17:** The `§10` object inventory is proven by **introspection tests** in `tests/schema/` querying `pg_catalog` / `information_schema`. Not a manual runbook, not reviewer eyeball — index predicates and enum label sets are exactly what human review of a 500-line hand-written DDL file misses.

- **D-18:** Inventory assertions are **exact-set, not superset**: full name-set equality for enum types, tables per schema, and indexes, plus assertions that there are zero triggers, views, and materialized views. `§1` says "add nothing that is not listed in this file", and only exact-set equality catches the stray object added later.

- **D-19:** Index predicates are asserted as **normalized predicate text** via `pg_get_expr(indpred, indrelid)`, with expected strings **captured from a real applied database** rather than guessed — PostgreSQL rewrites predicates on storage. Covers the five unique indexes with their exact predicates and the two non-unique partial indexes named in `§10`.

- **D-20:** A **dedicated apply/rollback test** applies the migration to a scratch database, runs `pogo rollback`, and asserts neither `core` nor `audit` remains. The session fixture's database drop is not the same code path and proves nothing about the rollback section.

### Claude's Discretion

- Inline commenting depth for the non-obvious constraints — the four-arm anti-abuse CHECK, the STORED generated column, the actor-field CHECKs on `audit.auth_events`.
- Whether `§9` ruling numbers are cited inline in the SQL at the points where a more "natural-looking" alternative was deliberately rejected.
- Choice of raw driver for `tests/schema/` (asyncpg vs psycopg) and whether the suite is sync or async.
- Exact test file split within `tests/schema/` (one module vs inventory / constraints / rollback split).
- How the session fixture names and reaches the dedicated test database.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Binding Specification

- `/home/init/native-speaker/specs/auth-refactor-phases/00-schema.md` — The phase specification. `§3–§7` contain the DDL to transcribe; `§8` the retention, delete-behavior, and cascade rules; `§9` the rulings that override contrary spec prose; `§10` the acceptance checks SCHEMA-08 requires. `§1`/`§2`'s six-file structure is overridden per D-01 — read them for **statement ordering and the prohibition list**, not for file layout.
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — Binds every phase and **wins over any conflicting phase brief**. Flag conflicts, never resolve them silently. "Global deletions" lists things to build in no phase.

### Project Planning

- `.planning/REQUIREMENTS.md` — SCHEMA-01 … SCHEMA-08, the eight requirements this phase must satisfy.
- `.planning/ROADMAP.md` — Phase 34 goal, dependency position (root of the graph), and success criteria.
- `.planning/PROJECT.md` — Key Decisions table records the rewrite-in-place override and the v2.0 constraint "one initial migration, never add incremental migrations".

### Current Implementation

- `migrations/20260322_01_initial-release.sql` — The file being replaced. Its baseline state is what `00-schema.md §0` expresses its delta against; also the reference for pogo header shape (`-- <description>`, `-- depends:`, `-- migrate: apply`, `-- migrate: rollback`).
- `pyproject.toml` `[tool.pogo]` — `migrations = './migrations'`, `database_config` with `{DB_USER}` placeholder, `schema = 'api'` for pogo's own migration-tracking table.
- `tests/conftest.py` — Minimal shared root; safe for a new `tests/schema/` sibling.
- `tests/e2e/conftest.py` — **Read to understand the constraint, not to reuse.** Imports `nativespeaker.api.app.main` and runs the app lifespan; applies to every subdirectory under `tests/e2e/`.
- `docker-compose.yml` — Local PostgreSQL with a `POSTGRES_USER` placeholder; no role definitions anywhere in the repo.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- pogo-migrate ≥0.4.2 is already a project dependency and configured — no new tooling.
- The existing migration file supplies the exact pogo header shape to copy.
- The project already runs tests against real PostgreSQL, so the infrastructure assumption is established.

### Established Patterns

- **Migration rewrite over incremental ALTER** — Phase 27 (v1.6) set this precedent for a pre-launch database with disposable data. Phase 34 repeats it.
- **Per-test transaction rollback** — the project's isolation convention (`join_transaction_mode=create_savepoint` in the SQLModel e2e suite). `tests/schema/` reproduces the *intent* on a raw connection, not the SQLModel mechanism.
- **Native PostgreSQL enum types for all domain enums** — established in v1.6; the eleven enums here continue it.

### Integration Points

- **Downstream, not in this phase:** `src/nativespeaker/api/models/*.py` SQLModel definitions diverge from the database at this commit and are rewritten in Phase 35/36. Do not touch them here.
- `[tool.pogo] schema = 'api'` tracks applied migration ids. Renaming the file changes its id, so any database holding the old id must be dropped and rebuilt — which `§9.13` requires regardless.
- Phase 35 (foundation) and every endpoint phase declare Phase 34 as a hard dependency and compile against this schema.

</code_context>

<specifics>
## Specific Ideas

- Expected index-predicate strings must be **captured from a real applied database**, not hand-written from the spec — PostgreSQL normalizes predicate expressions when it stores them, so a spec-verbatim string will not match.
- The exact-set inventory to assert, from `§10`: schemas `core` and `audit`; 11 enum types; 15 `core` tables; 2 `audit` tables; five named unique indexes with their exact predicates; two named non-unique partial indexes; and the confirmed absence of `core.subscription_plan`, `core.usage_monthly`, `core.subscription_events`, and `core.users.jwt_sub`.
- The nine rejection cases from `§10` are enumerated there explicitly — plus the four *valid* anti-abuse evidence tuples (native iOS, native Android, web anonymous, registered), which must insert successfully.

</specifics>

<deferred>
## Deferred Ideas

- **Full `§8` cascade-list introspection** — asserting all five ON DELETE CASCADE relationships and every NO ACTION default, beyond the single `ON DELETE RESTRICT` test in D-16. Considered and scoped down: meaningfully larger than `§10` asks for. A candidate for Phase 36, where the schema gains real traffic.
- **Actual `REVOKE DELETE` enforcement** — blocked until the deployment defines a database role. Documented in the migration comment and PROJECT.md per D-10/D-11; becomes actionable when role provisioning lands.
- **Application/model alignment with the new schema** — Phase 35 (foundation) and Phase 36 (rebind). Out of scope by the phase boundary.

</deferred>

---

*Phase: 34-Schema*
*Context gathered: 2026-08-19*
