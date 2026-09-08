"""Store-subscription restore: one client-presented proof, one transaction, one commit.
Lock order: grant rows ascending by id, then their usage rows; the subscription row is never locked."""
from datetime import datetime

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.app_store import AppStoreNotifications
from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.crud.subscriptions import (
    ENTITLED_STATUSES,
    SubscriptionsDB,
    WriteOutcome,
)
from nativespeaker.api.errors import (
    InternalError,
    RestoreProviderUnknown,
    RestoreSubscriptionNotEntitled,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus

logger = structlog.get_logger()


class RestoreService:

    def __init__(self, db: AsyncSession, evaluated_at: datetime,
                 app_store: AppStoreNotifications, package_name: str) -> None:
        self.session = db
        self.subscriptions_db = SubscriptionsDB(db)
        self.app_store = app_store
        # Held for the Play read 45-02 adds; the Apple check needs no application name.
        self.package_name = package_name
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at

    async def restore(self, identity: Identity, provider: PurchaseProvider,
                      restore_proof: str) -> None:
        """Verify the store proof and attach the entitlement the subscription it names carries."""
        proof = self._verify(provider, restore_proof)

        # A plain read, never a lock: a subscription-row lock would sit ahead of the grant locks below.
        stored = await self.subscriptions_db.read_subscription(proof.provider, proof.external_id)
        if stored is None:
            # 45-03 replaces this arm with the adoption branch, which creates the row instead.
            raise RestoreSubscriptionNotEntitled

        status = stored.status
        if status not in ENTITLED_STATUSES:
            # D-06: the stored row's own status decides, and restore never writes one from the proof.
            raise RestoreSubscriptionNotEntitled

        if stored.user_id != identity.user.id:
            # 45-03 and 45-04 replace this arm with the adoption branch and the capped move.
            raise RestoreSubscriptionNotEntitled

        marked_active = await self.subscriptions_db.lock_grants(stored.user_id, self.evaluated_at)
        # The webhook's own writer, called unchanged, so both paths mint one term the same way.
        outcome = await self.subscriptions_db.write_subscription_grant(
            user_id=stored.user_id,
            subscription_id=stored.id,
            status=status,
            marked_active=marked_active,
            tier_id=stored.tier_id,
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

    def _verify(self, provider: PurchaseProvider,
                restore_proof: str) -> RestoredSubscription:
        """Run the one proof check this store answers to, before any statement opens a transaction."""
        if provider is not PurchaseProvider.apple:
            # 45-02 adds the Play read; until it lands this deployment serves the Apple proof only.
            raise RestoreProviderUnknown
        # Verified locally against the vendored root, never live (D-04).
        return self.app_store.verify_transaction(restore_proof, self.evaluated_at)

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
