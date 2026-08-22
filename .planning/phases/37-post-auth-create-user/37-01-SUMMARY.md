---
phase: 37-post-auth-create-user
plan: 01
subsystem: database
tags: [postgresql, migration, sqlmodel, check-constraint, auth-challenges, pogo]

# Dependency graph
requires:
  - phase: 34-schema
    provides: the single initial migration and the core.auth_challenges DDL with its three CHECKs
  - phase: 35-foundation
    provides: ChallengeStore, the AuthChallenge model, and the HMAC keyring the store binds through
provides:
  - core.auth_challenges with no operation_variant column, in the file and in the live database
  - an operation-membership Ruling-9.8 CHECK admitting exactly the four challenge-bearing operations
  - ChallengeStore.issue(session, *, operation, identity, now) — the five-parameter signature every later 37 plan calls
  - a recorded resolution of the D-13-vs-SCHEMA-01 mechanism conflict, upholding SCHEMA-01
affects: [37-02, 37-06, 37-07, 37-08, 40-upgrade-anonymous, 41-claim-anonymous-grant, 42-claim-registered-grant]

actuals:
  tokens: 40500
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Destructive v2.0 schema changes edit the single initial migration in place and re-apply the disposable database — never add an incremental file"
    - "A schema change is proven applied by querying information_schema, never by re-reading the migration file"

key-files:
  created: []
  modified:
    - migrations/20260818_01_initial-release.sql
    - src/nativespeaker/api/models/auth.py
    - src/nativespeaker/api/auth/challenges.py
    - tests/unit/test_challenge_ids.py
    - tests/e2e/test_challenge_store.py
    - tests/schema/test_constraints.py
    - .planning/phases/37-post-auth-create-user/37-CONTEXT.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "37-01 Task 1 resolved as option-a: the initial migration is edited in place and the dev/test database dropped and re-applied. D-13's literal 'new migration' wording loses to shipped requirement SCHEMA-01, which has a live test enforcing it; recorded as a flagged conflict in 37-CONTEXT.md rather than resolved silently"
  - "The four-arm Ruling-9.8 CHECK collapses to a bare operation-membership test — with the variant column gone there is nothing left for the arms to constrain, and a membership CHECK is the weakest form that still refuses the three challenge-free operations"
  - "Phase 40 loses its database-level provider binding (upgrade_anonymous_to_registered was pinned to operation_variant IN ('google','apple')). Flagged forward in the migration comment, in 37-CONTEXT.md, and here; Phase 37 does not design the replacement"
  - "CREATE-02 left unchecked — this plan only removes a column; the requirement is also claimed by plans 37-02/06/07/08 and is completed by them, not here (same treatment as 36-01/REBIND-05)"
  - "The R9 rejection case was widened from restore_subscription alone to all three challenge-free operations: a membership CHECK written too loosely is the new failure mode, and one case would not catch it"

patterns-established:
  - "Schema-test pairing for a membership CHECK: one parametrized rejection case over every excluded enum member, one parametrized acceptance case over every admitted member — the pair is what pins the boundary"
  - "Flagged conflicts are recorded in both directions: the decision doc gets the resolution, and the requirement it upholds gets a back-reference"

requirements-completed: []

coverage:
  - id: D1
    description: "operation_variant is gone from the schema file, the AuthChallenge model, and ChallengeStore.issue's signature"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "python -c \"inspect.signature(ChallengeStore.issue).parameters\" == ['self','session','operation','identity','now']"
        status: pass
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py (whole module — 950 passed in the default suite)"
        status: pass
      - kind: other
        ref: "grep -rn operation_variant src/ migrations/ tests/ | grep -v comment lines => 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "The live nativespeaker database carries the new schema — the column is gone from the running server, not just the file"
    verification:
      - kind: integration
        ref: ".venv/bin/pogo rollback && .venv/bin/pogo apply; then information_schema.columns count for core.auth_challenges.operation_variant == 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "The rewritten Ruling-9.8 CHECK admits all four challenge-bearing operations (including Phase 40's upgrade_anonymous_to_registered) and refuses all three challenge-free ones"
    verification:
      - kind: integration
        ref: "tests/schema/test_constraints.py#test_challenge_for_every_challenge_bearing_operation_accepted"
        status: pass
      - kind: integration
        ref: "tests/schema/test_constraints.py#test_challenge_for_a_challenge_free_operation_rejected"
        status: pass
    human_judgment: false
  - id: D4
    description: "SCHEMA-01 survives the destructive change unamended — migrations/ still holds exactly one .sql file"
    verification:
      - kind: integration
        ref: "tests/schema/test_apply_rollback.py#test_exactly_one_sql_file (unmodified, green)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Phase 40's provider-binding handoff is surfaced to the roadmap as an open design gap"
    verification: []
    human_judgment: true
    rationale: "A forward handoff is only discharged when the roadmap owner accepts it and Phase 40 plans a replacement binding. No test can assert that a future phase has been told."

duration: ~20min
completed: 2026-08-22
status: complete
---

# Phase 37 Plan 01: Remove operation_variant Summary

**`core.auth_challenges.operation_variant` deleted outright — column, four-arm Ruling-9.8 CHECK, model field, and `ChallengeStore.issue()` parameter — with the CHECK rewritten as an operation-membership test that still admits Phase 40's rows, applied to the live database and green across 1,252 tests.**

## Performance

- **Duration:** ~20 min of executor time (excludes the wait at the Task 1 human decision gate)
- **Completed:** 2026-08-22T23:16:52Z
- **Tasks:** 3
- **Files modified:** 8 (3 source/migration, 3 test, 2 planning)

## Accomplishments

- Resolved the plan's blocking one-way decision in favor of the shipped requirement over the newer phase decision, and recorded the conflict in both documents rather than letting the winner erase the loser.
- Removed the column from the DDL, the model, and the store, leaving the lifecycle CHECK and the binding CHECK byte-identical — the diff touches exactly two hunks of the migration.
- Applied the change to the real `nativespeaker` database via `pogo rollback` + `pogo apply` and proved it against `information_schema`, so no unit test could pass against a stale schema.
- Replaced the deleted variant-partition test with a stronger pair: every challenge-free operation is refused, and every challenge-bearing operation inserts.

## Task Commits

1. **Task 1: Decide the migration mechanism (checkpoint:decision)** — `a7b4f06` (docs)
2. **Task 2: Remove operation_variant from schema, model, store** — `cf6b44f` (refactor)
3. **Task 3: Apply to the live database and repair test fallout** — `74f7196` (test)

## Files Created/Modified

- `migrations/20260818_01_initial-release.sql` — dropped the `operation_variant core.identity_provider` declaration; replaced the four-arm CHECK with the membership CHECK; rewrote the Ruling-9.8 comment and added the D-12/D-13 rationale plus the Phase 40 handoff note
- `src/nativespeaker/api/models/auth.py` — deleted `AuthChallenge.operation_variant`; docstring now names the operation-membership rule. `IdentityProvider`/`IdentityProviderType` imports **kept** — `AuthEvent.actor_provider` still uses both
- `src/nativespeaker/api/auth/challenges.py` — `issue()` is now `(session, *, operation, identity, now)`; dropped the unused `IdentityProvider` import; module docstring now says a challenge binds an operation and one identity, and that the store performs no variant comparison at all
- `tests/unit/test_challenge_ids.py` — `CHALLENGE_BEARING` collapsed from seven `(operation, variant)` pairs to the four operations; variant argument dropped from `issue_row` and eight `AuthChallenge(...)` constructions; the `row.operation_variant is None` assertion deleted
- `tests/e2e/test_challenge_store.py` — variant parameter dropped from the `issue` helper
- `tests/schema/test_constraints.py` — column removed from `_INSERT_CHALLENGE` and `_insert_challenge`; the create-user-without-variant case deleted; two parametrized replacement cases added
- `.planning/phases/37-post-auth-create-user/37-CONTEXT.md` — D-13 gains the flagged-conflict resolution block
- `.planning/REQUIREMENTS.md` — SCHEMA-01 gains a back-reference recording that it was upheld against D-13

## The rewritten CHECK

Verbatim, as it now stands in `migrations/20260818_01_initial-release.sql`:

```sql
    CHECK (
        operation IN (
            'create_user',
            'upgrade_anonymous_to_registered',
            'claim_anonymous_grant',
            'claim_registered_grant'
        )
    ),
```

It remains anonymous in the DDL (option-a needed no name to drop it by). The lifecycle CHECK above it and the binding CHECK below it are unchanged.

## Decisions Made

**Task 1 selected option-a — edit the initial migration in place.** The user chose it at the gate; the reasoning recorded in `37-CONTEXT.md` is that SCHEMA-01 is a locked, shipped requirement with `test_exactly_one_sql_file` enforcing it live, while the only thing a second migration file buys — an audit trail of a schema change — has no audience in a pre-launch repo with no deployed database and zero rows. The accepted cost is that a reviewer diffing the migration sees a schema shape that never existed on any machine; the flagged-conflict block is what discharges that confusion.

**CREATE-02 was deliberately left unchecked.** The plan's frontmatter claims it, but so do plans 37-02, 37-06, 37-07 and 37-08, and nothing in this plan implements prepare/completion mode partitioning — it removes a column those plans would otherwise have to write around. Marking it complete here would make the traceability table lie. Same treatment as 36-01's REBIND-05.

## Deviations from Plan

Three, all within Rules 1–3 and none affecting scope.

**1. [Rule 2 — Missing Critical] Widened the challenge-free rejection case from one operation to three**
- **Found during:** Task 3
- **Issue:** The plan asked for a case proving `restore_subscription` is still refused, and noted the existing R9 case might already cover it. But the CHECK changed shape: the old four-arm form could only fail by admitting a wrong variant, whereas the new membership form's realistic failure is being written too loosely (an enum-wide CHECK, or none) — which would admit `sign_out_all` and `sync` while a `restore_subscription`-only test stayed green. The plan's own `must_haves` truth names all three operations.
- **Fix:** Parametrized `test_challenge_for_a_challenge_free_operation_rejected` over `restore_subscription`, `sign_out_all`, `sync`.
- **Verification:** 3 cases pass under `-m schema`.
- **Committed in:** `74f7196`

**2. [Rule 2 — Missing Critical] Made the acceptance case cover all four challenge-bearing operations, not only Phase 40's**
- **Found during:** Task 3
- **Issue:** The plan asked for one case proving `upgrade_anonymous_to_registered` still inserts. A single-operation acceptance test paired with a three-operation rejection test leaves the boundary half-pinned — three admitted operations would go unasserted.
- **Fix:** Parametrized `test_challenge_for_every_challenge_bearing_operation_accepted` over all four. Phase 40's case is called out in the docstring as the load-bearing one.
- **Verification:** 4 cases pass under `-m schema`.
- **Committed in:** `74f7196`

**3. [Rule 3 — Blocking] Reworded a test docstring to satisfy the plan's own contradictory greps**
- **Found during:** Task 3
- **Issue:** The plan's `success_criteria` permit `operation_variant` in `tests/` "as narration", but its `acceptance_criteria` grep (`grep -v '^\s*--'`) only strips SQL comments and would have counted a Python docstring mention as a failure.
- **Fix:** Rephrased the new test's docstring to "a provider-variant arm (`IN ('google','apple')`)" — the forensic meaning survives without the literal identifier, so both readings pass.
- **Verification:** `grep -rn operation_variant tests/ src/ migrations/` filtered of comment lines returns 0.
- **Committed in:** `74f7196`

---

**Total deviations:** 3 auto-fixed (2 missing critical, 1 blocking)
**Impact on plan:** All three strengthen or disambiguate verification. No scope creep — no production behavior changed beyond what the plan specified.

## Issues Encountered

None. The precondition (PostgreSQL 17.11 reachable, `nativespeaker` present) held on the first read-only check, the database had zero rows as RESEARCH predicted, and `pogo rollback`/`pogo apply` ran clean and silent.

## Verification

| Gate | Result |
|---|---|
| `.venv/bin/pytest -q` | 950 passed, 302 deselected |
| `.venv/bin/pytest -q -m schema` | 89 passed |
| `.venv/bin/pytest -q -m e2e` | 213 passed |
| `.venv/bin/ruff check src/ tests/` | All checks passed |
| `information_schema` column count | 0 |
| `test_exactly_one_sql_file` | green, **unmodified** |

## Known Stubs

None.

## Threat Flags

None. T-37-01's mitigation is discharged by `test_challenge_for_a_challenge_free_operation_rejected` (asserted refusal, not assumed) and by the untouched lifecycle and binding CHECKs; T-37-03's by the `information_schema` proof in Task 3. No package was installed.

## User Setup Required

None — no external service configuration required. The developer's local `postgres:17` container was rolled back and re-applied in place; any other machine holding this database must run `.venv/bin/pogo rollback && .venv/bin/pogo apply` to pick up the change, since the migration id is unchanged and pogo will otherwise consider it already applied.

## Next Phase Readiness

- `ChallengeStore.issue()`'s five-parameter signature is now the one plans 37-02 through 37-10 must call. Any plan drafted against the six-parameter form needs its call sites read again.
- **Open handoff for Phase 40 (`POST /auth/upgrade-anonymous`):** the database no longer binds a target provider to an upgrade challenge. Phase 40 must supply its own mechanism — most likely at completion, from the same Firebase Admin `providerData` lookup D-12 introduced — and the CHECK was deliberately written so its rows insert in the meantime. This is a design gap, not a defect, and it is explicitly not Phase 37's to close.

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-22*

## Self-Check: PASSED

All modified artifacts exist on disk and all three task commits are reachable in `git log`.
