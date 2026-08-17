"""The shared pre-handler barrier, the route partition, the single Firebase integration,
ID-token verification, and the shared auth audit contract."""

import hashlib
import time
from contextlib import asynccontextmanager
from typing import Any

import pytest
import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.audit import (
    NO_ACTOR,
    AttemptPhase,
    AuditAlreadyWrittenError,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEventResult,
    AuthResultCounter,
    InvalidTerminalOutcomeError,
    OffPathAuditError,
    terminal_event,
)
from nativespeaker.api.auth.barrier import (
    AuthBarrier,
    AuthBarrierMiddleware,
    BarrierRejectionError,
    ResolutionOutcome,
    ResolvedIdentity,
    VerifiedIdentityContext,
    extract_bearer_token,
    verified_identity,
)
from nativespeaker.api.auth.integration import (
    FirebaseIntegration,
    FirebaseIntegrationConfigError,
    FirebaseIntegrations,
    UnrecognizedProviderError,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.routes import (
    AUTHENTICATED_ROUTES,
    ID_TOKEN_REQUIRED_ROUTES,
    PROVIDER_CALLBACK_ROUTES,
    PUBLIC_ROUTES,
    AuthenticatedRoute,
    ProviderCallbackRoute,
    RouteCategory,
    RouteCategoryError,
    assert_route_categories,
    categorize,
    is_pre_auth_callable,
)
from nativespeaker.api.auth.tokens import (
    CachedGoogleSigningKeys,
    FirebaseIdTokenVerifier,
    InvalidExternalJwtError,
    JwtRejectionReason,
)
from unit.conftest import PUBLIC_KEY_PEM, TEST_ISSUER, TEST_PROJECT_ID, make_token

ADMIN_CLIENT = object()


def make_verifier(*, issuer: str = TEST_ISSUER, audience: str = TEST_PROJECT_ID):
    return FirebaseIdTokenVerifier(issuer=issuer,
                                   audience=audience,
                                   key_resolver=lambda _token: PUBLIC_KEY_PEM)


def make_integrations(**kwargs) -> FirebaseIntegrations:
    return FirebaseIntegrations([FirebaseIntegration(issuer=TEST_ISSUER,
                                                     project_id=TEST_PROJECT_ID,
                                                     verifier=make_verifier(**kwargs),
                                                     admin_client=ADMIN_CLIENT)])


# A subject hasher with the shape the audit contract requires: a 32-byte HMAC digest plus the
# version of the key that produced it.
TEST_SUBJECT_HASH_KEY_VERSION = 7


def subject_hasher(subject: str) -> tuple[bytes, int]:
    return hashlib.sha256(b"barrier-test-key|" + subject.encode()).digest(), \
        TEST_SUBJECT_HASH_KEY_VERSION


def verified_test_actor(provider: IdentityProvider | None = None) -> AuthActor:
    digest, key_version = subject_hasher("actor-subject")
    return AuthActor(issuer=TEST_ISSUER, subject_hash=digest,
                     subject_hash_key_version=key_version, provider=provider)


class RecordingSink:
    """The writer hands a sink the built `audit.auth_events` row, never the raw event, so a
    sink cannot write anything `auth_event_row` did not redact and validate."""

    def __init__(self, fail: bool = False):
        self.rows: list[dict[str, Any]] = []
        self.sessions: list[Any] = []
        self.fail = fail

    async def insert(self, session: Any, row: Any) -> None:
        if self.fail:
            raise RuntimeError("audit insert failed")
        self.sessions.append(session)
        self.rows.append(dict(row))


class FakeSession:
    def __init__(self):
        self.committed = 0

    async def commit(self) -> None:
        self.committed += 1


def make_session_factory(sessions: list[FakeSession]):
    @asynccontextmanager
    async def factory():
        session = FakeSession()
        sessions.append(session)
        yield session
    return factory


class FakeResolver:
    def __init__(self, outcome: ResolutionOutcome = ResolutionOutcome.linked,
                 provider: IdentityProvider | None = IdentityProvider.google):
        self.outcome = outcome
        self.provider = provider
        self.seen: list[tuple[str, str]] = []

    async def resolve(self, issuer: str, subject: str) -> ResolvedIdentity:
        self.seen.append((issuer, subject))
        provider = self.provider if self.outcome is ResolutionOutcome.linked else None
        return ResolvedIdentity(outcome=self.outcome, provider=provider)


def make_writer(*, sink: RecordingSink | None = None,
                counter: AuthResultCounter | None = None,
                sessions: list[FakeSession] | None = None) -> AuthAuditWriter:
    return AuthAuditWriter(sink=sink or RecordingSink(),
                           counter=counter or AuthResultCounter(),
                           session_factory=make_session_factory(sessions
                                                                if sessions is not None else []))


def build_app(routes, *, resolver: FakeResolver, writer: AuthAuditWriter,
              with_barrier: bool = True) -> FastAPI:
    app = FastAPI()

    async def handler(request: Request,
                      identity: VerifiedIdentityContext = Depends(verified_identity)):
        return {"issuer": identity.issuer,
                "subject": identity.subject,
                "provider": identity.provider,
                "outcome": identity.outcome,
                "verified_by": type(request.app.state.auth_barrier).__name__}

    for method, path in routes:
        app.add_api_route(path, handler, methods=[method])
    register_exception_handlers(app)
    if with_barrier:
        app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]
    app.state.auth_barrier = AuthBarrier(integrations=make_integrations(),
                                         resolver=resolver,
                                         audit=writer,
                                         subject_hasher=subject_hasher)
    return app


class TestIdTokenVerification:
    # [utest->req~shared-verify-id-token~1]
    def test_accepts_a_correctly_signed_token(self):
        claims = make_verifier().verify_id_token(make_token("user-1"))
        assert claims.issuer == TEST_ISSUER
        assert claims.subject == "user-1"

    # [utest->req~shared-verify-id-token~1]
    @pytest.mark.parametrize(("token_kwargs", "reason"), [
        ({"iss": "https://securetoken.google.com/other"}, JwtRejectionReason.issuer_mismatch),
        ({"aud": "other-project"}, JwtRejectionReason.audience_mismatch),
        ({"exp": time.time() - 3600, "iat": time.time() - 7200}, JwtRejectionReason.expired),
        ({"sub": ""}, JwtRejectionReason.empty_subject),
    ])
    def test_rejects_tokens_failing_the_acceptance_policy(self, token_kwargs, reason):
        with pytest.raises(InvalidExternalJwtError) as exc:
            make_verifier().verify_id_token(make_token(**token_kwargs))
        assert exc.value.reason is reason

    # [utest->req~shared-verify-id-token~1]
    def test_rejects_unsigned_and_wrongly_signed_tokens(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
        with pytest.raises(InvalidExternalJwtError) as bad_signature:
            make_verifier().verify_id_token(make_token(private_key=other_pem))
        assert bad_signature.value.reason is JwtRejectionReason.bad_signature
        # An unverifiable token's claims are never read.
        unsigned = make_token(algorithm="none", private_key=None)  # type: ignore[invalid-argument-type]
        with pytest.raises(InvalidExternalJwtError) as unsigned_error:
            make_verifier().verify_id_token(unsigned)
        assert unsigned_error.value.reason is JwtRejectionReason.malformed

    # [utest->req~shared-verify-id-token~1]
    def test_the_signing_key_comes_from_the_cached_google_key_set(self):
        # The verifier resolves its key through the JWKS client rather than a constant, and it
        # resolves it once per verification.
        keys = CachedGoogleSigningKeys(jwks_url="https://example.invalid/jwks")
        keys._client = _StubJwkClient(PUBLIC_KEY_PEM)   # noqa: SLF001
        verifier = FirebaseIdTokenVerifier(issuer=TEST_ISSUER, audience=TEST_PROJECT_ID,
                                           key_resolver=keys)
        assert verifier.verify_id_token(make_token("user-1")).subject == "user-1"
        assert keys._client.calls == 1                  # noqa: SLF001

    # [utest->req~shared-verify-id-token~1]
    # [utest->req~shared-invalid-external-jwt-reasons~1]
    def test_a_key_fetch_outage_is_not_a_malformed_token(self):
        # A JWKS outage is a systemic backend-verification break. It must not be recorded and
        # counted as a client-side `malformed` token, which is what a resolver call inside the
        # decode's catch-all would make it.
        def unavailable(_token):
            raise ConnectionError("jwks endpoint unreachable")

        verifier = FirebaseIdTokenVerifier(issuer=TEST_ISSUER, audience=TEST_PROJECT_ID,
                                           key_resolver=unavailable)
        with pytest.raises(InvalidExternalJwtError) as exc:
            verifier.verify_id_token(make_token("user-1"))
        assert exc.value.reason is JwtRejectionReason.signing_key_unavailable


class _StubJwkClient:
    """Stands in for `PyJWKClient`, counting how often a key is resolved."""

    def __init__(self, key):
        self.key = key
        self.calls = 0

    def get_signing_key_from_jwt(self, token):
        self.calls += 1
        return self.key


class TestSingleFirebaseIntegration:
    # [utest->req~shared-single-firebase-integration~1]
    def test_configuration_carries_exactly_one_integration(self):
        integration = FirebaseIntegration(issuer=TEST_ISSUER, project_id=TEST_PROJECT_ID,
                                          verifier=make_verifier(), admin_client=ADMIN_CLIENT)
        with pytest.raises(FirebaseIntegrationConfigError):
            FirebaseIntegrations([])
        with pytest.raises(FirebaseIntegrationConfigError):
            FirebaseIntegrations([integration, integration])
        assert FirebaseIntegrations([integration]).sole is integration

    # [utest->req~shared-single-firebase-integration~1]
    def test_admin_client_is_selected_by_the_matched_issuer(self):
        integrations = make_integrations()
        assert integrations.admin_client_for_issuer(TEST_ISSUER) is ADMIN_CLIENT
        # An issuer mismatch fails before any Firebase Admin lookup, with no fallback client.
        with pytest.raises(InvalidExternalJwtError) as exc:
            integrations.admin_client_for_issuer("https://securetoken.google.com/other")
        assert exc.value.reason is JwtRejectionReason.issuer_mismatch

    # [utest->req~shared-single-firebase-integration~1]
    def test_provider_classifier_is_closed(self):
        class Entry:
            def __init__(self, provider_id):
                self.provider_id = provider_id

        assert FirebaseIntegrations.classify_provider([]) == "anonymous"
        assert FirebaseIntegrations.classify_provider([Entry("google.com")]) == "google"
        assert FirebaseIntegrations.classify_provider([Entry("apple.com")]) == "apple"
        for shape in ([Entry("facebook.com")], [Entry("google.com"), Entry("facebook.com")],
                      [Entry(None)]):
            with pytest.raises(UnrecognizedProviderError):
                FirebaseIntegrations.classify_provider(shape)


class TestBearerCredential:
    # [utest->req~shared-bearer-single-identity-carrier~1]
    def test_authorization_is_the_only_identity_carrier(self):
        resolver = FakeResolver()
        app = build_app([("POST", "/auth/sync")], resolver=resolver, writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={"Authorization": f"Bearer {make_token('real-subject')}",
                                            "X-Forwarded-User": "spoofed-subject",
                                            "X-Jwt-Claim-Sub": "spoofed-subject",
                                            "X-Endpoint-Api-Userinfo": "spoofed-subject"})
        assert response.status_code == 200
        assert response.json()["subject"] == "real-subject"
        assert resolver.seen == [(TEST_ISSUER, "real-subject")]

    # [utest->req~shared-bearer-single-identity-carrier~1]
    def test_missing_duplicate_and_malformed_authorization(self):
        with pytest.raises(InvalidExternalJwtError) as missing:
            extract_bearer_token([])
        assert missing.value.reason is JwtRejectionReason.missing_token
        with pytest.raises(InvalidExternalJwtError) as duplicate:
            extract_bearer_token(["Bearer a", "Bearer b"])
        assert duplicate.value.reason is JwtRejectionReason.duplicate_authorization
        with pytest.raises(InvalidExternalJwtError) as malformed:
            extract_bearer_token(["Basic abc"])
        assert malformed.value.reason is JwtRejectionReason.malformed
        with pytest.raises(InvalidExternalJwtError) as empty:
            extract_bearer_token(["Bearer "])
        assert empty.value.reason is JwtRejectionReason.missing_token

    # [utest->req~shared-bearer-single-identity-carrier~1]
    # [utest->req~sessions-wire-bearer-scheme-case~1]
    def test_the_scheme_matches_case_insensitively_and_the_token_bytes_do_not(self):
        # RFC 6750: the scheme name is case-insensitive.
        for scheme in ("Bearer", "bearer", "BEARER", "BeArEr"):
            assert extract_bearer_token([f"{scheme} AbC.dEf"]) == "AbC.dEf"
        # The token bytes are case-sensitive: they come back exactly as sent, never folded.
        assert extract_bearer_token(["Bearer AbC.dEf"]) != "abc.def"
        # Another scheme is not a Bearer credential.
        with pytest.raises(InvalidExternalJwtError) as basic:
            extract_bearer_token(["Basic AbC.dEf"])
        assert basic.value.reason is JwtRejectionReason.malformed


class TestPreHandlerBarrier:
    # [utest->req~shared-prehandler-barrier~1]
    def test_handlers_receive_the_typed_context_from_the_barrier(self):
        resolver = FakeResolver(provider=IdentityProvider.apple)
        app = build_app([("GET", "/users/me")], resolver=resolver, writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me",
                                  headers={"Authorization": f"Bearer {make_token('u1')}"})
        body = response.json()
        assert response.status_code == 200
        assert body["outcome"] == ResolutionOutcome.linked
        assert body["provider"] == IdentityProvider.apple

    # [utest->req~shared-prehandler-barrier~1]
    def test_a_route_wired_outside_the_barrier_rejects(self):
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer(),
                        with_barrier=False)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me",
                                  headers={"Authorization": f"Bearer {make_token('u1')}"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    # [utest->req~shared-prehandler-barrier~1]
    @pytest.mark.parametrize(("outcome", "status", "code"), [
        (ResolutionOutcome.historical_identity, 403, "account_unavailable"),
        (ResolutionOutcome.blocked_user, 403, "account_unavailable"),
        (ResolutionOutcome.pre_auth, 403, "preauth_identity_not_allowed"),
    ])
    def test_the_barrier_evaluates_the_resolution_outcomes(self, outcome, status, code):
        app = build_app([("POST", "/auth/sync")], resolver=FakeResolver(outcome),
                        writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={"Authorization": f"Bearer {make_token('u1')}"})
        assert response.status_code == status
        assert response.json()["code"] == code

    # [utest->req~shared-identity-from-verified-claims-only~1]
    def test_identity_comes_from_verified_claims_and_provider_never_from_them(self):
        resolver = FakeResolver(provider=IdentityProvider.google)
        app = build_app([("POST", "/auth/sync")], resolver=resolver, writer=make_writer())
        token = make_token("verified-subject",
                           extra_claims={"provider": "apple",
                                         "firebase": {"sign_in_provider": "apple"},
                                         "user_id": "claimed-other"})
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={"Authorization": f"Bearer {token}",
                                            "X-Provider": "apple"})
        body = response.json()
        assert body["subject"] == "verified-subject"
        assert body["issuer"] == TEST_ISSUER
        # `provider` is the stored value the resolver supplied, not the token's claim.
        assert body["provider"] == IdentityProvider.google


class TestRouteCategories:
    # [utest->req~shared-route-categories~1]
    def test_every_registered_route_is_in_exactly_one_category(self):
        from nativespeaker.api.app.main import app as real_app
        assert_route_categories(real_app)

    # [utest->req~shared-route-categories~1]
    def test_the_assertion_fails_closed_on_an_undeclared_route(self):
        app = FastAPI()

        @app.get("/secret/backdoor")
        async def backdoor():
            return {}

        with pytest.raises(RouteCategoryError):
            assert_route_categories(app)

    # [utest->req~shared-route-categories~1]
    def test_the_assertion_rejects_generic_callback_bypass_and_double_membership(self,
                                                                                monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.routes.PROVIDER_CALLBACK_ROUTES",
                            (ProviderCallbackRoute("POST", "/webhooks/app-store", "external"),))
        with pytest.raises(RouteCategoryError, match="named verifier"):
            assert_route_categories(FastAPI())

        monkeypatch.setattr("nativespeaker.api.auth.routes.PROVIDER_CALLBACK_ROUTES",
                            (ProviderCallbackRoute("GET", "/health/ready", "pubsub_oidc"),))
        with pytest.raises(RouteCategoryError, match="more than one category"):
            assert_route_categories(FastAPI())

    # [utest->req~shared-route-categories~1]
    def test_categories_and_the_pre_auth_declaration(self):
        assert categorize("GET", "/health/ready") is RouteCategory.public
        assert categorize("POST", "/webhooks/app-store") is RouteCategory.provider_callback
        assert categorize("POST", "/auth/sync") is RouteCategory.authenticated
        # Authentication is the default: an undeclared route is authenticated at runtime.
        assert categorize("GET", "/newly/added") is RouteCategory.authenticated
        assert is_pre_auth_callable("POST", "/auth/create-user") is True
        for route in AUTHENTICATED_ROUTES:
            if route.path != "/auth/create-user":
                assert is_pre_auth_callable(route.method, route.path) is False

    # [utest->req~shared-route-categories~1]
    def test_pre_auth_identities_are_admitted_only_on_create_user(self):
        app = build_app([("POST", "/auth/create-user"), ("POST", "/auth/sync")],
                        resolver=FakeResolver(ResolutionOutcome.pre_auth), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            headers = {"Authorization": f"Bearer {make_token('u1')}"}
            assert client.post("/auth/create-user?challenge=true", headers=headers).status_code == 200
            assert client.post("/auth/sync", headers=headers).status_code == 403


ID_TOKEN_FAMILIES = {
    "auth_sync": ("POST", "/auth/sync"),
    "challenge_prepare": ("POST", "/auth/create-user"),
    "completion": ("POST", "/auth/upgrade-anonymous"),
    "restore_subscription": ("POST", "/auth/restore-subscription"),
    "users_me": ("GET", "/users/me"),
    "chat_quota": ("GET", "/chats"),
    "sign_out_everywhere": ("POST", "/auth/sign-out-all"),
}


def assert_family_requires_id_token(method: str, path: str) -> None:
    """No token is rejected; a verified Firebase ID token is admitted."""
    app = build_app([(method, path)], resolver=FakeResolver(), writer=make_writer())
    with TestClient(app, raise_server_exceptions=False) as client:
        anonymous = client.request(method, path)
        authenticated = client.request(
            method, path, headers={"Authorization": f"Bearer {make_token('u1')}"})
    assert (method, path) in ID_TOKEN_REQUIRED_ROUTES
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "auth_required"
    assert authenticated.status_code == 200
    assert authenticated.json()["subject"] == "u1"


class TestIdTokenRequiredEndpoints:
    # [utest->req~shared-id-token-required-endpoints~1]
    # [utest->req~sessions-authenticated-endpoint-families~1]
    def test_every_listed_family_requires_the_id_token(self):
        for method, path in ID_TOKEN_FAMILIES.values():
            assert (method, path) in ID_TOKEN_REQUIRED_ROUTES
            assert categorize(method, path) is RouteCategory.authenticated

    # [utest->req~shared-id-token-endpoint-auth-sync~1]
    # [utest->req~sessions-authfamily-auth-sync~1]
    def test_auth_sync_requires_the_id_token(self):
        assert_family_requires_id_token(*ID_TOKEN_FAMILIES["auth_sync"])

    # [utest->req~shared-id-token-endpoint-challenge-prepare~1]
    # [utest->req~sessions-authfamily-challenge-prepare~1]
    def test_challenge_prepare_requires_the_id_token(self):
        assert_family_requires_id_token(*ID_TOKEN_FAMILIES["challenge_prepare"])

    # [utest->req~shared-id-token-endpoint-completion~1]
    # [utest->req~sessions-authfamily-completion-calls~1]
    def test_completion_calls_require_the_id_token(self):
        assert_family_requires_id_token(*ID_TOKEN_FAMILIES["completion"])

    # [utest->req~shared-id-token-endpoint-restore-subscription~1]
    # [utest->req~sessions-authfamily-restore-subscription~1]
    def test_restore_subscription_requires_the_id_token(self):
        assert_family_requires_id_token(*ID_TOKEN_FAMILIES["restore_subscription"])

    # [utest->req~shared-id-token-endpoint-users-me~1]
    # [utest->req~sessions-authfamily-users-me~1]
    def test_users_me_requires_the_id_token(self):
        assert_family_requires_id_token(*ID_TOKEN_FAMILIES["users_me"])

    # [utest->req~shared-id-token-endpoint-chat-quota~1]
    # [utest->req~sessions-authfamily-chat-and-quota~1]
    def test_chat_and_quota_endpoints_require_the_id_token(self):
        assert_family_requires_id_token(*ID_TOKEN_FAMILIES["chat_quota"])
        assert ("GET", "/users/me/quota") in ID_TOKEN_REQUIRED_ROUTES

    # [utest->req~shared-id-token-endpoint-sign-out-everywhere~1]
    # [utest->req~sessions-authfamily-sign-out-all~1]
    def test_sign_out_everywhere_requires_the_id_token(self):
        assert_family_requires_id_token(*ID_TOKEN_FAMILIES["sign_out_everywhere"])


class TestAuditContract:
    # [utest->req~shared-path-single-audit-row~1]
    async def test_one_row_per_attempt_and_never_a_second(self):
        sink = RecordingSink()
        writer = make_writer(sink=sink)
        attempt = AuthAttempt("POST", "/auth/sync")
        event = terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                               operation=AuthOperation.sync, actor=verified_test_actor())
        await writer.write_standalone(attempt, event)
        assert len(sink.rows) == 1
        with pytest.raises(AuditAlreadyWrittenError):
            await writer.write_standalone(attempt, event)
        assert len(sink.rows) == 1

    # [utest->req~shared-audit-outcome-barrier-rejection~1]
    def test_a_barrier_rejection_takes_the_actor_null_row_shape(self):
        actor = AuthActor(issuer=TEST_ISSUER, subject_hash=b"x", subject_hash_key_version=1)
        event = terminal_event(AttemptPhase.barrier, AuthEventResult.invalid_external_jwt,
                               operation=AuthOperation.sync, actor=actor)
        assert event.actor == NO_ACTOR
        assert event.actor.issuer is None and event.actor.subject_hash is None
        # The other barrier results keep the verified actor they resolved.
        blocked = terminal_event(AttemptPhase.barrier, AuthEventResult.blocked_user,
                                 operation=AuthOperation.sync, actor=actor)
        assert blocked.actor is actor
        with pytest.raises(InvalidTerminalOutcomeError):
            terminal_event(AttemptPhase.barrier, AuthEventResult.challenge_expired)

    # [utest->req~shared-audit-outcome-prepare-rejection~1]
    def test_a_prepare_phase_rejection_is_a_terminal_outcome(self):
        event = terminal_event(AttemptPhase.prepare, AuthEventResult.identity_already_linked,
                               operation=AuthOperation.create_user)
        assert event.result is AuthEventResult.identity_already_linked
        with pytest.raises(InvalidTerminalOutcomeError):
            terminal_event(AttemptPhase.prepare, AuthEventResult.succeeded)

    # [utest->req~shared-audit-outcome-business-rejection~1]
    def test_a_business_validation_rejection_is_a_terminal_outcome(self):
        event = terminal_event(AttemptPhase.business, AuthEventResult.invalid_restore_proof,
                               operation=AuthOperation.restore_subscription)
        assert event.result is AuthEventResult.invalid_restore_proof
        for forbidden in (AuthEventResult.succeeded, AuthEventResult.blocked_user):
            with pytest.raises(InvalidTerminalOutcomeError):
                terminal_event(AttemptPhase.business, forbidden)

    # [utest->req~shared-audit-outcome-later-failure~1]
    async def test_a_later_operation_failure_is_the_attempts_one_row(self):
        sink = RecordingSink()
        writer = make_writer(sink=sink)
        attempt = AuthAttempt("POST", "/auth/sign-out-all")
        event = terminal_event(AttemptPhase.later, AuthEventResult.revocation_unconfirmed,
                               operation=AuthOperation.sign_out_all, actor=verified_test_actor())
        await writer.write_standalone(attempt, event)
        assert [row["result"] for row in sink.rows] == [AuthEventResult.revocation_unconfirmed]
        with pytest.raises(InvalidTerminalOutcomeError):
            terminal_event(AttemptPhase.later, AuthEventResult.succeeded)

    # [utest->req~shared-audit-outcome-succeeded~1]
    def test_succeeded_is_the_only_success_code(self):
        event = terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                               operation=AuthOperation.sync)
        assert event.result is AuthEventResult.succeeded
        with pytest.raises(InvalidTerminalOutcomeError):
            terminal_event(AttemptPhase.success, AuthEventResult.policy_rejected)

    # [utest->req~shared-audit-write-in-transaction~1]
    async def test_an_attempt_in_a_transaction_writes_inside_it(self):
        sink = RecordingSink()
        sessions: list[FakeSession] = []
        writer = make_writer(sink=sink, sessions=sessions)
        session = FakeSession()
        await writer.write_in_transaction(session, AuthAttempt("POST", "/auth/claim-anonymous-grant"),
                                          terminal_event(AttemptPhase.success,
                                                         AuthEventResult.succeeded,
                                                         operation=AuthOperation.claim_anonymous_grant,
                                                         actor=verified_test_actor()))
        # Written on the caller's session, committed by that same transaction.
        assert sink.sessions == [session]
        assert session.committed == 0
        assert sessions == []

    # [utest->req~shared-audit-write-standalone~1]
    async def test_an_early_rejection_writes_a_standalone_durable_row(self):
        sink = RecordingSink()
        sessions: list[FakeSession] = []
        writer = make_writer(sink=sink, sessions=sessions)
        await writer.write_standalone(AuthAttempt("POST", "/auth/sync"),
                                      terminal_event(AttemptPhase.barrier,
                                                     AuthEventResult.blocked_user,
                                                     operation=AuthOperation.sync,
                                                     actor=verified_test_actor()))
        assert len(sessions) == 1
        assert sessions[0].committed == 1
        assert sink.sessions == [sessions[0]]

    # [utest->req~shared-audit-write-before-response~1]
    # [utest->req~shared-audit-obligation-of-path~1]
    def test_the_row_is_written_before_the_response_and_is_never_best_effort(self):
        sink = RecordingSink()
        counter = AuthResultCounter()
        app = build_app([("POST", "/auth/sync")],
                        resolver=FakeResolver(ResolutionOutcome.blocked_user),
                        writer=make_writer(sink=sink, counter=counter))
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={"Authorization": f"Bearer {make_token('u1')}"})
        # The audit obligation is the path's, not challenge consumption's: `sync` carries no
        # challenge and still writes its row before the rejection is returned.
        assert [row["result"] for row in sink.rows] == [AuthEventResult.blocked_user]
        assert sink.rows[0]["operation"] is AuthOperation.sync
        assert sink.rows[0]["challenge_row_id"] is None
        assert response.status_code == 403

        # A failed audit write is logged, and the client still gets the rejection it earned.
        failing = RecordingSink(fail=True)
        app = build_app([("POST", "/auth/sync")],
                        resolver=FakeResolver(ResolutionOutcome.blocked_user),
                        writer=make_writer(sink=failing))
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={"Authorization": f"Bearer {make_token('u1')}"})
        assert failing.rows == []
        assert response.status_code == 403
        assert response.json()["code"] == "account_unavailable"

    # [utest->req~shared-off-path-no-audit-row~1]
    def test_off_the_path_no_row_is_written_and_the_counter_still_fires(self):
        sink = RecordingSink()
        counter = AuthResultCounter()
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(),
                        writer=make_writer(sink=sink, counter=counter))
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me")
        assert response.status_code == 401
        assert sink.rows == []
        assert counter.value(result=AuthEventResult.invalid_external_jwt,
                             route="/users/me", reason="missing_token") == 1

    # [utest->req~shared-off-path-no-audit-row~1]
    async def test_the_writer_refuses_to_cross_the_path_boundary(self):
        writer = make_writer()
        off_path = AuthAttempt("GET", "/users/me")
        with pytest.raises(OffPathAuditError):
            await writer.write_standalone(off_path,
                                          terminal_event(AttemptPhase.barrier,
                                                         AuthEventResult.blocked_user))
        with pytest.raises(OffPathAuditError):
            writer.record_off_path(AuthAttempt("POST", "/auth/sync"), AuthEventResult.blocked_user)

    # [utest->req~shared-barrier-result-first-class~1]
    def test_a_barrier_result_is_first_class_on_and_off_the_path(self):
        sink = RecordingSink()
        counter = AuthResultCounter()
        writer = make_writer(sink=sink, counter=counter)
        on_path = build_app([("POST", "/auth/sync")],
                            resolver=FakeResolver(ResolutionOutcome.historical_identity),
                            writer=writer)
        with TestClient(on_path, raise_server_exceptions=False) as client:
            client.post("/auth/sync", headers={"Authorization": f"Bearer {make_token('u1')}"})
        # On the path: its own stored result, never collapsed into a generic 401 log line.
        assert [row["result"] for row in sink.rows] == [AuthEventResult.historical_identity]

        off_counter = AuthResultCounter()
        off_path = build_app([("GET", "/chats/{chat_id}")],
                             resolver=FakeResolver(ResolutionOutcome.historical_identity),
                             writer=make_writer(counter=off_counter))
        with structlog.testing.capture_logs() as logs:
            with TestClient(off_path, raise_server_exceptions=False) as client:
                client.get("/chats/abc",
                           headers={"Authorization": f"Bearer {make_token('u1')}"})
        # Off the path: the named result code in logs and metrics, on a bounded route label.
        assert any(entry.get("result") == AuthEventResult.historical_identity for entry in logs)
        assert off_counter.value(result=AuthEventResult.historical_identity,
                                 route="/chats/{chat_id}") == 1

    # [utest->req~shared-challenge-scope-narrower-subset~1]
    def test_a_barrier_rejection_consumes_no_challenge(self):
        class ChallengeStoreSpy:
            def __init__(self):
                self.touched = False

            def __getattr__(self, name):
                self.touched = True
                raise AssertionError(f"challenge store touched: {name}")

        store = ChallengeStoreSpy()
        app = build_app([("POST", "/auth/claim-anonymous-grant")],
                        resolver=FakeResolver(ResolutionOutcome.blocked_user),
                        writer=make_writer())
        app.state.challenge_store = store
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/claim-anonymous-grant",
                                   headers={"Authorization": f"Bearer {make_token('u1')}"},
                                   json={"challenge_id": "live-challenge"})
        assert response.status_code == 403
        assert store.touched is False


class TestRouteRegistries:
    # [utest->req~shared-route-categories~1]
    def test_the_three_registries_do_not_overlap(self):
        public = set(PUBLIC_ROUTES)
        callbacks = {(route.method, route.path) for route in PROVIDER_CALLBACK_ROUTES}
        authenticated = {(route.method, route.path) for route in AUTHENTICATED_ROUTES}
        assert public & callbacks == set()
        assert public & authenticated == set()
        assert callbacks & authenticated == set()
        assert all(isinstance(route, AuthenticatedRoute) for route in AUTHENTICATED_ROUTES)


def test_barrier_rejection_never_exposes_the_internal_result():
    error = BarrierRejectionError(AuthEventResult.blocked_user)
    assert error.error_code == "account_unavailable"
    assert error.result is AuthEventResult.blocked_user


class TestTheShippedApp:
    """The barrier is not a library the shipped app could forget to mount: these tests drive
    requests through `nativespeaker.api.app.main.app` itself."""

    @staticmethod
    def _shipped_app(resolver: FakeResolver, sink: RecordingSink, counter: AuthResultCounter):
        from nativespeaker.api.app.main import app

        app.state.auth_barrier = AuthBarrier(
            integrations=make_integrations(), resolver=resolver,
            audit=make_writer(sink=sink, counter=counter), subject_hasher=subject_hasher)
        return app

    # [utest->req~shared-prehandler-barrier~1]
    def test_the_shipped_app_runs_the_barrier_on_an_authenticated_route(self):
        counter = AuthResultCounter()
        app = self._shipped_app(FakeResolver(), RecordingSink(), counter)
        # TestClient is used without its context manager on purpose: the shipped lifespan wants
        # a database, a Firebase credential and a JWKS endpoint, none of which a unit test has.
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health/ready")
        assert response.status_code == 200      # public: the barrier passes it through

        response = client.get("/")
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"
        assert counter.value(result=AuthEventResult.invalid_external_jwt,
                             route="/", reason="missing_token") == 1

    # [utest->req~shared-prehandler-barrier~1]
    def test_the_shipped_app_rejects_a_blocked_user_before_the_handler(self):
        app = self._shipped_app(FakeResolver(ResolutionOutcome.blocked_user),
                                RecordingSink(), AuthResultCounter())
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/examples?lang=en",
                              headers={"Authorization": f"Bearer {make_token('u1')}"})
        # No handler ran: the route needs a chat service the test never wired, so a 403 here is
        # proof the barrier rejected ahead of the handler and its dependencies.
        assert response.status_code == 403
        assert response.json()["code"] == "account_unavailable"

    # [utest->req~shared-route-categories~1]
    def test_every_shipped_route_is_in_exactly_one_category(self):
        from nativespeaker.api.app.main import app

        # The startup assertion the shipped app runs, against the shipped router.
        assert_route_categories(app)
