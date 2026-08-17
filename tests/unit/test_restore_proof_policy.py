"""Restore's accepted bearer-credential property, its mitigations, and the entitlement behaviour
built on the verified store result."""

from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import REDACTED, AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.invariants import DevicePlatform, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_endpoints import RestoreRejected
from nativespeaker.api.auth.proof_restore import InvalidRestoreProof, VerifiedStoreProof
from nativespeaker.api.auth.restore import RestoreContractError, RestoreRejection
from nativespeaker.api.auth.restore_proof_policy import (
    BEARER_MITIGATIONS,
    BEARER_PRECONDITIONS,
    ENTITLEMENT_REPORTED_BY,
    FORBIDDEN_PROOF_SINKS,
    PROOF_RULES_OWNER,
    REPAIR_OPERATOR_ACTIONS,
    RESTORE_ABUSE_CONTROLS,
    SOURCE_UNRETIRE_PATHS,
    WEB_ATTESTATION_SURFACES,
    BindingOutcome,
    RestoreProofPolicyError,
    assert_bearer_mitigations,
    assert_proof_not_persisted,
    assert_proof_set_is_not_subscriber_identity,
    audit_safe_proof_details,
    bearer_credential_authorizes,
    bind_store_transaction,
    manual_binding_repair,
    manual_grant_source_produces,
    proof_rule_owner,
    reconcile_to_store,
    restore_abuse_controls,
    restore_calls_needed,
    store_side_verification,
    verify_store_artifact,
)

BOUND = uuid7()
OTHER = uuid7()
EXTERNAL_ID = "2000000123456789"
JWS = "signed.storekit.transaction"
APPLE_CHECKS = ("jws_certificate_chain", "bundle_id", "product_id", "environment")
PLAY_CHECKS = ("package_name", "product", "subscription_state")


def fake_verifier(provider: StoreProvider, artifact: str) -> VerifiedStoreProof:
    del artifact
    return VerifiedStoreProof(provider=provider, external_id=EXTERNAL_ID,
                              purchase_uuid=uuid7())


class TestStoreSideVerification:

    def test_apple_verification_is_the_documented_call_and_checks(self):
        # [utest->req~restore-proof-set-store-side-verification~1]
        call = store_side_verification(StoreProvider.apple, performed_checks=APPLE_CHECKS)
        assert call.api == "app_store_server_api.get_transaction_info"
        assert call.checks == APPLE_CHECKS

    def test_google_verification_is_the_documented_call_and_checks(self):
        # [utest->req~restore-proof-set-store-side-verification~1]
        call = store_side_verification(StoreProvider.google_play, performed_checks=PLAY_CHECKS)
        assert call.api == "play_developer_api.purchases.subscriptionsv2.get"
        assert call.checks == PLAY_CHECKS

    @pytest.mark.parametrize("dropped", APPLE_CHECKS)
    def test_a_skipped_store_check_rejects_the_proof(self, dropped):
        """Bundle ID, product ID and environment are ordinary store checks that must all run."""
        # [utest->req~restore-proof-set-store-side-verification~1]
        remaining = [check for check in APPLE_CHECKS if check != dropped]
        with pytest.raises(InvalidRestoreProof):
            store_side_verification(StoreProvider.apple, performed_checks=remaining)

    def test_verification_runs_against_the_store_not_the_device(self):
        # [utest->req~restore-proof-set-store-side-verification~1]
        with pytest.raises(RestoreProofPolicyError):
            store_side_verification(StoreProvider.apple, performed_checks=APPLE_CHECKS,
                                    target="device")

    def test_verified_artifact_resolves_the_store_subscription(self):
        # [utest->req~restore-proof-set-store-side-verification~1]
        verified = verify_store_artifact(DevicePlatform.ios, {"restore_proof": JWS},
                                        fake_verifier, performed_checks=APPLE_CHECKS)
        assert verified.provider is StoreProvider.apple
        assert verified.external_id == EXTERNAL_ID

    def test_web_platform_never_reaches_store_verification(self):
        # [utest->req~restore-proof-set-store-side-verification~1]
        with pytest.raises(RestoreRejected):
            verify_store_artifact(DevicePlatform.web, {"restore_proof": JWS},
                                  fake_verifier, performed_checks=APPLE_CHECKS)

    def test_the_proof_file_owns_the_proof_rules(self):
        assert proof_rule_owner("not_ownership_proof") == PROOF_RULES_OWNER
        assert proof_rule_owner("bearer_credential_property") \
            == "04-subscription-restore-and-entitlement-transfer.md"


class TestBearerCredentialProperty:

    def test_holder_of_a_valid_proof_can_attach_the_entitlement_once(self):
        # [utest->req~restore-proof-bearer-credential-accepted~1]
        assert bearer_credential_authorizes(satisfied=BEARER_PRECONDITIONS,
                                            restore_bound_user_id=None,
                                            destination_user_id=BOUND) is BindingOutcome.bound

    @pytest.mark.parametrize("dropped", BEARER_PRECONDITIONS)
    def test_every_precondition_still_applies(self, dropped):
        """The accepted property does not excuse any precondition in this document."""
        # [utest->req~restore-proof-bearer-credential-accepted~1]
        satisfied = [name for name in BEARER_PRECONDITIONS if name != dropped]
        with pytest.raises(RestoreProofPolicyError):
            bearer_credential_authorizes(satisfied=satisfied, restore_bound_user_id=None,
                                         destination_user_id=BOUND)

    def test_an_unregistered_caller_is_refused(self):
        # [utest->req~restore-proof-bearer-credential-accepted~1]
        with pytest.raises(RestoreContractError):
            bearer_credential_authorizes(satisfied=BEARER_PRECONDITIONS,
                                         restore_bound_user_id=None,
                                         destination_user_id=BOUND,
                                         destination_registered=False)

    def test_a_proof_for_an_already_linked_transaction_moves_nothing(self):
        # [utest->req~restore-proof-bearer-credential-accepted~1]
        with pytest.raises(RestoreRejection) as caught:
            bearer_credential_authorizes(satisfied=BEARER_PRECONDITIONS,
                                         restore_bound_user_id=OTHER,
                                         destination_user_id=BOUND)
        assert caught.value.result is AuthEventResult.store_transaction_already_linked


class TestBearerMitigations:

    def test_the_four_mitigations_are_exactly_these(self):
        # [utest->req~restore-proof-bearer-mitigations~1]
        assert assert_bearer_mitigations() == (
            "store_side_proof_verification",
            "lifetime_store_transaction_to_account_binding",
            "one_active_grant_per_user",
            "gateway_and_backend_admission_limits")

    @pytest.mark.parametrize("claimed", ["device_attestation", "app_attest",
                                         "play_integrity", "devicecheck"])
    def test_device_attestation_is_not_a_mitigation(self, claimed):
        # [utest->req~restore-proof-bearer-mitigations~1]
        with pytest.raises(RestoreProofPolicyError):
            assert_bearer_mitigations([*BEARER_MITIGATIONS, claimed])

    @pytest.mark.parametrize("dropped", BEARER_MITIGATIONS)
    def test_no_mitigation_may_go_missing(self, dropped):
        # [utest->req~restore-proof-bearer-mitigations~1]
        with pytest.raises(RestoreProofPolicyError):
            assert_bearer_mitigations([name for name in BEARER_MITIGATIONS if name != dropped])


class TestSecretBearerMaterial:

    @pytest.mark.parametrize("sink", sorted(FORBIDDEN_PROOF_SINKS))
    def test_raw_proof_reaches_no_durable_sink(self, sink):
        # [utest->req~restore-proof-secret-bearer-material~1]
        with pytest.raises(RestoreProofPolicyError):
            assert_proof_not_persisted(sink)

    def test_the_verification_call_is_the_only_permitted_path(self):
        # [utest->req~restore-proof-secret-bearer-material~1]
        assert assert_proof_not_persisted("store_verification_call") == "store_verification_call"

    def test_only_fingerprints_and_outcomes_are_persisted(self):
        # [utest->req~restore-proof-secret-bearer-material~1]
        details = audit_safe_proof_details(fingerprints=("sha256:abc",), outcome="adoption")
        assert details["verification"]["proof_fingerprints"] == ["sha256:abc"]
        assert details["mutation"]["restore_outcome"] == "adoption"

    def test_raw_proof_never_reaches_an_audit_row(self):
        # [utest->req~restore-proof-secret-bearer-material~1]
        with pytest.raises(RestoreProofPolicyError):
            audit_safe_proof_details(fingerprints=("sha256:abc",), outcome="adoption",
                                     raw_proof=JWS)

    def test_a_fingerprint_carrying_raw_material_is_refused(self):
        """A signed payload smuggled in as a fingerprint would be redacted, so it is refused."""
        # [utest->req~restore-proof-secret-bearer-material~1]
        with pytest.raises(RestoreProofPolicyError):
            audit_safe_proof_details(fingerprints=("eyJhbGci.eyJzdWIi.c2lnbg",),
                                     outcome="adoption")
        assert REDACTED == "[redacted]"


class TestNotSubscriberIdentity:

    def test_the_proof_set_proves_no_prior_ownership(self):
        # [utest->req~restore-proof-set-not-subscriber-identity~1]
        assert assert_proof_set_is_not_subscriber_identity() is None
        with pytest.raises(RestoreProofPolicyError):
            assert_proof_set_is_not_subscriber_identity(claimed_proof_of=["original_subscriber"])
        with pytest.raises(RestoreProofPolicyError):
            assert_proof_set_is_not_subscriber_identity(
                claimed_proof_of=["current_source_account_owner"])

    def test_a_repeat_into_the_bound_account_is_idempotent_success(self):
        # [utest->req~restore-proof-set-not-subscriber-identity~1]
        assert bind_store_transaction(restore_bound_user_id=BOUND,
                                      destination_user_id=BOUND) is BindingOutcome.idempotent

    def test_a_repeat_aimed_elsewhere_rejects(self):
        # [utest->req~restore-proof-set-not-subscriber-identity~1]
        with pytest.raises(RestoreRejection) as caught:
            bind_store_transaction(restore_bound_user_id=BOUND, destination_user_id=OTHER)
        assert caught.value.result is AuthEventResult.store_transaction_already_linked


class TestLifetimeBinding:

    def test_the_first_successful_restore_sets_the_binding(self):
        # [utest->req~restore-lifetime-transaction-account-binding~1]
        assert bind_store_transaction(restore_bound_user_id=None,
                                      destination_user_id=BOUND) is BindingOutcome.bound

    def test_re_restoring_into_the_same_account_is_idempotent(self):
        # [utest->req~restore-lifetime-transaction-account-binding~1]
        assert bind_store_transaction(restore_bound_user_id=BOUND,
                                      destination_user_id=BOUND) is BindingOutcome.idempotent

    def test_a_different_destination_rejects_and_is_never_re_linked(self):
        # [utest->req~restore-lifetime-transaction-account-binding~1]
        with pytest.raises(RestoreRejection) as caught:
            bind_store_transaction(restore_bound_user_id=BOUND, destination_user_id=OTHER)
        assert caught.value.result is AuthEventResult.store_transaction_already_linked

    def test_silently_re_linking_is_not_available(self):
        # [utest->req~restore-lifetime-transaction-account-binding~1]
        with pytest.raises(RestoreContractError):
            bind_store_transaction(restore_bound_user_id=BOUND, destination_user_id=OTHER,
                                   relink=True)


class TestStoreVerificationIsGroundTruth:

    def test_missing_rows_are_created_rather_than_rejected(self):
        # [utest->req~restore-store-verification-is-ground-truth~1]
        assert reconcile_to_store(store_verified=True, subscription_row_exists=False,
                                  purchase_row_exists=False,
                                  inside_locked_transaction=True) == (
            "core.subscriptions", "core.store_purchases")

    def test_an_absent_purchase_uuid_is_no_rejection(self):
        # [utest->req~restore-store-verification-is-ground-truth~1]
        assert reconcile_to_store(store_verified=True, subscription_row_exists=True,
                                  purchase_row_exists=True, inside_locked_transaction=True,
                                  carried_purchase_uuid=None,
                                  recorded_identity_value="token-1") == ()

    def test_only_a_failed_store_verification_rejects_for_proof_reasons(self):
        # [utest->req~restore-store-verification-is-ground-truth~1]
        # The split between "the row is missing" and "the proof failed verification" is
        # `restore_flow.missing_purchase_row_path`'s, so this takes that one audited outcome.
        with pytest.raises(RestoreRejection) as refused:
            reconcile_to_store(store_verified=False, subscription_row_exists=True,
                               purchase_row_exists=True, inside_locked_transaction=True)
        assert refused.value.result is AuthEventResult.invalid_restore_proof

    def test_a_differing_carried_uuid_still_rejects(self):
        # [utest->req~restore-store-verification-is-ground-truth~1]
        with pytest.raises(RestoreRejection) as caught:
            reconcile_to_store(store_verified=True, subscription_row_exists=True,
                               purchase_row_exists=True, inside_locked_transaction=True,
                               carried_purchase_uuid="token-2",
                               recorded_identity_value="token-1")
        assert caught.value.result is AuthEventResult.restore_purchase_uuid_mismatch

    def test_creation_happens_inside_the_locked_mutation_transaction(self):
        # [utest->req~restore-store-verification-is-ground-truth~1]
        with pytest.raises(RestoreContractError):
            reconcile_to_store(store_verified=True, subscription_row_exists=False,
                               purchase_row_exists=True, inside_locked_transaction=False)


class TestLinkedSubscriptionNeedsNoSecondRestore:

    def test_an_already_linked_purchase_needs_no_further_restore(self):
        # [utest->req~restore-linked-subscription-needs-no-second-restore~1]
        assert restore_calls_needed(subscription_user_id=BOUND, signed_in_user_id=BOUND) == 0
        assert ENTITLEMENT_REPORTED_BY is AuthOperation.sync

    def test_an_unclaimed_or_other_account_subscription_still_needs_one(self):
        # [utest->req~restore-linked-subscription-needs-no-second-restore~1]
        assert restore_calls_needed(subscription_user_id=None, signed_in_user_id=BOUND) == 1
        assert restore_calls_needed(subscription_user_id=OTHER, signed_in_user_id=BOUND) == 1


class TestManualBindingRepair:

    def test_the_repair_returns_the_row_to_the_unclaimed_shape(self):
        # [utest->req~restore-manual-binding-repair~1]
        transaction = object()
        repaired = manual_binding_repair(prior_grant_active=True, transaction=transaction,
                                         grant_transaction=transaction)
        assert repaired.user_id is None
        assert repaired.restore_bound_user_id is None

    @pytest.mark.parametrize("touched", ["grant_user_id", "store_purchases_row",
                                         "purchase_user_id", "terminal_grant_rows",
                                         "source_identity_row", "source_block_or_retirement",
                                         "firebase_refresh_token_revocation"])
    def test_the_repair_leaves_everything_else_exactly_as_it_is(self, touched):
        # [utest->req~restore-manual-binding-repair~1]
        with pytest.raises(RestoreProofPolicyError):
            manual_binding_repair(prior_grant_active=False, transaction=object(),
                                  touched=[touched])

    def test_the_repair_runs_in_one_transaction(self):
        # [utest->req~restore-manual-binding-repair~1]
        with pytest.raises(RestoreProofPolicyError):
            manual_binding_repair(prior_grant_active=True, transaction=object(),
                                  grant_transaction=object())

    def test_no_reattachment_action_and_no_revival_path_exist(self):
        # [utest->req~restore-manual-binding-repair~1]
        assert REPAIR_OPERATOR_ACTIONS == frozenset()
        assert SOURCE_UNRETIRE_PATHS == frozenset()

    def test_the_manual_grant_source_produces_a_grant_not_subscription_state(self):
        # [utest->req~restore-manual-binding-repair~1]
        assert manual_grant_source_produces(AccessGrantSource.manual) == "core.access_grants"
        with pytest.raises(RestoreProofPolicyError):
            manual_grant_source_produces(AccessGrantSource.subscription)


class TestAbuseThrottling:

    def test_throttling_stays_with_the_existing_limits(self):
        # [utest->req~restore-abuse-throttling-existing-limits~1]
        assert restore_abuse_controls() == ("gateway_admission_limits",
                                            "backend_restore_admission_control")

    @pytest.mark.parametrize("added", ["webauthn", "browser_integrity_signal",
                                       "restore_from_web_with_receipt_alone"])
    def test_no_new_mechanism_or_web_attestation_surface_is_added(self, added):
        # [utest->req~restore-abuse-throttling-existing-limits~1]
        with pytest.raises(RestoreProofPolicyError):
            restore_abuse_controls(added=[added])
        assert WEB_ATTESTATION_SURFACES == frozenset()
        assert RESTORE_ABUSE_CONTROLS == ("gateway_admission_limits",
                                          "backend_restore_admission_control")
