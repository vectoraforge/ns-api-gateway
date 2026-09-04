---
phase: 43-post-webhooks-app-store
plan: 04
subsystem: payments
tags: [access-grants, locks, postgres, sqlmodel, subscriptions, entitlements]

# Dependency graph
requires:
  - phase: 43-01
    provides: "`SubscriptionsDB`, `SubscriptionsService`, `status_at` and the one `commit()`"
  - phase: 43-03
    provides: "the resolved owner on `core.subscriptions.user_id`, and the add-never-clear rule"
  - phase: 42-02
    provides: "`activate_registered_account_grant`'s expire-then-flush boundary and its two-tier lock shape"
provides:
  - "`SubscriptionsDB.lock_grants`: the two lock tiers for one buyer, taken before every contended question"
  - "`SubscriptionsDB.write_subscription_grant`: the same-term no-op, the expire-then-insert flip, and the fresh usage row"
  - "`ENTITLED_STATUSES`: the set the generated column is built over, named once in `src/`"
  - "`insert_subscription` and `insert_store_purchase` in `tests/schema/helpers.py`"
  - "`tests/schema/test_subscription_ingestion.py`: every ingestion outcome executed on real PostgreSQL"
  - "The third lock-tier class and the third single-writer walk"
affects: [43-05, 43-06, 44-webhook-google-play-rtdn, 45-restore-subscription]

actuals:
  tokens: 10600
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A crud writer takes its locks through one method the caller runs first, so the replay read can sit between the locks and the writes"
    - "The superseded set is every grant the buyer holds, because the one-active index allows exactly one"

key-files:
  created:
    - tests/schema/test_subscription_ingestion.py
  modified:
    - src/nativespeaker/api/crud/subscriptions.py
    - src/nativespeaker/api/services/subscriptions.py
    - tests/schema/helpers.py
    - tests/schema/test_grant_locks.py
    - tests/unit/test_grant_sources.py
    - tests/unit/test_subscription_attribution.py

key-decisions:
  - "The writer locks `lock_active_grants` first and `lock_effective_grants` second, mirroring `activate_registered_account_grant`. The plan named only the effective read; a renewal's superseded grant is time-ended and therefore outside it, so the effective read alone would insert a second active grant per subscription and answer 500 for ever. Still exactly two tiers."
  - "When the subscription is entitled, every grant the buyer holds is superseded, not this subscription's alone. `ix_access_grants_one_active_per_user` allows one active grant per user, so a second subscription, a free grant and a `manual` grant all have to end before the paid one lands. This is what makes D-19's newest-purchase-wins rule reachable."
  - "`FREE_GRANT_SOURCES` is not referenced by the new writer. The free grant is expired because it is one of the buyer's held grants, not because its source was tested; a source test would have been a second, narrower copy of the same rule."
  - "`ENTITLED_STATUSES` lives in `crud/subscriptions.py`, so the entitled set is asked in one place rather than at each caller."
  - "The buyer is `user_id if this delivery resolved one else the stored owner`, read from a plain `read_subscription` before the locks. A subscription-row lock would be a tier ahead of the grant locks; a read is not a lock."
  - "A mid-term tier change takes the same expire-then-insert path, because the no-op test asks the tier with the term. The superseded term therefore stays in history."
  - "APPLEHOOK-01 is NOT marked complete by this plan — see Deviations, as 43-01 and 43-03 recorded."

patterns-established:
  - "A lock method separate from the writer, so the replay read sits after the locks and before the writes without the writer knowing about replay"

requirements-completed: []

coverage:
  - id: D18
    description: "An attributed, entitled notification leaves one active `subscription` grant on the mapped tier, with `starts_at` at the purchase date, `ends_at` at the expiry, and a fresh usage row at `monthly_used = 0` in the captured instant's month"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestTheFirstTermIsWritten::test_the_paid_grant_carries_the_term_and_the_mapped_tier"
        status: pass
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestTheFirstTermIsWritten::test_the_fresh_usage_row_is_written_with_the_grant"
        status: pass
    human_judgment: false
  - id: D19
    description: "An active grant for this subscription with the same `ends_at` and the same tier is an idempotent no-op: neither the grant's `updated_at` nor the usage row changes"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestTheTermDecidesWhatIsWritten::test_the_same_term_writes_nothing_to_either_table"
        status: pass
    human_judgment: false
  - id: D20
    description: "A renewal flips the superseded grant to `expired` with `ends_at` set, flushed alone and first, then inserts the next term's grant and its fresh usage row"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestTheTermDecidesWhatIsWritten::test_a_renewal_expires_the_old_term_and_inserts_the_next"
        status: pass
    human_judgment: false
  - id: D21
    description: "The buyer's active free grant is expired, never deleted, before the paid grant is inserted, and its usage row survives"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestTheFirstTermIsWritten::test_the_buyers_free_grant_is_expired_and_not_deleted"
        status: pass
    human_judgment: false
  - id: D22
    description: "Outside the entitled set the grant is marked `expired`, or `revoked` when the store withdrew the purchase, with `ends_at` set and no replacement inserted"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestLeavingTheEntitledSet::test_an_ended_term_leaves_the_buyer_holding_no_grant"
        status: pass
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestLeavingTheEntitledSet::test_a_withdrawn_purchase_marks_the_grant_revoked"
        status: pass
    human_judgment: false
  - id: D23
    description: "A second subscription for the same buyer wins through the same expire-then-insert path, and a repeat delivery for a recorded lifecycle key writes no second purchase row"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestTheNewestPurchaseWins"
        status: pass
    human_judgment: false
  - id: D24
    description: "An unattributed notification writes the subscription and its event row and no grant and no usage row, and takes no lock at all"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestNothingIsWrittenWithoutABuyerOrOnAReplay::test_an_unattributed_notification_writes_no_grant_and_no_usage_row"
        status: pass
      - kind: schema
        ref: "tests/schema/test_grant_locks.py::TestTheSubscriptionWriterAddsNoThirdLockTier::test_the_unattributed_path_takes_no_lock_at_all"
        status: pass
    human_judgment: false
  - id: D25
    description: "A replayed `notification_uuid` leaves all four row counts unchanged and the held term untouched, even when the second delivery carries a later expiry"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestNothingIsWrittenWithoutABuyerOrOnAReplay::test_a_replayed_notification_uuid_leaves_every_count_unchanged"
        status: pass
    human_judgment: false
  - id: D26
    description: "The deferrable foreign key is the backstop it is claimed to be: a subscription that leaves the entitled set with its grant left active fails the commit"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_subscription_ingestion.py::TestTheDeferrableForeignKeyIsTheBackstop::test_a_grant_left_active_fails_the_commit"
        status: pass
    human_judgment: false
  - id: D27
    description: "The SQL the ingestion writer emits locks the grant rows ascending by id before the usage rows and takes exactly two distinct lock tiers, naming neither `core.subscriptions`, `core.store_purchases` nor `core.users`"
    requirement: APPLEHOOK-01
    verification:
      - kind: schema
        ref: "tests/schema/test_grant_locks.py::TestTheSubscriptionWriterAddsNoThirdLockTier"
        status: pass
    human_judgment: false
  - id: D28
    description: "`AccessGrantSource.subscription` has exactly one construction site in `src/`, inside the crud writer the two lock tiers are taken for"
    requirement: APPLEHOOK-01
    verification:
      - kind: unit
        ref: "tests/unit/test_grant_sources.py::TestTheSubscriptionGrantHasExactlyOneWriter"
        status: pass
      - kind: unit
        ref: "tests/unit/test_grant_sources.py::TestTheSubscriptionWalkFires"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-09-04
status: complete
---

# Phase 43 Plan 04: The Entitlement Grant, Written Under the Two Lock Tiers — Summary

**A verified, entitled, attributed notification now leaves the buyer holding exactly one active `core.access_grants` row on the mapped tier with its fresh `core.user_monthly_usage` row, written in the same transaction as the subscription row under the project's fixed lock order — and every outcome is an executed case against real PostgreSQL.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-09-04T22:36:00Z
- **Completed:** 2026-09-04T22:56:00Z
- **Tasks:** 3 of 3
- **Files modified:** 7 (1 created, 6 modified)

## Accomplishments

- **The lock order is one method, taken before the replay read.** `SubscriptionsDB.lock_grants` takes `GrantsDB.lock_active_grants`, then `GrantsDB.lock_effective_grants`, then `lock_usage` for each effective grant — reusing `GrantsDB`'s own statements rather than writing a second spelling. The service calls it after the attribution read and before `read_event` (`services/subscriptions.py:65` → `:75` → `:77`), so no token read ever happens under a lock and no question a concurrent writer could change is asked before them.
- **The term is the grant's `ends_at`, and the tier is asked with it.** The same-term no-op is reached before any grant or usage write, and it is conditioned on the resolved tier as well as the expiry — so a mid-term tier change is applied rather than swallowed, through the same expire-then-insert path, leaving the superseded term readable in history.
- **Expire, flush, then insert.** The superseded rows are flipped and flushed alone and first, copying `crud/grants.py:216-239` with its reason: `ix_access_grants_one_per_subscription` is partial and per-statement, so the update has to land before the insert. Every flush sits alone in its `try` and the `except IntegrityError` arm reads SQLSTATE off the wrapped error, returning `lost_race` for `23505` and re-raising everything else.
- **The lapsed subscriber ends with nothing, deliberately.** The buyer's free grant is expired and never deleted, which spends the lifetime slot permanently because `ix_access_grants_one_free_grant_per_user_source` carries no status predicate. When the subscription later leaves the entitled set its grant is marked `expired` or `revoked` and no replacement is written. Both halves are executed cases, and D-18 accepts the consequence.
- **The deferrable foreign key was shown to fire.** The non-entitled transition is asserted to commit with the grant transitioned, and a control case attempts the same transition with the grant left active and observes `ForeignKeyViolationError` at the commit. Without it the first case could have passed with no constraint present at all.
- **Both structural claims were mutation-checked this session, not assumed.** Adding a `FOR UPDATE` on `core.subscriptions` inside `lock_grants` failed two lock-tier cases; adding a second `AccessGrantSource.subscription` construction site in `services/subscriptions.py` failed two single-writer cases. Both mutations were reverted and the suites re-run green.

## Task Commits

1. **Task 1: The subscription grant, written under the two lock tiers** — `d408f63` (feat)
2. **Task 2: The writer's outcomes, measured on real PostgreSQL** — `b037417` (test)
3. **Task 3: The lock tiers and the single writer, proved structurally** — `266790e` (test)

## Files Created/Modified

**Created**

- `tests/schema/test_subscription_ingestion.py` — 12 cases over the real `SubscriptionsService` against the migrated scratch database, each asserting the rows that exist afterwards rather than the statements that produced them, with FK-ordered clean-up keyed on the case's throwaway tier.

**Modified**

- `src/nativespeaker/api/crud/subscriptions.py` — `ENTITLED_STATUSES`, `lock_grants`, `write_subscription_grant`, and `GrantsDB` on the class. The module docstring now names the lock order it takes.
- `src/nativespeaker/api/services/subscriptions.py` — the subscription read and the owner decision moved ahead of the locks, the locks ahead of the replay read, and the grant write placed after the event append and before the one `commit()`.
- `tests/schema/helpers.py` — `insert_subscription` and `insert_store_purchase`, keyword-only, every value bound through an asyncpg `$N` parameter, neither committing nor owning a transaction.
- `tests/schema/test_grant_locks.py` — `_ingestion_run` and `TestTheSubscriptionWriterAddsNoThirdLockTier`, asserting over the captured `before_cursor_execute` statements. The module imports `PRODUCT_ID`, `_notification` and `_clean` from the ingestion module rather than copying them, following 42-03's reuse-by-import rule.
- `tests/unit/test_grant_sources.py` — `TestTheSubscriptionGrantHasExactlyOneWriter` and `TestTheSubscriptionWalkFires`. The two existing walk classes are byte-identical; `git diff` shows no removed line in the file.
- `tests/unit/test_subscription_attribution.py` — the 43-03 recording stand-in gained `lock_grants` and `write_subscription_grant` (see Deviations 3).

## Decisions Made

1. **`lock_active_grants` first, `lock_effective_grants` second.** The registered writer's exact shape and its exact reason: the status-only set contains the effective one, so one grant-tier order holds. The effective read is not decorative — its result selects which usage rows are locked, as it does at `crud/grants.py:192-196`.

2. **The superseded set is every grant the buyer holds.** `ix_access_grants_one_active_per_user` allows exactly one active grant per user, so a paid grant cannot land beside a free one, a `manual` one, or another subscription's. Superseding a `manual` comp grant is a real consequence of this and is recorded rather than special-cased: refusing instead would 500 on every retry for ever, which is worse than ending a grant the store's own purchase replaces.

3. **`FREE_GRANT_SOURCES` is not named by the new writer.** The plan asked for a source test over that constant. With decision 2 the free grant is already in the superseded set, and a source test would have been a second, narrower copy of a rule the index already carries. The behaviour D-18 demands is unchanged and is an executed case.

4. **The buyer is read, never locked.** `owner` is this delivery's resolved user when it has one and the stored `user_id` otherwise, read through the existing plain `read_subscription`. A stale read is arbitrated by the unique indexes and the deferrable foreign key, which is the same trade 43-03 already took for the attribution read.

5. **`starts_at` falls back to the captured instant** when the store gave no purchase date, because `core.access_grants.starts_at` is NOT NULL. Every other timestamp derives from the one captured instant, and neither module names `datetime.now`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] The effective read alone cannot see the grant a renewal supersedes**

- **Found during:** Task 1
- **Issue:** The plan says to reuse `GrantsDB.lock_effective_grants` and `GrantsDB.lock_usage`, and names no other read. `_effective_grants_statement` requires `ends_at IS NULL OR ends_at > evaluated_at`. A renewal arrives at or after the old term's expiry, so the grant it supersedes is time-ended and outside that set. The writer would have found nothing to flip, inserted a second grant for the same subscription, been refused by `ix_access_grants_one_per_subscription` mid-flush, read `23505` as a lost race, rolled back and answered 500 — on every retry, for ever, because the state never converges.
- **Fix:** `lock_grants` takes `lock_active_grants` first, exactly as `activate_registered_account_grant` does and for the identical stated reason, and branches on that set. `lock_effective_grants` still runs, still before `lock_usage`, and its result still chooses the usage rows locked. Both statements read `core.access_grants`, so the writer still takes exactly two distinct tiers.
- **Files modified:** `src/nativespeaker/api/crud/subscriptions.py`
- **Verification:** `tests/schema/test_subscription_ingestion.py::TestTheTermDecidesWhatIsWritten::test_a_renewal_expires_the_old_term_and_inserts_the_next`, and `TestTheSubscriptionWriterAddsNoThirdLockTier::test_exactly_two_distinct_lock_tiers_are_taken_on_the_ingestion` for the tier count.
- **Committed in:** `d408f63`

**2. [Rule 1 — Bug] Superseding only this subscription's grants breaks newest-purchase-wins**

- **Found during:** Task 2
- **Issue:** The first writer filtered the superseded set to grants whose `subscription_id` matched. D-19 requires the newest verified purchase to win across two different subscriptions for one buyer. With the filter, subscription B's grant would have been inserted while subscription A's stayed active, and `ix_access_grants_one_active_per_user` would have refused it — the same permanent 500 loop as deviation 1, reached by a different door.
- **Fix:** When the subscription is entitled the superseded set is every grant the lock returned; outside the entitled set it stays this subscription's alone, because nothing replaces them.
- **Files modified:** `src/nativespeaker/api/crud/subscriptions.py`
- **Verification:** `tests/schema/test_subscription_ingestion.py::TestTheNewestPurchaseWins::test_a_second_subscription_supersedes_the_first`.
- **Committed in:** `b037417`

**3. [Rule 3 — Blocking] The 43-03 recording stand-in did not know the two new crud methods**

- **Found during:** Task 1
- **Issue:** `tests/unit/test_subscription_attribution.py::_RecordingSubscriptions` replaces `SubscriptionsDB` wholesale on the real service. Eleven cases failed with `AttributeError: '_RecordingSubscriptions' object has no attribute 'lock_grants'`.
- **Fix:** Two recording methods added, in the shape the file's other five use. `lock_grants` answers with an empty list, which is the shape a buyer holding nothing has.
- **Files modified:** `tests/unit/test_subscription_attribution.py`
- **Verification:** `uv run pytest -q` — 1066 passed at the time of the fix, the pre-task count exactly.
- **Committed in:** `d408f63`

### Departures from the plan's letter, taken deliberately

**4. Task 1 is one commit, not a RED/GREEN/REFACTOR sequence.** The task carries `tdd="true"` and its own `<files>` block lists two source modules and no test file — every behavioural test of the writer is assigned to tasks 2 and 3. A RED commit would have had nothing to fail. The writer was driven against the real database before task 1 was committed, through the existing e2e ingestion cases, which exercise the attributed path end to end. `TDD_MODE=false` for this phase, so no gate was bypassed. 43-01 and 43-03 recorded the same boundary.

**5. `requirements.mark-complete` was NOT run for APPLEHOOK-01, and `.planning/REQUIREMENTS.md` is unmodified.** All six plans in phase 43 declare APPLEHOOK-01, and 43-06 owns the dated amendments 43-CONTEXT.md D-26 specifies. Checking the box now would assert something false: 43-05's two-connection race proof is still owed under the same requirement, and APPLEHOOK-02's enumeration clause is settled in code but not yet recorded. 43-01 and 43-03 left it unchecked for the same reason and this follows them. `requirements-completed` in this summary's frontmatter is empty accordingly.

**6. `tests/schema/test_grant_locks.py` imports three names from `tests/schema/test_subscription_ingestion.py`** rather than copying a notification factory, a product id and a clean-up routine into a second module. That is 42-03's recorded rule — reuse by import, not by copy — and it keeps one spelling of the clean-up order, which is the part most likely to drift.

---

**Total deviations:** 3 auto-fixed (two Rule 1, one Rule 3), plus 3 recorded departures from the plan's letter.
**Impact on plan:** No scope creep and no new artifact beyond the plan's list. Both Rule 1 fixes were found by writing the plan's own behaviour arms as executed cases, which is what task 2 exists for; each closed a path that would have answered 500 on every Apple retry for ever.

## Verification

All four gates green at completion, quoted from the tail of each run:

| Command | Result | Baseline (after wave 2) |
|---|---|---|
| `uv run pytest -q` | **1076 passed**, 435 deselected | 1066 |
| `uv run pytest -m e2e -q` | **265 passed**, 1246 deselected | 265 |
| `uv run pytest -m schema -q` | **170 passed**, 1341 deselected | 154 |
| `uv run ruff check src tests` | **All checks passed!** | clean |

Every acceptance grep in the plan matched:

- `lock_effective_grants` precedes `lock_usage` in `crud/subscriptions.py`, and both precede every grant write: `lock_grants` is the only lock site and the writer is called after it.
- Grant `status` assignments in `crud/subscriptions.py`: one, setting `expired` or `revoked`. The two other `status` assignments in the module are `core.subscriptions.status`, read and written by `upsert_subscription`. No assignment returns a grant to `active`; the new row's `active` comes from the model default at construction.
- `session.delete` (non-comment): `0`
- `datetime.now` in `crud/subscriptions.py` (non-comment): `0`; in `services/subscriptions.py` (non-comment): `0`
- `strftime("%Y-%m")` in `crud/subscriptions.py`: `1`, the spelling `services/quota.py:54-60` and `services/sync.py:26-27` use
- `git status --porcelain -- migrations/`: empty — the migration was not edited
- `conn.execute` in `tests/schema/helpers.py`: increased by exactly two, one per new helper, every value bound with `$N`
- `tests/schema/test_subscription_ingestion.py` carries `pytestmark = pytest.mark.schema` and 12 cases

**Three controls were applied and observed, not assumed:**

1. Making `write_subscription_grant` return immediately failed 10 of the 12 ingestion cases. The two that survived are the unattributed case, which writes no grant either way, and the deferrable-foreign-key control, which does not run the writer — both correct to survive.
2. Adding a `SELECT … FROM core.subscriptions … FOR UPDATE` to `lock_grants` failed both lock-tier cases, the tier set reading `{core.access_grants, core.subscriptions, core.user_monthly_usage}`.
3. Adding a second `AccessGrant(source=AccessGrantSource.subscription)` construction site in `services/subscriptions.py` failed the one-construction-site case and the recorded-modules case.

All three mutations were reverted and each suite re-run green immediately afterwards.

## Known Stubs

None. No placeholder value was introduced. 43-01's one recorded stub — the placeholder App Store product id in `config/config.yaml` — is untouched and is still resolved by an operator edit rather than by a later plan.

## Threat Flags

None. The files this plan changed add no network endpoint, no auth path and no schema change. The one new trust boundary — a verified notification becoming an entitlement — is already in the plan's threat register as T-43-14 through T-43-18, and each `mitigate` disposition has an executed case:

| Threat | Mitigation, as executed |
|---|---|
| T-43-14 double entitlement | the same-term no-op precedes every write; the two unique indexes refuse a second active row per statement |
| T-43-15 deadlock or lost update | `GrantsDB`'s own lock methods, one spelling, asserted over the SQL the writer emits |
| T-43-17 silent free allowance | no usage row is ever minted for an existing grant; the missing row stays a detectable broken invariant |
| T-43-18 a superseded term disappearing | grants are expired, never deleted, and a tier change flips rather than updating in place |

T-43-16, a lapsed subscriber losing the free grant for ever, is `accept` and is executed as `test_the_buyers_free_grant_is_expired_and_not_deleted` — recorded rather than mitigated, per D-18.

## Issues Encountered

**Two `CHECK (ends_at > starts_at)` traps in the test seeds, both real.** A superseded grant's `ends_at` is set to the captured instant, so a seeded grant whose `starts_at` is that same instant fails the CHECK rather than being expired. Every seeded grant therefore places its term explicitly in the past, exactly as `tests/schema/test_grant_locks.py::_account_holding` already does and for the same reason. In production the two instants belong to different requests and cannot coincide.

**Nothing else.** No package was installed, no migration was touched, no dependency file was edited, and no authentication gate was reached.

## User Setup Required

None by this plan.

## Next Phase Readiness

**Ready for 43-05 and 43-06.**

- **43-05** owns the two-connection race and the wire-level oracle proof. The grant writer adds a fourth arbiter for it to exercise — `ix_access_grants_one_per_subscription` and `ix_access_grants_one_active_per_user` are both non-deferrable and per-statement, and the expire-then-flush boundary is the point a concurrent claim contends with an ingestion. `tests/schema/test_subscription_ingestion.py::_buyer` is a ready harness for a second connection to race against, and `_clean` is the FK-ordered clean-up a race case will need.
- **43-06** writes the REQUIREMENTS.md amendments. APPLEHOOK-01 stays unchecked here for the reason 43-01 and 43-03 gave. Three things this plan settled belong in that record: D-18's accepted consequence is now executable rather than described, the superseding of a `manual` grant is a consequence D-19 implies but does not state, and the entitled set is named once in `src/` as `ENTITLED_STATUSES`.

**For Phase 45 (restore).** `AccessGrantSource.subscription` now has a single-writer walk, and it will fail the moment restore constructs a second grant of that source. That is the point: restore has to come to `tests/unit/test_grant_sources.py` and change a number a reader sees, rather than becoming a second writer quietly. Restore is also the only path back to a grant for a lapsed buyer, because ingestion never reactivates one — `write_subscription_grant` sets `expired` or `revoked` and nothing else.

**For Phase 44 (Google Play).** The grant half reads nothing store-specific: it takes a `SubscriptionStatus`, a tier id and two instants. A Google notification producing the same `VerifiedNotification` reaches it unchanged.

## Self-Check: PASSED

`tests/schema/test_subscription_ingestion.py` exists on disk, all six modified files are present, and the three task commits (`d408f63`, `b037417`, `266790e`) are in `git log`.

---
*Phase: 43-post-webhooks-app-store*
*Completed: 2026-09-04*
