"""`POST /auth/restore-subscription`: the endpoint contract and the registered destination."""

from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AttemptPhase, AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.external_identities import ExternalIdentityRow, IdentityError
from nativespeaker.api.auth.invariants import DevicePlatform, StoreProvider
from nativespeaker.api.auth.operations import (
    AdmissionRejection,
    AuthOperation,
    IdentityProvider,
    InvalidOperationVariantError,
)
from nativespeaker.api.auth.proof_endpoints import RestoreRejected
from nativespeaker.api.auth.restore import (
    BRANCH_ENDPOINTS,
    REGISTRATION_SUBSCRIPTION_RESERVATIONS,
    RESTORE_CHALLENGE_ROWS,
    RESTORE_METHOD,
    RESTORE_PATH,
    SURFACE_GATE_RESULTS,
    MovementClassification,
    RestoreAttemptAudit,
    RestoreAuditContext,
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
    anonymous_own_identity_row,
    assert_no_recovery_credential,
    assert_registered_destination,
    assert_restore_endpoint_contract,
    assert_restore_not_challenge_bearing,
    is_anonymous_account,
    movement_classification_for,
    native_only_surface_gate,
    registration_remediation_routes,
    require_store_proof,
    restore_admission_rejection_is_audited,
    restore_destination,
)

ISSUER = "https://securetoken.google.com/test-project"
USER = uuid7()
JWS = "signed.storekit.transaction"


def identity_row(provider: IdentityProvider = IdentityProvider.anonymous,
                 *, provider_uid: str | None = None) -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=USER, issuer=ISSUER, subject="sub-1",
                               provider=provider, provider_uid=provider_uid)


def linked_context(user_id=USER) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                   outcome=ResolutionOutcome.linked, user_id=user_id,
                                   external_identity_id=uuid7(),
                                   provider=IdentityProvider.google)


class TestEndpointContract:

    def test_route_performs_restore_subscription_only(self):
        # [utest->req~restore-endpoint-operation-and-branch-selection~1]
        assert (RESTORE_METHOD, RESTORE_PATH) == ("POST", "/auth/restore-subscription")
        assert assert_restore_endpoint_contract("POST", "/auth/restore-subscription") \
            is AuthOperation.restore_subscription
        # No other route performs it, and neither branch has an endpoint of its own.
        assert BRANCH_ENDPOINTS == frozenset()
        with pytest.raises(RestoreContractError):
            assert_restore_endpoint_contract("POST", "/auth/restore-subscription/adopt")
        with pytest.raises(RestoreContractError):
            assert_restore_endpoint_contract("POST", "/auth/sync")

    @pytest.mark.parametrize("field", ["transfer", "branch", "transfer_flag",
                                       "source_user_id", "destination_user_id"])
    def test_client_never_requests_the_branch(self, field):
        """The branch is a conclusion drawn from server state, not a request parameter."""
        # [utest->req~restore-endpoint-operation-and-branch-selection~1]
        # [utest->req~restore-branches-server-selected~1]
        with pytest.raises(RestoreContractError):
            assert_restore_endpoint_contract("POST", "/auth/restore-subscription",
                                             body={"restore_proof": JWS, field: "x"})

    def test_ordinary_body_is_accepted(self):
        # [utest->req~restore-branches-server-selected~1]
        assert assert_restore_endpoint_contract("POST", "/auth/restore-subscription",
                                                body={"restore_proof": JWS}) \
            is AuthOperation.restore_subscription


class TestNativeOnlySurfaceGate:

    def test_each_native_platform_fixes_its_store(self):
        # [utest->req~restore-native-only-surface-gate~1]
        assert native_only_surface_gate(DevicePlatform.ios,
                                        store_artifact=JWS) is StoreProvider.apple
        assert native_only_surface_gate(DevicePlatform.android,
                                        store_artifact="purchase-token") \
            is StoreProvider.google_play

    def test_web_call_is_operation_not_allowed_not_proof_rejected(self):
        """A web call has no store-artifact family: there is no proof to evaluate."""
        # [utest->req~restore-native-only-surface-gate~1]
        with pytest.raises(RestoreRejected) as caught:
            native_only_surface_gate(DevicePlatform.web, store_artifact=JWS)
        assert caught.value.error_code == "operation_not_allowed"
        assert caught.value.error_code != "proof_rejected"

    def test_cross_store_artifact_rejects_the_same_way(self):
        """One store's artifact presented from the other platform: same code, deterministically."""
        # [utest->req~restore-native-only-surface-gate~1]
        with pytest.raises(RestoreRejected) as first:
            native_only_surface_gate(DevicePlatform.ios,
                                     artifact_family="google_play_purchase_token",
                                     store_artifact="purchase-token")
        with pytest.raises(RestoreRejected) as second:
            native_only_surface_gate(DevicePlatform.android,
                                     artifact_family="signed_storekit_transaction",
                                     store_artifact=JWS)
        assert first.value.error_code == second.value.error_code == "operation_not_allowed"

    def test_no_native_artifact_family_presented(self):
        # [utest->req~restore-native-only-surface-gate~1]
        with pytest.raises(RestoreRejected):
            native_only_surface_gate(DevicePlatform.ios, store_artifact="   ")

    def test_gate_is_not_a_restore_internal_result(self):
        """The gate fires before restore's client error mapping, so it names no internal result."""
        # [utest->req~restore-native-only-surface-gate~1]
        assert SURFACE_GATE_RESULTS == frozenset()
        with pytest.raises(RestoreRejected) as caught:
            native_only_surface_gate(DevicePlatform.web, store_artifact=JWS)
        assert not isinstance(caught.value, RestoreRejection)


class TestRequestMaterial:

    def test_store_artifact_alone_is_the_proof(self):
        # [utest->req~restore-request-proof-store-artifact-only~1]
        assert require_store_proof(DevicePlatform.ios, {"restore_proof": JWS}) == JWS

    def test_missing_restore_proof_is_rejected(self):
        # [utest->req~restore-request-proof-store-artifact-only~1]
        # [utest->req~restore-single-audit-row-per-attempt~1]
        with pytest.raises(RestoreRejected):
            require_store_proof(DevicePlatform.ios, {})

    @pytest.mark.parametrize("field", ["app_attest_attestation", "play_integrity_token",
                                       "device_check_token"])
    def test_no_attestation_material_is_accepted(self, field):
        """No App Attest or Play Integrity proof is required or accepted on this endpoint."""
        # [utest->req~restore-request-proof-store-artifact-only~1]
        # [utest->req~restore-single-audit-row-per-attempt~1]
        with pytest.raises(RestoreRejection) as caught:
            require_store_proof(DevicePlatform.ios, {"restore_proof": JWS, field: "blob"})
        assert caught.value.result is AuthEventResult.invalid_restore_proof

    def test_no_prior_account_recovery_credential(self):
        """Restore is authorized by the verified ID token and store proof alone."""
        # [utest->req~restore-no-prior-account-recovery-credential~1]
        assert assert_no_recovery_credential({"restore_proof": JWS}) == (
            "backend_verified_id_token", "store_restore_proof")
        with pytest.raises(RestoreContractError):
            assert_no_recovery_credential({}, authorizers=("backend_verified_id_token",
                                                           "store_restore_proof",
                                                           "prior_account_recovery_code"))


class TestNotChallengeBearing:

    def test_restore_carries_no_challenge_at_all(self):
        # [utest->req~restore-not-challenge-bearing~1]
        # [utest->req~restore-proof-no-challenge-binding~2]
        assert RESTORE_CHALLENGE_ROWS == 0
        assert assert_restore_not_challenge_bearing() is None

    def test_prepare_phase_mode_signal_and_challenge_row_are_all_refused(self):
        # [utest->req~restore-not-challenge-bearing~1]
        with pytest.raises(RestoreContractError):
            assert_restore_not_challenge_bearing(prepare_phase=True)
        with pytest.raises(RestoreContractError):
            assert_restore_not_challenge_bearing(mode_signal="challenge")
        with pytest.raises(RestoreContractError):
            assert_restore_not_challenge_bearing(challenge_row_id=uuid7())

    def test_no_operation_variant(self):
        # [utest->req~restore-not-challenge-bearing~1]
        # [utest->req~restore-proof-no-challenge-binding~2]
        with pytest.raises(InvalidOperationVariantError):
            assert_restore_not_challenge_bearing(declared_variant="apple")


class TestRegisteredDestination:

    def test_destination_is_the_barrier_resolved_user(self):
        # [utest->req~restore-request-firebase-id-token~1]
        assert restore_destination(linked_context(), barrier_admitted=True) == USER

    def test_restore_logic_never_runs_before_the_barrier(self):
        # [utest->req~restore-request-firebase-id-token~1]
        with pytest.raises(RestoreContractError):
            restore_destination(linked_context(), barrier_admitted=False)
        with pytest.raises(RestoreContractError):
            restore_destination(linked_context(), barrier_admitted=True,
                                restore_logic_started=True)

    def test_an_unlinked_outcome_never_reaches_restore(self):
        # [utest->req~restore-request-firebase-id-token~1]
        context = VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                          outcome=ResolutionOutcome.pre_auth)
        with pytest.raises(RestoreContractError):
            restore_destination(context, barrier_admitted=True)

    def test_registered_destination_is_accepted(self):
        # [utest->req~restore-destination-must-be-registered~1]
        rows = [identity_row(IdentityProvider.google, provider_uid="g-1")]
        assert assert_registered_destination(destination_user_id=USER,
                                             identity_rows=rows) == USER

    def test_anonymous_destination_audits_as_restore_destination_anonymous(self):
        # [utest->req~restore-destination-must-be-registered~1]
        with pytest.raises(RestoreRejection) as caught:
            assert_registered_destination(destination_user_id=USER,
                                          identity_rows=[identity_row()])
        assert caught.value.result is AuthEventResult.restore_destination_anonymous

    def test_anonymous_destination_is_rejected_before_any_change(self):
        """Rejected before any ownership, grant, or cap change."""
        # [utest->req~restore-destination-must-be-registered~1]
        with pytest.raises(RestoreContractError):
            assert_registered_destination(destination_user_id=USER,
                                          identity_rows=[identity_row()],
                                          mutations_performed=("core.access_grants",))

    def test_backend_reads_stored_state_not_client_claims(self):
        """An old or modified client cannot declare itself registered."""
        # [utest->req~restore-destination-must-be-registered~1]
        with pytest.raises(RestoreContractError):
            assert_registered_destination(destination_user_id=USER,
                                          identity_rows=[identity_row()],
                                          client_declared_registered=True)

    def test_inactive_destination_is_refused(self):
        # [utest->req~restore-destination-must-be-registered~1]
        rows = [identity_row(IdentityProvider.google, provider_uid="g-1")]
        with pytest.raises(RestoreRejection):
            assert_registered_destination(destination_user_id=USER, identity_rows=rows,
                                          destination_active=False)

    def test_remediation_is_registration_then_retry(self):
        # [utest->req~restore-destination-must-be-registered~1]
        assert registration_remediation_routes() == (("POST", "/auth/upgrade-anonymous"),
                                                     ("POST", "/auth/create-user"))
        # Registration itself reserves nothing for the not-yet-registered destination.
        assert REGISTRATION_SUBSCRIPTION_RESERVATIONS == frozenset()


class TestAnonymousAccountDefinition:

    def test_anonymous_is_exactly_zero_provider_bearing_rows(self):
        # [utest->req~restore-anonymous-account-definition~1]
        assert is_anonymous_account([identity_row()]) is True
        assert is_anonymous_account([]) is True
        assert is_anonymous_account(
            [identity_row(IdentityProvider.google, provider_uid="g-1")]) is False
        assert is_anonymous_account(
            [identity_row(IdentityProvider.apple, provider_uid="a-1")]) is False

    def test_a_provider_bearing_row_alongside_anonymous_still_counts(self):
        # [utest->req~restore-anonymous-account-definition~1]
        rows = [identity_row(), identity_row(IdentityProvider.google, provider_uid="g-1")]
        assert is_anonymous_account(rows) is False

    def test_anonymous_account_holds_its_own_provider_less_row(self):
        # [utest->req~restore-anonymous-account-definition~1]
        row = anonymous_own_identity_row([identity_row()])
        assert row is not None
        assert row.provider is IdentityProvider.anonymous
        assert row.provider_uid is None
        assert anonymous_own_identity_row([]) is None

    def test_an_anonymous_row_with_a_provider_uid_is_refused(self):
        # [utest->req~restore-anonymous-account-definition~1]
        bad = ExternalIdentityRow(id=uuid7(), user_id=USER, issuer=ISSUER, subject="s",
                                  provider=IdentityProvider.anonymous)
        object.__setattr__(bad, "provider_uid", "sneaked-in")
        with pytest.raises(IdentityError):
            anonymous_own_identity_row([bad])


class TestSingleAuditRowPerAttempt:

    def test_movement_classification_follows_the_known_branch(self):
        # [utest->req~restore-single-audit-row-per-attempt~1]
        assert movement_classification_for(branch=RestoreBranch.same_account,
                                           result=AuthEventResult.succeeded) \
            is MovementClassification.same_account
        assert movement_classification_for(branch=RestoreBranch.adoption,
                                           result=AuthEventResult.succeeded) \
            is MovementClassification.adoption

    @pytest.mark.parametrize("branch,result", [
        (None, AuthEventResult.invalid_restore_proof),
        (RestoreBranch.same_account,
         AuthEventResult.restore_subscription_grant_owner_mismatch),
        (RestoreBranch.adoption, AuthEventResult.restore_branch_inconsistent),
        (RestoreBranch.same_account, AuthEventResult.store_transaction_already_linked),
    ])
    def test_unclassified_where_the_branch_is_unknowable_or_diverged(self, branch, result):
        # [utest->req~restore-single-audit-row-per-attempt~1]
        assert movement_classification_for(branch=branch, result=result) \
            is MovementClassification.unclassified

    def test_one_attempt_writes_exactly_one_row(self):
        # [utest->req~restore-single-audit-row-per-attempt~1]
        transaction = object()
        audit = RestoreAttemptAudit()
        event = audit.record(phase=AttemptPhase.success,
                             result=AuthEventResult.succeeded,
                             audit_transaction=transaction,
                             mutation_transaction=transaction,
                             branch=RestoreBranch.adoption,
                             context=RestoreAuditContext(destination_user_id=USER))
        assert event.operation is AuthOperation.restore_subscription
        assert event.details["mutation"]["movement_classification"] == "adoption"
        assert len(audit.rows) == 1
        with pytest.raises(RestoreContractError):
            audit.record(phase=AttemptPhase.success, result=AuthEventResult.succeeded,
                         audit_transaction=transaction)

    def test_a_mutating_attempt_audits_in_the_mutation_transaction(self):
        # [utest->req~restore-single-audit-row-per-attempt~1]
        with pytest.raises(RestoreContractError):
            RestoreAttemptAudit().record(phase=AttemptPhase.success,
                                         result=AuthEventResult.succeeded,
                                         audit_transaction=object(),
                                         mutation_transaction=object(),
                                         branch=RestoreBranch.adoption)

    def test_a_pre_transaction_rejection_audits_in_its_own_transaction(self):
        # [utest->req~restore-single-audit-row-per-attempt~1]
        audit = RestoreAttemptAudit()
        event = audit.record(phase=AttemptPhase.business,
                             result=AuthEventResult.invalid_restore_proof,
                             audit_transaction=object())
        assert event.details["mutation"]["movement_classification"] == "unclassified"
        with pytest.raises(RestoreContractError):
            RestoreAttemptAudit().record(phase=AttemptPhase.business,
                                         result=AuthEventResult.invalid_restore_proof,
                                         audit_transaction=None)

    def test_the_row_names_no_challenge(self):
        # [utest->req~restore-not-challenge-bearing~1]
        with pytest.raises(RestoreContractError):
            RestoreAttemptAudit().record(phase=AttemptPhase.success,
                                         result=AuthEventResult.succeeded,
                                         audit_transaction=object(),
                                         challenge_row_id=uuid7())

    def test_admission_control_rejections_write_no_row(self):
        # [utest->req~restore-single-audit-row-per-attempt~1]
        assert restore_admission_rejection_is_audited(
            AdmissionRejection.backend_rate_limited) is False
        assert restore_admission_rejection_is_audited(
            AdmissionRejection.gateway_rate_limited) is False
