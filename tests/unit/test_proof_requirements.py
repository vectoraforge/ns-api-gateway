"""What the user-creation and anonymous-continuity flows require as proof — and what they do not."""

from dataclasses import replace
from uuid import uuid7

import pytest

from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.external_identities import (
    ExternalIdentityRow,
    IdentityState,
    ProviderDataReadPoint,
)
from nativespeaker.api.auth.onboarding import AuthorizationHeaderSource
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_requirements import (
    ATTESTATION_PROOF_FLOWS,
    CREATE_USER_PROOF_MATERIAL,
    SPLIT_FLOWS,
    SYNC_DEVICE_STATE_ACCESS,
    SYNC_WRITES,
    DeviceCheckUse,
    ProofRequirementError,
    assert_device_check_use,
    assert_not_identity_material,
    create_user_proof_material,
    requires_attestation_proof,
    sync_request_credentials,
    upgrade_proof_basis,
)
from nativespeaker.api.auth.upgrade import UPGRADE_DEVICE_GRANT_BITS, UpgradeError
from nativespeaker.api.auth.users import UsersError
from unit.conftest import TEST_ISSUER

SUBJECT = "linked-subject"


def linked_row(provider: IdentityProvider = IdentityProvider.google,
               provider_uid: str | None = "google-account-id") -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=TEST_ISSUER, subject=SUBJECT,
                               provider=provider, provider_uid=provider_uid,
                               identity_state=IdentityState.active)


def linked_context(row: ExternalIdentityRow) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=row.issuer, subject=row.subject,
                                   outcome=ResolutionOutcome.linked, user_id=row.user_id,
                                   external_identity_id=row.id, provider=row.provider)


# [utest->req~users-no-attestation-proof-required~1]
def test_no_flow_in_this_split_requires_an_attestation_key_proof():
    assert ATTESTATION_PROOF_FLOWS == frozenset()
    for operation in SPLIT_FLOWS:
        assert requires_attestation_proof(operation) is False
    with pytest.raises(ProofRequirementError):
        requires_attestation_proof(AuthOperation.claim_anonymous_grant)


# [utest->req~users-create-user-no-integrity-proof~1]
def test_plain_create_user_requires_no_attestation_or_integrity_proof():
    assert CREATE_USER_PROOF_MATERIAL == frozenset()
    assert create_user_proof_material({"challenge_id": "abc", "provider": "anonymous"}) \
        == frozenset()
    for field in ("attestation_key_proof", "integrity_token", "play_integrity_token",
                  "devicecheck_token"):
        with pytest.raises(UsersError):
            create_user_proof_material({field: "material"})
    with pytest.raises(UsersError):
        create_user_proof_material({"restore_proof": {"receipt": "..."}})


# [utest->req~users-upgrade-proof-basis~1]
def test_the_upgrade_rests_on_the_verified_token_the_linked_row_and_the_admin_confirmation():
    row = linked_row()
    basis = upgrade_proof_basis(linked_context(row), row,
                                confirmed_provider=IdentityProvider.google)
    assert basis.verified_pair == (TEST_ISSUER, SUBJECT)
    assert basis.linked_identity_id == row.id
    assert basis.confirmed_provider is IdentityProvider.google


# [utest->req~users-upgrade-proof-basis~1]
def test_the_upgrade_takes_no_rewritten_header_no_other_read_point_and_no_anonymous_result():
    row = linked_row()
    context = linked_context(row)
    for header in (AuthorizationHeaderSource.gateway_rewritten_header,
                   AuthorizationHeaderSource.gateway_jwt_filter_metadata):
        with pytest.raises(ProofRequirementError):
            upgrade_proof_basis(context, row, confirmed_provider=IdentityProvider.google,
                                header=header)
    with pytest.raises(ProofRequirementError):
        upgrade_proof_basis(context, row, confirmed_provider=IdentityProvider.google,
                            read_point=ProviderDataReadPoint.claim_registered_grant_completion)
    with pytest.raises(ProofRequirementError):
        upgrade_proof_basis(context, row, confirmed_provider=IdentityProvider.anonymous)
    # A pre-auth caller has no linked identity row for the verified pair to rest on.
    preauth = VerifiedIdentityContext(issuer=TEST_ISSUER, subject="unlinked",
                                      outcome=ResolutionOutcome.pre_auth)
    with pytest.raises(UsersError):
        upgrade_proof_basis(preauth, row, confirmed_provider=IdentityProvider.google)


# [utest->req~users-auth-sync-token-only~1]
def test_auth_sync_accepts_only_the_id_token_and_stays_read_only():
    row = linked_row()
    context = linked_context(row)
    assert sync_request_credentials(context) == (TEST_ISSUER, SUBJECT)
    assert sync_request_credentials(
        context, offered=["authorization_bearer_firebase_id_token"]) == (TEST_ISSUER, SUBJECT)
    assert SYNC_WRITES == frozenset()
    assert SYNC_DEVICE_STATE_ACCESS == frozenset()
    assert requires_attestation_proof(AuthOperation.sync) is False
    for offered in (["devicecheck_token"], ["attestation_key_proof"], ["restore_proof"]):
        with pytest.raises(ProofRequirementError):
            sync_request_credentials(context, offered=offered)
    with pytest.raises(ProofRequirementError):
        sync_request_credentials(context,
                                 header=AuthorizationHeaderSource.gateway_rewritten_header)


# [utest->req~users-device-check-not-identity~1]
def test_a_device_check_token_is_grant_anti_abuse_state_and_never_identity():
    assert assert_device_check_use(DeviceCheckUse.grant_anti_abuse) is \
        DeviceCheckUse.grant_anti_abuse
    for use in (DeviceCheckUse.verified_identity, DeviceCheckUse.account_resolution):
        with pytest.raises(ProofRequirementError):
            assert_device_check_use(use)
    # The upgrade neither reads nor modifies that per-device state.
    assert UPGRADE_DEVICE_GRANT_BITS == frozenset()
    assert assert_not_identity_material(["challenge_id", "provider"]) is None
    with pytest.raises(ProofRequirementError):
        assert_not_identity_material(["devicecheck_token"])
    with pytest.raises(ProofRequirementError):
        assert_not_identity_material(["play_integrity_token", "provider"])


# [utest->req~users-upgrade-proof-basis~1]
def test_the_linked_row_must_be_the_one_the_verified_pair_resolves_to():
    row = linked_row()
    context = linked_context(row)
    other = replace(row, subject="another-subject")
    with pytest.raises(UpgradeError):
        upgrade_proof_basis(context, other, confirmed_provider=IdentityProvider.google)
