---
phase: 45-post-auth-restore-subscription
plan: 03
subsystem: api
tags: [sqlalchemy, sqlmodel, postgres, subscriptions, entitlements, concurrency]

# Dependency graph
requires:
  - phase: 43-post-webhooks-app-store
    provides: SubscriptionsDB.upsert_subscription, insert_purchase, write_subscription_grant, lock_grants, ENTITLED_STATUSES, PurchasesDB.resolve_user
  - phase: 45-post-auth-restore-subscription
    provides: "45-01: RestoreService, RestoredSubscription, RestoreRefused and its first leaf, seed_subscription; 45-02: the Play branch behind one _verify seam"
provides:
  - "GrantsDB.lock_active_grants_of: both accounts' active grant rows in one ascending statement"
  - "SubscriptionsDB.lock_grants_of: the two-tier composite over that lock, for the restore path"
  - "SubscriptionsDB.claim_subscription_owner: the conditional owner UPDATE, no subscription-row lock"
  - "D-09: upsert_subscription keeps an owner that is already set, and ingestion locks that same owner"
  - "RestoreAttributionMismatch: the second leaf of the restore_not_found family, declaring nothing"
  - "The adoption and adoption-with-creation branches of RestoreService, with the lost-claim re-read"
affects: [45-04 the capped move, 45-05 requirements amendments]

actuals:
  tokens: 9536
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "A conditional UPDATE whose WHERE restates the pre-transaction read, with is_not_distinct_from on both nullable columns; the row count is the whole contract"
    - "One statement over an `in_` of user ids, so two accounts are taken in one global ascending lock order rather than two"
    - "A single-id statement builder delegating to the many-id one, so the two lock methods cannot drift apart"
    - "`updated_at` as the executed witness that a branch ran no statement at all"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/grants.py
    - src/nativespeaker/api/crud/subscriptions.py
    - src/nativespeaker/api/services/restore.py
    - src/nativespeaker/api/services/subscriptions.py
    - src/nativespeaker/api/errors.py
    - tests/unit/test_subscription_attribution.py
    - tests/unit/test_rejection_vocabulary.py
    - tests/e2e/test_restore_subscription.py

key-decisions:
  - "The adoption-with-creation branch writes the row unowned and then claims it, because the pre-transaction read saw no row: owner_read is NULL, which is exactly what the conditional UPDATE must restate"
  - "`services/subscriptions.py` locks the owner the crud will keep, not the owner the token resolves to; D-09 in the crud alone would have expired an unrelated account's grants and then deadlocked on ix_access_grants_one_active_per_user"
  - "The two-user composite locks the usage row of every marked-active grant rather than of the effective subset, so the restore path adds one locking statement and not two"
  - "`_active_grants_statement` delegates to the new many-id builder, so a caller passing one id provably gets the rows `lock_active_grants` returns"
  - "claim_subscription_owner passes synchronize_session=False, which makes the RESEARCH note true rather than accidental: the statement reads nothing back and the service re-reads the row"
  - "list[UUID] rather than collections.abc.Collection: the crud import ratchet in test_claim_ordering.py admits no `collections` root, and list is the file's own convention"

patterns-established:
  - "Mirror-and-measure: a rule the unit suite's fake writer mirrors is changed in the same commit as the crud, with a case that fails before both change"
  - "Control pairs across classes: the adoption case asserts updated_at moves, so the same-account case asserting it does not move is non-vacuous"

requirements-completed: []

coverage:
  - id: D1
    description: "A verified proof for a subscription no account owns makes the caller its owner and writes one active grant with its usage row"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheAdoptionBranches::test_an_unowned_subscription_becomes_the_callers_and_carries_its_grant"
        status: pass
    human_judgment: false
  - id: D2
    description: "A verified proof with no canonical row creates that row at the proof's own status and tier, then attaches the grant"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheAdoptionBranches::test_a_proof_with_no_row_at_all_creates_it_at_the_proofs_own_state_and_tier"
        status: pass
    human_judgment: false
  - id: D3
    description: "A verified proof whose subscription is outside the entitled set answers 404 restore_not_found with the grant, usage, subscription and purchase counts unchanged"
    requirement: RESTORE-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTwoRefusalsOfTheRestoreNotFoundFamily::test_a_subscription_outside_the_entitled_set_writes_nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "A carried token recorded against another account answers the same 404, with the same four counts unchanged; the adoption case is the control that makes it non-vacuous"
    requirement: RESTORE-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTwoRefusalsOfTheRestoreNotFoundFamily::test_a_token_recorded_against_another_account_answers_the_same_body"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheTwoRefusalsOfTheRestoreNotFoundFamily::test_the_two_refusals_answer_bodies_equal_to_each_other"
        status: pass
    human_judgment: false
  - id: D5
    description: "T-45-05: the two refusals of the restore_not_found family declare neither status nor code below the base, so the bodies are byte-equal by structure"
    verification:
      - kind: unit
        ref: "tests/unit/test_rejection_vocabulary.py#TestTheRestoreArmsAnswerOneThingAndDeclareNothingBelowTheBase"
        status: pass
    human_judgment: false
  - id: D6
    description: "T-45-07: a renewal carrying the original buyer's attribution token does not change the owner of a subscription that already has one, and locks the owner it keeps"
    verification:
      - kind: unit
        ref: "tests/unit/test_subscription_attribution.py#TestTheOwnerIsChangedByRestoreAlone"
        status: pass
    human_judgment: false
  - id: D7
    description: "A same-account restore runs no owner UPDATE at all: the row's updated_at does not move, while the adoption case proves it moves when the statement runs"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSameAccountBranchRunsNoOwnerUpdate::test_the_row_the_caller_already_owns_is_not_written_at_all"
        status: pass
    human_judgment: false
  - id: D8
    description: "The conditional owner UPDATE takes no lock on core.subscriptions; the only locks are grant rows ascending by id, then their usage rows"
    verification:
      - kind: other
        ref: "test \"$(grep -c 'with_for_update' src/nativespeaker/api/crud/subscriptions.py)\" = \"0\""
        status: pass
      - kind: integration
        ref: "uv run pytest -m schema -q (205 passed)"
        status: pass
    human_judgment: false
  - id: D9
    description: "T-45-09: when the conditional UPDATE changes zero rows the transaction rolls back, the row is re-read, and the answer is what the new state earns"
    verification: []
    human_judgment: true
    rationale: "The arm exists and is read-only-verifiable by inspection, but no test drives two real connections into the losing branch this plan. 45-04 owns the two-connection race case on real PostgreSQL, per its own plan and CONTEXT D-13."

# Metrics
duration: 17 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 03: The adoption branches and D-09 Summary

**Restore now writes an owner where none exists — a conditional UPDATE that restates the pre-transaction read, under a grant lock that takes two accounts in one ascending statement — and ingestion can no longer take that owner back.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-09-08T01:22:43Z
- **Completed:** 2026-09-08T01:39:36Z
- **Tasks:** 2
- **Files modified:** 8 (0 created, 8 modified)

## Accomplishments

- `GrantsDB.lock_active_grants_of` takes both accounts' active grant rows in **one** `FOR UPDATE` statement with a single ascending `order_by` on the grant id, so two accounts are one global lock order rather than two. `_active_grants_statement` delegates to it, so the one-id caller provably gets the same rows.
- `SubscriptionsDB.claim_subscription_owner`: one `sqlalchemy.update()` whose `WHERE` restates the pre-transaction read with `is_not_distinct_from` on both nullable columns. No lock on `core.subscriptions` (43 D-16, D-08), no raw SQL, no synchronization — the row count is the whole answer.
- **D-09 landed with the restore writer, as CONTEXT required.** `upsert_subscription` now keeps an owner that is set; the token attributes an unowned row only. The unit suite's fake writer carries the same expression, changed in the same commit.
- The adoption branch and the adoption-with-creation branch, written as a refusal ladder in `services/auth.py::_claim_registered_grant`'s shape: entitlement, then attribution, then the stored owner, then the write.
- `RestoreAttributionMismatch` joins `RestoreSubscriptionNotEntitled` under `RestoreRefused`, declaring neither `status` nor `code`, so two causes answer one body — asserted byte-equal on the wire.
- Suite **1240 unit / 315 e2e / 205 schema**, `uv run ruff check src tests` clean.

## Task Commits

1. **Task 1 (RED): the failing D-09 owner case** — `74bab0c` (test)
2. **Task 1 (GREEN): the two-user lock, the conditional UPDATE and D-09** — `e60de17` (feat)
3. **Task 2 (RED): the failing adoption cases** — `793ed86` (test)
4. **Task 2 (GREEN): the adoption branches and the second refusal leaf** — `5811122` (feat)

**Plan metadata:** see the `docs(45-03)` commit that carries this file.

## Files Created/Modified

- `src/nativespeaker/api/crud/grants.py` — `_active_grants_of_statement` and `lock_active_grants_of`; the single-id builder now delegates
- `src/nativespeaker/api/crud/subscriptions.py` — `_claim_owner_statement`, `claim_subscription_owner`, `lock_grants_of`, and D-09's owner expression
- `src/nativespeaker/api/services/restore.py` — the branch ladder, the conditional claim, the purchase insert, and `_answer_as_the_winner_left_it`
- `src/nativespeaker/api/services/subscriptions.py` — the ingest lock now follows the same D-09 rule the crud holds
- `src/nativespeaker/api/errors.py` — `RestoreAttributionMismatch`, a leaf that declares nothing
- `tests/unit/test_subscription_attribution.py` — the fake writer's mirrored rule, and the two D-09 cases
- `tests/unit/test_rejection_vocabulary.py` — the log-vocabulary ratchet and the restore arm list, now two leaves
- `tests/e2e/test_restore_subscription.py` — adoption, adoption-with-creation, the two 404 refusals, the byte-equality pair, and the same-account no-update case

## Decisions Made

- **The created row is written unowned, then claimed.** The plan requires `claim_subscription_owner` to carry "the owner and month the pre-transaction read saw", and on adoption-with-creation that read saw no row at all. Creating the row already owned would have made `owner_read` a value no read ever produced, and would have moved the one owner write out of the statement that exists to settle owner writes.
- **`synchronize_session=False` on the update.** RESEARCH warns that a `Subscription` already in the identity map keeps its old `user_id`. Under SQLAlchemy's default `'auto'` that is not guaranteed — a fall-back to `'fetch'` would emit a second statement and expire the attribute. Pinning it makes the note true by construction, keeps the method to exactly one statement, and the service re-reads the row on the losing path as D-08 requires anyway.
- **The composite locks the usage row of every marked-active grant.** `lock_grants` locks the *effective* subset, which needs a second `FOR UPDATE` grant statement to compute. The plan forbids new locking statements beyond the two-user one plus `lock_usage`, so the restore path locks a superset within the same second tier. Effective grants are a subset of marked-active ones, so no lock is lost, and both tiers are still taken ascending by grant id.
- **`list[UUID]`, not `Collection[UUID]`.** `tests/unit/test_claim_ordering.py` holds a hand-maintained allow-list of import roots for `crud/grants.py`, and `collections` is not on it. Widening a ratchet that exists to keep a network client out of the crud, for a type annotation, is the wrong trade; `list[...]` is what the file already uses everywhere.
- **`updated_at` is the witness for "runs no owner UPDATE".** RESEARCH Q2's resolution proposes a call-site check. A call-site check is a code reading, not a measurement, so the same-account case asserts the row's clock does not move, and the adoption case asserts it does — the two together make the claim executed rather than argued.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] D-09 in the crud alone would have made ingestion expire the wrong account's grants**

- **Found during:** Task 1 (the D-09 rule)
- **Issue:** `services/subscriptions.py::ingest` computes the account it locks and grants as `owner = user_id if user_id is not None else stored.user_id` — the account the *token* resolves to. Once the crud keeps a stored owner, those two values diverge on exactly the case D-09 exists for. The service would then have locked account A's grants, passed them to `write_subscription_grant` as `marked_active`, and written the grant for account B: every one of A's active grants expired, then a 23505 on `ix_access_grants_one_per_subscription` for B, `lost_race`, a 500, and a store that redelivers forever. D-09 would have moved the failure rather than removed it.
- **Fix:** the service now restates the crud's rule — `owner = stored.user_id if stored is not None and stored.user_id is not None else user_id` — so the account locked is always the account the writer will keep. Every case where the two did not diverge is unaffected.
- **Files modified:** `src/nativespeaker/api/services/subscriptions.py`
- **Verification:** `tests/unit/test_subscription_attribution.py::TestTheOwnerIsChangedByRestoreAlone::test_the_locks_and_the_grant_follow_the_row_and_not_the_token`, which fails on the old line; `uv run pytest -m e2e -q` and `-m schema -q` green.
- **Committed in:** `e60de17`

**2. [Rule 3 - Blocking] `collections.abc.Collection` broke the crud import ratchet**

- **Found during:** Task 1 (the two-user lock)
- **Issue:** `tests/unit/test_claim_ordering.py::test_the_module_imports_only_the_stdlib_the_orm_and_this_project` walks `crud/grants.py`'s imports against a written-down allow-list; `collections` is not on it, so the suite went red on a type annotation.
- **Fix:** annotate with `list[UUID]`, which the file already uses, and drop the import from both crud modules.
- **Files modified:** `src/nativespeaker/api/crud/grants.py`, `src/nativespeaker/api/crud/subscriptions.py`
- **Verification:** `uv run pytest -q` (1237 passed at that point).
- **Committed in:** `e60de17`

### Departures from the plan text (not auto-fixes)

**3. `claim_subscription_owner` carries no SQLSTATE guard.** The plan says to copy the repeated 23505 guard "if the statement can raise `IntegrityError`". It cannot raise 23505: the statement writes `user_id`, `updated_at` and nothing else, and no unique index covers `core.subscriptions.user_id`. The two composite foreign keys that a changed owner could offend are `DEFERRABLE INITIALLY DEFERRED` and are checked at COMMIT as 23503 — a backstop and not control flow, exactly as the plan's own write-order paragraph says. Adding a guard for an unreachable code would have been a branch no case can enter.

**4. `services/subscriptions.py` is not in the plan's `files_modified`.** It is deviation 1 above. CONTEXT D-09 names `crud/subscriptions.py` and the tests that pin the old rule; the service's own owner line is a third mirror neither CONTEXT nor the plan located.

**5. Two of Task 2's four RED cases were green at RED.** The not-entitled and attribution-mismatch cases pass against 45-01's stub arm, which refused *everything* with the same 404. They were green for the wrong reason. The adoption case is what makes them non-vacuous after GREEN: it is the mismatch case's setup exactly, minus the one token binding, and it answers 200.

**6. The Task 2 e2e module gained one case the plan did not list** — the same-account no-owner-update case. It is the executed form of a plan `<behavior>` line ("A same-account restore runs no owner UPDATE at all") that the plan's acceptance criteria only gated by a call-site reading.

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking), plus 4 documented departures from the plan text.
**Impact on plan:** Deviation 1 is the load-bearing one — without it D-09 is a half-landed rule that trades one 500 loop for another. No scope creep: every file touched is inside the plan's declared trust boundaries or is the third mirror of the rule the plan's own threat register names.

## TDD Gate Compliance

Both tasks carry `tdd="true"` and both gate sequences are present and in order.

- **Task 1** — RED `74bab0c`: two cases, both failing with the owner reverted to the original buyer, which is the right reason. GREEN `e60de17`. No REFACTOR commit; the GREEN implementation needed no cleanup.
- **Task 2** — RED `793ed86`: the two adoption cases failing with 404 from 45-01's stub arms, which is the right reason. GREEN `5811122`. No REFACTOR commit.

The RED discipline was real in Task 1 despite the mirrored rule: the fake writer still carried the old expression at RED, so the case distinguished the two rules rather than restating one of them.

## Known Stubs

| File | Line | Stub | Resolved by |
|---|---|---|---|
| `src/nativespeaker/api/services/restore.py` | 72 | An owner that is another account raises `RestoreSubscriptionNotEntitled` | 45-04 (the capped move) |

One stub, carrying an inline comment naming 45-04, recorded as `.planning/WINDOWS.md` #25. This plan's two inherited entries — #23 (no stored row) and #24 (any owner other than the caller) — are closed: the first is now adoption-with-creation, and the second is split into the same-account branch, the adoption branch and this narrower move arm.

## Threat Flags

None. Every file touched is inside the plan's declared trust boundaries, and no new network endpoint, auth path or schema change was introduced.

The register's own dispositions:

- **T-45-07** (a renewal token overwriting a restored owner) — mitigated and proved by `TestTheOwnerIsChangedByRestoreAlone`, in the crud, in its unit mirror, and in the service line deviation 1 found.
- **T-45-01** (adoption as elevation of privilege) — mitigated: adoption requires a proof that verified *and* an entitled subscription, and a recorded attribution naming another account refuses.
- **T-45-05** (the two 404s as an enumeration oracle) — mitigated: the leaf declares neither `status` nor `code`, and the two bodies are asserted byte-equal to each other on the wire.
- **T-45-09** (the conditional UPDATE under concurrency) — the statement is in place and takes no subscription-row lock, but the losing arm is not yet driven by two real connections. 45-04 owns that case; recorded above as coverage `D9` with `human_judgment: true`.

The plan's `must_haves.prohibitions` entry — "ingestion must not silently take a restored subscription back from the account that restored it" — moves from `unverified` to **verified by test**.

## Issues Encountered

**A `git stash` was run mid-task and immediately reverted.** While checking whether `ty`'s diagnostics predated this plan, `git stash` was issued against the uncommitted Task 2 GREEN work. It was restored with `git stash pop` in the next command, confirmed intact by grep, and the stash entry was dropped. No work was lost and no commit was affected. `ty` is not a gate in this repository — there is no pre-commit config, no Makefile and no active git hook — and it reports 52 diagnostics against untouched code, so its baseline was not chased.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 45-04: `claim_subscription_owner` already takes `transfer_month`, and the arm that refuses an owner belonging to another account is the one line the move replaces. `lock_grants_of` takes a list, so adding the current owner is one element.
- 45-04 also owns the concurrency evidence this plan could not produce: two adopters racing for one unowned subscription, a second move in the same month, and a restore interrupted at commit, all on real PostgreSQL over two connections (CONTEXT D-13).
- `RESTORE-01` and `RESTORE-02` stay open in REQUIREMENTS.md: `requirements ready-ids` reports 0 of 1 ready, because 45-04 and 45-05 also declare them and have no summaries yet.
- The migration's comment on `last_cross_account_transfer_month` ("Written by nothing") is now one plan away from false. It is a 45-05 documentation item, not a code change: one migration, replaced and never amended.
- Flagged assumption A2 stands for both stores: no app exists on either platform, so no real store artifact has ever reached this deployment.

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*

## Self-Check: PASSED

- All eight modified files exist on disk and carry this plan's changes.
- All four task commits (`74bab0c`, `e60de17`, `793ed86`, `5811122`) are in the log.
- Every acceptance criterion of both tasks re-run and passing, including all four grep gates: `with_for_update` and `text(` are 0 in `crud/subscriptions.py`, `read_tokens` is 0 in `services/restore.py`, and the new lock statement carries exactly one ascending `order_by`.
- Both task `<verify>` blocks and the plan-level `<verification>` green: `uv run pytest -q` (1240 passed), `uv run pytest -m e2e -q` (315 passed), `uv run pytest -m schema -q` (205 passed), `uv run ruff check src tests` clean.
- Tracking writes confirmed on disk, not merely issued: `ROADMAP.md` shows `- [x] 45-03-PLAN.md` and `**Plans:** 3/5 plans executed`; `STATE.md` shows `Plan: 4 of 5` and `stopped_at: Completed 45-03-PLAN.md`.
