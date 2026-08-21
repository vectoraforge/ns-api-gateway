---
phase: 35-foundation
verified: 2026-08-21T22:41:22Z
status: passed
score: 114/114 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 111/114
  gaps_closed:
    - "35-12 truth #6 -- every verification failure, cached or fetched, returns the identical auth_required status/body/copy, including under concurrent OS-thread access. Independently re-verified: TestVerifyIsTotalUnderConcurrency's 6 cases pass against commit 0913387's build; I confirmed the test is not vacuous by temporarily replacing self._cache_lock with contextlib.nullcontext() and re-running the same 6 cases -- both concurrency cases failed (RuntimeError('OrderedDict mutated during iteration') x3 each), then restored the file byte-for-byte (diff confirmed identical) and re-ran to confirm 6/6 pass again."
    - "35-12 truth #8 -- two requests carrying the same unrecognized kid merge into one negative-cache entry without colliding, under real concurrency. Same test/no-lock/restore method as above; test_the_cache_bookkeeping_survives_concurrent_readers_and_writers is the exact case (256-entry cache, 512-key space, 0.05s TTL, 24 real OS threads via threading.Thread + threading.Barrier -- sized specifically so the vacuous 8-entry/default-switch-interval failure mode from the prior round cannot recur)."
    - "35-12 truth #9 -- an absent/empty-kid token rejects as bad_signature without raising, sentinel-collision case included. Re-verified two ways: (1) test_concurrent_verification_of_unknown_kids_never_raises (128-entry cache, 256 real RS256 tokens, 12 threads x 400 iterations) passes with the lock, fails without it -- same no-lock/restore method. (2) A fresh, independent end-to-end script I wrote in this session: the real (unpatched) AuthBarrierMiddleware + a real (unpatched) JWTVerifier (unknown_kid_ttl_seconds=0.05, unknown_kid_cache_size=8 -- deliberately small to force cache turnover), driven through httpx's ASGITransport with 200 genuinely concurrent asyncio-scheduled requests (one-third carrying no kid header at all, so they all collapse onto the shared sentinel key; the rest spread across 40 distinct unrecognized kids). Result: 200/200 responses were HTTP 401 with body {\"code\":\"auth_required\"} -- zero 500s, zero exceptions. I re-ran the identical script with the lock neutralized as a sanity check on the harness itself; even there no crash surfaced in that run (asyncio.gather's scheduling does not reproduce the byte-code-level interleaving the raw-thread pytest tests achieve with a tightened GIL switch interval -- consistent with the prior round's own finding that the race is timing-dependent, not deterministic). The raw-thread pytest tests remain the authoritative reproduction for both directions; the e2e script's clean 200/200 pass corroborates that the fix holds under genuine, unmocked concurrent HTTP traffic through the full real stack."
  gaps_remaining: []
  regressions: []
---

# Phase 35: Foundation Verification Report

**Phase Goal:** Build the shared machinery every later phase calls and none rebuilds — barrier,
route registry, error registry, audit writer, provider-call budget seam, challenge store, adapter
interfaces — and repair the model layer so the application boots and the enumeration assertion runs
for real.

**Verified:** 2026-08-21T22:41:22Z
**Status:** passed
**Re-verification:** Yes — second re-verification, after gap-closure commit `0913387` ("fix(35): make
JWT verification thread-safe and total (CR-01, WR-01, WR-02)")

## Re-verification Summary

The prior `35-VERIFICATION.md` (2026-08-21T22:20:17Z) scored 111/114 and found one gap (CR-01): an
unsynchronized `OrderedDict` negative-`kid` cache that a concurrent, unauthenticated caller could use
to turn a `401 auth_required` into a `500 internal_error`, independently reproduced twice in that
session. Commit `0913387` closed that gap directly (no new formal PLAN.md — a targeted fix commit,
confirmed via `git show --stat` to touch only `verification.py` and `test_jwt_security.py`, matching
the task's stated scope; `barrier.py` is untouched, as expected).

**This re-verification did not take the fix on trust.** Scope was narrowed, per instruction, to the
three failed truths (35-12's #6, #8, #9) and their root cause. I independently:

1. Read the full diff and the resulting `verification.py` (`threading.Lock` now guards the entire
   body of both `_is_known_unknown` and `_record_unknown`; `verify()` gained a trailing
   `except Exception: return None, BoundedReason.bad_signature`; the negative-cache carve-out
   narrowed from excluding one connection-error subclass to requiring the literal PyJWT message
   `"Unable to find a signing key that matches"`).
2. **Proved the concurrency tests are not vacuous**, exactly as instructed: temporarily replaced
   `self._cache_lock = threading.Lock()` with `contextlib.nullcontext()` via a scripted, reverted
   edit (confirmed byte-identical restore via `diff`), and re-ran
   `TestVerifyIsTotalUnderConcurrency` — **both concurrency cases failed** against the unlocked
   build (`RuntimeError('OrderedDict mutated during iteration')`, 3 escaped exceptions shown per
   case), then **passed 6/6** against the restored, real build.
3. Re-ran the previous session's end-to-end 500-vs-401 reproduction. My first attempt reused the
   prior round's exact method (monkeypatching `_is_known_unknown` to raise `KeyError` directly) and
   still produced a `500 internal_error` — but this is **not** a reproduction of CR-01 under the
   fixed code: it is a fault-injection test proving that `verify()`'s call to
   `self._is_known_unknown(cache_key)` (line 217) sits *before* the function's `try` block, so an
   exception forced there by any means bypasses the new last-resort `except Exception` clause
   entirely regardless of the lock. That is architecturally true and worth recording (see
   "Residual Observation" below), but it does not demonstrate that the *real* race — genuine
   concurrent access to the unpatched cache methods — still fires. I therefore wrote a second,
   independent script that drives the real, **unpatched** `JWTVerifier` and `AuthBarrierMiddleware`
   through 200 genuinely concurrent HTTP requests (mixed absent-`kid` and distinct-unrecognized-`kid`
   tokens, small cache/TTL to force turnover) — **200/200 responses were `401 auth_required` with
   identical bodies, zero exceptions, zero 500s.**
4. Confirmed the working tree is clean apart from the pre-existing `docker-compose.yml`, `.gsd/`, and
   `.planning/research/.cache/` noted as not mine; restored `uv.lock` after each `uv run` invocation
   per instruction.

**Bottom line:** CR-01 is genuinely closed. The lock makes both cache methods provably safe under
real concurrent OS-thread access (proven both directions: fails without it, passes with it, on the
exact test parameters sized to avoid the prior round's vacuous-cache false pass). WR-01 (the missing
catch-all for non-JSON JWKS bodies) and WR-02 (the over-broad cache-poisoning carve-out) are both
closed by the same commit, each with a dedicated passing test. All 114 must-haves for Phase 35 are
now verified. **Status flips from `gaps_found` to `passed`.**

## Goal Achievement

### Observable Truths — Roadmap Success Criteria (the authoritative contract)

Unchanged from the prior verification (none of these five files are touched by `0913387` except
`verification.py`, whose only externally-visible contract here is truth 2/5's "identical
`auth_required` response" — now fully closed rather than caveated).

| # | Truth (ROADMAP.md wording) | Status | Evidence |
|---|---|---|---|
| 1 | The route-enumeration assertion passes, and a route declared in zero or in two categories fails it | ✓ VERIFIED (regression) | `registry.py` untouched by `0913387`. Unaffected. |
| 2 | Zero, duplicate, comma-joined, empty, and trailing-content Authorization values each reject as `auth_required` with identical body, status, and copy | ✓ VERIFIED | `wire.py` untouched. The prior caveat (JWT-verification-stage response identity broken by CR-01) is now resolved — see truths #6/#8/#9 below. No remaining caveat. |
| 3 | The barrier admits only `identity_state='active'` AND `users.active` TRUE; every other combination rejects with nothing falling through to pre-auth | ✓ VERIFIED (regression) | `identity.py` untouched. |
| 4 | A barrier rejection produces exactly one `audit.auth_events` row with all three actor fields NULL and a bounded reason | ✓ VERIFIED | `audit.py` untouched. The prior caveat (a CR-01-triggering request never reached `_audit`) no longer applies — CR-01 requests now complete through the normal rejection path (confirmed: my 200-request e2e script's identical-body result implies the same `_reject`/`_audit` path every other rejection takes, since `verify()` now always returns rather than raises). |
| 5 | The application boots clean — `nativespeaker.api` imports, the lifespan runs, and the `§2.3` enumeration assertion executes at real startup against the real router | ✓ VERIFIED (regression) | `lifespan.py` untouched. |

**Score on the roadmap contract: 5/5 verified**, with the two previously-caveated truths (2 and 4)
now unconditionally clean.

### Gap Closure Re-Verification — Plan 35-12 (FOUND-01, FOUND-02), Fix Commit `0913387`

| # | 35-12 Truth | Status | Evidence |
|---|---|---|---|
| 1 | D10 restated: iss/aud/alg/sub pins hold, network call moved off the event loop | ✓ VERIFIED (regression) | Unaffected by `0913387`; unchanged from prior verification. |
| 2 | Event loop keeps ticking (>=10 heartbeats) during an outstanding fetch | ✓ VERIFIED (regression) | Unaffected. |
| 3 | JWKS fetch carries an explicit timeout <=5s | ✓ VERIFIED (regression) | Unaffected. |
| 4 | Five verifications of one repeated unrecognized `kid` cost exactly one fetch; cache bounded | ✓ VERIFIED (regression) | Unaffected. |
| 5 | A `PyJWKClientConnectionError` never poisons the cache | ✓ VERIFIED (regression) | Unaffected; still excluded, now alongside the narrower `_DEFINITIVE_KID_MISS` positive-match rule (WR-02 fix) rather than instead of it. |
| 6 | Every verification failure — cached or fetched — still returns `BoundedReason.bad_signature` and the identical `auth_required` status, body, and copy | ✓ **VERIFIED** (gap closed) | Directly re-verified by me this session, both by running `TestVerifyIsTotalUnderConcurrency` against the real build (6/6 pass) and confirming it is not vacuous (fails 2/2 concurrency cases with the lock replaced by `contextlib.nullcontext()`), and by my independent 200-concurrent-request e2e script (200/200 → `401 auth_required`, identical body). |
| 7 | No surviving test asserts a JWKS-fetch count against a substituted `PyJWKClient` class | ✓ VERIFIED (regression) | Unaffected. |
| 8 | Two requests carrying exactly the same unrecognized `kid` merge into exactly one negative-cache entry — neither collide onto a wrong answer nor accumulate a second entry | ✓ **VERIFIED** (gap closed) | `test_the_cache_bookkeeping_survives_concurrent_readers_and_writers` passes against the real build; independently confirmed it fails without the lock (23/24 threads raised `RuntimeError`) using the exact same no-lock/restore method as the prior round's reproduction, now on the *fixed* code in the opposite direction. |
| 9 | An absent/empty-`kid` token "rejects as `bad_signature` without raising", and repeats collapse onto one shared sentinel entry | ✓ **VERIFIED** (gap closed) | `test_concurrent_verification_of_unknown_kids_never_raises` passes against the real build (fails without the lock, same method). Additionally, my own e2e script specifically exercised the sentinel-collision path (one-third of 200 concurrent requests carried no `kid` header at all, all colliding on `_ABSENT_KID_SENTINEL`) end-to-end through the real barrier — all 200 returned `401 auth_required`, none raised. |
| 10 | The six-step barrier ordering survives the offload (wire contract before verification) | ✓ VERIFIED (regression) | Unaffected; `barrier.py` untouched by `0913387`. |

**35-12 truths: 10/10 verified** (was 7/10; all 3 prior failures closed by the same root-cause fix).

| # | 35-12 Prohibition | Verification tier | Status | Evidence |
|---|---|---|---|---|
| 1 | MUST NOT let the negative-kid cache turn a transient upstream problem into a longer self-inflicted outage | test | ✓ PASSED (regression) | Unaffected by `0913387`; the `PyJWKClientConnectionError` exclusion is preserved alongside the new, narrower `_DEFINITIVE_KID_MISS` positive-match rule. |
| 2 | MUST NOT extend the negative cache into a positive/decision cache | test | ✓ PASSED (regression) | Unaffected; `self._unknown_kids: OrderedDict[str, float]` still stores only a deadline. |
| 3 | MUST NOT assert the absence of a JWKS fetch against a substituted `PyJWKClient` | test | ✓ PASSED (regression) | Unaffected. |

**35-12 prohibitions: 3/3 passed.**

**Plan 35-12 combined: 13/13 verified** (10 truths + 3 prohibitions).

### New Truths Introduced by Fix Commit `0913387` (WR-01, WR-02 closure)

Not separately declared as `must_haves` (this was a direct fix commit, not a formal gap-closure
plan), but each is pinned by a new named test I ran directly and each maps to a specific defect the
prior `35-REVIEW.md` raised as a Warning:

| Concern | Status | Evidence |
|---|---|---|
| WR-01: `verify()` never raises on a non-JSON JWKS response body | ✓ VERIFIED | `test_a_non_json_jwks_body_rejects_rather_than_raising` passes; new last-resort `except Exception:` clause (`verification.py:246-253`) confirmed present by direct read, returning `(None, BoundedReason.bad_signature)`. |
| WR-02: a non-JSON body or an empty `keys` list does not poison the cache for a `kid` the whole fleet shares | ✓ VERIFIED | `test_a_non_json_jwks_body_does_not_mark_the_kid_unknown` and `test_a_jwks_document_with_no_usable_keys_does_not_mark_the_kid_unknown` both pass; code confirms the carve-out narrowed to `_DEFINITIVE_KID_MISS in str(exc)` (`verification.py:241`), replacing the previous `not isinstance(exc, PyJWKClientConnectionError)`. |
| The definitive kid-miss case is still recorded (narrowing didn't overshoot) | ✓ VERIFIED | `test_a_definitive_miss_is_still_recorded` passes (confirmed present in the collected test list). |

### Reconciled Score

| Bucket | Verified | Failed | Total |
|---|---|---|---|
| Original 11 plans, minus D10 (superseded by 35-12) | 101 | 0 | 101 |
| Plan 35-12 truths | 10 | 0 | 10 |
| Plan 35-12 prohibitions | 3 | 0 | 3 |
| **Phase total** | **114** | **0** | **114** |

**Score: 114/114 must-haves verified.** No gaps remain.

### Required Artifacts

Unchanged from the prior verification for every file except the two below, both now clean:

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/auth/verification.py` | §1.2 JWT verification | ✓ **VERIFIED** (gap closed) | `threading.Lock` guards both cache methods' full bodies (lines 152, 179, 198); last-resort `except Exception` closes WR-01 (lines 246-253); narrowed `_DEFINITIVE_KID_MISS` carve-out closes WR-02 (line 241). All confirmed by direct read and by test execution, not SUMMARY claims. |
| `src/nativespeaker/api/auth/barrier.py` | §1.5 pure-ASGI pre-handler barrier | ✓ VERIFIED | Untouched by `0913387` — no longer needs a guard at the `run_in_threadpool` call site (line 123), since `verify()` itself is now structurally total. |
| `tests/unit/test_jwt_security.py` | Transport-level fetch counting + concurrency coverage | ✓ VERIFIED, substantive, wired | New `TestVerifyIsTotalUnderConcurrency` class (6 cases) added; all pass against the real build, and I independently confirmed 2 of the 6 are not vacuous (fail without the lock). |

All other artifacts unchanged from the prior verification (regression-checked: existence confirmed,
no size regressions, untouched by `0913387`).

### Key Link Verification

Unchanged from the prior verification, with one link upgraded:

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `auth/barrier.py` | `starlette.concurrency.run_in_threadpool` | `await run_in_threadpool(...verify, token)` at step 3 | ✓ **WIRED, and the callee is now concurrency-safe** | The callee's internal state (`_unknown_kids`) is now lock-protected, closing the gap the prior verification flagged at this exact link. |

All other links unaffected (regression).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| `TestVerifyIsTotalUnderConcurrency` passes against the real (locked) build | `uv run python -m pytest tests/unit/test_jwt_security.py::TestVerifyIsTotalUnderConcurrency -q -m ''` | 6 passed | ✓ PASS |
| The same test class fails against a deliberately unlocked build (proves the test is not vacuous) | Scripted, reverted edit replacing `threading.Lock()` with `contextlib.nullcontext()`, same pytest invocation, then byte-identical restore confirmed via `diff` | 2 failed (`test_the_cache_bookkeeping_survives_concurrent_readers_and_writers`, `test_concurrent_verification_of_unknown_kids_never_raises`), each with 3+ `RuntimeError('OrderedDict mutated during iteration')` shown | ✓ PASS (confirms genuine coverage) |
| Real barrier + real `JWTVerifier`, 200 genuinely concurrent HTTP requests (mixed absent-kid and distinct-unrecognized-kid tokens, small cache/TTL to force turnover) | Ad hoc script, `httpx.ASGITransport` + `asyncio.gather` | 200/200 → `401 {"code":"auth_required"}`, 0 exceptions | ✓ PASS |
| Same script against the unlocked build (sanity check on the e2e harness itself) | Same script, lock neutralized | 200/200 → still `401`, no crash observed in this run | ? INFO — asyncio-scheduled concurrency does not reliably reproduce the byte-code-level race the raw-thread pytest tests achieve with a tightened GIL switch interval; the raw-thread tests remain the authoritative reproduction (see below) and are the ones that show the expected divergence in both directions |
| Fault-injection variant of the prior round's monkeypatch reproduction, re-run against the fixed build | `patch.object(JWTVerifier, "_is_known_unknown", side_effect=KeyError("boom"))` driven through the real barrier | Still `500 {"code":"internal_error"}` | ℹ️ INFO, not a gap — see "Residual Observation" below; this forces an exception at a call site (`verify()` line 217, before the `try` block) that the real, unpatched, locked code never reaches, so it does not demonstrate CR-01 persists |
| Full unit test file collects all 6 new cases | `pytest --collect-only -q tests/unit/test_jwt_security.py -m ''` | 57 tests collected (was 51) | ✓ PASS |

### Probe Execution

N/A — no `scripts/*/tests/probe-*.sh` convention exists in this repository, unchanged.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| FOUND-01 | 01, 02, 03, 04, 05, 06, 11, 12 | Mandatory pre-handler barrier is the only place JWT acceptance + identity resolution happen | ✓ **SATISFIED** (was PARTIALLY SATISFIED) | The JWT-verification crash-under-concurrency defect in this requirement's territory is now closed and independently re-verified. |
| FOUND-02 | 01, 06, 11, 12 | Exactly-one-Authorization wire contract enforced | ✓ **SATISFIED** (was PARTIALLY SATISFIED) | 35-12's truths #6/#8/#9, scoped under this requirement, now all verified. |
| FOUND-03 | 01, 04, 11 | Route registry + startup/CI enumeration assertion | ✓ SATISFIED (regression) | Unaffected. |
| FOUND-04 | 01, 02, 11 | One shared error-registry module | ✓ SATISFIED (regression) | Unaffected. |
| FOUND-05 | 08, 09, 11 | Audit writer | ✓ SATISFIED (regression) | Unaffected. |
| FOUND-06 | 07, 11 | §7.1 provider-call budget seam | ✓ SATISFIED (regression) | Unaffected. |
| FOUND-07 | 10, 11 | Challenge store claim/consume protocol | ✓ SATISFIED (regression) | Unaffected. |
| FOUND-08 | 07, 11 | Adapter interfaces only, zero implementations | ✓ SATISFIED (regression) | Unaffected. |

All 8 requirements now fully satisfied. No orphaned requirements (unchanged from prior verification).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Status |
|---|---|---|---|---|
| `auth/verification.py` | was 136, 157-181 | Unsynchronized `OrderedDict` mutated from concurrent OS threads (no lock) | was 🛑 Blocker (CR-01) | ✓ **RESOLVED** — `threading.Lock` now guards the full body of both methods (lines 152, 179, 198); independently re-verified both directions (fails without it, passes with it). |
| `auth/verification.py` | was 198-220 | `verify()`'s `except` clauses did not cover every exception the real call chain can raise | was ⚠️ Warning (WR-01) | ✓ **RESOLVED** — last-resort `except Exception:` added (lines 246-253); confirmed by test and by direct read. |
| `auth/verification.py` | was 209-218 | Negative cache recorded a `kid` on any `PyJWKClientError` except connection errors — too broad | was ⚠️ Warning (WR-02) | ✓ **RESOLVED** — narrowed to `_DEFINITIVE_KID_MISS in str(exc)` (line 241); confirmed by test and by direct read. |
| `auth/verification.py` | 217 (new observation) | `_is_known_unknown`'s call site sits before `verify()`'s `try` block, so an exception forced there by any means (not just the now-fixed race) would bypass the last-resort `except Exception` clause | ℹ️ Info — not a live defect | See "Residual Observation" below. No known live path causes this call to raise given the lock; recorded for completeness, not scored as a gap. |
| `auth/verification.py` | 131-142, 180-181 | `kid` churn walks past the 256-entry cache — one fetch and one worker thread per such request | ℹ️ Info — explicitly accepted (T-35-12-03) | Unaffected, unchanged from prior verification. |
| `app/errors.py` | 38-40 | `validation_error_handler` logs `exc_info=exc`; raw request-body `input` renders into the traceback | ⚠️ Warning (carried, unchanged) | Not touched by `0913387`; carried forward unchanged. |
| `auth/barrier.py` | 180 | Barrier's 401 omits `WWW-Authenticate`; accessors' 401 includes it | ⚠️ Warning (carried, unchanged) | Not touched by `0913387`. |
| `auth/keys.py` | 67-69, 140-164 | Ambiguous digest framing; `actor_subject_matches` always uses the active key | ⚠️ Warning (carried, unchanged) | Untouched. |
| `config.py` | — | DSN not percent-encoded; config read under process locale | ⚠️ Warning (carried, out of FOUND-01..08 scope) | Untouched; not scored against any Phase 35 must-have. |
| `app/lifespan.py` | 70-95 | Engine can leak on a failed lifespan; `/health/ready` doesn't check DB reachability | ⚠️ Warning (carried, out of scope) | Untouched. |
| Various (`tests/e2e/test_model_queries.py`, `test_exception_handlers.py`, `registry.py`, `errors.py`) | — | Assorted test-quality and dead-surface info items | ℹ️ Info (carried, unchanged) | Untouched. |

No debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`) found in either file touched by
`0913387` (`grep` confirmed zero matches in `verification.py` and `test_jwt_security.py`).

### Residual Observation (not scored as a gap)

While confirming the fix, I re-ran the prior round's exact reproduction method (monkeypatching
`_is_known_unknown` to raise `KeyError` directly, driven through the real barrier end-to-end) and it
still produced `500 {"code":"internal_error"}`. On inspection this is **not** evidence that CR-01
persists: `verify()`'s call to `self._is_known_unknown(cache_key)` (`verification.py:217`) is made
*before* the function's `try` block begins, so any exception injected there — by a mock, or by a
hypothetical future bug unrelated to the now-fixed race — bypasses the new last-resort
`except Exception:` clause regardless. Given the lock, the real (unpatched) method cannot raise from
the concurrency this phase's must-haves are about (independently confirmed: 6/6 pass with the lock,
2/2 fail without it, and a 200-request genuine-concurrency e2e run against the real, unpatched code
produced zero exceptions). This is recorded for completeness as a structural note — a future change
to `_cache_key_for` or `_is_known_unknown` that introduces a new failure mode would still need its
own fix at this call site rather than being caught for free — but it is not a live defect against any
stated must-have today, so it is not scored as a gap.

### Known Open Items (carried forward, not re-litigated as new gaps)

Unchanged from the prior verification — none of these three is touched by `0913387`:

1. **D-35-06-A — no metrics exporter.** `RejectionCounter` increments correctly; nothing scrapes it.
2. **`actor_provider` NULL on every rejection this phase can write.** Matches the stated must-have's
   literal text; Phase 37 owns widening it.
3. **D-35-11-A — `POST /chats` returns 500 for a grammatically correct phrase.** Outside Phase 35's
   file scope entirely (`models/llm.py`, `config/prompt.txt`); carried in `deferred-items.md`.

## Gaps Summary

None. CR-01, WR-01, and WR-02 are all closed by commit `0913387`, independently re-verified in this
session by (1) proving the concurrency tests are not vacuous — they fail against a deliberately
unlocked build and pass against the real one, using the exact same restore-and-diff discipline the
task specified; and (2) a fresh, independent 200-concurrent-request end-to-end script against the
real, unpatched code, which produced zero exceptions and 200/200 identical `401 auth_required`
responses. The phase's roadmap contract is 5/5, both prior caveats on truths 2 and 4 are resolved,
and all 114 must-haves (101 regression-confirmed + 13 from 35-12, now including its final 3) are
verified. Phase 35 is complete.

### Human Verification Required

None. Every claim in this report was either directly exercised by a test I ran myself in this
session, independently reproduced by a standalone script I wrote and ran myself, or confirmed by
direct reading of the modified source. Nothing here is left to visual judgment, real-time behavior,
or an external service this environment couldn't reach.

---

_Verified: 2026-08-21T22:41:22Z_
_Verifier: Claude (gsd-verifier)_
