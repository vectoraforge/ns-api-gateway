"""Store-subscription restore: one client-presented proof, one transaction, one commit.
Lock order: grant rows ascending by id, then their usage rows; the subscription row is never locked."""
from datetime import datetime
from uuid import UUID, uuid7

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.app_store import AppStoreNotifications
from nativespeaker.api.auth.google_play import PlaySubscriptionSource
from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.crud.subscriptions import (
    ENTITLED_STATUSES,
    SubscriptionsDB,
    WriteOutcome,
)
from nativespeaker.api.errors import (
    InternalError,
    RestoreAttributionMismatch,
    RestoreProviderUnknown,
    RestoreSubscriptionNotEntitled,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus

logger = structlog.get_logger()


class RestoreService:

    def __init__(self, db: AsyncSession, evaluated_at: datetime,
                 app_store: AppStoreNotifications, play: PlaySubscriptionSource,
                 package_name: str) -> None:
        self.session = db
        self.subscriptions_db = SubscriptionsDB(db)
        self.purchases_db = PurchasesDB(db)
        self.app_store = app_store
        self.play = play
        # The Play read travels the application name in its URL; the Apple check needs none.
        self.package_name = package_name
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at

    async def restore(self, identity: Identity, provider: PurchaseProvider,
                      restore_proof: str) -> None:
        """Verify the store proof and attach the entitlement the subscription it names carries."""
        proof = await self._verify(provider, restore_proof)
        destination = identity.user.id

        # Plain reads, never locks: a subscription-row lock would sit ahead of the grant locks below.
        stored = await self.subscriptions_db.read_subscription(proof.provider, proof.external_id)
        recorded = await self.subscriptions_db.read_purchase(proof.provider, proof.external_id)

        # D-06: a row that exists decides with its own status, because canonical state is the
        # webhooks'; where none exists the proof's own status decides instead.
        status = proof.status if stored is None else stored.status
        if status not in ENTITLED_STATUSES:
            raise RestoreSubscriptionNotEntitled

        token = proof.attribution_token
        # The nullable resolve, never the completeness-checking read: no row here is ordinary.
        attributed = (None if token is None
                      else await self.purchases_db.resolve_user(proof.provider, token))
        if attributed is not None and attributed != destination:
            # The store recorded this purchase against another account, so the proof is not theirs.
            raise RestoreAttributionMismatch

        owner_read = None if stored is None else stored.user_id
        month_read = None if stored is None else stored.last_cross_account_transfer_month
        if owner_read is not None and owner_read != destination:
            # 45-04 replaces this arm with the move, which is capped at one per UTC month.
            raise RestoreSubscriptionNotEntitled

        if stored is None:
            # Adoption-with-creation: written unowned, so the one owner write is the update below.
            stored, outcome = await self.subscriptions_db.upsert_subscription(
                provider=proof.provider,
                external_id=proof.external_id,
                user_id=None,
                tier_id=proof.tier_id,
                status=proof.status,
                # A client-presented proof carries no store clock; an absent date clears nothing.
                signed_at=None,
                evaluated_at=self.evaluated_at)
            await self._settle(outcome, proof)
        subscription_id = stored.id
        tier_id = stored.tier_id

        # One statement for the accounts this restore touches; 45-04 adds the current owner to it.
        marked_active = await self.subscriptions_db.lock_grants_of([destination])

        if owner_read != destination:
            # Adoption alone runs it: a same-account restore changes no owner, and a no-op update
            # would make "zero rows means a lost race" untrue for that branch.
            claimed = await self.subscriptions_db.claim_subscription_owner(
                subscription_id=subscription_id,
                owner_read=owner_read,
                month_read=month_read,
                destination=destination,
                # The move alone writes a month, and 45-04 is its only caller.
                transfer_month=None,
                evaluated_at=self.evaluated_at)
            if not claimed:
                return await self._answer_as_the_winner_left_it(proof, destination)

        if recorded is None:
            # Inserted after the subscription flushed: `core.store_purchases` keys a foreign key on the pair.
            await self._settle(await self.subscriptions_db.insert_purchase(
                provider=proof.provider,
                # A generated value only when the store gave none: the column is NOT NULL.
                identity_value=str(uuid7()) if token is None else token,
                external_id=proof.external_id,
                # A signed transaction names no per-term id here, and a purchase token is not one.
                store_transaction_id=None,
                store_original_transaction_id=proof.external_id,
                purchase_user_id=attributed,
                # Set only when the token resolved: the second foreign key needs a binding to point at.
                resolved_token_value=None if attributed is None else token,
                evaluated_at=self.evaluated_at), proof)

        # The webhook's own writer, called unchanged, so both paths mint one term the same way.
        outcome = await self.subscriptions_db.write_subscription_grant(
            user_id=destination,
            subscription_id=subscription_id,
            status=status,
            marked_active=marked_active,
            tier_id=tier_id,
            # The captured instant stands in where the store gave no purchase date for this term.
            starts_at=(self.evaluated_at if proof.purchased_at is None
                       else proof.purchased_at),
            # During grace the term is Apple's grace window, because the paid term has lapsed.
            ends_at=(proof.grace_period_expires_at
                     if status is SubscriptionStatus.grace_period else proof.expires_at),
            evaluated_at=self.evaluated_at)
        await self._settle(outcome, proof)

        # Deliberate commit: the caller reads the sync body, so 200 must mean the rows are durable.
        await self.session.commit()

    async def _answer_as_the_winner_left_it(self, proof: RestoredSubscription,
                                            destination: UUID) -> None:
        """Zero rows means another attempt won: answer as the state that attempt left behind earns."""
        # This transaction wrote nothing the winner did not overwrite, and the read below needs a fresh one.
        await self.session.rollback()
        # Re-read rather than the loaded object: the update above refreshes no attribute in memory.
        settled = await self.subscriptions_db.read_subscription(proof.provider, proof.external_id)
        if settled is not None and settled.user_id == destination:
            # The winner was another attempt of this same account, so its rows are there to read.
            return
        # Every other state the winner could have left is one this account may not restore from.
        raise RestoreSubscriptionNotEntitled

    async def _verify(self, provider: PurchaseProvider,
                      restore_proof: str) -> RestoredSubscription:
        """Run the one proof check this store answers to, before any statement opens a transaction."""
        # Each member is named: both stores report the same value type, so nothing below this
        # method forks on the provider again.
        if provider is PurchaseProvider.apple:
            # Verified locally against the vendored root, never live (D-04).
            return self.app_store.verify_transaction(restore_proof, self.evaluated_at)
        if provider is PurchaseProvider.google_play:
            # The purchase token is the proof, and the one live read is both checks (D-05).
            return await self.play.read_for_restore(package_name=self.package_name,
                                                    purchase_token=restore_proof)
        # Unreachable: the route refuses a store name outside the enum before the service runs.
        raise RestoreProviderUnknown

    async def _settle(self, outcome: WriteOutcome, proof: RestoredSubscription) -> None:
        """Answer for what the writer did: a lost race is a 5xx whose retry then finds the rows."""
        if outcome is not WriteOutcome.lost_race:
            return
        # The writer's transaction is unusable, and the winner's rows are what a retry will read.
        await self.session.rollback()
        # Labels come from a closed set only: the store's own name, never a proof value.
        logger.warning("restore_grant_race_lost", provider=str(proof.provider))
        # The generic 500, not a leaf of its own: the client is told nothing and may try again.
        raise InternalError
