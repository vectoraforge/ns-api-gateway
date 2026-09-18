# Phase 50: Typed runtime container behind an exit-stack lifespan - Pattern Map

**Mapped:** 2026-09-17
**Files analyzed:** 15 (7 source, 8 test)
**Analogs found:** 14 / 15

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/app/runtime.py` (new) | schema (frozen dataclass) | data declaration | `src/nativespeaker/api/schemas/auth.py:106-110` | exact |
| `src/nativespeaker/api/app/lifespan.py` | config / process lifecycle | boot + teardown | itself: `lifespan.py:56-121` builders, `101-110` raise | role-match (no `AsyncExitStack` anywhere in the tree) |
| `src/nativespeaker/api/app/dependencies.py` | dependency | request-response | itself: `dependencies.py:93-95, 121-127` (`Depends` chain, no `Request`) | exact |
| `src/nativespeaker/api/auth/google_play.py` | adapter | request-response | `src/nativespeaker/api/auth/app_store.py:47-59, 119-122` | exact |
| `src/nativespeaker/api/auth/firebase.py` | builder | boot | `lifespan.py:136-149` (`_play_credential`, narrow arm first) | exact |
| `src/nativespeaker/api/routers/auth.py` | handler (one route) | request-response | `routers/auth.py:190-197` (reads a dependency result field) | exact |
| `src/nativespeaker/api/services/restore.py` | service | CRUD | itself: `restore.py:43-50` (one annotation) | exact |
| `tests/unit/conftest.py` (Runtime factory) | test fixture | data declaration | `tests/unit/conftest.py:106-123` (`make_test_verifier`, `TEST_IDENTITY`) | exact |
| `tests/e2e/conftest.py` (7 fixtures) | test fixture | setup/teardown | `tests/e2e/conftest.py:289-298, 331-340` | exact |
| 6 unit files overriding a deleted getter | test | request-response | `tests/unit/test_challenge_endpoint.py:128-137` | exact |
| unit files setting `app.state` | test | setup | `tests/unit/test_identity_accessors.py:112-124` | exact |
| `tests/unit/test_app_wiring.py` (criteria 1, 3, 4, 5) | test | AST / route table | `test_app_wiring.py:25-51, 116-121`; `test_firebase_adapter.py:637-654`; `test_auth_package_shape.py:12-26` | exact for 4 and 5, none for 1 and 3 |
| `tests/unit/test_google_play_notifications.py` | test | request-response | itself: `:1008-1011` fixture, `:317-323` stub | exact |
| `tests/unit/test_config.py` | test | boot | itself: `:709-720` (`_warnings` recorder) | exact |
| `tests/unit/test_auth_package_shape.py` | test | AST count | itself: `:13` `CURRENT` literal | exact |

## Pattern Assignments

### `app/runtime.py` (new) — the `Runtime` container

**Analog:** `src/nativespeaker/api/schemas/auth.py:106-110`

```python
@dataclass(frozen=True, slots=True)
class LinkedIdentity:
    """The account a verified credential resolved to: the user row and the identity row."""
    user: User
    identity: ExternalIdentity
```

Same two decorator arguments, same one-field-per-line body, docstring within the three-line rule.
The eight D-02 fields, in build order, each typed — no default on any field (a default makes every
field `X | None` and drops the fact that boot produced all eight). `session_factory` is
`async_sessionmaker[SQLModelAsyncSession]` (D-04); the import pair is already in
`lifespan.py:15-16`.

---

### `app/lifespan.py` — builders and the stack

**Analog (the raise D-08 copies):** `lifespan.py:101-110`

```python
def build_jwt_verifier(jwt: JWTConfig) -> JWTVerifier:
    """The identity-barrier verifier. Unlike the two builders above, this one has no degraded form."""
    try:
        return JWTVerifier(jwks_url=jwt.jwks_url, ...)
    except PyJWTError as failure:
        raise RuntimeError(f"JWKS unusable at {jwt.jwks_url}: {failure}") from failure
```

`build_google_push_verifier` (`:83-98`) and `build_app_store_verifier` (`:56-73`) keep their
`return None` for absent settings and take this `raise RuntimeError(... ) from failure` shape for
the failure arms. The message names the setting or the URL, never a secret — `_prove_database_reachable`
(`:124-133`) shows the rule: it prints host, port and name because `DatabaseConfig.url` renders the
password.

**Analog (the two-arm narrow-first order, Pitfall 4):** `lifespan.py:136-149`

```python
    try:
        credential, _project = google.auth.default(scopes=[PLAY_SCOPE])
    except google.auth.exceptions.DefaultCredentialsError:
        return None
    except google.auth.exceptions.GoogleAuthError:
        ...
```

Keep `DefaultCredentialsError` first; the second arm becomes the raise, and the
`play_credential_warm_up_failed` warning goes.

**Analog (the `*_absent` warning, text unchanged):** `lifespan.py:184-192`

```python
        if app_store_verifier is None or not config.app_store.products:
            logger.warning("app_store_configuration_absent",
                           consequence="POST /webhooks/app-store refuses every notification and ...")
```

Each new `build_*` keeps its `logger.warning(event, consequence=...)` with the same event name and
the same text; only the two warm-up warnings are deleted.

**Analog (builder call shape and multiline arguments):** `lifespan.py:113-121` — one argument per
line aligned under the opening delimiter, and `logger.info("started", ...)` at `:231-232` stays.

**No analog:** the `AsyncExitStack` body. The tree holds no `ExitStack` or `AsyncExitStack`
(`grep -rn` over `src` and `tests`). Use RESEARCH.md "Pattern 1" verbatim: `stack.callback` for the
shutdown log first, `push_async_callback(engine.dispose)` before `_prove_database_reachable`,
`enter_async_context` for each `httpx.AsyncClient`, `stack.callback(firebase_admin.delete_app, app)`
per named app. The whole `try/finally` at `:166, 235-255` and every `shutdown_step_failed` line go.

---

### `auth/google_play.py` — `GooglePlayNotifications` (D-09, D-10)

**Analog:** `src/nativespeaker/api/auth/app_store.py:47-59`

```python
class AppStoreNotifications:
    """Apple's signed notification envelope and its two nested payloads, verified against a pinned root."""

    def __init__(self, *, verifier: SignedDataVerifier | None,
                 products: dict[str, str]) -> None:
        self._verifier = verifier
        # Server-controlled reference data, never a value the store supplied.
        self._products = products

    def verify(self, signed_payload: str) -> VerifiedNotification | None:
        """Verify the envelope and both nested payloads, then return this project's value type."""
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")
```

Keyword-only constructor, one `self._x = x` per parameter, and each entry point opening with its own
`if self._x is None: raise Unavailable(stage=...)`. `verify_transaction` (`:119-122`) repeats the same
guard for the second entry point — that is what `read` and `read_for_restore` do with the credential,
in place of `await self._credential_in_hand()` (`google_play.py:247-255`, deleted). Stages keep their
current strings: `google_push_verify`, `play_subscriptions_read`, `RESTORE_UNCONFIGURED_STAGE`.
Delete `build`, `_rebuild_lock`, `_rebuild_interval`, `_next_rebuild`, `_credential_in_hand` and the
two interval constants. `CappedRefreshRequest` (`:221-229`) stays: it is the refresh transport, not
the rebuild.

**Docstring:** one line saying what the class does, like `app_store.py:48` — not what the token is.

---

### `app/dependencies.py` — one `app.state` read

**Analog (a dependency taking only `Depends`, no `Request`):** `dependencies.py:121-127`

```python
def get_auth_service(db: AsyncSession = Depends(get_db),
                     adapter: FirebaseAdminLookup = Depends(get_firebase_adapter),
                     devicecheck: AppleDeviceCheck = Depends(get_devicecheck_adapter)
                     ) -> AuthService:
    return AuthService(db=db, adapter=adapter, devicecheck=devicecheck)
```

`get_runtime(request: Request) -> Runtime` is the only function left holding `Request` for
`app.state`; every other one gains `runtime: Runtime = Depends(get_runtime)` and reads a field.
`get_claims` (`:58-74`) keeps `Request` for `request.headers.get("authorization")` at `:63`.
`get_quota_service` (`:93-95`) needs the `runtime` parameter too, because `get_session_factory` goes
(Pitfall 5). Definition order matters: the comment at `:98` records that `Depends()` defaults are
evaluated at definition time, so `get_runtime` is defined at the top.

Delete the comments whose subject is gone: `:98`(reword if still true), `:112`, `:117`, `:138`.

---

### `routers/auth.py:206-213` — `sign_out_all`

**Analog:** the same file, `:190-197` — a route reading a field off a resolved dependency
(`linked.user.id`, `linked.identity.provider`). Replace
`adapter: FirebaseAdminLookup = Depends(get_firebase_adapter)` with
`runtime: Runtime = Depends(get_runtime)` and pass `runtime.firebase_adapter` to
`revoke_with_retry`. The `Depends(get_claims)` and `Depends(get_identity)` parameters do not move.

---

### `services/restore.py:43-50` — one annotation

`play: PlayDeveloperSubscriptions` becomes `play: GooglePlayNotifications`; the import at `:13`
changes with it. Nothing else in the file moves.

## Test Patterns

### A `Runtime` factory for unit tests

**Analog:** `tests/unit/conftest.py:106-123` — a module-level `make_*` function plus a module-level
literal (`TEST_IDENTITY`) built from the real production type. Build the container from the fakes
already there: `make_test_verifier()` (`:106`) and `FakeFirebaseAdapter` (`:196`).

### Swapping one field in an e2e fixture

**Analog:** `tests/e2e/conftest.py:289-298`

```python
@pytest.fixture
def scripted_firebase_adapter(_app_lifespan):
    """Swap app.state.firebase_adapter for a scripted fake, defaulting to ok with empty providerData."""
    original = _app_lifespan.state.firebase_adapter
    adapter = FakeFirebaseAdapter()
    _app_lifespan.state.firebase_adapter = adapter
    try:
        yield adapter
    finally:
        _app_lifespan.state.firebase_adapter = original
```

Same save / yield / restore skeleton; the two assignments become
`_app_lifespan.state.runtime = replace(_app_lifespan.state.runtime, firebase_adapter=...)`.
Save the **field**, never the whole container (Pitfall 3): `_db_transaction` (`:252-275`) is
`autouse` and `scripted_google_play` nests inside other fixtures. `_db_transaction:258` reads
`original_factory.kw["bind"]`, which works unchanged on `runtime.session_factory`.

### Overriding a dependency in a unit client

**Analog:** `tests/unit/test_challenge_endpoint.py:128-137`

```python
    app.dependency_overrides[get_claims] = lambda: claims
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter
```

The deleted getters' entries become one `app.dependency_overrides[get_runtime] = lambda: <Runtime>`.

### Setting lifespan objects on a test app

**Analog:** `tests/unit/test_identity_accessors.py:118-122`

```python
    # Read per request by the dependency, exactly as the real lifespan supplies them.
    app.state.jwt_verifier = make_test_verifier()
    opened: list[_ProbeSession] = []
    app.state.opened_sessions = opened
    app.state.session_factory = lambda: _ProbeSession(row, opened)
```

The two lifespan-built lines collapse into one `app.state.runtime = ...`; `opened_sessions` stays a
separate `app.state` attribute (criterion 6).

### The criterion 4 case: frozen and slotted

**Analog:** `tests/unit/test_firebase_adapter.py:637-654`

```python
        assert is_dataclass(value_type)
        assert value_type.__dataclass_params__.frozen is True
        assert hasattr(value_type, "__slots__")
    ...
        with pytest.raises(FrozenInstanceError):
            identity.provider_uid = "somebody-elses-uid"  # ty: ignore[invalid-assignment]
    ...
        assert not hasattr(identity, "__dict__")
```

Note Pitfall 6: an unknown attribute raises `FrozenInstanceError`, not `AttributeError`.

### The criterion 5 case: the route clause

**Analog:** `tests/unit/test_app_wiring.py:25-51` (`_api_routes`, `_declared`, `_flattened`,
`_route_at`) and `:116-121`

```python
class TestTheSignOutRouteOpensNoSession:
    """D-04. The revocation writes no row and reads no table, so the handler declares no session."""

    def test_sign_out_all_declares_no_database_session(self):
        # `_flattened` walks sub-dependencies, so a session taken through a service is visible here.
        assert get_db not in _flattened(_route_at("/auth/sign-out-all"))
```

`get_runtime in _flattened(_route_at("/auth/sign-out-all"))` and, for every other route, the
declared list holds no direct `get_runtime`.

### The criteria 1 and 3 case, and the counting literal

**Analog (source read over AST):** `tests/unit/test_auth_package_shape.py:16-26` — parse the module
with `ast`, walk it, compare against a literal recorded in the file. The same shape pins "one
`AsyncExitStack`", "`dispose` registered before the probe", "no `shutdown_step_failed`" and "exactly
one `request.app.state` read in `dependencies.py`". `CURRENT` at `:13` is re-measured from the
failing run's own text in the same commit as the merge (Pitfall 2) — never computed by arithmetic.

### Recording the warnings a builder logs

**Analog:** `tests/unit/test_config.py:709-720`

```python
    def _warnings(self, monkeypatch, failure: str) -> list[str]:
        """The events one read logs while `google.auth.default()` raises `failure`."""
        recorded: list[str] = []
        monkeypatch.setattr("nativespeaker.api.app.lifespan.logger.warning",
                            lambda event, **_fields: recorded.append(event))
```

The cases asserting `["play_credential_warm_up_failed"]` go with the warning; the absent-setting
cases keep this helper and their event names.

### The Play suite

**Analog:** `tests/unit/test_google_play_notifications.py:1008-1011`

```python
@pytest.fixture
def push_tokens(jwks) -> PubSubPushTokens:
    """The real push-token class over a real `JWTVerifier`, built the way lifespan builds it."""
    return PubSubPushTokens(verifier=build_google_push_verifier(_play_config()))
```

becomes `GooglePlayNotifications(...)` with the four D-09 constructor arguments. The cases at
`:1072-1075` and `:1086-1090` invert to `pytest.raises(RuntimeError)`; the class at `:1118-1148` is
deleted. `_stub_request` (`:317-323`) returns a `Runtime` in place of the `SimpleNamespace` — the
dependency now reads `runtime.google_play_notifications` and `runtime.config`.

## Shared Patterns

### Boot-fatal versus absent (D-08)
**Source:** `lifespan.py:101-110` (raise) and `:184-192` (warn and continue).
**Apply to:** `build_google_push_verifier`, `_play_credential`, `build_app_store_verifier`,
`_application_default_credential`. Absent setting → `None` plus the existing `*_absent` warning;
any other failure → `raise RuntimeError(...) from failure`.

### Refusing with `Unavailable`
**Source:** `auth/app_store.py:58-59, 121-122`.
**Apply to:** every entry point of `GooglePlayNotifications`, stage strings unchanged.

### Comments and docstrings
**Source:** `AGENTS.md`; live examples at `lifespan.py:115`, `dependencies.py:94`,
`app_store.py:53`. One line, inline, ASD-STE100, only where a later edit would go wrong without it.
Delete every comment whose subject this phase deletes (`lifespan.py:97, 138, 248`,
`dependencies.py:112, 117, 138`).

### Do not log the container
`Runtime` holds `config`, and `DatabaseConfig.url` renders a password. `logger.info("started", ...)`
(`lifespan.py:231-232`) names three scalars, never an object — keep it that way.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/lifespan.py` (the stack body) | config | boot + teardown | No `AsyncExitStack` or `ExitStack` exists in `src` or `tests`; use RESEARCH.md Pattern 1 |
| `tests/unit/test_app_wiring.py` (criteria 1 and 3) | test | AST | No case pins teardown order today; nearest shape is `test_auth_package_shape.py:16-26` |

## Metadata

**Analog search scope:** `src/nativespeaker/api/{app,auth,routers,services,schemas}`, `tests/unit`,
`tests/e2e`
**Files read this session:** 14 (all git-tracked; `git ls-files` confirmed)
**Pattern extraction date:** 2026-09-17
