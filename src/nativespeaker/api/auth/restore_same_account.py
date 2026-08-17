"""The same-account branch: its entry condition, its four mutation rules, and its postconditions.

Same-account restore settles an entitlement the destination user already owns. It changes no owner
on `core.subscriptions`, changes no ownership on the subscription-backed grant, and makes exactly
one kind of write to `core.store_purchases` — the insert-once creation of a row that never existed.
Live store-state verification belongs to the adoption branch and is not part of this one.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult, movement_details
from nativespeaker.api.auth.entitlement import AccessGrantStatus
from nativespeaker.api.auth.invariants import InvariantError, StoreProvider, assert_owner_agreement
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
)
from nativespeaker.api.auth.restore_flow import (
    PURCHASE_ROW_INSERT_ONCE,
    CurrentSubscriptionState,
    PurchaseRow,
    VerifiedTransaction,
    already_linked_rejection,
    apply_lifetime_binding,
    assert_carried_uuid_matches,
    assert_product_entitled,
    assert_purchase_row_immutable,
    internal_purchase_uuid,
)
from nativespeaker.api.auth.restore_operation import RestoreGrantMutations
from nativespeaker.api.auth.schema_invariants import assert_no_never_written_column
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.grants import is_product_entitled
from nativespeaker.api.quota.usage import assert_stays_with_grant


class SameAccountError(RestoreContractError):
    """The same-account branch was about to break one of its own guarantees."""


@dataclass(frozen=True, slots=True)
class SubscriptionGrant:
    """The subscription-backed `core.access_grants` row for the resolved store subscription."""
    grant_id: UUID
    user_id: UUID
    status: AccessGrantStatus
    subscription_id: UUID
    tier_id: str
    ends_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PaidPeriod:
    """The subscription's current paid period, which a reactivated grant re-derives from."""
    tier_id: str
    ends_at: datetime | None = None


# --- Entry condition ------------------------------------------------------------------------------


def entry_owner_equals_destination(subscription: CurrentSubscriptionState,
                                   *,
                                   destination_user_id: UUID,
                                   grant: SubscriptionGrant | None = None) -> bool:
    """The current owner from the canonical `core.subscriptions` row for the resolved
    `(provider, external_id)` store subscription equals the current authenticated (destination)
    user, and that owner must agree with the subscription-backed `core.access_grants.user_id`.

    A canonical row and its subscription-backed grant that name different owners is not a
    same-account entry at all: it is the owner-mismatch rejection.
    """
    # [impl->req~restore-same-account-entry-owner-equals-destination~1]
    owner = subscription.user_id
    if owner is None:
        return False
    if grant is not None:
        try:
            assert_owner_agreement(grant_user_id=grant.user_id, subscription_user_id=owner)
        except InvariantError:
            raise RestoreRejection(
                AuthEventResult.restore_subscription_grant_owner_mismatch,
                "the canonical row and its subscription-backed grant name different owners"
            ) from None
    return owner == destination_user_id


def entry_destination_active(*,
                             destination_user_id: UUID,
                             destination_active: bool) -> UUID:
    """The destination user is `active`. An inactive destination is audited as `blocked_user` and
    performs no mutation."""
    # [impl->req~restore-same-account-entry-destination-active~1]
    if not destination_active:
        raise RestoreRejection(AuthEventResult.blocked_user,
                               "the destination user is not active")
    return destination_user_id


def already_owned_is_this_branch(*,
                                 subscription: CurrentSubscriptionState,
                                 purchase_row: PurchaseRow | None,
                                 destination_user_id: UUID,
                                 rejected_as: AuthEventResult | None = None,
                                 recorded_source_user_id: UUID | None = None,
                                 subscription_columns_written: Iterable[str] = ()
                                 ) -> RestoreBranch:
    """An already-owned restore is the same-account branch, not an outcome of its own.

    The entry condition is met whenever the current owner equals the destination user, including
    where the resolved `core.store_purchases.purchase_user_id` names a different historical
    token-bound purchase user. Such an attempt must never be rejected as
    `restore_destination_already_entitled` — that code stands for a *different* active grant on the
    destination. The retained monthly cross-account transfer cap column is not updated, and any
    recorded source user is `NULL` or the current owner, never the token-bound purchase user.
    """
    # [impl->req~restore-same-account-already-owned-is-this-branch~1]
    owner = subscription.user_id
    if owner is None or owner != destination_user_id:
        raise SameAccountError(
            "an already-owned restore is one whose current owner is the destination user")
    if rejected_as is AuthEventResult.restore_destination_already_entitled:
        raise SameAccountError(
            "restore_destination_already_entitled stands for a different active grant, never for "
            "the owned subscription itself")
    assert_no_never_written_column("core.subscriptions", subscription_columns_written)
    if recorded_source_user_id is not None and recorded_source_user_id != owner:
        token_bound = purchase_row.purchase_user_id if purchase_row is not None else None
        raise SameAccountError(
            f"the recorded source user is NULL or the current owner, never {token_bound}")
    return RestoreBranch.same_account


# --- Mutation rules -------------------------------------------------------------------------------

# Writes the same-account branch never performs: it moves no owner and reassigns no grant.
SAME_ACCOUNT_FORBIDDEN_MUTATIONS: frozenset[str] = frozenset({
    "subscriptions_owner_change", "grant_ownership_change",
})


@dataclass(frozen=True, slots=True)
class StateRefresh:
    """A subscription-state refresh product policy permits — a tier or status confirmation observed
    from the verified store proof. It updates the canonical `core.subscriptions` row and the
    subscription-backed grant in the same transaction, under the regular subscription-state dedupe
    rules."""
    status: SubscriptionStatus
    subscription_transaction: object
    grant_transaction: object
    deduped: bool = True


def mutation_01_validate_before_mutation(*,
                                         subscription: CurrentSubscriptionState,
                                         purchase_row: PurchaseRow | None,
                                         verified: VerifiedTransaction,
                                         destination_user_id: UUID,
                                         grant: SubscriptionGrant | None,
                                         mutations: RestoreGrantMutations,
                                         creating_purchase_row: bool = False,
                                         performed: Iterable[str] = (),
                                         state_refresh: StateRefresh | None = None) -> UUID:
    """1. Confirm the subscription is product-entitled and complete ownership and linkage
    validation — the current owner equal to the destination user, the lifetime store-transaction
    binding, and the `core.store_purchases` resolution — before any grant mutation.

    This is where `store_transaction_already_linked` and the different-active-grant conflict are
    decided. Same-account restore performs no owner-change on `core.subscriptions` and no ownership
    change on the subscription-backed grant. A permitted state refresh is expressed as updating the
    canonical row and the subscription-backed grant in the same transaction, under the regular
    subscription-state dedupe rules.
    """
    # [impl->req~restore-same-account-mutation-01-validate-before-mutation~1]
    offending = sorted(set(performed) & SAME_ACCOUNT_FORBIDDEN_MUTATIONS)
    if offending:
        raise SameAccountError(f"same-account restore performs no {offending}")
    if mutations.statements:
        raise SameAccountError("validation completes before any grant mutation")
    assert_product_entitled(subscription.status)
    if not entry_owner_equals_destination(subscription,
                                          destination_user_id=destination_user_id,
                                          grant=grant):
        raise already_linked_rejection(source_user_active=True)
    apply_lifetime_binding(subscription=subscription, destination_user_id=destination_user_id)
    assert_carried_uuid_matches(verified, purchase_row)
    if purchase_row is None and not creating_purchase_row:
        raise SameAccountError(
            "the store purchase row is resolved, or created once, before any grant mutation")
    if state_refresh is not None:
        if state_refresh.subscription_transaction is not state_refresh.grant_transaction:
            raise SameAccountError(
                "a state refresh updates the canonical row and the grant in one transaction")
        if not state_refresh.deduped:
            raise SameAccountError("a state refresh uses the regular subscription-state dedupe")
    mutations.validate()
    return destination_user_id


class GrantSettlement(StrEnum):
    """How rule 2 settled the subscription-backed grant's status."""
    idempotent_success = "idempotent_success"
    reactivated = "reactivated"


@dataclass(frozen=True, slots=True)
class SettledGrant:
    """The settled grant: the same row, at the status rule 2 left it."""
    settlement: GrantSettlement
    grant_id: UUID
    status: AccessGrantStatus
    tier_id: str
    ends_at: datetime | None


def mutation_02_settle_grant_status(*,
                                    status: SubscriptionStatus,
                                    grant: SubscriptionGrant | None,
                                    mutations: RestoreGrantMutations,
                                    paid_period: PaidPeriod | None = None,
                                    different_active_grant_id: UUID | None = None,
                                    mint_new_grant_row: bool = False,
                                    replace_attribution_tokens: bool = False) -> SettledGrant:
    """2. Settle the subscription-backed grant's status rather than asserting it, by exactly one of
    four cases, ensuring a sole active grant rather than repairing dual actives.

    Entitled with the grant already active is idempotent success. Entitled with the grant expired
    reactivates that same current-term row by `UPDATE` in this transaction, with entitlement-derived
    and expiry fields re-derived from the subscription's current paid period; the row is reused and
    never re-minted, and the account's purchase-attribution tokens are never replaced. Entitled with
    a *different* active grant standing is the canonical `restore_destination_already_entitled`
    conflict, and no different active grant is ever expired to make room. Not entitled is
    `restore_subscription_not_entitled`, and no subscription-backed grant is activated or kept
    active. An entitled owned subscription with no subscription-backed grant row at all is data
    corruption: the attempt fails closed with `internal_error` and never creates the grant.
    """
    # [impl->req~restore-same-account-mutation-02-settle-grant-status~1]
    if mint_new_grant_row:
        raise SameAccountError("the existing grant row is reused; restore never mints a new one")
    if replace_attribution_tokens:
        raise SameAccountError(
            "purchase-attribution tokens are never replaced and live for the account's life")
    if not is_product_entitled(status):
        # Not entitled: never activate, and never keep active, a subscription-backed grant.
        raise RestoreRejection(AuthEventResult.restore_subscription_not_entitled,
                               f"{status} is not product-entitled")
    if grant is None:
        # Data corruption. Adoption is the one restore path that creates a grant, by design.
        raise RestoreRejection(
            AuthEventResult.internal_error,
            "an entitled owned subscription with no subscription-backed grant row is corruption")
    if different_active_grant_id is not None and different_active_grant_id != grant.grant_id:
        # No grant source is exempt and none outranks another; nothing is expired to make room.
        raise RestoreRejection(AuthEventResult.restore_destination_already_entitled,
                               "a different active grant stands in the way of the restoration")
    if grant.status is AccessGrantStatus.active:
        if mutations.statements:
            raise SameAccountError("an already-active grant is settled idempotently")
        return SettledGrant(settlement=GrantSettlement.idempotent_success,
                            grant_id=grant.grant_id,
                            status=AccessGrantStatus.active,
                            tier_id=grant.tier_id,
                            ends_at=grant.ends_at)
    period = paid_period or PaidPeriod(tier_id=grant.tier_id, ends_at=grant.ends_at)
    mutations.activate(grant.grant_id)
    return SettledGrant(settlement=GrantSettlement.reactivated,
                        grant_id=grant.grant_id,
                        status=AccessGrantStatus.active,
                        tier_id=period.tier_id,
                        ends_at=period.ends_at)


@dataclass(frozen=True, slots=True)
class PurchaseRowInsert:
    """The one `core.store_purchases` row a restore branch may write: a missing one, once, from the
    store-verified data. Both branches write it the same way, so it is described once."""
    provider: StoreProvider
    external_id: str
    identity_value: str
    purchase_user_id: UUID
    store_transaction_id: str | None = None
    store_original_transaction_id: str | None = None


def mutation_03_purchase_row_insert_once(*,
                                         purchase_row: PurchaseRow | None,
                                         verified: VerifiedTransaction,
                                         destination_user_id: UUID,
                                         current_owner: UUID,
                                         operation: str = PURCHASE_ROW_INSERT_ONCE
                                         ) -> PurchaseRowInsert | None:
    """3. Do not update or revoke any `core.store_purchases` row.

    Where the verified transaction resolves to no row — a store-initiated transaction that never
    carried the echoed token, or one verified before the row existed — insert the missing row once
    from the store-verified data, with a server-generated internal purchase UUID where the
    transaction carries none and the destination user (the current owner) as `purchase_user_id`.
    The row is immutable once written.
    """
    # [impl->req~restore-same-account-mutation-03-purchase-row-insert-once~1]
    if operation != PURCHASE_ROW_INSERT_ONCE:
        raise SameAccountError(f"{operation} is no permitted same-account purchase-row write")
    if purchase_row is not None:
        # The row resolved: it is immutable, so this branch neither updates nor revokes it.
        return None
    assert_purchase_row_immutable(purchase_row=None, operation=operation,
                                  branch=RestoreBranch.same_account)
    if current_owner != destination_user_id:
        raise SameAccountError(
            "the created row records the destination user, who is the current owner")
    return PurchaseRowInsert(provider=verified.provider,
                             external_id=verified.external_id,
                             identity_value=internal_purchase_uuid(verified),
                             purchase_user_id=destination_user_id)


def mutation_04_audit_row(*,
                          current_owner: UUID,
                          destination_user_id: UUID,
                          purchase_row: PurchaseRow | None = None,
                          recorded_source_user_id: UUID | None = None,
                          subscription_id: UUID | None = None,
                          access_grant_id: UUID | None = None,
                          proof_fingerprints: Iterable[str] = ()) -> dict[str, Any]:
    """4. Append the single `audit.auth_events` row with `movement_classification = 'same_account'`
    in `details`.

    Any recorded source user is either `NULL` or the current owner, which for this branch equals the
    destination user. It is never the `purchase_user_id` from `core.store_purchases` where that user
    differs from the current owner.
    """
    # [impl->req~restore-same-account-mutation-04-audit-row~1]
    if current_owner != destination_user_id:
        raise SameAccountError("the same-account branch's current owner is the destination user")
    token_bound = purchase_row.purchase_user_id if purchase_row is not None else None
    if recorded_source_user_id is not None and recorded_source_user_id != current_owner:
        raise SameAccountError(
            f"the recorded source user is NULL or the current owner, never {token_bound}")
    return movement_details(
        movement_classification=str(MovementClassification.same_account),
        source_user_id=recorded_source_user_id,
        destination_user_id=destination_user_id,
        subscription_id=subscription_id,
        access_grant_id=access_grant_id,
        store_purchase_id=purchase_row.purchase_id if purchase_row is not None else None,
        proof_fingerprints=list(proof_fingerprints))


# --- Postconditions -------------------------------------------------------------------------------


def postcondition_grant_id_preserved(*,
                                     before: SubscriptionGrant,
                                     after: SubscriptionGrant,
                                     destination_user_id: UUID) -> UUID:
    """The existing subscription-backed grant continues to be owned by the destination user,
    keeping the same grant `id`."""
    # [impl->req~restore-same-account-postcondition-grant-id-preserved~1]
    if after.grant_id != before.grant_id:
        raise SameAccountError("the subscription-backed grant keeps its id across the call")
    if after.user_id != destination_user_id or before.user_id != destination_user_id:
        raise SameAccountError("the grant continues to be owned by the destination user")
    return after.grant_id


def postcondition_usage_row_attached(*,
                                     grant_id: UUID,
                                     usage_row_grant_id: UUID,
                                     minted_fresh: bool = False) -> UUID:
    """The monthly usage row attached to that grant remains attached to the same `grant_id`, so the
    restored subscription does not receive a fresh monthly counter."""
    # [impl->req~restore-same-account-postcondition-usage-row-attached~1]
    assert_stays_with_grant(stored_grant_id=grant_id,
                            row_grant_id=usage_row_grant_id,
                            minted_fresh=minted_fresh)
    return grant_id
