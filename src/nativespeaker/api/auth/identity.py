"""The identity a verified credential resolves to, and the single query that resolves it."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.errors import (
    BlockedUser,
    HistoricalIdentity,
    IdentityUnresolvable,
    PreAuthIdentityNotAllowed,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityState
from nativespeaker.api.tables.users import User


@dataclass(frozen=True, slots=True)
class Identity:
    """A verified `(issuer, subject)` and the rows it resolved to.

    Both row fields are `None` together when the pair is linked to no account.
    """
    issuer: str
    subject: str
    user: User | None = None
    identity: ExternalIdentity | None = None


@dataclass(frozen=True, slots=True)
class RequestContext:
    """The request-scoped values later phases read and never recompute."""
    identity: Identity
    route: str
    evaluated_at: datetime
    attempt_id: UUID


async def resolve_identity(session: AsyncSession, *, issuer: str, subject: str,
                           allow_preauth: bool) -> Identity:
    """Resolve a verified `(issuer, subject)` or raise the rejection it earned, using a single query."""
    # Outer join: an identity row whose user_id resolves to nothing must stay distinct from no row.
    statement = (select(ExternalIdentity, User)
                 .join(User, col(ExternalIdentity.user_id) == col(User.id), isouter=True)
                 .where(col(ExternalIdentity.issuer) == issuer,
                        col(ExternalIdentity.subject) == subject))
    row = (await session.exec(statement)).first()

    if row is None:
        # Identity rows are never deleted, so no row can only mean this pair was never linked.
        if allow_preauth:  # only POST /auth/create-user passes True
            return Identity(issuer=issuer, subject=subject)
        raise PreAuthIdentityNotAllowed

    identity, user = row
    if user is None:
        # A broken link is unresolvable state: fail closed rather than read it as an unlinked pair.
        raise IdentityUnresolvable
    # Positive tests, so a NULL or any future enum member fails closed on these same two branches.
    if identity.identity_state != IdentityState.active:
        raise HistoricalIdentity
    if user.active is not True:
        raise BlockedUser
    return Identity(issuer=issuer, subject=subject, user=user, identity=identity)
