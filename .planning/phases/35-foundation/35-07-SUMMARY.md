---
phase: 35-foundation
plan: 07
subsystem: adapters
tags: [protocol, strenum, frozen-dataclass, budgets, firebase, store-verification, vendor-proof]

requires:
  - phase: 35-foundation
    plan: 02
    provides: "errors.py with VERIFICATION_TEMPORARILY_UNAVAILABLE/ErrorClass/ServiceError; auth/verification.py with VerifiedClaims"
provides:
  - "auth/budgets.py — the §7.1 provider-call budget gate: BudgetGate, BudgetExhausted, ADAPTER_FIREBASE_LOOKUP, FIREBASE_LOOKUP_ATTEMPTS"
  - "auth/adapters.py — the three §7 Protocols, four closed StrEnums, five frozen result types, zero implementations"
  - "tests/unit/test_budgets.py — 43 tests over the check-all-then-charge-together contract and the absence of traffic limiting"
  - "tests/unit/test_adapter_interfaces.py — 53 tests proving the seam declares and never does"
affects: [35-11, 36-rebinding, 37, 40, 41, 42]

actuals:
  tokens: 13106
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "A non-destructive check separated from an all-or-nothing charge, so the check may be called freely and no partial charge is observable on any path"
    - "Name-sequence deduplication inside the gate, which makes check and charge structurally incapable of disagreeing rather than agreeing by caller discipline"
    - "An exception carrying its error mapping as class data rather than as behaviour, so the call site cannot get the mapping wrong but must still act on it"
    - "ast-parsing the module under test to assert it holds only declarations — a body, a module-level function, or a non-declaration statement is a test failure"
    - "A subprocess for the module-absence assertion, because an in-process sys.modules check turns on test ordering rather than on the module's own imports"

key-files:
  created:
    - src/nativespeaker/api/auth/budgets.py
    - src/nativespeaker/api/auth/adapters.py
    - tests/unit/test_budgets.py
    - tests/unit/test_adapter_interfaces.py
  modified: []
  deleted: []

key-decisions:
  - "BudgetExhausted is deliberately not a ServiceError. One that auto-converted to a 503 would let an unhandled exhaustion produce a plausible client response while silently skipping the audit row the audited attempt path requires; as a plain Exception carrying audit_result and error_class as data, an unhandled one is a loud 500 and a handled one cannot mis-map."
  - "A name repeated in one sequence collapses to one budget. Without it, check_all([N, N]) against a remaining count of 1 would report capacity that charge_all([N, N]) would overspend — the one way check and charge could disagree."
  - "An undeclared budget name has zero capacity rather than raising or reading as unlimited. Fail-closed keeps check_all a pure read, which is the property the whole contract rests on."
  - "A negative limit clamps to zero; a non-int limit raises TypeError. A negative limit is representable honestly as 'no capacity', but a float is not representable without the rounding the truth forbids."
  - "ProviderDataEntry is declared as a twelfth symbol beyond the plan's export list, because §7.1's ok(provider_data_entries) needs a shape and the alternative (a mutable Mapping) would violate the all-result-types-are-immutable truth."
  - "No Protocol is @runtime_checkable. An isinstance pass over method names asserts nothing about the contracts in the docstrings, and having it available invites exactly that false comfort."

patterns-established:
  - "Mutation-verify every structural assertion before claiming coverage, then confirm the file byte-identical with git diff --exit-code"
  - "Assert closed enum sets as exact ordered member lists, so widening is a failure rather than a silent addition"
  - "Record a phase-scoped test's expiry and its owning phase in the summary, so a later phase deletes it deliberately instead of debugging it"

requirements-completed: [FOUND-06, FOUND-08]

coverage:
  - id: D1
    description: "The Firebase getUser retry budget permits exactly three attempts and the fourth is exhausted"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestFirebaseLookupBudget (5 tests)"
        status: pass
      - kind: other
        ref: "python -c '...[g.charge_all([N]) for _ in range(A)]; print(g.check_all([N]) == N, g.remaining(N))' -> True 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "check_all is non-destructive: any number of calls charges nothing"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestCheckAllIsNonDestructive (4 tests, mutation-verified)"
        status: pass
      - kind: other
        ref: "Mutation: decrement inside check_all -> 4 failures; file restored byte-identical"
        status: pass
    human_judgment: false
  - id: D3
    description: "No counter is incremented unless every applicable budget has capacity; charged counters stay charged"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestChargeAllIsAllOrNothing (6 tests, mutation-verified)"
        status: pass
      - kind: other
        ref: "Mutation: charge inside the check loop -> 3 failures; file restored byte-identical"
        status: pass
    human_judgment: false
  - id: D4
    description: "Budgets are evaluated broadest to narrowest; the global budget is the primary result and every exhausted limiter is recorded"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestCheckAllOrdering (4 tests), ::TestExhausted (4 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Empty name sequences are no-ops: check_all returns None and charge_all charges nothing"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestEmptySequences (3 tests)"
        status: pass
      - kind: other
        ref: "python -c 'g=BudgetGate({}); print(g.check_all([]) is None)' -> True"
        status: pass
    human_judgment: false
  - id: D6
    description: "Exhaustion maps to internal firebase_lookup_unavailable and client verification_temporarily_unavailable"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestExhaustionMapping (3 tests, including that it is not a ServiceError)"
        status: pass
    human_judgment: false
  - id: D7
    description: "The seam is not backend traffic limiting: no limits/redis/valkey import, no module-level counter, no ip/user/route/request key"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestNotTrafficLimiting (3 tests, exact-set assertion over every public signature's parameters)"
        status: pass
    human_judgment: false
  - id: D8
    description: "Counters are integers with no rounding, float, or overflow path; remaining never goes below zero"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestCounterFloor (4 tests)"
        status: pass
      - kind: other
        ref: "Backstop truth. Single-threaded evidence only; the overflow dimension is vacuous because Python ints are arbitrary precision"
        status: partial
    human_judgment: true
  - id: D9
    description: "A BudgetGate is per-request and in-process, sharing no counter across requests or processes"
    requirement: FOUND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_budgets.py::TestInstanceIsolation (3 tests — no shared state, the limits mapping is copied, charging does not mutate the caller's)"
        status: pass
      - kind: other
        ref: "Backstop truth. No concurrency test exists because there is no shared state to contend for; the claim is that none is made"
        status: partial
    human_judgment: true
  - id: D10
    description: "The adapter module declares interfaces and result types only — no concrete class, no method body, no module-level function"
    requirement: FOUND-08
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py::TestZeroImplementations (10 tests, ast-based, mutation-verified twice)"
        status: pass
      - kind: other
        ref: "Mutations: a Protocol method body -> 1 failure; a concrete subclass -> 3 failures; both restored byte-identical"
        status: pass
    human_judgment: false
  - id: D11
    description: "No firebase_admin import, no network client, and no I/O at import time"
    requirement: FOUND-08
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py::TestNoProviderDependency (3 tests, one in a subprocess), ::TestImportIsSideEffectFree (4 tests)"
        status: pass
      - kind: other
        ref: "python -c \"import sys, nativespeaker.api.auth.adapters; print('firebase_admin' in sys.modules)\" -> False"
        status: pass
    human_judgment: false
  - id: D12
    description: "The four closed outcome sets carry exactly their §7 members and no more"
    requirement: FOUND-08
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py::TestClosedOutcomeSets (5 tests, exact ordered member lists)"
        status: pass
      - kind: other
        ref: "Mutation: a fifth ProviderDataOutcome member -> 1 failure; restored byte-identical"
        status: pass
    human_judgment: false
  - id: D13
    description: "Foundation calls get_user_provider_data, revoke_refresh_tokens, and every store and vendor-proof method exactly zero times"
    requirement: FOUND-08
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py::TestZeroImplementations::test_foundation_calls_no_adapter_method_anywhere_in_src (scans every src/ module)"
        status: pass
    human_judgment: false
  - id: D14
    description: "ClaimKind is a parameter of both device-slot methods, so the adapter pins the bit and phase 06 cannot reach phase 07's slot"
    requirement: FOUND-08
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py::TestVendorProofAdapter (6 tests, including that no non-slot method takes a claim_kind)"
        status: pass
    human_judgment: false
  - id: D15
    description: "Every result type is a frozen dataclass or a StrEnum; none is mutable"
    requirement: FOUND-08
    verification:
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py::TestResultTypesAreImmutable (9 tests, including an exact-set assertion over every declared class)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-08-21
status: complete
---

# Phase 35 Plan 07: Provider-Call Budgets and Adapter Interfaces Summary

**The two seams foundation never exercises now exist and are provably empty: a budget gate whose
check cannot charge and whose charge cannot half-charge, and three Protocols with not one method
body, not one `firebase_admin` import, and a test that fails the moment either appears.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-21T05:40Z
- **Completed:** 2026-08-21T05:52Z
- **Tasks:** 2 of 2
- **Files created:** 4 (2 source, 2 test). None modified, none deleted.

## Accomplishments

- **§7.1's gating helper ships with the ordering that is load-bearing for phases 37/40/41/42.**
  `check_all` reads and mutates nothing; `charge_all` is the only mutator, and it re-checks every
  name before touching any counter, so no partial charge is observable on any path — not on the
  exception path, not by ordering, not ever. Both properties are mutation-verified, not asserted.
- **Exactly one budget name ships.** `ADAPTER_FIREBASE_LOOKUP` with `FIREBASE_LOOKUP_ATTEMPTS = 3`.
  `test_exactly_one_budget_name_ships` is an exact-set assertion over the module's public string
  constants, so a later phase adding an endpoint-layer name here fails the build rather than
  quietly widening foundation's scope.
- **D-05 is enforced by test, not by intention.** `TestNotTrafficLimiting` asserts no
  `limits`/`redis`/`valkey` import, no module-level mutable state, and — as an exact-set assertion
  over every public method's parameters — no `ip`, `user`, `route`, or `request` key anywhere in
  the gate's surface.
- **Three Protocols, zero implementations, proven structurally.** The test parses `adapters.py`
  with `ast` and asserts every method body holds nothing but a docstring or `...`, that the module
  declares no function at all, and that its module body holds only declarations. A concrete class
  trips three separate assertions.
- **Foundation calls the seam zero times, and that is a test.**
  `test_foundation_calls_no_adapter_method_anywhere_in_src` scans every module under
  `src/nativespeaker/` for all ten adapter method names.
- The unit suite grew **310 → 406** (+96) with zero regressions; e2e and schema are exactly at
  their measured baselines and both gates stay clean.

### The one shipped budget name

| Constant | Value | Scope |
|---|---|---|
| `ADAPTER_FIREBASE_LOOKUP` | `"adapter_firebase_lookup"` | the global provider-call budget guarding the Firebase Admin `getUser` lookup |
| `FIREBASE_LOOKUP_ATTEMPTS` | `3` | the initial call plus up to two additional, for retryable causes only |

No endpoint-layer name exists. Every one of them belongs to a later phase.

### The adapter surface (12 symbols)

| Symbol | Kind | §  | Owning phase for the implementation |
|---|---|---|---|
| `ProviderDataOutcome` | StrEnum (4, closed) | 7.1 | 02, 05, 06, 07 |
| `ProviderDataEntry` | frozen dataclass | 7.1 | 02 (the classifier itself) |
| `ProviderDataResult` | frozen dataclass | 7.1 | 02, 05, 06, 07 |
| `RevocationOutcome` | StrEnum (2, closed) | 7.1 | 11 |
| `FirebaseAdminAdapter` | Protocol (3 methods) | 7.1 | 02, 05, 06, 07, 11 |
| `VerifiedNotification` | frozen dataclass | 7.2 | 08, 09 |
| `VerifiedTransaction` | frozen dataclass | 7.2 | 10 |
| `StoreState` | frozen dataclass | 7.2 | 10 |
| `StoreAdapter` | Protocol (3 methods) | 7.2 | 08, 09, 10 |
| `ClaimKind` | StrEnum (2, closed) | 7.3 | 06 (`anonymous`), 07 (`registered`) |
| `DeviceBitState` | StrEnum (3, closed) | 7.3 | 06, 07 |
| `VendorProofAdapter` | Protocol (4 methods) | 7.3 | 06, 07 |

## Task Commits

1. **Task 1 (TDD): the §7.1 provider-call budget gate** — `8bf360e` (test, RED) → `36abf5e` (feat, GREEN)
2. **Task 2 (TDD): adapter interfaces with zero implementations** — `0fca1ed` (test, RED) → `2dd7149` (feat, GREEN)

Both RED commits left the rest of the suite at its prior count (310, then 353) and the new file
failing at collection, because in both cases the module under test did not yet exist. Neither task
needed a REFACTOR commit — nothing was left to clean up that the GREEN commit had not already
shaped.

**A RED-only lint artifact, recorded so it is not mistaken for a defect later.** `ruff`'s isort
resolves first-party packages against the filesystem, so at RED — with `budgets.py` absent —
`from nativespeaker.api.auth.budgets import ...` classified as third-party and `I001` fired on an
import block that is correctly ordered for the state the GREEN commit produces. Confirmed before
committing RED by creating an empty file at the target path, re-running `ruff` (clean), and
deleting it. Both gates are clean at every commit that contains a source module.

## Decisions Made

- **`BudgetExhausted` is deliberately not a `ServiceError`.** Making it one would have been the
  obvious move — the registry already maps exceptions to responses — and it is the wrong one.
  Exhaustion sits on the audited attempt path, where a rejection must write an `audit.auth_events`
  row. A `ServiceError` that auto-converted to `verification_temporarily_unavailable` would let an
  unhandled exhaustion return a perfectly plausible 503 while silently skipping that row: the
  failure would look exactly like success from outside. As a plain `Exception` carrying
  `audit_result` and `error_class` as class data, the call site cannot get the mapping wrong, must
  still act on it, and an unhandled one surfaces as a loud 500 instead of a convincing 503.
- **A name repeated in one sequence collapses to one budget.** This is the only way `check_all` and
  `charge_all` could have disagreed: `check_all([N, N])` against a remaining count of 1 reads as
  "capacity available", and a naive `charge_all([N, N])` would then spend two units against one.
  Deduplicating inside the gate makes the disagreement unrepresentable rather than a caller
  discipline. Mutation-verified — replacing `_ordered_unique` with `list(names)` fails two tests.
- **An undeclared budget name has zero capacity.** The alternatives were raising `KeyError` or
  treating it as unlimited. Unlimited fails open at a security seam. Raising would make `check_all`
  a method that can throw, which destroys the property the entire contract rests on — that the
  check is a free, pure read a caller may make as often as it likes. Zero capacity is loud enough
  in practice (the provider path 503s) and keeps `check_all` total.
- **A negative limit clamps to zero, a non-int limit raises.** Not an inconsistency: a negative
  limit *is* representable honestly as "no capacity", whereas a float is not representable at all
  without the rounding the plan's truth explicitly forbids — truncating `2.7` to `2` would hand out
  a different number of provider calls than the one written down. Clamping also avoids turning a
  constant-declaration bug into a 500 on every request rather than a 503 on the one path that meters.
- **`ProviderDataEntry` is a twelfth symbol beyond the plan's export list.** §7.1 specifies
  `ok(provider_data_entries)` without pinning an entry shape, and the alternatives were a mutable
  `Mapping` (which would violate the all-result-types-are-immutable truth) or an anonymous
  `tuple[tuple[str, str], ...]`. `provider_id` and `uid` are the two fields `02-create-user.md`
  already pins as the classifier's inputs. The **classification rule** — empty means anonymous,
  exactly one recognized entry means that provider, every other shape rejects, never take the first
  recognized entry — is left entirely to phase 02, and the docstring says so.
- **`verify_id_token` keeps §7.1's `-> VerifiedClaims` signature even though §1.2's verifier returns
  a two-tuple.** These are two seams onto one capability, not a contradiction: the barrier holds a
  `TokenVerifier` whose `verify` returns `(claims, reason)` precisely because middleware installed
  with `add_middleware` sits outside `ExceptionMiddleware` (D-01), while §7.1's method is for later
  phases calling from inside a handler, where raising is the established idiom. The docstring records
  the relationship rather than leaving a reader to discover the mismatch.
- **No Protocol is `@runtime_checkable`,** and a test asserts it stays that way. A runtime
  `isinstance` against these checks method *names* only — it would happily pass an object that
  ignores every rule in the docstrings (no call under a lock, a fixed timeout, no provider text to
  clients). Having the check available invites exactly that false comfort.
- **`StoreAdapter` rejects with an undistinguished `None` on all three methods.** §7.2 requires that
  rejection never distinguish malformed from unverifiable material to the client; a richer rejection
  type at this seam would be an oracle by construction. The test asserts the return annotation of
  each of the three methods is exactly `X | None`.

## Deviations from Plan

None. The plan executed exactly as written, with two additions inside its own instructions rather
than against them:

1. **`ProviderDataEntry`** — a twelfth declared symbol, for the reason given above. The plan's
   `<action>` instructs "frozen dataclass and `StrEnum` result types"; this is one, and the eleven
   enumerated exports are all present and unchanged.
2. **`ProviderDataResult.entries` defaults to `()`** so a non-`ok` outcome is constructible without
   naming an empty tuple at each site.

No Rule 1, 2, or 3 auto-fix was needed, and no Rule 4 architectural question arose. No package was
installed and no dependency changed — `pyproject.toml` and `uv.lock` are untouched, which
`T-35-07-SC` records as the gate for this plan.

## Issues Encountered

- **One test failure of my own, immediately after GREEN.** `test_the_module_docstring_records_the_shared_rules[5-10 seconds]` failed because the docstring had wrapped
  the phrase across a line break as `5-10\n  seconds`. Reflowed the line so the phrase is
  contiguous. Recorded because it is the honest cost of asserting on docstring text: the assertion
  is real (it fails if the §7 shared rule is deleted) but it is coupled to line wrapping, and a
  future editor reflowing that paragraph will see it fail.
- **`firebase_admin` is in `sys.modules` during a normal unit run.** `app/lifespan.py` still imports
  it at module scope until plan 04 deletes it (D-16), and `test_app_wiring.py` imports `app.main`.
  An in-process `'firebase_admin' not in sys.modules` assertion would therefore have passed or
  failed on test ordering rather than on anything `adapters.py` does. The check runs in a
  subprocess instead, which is also exactly the form the plan's acceptance criterion specifies.
- **Six mutations, all caught.** Coverage was verified by mutating the shipped modules rather than
  assumed: a destructive `check_all` (4 failures), a partially-charging `charge_all` (3), removing
  the name deduplication (2), giving a Protocol method a body (1), adding a concrete subclass (3),
  and adding a `firebase_admin` import plus a fifth `ProviderDataOutcome` member (4).
  `git diff --exit-code` confirmed both source modules byte-identical to their committed versions
  after every one.
- **Out of scope, unchanged:** the 26 e2e failures are the pre-existing v2.0 schema drift plan 35-05
  repairs. Reproduced exactly, not touched.

## Test Status

| Suite | Result | Note |
|---|---|---|
| Unit (`pytest -q`) | **406 passed**, 119 deselected | 310 baseline + 96 new; zero regressions |
| Schema (`pytest -q -m schema`) | **77 passed** | unchanged |
| E2E (`pytest -q -m e2e`) | 16 passed, **26 failed** | exactly the measured baseline — pre-existing v2.0 schema drift, repaired by plan 35-05 |
| `ruff check src tests` | **All checks passed!** | |
| `ty check src` | **All checks passed!** | |

No `xfail` and no `skip` marker exists in either new file (D-18). No new dependency appears in
`pyproject.toml` or `uv.lock`.

The plan's `<verification>` bullet "`pytest -q -m ""` green" cannot hold at plan 07, for the same
reason it could not at plans 01 and 02: it is the D-18 phase-end bar, and the e2e failures it covers
are plan 35-05's to repair.

## Known Stubs

None — and specifically none in the sense that matters here. `adapters.py` contains eleven method
declarations whose bodies are `...`, which is the plan's deliverable rather than a stub: a stub is
an implementation that pretends to work, and these are declarations that cannot be called at all.
`tests/unit/test_adapter_interfaces.py::TestZeroImplementations` fails if any of them ever acquires
a body in this module, and every one names the phase that owns its implementation.

Nothing was left unwired that this plan's goal required. Both `<verify>` blocks ran in full and both
passed.

## Threat Flags

None. Every file this plan created is covered by the plan's own `<threat_model>`. No network
endpoint, auth path, file-access pattern, or schema change at a trust boundary was introduced —
this plan's whole point is that it introduces no provider dependency at all. The four `mitigate`
dispositions are all implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-07-01 | `charge_all` collects every blocked name before touching any counter and raises with nothing spent; `test_raises_rather_than_partially_charging` and `test_raises_even_when_the_exhausted_name_is_charged_first` cover both orderings, and the mutation that reintroduces partial charging fails three tests |
| T-35-07-02 | `selection_failure` is a declared member of the closed `ProviderDataOutcome` set, and `issuer` is a parameter of both `FirebaseAdminAdapter` lookup methods, so selection is per call and no ambient, default, or global client is expressible through the Protocol |
| T-35-07-03 | `claim_kind: ClaimKind` is a parameter of both `read_device_bit` and `write_device_bit`, asserted by annotation identity; `test_no_non_slot_method_takes_a_claim_kind` fails if the slot surface widens |
| T-35-07-04 | The prohibition is in `VendorProofAdapter.__doc__` in full — no value raw, hashed, transaction-scoped, install-scoped, or otherwise derived may become a rate-limit key component or a synthetic device principal — and `test_the_seam_records_the_no_rate_limit_key_prohibition` fails if it is edited out |
| T-35-07-05 | Accepted per D-05, not mitigated. Recorded, not omitted: v2.0 ships only whatever the v1.6 chart already enforces, unverified against §9 |
| T-35-07-SC | No package was installed; the legitimacy gate stays vacuous for Phase 35 |

The **prohibition** — that the budget seam must not become backend traffic rate limiting — is
carried by `TestNotTrafficLimiting`, whose three assertions are structural rather than aspirational:
a source scan for `limits`/`redis`/`valkey` imports, a module-level mutable-state check, and an
exact-set assertion that the gate's entire public parameter surface is `{self, limits, names, name}`.
Adding an `ip=` or `user_id=` parameter anywhere fails the build.

### The two backstop truths, stated honestly

The plan authored both as `verification: backstop`, and neither is fully confirmable here:

- **Counter integrity under precision and overflow.** Tested single-threaded: `remaining` never
  returns a negative value after ten over-charge attempts, a negative limit clamps to zero, a float
  limit raises, and `type(remaining(...)) is int`. The *overflow* dimension is vacuous rather than
  proven — Python integers are arbitrary precision, so there is no wrap to test.
- **Concurrency.** No concurrency test exists, and none is meaningful: a `BudgetGate` holds one
  private `dict` created per request and shared with nothing, so there is no contention to
  exercise. The truth's claim is that the module asserts no cross-request or cross-process
  guarantee, and the module docstring states that in those words. A verifier should read this as
  "no guarantee is made", not as "a guarantee was tested".

## Next Phase Readiness

Ready. Every interface plans 11 and 36-46 import from this plan exists at its pinned module path:

- `auth.budgets.ADAPTER_FIREBASE_LOOKUP` / `FIREBASE_LOOKUP_ATTEMPTS` / `BudgetGate` / `BudgetExhausted`
- `auth.adapters.ProviderDataOutcome` / `ProviderDataEntry` / `ProviderDataResult` /
  `RevocationOutcome` / `FirebaseAdminAdapter` / `VerifiedNotification` / `VerifiedTransaction` /
  `StoreState` / `StoreAdapter` / `ClaimKind` / `DeviceBitState` / `VendorProofAdapter`

Notes for the plans that follow:

- **This plan does not edit `auth/__init__.py`.** It ran in wave 3 alongside plan 03 and shares no
  file with it. **Plan 11 writes the final barrel** and must add the sixteen symbols above; every
  consumer today uses the full module path, so nothing is broken in the meantime.
- **`test_foundation_calls_no_adapter_method_anywhere_in_src` has a named expiry.** It scans every
  module under `src/nativespeaker/` for all ten adapter method names, which is correct for
  *foundation* and wrong the moment a concrete adapter lands. **Phase 02 is the first phase that
  must narrow or delete it** (it implements `get_user_provider_data`), and phases 06/07/08/09/10/11
  follow. It is not a broken window — it is a phase-scoped invariant with an owner, recorded here so
  the failure is understood rather than debugged.
- **Callers charge, then call.** `charge_all` immediately before the outbound call and again before
  each permitted retry; a `user_not_found` outcome is definitive, spends no retry budget, and
  rejects immediately. `check_all` is free — call it as often as convenient.
- **Exhaustion needs two actions, not one.** Write the `audit.auth_events` row with
  `BudgetExhausted.audit_result` **and** return `BudgetExhausted.error_class`. Letting the exception
  escape produces a 500 and no audit row, which is the loud failure this design chose on purpose
  over a quiet convincing one.
- **`app/lifespan.py` still imports `firebase_admin` at module scope.** That is plan 04's deletion
  under D-16 and is untouched here; `adapters.py` itself is clean, proven in a subprocess. Nothing
  in this plan's seam depends on it either way.
- **`BudgetGate` is not yet constructed anywhere.** Foundation issues no provider call, so nothing
  builds one. Phase 37 is the first plan that needs one on `app.state` or the request context.

## Self-Check: PASSED

All four claimed files exist on disk (`src/nativespeaker/api/auth/budgets.py`,
`src/nativespeaker/api/auth/adapters.py`, `tests/unit/test_budgets.py`,
`tests/unit/test_adapter_interfaces.py`). All four claimed commits — `8bf360e`, `36abf5e`,
`0fca1ed`, `2dd7149` — are present in `git log`. Both source modules are byte-identical to their
committed versions after six mutation runs (`git diff --exit-code` clean).

---
*Phase: 35-foundation*
*Completed: 2026-08-21*
