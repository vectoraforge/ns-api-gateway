# Project Research Summary

**Project:** ns-api-gateway — v1.6 Schema Hardening
**Domain:** Native PostgreSQL enum types + config-driven quotas in existing FastAPI / SQLAlchemy async / SQLModel / Pydantic v2 app
**Researched:** 2026-03-23
**Confidence:** HIGH

## Executive Summary

This milestone replaces two related anti-patterns in the current schema: TEXT columns that should be native PostgreSQL enum types, and a static `core.plans` lookup table that is queried on every request despite never changing at runtime. Research confirms the entire change set can be delivered with zero new dependencies — SQLAlchemy 2.0.46, SQLModel 0.0.37, Pydantic 2.12.5, pyyaml, and pogo-migrate are already installed and fully capable.

The recommended approach is a single, atomically-structured migration that creates the four PG enum types in the `core` schema, drops FK constraints, converts all TEXT enum columns using `USING column::core.type`, and drops the `core.plans` table. Alongside this, `QuotaConfig` (a Pydantic model with `dict[Tier, int]`) replaces the plans table in `AppConfig`, and `UsageDB.try_increment` is simplified to accept `monthly_quota: int` directly from the service layer instead of performing a JOIN + subquery. The result is a simpler query path (no JOIN on every chat creation), stronger data integrity (DB-enforced enum constraints), and fail-fast quota validation at startup.

The primary risks are migration ordering constraints that are easy to get wrong: PostgreSQL requires column DEFAULTs to be dropped before `ALTER COLUMN TYPE`, FK constraints must be dropped before column type changes and before `DROP TABLE`, and all four `CREATE TYPE` statements must precede any `ALTER COLUMN`. A secondary risk is test/production schema drift from `create_all()` creating enum types in the wrong schema — this is eliminated by setting `create_type=False` on all `SAEnum` objects and having the test fixture create types explicitly before calling `create_all()`. All risks have well-understood mitigations documented in PITFALLS.md.

## Key Findings

### Recommended Stack

No new dependencies are required. The change relies entirely on existing stack capabilities: `sqlalchemy.dialects.postgresql.ENUM` (via `sa_type=` on SQLModel fields) with `create_type=False` and explicit `schema="core"`, and Pydantic `dict[Tier, int]` for config-validated quota mapping. Both are verified against the installed versions.

The critical implementation choice is `sa_type=PG_ENUM(...)` over `sa_column=Column(...)` — `sa_type` composes with other `Field()` parameters (default, index) while `sa_column` replaces them. This matches the project's existing `PydanticJSONB` pattern. Each `PG_ENUM` type object must be defined once at module level and shared across all model fields that reference the same PG type.

**Core technologies:**
- `sqlalchemy.dialects.postgresql.ENUM`: native PG enum column type — `create_type=False` + `schema="core"` is mandatory; prevents SQLAlchemy/migration DDL conflict
- `pydantic.BaseModel` (`QuotaConfig`): config-driven quota model — `dict[Tier, int]` validates enum keys at startup, catches missing tiers before first request
- `pogo-migrate` raw SQL: single migration file owns all DDL — atomic transaction covering CREATE TYPE, DROP CONSTRAINT, ALTER COLUMN, DROP TABLE

### Expected Features

The milestone has a clear, bounded scope with no ambiguous requirements.

**Must have (table stakes for v1.6):**
- `QuotaConfig` Pydantic model + YAML `quotas` section replacing `core.plans` table
- `UsageDB.try_increment` accepting `monthly_quota: int` (no JOIN to plans)
- `UsageDB.get_monthly_limit` removed; replaced by `config.quotas.monthly_quota(user.plan)` in callers
- Single pogo-migrate migration: CREATE TYPE x4, DROP FK x2, ALTER COLUMN TYPE x7, DROP TABLE plans
- SQLModel fields updated with `sa_type=PG_ENUM(...)` and `create_type=False`
- `Plan` model class deleted
- E2E conftest updated (remove plans seed, add CREATE TYPE before `create_all()`)
- Unit test mocks updated for new `try_increment` signature

**Should have (valuable but not blocking):**
- Startup exhaustiveness check: `model_validator` that confirms all Tier values have quota entries
- Type narrowing: `User.plan` and `Subscription.plan` from `str` to `Tier`
- Type narrowing: `SubscriptionEvent.old_tier`/`new_tier` from `str | None` to `Tier | None`
- `UserProfileResponse.plan` from `str` to `Tier` (non-breaking OpenAPI change)

**Defer (not in scope for v1.6):**
- Migration idempotency guards (`DO $$ ... $$` plpgsql blocks) — nice-to-have, not required for a one-shot migration
- `old_tier`/`new_tier` typed as `Tier | None` on SubscriptionEvent — audit-only fields, low urgency

### Architecture Approach

The architecture change is a targeted rewiring of the quota enforcement data flow. The service boundary is preserved: `ChatService` owns the business logic decision of which quota applies (it reads `config.quotas.monthly_quota(user.plan)`), and `UsageDB` owns only the SQL (it receives the quota as a primitive `int`). The `get_current_user` dependency already resolves the `User` object, so `create_chat` can accept `user: User` instead of `user_id: UUID`, giving the service access to `user.plan` without an extra DB query.

**Modified components:**
1. `config.py` / `config.yaml` — adds `QuotaConfig` with `tier_quotas: dict[Tier, int]`; `AppConfig` gains `quotas: QuotaConfig`
2. `models.py` — adds `PG_ENUM` module-level type objects; applies `sa_type=` to all enum fields; removes `Plan` model and FK declarations
3. `database/usage.py` — `try_increment` takes `monthly_quota: int`; `get_monthly_limit` removed; all table refs schema-qualified to `core.`
4. `services/chats.py` — receives `QuotaConfig` at construction; passes `user: User` to methods; resolves quota before calling `try_increment`
5. `routers/users.py` — injects `AppConfig` via DI; replaces `usage_db.get_monthly_limit` with `config.quotas.monthly_quota(user.plan)`
6. `app/dependencies.py` — passes `quota_config=config.quotas` to `ChatService` constructor
7. `migrations/` — new single SQL file with strict phase ordering
8. `tests/` — remove plans seed, add CREATE TYPE before `create_all()`, update mock signatures

### Critical Pitfalls

1. **Column DEFAULT blocks ALTER COLUMN TYPE** — PostgreSQL will not auto-cast a TEXT default to an enum type. For `users.plan` and `subscriptions.plan` (both with `DEFAULT 'free'`): drop default, alter type with USING clause, re-add default as `'free'::core.tier`. If omitted, migration fails mid-run.

2. **FK constraints must precede ALTER COLUMN and DROP TABLE** — `ALTER COLUMN plan TYPE core.tier` fails while `users_plan_fkey` references `core.plans(tier)` (type mismatch). `DROP TABLE core.plans` fails while FK constraints exist. Drop FKs explicitly using exact constraint names from `information_schema`; do not use `DROP TABLE ... CASCADE` as a silent workaround.

3. **create_type=False is mandatory** — Without it, `create_all()` in tests attempts `CREATE TYPE` in the `public` schema, conflicting with the migration's `core.tier` types. All four `PG_ENUM` objects must set `create_type=False`. The E2E test fixture must explicitly run `CREATE TYPE IF NOT EXISTS core.<type>` before `create_all()`.

4. **schema="core" must be explicit on every SAEnum** — Without it, SQLAlchemy generates unqualified type casts (`CAST('free' AS tier)` instead of `CAST('free' AS core.tier)`). PostgreSQL will not find the type if `core` is not in `search_path`. Every `PG_ENUM` / `SAEnum` constructor must include `schema="core"`.

5. **asyncpg OID cache invalidation after migration** — Existing pooled connections do not see new PG enum types created by the migration. Application must be restarted after the migration runs. In Kubernetes, the migration runs as an init container or Job before new pods start — this is already the correct pattern and avoids the issue automatically.

## Implications for Roadmap

Based on combined research, the changes decompose into four phases with a strict dependency order. This is a focused migration milestone, not a multi-week feature build.

### Phase 1: Config and Model Foundation

**Rationale:** All downstream code depends on `QuotaConfig` existing in `AppConfig` and on the SQLModel enum field definitions being in place. These are purely additive changes — they do not break anything because StrEnum values are strings and existing TEXT columns still accept them. This phase can be merged and deployed independently, before the migration runs.

**Delivers:** `QuotaConfig` Pydantic model, YAML `quotas` section, module-level `PG_ENUM` type objects on all enum fields, `Plan` model deleted, type annotations narrowed to `Tier`/`Role`/etc., `UserProfileResponse.plan` typed as `Tier`.

**Addresses:** Config-driven quotas, type-safe plan field, remove dead `Plan` model.

**Avoids:** Pitfall 3 (create_type=False must be set before any test run uses create_all), Pitfall 4 (schema="core" on all SAEnums from the start).

### Phase 2: Service and Database Layer Rewiring

**Rationale:** `UsageDB.try_increment` signature change and `ChatService` quota resolution are tightly coupled — one cannot ship without the other. `get_monthly_limit` removal must coincide with the users router switching to config lookup. These changes break existing behavior if deployed before the migration (the `JOIN plans` query disappears), so Phase 2 must deploy together with Phase 3.

**Delivers:** `UsageDB.try_increment(user_id, month, monthly_quota)` with schema-qualified SQL, `get_monthly_limit` removed, `ChatService` reads quota from `QuotaConfig` and passes `user: User` to create methods, users router reads monthly limit from config, `dependencies.py` passes `quota_config` to `ChatService`.

**Addresses:** Simplified quota enforcement query (no JOIN), correct schema qualification on all raw SQL, preserved service/DB boundary.

**Avoids:** Pitfall 6 (unqualified table names in raw SQL), Anti-pattern 4 (config lookup stays in service layer, not DB layer).

### Phase 3: Migration

**Rationale:** All DDL changes are logically atomic and must run as a single migration transaction. The strict internal ordering is critical: CREATE TYPE first, then DROP DEFAULT, then DROP FK, then ALTER COLUMN TYPE with USING, then SET DEFAULT as enum cast, then DROP TABLE plans. This phase is what makes the app code from Phase 2 correct in production.

**Delivers:** `core.role`, `core.tier`, `core.subscription_provider`, `core.subscription_status` PG enum types; seven TEXT columns converted to native enum types; FK constraints removed; `core.plans` table dropped; fully functional rollback section.

**Addresses:** Database-level enum enforcement, `core.plans` removal, FK constraint cleanup.

**Avoids:** Pitfall 1 (drop/re-add defaults around ALTER COLUMN), Pitfall 2 (CREATE TYPE before ALTER COLUMN), Pitfall 3 (DROP FK before DROP TABLE), Pitfall 10 (rollback in reverse order), Pitfall 11 (consider renaming `role` to `message_role` to avoid keyword ambiguity).

### Phase 4: Test Updates

**Rationale:** Tests validate the final state. They depend on all code and schema changes being complete. Updating them last ensures tests reflect the actual new contract, not an intermediate state.

**Delivers:** E2E conftest with CREATE TYPE statements before `create_all()` and plans seed removed; unit conftest with `QuotaConfig` fixture and `get_monthly_limit` mock removed; `test_usage.py` updated for new `try_increment` signature; serialization test verifying `GET /users/me` returns `"plan": "free"` not `"plan": "Tier.free"`.

**Addresses:** CI integrity after plans table removal.

**Avoids:** Pitfall 7 (plans seed in conftest), Pitfall 12 (response serialization regression).

### Phase Ordering Rationale

- Config and model changes first because every subsequent code change imports from them
- Service/DB rewiring and migration must deploy together — Phase 2 removes the plans JOIN but the plans table must also be gone at the same deploy
- In practice Phases 1-3 code changes can be in a single PR; the migration runs as a deploy-time step (K8s init container), not as part of application startup
- Tests last because they catch regressions in the final integrated state; updating them alongside code changes means they test the right thing

### Research Flags

Phases with well-understood patterns (no additional research needed):
- **Phase 1:** Standard Pydantic config extension and SQLModel field annotation — both are documented and locally verified
- **Phase 2:** Straightforward SQL rewrite and DI wiring — follows existing project patterns exactly
- **Phase 3:** Standard PostgreSQL DDL — all syntax is from official PostgreSQL docs; migration ordering is deterministic
- **Phase 4:** Fixture updates are mechanical — remove what references the deleted table, add what references the new config

No phases require a `research-phase` call. All patterns are HIGH-confidence and verified against installed library versions.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new dependencies; all patterns locally tested against SQLModel 0.0.37 + SQLAlchemy 2.0.46 + Pydantic 2.12.5 |
| Features | HIGH | Scope is bounded and explicit; all items are direct replacements for known behavior |
| Architecture | HIGH | Full codebase inspection; all integration points traced; DI patterns match existing conventions |
| Pitfalls | HIGH | All critical pitfalls are from official PostgreSQL/SQLAlchemy docs or directly observed in the codebase |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact FK constraint names:** The migration assumes `users_plan_fkey` and `subscriptions_plan_fkey`. These names should be confirmed against the live database before the migration is written (`SELECT constraint_name FROM information_schema.table_constraints WHERE table_schema = 'core' AND constraint_type = 'FOREIGN KEY'`).

- **`Message.__tablename__` anomaly:** `models.py` has `__tablename__ = "core.messages"` alongside `__table_args__ = {"schema": "core"}`, which is a double-prefix. This should be corrected to `__tablename__ = "messages"` as part of this release. It is an existing bug that becomes relevant when `create_all()` is called.

- **`role` keyword concern:** `core.role` uses a PostgreSQL non-reserved keyword as the type name. This works but could cause confusion in SQL tools. Consider `core.message_role` as an alternative. Decision should be made before writing the migration to avoid a follow-up rename.

- **`values_callable` consistency:** STACK.md notes that current StrEnums have name == value so `values_callable` is technically unnecessary, while FEATURES.md and ARCHITECTURE.md both recommend always including it. The safe and recommended choice is to always include `values_callable=lambda x: [e.value for e in x]` on every `PG_ENUM` definition as a project convention.

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 PostgreSQL Dialect — postgresql.ENUM](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html) — `create_type`, `schema` params
- [SQLAlchemy 2.0 Type Basics — Enum](https://docs.sqlalchemy.org/en/20/core/type_basics.html) — `values_callable`, `native_enum`, `inherit_schema`
- [PostgreSQL 18 ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — DEFAULT drop/re-add requirement, USING clause
- [PostgreSQL 18 Enumerated Types](https://www.postgresql.org/docs/current/datatype-enum.html) — CREATE TYPE, ALTER TYPE
- [SQLAlchemy Discussion #12123](https://github.com/sqlalchemy/sqlalchemy/discussions/12123) — StrEnum processing, values_callable
- [SQLAlchemy Discussion #10583](https://github.com/sqlalchemy/sqlalchemy/discussions/10583) — schema-qualified enums, inherit_schema
- Local verification: `sa_type=PG_ENUM(...)` with `create_type=False`, `schema="core"`, `default=Tier.free` tested against installed versions

### Secondary (MEDIUM confidence)
- [PostgreSQL Enum Types with SQLModel](https://shekhargulati.com/2025/01/12/postgresql-enum-types-with-sqlmodel-and-alembic/) — end-to-end walkthrough
- [SQLModel Discussion #717](https://github.com/fastapi/sqlmodel/discussions/717) — StrEnum breaking change in 0.0.9+
- [SQLModel Issue #96](https://github.com/fastapi/sqlmodel/issues/96) — sa_column pattern for PG enums
- [SQLAlchemy Discussion #6648](https://github.com/sqlalchemy/sqlalchemy/discussions/6648) — asyncpg OID cache invalidation

### Tertiary (supporting)
- [pogo-migrate on PyPI](https://pypi.org/project/pogo-migrate/) — migration file format
- [PostgreSQL ALTER TYPE](https://www.postgresql.org/docs/current/sql-altertype.html) — ADD VALUE limitations
- Codebase inspection: all files in `src/nativespeaker/api/` and `tests/`

---
*Research completed: 2026-03-23*
*Ready for roadmap: yes*
