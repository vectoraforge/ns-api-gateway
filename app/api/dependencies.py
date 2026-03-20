from collections.abc import AsyncGenerator

import structlog
from fastapi import Header, Request
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenVerifier
from app.config import AppConfig
from app.exceptions import AuthenticationError
from app.models import User
from app.services import ChatService, UserService


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


async def get_current_user(request: Request,
                           authorization: str | None = Header(None),
                           db: AsyncSession = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Missing Bearer token")
    verifier: TokenVerifier = request.app.state.verifier
    identity = verifier.verify(token)
    user_service = UserService(db)
    user = await user_service.get_or_create(identity)
    if not user.active:
        raise AuthenticationError("Authentication failed")
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user
