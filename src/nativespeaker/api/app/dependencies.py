from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import NoReturn
from uuid import uuid7

import structlog
from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import (
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.auth.identity import Reject, resolve_identity
from nativespeaker.api.auth.wire import BoundedReason, extract_bearer
from nativespeaker.api.config import AppConfig
from nativespeaker.api.errors import (
    AUTH_REQUIRED,
    PREAUTH_IDENTITY_NOT_ALLOWED,
    AuthenticationError,
    AuthRejectionError,
    ErrorClass,
)
from nativespeaker.api.models.auth import AuthEventResult
from nativespeaker.api.quota import QuotaGate
from nativespeaker.api.services import ChatService

logger = structlog.get_logger()


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


# Declared in `APIRouter(dependencies=[...])` on every non-public router, so auth is default-on.
async def get_request_context(request: Request) -> RequestContext:
    """Accept the token, resolve the identity, and build the request context -- once per request."""
    # One evaluation time and one attempt id per request, so no two reads straddle a boundary.
    evaluated_at = datetime.now(UTC)
    attempt_id = uuid7()

    route = request.scope["route"].path

    token, reason = extract_bearer(request.headers.raw)
    if token is None:
        _reject(AUTH_REQUIRED, AuthEventResult.invalid_external_jwt, reason, route)

    # `verify` is synchronous and can block on a JWKS fetch, so it never runs on the event loop.
    claims, reason = await run_in_threadpool(request.app.state.jwt_verifier.verify, token)
    if claims is None:
        _reject(AUTH_REQUIRED, AuthEventResult.invalid_external_jwt, reason, route)

    # Its own short session, closed before the handler: Depends(get_db) would hold it across the provider call.
    async with request.app.state.session_factory() as session:
        # allow_preauth=True here; get_linked_identity narrows, so create-user can answer 409 not 403.
        decision = await resolve_identity(session, issuer=claims.issuer,
                                          subject=claims.subject, allow_preauth=True)

    if isinstance(decision, Reject):
        _reject(decision.error_class, decision.result, None, route)

    return RequestContext(identity=decision.identity,
                          route=route,
                          evaluated_at=evaluated_at,
                          attempt_id=attempt_id)


def _reject(error_class: ErrorClass, result: AuthEventResult,
            bounded_reason: BoundedReason | None, route: str) -> NoReturn:
    """Record the rejection, then raise it; `NoReturn` lets each call site stand as a bare statement."""
    # The structured security log is the only record a rejection leaves.
    # `route` is the path template, never the caller's raw path.
    reason = None if bounded_reason is None else str(bounded_reason)
    logger.warning("auth_rejected", result=str(result), bounded_reason=reason, route=route)
    raise AuthRejectionError(error_class, f"admission rejected on {route}: {result}")


# Declared, never called directly: FastAPI's cache only sees solver-resolved deps, so a direct call re-verifies.
async def get_linked_identity(
        context: RequestContext = Depends(get_request_context)) -> LinkedIdentity:
    """The resolved user and identity row; rejects an unlinked caller with 403."""
    identity = context.identity
    if not isinstance(identity, LinkedIdentity):
        _reject(PREAUTH_IDENTITY_NOT_ALLOWED, AuthEventResult.preauth_identity_not_allowed,
                None, context.route)
    return identity


async def get_preauth_identity(
        context: RequestContext = Depends(get_request_context)) -> PreAuthIdentity:
    """The verified (issuer, subject) of an unlinked caller. Raises when the caller is linked."""
    # Nothing declares this today; create-user reads the variant off the context and answers 409.
    identity = context.identity
    if not isinstance(identity, PreAuthIdentity):
        raise AuthenticationError("Identity context is linked on a route expecting a pre-auth identity")
    return identity


# Defined below the accessors because its `Depends()` default is evaluated at definition time.
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config),
                     context: RequestContext = Depends(get_request_context)) -> ChatService:
    # Declared, not fetched, so it shares the one cached context this request already resolved.
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit,
                       quota_gate=get_quota_gate(request, context))


# These two accessors exist so a challenge-bearing route can stay Depends()-only and never take Request itself.
def get_challenge_store(request: Request) -> ChallengeStore:
    """The one `ChallengeStore` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.challenge_store


def get_firebase_adapter(request: Request):
    """The provider seam the lifespan built, deliberately unannotated."""
    # The concrete class implements the Protocol's one reachable method asynchronously, not synchronously.
    return request.app.state.firebase_adapter


# Consumption travels as QuotaGate, which ChatService calls at the resilience layer's admission callback.
def get_quota_gate(request: Request, context: RequestContext) -> QuotaGate:
    """Build the charge seam; QuotaGate takes the session factory, so no transaction spans the provider call."""
    # A route-level charge would bill callers for requests the service then refuses.
    identity = context.identity
    if not isinstance(identity, LinkedIdentity):
        # Unreachable: these routes declare get_linked_identity at router level. Fails closed anyway.
        raise AuthenticationError("Identity context is pre-auth on a quota-checked route")
    return QuotaGate(request.app.state.session_factory,
                     # Both from the request's captured instant; nothing here reads the clock.
                     evaluated_at=context.evaluated_at,
                     route=context.route)
