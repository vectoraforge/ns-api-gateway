---
phase: 42-post-auth-claim-registered-grant
plan: 04
subsystem: tests
tags: [ast-walk, single-writer, ordering, import-fence, mutation-testing, reggrant-01, reggrant-02, d-01, d-02, d-03, d-11]
status: complete

requires:
  - "42-02 (the registered writer and the registered claim these walks parse)"
  - "42-01 (the re-baselined anonymous in-writer count and the replaced near-miss literal)"
provides:
  - "TestTheRegisteredAccountGrantHasExactlyOneWriter — the REGGRANT-01 walk over today's `src/` tree"
  - "TestTheRegisteredWalkFires — the mutation control proving the registered walk is not vacuous"
  - "TestBothVendorCallsPrecedeTheRegisteredActivation — the arm-scoped order, the conversion's seam absence, and the no-lock assertion"
  - "A seam-name case over the registered writer, beside the unchanged import fence"
affects:
  - "any later plan adding a construction site for either free grant source — it must edit a literal here"

tech-stack:
  added: []
  patterns:
    - "A walk helper generalised by a defaulted argument, so the existing call sites stay byte-identical"
    - "An order asserted inside the one arm that reaches the seam, not flat over a five-arm body"
    - "Every new negative case mutation-tested before it is trusted"

key-files:
  created: []
  modified:
    - tests/unit/test_grant_sources.py
    - tests/unit/test_claim_ordering.py

decisions:
  - "Two classes rather than one parametrized pair: parametrizing would have rewritten the anonymous case bodies, which the plan forbids. The three walk helpers took a defaulted `member` argument instead, so no anonymous call site changed"
  - "The in-writer registered mention count is 2, recounted rather than copied — the in-lock repeat test and the one construction"
  - "The order is asserted as read-before-write inside the `if not held:` arm plus arm-end-before-writer-line, because the writer call sits outside the arm and a flat three-way order would not say which arm it belongs to"

metrics:
  duration: "~20 min"
  completed: 2026-09-03
  tasks: 2
  commits: 2

actuals:
  tokens: 4500
  tasks: 2
  commits: 2
---

# Phase 42 Plan 04: The Registered Walks Summary

REGGRANT-01 and the no-network-under-a-lock half of REGGRANT-02 are executable checks over the
registered claim, and each new negative case was made to fail by a mutation before it was trusted.

## What Was Built

Two test modules gained a registered half. Neither gained a behaviour.

**`tests/unit/test_grant_sources.py` (11 to 21 cases).** `TestTheRegisteredAccountGrantHasExactlyOneWriter`
walks every module under `src/` and asserts the set of modules holding an
`AccessGrant(source=AccessGrantSource.registered_account_grant)` construction is exactly
`["nativespeaker/api/crud/grants.py"]` with exactly one site in it; that the site is inside
`activate_registered_account_grant`, the function that takes both lock tiers; and that only three
modules name the member off its enum at all. `TestTheRegisteredWalkFires` is the mutation control —
a synthetic two-site module counts as two, three near-misses count as zero, and one extra case
asserts the two members do not alias each other.

**`tests/unit/test_claim_ordering.py` (9 to 15 cases).**
`TestBothVendorCallsPrecedeTheRegisteredActivation` asserts the order inside the new-grant arm, the
conversion arm's total absence of a vendor call, and that the claim takes none of the three locks.
`TestTheCrudWriterCannotReachTheVendor` gained a case over the registered writer.
`TestTheOrderAssertionFires` gained two controls.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | The registered single-writer walk, mutation-tested | `5917a82` | `tests/unit/test_grant_sources.py` |
| 2 | The ordering and import-fence proof for the registered claim | `5ae1fc5` | `tests/unit/test_claim_ordering.py` |

## Verification

| Gate | Before | After |
|------|--------|-------|
| `pytest tests/unit/test_grant_sources.py -q` | 11 passed | 21 passed |
| `pytest tests/unit/test_claim_ordering.py -q` | 9 passed | 15 passed |
| `pytest -q` (unit) | 985 passed | 1001 passed |
| `pytest -m schema tests/schema/test_grant_locks.py -q` | 15 passed | 15 passed |
| `ruff check src tests` | clean | clean |
| `test_grant_sources.py` names both members | — | `True True` |
| `test_claim_ordering.py` names both claims | — | `True True` |
| `pytest tests/unit/test_docstring_bar.py -q` | 9 passed | 9 passed |

Commands were run as `.venv/bin/python -m pytest` and `.venv/bin/ruff`, which is the same interpreter
`uv run` resolves to; the plan's `uv run` spellings were not otherwise altered.

## The Counted Numbers, Recounted Rather Than Copied

| Fact | Anonymous | Registered |
|------|-----------|------------|
| construction sites across `src/` | 1, `crud/grants.py:105` | 1, `crud/grants.py:170` |
| mentions inside its own writer | 1 | **2** — the in-lock repeat test at `:149` and the construction at `:172` |
| mentions inside the *other* writer | 1 (`:151`, the conversion's source test) | 0 |
| modules naming the member off its enum | `crud/grants.py`, `services/auth.py`, `tables/grants.py` | the same three |

The registered literal is written as `== 2` with a one-line comment naming both occurrences. Plan
42-02's forecast of `NAMING_MODULES` was four modules including `schemas/auth.py`; the walk measures
three. `schemas/auth.py` spells the member as a string value on `EntitlementType`, never off
`AccessGrantSource`, so `_names_the_member` does not see it — which 42-02's own note predicted.

## Mutation Testing — Three Mutations, All Caught

Every mutation was applied to a file under `src/` alone, never to a test file, and reverted by
copying back a backup taken in the same command. `git diff --stat` on the mutated file was empty
after each revert, and `git status --short` showed only the test file being written.

**Mutation 1 (Task 1) — a second construction site in another module.** Appended
`def _mutation_second_site(): return AccessGrant(source=AccessGrantSource.registered_account_grant)`
to `src/nativespeaker/api/services/auth.py`.

| Node id | Observed failure |
|---------|------------------|
| `TestTheRegisteredAccountGrantHasExactlyOneWriter::test_the_whole_tree_holds_exactly_one_construction_site` | `AssertionError: assert ['nativespeak...ices/auth.py'] == ['nativespeak...ud/grants.py']` / `Left contains one more item: 'nativespeaker/api/services/auth.py'` |

**Mutation 2 (Task 1) — the site moved out of the writer, staying in the same module.** The
`AccessGrant(...)` construction inside `activate_registered_account_grant` was replaced by a call to
a new module-level `_mutation_build(...)` holding it. Result: **1 failed, 3 passed** — the
whole-tree case stayed green, which is the point of having the second case.

| Node id | Observed failure |
|---------|------------------|
| `TestTheRegisteredAccountGrantHasExactlyOneWriter::test_the_one_site_is_inside_the_crud_activation_writer` | `assert 1 == 2` |

**Mutation 3 (Task 2) — the device write moved below the writer call.** The
`write_bits_with_retry(...)` line was deleted from inside the `if not held:` arm of
`_claim_registered_grant` and re-inserted after the `activate_registered_account_grant(...)` call, at
function level. Result: **2 failed, 13 passed**.

| Node id | Observed failure |
|---------|------------------|
| `TestBothVendorCallsPrecedeTheRegisteredActivation::test_the_read_and_the_write_both_precede_the_writer_on_the_new_grant_arm` | `AssertionError: write_bits_with_retry is not called at all` / `assert 'write_bits_with_retry' in ['has_prior_free_grant', 'read_bits_with_retry', 'DeviceGrantExhausted']` |
| `TestBothVendorCallsPrecedeTheRegisteredActivation::test_the_conversion_arm_reaches_neither_seam_function` | `AssertionError: assert {'write_bits_with_retry'} == set()` / `Extra items in the left set: 'write_bits_with_retry'` |

That second failure is the one worth reading: moving the write below the writer does not only break
the order, it puts a vendor call on the conversion path, which D-02 says makes no Apple call at all.
One mutation, two independent properties, both named.

## Why Two Classes and Not One Parametrized Pair

The plan allowed either, on the condition that the anonymous cases' assertions stay byte-identical.
Parametrizing would have added an argument to every anonymous case body, so a second class was
written. The three walk helpers — `_construction_sites`, `_names_the_member` and `_mentions` — each
took a `member: str = MEMBER` default instead. `git diff -U0` on the file removes ten lines: the
three-line module docstring, and the seven signature and body lines of those helpers. **No assertion
line of any anonymous case appears in the removed set.** The same holds for
`tests/unit/test_claim_ordering.py`, where the only removed lines are the three of the module
docstring.

`FREE_GRANT_SOURCES` and its two-member assertion were not touched, and
`tests/schema/test_grant_locks.py` is green at 15 — the constant is still bound to the live index
predicate.

## The Ordering Assertion's Shape, and Why It Is Not Flat

The anonymous claim has one arm, so a flat `read < write < activate` over the whole body is exact
there. `_claim_registered_grant` has five arms and only the `if not held:` block reaches Apple, so a
flat order would be true of a body where the write had drifted onto the conversion path. The
registered case therefore asserts two things: `read < write` **within the arm**, and
`arm.end_lineno < _call_line(claim, WRITER_REGISTERED)` — the writer runs past the arm's close. The
conversion is then covered by its own case, which takes the claim's calls minus the arm's and
asserts neither seam name is among them, with `activate_registered_account_grant` asserted present so
the empty intersection is not empty by accident.

`_new_grant_arm` raises a named `AssertionError` when the guard is renamed, rather than returning
nothing and letting the cases pass over an empty arm;
`test_a_body_without_the_new_grant_arm_is_reported_rather_than_passed` pins that.

## The Import Fence, Unchanged

`ALLOWED_IMPORT_ROOTS` still holds five members — `datetime`, `uuid`, `sqlalchemy`, `sqlmodel`,
`nativespeaker`. The registered writer added no root, so the literal did not grow. The subprocess
case that proves no HTTP client is transitively importable from `nativespeaker.api.crud.grants` is
byte-identical and green.

## Deviations from Plan

None. Both tasks were executed as written. Two points are worth stating exactly rather than as
deviations:

- **The plan's proposed near-miss replacement was already done.** The action said one near-miss
  source names a table plan 42-01 deleted, and to leave it alone if 42-01 had replaced it. 42-01 had:
  the `another_table_same_member` case already names `UserMonthlyUsage`. The registered control uses
  the same three near-misses with the registered member.
- **A fourth case was added to the registered walk class** beyond the two the plan names —
  `test_the_writer_is_reachable_as_a_method_rather_than_a_free_function`, the sibling of the
  anonymous control at `:103`. Without it, a renamed writer would make `_function` raise inside the
  in-writer case rather than fail as a missing method, which reads worse.

## Threat Model

| Threat ID | Disposition | Outcome |
|-----------|-------------|---------|
| T-42-04-01 | mitigate | Held, and mutation-proven twice. Mutation 1 (a second site elsewhere) and mutation 2 (a misplaced site in the right module) each failed a different named case. |
| T-42-04-02 | mitigate | Held. Mutation 3 failed both the arm-scoped order case and the conversion's seam-absence case; the claim is asserted to take none of the three locks, and the subprocess import fence is green and unchanged. |
| T-42-04-03 | mitigate | Held. All three mutations, their failing node ids and their observed messages are recorded above; the mutation control class was copied and extended, and one extra case proves the two members do not alias. |
| T-42-04-04 | mitigate | Held. The two-member assertion over `FREE_GRANT_SOURCES` is byte-identical, and `pytest -m schema tests/schema/test_grant_locks.py -q` is green at 15. |
| T-42-SC | mitigate | Held. No package was installed, added, moved or upgraded. |

## Known Stubs

None. No stub, TODO, FIXME or placeholder was introduced, and no test is skipped or marked xfail.
Both changed files were scanned before this summary was written; every case in both modules runs.

## Threat Flags

None. This plan adds tests only. No network endpoint, auth path, file access pattern or
trust-boundary schema change was introduced, and no file under `src/` is modified — all three
mutations were reverted and verified empty by `git diff --stat`.

## For the Next Plan

- Test counts after this plan: unit 1001, schema 126, e2e 237.
- `tests/unit/test_claim_ordering.py` and `tests/unit/test_grant_sources.py` are not touched by
  42-05, which owns `tests/schema/test_claim_race.py` alone.
- A new construction site for either free grant source now requires an edit to a literal in
  `tests/unit/test_grant_sources.py`, which is the point of the walk.
- `_new_grant_arm` keys on the guard name `held` in `_claim_registered_grant`; renaming that local
  fails a named case rather than silently emptying the arm.

## Self-Check: PASSED

- `tests/unit/test_grant_sources.py` and `tests/unit/test_claim_ordering.py` both exist on disk and
  are modified.
- `5917a82` and `5ae1fc5` are both present in git history.
