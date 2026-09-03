---
phase: 41-post-auth-claim-anonymous-grant
plan: 02
subsystem: infra
tags: [resilience, circuit-breaker, asyncio, tenacity, pydantic-settings, connection-pool]

# Dependency graph
requires:
  - phase: 37.5-admission-refactor
    provides: "`ResiliencePolicy.admission`, the `Admitted` token, and the twenty billing cases in tests/unit/test_quota_seam.py that this plan had to keep green"
provides:
  - "A per-attempt circuit breaker check, so a request in flight when the breaker opens dies on its next attempt with its own 503 and Retry-After"
  - "`LLMExecutionGate.inflight_slot` and `LLMExecutionGate.concurrency`, the two halves of the deleted `hold`"
  - "A quota charge that commits and releases its database connection before the request waits for a provider permit"
  - "`db.pool_size: 12` in the tracked config.yaml, with the `resilience.pool_size × 2 + 2` relation legible beside its operand"
  - "Proof that a partial YAML block deep-merges with the `DB_*` env nesting rather than replacing it"
affects: [chat path, quota billing, provider concurrency, any phase touching config/config.yaml]

actuals:
  tokens: 3242
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "A gate exposes one context manager per resource it bounds, so the caller chooses which it takes and for how long"
    - "A partial block in the tracked config.yaml deep-merges with env-supplied siblings (the `jwt:` precedent, now asserted)"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/resilience.py
    - config/config.yaml
    - tests/unit/test_resilience_retry.py
    - tests/unit/test_quota_seam.py
    - tests/unit/test_config.py
    - AGENTS.md
    - .planning/todos/done/breaker-check-moved-to-admission.md
    - .planning/todos/done/admission-holds-a-db-connection.md

key-decisions:
  - "D-14: the breaker is consulted before every attempt, not only at admission; the check sits inside the `try` so the pass-through arm is genuinely reachable and ordered first"
  - "D-15: `hold` is deleted rather than kept as a composition — nothing outside resilience.py called it, so the pair is the smaller surface"
  - "D-16: `db.pool_size: 12` lives in the tracked config.yaml, accepting that this forecloses `DB_POOL_SIZE` from .env"
  - "The plan's `requirements` field names decisions (D-14/D-15/D-16), not REQUIREMENTS.md ids, so no requirement checkbox was marked"

patterns-established:
  - "Attempt count is assertable: BreakerSpy counts `before_call`, which now fires exactly once per attempt"
  - "A permit-starved path is testable without the clock: take every permit, run the caller as a task, settle the loop, then release one"

requirements-completed: [D-14, D-15, D-16]

coverage:
  - id: D1
    description: "A request in flight when the breaker opens fails on its next attempt with the same 503 and Retry-After a fresh request gets, instead of spending its remaining attempts against a dead provider"
    requirement: "D-14"
    verification:
      - kind: unit
        ref: "tests/unit/test_resilience_retry.py#TestGateAndBreakerErrorsAreNeverWrapped::test_a_breaker_opening_mid_flight_ends_the_request_on_its_next_attempt"
        status: pass
      - kind: unit
        ref: "tests/unit/test_resilience_retry.py#TestGateAndBreakerErrorsAreNeverWrapped::test_the_full_budget_is_still_spent_while_the_breaker_stays_closed"
        status: pass
    human_judgment: false
  - id: D2
    description: "The gate-and-breaker pass-through arm is reachable again and ordered first, so a mid-flight CircuitOpenError is never recorded as a provider failure nor rewrapped into a generic 503"
    requirement: "D-14"
    verification:
      - kind: unit
        ref: "tests/unit/test_resilience_retry.py#test_a_breaker_opening_mid_flight_ends_the_request_on_its_next_attempt (asserts spy.failures == 1 and the 503/Retry-After)"
        status: pass
      - kind: other
        ref: "uv run python -c \"import inspect, nativespeaker.api.resilience as r; s=inspect.getsource(r.ResiliencePolicy.ainvoke); print(s.index('CircuitOpenError') < s.index('except Exception'))\" -> True"
        status: pass
    human_judgment: false
  - id: D3
    description: "The quota charge commits and releases its database connection before the request waits for a provider permit; a slow database no longer occupies one"
    requirement: "D-15"
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_seam.py#TestAdmissionHoldsNoProviderPermit::test_a_charge_commits_while_every_permit_is_taken"
        status: pass
      - kind: unit
        ref: "tests/unit/test_quota_seam.py#TestAdmissionHoldsNoProviderPermit::test_entering_admission_leaves_the_semaphore_untouched"
        status: pass
    human_judgment: false
  - id: D4
    description: "An open breaker or a full queue still answers 503 having spent nothing, and the twenty billing cases stay green in substance"
    requirement: "D-15"
    verification:
      - kind: unit
        ref: "tests/unit/test_quota_seam.py (22 cases, including test_a_full_queue_answers_503_and_spends_nothing and test_an_open_circuit_answers_503_and_spends_nothing)"
        status: pass
      - kind: other
        ref: "git diff of the RED commit shows zero removed lines in test_quota_seam.py — the twenty cases are untouched, only additions"
        status: pass
    human_judgment: false
  - id: D5
    description: "db.pool_size resolves to 12 against the tracked configuration file while every DB_* credential still arrives from the environment"
    requirement: "D-16"
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py#TestTheTrackedPoolSizeMergesWithTheEnvironmentCredentials::test_the_tracked_pool_size_loads_beside_the_environment_credentials"
        status: pass
      - kind: other
        ref: "uv run python -c \"from nativespeaker.api.config import EnvironmentConfig; c=EnvironmentConfig().app_config; print(c.db.pool_size, bool(c.db.host), c.resilience.pool_size)\" -> 12 True 5"
        status: pass
    human_judgment: false
  - id: D6
    description: "Both folded todos are recorded as finished rather than left open behind the phase that fixed them, and STATE.md blocker A-15 is closed"
    verification:
      - kind: other
        ref: "ls .planning/todos/pending/ lists neither; ls .planning/todos/done/ lists both, each with status: done, completed: 2026-09-02, completed_in: 41"
        status: pass
    human_judgment: false
  - id: D7
    description: "AGENTS.md § Resilience no longer states anything D-14 and D-15 made untrue"
    verification: []
    human_judgment: true
    rationale: "The realignment is prose. No test asserts its wording, and whether two sentences read in the file's own register is a judgment about writing, not a property a command can check. The diff's scope is mechanical (§ Resilience only, no new section) and was verified; its adequacy is not."

# Metrics
duration: 38 min
completed: 2026-09-02
status: complete
---

# Phase 41 Plan 02: The Two Folded Todos and the Pool Finding Summary

**The breaker is consulted before every attempt, the provider permit moved off the admission path and around the retry loop, and `db.pool_size` rose from 5 to 12 — three live defects on the chat path, closed with no change to `ChatService`.**

## Performance

- **Duration:** 38 min
- **Tasks:** 3
- **Files modified:** 8
- **Test count:** 888 passing before, 893 after (5 new cases, none removed)

## Accomplishments

- **A dead provider now costs one attempt, not ninety seconds (D-14).** `before_call()` runs at the top of every `attempt()` as well as at admission. A request admitted while the breaker was closed, whose provider then fails it open, ends on its second attempt carrying the breaker's own 503 and `Retry-After` — the same answer a fresh request gets — instead of spending its third against a provider already declared dead.
- **The pass-through arm is reachable again, and first (D-14).** The check sits *inside* the `try`, above `asyncio.wait_for`, so `except (QueueFullError, CircuitOpenError): raise` catches the breaker's refusal and re-raises it unwrapped. Under the generic arm below it, that same refusal would be counted as a provider failure and rewrapped — the system talking itself into a longer outage than the provider caused.
- **The quota charge no longer holds a provider permit (D-15).** `LLMExecutionGate.hold` split into `inflight_slot` (the promoted `_inflight_slot`) and `concurrency`. `admission()` keeps the breaker check and the slot, both instantaneous; `ainvoke()` wraps its whole `AsyncRetrying` in the permit. The charge therefore commits and releases its connection before the request waits for a permit, and the permit still covers all three attempts as one unit.
- **The pool no longer exhausts at three concurrent chat posts (D-16).** `config/config.yaml` declares `db: pool_size: 12` next to `resilience.pool_size: 5`, with the `×2 + 2` relation as a comment rather than as code. This closes STATE.md blocker A-15.
- **The merge is proved, not assumed.** Research assumption A8 held: a partial `db:` block deep-merges with the `DB_*` env nesting exactly as the `jwt:` precedent predicted. `test_config.py` now asserts the pool size and all five credentials together, so a future change to that behaviour fails here.

## Task Commits

1. **Task 1 (RED): failing cases for the per-attempt breaker check** — `2ea0f87` (test)
2. **Task 1 (GREEN): consult the circuit breaker before every attempt** — `a0c953a` (feat)
3. **Task 2 (RED): failing cases for the admission/permit split** — `b2fb46a` (test)
4. **Task 2 (GREEN): take the provider permit around the retry loop** — `33b6cff` (feat)
5. **Task 3: pool size, the rule it contradicted, and both closed todos** — `b0f8e45` (feat)

## Files Created/Modified

- `src/nativespeaker/api/resilience.py` — the per-attempt `before_call()`; `hold` split into `inflight_slot` and `concurrency`; the permit moved into `ainvoke`; three docstrings realigned
- `config/config.yaml` — a partial `db:` block declaring `pool_size: 12`, with the relation to `resilience.pool_size` as a comment above it
- `tests/unit/test_resilience_retry.py` — the mid-flight breaker case and its control; `BreakerSpy` gained a `checks` counter
- `tests/unit/test_quota_seam.py` — `TestAdmissionHoldsNoProviderPermit` (two cases) and two helpers; the twenty billing cases untouched
- `tests/unit/test_config.py` — the deep-merge case: pool size and all five `DB_*` credentials asserted together
- `AGENTS.md` — § Resilience realigned in two sentences
- `.planning/todos/done/breaker-check-moved-to-admission.md`, `.planning/todos/done/admission-holds-a-db-connection.md` — moved from `pending/`, frontmatter set to `status: done`, `completed: 2026-09-02`, `completed_in: 41`

## Decisions Made

- **`before_call()` went inside the `try`, not above it.** The plan allowed either. Above the `try`, the pass-through arm stays as unreachable as the todo found it; inside it, the arm is genuinely exercised by the new case. D-14 chose to keep that arm rather than delete it, so the placement that makes it load-bearing is the one that honours the choice.
- **`hold` was deleted rather than kept as the composition of the pair.** The plan offered both and preferred deletion "unless a caller turns up". `grep -rn "\.hold()" src tests` found none, so it went.
- **A property kept, not introduced: a request already charged is not refunded when it dies on the reopened breaker.** That was already true when all three attempts fail (`test_the_charge_is_not_refunded_when_the_provider_call_fails`), and the quota code deliberately has no refund path. No refund path was built.
- **The trade-off `db:` in the tracked YAML buys.** That file is authoritative for anything it declares, so this forecloses `DB_POOL_SIZE` from `.env`. Nothing sets it today and `.env.example` does not document it, which is why the trade is worth making. If a deployment later needs a per-environment pool size, the value moves to `config.py`'s field default and the YAML key goes.
- **No requirement checkbox was marked.** The plan's `requirements` field names decisions (D-14/D-15/D-16) rather than REQUIREMENTS.md ids — the plan says so explicitly in its objective. Running `requirements mark-complete` on decision ids would have edited the wrong thing, so it was skipped.

## Deviations from Plan

### Auto-fixed Issues

None. No bug, missing critical functionality, or blocker was encountered — three tasks, five commits, no fix attempts.

### Criterion amended in wording, not in substance

**1. Task 2's `_semaphore` grep is unsatisfiable under the design the same task prescribes**

- **Found during:** Task 2 (verifying acceptance criteria)
- **Criterion as written:** `'_semaphore' in inspect.getsource(ResiliencePolicy.ainvoke), '_semaphore' in inspect.getsource(ResiliencePolicy.admission)` should print `True False`. It prints `False False`.
- **Why:** the same task's action text asks for a *public* `concurrency` context manager on the gate, and for `ainvoke` to wrap its retry loop in it. Routed that way, `ainvoke` never names `_semaphore` — only `LLMExecutionGate.concurrency` does. Satisfying the grep literally would mean `ainvoke` reaching past the public manager into `self._gate._semaphore`, which is the design the criterion exists to protect.
- **Substantive equivalent run instead:** `'concurrency' in getsource(ainvoke), 'concurrency' in getsource(admission)` prints `True False`, and `grep -n "_semaphore" resilience.py` returns exactly two lines — its construction, and the single `async with` inside `LLMExecutionGate.concurrency`.
- **Impact:** none on behaviour. The property the criterion asserts — the permit is taken in `ainvoke` and not in `admission` — holds and is verified.

---

**Total deviations:** 0 auto-fixed. 1 acceptance criterion satisfied by an equivalent check rather than its literal wording.
**Impact on plan:** none. Every behavioural criterion passed as written.

## Issues Encountered

- **`state add-decision --summary-file` rejects `/tmp` paths.** The SDK confines file inputs to the repository root, so the three decision texts were written under `.planning/.tmp/` and removed after. Worth knowing for the next executor: `mktemp` will not work with these flags.

## Known Stubs

None. No hardcoded empty value, placeholder, or TODO marker was introduced; no test was skipped (`0 skipped` across all three suites the plan names).

## Threat Flags

None. The plan's register (T-41-11 … T-41-15) is fully mitigated by the three tasks, and no new security-relevant surface was introduced: `resilience.py` sees an operation callable and a token, never a request body, and no network endpoint, auth path, or schema changed. T-41-SC is not reachable — nothing was installed, and `pyproject.toml` was not touched.

## User Setup Required

None — no external service configuration required. `db.pool_size` is declared in the tracked configuration file, so no environment variable needs adding.

## Next Phase Readiness

- **Ready for 41-03.** This plan shares no file with the claim-anonymous-grant endpoint work: `resilience.py`, `config/config.yaml`, three unit test files and `AGENTS.md`.
- **One thing a later reader should know:** `db.pool_size` is now set by the tracked YAML, so `DB_POOL_SIZE` in a `.env` will be silently ignored. If per-environment pool sizing is ever needed, delete the YAML key and change `config.py`'s field default instead.
- **The deferred latency item (37-10) is untouched and still open** — the ~48s worst-case provider latency on the completion path is a policy decision on a shared budget, not something D-14 resolves. D-14 only bounds the case where the breaker has already opened.

---
*Phase: 41-post-auth-claim-anonymous-grant*
*Completed: 2026-09-02*

## Self-Check: PASSED

Every file named in `key-files.modified` exists on disk, all six commit hashes resolve in `git log --all`, the working tree is clean, and the full suite is green at 893 passed / 0 failed / 0 skipped.
