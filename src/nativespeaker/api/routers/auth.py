"""The eight auth routes: `/auth/challenge` issues a challenge, `/auth/create-user`, `/auth/upgrade-anonymous`
and the two `/auth/claim-*-grant` routes spend one, `/auth/restore-subscription` attaches a paid store
subscription, `/auth/sync` reports entitlement, and `/auth/sign-out-all` revokes the refresh tokens."""
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse, Response

from nativespeaker.api.app.dependencies import (
    get_auth_service,
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_identity,
    get_linked_identity,
    get_restore_service,
    get_sync_service,
)
from nativespeaker.api.auth.firebase import revoke_with_retry
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import (
    InvalidRequest,
    PreAuthIdentityNotAllowed,
    RestoreProviderUnknown,
)
from nativespeaker.api.schemas.auth import (
    ChallengeRequest,
    CompletionRequest,
    CompletionResponse,
    GrantClaimRequest,
    Identity,
    PrepareResponse,
    RestoreRequest,
    SyncResponse,
)
from nativespeaker.api.services import AuthService, RestoreService, SyncService
from nativespeaker.api.tables.auth import AuthOperation
from nativespeaker.api.tables.purchases import PurchaseProvider

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
@router.post("/auth/restore-subscription",
             response_model=SyncResponse,
             summary="Attach a verified paid store subscription to the caller's account",
             description="Verifies the store artifact supplied as `restore_proof` in the body "
                         "against the store named by `provider`, and attaches the paid "
                         "entitlement the subscription it names carries.")
async def restore_subscription(body: RestoreRequest,
                               response: Response,
                               identity: Identity = Depends(get_linked_identity),
                               service: RestoreService = Depends(get_restore_service),
                               sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Verify the store artifact and report the entitlement the caller's account now holds."""
    if body.provider not in PurchaseProvider:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a proof never is.
        logger.warning("restore_provider_not_served", provider=body.provider)
        raise RestoreProviderUnknown

    # Forwarded untouched and never logged: the store artifact is a secret.
    await service.restore(identity=identity,
                          provider=PurchaseProvider(body.provider),
                          restore_proof=body.restore_proof)
    # Read after the restore committed, so the restore and the repeat share one shape.
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


# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/sign-out-all",
             status_code=204,
             summary="Revoke every refresh token the caller's provider account holds",
             description="Signs the caller out on every device. The account cannot use its current "
                         "sessions again, and an anonymous account cannot be signed in to again.")
async def sign_out_all(identity: Identity = Depends(get_linked_identity),
                       adapter=Depends(get_firebase_adapter)) -> Response:
    """Revoke the caller's refresh tokens at the provider. It opens no session and writes no row."""
    # The request-verified pair, never the stored row: the provider is told what this request proved.
    await revoke_with_retry(adapter, identity.issuer, identity.subject)
    row = identity.identity
    # `resolve` sets the row and the user together, and `get_linked_identity` admits only a linked caller.
    assert row is not None
    # The row id alone: enough to answer "did this account sign out everywhere", and no more.
    logger.info("sign_out_all_confirmed", identity_row_id=str(row.id))
    return Response(status_code=204)
