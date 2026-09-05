"""Store-subscription ingestion: one verified notification, one transaction, one commit."""
from datetime import datetime
from uuid import uuid7

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.errors import AttributionConflict, InternalError, UnmappedStoreProduct
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
        self.purchases_db = PurchasesDB(db)
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
        # Server-controlled reference data, never a value the store supplied.
        self.products = products

    async def ingest(self, notification: VerifiedNotification) -> None:
        """Record one verified notification and commit, or return having written nothing.
        The purchase arms run in order: refuse a changed attribution, keep an agreeing one, insert a new pair."""
        if notification.external_id is None or notification.product_id is None:
            # Verified but unwritable: `audit.subscription_events.subscription_id` is NOT NULL.
            logger.info("store_notification_without_transaction",
                        event_type=notification.event_type)
            return

        tier_id = self.products.get(notification.product_id)
        if tier_id is None:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(notification.provider, notification.product_id)

        token = notification.attribution_token
        # Read before the transaction writes, so no token read happens under a lock.
        user_id = (None if token is None
                   else await self.purchases_db.resolve_user(notification.provider, token))

        stored = await self.subscriptions_db.read_subscription(notification.provider,
                                                               notification.external_id)
        old_tier_id = None if stored is None else stored.tier_id
        # A plain read, never a lock: a subscription-row lock would sit ahead of the grant locks below.
        owner = user_id if user_id is not None else (None if stored is None else stored.user_id)

        # An unattributed purchase has no buyer, so there is no row to lock and no grant to hold.
        marked_active = ([] if owner is None
                         else await self.subscriptions_db.lock_grants(owner, self.evaluated_at))

        if await self.subscriptions_db.read_event(notification.notification_uuid) is not None:
            # The replay: the store's own key is already recorded, so this delivery writes nothing.
            return

        if (stored is not None and stored.store_signed_at is not None
                and notification.signed_at is not None
                and notification.signed_at < stored.store_signed_at):
            # Apple guarantees no delivery order, and `notification_uuid` only catches the same payload twice.
            await self._settle(await self.subscriptions_db.append_event(
                subscription=stored,
                event_type=notification.event_type,
                notification_uuid=notification.notification_uuid,
                # The recorded tier on both sides: no transition was applied, so none is claimed.
                old_tier_id=stored.tier_id,
                new_tier_id=stored.tier_id,
                evaluated_at=self.evaluated_at), notification)
            logger.info("store_notification_superseded", event_type=notification.event_type)
            # Reached before the attribution guard: a stale payload must not earn the 500 that guard raises.
            await self.session.commit()
            return

        recorded = await self.subscriptions_db.read_purchase(notification.provider,
                                                             notification.external_id)
        # Keyed on the only-ever-store-supplied value: a server-minted placeholder is no rival owner.
        # That placeholder stays: the purchase row is written once per lifecycle key and never updated.
        if (recorded is not None and token is not None
                and recorded.resolved_token_value is not None
                and recorded.resolved_token_value != token):
            # Refused, never repaired: this route cannot verify a changed owner, and the store retries.
            raise AttributionConflict(notification.provider, notification.external_id)

        status = status_at(notification, self.evaluated_at)
        subscription, outcome = await self.subscriptions_db.upsert_subscription(
            provider=notification.provider,
            external_id=notification.external_id,
            user_id=user_id,
            tier_id=tier_id,
            status=status,
            signed_at=notification.signed_at,
            evaluated_at=self.evaluated_at)
        await self._settle(outcome, notification)

        if recorded is None:
            # Inserted after the subscription flushed: `core.store_purchases` keys a foreign key on the pair.
            await self._settle(await self.subscriptions_db.insert_purchase(
                provider=notification.provider,
                # A generated value only when the store gave none: the column is NOT NULL.
                identity_value=str(uuid7()) if token is None else token,
                external_id=notification.external_id,
                store_transaction_id=notification.transaction_id,
                store_original_transaction_id=notification.external_id,
                purchase_user_id=user_id,
                # Set only when the token resolved: the second foreign key needs a binding to point at.
                resolved_token_value=None if user_id is None else token,
                evaluated_at=self.evaluated_at), notification)

        # Appended after the subscription flushed: the event row's `subscription_id` references it.
        await self._settle(await self.subscriptions_db.append_event(
            subscription=subscription,
            event_type=notification.event_type,
            notification_uuid=notification.notification_uuid,
            old_tier_id=old_tier_id,
            new_tier_id=tier_id,
            evaluated_at=self.evaluated_at), notification)

        if subscription.user_id is not None:
            await self._settle(await self.subscriptions_db.write_subscription_grant(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                status=status,
                marked_active=marked_active,
                tier_id=tier_id,
                # The captured instant stands in where the store gave no purchase date for this term.
                starts_at=(self.evaluated_at if notification.purchased_at is None
                           else notification.purchased_at),
                # During grace the term is Apple's grace window, because the paid term has lapsed.
                ends_at=(notification.grace_period_expires_at
                         if status is SubscriptionStatus.grace_period else notification.expires_at),
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
