"""External IDP token validation and endpoint authorization, the client-visible rejection
classes, the backend trust boundary, pre-auth promotion, and the create-user identity-state
rules, as `01-sessions-and-identity-resolution.md` defines them.
"""

import time
from datetime import UTC, datetime
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

from nativespeaker.api.auth.audit import AuthEventResult, AuthResultCounter
from nativespeaker.api.auth.barrier import (
    GATEWAY_PRESENCE_MARKERS,
    NETWORK_ISOLATION_DATA_ARTIFACTS,
    NETWORK_ISOLATION_IS_LOAD_BEARING,
    OFF_GATEWAY_RESIDUAL_CAPABILITIES,
    OffGatewayTrustError,
    ResolutionOutcome,
    RevocationWindowState,
    VerifiedIdentityContext,
    admission_inputs,
    barrier_result_for,
    extract_bearer_token,
    revocation_window_class,
)
from nativespeaker.api.auth.challenges import ChallengeState
from nativespeaker.api.auth.create_user import (
    CreateUserRejection,
    new_user_row,
    race_loser_rejection,
)
from nativespeaker.api.auth.external_identities import (
    CREATE_USER_RACE_CONTROLS,
    FORBIDDEN_RACE_CONTROLS,
    RACE_LOSER_ROLLBACK,
    ExternalIdentityRow,
    IdentityAlreadyLinkedError,
    IdentityState,
    uniqueness_race_loser,
)
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.profile import AdminUserRecord
from nativespeaker.api.auth.routes import AUTHENTICATED_ROUTES
from nativespeaker.api.auth.taxonomy import (
    ACCOUNT_UNAVAILABLE_RESULTS,
    RESULT_TO_CLASS,
    ClientErrorClass,
    client_response,
    remediation_for,
    surface,
)
from nativespeaker.api.auth.tokens import InvalidExternalJwtError, JwtRejectionReason
from nativespeaker.api.auth.users import (
    ANONYMOUS_RECOVERY_ROUTES,
    SECONDARY_AUTH_STATE,
    CreateUserOutcome,
    UsersError,
    anonymous_session_lost_next_step,
    assert_no_secondary_auth_state,
    complete_create_user,
    create_user_prepare_constraints,
    preauth_context,
    resolves_as_linked,
)
from nativespeaker.api.ratelimit.config import (
    parse_key_policy,
)
from nativespeaker.api.ratelimit.keys import KeyComponent
from unit.conftest import TEST_ISSUER, make_token
from unit.test_auth_barrier import (
    FakeResolver,
    RecordingSink,
    build_app,
    make_verifier,
    make_writer,
)
from unit.test_create_user import (
    GOOGLE,
    FakeAccounts,
    FakeLookup,
    Flow,
)
from unit.test_sessions_preauth_limits import shipped, shipped_gateway

TOKEN_HEADER = "Authorization"

# The completion clock the profile rules are checked against.
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def call(path: str = "/users/me", *,
         method: str = "GET",
         outcome: ResolutionOutcome = ResolutionOutcome.linked,
         headers: dict[str, str] | None = None,
         token: str | None = None,
         sink: RecordingSink | None = None,
         counter: AuthResultCounter | None = None):
    """One request through the real barrier middleware, with the resolution outcome fixed."""
    resolver = FakeResolver(outcome)
    app = build_app([(method, path)], resolver=resolver,
                    writer=make_writer(sink=sink, counter=counter))
    sent = dict(headers or {})
    if token is not None:
        sent[TOKEN_HEADER] = f"Bearer {token}"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.request(method, path, headers=sent)
    return response, resolver


def preauth_identity() -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=TEST_ISSUER, subject="preauth-subject",
                                   outcome=ResolutionOutcome.pre_auth)


def linked_identity() -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=TEST_ISSUER, subject="linked-subject",
                                   outcome=ResolutionOutcome.linked,
                                   user_id=uuid7(), external_identity_id=uuid7(),
                                   provider=IdentityProvider.google)


# --- Endpoint admission after verification ------------------------------------------------------


# [utest->req~sessions-endpoint-admission-after-verification~1]
def test_an_endpoint_is_admitted_only_after_verification_and_resolution():
    admitted, resolver = call(token=make_token("u-1"))
    assert admitted.status_code == 200
    assert admitted.json()["subject"] == "u-1"
    assert resolver.seen == [(TEST_ISSUER, "u-1")]
    # A token that fails the acceptance policy never reaches resolution, so the handler is
    # never entered for it.
    rejected, unused = call(token="not-a-token")
    assert rejected.status_code == 401
    assert unused.seen == []


# [utest->req~sessions-backend-must-reject-list~1]
@pytest.mark.parametrize(("outcome", "token", "status", "code"), [
    (ResolutionOutcome.linked, None, 401, "auth_required"),
    (ResolutionOutcome.linked, "garbage", 401, "auth_required"),
    (ResolutionOutcome.historical_identity, "valid", 403, "account_unavailable"),
    (ResolutionOutcome.blocked_user, "valid", 403, "account_unavailable"),
    (ResolutionOutcome.linked, "valid", 200, None),
])
def test_the_backend_rejects_every_request_on_the_must_reject_list(outcome, token, status, code):
    presented = make_token("u-1") if token == "valid" else token
    response, _resolver = call(outcome=outcome, token=presented)
    assert response.status_code == status
    if code is not None:
        assert response.json()["code"] == code


# [utest->req~sessions-reject-no-bearer-credential~1]
def test_a_request_with_no_conforming_bearer_credential_is_rejected():
    no_header, resolver = call(token=None)
    assert no_header.status_code == 401
    assert no_header.json()["code"] == "auth_required"
    assert resolver.seen == []
    for values, reason in (((), JwtRejectionReason.missing_token),
                           (("Bearer",), JwtRejectionReason.malformed),
                           (("Bearer ",), JwtRejectionReason.missing_token),
                           (("Token abc",), JwtRejectionReason.malformed),
                           (("Bearer a b",), JwtRejectionReason.malformed),
                           (("Bearer a", "Bearer b"), JwtRejectionReason.duplicate_authorization)):
        with pytest.raises(InvalidExternalJwtError) as raised:
            extract_bearer_token(values)
        assert raised.value.reason is reason


# [utest->req~sessions-reject-failed-verification~1]
@pytest.mark.parametrize("claims", [
    {"iss": "https://securetoken.google.com/other-project"},
    {"aud": "other-project"},
    {"exp": time.time() - 60, "iat": time.time() - 120},
    {"sub": ""},
])
def test_a_token_that_fails_verification_for_any_reason_is_rejected(claims):
    response, resolver = call(token=make_token(**claims))
    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"
    # Nothing resolves for it, so no identity state is consulted at all.
    assert resolver.seen == []


# [utest->req~sessions-reject-historical-identity~1]
def test_a_historical_identity_is_rejected_under_its_own_audit_result():
    sink = RecordingSink()
    response, _resolver = call("/auth/sync", method="POST",
                               outcome=ResolutionOutcome.historical_identity,
                               token=make_token("retired"), sink=sink)
    assert response.status_code == 403
    assert response.json() == {"code": "account_unavailable"}
    assert [row["result"] for row in sink.rows] == [AuthEventResult.historical_identity]
    # It never receives the class that would send the client into create-user.
    assert response.json()["code"] != ClientErrorClass.preauth_identity_not_allowed


# [utest->req~sessions-reject-blocked-user~1]
def test_a_blocked_user_is_rejected_under_its_own_audit_result():
    sink = RecordingSink()
    response, _resolver = call("/auth/sync", method="POST",
                               outcome=ResolutionOutcome.blocked_user,
                               token=make_token("blocked"), sink=sink)
    assert response.status_code == 403
    assert response.json() == {"code": "account_unavailable"}
    # Distinct from the historical identity's result, though the client sees the same class.
    assert [row["result"] for row in sink.rows] == [AuthEventResult.blocked_user]


# [utest->req~sessions-token-class-failures-backend-side~1]
def test_the_backend_itself_fails_every_token_class_failure():
    verifier = make_verifier()
    cases = {
        "expired": make_token(exp=time.time() - 60, iat=time.time() - 120),
        "not_yet_valid": make_token(extra_claims={"nbf": time.time() + 3600}),
        "wrong_audience": make_token(aud="other-project"),
        "wrong_issuer": make_token(iss="https://securetoken.google.com/other-project"),
        # A wrong token class: a Firebase custom token names the identity-toolkit audience, and
        # a refresh token is not a JWT at all.
        "custom_token": make_token(
            aud="https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1."
                "IdentityToolkit"),
        "refresh_token": "AMf-opaque-refresh-token-value",
    }
    for name, token in cases.items():
        with pytest.raises(InvalidExternalJwtError) as raised:
            verifier.verify_id_token(token)
        # Each one carries a bounded internal reason; none of them verifies.
        assert raised.value.reason in set(JwtRejectionReason), name
    # No backend rule depends on the gateway having rejected them first: the same tokens are
    # refused with a header claiming the gateway already verified the request.
    response, resolver = call(token=cases["expired"],
                              headers={"X-Jwt-Verified": "true", "X-From-Gateway": "true"})
    assert response.status_code == 401
    assert resolver.seen == []


# [utest->req~sessions-verification-failure-mapping~1]
def test_every_verification_failure_audits_and_surfaces_identically():
    bodies, statuses = set(), set()
    sink = RecordingSink()
    for token in ("nonsense", make_token(aud="other-project"),
                  make_token(exp=time.time() - 60, iat=time.time() - 120)):
        response, _resolver = call("/auth/sync", method="POST", token=token, sink=sink)
        bodies.add(str(response.json()))
        statuses.add(response.status_code)
    assert bodies == {str({"code": "auth_required"})}
    assert statuses == {401}
    # One audit result for all of them, and it is `invalid_external_jwt`.
    assert [row["result"] for row in sink.rows] == [AuthEventResult.invalid_external_jwt] * 3
    assert surface(AuthEventResult.invalid_external_jwt) == ("auth_required", 401)


# [utest->req~sessions-preauth-context-from-verified-claims~1]
def test_the_preauth_context_is_the_verified_pair_and_nothing_minted():
    context = preauth_identity()
    assert preauth_context(context) == (TEST_ISSUER, "preauth-subject")
    # No user, identity row or stored provider stands in for it, and no backend-minted claim
    # exists to carry it.
    with pytest.raises(UsersError):
        preauth_context(VerifiedIdentityContext(issuer=TEST_ISSUER, subject="s",
                                                outcome=ResolutionOutcome.pre_auth,
                                                user_id=uuid7()))
    with pytest.raises(UsersError):
        preauth_context(linked_identity())
    assert not hasattr(context, "backend_token")
    assert not hasattr(context, "backend_claims")


# --- Client-visible rejection classes ----------------------------------------------------------


# [utest->req~sessions-rejection-classes~1]
def test_authenticated_route_rejections_use_only_the_declared_classes():
    declared = {str(one) for one in ClientErrorClass}
    used = {str(one) for one in RESULT_TO_CLASS.values()}
    assert used <= declared
    # The classes this file names are all present in the shared mapping.
    assert {"auth_required", "preauth_identity_not_allowed", "account_unavailable",
            "identity_already_linked", "operation_not_allowed"} <= used
    for result in RESULT_TO_CLASS:
        client_class, status = surface(result)
        assert client_response(client_class).status == status


# [utest->req~sessions-class-auth-required~1]
def test_auth_required_means_the_token_was_not_accepted():
    client_class, status = surface(AuthEventResult.invalid_external_jwt)
    assert (client_class, status) == ("auth_required", 401)
    remediation = remediation_for(ClientErrorClass.auth_required)
    assert remediation.action == "reauthenticate_and_retry_with_fresh_id_token"
    assert not remediation.terminal
    response, _resolver = call(token="rejected-by-the-backend")
    assert response.json() == {"code": "auth_required"}


# [utest->req~sessions-class-preauth-identity-not-allowed~1]
def test_preauth_identity_not_allowed_sends_the_client_to_create_user():
    client_class, status = surface(AuthEventResult.preauth_identity_not_allowed)
    assert (client_class, status) == ("preauth_identity_not_allowed", 403)
    assert remediation_for(client_class).next_route == "/auth/create-user"
    # A pre-auth identity on a linked-only route earns exactly that class.
    assert barrier_result_for(ResolutionOutcome.pre_auth, "GET", "/users/me") is \
        AuthEventResult.preauth_identity_not_allowed
    response, _resolver = call(outcome=ResolutionOutcome.pre_auth, token=make_token("fresh"))
    assert response.json() == {"code": "preauth_identity_not_allowed"}


# [utest->req~sessions-class-account-unavailable~1]
def test_account_unavailable_covers_a_historical_identity_and_a_blocked_user():
    for result in ACCOUNT_UNAVAILABLE_RESULTS:
        assert surface(result) == ("account_unavailable", 403)
    assert set(ACCOUNT_UNAVAILABLE_RESULTS) == {AuthEventResult.historical_identity,
                                                AuthEventResult.blocked_user}
    remediation = remediation_for(ClientErrorClass.account_unavailable)
    assert remediation.terminal and remediation.discard_credentials


# [utest->req~sessions-class-identity-already-linked~1]
def test_identity_already_linked_is_the_create_user_conflict():
    client_class, status = surface(AuthEventResult.identity_already_linked)
    assert (client_class, status) == ("identity_already_linked", 409)
    assert remediation_for(client_class).next_route == "/auth/sync"
    # Both phases of create-user produce it for an identity that already resolves as linked.
    with pytest.raises(ChallengeRejection) as prepare:
        create_user_prepare_constraints(linked_identity(), "anonymous")
    assert prepare.value.result is AuthEventResult.identity_already_linked


# [utest->req~sessions-class-operation-not-allowed~1]
def test_operation_not_allowed_carries_the_structural_conflicts():
    for result in (AuthEventResult.policy_rejected,
                   AuthEventResult.provider_account_already_linked):
        assert surface(result) == ("operation_not_allowed", 403)
    remediation = remediation_for(ClientErrorClass.operation_not_allowed)
    assert remediation.action == "remedy_structural_state_before_retrying"
    assert remediation.carries_blocking_end


# [utest->req~sessions-preauth-class-rationale~1]
def test_the_preauth_class_stays_its_own_and_is_not_folded_into_auth_required():
    preauth = remediation_for(ClientErrorClass.preauth_identity_not_allowed)
    auth_required = remediation_for(ClientErrorClass.auth_required)
    assert preauth != auth_required
    assert preauth.action != auth_required.action
    assert surface(AuthEventResult.preauth_identity_not_allowed)[0] != "auth_required"
    # It is the signal that sends the client into create-user, and it reveals nothing about
    # existing accounts: the body names the class and carries nothing else.
    assert preauth.next_route == "/auth/create-user"
    assert client_response(ClientErrorClass.preauth_identity_not_allowed).body == {
        "code": ClientErrorClass.preauth_identity_not_allowed}


# [utest->req~sessions-account-unavailable-shared-shape~1]
def test_historical_and_blocked_are_indistinguishable_to_clients_but_not_internally():
    historical, _ = call("/auth/sync", method="POST",
                         outcome=ResolutionOutcome.historical_identity,
                         token=make_token("retired"))
    blocked, _ = call("/auth/sync", method="POST", outcome=ResolutionOutcome.blocked_user,
                      token=make_token("blocked"))
    # Same status, same machine-readable code, same generic copy, and no state-specific field.
    assert historical.status_code == blocked.status_code == 403
    assert historical.json() == blocked.json() == {"code": "account_unavailable"}
    assert set(historical.json()) == {"code"}
    # Neither maps to `auth_required`, which would leave the client looping on a valid token.
    for result in ACCOUNT_UNAVAILABLE_RESULTS:
        assert RESULT_TO_CLASS[result] != ClientErrorClass.auth_required
    # Internally the two keep distinct audit results.
    assert AuthEventResult.historical_identity is not AuthEventResult.blocked_user
    assert barrier_result_for(ResolutionOutcome.historical_identity, "POST", "/auth/sync") is \
        AuthEventResult.historical_identity
    assert barrier_result_for(ResolutionOutcome.blocked_user, "POST", "/auth/sync") is \
        AuthEventResult.blocked_user


# [utest->req~sessions-historical-and-blocked-rejection-everywhere~1]
def test_both_states_are_rejected_on_every_route_including_create_user():
    for route in AUTHENTICATED_ROUTES:
        method, path = route.method, route.path
        assert barrier_result_for(ResolutionOutcome.historical_identity, method, path) is \
            AuthEventResult.historical_identity
        assert barrier_result_for(ResolutionOutcome.blocked_user, method, path) is \
            AuthEventResult.blocked_user
    # Including the pre-auth-declared create-user route, where a historical identity must never
    # enter and never receives `preauth_identity_not_allowed`.
    assert barrier_result_for(ResolutionOutcome.historical_identity,
                              "POST", "/auth/create-user") is AuthEventResult.historical_identity
    assert barrier_result_for(ResolutionOutcome.pre_auth, "POST", "/auth/create-user") is None


# [utest->req~sessions-single-lookup-path-no-early-exit~1]
def test_all_four_outcomes_come_out_of_one_lookup_with_no_early_exit():
    for outcome in ResolutionOutcome:
        response, resolver = call("/auth/sync", method="POST", outcome=outcome,
                                  token=make_token("subject"))
        # Exactly one resolution query, whatever the outcome: no extra query for a state and no
        # outcome-dependent second path.
        assert resolver.seen == [(TEST_ISSUER, "subject")]
        assert response.status_code in (200, 403)
    # And no state-specific externally observable side effect: the two rejected states are
    # externally identical.
    historical, _ = call("/auth/sync", method="POST",
                         outcome=ResolutionOutcome.historical_identity, token=make_token("s"))
    blocked, _ = call("/auth/sync", method="POST", outcome=ResolutionOutcome.blocked_user,
                      token=make_token("s"))
    assert (historical.status_code, historical.json(), sorted(historical.headers)) == \
        (blocked.status_code, blocked.json(), sorted(blocked.headers))


# [utest->req~sessions-residual-unlinked-vs-historical-oracle~1]
def test_the_create_user_oracle_is_accepted_and_bounded_by_the_gateway_limits():
    # Unlinked proceeds; historical refuses. That difference is the accepted residual.
    assert create_user_prepare_constraints(preauth_identity(), "anonymous") is \
        IdentityProvider.anonymous
    historical = VerifiedIdentityContext(issuer=TEST_ISSUER, subject="retired",
                                         outcome=ResolutionOutcome.historical_identity)
    with pytest.raises(ChallengeRejection) as raised:
        create_user_prepare_constraints(historical, "anonymous")
    assert raised.value.result is AuthEventResult.historical_identity
    # It is bounded by the route's required gateway limits, keyed on the client IP and bucketed
    # by /64 for IPv6.
    gateway = shipped_gateway()
    assert parse_key_policy(gateway.create_user_ip.key) == (KeyComponent.ip,)
    assert shipped()["rate_limits"]["client_address"]["ipv6_prefix"] == 64


# [utest->req~sessions-revocation-window-no-distinct-class~1]
def test_the_revocation_window_needs_no_distinct_class():
    assert revocation_window_class(RevocationWindowState.no_mintable_token) == "auth_required"
    assert revocation_window_class(RevocationWindowState.unexpired_id_token) == \
        "account_unavailable"
    # Both sides are classes the contract already defines: no third class exists for the window.
    for state in RevocationWindowState:
        assert revocation_window_class(state) in {str(one) for one in ClientErrorClass}
    # A still-valid token for a blocked subject reaches resolution and surfaces the terminal
    # class; an expired one fails acceptance and surfaces `auth_required`.
    reached, _ = call(outcome=ResolutionOutcome.blocked_user, token=make_token("blocked"))
    expired, _ = call(outcome=ResolutionOutcome.blocked_user,
                      token=make_token("blocked", exp=time.time() - 60, iat=time.time() - 120))
    assert reached.json() == {"code": "account_unavailable"}
    assert expired.json() == {"code": "auth_required"}


# --- The backend trust boundary ----------------------------------------------------------------


# [utest->req~sessions-network-isolation-recommended~1]
def test_isolation_is_defence_in_depth_and_never_a_trust_precondition():
    assert NETWORK_ISOLATION_IS_LOAD_BEARING is False
    # Admission reads the one identity carrier and no gateway-presence marker.
    assert admission_inputs(["Authorization", "X-Envoy-Internal", "X-Forwarded-Client-Cert"]) == \
        ("authorization",)
    # A request carrying no marker at all — one that reached the pod off-gateway — is admitted on
    # its token exactly as a gateway-forwarded one is.
    off_gateway, _resolver = call(token=make_token("u-1"))
    through_gateway, _ = call(token=make_token("u-1"),
                              headers=dict.fromkeys(sorted(GATEWAY_PRESENCE_MARKERS), "1"))
    assert off_gateway.status_code == through_gateway.status_code == 200
    assert off_gateway.json() == through_gateway.json()


# [utest->req~sessions-off-gateway-access-accepted-risk~1]
def test_an_off_gateway_caller_mints_no_identity_and_only_bypasses_the_limits():
    # Without a valid token the caller is rejected, however convincingly it claims to be the
    # gateway or an in-cluster workload.
    faked = dict.fromkeys(sorted(GATEWAY_PRESENCE_MARKERS), "1")
    rejected, resolver = call(token="not-a-real-token", headers=faked)
    assert rejected.status_code == 401
    assert resolver.seen == []
    # With a valid token the caller simply is that subject, exactly as through the gateway.
    admitted, resolver = call(token=make_token("victim"), headers=faked)
    assert admitted.status_code == 200
    assert admitted.json()["subject"] == "victim"
    # The residual capability is bypassing the gateway's rate limits, and nothing else.
    assert OFF_GATEWAY_RESIDUAL_CAPABILITIES == {"bypasses_gateway_rate_limits"}
    assert NETWORK_ISOLATION_DATA_ARTIFACTS == frozenset()
    # An admission path that declared it also read a gateway marker fails closed.
    with pytest.raises(OffGatewayTrustError):
        admission_inputs(["Authorization", "X-From-Gateway"],
                         consulted=("authorization", "x-from-gateway"))


# --- Pre-auth promotion -------------------------------------------------------------------------


def identity_row(user_id, *, provider: IdentityProvider = IdentityProvider.anonymous):
    return ExternalIdentityRow(id=uuid7(), user_id=user_id, issuer=TEST_ISSUER,
                               subject="preauth-subject", provider=provider,
                               provider_uid=None if provider is IdentityProvider.anonymous
                               else "provider-account-uid",
                               identity_state=IdentityState.active)


# [utest->req~sessions-preauth-promotion-obligations~1]
async def test_a_successful_create_user_promotes_the_preauth_identity():
    flow = Flow()
    created = await flow.complete("anonymous")
    # The identity row now exists for the verified pair, the account exists with it, and the
    # response carries backend state alone.
    assert created.identity.identity_state is IdentityState.active
    assert created.identity.user_id == created.user.id
    assert created.backend_token is None
    assert flow.audited() == [AuthEventResult.succeeded]
    assert flow.row().state is ChallengeState.consumed


# [utest->req~sessions-promotion-create-identity-row~1]
async def test_the_identity_row_carries_the_classified_provider():
    flow = Flow(lookup=FakeLookup(GOOGLE))
    created = await flow.complete("google", variant=IdentityProvider.google)
    assert created.identity.provider is IdentityProvider.google
    assert created.identity.provider_uid == "google-account-id"
    # A row carrying anything other than what the classifier returned is refused.
    session = object()
    user_id = uuid7()
    with pytest.raises(UsersError):
        complete_create_user(user_id=user_id,
                             identity=identity_row(user_id, provider=IdentityProvider.anonymous),
                             completion_transaction=session, identity_transaction=session,
                             classified=IdentityProvider.google)
    # The matching provider is accepted.
    assert complete_create_user(user_id=user_id,
                                identity=identity_row(user_id,
                                                      provider=IdentityProvider.anonymous),
                                completion_transaction=session, identity_transaction=session,
                                classified=IdentityProvider.anonymous).user_id == user_id


# [utest->req~sessions-promotion-single-transaction~1]
async def test_the_user_row_the_identity_row_and_the_profile_commit_together():
    session = object()
    user_id = uuid7()
    outcome = complete_create_user(user_id=user_id, identity=identity_row(user_id),
                                   completion_transaction=session, identity_transaction=session)
    assert isinstance(outcome, CreateUserOutcome)
    assert outcome.transaction is session
    # A second transaction for the identity row is refused outright.
    with pytest.raises(UsersError):
        complete_create_user(user_id=user_id, identity=identity_row(user_id),
                             completion_transaction=session, identity_transaction=object())
    # `registered_at` is NULL for an anonymous creation and non-null for a registered one, and
    # the verified-email copy lands in the same row.
    anonymous = new_user_row(IdentityProvider.anonymous, None, now=NOW)
    registered = new_user_row(IdentityProvider.google,
                              AdminUserRecord(email="user@example.com", email_verified=True),
                              now=NOW)
    assert anonymous.registered_at is None and anonymous.email is None
    assert registered.registered_at == NOW
    assert registered.email == "user@example.com"
    # A partial failure leaves nothing: the losing insert rolls user, identity and provider back.
    accounts = FakeAccounts()
    accounts.raises = IdentityAlreadyLinkedError("the winner got there first")
    flow = Flow(accounts=accounts)
    with pytest.raises(CreateUserRejection):
        await flow.complete("anonymous")
    assert accounts.users == {}
    assert accounts.identities.find(TEST_ISSUER, flow.context.subject) is None


# [utest->req~sessions-promotion-no-backend-token~1]
async def test_promotion_returns_no_backend_token():
    flow = Flow()
    created = await flow.complete("anonymous")
    assert created.backend_token is None
    user_id = uuid7()
    session = object()
    with pytest.raises(UsersError):
        complete_create_user(user_id=user_id, identity=identity_row(user_id),
                             completion_transaction=session, identity_transaction=session,
                             backend_token="minted")


# [utest->req~sessions-no-secondary-auth-state~1]
def test_no_secondary_auth_state_and_no_generation_exist():
    assert SECONDARY_AUTH_STATE == frozenset()
    assert_no_secondary_auth_state()
    with pytest.raises(UsersError):
        assert_no_secondary_auth_state({"session_version": 2})
    with pytest.raises(UsersError):
        assert_no_secondary_auth_state(generation=1)
    # The same external token resolves as linked next request purely because the row exists.
    user_id = uuid7()
    row = identity_row(user_id)
    context = VerifiedIdentityContext(issuer=TEST_ISSUER, subject="preauth-subject",
                                      outcome=ResolutionOutcome.linked, user_id=user_id,
                                      external_identity_id=row.id,
                                      provider=IdentityProvider.anonymous)
    assert resolves_as_linked(row, context) is True


# [utest->req~sessions-no-anonymous-account-recovery~1]
def test_a_lost_anonymous_session_registers_instead_of_recovering():
    assert ANONYMOUS_RECOVERY_ROUTES == frozenset()
    assert anonymous_session_lost_next_step() == ("POST /auth/create-user", "registered")
    # No route recovers a prior anonymous account.
    assert not [route for route in AUTHENTICATED_ROUTES if "recover" in route.path]


# --- Create-user identity-state rules -----------------------------------------------------------


# [utest->req~sessions-create-user-preauth-only~1]
async def test_both_phases_are_preauth_only():
    # Prepare rejects a linked identity with the conflict class, never with
    # `preauth_identity_not_allowed` and never as idempotent success.
    with pytest.raises(ChallengeRejection) as prepare:
        create_user_prepare_constraints(linked_identity(), "anonymous")
    assert prepare.value.result is AuthEventResult.identity_already_linked
    # Completion rejects it too, and writes nothing.
    accounts = FakeAccounts(outcome=ResolutionOutcome.linked)
    flow = Flow(accounts=accounts)
    with pytest.raises(CreateUserRejection) as completion:
        await flow.complete("anonymous")
    assert completion.value.result is AuthEventResult.identity_already_linked
    assert completion.value.status_code == 409
    assert accounts.users == {}
    # A historical identity and a blocked user keep their own distinct rejections.
    for outcome, result in ((ResolutionOutcome.historical_identity,
                             AuthEventResult.historical_identity),
                            (ResolutionOutcome.blocked_user, AuthEventResult.blocked_user)):
        rejected = Flow(accounts=FakeAccounts(outcome=outcome))
        with pytest.raises(CreateUserRejection) as raised:
            await rejected.complete("anonymous")
        assert raised.value.result is result


# [utest->req~sessions-create-user-prepare-check-best-effort~1]
async def test_the_prepare_check_is_best_effort_and_never_authoritative():
    # Prepare from a linked identity issues no challenge at all.
    flow = Flow()
    with pytest.raises(ChallengeRejection):
        await flow.endpoint.check_prepare_eligibility(linked_identity(),
                                                      IdentityProvider.anonymous)
    assert flow.h.store.rows == {}
    # And a pre-auth prepare is not evidence for completion: the subject that became linked
    # between the phases is still rejected, so the racy check is never relied on.
    accounts = FakeAccounts(outcome=ResolutionOutcome.linked)
    raced = Flow(accounts=accounts)
    with pytest.raises(CreateUserRejection) as raised:
        await raced.complete("anonymous")
    assert raised.value.result is AuthEventResult.identity_already_linked


# [utest->req~sessions-create-user-completion-re-resolves~1]
async def test_completion_re_resolves_inside_the_consuming_transaction():
    # The re-resolution happens against the store, inside the transaction that consumes the
    # challenge, and its verdict decides the outcome.
    admitted = Flow()
    created = await admitted.complete("anonymous")
    assert created.user.id in admitted.accounts.users
    assert admitted.accounts.sessions, "the mutation ran in the consuming transaction"
    for outcome, result in ((ResolutionOutcome.linked, AuthEventResult.identity_already_linked),
                            (ResolutionOutcome.historical_identity,
                             AuthEventResult.historical_identity),
                            (ResolutionOutcome.blocked_user, AuthEventResult.blocked_user)):
        accounts = FakeAccounts(outcome=outcome)
        flow = Flow(accounts=accounts)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is result
        # No user, identity, profile or grant state is mutated on any of those paths.
        assert accounts.users == {}
        assert accounts.identities.find(TEST_ISSUER, flow.context.subject) is None


# [utest->req~sessions-create-user-unique-constraint-arbiter~1]
async def test_the_unique_constraint_arbitrates_two_unlinked_observers():
    accounts = FakeAccounts()
    accounts.raises = IdentityAlreadyLinkedError("the winner got there first")
    flow = Flow(accounts=accounts)
    with pytest.raises(CreateUserRejection) as raised:
        await flow.complete("anonymous")
    # The loser returns the same conflict as the pre-check path and audits it as its own result.
    assert raised.value.result is AuthEventResult.identity_already_linked
    assert raised.value.status_code == 409
    assert flow.audited() == [AuthEventResult.identity_already_linked]
    # Every business mutation rolls back, and it never touches per-device grant state.
    assert accounts.users == {}
    assert accounts.identities.find(TEST_ISSUER, flow.context.subject) is None
    assert {"user_row", "identity_row", "grant", "per_device_grant_state_read",
            "per_device_grant_state_write"} <= RACE_LOSER_ROLLBACK
    # Never a generic server error, never `invalid_external_jwt`.
    outcome = uniqueness_race_loser()
    assert outcome.result is AuthEventResult.identity_already_linked
    assert outcome.client_class is ClientErrorClass.identity_already_linked
    assert race_loser_rejection().status_code != 500


# [utest->req~sessions-loser-challenge-consumed~1]
async def test_the_losers_challenge_is_consumed_and_survives_the_rollback():
    accounts = FakeAccounts()
    accounts.raises = IdentityAlreadyLinkedError("the winner got there first")
    flow = Flow(accounts=accounts)
    with pytest.raises(CreateUserRejection):
        await flow.complete("anonymous")
    # Single-use holds for the rejected attempt: the row is consumed, the business mutation is
    # rolled back, and the rejected audit result survives that rollback.
    assert flow.row().state is ChallengeState.consumed
    assert flow.h.factory.log.count("rollback_to_savepoint") == 1
    assert flow.audited() == [AuthEventResult.identity_already_linked]
    assert accounts.users == {}


# [utest->req~sessions-grant-side-effects-winner-only~1]
async def test_grant_side_effects_belong_to_the_winning_insert_alone():
    # The winner's completion creates account and identity state and no grant of its own.
    winner = Flow()
    created = await winner.complete("anonymous")
    assert created.user.id in winner.accounts.users
    with pytest.raises(UsersError):
        complete_create_user(user_id=created.user.id, identity=created.identity,
                             completion_transaction=winner.accounts.sessions[0],
                             identity_transaction=winner.accounts.sessions[0],
                             grant_writes=("access_grant", "device_grant_state"))
    # The loser's grant and per-device grant state roll back with the rest.
    assert "grant" in RACE_LOSER_ROLLBACK
    assert "per_device_grant_state_read" in RACE_LOSER_ROLLBACK
    loser_accounts = FakeAccounts()
    loser_accounts.raises = IdentityAlreadyLinkedError("the winner got there first")
    loser = Flow(accounts=loser_accounts)
    with pytest.raises(CreateUserRejection):
        await loser.complete("anonymous")
    assert loser_accounts.users == {}


# [utest->req~sessions-loser-no-recovery-api~1]
async def test_the_loser_needs_no_recovery_api():
    rejection = race_loser_rejection()
    # The remedy is `/auth/sync` on the winning account: no recovery endpoint, no idempotent
    # success, no second user and no second grant.
    assert remediation_for(rejection.error_code).next_route == "/auth/sync"
    assert rejection.error_code == ClientErrorClass.identity_already_linked
    accounts = FakeAccounts()
    accounts.raises = IdentityAlreadyLinkedError("the winner got there first")
    flow = Flow(accounts=accounts)
    with pytest.raises(CreateUserRejection):
        await flow.complete("anonymous")
    assert accounts.users == {}
    assert not [route for route in AUTHENTICATED_ROUTES if "recover" in route.path]
    assert CREATE_USER_RACE_CONTROLS and not FORBIDDEN_RACE_CONTROLS
