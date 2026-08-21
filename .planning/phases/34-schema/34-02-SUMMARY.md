---
phase: 34-schema
plan: 02
subsystem: database-schema
tags: [postgresql, pogo-migrate, ddl, auth, entitlements, tracer]
status: complete
requires: [34-01]
provides:
  - "migrations/20260818_01_initial-release.sql — the complete v2.0 auth schema in one from-empty apply"
  - "A live PostgreSQL 17.11 database holding the applied v2.0 schema (2 schemas, 11 enums, 17 tables, 54 indexes)"
  - "The four planning documents consistently naming the renamed migration (CONFLICT-1 closed)"
affects: [34-03, 34-04, 35, 36]
tech_stack:
  added: []
  patterns:
    - "One initial migration, renamed and replaced — the filename stem is pogo's tracked migration id, so a rename fails loudly where an in-id rewrite would silently skip"
    - "Rollback as two DROP SCHEMA … CASCADE statements rather than a reverse-order object list, so it cannot drift out of sync with the apply body"
    - "Declarative-only constraint enforcement: circular deferrable FKs and STORED generated columns instead of triggers or application checks"
key_files:
  created:
    - migrations/20260818_01_initial-release.sql
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/PROJECT.md
    - .planning/STATE.md
  deleted:
    - migrations/20260322_01_initial-release.sql
decisions:
  - "Task 1 one-way door resolved as `one-file`: the v2.0 schema ships as ONE migration written from scratch against an empty database, overriding 00-schema.md §1's six-file sequence"
  - "Wrote the seven DIRECTIVE-6 survivor objects by hand — §3–§7 is a delta against a baseline that does not exist at apply time, and copying the baseline core.users would have reintroduced jwt_sub while still letting the apply succeed"
  - "Took core.users from the §2 TARGET-shape table (00-schema.md:84-94), never from the baseline CREATE TABLE"
  - "Placed CREATE SCHEMA core / CREATE SCHEMA audit in an explicit unnumbered preamble labelled as such in the file (DIRECTIVE-5, closing CONFLICT-4)"
  - "Left every spec-unnamed CHECK constraint unnamed — auto-generated names are positional and order-fragile (P-8), and naming them would deviate from the verbatim DDL D-07 mandates"
metrics:
  duration: "~25 min"
  completed: 2026-08-21
actuals:
  tokens: 11622
  tasks: 3
  commits: 2
---

# Phase 34 Plan 02: The v2.0 Schema Applies From Empty — Summary

**`migrations/20260818_01_initial-release.sql` (699 lines) is now the only migration in the
repository, and it demonstrably applies to an empty PostgreSQL 17.11, rolls back to nothing, and
re-applies — every cycle actually executed against the live database from plan 34-01, not asserted.**

## Task 1 — the one-way door: `one-file`

**Selected option: `one-file`.** The v2.0 schema is delivered as ONE migration file written from
scratch against an empty database, deleting `20260322_01_initial-release.sql`, rather than as the
six incremental files `00-schema.md §1` specifies.

**Basis for the selection.** Auto mode was active and the developer twice instructed "resume". The
decision was not new: it is recorded in three independent places — `.planning/PROJECT.md`'s Key
Decisions table, `34-CONTEXT.md` D-01, and the v2.0 "never add incremental migrations" constraint —
with Phase 27 of v1.6 as precedent on this same file. The `six-files` alternative is moreover
**infeasible**, not merely less preferred: it requires a v1.6 baseline database to migrate *from*,
and plan 34-01 verified that `nativespeaker` was created empty on a fresh container. No such
baseline exists anywhere — not in git, not in any database. The developer was shown this reasoning
explicitly before this executor was dispatched.

The gate existed because D-01 is rated one-way, not because the decision was in doubt.
`00-schema.md §1`'s statement ordering and prohibition list still bind and were followed exactly
(CONFLICT-2, already resolved).

## Task 2 — the tracer

### The file

| Property | Value |
|---|---|
| Path | `migrations/20260818_01_initial-release.sql` |
| Lines | **699** (plan floor: 400) |
| Line 1 | `-- v2.0 authentication and entitlements schema` (D-04 rewrite) |
| Line 2 | exactly `-- depends:` — empty, root migration (D-03) |
| `-- depends:` occurrences in metadata | exactly 1 |
| Apply body | unnumbered schema preamble + 5 banner-commented sections (D-06, DIRECTIVE-5) |
| Rollback body | exactly 2 statements: `DROP SCHEMA IF EXISTS audit CASCADE;` then `… core CASCADE;` (D-05) |
| `migrations/*.sql` count | 1 |
| Old file | `git rm`'d — staged `D`, in the same commit (P-3) |

### The apply / rollback / re-apply / no-op cycle — all four actually run

Observed state between each step, not inferred from a chained `&&`:

| Step | Command output | `core`+`audit` namespaces | `_pogo_migration` rows | `core` tables | `audit` tables |
|---|---|---|---|---|---|
| after first apply | *(silent, exit 0)* | 2 | 1 | 15 | 2 |
| `pogo rollback --count 1` | `Rolling back 20260818_01_initial-release` | **0** | **0** | 0 | 0 |
| `pogo apply` | `Applying 20260818_01_initial-release` | 2 | 1 | 15 | 2 |
| `pogo apply` again | *(no output; 0 `Applying` lines)* | 2 | 1 | 15 | 2 |

The idempotent-skip path is proven by output shape, not just exit code: with `-vv` the real apply
prints `Applying 20260818_01_initial-release` and the fourth apply prints nothing at all.

The plan's `<automated>` block was then run **verbatim, unmodified**, and again after the task-2
commit as the tracer feedback gate. Both runs printed:

```
OK apply/rollback/re-apply clean; 11 enums, 15 core tables, 2 audit tables, 7 user columns
```

### The DIRECTIVE-6 survivors — the phase's highest-probability failure, checked explicitly

`00-schema.md §3–§7` is a delta against a baseline that does not exist at apply time. All seven
objects its inventory requires but its DDL never creates were written by hand:

| # | Object | Source used |
|---|---|---|
| 1 | `CREATE SCHEMA core` | preamble |
| 2 | `CREATE SCHEMA audit` | preamble |
| 3 | enum `core.chat_role` | deleted baseline, line 8 |
| 4 | enum `core.subscription_status` | deleted baseline, line 11 |
| 5 | table `core.users` | **`00-schema.md:84-94` §2 TARGET shape** — NOT the baseline `CREATE TABLE` |
| 6 | tables `core.chats`, `core.messages` | deleted baseline, lines 25-31 / 35-41 |
| 7 | index `ix_chats_user_id` | deleted baseline, line 33 |

The `core.users` trap was verified closed rather than assumed. `information_schema.columns` reports
exactly the seven target columns in order — `id, email, display_name, registered_at, active,
created_at, updated_at` — with `email` **nullable**, and **no** `jwt_sub`, **no**
`subscription_plan`, **no** `name`. Had the baseline shape been copied, the apply would still have
succeeded while silently violating SCHEMA-07; that is precisely why it was asserted directly.

### Acceptance criteria — every one verified against the applied database

All 48 introspection assertions passed. Highlights:

- **Object inventory (§10):** 11 `core` enums, 15 `core` tables, 2 `audit` tables, 7 `core.users` columns.
- **Enum label counts:** `access_grant_source` **4** (no `promo`, §9.1); `auth_event_result` **44**
  (no `invalid_attestation_or_integrity_proof`, no `cloudflare_lookup_unavailable`, §9.7);
  `auth_operation` 7; `subscription_provider` 2; and the remaining seven all exact.
- **SCHEMA-07 deletions:** `to_regtype('core.subscription_plan')`, `to_regclass('core.usage_monthly')`
  and `to_regclass('core.subscription_events')` all NULL; no `(core, users, jwt_sub)` row.
- **Baseline indexes correctly absent:** `ix_users_jwt_sub`, `ix_subscriptions_external_id`,
  `ix_subscriptions_user_provider_active`, `ix_usage_monthly_user_month`.
  `ix_subscription_events_subscription_id` **is** present and lives in `audit` (00-schema.md:339).
- **Seeds:** `SELECT count(*) FROM core.access_tiers` → **0** (00-schema.md:249 — Phase 00 seeds no tiers).
- **§1 prohibitions:** 0 user triggers, 0 views, 0 materialized views in `core`/`audit`; no extension
  beyond `plpgsql`.
- **The circular pair:** both back-pointing FKs on `core.access_grants` exist as
  `DEFERRABLE INITIALLY DEFERRED`, alongside the two deferred subscription FKs; the anti-abuse
  composite FK carries `ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED`.
- **6 STORED generated columns** across `core.subscriptions`, `core.access_grants` and
  `core.access_grants_anti_abuse`.

The five `§10` unique indexes and two non-unique partial indexes exist with the right uniqueness and
predicates. Captured predicate text (default `search_path`; see P-5 — 34-03 must pin it):

| Index | unique | `pg_get_expr(indpred, indrelid)` |
|---|---|---|
| `ix_external_identities_provider_account` | yes | `(provider_uid IS NOT NULL)` |
| `ix_subscriptions_provider_external_id` | yes | *(none)* |
| `ix_access_grants_one_per_subscription` | yes | `((source = 'subscription'::core.access_grant_source) AND (subscription_id IS NOT NULL) AND (status = 'active'::core.access_grant_status))` |
| `ix_access_grants_one_active_per_user` | yes | `(status = 'active'::core.access_grant_status)` |
| `ix_access_grants_one_free_grant_per_user_source` | yes | `(source = ANY (ARRAY['anonymous_device_grant'::core.access_grant_source, 'registered_account_grant'::core.access_grant_source]))` — **no status predicate** |
| `ix_access_grants_subscription` | **no** | `(subscription_id IS NOT NULL)` |
| `ix_access_grants_anti_abuse_idp_account_hash` | **no** | `(idp_account_hash IS NOT NULL)` |

### Spec adaptations beyond the seven documented survivors

**None.** Every table, column, enum label and its order, CHECK, foreign key, delete behavior and
index outside the seven survivors is transcribed verbatim from `00-schema.md §3–§8` per D-07.
Nothing had to be adapted for the from-empty context, so there is no spec conflict to flag on this
axis. The only additions to the file's *text* are comments: banner dividers, `§9` ruling citations at
the points where a more natural-looking alternative was deliberately rejected, and the D-10 REVOKE
notice — all of which `pogo_core/migration.py:22` strips or PostgreSQL handles natively.

### PostgreSQL 17.11 vs RESEARCH.md's 16.2 findings

RESEARCH.md's constants were captured on **16.2**; the real target is **17.11 (Debian
17.11-1.pgdg13+2)**. **No divergence was observed.** Every 16.2-derived figure this plan could check
reproduced exactly on 17.11:

| Constant | RESEARCH.md (16.2) | Observed (17.11) |
|---|---|---|
| Total indexes across `core` + `audit` | 54 | **54** |
| Internal (FK) triggers | 104 | **104** |
| User triggers / views / matviews | 0 / 0 / 0 | **0 / 0 / 0** |
| Tables recreated after rollback + re-apply | 17 | **17** |
| Predicate rendering (`= ANY (ARRAY[…])` with explicit `::type` casts) | as documented | identical |

This is corroborating evidence for RESEARCH.md assumption **A1**, not its closure. A1 closes when
plan 34-03 re-captures the full introspection constant set (Code Example 4) against this server, as
plan 34-01's summary states. 34-03 should still re-capture rather than copy — but it now has a
strong prior that the 16.2 numbers hold.

## Task 3 — CONFLICT-1 closed across four documents

All six locations amended; the verification script printed `OK all ten document assertions hold`.

| # | Location | Change |
|---|---|---|
| 1 | `.planning/REQUIREMENTS.md` SCHEMA-01 | names `20260818_01_initial-release.sql`, reads as replace-the-prior-migration; trailing "no incremental migration files are added" kept |
| 2 | `.planning/ROADMAP.md` Phase 34 `**Goal:**` | names the new file and states it replaces the deleted `20260322_01_initial-release.sql`; single changed line |
| 3 | `.planning/PROJECT.md` Key Decisions row | names the new file, states the old is deleted, and appends DIRECTIVE-1's reason (the stem is pogo's tracked id, so reusing it is silently skipped where a new id fails loudly); status marker untouched |
| 4 | `.planning/PROJECT.md` `## Constraints` bullet | mechanism framing updated; "pre-launch DB with no data" and "never add incremental migrations during v2.0" both kept verbatim |
| 5 | `.planning/REQUIREMENTS.md` global-exclusions row | right-hand cell only; the exclusion itself unchanged |
| 6 | `.planning/STATE.md` v2.0 bullet | mechanism framing updated; "never add incremental migrations during v2.0" and `(overrides 00-schema.md §1/§2)` both kept |

Plus the D-11 bullet: `.planning/PROJECT.md`'s "Known areas for future work" gained a fifth entry
naming `REVOKE DELETE ON core.external_identities`.

`git diff --stat` touched exactly those four files and no others under `.planning/`
(PROJECT.md +5/−2, REQUIREMENTS.md +2/−2, ROADMAP.md +1/−1, STATE.md +1/−1).

**The four legitimate non-migration uses of "in place" survive untouched**, though their line numbers
have drifted from the plan's citation — recorded here so 34-03/34-04 do not chase phantoms:

| Plan cited | Actual | Content |
|---|---|---|
| `PROJECT.md:180` | `PROJECT.md:181` | JWT-skeleton Key Decisions row (shifted by the new D-11 bullet) |
| `REQUIREMENTS.md:70` | `REQUIREMENTS.md:70` | UPGRADE-01 identity-provider flip |
| `ROADMAP.md:198`, `:202` | `ROADMAP.md:215`, `:220` | Phase 40 identity-provider flip |

## Deviations from Plan

**None affecting behavior.** No auto-fix was needed: no bug, no missing critical functionality, and
no blocking issue arose. Two observations worth recording, neither of which changed what was built:

1. **`git add` on the already-`git rm`'d path failed** with `pathspec … did not match any files`.
   Expected — `git rm` had already staged the deletion. Re-staged the new file only; the commit
   correctly shows `D` for the old path and `A` for the new one. Not a deviation, just a rejected
   redundant command.
2. **Doc line numbers drifted** from the plan's citations for the four surviving "in place" uses
   (table above). The plan's content-based assertions all hold; only the coordinates moved.

## Threat Mitigations Upheld

- **T-34-02-01 / -02 / -10** (free-grant farming, entitlement double-spend, anti-abuse-free grants):
  `ix_access_grants_one_free_grant_per_user_source` exists **with no status predicate** (verified
  from `pg_get_expr`); `ix_access_grants_one_active_per_user` exists as a non-deferrable partial
  unique index; the declarative quartet — deferred FK on `anti_abuse_required_grant_id`, the
  anti-abuse primary key, the composite `(grant_id, grant_source)` FK, and the per-source CHECK —
  all present. No trigger and no application check anywhere.
- **T-34-02-03 / -04** (entitlement without payment, cross-account theft): the STORED
  `product_entitled_subscription_id` is fixed at `('active','grace_period')`; both deferred FKs from
  `core.access_grants` onto `core.subscriptions (id, user_id)` and
  `(product_entitled_subscription_id)` verified `DEFERRABLE INITIALLY DEFERRED`.
- **T-34-02-05 / -06** (audit forgery, raw-subject leakage) and **prohibition SCHEMA-06**: the
  all-or-nothing actor CHECK, the keyed `BYTEA` hash with its version column, and the seven `details`
  shape CHECKs all ship. **No plaintext credential column was added to `audit.auth_events` or
  `core.auth_challenges`** — `core.external_identities` remains the sole plaintext reservation store.
  No key-version column was added to the challenge row (§9.4); no FK on `challenge_row_id` (§8).
- **T-34-02-07** (identity-row deletion) and **D-10/D-11**: `core.external_identities.user_id` is
  `ON DELETE RESTRICT`; the role-level `REVOKE DELETE` is recorded both as a prominent comment at the
  table definition and as a PROJECT.md future-work bullet. No database role was invented.
- **T-34-02-08** (unreviewed extra object): counts asserted immediately — 11/15/2, 0 triggers,
  0 views, 0 matviews. 34-03's exact-set assertions build on this.
- **T-34-02-09** (green apply against a stale schema) and **prohibition SCHEMA-01**: the file is
  renamed, so it presents as a new unapplied id. Confirmed applied under the id
  `20260818_01_initial-release`.
- **T-34-02-11** (retired-account re-registration): `ix_external_identities_provider_account` carries
  `WHERE provider_uid IS NOT NULL` and **no state predicate**, so it covers `historical` tombstones.
- **T-34-02-SC** (supply chain): **zero packages installed.** `git diff HEAD -- pyproject.toml`
  is empty (0 lines).
- **Prohibition SCHEMA-07** (no softening to keep v1.6 code alive): nothing was retained. The unit
  suite still passes at **163 passed**, matching RESEARCH.md A6's baseline — as A6 predicts, the
  post-Phase-34 breakage is runtime, not import.

## Constraint Compliance

- `pyproject.toml` — **byte-identical to HEAD**; `git diff HEAD -- pyproject.toml` produced 0 lines.
- `docker-compose.yml` — **untouched**; still carries the developer's uncommitted `env_file: - .env`
  edit (` M`), neither committed nor reverted, exactly as found.
- `.env` — never printed, echoed, `cat`'d, or quoted. All access was via `set -a && . ./.env` into a
  subshell that emitted only counts and booleans.
- `pogo validate` — **not run** (P-9: it crashes on the working baseline and exits 0 on the crash).
- `--create-schema` — **not passed** (P-10). Confirmed harmless: no `api` schema exists, every
  statement in the file is schema-qualified, and the apply succeeded under `search_path = api`.

## Known Stubs

None. The migration is complete: no partial section, no placeholder DDL, no deferred object. The one
deliberately-absent statement is the `REVOKE DELETE ON core.external_identities`, which is D-10's
recorded decision (this repo defines no database role) rather than a stub, and is documented in two
places.

## For Plans 34-03 and 34-04

- The migration id is `20260818_01_initial-release`; `migrations/` holds exactly one `.sql`.
- The `nativespeaker` database currently holds the **applied** schema. 34-03's session fixture should
  use its own scratch database (`ns_schema_test`, whose creation plan 34-01 already exercised).
- Useful captured constants on 17.11: **54** indexes across `core`+`audit`, **104** internal triggers,
  **0** user triggers/views/matviews. Re-capture per D-19 rather than copying, but expect these.
- P-5 is live: the predicate strings above were read under the default `search_path` and render enum
  casts as `'active'::core.access_grant_status`. Pin `search_path` in the predicate test.
- 34-04's rejection cases have their declarative machinery in place and verified structurally
  (deferrable FKs, generated columns, CHECK constraints) — but **no constraint behavior was exercised
  with real rows** in this plan. That is 34-04's job and remains unproven.

## Self-Check: PASSED

- `migrations/20260818_01_initial-release.sql` — **FOUND** (699 lines, 34498 bytes).
- `migrations/20260322_01_initial-release.sql` — **CONFIRMED ABSENT**; staged `D` and present in
  `git diff --diff-filter=D HEAD~1 HEAD` for commit `e5ac00c`.
- Commit `e5ac00c` — **FOUND** in `git log`.
- Commit `6b1c511` — **FOUND** in `git log`.
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/PROJECT.md`, `.planning/STATE.md` —
  all **FOUND** and modified; task 3's verification script exits 0.
- Every number, predicate string and command output quoted above was copied from a command that
  actually ran in this session. No assertion was weakened, skipped, or relaxed to obtain a pass.
