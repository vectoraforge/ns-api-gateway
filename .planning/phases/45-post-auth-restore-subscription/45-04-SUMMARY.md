---
phase: 45-post-auth-restore-subscription
plan: 04
subsystem: api
tags: [postgres, subscriptions, entitlements, concurrency, deferred-foreign-keys, sqlalchemy]

# Dependency graph
requires:
  - phase: 45-post-auth-restore-subscription
    provides: "45-01: RestoreService and the RestoreRefused family; 45-02: the Play branch; 45-03: claim_subscription_owner, lock_grants_of, the two-user lock and the lost-claim re-read"
  - phase: 43-post-webhooks-app-store
    provides: SubscriptionsDB.write_subscription_grant, ENTITLED_STATUSES, the term model
provides:
  - "RestoreTransferRejected: 409 restore_transfer_rejected, a second class at that status"
  - "The move branch of RestoreService: the two-user lock, the conditional claim carrying the transfer month, and the old owner's grant expired in the same transaction"
  - "D-10's cap, compared as real dates derived from the one captured instant"
  - "write_subscription_grant's replay check scoped to the destination account"
  - "tests/schema/test_restore_race.py: the adoption race, the capped double move, the interrupted commit and the deferred-foreign-key failure point"
  - "The first recorded use of _Attempt.integrity_at_commit in this repository"
affects: [45-05 requirements amendments]

actuals:
  tokens: 9808
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "A race barrier held at the door of the arbitrating statement rather than at the first flush: the arm under test writes nothing before it"
    - "A recording session that reads the SQLSTATE at both boundaries, because deferred constraints are checked at COMMIT and never at a flush"
    - "A third account as the control for `per subscription, never per user`: it had spent nothing of its own and was still refused"

key-files:
  created:
    - tests/schema/test_restore_race.py
  modified:
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/services/restore.py
    - src/nativespeaker/api/crud/subscriptions.py
    - tests/unit/test_error_contract.py
    - tests/unit/test_error_registry.py
    - tests/unit/test_rejection_vocabulary.py
    - tests/e2e/test_restore_subscription.py

key-decisions:
  - "write_subscription_grant's replay check now matches the destination account as well as the subscription: on a move `marked_active` carries the old owner's grant for the same subscription, at the same term and tier, and the writer read it as the caller's own replay"
  - "The e2e suite cannot observe a deferred foreign key at all: its session factory joins the outer transaction with `create_savepoint`, so every `commit()` is a savepoint release and the constraints are never checked"
  - "The two-connection barrier holds at the conditional owner UPDATE, not at the first flush: the adoption path emits no flush before that statement, so a flush barrier would release after the winner had already claimed"
  - "The transfer month is derived through `astimezone(UTC)`, so `UTC month` is true by construction rather than by the convention that `get_evaluated_at` returns UTC"
  - "The tests re-present one proof object across both restores, because one store reports one term for one subscription; two freshly minted proofs differ by microseconds and hide the writer defect"

patterns-established:
  - "Measure the premise, not just the outcome: the race case asserts both attempts read the row unowned at the barrier, so the arbitration claim cannot pass vacuously"
  - "A deliberately mis-ordered write, committed once, as the record of where a class of failure surfaces"

requirements-completed: []

coverage:
  - id: D1
    description: "The cap's refusal exists as one class at 409 with its own code, beside the challenge class already at that status, and both written-down mirrors carry it"
    requirement: RESTORE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_rejection_vocabulary.py#TestTheTransferRefusalStandsAloneAtItsOwnStatus"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_contract.py#TestOpenAPISchema::test_openapi_error_response_code_is_enum"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_registry.py#TestPhase37Classes::test_sharing_409_with_challenge_required_is_legal_and_intended"
        status: pass
    human_judgment: false
  - id: D2
    description: "A subscription owned by another account moves to the caller: the owner, the transfer month, the old owner's expired grant and the caller's new grant and usage row all land in one transaction"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSubscriptionMovesToTheCaller::test_the_owner_the_grants_and_the_transfer_month_all_move_together"
        status: pass
    human_judgment: false
  - id: D3
    description: "The account the subscription moved away from reads entitlement type none on its next /auth/sync (RESEARCH assumption A5, now executed rather than derived)"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSubscriptionMovesToTheCaller::test_the_account_it_moved_away_from_reads_no_entitlement_at_all"
        status: pass
    human_judgment: false
  - id: D4
    description: "A second move of one subscription in the same UTC calendar month answers 409 restore_transfer_rejected and writes nothing, on both the scripted stack and real PostgreSQL"
    requirement: RESTORE-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSecondMoveOfOneMonthIsRefused::test_a_stored_month_equal_to_this_one_answers_the_conflict_and_writes_nothing"
        status: pass
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTheSecondMoveOfOneMonthWritesNothing"
        status: pass
    human_judgment: false
  - id: D5
    description: "The cap is an equality on the month: a stored month earlier than this one is allowed and moves"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSubscriptionMovesToTheCaller::test_a_stored_month_earlier_than_this_one_is_allowed_and_moves"
        status: pass
    human_judgment: false
  - id: D6
    description: "Adoption and a same-account repeat spend none of the cap: last_cross_account_transfer_month stays NULL, and restore_bound_user_id stays NULL on every branch"
    requirement: RESTORE-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheBranchesThatSpendNoneOfTheCap"
        status: pass
    human_judgment: false
  - id: D7
    description: "T-45-09: two callers racing to adopt one unowned subscription on two real connections commit exactly one grant; the loser writes nothing and answers what the winner's state earns, never a 5xx"
    verification:
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTwoAdoptersOfOneSubscriptionCommitOneGrant"
        status: pass
    human_judgment: false
  - id: D8
    description: "A restore interrupted at its commit changes neither the owner nor any grant"
    verification:
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestARestoreInterruptedAtItsCommitChangesNothing"
        status: pass
    human_judgment: false
  - id: D9
    description: "T-45-11, RESEARCH Pitfall 2: a mis-ordered move surfaces as SQLSTATE 23503 at commit() and at no flush, and the production write order commits the same move"
    verification:
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTheDeferredForeignKeysFireAtCommitAndNotAtAFlush"
        status: pass
    human_judgment: false
  - id: D10
    description: "The writer's replay check reads the destination's own grants only, so a move is never mistaken for the old owner's replay"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSubscriptionMovesToTheCaller::test_the_owner_the_grants_and_the_transfer_month_all_move_together"
        status: pass
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTheDeferredForeignKeysFireAtCommitAndNotAtAFlush::test_the_production_order_commits_the_same_move"
        status: pass
    human_judgment: false
  - id: D11
    description: "The prohibition: the move does not take a paid subscription from the account paying for it more often than the published cap allows, and the cap is per subscription, never per user"
    verification:
      - kind: integration
        ref: "tests/schema/test_restore_race.py#TestTheSecondMoveOfOneMonthWritesNothing::test_a_second_move_in_the_same_month_answers_the_conflict"
        status: pass
    human_judgment: true
    rationale: "The mechanical half is measured: a third account that had spent nothing of its own is refused, which is what makes the cap per subscription rather than per user. Whether one move per UTC month is the right published product rule is D-10's own judgment, and no test can answer it."

# Metrics
duration: 21 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 04: The capped cross-account move Summary

**A subscription now leaves the account holding it and joins the caller once per UTC calendar month, refused with 409 on the second attempt — and the race, the cap, the interrupted commit and the deferred-foreign-key failure point are measured on real PostgreSQL rather than argued.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-09-08T01:45:03Z
- **Completed:** 2026-09-08T02:05:57Z
- **Tasks:** 3
- **Files modified:** 8 (1 created, 7 modified)

## Accomplishments

- `RestoreTransferRejected` — 409 `restore_transfer_rejected`, the second class at that status. `ChallengeRequired` keeps `answers_framework_status`, so a bare framework 409 still resolves to it; the totality walk, the OpenAPI enum and the log vocabulary all carry the new code.
- **The move branch.** The tie is `core.subscriptions.user_id`; `restore_bound_user_id` is neither read nor written. The stored month is compared as a real `date` derived from the one captured instant, so the cap refuses before any lock and with nothing written. Otherwise the two-user lock takes both accounts' grant rows in one ascending statement, the conditional UPDATE carries the computed transfer month, and the writer expires the old owner's grant and inserts the destination's in the same transaction.
- **The move, the cap and the moved-from account, end to end.** Five e2e cases through the real router: the move, the loss of access read back through `/auth/sync`, the cap with unchanged row snapshots for both accounts, the month boundary, and the two branches that spend none of the cap. Every case asserts `restore_bound_user_id` is still NULL.
- **`tests/schema/test_restore_race.py`** — 17 cases on real PostgreSQL: two adopters racing on two connections, the capped double move, a restore stopped at its commit, and RESEARCH Pitfall 2 proved as 23503 at `commit()`. The recording session now reads the SQLSTATE at both boundaries, and `_Attempt.integrity_at_commit` has its first recorded use.
- **T-45-09 is closed here**, as CONTEXT D-13 assigned it. 45-03 recorded it as coverage `D9` with `human_judgment: true` because no test drove two real connections into the losing arm of the conditional UPDATE. `TestTwoAdoptersOfOneSubscriptionCommitOneGrant` now does: both attempts are held at the door of that UPDATE, both read the row unowned, exactly one commits a grant, and the loser flushes nothing and answers 404.
- Suite **1246 unit / 321 e2e / 222 schema**, `uv run ruff check src tests` clean.

## Task Commits

1. **Task 1 (RED): the failing transfer-refusal cases** — `3606a04` (test)
2. **Task 1 (GREEN): the refusal, the move branch and the writer fix** — `c3cf727` (feat)
3. **Task 2: the move, the cap and the moved-from account end to end** — `be0b29c` (test)
4. **Task 3: the race, the atomicity and the deferred-key cases** — `96f8819` (test)

**Plan metadata:** see the `docs(45-04)` commit that carries this file.

## Files Created/Modified

- `tests/schema/test_restore_race.py` — **new.** The harness with its own lifecycle key and account list, a child-first cleanup that deletes usage and grants ahead of the subscriptions they point at, `_RecordingSession`, and the four case groups.
- `src/nativespeaker/api/errors.py` — `restore_transfer_rejected` in the `ErrorCode` literal and `RestoreTransferRejected` beside it, in one commit as the totality walk requires
- `src/nativespeaker/api/services/restore.py` — `current_owner`, the cap refusal, the two-account lock list, the transfer month on the claim, and `_this_month()`
- `src/nativespeaker/api/crud/subscriptions.py` — the writer's replay check scoped to the destination account
- `tests/e2e/test_restore_subscription.py` — the move, the moved-from `/auth/sync` read, the cap, the month boundary and the two no-cap branches, plus the snapshot helpers they compare with
- `tests/unit/test_error_contract.py` — `CONTRACT_CODES` gains the new code
- `tests/unit/test_error_registry.py` — the written-down set of codes at 409 gains the new one
- `tests/unit/test_rejection_vocabulary.py` — `EVENT_NAMES` gains the new event, and the new arm's own case group

## Decisions Made

- **The barrier holds at the conditional owner UPDATE, not at the first flush.** The ingestion analog holds `before_first_flush`, which works there because `upsert_subscription` flushes first. On the adoption path the row already exists, so nothing flushes until `insert_purchase` — which runs *after* the claim. A flush barrier would have released both attempts only once the winner had already claimed the row, and the case would have measured a sequence rather than a race. `_RecordingSession.exec` recognises an `Update` statement and holds there instead.
- **One proof object is re-presented across both restores.** `_proof()` mints `expires_at` from `datetime.now(UTC)`, so two calls differ by microseconds — enough for the writer to treat the two terms as different and mask the defect below. A store reports one term for one subscription, so the destination is shown the same expiry the old owner was shown. This is what made the writer defect visible.
- **`astimezone(UTC)` before `.date()`.** `get_evaluated_at` returns a UTC instant today, so `.date()` alone would be correct by convention. The conversion makes "the captured instant's UTC month" true by construction, at the cost of one call.
- **The deferred-foreign-key case drives the crud directly, not the service.** The service's write order is now correct, so the only way to reach the violation is to emit the owner UPDATE alone. Its control — the same move through the production path, committing — is what keeps the case about ordering rather than about the write being illegal.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `write_subscription_grant` read the old owner's grant as the destination's replay**

- **Found during:** Task 1 (the move branch), confirmed empirically before the GREEN commit
- **Issue:** The writer's replay check filters `marked_active` by source and `subscription_id` but not by account. On a move `marked_active` now carries **both** accounts' grants, and the old owner's grant for this subscription has the same `ends_at` and `tier_id` — because the store reports one term. The writer therefore answered `replayed` and wrote nothing at all: the owner UPDATE had already run, the destination received no grant, the old owner kept an active one, and the response reported `entitlement.type: none` with a 200. In production, where the commit is real, the same state additionally trips the deferred composite foreign key at COMMIT as 23503 — an uncaught `IntegrityError` and a 500.
- **Fix:** one added conjunct, `grant.user_id == user_id`. The writer is not forked: `superseded` still expires every marked-active grant of both accounts when the destination is entitled, which is what expires the old owner's grant. For every single-account caller — both webhooks, adoption, the same-account restore — the conjunct is already true of every row, so their behaviour is unchanged.
- **Files modified:** `src/nativespeaker/api/crud/subscriptions.py`
- **Verification:** `tests/e2e/test_restore_subscription.py::TestTheSubscriptionMovesToTheCaller::test_the_owner_the_grants_and_the_transfer_month_all_move_together`, which fails on the old expression with `assert 'none' == 'subscription'`; and `tests/schema/test_restore_race.py::…::test_the_production_order_commits_the_same_move`, which commits the move against real PostgreSQL.
- **Committed in:** `c3cf727`

**2. [Rule 3 - Blocking] A third written-down mirror of the codes at 409**

- **Found during:** Task 1 (GREEN)
- **Issue:** `tests/unit/test_error_registry.py::TestPhase37Classes::test_sharing_409_with_challenge_required_is_legal_and_intended` holds the set of codes declared at 409 as a literal. The plan names two mirrors; this is a third, and it went red the moment the class existed. Its own docstring says statuses may be shared by several codes, so admitting the new one is what the case is for.
- **Fix:** add `restore_transfer_rejected` to the literal.
- **Files modified:** `tests/unit/test_error_registry.py`
- **Verification:** `uv run pytest -q` (1246 passed).
- **Committed in:** `c3cf727`

### Departures from the plan text (not auto-fixes)

**3. `src/nativespeaker/api/crud/subscriptions.py` is not in the plan's `files_modified`.** It is deviation 1. The plan's instruction "do not fork the writer" is honoured — there is still one writer and one call site — but the writer's replay rule was written for a caller that locks one account, and this plan is the first to hand it two.

**4. Task 1's RED could not import the new class.** A module-level import of a class that does not exist breaks collection for the whole file, which would have hidden whether the two literal additions were right. The RED reads the class off the already-imported module inside each test body instead, so the failure is a precise `AttributeError` naming the missing class, and the two literal cases fail separately for their own reasons.

**5. Task 1's behaviour has no unit case of its own.** Task 1's `<files>` names only the two error-vocabulary test files and its `<verify>` runs the unit selection, so the move branch itself lands in GREEN with its cases in Tasks 2 and 3. The month arithmetic is `evaluated_at.astimezone(UTC).date().replace(day=1)`; both the e2e cap case and the schema double-move case pin the written value.

**6. The e2e cap case seeds through the production path rather than through a seeded grant.** `seed_grant` takes no `subscription_id`, so it cannot seed a subscription-source grant at all. The old owner restores first instead, which gives it a grant the route itself wrote — a stronger setup than a hand-built row, and it needed no change to `tests/e2e/conftest.py`.

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking), plus 4 documented departures from the plan text.
**Impact on plan:** Deviation 1 is load-bearing. Without it the move is a silent no-op on the scripted stack and a 500 in production, and every "the move works" claim in this plan would have been false. No scope creep: the one production file outside the plan's list is the writer the plan's own Task 1 instructs the move to call.

## TDD Gate Compliance

Task 1 carries `tdd="true"` and its gate sequence is present and in order.

- **RED** `3606a04`: seven failing cases — two literal mirrors that fail with a set mismatch, and five that fail with `AttributeError: module 'nativespeaker.api.errors' has no attribute 'RestoreTransferRejected'`. Each is the right reason.
- **GREEN** `c3cf727`. No REFACTOR commit; the implementation needed no cleanup.

Tasks 2 and 3 are `type="auto"` and carry no gate sequence; both are test-only and are committed as `test(45-04)`.

## Known Stubs

None. `.planning/WINDOWS.md` #25 — the arm that refused an owner belonging to another account — is closed by this plan and marked `fixed`; the ledger's open count fell from 15 to 14. `src/nativespeaker/api/services/restore.py` now carries no TODO, no FIXME and no arm deferred to a later plan.

## Threat Flags

None. No new network endpoint, auth path or schema change; `pyproject.toml` is untouched, so T-45-SC stands accepted.

The register's own dispositions:

- **T-45-01** (the move as elevation of privilege) — mitigated as D-10 specifies. One verified proof reaches at most two accounts in a UTC month, and the schema double-move case proves the cap follows the subscription: a third account that had spent nothing of its own is still refused.
- **T-45-09** (`claim_subscription_owner` under concurrency) — **mitigated and now measured.** Two real connections, both held at the UPDATE, one grant committed, the loser writing nothing. This is the case 45-03 could not produce.
- **T-45-10** (repeated moves as denial of service) — mitigated: the refusal is raised before any lock, and the schema case asserts the attempt flushed zero times and left both accounts' pictures byte-identical.
- **T-45-11** (the write order against the deferred foreign keys) — mitigated and proved. The mis-ordered write surfaces as 23503 at `commit()` and at no flush; the production order commits the same move.

The plan's `must_haves.prohibitions` entry moves from `unverified` to **verified by test** for its mechanical half, and stays a judgment for the rest: see coverage `D11`.

## Issues Encountered

**The e2e suite cannot observe a deferred foreign key, and now that is written down.** `tests/e2e/conftest.py::_db_transaction` builds its session factory with `join_transaction_mode="create_savepoint"`, so every `session.commit()` the app makes under test is a savepoint release inside one outer transaction that is always rolled back. `DEFERRABLE INITIALLY DEFERRED` constraints are checked at the real COMMIT, which never happens. A probe confirmed it: changing a subscription's owner while an active grant still referenced the old pair committed cleanly in e2e, and the same write raises 23503 in `tests/schema`. RESEARCH Pitfall 2 predicted the shape of this ("an e2e restore test passing while the schema test fails"); the cause is now identified to the line. Nothing needs repairing — the schema suite is where these cases belong and is where they were written — but no future plan should read an e2e pass as evidence about a deferred constraint.

No authentication gates. No `git stash` was run at any point in this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 45-05, the requirements amendments. All three outcomes of the route — same account, adoption, move — are executed cases, and both new error codes of this phase now exist with their mirrors.
- The migration's comment on `last_cross_account_transfer_month` ("Written by nothing: cross-account restore transfer is never performed, so this stays NULL") is **now false**. 45-05 owns recording that divergence in REQUIREMENTS.md; the migration itself is not edited (43 D-27, 45 D-14).
- `RESTORE-01` and `RESTORE-02` stay open: `requirements ready-ids` reports 0 of 1 ready, because 45-05 also declares them and has no summary yet.
- Flagged assumption A2 stands for both stores: no app exists on either platform, so no real store artifact has ever reached this deployment. Every proof in this phase's tests is scripted behind the two Protocols.

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*

## Self-Check: PASSED

- All eight source and test files exist on disk and carry this plan's changes; `tests/schema/test_restore_race.py` is new and collected under `-m schema` (17 cases).
- All four task commits (`3606a04`, `c3cf727`, `be0b29c`, `96f8819`) are in the log, RED before GREEN.
- Every acceptance criterion of all three tasks re-run and passing, including the grep gates: `restore_transfer_rejected` appears twice in `errors.py` (the literal and the class), `RestoreTransferRejected` declares `status = 409`, and `grep -c 'strftime' src/nativespeaker/api/services/restore.py` is 0.
- Both task-level and plan-level verification green: `uv run pytest -q` (1246 passed), `uv run pytest -m e2e -q` (321 passed), `uv run pytest -m schema -q` (222 passed), `uv run ruff check src tests` clean.
- Tracking writes confirmed on disk, not merely issued: `ROADMAP.md` shows `- [x] 45-04-PLAN.md` and `**Plans:** 4/5 plans executed`; `STATE.md` shows `Plan: 5 of 5` and `stopped_at: Completed 45-04-PLAN.md`; `WINDOWS.md` #25 reads `"status": "fixed"`.
