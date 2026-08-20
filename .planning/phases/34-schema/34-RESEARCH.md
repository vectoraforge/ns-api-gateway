# Phase 34: Schema - Research

**Researched:** 2026-08-19
**Domain:** PostgreSQL DDL authoring + pogo-migrate single-file migration + schema-conformance testing
**Confidence:** HIGH

> **This research executed the spec's DDL.** A throwaway PostgreSQL 16.2 server was stood up in
> `/tmp`, the §3–§7 DDL was assembled into a single pogo migration, applied through pogo's own
> parser, introspected, and exercised against 32 conformance cases. Every inventory count, index
> name, index predicate string, and rejection outcome below marked `[VERIFIED: live PG 16.2]` was
> observed, not inferred. See **Open Question OQ-1** for the PG 16.2 vs PG 17 caveat.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** One migration file, rewritten from scratch — the six-file sequence in `00-schema.md §1`/`§2` is **overridden**. There is no baseline to migrate *from*: the apply target is an empty database, so the teardown migration (`§2`) has nothing to tear down and its `ALTER TABLE core.users` collapses into a direct `CREATE TABLE`. Carried forward from PROJECT.md Key Decisions and the Phase 27 precedent (D-01, v1.6). Recorded here per the SHARED-INVARIANTS conflict rule — flagged, not silently resolved. — **Reversibility:** one-way — once the file is the sole migration and the dev database is rebuilt from it, restoring a six-file incremental sequence means reconstructing a baseline state that no longer exists anywhere.

- **D-02:** The file is **renamed** to `migrations/20260818_01_initial-release.sql`. The old `20260322_01_initial-release.sql` is deleted, not edited in place. The `initial-release` slug is kept — it is still literally the initial release — and the `20260818` date matches the ids the spec's own sequence used (`20260818_01…05`). — **Reversibility:** costly — the filename stem *is* pogo's migration id, so any database with the old id applied must be dropped and rebuilt. `§9.13` already mandates exactly that for the disposable dev database.

- **D-03:** `-- depends:` stays **empty**. This remains the root migration; nothing precedes it.

- **D-04:** The description header is rewritten to describe the v2.0 schema. The current line ("initial release with users, subscriptions, and usage") names tables this migration no longer creates.

- **D-05:** `-- migrate: rollback` is two statements: `DROP SCHEMA IF EXISTS audit CASCADE;` then `DROP SCHEMA IF EXISTS core CASCADE;`. Chosen over an explicit ~35-object reverse-order drop list specifically because it cannot drift out of sync with the apply section. — **Reversibility:** reversible — the rollback body is independent of everything else in the file.

- **D-06:** The apply section is organized into **five banner-commented sections in the spec's order**: enums → identity/tiers → subscriptions/store → grants/anti-abuse/usage → challenges/audit. This preserves `§1`'s non-negotiable statement ordering by construction and makes the single file reviewable against `00-schema.md §3–§7` section by section.

- **D-07:** Every table, column, enum, CHECK, foreign key, delete behavior, and index is **dictated by `00-schema.md §3–§8`** — transcription, not design. No gray areas were opened here and none should be invented during planning.

- **D-08:** `00-schema.md §9` rulings supersede any contrary prose elsewhere in the spec. Do not "restore" an older shape that reads more naturally. In particular: `promo` is deleted from `core.access_grant_source` (four values only); `invalid_attestation_or_integrity_proof` is deleted from `core.auth_event_result`; the product-entitled set in the `core.subscriptions` generated column is fixed at `('active','grace_period')` and is never a runtime toggle; open-ended grants are legal (`ends_at` nullable).

- **D-09:** `§1`'s prohibition holds absolutely — no triggers, stored procedures, rules, views, materialized views, extensions, partitioning, `NULLS NOT DISTINCT`, invented format CHECKs, scheduled-job scaffolding, or `ON UPDATE`/`ON DELETE` clauses beyond those `§8` enumerates. `updated_at` is maintained by application writes, never by a trigger.

- **D-10:** Take the **comment-only branch** of `§8`'s final bullet. This repository defines no database role — only a `DB_USER` placeholder in `[tool.pogo] database_config` and `docker-compose.yml`. A prominent comment at the `core.external_identities` definition states the `REVOKE DELETE ON core.external_identities` requirement for whoever provisions roles. Do **not** invent a role; `§8` explicitly warns against it and it would collide with whatever the Kubernetes deployment actually provisions.

- **D-11:** The REVOKE requirement is **also** recorded in PROJECT.md's "Known areas for future work". The migration comment reaches whoever reads the SQL; the project note reaches whoever provisions the cluster — different people.

- **D-12:** The `§10` constraint-rejection tests **ship in this phase**. `§10` calls them "optional but recommended" but SCHEMA-08 requires every `§10` check to pass, and `§10` enumerates nine specific rejection cases. They are also the only tests that can run at all until Phase 36.

- **D-13:** They live in a **new `tests/schema/` package**, sibling to `unit/` and `e2e/`, with its own `conftest.py` and a raw driver connection. **Zero imports from `nativespeaker.api`** — `tests/e2e/conftest.py` imports `nativespeaker.api.app.main` and runs the app lifespan, and pytest applies that conftest to every subdirectory beneath it, so nothing under `tests/e2e/` can run while the app is broken. The root `tests/conftest.py` is already minimal and adds nothing that would break. — **Reversibility:** reversible — a self-contained new directory.

- **D-14:** A **session-scoped fixture runs `pogo apply`** against a dedicated test database and drops it afterward. This makes the suite self-contained and turns `§10`'s first acceptance check — a fresh apply against an empty database succeeds — into something the suite exercises rather than merely asserts about.

- **D-15:** Seeding uses **small typed insert helpers** (`insert_user()`, `insert_tier()`, `insert_grant(...)`, each returning the new id) with per-test transaction rollback. Rejected session-scoped shared rows: the tests asserting "a second active grant for one user is rejected" and "a second free grant of the same source is rejected even after the first is expired" mutate shared state and would become order-dependent.

- **D-16:** Add a test that **`core.external_identities.user_id`'s `ON DELETE RESTRICT` blocks deleting a `core.users` row that has an identity row.** Not in `§10`'s list, but it is the one part of "identity rows are never deleted" the schema can enforce without a role, and `§8` calls that FK out as deliberate.

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

### Deferred Ideas (OUT OF SCOPE)

- **Full `§8` cascade-list introspection** — asserting all five ON DELETE CASCADE relationships and every NO ACTION default, beyond the single `ON DELETE RESTRICT` test in D-16. Considered and scoped down: meaningfully larger than `§10` asks for. A candidate for Phase 36, where the schema gains real traffic.
- **Actual `REVOKE DELETE` enforcement** — blocked until the deployment defines a database role. Documented in the migration comment and PROJECT.md per D-10/D-11; becomes actionable when role provisioning lands.
- **Application/model alignment with the new schema** — Phase 35 (foundation) and Phase 36 (rebind). Out of scope by the phase boundary.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHEMA-01 | Single initial migration creates the complete v2.0 schema in one apply against an empty database — no incremental migration files added | **Verified end to end.** A single-file assembly of `§3–§7` + the baseline survivors applied cleanly through pogo's own parser in one transaction (Pattern 1, Pitfall P-1 for the missing survivors). Filename conflict flagged — see **CONFLICT-1**. |
| SCHEMA-02 | `core.users`, `core.external_identities`, `core.identity_provider` support `(issuer, subject)` → user resolution, `identity_state`, tombstone rows | Verified: `external_identities_issuer_subject_key` UNIQUE exists; `identity_state` defaults `'active'`; `ON DELETE RESTRICT` on `user_id` blocks user deletion (case D16). `§4` DDL transcribes directly. |
| SCHEMA-03 | `core.access_grants`, `core.access_tiers`, `core.user_monthly_usage` enforce at most one active grant per user, usage keyed by grant id | Verified: `ix_access_grants_one_active_per_user` rejects the second active grant (`UniqueViolationError`); `core.user_monthly_usage_pkey` is on `grant_id`. |
| SCHEMA-04 | `core.subscriptions`, `core.store_purchases`, `core.store_purchase_tokens` support both stores; `product_entitled_subscription_id` STORED generated over `('active','grace_period')` | Verified: generated column rejects explicit writes (`GeneratedAlwaysError`); an active grant on an `expired` **or** `billing_retry` subscription is rejected at COMMIT by the deferred FK. `subscription_provider` has 2 labels. |
| SCHEMA-05 | `core.auth_challenges` supports the claim/consume protocol | Verified: the operation CHECK rejects `operation='restore_subscription'`; the three lifecycle/binding CHECKs create without error. |
| SCHEMA-06 | `audit.auth_events` enforces the actor-field CHECKs and the two enums in full | Verified: 5 distinct malformed audit rows rejected, 1 valid row accepted; `auth_event_result` has exactly 44 labels, `auth_operation` exactly 7. |
| SCHEMA-07 | Legacy structures gone — `users.jwt_sub`, `users.subscription_plan`, `core.usage_monthly`, `core.subscription_events`, `core.subscription_plan` enum, `promo` source | Verified by inventory: 11 enums (no `subscription_plan`), 15 `core` tables (no `usage_monthly`, no `subscription_events`), `access_grant_source` = 4 labels. Requires the `core.users` target shape from `§2`'s table, not the baseline `CREATE TABLE`. |
| SCHEMA-08 | Every acceptance check in `00-schema.md §10` passes against a freshly migrated database | **All nine `§10` rejection cases and all four valid anti-abuse tuples verified passing.** Exact expected inventory sets captured (Code Example 4). |
</phase_requirements>

---

## Summary

Phase 34 is a **transcription-and-proof** phase, not a design phase. `00-schema.md §3–§7` contains the
literal DDL; D-07 forbids invention. The genuine work splits three ways: (1) collapsing the six-file
delta sequence into one from-empty file *without dropping the objects the delta silently assumed
already existed*, (2) getting that file past pogo-migrate's strict, undocumented SQL-header parser,
and (3) building a `tests/schema/` harness that proves the result without importing the application.

The single most valuable finding is that **the spec's DDL works**. This research assembled the file,
applied it through `pogo_core`'s real parser against a live PostgreSQL 16.2 instance, and ran 32
conformance cases: 0 failures. The circular deferrable foreign keys resolve, the four STORED
generated columns on `core.access_grants` and the one on `core.subscriptions` are legal as both FK
referencing and FK referenced sides, the four-arm anti-abuse CHECK admits exactly the four valid
evidence tuples and rejects every malformed shape, and `pogo rollback` via two `DROP SCHEMA … CASCADE`
statements leaves nothing behind and permits a clean re-apply. The planner can treat the DDL as
low-risk and spend its task budget on the assembly and the test harness instead.

The second most valuable finding is that **`§3–§7` alone is an incomplete file**. Those blocks are a
delta from a baseline that no longer exists at apply time. Seven objects the delta never mentions —
schema `core`, enums `core.chat_role` and `core.subscription_status`, tables `core.users` (in `§2`'s
*target* shape, not the baseline shape), `core.chats`, `core.messages`, and index `ix_chats_user_id` —
must be written by hand or `§10`'s inventory check fails and half the DDL will not even parse. This is
the phase's highest-probability failure mode and it is invisible if you read `§3–§7` in isolation.

Third: the pogo SQL header regex is far stricter than the file format suggests, the migration hash is
computed from the **filename**, not the content, and `pogo_migrate.testing.apply(db=conn)` raises on
missing `DB_*` environment variables even when you hand it a connection. Each of those has a
one-line workaround and each will otherwise consume an executor iteration.

**Primary recommendation:** Write the single file as `schemas → enums → identity/tiers →
subscriptions/store → grants/anti-abuse/usage → challenges/audit`, prepending the seven baseline
survivors into the first two sections; drive `tests/schema/` from a **synchronous** session fixture
that calls `asyncio.run()` around `pogo_core.util.testing.apply()` (not `pogo_migrate.testing.apply`)
and a function-scoped async `conn` fixture with per-test transaction rollback; and copy the exact
expected inventory sets from Code Example 4 rather than deriving them from the spec prose.

---

## Conflicts to Flag (SHARED-INVARIANTS rule: flag, never resolve silently)

| # | Conflict | Sources | Recommended disposition |
|---|----------|---------|-------------------------|
| **CONFLICT-1** | Migration **filename**. `REQUIREMENTS.md` SCHEMA-01 and `ROADMAP.md` Phase 34 goal both name `migrations/20260322_01_initial-release.sql` and say "rewrite in place". CONTEXT.md **D-02** renames the file to `migrations/20260818_01_initial-release.sql` and deletes the old one. | `.planning/REQUIREMENTS.md:16`, `.planning/ROADMAP.md:117`, `34-CONTEXT.md` D-02 | CONTEXT.md D-02 is the later, explicit, reasoned user decision and should win; but SCHEMA-01's and the roadmap's literal text then need a one-line amendment so the phase does not verify against a stale requirement. **The planner should surface this, not decide it.** Both filenames apply identically from empty — the choice is purely about the tracked migration id. |
| **CONFLICT-2** | `00-schema.md §1` mandates six files; D-01 overrides to one. Already flagged in CONTEXT.md D-01 per the invariant rule. No further action — recorded here for completeness. | `00-schema.md:34-43`, `34-CONTEXT.md` D-01 | Resolved by D-01. `§1`'s **statement ordering** and **prohibition list** still bind. |
| **CONFLICT-3** | `00-schema.md §10` calls the conformance tests "optional but recommended"; SCHEMA-08 requires every `§10` check to pass, and D-12 ships them. | `00-schema.md:648`, `REQUIREMENTS.md:23`, D-12 | Resolved by D-12: they ship. Noted so the plan-checker does not flag the tests as out-of-scope gold-plating. |
| **CONFLICT-4** | D-06 enumerates **five** sections starting at enums, but `CREATE SCHEMA core` / `CREATE SCHEMA audit` must precede everything and belong to no listed section. | D-06 vs. execution order | Minor. Recommend a short unnumbered preamble (or fold the two `CREATE SCHEMA` statements into the top of the enums section). Either satisfies D-06's intent; the planner should pick one and state it so review is deterministic. |

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Identity uniqueness reservation (`(issuer,subject)`, `(issuer,provider,provider_uid)`) | Database / Storage | — | UNIQUE constraint + partial unique index. `SHARED-INVARIANTS` makes these the race arbiter for concurrent create-user; only the database can arbitrate. |
| "Exactly one active grant per user" | Database / Storage | — | `ix_access_grants_one_active_per_user`. `§6` explicitly forbids an application rejection path for it. |
| "One lifetime free grant per source per user" | Database / Storage | — | `ix_access_grants_one_free_grant_per_user_source`, no status predicate. |
| "Exactly one anti-abuse row iff free source" | Database / Storage | — | Lower bound = deferred FK on `anti_abuse_required_grant_id`; upper bound = anti-abuse PK; source restriction = composite FK + per-source CHECK. Fully declarative by design — `§6` says "no trigger, no application check". |
| Product entitlement definition (`active`/`grace_period`) | Database / Storage | — | STORED generated column. `§9.14`: never a runtime toggle. |
| Grant↔subscription owner agreement | Database / Storage | — | Deferred composite FK on the generated pair. |
| `updated_at` maintenance | API / Backend | — | `§1`: application writes in the same statement, **never a trigger**. Not this phase. |
| Monthly period format (`YYYY-MM`) | API / Backend | — | `§6`: free text, **no format CHECK**. Not this phase. |
| Tier sizing invariant (registered ≥ anonymous credits) | API / Backend | — | `§4`: enforced at config load/startup, not by a database constraint. Not this phase. |
| `REVOKE DELETE ON core.external_identities` | Deployment / Ops | Database | No role exists in this repo; D-10 takes the comment-only branch. |
| Schema conformance proof | Test harness (`tests/schema/`) | Database | D-12/D-17. Raw driver, zero app imports. |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pogo-migrate` | 0.4.2 (installed) | Migration runner; parses the SQL file, wraps apply in one transaction, tracks applied ids in `public._pogo_migration` | Already the project's migration tool `[VERIFIED: pyproject.toml:36 "pogo-migrate>=0.4.2"; .venv/bin/pogo --version → "pogo-migrate 0.4.2"]` |
| `pogo-core` | 0.1.2 (transitive) | Where the actual parser/apply/rollback/testing helpers live in 0.4.x | `[VERIFIED: .venv/lib/python3.14/site-packages/pogo_core-0.1.2.dist-info]` — `pogo_migrate.sql` is a deprecated shim that warns and forwards to `pogo_core.util.sql` |
| `asyncpg` | 0.31.0 (installed) | Raw driver for `tests/schema/` | Already a runtime dependency `[VERIFIED: pyproject.toml:16 "asyncpg >=0.30"]`; it is also the driver pogo itself uses, so the test harness and the migration runner share one connection type |
| `pytest` | 9.0.2 (installed) | Test runner | `[VERIFIED: pyproject.toml:29 "pytest >=9.0"]` |
| `pytest-asyncio` | 1.3.0 (installed) | Async test support, `asyncio_mode = "auto"` | `[VERIFIED: pyproject.toml:30 "pytest-asyncio >=1.3"; pyproject.toml:55 asyncio_mode = "auto"]` |
| PostgreSQL | 17 (target) | The database | `[CITED: 00-schema.md:7 "(pogo-migrate, `[tool.pogo] migrations = './migrations'`, PostgreSQL 17)"]`; `docker-compose.yml` pins `image: postgres:17` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sqlparse` | 0.5.2 (transitive) | Splits the apply/rollback bodies into statements inside pogo | Never called directly — but it is what decides where your statements end |
| `sqlglot` | 30.0.1 (transitive) | Backs `pogo validate` | **Do not rely on it** — see Pitfall P-9 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncpg` in `tests/schema/` | `psycopg` (sync) | Sidesteps every pytest-asyncio loop-scope question, but adds a dependency the project does not have, and its exception classes differ from the ones the rest of the project will assert on. **Recommend asyncpg** — the loop-scope problem is fully solved by the sync-session-fixture pattern in Code Example 3. |
| Running `pogo apply` as a subprocess in the fixture | Calling `pogo_core.util.testing.apply()` in-process | Subprocess needs `DB_*` env vars and a `.env` that does not exist in the repo; in-process takes an `asyncpg.Connection` and needs no environment at all `[VERIFIED: live run — see Pitfall P-4]` |
| Explicitly naming every CHECK/UNIQUE constraint | Letting PostgreSQL auto-name them | Explicit names would make constraint-name assertions stable, but deviates from the verbatim `§3–§7` DDL that D-07 mandates. **Keep the spec's DDL; assert on behavior, not constraint names** (Pitfall P-8). |

**Installation:** none. `[VERIFIED: pyproject.toml:5-38]` — every tool this phase needs is already
declared and installed. **This phase adds no package.**

---

## Package Legitimacy Audit

**This phase installs no external packages.** The audit below covers only the one package this
*research session* used as a disposable local tool (in an isolated `/tmp` venv, never in the project),
so the planner can decide whether to formalize it as a dev-environment fallback (see Environment
Availability).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pgserver` | PyPI 0.1.4 | released 2024-06-08 | unknown | github.com/orm011/pgserver | **[SUS]** | **Not added to the project.** Used only in `/tmp/pgverify` for this research. If the planner adopts it as a local-dev fallback, gate the install behind `checkpoint:human-verify`. |
| `pytest-postgresql` | PyPI | 2026-05-15 | unknown | github.com/dbfixtures/pytest-postgresql | [SUS] | Not recommended — requires a pre-existing system PostgreSQL, which is the thing that is missing. |
| `testing.postgresql` | PyPI | 2016-02-04 | unknown | github.com/tk0miya/testing.postgresql | [SUS] | Not recommended — unmaintained since 2016, same system-PostgreSQL requirement. |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `pgserver`, `pytest-postgresql`, `testing.postgresql` — none
enter the project. `pgserver` was discovered via WebSearch and is therefore `[ASSUMED]` as to
provenance even though the registry confirms it and it ran correctly here.

---

## Architecture Patterns

### System Architecture Diagram

```
                        ┌──────────────────────────────────────┐
   developer / CI  ──▶  │  pogo apply   (or pogo_core.util.    │
                        │               testing.apply(db=…))    │
                        └───────────────────┬──────────────────┘
                                            │
                     ┌──────────────────────▼──────────────────────┐
                     │ pogo_core.util.sql.get_connection()          │
                     │  · asyncpg.connect(dsn)                      │
                     │  · SET search_path TO api   ◀── [tool.pogo]  │
                     │  · ensure_pogo_sync() → public._pogo_*       │
                     └──────────────────────┬──────────────────────┘
                                            │
                     ┌──────────────────────▼──────────────────────┐
                     │ read_migrations(): iterdir() over migrations/│
                     │   id  := path.stem      hash := sha256(id)   │
                     └──────────────────────┬──────────────────────┘
                                            │
              ┌─────────────────────────────▼─────────────────────────────┐
              │ read_sql_migration(path)                                   │
              │  1. split on "-- migrate: apply"     → metadata | body     │
              │  2. regex the metadata: ONE desc line, then "-- depends:"  │
              │  3. split body on "-- migrate: rollback"                   │
              │  4. sqlparse.split() each half → statement list            │
              │  5. terminate_statements(): force ';' on the last          │
              └─────────────────────────────┬─────────────────────────────┘
                                            │
                        ┌───────────────────▼───────────────────┐
              already   │  applied?  (id in _pogo_migration)     │
              applied ◀─┤     yes → SKIP ENTIRELY               │
              = no-op   │     no  → BEGIN                        │
                        └───────────────────┬───────────────────┘
                                            │  one transaction (default)
                      ┌─────────────────────▼─────────────────────┐
                      │ for each statement:                        │
                      │   strip lines that startswith("--")        │
                      │   if non-empty → db.execute(stmt)          │
                      └─────────────────────┬─────────────────────┘
                                            │
   ┌────────────────────────────────────────▼────────────────────────────────────────┐
   │ APPLY ORDER (dependency-driven, §1 non-negotiable)                               │
   │                                                                                  │
   │  [pre] CREATE SCHEMA core ──▶ CREATE SCHEMA audit                                │
   │    │                                                                             │
   │  [1] enums: chat_role, subscription_status  (baseline survivors — ADD THESE)      │
   │      + subscription_provider, identity_provider, identity_state, auth_operation,  │
   │        access_grant_source, access_grant_status, auth_event_result,               │
   │        native_claim_provider, gate_consumption_kind          → 11 total           │
   │    │                                                                             │
   │  [2] core.users (§2 TARGET shape) ──▶ core.chats ──▶ core.messages  (ADD THESE)   │
   │      ──▶ ix_users_registered_at, ix_chats_user_id, ix_messages_chat_id            │
   │      ──▶ core.external_identities (+4 idx) ──▶ core.access_tiers                  │
   │    │                                                                             │
   │  [3] core.subscriptions ──▶ core.store_purchase_tokens ──▶ core.store_purchases   │
   │      ──▶ audit.subscription_events                                                │
   │    │        (store_purchases FKs need BOTH subscriptions and tokens first)        │
   │  [4] core.access_grants ──▶ core.access_grants_anti_abuse                          │
   │      ──▶ ALTER core.access_grants ADD the two back-pointing FKs  ◀ circular pair   │
   │      ──▶ ix_..._one_free_grant_per_user_source                                    │
   │      ──▶ core.manual_grant_issuances, core.provider_accounts                       │
   │      ──▶ core.provider_account_gate_consumptions ──▶ core.user_monthly_usage       │
   │    │                                                                             │
   │  [5] core.auth_challenges  (needs external_identities) ──▶ audit.auth_events      │
   └──────────────────────────────────────┬───────────────────────────────────────────┘
                                          │  COMMIT
                     ┌────────────────────▼────────────────────┐
                     │ INSERT public._pogo_migration (id, hash) │
                     └─────────────────────────────────────────┘

   tests/schema/  ──▶ session fixture (SYNC, asyncio.run):
                        CREATE DATABASE ns_schema_test
                        pogo_core.util.testing.apply(MIGRATIONS, db=conn, schema_name="api")
                      ──▶ per-test async `conn` fixture: BEGIN … yield … ROLLBACK
                      ──▶ inventory tests  (pg_catalog exact-set)
                      ──▶ rejection tests  (expect asyncpg.CheckViolationError / …)
                      ──▶ rollback test    (testing.rollback → assert core/audit gone)
                        DROP DATABASE ns_schema_test
```

### Recommended Project Structure

```
migrations/
└── 20260818_01_initial-release.sql   # the ONLY file here (D-02); old file deleted

tests/
├── conftest.py                        # unchanged, minimal
├── unit/                              # untouched
├── e2e/                               # untouched — do not import from here
└── schema/                            # NEW (D-13)
    ├── __init__.py                    # optional; keeps module names unambiguous
    ├── conftest.py                    # scratch DB + pogo apply + per-test rollback
    ├── helpers.py                     # insert_user / insert_tier / insert_grant (D-15)
    ├── test_inventory.py              # D-17/D-18 exact-set assertions
    ├── test_constraints.py            # §10 nine rejections + four valid tuples + D-16
    └── test_apply_rollback.py         # D-20
```

### Pattern 1: Collapsing a delta migration into a from-empty migration

**What:** `§3–§7` describes changes *relative to* `20260322_01_initial-release`. Applied to an empty
database those blocks reference objects that were never created.

**When to use:** Every time D-01's "one file, from empty" decision meets a spec written as a delta.

**The seven objects `§3–§7` never creates but `§10`'s inventory requires:**

| Object | Why `§3–§7` omits it | Where the shape comes from |
|--------|---------------------|---------------------------|
| `CREATE SCHEMA core` | baseline created it | `20260322_01_initial-release.sql:6` |
| `core.chat_role` enum | `[CITED: 00-schema.md:181]` "`core.chat_role` and `core.subscription_status` survive from the baseline unchanged and are not recreated" | `20260322_01_initial-release.sql:8` |
| `core.subscription_status` enum | same | `20260322_01_initial-release.sql:11` |
| `core.users` table | `§2` **alters** it | `00-schema.md:84-94` — the *target shape* table, not the baseline `CREATE TABLE` |
| `core.chats` table | `[CITED: 00-schema.md:82]` "`core.chats` and `core.messages` keep their existing definitions" | `20260322_01_initial-release.sql:25-31` |
| `core.messages` table | same | `20260322_01_initial-release.sql:35-41` |
| `ix_chats_user_id` | baseline index, never dropped by `§2` | `20260322_01_initial-release.sql:33` |

**`core.users` target shape (transcribed from the `§2` table at `00-schema.md:84-94`):**

```sql
CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    registered_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Note what `§2` does *not* say and therefore must not appear: no `jwt_sub`, no `subscription_plan`,
no `NOT NULL` on `email`, no `name` column (it was renamed to `display_name`), and no
`ix_users_jwt_sub`.

**Baseline indexes that must NOT be recreated:** `ix_users_jwt_sub` (dropped with the column),
`ix_subscriptions_external_id` and `ix_subscriptions_user_provider_active`
(`[CITED: 00-schema.md:333]` "Baseline indexes `ix_subscriptions_external_id` and
`ix_subscriptions_user_provider_active` are NOT recreated"), `ix_usage_monthly_user_month`
(table dropped). `ix_subscription_events_subscription_id` **is** recreated, but on
`audit.subscription_events` — `[CITED: 00-schema.md:339]` "The index keeps its baseline name but now
lives in `audit`."

### Pattern 2: The pogo SQL header is stricter than it looks

**What:** The header must be exactly one description comment line, immediately followed by the
`-- depends:` line. Nothing before it, nothing between them, no blank line.

**Source:** `[VERIFIED: .venv/…/pogo_core/migration.py:49]` —
`m = re.match(r".*--(.*)\s-- depends:(.*)[\s]?", metadata.strip())`. `re.match` is not `DOTALL`,
so `.*--(.*)` cannot cross a newline: the description must be line 1 and `-- depends:` must be line 2.

**Empirically confirmed this session:**

| Header shape | Parses? |
|--------------|---------|
| `-- desc` ⏎ `-- depends:` | ✅ `('desc', '')` |
| `-- desc` ⏎ `-- more notes` ⏎ `-- depends:` | ❌ `None` → `BadMigrationError` |
| `-- banner` ⏎ `-- desc` ⏎ `-- depends:` | ❌ `None` |
| `-- desc` ⏎ *(blank)* ⏎ `-- depends:` | ❌ `None` |
| `-- desc` ⏎ `-- depends:` ⏎ `-- extra note` | ✅ `('desc', '')` |

Extra header prose is legal **only after** the `-- depends:` line. Also `[VERIFIED:
pogo_core/migration.py:52-54]` — more than one `-- depends:` anywhere in the metadata is a hard error.

### Pattern 3: Comment handling inside the apply body

`[VERIFIED: pogo_core/migration.py:22]`
`return "\n".join([line for line in statement.split("\n") if not line.startswith("--")])`

- A comment at **column 0** is stripped before the statement reaches PostgreSQL.
- An **indented** comment (`    -- …`) is *not* stripped and is sent to PostgreSQL, which handles it
  natively. Both work.
- A standalone banner-comment block between statements collapses to `""` and is skipped by
  `if statement_:`. Verified: the five banner blocks in the assembled file caused no error.

Practical consequence for D-06 and the "Claude's Discretion" commenting-depth item: **banner comments
and inline `§9` ruling citations are both safe.** Write them freely.

### Anti-Patterns to Avoid

- **Deriving the expected inventory from the spec prose.** `§10` names 5 unique indexes and 2 partial
  indexes; the applied database has **54 indexes** including 25 auto-named constraint indexes. An
  exact-set assertion (D-18) built from `§10` will fail on the first run. Use Code Example 4.
- **Asserting on auto-generated CHECK constraint names.** They are positional
  (`auth_events_check`, `auth_events_check1`, `auth_events_details_check` … `_check6`) and shift if
  the DDL's CHECK clauses are reordered. Assert on the exception class and the *behavior*.
- **`try: commit / except: rollback` around a deferred-constraint test.** Once COMMIT fails the
  transaction is already gone; `rollback()` then raises. See Pitfall P-6.
- **Adding `NOT NULL` to `core.users.email`.** `[CITED: 00-schema.md:80]` "`email` becomes nullable
  because it is copied only from a Firebase Admin record whose `emailVerified` is TRUE."
- **Adding a format CHECK to `core.user_monthly_usage.monthly_period`.** `[CITED: 00-schema.md:500]`
  "`monthly_period` is free text in `YYYY-MM` (UTC calendar month) with no format CHECK".
- **Seeding `core.access_tiers`.** `[CITED: 00-schema.md:249]` "Phase 00 seeds NO tier rows". The
  *tests* must insert their own tier row; the migration must not.
- **Making `ix_access_grants_anti_abuse_idp_account_hash` unique.** `[CITED: 00-schema.md:497]`
  "Never make that index unique".
- **Adding a key-version column to `core.auth_challenges`.** `[CITED: 00-schema.md:595]` "Do NOT add
  a key-version column here (unlike `audit.auth_events`, which has one)."
- **Adding an FK on `audit.auth_events.challenge_row_id`.** `[CITED: 00-schema.md:608]` "Do not add an FK."

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Applying the migration in the test fixture | A `subprocess.run(["pogo","apply"])` wrapper, or your own statement splitter | `pogo_core.util.testing.apply(MIGRATIONS, db=conn, schema_name="api")` | Exercises the *same* parser production uses, needs no env vars, needs no `.env`, and returns a real exception on failure `[VERIFIED: live run]` |
| Rolling back in the test | Hand-written `DROP SCHEMA` in the test | `pogo_core.util.testing.rollback(...)` / `migrate.rollback(db, MIG, schema_name="api", count=1)` | D-20 exists precisely to prove the file's own rollback section works. Hand-written drops prove nothing. |
| Expected index-predicate strings | Transcribing `WHERE` clauses from the spec | `pg_get_expr(indpred, indrelid)` captured from a live apply (Code Example 4) | PostgreSQL rewrites predicates on storage — `IN (…)` becomes `= ANY (ARRAY[…])` with explicit `::type` casts. A spec-verbatim string never matches. |
| "Exactly one anti-abuse row iff free source" | A trigger, or an application-side check | The declarative quartet already in `§6` | `[CITED: 00-schema.md:495]` "Together they make 'exactly one anti-abuse row iff free source' fully declarative — no trigger, no application check." Verified working. |
| Per-test isolation | `TRUNCATE … CASCADE` between tests | `BEGIN` … `ROLLBACK` on a function-scoped connection | Matches the project's established convention (STATE.md: "Per-test transaction rollback via join_transaction_mode=create_savepoint") and is ~100× faster. Verified working in the prototype. |
| Enum label assertions | `information_schema` | `pg_type` ⋈ `pg_enum` with `ORDER BY enumsortorder` | `information_schema` has no enum-label view. Ordering matters: `§3` says "Every value listed, in this order". |

**Key insight:** every "smart" thing this phase could do has already been decided by `§9`'s fourteen
rulings and D-07's transcription rule. The only original engineering is the test harness — and the
harness's job is to be dumb, exact, and exhaustive.

---

## Runtime State Inventory

> This is a schema-replacement phase. All five categories answered.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | Any developer/CI PostgreSQL database that already applied the baseline holds (a) migration id `20260322_01_initial-release` in `public._pogo_migration` and (b) the v1.6 `core` schema objects. `[VERIFIED: pogo_core/util/sql.py:38 "Migration(path.stem, path, applied_migrations)"]` — the migration id **is** the filename stem, and `[VERIFIED: pogo_core/migration.py:97 "self.hash: str = hashlib.sha256(mig_id.encode(\"utf-8\")).hexdigest()"]` — the hash is over the **id**, never the file content. Renaming (D-02) therefore presents the file as a brand-new, unapplied migration on top of an existing schema. | **Data migration: drop and recreate the database.** Verified failure mode: with the old id marked applied and the old objects present, applying the renamed file fails with `BadMigrationError: Failed to apply 20260818_01_initial-release` / cause `type "chat_role" already exists`. `§9.13` already mandates the rebuild. The plan needs an explicit "drop and recreate the dev database" task, not a note. |
| | *Corollary:* if the file were edited **in place** under the old name (CONFLICT-1's other branch), pogo would see the id as already applied and **silently skip the whole file** — the developer would get a green `pogo apply` and a stale schema. | Whichever filename branch wins, the drop-and-recreate task is mandatory. |
| **Live service config** | None. `[VERIFIED: grep -rn -iE "migrat\|pogo\|initContainer\|DB_NAME" k8s/` → no matches]` — the Helm chart has no migration Job, no initContainer, and no database bootstrap. Migrations are applied by hand. No n8n/Datadog/Tailscale/Cloudflare-style external config references this schema. | None. |
| **OS-registered state** | None — verified: no scheduled tasks, no pm2/systemd/launchd units in the repo; the app is deployed as a Kubernetes Deployment (`k8s/templates/deployment.yaml`). | None. |
| **Secrets / env vars** | `[VERIFIED: pyproject.toml:71]` `database_config = 'postgres://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'` — five env vars. `[VERIFIED: .env.example:5-9]` declares `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`. **`.env` does not exist in the working tree** (`ls .env` → No such file) and is gitignored (`.gitignore:11`). `[VERIFIED: pyproject.toml:54]` `env_files = [".env"]` — pytest-dotenv silently loads nothing when the file is absent. No variable is renamed by this phase. | **No key renames.** But the plan must state how the test fixture reaches a database, because the CLI path (`pogo apply`) is unusable without a `.env`. Recommended: the fixture connects directly and calls `pogo_core.util.testing.apply(db=conn)`, which needs no env var at all (P-4). |
| **Build artifacts / installed packages** | None affected. The migration is data, not code; there is no compiled artifact, no `egg-info` regeneration need, no image rebuild triggered by a `.sql` change. `[VERIFIED: .gitignore:6 "*.egg-info/"]` and `find src -name "*.egg-info"` → none present. | None. |

**The canonical question — after every file in the repo is updated, what runtime systems still have
the old string cached, stored, or registered?** Exactly one: `public._pogo_migration` in whatever
PostgreSQL instance a developer has been using. Everything else is derived.

---

## Common Pitfalls

### P-1: `§3–§7` is an incomplete file (HIGHEST PROBABILITY)
**What goes wrong:** The executor copies the five `sql` blocks from `§3`–`§7`, wires the pogo header
around them, and applies. The apply fails at the first `REFERENCES core.users (id)` — or worse, if the
executor "fixes" it by adding the *baseline* `core.users`, the apply succeeds and ships `jwt_sub` and
`subscription_plan` straight into the v2.0 schema, silently violating SCHEMA-07.
**Why it happens:** `§0`/`§2` express `core.users` as an `ALTER`, and `§3` explicitly says `chat_role`
and `subscription_status` "are not recreated". Both statements are true *of the six-file sequence*
and false *of a from-empty single file*. Nothing in `§3–§7` flags the gap.
**How to avoid:** Pattern 1's seven-object table. Take `core.users` from the target-shape table at
`00-schema.md:84-94`, never from `20260322_01_initial-release.sql:13-21`.
**Warning signs:** apply error `relation "core.users" does not exist`; or an inventory test that
reports 15 core tables but a `core.users` with 9 columns instead of 7.

### P-2: Multi-line description header
**What goes wrong:** `BadMigrationError: <file>: No '-- depends:' or message found.` before a single
SQL statement runs.
**Why it happens:** The regex at `pogo_core/migration.py:49` requires description-then-depends on
consecutive lines 1 and 2. D-04 invites rewriting the description; a two-line rewrite breaks it.
**How to avoid:** One line. Put any additional prose *after* `-- depends:`. See Pattern 2's table.
**Warning signs:** the error above; also `Multiple '-- depends:' defined` if a banner comment happens
to contain that literal.

### P-3: A stray second migration file
**What goes wrong:** Verified this session — with both `20260322_01_initial-release.sql` and
`20260818_01_initial-release.sql` in `migrations/`, pogo applies the old one first and then fails the
new one: `Failed to apply 20260818_01_initial-release` / `type "chat_role" already exists`.
**Why it happens:** `[VERIFIED: pogo_core/util/sql.py:36-41]` `read_migrations` iterates **every**
`.py`/`.sql` file in the directory; with `-- depends:` empty there is no ordering constraint between
them and both are "unapplied".
**How to avoid:** `git rm` the old file in the same commit. Success criterion 1 says "no second
migration file present" — make it a literal assertion (`len(list(MIGRATIONS.glob("*.sql"))) == 1`).
**Warning signs:** `pogo apply` output showing two `Applying …` lines.

### P-4: `pogo_migrate.testing.apply(db=conn)` raises without `DB_*` env vars
**What goes wrong:** `InvalidConfigurationError: Configured database_config env var 'DB_USER' not set.`
— even though you handed it a live connection and never intended to use the DSN.
**Why it happens:** `[VERIFIED: pogo_migrate/testing.py:15]`
`await testing.apply(c.migrations, db=db, database_dsn=c.database_dsn, schema_name=c.schema)` —
`c.database_dsn` is a property evaluated **eagerly** as an argument, and
`[VERIFIED: pogo_migrate/config.py:36]` it does `os.environ[k[1]]` for each `{placeholder}` in
`database_config`, raising `KeyError`→`InvalidConfigurationError` on the first missing one. The repo
has no `.env`.
**How to avoid:** call the layer underneath —
`from pogo_core.util import testing as pogo_testing; await pogo_testing.apply(MIGRATIONS, db=conn, schema_name="api")`.
Verified working with all five `DB_*` vars deleted from the environment.
**Warning signs:** the exact error string above during fixture setup.

### P-5: `pg_get_expr` output depends on the reader's `search_path`
**What goes wrong:** D-19's predicate assertions pass locally and fail in CI, or vice versa.
**Why it happens:** verified on the live database — the same index renders differently:

| `search_path` | `ix_access_grants_one_active_per_user` predicate |
|---------------|--------------------------------------------------|
| `"$user", public` (default) | `(status = 'active'::core.access_grant_status)` |
| `core, public` | `(status = 'active'::access_grant_status)` |
| `api` (what `pogo apply` sets) | `(status = 'active'::core.access_grant_status)` |

**How to avoid:** pin it. Either `await conn.execute("SET search_path TO pg_catalog")` (or the plain
default) at the top of the predicate test, or normalize the returned string by stripping `core.`
before comparing. Pinning is preferable — it is one line and it keeps the assertion literal.
**Warning signs:** an assertion diff whose only difference is a `core.` prefix on enum casts.

### P-6: A deferred-constraint failure poisons `tx.rollback()`
**What goes wrong:** The test for "a free grant with no anti-abuse row is rejected" gets
`asyncpg.exceptions._base.InterfaceError: cannot rollback; the transaction is in error state`
*instead of* the `ForeignKeyViolationError` it was asserting.
**Why it happens:** the deferred FK fires at **COMMIT**. By the time the exception surfaces the
server has already aborted the transaction, but asyncpg's `Transaction` object still thinks it is
open, so calling `.rollback()` raises a second, different exception that masks the first.
**How to avoid:** for deferred-constraint cases, drive the transaction with explicit SQL
(`await conn.execute("BEGIN")` … `await conn.execute("COMMIT")`) and do not call `ROLLBACK` after a
failed `COMMIT`; or wrap the commit in its own `try` that swallows rollback errors. Code Example 2
shows the working shape.
**Which cases hit this (verified):** the free-grant-without-anti-abuse lower bound, the
active-grant-on-non-entitled-subscription case, and the grant/subscription owner-mismatch case.
Everything else in `§10` fails at statement time and is safe with the ordinary pattern.

### P-7: "Zero triggers" is false — 104 internal triggers exist
**What goes wrong:** D-18's `assert trigger_count == 0` fails immediately on a correct schema.
**Why it happens:** every foreign key is implemented as a pair of internal `pg_trigger` rows.
Verified counts on the applied schema: **0** user triggers, **104** internal triggers, 0 views,
0 matviews.
**How to avoid:** filter `AND NOT t.tgisinternal` in the trigger count query. `pg_views` /
`pg_matviews` need no filter.

### P-8: Auto-generated constraint names are positional and order-fragile
**What goes wrong:** a test asserting `constraint_name == "auth_events_check1"` breaks when someone
reorders two CHECK clauses in the DDL — even though the schema is semantically identical.
**Why it happens:** PostgreSQL names unnamed table CHECKs `<table>_check`, `<table>_check1`,
`<table>_check2`… in declaration order (column-attached ones get `<table>_<column>_check`). Verified
names on the applied schema include `auth_events_check`, `auth_events_check1`,
`auth_events_details_check` … `auth_events_details_check6`, `access_grants_check`,
`access_grants_check1`, `auth_challenges_check`…`check2`, `external_identities_check`.
**How to avoid:** assert `pytest.raises(asyncpg.CheckViolationError)` and the *row was rejected*, not
the constraint's name. Index names, by contrast, are explicit and stable — assert those freely.

### P-9: `pogo validate` is broken and is not a gate
**What goes wrong:** an executor adds `pogo validate` as a cheap pre-apply check and it crashes.
**Why it happens:** verified — running `.venv/bin/pogo validate` against the **existing, working**
baseline migration raises
`TypeError: unsupported operand type(s) for +=: 'NoneType' and 'int'` from
`sqlparse/sql.py:270` via `pogo_core/squash.py:146`. Its own help text says `[EXPERIMENTAL]` and
"Best effort". It also exits 0 on that crash, so it is worse than useless as a gate.
**How to avoid:** the gate is `pogo apply` against a real empty database. Nothing else.

### P-10: Applying against a database where `api` schema does not exist
**What goes wrong:** nothing — but it surprises people.
**Why it matters:** `[VERIFIED: pogo_core/util/sql.py:24]` `await db.execute(f"SET search_path TO {schema_name}")`
with `schema_name` = `api` `[VERIFIED: pyproject.toml:72 "schema = 'api'"]`. PostgreSQL accepts a
`search_path` naming a non-existent schema without error, and pogo's own bookkeeping tables are
hard-coded to `public`. Because every statement in `§3–§7` is schema-qualified, the whole file applies
correctly under `search_path = api`. Verified: `show search_path` → `api`, apply succeeded.
**Consequence:** do **not** add `--create-schema` and do **not** create an `api` schema; and do not
introduce any unqualified object reference into the DDL, because it would silently target `api`.

### P-11: Testing "a `subscription` grant cannot get an anti-abuse row" the naive way
**What goes wrong:** the test passes for the wrong reason. Inserting `source='subscription'` with a
NULL `subscription_id` trips `access_grants_check1` (the subscription_id CHECK) before the anti-abuse
insert is ever attempted — verified. The test then "passes" without exercising
`access_grants_anti_abuse_grant_source_check` at all.
**How to avoid:** build a real subscription row first, then a real subscription-backed grant, *then*
attempt the anti-abuse insert. Verified that this correctly rejects with
`CheckViolationError … access_grants_anti_abuse_…`. Same care applies to the `manual` case (which
needs no subscription and is safe).

---

## Code Examples

### 1. Migration file skeleton (header + banners + rollback)

```sql
-- v2.0 authentication and entitlements schema
-- depends:
--
-- Single initial migration (see .planning PROJECT.md Key Decisions and 34-CONTEXT.md D-01):
-- the v2.0 schema is delivered in one apply against an empty database; no incremental
-- migrations are added during v2.0. Statement order follows 00-schema.md §1 exactly.

-- migrate: apply

-- =====================================================================
-- 0. SCHEMAS
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS audit;

-- =====================================================================
-- 1. ENUMS  (00-schema.md §3, plus the two baseline survivors)
-- =====================================================================
CREATE TYPE core.chat_role AS ENUM ('human', 'ai');
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');
-- … then the nine types from §3, values in the order §3 lists them …

-- =====================================================================
-- 2. IDENTITY AND TIERS  (00-schema.md §4, plus users/chats/messages)
-- =====================================================================
-- … core.users (§2 target shape), core.chats, ix_chats_user_id, core.messages …
-- … then §4 verbatim …

-- =====================================================================
-- 3. SUBSCRIPTIONS AND STORE  (00-schema.md §5)
-- =====================================================================
-- =====================================================================
-- 4. GRANTS, ANTI-ABUSE, USAGE  (00-schema.md §6)
-- =====================================================================
-- =====================================================================
-- 5. CHALLENGES AND AUDIT  (00-schema.md §7)
-- =====================================================================

-- migrate: rollback

DROP SCHEMA IF EXISTS audit CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
```

Header shape verified against `pogo_core/migration.py:49`; the banner-only comment blocks were
verified to be skipped rather than executed. The rollback body was verified: after
`migrate.rollback(..., count=1)` the query
`select nspname from pg_namespace where nspname in ('core','audit')` returned `[]` and a subsequent
re-apply produced all 17 tables again.

### 2. `tests/schema/conftest.py` — verified working shape

```python
import asyncio
import pathlib

import asyncpg
import pytest
import pytest_asyncio
from pogo_core.util import testing as pogo_testing   # NOT pogo_migrate.testing — see P-4

MIGRATIONS = pathlib.Path(__file__).parents[2] / "migrations"
POGO_SCHEMA = "api"          # matches [tool.pogo] schema
TEST_DB = "ns_schema_test"


@pytest.fixture(scope="session")
def schema_db_uri(admin_dsn):          # admin_dsn: build from DB_* env, or a session default
    """Create a scratch database, apply the migration into it, drop it afterwards."""
    async def _setup() -> str:
        admin = await asyncpg.connect(admin_dsn)
        await admin.execute(f'DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE {TEST_DB}')
        await admin.close()

        uri = _with_database(admin_dsn, TEST_DB)
        conn = await asyncpg.connect(uri)
        await pogo_testing.apply(MIGRATIONS, db=conn, schema_name=POGO_SCHEMA)
        await conn.close()
        return uri

    async def _teardown() -> None:
        admin = await asyncpg.connect(admin_dsn)
        await admin.execute(f'DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)')
        await admin.close()

    uri = asyncio.run(_setup())        # SYNC fixture + asyncio.run: no loop-scope juggling
    yield uri
    asyncio.run(_teardown())


@pytest_asyncio.fixture
async def conn(schema_db_uri):
    """Function-scoped connection; every test runs inside a rolled-back transaction."""
    c = await asyncpg.connect(schema_db_uri)
    tx = c.transaction()
    await tx.start()
    try:
        yield c
    finally:
        try:
            await tx.rollback()
        except Exception:              # a deferred-FK failure already aborted it — see P-6
            pass
        await c.close()
```

**Why the session fixture is synchronous:** `[VERIFIED: pyproject.toml:55-56]`
`asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"`. A session-scoped
*async* fixture under a function-scoped default loop returns objects bound to a loop the tests do not
run in. Wrapping the one-shot setup in `asyncio.run()` inside a plain `@pytest.fixture` sidesteps the
entire problem and needs no `loop_scope=` markers anywhere.

**This exact structure was run this session** against the project's own interpreter, pytest 9.0.2 and
pytest-asyncio 1.3.0 with the project's asyncio settings: 3/3 passed, including a test proving the
previous test's rows were rolled back.

**Deferred-constraint cases need explicit transaction control (P-6):**

```python
async def test_free_grant_requires_anti_abuse_row(conn, tier):
    user_id = await insert_user(conn)
    await conn.execute("BEGIN")
    await conn.execute(
        "INSERT INTO core.access_grants (id, user_id, tier_id, source, status) "
        "VALUES ($1, $2, $3, 'anonymous_device_grant', 'active')",
        uuid4(), user_id, tier,
    )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await conn.execute("COMMIT")        # deferred FK fires HERE, not above
    # do NOT call ROLLBACK here — the server already aborted the transaction
```

### 3. Introspection queries for D-17 / D-18 / D-19

```python
ENUMS = """
SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
JOIN pg_enum e      ON e.enumtypid = t.oid
WHERE n.nspname = 'core' AND t.typtype = 'e'
GROUP BY t.typname
"""

TABLES = "SELECT tablename FROM pg_tables WHERE schemaname = $1"

INDEXES = """
SELECT n.nspname AS schema,
       i.relname AS index_name,
       ix.indisunique AS is_unique,
       pg_get_expr(ix.indpred, ix.indrelid) AS predicate
FROM pg_index ix
JOIN pg_class i     ON i.oid = ix.indexrelid
JOIN pg_class c     ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('core', 'audit')
"""

# P-7: internal FK triggers are NOT user triggers
USER_TRIGGERS = """
SELECT count(*) FROM pg_trigger t
JOIN pg_class c     ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('core','audit') AND NOT t.tgisinternal
"""

VIEWS    = "SELECT count(*) FROM pg_views    WHERE schemaname IN ('core','audit')"
MATVIEWS = "SELECT count(*) FROM pg_matviews WHERE schemaname IN ('core','audit')"

# SCHEMA-07 negative assertions
GONE = """
SELECT
  to_regtype('core.subscription_plan')  IS NULL AS no_plan_enum,
  to_regclass('core.usage_monthly')     IS NULL AS no_usage_monthly,
  to_regclass('core.subscription_events') IS NULL AS no_sub_events,
  NOT EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='core' AND table_name='users'
                AND column_name='jwt_sub')          AS no_jwt_sub
"""
```

### 4. Expected inventory — captured from a live applied database

> Copy these verbatim into `tests/schema/test_inventory.py`. Every value below was read out of a
> PostgreSQL instance that had just applied the assembled migration.

```python
EXPECTED_ENUM_LABEL_COUNTS = {
    "access_grant_source": 4,
    "access_grant_status": 3,
    "auth_event_result": 44,
    "auth_operation": 7,
    "chat_role": 2,
    "gate_consumption_kind": 2,
    "identity_provider": 3,
    "identity_state": 2,
    "native_claim_provider": 2,
    "subscription_provider": 2,
    "subscription_status": 5,
}                                    # exactly 11 keys

EXPECTED_CORE_TABLES = {
    "access_grants", "access_grants_anti_abuse", "access_tiers", "auth_challenges",
    "chats", "external_identities", "manual_grant_issuances", "messages",
    "provider_account_gate_consumptions", "provider_accounts", "store_purchase_tokens",
    "store_purchases", "subscriptions", "user_monthly_usage", "users",
}                                    # 15

EXPECTED_AUDIT_TABLES = {"auth_events", "subscription_events"}   # 2

EXPECTED_CORE_INDEXES = {            # 46
    "access_grants_anti_abuse_pkey",
    "access_grants_anti_abuse_registered_account_grant_id_key",
    "access_grants_id_source_key", "access_grants_pkey", "access_tiers_pkey",
    "auth_challenges_challenge_id_key", "auth_challenges_pkey", "chats_pkey",
    "external_identities_issuer_subject_key", "external_identities_pkey",
    "external_identities_user_id_key",
    "ix_access_grants_anti_abuse_idp_account_hash",
    "ix_access_grants_one_active_per_user",
    "ix_access_grants_one_free_grant_per_user_source",
    "ix_access_grants_one_per_subscription", "ix_access_grants_subscription",
    "ix_access_grants_user_active", "ix_auth_challenges_expires_at", "ix_chats_user_id",
    "ix_external_identities_provider", "ix_external_identities_provider_account",
    "ix_external_identities_user_active", "ix_external_identities_user_id",
    "ix_gate_consumptions_grant_id", "ix_messages_chat_id",
    "ix_store_purchase_tokens_user_id", "ix_store_purchases_provider_identity_value",
    "ix_store_purchases_purchase_user_id", "ix_subscriptions_provider_external_id",
    "ix_subscriptions_user_id", "ix_users_registered_at",
    "manual_grant_issuances_grant_id_key", "manual_grant_issuances_pkey", "messages_pkey",
    "provider_account_gate_consumptions_pkey", "provider_accounts_pkey",
    "provider_accounts_provider_provider_uid_key",
    "store_purchase_tokens_provider_identity_value_key",
    "store_purchase_tokens_user_id_provider_key", "store_purchases_pkey",
    "store_purchases_provider_external_id_key", "subscriptions_id_user_id_key",
    "subscriptions_pkey", "subscriptions_product_entitled_subscription_id_key",
    "user_monthly_usage_pkey", "users_pkey",
}

EXPECTED_AUDIT_INDEXES = {           # 8
    "auth_events_pkey", "ix_auth_events_actor_issuer_subject_hash",
    "ix_auth_events_challenge_row_id", "ix_auth_events_operation_created_at",
    "ix_auth_events_result_created_at", "ix_subscription_events_subscription_id",
    "subscription_events_notification_uuid_key", "subscription_events_pkey",
}

# pg_get_expr output with `core` NOT in search_path (see P-5 — pin search_path in the test)
EXPECTED_INDEX_PREDICATES = {
    "ix_external_identities_provider_account":
        "(provider_uid IS NOT NULL)",
    "ix_subscriptions_provider_external_id":
        None,
    "ix_access_grants_one_per_subscription":
        "((source = 'subscription'::core.access_grant_source) "
        "AND (subscription_id IS NOT NULL) "
        "AND (status = 'active'::core.access_grant_status))",
    "ix_access_grants_one_active_per_user":
        "(status = 'active'::core.access_grant_status)",
    "ix_access_grants_one_free_grant_per_user_source":
        "(source = ANY (ARRAY['anonymous_device_grant'::core.access_grant_source, "
        "'registered_account_grant'::core.access_grant_source]))",
    "ix_access_grants_subscription":
        "(subscription_id IS NOT NULL)",
    "ix_access_grants_anti_abuse_idp_account_hash":
        "(idp_account_hash IS NOT NULL)",
}

EXPECTED_USER_TRIGGERS = 0     # internal FK triggers (104) must be excluded — P-7
EXPECTED_VIEWS = 0
EXPECTED_MATVIEWS = 0
```

**`core.auth_event_result`'s 44 labels, in `enumsortorder`, as applied** (use for the exact-label
assertion; matches `00-schema.md:129-174` verbatim):

```
succeeded, challenge_expired, challenge_consumed, challenge_identity_mismatch,
challenge_operation_mismatch, challenge_not_found, invalid_external_jwt,
preauth_identity_not_allowed, identity_already_linked, provider_not_linked,
provider_transition_not_allowed, provider_account_already_linked, blocked_user,
historical_identity, invalid_restore_proof, proof_malformed,
store_transaction_already_linked, restore_subscription_unlinked,
restore_subscription_not_entitled, restore_purchase_uuid_unknown,
restore_purchase_uuid_mismatch, restore_subscription_grant_owner_mismatch,
restore_branch_inconsistent, restore_store_state_unverified, restore_source_user_inactive,
restore_destination_anonymous, restore_destination_already_entitled,
anti_abuse_already_claimed, native_claim_already_claimed, native_claim_unavailable,
native_claim_write_failed, devicecheck_read_budget_exhausted,
devicecheck_write_budget_exhausted, device_recall_read_budget_exhausted,
device_recall_write_budget_exhausted, firebase_user_unresolved, idp_account_not_eligible,
firebase_lookup_unavailable, verification_temporarily_unavailable,
idp_account_already_claimed, registered_grant_destination_incompatible, policy_rejected,
revocation_unconfirmed, internal_error
```

### 5. The conformance matrix — all 32 cases, with the observed outcome

> Every row below was executed against the applied schema. `FAILURES: 0 / 32`.

| # | Case | Source | Observed | Exception |
|---|------|--------|----------|-----------|
| V1 | anti-abuse: native iOS (`native_claim_provider='ios_devicecheck'`, hashes NULL) | §10 | ACCEPTED | — |
| V2 | anti-abuse: native Android (`android_play_integrity`) | §10 | ACCEPTED | — |
| V3 | anti-abuse: web anonymous (ncp NULL, both hash fields set) | §10 | ACCEPTED | — |
| V4 | anti-abuse: registered (ncp NULL, both hash fields set) | §10 | ACCEPTED | — |
| R1 | `anonymous_device_grant` with ncp **and** hash both NULL | §10 | REJECTED @stmt | `CheckViolationError` `access_grants_anti_abuse_check` |
| R2 | native row also carrying `idp_account_hash` | §10 | REJECTED @stmt | `CheckViolationError` |
| R3 | web-anonymous row carrying a `native_claim_provider` | §10 | REJECTED @stmt | `CheckViolationError` |
| R4 | registered row carrying a `native_claim_provider` | §10 | REJECTED @stmt | `CheckViolationError` |
| R5 | anti-abuse row for a real `subscription` grant | §10 | REJECTED @stmt | `CheckViolationError` `access_grants_anti_abuse_grant_source_check` (see P-11) |
| R6 | anti-abuse row for a `manual` grant | §10 | REJECTED @stmt | `CheckViolationError` |
| R7 | second `status='active'` grant for one user | §10 | REJECTED @stmt | `UniqueViolationError` `ix_access_grants_one_active_per_user` |
| R8 | second free grant, same source, first already `expired` | §10 | REJECTED @stmt | `UniqueViolationError` `ix_access_grants_one_free_grant_per_user_source` |
| R9 | `auth_challenges` row with `operation='restore_subscription'` | §10 | REJECTED @stmt | `CheckViolationError` `auth_challenges_check1` |
| A1 | audit row, non-`invalid_external_jwt` result, all actor fields NULL | §7 / roadmap #4 | REJECTED @stmt | `CheckViolationError` `auth_events_check` |
| A2 | audit row, `invalid_external_jwt` **with** actor fields | §7 | REJECTED @stmt | `CheckViolationError` `auth_events_check` |
| A3 | audit row, partial actor (issuer+hash, no key version) | §7 / roadmap #4 | REJECTED @stmt | `CheckViolationError` `auth_events_check` |
| A4 | audit row `result='succeeded'` with `operation` NULL | §7 | REJECTED @stmt | `CheckViolationError` `auth_events_check1` |
| A5 | audit row whose `details` omits the `failure` key | §7 | REJECTED @stmt | `CheckViolationError` `auth_events_details_check2` |
| A6 | audit row, valid minimal actor triple, default `details` | §7 | ACCEPTED | — |
| D16 | `DELETE FROM core.users` where an identity row exists | D-16 | REJECTED @stmt | `ForeignKeyViolationError` `external_identities_user_id_fkey` |
| I1 | identity `provider='anonymous'` with a `provider_uid` | §4 CHECK | REJECTED @stmt | `CheckViolationError` `external_identities_check` |
| I2 | identity `provider='google'` with `provider_uid=''` | §4 CHECK | REJECTED @stmt | `CheckViolationError` |
| LB | free-source grant with **no** anti-abuse row | §6 lower bound | REJECTED **@COMMIT** | `ForeignKeyViolationError` `access_grants_anti_abuse_required_grant_id_fkey` |
| E1 | active subscription grant on an `expired` subscription | §5 / §9.14 | REJECTED **@COMMIT** | `ForeignKeyViolationError` `access_grants_active_…_fkey` |
| E2 | active subscription grant on a `billing_retry` subscription | §9.14 | REJECTED **@COMMIT** | `ForeignKeyViolationError` — proves `billing_retry` is not entitled |
| OWN | grant `user_id` ≠ subscription `user_id` | §6 | REJECTED **@COMMIT** | `ForeignKeyViolationError` |
| SUB | two active grants on one subscription | §6 | REJECTED @stmt | `UniqueViolationError` `ix_access_grants_one_per_subscription` |
| GEN | explicit write to `product_entitled_subscription_id` | §5 | REJECTED @stmt | `GeneratedAlwaysError` |
| MS | `store_purchases` with NULL `resolved_token_value` | §5 MATCH SIMPLE | ACCEPTED | — |
| UNO | `core.subscriptions` with `user_id` NULL (unclaimed) | §5 | ACCEPTED | — |
| RB1 | `migrate.rollback(count=1)` | D-20 | `core`/`audit` both gone; `_pogo_migration` empty | — |
| RB2 | re-apply after rollback | D-20 | 17 tables recreated | — |

The three `@COMMIT` rows are the ones that need Code Example 2's explicit-transaction shape (P-6).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pogo_migrate.sql.*` helpers | `pogo_core.util.sql.*` | pogo-migrate 0.4.x | `[VERIFIED: pogo_migrate/sql.py:15-19]` — importing `pogo_migrate.sql` emits `FutureWarning: pogo_migrate.sql usage has been deprecated, please use pogo_core.util.sql`. Use `pogo_core` directly in the test harness. |
| Six incremental migrations (`00-schema.md §1`) | One from-empty migration | D-01 / PROJECT.md | See CONFLICT-2. `§1`'s ordering rules and prohibition list still bind. |
| `core.usage_monthly` keyed by `(user_id, month)` | `core.user_monthly_usage` keyed by `grant_id` | v2.0 | `[CITED: 00-schema.md:500]` "keyed by `grant_id`, NOT by user, and replaces the dropped `core.usage_monthly` entirely" |
| Plan on the user row (`users.subscription_plan`) | Tier on `core.access_tiers`, reached via grants/subscriptions | v2.0 | `[CITED: 00-schema.md:81]` "plan/tier lives on `core.access_tiers` referenced by grants and subscriptions, never on the user row" |
| `jwt_sub` on `core.users` | `(issuer, subject)` on `core.external_identities` | v2.0 | `[CITED: 00-schema.md:79]` "The external subject is never an ownership or lookup key on `core.users`" |

**Deprecated/outdated:**
- `pogo validate` — experimental, crashes on this repo's own migration (P-9). Do not use.
- `pogo_migrate.testing.apply/rollback` — works, but eagerly requires `DB_*` env vars even when
  handed a connection (P-4). Prefer `pogo_core.util.testing`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Everything verified on **PostgreSQL 16.2** behaves identically on **PostgreSQL 17** (the spec's stated target). No PG-17-only feature is used, and no PG-17 change touches STORED generated columns, partial unique indexes, deferrable FKs, or `pg_get_expr` rendering. | Whole document | LOW–MEDIUM. If wrong, the apply still almost certainly succeeds but a predicate string or an auto-generated name could differ. **Mitigation:** re-capture Code Example 4's constants from the first real PG 17 apply rather than trusting them blind. Make that an explicit plan step. |
| A2 | The developer/CI machine has, or can obtain, a PostgreSQL 17 the test suite can reach. None is reachable in the agent sandbox. | Environment Availability | HIGH. Without it, `tests/schema/` cannot run and SCHEMA-08 cannot be demonstrated. |
| A3 | `pgserver` (PyPI) is a legitimate, safe package. Discovered via WebSearch; registry existence confirmed; it ran correctly here. Not confirmed via any official documentation source. | Package Legitimacy Audit | LOW as used (throwaway `/tmp` venv, never in the project). If adopted as a dev fallback, gate behind `checkpoint:human-verify`. |
| A4 | `pgserver` 0.1.4 bundles PostgreSQL **16.2** — observed by running its bundled `postgres --version`, not from its docs. | Environment Availability | LOW. Only affects how A1's caveat is worded. |
| A5 | Which filename CONFLICT-1 resolves to. This research assembled and verified the file under D-02's `20260818_01_initial-release` name. | CONFLICT-1 | LOW technically (both apply identically from empty), MEDIUM procedurally — the requirement text and the roadmap goal currently name the other file. **Needs the user's confirmation, not the planner's choice.** |
| A6 | `tests/unit/` continues to pass after this phase. Verified today that `pytest --collect-only` collects 163 tests and `import nativespeaker.api.app.main` succeeds; the unit suite is mock-based and touches no database. But CONTEXT.md D-13 states the app "will not import after this commit". | Validation Architecture | LOW. The observed breakage is *runtime* (queries against dropped columns), not *import*. If the plan asserts "the app no longer imports" as a success signal it will be asserting something false. |

---

## Open Questions

1. **OQ-1 — PostgreSQL 17 vs 16.2 (A1).**
   - What we know: the full DDL, all 32 conformance cases, the rollback cycle, and the exact
     introspection outputs were verified on PG 16.2.
   - What's unclear: nothing observed suggests divergence, but PG 17 was never exercised.
   - Recommendation: keep every finding; add one plan task — "re-run the introspection capture against
     the real PostgreSQL 17 and reconcile Code Example 4's constants before committing the test file."
     Cheap, and it converts A1 into a verified fact.
   - **RESOLVED** by orchestrator DIRECTIVE-4, executed as plan **34-03 task 1**: the introspection
     capture is re-run against the real PostgreSQL 17 into `34-INVENTORY-PG17.md`, and task 3 copies
     its constants from that file rather than from Code Example 4. A1 closes when that task passes.

2. **OQ-2 — Which filename (CONFLICT-1).**
   - What we know: D-02 chooses `20260818_01_initial-release.sql`; SCHEMA-01 and the roadmap name
     `20260322_01_initial-release.sql`.
   - What's unclear: whether the requirement text should be amended, or D-02 revisited.
   - Recommendation: surface to the user before planning tasks. Note the asymmetric hazard —
     rewriting **in place** under the old name means any database that already applied it silently
     skips the file (P-3's corollary), which is strictly worse than the rename's loud failure.
   - **RESOLVED** by orchestrator DIRECTIVE-1 in favour of D-02's rename to
     `20260818_01_initial-release.sql`, on exactly the asymmetric-hazard reasoning above. The
     requirement text is the side that gets amended: plan **34-02 task 3** rewrites SCHEMA-01 in
     `REQUIREMENTS.md`, the Phase 34 goal in `ROADMAP.md`, the Key Decisions row plus the Constraints
     bullet in `PROJECT.md`, the global-exclusions row in `REQUIREMENTS.md`, and the v2.0 bullet in
     `STATE.md`. D-02 is not revisited; plan 34-02 task 1 gates only the one-file/six-file count.

3. **OQ-3 — How the session fixture reaches a database (D-14 discretion + A2).**
   - What we know: the repo has no `.env`, `pogo`'s DSN needs five env vars, and
     `pogo_core.util.testing.apply(db=conn)` needs none.
   - What's unclear: whether `tests/schema/` should skip cleanly when no database is reachable, or
     fail hard.
   - Recommendation: fail hard by default (SCHEMA-08 depends on these tests actually running), but
     mark the package with a dedicated marker (e.g. `schema`) so the developer can deselect it the way
     `e2e` already is `[VERIFIED: pyproject.toml:57-60]`. Do **not** reuse the `e2e` marker — the
     default `addopts` deselects it, which would silently skip the phase's only proof.
   - **RESOLVED** by adopting this recommendation verbatim — no directive was needed, because no
     source artifact contradicted it. Executed as plan **34-03 task 2**: `tests/schema/` fails hard
     rather than skipping, under a dedicated `schema` marker registered in
     `[tool.pytest.ini_options]` and deselected by `addopts`; the `e2e` marker is not reused.

4. **OQ-4 — `CREATE SCHEMA` placement (CONFLICT-4).**
   - Recommendation: unnumbered preamble before the enums banner. Trivial, but state it in the plan so
     the plan-checker does not read it as a D-06 violation.
   - **RESOLVED** by orchestrator DIRECTIVE-5, executed as plan **34-02 task 2**: the two
     `CREATE SCHEMA IF NOT EXISTS` statements are authored as an explicitly *labeled* unnumbered
     preamble above the enums banner, with the file stating that the preamble is deliberate and not a
     sixth D-06 section.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.7 (`.venv`) | — |
| `pogo-migrate` CLI | `pogo apply` / `pogo rollback` | ✓ | 0.4.2 | in-process `pogo_core.util.testing` |
| `pogo_core` | in-process apply/rollback in tests | ✓ | 0.1.2 | — |
| `asyncpg` | test harness driver | ✓ | 0.31.0 | — |
| `pytest` / `pytest-asyncio` | test runner | ✓ | 9.0.2 / 1.3.0 | — |
| `sqlparse` / `sqlglot` | pogo internals | ✓ | 0.5.2 / 30.0.1 | — |
| **PostgreSQL 17 server** | **every acceptance check in this phase** | **✗** | — | developer's own `docker-compose up db`; or `pgserver` (PG 16.2) in a scratch venv — used successfully by this research |
| `psql` client | manual inspection | ✗ | — | asyncpg from Python |
| Docker / Podman | `docker-compose.yml` (`postgres:17`) | ✗ | — | none in-sandbox |
| `sudo` (to `apt install postgresql`) | — | ✗ (password required) | — | none |
| `.env` file | `pogo` CLI DSN interpolation | ✗ (gitignored, absent) | — | pass an `asyncpg.Connection` to `pogo_core.util.testing.apply` — needs no env var |
| Network (PyPI) | installing a fallback | ✓ | — | — |

**Missing dependencies with no fallback:** none that block *planning*.

**Missing dependencies with fallback — but the fallback must be an explicit plan task:**
- **PostgreSQL 17.** Nothing in this phase can be *verified* without one. `pogo apply` succeeding is
  success criterion 1; the `tests/schema/` suite is SCHEMA-08. The plan's **first task** should be
  "provision a reachable PostgreSQL and confirm connectivity", and the phase should not be marked
  complete on a machine where that task was skipped. This research proved the fallback path works
  (embedded PG 16.2, no root, no Docker), so the executor is not blocked — but the version caveat
  (A1/OQ-1) rides along with it.

---

## Validation Architecture

> `workflow.nyquist_validation` is `true` `[VERIFIED: .planning/config.json]`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (lines 51-60) |
| Quick run command | `pytest tests/schema -x -q` |
| Full suite command | `pytest tests/schema` (plus `pytest tests/unit` for regression) |
| New marker needed | `schema: schema-conformance tests requiring a real PostgreSQL` — add to `markers` list. **Do not** reuse `e2e`; the default `addopts = "-v --tb=short -m 'not e2e'"` would deselect the phase's only proof. |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHEMA-01 | Fresh apply against empty DB succeeds; exactly one `.sql` in `migrations/` | integration | `pytest tests/schema/test_apply_rollback.py -x` | ❌ Wave 0 |
| SCHEMA-02 | `(issuer,subject)` unique; `identity_state` default; `ON DELETE RESTRICT` on identity's user | unit (DDL) | `pytest tests/schema/test_constraints.py -k identity -x` | ❌ Wave 0 |
| SCHEMA-03 | Second active grant rejected; `user_monthly_usage` PK is `grant_id` | unit (DDL) | `pytest tests/schema/test_constraints.py -k grant -x` | ❌ Wave 0 |
| SCHEMA-04 | Generated column rejects writes; non-entitled statuses rejected at COMMIT; both providers present | unit (DDL) | `pytest tests/schema/test_constraints.py -k subscription -x` | ❌ Wave 0 |
| SCHEMA-05 | `operation='restore_subscription'` rejected; the three challenge CHECKs behave | unit (DDL) | `pytest tests/schema/test_constraints.py -k challenge -x` | ❌ Wave 0 |
| SCHEMA-06 | 5 malformed audit rows rejected, 1 valid accepted; 44 + 7 enum labels | unit (DDL) | `pytest tests/schema/test_constraints.py -k audit -x` | ❌ Wave 0 |
| SCHEMA-07 | `to_regtype`/`to_regclass` negatives; no `jwt_sub` column; 4-label `access_grant_source` | unit (introspection) | `pytest tests/schema/test_inventory.py -k legacy -x` | ❌ Wave 0 |
| SCHEMA-08 | Exact-set inventory + predicates + zero triggers/views/matviews | unit (introspection) | `pytest tests/schema/test_inventory.py -x` | ❌ Wave 0 |

Every case in the Code Example 5 matrix maps to one of the rows above; the matrix is the coverage
target and it is already known to be achievable at 32/32.

### Sampling Rate

- **Per task commit:** `pytest tests/schema -x -q` (the whole suite is sub-second once the fixture's
  one-time apply is done — the prototype ran 3 tests in 0.15 s after setup).
- **Per wave merge:** `pytest tests/schema tests/unit`
- **Phase gate:** `pytest tests/schema` fully green, plus a manual `pogo apply` against a genuinely
  empty PostgreSQL 17 to satisfy success criterion 1 outside the fixture.

### Wave 0 Gaps

- [ ] `tests/schema/__init__.py`
- [ ] `tests/schema/conftest.py` — scratch DB + `pogo_core.util.testing.apply` + per-test rollback (Code Example 2)
- [ ] `tests/schema/helpers.py` — `insert_user()`, `insert_tier()`, `insert_grant()` per D-15
- [ ] `tests/schema/test_inventory.py` — covers SCHEMA-07, SCHEMA-08
- [ ] `tests/schema/test_constraints.py` — covers SCHEMA-02…SCHEMA-06
- [ ] `tests/schema/test_apply_rollback.py` — covers SCHEMA-01, D-20
- [ ] `pyproject.toml` — add the `schema` marker to `[tool.pytest.ini_options] markers`
- [ ] Framework install: none needed

---

## Security Domain

> `security_enforcement` is absent from `.planning/config.json` → treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | **no** (this phase) | The schema *stores* identity, but no authentication code ships here. `(issuer,subject)` uniqueness on `core.external_identities` is the substrate Phase 35's barrier will use. |
| V3 Session Management | no | `SHARED-INVARIANTS`: no backend-minted token, no session tier, no cookie. Nothing in the schema models a session — verify none is added. |
| V4 Access Control | **yes (partially)** | `ON DELETE RESTRICT` on `core.external_identities.user_id`; the `REVOKE DELETE ON core.external_identities` requirement, deferred to deployment per D-10/D-11. |
| V5 Input Validation | **yes** | The CHECK constraints *are* the validation layer here: the identity provider/`provider_uid` agreement, the four-arm anti-abuse shape, the challenge operation/variant matrix, the audit actor triple, and the seven `details` JSONB shape CHECKs. All verified enforcing. |
| V6 Cryptography | **yes (schema-only)** | `preauth_subject_hash BYTEA` and `actor_subject_hash BYTEA` + `actor_subject_hash_key_version SMALLINT` — raw subjects are never stored. The HMAC itself is Phase 35's job; this phase must not add a plaintext-subject column to either table. |
| V7 Error Handling & Logging | **yes** | `audit.auth_events` is the append-only audit substrate. The `details` DEFAULT ships the redaction-friendly six-key skeleton. |
| V8 Data Protection | **yes** | `§8`'s retention rules: identity rows are tombstones, never deleted; `issuer`/`subject`/`provider_uid` plaintext is the deliberate, disclosed exception because they exist solely as uniqueness reservations. |

### Known Threat Patterns for PostgreSQL DDL + this domain

| Pattern | STRIDE | Standard Mitigation | Status in this phase |
|---------|--------|---------------------|----------------------|
| Free-grant farming (one account claims repeatedly) | Elevation of Privilege | Lifetime partial unique index with **no status predicate** + `provider_accounts`/gate-consumption PK | Verified: R8 rejects a second free grant of the same source even after the first expired |
| Two concurrent active grants (entitlement double-spend) | Elevation of Privilege | Non-deferrable partial unique index, per-statement | Verified: R7 rejects |
| Entitlement without payment (grant on a lapsed subscription) | Elevation of Privilege | Deferred FK onto the STORED `product_entitled_subscription_id` | Verified: E1/E2 reject at COMMIT; `billing_retry` correctly not entitled |
| Cross-account entitlement theft (grant pointing at another user's subscription) | Elevation of Privilege | Deferred composite FK on the generated `(subscription_id, user_id)` pair | Verified: OWN rejects at COMMIT |
| Identity-row deletion to free a uniqueness reservation | Repudiation / Tampering | `ON DELETE RESTRICT`; plus `REVOKE DELETE` at the role layer | RESTRICT verified (D16). REVOKE deferred — **must be recorded in PROJECT.md per D-11, not just in a SQL comment** |
| Re-registration of a retired Google/Apple account | Elevation of Privilege | Partial unique index covering `active` **and** `historical` rows | Present by construction (`WHERE provider_uid IS NOT NULL`, no state predicate) |
| Audit-log forgery / actor spoofing | Repudiation | All-or-nothing actor CHECK; keyed hash + key version; no free-text outcome column | Verified: A1–A5 reject, A6 accepts |
| Raw external subject leaking into audit or challenge rows | Information Disclosure | `BYTEA` hash columns only; `core.external_identities` is the sole plaintext store | Present by construction — **planner must not add a convenience plaintext column** |
| SQL injection | Tampering | Not applicable — no application code ships. In `tests/schema/`, use asyncpg `$1` parameters, never f-strings, for row data. The one legitimate f-string is the scratch **database name** in `CREATE DATABASE` (identifiers cannot be parameterized) — keep it a module constant, never test input. | — |
| Unreviewed extra object slipping into the schema | Tampering | D-18's exact-set assertions | Enabled by Code Example 4 |

---

## Project Constraints (from AGENTS.md)

`/home/init/native-speaker/CLAUDE.md` is `@AGENTS.md`; the actionable directives are:

| Directive | Bearing on Phase 34 | Compliance check |
|-----------|--------------------|------------------|
| "First version of the app, built by a startup. There are no users yet" | Confirms the destructive-drop posture in the phase boundary. | The plan must not add backfill, dual-write, or compatibility tasks. |
| "Don't over-engineer for that threat model. But don't skip normal security measures" | The schema's declarative constraints *are* the normal measure. Do not add a role/permission layer this repo cannot define (D-10). | Do not invent a database role. Do not add triggers "for safety" (§1 forbids them). |
| **"Keep specs short: programming this app should not consume many tokens."** | Strongest constraint on this phase's *plan*. The DDL is ~470 lines of transcription; the plan should be a small number of large, mechanical tasks, not a task per table. | Aim for ~3–5 plan tasks: (1) provision a database, (2) write the migration file + delete the old one, (3) `tests/schema/` harness + inventory, (4) `tests/schema/` constraints + rollback, (5) PROJECT.md note per D-11. |
| "Runs in a Kubernetes cluster behind Envoy Gateway, which authenticates by JWT and rate-limits by IP, user, URL" | Context only; no schema impact this phase. | — |
| `.planning/config.json`: `commit_docs: false` | Write RESEARCH.md/PLAN.md to disk; do not commit planning docs. | — |
| `.planning/config.json`: `granularity: "fine"`, `parallelization: true` | The migration file and the test harness are genuinely parallelizable *after* the database exists — but the tests cannot be written against constants that have not been captured yet. | Wave 1 = provision + migration file. Wave 2 = tests. Do not parallelize the capture step away. |

No `./CLAUDE.md` or `./.claude/CLAUDE.md` exists inside `ns-api-gateway/` (both are gitignored at
`.gitignore:1-2`); no `.claude/skills/` or `.agents/skills/` directory exists.

---

## Sources

### Primary (HIGH confidence)

- **Live PostgreSQL 16.2** (`pgserver` 0.1.4, unix socket, `/tmp/schemaverify`) — assembled migration
  applied through `pogo_core.util.migrate.apply`; 54-index / 11-enum / 17-table inventory captured;
  32 conformance cases executed; rollback + re-apply cycle executed; `search_path` predicate-rendering
  experiment executed; two rename/stray-file hazards reproduced.
- `/home/init/native-speaker/specs/auth-refactor-phases/00-schema.md` — §0–§10, the binding DDL.
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — cross-phase rules.
- `.venv/lib/python3.14/site-packages/pogo_core/migration.py` (lines 22, 27, 49, 52-54, 61, 97) —
  comment stripping, statement termination, header regex, duplicate-depends guard, transaction
  default, hash-over-id.
- `.venv/lib/python3.14/site-packages/pogo_core/util/sql.py` (lines 24, 36-41) — `SET search_path`,
  `Migration(path.stem, …)`, directory iteration.
- `.venv/lib/python3.14/site-packages/pogo_core/util/migrate.py` — one-transaction apply, skip-if-applied.
- `.venv/lib/python3.14/site-packages/pogo_migrate/testing.py` (lines 15, 20) and
  `pogo_migrate/config.py` (lines 27, 36) — the eager-DSN gotcha.
- `.venv/lib/python3.14/site-packages/pogo_migrate/cli.py` (lines 380-466, 698-770) — `apply`,
  `rollback --count` default 1, `validate [EXPERIMENTAL]`.
- `ns-api-gateway/pyproject.toml`, `migrations/20260322_01_initial-release.sql`, `tests/conftest.py`,
  `tests/e2e/conftest.py`, `docker-compose.yml`, `.env.example`, `.gitignore`, `k8s/`.
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/config.json`,
  `.planning/phases/34-schema/34-CONTEXT.md`.

### Secondary (MEDIUM confidence)

- https://www.postgresql.org/docs/17/ddl-generated-columns.html — the documented generated-column
  restrictions (no default, no identity, not in a partition key, immutable functions only, no
  reference to another generated column). Notably **silent** on foreign keys — which is why this
  research executed them instead.
- https://www.postgresql.org/docs/17/sql-createtable.html — `DEFERRABLE INITIALLY DEFERRED` and
  `MATCH SIMPLE` semantics, quoted verbatim in Architecture Patterns.
- https://github.com/orm011/pgserver + https://pypi.org/project/pgserver/ — embedded PostgreSQL for
  Python, no root, no Docker.

### Tertiary (LOW confidence)

- WebSearch results for PostgreSQL FK-on-generated-column restrictions returned no authoritative
  statement either way. Superseded by direct execution.

---

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — every tool is already installed and pinned; versions read from disk.
- Architecture / DDL correctness: **HIGH** — the DDL was executed, not reasoned about. Downgraded to
  MEDIUM only on the PG 16.2 → 17 extrapolation (A1/OQ-1).
- Inventory constants (Code Example 4): **HIGH** — read out of a live database. Re-capture on PG 17
  before committing (OQ-1).
- Pitfalls P-1…P-11: **HIGH** — every one was reproduced this session with the exact error text.
- Test-harness pattern (Code Example 2): **HIGH** — prototyped and run green under the project's own
  interpreter and pytest settings.
- Environment: **HIGH** — probed directly.
- Filename decision: **LOW** — genuinely conflicting inputs; needs the user (OQ-2).

**Research date:** 2026-08-19
**Valid until:** 2026-09-18 (30 days — the spec is frozen and the toolchain is pinned; the only
volatile input is which PostgreSQL the developer provisions)
