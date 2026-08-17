"""How quota enforcement consumes the grant, tier and usage tables.

`core.access_grants` is the single entitlement table — subscription-backed access and
non-subscription access alike — and an active row on it is the whole of what says a user has a
monthly allowance. The table facts themselves are owned by `06-schema-reference.md`; this module
is their consumer. It applies one shared effective-grant predicate, derives the effective tier
from the grant's `core.access_tiers` row, and derives the reported entitlement from that same
effective grant.

Read paths own no repair. The deferrable foreign key from the generated
`active_subscription_grant_subscription_id` column to `product_entitled_subscription_id`
guarantees at commit that an active subscription-backed grant is backed by a product-entitled
subscription, so nothing here re-reads a subscription's status, detects divergence, or writes.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.models.subscriptions import SubscriptionStatus
from nativespeaker.api.quota.tiers import assert_no_per_user_credit_override
from nativespeaker.api.quota.usage import (
    assert_allowance_not_stored,
    assert_stays_with_grant,
    period_of,
)


class EntitlementError(RuntimeError):
    """A quota-and-access-enforcement rule was about to be broken."""


class TooManyActiveGrantsError(EntitlementError):
    """More than one effective grant exists for one user: an invariant violation, never a tie to
    break and never a precedence ranking to apply."""


class ReadPathRepairError(EntitlementError):
    """A read path was about to re-read, re-derive or repair the subscription-backed entitlement
    the deferrable foreign key already guarantees."""


class MissingTierError(EntitlementError):
    """An effective grant resolved to no `core.access_tiers` row."""


# The tables this file consumes, and what each of them owns. Entitlement is the grant table,
# paid billing records are the subscription table, the numbers are the tier table, and
# consumption is the usage table keyed by `grant_id`. There is no second entitlement table and
# no fake-subscription representation of a free grant.
# [impl->req~quota-access-grants-single-entitlement-table~1]
ENTITLEMENT_TABLE = "core.access_grants"
BILLING_TABLE = "core.subscriptions"
TIER_TABLE = "core.access_tiers"
USAGE_TABLE = "core.user_monthly_usage"

# Product access that carries no billing record: represented here as grants, never as fake
# subscriptions.
NON_SUBSCRIPTION_GRANT_SOURCES: frozenset[AccessGrantSource] = frozenset({
    AccessGrantSource.anonymous_device_grant,
    AccessGrantSource.registered_account_grant,
    AccessGrantSource.manual,
})

# Columns that would make an allowance a property of a user row or of a usage row instead of an
# active grant pointing at a tier.
PER_USER_ENTITLEMENT_COLUMNS: frozenset[str] = frozenset({
    "plan", "tier_id", "monthly_credits", "allowance", "monthly_allowance", "free_access",
    "has_access", "credits", "quota", "entitled", "subscription_status",
})

# The product-entitled subscription statuses. This list is descriptive: the single authoritative
# source of truth is the `product_entitled_subscription_id` generated-column expression on
# `core.subscriptions`, `CASE WHEN status IN ('active', 'grace_period') THEN id END`.
# [impl->req~quota-product-entitled-status-set~2]
PRODUCT_ENTITLED_GENERATED_COLUMN = "product_entitled_subscription_id"
PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES: frozenset[SubscriptionStatus] = frozenset({
    SubscriptionStatus.active,
    SubscriptionStatus.grace_period,
})

# Per-device evidence never reaches an entitlement decision: restore keeps no per-device state,
# the restore file's `req~restore-invariant-12~1`.
PER_DEVICE_STATE_INPUTS: frozenset[str] = frozenset({
    "device_id", "device_token", "device_fingerprint", "devicecheck_bit", "device_recall_bits",
    "installation_id", "vendor_identifier", "per_device_grant_state",
})


def is_product_entitled(status: SubscriptionStatus) -> bool:
    """Whether a subscription row is product-entitled — exactly the statuses the generated
    column's `CASE` arm selects. `billing_retry`, `expired` and `revoked` are not."""
    # [impl->req~quota-product-entitled-status-set~2]
    return status in PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES


@dataclass(frozen=True, slots=True)
class GrantRow:
    """One `core.access_grants` row as the enforcement paths read it, with the joined
    `core.access_tiers.monthly_credits` alongside."""
    grant_id: UUID
    user_id: UUID
    tier_id: str
    source: AccessGrantSource
    status: AccessGrantStatus
    starts_at: datetime
    ends_at: datetime | None = None
    subscription_id: UUID | None = None
    tier_monthly_credits: int | None = None


@dataclass(frozen=True, slots=True)
class EffectiveTier:
    """The user's effective grant, if any, and the allowance its tier configures."""
    grant: GrantRow | None
    allowance: int


class PublicEntitlementStatus(StrEnum):
    """The public status enum, exactly `none | active`: `expired` and `revoked` are internal
    lifecycle labels and are never reported."""
    # [impl->req~quota-public-status-none-or-active~1]
    none = "none"
    active = "active"


class PublicEntitlementType(StrEnum):
    """The reported `type`: `none`, or the effective grant's `core.access_grants.source`."""
    # [impl->req~quota-type-from-grant-source~1]
    none = "none"
    subscription = "subscription"
    anonymous_device_grant = "anonymous_device_grant"
    registered_account_grant = "registered_account_grant"
    manual = "manual"


@dataclass(frozen=True, slots=True)
class EntitlementReport:
    """The derived values of the entitlement response."""
    type: PublicEntitlementType
    status: PublicEntitlementStatus
    tier_id: str | None
    monthly_credits: int | None
    current_period: str
    monthly_used: int


# --- the shared effective-grant predicate -----------------------------------------------------


def is_effective(grant: GrantRow, now: datetime) -> bool:
    """The shared effective-grant predicate: the one definition of a grant's currentness,
    applied identically by quota enforcement, `/auth/sync` and every other consumer. No path
    selects by `status` alone.

    It reads the rows as they stand. A time-ended row that the lazy expiry flip has not yet
    moved off `status = 'active'` is simply not effective, so it never competes with its
    replacement, and no read path flips it.
    """
    # [impl->req~quota-shared-effective-grant-predicate~1]
    # [impl->req~quota-effective-tier-step-01~1]
    # [impl->req~quota-no-future-dating-lazy-expiry-flip~2]
    # Only the active, non-expired grant participates in the access calculation.
    # [impl->req~schema-access-grants-only-active-participates~1]
    return (grant.status is AccessGrantStatus.active
            and grant.starts_at <= now
            and (grant.ends_at is None or grant.ends_at > now))


def authorizes(grant: GrantRow | None, now: datetime) -> bool:
    """Only effective grants authorize access or quota consumption. A lapsed, revoked or
    not-yet-started row authorizes nothing, and neither does the existence of a usage row."""
    # [impl->req~quota-only-effective-grants-authorize~1]
    return grant is not None and is_effective(grant, now)


def has_monthly_allowance(grant: GrantRow | None,
                          *,
                          usage_row_exists: bool = False,
                          user_columns: Iterable[str] = ()) -> bool:
    """Whether a user has any monthly allowance at all. That is an active row in
    `core.access_grants` and nothing else: not the existence of a `core.user_monthly_usage`
    row, and not a field on `core.users`."""
    # [impl->req~quota-allowance-from-active-grant-row~1]
    offending = sorted({column for column in user_columns
                        if column in PER_USER_ENTITLEMENT_COLUMNS})
    if offending:
        raise EntitlementError(
            f"core.users.{offending} would make the allowance a user field; it is an active "
            f"{ENTITLEMENT_TABLE} row")
    del usage_row_exists  # a counter is not an entitlement and never decides this
    return grant is not None


def assert_billing_separation(source: AccessGrantSource,
                              subscription_id: UUID | None) -> None:
    """Paid billing records live in `core.subscriptions`; product access is granted through
    `core.access_grants`. A subscription-backed grant names its billing row, and an anonymous
    device grant, a registered account grant or a manual grant names none — a free grant is
    never written as a fake subscription."""
    # [impl->req~quota-billing-vs-grant-separation~1]
    if source is AccessGrantSource.subscription and subscription_id is None:
        raise EntitlementError(
            f"a subscription-backed grant names its {BILLING_TABLE} row")
    if source in NON_SUBSCRIPTION_GRANT_SOURCES and subscription_id is not None:
        raise EntitlementError(
            f"a {source} grant is product access without a {BILLING_TABLE} row")


def assert_limits_live_in_access_tiers(*,
                                       user_columns: Iterable[str] = (),
                                       usage_columns: Iterable[str] = ()) -> None:
    """Numeric monthly limits live in `core.access_tiers`, not in `core.users` and not in
    `core.user_monthly_usage`."""
    # [impl->req~quota-limits-live-in-access-tiers~1]
    # [impl->req~quota-usage-model-owned-by-schema-file~1]
    assert_no_per_user_credit_override("core.users", user_columns)
    assert_allowance_not_stored(usage_columns)


# --- effective access tier --------------------------------------------------------------------


def select_effective_grant(rows: Sequence[GrantRow], now: datetime) -> GrantRow | None:
    """Steps 1 and 2: the user's single effective grant, or none.

    The candidate set is the rows that satisfy the shared predicate; more than one is an
    invariant violation rather than a choice between them.
    """
    # [impl->req~quota-effective-tier-step-01~1]
    # [impl->req~quota-report-single-effective-grant~1]
    current = [row for row in rows if is_effective(row, now)]
    # [impl->req~quota-effective-tier-step-02~1]
    if len(current) > 1:
        raise TooManyActiveGrantsError(
            f"{current[0].user_id} has {len(current)} effective access grants")
    if not current:
        return None
    return honor_grant(current[0])


def honor_grant(grant: GrantRow,
                *,
                subscription_status: SubscriptionStatus | None = None,
                deferred_constraints_pending: bool = False) -> GrantRow:
    """Steps 3 and 4: honor the effective grant outright.

    A subscription-backed grant is honored without re-reading its subscription. The deferrable
    foreign key from the generated `active_subscription_grant_subscription_id` column to
    `product_entitled_subscription_id` guarantees at commit that the linked subscription is
    product-entitled, so evaluation never branches on that status, detects no divergence and
    writes nothing: the FK-backed active grant is the schema's canonical entitlement
    representation. Read paths own no repair, and entitlement is never evaluated from a
    deferred-constraint intermediate state.
    """
    # [impl->req~quota-effective-tier-step-03~1]
    # [impl->req~quota-subscription-grant-active-requires-entitled~2]
    # The deferrable foreign key is the sole enforcement mechanism, so no read path detects or
    # repairs a non-entitled active subscription-backed grant: it cannot exist in committed data.
    # [impl->req~schema-access-grants-active-requires-entitled-subscription~1]
    if subscription_status is not None:
        raise ReadPathRepairError(
            f"the deferrable foreign key to {PRODUCT_ENTITLED_GENERATED_COLUMN} already "
            "guarantees this grant is product-entitled; evaluation re-reads no subscription")
    # [impl->req~quota-effective-tier-step-04~1]
    if deferred_constraints_pending:
        raise ReadPathRepairError(
            "the deferred constraint is resolved before any transaction uses the effective tier")
    return grant


def effective_allowance(grant: GrantRow | None) -> int:
    """Steps 5 and 6: join the grant to `core.access_tiers` and use that row's
    `monthly_credits` as the configured monthly allowance. With no effective grant the allowance
    is `0` — and a stale non-entitled subscription-backed grant cannot exist in committed data,
    so zero never stands for one."""
    # [impl->req~quota-effective-tier-step-05~1]
    # [impl->req~quota-effective-tier-step-06~1]
    # [impl->req~quota-limits-live-in-access-tiers~1]
    if grant is None:
        # [impl->req~quota-no-grant-zero-allowance~1]
        return 0
    if grant.tier_monthly_credits is None:
        raise MissingTierError(
            f"grant {grant.grant_id} joins no {TIER_TABLE} row for tier {grant.tier_id}")
    return grant.tier_monthly_credits


def effective_tier(rows: Sequence[GrantRow], now: datetime) -> EffectiveTier:
    """The whole effective-access-tier calculation for one captured evaluation time."""
    # [impl->req~quota-shared-effective-grant-predicate~1]
    # [impl->req~quota-no-future-dating-lazy-expiry-flip~2]
    grant = select_effective_grant(rows, now)
    return EffectiveTier(grant=grant, allowance=effective_allowance(grant))


# --- entitlement reporting --------------------------------------------------------------------


def entitlement_report(rows: Sequence[GrantRow],
                       *,
                       now: datetime,
                       stored_period: str | None = None,
                       stored_used: int = 0) -> EntitlementReport:
    """The derived values of the entitlement response.

    `/auth/sync`'s endpoint behavior — its read-only reporting contract, its prohibitions, its
    no-device-proof and no-grant-minting rules — and the wire shape of the response are owned by
    `01-sessions-and-identity-resolution.md`. This function derives the values only, and mutates
    nothing: the rollover a stale stored period will get is the next quota-checked request's,
    not this read's.
    """
    # [impl->req~quota-sync-behavior-owned-by-sessions-file~1]
    # [impl->req~quota-entitlement-response-shape~2]
    # The period comes from the clock under the shared period definition, and the same captured
    # evaluation time drives grant selection and the usage read.
    # [impl->req~quota-auth-sync-no-grant-defaults~1]
    # [impl->req~quota-no-future-dating-lazy-expiry-flip~2]
    current = period_of(now)
    # The stored counter is this month's figure only when the row names this month.
    monthly_used = stored_used if stored_period == current else 0
    # [impl->req~quota-report-single-effective-grant~1]
    tier = effective_tier(rows, now)
    if tier.grant is None:
        # [impl->req~quota-public-status-none-or-active~1]
        return EntitlementReport(type=PublicEntitlementType.none,
                                 status=PublicEntitlementStatus.none,
                                 tier_id=None,
                                 monthly_credits=None,
                                 current_period=current,
                                 monthly_used=0)
    # [impl->req~quota-type-from-grant-source~1]
    return EntitlementReport(type=PublicEntitlementType(tier.grant.source.value),
                             # [impl->req~quota-public-status-none-or-active~1]
                             status=PublicEntitlementStatus.active,
                             tier_id=tier.grant.tier_id,
                             monthly_credits=tier.allowance,
                             current_period=current,
                             monthly_used=monthly_used)


# --- the subscription-backed grant lifecycle ---------------------------------------------------


def assert_no_per_device_state(inputs: Iterable[str]) -> None:
    """No per-device state participates in an entitlement decision."""
    # [impl->req~quota-restore-no-per-device-state~2]
    offending = sorted({name for name in inputs if name in PER_DEVICE_STATE_INPUTS})
    if offending:
        raise EntitlementError(f"{offending} is per-device state; restore keeps none")


def assert_owner_stability(*,
                           grant_user_id: UUID,
                           destination_user_id: UUID,
                           grant_id: UUID,
                           usage_row_grant_id: UUID) -> None:
    """Owner stability under restore: the grant never moves to a different user, and its monthly
    usage row stays attached to the same grant — the restore file's `req~restore-invariant-10~1`.
    """
    # [impl->req~quota-restore-owner-stability~2]
    if destination_user_id != grant_user_id:
        raise EntitlementError(f"grant {grant_id} never moves to another user")
    assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=usage_row_grant_id)


def settle_subscription_grant(grant: GrantRow,
                              *,
                              subscription_status: SubscriptionStatus,
                              destination_user_id: UUID,
                              usage_row_grant_id: UUID,
                              per_device_inputs: Iterable[str] = ()) -> GrantRow:
    """Restore's one entry into subscription-backed grant state: it must not move or activate a
    subscription-backed grant unless the canonical subscription row is currently
    product-entitled."""
    # [impl->req~quota-restore-requires-entitled-subscription~1]
    if not is_product_entitled(subscription_status):
        raise EntitlementError(
            f"restore activates no subscription-backed grant while its subscription is "
            f"{subscription_status}")
    assert_no_per_device_state(per_device_inputs)
    assert_owner_stability(grant_user_id=grant.user_id,
                           destination_user_id=destination_user_id,
                           grant_id=grant.grant_id,
                           usage_row_grant_id=usage_row_grant_id)
    return grant


# No scheduled reconciliation sweep exists over grant and subscription state: a status-changing
# writer's bug surfaces as its own loud commit failure instead.
# [impl->req~quota-status-writer-owns-grant-deactivation~1]
RECONCILIATION_SWEEPS: frozenset[str] = frozenset()


def settled_grant_status(new_status: SubscriptionStatus) -> AccessGrantStatus:
    """How the status writer settles the grant it is taking out of entitlement: a revoked
    subscription revokes its grant, and every other exit from the product-entitled set — expiry,
    lapse, a failed renewal — expires it."""
    # [impl->req~quota-status-writer-owns-grant-deactivation~1]
    if is_product_entitled(new_status):
        raise EntitlementError(f"{new_status} is product-entitled; its grant stays active")
    return (AccessGrantStatus.revoked if new_status is SubscriptionStatus.revoked
            else AccessGrantStatus.expired)


def assert_status_writer_settled_grant(*,
                                       old_status: SubscriptionStatus,
                                       new_status: SubscriptionStatus,
                                       active_grant_id: UUID | None,
                                       grant_deactivated: bool = False,
                                       grant_replaced: bool = False,
                                       subscription_transaction: object = None,
                                       grant_transaction: object = None) -> None:
    """Whichever write path transitions a subscription out of the product-entitled set — the
    store webhook or notification handler, expiry or lapse processing, refund handling, or an
    operator action — owns the obligation to deactivate or replace the active grant in the same
    transaction. This is that check, taken by the writer: without it the deferrable foreign key
    forces the commit to fail, which is the loud failure this raise stands in for.

    Lifecycle ingestion's same-transaction obligation is the schema fact
    `req~schema-access-grants-lifecycle-same-transaction~1`.
    """
    # [impl->req~quota-lifecycle-ingestion-single-transaction~2]
    # [impl->req~schema-access-grants-lifecycle-same-transaction~1]
    if subscription_transaction is not grant_transaction:
        raise EntitlementError(
            "a subscription status change and its grant settlement share one transaction")
    # [impl->req~quota-status-writer-owns-grant-deactivation~1]
    # [impl->req~quota-subscription-grant-active-requires-entitled~2]
    if (is_product_entitled(old_status)
            and not is_product_entitled(new_status)
            and active_grant_id is not None
            and not (grant_deactivated or grant_replaced)):
        raise EntitlementError(
            f"grant {active_grant_id} must be deactivated or replaced in the same transaction "
            f"as the {old_status} -> {new_status} change, or the foreign key fails the commit")


class RaceOutcome(StrEnum):
    """How ordinary transaction and foreign-key serialization resolves a concurrent restore
    racing a subscription losing entitlement."""
    committed = "committed"
    retry = "retry"
    failed = "failed"


def resolve_entitlement_race(*,
                             committed: bool,
                             retryable: bool = True,
                             repair_protocol: str | None = None) -> RaceOutcome:
    """A concurrent restore racing a subscription losing entitlement needs no separate repair
    protocol: one transaction commits and the other retries or fails cleanly."""
    # [impl->req~quota-restore-race-serialization~1]
    if repair_protocol is not None or RECONCILIATION_SWEEPS:
        raise EntitlementError(
            "this race is resolved by ordinary transaction and foreign-key serialization; "
            f"{repair_protocol or sorted(RECONCILIATION_SWEEPS)} is not a protocol this "
            "specification has")
    if committed:
        return RaceOutcome.committed
    return RaceOutcome.retry if retryable else RaceOutcome.failed


# The enforcement invariants that bear on quota and access are owned by `06-schema-reference.md`
# (`## Schema-Specific Invariants`); this module restates none of them and holds no second copy.
# [impl->req~quota-enforcement-invariants-owned-by-schema-file~1]
ENFORCEMENT_INVARIANT_OWNER = "06-schema-reference.md"
ENFORCEMENT_INVARIANTS: Mapping[str, str] = {
    name: ENFORCEMENT_INVARIANT_OWNER
    for name in ("schema-invariant-01", "schema-invariant-03", "schema-invariant-08",
                 "schema-invariant-11", "schema-invariant-14")
}
