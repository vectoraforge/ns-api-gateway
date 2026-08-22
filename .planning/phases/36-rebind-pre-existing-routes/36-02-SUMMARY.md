---
phase: 36-rebind-pre-existing-routes
plan: 02
subsystem: api
tags: [pydantic, llm, response-contract, documentation, d-12, d-13]

# Dependency graph
requires:
  - phase: 35-foundation
    provides: the deferred-items register recording D-35-11-A, the defect this plan closes
provides:
  - AnalyzeResponse.issues and AnalyzeResponse.suggestions default to empty lists — a grammatically correct phrase returns 200 instead of 500
  - .planning/todos/pending/restore-strict-structured-output.md — the general fix filed as an open backlog item
  - PROJECT.md no longer asserts constrained decoding as a shipped, validated capability
  - ROADMAP Phase 36 goal agrees with auth/registry.py on eight pre-existing routes
affects: [36-03 quota gate on POST /chats, 36-04 quota flow, 39 GET /users/me]

actuals:
  tokens: 2776
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "A knowingly-taken contract exception carries its justification in the source beside the change, naming the decision id and the defect it closes, not only in the planning artifacts"

key-files:
  created:
    - .planning/todos/pending/restore-strict-structured-output.md
  modified:
    - src/nativespeaker/api/models/llm.py
    - tests/unit/test_models.py
    - .planning/PROJECT.md
    - .planning/ROADMAP.md

key-decisions:
  - "D-12 implemented as plain `= []` defaults rather than a `default_factory`. Pydantic v2 deep-copies a mutable default per instance; `test_defaults_are_not_shared_between_instances` proves it rather than assuming it, so the plan's 'do not reach for a factory unless the test proves sharing' condition was never triggered."
  - "`resolved_mode` and `response` deliberately left required, and a new test pins that. T-36-llmshape depends on it: a truncated provider payload must still fail validation rather than reach the client as an empty success."
  - "`test_issues_required` and `test_suggestions_required` deleted, not adapted. They asserted exactly the behaviour D-35-11-A reports as the defect; keeping them in any form would re-pin the 500."
  - "The withdrawn PROJECT.md capability bullet stays on line 51 as an explicit `✗ Withdrawn — never shipped` entry inside `### Validated`, rather than being deleted or relocated. A deleted line leaves no trace that the claim was ever made; the phase's whole point is that an unexplained over-claim is what made D-35-11-A reachable."

patterns-established:
  - "Withdrawn-capability marker: a `### Validated` bullet that turns out never to have shipped is rewritten in place with `✗ Withdrawn`, the correcting decision id, and a pointer to the backlog item that would make it true — never silently removed."

requirements-completed: []

coverage:
  - id: D1
    description: "A grammatically correct phrase — the case where the model returns neither issues nor suggestions — validates to 200 with `issues == []` and `suggestions == []` instead of the 500 recorded as D-35-11-A."
    requirement: REBIND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_models.py::TestAnalyzeResponse::test_both_lists_default_to_empty"
        status: pass
      - kind: unit
        ref: "tests/unit/test_models.py::TestAnalyzeResponse::test_validates_payload_omitting_both_lists"
        status: pass
      - kind: other
        ref: "uv run python -c \"from nativespeaker.api.models.llm import AnalyzeResponse as A; A.model_validate({'resolved_mode':'analyze','response':'ok'})\" — prints `validates`"
        status: pass
    human_judgment: false
  - id: D2
    description: "The two defaults are per-instance, so mutating one response's `issues` does not leak into another's."
    requirement: REBIND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_models.py::TestAnalyzeResponse::test_defaults_are_not_shared_between_instances"
        status: pass
      - kind: other
        ref: "the plan's inline mutable-default-sharing probe — prints `ok`"
        status: pass
    human_judgment: false
  - id: D3
    description: "The D-12 exception did not disturb the shared auth error contract — REBIND-03's proof is still green."
    requirement: REBIND-03
    verification:
      - kind: unit
        ref: "tests/unit/test_error_contract.py (8 passed)"
        status: pass
      - kind: unit
        ref: "uv run pytest -q -m \"\" — 1168 passed, full suite against live PostgreSQL 17"
        status: pass
    human_judgment: false
  - id: D4
    description: "Neither PROJECT.md claim asserts constrained decoding as shipped; both cite D-13, the decisions row cites D-35-11-A as evidence, and the real fix is an open backlog item."
    requirement: REBIND-06
    verification:
      - kind: other
        ref: "grep -n 'D-13' .planning/PROJECT.md returns lines 51 and 189; grep 'D-35-11-A' returns line 189; sed -n '51p' | grep -qv '^- ✓' passes; sed -n '189p' | grep -c '✓ Good' returns 0"
        status: pass
      - kind: other
        ref: "test -f .planning/todos/pending/restore-strict-structured-output.md && grep -q '^status: open$' — OK"
        status: pass
    human_judgment: false
  - id: D5
    description: "The ROADMAP Phase 36 goal says eight pre-existing routes, agreeing with auth/registry.py and its own success criterion 2, and explains where the ninth went."
    requirement: REBIND-06
    verification:
      - kind: other
        ref: "grep -c 'nine pre-existing routes' .planning/ROADMAP.md == 0; the Phase 36 block matches 'eight pre-existing routes' once, 'users/me' once, 'Success criteria' once; the ROADMAP diff is exactly 2 changed lines"
        status: pass
    human_judgment: false

# Metrics
duration: 6min
completed: 2026-08-21
status: complete
---

# Phase 36 Plan 02: D-12 Defaults and D-13 Documentation Corrections Summary

**The product's primary route no longer returns 500 when the user's sentence is already correct, and PROJECT.md stops claiming the constrained decoding whose absence made that defect possible.**

## Performance

- **Duration:** 6 min (first task commit to last)
- **Started:** 2026-08-21T19:03:30-07:00
- **Completed:** 2026-08-21T19:06:11-07:00
- **Tasks:** 3 of 3
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- **Closed D-35-11-A at the response-model level (D-12).** `AnalyzeResponse.issues` and
  `AnalyzeResponse.suggestions` now default to `[]`, so the payload a model returns for a phrase
  with nothing to correct — `{resolved_mode, response}` and nothing else — validates instead of
  raising, and `POST /chats` answers 200 with two empty arrays. Wave ordering matters here: this
  lands before 36-03 attaches `require_quota`, so the correct-phrase failure is fixed before a user
  can be charged for it (T-36-drain).
- **Recorded the reason in the source, not only in the plan.** A sixteen-line comment beside the two
  fields names D-12 and D-35-11-A, explains that the chain is unconstrained JSON rather than a
  schema-bound call, states that this is a knowing exception to `01-foundation.md §8.3` cheap only
  because the product is pre-launch, and points at the backlog item holding the general fix.
- **Withdrew both constrained-decoding claims (D-13)** and filed
  `restore-strict-structured-output.md` as an open backlog item carrying D-35-11-A as its evidence,
  the real-provider-e2e reason it is out of a rebinding phase's scope, and the note that
  `config/prompt.txt:124` already asks for suggestions and is ignored — so prompt-strengthening is
  demonstrably not the fix.
- **Reconciled the ROADMAP route count** from nine to the eight `auth/registry.py` declares, with a
  parenthetical naming the ninth (`GET /users/me`, deleted by Phase 35 D-16, returning in Phase 39)
  so the correction reads as a reconciliation rather than a silent renumbering.

## Task Commits

1. **Task 1 (RED): failing tests for the defaulted list fields** — `8de2078` (test)
2. **Task 1 (GREEN): default `issues`/`suggestions` to empty** — `ba59a91` (fix)
3. **Task 2: withdraw the D-13 claims, file the backlog item** — `bca277e` (docs)
4. **Task 3: nine → eight pre-existing routes** — `0308533` (docs)

## Files Created/Modified

- `src/nativespeaker/api/models/llm.py` — the two field defaults plus the D-12 rationale comment.
  `FollowUpResponse`, `RejectResponse`, `Issue` and both input models are untouched.
- `tests/unit/test_models.py` — five new `TestAnalyzeResponse` cases; two obsolete ones removed
- `.planning/PROJECT.md` — line 51 (capability bullet) and line 189 (decisions row) rewritten
- `.planning/ROADMAP.md` — the Phase 36 `**Goal:**` line, one line replaced
- `.planning/todos/pending/restore-strict-structured-output.md` — new open backlog item

## Decisions Made

- **Plain `= []` over `default_factory`.** The plan permitted the simpler form unless the tests
  proved instance sharing. Pydantic v2 deep-copies a mutable default per model instance, and
  `test_defaults_are_not_shared_between_instances` confirms it against the real class rather than
  against the documentation, so the plain form stayed.
- **`resolved_mode` and `response` remain required, with a test pinning it.** The threat register's
  T-36-llmshape mitigation is precisely that D-12 defaults *only* the two list fields; without a
  test, "exactly two field defaults" is a claim in a comment that nothing enforces. The new
  `test_resolved_mode_and_response_stay_required` makes a future widening fail CI.
- **The withdrawn capability bullet stays in place rather than being deleted.** Deleting it would
  erase the evidence that the over-claim existed — and the over-claim standing unexamined is the
  causal chain this plan is correcting.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `test_issues_required` and `test_suggestions_required` contradicted D-12**

- **Found during:** Task 1 (RED phase)
- **Issue:** `TestAnalyzeResponse` already contained two cases asserting that omitting `issues` or
  `suggestions` raises `ValidationError` — exactly the behaviour D-12 removes. Leaving them would
  have made Task 1's own acceptance criterion (`uv run pytest -q` passes) unreachable.
- **Fix:** Both deleted in the RED commit, with a comment above the replacements recording that they
  pinned the D-35-11-A behaviour and were replaced rather than kept. Their two
  `# ty: ignore[missing-argument]` suppressions went with them, and `ty check src` stays clean.
- **Files modified:** `tests/unit/test_models.py`
- **Commit:** `8de2078`

### Documented departures from the plan text

**2. Task 1 committed as two commits, not one.** Task 1 carries `tdd="true"`, so the executor's TDD
flow requires a RED commit (failing tests, `8de2078`) and a GREEN commit (implementation,
`ba59a91`). The task's acceptance criterion "`git show --stat HEAD` names only
`src/nativespeaker/api/models/llm.py` and `tests/unit/test_models.py`" is written for a single
commit; across the two commits, `git show --stat 8de2078 ba59a91` names exactly those two files and
nothing else, so the criterion's intent — scope containment — holds. The plan total is four commits
rather than the three its `<verification>` block predicts.

**3. One extra test case beyond the four behaviours the plan enumerated.**
`test_resolved_mode_and_response_stay_required` is not in the plan's `<behavior>` list. It was added
because the plan's own prohibition ("not licence to relax validation anywhere else") and the
register's T-36-llmshape mitigation were otherwise unenforced by any test. Five cases were added,
not four.

**4. `requirements.mark-complete` not run.** The plan's frontmatter claims REBIND-03 and REBIND-06,
but both are also claimed by plans 36-03, 36-04 and 36-05, which deliver the substance — the barrier
rebinding and the quota statuses. This plan contributes a defect fix and three prose corrections
toward them; checking either off here would report the phase's central behaviour as done.

---

**Total deviations:** 1 auto-fixed (1 × Rule 3), 3 documented departures.
**Impact on plan:** None on scope. The auto-fix was forced by the plan's own change, and the extra
test tightens rather than widens the exception. `docker-compose.yml` and `uv.lock` were never staged.

## Issues Encountered

- **Flagged assumption on REBIND-03 stands unresolved, as the plan intended.** Edge-probe item 5 was
  carried into execution rather than silently decided. This plan's evidence for it is narrow and
  specific: `tests/unit/test_error_contract.py` is still green after the response-shape change, so
  the *auth* rejection contract is provably unchanged. Whether REBIND-03's "existing non-auth
  business error contracts unchanged" clause tolerates D-12 as a recorded exception is still a
  reviewer's call, not something this execution settled.
- **`gsd-tools query state.update-progress` fails** with "Progress field not found in STATE.md",
  as plan 36-01 reported. Known non-fatal tooling issue; not investigated.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -q` | 915 passed, 253 deselected (was 912 — net +3: five added, two removed) |
| `uv run pytest -q -m ""` | 1168 passed — full suite, live PostgreSQL 17, no regression |
| `uv run pytest tests/unit/test_error_contract.py -x` | 8 passed — REBIND-03's shared-taxonomy proof green |
| `uv run pytest tests/unit/test_models.py -k Analyze -x -q` | 9 passed |
| `uv run ruff check src tests` | clean |
| `uv run ty check src` | clean |
| Mutable-default-sharing probe | prints `ok` |
| `model_validate` probe on a payload missing both keys | prints `validates` |
| `git log --stat -4` | four scoped commits; none names `docker-compose.yml` or `uv.lock` |
| `git status --porcelain` | `docker-compose.yml` and `uv.lock` still ` M`, unstaged, uncommitted (D-15) |

No e2e or schema run was required by the plan; the full-suite run was done anyway, since D-12 changes
a served response shape and the deselected 253 include the e2e cases that exercise `POST /chats`.

## Threat Flags

None. No network endpoint, auth path or trust-boundary change is introduced. Against the plan's
register:

- **T-36-llmshape (Tampering):** mitigated as specified and now enforced by a test.
  `resolved_mode` and `response` stay required, so a truncated or wrong-mode provider payload still
  fails validation rather than reaching the client as an empty success.
- **T-36-drain (Denial of Service):** mitigated. The correct-phrase 500 is converted to a 200 in
  wave 1, before 36-03 attaches `require_quota` — the wave ordering is the mitigation and it held.
- **T-36-oracle (Information Disclosure):** accepted disposition honoured. The documentation
  over-claim was corrected as a trust issue, not treated as a security control.
- **T-36-SC (supply chain):** upheld. Zero packages installed; `uv.lock` untouched.

## Known Gaps

- **No test exercises the fix through `services/chats.py`.** D-12 is proven at the model layer.
  The `AnalyzeResponse.model_validate` call site that turned the missing fields into a 500 has no
  unit coverage — as D-35-11-A itself notes, "no unit test covers the served LLM path" — so the
  200-instead-of-500 claim rests on the model's behaviour plus the call site being a bare
  `model_validate`. A route-level case sending a correct phrase would close this; 36-03 rewires
  `POST /chats` and is the natural place.
- **The general fix is filed, not done.** The chain remains unconstrained JSON. Any *other*
  conditionally-emitted field in a future response model will reproduce the same class of defect
  until `restore-strict-structured-output.md` is picked up.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Ready. Wave 1 is complete (36-01 and 36-02 both executed), so wave 2 may start:

- `36-03` can attach `require_quota` to `POST /chats` knowing the correct-phrase path returns 200,
  so a quota-consuming request no longer charges for a guaranteed failure.
- The REBIND-03 flagged assumption is recorded and unresolved; if a reviewer disagrees with this
  plan's reading, REBIND-03's scope needs a decision before phase verification, not a re-plan.
- `docker-compose.yml` and `uv.lock` remain modified and uncommitted per D-15. The `uv.lock`
  `revision 2 -> 3` bump is still the deferred D-35-05-A.

---
*Phase: 36-rebind-pre-existing-routes*
*Completed: 2026-08-21*

## Self-Check: PASSED

All five claimed source/planning files plus this SUMMARY exist on disk, and all four claimed
commits (`8de2078`, `ba59a91`, `bca277e`, `0308533`) resolve in `git log`.
