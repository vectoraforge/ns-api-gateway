---
phase: 37-post-auth-create-user
plan: 05
subsystem: auth
tags: [firebase-admin, adapter, classifier, providerdata, email, lazy-import]
status: complete

# Dependency graph
requires:
  - phase: 35-foundation
    provides: "auth/adapters.py (ProviderDataEntry/ProviderDataOutcome/ProviderDataResult, the FirebaseAdminAdapter Protocol), the auth/ package import root (D-23), tests/unit/test_adapter_interfaces.py's src-wide adapter-method scan and its TestNoProviderDependency subprocess probe, models/identities.IdentityProvider, the run_in_threadpool house rule (35-12)"
  - plan: "37-02"
    provides: "ADAPTER_IMPLEMENTORS (the named, method-scoped allow-list this plan adds its second entry to) and auth/retry.py's result-based tenacity policy, whose predicate this adapter's return-never-raise contract satisfies"
  - plan: "37-03"
    provides: "config.FirebaseConfig.credential_dict() (dict | None, total over the absent state) and JWTConfig.issuer"
provides:
  - "src/nativespeaker/api/auth/firebase.py — build_admin_apps, FirebaseAdminLookup, FIREBASE_HTTP_TIMEOUT_SECONDS"
  - "src/nativespeaker/api/auth/classifier.py — classify_provider_data, email_to_persist"
  - "ProviderDataResult.email / .email_verified — the settled §02 step 10 email carrier"
  - "all five names re-exported from nativespeaker.api.auth (the three Firebase ones lazily)"
affects: [37-06, 37-07, 37-08, 37-10, 40, 41, 42, 46]

actuals:
  tokens: 21073
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "First concrete provider adapter behind the §7.1 seam: issuer-keyed named app, explicit app= on every call, no [DEFAULT] app expressible"
    - "Every lazy SDK property materialized inside the threadpool try, so a lazy-property raise cannot escape onto the event loop"
    - "PEP 562 module-level __getattr__ for re-exporting a provider-dependent submodule from a package root whose freedom from that provider is a tested guarantee"
    - "Closed classifier whose length check precedes any per-entry inspection, making 'never take the first recognized entry' structural"

key-files:
  created:
    - src/nativespeaker/api/auth/firebase.py
    - src/nativespeaker/api/auth/classifier.py
    - tests/unit/test_firebase_adapter.py
    - tests/unit/test_provider_classifier.py
  modified:
    - src/nativespeaker/api/auth/adapters.py
    - src/nativespeaker/api/auth/__init__.py
    - tests/unit/test_adapter_interfaces.py

key-decisions:
  - "Symbol names (Claude's discretion per 37-CONTEXT.md): classify_provider_data, email_to_persist, FirebaseAdminLookup, build_admin_apps, FIREBASE_HTTP_TIMEOUT_SECONDS."
  - "A-37-05-1: FirebaseAdminLookup implements get_user_provider_data alone. The verification method would be unreachable (the barrier's TokenVerifier is the only verification path, D-03); the revocation method is Phase 46's. Handed off, not omitted."
  - "The ProviderDataResult amendment is additive and defaulted, so no pre-existing construction site changed and all four of test_adapter_interfaces.py's foundation assertions still hold."
  - "The three auth/firebase.py re-exports are lazy (PEP 562 __getattr__); the auth/classifier.py ones are eager. Lazy is what lets D-23's one import root coexist with §7.1's no-provider-dependency test."
  - "Three plan acceptance criteria are self-invalidating literal-text greps and were satisfied by intent rather than by literal text — see Deviations 1, 2 and 4."

requirements-completed: [CREATE-03]

# Metrics
duration: ~14 min
completed: 2026-08-22
---

# Phase 37 Plan 05: Firebase Adapter and providerData Classifier Summary

**The codebase's first concrete provider adapter — issuer-selected, `[DEFAULT]`-free, with every lazy SDK read materialized inside the threadpool — plus §02's closed classifier, and the §02 step-10 email contract settled in wave 2 so 37-07 and 37-10 consume it rather than discover it.**

## Performance

- **Started:** 2026-08-22T23:34:26Z
- **Completed:** 2026-08-22T23:47:56Z
- **Duration:** ~14 min
- **Tasks:** 3
- **Files:** 7 (4 created, 3 modified, 0 deleted)
- **Tests:** 1029 → 1037 passing, 0 failing (baseline at this worktree's base commit: 963)

## Task Commits

1. **Task 1: The closed classifier, the email-copy predicate, and the `ProviderDataResult` amendment** — `32f676b` (test, RED) → `e31f182` (feat, GREEN)
2. **Task 2: The concrete issuer-selected Firebase Admin adapter** — `3aea796` (test, RED) → `e31d120` (feat, GREEN)
3. **Task 3: Re-export the new seams from `nativespeaker.api.auth`** — `81412d9` (feat)

No REFACTOR commits: neither GREEN implementation needed cleanup.

## The Names Chosen

37-CONTEXT.md left these to Claude's discretion. Later plans import all five from `nativespeaker.api.auth`.

| Symbol | Module | What it is |
|---|---|---|
| `classify_provider_data(entries) -> tuple[IdentityProvider, str \| None] \| None` | `auth/classifier.py` | §02 step 9's closed classifier. `None` means reject. |
| `email_to_persist(result) -> str \| None` | `auth/classifier.py` | §02 step 10's two-condition copy rule, one evaluation site. |
| `FirebaseAdminLookup` | `auth/firebase.py` | The adapter class. One method: `get_user_provider_data`. |
| `build_admin_apps(config) -> dict[str, firebase_admin.App]` | `auth/firebase.py` | Boot-time app builder, keyed on `jwt.issuer`. |
| `FIREBASE_HTTP_TIMEOUT_SECONDS` | `auth/firebase.py` | `8`, inside `adapters.py:16-17`'s mandated 5-10 s band. |

`FirebaseAdminLookup` rather than `FirebaseAdmin`/`FirebaseAdminAdapter`: it is *a lookup*, not the whole §7.1 adapter, and the name should not claim a Protocol it deliberately does not satisfy.

## The `ProviderDataResult` Amendment — a Phase 35 Foundation Amendment

**37-07 and 37-10 read this section as the settled contract.**

`src/nativespeaker/api/auth/adapters.py`'s `ProviderDataResult` grew exactly two fields, after `entries`:

```python
email: str | None = None
email_verified: bool = False
```

- **Both defaulted, so the amendment is purely additive.** Every pre-existing construction site — `ProviderDataResult(ProviderDataOutcome.selection_failure)` and its siblings in `auth/retry.py` and `tests/unit/test_firebase_retry.py` — still constructs from one positional argument and is byte-for-byte unchanged. A test pins that explicitly.
- **Why on this result type at all.** §02 step 10 pins the copy to "the same successful `getUser` response". An address re-fetched later is a *different* response, so the only shape satisfying that rule is one where the address rides out of the adapter on the object the one `getUser` call produced.
- **Populated on the `ok` arm only**, from the same `UserRecord`, inside the same threadpool `try` that materializes `entries`. Every failure arm leaves both at their defaults.
- **The adapter reports; it does not judge.** An unverified address is returned verbatim with `email_verified=False`; `classifier.email_to_persist` is what turns that pair into `None`.
- **`tests/unit/test_adapter_interfaces.py` stayed green throughout** — 56 passed immediately after the edit and before anything else was written. All four assertions the amendment could have disturbed still hold: zero module-level functions, imports confined to `{dataclasses, datetime, enum, typing, uuid, nativespeaker}`, module body holds only declarations, and every result type is a frozen slotted dataclass.

**The consumer contract:** 37-07's `auth/creation.py` takes an already-resolved `email: str | None` argument and re-derives nothing. 37-10's substituted adapter scripts `ProviderDataResult(outcome=ok, entries=..., email=..., email_verified=...)`. The router calls `email_to_persist(result)` to produce 37-07's argument.

## The Two Phase 35 Test/Module Amendments

### 1. `ADAPTER_IMPLEMENTORS` gains its second and final Phase 37 entry

`tests/unit/test_adapter_interfaces.py`:

```python
ADAPTER_IMPLEMENTORS: dict[str, frozenset[str]] = {
    "api/auth/retry.py": frozenset({"get_user_provider_data"}),
    "api/auth/firebase.py": frozenset({"get_user_provider_data"}),
}
```

**Forced by:** the src-wide scan reports any file under `src/` naming one of the ten adapter methods. `auth/firebase.py` defines `get_user_provider_data`, so the entry and the module had to land in the same commit — `e31d120`. They did. 37-02's entry-scope control reads `next(iter(ADAPTER_IMPLEMENTORS))` rather than a hardcoded path, so it needed no edit; both of 37-02's controls are untouched and passing.

**The both-ways liveness check, run as the plan requires, with observed exit codes:**

| Probe | `pytest -q tests/unit/test_adapter_interfaces.py` exit | Failure message named |
|---|---|---|
| **Half 2** — line naming `get_user_provider_data` appended to `auth/classifier.py` (non-exempt) | **1** | `api/auth/classifier.py: get_user_provider_data` |
| **Half 2** — reverted (restored byte-for-byte; `git diff --quiet` clean) | **0** | — |
| **Half 2b** — line naming the revocation method appended to `auth/firebase.py` (exempt for one method) | **1** | `api/auth/firebase.py: revoke_refresh_tokens` |
| **Half 2b** — reverted | **0** | — |

The exemption is method-scoped, not a blanket-exempt file. `pytest -k "control"` selects 2 tests, both passing. `ADAPTER_IMPLEMENTORS` has exactly 2 entries; the second resolves to a file that exists and its value has exactly 1 member.

**Phase 46 note:** adding `revoke_refresh_tokens` to `auth/firebase.py` requires widening that module's one-method entry **deliberately**. The scan reports it first — that is the whole point of the one-method entry, and Half 2b above is the proof it does.

### 2. `auth/__init__.py` reaches `auth/firebase.py` through a PEP 562 `__getattr__`

**Forced by:** `TestNoProviderDependency.test_importing_the_module_does_not_import_firebase_admin` runs a subprocess that imports `nativespeaker.api.auth.adapters` and asserts `firebase_admin` is absent from `sys.modules`. Python imports the parent package first, and `auth/__init__.py` imports all its siblings eagerly, so an ordinary `from nativespeaker.api.auth.firebase import ...` line would have flipped that test from passing to failing.

**The `sys.modules` probe, run before and after the edit as the plan requires:**

| When | `import sys, nativespeaker.api.auth.adapters; 'firebase_admin' in sys.modules` |
|---|---|
| Before the `__init__.py` edit | `False` |
| After the `__init__.py` edit | `False` |

Same answer, which is the point. Additionally observed in-process: `firebase_admin` is absent from `sys.modules` after `import nativespeaker.api.auth`, and present only once a caller names one of the three lazy attributes.

The implementation is a private `_LAZY_NAMES` mapping of the three names to `nativespeaker.api.auth.firebase`, a `__getattr__` that resolves through `importlib.import_module` and caches into `globals()`, an `AttributeError` for anything outside the mapping, a `__dir__` returning `sorted(__all__)`, and a `if TYPE_CHECKING:` import block for static resolution. `auth/classifier.py`'s two names are re-exported **eagerly** — that module imports only `auth/adapters.py` and `models/identities.py` and drags in nothing new.

Verified as a genuine re-export, not a copy: `nativespeaker.api.auth.build_admin_apps is nativespeaker.api.auth.firebase.build_admin_apps` → `True`, for all three names. Four regression tests in `test_firebase_adapter.py` now pin this permanently rather than leaving it a one-time observation.

## Flagged Assumption A-37-05-1 — the two non-implemented Protocol methods

`FirebaseAdminAdapter` declares three methods; `FirebaseAdminLookup` implements one. **This diverges from RESEARCH open question 3's recommendation**, on D-03's precedent (an unreachable structure is a defect, not completeness):

- **The token-verification method is not implemented.** The barrier's JWKS-backed `TokenVerifier` (`auth/verification.py`) is the service's only verification path and §02's hardenings forbid a handler re-implementing verification. An implementation here would be unreachable.
- **The refresh-token revocation method is not implemented.** §7.1 assigns the revocation adapter, its retry budget and any in-flight coalescing to **Phase 46** (`sign-out-all`). Building it here would be building another phase's adapter.

The Protocol is structural and not `@runtime_checkable`, so nothing breaks at runtime, and the class is deliberately **not** annotated as `FirebaseAdminAdapter` anywhere. Two tests pin both absences by name, and one pins that the Protocol is not in the class's MRO.

**Phase 46 handoff:** implement the revocation method on `FirebaseAdminLookup` (or a sibling class), widen the `api/auth/firebase.py` `ADAPTER_IMPLEMENTORS` entry to `frozenset({"get_user_provider_data", "revoke_refresh_tokens"})`, express the retry with `auth/retry.py`'s tenacity idiom rather than a second hand-rolled loop, and update `test_firebase_adapter.py::TestTheDeliberateNonImplementations`.

## RESEARCH A5 — did `httpTimeout` bound an observed `get_user` call?

**No real call was observed, and this is recorded as unmeasured rather than as confirmed.** Every test monkeypatches `firebase_admin.auth.get_user`; the suite runs with no credential, no app, and no network, which is a deliberate property of the plan and not a shortcut.

What *was* verified, statically against the installed `firebase-admin` 7.3.0:

- `httpTimeout` is a recognized app option — `firebase_admin/__init__.py:33` lists it in `_CONFIG_VALID_KEYS`, so a typo would have raised at `initialize_app`.
- The auth client consumes it: `firebase_admin/_auth_client.py:42` reads `app.options.get('httpTimeout', _http_client.DEFAULT_TIMEOUT_SECONDS)` and hands it to the HTTP client that serves `get_user`. That is the code path, read in the installed source rather than in the docs.
- A unit test pins `5 <= FIREBASE_HTTP_TIMEOUT_SECONDS <= 10`, so the value cannot drift out of `adapters.py:16-17`'s mandated band.

**Still open, unchanged from RESEARCH A5:** whether the option actually bounds a *slow* upstream in practice. A slow test against a real project remains the detector. Carry this into whichever phase first exercises the adapter against real Firebase (37-10's e2e work is the earliest candidate).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 2's `initialize_app()` acceptance grep is self-invalidating against the docstring the same task mandates**

- **Found during:** Task 2
- **Issue:** The action requires the module to record the ADC anti-pattern ("Never call `firebase_admin.initialize_app()` with no credential"), while an acceptance criterion requires `grep -n "initialize_app()" src/nativespeaker/api/auth/firebase.py` to return **no match**. Recording the prohibition in the obvious words puts the forbidden literal in the file. Observed: the grep returned 1, on the docstring line.
- **Fix:** Rephrased to "Calling `firebase_admin.initialize_app` with no credential argument…" — the prohibition is recorded in full, and the criterion's *intent* (no argument-less call in code) now holds literally as well.
- **Verification:** `grep -c "initialize_app()" …/firebase.py` → **0**. The single `initialize_app` call passes an explicit `credentials.Certificate`, an options dict, and `name=`.
- **Committed in:** `e31d120`

**2. [Rule 1 - Bug] The same conflict in Task 2, but load-bearing: the module docstring made the src-wide scan fire**

- **Found during:** Task 2 — caught by the scan itself, which failed with `api/auth/firebase.py: revoke_refresh_tokens` and `: verify_id_token`.
- **Issue:** The action mandates recording *why* the other two Protocol methods are not implemented, and the natural phrasing names them. The scan is a substring check over the file text, so a docstring mention is an offence — and the plan forbids widening the entry ("Add nothing else — not the revocation method, not the verification method"). The two requirements cannot both hold in literal text.
- **Fix:** Kept the entry at one method (the load-bearing requirement, and the one Half 2b proves) and rewrote the docstring to describe both omissions without the literal identifiers — "the token-verification method", "the refresh-token revocation method" — with a pointer to where they *are* spelled. The decision is recorded in full in the module, in `test_firebase_adapter.py` (which the scan does not read, since it walks `src/` only), and in this SUMMARY.
- **Verification:** `pytest -q tests/unit/test_adapter_interfaces.py` → 56 passed; the entry still names one method; Half 2b still fails on a tampered `firebase.py`.
- **Committed in:** `e31d120`

**3. [Rule 3 - Blocking] The worktree had no `.venv`**

- **Found during:** setup
- **Issue:** Every `<verify>` invokes `.venv/bin/python` / `.venv/bin/pytest`, and a fresh worktree carries no virtualenv (`.venv/` is gitignored). Same blocker 37-02 hit.
- **Fix:** `uv sync`.
- **Verification:** Baseline `pytest -q` → 963 passed, 0 failed.
- **Committed in:** n/a (gitignored)

### Criteria satisfied by intent, with the literal check recorded as unsatisfiable

**4. Three acceptance greps could not hold as literal text; each was verified structurally instead.** Following 37-02's precedent (its deviation 3), the load-bearing requirement was honoured and the criterion's intent verified with a stronger check.

| Criterion | Literal result | Why | How the intent was verified |
|---|---|---|---|
| `grep -c "sign_in_provider" …/classifier.py` returns 0 | **1** | The same task mandates a docstring recording "never read `firebase.sign_in_provider`" | AST check: strip the module docstring, and the identifier appears nowhere in the remaining source. Pinned as a test. |
| `grep -c "required_flow" …/classifier.py` returns 0 | **2** | The same task mandates recording, citing D-12, that no `required_flow` is derived | Same AST check, same test. |
| `grep -vE '^[[:space:]]*#' …/adapters.py \| grep -cE '^[[:space:]]*(async )?def '` returns 0 | **10** | **Pre-existing**: the regex matches indented Protocol method declarations. The count is 10 at this worktree's base commit `72e3433` and 10 after the amendment — unchanged | AST: module-level function names in `adapters.py` are `[]`, and `test_the_module_declares_no_function_at_all` passes. The amendment added no function. |

**5. Task 3's `__all__` sort criterion names the wrong sort order.** The plan's verify asserts `a.__all__ == sorted(a.__all__, key=str.lower)`. The file's actual, pre-existing invariant — stated in its docstring, established by `models/__init__.py`, and preserved by 37-02 — is plain ASCII sort. Measured at base: plain-ASCII-sorted `True`, case-insensitive-sorted `False` (`"CHALLENGE_TTL_SECONDS"` precedes `"Category"`, which case-insensitive sorting reverses). Adopting `key=str.lower` would have required reordering ~15 unrelated pre-existing entries for no benefit. **Kept plain ASCII sort**; verified `a.__all__ == sorted(a.__all__)` → `True`.

### Scope additions (tests beyond the listed behaviors)

- **`TestTheLazyReExport` (4 tests, `test_firebase_adapter.py`).** Task 3's plan verification is inline `python -c` only, which proves the property once at execution time and never again. The re-export-not-a-copy identity, `__all__` membership, the `AttributeError` for unmapped names, and `__dir__` coverage are now permanent regressions.
- **`test_user_not_found_is_not_swallowed_by_the_firebase_error_arm`.** `auth.UserNotFoundError` **subclasses** `exceptions.FirebaseError`, so reordering the two `except` arms would silently reclassify a definitive rejection as retryable — burning two attempts and returning a 503 where §02 earns a 401. Invisible in review, red here.
- **`test_an_absent_credential_does_not_raise_and_does_not_initialize_anything`.** Asserts via an exploding `initialize_app` monkeypatch that the absent-credential arm is not merely `[DEFAULT]`-free but never reaches initialization at all.
- **`test_the_per_attempt_timeout_sits_inside_the_mandated_band`** and **`test_the_recognized_provider_map_has_exactly_two_keys`.** Both pin closed sets the plan states in prose.
- **`test_a_non_ok_outcome_yields_none_even_if_the_fields_were_somehow_populated`.** The plan's cases prove `None` on a failure arm via the *defaults*; this proves the outcome gate is actually checked, so a future adapter bug that populates the fields on a failure arm cannot leak an address into `core.users`.

## must_haves verification

| Truth | Result |
|---|---|
| The concrete adapter lives outside `auth/adapters.py` and `test_adapter_interfaces.py` stays green | PASS (56 passed) |
| `auth/firebase.py` is admitted by the named, method-scoped allow-list — `get_user_provider_data` and nothing else — and the scan still reports any non-exempt file | PASS (Half 2 exit 1→0; Half 2b exit 1→0) |
| Importing `nativespeaker.api.auth.adapters` still leaves `firebase_admin` out of `sys.modules` after the re-export | PASS (`False` before and after) |
| No `[DEFAULT]` app is ever created; every call passes `app=` explicitly | PASS (one `auth.get_user(` call, `app=app`; `_DEFAULT_APP_NAME not in firebase_admin._apps`) |
| An issuer with no configured app returns `selection_failure` and issues no network call | PASS (call list asserted empty, for both a wrong issuer and an empty mapping) |
| `provider_data` is materialized into `ProviderDataEntry` tuples INSIDE the threadpool call | PASS (lazy-raising stub yields `retryable_failure`; nothing escapes) |
| `UserNotFoundError` → `user_not_found`; `ValueError` and `FirebaseError` → `retryable_failure`; no provider text attached | PASS (incl. the subclass-ordering case and a `repr` scan of every failure result) |
| The classifier returns anonymous / google / apple for the three shapes and rejects every other | PASS (3 accept cases, 9 reject cases) |
| Classifier rejection is order-independent and never takes the first recognized entry | PASS (both orderings, three pairs; the length check precedes any per-entry read) |
| A google or apple entry with an empty uid is rejected rather than persisted | PASS (both providers) |
| `ProviderDataResult` carries `email` and `email_verified`, both defaulted, populated only on `ok` from the same `UserRecord` | PASS |
| `email_to_persist` returns the address only when non-empty AND verified, and `None` otherwise including every non-`ok` outcome | PASS (7 cases + the verbatim-return case) |
| Every pre-existing `ProviderDataResult` construction site still type-checks and runs unchanged | PASS (full suite green; one-positional-argument case pinned) |

## Verification Commands Run

| Command | Result |
|---|---|
| `.venv/bin/pytest -q` | **1037 passed**, 302 deselected, 0 failed |
| `.venv/bin/pytest -q tests/unit/test_adapter_interfaces.py` | 56 passed |
| `.venv/bin/pytest -q tests/unit/test_adapter_interfaces.py -k control` | 2 selected, 2 passed |
| `.venv/bin/ruff check src/ tests/` | All checks passed |
| `.venv/bin/python -c "import nativespeaker.api.app.main"` | exit 0 |
| `grep -c "firebase_admin" …/auth/adapters.py` | 1 — **pre-existing**, and it is the docstring phrase "not one `firebase_admin` import". Count is 1 at base `72e3433` and 1 now; there is no import. |

## Known Stubs

None. No stub values, placeholder text, skipped tests, or unrun `<verify>` commands. The one genuinely unmeasured item — whether `httpTimeout` bounds a real slow `get_user` — is recorded above as an open RESEARCH A5 observation rather than as a stub, because nothing in this plan can measure it without a live credential.

## User Setup Required

None for this plan. `FIREBASE_SERVICE_ACCOUNT_JSON` remains unset and that is a supported state (37-03): the service boots, `build_admin_apps` returns `{}` with a warning naming the consequence, and a real completion fails closed as `verification_temporarily_unavailable` until the credential is set.

## Next Phase Readiness

- **37-07 (`auth/creation.py`)** takes an already-resolved `email: str | None` and re-derives nothing. The router calls `email_to_persist(result)` to produce it. The classifier's `(provider, provider_uid)` pair is the sole source of both persisted columns, and `provider_uid` is `None` exactly for `anonymous`.
- **37-10 (substituted adapter / e2e)** scripts `ProviderDataResult(outcome=..., entries=..., email=..., email_verified=...)`. All four fields exist and are defaulted.
- **37-08 / whichever plan wires the lifespan** calls `build_admin_apps(config)` once at boot and hands the mapping to `FirebaseAdminLookup(apps)`. `get_user_provider_data` is `async` and returns rather than raises, which is exactly what `auth/retry.py`'s `AsyncRetrying` + `retry_if_result` policy needs — 37-02 deliberately left `lookup_with_retry`'s `adapter` parameter unannotated for this reason, and that choice is now vindicated: the concrete method is `async` while the Protocol declares it sync.
- **Phase 46** — see the A-37-05-1 handoff above.
- **`ADAPTER_IMPLEMENTORS` is now complete for Phase 37.** Two entries, one method each. No later plan in this phase should add a third.

## Self-Check: PASSED

- Created files exist: `src/nativespeaker/api/auth/firebase.py`, `src/nativespeaker/api/auth/classifier.py`, `tests/unit/test_firebase_adapter.py`, `tests/unit/test_provider_classifier.py`.
- All five task commits present in `git log 72e3433..HEAD`: `32f676b`, `e31f182`, `3aea796`, `e31d120`, `81412d9`.
- `git diff --diff-filter=D --name-only 72e3433..HEAD` → empty. **No file was deleted by this plan.**
- `git diff 72e3433..HEAD --name-only -- .planning/STATE.md .planning/ROADMAP.md` → empty. Both untouched, as the parallel-execution contract requires.
- TDD gate sequence intact for both TDD tasks: `test(37-05)` precedes `feat(37-05)` in each pair.
- Every file written is under `git rev-parse --show-toplevel`; no path escaped the worktree.

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-22*
