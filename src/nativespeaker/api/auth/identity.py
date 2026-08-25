"""§1.3 identity resolution -- one query, one code path, four outcomes.

Resolution is a **positive test**: a caller is admitted only when the matching
`core.external_identities` row's `identity_state` is exactly `active` **and** the linked
`core.users.active` is exactly `True`. Everything else rejects, and nothing ever falls through to
pre-auth. The barrier decides admission here; it never leaves a result for a handler to re-check.

**The anti-oracle guarantee is structural (D-13).** Both `account_unavailable` branches --
`historical_identity` and `blocked_user` -- are reached from the *same* result of the *same*
single statement, through the same code path. Neither branch issues a query, a lookup, or a
network call the other skips, so no observable work distinguishes a retired identity from a
blocked user. Timing normalization, padding, and constant-time delays are **deliberately absent**:
D-13 rejects them for this product, on the reasoning that a timing oracle distinguishing "retired"
from "blocked" on a sub-$5/month subscription buys an attacker nothing worth per-rejection
latency. The omission is a decision, not an oversight -- do not "fix" it without revisiting D-13.

Two comparisons are written in their strict form on purpose:

- `identity.identity_state != IdentityState.active` rather than `== IdentityState.historical`, so
  a NULL and any future enum member fail closed on the same branch instead of reaching a caller;
- `user.active is not True` rather than `not user.active`, so a non-boolean value cannot be
  truthy-coerced into an admission.

The join is an **outer** one. An identity row whose `user_id` resolves to nothing is a distinct
condition from no identity row at all: the first is unresolvable state and fails closed as an
internal error, the second is an unlinked pair. An inner join would silently collapse the two and
read a broken link as a fresh identity.
"""
from dataclasses import dataclass

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.auth.registry import RouteMetadata
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
    """The barrier may dispatch: the §1.4 identity variant this request carries."""
    identity: LinkedIdentity | PreAuthIdentity


@dataclass(frozen=True, slots=True)
class Reject:
    """The barrier must answer: the client-visible class, and the internal result that never is.

    `actor_issuer` and `actor_subject` are populated on **every** branch reachable here, because
    every one of them is reached only after the token was verified. `invalid_external_jwt` is the
    sole result that may carry no actor at all; each result below has one, and a NULL actor here
    would mean a rejection had been classified before the token was verified.
    """
    error_class: ErrorClass
    result: AuthEventResult
    actor_issuer: str | None
    actor_subject: str | None


AdmissionDecision = Admit | Reject


async def resolve_identity(session: AsyncSession, *, issuer: str, subject: str,
                           meta: RouteMetadata) -> AdmissionDecision:
    """Resolve a verified `(issuer, subject)` into one of the four §1.3 outcomes.

    Exactly one statement is issued per call, whatever the outcome.
    """
    statement = (select(ExternalIdentity, User)
                 .join(User, col(ExternalIdentity.user_id) == col(User.id), isouter=True)
                 .where(col(ExternalIdentity.issuer) == issuer,
                        col(ExternalIdentity.subject) == subject))
    row = (await session.exec(statement)).first()

    if row is None:
        # Outcomes 1 and 1'. Identity rows are never deleted, so "no matching row" can only mean
        # this pair was never linked -- an administratively retired identity still has a row and
        # takes the branch below, and can therefore never surface as a fresh identity here.
        if meta.preauth_callable:
            return Admit(PreAuthIdentity(issuer=issuer, subject=subject))
        return Reject(PREAUTH_IDENTITY_NOT_ALLOWED,
                      AuthEventResult.preauth_identity_not_allowed, issuer, subject)

    identity, user = row
    if user is None:
        # Unresolvable stored state. Fail closed -- never invent, reassign, merge, or repair an
        # identity row inline, and never read the broken link as an unlinked pair.
        return Reject(INTERNAL_ERROR, AuthEventResult.internal_error, issuer, subject)
    if identity.identity_state != IdentityState.active:
        return Reject(ACCOUNT_UNAVAILABLE, AuthEventResult.historical_identity, issuer, subject)
    if user.active is not True:
        return Reject(ACCOUNT_UNAVAILABLE, AuthEventResult.blocked_user, issuer, subject)
    return Admit(LinkedIdentity(user=user, identity=identity, issuer=issuer, subject=subject))
