"""Per-request identity resolution for the shared pre-handler barrier.

The barrier resolves a backend-verified `(issuer, subject)` here and nowhere else. The mapping
lives on `core.external_identities`, which the applied schema keys by `(issuer, subject)`; the
four resolution outcomes the barrier acts on are read from that row and the user row it owns.
"""

from typing import Any

from sqlalchemy import text

from nativespeaker.api.auth.barrier import ResolutionOutcome, ResolvedIdentity
from nativespeaker.api.auth.external_identities import IdentityState
from nativespeaker.api.auth.operations import IdentityProvider

# One row per verified `(issuer, subject)`. `identity_state = 'historical'` is a retired
# identity, `users.active = false` a blocked user, and no row at all a pre-auth identity that
# has not completed `create_user`. The stored `provider` and the user's `registered_at` are read
# with them, because a linked outcome carries both onto the request context.
SELECT_IDENTITY = text("""
    SELECT ei.id AS external_identity_id,
           ei.identity_state AS identity_state,
           ei.provider AS provider,
           u.id AS user_id,
           u.active AS active,
           u.registered_at AS registered_at
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
        """The four per-request identity-resolution outcomes, and exactly those four. Identity
        comes from the verified claims alone: the only inputs are the issuer and subject the
        barrier verified.

        Resolution is a positive test. An identity is admitted only where the matching row's
        `identity_state` is exactly `active` and the linked user's `active` is exactly TRUE; every
        other combination rejects. A malformed or unexpected lifecycle value — `NULL`, an
        unrecognized state, an `active` column that is not exactly TRUE — therefore never
        authorizes a request, and it never falls through to the pre-auth outcome either, because
        only the absence of a row produces that one.
        """
        # [impl->req~sessions-barrier-positive-admission-test~1]
        # [impl->req~sessions-exactly-four-resolution-outcomes~1]
        # [impl->req~sessions-malformed-lifecycle-never-authorizes~1]
        async with self._session_factory() as session:
            result = await session.execute(SELECT_IDENTITY,
                                           {"issuer": issuer, "subject": subject})
            row = result.first()
        # 1. No matching row: pre-auth (unlinked). Rows are never deleted, so this can only mean
        # this `(issuer, subject)` was never linked.
        # [impl->req~sessions-resolution-outcome-01~1]
        if row is None:
            return ResolvedIdentity(outcome=ResolutionOutcome.pre_auth)
        # 2. A matching row whose `identity_state` is anything other than exactly `active` —
        # `historical`, `NULL`, or an unrecognized value — rejects on every authenticated route,
        # the pre-auth-declared `create-user` phases included. It stays distinct from unlinked.
        # [impl->req~sessions-resolution-outcome-02~1]
        if str(row.identity_state) != IdentityState.active:
            return ResolvedIdentity(outcome=ResolutionOutcome.historical_identity,
                                    user_id=row.user_id,
                                    external_identity_id=row.external_identity_id)
        # 3. `active IS NOT TRUE` on the linked user rejects as a blocked user on every route.
        # [impl->req~sessions-resolution-outcome-03~1]
        if row.active is not True:
            return ResolvedIdentity(outcome=ResolutionOutcome.blocked_user,
                                    user_id=row.user_id,
                                    external_identity_id=row.external_identity_id)
        # 4. Exactly `active` and exactly TRUE: the identity is linked, and the resolved rows
        # travel to the request context with the stored `provider` and the user's `registered_at`.
        # A stored provider outside the enumeration is a corrupt row: it fails closed here rather
        # than being admitted with an unknown classification.
        # [impl->req~sessions-resolution-outcome-04~1]
        return ResolvedIdentity(outcome=ResolutionOutcome.linked,
                                user_id=row.user_id,
                                external_identity_id=row.external_identity_id,
                                provider=IdentityProvider(str(row.provider)),
                                registered_at=row.registered_at)
