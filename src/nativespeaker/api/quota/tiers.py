"""`core.access_tiers`: the configured access tiers and their monthly credit limits.

A tier is product configuration, not per-user state. Its `id` is the stable identifier grants
and subscriptions point at, and its `monthly_credits` is the allowance every grant on that tier
spends. The catalogue is declared in the application configuration file and lives, as rows, in
PostgreSQL; nothing about a tier is ever copied onto a user, a grant, or a usage row.

The one sizing rule this module enforces is the tier-sizing invariant: no registered tier may
grant fewer monthly credits than the anonymous tier, so a converting user's carried
`monthly_used` can never exceed the allowance of the tier they land on.
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from nativespeaker.api.models.users import AccessTier


class TierConfigError(RuntimeError):
    """A configured tier catalogue this specification will not run: a registered tier sized
    below the anonymous tier, or a per-user credit override standing in for a tier row. Raised
    at configuration load and again wherever tier credit values are written, before traffic."""


class TierClass(StrEnum):
    """Which kind of account a tier is offered to. The anonymous tier is the floor every
    registered tier — the free registered tier and every paid tier alike — is measured against."""
    anonymous = "anonymous"
    registered = "registered"


class AccessTierEntry(BaseModel):
    """One configured tier: its monthly allowance and the account class it serves.

    `monthly_credits` is the configured monthly allowance for that tier. Zero is a legal value
    and means exactly what it says — no access, or a deliberately zero-credit tier — while a
    negative allowance is not a tier at all.
    """
    # [impl->req~schema-access-tiers-monthly-credits-allowance~1]
    # [impl->req~schema-access-tiers-zero-credits-allowed~1]
    monthly_credits: int = Field(ge=0)
    tier_class: TierClass


# Numeric credit amounts are a property of a tier row, never of a user. No per-user override
# column exists on `core.users` or `core.user_monthly_usage`, so a bespoke allowance is one more
# `core.access_tiers` row that grants point at.
# [impl->req~schema-access-tiers-custom-tiers-as-rows~1]
PER_USER_CREDIT_OVERRIDE_COLUMNS: frozenset[str] = frozenset({
    "monthly_credits", "monthly_credit_override", "credits", "credit_override",
    "extra_credits", "bonus_credits", "monthly_limit", "quota", "custom_quota",
})


def anonymous_floor(catalogue: Mapping[str, AccessTierEntry]) -> int:
    """The anonymous tier's configured allowance — the floor the registered tiers sit at or
    above. With several anonymous tiers configured, the largest of them is the floor."""
    # [impl->req~schema-access-tiers-registered-ge-anonymous~1]
    return max((entry.monthly_credits for entry in catalogue.values()
                if entry.tier_class is TierClass.anonymous), default=0)


def assert_tier_sizing(catalogue: Mapping[str, AccessTierEntry]) -> None:
    """Every registered tier's `monthly_credits` is greater than or equal to the anonymous
    tier's, the free registered tier and any paid tier alike. A catalogue that violates it is
    rejected outright — at configuration load and again wherever tier credit values are set, so
    an operator edit cannot install one at runtime either. There is no warn-and-continue path.
    """
    # [impl->req~schema-access-tiers-registered-ge-anonymous~1]
    # [impl->req~schema-access-tiers-sizing-invariant-enforced~1]
    floor = anonymous_floor(catalogue)
    violating = sorted(tier_id for tier_id, entry in catalogue.items()
                       if entry.tier_class is TierClass.registered
                       and entry.monthly_credits < floor)
    if violating:
        raise TierConfigError(
            f"registered tiers {violating} grant fewer than the anonymous tier's {floor} "
            "monthly credits")


def allowance_of(catalogue: Mapping[str, AccessTierEntry], tier_id: str) -> int:
    """The configured monthly allowance of one tier, read from the tier and from nowhere else."""
    # [impl->req~schema-access-tiers-monthly-credits-allowance~1]
    entry = catalogue.get(tier_id)
    if entry is None:
        raise TierConfigError(f"{tier_id} is not a configured access tier")
    return entry.monthly_credits


def assert_no_per_user_credit_override(table: str, columns: Iterable[str]) -> None:
    """A custom allowance is an additional tier row, never a numeric credit override stored per
    user. `core.access_tiers` is product configuration; per-user state is usage, and usage is a
    count of what was spent."""
    # [impl->req~schema-access-tiers-custom-tiers-as-rows~1]
    # [impl->req~schema-access-tiers-product-configuration~1]
    offending = sorted({column for column in columns
                        if column in PER_USER_CREDIT_OVERRIDE_COLUMNS})
    if offending:
        raise TierConfigError(
            f"{table}.{offending} would be a per-user credit override; add a tier row instead")


def tier_rows(catalogue: Mapping[str, AccessTierEntry],
              *, now: datetime | None = None) -> list[AccessTier]:
    """The catalogue as `core.access_tiers` rows: one row per configured tier, keyed by the
    stable tier `id` that grants and subscriptions reference. Custom tiers are additional rows
    here, and this is the only place the numbers are stored."""
    # [impl->req~schema-access-tiers-product-configuration~1]
    # [impl->req~schema-access-tiers-custom-tiers-as-rows~1]
    # [impl->req~schema-access-tiers-id-stable-identifier~1]
    assert_tier_sizing(catalogue)
    stamp = now or datetime.now(UTC)
    return [AccessTier(id=tier_id, monthly_credits=entry.monthly_credits,
                       created_at=stamp, updated_at=stamp)
            for tier_id, entry in sorted(catalogue.items())]
