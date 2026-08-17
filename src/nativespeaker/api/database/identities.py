"""Per-request identity resolution for the shared pre-handler barrier.

The barrier resolves a backend-verified `(issuer, subject)` here and nowhere else. Until the
schema slice introduces `core.external_identities`, the mapping lives on `core.users` and this
module reads it there; the four resolution outcomes the barrier acts on are unchanged.
"""

from typing import Any

from sqlalchemy import text

from nativespeaker.api.auth.barrier import ResolutionOutcome, ResolvedIdentity

# One row per verified subject. `active = false` is a blocked user; no row at all is a pre-auth
# identity that has not completed `create_user`.
SELECT_IDENTITY = text("""
    SELECT id, active
      FROM core.users
     WHERE jwt_sub = :subject
""")


class IdentityResolverDB:
    """Resolves the backend-verified `(issuer, subject)` through the identity tables."""

    # [impl->req~shared-prehandler-barrier~1]
    def __init__(self, session_factory: Any):
        self._session_factory = session_factory

    async def resolve(self, issuer: str, subject: str) -> ResolvedIdentity:
        """The four per-request identity-resolution outcomes. Identity comes from the verified
        claims alone: the only inputs are the issuer and subject the barrier verified."""
        async with self._session_factory() as session:
            result = await session.execute(SELECT_IDENTITY, {"subject": subject})
            row = result.first()
        if row is None:
            return ResolvedIdentity(outcome=ResolutionOutcome.pre_auth)
        if not row.active:
            return ResolvedIdentity(outcome=ResolutionOutcome.blocked_user, user_id=row.id)
        return ResolvedIdentity(outcome=ResolutionOutcome.linked,
                                user_id=row.id,
                                external_identity_id=row.id)
