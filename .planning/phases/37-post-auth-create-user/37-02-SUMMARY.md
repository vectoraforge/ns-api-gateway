---
phase: 37-post-auth-create-user
plan: 02
subsystem: auth
tags: [tenacity, retry, firebase, adapters, dependencies, uv]

# Dependency graph
requires:
  - phase: 35-foundation
    provides: "auth/adapters.py (ProviderDataOutcome/ProviderDataResult, FirebaseAdminAdapter), errors.VERIFICATION_TEMPORARILY_UNAVAILABLE, models/auth.AuthEventResult, the auth/ package import root (D-23), and tests/unit/test_adapter_interfaces.py's src-wide adapter-method scan"
provides:
  - "tenacity as a direct [project].dependencies entry"
  - "src/nativespeaker/api/auth/retry.py — FIREBASE_LOOKUP_ATTEMPTS, lookup_with_retry, LOOKUP_UNAVAILABLE_RESULT, LOOKUP_UNAVAILABLE_ERROR_CLASS"
  - "both retry names re-exported from nativespeaker.api.auth"
  - "ADAPTER_IMPLEMENTORS — a named, method-scoped allow-list for the src-wide adapter-method scan, plus the pure scan helper and two control tests"
  - "removal of auth/budgets.py, tests/unit/test_budgets.py, and the four budget re-exports"
affects: [37-05, 40, 41, 42, 11]

actuals:
  tokens: 12330
  tasks: 3
  commits: 4

tech-stack:
  added: [tenacity>=9.1.4]
  patterns:
    - "Result-based retry (retry_if_result) over adapters that return a closed outcome enum rather than raising"
    - "retry_error_callback as the mandatory exhaustion path for result-based retries — reraise=True cannot substitute"
    - "Named, method-scoped allow-list with a pure scan helper and control tests, in place of widening a prohibition's skip"

key-files:
  created:
    - src/nativespeaker/api/auth/retry.py
    - tests/unit/test_firebase_retry.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/nativespeaker/api/auth/__init__.py
    - src/nativespeaker/api/auth/adapters.py
    - tests/unit/test_adapter_interfaces.py

key-decisions:
  - "D-04's stated retry_if_exception_type predicate was NOT used: get_user_provider_data returns a closed ProviderDataResult and never raises, so an exception predicate would match nothing and §7.1's 3 attempts would silently collapse to 1. The predicate is retry_if_result."
  - "retry_error_callback is mandatory, not optional: reraise=True re-raises an ORIGINAL exception and a result-based retry has none, so exhaustion would surface as tenacity.RetryError — a 500 where §7.1 earns a 503."
  - "Phase 35 D-06 is SUPERSEDED. It claimed phases 37/40/41/42 would import the budget seam by name; they import the tenacity idiom from auth/retry.py instead."
  - "D-35-05-A is CLOSED. Its instruction was to run uv lock deliberately and commit the result on its own."
  - "No wait, backoff, or jitter: §02 step 8 specifies attempt counts only and each attempt already carries the adapter's fixed 5-10 s transport timeout."
  - "The src-wide adapter-method scan was rescoped to an allow-list, not skipped or deleted, and landed in the same commit as the module that made it fire."

patterns-established:
  - "Pattern 1: an adapter seam that returns a closed outcome enum is retried with retry_if_result and a retry_error_callback that returns the last result — never with retry_if_exception_type, never with reraise=True."
  - "Pattern 2: the exhaustion mapping (internal audit result + client error class) lives as named module constants, not as a literal repeated at each of §7.1's five read points."
  - "Pattern 3: a prohibition test that acquires a legitimate exception grows a named allow-list plus a positive control and an entry-scope control, so what ships is demonstrably an allow-list and not a deleted assertion."

requirements-completed: [CREATE-02]

coverage:
  - id: D1
    description: "tenacity is a direct [project].dependencies entry and the lockfile is consistent"
    requirement: "CREATE-02"
    verification:
      - kind: other
        ref: "uv lock --check"
        status: pass
      - kind: other
        ref: ".venv/bin/python -c \"import importlib.metadata as m; print(m.version('tenacity'))\" -> 9.1.4"
        status: pass
    human_judgment: false
  - id: D2
    description: "auth/budgets.py and tests/unit/test_budgets.py are gone, the auth package still imports, and no docstring names a module that does not exist"
    requirement: "CREATE-02"
    verification:
      - kind: other
        ref: "grep -rn 'BudgetGate|BudgetExhausted|auth.budgets' src/ tests/ -> 0 hits"
        status: pass
      - kind: unit
        ref: ".venv/bin/python -c 'import nativespeaker.api.app.main' + hasattr assertions on the auth package"
        status: pass
    human_judgment: false
  - id: D3
    description: "The Firebase providerData lookup retries exactly as §7.1 specifies and returns rather than raises on exhaustion"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_firebase_retry.py (18 tests: exact per-outcome attempt counts 3/2/1/1/1, no escaping RetryError under any of the four outcomes, and the exhaustion mapping constants)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The src-wide adapter-method scan carries a named, method-scoped allow-list and is still provably live"
    requirement: "CREATE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py (56 tests, incl. the two *_control tests and the allow-list existence check)"
        status: pass
      - kind: other
        ref: "liveness probe: appending a line naming get_user_provider_data to a non-exempt module -> pytest exit 1; reverted -> exit 0"
        status: pass
    human_judgment: false

# Metrics
duration: ~22min
completed: 2026-08-22
status: complete
---

# Phase 37 Plan 02: tenacity Retry Policy Summary

**`auth/budgets.py`'s 150-line one-name budget protocol replaced by a 65-line `tenacity` policy with a result-based predicate, a mandatory `retry_error_callback` exhaustion path, and a rescoped src-wide adapter-method scan that names its one legitimate caller.**

## Performance

- **Duration:** ~22 min (approximate — the start timestamp was not captured before the reading phase; first commit 2026-08-22T23:14:12Z)
- **Started:** ~2026-08-22T23:04:00Z
- **Completed:** 2026-08-22T23:25:30Z
- **Tasks:** 3
- **Files modified:** 9 (2 created, 5 modified, 2 deleted)

## Accomplishments

- `tenacity>=9.1.4` promoted to a direct dependency with `uv.lock` regenerated and committed on its own, **closing D-35-05-A**.
- `auth/budgets.py` (156 lines) and `tests/unit/test_budgets.py` (313 lines) deleted together with all four re-exports and every docstring reference; **Phase 35 D-06 is superseded**.
- `auth/retry.py` lands the one retry idiom the codebase will use: `stop_after_attempt(3)` + `retry_if_result` + `retry_error_callback`, with the `firebase_lookup_unavailable` → `verification_temporarily_unavailable` mapping preserved as two named constants.
- `tests/unit/test_adapter_interfaces.py`'s src-wide scan rescoped to `ADAPTER_IMPLEMENTORS`, a method-scoped allow-list with a pure helper and two control tests — in the same commit as the module that made it fire.

## Task Commits

1. **Task 1: Promote tenacity to a direct dependency (D-06)** — `2538e8e` (chore)
2. **Task 2: Delete auth/budgets.py and every reference to it (D-04)** — `551803a` (refactor)
3. **Task 3: The one tenacity retry policy** — `b176415` (test, RED) → `9b9c83b` (feat, GREEN)

No REFACTOR commit: the GREEN implementation needed no cleanup.

## Files Created/Modified

- `src/nativespeaker/api/auth/retry.py` **(new)** — `FIREBASE_LOOKUP_ATTEMPTS = 3`, `_is_retryable`, `lookup_with_retry`, and the two exhaustion-mapping constants. The module docstring states why the predicate is `retry_if_result`, why `retry_error_callback` cannot be replaced by `reraise=True`, and that `user_not_found` / `selection_failure` spend no attempts.
- `tests/unit/test_firebase_retry.py` **(new)** — 18 tests against a counting fake adapter.
- `pyproject.toml`, `uv.lock` — the `tenacity` direct entry.
- `src/nativespeaker/api/auth/__init__.py` — four budget names out, `FIREBASE_LOOKUP_ATTEMPTS` and `lookup_with_retry` in; `__all__` still ASCII-sorted.
- `src/nativespeaker/api/auth/adapters.py` — "Budget wiring" → "Retry wiring", pointing at `auth/retry.py`.
- `tests/unit/test_adapter_interfaces.py` — `ADAPTER_IMPLEMENTORS`, `_adapter_method_offenders`, three new assertions, amended module docstring.
- `src/nativespeaker/api/auth/budgets.py`, `tests/unit/test_budgets.py` **(deleted)**.

## Decisions Made

Recorded in `key-decisions` above. The three that later phases must carry:

1. **D-04's `retry_if_exception_type` was wrong and was not used.** `FirebaseAdminAdapter.get_user_provider_data` *returns* a `ProviderDataResult`; it never raises. An exception predicate would never fire, so the 3-attempt budget would silently become a 1-attempt one (T-37-04). The predicate is `retry_if_result(_is_retryable)`, true only for `ProviderDataOutcome.retryable_failure`.
2. **Phase 35 D-06 is superseded.** Phases 40/41/42 must reference `auth/retry.py` — `FIREBASE_LOOKUP_ATTEMPTS`, `lookup_with_retry`, `LOOKUP_UNAVAILABLE_RESULT`, `LOOKUP_UNAVAILABLE_ERROR_CLASS` — rather than the budget seam D-06 promised them by name. Phase 11 (`sign-out-all`) likewise: `adapters.py`'s `revoke_refresh_tokens` docstring now points it at this idiom instead of at "the budget wiring".
3. **D-35-05-A is closed.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 1's version-check verify command names an attribute tenacity 9.1.4 does not have**
- **Found during:** Task 1
- **Issue:** The acceptance criterion `.venv/bin/python -c "import tenacity; print(tenacity.__version__)"` raises `AttributeError: module 'tenacity' has no attribute '__version__'` — tenacity dropped the dunder.
- **Fix:** Verified with `importlib.metadata.version("tenacity")`, which prints `9.1.4`. The criterion's intent (the pinned version is importable) holds.
- **Verification:** `9.1.4` printed; `tenacity.AsyncRetrying` resolves.
- **Committed in:** `2538e8e`

**2. [Rule 3 - Blocking] The worktree had no `.venv`**
- **Found during:** Task 1
- **Issue:** Every `<verify>` in the plan invokes `.venv/bin/python` / `.venv/bin/pytest`, and a fresh worktree carries no virtualenv (`.venv/` is gitignored).
- **Fix:** `uv sync` — already Task 1's own instruction — created it in the worktree.
- **Verification:** All subsequent `.venv/bin/...` verifies ran.
- **Committed in:** n/a (gitignored)

**3. [Rule 1 - Bug] Task 3 carries two mutually contradictory requirements about `retry_if_exception_type`**
- **Found during:** Task 3
- **Issue:** The action mandates a module docstring stating "why the predicate is `retry_if_result` and not `retry_if_exception_type`", while an acceptance criterion requires that `retry.py` "does NOT contain `retry_if_exception_type`". As literal text checks these cannot both hold.
- **Fix:** Honored the docstring requirement (it is the load-bearing one — the next reader's protection against reintroducing the bug) and verified the criterion's *intent* with a stronger AST check instead of a grep: the name is neither imported nor referenced anywhere in code. Its single occurrence is line 3 of the module docstring.
- **Verification:** AST walk over `retry.py` — `imported = [AsyncRetrying, AuthEventResult, ErrorClass, ProviderDataOutcome, ProviderDataResult, VERIFICATION_TEMPORARILY_UNAVAILABLE, retry_if_result, stop_after_attempt]`; `retry_if_exception_type referenced in code: False`.
- **Committed in:** `9b9c83b`

**4. [Rule 2 - Missing Critical] Two further `adapters.py` docstring references to the deleted mechanism**
- **Found during:** Task 2
- **Issue:** The plan scopes the docstring edit to the "Budget wiring" paragraph (lines 22-27), but `get_user_provider_data` was described as "Budget-gated" and `revoke_refresh_tokens` pointed phase 11 at "the budget wiring" — both naming a mechanism that no longer exists. Task 2's `<done>` is "no docstring names a module that no longer exists."
- **Fix:** "Budget-gated" → "Retry-gated"; the phase-11 clause now points at the `auth/retry.py` tenacity idiom rather than a second hand-rolled loop.
- **Verification:** `grep -n "auth.budgets" adapters.py` → 0; `pytest tests/unit/test_adapter_interfaces.py` (which asserts on this module's docstrings) → 56 passed.
- **Committed in:** `551803a`

**5. [Rule 2 - Missing Critical] `__all__` reflow after the four removals**
- **Found during:** Task 2
- **Issue:** Deleting four names in place left the fill-wrapped block ragged, which the file's own docstring convention ("`__all__` comes first and is alphabetized") does not tolerate.
- **Fix:** Reflowed at the file's existing ~100-char wrap width, after asserting `sorted(names) == names` to confirm the list really is plain ASCII-sorted before touching its order.
- **Verification:** `ruff check` clean; the assertion held both before removal and after Task 3's two additions.
- **Committed in:** `551803a`, `9b9c83b`

**6. [Rule 3 - Blocking] Stale `src/ns_api_gateway.egg-info/SOURCES.txt` still listed `budgets.py`**
- **Found during:** Task 2
- **Issue:** The acceptance grep over `src/` returned 1 hit — a gitignored build artifact left stale by the editable install, not a source reference.
- **Fix:** `uv sync --reinstall-package ns-api-gateway`.
- **Verification:** The grep returns 0.
- **Committed in:** n/a (gitignored)

### Scope additions (tests beyond the listed behaviors)

Three tests in `test_firebase_retry.py` go past the plan's `<behavior>` list, each guarding a §7.1 rule the policy could break silently:
- `issuer` and `subject` are forwarded on **every** attempt (§7.1's per-call client selection must hold for retries too, or a retry could reach an ambient client);
- an `ok` result's `entries` pass through untouched (the policy decides whether to call again and nothing else);
- the policy is agnostic to a sync or async adapter — `AsyncRetrying` handles both, which matters because RESEARCH Pattern 2 anticipates plan 37-05 offloading the sync SDK call to a thread.

### Scope reductions / non-edits

- **`adapters.py:280`** ("Each call is gated by its own named fail-closed budget…") was left alone. It is inside `VendorProofAdapter`'s docstring describing a *phase 06/07* per-call budget concept; it does not name this module, and the vendor-proof seams are outside this plan.
- **`tests/unit/test_audit_details.py:75`**'s `budgets_consulted` was left alone, as the plan instructs — it is a `details.verification` sub-key name in the §4.4 audit shape.

---

**Total deviations:** 6 auto-fixed (2 bugs, 3 missing-critical, 1 blocking) + 3 scope additions.
**Impact on plan:** No scope creep. Deviations 1 and 3 correct plan text that could not be satisfied as written; 4, 5 and 6 close gaps the plan's own `<done>` clauses require. The declared file list was not exceeded.

## Issues Encountered

**20 pre-existing test failures in `tests/unit/test_challenge_ids.py` — NOT caused by this plan, NOT fixed here.**

Every failure is `TypeError: ChallengeStore.issue() got an unexpected keyword argument 'operation_variant'`. Proven pre-existing at this worktree's base commit `cf6b44f`: `challenges.py` contains **zero** `operation_variant` references there while `test_challenge_ids.py` contains **11** — the source was stripped without the test being updated. That is plan **37-01**'s declared scope (removing `core.auth_challenges.operation_variant`), which is running concurrently in a separate worktree.

Not touched, deliberately: it is outside this plan's declared files, and editing `challenges.py` or `test_challenge_ids.py` here would collide with 37-01 at merge.

**Consequence for the acceptance criteria:** the criterion `.venv/bin/pytest -q` exits 0 does **not** hold on the full suite. It holds on everything this plan can affect:

| Run | Result |
|---|---|
| `pytest -q` (full) | 20 failed, 911 passed — all 20 pre-existing, all in `test_challenge_ids.py` |
| `pytest -q --ignore=tests/unit/test_challenge_ids.py` | **874 passed, 0 failed** |
| Same, at Task 2 (before the retry module existed) | 853 passed, 0 failed |

`tests/unit/test_services.py` passes unchanged, as the plan's `<verification>` requires — D-05's once-only `on_admitted` contract is undisturbed.

**Expect the full suite to go green once 37-01 merges.** If it does not, the residue is 37-01's, not this plan's.

## must_haves verification

| Truth | Result |
|---|---|
| `tenacity` is a direct `[project].dependencies` entry and `uv lock --check` exits 0 | PASS |
| `auth/budgets.py` and `tests/unit/test_budgets.py` no longer exist and nothing under `src/` imports them | PASS (grep → 0) |
| A lookup returning `retryable_failure` is attempted exactly 3 times | PASS |
| A lookup returning `user_not_found` is attempted exactly 1 time and spends no further attempt | PASS (also pinned for `selection_failure` and first-attempt `ok`) |
| 3× `retryable_failure` RETURNS the last `ProviderDataResult`; `RetryError` never escapes | PASS (identity-asserted against the third scripted result) |
| The exhaustion path still carries `firebase_lookup_unavailable` → `VERIFICATION_TEMPORARILY_UNAVAILABLE` | PASS (503, code `verification_temporarily_unavailable`) |
| The scan carries a named, method-scoped allow-list with a control case | PASS (`ADAPTER_IMPLEMENTORS`, 2 `*_control` tests, existence check) |

**Liveness probe, run both ways once as the plan requires:** appending a line naming `get_user_provider_data` to a non-exempt module under `src/nativespeaker/` → `pytest -q tests/unit/test_adapter_interfaces.py` exits **1**. Reverting that line → exits **0**. The probe restored the file byte-for-byte.

## Known Stubs

None. No stub values, placeholder text, skipped tests, or unrun `<verify>` commands were left behind by this plan.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 37-05 must add the second `ADAPTER_IMPLEMENTORS` entry** (`api/auth/firebase.py`) in the commit that creates the concrete adapter, exactly as this plan added the first. The entry-scope control takes `next(iter(ADAPTER_IMPLEMENTORS))` rather than a hard-coded path, so it needs no edit.
- **`lookup_with_retry`'s `adapter` parameter is intentionally unannotated.** The `FirebaseAdminAdapter` Protocol declares `get_user_provider_data` as sync; if 37-05 offloads the SDK call and exposes it async, an annotation naming the Protocol would be false. `AsyncRetrying` handles either, and a test pins that.
- **Blocker for phase verification, not for the next plan:** the full unit suite is red until 37-01 lands (see Issues Encountered).

## Self-Check: PASSED

- Created files exist on disk: `src/nativespeaker/api/auth/retry.py`, `tests/unit/test_firebase_retry.py`, `.planning/phases/37-post-auth-create-user/37-02-SUMMARY.md`.
- Deleted files confirmed gone: `src/nativespeaker/api/auth/budgets.py`, `tests/unit/test_budgets.py`.
- All commits present in `git log`: `2538e8e`, `551803a`, `b176415`, `9b9c83b`, and this SUMMARY commit.
- Working tree clean; `.planning/STATE.md` and `.planning/ROADMAP.md` untouched (`git diff cf6b44f..HEAD --` on both returns empty).
- TDD gate sequence intact: `test(37-02)` (`b176415`, RED) precedes `feat(37-02)` (`9b9c83b`, GREEN).

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-22*
