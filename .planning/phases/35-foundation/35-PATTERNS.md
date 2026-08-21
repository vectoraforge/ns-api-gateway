# Phase 35: Foundation - Pattern Map

**Mapped:** 2026-08-20
**Files analyzed:** 30 new · 22 modified · 14 deleted
**Analogs found:** 30 / 30 new files (9 exact · 4 role-match · 2 partial for source; 15 for tests)

> Every excerpt below was read out of the working tree today. `.planning/codebase/*.md` is stale and
> was not consulted. Line numbers are from the files as they exist on branch `gsd/phase-34-schema`.

---

## File Classification

### New source files

| New file | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/auth/__init__.py` | package barrel | n/a | `src/nativespeaker/api/models/__init__.py` | exact |
| `src/nativespeaker/api/auth/verification.py` | verifier / adapter | request-response | `src/nativespeaker/api/auth.py` (the file being moved) | exact |
| `src/nativespeaker/api/auth/wire.py` | utility (pure parser) | transform | `src/nativespeaker/api/resilience.py:13-35` | role-match |
| `src/nativespeaker/api/auth/context.py` | typed value objects | n/a | `src/nativespeaker/api/auth.py:10-14` | exact |
| `src/nativespeaker/api/auth/barrier.py` | middleware | request-response | `src/nativespeaker/api/logs.py:57-76` | partial (base class differs) |
| `src/nativespeaker/api/auth/registry.py` | declarative table + startup validator | batch / startup | `src/nativespeaker/api/app/errors.py:22-42` + `config.py:100-109` | partial |
| `src/nativespeaker/api/auth/identity.py` | database accessor | CRUD (read) | `src/nativespeaker/api/database/chats.py:38-47` | exact |
| `src/nativespeaker/api/auth/audit.py` | database writer | append / CRUD (write) | `src/nativespeaker/api/database/subscriptions.py:61-80` + `app/dependencies.py:20-27` | role-match |
| `src/nativespeaker/api/auth/challenges.py` | database store | CRUD (atomic conditional update) | `src/nativespeaker/api/database/usage.py:16-35` | exact |
| `src/nativespeaker/api/auth/keys.py` | config model + crypto utility | transform | `src/nativespeaker/api/config.py:19-31, 100-109` | role-match |
| `src/nativespeaker/api/auth/budgets.py` | in-process counter | event-driven / metering | `src/nativespeaker/api/resilience.py:38-70` | role-match |
| `src/nativespeaker/api/auth/adapters.py` | interface declarations | n/a | `src/nativespeaker/api/auth.py:17-20` | exact |
| `src/nativespeaker/api/errors.py` | error registry (package root, D-10) | n/a | `src/nativespeaker/api/exceptions.py` + `app/errors.py:45-54` | exact |
| `src/nativespeaker/api/models/identities.py` *(new; split is discretion)* | model | n/a | `src/nativespeaker/api/models/subscriptions.py:29-52` | exact |
| `src/nativespeaker/api/models/auth.py` *(new; `AuthChallenge` + `AuthEvent`)* | model | n/a | `src/nativespeaker/api/models/subscriptions.py:29-52` + `models/users.py:26-36` | exact |

### New test files (from `35-VALIDATION.md` § Wave 0 Requirements)

| New file | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `tests/unit/test_barrier_wire_contract.py` | test (pure logic) | transform | `tests/unit/test_jwt_security.py:19-47` | role-match |
| `tests/unit/test_route_registry.py` | test (introspection) | batch | `tests/unit/test_error_contract.py:55-85` + `tests/schema/test_inventory.py:66-70` | exact |
| `tests/unit/test_error_registry.py` | test (contract) | n/a | `tests/unit/test_error_contract.py` + `test_exception_handlers.py:29-89` | exact |
| `tests/unit/test_audit_details.py` | test (pure logic) | transform | `tests/unit/test_models.py:25-43` | role-match |
| `tests/unit/test_hmac_keys.py` | test (config) | transform | `tests/unit/test_config.py:36-96` | exact |
| `tests/unit/test_budgets.py` | test (in-process gate) | event-driven | `tests/unit/test_usage.py:27-40` (`TestRequireQuota`) | role-match |
| `tests/unit/test_challenge_ids.py` | test (pure logic) | transform | `tests/unit/test_models.py` | role-match |
| `tests/unit/test_adapter_interfaces.py` | test (introspection) | batch | `tests/schema/test_inventory.py` (exact-set absence assertions) | role-match |
| `tests/unit/test_identity_accessors.py` | test (DI accessor raises) | request-response | `tests/unit/test_usage.py:27+` + `test_auth_security.py:16-34` | exact |
| `tests/unit/test_app_wiring.py` | test (app construction) | n/a | `tests/unit/test_logging.py:38-59` | exact |
| `tests/e2e/test_barrier_admission.py` | test (e2e, seeded rows) | request-response | `tests/e2e/test_isolation.py` | exact |
| `tests/e2e/test_barrier_wire_contract.py` | test (e2e, raw transport) | request-response | `tests/e2e/test_error_cases.py:50-82` | exact |
| `tests/e2e/test_startup_assertion.py` | test (e2e, lifespan) | batch / startup | `tests/e2e/test_health.py:1-11` | role-match |
| `tests/e2e/test_audit_writer.py` | test (e2e, row read-back) | CRUD | `tests/e2e/conftest.py:66-89` + `test_isolation.py:12-17` | role-match |
| `tests/e2e/test_challenge_store.py` | test (e2e, atomicity) | CRUD | `tests/schema/test_constraints.py:41-46` + `tests/e2e/conftest.py:66-89` | role-match |

### Modified files

| Modified file | What changes | Decision | In-file pattern to preserve |
|---------------|--------------|----------|------------------------------|
| `src/nativespeaker/api/app/main.py` | `docs_url=None/redoc_url=None/openapi_url=None`; `app.router.redirect_slashes = False`; barrier added **before** logging mw | D-03, D-04, Pitfalls 3+6 | keep the existing `# ty: ignore[invalid-argument-type]` comment convention at line 42-44 |
| `src/nativespeaker/api/app/dependencies.py` | add `get_linked_identity` / `get_preauth_identity` / `get_request_context`; delete `get_current_user`, `require_quota`, `get_subscription_service` | D-02, D-16 | keep `get_config`/`get_db` verbatim (lines 16-27) |
| `src/nativespeaker/api/app/errors.py` | delete `_STATUS_REMAP` + `_CODE_MAP`; register the generalized registry handlers | D-09, D-12 | keep `register_exception_handlers(app)` name and the four-handler registration order (lines 77-81) |
| `src/nativespeaker/api/app/lifespan.py` | drop `create_apple_verifier` + `firebase_admin` + `FirebaseService`; add keyring validation, enumeration assertion, challenge-store / audit-writer / budget construction | D-14, D-19, D-22 | keep the `app.state.X = ...` assignment shape and the ordered comment banners (lines 25-48) |
| `src/nativespeaker/api/config.py` | add `HmacConfig` + `AppConfig.hmac`; delete `AppleConfig`, `AppConfig.apple`, `AppConfig.quotas`, and the `SubscriptionPlan` import | D-20, D-16 | keep `BaseConfig`/`EnvironmentConfig` split and `SecretStr` usage |
| `config/config.yaml` | add `hmac:` block; delete `apple:` and `quotas:` blocks | D-20 | two-space YAML nesting, keys unquoted |
| `.env.example` | remove `APPLE_CERTS_DIR` | RESEARCH § Runtime State Inventory | — |
| `src/nativespeaker/api/models/users.py` | `User` → v2.0 seven columns; delete `UsageMonthly` | D-14 | keep `DateTimeType = cast(Any, DateTime(timezone=True))` idiom (line 10) |
| `src/nativespeaker/api/models/api.py` | delete `ErrorResponse` (moves to `errors.py`) and `UserProfileResponse` | D-09/D-10, D-16 | — |
| `src/nativespeaker/api/models/__init__.py` | rewrite `__all__` + imports | D-16 | keep `__all__`-first ordering (lint gate `I` requires it) |
| `src/nativespeaker/api/database/__init__.py` | drop `SubscriptionDB`, `UsageDB`, `UsersDB` | D-16 | same |
| `src/nativespeaker/api/routers/__init__.py` | drop `users_router`, `webhooks_router` | D-16 | same |
| `src/nativespeaker/api/services/__init__.py` | drop `FirebaseService`, `SubscriptionService`, `UserService`, `create_apple_verifier` | D-16 | same |
| `src/nativespeaker/api/routers/chats.py` | `Depends(get_current_user)` → `Depends(get_linked_identity)`; drop `dependencies=[Depends(require_quota)]` | D-15 | keep every `summary=`/`description=` kwarg — they are the OpenAPI contract |
| `src/nativespeaker/api/services/chats.py` | `create_chat(user: User)` / `send_message(user: User)` → `user_id: UUID` | RESEARCH § boot-repair | keep `raise <ServiceError subclass>` sites, retargeted at the new registry |
| `src/nativespeaker/api/routers/health.py` | **untouched** — only its registry declaration is added | RESEARCH Open Q2 | do not "fix" the bare `JSONResponse` return |
| `tests/e2e/conftest.py` | **extend**: add `seed_identity(state, user_active)`, add `stub_verifier`, repair `create_chat` | D-17 | never replace `_db_transaction` (lines 66-89) |
| `tests/unit/conftest.py` | narrow: drop `TEST_USER`, `mock_usage_db`, `webhook_client`, `get_current_user`/`require_quota` overrides | D-18 | keep the ephemeral-RSA block (lines 40-123) verbatim — the stub verifier reuses it |
| `tests/unit/test_auth_security.py`, `tests/unit/test_exception_handlers.py` | narrow to what survives | D-18 | — |
| `tests/e2e/test_error_cases.py`, `test_chats.py`, `test_chat_queries.py`, `test_isolation.py` | narrow | D-18 | — |

### Deleted files (no analog needed)

`src/nativespeaker/api/auth.py` (→ `auth/verification.py`) · `src/nativespeaker/api/exceptions.py` (→ `errors.py`) ·
`routers/webhooks.py` · `routers/users.py` · `services/subscriptions.py` · `services/users.py` · `services/firebase.py` ·
`database/subscriptions.py` · `database/usage.py` · `database/users.py` · `models/subscriptions.py` ·
`tests/unit/test_usage.py` · `tests/unit/test_subscriptions.py` · `tests/unit/test_webhooks.py` · `tests/e2e/test_users.py`

---

## Pattern Assignments

### `src/nativespeaker/api/auth/__init__.py` (package barrel)

**Analog:** `src/nativespeaker/api/models/__init__.py` (identical shape in `routers/`, `services/`, `database/`)

**Barrel pattern** (`models/__init__.py:1-18`) — `__all__` first, alphabetized, then absolute imports.
Ruff's `I` rule is on (`pyproject.toml:68 select = ["E","W","F","I","UP"]`) so import order is enforced:

```python
__all__ = [
    "AnalyzeInput", "AnalyzeResponse", "Chat", "ChatRequest", "ChatResponse", "ChatRole",
    ...
]

from nativespeaker.api.models.api import (
    ChatRequest,
    ChatResponse,
    ...
)
from nativespeaker.api.models.chats import Chat, ChatRole, Message
```

Smaller variant with the one-line form (`database/__init__.py:1-6`):

```python
__all__ = ["ChatsDB", "SubscriptionDB", "UsageDB", "UsersDB"]

from nativespeaker.api.database.chats import ChatsDB
```

**Note (RESEARCH § Runtime State Inventory):** `nativespeaker/` and `nativespeaker/api/` are implicit
namespace packages with **no** `__init__.py`; every subpackage (`models/`, `database/`, `routers/`,
`services/`) has one. `auth/` needs an explicit `__init__.py`, and the editable install must be
re-run so `packages.find` (`pyproject.toml:47-49`) discovers the new subpackage.

---

### `src/nativespeaker/api/auth/verification.py` (verifier, request-response)

**Analog:** `src/nativespeaker/api/auth.py` — this *is* the file, moved and extended. Copy it verbatim,
then layer `§1.2` on top. Do not rewrite.

**Whole current module** (`auth.py:1-61`) — the parts that survive unchanged:

```python
from dataclasses import dataclass
from typing import Protocol

import jwt
from jwt import PyJWKClient

from nativespeaker.api.exceptions import AuthenticationError   # ← retargets to nativespeaker.api.errors


class TokenVerifier(Protocol):
    def verify(self, token: str) -> UserIdentity:
        """Decode token and return user identity. Raise AuthenticationError on failure."""
        ...


class JWTVerifier:
    """Verifies RS256-signed JWTs using JWKS-fetched signing keys."""

    def __init__(self, *, jwks_url: str, audience: str, issuer: str,
                 leeway: int = 30, cache_ttl_seconds: float = 3600):
        self._jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=cache_ttl_seconds)
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway
        # Warm up JWKS cache — crashes startup if endpoint unreachable (fail-fast)
        self._jwks_client.get_signing_keys()
```

**Verification core to keep** (`auth.py:41-61`) — note `algorithms=["RS256"]` and the `require` list are
already exactly what `§1.2` and the ASVS V2 row demand; `tests/unit/test_jwt_security.py` pins them:

```python
    def verify(self, token: str) -> UserIdentity:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(token,
                                 signing_key,
                                 algorithms=["RS256"],
                                 audience=self._audience,
                                 issuer=self._issuer,
                                 leeway=self._leeway,
                                 options={"require": ["exp", "iat", "aud", "iss", "sub"]})
        except Exception as exc:
            raise AuthenticationError(f"Token verification failed: {exc}") from None

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Missing sub claim")
```

**What changes:** the non-empty-`sub` check already exists (lines 54-56). Add issuer pinning to the one
configured Firebase integration and a bounded-reason return rather than an exception, because the
barrier **returns** rather than raises (D-01). The `UserIdentity` dataclass moves to `context.py`.

**Call sites to retarget** (D-23):
`app/lifespan.py:10` · `app/dependencies.py:8` · `database/users.py:5` (deleted) · `services/users.py:3`
(deleted) · `tests/unit/conftest.py:21` · `tests/unit/test_users.py:10` · `tests/unit/test_exception_handlers.py:150`

---

### `src/nativespeaker/api/auth/wire.py` (utility, transform)

**Analog:** `src/nativespeaker/api/resilience.py:13-35` — the only module-level pure-predicate pair in the
codebase. Same shape: private `_`-prefixed helpers, positive early returns, no class.

**Module-level pure helper pattern** (`resilience.py:13-35`):

```python
def _extract_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    ...
    return False
```

**StrEnum pattern for `BoundedReason`** (`models/chats.py:13-15`; same in `models/subscriptions.py:10-26`):

```python
class ChatRole(StrEnum):
    human = "human"
    ai = "ai"
```

Members are `lower_snake` and the value repeats the name verbatim — hold that for `BoundedReason`, whose
members become audit `details.failure` and metric labels.

**Anti-pattern this file replaces** (`app/dependencies.py:51-58`) — the `Header(None)` path that silently
takes the first duplicate (RESEARCH Pitfall 1). It is deleted this phase:

```python
async def get_current_user(request: Request,
                           authorization: str | None = Header(None),
                           db: AsyncSession = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
```

---

### `src/nativespeaker/api/auth/context.py` (typed value objects)

**Analog:** `src/nativespeaker/api/auth.py:10-14` — the codebase's one frozen dataclass.

**Frozen value-object pattern** (`auth.py:10-14`):

```python
@dataclass(frozen=True, slots=True)
class UserIdentity:
    sub: str
    email: str
    name: str | None = None
```

Use `frozen=True, slots=True` for `LinkedIdentity`, `PreAuthIdentity`, `RouteMetadata` and
`RequestContext`. `RequestContext` must carry, per D-02: identity variant, route metadata record,
canonical client-IP bucket kind, the single captured evaluation time, the attempt id.

---

### `src/nativespeaker/api/auth/barrier.py` (middleware, request-response)

**Analog:** `src/nativespeaker/api/logs.py:57-76` — the only middleware in the repo. **Partial match**: it is a
`BaseHTTPMiddleware`, and RESEARCH § Summary rules the barrier must be pure ASGI. Copy the
*registration* and *structlog* conventions from it, not the base class.

**Existing middleware** (`logs.py:57-76`) — what the barrier sits directly beneath:

```python
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid.uuid4()),
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        if request.url.path not in _EXCLUDED_PATHS:
            log_method = logger.info if response.status_code < 400 else logger.error
            log_method("request", status_code=response.status_code, duration_ms=duration_ms)

        return response
```

Two consequences the planner must carry (RESEARCH Pitfall 2): this class calls
`clear_contextvars()` on the way *in*, so anything the barrier binds below it is fine for the barrier's
own security log but invisible to the `"request"` line; and it never sees the barrier's contextvars.
Carry request-scoped data on `scope["state"]` instead.

**`app.state` access pattern to copy — but per request, never in `__init__`** (`app/dependencies.py:16-21`):

```python
def get_config(request: Request) -> AppConfig:
    return request.app.state.config


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    async with request.app.state.session_factory() as session:
```

The barrier's ASGI equivalent is `scope["app"].state.session_factory` read inside `__call__`
(RESEARCH Pitfall 5 — caching it breaks `tests/e2e/conftest.py:66-89` rollback isolation).

**Registration + the `ty` ignore convention** (`app/main.py:42-44`) — reuse the comment shape if `ty`
complains about the new class:

```python
# ty cannot match a BaseHTTPMiddleware subclass against Starlette's
# _MiddlewareFactory ParamSpec protocol; this is the documented usage.
app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]
```

**No analog exists for:** pure-ASGI `__call__(scope, receive, send)`, `route.matches(scope)` resolution,
or awaiting a `Response` against `(scope, receive, send)`. Use `35-RESEARCH.md` § Pattern 1 and
§ Pattern 2 verbatim — both were executed against this repo's `.venv`.

---

### `src/nativespeaker/api/auth/registry.py` (declarative table + startup validator)

**Analog A — module-level declarative table:** `src/nativespeaker/api/app/errors.py:22-42`. This is the exact
shape `§2.2` wants, and also the table D-12 deletes; the registry inherits the *form*, not the content.

```python
_STATUS_REMAP: dict[int, int] = {
    405: 400,
    406: 400,
    409: 400,     # ← the live collision with challenge_required; D-12 deletes this table
    ...
}

_CODE_MAP: dict[int, str] = {
    400: "invalid_request",
    401: "unauthorized",
    ...
}
```

**Analog B — HTTP metadata declared on the class, read by one consumer:** `exceptions.py:14-21`. If a
`RouteMetadata` dataclass feels heavy, this is the established alternative:

```python
class ServiceError(Exception):
    """Base exception for service layer errors."""
    status_code: int = 500
    error_code: ErrorCode = "internal_error"
    log_level: int | None = None
```

**Analog C — fail-closed startup validation:** `config.py:100-109` is the codebase's one
"validate at load, raise to abort boot" hook:

```python
    @model_validator(mode="after")
    def load_config(self):
        config_path = self.config_dir / self.config_filename
        ...
        self.app_config = AppConfig(**yaml_data, ...)
        return self
```

and `app/lifespan.py:20-23` is the abort site the enumeration assertion joins:

```python
    config = EnvironmentConfig().app_config
    if config is None:
        raise RuntimeError("Configuration failed to load")
```

**The eight routes that must be declared** (RESEARCH Pitfall 4 — REBIND-01 lands here). Read off the real
router after D-04 and D-16:

```
GET    /                     GET    /chats            GET    /chats/{chat_id}
POST   /chats                POST   /chats/{chat_id}  DELETE /chats/{chat_id}
GET    /examples             GET    /health/ready
```

Declare `route.path` byte-identically (`/chats/{chat_id}`, not `/chats/{chat_id:uuid}`) and do **not**
synthesize `HEAD` (RESEARCH Pitfall 7). `GET /health/ready` is the only `public` member; the other seven
are `authenticated`, all with `operation=None, preauth_callable=False, challenge_bearing=False,
named_verifier=None`.

---

### `src/nativespeaker/api/auth/identity.py` (database accessor, CRUD read)

**Analog:** `src/nativespeaker/api/database/chats.py:38-47` — the codebase's one two-table join, and the
closest thing to `§1.3`'s single query.

**Join + `col()` + `.first()` pattern** (`database/chats.py:10-24, 38-47`):

```python
class ChatsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_chat(self, chat_id: UUID, user_id: UUID) -> Chat | None:
        statement = (
            select(Chat)
            .options(selectinload(Chat.messages))  # type: ignore[invalid-argument-type]
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        )
        return (await self.session.exec(statement)).first()

    async def get_messages(self, chat_id: UUID, user_id: UUID) -> list[Message]:
        statement = (
            select(Message)
            .join(Chat, col(Message.chat_id) == col(Chat.id))
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
            .order_by(col(Message.id).desc())
        )
        return list((await self.session.exec(statement)).all())
```

Note the `col(...)` wrapping on every comparison — that is the v1.6 convention introduced by commit
`fea82ad "types: use col() and cast for library interop"`; `ty check src` is a phase gate, and bare
attribute comparisons in `.where()` are what that commit fixed.

**The pattern this file replaces** (`database/users.py:14-24`) — JIT provisioning, deleted per
RESEARCH § State of the Art; the barrier never creates:

```python
    async def get_or_create(self, identity: UserIdentity) -> User:
        stmt = (
            pg_insert(User)
            .values(jwt_sub=identity.sub, email=identity.email, name=identity.name)
            .on_conflict_do_nothing(index_elements=["jwt_sub"])
        )
```

**Target query:** `35-RESEARCH.md` § Code Example 2. `identity_state != active` must use `!=` (not
`in (…)`) and `user.active is not True` (not `not user.active`) so NULL and future enum values fail
closed. Both `account_unavailable` branches leave the same single query — that is the whole of D-13.

---

### `src/nativespeaker/api/auth/audit.py` (database writer, append)

**Analog A — session-in-init class with a write that reports success:** `database/subscriptions.py:18-22, 61-80`:

```python
class SubscriptionDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert_event_idempotent(self, subscription_id: UUID, event_type: str,
                                      notification_uuid: str, ...) -> bool:
        """Insert subscription event if not duplicate. Returns True if inserted, False if duplicate."""
        stmt = (
            pg_insert(SubscriptionEvent)
            .values(subscription_id=subscription_id, event_type=event_type, ...)
            .on_conflict_do_nothing(index_elements=["notification_uuid"])
        )
        result = await self.session.exec(stmt)
        return result.rowcount > 0
```

This is the shape for **in-transaction mode** — the caller's `AsyncSession` arrives as a parameter and the
writer never commits.

**Analog B — own-session lifecycle for standalone-durable mode:** `app/dependencies.py:20-27`:

```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

D-19: the audit writer's standalone mode opens exactly this, from the **same** `session_factory`
attribute, read per call (Pitfall 5). Under the e2e fixture's `join_transaction_mode="create_savepoint"`
that `commit()` releases a savepoint, so the row is visible to a session on the same connection and
still rolls back.

**Row shape and its CHECKs** — `migrations/20260818_01_initial-release.sql:641-680`. Two constraints the
writer must satisfy structurally:

```sql
    CHECK (
        (result = 'invalid_external_jwt'
            AND actor_issuer IS NULL AND actor_subject_hash IS NULL
            AND actor_subject_hash_key_version IS NULL AND actor_provider IS NULL)
        OR
        (result <> 'invalid_external_jwt'
            AND actor_issuer IS NOT NULL AND actor_subject_hash IS NOT NULL
            AND actor_subject_hash_key_version IS NOT NULL)
    ),
```

and the six-key `details` shape (migration lines 662-668): `schema_version` (number), `context`,
`verification`, `resolved`, `mutation`, `failure` (all objects). RESEARCH Pitfall 10: an
`internal_error` or `preauth_identity_not_allowed` row **must** populate the three actor fields from the
already-verified `(issuer, subject)`, leaving `actor_provider` NULL.

**Structured-log companion** (`app/errors.py:12, 45-54`) — the writer's security log reuses this:

```python
logger = structlog.get_logger()

_LEVEL_TO_METHOD = {logging.DEBUG: "debug", logging.INFO: "info", ...}

    if exc.log_level is not None:
        method_name = _LEVEL_TO_METHOD.get(exc.log_level, "error")
        log_method = getattr(logger, method_name)
        log_method(str(exc), error_type=type(exc).__name__, ...)
```

---

### `src/nativespeaker/api/auth/challenges.py` (database store, atomic conditional update)

**Analog:** `src/nativespeaker/api/database/usage.py:16-35` — **the strongest analog in the repository**.
`UsageDB.try_increment` is already exactly the "one conditional `UPDATE` with `RETURNING`, decide by
affected rows" idiom `§6.1` requires, in this project's own ORM style:

```python
class UsageDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def try_increment(self, user_id: UUID, month: str, monthly_quota: int) -> bool:
        """Atomically increment usage if under quota. Returns True if allowed."""
        await self.session.exec(
            pg_insert(UsageMonthly)
            .values(id=uuid7(), user_id=user_id, month=month, used=0)
            .on_conflict_do_nothing(index_elements=["user_id", "month"])
        )

        result = await self.session.exec(
            update(UsageMonthly)
            .where(col(UsageMonthly.user_id) == user_id,
                   col(UsageMonthly.month) == month,
                   col(UsageMonthly.used) < monthly_quota)
            .values(used=col(UsageMonthly.used) + 1)
            .returning(col(UsageMonthly.used))
        )
        return result.first() is not None
```

Copy the structure verbatim; this file is deleted this phase, so the idiom must survive here.
Imports to copy (`database/usage.py:1-8`):

```python
from uuid import UUID, uuid7

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
```

**Two deviations from the analog** (`35-RESEARCH.md` § Pattern 7, executed against the live table):

1. Use `len(result.all()) == 1` rather than `result.first() is not None`, so a multi-row match is a
   detectable bug rather than a silent success.
2. The claim's `WHERE` carries **both** `claimed_at IS NULL` and `expires_at > now` — the only place
   expiry is ever evaluated. Consume sets `consumed_at` and clears `preauth_subject_hash` in **one**
   `UPDATE`; two statements trip the table CHECK at migration lines 626-634.

Statements: `35-RESEARCH.md` § Code Example 5.

---

### `src/nativespeaker/api/auth/keys.py` (config model + crypto utility)

**Analog A — `SecretStr` field with a derived accessor:** `config.py:19-31`:

```python
class DatabaseConfig(BaseModel):
    host: str = Field(description="Database server hostname")
    ...
    password: SecretStr = Field(description="Database password")
    pool_size: int = Field(default=5, ge=1, description="Connection pool size")

    @property
    def url(self) -> str:
        return (f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
                f"@{self.host}:{self.port}/{self.name}")
```

Every field carries `description=`; numeric bounds use `ge=`/`gt=`/`le=`. `HmacConfig.active_version`
gets `ge=1, le=32767` because `audit.auth_events.actor_subject_hash_key_version` is `SMALLINT`
(migration line 655).

**Analog B — `model_validator(mode="after")` that raises to abort:** `config.py:100-109` (shown under
`registry.py` above). D-22's active-key check goes here: missing/empty active version raises; a missing
*older* version only logs a warning.

**Analog C — derived enum/type constant pinned at module level:** `config.py:11`:

```python
LogLevel = StrEnum("LogLevel", {k: k for k in logging.getLevelNamesMapping()})
```

Pin the domain-separation prefixes the same way, as module-level `bytes` literals so they cannot drift:
`b"actor-subject:v1:"` and `b"idp-account:v1:"` (RESEARCH Pitfall 8).

**Config-file shape to add** (`config/config.yaml:16-19` shows the existing two-space nesting):

```yaml
jwt:
  jwks_cache_ttl_seconds: 3600
chats_limit: 50
messages_limit: 50
```

RESEARCH Pitfall 9: `AppConfig(**yaml_data, ...)` at `config.py:106` ranks `init_settings` above
`env_settings`, so anything the YAML declares cannot be overridden by env. Document that; the Secret
Manager follow-up must *remove* the YAML entries, not shadow them.

---

### `src/nativespeaker/api/auth/budgets.py` (in-process counter, metering)

**Analog:** `src/nativespeaker/api/resilience.py:38-70` — the codebase's one in-process counter with a
threshold and an exhaustion exception.

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_seconds: int):
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._failure_count = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            ...
            retry_after = max(1, int(self._reset_seconds - elapsed))
            raise CircuitOpenError(retry_after)
```

**Secondary analog — check-then-reserve with a non-destructive first step:** `resilience.py:81-93`:

```python
    @asynccontextmanager
    async def _inflight_slot(self):
        try:
            token = self._slots.get_nowait()
        except asyncio.QueueEmpty as exc:
            raise QueueFullError(self._retry_after_seconds) from exc
```

**Deviation `§7.1` requires (D-06):** the budget gate must **check every applicable budget
non-destructively first**, increment nothing unless all have capacity, then charge them together —
broadest to narrowest. That is stricter than `CircuitBreaker.before_call`, which mutates on the way past.
Interface: `35-RESEARCH.md` § Pattern 6. Foundation ships only the mechanism plus the
`adapter_firebase_lookup` name with its 3-attempt budget; exhaustion maps to internal
`firebase_lookup_unavailable` → client `verification_temporarily_unavailable`.

Note `CircuitBreaker` uses an `asyncio.Lock`; a per-request budget object carried on the request context
does not need one — it is not shared across requests.

---

### `src/nativespeaker/api/auth/adapters.py` (interface declarations, no implementations)

**Analog:** `src/nativespeaker/api/auth.py:17-20` — the codebase's one `Protocol`:

```python
class TokenVerifier(Protocol):
    def verify(self, token: str) -> UserIdentity:
        """Decode token and return user identity. Raise AuthenticationError on failure."""
        ...
```

Result types follow the frozen-dataclass pattern (`auth.py:10-14`) and the `StrEnum` pattern
(`models/chats.py:13-15`). **Hard rule (`§7.1`, RESEARCH § Pattern 8):** not one `firebase_admin` import
in this module — foundation calls `get_user_provider_data` zero times. `tests/unit/test_adapter_interfaces.py`
asserts the absence.

---

### `src/nativespeaker/api/errors.py` (error registry, package root — D-10)

**Analog A — the class metadata it absorbs:** `exceptions.py:1-21`. `ErrorCode` and `ServiceError` move
here; `unauthorized` is deleted from the `Literal` set (D-11):

```python
ErrorCode = Literal["invalid_request",
                    "validation_error",
                    "unauthorized",          # ← D-11 deletes this member
                    "not_found",
                    "service_unavailable",
                    "internal_error",
                    "quota_exceeded",
                    "out_of_scope"]


class ServiceError(Exception):
    """Base exception for service layer errors."""
    status_code: int = 500
    error_code: ErrorCode = "internal_error"
    log_level: int | None = None

    def extra_headers(self) -> dict[str, str] | None:
        return None
```

**Business classes that keep their code and status verbatim** (`§8.3`, D-09) — the full surviving set,
with the lines to copy: `UnsupportedLanguageError` 400/`invalid_request` (24-32) ·
`AnalysisError` 500/`internal_error` (35-39) · `TransientLLMError` 503/`service_unavailable` (42-47) ·
`PermanentLLMError` 503/`service_unavailable` (50-55) · `InvalidChatError` 404/`not_found` (58-64) ·
`InvalidCursorError` 400 (67-72) · `PageSizeLimitError` 400 (75-81) · `QueueFullError` 503 (84-93) ·
`CircuitOpenError` 503 (96-105) · `QuotaExceededError` 429/`quota_exceeded` (108-110) ·
`ChatHistoryLimitError` 400 (113-119) · `OutOfScopeError` 400/`out_of_scope` (122-127) ·
`DatabaseNotInitializedError` 500 (146-153).
Deleted with their surfaces: `AuthenticationError` (130-137, replaced by `auth_required`) and
`WebhookVerificationError` (140-143, deleted with `routers/webhooks.py`).

**The `extra_headers` seam is load-bearing** (`exceptions.py:92-93`) — `rate_limited` (D-07) and any 405
class need it, and `tests/unit/test_exception_handlers.py:182-201` asserts `Retry-After` today:

```python
    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}
```

**Analog B — the single data-driven handler that survives, generalized** (`app/errors.py:45-54`):

```python
async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        method_name = _LEVEL_TO_METHOD.get(exc.log_level, "error")
        log_method = getattr(logger, method_name)
        log_method(str(exc), error_type=type(exc).__name__,
                   exc_info=(exc.log_level >= logging.ERROR))
    return JSONResponse(status_code=exc.status_code,
                        content=ErrorResponse(code=exc.error_code).model_dump(),
                        headers=exc.extra_headers())
```

**Analog C — the response model that moves here** (`models/api.py:10-11`):

```python
class ErrorResponse(BaseModel):
    code: ErrorCode
```

The one-key body is asserted in four places (`tests/unit/test_error_contract.py:43-47`,
`test_exception_handlers.py:81`, `tests/e2e/test_error_cases.py:42-47`) — `list(body.keys()) == ["code"]`.
Do not add fields.

**What the registry must delete** (`app/errors.py:22-32, 62-69`) — D-12:

```python
_STATUS_REMAP: dict[int, int] = {405: 400, 406: 400, 409: 400, ...}

async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = _STATUS_REMAP.get(exc.status_code, exc.status_code)
    if status not in _CODE_MAP:
        status = 500
```

Replace with a closed `dict[int, ErrorClass]` and a lifespan self-check (RESEARCH § Pattern 4:
every status has exactly one class, no two classes share a code, a miss logs
`error_registry_unmapped_status` at ERROR and returns `internal_error`). Preserve the
`headers=getattr(exc, "headers", None)` pass-through at line 69 — that is how the 405's `Allow` header
survives.

**`ErrorResponse` import sites to retarget:** `app/main.py:9` (and its `responses={}` block at 25-33,
which must lose the `401: "Unauthorized"` entry per D-11) · `app/errors.py:10` · `models/__init__.py:12`.

---

### `src/nativespeaker/api/models/identities.py` and `models/auth.py` (models)

**Analog:** `src/nativespeaker/api/models/subscriptions.py:29-52` — native PostgreSQL enum binding plus
table args. This is the v1.6 convention CONTEXT § Established Patterns names.

**Enum-type + table pattern** (`models/subscriptions.py:10-14, 29-32, 35-53`):

```python
class SubscriptionStatus(StrEnum):
    active = "active"
    ...

SubscriptionPlanType = cast(Any, Enum(SubscriptionPlan, name='subscription_plan', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_provider_active", "user_id", "provider",
              unique=True,
              postgresql_where=text("status NOT IN ('expired', 'revoked')")),
        {"schema": "core"}
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", index=True)
    provider: SubscriptionProvider = Field(sa_type=SubscriptionProviderType)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```

The simple single-dict form is `models/users.py:14-15`:

```python
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}
```

For `AuthEvent` the schema is `"audit"`, not `"core"` — no existing model uses the `audit` schema, so
that is the one novel detail.

**Enums to declare, from the applied migration:**
`core.identity_provider` = `('anonymous','google','apple')` (line 56) ·
`core.identity_state` = `('active','historical')` (line 57) ·
`core.auth_operation` (lines 59-69) · `core.auth_event_result` (lines 89-133).

**`User` repair target** (`migrations/20260818_01_initial-release.sql:150-158`) — seven columns; `email`
is nullable on purpose (migration comment lines 148-149):

```sql
CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    registered_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Current `models/users.py:17-23` carries `jwt_sub`, `name`, `subscription_plan` and no `updated_at` /
`registered_at` — that mismatch is the `UndefinedColumnError` D-14 repairs.

`core.external_identities` is migration lines 206-242; `core.auth_challenges` is 575-635;
`audit.auth_events` is 641-680.

---

### Test files

#### `tests/unit/test_app_wiring.py` (D-03, D-04)

**Analog:** `tests/unit/test_logging.py:38-59` — builds a minimal app, adds the middleware, asserts
behaviour:

```python
@pytest.fixture
def _logging_app():
    """Minimal FastAPI app with RequestLoggingMiddleware for testing."""
    app = FastAPI()
    # See app/main.py: ty cannot match BaseHTTPMiddleware subclasses against
    # Starlette's _MiddlewareFactory ParamSpec protocol.
    app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]

    @app.get("/test")
    async def test_route():
        return {"ok": True}
```

Assert against the **real** app (`from nativespeaker.api.app.main import app as real_app`, the import
`tests/unit/test_error_contract.py:7` already uses) that
`[m.cls.__name__ for m in real_app.user_middleware] == ["RequestLoggingMiddleware", "AuthBarrierMiddleware"]`
(outermost first — RESEARCH Pitfall 3) and that no `/docs`, `/redoc`, `/openapi.json` route is registered.

#### `tests/unit/test_route_registry.py` and `test_error_registry.py` (FOUND-03, FOUND-04)

**Analog A — introspecting the real app** (`tests/unit/test_error_contract.py:55-71`):

```python
class TestOpenAPISchema:
    """ERR-04: ErrorResponse in OpenAPI, no 422."""

    def test_openapi_schema_has_422(self):
        """Every route with a request body should have a 422 response."""
        schema = real_app.openapi()
        for path, methods in schema.get("paths", {}).items():
```

Careful: with `openapi_url=None` (D-04), `real_app.openapi()` still works as a method call, but every
assertion in `TestOpenAPISchema` that depends on the enum contents must be updated for D-11
(`CONTRACT_CODES` at lines 9-11 lists `unauthorized`).

**Analog B — the parametrized exception→status matrix** (`tests/unit/test_exception_handlers.py:29-46, 76-89`):

```python
CASES = [
    ("missing_token", AuthenticationError("Missing Bearer token"), 401),
    ...
    ("starlette_http", StarletteHTTPException(status_code=404, detail="not found"), 404),
]

@pytest.mark.parametrize("name,exc,expected_status", CASES)
def test_handler(handler_client, name, exc, expected_status):
    response = handler_client.get(f"/raise/{name}")
    assert response.status_code == expected_status
    body = response.json()
    assert list(body.keys()) == ["code"], f"Expected only 'code' key, got {list(body.keys())}"
```

with the route-per-case factory at lines 53-73:

```python
def _make_raise_route(exc: Exception):
    async def _route():
        raise exc
    return _route

@pytest.fixture(scope="module")
def handler_client():
    app = FastAPI()
    register_exception_handlers(app)
    for name, exc, _ in CASES:
        app.add_api_route(f"/raise/{name}", _make_raise_route(exc), methods=["GET"])
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
```

Extend `CASES` with the seven foundation classes; **delete** `test_wrong_method_returns_400`
(`test_error_contract.py:31-35`) — D-12 makes it 405.

**Analog C — exact-set inventory assertions** (`tests/schema/test_inventory.py:66-70`) is the closest
precedent for `§2.3`'s two-direction set equality: capture the expected set as a module-level literal and
assert equality, reporting each difference separately.

#### `tests/unit/test_hmac_keys.py` (FOUND-05, D-21, D-22)

**Analog:** `tests/unit/test_config.py:36-96` — writes YAML into a tempdir and loads through the real
config machinery, plus the `_DOTENV_KEYS` scrub that this project needs because `pytest-dotenv` loads
`.env`:

```python
_DOTENV_KEYS = ["CONFIG_DIR"]

def test_main_config_loads_yaml_and_content():
    yaml_content = """..."""
    tmp_dir = tempfile.mkdtemp()
    try:
        Path(tmp_dir, "config.yaml").write_text(yaml_content)
        ...
        env_clean = {k: v for k, v in os.environ.items() if k not in _DOTENV_KEYS}
        with patch.dict(os.environ, env_clean, clear=True):
            # _env_file is declared on BaseSettings.__init__, but ty sees only the
            # __init__ synthesised from the model fields.
            config = EnvironmentConfig(config_dir=Path(tmp_dir),
                                       _env_file=None)  # ty: ignore[unknown-argument]
    finally:
        shutil.rmtree(tmp_dir)

def test_main_config_missing_file():
    ...
        with pytest.raises(FileNotFoundError):
```

The `_env_file=None  # ty: ignore[unknown-argument]` line is mandatory boilerplate — copy it.
Also copy the `pytest.raises(ValidationError)` form at lines 31-33 for the D-22 active-key abort.

#### `tests/unit/test_barrier_wire_contract.py`, `test_challenge_ids.py`, `test_audit_details.py`

**Analog:** `tests/unit/test_jwt_security.py:19-47` — class-grouped, one-behaviour-per-test, docstring
naming the requirement id:

```python
class TestAlgorithmSecurity:
    def test_rejects_alg_none(self, verifier):
        """AUTH-07: alg:none tokens must be rejected."""
        ...
        with pytest.raises(AuthenticationError):
            verifier.verify(token)
```

**Wire-contract trap (RESEARCH Pitfall 1, bonus):** a hand-built scope in a unit test does **not**
lowercase header keys — `Headers(raw=[(b"Authorization", ...)])` returns `None` from
`.get("authorization")`. Build scopes with lowercase byte keys, or go through a real client.

#### `tests/unit/test_identity_accessors.py` (FOUND-01 fail-loudly)

**Analog:** `tests/unit/test_auth_security.py:16-34` — an app wired with the *real* dependency chain and a
route that consumes it:

```python
@pytest.fixture(scope="module")
def dep_client():
    """Client with real auth dependency chain for testing Bearer token edge cases."""
    app = FastAPI()
    register_exception_handlers(app)
    app.state.jwt_verifier = make_test_verifier()
    app.dependency_overrides[get_db] = lambda: mock_db

    @app.get("/protected")
    async def _protected(user: User = Depends(get_current_user)):
        return {"user_id": str(user.id)}
```

For the accessors, the point is the *inverse*: register the route **without** the barrier and assert the
`Depends(get_linked_identity)` call fails as `auth_required` — never returns `None`.

#### `tests/e2e/*` — module conventions (mandatory)

**Analog:** `tests/e2e/test_health.py:1-11` — the whole file is the convention:

```python
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestHealthEndpoint:
    async def test_health_ready_returns_up(self, async_client):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "up"}
```

`pytestmark = pytest.mark.e2e` at module level **and** `@pytest.mark.asyncio(loop_scope="module")` on
every class — the `_app_lifespan` fixture is module-scoped (`tests/e2e/conftest.py:44-48`) and omitting
`loop_scope` binds the wrong event loop.

**Unauthenticated / raw-transport client** (`tests/e2e/test_error_cases.py:50-61`) — the analog for
`test_barrier_wire_contract.py`, because `async_client` always carries a Bearer header:

```python
@pytest.mark.asyncio(loop_scope="module")
class TestUnauthenticatedAccess:
    async def test_no_auth_header_returns_401(self, _app_lifespan):
        """Request without Authorization header returns 401 unauthorized."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "unauthorized"   # ← becomes auth_required (D-11)
```

**Seeded-row test using the rollback factory** (`tests/e2e/test_isolation.py:1-17`) — the analog for
`test_barrier_admission.py` and `test_audit_writer.py`:

```python
import pytest

from e2e.conftest import create_chat

pytestmark = pytest.mark.e2e

OTHER_USER = "other-user-not-in-firebase"


@pytest.mark.asyncio(loop_scope="module")
class TestCrossUserIsolation:
    async def test_cannot_read_other_user_chat(self, async_client, _db_transaction):
        chat_id = await create_chat(_db_transaction, OTHER_USER)
        response = await async_client.get(f"/chats/{chat_id}")
```

`_db_transaction` yields the swapped factory — assertions must read rows back **through it**, never
through a fresh engine.

---

## Shared Patterns

### The rollback fixture the whole e2e strategy depends on

**Source:** `tests/e2e/conftest.py:66-89`
**Apply to:** every e2e module, and — by implication — the barrier, audit writer and challenge store,
which must read `session_factory` per request rather than caching it.

```python
@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _db_transaction(_app_lifespan):
    """Wrap each test in a transaction that rolls back on completion."""
    original_factory = _app_lifespan.state.session_factory

    # async_sessionmaker stores bind in its kw dict
    engine = original_factory.kw["bind"]

    async with engine.connect() as connection:
        transaction = await connection.begin()

        test_factory = async_sessionmaker(
            bind=connection,
            class_=SQLModelAsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        _app_lifespan.state.session_factory = test_factory
        try:
            yield test_factory
        finally:
            _app_lifespan.state.session_factory = original_factory
            await transaction.rollback()
```

**Extend, do not replace.** Add `seed_identity(factory, *, state, user_active)` alongside `create_chat`
(lines 92-120) and a `stub_verifier` fixture that swaps `app.state.jwt_verifier`. `create_chat` itself is
broken today — line 104 builds `User(jwt_sub=user_id, ...)`, which no longer exists — and must seed
`core.users` **plus** a matching `core.external_identities` row.

### `app.state` construction and fail-closed startup

**Source:** `src/nativespeaker/api/app/lifespan.py:18-53`
**Apply to:** the challenge store, audit writer, budget gate, HMAC keyring, and the enumeration assertion.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    config = EnvironmentConfig().app_config
    if config is None:
        raise RuntimeError("Configuration failed to load")
    app.state.config = config

    # Setup logging
    setup_logging(log_level=config.log_level)

    # Initialize database
    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
    app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)

    # Initialize token verifiers
    app.state.jwt_verifier = JWTVerifier(jwks_url=config.jwt.jwks_url, ...)
    ...
    logger.info("started", model=config.model.name, ...)
    yield

    # Shutdown
    await db_engine.dispose()
```

Every subsystem is a `app.state.<name> = <constructor>(...)` line under a `#` banner comment. Lines 34
(`create_apple_verifier`) and 46-48 (`firebase_admin.initialize_app` + `FirebaseService`) are deleted,
as is line 56 (`firebase_admin.delete_app`). `EnvironmentConfig()` raising is already the fail-closed
precedent for D-22 and the `§2.3` assertion.

### Session-in-init database classes

**Source:** `database/chats.py:10-13`, `database/usage.py:11-14`, `database/subscriptions.py:18-21` — all
three identical
**Apply to:** `auth/identity.py`, `auth/challenges.py`, `auth/audit.py` (in-transaction mode)

```python
class ChatsDB:

    def __init__(self, session: AsyncSession):
        self.session = session
```

`from sqlmodel.ext.asyncio.session import AsyncSession` — never SQLAlchemy's `AsyncSession` directly, and
never `text()`. The audit writer is the one deviation: it also needs a standalone mode that opens its own
session from `app.state.session_factory`.

### `Depends()`-only route signatures

**Source:** `src/nativespeaker/api/routers/chats.py:13-22`
**Apply to:** the D-02 accessors, and to `routers/chats.py`'s own repair

```python
@router.get("/chats",
            response_model=list[ChatResponse],
            summary="List chats",
            description="Returns all chat sessions belonging to the authenticated user.")
async def list_chats(user: User = Depends(get_current_user),
                     service: ChatService = Depends(get_chat_service)):
    chats = await service.list_chats(user.id)
```

Default-value `Depends()` (not `Annotated[...]`), one dependency per line, and `summary=`/`description=`
on every route. `dependencies=[Depends(require_quota)]` at lines 43 and 60 is deleted (D-15).

### Error raising from services

**Source:** `src/nativespeaker/api/services/chats.py:53-61, 70-75`
**Apply to:** every `raise` site retargeted at `nativespeaker.api.errors`

```python
        resolved_mode = llm_response.get("resolved_mode")
        if resolved_mode == "reject":
            raise OutOfScopeError()
        ...
        if lang and lang not in self.supported_languages:
            raise UnsupportedLanguageError(lang, self.supported_languages)
```

Handlers never build a status code; the exception class carries it. The barrier is the deliberate
exception — it **returns** the registry's response object (D-01), because middleware added via
`add_middleware` sits outside Starlette's `ExceptionMiddleware`.

### Structured logging

**Source:** `src/nativespeaker/api/logs.py:14`, `app/errors.py:12`, `app/lifespan.py:15`
**Apply to:** the barrier's security log and the audit writer

```python
logger = structlog.get_logger()
...
logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size)
```

Module-level `logger`, snake_case event name as the first positional argument, everything else as
keywords. Test with `structlog.testing.capture_logs` (`tests/unit/test_logging.py:63-72`).

### Lint / type gate conventions

**Source:** `pyproject.toml:63-68` (`line-length = 120`, `target-version = "py314"`, `select = ["E","W","F","I","UP"]`)

- Alphabetized `__all__` before imports in every `__init__.py`.
- `col(...)` around SQLModel column comparisons in `.where()` clauses (commit `fea82ad`).
- `cast(Any, ...)` for SQLAlchemy type objects assigned to module constants (`models/chats.py:18-19`).
- Suppressions are narrow and carry a why-comment: `# ty: ignore[invalid-argument-type]`
  (`app/main.py:42-44`), `# type: ignore[invalid-argument-type]` (`database/chats.py:21`).

Both gates are green today and are a phase gate: `.venv/bin/ruff check src tests && .venv/bin/ty check src`.

---

## No Analog Found

| File / concern | Role | Data Flow | Reason | Use instead |
|----------------|------|-----------|--------|-------------|
| `auth/barrier.py` — pure-ASGI `__call__(scope, receive, send)` | middleware | request-response | The repo's only middleware is a `BaseHTTPMiddleware` (`logs.py:57`) | `35-RESEARCH.md` § Pattern 1 |
| `auth/barrier.py` — `route.matches(scope)` resolution before dispatch | middleware | request-response | Nothing in the repo introspects the router at request time | `35-RESEARCH.md` § Pattern 2 (verified against `.venv`) |
| `auth/barrier.py` — awaiting a `Response` against `(scope, receive, send)` | middleware | request-response | Every existing error path raises; none returns | `35-RESEARCH.md` § Pattern 1 |
| `auth/registry.py` — `enumerate_registered(app)` / `assert_route_enumeration` | startup validator | batch | No startup assertion exists; `app/lifespan.py:20-23` is the closest fail-closed precedent | `35-RESEARCH.md` § Code Example 3 |
| `auth/keys.py` — `hmac.new(key, msg, hashlib.sha256)` derivation | crypto utility | transform | No HMAC anywhere in `src/` today (`tests/schema/test_constraints.py:37-38` only uses fixed byte literals) | `35-RESEARCH.md` § Code Example 4 |
| `auth/challenges.py` — `secrets.token_bytes(16)` + base64url-unpadded handle | utility | transform | No CSPRNG handle generation exists; ids are `uuid7()` | `35-RESEARCH.md` § Standard Stack |
| `models/auth.py` — a SQLModel table in the `audit` schema | model | n/a | Every existing model is `{"schema": "core"}` | `models/subscriptions.py:35-45` shape with `"audit"` substituted |
| Concurrency test for challenge claim atomicity | test (e2e) | CRUD | No test in the repo runs concurrent writers | `35-RESEARCH.md` § Pattern 7 (executed against the live table) |

---

## Cross-Cutting Notes for the Planner

1. **`config.py` imports `SubscriptionPlan`** (`config.py:9`, used at lines 64 and 83). Deleting
   `models/subscriptions.py` breaks config import, which breaks *everything*. Order the plan so the
   config edit and the model deletion land together.
2. **`models/__init__.py:34` re-exports `UsageMonthly`**, and `database/__init__.py:5` re-exports
   `UsageDB`. Barrel files must change in the same commit as the module deletions or the package will not
   import.
3. **`tests/unit/conftest.py:126-132` defines `TEST_USER` at module scope** with `jwt_sub` and
   `subscription_plan`. It is evaluated at *collection* time, so it breaks the entire unit suite the
   moment `User` is repaired — not just the tests that use it.
4. **`tests/unit/conftest.py:40-123`** (the ephemeral RSA keypair, `make_token`, `_FixedKeyVerifier`) is
   the exact machinery the e2e `stub_verifier` fixture needs. Import it rather than duplicating; note
   `tests/e2e/*` currently imports from `e2e.conftest` (`test_isolation.py:3`) and `tests/unit/*` from
   `unit.conftest` (`test_auth_security.py:13`) — `pythonpath = ["."]` in `pyproject.toml:53` makes both
   work.
5. **`app/main.py:25-33`'s `responses={}` block** documents `401: "Unauthorized"`. D-11 retires that code;
   the block needs the same edit as the `Literal` set, and `tests/unit/test_error_contract.py:9-11`
   asserts the enum contents.
6. **`k8s/templates/backend-traffic-policy.yaml:53`** emits `'{"code":"quota_exceeded"}'` on a 429 where
   `§3.2` wants `rate_limited`. D-08 forbids touching `k8s/` this phase — record it as a known accepted
   inconsistency, not a task.
7. **Re-run the editable install** after `auth.py` → `auth/` so setuptools `packages.find`
   (`pyproject.toml:47-49`) picks up the new subpackage;
   `src/ns_api_gateway.egg-info/SOURCES.txt` still lists `exceptions.py`.

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/**` (all 30 modules), `tests/unit/**`, `tests/e2e/**`,
`tests/schema/**`, `config/`, `migrations/`, `pyproject.toml`
**Files scanned:** 66 Python files (6,119 lines total), 1 migration, 1 config YAML, 1 pyproject
**Files read in full:** 34
**Pattern extraction date:** 2026-08-20
**Source of truth:** working tree on `gsd/phase-34-schema` @ `f5815fd`. `.planning/codebase/*.md` was
deliberately not consulted (stale, pre-rename).
