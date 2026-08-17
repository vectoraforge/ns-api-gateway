"""Quota admission control and the lazy monthly rollover sequence.

Two independent controls run on a quota-checked business request, in this order. First the
configured `quota_checked_request` backend admission limit, keyed by the authenticated internal
`core.users.id` — an operational bound on how often one user may drive database quota mutation
work, and no part of monthly entitlement. Then the rollover sequence itself: lock the effective
grant, lock its usage row, roll the month over if it has turned, compute the allowance from the
grant's tier, and consume one credit if any remains.

The whole thing runs inside the request that spends the credit. No background job, no scheduled
sweep, and no retry loop of its own: a transaction the database aborts under contention fails,
and the client's next request is the natural retry.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from nativespeaker.api.auth.locks import LockingPath, LockLedger
from nativespeaker.api.exceptions import QuotaExceededError
from nativespeaker.api.quota.grants import (
    EffectiveTier,
    GrantRow,
    authorizes,
    effective_tier,
)
from nativespeaker.api.quota.usage import (
    assert_grants_no_access,
    needs_rollover,
    period_of,
    require_usage_row,
)
from nativespeaker.api.ratelimit.config import RateLimitsConfig
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import AdmissionLedger, ExpensiveStep
from nativespeaker.api.ratelimit.rejection import AdmissionRejected, admission_rejection


class QuotaSequenceError(RuntimeError):
    """The rollover sequence was about to run out of its fixed order or write something that is
    not usage state."""


# The one backend admission entry this split configures, and its key policy. The entry's policy
# values and key policy are defined in `08-rate-limits-and-admission-control.md`; nothing here
# restates the concrete limit.
# [impl->req~quota-admission-keyed-by-user-id~1]
QUOTA_ADMISSION_ENTRY = "quota_checked_request"
QUOTA_ADMISSION_KEY_POLICY: tuple[KeyComponent, ...] = (KeyComponent.user,)

# Costed limits for individual product features that perform expensive model or provider work
# after quota admission belong in those feature-specific specs. This split configures exactly
# one admission entry and no per-feature entry of its own.
# [impl->req~quota-feature-costed-limits-out-of-scope~1]
QUOTA_ADMISSION_ENTRIES: frozenset[str] = frozenset({QUOTA_ADMISSION_ENTRY})

# Quota enforcement requires no background job: no scheduled rollover, no expiry sweep, no
# reconciliation task. Every state change happens on the request that needs it.
# [impl->req~quota-no-background-job~1]
QUOTA_BACKGROUND_JOBS: frozenset[str] = frozenset()

# What the monthly reset may write. Usage state only: introductory entitlement is a grant, and
# a counter reset is not one.
ROLLOVER_WRITE_COLUMNS: frozenset[str] = frozenset({
    "monthly_period", "monthly_used", "updated_at"})


def assert_no_background_job(scheduled: Iterable[str] = ()) -> None:
    """Quota enforcement must not require a background job."""
    # [impl->req~quota-no-background-job~1]
    offending = sorted(set(scheduled) | QUOTA_BACKGROUND_JOBS)
    if offending:
        raise QuotaSequenceError(
            f"{offending} would make quota enforcement depend on a background job; the rollover "
            "is lazy and happens on the first quota-checked request of the new month")


def assert_admission_key_policy(config: RateLimitsConfig) -> None:
    """The admission limit is keyed by the authenticated internal `core.users.id`. The named
    entry lives in the application configuration file; this checks only that its key policy is
    the one this file depends on."""
    # [impl->req~quota-admission-keyed-by-user-id~1]
    entry = config.entries.get(QUOTA_ADMISSION_ENTRY)
    if entry is None:
        raise QuotaSequenceError(f"{QUOTA_ADMISSION_ENTRY} is not a configured entry")
    if entry.policy != QUOTA_ADMISSION_KEY_POLICY:
        raise QuotaSequenceError(
            f"{QUOTA_ADMISSION_ENTRY} keys on the authenticated internal core.users.id alone")


def rollover_values(period: str,
                    *,
                    now: datetime,
                    extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Step 4's write: advance `monthly_period` and reset `monthly_used` to `0`, and touch
    nothing else. Introductory entitlement is represented by a grant and is not conflated with
    `monthly_used` initialization, so no grant, tier or entitlement column rides along."""
    # [impl->req~quota-rollover-step-04~1]
    # [impl->req~quota-introductory-entitlement-is-a-grant~1]
    offending = sorted(extra or {})
    if offending:
        raise QuotaSequenceError(
            f"the monthly reset writes usage state only; {offending} is entitlement, and "
            "entitlement is a grant")
    assert_grants_no_access()
    return {"monthly_period": period, "monthly_used": 0, "updated_at": now}


def remaining_credits(allowance: int, monthly_used: int) -> int:
    """Step 6: `remaining = max(0, effective_allowance - monthly_used)`.

    The floor at zero is the general rule wherever remaining is computed or enforced. The
    tier-sizing invariant keeps it from firing at conversion; it still defends a mid-period tier
    price change, an operator edit to tier sizes, a manual adjustment or a future paid-to-cheaper
    downgrade, degrading a missed invariant violation to zero remaining until rollover rather
    than letting negative-value arithmetic leak elsewhere.
    """
    # [impl->req~quota-rollover-step-06~1]
    return max(0, allowance - monthly_used)


def quota_admission(ledger: AdmissionLedger,
                    *,
                    user_id: UUID,
                    decision: LimitDecision) -> None:
    """Apply the configured `quota_checked_request` backend admission limit, keyed by the
    authenticated internal `core.users.id`, before any database quota mutation begins.

    A request that exceeds the limit is rejected here — before the rollover writes, before any
    `core.user_monthly_usage` row is touched, and before the usage increment.
    """
    # [impl->req~quota-admission-before-quota-mutation~1]
    # [impl->req~quota-admission-keyed-by-user-id~1]
    if decision.limiter not in QUOTA_ADMISSION_ENTRIES:
        raise QuotaSequenceError(f"{decision.limiter} is not this path's admission entry")
    if not isinstance(user_id, UUID):
        raise QuotaSequenceError(
            "quota admission is keyed by the authenticated internal core.users.id")
    ledger.evaluate(QUOTA_ADMISSION_ENTRY, QUOTA_ADMISSION_KEY_POLICY, allowed=decision.allowed)
    if not decision.allowed:
        raise admission_rejection(decision)


@dataclass(frozen=True, slots=True)
class QuotaConsumption:
    """What the sequence decided for one request."""
    grant_id: UUID
    monthly_period: str
    allowance: int
    monthly_used: int
    remaining: int
    rolled_over: bool


class QuotaStore(Protocol):
    """The four statements the sequence takes against the database, in this order, plus the
    commit that ends the sequence's own transaction and releases its two locks."""

    async def locked_grant_rows(self, user_id: UUID,
                                now: datetime) -> Sequence[GrantRow]: ...

    async def locked_usage_row(self, grant_id: UUID) -> tuple[str, int] | None: ...

    async def write_rollover(self, grant_id: UUID, values: Mapping[str, Any]) -> None: ...

    async def increment_usage(self, grant_id: UUID, period: str) -> None: ...

    async def commit(self) -> None: ...


async def consume_quota(store: QuotaStore,
                        *,
                        user_id: UUID,
                        ledger: AdmissionLedger,
                        now: datetime | None = None) -> QuotaConsumption:
    """The rollover sequence, on each quota-checked request, after quota admission has passed.

    Grant lock first, usage lock second, under the shared grant-then-usage lock order, so a
    restore for the same user queues briefly behind this transaction instead of deadlocking with
    it. The two locks are held for these few statements and released at commit, no external call
    is made while they are held, and there is no retry loop.

    The commit is this sequence's own, taken before it returns: the request handler's outbound
    model or provider call runs after the locking transaction has ended, never inside it. Leaving
    the commit to the request-scoped session's finalizer would hold both row locks across that
    call, which is precisely the transaction shape this sequence does not share with restore.
    """
    # [impl->req~quota-rollover-after-admission~1]
    # One captured evaluation time drives grant selection, the period computation and the usage
    # read, so behavior at `ends_at` and at a month boundary is deterministic within a request.
    # [impl->req~quota-no-future-dating-lazy-expiry-flip~2]
    moment = now or datetime.now(UTC)

    # Quota admission is an operational request admission control, not entitlement: holding
    # entitlement exempts nothing, so the ledger refuses the first locking statement below
    # unless the admission entry was already evaluated for this request.
    # [impl->req~quota-admission-independent-of-entitlement~1]
    # [impl->req~quota-admission-before-quota-mutation~1]
    ledger.expensive_step(ExpensiveStep.database_lock, guarded_by=(QUOTA_ADMISSION_ENTRY,))

    # [impl->req~quota-rollover-lock-scope~1]
    with LockLedger(LockingPath.lazy_monthly_rollover) as locks:
        # 1. resolve the user's single active grant row and lock it `FOR UPDATE`.
        # [impl->req~quota-rollover-step-01~1]
        rows = await store.locked_grant_rows(user_id, moment)
        tier: EffectiveTier = effective_tier(rows, moment)
        # Passing admission grants no entitlement of its own: the allowance is still the
        # effective grant's tier, and no effective grant means nothing to consume.
        # [impl->req~quota-admission-independent-of-entitlement~1]
        # [impl->req~quota-only-effective-grants-authorize~1]
        grant: GrantRow | None = tier.grant
        if grant is None or not authorizes(grant, moment):
            raise QuotaExceededError("Monthly quota exceeded")
        locks.lock_grant(grant.grant_id)

        # 2. load the usage row for that grant `FOR UPDATE`, grant lock first and usage lock
        #    second. Every grant-creation path creates this row in the grant-creating
        #    transaction, so a missing row is an internal invariant violation and the request
        #    fails closed rather than minting a counter.
        # [impl->req~quota-rollover-step-02~1]
        locks.lock_usage(grant.grant_id)
        stored = await store.locked_usage_row(grant.grant_id)
        stored_period = require_usage_row(stored[0] if stored else None, grant.grant_id)
        monthly_used = stored[1] if stored else 0

        # 3. compute the current `monthly_period`, from the same captured evaluation time.
        # [impl->req~quota-rollover-step-03~1]
        current = period_of(moment)

        # 4. if the stored period is not the current one, advance it and zero the counter.
        # [impl->req~quota-rollover-step-04~1]
        rolled = needs_rollover(stored_period, current)
        if rolled:
            ledger.expensive_step(ExpensiveStep.database_mutation,
                                  guarded_by=(QUOTA_ADMISSION_ENTRY,))
            await store.write_rollover(grant.grant_id, rollover_values(current, now=moment))
            monthly_used = 0

        # 5. compute the allowance from the grant's tier.
        # [impl->req~quota-rollover-step-05~1]
        allowance = tier.allowance

        # 6. remaining, floored at zero.
        remaining = remaining_credits(allowance, monthly_used)

        # 7. zero remaining is ordinary quota exhaustion, never a distinct error.
        # [impl->req~quota-rollover-step-07~1]
        if remaining == 0:
            raise QuotaExceededError("Monthly quota exceeded")

        # 8. otherwise consume usage by incrementing `monthly_used`.
        # [impl->req~quota-rollover-step-08~1]
        ledger.expensive_step(ExpensiveStep.database_mutation,
                              guarded_by=(QUOTA_ADMISSION_ENTRY,))
        await store.increment_usage(grant.grant_id, current)
        monthly_used += 1

        # The sequence's own commit, the last thing it does under the locks: the grant and usage
        # locks are gone before this function returns, so the handler's store or provider call
        # cannot run while they are held. The lock ledger declares them released on the way out
        # of this block, which is the same moment.
        # [impl->req~quota-rollover-lock-scope~1]
        await store.commit()

    # The locks are released at commit; the sequence adds no retry loop of its own.
    # [impl->req~quota-rollover-lock-scope~1]
    # [impl->req~quota-no-background-job~1]
    assert_no_background_job()
    return QuotaConsumption(grant_id=grant.grant_id,
                            monthly_period=current,
                            allowance=allowance,
                            monthly_used=monthly_used,
                            remaining=remaining - 1,
                            rolled_over=rolled)


__all__ = [
    "QUOTA_ADMISSION_ENTRY",
    "QUOTA_ADMISSION_ENTRIES",
    "QUOTA_ADMISSION_KEY_POLICY",
    "AdmissionRejected",
    "QuotaConsumption",
    "QuotaSequenceError",
    "QuotaStore",
    "assert_admission_key_policy",
    "assert_no_background_job",
    "consume_quota",
    "quota_admission",
    "remaining_credits",
    "rollover_values",
]
