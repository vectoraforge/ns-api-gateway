"""Store-subscription ingestion: one verified notification, one transaction, one commit."""
from datetime import UTC, datetime
from uuid import uuid7

import structlog
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.store_notifications import VerifiedNotification, term_end_for
from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.crud.subscriptions import (
    ENTITLED_STATUSES,
    SubscriptionsDB,
    WriteOutcome,
)
from nativespeaker.api.crud.violations import is_unique_violation
from nativespeaker.api.errors import AttributionConflict, InternalError

logger = structlog.get_logger()


class SubscriptionsService:

    def __init__(self, db: AsyncSession) -> None:
        self.session = db
        self.subscriptions_db = SubscriptionsDB(db)
        self.purchases_db = PurchasesDB(db)

    async def ingest(self, notification: VerifiedNotification) -> None:
        """Record one verified notification and commit, or return having written nothing.
        The purchase arms run in order: refuse a changed attribution, keep an agreeing one, insert a new pair."""
        instant = datetime.now(UTC)
        if notification.external_id is None or notification.product_id is None:
            # Verified but unwritable: `audit.subscription_events.subscription_id` is NOT NULL.
            logger.info("store_notification_without_transaction",
                        event_type=notification.event_type)
            return

        # Resolved in the provider's own class, which refuses a product the configured map misses.
        tier_id = notification.tier_id
        if tier_id is None:
            # Tested, not assumed from `product_id`: it reaches three NOT NULL columns below.
            logger.error("store_notification_without_tier", event_type=notification.event_type)
            raise InternalError

        if await self.subscriptions_db.read_event(notification.notification_uuid) is not None:
            # The rollback releases the transaction now, because `get_db` closes it after the response.
            await self.session.rollback()
            return

        token = notification.attribution_token
        # Read before the transaction writes, so no token read happens under a lock.
        user_id = (None if token is None
                   else await self.purchases_db.resolve_user(notification.provider, token))

        stored = await self.subscriptions_db.read_subscription(notification.provider,
                                                               notification.external_id)
        # A plain read, never a lock: a subscription-row lock would sit ahead of the grant locks below.
        # The crud's D-09 rule, restated: the owner the writer will keep is the owner locked here.
        owner = (stored.user_id if stored is not None and stored.user_id is not None else user_id)

        # An unattributed purchase has no buyer, so there is no row to lock and no grant to hold.
        marked_active = ([] if owner is None
                         else await self.subscriptions_db.lock_grants(owner))

        settled_owner = await self.subscriptions_db.read_owner(notification.provider,
                                                               notification.external_id)
        if settled_owner is not None and settled_owner != owner:
            logger.warning("store_notification_owner_moved", provider=str(notification.provider))
            raise InternalError

        settled = await self.subscriptions_db.read_subscription(notification.provider,
                                                                 notification.external_id)
        old_tier_id = None if settled is None else settled.tier_id
        if (settled is not None and settled.store_signed_at is not None
                and notification.signed_at is not None
                and notification.signed_at < settled.store_signed_at):
            # Neither store guarantees delivery order, and `notification_uuid` only catches one payload twice.
            await self._settle(await self.subscriptions_db.append_event(
                subscription=settled,
                event_type=notification.event_type,
                notification_uuid=notification.notification_uuid,
                # The recorded tier on both sides: no transition was applied, so none is claimed.
                old_tier_id=settled.tier_id,
                new_tier_id=settled.tier_id), notification)
            logger.warning("store_notification_superseded", event_type=notification.event_type)
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
            raise AttributionConflict(notification.provider, recorded.id)

        # The store's own word, read live or from the signed envelope: never derived here.
        status = notification.status
        starts_at = min(notification.purchased_at or instant, instant)
        term_ends_at = term_end_for(status, notification)
        if status in ENTITLED_STATUSES and (term_ends_at is None
                                            or term_ends_at <= starts_at
                                            or term_ends_at <= instant):
            logger.error("store_notification_without_term", event_type=notification.event_type)
            raise InternalError
        subscription, outcome = await self.subscriptions_db.upsert_subscription(
            provider=notification.provider,
            external_id=notification.external_id,
            user_id=user_id,
            tier_id=tier_id,
            status=status,
            signed_at=notification.signed_at,
            clock_read=None if settled is None else settled.store_signed_at)
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
                resolved_token_value=None if user_id is None else token), notification)

        # Appended after the subscription flushed: the event row's `subscription_id` references it.
        await self._settle(await self.subscriptions_db.append_event(
            subscription=subscription,
            event_type=notification.event_type,
            notification_uuid=notification.notification_uuid,
            old_tier_id=old_tier_id,
            new_tier_id=tier_id), notification)

        if subscription.user_id is not None:
            await self._settle(await self.subscriptions_db.write_subscription_grant(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                status=status,
                marked_active=marked_active,
                tier_id=tier_id,
                starts_at=starts_at,
                ends_at=term_ends_at,
                may_reactivate=False), notification)

        # Deliberate commit: the store reads the status code, so 200 must mean the rows are durable.
        try:
            await self.session.commit()
        except IntegrityError as violation:
            # The entitlement keys are DEFERRABLE, so the commit is where they fail.
            if not is_unique_violation(violation):
                logger.error("store_notification_commit_refused",
                             sqlstate=getattr(violation.orig, "sqlstate", None))
                raise
            await self._settle(WriteOutcome.lost_race, notification)

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
