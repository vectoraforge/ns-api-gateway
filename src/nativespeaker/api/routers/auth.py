"""`POST /auth/create-user`: one route that dispatches on the mode signal to prepare or to completion."""
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse, Response

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_raw_query_string,
    get_request_context,
)
from nativespeaker.api.auth.adapters import ProviderDataEntry, ProviderDataOutcome
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.classifier import classify_provider_data, email_to_persist
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import (
    CLIENT_CLASS_FOR_RESULT,
    create_account,
    resolve_existing_identity,
)
from nativespeaker.api.auth.modesignal import ModeSignal, classify_mode_signal
from nativespeaker.api.auth.retry import (
    LOOKUP_UNAVAILABLE_ERROR_CLASS,
    LOOKUP_UNAVAILABLE_RESULT,
    lookup_with_retry,
)
from nativespeaker.api.errors import (
    AUTH_REQUIRED,
    CHALLENGE_REQUIRED,
    IDENTITY_ALREADY_LINKED,
    INVALID_REQUEST,
    OPERATION_NOT_ALLOWED,
    ErrorClass,
    error_response,
)
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState

logger = structlog.get_logger()

# Auth is default-on. The context is not narrowed to pre-auth: an already-linked caller is a 409 here, not a 401.
router = APIRouter(tags=["auth"], dependencies=[Depends(get_request_context)])


class CreateUserRequest(BaseModel):
    """The completion body. `challenge_id` is `Any` so every unusable handle rejects as 400 rather than 422."""
    challenge_id: Any = None


class PrepareResponse(BaseModel):
    """The prepare body: the handle and its expiry, and nothing else about the challenge is disclosed."""
    challenge_id: str
    expires_at: datetime


class CompletionResponse(BaseModel):
    """The completion body: the registration state. There is no backend session tier, so nothing is minted."""
    identity_provider: IdentityProvider


@router.post("/auth/create-user",
             summary="Create the account for a verified but unlinked identity",
             description="Prepare mode (`?challenge=true`) issues a single-use challenge; "
                         "completion mode (`challenge_id` in the body) creates the account.")
async def create_user(body: CreateUserRequest | None = None,
                      raw_query: bytes = Depends(get_raw_query_string),
                      context: RequestContext = Depends(get_request_context),
                      session: AsyncSession = Depends(get_db),
                      challenge_store: ChallengeStore = Depends(get_challenge_store),
                      adapter=Depends(get_firebase_adapter)) -> Response:
    """Classify the mode signal, then dispatch. The classification itself has no side effects."""
    body_challenge_id = None if body is None else body.challenge_id
    mode = classify_mode_signal(raw_query, body_challenge_id)
    if mode is None:
        logger.warning("auth_mode_signal_invalid",
                       route=context.route,
                       operation=str(AuthOperation.create_user),
                       # The raw handle is never logged; its shape is the whole diagnostic.
                       body_present=body is not None)
        return error_response(INVALID_REQUEST)

    identity = context.identity
    if mode is ModeSignal.prepare:
        return await _prepare(session, context=context, identity=identity,
                              challenge_store=challenge_store)

    # Forwarded untouched and never logged. Byte-for-byte comparison makes a padded handle a not-found, not a 400.
    completion_handle: str = body_challenge_id  # ty: ignore[invalid-assignment]
    return await _complete(session, context=context, identity=identity,
                           challenge_id=completion_handle,
                           challenge_store=challenge_store,
                           adapter=adapter)


async def _prepare(session: AsyncSession, *,
                   context: RequestContext,
                   identity: LinkedIdentity | PreAuthIdentity,
                   challenge_store: ChallengeStore) -> Response:
    """Reject an already-linked caller, else issue one challenge. No business state is mutated."""
    linked = await _already_linked(session, identity=identity)
    if linked is not None:
        # No rollback and no attribute read here: a rollback expires the row and the lazy load then fails.
        return error_response(IDENTITY_ALREADY_LINKED)

    challenge_id, expires_at = await challenge_store.issue(session,
                                                           operation=AuthOperation.create_user,
                                                           identity=identity,
                                                           now=context.evaluated_at)
    body = PrepareResponse(challenge_id=challenge_id, expires_at=expires_at)
    # `no-store` rather than `no-cache`: the handle is a secret, and a revalidatable copy is a copy.
    return JSONResponse(content=body.model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})


async def _already_linked(session: AsyncSession, *,
                          identity: LinkedIdentity | PreAuthIdentity) -> ExternalIdentity | None:
    """The active identity row when this caller already has an account, else `None`."""
    # Best-effort and racy: the unique constraints in the consuming transaction are the authority.
    if isinstance(identity, LinkedIdentity):
        return identity.identity
    existing = await resolve_existing_identity(session,
                                               issuer=identity.issuer, subject=identity.subject)
    if existing is not None and existing.identity_state is IdentityState.active:
        return existing
    return None


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
                                          cause=_classification_cause(provider_data.entries),
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


def _classification_cause(entries: tuple[ProviderDataEntry, ...]) -> str:
    """The bounded reason a provider account did not classify: no entries at all, or an unusable shape."""
    return "empty" if not entries else "invalid-shape"


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
