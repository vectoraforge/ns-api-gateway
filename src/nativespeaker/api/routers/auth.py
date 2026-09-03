"""The six auth routes: `/auth/challenge` issues a challenge, `/auth/create-user`,
`/auth/upgrade-anonymous`, `/auth/claim-anonymous-grant` and `/auth/claim-registered-grant` spend
one, and `/auth/sync` reports what the caller's account entitles it to."""
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
from nativespeaker.api.errors import InvalidRequest, PreAuthIdentityNotAllowed
from nativespeaker.api.schemas.auth import (
    ChallengeRequest,
    CompletionRequest,
    CompletionResponse,
    GrantClaimRequest,
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

    if body.operation not in AuthOperation:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest

    # Create-user is the only operation an account-less caller may prepare, because it is the only route it reaches.
    if body.operation != AuthOperation.create_user and identity.identity is None:
        raise PreAuthIdentityNotAllowed

    challenge_id, expires_at = await challenge_store.issue(session,
                                                           operation=AuthOperation(body.operation),
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
async def create_user(body: CompletionRequest,
                      identity: Identity = Depends(get_identity),
                      service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete(identity=identity, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)


# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/upgrade-anonymous",
             response_model=CompletionResponse,
             summary="Record the caller's identity row as registered with its real provider",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and records the provider the "
                         "Firebase read reports onto the caller's existing identity row.")
async def upgrade_anonymous(body: CompletionRequest,
                            identity: Identity = Depends(get_linked_identity),
                            service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete_upgrade(identity=identity, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)


# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/claim-anonymous-grant",
             response_model=SyncResponse,
             summary="Claim the caller's one anonymous device grant",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, verifies the device through "
                         "Apple DeviceCheck and activates the grant.")
async def claim_anonymous_grant(body: GrantClaimRequest,
                                response: Response,
                                identity: Identity = Depends(get_linked_identity),
                                service: AuthService = Depends(get_auth_service),
                                sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Complete the operation the body's handle stands for, and report the entitlement it left."""
    # Forwarded untouched and never logged: the handle and the device token are secrets.
    await service.complete_claim_anonymous_grant(identity=identity,
                                                 challenge_id=body.challenge_id,
                                                 device_token=body.device_token)
    # Read after the completion committed, so the claim, the repeat and the race loser share one shape.
    entitlement = await sync_service.read_entitlement(identity.user.id)
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)


# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/claim-registered-grant",
             response_model=SyncResponse,
             summary="Claim the caller's one registered account grant",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and activates the grant, "
                         "converting an anonymous device grant the caller already holds.")
async def claim_registered_grant(body: GrantClaimRequest,
                                 response: Response,
                                 identity: Identity = Depends(get_linked_identity),
                                 service: AuthService = Depends(get_auth_service),
                                 sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Complete the operation the body's handle stands for, and report the entitlement it left."""
    # Forwarded untouched and never logged: the handle and the device token are secrets.
    await service.complete_claim_registered_grant(identity=identity,
                                                  challenge_id=body.challenge_id,
                                                  device_token=body.device_token)
    # Read after the completion committed, so the claim, the repeat and the race loser share one shape.
    entitlement = await sync_service.read_entitlement(identity.user.id)
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)


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
