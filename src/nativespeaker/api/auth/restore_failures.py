"""How a restore attempt fails: the shared barrier failures restore audits as its own attempts, the
restore-specific rejection set, and the client error mapping for `restore_subscription`.

Three separate questions, kept apart on purpose. Which failures exist and what each one audits as —
the internal `core.auth_event_result` that stays server-side. Where each rejection's single
`audit.auth_events` row goes, which is Restore Operation Logic's placement rule read from
`restore_operation`. And which opaque client-visible class the client sees, which is deliberately
coarser than the internal taxonomy so restore failures do not over-expose it.

Backend restore admission control sits ahead of all of it: a request stopped there never becomes a
restore attempt at all.
"""

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum

from nativespeaker.api.auth.audit import (
    BARRIER_RESULTS,
    AttemptPhase,
    AuthEvent,
    AuthEventResult,
)
from nativespeaker.api.auth.operations import AdmissionRejection, is_admission_phase, is_on_audited_path
from nativespeaker.api.auth.restore import (
    RESTORE_METHOD,
    RESTORE_PATH,
    MovementClassification,
    RestoreAttemptAudit,
    RestoreAuditContext,
    RestoreBranch,
    RestoreContractError,
    movement_classification_for,
    registration_remediation_routes,
)
from nativespeaker.api.auth.restore_operation import RestorePhase, audit_placement
from nativespeaker.api.auth.schema_invariants import assert_no_never_written_column
from nativespeaker.api.auth.taxonomy import (
    ClientErrorClass,
    ClientRejection,
    Remediation,
    client_response,
    register_endpoint_class,
    surface,
)
from nativespeaker.api.exceptions import ErrorCode


class RestoreFailureError(RestoreContractError):
    """A restore failure was about to be audited, placed or surfaced wrongly."""


# --- The shared barrier failures, audited here as restore attempts ------------------------------

# The four shared barrier failures, each with the internal result `00-overview-and-shared-contracts.md`
# gives it. Their behaviour is that file's; what this file states is that restore audits each one as
# a restore attempt.
# [impl->req~restore-shared-barrier-failures-audited-as-attempts~1]
SHARED_BARRIER_FAILURES: dict[str, AuthEventResult] = {
    "token_acceptance": AuthEventResult.invalid_external_jwt,
    "preauth_admission": AuthEventResult.preauth_identity_not_allowed,
    "historical_identity": AuthEventResult.historical_identity,
    "blocked_user": AuthEventResult.blocked_user,
}

if set(SHARED_BARRIER_FAILURES.values()) != BARRIER_RESULTS:
    # The four are the shared contract's, not a second list: a barrier result restore did not
    # name would otherwise reach the restore path with no attempt row behind it.
    raise RestoreFailureError("the shared barrier failures are 00's four barrier results")


def audit_shared_barrier_failure(audit: RestoreAttemptAudit,
                                 failure: str,
                                 *,
                                 audit_transaction: object,
                                 context: RestoreAuditContext | None = None) -> AuthEvent:
    """Audit one shared barrier failure as a restore attempt.

    The route match already put the request on the audited attempt path, so a barrier rejection on
    `POST /auth/restore-subscription` owes the attempt's single row exactly as a business rejection
    does. The failure's own semantics — which result it takes and which shared class it surfaces —
    stay the shared contract's.
    """
    # [impl->req~restore-shared-barrier-failures-audited-as-attempts~1]
    result = SHARED_BARRIER_FAILURES.get(failure)
    if result is None:
        raise RestoreFailureError(f"{failure} is no shared barrier failure")
    if not is_on_audited_path(RESTORE_METHOD, RESTORE_PATH):
        raise RestoreFailureError("the route match puts restore on the audited attempt path")
    return audit.record(phase=AttemptPhase.barrier,
                        result=result,
                        audit_transaction=audit_transaction,
                        branch=None,
                        context=context)


# --- The restore-specific rejection set ----------------------------------------------------------


class RestoreRejectionCondition(StrEnum):
    """Every restore-specific rejection this document names, at minimum."""
    invalid_restore_proof = "invalid_restore_proof"
    signed_transaction_verification_failed = "signed_transaction_verification_failed"
    web_or_non_native_call = "web_or_non_native_call"
    store_transaction_already_linked = "store_transaction_already_linked"
    anonymous_destination = "anonymous_destination"
    source_account_inactive = "source_account_inactive"
    current_state_not_entitled = "current_state_not_entitled"
    locked_canonical_row_lost = "locked_canonical_row_lost"
    locked_purchase_row_lost = "locked_purchase_row_lost"
    carried_purchase_uuid_mismatch = "carried_purchase_uuid_mismatch"
    locked_owner_disagreement = "locked_owner_disagreement"
    locked_branch_divergence = "locked_branch_divergence"
    live_restore_resolution_failure = "live_restore_resolution_failure"
    destination_already_entitled = "destination_already_entitled"
    store_state_unverified = "store_state_unverified"


# The internal result each condition audits as. The web/non-native surface gate is the one entry
# with no internal result of its own: it is a routing rejection taken before the audited restore
# taxonomy applies, and it surfaces as the shared `operation_not_allowed`.
# [impl->req~restore-specific-rejection-set~1]
RESTORE_SPECIFIC_REJECTIONS: dict[RestoreRejectionCondition, AuthEventResult | None] = {
    RestoreRejectionCondition.invalid_restore_proof: AuthEventResult.invalid_restore_proof,
    RestoreRejectionCondition.signed_transaction_verification_failed:
        AuthEventResult.invalid_restore_proof,
    RestoreRejectionCondition.web_or_non_native_call: None,
    RestoreRejectionCondition.store_transaction_already_linked:
        AuthEventResult.store_transaction_already_linked,
    RestoreRejectionCondition.anonymous_destination: AuthEventResult.restore_destination_anonymous,
    RestoreRejectionCondition.source_account_inactive: AuthEventResult.restore_source_user_inactive,
    RestoreRejectionCondition.current_state_not_entitled:
        AuthEventResult.restore_subscription_not_entitled,
    RestoreRejectionCondition.locked_canonical_row_lost:
        AuthEventResult.restore_subscription_unlinked,
    RestoreRejectionCondition.locked_purchase_row_lost:
        AuthEventResult.restore_purchase_uuid_unknown,
    RestoreRejectionCondition.carried_purchase_uuid_mismatch:
        AuthEventResult.restore_purchase_uuid_mismatch,
    RestoreRejectionCondition.locked_owner_disagreement:
        AuthEventResult.restore_subscription_grant_owner_mismatch,
    RestoreRejectionCondition.locked_branch_divergence: AuthEventResult.restore_branch_inconsistent,
    RestoreRejectionCondition.live_restore_resolution_failure:
        AuthEventResult.restore_store_state_unverified,
    RestoreRejectionCondition.destination_already_entitled:
        AuthEventResult.restore_destination_already_entitled,
    RestoreRejectionCondition.store_state_unverified:
        AuthEventResult.restore_store_state_unverified,
}

# The conditions each branch adds to the common set: adoption rejects on an already-entitled
# destination and on unverified store state; the same-account branch also rejects with
# `restore_destination_already_entitled` when a different active grant stands.
# [impl->req~restore-specific-rejection-set~1]
BRANCH_ADDITIONAL_REJECTIONS: dict[RestoreBranch, tuple[RestoreRejectionCondition, ...]] = {
    RestoreBranch.adoption: (RestoreRejectionCondition.destination_already_entitled,
                             RestoreRejectionCondition.store_state_unverified),
    RestoreBranch.same_account: (RestoreRejectionCondition.destination_already_entitled,),
}

# The two locked-phase rejections that record `unclassified` movement in `audit.auth_events.details`.
# [impl->req~restore-specific-rejection-set~1]
UNCLASSIFIED_CONDITIONS: frozenset[RestoreRejectionCondition] = frozenset({
    RestoreRejectionCondition.locked_owner_disagreement,
    RestoreRejectionCondition.locked_branch_divergence,
})

def rejection_result(condition: RestoreRejectionCondition,
                     *,
                     branch: RestoreBranch | None = None) -> AuthEventResult | None:
    """The internal result one restore-specific rejection audits as, refusing a branch-specific
    condition raised on the branch that does not have it."""
    # [impl->req~restore-specific-rejection-set~1]
    if condition not in RESTORE_SPECIFIC_REJECTIONS:
        raise RestoreFailureError(f"{condition} is no restore-specific rejection")
    branch_only = {name for names in BRANCH_ADDITIONAL_REJECTIONS.values() for name in names}
    if condition in branch_only:
        if branch is None:
            raise RestoreFailureError(f"{condition} is a branch-specific rejection")
        if condition not in BRANCH_ADDITIONAL_REJECTIONS[branch]:
            raise RestoreFailureError(f"the {branch} branch does not reject on {condition}")
    return RESTORE_SPECIFIC_REJECTIONS[condition]


def rejection_classification(condition: RestoreRejectionCondition,
                             *,
                             branch: RestoreBranch | None = None,
                             cap_columns_written: Iterable[str] = ()) -> MovementClassification:
    """What one rejection records as its movement classification.

    The locked-phase owner disagreement and the locked-phase outcome divergence record
    `unclassified`, and the owner disagreement never updates the monthly cross-account transfer cap
    state — that column is never written by any path.
    """
    # [impl->req~restore-specific-rejection-set~1]
    result = rejection_result(condition, branch=branch)
    if result is None:
        raise RestoreFailureError(f"{condition} is a routing rejection, not an audited outcome")
    # The monthly cross-account transfer cap state is never updated. The column is
    # retained-but-never-written schema, so the guard is the schema module's.
    # [impl->req~restore-specific-rejection-set~1]
    assert_no_never_written_column("core.subscriptions", cap_columns_written)
    classification = movement_classification_for(branch=branch, result=result)
    if condition in UNCLASSIFIED_CONDITIONS and classification is not MovementClassification.unclassified:
        raise RestoreFailureError(f"{condition} is classified as unclassified")
    return classification


def reject(audit: RestoreAttemptAudit,
           condition: RestoreRejectionCondition,
           *,
           phase: RestorePhase,
           audit_transaction: object,
           branch: RestoreBranch | None = None,
           mutation_transaction: object | None = None,
           mutations_performed: Iterable[str] = (),
           context: RestoreAuditContext | None = None) -> AuthEvent:
    """Write the single `audit.auth_events` row one restore-specific rejection owes, in the place
    Restore Operation Logic puts it: a pre-transaction rejection writes its own rejection
    transaction, and a locked-phase rejection writes inside the locked mutation transaction."""
    # [impl->req~restore-rejection-single-audit-row~1]
    result = rejection_result(condition, branch=branch)
    if result is None:
        raise RestoreFailureError(
            f"{condition} is rejected before the audited restore taxonomy applies")
    placement = audit_placement(phase=phase, result=result,
                                mutation_performed=mutations_performed)
    event = audit.record(phase=placement.attempt_phase,
                         result=result,
                         audit_transaction=audit_transaction,
                         branch=branch,
                         mutation_transaction=mutation_transaction if placement.beside_mutation
                         else None,
                         context=context)
    if len(audit.rows) != 1:
        raise RestoreFailureError("a restore rejection writes exactly one audit row")
    return event


def assert_admission_control_ahead(rejection: AdmissionRejection,
                                   audit: RestoreAttemptAudit,
                                   *,
                                   budget: str | None = None) -> bool:
    """Backend restore admission control sits ahead of every failure above.

    A request it stops follows the admission-control carve-out in
    `00-overview-and-shared-contracts.md` and the shared behaviour in
    `08-rate-limits-and-admission-control.md`, so it writes no restore audit row and never becomes
    one of the rejections this file classifies. Provider-call-budget rejections are reported the
    same way, with their own operational counter.
    """
    # [impl->req~restore-admission-control-ahead-of-failures~1]
    if not is_admission_phase(rejection, budget=budget):
        raise RestoreFailureError(f"{rejection} is not an admission-control rejection")
    if audit.rows:
        raise RestoreFailureError(
            "a request stopped by restore admission control writes no restore audit row")
    return True


# --- Client error mapping for `restore_subscription` --------------------------------------------

# The five restore-specific classes, declared through the taxonomy's endpoint extension point so
# there is one registry, not two. Each carries its own normative remediation.
# [impl->req~restore-client-error-mapping-classes~1]
RESTORE_PROOF_REJECTED: ErrorCode = "restore_proof_rejected"
RESTORE_NOT_FOUND: ErrorCode = "restore_not_found"
RESTORE_TRANSFER_REJECTED: ErrorCode = "restore_transfer_rejected"
RESTORE_ALREADY_ENTITLED: ErrorCode = "restore_already_entitled"
RESTORE_TEMPORARILY_UNAVAILABLE: ErrorCode = "restore_temporarily_unavailable"

# The anonymous destination keeps its own operation-specific rejection, defined under Registered
# Destination and outside the restore-specific table below.
# [impl->req~restore-client-error-mapping-classes~1]
RESTORE_DESTINATION_ANONYMOUS: ErrorCode = "restore_destination_anonymous"

RESTORE_CLASS_REMEDIATIONS: dict[ErrorCode, Remediation] = {
    # Re-prepare the restore proof from the device's current store state — a fresh signed StoreKit
    # transaction or Google Play purchase token — and retry; on repeated failure, stop and contact
    # support.
    # [impl->req~restore-class-proof-rejected~1]
    RESTORE_PROOF_REJECTED: Remediation(
        action="re_prepare_restore_proof_from_current_store_state_and_retry", http_status=403,
        fresh_proof=True, retry_same_request=False),
    # Terminal: no active subscription was found and this purchase cannot be restored. The client
    # is not told to rebuild the request from the device's current store purchase and retry.
    # [impl->req~restore-class-not-found~1]
    RESTORE_NOT_FOUND: Remediation(
        action="stop_and_report_no_restorable_subscription", http_status=404, terminal=True),
    # Terminal: the transfer is not allowed, and the response exposes no source-account state.
    # [impl->req~restore-class-transfer-rejected~1]
    RESTORE_TRANSFER_REJECTED: Remediation(
        action="stop_transfer_not_allowed", http_status=409, terminal=True),
    # Terminal but benign: the account already holds an entitlement, so there is nothing to
    # restore. The client must not retry; it refreshes the destination's entitlement state and
    # returns to the subscribed experience.
    # [impl->req~restore-class-already-entitled~1]
    RESTORE_ALREADY_ENTITLED: Remediation(
        action="refresh_entitlement_and_return_to_subscribed_experience", http_status=409,
        terminal=True, retry_same_request=False),
    # Only a later user-initiated retry is permitted, with support offered if the class persists.
    # [impl->req~restore-class-temporarily-unavailable~1]
    RESTORE_TEMPORARILY_UNAVAILABLE: Remediation(
        action="user_initiated_retry_later_then_support_if_persistent", http_status=503,
        transient=True),
    # Complete registration, then retry restore. Which routes complete it is owned by Registered
    # Destination — `registration_remediation_routes()` — and there are two of them, so this entry
    # names none of its own rather than forking a second, shorter list.
    # [impl->req~restore-client-error-mapping-classes~1]
    RESTORE_DESTINATION_ANONYMOUS: Remediation(
        action="complete_registration_then_retry_restore", http_status=403),
}

for _class, _remediation in RESTORE_CLASS_REMEDIATIONS.items():
    register_endpoint_class(_class, _remediation, _remediation.http_status)


def anonymous_destination_next_routes() -> tuple[tuple[str, str], ...]:
    """Where a client sent the anonymous-destination rejection goes next. The rejection keeps its
    distinct operation-specific class, and its remediation routes are read from the owner under
    Registered Destination — the in-place `POST /auth/upgrade-anonymous` flip, or registered
    `POST /auth/create-user` where no existing anonymous user is being upgraded."""
    # [impl->req~restore-client-error-mapping-classes~1]
    return registration_remediation_routes()


# The restore-specific table: every restore internal result past the shared gates maps to exactly
# one of the five classes and to nothing else. No shared class appears here.
# [impl->req~restore-client-error-mapping-classes~1]
RESTORE_RESULT_CLASSES: dict[AuthEventResult, ErrorCode] = {
    # The presented restore evidence did not verify.
    # [impl->req~restore-class-proof-rejected~1]
    AuthEventResult.invalid_restore_proof: RESTORE_PROOF_REJECTED,
    AuthEventResult.restore_store_state_unverified: RESTORE_PROOF_REJECTED,
    # No restorable subscription stands behind the verified material.
    # [impl->req~restore-class-not-found~1]
    AuthEventResult.restore_subscription_unlinked: RESTORE_NOT_FOUND,
    AuthEventResult.restore_purchase_uuid_unknown: RESTORE_NOT_FOUND,
    AuthEventResult.restore_purchase_uuid_mismatch: RESTORE_NOT_FOUND,
    AuthEventResult.restore_subscription_not_entitled: RESTORE_NOT_FOUND,
    # The restore would move or attach entitlement the transfer rules do not allow.
    # [impl->req~restore-class-transfer-rejected~1]
    AuthEventResult.store_transaction_already_linked: RESTORE_TRANSFER_REJECTED,
    AuthEventResult.restore_source_user_inactive: RESTORE_TRANSFER_REJECTED,
    AuthEventResult.restore_subscription_grant_owner_mismatch: RESTORE_TRANSFER_REJECTED,
    # The dedicated class for an already-entitled destination.
    # [impl->req~restore-class-already-entitled~1]
    AuthEventResult.restore_destination_already_entitled: RESTORE_ALREADY_ENTITLED,
    # The invariant failure that is never exposed to the client.
    # [impl->req~restore-class-temporarily-unavailable~1]
    AuthEventResult.restore_branch_inconsistent: RESTORE_TEMPORARILY_UNAVAILABLE,
}

# The shared classes restore uses exactly as `00-overview-and-shared-contracts.md` defines them.
# `challenge_required` is not among them, because restore carries no challenge.
# [impl->req~restore-client-error-mapping-classes~1]
RESTORE_SHARED_CLASSES: tuple[ClientErrorClass, ...] = (
    ClientErrorClass.auth_required,
    ClientErrorClass.preauth_identity_not_allowed,
    ClientErrorClass.account_unavailable,
)
RESTORE_CLASS_NEVER_USED: frozenset[ClientErrorClass] = frozenset({
    ClientErrorClass.challenge_required})

# The surface gate rejects with the shared `operation_not_allowed` class before the mapping applies.
# [impl->req~restore-client-error-mapping-classes~1]
SURFACE_GATE_CLASS: ClientErrorClass = ClientErrorClass.operation_not_allowed

# The internal results whose class is the shared barrier's, taken from the shared mapping.
SHARED_BARRIER_RESULTS: frozenset[AuthEventResult] = frozenset(SHARED_BARRIER_FAILURES.values())

# The result whose operation-specific class is not one of the five.
OPERATION_SPECIFIC_RESULTS: dict[AuthEventResult, ErrorCode] = {
    AuthEventResult.restore_destination_anonymous: RESTORE_DESTINATION_ANONYMOUS,
}

# The fail-closed class for any restore internal result the table does not name: logged and
# alerted, never serialized to the client directly, and never left to implementation choice.
# [impl->req~restore-class-temporarily-unavailable~1]
FAIL_CLOSED_CLASS: ErrorCode = RESTORE_TEMPORARILY_UNAVAILABLE


def restore_client_class(result: AuthEventResult) -> ErrorCode:
    """The client-visible class one internal result surfaces as on `POST /auth/restore-subscription`.

    Shared barrier, identity and account results keep the shared classes. The anonymous destination
    keeps its own operation-specific rejection. Every other restore result maps to exactly one of
    the five restore-specific classes, and anything unnamed fails closed to
    `restore_temporarily_unavailable` rather than reaching the client as an internal value.
    """
    # [impl->req~restore-client-error-mapping-classes~1]
    # [impl->req~restore-class-temporarily-unavailable~1]
    if result in SHARED_BARRIER_RESULTS:
        client_class, _ = surface(result)
        return client_class
    if result in OPERATION_SPECIFIC_RESULTS:
        return OPERATION_SPECIFIC_RESULTS[result]
    return RESTORE_RESULT_CLASSES.get(result, FAIL_CLOSED_CLASS)


def restore_rejection_response(result: AuthEventResult) -> ClientRejection:
    """The response one internal result produces: the shared response shape naming the class, and
    never the internal or audit value itself."""
    # [impl->req~restore-client-error-mapping-classes~1]
    client_class = restore_client_class(result)
    response = client_response(client_class)
    disclosed = f"{sorted(response.body.items())}"
    if str(result) in disclosed and str(result) != client_class:
        raise RestoreFailureError(f"{result} must not reach the client as an internal value")
    return response


def assert_mapping_exhaustive(results: Sequence[AuthEventResult] | None = None) -> None:
    """Every restore-specific internal result past the shared gates maps to exactly one of the five
    restore-specific classes and to nothing else: no shared class appears in the table, and the
    grouping is coarser than one class per internal result."""
    # [impl->req~restore-client-error-mapping-classes~1]
    shared = {str(name) for name in ClientErrorClass}
    offending = sorted({name for name in RESTORE_RESULT_CLASSES.values() if name in shared})
    if offending:
        raise RestoreFailureError(f"{offending} is a shared class and belongs to no restore entry")
    classes = set(RESTORE_RESULT_CLASSES.values())
    if classes != {RESTORE_PROOF_REJECTED, RESTORE_NOT_FOUND, RESTORE_TRANSFER_REJECTED,
                   RESTORE_ALREADY_ENTITLED, RESTORE_TEMPORARILY_UNAVAILABLE}:
        raise RestoreFailureError("the table maps onto the five restore-specific classes")
    if len(classes) >= len(RESTORE_RESULT_CLASSES):
        raise RestoreFailureError("the grouping is coarser than one class per internal result")
    for result in results or ():
        if restore_client_class(result) not in {*classes, *shared, RESTORE_DESTINATION_ANONYMOUS}:
            raise RestoreFailureError(f"{result} surfaces outside the declared classes")


def assert_class_membership(client_class: str,
                            expected: Iterable[AuthEventResult]) -> tuple[AuthEventResult, ...]:
    """The exact internal results one restore-specific class covers — no more and no fewer."""
    # [impl->req~restore-class-proof-rejected~1]
    # [impl->req~restore-class-not-found~1]
    # [impl->req~restore-class-transfer-rejected~1]
    # [impl->req~restore-class-already-entitled~1]
    # [impl->req~restore-class-temporarily-unavailable~1]
    mapped = {result for result, name in RESTORE_RESULT_CLASSES.items() if name == client_class}
    wanted = set(expected)
    if mapped != wanted:
        raise RestoreFailureError(
            f"{client_class} covers {sorted(str(one) for one in wanted)}")
    return tuple(sorted(mapped, key=lambda one: str(one)))


def assert_no_source_account_state(body: Mapping[str, object]) -> None:
    """A `restore_transfer_rejected` response exposes no source-account state."""
    # [impl->req~restore-class-transfer-rejected~1]
    forbidden = sorted(key for key in body
                       if key in {"source_user_id", "source_account", "owner", "owner_user_id",
                                  "linked_user_id", "purchase_user_id"})
    if forbidden:
        raise RestoreFailureError(f"a transfer rejection exposes no {forbidden}")
