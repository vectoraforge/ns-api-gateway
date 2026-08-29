"""Identity resolution: one query, four outcomes. The two account_unavailable arms do identical work."""
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.auth.exceptions import IdentityUnresolvable, PreAuthIdentityNotAllowed
from nativespeaker.api.errors import BlockedUser, HistoricalIdentity
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityState
from nativespeaker.api.tables.users import User


async def resolve_identity(session: AsyncSession, *, issuer: str, subject: str,
                           allow_preauth: bool) -> LinkedIdentity | PreAuthIdentity:
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
            return PreAuthIdentity(issuer=issuer, subject=subject)
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
    return LinkedIdentity(user=user, identity=identity, issuer=issuer, subject=subject)
