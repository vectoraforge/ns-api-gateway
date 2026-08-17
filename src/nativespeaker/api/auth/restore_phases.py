"""Restore's nineteen common steps, in their two phases.

Steps 1 to 8 run before any restore mutation lock is held: proof re-verification, non-locking
resolutions, the provisional branch determination, and — for the adoption branch alone — the one
live provider call. Steps 9 to 19 run inside the locked mutation transaction: locks in the fixed
order, every piece of local state re-resolved under them, database-local checks only, the
branch-specific mutation, and the attempt's single audit row.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AttemptPhase, AuthEventResult
from nativespeaker.api.auth.invariants import InvariantError, StoreProvider, assert_owner_agreement
from nativespeaker.api.auth.locks import LockingPath, LockLedger
from nativespeaker.api.auth.proof_restore import StoreVerifier
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreAttemptAudit,
    RestoreAuditContext,
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
    movement_classification_for,
)
from nativespeaker.api.auth.restore_flow import (
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
    already_linked_rejection,
    assert_carried_uuid_matches,
    assert_carried_uuid_matches_recorded,
    assert_product_entitled,
    internal_purchase_uuid,
    resolve_canonical_subscription,
    resolve_purchase_row,
    select_branch,
    verify_signed_transaction,
)
from nativespeaker.api.auth.restore_operation import (
    RESTORE_MUTATIONS,
    RestoreGrantMutations,
    RestorePhase,
)
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.grants import is_product_entitled


class RestorePhaseError(RestoreContractError):
    """A restore step ran out of its phase, or claimed work its phase may not do."""


class RestoreContention(RuntimeError):
    """A lock wait timeout, a database-detected deadlock, or a serialization failure raised inside
    the locked mutation transaction. Transient contention, never a restore outcome."""


# --- The pre-transaction phase ---------------------------------------------------------------------


@dataclass(slots=True)
class PreTransactionLedger:
    """What the pre-transaction phase did, and what it is not allowed to have done: hold a restore
    mutation lock, or perform a restore mutation."""
    steps: list[str] = field(default_factory=list)
    barrier_admitted: bool = True
    locks_held: bool = False
    mutations: list[str] = field(default_factory=list)
    audit_rows: int = 0

    def record(self, step: str) -> None:
        self.steps.append(step)

    def mutate(self, mutation: str) -> None:
        self.mutations.append(mutation)


def assert_locks_not_held(ledger: PreTransactionLedger,
                          *, branch: RestoreBranch | None = None) -> PreTransactionLedger:
    """The pre-transaction steps apply to both branches, and the restore mutation locks are not
    yet held while any of them runs."""
    # [impl->req~restore-pre-transaction-locks-not-held~1]
    if ledger.locks_held:
        raise RestorePhaseError("the pre-transaction steps run before any restore mutation lock")
    if branch is not None and branch not in set(RestoreBranch):
        raise RestorePhaseError(f"{branch} is no restore branch")
    return ledger


def assert_barrier_and_audit_scope(ledger: PreTransactionLedger,
                                   *,
                                   rejected: bool = False,
                                   rejection_transaction: object | None = None,
                                   mutations_performed: Iterable[str] = ()) -> None:
    """Before step 1 runs, the shared barrier has already admitted the request.

    Any rejection produced by the pre-transaction steps writes the attempt's `audit.auth_events`
    row in one pre-transaction rejection transaction; "perform no mutation" in those steps means
    perform no restore mutation, not skip that audit write.
    """
    # [impl->req~restore-pre-transaction-barrier-and-audit-scope~1]
    if not ledger.barrier_admitted:
        raise RestorePhaseError("the shared barrier admits the request before step 1")
    performed = sorted(set(mutations_performed) | set(ledger.mutations))
    offending = sorted(set(performed) & RESTORE_MUTATIONS)
    if offending:
        raise RestorePhaseError(f"a pre-transaction step performs no restore mutation: {offending}")
    if not rejected:
        return
    if rejection_transaction is None:
        raise RestorePhaseError(
            "a pre-transaction rejection writes its audit row in its own rejection transaction")
    ledger.audit_rows += 1
    if ledger.audit_rows != 1:
        raise RestorePhaseError("one restore attempt writes one audit row")


def step_01_reverify_proof(platform: Any,
                           body: Mapping[str, Any] | None,
                           verifier: StoreVerifier,
                           *,
                           performed_checks: Iterable[str],
                           ledger: PreTransactionLedger,
                           branch: RestoreBranch | None = None) -> VerifiedTransaction:
    """1. Re-verify restore proof server-side, including the embedded signed transaction.

    An invalid or malformed proof, a failed signed-transaction verification, or a proof that does
    not supply the same transaction used to resolve the subscription entitlement rejects with the
    applicable verification result and performs no restore mutation. This validation runs before
    branch determination in step 5 and does not depend on which branch the attempt later resolves
    to, so no branch is passed to it.
    """
    # [impl->req~restore-pre-transaction-step-01-reverify-proof~1]
    assert_locks_not_held(ledger)
    if branch is not None:
        raise RestorePhaseError("step 1 runs before branch determination in step 5")
    ledger.record("01_reverify_proof")
    return verify_signed_transaction(platform, body, verifier,
                                     performed_checks=performed_checks)


def step_02_resolve_subscription(rows: Sequence[SubscriptionRow],
                                 verified: VerifiedTransaction,
                                 *,
                                 ledger: PreTransactionLedger,
                                 locking: bool = False
                                 ) -> tuple[CurrentSubscriptionState, bool]:
    """2. Resolve the store subscription identity through `core.subscriptions` as a non-locking
    read of the canonical row for `(provider, external_id)`.

    If no row exists, the attempt is marked adoption-with-creation: the canonical row will be
    created from the store-verified data inside the locked mutation transaction, and the missing
    row is no rejection.
    """
    # [impl->req~restore-pre-transaction-step-02-resolve-subscription~1]
    assert_locks_not_held(ledger)
    if locking:
        raise RestorePhaseError("step 2 is a non-locking read")
    ledger.record("02_resolve_subscription")
    subscription = resolve_canonical_subscription(rows, verified)
    return subscription, subscription.row is None


def step_03_extract_purchase_uuid(verified: VerifiedTransaction,
                                  *, ledger: PreTransactionLedger) -> str | None:
    """3. Extract the purchase UUID from the verified signed transaction where one is carried.

    A signed transaction that carries no provider-specific purchase UUID is not rejected; the
    purchase-row bookkeeping then uses a server-generated internal purchase UUID at creation.
    """
    # [impl->req~restore-pre-transaction-step-03-extract-purchase-uuid~1]
    assert_locks_not_held(ledger)
    ledger.record("03_extract_purchase_uuid")
    return verified.carried_purchase_uuid


def creation_purchase_uuid(verified: VerifiedTransaction) -> str:
    """The value the purchase row is created with where the transaction carried none: a
    server-generated internal purchase UUID."""
    # [impl->req~restore-pre-transaction-step-03-extract-purchase-uuid~1]
    return internal_purchase_uuid(verified)


def step_04_resolve_purchase_row(rows: Sequence[PurchaseRow],
                                 verified: VerifiedTransaction,
                                 *,
                                 ledger: PreTransactionLedger,
                                 locking: bool = False) -> PurchaseRow | None:
    """4. Resolve the `core.store_purchases` row directly by the `(provider, external_id)` resolved
    in step 2, as a non-locking read.

    A missing row is no rejection: it is created from the store-verified data inside the locked
    mutation transaction. Where the verified transaction carries a purchase UUID and the resolved
    row's recorded `identity_value` differs from it, the attempt rejects with
    `restore_purchase_uuid_mismatch` and performs no mutation.
    """
    # [impl->req~restore-pre-transaction-step-04-resolve-purchase-row~1]
    assert_locks_not_held(ledger)
    if locking:
        raise RestorePhaseError("step 4 is a non-locking read")
    ledger.record("04_resolve_purchase_row")
    purchase_row = resolve_purchase_row(rows, verified)
    assert_carried_uuid_matches(verified, purchase_row)
    return purchase_row


def step_05_determine_branch(subscription: CurrentSubscriptionState,
                             *,
                             destination_user_id: UUID,
                             ledger: PreTransactionLedger,
                             source_user_active: bool = True) -> RestoreBranch:
    """5. Determine the restore branch from the current owner read in step 2.

    An owner equal to the destination selects same-account; an unclaimed row, or no canonical row
    at all, selects adoption; a different account — or a non-NULL `restore_bound_user_id` that
    differs from the destination — rejects and performs no mutation, audited as
    `restore_source_user_inactive` where the linked source account is inactive and as
    `store_transaction_already_linked` otherwise. This determination is provisional: the locked
    phase re-confirms it from locked state.
    """
    # [impl->req~restore-pre-transaction-step-05-determine-branch~1]
    assert_locks_not_held(ledger)
    ledger.record("05_determine_branch")
    bound = subscription.restore_bound_user_id
    if bound is not None and bound != destination_user_id:
        raise already_linked_rejection(source_user_active=source_user_active)
    return select_branch(subscription=subscription,
                         destination_user_id=destination_user_id,
                         source_user_active=source_user_active)


# The steps the same-account branch skips outright.
LIVE_VERIFICATION_STEPS: tuple[int, ...] = (7, 8)


def step_06_same_account_skips_live_verification(branch: RestoreBranch,
                                                 *,
                                                 ledger: PreTransactionLedger
                                                 ) -> tuple[int, ...]:
    """6. Same-account restore is not subject to live store-state verification: it skips steps 7
    and 8 and proceeds directly to the locked mutation transaction phase."""
    # [impl->req~restore-pre-transaction-step-06-same-account-skips-live-verification~1]
    assert_locks_not_held(ledger)
    ledger.record("06_branch_gate")
    if branch is RestoreBranch.same_account:
        return LIVE_VERIFICATION_STEPS
    return ()


def step_07_adoption_entitlement_short_circuit(subscription: CurrentSubscriptionState,
                                               *,
                                               branch: RestoreBranch,
                                               ledger: PreTransactionLedger) -> bool:
    """7. Adoption only: confirm the canonical row read in step 2 is currently product-entitled.

    A row that is `expired`, `revoked` or otherwise non-entitled rejects with
    `restore_subscription_not_entitled` and performs no mutation, so an obviously non-entitled
    current state causes no provider call. Where no canonical row exists — adoption-with-creation —
    the short-circuit does not apply: entitlement is established by the live verification in step 8.
    """
    # [impl->req~restore-pre-transaction-step-07-adoption-entitlement-short-circuit~1]
    assert_locks_not_held(ledger)
    if branch is not RestoreBranch.adoption:
        return False
    ledger.record("07_entitlement_short_circuit")
    if subscription.row is None:
        return False
    status = subscription.status
    if status is None or not is_product_entitled(status):
        raise RestoreRejection(AuthEventResult.restore_subscription_not_entitled,
                               f"{status} is not product-entitled")
    return True


@dataclass(frozen=True, slots=True)
class LiveStoreVerification:
    """The pre-transaction provider verification the locked-phase recheck consumes: the store
    subscription it covered, the specific canonical row where one existed, and the server-issued
    verification timestamp."""
    provider: StoreProvider
    external_id: str
    subscription_id: UUID | None
    canonical_row_absent: bool
    verified_at: datetime
    status: SubscriptionStatus

    @property
    def key(self) -> tuple[StoreProvider, str]:
        return self.provider, self.external_id


# The live lookup's permitted input sources. Nothing the client sent, and nothing the message body
# carried, reaches the provider call.
LIVE_LOOKUP_INPUT_SOURCES: frozenset[str] = frozenset({
    "server_verified_restore_material", "resolved_subscription_state", "resolved_purchase_row",
})

# Live states that are not entitlement.
NON_ENTITLED_LIVE_STATES: frozenset[str] = frozenset({
    "missing", "unknown", "expired", "revoked", "refunded_voiding",
})


def step_08_live_store_state_verification(
        verified: VerifiedTransaction,
        subscription: CurrentSubscriptionState,
        *,
        branch: RestoreBranch,
        ledger: PreTransactionLedger,
        lookup: Callable[[StoreProvider, str], SubscriptionStatus | str | None],
        now: datetime,
        backend_held_credentials: bool = True,
        input_sources: Iterable[str] = ("server_verified_restore_material",),
) -> LiveStoreVerification | None:
    """8. Adoption only: perform the pre-transaction live store-state verification.

    The provider call uses backend-held provider credentials and derives its lookup inputs only
    from server-verified restore material and the locally resolved state from steps 2 and 4. A
    missing, unknown, expired, revoked, refunded-voiding or otherwise non-entitled live state, and
    a single provider call that fails or times out, reject with `restore_store_state_unverified`
    and perform no mutation. The outcome is recorded together with the resolved
    `(provider, external_id)`, the `core.subscriptions.id` it covered where a canonical row
    existed — the absence noted in its place where none did — and a server-issued timestamp.
    """
    # [impl->req~restore-pre-transaction-step-08-live-store-state-verification~1]
    assert_locks_not_held(ledger)
    if branch is not RestoreBranch.adoption:
        return None
    if not backend_held_credentials:
        raise RestorePhaseError("the provider call uses backend-held provider credentials")
    borrowed = sorted(set(input_sources) - LIVE_LOOKUP_INPUT_SOURCES)
    if borrowed:
        raise RestorePhaseError(f"{borrowed} is no permitted live-lookup input source")
    ledger.record("08_live_store_state_verification")
    try:
        observed = lookup(verified.provider, verified.external_id)
    except Exception:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "the live store-state verification failed or timed out") from None
    # What counts as currently entitled at the store has one implementation, in the live
    # verification module. It is imported here rather than at module scope because that module
    # reads this one's ledger and freshness recheck.
    from nativespeaker.api.auth.restore_live_verification import confirm_currently_entitled
    status = confirm_currently_entitled(observed)
    row = subscription.row
    return LiveStoreVerification(provider=verified.provider,
                                 external_id=verified.external_id,
                                 subscription_id=row.subscription_id if row is not None else None,
                                 canonical_row_absent=row is None,
                                 verified_at=now,
                                 status=status)


# --- The locked mutation transaction ------------------------------------------------------------


class LockTier(StrEnum):
    """The deterministic order the restore mutation locks are acquired in."""
    store_subscription_serialization = "store_subscription_serialization"
    canonical_subscription_row = "canonical_subscription_row"
    grant_rows = "grant_rows"
    usage_rows = "usage_rows"
    store_purchase_row = "store_purchase_row"


LOCK_ORDER: tuple[LockTier, ...] = (
    LockTier.store_subscription_serialization,
    LockTier.canonical_subscription_row,
    LockTier.grant_rows,
    LockTier.usage_rows,
    LockTier.store_purchase_row,
)

# Contention management the restore path adds beyond that order and the single retry: none.
EXTRA_CONTENTION_MANAGEMENT: frozenset[str] = frozenset()

# At most one retry of the locked mutation transaction per restore attempt.
MAX_LOCKED_RETRIES: int = 1


@dataclass(slots=True)
class LockedPhaseLedger:
    """One locked mutation transaction: the lock tiers it took, in order, the work it did, and the
    single audit row it owes."""
    tiers: list[LockTier] = field(default_factory=list)
    locks: LockLedger = field(
        default_factory=lambda: LockLedger(LockingPath.restore_mutation))
    steps: list[str] = field(default_factory=list)
    attempts: int = 0
    audit: RestoreAttemptAudit = field(default_factory=RestoreAttemptAudit)

    def record(self, step: str) -> None:
        self.steps.append(step)

    def acquire(self, tier: LockTier) -> None:
        expected = [item for item in LOCK_ORDER if item in {*self.tiers, tier}]
        if [*self.tiers, tier] != expected[:len(self.tiers) + 1]:
            raise RestorePhaseError(f"{tier} is out of the restore lock order {list(LOCK_ORDER)}")
        self.tiers.append(tier)

    @property
    def holds_locks(self) -> bool:
        return bool(self.tiers)


def assert_no_provider_calls(ledger: LockedPhaseLedger, call: str | None = None) -> None:
    """The locked mutation transaction makes no Apple or Google network call and retries no
    provider request while holding these locks."""
    # [impl->req~restore-locked-phase-no-provider-calls~1]
    if call is None:
        return
    if ledger.holds_locks:
        raise RestorePhaseError(f"{call} may not run while the restore mutation locks are held")
    ledger.locks.external_call(call)


def step_09_acquire_locks_and_retry(
        *,
        ledger: LockedPhaseLedger,
        store_subscription_key: tuple[StoreProvider, str],
        canonical_row: SubscriptionRow | None,
        grant_ids: Sequence[UUID],
        usage_grant_ids: Sequence[UUID] = (),
        purchase_row: PurchaseRow | None,
        run: Callable[[LockedPhaseLedger], Any],
        added_contention_management: Iterable[str] = ()) -> Any:
    """9. Enter the transaction that performs the mutation and writes the attempt's audit row,
    acquiring the restore mutation locks in the deterministic order before re-resolving state.

    First the store-subscription-level serialization for the resolved `(provider, external_id)` —
    which on the adoption-with-creation path is the store-subscription-level lock — together with
    the canonical row where one exists; then the grant rows in ascending grant `id` order; then
    their usage rows in that same order; then the resolved purchase row. No user-row lock tier runs
    ahead of the grant locks.

    A lock wait timeout, a deadlock, or a serialization failure raised inside this transaction is
    transient contention: the transaction rolls back — taking its audit row with it, so the attempt
    still writes exactly one row — and is re-run in full, at most once. The retry re-enters this
    locked transaction only: it repeats no pre-transaction step and makes no provider call.
    """
    # [impl->req~restore-locked-step-09-acquire-locks-and-retry~1]
    extra = sorted(set(added_contention_management) - EXTRA_CONTENTION_MANAGEMENT)
    if extra:
        raise RestorePhaseError(f"the restore path adds no {extra}")
    last: RestoreContention | None = None
    while ledger.attempts <= MAX_LOCKED_RETRIES:
        ledger.attempts += 1
        ledger.tiers.clear()
        ledger.steps.clear()
        ledger.locks = LockLedger(LockingPath.restore_mutation)
        ledger.audit = RestoreAttemptAudit()
        ledger.acquire(LockTier.store_subscription_serialization)
        ledger.record(f"serialize:{store_subscription_key[0]}:{store_subscription_key[1]}")
        if canonical_row is not None:
            ledger.acquire(LockTier.canonical_subscription_row)
        ordered = sorted(set(grant_ids))
        if ordered:
            ledger.acquire(LockTier.grant_rows)
            for grant_id in ordered:
                ledger.locks.lock_grant(grant_id)
        usage = sorted(set(usage_grant_ids) or set(ordered))
        if usage:
            ledger.acquire(LockTier.usage_rows)
            for grant_id in usage:
                ledger.locks.lock_usage(grant_id)
        if purchase_row is not None:
            ledger.acquire(LockTier.store_purchase_row)
        try:
            return run(ledger)
        except RestoreContention as contention:
            # Roll back — the attempt's audit row rolls back with it — and re-run in full.
            last = contention
            ledger.locks.commit()
    # The single retry is exhausted: the attempt fails through the existing rejected-attempt audit
    # and error path, unchanged, and stays visible through the existing database and error metrics.
    raise RestoreContention(
        f"restore contention persisted after {MAX_LOCKED_RETRIES} retry") from last


@dataclass(frozen=True, slots=True)
class LockedState:
    """Everything the locked phase reads, re-resolved from the locked rows."""
    subscription: CurrentSubscriptionState
    purchase_row: PurchaseRow | None
    grant_user_id: UUID | None
    grant_id: UUID | None
    destination_active: bool
    destination_registered: bool
    identity_linked: bool


def step_10_re_resolve_locked_state(
        *,
        ledger: LockedPhaseLedger,
        subscriptions: Sequence[SubscriptionRow],
        purchases: Sequence[PurchaseRow],
        verified: VerifiedTransaction,
        grant_user_id: UUID | None = None,
        grant_id: UUID | None = None,
        destination_active: bool = True,
        destination_registered: bool = True,
        identity_linked: bool = True,
        provider_call: str | None = None) -> LockedState:
    """10. Re-resolve the current subscription state, grant, ownership, purchase row and
    destination entitlement state from the locked rows, re-reading the canonical row for the
    `(provider, external_id)` store subscription. Only database-local checks follow."""
    # [impl->req~restore-locked-step-10-re-resolve-locked-state~1]
    assert_no_provider_calls(ledger, provider_call)
    ledger.record("10_re_resolve_locked_state")
    return LockedState(
        subscription=resolve_canonical_subscription(subscriptions, verified),
        purchase_row=resolve_purchase_row(purchases, verified),
        grant_user_id=grant_user_id,
        grant_id=grant_id,
        destination_active=destination_active,
        destination_registered=destination_registered,
        identity_linked=identity_linked)


def step_11_confirm_product_entitled(state: LockedState,
                                     *,
                                     ledger: LockedPhaseLedger,
                                     creation_status: SubscriptionStatus | None = None
                                     ) -> SubscriptionStatus:
    """11. Confirm the canonical row is currently product-entitled under locked DB state. A row
    that is `expired`, `revoked` or otherwise non-entitled rejects with
    `restore_subscription_not_entitled` and performs no mutation. On the adoption-with-creation
    path the check applies to the store-verified state the row is created at."""
    # [impl->req~restore-locked-step-11-confirm-product-entitled~1]
    ledger.record("11_confirm_product_entitled")
    assert_product_entitled(state.subscription.status, live_verified_status=creation_status)
    effective = state.subscription.status or creation_status
    if effective is None:
        raise RestorePhaseError("no locked state stands behind the entitlement check")
    return effective


def step_12_confirm_canonical_row_correspondence(
        state: LockedState,
        *,
        ledger: LockedPhaseLedger,
        pre_transaction_subscription_id: UUID | None,
        adoption_with_creation: bool) -> SubscriptionRow | None:
    """12. Confirm the resolved store subscription still has its canonical row and that the row
    corresponds to the one the pre-transaction phase used.

    A store subscription that no longer exists, or that now resolves to a different one, rejects
    with `restore_subscription_unlinked` and performs no mutation. On the adoption-with-creation
    path, a row that appeared under the store-subscription serialization since the pre-transaction
    read becomes the resolved row and is re-evaluated under this document's ownership rules;
    otherwise the creation proceeds in this transaction.
    """
    # [impl->req~restore-locked-step-12-confirm-canonical-row-correspondence~1]
    ledger.record("12_confirm_canonical_row")
    row = state.subscription.row
    if adoption_with_creation:
        return row
    if row is None or row.subscription_id != pre_transaction_subscription_id:
        raise RestoreRejection(AuthEventResult.restore_subscription_unlinked,
                               "the store subscription no longer resolves to the same row")
    return row


def step_13_confirm_purchase_row(state: LockedState,
                                 verified: VerifiedTransaction,
                                 *,
                                 ledger: LockedPhaseLedger,
                                 creating_purchase_row: bool) -> PurchaseRow | None:
    """13. Confirm the resolved purchase row is still present for the locked store subscription and
    that any carried purchase UUID still equals its recorded `identity_value`.

    A missing row rejects with `restore_purchase_uuid_unknown`; recorded attribution that no longer
    matches rejects with `restore_purchase_uuid_mismatch`. Where the row is being created in this
    transaction, a row that has appeared under the same serialization becomes the resolved row and
    is re-evaluated the same way.
    """
    # [impl->req~restore-locked-step-13-confirm-purchase-row~1]
    ledger.record("13_confirm_purchase_row")
    row = state.purchase_row
    if row is None:
        if creating_purchase_row:
            return None
        raise RestoreRejection(AuthEventResult.restore_purchase_uuid_unknown,
                               "the store purchase row is no longer present")
    assert_carried_uuid_matches_recorded(carried=verified.carried_purchase_uuid,
                                         recorded=row.identity_value)
    return row


def step_14_confirm_destination_and_binding(state: LockedState,
                                            *,
                                            ledger: LockedPhaseLedger,
                                            destination_user_id: UUID) -> UUID:
    """14. Confirm the destination user is `active`, that the current identity is still linked to
    it, and that it is still registered; then re-confirm the lifetime store-transaction binding
    from the locked row.

    An inactive destination rejects with `blocked_user`, an anonymous destination with
    `restore_destination_anonymous`, and a non-NULL `restore_bound_user_id` differing from the
    destination with `store_transaction_already_linked`. None of them performs a mutation.
    """
    # [impl->req~restore-locked-step-14-confirm-destination-and-binding~1]
    ledger.record("14_confirm_destination_and_binding")
    if not state.destination_active:
        raise RestoreRejection(AuthEventResult.blocked_user,
                               "the destination user is not active")
    if not state.identity_linked:
        raise RestoreRejection(AuthEventResult.blocked_user,
                               "the current identity is no longer linked to the destination")
    if not state.destination_registered:
        raise RestoreRejection(AuthEventResult.restore_destination_anonymous,
                               "restore requires a registered destination")
    bound = state.subscription.restore_bound_user_id
    if bound is not None and bound != destination_user_id:
        raise RestoreRejection(AuthEventResult.store_transaction_already_linked,
                               "this store transaction is already linked to another account")
    return destination_user_id


def step_15_owner_grant_agreement(state: LockedState,
                                  *,
                                  ledger: LockedPhaseLedger,
                                  source_user_checked: bool = False,
                                  mutations_performed: Iterable[str] = ()) -> UUID | None:
    """15. Confirm that the owner recorded on the canonical row agrees with the subscription-backed
    grant's `user_id` under locked state — before re-confirming the branch, before any source-user
    check, and before any restore mutation.

    A divergence rejects with `restore_subscription_grant_owner_mismatch`, performs no mutation,
    records `movement_classification = 'unclassified'` and updates no monthly cross-account
    transfer cap state.
    """
    # [impl->req~restore-locked-step-15-owner-grant-agreement~1]
    if source_user_checked:
        raise RestorePhaseError("step 15 runs before any source-user check")
    offending = sorted(set(mutations_performed) & RESTORE_MUTATIONS)
    if offending:
        raise RestorePhaseError(f"step 15 runs before any restore mutation, not after {offending}")
    ledger.record("15_owner_grant_agreement")
    owner = state.subscription.user_id
    grant_owner = state.grant_user_id
    if state.grant_id is not None or grant_owner is not None:
        # A subscription-backed grant row was locked, so both `user_id` values are read from the
        # locked rows and compared directly, NULLs included: an unclaimed canonical row whose
        # grant names a user diverges exactly as two different users do. The comparison itself
        # belongs to the shared owner-agreement invariant, so it is taken from there.
        try:
            assert_owner_agreement(grant_user_id=grant_owner, subscription_user_id=owner)
        except InvariantError:
            raise RestoreRejection(
                AuthEventResult.restore_subscription_grant_owner_mismatch,
                "the canonical row and its subscription-backed grant name different owners"
            ) from None
    return owner


# No monthly cross-account transfer cap state is updated by a divergent owner pair.
TRANSFER_CAP_UPDATES_ON_DIVERGENCE: frozenset[str] = frozenset()


def step_16_resolve_outcome_and_divergence(state: LockedState,
                                           *,
                                           ledger: LockedPhaseLedger,
                                           destination_user_id: UUID,
                                           pre_transaction_branch: RestoreBranch
                                           ) -> RestoreBranch:
    """16. Resolve the restore outcome from locked state and compare it with the pre-transaction
    determination.

    Same-account if the locked owner equals the destination, adoption if the subscription is
    unclaimed under locked state, and `store_transaction_already_linked` if it is linked to a
    different account — a conflict rejected with no mutation and never a transfer. An outcome that
    differs from the pre-transaction determination in any direction rejects with
    `restore_branch_inconsistent`: the locked phase never silently adopts the locked-state outcome.
    This runs before the adoption-only recheck in step 17, so a pre-transaction same-account
    attempt that diverges surfaces as `restore_branch_inconsistent` rather than
    `restore_store_state_unverified`.
    """
    # [impl->req~restore-locked-step-16-resolve-outcome-and-divergence~1]
    if "17_live_verification_freshness" in ledger.steps:
        raise RestorePhaseError("step 16 is evaluated before step 17")
    if TRANSFER_CAP_UPDATES_ON_DIVERGENCE:
        raise RestorePhaseError("a divergence updates no transfer cap state")
    ledger.record("16_resolve_outcome")
    owner = state.subscription.user_id
    if owner is not None and owner != destination_user_id:
        raise RestoreRejection(AuthEventResult.store_transaction_already_linked,
                               "this store transaction is already linked to another account")
    outcome = (RestoreBranch.same_account if owner == destination_user_id
               else RestoreBranch.adoption)
    if outcome is not pre_transaction_branch:
        raise RestoreRejection(
            AuthEventResult.restore_branch_inconsistent,
            f"locked state resolves {outcome}, not the pre-transaction {pre_transaction_branch}")
    return outcome


def step_17_live_verification_freshness(verification: LiveStoreVerification | None,
                                        *,
                                        ledger: LockedPhaseLedger,
                                        branch: RestoreBranch,
                                        locked_key: tuple[StoreProvider, str],
                                        locked_subscription_id: UUID | None,
                                        now: datetime,
                                        freshness_seconds: float,
                                        provider_call: str | None = None
                                        ) -> LiveStoreVerification | None:
    """17. Adoption only: confirm the step-8 verification is still fresh under the configured
    freshness bound and still corresponds to the store subscription now resolved inside the lock.

    The recorded `(provider, external_id)` must match the store subscription resolved at lock
    acquisition, and the recorded `core.subscriptions.id`, where it recorded one, must match the
    current row. Where the record noted that no canonical row existed, the `(provider,
    external_id)` match is the whole correspondence. A stale or non-corresponding record rejects
    with `restore_store_state_unverified`, and the locked phase calls no store to re-run it.
    """
    # [impl->req~restore-locked-step-17-live-verification-freshness~1]
    assert_no_provider_calls(ledger, provider_call)
    if branch is not RestoreBranch.adoption:
        return None
    ledger.record("17_live_verification_freshness")
    if verification is None:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "adoption requires a recorded live store-state verification")
    age = (now - verification.verified_at).total_seconds()
    if age < 0 or age > freshness_seconds:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "the recorded live verification is stale")
    if verification.key != locked_key:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "the recorded verification covers a different store subscription")
    if (not verification.canonical_row_absent
            and verification.subscription_id != locked_subscription_id):
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "the recorded verification covers a different canonical row")
    return verification


@dataclass(frozen=True, slots=True)
class BranchMutation:
    """What the branch-specific mutation settled: the grant it left active, the grants it expired
    with their reason codes, and the binding it set."""
    branch: RestoreBranch
    grant_id: UUID | None
    restore_bound_user_id: UUID
    expired_grants: tuple[Mapping[str, Any], ...] = ()


def step_18_branch_mutation_and_binding(state: LockedState,
                                        *,
                                        ledger: LockedPhaseLedger,
                                        branch: RestoreBranch,
                                        destination_user_id: UUID,
                                        grant_id: UUID | None,
                                        mutations: RestoreGrantMutations,
                                        stale_grant_ids: Sequence[UUID] = (),
                                        provider_call: str | None = None) -> BranchMutation:
    """18. Apply the branch-specific preconditions and perform the branch-specific mutation using
    only the locked, re-resolved local state.

    The one-active-grant and ownership invariants are preserved by the mutation ordering, and a
    successful mutation of either branch sets `core.subscriptions.restore_bound_user_id` to the
    destination user where it is still NULL, in this same transaction. The binding is never
    changed once set.
    """
    # [impl->req~restore-locked-step-18-branch-mutation-and-binding~1]
    assert_no_provider_calls(ledger, provider_call)
    ledger.record("18_branch_mutation")
    mutations.validate()
    for stale in sorted(set(stale_grant_ids)):
        mutations.expire(stale, same_subscription=True)
    if grant_id is not None:
        mutations.activate(grant_id, stale_grant_ids=stale_grant_ids)
    bound = state.subscription.restore_bound_user_id
    if bound is not None and bound != destination_user_id:
        raise RestorePhaseError("the lifetime binding is never changed once set")
    mutations.commit()
    return BranchMutation(branch=branch, grant_id=grant_id,
                          restore_bound_user_id=bound or destination_user_id,
                          expired_grants=tuple(mutations.expiry_details()))


def step_19_write_audit_row(*,
                            ledger: LockedPhaseLedger,
                            phase: RestorePhase,
                            result: AuthEventResult,
                            branch: RestoreBranch | None,
                            transaction: object,
                            mutation_transaction: object | None = None,
                            mutations: RestoreGrantMutations | None = None,
                            context: RestoreAuditContext | None = None) -> MovementClassification:
    """19. Write one `audit.auth_events` row for every attempt.

    A successful mutation and a locked-phase rejection write the row in this same transaction; a
    pre-transaction rejection writes it in that attempt's own rejection transaction, before the
    error response is returned. Same-account attempts record `movement_classification =
    'same_account'`, adoption attempts `'adoption'`, and a store transaction linked to a different
    account, an owner-mismatch rejection, or a divergence rejection record `'unclassified'`.
    """
    # [impl->req~restore-locked-step-19-write-audit-row~1]
    if phase is RestorePhase.locked_mutation and mutation_transaction is not transaction:
        raise RestorePhaseError(
            "a locked-phase row is written in the same transaction as the mutation")
    if phase is RestorePhase.pre_transaction and mutation_transaction is not None:
        raise RestorePhaseError("a pre-transaction rejection performs no restore mutation")
    if mutations is not None and mutations.expiries:
        # Every expiry the mutation made reaches the row's mutation details with the reason code
        # it carried, so no expiry is a silent side effect of the restore.
        # [impl->req~restore-grant-mutation-ordering~1]
        context = replace(context or RestoreAuditContext(),
                          expired_grants=tuple(mutations.expiry_details()))
    attempt_phase = (AttemptPhase.success if result is AuthEventResult.succeeded
                     else AttemptPhase.business)
    ledger.audit.record(phase=attempt_phase,
                        result=result,
                        audit_transaction=transaction,
                        branch=branch,
                        mutation_transaction=mutation_transaction,
                        context=context)
    return movement_classification_for(branch=branch, result=result)
