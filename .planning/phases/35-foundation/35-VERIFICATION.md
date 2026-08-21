---
phase: 35-foundation
verified: 2026-08-21T13:00:00Z
status: gaps_found
score: 101/102 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Token verification pins iss to exactly https://securetoken.google.com/<configured project id> and aud to exactly the configured project id, verifies RS256 only, requires a non-empty sub, and performs no per-request network call (35-02-PLAN.md must-have D10; roadmap goal text 'shared machinery every later phase calls')"
    status: failed
    reason: >
      Four of five conjuncts hold (iss pin, aud pin, RS256-only, non-empty sub — all confirmed
      directly in auth/verification.py and by tests/unit/test_jwt_security.py::TestClaimValidation /
      TestAlgorithmSecurity / TestSignatureVerification). The fifth — "performs no per-request
      network call" — is false whenever a request carries an unrecognized `kid`. `JWTVerifier.verify()`
      (auth/verification.py:111-126) calls the synchronous, blocking `PyJWKClient.get_signing_key_from_jwt`,
      invoked directly from `async def AuthBarrierMiddleware.__call__` (auth/barrier.py:113) with no
      `run_in_threadpool` offload and no configured fetch timeout (PyJWT's 30s default applies, since
      `JWTVerifier.__init__` never passes `timeout=`). This is documented in 35-REVIEW.md as CR-01
      (critical), independently reproduced there: 3 unauthenticated requests carrying unrecognized
      `kid`s triggered 3 live JWKS fetches and a measured 1.206s contiguous event-loop stall at a 0.4s
      simulated round trip — during which the entire process, including `/health/ready`, is blocked.
      I independently confirmed the code shape by direct read (barrier.py:113, verification.py:94-126)
      and by `grep -rn "run_in_threadpool|to_thread|ThreadPoolExecutor" src/` returning nothing, and
      by grepping verification.py for `timeout` (nothing). The one test that names this exact
      property, tests/unit/test_jwt_security.py::TestProductionVerifier::test_two_verifications_issue_no_additional_jwks_fetch,
      is vacuous: its fixture replaces the whole `PyJWKClient` class with a `MagicMock` and stubs
      `get_signing_key_from_jwt` (the method `verify()` actually calls) to return a static key
      directly, then asserts `get_signing_keys.call_count == 0` — a method `verify()` never calls in
      the first place. The assertion holds regardless of caching behaviour and cannot fail. I ran it
      to confirm it currently passes, then read its body to confirm why that pass is not evidence.
      35-02-SUMMARY.md's own D10 entry cites this test as "6 tests over the real JWTVerifier with only
      the JWKS transport stubbed" — the class is replaced wholesale, not its transport, so the SUMMARY
      overstates what was proven.
    artifacts:
      - path: "src/nativespeaker/api/auth/verification.py"
        issue: "JWTVerifier.__init__ (lines 94-109) passes no timeout= to PyJWKClient, and verify() (111-126) has no bounded negative-kid cache, so a cache-miss kid always re-fetches synchronously"
      - path: "src/nativespeaker/api/auth/barrier.py"
        issue: "Line 113 calls the synchronous verify() directly from async def __call__ with no run_in_threadpool / to_thread offload"
      - path: "tests/unit/test_jwt_security.py"
        issue: "TestProductionVerifier::test_two_verifications_issue_no_additional_jwks_fetch mocks PyJWKClient wholesale (jwks_client fixture, lines 291-297) and cannot exercise the fetch path it claims to prove absent"
    missing:
      - "Offload verify() to a threadpool at the barrier call site (starlette.concurrency.run_in_threadpool), or make verification async, per the fix 35-REVIEW.md CR-01 already spells out"
      - "Pass an explicit bounded fetch_timeout_seconds to PyJWKClient instead of PyJWT's 30s default"
      - "Add a bounded negative-kid cache so a repeated unrecognized kid does not refetch on every request"
      - "Replace the vacuous test with one that stubs the transport (urllib.request.urlopen) under a real PyJWKClient and asserts a bounded fetch count across repeated unknown kids (35-REVIEW.md WR-05 already drafts this test)"
---

# Phase 35: Foundation Verification Report

**Phase Goal:** Build the shared machinery every later phase calls and none rebuilds — barrier,
route registry, error registry, audit writer, provider-call budget seam, challenge store, adapter
interfaces — and repair the model layer so the application boots and the enumeration assertion runs
for real.

**Verified:** 2026-08-21T13:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

**Scope note (from the dispatching orchestrator, honored here):** Phase 35 is explicitly the first
**booting** app (D-14), not the first fully-working one — chat/quota routes still fail at runtime
until Phase 36 rewires them onto the grant model (D-15). This report holds the phase to that bar:
"boots and the enumeration assertion runs for real," not "every product flow works end to end." The
one gap below is evaluated against that bar explicitly, not against a broader standard the phase
never claimed.

## Goal Achievement

### Observable Truths — Roadmap Success Criteria (the authoritative contract)

All five were exercised directly (not inferred from presence) by running the named tests myself in
this session, against the live app and a live PostgreSQL database, in addition to the orchestrator's
already-measured full-suite pass (1137 passed, 0 failed).

| # | Truth (ROADMAP.md wording) | Status | Evidence |
|---|---|---|---|
| 1 | The route-enumeration assertion passes, and a route declared in zero or in two categories fails it | ✓ VERIFIED | `auth/registry.py::assert_route_enumeration` checks set equality both directions (conditions 1-2) plus 7 more conditions. Ran `tests/unit/test_route_registry.py` names directly: `test_zero_routes_and_zero_entries_pass`, `test_registered_route_absent_from_the_registry_raises`, `test_declared_entry_with_no_registered_route_raises`, `test_same_method_and_path_declared_twice_raises` all exist and (per orchestrator's full run) pass. Ran `tests/e2e/test_startup_assertion.py::TestStartupAssertion` (9 cases) myself — PASSED, including `test_assertion_passes_against_the_live_app` calling the assertion against the real started app. |
| 2 | Zero, duplicate, comma-joined, empty, and trailing-content Authorization values each reject as `auth_required` with identical body, status, and copy | ✓ VERIFIED | `auth/wire.py::extract_bearer` counts field instances before inspecting values (no first/last-value path). Ran `tests/e2e/test_barrier_wire_contract.py` myself (14 cases) — PASSED, including `test_all_six_bodies_are_byte_identical` and `test_all_six_statuses_are_identical` over a real ASGI transport, and `test_a_duplicate_is_refused_identically_on_every_authenticated_route` parametrized across `/`, `/examples`, `/chats`. |
| 3 | The barrier admits only `identity_state='active'` AND `users.active` TRUE; every other combination rejects with nothing falling through to pre-auth | ✓ VERIFIED | `auth/identity.py::resolve_identity` — single outer-joined query, strict `!= active` / `is not True` comparisons (fails closed on NULL/unknown values by construction, not by enumeration). Ran `tests/e2e/test_barrier_admission.py::TestOutcomesTwoAndThreeAreIndistinguishable`, `::TestOutcomeFourLinkedAndActive`, `::TestOneQueryPerRequest` myself (13 cases against seeded live-DB rows) — PASSED. |
| 4 | A barrier rejection produces exactly one `audit.auth_events` row with all three actor fields NULL and a bounded reason | ✓ VERIFIED | `auth/barrier.py::_reject`/`_audit` writes standalone-durable only when `meta.operation is not None`; `auth/audit.py::_assert_actor_consistency` enforces the all-NULL rule for `invalid_external_jwt` structurally (raises before any DB write otherwise). Ran `tests/e2e/test_audit_writer.py::TestAnOnPathRejectionWritesExactlyOneRow::test_a_missing_token_writes_one_row_and_returns_the_shared_401` and `::TestAVerifiedActorIsRecordedAsAKeyedHash::test_an_unlinked_subject_writes_all_three_actor_fields` myself against the live DB — PASSED. |
| 5 | The application boots clean — `nativespeaker.api` imports, the lifespan runs, and the `§2.3` enumeration assertion executes at real startup against the real router | ✓ VERIFIED | `app/lifespan.py` calls `assert_registry_total()` then `assert_route_enumeration(app, app.state.route_registry)` before yielding, ahead of DB/JWT/LLM init. Directly executed `python -c "import nativespeaker.api.app.main as m; ..."` myself — app object constructs, exactly 8 routes registered. `tests/e2e/test_startup_assertion.py::TestStartupAssertion::test_lifespan_completed` runs the real lifespan over ASGI and PASSED (run myself). |

**Score on the roadmap contract: 5/5 verified.**

### Observable Truths — Plan-Level Must-Haves (all 11 plans, FOUND-01…08)

The 11 plans declare 102 individual must-have truths in total (12+11+4+6+7+9+12+9+11+15+6 across
plans 01-11). I read every core artifact directly (`errors.py`, `wire.py`, `registry.py`,
`barrier.py`, `verification.py`, `context.py`, `identity.py`, `telemetry.py`, `budgets.py`,
`adapters.py`, `keys.py`, `audit.py`, `challenges.py`, `modesignal.py`, `auth/__init__.py`,
`app/lifespan.py`, `app/main.py`, `app/dependencies.py`, `app/errors.py`, `models/users.py`,
`models/identities.py`, `models/auth.py`, `config.py`, `config/config.yaml`, `routers/chats.py`,
`models/__init__.py`) rather than trusting SUMMARY.md, cross-referenced each against its plan's
must-have text, and spot-ran the tests that exercise the state-transition / concurrency-sensitive
ones myself (see Behavioral Spot-Checks). One truth fails; the other 101 are verified.

| Plan | Requirement(s) | Truths | Verified | Failed | Key artifact(s) | Notes |
|---|---|---|---|---|---|---|
| 35-01 | FOUND-01..04 | 12 | 12 | 0 | `barrier.py`, `registry.py`, `wire.py`, `errors.py` | Includes 1 backstop truth (zero-routes/zero-entries), confirmed by `test_zero_routes_and_zero_entries_pass` |
| 35-02 | FOUND-01, FOUND-04 | 11 | **10** | **1** | `errors.py`, `verification.py` | The one failure: "performs no per-request network call" — see gap above (CR-01) |
| 35-03 | FOUND-01 | 4 | 4 | 0 | `context.py`, `dependencies.py`, `models/identities.py` | Fail-loudly accessors confirmed by direct read + `test_identity_accessors.py` |
| 35-04 | FOUND-01, FOUND-03 | 6 | 6 | 0 | `registry.py`, `routers/chats.py`, `app/lifespan.py` | Exactly 8 routes confirmed by direct `python -c` execution against the live module |
| 35-05 | FOUND-01 | 7 | 7 | 0 | `models/users.py`, `config.py` | 7-column `User` model confirmed; `config/config.yaml` has no `apple`/`quotas` block |
| 35-06 | FOUND-01, FOUND-02 | 9 | 9 | 0 | `identity.py`, `telemetry.py`, `barrier.py` | Admission matrix + wire contract confirmed live against seeded Postgres rows (see spot-checks) |
| 35-07 | FOUND-06, FOUND-08 | 12 | 12 | 0 | `budgets.py`, `adapters.py` | Includes 3 backstop truths (int-only counters, per-request isolation, no import side effects) — all confirmed by named tests (`test_counters_are_plain_ints`, `test_two_gates_share_no_state`, `test_no_module_level_mutable_state`) |
| 35-08 | FOUND-05 | 9 | 9 | 0 | `keys.py`, `config.py` | Fail-closed active-key policy (D-22) confirmed by direct read of `HmacConfig._validate_key_material` |
| 35-09 | FOUND-05 | 11 | 11 | 0 | `audit.py`, `models/auth.py` | Redaction, details shape, all-or-nothing actor CHECK all confirmed live (see spot-checks) |
| 35-10 | FOUND-07 | 15 | 15 | 0 | `challenges.py`, `modesignal.py` | Claim/consume atomicity confirmed by running the concurrency test myself against live Postgres |
| 35-11 | FOUND-01..08 | 6 | 6 | 0 | `auth/__init__.py`, `COVERAGE.md` | 58-symbol public seam confirmed by direct import; `COVERAGE.md` confirmed to declare "No external API integration" |
| **Total** | | **102** | **101** | **1** | | |

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/errors.py` | Single client-visible error registry (D-10) | ✓ VERIFIED | 7 foundation + 8 pre-existing classes, `register_class` enforces no-duplicate-code, `assert_registry_total()` self-check, `STATUS_TO_CLASS` closed map |
| `src/nativespeaker/api/auth/wire.py` | §1.1 single-Authorization wire contract | ✓ VERIFIED | Reads raw ASGI header list (never `Headers.get`); counts before inspecting |
| `src/nativespeaker/api/auth/registry.py` | §2.2 registry + §2.3 enumeration assertion | ✓ VERIFIED | 8-route `REGISTRY`, 9-condition `assert_route_enumeration`, confirmed executing live |
| `src/nativespeaker/api/auth/barrier.py` | §1.5 pure-ASGI pre-handler barrier | ✓ VERIFIED (with a defect — see gap) | 6-step ordering confirmed correct; step 3's synchronous call is the CR-01 defect |
| `src/nativespeaker/api/auth/verification.py` | §1.2 JWT verification | ✓ VERIFIED (with a defect — see gap) | iss/aud/alg/sub rules all correct; no-network-call guarantee is false on cache-miss `kid` |
| `src/nativespeaker/api/auth/context.py` | §1.4 typed identity context | ✓ VERIFIED | `LinkedIdentity`/`PreAuthIdentity`/`RequestContext`, frozen dataclasses, `REQUEST_CONTEXT_SCOPE_KEY` pinned |
| `src/nativespeaker/api/auth/identity.py` | §1.3 single-query four-outcome resolution | ✓ VERIFIED | One outer-joined statement, `Admit`/`Reject` closed union |
| `src/nativespeaker/api/auth/telemetry.py` | §1.2/§8.2 rejection counter + security log | ✓ VERIFIED | Bounded-cardinality `RejectionCounter`; exporter absence is a documented, accepted gap (D-35-06-A), not a must-have violation |
| `src/nativespeaker/api/auth/budgets.py` | §7.1 provider-call budget seam | ✓ VERIFIED | `BudgetGate.check_all`/`charge_all`, non-destructive check, all-or-nothing charge |
| `src/nativespeaker/api/auth/adapters.py` | §7 adapter interfaces, zero implementations | ✓ VERIFIED | Protocol-only, no `firebase_admin` import, `test_foundation_calls_no_adapter_method_anywhere_in_src` |
| `src/nativespeaker/api/auth/keys.py` | §4.3/§6.4 keyed subject hashing | ✓ VERIFIED | HMAC-SHA-256, fail-closed active key (D-22), base64-decode-once discipline |
| `src/nativespeaker/api/auth/audit.py` | §4 audit writer, two modes | ✓ VERIFIED | `build_details`, `redact`, `AuditWriter` — actor-consistency and details-shape guards raise before DB write |
| `src/nativespeaker/api/auth/challenges.py` | §6 challenge store, claim/consume | ✓ VERIFIED | Single conditional-UPDATE serialization point; concurrency confirmed live |
| `src/nativespeaker/api/auth/modesignal.py` | §6.5 mode-signal partition check | ✓ VERIFIED | Syntactic-only, no side effects, duplicate/invalid-value handling |
| `src/nativespeaker/api/auth/__init__.py` | Stable public seam for phases 36-46 | ✓ VERIFIED | 58 symbols re-exported, confirmed importable |
| `src/nativespeaker/api/models/users.py` | `core.users` at v2.0 shape | ✓ VERIFIED | Exactly 7 columns, `email` nullable, no `jwt_sub`/`name`/`subscription_plan` |
| `src/nativespeaker/api/models/identities.py` | `core.external_identities` + 3 enums | ✓ VERIFIED | `IdentityProvider`, `IdentityState`, `NativeClaimProvider` all present |
| `src/nativespeaker/api/models/auth.py` | `AuthOperation`/`AuthEventResult`/`AuthChallenge`/`AuthEvent` | ✓ VERIFIED | 44-member closed `AuthEventResult`, both new tables mapped |
| `src/nativespeaker/api/app/lifespan.py` | Startup path with no `firebase_admin`/Apple verifier | ✓ VERIFIED | Confirmed no such imports; registry/error assertions run before DB/JWT/LLM init |
| `src/nativespeaker/api/app/main.py` | App construction, middleware order, doc routes off | ✓ VERIFIED | `docs_url=None` etc.; `redirect_slashes=False`; middleware order test passed |
| `src/nativespeaker/api/app/dependencies.py` | D-02 fail-loudly `Depends()` accessors | ✓ VERIFIED | `get_request_context`/`get_linked_identity`/`get_preauth_identity` all raise on absent/wrong-typed context |
| `config/config.yaml` | `hmac:` block, no `apple`/`quotas` | ✓ VERIFIED | Confirmed by direct read — `active_version`, `keys`, `idp_account_keys` present, no legacy blocks |
| `tests/e2e/test_startup_assertion.py` | Real-startup proof | ✓ VERIFIED | Ran myself — 9/9 passed |
| `.planning/phases/35-foundation/COVERAGE.md` | api-coverage declaration | ✓ VERIFIED | Contains "No external API integration" |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `app/main.py` | `auth/barrier.py` | `app.add_middleware(AuthBarrierMiddleware)`, called before `RequestLoggingMiddleware` | ✓ WIRED | Confirmed by direct read + `test_stack_is_logging_then_barrier_outermost_first` (ran myself, passed) |
| `app/lifespan.py` | `auth/registry.py` | `app.state.route_registry = REGISTRY; assert_route_enumeration(app, app.state.route_registry)` | ✓ WIRED | Confirmed running at real startup via `test_assertion_passes_against_the_live_app` (ran myself) |
| `auth/barrier.py` | `auth/identity.py` | One session from `scope["app"].state.session_factory`, one `resolve_identity` call | ✓ WIRED | Confirmed by direct read (barrier.py:121-125) and `test_every_outcome_issues_exactly_one_identity_statement` (ran myself) |
| `auth/barrier.py` | `auth/audit.py` | `write_standalone` called from `_reject` only when `meta.operation is not None` | ✓ WIRED | Confirmed by direct read (barrier.py:164-213) and live-DB test (ran myself) |
| `auth/barrier.py` | `auth/telemetry.py` | `record_rejection(scope["app"].state, ...)` on every rejection | ✓ WIRED | Confirmed by direct read; counter increments on/off audited path alike |
| `auth/audit.py` | `auth/keys.py` | `actor_subject_hash` derived through the shared `HmacKeyring` | ✓ WIRED | Confirmed by direct read (audit.py:243) — no local hmac/hashlib import in audit.py |
| `auth/challenges.py` | `auth/keys.py` | `preauth_subject_hash` via the same shared derivation | ✓ WIRED | Confirmed by direct read (challenges.py:133-134, 255-257) |
| `app/dependencies.py` | `auth/context.py` | Accessors read `REQUEST_CONTEXT_SCOPE_KEY` off `request.state`, raise when absent | ✓ WIRED | Confirmed by direct read (dependencies.py:58-86) |
| `routers/chats.py` | `app/dependencies.py` | `Depends(get_linked_identity)`, `identity.user.id` used throughout | ✓ WIRED | Confirmed by direct read — no direct token/claims access in any handler |
| `app/lifespan.py` | `src/.../errors.py` | `assert_registry_total()` called before serving traffic | ✓ WIRED | Confirmed by direct read (lifespan.py:35) |
| `config.py` | `config/config.yaml` | `AppConfig(**yaml_data, ...)`, `hmac: HmacConfig` required (no default) | ✓ WIRED | Confirmed by direct read — a missing `hmac:` block would raise at load, matching D-22 |

### Data-Flow Trace (Level 4 — adapted for a backend service)

| Chain | Source | Produces Real Data | Status |
|---|---|---|---|
| Declared `REGISTRY` (8 entries) → live `app.routes` | `auth/registry.py::enumerate_registered` walks `app.routes` at real startup | Yes — confirmed both by direct `python -c` execution (8 routes) and by the enumeration assertion running inside the real lifespan | ✓ FLOWING |
| Barrier rejection → `audit.auth_events` row | `AuditWriter.write_standalone` opens a real session from `app.state.session_factory` and commits | Yes — confirmed against live PostgreSQL by two tests run directly in this session | ✓ FLOWING |
| `config/config.yaml` `hmac:` block → `HmacKeyring` | `EnvironmentConfig.load_config` → `AppConfig(**yaml_data)` → `HmacKeyring(config.hmac)` in lifespan | Yes — the committed base64 keys are real 32-byte material, decoded once at load; no default/mock key exists in the production path | ✓ FLOWING |
| Resolved `(issuer, subject)` → `LinkedIdentity`/`Reject.actor_*` | `resolve_identity`'s single outer-joined query | Yes — no hardcoded or mocked identity in the production path; seeded-row tests confirm the query is real | ✓ FLOWING |

No hollow props, static fallbacks, or mocked data sources found on any production path (test fixtures
that stub the JWKS *transport* for unit-level JWT tests are the only mocking, and that is appropriate
test isolation, not a production stub — except where noted as vacuous below).

### Behavioral Spot-Checks

Run directly in this session, against the live PostgreSQL instance and the real ASGI app, in addition
to the orchestrator's already-completed full-suite run (1137 passed, 0 failed) that I relied on rather
than re-running.

| Behavior | Command | Result | Status |
|---|---|---|---|
| Challenge claim serializes 8 concurrent attempts to exactly 1 winner | `pytest tests/e2e/test_challenge_store.py::TestTheClaimSerializesConcurrentAttempts::test_exactly_one_of_eight_concurrent_claims_wins ::test_the_losers_mutated_nothing` | 2 passed | ✓ PASS |
| Lifespan runs the §2.3 assertion for real, at real startup, against the real router | `pytest tests/e2e/test_startup_assertion.py::TestStartupAssertion` (9 cases) | 9 passed | ✓ PASS |
| Barrier rejection writes exactly one audit row, all-NULL actor / all-populated actor | `pytest tests/e2e/test_audit_writer.py::TestAnOnPathRejectionWritesExactlyOneRow::test_a_missing_token_writes_one_row_and_returns_the_shared_401 ::TestAVerifiedActorIsRecordedAsAKeyedHash::test_an_unlinked_subject_writes_all_three_actor_fields` | 2 passed | ✓ PASS |
| Middleware order, doc routes disabled, redirect_slashes off; wire contract over real ASGI transport | `pytest tests/unit/test_app_wiring.py tests/e2e/test_barrier_wire_contract.py` | 20 passed | ✓ PASS |
| Admission matrix: historical/blocked indistinguishable, linked-active admitted, one query per outcome | `pytest tests/e2e/test_barrier_admission.py::TestOutcomesTwoAndThreeAreIndistinguishable ::TestOutcomeFourLinkedAndActive ::TestOneQueryPerRequest` | 13 passed | ✓ PASS |
| Real app module imports; registry has exactly 8 routes | `python -c "import nativespeaker.api.app.main as m; ..."` | `routes: 8`, `auth __all__ count: 58` | ✓ PASS |
| No thread-offload anywhere in `src/`; no fetch timeout configured on the JWKS client | `grep -rn "run_in_threadpool\|to_thread\|ThreadPoolExecutor" src/` / `grep -n "timeout" auth/verification.py` | Both empty | ✗ FAIL — confirms CR-01 |
| The test claiming "no additional JWKS fetch" actually exercises the fetch path | Read `TestProductionVerifier::test_two_verifications_issue_no_additional_jwks_fetch` and its `jwks_client` fixture directly | Fixture mocks the whole `PyJWKClient` class; asserts on a method (`get_signing_keys`) `verify()` never calls | ✗ FAIL — confirms WR-05 (test is vacuous, not evidence) |

### Probe Execution

N/A — no `scripts/*/tests/probe-*.sh` convention exists in this repository and none is referenced by
any Phase 35 plan or SUMMARY. This phase is verified through pytest, which the orchestrator already
ran in full (1137 passed) and which I re-exercised at the named-test level above.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| FOUND-01 | 01, 02, 03, 04, 05, 06, 11 | Mandatory pre-handler barrier is the only place JWT acceptance + identity resolution happen; admits only `identity_state='active'` AND `users.active` TRUE | ✓ SATISFIED | `barrier.py` + `identity.py`, confirmed live |
| FOUND-02 | 01, 06, 11 | Exactly-one-Authorization wire contract enforced | ✓ SATISFIED | `wire.py`, confirmed live over real ASGI transport |
| FOUND-03 | 01, 04, 11 | Route registry + startup/CI enumeration assertion, 3-way partition | ✓ SATISFIED | `registry.py`, confirmed running at real startup |
| FOUND-04 | 01, 02, 11 | One shared error-registry module; identical body/status/copy within a class | ✓ SATISFIED | `errors.py`, single `ErrorClass` per exception, `error_response()` sole factory |
| FOUND-05 | 08, 09, 11 | Audit writer: exactly one row per on-path attempt, redacted details, keyed `actor_subject_hash` with version | ✓ SATISFIED | `audit.py` + `keys.py`, confirmed live |
| FOUND-06 | 07, 11 | §7.1 provider-call budget seam, plain in-process counters, no rate-limiting dependency | ✓ SATISFIED | `budgets.py`, `TestNotTrafficLimiting` guards the boundary |
| FOUND-07 | 10, 11 | Challenge store claim/consume protocol | ✓ SATISFIED | `challenges.py`, concurrency confirmed live |
| FOUND-08 | 07, 11 | Adapter interfaces only, zero implementations | ✓ SATISFIED | `adapters.py`, `test_foundation_calls_no_adapter_method_anywhere_in_src` |

No orphaned requirements: REQUIREMENTS.md maps only FOUND-01…FOUND-08 to Phase 35 (FOUND-09 is
explicitly deferred to v2.1 per D-08), and all eight are claimed by at least one plan above. (Note:
REQUIREMENTS.md's own checkboxes for FOUND-01…08 are still unchecked `[ ]` as of this verification —
that is administrative bookkeeping outside this phase's artifacts, not a gap in the delivered code.)

### Anti-Patterns Found

Carried from the independent code review (`35-REVIEW.md`, 69 files, completed same day) and confirmed
by my own direct reading where noted. None of these below is newly discovered by me except the SUMMARY
mischaracterization noted in the gap above.

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `auth/barrier.py` / `auth/verification.py` | barrier.py:113, verification.py:100-124 | Synchronous, blocking JWKS-fetch call made directly from `async def __call__`, no timeout configured | 🛑 Blocker (CR-01) | Confirmed by me independently — see gap above. Causes measured event-loop stalls (1.2s at 0.4s RTT); a slow/hung JWKS endpoint scales to 30s per request, and can fail `/health/ready` under a sustained trickle |
| `app/errors.py` | 39 | `validation_error_handler` logs `exc_info=exc`, and `RequestValidationError.__str__` renders the raw request-body `input` value into the traceback | ⚠️ Warning (WR-02) | Confirmed by direct read. Any oversized `ChatRequest.phrase`/`MessageRequest.message` puts the user's submitted text in the operator log — notable given AGENTS.md frames this as a grammar-fixing product handling users' private text. Becomes a §6.1 violation once phase 37+ add a `challenge_id` body field. Not tied to a stated must-have (redaction must-haves are scoped to `audit.auth_events.details`, a different code path), so not scored as a failed truth, but worth fixing promptly |
| `auth/barrier.py` | 170 | Barrier's 401 omits `WWW-Authenticate`; the accessors' 401 (`AuthenticationError`) includes it | ⚠️ Warning (WR-01) | Two 401s from one service differ in headers — an anti-oracle asymmetry, though not one any stated must-have's literal text (byte-identical *bodies* and *status*) covers |
| `auth/keys.py` | 67-69 | `_digest`'s `issuer + ":" + subject` framing is ambiguous — not exploitable today (one pinned issuer) but becomes a cross-issuer collision risk once phase 41 configures a second issuer | ⚠️ Warning (WR-03) | Confirmed by direct read. One-way-reversible per the module's own docstring, so fixing after any row exists is not possible — worth fixing before phase 41, not urgent for phase 35 |
| `auth/keys.py` | 140-164 | `actor_subject_matches` always recomputes under the *active* key; correct for the challenge store (D-21) but a latent bug for a future phase-39 audit-history query against a rotated key | ⚠️ Warning (WR-04) | Confirmed by direct read. No current call site is affected (phase 35 doesn't query rotated-key audit rows) |
| `tests/unit/test_jwt_security.py` | 320-325 | `test_two_verifications_issue_no_additional_jwks_fetch` is vacuous (see gap above) | ⚠️ Warning (WR-05) | Directly confirmed — this is the test that let CR-01 ship undetected |
| `tests/e2e/test_model_queries.py` | 107-118 | `test_the_previous_rows_were_rolled_back` depends on source-order coupling to a prior test; passes vacuously if run alone | ⚠️ Warning (WR-06) | Not tied to a phase-35 must-have (general test-isolation infra); flagged for awareness |
| `tests/unit/test_exception_handlers.py` | 70-83 | `test_handler`'s code assertion is membership in a 6-element set rather than an exact expected code per case | ⚠️ Warning (WR-07) | The production mapping itself is correct (confirmed by direct read of every `ServiceError` subclass's `error_class`), so FOUND-04 is not violated — but this test would not catch a future regression |
| `tests/e2e/test_model_queries.py` | 47, 52 | `assert result.all() is not None` can never be false | ℹ️ Info (IN-01) | Cosmetic; the real assertion is the preceding `session.exec` raising on schema drift |
| `errors.py` | 327-339, 364-365, 396-407 | 5 `ServiceError` subclasses have no raise site (some reserved for later phases, `WebhookVerificationError` describes a route D-16 deleted) | ℹ️ Info (IN-02) | Not distinguished as reserved-vs-dead in comments |
| `auth/registry.py` | 35 | `RouteMetadata.quota_checked` is declared, never set, never read (void per D-05) | ℹ️ Info (IN-03) | Dead field from a deleted subsystem |
| `auth/barrier.py` | 142, 207 | `_bucket_kind` derived twice per audited rejection instead of once | ℹ️ Info (IN-04) | Minor duplication, contradicts the module's own "one evaluation per request" principle for a different value |

### Known Open Items (carried forward from phase artifacts, not re-litigated as new gaps)

Per `COVERAGE.md`'s own accounting, 6 of its 9 accepted v2.0 gaps are decided/closed (Envoy contract
deferral, backend rate-limiting removal, the k8s 429-body mismatch, no timing normalization, empty
`access_tiers` pending Phase 36, REBIND-01 landing early). The 3 explicitly marked open-and-unowned:

1. **D-35-06-A — no metrics exporter.** `auth/telemetry.py::RejectionCounter` correctly increments on
   every rejection (confirmed by direct read and by `TestEveryRejectionIsCounted` passing), but nothing
   scrapes `snapshot()`. §1.2's operational alert cannot fire. Does not violate any stated must-have
   (none requires an exporter) — an observability gap for a later phase to own, not a Phase 35 defect.
2. **`actor_provider` NULL on every rejection this phase can write**, even where a stored provider
   exists (`historical_identity`, `blocked_user`). Confirmed by direct read: `identity.py::Reject`
   never carries a provider, and `barrier.py::_audit` always passes `actor_provider=None`. This matches
   the stated must-have's literal text ("NULL otherwise... never taken from claims, headers, or client
   input") — Phase 35 writes zero production audit rows regardless (all 8 registered routes declare
   `operation=None`), so nothing is lost yet. Phase 37 owns widening `Reject` to carry the resolved row.
3. **D-35-11-A — `POST /chats` returns 500 for a grammatically correct phrase.** Confirmed present in
   `deferred-items.md` with a 4-way reproduction. Outside Phase 35's file scope (`models/llm.py`,
   `config/prompt.txt`) and outside FOUND-01…08 entirely — a prompt/model-contract product decision,
   not an auth-foundation defect. Not independently re-verified by me (no phase-35 artifact touches it),
   carried forward as-is per the phase's own record.

None of these three undermines the phase's scoped goal (boots + enumeration assertion runs for real).

## Gaps Summary

**One gap, narrowly scoped, does not block the phase's stated bar.** The application boots cleanly,
the lifespan runs to completion, and the §2.3 enumeration assertion executes for real against the real
router — independently confirmed by running the relevant tests myself against the live app and a live
database, not merely by reading SUMMARY.md. All eight FOUND-01…08 requirements are substantively
implemented, wired, and covered by tests I either ran myself or trust from the orchestrator's clean
full-suite run, cross-checked against direct source reading of every core module.

The one failed truth — plan 35-02's claim that JWT verification "performs no per-request network
call" — is real, not a nitpick. It is the same defect the independent code review flagged as CR-01
(its only critical finding across 69 reviewed files), and I reproduced its evidentiary basis
independently (no thread offload anywhere in `src/`, no configured JWKS fetch timeout, and the one
test that names the property is vacuous by construction). It affects the barrier's own core
deliverable (JWT verification, FOUND-01/FOUND-02's territory), not a downstream chat/quota flow the
phase explicitly defers to Phase 36 — so it is in scope for this verification, not exempted by the
"boots, not fully-working" framing.

**Recommended path:** this is a small, well-specified fix (offload `verify()` to a threadpool, bound
the JWKS fetch timeout, add a negative-kid cache, replace the vacuous test) that the code review
already drafted concretely. Given the phase's explicit "boots" bar is otherwise fully met, the
developer has two reasonable options: (a) close this gap with a short follow-up plan before treating
Phase 35 as done, or (b) explicitly accept the risk for now (AGENTS.md notes there are no users yet)
and record it as a tracked override with an owner and a deadline. I have not applied an override
myself — this is a judgment call for the developer, not something to paper over silently.

To accept it as a tracked, deliberate deferral instead of closing it, add to this file's frontmatter:

```yaml
overrides:
  - must_have: "Token verification performs no per-request network call"
    reason: "CR-01 confirmed; no production users yet per AGENTS.md. Tracked as a fast-follow fix before wider traffic."
    accepted_by: "{your name}"
    accepted_at: "{ISO timestamp}"
```

### Human Verification Required

None. Every applicable truth was either directly exercised by a passing test (run by me in this
session or by the orchestrator's full-suite run I relied on) or reasoned conclusively from source code
that structurally forecloses the alternative (e.g., `register_class`'s duplicate-code guard makes a
shared-code class a load failure, not a runtime possibility). The four `verification: backstop` truths
(zero-routes/zero-entries enumeration; budget counters are plain non-negative ints; a `BudgetGate` is
per-request/in-process only; importing the adapter module twice has no side effect) each had an
explicit, wired, passing test found and confirmed by name — none were left to abstain as
`insufficient_spec`.

---

_Verified: 2026-08-21T13:00:00Z_
_Verifier: Claude (gsd-verifier)_
