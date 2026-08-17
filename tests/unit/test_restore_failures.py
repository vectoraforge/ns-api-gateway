"""Restore's failure handling: the shared barrier failures it audits as its own attempts, the
restore-specific rejection set, and the client error mapping for `restore_subscription`."""

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.operations import AdmissionRejection
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreAttemptAudit,
    RestoreBranch,
)
from nativespeaker.api.auth.restore_failures import (
    BRANCH_ADDITIONAL_REJECTIONS,
    RESTORE_ALREADY_ENTITLED,
    RESTORE_CLASS_REMEDIATIONS,
    RESTORE_NOT_FOUND,
    RESTORE_PROOF_REJECTED,
    RESTORE_RESULT_CLASSES,
    RESTORE_SHARED_CLASSES,
    RESTORE_TEMPORARILY_UNAVAILABLE,
    RESTORE_TRANSFER_REJECTED,
    SHARED_BARRIER_FAILURES,
    SURFACE_GATE_CLASS,
    RestoreFailureError,
    RestoreRejectionCondition,
    assert_admission_control_ahead,
    assert_class_membership,
    assert_mapping_exhaustive,
    assert_no_source_account_state,
    audit_shared_barrier_failure,
    reject,
    rejection_classification,
    rejection_result,
    restore_client_class,
    restore_rejection_response,
)
from nativespeaker.api.auth.restore_operation import RestorePhase
from nativespeaker.api.auth.taxonomy import ClientErrorClass, remediation_for

TRANSACTION = object()


# --- Shared barrier failures ---------------------------------------------------------------------


# [utest->req~restore-shared-barrier-failures-audited-as-attempts~1]
def test_each_shared_barrier_failure_is_audited_as_a_restore_attempt():
    assert set(SHARED_BARRIER_FAILURES) == {"token_acceptance", "preauth_admission",
                                            "historical_identity", "blocked_user"}
    for failure, result in SHARED_BARRIER_FAILURES.items():
        audit = RestoreAttemptAudit()
        event = audit_shared_barrier_failure(audit, failure, audit_transaction=TRANSACTION)
        assert event.result is result
        assert len(audit.rows) == 1
        # The barrier rejection stays a restore attempt: one row, unclassified movement.
        assert audit.rows[0].details["mutation"]["movement_classification"] == str(
            MovementClassification.unclassified)
        assert audit.rows[0].operation is not None


# [utest->req~restore-shared-barrier-failures-audited-as-attempts~1]
def test_a_barrier_failure_restore_does_not_own_is_refused():
    with pytest.raises(RestoreFailureError, match="no shared barrier failure"):
        audit_shared_barrier_failure(RestoreAttemptAudit(), "challenge_expired",
                                     audit_transaction=TRANSACTION)


# --- The restore-specific rejection set ------------------------------------------------------------


# [utest->req~restore-specific-rejection-set~1]
def test_every_named_restore_rejection_audits_as_its_own_internal_result():
    expected = {
        RestoreRejectionCondition.invalid_restore_proof: AuthEventResult.invalid_restore_proof,
        RestoreRejectionCondition.signed_transaction_verification_failed:
            AuthEventResult.invalid_restore_proof,
        RestoreRejectionCondition.store_transaction_already_linked:
            AuthEventResult.store_transaction_already_linked,
        RestoreRejectionCondition.anonymous_destination:
            AuthEventResult.restore_destination_anonymous,
        RestoreRejectionCondition.source_account_inactive:
            AuthEventResult.restore_source_user_inactive,
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
        RestoreRejectionCondition.locked_branch_divergence:
            AuthEventResult.restore_branch_inconsistent,
        RestoreRejectionCondition.live_restore_resolution_failure:
            AuthEventResult.restore_store_state_unverified,
    }
    for condition, result in expected.items():
        assert rejection_result(condition) is result


# [utest->req~restore-specific-rejection-set~1]
def test_the_web_and_non_native_call_is_a_routing_rejection_with_no_internal_result():
    assert rejection_result(RestoreRejectionCondition.web_or_non_native_call) is None
    assert SURFACE_GATE_CLASS is ClientErrorClass.operation_not_allowed


# [utest->req~restore-specific-rejection-set~1]
def test_the_branch_specific_rejections_belong_to_their_branch():
    adoption = BRANCH_ADDITIONAL_REJECTIONS[RestoreBranch.adoption]
    assert set(adoption) == {RestoreRejectionCondition.destination_already_entitled,
                             RestoreRejectionCondition.store_state_unverified}
    assert BRANCH_ADDITIONAL_REJECTIONS[RestoreBranch.same_account] == (
        RestoreRejectionCondition.destination_already_entitled,)
    assert rejection_result(RestoreRejectionCondition.store_state_unverified,
                            branch=RestoreBranch.adoption) is (
        AuthEventResult.restore_store_state_unverified)
    # The same-account branch does not reject on unverified store state: it makes no provider call.
    with pytest.raises(RestoreFailureError, match="does not reject"):
        rejection_result(RestoreRejectionCondition.store_state_unverified,
                         branch=RestoreBranch.same_account)
    with pytest.raises(RestoreFailureError, match="branch-specific"):
        rejection_result(RestoreRejectionCondition.destination_already_entitled)


# [utest->req~restore-specific-rejection-set~1]
def test_the_two_locked_phase_disagreements_are_classified_unclassified():
    for condition in (RestoreRejectionCondition.locked_owner_disagreement,
                      RestoreRejectionCondition.locked_branch_divergence):
        assert rejection_classification(condition,
                                        branch=RestoreBranch.same_account) is (
            MovementClassification.unclassified)


# [utest->req~restore-specific-rejection-set~1]
def test_an_owner_disagreement_never_updates_the_transfer_cap_state():
    with pytest.raises(Exception, match="last_cross_account_transfer_month"):
        rejection_classification(RestoreRejectionCondition.locked_owner_disagreement,
                                 branch=RestoreBranch.same_account,
                                 cap_columns_written=("last_cross_account_transfer_month",))


# [utest->req~restore-rejection-single-audit-row~1]
def test_a_pre_transaction_rejection_writes_one_row_in_its_own_transaction():
    audit = RestoreAttemptAudit()
    event = reject(audit, RestoreRejectionCondition.invalid_restore_proof,
                   phase=RestorePhase.pre_transaction, audit_transaction=TRANSACTION)
    assert event.result is AuthEventResult.invalid_restore_proof
    assert len(audit.rows) == 1
    # A second row for the same attempt is refused by the attempt's own audit object.
    with pytest.raises(Exception, match="one restore attempt writes one audit row"):
        reject(audit, RestoreRejectionCondition.current_state_not_entitled,
               phase=RestorePhase.pre_transaction, audit_transaction=TRANSACTION)


# [utest->req~restore-rejection-single-audit-row~1]
def test_a_locked_phase_rejection_writes_its_row_beside_the_mutation_transaction():
    audit = RestoreAttemptAudit()
    event = reject(audit, RestoreRejectionCondition.locked_owner_disagreement,
                   phase=RestorePhase.locked_mutation,
                   audit_transaction=TRANSACTION, mutation_transaction=TRANSACTION,
                   branch=RestoreBranch.same_account)
    assert event.result is AuthEventResult.restore_subscription_grant_owner_mismatch
    assert len(audit.rows) == 1


# [utest->req~restore-rejection-single-audit-row~1]
def test_a_pre_transaction_rejection_that_mutated_is_refused():
    with pytest.raises(Exception, match="performs no restore mutation"):
        reject(RestoreAttemptAudit(), RestoreRejectionCondition.invalid_restore_proof,
               phase=RestorePhase.pre_transaction, audit_transaction=TRANSACTION,
               mutations_performed=("access_grants_write",))


# [utest->req~restore-admission-control-ahead-of-failures~1]
def test_admission_control_sits_ahead_of_every_restore_failure():
    audit = RestoreAttemptAudit()
    assert assert_admission_control_ahead(AdmissionRejection.backend_rate_limited, audit)
    assert assert_admission_control_ahead(AdmissionRejection.provider_budget_exhausted, audit,
                                          budget="provider_apple_store_live_verification_global")


# [utest->req~restore-admission-control-ahead-of-failures~1]
def test_a_request_stopped_by_admission_control_writes_no_restore_audit_row():
    audit = RestoreAttemptAudit()
    reject(audit, RestoreRejectionCondition.invalid_restore_proof,
           phase=RestorePhase.pre_transaction, audit_transaction=TRANSACTION)
    with pytest.raises(RestoreFailureError, match="no restore audit row"):
        assert_admission_control_ahead(AdmissionRejection.backend_rate_limited, audit)


# [utest->req~restore-admission-control-ahead-of-failures~1]
def test_a_free_grant_device_bit_budget_is_no_restore_admission_rejection():
    with pytest.raises(RestoreFailureError, match="not an admission-control rejection"):
        assert_admission_control_ahead(AdmissionRejection.provider_budget_exhausted,
                                       RestoreAttemptAudit(),
                                       budget="adapter_devicecheck_read")


# --- The client error mapping -------------------------------------------------------------------------


# [utest->req~restore-client-error-mapping-classes~1]
def test_every_restore_internal_result_maps_to_exactly_one_restore_class():
    assert_mapping_exhaustive(list(AuthEventResult))
    # No shared class appears in the restore-specific table.
    shared = {str(one) for one in ClientErrorClass}
    assert not shared & set(RESTORE_RESULT_CLASSES.values())
    # The grouping is coarser than one class per internal result.
    assert len(set(RESTORE_RESULT_CLASSES.values())) < len(RESTORE_RESULT_CLASSES)


# [utest->req~restore-client-error-mapping-classes~1]
def test_the_shared_barrier_classes_are_the_shared_ones_and_challenge_required_is_not_among_them():
    assert restore_client_class(AuthEventResult.invalid_external_jwt) == str(
        ClientErrorClass.auth_required)
    assert restore_client_class(AuthEventResult.preauth_identity_not_allowed) == str(
        ClientErrorClass.preauth_identity_not_allowed)
    assert restore_client_class(AuthEventResult.historical_identity) == str(
        ClientErrorClass.account_unavailable)
    assert restore_client_class(AuthEventResult.blocked_user) == str(
        ClientErrorClass.account_unavailable)
    assert ClientErrorClass.challenge_required not in RESTORE_SHARED_CLASSES


# [utest->req~restore-client-error-mapping-classes~1]
def test_the_anonymous_destination_keeps_its_own_operation_specific_rejection():
    assert restore_client_class(AuthEventResult.restore_destination_anonymous) == (
        "restore_destination_anonymous")
    assert restore_client_class(
        AuthEventResult.restore_destination_anonymous) not in RESTORE_RESULT_CLASSES.values()


# [utest->req~restore-client-error-mapping-classes~1]
def test_no_internal_result_reaches_the_client_as_a_raw_value():
    for result in RESTORE_RESULT_CLASSES:
        response = restore_rejection_response(result)
        assert response.body["code"] == RESTORE_RESULT_CLASSES[result]
        assert str(result) != response.body["code"]


# [utest->req~restore-class-proof-rejected~1]
def test_restore_proof_rejected_covers_the_two_evidence_failures_only():
    assert assert_class_membership(RESTORE_PROOF_REJECTED,
                                   (AuthEventResult.invalid_restore_proof,
                                    AuthEventResult.restore_store_state_unverified))
    remediation = RESTORE_CLASS_REMEDIATIONS[RESTORE_PROOF_REJECTED]
    assert remediation.fresh_proof and not remediation.terminal
    with pytest.raises(RestoreFailureError):
        assert_class_membership(RESTORE_PROOF_REJECTED,
                                (AuthEventResult.invalid_restore_proof,))


# [utest->req~restore-class-not-found~1]
def test_restore_not_found_covers_the_four_missing_subscription_results_and_is_terminal():
    assert assert_class_membership(RESTORE_NOT_FOUND,
                                   (AuthEventResult.restore_subscription_unlinked,
                                    AuthEventResult.restore_purchase_uuid_unknown,
                                    AuthEventResult.restore_purchase_uuid_mismatch,
                                    AuthEventResult.restore_subscription_not_entitled))
    remediation = remediation_for(RESTORE_NOT_FOUND)
    assert remediation.terminal
    # Terminal means the client is not told to rebuild the request and retry.
    assert not remediation.fresh_proof and not remediation.retry_same_request


# [utest->req~restore-class-transfer-rejected~1]
def test_restore_transfer_rejected_covers_the_three_transfer_results_and_leaks_no_source_state():
    assert assert_class_membership(RESTORE_TRANSFER_REJECTED,
                                   (AuthEventResult.store_transaction_already_linked,
                                    AuthEventResult.restore_source_user_inactive,
                                    AuthEventResult.restore_subscription_grant_owner_mismatch))
    assert remediation_for(RESTORE_TRANSFER_REJECTED).terminal
    body = restore_rejection_response(AuthEventResult.store_transaction_already_linked).body
    assert_no_source_account_state(body)
    with pytest.raises(RestoreFailureError, match="source_user_id"):
        assert_no_source_account_state({**body, "source_user_id": "someone"})


# [utest->req~restore-class-already-entitled~1]
def test_restore_already_entitled_is_its_own_class_for_one_result():
    assert assert_class_membership(RESTORE_ALREADY_ENTITLED,
                                   (AuthEventResult.restore_destination_already_entitled,))
    remediation = remediation_for(RESTORE_ALREADY_ENTITLED)
    assert remediation.terminal and not remediation.retry_same_request
    # Distinct from every other restore failure class.
    others = {RESTORE_PROOF_REJECTED, RESTORE_NOT_FOUND, RESTORE_TRANSFER_REJECTED,
              RESTORE_TEMPORARILY_UNAVAILABLE}
    assert all(remediation_for(other).action != remediation.action for other in others)


# [utest->req~restore-class-temporarily-unavailable~1]
def test_restore_temporarily_unavailable_carries_the_invariant_failure_and_the_fail_closed_default():
    assert assert_class_membership(RESTORE_TEMPORARILY_UNAVAILABLE,
                                   (AuthEventResult.restore_branch_inconsistent,))
    assert remediation_for(RESTORE_TEMPORARILY_UNAVAILABLE).transient
    # The fail-closed mapping for any restore internal result the table does not name.
    assert restore_client_class(AuthEventResult.succeeded) == RESTORE_TEMPORARILY_UNAVAILABLE
    assert restore_client_class(AuthEventResult.policy_rejected) == RESTORE_TEMPORARILY_UNAVAILABLE
    # The invariant failure never reaches the client as itself.
    body = restore_rejection_response(AuthEventResult.restore_branch_inconsistent).body
    assert body == {"code": RESTORE_TEMPORARILY_UNAVAILABLE}
