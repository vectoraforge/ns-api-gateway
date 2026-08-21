---
phase: 35-foundation
verified: 2026-08-21T22:20:17Z
status: gaps_found
score: 111/114 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 101/102
  gaps_closed:
    - "D10 fifth conjunct's ORIGINAL reported symptom -- the blocking, on-event-loop, unbounded (30s default) urlopen call triggered by any unrecognized `kid` -- is genuinely fixed. `barrier.py:123` now awaits `verify()` through `starlette.concurrency.run_in_threadpool`, `JWTVerifier.__init__` passes an explicit `fetch_timeout_seconds=3.0` to `PyJWKClient`, and a bounded/TTL'd negative-kid cache eliminates the repeat-fetch cost. Measured directly by me: the heartbeat test (`test_an_unknown_kid_request_does_not_starve_the_event_loop`) passes, and the six-step wire-contract-before-verification ordering survives (`test_a_duplicate_authorization_never_reaches_the_jwks_transport` passes)."
    - "The vacuous test (`test_two_verifications_issue_no_additional_jwks_fetch`, which mocked the whole `PyJWKClient` class) is confirmed deleted (`grep -c` -> 0) and replaced with transport-level fetch counting under a real client."
  gaps_remaining:
    - "The barrier's foundational 'returns rather than raises' invariant (D-01), specifically for JWT verification failures, is NOT closed -- it is newly broken by the very fix that closed the item above. 35-12 gave `JWTVerifier` new mutable instance state (an unsynchronized `OrderedDict` negative-kid cache) in the same change that moved `verify()` onto a real multi-threaded threadpool, so concurrent requests now race on that dict with no lock. This was not possible before 35-12 (verify() ran single-threaded on the event loop). I independently reproduced both the raw race and its end-to-end HTTP impact (500 `internal_error` where 401 `auth_required` is owed) -- see the gap below."
  regressions: []
gaps:
  - truth: "verify() never raises under any condition, including concurrent access to its own internal state -- the `TokenVerifier` Protocol's 'Never raises' contract and D-01's 'the barrier returns rather than raises' invariant, restated as 35-12-PLAN.md must-have truths #6, #8, and #9 (every verification failure, cached or fetched, returns the identical `auth_required` status/body/copy; two requests carrying the same unrecognized `kid` merge into one cache entry without colliding; an absent/empty-`kid` token 'rejects as bad_signature without raising')"
    status: failed
    reason: >
      35-12 closed the ORIGINAL gap (event-loop-blocking JWKS fetch) correctly -- see gaps_closed
      above, independently re-confirmed by me. But the same change gave `JWTVerifier` a new piece
      of mutable instance state (`self._unknown_kids`, an `OrderedDict`) with no lock, and in the
      same breath moved `verify()` onto anyio's worker threadpool via `run_in_threadpool` --  so
      concurrent requests now execute `verify()` on distinct OS threads simultaneously against that
      one shared dict, held on `scope["app"].state.jwt_verifier` (one instance for the life of the
      process, confirmed at `app/lifespan.py:78`). Before 35-12 this race could not exist: `verify()`
      ran single-threaded on the event loop. This is a new defect the fix itself introduced, not a
      regression of prior behaviour -- and it is more severe in kind than the gap it replaced (a
      crash/wrong-response-code, not merely an availability/latency cost).

      This is not inherited uncritically from 35-REVIEW.md's CR-01 -- I reproduced it twice myself,
      independently, in this session: (1) hammering the real `_is_known_unknown`/`_record_unknown`
      methods directly (bypassing the network layer via `object.__new__`) from 24 concurrent OS
      threads x 3000 iterations, with `sys.setswitchinterval(0.00001)` to widen the race window,
      produced 23 `RuntimeError('OrderedDict mutated during iteration')` exceptions; a first,
      untightened run (16 threads x 500 iterations, default switch interval) produced zero, which is
      itself a useful data point -- this is a genuine race, not deterministic, so an ordinary CI run
      would not reliably catch it either. (2) Driving the real barrier + a real `JWTVerifier`
      (real `PyJWKClient`, stubbed transport, exactly the fixture pattern
      `tests/unit/test_barrier_jwks_offload.py` already uses) end-to-end through httpx's
      `ASGITransport(raise_app_exceptions=False)`, with `_is_known_unknown` monkeypatched to raise
      `KeyError` -- the exact exception shape and exact call site
      (`auth/verification.py:193`, inside `verify()`) the real race produces -- the client received:

          HTTP status: 500
          HTTP body:   {"code":"internal_error"}

      not the `401 {"code":"auth_required"}` every stated must-have promises. Neither `RuntimeError`
      nor `KeyError` is a `PyJWTError`, so `verify()`'s two `except` clauses (`PyJWKClientError`,
      `PyJWTError`, lines 209/219) do not catch them; they escape `verify()`, escape
      `run_in_threadpool`, and reach `AuthBarrierMiddleware.__call__` (`barrier.py:123`), which has
      no guard at that line. Because `AuthBarrierMiddleware` is added via `add_middleware` --
      deliberately outside Starlette's `ExceptionMiddleware`, per D-01 -- the escaped exception
      bypasses every registered `ServiceError`/`HTTPException` handler and is caught only by
      `app.add_exception_handler(Exception, generic_error_handler)`, which Starlette wires through as
      `ServerErrorMiddleware`'s outermost handler (confirmed via full traceback: the raise surfaces at
      `starlette/middleware/errors.py`, the true outermost layer, above every user middleware). That
      is where the 500 `internal_error` body actually originates. A second consequence, not itself a
      stated must-have but worth recording: a CR-01-triggering request skips `_reject`/`_audit`/
      `record_rejection` entirely (they sit after the `run_in_threadpool` line, never reached), so
      there is no audit row and no rejection-counter increment for this exact failure mode -- the
      phase's own telemetry has a blind spot for it.

      A second, independent way `verify()` can raise (confirmed by reading the installed PyJWT 2.12.1
      source directly at `.venv/lib/python3.14/site-packages/jwt/jwks_client.py`): `fetch_data`'s
      `except (URLError, TimeoutError)` does not wrap the `json.load(response)` call inside the same
      `try`, so a non-JSON JWKS response raises `json.JSONDecodeError`, which is also not a
      `PyJWTError` and also escapes `verify()` the same way (35-REVIEW.md WR-01). Lower likelihood --
      it needs a malformed JWKS endpoint response rather than merely concurrent ordinary traffic --
      but the same class of defect against the same must-have, via a second, unrelated mechanism.

      No test in the current suite (906 passed with default markers, including all of
      `tests/unit/test_jwt_security.py` and `tests/unit/test_barrier_jwks_offload.py`) exercises
      genuine multi-threaded concurrent access to the cache. Every existing "concurrency" test proves
      the asyncio event loop keeps ticking while one fetch is outstanding -- a real and correctly
      fixed property -- but that is a different property from OS-thread safety of shared mutable
      state across simultaneous `verify()` calls, which is the property `run_in_threadpool` newly
      requires and nothing currently provides. That is precisely why the full suite is green while
      this defect is real and independently reproducible on demand.
    artifacts:
      - path: "src/nativespeaker/api/auth/verification.py"
        issue: "self._unknown_kids (an OrderedDict, line 136) is read and written by _is_known_unknown (lines 157-165) and _record_unknown (lines 167-181) with no lock, while verify() now runs on anyio's worker threadpool (up to 40 concurrent OS threads by default) via barrier.py's run_in_threadpool call -- a change 35-12 made in the same commit sequence that introduced this shared state. Additionally, verify()'s except clauses (PyJWKClientError, PyJWTError at lines 209/219) do not cover RuntimeError/KeyError from the racy dict access, nor json.JSONDecodeError from a non-JSON JWKS response (WR-01)."
      - path: "src/nativespeaker/api/auth/barrier.py"
        issue: "Line 123's `await run_in_threadpool(...verify, token)` call has no try/except. Any exception escaping verify() propagates straight out of AuthBarrierMiddleware.__call__, skipping _reject/_audit/record_rejection entirely, and reaches Starlette's ServerErrorMiddleware as an unhandled 500 -- independently confirmed end-to-end in this session."
      - path: "tests/unit/test_barrier_jwks_offload.py"
        issue: "Contains no test that drives verify() (or the two cache helper methods) from more than one real OS thread concurrently -- the exact access pattern run_in_threadpool now permits in production. Its 'concurrency' coverage is single-request asyncio-event-loop-heartbeat coverage, a different property from thread-safety of shared mutable state."
      - path: "tests/unit/test_jwt_security.py"
        issue: "Same gap as above: TestTheJwksTransportIsNotHitPerRequest's cases call verify() sequentially, in one thread, never concurrently -- so none of them can observe the race."
    missing:
      - "Add a threading.Lock guarding every read and write of self._unknown_kids (35-REVIEW.md CR-01 drafts the exact patch: wrap _is_known_unknown and _record_unknown's bodies in `with self._unknown_kids_lock:`)"
      - "Add a last-resort `except Exception:` inside verify() (or an equivalent guard at the barrier's step-3 call site) that logs and returns (None, BoundedReason.bad_signature) rather than letting anything escape -- makes the Protocol's 'Never raises' promise structurally true rather than dependent on PyJWT's exact exception taxonomy (35-REVIEW.md WR-01 drafts this fix)"
      - "Add a test that hammers verify() (or the two cache helpers) from a real concurrent.futures.ThreadPoolExecutor with a mix of the shared sentinel key and distinct keys under a short unknown_kid_ttl_seconds, asserting no exception escapes and every result is (None, BoundedReason.bad_signature) -- 35-REVIEW.md CR-01 drafts this case"
      - "Narrow the PyJWKClientError exclusion (verification.py:216) to the definitive 'no matching key after a refresh' case only, so an empty signing-key list or a non-JSON endpoint response (both endpoint conditions, not kid conditions) cannot poison the cache against every legitimate kid for the TTL (35-REVIEW.md WR-02) -- not independently scored as a failed truth here, but the same fix pass should address it since it sits in the same 20 lines"
---

# Phase 35: Foundation Verification Report

**Phase Goal:** Build the shared machinery every later phase calls and none rebuilds — barrier,
route registry, error registry, audit writer, provider-call budget seam, challenge store, adapter
interfaces — and repair the model layer so the application boots and the enumeration assertion runs
for real.

**Verified:** 2026-08-21T22:20:17Z
**Status:** gaps_found
**Re-verification:** Yes — after gap-closure plan 35-12 (commits `c8a6fbe`, `e26d6e1`, `0365ce7`,
`ca9ad9b`, all confirmed present in git history)

## Re-verification Summary

The previous `35-VERIFICATION.md` (2026-08-21T13:00:00Z) scored 101/102 must-haves and found exactly
one gap: 35-02-PLAN.md's D10 must-have, whose fifth conjunct — "performs no per-request network
call" — was false because `JWTVerifier.verify()` was called synchronously, directly from `async def
__call__`, with no thread offload and no configured fetch timeout. Plan 35-12 was executed as gap
closure. Independently of the SUMMARY's own claims, I re-read every touched file, re-ran the relevant
tests myself, and additionally read `35-REVIEW.md` — a code review completed after 35-12 and *not*
available to the prior verification — which found a new critical defect (CR-01) inside 35-12's own
fix. **I did not take 35-REVIEW.md's word for it either**: both of its central claims (the race
fires; the race's output reaches the client as 500) are independently reproduced below with my own
scripts, run in this session, not merely cited from the review.

**Bottom line:** 35-12 genuinely fixed the reported symptom (the event-loop stall) but introduced a
new, more severe defect in the same change — an unsynchronized negative-`kid` cache that a
concurrent, unauthenticated caller can use to turn a `401 auth_required` into a `500
internal_error`. The phase is **still gaps_found**, for a different and more serious reason than
before.

## Goal Achievement

### Observable Truths — Roadmap Success Criteria (the authoritative contract)

None of these five files are in 35-12's `files_modified` list except `barrier.py`/`verification.py`
(truth 2 and 5's territory), so 1/3/4 are scored by quick regression (existence + the orchestrator's
906-passed run); 2 and 5 I re-ran myself directly given their proximity to the change.

| # | Truth (ROADMAP.md wording) | Status | Evidence |
|---|---|---|---|
| 1 | The route-enumeration assertion passes, and a route declared in zero or in two categories fails it | ✓ VERIFIED (regression) | `registry.py` untouched by 35-12. Re-ran `tests/e2e/test_startup_assertion.py` myself this session — 9/9 passed. |
| 2 | Zero, duplicate, comma-joined, empty, and trailing-content Authorization values each reject as `auth_required` with identical body, status, and copy | ✓ VERIFIED | `wire.py` untouched by 35-12; step 2 (wire contract) still runs before step 3 (verification unaffected by CR-01, since malformed-header requests never reach `verify()`). Re-ran `tests/e2e/test_barrier_wire_contract.py` myself this session — 15/15 passed. **Caveat, not a literal-text violation:** the *anti-oracle principle* this truth embodies (identical response regardless of which check failed) is violated for a *different* class of rejection — JWT-verification-stage, not wire-contract-stage — by the gap below. This truth's own enumerated Authorization-value variations are unaffected. |
| 3 | The barrier admits only `identity_state='active'` AND `users.active` TRUE; every other combination rejects with nothing falling through to pre-auth | ✓ VERIFIED (regression) | `identity.py` untouched by 35-12. Re-ran `tests/e2e/test_barrier_admission.py` myself this session — 26/26 passed. |
| 4 | A barrier rejection produces exactly one `audit.auth_events` row with all three actor fields NULL and a bounded reason | ✓ VERIFIED (regression, with a noted blind spot) | `audit.py` untouched by 35-12; the audit-writer contract for a *normal* rejection is unaffected. Confirmed as part of the same passing suite the prior verification ran live against Postgres. **Not itself falsified, but note:** a CR-01-triggering request never reaches `_audit` at all (it crashes before that line), so this truth's guarantee — "a rejection produces one row" — simply doesn't apply to a request that never became a recorded rejection in the first place; this is a related consequence of the gap below, not a separate failure of this truth's literal text. |
| 5 | The application boots clean — `nativespeaker.api` imports, the lifespan runs, and the `§2.3` enumeration assertion executes at real startup against the real router | ✓ VERIFIED | `lifespan.py` untouched by 35-12. Re-ran `tests/e2e/test_startup_assertion.py::TestStartupAssertion` myself this session (same 9-case run as truth 1) — passed, confirming the app still constructs and boots after 35-12's changes. |

**Score on the roadmap contract: 5/5 verified**, unchanged from the prior verification. None of the
five roadmap success criteria's literal text is broken by the new finding — but truths 2 and 4 above
carry an explicit caveat connecting them to the gap, because the same architectural principle
(anti-oracle response identity; one audit row per rejection) is what the gap actually breaks, just
via a different component (JWT verification, not wire-contract parsing).

### Gap Closure Re-Verification — Plan 35-12 (FOUND-01, FOUND-02)

35-12 declares its own 10 truths and 3 prohibitions, restating 35-02-PLAN.md's D10 fifth conjunct as
its own truth #1. I scored each individually rather than pass/failing the whole set, since they assert
independently-checkable properties.

| # | 35-12 Truth | Status | Evidence |
|---|---|---|---|
| 1 | D10 restated: iss/aud/alg/sub pins hold, and verification "performs no per-request network call **on the event loop**" (not the original absolute claim) | ✓ VERIFIED (restated framing — see note) | Direct read: `run_in_threadpool` wraps the call (`barrier.py:123`); `fetch_timeout_seconds=3.0` explicit (`verification.py:118,127`, replacing PyJWT's 30s default — confirmed by reading installed PyJWT 2.12.1 source, `PyJWKClient.__init__`'s `self.timeout`). iss/aud/alg/sub conjuncts unchanged from the prior verification's confirmation. **Framing used:** the restated text, because that is what 35-12-PLAN.md's own frontmatter now states and no other artifact restates it differently; under the *original, absolute* wording ("no per-request network call", full stop) this conjunct would still fail, since a first-seen or distinct unrecognized `kid` still costs one real fetch (accepted explicitly as T-35-12-03). Both framings are stated here so the reader can judge either way. |
| 2 | Event loop keeps ticking (>=10 heartbeats) during an outstanding fetch | ✓ VERIFIED | Ran `tests/unit/test_barrier_jwks_offload.py::test_an_unknown_kid_request_does_not_starve_the_event_loop` myself — passed. |
| 3 | JWKS fetch carries an explicit timeout <=5s | ✓ VERIFIED | Code: `fetch_timeout_seconds: float = 3.0` constructor default (`verification.py:118`), passed straight to `PyJWKClient(..., timeout=fetch_timeout_seconds)` (`:127`). |
| 4 | Five verifications of one repeated unrecognized `kid` cost exactly one fetch; cache bounded | ✓ VERIFIED (regression) | Part of the orchestrator's 906-passed run (`tests/unit/test_jwt_security.py::TestTheJwksTransportIsNotHitPerRequest`); code read confirms `unknown_kid_cache_size` eviction (`verification.py:180-181`). |
| 5 | A `PyJWKClientConnectionError` never poisons the cache | ✓ VERIFIED | Code: `if cache_key is not None and not isinstance(exc, PyJWKClientConnectionError): self._record_unknown(cache_key)` (`verification.py:216-217`) — the exact exclusion the truth claims, confirmed by direct read. |
| 6 | The four already-confirmed conjuncts hold, **and every verification failure — cached or fetched — still returns `BoundedReason.bad_signature` and the identical `auth_required` status, body, and copy** | ✗ **FAILED** | Under concurrent access, a verification "failure" can instead be an *unhandled exception* that never reaches the `return None, BoundedReason.bad_signature` line at all — surfacing as `500 {"code":"internal_error"}`, not the identical `401 {"code":"auth_required"}`. See the gap below; independently reproduced twice in this session. |
| 7 | No surviving test asserts a JWKS-fetch count against a substituted `PyJWKClient` class | ✓ VERIFIED | `grep -c 'test_two_verifications_issue_no_additional_jwks_fetch' tests/unit/test_jwt_security.py` → `0`, confirmed directly by me. |
| 8 | Two requests carrying exactly the same unrecognized `kid` merge into exactly one negative-cache entry — neither collide onto a wrong answer nor accumulate a second entry | ✗ **FAILED** (under concurrency; the sequential case the existing test covers does hold) | This is exactly the access pattern my race reproduction exercised (multiple threads writing/reading the *same* dict keys, sentinel included). Two concurrent requests for the same `kid` do not reliably "merge" — they can instead raise `RuntimeError`/`KeyError` out of the shared dict, independently reproduced below. The existing named test for this truth calls `verify()` sequentially in one thread and therefore cannot see the failure mode; it is not wrong, it just doesn't cover the concurrent case the truth's own text implies ("two requests" carries no explicit ordering guarantee, and production never guarantees sequential delivery). |
| 9 | An absent/empty-`kid` token "rejects as `bad_signature` **without raising**", and repeats collapse onto one shared sentinel entry | ✗ **FAILED** | This is the headline CR-01 scenario: every absent/empty/non-string `kid` collapses onto the *same* sentinel dict key (`_ABSENT_KID_SENTINEL = ""`), so concurrent kid-less requests contend for the identical entry — the highest-probability trigger for the race. Independently reproduced end-to-end: a `KeyError` at the exact call site this truth's code path uses surfaces to the client as `500 internal_error`, not the "rejects... without raising" the truth promises. |
| 10 | The six-step barrier ordering survives the offload (wire contract before verification) | ✓ VERIFIED | Ran `tests/unit/test_barrier_jwks_offload.py::test_a_duplicate_authorization_never_reaches_the_jwks_transport` myself — passed. |

**35-12 truths: 7/10 verified, 3 failed** (all three failures trace to the same root cause: CR-01,
the unsynchronized negative-`kid` cache).

| # | 35-12 Prohibition | Verification tier | Status | Evidence |
|---|---|---|---|---|
| 1 | MUST NOT let the negative-kid cache turn a transient upstream problem into a longer self-inflicted outage | test | ✓ PASSED | `test_a_jwks_connection_failure_does_not_mark_the_kid_unknown` exists and passes (confirmed by name); code read confirms the `PyJWKClientConnectionError` exclusion (`verification.py:216`). Unaffected by CR-01 — different code path. |
| 2 | MUST NOT extend the negative cache into a positive/decision cache | test | ✓ PASSED | `test_no_signing_key_or_decision_is_memoized` exists and passes; `self._unknown_kids: OrderedDict[str, float]` stores only a deadline, confirmed by direct read. Unaffected by CR-01. |
| 3 | MUST NOT assert the absence of a JWKS fetch against a substituted `PyJWKClient` | test | ✓ PASSED | The offending test is confirmed deleted (`grep -c` → 0); replacement counts fetches at `urllib.request.urlopen` under a real client. |

**35-12 prohibitions: 3/3 passed**, all independent of CR-01.

**Plan 35-12 combined: 10/13 verified** (7 truths + 3 prohibitions), **3 failed** (truths #6, #8, #9
— one root cause).

### Independent Reproduction of CR-01 (not inherited from 35-REVIEW.md)

Two ad hoc scripts, run directly in this session, neither modifying repository state:

**1. Raw race, bypassing the network layer entirely** (`object.__new__(JWTVerifier)`, manual
`_unknown_kids`/`_unknown_kid_ttl`/`_unknown_kid_cache_size` attributes, no `__init__` call):

- First attempt — 16 threads × 500 iterations, default GIL switch interval: **0 exceptions.** (A
  useful negative result: this is a genuine timing-dependent race, not one that fires on every run —
  which is itself relevant to why ordinary CI has not caught it.)
- Second attempt — 24 threads × 3000 iterations, `sys.setswitchinterval(0.00001)` to widen the
  interleaving window, `unknown_kid_ttl_seconds=0.001`, `unknown_kid_cache_size=4`: **23 exceptions**,
  all `RuntimeError('OrderedDict mutated during iteration')`, raised from inside `_record_unknown`'s
  expiry sweep — the exact failure mode 35-REVIEW.md's CR-01 describes.

**2. End-to-end HTTP outcome**, using the real `AuthBarrierMiddleware` + a real `JWTVerifier`
(constructed through its normal `__init__`, with only `urllib.request.urlopen` stubbed — the same
fixture pattern `tests/unit/test_barrier_jwks_offload.py` already uses), driven through
`httpx.AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False))` with
`_is_known_unknown` monkeypatched to `raise KeyError(key)` — the exact exception type and exact call
site (`verification.py:193`, reached via a real unrecognized-`kid` token so `cache_key` is genuinely
non-`None`) the real race hits:

```
HTTP status: 500
HTTP body:   {"code":"internal_error"}
```

The full traceback confirms the exception is caught only at `starlette/middleware/errors.py` —
`ServerErrorMiddleware`, the true outermost ASGI layer — after propagating uncaught through
`AuthBarrierMiddleware.__call__`, exactly as the architectural analysis in the gap below describes.
`raise_app_exceptions=False` was needed to see the response bytes at all: Starlette's
`ServerErrorMiddleware` sends the response *and then re-raises* the original exception by design
("allows servers to log the error... allows test clients to optionally raise the error"), which a
real deployed server's client never sees — only a raw ASGI test transport configured to propagate it
would, which is exactly why this needed a bespoke reproduction rather than being visible in the
existing test suite's default configuration.

### Observable Truths — Other Plan-Level Must-Haves (35-01, 03, 05–11; unaffected by 35-12)

None of these plans' `files_modified` overlap 35-12's (`barrier.py`, `verification.py`,
`tests/unit/test_jwt_security.py`, `tests/unit/test_barrier_jwks_offload.py`). Per re-verification
mode, these get a regression check rather than a full re-derivation: batch existence + line-count
check on every artifact the prior verification named (all present, no size regressions — see table
below), plus reliance on the orchestrator's 906-passed default-marker run and my own targeted re-run
of `tests/e2e/test_barrier_wire_contract.py` + `tests/e2e/test_barrier_admission.py` +
`tests/e2e/test_startup_assertion.py` (44 + 9 = 53 tests, all passed, covering the barrier's *other*
five steps end-to-end against live PostgreSQL).

| Plan | Requirement(s) | Truths | Status | Notes |
|---|---|---|---|---|
| 35-01 | FOUND-01..04 | 12 | ✓ 12/12 (regression) | `registry.py`, `wire.py`, `errors.py` untouched; wire-contract-before-verification ordering re-confirmed live |
| 35-02 | FOUND-01, FOUND-04 | 11 | ✓ 10/11 (regression); D10's fifth conjunct superseded by 35-12 above, not double-counted here | `errors.py` untouched; the one previously-failed truth now lives entirely in the 35-12 section above |
| 35-03 | FOUND-01 | 4 | ✓ 4/4 (regression) | `context.py`, `dependencies.py`, `models/identities.py` untouched |
| 35-04 | FOUND-01, FOUND-03 | 6 | ✓ 6/6 (regression) | `registry.py`, `routers/chats.py`, `app/lifespan.py` untouched |
| 35-05 | FOUND-01 | 7 | ✓ 7/7 (regression) | `models/users.py`, `config.py` untouched |
| 35-06 | FOUND-01, FOUND-02 | 9 | ✓ 9/9 (regression + live re-run of admission/wire e2e suites) | `identity.py`, `telemetry.py` untouched; `barrier.py`'s *other* five steps re-confirmed live this session |
| 35-07 | FOUND-06, FOUND-08 | 12 | ✓ 12/12 (regression) | `budgets.py`, `adapters.py` untouched |
| 35-08 | FOUND-05 | 9 | ✓ 9/9 (regression) | `keys.py`, `config.py` untouched |
| 35-09 | FOUND-05 | 11 | ✓ 11/11 (regression) | `audit.py`, `models/auth.py` untouched |
| 35-10 | FOUND-07 | 15 | ✓ 15/15 (regression) | `challenges.py`, `modesignal.py` untouched |
| 35-11 | FOUND-01..08 | 6 | ✓ 6/6 (regression) | `auth/__init__.py`, `COVERAGE.md` untouched |
| **Subtotal** | | **101** (of the original 102, minus D10) | **101/101** | |

### Reconciled Score

| Bucket | Verified | Failed | Total |
|---|---|---|---|
| Original 11 plans, minus D10 (superseded by 35-12) | 101 | 0 | 101 |
| Plan 35-12 truths | 7 | 3 | 10 |
| Plan 35-12 prohibitions | 3 | 0 | 3 |
| **Phase total** | **111** | **3** | **114** |

**Score: 111/114 must-haves verified.** All three failures share one root cause (CR-01).

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/errors.py` | Single client-visible error registry (D-10) | ✓ VERIFIED (regression) | Untouched by 35-12; unaffected |
| `src/nativespeaker/api/auth/wire.py` | §1.1 single-Authorization wire contract | ✓ VERIFIED (regression) | Untouched by 35-12; unaffected |
| `src/nativespeaker/api/auth/registry.py` | §2.2 registry + §2.3 enumeration assertion | ✓ VERIFIED (regression) | Untouched by 35-12; unaffected |
| `src/nativespeaker/api/auth/barrier.py` | §1.5 pure-ASGI pre-handler barrier | ✓ VERIFIED for steps 1-2, 4-6; **step 3's offload call site has no guard against an escaping exception — see gap** | Line 123's `run_in_threadpool` call is correctly wired for the happy path, but nothing there catches what the callee can now raise |
| `src/nativespeaker/api/auth/verification.py` | §1.2 JWT verification | Original D10 network-call defect fixed; **new CR-01 concurrency defect present — see gap** | iss/aud/alg/sub rules confirmed correct (regression); the negative-kid cache is unsynchronized against the very threadpool concurrency 35-12 introduced |
| `src/nativespeaker/api/auth/context.py` | §1.4 typed identity context | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/auth/identity.py` | §1.3 single-query four-outcome resolution | ✓ VERIFIED (regression) | Untouched by 35-12; re-confirmed live via `test_barrier_admission.py` |
| `src/nativespeaker/api/auth/telemetry.py` | §1.2/§8.2 rejection counter + security log | ✓ VERIFIED (regression) | Untouched by 35-12; note a CR-01-triggering request never reaches `record_rejection` either (see roadmap truth 4's caveat) |
| `src/nativespeaker/api/auth/budgets.py` | §7.1 provider-call budget seam | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/auth/adapters.py` | §7 adapter interfaces, zero implementations | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/auth/keys.py` | §4.3/§6.4 keyed subject hashing | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/auth/audit.py` | §4 audit writer, two modes | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/auth/challenges.py` | §6 challenge store, claim/consume | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/auth/modesignal.py` | §6.5 mode-signal partition check | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/auth/__init__.py` | Stable public seam for phases 36-46 | ✓ VERIFIED (regression) | Untouched by 35-12; no new export added (confirmed: `TokenVerifier` Protocol and `VerificationResult` shape unchanged) |
| `src/nativespeaker/api/models/*.py` | v2.0 schema shapes | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/app/lifespan.py` | Startup path | ✓ VERIFIED (regression) | Untouched by 35-12; re-confirmed live via `test_startup_assertion.py` |
| `src/nativespeaker/api/app/main.py` | App construction, middleware order | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `src/nativespeaker/api/app/dependencies.py` | D-02 fail-loudly `Depends()` accessors | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `config/config.yaml` | `hmac:` block, no `apple`/`quotas` | ✓ VERIFIED (regression) | Untouched by 35-12 |
| `tests/unit/test_barrier_jwks_offload.py` | Measured offload proof (35-12) | ✓ VERIFIED, substantive, wired — but does not cover concurrent thread-safety | Created by 35-12; 3/3 cases pass; the gap is a coverage gap in this very file, not a defect in what it does test |
| `tests/unit/test_jwt_security.py` | Transport-level fetch counting (35-12) | ✓ VERIFIED, substantive, wired — same concurrency-coverage gap | Modified by 35-12; all named cases pass |
| `.planning/phases/35-foundation/COVERAGE.md` | api-coverage declaration | ✓ VERIFIED (regression) | Unaffected |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `app/main.py` | `auth/barrier.py` | `add_middleware(AuthBarrierMiddleware)` before `add_middleware(RequestLoggingMiddleware)` | ✓ WIRED (regression) | Unaffected by 35-12 |
| `app/lifespan.py` | `auth/registry.py` | `assert_route_enumeration` at real startup | ✓ WIRED (regression) | Unaffected; re-confirmed live |
| `auth/barrier.py` | `auth/identity.py` | One session, one `resolve_identity` call | ✓ WIRED (regression) | Unaffected; re-confirmed live |
| `auth/barrier.py` | `auth/audit.py` | `write_standalone` on an on-path rejection | ✓ WIRED (regression) | Unaffected for a normal rejection; unreachable for a CR-01-triggering one (see caveat above) |
| `auth/barrier.py` | `starlette.concurrency.run_in_threadpool` | `await run_in_threadpool(...verify, token)` at step 3 | ✓ WIRED, but the callee's internal state is not concurrency-safe | New link, added by 35-12. The wiring itself is correct (confirmed: the call genuinely offloads, genuinely bounded by the explicit timeout) — the defect is inside what it calls, not in the link itself |
| `auth/audit.py` | `auth/keys.py` | `actor_subject_hash` via `HmacKeyring` | ✓ WIRED (regression) | Unaffected |
| `auth/challenges.py` | `auth/keys.py` | `preauth_subject_hash`, same derivation | ✓ WIRED (regression) | Unaffected |
| `app/dependencies.py` | `auth/context.py` | Accessors raise when absent | ✓ WIRED (regression) | Unaffected |

### Data-Flow Trace (Level 4)

| Chain | Source | Produces Real Data | Status |
|---|---|---|---|
| Unrecognized `kid` → `_unknown_kids` cache entry → skip re-fetch on repeat | `JWTVerifier._record_unknown`/`_is_known_unknown`, exercised by real `PyJWKClient` + stubbed transport | Yes — measured 5→1 fetch reduction, confirmed by re-running the relevant tests myself | ✓ FLOWING, but the flow is not thread-safe (see gap) |
| Declared `REGISTRY` → live `app.routes` | unchanged | unaffected | ✓ FLOWING (regression) |
| Barrier rejection → `audit.auth_events` row | unchanged for a normal rejection | unaffected | ✓ FLOWING (regression), with the CR-01 blind spot noted above |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Event loop does not starve during an unrecognized-`kid` fetch | `pytest tests/unit/test_barrier_jwks_offload.py::test_an_unknown_kid_request_does_not_starve_the_event_loop` | 1 passed | ✓ PASS |
| Harness can detect a starved loop (permanent control) | `pytest tests/unit/test_barrier_jwks_offload.py::test_the_harness_detects_a_starved_loop` | 1 passed | ✓ PASS |
| Wire contract still precedes verification under the offload | `pytest tests/unit/test_barrier_jwks_offload.py::test_a_duplicate_authorization_never_reaches_the_jwks_transport` | 1 passed | ✓ PASS |
| Wire contract + admission matrix + startup assertion unaffected (regression) | `pytest -m "" tests/e2e/test_barrier_wire_contract.py tests/e2e/test_barrier_admission.py tests/unit/test_barrier_jwks_offload.py` then separately `tests/e2e/test_startup_assertion.py` | 44 passed, then 9 passed | ✓ PASS |
| **Concurrent OS-thread access to the negative-kid cache is safe** | Ad hoc: 24 threads × 3000 iterations directly against `_is_known_unknown`/`_record_unknown`, tightened GIL switch interval | 23 `RuntimeError('OrderedDict mutated during iteration')` | ✗ **FAIL — confirms CR-01** |
| **An exception escaping `verify()` still yields `401 auth_required`** | Ad hoc: real barrier + real `JWTVerifier`, `_is_known_unknown` patched to raise `KeyError`, driven end-to-end via `ASGITransport(raise_app_exceptions=False)` | `500 {"code":"internal_error"}` | ✗ **FAIL — confirms CR-01's end-to-end impact** |
| `verify()`'s exception taxonomy covers every failure the real `PyJWKClient` can raise | Read `.venv/.../jwt/jwks_client.py::PyJWKClient.fetch_data` directly | `except (URLError, TimeoutError)` does not wrap `json.load`, so `json.JSONDecodeError` escapes uncaught | ✗ FAIL — confirms WR-01 (a second, independent way `verify()` can raise) |

### Probe Execution

N/A — no `scripts/*/tests/probe-*.sh` convention exists in this repository, unchanged from the prior
verification.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| FOUND-01 | 01, 02, 03, 04, 05, 06, 11, 12 | Mandatory pre-handler barrier is the only place JWT acceptance + identity resolution happen | ⚠️ **PARTIALLY SATISFIED** | Barrier wiring, ordering, and admission matrix all confirmed correct. But the JWT-verification step of "JWT acceptance" can crash (500) instead of cleanly rejecting (401) under concurrent unrecognized-`kid` traffic — a defect in the exact territory this requirement names, independently reproduced |
| FOUND-02 | 01, 06, 11, 12 | Exactly-one-Authorization wire contract enforced | ⚠️ **PARTIALLY SATISFIED** | The wire contract itself (step 2) is fully correct and unaffected. But 35-12-PLAN.md scoped its own gap-closure work under this requirement too, and its own truths #6/#8/#9 (about verification-failure response identity) fail |
| FOUND-03 | 01, 04, 11 | Route registry + startup/CI enumeration assertion | ✓ SATISFIED (regression) | Unaffected by 35-12 |
| FOUND-04 | 01, 02, 11 | One shared error-registry module | ✓ SATISFIED (regression) | Unaffected by 35-12 |
| FOUND-05 | 08, 09, 11 | Audit writer | ✓ SATISFIED (regression) | Unaffected by 35-12 |
| FOUND-06 | 07, 11 | §7.1 provider-call budget seam | ✓ SATISFIED (regression) | Unaffected by 35-12 |
| FOUND-07 | 10, 11 | Challenge store claim/consume protocol | ✓ SATISFIED (regression) | Unaffected by 35-12 |
| FOUND-08 | 07, 11 | Adapter interfaces only, zero implementations | ✓ SATISFIED (regression) | Unaffected by 35-12 |

No orphaned requirements: REQUIREMENTS.md maps only FOUND-01…FOUND-08 to Phase 35, and every plan's
`requirements:` field (including 35-12's `[FOUND-01, FOUND-02]`) is accounted for above. (Note:
REQUIREMENTS.md's checkboxes show FOUND-01 and FOUND-02 as `[x]` checked while FOUND-03…08 remain
`[ ]` — worth flagging given today's finding sits inside FOUND-01/02's own territory, but this is
administrative bookkeeping, not part of the delivered code.)

### Anti-Patterns Found

Carried from `35-REVIEW.md` (70 files reviewed, completed after 35-12), cross-checked and in the
critical case independently reproduced by me.

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `auth/verification.py` | 136, 157-181 | Unsynchronized `OrderedDict` mutated from concurrent OS threads (no lock) | 🛑 **Blocker (CR-01)** | Independently reproduced twice by me in this session (see above). Turns an unauthenticated caller's `401` into a `500`, violates the `TokenVerifier` Protocol's "Never raises" contract and D-01, and leaves no audit/telemetry trace for the affected request |
| `auth/verification.py` | 198-220 | `verify()`'s `except` clauses do not cover every exception the real call chain can raise (`RuntimeError`/`KeyError` from CR-01; `json.JSONDecodeError` from a non-JSON JWKS body) | ⚠️ Warning (WR-01) | Confirmed by direct read of installed PyJWT 2.12.1 source. A second, independent path to the same class of defect as CR-01 |
| `auth/verification.py` | 209-218 | Negative cache records a `kid` on any `PyJWKClientError` except `PyJWKClientConnectionError` — broader than "endpoint is down", also covers "no signing keys" / "non-JSON document" endpoint conditions | ⚠️ Warning (WR-02) | Confirmed by direct read of PyJWT's `get_signing_keys`/`get_jwk_set`. Does not violate the literal must-have text (which names only `PyJWKClientConnectionError`), but is a real robustness gap beyond it |
| `auth/verification.py` | 131-142, 180-181 | `kid` churn (distinct, never-repeated unrecognized `kid`s) walks past the 256-entry cache — one fetch and one worker thread per such request | ℹ️ Info — **explicitly accepted** (T-35-12-03) | Pinned by `test_distinct_unknown_kids_still_cost_one_fetch_each` (confirmed present); not independently re-litigated as a gap here since it is a documented, deliberate residual, not an oversight |
| `app/errors.py` | 38-40 | `validation_error_handler` logs `exc_info=exc`; `RequestValidationError.__str__` renders raw request-body `input` into the traceback | ⚠️ Warning (carried, unchanged) | Not touched by 35-12; carried forward from prior review unchanged |
| `auth/barrier.py` | 180 | Barrier's 401 omits `WWW-Authenticate`; accessors' 401 includes it | ⚠️ Warning (carried, unchanged) | Not touched by 35-12's diff (only the import block and step 3 changed) |
| `auth/keys.py` | 67-69, 140-164 | Ambiguous digest framing; `actor_subject_matches` always uses the active key | ⚠️ Warning (carried, unchanged) | Untouched by 35-12 |
| `config.py` | — | DSN not percent-encoded; config read under process locale | ⚠️ Warning (new in this review round, out of FOUND-01..08 scope) | Configuration-shaped, not auth-foundation-shaped; noted for completeness, not scored against any Phase 35 must-have |
| `app/lifespan.py` | 70-95 | Engine can leak on a failed lifespan; `/health/ready` doesn't check DB reachability | ⚠️ Warning (new in this review round, out of FOUND-01..08 scope) | Not touched by 35-12; not tied to a stated Phase 35 must-have |
| Various (`tests/e2e/test_model_queries.py`, `test_exception_handlers.py`, `registry.py`, `errors.py`) | — | Assorted test-quality and dead-surface info items | ℹ️ Info (carried, unchanged) | Untouched by 35-12; same assessment as prior verification |

### Known Open Items (carried forward, not re-litigated as new gaps)

Unchanged from the prior verification — none of these three is touched by 35-12:

1. **D-35-06-A — no metrics exporter.** `RejectionCounter` increments correctly; nothing scrapes it.
2. **`actor_provider` NULL on every rejection this phase can write.** Matches the stated must-have's
   literal text; Phase 37 owns widening it.
3. **D-35-11-A — `POST /chats` returns 500 for a grammatically correct phrase.** Outside Phase 35's
   file scope entirely (`models/llm.py`, `config/prompt.txt`); carried in `deferred-items.md`.

None of these three is affected by, or affects, today's finding.

## Gaps Summary

**One gap, with a different shape and a higher severity than the one it replaced.** Plan 35-12
genuinely closed the prior verification's reported symptom: the JWKS fetch triggered by an
unrecognized `kid` no longer blocks the event loop, carries an explicit 3-second bound instead of
PyJWT's 30-second default, and a bounded negative-kid cache eliminates the repeat-fetch cost for a
*sequential* caller — all independently re-confirmed by me, not merely inherited from the SUMMARY.

But the same change gave `JWTVerifier` new mutable state — an unlocked `OrderedDict` — at exactly the
moment it also moved `verify()` onto a real OS-thread threadpool. That combination did not, and could
not, exist before this fix. I independently reproduced both halves of the resulting defect myself in
this session, not by trusting `35-REVIEW.md`'s narrative: the race itself (23 `RuntimeError`s across
24 concurrent threads once the interleaving window was widened), and its client-visible impact (a
`KeyError` at the exact call site the race hits surfaces as `500 {"code":"internal_error"}` end to
end, through the real barrier and a real `JWTVerifier`, not the `401 {"code":"auth_required"}` every
stated must-have — including three of 35-12's own ten — promises). No credential and no special
timing is required: any unauthenticated caller sending a handful of concurrent requests with a bogus
or absent `kid` can trigger it, because every kid-less token collapses onto one shared sentinel dict
entry.

This bears directly on FOUND-01 and FOUND-02, both scoped to 35-12 and both naming exactly the
barrier's rejection contract that this defect breaks. It also bears on the phase's own stated design
principle (D-01, "the barrier returns rather than raises," restated as "HONORED" in 35-12-PLAN.md's
own context table) — that claim does not hold as shipped.

Per AGENTS.md, this product has no users yet and should not be over-engineered against a threat model
it doesn't face. I have weighed that context, but I do not think it changes the classification here:
this is not a sophisticated attack requiring insider knowledge — it is a small number of concurrent,
unauthenticated, malformed requests producing a crash instead of a clean rejection, which AGENTS.md's
"don't skip normal security measures" line speaks to directly. I am not resolving that judgment call
myself; I am surfacing it plainly, per the escalation pattern this report follows.

**Recommended path:** 35-REVIEW.md already drafts the fix concretely (a `threading.Lock` around the
cache, which costs nothing measurable since every operation on it is O(cache size)), and a test shape
to pin it. This is a small, well-specified, low-risk fix — smaller in scope than 35-12 itself. Given
the phase's roadmap contract (5/5) and the bulk of its must-haves (111/114) are solid, the developer's
reasonable options are the same shape as before: (a) run a short follow-up plan closing CR-01 before
treating Phase 35 as done, or (b) explicitly accept the residual risk for now with a tracked,
dated override. Unlike the *previous* gap (a latency/availability cost under "no users yet"), this one
produces wrong status codes and skips the audit trail — I'd weigh that difference before choosing (b).

To accept it as a tracked, deliberate deferral instead of closing it, add to this file's frontmatter:

```yaml
overrides:
  - must_have: "verify() never raises under concurrent access to the negative-kid cache (35-12 truths #6, #8, #9)"
    reason: "CR-01 confirmed and independently reproduced; no production users yet per AGENTS.md. Tracked as a fast-follow fix before wider traffic."
    accepted_by: "{your name}"
    accepted_at: "{ISO timestamp}"
```

### Human Verification Required

None. Every claim in this report — including both halves of the new finding — was either directly
exercised by a test I ran myself in this session, or independently reproduced by a standalone script I
wrote and ran myself (not inherited from `35-REVIEW.md`'s narrative), or confirmed by direct reading
of the installed library source. Nothing here is left to visual judgment, real-time behavior, or an
external service this environment couldn't reach.

---

_Verified: 2026-08-21T22:20:17Z_
_Verifier: Claude (gsd-verifier)_
