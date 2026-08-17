"""Failure handling for `claim_registered_grant`, and the registered alternate path."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.external_identities import (
    ExternalIdentityRow,
    IdentityState,
    NativeClaimPlatform,
)
from nativespeaker.api.auth.free_grants import FreeGrantError
from nativespeaker.api.auth.grant_failures import (
    AnonFailureCondition,
    GrantFailureError,
    anonymous_remediation,
)
from nativespeaker.api.auth.invariants import GateConsumptionKind
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    route_for,
    variants_for,
)
from nativespeaker.api.auth.proof_adapters import ClaimRejection
from nativespeaker.api.auth.proof_endpoints import ClaimBranch, upgrade_in_place_flip
from nativespeaker.api.auth.registered_grant_failures import (
    DURABLE_REGISTERED_CLASSES,
    HELD_GRANT_FIELD,
    NON_RETRYABLE_RESULTS,
    PAID_CONTINUATIONS,
    REG_CLIENT_CLASSES,
    REG_RETRY_ADDITIONAL_ATTEMPTS,
    REG_RETRY_TOTAL_ATTEMPTS,
    RegClaimCondition,
    RegisteredStepFailed,
    RegRetryableStep,
    account_already_claimed_block,
    account_unavailable_results,
    alternate_path,
    assert_no_transient_as_exhausted,
    assert_non_retryable_immediate,
    assert_registered_retries_write_once,
    classify_registered_failure,
    destination_incompatible_rejection,
    device_grant_exhausted_conditions,
    device_state_set_closure,
    exhausted_or_no_anonymous_path_remediation,
    no_qualifying_native_evidence,
    other_durable_closure,
    preauth_caller_rejection,
    proof_rejected_conditions,
    registered_durable_rejection,
    registered_emitted_classes,
    registered_failure_class,
    registered_failure_rejection,
    registered_path_gates,
    registered_retry_budget_exhausted,
    registered_retry_is_whole_new_claim,
    registered_write_failure,
    retry_registered_step,
    verification_required_conditions,
    verification_temporarily_unavailable_conditions,
    web_gate_conflict_closure,
    web_stored_binding_closure,
)
from nativespeaker.api.auth.registered_grants import RegisteredDestinationBlocked
from nativespeaker.api.auth.taxonomy import ClientErrorClass, remediation_for
from nativespeaker.api.ratelimit.ordering import (
    DeviceBitCall,
    DeviceBitWrite,
    DeviceBitWriteError,
)

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
CONFIRMED_WRITE = DeviceBitWrite(call=DeviceBitCall.devicecheck_write, confirmed=True)
FAILED_WRITE = DeviceBitWrite(call=DeviceBitCall.devicecheck_write, confirmed=False)


def google_row(**overrides: Any) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.google,
                              "provider_uid": "google-account-1",
                              "identity_state": IdentityState.active}
    fields.update(overrides)
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(),
                               issuer="https://securetoken.google.com/test-project",
                               subject="firebase-subject", **fields)


# --- The classes the operation surfaces -------------------------------------------------------------


# [utest->req~grants-reg-failure-classes~1]
def test_every_registered_claim_failure_surfaces_one_declared_class():
    assert registered_emitted_classes() == frozenset(REG_CLIENT_CLASSES)
    # Every condition classifies, and its internal result stays behind the class.
    for condition in RegClaimCondition:
        failure = classify_registered_failure(condition)
        assert failure.client_class in REG_CLIENT_CLASSES
        assert registered_failure_class(condition) is failure.client_class
        rejection = registered_failure_rejection(condition, held_grant_ends_at=NOW)
        assert rejection.body["code"] == failure.client_class.value
        if failure.result not in {AuthEventResult.preauth_identity_not_allowed,
                                  AuthEventResult.verification_temporarily_unavailable}:
            assert str(failure.result) not in rejection.body.values()
    with pytest.raises(GrantFailureError):
        classify_registered_failure("not_a_condition")  # type: ignore[arg-type]


# [utest->req~grants-reg-class-preauth-identity-not-allowed~1]
def test_a_preauth_or_unlinked_caller_of_this_linked_only_endpoint_is_refused():
    failure = preauth_caller_rejection()
    assert failure.result is AuthEventResult.preauth_identity_not_allowed
    assert failure.client_class is ClientErrorClass.preauth_identity_not_allowed
    remediation = remediation_for(failure.client_class)
    assert remediation.next_route == "/auth/create-user"
    assert remediation.http_status == 403


# [utest->req~grants-reg-class-account-unavailable~1]
def test_an_inactive_blocked_or_historical_account_shares_one_class_with_distinct_results():
    results = account_unavailable_results()
    assert set(results) == {AuthEventResult.blocked_user, AuthEventResult.historical_identity}
    classes = {classify_registered_failure(condition).client_class
               for condition in (RegClaimCondition.blocked_or_inactive_user,
                                 RegClaimCondition.historical_identity)}
    assert classes == {ClientErrorClass.account_unavailable}
    assert remediation_for(ClientErrorClass.account_unavailable).terminal
    # The client cannot tell the two states apart: the body names the class and nothing else.
    for condition in (RegClaimCondition.blocked_or_inactive_user,
                      RegClaimCondition.historical_identity):
        body = registered_failure_rejection(condition).body
        assert set(body) == {"code"}


# [utest->req~grants-reg-class-operation-not-allowed~1]
def test_a_blocking_active_grant_reports_only_when_it_ends():
    ends = NOW + timedelta(days=9)
    rejection = destination_incompatible_rejection(RegisteredDestinationBlocked(ends))
    assert rejection.client_class is ClientErrorClass.operation_not_allowed
    assert rejection.audit_result is AuthEventResult.registered_grant_destination_incompatible
    assert set(rejection.body) == {"code", HELD_GRANT_FIELD}
    assert rejection.body[HELD_GRANT_FIELD] == ends.isoformat()
    assert rejection.retry_after_held_grant_ends and not rejection.contact_support
    # An open-ended grant reports `null`, and that user goes to support, not to a retry loop.
    open_ended = destination_incompatible_rejection(RegisteredDestinationBlocked(None))
    assert open_ended.body[HELD_GRANT_FIELD] is None
    assert open_ended.contact_support and not open_ended.retry_after_held_grant_ends
    # Nothing else about the held grant is disclosed: no source, tier or identifier.
    assert not {"source", "tier_id", "grant_id"} & set(rejection.body)
    # The other structural policy blocks take the same class through the same shape.
    structural = registered_failure_rejection(RegClaimCondition.structural_policy_block)
    assert structural.client_class is ClientErrorClass.operation_not_allowed
    assert structural.audit_result is AuthEventResult.policy_rejected
    assert HELD_GRANT_FIELD not in structural.body


# [utest->req~grants-reg-class-verification-required~1]
def test_an_ineligible_stored_identity_is_verification_required():
    conditions = verification_required_conditions()
    assert set(conditions) == {RegClaimCondition.stored_provider_not_google_or_apple,
                              RegClaimCondition.stored_provider_uid_absent}
    for condition in conditions:
        failure = classify_registered_failure(condition)
        assert failure.result is AuthEventResult.idp_account_not_eligible
        assert failure.client_class is ClientErrorClass.verification_required
        assert failure.durable and not failure.retryable
    remediation = remediation_for(ClientErrorClass.verification_required)
    assert not remediation.transient
    assert remediation.action == "obtain_registered_identity_then_retry_only_if_state_changed"


# [utest->req~grants-reg-class-device-grant-exhausted~1]
def test_an_already_set_registered_device_state_is_device_grant_exhausted():
    conditions = device_grant_exhausted_conditions()
    assert set(conditions) == {RegClaimCondition.ios_registered_bit_set,
                              RegClaimCondition.android_registered_recall_set}
    for condition in conditions:
        failure = classify_registered_failure(condition)
        assert failure.result is AuthEventResult.native_claim_already_claimed
        assert failure.client_class is ClientErrorClass.device_grant_exhausted
        assert failure.durable
    # The web kind has no such state, so no web condition produces this class.
    web_classes = {classify_registered_failure(condition).client_class
                   for condition in (RegClaimCondition.turnstile_dependency_failed,
                                     RegClaimCondition.registered_gate_consumed)}
    assert ClientErrorClass.device_grant_exhausted not in web_classes


# [utest->req~grants-reg-class-account-already-claimed~1]
def test_a_consumed_registered_gate_is_final_for_that_provider_account():
    failure = account_already_claimed_block()
    assert failure.result is AuthEventResult.idp_account_already_claimed
    assert failure.client_class is ClientErrorClass.account_already_claimed
    assert remediation_for(failure.client_class).terminal
    # It is the registered gate's block alone.
    with pytest.raises(GrantFailureError):
        account_already_claimed_block(GateConsumptionKind.web_anonymous_gate)


# [utest->req~grants-reg-class-verification-temporarily-unavailable~1]
def test_a_transient_dependency_failure_is_temporary_and_user_not_found_is_not():
    conditions = verification_temporarily_unavailable_conditions()
    assert set(conditions) == {RegClaimCondition.device_check_vendor_outage,
                              RegClaimCondition.firebase_provider_data_unavailable,
                              RegClaimCondition.turnstile_dependency_failed}
    assert classify_registered_failure(
        RegClaimCondition.firebase_provider_data_unavailable
    ).result is AuthEventResult.firebase_lookup_unavailable
    for condition in conditions:
        failure = classify_registered_failure(condition)
        assert failure.client_class is ClientErrorClass.verification_temporarily_unavailable
        assert failure.after_retry_budget
    assert remediation_for(ClientErrorClass.verification_temporarily_unavailable).transient
    # Firebase user-not-found at that read is non-retryable and surfaces as `auth_required`.
    not_found = classify_registered_failure(RegClaimCondition.firebase_user_not_found)
    assert not_found.result is AuthEventResult.firebase_user_unresolved
    assert not_found.client_class is ClientErrorClass.auth_required
    assert not not_found.retryable


# [utest->req~grants-reg-class-proof-rejected~1]
def test_missing_or_partial_platform_proof_is_proof_rejected_and_outages_are_not():
    conditions = proof_rejected_conditions()
    assert set(conditions) == {RegClaimCondition.incomplete_platform_proof_set,
                              RegClaimCondition.evidence_set_shape_invalid}
    for condition in conditions:
        failure = classify_registered_failure(condition)
        assert failure.result is AuthEventResult.proof_malformed
        assert failure.client_class is ClientErrorClass.proof_rejected
    # Vendor read/write outages and Turnstile dependency failures are never `proof_rejected`.
    for dependency in (RegClaimCondition.device_check_vendor_outage,
                       RegClaimCondition.turnstile_dependency_failed):
        assert classify_registered_failure(dependency).client_class \
            is ClientErrorClass.verification_temporarily_unavailable


# --- The in-request retry policy ---------------------------------------------------------------------


# [utest->req~grants-reg-retry-three-attempts~1]
def test_a_retryable_step_is_attempted_three_times_in_the_same_request():
    assert (REG_RETRY_TOTAL_ATTEMPTS, REG_RETRY_ADDITIONAL_ATTEMPTS) == (3, 2)
    attempts: list[int] = []

    def flaky(attempt: int) -> str:
        attempts.append(attempt)
        if attempt < REG_RETRY_TOTAL_ATTEMPTS:
            raise RegisteredStepFailed(RegRetryableStep.devicecheck_write, retryable=True)
        return "confirmed"

    outcome = retry_registered_step(RegRetryableStep.devicecheck_write, flaky)
    assert outcome.value == "confirmed"
    assert outcome.attempts == 3
    assert attempts == [1, 2, 3]
    # No step is attempted more than three times, and only budgeted steps are retried.
    with pytest.raises(GrantFailureError):
        retry_registered_step(RegRetryableStep.devicecheck_read, flaky, attempts=4)
    with pytest.raises(GrantFailureError):
        retry_registered_step("activation", flaky)  # type: ignore[arg-type]


# [utest->req~grants-reg-retry-budget-exhausted~1]
def test_an_exhausted_retry_budget_rejects_temporarily_and_creates_no_grant():
    calls: list[int] = []

    def always_failing(attempt: int) -> str:
        calls.append(attempt)
        raise RegisteredStepFailed(RegRetryableStep.device_recall_read, retryable=True)

    with pytest.raises(ClaimRejection) as rejected:
        retry_registered_step(RegRetryableStep.device_recall_read, always_failing)
    assert calls == [1, 2, 3]
    assert rejected.value.result is AuthEventResult.native_claim_unavailable
    assert rejected.value.error_code == ClientErrorClass.verification_temporarily_unavailable
    # The Firebase confirmation's own budget audits its own dependency result.
    firebase = registered_retry_budget_exhausted(RegRetryableStep.firebase_provider_data)
    assert firebase.result is AuthEventResult.firebase_lookup_unavailable
    # A spent budget never leaves a grant behind.
    with pytest.raises(GrantFailureError):
        registered_retry_budget_exhausted(RegRetryableStep.devicecheck_write, grants_written=1)


# [utest->req~grants-reg-non-retryable-immediate~1]
def test_the_non_retryable_rejections_reject_immediately_and_spend_no_budget():
    assert NON_RETRYABLE_RESULTS == frozenset({
        AuthEventResult.idp_account_not_eligible,
        AuthEventResult.idp_account_already_claimed,
        AuthEventResult.registered_grant_destination_incompatible,
        AuthEventResult.policy_rejected})
    for result in NON_RETRYABLE_RESULTS:
        attempts: list[int] = []

        def rejecting(attempt: int, result: AuthEventResult = result) -> str:
            attempts.append(attempt)
            raise RegisteredStepFailed(RegRetryableStep.devicecheck_read, retryable=False,
                                       result=result)

        with pytest.raises(RegisteredStepFailed):
            retry_registered_step(RegRetryableStep.devicecheck_read, rejecting)
        assert attempts == [1]
        with pytest.raises(GrantFailureError):
            assert_non_retryable_immediate(result, attempts_spent=2)
    assert_non_retryable_immediate(AuthEventResult.native_claim_unavailable, attempts_spent=3)


# [utest->req~grants-reg-retry-no-duplicate-rows~1]
def test_retries_insert_no_duplicate_rows_and_are_not_bounded_by_challenge_expiry():
    assert_registered_retries_write_once(attempts=3, grants_inserted=1, anti_abuse_inserted=1,
                                        destination_mutations=1, elapsed_seconds=120.0)
    for grants, anti_abuse in ((2, 1), (1, 2)):
        with pytest.raises(GrantFailureError):
            assert_registered_retries_write_once(attempts=3, grants_inserted=grants,
                                                anti_abuse_inserted=anti_abuse,
                                                destination_mutations=1)
    with pytest.raises(GrantFailureError):
        assert_registered_retries_write_once(attempts=1, grants_inserted=1,
                                            anti_abuse_inserted=1, destination_mutations=2)
    # Expiry was evaluated once, at the claim: a retry neither lengthens nor is bounded by it.
    with pytest.raises(GrantFailureError):
        assert_registered_retries_write_once(attempts=2, grants_inserted=0,
                                            anti_abuse_inserted=0, destination_mutations=0,
                                            expiry_extended=True)
    with pytest.raises(GrantFailureError):
        assert_registered_retries_write_once(attempts=2, grants_inserted=0,
                                            anti_abuse_inserted=0, destination_mutations=0,
                                            expiry_evaluations=2)


# [utest->req~grants-reg-write-failure-pre-activation~1]
def test_a_registered_bit_write_failure_refuses_before_activation():
    # A failed, ambiguous or unattempted write permits no grant row.
    for write in (FAILED_WRITE, None):
        with pytest.raises(DeviceBitWriteError):
            registered_write_failure(write)
    # And the backend never grants around it or reconciles vendor state from the database.
    with pytest.raises(GrantFailureError):
        registered_write_failure(FAILED_WRITE, grants_written=1)
    with pytest.raises(GrantFailureError):
        registered_write_failure(FAILED_WRITE, reconciled_from_database=True)
    # A confirmed write whose activation never happened burns the slot: the remedy is `manual`.
    assert registered_write_failure(CONFIRMED_WRITE).value == "manual"
    # A client retry is a whole new claim: fresh vendor material, a fresh operation challenge,
    # and a grant row that hangs on the new attempt's own confirmed write.
    assert registered_retry_is_whole_new_claim("fresh-token", previous_material="stale-token",
                                              challenge_id="challenge-2",
                                              previous_challenge_id="challenge-1",
                                              write=CONFIRMED_WRITE) == "fresh-token"
    with pytest.raises(GrantFailureError):
        registered_retry_is_whole_new_claim("fresh-token", previous_material="stale-token",
                                           challenge_id="challenge-1",
                                           previous_challenge_id="challenge-1",
                                           write=CONFIRMED_WRITE)
    with pytest.raises(DeviceBitWriteError):
        registered_retry_is_whole_new_claim("fresh-token", previous_material="stale-token",
                                           challenge_id="challenge-2",
                                           previous_challenge_id="challenge-1",
                                           write=FAILED_WRITE)


# [utest->req~grants-reg-durable-rejection-no-alternate~1]
def test_a_durable_registered_rejection_promises_no_alternate_free_path():
    assert DURABLE_REGISTERED_CLASSES == frozenset({ClientErrorClass.verification_required,
                                                    ClientErrorClass.account_already_claimed})
    for client_class in DURABLE_REGISTERED_CLASSES:
        alternate, continuations = registered_durable_rejection(client_class)
        assert alternate is None
        assert continuations == PAID_CONTINUATIONS == ("active_subscription",
                                                       "non_free_entitlement")
    # A transient failure is no durable rejection.
    with pytest.raises(GrantFailureError):
        registered_durable_rejection(ClientErrorClass.verification_temporarily_unavailable)


# --- The registered alternate path for anonymous grant closure -------------------------------------


# [utest->req~grants-alt-cond-device-state-set~1]
def test_an_already_set_anonymous_device_state_closes_the_path_and_names_the_alternate():
    for kind in (ClaimBranch.native_ios, ClaimBranch.native_android):
        result, client_class = device_state_set_closure(kind)
        assert result is AuthEventResult.native_claim_already_claimed
        assert client_class is ClientErrorClass.device_grant_exhausted
    # Web carries no per-device anonymous-claimed state.
    with pytest.raises(GrantFailureError):
        device_state_set_closure(ClaimBranch.web)


# [utest->req~grants-alt-cond-web-stored-binding~1]
def test_the_web_alternate_path_needs_a_confirmed_stored_binding():
    row = google_row()
    assert web_stored_binding_closure(row, classifier_passed=True, live_provider_matches=True,
                                     live_uid_matches=True) \
        is ClientErrorClass.device_grant_exhausted
    # An empty, invalid-shape or mismatching result follows the durable sign-in-gate path
    # instead of the duplicate branch.
    for kwargs in ({"classifier_passed": False, "live_provider_matches": True,
                    "live_uid_matches": True},
                   {"classifier_passed": True, "live_provider_matches": False,
                    "live_uid_matches": True},
                   {"classifier_passed": True, "live_provider_matches": True,
                    "live_uid_matches": False}):
        assert web_stored_binding_closure(row, **kwargs) \
            is ClientErrorClass.verification_required
    anonymous = google_row(provider=IdentityProvider.anonymous, provider_uid=None)
    assert web_stored_binding_closure(anonymous, classifier_passed=True,
                                     live_provider_matches=True, live_uid_matches=True) \
        is ClientErrorClass.verification_required


# [utest->req~grants-alt-cond-web-gate-conflict~1]
def test_a_web_gate_conflict_is_audited_as_consumed_and_surfaces_as_exhausted():
    result, client_class = web_gate_conflict_closure()
    assert result is AuthEventResult.anti_abuse_already_claimed
    assert client_class is ClientErrorClass.device_grant_exhausted
    # It keeps its own internal result, distinct from the per-device block's.
    assert result is not AuthEventResult.native_claim_already_claimed


# [utest->req~grants-alt-cond-no-qualifying-native-evidence~1]
def test_absent_qualifying_native_evidence_names_the_registered_path_as_the_alternate():
    client_class, operation = no_qualifying_native_evidence()
    assert client_class is ClientErrorClass.proof_rejected
    assert operation is AuthOperation.claim_registered_grant


# [utest->req~grants-alt-cond-other-durable-rejections~1]
def test_other_durable_anonymous_rejections_carry_no_guarantee():
    for condition in (AnonFailureCondition.anonymous_grant_policy_rejected,
                      AnonFailureCondition.cloudflare_bot_check_denied,
                      AnonFailureCondition.device_check_read_denied):
        client_class, guaranteed = other_durable_closure(condition)
        assert client_class is ClientErrorClass.verification_required
        assert guaranteed is False
    # A transient dependency failure is not a durable closure at all.
    with pytest.raises(GrantFailureError):
        other_durable_closure(AnonFailureCondition.devicecheck_read_unavailable)


# [utest->req~grants-remediation-exhausted-or-no-anonymous-path~1]
def test_the_remediation_for_an_exhausted_or_absent_anonymous_path():
    remediation = exhausted_or_no_anonymous_path_remediation()
    assert remediation.claim_route == "/auth/claim-registered-grant"
    assert not remediation.retry_anonymous_claim
    assert not remediation.guaranteed
    assert anonymous_remediation(ClientErrorClass.device_grant_exhausted).durably_closed
    operation, route = alternate_path()
    assert (operation, route) == (AuthOperation.claim_registered_grant,
                                 "/auth/claim-registered-grant")


# [utest->req~grants-alt-remediation-obtain-linked-identity~1]
def test_the_client_obtains_a_google_or_apple_identity_then_calls_the_registered_claim():
    remediation = exhausted_or_no_anonymous_path_remediation()
    assert remediation.obtain_identity_by == ("sign_in", "create", "upgrade", "link")
    assert remediation.claim_route == route_for(AuthOperation.claim_registered_grant)[1]


# [utest->req~grants-alt-remediation-upgrade-in-place~1]
def test_upgrade_anonymous_is_an_in_place_flip_not_a_retire_and_attach():
    remediation = exhausted_or_no_anonymous_path_remediation()
    assert remediation.upgrade_in_place
    assert remediation.upgrade_route == route_for(
        AuthOperation.upgrade_anonymous_to_registered)[1]
    anonymous = google_row(provider=IdentityProvider.anonymous, provider_uid=None,
                           native_claim_platform=NativeClaimPlatform.ios_devicecheck)
    flipped = upgrade_in_place_flip(anonymous, provider=IdentityProvider.google,
                                   provider_uid="google-account-9")
    # The same Firebase UID and the same internal identity row.
    assert (flipped.id, flipped.issuer, flipped.subject) == (anonymous.id, anonymous.issuer,
                                                             anonymous.subject)
    assert flipped.user_id == anonymous.user_id
    assert flipped.provider is IdentityProvider.google
    # It mints no grant and touches no device state.
    with pytest.raises(Exception):
        upgrade_in_place_flip(anonymous, provider=IdentityProvider.google,
                              provider_uid="google-account-9", grants_minted=["free_credit"])


# [utest->req~grants-alt-remediation-create-user~1]
def test_create_user_makes_a_net_new_registered_identity_when_there_is_none_to_upgrade():
    remediation = exhausted_or_no_anonymous_path_remediation()
    assert remediation.create_user_route == route_for(AuthOperation.create_user)[1]
    # The route serves the registered variants, so it can produce a net-new registered identity.
    assert set(variants_for(AuthOperation.create_user)) >= {IdentityProvider.google,
                                                           IdentityProvider.apple}


# [utest->req~grants-alt-remediation-call-registered-grant~1]
def test_the_remediation_ends_at_the_registered_claim_endpoint():
    remediation = exhausted_or_no_anonymous_path_remediation()
    assert remediation.claim_route == "/auth/claim-registered-grant"
    assert anonymous_remediation(
        ClientErrorClass.device_grant_exhausted).alternate_operation \
        is AuthOperation.claim_registered_grant


# [utest->req~grants-alt-remediation-no-retry~1]
def test_the_client_must_not_retry_the_anonymous_claim_under_the_same_condition():
    assert not exhausted_or_no_anonymous_path_remediation().retry_anonymous_claim
    assert not anonymous_remediation(ClientErrorClass.device_grant_exhausted).retry_same_endpoint
    assert anonymous_remediation(ClientErrorClass.device_grant_exhausted).durably_closed


# [utest->req~grants-alt-guarantee-registered-gates~1]
def test_the_registered_path_is_a_path_with_its_own_gates_not_a_guarantee():
    gates = registered_path_gates()
    assert gates == ("stored_google_or_apple_identity",
                     "stored_provider_uid_confirmed_by_provider_data",
                     "registered_gate_unconsumed_for_provider_account",
                     "account_own_grant_history",
                     "active_linked_user",
                     "no_incompatible_active_grant")
    assert not exhausted_or_no_anonymous_path_remediation().guaranteed


# [utest->req~grants-alt-guarantee-no-transient-as-exhausted~1]
def test_a_transient_failure_is_never_surfaced_as_device_grant_exhausted():
    for condition in (AnonFailureCondition.devicecheck_read_unavailable,
                      AnonFailureCondition.cloudflare_dependency_failed,
                      AnonFailureCondition.firebase_provider_data_unavailable):
        assert assert_no_transient_as_exhausted(condition) \
            is ClientErrorClass.verification_temporarily_unavailable
    # Only an independently observed durable state denies the grant that way.
    assert assert_no_transient_as_exhausted(
        AnonFailureCondition.devicecheck_read_unavailable,
        durable_state_observed=True) is ClientErrorClass.device_grant_exhausted
    with pytest.raises(GrantFailureError):
        assert_no_transient_as_exhausted(AnonFailureCondition.web_gate_already_consumed)


def test_the_registered_claim_rejection_helper_stays_inside_the_declared_classes():
    from nativespeaker.api.auth.registered_grant_failures import registered_claim_rejected
    rejected = registered_claim_rejected(AuthEventResult.idp_account_not_eligible)
    assert rejected.error_code == "verification_required"
    assert rejected.status_code == 403
    with pytest.raises(FreeGrantError):
        registered_claim_rejected(AuthEventResult.identity_already_linked)
