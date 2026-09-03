"""The three completions: the rejection precedence, the claim, the post-claim work and the spend."""
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import partial
from typing import NoReturn
from uuid import UUID

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.auth.devicecheck import read_bits_with_retry, write_bits_with_retry
from nativespeaker.api.auth.firebase import lookup_with_retry
from nativespeaker.api.crud import ChallengesDB, GrantsDB, IdentitiesDB
from nativespeaker.api.errors import (
    ActiveGrantOutsideItsTerm,
    AppError,
    BlockedUser,
    ChallengeConsumed,
    ChallengeExpired,
    ChallengeNotFound,
    ChallengeOperationMismatch,
    ClaimantNotAnonymous,
    ClaimantNotRegistered,
    DeviceGrantExhausted,
    FreeGrantAlreadyConsumed,
    HistoricalIdentity,
    IdentityAlreadyLinked,
    IdentityUnresolvable,
    NotLinked,
    OtherActiveGrantHeld,
    ProviderTransitionNotAllowed,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.auth import AuthOperation
from nativespeaker.api.tables.grants import AccessGrantSource
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState

logger = structlog.get_logger()

# The write seam of the shared sequence: it returns the provider the transaction settled on.
Write = Callable[[Identity, VerifiedProviderIdentity], Awaitable[IdentityProvider]]

# The post-claim seam of the shared sequence: whatever it returns is what the completion returns.
type PostClaim[T] = Callable[[Identity], Awaitable[T]]

# The seeded `core.access_tiers` row an anonymous device grant points at.
ANONYMOUS_TIER_ID = "anonymous"

# The seeded `core.access_tiers` row a registered account grant points at.
REGISTERED_TIER_ID = "registered"


class AuthService:

    def __init__(self,
                 db: AsyncSession,
                 challenge_store: ChallengesDB,
                 adapter,
                 evaluated_at: datetime,
                 devicecheck=None) -> None:
        self.session = db
        self.identities_db = IdentitiesDB(db)
        self.grants_db = GrantsDB(db)
        self.challenge_store = challenge_store
        self.adapter = adapter
        # Named for the vendor API, never for the company: two unrelated enums are already called apple.
        self.devicecheck = devicecheck
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at

    async def complete(self, *, identity: Identity, challenge_id: str) -> IdentityProvider:
        """Create the account the handle stands for, and return the provider it was created with."""
        return await self._complete(identity=identity,
                                    challenge_id=challenge_id,
                                    operation=AuthOperation.create_user,
                                    post_claim=partial(self._read_then_write,
                                                       write=self._apply_create_user))

    async def complete_upgrade(self, *, identity: Identity, challenge_id: str) -> IdentityProvider:
        """Record the caller's identity row as registered, and return the provider it now carries."""
        return await self._complete(identity=identity,
                                    challenge_id=challenge_id,
                                    operation=AuthOperation.upgrade_anonymous_to_registered,
                                    post_claim=partial(self._read_then_write,
                                                       write=self._apply_upgrade))

    async def complete_claim_anonymous_grant(self, *,
                                             identity: Identity,
                                             challenge_id: str,
                                             device_token: str) -> None:
        """Claim the caller's one anonymous device grant; the entitlement is read back after commit."""
        await self._complete(identity=identity,
                             challenge_id=challenge_id,
                             operation=AuthOperation.claim_anonymous_grant,
                             post_claim=partial(self._claim_anonymous_grant,
                                                device_token=device_token))

    async def complete_claim_registered_grant(self, *,
                                              identity: Identity,
                                              challenge_id: str,
                                              device_token: str) -> None:
        """Claim the caller's one registered account grant; the entitlement is read back after commit."""
        await self._complete(identity=identity,
                             challenge_id=challenge_id,
                             operation=AuthOperation.claim_registered_grant,
                             post_claim=partial(self._claim_registered_grant,
                                                device_token=device_token))

    async def _complete[T](self, *,
                           identity: Identity,
                           challenge_id: str,
                           operation: AuthOperation,
                           post_claim: PostClaim[T]) -> T:
        """The one completion sequence every route runs: locate, claim, commit, post-claim work, spend.
        The order of the rejections below is the precedence, and none of them carries a field."""
        # No rejection before the claim consumes anything, so a wrong presenter cannot burn a live challenge.
        located = await self.challenge_store.locate(self.session, challenge_id)
        if located is None:
            # A definitive no-row. A lookup outage raises out of `locate` instead of answering "no such challenge".
            raise ChallengeNotFound()

        # Every line below reads `challenge`, which only the binding check produces: deleting it is a NameError.
        challenge = self.challenge_store.verify_binding(located, identity)
        if challenge.operation is not operation:
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
            settled = await post_claim(identity)
        except AppError:
            # A conflicting write leaves the transaction unusable, and the spend below needs it back.
            await self.session.rollback()
            await self._consume_quietly(challenge_id=challenge_id,
                                        challenge_row_id=challenge_row_id)
            raise

        await self._consume_and_commit(challenge_id=challenge_id,
                                       challenge_row_id=challenge_row_id)
        return settled

    async def _read_then_write(self, identity: Identity, *, write: Write) -> IdentityProvider:
        """The Firebase routes' post-claim work: the retry-wrapped read, then the write it settles."""
        facts = await lookup_with_retry(self.adapter, identity.issuer, identity.subject)
        # The provider the transaction settled on, which a divergence makes different from the read's.
        return await write(identity, facts)

    async def _claim_anonymous_grant(self, identity: Identity, *, device_token: str) -> None:
        """Refuse, or verify the device with Apple and activate the grant inside one transaction."""
        # D-08: the stored provider column is the sole classifier, and it is tested positively.
        if identity.identity.provider is not IdentityProvider.anonymous:
            raise ClaimantNotAnonymous

        held = await self.grants_db.read_effective_grants(identity.user.id, self.evaluated_at)
        if any(grant.source is AccessGrantSource.anonymous_device_grant for grant in held):
            # The repeat: nothing is written, Apple is never reached, and the entitlement is read after commit.
            return
        # D-03: an ineligible account never costs an Apple round trip, and both arms decide before Apple.
        consumed = identity.identity.free_grant_consumed_at is not None
        if consumed or await self.grants_db.has_prior_free_grant(identity.user.id):
            # Read at any status, as the lifetime index is: revocation and expiry never reopen the slot.
            raise FreeGrantAlreadyConsumed
        if held:
            raise OtherActiveGrantHeld
        # The one-active index's own question, asked on the mark alone; no source-keyed read is added
        # here because `has_prior_free_grant` above already covers both free sources at any status.
        if await self.grants_db.read_active_grants(identity.user.id):
            raise ActiveGrantOutsideItsTerm

        # One token for both calls: the bit the read decided on is the bit the write then sets.
        state = await read_bits_with_retry(self.devicecheck, device_token)
        if state.bit0:
            raise DeviceGrantExhausted(stage="devicecheck_read", cause="already_set")

        # bit1 is carried forward, never fabricated: Apple writes both bits in this one call.
        await write_bits_with_retry(self.devicecheck, device_token, bit0=True, bit1=state.bit1)

        activated = await self.grants_db.activate_anonymous_device_grant(
            user_id=identity.user.id,
            identity_row=identity.identity,
            tier_id=ANONYMOUS_TIER_ID,
            evaluated_at=self.evaluated_at)
        if not activated:
            # The unique indexes are the arbiter, and the loser answers exactly as the repeat does.
            await self.session.rollback()

    async def _claim_registered_grant(self, identity: Identity, *, device_token: str) -> None:
        """Refuse, or convert the caller's anonymous grant, or verify the device and activate a new one."""
        # D-05: the stored provider column is the sole classifier, and it is tested positively.
        if identity.identity.provider not in (IdentityProvider.google, IdentityProvider.apple):
            raise ClaimantNotRegistered

        held = await self.grants_db.read_effective_grants(identity.user.id, self.evaluated_at)
        sources = [grant.source for grant in held]
        if AccessGrantSource.registered_account_grant in sources:
            # The repeat: nothing is written, Apple is never reached, and the entitlement is read after commit.
            return
        if any(source is not AccessGrantSource.anonymous_device_grant for source in sources):
            raise OtherActiveGrantHeld
        # D-09(e) on both destinations: the lifetime index keys on source and carries no status.
        if await self.grants_db.holds_grant_of_source(
                identity.user.id, AccessGrantSource.registered_account_grant):
            raise FreeGrantAlreadyConsumed
        # A row the one-active index sees and this window cannot; the insert below would be refused.
        marked = await self.grants_db.read_active_grants(identity.user.id)
        if [grant for grant in marked if grant.id not in {row.id for row in held}]:
            raise ActiveGrantOutsideItsTerm

        if not held:
            # History by source and status: `free_grant_consumed_at` is already set on the conversion path.
            if await self.grants_db.has_prior_free_grant(identity.user.id):
                raise FreeGrantAlreadyConsumed

            # One token for both calls: the bit the read decided on is the bit the write then sets.
            state = await read_bits_with_retry(self.devicecheck, device_token)
            if state.bit1:
                raise DeviceGrantExhausted(stage="devicecheck_read", cause="already_set")

            # bit0 is carried forward, never fabricated: Apple writes both bits in this one call.
            await write_bits_with_retry(self.devicecheck, device_token, bit0=state.bit0, bit1=True)

        activated = await self.grants_db.activate_registered_account_grant(
            user_id=identity.user.id,
            identity_row=identity.identity,
            tier_id=REGISTERED_TIER_ID,
            evaluated_at=self.evaluated_at)
        if not activated:
            # The unique indexes are the arbiter, and the loser answers exactly as the repeat does.
            await self.session.rollback()

    async def _apply_create_user(self, identity: Identity,
                                 facts: VerifiedProviderIdentity) -> IdentityProvider:
        """Create the account, and return the provider its new identity row carries."""
        await self.create_user(identity=identity,
                               provider=facts.provider,
                               provider_uid=facts.provider_uid,
                               # The copy rule was evaluated once, inside the read; nothing re-derives it.
                               email=facts.email)
        return facts.provider

    async def _apply_upgrade(self, identity: Identity,
                             facts: VerifiedProviderIdentity) -> IdentityProvider:
        """Re-check the locked rows' provider, and return the provider the flip settled on."""
        # Provider only: `identity_state` and `user.active` are read at admission and not again,
        # so a retire or block inside the challenge-commit window still upgrades (window 12).
        located = await self.identities_db.lock_identity_and_user(issuer=identity.issuer,
                                                                   subject=identity.subject)
        if located is None:
            # The barrier resolved both rows and neither is ever deleted, so no row is broken state.
            raise IdentityUnresolvable
        identity_row, user = located
        stored = identity_row.provider

        # First, because a stored-anonymous row and a live anonymous read agree on both values below.
        if stored is IdentityProvider.anonymous and facts.provider is IdentityProvider.anonymous:
            raise NotLinked(stage="upgrade_confirmation", cause="empty")

        if stored is facts.provider and identity_row.provider_uid == facts.provider_uid:
            # D-04: the repeat that changed nothing answers as the flip did, and writes nothing at all.
            return stored

        if stored is not IdentityProvider.anonymous:
            # A registered row whose live read disagrees is drift: refused here, never rewritten.
            raise ProviderTransitionNotAllowed(identity_row_id=identity_row.id,
                                               stored_provider=stored,
                                               live_provider=facts.provider)

        return await self.identities_db.flip_provider(evaluated_at=self.evaluated_at,
                                                      identity_row=identity_row,
                                                      user=user,
                                                      provider=facts.provider,
                                                      provider_uid=facts.provider_uid,
                                                      email=facts.email)

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

    async def _consume_quietly(self, *,
                               challenge_id: str,
                               challenge_row_id: str) -> None:
        """Spend the handle without raising, so the rejection already in flight stays the client's answer."""
        try:
            await self._consume_and_commit(challenge_id=challenge_id,
                                           challenge_row_id=challenge_row_id)
        except Exception as failure:
            # The handle stays claimed and so stays unusable; the client keeps the status it earned.
            logger.error("challenge_consume_failed", challenge_row_id=challenge_row_id,
                         failure=type(failure).__name__)

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
