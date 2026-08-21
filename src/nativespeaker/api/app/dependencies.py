from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.context import (
    REQUEST_CONTEXT_SCOPE_KEY,
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.config import AppConfig
from nativespeaker.api.errors import AuthenticationError
from nativespeaker.api.services import ChatService


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


# ---------------------------------------------------------------------------
# The §1.4 identity accessors (D-02)
#
# Routes stay Depends()-only: a handler reads the one object the barrier attached and never
# re-verifies a token or re-resolves identity.
#
# Each accessor RAISES rather than returning None -- that is §1.4's "fails loudly". A route
# registered outside the barrier has no identity context, and `auth_required` is the only safe
# reading of that: a None a handler could treat as anonymous is exactly the silently-open route
# the rule exists to prevent. Putting the check here, once, stops each of the seven later phases
# re-implementing it.
#
# None of the three creates, links, repairs, reassigns, or merges a row on any path. They are
# synchronous and take nothing but the Request -- there is no session to write through.
# ---------------------------------------------------------------------------


def get_request_context(request: Request) -> RequestContext:
    """The §1.4 context the barrier attached. Raises when the barrier did not run."""
    context = getattr(request.state, REQUEST_CONTEXT_SCOPE_KEY, None)
    if not isinstance(context, RequestContext):
        # isinstance, not `is None`: a wrong-typed value under the key is as unusable as an absent
        # one and must fail closed too, rather than reach a handler as a duck-typed stand-in.
        raise AuthenticationError("No identity context on this request: it ran outside the barrier")
    return context


def get_linked_identity(request: Request) -> LinkedIdentity:
    """The resolved user and identity row. Raises when absent, and when the variant is pre-auth."""
    identity = get_request_context(request).identity
    if not isinstance(identity, LinkedIdentity):
        # Reaching here means a route's registry declaration and its handler disagree: the barrier
        # admits a pre-auth principal only where `preauth_callable` is declared, so a pre-auth
        # variant arriving at a linked-only handler is a wiring bug, not a caller condition. The
        # caller-facing `preauth_identity_not_allowed` rejection is the barrier's to emit
        # (§1.5 step 5); this seam's only job is refusing to hand over the wrong variant.
        raise AuthenticationError("Identity context is pre-auth on a route requiring a linked identity")
    return identity


def get_preauth_identity(request: Request) -> PreAuthIdentity:
    """The verified (issuer, subject) of an unlinked caller. Raises when absent, and when linked."""
    identity = get_request_context(request).identity
    if not isinstance(identity, PreAuthIdentity):
        raise AuthenticationError("Identity context is linked on a route expecting a pre-auth identity")
    return identity


# ---------------------------------------------------------------------------
# Deleted here (D-16), together with the chat-route rewiring that was their last caller:
#
#   get_current_user       -- read the credential through FastAPI's `Header(None)` alias, which
#                             returns a single folded value and cannot see a duplicate
#                             `Authorization` field. That is the exact desync §1.1 exists to
#                             reject, so this was a second acceptance path beside the barrier's.
#                             It also provisioned `core.users` rows just in time; in v2.0 only
#                             `POST /auth/create-user` (Phase 37) creates an account.
#   require_quota          -- backend quota enforcement is Phase 36 REBIND-05, and the named
#                             `quota_checked_request` admission entry §8.4 described is void
#                             because D-05 deleted backend rate limiting from the product.
#   get_subscription_service -- read `app.state.apple_verifier`, which the lifespan no longer sets.
# ---------------------------------------------------------------------------
