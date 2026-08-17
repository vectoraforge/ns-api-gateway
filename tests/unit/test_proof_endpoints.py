"""Which endpoint requires which proof — and, mostly, which requires none."""

from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.derived_identifiers import (
    DerivationError,
    HmacKey,
    IdpAccountAliasIndex,
    KeyFamily,
    KeyRing,
)
from nativespeaker.api.auth.external_identities import (
    BindingDivergenceError,
    ExternalIdentityRow,
    LookupFailure,
    ProviderLookupFailedError,
)
from nativespeaker.api.auth.integration import FirebaseIntegration, FirebaseIntegrations
from nativespeaker.api.auth.invariants import (
    DevicePlatform,
    GateAlreadyConsumedError,
    GateConsumptionKind,
    ProofUse,
    ProviderAccountGates,
)
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_endpoints import (
    ATTESTATION_REQUIRING_OPERATIONS,
    GATE_DENIES,
    ClaimBranch,
    GateDenied,
    IdentityInput,
    ProofApplicabilityError,
    ProofArtifact,
    RestoreRejected,
    assert_anti_abuse_device_state_only,
    assert_gate_denial_scope,
    assert_not_attestation_evidence,
    claim_anonymous_grant_gate,
    create_user_takes_no_device_check,
    gate_lookup_unavailable,
    idp_hmac_applies,
    registered_grant_idp_account,
    requesting_identity,
    requires_attestation,
    restore_proof_applies_to,
    restore_proof_set,
    upgrade_in_place_flip,
    web_anonymous_grant_gate,
    web_gate_admin_client,
    web_gate_consumption,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass, ProviderDataReadPoint
from nativespeaker.api.auth.tokens import (
    FirebaseIdTokenVerifier,
    InvalidExternalJwtError,
)

from .conftest import PUBLIC_KEY_PEM

ISSUER = "https://securetoken.google.com/test-project"
KEY = HmacKey(version=1, secret=b"k" * 32)


def context(issuer: str = ISSUER, subject: str = "sub-1") -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=issuer, subject=subject,
                                   outcome=ResolutionOutcome.linked,
                                   user_id=uuid7(), external_identity_id=uuid7())


def google_row(uid: str = "g-1") -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=ISSUER, subject="sub-1",
                               provider=IdentityProvider.google, provider_uid=uid)


def anonymous_row() -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=ISSUER, subject="sub-1",
                               provider=IdentityProvider.anonymous)


def google_entries(uid: str = "g-1") -> list[dict[str, str]]:
    return [{"provider_id": "google.com", "uid": uid}]


# --- The requesting identity --------------------------------------------------------------------


class TestRequestingIdentity:

    # [utest->req~proof-requesting-identity-from-token~1]
    def test_the_identity_is_the_barriers_verified_issuer_and_subject(self):
        assert requesting_identity(context()) == (ISSUER, "sub-1")

    # No header, body field, query parameter, cookie or proof artifact contributes identity.
    # [utest->req~proof-requesting-identity-from-token~1]
    def test_nothing_else_contributes_identity(self):
        for source in (IdentityInput.request_header, IdentityInput.body_field,
                       IdentityInput.query_parameter, IdentityInput.cookie,
                       IdentityInput.proof_artifact):
            with pytest.raises(ProofApplicabilityError):
                requesting_identity(context(), source=source)

    # It is resolved once per request, by the shared barrier.
    # [utest->req~proof-requesting-identity-from-token~1]
    def test_it_is_resolved_once_per_request(self):
        with pytest.raises(ProofApplicabilityError):
            requesting_identity(context(), resolutions=2)
        with pytest.raises(ProofApplicabilityError):
            requesting_identity(VerifiedIdentityContext(
                issuer="", subject="", outcome=ResolutionOutcome.pre_auth))


# --- Attestation ---------------------------------------------------------------------------------


class TestAttestation:

    # [utest->req~proof-no-endpoint-requires-attestation~1]
    # [utest->req~proof-no-attestation-key-verification~1]
    def test_no_endpoint_requires_an_attestation_proof(self):
        assert ATTESTATION_REQUIRING_OPERATIONS == frozenset()
        for operation in AuthOperation:
            assert requires_attestation(operation) is False

    # No endpoint accepts one as identity, ownership, recovery, upgrade or account-resolution
    # evidence, and none verifies an attestation-key proof to establish any of them.
    # [utest->req~proof-no-endpoint-requires-attestation~1]
    # [utest->req~proof-no-attestation-key-verification~1]
    def test_attestation_is_never_evidence_for_any_role(self):
        for artifact in (ProofArtifact.attestation_key_proof, ProofArtifact.attestation_blob,
                         ProofArtifact.integrity_proof):
            for role in ProofUse:
                with pytest.raises(ProofApplicabilityError):
                    assert_not_attestation_evidence(artifact, role)

    # The free-grant claims' vendor material is anti-abuse device state only: none of it is
    # challenge-bound attestation proof.
    # [utest->req~proof-no-endpoint-requires-attestation~1]
    def test_the_claim_vendor_material_is_anti_abuse_device_state_only(self):
        assert_anti_abuse_device_state_only([ProofArtifact.devicecheck_query_token,
                                             ProofArtifact.devicecheck_update_token,
                                             ProofArtifact.play_integrity_verdict,
                                             ProofArtifact.turnstile_token])
        with pytest.raises(ProofApplicabilityError):
            assert_anti_abuse_device_state_only([ProofArtifact.attestation_key_proof])


class TestRestoreScope:

    # [utest->req~proof-restore-proof-scope~2]
    def test_restore_proof_applies_to_restore_subscription_only(self):
        assert restore_proof_applies_to(AuthOperation.restore_subscription) is True
        for operation in set(AuthOperation) - {AuthOperation.restore_subscription}:
            assert restore_proof_applies_to(operation) is False

    # Restore accepts the store artifact alone, with the store fixed by the calling platform.
    # [utest->req~proof-no-endpoint-requires-attestation~1]
    # [utest->req~proof-restore-proof-scope~2]
    def test_the_store_artifact_is_the_entire_proof_set(self):
        assert restore_proof_set(DevicePlatform.ios, store_artifact="jws") == \
            "signed_storekit_transaction"
        assert restore_proof_set(DevicePlatform.android, store_artifact="tok") == \
            "google_play_purchase_token"
        with pytest.raises(ProofApplicabilityError):
            restore_proof_set(DevicePlatform.ios, store_artifact="jws",
                              other_artifacts=[ProofArtifact.integrity_proof])

    # A web call, or any call presenting no native store-artifact family, is rejected with
    # `operation_not_allowed`.
    # [utest->req~proof-no-endpoint-requires-attestation~1]
    def test_a_web_or_artifactless_call_is_operation_not_allowed(self):
        with pytest.raises(RestoreRejected) as web:
            restore_proof_set(DevicePlatform.web, store_artifact="whatever")
        assert web.value.error_code == "operation_not_allowed"
        with pytest.raises(RestoreRejected):
            restore_proof_set(DevicePlatform.ios, store_artifact=None)


class TestCreateUser:

    # In either phase and in either its anonymous or registered form.
    # [utest->req~proof-create-user-no-device-check~1]
    def test_create_user_takes_no_proof_in_either_phase_or_form(self):
        for phase in RequestMode:
            for variant in IdentityProvider:
                assert create_user_takes_no_device_check(phase=phase, variant=variant) == \
                    frozenset()

    # [utest->req~proof-create-user-no-device-check~1]
    def test_an_offered_device_check_or_attestation_is_refused(self):
        for field in ("devicecheck_token", "play_integrity_token", "attestation_key_proof",
                      "integrity_proof"):
            with pytest.raises(ProofApplicabilityError):
                create_user_takes_no_device_check(phase=RequestMode.completion,
                                                  variant=IdentityProvider.anonymous,
                                                  body={field: "x"})

    # The device-check signal gates free-credit grant eligibility only and is never a control on
    # account-creation volume.
    # [utest->req~proof-create-user-no-device-check~1]
    def test_the_device_check_signal_never_gates_account_creation_volume(self):
        from nativespeaker.api.auth.proof_endpoints import (
            DEVICE_CHECK_GATES,
            DEVICE_CHECK_NEVER_GATES,
        )
        assert DEVICE_CHECK_GATES == frozenset({"free_credit_grant_eligibility"})
        assert not (DEVICE_CHECK_GATES & DEVICE_CHECK_NEVER_GATES)


# --- `claim-anonymous-grant` ----------------------------------------------------------------------


class TestAnonymousClaimGating:

    # The native path is gated by per-device device-check state; the web path by the server-side
    # Firebase sign-in check, deduplicated per provider account via `idp_account_hash`.
    # [utest->req~proof-claim-anonymous-grant-gating-paths~1]
    def test_the_two_paths_are_gated_differently(self):
        ios = claim_anonymous_grant_gate(ClaimBranch.native_ios)
        assert ios.material == frozenset({ProofArtifact.devicecheck_query_token,
                                          ProofArtifact.devicecheck_update_token})
        assert ios.dedup_key is None
        android = claim_anonymous_grant_gate(ClaimBranch.native_android)
        assert android.material == frozenset({ProofArtifact.play_integrity_verdict})
        web = claim_anonymous_grant_gate(ClaimBranch.web)
        assert web.dedup_key == "idp_account_hash"

    # Client-supplied device-check or integrity material is used only for the vendor read and
    # write: it is never an identity token and never resolves which account a request belongs to.
    # [utest->req~proof-claim-anonymous-grant-gating-paths~1]
    def test_client_vendor_material_is_never_identity_or_account_resolution(self):
        for role in (ProofUse.identity, ProofUse.account_resolution, ProofUse.ownership,
                     ProofUse.recovery, ProofUse.upgrade):
            with pytest.raises(ProofApplicabilityError):
                claim_anonymous_grant_gate(ClaimBranch.native_ios, client_material_role=role)

    # No attestation-key-derived identifier is enrolled on `core.external_identities` at claim
    # time, and none is stored on the grant anti-abuse record.
    # [utest->req~proof-claim-anonymous-grant-gating-paths~1]
    def test_no_attestation_derived_identifier_is_enrolled_or_stored(self):
        with pytest.raises(ProofApplicabilityError):
            claim_anonymous_grant_gate(ClaimBranch.native_ios,
                                       enrols_identity=["attestation_key_id"])
        with pytest.raises(ProofApplicabilityError):
            claim_anonymous_grant_gate(ClaimBranch.web,
                                       anti_abuse_identifiers=["attestation_key_hash"])


class TestUpgradeFlip:

    # An in-place flip on the existing row that keeps the same `(issuer, subject)`.
    # [utest->req~proof-upgrade-in-place-provider-flip~1]
    def test_the_flip_keeps_the_row_and_the_verified_pair(self):
        row = anonymous_row()
        flipped = upgrade_in_place_flip(row, provider=IdentityProvider.google, provider_uid="g-1")
        assert (flipped.id, flipped.issuer, flipped.subject) == (row.id, row.issuer, row.subject)
        assert flipped.provider is IdentityProvider.google

    # It reads, sets and clears no vendor per-device device-check state and mints no grant,
    # including when it completes an interrupted registration.
    # [utest->req~proof-upgrade-in-place-provider-flip~1]
    def test_the_flip_touches_no_device_state_and_mints_no_grant(self):
        row = anonymous_row()
        with pytest.raises(ProofApplicabilityError):
            upgrade_in_place_flip(row, provider=IdentityProvider.google, provider_uid="g-1",
                                  device_state_touched=["bit0"])
        with pytest.raises(ProofApplicabilityError):
            upgrade_in_place_flip(row, provider=IdentityProvider.google, provider_uid="g-1",
                                  grants_minted=["anonymous_device_grant"],
                                  interrupted_registration=True)

    # Each `core.users` row maps to a single `core.external_identities` row.
    # [utest->req~proof-upgrade-in-place-provider-flip~1]
    def test_one_identity_row_per_user(self):
        with pytest.raises(ProofApplicabilityError):
            upgrade_in_place_flip(anonymous_row(), provider=IdentityProvider.google,
                                  provider_uid="g-1", identity_rows_for_user=2)


# --- Where IDP-account HMAC derivation applies -----------------------------------------------------


class TestIdpHmacApplicability:

    # It applies to the registered claim and to the web sign-in gate of the anonymous claim —
    # and to nothing else, the anonymous claim's native branches included.
    # [utest->req~proof-idp-hmac-applicability~1]
    def test_it_applies_to_two_places_only(self):
        assert idp_hmac_applies(AuthOperation.claim_registered_grant) is True
        assert idp_hmac_applies(AuthOperation.claim_anonymous_grant,
                                branch=ClaimBranch.web) is True
        assert idp_hmac_applies(AuthOperation.claim_anonymous_grant,
                                branch=ClaimBranch.native_ios) is False
        for operation in (AuthOperation.create_user, AuthOperation.restore_subscription,
                          AuthOperation.upgrade_anonymous_to_registered, AuthOperation.sync,
                          AuthOperation.sign_out_all):
            assert idp_hmac_applies(operation) is False

    # The registered claim derives from the stored `provider_uid`, rejects when it is absent, and
    # confirms the stored binding on every call.
    # [utest->req~proof-idp-hmac-applicability~1]
    def test_the_registered_claim_derives_from_the_stored_binding(self):
        assert registered_grant_idp_account(google_row("g-5"), google_entries("g-5")) == "g-5"
        with pytest.raises(DerivationError):
            registered_grant_idp_account(anonymous_row(), [])

    # A divergent confirmation is a conflict, and it never rewrites the stored binding.
    # [utest->req~proof-idp-hmac-applicability~1]
    def test_a_divergent_confirmation_is_a_conflict(self):
        row = google_row("g-5")
        with pytest.raises(BindingDivergenceError) as raised:
            registered_grant_idp_account(row, google_entries("g-6"))
        assert raised.value.client_class is ClientErrorClass.operation_not_allowed
        assert row.provider_uid == "g-5"

    # Gate uniqueness is enforced through the canonical registry's consumption rows.
    # [utest->req~proof-idp-hmac-applicability~1]
    def test_the_web_gate_consumes_a_registry_row(self):
        index = IdpAccountAliasIndex(ProviderAccountGates(),
                                     KeyRing(KeyFamily.k_idp_account, current=KEY))
        account = web_anonymous_grant_gate(google_row("g-1"), google_entries("g-1"))
        assert web_gate_consumption(index, account, uuid7()) is \
            GateConsumptionKind.web_anonymous_gate
        with pytest.raises(GateAlreadyConsumedError):
            web_gate_consumption(index, account, uuid7())


# --- The web gate's classifier -----------------------------------------------------------------


class TestWebGateClassifier:

    # [utest->req~proof-web-gate-provider-data-classifier~1]
    def test_the_gate_accepts_only_the_sole_matching_entry(self):
        account = web_anonymous_grant_gate(google_row("g-1"), google_entries("g-1"))
        assert account.provider is IdentityProvider.google
        assert account.canonical_provider_account_id == "g-1"

    # Every other shape — both providers, multiple entries, an unrecognized entry, no entries, a
    # non-matching provider or uid, an anonymous claiming identity — denies the grant. Merely
    # finding one matching entry is never sufficient.
    # [utest->req~proof-web-gate-provider-data-classifier~1]
    def test_every_other_shape_denies_the_grant(self):
        row = google_row("g-1")
        for entries in ([{"provider_id": "google.com", "uid": "g-1"},
                         {"provider_id": "apple.com", "uid": "a-1"}],
                        [{"provider_id": "google.com", "uid": "g-1"},
                         {"provider_id": "google.com", "uid": "g-2"}],
                        [{"provider_id": "facebook.com", "uid": "f-1"}],
                        [],
                        [{"provider_id": "apple.com", "uid": "a-1"}],
                        [{"provider_id": "google.com", "uid": "g-2"}]):
            with pytest.raises(GateDenied):
                web_anonymous_grant_gate(row, entries)
        with pytest.raises(GateDenied):
            web_anonymous_grant_gate(anonymous_row(), google_entries())

    # A failed or indeterminate lookup is never read as an empty, invalid-shape or non-matching
    # result: it audits as `firebase_lookup_unavailable`, distinct from a client-supplied proof
    # failure, and surfaces as `verification_temporarily_unavailable`.
    # [utest->req~proof-web-gate-provider-data-classifier~1]
    def test_an_unavailable_lookup_keeps_its_own_result_and_class(self):
        failure = ProviderLookupFailedError(AuthEventResult.firebase_lookup_unavailable,
                                            ClientErrorClass.verification_temporarily_unavailable,
                                            retryable=True)
        with pytest.raises(ProviderLookupFailedError) as raised:
            web_anonymous_grant_gate(google_row(), None, lookup_failure=failure)
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert raised.value.client_class is \
            ClientErrorClass.verification_temporarily_unavailable
        assert raised.value.client_class.value != GateDenied.error_code
        assert gate_lookup_unavailable(None).result is \
            AuthEventResult.firebase_lookup_unavailable

    # A failed, indeterminate, invalid-shape or non-matching Admin lookup denies that free grant
    # and nothing else: never login, account creation, the upgrade, sync, restore, or a paid
    # entitlement path.
    # [utest->req~proof-web-gate-provider-data-classifier~1]
    def test_the_denial_touches_nothing_but_that_free_grant(self):
        assert GATE_DENIES == frozenset({AuthOperation.claim_anonymous_grant})
        assert_gate_denial_scope(AuthOperation.claim_anonymous_grant)
        for operation in (AuthOperation.create_user, AuthOperation.sync,
                          AuthOperation.upgrade_anonymous_to_registered,
                          AuthOperation.restore_subscription,
                          AuthOperation.claim_registered_grant, AuthOperation.sign_out_all):
            with pytest.raises(ProofApplicabilityError):
                assert_gate_denial_scope(operation)

    # The Admin lookup runs through the single configured integration selected by the verified
    # issuer match, and no other client.
    # [utest->req~proof-web-gate-provider-data-classifier~1]
    def test_the_admin_client_is_selected_by_the_verified_issuer(self):
        client = object()
        verifier = FirebaseIdTokenVerifier(issuer=ISSUER, audience="test-project",
                                           key_resolver=lambda _token: PUBLIC_KEY_PEM)
        integrations = FirebaseIntegrations([
            FirebaseIntegration(issuer=ISSUER, project_id="test-project",
                                verifier=verifier, admin_client=client)])
        assert web_gate_admin_client(integrations, ISSUER) is client
        with pytest.raises(InvalidExternalJwtError):
            web_gate_admin_client(integrations, "https://evil.example")

    # The gate reads at its own read point, not at another operation's.
    # [utest->req~proof-web-gate-provider-data-classifier~1]
    def test_the_gate_reads_at_its_own_read_point(self):
        with pytest.raises(ProofApplicabilityError):
            web_anonymous_grant_gate(
                google_row(), google_entries(),
                read_point=ProviderDataReadPoint.claim_registered_grant_completion)

    # A failed or indeterminate lookup, of any kind, is never turned into the classifier's own
    # denial: it keeps the unavailable result and never becomes a client-proof failure.
    # [utest->req~proof-web-gate-provider-data-classifier~1]
    def test_no_lookup_failure_kind_becomes_a_classifier_denial(self):
        for kind in (LookupFailure.transient, LookupFailure.infrastructure,
                     LookupFailure.malformed_response, LookupFailure.indeterminate):
            failure = ProviderLookupFailedError(
                AuthEventResult.firebase_lookup_unavailable,
                ClientErrorClass.verification_temporarily_unavailable,
                retryable=kind is not LookupFailure.user_not_found)
            with pytest.raises(ProviderLookupFailedError) as raised:
                web_anonymous_grant_gate(google_row(), None, lookup_failure=failure)
            assert not isinstance(raised.value, GateDenied)
            assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
