"""The two auth routes: `/auth/challenge` issues a challenge, and `/auth/create-user` spends one."""
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse, Response

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_identity,
)
from nativespeaker.api.auth.create_user import create_user as create_account
from nativespeaker.api.auth.firebase import lookup_with_retry
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import (
    AppError,
    ChallengeConsumed,
    ChallengeExpired,
    ChallengeNotFound,
    ChallengeOperationMismatch,
    InvalidRequest,
)
from nativespeaker.api.schemas.auth import (
    ChallengeRequest,
    CompletionResponse,
    CreateUserRequest,
    Identity,
    PrepareResponse,
)
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
             summary="Create the account for a verified but unlinked identity",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and creates the account.")
async def create_user(body: CreateUserRequest,
                      identity: Identity = Depends(get_identity),
                      session: AsyncSession = Depends(get_db),
                      challenge_store: ChallengesDB = Depends(get_challenge_store),
                      adapter=Depends(get_firebase_adapter)) -> Response:
    """Complete the operation the body's handle stands for. The framework owns every malformed-body rejection."""
    # Forwarded untouched and never logged. Byte-for-byte comparison makes a padded handle a not-found.
    return await _complete(session, identity=identity,
                           # One instant for this request; nothing below it reads the clock again.
                           evaluated_at=datetime.now(UTC),
                           challenge_id=body.challenge_id,
                           challenge_store=challenge_store,
                           adapter=adapter)


async def _complete(session: AsyncSession, *,
                    identity: Identity,
                    evaluated_at: datetime,
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
    located = await challenge_store.locate(session, challenge_id)
    if located is None:
        # A definitive no-row. A lookup outage raises out of `locate` instead of answering "no such challenge".
        raise ChallengeNotFound()

    # Every line below reads `challenge`, which only the binding check produces: deleting it is a NameError.
    challenge = challenge_store.verify_binding(located, identity)
    if challenge.operation is not AuthOperation.create_user:
        # A challenge issued for another operation is a pre-claim rejection, like the binding mismatch above.
        raise ChallengeOperationMismatch()

    if not await challenge_store.claim(session,
                                       challenge_id=challenge_id,
                                       now=evaluated_at):
        # `claimed_at` distinguishes the two losses; the claim's WHERE is the only expiry evaluation anywhere.
        await session.refresh(challenge)
        if challenge.claimed_at is None:
            raise ChallengeExpired()
        else:
            raise ChallengeConsumed()

    # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
    await session.commit()

    # Read off a just-committed instance, which the lifespan's `expire_on_commit=False` keeps loaded.
    challenge_row_id = str(challenge.id)

    try:
        # Per-minute traffic limits live in the gateway, not here; only the retry budget is in-process.
        facts = await lookup_with_retry(adapter, identity.issuer, identity.subject)
        await create_account(session,
                             identity=identity,
                             evaluated_at=evaluated_at,
                             provider=facts.provider,
                             provider_uid=facts.provider_uid,
                             # The copy rule was evaluated once, inside the read; nothing re-derives it.
                             email=facts.email)
    except AppError:
        # A conflicting insert leaves the transaction unusable, and the spend below needs it back.
        await session.rollback()
        try:
            await _consume_and_commit(session, challenge_id=challenge_id,
                                      challenge_row_id=challenge_row_id,
                                      challenge_store=challenge_store,
                                      evaluated_at=evaluated_at)
        except Exception as failure:
            # The handle stays claimed and so stays unusable; the client keeps the status it earned.
            logger.error("challenge_consume_failed", challenge_row_id=challenge_row_id,
                         failure=type(failure).__name__)
        raise

    await _consume_and_commit(session, challenge_id=challenge_id,
                              challenge_row_id=challenge_row_id,
                              challenge_store=challenge_store,
                              evaluated_at=evaluated_at)
    return JSONResponse(content=CompletionResponse(identity_provider=facts.provider)
                        .model_dump(mode="json"))


async def _consume_and_commit(session: AsyncSession, *,
                              challenge_id: str,
                              challenge_row_id: str,
                              challenge_store: ChallengesDB,
                              evaluated_at: datetime) -> None:
    """Spend the handle and commit, so neither path can leave a claimed handle re-presentable."""
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge_id,
                                             now=evaluated_at)
    if not consumed:
        # Not recoverable: this attempt holds the claim, so a `False` means stored state diverged.
        logger.error("challenge_consume_did_not_match", challenge_row_id=challenge_row_id)

    await session.commit()
