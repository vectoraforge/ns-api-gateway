"""The consuming transaction for `create_user`: one function, one transaction, every input a parameter."""
from datetime import datetime
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.identity import Identity
from nativespeaker.api.errors import (
    BlockedUser,
    HistoricalIdentity,
    IdentityAlreadyLinked,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.purchases import PurchaseProvider, StorePurchaseToken
from nativespeaker.api.tables.users import User


async def create_user(session: AsyncSession, *,
                      identity: Identity,
                      evaluated_at: datetime,
                      provider: IdentityProvider,
                      provider_uid: str | None,
                      email: str | None) -> UUID:
    """Return the new user's id, or raise the rejection the transaction earned."""
    existing = await resolve_existing_identity(session, issuer=identity.issuer, subject=identity.subject)

    if existing is not None:
        # The prepare-time pre-check is racy, so this resolution is the one that decides.
        await _reject_existing_identity(session, existing)

    return await _insert_account(session,
                                 evaluated_at=evaluated_at,
                                 identity=identity,
                                 provider=provider,
                                 provider_uid=provider_uid,
                                 email=email)


async def resolve_existing_identity(session: AsyncSession, *,
                                    issuer: str, subject: str) -> ExternalIdentity | None:
    """The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."""
    statement = select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                               col(ExternalIdentity.subject) == subject)
    return (await session.exec(statement)).first()


async def _reject_existing_identity(session: AsyncSession,
                                    existing: ExternalIdentity) -> NoReturn:
    """Raise what an already-present identity row earned. No mutation, and every test fails closed."""
    if existing.identity_state != IdentityState.active:
        raise HistoricalIdentity

    user = (await session.exec(select(User).where(col(User.id) == existing.user_id))).first()
    if user is None or user.active is not True:
        raise BlockedUser
    raise IdentityAlreadyLinked()


async def _insert_account(session: AsyncSession, *,
                          evaluated_at: datetime,
                          identity: Identity,
                          provider: IdentityProvider,
                          provider_uid: str | None,
                          email: str | None) -> UUID:
    """Insert the user, its identity row and its purchase tokens, and return the new user's id."""
    try:
        user = User(email=email,
                    registered_at=None if provider is IdentityProvider.anonymous else evaluated_at,
                    created_at=evaluated_at,
                    updated_at=evaluated_at)
        session.add(user)
        await session.flush()

        session.add(ExternalIdentity(user_id=user.id,
                                     issuer=identity.issuer,
                                     subject=identity.subject,
                                     provider=provider,
                                     # NULL for anonymous, never a sentinel: the CHECK requires it.
                                     provider_uid=provider_uid,
                                     identity_state=IdentityState.active,
                                     created_at=evaluated_at,
                                     updated_at=evaluated_at))

        # One per store, minted eagerly. A fresh `uuid4()` derived from nothing, so it correlates nothing.
        for store in PurchaseProvider:
            session.add(StorePurchaseToken(user_id=user.id,
                                           provider=store,
                                           identity_value=str(uuid4()),
                                           created_at=evaluated_at))

        await session.flush()
        return user.id
    except IntegrityError as conflict:
        raise IdentityAlreadyLinked() from conflict
