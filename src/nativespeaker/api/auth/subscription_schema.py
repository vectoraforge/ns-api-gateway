"""The row and constraint contract of the four store-subscription tables in the schema reference.

`core.subscriptions` holds the canonical current state of one provider-scoped paid subscription
lifecycle, one row per `(provider, external_id)`, updated in place. `core.store_purchase_tokens`
is the durable token-to-user binding minted once at user creation. `core.store_purchases` is the
purchase-attribution record, one immutable row per accepted store subscription.
`audit.subscription_events` is the append-only observation log beside the canonical row.

Almost every rule here is enforced by the declarative schema — the unique keys, the generated
`product_entitled_subscription_id` column, the composite foreign keys and the table CHECK. This
module is the write side of that contract: it declares the constraint facts the applied DDL must
carry, and it refuses to hand a write path a row or a transaction plan the schema would reject at
commit. Rules whose whole statement already lives in another module are delegated to rather than
restated.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from nativespeaker.api.auth.audit import REDACTED, AuthEventResult, redact
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.grant_schema import (
    PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN,
    SUBSCRIPTION_OWNER_FK,
    ForeignKeyFact,
    UniqueIndexFact,
    assert_active_subscription_entitled,
    assert_lifecycle_updates_share_transaction,
)
from nativespeaker.api.auth.invariants import (
    AttributionTokens,
    StoreProvider,
    assert_owner_agreement,
)
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.restore_flow import PurchaseRow, SubscriptionRow, VerifiedTransaction
from nativespeaker.api.auth.restore_phases import LockTier
from nativespeaker.api.auth.restore_proof_policy import BindingOutcome, bind_store_transaction
from nativespeaker.api.auth.schema_invariants import (
    NEVER_WRITTEN_COLUMNS,
    assert_no_client_asserted_attribution,
    assert_no_never_written_column,
    assert_tokens_minted_at_creation,
    assert_tokens_survive_upgrade,
    attribute_purchase,
)
from nativespeaker.api.auth.store_purchases import (
    IN_PLACE_TRANSITIONS,
    TableMutability,
    TableSemantics,
    assert_not_an_ownership_selector,
    build_purchase_row,
    resolve_or_create_purchase_row,
    table_semantics,
    upsert_canonical_subscription,
)
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.grants import (
    PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES,
    assert_billing_separation,
    assert_status_writer_settled_grant,
    is_product_entitled,
    settled_grant_status,
)


class SubscriptionSchemaError(RuntimeError):
    """A proposed row or write plan breaks one of the four tables' contract."""


ACCESS_GRANTS_TABLE: str = "core.access_grants"


# ==============================================================================================
# `core.subscriptions`
# ==============================================================================================

SUBSCRIPTIONS_TABLE: str = "core.subscriptions"

# The columns this table retains but no write path ever names. They are read out of the
# invariant that forbids writing them rather than spelled out again here.
RETAINED_UNWRITTEN_COLUMNS: tuple[str, ...] = tuple(sorted(
    name.rpartition(".")[2] for name in NEVER_WRITTEN_COLUMNS
    if name.startswith("core.subscriptions.")))

# The canonical current state of one provider-scoped paid subscription lifecycle, and nothing
# else: the lifecycle's identity, its current owner, its current tier and status, the two
# restore-related columns, and the generated entitlement key.
# [impl->req~schema-subscriptions-purpose~1]
SUBSCRIPTION_COLUMNS: tuple[str, ...] = (
    "id", "user_id", "provider", "external_id", "tier_id", "status",
    *RETAINED_UNWRITTEN_COLUMNS, "restore_bound_user_id",
    "product_entitled_subscription_id", "created_at", "updated_at",
)

# The lifecycle key: one row per provider-scoped stable paid subscription identity.
LIFECYCLE_KEY: tuple[str, str] = ("provider", "external_id")


def canonical_state(row: SubscriptionRow) -> dict[str, Any]:
    """The canonical current state of one provider-scoped paid subscription lifecycle: its
    current owner, tier and status, read off the one row that holds them."""
    # [impl->req~schema-subscriptions-purpose~1]
    return {"user_id": row.user_id, "tier_id": row.tier_id, "status": row.status}


def assert_one_row_per_lifecycle(rows: Sequence[SubscriptionRow]) -> None:
    """Each row represents exactly one provider-specific stable paid subscription identity: a
    second row for another state of the same lifecycle is not a new subscription."""
    # [impl->req~schema-subscriptions-row-per-lifecycle~1]
    seen: set[tuple[StoreProvider, str]] = set()
    for row in rows:
        if row.key in seen:
            raise SubscriptionSchemaError(
                f"{row.key} is one paid subscription lifecycle, held by exactly one row")
        seen.add(row.key)


# The stable lifecycle identity each store namespace supplies, and the per-term values that are
# not it: a renewal-scoped identifier would split one lifecycle across rows.
# [impl->req~schema-subscriptions-external-id-stable-identity~1]
LIFECYCLE_IDENTITY_FIELD: dict[StoreProvider, str] = {
    StoreProvider.apple: "originalTransactionId",
    StoreProvider.google_play: "purchaseToken",
}
PER_TERM_IDENTIFIERS: frozenset[str] = frozenset({
    "transactionId", "webOrderLineItemId", "orderId", "purchaseTime", "notificationUUID",
    "signedDate",
})


def lifecycle_external_id(provider: StoreProvider,
                          verified_purchase: Mapping[str, Any]) -> str:
    """`external_id` is the stable lifecycle identity within the provider namespace — Apple's
    `originalTransactionId`, Google Play's purchase token — and never a per-term identifier that
    changes with each billing period."""
    # [impl->req~schema-subscriptions-external-id-stable-identity~1]
    name = LIFECYCLE_IDENTITY_FIELD[provider]
    assert_stable_identity_field(name)
    value = verified_purchase.get(name)
    if not value:
        raise SubscriptionSchemaError(
            f"{provider} carries its stable lifecycle identity in {name}")
    return str(value)


def assert_stable_identity_field(name: str) -> None:
    """A per-term store identifier is not a lifecycle identity and never becomes `external_id`."""
    # [impl->req~schema-subscriptions-external-id-stable-identity~1]
    if name in PER_TERM_IDENTIFIERS:
        raise SubscriptionSchemaError(f"{name} changes per term; it is no stable lifecycle identity")
    if name not in set(LIFECYCLE_IDENTITY_FIELD.values()):
        raise SubscriptionSchemaError(f"{name} is no store's stable lifecycle identity")


# The lifecycle transitions that update the same canonical row in place.
# [impl->req~schema-subscriptions-transitions-update-in-place~1]
LIFECYCLE_TRANSITIONS: frozenset[str] = frozenset({
    "renewal", "grace_period", "billing_retry", "expiration", "revocation", "tier_change",
})


def resolve_for_ingestion(rows: Sequence[SubscriptionRow],
                          *,
                          provider: StoreProvider,
                          external_id: str) -> SubscriptionRow | None:
    """Verified subscription ingestion resolves by `(provider, external_id)`. The row it finds is
    the one it updates; finding none is what makes an insert correct."""
    # [impl->req~schema-subscriptions-ingestion-resolve-by-key~1]
    assert_one_row_per_lifecycle(rows)
    matches = [row for row in rows if row.key == (provider, external_id)]
    return matches[0] if matches else None


def apply_lifecycle_transition(rows: Sequence[SubscriptionRow],
                               *,
                               provider: StoreProvider,
                               external_id: str,
                               transition: str,
                               status: SubscriptionStatus,
                               tier_id: str,
                               user_id: UUID | None = None) -> SubscriptionRow:
    """Ordinary renewal, grace-period, billing-retry, expiration, revocation and tier-change
    transitions for the same store subscription update the same row in place: the resolved row
    keeps its `id`, and no second row is inserted for another state of one lifecycle."""
    # [impl->req~schema-subscriptions-transitions-update-in-place~1]
    # [impl->req~schema-subscriptions-ingestion-resolve-by-key~1]
    if transition not in LIFECYCLE_TRANSITIONS or transition not in IN_PLACE_TRANSITIONS:
        raise SubscriptionSchemaError(f"{transition} is no in-place lifecycle transition")
    existing = resolve_for_ingestion(rows, provider=provider, external_id=external_id)
    owner = existing.user_id if existing is not None else user_id
    updated = upsert_canonical_subscription(rows, provider=provider, external_id=external_id,
                                            status=status, tier_id=tier_id, user_id=owner,
                                            transition=transition)
    if existing is not None and updated.subscription_id != existing.subscription_id:
        raise SubscriptionSchemaError("a lifecycle transition updates the resolved row in place")
    return updated


# `(provider, external_id)` is globally unique: one canonical row per store subscription across
# the whole table, with no partial predicate narrowing it to a user or to live rows.
# [impl->req~schema-subscriptions-provider-external-id-unique~1]
PROVIDER_EXTERNAL_ID_INDEX = UniqueIndexFact(
    name="ix_subscriptions_provider_external_id",
    table=SUBSCRIPTIONS_TABLE,
    columns=LIFECYCLE_KEY)


def assert_lifecycle_globally_unique(rows: Sequence[SubscriptionRow],
                                     *,
                                     provider: StoreProvider,
                                     external_id: str) -> None:
    """An insert for a `(provider, external_id)` that already has a row is refused however the
    two rows would differ — a different owner does not buy a second canonical row."""
    # [impl->req~schema-subscriptions-provider-external-id-unique~1]
    if PROVIDER_EXTERNAL_ID_INDEX.predicate is not None:
        raise SubscriptionSchemaError("the lifecycle key is globally unique, not partially unique")
    if any(row.key == (provider, external_id) for row in rows):
        raise SubscriptionSchemaError(f"{(provider, external_id)} already has its canonical row")


def assert_rows_per_user_provider(rows: Sequence[SubscriptionRow]) -> None:
    """Multiple rows for the same `(user_id, provider)` are allowed only when they represent
    different `external_id` values for different subscription lifecycles — never two rows for one
    lifecycle."""
    # [impl->req~schema-subscriptions-multiple-rows-per-user-provider~1]
    seen: set[tuple[UUID | None, StoreProvider, str]] = set()
    for row in rows:
        key = (row.user_id, row.provider, row.external_id)
        if key in seen:
            raise SubscriptionSchemaError(
                "rows sharing (user_id, provider) carry different external_id values")
        seen.add(key)
    assert_one_row_per_lifecycle(rows)


def unclaimed_subscription(*,
                           provider: StoreProvider,
                           external_id: str,
                           status: SubscriptionStatus,
                           tier_id: str) -> SubscriptionRow:
    """Verified ingestion whose echoed token resolves to no binding creates the canonical row
    unowned: `user_id` is NULL, and no subscription-backed grant comes with it."""
    # [impl->req~schema-subscriptions-user-id-null-unclaimed~1]
    return SubscriptionRow(subscription_id=uuid4(), provider=provider, external_id=external_id,
                           status=status, tier_id=tier_id, user_id=None)


def assert_no_grant_while_unclaimed(*,
                                    subscription_user_id: UUID | None,
                                    grant_user_id: UUID | None) -> None:
    """The composite foreign key makes a subscription-backed grant impossible while the canonical
    row's `user_id` is NULL: a grant's `user_id` is NOT NULL, so it can match no `(id, NULL)`
    target. Restore's adoption is what first links the row and creates its grant and usage row."""
    # [impl->req~schema-subscriptions-user-id-null-unclaimed~1]
    if subscription_user_id is None and grant_user_id is not None:
        raise SubscriptionSchemaError(
            "an unclaimed subscription backs no grant; restore's adoption links it first")
    if subscription_user_id is not None and grant_user_id is not None:
        assert_owner_agreement(grant_user_id=grant_user_id,
                               subscription_user_id=subscription_user_id)


def adopt_unclaimed(row: SubscriptionRow, *, destination_user_id: UUID) -> SubscriptionRow:
    """Restore's adoption links the unclaimed canonical row to the destination user; only then
    can the grant and usage row exist."""
    # [impl->req~schema-subscriptions-user-id-null-unclaimed~1]
    if row.user_id is not None:
        raise SubscriptionSchemaError("adoption links an unclaimed subscription only")
    return SubscriptionRow(subscription_id=row.subscription_id, provider=row.provider,
                           external_id=row.external_id, status=row.status, tier_id=row.tier_id,
                           user_id=destination_user_id,
                           restore_bound_user_id=row.restore_bound_user_id)


def current_tier(row: SubscriptionRow) -> str:
    """`tier_id` records the access tier currently associated with this paid subscription
    lifecycle — the tier now, not the tier at purchase and not a history of tiers."""
    # [impl->req~schema-subscriptions-tier-id-current-tier~1]
    return row.tier_id


def assert_tier_is_current(row: SubscriptionRow, *, tier_id: str) -> None:
    """After a tier change the canonical row carries the new tier: the column is current state,
    so a stale value is a broken row rather than history."""
    # [impl->req~schema-subscriptions-tier-id-current-tier~1]
    if current_tier(row) != tier_id:
        raise SubscriptionSchemaError(
            f"{SUBSCRIPTIONS_TABLE}.tier_id records the current tier, not {current_tier(row)}")


# ---- the append-only event history beside the canonical row ----------------------------------

SUBSCRIPTION_EVENTS_TABLE: str = "audit.subscription_events"

# The event history is append-only: no update path and no delete path exists over it.
# [impl->req~schema-subscriptions-events-append-only-history~1]
EVENT_HISTORY_MUTATIONS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class SubscriptionEventRow:
    """One accepted observation of a provider notification, referencing the canonical row."""
    event_id: UUID
    subscription_id: UUID
    event_type: str
    notification_uuid: str
    old_tier_id: str | None = None
    new_tier_id: str | None = None


def append_subscription_event(events: Sequence[SubscriptionEventRow],
                              row: SubscriptionEventRow) -> tuple[SubscriptionEventRow, ...]:
    """`audit.subscription_events` is the append-only event history for the canonical
    `core.subscriptions` row it references: one row per accepted observation, appended beside the
    rows already there, never replacing one of them."""
    # [impl->req~schema-subscriptions-events-append-only-history~1]
    # [impl->req~schema-subscription-events-purpose~1]
    if EVENT_HISTORY_MUTATIONS:
        raise SubscriptionSchemaError(f"{SUBSCRIPTION_EVENTS_TABLE} has no update or delete path")
    if any(stored.event_id == row.event_id for stored in events):
        raise SubscriptionSchemaError("an appended observation is never rewritten")
    return (*events, row)


def assert_event_not_rewritten(stored: SubscriptionEventRow,
                               incoming: SubscriptionEventRow) -> None:
    """A recorded observation is immutable: correcting one means appending another."""
    # [impl->req~schema-subscriptions-events-append-only-history~1]
    if stored != incoming:
        raise SubscriptionSchemaError("a recorded observation is never updated or deleted")


# Internal enum values `event_type` would be normalized into. There are none: the column records
# what the provider sent.
# [impl->req~schema-subscription-events-event-type~1]
INTERNAL_EVENT_TYPES: Mapping[str, str] = {}


def record_event_type(notification_type: str) -> str:
    """`event_type` records the provider's notification type as received — an Apple App Store
    Server Notification type or a Google Play Real-time Developer Notification type — as an
    observation, not an internal enum."""
    # [impl->req~schema-subscription-events-event-type~1]
    if INTERNAL_EVENT_TYPES:
        raise SubscriptionSchemaError("event_type is an observation, not an internal enum")
    if not notification_type:
        raise SubscriptionSchemaError("an observation records the notification type it saw")
    return notification_type


def event_tier_transition(*,
                          old_tier_id: str | None,
                          new_tier_id: str | None) -> tuple[str | None, str | None]:
    """`old_tier_id` and `new_tier_id` record the tier transition the observation recorded, both
    referencing `core.access_tiers`, and are NULL when the notification implies no tier
    transition."""
    # [impl->req~schema-subscription-events-tier-transition~1]
    if old_tier_id == new_tier_id:
        return None, None
    if old_tier_id is None or new_tier_id is None:
        raise SubscriptionSchemaError(
            "a recorded tier transition names the tier it moved from and the tier it moved to")
    return old_tier_id, new_tier_id


# ---- billing facts, not access ---------------------------------------------------------------


def assert_billing_fact_not_access(*,
                                   source: AccessGrantSource,
                                   subscription_id: UUID | None) -> None:
    """Subscription rows are billing facts; product access is granted by the corresponding
    `core.access_grants` row, which names the billing row it is backed by."""
    # [impl->req~schema-subscriptions-billing-facts-not-access~1]
    assert_billing_separation(source, subscription_id)


def entitlement_input(table: str) -> str:
    """Entitlement and quota logic derive access from `core.access_grants`. A canonical
    subscription row — including a duplicate same-lifecycle row webhook ordering may have created
    — is a billing fact and never an entitlement input."""
    # [impl->req~schema-subscriptions-entitlement-from-grants~1]
    if table != ACCESS_GRANTS_TABLE:
        raise SubscriptionSchemaError(
            f"entitlement is derived from {ACCESS_GRANTS_TABLE}, never from {table}")
    return table


def assert_billing_fact_grants_nothing(*, subscription_rows: int, active_grants: int) -> None:
    """However many subscription rows a store's ordering produced, access is what the grant rows
    say: rows on the billing table confer none by themselves."""
    # [impl->req~schema-subscriptions-entitlement-from-grants~1]
    del subscription_rows
    if active_grants > 1:
        raise SubscriptionSchemaError("access follows the single active grant, not billing rows")


# ---- the fixed product-entitled status set ---------------------------------------------------

# The product-entitled subscription statuses, fixed by the generated-column expression on this
# table. `billing_retry`, `expired` and `revoked` are not product-entitled.
# [impl->req~schema-subscriptions-product-entitled-status-set~1]
PRODUCT_ENTITLED_STATUSES: frozenset[SubscriptionStatus] = PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES
PRODUCT_ENTITLED_EXPRESSION: str = PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN.expression
TERMINAL_STATUSES: frozenset[SubscriptionStatus] = frozenset({
    SubscriptionStatus.expired, SubscriptionStatus.revoked,
})


def is_entitled(status: SubscriptionStatus) -> bool:
    """The product-entitled subscription statuses are exactly `active` and `grace_period`, fixed
    by the `product_entitled_subscription_id` generated-column expression."""
    # [impl->req~schema-subscriptions-product-entitled-status-set~1]
    if PRODUCT_ENTITLED_STATUSES != frozenset({SubscriptionStatus.active,
                                               SubscriptionStatus.grace_period}):
        raise SubscriptionSchemaError("the product-entitled set is fixed at (active, grace_period)")
    return is_product_entitled(status)


def product_entitled_subscription_id(row: SubscriptionRow) -> UUID | None:
    """What Postgres stores in the generated column: the row's `id` when `status` is in the fixed
    product-entitled set, and NULL otherwise. This expression is the single authoritative source
    of truth for product entitlement — every other statement of the set cites it."""
    # [impl->req~schema-subscriptions-product-entitled-status-set~1]
    # [impl->req~schema-subscriptions-product-entitled-generated-column-authority~1]
    return row.subscription_id if is_entitled(row.status) else None


def assert_no_active_grant_for_terminal(*,
                                        status: SubscriptionStatus,
                                        active_grant_id: UUID | None) -> None:
    """`expired` and `revoked` subscription rows must not back an active subscription grant: the
    generated column is NULL for them, so the deferrable foreign key finds no target at commit."""
    # [impl->req~schema-subscriptions-expired-revoked-no-active-grant~1]
    if status in TERMINAL_STATUSES and active_grant_id is not None:
        raise SubscriptionSchemaError(
            f"a {status} subscription backs no active grant; grant {active_grant_id} must settle")
    if active_grant_id is not None:
        assert_active_subscription_entitled(status=AccessGrantStatus.active,
                                            subscription_status=status)


def assert_ingestion_settles_grant(*,
                                   old_status: SubscriptionStatus,
                                   new_status: SubscriptionStatus,
                                   old_tier_id: str,
                                   new_tier_id: str,
                                   active_grant_id: UUID | None,
                                   grant_tier_id: str | None = None,
                                   grant_deactivated: bool = False,
                                   grant_replaced: bool = False,
                                   subscription_transaction: object = None,
                                   grant_transaction: object = None) -> None:
    """When verified subscription ingestion changes `status` or `tier_id`, it updates the
    corresponding subscription-backed `core.access_grants` row in the same transaction — the
    status settlement and the tier move alike."""
    # [impl->req~schema-subscriptions-ingestion-updates-grant-same-transaction~1]
    if old_status is new_status and old_tier_id == new_tier_id:
        return
    assert_lifecycle_updates_share_transaction(subscription_transaction=subscription_transaction,
                                               grant_transaction=grant_transaction)
    if (old_tier_id != new_tier_id and active_grant_id is not None
            and not (grant_deactivated or grant_replaced) and grant_tier_id != new_tier_id):
        raise SubscriptionSchemaError(
            f"a tier change to {new_tier_id} moves grant {active_grant_id} in the same transaction")
    assert_status_writer_settled_grant(old_status=old_status, new_status=new_status,
                                       active_grant_id=active_grant_id,
                                       grant_deactivated=grant_deactivated,
                                       grant_replaced=grant_replaced,
                                       subscription_transaction=subscription_transaction,
                                       grant_transaction=grant_transaction)


def settle_grant_for_non_entitled(new_status: SubscriptionStatus,
                                  *,
                                  now: datetime) -> tuple[AccessGrantStatus, datetime]:
    """When a subscription changes to a non-entitled status the corresponding grant is marked
    `expired` or `revoked` and its `ends_at` is set, in that same transaction."""
    # [impl->req~schema-subscriptions-non-entitled-marks-grant-ended~1]
    status = settled_grant_status(new_status)
    return status, now


def assert_grant_ended(*,
                       grant_status: AccessGrantStatus,
                       ends_at: datetime | None) -> None:
    """The settled grant is terminal and carries the moment it ended; an `active` row or a NULL
    `ends_at` is not a settlement."""
    # [impl->req~schema-subscriptions-non-entitled-marks-grant-ended~1]
    if grant_status is AccessGrantStatus.active:
        raise SubscriptionSchemaError("a non-entitled subscription's grant is expired or revoked")
    if ends_at is None:
        raise SubscriptionSchemaError("the settled grant records its ends_at")


# Reactivation belongs to user-invoked restore alone: ingestion has no path to it.
# [impl->req~schema-subscriptions-reentitlement-no-auto-reactivate~1]
INGESTION_REACTIVATION_PATHS: frozenset[str] = frozenset()
REACTIVATION_OWNER: str = "restore_subscription"


def assert_no_ingestion_reactivation(*,
                                     new_status: SubscriptionStatus,
                                     grant_status: AccessGrantStatus,
                                     reactivated: bool = False) -> None:
    """When a subscription changes to an entitled status again, the ingestion path never
    reactivates the corresponding grant. The entitled-subscription/expired-grant state persists
    until the user invokes restore."""
    # [impl->req~schema-subscriptions-reentitlement-no-auto-reactivate~1]
    if INGESTION_REACTIVATION_PATHS:
        raise SubscriptionSchemaError(f"reactivation belongs to {REACTIVATION_OWNER} alone")
    if reactivated:
        raise SubscriptionSchemaError(
            f"ingestion never reactivates a grant; {REACTIVATION_OWNER} does")
    if is_entitled(new_status) and grant_status is not AccessGrantStatus.active:
        return  # the entitled-subscription/expired-grant state is allowed to stand


# ---- `UNIQUE (id, user_id)`, and the ownership agreement it backs -----------------------------

# `UNIQUE (id, user_id)` exists so the subscription-backed grant can bind to the canonical row
# through a composite foreign key without trigger logic. `id` is already the primary key, so the
# constraint adds no uniqueness of its own.
# [impl->req~schema-subscriptions-unique-id-user-id-fk-target~1]
ID_USER_ID_FK_TARGET: tuple[str, str] = ("id", "user_id")
SUBSCRIPTION_PRIMARY_KEY: tuple[str, ...] = ("id",)
OWNER_AGREEMENT_TRIGGERS: frozenset[str] = frozenset()


def assert_id_user_id_is_fk_target_only(*, additional_uniqueness_claimed: bool = False) -> None:
    """The constraint is a foreign-key target, not an additional uniqueness rule over what the
    primary key already provides, and it replaces trigger logic rather than adding it."""
    # [impl->req~schema-subscriptions-unique-id-user-id-fk-target~1]
    if SUBSCRIPTION_PRIMARY_KEY[0] not in ID_USER_ID_FK_TARGET:
        raise SubscriptionSchemaError("the composite target starts at the primary key")
    if tuple(SUBSCRIPTION_OWNER_FK.target_columns) != ID_USER_ID_FK_TARGET:
        raise SubscriptionSchemaError(
            f"{ID_USER_ID_FK_TARGET} is the target of the grant table's composite foreign key")
    if OWNER_AGREEMENT_TRIGGERS:
        raise SubscriptionSchemaError("the binding needs no trigger logic")
    if additional_uniqueness_claimed:
        raise SubscriptionSchemaError(
            "UNIQUE (id, user_id) adds no uniqueness beyond the primary key")


def assert_owner_agreement_at_commit(*,
                                     grant_user_id: UUID | None,
                                     subscription_user_id: UUID | None,
                                     subscription_transaction: object = None,
                                     grant_transaction: object = None,
                                     grant_user_id_rewritten: bool = False) -> None:
    """Ownership drift between the canonical row and the active subscription-backed grant is
    prevented declaratively by the deferrable composite foreign key on `core.access_grants`: both
    rows are written in one transaction, in either order, and the database checks that the two
    `user_id` values agree at commit. Neither ingestion nor `restore_subscription` reaches that
    agreement by rewriting a grant's `user_id`."""
    # [impl->req~schema-subscriptions-owner-drift-prevented-by-fk~1]
    if not SUBSCRIPTION_OWNER_FK.deferrable:
        raise SubscriptionSchemaError("the owner agreement is checked at commit, deferrably")
    if grant_user_id_rewritten:
        raise SubscriptionSchemaError("no path rewrites a grant's user_id to reach agreement")
    assert_lifecycle_updates_share_transaction(subscription_transaction=subscription_transaction,
                                               grant_transaction=grant_transaction)
    assert_owner_agreement(grant_user_id=grant_user_id,
                           subscription_user_id=subscription_user_id)


# ---- the generated column is the authority ----------------------------------------------------

# The one way the entitled status set may ever change, and the mechanisms that may not do it.
# [impl->req~schema-subscriptions-product-entitled-generated-column-authority~1]
ENTITLED_STATUS_CHANGE_MECHANISM: str = "schema_migration"
ENTITLED_STATUS_RUNTIME_MECHANISMS: frozenset[str] = frozenset({
    "runtime_configuration", "environment_variable", "feature_toggle",
    "independently_deployable_toggle",
})
LOCKSTEP_CHANGES: tuple[str, ...] = ("application_logic", "prose", "tests")


def assert_generated_column_is_the_authority(*, competing_sources: Iterable[str] = ()) -> None:
    """The generated-column expression is the single, authoritative source of truth for product
    entitlement — prose elsewhere is descriptive and cites it."""
    # [impl->req~schema-subscriptions-product-entitled-generated-column-authority~1]
    if PRODUCT_ENTITLED_EXPRESSION != (
            "CASE WHEN status IN ('active', 'grace_period') THEN id END"):
        raise SubscriptionSchemaError("the generated-column expression is the entitlement set")
    competing = sorted(set(competing_sources))
    if competing:
        raise SubscriptionSchemaError(
            f"{competing} may hold no second opinion about product entitlement")


def assert_entitled_status_set_change(mechanism: str,
                                      *,
                                      expression_altered: bool = False,
                                      lockstep: Iterable[str] = (),
                                      grants_adjusted_in_migration: bool = False) -> None:
    """Any future addition or removal of an entitled status is a deliberate schema migration that
    alters this expression — never a runtime configuration, environment variable, or
    independently deployable toggle — with application logic, prose and tests changed in lockstep
    and affected grants preserved or adjusted transactionally in the same migration."""
    # [impl->req~schema-subscriptions-product-entitled-generated-column-authority~1]
    if mechanism in ENTITLED_STATUS_RUNTIME_MECHANISMS:
        raise SubscriptionSchemaError(f"{mechanism} may not change the entitled status set")
    if mechanism != ENTITLED_STATUS_CHANGE_MECHANISM:
        raise SubscriptionSchemaError(
            f"the entitled status set changes by {ENTITLED_STATUS_CHANGE_MECHANISM} alone")
    if not expression_altered:
        raise SubscriptionSchemaError("such a migration alters the generated-column expression")
    missing = tuple(name for name in LOCKSTEP_CHANGES if name not in set(lockstep))
    if missing:
        raise SubscriptionSchemaError(f"{list(missing)} change in lockstep with the expression")
    if not grants_adjusted_in_migration:
        raise SubscriptionSchemaError(
            "affected grants are preserved or adjusted transactionally in the same migration")


def assert_entitlement_holds_at_commit(*,
                                       subscription_status: SubscriptionStatus,
                                       grant_status: AccessGrantStatus,
                                       subscription_transaction: object = None,
                                       grant_transaction: object = None,
                                       intermediate_states: Sequence[Any] = ()) -> None:
    """Subscription lifecycle ingestion and `restore_subscription` update the canonical row and
    the corresponding subscription-backed grant within one transaction, so the deferred foreign
    key holds at commit. Intermediate states inside the transaction are allowed; the final
    committed state is what is checked declaratively. Runtime checks rely on that FK-backed
    active grant as an equivalent predicate that cannot drift from the expression."""
    # [impl->req~schema-subscriptions-product-entitled-generated-column-authority~1]
    assert_lifecycle_updates_share_transaction(subscription_transaction=subscription_transaction,
                                               grant_transaction=grant_transaction)
    del intermediate_states  # allowed inside the transaction; only the commit is checked
    assert_active_subscription_entitled(status=grant_status,
                                        subscription_status=subscription_status)


def assert_transfer_month_untouched(columns: Iterable[str]) -> None:
    """The retained cross-account transfer month column stays NULL: cross-account restore
    transfer is never performed, so no restore outcome updates it. Its name is read from the
    invariant that forbids writing it — this module never spells out a column it may not write."""
    # [impl->req~schema-subscriptions-last-cross-account-transfer-month-null~1]
    assert_no_never_written_column(SUBSCRIPTIONS_TABLE, columns)


def bind_restore_destination(*,
                             restore_bound_user_id: UUID | None,
                             destination_user_id: UUID,
                             relink: bool = False) -> BindingOutcome:
    """`restore_bound_user_id` is the lifetime store-transaction-to-account restore binding: NULL
    until the store transaction's first successful restore, set to that restore's destination user
    in the same transaction, and never changed by any later restore. A restore whose destination
    differs from a non-NULL binding rejects with `store_transaction_already_linked`; re-restoring
    into the bound account is idempotent success; moving the binding is a manual operator repair
    only."""
    # [impl->req~schema-subscriptions-restore-bound-user-id~1]
    return bind_store_transaction(restore_bound_user_id=restore_bound_user_id,
                                  destination_user_id=destination_user_id,
                                  relink=relink)


def bound_after_restore(row: SubscriptionRow, *, destination_user_id: UUID) -> UUID:
    """The binding the canonical row carries once the restore commits: the first destination, and
    that one thereafter."""
    # [impl->req~schema-subscriptions-restore-bound-user-id~1]
    bind_restore_destination(restore_bound_user_id=row.restore_bound_user_id,
                             destination_user_id=destination_user_id)
    return row.restore_bound_user_id or destination_user_id


# The two lock tiers whose combination serializes restore per store subscription.
# [impl->req~schema-subscriptions-restore-serialization~1]
RESTORE_SERIALIZATION_TIERS: tuple[LockTier, LockTier] = (
    LockTier.store_subscription_serialization,
    LockTier.canonical_subscription_row,
)


def assert_restore_serialized(tiers: Sequence[LockTier]) -> None:
    """The restore locked phase's per-subscription serialization — the canonical
    `core.subscriptions` row lock plus store-subscription serialization for
    `(provider, external_id)` — prevents concurrent restore attempts for the same store
    subscription. Both are taken, in the locked phase's fixed order."""
    # [impl->req~schema-subscriptions-restore-serialization~1]
    taken = tuple(tier for tier in tiers if tier in set(RESTORE_SERIALIZATION_TIERS))
    if taken != RESTORE_SERIALIZATION_TIERS:
        raise SubscriptionSchemaError(
            f"concurrent restores are serialized by {list(RESTORE_SERIALIZATION_TIERS)}")


# ==============================================================================================
# `core.store_purchase_tokens`
# ==============================================================================================

STORE_PURCHASE_TOKENS_TABLE: str = "core.store_purchase_tokens"

# The row: the owning user, the store provider, and the token value. Nothing else, and no
# identity-kind dimension anywhere in it.
# [impl->req~schema-store-purchase-tokens-row-columns~1]
TOKEN_COLUMNS: tuple[str, ...] = ("user_id", "provider", "identity_value", "created_at")
TOKEN_REQUIRED_COLUMNS: tuple[str, ...] = ("user_id", "provider", "identity_value")
IDENTITY_KIND_COLUMNS: frozenset[str] = frozenset()

# At most one purchase-attribution token per user per store for the life of the account, and one
# owner per token within a store.
# [impl->req~schema-store-purchase-tokens-one-per-user-per-provider~1]
TOKEN_BINDING_KEY: tuple[str, str] = ("user_id", "provider")
TOKEN_RESOLUTION_KEY: tuple[str, str] = ("provider", "identity_value")
TOKEN_UNIQUE_KEYS: tuple[tuple[str, str], ...] = (TOKEN_BINDING_KEY, TOKEN_RESOLUTION_KEY)

# Store provider implies the token's store-specific use.
# [impl->req~schema-store-purchase-tokens-provider-token-kinds~1]
STORE_TOKEN_KIND: dict[StoreProvider, str] = {
    StoreProvider.apple: "app_account_token",
    StoreProvider.google_play: "obfuscated_external_account_id",
}

# The material a token is never derived from or guessable from.
# [impl->req~schema-store-purchase-tokens-random-opaque-uuid~1]
TOKEN_DERIVATION_INPUTS: frozenset[str] = frozenset({
    "issuer", "subject", "iss_sub", "user_id", "email", "provider_uid", "display_name",
})

# The token is non-secret: it is never rotated or replaced, has no administrative replacement
# path, and uses no secret-store machinery.
# [impl->req~schema-store-purchase-tokens-non-secret-never-rotated~1]
# [impl->req~schema-store-purchase-tokens-redacted-from-logs~1]
TOKEN_ROTATION_PATHS: frozenset[str] = frozenset()
TOKEN_SECRET_STORE_MACHINERY: frozenset[str] = frozenset()

# Knowledge of or equality with a token proves nothing at all.
# [impl->req~schema-store-purchase-tokens-knowledge-not-proof~1]
TOKEN_PROVES: frozenset[str] = frozenset()

# Where a token value can appear in a routine log, analytics event or error report.
TOKEN_LOG_FIELDS: tuple[str, ...] = (
    "app_account_token", "obfuscated_external_account_id", "identity_value",
    "resolved_token_value",
)


@dataclass(frozen=True, slots=True)
class StorePurchaseTokenRow:
    """One `core.store_purchase_tokens` row: one token value bound to one owning user, scoped
    only by store provider."""
    user_id: UUID
    provider: StoreProvider
    identity_value: str


def token_kind(provider: StoreProvider) -> str:
    """The two providers' tokens for a user are an Apple `app_account_token` and a Google
    `obfuscated_external_account_id`, each a randomly generated UUID."""
    # [impl->req~schema-store-purchase-tokens-provider-token-kinds~1]
    if set(STORE_TOKEN_KIND) != set(StoreProvider):
        raise SubscriptionSchemaError("every store provider has its own token kind")
    return STORE_TOKEN_KIND[provider]


def assert_random_opaque_uuid(value: str, *, derived_from: Iterable[str] = ()) -> UUID:
    """Each token is a random, opaque, server-generated UUID containing no PII, never derived
    from or guessable from `(issuer, subject)`, user ID, or email."""
    # [impl->req~schema-store-purchase-tokens-random-opaque-uuid~1]
    derived = sorted(set(derived_from) & TOKEN_DERIVATION_INPUTS)
    if derived:
        raise SubscriptionSchemaError(f"a token derived from {derived} is neither random nor opaque")
    try:
        parsed = UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise SubscriptionSchemaError(f"{value!r} is no UUID") from None
    if parsed.version != 4:
        raise SubscriptionSchemaError(
            "a purchase-attribution token is a random UUID, not a derived or time-ordered one")
    return parsed


def token_binding(row: StorePurchaseTokenRow) -> tuple[UUID, StoreProvider, str]:
    """The binding one row records: one token value, one owning `core.users.id`, scoped only by
    store provider, with the value stored as the randomly generated UUID the client passes into
    that store's SDK. There is no separate identity-kind dimension."""
    # [impl->req~schema-store-purchase-tokens-binding-definition~1]
    if IDENTITY_KIND_COLUMNS:
        raise SubscriptionSchemaError("the binding carries no identity-kind dimension")
    token_kind(row.provider)
    assert_random_opaque_uuid(row.identity_value)
    return row.user_id, row.provider, row.identity_value


def assert_token_row_columns(columns: Iterable[str]) -> None:
    """The row carries the owning user, the store provider and the token value — and nothing that
    would make the binding mean more than that."""
    # [impl->req~schema-store-purchase-tokens-row-columns~1]
    names = [str(column) for column in columns]
    unknown = sorted(set(names) - set(TOKEN_COLUMNS))
    if unknown:
        raise SubscriptionSchemaError(f"{unknown} are not {STORE_PURCHASE_TOKENS_TABLE} columns")
    missing = [name for name in TOKEN_REQUIRED_COLUMNS if name not in names]
    if missing:
        raise SubscriptionSchemaError(f"the binding row carries {missing}")


def mint_token_row(*,
                   user_id: UUID,
                   provider: StoreProvider,
                   operation: AuthOperation,
                   identity_value: str | None = None) -> StorePurchaseTokenRow:
    """The row is created once at user creation, with a freshly generated random UUID."""
    # [impl->req~schema-store-purchase-tokens-created-at-user-creation~1]
    # [impl->req~schema-store-purchase-tokens-random-opaque-uuid~1]
    assert_tokens_minted_at_creation(operation)
    value = identity_value or str(uuid4())
    assert_random_opaque_uuid(value)
    return StorePurchaseTokenRow(user_id=user_id, provider=provider, identity_value=value)


def mint_into(tokens: AttributionTokens, row: StorePurchaseTokenRow) -> None:
    """There is at most one purchase-attribution token per user per store for the life of the
    account, enforced by `UNIQUE (user_id, provider)`."""
    # [impl->req~schema-store-purchase-tokens-one-per-user-per-provider~1]
    if TOKEN_BINDING_KEY not in TOKEN_UNIQUE_KEYS:
        raise SubscriptionSchemaError("the per-user-per-store bound is a uniqueness constraint")
    token_binding(row)
    tokens.mint(row.user_id, row.provider, row.identity_value)


def assert_never_rotated(*, stored: str, incoming: str) -> str:
    """The token is non-secret, is never rotated or replaced, and has no administrative
    replacement path."""
    # [impl->req~schema-store-purchase-tokens-non-secret-never-rotated~1]
    if TOKEN_ROTATION_PATHS:
        raise SubscriptionSchemaError("no rotation or administrative replacement path exists")
    if stored != incoming:
        raise SubscriptionSchemaError("a purchase-attribution token is never rotated or replaced")
    return stored


def assert_token_proves_nothing(claims: Iterable[str]) -> None:
    """Knowledge of or equality with a token is never proof of purchase, identity ownership,
    restore authority, or entitlement."""
    # [impl->req~schema-store-purchase-tokens-knowledge-not-proof~1]
    overclaimed = sorted(set(claims) - TOKEN_PROVES)
    if overclaimed:
        raise SubscriptionSchemaError(f"knowing a token is no proof of {overclaimed}")


def redacted_token_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Token values are redacted from routine logs, analytics and error reporting; they do not
    use secret-store machinery."""
    # [impl->req~schema-store-purchase-tokens-redacted-from-logs~1]
    if TOKEN_SECRET_STORE_MACHINERY:
        raise SubscriptionSchemaError("a non-secret token uses no secret-store machinery")
    redacted = dict(redact(dict(payload)))
    for name in TOKEN_LOG_FIELDS:
        if name in redacted:
            redacted[name] = REDACTED
    return redacted


def resolve_owning_user(tokens: AttributionTokens,
                        *,
                        provider: StoreProvider,
                        identity_value: str) -> UUID | None:
    """Its `(provider, identity_value)` key is the key purchase ingestion uses to resolve the
    owning user. A value that matches no binding — or matches one in another store — resolves to
    nobody."""
    # [impl->req~schema-store-purchase-tokens-resolution-key~1]
    if TOKEN_RESOLUTION_KEY != ("provider", "identity_value"):
        raise SubscriptionSchemaError("ingestion resolves by the store and the token value")
    return tokens.owner_of(provider, identity_value)


def assert_binding_survives_upgrade(before: Mapping[str, str], after: Mapping[str, str]) -> None:
    """The binding persists across the in-place anonymous-to-registered upgrade without being
    regenerated, moved, or retired."""
    # [impl->req~schema-store-purchase-tokens-survives-upgrade~1]
    assert_tokens_survive_upgrade(before, after)


# ==============================================================================================
# `core.store_purchases`
# ==============================================================================================

STORE_PURCHASES_TABLE: str = "core.store_purchases"

PURCHASE_COLUMNS: tuple[str, ...] = (
    "id", "provider", "identity_value", "external_id", "store_transaction_id",
    "store_original_transaction_id", "purchase_user_id", "resolved_token_value", "created_at",
)
PURCHASE_KEY: tuple[str, str] = ("provider", "external_id")

# The purchase row names its canonical subscription, and — where ingestion resolved one — the
# token binding it resolved through. Neither foreign key cascades: an attribution record can
# never detach from its historical subscription, and a token binding can never be deleted out
# from under one.
# [impl->req~schema-store-purchases-subscription-fk~1]
# [impl->req~schema-store-purchases-resolved-token-value-fk~1]
PURCHASE_SUBSCRIPTION_FK = ForeignKeyFact(
    PURCHASE_KEY, SUBSCRIPTIONS_TABLE, LIFECYCLE_KEY)
PURCHASE_TOKEN_FK = ForeignKeyFact(
    ("provider", "resolved_token_value"), STORE_PURCHASE_TOKENS_TABLE,
    ("provider", "identity_value"), match="SIMPLE")
RESOLVED_TOKEN_CHECK: str = "resolved_token_value IS NULL OR resolved_token_value = identity_value"

# One row per accepted store subscription; `identity_value` is a plain, non-unique, indexed
# column, since one token spans an account's entire purchase history.
# [impl->req~schema-store-purchases-provider-external-id-unique~1]
PURCHASE_UNIQUE_KEY: tuple[str, str] = PURCHASE_KEY
IDENTITY_VALUE_IS_UNIQUE: bool = False
IDENTITY_VALUE_INDEX: str = "ix_store_purchases_provider_identity_value"

# Written once and never reassigned, rewritten or revoked.
# [impl->req~schema-store-purchases-rows-immutable~1]
IMMUTABLE_PURCHASE_COLUMNS: tuple[str, ...] = (
    "provider", "identity_value", "external_id", "store_transaction_id",
    "store_original_transaction_id", "purchase_user_id",
)
RESTORE_PURCHASE_WRITES: frozenset[str] = frozenset({"insert_once"})

# The authoritative server-side record of which attribution token a verified store subscription
# was purchased under.
# [impl->req~schema-store-purchases-authoritative-attribution-record~1]
ATTRIBUTION_RECORD: str = STORE_PURCHASES_TABLE


def purchase_table_semantics() -> TableSemantics:
    """A purchase-attribution table keyed one row per accepted `(provider, external_id)` store
    subscription — the durable attribution between a verified store subscription and the token it
    was purchased under, not a separate audit row per lifecycle event. Lifecycle history stays
    with the store and the canonical `core.subscriptions` row."""
    # [impl->req~schema-store-purchases-purpose~1]
    semantics = table_semantics(STORE_PURCHASES_TABLE)
    if semantics.keyed_by != PURCHASE_KEY:
        raise SubscriptionSchemaError(f"{STORE_PURCHASES_TABLE} is keyed by {PURCHASE_KEY}")
    if semantics.mutability is not TableMutability.insert_once:
        raise SubscriptionSchemaError("one row per accepted store subscription, written once")
    if semantics.history_in in (SUBSCRIPTION_EVENTS_TABLE, STORE_PURCHASES_TABLE):
        raise SubscriptionSchemaError("lifecycle history stays with the store")
    return semantics


def purchase_store(row: PurchaseRow) -> StoreProvider:
    """`provider` records which store the purchase was made through."""
    # [impl->req~schema-store-purchases-provider-column~1]
    if row.provider not in set(StoreProvider):
        raise SubscriptionSchemaError(f"{row.provider} is no store")
    return row.provider


def purchase_identity_value(echoed_token: str | None) -> str:
    """`identity_value` is the opaque, randomly generated UUID the client passed into the store
    SDK at purchase time — or, where the verified purchase carried no echoed token, the
    server-generated internal purchase UUID recorded in its place. In every case a randomly
    generated UUID."""
    # [impl->req~schema-store-purchases-identity-value-uuid~1]
    value = echoed_token or str(uuid4())
    assert_random_opaque_uuid(value)
    return value


def store_transaction_identifiers(
        verified_purchase: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """The row records the store transaction identifiers when available, and records nothing
    where the store supplied nothing."""
    # [impl->req~schema-store-purchases-store-transaction-ids~1]
    transaction = verified_purchase.get("transactionId")
    original = verified_purchase.get("originalTransactionId")
    return (str(transaction) if transaction else None,
            str(original) if original else None)


def resolved_token_value(*, identity_value: str, token_resolved: bool) -> str | None:
    """`resolved_token_value` is non-NULL exactly where ingestion resolved the echoed token to a
    `core.store_purchase_tokens` row, and NULL in every other case: an echoed token that resolved
    to no binding, a verified purchase carrying no echoed token, and a row `restore_subscription`
    created from store-verified proof. Where it is set it repeats `identity_value`."""
    # [impl->req~schema-store-purchases-resolved-token-value-fk~1]
    return identity_value if token_resolved else None


def assert_resolved_token_value(row: PurchaseRow) -> None:
    """The table CHECK holds the two values together so they can never drift, and the composite
    foreign key uses MATCH SIMPLE, so a NULL `resolved_token_value` skips the check and the three
    unresolved cases are recorded without rejection. Neither foreign key cascades."""
    # [impl->req~schema-store-purchases-resolved-token-value-fk~1]
    if row.resolved_token_value is not None and row.resolved_token_value != row.identity_value:
        raise SubscriptionSchemaError(RESOLVED_TOKEN_CHECK)
    if PURCHASE_TOKEN_FK.match != "SIMPLE" or PURCHASE_TOKEN_FK.on_delete is not None:
        raise SubscriptionSchemaError(
            "the token foreign key is MATCH SIMPLE and cascades no deletion")


def assert_names_canonical_subscription(subscriptions: Sequence[SubscriptionRow],
                                        *,
                                        provider: StoreProvider,
                                        external_id: str,
                                        subscription_written_first: bool = True) -> None:
    """Every purchase row names a real canonical subscription row through the composite foreign
    key to `core.subscriptions (provider, external_id)`; the subscription row is written first in
    the same transaction, and no cascading delete exists — the foreign key restricts deletion and
    key changes, so an attribution record can never detach from its historical subscription."""
    # [impl->req~schema-store-purchases-subscription-fk~1]
    if PURCHASE_SUBSCRIPTION_FK.on_delete is not None:
        raise SubscriptionSchemaError("the subscription foreign key cascades no deletion")
    if not subscription_written_first:
        raise SubscriptionSchemaError("the canonical subscription row is written first")
    if not any(row.key == (provider, external_id) for row in subscriptions):
        raise SubscriptionSchemaError(
            f"{(provider, external_id)} names no canonical {SUBSCRIPTIONS_TABLE} row")


def persistence_failure_result() -> AuthEventResult:
    """A foreign-key or persistence failure is an ingestion or internal-consistency error, never
    `restore_purchase_uuid_mismatch`."""
    # [impl->req~schema-store-purchases-subscription-fk~1]
    result = AuthEventResult.internal_error
    if result is AuthEventResult.restore_purchase_uuid_mismatch:
        raise SubscriptionSchemaError("a persistence failure is not an attribution mismatch")
    return result


def resolve_purchase_user(tokens: AttributionTokens,
                          *,
                          provider: StoreProvider,
                          echoed_token: str | None,
                          restoring_destination_user_id: UUID | None = None,
                          asserted: Mapping[str, Any] | None = None) -> UUID | None:
    """`purchase_user_id` records the user the echoed token was bound to at mint time, resolved
    through `core.store_purchase_tokens` by `(provider, identity_value)`. It is NULL for an
    unattributed purchase — one whose echoed token resolved to no binding, and one the store
    reported carrying no echoed token at all. Request-authenticated and client-asserted
    identities are not attribution sources, with one exception: a row `restore_subscription`
    creates from store-verified proof records the restoring destination user."""
    # [impl->req~schema-store-purchases-purchase-user-id-resolution~1]
    assert_no_client_asserted_attribution(asserted or {})
    owner = (resolve_owning_user(tokens, provider=provider, identity_value=echoed_token)
             if echoed_token else None)
    _, fields = attribute_purchase(token_owner_id=owner,
                                   restoring_destination_user_id=restoring_destination_user_id)
    resolved = fields["purchase_user_id"]
    return resolved if resolved is None else UUID(str(resolved))


def record_purchase(rows: Sequence[PurchaseRow],
                    *,
                    provider: StoreProvider,
                    external_id: str,
                    identity_value: str,
                    purchase_user_id: UUID | None,
                    token_resolved: bool,
                    verified_purchase: Mapping[str, Any] | None = None) -> PurchaseRow:
    """Each row records one accepted store subscription: the store it was made through, the
    attribution token value it was purchased under, the store transaction identifiers where the
    store supplied them, the user the attribution resolved to, and the token binding ingestion
    resolved through where it resolved one."""
    # [impl->req~schema-store-purchases-row-records-attribution~1]
    # [impl->req~schema-store-purchases-provider-external-id-unique~1]
    assert_random_opaque_uuid(identity_value)
    if any(row.key == (provider, external_id) for row in rows):
        raise SubscriptionSchemaError(
            f"{(provider, external_id)} already holds its one purchase-attribution row")
    transaction_id, original_transaction_id = store_transaction_identifiers(verified_purchase or {})
    row = build_purchase_row(provider=provider, external_id=external_id,
                             identity_value=identity_value, purchase_user_id=purchase_user_id,
                             store_transaction_id=transaction_id,
                             store_original_transaction_id=original_transaction_id,
                             token_resolved=token_resolved, existing=rows)
    purchase_store(row)
    assert_resolved_token_value(row)
    return row


def assert_identity_value_not_unique(rows: Sequence[PurchaseRow]) -> None:
    """`identity_value` is a plain, non-unique, indexed column: any number of rows may
    legitimately carry the same token, since one token spans an account's entire purchase
    history. Only `(provider, external_id)` is unique."""
    # [impl->req~schema-store-purchases-provider-external-id-unique~1]
    if IDENTITY_VALUE_IS_UNIQUE:
        raise SubscriptionSchemaError("one token spans an account's whole purchase history")
    keys = [row.key for row in rows]
    if len(set(keys)) != len(keys):
        raise SubscriptionSchemaError("one row per accepted store subscription")


def assert_no_attribution_conflict(existing: PurchaseRow | None, presented: str) -> None:
    """If an existing `(provider, external_id)` row's recorded `identity_value` differs from a
    newly presented token, ingestion refuses as an attribution conflict rather than silently
    reassigning the row: a subscription changing owners is an operator problem."""
    # [impl->req~schema-store-purchases-attribution-conflict-refused~1]
    if existing is None:
        return
    if existing.identity_value != presented:
        raise SubscriptionSchemaError(
            f"{existing.key} is attributed to another token; ingestion reassigns no row")


@dataclass(frozen=True, slots=True)
class IngestedLifecycleEvent:
    """What one verified lifecycle event left behind: the canonical row it updated or created,
    the purchase rows after it, and whether it inserted one."""
    subscription: SubscriptionRow
    purchases: tuple[PurchaseRow, ...]
    purchase_inserted: bool


def ingest_lifecycle_event(subscriptions: Sequence[SubscriptionRow],
                           purchases: Sequence[PurchaseRow],
                           *,
                           provider: StoreProvider,
                           external_id: str,
                           identity_value: str,
                           status: SubscriptionStatus,
                           tier_id: str,
                           user_id: UUID | None = None,
                           token_resolved: bool = True,
                           transition: str = "renewal") -> IngestedLifecycleEvent:
    """A verified event for a new `external_id` inserts a new purchase row under the same token;
    a repeat or lifecycle event for an existing `(provider, external_id)` is idempotent — mutable
    current state is updated in place on the canonical `core.subscriptions` row, and no second
    purchase row is inserted."""
    # [impl->req~schema-store-purchases-idempotent-lifecycle-events~1]
    existing = next((row for row in purchases if row.key == (provider, external_id)), None)
    assert_no_attribution_conflict(existing, identity_value)
    subscription = (apply_lifecycle_transition(subscriptions, provider=provider,
                                               external_id=external_id, transition=transition,
                                               status=status, tier_id=tier_id, user_id=user_id)
                    if any(row.key == (provider, external_id) for row in subscriptions)
                    else upsert_canonical_subscription(subscriptions, provider=provider,
                                                       external_id=external_id, status=status,
                                                       tier_id=tier_id, user_id=user_id))
    if existing is not None:
        return IngestedLifecycleEvent(subscription=subscription,
                                      purchases=tuple(purchases),
                                      purchase_inserted=False)
    row = record_purchase(purchases, provider=provider, external_id=external_id,
                          identity_value=identity_value, purchase_user_id=user_id,
                          token_resolved=token_resolved and user_id is not None)
    return IngestedLifecycleEvent(subscription=subscription,
                                  purchases=(*purchases, row),
                                  purchase_inserted=True)


def assert_history_confers_no_entitlement(purchases: Sequence[PurchaseRow],
                                          *,
                                          active_grant_ids: Sequence[UUID]) -> None:
    """Historical purchase rows never themselves confer entitlement: grants follow the
    single-active-grant invariant and current verified subscription state, enforced at the grant
    layer and fully compatible with a user holding multiple purchase rows."""
    # [impl->req~schema-store-purchases-history-confers-no-entitlement~1]
    entitlement_input(ACCESS_GRANTS_TABLE)
    del purchases  # however many rows there are, none of them is an entitlement
    if len(active_grant_ids) > 1:
        raise SubscriptionSchemaError("entitlement follows the one active grant")


def assert_purchase_row_immutable(stored: PurchaseRow, incoming: PurchaseRow) -> None:
    """Rows are immutable: `provider`, `identity_value`, `external_id`, the recorded store
    transaction identifiers and `purchase_user_id` are written once — at purchase ingestion, or by
    restore's insert-once creation of a missing row from store-verified data — and never
    reassigned, rewritten, or revoked."""
    # [impl->req~schema-store-purchases-rows-immutable~1]
    changed = sorted(name for name in IMMUTABLE_PURCHASE_COLUMNS
                     if getattr(stored, name) != getattr(incoming, name))
    if changed:
        raise SubscriptionSchemaError(f"{changed} are written once and never rewritten")


def assert_restore_purchase_write(action: str) -> None:
    """Beyond the insert-once creation, `restore_subscription` must not insert, update, or revoke
    any `core.store_purchases` row."""
    # [impl->req~schema-store-purchases-rows-immutable~1]
    if action not in RESTORE_PURCHASE_WRITES:
        raise SubscriptionSchemaError(
            f"restore_subscription performs {sorted(RESTORE_PURCHASE_WRITES)} and nothing else")


def attribution_record(table: str) -> str:
    """`core.store_purchases` is the authoritative server-side record of which attribution token a
    verified store subscription was purchased under: the answer is read from that table, not from
    the store, the client, or the canonical subscription row."""
    # [impl->req~schema-store-purchases-authoritative-attribution-record~1]
    if table != ATTRIBUTION_RECORD:
        raise SubscriptionSchemaError(f"{ATTRIBUTION_RECORD} records the attribution, not {table}")
    return table


def restore_purchase_row(rows: Sequence[PurchaseRow],
                         verified: VerifiedTransaction,
                         *,
                         destination_user_id: UUID | None = None) -> PurchaseRow:
    """`restore_subscription` resolves this table's row for the verified store subscription
    directly by `(provider, external_id)` and verifies any purchase UUID carried in the proof
    against that row's recorded `identity_value`. A carried purchase UUID that differs rejects
    restore as `restore_purchase_uuid_mismatch`; a missing row leads to the insert-once creation
    from store-verified data rather than rejection."""
    # [impl->req~schema-store-purchases-restore-uuid-verification~1]
    return resolve_or_create_purchase_row(rows, verified,
                                          destination_user_id=destination_user_id)


def restore_branch_owner(subscription: SubscriptionRow,
                         purchase: PurchaseRow | None = None) -> UUID | None:
    """`core.store_purchases` rows do not select the restore branch: branch selection compares the
    current owner on the canonical `core.subscriptions` row for the store subscription against the
    destination user, regardless of which user is recorded as `purchase_user_id`."""
    # [impl->req~schema-store-purchases-not-branch-selector~1]
    del purchase
    assert_not_an_ownership_selector("core.subscriptions.user_id")
    return subscription.user_id


def assert_purchase_user_id_not_load_bearing(inputs: Iterable[str]) -> None:
    """`purchase_user_id` is not load-bearing for branch selection, active-user checks, or restore
    source attribution: none of those decisions may read it."""
    # [impl->req~schema-store-purchases-purchase-user-id-not-load-bearing~1]
    for name in inputs:
        assert_not_an_ownership_selector(str(name))


class PurchaseAttributionUse(StrEnum):
    """What a purchase row's recorded attribution is, and is not, used for."""
    attribution_record = "attribution_record"
    branch_selection = "branch_selection"
    active_user_check = "active_user_check"
    restore_source_attribution = "restore_source_attribution"


NON_LOAD_BEARING_USES: frozenset[PurchaseAttributionUse] = frozenset({
    PurchaseAttributionUse.branch_selection,
    PurchaseAttributionUse.active_user_check,
    PurchaseAttributionUse.restore_source_attribution,
})


def assert_purchase_user_id_use(use: PurchaseAttributionUse) -> None:
    """The one thing `purchase_user_id` is for is the durable attribution record."""
    # [impl->req~schema-store-purchases-purchase-user-id-not-load-bearing~1]
    if use in NON_LOAD_BEARING_USES:
        raise SubscriptionSchemaError(f"purchase_user_id is not load-bearing for {use}")
