"""Per-request identity resolution for the shared pre-handler barrier.

The barrier resolves a backend-verified `(issuer, subject)` here and nowhere else. The mapping
lives on `core.external_identities`, which the applied schema keys by `(issuer, subject)`; the
four resolution outcomes the barrier acts on are read from that row and the user row it owns.
"""

from typing import Any

from sqlalchemy import text

from nativespeaker.api.auth.barrier import ResolutionOutcome, ResolvedIdentity
from nativespeaker.api.auth.external_identities import IdentityState

# One row per verified `(issuer, subject)`. `identity_state = 'historical'` is a retired
# identity, `users.active = false` a blocked user, and no row at all a pre-auth identity that
# has not completed `create_user`.
SELECT_IDENTITY = text("""
    SELECT ei.id AS external_identity_id,
           ei.identity_state AS identity_state,
           u.id AS user_id,
           u.active AS active
      FROM core.external_identities AS ei
      JOIN core.users AS u ON u.id = ei.user_id
     WHERE ei.issuer = :issuer AND ei.subject = :subject
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
            result = await session.execute(SELECT_IDENTITY,
                                           {"issuer": issuer, "subject": subject})
            row = result.first()
        if row is None:
            return ResolvedIdentity(outcome=ResolutionOutcome.pre_auth)
        if str(row.identity_state) == IdentityState.historical:
            return ResolvedIdentity(outcome=ResolutionOutcome.historical_identity,
                                    user_id=row.user_id,
                                    external_identity_id=row.external_identity_id)
        if not row.active:
            return ResolvedIdentity(outcome=ResolutionOutcome.blocked_user,
                                    user_id=row.user_id,
                                    external_identity_id=row.external_identity_id)
        return ResolvedIdentity(outcome=ResolutionOutcome.linked,
                                user_id=row.user_id,
                                external_identity_id=row.external_identity_id)
