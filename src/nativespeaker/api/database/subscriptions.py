from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.models import (
    Subscription,
    SubscriptionEvent,
    SubscriptionPlan,
    SubscriptionProvider,
    SubscriptionStatus,
)
from nativespeaker.api.models.users import AccessGrant, ExternalIdentity


class SubscriptionDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_subscription_by_external_id(self,
                                               external_id: str,
                                               provider: SubscriptionProvider) -> Subscription | None:
        result = await self.session.exec(
            select(Subscription).where(
                Subscription.external_id == external_id,
                Subscription.provider == provider,
            )
        )
        return result.first()

    async def create_subscription(self,
                                  user_id: UUID,
                                  provider: SubscriptionProvider,
                                  external_id: str,
                                  plan: SubscriptionPlan,
                                  status: SubscriptionStatus) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            provider=provider,
            external_id=external_id,
            plan=plan,
            status=status,
        )
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def update_subscription(self,
                                  subscription: Subscription,
                                  plan: SubscriptionPlan,
                                  status: SubscriptionStatus) -> None:
        subscription.plan = plan
        subscription.status = status
        subscription.updated_at = datetime.now(UTC)
        self.session.add(subscription)
        await self.session.flush()

    async def insert_event_idempotent(self,
                                      subscription_id: UUID,
                                      event_type: str,
                                      notification_uuid: str,
                                      old_plan: SubscriptionPlan | None,
                                      new_plan: SubscriptionPlan | None) -> bool:
        """Insert subscription event if not duplicate. Returns True if inserted, False if duplicate."""
        stmt = (
            pg_insert(SubscriptionEvent)
            .values(
                subscription_id=subscription_id,
                event_type=event_type,
                notification_uuid=notification_uuid,
                old_plan=old_plan,
                new_plan=new_plan,
            )
            .on_conflict_do_nothing(index_elements=["notification_uuid"])
        )
        result = await self.session.exec(stmt)
        return result.rowcount > 0

    async def update_user_plan(self, user_id: UUID, plan: SubscriptionPlan) -> UUID | None:
        """Point the user's subscription-backed access grant at the tier the plan names.

        A plan is not a column on `core.users`: entitlement is a `core.access_grants` row, and
        a plan change is a change of that grant's tier. Returns the grant id so the caller can
        reset the usage counter that hangs off it, or `None` where no subscription-backed grant
        exists to move.
        """
        # [impl->req~schema-users-no-plan-fields~1]
        result = await self.session.exec(
            select(AccessGrant).where(AccessGrant.user_id == user_id,
                                      AccessGrant.source == AccessGrantSource.subscription)
        )
        grant = result.first()
        if grant is None:
            return None
        grant.tier_id = str(plan)
        self.session.add(grant)
        await self.session.flush()
        return grant.id

    async def external_subject(self, user_id: UUID) -> str | None:
        """The verified external subject of this user's identity row, for the provider-side
        claim write. It comes from `core.external_identities` and from nowhere else."""
        result = await self.session.exec(
            select(ExternalIdentity.subject).where(ExternalIdentity.user_id == user_id)
        )
        return result.first()
