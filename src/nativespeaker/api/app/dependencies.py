from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import structlog
from fastapi import Header, Request
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nativespeaker.api.auth import TokenVerifier
from nativespeaker.api.config import AppConfig
from nativespeaker.api.database import UsageDB
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
                           authorization: str | None = Header(None),
                           db: AsyncSession = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Missing Bearer token")
    verifier: TokenVerifier = request.app.state.jwt_verifier
    identity = verifier.verify(token)
    user_service = UserService(db)
    user = await user_service.get_or_create(identity)
    if not user.active:
        raise AuthenticationError("Authentication failed")
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


async def require_quota(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        config: AppConfig = Depends(get_config)) -> None:
    """Atomically increment usage counter; raise 429 if monthly quota exhausted."""
    month = datetime.now(UTC).strftime("%Y-%m")
    monthly_quota = config.quotas[user.subscription_plan]
    usage_db = UsageDB(db)
    if not await usage_db.try_increment(user.id, month, monthly_quota):
        raise QuotaExceededError("Monthly quota exceeded")
