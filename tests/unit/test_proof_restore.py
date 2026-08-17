"""Restore proof: the store artifact, server-verified, and nothing else."""

from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.invariants import DevicePlatform, ProofUse
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_endpoints import (
    ProofApplicabilityError,
    ProofArtifact,
    RestoreRejected,
)
from nativespeaker.api.auth.proof_restore import (
    InvalidRestoreProof,
    RestoreProofError,
    StoreProvider,
    VerifiedStoreProof,
    assert_no_attestation_linkage,
    assert_not_challenge_bearing,
    assert_not_ownership_proof,
    assert_not_parameterized_by_recovery_material,
    assert_server_verifiable,
    live_store_verification_owner,
    restore_data_movement,
    restore_entire_proof_set,
    store_artifact_resolution_key,
    verify_restore_proof,
)

PURCHASE_UUID = UUID("0198f000-0000-7000-8000-000000000001")


def verifier(provider: StoreProvider, artifact: str) -> VerifiedStoreProof:
    return VerifiedStoreProof(provider=provider, external_id=f"{provider}:{artifact}",
                              purchase_uuid=PURCHASE_UUID)


def empty_verifier(provider: StoreProvider, artifact: str) -> VerifiedStoreProof:
    return VerifiedStoreProof(provider=provider, external_id="", purchase_uuid=PURCHASE_UUID)


# [utest->req~proof-restore-server-verifiable-store-proof~1]
def test_restore_proof_must_be_server_verifiable_store_proof():
    assert assert_server_verifiable("signed-transaction") == "signed-transaction"
    with pytest.raises(RestoreProofError):
        assert_server_verifiable("signed-transaction", verified_by="client_asserted_receipt")
    with pytest.raises(InvalidRestoreProof):
        assert_server_verifiable(None)
    with pytest.raises(InvalidRestoreProof):
        assert_server_verifiable("   ")


# [utest->req~proof-restore-not-challenge-bearing~1]
def test_restore_is_not_challenge_bearing():
    assert_not_challenge_bearing()
    with pytest.raises(RestoreProofError):
        assert_not_challenge_bearing(challenge_id="c-1")
    with pytest.raises(RestoreProofError):
        assert_not_challenge_bearing(AuthOperation.restore_subscription, challenge_id="c-1")


# [utest->req~proof-restore-server-side-verification~1]
def test_the_server_verifies_the_artifact_and_uses_the_result_only_for_entitlement():
    verified = verify_restore_proof(DevicePlatform.ios, "signed-transaction", verifier)
    assert verified.provider is StoreProvider.apple
    assert verified.purchase_uuid == PURCHASE_UUID
    android = verify_restore_proof(DevicePlatform.android, "purchase-token", verifier)
    assert android.provider is StoreProvider.google_play
    with pytest.raises(RestoreProofError):
        verify_restore_proof(DevicePlatform.ios, "signed-transaction", verifier,
                             used_for="anonymous_identity_recovery")
    with pytest.raises(RestoreRejected):
        verify_restore_proof(DevicePlatform.web, "anything", verifier)
    with pytest.raises(InvalidRestoreProof):
        verify_restore_proof(DevicePlatform.ios, "signed-transaction", empty_verifier)


# [utest->req~proof-restore-store-artifact-entire-proof-set~1]
def test_the_store_artifact_is_the_entire_proof_set():
    assert restore_entire_proof_set(DevicePlatform.ios, artifact="signed-transaction") == {
        ProofArtifact.store_artifact}
    with pytest.raises(ProofApplicabilityError):
        restore_entire_proof_set(DevicePlatform.ios, artifact="signed-transaction",
                                 offered=[ProofArtifact.attestation_key_proof])
    with pytest.raises(ProofApplicabilityError):
        restore_entire_proof_set(DevicePlatform.ios, artifact="signed-transaction",
                                 offered=[ProofArtifact.devicecheck_query_token])
    with pytest.raises(RestoreRejected):
        restore_entire_proof_set(DevicePlatform.web, artifact="signed-transaction")


# [utest->req~proof-restore-not-parameterized-by-recovery-material~1]
def test_restore_takes_no_source_anonymous_recovery_material():
    assert_not_parameterized_by_recovery_material({"restore_proof": "signed-transaction"})
    for field in ("source_subject", "anonymous_uid", "recovery_token", "previous_identity",
                  "attestation_key_proof"):
        with pytest.raises(RestoreProofError):
            assert_not_parameterized_by_recovery_material({"restore_proof": "p", field: "x"})


# [utest->req~proof-restore-not-ownership-proof~1]
def test_restore_proof_is_not_proof_of_prior_account_ownership():
    assert_not_ownership_proof(ProofUse.anti_abuse_gate)
    for role in (ProofUse.ownership, ProofUse.identity, ProofUse.recovery, ProofUse.upgrade,
                 ProofUse.account_resolution):
        with pytest.raises(RestoreProofError):
            assert_not_ownership_proof(role)


# [utest->req~proof-restore-no-attestation-linkage~1]
def test_restore_implies_no_attestation_linkage():
    assert_no_attestation_linkage()
    with pytest.raises(ProofApplicabilityError):
        assert_no_attestation_linkage("attestation_key_recovery")
    with pytest.raises(ProofApplicabilityError):
        assert_no_attestation_linkage("attestation_key_upgrade")


# [utest->req~proof-restore-moves-no-app-data~1]
def test_restore_moves_no_app_data_and_keeps_usage_on_the_same_grant():
    grant_id = uuid7()
    moved = restore_data_movement(grant_id=grant_id, usage_row_grant_id=grant_id)
    assert moved.grant_id == grant_id
    for data in ("chats", "external_identity", "access_grants", "profile_fields"):
        with pytest.raises(RestoreProofError):
            restore_data_movement(grant_id=grant_id, usage_row_grant_id=grant_id, moved=[data])
    with pytest.raises(RestoreProofError):
        restore_data_movement(grant_id=grant_id, usage_row_grant_id=uuid7())


# [utest->req~proof-store-artifact-resolves-provider-external-id~1]
def test_verification_resolves_the_provider_and_external_id_key():
    verified = verify_restore_proof(DevicePlatform.android, "purchase-token", verifier)
    assert store_artifact_resolution_key(verified) == (StoreProvider.google_play,
                                                       "google_play:purchase-token")
    assert live_store_verification_owner().startswith("04-")
    with pytest.raises(RestoreProofError):
        store_artifact_resolution_key(VerifiedStoreProof(provider=StoreProvider.apple,
                                                         external_id="",
                                                         purchase_uuid=PURCHASE_UUID))
