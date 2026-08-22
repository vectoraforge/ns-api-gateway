"""§8.4 quota consumption -- the one place an allowance is resolved and spent.

**This module is a named seam (D-03).** Phase 38's `/auth/sync` imports it by name and must act on
the same grant state quota enforcement would independently act on at the same instant, so the
module path and the grant-selection predicate are contract, not implementation detail. The
selection itself lives in `GrantsDB.lock_effective_grants` rather than in this function, because
sync reads the same rows without consuming anything.

**The caller opens its own session and commits it (D-04).** `consume_quota` never opens or closes
one; `QuotaGate.charge` below does, using a short transaction that is committed and closed before
the provider call is made. It deliberately does not take FastAPI's `get_db` yield-dependency: that
commits after the handler returns, which would hold the grant row locks across the entire provider
round trip -- exactly what §8.4 and SHARED-INVARIANTS forbid.

**Nothing here mints entitlement.** No branch creates a `core.access_grants` row (grants originate
from Phases 41, 42 and 45) and no branch lazily mints a `core.user_monthly_usage` row for an
existing grant (D-09): a missing usage row is divergent stored state and fails closed as an
internal error, never as a free allowance. More than one effective grant is likewise an integrity
failure with no tie-break and no precedence ranking (D-10) -- there is no "pick the best grant"
path here and none may be added.

**A failed provider call is not refunded (D-11).** Consumption is committed immediately before the
provider call, so a request whose LLM call then fails has still spent its credit. That is a
decision, not an oversight: the alternative is holding the transaction open across the provider
round trip, and this product would rather lose one credit on a rare provider failure than
serialise every caller behind a network call.

**But a request the service refused itself is not charged at all (REBIND-06).** D-11's accepted
loss covers calls that reached the provider and failed there. It does not cover the service's own
rejections -- an unsupported language, a history limit, an unknown chat id, an open circuit, a full
queue -- every one of which is decided without a provider call. `QuotaGate.charge` runs as the
resilience layer's admission callback for exactly this reason: it fires only once the call is
certain, so no rejection upstream of it can cost a credit. Anything that can refuse a request must
stay upstream of that callback; a new rejection added downstream of it would silently reintroduce
the charge-for-nothing this exists to prevent.

**Lock order.** `GrantsDB` takes the grant rows `FOR UPDATE` ascending by grant id before anything
touches `core.user_monthly_usage` (SHARED-INVARIANTS:33). This module is the first implementation
of that order; Phases 41, 42 and 45 copy it.

**Difference from the `auth/identity.py` analog.** `resolve_identity` *returns* a rejection,
because its caller is ASGI middleware that must not raise. `consume_quota` runs inside a request
handler's own call stack, so it **raises** `ServiceError` subclasses and lets
`service_error_handler` format them. There is no decision object to inspect and no handler change
to make.
"""
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.database import GrantsDB
from nativespeaker.api.errors import (
    MissingUsageRowError,
    MultipleEffectiveGrantsError,
    QuotaExceededError,
    UnknownTierError,
)

logger = structlog.get_logger()


async def consume_quota(session: AsyncSession, *, user_id: UUID, evaluated_at: datetime,
                        route: str) -> None:
    """Spend one unit of `user_id`'s allowance, or raise. Returns nothing on success.

    `route` is the matched route's **path template** and is used only as a telemetry label. It is
    never a raw path, so cardinality stays bounded (`auth/telemetry.py:10-15`).
    """
    grants_db = GrantsDB(session)
    grants = await grants_db.lock_effective_grants(user_id, evaluated_at)

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

    if len(grants) > 1:
        # §8.4 step 1's "log and fail closed, no tie-break" (D-10). A **tripwire, not a recovery
        # branch**: `ix_access_grants_one_active_per_user`
        # (migrations/20260818_01_initial-release.sql:458-460) is a plain non-deferrable partial
        # unique index permitting one `status='active'` row per user, and the effective-grant
        # predicate above is a strict subset of that, so this state is structurally unreachable.
        # It is asserted anyway so that dropping the index or widening the predicate fails loudly
        # instead of silently picking a grant -- which is the exact tie-break §8.4 forbids, and
        # what a `LIMIT 1` on the select would have made invisible.
        #
        # Flagged conflict, honoured in both directions: the migration comment at :455-457 says
        # not to write an application rejection path for this index. There is none here -- no
        # recovery, no precedence ranking, no repair. There is only an assertion that cannot pass
        # silently. Do not "resolve" the conflict by deleting the branch.
        logger.error("quota_integrity_failure", branch="multiple_effective_grants", route=route)
        raise MultipleEffectiveGrantsError(len(grants), user_id)

    grant = grants[0]

    # §8.4 step 2. Second in the lock order, always after the grant rows (SHARED-INVARIANTS:33).
    usage = await grants_db.lock_usage(grant.id)
    if usage is None:
        # §8.4 step 3: fail closed, never lazily mint (D-09). Phases 41, 42 and 45 write a grant
        # and its usage row in one transaction, so a grant without one is a failed write -- a
        # broken invariant, not an entitlement state. Minting it here would hand out a fresh
        # allowance every time the invariant broke, and would hide the break while doing it.
        #
        # 500 rather than 503: `service_unavailable` promises the caller that retrying soon will
        # work, and nothing repairs this state -- SHARED-INVARIANTS deletes background healers --
        # so that advice would be false.
        logger.error("quota_integrity_failure", branch="missing_usage_row", route=route)
        raise MissingUsageRowError(grant.id)

    # The only place the period string is derived, and it comes from the instant the barrier
    # captured for this request (D-06), never from the system clock -- so the grant cannot be
    # selected against one instant and its period computed against another. The column is free
    # text in YYYY-MM (UTC calendar month) with NO format CHECK in the database
    # (migrations/20260818_01_initial-release.sql:574-576); do not invent one here either.
    period = evaluated_at.strftime("%Y-%m")

    if usage.monthly_period != period:
        # §8.4 step 4, the lazy rollover -- and it happens **before** the allowance comparison, so
        # last month's exhausted count cannot refuse this month's first request. It runs inside the
        # same locked transaction as the increment below, so the reset and the charge commit
        # together or not at all; no reader can observe a row that was reset but never charged.
        usage.monthly_used = 0
        usage.monthly_period = period

    allowance = await grants_db.monthly_credits(grant.tier_id)
    if allowance is None:
        # The tier id comes from the locked grant row, never from the request, and a foreign key
        # makes a dangling one unreachable -- so this is the same class of tripwire as the
        # multi-grant branch. Failing closed is the point: reading a missing tier as allowance 0
        # is an unexplained 429 for a paying customer, and reading it as unbounded is a free
        # service. Neither may be inferred from an absent row.
        logger.error("quota_integrity_failure", branch="unknown_tier", route=route)
        raise UnknownTierError(grant.tier_id, grant.id)

    # §8.4 step 5. Floored at zero so `remaining` can never go negative: a stored count above the
    # allowance -- reachable only by a future tier downgrade, which no phase ships yet -- is
    # ordinary exhaustion, not a broken invariant, because unlike a missing usage row it implies
    # no failed write. Without the floor it would produce a negative count here and a second
    # charge below.
    remaining = max(allowance - usage.monthly_used, 0)
    if remaining == 0:
        # Raised **before** the increment: a request the service refused must never be charged.
        # Same closed-set labels as the no-grant branch above.
        logger.warning("quota_rejected", branch="allowance_exhausted", route=route)
        raise QuotaExceededError("The allowance for the current period is used up")

    # The charge. `usage` was loaded through this session, so it is already tracked and no
    # `session.add` is needed -- the caller's commit is what makes both this and any rollover
    # above durable. `updated_at` is stamped from the captured instant for the same reason the
    # period is: this module reads no clock.
    usage.monthly_used += 1
    usage.updated_at = evaluated_at


class QuotaGate:
    """One caller's ability to spend, bound to one request. Any consumer of the allowance holds one.

    **Why this is an object and not a FastAPI dependency.** Consumption used to run as a decorator
    dependency (`require_quota_*`), which fixed *when* the charge happened: after admission, before
    the handler body, and therefore before every rejection the handler itself performs. Five such
    rejections existed across the two gated routes -- an unsupported language, both history limits,
    an unknown chat id, and local backpressure -- and each one charged a caller for work the
    service refused without ever calling the provider (REBIND-06). A dependency cannot see any of
    them, because they have not happened yet when it runs.

    Moving the charge to a call site does not make it the caller's business to remember: `charge`
    is passed to the resilience layer as its admission callback, so it fires at the one instant the
    provider call is certain, and nothing downstream of it can reject the request for free.

    **It is not owned by any one service.** `ChatService` is merely the first consumer. A future
    service that spends the same allowance takes a `QuotaGate` the same way rather than importing
    `ChatService` or reimplementing the session handling; `consume_quota` below stays the single
    function that decides what a spend means.

    **The session is still its own (D-04).** `charge` opens, commits and closes a short session per
    call, so no grant or usage row lock is held across the provider round trip. That constraint is
    unchanged -- only the moment the transaction runs has moved later.
    """

    def __init__(self,
                 session_factory: async_sessionmaker | Callable[[], AsyncSession],
                 *,
                 evaluated_at: datetime,
                 route: str) -> None:
        self._session_factory = session_factory
        # Both come from the `RequestContext` the barrier captured (D-06), and are fixed for the
        # life of this object. Binding them here rather than taking them per call is what lets a
        # consumer pass `charge` itself as a zero-argument callback.
        self._evaluated_at = evaluated_at
        self._route = route

    async def charge(self, user_id: UUID) -> None:
        """Spend one unit of `user_id`'s allowance, or raise. Commits on success.

        Raises exactly what `consume_quota` raises -- `QuotaExceededError` for the two business
        refusals, the three `INTERNAL_ERROR` classes for divergent stored state -- so a caller
        needs no error translation and `service_error_handler` formats them as it always has.
        """
        async with self._session_factory() as session:
            try:
                await consume_quota(session,
                                    user_id=user_id,
                                    evaluated_at=self._evaluated_at,
                                    route=self._route)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
