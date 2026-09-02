---
phase: 40-post-auth-upgrade-anonymous
plan: 05
subsystem: auth
tags: [fastapi, sqlmodel, postgres, challenge, firebase, case-matrix, idempotence]

# Dependency graph
requires:
  - phase: 40-02
    provides: "`ProviderTransitionNotAllowed` and `ProviderAccountAlreadyLinked` under `UpgradeRefused`, and `NotLinked`'s `stage`/`cause` pair"
  - phase: 40-03
    provides: "the e2e file and the scripted-fake fixtures these four cases drive"
  - phase: 40-04
    provides: "`_complete`'s two seams, `_apply_upgrade`'s placeholder raise, `lock_identity_and_user` and `flip_provider`"
provides:
  - "the complete case matrix in `_apply_upgrade`: the flip, D-04's idempotent no-op, `NotLinked(cause=\"empty\")`, and the drift refusal, with no combination falling through"
  - "the `stage` literal `upgrade_confirmation` and this repository's only producer of `NotLinked(cause=\"empty\")`"
  - "`tests/unit/test_upgrade_precedence.py` — the case matrix, the rejection precedence, the per-branch handle disposition and the one-read-per-completion measurement"
  - "the four scripted-fake e2e cases the real Google account cannot produce on demand"
  - "`flip_provider`'s conflict arm raising from a value read before the flush, so the already-taken refusal is a 403 rather than a 500"
affects: [40-06, 40-07, 40-08, 41-claim-anonymous-grant, 42-claim-registered-grant]

# Actuals (#2632) — same estimateTokens scale (chars/4) as the plan's estimate.
actuals:
  tokens: 9296
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A case matrix written as three guard clauses and a fall-through, ordered so the earlier guard owns the overlap rather than nesting to disambiguate it"
    - "Every value a conflict arm needs is read before the statement that can fail: a failed flush expires the ORM row, so reading it inside the `except` re-queries a dead transaction"
    - "A crud call replaced by a recording callable set on the class, so a service's own branching is exercised without a database"

key-files:
  created:
    - tests/unit/test_upgrade_precedence.py
  modified:
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/crud/identities.py
    - tests/e2e/test_upgrade_anonymous.py

key-decisions:
  - "The stage literal is `upgrade_confirmation` — not one of the three existing stages, because the classifier succeeded and reusing `provider_classification` would read in the log as a classifier failure"
  - "The matrix is three flat guards, and the both-anonymous guard is first because a stored-anonymous row and a live anonymous read also satisfy the idempotent guard's equality test"
  - "`flip_provider` now captures `identity_row.id` beside `stored_provider`, before any assignment: reading it inside the `except IntegrityError` turned the already-taken 403 into an unhandled 500 against a real database"

patterns-established:
  - "The upgrade case matrix is closed over two inputs plus one uid comparison; phases 41 and 42 add a completion by writing a `Write` seam, not by extending this matrix"

requirements-completed: [UPGRADE-01, UPGRADE-02]

coverage:
  - id: D1
    description: "A live anonymous read against a stored anonymous row refuses with `NotLinked(stage=\"upgrade_confirmation\", cause=\"empty\")`, 403 with the one-field body, and nothing is written"
    requirement: "UPGRADE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestTheUpgradeCaseMatrix::test_a_live_anonymous_read_against_a_stored_anonymous_row_is_not_linked"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheRefusalsAndTheRepeat::test_a_live_anonymous_read_refuses_and_leaves_the_row_untouched"
        status: pass
    human_judgment: false
  - id: D2
    description: "A repeat call that changes nothing answers identically to the call that performed the flip — 200 with the same one-field body, and no write is issued"
    requirement: "UPGRADE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestTheUpgradeCaseMatrix::test_the_same_provider_and_the_same_uid_is_the_idempotent_repeat"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheRefusalsAndTheRepeat::test_the_repeat_that_changes_nothing_answers_as_the_flip_did"
        status: pass
    human_judgment: false
  - id: D3
    description: "A registered stored row whose live read disagrees — different uid, different provider, or anonymous — refuses as `ProviderTransitionNotAllowed` and nothing is rewritten"
    requirement: "UPGRADE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestTheUpgradeCaseMatrix (three cases, each asserting the stored provider and uid afterwards)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheRefusalsAndTheRepeat::test_a_diverged_binding_is_refused_rather_than_rewritten (binding read before and after, compared by equality)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A target provider-account triple another identity row holds refuses as `ProviderAccountAlreadyLinked`, raised from the write's conflict arm rather than a pre-flight lookup, and the handle is spent"
    requirement: "UPGRADE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestTheUpgradeCaseMatrix::test_a_target_triple_another_row_holds_is_raised_by_the_write (one flip attempt recorded)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheRefusalsAndTheRepeat::test_a_provider_account_another_row_holds_is_refused_and_spends_the_handle (genuinely pre-reserved triple)"
        status: pass
    human_judgment: false
  - id: D5
    description: "All three refusals answer one identical 403 body and are told apart only by the structured-log event name"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestTheUpgradeCaseMatrix::test_the_three_refusals_are_three_log_events_and_one_client_answer"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every outcome at or after the Firebase call spends the handle including the not-linked refusal; rejections before it neither claim nor consume nor read the provider"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestTheRejectionsThatSpendNothing and #TestEveryOutcomeAtOrAfterTheProviderCallSpends"
        status: pass
    human_judgment: false
  - id: D7
    description: "Exactly one providerData read happens per completion, including the idempotent repeat that changes nothing"
    requirement: "UPGRADE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestOneProviderReadPerCompletion (two cases)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheRefusalsAndTheRepeat::test_the_repeat_that_changes_nothing_answers_as_the_flip_did (call list equals the completion count)"
        status: pass
    human_judgment: false

# Metrics
duration: 32min
completed: 2026-09-02
status: complete
---

# Phase 40 Plan 05: The Rest of the Case Matrix Summary

**Every combination of the stored row and the live read now reaches a named outcome: the flip, D-04's idempotent 200, and three refusals that are one answer to the client and three records in the log.**

## Performance

- **Duration:** ~32 min
- **Completed:** 2026-09-02
- **Tasks:** 3
- **Files modified:** 4 (one created)

## Accomplishments

- `_apply_upgrade` is now three flat guard clauses and a fall-through, over two inputs plus one uid comparison. The placeholder is gone and no combination falls through.
- The **called-too-early** refusal raises `NotLinked(stage="upgrade_confirmation", cause="empty")` — this repository's only producer of that cause, which P-03 flagged as having none.
- The **idempotent repeat** returns the *stored* provider and issues no write at all, which the shared sequence already supported because 40-04 made `_complete` return the seam's value rather than `facts.provider`.
- The **drift** arms keep the class 40-04 gave them; this plan split the condition, not the class. The uid comparison is the whole split.
- The **already-taken** conflict is still raised only from `flip_provider`'s `IntegrityError` arm. No pre-flight lookup was added, no constraint name is compared and no message is parsed.
- `tests/unit/test_upgrade_precedence.py` is new: 18 cases over the case matrix, the five rejections that spend nothing, the per-branch handle disposition, and the one-read-per-completion measurement.
- The e2e file gained the four cases the real Google account cannot produce on demand, each driven end to end through the real router against the scripted seam.
- **A real bug fell out of the last of those.** See "Deviations".

## Task Commits

1. **Task 1 (RED): the three wrongly answered combinations, as failing cases** — `a484e46`
2. **Task 1 (GREEN): the complete case matrix** — `874bdb8`
3. **Task 2: the precedence and consumption-disposition cases** — `529da93`
4. **Task 3: the four scripted-fake e2e cases, and the conflict-arm fix they exposed** — `653c229`

The RED run failed on exactly the three combinations 40-04's summary and `WINDOWS.md` entry 11 named — `(anonymous, anonymous)`, and same-provider-same-uid — and the four drift cases passed unchanged, confirming that the branch's class was already right for them.

## Files Created/Modified

- `src/nativespeaker/api/services/auth.py` — the `NotLinked` import and the three-guard matrix replacing the placeholder raise
- `src/nativespeaker/api/crud/identities.py` — one captured local and its one-line comment, so the conflict arm reads no ORM attribute (see Deviations)
- `tests/unit/test_upgrade_precedence.py` — new; the scaffolding copied from `test_create_user_precedence.py`, plus `_RecordingUpgrade`, and four test classes
- `tests/e2e/test_upgrade_anonymous.py` — the shared refusal body, four helpers, and `TestTheRefusalsAndTheRepeat`

## The chosen `stage` literal, and why it is not one of the existing three

`upgrade_confirmation`. The three that exist are `issuer_selection`, `provider_lookup` and `provider_classification`, all raised inside `auth/firebase.py`. This rejection is raised *after* the read has completed and the classifier has **succeeded** — the classifier's verdict is `anonymous`, which is a valid answer, not a failure. Logging it under `provider_classification` would tell an operator the classifier failed and send them to `_resolve_provider`, which is the one place the cause did not come from. `upgrade_confirmation` names the decision point that actually rejected: the upgrade asked the live read to confirm a provider account and it confirmed none.

## Which cases assert what (Task 2's acceptance criterion, stated per case)

**Pre-claim — every one asserts `fake_firebase_adapter.calls == []`, which is what proves the rejection preceded the provider call:**

| Case | Internal result | Claimed | Consumed |
|---|---|---|---|
| unknown handle | `challenge_not_found` | n/a | `consume_calls == 0` |
| bound to another identity row | `challenge_identity_mismatch` | no | `consume_calls == 0` |
| issued for another operation | `challenge_operation_mismatch` | no | `consume_calls == 0` |
| expired | `challenge_expired` | no | `consume_calls == 0` |
| already consumed | `challenge_consumed` | holder's claim untouched | `consume_calls == 0` |

**At or after the provider call — every one asserts `consumed_at is not None` and `consume_calls == 1`:**

| Case | Client answer | Internal result | Wrote? |
|---|---|---|---|
| provider reports the user is gone | 401 `auth_required` | `user_not_found` | no |
| live anonymous vs stored anonymous | 403 `operation_not_allowed` | `not_linked` | no |
| the flip | 200 `{identity_provider}` | — | one flip |

## Decisions Made

- **The both-anonymous guard runs first, and that ordering is load-bearing.** A stored-anonymous row and a live anonymous read satisfy the idempotent guard's test too (`stored is facts.provider` and `None == None`), so the two guards overlap. Ordering resolves it in three flat statements; disambiguating inside the idempotent guard would have needed a nested condition for no gain. A comment on the guard says so, because the ordering is invisible otherwise.
- **The drift guard is written as "stored is not anonymous", not as an enumeration of the disagreements.** By the time control reaches it, agreement has already returned and both-anonymous has already raised, so every survivor with a registered stored row *is* a disagreement. Enumerating them would add a fourth thing to keep in sync with the enum.
- **Task 2's cycle collapsed to one commit.** Its subject is the shared sequence 40-04 built and the matrix Task 1 completed; there was no implementation step left to write, so the RED/GREEN pair would have been RED-that-passes. All 12 of its cases passed on their first run, which is the honest outcome for characterisation tests written after their subject — and is itself the assertion that 40-04's precedence survived Task 1's edit untouched.
- **The unit file stubs the two crud calls rather than the whole write seam.** Stubbing `_apply_upgrade` would have left the matrix — this plan's entire subject — untested at that layer. `lock_identity_and_user` and `flip_provider` are replaced by recorders set on `IdentitiesDB`, so `_apply_upgrade`'s own branching runs for real with no database.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The already-taken conflict answered 500, not 403, against a real database**

- **Found during:** Task 3, by the already-taken e2e case — the first time that arm had ever run against PostgreSQL.
- **Issue:** `flip_provider`'s `except IntegrityError` arm passed `identity_row.id` to `ProviderAccountAlreadyLinked`. A failed flush expires the instance, so that attribute access triggered a lazy refresh, which issued a SELECT on a session SQLAlchemy had already marked pending-rollback. The `PendingRollbackError` escaped as an unhandled 500, and the handle was never spent — so the refusal was both the wrong answer and a replayable one.
- **Why the unit case could not catch it:** its recorder raises the class directly, so no expiry ever happens. Only a real flush against a real index reaches the bug, which is exactly why D-19 assigns this case to the fake-driven e2e layer.
- **Fix:** capture `identity_row.id` into a local beside `stored_provider`, before the first assignment, and raise from the local. Two lines, and the same reasoning 40-04 already applied to `stored_provider` — that capture existed because the assignment overwrites it; this one exists because the failure expires it.
- **Files modified:** `src/nativespeaker/api/crud/identities.py`
- **Commit:** `653c229`
- **Scope note:** `crud/identities.py` is not in this plan's `files_modified`. It is not owned by the parallel plan 40-06 (`routers/auth.py`), and the fix is confined to the arm this plan's own acceptance criteria require to work. `insert_account`'s arm is unaffected — it raises `IdentityAlreadyLinked()` with no arguments and reads nothing.

### Scoping notes

- **Task 1's tests live in `tests/unit/test_upgrade_precedence.py`,** which Task 1 lists only `services/auth.py` under `<files>`. The task is `tdd="true"` and its seven behaviours are test behaviours, so they need a file; the plan's own `files_modified` declares that path, and Task 2 then extends the same file rather than creating it. No file outside `files_modified` plus the fix above was touched.
- **`.env` was copied into the worktree** because it is gitignored and the worktree was created without it; neither the e2e suite nor any database-backed verification runs without it. Never staged, never committed, never printed. `git status --short` shows only `.planning/WINDOWS.md` at the final commit.

## Issues Encountered

Only the one above, and it was found the way the plan intended — by a case that drives the conflict through a genuinely pre-reserved triple rather than a simulated error. Had the already-taken case been written against a scripted exception at the e2e layer too, this bug would have shipped.

## Verification

| Gate | Result |
|---|---|
| `uv run pytest -q` | **841 passed**, 331 deselected (823 before this plan) |
| `uv run pytest tests/unit/test_upgrade_precedence.py -q` | **18 passed** (≥ 9 required) |
| `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q` | **8 passed, 0 skipped** (4 before this plan) |
| `uv run pytest -m e2e -q` | 214 passed (210 before) |
| `uv run pytest -m schema -q` | 117 passed |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed — the bar holds at 0 on every root |
| `grep -c "NotImplementedError" src/.../services/auth.py` | `0` |
| `grep -c 'cause="empty"' src/.../services/auth.py` | `1` |
| `grep -rn 'cause="empty"' src/` | one site, the only producer in the tree |
| `grep -c "logger.warning" src/.../services/auth.py` | `0` |
| `grep -in "for update\|begin_nested\|advisory\|serializable" src/.../services/auth.py` | nothing |
| `git diff --diff-filter=D` on every commit | no deletions |

## Known Stubs

None. `WINDOWS.md` entry 11 — the placeholder raise this plan owned — is now `fixed`, closed through `gsd-tools query windows fixed 11`. No hardcoded empty collection, no placeholder text, no unwired data source, no skipped test and no unrun `<verify>`.

## Threat Flags

None new. The register's six entries stand, and three of them are now measured rather than argued:

- **T-40-05-01 (distinguishable refusals).** All three carry the 403 declared once on `UpgradeRefused`/`NotLinked`, and both the unit control case and every e2e refusal assert the body by `==` against `{"code": "operation_not_allowed"}`.
- **T-40-05-02 (challenge replay to probe provider state).** Asserted per branch, not assumed: the three at-or-after cases each assert `consumed_at is not None` and `consume_calls == 1`, and the five pre-claim cases each assert `consume_calls == 0` and an empty provider call list.
- **T-40-05-03 (diverged binding).** The drift e2e case reads the stored provider and uid before and after and compares by equality, so an auto-rewrite fails a test.
- **T-40-05-04 (claiming another user's provider account).** Driven through a genuinely pre-reserved triple — which is what exposed the 500 above. Now a 403 with the handle spent.
- **T-40-05-05 (unbounded provider lookups).** Accepted, unchanged, and now measured: `TestOneProviderReadPerCompletion` records one read per completion including the repeat that writes nothing. 40-08 records it in `REQUIREMENTS.md`.
- **T-40-05-SC (package installs).** Unreachable — nothing installed, `pyproject.toml` untouched.

## User Setup Required

None.

## Next Phase Readiness

- **40-06** is unaffected: `routers/auth.py` was not touched, and its `_NOT_ISSUABLE` restatement is still entirely its own.
- **40-07** inherits a schema-level invariant that is now written by exactly one method with a conflict arm proven against the real index.
- **40-08** should note in the `REQUIREMENTS.md` amendment that the accepted D-22 exposure is measured, not merely asserted, and that `upgrade_confirmation` joins the stage vocabulary.
- **41 and 42** still add a completion by writing one `Write` seam and one one-line caller. Nothing in `_complete` changed in this plan.

---
*Phase: 40-post-auth-upgrade-anonymous*
*Completed: 2026-09-02*

## Self-Check: PASSED

- `.planning/phases/40-post-auth-upgrade-anonymous/40-05-SUMMARY.md` — FOUND
- `tests/unit/test_upgrade_precedence.py`, `tests/e2e/test_upgrade_anonymous.py`, `src/nativespeaker/api/services/auth.py`, `src/nativespeaker/api/crud/identities.py` — all FOUND
- Commits `a484e46`, `874bdb8`, `529da93`, `653c229` — all FOUND in `git log`
- `src/nativespeaker/api/routers/auth.py` last written by `1f7a426` (plan 40-04) — not modified by this plan, as the parallel dispatch required
- `.env` present in the worktree, gitignored, and absent from every commit; working tree clean
