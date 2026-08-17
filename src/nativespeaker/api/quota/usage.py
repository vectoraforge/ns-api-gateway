"""`core.user_monthly_usage`: mutable monthly usage state for an access grant.

The row counts what one grant has spent this month, and that is all it is. It carries no
allowance — the allowance is derived by joining the owning `core.access_grants` row to
`core.access_tiers` — it grants no access on its own, and it never leaves the grant it was
created with. There is at most one row per grant, because `grant_id` is the primary key.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

# `YYYY-MM`, the accounting month a stored counter belongs to.
MONTHLY_PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# The columns of the row. Usage state only: which month is being counted and how much of it has
# been spent. The tier's allowance is not among them.
USAGE_ROW_COLUMNS: frozenset[str] = frozenset({
    "grant_id", "monthly_period", "monthly_used", "created_at", "updated_at",
})

# Allowance-shaped columns that must never appear on this table: the number lives on the tier.
ALLOWANCE_COLUMNS: frozenset[str] = frozenset({
    "monthly_credits", "allowance", "monthly_allowance", "monthly_limit", "tier_id",
    "credits", "quota",
})


class UsageRowError(RuntimeError):
    """A `core.user_monthly_usage` rule was about to be broken."""


class MissingUsageRowError(UsageRowError):
    """An existing grant has no monthly usage row. The row is created with its grant, never
    lazily by the quota path, so its absence is a server-side data error: the request fails
    closed rather than being handed a fresh counter."""

    def __init__(self, grant_id: UUID):
        self.grant_id = grant_id
        super().__init__(f"grant {grant_id} has no core.user_monthly_usage row")


@dataclass(frozen=True, slots=True)
class NewUsageRow:
    """The row a grant-creating transaction writes beside its grant."""
    grant_id: UUID
    monthly_period: str
    monthly_used: int = 0


def period_of(now: datetime | None = None) -> str:
    """The accounting month a moment falls in, `YYYY-MM` by the recommended convention: the UTC
    calendar month."""
    # [impl->req~schema-user-monthly-usage-monthly-period-field~1]
    moment = now or datetime.now(UTC)
    return moment.astimezone(UTC).strftime("%Y-%m")


def assert_period(period: str) -> str:
    """`monthly_period` is the current accounting month in `YYYY-MM` format."""
    # [impl->req~schema-user-monthly-usage-monthly-period-field~1]
    if not MONTHLY_PERIOD_PATTERN.match(period):
        raise UsageRowError(f"{period!r} is not a YYYY-MM accounting month")
    return period


def assert_monthly_used(monthly_used: int) -> int:
    """`monthly_used` is the amount already consumed for `monthly_period` — a count of spend in
    that month, never a balance and never negative."""
    # [impl->req~schema-user-monthly-usage-monthly-used-field~1]
    if monthly_used < 0:
        raise UsageRowError("monthly_used is the amount consumed, never a negative balance")
    return monthly_used


def assert_one_row_per_grant(grant_ids: Iterable[UUID]) -> None:
    """There is at most one row per `core.access_grants.id`; `grant_id` being the primary key is
    what makes a second row for the same grant impossible."""
    # [impl->req~schema-user-monthly-usage-one-row-per-grant~1]
    seen: set[UUID] = set()
    for grant_id in grant_ids:
        if grant_id in seen:
            raise UsageRowError(f"grant {grant_id} already owns a monthly usage row")
        seen.add(grant_id)


def new_usage_row(grant_id: UUID,
                  *,
                  now: datetime | None = None,
                  carried: tuple[str, int] | None = None,
                  grant_transaction: Any = None,
                  usage_transaction: Any = None) -> NewUsageRow:
    """The usage row of a newly created grant, written in the same transaction that creates the
    grant — by purchase ingestion, by the free-grant claims, and by restore's adoption of an
    unclaimed subscription. It initializes mutable usage state only, and nothing else: no
    access, no introductory entitlement, and no allowance, which stays derived from the grant's
    tier.

    The usage state it starts from is the fresh shape by default — the current accounting month
    and a zero counter — but a creator that supersedes an existing grant carries that grant's
    `(monthly_period, monthly_used)` across instead, unchanged: no clamping, no reset, no
    prorating. That is the one creation point either kind of creator uses.
    """
    # [impl->req~schema-user-monthly-usage-created-with-grant~1]
    # [impl->req~schema-user-monthly-usage-row-initializes-usage-only~1]
    if grant_transaction is not usage_transaction:
        raise UsageRowError(
            "the usage row is created in the same transaction as its grant")
    period, used = carried if carried is not None else (period_of(now), 0)
    return NewUsageRow(grant_id=grant_id,
                       monthly_period=assert_period(period),
                       monthly_used=assert_monthly_used(used))


def require_usage_row(stored_period: str | None, grant_id: UUID) -> str:
    """The quota path reads the row and never creates one. A grant with no row is data
    corruption, so the read fails closed instead of quietly minting a counter."""
    # [impl->req~schema-user-monthly-usage-created-with-grant~1]
    if stored_period is None:
        raise MissingUsageRowError(grant_id)
    return stored_period


def needs_rollover(stored_period: str, current: str) -> bool:
    """Whether this row is still counting a month that has ended."""
    # [impl->req~schema-user-monthly-usage-lazy-monthly-reset~1]
    return stored_period != current


def rolled_over(stored_period: str, stored_used: int, *, current: str) -> tuple[str, int]:
    """The lazy monthly reset: when the current month changes, `monthly_period` advances and
    `monthly_used` resets to `0`, on the first quota-checked request in the new month and not
    before. Nothing is carried forward, and no scheduled job does this."""
    # [impl->req~schema-user-monthly-usage-lazy-monthly-reset~1]
    assert_period(current)
    if needs_rollover(assert_period(stored_period), current):
        return current, 0
    return stored_period, assert_monthly_used(stored_used)


def derived_allowance(grant_tier_id: str | None, tier_monthly_credits: int | None) -> int:
    """The monthly allowance of a usage row's grant, derived from the owning
    `core.access_grants` row joined to `core.access_tiers`. A grant that resolves to no tier row
    has no allowance to spend."""
    # [impl->req~schema-user-monthly-usage-allowance-derived-from-tier~1]
    if grant_tier_id is None or tier_monthly_credits is None:
        return 0
    return tier_monthly_credits


def assert_allowance_not_stored(columns: Iterable[str]) -> None:
    """The allowance is not stored on this table: no allowance, credit or tier column may be
    added to it, and no writer may set one."""
    # [impl->req~schema-user-monthly-usage-allowance-not-stored~1]
    offending = sorted({column for column in columns if column in ALLOWANCE_COLUMNS})
    if offending:
        raise UsageRowError(
            f"{offending} is derived from the grant's tier, not stored on user_monthly_usage")
    unknown = sorted({column for column in columns if column not in USAGE_ROW_COLUMNS})
    if unknown:
        raise UsageRowError(f"{unknown} are not columns of core.user_monthly_usage")


# What creating a `core.user_monthly_usage` row allocates besides the counter: nothing. No
# grant row, and no introductory entitlement — that is itself a grant, and this row is not one.
USAGE_ROW_ALLOCATES: frozenset[str] = frozenset()


def assert_grants_no_access(rows_allocated: Iterable[str] = ()) -> None:
    """A usage row does not by itself grant access, and it allocates no introductory
    entitlement. Access is the grant; the row only counts what the grant allows. A row whose
    grant is no longer active is ordinary committed state — a superseded anonymous grant keeps
    both its expired grant row and its counter — so the decider is not the row's existence but
    the effective-grant check the quota path makes before any counter is read."""
    # [impl->req~schema-user-monthly-usage-grants-no-access~1]
    offending = sorted(set(rows_allocated) | USAGE_ROW_ALLOCATES)
    if offending:
        raise UsageRowError(f"creating a monthly usage row allocates no {offending}")


def assert_stays_with_grant(*,
                            stored_grant_id: UUID,
                            row_grant_id: UUID,
                            minted_fresh: bool = False) -> None:
    """A subscription-backed grant never moves to another user, so its usage row stays attached
    to the same `grant_id` for the life of the grant. Restore settles the existing grant and its
    existing counter; it never re-points the row and never mints a fresh counter for the same
    paid entitlement."""
    # [impl->req~schema-user-monthly-usage-stays-with-grant~1]
    if row_grant_id != stored_grant_id:
        raise UsageRowError("a monthly usage row stays attached to its own grant_id")
    if minted_fresh:
        raise UsageRowError(
            "restore mints no fresh monthly counter for an entitlement that already has one")


def usage_state(row: Mapping[str, Any]) -> dict[str, Any]:
    """The mutable state a writer may set on the row, with everything else refused."""
    # [impl->req~schema-user-monthly-usage-row-initializes-usage-only~1]
    assert_allowance_not_stored(row)
    return dict(row)
