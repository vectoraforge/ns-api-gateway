"""The two auth routes: `/auth/challenge` issues a challenge, and `/auth/create-user` spends one."""
import structlog
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse, Response

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_request_context,
)
from nativespeaker.api.auth.adapters import ProviderDataOutcome
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import CLIENT_CLASS_FOR_RESULT, create_account
from nativespeaker.api.auth.firebase import (
    LOOKUP_UNAVAILABLE_ERROR_CLASS,
    LOOKUP_UNAVAILABLE_RESULT,
    classify_provider_data,
    email_to_persist,
    lookup_with_retry,
)
from nativespeaker.api.errors import (
    AUTH_REQUIRED,
    CHALLENGE_REQUIRED,
    INVALID_REQUEST,
    OPERATION_NOT_ALLOWED,
    ErrorClass,
    error_response,
)
from nativespeaker.api.models.auth import (
    AuthChallenge,
    AuthEventResult,
    AuthOperation,
    ChallengeRequest,
    CompletionResponse,
    CreateUserRequest,
    PrepareResponse,
)
from nativespeaker.api.models.identities import IdentityProvider

logger = structlog.get_logger()

# Auth is default-on. The context is not narrowed to pre-auth: an already-linked caller is a 409 here, not a 401.
router = APIRouter(tags=["auth"], dependencies=[Depends(get_request_context)])


@router.post("/auth/challenge",
             summary="Issue a single-use challenge for a challenge-bearing operation")
async def issue_challenge(body: ChallengeRequest,
                          context: RequestContext = Depends(get_request_context),
                          session: AsyncSession = Depends(get_db),
                          challenge_store: ChallengeStore = Depends(get_challenge_store)) -> Response:
    """Issue one challenge for an operation this route serves. It reads no provider and mutates no account."""
    if body.operation != AuthOperation.create_user.value:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable",
                       route=context.route,
                       operation=body.operation)
        return error_response(INVALID_REQUEST)

    challenge_id, expires_at = await challenge_store.issue(session,
                                                           operation=AuthOperation.create_user,
                                                           identity=context.identity,
                                                           now=context.evaluated_at)
    # `no-store` rather than `no-cache`: the handle is a secret, and a revalidatable copy is a copy.
    return JSONResponse(content=PrepareResponse(challenge_id=challenge_id, expires_at=expires_at)
                        .model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})


@router.post("/auth/create-user",
             summary="Create the account for a verified but unlinked identity",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and creates the account.")
async def create_user(body: CreateUserRequest,
                      context: RequestContext = Depends(get_request_context),
                      session: AsyncSession = Depends(get_db),
                      challenge_store: ChallengeStore = Depends(get_challenge_store),
                      adapter=Depends(get_firebase_adapter)) -> Response:
    """Complete the operation the body's handle stands for. The framework owns every malformed-body rejection."""
    # Forwarded untouched and never logged. Byte-for-byte comparison makes a padded handle a not-found.
    return await _complete(session, context=context, identity=context.identity,
                           challenge_id=body.challenge_id,
                           challenge_store=challenge_store,
                           adapter=adapter)


async def _complete(session: AsyncSession, *,
                    context: RequestContext,
                    identity: LinkedIdentity | PreAuthIdentity,
                    challenge_id: str,
                    challenge_store: ChallengeStore,
                    adapter) -> Response:
    """Create the account. The order of the rejections below is the rejection precedence."""
    # No rejection before the claim consumes anything, so a wrong presenter cannot burn a live challenge.
    challenge = await challenge_store.locate(session, challenge_id)
    if challenge is None:
        # A definitive no-row. A lookup outage raises out of `locate` instead of answering "no such challenge".
        return await _challenge_rejected(session, result=AuthEventResult.challenge_not_found)

    # `ChallengeRejection` values are `AuthEventResult` values; the keyed comparison stays inside the store.
    rejection = challenge_store.verify_binding(challenge, identity)
    if rejection is not None:
        return await _challenge_rejected(session, result=AuthEventResult(rejection.value))
    if challenge.operation is not AuthOperation.create_user:
        # A challenge issued for another operation is a pre-claim rejection, like the binding mismatch above.
        return await _challenge_rejected(
            session, result=AuthEventResult.challenge_operation_mismatch)

    if not await challenge_store.claim(session,
                                       challenge_id=challenge_id,
                                       claim_attempt_id=context.attempt_id,
                                       now=context.evaluated_at):
        # `claimed_at` distinguishes the two losses; the claim's WHERE is the only expiry evaluation anywhere.
        await session.refresh(challenge)
        lost = (AuthEventResult.challenge_expired if challenge.claimed_at is None
                else AuthEventResult.challenge_consumed)
        return await _challenge_rejected(session, result=lost)

    # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
    await session.commit()

    # Per-minute traffic limits live in the gateway, not here; only the retry budget below is enforced in-process.
    provider_data = await lookup_with_retry(adapter, identity.issuer, identity.subject)

    if provider_data.outcome is not ProviderDataOutcome.ok:
        return await _consuming_rejection(session, context=context,
                                          challenge=challenge,
                                          stage="provider_lookup",
                                          challenge_store=challenge_store,
                                          **_LOOKUP_REJECTIONS[provider_data.outcome])

    classified = classify_provider_data(provider_data.entries)
    if classified is None:
        return await _consuming_rejection(session, context=context,
                                          challenge=challenge,
                                          result=AuthEventResult.provider_not_linked,
                                          error_class=OPERATION_NOT_ALLOWED,
                                          stage="provider_classification",
                                          # The bounded reason it did not classify: no entries at all, or a bad shape.
                                          cause="empty" if not provider_data.entries else "invalid-shape",
                                          challenge_store=challenge_store)
    provider, provider_uid = classified
    # The one place the copy rule is evaluated; `create_account` takes a plain `email` and re-derives nothing.
    email = email_to_persist(provider_data)

    result = await create_account(session,
                                  context=context,
                                  identity=identity,
                                  challenge=challenge,
                                  provider=provider,
                                  provider_uid=provider_uid,
                                  email=email,
                                  challenge_store=challenge_store)

    return _completion_response(result, provider)


async def _challenge_rejected(session: AsyncSession, *, result: AuthEventResult) -> Response:
    """Answer every challenge rejection with one class, so completion is not a challenge-enumeration oracle."""
    # The specific result goes to the log only; the public handle is never logged.
    logger.warning("create_user_challenge_rejected", stage=str(result))
    await session.rollback()
    return error_response(CHALLENGE_REQUIRED)


# `user_not_found` is definitive; the unavailable pair is retryable, and collapsing them misleads the client.
_LOOKUP_REJECTIONS: dict[ProviderDataOutcome, dict[str, object]] = {
    ProviderDataOutcome.user_not_found: {
        "result": AuthEventResult.firebase_user_unresolved,
        "error_class": AUTH_REQUIRED,
    },
    ProviderDataOutcome.retryable_failure: {
        "result": LOOKUP_UNAVAILABLE_RESULT,
        "error_class": LOOKUP_UNAVAILABLE_ERROR_CLASS,
    },
    ProviderDataOutcome.selection_failure: {
        "result": LOOKUP_UNAVAILABLE_RESULT,
        "error_class": LOOKUP_UNAVAILABLE_ERROR_CLASS,
    },
}


async def _consuming_rejection(session: AsyncSession, *,
                               context: RequestContext,
                               challenge: AuthChallenge,
                               result: AuthEventResult,
                               error_class: ErrorClass,
                               stage: str,
                               challenge_store: ChallengeStore,
                               cause: str | None = None) -> Response:
    """Reject after the provider read, consuming the challenge so the handle cannot be re-presented."""
    bounded = {} if cause is None else {"cause": cause}
    logger.warning("create_user_lookup_rejected", stage=stage, result=str(result), **bounded)
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge.challenge_id,
                                             claim_attempt_id=context.attempt_id,
                                             now=context.evaluated_at)
    if not consumed:
        # Not recoverable: this attempt holds the claim, so a `False` means stored state diverged.
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await session.commit()
    return error_response(error_class)


def _completion_response(result: AuthEventResult, provider: IdentityProvider) -> Response:
    """Map the internal result onto the client's answer. The internal result is never client-visible."""
    if result is not AuthEventResult.succeeded:
        logger.warning("create_user_transaction_rejected", result=str(result))
        return error_response(CLIENT_CLASS_FOR_RESULT[result])
    return JSONResponse(content=CompletionResponse(identity_provider=provider)
                        .model_dump(mode="json"))
