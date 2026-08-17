"""`GET /users/me`, as `01-sessions-and-identity-resolution.md` states it: two reads, one fixed
response shape carrying an entry for every store provider, and a must-not list that closes every
other door.
"""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import (
    BarrierRejectionError,
    ResolutionOutcome,
    VerifiedIdentityContext,
)
from nativespeaker.api.auth.endpoints import EndpointContractError, bearer_credential
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.sync import (
    REGISTRATION_STATE_FIELD,
    ReadOnlySyncSession,
    SyncState,
    sync_response,
)
from nativespeaker.api.auth.tokens import InvalidExternalJwtError
from nativespeaker.api.auth.users_me import (
    ATTRIBUTION_FIELD_BY_STORE,
    FORBIDDEN_EFFECTS,
    IGNORED_REQUEST_SIGNALS,
    IOS_PURCHASE_TOKEN_FIELD,
    PERMITTED_TOKEN_FIELDS,
    PROHIBITED_CALLS,
    RESPONSE_PROFILE_FIELDS,
    STORE_PROVIDERS,
    MissingAttributionTokenError,
    ProfileRow,
    ReadOnlyUsersMeSession,
    UsersMeEffect,
    UsersMeError,
    UsersMeProhibitedError,
    UsersMeState,
    assert_admitted,
    assert_no_client_signal_consulted,
    assert_payload_carries_no_store_secrets,
    assert_permitted,
    attribution_tokens,
    is_forbidden,
    storekit_app_account_token,
    users_me_credential,
    users_me_response,
    users_me_state,
)
from nativespeaker.api.quota.grants import (
    EntitlementReport,
    PublicEntitlementStatus,
    PublicEntitlementType,
)

ISSUER = "https://securetoken.google.com/test-project"
USER_ID = uuid4()
APPLE_TOKEN = "11111111-1111-1111-1111-111111111111"
GOOGLE_TOKEN = "22222222-2222-2222-2222-222222222222"


def linked(provider: IdentityProvider = IdentityProvider.google) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=ISSUER,
                                   subject="sub-1",
                                   outcome=ResolutionOutcome.linked,
                                   user_id=USER_ID,
                                   external_identity_id=uuid4(),
                                   provider=provider)


def profile_row(**overrides) -> ProfileRow:
    values = {"user_id": USER_ID,
              "email": "user@example.com",
              "display_name": "A User",
              "created_at": datetime(2026, 1, 1, tzinfo=UTC)}
    values.update(overrides)
    return ProfileRow(**values)


def session(*,
            tokens: dict | None = None,
            provider: IdentityProvider = IdentityProvider.google,
            row: ProfileRow | None = None) -> ReadOnlyUsersMeSession:
    return ReadOnlyUsersMeSession(
        profile_row=row or profile_row(),
        store_tokens=tokens if tokens is not None else {StoreProvider.apple: APPLE_TOKEN,
                                                       StoreProvider.google_play: GOOGLE_TOKEN},
        stored_provider=provider)


def state(provider: IdentityProvider = IdentityProvider.google) -> UsersMeState:
    return UsersMeState(profile=profile_row(),
                        identity_provider=provider,
                        store_tokens={str(StoreProvider.apple): APPLE_TOKEN,
                                      str(StoreProvider.google_play): GOOGLE_TOKEN})


class TestAuthenticationAndAdmission:
    # [utest->req~sessions-api-users-me-bearer-credential~1]
    def test_the_credential_is_exactly_one_authorization_bearer_value(self):
        assert users_me_credential(["Bearer id-token"]) == "id-token"
        for values in ([], ["Bearer a", "Bearer b"], ["Bearer a, Bearer b"], ["Basic a"],
                       ["Bearer "], ["Bearer a b"]):
            with pytest.raises(InvalidExternalJwtError):
                users_me_credential(values)

    # [utest->req~sessions-api-users-me-barrier-precondition~1]
    def test_the_endpoint_requires_a_linked_active_identity(self):
        assert assert_admitted(linked()).user_id == USER_ID
        for outcome, result in ((ResolutionOutcome.pre_auth,
                                 AuthEventResult.preauth_identity_not_allowed),
                                (ResolutionOutcome.historical_identity,
                                 AuthEventResult.historical_identity),
                                (ResolutionOutcome.blocked_user, AuthEventResult.blocked_user)):
            with pytest.raises(BarrierRejectionError) as raised:
                assert_admitted(VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                                        outcome=outcome))
            assert raised.value.result is result

    # [utest->req~sessions-api-users-me-barrier-precondition~1]
    def test_a_linked_outcome_with_no_resolved_user_is_not_a_principal(self):
        with pytest.raises(BarrierRejectionError):
            assert_admitted(VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                                    outcome=ResolutionOutcome.linked))

    # [utest->req~sessions-api-users-me-bearer-credential~1]
    def test_a_route_declaring_no_id_token_requirement_carries_no_credential(self):
        # `GET /users/me` does declare it, which is what makes the bearer credential its
        # authentication; a route that does not cannot borrow the contract.
        assert bearer_credential("GET", "/users/me", ["Bearer id-token"]) == "id-token"
        with pytest.raises(EndpointContractError):
            bearer_credential("GET", "/health/ready", ["Bearer id-token"])


class TestTheThreeSteps:
    # [utest->req~sessions-users-me-step-01~1]
    def test_step_one_loads_the_resolved_users_profile_fields(self):
        handle = session()
        result = users_me_state(linked(), handle)
        assert result.profile.email == "user@example.com"
        assert result.profile.display_name == "A User"
        assert "profile_row" in handle.reads

    # [utest->req~sessions-users-me-step-01~1]
    def test_the_profile_read_is_the_barrier_resolved_users_own_row(self):
        handle = session(row=profile_row(user_id=uuid4()))
        with pytest.raises(UsersMeError):
            users_me_state(linked(), handle)

    # [utest->req~sessions-users-me-step-02~1]
    def test_step_two_reads_the_persisted_tokens_scoped_per_store_provider(self):
        handle = session()
        result = users_me_state(linked(), handle)
        assert "store_tokens" in handle.reads
        assert result.store_tokens == {"apple": APPLE_TOKEN, "google_play": GOOGLE_TOKEN}

    # [utest->req~sessions-users-me-step-03~1]
    def test_step_three_returns_profile_registration_state_and_tokens(self):
        body = users_me_response(state(IdentityProvider.apple))
        assert body["profile"] == {"email": "user@example.com", "display_name": "A User"}
        assert body[REGISTRATION_STATE_FIELD] == "apple"
        assert body["store_purchase_tokens"]["apple"] == {"app_account_token": APPLE_TOKEN}
        assert body["store_purchase_tokens"]["google_play"] == {
            "obfuscated_external_account_id": GOOGLE_TOKEN}

    # [utest->req~sessions-users-me-step-03~1]
    @pytest.mark.parametrize("provider", list(IdentityProvider))
    def test_the_registration_state_is_the_same_value_sync_reports(self, provider):
        mine = users_me_response(state(provider))[REGISTRATION_STATE_FIELD]
        theirs = sync_response(SyncState(
            entitlement=EntitlementReport(type=PublicEntitlementType.none,
                                          status=PublicEntitlementStatus.none,
                                          tier_id=None, monthly_credits=None,
                                          current_period="2026-03", monthly_used=0),
            identity_provider=provider))[REGISTRATION_STATE_FIELD]
        # Same field name, same value, read from the same stored column.
        assert mine == theirs == provider.value

    # [utest->req~sessions-users-me-step-03~1]
    def test_the_response_profile_fields_are_the_canonical_ones(self):
        assert RESPONSE_PROFILE_FIELDS == ("email", "display_name")


class TestFixedResponseShape:
    # [utest->req~sessions-api-users-me-fixed-response-shape~1]
    def test_every_store_provider_always_gets_an_entry(self):
        body = users_me_response(state())
        assert set(body["store_purchase_tokens"]) == {str(p) for p in StoreProvider}
        assert STORE_PROVIDERS == tuple(StoreProvider)

    # [utest->req~sessions-api-users-me-fixed-response-shape~1]
    # [utest->req~sessions-api-users-me-no-token-rotation~1]
    @pytest.mark.parametrize("missing", list(StoreProvider))
    def test_a_missing_token_row_is_an_internal_invariant_failure(self, missing):
        tokens = {StoreProvider.apple: APPLE_TOKEN, StoreProvider.google_play: GOOGLE_TOKEN}
        del tokens[missing]
        handle = session(tokens=tokens)
        with pytest.raises(MissingAttributionTokenError) as raised:
            attribution_tokens(handle, USER_ID)
        # Never a `null` in the response, and never a lazily minted replacement.
        assert raised.value.provider is missing
        assert raised.value.result is AuthEventResult.internal_error

    # [utest->req~sessions-api-users-me-fixed-response-shape~1]
    def test_an_empty_stored_token_is_a_failure_rather_than_a_null_field(self):
        handle = session(tokens={StoreProvider.apple: "", StoreProvider.google_play: GOOGLE_TOKEN})
        with pytest.raises(MissingAttributionTokenError):
            attribution_tokens(handle, USER_ID)

    # [utest->req~sessions-api-users-me-fixed-response-shape~1]
    @pytest.mark.parametrize("signal", ["User-Agent", "X-Platform", "x-client-platform",
                                        "platform", "store", "x-gateway-claims"])
    def test_no_client_signal_or_gateway_claim_changes_the_tokens(self, signal):
        assert signal.lower() in IGNORED_REQUEST_SIGNALS
        with pytest.raises(UsersMeError):
            attribution_tokens(session(), USER_ID, request_signals=[signal])
        # With none of them read, the entry set is the same on every platform.
        assert set(attribution_tokens(session(), USER_ID)) == {str(p) for p in StoreProvider}

    # [utest->req~sessions-api-users-me-fixed-response-shape~1]
    def test_the_token_load_reads_the_resolved_user_and_nothing_else(self):
        assert_no_client_signal_consulted()
        with pytest.raises(UsersMeError):
            assert_no_client_signal_consulted(["x-platform"])

    # [utest->req~sessions-api-users-me-fixed-response-shape~1]
    def test_only_non_secret_attribution_identifiers_belong_in_the_payload(self):
        assert PERMITTED_TOKEN_FIELDS == {"app_account_token",
                                          "obfuscated_external_account_id"}
        assert_payload_carries_no_store_secrets(
            {"apple": {"app_account_token": APPLE_TOKEN}})
        for offending in ({"apple": {"signed_transaction": "x"}},
                          {"apple": {"receipt": "x"}},
                          {"apple": {"purchase_proof": "x"}},
                          {"apple": {"store_credential": "x"}},
                          {"apple": {"app_account_token": APPLE_TOKEN, "jws": "x"}}):
            with pytest.raises(UsersMeError):
                assert_payload_carries_no_store_secrets(offending)

    # [utest->req~sessions-api-users-me-fixed-response-shape~1]
    def test_a_null_token_never_reaches_the_response(self):
        # A `None` is not a shape the type admits, which is the first line of defence; the
        # builder refuses it at runtime too rather than emitting a null field.
        broken = UsersMeState(profile=profile_row(),
                              identity_provider=IdentityProvider.google,
                              store_tokens=cast("dict[str, str]",
                                                {str(StoreProvider.apple): None,
                                                 str(StoreProvider.google_play): GOOGLE_TOKEN}))
        with pytest.raises(UsersMeError):
            users_me_response(broken)


class TestPurpose:
    # [utest->req~sessions-api-users-me-purpose~1]
    def test_the_tokens_are_returned_unconditionally_for_every_provider_and_platform(self):
        for provider in IdentityProvider:
            body = users_me_response(state(provider))
            assert set(body["store_purchase_tokens"]) == {str(p) for p in StoreProvider}

    # [utest->req~sessions-api-users-me-purpose~1]
    def test_the_ios_client_reads_the_exact_stored_apple_app_account_token(self):
        assert IOS_PURCHASE_TOKEN_FIELD == "app_account_token"
        assert ATTRIBUTION_FIELD_BY_STORE[StoreProvider.apple] == "app_account_token"
        body = users_me_response(state())
        # The exact stored value, passed straight into StoreKit — never regenerated.
        assert storekit_app_account_token(body) == APPLE_TOKEN


class TestProhibitions:
    # [utest->req~sessions-api-users-me-prohibitions~1]
    def test_the_must_not_list_is_closed_and_nothing_on_it_is_permitted(self):
        assert FORBIDDEN_EFFECTS == frozenset(UsersMeEffect)
        for effect in UsersMeEffect:
            assert is_forbidden(effect) is True
            with pytest.raises(UsersMeProhibitedError):
                assert_permitted(effect)
        # An unrecognized effect is forbidden too: the contract is a closed permission set.
        assert is_forbidden("something_new") is True

    # [utest->req~sessions-users-me-must-not-create-users~1]
    @pytest.mark.parametrize("call", ["create_user", "insert_user"])
    def test_it_must_not_create_users(self, call):
        assert PROHIBITED_CALLS[call] is UsersMeEffect.create_user
        with pytest.raises(UsersMeProhibitedError) as raised:
            getattr(session(), call)()
        assert raised.value.effect is UsersMeEffect.create_user

    # [utest->req~sessions-users-me-must-not-mutate-identities~1]
    @pytest.mark.parametrize("call", ["link_identity", "mark_identity_historical",
                                      "write_identity"])
    def test_it_must_not_mutate_external_identities(self, call):
        assert PROHIBITED_CALLS[call] is UsersMeEffect.mutate_identities
        with pytest.raises(UsersMeProhibitedError):
            getattr(session(), call)()

    # [utest->req~sessions-users-me-must-not-mutate-grants~1]
    @pytest.mark.parametrize("call", ["create_grant", "expire_grant", "write_grant"])
    def test_it_must_not_mutate_access_grants(self, call):
        assert PROHIBITED_CALLS[call] is UsersMeEffect.mutate_grants
        with pytest.raises(UsersMeProhibitedError):
            getattr(session(), call)()

    # [utest->req~sessions-users-me-must-not-mutate-subscriptions~1]
    @pytest.mark.parametrize("call", ["modify_subscription", "write_store_purchase"])
    def test_it_must_not_mutate_subscriptions_or_store_purchases(self, call):
        assert PROHIBITED_CALLS[call] is UsersMeEffect.mutate_subscriptions
        with pytest.raises(UsersMeProhibitedError):
            getattr(session(), call)()

    # [utest->req~sessions-users-me-must-not-issue-challenges~1]
    def test_it_must_not_issue_operation_challenges(self):
        assert PROHIBITED_CALLS["issue_challenge"] is UsersMeEffect.issue_challenge
        with pytest.raises(UsersMeProhibitedError):
            session().issue_challenge()

    # [utest->req~sessions-users-me-must-not-verify-proofs~1]
    @pytest.mark.parametrize("call", ["verify_restore_proof", "verify_device_proof",
                                      "verify_devicecheck", "verify_play_integrity",
                                      "verify_device_recall"])
    def test_it_must_not_verify_restore_or_device_check_proofs(self, call):
        assert PROHIBITED_CALLS[call] is UsersMeEffect.verify_proof
        with pytest.raises(UsersMeProhibitedError):
            getattr(session(), call)()

    # [utest->req~sessions-users-me-must-not-touch-device-grant-state~1]
    @pytest.mark.parametrize("call", ["read_device_grant_state", "write_device_grant_state"])
    def test_it_must_not_read_or_modify_per_device_grant_state(self, call):
        assert PROHIBITED_CALLS[call] is UsersMeEffect.touch_device_grant_state
        with pytest.raises(UsersMeProhibitedError):
            getattr(session(), call)()

    # [utest->req~sessions-users-me-must-not-append-state-changing-audit~1]
    def test_it_must_not_append_state_changing_auth_audit_rows(self):
        assert PROHIBITED_CALLS["append_state_changing_audit"] is \
            UsersMeEffect.append_state_changing_audit
        with pytest.raises(UsersMeProhibitedError):
            session().append_state_changing_audit()

    # [utest->req~sessions-api-users-me-no-token-rotation~1]
    @pytest.mark.parametrize("call", ["mint_attribution_token", "rotate_attribution_token",
                                      "replace_attribution_token"])
    def test_it_never_creates_rotates_or_replaces_an_attribution_token(self, call):
        assert PROHIBITED_CALLS[call] is UsersMeEffect.rotate_attribution_token
        with pytest.raises(UsersMeProhibitedError):
            getattr(session(), call)()

    # [utest->req~sessions-api-users-me-no-token-rotation~1]
    def test_it_mints_no_grant_and_updates_no_profile_field(self):
        for call in ("mint_grant", "update_profile"):
            with pytest.raises(UsersMeProhibitedError):
                getattr(session(), call)()

    # [utest->req~sessions-api-users-me-prohibitions~1]
    def test_an_unnamed_call_on_the_session_is_refused_too(self):
        with pytest.raises(UsersMeProhibitedError):
            session().some_unforeseen_write()

    # [utest->req~sessions-api-users-me-prohibitions~1]
    def test_the_session_exposes_only_its_declared_reads(self):
        assert ReadOnlyUsersMeSession.READS == ("profile_row", "store_tokens")
        # The read-only session for `/auth/sync` is a separate handle; neither grows a write.
        assert ReadOnlySyncSession.READS == ("grant_rows", "usage_row", "stored_provider")

    # [utest->req~sessions-api-users-me-no-token-rotation~1]
    def test_a_full_call_performs_no_mutation_at_all(self):
        handle = session()
        users_me_state(linked(), handle)
        assert handle.reads == ["profile_row", "store_tokens", "stored_provider"]
