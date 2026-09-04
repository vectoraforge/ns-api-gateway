"""Store-subscription reads and writes over `core.subscriptions` and `audit.subscription_events`.
Takes no lock: a subscription-row lock would be a tier ahead of the grant locks."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.tables import (
    PurchaseProvider,
    StorePurchase,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)


class WriteOutcome(StrEnum):
    """What one write did: it changed a row, it changed nothing, or a concurrent writer won."""
    applied = "applied"
    replayed = "replayed"
    lost_race = "lost_race"


def _event_statement(notification_uuid: str):
    """The `audit.subscription_events` row carrying `notification_uuid`, which is UNIQUE."""
    return select(SubscriptionEvent).where(
        col(SubscriptionEvent.notification_uuid) == notification_uuid)


def _subscription_statement(provider: PurchaseProvider, external_id: str):
    """The `core.subscriptions` row for the lifecycle pair `ix_subscriptions_provider_external_id` keys."""
    return select(Subscription).where(col(Subscription.provider) == provider,
                                      col(Subscription.external_id) == external_id)


def _purchase_statement(provider: PurchaseProvider, external_id: str):
    """The `core.store_purchases` row for the lifecycle pair its UNIQUE constraint keys."""
    return select(StorePurchase).where(col(StorePurchase.provider) == provider,
                                       col(StorePurchase.external_id) == external_id)


class SubscriptionsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def read_event(self, notification_uuid: str) -> SubscriptionEvent | None:
        """The already-recorded event for `notification_uuid`, or `None`, taking no lock."""
        return (await self.session.exec(_event_statement(notification_uuid))).first()

    async def read_subscription(self, provider: PurchaseProvider,
                                external_id: str) -> Subscription | None:
        """The canonical row for the lifecycle pair, or `None`, taking no lock."""
        return (await self.session.exec(_subscription_statement(provider, external_id))).first()

    async def read_purchase(self, provider: PurchaseProvider,
                            external_id: str) -> StorePurchase | None:
        """The recorded purchase for the lifecycle pair, or `None`, taking no lock."""
        return (await self.session.exec(_purchase_statement(provider, external_id))).first()

    async def upsert_subscription(self, *,
                                  provider: PurchaseProvider,
                                  external_id: str,
                                  user_id: UUID | None,
                                  tier_id: str,
                                  status: SubscriptionStatus,
                                  evaluated_at: datetime) -> tuple[Subscription, WriteOutcome]:
        """Update the existing canonical row in place, or insert one, and flush it."""
        stored = await self.read_subscription(provider, external_id)
        outcome = WriteOutcome.applied
        if stored is None:
            stored = Subscription(provider=provider,
                                  external_id=external_id,
                                  user_id=user_id,
                                  tier_id=tier_id,
                                  status=status,
                                  created_at=evaluated_at,
                                  updated_at=evaluated_at)
            self.session.add(stored)
        else:
            # An owner is added, never cleared: a later notification without a token unlinks nobody.
            owner = stored.user_id if user_id is None else user_id
            if (stored.tier_id, stored.status, stored.user_id) == (tier_id, status, owner):
                # The lifecycle row already says this, so a repeat event carries no change to record.
                outcome = WriteOutcome.replayed
            else:
                # Updated in place, never flipped and re-inserted: one row per lifecycle pair is the index's rule.
                stored.tier_id = tier_id
                stored.status = status
                stored.user_id = owner
                stored.updated_at = evaluated_at

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return stored, WriteOutcome.lost_race
        return stored, outcome

    async def insert_purchase(self, *,
                              provider: PurchaseProvider,
                              identity_value: str,
                              external_id: str,
                              store_transaction_id: str | None,
                              store_original_transaction_id: str | None,
                              purchase_user_id: UUID | None,
                              resolved_token_value: str | None,
                              evaluated_at: datetime) -> WriteOutcome:
        """Add the one purchase row for this lifecycle pair and flush it."""
        self.session.add(StorePurchase(provider=provider,
                                       identity_value=identity_value,
                                       external_id=external_id,
                                       store_transaction_id=store_transaction_id,
                                       store_original_transaction_id=store_original_transaction_id,
                                       purchase_user_id=purchase_user_id,
                                       resolved_token_value=resolved_token_value,
                                       created_at=evaluated_at))

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return WriteOutcome.lost_race
        return WriteOutcome.applied

    async def append_event(self, *,
                           subscription: Subscription,
                           event_type: str,
                           notification_uuid: str,
                           old_tier_id: str | None,
                           new_tier_id: str,
                           evaluated_at: datetime) -> WriteOutcome:
        """Append the event row for one notification and flush it; the subscription is flushed already."""
        self.session.add(SubscriptionEvent(subscription_id=subscription.id,
                                           event_type=event_type,
                                           notification_uuid=notification_uuid,
                                           old_tier_id=old_tier_id,
                                           new_tier_id=new_tier_id,
                                           created_at=evaluated_at))

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return WriteOutcome.lost_race
        return WriteOutcome.applied
