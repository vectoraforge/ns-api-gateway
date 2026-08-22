---
phase: 37-post-auth-create-user
plan: 06
subsystem: resilience
tags: [tenacity, retry, circuit-breaker, quota, characterization-tests]

# Dependency graph
requires:
  - phase: 37-post-auth-create-user
    plan: 02
    provides: "tenacity as a direct [project].dependencies entry, and auth/retry.py — the idiom this plan converges on"
provides:
  - "src/nativespeaker/api/resilience.py — ResiliencePolicy.ainvoke running on tenacity.AsyncRetrying"
  - "_should_retry — the module-private exception predicate, and the comment explaining why it differs from auth/retry.py's result predicate"
  - "_sleep_if_positive — the retry policy's sleep, preserving the hand-rolled 'if backoff > 0' guard"
  - "tests/unit/test_resilience_retry.py — the first unit-level coverage of the on_admitted once-only contract"
affects: [40, 41, 42]

actuals:
  tokens: 7378
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Exception-based retry (retry_if_exception + reraise=True) over a seam that signals by raising — the mirror of 37-02's result-based policy, same library"
    - "Triage inside the attempt body, classification-reading in the predicate: the body decides transient/permanent once, the predicate only reads the resulting class"
    - "Unwrap a caller-owned exception OUTSIDE the retry construct, so the predicate can never inspect a class the caller chose"
    - "Characterization suite committed on its own, green against the unconverted code, before the refactor commit"

key-files:
  created:
    - tests/unit/test_resilience_retry.py
  modified:
    - src/nativespeaker/api/resilience.py

key-decisions:
  - "wait_exponential(multiplier=base, exp_base=2, max=cap) reproduces min(cap, base * 2 ** (attempt - 1)) exactly — no custom wait callable was needed. tenacity computes max(max(0, min), min(multiplier * exp_base ** (attempt_number - 1), max)) with min defaulting to 0, and attempt_number is the 1-based number of the attempt that just failed, i.e. the hand-rolled loop's own `attempt`."
  - "The predicate is retry_if_exception(_should_retry) over TransientLLMError — NOT a re-derivation of _is_transient_error. The attempt body has already triaged the failure into exactly one of TransientLLMError / PermanentLLMError, so re-judging in the predicate would be a second answer to one question."
  - "_AdmissionRejected is left wrapped inside the attempt body and unwrapped outside the AsyncRetrying construct. Unwrapping inside would hand the predicate the CALLER's exception class; a caller raising something that happened to be a TransientLLMError would have its own rejection retried."
  - "sleep=_sleep_if_positive was passed explicitly. retry_backoff_base_seconds is ge=0, and tenacity's default sleep issues asyncio.sleep(0) on a zero-length gap where the hand-rolled loop issued no sleep call at all."
  - "The trailing `raise TransientLLMError(\"LLM request failed after all retries\")` was DELETED, not kept as a guard: `return await retrying(attempt)` cannot fall through — retry_max_attempts is ge=1 and tenacity always performs a first attempt before consulting stop."
  - "DISCOVERED: tests/unit/test_services.py is NOT an oracle for the once-only on_admitted contract, contrary to the plan's premise. It mocks llm_service wholesale and tests/unit/conftest.py:143 says so explicitly. Before this plan the rule was covered only by tests/e2e/test_quota.py, behind real infrastructure."

patterns-established:
  - "Pattern 1: two tenacity policies may legitimately disagree on predicate. A seam that RETURNS a closed outcome takes retry_if_result + retry_error_callback; a seam that RAISES takes retry_if_exception + reraise=True. Both files now carry a comment naming the other so neither reads as a defect."
  - "Pattern 2: when converting a hand-rolled loop, pin its behavior in a committed characterization suite FIRST. The suite caught two silent behavior changes here that a post-hoc test would have simply blessed."
  - "Pattern 3: 37-02's src-wide adapter-method scan reads comments and docstrings, not just code. Cross-referencing an auth/ adapter seam by symbol name from any other src/ module is a red test."

requirements-completed: [CREATE-02]

coverage:
  - id: D1
    description: "on_admitted fires at most once across every attempt of one ainvoke call, including retries and including a callback that raises"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_resilience_retry.py::TestOnAdmittedFiresAtMostOnce (6 tests: success on attempt 1, retried-then-success, all-attempts-failed, raising callback spent, raising callback stops provider + breaker, no-callback case)"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -m e2e tests/e2e/test_quota.py -> 45 passed (the real charge against the real resilience layer)"
        status: pass
    human_judgment: false
  - id: D2
    description: "_AdmissionRejected re-raises the callback's own cause, records NO circuit-breaker failure, and triggers NO retry"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "test_a_raising_callback_is_spent_and_never_re_invoked (identity + __cause__ is None) and test_a_raising_callback_stops_the_provider_call_and_the_breaker (failures == successes == 0, operation.calls == 0)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A transient error retries to retry_max_attempts then raises TransientLLMError; a permanent one raises PermanentLLMError after exactly one call; QueueFullError and CircuitOpenError propagate unwrapped and unretried"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "TestErrorClassification (4 tests, incl. the real asyncio.wait_for timeout path) and TestGateAndBreakerErrorsAreNeverWrapped (2 tests, the breaker driven through a real open transition)"
        status: pass
    human_judgment: false
  - id: D4
    description: "record_failure fires exactly once per failed provider attempt and zero times on the _AdmissionRejected path"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "TestFailureAccounting — 5 parametrized cases asserting failures + successes == operation.calls"
        status: pass
    human_judgment: false
  - id: D5
    description: "Backoff is min(retry_backoff_max_seconds, retry_backoff_base_seconds * 2 ** (attempt - 1)) — the same schedule as the hand-rolled loop"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "TestBackoffSchedule — 4 tests: the formula, the cap (0.5/1.0/1.5/1.5 over a 5-attempt budget), the single-attempt no-sleep case, and the zero-backoff no-sleep-at-all case"
        status: pass
    human_judgment: false
  - id: D6
    description: "The codebase contains exactly one retry idiom: no hand-rolled attempt loop remains in src/"
    requirement: "CREATE-02"
    verification:
      - kind: other
        ref: "grep -v '^\\s*#' src/nativespeaker/api/resilience.py | grep -c 'for attempt in range' -> 0"
        status: pass
      - kind: other
        ref: "grep -rn 'for attempt|attempt in range|max_retries|while.*retr|retries \\+=|attempt \\+=' src/ --include=*.py -> 0 hits"
        status: pass
    human_judgment: false
  - id: D7
    description: "tests/unit/test_services.py passes unchanged after the conversion"
    requirement: "CREATE-02"
    verification:
      - kind: other
        ref: "git diff --stat tests/unit/test_services.py -> empty for the whole plan; 17 passed"
        status: pass
      - kind: unit
        ref: ".venv/bin/pytest -q -> 984 passed, 302 deselected"
        status: pass
    human_judgment: false

# Metrics
duration: ~14min
completed: 2026-08-22
status: complete
---

# Phase 37 Plan 06: tenacity Conversion of ResiliencePolicy Summary

**`ainvoke`'s hand-rolled attempt loop replaced by `tenacity.AsyncRetrying` under a 21-test characterization suite written first — the last hand-rolled retry loop in `src/` is gone, and the two tenacity policies now explain to each other why their predicates differ.**

## Performance

- **Duration:** ~14 min (base commit `72e3433` 23:32:04Z → summary commit)
- **Tasks:** 2
- **Commits:** 3 (2 task commits + this summary)
- **Files:** 1 created, 1 modified (+78 / −16 on `resilience.py`, +409 on the test file)

## Accomplishments

- **`ResiliencePolicy.ainvoke` runs on `tenacity`.** `stop_after_attempt`, `wait_exponential`, `retry_if_exception(_should_retry)`, `sleep=_sleep_if_positive`, `reraise=True`. The `for attempt in range(...)` loop and its trailing fall-through `raise` are both deleted.
- **A 21-test characterization suite landed first, on its own commit** (`60c1744`), green against the *unconverted* loop. It passed byte-identical against the converted one.
- **The three non-obvious behaviors are preserved literally** and each is now pinned by a count-and-class assertion rather than by a comment: `on_admitted` fires once per request, a permanent error costs one provider call, and the `_AdmissionRejected` path records zero breaker failures.
- **One retry idiom in `src/`.** A repo-wide scan for `for attempt`, `attempt in range`, `max_retries`, `while ... retr`, `retries +=` and `attempt +=` returns zero hits.

## The exact wait configuration (asked for by the plan's `<output>`)

```python
wait=wait_exponential(multiplier=self._retry_backoff_base,
                      exp_base=2,
                      max=self._retry_backoff_max)
```

No custom wait callable was required. tenacity 9.1.4's `wait_exponential.__call__` computes

```
max(max(0, self.min), min(self.multiplier * self.exp_base ** (attempt_number - 1), self.max))
```

with `min` defaulting to `0`, and `retry_state.attempt_number` at wait time is the 1-based number of the attempt that just failed — which is exactly the hand-rolled loop's `attempt`. Since `multiplier >= 0`, the outer `max(0, ...)` is inert and the expression collapses to `min(cap, base * 2 ** (attempt - 1))`, term for term.

`TestBackoffSchedule` does not trust that derivation: it records the actual durations and asserts `[0.5, 1.0]` on a 3-attempt budget and `[0.5, 1.0, 1.5, 1.5]` on a 5-attempt budget, so the cap is exercised rather than argued.

## Behaviors the D-05 write-up did not name

**1. `tests/unit/test_services.py` is not an oracle for the once-only contract.** The plan called it "this conversion's primary oracle" and required it stay byte-identical. It is byte-identical and green — but it does not exercise the resilience layer at all. It mocks `llm_service` wholesale, and `tests/unit/conftest.py:143` states outright that "the real `on_admitted` callback never fires and this gate is never called." Before this plan, the once-only rule was covered *only* by `tests/e2e/test_quota.py`, behind real infrastructure. Had the conversion double-fired the callback, the unit suite would have been green. `tests/unit/test_resilience_retry.py` is now the unit-level oracle that was assumed to already exist.

**2. Zero backoff is a legal configuration, and the naive conversion changes its behavior.** `retry_backoff_base_seconds` is `ge=0`. The hand-rolled loop guarded with `if backoff > 0`, so a zero schedule issued *no sleep call whatsoever*; tenacity's default sleep would issue `asyncio.sleep(0)` between every attempt. Same elapsed time, but an extra event-loop yield per attempt on the product's primary route. Fixed by passing `sleep=_sleep_if_positive`; `test_zero_backoff_records_no_sleep_at_all` pins it.

**3. Where `_AdmissionRejected` is unwrapped is load-bearing, not stylistic.** The obvious conversion keeps `except _AdmissionRejected as rejected: raise rejected.cause from None` inside the attempt body. That hands the retry predicate an exception class *the caller chose*. A callback raising something that happened to be a `TransientLLMError` would then have its own rejection retried. The unwrap was moved outside the `AsyncRetrying` construct so the predicate only ever sees a class this module produced.

**4. A permanent error following a transient one stops immediately.** D-05 named the pure-transient and pure-permanent paths; the mixed sequence (transient, then permanent) is the one a real provider actually produces. It costs 2 calls and 2 `record_failure`s and raises `PermanentLLMError` — `test_a_permanent_error_after_a_transient_one_stops_immediately`.

**5. 37-02's src-wide adapter-method scan reads prose.** The first draft of `_should_retry`'s docstring named the Firebase adapter method to explain why the two predicates differ. `test_adapter_interfaces::test_foundation_calls_no_adapter_method_anywhere_in_src` failed on it: the scan is a raw text scan over `src/`, `auth/` modules are exempt and `resilience.py` is not, and a docstring counts. Reworded to describe the seam without naming the symbol, with a note saying why. Worth knowing for phases 40–42, which will cross-reference the same seam.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_should_retry`'s docstring tripped the src-wide adapter-method scan**
- **Found during:** Task 2, at the full-suite verification
- **Issue:** `test_adapter_interfaces.py::TestZeroImplementations::test_foundation_calls_no_adapter_method_anywhere_in_src` failed with `api/resilience.py: get_user_provider_data`. The scan matches raw text, so naming the adapter method inside a docstring registers as a call site.
- **Fix:** Reworded the docstring to describe the seam ("the Firebase providerData lookup that module wraps") without the symbol, plus a parenthetical explaining the constraint to the next reader. `resilience.py` was **not** added to `ADAPTER_IMPLEMENTORS` — it does not call the method, and widening the allow-list to admit prose would blunt the scan.
- **Files modified:** `src/nativespeaker/api/resilience.py` (fixed before the Task 2 commit)
- **Commit:** `2afa7fd`

### Intentional divergences from the plan text

- **The predicate is `retry_if_exception(_should_retry)` over `TransientLLMError`, not the plan's "neither `_AdmissionRejected` nor `QueueFullError` nor `CircuitOpenError` **and** satisfies `_is_transient_error`".** Those two are equivalent given the attempt body's triage, and the class check is the one that cannot drift: `_is_transient_error` is consulted exactly once per failure, in the body, rather than once in the body and once in the predicate. The named module-private predicate the plan's `<artifacts>` section calls for still exists, and its docstring carries the reasoning.
- **The trailing `raise TransientLLMError("LLM request failed after all retries")` was deleted rather than kept as a guard.** The plan permitted deletion "only if `reraise=True` provably covers it". It does: `return await retrying(attempt)` either returns or raises, `retry_max_attempts` is `ge=1`, and tenacity performs the first attempt before consulting `stop`, so there is no fall-through path and no implicit `None` return.

## Environment notes (not code changes)

- The worktree carries no `.venv` or `.env` (both gitignored, both absent from a fresh worktree). Tests were run with the main checkout's interpreter and `PYTHONPATH` pinned to the **worktree's** `src`, verified by printing `nativespeaker.api.resilience.__file__` before the first run — without it the editable-install `.pth` would have silently tested the main checkout's code. A `.env` symlink was created (gitignored, never staged).
- `ty check` cannot resolve site-packages in this environment: it reports `unresolved-import` for `openai` as well as `tenacity`, and does the same for the pre-existing `auth/retry.py` on the base commit. Pre-existing environment noise, out of scope. `ruff check src/ tests/` passes clean.

## Verification

| Command | Result |
|---|---|
| `pytest -q tests/unit/test_resilience_retry.py` (pre-conversion) | 21 passed in 0.09s |
| `pytest -q tests/unit/test_resilience_retry.py tests/unit/test_services.py` (post-conversion) | 38 passed in 0.12s |
| `pytest -q` | 984 passed, 302 deselected |
| `pytest -q -m e2e tests/e2e/test_quota.py tests/e2e/test_chats.py` | 54 passed in 33.01s |
| `grep -v '^\s*#' src/nativespeaker/api/resilience.py \| grep -c "for attempt in range"` | 0 |
| `git diff --stat tests/unit/test_services.py` | empty |
| `ruff check src/ tests/` | All checks passed |

No `-m schema` command was run; 37-04 is wave 2's only schema-suite runner.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or schema change. The four mitigations this plan owns (T-37-20 through T-37-23) each have a named test above.

## Self-Check: PASSED

- `src/nativespeaker/api/resilience.py` — FOUND (modified, imports `tenacity` at line 8)
- `tests/unit/test_resilience_retry.py` — FOUND (409 lines, 21 tests)
- Commit `60c1744` — FOUND (`test(37-06)`, one file)
- Commit `2afa7fd` — FOUND (`refactor(37-06)`, one file)
- `.planning/STATE.md` / `.planning/ROADMAP.md` — untouched, as required for a parallel worktree agent
