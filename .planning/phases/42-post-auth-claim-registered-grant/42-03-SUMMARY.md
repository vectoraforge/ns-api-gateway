---
phase: 42-post-auth-claim-registered-grant
plan: 03
subsystem: auth
tags: [tests, precedence, consumption, refusals, devicecheck, d-01, d-05, d-09, reggrant-03]
status: complete

requires:
  - "42-02 (the route, the five-arm destination decision, both writers, the e2e module this extends)"
  - "42-01 (seed_grant with no companion-row parameter)"
  - "tests/unit/test_claim_precedence.py (the stubs this plan imports rather than copies)"
provides:
  - "tests/unit/test_claim_precedence_registered.py — 28 stub-session cases over the ten post-claim outcomes and the five pre-claim rejections"
  - "The four refusals proven byte-identical on the wire, at both depths"
  - "The three Apple arms proven to leave no grant row, no usage row and a NULL free-grant marker"
  - "A standing detector for the Phase 41 loser-arm refresh defect on this route"
affects:
  - "plan 42-04 (its walks read the same writer; no file is shared)"
  - "plan 42-05 (its race classes drive the same seam; no file is shared)"

tech-stack:
  added: []
  patterns:
    - "Scaffolding imported across test modules rather than copied, so one fake conditional update exists"
    - "A stub subclassed to add a recorder, never forked to change behaviour"
    - "Precedence asserted as an order over the recorded timeline, not only as an outcome"

key-files:
  created:
    - tests/unit/test_claim_precedence_registered.py
  modified:
    - tests/e2e/test_claim_registered_grant.py

decisions:
  - "The anonymous precedence module was left byte-identical: the registered sibling imports its stubs, so no shared helper module was needed and no assertion moved"
  - "The subscription refusal seeds its own core.subscriptions row inside the test module, because seed_grant cannot carry subscription_id and tests/e2e/conftest.py is outside this plan's files"
  - "Two cases plan 42-02 left in TestTheGuardsThatWriteNothing were relocated into the two new classes rather than duplicated"

metrics:
  duration: "~10 min"
  completed: 2026-09-03
  tasks: 2
  commits: 2

actuals:
  tokens: 10924
  tasks: 2
  commits: 2
---

# Phase 42 Plan 03: The Registered Claim's Case Matrix Summary

Every outcome the registered claim can reach is now a named, executed case: ten post-claim
outcomes with the consumption count asserted per outcome, five pre-claim rejections that spend
nothing, and twelve end-to-end cases through the real router against a real database.

## What Was Built

Plan 42-02 built the branches. This plan turns each of them into a case that fails when the branch
moves.

**`tests/unit/test_claim_precedence_registered.py` (new, 28 cases, 4 test classes).** The
scaffolding is imported from `tests/unit/test_claim_precedence.py` — `_FakeChallengeStore`,
`_StubSession`, `_RecordingGrants`, `_ScriptedDeviceCheck`, `_StubSync`, `_issued_row`, `_a_grant`
and the two header constants. Nothing was copied, so one fake of the conditional update exists in
the repository and not two.

**`tests/e2e/test_claim_registered_grant.py` (extended, 6 to 12 cases).** The repeat, the four
refusals and the three Apple arms, beside the two happy-path classes plan 42-02 wrote.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | The precedence and consumption matrix, on a stub session | `f23ae95` | `tests/unit/test_claim_precedence_registered.py` |
| 2 | The end-to-end case matrix | `d199801` | `tests/e2e/test_claim_registered_grant.py` |

## Verification

| Gate | Before | After |
|------|--------|-------|
| `pytest tests/unit/test_claim_precedence_registered.py -q` | — | 28 passed, zero skipped |
| `pytest tests/unit/test_claim_precedence.py -q` | 29 collected | 29 collected, `git diff --stat` empty |
| `pytest -q` (unit) | 957 passed | 985 passed |
| `pytest -m e2e tests/e2e/test_claim_registered_grant.py -q` | 6 passed | 12 passed, zero skipped |
| `pytest -m e2e -q` | 231 passed | 237 passed |
| `pytest -m e2e tests/e2e/test_claim_anonymous_grant.py -q` | 9 passed | 9 passed, `git diff --stat` empty |
| `pytest -m schema -q` | 126 passed | 126 passed |
| `ruff check src tests` | clean | clean |
| `pytest tests/unit/test_docstring_bar.py -q` | 9 passed | 9 passed |
| `ast` ClassDef count in the new module | — | 6 (4 test classes, 2 stub subclasses) |

Commands were run as `.venv/bin/python -m pytest` and `.venv/bin/ruff`, the same interpreter
`uv run` resolves to; the plan's `uv run` spellings were not otherwise altered.

## The Ten Post-Claim Outcomes, by Node ID

Each asserts its own outcome and a consumption count of exactly one. The class is
`TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce`.

| D-09 destination | Node id | What else it asserts |
|------------------|---------|----------------------|
| `ClaimantNotRegistered` | `::test_an_anonymous_claimant_is_refused_before_any_grant_is_read` | `"read_effective_grants" not in timeline` |
| `OtherActiveGrantHeld` | `::test_an_active_grant_of_another_source_is_refused_and_still_consumes` | no writer call, no device call |
| `FreeGrantAlreadyConsumed` | `::test_a_spent_free_grant_in_history_is_refused_and_still_consumes` | no writer call, no device call |
| repeat (a) | `::test_the_repeat_answers_two_hundred_writes_nothing_and_still_consumes` | writer never called, both device lists empty |
| conversion (c) | `::test_the_conversion_reaches_the_writer_without_reaching_apple_and_still_consumes` | writer called once, both device lists empty (D-02) |
| new grant (d) | `::test_the_new_grant_reaches_the_writer_after_one_read_and_one_write` | `write_calls == [(token, False, True)]` |
| `DeviceGrantExhausted` | `::test_a_spent_device_slot_is_exhausted_and_still_consumes` | no bit write, no writer call |
| `ProofRejected` | `::test_a_token_apple_refuses_is_a_proof_rejection_that_still_consumes` | no writer call |
| `Unavailable` | `::test_an_exhausted_apple_budget_is_unavailable_and_still_consumes` | 503, no writer call |
| race loss | `::test_the_race_loser_rolls_back_answers_two_hundred_and_refreshes_nothing` | rollback taken, `refresh_calls == []` |

`TestTheConsumptionCounterIsOneForEveryPostClaimOutcome` repeats the same ten as a parametrized
setup-function table, so an eleventh outcome added later must appear in `POST_CLAIM_OUTCOMES` to
pass.

## The Three Precedence Facts, Asserted as Order

`TestThePrecedenceOrderAndNotOnlyTheOutcome` holds the facts a copy of the anonymous module would
get wrong. Both refusals answer the same 403 body, so outcome alone cannot tell them apart; the
recorded timeline is what does.

- `test_an_active_subscription_refuses_before_the_history_read_is_issued` — an active
  `subscription` and no free history answers `OtherActiveGrantHeld`, and
  `"has_prior_free_grant" not in timeline` proves the history read was never reached.
- `test_a_spent_anonymous_grant_with_no_active_grant_is_refused_by_the_history_read` —
  `"has_prior_free_grant" in timeline`, and the scripted device double recorded zero calls.
- `test_an_active_anonymous_grant_converts_even_though_both_spent_signals_are_true` — the case is
  set up with `free_grant_consumed_at` set **and** `has_prior_free_grant` true, which is what the
  conversion path really looks like (Pitfall 4). Either signal used as a blanket guard turns this
  into a 403.

## Mutation Testing — Three Mutations, All Caught

Every mutation was applied to `src/nativespeaker/api/services/auth.py` alone and reverted with
`cp` from a backup taken in the same command; `git diff --stat` on that file was empty after each
revert, and no test file was touched during the cycle.

**Mutation 1 — reintroduce the Phase 41 defect: `await self.session.refresh(identity.identity)` on
the race-loser arm.**
Result: **2 failed, 26 passed.**

| Node id | Observed failure |
|---------|------------------|
| `TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_the_race_loser_rolls_back_answers_two_hundred_and_refreshes_nothing` | the caller's rows are detached, so the refresh raised and the 200 became a 500 |
| `TestTheConsumptionCounterIsOneForEveryPostClaimOutcome::test_each_outcome_consumes_exactly_once[race_lost]` | the same 500 lost the consume |

The property was asserted rather than grepped for: `_RecordingSession` records every instance the
completion asked it to refresh, and the loser arm must record none.

**Mutation 2 — replace the history read with a blanket `free_grant_consumed_at` guard, hoisted
above the `if not held:` block.**
Result: **3 failed, 25 passed**, including
`TestThePrecedenceOrderAndNotOnlyTheOutcome::test_an_active_anonymous_grant_converts_even_though_both_spent_signals_are_true`
— the conversion this route exists to serve became a 403, which is exactly the failure REGGRANT-03
names.

**Mutation 3 — delete the `has_prior_free_grant` guard from the preflight, run against the e2e
module.**
Result: **1 failed, 11 passed** —
`TestTheFourRefusals::test_a_revoked_anonymous_grant_is_refused_by_the_history_read`. The writer's
in-lock guard still returned false, so the mutant answered 200 with no grant row rather than 403;
the case asserts the status and caught it.

## The Four Refusals, Proven Indistinguishable

Each of the four e2e cases asserts `refusal.status_code == 403`, `refusal.text == REFUSED_BODY`
(the raw bytes `{"code":"operation_not_allowed"}`) and `refusal.json() == REFUSED`. The byte
comparison is what makes the set a wire-level guarantee rather than a parsed one.

| Cause | Node id | State assertion |
|-------|---------|-----------------|
| anonymous stored provider | `::test_an_anonymous_caller_is_refused_through_the_fourth_claim_leaf` | `(0, 0)` rows |
| active `manual` grant | `::test_an_active_manual_grant_is_refused` | `(1, 1)` rows, unchanged |
| active `subscription` grant | `::test_an_active_subscription_grant_is_refused_and_is_never_converted` | the seeded grant is still the only one |
| `anonymous_device_grant` at `revoked` | `::test_a_revoked_anonymous_grant_is_refused_by_the_history_read` | the revoked row is still the only one — no registered grant beside it |

The unit matrix carries the same four refusals against the stub session, so the guarantee holds at
both depths.

## The Three Apple Arms

`TestTheThreeAppleFailureArms` — bit1 already set is 403 `device_grant_exhausted`, a refused token
is 403 `proof_rejected`, and an exhausted retry budget is 503
`verification_temporarily_unavailable`. Each asserts, afterwards: no grant row, no usage row
(`_row_counts == (0, 0)`), `free_grant_consumed_at is None` on the identity row, and a consumed
challenge. The 503 arm additionally asserts `read_calls == [DEVICE_TOKEN] * DEVICECHECK_ATTEMPTS`,
so the budget is spent rather than short-circuited.

## Deviations from Plan

### Judgement Calls Inside Claude's Discretion

**1. Reuse was by import, so the anonymous module needed no edit at all.**

The plan allowed either an import from the existing module or a small shared helper module with the
anonymous module's imports updated. The import route was taken. `git diff --stat
tests/unit/test_claim_precedence.py` is empty — not "import-line changes only", but no change
whatsoever. The two behavioural adjustments the registered route needs were made by **subclassing**,
never by forking:

- `_RecordingSession(_StubSession)` adds a `refresh_calls` recorder and delegates to `super()`, so
  the detached-row raise that pins the Phase 41 defect is still the parent's.
- `_RegisteredStubSync(_StubSync)` answers with the registered entitlement, which is what the
  new-grant case reads off the body.

The eight fixtures are defined locally rather than imported. Three of them genuinely differ (the
account is registered through Google, the recorder patches
`activate_registered_account_grant`, the sync stub is the registered one) and pytest fixtures
imported by name are fragile; the stubs those fixtures assemble are the imported ones.

**2. Two cases plan 42-02 wrote were relocated, not duplicated.**

`TestTheGuardsThatWriteNothing` held the anonymous-caller refusal, the parametrized 422 pair and the
bit1 arm. The first belongs in `TestTheFourRefusals` and the third in `TestTheThreeAppleFailureArms`;
leaving them in place would have meant two copies of each case, and the four-refusal
byte-identity guarantee cannot be stated across two classes. Both were moved verbatim, then
strengthened (the refusal gained the byte comparison; the Apple arm gained the free-grant marker
assertion). No case was deleted. Their node ids changed:

| Was | Now |
|-----|-----|
| `TestTheGuardsThatWriteNothing::test_an_anonymous_caller_is_refused_through_the_fourth_claim_leaf` | `TestTheFourRefusals::test_an_anonymous_caller_is_refused_through_the_fourth_claim_leaf` |
| `TestTheGuardsThatWriteNothing::test_a_device_whose_bit1_is_already_set_is_exhausted_and_is_never_written_to` | `TestTheThreeAppleFailureArms::test_a_device_whose_bit1_is_already_set_is_exhausted_and_is_never_written_to` |

`TestTheGuardsThatWriteNothing` keeps the 422 pair and its docstring was rewritten to state what it
now holds.

**3. The subscription refusal seeds its own subscription row.**

`core.access_grants` carries `CHECK ((source = 'subscription' AND subscription_id IS NOT NULL) OR
(source <> 'subscription' AND subscription_id IS NULL))`, and the generated column
`active_subscription_grant_subscription_id` has a foreign key into
`core.subscriptions (product_entitled_subscription_id)`. So an active subscription grant needs a
real subscription row, and `seed_grant` has no `subscription_id` parameter. There is also no Python
model for `core.subscriptions` — the table is unmapped.

`tests/e2e/conftest.py` is outside this plan's `files_modified`, and 42-04 and 42-05 run after this
plan, so a conftest edit was declined. `_seed_subscription_grant` was written inside the test module
instead: one raw `INSERT INTO core.subscriptions` through `sqlalchemy.text` with bound parameters,
then the grant and its usage row through the ORM (`AccessGrant.subscription_id` is mapped). Twenty
lines, in the one file this plan owns.

### Acceptance Criteria That Were Wrong as Written

**"The module holds four classes: the two happy paths, the repeat, the refusals and the Apple
arms."** The list has five members, and the module holds six — the sixth is
`TestTheGuardsThatWriteNothing`, which plan 42-02 created and which still holds the 422 pair. The
criterion's own enumeration contradicts its count, and deleting a class to reach four would have
lost the 422 cases. Every class the criterion names exists and holds the cases it names.

**"`uv run pytest tests/unit/test_claim_precedence_registered.py -q` passes with at least 20
collected cases."** It collects 28. The other criteria in that block were run literally and all
hold: the `ast` ClassDef count prints `6` (at least `3` required), the anonymous module collects
exactly 29 as before with an empty diff, and the docstring bar is green.

## Threat Model

| Threat ID | Disposition | Outcome |
|-----------|-------------|---------|
| T-42-03-01 | mitigate | Held. Four e2e cases assert the same status and the same raw bytes; the unit matrix carries the same four refusals against the stub session. |
| T-42-03-02 | mitigate | Held. Each of the three Apple arms asserts no grant row, no usage row and a NULL `free_grant_consumed_at` afterwards. |
| T-42-03-03 | mitigate | Held, and mutation-proven. Mutation 3 removed the history guard and the revoked-grant case failed; the unit matrix carries the same fact. |
| T-42-03-04 | mitigate | Held. Ten named cases assert a consumption count of exactly one, and the parametrized table repeats all ten. |
| T-42-03-05 | mitigate | Held. `_StubSession.exec` still refuses unstubbed queries, and the loser arm asserts the production property (`refresh_calls == []`) rather than grepping the source. Mutation 1 proves it bites. |
| T-42-SC | mitigate | Held. No package was installed, added, moved or upgraded. |

## Known Stubs

None. No stub, TODO, FIXME or placeholder was introduced, and no test is skipped or marked xfail.
Both changed files were scanned before this summary was written; every case in both modules runs.

## Threat Flags

None. This plan adds tests only. No network endpoint, auth path, file access pattern or
trust-boundary schema change was introduced, and no source file under `src/` was modified — the
three mutations were reverted and verified empty by `git diff --stat`.

## For the Next Plan

- Test counts after this plan: unit 985, schema 126, e2e 237.
- `tests/unit/test_claim_precedence.py` is unchanged and still collects 29; its stubs are now
  imported by a second module, so an edit to them affects both.
- `POST_CLAIM_OUTCOMES` in `tests/unit/test_claim_precedence_registered.py` is the table an
  eleventh destination must be added to.
- `_seed_subscription_grant` in `tests/e2e/test_claim_registered_grant.py` is the only place in the
  suite that seeds an active subscription grant, if a later plan needs one.

## Self-Check: PASSED

- `tests/unit/test_claim_precedence_registered.py` exists on disk; `tests/e2e/test_claim_registered_grant.py` exists and is modified.
- `f23ae95` and `d199801` are both present in git history.
