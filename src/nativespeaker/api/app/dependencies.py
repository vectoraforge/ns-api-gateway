from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.adapters import FirebaseAdminAdapter
from nativespeaker.api.auth.google_play import (
    developer_notification_from,
    instant_from_millis,
    notification_key_for,
    subscription_notification_from,
)
from nativespeaker.api.auth.jwt_verifier import BoundedReason
from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.config import AppConfig
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.errors import (
    InvalidExternalJwt,
    NotificationRejected,
    PreAuthIdentityNotAllowed,
)
from nativespeaker.api.schemas.auth import Identity, LinkedIdentity
from nativespeaker.api.schemas.webhooks import AppStoreNotificationRequest, PubSubPushRequest
from nativespeaker.api.services import (
    AuthService,
    ChatService,
    QuotaService,
    RestoreService,
    SubscriptionsService,
    SyncService,
)


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    """The request session: it rolls back on the way out, and never commits."""
    # FastAPI resumes this generator on the request's inner exit stack, which `fastapi/routing.py`
    # closes only after `await response(...)`. A commit written here would therefore run once the
    # body is on the wire, where its failure reaches nobody -- the caller reads 200 for a
    # transaction that rolled back. Every write commits in its own service or handler instead.
    async with request.app.state.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# `auto_error=False`: our own code raises, so the rejection keeps its class, code and log event.
_bearer = HTTPBearer(auto_error=False)

#: The raw ASGI field name. ASGI lowercases every field name, so differently-cased duplicates fold into it.
_AUTHORIZATION = b"authorization"


async def get_identity(request: Request,
                       credential: HTTPAuthorizationCredentials | None = Depends(_bearer),
                       ) -> Identity:
    """Accept the token and resolve the identity it names -- once per request."""
    # Counted on the raw scope before any value is read: the merged view returns the first field
    # value and hides the rest, so a second Authorization field would otherwise win by position.
    if sum(1 for name, _value in request.scope["headers"] if name == _AUTHORIZATION) > 1:
        raise InvalidExternalJwt(bounded_reason=BoundedReason.duplicate_authorization)

    if credential is None:
        # `HTTPBearer` also answers `None` for a non-Bearer scheme and an empty token, which spec 01
        # §1.1 calls `malformed`; only zero field values are `missing_token`.
        presented = request.headers.get("authorization") is not None
        raise InvalidExternalJwt(bounded_reason=BoundedReason.malformed if presented
                                 else BoundedReason.missing_token)

    # `verify` is synchronous and can block on a JWKS fetch, so it never runs on the event loop.
    claims, reason = await run_in_threadpool(request.app.state.jwt_verifier.verify,
                                             credential.credentials)
    if claims is None:
        # `verify` is typed to allow `(None, None)`, and a null label would reach the log as the
        # string "None" -- a population the spike alert cannot name.
        raise InvalidExternalJwt(bounded_reason=reason or BoundedReason.bad_signature)

    # Its own short session, closed before the handler: Depends(get_db) would hold it across the provider call.
    async with request.app.state.session_factory() as session:
        # allow_preauth=True here; `get_linked_identity` is the dependency that narrows to linked callers.
        return await IdentitiesDB(session).resolve(issuer=claims.issuer,
                                                   subject=claims.subject, allow_preauth=True)


# Declared, never called directly: FastAPI's cache only sees solver-resolved deps, so a direct call re-verifies.
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> LinkedIdentity:
    """The resolved user and identity row; rejects an unlinked caller with 403."""
    # Both rows, not just the user: a user-only pair is the unresolvable state, and it fails closed
    # here rather than as an `AttributeError` eight handlers deep.
    if identity.user is None or identity.identity is None:
        raise PreAuthIdentityNotAllowed
    return LinkedIdentity(issuer=identity.issuer, subject=identity.subject,
                          user=identity.user, identity=identity.identity)


def get_session_factory(request: Request) -> async_sessionmaker:
    """The one factory the lifespan built."""
    return request.app.state.session_factory


def get_quota_service(session_factory: async_sessionmaker = Depends(get_session_factory)) -> QuotaService:
    # The factory, not `get_db`: the charge commits in its own session while the request session stays open.
    return QuotaService(session_factory=session_factory)


def get_evaluated_at() -> datetime:
    """One instant per request, shared by construction: FastAPI caches this dependency per request."""
    return datetime.now(UTC)


# Defined below the dependencies it declares, because its `Depends()` defaults are evaluated at definition time.
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config),
                     quota_service: QuotaService = Depends(get_quota_service),
                     evaluated_at: datetime = Depends(get_evaluated_at)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit,
                       quota_service=quota_service,
                       # The solver-resolved instant, never a second `now()`: the quota charge
                       # below it is a time-dependent write.
                       evaluated_at=evaluated_at)


# These two accessors exist so a challenge-bearing route can stay Depends()-only and never take Request itself.
def get_challenge_store(request: Request) -> ChallengesDB:
    """The one `ChallengesDB` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.challenge_store


def get_firebase_adapter(request: Request) -> FirebaseAdminAdapter:
    """The provider seam the lifespan built."""
    # The Protocol declares both methods async, which is what the concrete class implements.
    return request.app.state.firebase_adapter


def get_devicecheck_adapter(request: Request):
    """The device-gate seam the lifespan built, deliberately unannotated."""
    return request.app.state.devicecheck_adapter


def get_auth_service(db: AsyncSession = Depends(get_db),
                     challenge_store: ChallengesDB = Depends(get_challenge_store),
                     adapter=Depends(get_firebase_adapter),
                     devicecheck=Depends(get_devicecheck_adapter),
                     evaluated_at: datetime = Depends(get_evaluated_at)) -> AuthService:
    return AuthService(db=db,
                       challenge_store=challenge_store,
                       adapter=adapter,
                       devicecheck=devicecheck,
                       evaluated_at=evaluated_at)


def get_sync_service(db: AsyncSession = Depends(get_db),
                     evaluated_at: datetime = Depends(get_evaluated_at)) -> SyncService:
    return SyncService(db=db, evaluated_at=evaluated_at)


def get_subscriptions_service(db: AsyncSession = Depends(get_db),
                              evaluated_at: datetime = Depends(get_evaluated_at),
                              ) -> SubscriptionsService:
    return SubscriptionsService(db=db, evaluated_at=evaluated_at)


# Takes `Request` for the store class the lifespan built, as `get_chat_service` above does.
def get_restore_service(request: Request,
                        db: AsyncSession = Depends(get_db),
                        evaluated_at: datetime = Depends(get_evaluated_at)) -> RestoreService:
    return RestoreService(db=db,
                          evaluated_at=evaluated_at,
                          app_store=request.app.state.app_store_notifications,
                          play=request.app.state.play_subscriptions,
                          package_name=request.app.state.config.google_play.package_name)


def verify_app_store_notification(request: Request,
                                  body: AppStoreNotificationRequest) -> VerifiedNotification:
    """Turn the posted envelope into a verified notification, before the handler and before `get_db`."""
    # Never `run_in_threadpool`: with online checks off, no code path in the seam performs I/O.
    return request.app.state.app_store_notifications.verify(body.signedPayload)


async def verify_google_play_notification(
        request: Request,
        body: PubSubPushRequest,
        credential: HTTPAuthorizationCredentials | None = Depends(_bearer),
        evaluated_at: datetime = Depends(get_evaluated_at),
) -> VerifiedNotification | None:
    """Verify the push token and read the live subscription, before the handler and before `get_db`."""
    if credential is None:
        raise NotificationRejected(stage="push_credential_absent")

    await request.app.state.google_push_tokens.verify(credential.credentials)
    # Decoded only after the token check, so a forged body is never parsed.
    notification = developer_notification_from(body.message.data)
    if notification is None:
        return None

    subscription = subscription_notification_from(notification)
    if subscription is None:
        return None

    if notification.packageName != request.app.state.config.google_play.package_name:
        # Refused before the Play call: this delivery names an application this deployment does not serve.
        raise NotificationRejected(stage="package_name_mismatch")

    event_type = str(subscription.notificationType)
    return await request.app.state.play_subscriptions.read(
        package_name=notification.packageName,
        purchase_token=subscription.purchaseToken,
        event_type=event_type,
        notification_uuid=notification_key_for(subscription.purchaseToken,
                                               notification.eventTimeMillis, event_type),
        # Google's own instant for the event, which is what the out-of-order guard compares.
        signed_at=instant_from_millis(notification.eventTimeMillis),
        # Solver-resolved, so the adapter's entitlement decision and `SubscriptionsService`'s
        # grant write are made at the one instant FastAPI cached for this request.
        evaluated_at=evaluated_at)


# This accessor exists so the profile route can stay Depends()-only and never construct a database class itself.
def get_purchases_db(db: AsyncSession = Depends(get_db)) -> PurchasesDB:
    return PurchasesDB(db)
