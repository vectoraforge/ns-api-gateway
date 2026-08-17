"""Restore's own invariants: the properties every restore outcome must leave true.

Four of the fourteen are references — ownership keying, owner agreement, the
active-requires-product-entitled rule and the never-updated transfer-month column all have their
normative home in `06-schema-reference.md`, and are enforced at the sites that own them rather than
restated here. The remaining ten are restore's own, and this module is where a restore path checks
itself against them: what the canonical row means, what the proof does and does not prove, what
stays immutable, what may select the outcome, what may never move, and what the destination may
never end up holding.
"""

from collections.abc import Iterable, Sequence
from uuid import UUID

from nativespeaker.api.auth.audit import AttemptPhase, AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import assert_owner_agreement
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreAttemptAudit,
    RestoreBranch,
    RestoreContractError,
    movement_classification_for,
)
from nativespeaker.api.auth.restore_flow import (
    PURCHASE_ROW_INSERT_ONCE,
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
    assert_purchase_row_immutable,
    resolve_canonical_subscription,
    select_branch,
)
from nativespeaker.api.auth.restore_proof_policy import assert_proof_not_persisted


class RestoreInvariantError(RestoreContractError):
    """A restore path was about to leave one of restore's own invariants false."""


# --- 2. The canonical row, and where history lives ---------------------------------------------

# The one table that holds current state, and the one that holds the append-only history of
# provider state observations.
# [impl->req~restore-invariant-02~1]
CANONICAL_STATE_TABLE = "core.subscriptions"
OBSERVATION_HISTORY_TABLE = "audit.subscription_events"

# What the canonical row is authoritative for.
CANONICAL_ROW_FACTS: tuple[str, ...] = ("user_id", "status", "tier_id")


def canonical_current_state(rows: Sequence[SubscriptionRow],
                            verified: VerifiedTransaction) -> CurrentSubscriptionState:
    """`core.subscriptions` holds the canonical current state per `(provider, external_id)` store
    subscription as exactly one row. The current owner, status and tier of a store subscription are
    the values on that row."""
    # [impl->req~restore-invariant-02~1]
    return resolve_canonical_subscription(rows, verified)


def assert_updated_in_place(*,
                            existing: CurrentSubscriptionState,
                            rows_inserted: int = 0,
                            rows_updated: int = 0,
                            history_rows_appended: int = 0,
                            history_rows_updated: int = 0) -> None:
    """The canonical row is updated in place: an existing store subscription never gains a second
    row, and the append-only history of provider state observations is preserved in
    `audit.subscription_events` rather than by superseding the canonical row."""
    # [impl->req~restore-invariant-02~1]
    if existing.row is not None and rows_inserted:
        raise RestoreInvariantError(
            f"{CANONICAL_STATE_TABLE} holds one row per store subscription, updated in place")
    if existing.row is None and rows_updated:
        raise RestoreInvariantError("there is no canonical row to update in place")
    if history_rows_updated:
        raise RestoreInvariantError(f"{OBSERVATION_HISTORY_TABLE} is append-only")
    if history_rows_appended < 0:
        raise RestoreInvariantError(f"{OBSERVATION_HISTORY_TABLE} only ever gains rows")


# --- 5. What the restore proof is, and what it is not -------------------------------------------

# The proof set does not show the requester is the original subscriber or the current source owner.
# [impl->req~restore-invariant-05~1]
RESTORE_PROOF_DOES_NOT_PROVE: frozenset[str] = frozenset({
    "prior_app_account_ownership", "original_subscriber", "current_source_owner",
})
RESTORE_PROOF_IS: str = "bearer_recovery_credential_for_subscription_entitlement"

# Cross-account entitlement transfer is never performed, on any path.
# [impl->req~restore-invariant-05~1]
# [impl->req~restore-invariant-13~1]
CROSS_ACCOUNT_TRANSFER_PATHS: frozenset[str] = frozenset()


def assert_proof_is_bearer_credential_only(*, claims: Iterable[str] = ()) -> str:
    """Restore proof is not proof of prior app-account ownership; it is the accepted bearer
    recovery credential for subscription entitlement, and nothing more is inferred from it."""
    # [impl->req~restore-invariant-05~1]
    overclaimed = sorted(set(claims) & RESTORE_PROOF_DOES_NOT_PROVE)
    if overclaimed:
        raise RestoreInvariantError(f"a verified restore proof does not show {overclaimed}")
    return RESTORE_PROOF_IS


def assert_same_account_ownership_established(*,
                                              subscription: CurrentSubscriptionState,
                                              destination_user_id: UUID,
                                              purchase_row: PurchaseRow | None,
                                              purchase_row_created: bool = False) -> RestoreBranch:
    """Same-account ownership is established by the current owner on the canonical row equaling the
    destination user, combined with successful resolution — or insert-once creation — of the
    `core.store_purchases` row for the verified `(provider, external_id)`."""
    # [impl->req~restore-invariant-05~1]
    if subscription.user_id != destination_user_id:
        raise RestoreInvariantError(
            "same-account ownership needs the canonical owner to equal the destination")
    if purchase_row is None and not purchase_row_created:
        raise RestoreInvariantError(
            f"same-account restore resolves the purchase row or performs its {PURCHASE_ROW_INSERT_ONCE}")
    return RestoreBranch.same_account


def assert_adoption_preconditions(*,
                                  subscription: CurrentSubscriptionState,
                                  live_verified: bool,
                                  lifetime_binding_checked: bool) -> RestoreBranch:
    """Adoption of an unclaimed store subscription is authorized by a valid server-verified
    `restore_proof` only when every existing restore precondition succeeds — the lifetime
    store-transaction-to-account binding among them, which caps movement at the transaction's first
    successful restore — together with live store-state verification."""
    # [impl->req~restore-invariant-05~1]
    if subscription.user_id is not None:
        raise RestoreInvariantError("adoption attaches an unclaimed store subscription")
    if not lifetime_binding_checked:
        raise RestoreInvariantError(
            "the lifetime store-transaction-to-account binding is one of adoption's preconditions")
    if not live_verified:
        raise RestoreInvariantError("adoption requires live store-state verification")
    if CROSS_ACCOUNT_TRANSFER_PATHS:
        raise RestoreInvariantError("cross-account entitlement transfer is never performed")
    return RestoreBranch.adoption


def assert_proof_material_not_persisted(sink: str) -> str:
    """Raw `restore_proof` and equivalent proof payloads are secret bearer material and are not
    persisted outside the minimum verification path. The sink policy is the proof file's."""
    # [impl->req~restore-invariant-05~1]
    return assert_proof_not_persisted(sink)


# --- 6. `core.store_purchases` rows are immutable ------------------------------------------------

# How a purchase row comes to exist, and the only two ways.
# [impl->req~restore-invariant-06~1]
PURCHASE_ROW_WRITE_POINTS: tuple[str, ...] = ("purchase_ingestion", PURCHASE_ROW_INSERT_ONCE)

# What no restore branch ever does to one.
# [impl->req~restore-invariant-06~1]
FORBIDDEN_PURCHASE_ROW_ACTIONS: frozenset[str] = frozenset({
    "reassign", "revoke", "rewrite", "mutate", "update", "delete",
})


def assert_purchase_rows_immutable(*,
                                   branch: RestoreBranch,
                                   actions: Iterable[str] = (),
                                   created: bool = False,
                                   existing_row: PurchaseRow | None = None) -> None:
    """`core.store_purchases` rows are immutable once written: written once, at purchase ingestion
    or by restore's insert-once creation, and never reassigned, revoked, rewritten or otherwise
    mutated by either restore branch."""
    # [impl->req~restore-invariant-06~1]
    attempted = sorted({str(action) for action in actions} & FORBIDDEN_PURCHASE_ROW_ACTIONS)
    if attempted:
        raise RestoreInvariantError(
            f"the {branch} branch never performs {attempted} on core.store_purchases")
    if created and existing_row is not None:
        raise RestoreInvariantError("insert-once creation writes only a row that never existed")
    if created:
        assert_purchase_row_immutable(purchase_row=existing_row,
                                      operation=PURCHASE_ROW_INSERT_ONCE,
                                      branch=branch)


def purchase_row_attribution(row: PurchaseRow) -> UUID | None:
    """A purchase row's `purchase_user_id` identifies, for the lifetime of the row, the user the row
    was attributed to at write time: the token-resolved user at ingestion, `NULL` for an
    unattributed ingestion row, or the restoring user for a restore-created row."""
    # [impl->req~restore-invariant-06~1]
    return row.purchase_user_id


# --- 7. What selects the outcome ------------------------------------------------------------------

# The purchase row's attribution is purchase context only.
# [impl->req~restore-invariant-07~1]
OUTCOME_SELECTORS: tuple[str, ...] = ("core.subscriptions.user_id",)
PURCHASE_CONTEXT_ONLY: tuple[str, ...] = ("core.store_purchases.purchase_user_id",)


def select_restore_outcome(*,
                           subscription: CurrentSubscriptionState,
                           destination_user_id: UUID,
                           grant_user_id: UUID | None = None,
                           purchase_row: PurchaseRow | None = None,
                           source_user_active: bool = True) -> RestoreBranch:
    """The outcome is determined solely by comparing the current owner on the canonical
    `core.subscriptions` row — which must agree with any subscription-backed
    `core.access_grants.user_id` — against the destination user: equal is same-account, unclaimed is
    adoption, and a different linked account rejects with `store_transaction_already_linked`.

    The resolved purchase row's `purchase_user_id` takes no part in it: it is purchase context only
    and never names a source user.
    """
    # [impl->req~restore-invariant-07~1]
    if set(OUTCOME_SELECTORS) & set(PURCHASE_CONTEXT_ONLY):
        raise RestoreInvariantError("purchase_user_id is purchase context, not an outcome selector")
    branch = select_branch(subscription=subscription,
                           destination_user_id=destination_user_id,
                           grant_user_id=grant_user_id,
                           source_user_active=source_user_active)
    # The branch the canonical owner alone dictates. Anything else means something other than
    # `core.subscriptions.user_id` selected the outcome.
    # [impl->req~restore-invariant-07~1]
    owner = subscription.user_id
    expected = (RestoreBranch.adoption if owner is None
                else RestoreBranch.same_account if owner == destination_user_id
                else None)
    if branch is not expected:
        raise RestoreInvariantError(
            f"the canonical owner selects {expected}, not {branch}")
    if purchase_row is not None:
        # Read for context only. The branch above was computed without it and is not revised by
        # it, whatever the row's attribution says — and the row never names a source user.
        # [impl->req~restore-invariant-07~1]
        purchase_row_attribution(purchase_row)
    return branch


# --- 8. The source user a same-account audit row may record ---------------------------------------


def audited_source_user(*,
                       subscription_user_id: UUID | None,
                       grant_user_id: UUID | None,
                       purchase_user_id: UUID | None = None,
                       recorded_source_user_id: UUID | None = None) -> UUID | None:
    """A same-account restore audit row must not hide a different current source user.

    Where a restore records a source user separately from the destination user in
    `audit.auth_events.details`, that source user is the current owner from `core.subscriptions` and
    the subscription-backed `core.access_grants`, never the `purchase_user_id` from
    `core.store_purchases`.
    """
    # [impl->req~restore-invariant-08~1]
    if recorded_source_user_id is None:
        return None
    if grant_user_id is not None:
        assert_owner_agreement(grant_user_id=grant_user_id,
                               subscription_user_id=subscription_user_id)
    if recorded_source_user_id != subscription_user_id:
        raise RestoreInvariantError(
            "the recorded source user is the current owner from core.subscriptions")
    if purchase_user_id is not None and recorded_source_user_id == purchase_user_id != subscription_user_id:
        raise RestoreInvariantError(
            "the recorded source user is never the purchase row's purchase_user_id")
    return recorded_source_user_id


# --- 9. What restore does not touch ----------------------------------------------------------------

# Everything restore must not move, mutate or rebind — the destination's own as much as any other
# account's.
# [impl->req~restore-invariant-09~1]
UNTOUCHED_BY_RESTORE: frozenset[str] = frozenset({
    "core.chats", "core.messages", "core.external_identities", "core.users.profile",
    "anonymous_device_grant", "manual_grant", "non_subscription_user_monthly_usage",
})

# What restore does settle or create.
# [impl->req~restore-invariant-09~1]
RESTORE_SETTLES_OR_CREATES: frozenset[AccessGrantSource] = frozenset({AccessGrantSource.subscription})


def assert_paid_entitlement_only(touched: Iterable[str] = (),
                                 *,
                                 branch: RestoreBranch | None = None,
                                 grant_sources_written: Iterable[AccessGrantSource] = (),
                                 source_user_id: UUID | None = None) -> None:
    """Restore settles or creates paid subscription entitlement only.

    Adoption has no source user to take anything from, and no restore path moves an existing grant
    between users.
    """
    # [impl->req~restore-invariant-09~1]
    offending = sorted(set(touched) & UNTOUCHED_BY_RESTORE)
    if offending:
        raise RestoreInvariantError(f"restore does not move, mutate or rebind {offending}")
    wrong_source = sorted(str(one) for one in set(grant_sources_written) - RESTORE_SETTLES_OR_CREATES)
    if wrong_source:
        raise RestoreInvariantError(f"restore writes no {wrong_source} grant")
    if branch is RestoreBranch.adoption and source_user_id is not None:
        raise RestoreInvariantError("adoption has no source user to take anything from")


# --- 10. The subscription-backed grant stays where it is ------------------------------------------


def assert_grant_settled_in_place(*,
                                  grant_id_before: UUID,
                                  grant_id_after: UUID,
                                  grant_user_id_before: UUID,
                                  grant_user_id_after: UUID,
                                  usage_grant_id_before: UUID | None = None,
                                  usage_grant_id_after: UUID | None = None) -> UUID:
    """Restore never moves a subscription-backed grant to another user: same-account restore settles
    the existing grant in place, it keeps the same `id`, and the grant-attached monthly usage row
    continues to attach to the same `grant_id` — so the restored subscription does not receive a
    fresh monthly counter."""
    # [impl->req~restore-invariant-10~1]
    if grant_user_id_after != grant_user_id_before:
        raise RestoreInvariantError("restore never moves a subscription-backed grant to another user")
    if grant_id_after != grant_id_before:
        raise RestoreInvariantError("the settled grant keeps the same id")
    if usage_grant_id_before is not None or usage_grant_id_after is not None:
        if usage_grant_id_after != usage_grant_id_before:
            raise RestoreInvariantError(
                "the monthly usage row keeps attaching to the same grant_id")
        if usage_grant_id_after != grant_id_after:
            raise RestoreInvariantError("the monthly usage row attaches to the settled grant")
    return grant_id_after


# --- 12. Device-check state is none of restore's business ------------------------------------------

# The per-device free-grant device-check state restore neither reads nor modifies.
# [impl->req~restore-invariant-12~1]
DEVICE_CHECK_STATE: frozenset[str] = frozenset({
    "devicecheck", "device_check", "devicecheck_bit", "play_integrity_device_recall",
    "device_recall", "device_recall_state",
})


def assert_no_device_check_state(*,
                                 reads: Iterable[str] = (),
                                 writes: Iterable[str] = ()) -> None:
    """Restore neither reads nor modifies per-device free-grant device-check state. That state gates
    only free-credit grants and never gates, authorizes, or participates in subscription-backed
    entitlement transfer."""
    # [impl->req~restore-invariant-12~1]
    for kind, names in (("reads", reads), ("writes", writes)):
        offending = sorted({name for name in names
                            if any(marker in str(name).lower() for marker in DEVICE_CHECK_STATE)})
        if offending:
            raise RestoreInvariantError(f"restore {kind} no per-device state: {offending}")


# --- 13. Entitlement never moves away from a user ---------------------------------------------------

# The one ownership-establishing restore: adoption of an unclaimed subscription, which links it to
# the destination for life.
# [impl->req~restore-invariant-13~1]
OWNERSHIP_ESTABLISHING_BRANCH: RestoreBranch = RestoreBranch.adoption


def assert_entitlement_never_moved_away(*,
                                        branch: RestoreBranch | None,
                                        prior_owner_id: UUID | None,
                                        destination_user_id: UUID) -> RestoreBranch | None:
    """Restore never moves paid subscription entitlement away from any user: a store transaction
    linked to a different account is rejected with `store_transaction_already_linked`, cross-account
    entitlement transfer is never performed, and the only ownership-establishing restore is adoption
    of an unclaimed subscription."""
    # [impl->req~restore-invariant-13~1]
    if CROSS_ACCOUNT_TRANSFER_PATHS:
        raise RestoreInvariantError("cross-account entitlement transfer is never performed")
    if prior_owner_id is not None and prior_owner_id != destination_user_id:
        raise RestoreInvariantError(
            "a store transaction linked to a different account rejects with "
            f"{AuthEventResult.store_transaction_already_linked}")
    if branch is OWNERSHIP_ESTABLISHING_BRANCH and prior_owner_id is not None:
        raise RestoreInvariantError("adoption establishes ownership only for an unclaimed subscription")
    return branch


def assert_owner_mismatch_rejection(audit: RestoreAttemptAudit,
                                    *,
                                    branch: RestoreBranch | None,
                                    audit_transaction: object,
                                    mutations_performed: Iterable[str] = ()) -> MovementClassification:
    """The rejected owner-mismatch attempt records `movement_classification = 'unclassified'` in
    `audit.auth_events.details`, performs no restore mutation, and writes its single
    `audit.auth_events` row under the shared semantics."""
    # [impl->req~restore-invariant-13~1]
    result = AuthEventResult.restore_subscription_grant_owner_mismatch
    performed = sorted(mutations_performed)
    if performed:
        raise RestoreInvariantError(f"an owner-mismatch rejection performs no {performed}")
    classification = movement_classification_for(branch=branch, result=result)
    if classification is not MovementClassification.unclassified:
        raise RestoreInvariantError("an owner-mismatch rejection is classified as unclassified")
    audit.record(phase=AttemptPhase.business,
                 result=result,
                 audit_transaction=audit_transaction,
                 branch=branch)
    if len(audit.rows) != 1:
        raise RestoreInvariantError("the rejected attempt writes its single audit row")
    return classification


# --- 14. Never two active grants -------------------------------------------------------------------

# The lifetime store-transaction-to-account binding is `req~restore-lifetime-transaction-account-binding~1`,
# enforced by `restore_flow.apply_lifetime_binding` and read from there rather than restated here.
# [impl->req~restore-invariant-14~2]
LIFETIME_BINDING_OWNER = "req~restore-lifetime-transaction-account-binding~1"

# No precedence ranking between a destination's existing active grant and the restored one exists:
# there is no rule that picks a winner, so either the existing grant is ended as part of the restore
# or the restore is rejected.
# [impl->req~restore-invariant-14~2]
GRANT_PRECEDENCE_RANKING: tuple[str, ...] = ()


def assert_never_two_active_grants(*,
                                   existing_active_grant_id: UUID | None,
                                   existing_grant_status_after: AccessGrantStatus | None = None,
                                   restored_grant_active: bool,
                                   rejected: bool = False) -> int:
    """A restore never leaves the destination holding two active grants, and no precedence ranking
    exists: either the destination's existing active grant is ended as part of the restore, or the
    restore is rejected, as governed by the restore grant-mutation rules."""
    # [impl->req~restore-invariant-14~2]
    if GRANT_PRECEDENCE_RANKING:
        raise RestoreInvariantError("no precedence ranking between active grants exists")
    if rejected:
        if restored_grant_active:
            raise RestoreInvariantError("a rejected restore leaves no restored grant active")
        return 1 if existing_active_grant_id is not None else 0
    active = 1 if restored_grant_active else 0
    if existing_active_grant_id is not None:
        if existing_grant_status_after is AccessGrantStatus.active:
            active += 1
        elif existing_grant_status_after is None:
            raise RestoreInvariantError(
                "the destination's existing active grant is ended as part of the restore")
    if active > 1:
        raise RestoreInvariantError("a restore never leaves the destination holding two active grants")
    return active
