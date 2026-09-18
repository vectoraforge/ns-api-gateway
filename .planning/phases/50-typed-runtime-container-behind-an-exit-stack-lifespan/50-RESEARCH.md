# Phase 50: Typed runtime container behind an exit-stack lifespan - Research

**Researched:** 2026-09-17
**Domain:** FastAPI application wiring — `contextlib.AsyncExitStack` lifespan, a frozen slotted dataclass on `app.state`, and a boot-rule change
**Confidence:** HIGH — every claim below was measured in this session against this tree

## Summary

This phase adds no library. Everything it needs — `contextlib.AsyncExitStack`, `dataclasses.replace`,
`frozen=True, slots=True` — is in the standard library of the Python this project already runs
(3.14.7 `[VERIFIED: .venv/bin/python]`). The work is a rewrite of two files plus the test pass that
follows from the type change, so the risk is not "will the API work" but "which of the 30-odd call
sites moved, and what did the move break".

Three findings change what the plan must contain. **First, criterion 7 is red before this phase
starts**, and not because of this phase: `-m e2e` reads 1 failed / 360 passed at HEAD, the same
Phase-47 restore case STATE.md records. **Second, `tests/unit/test_auth_package_shape.py::CURRENT`
WILL change**, against the CONTEXT "Carried forward" note that says it will not — the literal counts
classes and functions, not files, and D-09 removes a class and D-10 removes functions. **Third,
`AsyncExitStack`'s teardown semantics are exactly what criterion 3 assumes**, proved by a probe run
here rather than read from memory.

**Primary recommendation:** Land the merge and the boot rule (D-08, D-09, D-10) first, in
`auth/google_play.py` plus the four builders, and re-measure `CURRENT` in that same commit. Then land
the exit stack. Then land the container type, which breaks every call site at once and is therefore
the one wave that must be atomic. Fix the pre-existing e2e case in its own commit so criterion 7 can
read green without hiding a debt that is not this phase's.

## User Constraints (from CONTEXT.md)

Full text: `.planning/phases/50-typed-runtime-container-behind-an-exit-stack-lifespan/50-CONTEXT.md`.
The locked decisions, by their titles:

### Locked Decisions

- **D-01: The module is `app/runtime.py`, the class is `Runtime`, the attribute is `app.state.runtime`.**
- **D-02: `Runtime` has eight fields, declared in build order.**
- **D-03: `get_config` is deleted.**
- **D-04: `session_factory` is annotated `async_sessionmaker[SQLModelAsyncSession]`.**
- **D-05: `sign_out_all` declares `get_runtime` and reads `runtime.firebase_adapter`.**
- **D-06: Each builder is named after the `Runtime` field it fills.**
- **D-07: `build_firebase_adapter` and `build_admin_apps` both take a `JWTConfig`.**
- **D-08: A warm-up that fails at boot stops the pod.**
- **D-09: `PubSubPushTokens` and `PlayDeveloperSubscriptions` merge into one class `GooglePlayNotifications`.**
- **D-10: The rebuild code is deleted.**
- **D-11: The Phase 50 entry in `ROADMAP.md` is amended in the discuss commit.** Already applied
  `[VERIFIED: .planning/ROADMAP.md:901-916]` — criterion 5 names `sign_out_all`, criterion 8 exists.

Carried forward: 48 D-10 and 49 (ASD-STE100 comments, one line, only where needed); 49 D-06
(adapter annotations stand); 49 D-08 (the `auth/` shape tuple) — **see Pitfall 2, this one is wrong**.

### Claude's Discretion

How the six unit files that override a deleted getter and the nine that set `app.state` build a
`Runtime` from fakes (shared helper in `tests/unit/conftest.py`, or per file); whether the seven e2e
fixtures share one `dataclasses.replace` helper or copy it; whether a wiring test pins criterion 5's
route clause; whether `Runtime` and `get_runtime` carry docstrings; commit granularity and wave order.

### Deferred Ideas (OUT OF SCOPE)

Moving the two pending todos out of `.planning/todos/pending/`. Both reviewed todos
(`secret-manager-integration`, `message-ordering-is-unspecified`) are not folded.

## Project Constraints (from AGENTS.md)

`[VERIFIED: AGENTS.md:1-40]`, read this session:

- Docstrings — three lines maximum, plain English, state what it does and nothing else.
- Comments — one line maximum, only where absolutely necessary, prefer inline.
- Do not write functions that are only one step (this is what deletes `get_config`).
- Multiline argument style: function definitions one argument per line aligned under the opening
  delimiter; calls collapse into one or more lines.
- Do not use string-based module references in Python tests.
- Keep specs short: programming this app should not consume many tokens.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Process-scoped resource ownership and teardown | `app/lifespan.py` | — | It is the only code with the `FastAPI` instance and the shutdown edge |
| The typed shape of what boot produced | `app/runtime.py` | — | A data declaration, no behaviour; not `services/`, which is request-scoped |
| Reading one field off that shape per request | `app/dependencies.py` | — | FastAPI caches a dependency per request, so one read serves every consumer |
| Verifying a store credential | `auth/` | — | `GooglePlayNotifications` keeps its own refusals; the lifespan only constructs it |
| Boot-fatal vs absent-configuration classification | `app/lifespan.py` builders | `auth/firebase.py` | D-08 puts the raise in the builder, so the pod dies before it serves |

## Standard Stack

No package is added or upgraded. Everything the phase uses is already installed.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `contextlib` (stdlib) | Python 3.14.7 | `AsyncExitStack` owns every teardown | `[VERIFIED: .venv/bin/python — AsyncExitStack exposes aclose, callback, enter_async_context, enter_context, pop_all, push, push_async_callback, push_async_exit]` |
| `dataclasses` (stdlib) | Python 3.14.7 | `Runtime` and `dataclasses.replace` | `[VERIFIED: probe run this session]` |
| fastapi | 0.135.1 | `Depends(get_runtime)`, lifespan protocol | `[VERIFIED: .venv/bin/python -c "import fastapi"]` |
| sqlalchemy | 2.0.46 | `async_sessionmaker[SQLModelAsyncSession]` is generic | `[VERIFIED: .venv/bin/python -c "import sqlalchemy"]` |
| httpx | installed | `AsyncClient` is an async context manager | `[VERIFIED: hasattr(httpx.AsyncClient, "__aenter__") is True]` |

**Installation:** none. `uv.lock` is not touched.

## Package Legitimacy Audit

Not applicable: this phase installs no external package. No entry to audit, nothing removed,
nothing flagged.

## Architecture Patterns

### System Architecture Diagram

```
EnvironmentConfig ──> config ──┐
                               │
  ┌────────────────────────────┴──────────────────────────────┐
  │  lifespan()  —  one AsyncExitStack, entered once          │
  │                                                            │
  │  stack.callback(logger.info, "shutdown")   registered 1st, runs LAST
  │                                                            │
  │  build_db_engine ─> push_async_callback(engine.dispose) ─> _prove_database_reachable
  │        └─> build_session_factory ──────────────────> session_factory
  │  build_jwt_verifier  ───(raises RuntimeError)─────> jwt_verifier
  │        ▲ the two boot-fatal steps run FIRST
  │                                                            │
  │  build_firebase_adapter(jwt, stack) ──> stack.callback(delete_app, app) per app
  │  build_devicecheck_adapter(cfg, stack) ─> enter_async_context(httpx.AsyncClient)
  │  build_app_store_notifications(cfg)                        │
  │  build_google_play_notifications(cfg, stack) ─> enter_async_context(httpx.AsyncClient)
  │                                                            │
  │  app.state.runtime = Runtime(<8 locals, top to bottom>)    │
  │  yield  ───────────────────────────────────────────────────┤
  └────────────────────────────────────────────────────────────┘
                               │
 request ──> get_runtime(request) -> request.app.state.runtime   (the ONE untyped read)
                               │
      ┌────────────────────────┼─────────────────────────┬──────────────────┐
  get_db                  get_claims              get_chat_service    verify_google_play_notification
  runtime.session_factory runtime.jwt_verifier    runtime.llm_service runtime.google_play_notifications
                          (+ keeps Request for     runtime.config      runtime.config
                           the header read)
```

### Pattern 1: the stack registers teardown at the moment of creation

```python
# Source: probe run in this session; contextlib.AsyncExitStack, Python 3.14.7
async with AsyncExitStack() as stack:
    stack.callback(logger.info, "shutdown")            # first in, last out
    engine = build_db_engine(config.db)
    stack.push_async_callback(engine.dispose)           # BEFORE the probe, per criterion 1
    await _prove_database_reachable(engine, config.db)
    client = await stack.enter_async_context(httpx.AsyncClient(timeout=...))
    ...
    app.state.runtime = Runtime(...)
    yield
```

`enter_async_context` for anything with `__aenter__`; `push_async_callback` for a bare coroutine
function such as `AsyncEngine.dispose`; `callback` for a plain function such as
`firebase_admin.delete_app`.

### Pattern 2: `Runtime`, following `LinkedIdentity`

```python
# Source: src/nativespeaker/api/schemas/auth.py:105-110, read this session
@dataclass(frozen=True, slots=True)
class LinkedIdentity:
    """The account a verified credential resolved to: the user row and the identity row."""
    user: User
    identity: ExternalIdentity
```

`Runtime` takes the same two decorator arguments and the same one-field-per-line body, with the
eight D-02 fields in build order.

### Pattern 3: an e2e fixture swaps one field

```python
# Source: this session's reading of tests/e2e/conftest.py:277-398, rewritten for the container
@pytest.fixture
def scripted_firebase_adapter(_app_lifespan):
    original = _app_lifespan.state.runtime.firebase_adapter
    adapter = FakeFirebaseAdapter()
    _app_lifespan.state.runtime = replace(_app_lifespan.state.runtime, firebase_adapter=adapter)
    try:
        yield adapter
    finally:
        _app_lifespan.state.runtime = replace(_app_lifespan.state.runtime,
                                              firebase_adapter=original)
```

Save and restore **the field**, never the whole container — see Pitfall 3.

### Anti-Patterns to Avoid

- **Giving `Runtime` fields defaults so tests can build a partial one.** Every field would become
  `X | None` and the type stops carrying the fact that boot produced all eight. Build a test helper
  instead; that is the discretion area CONTEXT names.
- **Deleting `Request` from `get_claims`.** It reads `request.headers.get("authorization")` at
  `dependencies.py:63`, which is not an `app.state` read. Criterion 5 forbids taking `Request` *to
  reach `app.state`*, and this one does not.
- **Passing a value and a function that makes it to one constructor.** CONTEXT records the user
  rejected this; it is exactly what D-10 deletes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Ordered teardown with per-step error isolation | A list of `try/except` blocks | `AsyncExitStack` | It already runs every remaining callback after one raises, and propagates — measured below |
| Replacing one field of a frozen container | A mutable mirror class for tests | `dataclasses.replace` | Keeps the production type in the test, so a renamed field fails the test |
| Re-fetching a credential after a failed boot | A lock plus an interval plus a `build` callable | Fail the boot (D-08) | Kubernetes restarts the pod; that is the retry |

**Key insight:** the rebuild machinery D-10 deletes is a hand-rolled supervisor inside a process that
already has one.

## Common Pitfalls

### Pitfall 1: criterion 7 is red at HEAD, and not because of this phase
**What goes wrong:** the plan claims criterion 7 and the gate reads `1 failed`.
**Measured this session, not copied:**

```
.venv/bin/pytest -q          -> 1906 passed, 658 deselected           exit 0
.venv/bin/pytest -q -m schema-> 297 passed, 2267 deselected           exit 0
.venv/bin/pytest -q -m e2e   -> 1 failed, 360 passed, 2203 deselected exit 1
.venv/bin/ruff check src tests -> All checks passed!                  exit 0
.venv/bin/ty check           -> Found 295 diagnostics
```

The one failure is `tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`,
and its assertion output is:

```
At index 0 diff: ('purchase_proof_rejected', 'VERIFICATION_FAILURE') != ('proof_rejected', 'VERIFICATION_FAILURE')
```

`[VERIFIED: pytest run this session]` The log event name comes from the class name
`PurchaseProofRejected`; the case asserts the `code` attribute `proof_rejected`. This is the same
root cause STATE.md records for Phase 47.
**How to avoid:** give it its own task and its own commit, so the record shows the debt was Phase
47's and the fix was Phase 50's.

### Pitfall 2: `CURRENT` in `test_auth_package_shape.py` WILL change
**What goes wrong:** CONTEXT "Carried forward" says the tuple does not change because no file is
added or removed. The tuple is not a file count.

```python
# Source: tests/unit/test_auth_package_shape.py:12-26, read this session
# What it measures now: modules, classes, functions.
CURRENT = (7, 19, 60)
```

and `_measure` walks the AST, so **every method and nested helper counts**
`[VERIFIED: tests/unit/test_auth_package_shape.py:12-26]`. `auth/google_play.py` today defines
8 classes `[VERIFIED: ast walk run this session — PlayExternalAccountIdentifiers,
PlaySubscriptionLineItem, PlaySubscription, SubscriptionNotification, DeveloperNotification,
PubSubPushTokens, CappedRefreshRequest, PlayDeveloperSubscriptions]` and 16 functions. D-09 merges
two classes into one and D-10 deletes `_credential_in_hand` and one `__init__`, so both the class
count and the function count move; the module count stays 7, because `app/runtime.py` is not in
`auth/`.
**How to avoid:** follow Phase 49 D-08 — write the **re-measured** tuple, read off the failing run's
own text, in the same commit as the merge. Do not compute it by arithmetic.

### Pitfall 3: composing e2e fixtures by restoring the whole container
**What goes wrong:** `scripted_google_play` depends on `scripted_play_subscriptions`
`[VERIFIED: tests/e2e/conftest.py:527-545]`, and `_db_transaction` is `autouse` and swaps the session
factory around every test `[VERIFIED: tests/e2e/conftest.py:252-274]`. If a fixture saves the whole
`Runtime` and restores that object on teardown, it silently reverts the swap of any fixture that ran
inside it.
**How to avoid:** save the field value, `replace` the field on the way in, `replace` it back on the
way out. Each `replace` reads the then-current container, so the nesting composes in any order.

### Pitfall 4: `DefaultCredentialsError` is a subclass of `GoogleAuthError`
**What goes wrong:** D-08 says return `None` only on `DefaultCredentialsError` and raise on
`GoogleAuthError`. Write the two `except` clauses in the wrong order and the raise is unreachable.

```
DefaultCredentialsError MRO: ['DefaultCredentialsError', 'GoogleAuthError', 'Exception', 'BaseException', 'object']
```

`[VERIFIED: .venv/bin/python -c "import google.auth.exceptions" this session]` `_play_credential` at
`lifespan.py:136-149` already has the narrow arm first; `_application_default_credential` at
`firebase.py:52-59` catches only `GoogleAuthError` and must be narrowed to
`DefaultCredentialsError`.

### Pitfall 5: `get_session_factory` is deleted, so `get_quota_service` must change too
**What goes wrong:** criterion 5 names four getters to delete, and the CONTEXT decision section only
discusses `get_config`. `get_quota_service` declares
`session_factory: async_sessionmaker = Depends(get_session_factory)`
`[VERIFIED: src/nativespeaker/api/app/dependencies.py:93]`, so it needs a `runtime` parameter.

### Pitfall 6: a frozen slotted dataclass raises `FrozenInstanceError`, not `AttributeError`
Setting an unknown attribute on the instance raises `FrozenInstanceError` too, because frozen
`__setattr__` runs before the slots check `[VERIFIED: probe run this session]`. A test that expects
`AttributeError` from a typo will not see one.

## Code Examples

### The exit stack's teardown order and error behaviour, measured

```python
# Source: probe run in this session against Python 3.14.7
async with AsyncExitStack() as stack:
    stack.callback(order.append, "shutdown_log")     # registered first
    async def boom(): order.append("boom"); raise RuntimeError("teardown failed")
    stack.push_async_callback(boom)
    stack.callback(order.append, "firebase_delete")  # registered last
```

Result: `['firebase_delete', 'boom', 'shutdown_log', 'propagated:RuntimeError']`

That is criterion 1 and criterion 3 in one line of output: LIFO, the first-registered log runs last,
a raising callback does not stop the ones still queued, and the exception propagates afterwards.
`shutdown_step_failed` has nothing left to do.

### The call sites the container change touches

`app.state` writes, all in the lifespan: `lifespan.py:157, 168, 178, 191, 210, 213, 221, 224, 226`.
`app.state` reads in `dependencies.py`: lines `41, 46, 69, 81, 90, 104, 113, 118, 142, 143, 144,
151, 163, 173, 179` `[VERIFIED: grep over src this session]`. After the rewrite these functions stop
taking `Request` entirely: `get_db`, `get_chat_service`, `get_restore_service`,
`verify_app_store_notification`, `verify_google_play_notification`, `get_identity`. `get_claims`
keeps it, for the header.

Outside `dependencies.py`, exactly one route reads a lifespan object:
`routers/auth.py:208` `adapter: FirebaseAdminLookup = Depends(get_firebase_adapter)`
`[VERIFIED: src/nativespeaker/api/routers/auth.py:206-213]`.

### The test surface, counted

| Kind | Files | Evidence |
|------|-------|----------|
| Sets a lifespan-built `app.state` attribute | `test_app_wiring.py:245-246`, `test_identity_accessors.py:119-122, 226`, `test_jwks_offload.py:109-110`, `test_auth_security.py:43-44`, `test_create_user_precedence.py:173`, `test_claim_precedence.py:266`, `test_claim_precedence_registered.py:146`, `test_exception_handlers.py:288`, `tests/e2e/conftest.py` (7 fixtures) | `[VERIFIED: grep -rn "app\.state" tests/]` |
| Keeps `app.state.opened_sessions` | `test_identity_accessors.py:121, 158, 294, 306` | same grep |
| Overrides a deleted getter | `test_create_user_body.py:106-108`, `test_create_user_precedence.py:174-176`, `test_claim_precedence.py:267-268`, `test_claim_precedence_registered.py:147-148`, `test_upgrade_precedence.py:172-174`, `test_challenge_endpoint.py:134` | `[VERIFIED: grep -rn over tests/]` |
| Imports a builder by name | `test_config.py:20-27` imports `_DB_POOL_RECYCLE_SECONDS`, `_play_credential`, `_prove_database_reachable`, `build_app_store_verifier`, `build_db_engine`, `build_jwt_verifier`; `test_google_play_notifications.py:23` imports `build_google_push_verifier` | `[VERIFIED: read this session]` |
| Builds a `SimpleNamespace` request stub | `test_google_play_notifications.py:317-323` `_stub_request` — becomes a `Runtime` | `[VERIFIED: read this session]` |
| Asserts the old boot rule | `test_google_play_notifications.py:1075, 1090` assert `build_google_push_verifier(...) is None`; `TestAWarmUpFailureIsRetriedRatherThanCachedForThePodsLife` at 1118+ | `[VERIFIED: read this session]` |

Note `tests/unit/test_create_user_precedence.py:173` sets `app.state.session_factory = lambda: session`
— a lambda, not an `async_sessionmaker`. The container is a dataclass and validates nothing at
runtime, so this keeps working; `ty` may add a diagnostic. See Validation Architecture.

## Runtime State Inventory

This is a refactor of in-process wiring. No stored data, no live service configuration and no
OS-registered state carries any name this phase changes.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no database column, enum or row value is renamed; the migration set is untouched | none |
| Live service config | None — no Envoy route, no Helm value and no k8s manifest names `app.state` or a getter | none |
| OS-registered state | None — the pod is the only registration, and it is rebuilt from the image | none |
| Secrets/env vars | None — `EnvironmentConfig` keys are unchanged; D-07 passes an existing config block to a builder, it renames no setting | none |
| Build artifacts | `src/nativespeaker/api/app/__pycache__/` holds compiled `lifespan`/`dependencies`; the package is installed from `src/` and no module is renamed, only added (`app/runtime.py`) | none — no reinstall |

**One behaviour change reaches production:** D-08 turns four degraded-mode returns into a boot
failure. A cluster whose Google metadata server or whose JWKS endpoint is briefly unreachable at pod
start now gets `CrashLoopBackOff` instead of a pod serving 503 on two routes. That is the intent,
and it should be stated in the summary so the operator is not surprised.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python + `.venv` | every suite | ✓ | 3.14.7 | — |
| pytest | criterion 7 | ✓ | `asyncio_mode = "auto"`, markers `e2e`, `schema`, `timing` `[VERIFIED: pyproject.toml:65-76]` | — |
| Live PostgreSQL | `-m schema`, `-m e2e` | ✓ | reachable — 297 schema and 361 e2e cases ran this session | — |
| `pg_isready` binary | nothing | ✗ | — | irrelevant; the suites connect through SQLAlchemy |
| ruff | lint gate | ✓ | `line-length = 120`, `target-version = "py314"`, select `E W F I UP` `[VERIFIED: pyproject.toml:78-83]` | — |
| ty | type report | ✓ | 295 diagnostics at HEAD | it is a baseline, not a gate |

**Missing dependencies with no fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest with `pytest-asyncio` in auto mode |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest -q` |
| Full suite command | `.venv/bin/pytest -q -m ''` |

`addopts = "-v --tb=short -m 'not e2e and not schema'"`, so a bare run is unit-only and the two
infrastructure suites need `-m e2e` / `-m schema` / `-m ''`.

### Phase Requirements → Test Map

No requirement ID maps to this phase. The success criteria are the acceptance surface.

| Criterion | Behavior | Test Type | Automated Command | File Exists? |
|-----------|----------|-----------|-------------------|--------------|
| 1, 3 | One `AsyncExitStack`, `dispose` before the probe, "shutdown" registered first, no `shutdown_step_failed` | unit (AST or source read, as `test_auth_package_shape.py` does) | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ Wave 0 — no case pins the teardown shape today |
| 2 | Builders exist and the boot-fatal ones run first; `*_absent` texts unchanged | unit | `.venv/bin/pytest -q tests/unit/test_config.py` | ✅ (edits where a signature changed) |
| 4 | `Runtime` is frozen, slotted, eight typed fields, in `app/runtime.py` | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ Wave 0 |
| 5 | Exactly one `request.app.state` read in `dependencies.py`; four getters gone; `sign_out_all` declares `get_runtime` and no other route does | unit (AST over `dependencies.py` and the route table) | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ Wave 0 — this is the discretion item CONTEXT flags |
| 6 | No test sets a lifespan-built `app.state` attribute; `opened_sessions` stays | unit (grep-style AST case) or reviewer check | `.venv/bin/pytest -q -m ''` | ❌ Wave 0 (optional) |
| 7 | All three suites exit 0 | all | `.venv/bin/pytest -q -m ''` and `-m e2e` and `-m schema` | ✅ — **blocked by the pre-existing failure, Pitfall 1** |
| 8 | Four builders raise on a transient failure, return `None` only for absent settings; one Play class, no `build`/lock/interval; two warm-up warnings gone | unit | `.venv/bin/pytest -q tests/unit/test_google_play_notifications.py tests/unit/test_config.py` | ✅ (cases at 1075, 1090 invert; the rebuild class at 1118+ is deleted) |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest -q` plus `.venv/bin/ruff check src tests`
- **Per wave merge:** `.venv/bin/pytest -q -m ''`
- **Phase gate:** all three marker runs exit 0, `ruff` prints `All checks passed!`, and `ty check`
  is re-read against the 295 baseline — measured, never copied from this document.

### Wave 0 Gaps
- [ ] A case that pins the exit-stack shape (criteria 1 and 3) — none exists today.
- [ ] A case that pins `Runtime` as frozen and slotted with eight fields (criterion 4).
- [ ] A case that pins "exactly one `app.state` read in `dependencies.py`" and the route clause of
      criterion 5 — CONTEXT leaves this to the planner; without it criterion 5 is a claim, not a
      measurement.
- [ ] A `Runtime` factory for unit tests, filling the fields a case does not name.

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `build_jwt_verifier` stays boot-fatal; D-08 extends the same rule to the Play push verifier, so a pod never serves a route whose verifier is `None` for a transient reason |
| V3 Session Management | no | untouched |
| V4 Access Control | yes — by preservation | `sign_out_all` keeps `Depends(get_identity)`; D-05 changes one parameter and nothing about the barrier |
| V5 Input Validation | no | no request body or header parsing changes |
| V6 Cryptography | no | no key handling changes; `read_private_key` and `SignedDataVerifier` keep their call shape |

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A pod serving with a silently absent verifier | Spoofing | D-08 — raise at boot; the `*_absent` path stays only for genuinely unconfigured settings |
| A failing teardown hiding a leaked credential-bearing client | Information disclosure | `AsyncExitStack` runs every remaining callback and then propagates, so no leak is swallowed |
| The container exposing a secret through a `repr` | Information disclosure | `Runtime` holds adapters and the config object, not raw secrets; `DatabaseConfig.url` renders a password, and `build_db_engine` already sets `hide_parameters=True`. A `Runtime` accidentally logged would render `config`. Worth one line in the plan: do not log the container. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The re-measured `CURRENT` will be `(7, 18, 58)` | Pitfall 2 | Low — the plan must re-measure from the failing run's text, never write this number |
| A2 | Fixing the pre-existing e2e case is a one-line expectation change (`proof_rejected` → `purchase_proof_rejected`) | Pitfall 1 | Medium — the alternative is changing the log event name in `errors.py`, which would ripple; the plan should decide deliberately, not assume |
| A3 | `ty check` will not gain diagnostics from the lambda session factories in unit tests | Environment Availability | Low — `ty` is a baseline, not a gate; a rise is recorded rather than blocking |

## Open Questions

1. **Does criterion 7 include fixing the Phase-47 restore case?**
   - What we know: the case fails at HEAD, is unrelated to this phase, and criterion 7 says all
     three suites exit 0.
   - What's unclear: whether the user wants Phase 50 to carry someone else's fix.
   - Recommendation: fix it, in its own commit with its own message naming Phase 47 as the origin,
     so the record stays honest either way.

2. **Does `CappedRefreshRequest` survive the merge?**
   - What we know: it exists only to cap the credential refresh timeout for the Play read
     `[VERIFIED: auth/google_play.py:221-229]`, and D-09 does not name it.
   - Recommendation: keep it — D-10 deletes the rebuild machinery, not the refresh transport.

## Sources

### Primary (HIGH confidence)
- This tree, read this session: `src/nativespeaker/api/app/lifespan.py`,
  `app/dependencies.py`, `app/main.py`, `auth/google_play.py`, `auth/firebase.py`,
  `auth/app_store.py`, `services/restore.py`, `routers/auth.py`, `schemas/auth.py`,
  `tests/unit/conftest.py`, `tests/e2e/conftest.py`, `tests/unit/test_auth_package_shape.py`,
  `tests/unit/test_config.py`, `tests/unit/test_google_play_notifications.py`, `pyproject.toml`,
  `AGENTS.md`, `.planning/ROADMAP.md:901-916`, `50-CONTEXT.md`, `.planning/STATE.md`
- Commands run this session: `pytest -q`, `pytest -q -m e2e`, `pytest -q -m schema`,
  `ruff check src tests`, `ty check`, an `AsyncExitStack` teardown probe, a frozen-slots
  dataclass probe, and an `ast` walk of `auth/google_play.py`

### Secondary (MEDIUM confidence)
- None consulted; no external documentation was needed, because the phase adds no library.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, versions read from the installed interpreter
- Architecture: HIGH — every call site enumerated by grep and read
- Pitfalls: HIGH — each one was reproduced or measured, not recalled

**Research date:** 2026-09-17
**Valid until:** 30 days, or the first commit that touches `lifespan.py` or `dependencies.py`
