---
phase: 37-post-auth-create-user
plan: 04
subsystem: database
tags: [sqlmodel, sqlalchemy, postgres, asyncpg, purchase-attribution, enum, schema-test]

requires:
  - phase: 37-01
    provides: the schema baseline these models sit on (operation_variant removed)
  - phase: 34
    provides: the schema-conformance suite (scratch database, apply, per-test rollback)
provides:
  - "PurchaseProvider (StrEnum) — the Python mirror of the pre-existing core.subscription_provider type"
  - "StorePurchaseToken (SQLModel table class) over the PK-less core.store_purchase_tokens"
  - "Both symbols exported from nativespeaker.api.models"
  - "RESEARCH assumption A2 closed-CONFIRMED by a committed round-trip against PostgreSQL 17.11"
  - "The live constraint names both UNIQUE rules report, for constraint-name discrimination downstream"
affects: [37-07, 37-08, 37-09, 37-10, phase-40, phase-41, phase-42]

actuals:
  tokens: 7756
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "ORM-level composite primary key over a deliberately PK-less table"
    - "Explicit name=/schema= pinning when the Python enum class and the PostgreSQL type names diverge"
    - "A schema test that builds its own SQLAlchemy engine over the scratch database to exercise the mapper"

key-files:
  created:
    - src/nativespeaker/api/models/purchase_tokens.py
    - tests/schema/test_store_purchase_tokens.py
  modified:
    - src/nativespeaker/api/models/__init__.py
    - tests/unit/test_models.py

key-decisions:
  - "A2 confirmed: SQLAlchemy accepts an ORM-level composite primary key on a table with no database PK and INSERTs/commits correctly. The Core-insert() fallback is NOT needed; 37-07 writes its transaction through the mapped class."
  - "The D-16 guard collision is resolved by naming, not by amending the guard: models/purchase_tokens.py + PurchaseProvider/StorePurchaseToken, with tests/unit/test_users.py untouched."
  - "PurchaseProviderType pins name='subscription_provider', schema='core' — the Python class and the database type deliberately carry different names, and this phase renames neither database object."
  - "No unique=True on identity_value: the database rule is the composite UNIQUE (provider, identity_value), and a single-column marker would claim a stricter rule than is enforced."
  - "No default_factory on identity_value or created_at: the creating transaction owns the single clock (35 D-02 evaluated_at) and the single RNG (uuid4 per row)."
  - "tests/schema/test_store_purchase_tokens.py is the one documented exception to the package's no-application-imports rule, and it commits rather than rolls back, because A2 is a claim about a committed INSERT through the mapper."

patterns-established:
  - "Python/database name divergence is held together by an explicit name=/schema= pair and a comment saying it may not be tidied to match the class"
  - "Constraint discrimination reads constraint_name off the asyncpg cause under the SQLAlchemy IntegrityError, never str(exc)"
  - "Expected constraint names are looked up from pg_constraint at test time, not hardcoded"

requirements-completed: [CREATE-03]

coverage:
  - id: D1
    description: "PurchaseProvider mirrors core.subscription_provider with exactly two members, apple and google_play"
    requirement: CREATE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_models.py#TestPurchaseProviderEnum::test_exactly_two_members_in_migration_order"
        status: pass
      - kind: unit
        ref: "tests/unit/test_models.py#TestPurchaseProviderEnum::test_values_are_the_migration_labels"
        status: pass
    human_judgment: false
  - id: D2
    description: "StorePurchaseToken imports and its mapper configures over the PK-less table, with exactly the four migration columns and an ORM-level (user_id, provider) key"
    requirement: CREATE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_models.py#TestStorePurchaseTokenMapping::test_the_models_package_imports"
        status: pass
      - kind: unit
        ref: "tests/unit/test_models.py#TestStorePurchaseTokenMapping::test_orm_primary_key_is_the_composite_user_id_provider"
        status: pass
      - kind: unit
        ref: "tests/unit/test_models.py#TestStorePurchaseTokenMapping::test_column_set_is_exactly_the_four_table_columns"
        status: pass
    human_judgment: false
  - id: D3
    description: "The mapped provider column still binds to the pre-existing core.subscription_provider PostgreSQL type — no second enum type is emitted (T-37-14)"
    requirement: CREATE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_models.py#TestStorePurchaseTokenMapping::test_provider_column_binds_the_pre_existing_database_enum_type"
        status: pass
      - kind: integration
        ref: ".venv/bin/pytest -q -m schema tests/schema/test_store_purchase_tokens.py (rows INSERT against the real enum type)"
        status: pass
    human_judgment: false
  - id: D4
    description: "RESEARCH A2 proven: two StorePurchaseToken rows for one user across both providers flush and COMMIT through the ORM against a table with no database primary key, and round-trip on re-read"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/schema/test_store_purchase_tokens.py#TestTheMapperCommitsAgainstAPkLessTable::test_both_providers_commit_for_one_user_and_round_trip"
        status: pass
      - kind: integration
        ref: "tests/schema/test_store_purchase_tokens.py#TestTheMapperCommitsAgainstAPkLessTable::test_a_committed_token_is_visible_to_a_fresh_session"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both database UNIQUE rules fire and are discriminated by live constraint name; the composite (provider, identity_value) rule is proven to be the real one"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/schema/test_store_purchase_tokens.py#TestTheDatabaseOwnsTheUniquenessRules::test_one_token_per_user_per_store"
        status: pass
      - kind: integration
        ref: "tests/schema/test_store_purchase_tokens.py#TestTheDatabaseOwnsTheUniquenessRules::test_one_owner_per_provider_identity_value"
        status: pass
      - kind: integration
        ref: "tests/schema/test_store_purchase_tokens.py#TestTheDatabaseOwnsTheUniquenessRules::test_the_same_identity_value_is_free_under_a_different_provider"
        status: pass
    human_judgment: false
  - id: D6
    description: "core.store_purchase_tokens keeps its documented PK-less shape — nothing in this phase added a PRIMARY KEY to satisfy the mapper (T-37-12)"
    verification:
      - kind: integration
        ref: "tests/schema/test_store_purchase_tokens.py#TestTheTableStillHasNoPrimaryKey::test_zero_primary_key_constraints"
        status: pass
      - kind: other
        ref: "grep -n 'PRIMARY KEY' migrations/20260818_01_initial-release.sql | grep -i store_purchase → no match"
        status: pass
    human_judgment: false
  - id: D7
    description: "The D-16 subscription-layer guard still guards at full strength, satisfied by naming rather than amendment (T-37-15)"
    verification:
      - kind: unit
        ref: ".venv/bin/pytest -q tests/unit/test_users.py (12 passed)"
        status: pass
      - kind: other
        ref: "git diff --exit-code tests/unit/test_users.py → clean"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-08-22
status: complete
---

# Phase 37 Plan 04: Purchase-attribution model layer Summary

**`PurchaseProvider` + `StorePurchaseToken` over the deliberately PK-less `core.store_purchase_tokens`, with RESEARCH assumption A2 closed-CONFIRMED by a committed two-provider round-trip against PostgreSQL 17.11.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-08-22T23:28Z
- **Completed:** 2026-08-22T23:41Z
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- **A2 is settled by execution, not inference — CONFIRMED.** Two `StorePurchaseToken` rows for one `user_id` (one `apple`, one `google_play`) flush and **commit** through the mapped class against a table with no database primary key, and both `identity_value`s round-trip distinct on re-read from a fresh session. The Core-`insert()`-against-a-`Table` fallback is **not** needed; 37-07 writes its consuming transaction through the mapped class as planned.
- CREATE-03's missing model layer exists: `PurchaseProvider` (exactly `apple`, `google_play`) and `StorePurchaseToken` (exactly `user_id`, `provider`, `identity_value`, `created_at` — no surrogate key), both exported from `nativespeaker.api.models`.
- Both database UNIQUE rules are proven to fire, discriminated by **live** constraint name read from `pg_constraint` rather than hardcoded or parsed out of the message.
- The D-16 guard in `tests/unit/test_users.py` passes **unedited** — the naming collision was routed around, not weakened.

## Task Commits

1. **Task 1: PurchaseProvider enum and the StorePurchaseToken model** (TDD)
   - RED — `3edc170` (test)
   - GREEN — `540d864` (feat)
   - No refactor commit: the GREEN implementation needed no cleanup.
2. **Task 2: Prove A2 end-to-end against the real database** — `1ee7fc4` (test)

## Files Created/Modified

- `src/nativespeaker/api/models/purchase_tokens.py` (new) — `PurchaseProvider`, the module-internal `PurchaseProviderType`, and `StorePurchaseToken`.
- `src/nativespeaker/api/models/__init__.py` — two names added to the alphabetized `__all__` and one module-grouped import block entry.
- `tests/schema/test_store_purchase_tokens.py` (new) — the A2 proof and both UNIQUE rules, against real PostgreSQL.
- `tests/unit/test_models.py` — `TestPurchaseProviderEnum` and `TestStorePurchaseTokenMapping`, reading the mapped shape off `__table__`.

## A2: CLOSED — CONFIRMED

**Claim:** SQLAlchemy accepts an ORM-level composite primary key on a table whose database definition has none, and will `INSERT` correctly.

**Observed, against PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2), scratch database `ns_schema_test` with `migrations/` freshly applied:**

| Half of the claim | Result | Evidence |
|---|---|---|
| Mapper configures at import | PASS — no "could not assemble any primary key columns" | `tests/unit/test_models.py::TestStorePurchaseTokenMapping::test_the_models_package_imports`; full unit suite 970 passed |
| Two rows for one `user_id` across both providers flush + COMMIT | PASS | `test_both_providers_commit_for_one_user_and_round_trip` |
| Rows re-read distinct after commit (not one overwriting the other, not the identity map answering) | PASS — 2 distinct `identity_value`s | same case + `test_a_committed_token_is_visible_to_a_fresh_session` |
| Table still has zero `PRIMARY KEY` constraints | PASS — `count(*) = 0` in `pg_constraint` where `contype = 'p'` | `TestTheTableStillHasNoPrimaryKey` |

**Consequence for the rest of the phase:** 37-07 may write the create transaction as ORM `session.add(StorePurchaseToken(...))`. No fallback shape is required, and no `PRIMARY KEY` was or may be added to the migration.

## Live constraint names (for downstream constraint-name discrimination)

Read from `pg_constraint` on `core.store_purchase_tokens`. PostgreSQL generated these implicitly — the migration names neither constraint, so a future explicit name in the migration would change them. Downstream code should look them up or match the pattern rather than hardcoding, exactly as this test module does.

| Rule | Constraint name | Type |
|---|---|---|
| `UNIQUE (user_id, provider)` | `store_purchase_tokens_user_id_provider_key` | `u` |
| `UNIQUE (provider, identity_value)` | `store_purchase_tokens_provider_identity_value_key` | `u` |
| `user_id` FK to `core.users` | `store_purchase_tokens_user_id_fkey` | `f` |
| PRIMARY KEY | *(none — zero rows of `contype = 'p'`)* | — |

## Decisions Made

- **The Python/database name divergence is deliberate and must not be "fixed" in either direction.** The Python class is `PurchaseProvider` in `models/purchase_tokens.py`; the PostgreSQL type it binds to is and remains `core.subscription_provider`, consumed today by three other tables. This phase migrates nothing. The binding is held together **solely** by `Enum(PurchaseProvider, name='subscription_provider', schema='core')`. Drop `name=` and SQLAlchemy derives the type name from the class, silently emitting a *second* enum type at DDL time — nothing fails at import, and the mismatch first surfaces on a real INSERT (T-37-14). A comment on that line says so; the mapping test asserts `.name == 'subscription_provider'` and `.schema == 'core'`.
- **The D-16 guard collision was resolved by naming, not by amendment.** `tests/unit/test_users.py::TestSubscriptionModelLayerIsGone` forbids `models/subscriptions.py`, every name in `REMOVED_SYMBOLS`, and any `models.__all__` entry containing `Subscription`/`Usage`. RESEARCH's Code Example 7 used exactly those forbidden identifiers. This plan's names clear all three predicates; the guard file is byte-identical to its pre-plan state (`git diff --exit-code` clean) and neither frozenset was touched (T-37-15).
- **`tests/schema/test_store_purchase_tokens.py` is the one documented exception to the package's no-application-imports rule** (`tests/schema/conftest.py:45`, D-13). A2 is specifically a claim about the SQLAlchemy mapper, and this package's `conn` fixture is asyncpg, so the module builds its own async engine from `_schema_db_uri` (translating the `postgres://` prefix to `postgresql+asyncpg://`) and disposes it in a `finally`. Its module docstring states this and that **no other module in the package may follow**. It also **commits** rather than rolling back — A2 is a claim about a committed INSERT — and cleans up by deleting its `core.users` rows in a `finally`, relying on the FK's `ON DELETE CASCADE`. `test_grant_locks.py` is the package's other committing module, for the same kind of reason.
- **No `unique=True` on `identity_value`, no `default_factory` anywhere** — the database's rule is the composite `UNIQUE (provider, identity_value)`, and the creating transaction owns both the clock (35 D-02's single `evaluated_at`) and the RNG (a fresh `uuid4()` per row). Both absences are asserted by comment-stripped greps and by schema-test case 3's control (`test_the_same_identity_value_is_free_under_a_different_provider`), which shows the same value is free under a different provider.

## Deviations from Plan

None — plan executed exactly as written.

The only unplanned step was environment provisioning: the worktree ships without `.venv` or `.env` (both gitignored), so `uv sync --frozen` was run against the committed `uv.lock` and `.env` was copied from the main checkout. No dependency was added, `uv.lock` and `pyproject.toml` are unmodified, and neither artifact is tracked.

## Issues Encountered

- **One deprecation warning, fixed before commit.** The fixture teardown initially deleted its rows via `session.execute(delete(User)...)`, which SQLModel deprecates in favour of `exec()` — and `exec()` takes a select, not a delete. Teardown now issues a raw `text()` DELETE on its own engine connection, which is warning-free and has no reason to care about the ORM path. `-m schema` is clean of warnings from this module.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or trust-boundary schema change beyond what the plan's `<threat_model>` already registered. All five mitigations (T-37-11 through T-37-15) are implemented and each has a passing assertion.

## Verification

| Gate | Result |
|---|---|
| `.venv/bin/pytest -q` | 970 passed, 310 deselected (baseline was 963 — 7 added) |
| `.venv/bin/pytest -q -m schema` | 96 passed, 1184 deselected (baseline was 89 — 7 added) |
| `.venv/bin/pytest -q tests/unit/test_users.py` | 12 passed |
| `git diff --exit-code tests/unit/test_users.py` | clean |
| `.venv/bin/ruff check` on all four files | All checks passed |
| `sed 's/#.*//' … \| grep -c "unique=True"` | 0 |
| `sed 's/#.*//' … \| grep -c "default_factory"` | 0 |
| `grep -n "PRIMARY KEY" migrations/… \| grep -i store_purchase` | no match |
| Plan's inline mapper assertion script | `ok` |

## Next Phase Readiness

- **37-07 (the phase tracer) is unblocked on its highest-risk dependency.** A2 is confirmed; the create transaction inserts `StorePurchaseToken` rows through the mapped class. It must supply `created_at` from the request's single captured `RequestContext.evaluated_at` and `identity_value` from a fresh `uuid4()` per row — the model supplies neither by design.
- Downstream conflict handling (37-07's savepoint classification, per RESEARCH Pattern 3 / Pitfall 5) can discriminate this table's two rules by the constraint names recorded above; the asyncpg-cause walk in `_asyncpg_cause` is the reusable idiom.
- Nothing here is blocked or deferred.

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-22*
