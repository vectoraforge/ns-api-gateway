# Phase 38: POST /auth/sync - Pattern Map

**Mapped:** 2026-09-01
**Files analyzed:** 12 code files + 3 documentation files
**Analogs found:** 12 / 12 code files (no code file in this phase lacks an analog)

There is no RESEARCH.md for this phase. Every pattern below is taken from code that is already in
this repository, so the planner should not need an external reference for any file.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/schemas/auth.py` (MODIFY — add the sync response models) | schema | request-response | `CompletionResponse` / `PrepareResponse`, same file :16-31 | exact (same file) |
| `src/nativespeaker/api/crud/grants.py` (MODIFY — non-locking effective-grant read) | crud | read-only query | `GrantsDB.lock_effective_grants`, same file :16-32 | exact (self-analog) |
| service holding the sync read — new `services/sync.py` **or** a method on `services/auth.py` | service | read-only aggregate | `services/quota.py::QuotaService.charge` :27-82 | exact (same three reads, same tripwires) |
| the `/auth/sync` handler — `routers/auth.py` **or** a new `routers/sync.py` | router | request-response | `routers/chats.py` :14-26 (router-level `get_linked_identity`) and `routers/auth.py` :58-69 (route-level dep + `response_model`) | exact |
| `src/nativespeaker/api/app/dependencies.py` (MODIFY — a `get_*_service` provider) | config/wiring | request-response | `get_auth_service` :101-108 and `get_chat_service` :75-86 | exact |
| `src/nativespeaker/api/app/main.py` (MODIFY — only if a new router module) | config/wiring | n/a | `app.include_router(auth_router)` :43-47 | exact |
| `src/nativespeaker/api/routers/__init__.py` (MODIFY — only if a new router module) | config/wiring | n/a | same file :1-7 | exact |
| `src/nativespeaker/api/services/__init__.py` (MODIFY — only if a new service module) | config/wiring | n/a | same file :1-6 | exact |
| `tests/unit/test_app_wiring.py` (MODIFY) | test | n/a | same file :11-12, :39-44 | exact |
| `tests/unit/test_sync_resolver.py` (NEW — the service's policy) | test | n/a | `tests/unit/test_quota_resolver.py` | exact |
| `tests/unit/test_sync_endpoint.py` (NEW — the route, if the planner wants route-level coverage) | test | n/a | `tests/unit/test_challenge_endpoint.py` :75-101 | exact |
| `tests/e2e/test_sync.py` (NEW) | test | n/a | `tests/e2e/test_create_user.py` + `tests/e2e/conftest.py` fixtures | exact |
| `specs/auth-refactor-phases/SHARED-INVARIANTS.md` (MODIFY — D-03) | docs | n/a | — | n/a |
| `.planning/REQUIREMENTS.md` (MODIFY — D-04, D-05) | docs | n/a | the Phase 37.1/37.2 dated amendment blocks at :12-14 | exact |
| `.planning/ROADMAP.md` (MODIFY — D-05, criterion 4) | docs | n/a | — | n/a |

Files explicitly **not** touched: `migrations/20260818_01_initial-release.sql`, `tests/schema/*`,
`src/nativespeaker/api/errors.py` (D-07 reuses the three existing classes), `logs.py` (D-02 adds no
event), `specs/auth-refactor-phases/03-sync.md` (marked verbatim).

## Repository rules that bind every file below

From `ns-api-gateway/AGENTS.md`:

- **Layering (37.5 D-01):** `routers/` holds the handler and takes `Depends()` only; `services/`
  holds the logic and the transaction boundary; `crud/` holds *every* query; `schemas/` holds the
  response body. Exception 4 is directly relevant here: *"A fail-closed read may raise its own
  rejection, so the rejection stays with the query in `crud/`."* — but note that `QuotaService`
  puts the three tripwire raises in the **service**, not in `GrantsDB`, so sync should follow
  `quota.py` and keep them in the service too.
- **Docstrings — three lines maximum.** `tests/unit/test_docstring_bar.py` enforces this
  mechanically with `BASELINE = {"src": 0, "tests": 0, "tests/e2e": 0, "tests/schema": 0,
  "tests/unit": 0}` and asserts **equality, not `<=`**. Any four-line docstring added by this phase
  fails the suite.
- **Comments — default to none, one line each,** explaining the line below, never the design.
- **Function shape:** delete a function that is only a step.

## Pattern Assignments

### `src/nativespeaker/api/crud/grants.py` (crud, read-only query) — MODIFY

**Analog:** itself. The predicate must stay one definition (CONTEXT.md § Claude's Discretion).

Current state, in full — this is the body the planner has to factor:

```python
"""Entitlement reads over `core.access_grants`. Global lock order: grant rows ascending by id, then usage rows."""
from datetime import datetime
from uuid import UUID

from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.tables import AccessGrant, AccessGrantStatus, AccessTier, UserMonthlyUsage


class GrantsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."""
        statement = (
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id,
                   # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
                   col(AccessGrant.status) == AccessGrantStatus.active,
                   col(AccessGrant.starts_at) <= evaluated_at,
                   or_(col(AccessGrant.ends_at).is_(None),
                       col(AccessGrant.ends_at) > evaluated_at))
            .order_by(col(AccessGrant.id).asc())
            # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
            .with_for_update()
        )
        # No `.limit(...)`: the caller must see a second effective grant and fail closed on it.
        return list((await self.session.exec(statement)).all())

    async def lock_usage(self, grant_id: UUID) -> UserMonthlyUsage | None:
        """Lock and return `grant_id`'s usage row, or `None`. Second in the lock order and never first."""
        # Never inserts: `None` is the fail-closed signal, not a cue to mint a row and hand out an allowance.
        statement = (
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id)
            .with_for_update()
        )
        return (await self.session.exec(statement)).first()

    async def monthly_credits(self, tier_id: str) -> int | None:
        statement = select(AccessTier.monthly_credits).where(col(AccessTier.id) == tier_id)
        return (await self.session.exec(statement)).first()
```

**Facts the planner needs to choose a factoring:**

- The whole locking difference is the single trailing `.with_for_update()` on
  `lock_effective_grants` and on `lock_usage`. `monthly_credits` already takes no lock and can be
  called by sync unchanged.
- The module docstring names the lock order, so if a non-locking sibling lands here the docstring
  must stay ≤ 3 lines and stay true.
- The three inline comments are load-bearing rules, not steps. Whichever factoring is chosen, the
  `== active` comment and the "No `.limit(...)`" comment must end up attached to the one surviving
  predicate expression — they explain the predicate, and duplicating them into two methods would be
  the drift CONTEXT.md forbids.
- The `.with_for_update()` line carries its own comment about Postgres rejecting `FOR UPDATE` with
  an eager-loading join. That comment belongs to the locking variant only; a non-locking read has no
  such constraint.
- `AccessGrant.id` is `uuid7`, so `ORDER BY id ASC` is insertion order. The non-locking read must
  keep the same ordering, or a two-grant tripwire could report a different grant than quota picks.
- `tests/unit/test_quota_resolver.py` asserts the compiled SQL of statement 0 contains
  `"FOR UPDATE"` and `"ORDER BY core.access_grants.id ASC"` (`:277-281`). Any refactor that changes
  statement order or drops the lock on the quota path breaks that file.

**Function-shape check (AGENTS.md):** a private helper that only builds the `where(...)` tuple is a
step, and inlining it would leave the call site unreadable *only if* the name carries the rule.
`_effective_grant_predicate` does carry the rule ("effective at `evaluated_at`"), so it survives the
check — but a `bool` parameter such as `lock: bool = True` on the existing method is the smaller
edit and keeps one statement builder. Both are within the discretion CONTEXT.md grants; the planner
must pick one and say why.

---

### The sync service (service, read-only aggregate) — NEW logic

**Analog:** `src/nativespeaker/api/services/quota.py::QuotaService.charge` — the reference
implementation of exactly the same read.

**Full analog body** (`services/quota.py:1-82`):

```python
"""Quota consumption: the one place an allowance is resolved and spent.
A failed provider call is not refunded."""
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud import GrantsDB
from nativespeaker.api.errors import (
    MissingUsageRowError,
    MultipleEffectiveGrantsError,
    QuotaExceededError,
    UnknownTierError,
)

logger = structlog.get_logger()


class QuotaService:

    def __init__(self, session_factory: async_sessionmaker | Callable[[], AsyncSession]) -> None:
        self.session_factory = session_factory

    async def charge(self, *, user_id: UUID, evaluated_at: datetime) -> None:
        """Spend one unit of `user_id`'s allowance, or raise. Commits on success."""
        # Its own short session: no grant or usage row lock is held across the provider round trip.
        async with self.session_factory() as session:
            try:
                grants_db = GrantsDB(session)
                grants = await grants_db.lock_effective_grants(user_id, evaluated_at)

                if not grants:
                    # Labels come from a closed set only: a fixed branch name, never an id or a raw path.
                    logger.warning("quota_rejected", branch="no_effective_grant")
                    raise QuotaExceededError("No effective grant for this user")

                if len(grants) > 1:
                    # A tripwire, not a recovery branch: a partial unique index makes it unreachable.
                    logger.error("quota_integrity_failure", branch="multiple_effective_grants")
                    raise MultipleEffectiveGrantsError(len(grants), user_id)

                grant = grants[0]

                # Second in the lock order, always after the grant rows.
                usage = await grants_db.lock_usage(grant.id)
                if usage is None:
                    # Fail closed, never mint: a grant without a usage row is a failed write, not a fresh allowance.
                    logger.error("quota_integrity_failure", branch="missing_usage_row")
                    raise MissingUsageRowError(grant.id)

                # The only place the period is derived, and always from the request's captured instant.
                period = evaluated_at.strftime("%Y-%m")

                if usage.monthly_period != period:
                    # Rollover runs before the comparison and in the same transaction: no reset commits uncharged.
                    usage.monthly_used = 0
                    usage.monthly_period = period

                allowance = await grants_db.monthly_credits(grant.tier_id)
                if allowance is None:
                    # Fail closed: a missing tier row is neither a zero allowance nor an unbounded one.
                    logger.error("quota_integrity_failure", branch="unknown_tier")
                    raise UnknownTierError(grant.tier_id, grant.id)

                # Floored at zero: a stored count above the allowance is ordinary exhaustion.
                remaining = max(allowance - usage.monthly_used, 0)
                if remaining == 0:
                    # Raised before the increment: a request the service refused must never be charged.
                    logger.warning("quota_rejected", branch="allowance_exhausted")
                    raise QuotaExceededError("The allowance for the current period is used up")

                # `updated_at` is stamped from the captured instant, not a clock.
                usage.monthly_used += 1
                usage.updated_at = evaluated_at

                await session.commit()
            except Exception:
                await session.rollback()
                raise
```

**What sync copies, line for line:**

| Quota line | Sync's version |
|---|---|
| `grants = await grants_db.lock_effective_grants(user_id, evaluated_at)` | the non-locking sibling, same arguments |
| `if not grants:` → `QuotaExceededError` | → the zero-grant answer: `type = "none"`, `status = "none"`, `tier_id = None`, `monthly_credits = None`, `monthly_used = 0`, `current_period = period`. Not an error, and no log line (D-02). |
| `if len(grants) > 1:` → `MultipleEffectiveGrantsError(len(grants), user_id)` | identical (D-07) |
| `usage = await grants_db.lock_usage(grant.id)` → `if usage is None: MissingUsageRowError(grant.id)` | identical (D-07) — this is the **deliberate divergence from the brief**, which said report `0` |
| `period = evaluated_at.strftime("%Y-%m")` | identical, and the *only* place `current_period` comes from |
| `if usage.monthly_period != period: usage.monthly_used = 0` | the same rule, but **as a read only** — sync must compute `0` without assigning to the row (a mutation would break roadmap criterion 3 and D-06's read-only rule) |
| `allowance = await grants_db.monthly_credits(grant.tier_id)` → `if allowance is None: UnknownTierError(...)` | identical (D-07); the value becomes `monthly_credits` |
| `remaining` / the increment / `usage.updated_at` / `session.commit()` | **not copied** — sync spends nothing and commits nothing |

**Structured-log labels** (`quota.py:36-37`): the comment `# Labels come from a closed set only: a
fixed branch name, never an id or a raw path.` is the repo's rule. D-02 says sync emits **no new
event at all**, so the three `logger.error("quota_integrity_failure", branch=...)` lines are the
only thing to consider mirroring — and even those are optional, since the errors already log at
`ERROR` via `AppError.log_level`. Do not add an `auth_sync_succeeded` event, a user id label, or any
per-attempt telemetry.

**Session strategy — the one place sync should *not* copy quota.** `QuotaService` takes a
`session_factory` and opens *its own short session* because it commits mid-request while the request
session stays open (see `get_quota_service`'s comment at `dependencies.py:70`). Sync commits
nothing, so it should take the request session directly, the way `AuthService` does:

```python
# services/auth.py:28-40
class AuthService:

    def __init__(self,
                 db: AsyncSession,
                 challenge_store: ChallengesDB,
                 adapter,
                 evaluated_at: datetime) -> None:
        self.session = db
        self.identities_db = IdentitiesDB(db)
        self.challenge_store = challenge_store
        self.adapter = adapter
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
```

**Placement note for the planner:** `AuthService.__init__` requires `challenge_store` and `adapter`,
neither of which a read-only sync needs, and `get_auth_service` resolves both. Adding a sync method
to `AuthService` therefore drags a Firebase adapter and a challenge store into a route that reads
neither. A separate class (`services/sync.py`, constructed with `db` + `evaluated_at` only) keeps
the dependency graph honest. Either way the `__init__` shape above — assign `db`, construct the
`*DB` wrapper over it, store `evaluated_at` with its one-line comment — is the pattern.

---

### `src/nativespeaker/api/schemas/auth.py` (schema, request-response) — MODIFY

**Analog:** the response models already in this file.

**Full current file** (`schemas/auth.py:1-41`):

```python
"""The auth request and response bodies, and the identity a verified credential resolves to."""
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field

from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User


class ChallengeRequest(BaseModel):
    """The issuance body. `operation` is a plain `str`, never a Literal: an unissuable value is the handler's 400."""
    operation: str


class PrepareResponse(BaseModel):
    """The prepare body: the handle and its expiry, and nothing else about the challenge is disclosed."""
    challenge_id: str
    expires_at: datetime


class CreateUserRequest(BaseModel):
    """The completion body: the handle obtained from `/auth/challenge`, and nothing else."""
    # Required and non-empty, so an unusable handle is the framework's 422 rather than a not-found 409.
    # The length counts characters, so a padded handle stays a distinct value and reaches the store untrimmed.
    challenge_id: str = Field(..., min_length=1)


class CompletionResponse(BaseModel):
    """The completion body: the registration state, and nothing else."""
    identity_provider: IdentityProvider


@dataclass(frozen=True, slots=True)
class Identity:
    """A verified `(issuer, subject)` and the rows it resolved to, both `None` when it is unlinked."""
    issuer: str
    subject: str
    user: User | None = None
    identity: ExternalIdentity | None = None
```

**Conventions to copy exactly:**

- Plain `pydantic.BaseModel`. **No `model_config`, no `ConfigDict`, no validators anywhere in this
  file or in `schemas/api.py`.** Do not introduce one.
- Bare annotations for required fields; `Field(...)` only when a constraint is being added
  (`min_length=1` on `CreateUserRequest`). `schemas/api.py` uses `Field(..., max_length=4096)` and
  `Field(default=None, ...)` the same way.
- **Enum types go straight on the field**: `identity_provider: IdentityProvider` — the existing
  `CompletionResponse` already types this exact field with the exact enum the new response needs.
  `IdentityProvider` is a `StrEnum` (`tables/identities.py:11-15`) with members
  `anonymous | google | apple`, so it serialises to the spec's strings with no extra work.
- One-line docstring per model, in the shape *"The X body: the Y, and nothing else."*
- A nested model is a second `BaseModel` class in this file, referenced by annotation. There is no
  existing nested-response example in the repo, so the `entitlement` block is the first — declare
  it as its own class above the wrapper (top-down order matches the file's existing flow: request
  model, then response model).

**Shape pinned by D-06 / `req~sessions-sync-entitlement-response-shape~1`:**

```json
{"entitlement": {"type": "...", "status": "...", "tier_id": null,
                 "monthly_credits": null, "current_period": "2026-09", "monthly_used": 0},
 "identity_provider": "google"}
```

- `type`: closed enumeration `none | subscription | anonymous_device_grant |
  registered_account_grant | manual`. The last four are exactly `AccessGrantSource`
  (`tables/grants.py:11-16`) — so `type` is `AccessGrantSource | None`-plus-`"none"`, not a free
  string. The `"none"` member has no `AccessGrantSource` counterpart, which is the one place a new
  schema-level enum (or a `Literal["none"]` union) is justified.
- `status`: exactly `none | active`. `AccessGrantStatus` (`tables/grants.py:19-23`) has
  `active | revoked | expired`, so it is **not** the right type for this field: `revoked` and
  `expired` must never reach the wire (D-06). Declare the public two-member enum separately.
- `tier_id: str | None`, `monthly_credits: int | None`, `current_period: str` (never null),
  `monthly_used: int` (never null).

---

### The `/auth/sync` handler (router, request-response) — NEW

Two live analogs; the planner picks the placement.

**Analog A — router-level narrowing** (`routers/chats.py:1-26`), which is what sync needs:

```python
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from nativespeaker.api.app.dependencies import (
    get_chat_service,
    get_linked_identity,
)
from nativespeaker.api.schemas.api import ChatRequest, ChatResponse, MessageRequest, MessageResponse
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.services import ChatService

# Authentication is default-on for every route on this router.
router = APIRouter(tags=["chats"], dependencies=[Depends(get_linked_identity)])


@router.get("/chats",
            response_model=list[ChatResponse],
            summary="List chats",
            description="Returns all chat sessions belonging to the authenticated user.")
async def list_chats(identity: Identity = Depends(get_linked_identity),
                     service: ChatService = Depends(get_chat_service)):
    chats = await service.list_chats(identity.user.id)
    return [ChatResponse(chat_id=chat.id, title=chat.title,
                         created_at=chat.created_at, lang=chat.lang)
            for chat in chats]
```

**Analog B — the current auth router** (`routers/auth.py:29-30, 58-69`), whose router-level
dependency is deliberately *un*narrowed:

```python
# Auth is default-on, and deliberately unnarrowed: an already-linked caller is a 409 here, not a 401.
router = APIRouter(tags=["auth"], dependencies=[Depends(get_identity)])


@router.post("/auth/create-user",
             response_model=CompletionResponse,
             summary="Create the account for a verified but unlinked identity",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and creates the account.")
async def create_user(body: CreateUserRequest,
                      identity: Identity = Depends(get_identity),
                      service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete(identity=identity, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)
```

**Router conventions, from both files:**

- `APIRouter(tags=[...], dependencies=[Depends(<the identity dependency>)])`, with a one-line
  comment above it stating *why* that dependency and not the other one.
- Full path in the decorator (`"/auth/create-user"`, `"/chats"`) — there is no `prefix=`.
- `response_model=` plus a return annotation of the same type. `summary=` always; `description=`
  where the route needs one. No explicit `status_code=` for a 200 (only `chats.py:79`'s delete sets
  `status_code=204`).
- The handler re-declares `identity: Identity = Depends(get_linked_identity)` even when the router
  already declares it. `dependencies.py:56` explains why that is free: FastAPI caches solver-resolved
  dependencies, and `tests/unit/test_app_wiring.py::test_one_verify_and_one_query_for_a_doubly_declared_route`
  asserts one verify and one query for a doubly-declared route.
- Handler body: one `await service.<verb>(...)` call, then construct the response model. **No logic.**
- `identity.user.id` is read directly (`chats.py:23`) — `get_linked_identity` has already rejected
  `user is None`, so no defensive check belongs in the handler.
- A handler docstring is optional (`chats.py` has none; `auth.py`'s are one line).

**The placement decision (CONTEXT.md discretion), with the facts:**

`routers/auth.py`'s router-level `Depends(get_identity)` cannot be narrowed for one route by adding
a route-level `Depends(get_linked_identity)` *silently* — it works, but
`tests/unit/test_app_wiring.py:12` hardcodes `PREAUTH_CALLABLE_PATHS = {"/auth/create-user",
"/auth/challenge"}` and `test_every_route_but_the_two_exemptions_requires_a_linked_identity` demands
`get_linked_identity` in the declared set for every path outside that literal set. So:

- **Route-level dep on the existing `auth_router`:** `/auth/sync` gets both `get_identity` (from the
  router) and `get_linked_identity` (from the route). It passes
  `test_every_route_but_the_two_exemptions...` and `test_the_public_allowlist...` with **no edit to
  the test's literal sets**, because it is not in `PREAUTH_CALLABLE_PATHS` and does declare
  `get_linked_identity`. Note `test_the_preauth_callable_route_still_resolves_the_identity` only
  iterates paths *in* `PREAUTH_CALLABLE_PATHS`, so it is unaffected.
- **A new router module:** requires edits to `routers/__init__.py`, `app/main.py` and the
  `routers/auth.py` module docstring (`"""The two auth routes: ..."""` becomes wrong either way if
  the route lands there — that docstring must be updated in the first option too, and stay ≤3 lines).

---

### `src/nativespeaker/api/app/dependencies.py` (wiring) — MODIFY

**Analog:** `get_auth_service` (`:101-108`) — the same shape sync needs (request session, one
captured instant), minus the two collaborators sync does not use:

```python
def get_auth_service(db: AsyncSession = Depends(get_db),
                     challenge_store: ChallengesDB = Depends(get_challenge_store),
                     adapter=Depends(get_firebase_adapter)) -> AuthService:
    return AuthService(db=db,
                       challenge_store=challenge_store,
                       adapter=adapter,
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC))
```

and `get_chat_service` (`:74-86`), which carries the ordering rule:

```python
# Defined below the dependencies it declares, because its `Depends()` defaults are evaluated at definition time.
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config),
                     quota_service: QuotaService = Depends(get_quota_service)) -> ChatService:
    return ChatService(db=db,
                       ...
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC))
```

**Rules this file enforces:**

- `evaluated_at=datetime.now(UTC)` is passed **from the dependency**, with the verbatim comment
  `# One instant for this request; nothing downstream reads the clock again.` This is the mechanism
  that satisfies `req~sessions-sync-single-evaluation-time~2`; it is not a new mechanism.
- The provider is a plain `def` (not `async def`), returns the constructed service, and is placed
  **below** every dependency it names.
- `get_db` (`:22-29`) yields the request session and **commits on exit**. For a strictly read-only
  sync that commit is a no-op on an unmodified session, so `Depends(get_db)` is correct and the
  planner does not need `get_session_factory`. It also means the service must not leave dirty
  objects on the session — another reason the stale-period branch must compute `0` rather than
  assign `usage.monthly_used = 0` the way `charge` does. **This is the single highest-risk line in
  the phase**: copying quota's two assignment lines verbatim would silently commit a rollover from a
  read-only endpoint and break roadmap criterion 3.

The barrier itself needs no change:

```python
# dependencies.py:56-61
# Declared, never called directly: FastAPI's cache only sees solver-resolved deps, so a direct call re-verifies.
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> Identity:
    """The resolved user and identity row; rejects an unlinked caller with 403."""
    if identity.user is None:
        raise PreAuthIdentityNotAllowed
    return identity
```

---

### `src/nativespeaker/api/app/main.py` + the two `__init__.py` files (wiring) — MODIFY only if a new module lands

```python
# app/main.py:42-48
# Each router declares its own auth dependency; health declares none, being the whole public allowlist.
app.include_router(root_router)
app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
register_exception_handlers(app)
```

```python
# routers/__init__.py — `__all__` first, alphabetical, one aliasing import per router
__all__ = ["auth_router", "chats_router", "examples_router", "health_router", "root_router"]

from nativespeaker.api.routers.auth import router as auth_router
...
```

```python
# services/__init__.py — same shape, no aliasing
__all__ = ["AuthService", "ChatService", "LLMService", "QuotaService"]

from nativespeaker.api.services.auth import AuthService
...
```

`crud/__init__.py` follows the identical pattern (`__all__ = ["ChallengesDB", "ChatsDB", "GrantsDB",
"IdentitiesDB"]`) and needs no edit — `GrantsDB` is already exported, so a new method on it is
reachable as `from nativespeaker.api.crud import GrantsDB`, exactly as `quota.py:11` imports it.

---

### `tests/unit/test_sync_resolver.py` (test) — NEW

**Analog:** `tests/unit/test_quota_resolver.py` — same subject, same stubs, reusable wholesale.

The stub harness (`:31-81`) is the piece to copy. It fakes a session by dispatching on the
statement's target entity, which is what lets a unit test assert both the values and the SQL:

```python
class _StubSession:
    """Stands in for the short session the charge opens, keeping every statement it was asked to run."""

    _ENTITY_KEY = {AccessGrant: "grants", UserMonthlyUsage: "usage", AccessTier: "allowance"}

    def __init__(self, *, grants=(), usage=None, allowance=ALLOWANCE):
        self._rows = {"grants": list(grants),
                      "usage": [] if usage is None else [usage],
                      "allowance": [] if allowance is None else [allowance]}
        self.statements = []
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def exec(self, statement):
        self.statements.append(statement)
        entity = statement.column_descriptions[0]["entity"]
        return _StubResult(self._rows[self._ENTITY_KEY[entity]])

    @property
    def entities(self) -> list[str]:
        """The target entity of each statement, in the order the resolver issued them."""
        return [self._ENTITY_KEY[s.column_descriptions[0]["entity"]] for s in self.statements]
```

The SQL-assertion helper (`:120-122`) is how this phase proves sync takes **no lock** — the exact
inverse of the quota assertions at `:277-290`:

```python
def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))

# quota's assertions, which sync's must mirror in the negative:
assert "FOR UPDATE" in sql
assert "ORDER BY core.access_grants.id ASC" in sql
```

Sync's version: `assert "FOR UPDATE" not in _compiled(session.statements[0])` alongside the same
`ORDER BY core.access_grants.id ASC`, plus the four predicate-boundary assertions verbatim
(`:292-309`) — inclusive `starts_at <=`, exclusive `ends_at >`, `ends_at IS NULL` — which is how the
planner *proves* the predicate did not drift, rather than asserting it did not.

Read-only proof, adapted from `test_nothing_is_minted` (`:169-175`) and the stub's `committed` flag:

```python
assert session.added == []
assert session.entities == ["grants", "usage", "allowance"]
```

plus `assert session.committed is False` and, for the stale-period case, that the usage row's
`monthly_period` and `monthly_used` are **unchanged** after the call — the mirror of quota's
`TestLazyRollover` (`:245-249`), which asserts the opposite.

Fixture/constant conventions to copy (`:23-28`, `:84-99`): module-level `USER_ID = uuid7()`,
`TIER_ID = "registered"`, a fixed `EVALUATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)` with its
`PERIOD` and `STALE_PERIOD` strings, and `_grant()` / `_usage()` builders using the `...` sentinel
for "default unless overridden". Test classes are named `TestX` with a one-line docstring stating
the rule; `async def test_...` with no `@pytest.mark.asyncio` (unit tests run under an auto mode).

---

### `tests/unit/test_sync_endpoint.py` (test) — NEW, optional

**Analog:** `tests/unit/test_challenge_endpoint.py:75-101` — the route mounted on a bare `FastAPI()`
with the barrier's context supplied by overrides:

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

For sync the override is `get_linked_identity` with an `Identity` carrying a real `User`. Note the
recording session's guard rails at `:57-61`, which are exactly the read-only assertion this endpoint
wants:

```python
    async def commit(self):
        raise AssertionError("no path in this module may commit")

    async def rollback(self):
        raise AssertionError("no path in this module may roll back")
```

Response assertions use the **key set**, never two known keys (`:110-111`):

```python
# The key set, not two known keys: a third field would pass the weaker check.
assert set(response.json()) == {"challenge_id", "expires_at"}
```

---

### `tests/unit/test_app_wiring.py` (test) — MODIFY

The literal sets and the assertions the new route must satisfy (`:8-44`):

```python
DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# Literals rather than derived from anything, so widening the exemption is a visible edit here.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}


def _declared(route: APIRoute) -> list:
    """The callables FastAPI resolved for this route, router-level declarations included."""
    return [dependency.call for dependency in route.dependant.dependencies]


    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   and get_linked_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"
```

**`/auth/sync` must NOT be added to either literal set** — `req~sessions-sync-not-preauth-callable~1`
says so, and the existing assertion already covers the new route once it declares
`get_linked_identity`. The likely edit here is therefore an *addition*, not a change: a test naming
`/auth/sync` and asserting `get_linked_identity in _declared(route)` — mirroring the shape of
`test_the_preauth_callable_route_still_resolves_the_identity` (`:33-37`). Also note `_declared`
returns router-level declarations too, so a route-level narrowing is visible to it.

Related, **do not change**: `tests/unit/test_challenge_endpoint.py:123` lists `"sync"` in
`_NOT_ISSUABLE`. `/auth/sync` is not challenge-bearing
(`req~sessions-api-sync-audited-attempt-path~1` says it has no prepare mode), so `"sync"` stays an
unissuable operation and that test stays exactly as it is.

---

### `tests/e2e/test_sync.py` (test) — NEW

**Analogs:** `tests/e2e/conftest.py` for fixtures, `tests/e2e/test_create_user.py` for shape.

Every fixture sync needs already exists in `tests/e2e/conftest.py`:

| Fixture / helper | Line | What it gives sync |
|---|---|---|
| `async_client` | :98-104 | a client over the real app with a real Firebase token attached |
| `linked_firebase_identity` | :163-168 | the seeded `(User, ExternalIdentity)` pair that makes the caller linked |
| `quota_grant` | :195-199 | one effective grant plus its usage row for that caller |
| `seed_grant(...)` | :219-249 | the parameterised seeder: `status`, `starts_at`, `ends_at`, `monthly_period`, `monthly_used`, `with_usage=False` — every case D-06/D-07 needs |
| `seed_identity(...)` | :171-192 | a second caller, or a non-`google` `provider` for the `identity_provider` field |
| `_db_transaction` | :114-137 (autouse) | wraps each test in a rolled-back transaction, swapping the app's session factory so app writes join it |
| `REGISTERED_TIER_ID = "registered"` | :32 | the migration-seeded tier at 50 monthly credits |

`seed_grant`'s own comment names the fail-closed case this phase reuses (`:230`):

```python
    # A grant with no usage row is a 500 rather than a 429, so with_usage=False is only for that case.
```

Module and assertion shape, from `test_create_user.py:1-20, 37-54, 85-90`:

```python
"""An unlinked caller goes from no account to an account, unstubbed but for the verifier and the adapter."""
import pytest
...
pytestmark = pytest.mark.e2e


async def _count(factory, statement) -> int:
    async with factory() as session:
        return (await session.exec(statement)).one()


_GRANTS = select(func.count()).select_from(AccessGrant)
_MONTHLY_USAGE = select(func.count()).select_from(UserMonthlyUsage)


@pytest.mark.asyncio(loop_scope="module")
class TestTheAnonymousHappyPath:
    """One unlinked caller, one issued challenge, one completion, and the exact row set that must result."""

    async def test_an_unlinked_caller_creates_an_anonymous_account(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        ...
        assert completion.status_code == 200
        assert completion.json() == {"identity_provider": "anonymous"}
```

Note `assert completion.json() == {...}` — the **whole body**, compared as a dict literal. That is
the right assertion for sync's spec-pinned response, and it is how roadmap criterion 2 ("zero
effective grants and a lapsed grant return byte-identical responses") gets tested: call sync twice
against two different seeded states and compare the two `response.json()` values to each other.

`_assert_step_10s_global_invariants` (`:50-54`) is the template for roadmap criterion 3 — a helper
that counts `core.*` rows and is called before and after the request:

```python
async def _assert_step_10s_global_invariants(factory) -> None:
    """Two rules hold after every completion here: no entitlement is minted anywhere, display_name stays NULL."""
    assert await _count(factory, _GRANTS) == 0
    assert await _count(factory, _MONTHLY_USAGE) == 0
    assert await _count(factory, _USERS_CARRYING_A_NAME) == 0
```

For the barrier's own rejections, `tests/e2e/test_unauthenticated_access.py:20-25` shows the shape:

```python
    async def test_unauthenticated_root_is_rejected(self, unauthenticated_client):
        """GET / with no Authorization header returns 401 auth_required."""
        async with unauthenticated_client as client:
            response = await client.get("/")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
```

---

### Documentation files

**`specs/auth-refactor-phases/SHARED-INVARIANTS.md`** (D-03) — the clauses to strike are at
`:51-53`, `:57` and `:58`. `:51` is the `## Audit` heading; `:52-53` are the two clauses that
mandate the durable row and the route→operation metadata; `:57` and `:58` mention audit rows while
also carrying non-audit substance (the counter metric, the admission-phase rule), so those two need
editing rather than deletion. `:48` mentions `core.auth_event_result` values and needs checking too.
There is no in-repo analog for editing this file; D-03 says no flagged-conflict entry is added,
because after the edit there is no surviving text to conflict with.

**`.planning/REQUIREMENTS.md`** (D-04, D-05) — the dated-amendment format is established at the top
of the file by Phase 37.1 and 37.2:

> `> **Amended by Phase 37.1 (2026-08-24) for two deletions.** ... Every requirement those deletions
> touched carries a note saying which treatment it got and why: **amended** (mechanism changed,
> substance intact), **withdrawn** (its subject no longer exists), or **flagged forward** (an unbuilt
> phase must decide for itself).`

Phase 38's SYNC-03 amendment uses the same blockquote + bolded lead + the same three-word
vocabulary. SYNC entries are at `:190-197`; the flagged-conflicts table is at `:461`; the three
sibling entries (`APPLEHOOK-02`, `PLAYHOOK-03`, `SIGNOUT-02`) are amended per D-04.

**`.planning/ROADMAP.md`** (D-05) — Phase 38 success criterion 4 is the long **BLOCKED:** paragraph;
D-01 chooses option (b), so it is rewritten to describe what is built. Criteria 1–3 stand.

## Shared Patterns

### One captured instant per request

**Source:** `app/dependencies.py:85-86` and `:107-108`, `services/auth.py:39-40`,
`services/quota.py:54-55`
**Apply to:** the dependency provider, the service `__init__`, and every derivation of
`current_period`

```python
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC))
```

```python
                # The only place the period is derived, and always from the request's captured instant.
                period = evaluated_at.strftime("%Y-%m")
```

`tests/unit/test_quota_resolver.py:333` has a whole class for this
(`TestTheResolverReadsNoClock`), which is the analog for sync's equivalent assertion.

### Fail-closed tripwires reused unchanged (D-07)

**Source:** `errors.py:213-242`
**Apply to:** the sync service, verbatim — this phase adds no error class

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
        ...


class UnknownTierError(InternalError):
    """A grant whose `tier_id` has no `core.access_tiers` row."""
    # A foreign key makes this unreachable; the silent readings are a wrong 429 or a free service.
    log_level = logging.ERROR

    def __init__(self, tier_id: str, grant_id: UUID):
        ...
```

All three inherit `InternalError` (`:131-136`: `status = 500`, `code = "internal_error"`), so the
client sees `{"code": "internal_error"}` and nothing more. `log_level = logging.ERROR` means
`app_error_handler` already logs them — which is why D-02 needs no new event on any failure path
either.

Assertion pattern for these, from `test_quota_resolver.py:154-160`:

```python
        assert (caught.value.status, caught.value.code) == (500, "internal_error")
        assert not isinstance(caught.value, QuotaExceededError)
```

### Structured-log labels from a closed set

**Source:** `services/quota.py:36-37`, restated in `routers/auth.py:44-45`
**Apply to:** any log line this phase writes — though D-02 says it should write none

```python
                    # Labels come from a closed set only: a fixed branch name, never an id or a raw path.
                    logger.warning("quota_rejected", branch="no_effective_grant")
```

```python
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
```

`logger = structlog.get_logger()` at module level is the convention in `routers/auth.py:27`,
`services/auth.py:25`, `services/quota.py:19`.

### The read-only guarantee

**Sources:** `dependencies.py:22-29` (`get_db` commits on exit),
`tests/unit/test_quota_resolver.py:174` (`assert session.added == []`),
`tests/unit/test_challenge_endpoint.py:57-61` (a session that raises on `commit`),
`tests/e2e/test_create_user.py:50-54` (before/after row counts)
**Apply to:** the service, and to all three test layers

Concretely: no `session.add(...)`, no attribute assignment on a loaded `AccessGrant`,
`UserMonthlyUsage` or `User`, no `session.commit()` in the service. `get_db`'s trailing commit is a
no-op only if the session is clean, so the stale-period branch must not write.

## No Analog Found

None. Every code file this phase creates or modifies has a same-role, same-data-flow analog already
in the repository.

The two things without a precedent are both *within* files that have analogs:

| Thing | File | Why it is new |
|---|---|---|
| A nested Pydantic response model (`entitlement` inside the top-level body) | `schemas/auth.py` | Every existing response body in `schemas/auth.py` and `schemas/api.py` is flat. The declaration mechanics are unchanged — a second `BaseModel` referenced by annotation — but there is no in-repo example to copy. |
| A public two-member `status` enum that is not `AccessGrantStatus` | `schemas/auth.py` | The tables enum has three members and two of them (`revoked`, `expired`) are forbidden on the wire by D-06. Every other enum-typed response field in the repo (`CompletionResponse.identity_provider`) reuses a `tables/` enum directly; this one cannot. |

## Metadata

**Analog search scope:** `src/nativespeaker/api/{routers,services,crud,schemas,app,tables}/`,
`tests/unit/`, `tests/e2e/`, `specs/auth-refactor/`, `specs/auth-refactor-phases/`, `.planning/`
**Files read in full:** `services/quota.py`, `crud/grants.py`, `app/dependencies.py`,
`routers/auth.py`, `routers/chats.py`, `app/main.py`, `schemas/auth.py`, `schemas/api.py`,
`services/auth.py`, `tables/grants.py`, `tests/unit/test_app_wiring.py`,
`tests/unit/test_docstring_bar.py`, `tests/e2e/conftest.py`,
`tests/e2e/test_unauthenticated_access.py`, the three `__init__.py` barrels
**Files read in part:** `errors.py` (:120-249), `tests/unit/test_quota_resolver.py` (:1-330),
`tests/unit/test_challenge_endpoint.py` (:1-134), `tests/e2e/test_create_user.py` (:1-120),
`specs/auth-refactor/01-sessions-and-identity-resolution.md` (the two named sections)
**Pattern extraction date:** 2026-09-01
