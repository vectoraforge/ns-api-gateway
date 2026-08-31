"""The create-user completion: the rejection precedence, the claim, the provider read, and the spend."""
from datetime import datetime
from typing import NoReturn
from uuid import UUID

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.firebase import lookup_with_retry
from nativespeaker.api.crud import ChallengesDB, IdentitiesDB
from nativespeaker.api.errors import (
    AppError,
    BlockedUser,
    ChallengeConsumed,
    ChallengeExpired,
    ChallengeNotFound,
    ChallengeOperationMismatch,
    HistoricalIdentity,
    IdentityAlreadyLinked,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.auth import AuthOperation
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState

logger = structlog.get_logger()


class AuthService:

    def __init__(self,
                 db: AsyncSession,
                 challenge_store: ChallengesDB,
                 adapter,
                 evaluated_at: datetime) -> None:
        self.session = db
        self.identities_db = IdentitiesDB(db)
        self.challenge_store = challenge_store
        self.adapter = adapter
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at

    async def complete(self, *, identity: Identity, challenge_id: str) -> IdentityProvider:
        """Create the account and return the provider the read reported.

        The order of the rejections below is the precedence, and none of them carries a field.
        """
        # No rejection before the claim consumes anything, so a wrong presenter cannot burn a live challenge.
        located = await self.challenge_store.locate(self.session, challenge_id)
        if located is None:
            # A definitive no-row. A lookup outage raises out of `locate` instead of answering "no such challenge".
            raise ChallengeNotFound()

        # Every line below reads `challenge`, which only the binding check produces: deleting it is a NameError.
        challenge = self.challenge_store.verify_binding(located, identity)
        if challenge.operation is not AuthOperation.create_user:
            # A challenge issued for another operation is a pre-claim rejection, like the binding mismatch above.
            raise ChallengeOperationMismatch()

        if not await self.challenge_store.claim(self.session,
                                                challenge_id=challenge_id,
                                                now=self.evaluated_at):
            # `claimed_at` distinguishes the two losses; the claim's WHERE is the only expiry evaluation anywhere.
            await self.session.refresh(challenge)
            if challenge.claimed_at is None:
                raise ChallengeExpired()
            else:
                raise ChallengeConsumed()

        # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
        await self.session.commit()

        # Read off a just-committed instance, which the lifespan's `expire_on_commit=False` keeps loaded.
        challenge_row_id = str(challenge.id)

        try:
            # Per-minute traffic limits live in the gateway, not here; only the retry budget is in-process.
            facts = await lookup_with_retry(self.adapter, identity.issuer, identity.subject)
            await self.create_user(identity=identity,
                                   provider=facts.provider,
                                   provider_uid=facts.provider_uid,
                                   # The copy rule was evaluated once, inside the read; nothing re-derives it.
                                   email=facts.email)
        except AppError:
            # A conflicting insert leaves the transaction unusable, and the spend below needs it back.
            await self.session.rollback()
            try:
                await self._consume_and_commit(challenge_id=challenge_id,
                                               challenge_row_id=challenge_row_id)
            except Exception as failure:
                # The handle stays claimed and so stays unusable; the client keeps the status it earned.
                logger.error("challenge_consume_failed", challenge_row_id=challenge_row_id,
                             failure=type(failure).__name__)
            raise

        await self._consume_and_commit(challenge_id=challenge_id,
                                       challenge_row_id=challenge_row_id)
        return facts.provider

    async def create_user(self, *,
                          identity: Identity,
                          provider: IdentityProvider,
                          provider_uid: str | None,
                          email: str | None) -> UUID:
        """Return the new user's id, or raise the rejection the transaction earned."""
        existing = await self.identities_db.resolve_existing(issuer=identity.issuer,
                                                             subject=identity.subject)

        if existing is not None:
            # The prepare-time pre-check is racy, so this resolution is the one that decides.
            await self._reject_existing_identity(existing)

        return await self.identities_db.insert_account(evaluated_at=self.evaluated_at,
                                                       identity=identity,
                                                       provider=provider,
                                                       provider_uid=provider_uid,
                                                       email=email)

    async def _reject_existing_identity(self, existing: ExternalIdentity) -> NoReturn:
        """Raise what an already-present identity row earned. No mutation, and every test fails closed."""
        if existing.identity_state != IdentityState.active:
            raise HistoricalIdentity

        user = await self.identities_db.user_by_id(existing.user_id)
        if user is None or user.active is not True:
            raise BlockedUser
        raise IdentityAlreadyLinked()

    async def _consume_and_commit(self, *,
                                  challenge_id: str,
                                  challenge_row_id: str) -> None:
        """Spend the handle and commit, so neither path can leave a claimed handle re-presentable."""
        consumed = await self.challenge_store.consume(self.session,
                                                      challenge_id=challenge_id,
                                                      now=self.evaluated_at)
        if not consumed:
            # Not recoverable: this attempt holds the claim, so a `False` means stored state diverged.
            logger.error("challenge_consume_did_not_match", challenge_row_id=challenge_row_id)

        await self.session.commit()
