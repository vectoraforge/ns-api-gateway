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
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.create_user import create_user as create_account
from nativespeaker.api.auth.exceptions import (
    AuthRejected,
    ChallengeConsumed,
    ChallengeExpired,
    ChallengeNotFound,
    ChallengeOperationMismatch,
)
from nativespeaker.api.auth.firebase import lookup_with_retry
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import INVALID_REQUEST, error_response
from nativespeaker.api.tables.auth import (
    AuthChallenge,
    AuthOperation,
    ChallengeRequest,
    CompletionResponse,
    CreateUserRequest,
    PrepareResponse,
)

logger = structlog.get_logger()

# Auth is default-on. The context is not narrowed to pre-auth: an already-linked caller is a 409 here, not a 401.
router = APIRouter(tags=["auth"], dependencies=[Depends(get_request_context)])


@router.post("/auth/challenge",
             summary="Issue a single-use challenge for a challenge-bearing operation")
async def issue_challenge(body: ChallengeRequest,
                          context: RequestContext = Depends(get_request_context),
                          session: AsyncSession = Depends(get_db),
                          challenge_store: ChallengesDB = Depends(get_challenge_store)) -> Response:
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
                      challenge_store: ChallengesDB = Depends(get_challenge_store),
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
                    challenge_store: ChallengesDB,
                    adapter) -> Response:
    """Create the account. The order of the rejections below is the rejection precedence.

    Every rejection before the claim is raised, never caught here: `get_db` rolls the session back
    on the way out and the handler answers the one 409 they all share. None of them carries a field,
    because the row they were discovered on is expired by that rollback -- reading an attribute off
    it in the handler would be I/O outside a greenlet, and the client would get 500 where 409 is owed.
    """
    # No rejection before the claim consumes anything, so a wrong presenter cannot burn a live challenge.
    challenge = await challenge_store.locate(session, challenge_id)
    if challenge is None:
        # A definitive no-row. A lookup outage raises out of `locate` instead of answering "no such challenge".
        raise ChallengeNotFound()

    # A bare statement: the keyed comparison stays inside the store, and the mismatch it finds is
    # raised there rather than returned. Pre-claim, so nothing here consumes and nothing rolls back.
    challenge_store.verify_binding(challenge, identity)
    if challenge.operation is not AuthOperation.create_user:
        # A challenge issued for another operation is a pre-claim rejection, like the binding mismatch above.
        raise ChallengeOperationMismatch()

    if not await challenge_store.claim(session,
                                       challenge_id=challenge_id,
                                       claim_attempt_id=context.attempt_id,
                                       now=context.evaluated_at):
        # `claimed_at` distinguishes the two losses; the claim's WHERE is the only expiry evaluation anywhere.
        await session.refresh(challenge)
        if challenge.claimed_at is None:
            raise ChallengeExpired()
        else:
            raise ChallengeConsumed()

    # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
    await session.commit()

    try:
        # One arm covers the whole post-claim region -- the lookup, the classification now inside it,
        # and the transaction -- because the lookup's rejections are members of the same family. No
        # arm is missing here; that shared base is the payoff of consolidating them in `exceptions.py`.
        #
        # Per-minute traffic limits live in the gateway, not here; only the retry budget is in-process.
        facts = await lookup_with_retry(adapter, identity.issuer, identity.subject)
        await create_account(session,
                             context=context,
                             identity=identity,
                             challenge=challenge,
                             provider=facts.provider,
                             provider_uid=facts.provider_uid,
                             # The copy rule was evaluated once, inside the read; nothing re-derives it.
                             email=facts.email,
                             challenge_store=challenge_store)
    except AuthRejected:
        # D-04/D-11: every raising arm past the claim leaves the consume here, so the paths spend the
        # handle exactly once between them. The bare re-raise is safe because after the commit the
        # session holds no transaction, so `get_db`'s rollback-on-exception cannot un-consume it --
        # the client spent this handle and must not get it back.
        await _consume_and_commit(session, context=context, challenge=challenge,
                                  challenge_store=challenge_store)
        raise

    return JSONResponse(content=CompletionResponse(identity_provider=facts.provider)
                        .model_dump(mode="json"))


async def _consume_and_commit(session: AsyncSession, *,
                              context: RequestContext,
                              challenge: AuthChallenge,
                              challenge_store: ChallengesDB) -> None:
    """Spend the handle and commit, so a rejection after the claim cannot be re-presented."""
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge.challenge_id,
                                             claim_attempt_id=context.attempt_id,
                                             now=context.evaluated_at)
    if not consumed:
        # Not recoverable: this attempt holds the claim, so a `False` means stored state diverged.
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await session.commit()
