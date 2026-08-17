"""Failure handling for `claim_anonymous_grant`, and the grants half of the client error taxonomy."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import (
    ExternalIdentityRow,
    IdentityState,
    NativeClaimPlatform,
)
from nativespeaker.api.auth.free_grants import FreeGrantError, FreeGrantRejected
from nativespeaker.api.auth.grant_failures import (
    ANON_CLIENT_CLASSES,
    ANON_FAILURES,
    ANON_GRANT_CLASSES,
    ANON_REMEDIATION,
    ANON_RETRY_ADDITIONAL_ATTEMPTS,
    ANON_RETRY_TOTAL_ATTEMPTS,
    ANON_SHARED_CLASSES,
    COMPLETION_ENDPOINTS,
    DEVICE_BIT_BUDGET_RESULTS,
    EXHAUSTED_CONDITIONS,
    GRANTS_OWNED_CLASSES,
    NOT_STRUCTURAL_RESULTS,
    PENDING_STATE_MACHINES,
    SHARED_CATALOG_CLASSES,
    STEP_EXHAUSTED_CONDITION,
    TURNSTILE_AUDIT_RESULT,
    VENDOR_STATE_RECONCILERS,
    VERIFICATION_REQUIRED_CONDITIONS,
    VTU_CONDITIONS,
    VULNERABILITY_CONDITIONS,
    AnonFailureCondition,
    BurnedSlotCause,
    ClaimStepFailed,
    GrantFailureError,
    ProviderTransaction,
    RegFailureCondition,
    RetryableStep,
    StructuralBlock,
    VendorMaterialCause,
    accepted_burned_slot,
    account_already_claimed_scope,
    anonymous_emitted_classes,
    anonymous_failure_class,
    anonymous_remediation,
    anonymous_structural_scope,
    assert_activation_never_rejects_on_expiry,
    assert_grant_time_and_write_time_distinct,
    assert_no_raw_provider_account_ids,
    assert_not_vulnerable,
    assert_registered_allowance_unused,
    assert_remediations_distinct,
    assert_retries_not_bounded_by_expiry,
    burned_slot_retry_outcome,
    classify_anonymous_failure,
    completion_rejection,
    device_grant_exhausted_outcome,
    device_grant_exhausted_scope,
    exhausted_alternate_path,
    exhausted_conditions,
    firebase_provider_data_read_points,
    grants_client_class,
    operation_not_allowed_block,
    registered_split,
    retry_claim_step,
    shared_catalog_remediation,
    transient_failure_class,
    vendor_material_rejection,
    verification_required_conditions,
    verification_required_outcome,
    verification_required_scope,
    verification_temporarily_unavailable_outcome,
    verification_temporarily_unavailable_results,
    vtu_conditions,
    vtu_registered_backstop,
    whole_claim_retry,
)
from nativespeaker.api.auth.invariants import GateConsumptionKind, InvariantError, ProofUse
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_adapters import ClaimRejection, ProofAdapterError
from nativespeaker.api.auth.proof_endpoints import ClaimBranch
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.ratelimit.ordering import (
    DeviceBitCall,
    DeviceBitWrite,
    DeviceBitWriteError,
)

# --- fixtures and doubles -------------------------------------------------------------------


def identity_row(*,
                 provider: IdentityProvider = IdentityProvider.google,
                 provider_uid: str | None = "google-account-1",
                 native_claim_platform: NativeClaimPlatform | None = None,
                 identity_state: IdentityState = IdentityState.active,
                 user_id: UUID | None = None) -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=user_id or uuid7(),
                               issuer="https://securetoken.google.com/test-project",
                               subject="firebase-subject",
                               provider=provider, provider_uid=provider_uid,
                               identity_state=identity_state,
                               native_claim_platform=native_claim_platform)


CONFIRMED_WRITE = DeviceBitWrite(call=DeviceBitCall.devicecheck_write, confirmed=True)
FAILED_WRITE = DeviceBitWrite(call=DeviceBitCall.devicecheck_write, confirmed=False)


# --- the classes `claim_anonymous_grant` surfaces ---------------------------------------------


# [utest->req~grants-anon-failure-classes~1]
def test_anonymous_claim_surfaces_only_its_nine_classes():
    emitted = anonymous_emitted_classes()
    assert emitted == ANON_CLIENT_CLASSES
    assert set(ANON_GRANT_CLASSES) == {ClientErrorClass.device_grant_exhausted,
                                       ClientErrorClass.verification_required,
                                       ClientErrorClass.verification_temporarily_unavailable}
    assert set(ANON_SHARED_CLASSES) == {ClientErrorClass.auth_required,
                                        ClientErrorClass.preauth_identity_not_allowed,
                                        ClientErrorClass.account_unavailable,
                                        ClientErrorClass.challenge_required,
                                        ClientErrorClass.proof_rejected,
                                        ClientErrorClass.operation_not_allowed}
    # Every condition a claimant can hit resolves to one of them, and to exactly one.
    for condition in AnonFailureCondition:
        assert anonymous_failure_class(condition) in emitted


# [utest->req~grants-anon-failure-classes~1]
def test_a_class_the_registry_disagrees_with_is_refused(monkeypatch):
    failure = ANON_FAILURES[AnonFailureCondition.ios_anonymous_bit_set]
    monkeypatch.setitem(
        ANON_FAILURES, AnonFailureCondition.ios_anonymous_bit_set,
        type(failure)(failure.condition, failure.result,
                      ClientErrorClass.verification_temporarily_unavailable))
    with pytest.raises(GrantFailureError):
        anonymous_failure_class(AnonFailureCondition.ios_anonymous_bit_set)


# [utest->req~grants-anon-class-device-grant-exhausted~1]
@pytest.mark.parametrize("condition", EXHAUSTED_CONDITIONS)
def test_device_grant_exhausted_is_durable_and_points_at_the_registered_path(condition):
    outcome = device_grant_exhausted_outcome(condition)
    assert outcome.client_class is ClientErrorClass.device_grant_exhausted
    assert outcome.durable is True
    assert outcome.next_route == "/auth/claim-registered-grant"
    # Non-accusatory copy: it states the fact and blames nobody.
    assert outcome.copy is not None
    for word in ("abuse", "cheat", "fraud", "banned", "suspicious"):
        assert word not in outcome.copy.lower()
    # The per-device block and the web gate conflict keep distinct internal results.
    assert outcome.result in {AuthEventResult.native_claim_already_claimed,
                              AuthEventResult.anti_abuse_already_claimed}


# [utest->req~grants-anon-class-device-grant-exhausted~1]
def test_a_dependency_failure_is_not_an_already_claimed_outcome():
    with pytest.raises(GrantFailureError):
        device_grant_exhausted_outcome(AnonFailureCondition.devicecheck_read_unavailable)


# [utest->req~grants-anon-class-verification-required~1]
def test_verification_required_is_durable_with_no_guaranteed_alternate():
    outcome = verification_required_outcome(AnonFailureCondition.web_stored_binding_mismatch)
    assert outcome.client_class is ClientErrorClass.verification_required
    assert outcome.durable is True
    assert outcome.guaranteed_alternate is False
    assert outcome.result is AuthEventResult.policy_rejected


# [utest->req~grants-anon-class-verification-required~1]
def test_verification_required_never_covers_a_retryable_or_already_claimed_case():
    with pytest.raises(GrantFailureError):
        verification_required_outcome(AnonFailureCondition.firebase_provider_data_unavailable)
    with pytest.raises(GrantFailureError):
        verification_required_outcome(AnonFailureCondition.web_gate_already_consumed)


# [utest->req~grants-anon-class-verification-temporarily-unavailable~1]
def test_vtu_fails_closed_only_after_the_retry_budget_and_only_for_the_free_grant():
    outcome = verification_temporarily_unavailable_outcome(
        AnonFailureCondition.devicecheck_read_unavailable, retry_budget_exhausted=True)
    assert outcome.client_class is ClientErrorClass.verification_temporarily_unavailable
    assert outcome.durable is False
    # Not yet exhausted: the grant does not fail closed.
    with pytest.raises(GrantFailureError):
        verification_temporarily_unavailable_outcome(
            AnonFailureCondition.cloudflare_dependency_failed, retry_budget_exhausted=False)
    # And it never blocks login, account creation, upgrade, sync or restore.
    for operation in (AuthOperation.create_user,
                      AuthOperation.upgrade_anonymous_to_registered,
                      AuthOperation.sync,
                      AuthOperation.restore_subscription):
        with pytest.raises(GrantFailureError):
            verification_temporarily_unavailable_outcome(
                AnonFailureCondition.firebase_provider_data_unavailable, blocks=[operation])


# [utest->req~grants-anon-class-verification-temporarily-unavailable~1]
def test_the_provider_data_read_points_are_a_closed_set_of_five():
    points = firebase_provider_data_read_points()
    assert len(points) == 5
    assert {str(point) for point in points} == {
        "anonymous_create_user_completion", "registered_create_user_completion",
        "upgrade_anonymous_completion", "web_anonymous_grant_gate",
        "claim_registered_grant_completion"}


# --- the three condition sets ------------------------------------------------------------------


# [utest->req~grants-exhausted-condition-set~1]
def test_the_exhausted_condition_set_is_closed():
    assert exhausted_conditions() == EXHAUSTED_CONDITIONS
    assert {failure.condition for failure in ANON_FAILURES.values()
            if failure.client_class is ClientErrorClass.device_grant_exhausted} \
        == set(EXHAUSTED_CONDITIONS)


# [utest->req~grants-exhausted-condition-set~1]
def test_a_condition_missing_from_its_declared_set_is_refused(monkeypatch):
    failure = ANON_FAILURES[AnonFailureCondition.device_check_read_denied]
    monkeypatch.setitem(
        ANON_FAILURES, AnonFailureCondition.device_check_read_denied,
        type(failure)(failure.condition, failure.result,
                      ClientErrorClass.device_grant_exhausted))
    with pytest.raises(GrantFailureError):
        exhausted_conditions()


# [utest->req~grants-exhausted-cond-ios-bit-set~1]
def test_an_already_set_ios_bit_is_device_grant_exhausted():
    failure = classify_anonymous_failure(AnonFailureCondition.ios_anonymous_bit_set)
    assert failure.client_class is ClientErrorClass.device_grant_exhausted
    assert failure.result is AuthEventResult.native_claim_already_claimed


# [utest->req~grants-exhausted-cond-android-recall-set~1]
def test_an_already_set_device_recall_state_is_device_grant_exhausted():
    failure = classify_anonymous_failure(AnonFailureCondition.android_recall_anonymous_state_set)
    assert failure.client_class is ClientErrorClass.device_grant_exhausted
    assert failure.result is AuthEventResult.native_claim_already_claimed


# [utest->req~grants-exhausted-cond-web-gate-consumed~1]
def test_a_web_gate_conflict_is_device_grant_exhausted_under_its_own_result():
    failure = classify_anonymous_failure(AnonFailureCondition.web_gate_already_consumed)
    assert failure.client_class is ClientErrorClass.device_grant_exhausted
    assert failure.result is AuthEventResult.anti_abuse_already_claimed


# [utest->req~grants-verification-required-condition-set~1]
def test_the_verification_required_condition_set_is_closed():
    assert verification_required_conditions() == VERIFICATION_REQUIRED_CONDITIONS
    assert len(VERIFICATION_REQUIRED_CONDITIONS) == 4


# [utest->req~grants-vr-cond-device-check-denied~1]
def test_a_durable_device_check_denial_is_verification_required():
    failure = classify_anonymous_failure(AnonFailureCondition.device_check_read_denied)
    assert failure.client_class is ClientErrorClass.verification_required
    # A durable denial is not a retryable dependency failure.
    assert failure.after_retry_budget is False


# [utest->req~grants-vr-cond-policy-rejected~1]
def test_anonymous_grant_policy_rejection_is_verification_required():
    failure = classify_anonymous_failure(AnonFailureCondition.anonymous_grant_policy_rejected)
    assert failure.result is AuthEventResult.policy_rejected
    assert failure.client_class is ClientErrorClass.verification_required
    assert grants_client_class(AuthEventResult.policy_rejected,
                               operation=AuthOperation.claim_anonymous_grant) \
        is ClientErrorClass.verification_required


# [utest->req~grants-vr-cond-web-binding-mismatch~1]
def test_a_completed_web_lookup_that_fails_the_binding_check_is_verification_required():
    failure = classify_anonymous_failure(AnonFailureCondition.web_stored_binding_mismatch)
    assert failure.client_class is ClientErrorClass.verification_required
    # It is a completed lookup, not an unavailable one.
    assert failure.result is not AuthEventResult.firebase_lookup_unavailable


# [utest->req~grants-vr-cond-cloudflare-denial~1]
def test_a_server_validated_bot_check_denial_is_verification_required():
    denial = classify_anonymous_failure(AnonFailureCondition.cloudflare_bot_check_denied)
    dependency = classify_anonymous_failure(AnonFailureCondition.cloudflare_dependency_failed)
    assert denial.client_class is ClientErrorClass.verification_required
    assert dependency.client_class is ClientErrorClass.verification_temporarily_unavailable


# [utest->req~grants-vtu-condition-set~1]
def test_the_vtu_condition_set_is_closed():
    assert vtu_conditions() == VTU_CONDITIONS
    assert len(VTU_CONDITIONS) == 9


# [utest->req~grants-vtu-cond-devicecheck-read~1]
def test_devicecheck_read_unavailability_is_vtu_after_the_budget():
    failure = classify_anonymous_failure(AnonFailureCondition.devicecheck_read_unavailable)
    assert failure.result is AuthEventResult.native_claim_unavailable
    assert failure.client_class is ClientErrorClass.verification_temporarily_unavailable
    assert failure.after_retry_budget is True


# [utest->req~grants-vtu-cond-play-integrity-read~1]
def test_play_integrity_recall_read_unavailability_is_vtu_after_the_budget():
    failure = classify_anonymous_failure(
        AnonFailureCondition.play_integrity_recall_read_unavailable)
    assert failure.result is AuthEventResult.native_claim_unavailable
    assert failure.after_retry_budget is True


# [utest->req~grants-vtu-cond-write-failure~1]
def test_a_device_state_write_failure_is_vtu_after_the_budget():
    failure = classify_anonymous_failure(AnonFailureCondition.device_state_write_failed)
    assert failure.result is AuthEventResult.native_claim_write_failed
    assert failure.client_class is ClientErrorClass.verification_temporarily_unavailable
    assert failure.after_retry_budget is True


# [utest->req~grants-vtu-cond-firebase-lookup~1]
def test_a_firebase_provider_data_outage_is_vtu_after_the_budget():
    failure = classify_anonymous_failure(AnonFailureCondition.firebase_provider_data_unavailable)
    assert failure.result is AuthEventResult.firebase_lookup_unavailable
    assert failure.after_retry_budget is True


# [utest->req~grants-vtu-cond-cloudflare-dependency~1]
def test_a_cloudflare_dependency_failure_records_the_class_value_itself():
    failure = classify_anonymous_failure(AnonFailureCondition.cloudflare_dependency_failed)
    assert failure.result is TURNSTILE_AUDIT_RESULT
    assert failure.result is AuthEventResult.verification_temporarily_unavailable
    assert "cloudflare_lookup_unavailable" not in AuthEventResult.__members__


# [utest->req~grants-vtu-cond-device-bit-budget~1]
@pytest.mark.parametrize("condition,entry", [
    (AnonFailureCondition.devicecheck_read_budget_exhausted, "adapter_devicecheck_read"),
    (AnonFailureCondition.devicecheck_write_budget_exhausted, "adapter_devicecheck_write"),
    (AnonFailureCondition.device_recall_read_budget_exhausted,
     "adapter_play_integrity_device_recall_read"),
    (AnonFailureCondition.device_recall_write_budget_exhausted,
     "adapter_play_integrity_device_recall_write"),
])
def test_an_exhausted_device_bit_budget_audits_as_its_own_result_never_a_429(condition, entry):
    failure = classify_anonymous_failure(condition)
    assert failure.budget_entry == entry
    assert failure.result in DEVICE_BIT_BUDGET_RESULTS
    assert str(failure.result) == str(condition)
    assert failure.client_class is ClientErrorClass.verification_temporarily_unavailable
    verification_temporarily_unavailable_outcome(condition, http_status=503)
    with pytest.raises(GrantFailureError):
        verification_temporarily_unavailable_outcome(condition, http_status=429)


# --- the in-request retry policy ---------------------------------------------------------------


# [utest->req~grants-anon-retry-three-attempts~1]
@pytest.mark.parametrize("step", list(RetryableStep))
def test_a_retryable_step_is_attempted_three_times(step):
    seen: list[int] = []

    def run(attempt: int) -> str:
        seen.append(attempt)
        if attempt < ANON_RETRY_TOTAL_ATTEMPTS:
            raise ClaimStepFailed(step, retryable=True)
        return "ok"

    outcome = retry_claim_step(step, run)
    assert outcome.value == "ok"
    assert outcome.attempts == ANON_RETRY_TOTAL_ATTEMPTS == 3
    assert ANON_RETRY_ADDITIONAL_ATTEMPTS == 2
    assert seen == [1, 2, 3]


# [utest->req~grants-anon-retry-three-attempts~1]
def test_a_fourth_attempt_is_never_permitted():
    with pytest.raises(GrantFailureError):
        retry_claim_step(RetryableStep.devicecheck_read, lambda attempt: "ok",
                         attempts=ANON_RETRY_TOTAL_ATTEMPTS + 1)


# [utest->req~grants-anon-retry-budget-exhausted~1]
@pytest.mark.parametrize("step,result", [
    (RetryableStep.devicecheck_read, AuthEventResult.native_claim_unavailable),
    (RetryableStep.devicecheck_write, AuthEventResult.native_claim_write_failed),
    (RetryableStep.device_recall_read, AuthEventResult.native_claim_unavailable),
    (RetryableStep.device_recall_write, AuthEventResult.native_claim_write_failed),
    (RetryableStep.cloudflare_validation, AuthEventResult.verification_temporarily_unavailable),
    (RetryableStep.web_firebase_provider_data, AuthEventResult.firebase_lookup_unavailable),
])
def test_a_spent_retry_budget_rejects_with_vtu_and_no_grant(step, result):
    attempts: list[int] = []

    def run(attempt: int) -> str:
        attempts.append(attempt)
        raise ClaimStepFailed(step, retryable=True)

    with pytest.raises(ClaimRejection) as rejected:
        retry_claim_step(step, run)
    assert rejected.value.result is result
    assert rejected.value.error_code == "verification_temporarily_unavailable"
    assert len(attempts) == ANON_RETRY_TOTAL_ATTEMPTS


# [utest->req~grants-anon-retry-budget-exhausted~1]
def test_a_spent_budget_leaves_no_grant_behind():
    def run(attempt: int) -> str:
        raise ClaimStepFailed(RetryableStep.cloudflare_validation, retryable=True)

    with pytest.raises(GrantFailureError):
        retry_claim_step(RetryableStep.cloudflare_validation, run, grants_written=1)


# [utest->req~grants-anon-non-retryable-immediate~1]
def test_a_non_retryable_rejection_spends_no_retry_budget():
    attempts: list[int] = []

    def run(attempt: int) -> str:
        attempts.append(attempt)
        raise ClaimStepFailed(RetryableStep.devicecheck_read, retryable=False,
                              message="durably denied")

    with pytest.raises(ClaimStepFailed):
        retry_claim_step(RetryableStep.devicecheck_read, run)
    assert attempts == [1]


# [utest->req~grants-anon-retry-whole-claim~1]
def test_a_retry_is_a_whole_new_claim_and_never_activates_around_a_failed_write():
    fresh = whole_claim_retry("material-2", previous_material="material-1",
                              challenge_id="challenge-2", previous_challenge_id="challenge-1",
                              write=CONFIRMED_WRITE)
    assert fresh == "material-2"
    # The same challenge is not a new claim.
    with pytest.raises(GrantFailureError):
        whole_claim_retry("material-2", previous_material="material-1",
                          challenge_id="challenge-1", previous_challenge_id="challenge-1",
                          write=CONFIRMED_WRITE)
    # Nor is the same vendor material.
    with pytest.raises(ProofAdapterError):
        whole_claim_retry("material-1", previous_material="material-1",
                          challenge_id="challenge-2", previous_challenge_id="challenge-1",
                          write=CONFIRMED_WRITE)
    # And the server never activates around a failed or ambiguous write.
    with pytest.raises(DeviceBitWriteError):
        whole_claim_retry("material-2", previous_material="material-1",
                          challenge_id="challenge-2", previous_challenge_id="challenge-1",
                          write=FAILED_WRITE)


# [utest->req~grants-anon-retry-whole-claim~1]
def test_a_web_retry_brings_fresh_material_and_has_no_device_bit_write_to_confirm():
    # The web branch's exhausted Cloudflare or Firebase step is retried as a whole new claim with
    # a fresh operation challenge and fresh platform proof material. It carries no per-device bit,
    # so there is no vendor write confirmation to wait for.
    fresh = whole_claim_retry("turnstile-token-2", branch=ClaimBranch.web,
                              previous_material="turnstile-token-1",
                              challenge_id="challenge-2", previous_challenge_id="challenge-1")
    assert fresh == "turnstile-token-2"
    for step in (RetryableStep.cloudflare_validation,
                 RetryableStep.web_firebase_provider_data):
        outcome = verification_temporarily_unavailable_outcome(STEP_EXHAUSTED_CONDITION[step],
                                                              retry_budget_exhausted=True)
        assert outcome.client_class is ClientErrorClass.verification_temporarily_unavailable
    # A web retry claiming a per-device bit write is a contradiction, and the native branches
    # still need theirs confirmed.
    with pytest.raises(GrantFailureError):
        whole_claim_retry("turnstile-token-2", branch=ClaimBranch.web,
                          previous_material="turnstile-token-1", challenge_id="challenge-2",
                          previous_challenge_id="challenge-1", write=CONFIRMED_WRITE)
    with pytest.raises(DeviceBitWriteError):
        whole_claim_retry("material-2", branch=ClaimBranch.native_android,
                          previous_material="material-1", challenge_id="challenge-2",
                          previous_challenge_id="challenge-1")


# [utest->req~grants-anon-retry-not-bounded-by-expiry~1]
def test_retries_neither_lengthen_nor_are_bounded_by_the_challenge_expiry():
    # Long after the challenge's own 300-second lifetime: nothing after the claim rejects on it.
    assert_retries_not_bounded_by_expiry(elapsed_seconds=9_000.0,
                                         attempts=ANON_RETRY_TOTAL_ATTEMPTS)
    with pytest.raises(GrantFailureError):
        assert_retries_not_bounded_by_expiry(elapsed_seconds=1.0, attempts=1,
                                             expiry_extended=True)
    with pytest.raises(GrantFailureError):
        assert_retries_not_bounded_by_expiry(elapsed_seconds=1.0, attempts=1,
                                             expiry_evaluations=2)
    # The retry budget is the bound instead.
    with pytest.raises(ProofAdapterError):
        assert_retries_not_bounded_by_expiry(elapsed_seconds=1.0,
                                             attempts=ANON_RETRY_TOTAL_ATTEMPTS + 1)


# --- the burned device slot --------------------------------------------------------------------


# [utest->req~grants-burned-slot-accepted-outcome~1]
@pytest.mark.parametrize("cause", list(BurnedSlotCause))
def test_a_burned_slot_is_remediated_with_a_manual_grant(cause):
    assert accepted_burned_slot(cause, write_confirmed=True,
                                grant_activated=False) is AccessGrantSource.manual
    assert PENDING_STATE_MACHINES == frozenset()
    assert VENDOR_STATE_RECONCILERS == frozenset()


# [utest->req~grants-burned-slot-accepted-outcome~1]
def test_only_a_confirmed_write_without_a_grant_burns_a_slot():
    with pytest.raises(GrantFailureError):
        accepted_burned_slot(BurnedSlotCause.crash_after_confirmed_write,
                             write_confirmed=False, grant_activated=False)
    with pytest.raises(GrantFailureError):
        accepted_burned_slot(BurnedSlotCause.crash_after_confirmed_write,
                             write_confirmed=True, grant_activated=True)


# [utest->req~grants-burned-slot-accepted-outcome~1]
@pytest.mark.parametrize("branch", [ClaimBranch.native_ios, ClaimBranch.native_android])
def test_the_whole_claim_retry_after_a_lost_ack_reads_the_set_bit(branch):
    outcome = burned_slot_retry_outcome(branch)
    assert outcome.client_class is ClientErrorClass.device_grant_exhausted
    assert outcome.result is AuthEventResult.native_claim_already_claimed
    with pytest.raises(GrantFailureError):
        burned_slot_retry_outcome(ClaimBranch.web)


# [utest->req~grants-burned-slot-accepted-outcome~1]
def test_vendor_latency_after_a_confirmed_write_causes_no_time_based_rejection():
    # Ordinary latency, long past the challenge lifetime: the activation still commits.
    assert_activation_never_rejects_on_expiry(write_confirmed=True,
                                              vendor_latency_seconds=1_200.0)
    with pytest.raises(GrantFailureError):
        assert_activation_never_rejects_on_expiry(write_confirmed=True,
                                                  vendor_latency_seconds=1.0,
                                                  expiry_evaluations=2)


# --- the normative client remediation ----------------------------------------------------------


# [utest->req~grants-remediation-device-grant-exhausted~1]
def test_the_exhausted_remediation_is_declared_for_the_class():
    remediation = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    assert remediation.client_class is ClientErrorClass.device_grant_exhausted
    assert ClientErrorClass.device_grant_exhausted in ANON_REMEDIATION


# [utest->req~grants-remediation-exhausted-alternate-path~1]
def test_the_exhausted_alternate_path_is_the_registered_claim():
    remediation = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    assert remediation.durably_closed is True
    assert remediation.alternate_operation is AuthOperation.claim_registered_grant
    row = identity_row()
    assert exhausted_alternate_path(row, active_grant_source=None) \
        is AuthOperation.claim_registered_grant
    # It requires a Google or Apple linked identity: it is a path, not a guarantee.
    with pytest.raises(FreeGrantRejected):
        exhausted_alternate_path(identity_row(provider=IdentityProvider.anonymous,
                                              provider_uid=None),
                                 active_grant_source=None)
    # Nor does it survive an active grant that is not a convertible anonymous device grant.
    with pytest.raises(FreeGrantRejected):
        exhausted_alternate_path(row, active_grant_source=AccessGrantSource.subscription)


# [utest->req~grants-remediation-exhausted-direct-to-registered~1]
def test_the_client_is_directed_to_a_google_or_apple_identity_then_the_registered_route():
    remediation = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    assert remediation.alternate_route == "/auth/claim-registered-grant"
    assert remediation.obtain_identity_by == ("sign_in", "create", "upgrade", "link")


# [utest->req~grants-remediation-exhausted-no-retry~1]
def test_the_client_never_retries_the_anonymous_claim_under_the_same_condition():
    remediation = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    assert remediation.retry_same_endpoint is False
    assert remediation.transient is False


# [utest->req~grants-remediation-verification-required~1]
def test_the_verification_required_remediation_is_declared_for_the_class():
    remediation = anonymous_remediation(ClientErrorClass.verification_required)
    assert remediation.client_class is ClientErrorClass.verification_required
    assert ClientErrorClass.verification_required in ANON_REMEDIATION


# [utest->req~grants-remediation-vr-durably-closed~1]
def test_verification_required_leaves_no_guaranteed_free_credit_alternate():
    remediation = anonymous_remediation(ClientErrorClass.verification_required)
    assert remediation.durably_closed is True
    assert remediation.guaranteed_alternate is False


# [utest->req~grants-remediation-vr-no-blind-retry~1]
def test_verification_required_is_never_blind_retried():
    remediation = anonymous_remediation(ClientErrorClass.verification_required)
    assert remediation.retry_same_endpoint is False
    assert remediation.fresh_challenge is False


# [utest->req~grants-remediation-verification-temporarily-unavailable~1]
def test_the_vtu_remediation_is_declared_for_the_class():
    remediation = anonymous_remediation(
        ClientErrorClass.verification_temporarily_unavailable)
    assert remediation.client_class is ClientErrorClass.verification_temporarily_unavailable
    assert ClientErrorClass.verification_temporarily_unavailable in ANON_REMEDIATION


# [utest->req~grants-remediation-vtu-transient~1]
def test_vtu_is_transient_rather_than_durable_anti_abuse_state():
    remediation = anonymous_remediation(
        ClientErrorClass.verification_temporarily_unavailable)
    assert remediation.transient is True
    assert remediation.durably_closed is False


# [utest->req~grants-remediation-vtu-retry-fresh-material~1]
def test_vtu_is_retried_with_a_fresh_challenge_fresh_proof_and_backoff():
    remediation = anonymous_remediation(
        ClientErrorClass.verification_temporarily_unavailable)
    assert remediation.retry_same_endpoint is True
    assert remediation.fresh_challenge is True
    assert remediation.fresh_proof is True
    assert remediation.backoff is True


# [utest->req~grants-remediation-vtu-registered-backstop~1]
def test_the_registered_backstop_waits_out_a_held_grant_without_forfeiting_the_free_grant():
    row = identity_row()
    operation, blocked_until = vtu_registered_backstop(row, active_grant_source=None)
    assert operation is AuthOperation.claim_registered_grant
    assert blocked_until is None
    # A convertible anonymous device grant does not block the backstop.
    operation, _ = vtu_registered_backstop(
        row, active_grant_source=AccessGrantSource.anonymous_device_grant)
    assert operation is AuthOperation.claim_registered_grant
    # Any other active grant refuses the claim until it ends, and reports when that is.
    ends = datetime.now(UTC) + timedelta(days=30)
    operation, blocked_until = vtu_registered_backstop(
        row, active_grant_source=AccessGrantSource.subscription, held_grant_ends_at=ends)
    assert operation is None
    assert blocked_until == ends
    # The free grant is not forfeited by the wait: once the grant ends it is claimable again.
    assert vtu_registered_backstop(row, active_grant_source=None)[0] \
        is AuthOperation.claim_registered_grant


# --- the client error taxonomy for the completion endpoints ------------------------------------


# [utest->req~grants-taxonomy-opaque-classes~1]
def test_the_four_completion_endpoints_return_opaque_classes():
    assert set(COMPLETION_ENDPOINTS) == {AuthOperation.create_user,
                                         AuthOperation.upgrade_anonymous_to_registered,
                                         AuthOperation.claim_anonymous_grant,
                                         AuthOperation.claim_registered_grant}
    for operation in COMPLETION_ENDPOINTS:
        rejection = completion_rejection(AuthEventResult.challenge_expired, operation=operation)
        assert rejection.body == {"code": ClientErrorClass.challenge_required}
        # The internal result stays behind.
        assert "challenge_expired" not in set(rejection.body.values())
    # An operation outside the four has no place in this taxonomy.
    with pytest.raises(GrantFailureError):
        grants_client_class(AuthEventResult.challenge_expired,
                            operation=AuthOperation.restore_subscription)


# [utest->req~grants-taxonomy-shared-response-shape~1]
def test_one_response_shape_across_the_endpoints_with_the_specific_result_audited():
    shapes = {tuple(sorted(completion_rejection(AuthEventResult.firebase_lookup_unavailable,
                                                operation=operation).body))
              for operation in COMPLETION_ENDPOINTS}
    assert shapes == {("code",)}
    # The endpoint-specific classes are part of the same shape, not a second contract.
    exhausted = completion_rejection(AuthEventResult.anti_abuse_already_claimed,
                                     operation=AuthOperation.claim_anonymous_grant)
    assert exhausted.body == {"code": ClientErrorClass.device_grant_exhausted}
    # The audit row keeps the specific internal result, never the generic class name.
    assert exhausted.audit_result is AuthEventResult.anti_abuse_already_claimed
    assert str(exhausted.audit_result) != str(exhausted.client_class)
    # `succeeded` is no rejection, and no generic placeholder result exists.
    with pytest.raises(GrantFailureError):
        completion_rejection(AuthEventResult.succeeded,
                             operation=AuthOperation.claim_anonymous_grant)


# [utest->req~grants-taxonomy-normative-remediation~1]
def test_classes_with_different_remediations_are_never_collapsed():
    assert_remediations_distinct(*ANON_GRANT_CLASSES)
    with pytest.raises(GrantFailureError):
        assert_remediations_distinct(ClientErrorClass.verification_required,
                                     ClientErrorClass.verification_required)
    # A transient provider failure is never surfaced as a durable denial on its own.
    assert transient_failure_class(AnonFailureCondition.devicecheck_read_unavailable) \
        is ClientErrorClass.verification_temporarily_unavailable
    assert transient_failure_class(AnonFailureCondition.devicecheck_read_unavailable,
                                   durable_state_observed=True) \
        is ClientErrorClass.device_grant_exhausted
    with pytest.raises(GrantFailureError):
        transient_failure_class(AnonFailureCondition.cloudflare_bot_check_denied)


# [utest->req~grants-taxonomy-shared-catalog-classes~1]
def test_the_five_shared_catalog_classes_keep_no_grants_domain_copy():
    assert SHARED_CATALOG_CLASSES == {ClientErrorClass.auth_required,
                                      ClientErrorClass.preauth_identity_not_allowed,
                                      ClientErrorClass.account_unavailable,
                                      ClientErrorClass.identity_already_linked,
                                      ClientErrorClass.challenge_required}
    assert SHARED_CATALOG_CLASSES & GRANTS_OWNED_CLASSES == frozenset()
    assert SHARED_CATALOG_CLASSES & set(ANON_REMEDIATION) == frozenset()
    for client_class in SHARED_CATALOG_CLASSES:
        assert shared_catalog_remediation(client_class).action
    with pytest.raises(GrantFailureError):
        shared_catalog_remediation(ClientErrorClass.device_grant_exhausted)


# [utest->req~grants-class-proof-rejected~1]
@pytest.mark.parametrize("cause", list(VendorMaterialCause))
def test_every_vendor_material_failure_returns_the_one_class(cause):
    result, client_class = vendor_material_rejection(cause)
    assert client_class is ClientErrorClass.proof_rejected
    assert result is AuthEventResult.proof_malformed


# [utest->req~grants-class-proof-rejected~1]
def test_a_structurally_valid_proof_never_audits_as_proof_malformed():
    with pytest.raises(GrantFailureError):
        vendor_material_rejection(VendorMaterialCause.inconsistent_app_identity, parseable=True)


# [utest->req~grants-class-proof-rejected~1]
@pytest.mark.parametrize("transaction", list(ProviderTransaction))
def test_a_provider_transaction_maps_to_a_dependency_class_not_proof_rejected(transaction):
    result, client_class = vendor_material_rejection(
        VendorMaterialCause.malformed_proof, transaction=transaction)
    assert client_class is ClientErrorClass.verification_temporarily_unavailable
    assert result is not AuthEventResult.proof_malformed


# [utest->req~grants-class-operation-not-allowed~1]
def test_structural_blocks_surface_as_operation_not_allowed_with_their_own_results():
    for block in StructuralBlock:
        blocked_until = (datetime.now(UTC) + timedelta(days=1)
                         if block is StructuralBlock.registered_grant_destination_incompatible
                         else None)
        rejection = operation_not_allowed_block(block, blocked_until=blocked_until)
        assert rejection.client_class is ClientErrorClass.operation_not_allowed
    # The destination case is a wait: it reports when the held grant ends.
    with pytest.raises(GrantFailureError):
        operation_not_allowed_block(
            StructuralBlock.registered_grant_destination_incompatible)
    destination = operation_not_allowed_block(
        StructuralBlock.registered_grant_destination_incompatible,
        blocked_until=datetime.now(UTC) + timedelta(days=1))
    assert destination.audit_result \
        is AuthEventResult.registered_grant_destination_incompatible
    assert "blocked_until" in destination.body


# [utest->req~grants-class-operation-not-allowed~1]
def test_the_cases_operation_not_allowed_never_covers():
    assert NOT_STRUCTURAL_RESULTS == {AuthEventResult.identity_already_linked,
                                      AuthEventResult.preauth_identity_not_allowed,
                                      AuthEventResult.blocked_user,
                                      AuthEventResult.historical_identity}
    for result in NOT_STRUCTURAL_RESULTS:
        with pytest.raises(GrantFailureError):
            grants_client_class(result, operation=AuthOperation.create_user, structural=True)
        assert grants_client_class(result, operation=AuthOperation.create_user) \
            is not ClientErrorClass.operation_not_allowed
    # `policy_rejected` from create-user and upgrade-anonymous maps here: neither is a
    # free-credit path.
    for operation in (AuthOperation.create_user,
                      AuthOperation.upgrade_anonymous_to_registered):
        assert grants_client_class(AuthEventResult.policy_rejected, operation=operation) \
            is ClientErrorClass.operation_not_allowed


# [utest->req~grants-class-operation-not-allowed~1]
def test_the_anonymous_claims_structural_scope_excludes_three_legitimate_cases():
    # A registered google/apple claimant on a native path is legitimate.
    assert anonymous_structural_scope(ClaimBranch.native_ios, registered_claimant=True) is None
    # A missing or insufficient native gate is a vendor-material failure.
    assert anonymous_structural_scope(ClaimBranch.native_android, native_gate_missing=True) \
        is ClientErrorClass.proof_rejected
    # A web claimant failing the stored-binding gate follows verification_required.
    assert anonymous_structural_scope(ClaimBranch.web, web_binding_unsatisfied=True) \
        is ClientErrorClass.verification_required
    # Anything else structural keeps the class.
    assert anonymous_structural_scope(ClaimBranch.native_ios) \
        is ClientErrorClass.operation_not_allowed


# [utest->req~grants-class-verification-required~1]
def test_verification_required_covers_both_claims_own_durable_blocks():
    result, client_class = verification_required_scope(
        AuthOperation.claim_anonymous_grant,
        condition=AnonFailureCondition.cloudflare_bot_check_denied)
    assert client_class is ClientErrorClass.verification_required
    assert result is AuthEventResult.policy_rejected
    result, client_class = verification_required_scope(AuthOperation.claim_registered_grant)
    assert result is AuthEventResult.idp_account_not_eligible
    assert client_class is ClientErrorClass.verification_required
    with pytest.raises(GrantFailureError):
        verification_required_scope(AuthOperation.create_user)


# [utest->req~grants-class-device-grant-exhausted~1]
def test_the_exhausted_class_routes_by_which_path_closed():
    route, actions = device_grant_exhausted_scope(AuthOperation.claim_anonymous_grant)
    assert route == "/auth/claim-registered-grant"
    assert actions == ("sign_in", "create", "upgrade", "link")
    # From the registered claim there is no further free-credit path.
    assert device_grant_exhausted_scope(AuthOperation.claim_registered_grant) == (None, ())


# [utest->req~grants-class-account-already-claimed~1]
def test_only_the_registered_gate_conflict_is_account_already_claimed():
    result, client_class = account_already_claimed_scope(
        GateConsumptionKind.registered_account_grant)
    assert result is AuthEventResult.idp_account_already_claimed
    assert client_class is ClientErrorClass.account_already_claimed
    # The web anonymous-grant conflict is device_grant_exhausted, never this class.
    result, client_class = account_already_claimed_scope(GateConsumptionKind.web_anonymous_gate)
    assert client_class is ClientErrorClass.device_grant_exhausted
    assert result is AuthEventResult.anti_abuse_already_claimed


# [utest->req~grants-class-verification-temporarily-unavailable~1]
def test_the_vtu_results_include_the_native_firebase_and_budget_families():
    results = verification_temporarily_unavailable_results()
    assert AuthEventResult.native_claim_unavailable in results
    assert AuthEventResult.native_claim_write_failed in results
    assert AuthEventResult.firebase_lookup_unavailable in results
    assert DEVICE_BIT_BUDGET_RESULTS <= results
    assert TURNSTILE_AUDIT_RESULT in results
    # The same class at anonymous create-user completion.
    assert grants_client_class(AuthEventResult.firebase_lookup_unavailable,
                               operation=AuthOperation.create_user) \
        is ClientErrorClass.verification_temporarily_unavailable
    # Both free-credit claims can write a device-bit budget result.
    for operation in (AuthOperation.claim_anonymous_grant,
                      AuthOperation.claim_registered_grant):
        for result in DEVICE_BIT_BUDGET_RESULTS:
            assert grants_client_class(result, operation=operation) \
                is ClientErrorClass.verification_temporarily_unavailable


# [utest->req~grants-anon-proof-state-dependency-split~1]
def test_the_anonymous_split_is_normative():
    families: dict[ClientErrorClass, set[AnonFailureCondition]] = {}
    for condition in AnonFailureCondition:
        failure = classify_anonymous_failure(condition)
        families.setdefault(failure.client_class, set()).add(condition)
    assert families[ClientErrorClass.proof_rejected] == {
        AnonFailureCondition.client_proof_missing_or_malformed}
    assert families[ClientErrorClass.device_grant_exhausted] == set(EXHAUSTED_CONDITIONS)
    assert families[ClientErrorClass.verification_required] == \
        set(VERIFICATION_REQUIRED_CONDITIONS)
    assert families[ClientErrorClass.verification_temporarily_unavailable] == set(VTU_CONDITIONS)
    # There is no enrolled-key conflict branch at all.
    assert not [condition for condition in AnonFailureCondition if "enrolled" in str(condition)]


# [utest->req~grants-reg-state-duplicate-dependency-split~1]
def test_the_registered_split_is_normative_and_keeps_its_outcomes_distinct():
    assert registered_split(RegFailureCondition.identity_not_google_or_apple) == (
        AuthEventResult.idp_account_not_eligible, ClientErrorClass.verification_required)
    assert registered_split(RegFailureCondition.stored_provider_uid_absent) == (
        AuthEventResult.idp_account_not_eligible, ClientErrorClass.verification_required)
    assert registered_split(RegFailureCondition.registered_gate_conflict) == (
        AuthEventResult.idp_account_already_claimed, ClientErrorClass.account_already_claimed)
    assert registered_split(RegFailureCondition.device_check_dependency_failed) == (
        AuthEventResult.native_claim_unavailable,
        ClientErrorClass.verification_temporarily_unavailable)
    assert_grant_time_and_write_time_distinct()
    # No raw provider account identifier on an audit, grant or anti-abuse row.
    assert_no_raw_provider_account_ids(["grant_id", "idp_account_hash",
                                        "idp_account_hash_key_version"])
    with pytest.raises(GrantFailureError):
        assert_no_raw_provider_account_ids(["grant_id", "provider_uid"])


# --- accepted limitations ------------------------------------------------------------------------


# [utest->req~grants-accepted-limitations-vulnerability-conditions~1]
def test_the_safe_native_and_web_paths_are_not_vulnerable():
    assert len(VULNERABILITY_CONDITIONS) == 8
    assert_not_vulnerable(ClaimBranch.native_ios,
                          device_state_read=True, write=CONFIRMED_WRITE,
                          web_binding_verified=False, bot_gate_verified=False,
                          proof_use=ProofUse.anti_abuse_gate,
                          persisted_columns=["grant_id", "native_claim_provider"],
                          uniqueness_domains=["user_grant_source"],
                          committed_free_sources=[], active_grants=0)
    assert_not_vulnerable(ClaimBranch.web,
                          device_state_read=False, write=None,
                          web_binding_verified=True, bot_gate_verified=True,
                          proof_use=ProofUse.anti_abuse_gate,
                          persisted_columns=["grant_id", "idp_account_hash"],
                          uniqueness_domains=["user_grant_source",
                                              "web_anonymous_gate_provider_account"],
                          committed_free_sources=[], active_grants=0)


# [utest->req~grants-accepted-limitations-vulnerability-conditions~1]
@pytest.mark.parametrize("overrides", [
    # grants before reading the applicable device state
    {"device_state_read": False},
    # grants before the vendor confirms the applicable bit write
    {"write": FAILED_WRITE},
    {"write": None},
    # persists a raw vendor token or a synthetic device principal hash
    {"persisted_columns": ["devicecheck_token"]},
    {"persisted_columns": ["device_principal_hash"]},
    # treats the device check or the bot check as account-ownership proof
    {"proof_use": ProofUse.ownership},
    {"proof_use": ProofUse.identity},
    # omits the (user, grant source) uniqueness domain
    {"uniqueness_domains": []},
    # creates multiple active free grants for the same user
    {"active_grants": 2},
    # the user's history already carries the free allowance
    {"committed_free_sources": [AccessGrantSource.anonymous_device_grant],
     "registered_claim": True},
])
def test_each_vulnerability_condition_is_refused(overrides: dict[str, Any]):
    arguments: dict[str, Any] = {
        "device_state_read": True, "write": CONFIRMED_WRITE,
        "web_binding_verified": False, "bot_gate_verified": False,
        "proof_use": ProofUse.anti_abuse_gate,
        "persisted_columns": ["grant_id"],
        "uniqueness_domains": ["user_grant_source"],
        "committed_free_sources": [], "active_grants": 0,
    }
    arguments.update(overrides)
    with pytest.raises((GrantFailureError, FreeGrantError, DeviceBitWriteError,
                        InvariantError)):
        assert_not_vulnerable(ClaimBranch.native_ios, **arguments)


# [utest->req~grants-accepted-limitations-vulnerability-conditions~1]
@pytest.mark.parametrize("use", [use for use in ProofUse if use is not ProofUse.anti_abuse_gate])
def test_the_device_and_bot_checks_are_never_account_ownership_proof(use: ProofUse):
    # The material is anti-abuse device state and nothing else: every other use of it — identity,
    # ownership, recovery, upgrade, account resolution — is refused on both branches.
    for branch, write in ((ClaimBranch.native_ios, CONFIRMED_WRITE), (ClaimBranch.web, None)):
        with pytest.raises((GrantFailureError, InvariantError)):
            assert_not_vulnerable(branch,
                                  device_state_read=True, write=write,
                                  web_binding_verified=True, bot_gate_verified=True,
                                  proof_use=use,
                                  persisted_columns=["grant_id"],
                                  uniqueness_domains=["user_grant_source",
                                                      "web_anonymous_gate_provider_account"])


# [utest->req~grants-accepted-limitations-vulnerability-conditions~1]
def test_a_web_grant_before_the_binding_and_bot_gate_is_a_vulnerability():
    for binding, bot in ((False, True), (True, False), (False, False)):
        with pytest.raises(GrantFailureError):
            assert_not_vulnerable(ClaimBranch.web,
                                  device_state_read=False, write=None,
                                  web_binding_verified=binding, bot_gate_verified=bot,
                                  proof_use=ProofUse.anti_abuse_gate,
                                  uniqueness_domains=["user_grant_source",
                                                      "web_anonymous_gate_provider_account"])


# [utest->req~grants-accepted-limitations-vulnerability-conditions~1]
def test_a_registered_grant_is_refused_once_the_allowance_is_spent():
    assert_registered_allowance_unused([], identity_row())
    for source in (AccessGrantSource.anonymous_device_grant,
                   AccessGrantSource.registered_account_grant):
        with pytest.raises(GrantFailureError):
            assert_registered_allowance_unused([source], identity_row())
    with pytest.raises(GrantFailureError):
        assert_registered_allowance_unused(
            [], identity_row(provider=IdentityProvider.anonymous, provider_uid=None))
