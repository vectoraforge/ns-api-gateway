---
phase: 40-post-auth-upgrade-anonymous
plan: 06
subsystem: auth
tags: [fastapi, challenge, authorization, enum, tests]

# Dependency graph
requires:
  - phase: 40-01
    provides: "`AuthOperation` shrunk to its four challenge-bearing labels, so both the membership test and the derived parametrizations are complete without a written list"
  - phase: 40-04
    provides: "the membership test `body.operation not in AuthOperation` and the enum-valued `operation=` argument this plan builds the account check on top of"
provides:
  - "the issuance handler's final shape: membership first, then D-10's account-less condition, then issuance"
  - "`tests/unit/test_challenge_endpoint.py` restated against the four-value vocabulary, with a linked-caller fixture beside the account-less one"
  - "the AST control asserting the router module declares no module-level collection of operation names"
affects: [40-07, 40-08, 41-claim-anonymous-grant, 42-claim-registered-grant]

# Actuals (#2632) — same estimateTokens scale (chars/4) as the plan's estimate.
actuals:
  tokens: 4182
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "An authorization rule stated as one derived condition over the identity, never as a per-operation admission table"
    - "Refusal order is contract: the cheaper, vocabulary-level refusal runs first so a narrower refusal cannot confirm which inputs are real"
    - "A test parametrization derived from the enum it is about, so the test cannot disagree with the type"
    - "An AST control asserting the absence of a second enumeration, rather than a comment asking future readers not to add one"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/routers/auth.py
    - tests/unit/test_challenge_endpoint.py

key-decisions:
  - "The condition is `body.operation != AuthOperation.create_user and identity.identity is None` — one expression, in the handler, reusing `PreAuthIdentityNotAllowed`. No new class, no new error code, no table, no route metadata."
  - "The membership test keeps running first. Reversing the two would make the 403 confirm that a string is a real operation name, which is the disclosure T-40-06-02 exists to stop."
  - "The positive parametrization moved to a new `linked_client` fixture. The file's only fixture was account-less, so leaving the four-operation positive case on it would have made D-10's rule and the issuance case contradict each other."
  - "`_NOT_ISSUABLE` was renamed `_OUTSIDE_THE_VOCABULARY` rather than kept. Its name asserted the old seven-value premise as loudly as its comment did; every string it held survives as a case."

patterns-established:
  - "Two caller fixtures built from one factory — `client` (no identity row) and `linked_client` (identity row and user) — so every case in the file states which caller it is about"

requirements-completed: []

coverage:
  - id: D1
    description: "Every one of the four challenge-bearing operations issues for a linked caller, with the store receiving the enum member rather than the caller's string"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheIssuableOperations::test_a_member_of_the_vocabulary_is_issued_with_the_two_field_body (4 cases, parametrized off AuthOperation)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A caller with no account row prepares create-user and is refused 403 preauth_identity_not_allowed for each of the other three, with the store never asked to issue"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheAccountLessCallerPreparesCreateUserAndNothingElse"
        status: pass
    human_judgment: false
  - id: D3
    description: "A string outside the enum is 400 invalid_request for the account-less and the linked caller alike, so the refusal order discloses nothing about the vocabulary"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheRefusalOrderDisclosesNothing (7 cases, both callers each)"
        status: pass
    human_judgment: false
  - id: D4
    description: "No second enumeration of the issuable set exists: the router module declares no module-level list, set, dict or tuple"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheIssuableSetIsTheEnumAndNothingElse"
        status: pass
      - kind: other
        ref: "the plan's AST one-liner over routers/auth.py prints []"
        status: pass
    human_judgment: false

# Metrics
duration: 24min
completed: 2026-09-02
status: complete
---

# Phase 40 Plan 06: The Issuance Handler's Final Shape Summary

**`/auth/challenge` now issues for all four challenge-bearing operations, answers everything outside the enum with one indistinguishable 400 regardless of who asked, and lets a caller holding no account row prepare create-user and nothing else — by a single derived condition with no list anywhere behind it.**

## Performance

- **Duration:** ~24 min
- **Completed:** 2026-09-02
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **D-10 is three lines in the handler**: one comment, one condition, one raise, placed between the membership test and the issue call. It reuses `PreAuthIdentityNotAllowed` (`errors.py:304-307`) exactly as the plan required — no class was declared, no error code was added, and the rejected-operation log line, the `no-store` response block and both pre-existing comments are byte-identical to what 40-04 left.
- **The order is the security property, and it is now tested as one.** The membership test runs first, so `nope` and `sync` earn the same 400 for a caller with an account and a caller without. `TestTheRefusalOrderDisclosesNothing` posts each of the seven outside-the-vocabulary strings through *both* client fixtures in the same case and asserts both refusals, which is what makes the ordering a fact rather than an incidental property of how the function happens to read.
- **The file's premise was restated, not patched.** Three things had become false after the enum shrink and are now true: the module docstring (which claimed one refusal bucket, when there are now two — the 400 for the vocabulary and the 403 for the caller), the comment above the not-issuable list ("members of the operation vocabulary whose phases are unbuilt" — there are no unbuilt members left), and the class docstring resting on the unbuilt-versus-invented distinction that no longer has a subject. All seven strings survive as cases; the list is now `_OUTSIDE_THE_VOCABULARY`, which is what it holds.
- **Two caller fixtures out of one factory.** The file previously had exactly one client, and it was account-less — which is why the four-operation positive parametrization 40-04 added would have contradicted D-10 the moment the condition landed. `_client_for` builds the app once and `client` / `linked_client` supply the two identities, so every case in the file now names the caller it is about.
- **The absence of a second list is asserted, not requested.** `TestTheIssuableSetIsTheEnumAndNothingElse` parses the router module and asserts it declares no module-level `List`, `Set`, `Dict` or `Tuple`. D-10 rejected three ways of writing that list down; this is the test that notices if a fourth is invented.

## Task Commits

1. **Task 1 (TDD RED): failing tests for the account-less condition** — `5836908`
2. **Task 1 (TDD GREEN): the derived condition in the issuance handler** — `1d1d68a`
3. **Task 2: restate the test file against the four-value vocabulary** — `0e4f7d5`

RED failed with exactly the three intended cases (`upgrade_anonymous_to_registered`, `claim_anonymous_grant`, `claim_registered_grant` each `assert 200 == 403`) and 38 passing, so the gate proved the condition absent before it was written. No REFACTOR commit: the GREEN change is three lines and had nothing to clean up.

## Files Created/Modified

- `src/nativespeaker/api/routers/auth.py` — the `PreAuthIdentityNotAllowed` import and D-10's condition with its one-line comment, inserted between the membership test and the `challenge_store.issue` call
- `tests/unit/test_challenge_endpoint.py` — the module docstring; `_client_for` plus the `client` and `linked_client` fixtures; `_assert_preauth_refused`; `_EVERY_OPERATION` and `_BEYOND_CREATE_USER`; the widened issued-operations assertion; `_OUTSIDE_THE_VOCABULARY` and its rewritten comment and class docstring; the 403 arm in `TestEveryRefusalLeavesNothingBehind`; and the three new classes

## The condition, verbatim

```python
    # Create-user is the only operation an account-less caller may prepare, because it is the only route it reaches.
    if body.operation != AuthOperation.create_user and identity.identity is None:
        raise PreAuthIdentityNotAllowed
```

`identity.identity` is the attribute that is `None` for a caller with no account — `Identity` carries both `user` and `identity` as `| None`, and `get_linked_identity` is the dependency that narrows on it elsewhere. The comment states the reason the rule stays correct for Phases 41 and 42 without anyone touching it, which is the fact `tests/unit/test_app_wiring.py::PREAUTH_CALLABLE_PATHS` already pins.

## Decisions Made

- **The condition tests `identity.identity`, not `identity.user`.** Both are `None` together for an unlinked caller, so either would pass every test in the file. `identity.identity` is the one the rest of the application already treats as the account-existence signal — `PreAuthIdentityNotAllowed`'s own docstring is "a verified pair that matched no identity row" — so the condition and the exception it raises are about the same thing.
- **`!=` against the enum member rather than against `.value`.** `AuthOperation` is a `StrEnum`, so `body.operation != AuthOperation.create_user` compares the caller's string to the member directly. The alternative (`.value`) reads as though the member were not already a string and invites the same `.value` to be sprinkled through the membership test beside it, which 40-04 deliberately does not do.
- **The `TestEveryRefusalLeavesNothingBehind` 403 arm is `_BEYOND_CREATE_USER[0]`, not a literal.** That class asserts the stronger property — nothing issued, no statement executed, no provider call — and the 403 arm needed to be in it. Writing the operation name in would have restated the vocabulary in the one file whose whole point is not to; indexing the derived list keeps the acceptance criterion (`grep -c "upgrade_anonymous_to_registered"` → `0`) true for the right reason rather than by accident.
- **`_NOT_ISSUABLE` was renamed.** The plan asked for the comment and the class docstring; the identifier asserted the same stale premise, since three of the strings in it are perfectly issuable-looking former members and "not issuable" was the framing that made them look like a coherent group. `_OUTSIDE_THE_VOCABULARY` says the one thing they share.

## Deviations from Plan

Two, both about the plan's acceptance criteria rather than its instructions. No code deviation.

**1. [Rule 3 - Blocking] `.env` had to be copied into the worktree.**
- **Found during:** setup, before Task 1
- **Issue:** `.env` is gitignored, so the worktree was created without it; the e2e and schema suites cannot connect without the `DB_*` values.
- **Fix:** copied from the main checkout as the dispatch directed.
- **Files modified:** none tracked — never staged, never committed, and `git status --short` is empty at all three commits.

**2. Task 1's `grep -c "no-store"` criterion reads `1`; the true count is `2`, before and after.**
- **Found during:** Task 1 verification
- **Issue:** two lines in `routers/auth.py` contain the string — the explanatory comment (``# `no-store` rather than `no-cache`…``) and the header itself — and `grep -c` counts lines, not occurrences. The criterion's literal was written against a count that was already wrong.
- **Resolution:** verified the invariant the criterion is actually about instead. `git show HEAD:…/routers/auth.py | grep -c "no-store"` returned `2` before the change and returns `2` after, so the response block is provably unchanged. No file was edited to satisfy the literal — doing so would have meant deleting a correct comment to make a stale number true.

**Note on Task 2's `claim_anonymous_grant` criterion.** The criterion is "a non-zero count, and that operation appears only among the issuable cases." Collection yields 3 cases naming it: the issuance case, the linked-caller issuance case in the D-10 class, and the D-10 account-less refusal. `grep -n "claim_anonymous_grant" tests/unit/test_challenge_endpoint.py` returns **nothing** — the string is written nowhere in the file and all three ids are derived from the enum. The refusal case is about the *caller*, not the vocabulary: the operation is issuable, and that case is what proves the caller is not entitled to it. The criterion's target — Pitfall 5's concern that `claim_anonymous_grant` was sitting in the not-issuable list — is satisfied absolutely, since that list contains no enum member at all.

## Issues Encountered

One, caught and fixed inside Task 2: the rewritten module docstring wrapped to four lines and tripped `test_docstring_bar.py`'s `tests/unit` baseline of 0. Rewritten to three. The bar is the gate working exactly as intended — it caught the regression in the same run that introduced it, before the commit.

## Verification

| Gate | Result |
|---|---|
| `uv run pytest tests/unit/test_challenge_endpoint.py -q` | **42 passed** — **26 before this plan** (strictly more, as required) |
| `uv run pytest -q` | **839 passed**, 327 deselected — 823 before this plan |
| `uv run pytest -m e2e -q` | 210 passed, 956 deselected |
| `uv run pytest -m schema -q` | 117 passed, 1049 deselected |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed — the bar holds at 0 on every root |
| `grep -c "PreAuthIdentityNotAllowed" src/…/routers/auth.py` | `2` (the import and the raise) — at least 1, as required |
| `grep -c "no-store" src/…/routers/auth.py` | `2`, identical to `git show HEAD:` before the change |
| AST module-level collection check over `routers/auth.py` | `[]` |
| `grep -c "upgrade_anonymous_to_registered" tests/unit/test_challenge_endpoint.py` | `0` |
| `--collect-only \| grep -c "claim_anonymous_grant"` | `3`; `grep -n` over the file itself returns nothing |
| `git diff --name-only feabd72 HEAD` | exactly the two declared files |
| `git diff --diff-filter=D --name-only feabd72 HEAD` | nothing deleted |

**Collected-case counts, as the plan asked to be recorded: 26 before, 42 after.**

## Known Stubs

None. No hardcoded empty collection, no placeholder text, no unwired data source, and no `TODO`/`FIXME` introduced. Every branch this plan added is a shipped refusal a client can observe.

## Threat Flags

None new. The register's five entries are all discharged by this plan:

- **T-40-06-01 (elevation of privilege — issuance to an account-less caller).** Closed. The three non-create-user operations are 403 for a caller with no identity row, and each refusal case asserts `store.issued == []`, so the refusal is proven to precede issuance rather than merely to accompany it.
- **T-40-06-02 (information disclosure — the operation vocabulary).** Closed. The membership test is first, and `TestTheRefusalOrderDisclosesNothing` asserts the equality of the two callers' refusals directly for all seven strings rather than inferring it from the source order.
- **T-40-06-03 (tampering — the issuable set).** Closed. The handler tests membership against the type, both parametrizations are comprehensions over `AuthOperation`, and the AST control fails if any module-level collection appears in the router module.
- **T-40-06-04 (information disclosure — the issued handle).** Unchanged and re-verified. The `no-store` block and the `auth_challenge_operation_not_issuable` log line are untouched; the new refusal logs nothing at all, so the handle and the 403 both disclose nothing.
- **T-40-06-SC (package installs).** Unreachable — nothing installed; `pyproject.toml` untouched.

## User Setup Required

None.

## Next Phase Readiness

- **`services/auth.py` was not touched**, as the wave dispatch required — plan 40-05 owns it and no service change proved necessary. `git diff --name-only` against the base lists only the two declared files.
- **`REQUIREMENTS.md` was deliberately not edited.** UPGRADE-02 is shared with 40-04 and 40-07 and two worktrees are live in this wave; marking it from here would race. The orchestrator should mark UPGRADE-02 after the wave merges.
- **Phases 41 and 42 need no change here.** Adding a completion adds an enum member, and both the handler's membership test and both test parametrizations pick it up with no edit. The only work either phase owes this file is a new case if it wants one — the four-operation coverage grows on its own.

---
*Phase: 40-post-auth-upgrade-anonymous*
*Completed: 2026-09-02*

## Self-Check: PASSED

- `.planning/phases/40-post-auth-upgrade-anonymous/40-06-SUMMARY.md` — FOUND
- `src/nativespeaker/api/routers/auth.py`, `tests/unit/test_challenge_endpoint.py` — FOUND
- Commits `5836908`, `1d1d68a`, `0e4f7d5`, `20e5311` — all FOUND in `git log`
- `.env` present in the worktree, absent from `git log --all -- .env`, and `git status --short` empty at every commit
- `src/nativespeaker/api/services/auth.py` NOT in `git diff --name-only feabd72..HEAD`
