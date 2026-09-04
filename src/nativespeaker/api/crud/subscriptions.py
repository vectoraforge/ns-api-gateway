"""Store-subscription writes over `core.subscriptions`, `audit.subscription_events` and the buyer's grant.
Lock order: grant rows ascending by id, then their usage rows; the subscription row is never locked."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud.grants import GrantsDB
from nativespeaker.api.tables import (
    FREE_GRANT_SOURCES,
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    PurchaseProvider,
    StorePurchase,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
    UserMonthlyUsage,
)

# The set `core.subscriptions.product_entitled_subscription_id` is generated over, named once for its readers.
ENTITLED_STATUSES = frozenset({SubscriptionStatus.active, SubscriptionStatus.grace_period})


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
        # The one spelling of the lock order: a second pair of statements would be a second thing to keep correct.
        self.grants_db = GrantsDB(session)

    async def lock_grants(self, user_id: UUID, evaluated_at: datetime) -> list[AccessGrant]:
        """Take both lock tiers for one buyer and return every grant row marked active."""
        # First and ascending by id: this set contains the effective one, so one grant-tier order holds.
        marked_active = await self.grants_db.lock_active_grants(user_id)
        effective = await self.grants_db.lock_effective_grants(user_id, evaluated_at)
        for grant in effective:
            # Second in the lock order, always after the grant rows.
            await self.grants_db.lock_usage(grant.id)
        return marked_active

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

    async def write_subscription_grant(self, *,
                                       user_id: UUID,
                                       subscription_id: UUID,
                                       status: SubscriptionStatus,
                                       marked_active: list[AccessGrant],
                                       tier_id: str,
                                       starts_at: datetime,
                                       ends_at: datetime | None,
                                       evaluated_at: datetime) -> WriteOutcome:
        """Supersede the buyer's held grants and insert this term's, under locks `lock_grants` took."""
        entitled = status in ENTITLED_STATUSES
        held = [grant for grant in marked_active
                if grant.source is AccessGrantSource.subscription
                and grant.subscription_id == subscription_id]
        # The tier is asked with the term: a mid-term tier change takes the same expire-then-insert path below.
        if entitled and [grant for grant in held
                         if grant.ends_at == ends_at and grant.tier_id == tier_id]:
            return WriteOutcome.replayed

        superseded = list(held)
        if entitled:
            # The lifetime free slot is spent here, and only restore is a path back to a grant.
            superseded += [grant for grant in marked_active if grant.source in FREE_GRANT_SOURCES]
        for grant in superseded:
            # Revoked only where the store withdrew the purchase; every other end of a term is an expiry.
            grant.status = (AccessGrantStatus.revoked
                            if grant.source is AccessGrantSource.subscription
                            and status is SubscriptionStatus.revoked
                            else AccessGrantStatus.expired)
            grant.ends_at = evaluated_at
            grant.updated_at = evaluated_at

        if superseded:
            # Flushed alone and first: the ORM emits inserts before updates, and the index is per-statement.
            try:
                await self.session.flush()
            except IntegrityError as violation:
                # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
                if violation.orig.sqlstate != "23505":
                    # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                    raise
                return WriteOutcome.lost_race

        if not entitled:
            # The buyer holds no grant outside the entitled set; the deferrable foreign key is the backstop, not this.
            return WriteOutcome.applied if superseded else WriteOutcome.replayed

        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.subscription,
                                subscription_id=subscription_id,
                                starts_at=starts_at,
                                ends_at=ends_at,
                                created_at=evaluated_at,
                                updated_at=evaluated_at)
        self.session.add(activated)
        # Minted with its grant and never for an existing one: a missing usage row is a broken invariant.
        self.session.add(UserMonthlyUsage(grant_id=activated.id,
                                          monthly_period=evaluated_at.strftime("%Y-%m"),
                                          monthly_used=0,
                                          created_at=evaluated_at,
                                          updated_at=evaluated_at))

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
