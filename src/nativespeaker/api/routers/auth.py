"""The eight auth routes: `/auth/challenge` issues a challenge, `/auth/create-user`, `/auth/upgrade-anonymous`
and the two `/auth/claim-*-grant` routes spend one, `/auth/restore-subscription` attaches a paid store
subscription, `/auth/sync` reports entitlement, and `/auth/sign-out-all` revokes the refresh tokens."""
import structlog
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import Response

from nativespeaker.api.app.dependencies import (
    get_auth_service,
    get_claims,
    get_db,
    get_firebase_adapter,
    get_identity,
    get_restore_service,
    get_sync_service,
)
from nativespeaker.api.auth.firebase import revoke_with_retry
from nativespeaker.api.auth.jwt_verifier import VerifiedClaims
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.crud.identities import IdentitiesDB
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
    LinkedIdentity,
    PrepareResponse,
    RestoreRequest,
    SyncResponse,
)
from nativespeaker.api.services import AuthService, RestoreService, SyncService
from nativespeaker.api.tables.auth import AuthOperation
from nativespeaker.api.tables.purchases import PurchaseProvider

logger = structlog.get_logger()

router = APIRouter(tags=["auth"], dependencies=[Depends(get_claims)])


@router.post("/auth/challenge",
             response_model=PrepareResponse,
             summary="Issue a single-use challenge for a challenge-bearing operation")
async def issue_challenge(body: ChallengeRequest,
                          response: Response,
                          claims: VerifiedClaims = Depends(get_claims),
                          session: AsyncSession = Depends(get_db)) -> PrepareResponse:
    """Issue one challenge for an operation this route serves."""
    if body.operation not in AuthOperation:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest

    # Read after the vocabulary check: a refused body issues no statement.
    linked = await IdentitiesDB(session).resolve(issuer=claims.issuer, subject=claims.subject)
    # Create-user is the only operation an account-less caller may prepare, because it is the only route it reaches.
    if body.operation != AuthOperation.create_user and linked is None:
        raise PreAuthIdentityNotAllowed

    challenge_id, expires_at = await ChallengesDB().issue(session,
                                                          operation=AuthOperation(body.operation),
                                                          claims=claims,
                                                          linked=linked)
    # `get_db` never commits. This commit makes the issued row durable before the answer.
    await session.commit()
    # `no-store` rather than `no-cache`: the handle is a secret, and a revalidatable copy is a copy.
    response.headers["Cache-Control"] = "no-store"
    return PrepareResponse(challenge_id=challenge_id, expires_at=expires_at)


@router.post("/auth/create-user",
             response_model=CompletionResponse,
             summary="Create the account for a verified but unlinked identity",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and creates the account.")
async def create_user(body: CompletionRequest,
                      claims: VerifiedClaims = Depends(get_claims),
                      service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete(claims=claims, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)


@router.post("/auth/upgrade-anonymous",
             response_model=CompletionResponse,
             summary="Record the caller's identity row as registered with its real provider",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and records the provider the "
                         "Firebase read reports onto the caller's existing identity row.")
async def upgrade_anonymous(body: CompletionRequest,
                            claims: VerifiedClaims = Depends(get_claims),
                            linked: LinkedIdentity = Depends(get_identity),
                            service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete_upgrade(claims=claims, linked=linked,
                                              challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)


@router.post("/auth/claim-anonymous-grant",
             response_model=SyncResponse,
             summary="Claim the caller's one anonymous device grant",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, verifies the device through "
                         "Apple DeviceCheck and activates the grant.")
async def claim_anonymous_grant(body: GrantClaimRequest,
                                response: Response,
                                claims: VerifiedClaims = Depends(get_claims),
                                linked: LinkedIdentity = Depends(get_identity),
                                service: AuthService = Depends(get_auth_service),
                                sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Complete the operation the body's handle stands for, and report the entitlement it left."""
    # Forwarded untouched and never logged: the handle and the device token are secrets.
    await service.complete_claim_anonymous_grant(claims=claims,
                                                 linked=linked,
                                                 challenge_id=body.challenge_id,
                                                 device_token=body.device_token)
    # Read after the completion committed, so the claim, the repeat and the race loser share one shape.
    entitlement = await sync_service.read_entitlement(linked.user.id)
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=linked.identity.provider)


@router.post("/auth/claim-registered-grant",
             response_model=SyncResponse,
             summary="Claim the caller's one registered account grant",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and activates the grant, "
                         "converting an anonymous device grant the caller already holds.")
async def claim_registered_grant(body: GrantClaimRequest,
                                 response: Response,
                                 claims: VerifiedClaims = Depends(get_claims),
                                 linked: LinkedIdentity = Depends(get_identity),
                                 service: AuthService = Depends(get_auth_service),
                                 sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Complete the operation the body's handle stands for, and report the entitlement it left."""
    # Forwarded untouched and never logged: the handle and the device token are secrets.
    await service.complete_claim_registered_grant(claims=claims,
                                                  linked=linked,
                                                  challenge_id=body.challenge_id,
                                                  device_token=body.device_token)
    # Read after the completion committed, so the claim, the repeat and the race loser share one shape.
    entitlement = await sync_service.read_entitlement(linked.user.id)
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=linked.identity.provider)


@router.post("/auth/restore-subscription",
             response_model=SyncResponse,
             summary="Attach a verified paid store subscription to the caller's account",
             description="Verifies the store artifact supplied as `restore_proof` in the body "
                         "against the store named by `provider`, and attaches the paid "
                         "entitlement the subscription it names carries.")
async def restore_subscription(body: RestoreRequest,
                               response: Response,
                               linked: LinkedIdentity = Depends(get_identity),
                               service: RestoreService = Depends(get_restore_service),
                               sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Verify the store artifact and report the entitlement the caller's account now holds."""
    if body.provider not in PurchaseProvider:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a proof never is.
        logger.warning("restore_provider_not_served", provider=body.provider)
        raise RestoreProviderUnknown

    # Forwarded untouched and never logged: the store artifact is a secret.
    await service.restore(linked=linked,
                          provider=PurchaseProvider(body.provider),
                          restore_proof=body.restore_proof)
    # Read after the restore committed, so the restore and the repeat share one shape.
    entitlement = await sync_service.read_entitlement(linked.user.id)
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=linked.identity.provider)


@router.post("/auth/sync",
             response_model=SyncResponse,
             summary="Report the caller's entitlement and registration state",
             description="Reads the caller's effective grant, the current period's usage and the "
                         "stored registration state. Nothing is written.")
async def sync(linked: LinkedIdentity = Depends(get_identity),
               service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Report what the caller's account entitles it to at this request's instant."""
    entitlement = await service.read_entitlement(linked.user.id)
    return SyncResponse(entitlement=entitlement, identity_provider=linked.identity.provider)


@router.post("/auth/sign-out-all",
             status_code=204,
             summary="Revoke every refresh token the caller's provider account holds",
             description="Revokes every refresh token the account holds, so no new session can be "
                         "minted for it. An ID token already issued stays valid until it expires "
                         "(up to one hour). An anonymous account cannot be signed in to again.")
async def sign_out_all(claims: VerifiedClaims = Depends(get_claims),
                       linked: LinkedIdentity = Depends(get_identity),
                       adapter=Depends(get_firebase_adapter)) -> Response:
    """Revoke the caller's refresh tokens at the provider."""
    # The request-verified pair, never the stored row: the provider is told what this request proved.
    await revoke_with_retry(adapter, claims.issuer, claims.subject)
    # The row id alone: enough to answer "did this account sign out everywhere", and no more.
    logger.info("sign_out_all_confirmed", identity_row_id=str(linked.identity.id))
    return Response(status_code=204)
