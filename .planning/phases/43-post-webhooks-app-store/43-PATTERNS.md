# Phase 43: POST /webhooks/app-store - Pattern Map

**Mapped:** 2026-09-04
**Files analyzed:** 27 (9 new source, 6 new test, 12 edited)
**Analogs found:** 26 / 27

Every analog path below was checked with `git ls-files` and is tracked source in this submodule.
Line numbers are from the working tree at `f5c0cdb`.

## File Classification

### New source files

| New file | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|
| `src/nativespeaker/api/auth/app_store.py` | auth (external-SDK seam) | transform (verify → frozen value) | `src/nativespeaker/api/auth/devicecheck.py` | exact |
| `src/nativespeaker/api/routers/webhooks.py` | router + handler | request-response | `src/nativespeaker/api/routers/users.py` | exact |
| `src/nativespeaker/api/services/subscriptions.py` | service | one transaction, then `commit()` | `src/nativespeaker/api/services/auth.py` | role-match |
| `src/nativespeaker/api/crud/subscriptions.py` | crud | CRUD under locks | `src/nativespeaker/api/crud/grants.py` | exact |

### Edited source files

| Edited file | Role | What is added | Analog inside the same file | Match |
|---|---|---|---|---|
| `src/nativespeaker/api/config.py` | config | `AppStoreConfig`, `AppConfig.app_store` | `DeviceCheckConfig` (`:58-62`), `AppConfig.devicecheck` (`:79`) | exact |
| `src/nativespeaker/api/app/dependencies.py` | dependency | `verify_app_store_notification`, `get_subscriptions_service` | `get_identity` (`:37-54`), `get_auth_service` (`:112-121`) | exact |
| `src/nativespeaker/api/app/lifespan.py` | lifespan | build `SignedDataVerifier`, set `app.state.app_store_notifications` | the devicecheck block (`:40-50`) | exact |
| `src/nativespeaker/api/app/main.py` | app wiring | `include_router(webhooks_router)` | `:44-49` | exact |
| `src/nativespeaker/api/errors.py` | error tree | `NotificationRejected`, `AttributionConflict`, `UnmappedStoreProduct` | `ProofRejected` (`:421-425`), `MissingUsageRowError` (`:218-225`) | exact |
| `src/nativespeaker/api/schemas/auth.py` | schema | the one-field request body | `CompletionRequest` (`:24-28`) | exact |
| `src/nativespeaker/api/tables/purchases.py` | tables | `Subscription`, `StorePurchase`, `SubscriptionEvent`, `SubscriptionStatus` | `StorePurchaseToken` (`:21-32`), `AccessGrant` in `tables/grants.py:49-65` | exact |
| `src/nativespeaker/api/{routers,crud,services,tables}/__init__.py` | barrel | one export each | each file's existing `__all__` + import block | exact |
| `config/config.yaml` | config | `app_store.products` only | the `db:` partial block (`:18-19`) | exact |
| `.env.example` | config docs | the Apple App Store block | the DeviceCheck block (`:67-81`) | exact |
| `k8s/templates/httproute-webhooks.yaml` | gateway | `/webhooks/apple` → `/webhooks/app-store` | the file itself (`:15`) | exact |

### New and edited test files

| Test file | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|
| `tests/unit/test_app_store_notifications.py` (new) | unit, seam | transform | `tests/unit/test_devicecheck_adapter.py` | exact |
| `tests/e2e/test_app_store_webhook.py` (new) | e2e, route | request-response | `tests/e2e/test_claim_registered_grant.py` | exact |
| `tests/schema/test_subscription_ingestion.py` (new) | schema, writer | CRUD on real PostgreSQL | `tests/schema/test_grant_locks.py` + `tests/schema/helpers.py` | role-match |
| `tests/schema/test_subscription_race.py` (new) | schema, race | two-connection race | `tests/schema/test_claim_race.py` | exact |
| `tests/e2e/conftest.py` (edit) | fixture | scripted fake on `app.state` | `FakeDeviceCheckAdapter` + `scripted_devicecheck_adapter` (`:224-263`) | exact |
| `tests/schema/helpers.py` (edit) | fixture | seed helpers | `insert_grant` / `insert_usage` (`:39-78`) | exact |
| `tests/unit/test_app_wiring.py` (edit) | unit, ratchet | structural set | the file's own two structural cases (`:28-32`, `:57-62`) | exact |
| `tests/unit/test_auth_package_shape.py` (edit) | unit, ratchet | literal triple | `CURRENT` (`:13`) | exact |
| `tests/unit/test_rejection_vocabulary.py` (edit) | unit, ratchet | literal frozenset | `EVENT_NAMES` (`:60-124`), `CONSTRUCTOR_ARGUMENTS` (`:146-166`) | exact |
| a single-writer walk for `AccessGrantSource.subscription` (optional, RESEARCH OQ-3) | unit | ast walk | `tests/unit/test_grant_sources.py` | role-match |

---

## Pattern Assignments

### `src/nativespeaker/api/auth/app_store.py` (auth seam, transform)

**Analog:** `src/nativespeaker/api/auth/devicecheck.py`

**Module docstring + no logger** (`devicecheck.py:1-2`) — copy the second sentence's shape, because the
same rule binds here (RESEARCH Pitfall 8):

```python
"""The Apple DeviceCheck integration: the two-bit query, the two-bit update, and one ES256 bearer per call.
A device token is a secret capability: this module holds no logger, so none is logged."""
```

**Imports** (`devicecheck.py:3-13`) — stdlib, third-party SDK, then the project's errors. No `structlog`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, Protocol
from uuid import uuid4

import httpx
import jwt
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt

from nativespeaker.api.errors import ProofRejected, Unavailable
```

**Frozen value type** (`devicecheck.py:34-39`) — `VerifiedNotification` copies this exactly, with
D-08's field names and no Apple type:

```python
@dataclass(frozen=True, slots=True)
class BitState:
    """The two bits Apple holds for one device, as one completed query reported them."""

    bit0: bool
    bit1: bool
```

**Protocol beside the implementation** (`devicecheck.py:42-51`) — the seam D-07/D-24 name. It stays in
this module, never in `auth/adapters.py`, whose import fence (`tests/unit/test_adapter_interfaces.py:23-24`)
admits only stdlib and `nativespeaker`:

```python
class DeviceCheckAdapter(Protocol):
    """The device-gate seam: one read of both bits, and one write of both."""

    async def read_bits(self, device_token: str) -> BitState:
        """The query call: the device's bit state, or a raise."""
        ...
```

**Absent credential raises `Unavailable` on use, never at construction** (`devicecheck.py:62-65`) —
D-07's "pass `None` and raise on use" is this shape:

```python
def _service_jwt(key_id: str | None, team_id: str | None, private_key: str | None, *, stage: str) -> str:
    """Mint the ES256 bearer Apple's server-to-server API requires, or fail closed having sent nothing."""
    if not (key_id and team_id and private_key):
        raise Unavailable(stage=stage)
```

**The class: constructor takes the built collaborator, methods are thin** (`devicecheck.py:113-126`) —
`AppStoreNotifications.__init__(self, *, verifier: SignedDataVerifier | None)` and one `verify` method:

```python
class AppleDeviceCheck:
    """Apple's two-bit device gate over HTTPS, signed per call with the configured ES256 key."""

    def __init__(self, *, key_id: str | None, team_id: str | None,
                 private_key: str | None, client: httpx.AsyncClient) -> None:
        self._key_id = key_id
        ...

    async def read_bits(self, device_token: str) -> BitState:
        """Ask Apple for this device's two bits and classify the answer."""
        response = await self._post(QUERY_PATH, _shared_body(device_token), stage="devicecheck_read")
        return _parse_bit_state(response, stage="devicecheck_read")
```

**One statement in the `try`, converted on the way out** (`devicecheck.py:137-141`) — D-07's three
library calls each get this shape; no nested `try`:

```python
        try:
            return await self._client.post(f"{DEVICECHECK_HOST}{path}", json=body,
                                           headers={"Authorization": f"Bearer {bearer}"})
        except httpx.HTTPError as failure:
            raise RetryableDeviceCheckError(type(failure).__name__) from failure
```

**Module constants named and commented** (`devicecheck.py:15-27`) — the two Apple OIDs and any
chain literal follow this: one comment stating why the value is what it is.

**Ratchet:** adding this module breaks `tests/unit/test_auth_package_shape.py:13` (`CURRENT = (5, 12, 35)`).
Re-measure and write the new triple in the same commit (RESEARCH P-06).

---

### `src/nativespeaker/api/routers/webhooks.py` (router + handler, request-response)

**Analog:** `src/nativespeaker/api/routers/users.py` (one route, one router-level gate).
**Second analog:** `src/nativespeaker/api/routers/auth.py:36` for the router construction comment.

**The router-level dependency is the partition** (`users.py:9-10`):

```python
# Router-level auth protects an endpoint added later whose own Depends is forgotten; the same callable runs once.
router = APIRouter(tags=["users"], dependencies=[Depends(get_linked_identity)])
```

`auth.py:36` is the same mechanism with its own reason line:

```python
# Auth is default-on, and deliberately unnarrowed: an already-linked caller is a 409 here, not a 401.
router = APIRouter(tags=["auth"], dependencies=[Depends(get_identity)])
```

**The handler re-declares the gate to receive its value** (`users.py:18-22`) — this is D-03's
"declared twice, resolved once"; `identity: Identity = Depends(get_linked_identity)` is exactly
`notification: VerifiedNotification = Depends(verify_app_store_notification)`:

```python
async def me(response: Response,
             identity: Identity = Depends(get_linked_identity),
             purchases: PurchasesDB = Depends(get_purchases_db)) -> MeResponse:
    """Report what the caller's own account holds at this request's instant."""
    purchase_tokens = await purchases.read_tokens(identity.user.id)
```

**The thin handler that only calls the service** (`auth.py:89-95`) — D-12's shape:

```python
async def upgrade_anonymous(body: CompletionRequest,
                            identity: Identity = Depends(get_linked_identity),
                            service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete_upgrade(identity=identity, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)
```

**Route decorator keywords** (`auth.py:83-88`) — `summary=` and `description=` are always present:

```python
@router.post("/auth/upgrade-anonymous",
             response_model=CompletionResponse,
             summary="Record the caller's identity row as registered with its real provider",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, ...")
```

**Router-level logger** (`auth.py:33`) — `logger = structlog.get_logger()`, used only for a bounded
label (`auth.py:51`). D-22's INFO line and D-21's ERROR lines belong here or in the service, never
in `auth/app_store.py`:

```python
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
```

**Barrel export** — `routers/__init__.py:1-9`: add `"webhooks_router"` to `__all__` (alphabetical)
and `from nativespeaker.api.routers.webhooks import router as webhooks_router`.

**Registration** — `app/main.py:43-49`, one line in the existing block whose comment already states
the rule:

```python
# Each router declares its own auth dependency; health declares none, being the whole public allowlist.
app.include_router(root_router)
app.include_router(auth_router)
```

---

### `src/nativespeaker/api/services/subscriptions.py` (service, one transaction + commit)

**Analog:** `src/nativespeaker/api/services/auth.py` (constructor, ordering, outcome handling) and
`src/nativespeaker/api/services/sync.py` (the small-service shape).

**Constructor: session, its crud classes, the one instant** (`sync.py:16-22`) — the minimal shape;
`services/auth.py:59-73` is the same with more collaborators:

```python
class SyncService:

    def __init__(self, db: AsyncSession, evaluated_at: datetime) -> None:
        self.session = db
        self.grants_db = GrantsDB(db)
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
```

**The refusal-order preamble comment** (`services/auth.py:118-119`) — D-13's status precedence and
D-20's replay read deserve the same one-line statement that the order *is* the rule:

```python
        """The one completion sequence every route runs: locate, claim, commit, post-claim work, spend.
        The order of the rejections below is the precedence, and none of them carries a field."""
```

**Read-then-decide, with the repeat as a silent return** (`services/auth.py:209-216`) — D-20's
"event row found → write nothing, 200" copies this arm exactly:

```python
        held = await self.grants_db.read_effective_grants(identity.user.id, self.evaluated_at)
        ...
        if AccessGrantSource.registered_account_grant in sources:
            # The repeat: nothing is written, Apple is never reached, and the entitlement is read after commit.
            return
```

**Answering for what the writer did** (`services/auth.py:248-258`) — D-20's lost-race arm is this
method with a 5xx instead of a re-read:

```python
    async def _settle(self, identity: Identity, outcome: ActivationOutcome) -> None:
        """Answer for what the writer did: a race re-reads the winner's row, and a refusal raises."""
        if outcome is ActivationOutcome.activated:
            return
        # The writer's transaction is unusable either way, and the read below needs a fresh one.
        await self.session.rollback()
        if outcome is ActivationOutcome.lost_race and await self.grants_db.read_effective_grants(
                identity.user.id, self.evaluated_at):
            # The loser answers exactly as the repeat does, because the winner's row is there to read.
            return
        raise ClaimRefusedUnderLock
```

**`commit()` and `rollback()` live here, never in crud** (`services/auth.py:141-142`, `:356`;
`services/quota.py:79-81`):

```python
        # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
        await self.session.commit()
```

**Monthly period derivation, for D-15's fresh usage row** (`sync.py:26-27`, `quota.py:54-60`) — one
spelling, always off the captured instant:

```python
        # The only place the period is derived, and always from the request's captured instant.
        period = self.evaluated_at.strftime("%Y-%m")
```

**Import boundary:** this module must import nothing from `appstoreserverlibrary`
(RESEARCH § Anti-Patterns). `services/auth.py:11-13` imports the seam's *value* and *helpers*, never
a vendor SDK — the same line to hold here.

**Barrel export** — `services/__init__.py:1-7`.

---

### `src/nativespeaker/api/crud/subscriptions.py` (crud, CRUD under locks)

**Analog:** `src/nativespeaker/api/crud/grants.py` (locks, SQLSTATE, flush boundary);
`src/nativespeaker/api/crud/purchases.py` (the minimal DB class).

**Module docstring naming the lock order** (`grants.py:1-2`):

```python
"""Entitlement reads over `core.access_grants`, and the one writer of each of the two free grants.
Global lock order: grant rows ascending by id, then usage rows, and never a third tier."""
```

**Statement builders as module functions, class methods stay thin** (`grants.py:24-42`, `:85-96`):

```python
def _effective_grants_statement(user_id: UUID, evaluated_at: datetime):
    """Every grant of `user_id` effective at `evaluated_at`, ascending by id."""
    return (
        select(AccessGrant)
        .where(col(AccessGrant.user_id) == user_id,
               # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
               col(AccessGrant.status) == AccessGrantStatus.active,
               ...)
        .order_by(col(AccessGrant.id).asc())
    )


class GrantsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."""
        # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
        statement = _effective_grants_statement(user_id, evaluated_at).with_for_update()
        return list((await self.session.exec(statement)).all())
```

**The two lock tiers, in order** (`grants.py:136-138`) — D-16's first two steps, verbatim shape:

```python
        grants = await self.lock_effective_grants(user_id, evaluated_at)
        for grant in grants:
            await self.lock_usage(grant.id)
```

**The expire-then-insert flush boundary** (`grants.py:226-239`) — D-15's renewal copies this whole
block, including the reason comment. This is the shape `ix_access_grants_one_per_subscription` forces:

```python
        if superseded is not None:
            superseded.status = AccessGrantStatus.expired
            superseded.ends_at = evaluated_at
            superseded.updated_at = evaluated_at
            # Flushed alone and first: the ORM emits inserts before updates, and the one-active index is per-statement.
            try:
                await self.session.flush()
            except IntegrityError as violation:
                # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
                if violation.orig.sqlstate != "23505":
                    # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                    raise
                return ActivationOutcome.lost_race
```

**The grant + usage insert pair** (`grants.py:157-168`) — D-15's new term row:

```python
        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.anonymous_device_grant,
                                starts_at=evaluated_at,
                                created_at=evaluated_at,
                                updated_at=evaluated_at)
        self.session.add(activated)
        self.session.add(UserMonthlyUsage(grant_id=activated.id,
                                          monthly_period=evaluated_at.strftime("%Y-%m"),
                                          monthly_used=0,
                                          created_at=evaluated_at,
                                          updated_at=evaluated_at))
```

**Fail-closed read raising from crud** (`purchases.py:22-26`) — the shape for `AttributionConflict`
and `UnmappedStoreProduct` if either is detected in crud rather than the service:

```python
        missing = set(PurchaseProvider) - set(tokens)
        if missing:
            # Completeness, never emptiness: one row present and one absent is the same broken invariant.
            raise MissingPurchaseTokenError(user_id, sorted(missing))
        return tokens
```

**Token resolution for D-16** (`purchases.py:16-20`) — the existing read is by `user_id`; the new
read is the inverse, `(provider, identity_value) → user_id`, in the same statement style.

**Barrel export** — `crud/__init__.py:1-7`.

---

### `src/nativespeaker/api/tables/purchases.py` (tables — four new names)

**Analog:** the same file's `StorePurchaseToken`, plus `tables/grants.py` for the enum + generated-column rules.

**Enum mirroring a PostgreSQL type, with the pinned `name=`** (`purchases.py:10-18`) —
`SubscriptionStatus` copies this exactly (RESEARCH P-15):

```python
class PurchaseProvider(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_provider` -- exactly two values."""
    apple = "apple"
    google_play = "google_play"


# `name=` pins the pre-existing type; without it SQLAlchemy derives a second, differently-named enum.
PurchaseProviderType = cast(Any, Enum(PurchaseProvider, name='subscription_provider', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))
```

**Table model** (`purchases.py:21-32`) — `__tablename__`, `__table_args__ = {"schema": ...}`, and a
comment on every column whose declaration is not obvious:

```python
class StorePurchaseToken(SQLModel, table=True):
    """One purchase-attribution token per user per store, for the account's life."""

    __tablename__ = "store_purchase_tokens"
    __table_args__ = {"schema": "core"}

    # The table has no crud primary key; these two markers are ORM-level, met by UNIQUE (user_id, provider).
    user_id: UUID = Field(foreign_key="core.users.id", primary_key=True)
    provider: PurchaseProvider = Field(sa_type=PurchaseProviderType, primary_key=True)
    # Deliberately not `unique=True`: the table's rule is the composite UNIQUE (provider, identity_value).
    identity_value: str = Field()
    created_at: datetime = Field(sa_type=DateTimeType)
```

**Generated columns are omitted, with the reason stated on the class** (`tables/grants.py:48-55`) —
`core.subscriptions.product_entitled_subscription_id` is exactly this case:

```python
# The table's two GENERATED ALWAYS AS STORED columns are deliberately unmapped: Postgres rejects an explicit value.
class AccessGrant(SQLModel, table=True):
    """One entitlement held by one user, resolved against a tier for its allowance."""

    __tablename__ = "access_grants"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
```

**Barrel export** — `tables/__init__.py:1-10` and `:43-46`: four names into `__all__` (alphabetical)
and into the `tables.purchases` import block.

---

### `src/nativespeaker/api/config.py` — `AppStoreConfig` (config)

**Analog:** `DeviceCheckConfig` (`config.py:58-62`) — every field optional, with the reason as a comment:

```python
class DeviceCheckConfig(BaseModel):
    # All three optional, unlike JWTConfig: an absent credential lets boot proceed and the route fail closed.
    key_id: str | None = Field(default=None, description="Apple DeviceCheck key ID")
    team_id: str | None = Field(default=None, description="Apple developer team ID")
    private_key_path: str | None = Field(default=None, description="Path to the ES256 private key PEM")
```

**Mounting on `AppConfig`** (`config.py:79`):

```python
    devicecheck: DeviceCheckConfig = Field(default_factory=DeviceCheckConfig)
```

**Typed-value precedent for `environment`** (`config.py:9`) — the file already builds a `StrEnum`
rather than accepting free text; RESEARCH § Security residual 1 makes this load-bearing:

```python
LogLevel = StrEnum("LogLevel", {k: k for k in logging.getLevelNamesMapping()})
```

**Nesting rule** (`config.py:12-16`) — `env_nested_delimiter="_"`, `env_nested_max_split=1`;
`APP_STORE_*` lands (RESEARCH P-14). No alias field named `appstore` may be added.

**`config/config.yaml`** — `app_store.products` is a partial block, exactly like `db:` (`config.yaml:18-19`):

```yaml
db:
  pool_size: 12
```

`bundle_id`, `app_apple_id`, `environment` and `root_certificate_path` stay out of the YAML, because
the file's own comment (`config.yaml:31-34`) says a declared key can never be set from the environment.

**`.env.example`** — the DeviceCheck block (`.env.example:67-81`) is the template: a `# --- <name>: <where it is used> ---`
header, where the values come from, why they are not in `config/config.yaml`, and what happens
without them:

```
# --- Apple DeviceCheck credentials: the device gate on POST /auth/claim-anonymous-grant ---
#
# ... These never go in config/config.yaml, which is tracked in git.
#
# Everything except the claim runs without them: the service boots, and a real claim fails
# closed as 503 verification_temporarily_unavailable. There is no bypass on any code path.
DEVICECHECK_KEY_ID=...
```

---

### `src/nativespeaker/api/app/dependencies.py` — the two new dependencies

**Analog for the admission gate:** `get_identity` (`:37-54`) — reads the collaborator off
`request.app.state` per request, converts a failure into an `AppError`:

```python
async def get_identity(request: Request,
                       credential: HTTPAuthorizationCredentials | None = Depends(_bearer),
                       ) -> Identity:
    """Accept the token and resolve the identity it names -- once per request."""
    if credential is None:
        raise InvalidExternalJwt(bounded_reason=None)

    # `verify` is synchronous and can block on a JWKS fetch, so it never runs on the event loop.
    claims, reason = await run_in_threadpool(request.app.state.jwt_verifier.verify,
                                             credential.credentials)
```

D-07 forbids `run_in_threadpool` here — with `enable_online_checks=False` there is no I/O. The rest
of the shape (take `Request`, one line, raise) is copied.

**Analog for the `app.state` accessor** (`:102-104`) — if the class is reached through its own accessor:

```python
def get_devicecheck_adapter(request: Request):
    """The device-gate seam the lifespan built, deliberately unannotated."""
    return request.app.state.devicecheck_adapter
```

**Analog for the service factory** (`:112-121`) — `get_subscriptions_service` copies this, including
`get_evaluated_at` for the one instant (`:107-109`):

```python
def get_auth_service(db: AsyncSession = Depends(get_db),
                     challenge_store: ChallengesDB = Depends(get_challenge_store),
                     adapter=Depends(get_firebase_adapter),
                     devicecheck=Depends(get_devicecheck_adapter),
                     evaluated_at: datetime = Depends(get_evaluated_at)) -> AuthService:
    return AuthService(db=db, ...)
```

```python
def get_evaluated_at() -> datetime:
    """One instant per request, shared by construction: FastAPI caches this dependency per request."""
    return datetime.now(UTC)
```

**Ordering rule** (`:75`) — the new dependencies go below what they declare:

```python
# Defined below the dependencies it declares, because its `Depends()` defaults are evaluated at definition time.
```

---

### `src/nativespeaker/api/app/lifespan.py` — building the verifier once

**Analog:** the devicecheck block (`:40-50`) — read the material, warn with a `consequence=` field
naming the client-visible failure, then construct and set on `app.state` unconditionally:

```python
    devicecheck_key = read_private_key(config.devicecheck.private_key_path)
    if not (config.devicecheck.key_id and config.devicecheck.team_id and devicecheck_key):
        logger.warning("devicecheck_credential_absent",
                       consequence="the anonymous grant claim fails closed as "
                                   "verification_temporarily_unavailable until the DeviceCheck key id, "
                                   "team id and private key are available in this environment")
    devicecheck_client = httpx.AsyncClient(timeout=DEVICECHECK_HTTP_TIMEOUT_SECONDS)
    app.state.devicecheck_adapter = AppleDeviceCheck(key_id=config.devicecheck.key_id,
                                                     team_id=config.devicecheck.team_id,
                                                     private_key=devicecheck_key,
                                                     client=devicecheck_client)
```

Two departures this phase must make, both from RESEARCH P-04: the completeness test is
"can the verifier be built" (Production without `app_apple_id` is *incomplete*), and the
`SignedDataVerifier` is constructed only when complete — `None` otherwise. RESEARCH § Code Example 1
is the measured form.

**Reading a file off a config path** (`devicecheck.py:54-59`) — the root certificate load copies this,
returning `None` for an unusable path rather than raising:

```python
def read_private_key(path: str | None) -> str | None:
    """Read the ES256 private key at `path`, or return `None` when there is no usable file."""
    if path is None:
        return None
    pem = Path(path)
    return pem.read_text() if pem.is_file() else None
```

---

### `src/nativespeaker/api/errors.py` — three new leaves

**Analog for `NotificationRejected`:** `ProofRejected` (`:421-425`) — a `ProviderLookupError` leaf
declaring only status and code, whose `stage` field is already carried by the base:

```python
class ProofRejected(ProviderLookupError):
    """Apple refused the device token, or accepted it and refused the bit write."""
    status = 403
    code = "proof_rejected"
```

The base it inherits (`:348-361`) is what gives D-04 its `stage=<VerificationStatus name>` log field
for free, and its comment already states the rule that makes `VerificationStatus.name` admissible:

```python
class ProviderLookupError(AppError):
    """The provider lookup's rejections share this shape; only its leaves are raised."""

    def __init__(self, *, stage: str, cause: str | None = None) -> None:
        # Plain strings, both of them ours: no provider text is ever admissible in either field.
        self.stage = stage
        self.cause = cause
        super().__init__(f"{type(self).__name__.lower()} at {stage}")

    def log_fields(self) -> dict[str, str | None]:
        fields: dict[str, str | None] = {"stage": self.stage}
```

**`Unavailable` is reused, not subclassed** (`:374-377`) — D-04:

```python
class Unavailable(ProviderLookupError):
    """The read could not be completed: an exhausted retry budget, or no app configured."""
    status = 503
    code = "verification_temporarily_unavailable"
```

**Analog for `AttributionConflict` and `UnmappedStoreProduct`:** `MissingUsageRowError` (`:218-225`)
— an `InternalError` leaf at ERROR with its own `__init__` and message:

```python
class MissingUsageRowError(InternalError):
    """An effective grant with no `core.user_monthly_usage` row."""
    # Never minted here: that would turn a detectable broken invariant into a silent free allowance.
    log_level = logging.ERROR

    def __init__(self, grant_id: UUID):
        self.grant_id = grant_id
        super().__init__(f"Grant {grant_id} has no core.user_monthly_usage row")
```

D-21's two leaves log `provider` and `external_id`, so they also need a `log_fields()` override —
`UpgradeRefused` (`:403-407`) is the shape, with its comment stating what is *not* admissible:

```python
    def log_fields(self) -> dict[str, str | None]:
        # Enough to find the row and name the disagreement; the provider account uid is not admissible.
        return {"identity_row_id": str(self.identity_row_id),
                "stored_provider": str(self.stored_provider),
                "live_provider": str(self.live_provider)}
```

**No new `ErrorCode` member** (D-04) — `auth_required`, `verification_temporarily_unavailable` and
`internal_error` are all already in the Literal at `:14-31`.

---

### `src/nativespeaker/api/schemas/auth.py` — the request body

**Analog:** `CompletionRequest` (`:24-28`) — one field, required and non-empty, with the reason the
422 is preferred over a business rejection:

```python
class CompletionRequest(BaseModel):
    """The completion body: the handle obtained from `/auth/challenge`, and nothing else."""
    # Required and non-empty, so an unusable handle is the framework's 422 rather than a not-found 409.
    # The length counts characters, so a padded handle stays a distinct value and reaches the store untrimmed.
    challenge_id: str = Field(..., min_length=1)
```

The one field is `signedPayload` — Apple's spelling, so it is a camelCase field name in an otherwise
snake_case schema module. State that in the docstring.

---

### `tests/unit/test_app_store_notifications.py` (new, unit seam)

**Analog:** `tests/unit/test_devicecheck_adapter.py`

**Module docstring recording what is and is not exercised for real** (`:1-3`) — RESEARCH
§ Environment Availability recommends the same note, with the opposite content (this phase's chain
check *does* run for real):

```python
"""The Apple wire contract: the signing, both request bodies, the bit1 carry-forward and every parse arm.
The shapes are [ASSUMED] from secondary sources -- see 41-RESEARCH.md § Assumptions Log, so a real 400
from Apple is evidence about these literals rather than a regression."""
```

**Module-scoped ephemeral EC key fixture** (`:36-42`) — the throwaway chain fixture (D-24, RESEARCH
§ Code Example 6) extends this to three keys and three certificates:

```python
@pytest.fixture(scope="module")
def private_key() -> str:
    """An ephemeral EC P-256 key generated here: never a fixture file and never a real Apple key."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(encoding=serialization.Encoding.PEM,
                             format=serialization.PrivateFormat.PKCS8,
                             encryption_algorithm=serialization.NoEncryption()).decode()
```

**The recorder/builder helper pair** (`:45-70`) — a scripted collaborator plus a `_adapter(...)`
factory with keyword overrides, so a case that removes one config field is one argument:

```python
def _adapter(recorder: Recorder, private_key: str, *, key_id: str | None = KEY_ID,
             team_id: str | None = TEAM_ID, key: str | None = "") -> AppleDeviceCheck:
    """The real adapter over a mock transport; certificate verification is never touched."""
```

The `AppStoreNotifications` equivalent takes `root_certificates=`, `environment=`, `bundle_id=` and
`app_apple_id=` overrides, so the vendored-root control (RESEARCH P-10) is one argument.

**Imports come from the seam module, not from a copy** (`:12-22`) — constants included.

---

### `tests/e2e/test_app_store_webhook.py` (new, e2e route) and `tests/e2e/conftest.py` (edit)

**Analog:** `tests/e2e/test_claim_registered_grant.py` + `tests/e2e/conftest.py:224-263`.

**The scripted fake behind the Protocol** (`conftest.py:224-251`) — `FakeAppStoreNotifications`
copies the raise-or-return contract and the call recording:

```python
class FakeDeviceCheckAdapter:
    """A scriptable stand-in for the device-gate seam, recording each method's calls separately."""

    def __init__(self) -> None:
        # A never-set device: the eligible first-ever claim, and what most cases want.
        self.answer: BaseException | BitState = BitState(bit0=False, bit1=False)
        ...

    def script(self, answer: BaseException | BitState) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted state is returned."""
        self.answer = answer

    async def read_bits(self, device_token: str) -> BitState:
        self.read_calls.append(device_token)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer
```

**The swap fixture with a `finally` restore** (`conftest.py:254-263`) — copy verbatim with the new
`app.state` attribute:

```python
@pytest.fixture
def scripted_devicecheck_adapter(_app_lifespan):
    """Swap app.state.devicecheck_adapter for a scripted fake, defaulting to a never-set device."""
    original = _app_lifespan.state.devicecheck_adapter
    adapter = FakeDeviceCheckAdapter()
    _app_lifespan.state.devicecheck_adapter = adapter
    try:
        yield adapter
    finally:
        _app_lifespan.state.devicecheck_adapter = original
```

**Test-module preamble: marker, module constants, the shared body compared by equality**
(`test_claim_registered_grant.py:29-47`):

```python
pytestmark = pytest.mark.e2e

SUBJECT = "tracer-claim-registered-subject"

# The one body every refusal answers with, compared by equality so a more helpful field fails here.
REFUSED = {"code": "operation_not_allowed"}

# The same body as bytes, so the four refusals are compared on the wire and not after parsing.
REFUSED_BODY = '{"code":"operation_not_allowed"}'
```

D-04's single 401 body is exactly this pattern: one `REJECTED = {"code": "auth_required"}` constant
compared with `==` across every verification-failure case, which is what makes "no oracle" testable.

**The client fixture over the started app** (`test_claim_registered_grant.py:49-54`) — D-05's case
(a valid Firebase token with a bad payload) needs the authenticated client; the no-header case uses
`unauthenticated_client` from `tests/e2e/test_unauthenticated_access.py:11-15`:

```python
@pytest_asyncio.fixture(loop_scope="module")
async def claim_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

**Row-count helpers that prove "nothing was written"** (`test_claim_registered_grant.py:83-95`) —
D-21 and D-22 both assert this:

```python
async def _grants_of(factory, user_id) -> list[AccessGrant]:
    """Every grant row of `user_id`, in the same ascending order the writer locks them."""
    async with factory() as session:
        return list((await session.exec(
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id)
            .order_by(col(AccessGrant.id).asc()))).all())
```

---

### `tests/schema/test_subscription_ingestion.py` and `test_subscription_race.py` (new)

**Analog:** `tests/schema/test_claim_race.py` and `tests/schema/helpers.py`.

**Seed helper shape** (`helpers.py:39-60`) — `insert_subscription` and `insert_store_purchase` copy
this: `asyncpg` `$N` parameters, keyword-only, returns the id, no commit:

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
    """Insert one core.access_grants row; source and status bind as text against the enum columns."""
    grant_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO core.access_grants (id, user_id, tier_id, source, status, subscription_id) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        grant_id, user_id, tier_id, source, status, subscription_id,
    )
    return grant_id
```

The file header states the contract to keep (`helpers.py:1-6`):

```python
"""Typed seed helpers for the schema-conformance suite -- each returns the id of the row it inserted."""
# Every row value binds through an asyncpg $N parameter, and no helper commits or owns a transaction.
```

**The race harness** (`test_claim_race.py:22-55`) — copy the dataclass, the fixture, the bounded
barrier and the FK-ordered cleanup; only the private key changes (an issuer there, a
`(provider, external_id)` or a `notification_uuid` prefix here):

```python
pytestmark = pytest.mark.schema

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# Bounded so a partner that fails before its flush shows up as a failure rather than as a hung suite.
BARRIER_TIMEOUT_SECONDS = 20


@dataclass
class _Harness:
    engine: object
    factory: async_sessionmaker
    issuer: str


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """A committing session factory plus this test's private issuer, cleaned up in FK order."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    ...
    try:
        yield subject
    finally:
        try:
            await clean_up(subject)
        finally:
            await engine.dispose()
```

**Child-first cleanup** (`test_claim_race.py:57-78`) — the new suite adds `audit.subscription_events`,
`core.store_purchases`, then `core.subscriptions` ahead of the users delete:

```python
async def clean_up(harness: _Harness) -> None:
    """Child-first: usage, grants, then the identity rows, then the users they pointed at."""
    ...
        # Last: core.external_identities references core.users ON DELETE RESTRICT.
```

**Reads on a separate connection** (`test_claim_race.py:81-89`) — the loser/winner assertions use this:

```python
async def read(harness: _Harness, sql: str, params: dict | None = None):
    """One read on a connection of its own -- never the one an attempt under test used."""
```

---

### `tests/unit/test_app_wiring.py` (edit — the third literal)

**Analog:** the file's own two literals and two helpers (`:11-22`):

```python
# Literals rather than derived from anything, so widening the exemption is a visible edit here.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}


def _api_routes() -> list[APIRoute]:
    return [route for route in real_app.routes if isinstance(route, APIRoute)]


def _declared(route: APIRoute) -> list:
    """The callables FastAPI resolved for this route, router-level declarations included."""
    return [dependency.call for dependency in route.dependant.dependencies]
```

`PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}` joins them with the same comment force.

**The two cases that break** (`:28-32` and `:57-62`), quoted so the edit is unambiguous — both need
`PROVIDER_CALLBACK_PATHS` in the union (RESEARCH P-05, measured):

```python
    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   and get_linked_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"
```

```python
    def test_the_public_allowlist_is_exactly_the_readiness_probe(self):
        """A second public route would have to be added to `PUBLIC_PATHS` above to pass."""
        unauthenticated = {route.path for route in _api_routes()
                           if get_linked_identity not in _declared(route)
                           and get_identity not in _declared(route)}
        assert unauthenticated == PUBLIC_PATHS
```

**The named-path parametrize pattern** (`:40-47`) — D-01's "each callback route declares the
verifier" case copies it, so the generic case cannot be the only cover:

```python
    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous", ...))
    def test_a_narrowed_route_declares_the_linked_identity_narrowing(self, path):
        """Named rather than left to the generic case, which would also pass if the route were exempted."""
        declared = [_declared(route) for route in _api_routes() if route.path == path]
        assert declared, f"{path} is not a registered route"
        assert all(get_linked_identity in calls for calls in declared)
```

---

## Shared Patterns

### The SQLSTATE 23505 idiom (one spelling, three shipped sites)

**Source:** `src/nativespeaker/api/crud/grants.py:174-182` (also `:232-239`, `:261-269`)
**Apply to:** every flush in `crud/subscriptions.py` (D-20)

```python
        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return ActivationOutcome.lost_race
```

`violation.orig.sqlstate`, not `violation.orig.__cause__.sqlstate` — 43-CONTEXT.md's "Carried
forward" entry is stale; `6b14231` replaced it (RESEARCH P-02).

### The lock order

**Source:** `src/nativespeaker/api/crud/grants.py:1-2` (the docstring) and `:136-138` (the code)
**Apply to:** `crud/subscriptions.py`, `services/subscriptions.py` (D-16)

Grant rows ascending by id, then their usage rows, and never a third tier ahead of them. The
re-read of a collaborating row is a plain read, never a lock (`grants.py:140-142`):

```python
        # A plain re-read, never `lock_identity_and_user`: a user-row lock ahead of the grant locks is forbidden.
```

### The one captured instant

**Source:** `src/nativespeaker/api/app/dependencies.py:107-109`, `services/sync.py:21-22`
**Apply to:** the handler, the service, every crud write (D-13, D-15)

`get_evaluated_at` is a dependency so FastAPI caches it per request; the service stores it as
`self.evaluated_at` with the comment "One instant for this request; nothing below it reads the clock
again." `created_at`, `updated_at`, `starts_at`, `ends_at` and `monthly_period` all derive from it.

### Structured-log labels from a closed set

**Source:** `src/nativespeaker/api/services/quota.py:36-37`, `routers/auth.py:50-51`,
`errors.py:352`
**Apply to:** D-21's two ERROR lines, D-22's INFO line, D-04's `stage` field

```python
                    # Labels come from a closed set only: a fixed branch name, never an id or a raw path.
                    logger.warning("quota_rejected", branch="no_effective_grant")
```

`VerificationStatus.name` is a closed set of eight strings, so it is admissible as `stage`
(RESEARCH § Code Example 2). `signedPayload`, `appAccountToken` and `identity_value` never are.

### The event name is the exception class name

**Source:** `src/nativespeaker/api/app/error_handlers.py:26-44`
**Apply to:** all three new error leaves — no `audit.auth_events` row and no event enum exists

```python
def camel_to_snake(name: str) -> str:
    ...

async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Record the failure once, then answer with the status and code its class declared."""
    assert isinstance(exc, AppError)
    if exc.log_level is not None:
        ...
        record(camel_to_snake(type(exc).__name__),
               exc_info=(exc.log_level >= logging.ERROR), **exc.log_fields())
    return JSONResponse(status_code=exc.status,
                        content=ErrorResponse(code=exc.code).model_dump(),
                        headers=exc.extra_headers())
```

This is why `NotificationRejected` reaching the handler produces exactly one WARNING and the one-field
body, with no line written by the router.

### The barrel export

**Source:** `crud/__init__.py:1-7`, `services/__init__.py:1-7`, `routers/__init__.py:1-9`,
`tables/__init__.py:1-10`
**Apply to:** every new class and router

`__all__` first as a sorted literal, then the imports in the same order. Four barrels are edited
this phase.

### Comment shape

**Source:** every file read above
**Apply to:** all new code (D-25 + `AGENTS.md` § Comments and docstrings)

One line, placed above the line it explains, stating *why* rather than *what*, and naming the
alternative it rejects. Docstrings are one to three lines — `tests/unit/test_docstring_bar.py`
holds a `BASELINE` of zero over-long docstrings for all five roots and fails on the fourth line.

### Ratchet literals are extended in the commit that trips them

**Source:** `tests/unit/test_auth_package_shape.py:13`, `tests/unit/test_rejection_vocabulary.py:60`
and `:146`, `tests/unit/test_app_wiring.py:12-13`
**Apply to:** four files (RESEARCH § Test Ratchets)

| Literal | Tripped by | Same commit as |
|---|---|---|
| `CURRENT = (5, 12, 35)` | `auth/app_store.py` | the module |
| `EVENT_NAMES` (+3), `CONSTRUCTOR_ARGUMENTS` (+3, all three take kwargs) | the three error leaves | `errors.py` |
| `PUBLIC_PATHS` unions ×2, `PROVIDER_CALLBACK_PATHS` | `include_router(webhooks_router)` | `app/main.py` |
| `BASELINE` in `test_docstring_bar.py` | any docstring over three lines | never — keep docstrings short |

---

## No Analog Found

| File | Role | Data flow | Reason |
|---|---|---|---|
| the throwaway root/intermediate/leaf chain fixture in `tests/unit/test_app_store_notifications.py` | test fixture | crypto | Nothing in the repository builds an X.509 chain. `tests/unit/test_devicecheck_adapter.py:36-42` is the closest — it generates one EC key and never a certificate. Use RESEARCH § Code Example 6, which was measured working, for the two Apple OIDs, the three-certificate order and the `x5c` header. |

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/` (all 34 modules), `tests/unit/`, `tests/e2e/`,
`tests/schema/`, `config/`, `k8s/templates/`, `.env.example`
**Files read this session:** 31
**Tracked-source check:** `git ls-files` run over every analog path named above; all tracked
**Pattern extraction date:** 2026-09-04
