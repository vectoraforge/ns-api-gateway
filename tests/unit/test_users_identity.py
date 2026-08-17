"""User creation and in-place anonymous upgrade: pre-auth identities and their promotion, the
identity transitions the two endpoints make, their challenge-bound provider variant, where their
handler admission controls sit, and the identity constraints each phase enforces."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid7

import pytest
import yaml

from nativespeaker.api.auth import users as users_module
from nativespeaker.api.auth.audit import (
    AttemptPhase,
    AuditAlreadyWrittenError,
    AuthAttempt,
    AuthAuditWriter,
    AuthEventResult,
    resolved_actor,
)
from nativespeaker.api.auth.barrier import (
    ResolutionOutcome,
    VerifiedIdentityContext,
    barrier_result_for,
)
from nativespeaker.api.auth.challenges import ChallengeRow, IdentityBinding
from nativespeaker.api.auth.external_identities import (
    ExternalIdentities,
    ExternalIdentityRow,
    IdentityAlreadyLinkedError,
    IdentityError,
    IdentityState,
    ProviderLookupFailedError,
    assert_no_identity_delete,
    assert_provider_uid_check,
    assert_reservation_index,
    assign_provider_uid,
    in_reservation_scope,
    may_delete_identity_rows,
    never_linked,
    provider_uid_for,
    retire,
    upgrade_to_registered,
)
from nativespeaker.api.auth.integration import FirebaseIntegration, FirebaseIntegrations
from nativespeaker.api.auth.invariants import InvariantError
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.movement import (
    MovementClassification,
    MovementError,
    movement_event,
    record_movement_attempt,
)
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    InvalidOperationVariantError,
    normalize_variant,
)
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.auth.tokens import FirebaseIdTokenVerifier, InvalidExternalJwtError
from nativespeaker.api.auth.users import (
    CREATE_USER_ROUTE,
    PREAUTH_REJECTED_ROUTES,
    UPGRADE_ROUTE,
    IdentityContextSource,
    UpgradeBranch,
    UsersError,
    apply_upgrade,
    assert_admission_entries_named_in_08,
    assert_counters_not_fused,
    assert_no_anonymous_proof,
    assert_no_attestation,
    assert_no_free_credits,
    assert_no_restore_proof,
    assert_no_secondary_auth_state,
    assert_preauth_admission_owner,
    assert_shared_challenge_contracts,
    assert_upgrade_gateway_limit,
    barrier_verification_next,
    client_class_for,
    complete_create_user,
    completion_admission,
    completion_variant_matches,
    context_pair,
    create_user_authentication,
    create_user_challenge_source,
    create_user_completion_constraints,
    create_user_operation,
    create_user_prepare_constraints,
    firebase_identity_lookup,
    gateway_limit_key,
    identity_pair,
    issuer_selected_admin_client,
    lookup_admission,
    preauth_admitted,
    preauth_context,
    preauth_outcome,
    preauth_rejection,
    prepare_admission,
    prepare_variant,
    resolves_as_linked,
    secondary_subject_entry,
    unavailable_account,
    upgrade_audit_context,
    upgrade_completion_decision,
    upgrade_gateway_admission,
    upgrade_linked_identity,
    upgrade_prepare_constraints,
    users_operation,
    variant_mismatch,
)
from nativespeaker.api.ratelimit.config import (
    CREATE_USER_SECONDARY_ENTRY,
    GatewayRateLimitEntry,
    GatewayRateLimitsConfig,
    RateLimitsConfig,
)
from nativespeaker.api.ratelimit.keys import (
    UNRESOLVED_ADDRESS_KEY,
    AddressSource,
    DerivedIdentifier,
    IdentitySource,
    KeyComponent,
    KeyMaterial,
    LimiterKeyError,
    gateway_resolved_address,
)
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import (
    AdmissionLedger,
    AdmissionOrderError,
    ExpensiveStep,
    GetUserCallSite,
)
from nativespeaker.api.ratelimit.rejection import AdmissionPhaseError, SecurityTelemetry
from unit.conftest import PUBLIC_KEY_PEM, TEST_ISSUER
from unit.test_auth_challenges import Harness
from unit.test_auth_challenges import preauth_context as preauth_challenge_context

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "migrations" / "20260816_01_auth-refactor-schema.sql").read_text()
SHIPPED = yaml.safe_load((ROOT / "config" / "config.yaml").read_text())

SUBJECT = "verified-subject"


def linked_ctx(**overrides) -> VerifiedIdentityContext:
    values: dict[str, Any] = {"issuer": TEST_ISSUER, "subject": SUBJECT,
              "outcome": ResolutionOutcome.linked,
              "user_id": uuid7(), "external_identity_id": uuid7(),
              "provider": IdentityProvider.anonymous}
    values.update(overrides)
    return VerifiedIdentityContext(**values)


def preauth_ctx(**overrides) -> VerifiedIdentityContext:
    values: dict[str, Any] = {"issuer": TEST_ISSUER, "subject": SUBJECT, "outcome": ResolutionOutcome.pre_auth}
    values.update(overrides)
    return VerifiedIdentityContext(**values)


def identity_row(user_id: UUID | None = None, **overrides) -> ExternalIdentityRow:
    values: dict[str, Any] = {"id": uuid7(), "user_id": user_id or uuid7(), "issuer": TEST_ISSUER,
              "subject": SUBJECT, "provider": IdentityProvider.anonymous}
    values.update(overrides)
    return ExternalIdentityRow(**values)


def provider_data(provider_id: str, uid: str = "provider-account-uid") -> list[dict[str, str]]:
    return [{"provider_id": provider_id, "uid": uid}]


def shipped_policies() -> dict[str, tuple[KeyComponent, ...]]:
    config = RateLimitsConfig(**SHIPPED["rate_limits"])
    return {name: entry.policy for name, entry in config.entries.items()}


def test_verifier() -> FirebaseIdTokenVerifier:
    return FirebaseIdTokenVerifier(issuer=TEST_ISSUER, audience="test-project",
                                   key_resolver=lambda _token: PUBLIC_KEY_PEM)


def gateway_entry() -> GatewayRateLimitEntry:
    return GatewayRateLimitsConfig(**SHIPPED["gateway_rate_limits"]).upgrade_anonymous


# --- Pre-auth identities and promotion ---------------------------------------------------------


class TestIdentityContext:
    # [utest->req~users-identity-context-from-backend-verified-token~1]
    def test_the_identity_context_is_the_backend_verified_pair(self):
        assert identity_pair(TEST_ISSUER, SUBJECT,
                             source=IdentityContextSource.backend_verified_id_token) == \
            (TEST_ISSUER, SUBJECT)
        assert context_pair(preauth_ctx()) == (TEST_ISSUER, SUBJECT)

    # [utest->req~users-identity-context-from-backend-verified-token~1]
    @pytest.mark.parametrize("source", [IdentityContextSource.gateway_jwt_filter_metadata,
                                        IdentityContextSource.request_header,
                                        IdentityContextSource.client_field])
    def test_no_other_source_establishes_the_identity_context(self, source):
        with pytest.raises(UsersError):
            identity_pair(TEST_ISSUER, SUBJECT, source=source)

    # [utest->req~users-preauth-identity-definition~1]
    def test_no_identity_row_is_pre_auth_and_a_historical_row_never_is(self):
        assert preauth_outcome(None) is ResolutionOutcome.pre_auth
        assert preauth_outcome(identity_row()) is ResolutionOutcome.linked
        historical = identity_row(identity_state=IdentityState.historical)
        assert preauth_outcome(historical) is ResolutionOutcome.historical_identity

    # [utest->req~users-preauth-identity-definition~1]
    def test_admitting_a_pre_auth_principal_is_the_barriers_responsibility(self):
        assert_preauth_admission_owner("shared_pre_handler_barrier")
        with pytest.raises(UsersError):
            assert_preauth_admission_owner("create_user_completion_step")

    # [utest->req~users-preauth-context-is-verified-pair~1]
    def test_the_pre_auth_context_is_the_verified_pair_and_nothing_else(self):
        assert preauth_context(preauth_ctx()) == (TEST_ISSUER, SUBJECT)
        with pytest.raises(UsersError):
            preauth_context(linked_ctx())
        with pytest.raises(UsersError):
            preauth_context(preauth_ctx(user_id=uuid7()))
        with pytest.raises(UsersError):
            preauth_context(preauth_ctx(provider=IdentityProvider.google))


class TestBarrierAdmission:
    # [utest->req~users-barrier-admits-preauth-to-create-user-only~1]
    def test_only_create_user_admits_a_pre_auth_identity_in_both_phases(self):
        for phase in (RequestMode.prepare, RequestMode.completion):
            assert preauth_admitted(*CREATE_USER_ROUTE, phase=phase) is True
            assert barrier_result_for(ResolutionOutcome.pre_auth, *CREATE_USER_ROUTE) is None
        for route in PREAUTH_REJECTED_ROUTES:
            assert preauth_admitted(*route) is False

    # [utest->req~users-barrier-rejects-preauth-elsewhere~1]
    @pytest.mark.parametrize("route", PREAUTH_REJECTED_ROUTES)
    def test_every_other_route_rejects_a_pre_auth_identity(self, route):
        result, client_class = preauth_rejection(*route)
        assert result is AuthEventResult.preauth_identity_not_allowed
        assert client_class == ClientErrorClass.preauth_identity_not_allowed

    # [utest->req~users-barrier-rejects-preauth-elsewhere~1]
    def test_create_user_is_not_a_route_a_pre_auth_identity_is_rejected_on(self):
        with pytest.raises(UsersError):
            preauth_rejection(*CREATE_USER_ROUTE)

    # [utest->req~users-historical-and-blocked-account-unavailable~1]
    @pytest.mark.parametrize("route", [CREATE_USER_ROUTE, UPGRADE_ROUTE, ("GET", "/users/me")])
    def test_historical_and_blocked_are_unavailable_on_every_route(self, route):
        historical, historical_class = unavailable_account(
            ResolutionOutcome.historical_identity, *route)
        blocked, blocked_class = unavailable_account(ResolutionOutcome.blocked_user, *route)
        assert historical is AuthEventResult.historical_identity
        assert blocked is AuthEventResult.blocked_user
        assert historical is not blocked
        assert historical_class == blocked_class == ClientErrorClass.account_unavailable

    # [utest->req~users-historical-and-blocked-account-unavailable~1]
    def test_a_linked_identity_is_not_an_unavailable_account_state(self):
        with pytest.raises(UsersError):
            unavailable_account(ResolutionOutcome.linked, *CREATE_USER_ROUTE)


class TestUpgradeIsNotPreAuth:
    # [utest->req~users-upgrade-anonymous-not-preauth-endpoint~1]
    def test_the_upgrade_route_operates_on_an_existing_linked_identity(self):
        context = linked_ctx()
        assert upgrade_linked_identity(context) == context.external_identity_id
        with pytest.raises(UsersError):
            upgrade_linked_identity(preauth_ctx())

    # [utest->req~users-upgrade-anonymous-not-preauth-endpoint~1]
    def test_the_target_provider_comes_from_admin_provider_data_not_the_token(self):
        assert users_module.upgrade_target_provider(
            IdentityProvider.google, provider_data("google.com")) is IdentityProvider.google
        with pytest.raises(users_module.ProviderNotConfirmedError) as raised:
            users_module.upgrade_target_provider(IdentityProvider.google,
                                                 provider_data("apple.com"))
        assert raised.value.result is AuthEventResult.provider_not_linked


# --- What a successful `create_user` owes -------------------------------------------------------


class TestCreateUserSuccessObligations:
    def creation(self, **overrides):
        user_id = uuid7()
        transaction = object()
        values: dict[str, Any] = {"user_id": user_id, "identity": identity_row(user_id),
                  "completion_transaction": transaction, "identity_transaction": transaction}
        values.update(overrides)
        return complete_create_user(**values)

    # [utest->req~users-create-user-success-obligations~1]
    # [utest->req~users-create-user-creates-identity-row~1]
    def test_success_creates_the_identity_row_for_the_new_user(self):
        outcome = self.creation()
        assert outcome.identity.user_id == outcome.user_id
        assert outcome.identity.identity_state is IdentityState.active

    # [utest->req~users-identity-row-in-completion-transaction~1]
    # [utest->req~users-account-and-identity-row-atomic~1]
    def test_the_identity_row_is_written_in_the_completion_transaction(self):
        user_id = uuid7()
        with pytest.raises(UsersError):
            complete_create_user(user_id=user_id, identity=identity_row(user_id),
                                 completion_transaction=object(),
                                 identity_transaction=object())

    # [utest->req~users-account-and-identity-row-atomic~1]
    def test_the_identity_row_belongs_to_the_user_created_with_it(self):
        transaction = object()
        with pytest.raises(IdentityError):
            complete_create_user(user_id=uuid7(), identity=identity_row(),
                                 completion_transaction=transaction,
                                 identity_transaction=transaction)

    # [utest->req~users-create-user-returns-no-backend-token~1]
    def test_the_response_carries_no_backend_token(self):
        assert self.creation().backend_token is None
        with pytest.raises(UsersError):
            self.creation(backend_token="backend.jwt")

    # [utest->req~users-no-secondary-auth-state-or-generation~1]
    def test_there_is_no_secondary_auth_state_and_no_generation(self):
        assert_no_secondary_auth_state()
        with pytest.raises(UsersError):
            assert_no_secondary_auth_state({"session_generation": 2})
        with pytest.raises(UsersError):
            assert_no_secondary_auth_state(generation=1)

    # [utest->req~users-create-user-success-links-identity~1]
    # [utest->req~users-no-secondary-auth-state-or-generation~1]
    def test_the_same_token_resolves_as_linked_on_the_next_request(self):
        outcome = self.creation()
        assert resolves_as_linked(outcome.identity, preauth_ctx()) is True
        retired = retire(outcome.identity)
        assert resolves_as_linked(retired, preauth_ctx()) is False
        assert resolves_as_linked(outcome.identity, preauth_ctx(subject="other")) is False

    # [utest->req~users-create-user-no-free-credits~1]
    def test_create_user_allocates_no_free_credits_or_device_grants(self):
        assert_no_free_credits()
        with pytest.raises(UsersError):
            assert_no_free_credits(["anonymous_device_grant"])
        with pytest.raises(UsersError):
            self.creation(grant_writes=["free_credit_grant"])


# --- Identity transitions ------------------------------------------------------------------------


class TestIdentityTransitions:
    # [utest->req~users-allowed-provider-values~1]
    def test_the_only_allowed_provider_values(self):
        assert {str(provider) for provider in IdentityProvider} == {"anonymous", "google", "apple"}
        with pytest.raises(InvalidOperationVariantError):
            normalize_variant(AuthOperation.create_user, "facebook")

    # [utest->req~users-identity-rows-never-deleted~1]
    # [utest->req~users-rule-no-physical-delete~1]
    def test_identity_rows_are_never_deleted(self):
        with pytest.raises(IdentityError):
            assert_no_identity_delete("cleanup_job")
        assert may_delete_identity_rows("app") is False
        assert never_linked(None) is True

    # [utest->req~users-identity-rows-never-deleted~1]
    def test_retirement_is_an_in_place_administrative_transition(self):
        row = identity_row()
        tombstone = retire(row)
        assert tombstone.id == row.id
        assert tombstone.identity_state is IdentityState.historical
        assert (tombstone.issuer, tombstone.subject) == (row.issuer, row.subject)
        with pytest.raises(IdentityError):
            retire(row, administrative=False)

    # [utest->req~users-provider-uid-source-and-immutability~1]
    def test_provider_uid_comes_from_the_matching_provider_data_entry(self):
        assert provider_uid_for(IdentityProvider.anonymous, []) is None
        assert provider_uid_for(IdentityProvider.google,
                                provider_data("google.com", "google-account")) == "google-account"

    # [utest->req~users-provider-uid-source-and-immutability~1]
    def test_provider_uid_is_immutable_once_assigned(self):
        upgrade = AuthOperation.upgrade_anonymous_to_registered
        assert assign_provider_uid(None, "uid-1", operation=upgrade) == "uid-1"
        with pytest.raises(InvariantError):
            assign_provider_uid("uid-1", "uid-2", operation=upgrade)
        with pytest.raises(IdentityError):
            assign_provider_uid(None, "uid-1", operation=AuthOperation.create_user)

    # [utest->req~users-upgrade-flips-provider-in-place~1]
    def test_the_upgrade_flips_the_stored_provider_in_place(self):
        row = identity_row()
        transaction = object()
        upgraded = upgrade_to_registered(row, provider=IdentityProvider.google,
                                         provider_uid="google-account", transaction=transaction)
        assert upgraded.id == row.id and upgraded.user_id == row.user_id
        assert upgraded.provider is IdentityProvider.google
        assert upgraded.provider_uid == "google-account"
        assert upgraded.identity_state is IdentityState.active

    # [utest->req~users-upgrade-flips-provider-in-place~1]
    def test_a_registered_row_is_never_flipped_again(self):
        registered = identity_row(provider=IdentityProvider.google, provider_uid="google-account")
        with pytest.raises(IdentityError):
            upgrade_to_registered(registered, provider=IdentityProvider.apple,
                                  provider_uid="apple-account", transaction=object())


class TestIdentityRules:
    # [utest->req~users-rule-unique-issuer-subject~1]
    def test_unique_issuer_subject_holds_over_every_row(self):
        table = ExternalIdentities()
        table.link(identity_row())
        with pytest.raises(IdentityAlreadyLinkedError):
            table.link(identity_row())
        assert "UNIQUE (issuer, subject)" in MIGRATION

    # [utest->req~users-rule-unique-user-id~1]
    def test_unique_user_id_caps_a_user_at_one_identity_row(self):
        table = ExternalIdentities()
        user_id = uuid7()
        table.link(identity_row(user_id))
        with pytest.raises(IdentityError):
            table.link(identity_row(user_id, subject="second-subject"))
        assert "UNIQUE (user_id)" in MIGRATION

    # [utest->req~users-rule-identity-lifecycle-state~1]
    def test_an_identity_is_active_or_historical(self):
        assert {str(state) for state in IdentityState} == {"active", "historical"}
        assert "CREATE TYPE core.identity_state AS ENUM ('active', 'historical')" in MIGRATION

    # [utest->req~users-rule-partial-unique-provider-account~1]
    def test_the_provider_account_reservation_is_a_partial_unique_index(self):
        assert_reservation_index(columns=("issuer", "provider", "provider_uid"),
                                 predicate="provider_uid IS NOT NULL")
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=("issuer", "provider", "provider_uid"),
                                     predicate="provider_uid IS NOT NULL",
                                     table_wide_unique=True)
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=("issuer", "provider", "provider_uid"),
                                     predicate="", options=["NULLS NOT DISTINCT"])
        assert "ON core.external_identities (issuer, provider, provider_uid)" in MIGRATION
        assert "WHERE provider_uid IS NOT NULL" in MIGRATION

    # [utest->req~users-rule-partial-unique-provider-account~1]
    def test_historical_registered_rows_stay_reserved_and_anonymous_rows_stay_outside(self):
        registered = identity_row(provider=IdentityProvider.google, provider_uid="google-account",
                                  identity_state=IdentityState.historical)
        assert in_reservation_scope(registered) is True
        assert in_reservation_scope(identity_row()) is False

    # [utest->req~users-rule-provider-uid-nullability~1]
    def test_provider_uid_nullability_follows_the_identity_kind(self):
        assert_provider_uid_check(IdentityProvider.anonymous, None)
        assert_provider_uid_check(IdentityProvider.google, "google-account")
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.anonymous, "google-account")
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.apple, "")
        assert "(provider = 'anonymous' AND provider_uid IS NULL)" in MIGRATION


# --- Operation challenges --------------------------------------------------------------------------


class TestOperationChallenges:
    # [utest->req~users-state-changing-endpoints-are-operation-specific~1]
    def test_each_route_names_exactly_one_operation(self):
        assert users_operation(*CREATE_USER_ROUTE) is AuthOperation.create_user
        assert users_operation(*UPGRADE_ROUTE) is \
            AuthOperation.upgrade_anonymous_to_registered
        with pytest.raises(UsersError):
            users_operation("POST", "/auth/claim-anonymous-grant")

    # [utest->req~users-create-user-endpoint-single-operation~1]
    def test_create_user_endpoint_performs_only_create_user(self):
        assert create_user_operation(*CREATE_USER_ROUTE) is AuthOperation.create_user
        with pytest.raises(UsersError):
            create_user_operation(*UPGRADE_ROUTE)

    # [utest->req~users-shared-challenge-contracts-apply~1]
    # [utest->req~users-completion-shared-contracts~1]
    def test_both_endpoints_use_the_shared_challenge_contracts(self):
        for operation in (AuthOperation.create_user,
                          AuthOperation.upgrade_anonymous_to_registered):
            assert assert_shared_challenge_contracts(operation) is operation
        with pytest.raises(UsersError):
            assert_shared_challenge_contracts(AuthOperation.restore_subscription)

    # [utest->req~users-challenge-bound-provider-variant~1]
    # [utest->req~users-create-user-request-provider-field~1]
    def test_prepare_normalizes_and_binds_the_declared_provider(self):
        assert prepare_variant(AuthOperation.create_user, None) is IdentityProvider.anonymous
        assert prepare_variant(AuthOperation.create_user, "google") is IdentityProvider.google
        assert prepare_variant(AuthOperation.upgrade_anonymous_to_registered, "apple") is \
            IdentityProvider.apple
        with pytest.raises(InvalidOperationVariantError):
            prepare_variant(AuthOperation.upgrade_anonymous_to_registered, None)

    # [utest->req~users-challenge-bound-provider-variant~1]
    # [utest->req~users-create-user-request-provider-field~1]
    def test_completion_compares_the_declaration_byte_for_byte(self):
        row = ChallengeRow(challenge_id="c" * 22, operation=AuthOperation.create_user,
                           operation_variant=IdentityProvider.google,
                           binding=IdentityBinding(bound_external_identity_id=uuid7()),
                           expires_at=datetime.now(UTC))
        assert completion_variant_matches(row, "google") is True
        assert completion_variant_matches(row, "Google") is False
        assert completion_variant_matches(row, " google") is False
        assert completion_variant_matches(row, None) is False
        assert completion_variant_matches(row, "anonymous") is False

    # [utest->req~users-challenge-bound-provider-variant~1]
    def test_a_variant_mismatch_is_challenge_required(self):
        mismatch = variant_mismatch()
        assert mismatch.result is AuthEventResult.challenge_operation_mismatch
        assert mismatch.client_class == ClientErrorClass.challenge_required
        assert mismatch.consumes_challenge is True

    # [utest->req~users-challenge-bound-provider-variant~1]
    async def test_an_anonymous_challenge_cannot_complete_registered_creation(self):
        harness = Harness()
        context = preauth_challenge_context()
        endpoint = harness.endpoint(AuthOperation.create_user)
        await harness.service.prepare(AuthOperation.create_user, IdentityProvider.anonymous,
                                      context, endpoint)
        row = harness.store.only()
        assert row.operation_variant is IdentityProvider.anonymous
        with pytest.raises(ChallengeRejection) as raised:
            await harness.service.complete(AuthOperation.create_user, "google", row.challenge_id,
                                           context, harness.endpoint(AuthOperation.create_user))
        assert raised.value.result is AuthEventResult.challenge_operation_mismatch
        assert raised.value.error_code == ClientErrorClass.challenge_required
        # The mismatch consumed the challenge: the client must prepare a fresh one.
        assert harness.store.rows[row.challenge_id].state.value == "consumed"


# --- Handler admission control ----------------------------------------------------------------------


class TestHandlerAdmissionControl:
    def ledger(self, route=CREATE_USER_ROUTE, mode=RequestMode.completion) -> AdmissionLedger:
        return AdmissionLedger(*route, mode=mode)

    def receipt(self) -> AdmissionLedger:
        ledger = self.ledger()
        completion_admission(ledger, AuthOperation.create_user,
                             address=gateway_resolved_address(
                                 "203.0.113.7", source=AddressSource.envoy_direct_downstream))
        barrier_verification_next(
            ledger, request_shape_valid=True,
            identity_source=IdentityContextSource.backend_verified_id_token)
        return ledger

    # [utest->req~users-handler-admission-controls-required~1]
    def test_every_admission_control_is_a_named_entry_of_08(self):
        assert_admission_entries_named_in_08()
        with pytest.raises(UsersError):
            assert_admission_entries_named_in_08(("create_user_subject_burst",))

    # [utest->req~users-per-operation-prepare-limit~1]
    @pytest.mark.parametrize(("operation", "entry"),
                            [(AuthOperation.create_user, "create_user_prepare"),
                             (AuthOperation.upgrade_anonymous_to_registered,
                              "upgrade_anonymous_prepare")])
    def test_the_prepare_limit_runs_after_the_barrier_and_before_the_challenge(self, operation,
                                                                               entry):
        ledger = self.ledger(mode=RequestMode.prepare)
        policies = shipped_policies()
        with pytest.raises(UsersError):
            prepare_admission(ledger, operation, policies)
        ledger.verify_jwt()
        assert prepare_admission(ledger, operation, policies) == (entry,)
        assert entry in ledger.evaluated
        ledger.issue_challenge((entry,))
        with pytest.raises(UsersError):
            prepare_admission(ledger, operation, policies)

    # [utest->req~users-per-operation-completion-limit~1]
    def test_create_user_completion_is_bounded_by_its_client_ip_entry(self):
        ledger = self.ledger()
        completion_admission(ledger, AuthOperation.create_user,
                             address=gateway_resolved_address(
                                 "203.0.113.7", source=AddressSource.envoy_direct_downstream))
        assert ledger.evaluated == ["create_user"]

    # [utest->req~users-per-operation-completion-limit~1]
    def test_upgrade_completion_has_no_backend_per_operation_entry(self):
        ledger = self.ledger(route=UPGRADE_ROUTE)
        assert completion_admission(ledger, AuthOperation.upgrade_anonymous_to_registered,
                                    address=None) is None
        assert ledger.evaluated == []

    # [utest->req~users-completion-client-ip-counter-at-receipt~1]
    def test_the_client_ip_counter_is_charged_at_request_receipt(self):
        ledger = self.ledger()
        ledger.verify_jwt()
        with pytest.raises(UsersError):
            completion_admission(ledger, AuthOperation.create_user, address=None)

    # [utest->req~users-completion-client-ip-counter-at-receipt~1]
    def test_an_unresolvable_address_enters_the_shared_unresolved_bucket(self):
        resolved = gateway_resolved_address("198.51.100.9", source=AddressSource.unresolved)
        assert completion_admission(self.ledger(), AuthOperation.create_user,
                                    address=resolved) == UNRESOLVED_ADDRESS_KEY
        assert SHIPPED["rate_limits"]["client_address"]["unresolved_limit"] == "10/minute"

    # [utest->req~users-request-shape-and-barrier-verification-next~1]
    def test_request_shape_and_barrier_verification_run_after_the_ip_counter(self):
        ledger = self.ledger()
        with pytest.raises(UsersError):
            barrier_verification_next(
                ledger, request_shape_valid=True,
                identity_source=IdentityContextSource.backend_verified_id_token)
        completion_admission(ledger, AuthOperation.create_user, address=None)
        with pytest.raises(UsersError):
            barrier_verification_next(
                ledger, request_shape_valid=True,
                identity_source=IdentityContextSource.request_header)
        assert ledger.jwt_verified is False
        barrier_verification_next(
            ledger, request_shape_valid=True,
            identity_source=IdentityContextSource.backend_verified_id_token)
        assert ledger.jwt_verified is True

    # [utest->req~users-firebase-identity-lookup-counters-before-lookup~1]
    def test_both_lookup_counters_are_charged_before_the_lookup(self):
        ledger = self.receipt()
        charged: list[str] = []
        verdict = lookup_admission(ledger, GetUserCallSite.create_user_registered_completion,
                                   test=lambda _name: True,
                                   charge=lambda names: charged.extend(names))
        assert verdict.allowed is True
        assert "create_user_firebase_identity_lookup" in charged
        assert "create_user_firebase_identity_lookup_ip" in charged
        assert ledger.expensive_steps == [ExpensiveStep.firebase_lookup]

    # [utest->req~users-firebase-identity-lookup-counters-before-lookup~1]
    def test_an_exhausted_counter_charges_nothing_and_takes_no_lookup(self):
        ledger = self.receipt()
        charged: list[str] = []
        verdict = lookup_admission(
            ledger, GetUserCallSite.create_user_anonymous_completion,
            test=lambda name: name != "create_user_firebase_identity_lookup_ip",
            charge=lambda names: charged.extend(names))
        assert verdict.allowed is False
        assert charged == []
        assert ledger.expensive_steps == []

    # [utest->req~users-optional-subject-hash-secondary-entry~1]
    def test_the_secondary_subject_entry_is_late_and_non_blocking(self):
        ledger = self.ledger()
        with pytest.raises(UsersError):
            secondary_subject_entry(ledger)
        ledger = self.receipt()
        assert secondary_subject_entry(ledger, allowed=False) == CREATE_USER_SECONDARY_ENTRY
        assert ledger.refused is False

    # [utest->req~users-optional-subject-hash-secondary-entry~1]
    def test_the_secondary_entry_never_substitutes_for_the_client_ip_counter(self):
        ledger = self.ledger()
        ledger.verify_jwt()
        with pytest.raises(UsersError):
            secondary_subject_entry(ledger)

    # [utest->req~users-counters-never-fused-or-deferred~1]
    def test_the_ip_and_deployment_counters_are_never_fused(self):
        assert_counters_not_fused(shipped_policies())
        with pytest.raises(UsersError):
            assert_counters_not_fused({"create_user": (KeyComponent.ip, KeyComponent.issuer)})
        with pytest.raises(UsersError):
            assert_counters_not_fused({"create_user_firebase_identity_lookup":
                                       (KeyComponent.deployment, KeyComponent.subject_hash)})

    # [utest->req~users-admission-rejection-behavior~1]
    # [utest->req~users-admission-rejections-no-audit-row~1]
    def test_an_admission_rejection_is_a_429_that_writes_no_audit_row(self):
        attempt = AuthAttempt(*CREATE_USER_ROUTE, route_template=CREATE_USER_ROUTE[1])
        decision = LimitDecision(limiter="create_user", allowed=False, retry_after_seconds=30)
        rejection = users_module.admission_phase_rejection(attempt, SecurityTelemetry(), decision)
        assert rejection.error.status_code == 429
        assert rejection.error.extra_headers() == {"Retry-After": "30"}
        assert rejection.audit_rows == 0
        assert attempt.audited is False

    # [utest->req~users-admission-rejections-no-audit-row~1]
    def test_an_attempt_that_already_audited_takes_no_admission_rejection(self):
        attempt = AuthAttempt(*CREATE_USER_ROUTE, route_template=CREATE_USER_ROUTE[1])
        attempt.audited = True
        decision = LimitDecision(limiter="create_user", allowed=False)
        with pytest.raises(AdmissionPhaseError):
            users_module.admission_phase_rejection(attempt, SecurityTelemetry(), decision)


class TestGatewayLimits:
    # [utest->req~users-standalone-gateway-upgrade-limit~1]
    def test_the_shipped_standalone_upgrade_limit(self):
        entry = gateway_entry()
        assert_upgrade_gateway_limit(entry)
        assert entry.route == "POST /auth/upgrade-anonymous"
        assert entry.limit == "3/hour"
        assert entry.key == "issuer+subject_hash"

    # [utest->req~users-standalone-gateway-upgrade-limit~1]
    def test_a_limit_keyed_on_anything_but_the_linked_subject_is_refused(self):
        entry = gateway_entry().model_copy(update={"key": "ip"})
        with pytest.raises(UsersError):
            assert_upgrade_gateway_limit(entry)
        elsewhere = gateway_entry().model_copy(update={"route": "POST /auth/create-user"})
        with pytest.raises(UsersError):
            assert_upgrade_gateway_limit(elsewhere)

    # [utest->req~users-standalone-gateway-upgrade-limit~1]
    def test_an_over_limit_request_never_reaches_firebase(self):
        ledger = AdmissionLedger(*UPGRADE_ROUTE, mode=RequestMode.completion)
        ledger.verify_jwt()
        upgrade_gateway_admission(ledger, jwt_filter_verified=True, allowed=False)
        with pytest.raises(AdmissionOrderError):
            ledger.expensive_step(ExpensiveStep.firebase_lookup)

    # [utest->req~users-standalone-gateway-upgrade-limit~1]
    def test_the_standalone_limit_runs_before_the_firebase_call(self):
        ledger = AdmissionLedger(*UPGRADE_ROUTE, mode=RequestMode.completion)
        ledger.verify_jwt()
        upgrade_gateway_admission(ledger, jwt_filter_verified=True)
        ledger.expensive_step(ExpensiveStep.firebase_lookup)
        with pytest.raises(UsersError):
            upgrade_gateway_admission(ledger, jwt_filter_verified=True)

    # [utest->req~users-identity-keyed-gateway-limit-keying~1]
    def test_the_gateway_key_comes_from_envoy_jwt_filter_metadata_alone(self):
        material = KeyMaterial(identity_source=IdentitySource.envoy_jwt_filter,
                               issuer=TEST_ISSUER,
                               subject_hash=DerivedIdentifier(b"\x01" * 32, 1))
        assert TEST_ISSUER in gateway_limit_key(gateway_entry(), material)
        backend = KeyMaterial(identity_source=IdentitySource.backend_barrier,
                              issuer=TEST_ISSUER,
                              subject_hash=DerivedIdentifier(b"\x01" * 32, 1))
        with pytest.raises(LimiterKeyError):
            gateway_limit_key(gateway_entry(), backend)

    # [utest->req~users-identity-keyed-gateway-limit-keying~1]
    def test_an_identity_keyed_gateway_limit_evaluates_after_jwt_verification(self):
        early = gateway_entry().model_copy(update={"evaluate_after": "route_match"})
        material = KeyMaterial(identity_source=IdentitySource.envoy_jwt_filter,
                               issuer=TEST_ISSUER,
                               subject_hash=DerivedIdentifier(b"\x01" * 32, 1))
        with pytest.raises(UsersError):
            gateway_limit_key(early, material)
        # An IP-keyed limit needs no verified identity and may run at any position.
        ip_keyed = gateway_entry().model_copy(update={"key": "ip",
                                                      "evaluate_after": "route_match"})
        address = gateway_resolved_address("203.0.113.7",
                                           source=AddressSource.envoy_direct_downstream)
        assert gateway_limit_key(ip_keyed, KeyMaterial(client_address=address))

    # [utest->req~users-identity-keyed-gateway-limit-keying~1]
    def test_the_gateway_key_never_supplies_the_backend_identity_context(self):
        with pytest.raises(UsersError):
            identity_pair(TEST_ISSUER, SUBJECT,
                          source=IdentityContextSource.gateway_jwt_filter_metadata)


class TestFirebaseLookup:
    def admitted_ledger(self) -> AdmissionLedger:
        ledger = AdmissionLedger(*CREATE_USER_ROUTE, mode=RequestMode.completion)
        completion_admission(ledger, AuthOperation.create_user, address=None)
        barrier_verification_next(
            ledger, request_shape_valid=True,
            identity_source=IdentityContextSource.backend_verified_id_token)
        lookup_admission(ledger, GetUserCallSite.create_user_anonymous_completion,
                         test=lambda _name: True, charge=lambda _names: None)
        return ledger

    # [utest->req~users-firebase-lookup-admission-and-retry~1]
    async def test_a_retryable_failure_is_retried_twice_and_then_rejects(self):
        calls: list[int] = []

        async def lookup():
            calls.append(1)
            raise users_module.lookup_unavailable()

        with pytest.raises(ProviderLookupFailedError):
            await firebase_identity_lookup(lookup, ledger=self.admitted_ledger())
        assert len(calls) == 3

    # [utest->req~users-firebase-lookup-admission-and-retry~1]
    async def test_a_non_retryable_failure_consumes_no_retry_budget(self):
        calls: list[int] = []

        async def lookup():
            calls.append(1)
            raise ProviderLookupFailedError(AuthEventResult.firebase_user_unresolved,
                                            ClientErrorClass.auth_required, retryable=False)

        with pytest.raises(ProviderLookupFailedError):
            await firebase_identity_lookup(lookup)
        assert len(calls) == 1

    # [utest->req~users-firebase-lookup-admission-and-retry~1]
    async def test_the_lookup_runs_after_admission_and_before_the_write_transaction(self):
        unadmitted = AdmissionLedger(*CREATE_USER_ROUTE, mode=RequestMode.completion)

        async def lookup():
            return {"providerData": []}

        with pytest.raises(UsersError):
            await firebase_identity_lookup(lookup, ledger=unadmitted)
        ledger = self.admitted_ledger()
        assert await firebase_identity_lookup(lookup, ledger=ledger) == {"providerData": []}
        ledger.expensive_step(ExpensiveStep.database_mutation)
        with pytest.raises(UsersError):
            await firebase_identity_lookup(lookup, ledger=ledger)

    # [utest->req~users-issuer-selected-admin-client~1]
    def test_the_admin_client_is_selected_by_the_verified_issuer(self):
        admin = object()
        integrations = FirebaseIntegrations([FirebaseIntegration(
            issuer=TEST_ISSUER, project_id="test-project", verifier=test_verifier(),
            admin_client=admin)])
        assert issuer_selected_admin_client(integrations, TEST_ISSUER) is admin
        with pytest.raises(InvalidExternalJwtError):
            issuer_selected_admin_client(integrations, "https://securetoken.google.com/other")

    # [utest->req~users-issuer-selected-admin-client~1]
    def test_an_unselectable_admin_client_fails_closed(self):
        integrations = FirebaseIntegrations([FirebaseIntegration(
            issuer=TEST_ISSUER, project_id="test-project", verifier=test_verifier(),
            admin_client=None)])
        with pytest.raises(ProviderLookupFailedError) as raised:
            issuer_selected_admin_client(integrations, TEST_ISSUER)
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert raised.value.client_class is \
            ClientErrorClass.verification_temporarily_unavailable


# --- The upgrade's account-movement audit context -------------------------------------------------


class TestUpgradeMovementAudit:
    def context(self, result: AuthEventResult = AuthEventResult.succeeded, **overrides):
        values: dict[str, Any] = {"result": result, "occurred_at": datetime.now(UTC),
                  "user_id": uuid7(), "external_identity_id": uuid7(),
                  "challenge_row_id": uuid7()}
        values.update(overrides)
        return upgrade_audit_context(**values)

    # [utest->req~users-upgrade-movement-audit-context~1]
    def test_the_context_is_the_same_identity_row_before_and_after(self):
        context = self.context()
        assert context.classification is MovementClassification.upgrade
        assert context.source_external_identity_id == context.destination_external_identity_id
        assert context.source_user_id == context.destination_user_id
        assert context.challenge_row_id is not None

    # [utest->req~users-upgrade-movement-audit-context~1]
    def test_the_public_challenge_handle_is_never_recorded(self):
        with pytest.raises(MovementError):
            self.context(challenge_row_id="public-challenge-handle")

    # [utest->req~users-upgrade-movement-audit-context~1]
    async def test_one_attempt_writes_one_row_and_no_second_durable_row(self):
        harness = Harness()
        writer: AuthAuditWriter = harness.audit
        attempt = AuthAttempt(*UPGRADE_ROUTE, route_template=UPGRADE_ROUTE[1])
        context = self.context(result=AuthEventResult.provider_transition_not_allowed)
        actor = resolved_actor(TEST_ISSUER, bytes(range(32)), 1,
                               stored_provider=IdentityProvider.anonymous)
        event = movement_event(AttemptPhase.business, context, actor=actor)
        error = await record_movement_attempt(writer, attempt, event,
                                              error=ChallengeRejection(context.result))
        assert isinstance(error, ChallengeRejection)
        assert len(harness.sink.events) == 1
        with pytest.raises(AuditAlreadyWrittenError):
            await record_movement_attempt(writer, attempt, event,
                                          error=ChallengeRejection(context.result))
        assert len(harness.sink.events) == 1


# --- Operation-specific identity constraints ---------------------------------------------------------


class TestCreateUserIdentityConstraints:
    challenge = ChallengeRow(challenge_id="d" * 22, operation=AuthOperation.create_user,
                             operation_variant=IdentityProvider.anonymous,
                             binding=IdentityBinding(preauth_issuer=TEST_ISSUER,
                                                     preauth_subject_hash=b"\x02" * 32),
                             expires_at=datetime.now(UTC))

    # [utest->req~users-create-user-identity-constraints~1]
    def test_prepare_requires_a_pre_auth_identity_and_binds_the_variant(self):
        assert create_user_prepare_constraints(preauth_ctx(), None) is IdentityProvider.anonymous
        assert create_user_prepare_constraints(preauth_ctx(), "apple") is IdentityProvider.apple

    # [utest->req~users-create-user-identity-constraints~1]
    def test_an_already_linked_identity_is_the_conflict_class_in_both_phases(self):
        with pytest.raises(ChallengeRejection) as prepare_phase:
            create_user_prepare_constraints(linked_ctx(), None)
        assert prepare_phase.value.result is AuthEventResult.identity_already_linked
        assert prepare_phase.value.error_code == ClientErrorClass.identity_already_linked
        with pytest.raises(ChallengeRejection) as completion:
            create_user_completion_constraints(preauth_ctx(), self.challenge, "anonymous",
                                               live=ResolutionOutcome.linked)
        assert completion.value.result is AuthEventResult.identity_already_linked

    # [utest->req~users-create-user-identity-constraints~1]
    def test_completion_re_resolves_authoritatively_and_compares_the_variant(self):
        assert create_user_completion_constraints(preauth_ctx(), self.challenge, "anonymous",
                                                  live=ResolutionOutcome.pre_auth) is \
            IdentityProvider.anonymous
        with pytest.raises(ChallengeRejection) as raised:
            create_user_completion_constraints(preauth_ctx(), self.challenge, "google",
                                               live=ResolutionOutcome.pre_auth)
        assert raised.value.result is AuthEventResult.challenge_operation_mismatch

    # [utest->req~users-create-user-identity-constraints~1]
    def test_an_unavailable_account_is_rejected_before_either_phase(self):
        for outcome, expected in ((ResolutionOutcome.historical_identity,
                                   AuthEventResult.historical_identity),
                                  (ResolutionOutcome.blocked_user,
                                   AuthEventResult.blocked_user)):
            with pytest.raises(ChallengeRejection) as raised:
                create_user_prepare_constraints(preauth_ctx(outcome=outcome), None)
            assert raised.value.result is expected
            assert raised.value.error_code == ClientErrorClass.account_unavailable


class TestUpgradeIdentityConstraints:
    # [utest->req~users-upgrade-identity-constraints~1]
    def test_prepare_requires_a_linked_identity_and_a_declared_target(self):
        assert upgrade_prepare_constraints(linked_ctx(), "google") is IdentityProvider.google
        with pytest.raises(UsersError):
            upgrade_prepare_constraints(preauth_ctx(), "google")
        with pytest.raises(InvalidOperationVariantError):
            upgrade_prepare_constraints(linked_ctx(), None)

    # [utest->req~users-upgrade-identity-constraints~1]
    def test_the_mutable_path_requires_the_stored_provider_to_be_anonymous(self):
        row = identity_row()
        decision = upgrade_completion_decision(row, IdentityProvider.google,
                                               provider_data=provider_data("google.com"))
        assert decision.branch is UpgradeBranch.mutable
        assert decision.provider_uid == "provider-account-uid"
        flipped = apply_upgrade(row, decision, transaction=object())
        assert flipped.provider is IdentityProvider.google
        assert flipped.provider_uid == "provider-account-uid"

    # [utest->req~users-upgrade-identity-constraints~1]
    def test_idempotent_success_requires_stored_live_and_uid_to_agree(self):
        row = identity_row(provider=IdentityProvider.google,
                           provider_uid="provider-account-uid")
        decision = upgrade_completion_decision(row, IdentityProvider.google,
                                               provider_data=provider_data("google.com"))
        assert decision.branch is UpgradeBranch.idempotent
        assert apply_upgrade(row, decision, transaction=object()) is row

    # [utest->req~users-upgrade-identity-constraints~1]
    def test_a_divergent_stored_binding_is_provider_transition_not_allowed(self):
        different_uid = identity_row(provider=IdentityProvider.google,
                                     provider_uid="another-account")
        with pytest.raises(ChallengeRejection) as raised:
            upgrade_completion_decision(different_uid, IdentityProvider.google,
                                        provider_data=provider_data("google.com"))
        assert raised.value.result is AuthEventResult.provider_transition_not_allowed
        assert different_uid.provider_uid == "another-account"

        different_provider = identity_row(provider=IdentityProvider.apple,
                                          provider_uid="apple-account")
        with pytest.raises(ChallengeRejection) as second:
            upgrade_completion_decision(different_provider, IdentityProvider.google,
                                        provider_data=provider_data("google.com"))
        assert second.value.result is AuthEventResult.provider_transition_not_allowed
        assert different_provider.provider is IdentityProvider.apple

    # [utest->req~users-upgrade-identity-constraints~1]
    def test_an_unconfirmed_declaration_never_mutates_the_row(self):
        row = identity_row()
        with pytest.raises(users_module.ProviderNotConfirmedError) as raised:
            upgrade_completion_decision(row, IdentityProvider.google, provider_data=[])
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert row.provider is IdentityProvider.anonymous


class TestClientErrorTaxonomy:
    # [utest->req~users-client-error-taxonomy-not-internal-results~1]
    @pytest.mark.parametrize("result", sorted(users_module.USERS_INTERNAL_RESULTS))
    def test_every_internal_result_surfaces_through_a_shared_class(self, result):
        client_class = client_class_for(result)
        assert client_class in {str(entry) for entry in ClientErrorClass}
        if result not in (AuthEventResult.preauth_identity_not_allowed,
                          AuthEventResult.identity_already_linked):
            assert client_class != str(result)

    # [utest->req~users-client-error-taxonomy-not-internal-results~1]
    def test_a_result_these_endpoints_never_produce_is_refused(self):
        with pytest.raises(UsersError):
            client_class_for(AuthEventResult.restore_subscription_unlinked)


# --- The `POST /auth/create-user` request ---------------------------------------------------------------


class TestCreateUserRequest:
    # [utest->req~users-create-user-request-token~1]
    def test_the_token_resolves_to_a_pre_auth_identity_with_no_token_provider(self):
        assert create_user_authentication(preauth_ctx()) == (TEST_ISSUER, SUBJECT)
        with pytest.raises(UsersError):
            create_user_authentication(preauth_ctx(), token_provider="google.com")
        with pytest.raises(UsersError):
            create_user_authentication(linked_ctx())

    # [utest->req~users-create-user-request-challenge~1]
    def test_the_challenge_comes_from_the_endpoints_own_prepare_call(self):
        assert create_user_challenge_source() == "POST /auth/create-user?challenge=true"

    # [utest->req~users-create-user-request-no-anonymous-proof~1]
    def test_no_proof_for_a_prior_anonymous_identity(self):
        assert_no_anonymous_proof({"challenge_id": "c" * 22, "provider": "anonymous"})
        with pytest.raises(UsersError):
            assert_no_anonymous_proof({"anonymous_id_token": "eyJ..."})
        with pytest.raises(UsersError):
            assert_no_anonymous_proof({"source_anonymous_identity": str(uuid7())})

    # [utest->req~users-create-user-request-no-attestation~1]
    def test_no_attestation_or_integrity_proof(self):
        assert_no_attestation({"provider": "google"})
        with pytest.raises(UsersError):
            assert_no_attestation({"attestation": "blob"})
        with pytest.raises(UsersError):
            assert_no_attestation({"play_integrity_token": "verdict"})

    # [utest->req~users-create-user-request-no-restore-proof~1]
    def test_no_restore_proof(self):
        assert_no_restore_proof({"provider": "apple"})
        with pytest.raises(UsersError):
            assert_no_restore_proof({"restore_proof": {"transaction_id": "1"}})
