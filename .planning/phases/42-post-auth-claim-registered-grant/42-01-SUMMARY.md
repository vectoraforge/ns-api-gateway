---
phase: 42-post-auth-claim-registered-grant
plan: 01
subsystem: schema
tags: [migration, deletion, anti-abuse, grants, d-07, d-08]
status: complete

requires:
  - "migrations/20260818_01_initial-release.sql (the single v2.0 migration)"
  - "crud/grants.py::activate_anonymous_device_grant (Phase 41's writer)"
provides:
  - "A migration that creates no receipt table, no provider-account table and no gate-consumption enum"
  - "seed_grant able to seed a free-source grant with no companion row (plan 42-02 needs this)"
  - "An anonymous claim that writes three rows instead of four"
affects:
  - "plan 42-02 (its writer edits the same function and the same test files)"
  - "plan 42-05 (the race harness whose clean_up lost a DELETE)"

tech-stack:
  added: []
  patterns:
    - "In-place edit of the one migration under SCHEMA-01, behind a checkpoint:decision"
    - "Exact-set inventory literals re-baselined by hand, never derived from the database"

key-files:
  created: []
  modified:
    - migrations/20260818_01_initial-release.sql
    - src/nativespeaker/api/tables/grants.py
    - src/nativespeaker/api/tables/__init__.py
    - src/nativespeaker/api/crud/grants.py
    - tests/schema/test_inventory.py
    - tests/schema/test_constraints.py
    - tests/schema/test_claim_race.py
    - tests/e2e/conftest.py
    - tests/e2e/test_claim_anonymous_grant.py
    - tests/unit/test_grant_sources.py

decisions:
  - "D-07 executed as written: three tables, one enum, two generated columns, two deferred FKs, one composite unique key and two indexes left the migration"
  - "core.native_claim_provider kept: external_identities.native_claim_platform still binds it and it stays the record of the device platform"
  - "D-08 held: no hash column, no key and no key version were introduced anywhere"

metrics:
  duration: "~30 min"
  completed: 2026-09-03
  tasks: 3
  commits: 2

actuals:
  tokens: 28856
  tasks: 3
  commits: 2
---

# Phase 42 Plan 01: The D-07 Schema Deletion Summary

The anti-abuse receipt table and the two provider-account tables left the single v2.0 migration
with everything only they needed, and the deletion was carried through the model layer, Phase 41's
writer and the six test files that read them.

## What Was Built

The receipt row decided nothing. Every fact on it existed elsewhere — the grant's own `source`, the
identity row's `native_claim_platform`, the identity row's `provider_uid` — and the two provider
tables were never written by any code. All three are gone.

**Removed from `migrations/20260818_01_initial-release.sql`:** `core.access_grants_anti_abuse`,
`core.provider_accounts`, `core.provider_account_gate_consumptions`, the
`core.gate_consumption_kind` enum, the generated columns `anti_abuse_required_grant_id` and
`active_registered_account_grant_id`, both deferred foreign keys that pointed back at the receipt
table, `UNIQUE (id, source)` on `core.access_grants`, and the indexes
`ix_access_grants_anti_abuse_idp_account_hash` and `ix_gate_consumptions_grant_id`.

**Kept, and checked one by one:** `core.native_claim_provider` survives because
`external_identities.native_claim_platform` binds it. Both remaining partial unique indexes over
`core.access_grants` survive verbatim with their predicates. `core.subscriptions`'s own
`UNIQUE (id, user_id)` was not collateral damage. The `-- migrate: rollback` body needed no edit —
it is two `DROP SCHEMA ... CASCADE` statements.

**In code:** `AccessGrantAntiAbuse` left `tables/grants.py` and `tables/__init__.py`.
`activate_anonymous_device_grant` stopped building the receipt row; the grant row, the usage row,
the three identity-marker assignments, the single `flush()` in its bare `try` and the
`except IntegrityError: return False` arm are byte-identical.

**Both databases carry the edited schema.** The developer's `nativespeaker` database was dropped and
re-applied by hand, going from 15 core tables to 12 and from 10 core enums to 9. The schema suite's
scratch database needed no manual step — its session fixture drops, recreates and migrates it.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Authorise the one-way migration edit and the destructive rebuild | — (checkpoint) | none |
| 2 | The deletion in the migration and in the code, both databases rebuilt | `496d8dd` | migration, `tables/grants.py`, `tables/__init__.py`, `crud/grants.py` |
| 3 | The test cascade | `29ecaf3` | the six test files |

## Verification

| Gate | Result |
|------|--------|
| `uv run pytest -q` | 952 passed, 344 deselected |
| `uv run pytest -m schema -q` | 119 passed, zero skipped |
| `uv run pytest -m e2e -q` | 225 passed, zero skipped |
| `uv run ruff check src tests` | All checks passed |
| `ls migrations/*.sql \| wc -l` | 1 |
| dev database core tables | 12, none of the three deleted names |
| inventory literals (enums, tables, indexes, predicates) | `9 12 38 6` |
| D-08 hash/key/HMAC grep over `src/` and `migrations/` | no match |
| `FREE_GRANT_SOURCES` | both members, not narrowed |

## Task 1: The Checkpoint

Task 1 was a `checkpoint:decision` gating two things: editing the one initial migration in place
(there is no reverse migration, and SCHEMA-01 forbids a second file) and dropping the developer's
local `nativespeaker` database. The developer answered **`rebuild-now`**, authorising both. The
deletion itself was already decided by D-07 and was not what the gate asked about.

Rows lost: zero by the research's count, and zero in fact — the two provider tables had no writer
anywhere in `src/`, and the receipt table had exactly one, added by Phase 41.

## Deleted Test Cases, by Node ID

Every case below is named with its disposition, so no coverage vanishes silently (T-42-01-05).

**`tests/schema/test_constraints.py` — 40 collected before, 27 after (13 deleted).**

From `TestAccessGrantConstraints`:

| Node ID | Disposition |
|---------|-------------|
| `::test_grant_free_source_without_anti_abuse_row_rejected_at_commit` | Property left with its subject. It asserted the deferred FK that required a receipt row per free grant; that FK is deleted. |
| `::test_grant_free_source_with_anti_abuse_row_passes_the_deferred_check` | Property left with its subject. It was the positive control for the case above. |

From `TestAntiAbuseEvidenceConstraints` — the whole class, 11 cases. Every one exercised the
four-arm exclusive-or CHECK or the "free sources only" partition on the deleted table. **All 11
properties left with their subject; no survivor carries any of them, because the table they
constrained no longer exists.**

`::test_grant_anti_abuse_native_ios_tuple_accepted`,
`::test_grant_anti_abuse_native_android_tuple_accepted`,
`::test_grant_anti_abuse_web_anonymous_tuple_accepted`,
`::test_grant_anti_abuse_registered_tuple_accepted`,
`::test_grant_anti_abuse_anonymous_row_without_any_evidence_rejected`,
`::test_grant_anti_abuse_native_row_carrying_idp_hash_rejected`,
`::test_grant_anti_abuse_web_anonymous_row_carrying_native_provider_rejected`,
`::test_grant_anti_abuse_registered_row_carrying_native_provider_rejected`,
`::test_grant_anti_abuse_row_for_subscription_backed_grant_rejected`,
`::test_grant_anti_abuse_row_for_manual_grant_rejected`,
`::test_grant_anti_abuse_grant_source_check_is_subsumed`.

**`tests/schema/test_claim_race.py` — 1 deleted.**

| Node ID | Disposition |
|---------|-------------|
| `TestTwoSimultaneousClaims::test_exactly_one_anti_abuse_row_carries_the_ios_provider` | Split. The receipt half left with its subject. The **device-platform half survives** in `test_the_lifetime_marker_is_set_once`, which asserts `native_claim_platform == "ios_devicecheck"` on the identity row — the surviving record of the platform (D-07, T-42-01-04). |

No test case was deleted from `tests/e2e/`, `tests/unit/` or `tests/schema/test_inventory.py`; those
files lost assertions and literals, not cases.

## Controls That Survive Untouched

The deletion removes evidence, never a guard. Each of these was checked individually after the edit:

- `ix_external_identities_provider_account` — `UNIQUE (issuer, provider, provider_uid)`, no state
  predicate. One identity row per Google or Apple account, ever.
- `UNIQUE (user_id)` on `core.external_identities` — that row ties to one user.
- `ix_access_grants_one_free_grant_per_user_source` — predicate verbatim, no status predicate, so
  expiry or revocation never reopens the lifetime slot.
- `ix_access_grants_one_active_per_user` — predicate verbatim.
- `external_identities.free_grant_consumed_at` — set once, never cleared.
- `FREE_GRANT_SOURCES` — still both members, still bound to the live index predicate.

`tests/schema/test_constraints.py`'s free-grant and active-grant unique-index cases were left
byte-identical, and are green.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The single-writer walk counted a construction site the deletion removed**

- **Found during:** Task 3, on the first `uv run pytest -q`
- **Issue:** `tests/unit/test_grant_sources.py::TestTheAnonymousDeviceGrantHasExactlyOneWriter::test_the_one_site_is_inside_the_crud_activation_writer` asserted the writer names `AccessGrantSource.anonymous_device_grant` exactly **twice** — once in `AccessGrant(source=...)` and once in the deleted `AccessGrantAntiAbuse(grant_source=...)`. Task 2 removed one, so the literal was stale.
- **Fix:** Re-baselined `== 2` to `== 1`. Assertion strength is unchanged and arguably sharper: the count now agrees exactly with `test_the_whole_tree_holds_exactly_one_construction_site`.
- **Files modified:** `tests/unit/test_grant_sources.py`
- **Commit:** `29ecaf3`
- **Note:** The plan's Task 3 action said to change nothing in this file beyond the near-miss string, and `42-RESEARCH.md` Pitfall 8 flagged only line 120. Both missed this second, load-bearing consequence.

**2. [Rule 1 - Bug] A row-count tuple literal outside the swept pattern**

- **Found during:** Task 3, on `uv run pytest -m e2e -q`
- **Issue:** `_row_counts` became a 2-tuple, and `test_a_repeat_answers_the_fresh_claim_body_writes_nothing_and_never_reaches_apple` compared the captured variable (`assert after_first == (1, 1, 1)`) rather than the call, so it escaped the call-site sweep.
- **Fix:** `(1, 1, 1)` to `(1, 1)`.
- **Files modified:** `tests/e2e/test_claim_anonymous_grant.py`
- **Commit:** `29ecaf3`

**3. [Rule 2 - Correctness] Two stale counts in comments the deletion falsified**

- **Found during:** Task 2
- **Issue:** `tables/grants.py` said "The table's **four** GENERATED ALWAYS AS STORED columns are deliberately unmapped" above `AccessGrant`; two of those four were deleted. `crud/grants.py`'s comment above the `try` said "all three rows go in it: the two FKs are deferred to commit", wrong on both counts afterwards.
- **Fix:** "four" to "two"; the `try` comment rewritten to state what is actually true (only the flush is inside, the `try` holds the one statement that can raise). The writer's docstring, which named four things written, now names three. All within the `AGENTS.md` one-line and three-line caps.
- **Files modified:** `src/nativespeaker/api/tables/grants.py`, `src/nativespeaker/api/crud/grants.py`
- **Commit:** `496d8dd`

### Acceptance Criteria That Were Wrong as Written

Two criteria in the plan could not be satisfied literally, and in both cases the criterion was the
defect, not the implementation. Neither was worked around silently.

**1. `grep -c "provider_account"` over the migration was required to return `0`.**
It returns `1`, and must. The one match is `ix_external_identities_provider_account` — the unique
index D-06 names as the control that **replaces** the deleted provider tables. Driving this
criterion to zero would have deleted the guard along with the evidence, which is exactly what this
plan's first prohibition forbids. The substantive assertions were run instead and both return `0`:
`provider_accounts` and `provider_account_gate_consumptions`.

**2. `uv run python -c "import tests.e2e.conftest ..."` fails with `ModuleNotFoundError: No module named 'unit'`.**
An environment defect, not a code one: pytest puts `tests/` on `sys.path`, a bare `python -c` does
not, and `tests/e2e/conftest.py` imports `unit.conftest`. Re-run with the same import root pytest
uses, it prints `False` as required, and the parameter list is
`[factory, user_id, tier_id, source, status, monthly_period, monthly_used, starts_at, ends_at, with_usage]`.

### Sequencing Note (not a defect)

At the end of Task 2, `uv run pytest -q` aborted with a collection error —
`tests/e2e/conftest.py` still imported `AccessGrantAntiAbuse`, which Task 2 had just deleted. Task
2's `<verify>` block demanded a green unit run, while Task 2's own action text forbade touching
`tests/` and the plan states that a red suite at the end of Task 2 is "the expected state and not a
defect". The two are in tension. The action text was followed, because Task 3 exists precisely to be
the completing half of this deletion and merging them would have destroyed the atomic split the plan
was sequenced to preserve. Commit `496d8dd` is therefore knowingly red on collection; `29ecaf3`
makes all four gates green. No third state was left behind.

## Threat Model

| Threat ID | Disposition | Outcome |
|-----------|-------------|---------|
| T-42-01-01 | mitigate | Held. All six surviving controls named and individually checked; the free-grant and active-grant constraint cases are byte-identical and green. |
| T-42-01-02 | mitigate | Held. The dev database was rebuilt and proves it by its own table list (12, none deleted). `-m e2e` is green, so no stale-schema mismatch remains. |
| T-42-01-03 | mitigate | Held. `grep -riE "idp_account_hash\|key_version\|hmac"` over `src/nativespeaker/api` and `migrations` returns no match. |
| T-42-01-04 | accept | As accepted. `core.native_claim_provider` and `external_identities.native_claim_platform` survive and are asserted by a live case. |
| T-42-01-05 | mitigate | Held. All 14 deleted cases are named above by node id with their disposition. |
| T-42-SC | mitigate | Held. No package was installed, added, moved or upgraded. |

## Known Stubs

None. No stub, TODO, FIXME or placeholder was introduced; the changed files were scanned before this
summary was written.

## Threat Flags

None. This plan removed surface and introduced none. No new endpoint, auth path, file access pattern
or trust-boundary schema change.

## For the Next Plan

- `seed_grant` no longer takes `with_anti_abuse`, so a free-source grant seeds with no companion
  row — which is what plan 42-02's registered cases need.
- `activate_anonymous_device_grant` is now the three-row model that 42-02's
  `activate_registered_account_grant` copies.
- `tests/schema/test_claim_race.py::clean_up` no longer clears a receipt table; 42-05's new race
  classes inherit that helper as it now stands.
- The four inventory literals in `tests/schema/test_inventory.py` are `9 12 38 6`. Phase 42 adds no
  further schema object, so any later movement in these numbers is a defect.

## Self-Check: PASSED

All modified files exist on disk and both task commits are present in git history.
