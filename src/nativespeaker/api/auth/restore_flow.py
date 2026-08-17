"""The restore flow: six ordered steps, the branching and reject policy they feed, and the
conjunction that authorizes an outcome.

Every decision here is taken from verified server state. The verified store artifact yields a
`(provider, external_id)` store subscription; the canonical `core.subscriptions` row for that key
supplies the current owner, status and tier; the `core.store_purchases` row for the same key
supplies the recorded attribution; and the branch follows from comparing that current owner against
the destination user. Nothing the client sends selects any of it.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.invariants import InvariantError, StoreProvider, assert_owner_agreement
from nativespeaker.api.auth.proof_restore import StoreVerifier, VerifiedStoreProof
from nativespeaker.api.auth.restore import (
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
)
from nativespeaker.api.auth.restore_proof_policy import (
    BindingOutcome,
    bind_store_transaction,
    verify_store_artifact,
)
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.grants import is_product_entitled

# The one resolution key for both tables: the provider's stable store subscription identity within
# the provider namespace, together with the provider.
RESOLUTION_KEY: tuple[str, str] = ("provider", "external_id")


@dataclass(frozen=True, slots=True)
class VerifiedTransaction:
    """What server-side verification of the store artifact resolved: the store subscription's
    stable identity, and the purchase UUID the same signed transaction carried, where it carried
    one."""
    provider: StoreProvider
    external_id: str
    carried_purchase_uuid: str | None = None

    @property
    def key(self) -> tuple[StoreProvider, str]:
        return self.provider, self.external_id


@dataclass(frozen=True, slots=True)
class SubscriptionRow:
    """The canonical `core.subscriptions` row for one `(provider, external_id)` store
    subscription."""
    subscription_id: UUID
    provider: StoreProvider
    external_id: str
    status: SubscriptionStatus
    tier_id: str
    user_id: UUID | None = None
    restore_bound_user_id: UUID | None = None

    @property
    def key(self) -> tuple[StoreProvider, str]:
        return self.provider, self.external_id


@dataclass(frozen=True, slots=True)
class PurchaseRow:
    """The `core.store_purchases` row for one accepted store subscription: the attribution token
    value or the server-generated internal purchase UUID recorded in its place, the store
    transaction identifiers where the store supplied them, the user the attribution resolved to,
    and — where it resolved to one — the token it resolved through, which is that same
    `identity_value`."""
    purchase_id: UUID
    provider: StoreProvider
    external_id: str
    identity_value: str
    purchase_user_id: UUID | None = None
    store_transaction_id: str | None = None
    store_original_transaction_id: str | None = None
    resolved_token_value: str | None = None

    @property
    def key(self) -> tuple[StoreProvider, str]:
        return self.provider, self.external_id


# --- Step 1: verify the signed transaction -------------------------------------------------------


def verify_signed_transaction(platform: Any,
                              body: Mapping[str, Any] | None,
                              verifier: StoreVerifier,
                              *,
                              performed_checks: Iterable[str]) -> VerifiedTransaction:
    """Step 1: the backend verifies the supplied StoreKit signed transaction server-side.

    Everything downstream reads what that verification returned and nothing else — the store
    subscription's stable identity and the purchase UUID the same verified signed transaction
    carried. The client cannot supply that carried value, so it cannot decide whether the step-4
    comparison fires; a `carried_purchase_uuid` field in the request body is refused outright.
    """
    # [impl->req~restore-flow-01-verify-signed-transaction~1]
    if "carried_purchase_uuid" in dict(body or {}):
        raise RestoreRejection(AuthEventResult.invalid_restore_proof,
                               "the carried purchase UUID comes from the verified transaction")
    verified: VerifiedStoreProof = verify_store_artifact(platform, body, verifier,
                                                         performed_checks=performed_checks)
    return VerifiedTransaction(
        provider=StoreProvider(str(verified.provider)),
        external_id=verified.external_id,
        carried_purchase_uuid=(str(verified.purchase_uuid)
                               if verified.purchase_uuid is not None else None))


# --- Step 2: resolve the canonical subscription --------------------------------------------------


@dataclass(frozen=True, slots=True)
class CurrentSubscriptionState:
    """What the canonical row supplies for the store subscription: its current owner, status and
    tier. A `None` row is the adoption-with-creation case, not a rejection."""
    row: SubscriptionRow | None

    @property
    def user_id(self) -> UUID | None:
        return self.row.user_id if self.row is not None else None

    @property
    def status(self) -> SubscriptionStatus | None:
        return self.row.status if self.row is not None else None

    @property
    def tier_id(self) -> str | None:
        return self.row.tier_id if self.row is not None else None

    @property
    def restore_bound_user_id(self) -> UUID | None:
        return self.row.restore_bound_user_id if self.row is not None else None


def resolve_canonical_subscription(rows: Sequence[SubscriptionRow],
                                   verified: VerifiedTransaction) -> CurrentSubscriptionState:
    """Step 2: extract the provider's stable store subscription identity and resolve it through
    `core.subscriptions` to the canonical row for `(provider, external_id)`. That row supplies the
    current `user_id`, `status` and `tier_id` for the store subscription."""
    # [impl->req~restore-flow-02-resolve-canonical-subscription~1]
    matches = [row for row in rows if row.key == verified.key]
    if len(matches) > 1:
        raise RestoreContractError(
            f"{verified.key} names exactly one canonical subscription row")
    return CurrentSubscriptionState(row=matches[0] if matches else None)


# --- Step 3: resolve the purchase row -------------------------------------------------------------


def resolve_purchase_row(rows: Sequence[PurchaseRow],
                         verified: VerifiedTransaction,
                         *,
                         by_token: bool = False) -> PurchaseRow | None:
    """Step 3: resolve the `core.store_purchases` row for the verified store subscription directly
    by `(provider, external_id)`.

    Token-only resolution is not used: one token spans an account's entire purchase history and may
    cover many rows, so older rows carrying the same stable token are irrelevant to this restore.
    """
    # [impl->req~restore-flow-03-resolve-purchase-row-by-provider-external-id~1]
    if by_token:
        raise RestoreContractError("token-only purchase resolution is not used")
    matches = [row for row in rows if row.key == verified.key]
    if len(matches) > 1:
        raise RestoreContractError(f"{verified.key} names exactly one purchase row")
    return matches[0] if matches else None


# --- Step 4: the carried purchase UUID ------------------------------------------------------------


def assert_carried_uuid_matches_recorded(*,
                                         carried: str | None,
                                         recorded: str | None) -> str | None:
    """The one comparison behind step 4, wherever it is reached from: a carried purchase UUID that
    differs from the recorded attribution rejects with `restore_purchase_uuid_mismatch`, and no
    other outcome stands for that condition."""
    # [impl->req~restore-flow-04-carried-uuid-must-match-identity-value~1]
    # [impl->req~restore-policy-purchase-uuid-mismatch-rejects~1]
    if carried is None or recorded is None:
        return carried
    if carried != recorded:
        raise RestoreRejection(AuthEventResult.restore_purchase_uuid_mismatch,
                               "the subscription is attributed to a different token")
    return carried


def assert_carried_uuid_matches(verified: VerifiedTransaction,
                                purchase_row: PurchaseRow | None) -> str | None:
    """Step 4: where the same verified signed transaction carries a purchase UUID value, it must
    equal the resolved row's recorded `identity_value`. A carried purchase UUID that differs is not
    proof for this restore: the presented subscription exists but is attributed to a different
    token."""
    # [impl->req~restore-flow-04-carried-uuid-must-match-identity-value~1]
    # [impl->req~restore-policy-purchase-uuid-mismatch-rejects~1]
    return assert_carried_uuid_matches_recorded(
        carried=verified.carried_purchase_uuid,
        recorded=purchase_row.identity_value if purchase_row is not None else None)


def internal_purchase_uuid(verified: VerifiedTransaction) -> str:
    """A verified signed transaction that carries no echoed token does not reject: store-initiated
    transactions legitimately omit it, and the purchase-row bookkeeping then uses a
    server-generated internal purchase UUID at creation."""
    # [impl->req~restore-policy-missing-echoed-token-not-rejected~1]
    if verified.carried_purchase_uuid:
        return verified.carried_purchase_uuid
    return str(uuid4())


# --- Step 5: branch selection ---------------------------------------------------------------------


def already_linked_rejection(*, source_user_active: bool) -> RestoreRejection:
    """The rejection every attempt refused because the store transaction is linked to a different
    account takes — the owner branch and the lifetime binding alike.

    The source-owner-active precondition is retained inside it: a linked source account that is
    inactive, blocked or retired, audits as `restore_source_user_inactive` in place of
    `store_transaction_already_linked`. Both surface as transfer-not-allowed.
    """
    # [impl->req~restore-policy-different-owner-rejects~1]
    if not source_user_active:
        return RestoreRejection(AuthEventResult.restore_source_user_inactive,
                                "the linked source account is not active")
    return RestoreRejection(AuthEventResult.store_transaction_already_linked,
                            "this store transaction is already linked to another account")


def select_branch(*,
                  subscription: CurrentSubscriptionState,
                  destination_user_id: UUID,
                  grant_user_id: UUID | None = None,
                  source_user_active: bool = True) -> RestoreBranch:
    """Step 5: the branch is selected by comparing the current owner from step 2 — the `user_id` on
    the canonical row, which must agree with the subscription-backed `core.access_grants.user_id` —
    against the destination user.

    Equal selects the same-account branch; an unclaimed subscription, or no canonical row at all,
    selects the adoption branch; and a different current owner is rejected with
    `store_transaction_already_linked`, never transferred. Where that linked source account is
    itself inactive — blocked or retired — the rejection audits as `restore_source_user_inactive`
    instead.
    """
    # [impl->req~restore-flow-05-branch-selection~1]
    # [impl->req~restore-branches-server-selected~1]
    # [impl->req~restore-endpoint-operation-and-branch-selection~1]
    # [impl->req~restore-policy-unclaimed-selects-adoption~1]
    # [impl->req~restore-policy-same-owner-selects-same-account~1]
    # [impl->req~restore-policy-different-owner-rejects~1]
    owner = subscription.user_id
    if owner is None:
        return RestoreBranch.adoption
    if grant_user_id is not None:
        try:
            assert_owner_agreement(grant_user_id=grant_user_id, subscription_user_id=owner)
        except InvariantError:
            raise RestoreRejection(
                AuthEventResult.restore_subscription_grant_owner_mismatch,
                "the canonical row and its subscription-backed grant name different owners"
            ) from None
    if owner == destination_user_id:
        return RestoreBranch.same_account
    raise already_linked_rejection(source_user_active=source_user_active)


def apply_lifetime_binding(*,
                           subscription: CurrentSubscriptionState,
                           destination_user_id: UUID,
                           source_user_active: bool = True) -> BindingOutcome:
    """Independently of branch selection, the lifetime store-transaction-to-account binding applies
    to every attempt: a destination equal to a non-NULL binding proceeds as idempotent re-restore, a
    destination that differs rejects and is never silently re-linked, and a successful restore of
    either branch sets the binding where it is still NULL.

    A binding mismatch is one of the attempts this document rejects because the store transaction is
    linked to a different account, so it takes the same substitution: an inactive linked source
    account audits as `restore_source_user_inactive` rather than `store_transaction_already_linked`.
    """
    # [impl->req~restore-policy-lifetime-binding-applies-to-every-attempt~1]
    try:
        return bind_store_transaction(restore_bound_user_id=subscription.restore_bound_user_id,
                                      destination_user_id=destination_user_id)
    except RestoreRejection as rejection:
        if rejection.result is AuthEventResult.store_transaction_already_linked:
            raise already_linked_rejection(source_user_active=source_user_active) from None
        raise


# --- Owner changes ---------------------------------------------------------------------------------

# The one branch that may change a store subscription's current owner. Manual binding repair
# changes no owner directly: it returns the row to unclaimed and leaves this same path to set the
# new one.
OWNER_CHANGING_BRANCHES: frozenset[RestoreBranch] = frozenset({RestoreBranch.adoption})

# Paths that move an existing subscription-backed grant to a different user: none.
GRANT_REASSIGNMENT_PATHS: frozenset[str] = frozenset()


def assert_owner_change_only_by_adoption(*,
                                         branch: RestoreBranch,
                                         grant_created_for: UUID | None,
                                         destination_user_id: UUID,
                                         subscription_transaction: object,
                                         grant_transaction: object,
                                         moved_grant_user_id: UUID | None = None) -> UUID:
    """For subscription-backed access, a store subscription's current owner changes only when
    restore adopts an unclaimed subscription, and that adoption creates the subscription-backed
    grant for the destination user in the same transaction.

    No path moves an existing subscription-backed grant to a different user, so a reassignment is
    refused here rather than represented as an owner change.
    """
    # [impl->req~restore-owner-changes-only-by-adoption~1]
    if GRANT_REASSIGNMENT_PATHS or moved_grant_user_id is not None:
        raise RestoreContractError(
            "no path moves an existing subscription-backed grant to a different user")
    if branch not in OWNER_CHANGING_BRANCHES:
        raise RestoreContractError(f"{branch} changes no store subscription's owner")
    if subscription_transaction is not grant_transaction:
        raise RestoreContractError(
            "adoption creates the subscription-backed grant in the same transaction")
    if grant_created_for != destination_user_id:
        raise RestoreContractError(
            f"adoption creates the grant for {destination_user_id}, not {grant_created_for}")
    return destination_user_id


# --- Step 6: product-entitled state ---------------------------------------------------------------


def assert_product_entitled(status: SubscriptionStatus | None,
                            *, live_verified_status: SubscriptionStatus | None = None) -> None:
    """Step 6: only if the resolved current `core.subscriptions` state for the store subscription is
    product-entitled does the backend move or attach the subscription-backed access grant.

    On the adoption-with-creation path, where no canonical row exists, the live-verified store state
    is what has to be product-entitled — the row is created at that state.
    """
    # [impl->req~restore-flow-06-product-entitled-required~1]
    effective = status if status is not None else live_verified_status
    if effective is None:
        raise RestoreRejection(AuthEventResult.restore_subscription_not_entitled,
                               "no product-entitled state stands behind the verified material")
    if not is_product_entitled(effective):
        raise RestoreRejection(AuthEventResult.restore_subscription_not_entitled,
                               f"{effective} is not product-entitled")


# --- Branching and reject policy ------------------------------------------------------------------


# The rows a missing resolution leads to creating rather than rejecting on, and the branch that
# creation belongs to.
CREATION_BRANCH: RestoreBranch = RestoreBranch.adoption


def missing_subscription_row_path(subscription: CurrentSubscriptionState) -> RestoreBranch | None:
    """If no `core.subscriptions` row exists for the resolved `(provider, external_id)`, restore
    proceeds on the adoption-with-creation path: the canonical row is created from the
    store-verified data inside the locked mutation transaction."""
    # [impl->req~restore-policy-missing-subscription-row-adoption-with-creation~1]
    if subscription.row is not None:
        return None
    return CREATION_BRANCH


def missing_purchase_row_path(purchase_row: PurchaseRow | None,
                              *, store_verified: bool = True) -> RestoreBranch | None:
    """If no `core.store_purchases` row exists for the resolved `(provider, external_id)`, the
    missing purchase row is created the same way; only a proof that fails store verification itself
    rejects for proof reasons."""
    # [impl->req~restore-policy-missing-purchase-row-created~1]
    if not store_verified:
        raise RestoreRejection(AuthEventResult.invalid_restore_proof,
                               "the proof failed store verification itself")
    if purchase_row is not None:
        return None
    return CREATION_BRANCH


# What restore may do to a `core.store_purchases` row beyond insert-once creation of a missing one:
# nothing. Rows are never reassigned, revoked, rewritten, or otherwise mutated by either branch.
PURCHASE_ROW_MUTATIONS: frozenset[str] = frozenset()
PURCHASE_ROW_INSERT_ONCE: str = "insert_once_creation_of_a_missing_row"


def assert_purchase_row_immutable(*,
                                  purchase_row: PurchaseRow | None,
                                  operation: str,
                                  branch: RestoreBranch) -> PurchaseRow | None:
    """`core.store_purchases` rows are immutable: never reassigned, revoked, rewritten, or otherwise
    mutated by either restore branch. Their `purchase_user_id` continues to identify the user the
    echoed token resolved to at purchase ingestion, regardless of subsequent owner changes."""
    # [impl->req~restore-policy-purchase-rows-immutable~1]
    if PURCHASE_ROW_MUTATIONS:
        raise RestoreContractError("restore mutates no purchase row")
    if operation == PURCHASE_ROW_INSERT_ONCE:
        if purchase_row is not None:
            raise RestoreContractError("insert-once creation applies to a missing row only")
        return None
    raise RestoreContractError(f"{operation} is no permitted purchase-row write on {branch}")


# --- The authorization conjunction ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RestoreAuthorization:
    """The authorized outcome: the branch, and the binding decision that came with it."""
    branch: RestoreBranch
    binding: BindingOutcome


def authorize_restore(*,
                      subscription: CurrentSubscriptionState,
                      purchase_row: PurchaseRow | None,
                      verified: VerifiedTransaction,
                      destination_user_id: UUID,
                      grant_user_id: UUID | None = None,
                      source_user_active: bool = True,
                      destination_holds_different_active_grant: bool = False,
                      live_store_verified: bool | None = None,
                      live_verified_status: SubscriptionStatus | None = None) -> RestoreAuthorization:
    """A verified signed transaction is not by itself proof that the current user owns the
    subscription.

    Same-account ownership is established by the current owner on the canonical row equaling the
    destination user — which must agree with the subscription-backed grant's `user_id` — combined
    with successful resolution, or insert-once creation, of the purchase row for the verified store
    subscription's `(provider, external_id)`, with any carried purchase UUID matching its recorded
    `identity_value`. Adoption is authorized only by the conjunction of an unclaimed canonical row,
    that same resolution or creation, the additional adoption preconditions including an active
    destination holding no different active grant, and live store-state verification. A current
    owner that differs from the destination user is rejected with `store_transaction_already_linked`.
    """
    # [impl->req~restore-ownership-authorization-conjunction~1]
    binding = apply_lifetime_binding(subscription=subscription,
                                     destination_user_id=destination_user_id,
                                     source_user_active=source_user_active)
    branch = select_branch(subscription=subscription,
                           destination_user_id=destination_user_id,
                           grant_user_id=grant_user_id,
                           source_user_active=source_user_active)
    assert_carried_uuid_matches(verified, purchase_row)
    if purchase_row is None:
        missing_purchase_row_path(purchase_row)
    if branch is RestoreBranch.adoption:
        if destination_holds_different_active_grant:
            raise RestoreRejection(AuthEventResult.restore_destination_already_entitled,
                                   "the destination already holds a different active grant")
        if not live_store_verified:
            raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                                   "adoption requires live store-state verification")
    assert_product_entitled(subscription.status, live_verified_status=live_verified_status)
    return RestoreAuthorization(branch=branch, binding=binding)
