# Phase 41: POST /auth/claim-anonymous-grant - Pattern Map

**Mapped:** 2026-09-02
**Files analyzed:** 27 (7 new source/test modules, 20 modified)
**Analogs found:** 25 / 27

All analog paths below were checked with `git ls-files` this session and are tracked source in
`ns-api-gateway` (a submodule of `native-speaker`). No path here is a gitignored mirror.

## File Classification

### New files

| New file | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/auth/devicecheck.py` | external-SDK seam (adapter + Protocol + retry) | request-response (outbound HTTPS) | `src/nativespeaker/api/auth/firebase.py` + `src/nativespeaker/api/auth/adapters.py` | exact (role) / partial (transport: `httpx` vs `firebase-admin`+threadpool) |
| `tests/unit/test_devicecheck_adapter.py` | test (unit, adapter) | request-response | `tests/unit/test_firebase_retry.py` (+ `tests/unit/test_adapter_interfaces.py`) | role-match |
| `tests/unit/test_claim_precedence.py` | test (unit, route precedence) | request-response | `tests/unit/test_upgrade_precedence.py` | exact |
| `tests/unit/test_grant_sources.py` | test (unit, AST/structural) | batch/transform | `tests/unit/test_adapter_interfaces.py::TestNoProviderDependency` | role-match |
| `tests/unit/test_claim_ordering.py` | test (unit, AST/structural) | batch/transform | `tests/unit/test_adapter_interfaces.py::TestNoProviderDependency` + `tests/unit/test_auth_package_shape.py::_measure` | role-match |
| `tests/e2e/test_claim_anonymous_grant.py` | test (e2e, endpoint) | request-response | `tests/e2e/test_upgrade_anonymous.py` | exact |
| `tests/schema/test_claim_race.py` | test (schema, two-connection race) | event-driven (concurrency) | `tests/schema/test_create_race.py` | exact |

### Modified files

| Modified file | Role | Data Flow | Closest Analog (in-file precedent) | Match Quality |
|---------------|------|-----------|-------------------------------------|---------------|
| `src/nativespeaker/api/crud/grants.py` (+ activation writer) | crud | CRUD (multi-row insert) | `src/nativespeaker/api/crud/identities.py::insert_account` (:80-115) | exact |
| `src/nativespeaker/api/tables/grants.py` (+ `AccessGrantAntiAbuse`) | table model | CRUD | `src/nativespeaker/api/tables/grants.py::AccessGrant` (:44-61) + `UserMonthlyUsage` (:64-76) | exact |
| `src/nativespeaker/api/schemas/auth.py` (+ claim request model) | schema | request-response | `schemas/auth.py::CompletionRequest` (:24-28) | exact |
| `src/nativespeaker/api/errors.py` (+2 classes, `ErrorCode` 16→18) | error registry | request-response | `errors.py::ProviderLookupError` family (:346-381) | exact |
| `src/nativespeaker/api/services/auth.py` (`_complete` generalised + new completion) | service | request-response + transaction boundary | `services/auth.py::_complete` (:64-111) and `_apply_upgrade` (:123-155) | exact |
| `src/nativespeaker/api/routers/auth.py` (+ route, docstring 4→5) | router | request-response | `routers/auth.py::upgrade_anonymous` (:80-93) + `issue_challenge`'s `no-store` response (:60-63) | exact |
| `src/nativespeaker/api/app/dependencies.py` (+ adapter accessor, wire into `get_auth_service`) | config/wiring | request-response | `app/dependencies.py::get_firebase_adapter` + `get_auth_service` (:96-109) | exact |
| `src/nativespeaker/api/app/lifespan.py` (+ build the adapter) | config/wiring | batch (boot) | `app/lifespan.py` :30-34 | exact |
| `src/nativespeaker/api/config.py` (+ `DeviceCheckConfig`) | config | batch (boot) | `config.py::JWTConfig` (:45-55) + `AppConfig` field list (:64-76) | exact |
| `config/config.yaml` (+ `db: pool_size: 12`) | config | batch (boot) | `config/config.yaml` `jwt:` block (:15-16) | exact |
| `.env.example` (+ DeviceCheck credentials block) | config | batch (boot) | `.env.example` Firebase Admin ADC block | exact |
| `pyproject.toml` (`httpx` → `[project].dependencies`) | config | batch | existing `[project].dependencies` list | exact |
| `src/nativespeaker/api/resilience.py` (D-14/D-15) | utility (in-process gate) | event-driven | `resilience.py::LLMExecutionGate.hold` (:97-102), `admission` (:133-138), `ainvoke` (:140-169) | exact (edit in place) |
| `tests/unit/test_quota_seam.py` (reword + extend) | test (unit) | event-driven | itself (:200-448, six classes / twenty cases) | exact |
| `tests/unit/test_resilience_retry.py` (extend) | test (unit) | event-driven | `test_resilience_retry.py::TestGateAndBreakerErrorsAreNeverWrapped` (:157-196) | exact |
| `tests/unit/test_config.py` (extend) | test (unit) | batch | `test_config.py::test_resilence_config_defaults` (:38) and `TestSubscriptionConfigSurfaceIsGone` (:100-134) | exact |
| `tests/unit/test_app_wiring.py` (add path to two parametrize lists) | test (unit) | request-response | `test_app_wiring.py` :40, :47 | exact |
| `tests/unit/test_auth_package_shape.py` (`CURRENT` literal) | test (unit) | batch | `test_auth_package_shape.py:13` | exact |
| `tests/e2e/conftest.py` (+ `scripted_devicecheck_adapter`) | test fixture | request-response | `tests/e2e/conftest.py::scripted_firebase_adapter` (:211-220) + `tests/unit/conftest.py::FakeFirebaseAdapter` (:192-216) | exact |
| `tests/schema/test_grant_locks.py` (extend) | test (schema) | event-driven | itself (:16-31) | exact |
| `.planning/REQUIREMENTS.md` / `ROADMAP.md` / `STATE.md` / `AGENTS.md` / two todo files | docs | — | prior-phase amendment convention | n/a (see § No Analog Found) |

---

## Pattern Assignments

### `src/nativespeaker/api/auth/devicecheck.py` (external-SDK seam, request-response)

**Analog:** `src/nativespeaker/api/auth/firebase.py` (whole module, 147 lines — read in one pass)
**Secondary analog:** `src/nativespeaker/api/auth/adapters.py` (Protocol + frozen value type)

Do **not** put the Protocol in `auth/adapters.py`: that module is fenced by an import allowlist
(`tests/unit/test_adapter_interfaces.py:23`) that excludes `httpx`. Declare the Protocol beside the
implementation in `auth/devicecheck.py`.

**Module docstring + imports pattern** (`auth/firebase.py:1-24`):

```python
"""The Firebase Admin integration: one named app per issuer, one adapter method, never a [DEFAULT] app.
Never take the first recognized entry, and never classify non-empty providerData as anonymous.
Never read `firebase.sign_in_provider`: no declaration match here, and no `required_flow` anywhere."""
from typing import NoReturn

import firebase_admin
import structlog
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.errors import NotLinked, Unavailable, UserNotFound
from nativespeaker.api.tables.identities import IdentityProvider

logger = structlog.get_logger()

# An app-level option because the SDK exposes no per-call timeout: every call through the app inherits it.
FIREBASE_HTTP_TIMEOUT_SECONDS = 8

# The whole budget for one lookup: the initial call plus up to two more, spent on retryable outcomes only.
FIREBASE_LOOKUP_ATTEMPTS = 3
```

**Deviate on one point:** `logger = structlog.get_logger()` must **not** be copied into
`devicecheck.py`. The module handles raw device tokens, so it follows `crud/challenges.py:1`
instead — *"A handle is a secret capability: this module holds no logger, so none is logged."*
(CONTEXT.md D-06, RESEARCH Pitfall 15.)

**Internal retry marker** (`auth/firebase.py:27-28`):

```python
class RetryableLookupError(Exception):
    """The retry predicate's only target, always converted before it can escape."""
```

**Retry wrapper — copy verbatim in shape** (`auth/firebase.py:134-147`):

```python
def _exhausted(retry_state) -> NoReturn:
    """Convert an exhausted retry budget into the `Unavailable` rejection the client is owed."""
    raise Unavailable(stage="provider_lookup") from retry_state.outcome.exception()


async def lookup_with_retry(adapter, issuer: str, subject: str) -> VerifiedProviderIdentity:
    """Call the adapter up to `FIREBASE_LOOKUP_ATTEMPTS` times; return the identity or raise."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        # Only the internal marker retries, so `UserNotFound` and `NotLinked` propagate after one attempt.
        retry=retry_if_exception_type(RetryableLookupError),
        retry_error_callback=_exhausted,
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
```

`retry_error_callback=_exhausted`, **not** `reraise=True`: the exhausted budget becomes the client's
owed 503 and the internal marker never escapes. `resilience.py:167` uses `reraise=True` — that is the
LLM path's contract, not this one. Do not copy it here.

**Error-classification pattern (per-exception arm, provider text to the log only)**
(`auth/firebase.py:82-96`):

```python
        except auth.UserNotFoundError:
            # Definitive, spends no retry budget, and listed before the FirebaseError it subclasses.
            logger.info("firebase_get_user_not_found")
            raise UserNotFound(stage="provider_lookup") from None
        except ValueError as error:
            logger.warning("firebase_provider_data_malformed", detail=str(error))
            raise RetryableLookupError(str(error)) from error
```

Copy the arm shape (one `except` per definitive/retryable class, `from error`, no nested `try`), but
drop the `logger` calls per the no-logger rule above; the branch name travels in `stage`/`cause`.

**Protocol + frozen value type** (`auth/adapters.py:9-26`) — the shape for `BitState` and the
DeviceCheck Protocol:

```python
@dataclass(frozen=True, slots=True)
class VerifiedProviderIdentity:
    """What one completed providerData read established: which provider owns the caller, and its uid.
    Every field here has already passed its rule -- the shape classified, the address verified."""

    provider: IdentityProvider
    # `None` exactly for the anonymous arm: `core.external_identities`' CHECK requires NULL there.
    provider_uid: str | None
    email: str | None = None


class FirebaseAdminAdapter(Protocol):
    """One configured integration, one client selected by issuer match, and no ambient fallback."""

    def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """The providerData read: the verified identity, or a raise."""
        ...
```

`BitState` must be `frozen=True, slots=True` for the same reason (`test_adapter_interfaces.py:78-95`
asserts immutability and no `__dict__` on the seam's value type; write the sibling assertions in
`tests/unit/test_devicecheck_adapter.py`).

---

### `src/nativespeaker/api/crud/grants.py` — the activation writer (crud, CRUD)

**Analog:** `src/nativespeaker/api/crud/identities.py::insert_account` (:80-115)

**Multi-row insert, one flush, `IntegrityError` caught at the flush, constraint never named**
(`crud/identities.py:86-115`):

```python
        """Insert the user, its identity row and its purchase tokens, and return the new user's id."""
        try:
            user = User(email=email, ..., created_at=evaluated_at, updated_at=evaluated_at)
            self.session.add(user)
            await self.session.flush()

            self.session.add(ExternalIdentity(user_id=user.id, ...))

            await self.session.flush()
            return user.id
        except IntegrityError as conflict:
            raise IdentityAlreadyLinked() from conflict
```

Apply with two adjustments the research pins:
- The grant row and its `AccessGrantAntiAbuse` row go in the **same flush** — their two FKs are
  `DEFERRABLE INITIALLY DEFERRED` (migration :304-307, :316-322), so splitting the flush moves a
  violation out to `session.commit()` where no handler sits (Pitfall 6).
- D-13's race loser is not an error: either raise a private sentinel the service converts, or return
  a `bool` the service branches on. `IntegrityError` is still caught without naming a constraint or
  parsing a message (Phase 40 D-08).

**Narrow-`try` counter-pattern for the ORM-assignment case** (`crud/identities.py:126-143`) — copy
this when only a flush can raise:

```python
        # Read before the flush too: a failed flush expires the row, and reading it after re-queries a dead transaction.
        identity_row_id = identity_row.id
        identity_row.provider = provider
        ...
        # Only the flush is inside: an ORM assignment sends nothing to the database.
        try:
            await self.session.flush()
        except IntegrityError as conflict:
            raise ProviderAccountAlreadyLinked(...) from conflict
```

**Lock-order helpers to call, never to reimplement** (`crud/grants.py:37-53`):

```python
    async def lock_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."""
        # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
        statement = _effective_grants_statement(user_id, evaluated_at).with_for_update()
        return list((await self.session.exec(statement)).all())

    async def lock_usage(self, grant_id: UUID) -> UserMonthlyUsage | None:
        """Lock and return `grant_id`'s usage row, or `None`. Second in the lock order and never first."""
        statement = _usage_statement(grant_id).with_for_update()
        return (await self.session.exec(statement)).first()
```

**Module-level statement builder pattern** (`crud/grants.py:11-29`) — a new preflight query for the
prior-free-grant read (any status, both free sources) belongs here as a private `_..._statement`
free function beside `_effective_grants_statement` / `_usage_statement`, not inside the class:

```python
def _effective_grants_statement(user_id: UUID, evaluated_at: datetime):
    """Every grant of `user_id` effective at `evaluated_at`, ascending by id."""
    return (
        select(AccessGrant)
        .where(col(AccessGrant.user_id) == user_id,
               # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
               col(AccessGrant.status) == AccessGrantStatus.active,
               ...)
        # No `.limit(...)`: the caller must see a second effective grant and fail closed on it.
        .order_by(col(AccessGrant.id).asc())
    )
```

**Do NOT reuse** `crud/identities.py::lock_identity_and_user` (:61-74) — it ends `.with_for_update()`
on identity and user, which `SHARED-INVARIANTS.md:34` forbids ahead of the grant locks (D-13). Use
`crud/identities.py::resolve_existing` (:55-59), the non-locking re-resolution:

```python
    async def resolve_existing(self, *, issuer: str, subject: str) -> ExternalIdentity | None:
        """The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."""
```

---

### `src/nativespeaker/api/tables/grants.py` — `AccessGrantAntiAbuse` (table model, CRUD)

**Analog:** `tables/grants.py::AccessGrant` (:44-61) and `UserMonthlyUsage` (:64-76), same file.

```python
AccessGrantSourceType = cast(Any, Enum(AccessGrantSource, name='access_grant_source', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


# The table's four GENERATED ALWAYS AS STORED columns are deliberately unmapped: Postgres rejects an explicit value.
class AccessGrant(SQLModel, table=True):
    """One entitlement held by one user, resolved against a tier for its allowance."""

    __tablename__ = "access_grants"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id")
    source: AccessGrantSource = Field(sa_type=AccessGrantSourceType)
    status: AccessGrantStatus = Field(sa_type=AccessGrantStatusType, default=AccessGrantStatus.active)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```

Carry over exactly: the `cast(Any, Enum(..., schema='core'))` alias style, `__tablename__` +
`__table_args__ = {"schema": "core"}`, `sa_type=DateTimeType` on every timestamp, and the
unmapped-GENERATED-column comment (here for `registered_account_grant_id`, Pitfall 9).

`NativeClaimProviderType` already exists and is the enum type to bind
(`tables/identities.py:24-32`):

```python
class NativeClaimProvider(StrEnum):
    """Mirrors `core.native_claim_provider` -- the platform a native claim is pinned to, immutably."""
    ios_devicecheck = "ios_devicecheck"
    android_play_integrity = "android_play_integrity"

NativeClaimProviderType = cast(Any, Enum(NativeClaimProvider, name='native_claim_provider', schema='core'))
```

`created_at` on the anti-abuse table is `NOT NULL` with no database default — the same asymmetry
`UserMonthlyUsage` already documents (`tables/grants.py:74`):

```python
    # NOT NULL with no crud DEFAULT, unlike every other table: these factories are the only source of a value.
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```

---

### `src/nativespeaker/api/schemas/auth.py` — the claim request model (schema, request-response)

**Analog:** `schemas/auth.py::CompletionRequest` (:24-28)

```python
class CompletionRequest(BaseModel):
    """The completion body: the handle obtained from `/auth/challenge`, and nothing else."""
    # Required and non-empty, so an unusable handle is the framework's 422 rather than a not-found 409.
    # The length counts characters, so a padded handle stays a distinct value and reaches the store untrimmed.
    challenge_id: str = Field(..., min_length=1)
```

The three fields (handle, query token, update token) all take `Field(..., min_length=1)`, so an
absent or empty token is the framework's 422 (Claude's Discretion; record the divergence from the
brief's `proof_malformed` under D-17).

**Response model — reuse, do not mint a twin** (`schemas/auth.py:51-64`):

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

---

### `src/nativespeaker/api/errors.py` — `ProofRejected` / `DeviceGrantExhausted` (error registry)

**Analog:** `errors.py::ProviderLookupError` and its three leaves (:346-381)

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
        if self.cause is not None:
            fields["cause"] = self.cause
        return fields


class Unavailable(ProviderLookupError):
    """The read could not be completed: an exhausted retry budget, or no app configured."""
    status = 503
    code = "verification_temporarily_unavailable"


class NotLinked(ProviderLookupError):
    """A providerData shape outside the accept set, so no provider account may be claimed for it."""
    status = 403
    code = "operation_not_allowed"
```

The two new classes subclass `ProviderLookupError` and declare `status = 403` plus their own `code`,
one docstring line each. `Unavailable` is reused unchanged for every ambiguity/exhaustion arm — no
third class.

**Shared-base anti-oracle pattern for the three D-09 refusals** (`errors.py:387-413`) — one 403
declared on the base, leaves declaring nothing:

```python
class UpgradeRefused(AppError):
    """The upgrade's two drift rejections share this shape; only its leaves are raised."""

    # The 403 is declared here and nowhere below, so the refusal cannot become an enumeration oracle.
    status = 403
    code = "operation_not_allowed"
    ...

class ProviderTransitionNotAllowed(UpgradeRefused):
    """The stored row is registered and the live read disagrees: the two have drifted apart."""
```

**`ErrorCode` literal — append two members in the same edit** (`errors.py:13-29`):

```python
# The codes the body may carry. A typo is a ValidationError at construction, not a runtime 500.
ErrorCode = Literal["auth_required",
                    ...
                    "identity_already_linked",
                    "operation_not_allowed"]
```

`tests/unit/test_error_registry.py` needs **no** edit: its assertion is symmetric
(`set(get_args(ErrorCode)) == {cls.code for cls in _family(AppError)}`), Pitfall 11.

---

### `src/nativespeaker/api/services/auth.py` — the new completion (service, request-response)

**Analog:** `services/auth.py::_complete` (:64-111), same file — generalise, do not fork
(Phase 40 D-16).

**The sequence and its rejection precedence, unchanged** (:69-97):

```python
        """The one completion sequence both routes run: locate, claim, read, write, spend.
        The order of the rejections below is the precedence, and none of them carries a field."""
        # No rejection before the claim consumes anything, so a wrong presenter cannot burn a live challenge.
        located = await self.challenge_store.locate(self.session, challenge_id)
        if located is None:
            raise ChallengeNotFound()

        challenge = self.challenge_store.verify_binding(located, identity)
        if challenge.operation is not operation:
            raise ChallengeOperationMismatch()

        if not await self.challenge_store.claim(self.session, challenge_id=challenge_id,
                                                now=self.evaluated_at):
            await self.session.refresh(challenge)
            if challenge.claimed_at is None:
                raise ChallengeExpired()
            else:
                raise ChallengeConsumed()

        # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
        await self.session.commit()
```

**The seam to generalise — the two hardwired statements become one injected `post_claim`
callable** (:98-111):

```python
        try:
            facts = await lookup_with_retry(self.adapter, identity.issuer, identity.subject)
            # The provider the transaction settled on, which a divergence makes different from the read's.
            settled = await write(identity, facts)
        except AppError:
            # A conflicting write leaves the transaction unusable, and the spend below needs it back.
            await self.session.rollback()
            await self._consume_quietly(challenge_id=challenge_id,
                                        challenge_row_id=challenge_row_id)
            raise

        await self._consume_and_commit(challenge_id=challenge_id,
                                       challenge_row_id=challenge_row_id)
        return settled
```

The `except AppError` rollback-then-consume arm, `_consume_quietly` and `_consume_and_commit` are
untouched. The `Write` type alias at :32-33 generalises rather than gaining a sibling:

```python
# The write seam of the shared sequence: it returns the provider the transaction settled on.
Write = Callable[[Identity, VerifiedProviderIdentity], Awaitable[IdentityProvider]]
```

**The thin public entry point** (:57-62) — the new `complete_claim_anonymous_grant` copies this:

```python
    async def complete_upgrade(self, *, identity: Identity, challenge_id: str) -> IdentityProvider:
        """Record the caller's identity row as registered, and return the provider it now carries."""
        return await self._complete(identity=identity,
                                    challenge_id=challenge_id,
                                    operation=AuthOperation.upgrade_anonymous_to_registered,
                                    write=self._apply_upgrade)
```

**The in-transaction revalidation body** — `_apply_upgrade` (:123-155) is the shape for the claim's
post-claim closure (re-read, branch on the stored column, return-without-writing for the repeat):

```python
    async def _apply_upgrade(self, identity: Identity,
                             facts: VerifiedProviderIdentity) -> IdentityProvider:
        """Re-check the locked rows' provider, and return the provider the flip settled on."""
        located = await self.identities_db.lock_identity_and_user(...)
        if located is None:
            # The barrier resolved both rows and neither is ever deleted, so no row is broken state.
            raise IdentityUnresolvable
        identity_row, user = located
        stored = identity_row.provider
        ...
        if stored is facts.provider and identity_row.provider_uid == facts.provider_uid:
            # D-04: the repeat that changed nothing answers as the flip did, and writes nothing at all.
            return stored
```

Substitute `resolve_existing` for `lock_identity_and_user` (lock-order rule above) and
`identity.identity.provider is IdentityProvider.anonymous` as the D-08 classifier.

**Post-commit response read — reuse verbatim** (`services/sync.py:24-63`):

```python
    async def read_entitlement(self, user_id: UUID) -> Entitlement:
        """Report the entitlement `user_id` holds at the captured instant, taking no lock and writing nothing."""
        # The only place the period is derived, and always from the request's captured instant.
        period = self.evaluated_at.strftime("%Y-%m")

        grants = await self.grants_db.read_effective_grants(user_id, self.evaluated_at)
        ...
        usage = await self.grants_db.read_usage(grant.id)
        if usage is None:
            # Fail closed: reporting zero used would promise an allowance the charge refuses at this same instant.
            raise MissingUsageRowError(grant.id)
```

The `%Y-%m` derivation from the captured instant is also the usage row's `monthly_period` value.

---

### `src/nativespeaker/api/routers/auth.py` — the route (router, request-response)

**Analog:** `routers/auth.py::upgrade_anonymous` (:80-93) for the route-level barrier and body
forwarding; `issue_challenge` (:60-63) for `Cache-Control: no-store`.

```python
# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/upgrade-anonymous",
             response_model=CompletionResponse,
             summary="Record the caller's identity row as registered with its real provider",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and records the provider the "
                         "Firebase read reports onto the caller's existing identity row.")
async def upgrade_anonymous(body: CompletionRequest,
                            identity: Identity = Depends(get_linked_identity),
                            service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete_upgrade(identity=identity, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)
```

**`no-store` on a secret-bearing response** (`routers/auth.py:60-63`):

```python
    # `no-store` rather than `no-cache`: the handle is a secret, and a revalidatable copy is a copy.
    return JSONResponse(content=PrepareResponse(...).model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})
```

Phase 39 D-09 uses an injected `Response` for the same header on `/users/me`; either is precedented —
the `JSONResponse` form above loses `response_model` validation, so prefer the injected `Response`
when returning `SyncResponse` typed.

The module docstring at :1-2 counts the routes and must grow from four to five:

```python
"""The four auth routes: `/auth/challenge` issues a challenge, `/auth/create-user` and
`/auth/upgrade-anonymous` spend one, and `/auth/sync` reports what the caller's account entitles it to."""
```

---

### `src/nativespeaker/api/app/dependencies.py` + `app/lifespan.py` (config/wiring, boot)

**Analog:** `app/dependencies.py:96-109`

```python
def get_firebase_adapter(request: Request):
    """The provider seam the lifespan built, deliberately unannotated."""
    # The concrete class implements the Protocol's one reachable method asynchronously, not synchronously.
    return request.app.state.firebase_adapter


def get_auth_service(db: AsyncSession = Depends(get_db),
                     challenge_store: ChallengesDB = Depends(get_challenge_store),
                     adapter=Depends(get_firebase_adapter)) -> AuthService:
    return AuthService(db=db,
                       challenge_store=challenge_store,
                       adapter=adapter,
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC))
```

The DeviceCheck accessor copies `get_firebase_adapter` verbatim in shape (unannotated return,
`request.app.state.<name>`), and `get_auth_service` gains a second `Depends()` parameter.

**Boot-time construction** (`app/lifespan.py:30-34`):

```python
    # One named Firebase app per configured issuer; an absent credential returns {} and boot proceeds.
    firebase_apps = build_admin_apps(config)
    app.state.firebase_adapter = FirebaseAdminLookup(firebase_apps)

    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
```

`pool_size` already flows from config, so D-16 needs no `lifespan.py` edit — only the config value.
The absent-credential path is the precedent for DeviceCheck's missing key: warn and let boot proceed,
so the route fails closed at call time as `Unavailable`, mirroring `build_admin_apps`
(`auth/firebase.py:31-45`).

---

### `src/nativespeaker/api/config.py` + `config/config.yaml` + `.env.example` (config, boot)

**Analog:** `config.py::JWTConfig` (:45-55) and the `AppConfig` field list (:64-76)

```python
class JWTConfig(BaseModel):
    project_id: str = Field(description="GCP project ID")
    api_key: str = Field(description="GCP API key")
    jwks_url: str = Field(default="https://www.googleapis.com/service_accounts/v1/jwk/"
                                  "securetoken@system.gserviceaccount.com")
    leeway_seconds: int = Field(default=30, ge=0, description="Expiration timeout")


class AppConfig(BaseConfig):
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
```

`DeviceCheckConfig` is a plain `BaseModel` with no defaults for the secret fields (exactly as
`JWTConfig.project_id` / `api_key`) and is added to `AppConfig` as
`devicecheck: DeviceCheckConfig = Field(default_factory=DeviceCheckConfig)`. The nested env
delimiter is set once on `BaseConfig` (`config.py:12-16`), so `DEVICECHECK_KEY_ID` etc. land
automatically:

```python
class BaseConfig(BaseSettings):
    # `hide_input_in_errors` belongs here, not on the nested tables: a nested error renders under the outer config.
    model_config = SettingsConfigDict(env_nested_delimiter="_",
                                      env_nested_max_split=1,
                                      hide_input_in_errors=True)
```

**The YAML partial-block precedent D-16 follows** (`config/config.yaml:15-16`):

```yaml
resilience:
  pool_size: 5
  ...
jwt:
  jwks_cache_ttl_seconds: 3600
```

`jwt:` declares one key while `JWT_PROJECT_ID` and `JWT_API_KEY` still arrive from `.env`, proving a
partial block deep-merges. Adding `db:` / `pool_size: 12` puts the number one screen from
`resilience.pool_size: 5`, where D-16's "×2+2" comment reads. **Note the file's own warning** (in the
header comment block): YAML is authoritative for anything it declares, so a `db:` block forecloses
`DB_POOL_SIZE` from `.env` — that is the trade-off, and `config.py:25` is the alternative site.

**Secret-in-`.env` precedent** — the Firebase Admin ADC block in `.env.example` documents a **path
to a file outside the repo, mode 600**, plus the boot behaviour when it is absent. The DeviceCheck
PEM block copies that structure (Open Question 2 recommends `DEVICECHECK_PRIVATE_KEY_PATH`).

---

### `src/nativespeaker/api/resilience.py` (utility, event-driven) — D-14 / D-15

**Analog:** the file itself; both edits are in place (`AGENTS.md` § Resilience: *"They are not
awaiting replacement."*)

**What splits** (`resilience.py:97-102`, :133-138):

```python
    @asynccontextmanager
    async def hold(self):
        """Hold an in-flight slot and the concurrency semaphore, or raise `QueueFullError`."""
        async with self._inflight_slot():
            async with self._semaphore:
                yield

    @asynccontextmanager
    async def admission(self):
        """Admit one request: the breaker is consulted and a slot is held for the caller's whole body."""
        await self._circuit_breaker.before_call()
        async with self._gate.hold():
            yield Admitted()
```

`_inflight_slot` (:83-95) is already a standalone context manager — the second public one D-15 needs
is a rename/exposure of it, not new machinery. Both docstrings change.

**Where D-14's `before_call()` goes** (`resilience.py:143-156`) — above the `try`, or inside it above
`asyncio.wait_for` with the existing pass-through arm ordered first:

```python
        async def attempt() -> Any:
            """One attempt, already triaged: everything `_should_retry` reads is decided here."""
            try:
                result = await asyncio.wait_for(operation(), timeout=self._timeout_seconds)
            except (QueueFullError, CircuitOpenError):
                raise
            except Exception as e:
                # Everything reaching here came out of `operation` itself, so every classification is the provider's.
                await self._circuit_breaker.record_failure()
                if _is_transient_error(e):
                    raise TransientLLMError(str(e)) from e
                raise PermanentLLMError(str(e)) from e
            await self._circuit_breaker.record_success()
            return result
```

The `except (QueueFullError, CircuitOpenError): raise` arm at :147 must stay **first** or the
`CircuitOpenError` is recorded as a breaker failure and rewrapped, losing its `Retry-After`
(Pitfall 13). D-15 wraps the `AsyncRetrying` at :158-169 in the semaphore.

**Test analog for the new D-14 case** (`tests/unit/test_resilience_retry.py:157-196`,
`TestGateAndBreakerErrorsAreNeverWrapped`) — `test_circuit_open_propagates_unwrapped_and_is_not_retried`
is the existing case; the new one opens the breaker mid-flight and asserts 503 + `Retry-After`
instead of the remaining attempts being spent.

---

### `tests/e2e/conftest.py` — the scripted DeviceCheck fake (test fixture)

**Analog:** `tests/e2e/conftest.py::scripted_firebase_adapter` (:211-220)

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

**The fake itself** (`tests/unit/conftest.py:192-216`) — script-or-raise, records every call:

```python
class FakeFirebaseAdapter:
    """A scriptable stand-in for the provider seam; async because a synchronous fake would fail against real wiring.

    It scripts the seam's answer and nothing behind it: no classification and no email rule.
    """

    def __init__(self) -> None:
        self.answer: BaseException | VerifiedProviderIdentity = ANONYMOUS_IDENTITY
        self.calls: list[tuple[str, str]] = []

    def script(self, answer: BaseException | VerifiedProviderIdentity) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted identity is returned."""
        self.answer = answer

    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        self.calls.append((issuer, subject))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer
```

The DeviceCheck fake needs **two** recorded call lists (read and write) so a case can assert the
update carried the query's `bit1` forward and that no Apple call happened on the D-09 repeat.

**Grant seeding** (`tests/e2e/conftest.py:279-309`) — note the comment that explains why this phase's
writer is the only producer of a free grant:

```python
        # source defaults to manual: the free sources need an anti-abuse row nothing here can seed.
        grant = AccessGrant(user_id=user_id, tier_id=tier_id, source=source, status=status, ...)
```

Once `AccessGrantAntiAbuse` exists, `seed_grant` can gain an opt-in anti-abuse row for the
"consumed but inactive free grant" and "active grant of another source" refusal cases.

---

### `tests/e2e/test_claim_anonymous_grant.py` (test, e2e)

**Analog:** `tests/e2e/test_upgrade_anonymous.py` (308 lines)

**Header, markers, shared refusal body** (:1-27):

```python
pytestmark = pytest.mark.e2e

SUBJECT = "tracer-anonymous-subject"

# The one body all three refusals answer with, compared by equality so a more helpful field fails.
REFUSED = {"code": "operation_not_allowed"}
```

**Client fixture over the real started app** (:30-35):

```python
@pytest_asyncio.fixture(loop_scope="module")
async def upgrade_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

**Prepare-then-complete, with the "prepare touched no provider" assertion** (:100-118):

```python
        issued = await upgrade_client.post("/auth/challenge",
                                           json={"operation": "upgrade_anonymous_to_registered"},
                                           headers=_auth())
        assert issued.status_code == 200
        handle = issued.json()["challenge_id"]
        # Issuance reads no provider, so a call here would mean the handler did more than issue.
        assert scripted_firebase_adapter.calls == []

        completion = await upgrade_client.post("/auth/upgrade-anonymous",
                                               json={"challenge_id": handle},
                                               headers=_auth())

        assert completion.status_code == 200
        assert completion.json() == {"identity_provider": "google"}
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)]
```

**Per-case helpers and the refusal-case shape** (:136-190):

```python
async def _issue(client, subject: str) -> str:
    """Obtain an upgrade handle for `subject`, which every case below spends exactly once."""
    ...

async def _challenge_for(factory, handle: str) -> AuthChallenge:
    async with factory() as session:
        return (await session.exec(
            select(AuthChallenge).where(col(AuthChallenge.challenge_id) == handle))).one()


@pytest.mark.asyncio(loop_scope="module")
class TestTheRefusalsAndTheRepeat:
    """The four cases the real Google account cannot produce on demand, each through the real router."""

    async def test_a_live_anonymous_read_refuses_and_leaves_the_row_untouched(...):
        """The client called before its own linking finished: refused, and nothing is recorded."""
        ...
        assert completion.status_code == 403, completion.text
        assert completion.json() == REFUSED
        assert await _binding(_db_transaction, subject) == before
```

`_challenge_for` is the read that proves "every post-claim outcome consumed the challenge" (D-06).

---

### `tests/schema/test_claim_race.py` (test, schema, two-connection race)

**Analog:** `tests/schema/test_create_race.py` (344 lines) — extend `_Harness`, `_Attempt`,
`barrier_for` and the FK-ordered cleanup.

**Harness with a private issuer and FK-ordered teardown** (:30-62):

```python
@dataclass
class _Harness:
    engine: object
    factory: async_sessionmaker
    issuer: str
    owned_user_ids: list[uuid.UUID] = field(default_factory=list)


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """A committing session factory plus this test's private issuer, cleaned up in FK order."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    subject = _Harness(engine=engine,
                       factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                  expire_on_commit=False),
                       issuer=f"ns-race-{uuid.uuid4().hex[:12]}")
```

Cleanup for this phase adds `core.access_grants_anti_abuse`, `core.user_monthly_usage` and
`core.access_grants` ahead of `core.external_identities` and `core.users`.

**Two prepared challenges, driven through the production service on independent
sessions** (:77-92, :144-162):

```python
async def commit_claimed_challenge(harness: _Harness, *, subject: str) -> tuple[uuid.UUID, str]:
    """One already-claimed challenge; each attempt gets its own and must consume it."""
    ...
        await conn.execute(
            text("INSERT INTO core.auth_challenges "
                 "(id, challenge_id, operation, preauth_issuer, preauth_subject, "
                 " expires_at, claimed_at, created_at) "
                 "VALUES (:id, :challenge_id, 'create_user', :issuer, :subject, "
                 "        :expires_at, :now, :now)"), {...})


async def run_attempt(harness: _Harness, attempt: _Attempt, after_first_read=None) -> _Attempt:
    """Drive the production consuming transaction once, on its own session and connection."""
    store = ChallengesDB()
    async with harness.factory() as real_session:
        session = _HookedSession(real_session, after_first_read)
        try:
            service = AuthService(db=session, challenge_store=store, adapter=None, evaluated_at=NOW)
            attempt.result = await service.create_user(...)
        except AppError as rejection:
            # The route's own except arm: roll the conflicting inserts back, then spend the handle.
            await session.rollback()
            attempt.result = rejection
        await store.consume(session, challenge_id=attempt.challenge_id, now=NOW)
        await session.commit()
    return attempt
```

The challenge row's `operation` becomes `'claim_anonymous_grant'` and `adapter=None` becomes the
scripted DeviceCheck fake.

**The barrier that proves both attempts saw the pre-state** (:165-176):

```python
def barrier_for(harness: _Harness, attempt: _Attempt, mine: asyncio.Event, theirs: asyncio.Event):
    """Announce that this attempt has re-resolved, then wait for its partner; the row count records the premise."""

    async def hold() -> None:
        attempt.identities_seen_at_barrier = await scalar(harness, "SELECT count(*) ...", {...})
        mine.set()
        await asyncio.wait_for(theirs.wait(), timeout=BARRIER_TIMEOUT_SECONDS)

    return hold
```

**Assertion vocabulary** (:196, :199-269) — the `by_result` bucketing and one case per invariant:

```python
        by_result = {outcome_name(attempt): attempt for attempt in (first, second)}

    async def test_both_attempts_observed_an_unlinked_subject(self, raced):
        """The premise: without this the case could be two sequential creations."""
        assert [attempt.identities_seen_at_barrier for attempt in raced["attempts"]] == [0, 0]

    async def test_both_challenges_were_consumed_and_their_verifiers_cleared(self, harness, raced):
        """The loser consumes too, so a retry needs a fresh prepare rather than a replay of this one."""
```

D-13 inverts one assertion: `test_the_second_run_rejects_rather_than_returning_idempotent_success`
(:321) becomes "the loser answers 200 with the winner's grant" here.

**The lock-order proof to extend** (`tests/schema/test_grant_locks.py:16-31`) — the SQL literals
mirror `GrantsDB`, so the new writer must not introduce a third lock tier:

```python
# Mirrors GrantsDB.lock_effective_grants; the ORDER BY is the lock order itself, not presentation.
_LOCK_GRANTS = ("SELECT id FROM core.access_grants WHERE user_id = $1 AND status = 'active' ... "
                "ORDER BY id ASC FOR UPDATE")

# Mirrors GrantsDB.lock_usage: second in the order, keyed on the whole primary key, and never an INSERT.
_LOCK_USAGE = "SELECT grant_id FROM core.user_monthly_usage WHERE grant_id = $1 FOR UPDATE"
```

---

### `tests/unit/test_claim_precedence.py` (test, unit)

**Analog:** `tests/unit/test_upgrade_precedence.py` (:1-100+) — the in-memory challenge store, the
rejection log and the boundary-recording stub session.

```python
class _FakeChallengeStore:
    """One in-memory row whose `claim` and `consume` mirror the real conditional updates clause for clause."""

    async def claim(self, session, *, challenge_id, now) -> bool:
        row = self.row
        if row is None or row.challenge_id != challenge_id:
            return False
        if row.claimed_at is not None or row.expires_at <= now:
            return False
        row.claimed_at = now
        return True


class _RejectionLog:
    @property
    def results(self) -> list[str]:
        """One string per rejection. The class name, snake_cased, is the outcome vocabulary (D-05)."""
        return [event for event, _ in self.entries]


class _StubSession:
    """Records transaction boundaries and refuses queries: a statement here would mean the write ran unstubbed."""
```

`consume_calls` is the counter that proves D-06's "every post-claim outcome consumes, no pre-claim
rejection does". The app is assembled from the real router with `Depends` overrides
(`test_upgrade_precedence.py:9-24` imports `auth_router`, `register_exception_handlers`,
`get_challenge_store`, `get_db`, `get_firebase_adapter`, `get_identity`).

---

### `tests/unit/test_devicecheck_adapter.py` (test, unit)

**Analog:** `tests/unit/test_firebase_retry.py` for the attempt-budget cases:

```python
class CountingAdapter:
    """Raises or returns a scripted sequence and records every call; overrunning the script is an error."""

    def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        self.calls.append((issuer, subject))
        if len(self.calls) > len(self.scripted):
            # Overrunning the script is the failure this file exists to catch, so name it.
            raise AssertionError(f"attempt {len(self.calls)} exceeds the scripted {len(self.scripted)}")
        ...


class TestAttemptCountsPerOutcome:
    """Three attempts total for the retryable marker only; every other answer is definitive."""

    async def test_three_retryable_failures_cost_exactly_three_attempts(self):
        adapter = CountingAdapter(*[_retryable() for _ in range(3)])
        with pytest.raises(Unavailable):
            await lookup_with_retry(adapter, ISSUER, SUBJECT)
        assert len(adapter.calls) == 3
```

For the signing and the four parse arms, drive the real adapter through `httpx.MockTransport`
(installed with httpx 0.28.1; `respx` is not installed and must not be added). Assert:
JWT header `kid` / alg ES256 and claims; both body shapes; `bit1` carried forward from a scripted
`bit1=true` query; and all four parse arms including the plain-text never-set body and the
fail-closed fourth arm.

---

### `tests/unit/test_grant_sources.py` and `tests/unit/test_claim_ordering.py` (test, unit, structural)

**Analog:** `tests/unit/test_adapter_interfaces.py:26-72` — parse the module source with `ast` and
assert over the tree, plus a subprocess import check:

```python
SOURCE_PATH = Path(adapters_module.__file__)
SOURCE = SOURCE_PATH.read_text()
TREE = ast.parse(SOURCE)

# Only the standard library and this project; a provider SDK or credential source here is the drift.
ALLOWED_IMPORT_ROOTS = {"dataclasses", "datetime", "enum", "typing", "uuid", "nativespeaker"}


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)


    def test_the_source_imports_only_the_stdlib_and_this_project(self):
        roots = set()
        for node in ast.walk(TREE):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            ...
        assert roots <= ALLOWED_IMPORT_ROOTS, f"unexpected imports: {sorted(roots - ALLOWED_IMPORT_ROOTS)}"
```

`tests/unit/test_auth_package_shape.py:16-26` is the second half of the pattern — a `_measure`-style
walk over a directory plus a **control case** proving the measurement actually fires
(`test_a_method_and_a_nested_helper_both_count_control`, :40-47). Write the control; a structural
test that silently measures nothing passes for the wrong reason.

**The literal ratchet to update, not create** (`test_auth_package_shape.py:12-13`):

```python
# What it measures now: modules, classes, functions.
CURRENT = (4, 8, 18)
```

---

## Shared Patterns

### One captured instant per request
**Source:** `app/dependencies.py:102-109`, `services/auth.py:47-48`, `services/sync.py:21-27`
**Apply to:** the service, the crud writer, every timestamp the claim writes

```python
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC)
```
```python
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
```
```python
        # The only place the period is derived, and always from the request's captured instant.
        period = self.evaluated_at.strftime("%Y-%m")
```

### Fail-closed reads raise their own rejection in `crud/`
**Source:** `services/sync.py:45-53`, `crud/grants.py:16-17, 28`
**Apply to:** the eligibility preflight and every response read

```python
        usage = await self.grants_db.read_usage(grant.id)
        if usage is None:
            # Fail closed: reporting zero used would promise an allowance the charge refuses at this same instant.
            raise MissingUsageRowError(grant.id)
```
```python
               # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
```
```python
    # Never inserts: `None` is the fail-closed signal, not a cue to mint a row and hand out an allowance.
```

### Positive enum tests, never negative
**Source:** `crud/identities.py:48-52`
**Apply to:** the D-08 claimant check and every status/provider branch

```python
        # Positive tests, so a NULL or any future enum member fails closed on these same two branches.
        if identity.identity_state != IdentityState.active:
            raise HistoricalIdentity
        if user.active is not True:
            raise BlockedUser
```

D-08 therefore reads `identity.identity.provider is IdentityProvider.anonymous`, never
`is not IdentityProvider.google`.

### The barrier is the only place identity happens
**Source:** `app/dependencies.py:57-62`
**Apply to:** the new route (`Depends(get_linked_identity)`, no re-verification in the handler)

```python
# Declared, never called directly: FastAPI's cache only sees solver-resolved deps, so a direct call re-verifies.
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> Identity:
    """The resolved user and identity row; rejects an unlinked caller with 403."""
    if identity.user is None:
        raise PreAuthIdentityNotAllowed
    return identity
```

### `Depends()`-only handlers
**Source:** `AGENTS.md:34, 44-47`; every handler in `routers/auth.py`
**Apply to:** the new route — take the session, the barrier and the service from dependencies; never
construct a database class or read `Request` in the body.

### Comment and docstring bar
**Source:** `AGENTS.md:3-22`; gated by `tests/unit/test_docstring_bar.py` at baseline 0 on every root
**Apply to:** all new code

Docstrings: three lines maximum, stating what the entity does and nothing else. Comments: one line
each, only to resolve a genuine ambiguity, default to none. Every excerpt quoted in this document
obeys the bar — copy their register, not their volume.

### No nested `try`; a `try` holds only the statement that can raise
**Source:** `crud/identities.py:137-143` (quoted above), Phase 40 D-17
**Apply to:** the `IntegrityError` arm, both Apple calls, the parse arms

### Barrel exports
**Source:** `src/nativespeaker/api/crud/__init__.py`

```python
__all__ = ["ChallengesDB", "ChatsDB", "GrantsDB", "IdentitiesDB", "PurchasesDB"]

from nativespeaker.api.crud.challenges import ChallengesDB
```

`auth/__init__.py` is one line and exports nothing — `auth/devicecheck.py` is imported by full path,
as `auth/firebase.py` is in `app/lifespan.py:9`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| The Apple wire contract inside `auth/devicecheck.py` (JWT claim set, both request bodies, the four parse arms) | external-SDK seam | request-response | No `httpx`-based outbound seam exists anywhere in `src/`: `auth/firebase.py` goes through `firebase-admin` + `run_in_threadpool`, and `auth/jwt_verifier.py` fetches JWKS synchronously. The module *structure* copies `firebase.py` exactly (above); the request/response bodies have no in-repo precedent and come from RESEARCH.md § Code Examples 2-3, all tagged `[ASSUMED]`. |
| `.planning/REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `AGENTS.md`, the two todo files (D-17…D-21) | docs | — | Planning artifacts, not code. The convention is prior-phase amendment entries; the planner should read `.planning/REQUIREMENTS.md`'s own header for the amendment format and the current conflict counts rather than copy a source analog. |

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/**` (auth, services, crud, tables, schemas, routers,
app, config, resilience), `tests/unit/**`, `tests/e2e/**`, `tests/schema/**`, `config/`, `.env.example`
**Files scanned:** 30 tracked files, all confirmed with `git ls-files`
**Files read in full:** `auth/firebase.py`, `auth/adapters.py`, `services/auth.py`, `services/sync.py`,
`crud/grants.py`, `crud/identities.py`, `tables/grants.py`, `routers/auth.py`, `schemas/auth.py`,
`config.py`, `app/dependencies.py`, `app/lifespan.py`, `resilience.py`,
`tests/schema/test_create_race.py`, `tests/unit/test_adapter_interfaces.py`,
`tests/unit/test_auth_package_shape.py`, `AGENTS.md`
**Files read in targeted ranges:** `errors.py` (:13-32, :344-418 + structural outline),
`tables/identities.py` (:1-60), `tests/unit/conftest.py` (:180-217),
`tests/unit/test_firebase_retry.py` (:1-80), `tests/unit/test_upgrade_precedence.py` (:1-100),
`tests/e2e/conftest.py` (:200-320), `tests/e2e/test_upgrade_anonymous.py` (:1-70, :95-190),
`tests/schema/test_grant_locks.py` (:1-60)
**Pattern extraction date:** 2026-09-02
