---
phase: 48-narrow-identity-to-the-verified-pair
plan: 01
subsystem: auth
tags: [fastapi, dependencies, dataclasses, refactor, jwt]

# Dependency graph
requires:
  - phase: 46-post-auth-sign-out-all
    provides: the barrier as get_identity then get_linked_identity, and the rule that the provider is told what the request proved
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: the suite counts and the one pre-existing failing case criterion 5 must not be charged for
provides:
  - LinkedIdentity with exactly user and identity, both required, frozen, slotted, over no base class
  - AuthIdentity deleted from src/
  - get_claims, which verifies the token and reads no table
  - get_identity, which resolves in its own short session and raises PreAuthIdentityNotAllowed on no row
  - IdentitiesDB.resolve(*, issuer, subject) -> LinkedIdentity | None, with the three rejections unchanged
  - ChallengesDB.issue and verify_binding taking claims and linked
  - AuthService taking claims and linked, and resolving the caller itself at create-user
affects: [48-02, 48-03, 48-04, 48-05, 48-06, 48-07, 48-08, 49-delete-the-single-implementation-auth-protocols]

actuals:
  tokens: 30112
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "The barrier is two declarations, not one type with nullable fields: get_claims proves the token, get_identity proves the account"
    - "A route that needs both declares both; FastAPI's cache makes that one verification and one query"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/schemas/auth.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/crud/identities.py
    - src/nativespeaker/api/crud/challenges.py
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/services/restore.py
    - src/nativespeaker/api/routers/auth.py
    - src/nativespeaker/api/routers/users.py
    - src/nativespeaker/api/routers/chats.py
    - src/nativespeaker/api/routers/root.py
    - src/nativespeaker/api/routers/examples.py
    - tests/unit/conftest.py
    - tests/unit/test_identity_accessors.py
    - tests/unit/test_app_wiring.py

key-decisions:
  - "Task 1 answered B: AuthService.complete resolves the caller itself, so every create-user wire outcome stays byte-identical to today"
  - "The plan's grep for LinkedIdentity | None counted the return type D-03 mandates; the invariant measured instead is that no third src file takes it as a parameter"
  - "The 'resolves once' case is split: /admitted asserts get_claims opens no session at all, which is stronger than the session count it replaced"
  - "_unlinked() is kept as a VerifiedClaims builder and used by the admitting-route case, so it has a caller"

patterns-established:
  - "Two dependencies, two value types, no nullable field: the declaration is what refuses, not a runtime None check"
  - "A crud read that can legitimately find nothing answers None; the refusal for 'nothing' belongs to the caller that requires something"

requirements-completed: []

coverage:
  - id: D1
    description: "LinkedIdentity carries exactly user and identity, both required, frozen, slotted, over no base class"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestTheLinkedIdentityShape::test_it_carries_both_rows_frozen_slotted_and_over_no_base_class"
        status: pass
    human_judgment: false
  - id: D2
    description: "AuthIdentity is gone from src/; the token result is VerifiedClaims from auth/jwt_verifier.py"
    verification:
      - kind: other
        ref: "grep -rn '\\bAuthIdentity\\b' src"
        status: pass
    human_judgment: false
  - id: D3
    description: "get_claims refuses the same five token arms and opens no session"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestTheWireArmsRaiseAndTheHandlerRecordsThemOnce::test_each_arm_logs_one_record_naming_its_class_and_its_bounded_reason"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestAccessorsCannotProvision::test_the_admitting_declaration_reads_no_table_at_all"
        status: pass
    human_judgment: false
  - id: D4
    description: "get_identity answers 403 preauth_identity_not_allowed for a caller with no row, and resolves in its own short session closed before the handler"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestTheNarrowingHoldsInBothDirections::test_a_caller_with_no_row_on_a_linked_route_answers_403"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestAccessorsCannotProvision::test_the_declaration_resolves_once"
        status: pass
    human_judgment: false
  - id: D5
    description: "IdentitiesDB.resolve takes issuer and subject only and answers LinkedIdentity or None, keeping IdentityUnresolvable, HistoricalIdentity and BlockedUser"
    verification:
      - kind: other
        ref: "grep -rn 'allow_preauth' src"
        status: pass
    human_judgment: true
    rationale: "The three rejections were copied character for character but are re-run against the crud suite only in plan 48-02, which is where they are proved rather than inspected"
  - id: D6
    description: "The declaration matrix matches D-08's table, read off the live app"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestEveryRouteIsAuthenticated"
        status: pass
    human_judgment: false
  - id: D7
    description: "A route declaring both dependencies verifies the token once and queries once"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheAuthDependencyIsResolvedOncePerRequest::test_one_verify_and_one_query_for_a_doubly_declared_route"
        status: pass
    human_judgment: false
  - id: D8
    description: "Every create-user wire outcome is unchanged under option B, including the three rejections and their precedence"
    verification: []
    human_judgment: true
    rationale: "tests/e2e/test_create_user.py:203-256 pins today's two outcomes and is not rewritten by this plan; it is re-run in plan 48-05 and at the phase gate"

duration: 12 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 01: Narrow Identity to the verified pair Summary

**`AuthIdentity` deleted; the barrier is now `get_claims` (token, no table) and `get_identity` (account, one statement in its own session), with `LinkedIdentity` holding two required rows and no base class.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-16T21:38:07Z
- **Completed:** 2026-09-16T21:50:00Z
- **Tasks:** 3
- **Files modified:** 14

## Accomplishments

- The four-field class is gone from `src/`. The token result is `VerifiedClaims`, which `auth/jwt_verifier.py` already defined; `LinkedIdentity` is a frozen, slotted dataclass over `object` with `user` and `identity`, both required.
- The barrier is two declarations. `get_claims` checks the credential and the token with the same five `BoundedReason` arms as before and touches no table; `get_identity` declares it, resolves in one statement in its own short session, and raises `PreAuthIdentityNotAllowed` when that answers `None`.
- `IdentitiesDB.resolve` lost `allow_preauth` and answers `LinkedIdentity | None`. The three rejections at the old `:45-53` are copied character for character.
- Every `src/` caller moved in one commit: the challenge store, both services, and all five routers. `routers/root.py` and `routers/examples.py` were included, which CONTEXT's scope list omitted and RESEARCH A1 caught.
- Under the developer's answer to Task 1, `AuthService.complete` resolves the caller itself, so `IdentityUnresolvable`, `HistoricalIdentity` and `BlockedUser` still refuse a create-user caller **before** the claim spends its challenge.

## Task Commits

1. **Task 1: Decide what an already-linked caller gets at create-user** — no commit; a decision checkpoint, answered before execution (see below)
2. **Task 2: The two types, the two dependencies and every src caller** — `493a128` (test, RED) and `89ede98` (feat, GREEN)
3. **Task 3: The declaration matrix follows the two names** — `c2c14be` (test)

**Plan metadata:** see the final `docs(48-01)` commit.

## Task 1 — the developer's answer

The checkpoint was `gate="blocking-human"` and was put to the developer by the orchestrator before execution began. The answer, quoted:

> **"B: Check for the account inside the service" — `AuthService.complete` resolves the caller itself.**

Execution continued with Task 2, as the plan's acceptance criteria require for B. No source file was edited before the answer was given.

What B bought, and it is the reason the plan is behavior-preserving: `complete` calls
`self.identities_db.resolve(issuer=claims.issuer, subject=claims.subject)` before `_complete`, so a
caller holding an active row still reaches `_reject_existing_identity` and is answered 409
`identity_already_linked`, rather than hitting the row-bound branch of `verify_binding` with nothing
to compare and being answered 409 `challenge_required` in a loop. The query count for create-user
does not move, because the router-level dependency ran the same statement before this phase.

## Files Created/Modified

- `src/nativespeaker/api/schemas/auth.py` — `AuthIdentity` deleted; `LinkedIdentity` re-declared with two required fields
- `src/nativespeaker/api/crud/identities.py` — `resolve` loses the flag and answers `| None`; `insert_account` takes `claims`
- `src/nativespeaker/api/app/dependencies.py` — split into `get_claims` and `get_identity`
- `src/nativespeaker/api/crud/challenges.py` — `issue` and `verify_binding` take `claims` and `linked`
- `src/nativespeaker/api/services/auth.py` — `PostClaim[T]` takes `claims` alone; `_complete` loses its type variable; `complete` resolves the caller
- `src/nativespeaker/api/services/restore.py` — the parameter is `linked`
- `src/nativespeaker/api/routers/auth.py` — router-level `get_claims`; the eight routes follow D-08's table; the challenge route resolves after the vocabulary check
- `src/nativespeaker/api/routers/{users,chats,root,examples}.py` — both declaration levels take `get_identity`; handler parameters are `linked`
- `tests/unit/conftest.py` — `TEST_IDENTITY` drops its two token keywords; the override keys on `get_identity`; the fake store follows the new signature
- `tests/unit/test_identity_accessors.py` — rewritten against the two names; `TestTheLinkedIdentityShape` replaces `TestTheIdentityShape`
- `tests/unit/test_app_wiring.py` — the matrix, the exemptions and the doubly-declared probe follow the two names

## Verification — measured, not copied

Every command below was run in this session at `c2c14be`.

| Command | Result |
|---|---|
| `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` | `80 passed`, exit 0 |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |
| `grep -rn '\bAuthIdentity\b' src` | no output, exit 1 |
| `grep -rn 'get_linked_identity\|allow_preauth' src` | no output, exit 1 |
| `grep -c 'async def get_claims' src/.../app/dependencies.py` | `1` |
| `grep -c 'async def get_identity' src/.../app/dependencies.py` | `1` |
| files taking `LinkedIdentity \| None` as a **parameter** | `crud/challenges.py`, `services/auth.py`, and nothing else |

Router-level declarations read off the live routers: `auth` → `get_claims`; `chats`, `users`, `root`,
`examples` → `get_identity`. `get_claims` returns `VerifiedClaims`; `get_identity` returns
`LinkedIdentity`.

**The wider suite is red on purpose, and its scope is measured.** The plan predicted 21 test files
still naming a renamed or deleted symbol; the measured count at `c2c14be` is **19** (the plan's
figure counted `tests/unit/test_app_wiring.py`, which this plan fixed, and one further file whose
only match is a test-method name). Plans 02 to 07 turn them green, one file group each. The full
`-m ''` suite was deliberately not run, per the plan and the phase's execution conventions.

## Decisions Made

- **Task 1 is B**, quoted above.
- **`_complete` keeps `T` and loses `I`** (planner note P-02). Each public method binds `linked` into
  its own `partial`, so `type PostClaim[T] = Callable[[VerifiedClaims], Awaitable[T]]` and no alias
  spells an optional. `_complete` still holds `linked: LinkedIdentity | None` for `verify_binding`.
- **`get_identity` raises outside the `async with`**, so the session is closed before the rejection
  travels. The test that pins "the session closes before the handler runs" holds either way; this
  ordering makes it hold for the refusal path too.
- **The challenge route's `resolve` sits between the vocabulary check and the row check** (RESEARCH
  A2), so a refused body still issues no statement.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's fourth `<verify>` command contradicts the decision it protects**

- **Found during:** Task 2 (running the plan's four verify commands)
- **Issue:** The command asserts `grep -rln 'LinkedIdentity | None' src` returns exactly
  `crud/challenges.py` and `services/auth.py`. It returned a third file, `crud/identities.py` —
  because **D-03 requires** `resolve` to be annotated `-> LinkedIdentity | None`. The grep counts
  every occurrence of the spelling, including the return type the plan's own `<action>` mandates, so
  as written it can never pass. The plan-level `<verification>` block and RESEARCH's criterion-3 row
  carry the same error.
- **Fix:** No source change — the source is right and the check was wrong. The invariant D-08 and the
  plan's `key_links` actually state is that only two files carry the optional **as a parameter**.
  Measured with `grep -rn 'LinkedIdentity | None' src | grep -v -- '-> LinkedIdentity | None'`, which
  returns `crud/challenges.py` (two parameters) and `services/auth.py` (one), and nothing else.
- **Files modified:** none
- **Verification:** the corrected command, run above; the full occurrence list is four lines, three of
  them parameters in the two expected files and one the mandated return type
- **Committed in:** n/a — a check correction, carried here rather than silently into the source

**2. [Rule 1 - Bug] The "resolves once" case asserted a session the split deliberately removes**

- **Found during:** Task 2 (first GREEN run: 1 failed, 44 passed)
- **Issue:** `test_the_declaration_resolves_once` was parametrized over `/admitted` and `/linked`. It
  passed before this phase because the pre-split `get_identity` opened a session on both paths. After
  D-04, `/admitted` declares `get_claims` alone, which reads no table — so the `/admitted` arm
  asserted `len(opened) == 1` against a route that correctly opens **zero** sessions. The plan said to
  keep this pin unchanged; measured against the tree, keeping it unchanged would have required
  `get_claims` to query, which D-04 forbids.
- **Fix:** Split the case. `test_the_declaration_resolves_once` covers `/linked` and keeps all three
  original assertions (one session, one statement, closed before the handler). A new case,
  `test_the_admitting_declaration_reads_no_table_at_all`, asserts `/admitted` answers 200 and opens no
  session at all — a **stronger** claim than the one it replaces, and the executable form of
  criterion 2's "`get_claims` issues no SQL".
- **Files modified:** `tests/unit/test_identity_accessors.py`
- **Verification:** `45 passed` on the accessor suite; the criterion-2 pin at the old `:152-156`
  (a refused token opens no session) is untouched
- **Committed in:** `89ede98`

**3. [Rule 3 - Blocking] `tests/unit/test_app_wiring.py` was imported out of isort order after the rename**

- **Found during:** Task 3
- **Issue:** The mechanical two-phase rename left `get_db` before `get_claims` in the dependency
  import block, which ruff's `I` rules reject.
- **Fix:** Reordered the block.
- **Files modified:** `tests/unit/test_app_wiring.py`
- **Verification:** `.venv/bin/ruff check src tests` prints `All checks passed!`
- **Committed in:** `c2c14be`

### Judgement calls recorded rather than auto-fixed

- **`_unlinked()` was nearly orphaned.** The plan turns it into a `VerifiedClaims` builder, but every
  one of its old callers lives in `TestTheIdentityShape`, which the plan deletes. Rather than leave a
  function with no caller (AGENTS.md § Function shape would have it deleted), it is used by
  `test_a_caller_with_no_row_on_an_admitting_route_is_admitted` as the expected subject. It has a
  caller and the plan's instruction stands.
- **`issue_challenge` constructs `IdentitiesDB` in the handler body**, which AGENTS.md § Package
  layout otherwise forbids ("never construct a database class in the body"). D-06 mandates it
  explicitly and the plan repeats it, so the locked decision was followed. Flagged here, not resolved
  silently: `get_purchases_db` in `app/dependencies.py` is the precedent for the alternative, and
  Phase 49 or 50 could take it if the rule is to hold without exception.

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking) plus 2 judgement calls recorded.
**Impact on plan:** No scope creep. Deviations 1 and 2 are both cases of a plan artifact contradicting
a locked decision from the same plan; in each the decision won and the check was corrected. Both are
worth carrying into the phase gate, because the plan-level `<verification>` block and RESEARCH's
criterion-3 row still carry deviation 1's wrong expectation.

## TDD Gate Compliance

Task 2 carries `tdd="true"`. The gate sequence is present: `493a128` is the RED (`test(48-01)`),
`89ede98` is the GREEN (`feat(48-01)`). No REFACTOR commit was needed.

**One honest qualification.** The RED could not fail for a behavioural reason. The feature is the
split and rename of a type and two dependencies, so a suite written against the new names fails at
import — measured: `ImportError: cannot import name 'get_claims' from
'nativespeaker.api.app.dependencies'`, exit 2. That is a real red proving the suite binds to names
that do not yet exist, but it is an import error, which `references/tdd.md` names as the weaker kind.
There is no ordering of a rename that produces a behavioural red; recorded rather than dressed up.

## Issues Encountered

Beyond the two plan-artifact errors documented above — both found by running the checks rather than
by reading them — one out-of-scope blocker was hit and deferred rather than fixed.

**`.planning/WINDOWS.md` cannot be appended to.** `gsd-tools windows append` refuses with
`Ledger counts disagree with entries: frontmatter open/waived/fixed/total=20/1/11/32 but entries
yield 19/1/12/32`. An entry was fixed at some point without its frontmatter counter being moved.
This is pre-existing and unrelated to anything this plan changed, so the executor scope boundary
forbids fixing it here; it is logged in `deferred-items.md` in this phase directory. The consequence
worth naming: every `windows append` in phases 48 to 50 will fail the same way, so a defect that
should surface at the ship gate is recorded only in its own SUMMARY until the counters are corrected.
Deviation 1 above is the entry that could not be written.

## Known Stubs

None. No placeholder, no hardcoded empty value, and no TODO was introduced.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to. T-48-01 through T-48-07
are each carried by a case that passes above; T-48-SC holds, since `pyproject.toml` is untouched and
no package was installed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The barrier is in place and proved end to end on real routers. Plans 02 to 08 can proceed.
- **19 test files still name a renamed or deleted symbol** and are red until plans 02 to 07 reach
  them. That is the planned intermediate state, not a defect.
- **Carry into the phase gate:** the plan-level `<verification>` line
  "`grep -rln 'LinkedIdentity | None' src` prints `crud/challenges.py` and `services/auth.py` and
  nothing else" is unsatisfiable as written, because D-03 mandates the third occurrence as `resolve`'s
  return type. Plan 48-08 should measure the parameter form instead.
- Plan 48-02 owns the crud suite, including the new case asserting `resolve` answers `None` for no
  row, and the re-run of the three rejections that this plan copied but did not re-prove.

## Self-Check: PASSED

- `src/nativespeaker/api/app/dependencies.py` — FOUND, declares `get_claims` and `get_identity` once each
- `src/nativespeaker/api/schemas/auth.py` — FOUND, `LinkedIdentity` with two fields
- `src/nativespeaker/api/crud/identities.py` — FOUND, `resolve` without the flag
- `tests/unit/test_identity_accessors.py` — FOUND, 45 cases pass
- `tests/unit/test_app_wiring.py` — FOUND, 35 cases pass
- Commits `493a128`, `89ede98`, `c2c14be` — all present in `git log`
- Every `<acceptance_criteria>` of Tasks 2 and 3 re-run above; all pass
- Plan-level `<verification>` re-run above; four of five pass as written, the fifth passes in the
  corrected form and is recorded as deviation 1

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
