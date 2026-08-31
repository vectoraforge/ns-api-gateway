"""The consuming transaction for `create_user`: one function, one transaction, every input a parameter."""
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import (
    BlockedUser,
    HistoricalIdentity,
    IdentityAlreadyLinked,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState


async def create_user(session: AsyncSession, *,
                      identity: Identity,
                      evaluated_at: datetime,
                      provider: IdentityProvider,
                      provider_uid: str | None,
                      email: str | None) -> UUID:
    """Return the new user's id, or raise the rejection the transaction earned."""
    identities_db = IdentitiesDB(session)
    existing = await identities_db.resolve_existing(issuer=identity.issuer, subject=identity.subject)

    if existing is not None:
        # The prepare-time pre-check is racy, so this resolution is the one that decides.
        await _reject_existing_identity(identities_db, existing)

    return await identities_db.insert_account(evaluated_at=evaluated_at,
                                              identity=identity,
                                              provider=provider,
                                              provider_uid=provider_uid,
                                              email=email)


async def _reject_existing_identity(identities_db: IdentitiesDB,
                                    existing: ExternalIdentity) -> NoReturn:
    """Raise what an already-present identity row earned. No mutation, and every test fails closed."""
    if existing.identity_state != IdentityState.active:
        raise HistoricalIdentity

    user = await identities_db.user_by_id(existing.user_id)
    if user is None or user.active is not True:
        raise BlockedUser
    raise IdentityAlreadyLinked()
