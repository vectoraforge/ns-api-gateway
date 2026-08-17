"""The request contracts of `POST /auth/claim-anonymous-grant` and
`POST /auth/claim-registered-grant`."""

from typing import Any
from uuid import uuid7

import pytest

from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.claim_endpoints import (
    ANON_ENDPOINT_ERROR_CLASSES,
    ANON_FORBIDDEN_FIELDS,
    ANON_WEB_BODY_EVIDENCE,
    CLIENT_SUPPLIED_WEB_SIGN_IN_EVIDENCE,
    REG_ENDPOINT_ERROR_CLASSES,
    REGISTRATION_TIMESTAMP_INPUTS,
    ClaimEndpointError,
    anonymous_challenge_source,
    anonymous_endpoint_error_classes,
    anonymous_grant_authentication,
    anonymous_grant_operation,
    anonymous_identity_shape,
    anonymous_native_vendor_tokens,
    anonymous_proof_is_not_identity,
    anonymous_web_evidence,
    assert_device_state_scope,
    assert_no_attestation_material,
    assert_no_client_provider_identifier,
    assert_no_registered_device_identity_proof,
    assert_no_registered_restore_proof,
    registered_challenge_source,
    registered_endpoint_error_classes,
    registered_endpoint_reads_and_enforces,
    registered_grant_authentication,
    registered_grant_operation_for,
    registered_identity_linked_active,
    registered_platform_proof_set,
    registered_proof_rejected_scope,
    registered_provider_requirement,
)
from nativespeaker.api.auth.derived_identifiers import (
    HmacKey,
    IdpAccountAliasIndex,
    KeyFamily,
    KeyRing,
)
from nativespeaker.api.auth.external_identities import ExternalIdentityRow, IdentityState
from nativespeaker.api.auth.free_grants import (
    FreeGrantError,
    FreeGrantRejected,
    WebGateRead,
)
from nativespeaker.api.auth.integration import FirebaseIntegration, FirebaseIntegrations
from nativespeaker.api.auth.invariants import ProviderAccountGates
from nativespeaker.api.auth.onboarding import AuthorizationHeaderSource
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_endpoints import ClaimBranch, GateDenied, ProofArtifact
from nativespeaker.api.auth.taxonomy import ClientErrorClass

ISSUER = "https://securetoken.google.com/test-project"
ADMIN_CLIENT = object()
GOOGLE_PROVIDER_DATA: list[Any] = [{"providerId": "google.com", "uid": "google-account-1"}]


class _Verifier:
    def verify_id_token(self, token: str) -> Any:  # pragma: no cover - never called here
        raise AssertionError("the endpoint contract verifies no token itself")


def identity_row(*,
                 provider: IdentityProvider = IdentityProvider.anonymous,
                 provider_uid: str | None = None,
                 identity_state: IdentityState = IdentityState.active) -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=ISSUER,
                               subject="firebase-subject", provider=provider,
                               provider_uid=provider_uid, identity_state=identity_state)


def google_row(**overrides: Any) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.google,
                              "provider_uid": "google-account-1"}
    fields.update(overrides)
    return identity_row(**fields)


def context_for(row: ExternalIdentityRow,
                outcome: ResolutionOutcome = ResolutionOutcome.linked) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=row.issuer, subject=row.subject, outcome=outcome,
                                   user_id=row.user_id, external_identity_id=row.id,
                                   provider=row.provider)


def integrations(issuer: str = ISSUER) -> FirebaseIntegrations:
    return FirebaseIntegrations([FirebaseIntegration(issuer=issuer, project_id="test-project",
                                                    verifier=_Verifier(),
                                                    admin_client=ADMIN_CLIENT)])


def web_gate_read(row: ExternalIdentityRow, *,
                  bot_check: bool = True,
                  provider_data: list[Any] | None = None) -> WebGateRead:
    def read(client: Any) -> list[Any] | None:
        assert client is ADMIN_CLIENT
        return GOOGLE_PROVIDER_DATA if provider_data is None else provider_data

    return WebGateRead(row=row, bot_check=lambda: bot_check, integrations=integrations(),
                       issuer=row.issuer, read_provider_data=read)


def alias_index() -> IdpAccountAliasIndex:
    ring = KeyRing(KeyFamily.k_idp_account, current=HmacKey(version=1, secret=b"i" * 32))
    return IdpAccountAliasIndex(ProviderAccountGates(), ring)


# --- One operation per endpoint ---------------------------------------------------------------


# [utest->req~grants-anon-endpoint-single-operation~1]
def test_the_anonymous_endpoint_performs_only_claim_anonymous_grant() -> None:
    assert anonymous_grant_operation("POST", "/auth/claim-anonymous-grant") \
        is AuthOperation.claim_anonymous_grant
    for method, path in (("POST", "/auth/claim-registered-grant"),
                         ("POST", "/auth/sync"),
                         ("GET", "/auth/claim-anonymous-grant")):
        with pytest.raises(ClaimEndpointError):
            anonymous_grant_operation(method, path)


# [utest->req~grants-reg-endpoint-single-operation~1]
def test_the_registered_endpoint_performs_only_claim_registered_grant() -> None:
    assert registered_grant_operation_for("POST", "/auth/claim-registered-grant") \
        is AuthOperation.claim_registered_grant
    for method, path in (("POST", "/auth/claim-anonymous-grant"),
                         ("POST", "/auth/restore-subscription"),
                         ("GET", "/auth/claim-registered-grant")):
        with pytest.raises(ClaimEndpointError):
            registered_grant_operation_for(method, path)


# --- The `Authorization` credential -----------------------------------------------------------


# [utest->req~grants-anon-req-authorization-token~1]
def test_the_anonymous_claim_authenticates_only_on_the_barrier_supplied_pair() -> None:
    row = identity_row()
    assert anonymous_grant_authentication(context_for(row), row=row) == (row.issuer, row.subject)
    with pytest.raises(ClaimEndpointError):
        anonymous_grant_authentication(
            context_for(row), row=row,
            header=AuthorizationHeaderSource.gateway_jwt_filter_metadata)
    unresolved = VerifiedIdentityContext(issuer="", subject="", outcome=ResolutionOutcome.linked)
    with pytest.raises(ClaimEndpointError):
        anonymous_grant_authentication(unresolved)
    other = identity_row()
    object.__setattr__(other, "subject", "another-firebase-subject")
    with pytest.raises(ClaimEndpointError):
        anonymous_grant_authentication(context_for(row), row=other)


# [utest->req~grants-reg-req-authorization-token~1]
def test_the_registered_claim_authenticates_only_on_the_barrier_supplied_pair() -> None:
    row = google_row()
    assert registered_grant_authentication(context_for(row), row=row) == (row.issuer, row.subject)
    with pytest.raises(ClaimEndpointError):
        registered_grant_authentication(
            context_for(row), row=row,
            header=AuthorizationHeaderSource.gateway_rewritten_header)
    with pytest.raises(ClaimEndpointError):
        registered_grant_authentication(
            VerifiedIdentityContext(issuer=ISSUER, subject="",
                                    outcome=ResolutionOutcome.linked))


# --- The identity shape -----------------------------------------------------------------------


# [utest->req~grants-anon-req-identity-shape~1]
def test_native_paths_admit_an_anonymous_or_registered_active_identity() -> None:
    for branch in (ClaimBranch.native_ios, ClaimBranch.native_android):
        assert anonymous_identity_shape(identity_row(), branch) is IdentityProvider.anonymous
        assert anonymous_identity_shape(google_row(), branch) is IdentityProvider.google
        with pytest.raises(ClaimEndpointError):
            anonymous_identity_shape(identity_row(identity_state=IdentityState.historical), branch)


# [utest->req~grants-anon-req-identity-shape~1]
def test_web_requires_a_registered_stored_provider_and_a_stored_provider_uid() -> None:
    assert anonymous_identity_shape(google_row(), ClaimBranch.web) is IdentityProvider.google
    with pytest.raises(FreeGrantRejected):
        anonymous_identity_shape(identity_row(), ClaimBranch.web)
    row = google_row()
    object.__setattr__(row, "provider_uid", "")
    with pytest.raises(ClaimEndpointError):
        anonymous_identity_shape(row, ClaimBranch.web)


# [utest->req~grants-anon-req-identity-shape~1]
def test_registered_at_is_not_an_eligibility_input() -> None:
    assert REGISTRATION_TIMESTAMP_INPUTS == frozenset()
    with pytest.raises(ClaimEndpointError):
        anonymous_identity_shape(google_row(), ClaimBranch.web, consulted=("registered_at",))


# [utest->req~grants-reg-req-linked-active~1]
def test_the_registered_claim_needs_a_linked_active_identity_and_active_user() -> None:
    row = google_row()
    assert registered_identity_linked_active(context_for(row), row, user_active=True) is row
    with pytest.raises(ClaimEndpointError):
        registered_identity_linked_active(context_for(row, ResolutionOutcome.pre_auth), row,
                                          user_active=True)
    historical = google_row(identity_state=IdentityState.historical)
    with pytest.raises(ClaimEndpointError):
        registered_identity_linked_active(context_for(historical), historical, user_active=True)
    with pytest.raises(ClaimEndpointError):
        registered_identity_linked_active(context_for(row), row, user_active=False)


# [utest->req~grants-reg-req-provider-google-apple~1]
def test_the_registered_claim_requires_a_google_or_apple_stored_provider() -> None:
    for provider, uid in ((IdentityProvider.google, "google-account-1"),
                          (IdentityProvider.apple, "apple-account-1")):
        row = identity_row(provider=provider, provider_uid=uid)
        assert registered_provider_requirement(row) is provider
    with pytest.raises(FreeGrantRejected):
        registered_provider_requirement(identity_row())


# --- The operation challenge ------------------------------------------------------------------


# [utest->req~grants-anon-req-operation-challenge~1]
def test_the_anonymous_challenge_comes_from_the_endpoints_own_prepare_url() -> None:
    assert anonymous_challenge_source() == "POST /auth/claim-anonymous-grant?challenge=true"


# [utest->req~grants-reg-req-operation-challenge~1]
def test_the_registered_challenge_comes_from_the_endpoints_own_prepare_url() -> None:
    assert registered_challenge_source() == "POST /auth/claim-registered-grant?challenge=true"


# --- The anonymous claim's vendor material ----------------------------------------------------


# [utest->req~grants-anon-req-native-vendor-tokens~1]
def test_ios_carries_two_devicecheck_tokens_and_android_one_play_integrity_token() -> None:
    assert anonymous_native_vendor_tokens(ClaimBranch.native_ios) == frozenset({
        ProofArtifact.devicecheck_query_token, ProofArtifact.devicecheck_update_token})
    assert anonymous_native_vendor_tokens(ClaimBranch.native_android) == frozenset({
        ProofArtifact.play_integrity_verdict})
    with pytest.raises(ClaimEndpointError):
        anonymous_native_vendor_tokens(ClaimBranch.web)


# [utest->req~grants-anon-req-native-vendor-tokens~1]
def test_the_android_native_path_exists_only_where_device_recall_is_available() -> None:
    with pytest.raises(ClaimEndpointError):
        anonymous_native_vendor_tokens(ClaimBranch.native_android, device_recall_available=False)


# [utest->req~grants-anon-req-web-evidence~1]
def test_the_web_body_carries_bot_check_evidence_and_the_gate_reads_provider_data() -> None:
    assert ANON_WEB_BODY_EVIDENCE == frozenset({ProofArtifact.turnstile_token})
    assert CLIENT_SUPPLIED_WEB_SIGN_IN_EVIDENCE == frozenset()
    row = google_row()
    account = anonymous_web_evidence(web_gate_read(row))
    assert account.provider is IdentityProvider.google
    assert account.canonical_provider_account_id == "google-account-1"
    with pytest.raises(ClaimEndpointError):
        anonymous_web_evidence(web_gate_read(row),
                               body_evidence=(ProofArtifact.turnstile_token,
                                              ProofArtifact.devicecheck_query_token))


# [utest->req~grants-anon-req-web-evidence~1]
def test_a_mismatching_provider_data_result_denies_the_web_gate() -> None:
    row = google_row()
    with pytest.raises(GateDenied):
        anonymous_web_evidence(web_gate_read(
            row, provider_data=[{"providerId": "google.com", "uid": "someone-else"}]))
    with pytest.raises(GateDenied):
        anonymous_web_evidence(web_gate_read(row, bot_check=False))


# [utest->req~grants-anon-req-no-attestation-material~1]
def test_the_anonymous_request_carries_no_attestation_or_restore_material() -> None:
    assert_no_attestation_material({"challenge_id": "c", "turnstile_token": "t"})
    assert_no_attestation_material(None)
    for field in ("app_attest_assertion", "android_keystore_proof", "enrolled_key_proof",
                  "restore_proof", "attestation_key_proof"):
        assert field in ANON_FORBIDDEN_FIELDS
        with pytest.raises(ClaimEndpointError):
            assert_no_attestation_material({field: "x"})


# [utest->req~grants-anon-proof-not-identity-token~1]
def test_vendor_material_never_resolves_the_account() -> None:
    row = identity_row()
    assert anonymous_proof_is_not_identity(context_for(row)) == (row.issuer, row.subject)
    for material in ("devicecheck_query_token", "play_integrity_token", "turnstile_token"):
        with pytest.raises(FreeGrantError):
            anonymous_proof_is_not_identity(context_for(row), offered=(material,))
    with pytest.raises(ClaimEndpointError):
        anonymous_proof_is_not_identity(context_for(row), resolved_by="gateway_jwt_filter")


# --- The device-state scope -------------------------------------------------------------------


# [utest->req~grants-anon-endpoint-device-state-scope~1]
def test_device_state_is_touched_only_through_the_platform_gate() -> None:
    assert_device_state_scope(device_state_paths=("platform_gate",),
                              web_sign_in_paths=("firebase_admin_provider_data",))
    with pytest.raises(ClaimEndpointError):
        assert_device_state_scope(device_state_paths=("users_me_read",))
    with pytest.raises(ClaimEndpointError):
        assert_device_state_scope(web_sign_in_paths=("client_supplied_id_token",))


# --- The registered claim's proof set and prohibitions ----------------------------------------


# [utest->req~grants-reg-req-no-device-identity-proof~1]
def test_no_device_material_is_identity_or_ownership_proof_on_the_registered_claim() -> None:
    assert_no_registered_device_identity_proof()
    with pytest.raises(FreeGrantError):
        assert_no_registered_device_identity_proof(required=("app_attest_assertion",))
    with pytest.raises(FreeGrantError):
        assert_no_registered_device_identity_proof(accepted=("android_keystore_proof",))
    with pytest.raises(FreeGrantError):
        assert_no_registered_device_identity_proof(evaluated=("attestation_key_proof",))


# [utest->req~grants-reg-req-platform-proof-set~1]
def test_every_claim_kind_carries_its_mandatory_platform_proof_set() -> None:
    assert registered_platform_proof_set(ClaimBranch.native_ios) == frozenset({
        ProofArtifact.devicecheck_query_token, ProofArtifact.devicecheck_update_token})
    assert registered_platform_proof_set(ClaimBranch.native_android) == frozenset({
        ProofArtifact.play_integrity_verdict})
    assert registered_platform_proof_set(ClaimBranch.web) == frozenset({
        ProofArtifact.turnstile_token})
    # The release policy decides what the one Android token covers, never whether it is required.
    assert registered_platform_proof_set(ClaimBranch.native_android, recall_required=False) \
        == frozenset({ProofArtifact.play_integrity_verdict})


# [utest->req~grants-reg-req-no-restore-proof~1]
def test_the_registered_request_carries_no_restore_proof() -> None:
    assert_no_registered_restore_proof({"challenge_id": "c"})
    with pytest.raises(ClaimEndpointError):
        assert_no_registered_restore_proof({"restore_proof": {"receipt": "x"}})


# [utest->req~grants-reg-req-no-client-provider-id~1]
def test_the_registered_request_carries_no_client_supplied_provider_account_id() -> None:
    assert_no_client_provider_identifier({"challenge_id": "c"})
    for field in ("provider_uid", "provider_account_id", "idp_account_hash", "google_uid",
                  "apple_uid", "email"):
        with pytest.raises(ClaimEndpointError):
            assert_no_client_provider_identifier({field: "x"})


# [utest->req~grants-reg-endpoint-reads-and-enforces~1]
def test_the_registered_endpoint_reads_stored_values_and_enforces_both_gates() -> None:
    row = google_row()
    assert registered_endpoint_reads_and_enforces(row, alias_index()) == (
        "one_free_grant_per_account",
        "registered_gate_consumption_uniqueness_on_stable_uid")
    with pytest.raises(ClaimEndpointError):
        registered_endpoint_reads_and_enforces(row, alias_index(),
                                               provider_data_confirmations=0)
    with pytest.raises(ClaimEndpointError):
        registered_endpoint_reads_and_enforces(row, alias_index(),
                                               provider_data_confirmations=2)
    with pytest.raises(FreeGrantRejected):
        registered_endpoint_reads_and_enforces(identity_row(), alias_index())


# --- The client-visible classes ---------------------------------------------------------------


# [utest->req~grants-anon-endpoint-error-classes~1]
def test_the_anonymous_endpoint_returns_exactly_its_nine_opaque_classes() -> None:
    assert anonymous_endpoint_error_classes() == frozenset(ANON_ENDPOINT_ERROR_CLASSES)
    assert set(ANON_ENDPOINT_ERROR_CLASSES) == {
        ClientErrorClass.auth_required, ClientErrorClass.preauth_identity_not_allowed,
        ClientErrorClass.account_unavailable, ClientErrorClass.challenge_required,
        ClientErrorClass.proof_rejected, ClientErrorClass.operation_not_allowed,
        ClientErrorClass.device_grant_exhausted, ClientErrorClass.verification_required,
        ClientErrorClass.verification_temporarily_unavailable}
    assert ClientErrorClass.account_already_claimed not in ANON_ENDPOINT_ERROR_CLASSES


# [utest->req~grants-reg-endpoint-error-classes~1]
def test_the_registered_endpoint_returns_exactly_its_ten_opaque_classes() -> None:
    assert registered_endpoint_error_classes() == frozenset(REG_ENDPOINT_ERROR_CLASSES)
    assert set(REG_ENDPOINT_ERROR_CLASSES) == set(ANON_ENDPOINT_ERROR_CLASSES) | {
        ClientErrorClass.account_already_claimed}


# [utest->req~grants-reg-endpoint-error-classes~1]
def test_registered_proof_rejected_covers_only_transaction_material() -> None:
    conditions = registered_proof_rejected_scope()
    assert {str(condition) for condition in conditions} == {
        "incomplete_platform_proof_set", "evidence_set_shape_invalid"}
