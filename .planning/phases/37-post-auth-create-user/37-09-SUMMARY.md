---
phase: 37-post-auth-create-user
plan: 09
subsystem: auth
tags: [savepoint, integrity-error, constraint-name, race-arbitration, schema-test, postgres, atomicity]
status: complete

requires:
  - plan: "37-07"
    provides: "create_account / resolve_existing_identity as a plain function over (session + resolved facts), and the begin_nested savepoint whose rollback arm this plan supplies"
  - plan: "37-04"
    provides: "A2 CONFIRMED (write through the mapped class), and the pg_constraint-at-test-time idiom this plan reuses for external_identities"
  - plan: "37-03"
    provides: "IDENTITY_ALREADY_LINKED, OPERATION_NOT_ALLOWED, ACCOUNT_UNAVAILABLE"
provides:
  - "RACE_CONSTRAINT_NAMES / PROVIDER_ACCOUNT_INDEX_NAME / CLIENT_CLASS_FOR_RESULT / classify_insert_conflict in auth/creation.py"
  - "The except IntegrityError arm: rollback-to-savepoint then classify, so consume + audit commit on the still-live outer transaction"
  - "blocked_user as a distinct internal result from the in-transaction re-resolution"
  - "ROADMAP criteria 3 and 4 proven against real committing PostgreSQL 17.11"
affects: [37-08, 37-10, 38, 40, 41, 42]

actuals:
  tokens: 25607
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Rollback to the savepoint FIRST, classify second — a classifier that raises before the rollback leaves the outer transaction poisoned"
    - "Conflict discrimination on the driver's structured constraint_name, with the literals asserted against pg_constraint/pg_class at test time"
    - "A session wrapper that hooks the first read, so a second connection can commit in the exact window between re-resolution and insert"
    - "A two-party asyncio barrier that makes the race PREMISE deterministic while leaving the OUTCOME to the database"
    - "AST-over-stripped-source guards where a plain grep criterion would be satisfied only by deleting the documentation it exists to protect"

key-files:
  created:
    - tests/unit/test_conflict_classification.py
    - tests/unit/test_create_user_rollback.py
    - tests/schema/test_create_atomicity.py
    - tests/schema/test_create_race.py
  modified:
    - src/nativespeaker/api/auth/creation.py

key-decisions:
  - "Symbol names (left to implementation by the plan): RACE_CONSTRAINT_NAMES, PROVIDER_ACCOUNT_INDEX_NAME, CLIENT_CLASS_FOR_RESULT, classify_insert_conflict, _conflicting_constraint_name, _flush_account."
  - "The three constraint names stay LITERALS in creation.py (no runtime catalog lookup — that would be a per-request query to learn something static) and the schema test asserts them against pg_constraint/pg_class. A rename breaks a test instead of silently turning every conflict into an unmapped re-raise."
  - "CLIENT_CLASS_FOR_RESULT lives in creation.py beside the code that produces the results. routers/auth.py does not consume it yet — see Deviation 2 and Known Stubs."
  - "_result_for_existing became async and issues ONE extra read, only on the active arm, to reach its core.users row. A historical row is already decisive."
  - "The (issuer, subject) collision is forced by a second connection committing mid-transaction, not by a monkeypatch. The attribution-token collision pins uuid4 because its key is random by design and unknowable otherwise — the collision PostgreSQL then raises is real."
  - "An attribution-token conflict RE-RAISES rather than classifying: no core.auth_event_result describes it, and inventing one would tell a client something false."

patterns-established:
  - "Mutation-check a durability test before trusting it: removing `await savepoint.rollback()` turned 9 of 16 atomicity cases into PendingRollbackError errors, which is how the module was confirmed load-bearing rather than vacuous"
  - "Assert the premise of a concurrency test, not just its outcome — both racers record the identity-row count at their own barrier arrival"

requirements-completed: [CREATE-03, CREATE-04]

coverage:
  - id: D1
    description: "Three live constraint names map to exactly two internal results and two client classes; every other name re-raises"
    requirement: CREATE-04
    verification:
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestConflictDiscriminationByConstraintName (4 cases)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestAnUnrecognisedConflictIsReRaised (4 cases incl. external_identities_check, no orig, no constraint_name)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The literals in creation.py are the names PostgreSQL actually reports, read from pg_constraint and pg_class"
    requirement: CREATE-04
    verification:
      - kind: integration
        ref: "tests/schema/test_create_atomicity.py#TestTheConstraintNamesInTheCodeAreTheOnesPostgresReports (2 cases)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The in-transaction re-resolution's three no-mutation arms, with blocked_user distinct from historical_identity internally and identical to the client"
    requirement: CREATE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms (7 cases over a session whose every write entry point raises)"
        status: pass
    human_judgment: false
  - id: D4
    description: "ROADMAP criterion 3 — a forced mid-transaction failure leaves zero users, zero external_identities and zero store_purchase_tokens rows"
    requirement: CREATE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_rollback.py (9 cases: control flow, both failure positions, unmapped and non-IntegrityError propagation)"
        status: pass
      - kind: integration
        ref: "tests/schema/test_create_atomicity.py#TestAConflictOnTheIdentityInsertLeavesNoPartialAccount + TestAConflictOnTheAttributionTokenInsertAlsoUndoesTheFirstTwo"
        status: pass
    human_judgment: false
  - id: D5
    description: "The consumption and the rejected audit row COMMIT despite the business rollback — no PendingRollbackError anywhere"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/schema/test_create_atomicity.py::test_the_challenge_consumption_committed_despite_the_rollback + test_exactly_one_rejected_audit_row_committed (read back over a fresh connection)"
        status: pass
      - kind: other
        ref: "Mutation check: deleting `await savepoint.rollback()` produces 9 PendingRollbackError errors in this module; restored and verified byte-identical to the committed file"
        status: pass
    human_judgment: true
  - id: D6
    description: "ROADMAP criterion 4 — two concurrent completions on two real connections produce exactly one account, one succeeded, one identity_already_linked"
    requirement: CREATE-04
    verification:
      - kind: integration
        ref: "tests/schema/test_create_race.py#TestTwoConcurrentCompletionsProduceExactlyOneAccount (10 cases; stable over 8 consecutive runs)"
        status: pass
    human_judgment: false
  - id: D7
    description: "No merge and no overwrite of the winner's provider/provider_uid; the loser mints nothing"
    requirement: CREATE-04
    verification:
      - kind: integration
        ref: "tests/schema/test_create_race.py::test_the_surviving_row_carries_the_winners_pair_and_none_of_the_losers + test_the_winner_minted_two_tokens_and_the_loser_none"
        status: pass
      - kind: integration
        ref: "tests/schema/test_create_race.py#TestRunningTheSameCreationTwiceSequentially::test_the_second_run_overwrites_nothing_on_the_first_runs_row (byte-identical row before and after)"
        status: pass
    human_judgment: false
  - id: D8
    description: "No advisory lock, serializable isolation, generation CAS or row lock anywhere in the module"
    requirement: CREATE-04
    verification:
      - kind: unit
        ref: "tests/unit/test_conflict_classification.py#TestTheModuleUsesNoSecondRaceArbiter (6 parametrised cases over comment- and docstring-stripped source)"
        status: pass
    human_judgment: false

duration: ~25 min
completed: 2026-08-23
---

# Phase 37 Plan 09: The Consuming Transaction's Rejection Arms Summary

**A genuine `UNIQUE (issuer, subject)` race now earns its 409 instead of a 500, discriminated on the driver's `constraint_name` and proven — not asserted — by two real transactions on two real connections against PostgreSQL 17.11, with the loser's consumption and audit row read back committed from a third.**

## Performance

- **Started:** 2026-08-23T23:18Z
- **Completed:** 2026-08-23T23:40Z
- **Duration:** ~25 min active (plus ~8 min one-time environment provisioning — the worktree ships without `.venv`/`.env`)
- **Tasks:** 3
- **Files:** 5 (4 created, 1 modified, **0 deleted**)
- **Tests:** unit 1097 → 1133 (+36), schema 96 → 127 (+31), e2e 220 → 220 (unchanged). Zero failures throughout.

## Task Commits

1. **Task 1: in-transaction re-resolution + conflict discrimination** (TDD) — `eaabe50` (test, RED — `ImportError`, the symbols did not exist) → `009907f` (feat, GREEN). No REFACTOR commit; the GREEN implementation needed none.
2. **Task 2: criterion 3, no partial account** — `f64fd02` (test)
3. **Task 3: criterion 4, one account from two concurrent creates** — `a716011` (test)

Tasks 2 and 3 are single `test(...)` commits with no `feat(...)` pair, and correctly so — see Deviation 3.

## The Live Constraint Names: RESEARCH's Table Is Confirmed, Unchanged

Read from `pg_constraint` and `pg_index`/`pg_class` on the migrated scratch database. All three match 37-RESEARCH Pitfall 5's table exactly; **nothing needed correcting**.

| Rule | Live name | Catalog | Internal result | Client class |
|---|---|---|---|---|
| `UNIQUE (issuer, subject)` | `external_identities_issuer_subject_key` | `pg_constraint`, `contype='u'` | `identity_already_linked` | `identity_already_linked` (409) |
| `UNIQUE (user_id)` | `external_identities_user_id_key` | `pg_constraint`, `contype='u'` | `identity_already_linked` | `identity_already_linked` (409) |
| `UNIQUE (issuer, provider, provider_uid) WHERE provider_uid IS NOT NULL` | `ix_external_identities_provider_account` | **`pg_index`** — a standalone partial unique index is not a constraint and `pg_constraint` does not know it at all | `provider_account_already_linked` | `operation_not_allowed` (403) |
| the provider/provider_uid agreement CHECK | `external_identities_check` | — | *(none)* | re-raises |

**Why the names are literals in the code rather than a runtime lookup.** 37-04's executor recommended resolving them from the catalog because an unnamed constraint's generated name is not a stable contract. That is right about the *risk* and it is addressed here, but a per-request `pg_constraint` query would be a database round trip to learn something that cannot change while the process runs. The literals therefore live in `creation.py` and `tests/schema/test_create_atomicity.py` asserts them against the live catalog — the same test-time-lookup pattern 37-04 itself established. A migration that names a constraint explicitly breaks a named test with a legible message, rather than silently turning every race into an unmapped re-raise, which would surface to clients as a 500 exactly where the 409 was earned.

## The Savepoint Does Let the Consumption and the Audit Row Commit — Confirmed by Execution

This is the plan's central claim and it is now settled against a real database rather than inferred.

After a business `INSERT` is rolled back to the savepoint, read back **over a fresh connection**:

- `core.auth_challenges.consumed_at IS NOT NULL` and `preauth_subject_hash IS NULL` — consumption happened and cleared the verifier in the same state transition.
- Exactly one `audit.auth_events` row for that `challenge_row_id`, with `result = 'identity_already_linked'` — the specific internal result, not the `invalid_external_jwt` §02 step 12 names as the wrong answer.
- `details.mutation` records `user_created: false`, `identity_created: false`, `store_attribution_rows_minted: 0` — the rejection does not misdescribe the state it left.
- Zero `core.users`, zero new `core.external_identities`, zero `core.store_purchase_tokens`.
- No `PendingRollbackError` on any path, and the outer `commit()` succeeded.

**I did not take the passing test as proof on its own.** A durability test that passes for the wrong reason is worse than none, so the savepoint arm was mutated out (`await savepoint.rollback()` replaced with `pass`) and the module re-run: **9 of the 16 cases turned into `PendingRollbackError` errors**, precisely the failure 37-RESEARCH Pitfall 1 predicted. The line was then restored and `git diff` confirmed the file byte-identical to the committed version. The tests are load-bearing.

## The Interleaving Technique — What Was Used and Why

The plan offered two options and asked which was used. **Both were, for different cases**, because they answer different questions.

**Criterion 3 (`test_create_atomicity.py`) — a session wrapper that hooks the first read.** `create_account` is called completely unmodified; a thin wrapper around its session counts `exec` calls and, immediately after the first one returns, runs a callback on a *second* connection that commits the contested identity row and commits. The first `exec` is the in-transaction re-resolution, so the callback fires in exactly the window §02 step 12 describes. The attempt then reaches its savepoint and its `INSERT` genuinely violates `UNIQUE (issuer, subject)`. Nothing is monkeypatched and no production line is aware of the test.

**Criterion 4 (`test_create_race.py`) — `asyncio.gather` over two coroutines sharing a two-party barrier.** Each attempt runs on its own session on its own connection. The same first-read hook holds each one at a barrier — announce, then wait for the partner — so both are guaranteed past their re-resolution before either inserts. **Past the barrier nothing is coordinated**: both issue their inserts concurrently and PostgreSQL picks the winner, which is the part that must not be simulated. So the *premise* is deterministic and the *outcome* is genuinely the database's. Every assertion is written as "exactly one succeeded, exactly one rejected" rather than naming a winner, and the module was run 8 consecutive times with 15/15 passing each time.

**The premise is asserted, not assumed.** Each attempt records the identity-row count for the contested pair at its own barrier arrival, and a test asserts both saw `0`. Without that, the whole race case could be quietly passing through the no-mutation re-resolution arm — same returned result, none of the savepoint — and proving nothing at all about the constraint. That assertion is what makes the rest of the module mean what it says.

## No Merge, No Overwrite — Made Visible Rather Than Assumed

§02 spends a whole sentence forbidding the loser from merging into or overwriting the winner's row, and row counts alone cannot catch it. Two attempts for one subject would normally classify identically, which would make an overwrite invisible.

So **the two racers classify differently on purpose** — one `google` with its own `provider_uid`, one `apple` with its own. That is a legitimate real-world shape (the provider record can change between two lookups), and it makes the negative checkable: the surviving row must carry the winner's pair, and the loser's `provider_uid` must appear nowhere. The sequential double-run case does the literal before/after form as well — the row is read, a second attempt runs with a *different* provider and uid, and the row is asserted byte-identical including its `user_id`.

## Criterion 3's Second Forcing Shape

A conflict on the **third** insert is the case that would expose a savepoint scoped around only the first two. Its key is a fresh `uuid4()` per row by design, so it cannot be pre-seeded — the value is unknowable. That case therefore pins the generator (`monkeypatch.setattr(creation, "uuid4", ...)`), which makes the value knowable; the duplicate is then real and PostgreSQL raises a real `store_purchase_tokens_provider_identity_value_key` violation. That name is in no mapping, so it **re-raises** — correctly, because no `core.auth_event_result` describes an attribution collision and inventing one would tell a client something false about their account. The savepoint still rolled back first, and the test asserts zero `core.users` and zero `core.external_identities` rows survive.

This is the one place a patch was used, and it is a patch of the *test's* randomness, not of the code under test. The `(issuer, subject)` case — the one the plan explicitly asked not to monkeypatch — uses the real second-connection race.

## Deviations from Plan

### 1. [Self-invalidating acceptance criterion] `grep -ci "serializable\|advisory_lock\|pg_advisory"` cannot return 0 without deleting the documentation it protects

- **Found during:** Task 1
- **The conflict:** Task 1's acceptance criterion requires that grep to return `0`. It returned `1` *before I touched the file* — `creation.py:175`, written by 37-07, reads: `them the only arbiters. No `FOR UPDATE`, no advisory lock, no serializable isolation.` That line is the prose stating these mechanisms are **not** used, which is exactly what the plan's own `must_haves` truth #13 requires be true and discoverable. The criterion is satisfiable only by deleting the sentence that documents compliance.
- **Resolution (criterion's intent, not its letter):** the prose stays, and `tests/unit/test_conflict_classification.py::TestTheModuleUsesNoSecondRaceArbiter` parses the module with `ast`, strips docstrings and comments, re-unparses, and asserts none of `serializable`, `advisory_lock`, `pg_advisory`, `isolation_level`, `for update`, `select_for_update` appears in the **executable text**. That is the true form of "the module does not use X", which a text search over a file containing prose about X can never express. The same guard covers the `str(exc)`/`str(e)` criterion (which does hold literally — count 0 — and is asserted structurally as well).
- **Neither side dropped.** The prohibition is enforced more strictly than the grep would have; the documentation survives.

### 2. [Rule 4 → reported, not acted on] `provider_account_already_linked` reaches a client as `account_unavailable`, and the fix is in a file I may not edit

- **Found during:** Task 1
- **The issue:** `routers/auth.py::_completion_response` maps `succeeded` → 200, `identity_already_linked` → `IDENTITY_ALREADY_LINKED`, **everything else** → `ACCOUNT_UNAVAILABLE`. That was correct for every result `create_account` could previously return (`historical_identity` → `account_unavailable` ✓). This plan makes `provider_account_already_linked` reachable, and §02 step 11 gives it `operation_not_allowed` — same 403 status, **different code and different remediation** (support, not `/auth/sync`). The else-arm now under-specifies it. `blocked_user`, also newly reachable, maps correctly.
- **Why I did not fix it:** `routers/auth.py` is 37-08's file this wave and it is executing concurrently in another worktree. My instructions are explicit — make no edits there, and report rather than edit.
- **What I did instead:** exported `CLIENT_CLASS_FOR_RESULT` from `creation.py`, the authoritative result→class mapping, unit-asserted in full (including that the two conflict results land on two *different* `ErrorClass` objects, which is Task 1's acceptance criterion). The router fix is one line: `return error_response(CLIENT_CLASS_FOR_RESULT[result])` replacing the three-line conditional. Recorded as Known Stub 1, as ledger entry 8, and here. **Not silently shipped.**

### 3. Tasks 2 and 3 are marked `tdd="true"` but are test-only; the gate could not be honoured as RED→GREEN

- **Issue:** both tasks' subject — the savepoint rollback arm and the constraint discrimination — was implemented by Task 1, which is where the RED→GREEN pair legitimately lives (`eaabe50` → `009907f`). Writing production code purely so a Task 2 test could fail first would be theatre, and 37-07's Task 3 hit and documented the identical situation.
- **What replaced the gate:** the mutation check described above. Removing `await savepoint.rollback()` broke 9 of 16 atomicity cases, which establishes the same property RED→GREEN establishes — that the test fails when the behaviour is absent — without inventing a fake failing state.

### 4. Environment provisioning (not a code change)

The worktree ships without `.venv` or `.env` (both gitignored), so `uv sync --frozen` was run against the committed lockfile and `.env` was copied from the main checkout — exactly what 37-04 recorded. No dependency added; `uv.lock` and `pyproject.toml` are unmodified and untracked artifacts stayed untracked.

## Known Stubs

| # | Gap | Owner | Site | Behaviour today |
|---|---|---|---|---|
| 1 | `provider_account_already_linked` returns body code `account_unavailable` where §02 step 11 earns `operation_not_allowed` | 37-08 / whoever next owns `routers/auth.py` | `routers/auth.py::_completion_response` | Correct **status** (403) and a fail-closed refusal; the code and remediation are the wrong one of two 403 classes. One-line fix stated in Deviation 2. |

Nothing else. The two stubs this plan owned — 37-07's Known Stubs 3 and 4, ledger entries 5 and 7 — are **closed**, and both were marked `fixed` in `.planning/WINDOWS.md`.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or trust-boundary schema change beyond the plan's `<threat_model>`. Every `mitigate` disposition has a passing assertion:

| Threat | Status |
|---|---|
| T-37-41 (duplicate accounts from concurrent completions) | Two real connections, one account — `test_create_race.py`, 8/8 stable runs. No pre-SELECT-then-INSERT added. |
| T-37-42 (rejection audit row lost to a poisoned session) | Consumption + audit row read back committed from a fresh connection; mutation-verified load-bearing. |
| T-37-43 (loser merging into or overwriting the winner) | Racers classify differently so an overwrite is visible; plus a byte-identical before/after case. |
| T-37-44 (collapsing the two conflict classes) | Three names → two results → two `ErrorClass` objects, distinctness asserted on both layers. Discrimination on `constraint_name`; message-text parsing structurally excluded. **Client-facing half of this is Known Stub 1.** |
| T-37-45 (partial account) | All three inserts in one savepoint; failure forced on both the second and the third insert, zero rows in all three tables both times. Orphan-user and orphan-token queries assert zero. |
| T-37-46 (uniqueness violation escaping as a 500) | Recognised constraints classify; unrecognised ones re-raise deliberately. No test catches or expects `PendingRollbackError`. |
| T-37-SC (package installs) | No install. `uv sync --frozen` against the committed lockfile only. |

## Verification Commands Run

| Command | Result |
|---|---|
| `.venv/bin/pytest -q` | **1133 passed**, 347 deselected, 0 failed (baseline 1097) |
| `.venv/bin/pytest -q -m schema` | **127 passed**, 1353 deselected, 0 failed (baseline 96) |
| `.venv/bin/pytest -q -m e2e` | **220 passed**, 1260 deselected, 0 failed (baseline 220 — unchanged) |
| `.venv/bin/pytest -q -m schema tests/schema/test_create_race.py` × 8 | 15 passed every run — not flaky |
| `.venv/bin/ruff check src/ tests/` | All checks passed |
| Mutation: `savepoint.rollback()` removed → atomicity module | 7 passed, **9 errors** (`PendingRollbackError`); restored, `git diff` clean |
| `grep -c "str(exc)\|str(e)" creation.py` | 0 ✓ |
| `grep -ci "serializable\|advisory_lock\|pg_advisory" creation.py` | 1 — 37-07 prose only; see Deviation 1 |
| `grep -c "begin_nested" / "savepoint.rollback()" creation.py` | 2 / 1 ✓ |
| three constraint-name literals present in `creation.py` | 1 occurrence each ✓ |
| `git diff --diff-filter=D --name-only 0ef83e1..HEAD` | empty — no file deleted |

## Next Phase Readiness

- **37-08** is unaffected by this plan: no line of `routers/auth.py` was touched, and `create_account`'s signature and return type are unchanged. Its only new information is Known Stub 1 — a one-line change to `_completion_response` whose replacement value is already exported and tested.
- **Phase 38 (`POST /auth/sync`)** is the remediation the 409 names. The race loser's disposition is now fully proven, so 38 knows exactly what state a reconciling client arrives in: its own challenge consumed, its own `identity_already_linked` audit row durable, and no rows of its own anywhere.
- **Phases 40/41/42** inherit `classify_insert_conflict` and `CLIENT_CLASS_FOR_RESULT` for their own consuming transactions. Both are additive: a new constraint gets a new entry, and until it does, it re-raises loudly rather than being guessed at.
- **Left deliberately unproven:** nothing. Both ROADMAP criteria this plan owns are demonstrated against real committing PostgreSQL, not against mocks.

## Self-Check: PASSED

- All four created files exist at their declared paths; `src/nativespeaker/api/auth/creation.py` modified.
- All four task commits present in `git log 0ef83e1..HEAD`: `eaabe50`, `009907f`, `f64fd02`, `a716011`.
- TDD gate sequence intact for Task 1: `test(37-09)` (`eaabe50`, failing) precedes `feat(37-09)` (`009907f`).
- `git diff --diff-filter=D --name-only 0ef83e1..HEAD` → empty. No file deleted.
- Only the five declared files changed; `routers/auth.py`, `STATE.md` and `ROADMAP.md` are untouched (`git diff --stat` lists five paths).
- Branch verified `worktree-agent-a13e2768326da22d6` and descent from base `0ef83e1` before committing.

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-23*
