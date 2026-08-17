"""Operation challenge transport and binding, as `01-sessions-and-identity-resolution.md` states
it: the handle travels in two bodies and nowhere else, prepare responses are `no-store`, nothing
logs the handle, completion always needs the current verified ID token, and the binding stays
proportionate.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.auth.challenge_transport import (
    ACCEPTED_ATTACKER_ALREADY_COMPROMISED_ACCOUNT,
    CACHE_CONTROL_HEADER,
    LOGGING_SINKS,
    NO_STORE,
    OUT_OF_SCOPE_HARDENING,
    PERMITTED_LOCATIONS,
    PROPORTIONATE_CONTROLS,
    REJECTED_BINDINGS,
    URL_LOCATIONS,
    IdentitySource,
    TransportError,
    TransportLocation,
    assert_not_in_url,
    assert_nothing_logs_the_handle,
    assert_prepare_response_safe,
    assert_proportionate_controls,
    assert_transport_location,
    client_error_message,
    completion_identity,
    log_correlation_id,
    prepare_response_headers,
)
from nativespeaker.api.auth.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengeRow,
    IdentityBinding,
    PrepareResponse,
    new_challenge_id,
)
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.tokens import VerifiedClaims

ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "firebase-uid-1"
NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def row(challenge_id: str | None = None) -> ChallengeRow:
    return ChallengeRow(id=uuid7(),
                        challenge_id=challenge_id or new_challenge_id(),
                        operation=AuthOperation.claim_registered_grant,
                        operation_variant=None,
                        binding=IdentityBinding(bound_external_identity_id=uuid7()),
                        expires_at=NOW + timedelta(seconds=CHALLENGE_TTL_SECONDS))


class TestTransport:
    # [utest->req~sessions-challenge-transport-body-only~1]
    def test_the_handle_travels_in_the_two_bodies_and_nowhere_else(self):
        assert PERMITTED_LOCATIONS == {TransportLocation.prepare_response_body,
                                       TransportLocation.completion_request_body}
        for permitted in PERMITTED_LOCATIONS:
            assert assert_transport_location(permitted) is permitted
        for forbidden in (TransportLocation.request_header, TransportLocation.response_header,
                          TransportLocation.cookie, TransportLocation.url_path,
                          TransportLocation.query_string, TransportLocation.audit_row):
            with pytest.raises(TransportError):
                assert_transport_location(forbidden)

    # [utest->req~sessions-challenge-transport-body-only~1]
    def test_an_unrecognized_location_is_refused_rather_than_passed_through(self):
        with pytest.raises(TransportError):
            assert_transport_location("grpc_metadata")

    # [utest->req~sessions-challenge-transport-body-only~1]
    def test_the_two_bodies_ride_on_https_only(self):
        with pytest.raises(TransportError):
            assert_transport_location(TransportLocation.prepare_response_body, scheme="http")

    # [utest->req~sessions-challenge-transport-never-in-url~1]
    def test_the_handle_never_appears_in_a_url_path_or_query_string(self):
        handle = new_challenge_id()
        assert_not_in_url(path="/auth/claim-registered-grant", query="", challenge_id=handle)
        with pytest.raises(TransportError):
            assert_not_in_url(path=f"/auth/complete/{handle}", query="", challenge_id=handle)
        with pytest.raises(TransportError):
            assert_not_in_url(path="/auth/complete", query=f"challenge_id={handle}",
                              challenge_id=handle)
        # Both URL locations are on the forbidden list in their own right.
        assert URL_LOCATIONS == {TransportLocation.url_path, TransportLocation.query_string}

    # [utest->req~sessions-challenge-transport-never-in-url~1]
    def test_the_handle_is_never_written_to_an_audit_row(self):
        with pytest.raises(TransportError):
            assert_transport_location(TransportLocation.audit_row)


class TestNoStore:
    # [utest->req~sessions-challenge-transport-no-store~1]
    def test_a_prepare_response_carries_cache_control_no_store(self):
        assert prepare_response_headers()[CACHE_CONTROL_HEADER] == NO_STORE
        # It is added even when the caller supplied other headers.
        headers = prepare_response_headers({"Content-Type": "application/json"})
        assert headers[CACHE_CONTROL_HEADER] == NO_STORE
        assert headers["Content-Type"] == "application/json"

    # [utest->req~sessions-challenge-transport-no-store~1]
    @pytest.mark.parametrize("weaker", ["private, max-age=60", "no-cache", "public"])
    def test_a_caller_cannot_weaken_it(self, weaker):
        with pytest.raises(TransportError):
            prepare_response_headers({"Cache-Control": weaker})

    # [utest->req~sessions-challenge-transport-no-store~1]
    def test_a_case_differing_header_name_is_still_the_same_field(self):
        with pytest.raises(TransportError):
            prepare_response_headers({"cache-control": "max-age=300"})
        assert prepare_response_headers({"cache-control": "no-store"})[CACHE_CONTROL_HEADER] == \
            NO_STORE

    # [utest->req~sessions-challenge-transport-no-store~1]
    # [utest->req~sessions-challenge-transport-body-only~1]
    def test_a_prepare_response_is_checked_before_it_goes_out(self):
        challenge = row()
        response = PrepareResponse(challenge_id=challenge.challenge_id,
                                   expires_at=challenge.expires_at)
        assert assert_prepare_response_safe(response, challenge) is response
        # A response carrying some other row's handle is refused.
        with pytest.raises(TransportError):
            assert_prepare_response_safe(response, row())


class TestNoPlaintextLogging:
    # [utest->req~sessions-challenge-transport-no-plaintext-logging~1]
    def test_the_server_side_row_id_is_what_is_logged_for_correlation(self):
        challenge = row()
        assert log_correlation_id(challenge) == str(challenge.id)
        assert log_correlation_id(challenge) != challenge.challenge_id

    # [utest->req~sessions-challenge-transport-no-plaintext-logging~1]
    def test_a_row_whose_id_is_the_handle_fails_closed(self):
        row_id = uuid7()
        challenge = ChallengeRow(id=row_id,
                                 challenge_id=str(row_id),
                                 operation=AuthOperation.claim_registered_grant,
                                 operation_variant=None,
                                 binding=IdentityBinding(bound_external_identity_id=uuid7()),
                                 expires_at=NOW + timedelta(seconds=CHALLENGE_TTL_SECONDS))
        with pytest.raises(TransportError):
            log_correlation_id(challenge)

    # [utest->req~sessions-challenge-transport-no-plaintext-logging~1]
    @pytest.mark.parametrize("build", [
        lambda handle: {"challenge_id": handle},
        lambda handle: {"message": f"challenge {handle} expired"},
        lambda handle: {"context": {"nested": {"handle": handle}}},
        lambda handle: {"tags": [handle]},
        lambda handle: {"detail": ("prepared", handle)},
    ])
    def test_no_log_trace_or_error_payload_may_carry_the_handle(self, build):
        handle = new_challenge_id()
        with pytest.raises(TransportError):
            assert_nothing_logs_the_handle(build(handle), challenge_id=handle)
        # A payload carrying only the row id is fine.
        assert_nothing_logs_the_handle({"challenge_row_id": str(uuid7())}, challenge_id=handle)

    # [utest->req~sessions-challenge-transport-no-plaintext-logging~1]
    def test_every_named_sink_is_covered(self):
        assert LOGGING_SINKS == {TransportLocation.access_log,
                                 TransportLocation.application_log,
                                 TransportLocation.trace,
                                 TransportLocation.analytics,
                                 TransportLocation.error_report,
                                 TransportLocation.client_visible_error}
        for sink in LOGGING_SINKS:
            with pytest.raises(TransportError):
                assert_transport_location(sink)

    # [utest->req~sessions-challenge-transport-no-plaintext-logging~1]
    def test_a_client_visible_error_message_names_no_handle(self):
        challenge = row()
        message = client_error_message(challenge)
        assert challenge.challenge_id not in message
        assert_nothing_logs_the_handle({"message": message},
                                       challenge_id=challenge.challenge_id)


class TestNotACredential:
    # [utest->req~sessions-challenge-binding-not-a-credential~1]
    def test_completion_identity_comes_only_from_the_verified_id_token(self):
        claims = VerifiedClaims(issuer=ISSUER, subject=SUBJECT)
        assert completion_identity(claims) == (ISSUER, SUBJECT)

    # [utest->req~sessions-challenge-binding-not-a-credential~1]
    def test_a_challenge_handle_alone_authenticates_nobody(self):
        with pytest.raises(TransportError):
            completion_identity(None, challenge_id=new_challenge_id())

    # [utest->req~sessions-challenge-binding-not-a-credential~1]
    @pytest.mark.parametrize("source", [IdentitySource.request_body_field,
                                        IdentitySource.client_supplied_header,
                                        IdentitySource.proxy_supplied_header,
                                        IdentitySource.challenge_row])
    def test_no_body_field_header_or_challenge_row_establishes_the_identity(self, source):
        claims = VerifiedClaims(issuer=ISSUER, subject=SUBJECT)
        with pytest.raises(TransportError):
            completion_identity(claims, source=source)

    # [utest->req~sessions-challenge-binding-not-a-credential~1]
    def test_an_empty_verified_issuer_or_subject_is_no_identity(self):
        for claims in (VerifiedClaims(issuer="", subject=SUBJECT),
                       VerifiedClaims(issuer=ISSUER, subject="")):
            with pytest.raises(TransportError):
                completion_identity(claims)

    # [utest->req~sessions-challenge-binding-not-a-credential~1]
    def test_treating_the_challenge_as_a_credential_would_fail_closed(self, monkeypatch):
        monkeypatch.setattr(
            "nativespeaker.api.auth.challenge_transport.CHALLENGE_IS_A_CREDENTIAL", True)
        with pytest.raises(TransportError):
            completion_identity(VerifiedClaims(issuer=ISSUER, subject=SUBJECT))


class TestProportionality:
    # [utest->req~sessions-challenge-binding-proportionality~1]
    def test_the_proportionate_controls_are_exactly_these_five(self):
        assert assert_proportionate_controls(PROPORTIONATE_CONTROLS) == PROPORTIONATE_CONTROLS
        assert PROPORTIONATE_CONTROLS == ("exact_identity_binding",
                                          "random_challenge_ids_128_bit",
                                          "short_challenge_lifetime",
                                          "single_use",
                                          "existing_gateway_rate_limits")

    # [utest->req~sessions-challenge-binding-proportionality~1]
    @pytest.mark.parametrize("rejected", sorted(REJECTED_BINDINGS))
    def test_no_network_device_or_key_binding_is_added(self, rejected):
        with pytest.raises(TransportError):
            assert_proportionate_controls([rejected])

    # [utest->req~sessions-challenge-binding-proportionality~1]
    @pytest.mark.parametrize("hardening", sorted(OUT_OF_SCOPE_HARDENING))
    def test_the_optional_prepare_time_hardening_stays_out_of_scope(self, hardening):
        with pytest.raises(TransportError):
            assert_proportionate_controls([hardening])

    # [utest->req~sessions-challenge-binding-proportionality~1]
    def test_a_control_outside_the_set_is_refused_too(self):
        with pytest.raises(TransportError):
            assert_proportionate_controls(["captcha_on_completion"])

    # [utest->req~sessions-challenge-binding-proportionality~1]
    def test_the_two_numeric_controls_are_read_from_the_challenge_module(self):
        assert CHALLENGE_ID_BYTES * 8 == 128
        assert 0 < CHALLENGE_TTL_SECONDS <= 900
        assert ACCEPTED_ATTACKER_ALREADY_COMPROMISED_ACCOUNT is True

    # [utest->req~sessions-challenge-binding-proportionality~1]
    def test_a_shortened_challenge_id_fails_closed(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.challenge_transport.CHALLENGE_ID_BYTES", 8)
        with pytest.raises(TransportError):
            assert_proportionate_controls()
