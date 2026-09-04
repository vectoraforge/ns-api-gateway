"""Store-subscription ingestion: one verified notification, one transaction, one commit."""
from datetime import datetime

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.errors import InternalError, UnmappedStoreProduct
from nativespeaker.api.tables import SubscriptionStatus

logger = structlog.get_logger()


def status_at(notification: VerifiedNotification,
              evaluated_at: datetime) -> SubscriptionStatus:
    """The subscription's status from its dates alone. The notification type is only recorded."""
    if notification.revoked_at is not None:
        # A withdrawal is terminal, so it outranks every date below it.
        return SubscriptionStatus.revoked
    if notification.expires_at is not None and notification.expires_at > evaluated_at:
        # An unfinished paid term is entitled, whatever the renewal flags say about the next one.
        return SubscriptionStatus.active
    if (notification.grace_period_expires_at is not None
            and notification.grace_period_expires_at > evaluated_at):
        # Tested before billing retry: Apple sets the retry flag during grace too, and grace is entitled.
        return SubscriptionStatus.grace_period
    if notification.in_billing_retry:
        # The term is over and Apple is still charging, so the store has not given up on it.
        return SubscriptionStatus.billing_retry
    return SubscriptionStatus.expired


class SubscriptionsService:

    def __init__(self, db: AsyncSession, evaluated_at: datetime,
                 products: dict[str, str]) -> None:
        self.session = db
        self.subscriptions_db = SubscriptionsDB(db)
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
        # Server-controlled reference data, never a value the store supplied.
        self.products = products

    async def ingest(self, notification: VerifiedNotification) -> None:
        """Record one verified notification and commit, or return having written nothing."""
        if notification.external_id is None or notification.product_id is None:
            # Verified but unwritable: `audit.subscription_events.subscription_id` is NOT NULL.
            logger.info("store_notification_without_transaction",
                        event_type=notification.event_type)
            return

        tier_id = self.products.get(notification.product_id)
        if tier_id is None:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(notification.provider, notification.product_id)

        if await self.subscriptions_db.read_event(notification.notification_uuid) is not None:
            # The replay: the store's own key is already recorded, so this delivery writes nothing.
            return

        stored = await self.subscriptions_db.read_subscription(notification.provider,
                                                               notification.external_id)
        old_tier_id = None if stored is None else stored.tier_id

        subscription, outcome = await self.subscriptions_db.upsert_subscription(
            provider=notification.provider,
            external_id=notification.external_id,
            tier_id=tier_id,
            status=status_at(notification, self.evaluated_at),
            evaluated_at=self.evaluated_at)
        await self._settle(outcome, notification)

        # Appended after the subscription flushed: the event row's `subscription_id` references it.
        await self._settle(await self.subscriptions_db.append_event(
            subscription=subscription,
            event_type=notification.event_type,
            notification_uuid=notification.notification_uuid,
            old_tier_id=old_tier_id,
            new_tier_id=tier_id,
            evaluated_at=self.evaluated_at), notification)

        # Deliberate commit: the store reads the status code, so 200 must mean the rows are durable.
        await self.session.commit()

    async def _settle(self, outcome: WriteOutcome,
                      notification: VerifiedNotification) -> None:
        """Answer for what the writer did: a lost race is a 5xx the store's resend then finds recorded."""
        if outcome is not WriteOutcome.lost_race:
            return
        # The writer's transaction is unusable, and the winner's rows are what the resend will read.
        await self.session.rollback()
        # Labels come from a closed set only: the store's own name, never a payload value.
        logger.warning("store_notification_race_lost", provider=str(notification.provider))
        # The generic 500, not a leaf of its own: the client is told nothing and the store retries.
        raise InternalError
