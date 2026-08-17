from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import structlog
from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth import verified_identity
from nativespeaker.api.config import AppConfig
from nativespeaker.api.database import UsageDB
from nativespeaker.api.database.usage import GrantsDB, current_period
from nativespeaker.api.exceptions import AuthenticationError, QuotaExceededError
from nativespeaker.api.models import User
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


async def require_quota(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)) -> None:
    """Atomically increment the effective grant's usage counter; raise 429 when the monthly
    allowance is exhausted. The allowance is the tier of the user's single effective access
    grant, and a user with no effective grant has an allowance of zero."""
    now = datetime.now(UTC)
    grant = await GrantsDB(db).effective_grant(user.id, now)
    # Entitlement is the grant. A user with no effective grant is refused here, before any
    # usage row is read: a counter is not access and never stands in for one.
    # [impl->req~schema-user-monthly-usage-grants-no-access~1]
    if grant is None or grant.monthly_credits <= 0:
        raise QuotaExceededError("Monthly quota exceeded")
    usage_db = UsageDB(db)
    if not await usage_db.try_increment(grant.grant_id, current_period(now),
                                        grant.monthly_credits):
        raise QuotaExceededError("Monthly quota exceeded")
