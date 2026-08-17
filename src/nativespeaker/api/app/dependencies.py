from collections.abc import AsyncGenerator

import structlog
from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth import verified_identity
from nativespeaker.api.config import AppConfig
from nativespeaker.api.database.usage import QuotaStoreDB
from nativespeaker.api.exceptions import AuthenticationError
from nativespeaker.api.models import User
from nativespeaker.api.quota.rollover import (
    QUOTA_ADMISSION_ENTRY,
    QUOTA_ADMISSION_KEY_POLICY,
    consume_quota,
    quota_admission,
)
from nativespeaker.api.ratelimit.keys import IdentitySource, KeyMaterial, build_key
from nativespeaker.api.ratelimit.limiter import RateLimiter
from nativespeaker.api.ratelimit.ordering import AdmissionLedger
from nativespeaker.api.services import ChatService, SubscriptionService, UserService


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit)


def get_subscription_service(request: Request,
                             db: AsyncSession = Depends(get_db),
                             config: AppConfig = Depends(get_config)) -> SubscriptionService:
    return SubscriptionService(
        db=db,
        verifier=request.app.state.apple_verifier,
        firebase_service=request.app.state.firebase_service,
        product_id_to_plan=config.apple.product_id_to_plan,
    )


async def get_current_user(request: Request,
                           db: AsyncSession = Depends(get_db)) -> User:
    """The handler-side view of the barrier's typed verified identity context.

    This dependency accepts no external JWT, reads no `Authorization` header and resolves no
    identity: the shared pre-handler barrier already did all three, once, for every
    authenticated route. All that is left here is loading the business row the barrier's
    resolved user id names.
    """
    # [impl->req~shared-prehandler-barrier~1]
    # [impl->req~shared-identity-from-verified-claims-only~1]
    context = verified_identity(request)
    if context.user_id is None:
        # A pre-auth identity reached a route the barrier admits it on; no business row exists.
        raise AuthenticationError("Authentication failed")
    user = await UserService(db).get_by_id(context.user_id)
    if user is None or not user.active:
        raise AuthenticationError("Authentication failed")
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


async def require_quota(request: Request,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)) -> None:
    """The quota-checked request path: backend admission first, then the lazy monthly rollover
    sequence.

    Admission is the configured `quota_checked_request` entry, keyed by the authenticated
    internal `core.users.id` the barrier resolved, and it runs before any database quota
    mutation. Entitlement is separate and comes after: the allowance is the tier of the user's
    single effective access grant, and a user with no effective grant has an allowance of zero.
    """
    # [impl->req~quota-admission-before-quota-mutation~1]
    # [impl->req~quota-admission-independent-of-entitlement~1]
    ledger = AdmissionLedger(request.method, request.url.path)
    ledger.verify_jwt()
    ledger.admit_barrier()
    limiter: RateLimiter = request.app.state.rate_limiter
    # [impl->req~quota-admission-keyed-by-user-id~1]
    key = build_key(QUOTA_ADMISSION_KEY_POLICY,
                    KeyMaterial(user_id=user.id,
                                barrier_admitted=True,
                                identity_source=IdentitySource.backend_barrier))
    quota_admission(ledger, user_id=user.id,
                    decision=limiter.consume(QUOTA_ADMISSION_ENTRY, key))
    # Entitlement is the grant. A user with no effective grant is refused inside the sequence,
    # before any counter is read: a counter is not access and never stands in for one.
    # [impl->req~schema-user-monthly-usage-grants-no-access~1]
    # [impl->req~quota-rollover-after-admission~1]
    await consume_quota(QuotaStoreDB(db), user_id=user.id, ledger=ledger)
