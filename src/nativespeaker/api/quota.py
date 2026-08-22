"""§8.4 quota consumption -- the one place an allowance is resolved and spent.

**This module is a named seam (D-03).** Phase 38's `/auth/sync` imports it by name and must act on
the same grant state quota enforcement would independently act on at the same instant, so the
module path and the grant-selection predicate are contract, not implementation detail. The
selection itself lives in `GrantsDB.lock_effective_grants` rather than in this function, because
sync reads the same rows without consuming anything.

**The caller opens its own session and commits it (D-04).** `consume_quota` never opens or closes
one; `require_quota` does, in `app/dependencies.py`, using a short transaction that is committed
and closed *before* the handler body is entered. It deliberately does not take FastAPI's
`get_db` yield-dependency: that commits after the handler returns, which would hold the grant row
locks across the entire provider round trip -- exactly what §8.4 and SHARED-INVARIANTS forbid.

**Nothing here mints entitlement.** No branch creates a `core.access_grants` row (grants originate
from Phases 41, 42 and 45) and no branch lazily mints a `core.user_monthly_usage` row for an
existing grant (D-09): a missing usage row is divergent stored state and fails closed as an
internal error, never as a free allowance. More than one effective grant is likewise an integrity
failure with no tie-break and no precedence ranking (D-10) -- there is no "pick the best grant"
path here and none may be added.

**A failed provider call is not refunded (D-11).** Consumption is committed before the handler
runs, so a request whose LLM call then fails has still spent its credit. That is a decision, not
an oversight: the alternative is holding the transaction open across the provider round trip, and
this product would rather lose one credit on a rare provider failure than serialise every caller
behind a network call.

**Lock order.** `GrantsDB` takes the grant rows `FOR UPDATE` ascending by grant id before anything
touches `core.user_monthly_usage` (SHARED-INVARIANTS:33). This module is the first implementation
of that order; Phases 41, 42 and 45 copy it.

**Difference from the `auth/identity.py` analog.** `resolve_identity` *returns* a rejection,
because its caller is ASGI middleware that must not raise. `consume_quota` runs inside a FastAPI
dependency, so it **raises** `ServiceError` subclasses and lets `service_error_handler` format
them. There is no decision object to inspect and no handler change to make.
"""
from datetime import datetime
from uuid import UUID

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.database import GrantsDB
from nativespeaker.api.errors import QuotaExceededError

logger = structlog.get_logger()


async def consume_quota(session: AsyncSession, *, user_id: UUID, evaluated_at: datetime,
                        route: str) -> None:
    """Spend one unit of `user_id`'s allowance, or raise. Returns nothing on success.

    `route` is the matched route's **path template** and is used only as a telemetry label. It is
    never a raw path, so cardinality stays bounded (`auth/telemetry.py:10-15`).
    """
    grants = await GrantsDB(session).lock_effective_grants(user_id, evaluated_at)

    if not grants:
        # §8.4 step 1 routes "no effective grant" to an allowance of 0, and step 5 routes an
        # allowance of 0 to the existing quota-exceeded contract -- so this is the spec's own
        # answer, read across two steps (D-08). `QuotaExceededError` is reused verbatim: `ErrorCode`
        # is closed and `assert_registry_total()` fails boot on a mismatch, so no class is
        # registered here.
        #
        # Labels come from closed sets only: a fixed branch name and the route path template.
        # Never a grant id, a user id, a subject, or a raw path. `record_rejection` is deliberately
        # NOT called and `AuthEventResult` is deliberately NOT widened -- its 44 values are pinned
        # by migrations/20260818_01_initial-release.sql:84-88, and reusing it here would need
        # either a non-member string or a forbidden enum widening.
        logger.warning("quota_rejected", branch="no_effective_grant", route=route)
        raise QuotaExceededError("No effective grant for this user")

    # ---------------------------------------------------------------------------
    # §8.4 steps 2-4 land in plan 36-04: locking the usage row in the same ascending order,
    # failing closed on a missing one (D-09), the lazy period rollover, the allowance arithmetic
    # against `core.access_tiers.monthly_credits`, the >1-effective-grant tripwire (D-10), and the
    # increment itself.
    #
    # Until then a caller holding an effective grant passes this gate **uncharged**: nothing reads
    # or writes `core.user_monthly_usage` yet. That gap is deliberate and is the stricter of the
    # two possible incomplete states -- no row is created, so D-09's never-lazily-mint rule cannot
    # be violated by an unfinished increment. Do not stand the steps up with a permissive branch.
    # ---------------------------------------------------------------------------
