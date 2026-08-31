from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.config import AppConfig
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import InvalidExternalJwt, PreAuthIdentityNotAllowed
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.services import AuthService, ChatService, QuotaService


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


# `auto_error=False`: our own code raises, so the rejection keeps its class, code and log event.
_bearer = HTTPBearer(auto_error=False)


# Declared in `APIRouter(dependencies=[...])` on every non-public router, so auth is default-on.
async def get_identity(request: Request,
                       credential: HTTPAuthorizationCredentials | None = Depends(_bearer),
                       ) -> Identity:
    """Accept the token and resolve the identity it names -- once per request."""
    if credential is None:
        raise InvalidExternalJwt(bounded_reason=None)

    # `verify` is synchronous and can block on a JWKS fetch, so it never runs on the event loop.
    claims, reason = await run_in_threadpool(request.app.state.jwt_verifier.verify,
                                             credential.credentials)
    if claims is None:
        raise InvalidExternalJwt(bounded_reason=reason)

    # Its own short session, closed before the handler: Depends(get_db) would hold it across the provider call.
    async with request.app.state.session_factory() as session:
        # allow_preauth=True here; get_linked_identity narrows, so create-user can answer 409 not 403.
        # Rejections raise through untouched: the handler is the one site that records them.
        return await IdentitiesDB(session).resolve(issuer=claims.issuer,
                                                   subject=claims.subject, allow_preauth=True)


# Declared, never called directly: FastAPI's cache only sees solver-resolved deps, so a direct call re-verifies.
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> Identity:
    """The resolved user and identity row; rejects an unlinked caller with 403."""
    if identity.user is None:
        raise PreAuthIdentityNotAllowed
    return identity


def get_session_factory(request: Request) -> async_sessionmaker:
    """The one factory the lifespan built. Taken by a caller that needs its own short session, not `get_db`'s."""
    return request.app.state.session_factory


def get_quota_service(session_factory: async_sessionmaker = Depends(get_session_factory)) -> QuotaService:
    # The factory, not `get_db`: the charge commits in its own session while the request session stays open.
    return QuotaService(session_factory=session_factory)


# Defined below the dependencies it declares, because its `Depends()` defaults are evaluated at definition time.
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config),
                     quota_service: QuotaService = Depends(get_quota_service)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit,
                       quota_service=quota_service,
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC))


# These two accessors exist so a challenge-bearing route can stay Depends()-only and never take Request itself.
def get_challenge_store(request: Request) -> ChallengesDB:
    """The one `ChallengesDB` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.challenge_store


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
