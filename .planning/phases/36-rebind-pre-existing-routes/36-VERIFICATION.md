---
phase: 36-rebind-pre-existing-routes
verified: 2026-08-22T04:53:36Z
status: human_needed
score: 6/6 truths verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/6
  gaps_closed:
    - "Every pre-existing route serves as it did in v1.6, apart from auth rejections now using the shared error classes (ROADMAP SC1 / REBIND-06). All five confirmed pre-provider-rejection charge paths (unsupported language, chat-count limit, chat not found, message-count limit, circuit-open/queue-full backpressure) now cost nothing, independently re-confirmed by re-running the persisted suite plus two verifier-authored behavioral probes for the two sub-cases the persisted suite still does not cover."
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Whether REBIND-02's 'increment the bounded-cardinality counter metric' on rejection covers quota rejections (429) in addition to barrier/auth rejections."
    expected: "A ruling on whether the phase's own flagged, deliberately-unresolved reading (structured log only, no counter increment, for quota 429s) satisfies REBIND-02 as marked complete in REQUIREMENTS.md, or whether a second counter is required."
    why_human: "Requirement-text interpretation the phase's own authors declined to resolve unilaterally (36-05-SUMMARY.md, 'Flagged assumption carried forward — REBIND-02'); unchanged by the three gap-closure commits (none touch audit/telemetry code). Not decidable from code or tests alone."
---

# Phase 36: Rebind Pre-existing Routes Verification Report

**Phase Goal:** Phase 36 is the first fully working application — rebind the eight pre-existing routes onto the v2.0 grant model so the chat quota path works end to end (spec §8, plus SHARED-INVARIANTS.md).
**Verified:** 2026-08-22
**Status:** human_needed
**Re-verification:** Yes — after gap closure (three inline commits, no gap PLAN: `473b377` RED, `4fb242a` GREEN, `df73f89` WR-01 test)

## What changed since the prior verification

`git show --stat` on all three commits confirms exactly these files moved, nothing in `.planning/`:
`src/nativespeaker/api/{app/dependencies.py, auth/registry.py, quota.py, resilience.py, routers/chats.py, services/chats.py, services/llm.py}` and `tests/{e2e/conftest.py, e2e/test_quota.py, unit/conftest.py, unit/test_route_registry.py}`. `src/nativespeaker/api/database/grants.py` (the resolver's SQL) and `src/nativespeaker/api/quota.py`'s `consume_quota` function body are **byte-identical** to the pre-fix commit (`git diff 7b09291 HEAD -- src/nativespeaker/api/quota.py` shows only docstring/comment changes plus a new, additive `QuotaGate` class) — confirmed by direct diff, not assumed.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /health/ready` is reachable unauthenticated; `GET /`, `GET /examples`, and all five `/chats` routes reject an unauthenticated caller (SC2 / REBIND-01). | ✓ VERIFIED (regression-checked) | `auth/registry.py:68-86`'s 8-route `REGISTRY` tuple is unchanged in shape/category. Quick regression: I re-ran the full suite myself (below) — `tests/unit/test_route_registry.py::TestAssertionPasses::test_real_app_registry_matches_the_real_router` and `tests/e2e/test_audit_writer.py::TestOffPathRequestsWriteNothing` both pass against the rewritten registry. |
| 2 | No `audit.auth_events` row is written by any of the eight routes at any outcome, including on rejection (SC3 / REBIND-02). | ✓ VERIFIED (no-row half); counter half still an open question | Unchanged by this fix — `barrier.py`/`registry.py`'s `operation=None` on all 8 entries and the audit writer are untouched by the three commits. `tests/e2e/test_quota.py::TestAQuotaRejectionWritesNoAuditRow` (2 cases) re-run and pass. The counter-increment half of REBIND-02's text remains the same flagged, unresolved reading as before — see Human Verification. |
| 3 | The quota flow resolves one effective grant, locks grant-then-usage ascending by id, fails closed on a missing usage row, performs lazy rollover in the same transaction, and never lets `remaining` go negative (REBIND-05). | ✓ VERIFIED (regression-checked, logic unchanged) | `consume_quota` (`quota.py:66-166`) is byte-for-byte identical to the pre-fix commit — confirmed by `git diff 7b09291 HEAD`. Re-ran `tests/schema/test_grant_locks.py` (4 passed) and `tests/unit/test_quota_resolver.py` (38 passed) myself; both green. |
| 4 | The application starts and every pre-existing route serves as it did in v1.6, apart from auth rejections now using the shared error classes (SC1 / REBIND-06). | ✓ VERIFIED | **The prior gap. Closed — independently re-derived, not taken on trust.** See "REBIND-06 deep-dive" below for the full rejection-site sweep, the tests I re-ran myself, and the two behavioral probes I wrote to cover what the persisted suite still does not. |
| 5 | Auth rejections on the eight routes surface through the shared error taxonomy while existing non-auth business error contracts are unchanged (REBIND-03). | ✓ VERIFIED (partial, by design — unchanged) | `errors.py` and `models/api.py` are untouched by the three commits (confirmed: not in any of the three `git show --stat` file lists). Re-ran `tests/unit/test_error_contract.py` (8 passed). Same explicitly-scoped reading as the prior verification: the auth half is proven, the business-contract half carries D-12's known narrow exception, and REQUIREMENTS.md correctly leaves REBIND-03 unchecked rather than over-claiming. Not a gap. |
| 6 | A missing usage row fails a quota-checked chat request closed rather than minting one — the `quota_checked_request` admission entry is void per D-05 (SC4). | ✓ VERIFIED (regression-checked, logic unchanged) | Same unchanged `consume_quota` logic as truth 3. `tests/e2e/test_quota.py::TestAGrantWithNoUsageRow` (2 cases) re-run and pass — 500, and the usage row stays absent afterward. |

**Score:** 6/6 truths verified (REBIND-03 counted as satisfied on its own explicitly-scoped reading, per the prior verification's reasoning, which this pass did not need to revisit since nothing touched it; REBIND-06 is the truth that flipped from FAILED to VERIFIED this pass)

### REBIND-06 deep-dive (the truth that failed last time)

This is a **behavior-dependent truth** — a cancellation/ordering invariant ("nothing downstream of the charge callback can reject the request for free," and its mirror, "nothing upstream of it can be charged"). Per the verification methodology, presence and wiring are not sufficient here; I required either a passing pre-existing test or my own direct execution for every claim below.

**1. Exhaustive rejection-site sweep (code reading, adversarial — looking for anything the executors' own list of five might have missed).** I read every `raise` reachable from `ChatService.create_chat`, `.send_message`, `.ask_llm`, `LLMService.ainvoke`, `ResiliencePolicy.ainvoke`, `LLMExecutionGate.run`, and `CircuitBreaker.before_call`, and classified each by position relative to the charge:

| Rejection | Raised at | Charged? | How I confirmed |
|---|---|---|---|
| `UnsupportedLanguageError` (400) | `services/chats.py:107-108`, before `ask_llm` | No | `tests/e2e/test_quota.py::TestNoPreProviderRejectionIsCharged::test_an_unsupported_language_is_not_charged` — re-run, passes |
| `ChatHistoryLimitError`, chat-count (400) | `services/chats.py:110-112`, before `ask_llm` | No | `...::test_the_chat_history_limit_is_not_charged` — re-run, passes |
| `InvalidChatError`, chat not found (404) | `services/chats.py:131-132`, before `ask_llm` | No | `...::test_a_chat_that_does_not_exist_is_not_charged` — re-run, passes |
| `ChatHistoryLimitError`, message-count (400) | `services/chats.py:134-135`, before `ask_llm` | No | `...::test_the_message_history_limit_is_not_charged` — re-run, passes |
| `CircuitOpenError` (503) | `resilience.py:56`, before `_gate.run` → before `on_admitted` | No | `...::test_an_open_circuit_is_not_charged` — re-run, passes |
| `QueueFullError` (503) | `resilience.py:103-104`, inside `_inflight_slot()`, before `_semaphore`/`on_admitted` | No | **No persisted test exists for this specific case** (the suite tests only the circuit-open half of "circuit open/queue full"). I confirmed it myself — see Behavioral Spot-Checks, probe 2. |
| `MissingUsageRowError` / `MultipleEffectiveGrantsError` / `UnknownTierError` (500, inside the charge itself) | `quota.py:122,106,147` | No | `QuotaGate.charge` (`quota.py:213-222`) wraps `consume_quota` in `try: ...; await session.commit() / except Exception: await session.rollback(); raise` — `session.commit()` is the line *after* `consume_quota` returns, so **any** exception from `consume_quota` skips it unconditionally. Confirmed by reading the control flow (no dynamic dispatch to obscure it) and by the existing `tests/e2e/test_quota.py::TestAGrantWithNoUsageRow` (real DB round trip, row stays absent) and `tests/unit/test_quota_resolver.py::TestMissingUsageRow`/`TestUnknownTier` (in-memory state never mutated). |
| `QuotaExceededError` (429, no grant / exhausted) | `quota.py:89,159` | No (by design — this *is* the charge decision) | Pre-existing, unaffected, re-run and green. |
| `OutOfScopeError`, `AnalysisError`, provider timeouts/errors | After `llm_response` is returned, i.e. *after* the provider call succeeded or was genuinely attempted | Yes — correctly, per D-11 | Out of REBIND-06's scope by the phase's own stated boundary; unchanged behavior. |

No rejection reachable before the provider call was found uncharged-for-the-wrong-reason or charged-when-it-shouldn't-be. **Judgment on the three internal-error branches** (task-specified open question): not charging them is correct — they represent broken invariants (near-unreachable in real Postgres, guarded by a partial unique index and a FK respectively), no analysis is ever performed on those paths, and D-11's own stated boundary ("a request the service refused itself is not charged") covers a service refusing itself due to its own broken state exactly as much as it covers a business rule refusing the caller.

**2. D-04 (no grant/usage lock spans the provider round trip).** `QuotaGate.charge` (`quota.py:213-222`) opens, commits/rolls back, and closes its session entirely inside the `async with self._session_factory() as session:` block, which is fully `await`ed before `admit_once()` (`resilience.py:156-163`) returns, which itself runs, and is fully awaited, before `LLMExecutionGate.run` (`resilience.py:113-130`) proceeds to `return await operation()` — the actual provider call. I grepped the whole call chain (`quota.py`, `resilience.py`, `services/chats.py`, `services/llm.py`, `app/dependencies.py`) for `create_task`/`ensure_future`/`gather`/`TaskGroup` and found none — the sequencing is a straight-line `await` chain with no concurrent path that could reorder it. Confirmed structurally, and consistent with all passing e2e cases that go all the way to a served 200 (`TestASeededGrantIsAdmitted`, `TestACorrectPhraseIsServedAndCharged`).

**3. Double-charge-on-retry guard, and no-retry-on-admission-rejection (task-specified check).** No persisted test in the repository exercises `ResiliencePolicy`'s retry loop against the admission callback — I wrote and ran two throwaway scripts directly against the real, imported production classes (not mocks) to close this gap myself:

- A flaky operation that fails transiently twice then succeeds, with an `on_admitted` counter: **`on_admitted` fired exactly once across 3 attempts.**
- An `on_admitted` that raises on its one call: **the provider `operation()` was never invoked, no retry occurred, and the original exception propagated unwrapped** (not turned into a `TransientLLMError`/503, not recorded against the circuit breaker).

Both match the code's own reasoning (`resilience.py:145-163`: `admitted` is set `True` *before* `await on_admitted()`, and `except _AdmissionRejected as rejected: raise rejected.cause from None` sits before the generic retry-handling `except Exception`). See Behavioral Spot-Checks for the exact scripts and output.

**4. Condition 10 (registry.py) — both directions confirmed, but the guarantee is narrower than before.** `quota_consuming_handlers = (create_chat, send_message)` (`registry.py:153`), matched against `route.endpoint` by identity (`registry.py:220-225`), still fails boot in both directions — confirmed by re-running `tests/unit/test_route_registry.py::TestCondition10QuotaFlagAndConsumingHandlerDisagree` (all cases pass) and by the fact this is part of the 1264-test full-suite pass I ran myself. **However**, this is a real narrowing worth flagging (WARNING, not a blocker): the *old* check matched the identity of a function whose *entire body* was the charge, so "the wrapper is attached" was close to a direct proof that a charge would occur. The *new* check matches the identity of the route's business-logic handler, which charges only via a much deeper chain (`ChatService.ask_llm` → `on_admitted=charge` → `QuotaGate.charge`) that condition 10 does not itself re-verify. A future edit to `ask_llm` that dropped `on_admitted=charge` would **not** fail boot — it would only be caught by the e2e suite (which is exactly what the commit message's own manual check, "unwiring `on_admitted` fails 23 cases," demonstrates — a behavioral, not structural, backstop). The class's own docstring in `test_route_registry.py:222-227` is honest about this narrower framing ("served by a handler that charges nothing"). This does not affect REBIND-06's current truth value — the wiring is intact today — but it is a defense-in-depth regression for future changes.

**5. `TestNoEffectiveGrant`'s `own_chat` fixture change (task-specified judgment call).** Legitimate preservation of intent, not a weakened test. Under the old decorator architecture, a nonexistent chat id never reached the handler (the wrapper ran first), so the test could use a fake id without weakening its claim. Under the new architecture the handler runs first by design — using a fake id would now hit `InvalidChatError` (404) before the quota check ever ran, which would make the test assert the *wrong* thing were it left unchanged. `own_chat` (`tests/e2e/conftest.py:207-232`) seeds a chat genuinely owned by the same identity making the request, so the case must pass through ownership and history-limit checks (which the code review's own reasoning confirms happen first) before it can reach the quota check — if any of those checks broke, the test's explicit `assert response.status_code == 429` / `quota_exceeded` would fail loudly, not pass for the wrong reason. This is, if anything, a *more* end-to-end exercise of the pipeline than the original.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/quota.py` — `consume_quota` | The §8.4 resolver, unchanged | ✓ VERIFIED | Byte-identical to pre-fix commit (`git diff 7b09291 HEAD`), all logic tests re-run green. |
| `src/nativespeaker/api/quota.py` — `QuotaGate` (new) | Session-owning charge object, D-04-compliant | ✓ VERIFIED | Exists (`quota.py:169-222`), substantive (opens/commits/rolls back its own session), wired into `ChatService` via `get_chat_service`/`get_quota_gate`, behaviorally confirmed (charges land in the DB in e2e cases, never charges on any pre-provider rejection). |
| `src/nativespeaker/api/app/dependencies.py` | `require_quota*` deleted; `get_quota_gate` added | ✓ VERIFIED | `grep -rn "require_quota" src/` returns zero hits — fully removed, not left as a dead no-op. `get_quota_gate` (`dependencies.py:119-141`) exists, wired into `get_chat_service` (`dependencies.py:32-40`). |
| `src/nativespeaker/api/resilience.py` | `on_admitted` admission callback, one-shot guard, `_AdmissionRejected` unwrap | ✓ VERIFIED | Exists (`resilience.py:72-192`), wired (`services/llm.py:32-44` forwards it, `services/chats.py:56-73` supplies it), behaviorally confirmed by re-run e2e tests plus my two ad hoc probes (see below). |
| `src/nativespeaker/api/services/chats.py` | `ChatService(quota_gate=...)` required, charge fired from `ask_llm` | ✓ VERIFIED | Constructor takes `quota_gate: QuotaGate` with no default (`services/chats.py:24-30`) — a wiring slip cannot silently serve requests free. `charge()` closure (`services/chats.py:56-67`) passed as `on_admitted`. |
| `src/nativespeaker/api/auth/registry.py` | Condition 10 rekeyed to handler identity | ✓ VERIFIED (see WARNING above) | `quota_consuming_handlers = (create_chat, send_message)` (`registry.py:153`), both directions tested (`test_route_registry.py`), real app boot assertion passes. |
| `tests/e2e/test_quota.py` — `TestNoPreProviderRejectionIsCharged` (new) | 5 cases proving no pre-provider rejection is charged | ✓ VERIFIED | 707-line file, 45 tests total in the file, all re-run and pass against the real app + real Postgres + real Firebase token. |
| `tests/e2e/test_quota.py` — `TestOneUsersGrantIsNotAnothers`, `TestTheEffectiveGrantStatement` (WR-01) | Tenant-scope regression coverage | ✓ VERIFIED — and load-bearing, not cosmetic | I mutation-tested this myself: temporarily deleted `col(AccessGrant.user_id) == user_id` from `grants.py:38`, re-ran the targeted tests — exactly these two failed (one via a 500 `MultipleEffectiveGrantsError`, one via the missing SQL substring), confirming the fix genuinely catches the regression it claims to. File restored via `cp` from a pre-mutation backup; `git diff` confirms zero residual changes. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `ChatService.ask_llm`'s `charge()` closure | `QuotaGate.charge` | Direct call, `services/chats.py:66-67` | ✓ WIRED | Confirmed by reading and by e2e tests that show a real `monthly_used` increment after a served 200. |
| `LLMService.ainvoke`'s `on_admitted` param | `ResiliencePolicy.ainvoke`'s `on_admitted` param | Verbatim forwarding, `services/llm.py:41-44` | ✓ WIRED | Confirmed by reading; no transformation in between. |
| `ResiliencePolicy.ainvoke`'s `admit_once` | `LLMExecutionGate.run`'s `on_admitted` call site | `resilience.py:172` passes `admit_once`; `resilience.py:126-129` calls it after slot+semaphore, before `operation()` | ✓ WIRED | Confirmed by reading **and** by my own direct execution (Behavioral Spot-Checks) — not presence alone. |
| `registry.py`'s `quota_consuming_handlers` | `routers/chats.py`'s `create_chat`/`send_message` | Identity match on `route.endpoint`, `registry.py:220-225` | ✓ WIRED (narrower guarantee than before — see WARNING) | Both directions tested, real app boot assertion passes. |
| `get_chat_service` | `ChatService(quota_gate=...)` | `dependencies.py:32-40`, no default on the constructor param | ✓ WIRED | A missing wire fails at construction time (`TypeError`), not silently. |
| ~~`require_quota`'s commit → handler body / provider dispatch (absence of a compensating link)~~ | — | — | **RESOLVED — architecture changed** | The prior gap's root cause (a decorator-dependency commit with no way to reverse it) no longer exists as a *concept*: the charge now sits *after* every rejection it needs to be after, so there is nothing left to compensate for. Replaced by the "charge → LLM call" link above, which is correctly `WIRED`. |

### Data-Flow Trace (charge reaches a real row, not a stub)

| Artifact | Charge variable | Source | Produces real effect | Status |
|---|---|---|---|---|
| `QuotaGate.charge` | `usage.monthly_used` | `GrantsDB.lock_usage(grant.id)` — a real `SELECT ... FOR UPDATE` against `core.user_monthly_usage`, then `usage.monthly_used += 1` on the loaded row, then `session.commit()` | Yes | ✓ FLOWING — confirmed via `tests/e2e/test_quota.py::TestASeededGrantIsAdmitted::test_the_follow_up_route_is_admitted_and_charged_exactly_once`, which reads the row back through a second, real DB session and observes `[1]` then `[2]` |
| `QuotaGate.charge` on a rejected/refused request | `usage.monthly_used` | Same row, but the increment line is never reached, or is reached and then rolled back | No increment persists | ✓ CONFIRMED ABSENT — every `TestNoPreProviderRejectionIsCharged` case reads `monthly_used` before and after and asserts equality |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Unit: resolver + registry regression | `uv run pytest tests/unit/test_quota_resolver.py tests/unit/test_route_registry.py -q` | 75 passed | ✓ PASS |
| E2E: full quota module against real app/DB/Firebase | `uv run pytest tests/e2e/test_quota.py -q -m e2e` | 45 passed | ✓ PASS |
| WR-01 mutation test: delete `user_id` scoping term, re-run the two new e2e cases | `sed -i` removal of `col(AccessGrant.user_id) == user_id,` in `grants.py`, then `uv run pytest tests/e2e/test_quota.py -q -m e2e -k "TestOneUsersGrantIsNotAnothers or TestTheEffectiveGrantStatement"` | 2 failed (as intended) — one 500 `MultipleEffectiveGrantsError`, one missing-substring `AssertionError` | ✓ PASS (regression genuinely caught; file restored immediately after, `git diff` clean) |
| WR-01 mutation test, same mutation, against the *specific file the prior verification named* | `uv run pytest tests/unit/test_quota_resolver.py -q -k TestTheLockingStatements` (same mutated `grants.py`) | 6 passed — **does not catch the mutation** | ⚠️ WARNING — confirms the prior verification's named location (`tests/unit/test_quota_resolver.py:295-299`) still lacks the `user_id` assertion; the equivalent protection now lives only in `tests/e2e/test_quota.py`, not here |
| Ad hoc probe 1: one-shot admission guard across retries (no persisted test covers this) | `/tmp/verify_resilience_admission.py` — real `ResiliencePolicy`, a flaky operation failing twice then succeeding, `on_admitted` call-counted | `on_admitted` called exactly once across 3 attempts | ✓ PASS (verifier-authored, not part of the repo) |
| Ad hoc probe 1b: raising admission callback aborts immediately, no retry | Same script, second scenario | `on_admitted` called once, provider `operation` never called, original exception propagated | ✓ PASS (verifier-authored, not part of the repo) |
| Ad hoc probe 2: `QueueFullError` never reaches the charge callback (no persisted test covers this) | `/tmp/verify_queue_full_not_charged.py` — real `LLMExecutionGate` with its one slot pre-drained | `QueueFullError` raised; `on_admitted`/`operation` both called 0 times | ✓ PASS (verifier-authored, not part of the repo) |
| Full workspace suite, run once by me (not taken from SUMMARY.md) | `uv run pytest -q -m ""` | 1264 passed in 72.21s | ✓ PASS |
| Lint / type gates, run by me | `uv run ruff check src tests` / `uv run ty check src` | clean / clean | ✓ PASS |
| Real app enumeration assertion | Part of the full-suite run above: `test_real_app_registry_matches_the_real_router` | passed | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention or explicit probe declarations found in this phase's PLAN/SUMMARY files. Step 7c: SKIPPED — no runnable probe scripts declared. (The two "probes" I wrote for this re-verification are ad hoc Python scripts in `/tmp/`, not repository probe scripts, and are called out explicitly above rather than folded into this section.)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| REBIND-01 | 36-03, 36-05 | Route partition + enumeration assertion | ✓ SATISFIED | See truth 1. `REQUIREMENTS.md` marks `[x]` — still justified after this fix; unaffected by the changed files. |
| REBIND-02 | 36-05 | No audit row on these routes; counter increments on rejection | ✓ SATISFIED (no-row half); counter half open | See truth 2 and Human Verification. `REQUIREMENTS.md` marks `[x]` — the no-row half justifies this, but the flagged counter-metric reading is unchanged and still deserves an explicit human ruling. |
| REBIND-03 | 36-02 | Shared error taxonomy for auth rejections; business contracts unchanged | Unaffected — same reading as before | `REQUIREMENTS.md` correctly leaves this `[ ]`. Untouched by the three gap-closure commits. |
| REBIND-04 | — | Void | N/A | Correctly annotated void in both `ROADMAP.md` and `REQUIREMENTS.md:49`. |
| REBIND-05 | 36-01, 36-03, 36-04, 36-05 | Grant resolution, lock order, lazy rollover, non-negative remaining | ✓ SATISFIED | See truths 3 and 6. Logic byte-identical to the previously-verified state. |
| REBIND-06 | 36-02, 36-03, 36-04, 36-05 | App starts, every route behaves as v1.6 except auth rejections | **✓ now SATISFIED** — code confirms it, but `REQUIREMENTS.md:51` still shows `[ ]` | This is the requirement that changed status this pass. See the deep-dive above. `REQUIREMENTS.md` and `ROADMAP.md` (which also still shows `36-05-PLAN.md` unchecked and "4/5 plans executed" despite `36-05`'s own SUMMARY documenting completion) have not been updated to reflect the current code state — this is a documentation-sync recommendation, not a code gap. |

No orphaned requirements — REBIND-01 … REBIND-06 in `REQUIREMENTS.md` map 1:1 onto this phase's plans' `requirements:` fields; the three gap-closure commits are inline fixes against the existing REBIND-06 requirement rather than a new plan, consistent with the task framing.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/nativespeaker/api/resilience.py` | 90-131 | No persisted test exercises `QueueFullError`'s non-charge behavior specifically (only `CircuitOpenError` is e2e-tested; both share the identical structural guard) | ⚠️ Warning | Confirmed correct by this verification's own ad hoc probe, but a future regression on this specific path would not be caught by CI. Recommend adding a `tests/e2e` or `tests/unit` case that drains `LLMExecutionGate`'s slots and asserts no charge. |
| `src/nativespeaker/api/resilience.py` | 145-192 | No persisted test exercises the one-shot admission guard across a retry, or the no-retry-on-admission-rejection behavior | ⚠️ Warning | Confirmed correct by this verification's own ad hoc probe. Recommend a small `tests/unit/test_resilience.py` (does not currently exist) driving `ResiliencePolicy.ainvoke` directly with a flaky/raising `on_admitted`. |
| `src/nativespeaker/api/auth/registry.py` | 211-235 | Condition 10's new handler-identity keying no longer provides a boot-time backstop for the deeper `ChatService → ask_llm → on_admitted → QuotaGate.charge` chain (only structural handler-identity, not charge-behavior) | ⚠️ Warning | Not a current defect — the chain is intact and tested today — but a defense-in-depth regression versus the old wrapper-identity keying, where "attached" was much closer to "will charge." Purely a future-regression risk; no action required for this phase's goal. |
| `tests/unit/test_quota_resolver.py` | 295-299 | `TestTheLockingStatements` still does not assert `core.access_grants.user_id = ` in the compiled SQL — the exact gap the prior verification's WR-01 finding named at this location | ⚠️ Warning (low severity — mitigated elsewhere) | Confirmed by mutation test: this file's tests stay green even with the tenant-scoping predicate deleted. The underlying vulnerability is closed (`tests/e2e/test_quota.py`'s `TestTheEffectiveGrantStatement`/`TestOneUsersGrantIsNotAnothers` now catch it), but this specific, previously-named file was not updated, so the redundant protection this file's docstring implies it provides is not actually there. |
| `tests/e2e/test_chats.py` | 20-21 | Module docstring still says "`POST /chats` now carries `require_quota_create_chat`" — that dependency was deleted by this fix | ℹ️ Info | Cosmetic only (prose inside a triple-quoted docstring, not executable), pre-dates the three gap-closure commits (file untouched by them). Worth a follow-up doc fix, not a behavior issue. |
| `src/nativespeaker/api/services/chats.py` | 75 | `llm_response.get("resolved_mode")` on an unvalidated provider dict (pre-existing WR-03 from `36-REVIEW.md`, not touched by this fix) | ℹ️ Info | Out of scope for REBIND-06; carried forward as a known, pre-existing issue, not newly introduced or newly discovered by this pass. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` markers found in any file touched by the three gap-closure commits.

### Human Verification Required

### 1. REBIND-02's counter-increment scope for quota rejections

**Test:** Read `36-05-SUMMARY.md`'s "Flagged assumption carried forward — REBIND-02" section and decide whether a quota 429 on `POST /chats` or `POST /chats/{chat_id}` must also increment a bounded-cardinality counter, or whether the current structured-log-only treatment satisfies the requirement text.
**Expected:** A ruling recorded either as an accepted reading (no code change) or as a follow-up task to add a second counter.
**Why human:** Requirement-text interpretation the phase's own authors declined to resolve unilaterally; not decidable from code or tests alone. Unchanged by the three gap-closure commits — none touch audit or telemetry code.

### Gaps Summary

**The previously-blocking gap is closed.** REBIND-06 — "every pre-existing route serves as it did in v1.6, apart from auth rejections" — failed the prior verification because three (later found to be five) distinct code paths charged a caller for a request the application refused before ever contacting the LLM provider. The fix relocates the charge from a FastAPI decorator dependency (which necessarily ran *before* the handler could reject anything) to the resilience layer's admission callback (which fires only once the circuit breaker and the local execution gate have both admitted the call, immediately before the provider is invoked). This is a general, structural fix rather than five point patches: I independently re-derived, via direct code reading and by re-running the persisted test suite myself (not trusting the SUMMARY's counts), that all five previously-identified rejection paths (unsupported language, both history limits, unknown/foreign chat id, and circuit-open/queue-full backpressure) now cost nothing, and additionally swept for any rejection path the fix might have missed — finding none. I also independently confirmed, via two throwaway behavioral scripts against the real production classes, two claims the persisted suite does not itself cover: that a retry cannot double-charge, and that `QueueFullError` specifically (not just its sibling `CircuitOpenError`) never reaches the charge callback. D-04 (no lock spans the provider round trip) holds by direct inspection of a strictly sequential `await` chain with no concurrent task spawning. The WR-01 tenant-scoping fix is genuine and load-bearing, confirmed by my own mutation test — though it landed in `tests/e2e/test_quota.py` rather than the specific unit-test location the prior verification named, leaving that file's own version of the same gap unaddressed (low-severity, since the risk itself is now mitigated elsewhere).

**What remains is not a code gap but an unresolved interpretive question the phase's own authors flagged and never re-touched in this fix:** whether REBIND-02's "increment the bounded-cardinality counter metric" on rejection also covers the quota 429s this phase invented, or only barrier/auth rejections. This routes to `human_needed` rather than `passed` per the verification decision tree, exactly as it would have independent of the REBIND-06 gap closure.

**Two lower-stakes, non-blocking findings are worth a human's attention but do not block this phase:** (1) `REQUIREMENTS.md` (REBIND-06's checkbox) and `ROADMAP.md` (the `36-05-PLAN.md` checkbox and "4/5 plans executed" line) have not been updated to reflect work this phase's own SUMMARY files and this verification confirm is done — a documentation-sync task. (2) Three specific behaviors this verification confirmed correct only through its own ad hoc, non-persisted scripts (`QueueFullError` non-charge, the retry one-shot guard, the no-retry-on-admission-rejection behavior) have no regression test in the repository — recommend `tests/unit/test_resilience.py` (does not currently exist) as a follow-up so these do not silently regress.

---

_Verified: 2026-08-22_
_Verifier: Claude (gsd-verifier)_
