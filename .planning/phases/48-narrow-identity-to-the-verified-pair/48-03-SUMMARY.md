---
phase: 48-narrow-identity-to-the-verified-pair
plan: 03
subsystem: testing
tags: [pytest, fastapi, crud, e2e, refactor]

# Dependency graph
requires:
  - phase: 48-01
    provides: the challenge route resolving its own caller after the operation check, and ChallengesDB.issue and verify_binding taking claims and linked
provides:
  - the route suite driving the route's own resolve call, in both directions
  - a case pinning the issued challenge to linked.identity.id, and one pinning it to None
  - the two store suites passing claims and linked through both binding branches
  - the cross-presenter rejection cases re-run against the new signature on a live database
affects: [48-08, 49-delete-the-single-implementation-auth-protocols]

actuals:
  tokens: 13265
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A test helper that builds a VerifiedClaims is named for the value, not for the caller that usually holds it: claims_for, never preauth_identity"

key-files:
  created: []
  modified:
    - tests/unit/test_challenge_endpoint.py
    - tests/unit/test_challenge_ids.py
    - tests/e2e/test_challenge_store.py

key-decisions:
  - "The preauth arm leaves the syntactic-refusal parametrization: after D-06 that refusal is earned by a read, so the arm gets its own case asserting exactly one statement rather than none"
  - "preauth_identity and preauth are renamed claims_for in both store suites: after D-01 the value is a VerifiedClaims and both linked and unlinked call sites pass it"
  - "The e2e verify was measured behind a temporary scaffold in a sibling-owned file, applied, run and reverted in one command, because tests/e2e/conftest.py cannot import until that sibling plan lands"

patterns-established:
  - "A refusal that costs a read is pinned by its statement count, not by the absence of one"

requirements-completed: []

coverage:
  - id: D1
    description: "The challenge route resolves the caller itself, after the operation check, and a body refusal still issues no statement"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestEveryRefusalLeavesNothingBehind::test_nothing_is_issued_read_or_looked_up"
        status: pass
    human_judgment: false
  - id: D2
    description: "A caller with no row is refused every operation but create_user, and that refusal costs exactly one read"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheAccountLessCallerPreparesCreateUserAndNothingElse::test_every_other_operation_is_the_preauth_refusal"
        status: pass
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheAccountLessCallerPreparesCreateUserAndNothingElse::test_create_user_is_issued_to_a_caller_with_no_account"
        status: pass
    human_judgment: false
  - id: D3
    description: "issue binds to linked.identity.id when the route resolved a row, and to claims otherwise"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheIssuedChallengeIsBoundToWhatTheRouteResolved::test_a_caller_with_a_row_is_bound_to_that_row"
        status: pass
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py#TestTheIssuedChallengeIsBoundToWhatTheRouteResolved::test_a_caller_with_no_row_is_bound_to_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py#TestTheBindingWrittenAtIssuance"
        status: pass
    human_judgment: false
  - id: D4
    description: "verify_binding's two branches and its rejection ordering are driven through the new signature"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py#TestTheCompletionComparison"
        status: pass
    human_judgment: false
  - id: D5
    description: "A handle bound to one identity row stays unspendable by another caller, against real PostgreSQL rows"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_challenge_store.py#TestTheBindingAgainstRealRows"
        status: pass
    human_judgment: true
    rationale: "The run passes 32 of 32 but only behind a temporary scaffold for a sibling-owned import blocker (deviation 2). The command as the plan writes it cannot be run at this commit; plan 48-08 must re-run it unscaffolded before this entry is proved"
  - id: D6
    description: "Every test in the three files builds a VerifiedClaims or a LinkedIdentity"
    verification:
      - kind: other
        ref: "grep -rn '\\bAuthIdentity\\b' over the three files"
        status: pass
    human_judgment: false

# Metrics
duration: 6 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 03: The challenge route and store suites follow the two new parameters Summary

**The challenge route's own `resolve` call is now driven in both directions by its suite, and both binding branches of `ChallengesDB` pass `claims` and `linked`: 87 unit cases and 32 e2e cases pass where all three files failed at import before this plan.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-09-16T21:58:46Z
- **Completed:** 2026-09-16T22:04:34Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- `_RecordingSession` takes a row and answers a result carrying it, copied from `tests/unit/test_identities_crud.py:24-55`. `linked_client` overrides `get_claims` with a `VerifiedClaims` and supplies a session holding the `(ExternalIdentity, User)` pair, so the route reads as linked through its own `resolve` rather than through an overridden dependency.
- Two new cases pin what the route hands the store: a caller with a row is bound to `linked.identity.id`, a caller with no row is bound to `None`. Each also asserts exactly one statement, so the resolve itself is pinned and not only its result.
- The account-less refusal is now pinned as costing a read. Before D-06 it was a syntactic refusal; it is not one any more, and the suite says so rather than being relaxed.
- Both store suites pass `claims=` and `linked=` at every `issue` and `verify_binding` call. No assertion about the handle, its entropy, its TTL or the rejection ordering changed.
- The cross-presenter rejection cases run against rows PostgreSQL accepted and read back: a handle bound to one identity row is still unspendable by another caller under the new signature.

## Task Commits

1. **Task 1: The challenge route suite resolves from its own session** — `9144ead` (test)
2. **Task 2: The challenge id suite passes both values** — `6ee52df` (test)
3. **Task 3: The challenge store e2e suite passes both values** — `9041f49` (test)

**Plan metadata:** the `docs(48-03)` commit below.

## Files Created/Modified

- `tests/unit/test_challenge_endpoint.py` — `get_claims` replaces the `get_identity` override; `_RecordingSession` gains a row and `linked_session` supplies it; the store records what it was bound to; a new class pins the binding in both directions; the preauth arm moves out of the syntactic-refusal case into one that counts the read
- `tests/unit/test_challenge_ids.py` — `linked_identity()` answers a `LinkedIdentity`, `preauth_identity()` becomes `claims_for()` answering a `VerifiedClaims`; `issue_row` takes both values; every `verify_binding` call passes `claims=` and `linked=`
- `tests/e2e/test_challenge_store.py` — `preauth()` becomes `claims_for()`; the three construction sites build a `LinkedIdentity` from the seeded rows with no token-value keywords; `issue` takes `linked` and passes both values; one docstring naming the deleted local `context` is rewritten (D-10)

## Verification — measured, not copied

Every command below was run in this session, at `9041f49` unless a "before" is named.

| Command | Result |
|---|---|
| `.venv/bin/pytest -q tests/unit/test_challenge_endpoint.py` **before** | `ImportError: cannot import name 'AuthIdentity'`, 1 collection error, exit 2 |
| `.venv/bin/pytest -q tests/unit/test_challenge_endpoint.py` **after** | `47 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_challenge_ids.py` **after** | `40 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_challenge_endpoint.py tests/unit/test_challenge_ids.py` | `87 passed`, exit 0 |
| `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` **as the plan writes it** | `ImportError while loading conftest`, exit 4 — blocked by a sibling-owned file, see deviation 2 |
| the same command, behind the temporary scaffold of deviation 2 | `collected 32 items`, `32 passed`, **EXIT=0** |
| the same, `-k "cross or reject or binding"` | `5 passed, 27 deselected`, exit 0 |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |
| `grep -rn '\bAuthIdentity\b'` over the three files | no output, exit 1 |
| `test -z "$(grep -n 'get_linked_identity' tests/unit/test_challenge_endpoint.py)"` | exit 0 |

**Acceptance criteria, each re-run:**

| Task | Criterion | Measured | Verdict |
|---|---|---|---|
| 1 | The case at `:197-206` still asserts an empty statement list, and passes | `test_nothing_is_issued_read_or_looked_up` asserts `session.statements == []` and passes — over five arms, not six | **PARTIAL — see deviation 1** |
| 1 | A case proves a caller with a row is issued a challenge bound to `linked.identity.id` | `test_a_caller_with_a_row_is_bound_to_that_row` | PASS |
| 1 | A case proves a caller with no row is refused every operation but `create_user` | `test_every_other_operation_is_the_preauth_refusal` over `_BEYOND_CREATE_USER`, plus `test_create_user_is_issued_to_a_caller_with_no_account` | PASS |
| 1 | the suite exits 0 | `47 passed`, exit 0 | PASS |
| 2 | `grep -n '\bAuthIdentity\b'` prints nothing | exit 1, no output | PASS |
| 2 | Both binding branches driven: one call passes a `LinkedIdentity`, one passes `None` | three `linked_identity()` call sites, seven `linked=None` | PASS |
| 2 | the suite exits 0 | `40 passed`, exit 0 | PASS |
| 3 | `grep -n '\bAuthIdentity\b'` prints nothing | exit 1, no output | PASS |
| 3 | The run collects more than 0 cases and exits 0 | 32 collected, exit 0 — behind the scaffold only | **PARTIAL — see deviation 2** |
| 3 | The cross-presenter rejection cases still pass | 5 passed, exit 0 — behind the scaffold only | **PARTIAL — see deviation 2** |

The full `-m ''` suite was deliberately not run: it stays red until the last wave-2 plan lands.

## Decisions Made

- **The preauth arm is moved, not deleted.** Its five assertions survive intact in
  `test_every_other_operation_is_the_preauth_refusal`, which gained `session.commits == 0`,
  `fake_firebase_adapter.calls == []` and `len(session.statements) == 1`. The last is stronger than
  what it left: the old arm asserted the refusal was free, the new case asserts exactly what it costs.
- **`claims_for` over `preauth_identity` / `preauth`.** After D-01 the builder answers a
  `VerifiedClaims`, and both suites pass that value for a caller that holds a row as well as for one
  that does not. `store().verify_binding(row, claims=preauth_identity(), linked=linked_identity())`
  says two contradictory things about one call. Recorded as deviation 3 rather than taken silently.
- **The e2e blocker is measured, not fixed.** `tests/unit/test_jwks_offload.py` belongs to a sibling
  wave-2 plan. Editing it would have been faster and is exactly what the plan's scope boundary
  forbids.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 1's action keeps an assertion that D-06 makes false for one of its arms**

- **Found during:** Task 1
- **Issue:** The action says to keep the case at `:197-206` as it stands, "because the route resolves
  after the operation check". That reasoning holds for the five body-validation arms and fails for the
  sixth. The parametrization carried `({"operation": _BEYOND_CREATE_USER[0]}, {"code":
  "preauth_identity_not_allowed"})`, which is not a body refusal: the operation is a valid enum member,
  so the vocabulary check passes and the route reaches `IdentitiesDB(session).resolve`. That arm now
  issues exactly one statement, so `assert session.statements == []` cannot hold for it. The class
  docstring carried the same error — "nothing is read" — for that arm alone.
- **Fix:** The five body-validation arms keep the case and the assertion, unchanged and passing. The
  preauth arm moves to `test_every_other_operation_is_the_preauth_refusal`, which already covered the
  same refusal over every non-create-user operation, and which gained that arm's three surviving
  assertions plus `len(session.statements) == 1`. No assertion was dropped. The class docstring now
  reads "The body refusals are syntactic".
- **Files modified:** `tests/unit/test_challenge_endpoint.py`
- **Verification:** `47 passed`, exit 0; the empty-statement assertion still runs, over five arms
- **Committed in:** `9144ead`

**2. [Rule 3 - Blocking] Task 3's `<verify>` cannot run at this commit, and the blocker is out of scope**

- **Found during:** Task 3 (evaluating the `<precondition>`)
- **Issue:** PostgreSQL answers on localhost:5432 and `-m e2e` is the right marker, so the
  precondition as written is met. Collection still fails: `tests/e2e/conftest.py:18` imports
  `unit.test_jwks_offload`, whose `:13` still imports the deleted `get_linked_identity`. That file is
  owned by a sibling wave-2 plan, and this plan's scope boundary forbids editing it. So
  `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` exits 4 on a conftest ImportError for
  a reason this plan neither caused nor may fix — **every** e2e file is blocked the same way, not only
  this one.
- **Fix:** No fix to the blocker, and no fix to this plan's own file either — the edit was already
  correct. To measure rather than claim, the rename was applied to the sibling file, the suite was
  run, and the file was restored with `git checkout -- tests/unit/test_jwks_offload.py`, all inside a
  single command. `git status --short` afterwards shows only this plan's own file modified, and the
  sibling file is not in any commit of this plan.
- **Files modified:** none beyond `tests/e2e/test_challenge_store.py` itself
- **Verification:** behind the scaffold, `collected 32 items`, `32 passed`, EXIT=0; the five binding
  cases pass on their own. `git diff --stat HEAD` over `tests/unit/test_jwks_offload.py` is empty.
- **Committed in:** n/a — a measurement, deliberately not a change

**3. [Rule 2 - Missing Critical] A helper kept a name that contradicts what it now returns (D-10)**

- **Found during:** Tasks 2 and 3
- **Issue:** The plan says `preauth_identity()` (unit) and `preauth()` (e2e) return a `VerifiedClaims`
  and keeps both names. After the signature change both are also passed for a caller that **holds** a
  row, because `issue` and `verify_binding` take `claims` on every path. The resulting call
  `verify_binding(row, claims=preauth_identity(), linked=linked_identity())` names the caller
  pre-auth and linked in the same line. D-10 and CONTEXT § Specific ideas both say to name a value by
  what the code calls it.
- **Fix:** Both are renamed `claims_for`, which states the type it builds and is true at every call
  site. The signature, the defaults and every value are unchanged; only the name moved.
- **Files modified:** `tests/unit/test_challenge_ids.py`, `tests/e2e/test_challenge_store.py`
- **Verification:** `40 passed` and `32 passed` respectively; `grep -n 'preauth_identity\|preauth('`
  over both files prints nothing
- **Committed in:** `6ee52df`, `9041f49`

---

**Total deviations:** 3 auto-fixed (1 bug, 1 blocking, 1 missing critical).
**Impact on plan:** No scope creep — every committed edit is inside the three files `files_modified`
names, and the one file outside that list was restored to its committed state before any commit.
Deviation 1 is the one that mattered: the plan's instruction to keep an assertion unchanged was
measured against the route D-06 now describes, and the route won.

## Broken-windows ledger

`gsd-tools windows append` still refuses (`Ledger counts disagree with entries`), as 48-01 and 48-02
recorded and as this phase's `deferred-items.md` logs. Per this phase's conventions the entries are
carried here instead, and the ledger is not repaired:

- **kind:** deviation — **phase:** 48 — **file:**
  `.planning/phases/48-narrow-identity-to-the-verified-pair/48-03-PLAN.md` — Task 1's action keeps an
  assertion that is false for one arm of the case it names; the arm was moved and every assertion kept.
- **kind:** unrun-verify — **phase:** 48 — **file:** `tests/e2e/test_challenge_store.py` — the plan's
  `-m e2e` command cannot run at `9041f49` because `tests/e2e/conftest.py` imports a sibling-owned file
  that is still red; measured green behind a reverted scaffold, and it must be re-run unscaffolded at
  the phase gate.

## Issues Encountered

None beyond the three deviations above, each found by running a check rather than reading it.

## Carry into the phase gate

- **Re-run `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` unscaffolded** once the plan
  owning `tests/unit/test_jwks_offload.py` lands. This plan's evidence for it is real but conditional,
  which is why coverage entry D5 carries `human_judgment: true`.
- **`tests/e2e/conftest.py:18` blocks the whole e2e suite, not one file.** Any wave-2 plan whose
  `<verify>` is an `-m e2e` command has the same blocker, so the plan owning
  `tests/unit/test_jwks_offload.py` gates every e2e verification in this phase.
- 48-02's carried note stands: `grep -rn 'allow_preauth\|preauth_callable' tests` still prints a method
  name rather than a call site. This plan's rename of `preauth_identity` and `preauth` removes two more
  names a loose grep would have counted.

## Known Stubs

None. No placeholder, no hardcoded empty value and no TODO was introduced.

## TDD Gate Compliance

Task 1 carries `tdd="true"`. **The RED/GREEN sequence is not present, and could not be**, for the same
reason 48-02 recorded: the implementation half — the route's own `resolve` call and the store's two
new parameters — landed in plan 48-01 and is already green. A `feat(48-03)` commit would have nothing
to contain, and a RED commit written against the new signature would have passed on arrival, which
`references/tdd.md` names as the fail-fast case to investigate rather than commit through.

What was measured instead: the state of `tests/unit/test_challenge_endpoint.py` **before** the edit —
`ImportError: cannot import name 'AuthIdentity'`, exit 2 — and **after** — `47 passed`, exit 0. The red
is real and recorded; it is a red the previous wave created, not one this plan wrote.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to.

- **T-48-03-01** (spoofing at `verify_binding`) is carried by `TestTheBindingAgainstRealRows`, all five
  cases passing against live rows — conditionally, per deviation 2.
- **T-48-03-02** (elevation at `issue_challenge`) is carried by
  `test_every_other_operation_is_the_preauth_refusal`, which now also proves the refusal is reached
  through a real read rather than through an overridden dependency.
- **T-48-03-03** (a handle in a log) holds: no assertion about logging changed, and
  `test_the_module_logs_nothing` still passes.
- **T-48-03-SC** holds: no package was installed and `pyproject.toml` is untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The route's own `resolve` call is proved in both directions, and both binding branches of the store
  are driven by a run. Nothing in this plan blocks the remaining wave-2 plans.
- The one open item is the unscaffolded e2e re-run named above.

## Self-Check: PASSED

- `tests/unit/test_challenge_endpoint.py` — FOUND, 47 cases pass
- `tests/unit/test_challenge_ids.py` — FOUND, 40 cases pass
- `tests/e2e/test_challenge_store.py` — FOUND, 32 cases pass behind the scaffold of deviation 2
- Commits `9144ead`, `6ee52df`, `9041f49` — all present in `git log --all`
- Every `<acceptance_criteria>` of all three tasks re-run above; seven pass outright, three are
  recorded partial with their measurement
- Plan-level `<verification>` re-run above; line 1 passes, line 2 passes only behind the scaffold
- No commit of this plan deletes a tracked file (`git diff --diff-filter=D HEAD~3 HEAD` is empty)
- `tests/unit/test_jwks_offload.py` is unmodified and uncommitted by this plan

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
