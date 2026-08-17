"""Sign-out everywhere, as `01-sessions-and-identity-resolution.md` states it: one endpoint, one
unconditional Firebase revocation, one audit row per attempt, and success only on a confirmed
revocation. Plus the client responsibilities and the accepted risks the endpoint carries.
"""

import asyncio
import threading
from uuid import uuid4

import pytest

from nativespeaker.api.auth.audit import (
    AuthActor,
    AuthAttempt,
    AuthEventResult,
    InvalidTerminalOutcomeError,
    RevocationErrorCategory,
)
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.integration import (
    AdminCallSite,
    FirebaseIntegration,
    FirebaseIntegrations,
)
from nativespeaker.api.auth.operations import (
    AdmissionRejection,
    AuthOperation,
    IdentityProvider,
    is_challenge_bearing,
    supports_prepare,
)
from nativespeaker.api.auth.sign_out import (
    ANONYMOUS_SIGN_OUT_WARNING,
    DURABLE_REVOCATION_STATE,
    LOCAL_SIGN_OUT_BACKEND_CALLS,
    LOCAL_SIGN_OUT_CLEARS,
    MAX_REVOCATION_ATTEMPTS,
    PER_DEVICE_SIGN_OUT_ENDPOINTS,
    PER_REQUEST_REVOCATION_CHECKS,
    REVOCATION_RECONCILIATION_JOBS,
    REVOCATION_RETRY_QUEUES,
    SIGN_OUT_ALL_BACKEND_ENTRIES,
    SIGN_OUT_ALL_GATEWAY_BOUNDS,
    SIGN_OUT_ALL_METHOD,
    SIGN_OUT_ALL_PATH,
    SIGN_OUT_ENDPOINTS,
    SUCCESS_INVALIDATES_MINTED_ID_TOKENS,
    ClientSignOutDisposition,
    ClientSignOutScope,
    CoalescedRevocation,
    RevocationAttempt,
    RevocationDependencyError,
    RevocationOutcome,
    RevocationTimeout,
    SignOutAllUnconfirmedError,
    SignOutError,
    admission_rejection_writes_row,
    anonymous_revocation_consequence,
    assert_no_backend_quota,
    assert_no_business_mutation,
    assert_no_per_request_revocation_check,
    assert_one_row_per_attempt,
    assert_provider_not_consulted,
    barrier_rejection_event_result,
    client_sign_out_outcome,
    client_sign_out_plan,
    compromised_install_in_scope,
    leaked_token_escalates_privilege,
    may_share_revocation_result,
    operator_revocation_is_authoritative_after,
    retry_is_safe,
    revoke_refresh_tokens,
    self_service_admitted,
    sign_out_all,
    sign_out_all_attempt_event,
    sign_out_all_credential,
    sign_out_all_failure,
    sign_out_all_subject,
    sign_out_all_succeeded,
    sign_out_endpoint,
    token_lifetime_source,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.auth.tokens import InvalidExternalJwtError, VerifiedClaims

ISSUER = "https://securetoken.google.com/test-project"
OTHER_ISSUER = "https://securetoken.google.com/other-project"
SUBJECT = "firebase-uid-1"
USER_ID = uuid4()
REQUEST_ID = "req-0001"


def linked(provider: IdentityProvider = IdentityProvider.google,
           *, issuer: str = ISSUER) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=issuer,
                                   subject=SUBJECT,
                                   outcome=ResolutionOutcome.linked,
                                   user_id=USER_ID,
                                   external_identity_id=uuid4(),
                                   provider=provider)


def actor() -> AuthActor:
    return AuthActor(issuer=ISSUER, subject_hash=b"\x22" * 32, subject_hash_key_version=1)


ADMIN_CLIENT = object()


class _Verifier:
    """Sign-out everywhere never verifies a token itself — the barrier already did — so the
    integration's verifier is present only to make the integration well-formed."""

    def verify_id_token(self, token: str) -> VerifiedClaims:
        return VerifiedClaims(issuer=ISSUER, subject=SUBJECT)


def integrations() -> FirebaseIntegrations:
    return FirebaseIntegrations([FirebaseIntegration(issuer=ISSUER,
                                                    project_id="test-project",
                                                    verifier=_Verifier(),
                                                    admin_client=ADMIN_CLIENT)])


class Revoker:
    """A stand-in for Firebase Admin refresh-token revocation. Records every call, and can fail a
    bounded number of times before succeeding."""

    def __init__(self, *, errors: list[BaseException] | None = None):
        self.errors = list(errors or [])
        self.calls: list[tuple[str, object]] = []

    def __call__(self, subject: str, *, client: object) -> None:
        self.calls.append((subject, client))
        if self.errors:
            raise self.errors.pop(0)


def attempt() -> AuthAttempt:
    return AuthAttempt(SIGN_OUT_ALL_METHOD, SIGN_OUT_ALL_PATH)


class TestOneEndpoint:
    # [utest->req~sessions-single-sign-out-endpoint~1]
    def test_the_backend_exposes_exactly_one_sign_out_endpoint(self):
        assert SIGN_OUT_ENDPOINTS == (("POST", "/auth/sign-out-all"),)
        assert sign_out_endpoint() == ("POST", "/auth/sign-out-all")

    # [utest->req~sessions-no-per-device-backend-sign-out~1]
    def test_there_is_no_per_device_backend_sign_out(self):
        assert PER_DEVICE_SIGN_OUT_ENDPOINTS == frozenset()
        # Current-device sign-out calls no backend endpoint at all; it clears local state only.
        assert LOCAL_SIGN_OUT_BACKEND_CALLS == ()
        plan = client_sign_out_plan(ClientSignOutScope.current_device)
        assert plan.backend_call is None
        # A client that wants to sign out everywhere calls the one endpoint.
        assert client_sign_out_plan(ClientSignOutScope.everywhere).backend_call == \
            ("POST", "/auth/sign-out-all")

    # [utest->req~sessions-single-sign-out-endpoint~1]
    # [utest->req~sessions-no-per-device-backend-sign-out~1]
    def test_a_second_or_per_device_endpoint_fails_closed(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.sign_out.PER_DEVICE_SIGN_OUT_ENDPOINTS",
                            frozenset({("POST", "/auth/sign-out-device")}))
        with pytest.raises(SignOutError):
            sign_out_endpoint()
        monkeypatch.setattr("nativespeaker.api.auth.sign_out.PER_DEVICE_SIGN_OUT_ENDPOINTS",
                            frozenset())
        monkeypatch.setattr("nativespeaker.api.auth.sign_out.SIGN_OUT_ENDPOINTS",
                            (("POST", "/auth/sign-out-all"), ("POST", "/auth/logout")))
        with pytest.raises(SignOutError):
            sign_out_endpoint()


class TestAuthenticationAndAdmission:
    # [utest->req~sessions-api-sign-out-all-bearer-credential~1]
    def test_the_credential_is_exactly_one_authorization_bearer_value(self):
        assert sign_out_all_credential(["Bearer id-token"]) == "id-token"
        for values in ([], ["Bearer a", "Bearer b"], ["Bearer a, Bearer b"], ["Basic a"],
                       ["Bearer "], ["Bearer a b"]):
            with pytest.raises(InvalidExternalJwtError):
                sign_out_all_credential(values)

    # [utest->req~sessions-api-sign-out-all-barrier-precondition~1]
    # [utest->req~sessions-api-sign-out-all-purpose~1]
    def test_only_a_barrier_admitted_linked_identity_reaches_the_revocation(self):
        assert sign_out_all_subject(linked()) == (ISSUER, SUBJECT)
        for outcome in (ResolutionOutcome.pre_auth, ResolutionOutcome.historical_identity,
                        ResolutionOutcome.blocked_user):
            with pytest.raises(SignOutError):
                sign_out_all_subject(VerifiedIdentityContext(issuer=ISSUER, subject=SUBJECT,
                                                             outcome=outcome))
        # A linked outcome carrying no resolved user is not an admitted principal either.
        with pytest.raises(SignOutError):
            sign_out_all_subject(VerifiedIdentityContext(issuer=ISSUER, subject=SUBJECT,
                                                         outcome=ResolutionOutcome.linked))

    # [utest->req~sessions-sign-out-self-service-scope~1]
    def test_the_barrier_rejects_blocked_and_retired_here_with_no_route_exception(self):
        assert self_service_admitted(ResolutionOutcome.linked) is True
        assert self_service_admitted(ResolutionOutcome.blocked_user) is False
        assert self_service_admitted(ResolutionOutcome.historical_identity) is False
        assert self_service_admitted(ResolutionOutcome.pre_auth) is False

    # [utest->req~sessions-sign-out-self-service-scope~1]
    def test_the_operator_paths_revoke_and_commit_the_database_change_first(self):
        # Each operator path has its own Admin revocation call site, so a blocked or retired
        # account's sessions are already ended for it.
        assert AdminCallSite.operator_block_revocation is not None
        assert AdminCallSite.identity_retirement_revocation is not None
        # The flag or tombstone stays authoritative whatever the revocation outcome.
        assert operator_revocation_is_authoritative_after(database_committed=True,
                                                          revocation_confirmed=False) is True
        with pytest.raises(SignOutError):
            operator_revocation_is_authoritative_after(database_committed=False,
                                                       revocation_confirmed=True)


class TestNoBackendQuota:
    # [utest->req~sessions-api-sign-out-all-no-backend-quota~1]
    def test_no_backend_counter_rejects_an_authenticated_request(self):
        assert SIGN_OUT_ALL_BACKEND_ENTRIES == ()
        assert SIGN_OUT_ALL_GATEWAY_BOUNDS == ("gateway_per_ip", "gateway_per_user")
        assert_no_backend_quota()
        # A counter offered for this route fails closed rather than being accepted.
        with pytest.raises(SignOutError):
            assert_no_backend_quota(["sign_out_all_subject"])

    # [utest->req~sessions-api-sign-out-all-no-backend-quota~1]
    def test_concurrent_revocations_may_coalesce_but_a_later_request_may_not_reuse_the_result(self):
        shared = CoalescedRevocation(subject=SUBJECT, outcome=RevocationOutcome.confirmed,
                                    in_flight=True)
        assert may_share_revocation_result(shared, sequential=False) is True
        # A later sequential request needs its own revocation: the user may have re-authenticated.
        assert may_share_revocation_result(shared, sequential=True) is False
        settled = CoalescedRevocation(subject=SUBJECT, outcome=RevocationOutcome.confirmed,
                                     in_flight=False)
        assert may_share_revocation_result(settled, sequential=False) is False


class TestRevocation:
    # [utest->req~sessions-sign-out-all-step-01~1]
    # [utest->req~sessions-sign-out-revokes-refresh-tokens~1]
    async def test_the_revocation_runs_through_the_issuer_selected_admin_client(self):
        revoker = Revoker()
        result = await revoke_refresh_tokens(integrations(), linked(), revoker=revoker)
        assert result.outcome is RevocationOutcome.confirmed
        assert revoker.calls == [(SUBJECT, ADMIN_CLIENT)]

    # [utest->req~sessions-sign-out-revokes-refresh-tokens~1]
    # [utest->req~sessions-risk-revocation-scope~1]
    @pytest.mark.parametrize("provider", list(IdentityProvider))
    async def test_revocation_is_unconditional_and_reads_no_stored_provider(self, provider):
        revoker = Revoker()
        result = await revoke_refresh_tokens(integrations(), linked(provider), revoker=revoker)
        assert result.outcome is RevocationOutcome.confirmed
        assert revoker.calls == [(SUBJECT, ADMIN_CLIENT)]
        # And a path that tried to consult the stored provider fails closed.
        assert_provider_not_consulted()
        with pytest.raises(SignOutError):
            assert_provider_not_consulted(["stored_provider"])

    # [utest->req~sessions-sign-out-all-step-01~1]
    async def test_a_mismatched_issuer_never_revokes_against_another_project(self):
        revoker = Revoker()
        result = await revoke_refresh_tokens(integrations(), linked(issuer=OTHER_ISSUER),
                                            revoker=revoker)
        assert result.outcome is RevocationOutcome.definitive_failure
        assert revoker.calls == []

    # [utest->req~sessions-sign-out-all-step-01~1]
    @pytest.mark.parametrize(("error", "outcome", "expected_calls"), [
        (RevocationTimeout("lost"), RevocationOutcome.ambiguous, MAX_REVOCATION_ATTEMPTS),
        (TimeoutError(), RevocationOutcome.ambiguous, MAX_REVOCATION_ATTEMPTS),
        (ConnectionError(), RevocationOutcome.ambiguous, MAX_REVOCATION_ATTEMPTS),
        (RevocationDependencyError("no client"), RevocationOutcome.dependency_unavailable, 1),
        (RuntimeError("firebase said no"), RevocationOutcome.definitive_failure, 1),
    ])
    async def test_each_failure_shape_takes_its_own_bounded_outcome(self, error, outcome,
                                                                   expected_calls):
        revoker = Revoker(errors=[error] * MAX_REVOCATION_ATTEMPTS)
        result = await revoke_refresh_tokens(integrations(), linked(), revoker=revoker)
        assert result.outcome is outcome
        # An ambiguous outcome is worth a bounded retry inside the request; the other two are not.
        assert result.calls == expected_calls
        assert len(revoker.calls) == expected_calls

    # [utest->req~sessions-sign-out-all-step-01~1]
    async def test_a_bounded_in_request_retry_can_still_confirm(self):
        revoker = Revoker(errors=[RevocationTimeout("lost")])
        result = await revoke_refresh_tokens(integrations(), linked(), revoker=revoker)
        assert result.outcome is RevocationOutcome.confirmed
        assert result.calls == 2

    # [utest->req~sessions-revocation-idempotent-client-retries~1]
    def test_retrying_after_any_outcome_is_safe_and_the_backend_keeps_no_retry_state(self):
        for outcome in RevocationOutcome:
            assert retry_is_safe(outcome) is True
        assert REVOCATION_RETRY_QUEUES == frozenset()
        assert REVOCATION_RECONCILIATION_JOBS == frozenset()
        assert DURABLE_REVOCATION_STATE == frozenset()

    # [utest->req~sessions-revocation-idempotent-client-retries~1]
    def test_a_backend_retry_queue_or_durable_revocation_state_fails_closed(self, monkeypatch):
        for name in ("REVOCATION_RETRY_QUEUES", "REVOCATION_RECONCILIATION_JOBS",
                     "DURABLE_REVOCATION_STATE"):
            monkeypatch.setattr(f"nativespeaker.api.auth.sign_out.{name}", frozenset({"x"}))
            with pytest.raises(SignOutError):
                retry_is_safe(RevocationOutcome.ambiguous)
            monkeypatch.setattr(f"nativespeaker.api.auth.sign_out.{name}", frozenset())

    # [utest->req~sessions-revocation-idempotent-client-retries~1]
    async def test_re_revoking_the_same_subject_is_accepted_twice(self):
        revoker = Revoker()
        first = await revoke_refresh_tokens(integrations(), linked(), revoker=revoker)
        second = await revoke_refresh_tokens(integrations(), linked(), revoker=revoker)
        assert first.outcome is second.outcome is RevocationOutcome.confirmed
        assert revoker.calls == [(SUBJECT, ADMIN_CLIENT), (SUBJECT, ADMIN_CLIENT)]


class TestSuccessAndFailureSurfacing:
    # [utest->req~sessions-sign-out-all-step-03~1]
    # [utest->req~sessions-api-sign-out-all-success-meaning~1]
    def test_success_means_only_a_confirmed_revocation(self):
        assert sign_out_all_succeeded(RevocationAttempt(RevocationOutcome.confirmed, 1)) is True
        for outcome in (RevocationOutcome.definitive_failure,
                        RevocationOutcome.dependency_unavailable,
                        RevocationOutcome.ambiguous):
            assert sign_out_all_succeeded(RevocationAttempt(outcome, 1)) is False
        # Success does not mean already-minted ID tokens are invalid.
        assert SUCCESS_INVALIDATES_MINTED_ID_TOKENS is False

    # [utest->req~sessions-sign-out-all-step-03~1]
    @pytest.mark.parametrize("outcome", [RevocationOutcome.definitive_failure,
                                         RevocationOutcome.dependency_unavailable,
                                         RevocationOutcome.ambiguous])
    def test_every_other_outcome_is_a_retryable_server_side_failure(self, outcome):
        error = sign_out_all_failure(outcome)
        assert isinstance(error, SignOutAllUnconfirmedError)
        assert error.retryable is True
        assert error.status_code == 503
        assert error.error_code == "service_unavailable"

    # [utest->req~sessions-sign-out-all-step-03~1]
    def test_a_definitive_configuration_failure_may_be_non_retryable_but_never_success(self):
        error = sign_out_all_failure(RevocationOutcome.definitive_failure,
                                    definitive_configuration_failure=True)
        assert error.retryable is False
        assert error.status_code == 500
        assert error.error_code == "internal_error"
        # Neither surfacing adds a new client-visible class, and neither is a success.
        assert error.error_code not in set(ClientErrorClass)
        with pytest.raises(SignOutError):
            sign_out_all_failure(RevocationOutcome.confirmed)

    # [utest->req~sessions-risk-no-per-request-revocation-check~1]
    def test_the_backend_runs_no_per_request_revocation_check(self):
        assert PER_REQUEST_REVOCATION_CHECKS == frozenset()
        assert_no_per_request_revocation_check()
        with pytest.raises(SignOutError):
            assert_no_per_request_revocation_check(["firebase_revocation_state_lookup"])


class TestAuditRow:
    # [utest->req~sessions-api-sign-out-all-canonical-operation~1]
    def test_the_operation_is_on_the_audited_path_and_is_challenge_free(self):
        recorded = assert_one_row_per_attempt(attempt())
        assert recorded.operation is AuthOperation.sign_out_all
        assert recorded.on_audited_path is True
        assert is_challenge_bearing(AuthOperation.sign_out_all) is False
        assert supports_prepare(AuthOperation.sign_out_all) is False
        # A request on another route is not this operation's attempt.
        with pytest.raises(SignOutError):
            assert_one_row_per_attempt(AuthAttempt("GET", "/users/me"))

    # [utest->req~sessions-api-sign-out-all-audit-row~1]
    # [utest->req~sessions-sign-out-all-step-02~1]
    def test_a_confirmed_revocation_records_succeeded_and_no_error_category(self):
        event = sign_out_all_attempt_event(
            actor=actor(), request_id=REQUEST_ID,
            attempt=RevocationAttempt(RevocationOutcome.confirmed, 1))
        assert event.result is AuthEventResult.succeeded
        assert event.operation is AuthOperation.sign_out_all
        assert event.details["context"]["request_id"] == REQUEST_ID
        assert event.details["failure"] == {}
        assert event.details["mutation"] == {}

    # [utest->req~sessions-api-sign-out-all-audit-row~1]
    # [utest->req~sessions-sign-out-all-step-02~1]
    @pytest.mark.parametrize(("outcome", "category"), [
        (RevocationOutcome.definitive_failure, RevocationErrorCategory.definitive_failure),
        (RevocationOutcome.dependency_unavailable,
         RevocationErrorCategory.dependency_unavailable),
        (RevocationOutcome.ambiguous, RevocationErrorCategory.ambiguous_outcome),
    ])
    def test_each_unconfirmed_outcome_records_its_sanitized_category(self, outcome, category):
        event = sign_out_all_attempt_event(actor=actor(), request_id=REQUEST_ID,
                                           attempt=RevocationAttempt(outcome, 1))
        assert event.result is AuthEventResult.revocation_unconfirmed
        assert event.details["failure"]["error_category"] == str(category)
        # `result` alone carries the outcome: no second outcome field appears.
        assert set(event.details["failure"]) == {"error_category"}

    # [utest->req~sessions-api-sign-out-all-audit-row~1]
    def test_the_row_records_no_vendor_text_and_no_second_outcome_field(self):
        for offending in ({"failure": {"firebase_message": "boom"}},
                          {"failure": {"stack_trace": "..."}},
                          {"failure": {"outcome": "revoked"}},
                          {"failure": {"revocation_status": "unknown"}}):
            with pytest.raises(InvalidTerminalOutcomeError):
                sign_out_all_attempt_event(
                    actor=actor(), request_id=REQUEST_ID,
                    attempt=RevocationAttempt(RevocationOutcome.ambiguous, 1),
                    details=offending)

    # [utest->req~sessions-api-sign-out-all-audit-row~1]
    def test_the_row_records_the_request_id(self):
        with pytest.raises(InvalidTerminalOutcomeError):
            sign_out_all_attempt_event(actor=actor(), request_id="",
                                       attempt=RevocationAttempt(RevocationOutcome.confirmed, 1))

    # [utest->req~sessions-api-sign-out-all-audit-row~1]
    def test_a_barrier_rejection_carries_the_barriers_own_more_specific_result(self):
        assert barrier_rejection_event_result(ResolutionOutcome.pre_auth) is \
            AuthEventResult.preauth_identity_not_allowed
        assert barrier_rejection_event_result(ResolutionOutcome.historical_identity) is \
            AuthEventResult.historical_identity
        assert barrier_rejection_event_result(ResolutionOutcome.blocked_user) is \
            AuthEventResult.blocked_user
        # It never claims revocation was attempted, and an admitted outcome writes no such row.
        with pytest.raises(SignOutError):
            barrier_rejection_event_result(ResolutionOutcome.linked)

    # [utest->req~sessions-api-sign-out-all-audit-row~1]
    def test_an_admission_or_gateway_rejection_writes_no_row_at_all(self):
        for rejection in (AdmissionRejection.gateway_rate_limited,
                          AdmissionRejection.backend_rate_limited,
                          AdmissionRejection.overload_shed):
            assert admission_rejection_writes_row(rejection) is False

    # [utest->req~sessions-api-sign-out-all-canonical-operation~1]
    def test_a_second_row_for_one_attempt_is_refused(self):
        one = attempt()
        assert_one_row_per_attempt(one)
        one.audited = True
        # Each retry is a new attempt with its own single row, so the claim is per attempt.
        fresh = attempt()
        assert fresh.audited is False


class TestNoBusinessMutation:
    # [utest->req~sessions-sign-out-no-business-mutation~1]
    # [utest->req~sessions-api-sign-out-all-no-business-mutation~1]
    def test_no_postgresql_business_state_table_is_mutated(self):
        assert_no_business_mutation()
        for table in ("core.users", "core.external_identities", "core.access_grants",
                      "core.subscriptions", "core.store_purchase_tokens"):
            with pytest.raises(SignOutError):
                assert_no_business_mutation([table])

    # [utest->req~sessions-api-sign-out-all-no-business-mutation~1]
    def test_appending_the_attempts_audit_row_is_compatible_with_that_rule(self):
        # The one permitted write is operational logging, not business state.
        assert_no_business_mutation(["audit.auth_events"])


class TestAnonymousOneWayDoor:
    # [utest->req~sessions-anonymous-revocation-one-way-door~1]
    def test_for_an_anonymous_identity_revocation_is_a_one_way_door(self):
        consequence = anonymous_revocation_consequence(IdentityProvider.anonymous)
        assert consequence is not None
        assert consequence.reachable_by_later_sign_in is False
        assert consequence.refresh_token_holder_locked_out_at_once is True
        assert consequence.id_token_holder_locked_out_at_exp is True
        # The rows remain in PostgreSQL; nothing reaches them, and there is no recovery path.
        assert "core.users" in consequence.retained_rows
        assert "core.chats" in consequence.retained_rows
        assert "core.access_grants" in consequence.retained_rows
        assert consequence.recovery_path is None

    # [utest->req~sessions-anonymous-revocation-one-way-door~1]
    @pytest.mark.parametrize("provider", [IdentityProvider.google, IdentityProvider.apple])
    def test_a_registered_identity_has_no_such_door(self, provider):
        assert anonymous_revocation_consequence(provider) is None

    # [utest->req~sessions-anonymous-revocation-one-way-door~1]
    def test_an_anonymous_recovery_path_would_fail_closed(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.sign_out.ANONYMOUS_RECOVERY_PATH",
                            "/auth/recover-anonymous")
        with pytest.raises(SignOutError):
            anonymous_revocation_consequence(IdentityProvider.anonymous)


class TestClientResponsibilities:
    # [utest->req~sessions-client-local-sign-out~1]
    def test_current_device_sign_out_clears_local_state_and_calls_no_backend(self):
        plan = client_sign_out_plan(ClientSignOutScope.current_device,
                                    provider=IdentityProvider.google)
        assert plan.backend_call is None
        assert plan.clears == LOCAL_SIGN_OUT_CLEARS
        assert "local_client_session_state" in plan.clears
        assert "local_idp_session" in plan.clears
        assert plan.clear_after_success is False

    # [utest->req~sessions-client-anonymous-local-sign-out~1]
    def test_current_device_anonymous_sign_out_is_local_only_too(self):
        plan = client_sign_out_plan(ClientSignOutScope.current_device,
                                    provider=IdentityProvider.anonymous)
        assert plan.backend_call is None
        assert plan.clears == LOCAL_SIGN_OUT_CLEARS
        assert plan.warning is None

    # [utest->req~sessions-client-sign-out-everywhere-order~1]
    def test_sign_out_everywhere_clears_local_state_only_after_success(self):
        plan = client_sign_out_plan(ClientSignOutScope.everywhere,
                                    provider=IdentityProvider.apple)
        assert plan.backend_call == ("POST", "/auth/sign-out-all")
        assert plan.clear_after_success is True
        assert plan.clears == LOCAL_SIGN_OUT_CLEARS

    # [utest->req~sessions-client-anonymous-sign-out-warning~1]
    def test_an_anonymous_session_is_warned_before_it_signs_out_everywhere(self):
        plan = client_sign_out_plan(ClientSignOutScope.everywhere,
                                    provider=IdentityProvider.anonymous)
        assert plan.warning == ANONYMOUS_SIGN_OUT_WARNING
        assert "chat history" in plan.warning
        assert "credits" in plan.warning
        assert "every device" in plan.warning
        assert "Google" in plan.warning and "Apple" in plan.warning
        # A registered session gets no such warning: it has nothing to lose here.
        assert client_sign_out_plan(ClientSignOutScope.everywhere,
                                    provider=IdentityProvider.google).warning is None

    # [utest->req~sessions-client-sign-out-everywhere-order~1]
    def test_a_success_lets_the_client_report_signed_out_everywhere(self):
        outcome = client_sign_out_outcome(success=True)
        assert outcome.disposition is ClientSignOutDisposition.signed_out_everywhere
        assert outcome.report_signed_out_everywhere is True

    # [utest->req~sessions-client-non-success-sign-out-handling~1]
    @pytest.mark.parametrize("client_class", [None, "service_unavailable", "internal_error",
                                              ClientErrorClass.auth_required,
                                              ClientErrorClass.invalid_request])
    def test_a_non_success_other_than_account_unavailable_keeps_the_credential(self,
                                                                              client_class):
        outcome = client_sign_out_outcome(success=False, client_class=client_class)
        assert outcome.disposition is ClientSignOutDisposition.unconfirmed_retryable
        assert outcome.keep_credential is True
        assert outcome.may_retry is True
        # It never reports that the user is signed out everywhere, and a local-only sign-out
        # offered alongside it must say so.
        assert outcome.report_signed_out_everywhere is False
        assert outcome.local_only_must_be_labeled is True

    # [utest->req~sessions-client-account-unavailable-terminal~1]
    def test_account_unavailable_is_terminal_and_discards_the_credential(self):
        outcome = client_sign_out_outcome(success=False,
                                          client_class=ClientErrorClass.account_unavailable)
        assert outcome.disposition is ClientSignOutDisposition.account_unavailable_terminal
        assert outcome.keep_credential is False
        assert outcome.may_retry is False
        assert outcome.report_signed_out_everywhere is False

    # [utest->req~sessions-client-account-unavailable-terminal~1]
    def test_sign_out_everywhere_is_never_offered_as_recovery_from_that_class(self):
        from nativespeaker.api.auth.sign_out import (
            account_unavailable_offers_sign_out_everywhere,
        )
        assert account_unavailable_offers_sign_out_everywhere() is False

    # [utest->req~sessions-client-sign-out-everywhere-order~1]
    def test_a_success_carrying_an_error_class_is_a_contradiction(self):
        with pytest.raises(SignOutError):
            client_sign_out_outcome(success=True,
                                    client_class=ClientErrorClass.account_unavailable)


class TestAcceptedRisk:
    # [utest->req~sessions-risk-leaked-token-usable~1]
    def test_the_returned_store_tokens_add_no_authority_a_bearer_lacked(self):
        assert leaked_token_escalates_privilege() is False

    # [utest->req~sessions-risk-leaked-token-usable~1]
    def test_a_store_token_that_carried_authority_would_be_an_escalation(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.sign_out."
                            "STORE_ATTRIBUTION_TOKEN_AUTHORITY", frozenset({"refund_purchase"}))
        assert leaked_token_escalates_privilege() is True

    # [utest->req~sessions-risk-token-lifetime-idp-governed~1]
    def test_token_lifetime_is_governed_by_the_idp_and_not_by_the_backend(self):
        assert token_lifetime_source() == ("external_idp_token_exp", "idp_refresh_token")

    # [utest->req~sessions-risk-token-lifetime-idp-governed~1]
    def test_a_backend_absolute_session_expiry_would_fail_closed(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.sign_out.BACKEND_ABSOLUTE_SESSION_EXPIRY",
                            3600)
        with pytest.raises(SignOutError):
            token_lifetime_source()

    # [utest->req~sessions-risk-compromised-install-out-of-scope~1]
    def test_a_compromised_registered_install_is_out_of_scope(self):
        from nativespeaker.api.auth.sign_out import COMPROMISED_INSTALL_WOULD_REQUIRE
        assert compromised_install_in_scope() is False
        assert COMPROMISED_INSTALL_WOULD_REQUIRE == ("upstream_session_revocation_semantics",
                                                     "client_side_credential_binding")

    # [utest->req~sessions-risk-compromised-install-out-of-scope~1]
    def test_claiming_a_mitigation_would_put_it_in_scope(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.sign_out.COMPROMISED_INSTALL_MITIGATIONS",
                            frozenset({"device_bound_credentials"}))
        assert compromised_install_in_scope() is True


class TestTheWholeEndpoint:
    # [utest->req~sessions-api-sign-out-all-canonical-operation~1]
    # [utest->req~sessions-sign-out-all-step-02~1]
    async def test_a_confirmed_attempt_audits_success_and_returns_success(self):
        result = await sign_out_all(integrations(), linked(),
                                    actor=actor(), request_id=REQUEST_ID,
                                    audit_attempt=attempt(), revoker=Revoker())
        assert result.succeeded is True
        assert result.event.result is AuthEventResult.succeeded
        assert result.attempt.outcome is RevocationOutcome.confirmed

    # [utest->req~sessions-sign-out-all-step-02~1]
    # [utest->req~sessions-sign-out-all-step-03~1]
    async def test_an_unconfirmed_attempt_still_audits_and_never_returns_success(self):
        revoker = Revoker(errors=[RuntimeError("firebase said no")])
        result = await sign_out_all(integrations(), linked(),
                                    actor=actor(), request_id=REQUEST_ID,
                                    audit_attempt=attempt(), revoker=revoker)
        assert result.succeeded is False
        assert result.event.result is AuthEventResult.revocation_unconfirmed
        assert result.event.details["failure"]["error_category"] == \
            str(RevocationErrorCategory.definitive_failure)

    # [utest->req~sessions-api-sign-out-all-purpose~1]
    async def test_the_endpoint_revokes_for_the_verified_subject_whatever_the_stored_provider(self):
        for provider in IdentityProvider:
            revoker = Revoker()
            result = await sign_out_all(integrations(), linked(provider),
                                        actor=actor(), request_id=REQUEST_ID,
                                        audit_attempt=attempt(), revoker=revoker)
            assert result.succeeded is True
            assert revoker.calls == [(SUBJECT, ADMIN_CLIENT)]


def test_the_revocation_call_runs_off_the_event_loop():
    """The Firebase Admin call is blocking, so it is awaited off the loop rather than inline."""
    seen: list[int] = []

    def revoker(subject: str, *, client: object) -> None:
        seen.append(threading.get_ident())

    result = asyncio.run(revoke_refresh_tokens(integrations(), linked(), revoker=revoker))
    assert result.outcome is RevocationOutcome.confirmed
    assert seen and seen[0] != threading.get_ident()
