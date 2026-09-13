"""Store-subscription writes over `core.subscriptions`, `audit.subscription_events` and the buyer's grant.
Lock order: grant rows ascending by id, then their usage rows; the subscription row is never locked."""
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

import structlog
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud.grants import GrantsDB
from nativespeaker.api.crud.violations import is_unique_violation
from nativespeaker.api.errors import MissingUsageRowError, MultipleEffectiveGrantsError
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    PurchaseProvider,
    StorePurchase,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
    UserMonthlyUsage,
    clamped_to_database_instant,
    database_instant,
    monthly_period_for,
)

logger = structlog.get_logger()

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


def _claim_owner_statement(subscription_id: UUID, owner_read: UUID | None,
                           month_read: date | None, values: dict):
    """The conditional owner update: it writes only where the row still says what the read saw."""
    return (update(Subscription)
            .where(col(Subscription.id) == subscription_id,
                   # Both columns are nullable, so equality would not match the NULL a read saw.
                   col(Subscription.user_id).is_not_distinct_from(owner_read),
                   col(Subscription.last_cross_account_transfer_month)
                   .is_not_distinct_from(month_read))
            .values(**values)
            # No synchronization, so this emits one statement and reads nothing back.
            .execution_options(synchronize_session=False))


def _hold_clock_statement(subscription_id: UUID, clock_read: datetime | None,
                          instant: datetime):
    """The conditional touch that takes the row only where its store clock still reads as read."""
    return (update(Subscription)
            .where(col(Subscription.id) == subscription_id,
                   col(Subscription.store_signed_at).is_not_distinct_from(clock_read))
            .values(updated_at=instant)
            .execution_options(synchronize_session=False))


def _purchase_statement(provider: PurchaseProvider, external_id: str):
    """The `core.store_purchases` row for the lifecycle pair its UNIQUE constraint keys."""
    return select(StorePurchase).where(col(StorePurchase.provider) == provider,
                                       col(StorePurchase.external_id) == external_id)


class SubscriptionsDB:

    def __init__(self, session: AsyncSession):
        self.session = session
        # The one spelling of the lock order: a second pair of statements would be a second thing to keep correct.
        self.grants_db = GrantsDB(session)

    async def lock_grants(self, user_id: UUID) -> list[AccessGrant]:
        """Take both lock tiers for one buyer and return every grant row marked active."""
        return await self.lock_grants_of([user_id], counted_for=user_id)

    async def lock_grants_of(self, user_ids: list[UUID], *,
                             counted_for: UUID) -> list[AccessGrant]:
        """Take both lock tiers for one or two accounts at once and return every grant marked active.
        `counted_for` is the account whose monthly counter the write under these locks carries."""
        # One statement for the pair, so the grant tier stays one ascending order and never two.
        marked_active = await self.grants_db.lock_active_grants_of(user_ids)
        for grant in marked_active:
            usage = await self.grants_db.lock_usage(grant.id)
            if usage is None:
                if grant.user_id == counted_for:
                    raise MissingUsageRowError(grant.id)
                # A move reads no counter of the other account, so a break there is a log and not a refusal.
                logger.error("source_grant_without_usage_row", grant_id=str(grant.id),
                             user_id=str(grant.user_id))
        return marked_active

    async def read_event(self, notification_uuid: str) -> SubscriptionEvent | None:
        """The already-recorded event for `notification_uuid`, or `None`, taking no lock."""
        return (await self.session.exec(_event_statement(notification_uuid))).first()

    async def read_subscription(self, provider: PurchaseProvider,
                                external_id: str) -> Subscription | None:
        """The canonical row as of now for the lifecycle pair, or `None`, taking no lock."""
        # Keep populate_existing. Without it the identity map gives the values of the first read.
        statement = _subscription_statement(provider, external_id).execution_options(
            populate_existing=True)
        return (await self.session.exec(statement)).first()

    async def read_owner(self, provider: PurchaseProvider, external_id: str) -> UUID | None:
        """The owner the canonical row carries right now, or `None`, taking no lock."""
        statement = select(Subscription.user_id).where(col(Subscription.provider) == provider,
                                                       col(Subscription.external_id) == external_id)
        return (await self.session.exec(statement)).first()

    async def read_purchase(self, provider: PurchaseProvider,
                            external_id: str) -> StorePurchase | None:
        """The recorded purchase for the lifecycle pair, or `None`, taking no lock."""
        return (await self.session.exec(_purchase_statement(provider, external_id))).first()

    async def _flush_or_lose(self, stored: Subscription,
                             outcome: WriteOutcome) -> tuple[Subscription, WriteOutcome]:
        """Flush the pending canonical row, reading a unique violation as a race this writer lost."""
        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if not is_unique_violation(violation):
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return stored, WriteOutcome.lost_race
        return stored, outcome

    async def insert_subscription(self, *,
                                  provider: PurchaseProvider,
                                  external_id: str,
                                  user_id: UUID | None,
                                  tier_id: str,
                                  status: SubscriptionStatus,
                                  signed_at: datetime | None) -> tuple[Subscription, WriteOutcome]:
        """Add the canonical row for a lifecycle pair that has none, and flush it.
        A row another writer committed first is a lost race, never an update over its state."""
        instant = datetime.now(UTC)
        stored = Subscription(provider=provider,
                              external_id=external_id,
                              user_id=user_id,
                              tier_id=tier_id,
                              status=status,
                              store_signed_at=signed_at,
                              created_at=instant,
                              updated_at=instant)
        self.session.add(stored)
        return await self._flush_or_lose(stored, WriteOutcome.applied)

    async def upsert_subscription(self, *,
                                  provider: PurchaseProvider,
                                  external_id: str,
                                  user_id: UUID | None,
                                  tier_id: str,
                                  status: SubscriptionStatus,
                                  signed_at: datetime | None,
                                  clock_read: datetime | None) -> tuple[Subscription, WriteOutcome]:
        """Update the existing canonical row in place, or insert one, and flush it.
        Both the owner and the store clock are taken conditionally, on what the caller read: this
        row is never locked, so an update keyed on the id alone is last-writer-wins over a rival."""
        instant = datetime.now(UTC)
        stored = await self.read_subscription(provider, external_id)
        outcome = WriteOutcome.applied
        if stored is None:
            stored = Subscription(provider=provider,
                                  external_id=external_id,
                                  user_id=user_id,
                                  tier_id=tier_id,
                                  status=status,
                                  store_signed_at=signed_at,
                                  created_at=instant,
                                  updated_at=instant)
            self.session.add(stored)
        else:
            # D-09: the token attributes an unowned row only, and restore alone changes an owner.
            owner = stored.user_id if stored.user_id is not None else user_id
            settled = (stored.tier_id, stored.status, stored.user_id) == (tier_id, status, owner)
            if stored.user_id is None and owner is not None:
                claimed = await self.claim_subscription_owner(
                    subscription_id=stored.id,
                    owner_read=None,
                    month_read=stored.last_cross_account_transfer_month,
                    destination=owner,
                    transfer_month=None)
                if not claimed:
                    return stored, WriteOutcome.lost_race
            moves_clock = signed_at is not None and (stored.store_signed_at is None
                                                     or signed_at > stored.store_signed_at)
            if not settled or moves_clock:
                if not await self.hold_subscription_clock(subscription_id=stored.id,
                                                          clock_read=clock_read):
                    return stored, WriteOutcome.lost_race
            advanced = signed_at if moves_clock else None
            if advanced is not None:
                stored.store_signed_at = advanced
                stored.updated_at = instant
            if settled:
                # The lifecycle row already says this, so a repeat event carries no change to record.
                outcome = WriteOutcome.replayed
            else:
                # Updated in place, never flipped and re-inserted: one row per lifecycle pair is the index's rule.
                stored.tier_id = tier_id
                stored.status = status
                stored.user_id = owner  # The claim above writes the column. The callers read this attribute.
                stored.updated_at = instant

        return await self._flush_or_lose(stored, outcome)

    async def claim_subscription_owner(self, *,
                                       subscription_id: UUID,
                                       owner_read: UUID | None,
                                       month_read: date | None,
                                       destination: UUID,
                                       transfer_month: date | None) -> bool:
        """Set the owner where the row still says what the pre-transaction read saw.
        Takes no lock on `core.subscriptions`; the row count is the whole answer."""
        instant = datetime.now(UTC)
        values: dict[str, object] = {"user_id": destination, "updated_at": instant}
        if transfer_month is not None:
            # A move alone gives one: adoption leaves the column exactly as it found it.
            values["last_cross_account_transfer_month"] = transfer_month
        # The caller must re-read the row: this never refreshes a `Subscription` already loaded.
        statement = _claim_owner_statement(subscription_id, owner_read, month_read, values)
        return (await self.session.exec(statement)).rowcount == 1

    async def hold_subscription_clock(self, *, subscription_id: UUID,
                                      clock_read: datetime | None) -> bool:
        """Take the canonical row where its store clock still says what the caller decided on.
        Takes no `FOR UPDATE` (43 D-16): the write lock this statement itself holds until the
        transaction ends is what serializes the writes behind it, and the row count is the answer."""
        instant = datetime.now(UTC)
        statement = _hold_clock_statement(subscription_id, clock_read, instant)
        return (await self.session.exec(statement)).rowcount == 1

    async def insert_purchase(self, *,
                              provider: PurchaseProvider,
                              identity_value: str,
                              external_id: str,
                              store_transaction_id: str | None,
                              store_original_transaction_id: str | None,
                              purchase_user_id: UUID | None,
                              resolved_token_value: str | None) -> WriteOutcome:
        """Add the one purchase row for this lifecycle pair and flush it."""
        instant = datetime.now(UTC)
        self.session.add(StorePurchase(provider=provider,
                                       identity_value=identity_value,
                                       external_id=external_id,
                                       store_transaction_id=store_transaction_id,
                                       store_original_transaction_id=store_original_transaction_id,
                                       purchase_user_id=purchase_user_id,
                                       resolved_token_value=resolved_token_value,
                                       created_at=instant))

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if not is_unique_violation(violation):
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return WriteOutcome.lost_race
        return WriteOutcome.applied

    async def append_event(self, *,
                           subscription: Subscription,
                           event_type: str,
                           notification_uuid: str,
                           old_tier_id: str | None,
                           new_tier_id: str) -> WriteOutcome:
        """Append the event row for one notification and flush it; the subscription is flushed already."""
        instant = datetime.now(UTC)
        self.session.add(SubscriptionEvent(subscription_id=subscription.id,
                                           event_type=event_type,
                                           notification_uuid=notification_uuid,
                                           old_tier_id=old_tier_id,
                                           new_tier_id=new_tier_id,
                                           created_at=instant))

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if not is_unique_violation(violation):
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
                                       may_reactivate: bool) -> WriteOutcome:
        """Supersede the buyer's held grants and insert this term's, under locks `lock_grants` took.
        `may_reactivate` is restore's alone: ingestion passes False and writes nothing for a lapsed term."""
        instant = datetime.now(UTC)
        entitled = status in ENTITLED_STATUSES
        held = [grant for grant in marked_active
                if grant.source is AccessGrantSource.subscription
                and grant.subscription_id == subscription_id
                # The buyer's own rows only: on a move `marked_active` also holds the old owner's,
                # and reading one of those as a replay would leave the destination with no grant.
                and grant.user_id == user_id]
        # The tier is asked with the term: a mid-term tier change takes the same expire-then-insert path below.
        if entitled and [grant for grant in held
                         if grant.ends_at == ends_at and grant.tier_id == tier_id]:
            return WriteOutcome.replayed

        if (entitled and not held and not may_reactivate
                and await self.grants_db.has_prior_subscription_grant(subscription_id)):
            return WriteOutcome.replayed

        # Every grant the destination holds goes, the free one too: `ix_access_grants_one_active_per_user` allows one.
        # The old owner's grant for another subscription is not this write's to end.
        superseded = ([grant for grant in marked_active
                       if grant.user_id == user_id or grant.subscription_id == subscription_id]
                      if entitled else held)
        # Revoked only where the store withdrew this subscription; every other end of a term is an expiry.
        ended = (AccessGrantStatus.revoked if status is SubscriptionStatus.revoked
                 else AccessGrantStatus.expired)
        for grant in superseded:
            if grant.source is AccessGrantSource.manual:
                logger.warning("manual_grant_superseded", grant_id=str(grant.id),
                               source=grant.source)
            grant.status = ended
            grant.ends_at = database_instant()
            grant.updated_at = instant

        if superseded:
            # Flushed alone and first: the ORM emits inserts before updates, and the index is per-statement.
            try:
                await self.session.flush()
            except IntegrityError as violation:
                # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
                if not is_unique_violation(violation):
                    # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                    raise
                return WriteOutcome.lost_race

        if not entitled:
            # The buyer holds no grant outside the entitled set, and only restore is a path back to one.
            return WriteOutcome.applied if superseded else WriteOutcome.replayed

        period = monthly_period_for(instant)
        carried = 0
        mine = [grant for grant in superseded
                if grant.user_id == user_id and grant.source is AccessGrantSource.subscription]
        if len(mine) > 1:
            raise MultipleEffectiveGrantsError(len(mine), user_id)
        for grant in mine:
            usage = await self.grants_db.read_usage(grant.id)
            if usage is None:
                raise MissingUsageRowError(grant.id)
            if usage.monthly_period == period:
                carried = usage.monthly_used

        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.subscription,
                                subscription_id=subscription_id,
                                starts_at=clamped_to_database_instant(starts_at),
                                ends_at=ends_at,
                                created_at=instant,
                                updated_at=instant)
        self.session.add(activated)
        # Minted with its grant and never for an existing one: a missing usage row is a broken invariant.
        self.session.add(UserMonthlyUsage(grant_id=activated.id,
                                          monthly_period=period,
                                          monthly_used=carried,
                                          created_at=instant,
                                          updated_at=instant))

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if not is_unique_violation(violation):
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return WriteOutcome.lost_race
        return WriteOutcome.applied
