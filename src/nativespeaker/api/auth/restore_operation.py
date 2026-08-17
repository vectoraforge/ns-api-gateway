"""Restore's operation logic: what it is for, what must hold before it runs, how its work is
split across two phases, and the one ordering rule its grant writes obey.

Restore exists to attach paid subscription entitlement to the current authenticated user. The
verified store proof is authoritative for that entitlement and for nothing else, and both branches
are conclusions the backend draws from verified server state. The work is split in two: a
pre-transaction phase that verifies the proof, reads local state without locking it and — for the
adoption branch alone — makes the single provider call, and a locked mutation transaction that
re-resolves everything under the restore mutation locks, performs only database-local checks, and
writes the attempt's one audit row beside any mutation.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AttemptPhase, AuthEventResult
from nativespeaker.api.auth.barrier import VerifiedIdentityContext
from nativespeaker.api.auth.external_identities import ExternalIdentityRow
from nativespeaker.api.auth.invariants import DevicePlatform
from nativespeaker.api.auth.proof_restore import StoreVerifier
from nativespeaker.api.auth.restore import (
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
    assert_registered_destination,
    require_store_proof,
    restore_destination,
)
from nativespeaker.api.auth.restore_flow import (
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
    assert_carried_uuid_matches,
    assert_product_entitled,
    internal_purchase_uuid,
    resolve_canonical_subscription,
    resolve_purchase_row,
    select_branch,
    verify_signed_transaction,
)
from nativespeaker.api.models import SubscriptionStatus

# --- Purpose ---------------------------------------------------------------------------------------

# What the operation is for, stated once.
RESTORE_PURPOSE: str = "restore_paid_subscription_entitlement_to_the_current_authenticated_user"

# What a verified store proof is authoritative for, and the whole of it.
PROOF_AUTHORITATIVE_FOR: tuple[str, ...] = ("subscription_entitlement",)

# What it is never authoritative for: no app-account ownership, no chats, no external identity, no
# free or manual entitlement.
PROOF_NOT_AUTHORITATIVE_FOR: frozenset[str] = frozenset({
    "app_account_ownership", "prior_account_ownership", "chats", "external_identities",
    "sessions", "free_grants", "manual_grants", "introductory_allocations",
})


def restore_purpose(*, destination_user_id: UUID, attaches_to: UUID | None = None) -> str:
    """Restore paid subscription entitlement to the current authenticated user.

    The entitlement lands on the destination user the barrier resolved and on no other account:
    an attempt that would attach it elsewhere is a server-side bug, not an outcome.
    """
    # [impl->req~restore-purpose-restore-paid-entitlement~1]
    landing = destination_user_id if attaches_to is None else attaches_to
    if landing != destination_user_id:
        raise RestoreContractError(
            f"restore attaches entitlement to {destination_user_id}, not {landing}")
    return RESTORE_PURPOSE


def proof_authority(claimed: Iterable[str] = PROOF_AUTHORITATIVE_FOR) -> tuple[str, ...]:
    """Verified store proof is authoritative for subscription entitlement only."""
    # [impl->req~restore-purpose-proof-authoritative-for-entitlement-only~1]
    offered = set(claimed)
    overreach = sorted(offered & PROOF_NOT_AUTHORITATIVE_FOR)
    if overreach:
        raise RestoreContractError(f"verified store proof carries no authority over {overreach}")
    if offered != set(PROOF_AUTHORITATIVE_FOR):
        raise RestoreContractError(
            f"verified store proof is authoritative for {list(PROOF_AUTHORITATIVE_FOR)} alone")
    return PROOF_AUTHORITATIVE_FOR


# The two branches, and the only two. Neither is a client-selected variant.
SERVER_DETERMINED_BRANCHES: frozenset[RestoreBranch] = frozenset(RestoreBranch)


def two_server_determined_branches(*,
                                   subscription: CurrentSubscriptionState,
                                   destination_user_id: UUID,
                                   destination_registered: bool,
                                   grant_user_id: UUID | None = None,
                                   source_user_active: bool = True) -> RestoreBranch:
    """Subscription restore has two server-determined branches, and the backend selects between
    them from verified server state alone.

    The destination is the current authenticated user, who must be registered. The current owner on
    the canonical `core.subscriptions` row — which must agree with any subscription-backed
    `core.access_grants.user_id` — is compared against that destination: equal selects
    same-account, no linked account selects adoption, and a different linked account rejects with
    `store_transaction_already_linked`. Cross-account entitlement transfer is never performed.
    """
    # [impl->req~restore-purpose-two-server-determined-branches~1]
    if set(SERVER_DETERMINED_BRANCHES) != set(RestoreBranch):
        raise RestoreContractError("restore has exactly two server-determined branches")
    if not destination_registered:
        raise RestoreContractError("the destination must be registered under Registered Destination")
    return select_branch(subscription=subscription,
                         destination_user_id=destination_user_id,
                         grant_user_id=grant_user_id,
                         source_user_active=source_user_active)


# --- Common entry conditions at completion time ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RestoreEntry:
    """What the entry conditions resolved: the destination, the verified transaction, the local
    rows it resolved to, and whether this attempt is adoption-with-creation."""
    destination_user_id: UUID
    verified: VerifiedTransaction
    subscription: CurrentSubscriptionState
    purchase_row: PurchaseRow | None
    purchase_uuid: str
    adoption_with_creation: bool


def entry_destination(context: VerifiedIdentityContext,
                      *,
                      identity_rows: Sequence[ExternalIdentityRow],
                      barrier_admitted: bool = True,
                      destination_active: bool = True) -> UUID:
    """The client's Firebase ID token has been cryptographically verified by the backend under the
    shared per-request contract before any restore logic runs, and resolves to a linked identity
    for an active user — the destination user, whose account must be registered. An anonymous
    destination is audited as `restore_destination_anonymous` and rejected."""
    # [impl->req~restore-entry-verified-id-token-active-registered-user~1]
    destination = restore_destination(context, barrier_admitted=barrier_admitted)
    return assert_registered_destination(destination_user_id=destination,
                                         identity_rows=identity_rows,
                                         destination_active=destination_active)


def entry_proof_supplied(platform: DevicePlatform, body: Mapping[str, Any] | None) -> str:
    """`restore_proof` is supplied. A request that omits it never reaches proof verification."""
    # [impl->req~restore-entry-proof-supplied~1]
    fields = dict(body or {})
    artifact = fields.get("restore_proof")
    if not isinstance(artifact, str) or not artifact.strip():
        raise RestoreRejection(AuthEventResult.invalid_restore_proof,
                               "restore_proof is required")
    return require_store_proof(platform, fields)


def entry_proof_server_verified(platform: DevicePlatform,
                                body: Mapping[str, Any] | None,
                                verifier: StoreVerifier,
                                *,
                                performed_checks: Iterable[str]) -> VerifiedTransaction:
    """The restore proof is server-verified, including the embedded signed transaction."""
    # [impl->req~restore-entry-proof-server-verified~1]
    entry_proof_supplied(platform, body)
    return verify_signed_transaction(platform, body, verifier,
                                     performed_checks=performed_checks)


def entry_subscription_identity_resolves(rows: Sequence[SubscriptionRow],
                                         verified: VerifiedTransaction
                                         ) -> tuple[CurrentSubscriptionState, bool]:
    """The verified store subscription identity extracted from the signed transaction resolves
    through `core.subscriptions` to the canonical row for `(provider, external_id)` — or resolves
    to no row at all, the adoption-with-creation case, where the canonical row is created from the
    store-verified data inside the locked mutation transaction and the missing row is no
    rejection."""
    # [impl->req~restore-entry-subscription-identity-resolves~1]
    subscription = resolve_canonical_subscription(rows, verified)
    return subscription, subscription.row is None


def entry_current_state_product_entitled(subscription: CurrentSubscriptionState,
                                         *,
                                         live_verified_status: SubscriptionStatus | None = None
                                         ) -> SubscriptionStatus:
    """The current `core.subscriptions` state for that store subscription is product-entitled. On
    the adoption-with-creation path, where no canonical row exists, entitlement is established by
    the live store-state verification and the row is created at the live-verified state."""
    # [impl->req~restore-entry-current-state-product-entitled~1]
    assert_product_entitled(subscription.status, live_verified_status=live_verified_status)
    effective = subscription.status if subscription.status is not None else live_verified_status
    if effective is None:
        raise RestoreContractError("no state stands behind the entitlement check")
    return effective


def entry_purchase_row_resolved_or_created(rows: Sequence[PurchaseRow],
                                           verified: VerifiedTransaction
                                           ) -> tuple[PurchaseRow | None, str]:
    """The `core.store_purchases` row is resolved directly by `(provider, external_id)` — or
    created from the store-verified data where missing — and any purchase UUID carried in the same
    signed transaction equals that row's recorded `identity_value`."""
    # [impl->req~restore-entry-purchase-row-resolved-or-created~1]
    purchase_row = resolve_purchase_row(rows, verified)
    assert_carried_uuid_matches(verified, purchase_row)
    if purchase_row is not None:
        return purchase_row, purchase_row.identity_value
    return None, internal_purchase_uuid(verified)


def restore_entry_conditions(context: VerifiedIdentityContext,
                             *,
                             identity_rows: Sequence[ExternalIdentityRow],
                             platform: DevicePlatform,
                             body: Mapping[str, Any] | None,
                             verifier: StoreVerifier,
                             performed_checks: Iterable[str],
                             subscriptions: Sequence[SubscriptionRow] = (),
                             purchases: Sequence[PurchaseRow] = (),
                             destination_active: bool = True,
                             live_verified_status: SubscriptionStatus | None = None
                             ) -> RestoreEntry:
    """The common entry condition at completion time, as one conjunction."""
    destination = entry_destination(context, identity_rows=identity_rows,
                                    destination_active=destination_active)
    verified = entry_proof_server_verified(platform, body, verifier,
                                           performed_checks=performed_checks)
    subscription, adoption_with_creation = entry_subscription_identity_resolves(
        subscriptions, verified)
    purchase_row, purchase_uuid = entry_purchase_row_resolved_or_created(purchases, verified)
    entry_current_state_product_entitled(subscription,
                                         live_verified_status=live_verified_status)
    return RestoreEntry(destination_user_id=destination,
                        verified=verified,
                        subscription=subscription,
                        purchase_row=purchase_row,
                        purchase_uuid=purchase_uuid,
                        adoption_with_creation=adoption_with_creation)


# --- The two phases -----------------------------------------------------------------------------


class RestorePhase(StrEnum):
    """The two phases restore's common steps are split into."""
    pre_transaction = "pre_transaction"
    locked_mutation = "locked_mutation"


# What each phase may do. The provider call belongs to the pre-transaction phase and to the
# adoption branch alone; the locked phase performs only database-local checks.
PHASE_WORK: Mapping[RestorePhase, frozenset[str]] = {
    RestorePhase.pre_transaction: frozenset({
        "verify_restore_proof", "read_local_state", "live_store_state_verification",
        "provider_call", "write_rejection_audit_row",
    }),
    RestorePhase.locked_mutation: frozenset({
        "acquire_restore_mutation_locks", "re_resolve_locked_state", "database_local_check",
        "restore_mutation", "write_audit_row", "freshness_and_correspondence_recheck",
    }),
}

# Work no phase may do while holding the restore mutation locks.
LOCKED_PHASE_FORBIDDEN: frozenset[str] = frozenset({
    "provider_call", "apple_network_call", "google_network_call", "retry_provider_request",
    "live_store_state_verification",
})


def assert_phase_work(phase: RestorePhase,
                      work: Iterable[str],
                      *,
                      branch: RestoreBranch | None = None,
                      barrier_admitted: bool = True) -> tuple[str, ...]:
    """Common mutation steps are split into a pre-transaction phase and a locked mutation
    transaction phase.

    The shared barrier admits the request before the pre-transaction phase. The pre-transaction
    phase performs restore-proof verification, read-only resolutions, and — for the adoption branch
    only — the live provider call. The locked phase acquires the restore mutation locks,
    re-resolves all local state inside the lock, performs only database-local checks, and must make
    no Apple or Google network call and no provider retry while holding those locks.
    """
    # [impl->req~restore-two-phase-pre-transaction-and-locked~1]
    if not barrier_admitted:
        raise RestoreContractError("the shared barrier admits the request before phase one")
    requested = tuple(work)
    outside = sorted(set(requested) - PHASE_WORK[phase])
    if outside:
        raise RestoreContractError(f"{outside} is no {phase} work")
    if phase is RestorePhase.locked_mutation:
        forbidden = sorted(set(requested) & LOCKED_PHASE_FORBIDDEN)
        if forbidden:
            raise RestoreContractError(f"the locked phase performs no {forbidden}")
    if (phase is RestorePhase.pre_transaction
            and "provider_call" in set(requested)
            and branch is not RestoreBranch.adoption):
        raise RestoreContractError("only the adoption branch makes the live provider call")
    return requested


# --- Audit placement per phase --------------------------------------------------------------------

# Pre-transaction rejections: each writes the attempt's one row in a rejection transaction of its
# own while performing no restore mutation.
PRE_TRANSACTION_REJECTIONS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.invalid_restore_proof,
    AuthEventResult.restore_subscription_unlinked,
    AuthEventResult.restore_purchase_uuid_mismatch,
    AuthEventResult.restore_subscription_not_entitled,
    AuthEventResult.restore_store_state_unverified,
})

# What "perform no mutation" excludes in a pre-transaction rejection step: the restore mutations,
# never the audit write the audited attempt path requires.
RESTORE_MUTATIONS: frozenset[str] = frozenset({
    "subscriptions_owner_change", "subscriptions_row_creation", "access_grants_write",
    "store_purchases_write",
})

# Missing rows are no rejection: they are the adoption-with-creation path.
NOT_REJECTIONS: frozenset[str] = frozenset({
    "missing_canonical_subscription_row", "missing_store_purchase_row"})


@dataclass(frozen=True, slots=True)
class AuditPlacement:
    """Where an attempt's single `audit.auth_events` row is written."""
    phase: RestorePhase
    attempt_phase: AttemptPhase
    own_transaction: bool
    beside_mutation: bool


def audit_placement(*,
                    phase: RestorePhase,
                    result: AuthEventResult,
                    mutation_performed: Iterable[str] = ()) -> AuditPlacement:
    """Audit placement follows the audited-attempt-path rules; restore consumes no challenge.

    A pre-transaction rejection writes its row in a pre-transaction rejection transaction of its
    own while performing no restore mutation. A locked-phase outcome — a successful mutation or a
    locked-phase rejection — writes its row in the locked mutation transaction, together with any
    restore mutation.
    """
    # [impl->req~restore-audit-placement-per-phase~1]
    performed = set(mutation_performed)
    if phase is RestorePhase.pre_transaction:
        if result not in PRE_TRANSACTION_REJECTIONS:
            raise RestoreContractError(f"{result} is no pre-transaction restore rejection")
        offending = sorted(performed & RESTORE_MUTATIONS)
        if offending:
            raise RestoreContractError(
                f"a pre-transaction rejection performs no restore mutation, but did {offending}")
        return AuditPlacement(phase=phase, attempt_phase=AttemptPhase.business,
                              own_transaction=True, beside_mutation=False)
    unknown = sorted(performed - RESTORE_MUTATIONS)
    if unknown:
        raise RestoreContractError(f"{unknown} is no restore mutation")
    attempt_phase = (AttemptPhase.success if result is AuthEventResult.succeeded
                     else AttemptPhase.business)
    return AuditPlacement(phase=phase, attempt_phase=attempt_phase,
                          own_transaction=False, beside_mutation=True)


def missing_row_is_not_a_rejection(condition: str) -> bool:
    """A missing canonical subscription row and a missing purchase row are no rejection: they are
    the adoption-with-creation path."""
    # [impl->req~restore-audit-placement-per-phase~1]
    return condition in NOT_REJECTIONS


# --- Restore grant-mutation ordering ----------------------------------------------------------------

# The reason code an expiry made to clear the non-deferrable index carries, so no expiry is a
# silent side effect.
RESTORE_EXPIRY_REASON: str = "superseded_by_restore"

# The index the ordering exists for. It is plain and non-deferrable: no `DEFERRABLE` exclusion
# constraint replaces it, and no application rejection path exists for its violation.
ONE_ACTIVE_GRANT_INDEX: str = "ix_access_grants_one_active_per_user"
DEFERRABLE_REPLACEMENTS: frozenset[str] = frozenset()
INDEX_VIOLATION_REJECTION_PATHS: frozenset[str] = frozenset()

# The only rows restore may expire to make room: the same subscription's own superseded or stale
# grant rows. A different active grant is never expired — that case is the conflict rejection.
DIFFERENT_ACTIVE_GRANT_RESULT: AuthEventResult = AuthEventResult.restore_destination_already_entitled


class RestoreOrderingError(RestoreContractError):
    """A restore grant write was about to break the mutation ordering."""


@dataclass(slots=True)
class RestoreGrantMutations:
    """One restore mutation transaction's grant writes, in the order it made them.

    Product entitlement, ownership and linkage validation complete before any grant mutation; every
    superseded or stale grant row of the same subscription is expired in its own earlier statement,
    each with a reason code; and only then may a statement make the subscription-backed grant
    active. The destination may momentarily hold zero active grants — the index enforces a maximum
    of one, never a minimum.
    """
    validated: bool = False
    statements: list[str] = field(default_factory=list)
    expired: list[UUID] = field(default_factory=list)
    activated: UUID | None = None
    committed: bool = False
    rolled_back: bool = False

    def validate(self) -> None:
        """Product entitlement, ownership and linkage validation — where
        `store_transaction_already_linked` and the different-active-grant conflict are decided."""
        # [impl->req~restore-grant-mutation-ordering~1]
        if self.statements:
            raise RestoreOrderingError("validation completes before any grant mutation")
        self.validated = True

    def expire(self, grant_id: UUID, *,
               same_subscription: bool,
               destination_holds_different_active_grant: bool = False,
               reason: str = RESTORE_EXPIRY_REASON) -> None:
        """Expire a superseded or stale grant row of the same subscription, in its own statement,
        recorded with a reason code. A different active grant is never expired to make room."""
        # [impl->req~restore-grant-mutation-ordering~1]
        self._require_validated()
        if destination_holds_different_active_grant or not same_subscription:
            raise RestoreRejection(DIFFERENT_ACTIVE_GRANT_RESULT,
                                   "a different active grant is never expired to make room")
        if not reason:
            raise RestoreOrderingError("each expiry is recorded with a reason code")
        if self.activated is not None:
            raise RestoreOrderingError(
                f"{ONE_ACTIVE_GRANT_INDEX} is per-statement: expiries precede activation")
        self.statements.append(f"expire_grant:{reason}")
        self.expired.append(grant_id)

    def activate(self, grant_id: UUID, *, stale_grant_ids: Sequence[UUID] = ()) -> None:
        """Make the subscription-backed grant active. Every superseded or stale row of the same
        subscription must already have been expired in an earlier statement."""
        # [impl->req~restore-grant-mutation-ordering~1]
        self._require_validated()
        outstanding = sorted(set(stale_grant_ids) - set(self.expired))
        if outstanding:
            raise RestoreOrderingError(
                f"{outstanding} is expired before any statement activates {grant_id}")
        if DEFERRABLE_REPLACEMENTS or INDEX_VIOLATION_REJECTION_PATHS:
            raise RestoreOrderingError(
                f"{ONE_ACTIVE_GRANT_INDEX} is plain and non-deferrable, with no rejection path")
        self.statements.append("activate_subscription_grant")
        self.activated = grant_id

    def commit(self, *, ownership_writes_succeeded: bool = True) -> None:
        """The transaction commits only after all ownership and grant writes succeed; a failure
        rolls back any earlier expiry with it."""
        # [impl->req~restore-grant-mutation-ordering~1]
        if not ownership_writes_succeeded:
            self.rolled_back = True
            self.expired.clear()
            self.statements.clear()
            self.activated = None
            raise RestoreOrderingError("an earlier expiry rolls back with the failed transaction")
        self.committed = True

    def _require_validated(self) -> None:
        if not self.validated:
            raise RestoreOrderingError("validation completes before any grant mutation")


# Paths the ordering rule binds. It binds every restore path and only restore: it does not bind
# upgrade or grant issuance.
ORDERING_BINDS: frozenset[str] = frozenset({"restore_subscription"})
ORDERING_DOES_NOT_BIND: frozenset[str] = frozenset({
    "upgrade_anonymous_to_registered", "grant_issuance", "claim_anonymous_grant",
    "claim_registered_grant", "manual_issuance",
})


def ordering_binds(operation: str) -> bool:
    """One rule binds every restore path, and only restore."""
    # [impl->req~restore-grant-mutation-ordering~1]
    if ORDERING_BINDS & ORDERING_DOES_NOT_BIND:
        raise RestoreOrderingError("the ordering rule binds restore and nothing else")
    return operation in ORDERING_BINDS
