"""The three auth routes: `/auth/challenge` issues a challenge, `/auth/create-user` spends one,
and `/auth/sync` reports what the caller's account entitles it to."""
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse, Response

from nativespeaker.api.app.dependencies import (
    get_auth_service,
    get_challenge_store,
    get_db,
    get_identity,
    get_linked_identity,
    get_sync_service,
)
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import InvalidRequest
from nativespeaker.api.schemas.auth import (
    ChallengeRequest,
    CompletionResponse,
    CreateUserRequest,
    Identity,
    PrepareResponse,
    SyncResponse,
)
from nativespeaker.api.services import AuthService, SyncService
from nativespeaker.api.tables.auth import AuthOperation

logger = structlog.get_logger()

# Auth is default-on, and deliberately unnarrowed: an already-linked caller is a 409 here, not a 401.
router = APIRouter(tags=["auth"], dependencies=[Depends(get_identity)])


@router.post("/auth/challenge",
             summary="Issue a single-use challenge for a challenge-bearing operation")
async def issue_challenge(body: ChallengeRequest,
                          identity: Identity = Depends(get_identity),
                          session: AsyncSession = Depends(get_db),
                          challenge_store: ChallengesDB = Depends(get_challenge_store)) -> Response:
    """Issue one challenge for an operation this route serves. It reads no provider and mutates no account."""
    # One instant for this request, so `created_at` and `expires_at` cannot straddle a boundary.
    evaluated_at = datetime.now(UTC)

    if body.operation != AuthOperation.create_user.value:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest

    challenge_id, expires_at = await challenge_store.issue(session,
                                                           operation=AuthOperation.create_user,
                                                           identity=identity,
                                                           now=evaluated_at)
    # `no-store` rather than `no-cache`: the handle is a secret, and a revalidatable copy is a copy.
    return JSONResponse(content=PrepareResponse(challenge_id=challenge_id, expires_at=expires_at)
                        .model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})


@router.post("/auth/create-user",
             response_model=CompletionResponse,
             summary="Create the account for a verified but unlinked identity",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and creates the account.")
async def create_user(body: CreateUserRequest,
                      identity: Identity = Depends(get_identity),
                      service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete(identity=identity, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)


# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/sync",
             response_model=SyncResponse,
             summary="Report the caller's entitlement and registration state",
             description="Reads the caller's effective grant, the current period's usage and the "
                         "stored registration state. Nothing is written.")
async def sync(identity: Identity = Depends(get_linked_identity),
               service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Report what the caller's account entitles it to at this request's instant."""
    entitlement = await service.read_entitlement(identity.user.id)
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
