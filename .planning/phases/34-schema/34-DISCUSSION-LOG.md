# Phase 34: Schema - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-19
**Phase:** 34-Schema
**Areas discussed:** Rollback section, Conformance tests, Acceptance proof, DB role / REVOKE

---

## Rollback Section & File Structure

### Q1 — What should `-- migrate: rollback` contain?

| Option | Description | Selected |
|--------|-------------|----------|
| DROP SCHEMA CASCADE | Two statements dropping `audit` then `core`. The apply target is an empty database, so the schema pair is the natural unit. Immune to drift. | ✓ |
| Explicit reverse-order drop list | Mirrors the current file: every table, then every enum, then the schemas. Self-documenting but ~35 hand-maintained lines with silent drift risk. | |
| Hybrid — CASCADE plus a comment | CASCADE as the body, with a comment naming the scope removed. | |

**User's choice:** DROP SCHEMA CASCADE

### Q2 — File identity and description header

| Option | Description | Selected |
|--------|-------------|----------|
| Keep id, rewrite description | Filename and pogo id unchanged; only the description line changes. | |
| Keep everything as-is | Smallest diff, but leaves a header describing a schema that no longer exists. | |
| Rename to a 20260818 id | Date reflects the v2.0 rewrite. Changes the pogo id, so any dev database with the old id must be dropped — which `§9.13` mandates anyway. | ✓ |

**User's choice:** Rename to a 20260818 id
**Notes:** Consequence accepted — the old file is removed rather than edited, and the dev database is dropped and rebuilt.

### Q3 — Exact filename

| Option | Description | Selected |
|--------|-------------|----------|
| `20260818_01_initial-release.sql` | Keeps the `initial-release` slug; matches the ids the spec's own six-file sequence used. | ✓ |
| `20260818_01_auth-schema.sql` | Names what the migration now delivers; drops a slug that no longer carries meaning. | |
| `20260818_01_initial-auth-schema.sql` | Both signals, unambiguous to a cold reader of `migrations/`. | |

**User's choice:** `20260818_01_initial-release.sql`
**Notes:** `-- depends:` stays empty — it remains the root migration.

### Q4 — Internal organization of the ~500-line apply section

| Option | Description | Selected |
|--------|-------------|----------|
| Section comments per spec group | Five banner-commented sections in spec order: enums → identity/tiers → subscriptions/store → grants/anti-abuse/usage → challenges/audit. Preserves `§1`'s mandated ordering by construction. | ✓ |
| Group by object type | All enums, then tables, then indexes, then deferred FK ALTERs. Risks a subtle ordering violation for no real gain. | |
| Flat, dependency order only | Smallest file, but review against a 46KB spec means tracking position by eye. | |

**User's choice:** Section comments per spec group

---

## Conformance Tests

### Q1 — Does Phase 34 ship the `§10` constraint-rejection tests?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, ship them this phase | SCHEMA-08 names `§10` as a requirement and `§10` enumerates nine rejection cases. Also the only tests that can run before the app boots again. | ✓ |
| Defer to Phase 36 | Keeps Phase 34 to pure SQL, but leaves the schema unverified across two phases. | |
| Minimal subset only | Cheaper, but `§10` names its cases explicitly, so a subset leaves SCHEMA-08 partially unmet. | |

**User's choice:** Yes, ship them this phase

### Q2 — Where do they live?

| Option | Description | Selected |
|--------|-------------|----------|
| New `tests/schema/` package | Own conftest, raw driver connection, zero `nativespeaker.api` imports — runs green while the app is broken. | ✓ |
| `tests/e2e/schema/` subpackage | Groups with other real-infrastructure tests, but pytest collects `tests/e2e/conftest.py` for every subdirectory, so its app import and lifespan fixture would run. | |
| Standalone SQL assertion script | No Python test dependency, but no fixtures, no useful failure output, never runs in CI. | |

**User's choice:** New `tests/schema/` package
**Notes:** Constraint surfaced during codebase scout — `tests/e2e/conftest.py` imports `nativespeaker.api.app.main` and runs the app lifespan.

### Q3 — How is the test database provisioned?

| Option | Description | Selected |
|--------|-------------|----------|
| Session fixture runs `pogo apply` | Self-contained, and turns `§10`'s first acceptance check into something the suite exercises rather than asserts about. | ✓ |
| Connect to an externally-migrated DB | Simplest fixture, but the apply itself goes untested and a stale database yields confusing failures. | |
| Execute the `.sql` file directly | Fast and dependency-free, but tests the SQL rather than the migration — a broken pogo header would sail through. | |

**User's choice:** Session fixture runs `pogo apply`

### Q4 — How much seeding machinery?

| Option | Description | Selected |
|--------|-------------|----------|
| Small typed insert helpers | `insert_user()` / `insert_tier()` / `insert_grant(...)` returning ids, with per-test rollback. Mirrors the project's existing convention. | ✓ |
| Session-scoped shared fixture rows | Fastest, but the second-active-grant and second-free-grant tests mutate shared state — order-dependent and fragile. | |
| Inline SQL per test | Maximum explicitness, but the parent chain repeats in all nine cases. | |

**User's choice:** Small typed insert helpers

---

## Acceptance Proof

### Q1 — How is the `§10` object inventory proven?

| Option | Description | Selected |
|--------|-------------|----------|
| Introspection tests in `tests/schema/` | Query `pg_catalog` / `information_schema` and assert the sets by name. Catches transcription slips in a 500-line hand-written DDL file. | ✓ |
| Documented manual runbook | No new code, but proves the schema only when someone runs it. | |
| Reviewer eyeball of the SQL | Zero cost, but index predicates and enum label sets are exactly what human review misses. | |

**User's choice:** Introspection tests in `tests/schema/`

### Q2 — Exact-set or superset assertions?

| Option | Description | Selected |
|--------|-------------|----------|
| Exact set — these and only these | Full name-set equality plus zero triggers/views/matviews. Only this catches the stray object `§1` forbids. | ✓ |
| Superset — at least these exist | Never fails spuriously, but cannot detect a leftover legacy table or a well-meant extra index. | |
| Exact for enums/tables, superset for indexes | Pragmatic, but the five unique indexes are load-bearing invariants, not tuning. | |

**User's choice:** Exact set

### Q3 — How are index predicates asserted?

| Option | Description | Selected |
|--------|-------------|----------|
| Assert normalized predicate text | Compare `pg_get_expr(indpred, indrelid)` against strings captured from a real applied database. Pins the predicate exactly. | ✓ |
| Assert behavior, not predicate text | Immune to formatting changes, but a too-broad predicate passes every rejection test while wrongly rejecting valid rows. | |
| Both — text and behavior | Pins from both directions; costs duplication. | |

**User's choice:** Assert normalized predicate text
**Notes:** The rejection tests decided in the previous area already supply the behavioral half in practice.

### Q4 — Is the rollback exercised?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — a dedicated apply/rollback test | Applies, runs `pogo rollback`, asserts neither `core` nor `audit` remains. Cheap now the fixture already shells out to pogo. | ✓ |
| No — verify manually once | Costs nothing to build, but the rollback silently rots when the migration changes. | |
| Rely on fixture teardown | Dropping a database is not the `pogo rollback` code path — proves nothing about the rollback section. | |

**User's choice:** Yes — a dedicated apply/rollback test

---

## DB Role / REVOKE

### Q1 — Which branch of `§8`'s final bullet?

| Option | Description | Selected |
|--------|-------------|----------|
| Comment only — no role invented | Fits the evidence: no role exists in this repo, `DB_USER` resolves to whatever the deployment supplies. | ✓ |
| Create an application role in the migration | Enforced rather than documented, but invents deployment topology the repo does not own — which `§8` warns against. | |
| Conditional REVOKE on an existing role | Enforces where possible, no-ops otherwise — but needs a role name, and there is none. | |

**User's choice:** Comment only — no role invented
**Notes:** Scout confirmed the repo defines no role — only a `DB_USER` placeholder in `[tool.pogo] database_config` and `POSTGRES_USER` in `docker-compose.yml`.

### Q2 — Should the requirement be recorded outside the migration?

| Option | Description | Selected |
|--------|-------------|----------|
| Also carry it forward as a project note | PROJECT.md "Known areas for future work". The SQL comment reaches whoever reads the migration; the project note reaches whoever provisions the cluster. | ✓ |
| Migration comment only | Maximum locality, but nobody writing Helm role definitions reads the migration file. | |
| Comment plus a Helm chart TODO | Closest to point of use, but the chart does not manage roles today. | |

**User's choice:** Also carry it forward as a project note

### Q3 — Test the `ON DELETE RESTRICT` on `external_identities.user_id`?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — test the RESTRICT | The one part of "identity rows are never deleted" the schema can enforce without a role; three lines given the insert helpers exist. | ✓ |
| No — stick to the `§10` list | Keeps scope traceable one-to-one to the requirement, but leaves the most consequential delete-behavior guarantee unexercised. | |
| Test the whole `§8` cascade list | Most thorough, but meaningfully larger than `§10` asks for. | |

**User's choice:** Yes — test the RESTRICT
**Notes:** The full `§8` cascade list was scoped down and recorded as a deferred idea.

---

## Claude's Discretion

- Inline commenting depth for the anti-abuse CHECK arms, the STORED generated column, and the `audit.auth_events` actor-field CHECKs.
- Whether `§9` ruling numbers are cited inline in the SQL where a more natural-looking alternative was deliberately rejected.
- Raw driver choice for `tests/schema/` (asyncpg vs psycopg); sync vs async suite.
- Test file split within `tests/schema/`.
- Naming and reachability of the dedicated test database.

## Deferred Ideas

- Full `§8` cascade-list introspection beyond the single `ON DELETE RESTRICT` test — candidate for Phase 36.
- Actual `REVOKE DELETE` enforcement — blocked until the deployment defines a database role.
- Application/model alignment with the new schema — Phases 35 and 36 by the phase boundary.
