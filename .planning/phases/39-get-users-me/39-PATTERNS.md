# Phase 39: GET /users/me - Pattern Map

**Mapped:** 2026-09-01
**Files analyzed:** 17 (5 new, 12 modified)
**Analogs found:** 17 / 17 (every file has an in-repo analog; none is a greenfield shape)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/routers/users.py` **(new)** | router | request-response | `src/nativespeaker/api/routers/root.py` (router-level narrowing) + `routers/auth.py:77-86` (`sync` handler body) | exact (split across two) |
| `src/nativespeaker/api/crud/purchases.py` **(new)** | crud / repository | read-only query + fail-closed raise | `src/nativespeaker/api/crud/grants.py:32-57` | exact |
| `src/nativespeaker/api/schemas/auth.py` (edit) | schema | value type | `schemas/auth.py:50-63` (`Entitlement` + `SyncResponse`) | exact (same file) |
| `src/nativespeaker/api/errors.py` (edit) | error class | n/a | `errors.py:213-220` (`MissingUsageRowError`) | exact |
| `src/nativespeaker/api/app/dependencies.py` (edit) | provider/accessor | request-scoped construction | `app/dependencies.py:111-114` (`get_sync_service`) — **not** `get_challenge_store` (see Correction 1) | exact |
| `src/nativespeaker/api/routers/__init__.py` (edit) | barrel export | n/a | `routers/__init__.py:1-7` | exact (same file) |
| `src/nativespeaker/api/crud/__init__.py` (edit) | barrel export | n/a | `crud/__init__.py:1-6` | exact (same file) |
| `src/nativespeaker/api/app/main.py` (edit) | config / wiring | n/a | `app/main.py:10-16, 43-47` | exact (same file) |
| `tests/unit/test_users_me.py` **(new)** | test (route unit) | request-response | `tests/unit/test_challenge_endpoint.py:64-119` | exact |
| `tests/unit/test_purchases_crud.py` **(new)** | test (crud unit) | read query | `tests/unit/test_identities_crud.py:24-70` + `tests/unit/test_sync_resolver.py:106-150` | exact (split across two) |
| `tests/e2e/test_users_me.py` **(new)** | test (e2e) | request-response | `tests/e2e/test_sync.py` (whole file) | exact |
| `tests/e2e/conftest.py` (edit) | test fixture | file-scoped seeding | `tests/e2e/conftest.py:171-192` (`seed_identity`) + `:219-249` (`seed_grant`) | exact (same file) |
| `tests/unit/test_rejection_vocabulary.py` (edit) | ratchet test | n/a | `tests/unit/test_rejection_vocabulary.py:34-82, 104-118` | exact (same file) |
| `tests/unit/test_app_wiring.py` (edit) | ratchet test | n/a | `tests/unit/test_app_wiring.py:39-48` | exact (same file) |
| `tests/unit/test_error_contract.py` (edit) | ratchet test | n/a | `tests/unit/test_error_contract.py:60-93` | exact (same file) |
| `AGENTS.md` (edit) | convention doc | n/a | `AGENTS.md` § "Package layout" (:24-47) | exact (same file) |
| `.planning/REQUIREMENTS.md` (edit) | planning doc | n/a | `.planning/REQUIREMENTS.md:201-209` (Phase 38 amendment block) | exact (same file) |

---

## Pattern Assignments

### `src/nativespeaker/api/routers/users.py` (router, request-response) — NEW

**Primary analog:** `src/nativespeaker/api/routers/root.py` (whole file, 22 lines) — this is the
**only** router in `src/` that both declares the narrowing at router level *and* re-declares it at
route level. D-08 asks for exactly this. `routers/auth.py::sync` supplies the handler *body* shape.

**Router-level narrowing** — `routers/root.py:3-17` (verbatim):
```python
from fastapi import APIRouter, Depends

from nativespeaker.api.app.dependencies import get_chat_service, get_linked_identity
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.services import ChatService

# Router-level auth protects an endpoint added later whose own Depends is forgotten; the same callable runs once.
router = APIRouter(tags=["root"], dependencies=[Depends(get_linked_identity)])


@router.get("/",
            summary="API information",
            description="Returns API name, version, and supported languages.")
async def root(identity: Identity = Depends(get_linked_identity),
               service: ChatService = Depends(get_chat_service)):
```
Copy: the module-level `router = APIRouter(tags=[...], dependencies=[Depends(get_linked_identity)])`,
and the one-line comment justifying the double declaration. The double declaration is *deliberate and
already proven safe* — `tests/unit/test_app_wiring.py:88-157` asserts one verify + one query for a
doubly-declared route, because FastAPI's dependency cache keys on the callable.

**Handler body + typed return** — `routers/auth.py:76-86` (verbatim):
```python
# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/sync",
             response_model=SyncResponse,
             summary="Report the caller's entitlement and registration state",
             description="Reads the caller's effective grant, the current period's usage and the "
                         "stored registration state. Nothing is written.")
async def sync(identity: Identity = Depends(get_linked_identity),
               service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Report what the caller's account entitles it to at this request's instant."""
    entitlement = await service.read_entitlement(identity.user.id)
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
```
Copy: `response_model=` + `summary=` + `description=`, a one-line docstring, the `identity.user.id` /
`identity.identity.provider` detached reads, and the single-expression typed return.
**Do not copy** `routers/auth.py:44-45`'s `evaluated_at = datetime.now(UTC)` — CONTEXT.md
§ Established Patterns: this endpoint reads no clock.

**Module docstring** — `routers/auth.py:1-2` is the register to imitate (two lines, names what the
routes are, nothing else). `routers/root.py` has none; either is in-bar.

**`Cache-Control` precedent** — `routers/auth.py:56-59` (verbatim):
```python
    # `no-store` rather than `no-cache`: the handle is a secret, and a revalidatable copy is a copy.
    return JSONResponse(content=PrepareResponse(challenge_id=challenge_id, expires_at=expires_at)
                        .model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})
```
This is the *header value* precedent and the comment register — **but D-09 explicitly rejects the
`JSONResponse` mechanism** (it loses the typed return and the `response_model` OpenAPI entry). Use an
injected `starlette.responses.Response` and set `response.headers["Cache-Control"] = "no-store"`.
`Response` is already imported in `routers/auth.py:8` alongside `JSONResponse`, so the import path
(`from starlette.responses import Response`) is settled by precedent.

**Import block convention** — `routers/auth.py:3-31`: stdlib, blank, third-party, blank, then
absolute `nativespeaker.api.*` imports sorted by module, with parenthesised multi-name imports.
Never relative inside `src/`.

---

### `src/nativespeaker/api/crud/purchases.py` (crud, read-only query + fail-closed raise) — NEW

**Analog:** `src/nativespeaker/api/crud/grants.py` (session-in-`__init__`, no-lock read).
**Secondary analog:** `src/nativespeaker/api/crud/identities.py:27-51` (a `crud/` method that raises
its own rejections — `AGENTS.md` § Package layout exception 4).

**Module docstring + imports** — `crud/grants.py:1-8` (verbatim):
```python
"""Entitlement reads over `core.access_grants`. Global lock order: grant rows ascending by id, then usage rows."""
from datetime import datetime
from uuid import UUID

from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.tables import AccessGrant, AccessGrantStatus, AccessTier, UserMonthlyUsage
```
Note the table import comes from the **barrel** `nativespeaker.api.tables`, which already exports
`PurchaseProvider` and `StorePurchaseToken` (`tables/__init__.py:7, 41-44`) — no barrel edit needed.
(`crud/identities.py:18` imports from `tables.purchases` directly; the barrel is the majority form.)

**Session-in-`__init__` + no-lock read** — `crud/grants.py:32-35, 44-48, 55-57` (verbatim):
```python
class GrantsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def read_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Return every effective grant for `user_id` at `evaluated_at`, ascending by id, taking no lock."""
        statement = _effective_grants_statement(user_id, evaluated_at)
        return list((await self.session.exec(statement)).all())

    async def read_usage(self, grant_id: UUID) -> UserMonthlyUsage | None:
        """Return `grant_id`'s usage row, or `None`, taking no lock."""
        return (await self.session.exec(_usage_statement(grant_id))).first()
```
Copy: `__init__(self, session: AsyncSession)` storing `self.session`; `(await self.session.exec(stmt)).all()`
for a multi-row read; a one-line docstring per method that names the return **and** says "taking no lock"
where that is the point. **Do not copy `ChallengesDB`** (`app/lifespan.py:28` builds one long-lived
instance that takes a session per method) — research Pattern 3 flags it as the exception.

**Predicate style** — `crud/grants.py:11-29` factors statements into module-level `_x_statement()`
helpers with their own docstrings, and uses `col(Table.column) == value` (never bare `Table.column ==`).
`crud/identities.py:30-33, 55-57` builds statements inline in the method. Both are in-repo; the
`col(...)` wrapper is non-negotiable in both. One read with no locking sibling makes the inline form
defensible (research Pattern 4).

**Fail-closed raise inside `crud/`** — `crud/identities.py:36-50` (verbatim):
```python
        if row is None:
            # Identity rows are never deleted, so no row can only mean this pair was never linked.
            if allow_preauth:
                return Identity(issuer=issuer, subject=subject)
            raise PreAuthIdentityNotAllowed

        identity, user = row
        if user is None:
            # A broken link is unresolvable state: fail closed rather than read it as an unlinked pair.
            raise IdentityUnresolvable
        # Positive tests, so a NULL or any future enum member fails closed on these same two branches.
        if identity.identity_state != IdentityState.active:
            raise HistoricalIdentity
        if user.active is not True:
            raise BlockedUser
```
Copy: the guard-then-raise shape, and the one-line comment that states *why the branch fails closed*
rather than what the code does. D-07's check (`set(PurchaseProvider) - set(tokens)`) earns exactly one
such comment: completeness, never emptiness.

**Never mint here** — `crud/identities.py:88-93` is the only mint site in the repo and stays so:
```python
            # One per store, minted eagerly. A fresh `uuid4()` derived from nothing, so it correlates nothing.
            for store in PurchaseProvider:
                self.session.add(StorePurchaseToken(user_id=user.id,
                                                    provider=store,
                                                    identity_value=str(uuid4()),
                                                    created_at=evaluated_at))
```
This is the loop `crud/purchases.py` is the read-side mirror of — same `for store in PurchaseProvider`
totality, opposite direction.

**Table shape** — `tables/purchases.py:10-14, 28-31` (verbatim):
```python
class PurchaseProvider(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_provider` -- exactly two values."""
    apple = "apple"
    google_play = "google_play"
...
    user_id: UUID = Field(foreign_key="core.users.id", primary_key=True)
    provider: PurchaseProvider = Field(sa_type=PurchaseProviderType, primary_key=True)
    # Deliberately not `unique=True`: the table's rule is the composite UNIQUE (provider, identity_value).
    identity_value: str = Field()
```

---

### `src/nativespeaker/api/errors.py` (error class, edit)

**Analog:** `errors.py:213-231` — `MissingUsageRowError` and `MultipleEffectiveGrantsError`, the two
neighbours the new class sits between. Insert after `UnknownTierError` (`:234-243`) to keep the
service-arm block contiguous.

**Verbatim template** (`errors.py:213-231`):
```python
class MissingUsageRowError(InternalError):
    """An effective grant with no `core.user_monthly_usage` row."""
    # Never minted here: that would turn a detectable broken invariant into a silent free allowance.
    log_level = logging.ERROR

    def __init__(self, grant_id: UUID):
        self.grant_id = grant_id
        super().__init__(f"Grant {grant_id} has no core.user_monthly_usage row")


class MultipleEffectiveGrantsError(InternalError):
    """More than one effective grant for one user."""
    # A unique index makes this unreachable; asserted so dropping it fails loudly, never tie-breaks.
    log_level = logging.ERROR

    def __init__(self, count: int, user_id: UUID):
        self.count = count
        self.user_id = user_id
        super().__init__(f"{count} effective grants for user {user_id}; refusing to tie-break")
```
Copy exactly: `InternalError` base, one-line docstring naming the broken invariant, one-line comment
justifying non-repair, `log_level = logging.ERROR`, `__init__` storing each argument on `self` then
one `super().__init__(f"...")` message naming the identifiers. **Declare neither `status` nor `code`**
— inherited from `errors.py:131-136`:
```python
class InternalError(AppError):
    """The generic 500: the service failed and the client is told nothing more."""
    status = 500
    code = "internal_error"
    log_level = None
    answers_framework_status = True
```
Declaring either would trip `tests/unit/error_tree.py`'s together-or-neither rule.

**`log_fields()` is not overridden** — the base returns `{}` (`errors.py:50-52`). None of the three
id-carrying siblings overrides it, so `user_id` and the missing providers reach the *message* (and
thus the traceback and the log's `event`/`exc_info`), never a structured field. That is what keeps
D-06 consistent with the scalars-only ratchet at
`tests/unit/test_rejection_vocabulary.py:138-141`.

**How the class earns its one ERROR line** — `app/error_handlers.py:33-44`; no `logger.error(...)` is
ever written in `crud/`:
```python
async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Record the failure once, then answer with the status and code its class declared."""
    assert isinstance(exc, AppError)
    if exc.log_level is not None:
        level = exc.log_level if exc.log_level in _LOGGABLE else logging.ERROR
        record = getattr(logger, logging.getLevelName(level).lower())
        record(camel_to_snake(type(exc).__name__),
               exc_info=(exc.log_level >= logging.ERROR), **exc.log_fields())
    return JSONResponse(status_code=exc.status,
                        content=ErrorResponse(code=exc.code).model_dump(),
                        headers=exc.extra_headers())
```
Event name will be `missing_purchase_token_error` (`camel_to_snake`, `error_handlers.py:26-30`).

---

### `src/nativespeaker/api/schemas/auth.py` (schema, edit)

**Analog:** `schemas/auth.py:50-63` — the nested-block-plus-top-level-field pair D-01 mirrors:
```python
class Entitlement(BaseModel):
    """The entitlement block: the grant, its tier allowance, and the current period's usage."""
    type: EntitlementType
    status: EntitlementStatus
    tier_id: str | None
    monthly_credits: int | None
    current_period: str
    monthly_used: int


class SyncResponse(BaseModel):
    """The sync body: the entitlement and the registration state, and nothing else."""
    entitlement: Entitlement
    identity_provider: IdentityProvider
```
Copy: the block model declared immediately above the response model; docstring form
*"The X body: <fields>, and nothing else."* — the closing clause is the codebase's way of recording a
closed payload (D-01) and appears on four models in this file (`:18, 24, 31, 61`). Place the new pair
after `SyncResponse` (`:63`) and before the `Identity` dataclass (`:66`).

**Field typing** — `identity_provider: IdentityProvider` exactly as `SyncResponse:63` and
`CompletionResponse:32` do (Pitfall 4: never `PurchaseProvider`, never `str`).
`purchase_tokens: dict[PurchaseProvider, str]` needs a new import from
`nativespeaker.api.tables.purchases` beside the existing `:8-9` table imports.
**`email` and `display_name` are both `str | None`** — `tables/users.py:17-18` declares both nullable
(`email` "left NULL otherwise", `display_name` never populated this milestone). The optional-field
precedent in this file is `Entitlement.tier_id: str | None` (`:54`).

---

### `src/nativespeaker/api/app/dependencies.py` (accessor, edit)

**Correction 1 — the analog is `get_sync_service`, not `get_challenge_store`.** The research prompt
names `get_challenge_store` (`:90-92`), but that accessor reads a *lifespan-built singleton* off
`request.app.state` and takes a session per method call. `PurchasesDB` follows `GrantsDB`: it binds
the **request** session in `__init__`. The correct analog is therefore `dependencies.py:111-114`
(verbatim):
```python
def get_sync_service(db: AsyncSession = Depends(get_db)) -> SyncService:
    return SyncService(db=db,
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC))
```
Copy: `def get_x(db: AsyncSession = Depends(get_db)) -> X: return X(db)`, no docstring (this accessor
has none, and neither do `get_quota_service`/`get_chat_service`/`get_auth_service`). **Drop the
`evaluated_at` argument and its comment** — this endpoint reads no clock.

**Placement rule** — `dependencies.py:74` (verbatim comment):
```python
# Defined below the dependencies it declares, because its `Depends()` defaults are evaluated at definition time.
```
`get_purchases_db` must appear after `get_db` (`:22`). Appending at end of file (after `:114`) is
safest and matches the file's append-only growth.

**Import to add** — `from nativespeaker.api.crud.purchases import PurchasesDB`, matching the existing
per-module crud imports at `:11-12` (`crud.challenges`, `crud.identities`), not the barrel.

**Why this accessor exists at all** — `dependencies.py:89` records the same justification for the
challenge pair, and is the sentence to echo in the plan's rationale:
```python
# These two accessors exist so a challenge-bearing route can stay Depends()-only and never take Request itself.
```

---

### `src/nativespeaker/api/routers/__init__.py` + `crud/__init__.py` (barrel exports, edit)

Both are literal `__all__` lists in alphabetical order followed by one import per line, alphabetical.

`routers/__init__.py:1-7` (verbatim):
```python
__all__ = ["auth_router", "chats_router", "examples_router", "health_router", "root_router"]

from nativespeaker.api.routers.auth import router as auth_router
from nativespeaker.api.routers.chats import router as chats_router
```
→ add `"users_router"` last in `__all__`; add
`from nativespeaker.api.routers.users import router as users_router` last.

`crud/__init__.py:1-6` (verbatim):
```python
__all__ = ["ChallengesDB", "ChatsDB", "GrantsDB", "IdentitiesDB"]

from nativespeaker.api.crud.challenges import ChallengesDB
```
→ `"PurchasesDB"` sorts after `"IdentitiesDB"`; import line likewise last.

---

### `src/nativespeaker/api/app/main.py` (wiring, edit)

`app/main.py:10-16` and `:42-47` (verbatim):
```python
from nativespeaker.api.routers import (
              auth_router,
              chats_router,
              examples_router,
              health_router,
              root_router,
)
...
# Each router declares its own auth dependency; health declares none, being the whole public allowlist.
app.include_router(root_router)
app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
```
Note the unusual continuation indentation in the import block — match it rather than reformatting.
`include_router` order is **not** alphabetical (root, auth, chats, examples, health); append
`app.include_router(users_router)` before `health_router` or after it — either keeps the comment true.
`register_exception_handlers(app)` (`:48`) must stay last-but-one, before `add_middleware` (`:50`).

---

### `tests/unit/test_users_me.py` (test, route unit) — NEW

**Analog:** `tests/unit/test_challenge_endpoint.py` — the only unit file that mounts a **real router**
on a bare `FastAPI()` and overrides the barrier.

**The client fixture** — `test_challenge_endpoint.py:74-88` (verbatim):
```python
@pytest.fixture
def client(store, session, fake_firebase_adapter):
    """The real auth router, with the barrier's context supplied and app state substituted."""
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    identity = Identity(issuer=TEST_ISSUER, subject=UNLINKED_SUBJECT)
    app.dependency_overrides[get_identity] = lambda: identity
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
```
Copy exactly, substituting `users_router`, `get_linked_identity` and `get_purchases_db`.
`raise_server_exceptions=False` is required for the 500 case to render through the shared handler.
A ready-made linked `Identity` exists at `tests/unit/conftest.py:103-114` (`TEST_IDENTITY`) but its
`User` sets only `id` and `active` — a local `Identity` carrying `email` and `display_name` is needed.

**Recording double** — `test_challenge_endpoint.py:31-61`:
```python
class _RecordingChallengeStore:
    """Records what the route asked of the store, and answers the minimum needed to observe issuance."""

    def __init__(self) -> None:
        self.issued: list[str] = []

    async def issue(self, session, *, operation, identity, now):
        self.issued.append(str(operation))
        return ISSUED_HANDLE, ISSUED_EXPIRY
...
class _RecordingSession:
    """Records what it was asked, so a query on any arm of this route would be visible."""

    def __init__(self) -> None:
        self.statements: list[object] = []

    async def exec(self, statement):
        self.statements.append(statement)
        return _EmptyResult()

    async def commit(self):
        raise AssertionError("no path in this module may commit")
```
Copy the `_Recording*` naming, the `self.statements` list (this is how D-03's "exactly one query" is
asserted), and the `raise AssertionError` on forbidden methods.

**`Cache-Control` assertion** — `test_challenge_endpoint.py:115-119` (verbatim):
```python
    def test_the_issued_handle_is_not_cacheable(self, client):
        """`no-store` and not `no-cache`: a revalidatable copy of a secret handle is still a copy."""
        response = client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.headers["cache-control"] == "no-store"
```
Lowercase header key, equality not containment.

**Whole-body / key-set assertion** — `test_challenge_endpoint.py:110-111`:
```python
        # The key set, not two known keys: a third field would pass the weaker check.
        assert set(response.json()) == {"challenge_id", "expires_at"}
```
This is the executable form of D-01's closed payload; pair it with a full `response.json() == {...}`
equality as `tests/e2e/test_sync.py:101-110` does.

**Parametrised invariance** — `test_challenge_endpoint.py:130-132` is the shape for the
client-signal-invariance cases (differing `User-Agent`, an `X-Platform` header, a `?platform=` query):
```python
    @pytest.mark.parametrize("operation", _NOT_ISSUABLE)
    def test_every_unissuable_string_is_the_same_refusal(self, client, operation):
```

---

### `tests/unit/test_purchases_crud.py` (test, crud unit) — NEW

**Analog A (stub + direct crud call):** `tests/unit/test_identities_crud.py:24-70` (verbatim):
```python
class _StubResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _StubSession:
    """Stands in for the one short session the barrier opens, and keeps what it was asked to run."""

    def __init__(self, row=None):
        self._row = row
        self.statements = []

    @property
    def executed(self) -> int:
        return len(self.statements)

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._row)
```
For a multi-row read the result double needs `.all()` — `tests/unit/test_sync_resolver.py:35-45`:
```python
class _StubResult:
    """Both accessor shapes the service uses, over one row list."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None
```
**Pitfall 7 applies:** do **not** copy `test_sync_resolver.py:77-80`'s
`statement.column_descriptions[0]["entity"]` dispatch. A two-column `select(...)` returns `Row`
tuples, so the stub must yield `(provider, identity_value)` tuples matching the production unpacking.

**Analog B (no-lock proof):** `tests/unit/test_sync_resolver.py:31-32, 106-108, 137-142` (verbatim):
```python
# The whole difference between the locking and the non-locking read, as PostgreSQL receives it.
LOCK_CLAUSE = " FOR UPDATE"
...
def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))
...
class TestSyncTakesNoLock:
    """Every statement sync issues is lock-free, which is the exact inverse of what the charge issues."""

    async def test_the_effective_grant_statement_takes_no_lock(self):
        session = await _happy_path()
        assert "FOR UPDATE" not in _compiled(session.statements[0])
```
(requires `from sqlalchemy.dialects import postgresql`). The same `_compiled` helper carries the
"reads no other table" assertion at `:206-209`, which is the template for proving D-03's *no second
`core.users` read*:
```python
    async def test_no_user_row_is_read_by_any_statement(self):
        """SHARED-INVARIANTS:33 forbids a user-row tier above the grants on any path, not just a swap."""
        session = await _happy_path()
        assert all("core.users" not in _compiled(s) for s in session.statements)
```

**Raise-assertion helper** — `test_identities_crud.py:67-70`:
```python
async def _rejected(row, expected: type[BaseException], *, preauth_callable: bool = False):
    """The rejecting half: resolution raises, and the raised instance is what the cases read."""
    session = _StubSession(row)
    with pytest.raises(expected) as caught:
```

**Test-class naming register** across both files: `class TestOutcomeFourLinkedAndActive:`,
`class TestTheZeroGrantAnswer:`, `class TestSyncTakesNoLock:` — full-sentence names, a docstring
stating the *rule* the class holds, and method names spelling the behaviour
(`test_a_grant_whose_window_closed_a_moment_ago_is_absent`).

---

### `tests/e2e/test_users_me.py` (test, e2e) — NEW

**Analog:** `tests/e2e/test_sync.py` — the direct precedent, same barrier, same fixtures.

**Header + marker** — `test_sync.py:1-17`:
```python
"""What `/auth/sync` answers over the real stack: the entitlement it holds, and the two absent states."""
...
from .conftest import seed_grant, seed_identity

pytestmark = pytest.mark.e2e
```
Every class then carries `@pytest.mark.asyncio(loop_scope="module")` (`:88, 113, 151, 189, 254, 270, 293`).

**Stored-column readback (criterion 2)** — `test_sync.py:71-76` (verbatim), reusable as-is for
`identity_provider`:
```python
async def _stored_provider(factory, issuer: str, subject: str):
    """The provider value actually on the row, read back rather than taken from the fixture's argument."""
    async with factory() as session:
        statement = select(ExternalIdentity.provider).where(col(ExternalIdentity.issuer) == issuer,
                                                            col(ExternalIdentity.subject) == subject)
        return (await session.exec(statement)).one()
```
and its use at `:258-267`:
```python
    async def test_a_non_google_caller_reports_its_stored_provider(
            self, async_client, _db_transaction, _app_config, test_user_id, apple_linked_identity):
        stored = await _stored_provider(_db_transaction, _app_config.jwt.issuer, test_user_id)
        # The happy-path fixture seeds google; a row equal to it would leave the case proving nothing.
        assert stored != IdentityProvider.google

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert response.json()["identity_provider"] == stored
```
The same shape reads back `core.store_purchase_tokens.identity_value` per provider.

**Unchanged-table-state (PROF-02 / "writes nothing")** — `test_sync.py:50-68` (verbatim):
```python
# `SELECT *`, not the mapped columns: access_grants carries four GENERATED ALWAYS columns the ORM leaves unmapped.
_GRANT_ROWS = text("SELECT * FROM core.access_grants WHERE user_id = :user_id ORDER BY id")
...
_USER_ROW = text("SELECT * FROM core.users WHERE id = :user_id")
_TABLE_COUNTS = text("SELECT (SELECT count(*) FROM core.access_grants),"
                     " (SELECT count(*) FROM core.user_monthly_usage),"
                     " (SELECT count(*) FROM core.users)")


async def _entitlement_snapshot(factory, user_id) -> dict:
    """Every column of the caller's grant, usage and user rows, plus the three whole-table counts."""
    async with factory() as session:
        params = {"user_id": user_id}
        return {"grants": [tuple(r) for r in (await session.execute(_GRANT_ROWS, params)).all()],
                "usage": [tuple(r) for r in (await session.execute(_USAGE_ROWS, params)).all()],
                "user": [tuple(r) for r in (await session.execute(_USER_ROW, params)).all()],
                "counts": tuple((await session.execute(_TABLE_COUNTS)).one())}
```
Phase 39's version swaps in
`SELECT * FROM core.store_purchase_tokens WHERE user_id = :user_id ORDER BY provider` plus
`core.users`, and keeps the whole-table counts. Call shape — `test_sync.py:193-202`:
```python
    async def test_a_current_period_grant_is_left_untouched(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_grant(_db_transaction, user_id=user.id, monthly_used=_CURRENT_USED)
        before = await _entitlement_snapshot(_db_transaction, user.id)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 200, response.text
        assert await _entitlement_snapshot(_db_transaction, user.id) == before
```

**Barrier 401/403 (D-08)** — `test_sync.py:270-290` (verbatim), the exact template:
```python
class TestTheRouteInheritsTheBarriersRejections:
    """Both rejections come from the existing dependencies; the route adds no handling and no exemption."""

    async def test_a_caller_with_no_credential_is_rejected(self, _app_lifespan):
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/auth/sync")

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_a_verified_but_unlinked_caller_is_rejected(self, _app_lifespan, stub_verifier):
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/auth/sync", headers={"Authorization": f"Bearer {make_token(sub=_UNLINKED_SUBJECT)}"})

        # Status and code read off the error class rather than guessed, so a renamed code fails here first.
        assert response.status_code == PreAuthIdentityNotAllowed.status
        assert response.json() == {"code": PreAuthIdentityNotAllowed.code}
```
Note: `async_client` must **not** be used for the no-credential case — `tests/e2e/conftest.py:99-104`
sets the `Authorization` header on it. `tests/e2e/test_unauthenticated_access.py:10-15` records the
same warning verbatim and offers an `unauthenticated_client` fixture as the alternative.

**Fail-closed 500 (criterion 4 / D-06)** — `test_sync.py:293-307` (verbatim):
```python
class TestTheFailClosedFiveHundred:
    """An effective grant whose usage row is missing answers an opaque 500, never the zero a brief would report."""

    async def test_a_grant_with_no_usage_row_is_an_opaque_500(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        # with_usage=False is the case the fixture's own comment says the parameter exists for.
        await seed_grant(_db_transaction, user_id=user.id, with_usage=False)

        response = await async_client.post("/auth/sync")

        assert response.status_code == 500
        # The whole body as a literal: an added detail field would name which condition tripped.
        assert response.json() == {"code": "internal_error"}
```
For `/users/me` the fail-closed case needs **no seeding at all** — `seed_identity` mints no tokens
(Pitfall 3), so the current `linked_firebase_identity` fixture already produces it.

---

### `tests/e2e/conftest.py` (test fixture, edit) — `seed_purchase_tokens`

**Analog:** `tests/e2e/conftest.py:171-192` (`seed_identity`) and `:219-249` (`seed_grant`) — both
module-level `async def seed_x(factory, *, ...)` helpers, keyword-only after `factory`, with defaults
that make the happy path the default and a flag for the broken-state case.

`seed_identity` (verbatim, `:171-192`):
```python
async def seed_identity(factory, *,
                        issuer: str,
                        subject: str,
                        identity_state: IdentityState = IdentityState.active,
                        user_active: bool = True,
                        provider: IdentityProvider = IdentityProvider.google):
    """Insert a core.users row and its matching core.external_identities row; return both."""
    # The table's CHECK ties the two together: provider_uid is NULL exactly for anonymous.
    provider_uid = None if provider is IdentityProvider.anonymous else f"{provider}-uid-{subject}"
    async with factory() as session:
        user = User(active=user_active)
        session.add(user)
        await session.flush()
        identity = ExternalIdentity(user_id=user.id, ...)
        session.add(identity)
        await session.commit()
    return user, identity
```
`seed_grant`'s `with_usage: bool = True` (`:228`) and its comment at `:230` are the precedent for a
partial-seed argument covering D-07's one-row-missing case:
```python
    """Insert a core.access_grants row and its core.user_monthly_usage row; return both."""
    # A grant with no usage row is a 500 rather than a 429, so with_usage=False is only for that case.
```
New helper signature per research:
`async def seed_purchase_tokens(factory, *, user_id: UUID, providers=PurchaseProvider)`.
Imports: `StorePurchaseToken` and `PurchaseProvider` are already exported by
`nativespeaker.api.tables` (`tables/__init__.py:7`), so extend the existing import list at `:17-29`.
`StorePurchaseToken.created_at` has **no default** (`tables/purchases.py:32`) — it must be passed,
unlike `AccessGrant`; `seed_grant:231`'s `now = datetime.now(UTC)` is the pattern.

A module-scoped `@pytest_asyncio.fixture(loop_scope="module")` wrapper follows
`linked_firebase_identity` (`:163-168`) / `quota_grant` (`:195-199`):
```python
@pytest_asyncio.fixture(loop_scope="module")
async def quota_grant(_db_transaction, linked_firebase_identity):
    """One effective grant plus its usage row for the seeded caller; without it a quota route answers 429."""
    user, _ = linked_firebase_identity
    return await seed_grant(_db_transaction, user_id=user.id)
```

---

### `tests/unit/test_rejection_vocabulary.py` (ratchet, edit) — **same commit as the error class**

Two literals, both hand-written. `:33-34, 54-56` (verbatim):
```python
# One entry per class in the tree.
EVENT_NAMES = frozenset({
...
    "missing_usage_row_error",
    "multiple_effective_grants_error",
    "unknown_tier_error",
```
→ add `"missing_purchase_token_error"` in the "service arms" block beside its three siblings.

`:103-110` (verbatim):
```python
# The arguments each class's own `__init__` insists on.
CONSTRUCTOR_ARGUMENTS: dict[type, tuple[tuple, dict]] = {
    errors_module.UnsupportedLanguageError: (("fr", ["en"]), {}),
    errors_module.ChatHistoryLimitError: ((), {"max_messages": 50}),
    errors_module.InvalidChatError: (("chat-id",), {}),
    errors_module.MissingUsageRowError: ((uuid7(),), {}),
    errors_module.MultipleEffectiveGrantsError: ((2, uuid7()), {}),
    errors_module.UnknownTierError: (("registered", uuid7()), {}),
```
→ add `errors_module.MissingPurchaseTokenError: ((uuid7(), [PurchaseProvider.apple]), {}),`
(needs a `PurchaseProvider` import). Without it `_sample()` (`:121-124`) falls back to a no-arg build
and `test_every_class_in_the_tree_contributes_only_scalars` (`:138-141`) raises `TypeError`.

The failing assertion if skipped — `:93-95`:
```python
    def test_the_tree_spells_exactly_the_recorded_event_names(self):
        derived = {camel_to_snake(cls.__name__) for cls in _production_family()}
        assert derived == EVENT_NAMES
```

---

### `tests/unit/test_app_wiring.py` (ratchet, edit)

**Do not touch the two literals** — `:10-12` (verbatim):
```python
# Literals rather than derived from anything, so widening the exemption is a visible edit here.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}
```
`/users/me` belongs in neither.

**The pair to extend** — `:39-48` (verbatim):
```python
    def test_the_sync_route_declares_the_linked_identity_narrowing(self):
        """Named rather than left to the generic case, which would also pass if sync were exempted."""
        declared = [_declared(route) for route in _api_routes() if route.path == "/auth/sync"]
        assert declared, "/auth/sync is not a registered route"
        assert all(get_linked_identity in calls for calls in declared)

    def test_the_sync_route_is_in_neither_exemption_set(self):
        """Sync is authenticated and narrowed, so widening either literal above would fail here."""
        assert "/auth/sync" in {route.path for route in _api_routes()}
        assert "/auth/sync" not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
```
Research recommendation (Open Question 1): parametrise this pair over `("/auth/sync", "/users/me")`
and rename to drop `the_sync_route`. The file's existing parametrise register is `:34-37` /
`test_error_contract.py:73-74`. Whichever shape, the docstrings above must be reworded — they name
sync explicitly.

Two assertions that pass **only if the narrowing is declared correctly** and need no edit —
`:27-31, 50-55`:
```python
    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   and get_linked_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"
...
    def test_the_public_allowlist_is_exactly_the_readiness_probe(self):
        unauthenticated = {route.path for route in _api_routes()
                           if get_linked_identity not in _declared(route)
                           and get_identity not in _declared(route)}
        assert unauthenticated == PUBLIC_PATHS
```

---

### `tests/unit/test_error_contract.py` (ratchet, edit)

**The helper and its three parametrise ids** — `:60-67, 73-74` (verbatim):
```python
def _id_carrying_cases():
    """The three classes that format server-side identifiers into their own message."""
    grant_id, user_id = uuid7(), uuid7()
    return [
        (MissingUsageRowError(grant_id), [str(grant_id)]),
        (MultipleEffectiveGrantsError(3, user_id), [str(user_id), "3"]),
        (UnknownTierError("a-private-tier-id", grant_id), ["a-private-tier-id", str(grant_id)]),
    ]
...
    @pytest.mark.parametrize("exc,secrets", _id_carrying_cases(),
                             ids=["missing_usage_row", "multiple_grants", "unknown_tier"])
```
→ add a fourth tuple and a fourth id; **the docstring says "The three classes"** and must be updated.
The three cases it feeds (`:75-93`) then cover D-06's redaction for free, including the control:
```python
    def test_the_premise_holds_and_each_message_really_names_its_identifiers(self, exc, secrets):
        """The control: without it the case above would pass on a class that stored nothing."""
        for secret in secrets:
            assert secret in str(exc)
```
`CONTRACT_CODES` (`:18-22`) is **not** edited — D-06 adds no `ErrorCode` member.

---

### `AGENTS.md` § "Package layout" (convention, edit)

**The text being amended** — `AGENTS.md:24-47`. The two lines D-05 touches (verbatim):
```
- `services/` — business logic: orchestration, rules, transaction boundaries.
- `crud/` — database access.
...
- `routers/` — HTTP handlers, `Depends()` only.
```
and the four numbered exceptions, each written as a rule plus a one-clause ground:
```
4. A fail-closed read may raise its own rejection, so the rejection stays with
   the query in `crud/`.
```
Register to copy: imperative, no hedging, ~70-char wrap, ground stated after a comma or a colon.
**`Depends()` only stays** (Pitfall 6) — the amendment removes the service requirement, not the
`Depends()`-only rule.

---

### `.planning/REQUIREMENTS.md` (planning doc, edit)

**Analog:** `.planning/REQUIREMENTS.md:200-209` — the Phase 38 amendment block, a blockquote nested
under the requirement bullet:
```
- [x] **SYNC-03**: ...
  > **Amended by Phase 38 (D-01/D-02), 2026-09-01 — the decision Phase 37.1 flagged forward is made here.** As written this requirement read *"..."*, and it carried ...
  >
  > **Option (b) was chosen, dated 2026-09-01. ...**
```
Format: `> **Amended by Phase NN (D-xx), YYYY-MM-DD — <one-clause summary>.**` then bolded lead
sentences per paragraph, `>` blank line between paragraphs. Append under **PROF-01** (`:213`) for
D-02's rate-limit omission and D-03's divergence from handler step 1; the existing PROF-02 amendment
block (`:215-217`) is left untouched.

---

## Shared Patterns

### Docstring and comment bar (applies to every new file)
**Source:** `AGENTS.md:3-22`, enforced by `tests/unit/test_docstring_bar.py:42-48`
```python
BASELINE: dict[str, int] = {
    "src": 0,
    "tests": 0,
    "tests/e2e": 0,
    "tests/schema": 0,
    "tests/unit": 0,
}
```
Every root is at **0 over-long docstrings** and must stay 0. Three lines maximum, measured on the
stripped body. Comments: one line each, only where they resolve a genuine ambiguity. Test *class*
docstrings are the one place the codebase spends a full sentence on rationale
(`test_sync_resolver.py:138`, `test_sync.py:191`) — still one line.

### `Depends()`-only routers
**Source:** `AGENTS.md:33`; `routers/root.py:16-17`, `routers/auth.py:39-42, 67-69, 82-83`
**Apply to:** `routers/users.py`
No router in `src/` constructs a DB class inline — every dependency arrives as a `Depends()` default.
Hence `get_purchases_db` in `app/dependencies.py`.

### Fail-closed raise lives with the query
**Source:** `AGENTS.md:46-47` (exception 4); `crud/identities.py:36-50`
**Apply to:** `crud/purchases.py`
Never a `try/except` in the router; never a `logger.error(...)` at the raise site.

### The shared error handler owns status, body and the log line
**Source:** `app/error_handlers.py:33-44, 76-81`
**Apply to:** `errors.py`, `crud/purchases.py`, `routers/users.py`
```python
def register_exception_handlers(app: FastAPI) -> None:
    # One entry covers every subclass: Starlette resolves a handler by walking `type(exc).__mro__`.
    app.add_exception_handler(AppError, app_error_handler)
```
Raise and stop. The body is `{"code": ...}` built from the class alone; the message never reaches it.

### Detached-row reads after the barrier's session closes
**Source:** `app/lifespan.py:34-36` (`expire_on_commit=False`); `routers/auth.py:85-86`
```python
    entitlement = await service.read_entitlement(identity.user.id)
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
```
**Apply to:** `routers/users.py` — `identity.user.email` / `identity.user.display_name` read the same
way (D-03). The e2e harness sets the same flag (`tests/e2e/conftest.py:125-130`), so e2e exercises it.

### Two enums that share the value `"apple"`
**Source:** `tables/identities.py` (`IdentityProvider`) vs `tables/purchases.py:10-14`
(`PurchaseProvider`)
**Apply to:** `schemas/auth.py`, `crud/purchases.py`, `errors.py`, every test
Annotate `identity_provider: IdentityProvider` and `purchase_tokens: dict[PurchaseProvider, str]`;
never construct one from the other's value (Pitfall 4).

### Whole-body equality in tests, never two known keys
**Source:** `test_challenge_endpoint.py:110-111`; `tests/e2e/test_sync.py:101-110`, `:306-307`
**Apply to:** `tests/unit/test_users_me.py`, `tests/e2e/test_users_me.py`
```python
        # The whole body, not two known keys: a seventh field would pass the weaker check.
        assert response.json() == { ... }
```
This is how D-01's closed payload is made executable.

### Barrel `__all__` is a sorted literal
**Source:** `routers/__init__.py:1`, `crud/__init__.py:1`, `tables/__init__.py:1-9`
**Apply to:** `routers/__init__.py`, `crud/__init__.py`
Alphabetical inside `__all__`, one import per line below it, same order.

---

## No Analog Found

None. Every file in this phase has a same-role, same-data-flow analog already in the repository.

Two near-misses worth recording so a planner does not chase them:

| File | Would-be analog | Why it is the wrong one |
|------|-----------------|-------------------------|
| `app/dependencies.py::get_purchases_db` | `get_challenge_store` (`:90-92`) | Reads a lifespan-built singleton off `request.app.state`; `PurchasesDB` binds the **request** session. Use `get_sync_service` (`:111-114`). |
| `crud/purchases.py` | `crud/challenges.py::ChallengesDB` | Holds no session and takes one per method because the lifespan builds it once (`app/lifespan.py:28`). Use `GrantsDB`. |

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/{routers,crud,schemas,tables,app}/`, `src/nativespeaker/api/errors.py`,
`tests/unit/`, `tests/e2e/`, `AGENTS.md`, `.planning/REQUIREMENTS.md`
**Files scanned:** 22 read in full or by targeted range; `tests/unit/` and `tests/e2e/` enumerated
**Pattern extraction date:** 2026-09-01
