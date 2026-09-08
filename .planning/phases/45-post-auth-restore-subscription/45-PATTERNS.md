# Phase 45: POST /auth/restore-subscription - Pattern Map

**Mapped:** 2026-09-07
**Files analyzed:** 21 (4 new source/test files, 12 modified source files, 5 ratchet/doc mirrors)
**Analogs found:** 20 / 21

Every analog path below is git-tracked source under `/home/init/native-speaker/ns-api-gateway`,
verified with `git ls-files`. No path is a gitignored install mirror.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/services/restore.py` (NEW) | service | request-response + CRUD in one transaction | `src/nativespeaker/api/services/subscriptions.py` | exact |
| `src/nativespeaker/api/routers/auth.py` (MOD) | router | request-response | `routers/auth.py::claim_registered_grant` (same file, lines 122-143) | exact |
| `src/nativespeaker/api/schemas/auth.py` (MOD) | schema | request body | `schemas/auth.py::GrantClaimRequest` (same file, lines 31-35) | exact |
| `src/nativespeaker/api/app/dependencies.py` (MOD) | config/wiring | request-response | `dependencies.py::get_subscriptions_service` (same file, 147-150) | exact |
| `src/nativespeaker/api/services/__init__.py` (MOD) | config | — | same file, lines 1-9 | exact |
| `src/nativespeaker/api/auth/app_store.py` (MOD) | adapter | request-response (local verify) | `auth/app_store.py::AppStoreNotifications.verify` (same file, 73-107) | exact |
| `src/nativespeaker/api/auth/google_play.py` (MOD) | adapter | request-response (network read) | `auth/google_play.py::PlayDeveloperSubscriptions.read` (same file, 196-248) | exact |
| `src/nativespeaker/api/auth/store_notifications.py` (MOD) | schema (value type) | transform | `auth/store_notifications.py::VerifiedNotification` (same file, 9-27) | exact |
| `src/nativespeaker/api/crud/subscriptions.py` (MOD: `claim_subscription_owner`) | crud | CRUD (conditional UPDATE) | `crud/subscriptions.py::upsert_subscription` (same file, 84-130) | role-match |
| `src/nativespeaker/api/crud/subscriptions.py` (MOD: D-09 owner rule) | crud | CRUD | same file, line 106-107 | exact |
| `src/nativespeaker/api/crud/grants.py` (MOD: two-user grant lock) | crud | CRUD (locking read) | `crud/grants.py::_active_grants_statement` + `lock_active_grants` (45-51, 98-102) | exact |
| `src/nativespeaker/api/errors.py` (MOD: +2 codes, +4 classes) | errors | — | `errors.py::ClaimRefused` block (same file, 475-505) | exact |
| `tests/unit/test_restore_proof.py` (NEW) | test (unit) | request-response | `tests/unit/test_app_store_notifications.py` + `tests/unit/test_google_play_notifications.py` | exact |
| `tests/e2e/test_restore_subscription.py` (NEW) | test (e2e) | request-response | `tests/e2e/test_claim_registered_grant.py` | exact |
| `tests/schema/test_restore_race.py` (NEW) | test (schema) | CRUD race | `tests/schema/test_subscription_race.py` | exact |
| `tests/e2e/conftest.py` (MOD: `seed_subscription`) | test fixture | CRUD seed | `tests/e2e/conftest.py::seed_grant` (536-565) + `tests/e2e/test_claim_registered_grant.py::_seed_subscription_grant` (117-139) | exact |
| `tests/unit/test_app_wiring.py` (MOD) | test (ratchet) | — | same file, lines 70-85 | exact |
| `tests/unit/test_error_contract.py` (MOD) | test (ratchet) | — | same file, lines 19-25 | exact |
| `tests/unit/test_rejection_vocabulary.py` (MOD) | test (ratchet) | — | same file, lines 41-60 | exact |
| `tests/unit/test_auth_package_shape.py` (MOD) | test (ratchet) | — | same file, line 13 | exact |
| `tests/unit/test_subscription_attribution.py` (MOD) | test (fake mirror) | — | same file, lines 113-114 | exact |
| `.planning/REQUIREMENTS.md`, `.planning/STATE.md` (MOD) | docs | — | prior phase amendment entries | no analog read this pass |

## Pattern Assignments

### `src/nativespeaker/api/services/restore.py` (NEW — service, request-response + CRUD)

**Analog:** `src/nativespeaker/api/services/subscriptions.py`

**Module docstring + imports pattern** (lines 1-14) — one line, then the crud and error imports,
then the module logger:
```python
"""Store-subscription ingestion: one verified notification, one transaction, one commit."""
from datetime import datetime
from uuid import uuid7

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.errors import AttributionConflict, InternalError
from nativespeaker.api.tables import SubscriptionStatus

logger = structlog.get_logger()
```

**Constructor pattern** (lines 17-24) — the session, the crud classes it owns, and the one instant:
```python
class SubscriptionsService:

    def __init__(self, db: AsyncSession, evaluated_at: datetime) -> None:
        self.session = db
        self.subscriptions_db = SubscriptionsDB(db)
        self.purchases_db = PurchasesDB(db)
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
```
`RestoreService` takes the same two arguments plus the two store classes off `app.state`
(see the dependency section below). Copy the `self.evaluated_at` comment verbatim — it is the
`get_evaluated_at` contract, and D-10's transfer month derives from it.

**Non-locking pre-transaction reads, then the locks** (lines 38-51) — this is the exact order
restore's service must repeat, with the store call moved ahead of every line of it (Pattern 1 of
RESEARCH):
```python
        token = notification.attribution_token
        # Read before the transaction writes, so no token read happens under a lock.
        user_id = (None if token is None
                   else await self.purchases_db.resolve_user(notification.provider, token))

        stored = await self.subscriptions_db.read_subscription(notification.provider,
                                                               notification.external_id)
        old_tier_id = None if stored is None else stored.tier_id
        # A plain read, never a lock: a subscription-row lock would sit ahead of the grant locks below.
        owner = user_id if user_id is not None else (None if stored is None else stored.user_id)

        # An unattributed purchase has no buyer, so there is no row to lock and no grant to hold.
        marked_active = ([] if owner is None
                         else await self.subscriptions_db.lock_grants(owner, self.evaluated_at))
```

**The purchase-row insert with a minted attribution value** (lines 96-108) — restore repeats this
for the missing-purchase case (CONTEXT carried-forward: "restore inserts it when missing, with a
`uuid7()` `identity_value` when the transaction carries no token"):
```python
        if recorded is None:
            # Inserted after the subscription flushed: `core.store_purchases` keys a foreign key on the pair.
            await self._settle(await self.subscriptions_db.insert_purchase(
                provider=notification.provider,
                # A generated value only when the store gave none: the column is NOT NULL.
                identity_value=str(uuid7()) if token is None else token,
                external_id=notification.external_id,
                store_transaction_id=notification.transaction_id,
                store_original_transaction_id=notification.external_id,
                purchase_user_id=user_id,
                # Set only when the token resolved: the second foreign key needs a binding to point at.
                resolved_token_value=None if user_id is None else token,
                evaluated_at=self.evaluated_at), notification)
```

**The `write_subscription_grant` call and its term expression** (lines 119-132) — **copy the
`starts_at`/`ends_at` expression exactly**, or `WriteOutcome.replayed` never matches and a repeat
restore mints a fresh usage row:
```python
        if subscription.user_id is not None:
            await self._settle(await self.subscriptions_db.write_subscription_grant(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                status=status,
                marked_active=marked_active,
                tier_id=tier_id,
                # The captured instant stands in where the store gave no purchase date for this term.
                starts_at=(self.evaluated_at if notification.purchased_at is None
                           else notification.purchased_at),
                # During grace the term is Apple's grace window, because the paid term has lapsed.
                ends_at=(notification.grace_period_expires_at
                         if status is SubscriptionStatus.grace_period else notification.expires_at),
                evaluated_at=self.evaluated_at), notification)

        # Deliberate commit: the store reads the status code, so 200 must mean the rows are durable.
        await self.session.commit()
```

**Rollback-and-answer pattern for a lost race** (lines 137-147) — restore's zero-rows path from
D-08 takes this shape, except that restore re-reads and answers instead of raising `InternalError`:
```python
    async def _settle(self, outcome: WriteOutcome,
                      notification: VerifiedNotification) -> None:
        """Answer for what the writer did: a lost race is a 5xx the store's resend then finds recorded."""
        if outcome is not WriteOutcome.lost_race:
            return
        # The writer's transaction is unusable, and the winner's rows are what the resend will read.
        await self.session.rollback()
        # Labels come from a closed set only: the store's own name, never a payload value.
        logger.warning("store_notification_race_lost", provider=str(notification.provider))
```

**Secondary analog for the pre-transaction refusal ladder:**
`src/nativespeaker/api/services/auth.py::_claim_registered_grant` (lines 203-226). Its shape is
"read, then a fixed order of raises, then the write" and each refusal is a bare `raise Leaf` with a
one-line comment. Restore's branch decision (same-account / adoption / move / not entitled / capped)
copies that ladder. Note its rollback contract at lines 149-151:
```python
        except AppError:
            # A conflicting write leaves the transaction unusable, and the spend below needs it back.
            await self.session.rollback()
```

---

### `src/nativespeaker/api/routers/auth.py` (MOD — router, request-response)

**Analog:** the same file. Two excerpts compose the new handler.

**The provider gate** — `issue_challenge` lines 49-52 (D-01 raises a 403 leaf here rather than
`InvalidRequest`):
```python
    if body.operation not in AuthOperation:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest
```

**The handler body, the sync read-back and the `no-store` header** — `claim_registered_grant`,
lines 122-143, copied whole:
```python
# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/claim-registered-grant",
             response_model=SyncResponse,
             summary="Claim the caller's one registered account grant",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, ...")
async def claim_registered_grant(body: GrantClaimRequest,
                                 response: Response,
                                 identity: Identity = Depends(get_linked_identity),
                                 service: AuthService = Depends(get_auth_service),
                                 sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Complete the operation the body's handle stands for, and report the entitlement it left."""
    # Forwarded untouched and never logged: the handle and the device token are secrets.
    await service.complete_claim_registered_grant(identity=identity,
                                                  challenge_id=body.challenge_id,
                                                  device_token=body.device_token)
    # Read after the completion committed, so the claim, the repeat and the race loser share one shape.
    entitlement = await sync_service.read_entitlement(identity.user.id)
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
```

**Also modified in this file:** the module docstring at lines 1-3 says "The six auth routes" and is
exactly three lines. It becomes seven routes and must stay at three lines
(`tests/unit/test_docstring_bar.py` baseline is 0).

---

### `src/nativespeaker/api/schemas/auth.py` (MOD — schema, request body)

**Analog:** `GrantClaimRequest`, same file lines 31-35, and `ChallengeRequest` lines 13-14 for the
plain-`str` field:
```python
class ChallengeRequest(BaseModel):
    """The issuance body. `operation` is a plain `str`, never a Literal: an unissuable value is the handler's 400."""
    operation: str


class GrantClaimRequest(BaseModel):
    """The body both grant claims share: the handle, and the DeviceCheck token naming the device."""
    challenge_id: str = Field(..., min_length=1)
    # One token for the read and the write: two would let the bit read name a different device.
    device_token: str = Field(..., min_length=1)
```
`RestoreRequest` is `GrantClaimRequest`'s `Field(..., min_length=1)` shape with `ChallengeRequest`'s
plain-`str` rationale in its docstring. Place it after `GrantClaimRequest` and before
`CompletionResponse`, keeping the request models grouped.

---

### `src/nativespeaker/api/app/dependencies.py` (MOD — config/wiring)

**Analog:** `get_subscriptions_service`, same file lines 147-150, and `get_sync_service` at 142-144:
```python
def get_sync_service(db: AsyncSession = Depends(get_db),
                     evaluated_at: datetime = Depends(get_evaluated_at)) -> SyncService:
    return SyncService(db=db, evaluated_at=evaluated_at)


def get_subscriptions_service(db: AsyncSession = Depends(get_db),
                              evaluated_at: datetime = Depends(get_evaluated_at),
                              ) -> SubscriptionsService:
    return SubscriptionsService(db=db, evaluated_at=evaluated_at)
```

**Reading the store classes off `app.state`** — the accessor pattern, lines 109-122:
```python
# These two accessors exist so a challenge-bearing route can stay Depends()-only and never take Request itself.
def get_challenge_store(request: Request) -> ChallengesDB:
    """The one `ChallengesDB` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.challenge_store


def get_firebase_adapter(request: Request):
    """The provider seam the lifespan built, deliberately unannotated."""
    # The concrete class implements the Protocol's one reachable method asynchronously, not synchronously.
    return request.app.state.firebase_adapter
```
`get_restore_service` takes `request: Request` for `app.state.app_store_notifications`,
`app.state.play_subscriptions` and `app.state.config.google_play.package_name`, plus
`Depends(get_db)` and `Depends(get_evaluated_at)` — the shape `get_chat_service` (lines 94-105)
already uses when it needs both `Request` and dependencies.

---

### `src/nativespeaker/api/auth/app_store.py` (MOD — adapter, local verification)

**Analog:** `AppStoreNotifications.verify`, same file lines 73-107, and `_tier_for` at 109-115.

**The unconfigured guard, the verify call and the rejection mapping** (lines 73-91):
```python
    def verify(self, signed_payload: str) -> VerifiedNotification:
        """Verify the envelope and both nested payloads, then return this project's value type."""
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")

        try:
            payload = self._verifier.verify_and_decode_notification(signed_payload)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure
```
`verify_transaction` copies this exactly with two substitutions:
`verify_and_decode_signed_transaction` for the decode call, and `ProofRejected` for
`NotificationRejected` (D-11: `NotificationRejected` answers 401 `auth_required`, which is wrong for
a caller whose Firebase token was valid).

**The product map refusal** (lines 109-115) — reuse `_tier_for` as-is, do not re-implement:
```python
    def _tier_for(self, product_id: str | None) -> str:
        """The tier this store product maps to, or a refusal that leaves nothing written."""
        tier_id = None if product_id is None else self._products.get(product_id)
        if tier_id is None:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.apple, str(product_id))
        return tier_id
```

**The millisecond converter** (lines 36-38) — the status derivation reuses it, never a new one:
```python
def _instant(milliseconds: int | None) -> datetime | None:
    """Convert one of Apple's UNIX-millisecond stamps, keeping an absent one absent."""
    return None if milliseconds is None else datetime.fromtimestamp(milliseconds / 1000, UTC)
```

**Not usable here:** `_APPLE_STATUSES` (lines 20-25) keys on the *notification's* `data.status`. A
bare transaction has none. The derived rule goes beside it as a module-level function, following the
`_status_for` precedent in `google_play.py` (lines 155-165).

---

### `src/nativespeaker/api/auth/google_play.py` (MOD — adapter, network read)

**Analog:** `PlayDeveloperSubscriptions.read`, same file lines 196-235.

**The entry point's guard, the answer classification and the product refusal** (lines 196-216):
```python
    async def read(self, *, package_name: str, purchase_token: str, event_type: str,
                   notification_uuid: str, signed_at: datetime | None) -> VerifiedNotification | None:
        """Read this subscription's live state from Play, or answer `None` for a gone token."""
        if self._credential is None:
            raise Unavailable(stage="play_subscriptions_read")

        response = await self._get(package_name, purchase_token)
        if not _play_answer_is_usable(response):
            return None
        subscription = PlaySubscription.model_validate(response.json())

        line_item = subscription.lineItems[0] if subscription.lineItems else None
        product_id = None if line_item is None else line_item.productId
        if product_id is None or product_id not in self._products:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.google_play, str(product_id))
```

**The grace-window field, which the term expression depends on** (lines 213-234):
```python
        expiry = None if line_item is None else line_item.expiryTime
        # Google carries no separate grace field, so in grace this expiry is the end of the window.
        # Left as None, every grace-period subscriber's grant would be written with no end date.
        in_grace = subscription.subscriptionState == GRACE_STATE
        ...
            grace_period_expires_at=expiry if in_grace else None,
```

**The two failure paths D-05 must re-map** — the gone-token classifier at 143-152 and the transport
raise at 237-248. Both raise or return through `InternalError`, and `UnmappedStoreProduct` is a
subclass of `InternalError` (`errors.py:262`), so a broad `except InternalError` swallows the
operator error:
```python
def _play_answer_is_usable(response: httpx.Response) -> bool:
    """Classify one Play answer in the one order that lets nothing fall through to a default."""
    if response.status_code // 100 == 2:
        return True
    if response.status_code in _GONE_STATUSES:
        # Definitive: a token Google says is gone can never resolve, so a retry loops until retention.
        logger.error("google_play_purchase_token_gone", status_code=response.status_code)
        return False
    # Pub/Sub acknowledges five statuses only, so a failed read is redelivered rather than lost.
    raise InternalError
```
```python
    async def _get(self, package_name: str, purchase_token: str) -> httpx.Response:
        """Send one signed read; a transport failure is the 500 that makes Pub/Sub redeliver."""
        ...
        except httpx.HTTPError as failure:
            raise InternalError from failure
```
The restore entry point reuses `_get` and re-classifies its own answer: 2xx → the value type,
`_GONE_STATUSES` → `ProofRejected(stage=...)`, everything else and every `httpx.HTTPError` →
`Unavailable(stage=...)`. `UnmappedStoreProduct` is raised after that classification and propagates.

**The status rule to reuse, never re-implement** (lines 155-165):
```python
def _status_for(state: str, expiry: datetime | None,
                evaluated_at: datetime) -> SubscriptionStatus:
    """The subscription's status from Play's own state word, which is the only source here."""
    if state == _CANCELED_STATE:
        # Canceled but not expired is still a paid term: Google says so in the field's own text.
        return (SubscriptionStatus.active if expiry is not None and expiry > evaluated_at
                else SubscriptionStatus.expired)
    return _STATES.get(state, SubscriptionStatus.expired)
```

---

### `src/nativespeaker/api/auth/store_notifications.py` (MOD — value type)

**Analog:** `VerifiedNotification`, same file lines 1-27:
```python
"""The verified store notification both providers fill, in this project's own field names.
A verified notification carries an attribution token: this module holds no logger, so none is logged."""
from dataclasses import dataclass
from datetime import datetime

from nativespeaker.api.tables.purchases import PurchaseProvider, SubscriptionStatus


@dataclass(frozen=True, slots=True)
class VerifiedNotification:
    """One store notification after verification, in this project's own field names."""

    provider: PurchaseProvider
    notification_uuid: str
    event_type: str
    external_id: str | None
    transaction_id: str | None
    product_id: str | None
    # Resolved by the provider's own class, so it is absent exactly when `product_id` is.
    tier_id: str | None
    attribution_token: str | None
    # The store's own word for this subscription, never derived from a date here.
    status: SubscriptionStatus
    signed_at: datetime | None
    purchased_at: datetime | None
    expires_at: datetime | None
    grace_period_expires_at: datetime | None
```
The restore value type is a sibling `@dataclass(frozen=True, slots=True)` in this same module,
carrying only the fields restore consumes. The module holds no logger, and that must stay true: the
new type carries the purchase token in `external_id` on the Google path.

---

### `src/nativespeaker/api/crud/subscriptions.py` (MOD — crud, CRUD)

**Analog for the D-09 one-line change:** the rule lives at lines 105-107 and nowhere else:
```python
        else:
            # An owner is added, never cleared: a later notification without a token unlinks nobody.
            owner = stored.user_id if user_id is None else user_id
```
The comment changes with the expression; the new rule is "the token attributes an unowned row only".

**Analog for the new conditional-UPDATE method:** `upsert_subscription`'s signature, keyword-only
arguments and the flush guard, lines 84-130:
```python
    async def upsert_subscription(self, *,
                                  provider: PurchaseProvider,
                                  external_id: str,
                                  user_id: UUID | None,
                                  tier_id: str,
                                  status: SubscriptionStatus,
                                  signed_at: datetime | None,
                                  evaluated_at: datetime) -> tuple[Subscription, WriteOutcome]:
        """Update the existing canonical row in place, or insert one, and flush it."""
```

**The SQLSTATE guard, repeated identically in five places in this file** (lines 121-130) — copy it
verbatim, comments included, for any new statement that can raise:
```python
        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return stored, WriteOutcome.lost_race
        return stored, outcome
```

**The module-level statement helpers** (lines 41-50) — the new UPDATE statement follows this
"one named function per statement" convention:
```python
def _subscription_statement(provider: PurchaseProvider, external_id: str):
    """The `core.subscriptions` row for the lifecycle pair `ix_subscriptions_provider_external_id` keys."""
    return select(Subscription).where(col(Subscription.provider) == provider,
                                      col(Subscription.external_id) == external_id)
```

**`write_subscription_grant` is called unchanged (D-07).** Its three load-bearing behaviours,
lines 198-219 — the plan must not fork any of them:
```python
        entitled = status in ENTITLED_STATUSES
        held = [grant for grant in marked_active
                if grant.source is AccessGrantSource.subscription
                and grant.subscription_id == subscription_id]
        # The tier is asked with the term: a mid-term tier change takes the same expire-then-insert path below.
        if entitled and [grant for grant in held
                         if grant.ends_at == ends_at and grant.tier_id == tier_id]:
            return WriteOutcome.replayed

        # Every held grant goes, the free one included: `ix_access_grants_one_active_per_user` allows one.
        superseded = list(marked_active) if entitled else held
        ...
        if superseded:
            # Flushed alone and first: the ORM emits inserts before updates, and the index is per-statement.
```

---

### `src/nativespeaker/api/crud/grants.py` (MOD — crud, locking read)

**Analog:** `_active_grants_statement` + `lock_active_grants`, same file lines 45-51 and 98-102.
The two-user lock is the same statement with an `in_` on `user_id`, keeping the single ascending
`order_by` so one statement takes both users' rows in the global lock order:
```python
def _active_grants_statement(user_id: UUID):
    """Every grant of `user_id` marked active, whatever its term, ascending by id."""
    # No time window: a partial index predicate must be IMMUTABLE, so `now()` cannot appear in
    # `ix_access_grants_one_active_per_user`, and its question is therefore asked on the mark alone.
    return (select(AccessGrant).where(col(AccessGrant.user_id) == user_id,
                                      col(AccessGrant.status) == AccessGrantStatus.active)
            .order_by(col(AccessGrant.id).asc()))
```
```python
    async def lock_active_grants(self, user_id: UUID) -> list[AccessGrant]:
        """Lock and return every grant of `user_id` the one-active index sees, ascending by id."""
        # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
        statement = _active_grants_statement(user_id).with_for_update()
        return list((await self.session.exec(statement)).all())
```

**The composition of the two lock tiers** — `SubscriptionsDB.lock_grants`
(`crud/subscriptions.py:60-68`) is the model for the two-user version, and its comments state the
order rule:
```python
    async def lock_grants(self, user_id: UUID, evaluated_at: datetime) -> list[AccessGrant]:
        """Take both lock tiers for one buyer and return every grant row marked active."""
        # First and ascending by id: this set contains the effective one, so one grant-tier order holds.
        marked_active = await self.grants_db.lock_active_grants(user_id)
        effective = await self.grants_db.lock_effective_grants(user_id, evaluated_at)
        for grant in effective:
            # Second in the lock order, always after the grant rows.
            await self.grants_db.lock_usage(grant.id)
        return marked_active
```

---

### `src/nativespeaker/api/errors.py` (MOD — errors)

**Analog:** the `ClaimRefused` block, same file lines 472-505 — one base declares the status and the
code, and every leaf adds only a docstring:
```python
# --- Claim arms ---


class ClaimRefused(AppError):
    """The claim's refusals share this shape, and its leaves add only their own name."""

    # The 403 is declared here and nowhere below, so the refusal cannot become an enumeration oracle.
    status = 403
    code = "operation_not_allowed"


class ClaimantNotAnonymous(ClaimRefused):
    """The stored identity row is registered, so the anonymous claim is not the route that serves it."""


class ClaimantNotRegistered(ClaimRefused):
    """The stored identity row is anonymous, so the registered claim is not the route that serves it."""
```
`ChallengeRejected` (lines 510-535) is the same pattern at 409 with five leaves. Add a
`# --- Restore arms ---` section header in this style, placed after the claim arms.

**The `ErrorCode` literal** (lines 13-31) — the two new codes join this list; `ErrorResponse` and
the totality test both read it:
```python
# The codes the body may carry. A typo is a ValidationError at construction, not a runtime 500.
ErrorCode = Literal["auth_required",
                    ...
                    "proof_rejected",
                    "device_grant_exhausted"]
```

**The keyword-only `stage` constructor the reused leaves need** (lines 380-393) —
`raise ProofRejected()` is a `TypeError`:
```python
class ProviderLookupError(AppError):
    """The provider lookup's rejections share this shape; only its leaves are raised."""

    def __init__(self, *, stage: str, cause: str | None = None) -> None:
        # Plain strings, both of them ours: no provider text is ever admissible in either field.
        self.stage = stage
        self.cause = cause
        super().__init__(f"{type(self).__name__.lower()} at {stage}")
```

**The three leaves restore reuses, unchanged** (lines 406-409, 453-456):
```python
class Unavailable(ProviderLookupError):
    """The read could not be completed: an exhausted retry budget, or no app configured."""
    status = 503
    code = "verification_temporarily_unavailable"


class ProofRejected(ProviderLookupError):
    """Apple refused the device token, or accepted it and refused the bit write."""
    status = 403
    code = "proof_rejected"
```

**`log_fields` when a class carries an identifier** (lines 288-291) — the precedent that keeps the
purchase token out of a log line, which recurs on the Google path where `external_id` *is* the token:
```python
    def log_fields(self) -> dict[str, str | None]:
        # The row's own key, never the lifecycle key: on the Google path the lifecycle key is the
        # purchase token itself (44 D-10), which is not admissible in a log line.
        return {"provider": str(self.provider), "purchase_id": str(self.purchase_id)}
```
The new restore leaves carry no field at all, as `ClaimRefused`'s leaves do, so they need no
`log_fields`.

---

### `tests/unit/test_restore_proof.py` (NEW — test, unit)

**Analog A (Apple):** `tests/unit/test_app_store_notifications.py`.

**The throwaway chain fixture to import, not rebuild** (lines 105, 166-178):
```python
def _build_chain(*, leaf_valid_to: datetime | None = None) -> _Chain:
    """Three EC P-256 keys and three SHA-256 certificates, carrying the two OIDs the library checks."""
```
```python
@pytest.fixture(scope="module")
def chain() -> _Chain:
    """One throwaway chain for the whole module: three key generations and three signings."""
    return _build_chain()


def _mint(chain: _Chain, payload: dict, *,
          key: ec.EllipticCurvePrivateKey | None = None,
          x5c: list[str] | None = None) -> str:
    """One ES256 JWS carrying the three-certificate `x5c` header the library walks."""
    return pyjwt.encode(payload, key if key is not None else chain.leaf_key,
                        algorithm="ES256",
                        headers={"x5c": chain.x5c if x5c is None else x5c})
```
Import these from `unit.test_app_store_notifications` the way that file itself imports from
`unit.test_google_play_notifications` (lines 26-32).

**The control case that makes a chain assertion non-vacuous** (lines 263-271) — restore needs the
same control, since the whole Apple check is local:
```python
    def test_the_vendored_apple_root_refuses_the_same_payload_control(self, chain):
        """The control that makes the case above non-vacuous: the real root does not sign this chain."""
        assert APPLE_ROOT_G3.is_file(), f"{APPLE_ROOT_G3} is the pinned root and must be tracked"
        notifications = _notifications(chain, root_certificates=[APPLE_ROOT_G3.read_bytes()])

        with pytest.raises(NotificationRejected) as refusal:
            notifications.verify(_full(chain))

        assert refusal.value.stage == "VERIFICATION_FAILURE"
```

**The closed-stage-set case to extend** (lines 432-445) — restore's stages must satisfy the same
assertion, with `ProofRejected` substituted:
```python
    def test_every_reachable_stage_is_a_closed_set_name(self, chain):
        """`VerificationStatus.name` is one of eight strings, which is what makes it a safe log label."""
        from appstoreserverlibrary.signed_data_verifier import VerificationStatus

        refusals = []
        for envelope in (_mint(chain, _envelope(chain), x5c=chain.x5c[:2]),
                         _mint(chain, _envelope(chain, bundle_id="com.example.someone-else")),
                         _mint(chain, _envelope(chain, environment="Production"))):
            with pytest.raises(NotificationRejected) as refusal:
                _notifications(chain).verify(envelope)
            refusals.append(refusal.value.stage)

        assert set(refusals) <= {status.name for status in VerificationStatus}
        assert len(set(refusals)) == 3
```

**Analog B (Google):** `tests/unit/test_google_play_notifications.py`.

**The fixed instants and the fake credential** (lines 50-55, 74-81):
```python
# One captured instant for every case below, so no assertion here depends on the wall clock.
EVALUATED_AT = datetime(2026, 6, 1, tzinfo=UTC)
PURCHASED_AT = EVALUATED_AT - timedelta(days=30)
SIGNED_AT = EVALUATED_AT - timedelta(minutes=1)
UNEXPIRED = EVALUATED_AT + timedelta(days=10)
LAPSED = EVALUATED_AT - timedelta(days=1)
```
```python
class _FakeCredential:
    """ADC as the Play read uses it: already valid, so a refresh here is a failure, not a fixture."""

    valid = True
    token = "play-access-token"

    def refresh(self, request):
        raise AssertionError("a valid credential must not be refreshed")
```

**The body builder and the one-call helper** (lines 84-90, 111-120):
```python
def _subscription_body(state: str, *, expiry: datetime | None = None,
                       product_id: str | None = PRODUCT_ID) -> dict:
    """One `subscriptionsv2.get` answer in Google's own field names."""
```
```python
async def _read_through(reader: PlayDeveloperSubscriptions) -> VerifiedNotification | None:
    """One read on this reader, with the arguments the dependency passes in production."""
    return await reader.read(package_name=PACKAGE_NAME, purchase_token=PURCHASE_TOKEN,
                             event_type=EVENT_TYPE, notification_uuid=NOTIFICATION_KEY,
                             signed_at=SIGNED_AT)
```
The restore file gets its own `_restore_through(...)` on the same lines, calling the new entry point.
The Pitfall-1 case (an unmapped Play product must answer 500, not 503) belongs here.

---

### `tests/e2e/test_restore_subscription.py` (NEW — test, e2e)

**Analog:** `tests/e2e/test_claim_registered_grant.py`.

**Module header, the marker and the byte-identical refusal literals** (lines 1-46):
```python
"""The registered account-grant claim, end to end through the real router against a real database."""
...
pytestmark = pytest.mark.e2e

SUBJECT = "tracer-claim-registered-subject"

# The one body every refusal answers with, compared by equality so a more helpful field fails here.
REFUSED = {"code": "operation_not_allowed"}

# The same body as bytes, so the four refusals are compared on the wire and not after parsing.
REFUSED_BODY = '{"code":"operation_not_allowed"}'
```

**The client fixture and the auth helper** (lines 49-58):
```python
@pytest_asyncio.fixture(loop_scope="module")
async def claim_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}
```

**The row-reading helpers the assertions use** (lines 83-107):
```python
async def _grants_of(factory, user_id) -> list[AccessGrant]:
    """Every grant row of `user_id`, in the same ascending order the writer locks them."""
    async with factory() as session:
        return list((await session.exec(
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id)
            .order_by(col(AccessGrant.id).asc()))).all())


async def _row_counts(factory, user_id) -> tuple[int, int]:
    """The grant and usage row counts for `user_id`: the two kinds a claim writes."""
```
These are what "nothing was written" assertions read on the `restore_not_found` and
`restore_transfer_rejected` cases.

**The store-class fakes to script** — `tests/e2e/conftest.py` lines 296-316 and 430-439:
```python
@pytest.fixture
def scripted_app_store_notifications(_app_lifespan):
    """Swap app.state.app_store_notifications for a scripted fake, scripted per case."""
    original = _app_lifespan.state.app_store_notifications
    notifications = FakeAppStoreNotifications()
    _app_lifespan.state.app_store_notifications = notifications
    try:
        yield notifications
    finally:
        _app_lifespan.state.app_store_notifications = original
```
```python
@pytest.fixture
def scripted_play_subscriptions(_app_lifespan):
    """Swap app.state.play_subscriptions for a scripted fake, scripted per case."""
```
Both fakes use the same raise-or-return contract (`conftest.py:284-293`, `404-417`):
```python
    def script(self, answer: BaseException | VerifiedNotification) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted notification is returned."""
        self.answer = answer
```
The two fakes gain one restore method each, mirroring the new entry points.

---

### `tests/schema/test_restore_race.py` (NEW — test, schema)

**Analog:** `tests/schema/test_subscription_race.py`.

**The private-key harness and its child-first cleanup** (lines 37-75):
```python
@dataclass
class _Harness:
    engine: object
    factory: async_sessionmaker
    uuid_prefix: str
    external_id: str


@pytest_asyncio.fixture
async def harness(_schema_db_uri):
    """A committing session factory plus this test's private store key and lifecycle key."""
    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    private = uuid.uuid4().hex[:10]
    ...
```
```python
async def clean_up(harness: _Harness) -> None:
    """Child-first: the event rows, then the purchase rows, then the subscriptions they pointed at."""
```
Restore's cleanup must also delete `core.access_grants` and `core.user_monthly_usage` rows, which
this analog does not create.

**The SQLSTATE-recording session, which is also RESEARCH Pattern 1's ordering recorder** (lines
77-91):
```python
class _RacedSession(_RacingSession):
    """The claim race's session, plus the SQLSTATE its violation carried."""

    def __init__(self, session, before_first_flush=None) -> None:
        super().__init__(session, before_first_flush)
        self.sqlstate: str | None = None

    async def flush(self, *args, **kwargs):
        try:
            return await super().flush(*args, **kwargs)
        except IntegrityError as violation:
            # The classification is the SQLSTATE alone; nothing here reads a message or an index.
            self.sqlstate = violation.orig.sqlstate
            raise
```
Pitfall 2 needs the same recording around `commit()`, not only `flush()`, because a deferred foreign
key raises 23503 at commit.

**The per-attempt observation record and its bucketing** (lines 93-116):
```python
@dataclass
class _Attempt:
    """One delivery's notification and everything observable about what it did."""

    name: str
    notification: VerifiedNotification
    # What the call produced: nothing when it committed, or the rejection it raised.
    result: AppError | None = None
    events_seen_at_barrier: int | None = None
    sqlstate: str | None = None
    integrity_at_flush: bool = False
    integrity_at_commit: bool = False
    # Every write the writer emits goes through one of these, so zero means the attempt wrote nothing.
    flushes: int = 0
```
```python
def status_of(attempt: _Attempt) -> int:
    """The status the route would have answered: a completed ingestion is a 200."""
    return attempt.result.status if isinstance(attempt.result, AppError) else 200
```
`integrity_at_commit` already exists on this dataclass and is exactly Pitfall 2's observable.

---

### `tests/e2e/conftest.py` (MOD — a `seed_subscription` factory)

**Analog A:** `seed_grant`, same file lines 536-565 — the signature style, the `factory` first
argument, the keyword defaults and the return of both rows:
```python
async def seed_grant(factory, *,
                     user_id: UUID,
                     tier_id: str = REGISTERED_TIER_ID,
                     source: AccessGrantSource = AccessGrantSource.manual,
                     status: AccessGrantStatus = AccessGrantStatus.active,
                     ...
                     with_usage: bool = True):
    """Insert a core.access_grants row and its core.user_monthly_usage row; return both."""
    # A grant with no usage row is a 500 rather than a 429, so with_usage=False is only for that case.
    now = datetime.now(UTC)
    async with factory() as session:
        grant = AccessGrant(...)
        session.add(grant)
        await session.flush()
        ...
        await session.commit()
    return grant, usage
```

**Analog B:** the subscription insert itself already exists in
`tests/e2e/test_claim_registered_grant.py` lines 117-138 — lift it into `conftest.py` rather than
re-deriving the column list:
```python
async def _seed_subscription_grant(factory, *, user_id) -> AccessGrant:
    """Insert an active subscription and the grant it entitles; `seed_grant` cannot carry the id."""
    now = datetime.now(UTC)
    subscription_id = uuid4()
    async with factory() as session:
        await session.exec(text(
            "INSERT INTO core.subscriptions"
            " (id, user_id, provider, external_id, tier_id, status, created_at, updated_at)"
            " VALUES (:id, :user_id, 'apple', :external_id, 'registered', 'active', :now, :now)")
            .bindparams(id=subscription_id, user_id=user_id,
                        external_id=f"e2e-subscription-{subscription_id}", now=now))
        grant = AccessGrant(user_id=user_id, ... subscription_id=subscription_id, ...)
```
The restore factory needs `user_id=None` (adoption) and a `last_cross_account_transfer_month`
argument, which this statement does not carry today.

**`seed_purchase_tokens`** (lines 568-583) is the analog for seeding the attribution binding that
`PurchasesDB.resolve_user` reads.

---

### Ratchet mirrors (MOD — tests, no new pattern)

Each is a literal edit in place; the analog is the literal's own current text.

| File | Line(s) | Current text | Change |
|------|---------|--------------|--------|
| `tests/unit/test_app_wiring.py` | 70-72, 79-81 | `@pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous", "/auth/claim-anonymous-grant", "/auth/claim-registered-grant", "/users/me"))` | add `"/auth/restore-subscription"` to both lists |
| `tests/unit/test_error_contract.py` | 19-25 | `CONTRACT_CODES = {...}` | add both new codes |
| `tests/unit/test_rejection_vocabulary.py` | 41-60 | `CHALLENGE_ARMS` / `UPGRADE_ARMS` / `CLAIM_ARMS` tuples and `EVENT_NAMES` frozenset | add a `RESTORE_ARMS` tuple on the same "listed rather than derived" comment style, and one `EVENT_NAMES` entry per new class |
| `tests/unit/test_auth_package_shape.py` | 13 | `CURRENT = (8, 23, 53)` | re-measure, do not guess |
| `tests/unit/test_subscription_attribution.py` | 113-114 | `# The same rule the crud holds: an owner is added, never cleared.` / `stored.user_id = stored.user_id if fields["user_id"] is None else fields["user_id"]` | mirror D-09's new expression and rewrite the comment with it |

## Shared Patterns

### The lock order, stated in every module that takes a lock
**Source:** `crud/grants.py:1-2`, `crud/subscriptions.py:1-2`
**Apply to:** `crud/grants.py`, `crud/subscriptions.py`, `services/restore.py`
```python
"""Entitlement reads over `core.access_grants`, and the one writer of each of the two free grants.
Global lock order: grant rows ascending by id, then usage rows, and never a third tier."""
```
```python
"""Store-subscription writes over `core.subscriptions`, `audit.subscription_events` and the buyer's grant.
Lock order: grant rows ascending by id, then their usage rows; the subscription row is never locked."""
```

### The SQLSTATE-23505 guard around a flush
**Source:** `crud/subscriptions.py:121-129` (repeated at 151-159, 177-185, 217-226, 248-256);
`crud/grants.py:173-181`
**Apply to:** every new crud statement that can raise `IntegrityError`
```python
        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return WriteOutcome.lost_race
        return WriteOutcome.applied
```

### The one captured instant
**Source:** `services/subscriptions.py:23-24`, `services/sync.py:21-22`,
`app/dependencies.py:125-127`
**Apply to:** `services/restore.py`, `app/dependencies.py`
```python
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
```
```python
def get_evaluated_at() -> datetime:
    """One instant per request, shared by construction: FastAPI caches this dependency per request."""
    return datetime.now(UTC)
```

### The fail-closed read that raises its own rejection
**Source:** `services/sync.py:45-53`
**Apply to:** `services/restore.py`'s entitlement decision (D-06) and every read whose absence is
not an ordinary outcome
```python
        usage = await self.grants_db.read_usage(grant.id)
        if usage is None:
            # Fail closed: reporting zero used would promise an allowance the charge refuses at this same instant.
            raise MissingUsageRowError(grant.id)

        allowance = await self.grants_db.monthly_credits(grant.tier_id)
        if allowance is None:
            # Fail closed: a missing tier row is neither a zero allowance nor an unbounded one.
            raise UnknownTierError(grant.tier_id, grant.id)
```

### Positive membership tests, never negative ones
**Source:** `services/auth.py:168-170`, `205-207`; `crud/grants.py:29-30`
**Apply to:** the `provider not in PurchaseProvider` gate, the entitlement test against
`ENTITLED_STATUSES`, and the branch decision
```python
        # D-08: the stored provider column is the sole classifier, and it is tested positively.
        if identity.identity.provider is not IdentityProvider.anonymous:
            raise ClaimantNotAnonymous
```
```python
               # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
               col(AccessGrant.status) == AccessGrantStatus.active,
```

### Log labels come from a closed set, never from a store value
**Source:** `services/subscriptions.py:144-145`, `auth/google_play.py:1-2`,
`auth/store_notifications.py:1-2`, `errors.py:288-291`
**Apply to:** every logger call and every `stage=` value this phase writes. On the Google path
`external_id` **is** the purchase token, so it is never admissible.
```python
        # Labels come from a closed set only: the store's own name, never a payload value.
        logger.warning("store_notification_race_lost", provider=str(notification.provider))
```
```python
"""The Google Play integration: the Pub/Sub push token, the RTDN body, and the live subscription read.
Log labels come from a closed set: the purchase token, the push token and every Play value are excluded."""
```

### Comment and docstring shape (AGENTS.md, D-15)
**Source:** every file above
**Apply to:** every line this phase writes
- Docstrings: three lines maximum, stripped body. `tests/unit/test_docstring_bar.py` BASELINE is
  `0` over-long docstrings on all five roots, and it walks modules, classes, functions and methods.
- Comments: one line, placed above the lines they explain, ASD-STE100, default to none. The
  established form is a reason, not a restatement — for example
  `# Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.`

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.planning/REQUIREMENTS.md`, `.planning/STATE.md` (D-13 amendments) | docs | — | Planning documents, not code. The format analog is the existing dated-amendment entries in those same files, which the planner reads directly; no source pattern applies. |

Two source items have a **partial** analog only, and the planner should note the gap:

- **The conditional UPDATE with `IS NOT DISTINCT FROM`** — no `sqlalchemy.update()` construct exists
  anywhere in `crud/`. Every write today is ORM attribute assignment plus a flush. The signature,
  the keyword-only arguments and the docstring style copy `upsert_subscription`
  (`crud/subscriptions.py:84-92`), but the statement itself is new. RESEARCH § Pattern 4 carries the
  measured verification that `ColumnOperators.is_not_distinct_from` exists on the installed
  SQLAlchemy 2.0.46, and RESEARCH § Example 5 sketches the method.
- **A `tests/schema` case asserting SQLSTATE 23503 at commit** — `_Attempt.integrity_at_commit`
  exists on the analog dataclass (`tests/schema/test_subscription_race.py:104`) but no case in the
  repository sets it. The recorder shape is the analog; the assertion is new.

## Metadata

**Analog search scope:** `src/nativespeaker/api/{routers,services,crud,schemas,auth,app,tables}`,
`src/nativespeaker/api/errors.py`, `tests/unit`, `tests/e2e`, `tests/schema`
**Files scanned:** 24 read in full or in targeted ranges; all verified git-tracked
**Pattern extraction date:** 2026-09-07
