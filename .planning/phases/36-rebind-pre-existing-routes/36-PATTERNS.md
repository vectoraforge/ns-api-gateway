# Phase 36: Rebind Pre-existing Routes - Pattern Map

**Mapped:** 2026-08-21
**Files analyzed:** 21 (6 new source/test modules, 13 modified, 2 docs-only)
**Analogs found:** 17 / 19 code files (2 docs-only files excluded; 2 have no analog)

Every excerpt below was read from source this session. Line numbers are from the working tree at
commit `28cd4f2` plus the uncommitted D-01 changes.

`docker-compose.yml` and `uv.lock` are **out of scope (D-15)** and are deliberately absent from
every table here.

## File Classification

| New/Modified File | New? | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|---|
| `src/nativespeaker/api/models/grants.py` | new | model | CRUD (read-only this phase) | `src/nativespeaker/api/models/identities.py` | exact |
| `src/nativespeaker/api/database/grants.py` | new | database / repository | CRUD + row locking | `src/nativespeaker/api/database/chats.py` | exact |
| `src/nativespeaker/api/<pkg>/quota.py` (resolver; name at discretion) | new | service / policy resolver | request-response, transform | `src/nativespeaker/api/auth/identity.py` | exact |
| `src/nativespeaker/api/app/dependencies.py` (`require_quota` + 2 wrappers) | mod | middleware / DI seam | request-response | same file, lines 21-38 and 58-86 | exact |
| `src/nativespeaker/api/routers/chats.py` (2 decorators) | mod | route | request-response | same file, lines 46-59 / 62-76 | exact |
| `src/nativespeaker/api/auth/registry.py` (`quota_checked=True` + cross-check) | mod | config + validation | batch (boot-time) | same file, `assert_route_enumeration` 117-189 | exact |
| `src/nativespeaker/api/errors.py` (2 fail-closed 500 classes) | mod | error taxonomy | — | same file, `DatabaseNotInitializedError` 401-407 | exact |
| `src/nativespeaker/api/models/llm.py` (D-12 defaults) | mod | model (pydantic DTO) | transform | same file, lines 22-26 | exact |
| `src/nativespeaker/api/models/__init__.py` (exports) | mod | barrel | — | same file, lines 1-37 | exact |
| `src/nativespeaker/api/database/__init__.py` (export `GrantsDB`) | mod | barrel | — | same file, lines 1-3 | exact |
| `src/nativespeaker/api/auth/telemetry.py` (optional quota counter) | mod (discretionary) | telemetry | event-driven | same file, `RejectionCounter` 30-46 | exact |
| `tests/e2e/test_quota.py` | new | test (e2e) | request-response | `tests/e2e/test_audit_writer.py` + `tests/e2e/test_error_cases.py` | exact |
| `tests/unit/test_quota_resolver.py` | new | test (unit, pure policy) | transform | `tests/unit/test_identity_resolution.py` | exact |
| `tests/schema/test_grant_locks.py` | new | test (schema, 2 connections) | CRUD under contention | `tests/schema/test_apply_rollback.py::TestRollback` (own-connection) + `tests/schema/conftest.py` `conn` | role-match |
| `tests/e2e/conftest.py` (grant-seeding fixture) | mod | test fixture | file-less CRUD seed | same file, `seed_identity` 146-178 | exact |
| `tests/unit/conftest.py` (quota overrides) | mod | test fixture | — | same file, `client` 146-167 | exact |
| `tests/e2e/test_audit_writer.py` (add missing pair) | mod | test (e2e) | request-response | same file, lines 339-345 | exact |
| `tests/unit/test_route_registry.py` (cross-check cases) | mod | test (unit) | — | same file, `_app` / `_fails_with` 30-45 | exact |
| `tests/unit/test_models.py` (D-12 cases) | mod | test (unit) | — | same file, `TestAnalyzeResponse` 161-187 | exact |
| `.planning/PROJECT.md` (D-13 lines 56, 189) | mod | docs | — | — | n/a |
| `.planning/ROADMAP.md` ("nine" → eight) | mod | docs | — | — | n/a |

D-01's three already-applied files (`migrations/20260818_01_initial-release.sql`,
`tests/schema/conftest.py`, `tests/schema/test_apply_rollback.py`) need **no new pattern** — they
are verify-and-commit only. Their current shape is quoted below under *Shared Patterns → Seeded
tier reference data* because the new e2e grant fixture depends on it.

---

## Pattern Assignments

### `src/nativespeaker/api/models/grants.py` (model, CRUD)

**Analog:** `src/nativespeaker/api/models/identities.py` — the most recent table module, and the
only one that maps native PG enums, which `core.access_grants` needs for `source` and `status`.

**Module docstring + imports pattern** (`models/identities.py:1-24`):
```python
"""The `core.external_identities` table and the three native enums it binds.
...
The database owns every constraint. The provider/provider_uid agreement CHECK, the
`UNIQUE (issuer, subject)` auth-time lookup key, and the partial
`ix_external_identities_provider_account` index are declared in
`migrations/20260818_01_initial-release.sql` and are deliberately not re-encoded here: a Python
copy of a CHECK is a second source of truth that can drift from the one that actually enforces.
"""
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum
from sqlmodel import Field, SQLModel
```
Copy the "database owns every constraint, do not re-encode" paragraph — it is the standing rule
for `access_grants`' six CHECKs and three partial unique indexes.

**Native-enum pattern** (`models/identities.py:27-54`) — `StrEnum` mirroring the PG type, then a
`cast(Any, Enum(...))` alias naming the type and schema:
```python
class IdentityProvider(StrEnum):
    """Mirrors `core.identity_provider`. `provider_uid` is NULL exactly for `anonymous`."""
    anonymous = "anonymous"
    google = "google"
    apple = "apple"

IdentityProviderType = cast(Any, Enum(IdentityProvider, name='identity_provider', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))
```
Apply to `core.access_grant_source` (4 members) and `core.access_grant_status` (3 members),
verbatim from `migrations/20260818_01_initial-release.sql:71-82`.

**Table-class pattern** (`models/identities.py:58-80`):
```python
class ExternalIdentity(SQLModel, table=True):
    """A verified `(issuer, subject)` bound to exactly one `core.users` row."""

    __tablename__ = "external_identities"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", unique=True)
    provider: IdentityProvider = Field(sa_type=IdentityProviderType)
    provider_uid: str | None = Field(default=None)
    identity_state: IdentityState = Field(sa_type=IdentityStateType, default=IdentityState.active)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```
Non-UUID primary key precedent for `AccessTier.id: str`: `models/chats.py:38`
(`id: UUID = Field(primary_key=True)` with no `default_factory`) — declare
`id: str = Field(primary_key=True)`, no default.

**Deviation this file must make (no analog exists):**
- **Omit the four `GENERATED ALWAYS AS (...) STORED` columns** on `core.access_grants`
  (`migration:405-416`: `anti_abuse_required_grant_id`, `active_registered_account_grant_id`,
  `active_subscription_grant_subscription_id`, `active_subscription_grant_user_id`). No existing
  model maps a generated column, so there is no idiom to copy — omit them. Record why in the
  docstring, in the style of `models/users.py:1-15`'s "three columns deliberately absent" block.
- **`UserMonthlyUsage.created_at` / `updated_at` are `NOT NULL` with no DEFAULT**
  (`migration:578-585`), unlike every other table. The `default_factory=lambda: datetime.now(UTC)`
  from the analog is therefore load-bearing here, not decorative.

**Docstring precedent for "a later phase owns this"** (`models/users.py:12-14`), which the new
module's header should invert (Phase 36 now owns it):
```python
`core.usage_monthly` was dropped by the same migration, so `UsageMonthly` went with it. Phase 36
introduces `core.user_monthly_usage`, keyed on `grant_id`; that is a different table it owns.
```

**Barrel export** — `models/__init__.py:1-7` keeps `__all__` alphabetised, then one grouped import
per module (lines 9-37). Add the three new names to `__all__` and a
`from nativespeaker.api.models.grants import (...)` block in alphabetical module order (between
`chats` and `identities`).

---

### `src/nativespeaker/api/database/grants.py` (`GrantsDB`) (database, CRUD + locking)

**Analog:** `src/nativespeaker/api/database/chats.py` — 54 lines, the session-in-init convention
CONTEXT D-03 names explicitly.

**Full imports + class shape** (`database/chats.py:1-16`):
```python
from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import col, delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.models import Chat, Message


class ChatsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    def create_chat(self, obj: Chat):
        self.session.add(obj)
```
Copy: no docstring on the class, session on `__init__` only, methods take scalar params.
**Do not copy** the `selectinload` import (`chats.py:3`, used at `:21`) — RESEARCH Pitfall 4:
PostgreSQL rejects `FOR UPDATE` with the outer join eager loading emits.

**Core read pattern — `col()`-wrapped filters, `.exec(...).first()`** (`database/chats.py:18-24`):
```python
    async def get_chat(self, chat_id: UUID, user_id: UUID) -> Chat | None:
        statement = (
            select(Chat)
            .options(selectinload(Chat.messages))  # type: ignore[invalid-argument-type]
            .where(col(Chat.id) == chat_id, col(Chat.user_id) == user_id)
        )
        return (await self.session.exec(statement)).first()
```

**Multi-row read with explicit ordering** (`database/chats.py:30-36`) — the shape the
effective-grant query extends with `.with_for_update()` and `.all()` (not `.first()`, per D-10):
```python
    async def list_chats(self, user_id: UUID) -> list[Chat]:
        statement = (
            select(Chat)
            .where(col(Chat.user_id) == user_id)
            .order_by(col(Chat.created_at).desc())
        )
        return list((await self.session.exec(statement)).all())
```

**Two-statement lock form to write** (from RESEARCH, SQL compilation verified in that session;
this is the reference shape Phases 41/42/45 copy — SHARED-INVARIANTS:33):
```python
# 1. grants first, ascending id -- no LIMIT 1 (D-10)
grant_stmt = (select(AccessGrant)
              .where(col(AccessGrant.user_id) == user_id,
                     col(AccessGrant.status) == GrantStatus.active,
                     col(AccessGrant.starts_at) <= evaluated_at,
                     or_(col(AccessGrant.ends_at).is_(None),
                         col(AccessGrant.ends_at) > evaluated_at))
              .order_by(col(AccessGrant.id).asc())
              .with_for_update())

# 2. then the usage row, same order
usage_stmt = (select(UserMonthlyUsage)
              .where(col(UserMonthlyUsage.grant_id) == grant.id)
              .with_for_update())
```

**Comment style for a strict/defensive comparison** — copy the reasoning-in-comment convention
from `auth/identity.py:17-22` when writing the `status == active` and "no `LIMIT 1`" lines:
```python
Two comparisons are written in their strict form on purpose:

- `identity.identity_state != IdentityState.active` rather than `== IdentityState.historical`, so
  a NULL and any future enum member fail closed on the same branch instead of reaching a caller;
```

**Barrel export** (`database/__init__.py:1-3`, whole file):
```python
__all__ = ["ChatsDB"]

from nativespeaker.api.database.chats import ChatsDB
```
Becomes `__all__ = ["ChatsDB", "GrantsDB"]` plus the second import line.

---

### `src/nativespeaker/api/<pkg>/quota.py` — the resolver (service / policy)

**Analog:** `src/nativespeaker/api/auth/identity.py` (101 lines). It is the only existing
"module-level async function over a session that returns a typed decision" in the codebase, and it
is the exact shape D-03 asks for: policy above a session, importable by name from another phase.

**Decision-type pattern** (`auth/identity.py:47-68`) — frozen slotted dataclasses plus a union
alias, so the caller matches on type rather than on a sentinel:
```python
@dataclass(frozen=True, slots=True)
class Admit:
    """The barrier may dispatch: the §1.4 identity variant this request carries."""
    identity: LinkedIdentity | PreAuthIdentity


@dataclass(frozen=True, slots=True)
class Reject:
    error_class: ErrorClass
    result: AuthEventResult
    actor_issuer: str | None
    actor_subject: str | None


AdmissionDecision = Admit | Reject
```
If the discretion item picks the "small result carrying `remaining`/`allowance`" return over a
pure `None` gate, this is the shape to copy for it.

**Resolver signature and body pattern** (`auth/identity.py:71-101`) — keyword-only inputs, a
docstring stating the query-count invariant, then a flat sequence of fail-closed branches with the
reason in a comment beside each:
```python
async def resolve_identity(session: AsyncSession, *, issuer: str, subject: str,
                           meta: RouteMetadata) -> AdmissionDecision:
    """Resolve a verified `(issuer, subject)` into one of the four §1.3 outcomes.

    Exactly one statement is issued per call, whatever the outcome.
    """
    ...
    if row is None:
        # Outcomes 1 and 1'. Identity rows are never deleted, so "no matching row" can only mean
        # this pair was never linked -- ...
        if meta.preauth_callable:
            return Admit(PreAuthIdentity(issuer=issuer, subject=subject))
        return Reject(PREAUTH_IDENTITY_NOT_ALLOWED,
                      AuthEventResult.preauth_identity_not_allowed, issuer, subject)

    identity, user = row
    if user is None:
        # Unresolvable stored state. Fail closed -- never invent, reassign, merge, or repair an
        # identity row inline, and never read the broken link as an unlinked pair.
        return Reject(INTERNAL_ERROR, AuthEventResult.internal_error, issuer, subject)
```
Map the branch set directly: 0 grants → `QuotaExceededError` (D-08); >1 grants → internal 500
(D-10); no usage row → internal 500, never minted (D-09); `remaining == 0` →
`QuotaExceededError`.

**Anti-oracle / deliberate-omission docstring precedent** (`auth/identity.py:8-15`) — the model for
recording D-10's "structurally unreachable, asserted anyway" and D-11's "a failed LLM call burns the
credit" as decisions rather than oversights:
```python
**The anti-oracle guarantee is structural (D-13).** ... Timing normalization, padding, and
constant-time delays are **deliberately absent**: D-13 rejects them for this product ... The
omission is a decision, not an oversight -- do not "fix" it without revisiting D-13.
```

**Difference from the analog to be explicit about:** `resolve_identity` *returns* a `Reject`
because its caller is ASGI middleware that must not raise (`barrier.py:158-160`). The quota
resolver runs inside a FastAPI dependency, so it **raises** `ServiceError` subclasses and lets
`service_error_handler` (`app/errors.py:28-35`) format them. Do not copy the return-a-rejection
half.

---

### `src/nativespeaker/api/app/dependencies.py` — `require_quota` + two per-route wrappers

**Analog:** the same file. Three seams already there give every piece.

**Own-session pattern to copy the `async with` from, and to deviate from** (`dependencies.py:21-28`):
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
D-04: `require_quota` opens `request.app.state.session_factory()` the same way but **does not
yield** — it commits inside its own body and returns, so the locks are gone before the handler is
entered. `barrier.py:132-135` is the in-tree precedent for the non-yield form and states the rule
this phase inherits:
```python
        # Step 4 -- resolution. Exactly one short session, closed before dispatch: no lock is held
        # and no network call is made while it is open.
        async with scope["app"].state.session_factory() as session:
            decision = await resolve_identity(session, issuer=claims.issuer,
                                              subject=claims.subject, meta=meta)
```

**Composed-dependency pattern** (`dependencies.py:31-38`) — the shape for the two thin per-route
wrappers, which take `Depends()` params plus the declared body model (D-14):
```python
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(db=db, ...)
```
The D-14 wrappers add a plain (non-`Depends`) body parameter so FastAPI validates the body while
solving the dependency:
`async def require_quota_create_chat(request: Request, body: ChatRequest, context: RequestContext = Depends(get_request_context))`
and `..._send_message(request: Request, chat_id: UUID, body: MessageRequest, ...)`.
Body models are `ChatRequest` (`models/api.py:14-18`) and `MessageRequest` (`models/api.py:29-31`).

**Context accessor pattern** (`dependencies.py:58-65`) — how `require_quota` reads
`evaluated_at` and `identity.user.id` (D-06), and the fail-loudly convention:
```python
def get_request_context(request: Request) -> RequestContext:
    """The §1.4 context the barrier attached. Raises when the barrier did not run."""
    context = getattr(request.state, REQUEST_CONTEXT_SCOPE_KEY, None)
    if not isinstance(context, RequestContext):
        # isinstance, not `is None`: a wrong-typed value under the key is as unusable as an absent
        # one and must fail closed too, ...
        raise AuthenticationError("No identity context on this request: it ran outside the barrier")
    return context
```
`RequestContext` fields, `auth/context.py:82-93`: `identity`, `route_metadata`,
`client_ip_bucket_kind`, `evaluated_at`, `attempt_id`. `LinkedIdentity` (`context.py:53-65`)
carries `user: User`. Period string is `context.evaluated_at.strftime("%Y-%m")` — `evaluated_at`
is already UTC-aware (`barrier.py:100`).

**Where the new code goes:** the reserved slot is the D-16 comment block at `dependencies.py:89-102`.
Delete only the `require_quota` entry (lines 98-100) from that block, leave `get_current_user` and
`get_subscription_service` recorded:
```python
#   require_quota          -- backend quota enforcement is Phase 36 REBIND-05, and the named
#                             `quota_checked_request` admission entry §8.4 described is void
#                             because D-05 deleted backend rate limiting from the product.
```

**Header-comment convention for a new seam group** (`dependencies.py:41-55`) — a `# ---` banner, the
spec/decision reference, then the reasoning. Reuse it for the quota block.

---

### `src/nativespeaker/api/errors.py` — two fail-closed 500 classes

**Analog:** `errors.py:401-407`, the one existing `INTERNAL_ERROR`-mapped class:
```python
class DatabaseNotInitializedError(ServiceError):
    """Raised when DB session factory is not initialized -- maps to 500."""
    error_class = INTERNAL_ERROR
    log_level = logging.ERROR

    def __init__(self):
        super().__init__("Database session factory is not initialized")
```
`log_level = logging.ERROR` is load-bearing: `service_error_handler` (`app/errors.py:30-34`) logs
with `exc_info=True` at ERROR and above. That is the right level for both D-09 and D-10.

**Reuse verbatim, add nothing:** `QUOTA_EXCEEDED` (`errors.py:186-190`) and
`QuotaExceededError` (`errors.py:364-365`, whole class):
```python
class QuotaExceededError(ServiceError):
    error_class = QUOTA_EXCEEDED
```
It inherits `extra_headers() -> None` from `ServiceError` (`errors.py:285-286`), so no
`Retry-After` — matching v1.6 and the passed-over discretion item. The `Retry-After` shape, if the
discretion is ever revisited, is `CircuitOpenError` (`errors.py:353-361`).

**Do not** call `register_class` for the quota path — `ErrorCode` (`errors.py:24-35`) is closed and
`assert_registry_total()` (`errors.py:260-268`) fails boot on a mismatch. The two new classes reuse
existing registered `ErrorClass` objects.

---

### `src/nativespeaker/api/routers/chats.py` — the two POST decorators

**Analog:** the same file. Only the decorator changes; the handler bodies are untouched.

**Current decorator** (`routers/chats.py:46-54`):
```python
@router.post("/chats",
             response_model=MessageResponse,
             summary="Start new analysis",
             description="Analyzes a phrase and creates a new chat session with the AI response. "
                         "Consumes one request from the user's monthly quota.",
             response_description="AI analysis message")
async def create_chat(body: ChatRequest,
                      identity: LinkedIdentity = Depends(get_linked_identity),
                      service: ChatService = Depends(get_chat_service)) -> MessageResponse:
```
Add `dependencies=[Depends(require_quota_create_chat)]` to the decorator kwargs. Same for
`POST /chats/{chat_id}` at `:62-71` with the `send_message` wrapper. The description string already
says "Consumes one request from the user's monthly quota" — after this phase it is finally true.

**Module-comment convention** (`routers/chats.py:12-15`) — the per-module note explaining the
wiring rule, which should gain one sentence about the quota dependency:
```python
# Every handler below reads the one identity context the barrier attached, through the §1.4
# accessor and nothing else (D-02). `get_linked_identity` raises rather than returning `None`, so a
# handler cannot serve a request the barrier did not admit. ...
```

**Anti-pattern confirmed by the file:** no router-level dependency exists on any of the four
routers (`routers/__init__.py:1-6`, `app/main.py:47-50`). Do not add one (RESEARCH §The Eight
Pre-existing Routes).

---

### `src/nativespeaker/api/auth/registry.py` — `quota_checked=True` + the D-05 cross-check

**Analog:** the same file. The field exists (`registry.py:35`, verbatim `quota_checked: bool = False`)
and the assertion has a slot-shaped hole for the new condition.

**Registry entry pattern** (`registry.py:73, 75`) — two entries gain one kwarg:
```python
    RouteMetadata(method="POST", path="/chats", category=Category.authenticated),
    RouteMetadata(method="POST", path="/chats/{chat_id}", category=Category.authenticated),
```

**Problem-accumulation pattern to extend** (`registry.py:128-136` and `188-189`) — append to
`problems`, never raise early; the raise lists everything:
```python
    registered, problems = enumerate_registered(app)
    declared = {(e.method, e.path) for e in registry}

    if extra := registered - declared:
        problems.append(f"registered but undeclared: {sorted(extra)}")
    if missing := declared - registered:
        problems.append(f"declared but unregistered: {sorted(missing)}")
    ...
    if problems:
        raise RuntimeError("route enumeration assertion failed:\n  " + "\n  ".join(problems))
```

**Per-entry condition pattern to copy for the cross-check** (`registry.py:147-149`) — the closest
existing "this flag is only legal in this exact place" condition:
```python
        if entry.preauth_callable and key != _PREAUTH_CALLABLE_ROUTE:  # condition 6
            problems.append(f"illegal preauth_callable declaration on {key}: only "
                            f"{_PREAUTH_CALLABLE_ROUTE} may be pre-auth callable")
```
The new condition must compare in **both** directions (declared-but-not-attached and
attached-but-not-declared), mirroring conditions 1/2 above.

**Route-walking pattern for the dependency inspection** (`registry.py:97-114`) — the walk already
exists; the cross-check needs the same `isinstance(route, APIRoute)` loop plus `route.dependencies`
/ `route.dependant.dependencies`:
```python
def enumerate_registered(app: Any) -> tuple[set[tuple[str, str]], list[str]]:
    registered: set[tuple[str, str]] = set()
    problems: list[str] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                registered.add((method, route.path))
```
Match the wrappers **by callable identity** against `dep.call`, not by name string (RESEARCH; a
name match silently passes a renamed function). Assumption A2 — verify
`route.dependant.dependencies` on the installed FastAPI 0.135.1 before writing the task.

**Local-import precedent for a cycle** (`registry.py:122-124`) — if the cross-check needs to import
the wrappers from `app.dependencies` (which imports `auth.context` → `auth.registry`), copy this:
```python
    # Local import: barrier.py imports this module for its own route lookup, and condition 9 needs
    # the barrier class by identity. Importing at function scope keeps the cycle from forming.
    from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
```

**Boot wiring — no change needed** (`app/lifespan.py:35-37`); the cross-check rides the existing call:
```python
    assert_registry_total()
    app.state.route_registry = REGISTRY
    assert_route_enumeration(app, app.state.route_registry)
```
Pitfall 7: registry flag, decorator attachment, and cross-check must land in **one commit** or the
app will not boot between commits.

---

### `src/nativespeaker/api/models/llm.py` (D-12)

**Analog:** the same file, four lines up. `AnalyzeInput` (`models/llm.py:11-14`) already shows the
defaulted-field form:
```python
class AnalyzeInput(BaseModel):
    mode: Literal["analyze"] = "analyze"
    phrase: str
    context: str | None = None
```
Change (`models/llm.py:22-26`):
```python
class AnalyzeResponse(BaseModel):
    resolved_mode: Literal["analyze"]
    response: str
    issues: list[Issue]
    suggestions: list[str]
```
→ `issues: list[Issue] = []` and `suggestions: list[str] = []`. The validation call site is
`services/chats.py:57` (`AnalyzeResponse.model_validate(llm_response)`); no other code reads these
fields, so no downstream change follows.

---

### `src/nativespeaker/api/auth/telemetry.py` (discretionary quota counter)

**Analog:** the same file, `RejectionCounter` (`telemetry.py:30-46`, whole class):
```python
class RejectionCounter:
    """An in-process counter keyed by result x bounded reason x route."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str | None, str], int] = {}

    def increment(self, *, result: str, bounded_reason: str | None, route: str) -> None:
        key = (result, bounded_reason, route)
        self._counts[key] = self._counts.get(key, 0) + 1

    def snapshot(self) -> dict[tuple[str, str | None, str], int]:
        """A copy, so a reader cannot mutate live counts."""
        return dict(self._counts)
```
**Constraint:** `record_rejection` (`telemetry.py:49-52`) types `result: AuthEventResult`, a closed
44-value enum (`models/auth.py:37-42` docstring: "Closed and exact (44 values)"). Do **not** widen
it. If a quota metric is wanted, add a separate small counter beside this class and instantiate it
in `app/lifespan.py` next to line 44 (`app.state.rejection_counter = RejectionCounter()`).

**Structured-log call pattern for the fail-closed branches** (`telemetry.py:64-68`):
```python
        logger.error("rejection_counter_missing",
                     result=str(result), bounded_reason=reason, route=route)
    ...
    logger.warning("auth_rejected", result=str(result), bounded_reason=reason, route=route)
```
Bounded-cardinality rule (`telemetry.py:10-15`): labels come from closed sets only — never the raw
path, the subject, or a grant id.

---

### `tests/e2e/test_quota.py` (test, e2e)

**Analogs:** `tests/e2e/test_audit_writer.py` (module conventions, row counting, counter deltas) and
`tests/e2e/test_error_cases.py` (per-branch status/body assertions on the chat routes).

**Module header + marker pattern** (`test_audit_writer.py:19-33`):
```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func
from sqlmodel import select
from unit.conftest import TEST_ISSUER, make_token

from e2e.conftest import seed_identity
from nativespeaker.api.models.auth import AuthEvent

pytestmark = pytest.mark.e2e
```
Cross-package imports are bare `unit.conftest` / `e2e.conftest` (`pythonpath = ["."]`).

**Class-level loop-scope pattern** (`test_audit_writer.py:105-107`, and again at `:333`, `:379`) —
required, because `_app_lifespan` is module-scoped:
```python
@pytest.mark.asyncio(loop_scope="module")
class TestAnOnPathRejectionWritesExactlyOneRow:
    """§4.1: one row per on-path attempt, for its terminal outcome, before the response returns."""
```

**Row-count helper pattern** (`test_audit_writer.py:96-102`) — read back through the swapped
`_db_transaction` factory, never a fresh engine. The `monthly_used`-unchanged assertion for the
D-14 malformed-body case copies this exactly, with `UserMonthlyUsage` in place of `AuthEvent`:
```python
async def rows(factory) -> list[AuthEvent]:
    async with factory() as session:
        return list((await session.exec(select(AuthEvent))).all())


async def row_count(factory) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(AuthEvent))
```

**Zero-audit-row-on-a-quota-429 pattern** (`test_audit_writer.py:333-350`) — extend this class or
mirror it:
```python
@pytest.mark.asyncio(loop_scope="module")
class TestOffPathRequestsWriteNothing:
    @pytest.mark.parametrize("method,path", [("GET", "/"), ("GET", "/examples"),
                                             ("GET", "/chats"), ("POST", "/chats"),
                                             ("GET", "/chats/0198f0d2-0000-7000-8000-00000000000a"),
                                             ("DELETE",
                                              "/chats/0198f0d2-0000-7000-8000-00000000000a")])
    async def test_an_unauthenticated_request_to_a_foundation_route_writes_zero_rows(
            self, unauthenticated_client, _db_transaction, method, path):
        async with unauthenticated_client as client:
            response = await client.request(method, path)

        assert response.status_code == 401
        assert await row_count(_db_transaction) == 0
```
**Also add** `("POST", "/chats/{chat_id}")` — the pair missing from this list, and one of the two
quota-checked routes.

**Status + shared-body assertion pattern** (`test_error_cases.py:54-65`) — the exact form for the
429 and 500 cases:
```python
    async def test_unsupported_language_returns_400(self, async_client, linked_firebase_identity):
        response = await async_client.post("/chats", json={"phrase": "test", "lang": "xx"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    async def test_missing_phrase_returns_422(self, async_client, linked_firebase_identity):
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"
```
`test_error_cases.py:63` and `:99` and `test_chats.py:170` all send `{"lang": "en"}` — the exact
malformed body D-14's `-k malformed` test must prove burns nothing.

**Counter-observation pattern, before/after delta** (`test_audit_writer.py:395-403`) — module-scoped
app means counts accumulate, so never assert exact equality against the real app:
```python
    async def test_an_off_path_rejection_increments_the_counter_too(
            self, unauthenticated_client, _app_lifespan):
        counter = _app_lifespan.state.rejection_counter
        before = counter.snapshot().get(("invalid_external_jwt", "missing_token", "/chats"), 0)
        async with unauthenticated_client as client:
            await client.get("/chats")

        after = counter.snapshot()[("invalid_external_jwt", "missing_token", "/chats")]
        assert after == before + 1
```

**Module-docstring convention** — every e2e module states what the pair of classes proves and why
each is the other's control (`test_chats.py:1-21`, `test_error_cases.py:1-21`). `test_chats.py:19-20`
is the sentence this phase retires:
> No case here asserts a quota outcome. The chat quota path reads a grant model Phase 36 wires
> (D-15), so there is no allowance to enforce and nothing honest to assert about one.

---

### `tests/unit/test_quota_resolver.py` (test, unit, pure policy)

**Analog:** `tests/unit/test_identity_resolution.py` — the same job for the same-shaped resolver:
prove the branches the database cannot produce, with a stub session, no DB, no e2e marker.

**Module docstring stating why a stub is the only way** (`test_identity_resolution.py:1-11`):
```python
"""FOUND-01 / §1.3: the four-outcome admission matrix as logic, plus the §1.2 counter.

`tests/e2e/test_barrier_admission.py` proves the matrix against real rows over the real transport.
This module proves the branches the *database* cannot produce. ... A stub session is the only way
to put such a row in front of `resolve_identity`.

The stub also makes the query-count claim checkable directly: it counts its own `exec` calls, so
"exactly one SELECT per resolution" is asserted rather than read off the source.
"""
```
This is precisely D-10's situation: `ix_access_grants_one_active_per_user` makes two effective
grants unreachable in PostgreSQL, so the multi-grant tripwire is only testable through a stub.

**Stub session pattern** (`test_identity_resolution.py:33-53`) — copy verbatim, extend `_StubResult`
with `.all()` for the no-`LIMIT 1` grant query:
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

**Row-builder helper pattern** (`test_identity_resolution.py:62-71`) — a `_row(...)` factory with
`...`-sentinel defaults, so each test varies exactly one field:
```python
def _row(*, identity_state=IdentityState.active, user_active: bool = True, user=...):
    """An `(identity, user)` pair shaped exactly as the single joined statement returns one."""
    user_id = uuid7()
    identity = ExternalIdentity(id=uuid7(), user_id=user_id, ...)
    if user is ...:
        user = User(id=user_id, active=user_active)
    return identity, user
```

**Class-per-outcome naming** (`test_identity_resolution.py:80-215`): `TestOutcomeOneNoMatchingRow`,
`TestOutcomeTwoIdentityStateIsNotExactlyActive`, `TestUnresolvableUser`, `TestOneQueryOneCodePath`,
`TestTheResolutionStatement`. Map to: `TestNoEffectiveGrant`, `TestMissingUsageRow`,
`TestMultipleEffectiveGrants`, `TestRemainingNeverNegative`, `TestLazyRollover`,
`TestTheLockingStatements` (which can assert the compiled SQL carries `FOR UPDATE` and the
ascending `ORDER BY`, the same way `TestTheResolutionStatement` inspects its statement).

---

### `tests/schema/test_grant_locks.py` (test, schema, two connections)

**Analog:** partial. `tests/schema/` has the harness but **no existing two-connection contention
test**, so this file combines two in-tree patterns and invents the contention part.

**Module header + marker + helper imports** (`test_constraints.py:1-10`):
```python
"""SCHEMA-02 .. SCHEMA-06 -- the 00-schema.md section 10 rejection cases, exercised with real rows."""
import contextlib
import uuid

import asyncpg
import pytest

from schema.helpers import insert_grant, insert_user

pytestmark = pytest.mark.schema
```

**Seed helpers to reuse unchanged** (`tests/schema/helpers.py:11-70`) — `insert_user`,
`insert_tier`, `insert_grant`, all `$N`-parameterised and none committing:
```python
async def insert_grant(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    tier_id: str,
    source: str = "anonymous_device_grant",
    status: str = "active",
    subscription_id: uuid.UUID | None = None,
) -> uuid.UUID:
```
No `insert_usage` helper exists — `test_constraints.py:73` inlines the
`INSERT INTO core.user_monthly_usage` string. Adding a fourth helper to `helpers.py` following the
same signature shape is the natural move; keep it `$N`-bound and non-committing.

**The single-connection `conn` fixture this test must NOT rely on alone** (`tests/schema/conftest.py:125-138`):
```python
@pytest_asyncio.fixture
async def conn(_schema_db_uri):
    """Connection to the migrated scratch database, inside a transaction that always rolls back."""
    connection = await asyncpg.connect(_schema_db_uri)
    tx = connection.transaction()
    await tx.start()
    try:
        yield connection
    finally:
        try:
            await tx.rollback()
        except Exception:  # a deferred-constraint failure already aborted it -- RESEARCH P-6
            pass
        await connection.close()
```
The rollback already tolerates a poisoned transaction — useful when a contending statement is
cancelled.

**Own-extra-connection pattern** (`test_apply_rollback.py:44-58`) — the in-tree precedent for a test
opening its own `asyncpg.connect` with nested `try/finally` cleanup. The second connection for the
contention test copies this structure but targets `_schema_db_uri` (not a new database):
```python
    async def test_pogo_rollback_leaves_neither_schema(self):
        uri = await create_database(ROLLBACK_TEST_DB)
        try:
            connection = await asyncpg.connect(uri)
            try:
                ...
            finally:
                await connection.close()
        finally:
            await drop_database(ROLLBACK_TEST_DB)
```
Note the second connection is **outside** the `conn` fixture's transaction, so anything it commits
must be cleaned up by the test itself. Prefer: seed on `conn`, commit nothing, and have the second
connection contend against rows the first holds locked.

**Invariant-with-a-comment style for a rule no CHECK expresses** (`test_apply_rollback.py:82-91`) —
the model for documenting the ascending-grant-id lock order:
```python
    async def test_registered_is_not_smaller_than_anonymous(self, conn):
        """07-claim-registered-grant.md:59's sizing invariant, which no CHECK can express.
        ...
        """
```

**Why this file exists at all** — Pitfall 3: `tests/e2e/conftest.py:81-104` binds every session to
one connection with `join_transaction_mode="create_savepoint"`, so a contention test written in
`tests/e2e/` would pass vacuously.

---

### `tests/e2e/conftest.py` — the grant-seeding fixture

**Analog:** the same file, `seed_identity` (`conftest.py:146-178`) — the SQLModel-session seeding
convention this package uses (the `tests/schema/` asyncpg helpers are a different package and are
not importable here).

**Seed-helper pattern** (`conftest.py:146-178`), whole function:
```python
async def seed_identity(factory, *,
                        issuer: str,
                        subject: str,
                        identity_state: IdentityState = IdentityState.active,
                        user_active: bool = True,
                        provider: IdentityProvider = IdentityProvider.google):
    """Insert a `core.users` row and its matching `core.external_identities` row; return both.
    ...
    Test seeding only, and deliberately not a provisioning path -- no route reaches it, and `src/`
    still contains no code that writes either table. `core.users` rows originate from
    `POST /auth/create-user` in Phase 37.
    """
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
Copy: module-level `async def` taking `factory` first, `async with factory() as session`, `flush()`
between dependent inserts, one `commit()` at the end, returns the rows. **The grant seeder must
insert the `core.access_grants` row AND its `core.user_monthly_usage` row in the same call** — D-09
turns a grant without usage into a 500, which is a worse failure than the 429 it replaces
(Pitfall 2).

**Fixture-wrapping-a-helper pattern** (`conftest.py:132-143`) — the shape for a
`seeded_grant`/`quota_grant` fixture that the six existing chat tests will depend on:
```python
@pytest_asyncio.fixture(loop_scope="module")
async def linked_firebase_identity(_db_transaction, _app_config, test_user_id):
    """Seed the *real* Firebase credential's pair, so `async_client` is admitted by the barrier.
    ...
    Seeded inside the per-test transaction, so it rolls back.
    """
    return await seed_identity(_db_transaction,
                               issuer=_app_config.jwt.issuer,
                               subject=test_user_id,)
```
`loop_scope="module"` and the `_db_transaction` dependency are both mandatory.

**Tier id to use:** the seeded `registered` id (50 credits) from
`migrations/20260818_01_initial-release.sql:280-283`, not a randomised `insert_tier` id. Pinned by
`tests/schema/test_apply_rollback.py:20` (`SEEDED_TIERS = {"anonymous", "registered", "paid"}`) and
`:74-79`.

**The six tests that need this fixture** (Pitfall 2): `test_chats.py` `TestCreateChat` (lines 35,
47, 58, 82, 94) and `TestFollowup` (118); `test_flows.py:28, 37`; `test_isolation.py:92`;
`test_error_cases.py:49, 56, 63, 92, 99`. The fixture must land in the **same wave** as the
decorator attachment.

---

### `tests/unit/conftest.py` — quota dependency overrides

**Analog:** the same file, the `client` fixture (`conftest.py:146-167`), whole function:
```python
@pytest.fixture
def client(mock_chats_db, service):
    """The four surviving routers with the identity context supplied instead of the barrier.

    `get_linked_identity` is overridden rather than the barrier being installed: this fixture's
    subject is what a handler does *once admitted*. ...
    """
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(chats_router)
    app.include_router(examples_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: service
    app.dependency_overrides[get_linked_identity] = lambda: TEST_IDENTITY

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
```
Add one `app.dependency_overrides[...] = ...` line **per wrapper** (Pitfall 6: overrides key on the
exact callable and do not cascade — overriding the shared resolver they call is not enough). This
app has no `state.session_factory`, so without the overrides every unit test through this fixture
hits real quota code and fails.

**Import line to extend** (`conftest.py:12`):
```python
from nativespeaker.api.app.dependencies import get_chat_service, get_db, get_linked_identity
```

**Stand-in-identity pattern already available** (`conftest.py:105-118`) — `TEST_USER_ID` and
`TEST_IDENTITY` are what a quota-path unit test would need for `identity.user.id`:
```python
TEST_SUBJECT = "test-user"
TEST_USER_ID = uuid7()
TEST_IDENTITY = LinkedIdentity(
    user=User(id=TEST_USER_ID, active=True),
    identity=ExternalIdentity(id=uuid7(), user_id=TEST_USER_ID, ...),
    issuer=TEST_ISSUER,
    subject=TEST_SUBJECT,
)
```
There is **no** `RequestContext` stand-in in this file yet — if a unit test needs one, build it from
`TEST_IDENTITY` plus a fixed `evaluated_at`, following `auth/context.py:82-93`.

**Mock-DB-class pattern** (`conftest.py:121-130`) — the shape for a `mock_grants_db` if the resolver
is unit-tested against a mocked `GrantsDB` rather than the stub session:
```python
@pytest.fixture
def mock_chats_db():
    db = AsyncMock(spec=ChatsDB)
    db.create_chat = MagicMock()
    db.get_chat = AsyncMock(return_value=None)
    ...
    return db
```

---

### `tests/unit/test_route_registry.py` — D-05 cross-check cases

**Analog:** the same file. Its two helpers are exactly what a new
`TestCondition10QuotaFlagAndDependencyDisagree` class needs (`test_route_registry.py:30-45`):
```python
def _app(*routes: tuple[str, str], barrier: bool = True) -> FastAPI:
    """A throwaway app carrying exactly the given (method, path) routes."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    for method, path in routes:
        app.add_api_route(path, _endpoint, methods=[method])
    if barrier:
        app.add_middleware(AuthBarrierMiddleware)
    return app


def _fails_with(substring: str, app: FastAPI, registry: tuple[RouteMetadata, ...], **kwargs) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        assert_route_enumeration(app, registry, **kwargs)
    assert substring in str(excinfo.value)
```
`_app` will need a `dependencies=[...]` passthrough to `add_api_route` so the negative cases can
build a route that carries the wrapper without the flag, and vice versa.

**Positive case to keep green** (`test_route_registry.py:48-51`) — the guard that the real registry
and the real router agree after the change:
```python
class TestAssertionPasses:
    def test_real_app_registry_matches_the_real_router(self):
        """The shipped REGISTRY is set-equal to what the real app registers."""
        assert_route_enumeration(real_app)
```

**Naming convention:** one class per §2.3 condition (`TestCondition1...` through
`TestCondition9...`), each with a raises-case and a message-content case.

---

### `tests/unit/test_models.py` — D-12 cases

**Analog:** the same file, `TestAnalyzeResponse` (`test_models.py:161-187`). Add a case constructing
`AnalyzeResponse(resolved_mode="analyze", response="ok")` with both list fields omitted and
asserting `ar.issues == []` and `ar.suggestions == []`. Import block is already in place
(`test_models.py:15-22`).

---

## Shared Patterns

### Session and transaction boundary
**Source:** `src/nativespeaker/api/auth/barrier.py:132-135`, `app/dependencies.py:21-28`
**Apply to:** `require_quota`, `GrantsDB`, the resolver
```python
        # Step 4 -- resolution. Exactly one short session, closed before dispatch: no lock is held
        # and no network call is made while it is open.
        async with scope["app"].state.session_factory() as session:
```
Two forms exist in the tree: the yield-dependency `get_db` (commits *after* the handler) and the
barrier's own short session. D-04 requires the second. Nothing that holds a lock may await a
network call.

### Error raising and response mapping
**Source:** `src/nativespeaker/api/errors.py:281-286`, `src/nativespeaker/api/app/errors.py:28-35`
**Apply to:** every quota rejection branch — **no handler change is needed**
```python
class ServiceError(Exception):
    """Base exception for service layer errors."""
    error_class: ErrorClass = INTERNAL_ERROR
    log_level: int | None = None

    def extra_headers(self) -> dict[str, str] | None:
        return None
```
```python
async def service_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    if exc.log_level is not None:
        method_name = _LEVEL_TO_METHOD.get(exc.log_level, "error")
        log_method = getattr(logger, method_name)
        log_method(str(exc), error_type=type(exc).__name__,
                   exc_info=(exc.log_level >= logging.ERROR))
    return error_response(exc.error_class, headers=exc.extra_headers())
```
Registered once at `app/errors.py:66` (`app.add_exception_handler(ServiceError, service_error_handler)`).
HTTP metadata lives on the exception class; there is exactly one data-driven handler.

### ORM-constructs-only, `col()`-wrapped comparisons
**Source:** `database/chats.py:18-47`, `auth/identity.py:77-81`
**Apply to:** every statement in `GrantsDB`
```python
    statement = (select(ExternalIdentity, User)
                 .join(User, col(ExternalIdentity.user_id) == col(User.id), isouter=True)
                 .where(col(ExternalIdentity.issuer) == issuer,
                        col(ExternalIdentity.subject) == subject))
    row = (await session.exec(statement)).first()
```
Zero `text()` SQL anywhere in `src/`. `col(...)` on both sides of a comparison is the house form.

### Fail-closed comparison style
**Source:** `auth/identity.py:97-100`, `models/users.py:38-40`
**Apply to:** the grant-status and usage-period comparisons
```python
    if identity.identity_state != IdentityState.active:
        return Reject(ACCOUNT_UNAVAILABLE, AuthEventResult.historical_identity, issuer, subject)
    if user.active is not True:
        return Reject(ACCOUNT_UNAVAILABLE, AuthEventResult.blocked_user, issuer, subject)
```
Positive tests, strict comparisons, so a NULL or a future enum member fails closed rather than
falling through.

### Seeded tier reference data (D-01, already applied — verify only)
**Source:** `migrations/20260818_01_initial-release.sql:267-283`
**Apply to:** the e2e grant fixture and any schema test that touches `core.access_tiers`
```sql
-- Seeded as reference data, overriding 00-schema.md:249 ("Phase 00 seeds NO tier rows -
-- tier ids are configuration owned by later phases/deployment"). Recorded here as the
-- required SHARED-INVARIANTS conflict flag rather than resolved silently.
INSERT INTO core.access_tiers (id, monthly_credits) VALUES
    ('anonymous', 10),
    ('registered', 50),
    ('paid', 1000);
```
Pinned by `tests/schema/test_apply_rollback.py:20` (`SEEDED_TIERS`) and `:71-91`
(`TestSeededTiers`). The `tier` fixture (`tests/schema/conftest.py:141-148`) inserts randomised
`tier_<hex>` ids that never collide with these three.

### Comment-as-decision-record
**Source:** `app/dependencies.py:41-55` and `:89-102`; `auth/identity.py:1-27`;
`registry.py:63-67`; `models/users.py:1-15`
**Apply to:** every new module and every deleted/reserved slot
The codebase records *why* beside the code, names the deciding D-number, and states what a later
phase owns. New quota code should carry: D-03 (the shared seam Phase 38 imports by name), D-04 (why
its own session), D-09/D-10 (why no lazy mint and no tie-break), D-11 (why no refund),
SHARED-INVARIANTS:33 (the lock order this file is the first implementation of).

### Test-package conventions
**Source:** `pyproject.toml:51-61`; `tests/e2e/test_audit_writer.py:33, 105`;
`tests/schema/test_constraints.py:11`
**Apply to:** all three new test modules

| Package | Marker | Async convention | Isolation |
|---|---|---|---|
| `tests/unit/` | none (default `addopts` selects it) | `asyncio_mode = "auto"` | no DB at all |
| `tests/e2e/` | `pytestmark = pytest.mark.e2e` | `@pytest.mark.asyncio(loop_scope="module")` on every class | `_db_transaction` autouse rollback |
| `tests/schema/` | `pytestmark = pytest.mark.schema` | function-scoped `conn` fixture, no loop_scope marker | per-test asyncpg transaction rollback |

Commands: `uv run pytest -q` (unit, 912) · `uv run pytest -q -m ""` (all 1162) ·
`uv run ruff check src tests && uv run ty check src`.

---

## No Analog Found

| File / element | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/schema/test_grant_locks.py` — the **contention** half | test (schema) | CRUD under two-connection contention | No test in the repo exercises `FOR UPDATE` contention between two live connections. `test_apply_rollback.py::TestRollback` supplies the own-extra-connection idiom; the blocking/ordering assertion itself is new. Use RESEARCH § *Lock ordering* and SHARED-INVARIANTS:33 as the spec. |
| The D-05 registry **cross-check** internals | config validation | batch (boot) | `assert_route_enumeration` has no existing condition that inspects a live route's `dependant`; conditions 1-9 all read the declaration table or `app.user_middleware`. The accumulate-into-`problems` scaffolding is the analog; the FastAPI introspection is new and rests on assumption A2 — verify against installed FastAPI 0.135.1 first. |
| `GENERATED ALWAYS AS ... STORED` column handling | model | — | No SQLModel class in `src/` maps a generated column. Resolution is to omit all four (Pitfall 5), which needs no idiom — just a docstring note in the `models/users.py:1-15` style. |
| `.planning/PROJECT.md` / `.planning/ROADMAP.md` edits (D-13, "nine"→eight) | docs | — | Prose corrections; no code pattern applies. |

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/**` (39 modules, all enumerated),
`tests/{unit,e2e,schema}/**` (37 modules, all enumerated),
`migrations/20260818_01_initial-release.sql`.

**Files read this session:** `database/chats.py`, `database/__init__.py`, `app/dependencies.py`,
`app/lifespan.py`, `app/main.py`, `app/errors.py`, `errors.py` (targeted ranges),
`auth/registry.py`, `auth/telemetry.py`, `auth/identity.py`, `auth/context.py` (30-100),
`auth/barrier.py` (85-200), `routers/chats.py`, `routers/__init__.py`, `services/chats.py` (1-115),
`services/llm.py` (20-40), `models/{users,chats,identities,llm,api,__init__}.py`, `models/auth.py`
(1-90), `tests/{unit,e2e,schema}/conftest.py`, `tests/schema/helpers.py`,
`tests/schema/test_apply_rollback.py`, `tests/schema/test_constraints.py` (1-40 + index),
`tests/e2e/test_audit_writer.py` (targeted ranges), `tests/e2e/test_chats.py` (targeted),
`tests/e2e/test_error_cases.py`, `tests/e2e/test_startup_assertion.py`,
`tests/unit/test_identity_resolution.py` (1-70), `tests/unit/test_route_registry.py` (1-80 + index),
`tests/unit/test_budgets.py` (1-60), `tests/unit/test_models.py` (1-40 + index),
`migrations/20260818_01_initial-release.sql` (250-290, 376-470, 555-600).

**Project skills:** none — no `.claude/skills/` or `.agents/skills/` directory exists in this repo.

**Pattern extraction date:** 2026-08-21
