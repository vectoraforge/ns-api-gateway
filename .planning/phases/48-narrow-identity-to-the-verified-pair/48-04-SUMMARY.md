---
phase: 48-narrow-identity-to-the-verified-pair
plan: 04
subsystem: testing
tags: [pytest, fastapi, dependencies, refactor]

# Dependency graph
requires:
  - phase: 48-01
    provides: get_claims and get_identity, where the account dependency declares the token one and not the reverse
provides:
  - the three precedence suites supplying both values through two dependency overrides each
  - the rejection precedence of the upgrade route and both grant routes, re-run rather than inspected
affects: [48-08, 49-delete-the-single-implementation-auth-protocols]

actuals:
  tokens: 22442
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A suite behind a route that declares both dependencies overrides both: one entry leaves the other dependency running for real"

key-files:
  created: []
  modified:
    - tests/unit/test_upgrade_precedence.py
    - tests/unit/test_claim_precedence.py
    - tests/unit/test_claim_precedence_registered.py

key-decisions:
  - "The one `identity` fixture becomes two fixtures, `claims` and `linked`, rather than one fixture answering a pair: each override needs its own callable, and a pair-unpacking lambda would name a value the codebase does not have"
  - "The `VerifiedClaims` carries the same issuer and subject the rows carry, which is what keeps the upgrade suite's provider-read assertion true"

patterns-established:
  - "Two overrides, two value types: the test app supplies what the route declares, never what one declaration used to derive"

requirements-completed: []

coverage:
  - id: D1
    description: "The upgrade route's rejection precedence is unchanged with both values supplied"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Both grant routes' rejection precedence is unchanged with both values supplied"
    verification:
      - kind: unit
        ref: "tests/unit/test_claim_precedence.py"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claim_precedence_registered.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Each of the three suites overrides get_claims and get_identity, so no case runs the real account dependency against no database (T-48-04-01)"
    verification:
      - kind: other
        ref: "grep -c 'dependency_overrides\\[get_claims\\]\\|dependency_overrides\\[get_identity\\]' over the three files prints 2 each"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every test in the three files builds a VerifiedClaims or a LinkedIdentity (D-11)"
    verification:
      - kind: other
        ref: "grep -n '\\bAuthIdentity\\b' over the three files"
        status: pass
    human_judgment: false
  - id: D5
    description: "The grant writers record what the request proved, and the suites keep the cases that assert it (T-48-04-02)"
    verification:
      - kind: unit
        ref: "tests/unit/test_upgrade_precedence.py#TestOneProviderReadPerCompletion::test_the_repeat_that_changes_nothing_still_reads"
        status: pass
    human_judgment: true
    rationale: "Neither grant suite asserts the recorded issuer and subject — `_RecordingGrants.activate` records the tier and the claim platform only. The one live assertion over the values now sourced from `claims` is the upgrade suite's provider-read pin above; the grant writers' recorded values are pinned in `tests/schema/`, owned by a sibling wave-2 plan"

# Metrics
duration: 2 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 04: The three precedence suites give both dependencies an override Summary

**The reversed dependency chain is handled in all three precedence suites: 105 cases pass where all three failed at import before this plan, and not one rejection, order or assertion moved.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-16T22:07:59Z
- **Completed:** 2026-09-16T22:10:17Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Each of the three client fixtures now sets two entries, `dependency_overrides[get_claims]` and `dependency_overrides[get_identity]`. Before D-04 and D-05 one entry was enough, because the account dependency was derived from the token one; the chain runs the other way now, so a suite with one entry would have run the real account dependency against no database. That is exactly T-48-04-01, and each file's two entries are asserted.
- The `identity` fixture in each file becomes `claims` (a `VerifiedClaims` carrying the same two token values) and `linked` (a `LinkedIdentity` carrying the same two rows). Every case keeps the caller it had, so every binding comparison, every rejection and every log assertion is unchanged.
- No assertion, no parametrization and no case was added, removed or relaxed. The case counts match the pre-phase tree exactly: 18 in the upgrade suite, and 44 + 43 = 87 across the two grant suites, which is what the three files collect now.

## Task Commits

1. **Task 1: The upgrade precedence suite overrides both dependencies** — `df9774d` (test)
2. **Task 2: The two grant claim precedence suites override both dependencies** — `9973a57` (test)

**Plan metadata:** the `docs(48-04)` commit below.

## Files Created/Modified

- `tests/unit/test_upgrade_precedence.py` — imports `get_claims` and `VerifiedClaims`, drops `AuthIdentity` for `LinkedIdentity`; the `identity` fixture splits into `claims` and `linked`; the client fixture sets both overrides
- `tests/unit/test_claim_precedence.py` — the same three edits; the module's shared helpers, which the registered suite imports, are untouched
- `tests/unit/test_claim_precedence_registered.py` — the same three edits

## Verification — measured, not copied

Every command below was run in this session, at `9973a57` unless a "before" is named.

| Command | Result |
|---|---|
| `.venv/bin/pytest -q tests/unit/test_upgrade_precedence.py` **before** | `ImportError: cannot import name 'AuthIdentity'`, exit 2 |
| `.venv/bin/pytest -q tests/unit/test_upgrade_precedence.py` **after** | `18 passed`, exit 0 |
| `.venv/bin/pytest -q tests/unit/test_claim_precedence.py tests/unit/test_claim_precedence_registered.py` | `87 passed`, exit 0 |
| all three files together (the plan-level `<verification>`) | `105 passed`, **EXIT=0** |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |
| `grep -n '\bAuthIdentity\b'` over the three files | no output, exit 1 |
| `grep -c 'dependency_overrides\[get_claims\]\|dependency_overrides\[get_identity\]'` per file | `2`, `2`, `2` |
| `test "$(grep -c 'dependency_overrides\[get_claims\]' tests/unit/test_upgrade_precedence.py)" = "1"` | exit 0 |

**Acceptance criteria, each re-run:**

| Task | Criterion | Measured | Verdict |
|---|---|---|---|
| 1 | Both `get_claims` and `get_identity` appear in `dependency_overrides` assignments | lines 167 and 168 | PASS |
| 1 | `grep -n '\bAuthIdentity\b'` prints nothing | exit 1, no output | PASS |
| 1 | The same number of cases passes as before the phase | 18 `def test_` at `937864c`, 18 collected and passing now | PASS |
| 1 | the suite exits 0 | `18 passed`, exit 0 | PASS |
| 2 | Each file assigns both overrides | one `get_claims` and one `get_identity` entry in each | PASS |
| 2 | `grep -n '\bAuthIdentity\b'` over both files prints nothing | exit 1, no output | PASS |
| 2 | both suites exit 0 | `87 passed`, exit 0 | PASS |

**The case-count check, derived rather than asserted.** `git show 937864c:` gives 31 and 29 `def test_` in the two grant suites. One case in each is parametrized over `POST_CLAIM_OUTCOMES`, which holds 14 entries in the anonymous suite and 15 in the registered one, so the collected counts are 30 + 14 = 44 and 28 + 15 = 43. The measured collection is 87, which is 44 + 43. No case was lost or gained.

The full `-m ''` suite was deliberately not run: it stays red until the last wave-2 plan lands.

## Decisions Made

- **Two fixtures, not one answering a pair.** The plan says the fixture "builds a `VerifiedClaims` ... and a `LinkedIdentity`". Each `dependency_overrides` entry needs its own callable, so one fixture returning a tuple would have to be unpacked by two lambdas and would need a name for the pair — and CONTEXT § Specific ideas forbids coining one. `claims` and `linked` are the names the routes and the services already use.
- **The `VerifiedClaims` carries the row values.** Each suite's `account` fixture builds its `ExternalIdentity` with `TEST_ISSUER` and that module's `SUBJECT`, and the `claims` fixture is built from the same two constants. This is load-bearing in the upgrade suite, where `fake_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)]` now asserts values the route reads off `claims` rather than off the row.
- **The two grant suites assert no recorded issuer or subject**, measured rather than assumed: `_RecordingGrants.activate` records `claim_platform` and `tier_id` only. The plan's conditional — "a case that asserts the written values keeps its expectation only if the `VerifiedClaims` carries the same two values as the rows" — is satisfied vacuously there and really in the upgrade suite.
- **No direct service call exists in either grant module.** The plan allows for one ("any direct service call in the module follows those keywords"); both suites drive `complete_claim_anonymous_grant` and `complete_claim_registered_grant` through the route alone, so no call site needed the new keywords.

## Deviations from Plan

None — plan executed exactly as written. The `<action>` of both tasks described the edit correctly against the working tree, every `<verify>` command ran as written, and every `<acceptance_criteria>` passed on the first run.

## Broken-windows ledger

No entry was needed: this plan left no stub, no skipped test, no unrun `<verify>` and no deviation. `gsd-tools windows append` was therefore not called, which is also what this phase's conventions would have required had there been an entry (the ledger's counters disagree with its own entries, logged in `deferred-items.md`, and repairing it is out of scope).

## Issues Encountered

None.

## Known Stubs

None. No placeholder, no hardcoded empty value and no TODO was introduced.

## TDD Gate Compliance

Neither task carries `tdd="true"`, so no RED/GREEN sequence applies. Both commits are `test(48-04)`, which is the right type: both tasks change test files only. The implementation half — the split of the barrier into `get_claims` and `get_identity` — landed in plan 48-01 and is already green.

The red these commits close is real and was measured, not assumed: `.venv/bin/pytest -q tests/unit/test_upgrade_precedence.py` before the edit answered `ImportError: cannot import name 'AuthIdentity' from 'nativespeaker.api.schemas.auth'`, exit 2. It is a red the previous wave created.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to.

- **T-48-04-01** (a suite overriding one dependency would run the real account dependency against no database) is carried by the two entries in each of the three files, asserted above.
- **T-48-04-02** (the grant writers record what the request proved) is carried by the upgrade suite's provider-read pin, and recorded honestly as `human_judgment: true` in coverage entry D5, because neither grant suite asserts the recorded pair.
- **T-48-04-SC** holds: no package was installed and `pyproject.toml` is untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The four non-mechanical sites RESEARCH named are now three down: this plan closes the third (the reversed override chain in the three precedence suites). Nothing here blocks the remaining wave-2 plans.
- Two notes carried by siblings still stand for the phase gate, and neither is this plan's to close: `tests/e2e/conftest.py:18` blocks every `-m e2e` command until the plan owning `tests/unit/test_jwks_offload.py` lands (48-03 deviation 2), and the plan-level `grep -rln 'LinkedIdentity | None' src` line is unsatisfiable as written (48-01 deviation 1).

## Self-Check: PASSED

- `tests/unit/test_upgrade_precedence.py` — FOUND, 18 cases pass
- `tests/unit/test_claim_precedence.py` and `tests/unit/test_claim_precedence_registered.py` — FOUND, 87 cases pass together
- Commits `df9774d` and `9973a57` — both present in `git log --all`
- Every `<acceptance_criteria>` of both tasks re-run above; all seven pass
- Plan-level `<verification>` re-run above; both lines pass
- Neither commit deletes a tracked file (`git diff --diff-filter=D --name-only HEAD~2 HEAD` is empty)
- No file outside this plan's `files_modified` list was edited (`git status --short` shows only the three pre-existing untracked `.planning` directories, which predate this session)

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
