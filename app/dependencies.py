from collections.abc import AsyncGenerator

from fastapi import Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenVerifier
from app.config import AppConfig
from app.database import session_factory
from app.exceptions import AuthenticationError, DatabaseNotInitializedError
from app.services import AnalysisService


def get_service(request: Request) -> AnalysisService:
    return request.app.state.service


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if session_factory is None:
        raise DatabaseNotInitializedError()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_user_id(request: Request, authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Missing Bearer token")
    verifier: TokenVerifier = request.app.state.verifier
    return verifier.verify(token)
