"""The two onboarding operations as the endpoints wire them, and the
`POST /auth/upgrade-anonymous` request contract."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import ChallengeRow, ChallengeState, IdentityBinding
from nativespeaker.api.auth.external_identities import ExternalIdentityRow, IdentityState
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.onboarding import (
    ONBOARDING_ENDPOINTS,
    AuthorizationHeaderSource,
    assert_endpoint_uses_shared_contract,
    assert_no_attestation_key_proof,
    assert_no_upgrade_restore_proof,
    assert_pre_consumption_checks_first,
    operation_for_endpoint,
    upgrade_authentication,
    upgrade_challenge_source,
    upgrade_declared_provider,
    upgrade_operation,
    upgrade_success,
)
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    InvalidOperationVariantError,
)
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.users import UpgradeBranch, UpgradeDecision, UsersError
from unit.conftest import TEST_ISSUER

SUBJECT = "verified-subject"


def linked_ctx(**overrides) -> VerifiedIdentityContext:
    values: dict[str, Any] = {"issuer": TEST_ISSUER, "subject": SUBJECT,
                              "outcome": ResolutionOutcome.linked,
                              "user_id": uuid7(), "external_identity_id": uuid7(),
                              "provider": IdentityProvider.anonymous}
    values.update(overrides)
    return VerifiedIdentityContext(**values)


def identity_row(identity_id=None, user_id=None, **overrides) -> ExternalIdentityRow:
    values: dict[str, Any] = {"id": identity_id or uuid7(), "user_id": user_id or uuid7(),
                              "issuer": TEST_ISSUER, "subject": SUBJECT,
                              "provider": IdentityProvider.anonymous}
    values.update(overrides)
    return ExternalIdentityRow(**values)


def challenge(operation: AuthOperation = AuthOperation.upgrade_anonymous_to_registered,
              variant: IdentityProvider | None = IdentityProvider.google,
              state: ChallengeState = ChallengeState.claimed) -> ChallengeRow:
    claimed = state is not ChallengeState.issued
    return ChallengeRow(challenge_id="a" * 22, operation=operation, operation_variant=variant,
                        binding=IdentityBinding(bound_external_identity_id=uuid7()),
                        expires_at=datetime(2026, 8, 16, 12, 5, tzinfo=UTC), state=state,
                        id=uuid7(), claim_attempt_id=uuid7() if claimed else None)


class Endpoint:
    """A minimal endpoint half: it names one operation and implements the shared hooks."""

    def __init__(self, operation: AuthOperation) -> None:
        self.operation = operation

    async def check_prepare_eligibility(self, identity, variant) -> None: ...
    async def verify_proof(self, identity, row, body): ...
    async def confirm_live_state(self, session, identity, row): ...
    async def mutate(self, session, identity, row, proof, live): ...


# --- Operation logic ----------------------------------------------------------------------------


class TestOperationLogic:
    def test_each_operation_names_its_own_endpoint(self):
        assert ONBOARDING_ENDPOINTS[AuthOperation.create_user] == ("POST", "/auth/create-user")
        assert ONBOARDING_ENDPOINTS[AuthOperation.upgrade_anonymous_to_registered] == \
            ("POST", "/auth/upgrade-anonymous")
        assert operation_for_endpoint("POST", "/auth/create-user") is AuthOperation.create_user
        with pytest.raises(UsersError):
            operation_for_endpoint("POST", "/auth/sync")

    # [utest->req~users-endpoints-use-shared-challenge-contract~1]
    def test_each_endpoint_uses_the_shared_operation_challenge_contract(self):
        for operation in ONBOARDING_ENDPOINTS:
            assert assert_endpoint_uses_shared_contract(Endpoint(operation)) is operation

    # [utest->req~users-endpoints-use-shared-challenge-contract~1]
    def test_an_endpoint_of_another_operation_is_refused(self):
        with pytest.raises(UsersError):
            assert_endpoint_uses_shared_contract(Endpoint(AuthOperation.sync))

    # [utest->req~users-endpoints-use-shared-challenge-contract~1]
    def test_an_endpoint_missing_a_shared_hook_is_refused(self):
        class Partial:
            operation = AuthOperation.create_user

            async def check_prepare_eligibility(self, identity, variant) -> None: ...

        with pytest.raises(UsersError):
            assert_endpoint_uses_shared_contract(Partial())

    # [utest->req~users-endpoints-use-shared-challenge-contract~1]
    def test_a_second_completion_or_audit_path_is_a_second_contract(self):
        endpoint = Endpoint(AuthOperation.create_user)
        endpoint.complete = lambda *args: None  # type: ignore[attr-defined]
        with pytest.raises(UsersError):
            assert_endpoint_uses_shared_contract(endpoint)

    # [utest->req~users-shared-pre-consumption-checks-first~1]
    def test_a_mutation_rule_only_sees_a_row_this_attempt_claimed(self):
        claimed = challenge()
        assert assert_pre_consumption_checks_first(claimed) is claimed
        for state in (ChallengeState.issued, ChallengeState.consumed):
            with pytest.raises(UsersError):
                assert_pre_consumption_checks_first(challenge(state=state))

    # [utest->req~users-shared-pre-consumption-checks-first~1]
    def test_a_row_of_another_operation_reaches_no_mutation_rule_of_this_split(self):
        with pytest.raises(UsersError):
            assert_pre_consumption_checks_first(
                challenge(operation=AuthOperation.claim_anonymous_grant, variant=None))


# --- The `POST /auth/upgrade-anonymous` request contract ------------------------------------------


class TestUpgradeRequest:
    # [utest->req~users-upgrade-endpoint-single-operation~1]
    def test_the_endpoint_performs_only_the_anonymous_upgrade(self):
        assert upgrade_operation("POST", "/auth/upgrade-anonymous") is \
            AuthOperation.upgrade_anonymous_to_registered
        for route in (("POST", "/auth/create-user"), ("POST", "/auth/sync")):
            with pytest.raises(UsersError):
                upgrade_operation(*route)

    # [utest->req~users-upgrade-request-token~1]
    def test_the_token_must_resolve_to_an_existing_linked_active_identity_row(self):
        context = linked_ctx()
        row = identity_row(identity_id=context.external_identity_id)
        assert upgrade_authentication(context, row=row) == context.external_identity_id
        historical = identity_row(identity_id=context.external_identity_id,
                                  identity_state=IdentityState.historical)
        with pytest.raises(UsersError):
            upgrade_authentication(context, row=historical)
        with pytest.raises(UsersError):
            upgrade_authentication(VerifiedIdentityContext(
                issuer=TEST_ISSUER, subject=SUBJECT, outcome=ResolutionOutcome.pre_auth))

    # [utest->req~users-upgrade-request-token~1]
    def test_any_valid_token_for_the_pair_suffices_at_any_freshness(self):
        context = linked_ctx()
        for age in (timedelta(seconds=0), timedelta(days=30)):
            assert upgrade_authentication(context, token_age=age) == \
                context.external_identity_id

    # [utest->req~users-upgrade-request-token~1]
    @pytest.mark.parametrize("header", [AuthorizationHeaderSource.gateway_rewritten_header,
                                        AuthorizationHeaderSource.gateway_jwt_filter_metadata])
    def test_only_the_unchanged_client_header_authenticates_the_upgrade(self, header):
        with pytest.raises(UsersError):
            upgrade_authentication(linked_ctx(), header=header)

    # [utest->req~users-upgrade-request-provider-field~1]
    def test_prepare_requires_a_declared_google_or_apple_target(self):
        assert upgrade_declared_provider("google", phase=RequestMode.prepare) is \
            IdentityProvider.google
        assert upgrade_declared_provider("apple", phase=RequestMode.prepare) is \
            IdentityProvider.apple
        for declared in (None, "anonymous", "Google", ""):
            with pytest.raises((InvalidOperationVariantError, UsersError)):
                upgrade_declared_provider(declared, phase=RequestMode.prepare)

    # [utest->req~users-upgrade-request-provider-field~1]
    def test_completion_must_equal_the_challenge_bound_variant(self):
        row = challenge(variant=IdentityProvider.google)
        assert upgrade_declared_provider("google", phase=RequestMode.completion, row=row) is \
            IdentityProvider.google
        for declared in (None, "apple", "GOOGLE"):
            with pytest.raises(ChallengeRejection) as raised:
                upgrade_declared_provider(declared, phase=RequestMode.completion, row=row)
            assert raised.value.result is AuthEventResult.challenge_operation_mismatch

    # [utest->req~users-upgrade-request-challenge~1]
    def test_the_challenge_comes_from_the_endpoints_own_prepare_url(self):
        assert upgrade_challenge_source() == "POST /auth/upgrade-anonymous?challenge=true"

    # [utest->req~users-upgrade-request-no-attestation-key-proof~1]
    def test_the_request_carries_no_attestation_key_proof(self):
        assert_no_attestation_key_proof({"challenge_id": "x", "provider": "google"})
        assert_no_attestation_key_proof(None)
        for field in ("attestation_key_proof", "app_attest_assertion", "integrity_token"):
            with pytest.raises(UsersError):
                assert_no_attestation_key_proof({field: "material"})

    # [utest->req~users-upgrade-request-no-restore-proof~1]
    def test_the_request_carries_no_restore_proof(self):
        assert_no_upgrade_restore_proof({"challenge_id": "x", "provider": "apple"})
        with pytest.raises(UsersError):
            assert_no_upgrade_restore_proof({"restore_proof": {"receipt": "..."}})

    # [utest->req~users-upgrade-success-flip-or-idempotent~1]
    def test_success_flips_the_row_in_place_on_the_same_user(self):
        context = linked_ctx()
        row = identity_row(identity_id=context.external_identity_id, user_id=context.user_id)
        decision = UpgradeDecision(UpgradeBranch.mutable, IdentityProvider.google, "google-uid")
        upgraded = upgrade_success(row, decision, context=context, transaction=object())
        assert upgraded.id == row.id and upgraded.user_id == row.user_id
        assert upgraded.provider is IdentityProvider.google
        assert upgraded.provider_uid == "google-uid"
        assert upgraded.identity_state is IdentityState.active

    # [utest->req~users-upgrade-success-flip-or-idempotent~1]
    def test_an_agreeing_stored_binding_is_idempotent_success_that_mutates_nothing(self):
        context = linked_ctx(provider=IdentityProvider.apple)
        row = identity_row(identity_id=context.external_identity_id, user_id=context.user_id,
                           provider=IdentityProvider.apple, provider_uid="apple-uid")
        decision = UpgradeDecision(UpgradeBranch.idempotent, IdentityProvider.apple, "apple-uid")
        assert upgrade_success(row, decision, context=context, transaction=object()) == row

    # [utest->req~users-upgrade-success-flip-or-idempotent~1]
    def test_no_backend_token_is_issued_and_anonymous_is_no_success_target(self):
        context = linked_ctx()
        row = identity_row(identity_id=context.external_identity_id, user_id=context.user_id)
        decision = UpgradeDecision(UpgradeBranch.mutable, IdentityProvider.google, "google-uid")
        with pytest.raises(UsersError):
            upgrade_success(row, decision, context=context, transaction=object(),
                            backend_token="backend.jwt")
        anonymous = UpgradeDecision(UpgradeBranch.mutable, IdentityProvider.anonymous, "")
        with pytest.raises(UsersError):
            upgrade_success(row, anonymous, context=context, transaction=object())
