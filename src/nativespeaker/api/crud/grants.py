"""Entitlement reads over `core.access_grants`, and the one writer of each of the two free grants.
Global lock order: grant rows ascending by id, then usage rows, and never a third tier."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import MultipleEffectiveGrantsError
from nativespeaker.api.tables import (
    FREE_GRANT_SOURCES,
    AccessGrant,
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


def _active_grants_statement(user_id: UUID):
    """Every grant of `user_id` marked active, whatever its term, ascending by id."""
    # No time window: a partial index predicate must be IMMUTABLE, so `now()` cannot appear in
    # `ix_access_grants_one_active_per_user`, and its question is therefore asked on the mark alone.
    return (select(AccessGrant).where(col(AccessGrant.user_id) == user_id,
                                      col(AccessGrant.status) == AccessGrantStatus.active)
            .order_by(col(AccessGrant.id).asc()))


def _grants_of_source_statement(user_id: UUID, source: AccessGrantSource):
    """Every grant `user_id` has ever held from one source, in any status."""
    # One source and no status, which is `ix_access_grants_one_free_grant_per_user_source` exactly;
    # `_prior_free_grant_statement` below stays the broader account-level rule over both free sources.
    return select(AccessGrant).where(col(AccessGrant.user_id) == user_id,
                                     col(AccessGrant.source) == source)


def _prior_free_grant_statement(user_id: UUID):
    """Every free-source grant `user_id` has ever held, in any status."""
    # No status predicate: the index this mirrors has none, so expiry never reopens the lifetime slot.
    return select(AccessGrant).where(col(AccessGrant.user_id) == user_id,
                                     col(AccessGrant.source).in_(FREE_GRANT_SOURCES))


# A state the preflight tested that changed under the lock is a race; every other refusal is a refusal.
class ActivationOutcome(StrEnum):
    """What a writer did under the locks, in the three terms the route branches on."""
    # The grant was written.
    activated = "activated"
    # Another writer holds the slot, and the caller re-reads the winner's row.
    lost_race = "lost_race"
    # The write was impossible, and there is nothing to re-read.
    refused = "refused"


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

    async def lock_active_grants(self, user_id: UUID) -> list[AccessGrant]:
        """Lock and return every grant of `user_id` the one-active index sees, ascending by id."""
        # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
        statement = _active_grants_statement(user_id).with_for_update()
        return list((await self.session.exec(statement)).all())

    async def read_active_grants(self, user_id: UUID) -> list[AccessGrant]:
        """Return every grant of `user_id` the one-active index sees, ascending by id, taking no lock."""
        return list((await self.session.exec(_active_grants_statement(user_id))).all())

    async def holds_grant_of_source(self, user_id: UUID, source: AccessGrantSource) -> bool:
        """Whether `user_id` holds a grant of `source` at any status, taking no lock."""
        statement = _grants_of_source_statement(user_id, source)
        return (await self.session.exec(statement)).first() is not None

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
                                              evaluated_at: datetime) -> ActivationOutcome:
        """Take both lock tiers, then write the grant, its usage row and the identity marker."""
        grants = await self.lock_effective_grants(user_id, evaluated_at)
        for grant in grants:
            await self.lock_usage(grant.id)

        # A plain re-read, never `lock_identity_and_user`: a user-row lock ahead of the grant locks is forbidden.
        stored = await IdentitiesDB(self.session).resolve_existing(issuer=identity_row.issuer,
                                                                   subject=identity_row.subject)
        if stored is None or stored.provider is not IdentityProvider.anonymous:
            return ActivationOutcome.refused
        if len(grants) > 1:
            # A tripwire, not a recovery branch: a partial unique index makes it unreachable.
            raise MultipleEffectiveGrantsError(len(grants), user_id)
        if any(grant.source is AccessGrantSource.anonymous_device_grant for grant in grants):
            # The repeat under the lock, and the only branch here whose row is there to be read back.
            return ActivationOutcome.lost_race
        if grants or stored.free_grant_consumed_at is not None:
            return ActivationOutcome.refused
        if await self.has_prior_free_grant(user_id):
            # No conversion exists on this route, so no loser lands here and nothing is left to re-read.
            return ActivationOutcome.refused

        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.anonymous_device_grant,
                                starts_at=evaluated_at,
                                created_at=evaluated_at,
                                updated_at=evaluated_at)
        self.session.add(activated)
        self.session.add(UserMonthlyUsage(grant_id=activated.id,
                                          monthly_period=evaluated_at.strftime("%Y-%m"),
                                          monthly_used=0,
                                          created_at=evaluated_at,
                                          updated_at=evaluated_at))
        stored.free_grant_consumed_at = evaluated_at
        stored.native_claim_platform = NativeClaimProvider.ios_devicecheck
        stored.updated_at = evaluated_at

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return ActivationOutcome.lost_race
        return ActivationOutcome.activated

    async def activate_registered_account_grant(self, *,
                                                user_id: UUID,
                                                identity_row: ExternalIdentity,
                                                tier_id: str,
                                                evaluated_at: datetime) -> ActivationOutcome:
        """Take both lock tiers, re-decide the destination, and write it: a conversion, or a new grant."""
        # First and ascending by id: this set contains the effective one, so one grant-tier order holds.
        marked_active = await self.lock_active_grants(user_id)
        grants = await self.lock_effective_grants(user_id, evaluated_at)
        # The usage row is kept rather than discarded: the conversion carries the old counters across.
        locked_usage: dict[UUID, UserMonthlyUsage | None] = {}
        for grant in grants:
            locked_usage[grant.id] = await self.lock_usage(grant.id)

        # A plain re-read, never `lock_identity_and_user`: a user-row lock ahead of the grant locks is forbidden.
        stored = await IdentitiesDB(self.session).resolve_existing(issuer=identity_row.issuer,
                                                                   subject=identity_row.subject)
        # Tested positively, so a NULL or any future provider member is refused on this same branch.
        if stored is None or stored.provider not in (IdentityProvider.google, IdentityProvider.apple):
            return ActivationOutcome.refused

        held = [grant.source for grant in grants]
        if AccessGrantSource.registered_account_grant in held:
            # The repeat under the lock, and the one branch here whose row is there to be read back.
            return ActivationOutcome.lost_race
        if any(source is not AccessGrantSource.anonymous_device_grant for source in held):
            return ActivationOutcome.refused
        if len(grants) > 1:
            # A tripwire, not a recovery branch: a partial unique index makes it unreachable.
            raise MultipleEffectiveGrantsError(len(grants), user_id)
        superseded = grants[0] if grants else None
        # A row the one-active index sees and this window cannot: the insert below would be refused.
        if [grant for grant in marked_active if superseded is None or grant.id != superseded.id]:
            return ActivationOutcome.refused
        # History by source and status, never `free_grant_consumed_at`, which the conversion already carries.
        if superseded is None and await self.has_prior_free_grant(user_id):
            # The conversion race loser and nothing else: only a concurrent commit takes its locked row away.
            return ActivationOutcome.lost_race
        # The lifetime index's own question, which one revoked registered row is enough to answer.
        if await self.holds_grant_of_source(user_id, AccessGrantSource.registered_account_grant):
            return ActivationOutcome.refused

        carried = locked_usage.get(superseded.id) if superseded is not None else None
        if superseded is not None:
            superseded.status = AccessGrantStatus.expired
            superseded.ends_at = evaluated_at
            superseded.updated_at = evaluated_at
            # Flushed alone and first: the ORM emits inserts before updates, and the one-active index is per-statement.
            try:
                await self.session.flush()
            except IntegrityError as violation:
                # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
                if violation.orig.sqlstate != "23505":
                    # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                    raise
                return ActivationOutcome.lost_race

        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.registered_account_grant,
                                starts_at=evaluated_at,
                                created_at=evaluated_at,
                                updated_at=evaluated_at)
        self.session.add(activated)
        # The carried period and count are safe because the registered tier's allowance is the larger one.
        self.session.add(UserMonthlyUsage(
            grant_id=activated.id,
            monthly_period=evaluated_at.strftime("%Y-%m") if carried is None else carried.monthly_period,
            monthly_used=0 if carried is None else carried.monthly_used,
            created_at=evaluated_at,
            updated_at=evaluated_at))
        if stored.free_grant_consumed_at is None:
            # Set where unset: the conversion path already spent the slot and the instant it spent it is the record.
            stored.free_grant_consumed_at = evaluated_at
        stored.updated_at = evaluated_at

        # Only the flush is inside: the try holds the one statement that can raise, and nothing else.
        try:
            await self.session.flush()
        except IntegrityError as violation:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            if violation.orig.sqlstate != "23505":
                # Not a unique violation: a CHECK or a foreign key is a broken invariant, never a race this lost.
                raise
            return ActivationOutcome.lost_race
        return ActivationOutcome.activated
