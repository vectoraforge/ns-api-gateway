# Phase 50: Typed runtime container behind an exit-stack lifespan - Context

**Gathered:** 2026-09-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Two rewrites of `app/lifespan.py`: one `AsyncExitStack` owns every teardown, and each provider
has a builder. The eight objects the lifespan builds go into one frozen, slotted dataclass,
`Runtime`, which is the only attribute the lifespan puts on `app.state`. `dependencies.py` reads
`app.state` once, in `get_runtime`. The tests that set `app.state` attributes replace the
container instead.

The discussion added one rule the ROADMAP goal did not have. A warm-up that fails at boot stops
the pod (D-08). With the retry gone, the two Google Play classes merge into
`GooglePlayNotifications` (D-09). So this phase is a refactor plus one boot-rule change, and the
Phase 50 entry in `ROADMAP.md` says so (D-11).

**In scope:** `app/{lifespan,dependencies}.py`, the new `app/runtime.py`,
`auth/{google_play,firebase}.py`, `routers/auth.py` (one route), `services/restore.py` (one
annotation), the Phase 50 entry in `ROADMAP.md`, and the unit, e2e and schema tests that set
`app.state`, override a deleted getter, import a changed builder, or test the rebuild.

**Out of scope:** any change to a route's status code or body; `AppStoreNotifications`,
`AppleDeviceCheck`, `FirebaseAdminLookup`, `JWTVerifier` and `LLMService` beyond their
constructor call sites; both matched todos.

</domain>

<decisions>
## Implementation Decisions

### The container

- **D-01: The module is `app/runtime.py`, the class is `Runtime`, the attribute is `app.state.runtime`.**
  `get_runtime(request: Request) -> Runtime` in `dependencies.py` returns that attribute and is
  the one `app.state` read. Every other dependency declares `runtime: Runtime =
  Depends(get_runtime)` and reads a field.
- **D-02: `Runtime` has eight fields, declared in build order.** `config`, `session_factory`,
  `jwt_verifier`, `firebase_adapter`, `devicecheck_adapter`, `app_store_notifications`,
  `google_play_notifications`, `llm_service`. The two boot-fatal objects sit first. The
  lifespan's one `Runtime(...)` call reads top to bottom in the order the locals were built.
  `google_play_notifications` replaces the ROADMAP's `google_push_tokens` and
  `play_subscriptions` (D-09).
- **D-03: `get_config` is deleted.** After the rewrite it is a one-line step with no caller.
  `get_chat_service` reads `runtime.config`.
- **D-04: `session_factory` is annotated `async_sessionmaker[SQLModelAsyncSession]`.** The
  builder declares that return type and the field takes it. `dependencies.py:88` uses the bare
  name today.

### The sign-out-all route

- **D-05: `sign_out_all` declares `get_runtime` and reads `runtime.firebase_adapter`.**
  The parameter is `runtime: Runtime = Depends(get_runtime)`.
  `routers/auth.py:208` declares `get_firebase_adapter` today, and criterion 5 deletes that
  getter. The route still opens no session. No other route declares `get_runtime`. Criterion 5 in
  `ROADMAP.md` is amended to say both (D-11). — **Reversibility:** reversible — one route, one
  parameter.

### Builders

- **D-06: Each builder is named after the `Runtime` field it fills.** `build_session_factory`,
  `build_firebase_adapter`, `build_devicecheck_adapter`, `build_app_store_notifications`,
  `build_google_play_notifications`. The three that own the engine or an httpx client are `async
  def` and take the stack. `build_session_factory` registers `dispose` before the reachability
  probe. `build_db_engine`, `build_jwt_verifier`, `build_app_store_verifier`,
  `build_google_push_verifier`, `google_push_pins` and `_play_credential` keep their names:
  `tests/unit/test_config.py` and `tests/unit/test_google_play_notifications.py` import them.
- **D-07: `build_firebase_adapter` and `build_admin_apps` both take a `JWTConfig`.**
  The parameter is `jwt: JWTConfig`.
  `build_admin_apps` reads only `config.jwt` today (`firebase.py:45-49`) and has no annotation.
  The four `StubConfig()` call sites in `tests/unit/test_firebase_adapter.py` pass the jwt block.
- **D-08: A warm-up that fails at boot stops the pod.** The rule `build_jwt_verifier` already
  follows (`lifespan.py:109-110`) applies to every provider. A setting or a file that is absent
  means the deployment has no such provider: the pod starts, and the existing `*_absent` warning
  is logged, text unchanged. A transient failure, or a file that exists but cannot be read or
  parsed, raises `RuntimeError` and the pod does not start. Four functions change:
  `build_google_push_verifier` raises on `PyJWTError` and returns `None` only when the pins are
  absent; `_play_credential` raises on `GoogleAuthError` and returns `None` only on
  `DefaultCredentialsError`; `_application_default_credential` in `auth/firebase.py` catches
  `DefaultCredentialsError` only; `build_app_store_verifier` raises on `OSError` or `ValueError`
  from the root file. The two warm-up warnings, `google_push_verifier_warm_up_failed` and
  `play_credential_warm_up_failed`, are deleted with the tests that assert them.
  — **Reversibility:** costly — reverses Phase 44 D-14 and WR-41 for the Play route, and the
  rebuild code is deleted, not disabled.
- **D-09: `PubSubPushTokens` and `PlayDeveloperSubscriptions` merge into one class `GooglePlayNotifications`.**
  It lives in `auth/google_play.py`, shaped like `AppStoreNotifications`. Its constructor takes
  `verifier: JWTVerifier | None`, the credential or `None`, the httpx client and the product
  map. It keeps `verify`, `read` and `read_for_restore`, each refusing with `Unavailable` when
  its value is `None`, as today. Consumers: `dependencies.py` (one field, two reads),
  `services/restore.py:44` (the `play` annotation), the lifespan. The docstring says what the
  class does, within the three-line rule; the user rejected the old docstring, which described
  the token rather than the class.
- **D-10: The rebuild code is deleted.** The `build` parameters, `_rebuild_lock`,
  `rebuild_interval_seconds`, `_next_rebuild`, `_credential_in_hand`,
  `PUSH_VERIFIER_REBUILD_INTERVAL_SECONDS` and `PLAY_CREDENTIAL_REBUILD_INTERVAL_SECONDS` go.
  The lifespan passes each value once, never a value and a function that makes it.
  `tests/unit/test_google_play_notifications.py:1118-1145` (the rebuild class) is deleted; the
  cases at lines 1075 and 1090 expect the raise; `push_tokens` at line 1009 builds the merged
  class. `google_push_pins` is read once in the builder; a `None` verifier then has one meaning.

### Records

- **D-11: The Phase 50 entry in `ROADMAP.md` is amended in the discuss commit.** Eight fields
  and the field list (D-02, D-09); criterion 5 names `sign_out_all` and pins that no other route
  declares `get_runtime` (D-05); "every warning text unchanged" excepts the two deleted warm-up
  warnings; a new criterion 8 states the boot rule and the merge (D-08, D-09, D-10); the
  requirements line no longer says "behavior-preserving". `REQUIREMENTS.md` maps nothing to this
  phase and is not edited.

### Carried forward

- 48 D-10, 49: every comment this phase writes is ASD-STE100, one line, only where needed.
  Delete every comment whose subject is a deleted getter, the old teardown, or the rebuild
  (for example `lifespan.py:97, 138, 248`, `dependencies.py:112, 117, 138`).
- 49 D-06 annotations stand: `AuthService.__init__` and `get_auth_service` annotate the two
  adapters as `FirebaseAdminLookup` and `AppleDeviceCheck`.
- 49 D-08: `tests/unit/test_auth_package_shape.py` compares a literal file count of `auth/`.
  This phase adds and removes no file there, so the tuple does not change.

### Claude's Discretion

- The tests area was not discussed. The planner chooses how the six unit files that override
  `get_firebase_adapter` or `get_devicecheck_adapter` and the nine files that set `app.state`
  build a `Runtime` from fakes: a shared helper in `tests/unit/conftest.py` that fills the
  unnamed fields, or per-file construction. The seven e2e fixtures in `tests/e2e/conftest.py`
  that swap one attribute use `dataclasses.replace` on the real `Runtime`, as the ROADMAP says;
  one helper or seven copies is the planner's call. `_stub_request` in
  `tests/unit/test_google_play_notifications.py:318` builds a `Runtime`, not a `SimpleNamespace`.
- Whether a wiring test in `tests/unit/test_app_wiring.py` pins criterion 5's route clause.
- Whether `Runtime` and `get_runtime` carry docstrings, within the three-line rule.
- Commit granularity and plan wave order. The container type change breaks every site at once;
  the boot rule (D-08) and the merge (D-09, D-10) can land before or after it.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The phase entry
- `.planning/ROADMAP.md` Phase 50 — the goal and the eight criteria, as amended by D-11.

### Prior-phase decisions
- `.planning/phases/49-delete-the-single-implementation-auth-protocols/49-CONTEXT.md` — D-06
  (adapter annotations), D-08 (the `auth/` file-count tuple), the comment rule.
- `.planning/phases/49-delete-the-single-implementation-auth-protocols/49-VERIFICATION.md` —
  the suite counts criterion 7 starts from.
- `.planning/phases/48-narrow-identity-to-the-verified-pair/48-CONTEXT.md` — D-10 (comment
  rule).
- `.planning/phases/44-post-webhooks-google-play-rtdn/44-CONTEXT.md` — the degraded-mode rule
  D-08 replaces for a failed warm-up. Absent configuration keeps its 503 behavior.

### Conventions
- `AGENTS.md` (repo root) — package layout, function shape, comment and docstring rules.

No spec file: Phases 47 to 50 are refactors added after the spec phases closed.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lifespan.py:56-121` — the five existing builders; `build_jwt_verifier:109-110` is the model
  for D-08's raise.
- `schemas/auth.py:106` — `LinkedIdentity`, the frozen slotted dataclass style `Runtime` follows.
- `auth/app_store.py:47-56` — `AppStoreNotifications`, the shape `GooglePlayNotifications`
  follows.
- `tests/unit/conftest.py:106, 196` — `make_test_verifier` and `FakeFirebaseAdapter`, the fakes
  a `Runtime` helper would take.

### Established Patterns
- A builder returns `None` for absent settings and logs one `*_absent` warning through the
  module logger; `tests/unit/test_config.py:712` monkeypatches `lifespan.logger.warning`.
- A dependency reads a dependency's result field (`linked.identity.id`), which is how the route
  in D-05 reads `runtime.firebase_adapter`.
- `tests/e2e/conftest.py:255-274` reads `session_factory.kw["bind"]` for the engine; that read
  works on `runtime.session_factory`.

### Integration Points
- `app.state` writes: `lifespan.py:157, 168, 178, 191, 210, 213, 221, 224, 226`. Reads:
  `dependencies.py:41, 46, 69, 81, 90, 104, 113, 118, 142-144, 151, 163, 173, 179`.
- `get_firebase_adapter` / `get_devicecheck_adapter` overrides: six unit files
  (`test_create_user_body`, `test_create_user_precedence`, `test_claim_precedence`,
  `test_claim_precedence_registered`, `test_upgrade_precedence`, `test_challenge_endpoint`).
- `app.state` setters in tests: `tests/e2e/conftest.py` (seven fixtures),
  `tests/unit/test_identity_accessors.py`, `test_jwks_offload.py`, `test_auth_security.py`,
  `test_app_wiring.py`, `test_exception_handlers.py`, and the three precedence suites.
  `opened_sessions` stays on `app.state`.
- The two Play classes: `auth/google_play.py:192-262`, `services/restore.py:13, 44`,
  `dependencies.py:143, 163, 179`, `lifespan.py:30-31, 210-217`.

</code_context>

<specifics>
## Specific Ideas

- The user reads the code, not the prose. Name things by their identifiers: `Runtime`,
  `get_runtime`, `GooglePlayNotifications`, `build_google_play_notifications`. Do not coin
  words such as "container object", "seam" or "degraded mode" in code or comments.
- The user rejected: a value and a function that makes it passed to one constructor; a
  docstring that names what a class checks instead of what it does; a pod that starts when a
  boot-time fetch failed.
- Plain English in every user-facing sentence, ASD-STE100.

</specifics>

<deferred>
## Deferred Ideas

- The two pending todos match every phase because `todo.match-phase` has no score threshold.
  Moving them out of `.planning/todos/pending/` into backlog phases of `ROADMAP.md` would stop
  it; raised, not done.

### Reviewed Todos (not folded)

- `secret-manager-integration` (score 0.9) — config; matched on "google", "phase", "replace"
  and the word "config" in the goal. Not folded, as in Phases 46, 48 and 49.
- `message-ordering-is-unspecified` (score 0.6) — chats; matched on "read", "llm", "phase",
  "two", "both". Not folded, as in Phases 46, 48 and 49.

</deferred>

---

*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Context gathered: 2026-09-17*
