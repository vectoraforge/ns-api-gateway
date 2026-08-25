"""Identity resolution: one query, four outcomes. The two account_unavailable arms do identical work."""
from dataclasses import dataclass

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    INTERNAL_ERROR,
    PREAUTH_IDENTITY_NOT_ALLOWED,
    ErrorClass,
)
from nativespeaker.api.models.auth import AuthEventResult
from nativespeaker.api.models.identities import ExternalIdentity, IdentityState
from nativespeaker.api.models.users import User


@dataclass(frozen=True, slots=True)
class Admit:
    """The caller is admitted, carrying the identity variant this request resolved to."""
    identity: LinkedIdentity | PreAuthIdentity


@dataclass(frozen=True, slots=True)
class Reject:
    """The client-visible error class, plus the internal result that never reaches the client."""
    error_class: ErrorClass
    result: AuthEventResult
    actor_issuer: str | None
    actor_subject: str | None


AdmissionDecision = Admit | Reject


async def resolve_identity(session: AsyncSession, *, issuer: str, subject: str,
                           allow_preauth: bool) -> AdmissionDecision:
    """Resolve a verified `(issuer, subject)` into one of the four outcomes, using a single query."""
    # Outer join: an identity row whose user_id resolves to nothing must stay distinct from no row.
    statement = (select(ExternalIdentity, User)
                 .join(User, col(ExternalIdentity.user_id) == col(User.id), isouter=True)
                 .where(col(ExternalIdentity.issuer) == issuer,
                        col(ExternalIdentity.subject) == subject))
    row = (await session.exec(statement)).first()

    if row is None:
        # Identity rows are never deleted, so no row can only mean this pair was never linked.
        if allow_preauth:  # only POST /auth/create-user passes True
            return Admit(PreAuthIdentity(issuer=issuer, subject=subject))
        return Reject(PREAUTH_IDENTITY_NOT_ALLOWED,
                      AuthEventResult.preauth_identity_not_allowed, issuer, subject)

    identity, user = row
    if user is None:
        # A broken link is unresolvable state: fail closed rather than read it as an unlinked pair.
        return Reject(INTERNAL_ERROR, AuthEventResult.internal_error, issuer, subject)
    # Positive tests, so a NULL or any future enum member fails closed on these same two branches.
    if identity.identity_state != IdentityState.active:
        return Reject(ACCOUNT_UNAVAILABLE, AuthEventResult.historical_identity, issuer, subject)
    if user.active is not True:
        return Reject(ACCOUNT_UNAVAILABLE, AuthEventResult.blocked_user, issuer, subject)
    return Admit(LinkedIdentity(user=user, identity=identity, issuer=issuer, subject=subject))
