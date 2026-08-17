"""The shared client-visible error contract: the registry of classes, the normative
remediation each one carries, and the single response shape they all use."""

import pytest
from fastapi.testclient import TestClient

from nativespeaker.api.auth.audit import AuthEventResult, AuthResultCounter
from nativespeaker.api.auth.barrier import BarrierRejectionError, ResolutionOutcome
from nativespeaker.api.auth.modes import (
    CHALLENGE_ID_FIELD,
    ModeSignalDefect,
    ModeSignalError,
    classify_mode,
)
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.taxonomy import (
    AUTH_REQUIRED_EXCLUSIONS,
    AUTH_REQUIRED_RESULTS,
    CHALLENGE_REQUIRED_RESULTS,
    INVALID_EXTERNAL_JWT_REASONS,
    REMEDIATIONS,
    RESULT_TO_CLASS,
    ClassNotEmittableError,
    ClientErrorClass,
    ProviderDataReadPoint,
    Remediation,
    TaxonomyError,
    UnsurfacedResultError,
    assert_emitted_subset,
    client_response,
    device_grant_exhausted_next_path,
    next_route_for,
    register_client_class,
    remediation_for,
    surface,
)
from nativespeaker.api.auth.tokens import JwtRejectionReason
from unit.conftest import make_token
from unit.test_auth_barrier import FakeResolver, RecordingSink, build_app, make_writer

# The registry as the specification lists it, in order.
DECLARED_CLASSES = ("auth_required", "preauth_identity_not_allowed", "account_unavailable",
                    "identity_already_linked", "challenge_required", "invalid_request",
                    "proof_rejected", "operation_not_allowed", "verification_required",
                    "device_grant_exhausted", "account_already_claimed",
                    "verification_temporarily_unavailable",
                    "registration_temporarily_unavailable")


class TestTheRegistry:
    # [utest->req~shared-error-class-registry~1]
    # [utest->req~shared-error-class-auth-required~1]
    # [utest->req~shared-error-class-preauth-identity-not-allowed~1]
    # [utest->req~shared-error-class-account-unavailable~1]
    # [utest->req~shared-error-class-identity-already-linked~1]
    # [utest->req~shared-error-class-challenge-required~1]
    # [utest->req~shared-error-class-invalid-request~1]
    # [utest->req~shared-error-class-proof-rejected~1]
    # [utest->req~shared-error-class-operation-not-allowed~1]
    # [utest->req~shared-error-class-verification-required~1]
    # [utest->req~shared-error-class-device-grant-exhausted~1]
    # [utest->req~shared-error-class-account-already-claimed~1]
    # [utest->req~shared-error-class-verification-temporarily-unavailable~1]
    # [utest->req~shared-error-class-registration-temporarily-unavailable~1]
    @pytest.mark.parametrize("declared", DECLARED_CLASSES)
    def test_every_client_visible_class_is_declared_and_usable(self, declared):
        assert declared in set(ClientErrorClass)
        # A declared class is usable: it carries a remediation and a response of its own.
        assert remediation_for(declared).action
        assert client_response(declared).body["code"] == declared

    # [utest->req~shared-error-class-registry~1]
    # [utest->req~shared-error-registry-exhaustive~1]
    def test_the_registry_is_exactly_the_declared_list(self):
        assert [str(klass) for klass in ClientErrorClass] == list(DECLARED_CLASSES)

    # [utest->req~shared-error-registry-exhaustive~1]
    def test_an_endpoint_emits_only_declared_classes_it_mapped(self):
        mapped = [AuthEventResult.challenge_expired, AuthEventResult.policy_rejected]
        assert_emitted_subset(["challenge_required", "operation_not_allowed"], mapped)
        # An endpoint need not emit every shared class, but it may not emit one it never
        # mapped, and it may not invent a class the registry does not declare.
        with pytest.raises(ClassNotEmittableError):
            assert_emitted_subset(["account_unavailable"], mapped)
        with pytest.raises(ClassNotEmittableError):
            assert_emitted_subset(["totally_made_up"], mapped)

    # [utest->req~shared-error-registry-exhaustive~1]
    def test_invalid_request_is_the_one_class_needing_no_mapping(self):
        # It is emitted through the shared mode-signal partition, which belongs to the
        # admission phase and has no internal `core.auth_event_result` at all.
        assert ClientErrorClass.invalid_request not in RESULT_TO_CLASS.values()
        assert_emitted_subset(["invalid_request"], [AuthEventResult.challenge_expired])

    # [utest->req~shared-error-remediation-normative~1]
    def test_each_class_carries_its_own_remediation_and_none_can_be_collapsed(self):
        assert set(REMEDIATIONS) == set(ClientErrorClass)
        actions = [remediation.action for remediation in REMEDIATIONS.values()]
        # Two classes sharing one remediation would let a client collapse them into a single
        # handler; distinct actions are what forbids that.
        assert len(set(actions)) == len(ClientErrorClass)
        # The remediation is data on the contract, not something inferred from the class name.
        assert remediation_for("account_unavailable").action != "account_unavailable"
        with pytest.raises(TaxonomyError):
            remediation_for("not_a_class")


class TestTheClassesGovernEveryRoute:
    # [utest->req~shared-error-classes-govern-all-routes~1]
    def test_a_barrier_rejection_uses_the_shared_classes_and_shape(self):
        for outcome, expected, status in (
                (ResolutionOutcome.blocked_user, "account_unavailable", 403),
                (ResolutionOutcome.historical_identity, "account_unavailable", 403),
                (ResolutionOutcome.pre_auth, "preauth_identity_not_allowed", 403)):
            app = build_app([("POST", "/auth/sync")], resolver=FakeResolver(outcome),
                            writer=make_writer())
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/auth/sync",
                                       headers={"Authorization": f"Bearer {make_token('u')}"})
            assert (response.status_code, response.json()) == (status, {"code": expected})

    # [utest->req~shared-error-classes-govern-all-routes~1]
    def test_an_endpoint_may_add_a_case_but_never_replace_a_shared_class(self):
        distinct = Remediation(action="do_something_else_entirely", http_status=409)
        try:
            # An endpoint-specific class is allowed where its remediation is genuinely its own.
            register_client_class(AuthEventResult.provider_transition_not_allowed,
                                  "create_flow_mismatch", 409,  # type: ignore[invalid-argument-type]
                                  remediation=distinct)
            assert remediation_for("create_flow_mismatch") is distinct
            # Re-using an existing remediation under a new name is not a distinct case.
            with pytest.raises(UnsurfacedResultError):
                register_client_class(AuthEventResult.policy_rejected, "another_name", 409,  # type: ignore[invalid-argument-type]
                                      remediation=Remediation(
                                          action="do_something_else_entirely", http_status=409))
            # And a result the shared contract owns is never remapped.
            with pytest.raises(UnsurfacedResultError):
                register_client_class(AuthEventResult.challenge_expired, "invalid_request", 400)
        finally:
            RESULT_TO_CLASS.pop(AuthEventResult.provider_transition_not_allowed, None)

    # [utest->req~shared-error-no-internal-results-exposed~1]
    def test_no_internal_result_value_reaches_the_client(self):
        # Every mapped internal result surfaces as a declared class, and the three the
        # specification names identically on both sides are the only ones that look alike.
        for result, klass in RESULT_TO_CLASS.items():
            assert klass in set(ClientErrorClass)
            if str(result) == klass:
                assert result in (AuthEventResult.identity_already_linked,
                                  AuthEventResult.preauth_identity_not_allowed,
                                  AuthEventResult.verification_temporarily_unavailable)
        # An unmapped internal result fails closed instead of leaking.
        with pytest.raises(UnsurfacedResultError):
            surface(AuthEventResult.native_claim_write_failed)
        # The response body carries the class and nothing else.
        assert client_response("challenge_required").body == {"code": "challenge_required"}


class TestAuthRequiredGrouping:
    # [utest->req~shared-auth-required-grouping~1]
    def test_auth_required_groups_verification_failure_and_user_not_found(self):
        assert AUTH_REQUIRED_RESULTS == {AuthEventResult.invalid_external_jwt,
                                         AuthEventResult.firebase_user_unresolved}
        assert surface(AuthEventResult.invalid_external_jwt) == ("auth_required", 401)
        # A definitive Firebase Admin `user-not-found` after the token verified is not a
        # transient verification failure: it surfaces through this same class.
        assert surface(AuthEventResult.firebase_user_unresolved) == ("auth_required", 401)
        assert len(set(ProviderDataReadPoint)) == 5
        # Its remediation is to re-authenticate and retry with a fresh ID token.
        assert remediation_for("auth_required").action == \
            "reauthenticate_and_retry_with_fresh_id_token"

    # [utest->req~shared-auth-required-exclusions~1]
    def test_three_results_are_deliberately_not_grouped_under_auth_required(self):
        assert AUTH_REQUIRED_EXCLUSIONS == {
            AuthEventResult.blocked_user: ClientErrorClass.account_unavailable,
            AuthEventResult.preauth_identity_not_allowed:
                ClientErrorClass.preauth_identity_not_allowed,
            AuthEventResult.identity_already_linked: ClientErrorClass.identity_already_linked}
        for result, expected in AUTH_REQUIRED_EXCLUSIONS.items():
            assert surface(result)[0] == expected
            assert result not in AUTH_REQUIRED_RESULTS

    # [utest->req~shared-invalid-external-jwt-reasons~1]
    def test_the_bounded_reason_is_audit_and_metric_only(self):
        # The enumeration is bounded and includes every named branch.
        assert INVALID_EXTERNAL_JWT_REASONS >= {"missing_token", "malformed",
                                                "duplicate_authorization", "bad_signature",
                                                "issuer_mismatch", "audience_mismatch",
                                                "expired", "empty_subject"}
        # Every failure branch returns the same body and status, naming no issuer, integration
        # or failed check.
        bodies = set()
        for reason in JwtRejectionReason:
            error = BarrierRejectionError(AuthEventResult.invalid_external_jwt, str(reason))
            assert error.reason == str(reason)
            bodies.add((error.rejection.status, tuple(sorted(error.body().items()))))
        assert bodies == {(401, (("code", "auth_required"),))}


class TestRemediations:
    # [utest->req~shared-preauth-not-allowed-remediation~1]
    def test_an_unlinked_caller_is_told_to_create_the_user_first(self):
        remediation = remediation_for("preauth_identity_not_allowed")
        assert remediation.next_route == "/auth/create-user"
        assert remediation.http_status == 403
        assert not remediation.terminal
        assert surface(AuthEventResult.preauth_identity_not_allowed)[0] != "auth_required"

    # [utest->req~shared-account-unavailable-remediation~1]
    def test_account_unavailable_is_terminal_and_hides_which_state_caused_it(self):
        # A historical identity and a blocked user are mutually indistinguishable.
        assert surface(AuthEventResult.historical_identity) == \
            surface(AuthEventResult.blocked_user) == ("account_unavailable", 403)
        assert client_response("account_unavailable").body == {"code": "account_unavailable"}
        # A historical identity must never surface `preauth_identity_not_allowed`.
        assert surface(AuthEventResult.historical_identity)[0] != "preauth_identity_not_allowed"
        remediation = remediation_for("account_unavailable")
        # Terminal: discard the stored credentials, stop, and offer no further call — not the
        # same route, not another endpoint, and never "sign out everywhere" as recovery.
        assert remediation.terminal and remediation.discard_credentials
        assert not remediation.retry_same_request
        assert next_route_for("account_unavailable") is None
        assert remediation.next_route is None

    # [utest->req~shared-identity-already-linked-remediation~1]
    def test_an_already_linked_subject_is_sent_to_sync(self):
        klass, status = surface(AuthEventResult.identity_already_linked)
        assert (klass, status) == ("identity_already_linked", 409)
        # Never converted to idempotent success and never a generic 500.
        assert status not in (200, 500)
        assert next_route_for(klass) == "/auth/sync"
        # And never audited as `invalid_external_jwt`.
        assert RESULT_TO_CLASS[AuthEventResult.identity_already_linked] != "auth_required"

    # [utest->req~shared-challenge-required-remediation~1]
    def test_every_challenge_rejection_becomes_one_class_with_one_remedy(self):
        assert CHALLENGE_REQUIRED_RESULTS == {AuthEventResult.challenge_not_found,
                                              AuthEventResult.challenge_identity_mismatch,
                                              AuthEventResult.challenge_operation_mismatch,
                                              AuthEventResult.challenge_expired,
                                              AuthEventResult.challenge_consumed}
        for result in CHALLENGE_REQUIRED_RESULTS:
            assert surface(result) == ("challenge_required", 403)
        assert remediation_for("challenge_required").fresh_challenge is True
        # No `challenge_replayed` result exists, and none was added for the claimed state.
        assert "challenge_replayed" not in AuthEventResult.__members__
        assert "challenge_claimed" not in AuthEventResult.__members__

    # [utest->req~shared-invalid-request-remediation~1]
    def test_invalid_request_is_the_one_class_for_a_wrong_request_shape(self):
        shapes = [([("challenge", "true")], {CHALLENGE_ID_FIELD: "abc"},
                   ModeSignalDefect.both_signals),
                  ([], {}, ModeSignalDefect.neither_signal),
                  ([("challenge", "true"), ("challenge", "true")], None,
                   ModeSignalDefect.duplicate_challenge_param),
                  ([("challenge", "yes")], None, ModeSignalDefect.challenge_param_not_true),
                  ([], {CHALLENGE_ID_FIELD: None}, ModeSignalDefect.malformed_challenge_id),
                  ([], {CHALLENGE_ID_FIELD: ""}, ModeSignalDefect.malformed_challenge_id),
                  ([], {CHALLENGE_ID_FIELD: 17}, ModeSignalDefect.malformed_challenge_id)]
        for query_items, body, defect in shapes:
            with pytest.raises(ModeSignalError) as excinfo:
                classify_mode(query_items, body)
            assert excinfo.value.defect is defect
            assert (excinfo.value.error_code, excinfo.value.status_code) == \
                ("invalid_request", 400)
        assert client_response("invalid_request").status == 400
        remediation = remediation_for("invalid_request")
        assert remediation.action == "correct_the_request_shape_and_resend"
        # The rejection has no side effects, so the corrected retry may reuse the same
        # unexpired challenge; it is not an authentication or challenge-validity signal.
        assert remediation.reuse_unexpired_challenge is True
        assert not remediation.fresh_challenge

    # [utest->req~shared-proof-rejected-remediation~1]
    def test_proof_rejected_carries_no_per_cause_code(self):
        for result in (AuthEventResult.proof_malformed, AuthEventResult.invalid_restore_proof):
            assert surface(result) == ("proof_rejected", 403)
        # The shared shape names the class and no proof or attestation cause.
        assert client_response("proof_rejected").body == {"code": "proof_rejected"}
        remediation = remediation_for("proof_rejected")
        assert remediation.fresh_proof and remediation.fresh_challenge
        assert not remediation.retry_same_request
        # Neither an authentication failure nor a durable anti-abuse block.
        assert remediation.action != remediation_for("auth_required").action
        assert remediation.action != remediation_for("device_grant_exhausted").action

    # [utest->req~shared-operation-not-allowed-remediation~1]
    def test_operation_not_allowed_can_name_the_end_of_the_blocking_state(self):
        from datetime import UTC, datetime
        assert surface(AuthEventResult.provider_account_already_linked) == \
            ("operation_not_allowed", 403)
        assert not remediation_for("operation_not_allowed").retry_same_request
        ends = datetime(2026, 9, 1, tzinfo=UTC)
        response = client_response("operation_not_allowed", blocked_until=ends)
        assert response.body == {"code": "operation_not_allowed",
                                 "blocked_until": ends.isoformat()}
        # A class whose remediation names no blocking state never carries one.
        with pytest.raises(TaxonomyError):
            client_response("challenge_required", blocked_until=ends)

    # [utest->req~shared-verification-required-remediation~1]
    def test_verification_required_is_durable_and_never_retried_on_a_timer(self):
        remediation = remediation_for("verification_required")
        assert remediation.transient is False
        assert remediation.retry_same_request is False
        assert remediation.action == \
            "obtain_registered_identity_then_retry_only_if_state_changed"
        # It is not the transient verification class and must not be handled as one.
        assert remediation != remediation_for("verification_temporarily_unavailable")

    # [utest->req~shared-device-grant-exhausted-remediation~1]
    def test_device_grant_exhausted_depends_on_which_path_closed(self):
        # From the anonymous claim the client is routed to the registered-account path.
        assert device_grant_exhausted_next_path(AuthOperation.claim_anonymous_grant) == \
            "/auth/claim-registered-grant"
        # From the registered claim it stops: no further free-credit path is specified.
        assert device_grant_exhausted_next_path(AuthOperation.claim_registered_grant) is None
        # No other operation emits the class at all.
        with pytest.raises(TaxonomyError):
            device_grant_exhausted_next_path(AuthOperation.sync)
        response = client_response("device_grant_exhausted")
        # HTTP 403 from both grant endpoints, disclosing no device state, hash, anti-abuse
        # result or other diagnostic detail.
        assert response.status == 403
        assert response.body == {"code": "device_grant_exhausted"}
        assert not remediation_for("device_grant_exhausted").retry_same_request

    # [utest->req~shared-account-already-claimed-remediation~1]
    def test_account_already_claimed_is_final_and_not_device_exhaustion(self):
        remediation = remediation_for("account_already_claimed")
        assert remediation.terminal is True
        assert next_route_for("account_already_claimed") is None
        # Distinct from `device_grant_exhausted`: the two must not be conflated.
        assert remediation.action != remediation_for("device_grant_exhausted").action
        assert client_response("account_already_claimed").body["code"] == \
            "account_already_claimed"

    # [utest->req~shared-verification-temporarily-unavailable-remediation~1]
    def test_the_transient_verification_class_is_retried_whole_with_backoff(self):
        for result in (AuthEventResult.firebase_lookup_unavailable,
                       AuthEventResult.verification_temporarily_unavailable):
            assert surface(result)[0] == "verification_temporarily_unavailable"
        remediation = remediation_for("verification_temporarily_unavailable")
        assert remediation.transient is True
        assert remediation.fresh_proof and remediation.fresh_challenge
        assert remediation.http_status == 503
        # Never durable state, and never a reason to switch the user into another flow.
        assert remediation.terminal is False
        assert remediation.switch_flow is False

    # [utest->req~shared-registration-temporarily-unavailable-remediation~1]
    def test_registration_rate_limiting_is_its_own_transient_class(self):
        remediation = remediation_for("registration_temporarily_unavailable")
        assert (remediation.http_status, remediation.transient) == (429, True)
        # The header reflects the longest known wait when more than one limit applies, and the
        # body is identical whichever bucket fired: it never identifies the exhausted bucket.
        per_ip = client_response("registration_temporarily_unavailable",
                                 retry_after_seconds=[30])
        both = client_response("registration_temporarily_unavailable",
                               retry_after_seconds=[30, 900])
        assert per_ip.headers["Retry-After"] == "30"
        assert both.headers["Retry-After"] == "900"
        assert per_ip.body == both.body == {"code": "registration_temporarily_unavailable"}
        assert per_ip.status == both.status == 429
        # It is distinct from `verification_temporarily_unavailable` and never reuses it.
        assert remediation != remediation_for("verification_temporarily_unavailable")
        with pytest.raises(TaxonomyError):
            client_response("verification_temporarily_unavailable", retry_after_seconds=[30])


class TestTheMetric:
    # [utest->req~shared-invalid-external-jwt-metric~1]
    def test_invalid_external_jwt_is_counted_by_reason_and_route(self):
        counter = AuthResultCounter()
        sink = RecordingSink()
        app = build_app([("POST", "/auth/sync"), ("GET", "/users/me")],
                        resolver=FakeResolver(), writer=make_writer(sink=sink, counter=counter))
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/auth/sync")                                   # missing token
            client.get("/users/me", headers={"Authorization": "Bearer nope"})
        # Labeled by bounded reason and route, on the audited path and off it alike, so a
        # systemic verification break is visible even though clients cannot tell it apart from
        # ordinary session expiry.
        assert counter.value(result=AuthEventResult.invalid_external_jwt,
                             route="/auth/sync", reason="missing_token") == 1
        assert counter.value(result=AuthEventResult.invalid_external_jwt,
                             route="/users/me", reason="malformed") == 1
        assert all(reason in INVALID_EXTERNAL_JWT_REASONS
                   for _result, reason, _route in counter.labels())
