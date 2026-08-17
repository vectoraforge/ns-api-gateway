"""The row and constraint contract of `core.access_grants` and `core.access_grants_anti_abuse`.

`core.access_grants` is the one table that says a user has access, free or paid. It carries
entitlement state only: the source-specific anti-abuse evidence of a free-credit grant sits
beside it on `core.access_grants_anti_abuse`, keyed one-to-one by `grant_id`.

Almost every rule here is enforced by the declarative schema — generated columns, partial unique
indexes, per-source CHECKs and deferrable foreign keys. This module is the write side of that
contract: it declares the constraint facts the applied DDL must carry, and it refuses to hand a
write path a row or a transaction plan the schema would reject at commit. Rules whose whole
statement already lives in another module are enforced there and delegated to from here rather
than restated.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import NativeClaimPlatform
from nativespeaker.api.auth.invariants import (
    DEVICE_GRANT_BLOCK,
    GATE_CONFLICTS,
    DevicePlatform,
    GateConsumptionKind,
    GrantCreator,
    assert_grant_columns_entitlement_only,
    assert_grant_creator,
    assert_owner_agreement,
    assert_same_transaction,
)
from nativespeaker.api.auth.schema_invariants import (
    AntiAbuseEvidence,
    anti_abuse_evidence,
    assert_anti_abuse_pairing,
    assert_native_claim_written_before_grant,
    assert_no_raw_device_material,
    requires_anti_abuse_row,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.models.subscriptions import SubscriptionStatus
from nativespeaker.api.quota.grants import (
    NON_SUBSCRIPTION_GRANT_SOURCES,
    PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES,
    RaceOutcome,
    assert_billing_separation,
    is_effective,
    is_product_entitled,
    resolve_entitlement_race,
)
from nativespeaker.api.quota.usage import NewUsageRow, new_usage_row


class GrantSchemaError(RuntimeError):
    """A proposed row or transaction plan breaks the grant tables' contract."""


# --- What each of the two tables is for -------------------------------------------------------

ACCESS_GRANTS_TABLE: str = "core.access_grants"
ANTI_ABUSE_TABLE: str = "core.access_grants_anti_abuse"

# The entitlement table's own columns, generated columns included. Entitlement state and the
# generated keys the declarative constraints hang off — and nothing else.
# [impl->req~schema-access-grants-purpose~1]
GRANT_ENTITLEMENT_COLUMNS: tuple[str, ...] = (
    "id", "user_id", "tier_id", "source", "subscription_id", "status", "starts_at", "ends_at",
    "anti_abuse_required_grant_id", "active_registered_account_grant_id",
    "active_subscription_grant_subscription_id", "active_subscription_grant_user_id",
    "created_at", "updated_at",
)

# The three anti-abuse columns, which live on the anti-abuse table and never on the grant row.
# [impl->req~schema-access-grants-no-anti-abuse-columns~1]
ANTI_ABUSE_ONLY_COLUMNS: frozenset[str] = frozenset({
    "native_claim_provider", "idp_account_hash", "idp_account_hash_key_version",
})


def assert_entitlement_state_only(columns: Iterable[str]) -> None:
    """`core.access_grants` carries entitlement state only. Anti-abuse evidence is not
    entitlement state, so `native_claim_provider`, `idp_account_hash` and
    `idp_account_hash_key_version` may only ever be columns of `core.access_grants_anti_abuse`.
    """
    # [impl->req~schema-access-grants-purpose~1]
    # [impl->req~schema-access-grants-no-anti-abuse-columns~1]
    names = [str(column) for column in columns]
    # Device-check state on the entitlement row is refused by the shared invariant's guard.
    assert_grant_columns_entitlement_only(names)
    offending = sorted(ANTI_ABUSE_ONLY_COLUMNS.intersection(names))
    if offending:
        raise GrantSchemaError(f"{offending} live only on {ANTI_ABUSE_TABLE}")
    unknown = sorted(set(names) - set(GRANT_ENTITLEMENT_COLUMNS))
    if unknown:
        raise GrantSchemaError(f"{unknown} are not {ACCESS_GRANTS_TABLE} columns")


# --- The declared constraint facts of `core.access_grants` ------------------------------------


@dataclass(frozen=True, slots=True)
class GeneratedColumn:
    """A `GENERATED ALWAYS AS ... STORED` column and the `CASE` arm that populates it."""
    name: str
    expression: str


@dataclass(frozen=True, slots=True)
class UniqueIndexFact:
    """A unique index, its key, its partial predicate, and whether it is deferrable."""
    name: str
    table: str
    columns: tuple[str, ...]
    predicate: str | None = None
    deferrable: bool = False


@dataclass(frozen=True, slots=True)
class ForeignKeyFact:
    """A foreign key, its target, and the properties the schema gives it."""
    columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]
    deferrable: bool = False
    on_delete: str | None = None
    match: str = "SIMPLE"


# Every grant belongs to exactly one `core.users` row, and points at exactly one
# `core.access_tiers` row: one owning reference and one tier reference, both single-column.
# [impl->req~schema-access-grants-one-user-per-grant~1]
# [impl->req~schema-access-grants-one-tier-per-grant~1]
GRANT_OWNER_FK = ForeignKeyFact(("user_id",), "core.users", ("id",), on_delete="CASCADE")
GRANT_TIER_FK = ForeignKeyFact(("tier_id",), "core.access_tiers", ("id",))

# The active-grant axis: a plain, non-deferrable partial unique index, enforced per statement.
# [impl->req~schema-access-grants-one-active-per-user~1]
# [impl->req~schema-access-grants-active-index-non-deferrable~1]
ACTIVE_GRANT_INDEX = UniqueIndexFact(
    name="ix_access_grants_one_active_per_user",
    table=ACCESS_GRANTS_TABLE,
    columns=("user_id",),
    predicate="status = 'active'",
    deferrable=False)

# The lifetime free-grant axis: one committed grant per user per free source, for life. The
# predicate names the two free sources and carries no status term, so an expired or revoked row
# still occupies the slot; `subscription` and `manual` fall outside it and stay unbounded.
# [impl->req~schema-access-grants-lifetime-free-grant-per-source~1]
FREE_GRANT_LIFETIME_INDEX = UniqueIndexFact(
    name="ix_access_grants_one_free_grant_per_user_source",
    table=ACCESS_GRANTS_TABLE,
    columns=("user_id", "source"),
    predicate="source IN ('anonymous_device_grant', 'registered_account_grant')")

# One active subscription-backed grant per store subscription; superseded terms stay in history.
# [impl->req~schema-access-grants-subscription-id-unique-among-active~1]
ONE_ACTIVE_GRANT_PER_SUBSCRIPTION_INDEX = UniqueIndexFact(
    name="ix_access_grants_one_per_subscription",
    table=ACCESS_GRANTS_TABLE,
    columns=("subscription_id",),
    predicate="source = 'subscription' AND subscription_id IS NOT NULL AND status = 'active'")

# `UNIQUE (id, source)` exists so the anti-abuse row can point at `(id, source)`. It is an FK
# target, not a uniqueness rule beyond the primary key: `id` alone is already unique.
# [impl->req~schema-access-grants-unique-id-source-fk-target~1]
ID_SOURCE_FK_TARGET: tuple[str, ...] = ("id", "source")

# `source` is not database-enforced provenance: no trigger, stored function, pinning table,
# permission boundary or DBA test obligation protects it. The composite foreign key only makes
# the anti-abuse row's `grant_source` agree with it at commit.
# [impl->req~schema-access-grants-unique-id-source-fk-target~1]
SOURCE_PROVENANCE_MECHANISMS: frozenset[str] = frozenset()

# The generated columns the deferrable foreign keys hang off, with the arms that populate them.
# [impl->req~schema-access-grants-required-anti-abuse-fk~1]
ANTI_ABUSE_REQUIRED_COLUMN = GeneratedColumn(
    "anti_abuse_required_grant_id",
    "CASE WHEN source IN ('anonymous_device_grant', 'registered_account_grant') THEN id END")
# [impl->req~schema-access-grants-entitled-subscription-generated-fk~1]
# [impl->req~schema-access-grants-subscription-owner-composite-fk~1]
ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN = GeneratedColumn(
    "active_subscription_grant_subscription_id",
    "CASE WHEN source = 'subscription' AND status = 'active' THEN subscription_id END")
ACTIVE_SUBSCRIPTION_GRANT_USER_COLUMN = GeneratedColumn(
    "active_subscription_grant_user_id",
    "CASE WHEN source = 'subscription' AND status = 'active' THEN user_id END")
# The `core.subscriptions` side of the entitled-subscription foreign key, and the fixed
# product-entitled status set its `CASE` arm names.
# [impl->req~schema-access-grants-entitled-subscription-generated-fk~1]
PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN = GeneratedColumn(
    "product_entitled_subscription_id",
    "CASE WHEN status IN ('active', 'grace_period') THEN id END")
ENTITLED_STATUS_SET: frozenset[SubscriptionStatus] = PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES

# The lower-bound existence foreign key: an anti-abuse-eligible grant must point at an existing
# anti-abuse row at commit. Deferrable, so the two rows may be inserted in either order.
# [impl->req~schema-access-grants-required-anti-abuse-fk~1]
ANTI_ABUSE_REQUIRED_FK = ForeignKeyFact(
    (ANTI_ABUSE_REQUIRED_COLUMN.name,), ANTI_ABUSE_TABLE, ("grant_id",), deferrable=True)

# Owner agreement between an active subscription-backed grant and its canonical subscription,
# on the generated pair, with MATCH SIMPLE so a row with NULLs is skipped.
# [impl->req~schema-access-grants-subscription-owner-composite-fk~1]
SUBSCRIPTION_OWNER_FK = ForeignKeyFact(
    (ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN.name,
     ACTIVE_SUBSCRIPTION_GRANT_USER_COLUMN.name),
    "core.subscriptions", ("id", "user_id"), deferrable=True, match="SIMPLE")

# An active subscription-backed grant may only be backed by a product-entitled subscription.
# [impl->req~schema-access-grants-entitled-subscription-generated-fk~1]
# [impl->req~schema-access-grants-active-requires-entitled-subscription~1]
ENTITLED_SUBSCRIPTION_FK = ForeignKeyFact(
    (ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN.name,),
    "core.subscriptions", (PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN.name,), deferrable=True)

# The deferrable foreign key is the sole enforcement mechanism for the entitled-subscription
# rule: the state cannot exist in committed data, so no read path detects or repairs it.
# [impl->req~schema-access-grants-active-requires-entitled-subscription~1]
ENTITLED_SUBSCRIPTION_ENFORCEMENT: tuple[str, ...] = (ENTITLED_SUBSCRIPTION_FK.target_columns[0],)
ENTITLED_SUBSCRIPTION_READ_PATH_REPAIRS: frozenset[str] = frozenset()


def generated_column_value(column: GeneratedColumn,
                           *,
                           grant_id: UUID,
                           source: AccessGrantSource,
                           status: AccessGrantStatus,
                           user_id: UUID | None = None,
                           subscription_id: UUID | None = None) -> UUID | None:
    """What Postgres stores in one of the grant table's generated columns for this row. Each is
    non-NULL only for the rows its `CASE` arm selects, which is what makes the deferrable foreign
    keys skip every other row."""
    # [impl->req~schema-access-grants-required-anti-abuse-fk~1]
    # [impl->req~schema-access-grants-subscription-owner-composite-fk~1]
    # [impl->req~schema-access-grants-entitled-subscription-generated-fk~1]
    if column is ANTI_ABUSE_REQUIRED_COLUMN:
        return grant_id if requires_anti_abuse_row(source) else None
    active_subscription = (source is AccessGrantSource.subscription
                           and status is AccessGrantStatus.active)
    if column is ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN:
        return subscription_id if active_subscription else None
    if column is ACTIVE_SUBSCRIPTION_GRANT_USER_COLUMN:
        return user_id if active_subscription else None
    raise GrantSchemaError(f"{column.name} is no generated column of {ACCESS_GRANTS_TABLE}")


def assert_active_subscription_owner(*,
                                    source: AccessGrantSource,
                                    status: AccessGrantStatus,
                                    grant_user_id: UUID,
                                    subscription_user_id: UUID | None) -> None:
    """An active subscription-backed grant's `user_id` must equal its linked subscription's
    `user_id` at commit. Terminal subscription-backed rows and non-subscription grants generate
    NULLs and are not subject to the check; a grant's `user_id` is never rewritten to reach the
    agreement."""
    # [impl->req~schema-access-grants-subscription-owner-composite-fk~1]
    if generated_column_value(ACTIVE_SUBSCRIPTION_GRANT_USER_COLUMN,
                              grant_id=UUID(int=0), source=source, status=status,
                              user_id=grant_user_id) is None:
        return
    assert_owner_agreement(grant_user_id=grant_user_id,
                           subscription_user_id=subscription_user_id)


def assert_active_subscription_entitled(*,
                                       status: AccessGrantStatus,
                                       subscription_status: SubscriptionStatus) -> None:
    """Activating a subscription-backed grant whose linked subscription is not product-entitled
    cannot commit: the deferrable foreign key to `product_entitled_subscription_id` finds no
    target row. This is that same condition, taken by the writer before it proposes the row."""
    # [impl->req~schema-access-grants-active-requires-entitled-subscription~1]
    # [impl->req~schema-access-grants-entitled-subscription-generated-fk~1]
    # [impl->req~restore-invariant-04~2]
    if ENTITLED_SUBSCRIPTION_READ_PATH_REPAIRS:
        raise GrantSchemaError(
            "the deferrable foreign key is the sole enforcement mechanism; no read path repairs")
    if ENTITLED_STATUS_SET != PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES:
        raise GrantSchemaError("the product-entitled status set is fixed at (active, grace_period)")
    if status is not AccessGrantStatus.active:
        return
    if not is_product_entitled(subscription_status):
        raise GrantSchemaError(
            f"a subscription-backed grant cannot be active while its subscription is "
            f"{subscription_status}")


# --- Proposing one `core.access_grants` row ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class GrantRowProposal:
    """One row a creator proposes for `core.access_grants`."""
    id: UUID
    user_id: UUID
    tier_id: str
    source: AccessGrantSource
    status: AccessGrantStatus
    starts_at: datetime
    ends_at: datetime | None = None
    subscription_id: UUID | None = None


def access_grant_row(*,
                     grant_id: UUID,
                     user_id: UUID,
                     tier_id: str,
                     source: AccessGrantSource,
                     status: AccessGrantStatus = AccessGrantStatus.active,
                     starts_at: datetime,
                     ends_at: datetime | None = None,
                     subscription_id: UUID | None = None,
                     now: datetime | None = None,
                     columns: Iterable[str] = ()) -> GrantRowProposal:
    """One entitlement row, checked against every column-level rule the table carries.

    It belongs to one user and names one tier; a `subscription` grant names its billing row and a
    grant of any other source names none; it is never future-dated; and a non-NULL `ends_at` is
    later than `starts_at`.
    """
    # [impl->req~schema-access-grants-purpose~1]
    # [impl->req~schema-access-grants-one-user-per-grant~1]
    # [impl->req~schema-access-grants-one-tier-per-grant~1]
    if not tier_id:
        raise GrantSchemaError(f"a grant names one {GRANT_TIER_FK.target_table} row")
    assert_entitlement_state_only(columns)
    # [impl->req~schema-access-grants-subscription-source-requires-subscription-id~1]
    # [impl->req~schema-access-grants-non-subscription-no-subscription-id~1]
    assert_subscription_id_shape(source, subscription_id)
    # [impl->req~schema-access-grants-no-future-dating~1]
    assert_not_future_dated(starts_at, now=now if now is not None else starts_at)
    # [impl->req~schema-access-grants-ends-at-after-starts-at~1]
    assert_ends_after_starts(starts_at, ends_at)
    return GrantRowProposal(id=grant_id, user_id=user_id, tier_id=tier_id, source=source,
                            status=status, starts_at=starts_at, ends_at=ends_at,
                            subscription_id=subscription_id)


def assert_subscription_id_shape(source: AccessGrantSource,
                                 subscription_id: UUID | None) -> None:
    """The table CHECK on `(source, subscription_id)`, both ways round: `source =
    'subscription'` must carry a `subscription_id`, and every other source must carry none."""
    # [impl->req~schema-access-grants-subscription-source-requires-subscription-id~1]
    # [impl->req~schema-access-grants-non-subscription-no-subscription-id~1]
    assert_billing_separation(source, subscription_id)


SUBSCRIPTION_ID_CHECK: str = (
    "(source = 'subscription' AND subscription_id IS NOT NULL) "
    "OR (source <> 'subscription' AND subscription_id IS NULL)")
ENDS_AT_CHECK: str = "ends_at IS NULL OR ends_at > starts_at"


def assert_ends_after_starts(starts_at: datetime, ends_at: datetime | None) -> None:
    """A non-null `ends_at` must be later than `starts_at`, enforced as a table CHECK."""
    # [impl->req~schema-access-grants-ends-at-after-starts-at~1]
    if ends_at is not None and ends_at <= starts_at:
        raise GrantSchemaError(f"ends_at {ends_at} is not later than starts_at {starts_at}")


def assert_not_future_dated(starts_at: datetime, *, now: datetime) -> None:
    """No grant is future-dated: `starts_at` is at or before the row's creation/activation
    time."""
    # [impl->req~schema-access-grants-no-future-dating~1]
    if starts_at > now:
        raise GrantSchemaError(f"a grant starting at {starts_at} would be future-dated at {now}")


# --- How free and paid access are represented -------------------------------------------------


class AccessRepresentation(StrEnum):
    """How each kind of product access is written down."""
    grant_row_only = "grant_row_only"
    subscription_row_plus_grant_row = "subscription_row_plus_grant_row"


def access_representation(source: AccessGrantSource) -> AccessRepresentation:
    """Anonymous device grants, registered account grants and manual grants are grant rows with
    no billing row: they are never written as fake subscriptions. Paid access is a
    `core.subscriptions` row plus a subscription-backed grant row."""
    # [impl->req~schema-access-grants-free-and-manual-not-fake-subscriptions~1]
    # [impl->req~schema-access-grants-paid-access-shape~1]
    if source in NON_SUBSCRIPTION_GRANT_SOURCES:
        return AccessRepresentation.grant_row_only
    if source is AccessGrantSource.subscription:
        return AccessRepresentation.subscription_row_plus_grant_row
    raise GrantSchemaError(f"{source} is no core.access_grant_source value")


def paid_access_rows(*, subscription_id: UUID, grant_id: UUID) -> tuple[str, ...]:
    """The two rows paid subscription access is: the billing row and the grant row that points at
    it. One without the other is not paid access."""
    # [impl->req~schema-access-grants-paid-access-shape~1]
    if subscription_id is None or grant_id is None:
        raise GrantSchemaError("paid access is a subscription row plus a grant row")
    return ("core.subscriptions", ACCESS_GRANTS_TABLE)


# `source` records which of the four sources issued the grant — the whole enumeration — and is
# what database grant state is reconciled against per-device device-check state through, where a
# per-device gate applies at all.
# [impl->req~schema-access-grants-source-enumeration~1]
GRANT_SOURCE_VALUES: tuple[AccessGrantSource, ...] = (
    AccessGrantSource.anonymous_device_grant,
    AccessGrantSource.registered_account_grant,
    AccessGrantSource.subscription,
    AccessGrantSource.manual,
)
# Only the native anonymous shape has per-device device-check state to reconcile against.
# [impl->req~schema-access-grants-source-enumeration~1]
DEVICE_CHECK_RECONCILED_SOURCES: frozenset[AccessGrantSource] = frozenset({
    AccessGrantSource.anonymous_device_grant,
})


def reconciles_with_device_check_state(source: AccessGrantSource) -> bool:
    """Whether database grant state for this source is reconciled against per-device
    device-check state. The registered, subscription and manual sources have no per-device bit to
    reconcile with."""
    # [impl->req~schema-access-grants-source-enumeration~1]
    if source not in GRANT_SOURCE_VALUES:
        raise GrantSchemaError(f"{source} is not one of the four grant sources")
    return source in DEVICE_CHECK_RECONCILED_SOURCES


# --- The active-grant axis, and the lazy expiry flip ------------------------------------------


def assert_one_active_per_user(statuses: Sequence[AccessGrantStatus]) -> None:
    """At most one grant with `status = 'active'` may exist for a user, whatever the sources of
    the rows involved."""
    # [impl->req~schema-access-grants-one-active-per-user~1]
    active = [status for status in statuses if status is AccessGrantStatus.active]
    if len(active) > 1:
        raise GrantSchemaError(
            f"{len(active)} active grants for one user; {ACTIVE_GRANT_INDEX.name} allows one")


def participates_in_access_calculation(grant: Any, now: datetime) -> bool:
    """Only the active, non-expired grant participates in access calculation. This is the shared
    effective-grant predicate, not a second definition of currentness."""
    # [impl->req~schema-access-grants-only-active-participates~1]
    return is_effective(grant, now)


# No exclusion constraint replaces the active-grant index, it is never made `DEFERRABLE`, and no
# application path rejects its violation: restore's expire-before-activate statement ordering
# makes the violation unreachable under correct input.
# [impl->req~schema-access-grants-active-index-non-deferrable~1]
ACTIVE_INDEX_REPLACEMENTS: frozenset[str] = frozenset()
ACTIVE_INDEX_REJECTION_PATHS: frozenset[str] = frozenset()


def active_index_violation_outcome(*, retryable: bool = True) -> RaceOutcome:
    """What a violation of `ix_access_grants_one_active_per_user` does if it ever fires — a
    concurrent restore, or a bug. There is no application rejection path: the transaction fails
    and the caller sees a conflict or retry-class error."""
    # [impl->req~schema-access-grants-active-index-non-deferrable~1]
    if ACTIVE_INDEX_REPLACEMENTS or ACTIVE_INDEX_REJECTION_PATHS:
        raise GrantSchemaError(
            f"{ACTIVE_GRANT_INDEX.name} stays a plain non-deferrable unique index with no "
            "application rejection path")
    return resolve_entitlement_race(committed=False, retryable=retryable)


# The one transaction that flips a time-ended `active` row to `expired`, and the paths that never
# do: there is no scheduled sweeper, and neither `/auth/sync` nor quota enforcement flips.
# [impl->req~schema-access-grants-lazy-expiry-flip~1]
EXPIRY_FLIP_PATHS: frozenset[str] = frozenset({"grant_issuance_or_replacement"})
NON_FLIPPING_PATHS: frozenset[str] = frozenset({"auth_sync", "quota_enforcement",
                                                "scheduled_sweeper"})
EXPIRY_SWEEPERS: frozenset[str] = frozenset()


def lazy_expiry_flip(*,
                    path: str,
                    ended_grant_ids: Sequence[UUID],
                    before_insert: bool = True) -> tuple[UUID, ...]:
    """The rows a path may flip from `active` to `expired`, and when. Only the grant-issuance or
    replacement transaction flips, and only immediately before it inserts the new grant, so the
    status-only unique index stays accurate through the flip."""
    # [impl->req~schema-access-grants-lazy-expiry-flip~1]
    if EXPIRY_SWEEPERS:
        raise GrantSchemaError("no scheduled sweeper flips a time-ended grant")
    if path in NON_FLIPPING_PATHS or path not in EXPIRY_FLIP_PATHS:
        raise GrantSchemaError(f"{path} never performs the lazy expiry flip")
    if not before_insert:
        raise GrantSchemaError("the flip happens immediately before the new grant is inserted")
    return tuple(ended_grant_ids)


# --- The lifetime free-grant slots ------------------------------------------------------------

FREE_GRANT_SOURCES: frozenset[AccessGrantSource] = frozenset({
    AccessGrantSource.anonymous_device_grant,
    AccessGrantSource.registered_account_grant,
})
# The lifetime index has no status predicate, so no later event reopens a consumed slot, and a
# lapsed paid entitlement sends the user to checkout rather than to a new free grant.
# [impl->req~schema-access-grants-lifetime-free-grant-per-source~1]
SLOT_REOPENING_EVENTS: frozenset[str] = frozenset()
ACCESS_AFTER_PAID_LAPSE: str = "paid_checkout"
# One free grant per account across both claim endpoints, whichever endpoint consumed it.
# [impl->req~schema-access-grants-one-free-grant-across-endpoints~1]
FREE_GRANTS_PER_ACCOUNT: int = 1
CLAIM_ENDPOINT_SOURCES: dict[str, AccessGrantSource] = {
    "claim_anonymous_grant": AccessGrantSource.anonymous_device_grant,
    "claim_registered_grant": AccessGrantSource.registered_account_grant,
}


def assert_free_slot_available(source: AccessGrantSource,
                               committed_sources: Iterable[AccessGrantSource]) -> None:
    """The lifetime slot check the partial unique index performs: a user who has ever committed a
    grant of this free source may never commit another, whatever its status became. Only a
    committed row consumes the slot — a failed claim rolls back and consumes nothing — and
    `subscription` and `manual` are outside the predicate entirely."""
    # [impl->req~schema-access-grants-lifetime-free-grant-per-source~1]
    if SLOT_REOPENING_EVENTS:
        raise GrantSchemaError("expiry, revocation or a paid lapse never reopens a free slot")
    if source not in FREE_GRANT_SOURCES:
        return
    if source in set(committed_sources):
        raise GrantSchemaError(
            f"{FREE_GRANT_LIFETIME_INDEX.name} allows one committed {source} grant for life")


def assert_free_grant_eligibility_is_the_unique_violation(*,
                                                          history_query_decided: bool) -> None:
    """Claim code treats the unique violation itself as the concurrency-safe final eligibility
    check. A prior application-level history query is not that check and may not be what decides
    the claim."""
    # [impl->req~schema-access-grants-user-id-source-immutable~1]
    if history_query_decided:
        raise GrantSchemaError(
            "the unique violation, not a prior history query, is the final eligibility check")


def assert_grant_identity_immutable(*,
                                    stored_user_id: UUID,
                                    stored_source: AccessGrantSource,
                                    incoming_user_id: UUID,
                                    incoming_source: AccessGrantSource,
                                    deleted: bool = False) -> None:
    """`user_id` and `source` are immutable after insertion, and a historical free-grant row is
    never deleted — that is what makes a committed free grant occupy its lifetime slot
    permanently."""
    # [impl->req~schema-access-grants-user-id-source-immutable~1]
    if incoming_user_id != stored_user_id:
        raise GrantSchemaError("a grant's user_id is immutable after insertion")
    if incoming_source is not stored_source:
        raise GrantSchemaError("a grant's source is immutable after insertion")
    if deleted and stored_source in FREE_GRANT_SOURCES:
        raise GrantSchemaError("a historical free-grant row is never deleted")


class FreeClaimOutcome(StrEnum):
    """What a claim endpoint does for a user whose free allowance is already accounted for."""
    issued = "issued"
    converted = "converted"
    refused = "refused"


def free_claim_outcome(endpoint: str,
                       *,
                       committed_sources: Iterable[AccessGrantSource],
                       converting_active_anonymous_grant: bool = False) -> FreeClaimOutcome:
    """One free grant per account across both claim endpoints: after any successful claim on
    either endpoint, the other refuses for that user. `claim_registered_grant`'s conversion of
    the user's active anonymous grant is a transition of the same allowance, not a second
    issuance."""
    # [impl->req~schema-access-grants-one-free-grant-across-endpoints~1]
    source = CLAIM_ENDPOINT_SOURCES.get(endpoint)
    if source is None:
        raise GrantSchemaError(f"{endpoint} is not a free-credit claim endpoint")
    committed = set(committed_sources)
    if source in committed or len(committed & FREE_GRANT_SOURCES) >= FREE_GRANTS_PER_ACCOUNT:
        # The allowance is already accounted for. The conversion is a transition of that same
        # allowance and can happen at most once, so a repeat call for a user who already holds the
        # committed registered grant is refused here rather than converting a second time.
        if (converting_active_anonymous_grant
                and source is not AccessGrantSource.registered_account_grant):
            raise GrantSchemaError("only claim_registered_grant converts an anonymous grant")
        if (converting_active_anonymous_grant and source not in committed
                and AccessGrantSource.anonymous_device_grant in committed):
            return FreeClaimOutcome.converted
        return FreeClaimOutcome.refused
    if converting_active_anonymous_grant:
        if source is not AccessGrantSource.registered_account_grant:
            raise GrantSchemaError("only claim_registered_grant converts an anonymous grant")
        raise GrantSchemaError("the conversion path needs the user's active anonymous grant")
    return FreeClaimOutcome.issued


# --- Subscription-backed grants: ingestion, renewal, restore ----------------------------------

# The creating operations of a subscription-backed grant, and nothing else. Verified purchase
# ingestion creates them; restore's adoption of an unclaimed subscription is the only other
# creator, and later terms come from ingestion's per-term renewal rather than from restore.
# [impl->req~schema-access-grants-ingestion-creates-subscription-grant~1]
SUBSCRIPTION_GRANT_CREATORS: tuple[GrantCreator, ...] = (
    GrantCreator.purchase_ingestion,
    GrantCreator.renewal_term_insert,
    GrantCreator.restore_adoption,
)


@dataclass(frozen=True, slots=True)
class IngestedTerm:
    """The rows one paid term's ingestion transaction writes. A redelivered term writes none, so
    it carries no usage row at all: the live counter is left exactly as it stands."""
    grant: GrantRowProposal
    usage: NewUsageRow | None = None
    expired_grant_ids: tuple[UUID, ...] = ()
    idempotent_no_op: bool = False
    deleted_grant_ids: tuple[UUID, ...] = field(default_factory=tuple)


def resolve_subscription_tier(store_product_id: str,
                             product_id_to_tier: Mapping[str, str],
                             *,
                             client_supplied_tier_id: str | None = None) -> str:
    """The tier of a subscription-backed grant, resolved at creation from the server-controlled
    store-product-ID-to-tier mapping. Client input never names the tier."""
    # [impl->req~schema-access-grants-ingestion-creates-subscription-grant~1]
    if client_supplied_tier_id is not None:
        raise GrantSchemaError("the grant's tier is never resolved from client input")
    tier_id = product_id_to_tier.get(store_product_id)
    if tier_id is None:
        raise GrantSchemaError(f"{store_product_id!r} maps to no access tier")
    return tier_id


def ingest_subscription_term(*,
                            creator: GrantCreator,
                            grant_id: UUID,
                            user_id: UUID,
                            subscription_id: UUID,
                            store_product_id: str,
                            product_id_to_tier: Mapping[str, str],
                            subscription_status: SubscriptionStatus,
                            starts_at: datetime,
                            ends_at: datetime | None = None,
                            blocking_grant_ids: Sequence[UUID] = (),
                            transaction: object = None,
                            usage_transaction: object = None,
                            existing_term_grant_id: UUID | None = None,
                            client_supplied_tier_id: str | None = None,
                            free_tier_monthly_used: int | None = None) -> IngestedTerm:
    """Verified purchase ingestion, as one transaction — the grant-side view of the flow
    `store_purchases` owns end to end.

    One grant row per paid term under the flip-then-insert renewal flow: any index-blocking grant
    is expired first — never deleted — then the new grant and its `core.user_monthly_usage` row,
    seeded `monthly_used = 0`, are inserted. Free-tier usage is never copied into the paid
    counter. The tier comes from the server-controlled store-product mapping. A redelivered
    same-term event is an idempotent no-op: it duplicates no grant and writes no usage row, so the
    live counter cannot be reset by one.

    The ordering rules themselves are not restated here: the redelivery no-op is
    `store_purchases.renew_per_term`'s and the expire-before-insert half, with its reason and its
    "no insert has been recorded yet" check, is `store_purchases.expire_before_insert`'s. What this
    function adds is the schema's own facts — which creators may produce a subscription-backed
    grant, which paths may flip a time-ended row, and the grant and usage row shapes.
    """
    # [impl->req~schema-access-grants-ingestion-creates-subscription-grant~1]
    from nativespeaker.api.auth.store_purchases import (  # noqa: PLC0415
        IngestionLedger,
        expire_before_insert,
        renew_per_term,
    )

    if creator not in SUBSCRIPTION_GRANT_CREATORS:
        raise GrantSchemaError(f"{creator} does not create a subscription-backed grant")
    assert_grant_creator(creator, AccessGrantSource.subscription)
    if transaction is None:
        raise GrantSchemaError("ingestion names the one transaction it writes both rows in")
    if free_tier_monthly_used:
        raise GrantSchemaError("free-tier usage is never copied into the paid counter")
    tier_id = resolve_subscription_tier(store_product_id, product_id_to_tier,
                                       client_supplied_tier_id=client_supplied_tier_id)
    # A redelivery of the term that already has its grant changes nothing at all.
    if existing_term_grant_id is not None:
        renewal = renew_per_term(active_grant_id=existing_term_grant_id, time_ended=False,
                                 already_applied=True)
        if not renewal.idempotent_no_op or renewal.new_grant_id is not None:
            raise GrantSchemaError("a redelivered term duplicates no grant and writes no usage")
        return IngestedTerm(
            grant=GrantRowProposal(id=existing_term_grant_id, user_id=user_id, tier_id=tier_id,
                                   source=AccessGrantSource.subscription,
                                   status=AccessGrantStatus.active, starts_at=starts_at,
                                   ends_at=ends_at, subscription_id=subscription_id),
            usage=None, idempotent_no_op=True)
    # The flip half of flip-then-insert: the blocking row is expired, never deleted, and recorded
    # with its reason before any insert statement.
    lazy_expiry_flip(path="grant_issuance_or_replacement", ended_grant_ids=blocking_grant_ids)
    expired = expire_before_insert(blocking_grant_ids, ledger=IngestionLedger())
    assert_active_subscription_entitled(status=AccessGrantStatus.active,
                                       subscription_status=subscription_status)
    grant = access_grant_row(grant_id=grant_id, user_id=user_id, tier_id=tier_id,
                             source=AccessGrantSource.subscription,
                             status=AccessGrantStatus.active,
                             starts_at=starts_at, ends_at=ends_at,
                             subscription_id=subscription_id, now=starts_at)
    usage = new_usage_row(
        grant_id, now=starts_at, grant_transaction=transaction,
        usage_transaction=transaction if usage_transaction is None else usage_transaction)
    return IngestedTerm(grant=grant, usage=usage, expired_grant_ids=expired)


def assert_one_active_grant_per_subscription(subscription_ids: Sequence[UUID]) -> None:
    """`subscription_id` is unique among active subscription-backed grants; the superseded term
    rows stay in history under the same `subscription_id`."""
    # [impl->req~schema-access-grants-subscription-id-unique-among-active~1]
    if len(set(subscription_ids)) != len(subscription_ids):
        raise GrantSchemaError(
            f"{ONE_ACTIVE_GRANT_PER_SUBSCRIPTION_INDEX.name} allows one active grant per "
            "subscription")


class RestoreGrantAction(StrEnum):
    """What `restore_subscription` may do to subscription-backed grant state."""
    settle_in_place = "settle_in_place"
    adopt_unclaimed = "adopt_unclaimed"
    reject_owner_mismatch = "reject_owner_mismatch"


def restore_grant_action(*,
                         same_account: bool,
                         existing_grant_id: UUID | None,
                         subscription_owner_id: UUID | None,
                         destination_user_id: UUID) -> RestoreGrantAction:
    """Restore never creates a second active subscription-backed grant for one store
    subscription: same-account restore settles the current-term grant in place, adoption of an
    unclaimed subscription creates that subscription's first grant row, and an owner-mismatched
    restore is rejected. Later terms are ingestion's per-term renewal, not restore's."""
    # [impl->req~schema-access-grants-restore-no-second-active-subscription-grant~1]
    if subscription_owner_id is not None and subscription_owner_id != destination_user_id:
        return RestoreGrantAction.reject_owner_mismatch
    if same_account:
        if existing_grant_id is None:
            raise GrantSchemaError(
                "same-account restore settles the current-term grant it found in place")
        return RestoreGrantAction.settle_in_place
    if existing_grant_id is not None:
        raise GrantSchemaError(
            "adoption creates the first grant row for an unclaimed subscription only")
    return RestoreGrantAction.adopt_unclaimed


def assert_lifecycle_updates_share_transaction(*,
                                              subscription_transaction: object,
                                              grant_transaction: object) -> None:
    """A subscription lifecycle update that changes entitlement state updates the linked grant
    state in the same transaction, so the deferred foreign keys hold at commit."""
    # [impl->req~schema-access-grants-lifecycle-same-transaction~1]
    assert_same_transaction("subscription_lifecycle_ingestion",
                            [subscription_transaction, grant_transaction])


# --- Monthly usage is owned by the grant ------------------------------------------------------

# Grant rows are access facts and own monthly usage state: consumption is stored on
# `core.user_monthly_usage`, keyed by `grant_id`.
# [impl->req~schema-access-grants-owns-monthly-usage~1]
MONTHLY_USAGE_TABLE: str = "core.user_monthly_usage"
MONTHLY_USAGE_OWNER_COLUMN: str = "grant_id"


def monthly_usage_owner(grant: GrantRowProposal) -> tuple[str, UUID]:
    """Which row owns a grant's monthly usage state: the usage row keyed by this grant's `id`.
    Usage is never keyed by the user, so it can never outlive or move off its grant."""
    # [impl->req~schema-access-grants-owns-monthly-usage~1]
    return MONTHLY_USAGE_TABLE, grant.id


# --- The anti-abuse row beside a free-credit grant --------------------------------------------

# This file's own table semantics are the sole normative owner of the anti-abuse row shape: the
# column set, the `core.native_claim_provider` enum, and the per-source CHECK. No other file
# states a competing shape enumeration.
# [impl->req~schema-access-grants-anti-abuse-sole-row-shape-owner~1]
ANTI_ABUSE_ROW_SHAPE_OWNER: str = "06-schema-reference.md"
COMPETING_ROW_SHAPE_ENUMERATIONS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class AntiAbuseColumn:
    """One `core.access_grants_anti_abuse` column and what it means."""
    name: str
    sql_type: str
    nullable: bool
    meaning: str


# The row's whole column set, in order. `grant_id` is the primary key, which is what caps the
# table at one row per grant.
# [impl->req~schema-access-grants-anti-abuse-grant-id-field~1]
ANTI_ABUSE_KEY: str = "grant_id"
ANTI_ABUSE_COLUMNS: tuple[AntiAbuseColumn, ...] = (
    # [impl->req~schema-access-grants-anti-abuse-grant-id-field~1]
    AntiAbuseColumn("grant_id", "UUID", False, "primary key; the grant this evidence belongs to"),
    # [impl->req~schema-access-grants-anti-abuse-grant-source-field~1]
    AntiAbuseColumn("grant_source", "core.access_grant_source", False,
                    "pinned to the linked grant's source by the composite foreign key"),
    # [impl->req~schema-access-grants-anti-abuse-native-claim-provider-field~1]
    AntiAbuseColumn("native_claim_provider", "core.native_claim_provider", True,
                    "the provider of the platform-managed per-device claim state"),
    # [impl->req~schema-access-grants-anti-abuse-idp-account-hash-field~1]
    AntiAbuseColumn("idp_account_hash", "BYTEA", True,
                    "HMAC alias of the stable provider account identifier"),
    # [impl->req~schema-access-grants-anti-abuse-idp-hash-key-version-field~1]
    AntiAbuseColumn("idp_account_hash_key_version", "SMALLINT", True,
                    "the HMAC key version the alias was derived with"),
    # The generated key the registered gate's uniqueness and the grant side's foreign key hang off;
    # it is part of the row shape this file owns.
    # [impl->req~schema-access-grants-anti-abuse-sole-row-shape-owner~1]
    AntiAbuseColumn("registered_account_grant_id", "UUID", True,
                    "generated: the grant id on registered-account-grant rows, unique"),
    # [impl->req~schema-access-grants-anti-abuse-created-at-field~1]
    AntiAbuseColumn("created_at", "TIMESTAMPTZ", False, "insert timestamp"),
)

# The generated column above, with the arm that populates it and the uniqueness it carries.
# [impl->req~schema-access-grants-anti-abuse-sole-row-shape-owner~1]
REGISTERED_ACCOUNT_GRANT_COLUMN = GeneratedColumn(
    "registered_account_grant_id",
    "CASE WHEN grant_source = 'registered_account_grant' THEN grant_id END")
REGISTERED_ACCOUNT_GRANT_UNIQUE_ON: tuple[str, ...] = (REGISTERED_ACCOUNT_GRANT_COLUMN.name,)

# The composite foreign key that binds the row to its grant, with the three declarative
# properties it supplies at once: source agreement, cascade on delete, and either-order insertion
# inside one transaction.
# [impl->req~schema-access-grants-anti-abuse-composite-fk-properties~1]
# [impl->req~schema-access-grants-anti-abuse-grant-id-field~1]
# [impl->req~schema-access-grants-anti-abuse-grant-source-field~1]
ANTI_ABUSE_COMPOSITE_FK = ForeignKeyFact(
    ("grant_id", "grant_source"), ACCESS_GRANTS_TABLE, ID_SOURCE_FK_TARGET,
    deferrable=True, on_delete="CASCADE")

# The per-source CHECK's first half: `grant_source` is restricted to the two anti-abuse-eligible
# sources, so no row can exist for a `subscription` or `manual` grant.
# [impl->req~schema-access-grants-anti-abuse-no-row-for-other-sources~1]
ANTI_ABUSE_SOURCE_CHECK: str = (
    "grant_source IN ('anonymous_device_grant', 'registered_account_grant')")

# `grant_source` is not database-enforced provenance either: the composite foreign key only makes
# it agree with the linked grant's `source` at commit.
# [impl->req~schema-access-grants-anti-abuse-composite-fk-properties~1]
GRANT_SOURCE_PROVENANCE_MECHANISMS: frozenset[str] = frozenset()


class AntiAbuseBound(StrEnum):
    """The three bounds that together make "exactly one anti-abuse row per eligible grant"."""
    at_most_one = "at_most_one"
    none_for_other_sources = "none_for_other_sources"
    at_least_one = "at_least_one"


# Each bound and the declarative mechanism that enforces it. All three are schema-enforced: no
# application check is the enforcement, and none is needed.
# [impl->req~schema-access-grants-exactly-one-anti-abuse-row~1]
# [impl->req~schema-access-grants-anti-abuse-exactly-one-declarative~1]
ANTI_ABUSE_ROW_BOUNDS: dict[AntiAbuseBound, str] = {
    AntiAbuseBound.at_most_one: f"{ANTI_ABUSE_TABLE}.{ANTI_ABUSE_KEY} primary key",
    AntiAbuseBound.none_for_other_sources:
        f"composite foreign key on {ANTI_ABUSE_COMPOSITE_FK.columns} plus the per-source CHECK",
    AntiAbuseBound.at_least_one:
        f"deferrable foreign key from {ANTI_ABUSE_REQUIRED_COLUMN.name}",
}


def anti_abuse_row_bounds() -> dict[AntiAbuseBound, str]:
    """The three declarative bounds, read back as one set. The deferrable foreign keys still let
    either claim insert the grant row and the anti-abuse row in either order inside one
    transaction."""
    # [impl->req~schema-access-grants-exactly-one-anti-abuse-row~1]
    # [impl->req~schema-access-grants-anti-abuse-exactly-one-declarative~1]
    if not (ANTI_ABUSE_REQUIRED_FK.deferrable and ANTI_ABUSE_COMPOSITE_FK.deferrable):
        raise GrantSchemaError("both anti-abuse foreign keys are DEFERRABLE INITIALLY DEFERRED")
    return dict(ANTI_ABUSE_ROW_BOUNDS)


def assert_anti_abuse_row_presence(source: AccessGrantSource,
                                   anti_abuse_grant_source: AccessGrantSource | None) -> None:
    """Every `anonymous_device_grant` and `registered_account_grant` row has one anti-abuse row
    whose `grant_source` equals the grant's `source`; a `subscription` or `manual` grant has
    none."""
    # [impl->req~schema-access-grants-requires-anti-abuse-row~1]
    # [impl->req~schema-access-grants-anti-abuse-purpose~1]
    # [impl->req~schema-access-grants-anti-abuse-no-row-for-other-sources~1]
    assert_anti_abuse_pairing(source, anti_abuse_grant_source)


def assert_anti_abuse_lower_bound(*,
                                  source: AccessGrantSource,
                                  grant_id: UUID,
                                  anti_abuse_grant_ids: Iterable[UUID],
                                  grant_transaction: object = None,
                                  anti_abuse_transaction: object = None) -> None:
    """The lower bound the deferrable foreign key from `anti_abuse_required_grant_id` enforces at
    commit: an anti-abuse-eligible grant must point at an existing anti-abuse row. Insertion
    order inside the transaction is free, which is what "deferrable" buys."""
    # [impl->req~schema-access-grants-required-anti-abuse-fk~1]
    if grant_transaction is not anti_abuse_transaction:
        raise GrantSchemaError("the grant row and its anti-abuse row commit in one transaction")
    required = generated_column_value(ANTI_ABUSE_REQUIRED_COLUMN, grant_id=grant_id,
                                      source=source, status=AccessGrantStatus.active)
    if required is None:
        return
    if required not in set(anti_abuse_grant_ids):
        raise GrantSchemaError(
            f"a {source} grant must point at an existing {ANTI_ABUSE_TABLE} row at commit")


def assert_registered_grant_hash_recorded(*,
                                          idp_account_hash: bytes | None,
                                          idp_account_hash_key_version: int | None) -> None:
    """An active `registered_account_grant` carries `idp_account_hash` and
    `idp_account_hash_key_version` on its anti-abuse row, and no `native_claim_provider`, as the
    per-source CHECK requires."""
    # [impl->req~schema-access-grants-registered-grant-hash-required~1]
    # [impl->req~schema-access-grants-anti-abuse-registered-shape-required~1]
    anti_abuse_evidence(grant_source=AccessGrantSource.registered_account_grant,
                        idp_account_hash=idp_account_hash,
                        idp_account_hash_key_version=idp_account_hash_key_version)


def assert_native_write_precedes_activation(*,
                                            source: AccessGrantSource,
                                            native_claim_written: bool,
                                            same_attempt: bool) -> None:
    """For the native anonymous-device-grant shape, the successful native claimed-state write
    comes first, in the same attempt, and only then is the `active` grant row created. The
    ordering is a `claim_anonymous_grant` operation rule, not a schema constraint. Web anonymous
    rows are governed by the web provider-account gate instead."""
    # [impl->req~schema-access-grants-native-write-before-activation~1]
    if source is not AccessGrantSource.anonymous_device_grant:
        raise GrantSchemaError(f"{source} has no native claimed-state ordering rule")
    assert_native_claim_written_before_grant(native_claim_written=native_claim_written,
                                            same_attempt=same_attempt)


# --- The two anonymous evidence forms, and the four valid tuples ------------------------------


class AntiAbuseForm(StrEnum):
    """The forms the per-source CHECK admits."""
    native = "native"
    web = "web"
    registered = "registered"


def anti_abuse_form(*,
                    grant_source: AccessGrantSource,
                    native_claim_provider: NativeClaimPlatform | None = None,
                    idp_account_hash: bytes | None = None,
                    idp_account_hash_key_version: int | None = None) -> AntiAbuseForm:
    """Which form a proposed row is, refusing every shape the per-source CHECK rejects.

    An `anonymous_device_grant` row is either the native form — `native_claim_provider` set,
    both IDP-account columns NULL — or the web form — `native_claim_provider` NULL, both
    IDP-account columns set. A `registered_account_grant` row is the registered form: IDP-account
    evidence and no `native_claim_provider`.
    """
    # [impl->req~schema-access-grants-anti-abuse-anonymous-shape-forms~1]
    # [impl->req~schema-access-grants-anti-abuse-registered-shape-required~1]
    # [impl->req~schema-access-grants-anti-abuse-native-claim-provider-field~1]
    # [impl->req~schema-access-grants-anti-abuse-idp-account-hash-field~1]
    # [impl->req~schema-access-grants-anti-abuse-idp-hash-key-version-field~1]
    evidence = anti_abuse_evidence(grant_source=grant_source,
                                   native_claim_provider=native_claim_provider,
                                   idp_account_hash=idp_account_hash,
                                   idp_account_hash_key_version=idp_account_hash_key_version)
    if grant_source is AccessGrantSource.registered_account_grant:
        return AntiAbuseForm.registered
    return (AntiAbuseForm.native if evidence is AntiAbuseEvidence.native_device_check
            else AntiAbuseForm.web)


# The native form is identical on both platforms except for the recorded provider value.
# [impl->req~schema-access-grants-anti-abuse-native-form-cross-platform~1]
NATIVE_CLAIM_PROVIDERS: dict[DevicePlatform, NativeClaimPlatform] = {
    DevicePlatform.ios: NativeClaimPlatform.ios_devicecheck,
    DevicePlatform.android: NativeClaimPlatform.android_play_integrity,
}
# A commit failure after the confirmed vendor write is not compensated: nothing clears or
# reconciles the vendor bit, and the affected device falls back to registered sign-up.
# [impl->req~schema-access-grants-anti-abuse-native-form-cross-platform~1]
VENDOR_BIT_COMPENSATIONS: frozenset[str] = frozenset()
VENDOR_BIT_FALLBACK: str = "registered_sign_up"


def native_claim_provider_for(platform: DevicePlatform) -> NativeClaimPlatform:
    """The `native_claim_provider` value a native claim records. An Android claim records
    `android_play_integrity`; recording it as `ios_devicecheck` as a compatibility workaround is
    never allowed."""
    # [impl->req~schema-access-grants-anti-abuse-native-claim-provider-field~1]
    # [impl->req~schema-access-grants-anti-abuse-native-form-cross-platform~1]
    provider = NATIVE_CLAIM_PROVIDERS.get(platform)
    if provider is None:
        raise GrantSchemaError(f"{platform} has no native anonymous-device-grant form")
    return provider


def native_claim_write_order(platform: DevicePlatform) -> tuple[str, ...]:
    """The native form's one ordering, the same on both platforms: write and receive vendor
    confirmation of the per-device bit, then insert the anti-abuse row and the grant row in one
    transaction under the deferrable foreign keys. No per-platform redesign, and no compensation
    if the commit then fails."""
    # [impl->req~schema-access-grants-anti-abuse-native-form-cross-platform~1]
    if VENDOR_BIT_COMPENSATIONS:
        raise GrantSchemaError("the vendor bit is never cleared or reconciled")
    native_claim_provider_for(platform)
    return ("vendor_bit_write_confirmed", "anti_abuse_row_insert", "grant_row_insert", "commit")


# Request-scoped attestation artifacts an IdP account hash is never synthesized from: the vendor
# bit itself is the native evidence.
# [impl->req~schema-access-grants-anti-abuse-no-hash-from-attestation~1]
ATTESTATION_ARTIFACTS: frozenset[str] = frozenset({
    "play_integrity_token", "device_recall_value", "recall_value", "package_name",
    "devicecheck_token", "attestation_object", "assertion",
})


def assert_hash_not_derived_from_attestation(artifacts: Iterable[str]) -> None:
    """No native path derives `idp_account_hash` from device-attestation evidence."""
    # [impl->req~schema-access-grants-anti-abuse-no-hash-from-attestation~1]
    offending = sorted(ATTESTATION_ARTIFACTS.intersection(str(name) for name in artifacts))
    if offending:
        raise GrantSchemaError(f"{offending} never yields an idp_account_hash")


# Adding the Android enum value is additive: no valid Android row could exist under the prior
# contract, so there is nothing to backfill, and iOS, web anonymous and registered rows are
# untouched. The enum value and the corrected CHECK ship before the Android grant path deploys.
# [impl->req~schema-access-grants-anti-abuse-android-enum-additive~1]
ANDROID_ENUM_VALUE: NativeClaimPlatform = NativeClaimPlatform.android_play_integrity
ANDROID_ROLLOUT_BACKFILLS: frozenset[str] = frozenset()
ANDROID_ROLLOUT_ORDER: tuple[str, ...] = ("enum_value_and_check", "android_grant_path_deploy")


def assert_android_enum_rollout_additive(*,
                                        rows_affected: Iterable[str] = (),
                                        deploy_order: Sequence[str] | None = None) -> None:
    """The Android rollout is additive with no backfill and no effect on existing rows."""
    # [impl->req~schema-access-grants-anti-abuse-android-enum-additive~1]
    if ANDROID_ROLLOUT_BACKFILLS or list(rows_affected):
        raise GrantSchemaError("adding the Android enum value backfills and affects nothing")
    if tuple(deploy_order or ANDROID_ROLLOUT_ORDER) != ANDROID_ROLLOUT_ORDER:
        raise GrantSchemaError("the enum value and the corrected CHECK land first")


@dataclass(frozen=True, slots=True)
class EvidenceTuple:
    """One evidence tuple, as the conformance test proposes it."""
    label: str
    grant_source: AccessGrantSource
    native_claim_provider: NativeClaimPlatform | None
    idp_account_hash: bytes | None
    idp_account_hash_key_version: int | None


# The four valid evidence tuples the schema accepts.
# [impl->req~schema-access-grants-anti-abuse-conformance-test-tuples~1]
VALID_EVIDENCE_TUPLES: tuple[EvidenceTuple, ...] = (
    EvidenceTuple("native_ios", AccessGrantSource.anonymous_device_grant,
                  NativeClaimPlatform.ios_devicecheck, None, None),
    EvidenceTuple("native_android", AccessGrantSource.anonymous_device_grant,
                  NativeClaimPlatform.android_play_integrity, None, None),
    EvidenceTuple("web_anonymous", AccessGrantSource.anonymous_device_grant,
                  None, b"web-alias", 1),
    EvidenceTuple("registered", AccessGrantSource.registered_account_grant,
                  None, b"registered-alias", 1),
)
# The malformed rows it rejects.
# [impl->req~schema-access-grants-anti-abuse-conformance-test-tuples~1]
MALFORMED_EVIDENCE_TUPLES: tuple[EvidenceTuple, ...] = (
    EvidenceTuple("anonymous_with_neither", AccessGrantSource.anonymous_device_grant,
                  None, None, None),
    EvidenceTuple("native_carrying_hash", AccessGrantSource.anonymous_device_grant,
                  NativeClaimPlatform.ios_devicecheck, b"alias", 1),
    EvidenceTuple("web_carrying_native_provider", AccessGrantSource.anonymous_device_grant,
                  NativeClaimPlatform.ios_devicecheck, b"alias", None),
    EvidenceTuple("registered_carrying_native_provider",
                  AccessGrantSource.registered_account_grant,
                  NativeClaimPlatform.ios_devicecheck, b"alias", 1),
)


def evidence_tuple_form(candidate: EvidenceTuple) -> AntiAbuseForm:
    """The form of one proposed evidence tuple, or a refusal. This is what the schema conformance
    test drives: the four valid tuples resolve to a form, the malformed ones raise."""
    # [impl->req~schema-access-grants-anti-abuse-conformance-test-tuples~1]
    return anti_abuse_form(grant_source=candidate.grant_source,
                           native_claim_provider=candidate.native_claim_provider,
                           idp_account_hash=candidate.idp_account_hash,
                           idp_account_hash_key_version=candidate.idp_account_hash_key_version)


# --- Gate uniqueness, and what a duplicate claim does -----------------------------------------

# Each gate's global uniqueness is enforced on the stable provider UID by one gate-consumption
# row per `(provider_account_id, consumption_kind)`; the two kinds are distinct rows, and
# `idp_account_hash` decides nothing.
# [impl->req~schema-access-grants-anti-abuse-registered-gate-global-uniqueness~1]
# [impl->req~schema-access-grants-anti-abuse-web-gate-uniqueness~1]
GATE_CONSUMPTIONS_TABLE: str = "core.provider_account_gate_consumptions"
GATE_CONSUMPTIONS_KEY: tuple[str, ...] = ("provider_account_id", "consumption_kind")
IDP_ACCOUNT_HASH_IS_AUTHORITATIVE: bool = False
GATE_UNIQUENESS_SCOPE: str = "global_per_canonical_provider_account"


def gate_for(source: AccessGrantSource) -> GateConsumptionKind:
    """Which gate-consumption row a free-credit grant of this source consumes. A registered
    account grant consumes the `registered_account_grant` gate; a web anonymous device grant
    consumes the separate `web_anonymous_gate` row."""
    # [impl->req~schema-access-grants-anti-abuse-registered-gate-global-uniqueness~1]
    # [impl->req~schema-access-grants-anti-abuse-web-gate-uniqueness~1]
    if IDP_ACCOUNT_HASH_IS_AUTHORITATIVE:
        raise GrantSchemaError("idp_account_hash is a lookup and audit alias, never the gate")
    if source is AccessGrantSource.registered_account_grant:
        return GateConsumptionKind.registered_account_grant
    if source is AccessGrantSource.anonymous_device_grant:
        return GateConsumptionKind.web_anonymous_gate
    raise GrantSchemaError(f"a {source} grant consumes no free-credit gate")


# Registered-account-grant activation is governed by the registered-grant activation rules of
# `03-free-credit-grants-and-anti-abuse.md`, never by native claimed state.
# [impl->req~schema-access-grants-anti-abuse-registered-activation-rules~1]
REGISTERED_ACTIVATION_RULES_OWNER: str = "claim_registered_grant"
REGISTERED_ACTIVATION_NATIVE_STATE_INPUTS: frozenset[str] = frozenset()


def assert_registered_activation_not_native_state(inputs: Iterable[str] = ()) -> None:
    """Registered account grant activation reads no native claimed state."""
    # [impl->req~schema-access-grants-anti-abuse-registered-activation-rules~1]
    offending = sorted({str(name) for name in inputs}
                       | REGISTERED_ACTIVATION_NATIVE_STATE_INPUTS)
    if offending:
        raise GrantSchemaError(
            f"{REGISTERED_ACTIVATION_RULES_OWNER}'s activation rules govern, not {offending}")


def assert_no_raw_anti_abuse_material(columns: Iterable[str]) -> None:
    """The row stores no raw DeviceCheck or Play Integrity token, no raw Cloudflare bot-check
    token, no device-check-state hash, no synthetic stable provider device principal hash and no
    raw provider account identifier — web anonymous rows included. Account-level evidence is
    `idp_account_hash` and `idp_account_hash_key_version`, and nothing else."""
    # [impl->req~schema-access-grants-anti-abuse-no-raw-material-stored~1]
    names = [str(column) for column in columns]
    assert_no_raw_device_material(names)
    assert_hash_not_derived_from_attestation(names)
    account_evidence = {"idp_account_hash", "idp_account_hash_key_version"}
    unknown = sorted(set(names) - {column.name for column in ANTI_ABUSE_COLUMNS})
    if unknown:
        raise GrantSchemaError(
            f"{unknown} is not part of the row; account-level evidence is "
            f"{sorted(account_evidence)}")


@dataclass(frozen=True, slots=True)
class DuplicateRejection:
    """How one detected duplicate claim is audited, surfaced, and rolled back."""
    result: AuthEventResult
    client_class: ClientErrorClass
    rolls_back_grant_insert: bool = True


class DuplicateDetection(StrEnum):
    """Where a duplicate free-credit claim was detected."""
    native_device_check_state = "native_device_check_state"
    web_gate = "web_gate"
    registered_gate = "registered_gate"


# The three detections, each with its audited internal result and its client-visible class. The
# anonymous and registered rejection paths are distinct in audit, in class, and in remediation.
# [impl->req~schema-access-grants-duplicate-claim-rejection-results~1]
# [impl->req~schema-access-grants-anti-abuse-native-duplicate-result~1]
# [impl->req~schema-access-grants-anti-abuse-web-duplicate-rollback~1]
# [impl->req~schema-access-grants-anti-abuse-registered-duplicate-result~1]
DUPLICATE_REJECTIONS: dict[DuplicateDetection, DuplicateRejection] = {
    DuplicateDetection.native_device_check_state: DuplicateRejection(*DEVICE_GRANT_BLOCK),
    DuplicateDetection.web_gate: DuplicateRejection(
        *GATE_CONFLICTS[GateConsumptionKind.web_anonymous_gate]),
    DuplicateDetection.registered_gate: DuplicateRejection(
        *GATE_CONFLICTS[GateConsumptionKind.registered_account_grant]),
}


def duplicate_claim_rejection(detection: DuplicateDetection,
                              *,
                              inside_activation: bool = True) -> DuplicateRejection:
    """The audited result and client-visible class of a duplicate free-credit claim, and whether
    the grant insert rolls back.

    A duplicate anonymous-device-grant claim surfaces as `device_grant_exhausted`, audited
    `native_claim_already_claimed` when the per-device device-check state caught it and
    `anti_abuse_already_claimed` when the web IDP-account-hash gate did. A duplicate registered
    claim is audited `idp_account_already_claimed` and surfaces as `account_already_claimed`.
    Detected inside activation, either rolls the grant insert back in the same transaction, so no
    grant rows remain for that attempt.
    """
    # [impl->req~schema-access-grants-duplicate-claim-rejection-results~1]
    # [impl->req~schema-access-grants-anti-abuse-native-duplicate-result~1]
    # [impl->req~schema-access-grants-anti-abuse-web-duplicate-rollback~1]
    # [impl->req~schema-access-grants-anti-abuse-registered-duplicate-result~1]
    rejection = DUPLICATE_REJECTIONS.get(detection)
    if rejection is None:
        raise GrantSchemaError(f"{detection} detects no duplicate claim")
    return DuplicateRejection(result=rejection.result,
                              client_class=rejection.client_class,
                              rolls_back_grant_insert=inside_activation)
