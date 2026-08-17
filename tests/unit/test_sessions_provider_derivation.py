"""The closed provider-derivation procedure and the single Firebase integration's selection rules.

Call sites, lookup failure, the classifier, declaration match and persistence are one procedure,
and every Admin read a stage names runs on the integration selected by issuer match.
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.create_user import (
    CREATE_FLOW_MISMATCH_CLASS,
    AdminLookupResult,
    CreateFlow,
    CreateUserError,
    CreateUserRejection,
    ProviderNotLinkedCause,
    classify_admin_provider_data,
    confirm_declaration,
    firebase_admin_get_user,
    lookup_failure,
)
from nativespeaker.api.auth.external_identities import (
    ADMINISTRATIVE_ADMIN_CALL_SITES,
    LOOKUP_FAILURE_PERSISTS,
    PROVIDER_DERIVATION_STAGES,
    PROVIDER_RECONCILIATION_JOBS,
    AdministrativeAction,
    ExternalIdentityRow,
    IdentityError,
    IdentityState,
    LookupFailure,
    ProviderClassificationError,
    ProviderConsumer,
    ProviderDataReadPoint,
    ProviderDeclarationMismatchError,
    ProviderLookupFailedError,
    ProviderUidSource,
    admin_client_for_identity,
    administrative_write,
    assert_declared_provider,
    assert_may_write_provider_fields,
    assert_provider_data_read_point,
    assert_provider_uid_source,
    authoritative_provider,
    classify_provider,
    provider_derivation_stage,
    provider_from_lookup,
    provider_uid_for,
    write_provider_uid,
)
from nativespeaker.api.auth.integration import (
    ADMINISTRATIVE_ADMIN_SITES,
    ALLOWED_SIGN_IN_PROVIDERS,
    PROVIDER_ID_TO_PROVIDER,
    REQUEST_DRIVEN_ADMIN_SITES,
    AdminCallSite,
    AdminSelectionSiteError,
    UnrecognizedProviderError,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.profile import ProfileError, assert_registered_at_pairing
from nativespeaker.api.auth.taxonomy import ClientErrorClass, surface
from nativespeaker.api.auth.tokens import InvalidExternalJwtError
from nativespeaker.api.auth.users import (
    ProviderNotConfirmedError,
    issuer_selected_admin_client,
    upgrade_completion_decision,
    upgrade_target_provider,
)
from unit.conftest import TEST_ISSUER
from unit.test_create_user import (
    ADMIN_CLIENT,
    APPLE,
    GOOGLE,
    NOW,
    FakeLookup,
    Flow,
    _lookup_error,
    integrations,
)

SRC = Path(__file__).resolve().parents[2] / "src"


def entry(provider_id: str, uid: str = "provider-account-uid") -> dict[str, str]:
    return {"provider_id": provider_id, "uid": uid}


def identity_row(*, provider: IdentityProvider = IdentityProvider.anonymous,
                 provider_uid: str | None = None,
                 issuer: str = TEST_ISSUER) -> ExternalIdentityRow:
    from uuid import uuid7
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=issuer, subject="sub-1",
                               provider=provider, provider_uid=provider_uid,
                               identity_state=IdentityState.active)


# --- The closed procedure ---------------------------------------------------------------------


class TestClosedProcedure:
    # [utest->req~sessions-provider-derivation-closed-procedure~1]
    def test_the_procedure_is_exactly_these_five_stages_in_order(self):
        assert [stage for stage, _ in PROVIDER_DERIVATION_STAGES] == [
            "call_sites", "lookup_failure", "classifier", "declaration_match", "persistence"]
        # Each stage names the entry point that performs it, and each one exists.
        import nativespeaker.api.auth.external_identities as derivation
        for stage, entry_point in PROVIDER_DERIVATION_STAGES:
            assert provider_derivation_stage(stage) == entry_point
            assert callable(getattr(derivation, entry_point))
        # Nothing else is a stage of provider derivation, so no sixth stage can appear silently.
        for outsider in ("token_claim", "request_header", "reconciliation", "cache"):
            with pytest.raises(ProviderClassificationError):
                provider_derivation_stage(outsider)

    # [utest->req~sessions-provider-derivation-closed-procedure~1]
    def test_nothing_outside_the_procedure_maps_a_provider_id_to_a_provider(self):
        mapping = re.compile(r'^\s*"(?:google|apple)\.com"\s*:')
        mappers = sorted(path.name for path in SRC.rglob("*.py")
                         if any(mapping.match(line) for line in path.read_text().splitlines()))
        # The classifier's table and the `provider_uid` derivation's table, and no third one: a
        # second mapping anywhere else would be a second classifier.
        assert mappers == ["integration.py", "invariants.py"]

    # [utest->req~sessions-provider-derivation-closed-procedure~1]
    async def test_every_providerdata_read_runs_on_the_selected_integration(self):
        # The one `getUser(subject)` call site in the tree takes its Admin client as an argument;
        # it never reaches for an ambient or default app.
        callers = sorted(path.name for path in SRC.rglob("*.py")
                         if "auth.get_user" in path.read_text())
        assert callers == ["create_user.py"]
        # The read a stage names runs on the client the issuer match selected, and on no other.
        selected = object()
        flow = Flow(lookup=FakeLookup(GOOGLE), admin=selected)
        await flow.complete("google", variant=IdentityProvider.google)
        assert flow.lookup.clients == [selected]
        assert issuer_selected_admin_client(integrations(selected), TEST_ISSUER) is selected


# --- Call sites -------------------------------------------------------------------------------


class TestReadCallSites:
    # [utest->req~sessions-providerdata-read-call-sites~1]
    def test_the_read_points_are_exactly_the_enumerated_five(self):
        assert {point.value for point in ProviderDataReadPoint} == {
            "anonymous_create_user_completion", "registered_create_user_completion",
            "upgrade_anonymous_completion", "web_anonymous_grant_gate",
            "claim_registered_grant_completion"}
        for point in ProviderDataReadPoint:
            assert assert_provider_data_read_point(point) is point

    # [utest->req~sessions-providerdata-read-call-sites~1]
    def test_no_other_operation_reads_provider_data(self):
        # `POST /auth/sync`, `GET /users/me` and every other ordinary authenticated request are
        # not read points, and neither is a reconciliation job or an admin surface.
        for outsider in ("auth_sync", "users_me", "authenticated_request", "reconciliation_job",
                         "admin_reconciliation_surface"):
            with pytest.raises(IdentityError):
                assert_provider_data_read_point(outsider)
        assert PROVIDER_RECONCILIATION_JOBS == frozenset()

    # [utest->req~sessions-providerdata-read-call-sites~1]
    def test_only_creation_and_upgrade_persist_provider_fields(self):
        for point in (ProviderDataReadPoint.anonymous_create_user_completion,
                      ProviderDataReadPoint.registered_create_user_completion,
                      ProviderDataReadPoint.upgrade_anonymous_completion):
            assert_may_write_provider_fields(point)
        for read_only in (ProviderDataReadPoint.web_anonymous_grant_gate,
                          ProviderDataReadPoint.claim_registered_grant_completion):
            with pytest.raises(IdentityError):
                assert_may_write_provider_fields(read_only)


class TestProviderUidFromTheSameRead:
    # [utest->req~sessions-provider-uid-from-same-read~1]
    def test_the_uid_comes_from_the_matching_entry_of_that_read(self):
        google = [entry("google.com", "google-account-id")]
        apple = [entry("apple.com", "apple-user-id")]
        assert provider_uid_for(IdentityProvider.google, google) == "google-account-id"
        assert provider_uid_for(IdentityProvider.apple, apple) == "apple-user-id"
        # `NULL` for `anonymous`, and non-empty for the two registered providers.
        assert provider_uid_for(IdentityProvider.anonymous, []) is None
        with pytest.raises(ProviderLookupFailedError):
            provider_uid_for(IdentityProvider.google, [entry("google.com", "")])

    # [utest->req~sessions-provider-uid-from-same-read~1]
    def test_it_is_never_taken_from_client_input_headers_claims_email_or_display_name(self):
        assert_provider_uid_source(ProviderUidSource.firebase_provider_data)
        for source in (ProviderUidSource.client_input, ProviderUidSource.request_header,
                       ProviderUidSource.token_claim, ProviderUidSource.email,
                       ProviderUidSource.display_name):
            with pytest.raises(IdentityError):
                assert_provider_uid_source(source)


# --- Lookup failure ---------------------------------------------------------------------------


class TestLookupFailure:
    # [utest->req~sessions-providerdata-lookup-failure~1]
    def test_only_a_successful_well_formed_record_yields_a_provider(self):
        assert provider_from_lookup([]) is IdentityProvider.anonymous
        # A failed or indeterminate lookup is never read as an empty `providerData` result.
        with pytest.raises(ProviderLookupFailedError) as missing:
            provider_from_lookup(None)
        assert missing.value.result is AuthEventResult.firebase_lookup_unavailable
        for malformed in ("not-a-sequence", b"bytes"):
            with pytest.raises(ProviderLookupFailedError):
                provider_from_lookup(malformed)
        for failure in LookupFailure:
            with pytest.raises(ProviderLookupFailedError):
                provider_from_lookup([], failure=failure)

    # [utest->req~sessions-providerdata-lookup-failure~1]
    async def test_a_record_without_provider_data_is_a_failed_lookup_not_an_empty_result(self):
        """The production read is the one that matters: a record whose `providerData` is absent,
        null, or not a sequence of entries fails closed instead of being read as an empty result,
        which would classify the account `anonymous` and persist that."""
        import firebase_admin.auth as admin_auth  # noqa: PLC0415

        for record in (SimpleNamespace(email=None, email_verified=False, provider_data=None),
                       SimpleNamespace(email=None, email_verified=False),
                       SimpleNamespace(email=None, email_verified=False,
                                       provider_data="not-a-sequence"),
                       None):
            with (patch.object(admin_auth, "get_user", return_value=record),
                  pytest.raises(ProviderLookupFailedError) as rejected):
                await firebase_admin_get_user(ADMIN_CLIENT, "subject-1")
            assert rejected.value.result is AuthEventResult.firebase_lookup_unavailable
            assert rejected.value.retryable is True

        # A successful, well-formed record still yields its entries — an empty tuple included.
        well_formed = SimpleNamespace(email=None, email_verified=False, provider_data=())
        with patch.object(admin_auth, "get_user", return_value=well_formed):
            assert await firebase_admin_get_user(ADMIN_CLIENT,
                                                "subject-1") == AdminLookupResult()

    # [utest->req~sessions-providerdata-lookup-failure~1]
    async def test_a_failed_lookup_persists_nothing_at_all(self):
        assert LOOKUP_FAILURE_PERSISTS == frozenset()
        lookup = FakeLookup(failures=[_lookup_error(LookupFailure.transient)] * 3)
        flow = Flow(lookup=lookup)
        with pytest.raises(CreateUserRejection):
            await flow.complete("anonymous")
        # No user, no identity row, no provider, no `registered_at`, no email, no grant.
        assert flow.accounts.users == {}
        assert flow.accounts.reserved == {}

    # [utest->req~sessions-failure-classes-distinct~1]
    def test_the_two_failure_classes_stay_distinct(self):
        deleted = lookup_failure(LookupFailure.user_not_found)
        for indeterminate in (LookupFailure.transient, LookupFailure.infrastructure,
                              LookupFailure.malformed_response, LookupFailure.indeterminate):
            other = lookup_failure(indeterminate)
            assert other.result is AuthEventResult.firebase_lookup_unavailable
            assert other.result is not deleted.result
            assert other.retryable is True
        assert deleted.result is AuthEventResult.firebase_user_unresolved
        assert deleted.retryable is False

    # [utest->req~sessions-failure-user-not-found~1]
    async def test_a_deleted_firebase_subject_is_non_retryable_and_creates_nothing(self):
        lookup = FakeLookup(failures=[_lookup_error(LookupFailure.user_not_found)] * 3)
        flow = Flow(lookup=lookup)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is AuthEventResult.firebase_user_unresolved
        # Surfaced to the client through the existing `auth_required` class.
        assert raised.value.error_code == ClientErrorClass.auth_required
        assert surface(AuthEventResult.firebase_user_unresolved)[0] == \
            ClientErrorClass.auth_required
        # Non-retryable: the one attempt is not repeated, and no account is created or upgraded.
        assert lookup.calls == 1
        assert flow.accounts.users == {}
        assert flow.audited() == [AuthEventResult.firebase_user_unresolved]

    # [utest->req~sessions-failure-transient-unavailable~1]
    @pytest.mark.parametrize("failure", [LookupFailure.transient, LookupFailure.infrastructure,
                                         LookupFailure.malformed_response,
                                         LookupFailure.indeterminate])
    async def test_transient_and_infrastructure_failures_retry_then_surface_unavailable(self,
                                                                                       failure):
        lookup = FakeLookup(failures=[_lookup_error(failure)] * 3)
        flow = Flow(lookup=lookup)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        # Audited distinctly from a client-sent bad provider, and surfaced only after the
        # in-request retry budget is exhausted.
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert raised.value.result is not AuthEventResult.provider_not_linked
        assert raised.value.error_code == ClientErrorClass.verification_temporarily_unavailable
        assert lookup.calls == 3
        assert flow.accounts.users == {}

    # [utest->req~sessions-failure-challenge-consumed~1]
    async def test_a_rejected_attempt_consumes_its_challenge_with_no_recycling_path(self):
        from nativespeaker.api.auth.challenges import ChallengeState
        from nativespeaker.api.auth.procedures import ChallengeRejection
        lookup = FakeLookup(failures=[_lookup_error(LookupFailure.user_not_found)])
        flow = Flow(lookup=lookup)
        row = await flow.prepare()
        with pytest.raises(CreateUserRejection):
            await flow.h.service.complete(AuthOperation.create_user, "anonymous",
                                          row.challenge_id, flow.context, flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "anonymous"})
        assert flow.row().state is ChallengeState.consumed
        # The client prepares a fresh challenge and retries; the consumed one never recycles.
        with pytest.raises(ChallengeRejection) as retry:
            await flow.h.service.complete(AuthOperation.create_user, "anonymous",
                                          row.challenge_id, flow.context, flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "anonymous"})
        assert retry.value.result is AuthEventResult.challenge_consumed

    # [utest->req~sessions-failure-web-grant-gate-fails-closed~1]
    def test_a_web_gate_lookup_failure_denies_that_grant_and_nothing_else(self):
        from nativespeaker.api.auth.proof_endpoints import (
            GATE_DENIES,
            GATE_NEVER_DENIES,
            GATE_NEVER_DENIES_PAID_ENTITLEMENT,
            web_anonymous_grant_gate,
        )
        assert GATE_DENIES == frozenset({AuthOperation.claim_anonymous_grant})
        # Login, account creation, upgrade, sync, restore and every paid entitlement path stay
        # outside what a failed gate lookup may deny.
        for operation in (AuthOperation.create_user,
                          AuthOperation.upgrade_anonymous_to_registered,
                          AuthOperation.sync, AuthOperation.restore_subscription,
                          AuthOperation.claim_registered_grant, AuthOperation.sign_out_all):
            assert operation in GATE_NEVER_DENIES
        assert GATE_NEVER_DENIES_PAID_ENTITLEMENT is True
        # The gate itself fails closed: no `providerData` means no grant, never a granted one.
        row = identity_row(provider=IdentityProvider.google, provider_uid="google-account-id")
        with pytest.raises(ProviderLookupFailedError) as raised:
            web_anonymous_grant_gate(row, None,
                                     lookup_failure=_lookup_error(LookupFailure.transient))
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable


# --- The classifier ---------------------------------------------------------------------------


class TestClassifier:
    # [utest->req~sessions-classifier-closed-mapping~1]
    def test_the_mapping_is_closed(self):
        assert classify_provider([]) is IdentityProvider.anonymous
        assert classify_provider([entry("google.com")]) is IdentityProvider.google
        assert classify_provider([entry("apple.com")]) is IdentityProvider.apple
        for rejected in ([entry("password")], [entry("google.com"), entry("apple.com")],
                         [entry("google.com"), entry("google.com")], [entry("")]):
            with pytest.raises(ProviderClassificationError):
                classify_provider(rejected)

    # [utest->req~sessions-classify-no-entries-anonymous~1]
    def test_no_entries_classifies_as_anonymous(self):
        assert classify_provider([]) is IdentityProvider.anonymous

    # [utest->req~sessions-classify-google~1]
    def test_exactly_one_google_entry_classifies_as_google(self):
        assert classify_provider([entry("google.com", "google-account-id")]) is \
            IdentityProvider.google

    # [utest->req~sessions-classify-apple~1]
    def test_exactly_one_apple_entry_classifies_as_apple(self):
        assert classify_provider([entry("apple.com", "apple-user-id")]) is IdentityProvider.apple

    # [utest->req~sessions-classify-both-providers-reject~1]
    async def test_entries_for_both_providers_reject_with_no_persistence(self):
        with pytest.raises(ProviderClassificationError):
            classify_provider([entry("google.com"), entry("apple.com")])
        both = AdminLookupResult(provider_data=(entry("google.com"), entry("apple.com")))
        flow = Flow(lookup=FakeLookup(both))
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("google", variant=IdentityProvider.google)
        assert raised.value.cause is ProviderNotLinkedCause.invalid_provider_data_shape
        assert flow.accounts.users == {}

    # [utest->req~sessions-classify-other-shape-reject~1]
    @pytest.mark.parametrize("provider_id", ["password", "phone", "saml.acme", "oidc.acme",
                                             "facebook.com", "custom"])
    def test_any_other_shape_rejects(self, provider_id):
        with pytest.raises(ProviderClassificationError):
            classify_provider([entry(provider_id)])

    # [utest->req~sessions-classifier-no-first-entry-shortcut~1]
    def test_the_first_recognized_entry_is_never_taken_and_extras_are_never_discarded(self):
        with pytest.raises(ProviderClassificationError):
            classify_provider([entry("google.com"), entry("password")])
        with pytest.raises(ProviderClassificationError):
            classify_provider([entry("password"), entry("google.com")])
        # Non-empty `providerData` is never classified `anonymous`.
        for shape in ([entry("password")], [entry("google.com"), entry("google.com")]):
            with pytest.raises(ProviderClassificationError):
                classify_provider(shape)

    # [utest->req~sessions-classifier-no-first-entry-shortcut~1]
    def test_the_token_sign_in_provider_claim_is_never_used(self):
        with pytest.raises(CreateUserError):
            classify_admin_provider_data([entry("google.com")],
                                         token_claims={"firebase":
                                                       {"sign_in_provider": "apple.com"}})

    # [utest->req~sessions-pinned-project-bounds-provider-kinds~1]
    def test_the_pinned_project_bounds_the_kinds_and_the_classifier_is_the_only_backstop(self):
        assert ALLOWED_SIGN_IN_PROVIDERS == frozenset({"anonymous", "google", "apple"})
        assert set(PROVIDER_ID_TO_PROVIDER) == {"google.com", "apple.com"}
        # No further shape-refusal machinery: every other kind is refused by the classifier alone.
        for kind in ("password", "phone", "saml.acme", "oidc.acme", "custom"):
            with pytest.raises(UnrecognizedProviderError):
                from nativespeaker.api.auth.integration import FirebaseIntegrations
                FirebaseIntegrations.classify_provider([type("E", (), {"provider_id": kind})()])


# --- Declaration match ------------------------------------------------------------------------


class TestDeclarationMatch:
    # [utest->req~sessions-declaration-match~1]
    def test_the_classification_must_equal_the_declaration(self):
        assert assert_declared_provider(IdentityProvider.google, IdentityProvider.google) is \
            IdentityProvider.google
        # No declaration to match is left to the call site that has one.
        assert assert_declared_provider(IdentityProvider.anonymous, None) is \
            IdentityProvider.anonymous
        with pytest.raises(ProviderDeclarationMismatchError) as raised:
            assert_declared_provider(IdentityProvider.apple, IdentityProvider.google)
        assert raised.value.classified is IdentityProvider.apple
        assert raised.value.declared is IdentityProvider.google

    # [utest->req~sessions-declaration-anonymous-create-user~1]
    async def test_anonymous_creation_requires_an_empty_result_and_names_the_registered_flow(self):
        # A successful lookup with a Google login attached refuses the anonymous flow, names the
        # registered one, and records nothing — never the account as registered instead.
        flow = Flow(lookup=FakeLookup(GOOGLE))
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.error_code == CREATE_FLOW_MISMATCH_CLASS
        assert raised.value.required_flow is CreateFlow.registered
        assert flow.accounts.users == {}
        assert flow.accounts.identities.find(TEST_ISSUER, flow.context.subject) is None
        # The empty result is what the anonymous flow requires.
        created = await Flow().complete("anonymous")
        assert created.identity.provider is IdentityProvider.anonymous

    # [utest->req~sessions-declaration-registered-create-user~1]
    async def test_registered_creation_requires_the_declared_provider_and_never_stores_anonymous(
            self):
        empty = Flow()
        with pytest.raises(CreateUserRejection) as raised:
            await empty.complete("google", variant=IdentityProvider.google)
        assert raised.value.error_code == CREATE_FLOW_MISMATCH_CLASS
        assert raised.value.required_flow is CreateFlow.anonymous
        assert empty.accounts.users == {}
        # A declared provider the classifier does not return is refused as well.
        mismatch = Flow(lookup=FakeLookup(APPLE))
        with pytest.raises(CreateUserRejection):
            await mismatch.complete("google", variant=IdentityProvider.google)
        assert mismatch.accounts.users == {}
        # Agreement creates the registered account with the classified provider.
        agreed = Flow(lookup=FakeLookup(GOOGLE))
        created = await agreed.complete("google", variant=IdentityProvider.google)
        assert created.identity.provider is IdentityProvider.google
        assert created.identity.provider_uid == "google-account-id"

    # [utest->req~sessions-declaration-registered-create-user~1]
    def test_confirm_declaration_names_the_flow_from_the_classification(self):
        with pytest.raises(CreateUserRejection) as raised:
            confirm_declaration(IdentityProvider.google, AdminLookupResult())
        assert raised.value.required_flow is CreateFlow.anonymous
        assert raised.value.cause is ProviderNotLinkedCause.empty_provider_data

    # [utest->req~sessions-declaration-upgrade-anonymous~1]
    def test_upgrade_requires_the_same_agreement_including_the_idempotent_repeat(self):
        google = [entry("google.com", "google-account-id")]
        assert upgrade_target_provider(IdentityProvider.google, google) is IdentityProvider.google
        with pytest.raises(ProviderNotConfirmedError):
            upgrade_target_provider(IdentityProvider.apple, google)
        # The idempotent repeat, where the stored provider already equals the declaration, still
        # requires the live classifier to agree with it.
        stored = identity_row(provider=IdentityProvider.google, provider_uid="google-account-id")
        decision = upgrade_completion_decision(stored, IdentityProvider.google,
                                               provider_data=google)
        assert decision.provider is IdentityProvider.google
        from nativespeaker.api.auth.procedures import ChallengeRejection
        with pytest.raises(ChallengeRejection) as diverged:
            upgrade_completion_decision(stored, IdentityProvider.google,
                                        provider_data=[entry("apple.com", "apple-user-id")])
        assert diverged.value.result is AuthEventResult.provider_transition_not_allowed


# --- Persistence ------------------------------------------------------------------------------


class TestPersistence:
    # [utest->req~sessions-provider-persistence-single-transaction~1]
    def test_the_provider_and_its_uid_are_written_in_the_one_transaction(self):
        row = identity_row()
        transaction = object()
        written = write_provider_uid(row, "google-account-id",
                                    provider=IdentityProvider.google,
                                    row_transaction=transaction, uid_transaction=transaction)
        assert written.provider is IdentityProvider.google
        assert written.provider_uid == "google-account-id"
        with pytest.raises(IdentityError):
            write_provider_uid(row, "google-account-id", provider=IdentityProvider.google,
                               row_transaction=transaction, uid_transaction=object())

    # [utest->req~sessions-provider-persistence-single-transaction~1]
    async def test_the_completion_transaction_aligns_provider_and_registered_at(self):
        created = await Flow(lookup=FakeLookup(GOOGLE)).complete(
            "google", variant=IdentityProvider.google)
        assert created.user.registered_at == NOW
        assert_registered_at_pairing(created.identity.provider, created.user.registered_at)
        anonymous = await Flow().complete("anonymous")
        assert anonymous.user.registered_at is None
        assert_registered_at_pairing(anonymous.identity.provider, anonymous.user.registered_at)

    # [utest->req~sessions-provider-registered-at-pairing~1]
    def test_registered_at_is_set_if_and_only_if_the_provider_is_registered(self):
        assert_registered_at_pairing(IdentityProvider.anonymous, None)
        for provider in (IdentityProvider.google, IdentityProvider.apple):
            assert_registered_at_pairing(provider, NOW)
            with pytest.raises(ProfileError):
                assert_registered_at_pairing(provider, None)
        # No third state: an anonymous provider with a timestamp is corruption, not a class.
        with pytest.raises(ProfileError):
            assert_registered_at_pairing(IdentityProvider.anonymous, NOW)

    # [utest->req~sessions-stored-provider-sole-classifier~1]
    def test_the_stored_provider_is_the_sole_per_request_classifier(self):
        row = identity_row(provider=IdentityProvider.google, provider_uid="google-account-id")
        for consumer in (ProviderConsumer.registered_grant_gating, ProviderConsumer.claim_path,
                         ProviderConsumer.authorization_branch, ProviderConsumer.audit_branch,
                         ProviderConsumer.entitlement_handling):
            assert authoritative_provider(row, consumer) is IdentityProvider.google
        # Revocation reads no provider, and no per-request path rederives the classification.
        with pytest.raises(IdentityError):
            authoritative_provider(row, ProviderConsumer.refresh_token_revocation)
        for outsider in ("auth_sync", "users_me", "authenticated_request"):
            with pytest.raises(IdentityError):
                assert_provider_data_read_point(outsider)


# --- Firebase integration selection -----------------------------------------------------------


class TestIntegrationSelection:
    # [utest->req~sessions-admin-client-by-issuer-match~1]
    def test_every_admin_call_selects_its_client_by_issuer_match(self):
        selected = integrations(ADMIN_CLIENT)
        assert selected.admin_client_for_issuer(TEST_ISSUER) is ADMIN_CLIENT
        # No ambient, default or global client to fall back to.
        with pytest.raises(InvalidExternalJwtError):
            selected.admin_client_for_issuer("https://securetoken.google.com/other")
        assert not hasattr(selected, "default_admin_client")
        # Selection is never derived from the subject, the provider or client input: the selector
        # takes the issuer and nothing else.
        from inspect import signature
        assert list(signature(selected.admin_client_for_issuer).parameters) == ["issuer"]

    # [utest->req~sessions-integration-select-request-driven~1]
    def test_request_driven_work_selects_on_the_request_verified_issuer(self):
        selected = integrations(ADMIN_CLIENT)
        assert REQUEST_DRIVEN_ADMIN_SITES == frozenset({AdminCallSite.provider_data_read,
                                                        AdminCallSite.sign_out_all_revocation})
        for site in REQUEST_DRIVEN_ADMIN_SITES:
            assert selected.admin_client_for_request(verified_issuer=TEST_ISSUER,
                                                     site=site) is ADMIN_CLIENT
        # The provider read points reach the same selector.
        assert issuer_selected_admin_client(selected, TEST_ISSUER) is ADMIN_CLIENT
        # An administrative site never selects on the request's issuer.
        with pytest.raises(AdminSelectionSiteError):
            selected.admin_client_for_request(verified_issuer=TEST_ISSUER,
                                              site=AdminCallSite.operator_block_revocation)

    # [utest->req~sessions-integration-select-administrative~1]
    def test_administrative_work_selects_on_the_stored_issuer(self):
        selected = integrations(ADMIN_CLIENT)
        assert ADMINISTRATIVE_ADMIN_SITES == frozenset({
            AdminCallSite.operator_block_revocation,
            AdminCallSite.identity_retirement_revocation})
        for action, site in ADMINISTRATIVE_ADMIN_CALL_SITES.items():
            assert site in ADMINISTRATIVE_ADMIN_SITES
            assert admin_client_for_identity(selected, identity_row(),
                                             action=action) is ADMIN_CLIENT
        assert selected.admin_client_for_stored_issuer(
            stored_issuer=TEST_ISSUER,
            site=AdminCallSite.identity_retirement_revocation) is ADMIN_CLIENT
        # A request-driven site never selects on a stored issuer.
        with pytest.raises(AdminSelectionSiteError):
            selected.admin_client_for_stored_issuer(stored_issuer=TEST_ISSUER,
                                                    site=AdminCallSite.provider_data_read)

    # [utest->req~sessions-integration-selection-fails-closed~1]
    def test_selection_fails_closed_on_either_path(self):
        selected = integrations(ADMIN_CLIENT)
        # A request-verified issuer that is not the configured one rejects the operation.
        with pytest.raises(InvalidExternalJwtError):
            selected.admin_client_for_request(verified_issuer="https://securetoken.google.com/x",
                                              site=AdminCallSite.provider_data_read)
        with pytest.raises(InvalidExternalJwtError):
            issuer_selected_admin_client(selected, "https://securetoken.google.com/x")
        # A stored issuer that no longer matches is a hard error, never a revocation against
        # another project.
        with pytest.raises(InvalidExternalJwtError):
            admin_client_for_identity(selected,
                                      identity_row(issuer="https://securetoken.google.com/x"),
                                      action=AdministrativeAction.retire_identity)
        # A `providerData` read whose Admin selection fails substitutes no assumed provider.
        with pytest.raises(ProviderLookupFailedError):
            issuer_selected_admin_client(integrations(None), TEST_ISSUER)

    # [utest->req~sessions-stored-issuer-equals-configured~1]
    def test_a_stored_issuer_always_equals_the_configured_one(self):
        from nativespeaker.api.auth.external_identities import (
            IDENTITY_LOOKUP_KEY,
            assert_lookup_fields,
        )
        selected = integrations(ADMIN_CLIENT)
        assert selected.configured_issuer == selected.sole.issuer == TEST_ISSUER
        row = identity_row()
        assert row.issuer == selected.configured_issuer
        assert admin_client_for_identity(selected, row) is ADMIN_CLIENT
        # Identity lookup stays keyed on `(issuer, subject)` and needs no other ownership key.
        assert IDENTITY_LOOKUP_KEY == ("issuer", "subject")
        assert_lookup_fields(IDENTITY_LOOKUP_KEY)
        with pytest.raises(IdentityError):
            assert_lookup_fields(("issuer", "subject", "user_id"))

    # [utest->req~sessions-database-change-first-on-revocation~1]
    def test_the_lifecycle_write_commits_first_and_survives_a_failed_revocation(self):
        for action in AdministrativeAction:
            outcome = administrative_write(action, revocation_failed=True)
            # Committed and authoritative, with the failure surfaced rather than swallowed.
            assert outcome.committed is True
            assert outcome.revocation_failed is True
            assert outcome.operator_retry_available is True
            assert outcome.lifecycle_write
            # A selection failure never undoes it either: no rollback is available at all.
            with pytest.raises(IdentityError):
                administrative_write(action, revocation_failed=True, rollback_requested=True)
