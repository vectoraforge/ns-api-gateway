"""Entitlement reads over `core.access_grants`, and the one writer of an anonymous device grant.
Global lock order: grant rows ascending by id, then usage rows, and never a third tier."""
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.tables import (
    FREE_GRANT_SOURCES,
    AccessGrant,
    AccessGrantAntiAbuse,
    AccessGrantSource,
    AccessGrantStatus,
    AccessTier,
    UserMonthlyUsage,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, NativeClaimProvider


def _effective_grants_statement(user_id: UUID, evaluated_at: datetime):
    """Every grant of `user_id` effective at `evaluated_at`, ascending by id."""
    return (
        select(AccessGrant)
        .where(col(AccessGrant.user_id) == user_id,
               # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
               col(AccessGrant.status) == AccessGrantStatus.active,
               col(AccessGrant.starts_at) <= evaluated_at,
               or_(col(AccessGrant.ends_at).is_(None),
                   col(AccessGrant.ends_at) > evaluated_at))
        # No `.limit(...)`: the caller must see a second effective grant and fail closed on it.
        .order_by(col(AccessGrant.id).asc())
    )


def _usage_statement(grant_id: UUID):
    """The `core.user_monthly_usage` row keyed by `grant_id`."""
    # Never inserts: `None` is the fail-closed signal, not a cue to mint a row and hand out an allowance.
    return select(UserMonthlyUsage).where(col(UserMonthlyUsage.grant_id) == grant_id)


def _prior_free_grant_statement(user_id: UUID):
    """Every free-source grant `user_id` has ever held, in any status."""
    # No status predicate: the index this mirrors has none, so expiry never reopens the lifetime slot.
    return select(AccessGrant).where(col(AccessGrant.user_id) == user_id,
                                     col(AccessGrant.source).in_(FREE_GRANT_SOURCES))


class GrantsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."""
        # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
        statement = _effective_grants_statement(user_id, evaluated_at).with_for_update()
        return list((await self.session.exec(statement)).all())

    async def read_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Return every effective grant for `user_id` at `evaluated_at`, ascending by id, taking no lock."""
        statement = _effective_grants_statement(user_id, evaluated_at)
        return list((await self.session.exec(statement)).all())

    async def lock_usage(self, grant_id: UUID) -> UserMonthlyUsage | None:
        """Lock and return `grant_id`'s usage row, or `None`. Second in the lock order and never first."""
        statement = _usage_statement(grant_id).with_for_update()
        return (await self.session.exec(statement)).first()

    async def read_usage(self, grant_id: UUID) -> UserMonthlyUsage | None:
        """Return `grant_id`'s usage row, or `None`, taking no lock."""
        return (await self.session.exec(_usage_statement(grant_id))).first()

    async def monthly_credits(self, tier_id: str) -> int | None:
        statement = select(AccessTier.monthly_credits).where(col(AccessTier.id) == tier_id)
        return (await self.session.exec(statement)).first()

    async def has_prior_free_grant(self, user_id: UUID) -> bool:
        """Whether `user_id` has ever held a free-source grant, taking no lock."""
        return (await self.session.exec(_prior_free_grant_statement(user_id))).first() is not None

    async def activate_anonymous_device_grant(self, *,
                                              user_id: UUID,
                                              identity_row: ExternalIdentity,
                                              tier_id: str,
                                              evaluated_at: datetime) -> bool:
        """Take both lock tiers, then write the grant, its anti-abuse row, its usage row and the marker."""
        grants = await self.lock_effective_grants(user_id, evaluated_at)
        for grant in grants:
            await self.lock_usage(grant.id)

        # A plain re-read, never `lock_identity_and_user`: a user-row lock ahead of the grant locks is forbidden.
        stored = await IdentitiesDB(self.session).resolve_existing(issuer=identity_row.issuer,
                                                                   subject=identity_row.subject)
        if stored is None or stored.provider is not IdentityProvider.anonymous:
            return False
        if grants or stored.free_grant_consumed_at is not None:
            return False
        if await self.has_prior_free_grant(user_id):
            return False

        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.anonymous_device_grant,
                                starts_at=evaluated_at,
                                created_at=evaluated_at,
                                updated_at=evaluated_at)
        self.session.add(activated)
        # Both hash columns stay NULL: that exact pattern is the iOS arm of the table's exclusive-or CHECK.
        self.session.add(AccessGrantAntiAbuse(grant_id=activated.id,
                                              grant_source=AccessGrantSource.anonymous_device_grant,
                                              native_claim_provider=NativeClaimProvider.ios_devicecheck,
                                              created_at=evaluated_at))
        self.session.add(UserMonthlyUsage(grant_id=activated.id,
                                          monthly_period=evaluated_at.strftime("%Y-%m"),
                                          monthly_used=0,
                                          created_at=evaluated_at,
                                          updated_at=evaluated_at))
        stored.free_grant_consumed_at = evaluated_at
        stored.native_claim_platform = NativeClaimProvider.ios_devicecheck
        stored.updated_at = evaluated_at

        # Only the flush is inside, and all three rows go in it: the two FKs are deferred to commit.
        try:
            await self.session.flush()
        except IntegrityError:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            return False
        return True
